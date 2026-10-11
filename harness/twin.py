"""Local executor of a compiled Freya workflow, matching the E1-verified engine semantics (docs/CONTRACTS.md E.1).
Owner: agent 4.

CONTRACT NOTE (choices where E.1 / the kit docs are silent; simplest reading):
- Variables: test_variables are merged under the call variables (a call variable wins). The engine's automatic
  values (`<x>_success_count`, flattened `*_response.*` leaves, status codes) are written as strings, like
  everything else, so `equals` / `greater_than` behave as on the platform's string table.
- Extraction: every name of the node's `extraction_schema` is written each turn (default extractor: `u_text` =
  the text, all others ""); `sensors` override, restricted to schema names (others are ignored and logged as an
  event). In chat mode, turn 1 at the initial node runs no extraction and no routing ("Missing prior assistant
  message"); the reply is the «…» text of the initial node's task_message.
- Transitions with the same target are merged at their first position (OR; unconditional if one is), as the
  engine does at load time. A `matches_intent` condition records an error and counts as false.
- A non-passthrough conversation node with no matching transition: the call stays there and an error is
  recorded (on the platform the dialogue model would improvise). A passthrough node with no match falls back to
  `passthrough_default_transition`; none -> error, the call is stuck.
- api_request: body defaults are baked at every entry ("{{x}}" with x unset -> field dropped; "{{x:json}}" ->
  json-decoded value when possible; mixed text keeps unresolved placeholders literally). The URL must equal the
  bank catalog URL of the tool (else error). `config.maxRetries` re-sends on HTTP >= 500. Envelope:
  {status, data, message, status_code}; a non-2xx response has data None and leaves mappings untouched.
- Code nodes: `exec(code, {"vars": vars})`; an exception is recorded as an error plus `<node>_failure_count`
  (writes made before the exception persist); a code string containing "{{" or "}}" is an error (the platform
  would template it).
- Hops = node entries per customer turn (start() counts as turn 0). Above max_hops -> error, the call is stuck.
  `paths[i]` lists the nodes entered in turn i (same index as `hops`); `ctl_hops()` counts the code-node entries
  per turn (the costly hops: each runs the packed ctl).
- Transcript roles are "agent" / "customer" (harness.persona uses the same).
"""
import copy
import json
import re


class TwinError(Exception):
    pass


_PH = re.compile(r"\{\{\s*([A-Za-z0-9_.\-]+?)(:json)?\s*\}\}")
_EXACT_PH = re.compile(r"^\s*\{\{\s*([A-Za-z0-9_.\-]+?)(:json)?\s*\}\}\s*$")
_GUILLEMETS = re.compile(r"«(.*?)»", re.S)


def _s(v):
    """Engine-style string of a variable value (used for comparisons and substitution)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    return str(v)


def eval_condition(cond, vars):
    """Kit condition shapes (bare always, or/and groups; equals, not_equals, greater_than, less_than, contains,
    is_set, is_not_set). matches_intent -> TwinError."""
    if not isinstance(cond, dict) or not cond:
        raise TwinError("transition without a condition: %r" % (cond,))
    if "logic" in cond or "conditions" in cond:
        logic = str(cond.get("logic", "or")).lower()
        subs = cond.get("conditions") or []
        if logic not in ("or", "and"):
            raise TwinError("unknown logic %r" % logic)
        results = [eval_condition(c, vars) for c in subs]     # evaluate all: errors surface deterministically
        return any(results) if logic == "or" else (bool(results) and all(results))
    op = cond.get("operator")
    if op == "always":
        return True
    if op == "matches_intent":
        raise TwinError("matches_intent is not deterministic: %r" % cond.get("description", ""))
    name = cond.get("variable")
    present = name in vars
    val = vars.get(name)
    operand = cond.get("operand")
    if op == "is_set":
        return present
    if op == "is_not_set":
        return not present
    if op == "equals":
        return present and _s(val) == _s(operand)
    if op == "not_equals":
        return not (present and _s(val) == _s(operand))
    if op in ("greater_than", "less_than"):
        if not present:
            return False
        try:
            a, b = float(_s(val)), float(_s(operand))
        except (TypeError, ValueError):
            return False
        return a > b if op == "greater_than" else a < b
    if op == "contains":
        return present and _s(operand).lower() in _s(val).lower()
    raise TwinError("unknown operator %r" % (op,))


def substitute(text, vars, drop_if_unset=False):
    """{{var}} / {{var:json}} substitution. drop_if_unset: a value that is exactly one unset placeholder -> None."""
    if not isinstance(text, str):
        return text
    if drop_if_unset:
        m = _EXACT_PH.match(text)
        if m and m.group(1) not in vars:
            return None

    def rep(m):
        name, js = m.group(1), m.group(2)
        if name not in vars:
            return m.group(0)
        v = vars[name]
        return json.dumps(v) if js else _s(v)
    return _PH.sub(rep, text)


def unresolved(text, vars):
    """Placeholder names in text that have no value."""
    return [m.group(1) for m in _PH.finditer(text or "") if m.group(1) not in vars]


def _merge_transitions(trs):
    out, by_target = [], {}
    for t in trs or []:
        tgt = t.get("target_node")
        if tgt in by_target:
            prev = by_target[tgt]
            a, b = prev.get("condition") or {}, t.get("condition") or {}
            if a.get("operator") == "always" or b.get("operator") == "always":
                prev["condition"] = {"operator": "always"}
            else:
                prev["condition"] = {"logic": "or", "conditions": [a, b]}
            prev["_merged"] = True
            continue
        c = copy.deepcopy(t)
        by_target[tgt] = c
        out.append(c)
    return out


def _walk(obj, path):
    cur = obj
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return False, None
    return True, cur


def _flatten(prefix, obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten(prefix + "." + str(k), v, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _flatten(prefix + "." + str(i), v, out)
    else:
        out[prefix] = "null" if obj is None else _s(obj)


class Twin:
    def __init__(self, workflow, bank, call_vars, mode="sim", bool_style="lower", list_style="json",
                 flat_keys="both", max_hops=30, extractor=None):
        """mode 'sim' (initial tts spoken first) | 'chat' (customer speaks first, routing suppressed on turn 1).
        bool_style 'lower'|'title'; list_style 'json'|'pyrepr'; flat_keys 'tool'|'node'|'both'."""
        if mode not in ("sim", "chat"):
            raise TwinError("mode must be sim or chat")
        if bool_style not in ("lower", "title") or list_style not in ("json", "pyrepr") \
                or flat_keys not in ("tool", "node", "both"):
            raise TwinError("bad twin style option")
        self.wf = workflow
        self.nodes = workflow.get("nodes") or {}
        self.bank = bank
        self.mode, self.bool_style, self.list_style, self.flat_keys = mode, bool_style, list_style, flat_keys
        self.max_hops = max_hops
        self.extractor = extractor
        self.vars = {k: v for k, v in (workflow.get("test_variables") or {}).items()}
        self.vars.update(call_vars or {})
        self.events, self.transcript, self.hops, self.errors = [], [], [], []
        self.ended = False
        self.stuck = False
        self.node = None
        self.entered = set()
        self.turn_lines = []
        self._chat_first = mode == "chat"
        self._hop = 0
        self.paths, self._path = [], []
        self._trs = {k: _merge_transitions(n.get("transitions")) for k, n in self.nodes.items()}
        self._check_static()

    # ------------------------------------------------------------------ helpers
    def _err(self, msg):
        self.errors.append(msg)
        self.events.append({"event": "error", "message": msg, "node": self.node})

    def _check_static(self):
        init = self.wf.get("initial_node")
        if init not in self.nodes:
            raise TwinError("initial_node %r is not a node" % (init,))
        for k, n in self.nodes.items():
            for t in n.get("transitions") or []:
                if t.get("target_node") not in self.nodes:
                    self._err("node %s: transition target %r does not exist" % (k, t.get("target_node")))
            for t in n.get("transitions") or []:
                if "matches_intent" in json.dumps(t.get("condition") or {}):
                    self._err("node %s: matches_intent condition (model routing is not modelled)" % k)
            if any(t.get("_merged") for t in self._trs[k]):
                self.events.append({"event": "merged_transitions", "node": k})

    def _say(self, text):
        if not (text or "").strip():
            self.events.append({"event": "empty_tts", "node": self.node})
            return
        self.turn_lines.append(text)
        self.transcript.append(("agent", text))
        self.events.append({"event": "say", "node": self.node, "text": text})

    def _bool(self, b):
        if self.bool_style == "title":
            return "True" if b else "False"
        return "true" if b else "false"

    def _mapped(self, v):
        if isinstance(v, bool):
            return self._bool(v)
        if isinstance(v, (list, dict)):
            return json.dumps(v) if self.list_style == "json" else repr(v)
        if v is None:
            return "None"
        return _s(v)

    # ------------------------------------------------------------------ public API
    def start(self):
        """-> list of assistant lines spoken before the customer's first turn."""
        self.turn_lines = []
        self.node = self.wf["initial_node"]
        self._path = []
        if self.mode == "chat":
            self._end_turn()
            return []
        self._hop = 0
        self._run_from(self.node, reason="start", from_node="")
        self._end_turn()
        return list(self.turn_lines)

    def turn(self, text, sensors=None):
        """One customer turn -> list of assistant lines. sensors: extraction overrides (restricted to the node schema)."""
        self.turn_lines = []
        if self.ended:
            self._err("customer turn after the call ended")
            return []
        if self.stuck:
            self._err("customer turn while the twin is stuck")
            return []
        if self.node is None:
            self.start()
            self.turn_lines = []
        self.transcript.append(("customer", text))
        self.events.append({"event": "user", "node": self.node, "text": text})
        node = self.nodes[self.node]
        self._hop = 0
        self._path = []
        if self._chat_first:
            self._chat_first = False
            self.entered.add(self.node)
            m = _GUILLEMETS.search(node.get("task_message") or "")
            if m:
                self._say(substitute(m.group(1), self.vars))
            else:
                self._err("chat turn 1: initial node has no «…» task_message; nothing would be said reliably")
                tts = (node.get("on_enter") or {}).get("text")
                if tts:
                    self._say(substitute(tts, self.vars))
            self._end_turn()
            return list(self.turn_lines)
        self._extract(self.node, node, text, sensors)
        target = self._route(self.node, passthrough=False)
        if target is None:
            self._err("no transition matched at listen node %s" % self.node)
        else:
            self._run_from(target, reason="transition", from_node=self.node)
        self._end_turn()
        return list(self.turn_lines)

    def _end_turn(self):
        self.hops.append(self._hop)
        self.paths.append(self._path)

    def ctl_hops(self):
        """Code-node entries per turn (index-aligned with `hops`)."""
        return [sum(1 for k in p if (self.nodes.get(k) or {}).get("node_type") == "code") for p in self.paths]

    # ------------------------------------------------------------------ engine
    def _extract(self, key, node, text, sensors):
        names = [f.get("name") for f in node.get("extraction_schema") or [] if f.get("name")]
        if self.extractor is not None:
            got = self.extractor(key, node.get("extraction_schema") or [], text, dict(self.vars)) or {}
        else:
            got = {}
        vals = {}
        for n in names:
            if n in got:
                vals[n] = got[n]
            elif n == "u_text":
                vals[n] = text
            else:
                vals[n] = ""
        ignored = []
        for k, v in (sensors or {}).items():
            if k in names:
                vals[k] = v
            else:
                ignored.append(k)
        if ignored:
            self.events.append({"event": "sensors_ignored", "node": key, "names": ignored})
        for k, v in vals.items():
            self.vars[k] = "" if v is None else str(v)
        self.events.append({"event": "variable_extracted", "node": key, "values": dict(vals)})

    def _route(self, key, passthrough):
        for t in self._trs.get(key, []):
            try:
                ok = eval_condition(t.get("condition"), self.vars)
            except TwinError as e:
                self._err("node %s: %s" % (key, e))
                ok = False
            if ok:
                self.events.append({"event": "route_evaluated", "from_node": key, "target": t["target_node"]})
                return t["target_node"]
        if passthrough:
            d = self.nodes[key].get("passthrough_default_transition")
            if d:
                self.events.append({"event": "route_evaluated", "from_node": key, "target": d, "reason": "default"})
                return d
        return None

    def _run_from(self, key, reason, from_node):
        while True:                                     # every exit is a return (key is never None here)
            if key not in self.nodes:
                self._err("transition to unknown node %r" % key)
                self.stuck = True
                return
            self._hop += 1
            self._path.append(key)
            if self._hop > self.max_hops:
                self._err("hop limit %d exceeded at %s" % (self.max_hops, key))
                self.stuck = True
                self.node = key
                return
            self.node = key
            node = self.nodes[key]
            self.events.append({"event": "node_enter", "node": key, "from_node": from_node, "reason": reason})
            first = key not in self.entered
            self.entered.add(key)
            nt = node.get("node_type")
            if nt == "end_call":
                self.ended = True
                msg = node.get("spoken_message") or ""
                if msg:
                    self._say(substitute(msg, self.vars))
                return
            if nt == "code":
                self._run_code(key, node)
            elif nt == "api_request":
                self._run_api(key, node)
            elif nt == "conversation":
                self._enter_conversation(key, node, first)
            else:
                self._err("node %s: unsupported node_type %r" % (key, nt))
                self.stuck = True
                return
            passthrough = bool(node.get("passthrough")) or nt in ("code", "api_request")
            if nt in ("code", "api_request") and not node.get("passthrough"):
                self._err("node %s: %s node is not passthrough" % (key, nt))
            if not passthrough:
                return                                   # listen: wait for the customer
            nxt = self._route(key, passthrough=True)
            if nxt is None:
                self._err("passthrough node %s: no transition matched and no default (deadlock)" % key)
                self.stuck = True
                return
            from_node, reason, key = key, "transition", nxt

    def _enter_conversation(self, key, node, first):
        oe = node.get("on_enter") or {"type": "llm"}
        typ = oe.get("type")
        if node.get("on_enter_first_entry_only") and not first:
            return
        if typ == "tts":
            text = oe.get("text") or ""
            missing = unresolved(text, self.vars)
            if missing:
                self._err("node %s: unresolved %s in tts (spoken literally)" % (key, ", ".join(missing)))
            self._say(substitute(text, self.vars))
        elif typ == "silent":
            return
        else:
            self._err("node %s: on_enter %r is model-generated; the twin cannot speak it" % (key, typ))

    def _run_code(self, key, node):
        code = None
        for pa in node.get("pre_actions") or []:
            fn = pa.get("function") or {}
            if fn.get("handler") == "__function__:code_exec":
                code = (((fn.get("parameters") or {}).get("properties") or {}).get("code") or {}).get("default")
        if not isinstance(code, str):
            self._err("code node %s: no code_exec default code" % key)
            self._count(key, False)
            return
        if "{{" in code or "}}" in code:
            self._err("code node %s: code contains '{{' or '}}'" % key)
        before = dict(self.vars)
        self.events.append({"event": "function_call_start", "node": key, "function": "code_exec"})
        try:
            exec(compile(code, "<%s>" % key, "exec"), {"vars": self.vars})
            ok = True
        except Exception as e:                            # noqa: BLE001 - the platform swallows it too
            ok = False
            self._err("code node %s raised %s: %s" % (key, type(e).__name__, str(e)[:200]))
        bad = sorted(k for k, v in self.vars.items() if not isinstance(v, str)
                     and (k not in before or before[k] is not v))
        if bad:
            self._err("code node %s wrote non-string values: %s" % (key, ", ".join(bad)))
        # LIVE 2026-10-11: a code write outside an extraction variable's enum_values is "rejected by schema
        # validation" and the old value stays.
        for k, allowed in self._enums().items():
            if k in self.vars and self.vars[k] != before.get(k) and self.vars[k] not in allowed:
                self._err("code node %s wrote %r to enum variable %s (platform rejects it)" % (key, self.vars[k], k))
                if k in before:
                    self.vars[k] = before[k]
                else:
                    del self.vars[k]
        self.events.append({"event": "function_call_complete", "node": key, "function": "code_exec", "ok": ok,
                            "writes": {k: v for k, v in self.vars.items() if before.get(k, object()) != v}})
        self.vars[key + "_response.status"] = "success" if ok else "error"
        self.vars[key + "_status_code"] = "200" if ok else "500"
        self._count(key, ok)

    def _enums(self):
        if not hasattr(self, "_enum_cache"):
            out = {}
            for n in self.nodes.values():
                for x in n.get("extraction_schema") or []:
                    if isinstance(x, dict) and x.get("enum_values"):
                        out.setdefault(x.get("name"), set()).update(str(v) for v in x["enum_values"])
            self._enum_cache = out
        return self._enum_cache

    def _count(self, key, ok):
        name = key + ("_success_count" if ok else "_failure_count")
        try:
            n = int(self.vars.get(name, "0"))
        except (TypeError, ValueError):
            n = 0
        self.vars[name] = str(n + 1)

    def _run_api(self, key, node):
        calls = [pa for pa in node.get("pre_actions") or []
                 if ((pa.get("function") or {}).get("handler") == "__function__:api_call")]
        if not calls:
            self._err("api node %s: no api_call pre_action" % key)
            self._count(key, False)
            return
        if node.get("suppress_tool_results") is not True:
            self._err("api node %s: suppress_tool_results is not true" % key)
        env = {}
        for pa in calls:
            env = self._one_call(key, node, pa)          # always an envelope dict
        for m in node.get("response_mapping") or []:
            path, var = m.get("path", ""), m.get("variable")
            if not var:
                continue
            if not path.startswith("data."):
                self._err("api node %s: mapping path %r does not start with data." % (key, path))
            if env.get("data") is None:
                continue
            found, val = _walk(env, path)
            if found:
                self.vars[var] = self._mapped(val)

    def _one_call(self, key, node, pa):
        fn = pa.get("function") or {}
        tool = fn.get("name")
        props = (fn.get("parameters") or {}).get("properties") or {}
        url = substitute((props.get("url") or {}).get("default", ""), self.vars)
        method = (props.get("method") or {}).get("default", "POST")
        body = {}
        for field, spec in ((props.get("body") or {}).get("properties") or {}).items():
            if "default" not in spec:
                continue
            d = spec["default"]
            if isinstance(d, str):
                m = _EXACT_PH.match(d)
                if m:
                    if m.group(1) not in self.vars:
                        self.events.append({"event": "field_dropped", "node": key, "field": field})
                        continue
                    v = self.vars[m.group(1)]
                    if m.group(2):
                        try:
                            v = json.loads(_s(v))
                        except ValueError:
                            pass
                    else:
                        v = _s(v)
                    body[field] = v
                    continue
                miss = unresolved(d, self.vars)
                if miss:
                    self._err("api node %s: field %s sent with literal %s" % (key, field, ", ".join(miss)))
                body[field] = substitute(d, self.vars)
            else:
                body[field] = d
        cat = (getattr(self.bank, "catalog", None) or {}).get("tools", {}).get(tool)
        if cat is None:
            self._err("api node %s: tool %r is not in the bank catalog" % (key, tool))
        elif url != cat.get("url"):
            self._err("api node %s: url %r != catalog url %r" % (key, url, cat.get("url")))
        retries = int(((pa.get("config") or {}).get("maxRetries")) or 0)
        args = {"url": url, "method": method, "body": body}
        for k, v in body.items():
            self.vars["%s_args.%s" % (tool, k)] = _s(v)
        status, data = 0, None
        for attempt in range(retries + 1):
            self.events.append({"event": "function_call_start", "node": key, "function": tool, "args": args,
                                "attempt": attempt + 1})
            status, data = self.bank.call(tool, copy.deepcopy(body))
            if status < 500:
                break
        ok = 200 <= status < 300
        env = {"status": "success" if ok else "error", "data": data if ok else None,
               "message": ("Successfully executed %s request" % method) if ok
               else "Request failed with status code %d" % status, "status_code": status}
        self.events.append({"event": "function_call_complete", "node": key, "function": tool, "result": env})
        prefixes = []
        if self.flat_keys in ("tool", "both"):
            prefixes.append(tool)
        if self.flat_keys in ("node", "both"):
            prefixes.append(key)
        for p in prefixes:
            flat = {}
            if ok and data is not None:
                _flatten(p + "_response.data", data, flat)
            flat[p + "_response.status"] = env["status"]
            flat[p + "_response.message"] = env["message"]
            flat[p + "_response.status_code"] = str(status)
            flat[p + "_status_code"] = str(status)
            self.vars.update(flat)
        self._count(key, ok)
        return env


def run_script(twin, turns):
    """Convenience: start + a list of (text, sensors) or plain strings -> list of per-turn line lists."""
    out = [twin.start()]
    for t in turns:
        if twin.ended:
            break
        if isinstance(t, str):
            out.append(twin.turn(t))
        else:
            out.append(twin.turn(t[0], t[1] if len(t) > 1 else None))
    return out
