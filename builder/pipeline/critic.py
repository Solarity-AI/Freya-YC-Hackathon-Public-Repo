"""Critic: brief vs code-rendered plain-English Spec -> patches (docs/CONTRACTS.md F). Owner: agent 5.
One LLM call (+ at most one targeted re-extraction, driven by build.py). Patches are re-validated and reverted if
invalid (build.py: apply_and_check()).

Issue quotes must be verbatim spans of the brief; an issue whose quote cannot be found is dropped (a critic that
cannot cite the brief does not get to change the Spec).
"""
import copy
import json

from builder import llm, trace
from builder.pipeline import segment as seg

CRITIC_TIMEOUT_S = 420
_OUT_OF_RANGE = "index out of range: %s"

CRITIC_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["issues", "residual"],
    "properties": {
        "issues": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["quote", "problem", "pointer", "op"],
            "properties": {
                "quote": {"type": "string"}, "problem": {"type": "string"}, "pointer": {"type": "string"},
                "op": {"type": "object", "additionalProperties": False, "properties": {
                    "op": {"enum": ["add", "replace", "remove"]}, "path": {"type": "string"}, "value": {}}}}}},
        "residual": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "class"],
            "properties": {"text": {"type": "string"}, "class": {"enum": ["speech", "flow"]}}}},
    },
}


# ----------------------------------------------------------------------------------------------- English

def _dr(rule):
    """DateRule -> words."""
    if not isinstance(rule, dict):
        return "?"
    k = rule.get("kind")
    if k == "today":
        return "today"
    if k == "next_business_day":
        return "the next business day"
    if k == "nth_business_day_after_today":
        return "the business day number %s after today" % rule.get("n")
    if k == "nth_calendar_day_after_today":
        return "today + %s calendar days (roll %s)" % (rule.get("n"), rule.get("roll", "none"))
    if k == "last_business_day_of_week":
        return "the last business day of this week%s" % (
            " (next week's if today is that day)" if rule.get("if_today") == "next_week" else "")
    if k == "end_of_month":
        return "the end of the month (roll %s)" % rule.get("roll", "none")
    if k == "last_business_day_of_month":
        return "the last business day of the month"
    if k == "deadline":
        return "the deadline"
    if k == "fixed":
        return rule.get("date", "?")
    if k in ("min", "max"):
        return "the %s of (%s)" % ("earliest" if k == "min" else "latest", "; ".join(_dr(a) for a in rule.get("args") or []))
    return str(k)


def _ar(rule):
    """AmountRule -> words."""
    if not isinstance(rule, dict):
        return "?"
    k = rule.get("kind")
    if k == "full":
        return "the full past-due amount"
    if k == "floor":
        return "the floor"
    if k == "field":
        return "the product's '%s'" % rule.get("field")
    if k == "percent_of_full":
        return "%s%% of the past-due amount (rounding %s)" % (rule.get("pct"), rule.get("rounding", "half_up"))
    if k == "fixed":
        return "the fixed amount %s" % rule.get("value")
    if k in ("min", "max"):
        return "the %s of (%s)" % ("smaller" if k == "min" else "larger", "; ".join(_ar(a) for a in rule.get("args") or []))
    if k == "floor_if_too_much_else_full":
        return "the floor if the customer said the full amount is too much, else the full amount"
    return str(k)


def _sit(spec, sid):
    s = (spec.get("situations") or {}).get(sid)
    if not isinstance(s, dict):
        return "%s (UNDEFINED)" % sid
    r = s.get("reason") or "no reason"
    extra = (", queue %s" % s["queue"]) if s.get("queue") else ""
    note = (", note %s" % s["note_reason"]) if s.get("note_reason") else ""
    return "%s = close %s / %s%s%s" % (sid, s.get("outcome"), r, extra, note)


def spec_to_english(spec):
    """Deterministic plain-English rendering of the Spec rules (no LLM)."""
    s = spec or {}
    L = []
    add = L.append
    b = s.get("bank") or {}
    add("BANK: %s; the agent calls itself %r. Currency: %s." % (b.get("name"), b.get("assistant_self"),
                                                                 json.dumps(b.get("currency"))))
    cv = s.get("call_variables") or {}
    add("CALL VARIABLES: %s; customer id variable %s; current time variable %s." % (
        ", ".join(d.get("name", "?") for d in cv.get("declared") or []), cv.get("customer_key"), cv.get("now")))
    add("ADDRESS the customer as %r; own-name tokens from %s." % ((s.get("addressing") or {}).get("customer"),
                                                                  (s.get("addressing") or {}).get("name_vars")))
    op = s.get("opening") or {}
    rp = s.get("right_party") or {}
    add("OPENING (first thing said): %r then %r." % (op.get("line"), rp.get("ask")))
    bn = s.get("banned") or {}
    add("NEVER SAY before identity is verified: %s. Never offer: %s. Never ask: %s." % (
        bn.get("before_verification"), bn.get("never_offer"), bn.get("never_ask")))
    add("RIGHT PARTY: confirmed by %s (own name counts: %s), not by %s. At most %s asks in total, then %s. "
        "A bare 'No.' means %s. Answers: who=%r why=%r." % (
            rp.get("confirm_examples"), rp.get("accept_own_name"), rp.get("non_confirm_examples"), rp.get("max_asks"),
            _sit(s, rp.get("on_unresolved")), rp.get("bare_no"), (rp.get("answers") or {}).get("who"),
            (rp.get("answers") or {}).get("why")))
    tp = s.get("third_party") or {}
    cb = tp.get("callback") or {}
    dr = cb.get("date_rule") or {}
    wins = "; ".join("%s-%s (%s/%s, %s days)" % (w.get("from"), w.get("to"),
                                                  "incl" if w.get("inclusive_from") else "excl",
                                                  "incl" if w.get("inclusive_to") else "excl", w.get("days"))
                     for w in cb.get("windows") or [])
    add("THIRD PARTY: say nothing beyond the opening; ask %r. Callback days: today=%s (must be business day: %s), "
        "+%s business days, +%s calendar days; windows %s; must be later than now: %s. An outside offer gets "
        "%r + another ask, at most %s time(s), then %s. Vague answers get %r (%s free). Booked -> %r, %s. "
        "Relatives may verify: %s, may pay: %s. Max %s third-party turns." % (
            tp.get("reach_ask"), dr.get("include_today"), dr.get("today_must_be_business_day"),
            dr.get("business_days_ahead"), dr.get("calendar_days_ahead"), wins, cb.get("after_now"),
            tp.get("outside_line"), cb.get("reask_limit"), _sit(s, (tp.get("situations") or {}).get("no_callback")),
            tp.get("vague_line"), cb.get("vague_asks"), tp.get("booked_line"),
            _sit(s, (tp.get("situations") or {}).get("callback")), tp.get("relative_may_verify"),
            tp.get("relative_may_pay"), tp.get("turn_budget")))
    idn = s.get("identity") or {}
    for i, q in enumerate(idn.get("questions") or []):
        add("IDENTITY Q%d (%s): ask %r; sent to the bank as %s (%s, wire %s, length %s, numeric dates read %s); "
            "per-question wrong limit %s." % (i + 1, q.get("key"), q.get("ask"), q.get("field_value"), q.get("kind"),
                                              q.get("wire_format"), q.get("length"), q.get("numeric_order"),
                                              q.get("max_wrong") or "none"))
    for h in idn.get("hints") or []:
        add("IDENTITY HINT %s: say %r, counts as wrong: %s, at most %s time(s)." % (
            h.get("value"), h.get("say"), h.get("counts_as_wrong"), h.get("max")))
    dc = idn.get("decline") or {}
    add("IDENTITY: %s wrong answers in total fail the check -> %r, %s. Declining: explain %r (%s time), %s refusals "
        "-> %s; a purpose question counts as declining: %s." % (
            idn.get("max_wrong_total"), idn.get("fail_line"), _sit(s, idn.get("on_failed")), dc.get("explain"),
            dc.get("explain_times"), dc.get("max_declines"), _sit(s, idn.get("on_declined")),
            dc.get("purpose_question_counts")))
    pr = s.get("products") or {}
    for t, d in (pr.get("types") or {}).items():
        add("PRODUCT TYPE %s: spoken %r; floor = %s." % (t, (d or {}).get("spoken"), _ar((d or {}).get("floor"))))
    add("PRODUCTS: at most %s per customer." % pr.get("max"))
    st = s.get("statement") or {}
    add("AFTER VERIFICATION say %r then per product %r." % (st.get("intro"), st.get("item")))
    cal = s.get("calendar") or {}
    add("CALENDAR: business weekdays %s (Mon=0); holidays %s; holiday rules %s; week starts %s; "
        "'this <weekday>' = %s, 'next <weekday>' = %s; numeric dates %s." % (
            cal.get("business_weekdays"), cal.get("holidays"), cal.get("holiday_rules"), cal.get("week_start"),
            (cal.get("this_next") or {}).get("this"), (cal.get("this_next") or {}).get("next"),
            cal.get("numeric_order")))
    for bd in s.get("bands") or []:
        add("BAND %s: %s-%s days late; deadline %s; %s persuasion attempt(s)." % (
            bd.get("key"), bd.get("days_late_min"), bd.get("days_late_max"), _dr(bd.get("deadline")),
            bd.get("attempts")))
    pd = s.get("promise_date") or {}
    add("PROMISE DATE: from %s to %s; business days only: %s; weekend/holiday before the deadline -> %s; "
        "after the deadline -> %s; vague -> ask %s time(s) then %s." % (
            _dr(pd.get("earliest")), _dr(pd.get("latest")), pd.get("business_day_only"),
            pd.get("non_business_within_deadline"), pd.get("after_deadline"),
            (pd.get("vague") or {}).get("ask_exact_times"), (pd.get("vague") or {}).get("then")))
    am = s.get("amounts") or {}
    tm = am.get("too_much") or {}
    bf = am.get("below_floor") or {}
    add("AMOUNTS: first ask %s; never ask the customer for an amount: %s; accept %s .. %s. 'Too much' -> offer %s "
        "(%s time(s), date %s) and say %r. Below the floor -> %r and offer %s (%s time(s)), then flat refusal." % (
            _ar(am.get("first")), am.get("never_ask_customer"), _ar(am.get("accept_min")), _ar(am.get("accept_max")),
            _ar(tm.get("offer")), tm.get("times"), tm.get("date"), tm.get("say_rest"), bf.get("say"),
            _ar(bf.get("offer")), bf.get("times")))
    ng = s.get("negotiation") or {}
    fa = ng.get("first_ask") or {}
    add("FIRST ASK: %r (several products: %r) for %s on %s; uses an attempt: %s." % (
        fa.get("single"), fa.get("multi"), _ar(fa.get("amount")), _dr(fa.get("date")), fa.get("consumes_attempt")))
    for r in ng.get("ladder") or []:
        add("ATTEMPT %s (%s, bands %s): propose %s on %s: %r." % (
            r.get("attempt"), r.get("key"), r.get("bands"), _ar(r.get("amount")), _dr(r.get("date")), r.get("line")))
    add("NEGOTIATION: refused offers are never repeated: %s; a non-answer counts as a refusal: %s; attempts used up "
        "-> %s. Forbidden offers: %s." % (ng.get("no_repeat_refused_offer"), ng.get("non_answer_counts_as_refusal"),
                                          _sit(s, ng.get("on_exhausted")), ng.get("forbidden_offers")))
    for it in sorted(s.get("intents") or [], key=lambda x: -int((x or {}).get("precedence", 0) or 0)):
        a = it.get("action") or {}
        parts = ["INTENT %s (precedence %s, stages %s): %s -> %s" % (
            it.get("id"), it.get("precedence"), it.get("scope"), it.get("description"), a.get("kind"))]
        for k in ("say", "question"):
            if a.get(k):
                parts.append("%s %r" % (k, a[k]))
        for k in ("situation", "situation_pre_verification", "accept_situation", "decline_situation"):
            if a.get(k):
                parts.append("%s %s" % (k, _sit(s, a[k])))
        for k in ("queue", "limit", "drop_unrecorded", "suspend_persuasion"):
            if k in a:
                parts.append("%s=%s" % (k, a[k]))
        add("; ".join(parts) + ".")
    oc = s.get("outcomes") or {}
    add("CLOSING OUTCOME (first match wins): %s. Outcomes sent without a reason: %s. Unresolved products count as %s." % (
        "; ".join("%s -> %s" % (r.get("when"), r.get("use")) for r in oc.get("precedence") or []),
        oc.get("reasonless_outcomes"), oc.get("unresolved_product_situation")))
    for sid in sorted(s.get("situations") or {}):
        add("SITUATION " + _sit(s, sid) + ".")
    nt = s.get("notes") or {}
    add("NOTES: enabled %s, scope %s, when %s, skipped after a transfer: %s." % (
        nt.get("enabled"), nt.get("scope"), nt.get("when"), nt.get("skip_if_transfer")))
    mp = s.get("multi_product") or {}
    add("SEVERAL PRODUCTS: state all first %s; ask for all today first %s; attempts per product %s; one date for all "
        "-> %s (%r); hardship applies to %s; dispute/paid continues with the others %s; one read-back %s." % (
            mp.get("state_all_first"), mp.get("ask_all_today_first"), mp.get("attempts_per_product"),
            mp.get("one_date_for_all"), mp.get("clamp_line"), mp.get("hardship_applies_to"),
            mp.get("dispute_or_paid_continues"), mp.get("readback_together")))
    cf = s.get("confirmation") or {}
    add("READ-BACK: %r with items %r, then %r (exact: %s). A change is re-checked and read back again. A bare no -> %r. "
        "Change after recording -> %r." % (cf.get("readback"), cf.get("readback_item"), cf.get("question"),
                                           cf.get("verbatim_question"), cf.get("what_to_change"),
                                           cf.get("recorded_cannot_change")))
    rc = s.get("recording") or {}
    add("RECORDING: create the promise only after a clear yes; %s tries; success -> %r; all failed -> %r and %s." % (
        rc.get("tries"), rc.get("recorded"), rc.get("failed"), _sit(s, rc.get("on_all_failed"))))
    for r in s.get("required_sentences") or []:
        add("REQUIRED SENTENCE (%s, once %s): %r." % (r.get("trigger"), r.get("once"), r.get("text")))
    cl = s.get("closing") or {}
    add("GOODBYE before closing: %r; per situation %s." % (cl.get("goodbye"), cl.get("per_situation")))
    ip = s.get("interpretation") or {}
    if ip:
        add("INTERPRETATION: %s." % json.dumps(ip, sort_keys=True))
    return "\n".join(L)


# ----------------------------------------------------------------------------------------------- patches

class PatchError(Exception):
    pass


def _parts(path):
    if path == "":
        return []
    if not path.startswith("/"):
        raise PatchError("bad pointer %r" % path)
    return [p.replace("~1", "/").replace("~0", "~") for p in path.split("/")[1:]]


def _apply_one(doc, op):
    kind, path = op.get("op"), op.get("path", "")
    parts = _parts(path)
    if not parts:
        raise PatchError("cannot patch the root")
    if kind in ("add", "replace") and "value" not in op:
        raise PatchError("%s without value" % kind)
    parent = doc
    for p in parts[:-1]:
        if isinstance(parent, dict) and p in parent:
            parent = parent[p]
        elif isinstance(parent, list) and p.isdigit() and int(p) < len(parent):
            parent = parent[int(p)]
        else:
            raise PatchError("path not found: %s" % path)
    last = parts[-1]
    val = copy.deepcopy(op.get("value"))
    if isinstance(parent, dict):
        if kind == "add":
            parent[last] = val
        elif kind == "replace":
            if last not in parent:
                raise PatchError("replace of missing key: %s" % path)
            parent[last] = val
        elif kind == "remove":
            if last not in parent:
                raise PatchError("remove of missing key: %s" % path)
            del parent[last]
        else:
            raise PatchError("unsupported op %r" % kind)
    elif isinstance(parent, list):
        if last == "-" and kind == "add":
            parent.append(val)
            return
        if not last.isdigit():
            raise PatchError("bad list index in %s" % path)
        i = int(last)
        if kind == "add":
            if i > len(parent):
                raise PatchError(_OUT_OF_RANGE % path)
            parent.insert(i, val)
        elif kind == "replace":
            if i >= len(parent):
                raise PatchError(_OUT_OF_RANGE % path)
            parent[i] = val
        elif kind == "remove":
            if i >= len(parent):
                raise PatchError(_OUT_OF_RANGE % path)
            del parent[i]
        else:
            raise PatchError("unsupported op %r" % kind)
    else:
        raise PatchError("parent is not a container: %s" % path)


def apply_patches(spec, ops):
    """RFC 6902 subset (add / replace / remove) -> new spec. Never mutates the input. Raises PatchError."""
    doc = copy.deepcopy(spec)
    for op in ops or []:
        if op.get("path", "").startswith("/meta"):
            raise PatchError("meta is code-owned")
        _apply_one(doc, op)
    return doc


def usable_op(op):
    return isinstance(op, dict) and op.get("op") in ("add", "replace", "remove") and \
        str(op.get("path", "")).startswith("/") and (op.get("op") == "remove" or "value" in op)


# ----------------------------------------------------------------------------------------------- critique

def build_prompt(bdoc, spec):
    body = {k: v for k, v in spec.items() if k != "meta"}
    return ("# The brief (numbered lines; when quoting, copy only the text after \"| \")\n\n" + bdoc["numbered"]
            + "\n# The Spec in plain English (rendered by code)\n\n" + spec_to_english(spec)
            + "\n\n# The Spec JSON\n\n" + json.dumps(body, ensure_ascii=False, sort_keys=True)
            + "\n\n# Your task\n\n" + (_prompt_text()))


def _prompt_text():
    from builder.pipeline.extract import load_prompt
    return load_prompt("critic.md")


def critique(bdoc, spec, _catalog, budget):
    """-> {"issues": [{"quote", "problem", "pointer", "op"}], "residual": [{"text", "class"}]}.
    Issues whose quote is not in the brief are dropped (logged)."""
    from builder.pipeline.extract import load_prompt
    t = CRITIC_TIMEOUT_S if budget is None else budget.call_timeout(CRITIC_TIMEOUT_S)
    if t <= 0:
        trace.event("BUDGET", "critic skipped: no time")
        return {"issues": [], "residual": [], "dropped": []}
    res = llm.call_json("critic: brief vs Spec", load_prompt("system.md"), build_prompt(bdoc, spec), CRITIC_SCHEMA,
                        timeout_s=t, model=llm.choice("critic")[0], effort=llm.choice("critic")[1], budget=budget)
    hay = seg.norm_quote_text(bdoc.get("text") or "\n".join(d["text"] for d in bdoc["docs"]))
    issues, dropped = [], []
    for it in res.get("issues") or []:
        if seg.quote_in(it.get("quote", ""), hay):
            issues.append(it)
        else:
            dropped.append(it)
    trace.event("CRITIC", "issues=%d dropped_unquoted=%d residual=%d" % (
        len(issues), len(dropped), len(res.get("residual") or [])))
    for it in issues:
        trace.event("CRITIC", it.get("problem", "")[:200], pointer=it.get("pointer"),
                    op=(it.get("op") or {}).get("op", "none"))
    return {"issues": issues, "residual": list(res.get("residual") or []), "dropped": dropped}


def apply_and_check(spec, issues, check):
    """Apply usable ops one by one; keep an op only if check(spec) -> error count does not increase.
    -> (new_spec, applied_issues, rejected_issues)."""
    cur = copy.deepcopy(spec)
    base_errs = check(cur)
    applied, rejected = [], []
    for it in issues:
        op = it.get("op")
        if not usable_op(op):
            rejected.append(dict(it, why="no usable op"))
            continue
        try:
            cand = apply_patches(cur, [op])
        except PatchError as e:
            rejected.append(dict(it, why=str(e)))
            continue
        n = check(cand)
        if n <= base_errs:
            cur, base_errs = cand, n
            applied.append(it)
        else:
            rejected.append(dict(it, why="patch adds validation errors"))
    return cur, applied, rejected
