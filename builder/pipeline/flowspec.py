"""Flow mode extraction: case documents + the bank's operations -> a flow-mode Spec (runtime/flow.py), in ONE
structured model call, checked by code and repaired by builder.llm when the check finds errors. Generic."""
import json
import pathlib
import re

PROMPT_PATH = pathlib.Path(__file__).resolve().parent.parent / "prompts" / "flow.md"
MAX_DOC_CHARS = 260_000
NODE_TYPES = ("call", "branch", "say", "ask", "select", "set", "end")
_OBJ = {"type": "object", "additionalProperties": True}

SCHEMA = {
    "type": "object",
    "required": ["bank", "call_variables", "opening", "lines", "flow", "decisions"],
    "properties": {
        "bank": {"type": "object", "required": ["name", "language"], "properties": {
            "name": {"type": "string"}, "language": {"type": "string"}, "assistant_self": {"type": "string"}}},
        "call_variables": {"type": "object", "required": ["declared", "now"], "properties": {
            "declared": {"type": "array", "items": {"type": "object", "required": ["name"], "properties": {
                "name": {"type": "string"}, "meaning": {"type": "string"}, "example": {"type": "string"}}}},
            "now": {"type": "string"}}},
        "opening": {"type": "object", "required": ["line"], "properties": {"line": {"type": "string"}}},
        "lines": {"type": "object", "required": ["clarify", "goodbye"], "properties": {
            "clarify": {"type": "string"}, "goodbye": {"type": "string"}, "hold": {"type": "string"}}},
        "flow": {"type": "object", "required": ["start", "nodes", "global", "on_error", "on_unclear"], "properties": {
            "start": {"type": "string"},
            "nodes": {"type": "array", "items": {"type": "object", "required": ["id", "type"],
                                                 "additionalProperties": True, "properties": {
                                                     "id": {"type": "string"},
                                                     "type": {"type": "string", "enum": list(NODE_TYPES)}}}},
            "global": {"type": "array", "items": _OBJ},
            "on_error": {"type": "string"}, "on_unclear": {"type": "string"},
            "max_reasks": {"type": "integer"}, "currency": {"type": "string"}, "amount_unit": {"type": "string"},
            "currency_words": _OBJ}},
        "decisions": {"type": "array", "items": {"type": "string"}},
        "sources": {"type": "array", "items": _OBJ},
    },
}

_PH = re.compile(r"<([^<>]+)>")


def ops_text(ops):
    """The operation list shown to the model: key, method, path, parameters, body fields, response fields."""
    out = []
    for k, op in sorted(ops.items()):
        ps = ", ".join("%s (%s%s)" % (n, p["in"], ", required" if p.get("required") else "")
                       for n, p in sorted(op["params"].items()))
        bs = ", ".join("%s%s%s" % (f, " (required)" if f in op["required"] else "",
                                   (" enum " + "/".join(map(str, leaf["enum"]))) if leaf.get("enum") else "")
                       for f, leaf in sorted(op["body"].items()))
        out.append("- %s: %s %s%s%s%s%s" % (k, op["method"], op["path"], (" | params: " + ps) if ps else "",
                                            (" | body: " + bs) if bs else "",
                                            (" | response fields: " + ", ".join(op["res"])) if op["res"] else "",
                                            (" | " + op["summary"]) if op.get("summary") else ""))
    return "\n".join(out)


def docs_text(docs):
    parts = []
    for d in docs:
        t = (d.get("text") or "").strip()
        if t:
            parts.append("=== %s ===\n%s" % (d.get("rel") or d.get("name") or "document", t))
    return "\n\n".join(parts)[:MAX_DOC_CHARS]


def to_spec(obj):
    """Model output -> flow-mode Spec (nodes list -> {id: node})."""
    spec = json.loads(json.dumps(obj))
    fl = spec.get("flow") or {}
    nodes = {}
    for nd in fl.get("nodes") or []:
        if isinstance(nd, dict) and nd.get("id"):
            nid = str(nd.pop("id"))
            nodes[nid] = nd
    fl["nodes"] = nodes
    spec["flow"] = fl
    spec["mode"] = "flow"
    spec["meta"] = {"decisions": spec.pop("decisions", []), "sources": spec.pop("sources", [])}
    return spec


def _saved_names(F):
    names = set()
    for nd in (F.get("nodes") or {}).values():
        if not isinstance(nd, dict):
            continue
        if nd.get("type") in ("call", "select") and nd.get("save"):
            names.add(str(nd["save"]))
        if nd.get("type") == "call" and not nd.get("save"):
            names.add(str(nd.get("op")))
        if nd.get("type") == "set" and nd.get("name"):
            names.add(str(nd["name"]))
    return names


def _paths_in(x):
    """Every $path operand and template path in a node (recursively)."""
    out = []
    if isinstance(x, str):
        if x.startswith("$"):
            out.append(x[1:])
        for m in _PH.finditer(x):
            body = m.group(1).split("|")[0].strip()
            if body != "options":
                out.append(body)
            arg = m.group(1).split("|")[1].split(":", 1)[1] if "|" in m.group(1) and ":" in m.group(1).split(
                "|")[1] else ""
            if arg.startswith("$"):
                out.append(arg[1:])
    elif isinstance(x, dict):
        for k, v in x.items():
            if k not in ("id", "type", "next", "else", "on_none", "on_fail", "on_error", "op", "save", "name",
                         "keywords", "desc", "on_status", "field"):
                out += _paths_in(v)
    elif isinstance(x, list):
        for v in x:
            out += _paths_in(v)
    return out


def check(spec, ops):
    """-> list of hard errors (empty = usable)."""
    from builder.compiler import flowgraph
    errs = []
    F = spec.get("flow") or {}
    nodes = F.get("nodes") or {}
    if not nodes:
        return ["flow.nodes is empty"]
    declared = {str(d.get("name")) for d in (spec.get("call_variables") or {}).get("declared") or []}
    names = _saved_names(F) | {"call", "now", "today", "it"}
    for nid, nd in nodes.items():
        if not isinstance(nd, dict):
            continue
        if nd.get("type") == "call":
            op = ops.get(str(nd.get("op")))
            if not op:
                errs.append("node %s: operation %r is not in the operation list" % (nid, nd.get("op")))
            else:
                fields = set(op["body"]) | set(op["params"])
                for a in (nd.get("args") or {}):
                    if a not in fields:
                        errs.append("node %s: %s has no parameter %r (has: %s)" % (nid, op["key"], a,
                                                                                     ", ".join(sorted(fields))))
                need = [f for f in op["required"] if f not in (nd.get("args") or {})]
                need += [n for n, p in op["params"].items() if p.get("required") and n not in (nd.get("args") or {})]
                for f in need:
                    errs.append("node %s: required parameter %r of %s is not given in args" % (nid, f, op["key"]))
        for p in _paths_in(nd):
            head = p.split(".")[0]
            if head not in names:
                errs.append("node %s: path %r reads %r, which no call/select/set saves" % (nid, p, head))
            if head == "call" and p.count(".") >= 1 and p.split(".")[1] not in declared:
                errs.append("node %s: %r is not a declared call variable" % (nid, p))
        if nd.get("type") == "select" and "<options>" not in str(nd.get("ask") or ""):
            errs.append("node %s: select.ask must name the items with <options>" % nid)
    for g in F.get("global") or []:
        if not g.get("id") or not (g.get("next") or g.get("say")):
            errs.append("global intent %r needs an id and a next or a say" % g.get("id"))
    try:
        wf, w = flowgraph.compile_flow(spec, ops, code="pass")
        errs += flowgraph.check(wf, w, spec)
    except Exception as e:                                  # noqa: BLE001
        errs.append("compile: %s" % e)
    errs += _reachability(F)
    return errs


def _reachability(F):
    nodes = F.get("nodes") or {}
    seen, todo = set(), [F.get("start")] + [g.get("next") for g in F.get("global") or [] if g.get("next")] + [
        F.get("on_error"), F.get("on_unclear")]
    while todo:
        n = todo.pop()
        if n in seen or n not in nodes:
            continue
        seen.add(n)
        nd = nodes[n] if isinstance(nodes[n], dict) else {}
        for k in ("next", "else", "on_none", "on_fail", "on_error"):
            if nd.get(k):
                todo.append(nd[k])
        todo += [c.get("next") for c in nd.get("cases") or [] if isinstance(c, dict)]
        todo += [c.get("next") for c in nd.get("choices") or [] if isinstance(c, dict)]
        todo += list((nd.get("on_status") or {}).values())
    return ["node %s is never reached" % n for n in sorted(set(nodes) - seen)]


def extract(docs, ops, *, budget=None, timeout_s=900):
    """-> (spec, warnings). One structured call; check() errors drive the llm repair loop."""
    from builder import llm
    system = PROMPT_PATH.read_text()
    prompt = ("# Operations (the bank's services; the tools call them exactly like this)\n\n" + ops_text(ops) +
              "\n\n# Documents\n\n" + docs_text(docs))
    model, effort = llm.choice("flow")

    def validate(obj):
        return check(to_spec(obj), ops)[:40]

    out = llm.call_json("flow", system, prompt, SCHEMA, timeout_s=timeout_s, effort=effort, model=model,
                        budget=budget, validate=validate)
    spec = to_spec(out)
    return spec, check(spec, ops)
