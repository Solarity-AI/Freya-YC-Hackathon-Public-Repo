"""Flow mode compiler: a Spec with mode "flow" (spec.flow, see runtime/flow.py) + the bank's operations -> a Freya
workflow. Generic: any service contract, any flow drawing; nothing of a specific case.

- flow_ops(doc, mock_url) -> {op_key: op}: every operation of an OpenAPI document with its exact method, path, path /
  query / header parameters, JSON body fields and top-level response fields (all statuses). The tools call the
  operation at mock_url + its own path, with the same method: path and query parameters are templated into the URL.
- compile_flow(spec, ops) -> (workflow, wiring): s_open (opening line) -> ctl (the packed flow runtime) <-> one
  api_request node per operation the flow calls, s_flow (the question listen node), s_safe, s_bye -> end.
"""
import copy
import re
from urllib.parse import quote

from builder import openapi_model as OM
from builder.compiler import graph, render
from builder.compiler.graph import (ALWAYS, API_TIMEOUT_MS, CTL_TIMEOUT_MS, LISTEN_TASK, MAX_NODE_TURNS, SAY_TTS,
                                    SILENT_TASK, _always, _c, _or, _tr)
from builder.compiler import snippet

LISTEN, SAFE, BYE, OPEN, CTL, END = "s_flow", "s_safe", "s_bye", "s_open", "ctl", "end"
# slow bank answers: wait up to 30 s for them; writes are never retried
FLOW_API_TIMEOUT_MS = 30000
KIND_VALUES = ["none", "answer", "yes", "no", "hedge", "question", "repeat", "hold", "refusal", "smalltalk",
               "correction"]
U_VAL_DESC = ("A value the customer gives in this message, normalised: digits only for any number or digit sequence "
              "(number words turned into digits, in the order said, e.g. 'bir iki üç dört' -> 1234); a date as "
              "YYYY-MM-DD; an e-mail address as written; empty if none.")
U_KIND_DESC = ("What the most recent customer message does. yes: a clear yes, accepts or confirms. no: declines or "
               "says no. hedge: an unsure or half yes ('belki', 'galiba', 'maybe', 'I suppose'). answer: gives information or a choice. question: asks something. repeat: asks the agent to "
               "repeat. hold: asks to wait. refusal: refuses to continue. smalltalk: small talk only. correction: "
               "corrects something said before. none: none of these.")


class FlowCompileError(Exception):
    pass


def _slug(s, n=40):
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", str(s))).strip("_")[:n] or "op"


def _props(sch):
    sch = sch or {}
    props = dict(sch.get("properties") or {})
    for part in (sch.get("allOf") or []) + (sch.get("oneOf") or []) + (sch.get("anyOf") or []):
        if isinstance(part, dict):
            props.update(part.get("properties") or {})
    return props


def _flatten(doc, sch, prefix, req, body, required, depth=0):
    """Request body schema -> dotted leaf fields ({"body": {"memberId"}} -> "body.memberId"); a leaf is required
    when it and every object above it are required."""
    reqs = set(str(r) for r in (sch or {}).get("required") or [])
    for f, leaf in _props(sch).items():
        leaf = OM._resolve(doc, leaf) if isinstance(leaf, dict) and "$ref" in leaf else (leaf or {})
        name = prefix + str(f)
        if depth < 3 and (leaf.get("properties") or OM._type(leaf) == "object") and _props(leaf):
            _flatten(doc, leaf, name + ".", req and str(f) in reqs, body, required, depth + 1)
            continue
        body[name] = {"type": OM._type(leaf), "enum": list(leaf.get("enum") or []),
                      "description": str(leaf.get("description") or "")[:300]}
        if req and str(f) in reqs:
            required.append(name)


def flow_ops(doc, mock_url=""):
    """-> {op_key: {key, node, method, path, url, params {name: in}, body {field: leaf}, required [..], res [..],
    summary}} for every operation in the OpenAPI document."""
    out = {}
    paths = doc.get("paths") or {}
    for path in sorted(paths, key=str):
        item = paths[path] or {}
        if not isinstance(item, dict):
            continue
        shared = item.get("parameters") or []
        for method in ("get", "post", "put", "patch", "delete"):
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            key = str(op.get("operationId") or "").strip() or "%s_%s" % (method, _slug(path))
            key = _slug(key, 60)
            while key in out:
                key += "_x"
            params = {}
            for p in list(shared) + list(op.get("parameters") or []):
                p = OM._resolve(doc, p) if isinstance(p, dict) and "$ref" in p else p
                if isinstance(p, dict) and p.get("name") and p.get("in") in ("path", "query", "header"):
                    sch = OM._resolve(doc, p.get("schema") or {}) or {}
                    params[str(p["name"])] = {"in": p["in"], "type": OM._type(sch) if sch else "string",
                                              "required": bool(p.get("required") or p.get("in") == "path"),
                                              "description": str(p.get("description") or "")[:300]}
            body, required = {}, []
            if op.get("requestBody"):
                _flatten(doc, OM._json_schema(doc, op.get("requestBody")), "", True, body, required)
            res = []
            for _, resp in sorted((op.get("responses") or {}).items(), key=lambda kv: str(kv[0])):
                rs = OM._json_schema(doc, resp)
                for f in _props(rs):
                    if str(f) not in res:
                        res.append(str(f))
            out[key] = {"key": key, "node": "f_" + _slug(key, 36), "method": method.upper(), "path": path,
                        "params": params, "body": body, "required": required, "res": res,
                        "summary": str(op.get("summary") or op.get("description") or "")[:300],
                        "base": (mock_url or "").rstrip("/")}
    return out


def _var(node, field):
    return "b_%s_%s" % (node, _slug(field, 30))


def _url(op):
    node = op["node"]
    path = re.sub(r"\{([^{}]+)\}", lambda m: "{{" + _var(node, m.group(1)) + "}}", op["path"])
    q = ["%s={{%s}}" % (quote(n, safe=""), _var(node, n)) for n, p in sorted(op["params"].items())
         if p["in"] == "query"]
    return op["base"] + path + (("?" + "&".join(q)) if q else "")


def _binding(op, used):
    """The api_call pre_action of one operation's node: same method and path as the contract."""
    node = op["node"]
    props = {}
    for f, leaf in op["body"].items():
        if f not in used and f not in op["required"]:
            continue
        typ = graph._leaf_type(leaf["type"])
        p = {"type": typ, "default": "{{" + _var(node, f) + "}}"}
        if leaf.get("enum"):
            p["enum"] = list(leaf["enum"])
        cur, parts = props, f.split(".")
        for part in parts[:-1]:                         # a nested body field: {"body": {"memberId": ...}}
            cur = cur.setdefault(part, {"type": "object", "properties": {}})["properties"]
        cur[parts[-1]] = p
    headers = {"Content-Type": {"type": "string", "default": "application/json"}}
    for n, p in sorted(op["params"].items()):
        if p["in"] == "header":
            headers[n] = {"type": "string", "default": "{{" + _var(node, n) + "}}"}
    params = {"url": {"type": "string", "default": _url(op)},
              "method": {"type": "string", "default": op["method"]},
              "headers": {"type": "object", "properties": headers}}
    if op["method"] in ("POST", "PUT", "PATCH") or props:
        params["body"] = {"type": "object", "required": sorted(set(f.split(".")[0] for f in op["required"]
                                                                 if f.split(".")[0] in props)),
                          "properties": props}
    return {"type": "function", "config": {"timeoutMs": FLOW_API_TIMEOUT_MS, "maxRetries": 0},
            "function": {"name": node, "handler": "__function__:api_call",
                         "description": op["summary"] or op["key"],
                         "parameters": {"type": "object", "properties": params}}}


def _used_ops(spec):
    used = {}
    for nd in ((spec.get("flow") or {}).get("nodes") or {}).values():
        if isinstance(nd, dict) and nd.get("type") == "call":
            used.setdefault(str(nd.get("op")), set()).update((nd.get("args") or {}).keys())
    return used


def wiring(spec, ops):
    used = _used_ops(spec)
    missing = sorted(k for k in used if k not in ops)
    if missing:
        raise FlowCompileError("the flow calls operations the contract does not have: %s" % ", ".join(missing))
    w_ops = {}
    for k in sorted(used):
        op = ops[k]
        node = op["node"]
        fields = sorted(set(op["body"]) | set(op["params"]))
        w_ops[k] = {"node": node, "fname": node, "body": {f: _var(node, f) for f in fields},
                    "res": {f: "r_%s_%s" % (node, _slug(f, 30)) for f in op["res"]}}
    return {"v": 1, "mode": "flow", "listen": LISTEN, "safe": SAFE, "bye": BYE, "end": END, "ops": w_ops}


def _intent_values(spec):
    F = spec.get("flow") or {}
    vals, desc = ["none", "repeat"], ["none: nothing below", "repeat: asks the agent to say it again"]
    for g in F.get("global") or []:
        gid = str(g.get("id") or "")
        if gid and gid not in vals:
            vals.append(gid)
            desc.append("%s: %s" % (gid, str(g.get("desc") or "")[:160]))
    for nd in (F.get("nodes") or {}).values():
        for ch in (nd or {}).get("choices") or [] if isinstance(nd, dict) else []:
            cid = str(ch.get("id") or "")
            if cid and cid not in vals:
                vals.append(cid)
                desc.append("%s: %s" % (cid, str(ch.get("desc") or "")[:160]))
    return vals, desc


def extraction_schema(spec):
    lang = render.LANGUAGES.get(render.call_language(spec), render.call_language(spec))
    vals, desc = _intent_values(spec)
    fields = [
        {"name": "u_text", "type": "string", "min_confidence": 0.3,
         "description": render.U_TEXT_DESC + " Keep the customer's language (" + lang + ")."},
        {"name": "u_val", "type": "string", "min_confidence": 0.4, "description": U_VAL_DESC},
        {"name": "u_kind", "type": "string", "min_confidence": 0.5, "description": U_KIND_DESC,
         "enum_values": list(KIND_VALUES)},
        {"name": "u_intent", "type": "string", "min_confidence": 0.5, "enum_values": vals,
         "description": ("What the customer wants in their most recent message, answering the agent's last "
                         "question. Pick the one that fits; none when nothing fits. " + "; ".join(desc))[:1900]},
    ]
    if render.call_language(spec) != "en":
        fields.insert(1, {"name": "u_en", "type": "string", "min_confidence": 0.3, "description": render.U_EN_DESC})
    return fields


def _listen(name, spec, tts=SAY_TTS, task=LISTEN_TASK):
    return {"name": name, "node_type": "conversation", "on_enter": {"type": "tts", "text": tts},
            "task_message": task, "extraction_schema": extraction_schema(spec), "max_node_turns": MAX_NODE_TURNS,
            "max_turn_transition": CTL, "transitions": [_always(CTL)]}


def system_prompt(spec):
    bank = spec.get("bank") or {}
    lang = render.LANGUAGES.get(str(bank.get("language") or "en").lower()[:2], str(bank.get("language") or "English"))
    who = str(bank.get("assistant_self") or "") or "the bank's digital assistant"
    return " ".join([
        "You are %s, speaking on the phone with a customer of %s. Speak %s." % (who, bank.get("name") or "the bank",
                                                                               lang),
        "Every line you say is given to you by the workflow. Say exactly the line you are given and nothing else.",
        "Never call a tool. Tool calls are made by the workflow, not by you.",
        "Never invent facts, amounts, dates or offers.", "Keep every turn short."])


def ctl_code(spec, w):
    from runtime import bundle
    rs = {"v": 1, "spec": snippet_spec(spec), "wiring": w}
    inner = bundle.make_snippet(rs, encoding="json", max_bytes=0, compact=False, modules=bundle.FLOW_MODULES)
    probs = snippet.check_code(inner)
    if probs:
        raise FlowCompileError("; ".join(probs[:5]))
    code = bundle.pack_snippet(inner)
    probs = snippet.check_code(code)
    if probs:
        raise FlowCompileError("; ".join(probs[:5]))
    return code


def snippet_spec(spec):
    s = copy.deepcopy(spec)
    for k in ("meta", "banned"):
        s.pop(k, None)
    for nd in ((s.get("flow") or {}).get("nodes") or {}).values():
        if isinstance(nd, dict):
            nd.pop("source", None)
            for ch in nd.get("choices") or []:
                ch.pop("desc", None)
    for g in (s.get("flow") or {}).get("global") or []:
        g.pop("desc", None)
    return s


def compile_flow(spec, ops, code=None):
    """-> (workflow, wiring). Deterministic; no null values."""
    w = wiring(spec, ops)
    code = code or ctl_code(spec, w)
    used = _used_ops(spec)
    nodes = {}
    open_line = render.compile_line((spec.get("opening") or {}).get("line") or "", spec) if (
        spec.get("opening") or {}).get("line") else ""
    nodes[OPEN] = {"name": OPEN, "node_type": "conversation", "on_enter": {"type": "tts", "text": open_line},
                   "task_message": "Say exactly this and nothing else, and do not call any tool: «%s»" % open_line,
                   "extraction_schema": extraction_schema(spec), "transitions": [_always(CTL)]}
    trs = []
    for k in sorted(w["ops"]):
        node = w["ops"][k]["node"]
        trs.append(_tr(node, "ctl calls " + k, _or(_c("nx", "equals", node))))
    for n in (LISTEN, BYE):
        trs.append(_tr(n, "ctl routes to " + n, _or(_c("nx", "equals", n))))
    trs.append(_always(SAFE))
    nodes[CTL] = {"name": CTL, "node_type": "code", "passthrough": True, "passthrough_default_transition": SAFE,
                  "on_enter": {"type": "silent"},
                  "pre_actions": [{"type": "function", "function": {
                      "name": "code_exec", "handler": "__function__:code_exec",
                      "parameters": {"type": "object", "properties": {
                          "code": {"type": "string", "default": code},
                          "timeout_ms": {"type": "number", "default": CTL_TIMEOUT_MS}}}}}],
                  "transitions": trs}
    nodes[LISTEN] = _listen(LISTEN, spec)
    clar = render.compile_line(((spec.get("lines") or {}).get("clarify") or "").strip(), spec) or SAY_TTS
    nodes[SAFE] = _listen(SAFE, spec, tts=clar, task=LISTEN_TASK.replace(SAY_TTS, clar))
    for k in sorted(w["ops"]):
        op = ops[k]
        node = op["node"]
        nodes[node] = {"name": node, "node_type": "api_request", "passthrough": True,
                       "passthrough_default_transition": CTL, "on_enter": {"type": "silent"},
                       "pre_actions": [_binding(op, used.get(k) or set())],
                       "response_mapping": [{"path": "data." + f, "variable": v}
                                            for f, v in sorted(w["ops"][k]["res"].items())],
                       "suppress_tool_results": True, "disable_inactivity_monitor": True,
                       "transitions": [_always(CTL)]}
    nodes[BYE] = {"name": BYE, "node_type": "conversation", "passthrough": True,
                  "passthrough_default_transition": END, "on_enter": {"type": "tts", "text": SAY_TTS},
                  "task_message": SILENT_TASK, "disable_inactivity_monitor": True, "transitions": [_always(END)]}
    nodes[END] = graph._end_node()
    nodes[END]["name"] = END
    cv = spec.get("call_variables") or {}
    tv = {}
    for d in cv.get("declared") or []:
        n = str((d or {}).get("name") or "")
        if n:
            tv[n] = graph.TEST_NOW if n == cv.get("now") else str(d.get("example") or "Test")
    wf = {"initial_node": OPEN, "system_prompt": system_prompt(spec), "nodes": nodes, "global_nodes": {},
          "test_variables": tv}
    return wf, w


def check(workflow, wiring_, spec):
    """Structural checks -> list of error strings (targets exist, flow references resolve, no null)."""
    errs = []
    nodes = workflow.get("nodes") or {}
    for n, nd in nodes.items():
        for t in nd.get("transitions") or []:
            if t.get("target_node") not in nodes:
                errs.append("%s: transition to unknown node %s" % (n, t.get("target_node")))
        if nd.get("passthrough_default_transition") and nd["passthrough_default_transition"] not in nodes:
            errs.append("%s: default transition to unknown node" % n)
    F = spec.get("flow") or {}
    fn = F.get("nodes") or {}
    if F.get("start") not in fn:
        errs.append("flow.start %r is not a node" % F.get("start"))
    refs = ("next", "else", "on_none", "on_fail", "on_error")
    for nid, nd in fn.items():
        if not isinstance(nd, dict):
            errs.append("flow node %s is not an object" % nid)
            continue
        if nd.get("type") not in ("call", "branch", "say", "ask", "select", "set", "end"):
            errs.append("flow node %s: unknown type %r" % (nid, nd.get("type")))
        targets = [nd.get(r) for r in refs if nd.get(r)]
        targets += [c.get("next") for c in nd.get("cases") or [] if isinstance(c, dict)]
        targets += [c.get("next") for c in nd.get("choices") or [] if isinstance(c, dict) and c.get("next")]
        targets += list((nd.get("on_status") or {}).values())
        for t in targets:
            if t not in fn:
                errs.append("flow node %s: goes to unknown node %r" % (nid, t))
        if nd.get("type") in ("say", "set", "call", "select") and not nd.get("next"):
            errs.append("flow node %s (%s) has no next" % (nid, nd.get("type")))
        if nd.get("type") == "ask" and not nd.get("choices"):
            errs.append("flow node %s: a question without choices" % nid)
    for g in F.get("global") or []:
        if g.get("next") and g["next"] not in fn:
            errs.append("flow global %s: goes to unknown node %r" % (g.get("id"), g.get("next")))
    for k in ("on_error", "on_unclear"):
        if F.get(k) and F[k] not in fn:
            errs.append("flow.%s %r is not a node" % (k, F[k]))
    import json
    if ": null" in json.dumps(workflow):
        errs.append("a null value in the workflow")
    return errs
