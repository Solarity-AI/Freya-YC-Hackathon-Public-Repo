"""Graph template: wiring + nodes + transitions (docs/CONTRACTS.md C.8, D.2-D.5). Owner: agent 3.

Expected wiring for the golden specs: tests/fixtures/wiring-a.json, wiring-ab.json. Output must be byte-stable.

CONTRACT NOTE (agent 3; where D.3/D.5/C.8 leave room, the simplest reading is implemented):
1. `ctl` gets a guarded transition to EVERY api node, including `a_close_r` / `a_close_n` (needed for
   bye=apinode and bye=listen; harmless for bye=pass because ctl writes nx=s_bye there). Listen targets are
   s_rp s_tp s_id s_neg s_conf (+ s_bye unless bye=apinode); never s_open / s_safe.
2. `s_bye -> a_close_r` (cmode equals r) and `s_bye -> a_close_n` (always) carry no `pending` guard, exactly as
   D.3 writes them; the lint guard rule therefore exempts transitions out of s_bye (an `always` cannot be guarded).
3. bye=apinode: no s_bye node, wiring `bye` = "" and the close nodes speak `{{say}}` as tts on entry.
4a. Chain targets are restricted to the C.8 plan order instead of "all other chainable writers": a promise
   node chains to other promise nodes, note nodes, transfer nodes, s_bye, close; a note node to other note nodes,
   transfer nodes, s_bye, close; a transfer node to s_bye, close; a callback node only to s_bye, close.
   (Same behaviour for every plan C.8 can build; ~45% smaller graph.)
4. Optional spokes: `cb` nodes exist only when the Spec has `third_party.callback`; `xfer` nodes only when some
   situation or intent action names a queue; note nodes per D.1/C.8 (`notes.enabled` + scope).
5. Body fields (wiring.nodes[*].body) = every role-bound request field except the customer role and the `text`
   role (the latter only when `notes.text` is non-empty, for the note tool); a call-scoped note node
   (`a_note_call_1`) also drops the product role. The identity tool in per_field
   mode also gets its unbound answer fields. Close nodes use `co`/`cr`; `a_close_n` never has the reason field.
   A required field with no role and no runtime source is baked as a literal (example, else enum[0]) + WARN.
6. `wire` lists, for every emitted runtime body field, those whose type is not string or that carry a
   wire_format or a scale != 1.
7. test_variables: customer key -> "c_test", now -> a fixed synthetic ISO time, others -> "Test".
8. Identity chain (flag `vchain`, LATENCY): a verify node whose result says this answer verified skips ctl.
   All verified -> straight to the account read ctl armed (`wn_<verify> equals <acct>`, pending guard on the
   account node); verified with questions left -> straight to the ID listen node, which speaks the line ctl
   computed in advance (`wl_<verify> equals <listen>`). Each OR group compares the ok / verified / all leaves with
   one boolean spelling (wiring `vchain` {"t": [...], "f": [...]}, index-aligned). Only for a `bool_true` identity
   tool that maps the verified and all-verified leaves, and only with write_chain on (same G6 mechanism); anything
   else goes back to ctl as before.
"""
import copy
import json
import re

from builder.compiler import render, snippet
from builder.spec import vocab

_BODY_VAR = "b_%s_%s"                          # an api node's body variable: b_<node>_<field>
FLAGS_DEFAULT = {"bye": "pass", "write_chain": "on", "qnodes": "off", "uvars": "reset", "amount_tpl": "plain",
                 "vchain": "on"}
FLAG_VALUES = {"bye": ("pass", "apinode", "listen"), "write_chain": ("on", "off"), "qnodes": ("off",),
               "uvars": ("reset", "rotate"), "amount_tpl": ("plain", "json"), "vchain": ("on", "off")}

LISTEN_TASK = ("You have already said the line. Say nothing else and do not call any tool. "
               "No tool call is allowed in this turn. If you must speak, repeat exactly: {{say}}")
SILENT_TASK = "You have already said the line. Say nothing else and do not call any tool."
LISTEN_STAGES = ("rp", "tp", "id", "neg", "conf")
CTL_TIMEOUT_MS = 20000
API_TIMEOUT_MS = 12000
# Writes that are idempotent by contract may be re-sent on HTTP >= 500: a 5xx close records nothing and a repeated
# close answers "already closed" without recording twice. Every other write keeps maxRetries 0 (lint I3).
IDEMPOTENT_WRITE_RETRIES = {"close_call": 2}
MAX_NODE_TURNS = 100
TEST_NOW = "2026-01-07T11:00"
END_FUNCTION = "call_closed"
ALWAYS = {"operator": "always"}
SAY_TTS = "{{say}}"  # the ctl-composed line, spoken by listen/bye nodes


class CompileError(Exception):
    pass


def _log(kind, msg, **fields):
    import sys
    from builder import trace
    fields.setdefault("mod", "builder.compiler.graph." + sys._getframe(1).f_code.co_name)
    trace.event(kind, msg, **fields)                    # never raises


def merge_flags(flags=None):
    out = dict(FLAGS_DEFAULT)
    for k, v in (flags or {}).items():
        if k not in FLAGS_DEFAULT:
            raise CompileError(f"unknown compile flag {k!r}")
        if v not in FLAG_VALUES[k]:
            raise CompileError(f"bad value {v!r} for flag {k!r} (allowed: {', '.join(FLAG_VALUES[k])})")
        out[k] = v
    return out


# ------------------------------------------------------------------------------------------------ wiring (C.8)

def _n_verify(spec):
    idn = spec.get("identity") or {}
    q = len(idn.get("questions") or [])
    wrong = int(idn.get("max_wrong_total") or 0)
    hints = sum(int(h.get("max") or 0) for h in idn.get("hints") or [])
    return max(1, min(12, q + wrong + hints + 2))


def _uses_transfer(spec):
    if any((s or {}).get("queue") for s in (spec.get("situations") or {}).values()):
        return True
    return any((it.get("action") or {}).get("queue") for it in spec.get("intents") or [])


def _uses_callback(spec):
    tp = spec.get("third_party") or {}
    return bool(tp.get("callback")) and tp.get("mode") != "close"      # mode close never books (no a_cb nodes)


def _field_roles(tool):
    return {f: r for r, f in tool["roles"]["request"].items()}


def _node_entry(node, tool_name, catalog, spec, close=None, call_scope=False):
    tool = catalog["tools"][tool_name]
    froles = _field_roles(tool)
    notes_text = str((spec.get("notes") or {}).get("text") or "")
    body = {}
    for field in tool["request"]:
        role = froles.get(field)
        if role == "customer":
            continue
        if close is not None:
            if role == "outcome":
                body[field] = "co"
            elif role == "reason" and close == "r":
                body[field] = "cr"
            continue
        if role is None:
            if tool_name == "verify_identity" and catalog.get("identity_mode") == "per_field":
                body[field] = _BODY_VAR % (node, field)
            continue
        if role == "text" and not (tool_name == "add_note" and (notes_text or field in (tool.get("required") or []))):
            continue                    # a required note text without a Spec template carries the note's reason
        if role == "product" and call_scope:
            continue
        body[field] = _BODY_VAR % (node, field)
    res, res_leaf = {}, {}
    for role, leaf in tool["roles"]["response"].items():
        res[role] = "r_%s_%s" % (node, role)
        res_leaf[role] = leaf
    return {"tool": tool_name, "body": body, "res": res, "res_leaf": res_leaf}


# Promise kind (generic, language words only): a create_promise enum field whose values name "the full amount",
# "the minimum" and "part of it" (e.g. FULL/MINIMUM/PARTIAL). The runtime picks the value from the promised amount
# against the product's due amount and floor; without it the field would be baked as enum[0] for every promise.
_PK_WORDS = {
    "full": ("FULL", "TOTAL", "ALL", "COMPLETE", "ENTIRE", "WHOLE", "TAM", "TAMAMI", "TAMAMEN", "TUM", "TUMU",
             "HEPSI", "BUTUN", "KOMPLE"),
    "min": ("MIN", "MINIMUM", "MINIMAL", "LEAST", "LOWEST", "ASGARI", "ENAZ", "EN_AZ"),
    "part": ("PART", "PARTIAL", "PARTLY", "KISMI", "KISMEN", "KISIM", "PARCA", "PARCALI", "ARA", "OTHER", "DIGER"),
}
_PK_FOLD = str.maketrans("ÇĞİIÖŞÜçğıiöşü", "CGIIOSUcgiiosu")


def _pk_class(value):
    toks = [t for t in re.split(r"[^A-Z0-9]+", str(value).translate(_PK_FOLD).upper()) if t]
    toks += ["_".join(toks[i:i + 2]) for i in range(len(toks) - 1)]          # two-word names (EN_AZ)
    hits = [k for k, words in _PK_WORDS.items() if any(t in words for t in toks)]
    return hits[0] if len(hits) == 1 else None


def promise_kind(catalog):
    """-> {"field", "full", "min", "part"} for a create_promise enum field (role reason or none) whose values name
    at least two of the full / minimum / partial kinds; else None."""
    tool = (catalog.get("tools") or {}).get("create_promise") or {}
    froles = _field_roles(tool) if tool else {}
    for field, leaf in (tool.get("request") or {}).items():
        if froles.get(field) not in (None, "reason") or not leaf.get("enum"):
            continue
        got = {}
        for v in leaf["enum"]:
            k = _pk_class(v)
            if k and k not in got:
                got[k] = str(v)
        if len(got) >= 2:
            return dict(got, field=field)
    return None


def _variants(spec):
    """[spec] + the Spec as runtime.brain.dated_spec makes it on each Spec.dated `from` date."""
    import datetime
    from runtime.brain import dated_spec
    out = [spec]
    for d in spec.get("dated") or []:
        try:
            out.append(dated_spec(spec, datetime.date.fromisoformat(str(d.get("from")))))
        except (TypeError, ValueError):
            continue
    return out


def wiring(spec, catalog, flags=None):
    """-> wiring dict (C.8): listen, bye, bye_mode, end, api, nodes, roles, success, wire, identity_mode, chain,
    chainable, flags."""
    fl = merge_flags(flags)
    vs = _variants(spec)            # the Spec as it is on every effective date (Spec.dated): nodes for all of them
    pmax = max(int((v.get("products") or {}).get("max") or 1) for v in vs)
    tries = max(int((v.get("recording") or {}).get("tries") or 1) for v in vs)
    on = [(v.get("notes") or {}).get("scope") for v in vs if (v.get("notes") or {}).get("enabled")]
    api = {
        "verify": ["a_verify_%d" % i for i in range(1, _n_verify(spec) + 1)],
        "acct": ["a_acct_1", "a_acct_2"],
        "promise": [["a_promise_%d_%d" % (k, t) for t in range(1, tries + 1)] for k in range(1, pmax + 1)],
        "note": [["a_note_%d" % k] for k in range(1, pmax + 1)] if "product" in on else [],
        "note_call": ["a_note_call_1"] if "call" in on else [],
        "cb": ["a_cb_1", "a_cb_2"] if _uses_callback(spec) else [],
        "xfer": ["a_xfer_1", "a_xfer_2"] if _uses_transfer(spec) else [],
        "close_r": vocab.CLOSE_R,
        "close_n": vocab.CLOSE_N,
    }
    nodes = {}
    for n in api["verify"]:
        nodes[n] = _node_entry(n, "verify_identity", catalog, spec)
    for n in api["acct"]:
        nodes[n] = _node_entry(n, "get_account", catalog, spec)
    for row in api["promise"]:
        for n in row:
            nodes[n] = _node_entry(n, "create_promise", catalog, spec)
    for row in api["note"]:
        for n in row:
            nodes[n] = _node_entry(n, "add_note", catalog, spec)
    for n in api["note_call"]:
        nodes[n] = _node_entry(n, "add_note", catalog, spec, call_scope=True)
    for n in api["cb"]:
        nodes[n] = _node_entry(n, "schedule_callback", catalog, spec)
    for n in api["xfer"]:
        nodes[n] = _node_entry(n, "transfer_to_agent", catalog, spec)
    nodes[vocab.CLOSE_R] = _node_entry(vocab.CLOSE_R, "close_call", catalog, spec, close="r")
    nodes[vocab.CLOSE_N] = _node_entry(vocab.CLOSE_N, "close_call", catalog, spec, close="n")

    pk = promise_kind(catalog)
    if pk:
        for row in api["promise"]:
            for n in row:
                nodes[n]["body"].setdefault(pk["field"], _BODY_VAR % (n, pk["field"]))
    wire = {}
    for n, ent in nodes.items():
        tool = catalog["tools"][ent["tool"]]
        for field, var in ent["body"].items():
            if var in ("co", "cr"):
                continue
            leaf = tool["request"].get(field) or {}
            if leaf.get("type", "string") != "string" or leaf.get("wire_format") or int(leaf.get("scale") or 1) != 1:
                wire["%s.%s" % (ent["tool"], field)] = {"type": leaf.get("type", "string"),
                                                        "format": leaf.get("wire_format", ""),
                                                        "scale": int(leaf.get("scale") or 1)}
    chain = fl["write_chain"] == "on"
    chainable = []
    if chain:
        for n, ent in nodes.items():
            if ent["tool"] in ("create_promise", "add_note", "schedule_callback", "transfer_to_agent") \
                    and catalog["tools"][ent["tool"]]["success"]["kind"] != "http_ok_no_error":
                chainable.append(n)
    vchain = _vchain(catalog, fl)
    roles = {t: {"req": dict(catalog["tools"][t]["roles"]["request"]),
                 "res": dict(catalog["tools"][t]["roles"]["response"]),
                 "item": dict(catalog["tools"][t]["roles"]["item"])} for t in vocab.TOOLS}
    success = {t: copy.deepcopy(catalog["tools"][t]["success"]) for t in vocab.TOOLS}
    out = {
        "v": 1,
        "listen": dict(vocab.LISTEN_NODES),
        "bye": "" if fl["bye"] == "apinode" else vocab.BYE_NODE,
        "bye_mode": fl["bye"],
        "end": vocab.END_NODE,
        "api": api,
        "nodes": nodes,
        "roles": roles,
        "success": success,
        "wire": {k: wire[k] for k in sorted(wire)},
        "identity_mode": catalog.get("identity_mode", "selector"),
        "chain": chain,
        "chainable": sorted(chainable),
        "vchain": vchain,
        "flags": fl,
    }
    if pk:
        out["pkind"] = pk
    return out


def _vchain(catalog, fl):
    """Identity chain spellings (contract note 8): {} when off or when the identity tool does not fit."""
    tool = catalog["tools"]["verify_identity"]
    succ = tool.get("success") or {}
    res = (tool.get("roles") or {}).get("response") or {}
    if fl["vchain"] != "on" or fl["write_chain"] != "on" or succ.get("kind") != "bool_true" or not all(r in res for r in ("s", "verified", "all")):
        return {}
    t = [str(v) for v in succ.get("values") or [] if str(v).lower() == "true"]
    return {"t": t, "f": [v.replace("true", "false").replace("True", "False").replace("TRUE", "FALSE") for v in t]}


def api_nodes(wiring_):
    """All api node keys in canonical order (verify, acct, promise, note, note_call, cb, xfer, close_r, close_n)."""
    a = wiring_["api"]
    out = list(a["verify"]) + list(a["acct"])
    for row in a["promise"]:
        out += row
    for row in a["note"]:
        out += row
    out += list(a["note_call"]) + list(a["cb"]) + list(a["xfer"]) + [a["close_r"], a["close_n"]]
    return out


# ------------------------------------------------------------------------------------------------ node helpers

def _c(var, op, operand):
    return {"variable": var, "operator": op, "operand": operand}


def _and(*conds):
    return {"logic": "and", "conditions": list(conds)}


def _or(*items):
    return {"logic": "or", "conditions": list(items)}


def _tr(target, description, condition):
    return {"target_node": target, "description": description, "condition": condition}


def _always(target):
    return _tr(target, "always", dict(ALWAYS))


def _listen_node(key, stage, spec, tts=SAY_TTS, task=LISTEN_TASK):
    return {
        "name": key,
        "node_type": "conversation",
        "on_enter": {"type": "tts", "text": tts},
        "task_message": task,
        "extraction_schema": render.extraction_schema(stage, spec),
        "max_node_turns": MAX_NODE_TURNS,
        "max_turn_transition": vocab.CTL_NODE,
        "transitions": [_always(vocab.CTL_NODE)],
    }


def _open_node(spec):
    return {
        "name": vocab.LISTEN_NODES["open"],
        "node_type": "conversation",
        "on_enter": {"type": "tts", "text": render.open_line(spec)},
        "task_message": render.open_task(spec),
        "extraction_schema": render.extraction_schema("rp", spec),
        "transitions": [_always(vocab.CTL_NODE)],
    }


def ctl_node(code, wiring_):
    """The ctl code node with guarded api transitions, nx-equals listen transitions and the final always -> s_safe."""
    trs = []
    for w in api_nodes(wiring_):
        res_s = wiring_["nodes"][w]["res"].get("s", "r_%s_s" % w)
        trs.append(_tr(w, "ctl routes to " + w, _or(_and(_c("nx", "equals", w), _c(res_s, "equals", vocab.PENDING)))))
    listen = [wiring_["listen"][s] for s in LISTEN_STAGES]
    if wiring_.get("bye"):
        listen.append(wiring_["bye"])
    for node in listen:
        trs.append(_tr(node, "ctl routes to " + node, _or(_c("nx", "equals", node))))
    trs.append(_always(wiring_["listen"]["safe"]))
    return {
        "name": vocab.CTL_NODE,
        "node_type": "code",
        "passthrough": True,
        "passthrough_default_transition": wiring_["listen"]["safe"],
        "on_enter": {"type": "silent"},
        "pre_actions": [{
            "type": "function",
            "function": {
                "name": "code_exec",
                "handler": "__function__:code_exec",
                "parameters": {"type": "object", "properties": {
                    "code": {"type": "string", "default": code},
                    "timeout_ms": {"type": "number", "default": CTL_TIMEOUT_MS},
                }},
            },
        }],
        "transitions": trs,
    }


def _leaf_type(t):
    return t if t in ("string", "number", "integer", "boolean") else "string"


def max_retries(name, tool):
    """Read tools keep the catalog's max_retries; a write gets 0 unless it is idempotent by contract."""
    return IDEMPOTENT_WRITE_RETRIES.get(name, 0) if tool.get("write") else int(tool.get("max_retries") or 0)


def tool_binding(node_key, catalog, wiring_, spec, flags):
    """The pre_action api_call function for one api node (D.5)."""
    ent = wiring_["nodes"][node_key]
    tool = catalog["tools"][ent["tool"]]
    froles = _field_roles(tool)
    cust_key = (spec.get("call_variables") or {}).get("customer_key") or "customer_id"
    props = {}
    for field, leaf in tool["request"].items():
        role = froles.get(field)
        if role == "customer":
            props[field] = {"type": _leaf_type(leaf["type"]), "default": "{{" + cust_key + "}}"}
        elif field in ent["body"]:
            var = ent["body"][field]
            typ = _leaf_type(leaf["type"])
            tpl = "{{" + var + (":json" if flags.get("amount_tpl") == "json" and typ != "string" else "") + "}}"
            p = {"type": typ, "default": tpl}
            if leaf.get("enum"):
                p["enum"] = list(leaf["enum"])
            if leaf.get("description"):
                p["description"] = leaf["description"]
            props[field] = p
        elif role is None and leaf.get("required"):
            literal = leaf.get("example") or (leaf.get("enum") or [""])[0]
            props[field] = {"type": _leaf_type(leaf["type"]), "default": literal}
            _log("WARN", f"{node_key}: required field {field} has no source; baked literal {literal!r}")
    required = [f for f in tool["required"] if f in props]
    return {
        "type": "function",
        "config": {"timeoutMs": API_TIMEOUT_MS, "maxRetries": max_retries(ent["tool"], tool)},
        "function": {
            "name": ent["tool"],
            "handler": "__function__:api_call",
            "description": tool.get("summary") or ent["tool"],
            "parameters": {"type": "object", "properties": {
                "url": {"type": "string", "default": tool["url"]},
                "method": {"type": "string", "default": tool["method"]},
                "headers": {"type": "object", "properties": {
                    "Content-Type": {"type": "string", "default": "application/json"}}},
                "body": {"type": "object", "required": required, "properties": props},
            }},
        },
    }


CHAIN_GROUP = {"create_promise": 0, "add_note": 1, "transfer_to_agent": 2, "schedule_callback": 3}


def chain_targets(node_key, wiring_):
    """Chain successors of a chainable writer, in plan order (C.8: promises, notes, transfer, then s_bye).
    A promise may chain to any other promise; any writer only to writers of a later group; a callback (group 3,
    never planned together with the others) only to s_bye / the close nodes."""
    if not wiring_.get("chain") or node_key not in wiring_.get("chainable", []):
        return []
    grp = CHAIN_GROUP.get(wiring_["nodes"][node_key]["tool"], 3)
    out = []
    for n in api_nodes(wiring_):
        if n == node_key or n not in wiring_["chainable"]:
            continue
        g = CHAIN_GROUP.get(wiring_["nodes"][n]["tool"], 3)
        if grp == 3 or g == 3:
            continue
        if g > grp or (g == grp == 0) or (g == grp == 1):
            out.append(n)
    if wiring_.get("bye"):
        out.append(wiring_["bye"])
    out += [wiring_["api"]["close_r"], wiring_["api"]["close_n"]]
    return out


def vchain_transitions(node_key, wiring_):
    """Identity chain out of a verify node (contract note 8): -> account read(s), -> the ID listen node."""
    vc = wiring_.get("vchain") or {}
    if not vc.get("t") or node_key not in wiring_["api"]["verify"]:
        return []
    res = wiring_["nodes"][node_key]["res"]
    trs = []
    for acct in wiring_["api"]["acct"]:
        guard = wiring_["nodes"][acct]["res"].get("s", "r_%s_s" % acct)
        groups = [_and(_c("wn_" + node_key, "equals", acct), _c(res["s"], "equals", t),
                       _c(res["verified"], "equals", t), _c(res["all"], "equals", t), _c(guard, "equals", vocab.PENDING))
                  for t in vc["t"]]
        trs.append(_tr(acct, "chain: all verified, read the account", _or(*groups)))
    lid = wiring_["listen"]["id"]
    groups = [_and(_c("wl_" + node_key, "equals", lid), _c(res["s"], "equals", t), _c(res["verified"], "equals", t),
                   _c(res["all"], "equals", f)) for t, f in zip(vc["t"], vc["f"])]
    trs.append(_tr(lid, "chain: verified, ask the next question", _or(*groups)))
    return trs


def api_node(node_key, tool, catalog, wiring_, flags, spec=None):
    """One api_request node with its bound pre_action, response_mapping and transitions (D.3, D.5)."""
    spec = spec or {}
    ent = wiring_["nodes"][node_key]
    tdef = catalog["tools"][tool]
    is_close = node_key in (wiring_["api"]["close_r"], wiring_["api"]["close_n"])
    trs = []
    if is_close:
        trs.append(_always(wiring_["end"]))
        default = wiring_["end"]
    else:
        succ = wiring_["success"][tool]
        res_s = ent["res"].get("s", "r_%s_s" % node_key)
        for t in chain_targets(node_key, wiring_):
            groups = []
            for v in succ["values"]:
                conds = [_c("wn_" + node_key, "equals", t), _c(res_s, "equals", v)]
                if t in wiring_["nodes"]:
                    conds.append(_c(wiring_["nodes"][t]["res"].get("s", "r_%s_s" % t), "equals", vocab.PENDING))
                groups.append(_and(*conds))
            trs.append(_tr(t, "chain: %s succeeded, next %s" % (node_key, t), _or(*groups)))
        trs += vchain_transitions(node_key, wiring_)
        trs.append(_always(vocab.CTL_NODE))
        default = vocab.CTL_NODE
    on_enter = {"type": "silent"}
    if is_close and wiring_["bye_mode"] == "apinode":
        on_enter = {"type": "tts", "text": SAY_TTS}
    mapping = [{"path": tdef["response"][leaf]["path"], "variable": ent["res"][role]}
               for role, leaf in ent["res_leaf"].items()]
    return {
        "name": node_key,
        "node_type": "api_request",
        "passthrough": True,
        "passthrough_default_transition": default,
        "on_enter": on_enter,
        "pre_actions": [tool_binding(node_key, catalog, wiring_, spec, flags)],
        "response_mapping": mapping,
        "suppress_tool_results": True,
        "disable_inactivity_monitor": True,
        "transitions": trs,
    }


def _bye_node(spec, wiring_):
    if wiring_["bye_mode"] == "listen":
        n = _listen_node(wiring_["bye"], "safe", spec)
        n["disable_inactivity_monitor"] = True
        return n
    close_r, close_n = wiring_["api"]["close_r"], wiring_["api"]["close_n"]
    return {
        "name": wiring_["bye"],
        "node_type": "conversation",
        "passthrough": True,
        "passthrough_default_transition": close_n,
        "on_enter": {"type": "tts", "text": SAY_TTS},
        "task_message": SILENT_TASK,
        "disable_inactivity_monitor": True,
        "transitions": [_tr(close_r, "the close carries a reason", _or(_c("cmode", "equals", "r"))),
                        _always(close_n)],
    }


def _end_node():
    return {
        "name": vocab.END_NODE,
        "node_type": "end_call",
        "on_enter": {"type": "silent"},
        "disable_inactivity_monitor": True,
        "transitions": [],
        "terminal": {"type": "function", "function": {
            "name": END_FUNCTION,
            "handler": "__function__:end_call",
            "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "none"}}},
        }},
    }


def make_test_variables(spec):
    cv = spec.get("call_variables") or {}
    out = {}
    for d in cv.get("declared") or []:
        name = d.get("name")
        if not name:
            continue
        if name == cv.get("customer_key"):
            out[name] = "c_test"
        elif name == cv.get("now"):
            out[name] = TEST_NOW
        else:
            out[name] = "Test"
    return out


def compile_workflow(spec, catalog, flags=None, code=None):
    """-> (workflow dict, wiring dict). Deterministic; no null values anywhere.

    `code` overrides the ctl snippet (tests / dev only); default = snippet.build_ctl_code(spec, wiring)."""
    fl = merge_flags(flags)
    w = wiring(spec, catalog, fl)
    if code is None:
        code = snippet.build_ctl_code(spec, w)
    L = w["listen"]
    nodes = {L["open"]: _open_node(spec), vocab.CTL_NODE: ctl_node(code, w)}
    for st in LISTEN_STAGES:
        nodes[L[st]] = _listen_node(L[st], st, spec)
    clar = render.clarify_line(spec)
    nodes[L["safe"]] = _listen_node(L["safe"], "safe", spec, tts=clar,
                                    task=LISTEN_TASK.replace(SAY_TTS, clar))
    for n in api_nodes(w):
        nodes[n] = api_node(n, w["nodes"][n]["tool"], catalog, w, fl, spec)
    if w["bye"]:
        nodes[w["bye"]] = _bye_node(spec, w)
    nodes[vocab.END_NODE] = _end_node()
    wf = {
        "initial_node": L["open"],
        "system_prompt": render.system_prompt(spec),
        "nodes": nodes,
        "global_nodes": {},
        "test_variables": make_test_variables(spec),
    }
    _log("COMPILE", f"{len(nodes)} nodes, {sum(len(n.get('transitions') or []) for n in nodes.values())} "
         f"transitions, ctl code {len(code)} bytes", flags=",".join(f"{k}={v}" for k, v in fl.items()))
    return wf, w


def dumps(obj):
    """Byte-stable JSON text (sorted keys, fixed separators)."""
    return json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False)
