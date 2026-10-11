"""Local runner for a flow-mode workflow: executes the real packed ctl code, fires the api nodes (against a live mock
over HTTP, or a fake), and plays scripted customer turns given as typed sensors.

    python -m harness.flow_sim <workflow.json> <script.json> [--var name=value ...]

script.json: [{"u_text": "...", "u_en": "...", "u_val": "", "u_kind": "none", "u_intent": "none"}, ...]
Prints every agent line, every bank call (method, url, body, status) and the end.
"""
import json
import re
import sys
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) flow-sim"


def _fill(tpl, vars_):
    return re.sub(r"\{\{([^{}]+)\}\}", lambda m: str(vars_.get(m.group(1).split(":")[0].strip(), "")), str(tpl))


def _typed(v, typ):
    if typ in ("integer", "number"):
        try:
            return int(v) if typ == "integer" else float(v)
        except (TypeError, ValueError):
            return v
    if typ == "boolean":
        return str(v).lower() == "true"
    return v


STORE = "json"     # how mapped objects are stored: "json" text, "repr" (Python literal) or "flat" (flattened keys only)


def _flat(prefix, v, out):
    if isinstance(v, dict):
        for k, x in v.items():
            _flat(prefix + "." + str(k), x, out)
    elif isinstance(v, list):
        for i, x in enumerate(v):
            _flat(prefix + "." + str(i), x, out)
    else:
        out[prefix] = str(v).lower() if isinstance(v, bool) else ("" if v is None else str(v))


def _body(props, vars_):
    """Fill a (possibly nested) body schema's defaults like the engine does."""
    out = {}
    for f, p in props.items():
        if p.get("type") == "object" and "properties" in p:
            out[f] = _body(p["properties"], vars_)
        else:
            out[f] = _typed(_fill(p.get("default", ""), vars_), p.get("type"))
    return out


def http_fire(method, url, body, headers=None, timeout=15):
    data = json.dumps(body).encode() if body is not None and method in ("POST", "PUT", "PATCH") else None
    h = {"User-Agent": UA, "Content-Type": "application/json"}
    h.update({k: v for k, v in (headers or {}).items() if v})
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw or "null")
        except ValueError:
            return e.code, raw


def fire_node(node, vars_, fire=http_fire, log=print):
    fn = node["pre_actions"][0]["function"]
    props = fn["parameters"]["properties"]
    url = _fill(props["url"]["default"], vars_)
    method = props["method"]["default"]
    headers = {k: _fill(v.get("default", ""), vars_) for k, v in props["headers"]["properties"].items()}
    body = None
    if "body" in props:
        body = _body(props["body"]["properties"], vars_)
    status, data = fire(method, url, body, headers)
    log("  BANK %s %s %s -> %s %s" % (method, url, json.dumps(body, ensure_ascii=False) if body else "",
                                      status, json.dumps(data, ensure_ascii=False)[:400]))
    if STORE != "json":
        # the engine flattens every result into <tool>_response.data.<path> by itself (strings, booleans lower case)
        _flat(fn["name"] + "_response.data", data, vars_)
    for m in node.get("response_mapping") or []:
        f = m["path"][5:] if m["path"].startswith("data.") else m["path"]
        if isinstance(data, dict) and f in data:
            v = data[f]
            if STORE == "flat" and isinstance(v, (list, dict)):
                continue                                # a mapped object left unset: only the flattened keys
            vars_[m["variable"]] = (repr(v) if STORE == "repr" else json.dumps(v)) if isinstance(v, (list, dict)) \
                else (str(v).lower() if isinstance(v, bool) else v)
    vars_[fn["name"] + "_status_code"] = status


def run(workflow, turns, call_vars, fire=http_fire, log=print, max_steps=200):
    nodes = workflow["nodes"]
    code = nodes["ctl"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
    vars_ = dict(call_vars)
    said, calls = [], []
    turns = list(turns)
    cur = workflow["initial_node"]
    log("AGENT: " + nodes[cur]["on_enter"].get("text", ""))
    for _ in range(max_steps):
        if cur in ("s_flow", "s_safe", "s_open"):
            if not turns:
                return dict(said=said, calls=calls, end="no more customer turns", vars=vars_)
            t = turns.pop(0)
            for k in ("u_text", "u_en", "u_val", "u_kind", "u_intent"):
                vars_[k] = t.get(k, "none" if k in ("u_kind", "u_intent") else "")
            log("CUSTOMER: %s  %s" % (t.get("u_text", ""), {k: v for k, v in t.items() if k != "u_text"}))
            cur = "ctl"
        if cur == "ctl":
            g = {"vars": vars_}
            exec(code, g)
            if vars_.get("dbg_err"):
                log("  DBG_ERR " + str(vars_.get("dbg_err")))
            cur = vars_.get("nx")
            if cur not in nodes:
                cur = "s_safe"
            if cur in ("s_flow", "s_bye"):
                said.append(vars_.get("say", ""))
                log("AGENT: " + vars_.get("say", ""))
            if cur == "s_bye":
                return dict(said=said, calls=calls, end="bye", vars=vars_)
            continue
        nd = nodes.get(cur) or {}
        if nd.get("node_type") == "api_request":
            calls.append(cur)
            fire_node(nd, vars_, fire=fire, log=log)
            cur = "ctl"
            continue
        return dict(said=said, calls=calls, end="stopped at " + str(cur), vars=vars_)
    return dict(said=said, calls=calls, end="step cap", vars=vars_)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    wf = json.load(open(argv[0]))
    turns = json.load(open(argv[1]))
    cv = dict(wf.get("test_variables") or {})
    for a in argv[2:]:
        if a.startswith("--var"):
            continue
        if "=" in a:
            k, v = a.split("=", 1)
            cv[k] = v
    res = run(wf, turns, cv)
    print("END:", res["end"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
