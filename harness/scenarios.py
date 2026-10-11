"""Scenario loading, running (twin + mock bank + kit score) and generic generation from a Spec
(docs/CONTRACTS.md E.3). Owner: agent 4.

CONTRACT NOTE (choices where E.3 is silent; simplest reading):
- `case` in a scenario is deep-merged over the public case named by `pub` (scenario keys win); `expect` is merged
  over the case's `expected` block key by key. Without `pub`, `case` must be complete (variables, identity,
  products, expected or `expect`).
- Turn items: {"say": text, "x": {sensor: value}, "agent_has": "substring"} — `agent_has` (optional) checks the
  agent lines spoken just before this customer turn (catches a script that drifted from the agent's flow).
  Turns left over after the call ended are ignored (reported in `notes`, not failures).
- transcript.must / must_not: [[k, text]]; k = -1 means any agent line, k >= 0 means the agent lines of
  turn k (0 = lines spoken by start(), i = lines after customer turn i). Case-insensitive substring.
- no_banned_before_verified needs the Spec (`banned.before_verification`) or a scenario `banned` list; the
  verification point is the first verify result with the `all` leaf true or the first successful account read.
- one_line_per_turn: sim start() and every processed customer turn produce exactly one agent line
  (chat: start() is exempt).
- max_hops / max_ctl_hops: node entries / ctl (code node) entries allowed in any one turn.
- Every twin error is a failure. A call that has not ended after the last turn is a failure.
- `generate` builds a synthetic case (identity values per question kind, one product of the first Spec type)
  and expected ledgers from the Spec's own situations; scenarios it cannot derive are skipped.
"""
import copy
import datetime
import json
import pathlib
import re

from builder.paths import KIT
from harness import score as hscore
from harness.mockbank import MockBank
from harness.twin import Twin

DEFAULT_MAX_HOPS = 24
DEFAULT_MAX_CTL_HOPS = 4   # ctl entries per customer turn (docs/SYSTEM-DESIGN.md "Hop bound", K = 4)


def load(path_or_dir):
    """-> list of scenario dicts (a file holds one scenario or a list)."""
    p = pathlib.Path(path_or_dir)
    files = sorted(p.glob("*.json")) if p.is_dir() else [p]
    out = []
    for f in files:
        data = json.loads(f.read_text())
        items = data if isinstance(data, list) else [data]
        for it in items:
            it = dict(it)
            it.setdefault("_file", f.name)
            out.append(it)
    return out


def _deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


_PUB = None


def public_case(case_id):
    global _PUB
    if _PUB is None:
        _PUB = {c["id"]: c for c in json.loads((KIT / "public-test-set.json").read_text())}
    if case_id not in _PUB:
        raise KeyError("unknown public case %r" % case_id)
    return copy.deepcopy(_PUB[case_id])


def case_for(scenario):
    """-> (case dict, expected dict)."""
    base = public_case(scenario["pub"]) if scenario.get("pub") else {}
    case = _deep_merge(base, scenario.get("case") or {})
    case.setdefault("id", scenario.get("id", "scenario"))
    expected = dict(case.get("expected") or {})
    expected.update(copy.deepcopy(scenario.get("expect") or {}))
    for k in ("promises", "notes", "callbacks", "transfers"):
        expected.setdefault(k, [])
    expected.setdefault("reason", None)
    case["expected"] = expected
    return case, expected


def _customer_key(spec):
    return ((spec or {}).get("call_variables") or {}).get("customer_key") or "customer_id"


def run(scenario, workflow, catalog, spec=None):
    """-> {"pass": bool, "failed": [str], "transcript": [(role, text)], "ledger": dict, "hops": [int]}."""
    case, expected = case_for(scenario)
    ckey = _customer_key(spec)
    variables = dict(case.get("variables") or {})
    variables.setdefault(ckey, "c_twin_" + re.sub(r"[^a-z0-9]+", "_", str(case["id"]).lower()))
    case["variables"] = variables
    variables.setdefault("customer_id", variables[ckey])
    reasonless = ((spec or {}).get("outcomes") or {}).get("reasonless_outcomes")
    bank = MockBank(catalog, case, faults=scenario.get("faults"), fault_mode=scenario.get("fault_mode", "http500"),
                    reasonless=reasonless,
                    max_wrong=((spec or {}).get("identity") or {}).get("max_wrong_total"))
    bank.customer_id = variables[ckey]
    opts = dict(scenario.get("twin") or {})
    tcheck = dict(scenario.get("transcript") or {})
    opts.setdefault("max_hops", max(30, int(tcheck.get("max_hops", DEFAULT_MAX_HOPS)) + 5))
    mode = scenario.get("mode", "sim")
    failed, notes = [], []
    call_vars = {k: v for k, v in variables.items() if k != "customer_id" or ckey == "customer_id"}
    try:
        twin = Twin(workflow, bank, call_vars, mode=mode, **opts)
    except Exception as e:                                    # noqa: BLE001
        return {"id": scenario.get("id"), "pass": False, "failed": ["twin setup: %s" % e], "transcript": [],
                "ledger": bank.ledger(), "hops": [], "errors": [], "notes": []}
    per_turn = [twin.start()]
    turns = scenario.get("turns") or []
    for i, t in enumerate(turns):
        if twin.ended or twin.stuck:
            notes.append("%d scripted turn(s) left after the call ended" % (len(turns) - i))
            break
        want = t.get("agent_has")
        if want and not any(want.lower() in (ln or "").lower() for ln in per_turn[-1]):
            failed.append("turn %d: agent lines %r lack %r" % (i + 1, per_turn[-1], want))
        per_turn.append(twin.turn(t.get("say", ""), t.get("x")))
    after = (((spec or {}).get("lines") or {}).get("anything_else") or "").strip().lower()
    for _ in range(2):
        # after_record = ask_anything_else: a script that ends at the read-back has nothing more to ask; answer the
        # 'anything else?' question the way a customer would (the persona does the same live)
        if twin.ended or twin.stuck or not after or not any(after in (ln or "").lower() for ln in per_turn[-1]):
            break
        notes.append("auto reply to the anything-else question")
        per_turn.append(twin.turn("No, that's all. Thank you.", {"u_act": "no", "u_topic": "none"}))
    if not twin.ended:
        failed.append("the call did not end (node %s)" % twin.node)
    failed += ["twin: " + e for e in twin.errors]
    ledger = bank.ledger()
    failed += score_ledger_failures(expected, ledger)
    failed += _transcript_checks(tcheck, per_turn, twin, mode, spec, catalog, scenario)
    return {"id": scenario.get("id"), "pass": not failed, "failed": failed, "transcript": list(twin.transcript),
            "ledger": ledger, "hops": list(twin.hops), "errors": list(twin.errors), "notes": notes,
            "paths": [list(p) for p in twin.paths], "ctl_hops": twin.ctl_hops(),
            "lines_per_turn": [len(x) for x in per_turn], "events": twin.events}


def score_ledger_failures(expected, ledger):
    return list(hscore.score_ledger({"expected": expected}, ledger)["failed"])


def _transcript_checks(tc, per_turn, twin, mode, spec, catalog, scenario):
    fails = []
    agent_all = [ln for lines in per_turn for ln in lines]
    for k, text in tc.get("must") or []:
        pool = agent_all if k == -1 else (per_turn[k] if 0 <= k < len(per_turn) else [])
        if not any(text.lower() in (ln or "").lower() for ln in pool):
            fails.append("transcript must: %r not in turn %s" % (text, k))
    for k, text in tc.get("must_not") or []:
        pool = agent_all if k == -1 else (per_turn[k] if 0 <= k < len(per_turn) else [])
        bad = [ln for ln in pool if text.lower() in (ln or "").lower()]
        if bad:
            fails.append("transcript must_not: %r in %r" % (text, bad[0][:120]))
    if tc.get("no_banned_before_verified"):
        banned = scenario.get("banned") or ((spec or {}).get("banned") or {}).get("before_verification") or []
        if not banned:
            fails.append("no_banned_before_verified needs the Spec or a scenario 'banned' list")
        for ln in hscore.lines_before_verified(twin.events, catalog):
            hits = hscore.banned_hits(ln, banned)
            if hits:
                fails.append("banned before verification %s in %r" % (hits, ln[:120]))
    if tc.get("one_line_per_turn"):
        for i, lines in enumerate(per_turn):
            if i == 0 and mode == "chat":
                continue
            if len(lines) != 1:
                fails.append("turn %d produced %d agent lines: %r" % (i, len(lines), [x[:60] for x in lines]))
    if "max_hops" in tc and twin.hops and max(twin.hops) > int(tc["max_hops"]):
        fails.append("hops %d > max_hops %d" % (max(twin.hops), int(tc["max_hops"])))
    ctl = twin.ctl_hops()
    if "max_ctl_hops" in tc and ctl and max(ctl) > int(tc["max_ctl_hops"]):
        fails.append("ctl entries %d > max_ctl_hops %d in one turn" % (max(ctl), int(tc["max_ctl_hops"])))
    return fails


def run_suite(scenarios, workflow, catalog, spec=None):
    """-> {"passed": int, "total": int, "results": [...]}."""
    results = [run(s, workflow, catalog, spec) for s in scenarios]
    return {"passed": sum(1 for r in results if r["pass"]), "total": len(results), "results": results}


# ---------------------------------------------------------------------------------------------------------------
# generic generation from a Spec (L2 smoke)

_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"]
_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _ordinal(n):
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return "%d%s" % (n, suf)


def _wire_date(d, fmt):
    out = fmt or "%Y-%m-%d"
    for k, v in (("%Y", "%04d" % d.year), ("%m", "%02d" % d.month), ("%d", "%02d" % d.day),
                 ("%y", "%02d" % (d.year % 100))):
        out = out.replace(k, v)
    return out


def _id_value(q, variant):
    """-> (wire answer, spoken answer, sensor u_ans) or None. variant 0 = the true answer, >0 = wrong ones."""
    kind, n = q.get("kind"), int(q.get("length") or 0)
    if kind == "date":
        d = datetime.date(1980 + variant, 1 + variant % 12, 15 + variant)
        spoken = "%d %s %d" % (d.day, _MONTHS[d.month - 1], d.year)
        return _wire_date(d, q.get("wire_format")), spoken, spoken
    if kind == "digits":
        n = n or 4
        digits = ("1234567890" if variant == 0 else "9876504321")[variant % 3:][:n].ljust(n, "5")
        return digits, " ".join(digits), digits
    if kind == "year":
        y = str(1980 + 7 * variant)
        return y, y, y
    if kind == "alnum":
        n = n or 6
        v = ("AB12CD34EF" if variant == 0 else "ZX98YW76VU")[:n]
        return v, " ".join(v), v
    if kind == "text":
        v = "Testvalue" if variant == 0 else "Othervalue%d" % variant
        return v, v, v
    return None


def _is_bd(cal, d):
    return d.weekday() in (cal.get("business_weekdays") or [0, 1, 2, 3, 4]) and d.isoformat() not in (cal.get("holidays") or [])


def _next_bd(cal, d):
    d = d + datetime.timedelta(days=1)
    for _ in range(400):
        if _is_bd(cal, d):
            return d
        d += datetime.timedelta(days=1)
    return None


def _nth_bd(rule, cal, today):
    d = today
    n = int(rule.get("n", 1))
    if cal.get("count_from") == "including_today" and _is_bd(cal, today):
        n -= 1
    for _ in range(n):
        d = _next_bd(cal, d)
        if d is None:                                   # no business day within reach: no date
            return None
    return d


def _eval_simple_date(rule, cal, today):
    k = (rule or {}).get("kind")
    if cal.get("holiday_rules"):
        return None                                     # needs runtime.cal; skip rather than guess
    if k == "today":
        return today
    if k == "next_business_day":
        return _next_bd(cal, today)
    if k == "nth_business_day_after_today":
        return _nth_bd(rule, cal, today)
    if k == "fixed":
        try:
            return datetime.date.fromisoformat(rule.get("date"))
        except (TypeError, ValueError):
            return None
    return None


def _eval_simple_amount(rule, prod, floor):
    k = (rule or {}).get("kind")
    full = prod["_full"]
    if k == "full":
        return full
    if k == "floor":
        return min(floor, full)
    if k == "fixed":
        return float(rule.get("value", 0))
    if k == "percent_of_full":
        return round(full * float(rule.get("pct", 100)) / 100.0, 2)
    return None


def _situation_expect(spec, sid):
    s = (spec.get("situations") or {}).get(sid) or {}
    return s.get("outcome"), (s.get("reason") or None)


def _resolve_product_outcome(spec, psit):
    oc = spec.get("outcomes") or {}
    for rule in oc.get("precedence") or []:
        when, use = rule.get("when", ""), rule.get("use", "")
        if when in ("transfer_done", "any_promise_recorded", "call_situation"):
            continue
        if when.startswith(("all_products:", "any_product:")) and when.split(":", 1)[1] != psit:
            continue
        if use.startswith("situation:"):
            return use.split(":", 1)[1]
        if use.startswith("first_product_excluding:"):
            excl = use.split(":", 1)[1].split(",")
            return psit if psit not in excl else oc.get("unresolved_product_situation")
    return psit


def _promise_situation(spec):
    for rule in (spec.get("outcomes") or {}).get("precedence") or []:
        if rule.get("when") == "any_promise_recorded" and rule.get("use", "").startswith("situation:"):
            return rule["use"].split(":", 1)[1]
    return None


def generate(spec, catalog):
    """Generic smoke scenarios built from Spec values only (happy path, identity failure, callback, refusal)."""
    cv = spec.get("call_variables") or {}
    ckey, nowkey = cv.get("customer_key") or "customer_id", cv.get("now") or "now"
    now = "2026-01-07T11:00"
    today = datetime.date(2026, 1, 7)
    names = (spec.get("addressing") or {}).get("name_vars") or []
    variables = {}
    for d in cv.get("declared") or []:
        variables[d["name"]] = "Tester"
    variables.update({ckey: "c_gen", nowkey: now})
    for i, nv in enumerate(names):
        variables[nv] = ["Alex", "Morgan", "Jordan"][i % 3]
    own = variables.get(names[0], "Alex") if names else "Alex"
    cal = dict(spec.get("calendar") or {})
    if cal.get("holiday_rules"):
        # expand the rule-based holidays with the runtime's own calendar code, then use plain dated holidays
        from runtime.cal import prepare
        cal["holidays"] = list(prepare(cal, today).get("hol") or [])
        cal["holiday_rules"] = []
    item = ((catalog.get("tools") or {}).get("get_account", {}).get("roles") or {}).get("item") or {}
    types = (spec.get("products") or {}).get("types") or {}
    bands = spec.get("bands") or []
    out = []
    if not types or not item.get("type") or not item.get("past_due"):
        return out
    tname, tdef = next(iter(types.items()))
    prod = {item["type"]: tname, item["past_due"]: 250.0}
    if item.get("days_late"):
        prod[item["days_late"]] = int(bands[0]["days_late_min"]) if bands else 5
    floor = 250.0
    fr = (tdef or {}).get("floor") or {}
    if fr.get("kind") == "field" and fr.get("field"):
        prod[fr["field"]] = 75.0
        floor = 75.0
    for leaf in re.findall(r"<f:(\w+)>", (tdef or {}).get("spoken", ""), re.A):
        prod.setdefault(leaf, "1234")
    prod["_full"] = 250.0
    questions = (spec.get("identity") or {}).get("questions") or []
    ident, id_turns, ok = {}, [], True
    for q in questions:
        v = _id_value(q, 0)
        if v is not None and q.get("kind") == "alnum" and q.get("pattern") and not re.match(q["pattern"], v[0]):
            # a code with a shape (e.g. a separator): a sample made from the Spec pattern, spoken without it
            from builder.pipeline.validate import _sample_from_pattern
            smp = _sample_from_pattern(q["pattern"])
            if smp:
                v = (smp, " ".join(re.sub(r"[^A-Za-z0-9]", "", smp)), re.sub(r"[^A-Za-z0-9]", "", smp))
        if v is None or (q.get("pattern") and not re.match(q["pattern"], v[0])):
            ok = False
            break
        ident[q["field_value"]] = v[0]
        id_turns.append({"say": v[1], "x": {"u_act": "answer", "u_ans": v[2]}})
    product = {k: v for k, v in prod.items() if k != "_full"}
    base_case = {"id": "GEN", "variables": variables, "identity": ident, "products": [product]}
    tc = {"no_banned_before_verified": True, "one_line_per_turn": True, "max_hops": DEFAULT_MAX_HOPS,
          "max_ctl_hops": DEFAULT_MAX_CTL_HOPS}
    confirm = {"say": "Yes, this is %s speaking." % own, "x": {"u_act": "yes"}}
    if ok and questions:
        # happy path
        fa = (spec.get("negotiation") or {}).get("first_ask") or {}
        amt = _eval_simple_amount(fa.get("amount"), prod, floor)
        day = _eval_simple_date(fa.get("date"), cal, today)
        psit = _promise_situation(spec)
        if amt is not None and day is not None and psit:
            o, r = _situation_expect(spec, psit)
            out.append({"id": "GEN-happy", "mode": "sim", "case": dict(base_case, id="GEN-happy"),
                        "turns": [confirm] + id_turns + [{"say": "Yes, I can pay that today.", "x": {"u_act": "yes"}},
                                                         {"say": "Yes, I confirm.", "x": {"u_act": "yes"}},
                                                         {"say": "Thank you, goodbye.", "x": {"u_act": "chatter_only"}}],
                        "expect": {"outcome": o, "reason": r,
                                   "promises": [{"product_id": "p1", "amount": amt, "date": day.isoformat()}]},
                        "transcript": tc})
        # identity failure: wrong answers on the first question until the total limit
        idn = spec.get("identity") or {}
        limit = int(idn.get("max_wrong_total") or 3)
        q0 = questions[0]
        wrong_turns = []
        for k in range(1, limit + 1):
            v = _id_value(q0, k)
            wrong_turns.append({"say": v[1], "x": {"u_act": "answer", "u_ans": v[2]}})
        if idn.get("on_failed"):
            o, r = _situation_expect(spec, idn["on_failed"])
            out.append({"id": "GEN-id-failed", "mode": "sim", "case": dict(base_case, id="GEN-id-failed"),
                        "turns": [confirm] + wrong_turns + [{"say": "Okay, goodbye.", "x": {"u_act": "chatter_only"}}],
                        "expect": {"outcome": o, "reason": r}, "transcript": tc})
        # refusal of every offer
        neg = spec.get("negotiation") or {}
        if neg.get("on_exhausted"):
            sid = _resolve_product_outcome(spec, neg["on_exhausted"])
            o, r = _situation_expect(spec, sid)
            notes = []
            nt = spec.get("notes") or {}
            if nt.get("enabled") and nt.get("scope") == "product":
                nr = ((spec.get("situations") or {}).get(neg["on_exhausted"]) or {}).get("note_reason")
                if nr:
                    notes = [{"product_id": "p1", "reason": nr}]
            n_ref = len(neg.get("ladder") or []) + 3
            out.append({"id": "GEN-refused", "mode": "sim", "case": dict(base_case, id="GEN-refused"),
                        "turns": [confirm] + id_turns + [{"say": "No.", "x": {"u_act": "no"}}] * n_ref,
                        "expect": {"outcome": o, "reason": r, "notes": notes}, "transcript": tc})
    # third party callback
    tp = spec.get("third_party") or {}
    cb = None if cal.get("holiday_rules") else _callback_slot(tp.get("callback") or {}, cal, today, 11 * 60)
    sid = (tp.get("situations") or {}).get("callback")
    if cb and sid:
        d, hhmm = cb
        o, r = _situation_expect(spec, sid)
        spoken = "Please call back on %s the %s of %s at %s." % (_WEEKDAYS[d.weekday()], _ordinal(d.day),
                                                                  _MONTHS[d.month - 1], hhmm)
        out.append({"id": "GEN-callback", "mode": "sim", "case": dict(base_case, id="GEN-callback"),
                    "turns": [{"say": "No, this is a friend. %s is not here right now." % own,
                               "x": {"u_act": "no", "u_topic": "other_person"}},
                              {"say": spoken, "x": {"u_act": "answer", "u_date": spoken, "u_time": hhmm}},
                              {"say": "Okay, goodbye.", "x": {"u_act": "chatter_only"}}],
                    "expect": {"outcome": o, "reason": r, "callbacks": [{"date": d.isoformat(), "time": hhmm}]},
                    "transcript": tc})
    return out


def _hm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _callback_slot(cb, cal, today, now_min):
    """A clearly valid (date, "HH:MM") for the Spec's callback rule, or None."""
    rule = cb.get("date_rule") or {}
    wins = cb.get("windows") or []
    if not wins:
        return None
    dates = []
    if rule.get("include_today") and (not rule.get("today_must_be_business_day") or _is_bd(cal, today)):
        dates.append(today)
    d = today
    for _ in range(int(rule.get("business_days_ahead") or 0)):
        d = _next_bd(cal, d)
        if d is None:                                   # no further business day: stop instead of _next_bd(None)
            break
        dates.append(d)
    for n in range(1, int(rule.get("calendar_days_ahead") or 0) + 1):
        dates.append(today + datetime.timedelta(days=n))
    for day in sorted(set(dates), reverse=True):        # prefer a later day: clearly after now
        for w in wins:
            if w.get("days") == "business" and not _is_bd(cal, day):
                continue
            if w.get("days") == "non_business" and _is_bd(cal, day):
                continue
            lo, hi = _hm(w["from"]), _hm(w["to"])
            t = ((lo + hi) // 2) // 60 * 60
            if not lo < t < hi:
                continue
            if day == today and t <= now_min + int(cb.get("min_lead_minutes") or 0):
                continue
            return day, "%02d:%02d" % (t // 60, t % 60)
    return None
