"""A tiny, generic hub workflow (E1 shape) driven by a fixed replay plan instead of the runtime brain.

Used by the harness tests (and as an integration smoke when the compiler/brain are not ready): it exercises the
twin, the mock bank and the scorer with the same node shapes the compiler emits (listen node with tts {{say}},
passthrough `ctl` code node, guarded api nodes with node-level response_mapping, s_bye, a_close_r/a_close_n,
e_end). Everything is derived from the ToolCatalog; no brief values live here.

Plan steps (JSON lists, decoded from hex inside the brace-free ctl code; one ctl entry runs steps until it
reaches a `say`, `call` or `close`):
  ["say", text, listen_node]            -> vars say/nx (listen_node is "s_l" or "s_safe")
  ["set", var, value]                   -> vars[var] = value, continue
  ["call", tool, {field: value, ...}]   -> b_a_<tool>_<field>, r_a_<tool>_s = "pending", nx = a_<tool>
                                           (with node_prefix "": the 2nd item is the api node key itself)
  ["close", outcome, reason, goodbye]   -> co, cr, cmode, say, nx = s_bye
"""
import json

CTL_CODE = """import json
try:
    P = json.loads(bytes.fromhex(PLAN_HEX).decode('utf-8'))
    i = int(vars.get('tp') or '0')
    vars['nx'] = 's_safe'
    while i < len(P):
        s = P[i]
        i = i + 1
        k = s[0]
        if k == 'say':
            vars['say'] = s[1]
            vars['nx'] = s[2]
            break
        if k == 'set':
            vars[s[1]] = s[2]
            continue
        if k == 'call':
            node = NODE_PREFIX + s[1]
            for f in s[2]:
                vars['b_' + node + '_' + f] = str(s[2][f])
            vars['r_' + node + '_s'] = 'pending'
            vars['nx'] = node
            break
        if k == 'close':
            vars['co'] = s[1]
            vars['cr'] = s[2]
            vars['cmode'] = 'r' if s[2] else 'n'
            vars['say'] = s[3]
            vars['nx'] = 's_bye'
            break
    vars['tp'] = str(i)
except Exception:
    vars['nx'] = 's_safe'
"""

LISTEN_TASK = ("You have already said the line. Say nothing else and do not call any tool. No tool call is allowed in "
               "this turn. If you must speak, repeat exactly: {{say}}")


def _always(target):
    return {"target_node": target, "description": "always", "condition": {"operator": "always"}}


def _eq(target, *pairs):
    conds = [{"variable": v, "operator": "equals", "operand": o} for v, o in pairs]
    if len(conds) == 1:
        return {"target_node": target, "description": target, "condition": {"logic": "or", "conditions": conds}}
    return {"target_node": target, "description": target,
            "condition": {"logic": "or", "conditions": [{"logic": "and", "conditions": conds}]}}


def ctl_code(plan, node_prefix="a_"):
    """Brace-free replay snippet. node_prefix "" lets `call` steps name api nodes directly (compiled graphs)."""
    return ("PLAN_HEX = '" + json.dumps(plan, separators=(",", ":")).encode("utf-8").hex() + "'\n" +
            "NODE_PREFIX = '" + node_prefix + "'\n" + CTL_CODE)


def replace_ctl(workflow, plan, ctl="ctl", node_prefix=""):
    """Copy of a (compiled) workflow whose ctl node replays `plan` instead of running the brain."""
    wf = json.loads(json.dumps(workflow))
    props = wf["nodes"][ctl]["pre_actions"][0]["function"]["parameters"]["properties"]
    props["code"]["default"] = ctl_code(plan, node_prefix)
    return wf


def _api_node(key, tool, catalog, body_fields, customer_key="customer_id"):
    t = catalog["tools"][tool]
    roles = t.get("roles") or {}
    cust = (roles.get("request") or {}).get("customer")
    props = {}
    for f, meta in (t.get("request") or {}).items():
        if f not in body_fields and f != cust:
            continue
        p = {"type": meta.get("type") or "string"}
        p["default"] = "{{%s}}" % customer_key if f == cust else body_fields[f]
        if meta.get("enum"):
            p["enum"] = list(meta["enum"])
        props[f] = p
    return {
        "name": key, "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "ctl",
        "on_enter": {"type": "silent"}, "suppress_tool_results": True, "disable_inactivity_monitor": True,
        "pre_actions": [{"type": "function", "config": {"timeoutMs": 12000, "maxRetries": int(t.get("max_retries", 0))
                                                         if not t.get("write") else 0},
                         "function": {"name": tool, "handler": "__function__:api_call", "description": t.get("summary", ""),
                                      "parameters": {"type": "object", "properties": {
                                          "url": {"type": "string", "default": t["url"]},
                                          "method": {"type": "string", "default": t.get("method", "POST")},
                                          "headers": {"type": "object", "properties": {
                                              "Content-Type": {"type": "string", "default": "application/json"}}},
                                          "body": {"type": "object", "required": [], "properties": props}}}}}],
        "response_mapping": [{"path": "data." + leaf, "variable": "r_%s_%s" % (key, role)}
                             for role, leaf in sorted((roles.get("response") or {}).items())],
        "transitions": [],
    }


def hub_workflow(catalog, plan, opening="Hello, am I speaking with {{first_name}}?", clarify="Sorry?",
                 customer_key="customer_id"):
    """-> workflow JSON (no nulls) whose ctl replays `plan`."""
    roles = {t: (catalog["tools"][t].get("roles") or {}) for t in catalog["tools"]}
    nodes = {}
    listen_extraction = [{"name": "u_text", "type": "string", "description": "verbatim", "min_confidence": 0.3},
                         {"name": "u_act", "type": "string", "description": "act", "min_confidence": 0.5}]
    nodes["s_open"] = {"name": "s_open", "node_type": "conversation", "on_enter": {"type": "tts", "text": opening},
                       "task_message": "Say exactly this and nothing else, and do not call any tool: «%s»" % opening,
                       "extraction_schema": listen_extraction, "transitions": [_always("ctl")]}
    nodes["s_l"] = {"name": "s_l", "node_type": "conversation", "on_enter": {"type": "tts", "text": "{{say}}"},
                    "task_message": LISTEN_TASK, "extraction_schema": listen_extraction,
                    "transitions": [_always("ctl")]}
    nodes["s_safe"] = {"name": "s_safe", "node_type": "conversation", "on_enter": {"type": "tts", "text": clarify},
                       "task_message": LISTEN_TASK, "extraction_schema": listen_extraction,
                       "transitions": [_always("ctl")]}
    api_keys = []
    for tool in catalog["tools"]:
        if tool == "close_call":
            continue
        key = "a_" + tool
        req = (roles[tool].get("request") or {})
        fields = {f: "{{b_%s_%s}}" % (key, f) for r, f in req.items() if r != "customer"}
        nodes[key] = _api_node(key, tool, catalog, fields, customer_key)
        nodes[key]["transitions"] = [_always("ctl")]
        api_keys.append(key)
    creq = roles["close_call"].get("request") or {}
    out_f, rea_f = creq.get("outcome"), creq.get("reason")
    close_r = {out_f: "{{co}}"}
    if rea_f:
        close_r[rea_f] = "{{cr}}"
    nodes["a_close_r"] = _api_node("a_close_r", "close_call", catalog, close_r, customer_key)
    nodes["a_close_r"]["transitions"] = [_always("e_end")]
    nodes["a_close_r"]["passthrough_default_transition"] = "e_end"
    nodes["a_close_n"] = _api_node("a_close_n", "close_call", catalog, {out_f: "{{co}}"}, customer_key)
    nodes["a_close_n"]["transitions"] = [_always("e_end")]
    nodes["a_close_n"]["passthrough_default_transition"] = "e_end"
    nodes["s_bye"] = {"name": "s_bye", "node_type": "conversation", "passthrough": True,
                      "passthrough_default_transition": "a_close_n", "on_enter": {"type": "tts", "text": "{{say}}"},
                      "task_message": LISTEN_TASK,
                      "transitions": [_eq("a_close_r", ("cmode", "r")), _always("a_close_n")]}
    nodes["e_end"] = {"name": "e_end", "node_type": "end_call", "message_mode": "none",
                      "disable_inactivity_monitor": True, "transitions": []}
    trs = [_eq(k, ("nx", k), ("r_%s_s" % k, "pending")) for k in api_keys]
    trs += [_eq(k, ("nx", k)) for k in ("s_l", "s_bye")]
    trs.append(_always("s_safe"))
    nodes["ctl"] = {"name": "ctl", "node_type": "code", "passthrough": True, "passthrough_default_transition": "s_safe",
                    "on_enter": {"type": "silent"},
                    "pre_actions": [{"type": "function", "function": {
                        "name": "code_exec", "handler": "__function__:code_exec",
                        "parameters": {"type": "object", "properties": {
                            "code": {"type": "string", "default": ctl_code(plan)},
                            "timeout_ms": {"type": "number", "default": 20000}}}}}],
                    "transitions": trs}
    return {"initial_node": "s_open", "system_prompt": "toy", "nodes": nodes, "global_nodes": {},
            "test_variables": {"first_name": "Test"}}
