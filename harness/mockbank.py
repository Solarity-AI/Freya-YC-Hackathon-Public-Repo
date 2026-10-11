"""Local mock of the bank tool API, driven by the ToolCatalog + one case, kit ledger shape (docs/CONTRACTS.md E.2).
Owner: agent 4. Field names come from catalog roles, never hard-coded.

CONTRACT NOTE (choices where E.2 is silent; simplest reading, kept generic):
- Tools are addressed by the 7 fixed tool names (D.1); every request/response leaf name comes from the catalog
  `roles`. A role the catalog does not bind is simply left out of the response.
- Business errors: HTTP 200 + {s-leaf: false, err-leaf: "<text>"}. Unknown or missing customer -> 404, NOT logged
  (the ledger is per customer). Every other call that reaches the bank is logged in `calls` (rejected ones too).
- Injected faults are applied after the "already closed" check and before validation; a fault never records
  anything. fault_mode: "http500" (500, no body), "ok_false" (200 + service error), "empty" (200, {}),
  "timeout" (599, no body: the twin treats it like a transport failure). Fault specs: the case's `faults`
  plus the `faults` argument, each {tool, fail_first_n} or {tool, fail_calls: [1-based call numbers]},
  optional per-entry `mode`.
- verify: the wrong-answer limit is 3 (case `max_wrong`, else the constructor's max_wrong, e.g. the Spec's
  identity.max_wrong_total). Digits of the wrong length for a digits answer are rejected with s:false and not counted
  (kit OpenAPI "unreadable"). create_promise stores the amount in major units (wire value / the field's
  scale) and rejects a non-integer for an integer field. The 3rd wrong answer returns
  {s:false, left:0, verified:false}; later answers are refused as locked (not counted). A re-verify of an
  already verified field omits the `all` leaf (probed bank quirk). A hint answer is s:true, verified:false, not
  counted. Non-date expected answers compare after removing whitespace, case-insensitively (spoken digit
  words are NOT normalised: the real bank counted them wrong).
- per_field identity mode (no selector role): every request field named like an identity key is an answer.
- Numbers in responses follow JSON-from-JS rules: an integral float is returned as int (420.0 -> 420).
- add_note is not identity-gated (a call-level note may be legal on an unverified call).
"""
import copy
import datetime
import re

TOOLS = ("verify_identity", "get_account", "create_promise", "add_note", "schedule_callback",
         "transfer_to_agent", "close_call")
MAX_WRONG = 3
NOT_VERIFIED = "identity not verified"
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _jsnum(v):
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _js(obj):
    if isinstance(obj, dict):
        return {k: _js(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_js(v) for v in obj]
    return _jsnum(obj)


def _valid_iso(s):
    if not isinstance(s, str) or not _ISO_DATE.match(s):
        return False
    try:
        datetime.date.fromisoformat(s)
        return True
    except ValueError:
        return False


def _num(v):
    """Number or numeric string -> float, else None (bools are not numbers)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and re.match(r"^\s*-?\d+(\.\d+)?\s*$", v):
        return float(v)
    return None


def _norm_answer(s, keep_space=False):
    """Case-insensitive; whitespace removed, or (keep_space: the expected value has a separator, e.g. a postcode
    "LS6 2QT") collapsed to one space, so a missing separator does not match."""
    s = str(s).strip().upper()
    return re.sub(r"\s+", " ", s) if keep_space else re.sub(r"\s+", "", s)


class MockBank:
    def __init__(self, catalog, case, faults=None, fault_mode="http500", reasonless=None, max_wrong=None):
        self.catalog = catalog
        self.case = copy.deepcopy(case)
        variables = self.case.get("variables") or {}
        self.customer_id = variables.get("customer_id") or ("c_twin_" + str(self.case.get("id", "case")).lower())
        self.identity = dict(self.case.get("identity") or {})
        self.max_wrong = int(self.case.get("max_wrong") or max_wrong or MAX_WRONG)
        self.fault_mode = fault_mode
        self.faults = list(self.case.get("faults") or [])
        if isinstance(faults, dict):
            faults = [{"tool": t, "fail_first_n": n} for t, n in faults.items()]
        self.faults += list(faults or [])
        if reasonless is None:
            reasonless = catalog.get("reasonless_outcomes_hint") or []
        self.reasonless = set(reasonless)
        id_leaf = self._item_leaf("id") or "id"
        self.products = []
        for i, p in enumerate(self.case.get("products") or []):
            row = {id_leaf: p.get(id_leaf) or p.get("id") or "p%d" % (i + 1)}
            row.update({k: v for k, v in p.items() if k not in (id_leaf, "id")})
            self.products.append(row)
        self.id_leaf = id_leaf
        # ledger state
        self.verified = {k: False for k in self.identity}
        self.wrong = 0
        self.hinted = 0
        self.promises, self.notes, self.callbacks, self.transfers, self.calls = [], [], [], [], []
        self.outcome = None
        self.reason = None
        self.closed = False
        self.failures = {}
        self.tool_calls = {}

    # ---------------------------------------------------------------- catalog helpers
    def _tool(self, tool):
        return (self.catalog.get("tools") or {}).get(tool) or {}

    def _req(self, tool, role):
        return ((self._tool(tool).get("roles") or {}).get("request") or {}).get(role)

    def _res(self, tool, role):
        return ((self._tool(tool).get("roles") or {}).get("response") or {}).get(role)

    def _item_leaf(self, role):
        return ((self._tool("get_account").get("roles") or {}).get("item") or {}).get(role)

    def _hint_value(self):
        leaf = self._res("verify_identity", "hint")
        if not leaf:
            return None
        enum = ((self._tool("verify_identity").get("response") or {}).get(leaf) or {}).get("enum") or []
        return enum[0] if enum else None

    def _resp(self, tool, ok, err=None, **roles):
        out = {}
        s = self._res(tool, "s")
        if s:
            out[s] = bool(ok)
        if err is not None:
            e = self._res(tool, "err") or "error"
            out[e] = err
        for role, val in roles.items():
            leaf = self._res(tool, role)
            if leaf:
                out[leaf] = val
        return out

    def _all_ok(self):
        return bool(self.identity) and all(self.verified.get(k) for k in self.identity)

    # ---------------------------------------------------------------- faults
    def _fault_for(self, tool, nth):
        for f in self.faults:
            if f.get("tool") != tool:
                continue
            if nth <= int(f.get("fail_first_n", 0) or 0) or nth in (f.get("fail_calls") or []):
                return f.get("mode") or self.fault_mode
        return None

    # ---------------------------------------------------------------- entry point
    def call(self, tool, body):
        """-> (status_code, response body dict or None)."""
        body = dict(body or {})
        if tool not in TOOLS or tool not in (self.catalog.get("tools") or {}):
            return 404, {"error": "unknown tool"}
        cust_field = self._req(tool, "customer")
        if cust_field and body.get(cust_field) != self.customer_id:
            return 404, {"error": "unknown customer_id"}
        nth = self.tool_calls.get(tool, 0) + 1
        self.tool_calls[tool] = nth
        if self.closed:
            return self._log(tool, body, 200, self._resp(tool, False, "the call is already closed"))
        mode = self._fault_for(tool, nth)
        if mode:
            self.failures[tool] = self.failures.get(tool, 0) + 1
            if mode == "ok_false":
                return self._log(tool, body, 200, self._resp(tool, False, "the service failed"))
            if mode == "empty":
                return self._log(tool, body, 200, {})
            return self._log(tool, body, 599 if mode == "timeout" else 500, None)
        if tool in ("get_account", "create_promise") and not self._all_ok():
            return self._log(tool, body, 200, self._resp(tool, False, NOT_VERIFIED))
        err = self._generic_check(tool, body)
        if err:
            return self._log(tool, body, 200, self._resp(tool, False, err))
        status, resp = getattr(self, "_t_" + tool)(body)
        return self._log(tool, body, status, resp)

    def _log(self, tool, body, status, resp):
        self.calls.append({"n": len(self.calls) + 1, "tool": tool, "args": copy.deepcopy(body), "status": status,
                           "result": copy.deepcopy(resp) if isinstance(resp, dict) else {}})
        return status, (_js(copy.deepcopy(resp)) if resp is not None else None)

    def _generic_check(self, tool, body):
        t = self._tool(tool)
        for f in t.get("required") or []:
            if f not in body or body.get(f) in (None, ""):
                return "missing " + f
        for f, meta in (t.get("request") or {}).items():
            enum = meta.get("enum") or []
            if enum and f in body and body[f] not in enum:
                return "unknown " + f
        return None

    # ---------------------------------------------------------------- tools
    def _t_verify_identity(self, body):
        tool = "verify_identity"
        sel = self._req(tool, "selector")
        if sel:
            pairs = [(body.get(sel), body.get(self._req(tool, "answer") or "answer"))]
        else:
            pairs = [(k, body[k]) for k in self.identity if k in body]
            if not pairs:
                return 200, self._resp(tool, False, "no identity answer given")
        if self.wrong >= self.max_wrong:
            return 200, self._resp(tool, False, "identity check locked: too many wrong answers",
                                   verified=False, left=0)
        res = None
        for field, answer in pairs:
            res = self._verify_one(field, answer)
            if res[0] != "ok":
                break
        return 200, res[1]

    def _verify_one(self, field, answer):
        tool = "verify_identity"
        if field not in self.identity:
            return "err", self._resp(tool, False, "unknown field")
        expected = str(self.identity[field])
        answer = "" if answer is None else str(answer).strip()
        left = max(0, self.max_wrong - self.wrong)
        if _ISO_DATE.match(expected):
            if not _valid_iso(answer):
                return "err", self._resp(tool, False, "answer must be a date as YYYY-MM-DD", verified=False, left=left)
            if answer == expected:
                return self._verified(field)
            ey, em, ed = expected.split("-")
            ay, am, ad = answer.split("-")
            hint = self._hint_value()
            if hint and ay == ey and am == ed and ad == em:
                self.hinted += 1
                return "ok", self._resp(tool, True, verified=False, left=left, all=self._all_ok(), hint=hint)
        elif re.match(r"^\d+$", expected) and re.match(r"^\d+$", answer) and len(answer) != len(expected):
            # digits of the wrong length (a short account number, a two-digit year): rejected, not counted. Words
            # stay a counted wrong answer (probed on the real bank)
            return "err", self._resp(tool, False, "unreadable answer", verified=False, left=left)
        elif answer and _norm_answer(answer, " " in expected.strip()) == _norm_answer(expected, " " in expected.strip()):
            return self._verified(field)
        self.wrong += 1
        left = max(0, self.max_wrong - self.wrong)
        if left == 0:
            return "err", self._resp(tool, False, "too many wrong answers", verified=False, left=0,
                                     all=False)
        return "ok", self._resp(tool, True, verified=False, left=left, all=self._all_ok())

    def _verified(self, field):
        again = self.verified.get(field)
        self.verified[field] = True
        left = max(0, self.max_wrong - self.wrong)
        if again:
            return "ok", self._resp("verify_identity", True, verified=True, left=left)
        return "ok", self._resp("verify_identity", True, verified=True, left=left, all=self._all_ok())

    def _t_get_account(self, _body):
        # call() already answers NOT_VERIFIED before an unverified get_account / create_promise reaches here
        return 200, self._resp("get_account", True, products=copy.deepcopy(self.products))

    def _product(self, pid):
        for p in self.products:
            if p.get(self.id_leaf) == pid:
                return p
        return None

    def _t_create_promise(self, body):
        tool = "create_promise"
        pid = body.get(self._req(tool, "product") or "")
        prod = self._product(pid)
        if prod is None:
            return 200, self._resp(tool, False, "unknown product_id")
        afield = self._req(tool, "amount") or ""
        meta = (self._tool(tool).get("request") or {}).get(afield) or {}
        amount = _num(body.get(afield))
        if amount is None:
            return 200, self._resp(tool, False, "amount must be a number")
        if meta.get("type") == "integer" and not float(amount).is_integer():
            return 200, self._resp(tool, False, "amount must be an integer")
        amount = round(amount / float(meta.get("scale") or 1), 2)      # minor units on the wire -> major in the ledger
        date = body.get(self._req(tool, "date") or "")
        if not _valid_iso(date):
            return 200, self._resp(tool, False, "date must be YYYY-MM-DD")
        if any(p["product_id"] == pid for p in self.promises):
            return 200, self._resp(tool, False, "this product already has a promise")
        promise_id = "pr%d" % (len(self.promises) + 1)
        type_leaf = self._item_leaf("type") or "type"
        self.promises.append({"promise_id": promise_id, "product_id": pid, "type": prod.get(type_leaf),
                              "amount": amount, "date": date})
        return 200, self._resp(tool, True, pid=promise_id)

    def _t_add_note(self, body):
        tool = "add_note"
        pf = self._req(tool, "product")
        note = {}
        if pf:
            pid = body.get(pf)
            if self._product(pid) is None:
                return 200, self._resp(tool, False, "unknown product_id")
            note["product_id"] = pid
        rf = self._req(tool, "reason")
        note["reason"] = body.get(rf) if rf else None
        tf = self._req(tool, "text")
        if tf and body.get(tf):
            note["text"] = body.get(tf)
        self.notes.append(note)
        return 200, self._resp(tool, True)

    def _t_schedule_callback(self, body):
        tool = "schedule_callback"
        dtf = self._req(tool, "datetime")
        if dtf and dtf in body:
            m = re.match(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(:\d{2})?", str(body.get(dtf)))
            date, time = (m.group(1), m.group(2)) if m else ("", "")
        else:
            date = body.get(self._req(tool, "date") or "")
            time = body.get(self._req(tool, "time") or "")
        if not _valid_iso(date) or not isinstance(time, str) or not _HHMM.match(time):
            return 200, self._resp(tool, False, "date must be YYYY-MM-DD and time HH:MM")
        self.callbacks.append({"date": date, "time": time})
        return 200, self._resp(tool, True)

    def _t_transfer_to_agent(self, body):
        q = body.get(self._req("transfer_to_agent", "queue") or "")
        if not q:
            return 200, self._resp("transfer_to_agent", False, "missing queue")
        self.transfers.append({"queue": q})
        return 200, self._resp("transfer_to_agent", True)

    def _t_close_call(self, body):
        tool = "close_call"
        outcome = body.get(self._req(tool, "outcome") or "")
        rf = self._req(tool, "reason")
        reason = body.get(rf) if rf else None
        if not outcome:
            return 200, self._resp(tool, False, "missing outcome")
        if outcome not in self.reasonless and not reason:
            return 200, self._resp(tool, False, "a reason is required for outcome " + str(outcome))
        self.outcome = outcome
        self.reason = reason if reason not in ("",) else None
        if rf and rf in body and body.get(rf) == "":
            self.reason = ""                              # an empty reason leaf is still a reason leaf
        self.closed = True
        return 200, self._resp(tool, True)

    # ---------------------------------------------------------------- ledger
    def ledger(self):
        """-> {outcome, reason, promises, notes, callbacks, transfers, calls} (kit score.py shape)."""
        return copy.deepcopy({
            "case": self.case.get("id"), "now": (self.case.get("variables") or {}).get("now"),
            "verified": self.verified, "wrong": self.wrong, "hinted": self.hinted,
            "promises": self.promises, "notes": self.notes, "callbacks": self.callbacks,
            "transfers": self.transfers, "outcome": self.outcome, "reason": self.reason,
            "failures": self.failures, "calls": self.calls,
        })
