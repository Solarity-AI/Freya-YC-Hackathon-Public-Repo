"""Rehearsal fix round (2026-10-11): regression tests for the bugs the four hidden-brief rehearsal fixtures
(testbed/raw-a, raw-ab, mut-c, mut-d) exposed. Every Spec value here is synthetic or from the golden A/A+B Specs;
fixture values stay in testbed/."""
import copy
import datetime
import json

import pytest

from builder.compiler import graph
from builder.pipeline import extract, validate as V
from harness import scenarios
from harness.mockbank import MockBank
from runtime import brain, bundle, parse
from runtime.cal import eval_date_rule, prepare
from runtime.ident import id_answer
from test_brain import CATALOG, P05_ID, P07_ID, SPEC_A, SPEC_AB, exp, run_a

TODAY = datetime.date(2026, 10, 14)
ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
P01_ID = ["Yes, speaking.", "14 March 1988", "4471"]
P11_ID = ["Yes.", "3 June 1987", "2288"]
P12_ID = ["Yes.", "19 October 1983", "4410"]


def _sp(base=SPEC_A, **interp):
    sp = copy.deepcopy(base)
    sp["interpretation"].update(interp)
    return sp


def _intent(sp, iid):
    return [it for it in sp["intents"] if it["id"] == iid][0]


def _validate(spec, brief_text=None):
    return V.validate(spec, CATALOG, brief_text=brief_text)


# ======================================================================= dated rules (CRITICAL raw-a / mut-d)
def test_dated_spec_applies_entries_in_force_on_the_call_date_only():
    sp = {"bands": [{"deadline": {"n": 12}}], "calendar": {"holidays": ["2026-12-25"]},
          "dated": [{"from": "2026-11-16", "path": "/bands/0/deadline/n", "value": 10},
                    {"from": "2026-12-01", "until": "2026-12-10", "path": "/calendar/holidays",
                     "value": ["2026-12-25", "2026-12-07"]},
                    {"from": "2026-12-05", "path": "/bands/0/deadline/n", "value": 9},
                    {"from": "2026-11-01", "path": "/nope/0/x", "value": 1}]}
    keep = copy.deepcopy(sp)
    assert brain.dated_spec(sp, datetime.date(2026, 11, 15))["bands"][0]["deadline"]["n"] == 12
    assert brain.dated_spec(sp, datetime.date(2026, 11, 16))["bands"][0]["deadline"]["n"] == 10
    on = brain.dated_spec(sp, datetime.date(2026, 12, 6))
    assert on["bands"][0]["deadline"]["n"] == 9 and "2026-12-07" in on["calendar"]["holidays"]
    assert brain.dated_spec(sp, datetime.date(2026, 12, 10))["calendar"]["holidays"] == ["2026-12-25"]  # until: out
    assert sp == keep                                              # the Spec itself is never changed
    plain = {"bands": []}
    assert brain.dated_spec(plain, TODAY) is plain


@pytest.mark.parametrize("start,n", [(TODAY, 5), (TODAY + datetime.timedelta(days=1), 7)])
def test_dated_band_deadline_changes_the_offered_latest_date(start, n):
    sp = copy.deepcopy(SPEC_A)
    sp["dated"] = [{"from": start.isoformat(), "path": "/bands/1/deadline/n", "value": 5}]
    want = eval_date_rule(prepare(sp["calendar"], TODAY), {"kind": "nth_business_day_after_today", "n": n}, TODAY, {})
    d = run_a(["Yes, speaking.", "30 January 1984", "2219",
               {"t": "My salary arrives on the 6th of November, I can pay then.", "u_date": "the 6th of November"},
               "Yes, that works.", "Yes."], cid="PUB-04", spec=sp)
    assert [(p["amount"], p["date"]) for p in d.ledger()["promises"]] == [(1250.0, want.isoformat())], d.lines


def test_dated_floor_rule_switches_on_the_effective_date():
    # a card floor that becomes max(minimum, 50% of full) from a date: before it the minimum is accepted
    sp = copy.deepcopy(SPEC_AB)
    new = {"kind": "max", "args": [sp["products"]["types"]["credit_card"]["floor"],
                                   {"kind": "percent_of_full", "pct": 50, "rounding": "half_up"}]}
    for start, ok in ((TODAY + datetime.timedelta(days=1), True), (TODAY, False)):
        sp["dated"] = [{"from": start.isoformat(), "path": "/products/types/credit_card/floor", "value": new}]
        r = V.validate(sp, CATALOG)
        assert not r["errors"], r["errors"]
        d = run_a(P11_ID + ["No, I cannot pay today.", "I can pay 80 this Friday."], cid="PUB-11", spec=sp)
        assert ("below 110" not in d.lines[-1]) is ok, (start, d.lines[-1])


def test_validate_rejects_dated_entries_it_cannot_apply():
    sp = copy.deepcopy(SPEC_A)
    sp["dated"] = [{"from": "2026-11-16", "path": "/identity/max_wrong_total", "value": 2},
                   {"from": "2026-11-16", "path": "/bands/7/deadline/n", "value": 2},
                   {"from": "2026-11-16", "until": "2026-11-01", "path": "/bands/0/deadline/n", "value": 2}]
    errs = _validate(sp)["errors"]
    assert any("compiled into the graph" in e for e in errs)
    assert any("does not resolve" in e for e in errs)
    assert any("ends" in e and "before it starts" in e for e in errs)
    sp["dated"] = [{"from": "2026-11-16", "path": "/bands/0/deadline/n", "value": "ten"}]
    errs = _validate(sp)["errors"]
    assert any("as dated from 2026-11-16" in e for e in errs), errs
    sp["dated"] = [{"from": "2026-11-16", "path": "/bands/0/deadline/n", "value": 10}]
    assert _validate(sp)["errors"] == []
    assert V.facets_with_errors(["/bands/0/deadline/n: schema (as dated from 2026-11-16): x"]) == ["F3"]


def test_residual_rule_with_an_effective_date_and_no_dated_entry_warns():
    sp = copy.deepcopy(SPEC_A)
    sp["meta"]["residual_rules"] = [{"text": "The deadline changes to the tenth business day from 2026-11-16.",
                                     "class": "flow"}]
    assert any("not applied by the runtime" in w for w in _validate(sp)["warnings"])
    sp["dated"] = [{"from": "2026-11-16", "path": "/bands/0/deadline/n", "value": 10}]
    assert not any("not applied by the runtime" in w for w in _validate(sp)["warnings"])


def test_extract_merges_a_facets_dated_entries():
    meta = {"warnings": []}
    spec = {"dated": [{"from": "2026-01-01", "path": "/bands/0/attempts", "value": 1},
                      {"from": "2026-01-01", "path": "/third_party/turn_budget", "value": 3}]}
    entries = [{"from": "2026-11-16", "until": "", "pointer": "bands/0/deadline/n", "value_json": "10",
                "quote": "from 16 November"},
               {"from": "2026-11-16", "until": "2026-12-01", "pointer": "/calendar/holidays",
                "value_json": "[\"2026-11-27\"]", "quote": "not in the brief"},
               {"from": "2026-11-16", "until": "", "pointer": "/identity/max_wrong_total", "value_json": "2",
                "quote": ""}]
    extract.merge_dated(spec, "F3", extract.FACETS["F3"], entries, "from 16 november", meta)
    paths = [(d["path"], d["value"], d.get("until")) for d in spec["dated"]]
    assert ("/third_party/turn_budget", 3, None) in paths                  # another facet's entry is kept
    assert ("/bands/0/deadline/n", 10, None) in paths and ("/calendar/holidays", ["2026-11-27"], "2026-12-01") in paths
    assert not any(p[0] == "/bands/0/attempts" for p in paths)              # this facet's old entry is replaced
    assert not any(p[0].startswith("/identity") for p in paths)
    assert any("outside the facet" in w for w in meta["warnings"])
    assert any("unverified quote" in w for w in meta["warnings"])
    extract.merge_dated(spec, "F1", extract.FACETS["F1"], [], "", meta)
    extract.merge_dated(spec, "F3", extract.FACETS["F3"], [], "", meta)
    assert "dated" not in spec
    assert "dated" in extract.output_schema("F3")["properties"]


# ======================================================================= identity (CRITICAL mut-c, MAJOR mut-d)
POSTCODE = {"key": "postcode", "field_value": "postcode", "kind": "alnum", "numeric_order": "DMY", "wire_format": "upper",
            "length": 0, "pattern": "^[A-Z]{1,2}[0-9][A-Z0-9]? [0-9][A-Z]{2}$"}


@pytest.mark.parametrize("text,wire", [("L S six, two Q T", "LS6 2QT"), ("Sierra Whiskey one Alpha, one Alpha Alpha", "SW1A 1AA"),
                                       ("M fourteen, five B G", "M14 5BG"), ("LS62QT", "LS6 2QT"), ("LS6 2QT", "LS6 2QT")])
def test_alnum_answer_gets_the_separator_its_pattern_needs(text, wire):
    for fmt in ("upper", "upper_nospace"):
        assert id_answer(dict(POSTCODE, wire_format=fmt), text, "", TODAY) == {"status": "complete", "wire": wire}


def test_partial_or_patternless_alnum_answers_are_unchanged():
    assert id_answer(POSTCODE, "L S six", "", TODAY)["status"] == "invalid"
    assert id_answer(dict(POSTCODE, pattern=""), "L S six, two Q T", "", TODAY) == {"status": "complete", "wire": "LS62QT"}
    dash = dict(POSTCODE, pattern="^[0-9]{3}-[0-9]{3}$")
    assert id_answer(dash, "one two three four five six", "", TODAY) == {"status": "complete", "wire": "123-456"}


@pytest.mark.parametrize("text", ["eighty-eight", "88", "90", "ninety", "I was born in 88"])
def test_two_digit_year_is_never_sent(text):
    q = {"key": "year", "kind": "year", "wire_format": "%Y", "length": 4, "pattern": ""}
    assert id_answer(q, text, "", TODAY)["status"] == "invalid"
    if text != "ninety":
        assert id_answer(dict(q, two_digit_year="pivot"), text, "", TODAY)["status"] == "complete"


@pytest.mark.parametrize("text,y", [("nineteen eighty-eight", "1988"), ("1988", "1988"), ("one nine eight eight", "1988"),
                                    ("Nineteen ninety.", "1990"), ("twenty oh five", "2005")])
def test_full_year_still_completes(text, y):
    q = {"key": "year", "kind": "year", "wire_format": "%Y", "length": 4, "pattern": ""}
    assert id_answer(q, text, "", TODAY) == {"status": "complete", "wire": y}
    assert id_answer(q, "hello", "", TODAY)["status"] == "none"


def test_validate_repairs_an_identity_question_that_can_never_complete():
    sp = copy.deepcopy(SPEC_A)
    sp["identity"]["questions"][1] = dict(sp["identity"]["questions"][1], **dict(POSTCODE, length=7))
    r = _validate(sp)
    q = r["spec"]["identity"]["questions"][1]
    assert q["length"] == 0 and any("length" in f for f in r["fixes"])
    sp["identity"]["questions"][1]["pattern"] = "^[a-z]{3}$"        # upper-case wire can never match
    sp["identity"]["questions"][1]["length"] = 0
    assert any("never completes" in w for w in _validate(sp)["warnings"])
    assert V._sample_from_pattern("^[A-Z]{1,2}[0-9][A-Z0-9]? [0-9][A-Z]{2}$") == "A0 0AA"
    assert V._sample_from_pattern(r"^\d{3}-\d+$") == "000-0"
    for bad in ("^(a|b)$", "^[A-Z", "^a{x}$", "^[^a]$", "^a{2$"):
        assert V._sample_from_pattern(bad) is None


def test_mockbank_keeps_the_separator_significant_and_scales_minor_units():
    cat = copy.deepcopy(CATALOG)
    cat["tools"]["create_promise"]["request"]["amount"].update(type="integer", scale=100)
    case = {"id": "x", "identity": {"date_of_birth": "1988-03-14", "phone_last4": "AB1 2CD"},
            "products": [{"type": "credit_card", "past_due": 420.0, "days_late": 6}]}
    b = MockBank(cat, case, max_wrong=2)
    cid = b.customer_id
    v = lambda a: b.call("verify_identity", {"customer_id": cid, "field": "phone_last4", "answer": a})[1]
    assert v("AB12CD")["verified"] is False and v("ab1 2cd")["verified"] is True
    b.call("verify_identity", {"customer_id": cid, "field": "date_of_birth", "answer": "1988-03-14"})
    assert b.call("create_promise", {"customer_id": cid, "product_id": "p1", "amount": "30865.5",
                                     "date": "2026-10-14"})[1]["ok"] is False
    assert b.call("create_promise", {"customer_id": cid, "product_id": "p1", "amount": "30865",
                                     "date": "2026-10-14"})[1]["ok"] is True
    assert b.ledger()["promises"][0]["amount"] == 308.65
    b2 = MockBank(cat, case, max_wrong=2)
    for _ in range(2):
        b2.call("verify_identity", {"customer_id": b2.customer_id, "field": "date_of_birth", "answer": "1990-01-01"})
    assert b2.ledger()["wrong"] == 2 and b2.wrong >= b2.max_wrong


def test_mockbank_digits_of_the_wrong_length_are_not_counted():
    b = MockBank(CATALOG, {"id": "x", "identity": {"date_of_birth": "1988-03-14", "phone_last4": "4471"},
                           "products": []})
    r = b.call("verify_identity", {"customer_id": b.customer_id, "field": "phone_last4", "answer": "447"})[1]
    assert r["ok"] is False and b.ledger()["wrong"] == 0
    r = b.call("verify_identity", {"customer_id": b.customer_id, "field": "phone_last4", "answer": "4472"})[1]
    assert b.ledger()["wrong"] == 1


# ======================================================================= parse (MAJOR raw-a)
@pytest.mark.parametrize("text", ["Can't you just give me a discount?", "Couldn't you waive the fee?", "Won't you reduce it?",
                                  "Why can't you lower it?"])
def test_negative_form_question_is_not_a_refusal(text):
    r = parse.yes_no(text)
    assert r["yn"] == "" and r["cant"] is False and r["question"] is True


@pytest.mark.parametrize("text", ["I can't.", "No, I can't pay", "I can't, sorry", "Can't do it, no"])
def test_refusals_stay_refusals(text):
    assert parse.yes_no(text)["yn"] == "no"


def test_negative_question_to_a_transfer_offer_reasks_and_does_not_use_an_attempt():
    d = run_a(P05_ID + ["I lost my job last month and I cannot pay anything.", "Can't you just give me a discount?",
                        "Okay, yes, please put me through."], cid="PUB-05",
              expected=exp("transferred", "support", transfers=[{"queue": "support"}]))
    assert d.score()["pass"], d.lines
    d = run_a(P07_ID + ["Couldn't you waive the fees?", "No, I cannot pay today."], cid="PUB-07")
    assert not d.ended and "Could you pay" in d.lines[-1], d.lines        # attempt 1 is still to come


@pytest.mark.parametrize("text", ["when my December salary comes", "after my next paycheck",
                                  "when my November pay comes in", "once my bonus arrives", "next payday"])
def test_payday_with_a_qualifier_is_vague(text):
    assert parse.parse_date(text, TODAY, prepare(None, TODAY)) == {"kind": "vague", "what": "payday"}


def test_past_salary_is_not_vague():
    assert parse.parse_date("my salary came last week", TODAY, prepare(None, TODAY))["kind"] == "none"


def test_unparsed_named_period_is_vague_not_a_refusal():
    d = run_a(P07_ID + [{"t": "Not today. I'll pay after the harvest festival.", "u_act": "proposal",
                         "u_date": "after the harvest festival"}], cid="PUB-07")
    assert d.lines[-1] == SPEC_A["lines"].get("date_ask_exact", "Which exact day would work for you?"), d.lines


# ======================================================================= intents (MAJOR raw-ab)
def test_extracted_hardship_needs_a_cause_word_not_a_spec_keyword():
    sp = copy.deepcopy(SPEC_A)
    _intent(sp, "hardship")["keywords"] = [r"\blost my job\b"]
    for text in ("I'm between jobs, I can't pay.", "I've been unwell for weeks.", "I had surgery last month."):
        d = run_a(P05_ID + [{"t": text, "u_topic": "hardship"}], cid="PUB-05", spec=sp)
        assert "Would you like me to connect you" in d.lines[-1], (text, d.lines)
    d = run_a(P05_ID + [{"t": "I can't afford it.", "u_topic": "hardship"}], cid="PUB-05", spec=sp)
    assert "connect you" not in d.lines[-1], d.lines


@pytest.mark.parametrize("text", ["Not today. I'm not sick or anything, I can pay on Friday.",
                                  "No, I'm sick of these calls."])
def test_negated_or_idiomatic_hardship_keyword_does_not_offer_a_transfer(text):
    d = run_a(P05_ID + [text], cid="PUB-05")
    assert "connect you" not in d.lines[-1], d.lines


def test_a_relatives_death_does_not_close_the_call_as_deceased():
    d = run_a([{"t": "No, I'm her son.", "u_topic": "other_person"},
               {"t": "Her husband died last year, she lives alone now. She's out at the moment.",
                "u_topic": "other_person"}])
    assert not d.ended or d.ledger()["reason"] != "deceased", d.lines
    d = run_a([{"t": "No, I'm her son.", "u_topic": "other_person"},
               {"t": "She passed away last month.", "u_topic": "deceased"}])
    assert d.ended and d.score(exp("not_reached", "deceased"))["pass"], d.lines
    it = _intent(SPEC_A, "deceased")
    assert brain._b_kw_void(it, "My father died last year.", True)
    assert not brain._b_kw_void(it, "He died last year.", True)
    assert not brain._b_kw_void({"keywords": []}, "x", True)


def test_keyword_only_transfer_does_not_interrupt_a_proposal():
    sp = copy.deepcopy(SPEC_A)
    _intent(sp, "human")["keywords"] = [r"\b(an )?(agent|operator|advisor|adviser)\b"]
    d = run_a(P07_ID + [{"t": "No, but my financial advisor says I can pay it on Friday.", "u_act": "proposal",
                         "u_date": "Friday"}], cid="PUB-07", spec=sp)
    assert d.lines[-1].endswith("Do you confirm?"), d.lines
    d = run_a(P07_ID + ["Can I talk to an agent?"], cid="PUB-07", spec=sp)
    assert d.lines[-1] == _intent(sp, "human")["action"]["question"], d.lines


def test_product_placeholder_in_an_intent_line_names_the_product():
    sp = copy.deepcopy(SPEC_AB)
    _intent(sp, "dispute")["action"]["say"] = "I will not take a promise for your <product>."
    d = run_a(P12_ID[:2] + ["4410", "The car loan is not mine."], cid="PUB-12", spec=sp)
    assert any("for your car loan." in x for x in d.lines), d.lines
    single = copy.deepcopy(SPEC_A)
    _intent(single, "dispute")["action"]["say"] = "I will not take a promise for your <product>."
    d = run_a(P07_ID + ["This debt is not mine."], cid="PUB-07", spec=single)
    assert "for your personal loan." in d.lines[-1], d.lines


def test_named_date_after_a_declined_hardship_offer_gets_the_deadline_offer():
    sp = copy.deepcopy(SPEC_A)
    dl = eval_date_rule(prepare(sp["calendar"], TODAY), sp["bands"][1]["deadline"], TODAY, {})
    late = dl + datetime.timedelta(days=7)
    said = "No, I can pay the full amount on the %d%s of %s." % (late.day, "th", late.strftime("%B"))
    d = run_a(P05_ID + ["I lost my job last month.", {"t": said, "u_date": late.strftime("%d %B")}, "Yes.", "Yes."],
              cid="PUB-05")
    assert [(p["amount"], p["date"]) for p in d.ledger()["promises"]] == [(780.0, dl.isoformat())], d.lines
    d = run_a(P05_ID + ["I lost my job last month.", {"t": said, "u_date": late.strftime("%d %B")}, "No."], cid="PUB-05")
    assert d.ended and d.score(exp("no_promise", "hardship"))["pass"], d.lines


# ======================================================================= negotiation lines (MAJOR mut-c, minor raw-ab)
def test_not_all_of_them_is_a_plain_no_not_too_much():
    d = run_a(P11_ID + ["No, not all of them today."], cid="PUB-11")
    assert "220" in d.lines[-1] or "640" in d.lines[-1], d.lines        # attempt 1 = the full amount, not a floor
    assert not any(p.get("tm") for p in json.loads(d.vars["st"])["prods"])
    d = run_a(P11_ID + ["That's too much."], cid="PUB-11")
    assert any(p.get("tm") for p in json.loads(d.vars["st"])["prods"])


@pytest.mark.parametrize("say,qmarks", [("I'm sorry, I cannot record an amount below <floor>. Could you pay <floor>?", 1),
                                        ("Sorry, <amount> cannot be recorded. Could you pay <floor> on <date>?", 1)])
def test_below_floor_line_asks_one_question(say, qmarks):
    sp = copy.deepcopy(SPEC_A)
    sp["amounts"]["below_floor"]["say"] = say
    d = run_a(["Yes, this is Priya Nair.", "17 May 1986", "1502", "I could pay 10 on Friday."], cid="PUB-06", spec=sp)
    assert d.lines[-1].count("?") == qmarks, d.lines[-1]
    assert " on?" not in d.lines[-1]
    if "<amount>" in say:
        assert d.lines[-1].startswith("Sorry, $10 cannot") or "10 cannot" in d.lines[-1], d.lines[-1]


def test_call_level_close_with_a_note_reason_notes_every_open_product():
    sp = copy.deepcopy(SPEC_AB)
    sp["situations"]["S_CUSTOM_1"] = {"outcome": "no_promise", "reason": "hardship", "queue": "", "note_reason": "hardship"}
    sp["intents"].append({"id": "insolvent", "keywords": [r"\bbankrupt\w*\b"], "scope": ["neg", "conf"],
                          "precedence": 900, "product_scoped": False,
                          "action": {"kind": "close_now", "say": "I understand.", "situation": "S_CUSTOM_1"}})
    d = run_a(P11_ID + ["No, I cannot pay today. I am bankrupt."], cid="PUB-11", spec=sp)
    assert d.ended and sorted(n["reason"] for n in d.ledger()["notes"]) == ["hardship"] * 3, d.ledger()
    sp["situations"]["S_CUSTOM_1"]["note_reason"] = ""
    d = run_a(P11_ID + ["No, I cannot pay today. I am bankrupt."], cid="PUB-11", spec=sp)
    assert all(n["reason"] != "hardship" for n in d.ledger()["notes"])


# ======================================================================= after the promise (MAJOR mut-d)
def test_after_record_ask_anything_else_lets_a_transfer_follow_the_promise():
    sp = _sp(after_record="ask_anything_else")
    d = run_a(P01_ID + ["Yes, I can pay it all today.", "Yes.", "No, that's all, thanks."], spec=sp,
              expected=exp("promise", promises=[{"product_id": "p1", "amount": 420.0, "date": "2026-10-14"}]))
    assert d.score()["pass"] and d.lines[-2].endswith("Is there anything else I can help you with?"), d.lines
    assert d.lines[-2].count("text message") == 1 and "text message" not in d.lines[-1], d.lines
    d = run_a(P01_ID + ["Yes, I can pay it all today.", "Yes.", "I want to speak to a real person.",
                        "Yes, a real person please."], spec=sp,
              expected=exp("transferred", "human", promises=[{"product_id": "p1", "amount": 420.0, "date": "2026-10-14"}],
                           transfers=[{"queue": "general"}]))
    assert d.score()["pass"], (d.score(), d.lines)
    d = run_a(P01_ID + ["Yes, I can pay it all today.", "Yes.", "Can I change the promise later?", "When does it end?",
                        "What?"], spec=sp)
    assert d.ended and d.ledger()["outcome"] == "promise", d.lines


def test_after_record_close_is_unchanged_and_failed_writes_close_normally():
    d = run_a(P01_ID + ["Yes, I can pay it all today.", "Yes."])
    assert d.ended and "anything else" not in d.lines[-1]
    sp = _sp(after_record="ask_anything_else")
    d = run_a(P01_ID + ["Yes, I can pay it all today.", "Yes."], spec=sp,
              faults=[{"tool": "create_promise", "fail_first_n": 2}])
    assert d.ended and d.ledger()["promises"] == [] and "anything else" not in d.lines[-1], d.lines


def test_validate_derives_after_record_from_the_outcome_precedence():
    sp = copy.deepcopy(SPEC_A)
    del sp["interpretation"]["after_record"]
    assert _validate(sp)["spec"]["interpretation"]["after_record"] == "ask_anything_else"
    sp["outcomes"]["precedence"] = [p for p in sp["outcomes"]["precedence"] if p["when"] != "transfer_done"]
    assert _validate(sp)["spec"]["interpretation"]["after_record"] == "close"


def test_scenario_runner_answers_the_anything_else_question():
    sp = _sp(after_record="ask_anything_else")
    wf, _w = graph.compile_workflow(sp, CATALOG)
    r = scenarios.run({"id": "x", "pub": "PUB-01", "turns": [{"say": t} for t in P01_ID + ["Yes, I can pay it all today.",
                                                                                          "Yes."]]}, wf, CATALOG, sp)
    assert r["pass"], r["failed"]
    assert "auto reply to the anything-else question" in r["notes"]


# ======================================================================= closing lines (MAJOR/minor mut-d, raw-a)
def test_third_party_close_mode_ends_in_one_turn_with_the_brief_line_last():
    sp = copy.deepcopy(SPEC_A)
    sp["third_party"].update(mode="close", close_line="Thank you, we will try again another time. Goodbye.")
    sp["closing"]["per_situation"] = {"S_NO_CALLBACK": "Thank you, we will try again another time."}
    d = run_a(["No."], spec=sp, expected=exp("not_reached", "no_callback"))
    assert d.ended and d.score()["pass"], d.lines
    assert d.lines[-1].endswith("another time. Goodbye."), d.lines
    wf, w = graph.compile_workflow(sp, CATALOG)
    assert not w["api"]["cb"] and not any(n.startswith("a_cb") for n in wf["nodes"])


def test_validate_turns_a_never_book_third_party_policy_into_close_mode():
    sp = copy.deepcopy(SPEC_A)
    sp["third_party"]["callback"]["windows"] = [{"from": "00:00", "to": "00:00", "inclusive_from": True,
                                                 "inclusive_to": True, "days": "any"}]
    r = _validate(sp)
    assert r["spec"]["third_party"]["mode"] == "close" and r["spec"]["third_party"]["close_line"]
    sp = copy.deepcopy(SPEC_A)
    sp["third_party"]["reach_ask"] = "Thank you, we will call again. Goodbye."
    assert _validate(sp)["spec"]["third_party"]["mode"] == "close"
    assert "mode" not in _validate(copy.deepcopy(SPEC_A))["spec"]["third_party"]


def test_goodbye_is_stripped_from_a_line_the_call_goes_on_after():
    sp = copy.deepcopy(SPEC_A)
    _intent(sp, "refuse_talk")["action"]["say"] = "Thank you for your time. Goodbye."
    r = _validate(sp)
    assert _intent(r["spec"], "refuse_talk")["action"]["say"] == sp["lines"].get("ack", "I understand.")
    d = run_a(P07_ID + ["I don't want to talk about this."], cid="PUB-07", spec=r["spec"])
    assert "Goodbye" not in d.lines[-1] and not d.ended, d.lines


def test_no_goodbye_situation_says_only_its_line():
    sp = copy.deepcopy(SPEC_A)
    sp["closing"]["no_goodbye"] = ["S_DECEASED"]
    d = run_a([{"t": "No, I'm her son.", "u_topic": "other_person"},
               {"t": "She passed away last month.", "u_topic": "deceased"}], spec=sp)
    assert d.ended and d.lines[-1] == "I am sorry for your loss.", d.lines


def test_number_doublets_are_spoken_once_and_verbatim_still_matches():
    sp = copy.deepcopy(SPEC_A)
    _intent(sp, "paid")["action"]["say"] = "Payments can take up to two (2) business days to appear."
    sp["required_sentences"].append({"id": "x", "text": "Call us within seven (7) calendar days, item (3).",
                                     "trigger": "before_close", "once": True, "verbatim": True})
    brief = (ROOT / "kit" / "briefs" / "brief-a.md").read_text() + "\nSay: Call us within seven (7) calendar days, item (3)."
    r = _validate(sp, brief_text=brief)
    assert _intent(r["spec"], "paid")["action"]["say"] == "Payments can take up to two business days to appear."
    assert r["spec"]["required_sentences"][-1]["text"] == "Call us within seven calendar days, item (3)."
    assert r["errors"] == [], r["errors"]
    assert _validate(r["spec"], brief_text=brief)["errors"] == []
    assert V.collapse_doublets("twenty-one (21) and two (3)") == "twenty-one and two (3)"


def test_required_sentence_repeating_a_product_intent_line_is_dropped():
    sp = copy.deepcopy(SPEC_AB)
    sp["required_sentences"].append({"id": "paid_again", "text": _intent(sp, "paid")["action"]["say"],
                                     "trigger": "on_situation:S_PAID", "once": False, "verbatim": False})
    r = _validate(sp)
    assert "paid_again" not in [x["id"] for x in r["spec"]["required_sentences"]]
    assert "sorry_loss" in [x["id"] for x in r["spec"]["required_sentences"]]       # close_now line kept


def test_callback_today_interpretation_follows_the_date_rule():
    sp = copy.deepcopy(SPEC_A)
    sp["third_party"]["callback"]["date_rule"]["today_must_be_business_day"] = True
    sp["interpretation"]["callback_today_nonbd"] = "allow"
    r = _validate(sp)
    assert r["spec"]["interpretation"]["callback_today_nonbd"] == "refuse"
    assert any("callback_today_nonbd" in f for f in r["fixes"])


def test_keyword_matching_its_own_negative_warns_unless_the_runtime_guards_it():
    sp = copy.deepcopy(SPEC_A)
    _intent(sp, "restructure")["negatives"] = ["I don't want a payment plan, just a date."]
    _intent(sp, "restructure")["keywords"] = [r"\bpayment plan\b"]
    assert any("own negative" in w for w in _validate(sp)["warnings"])
    assert not any("own negative" in w for w in _validate(copy.deepcopy(SPEC_A))["warnings"])


# ======================================================================= money (minor raw-a)
@pytest.mark.parametrize("cur,out", [({"symbol": "USD", "position": "before"}, "USD 348"),
                                     ({"symbol": "$", "position": "before"}, "$348"),
                                     ({"symbol": "EUR", "position": "after"}, "348 EUR"),
                                     ({"symbol": "€", "position": "after"}, "348€"),
                                     ({"word": "dollars", "position": "none"}, "348 dollars")])
def test_letter_code_currency_is_a_separate_word(cur, out):
    assert brain._b_money(34800, {"bank": {"currency": cur}}) == out


# ======================================================================= harness / build (minor mut-c)
def test_generator_handles_holiday_rules_and_a_shaped_code():
    sp = copy.deepcopy(SPEC_A)
    sp["calendar"]["holiday_rules"] = [{"kind": "nth_weekday", "month": 5, "weekday": 0, "n": 1}]
    sp["identity"]["questions"][1] = dict(sp["identity"]["questions"][1], **POSTCODE)
    cat = copy.deepcopy(CATALOG)
    ids = [s["id"] for s in scenarios.generate(sp, cat)]
    assert {"GEN-happy", "GEN-id-failed", "GEN-refused", "GEN-callback"} <= set(ids), ids


def test_build_warns_when_no_smoke_scenario_was_generated(tmp_path, monkeypatch):
    from builder import build, trace
    seen = []
    monkeypatch.setattr(trace, "event", lambda kind, msg, **kw: seen.append((kind, msg)))
    monkeypatch.setattr(scenarios, "generate", lambda spec, catalog: [])
    summary = {}
    build._stage_twin(type("A", (), {"dev": False})(), SPEC_A, CATALOG, {}, tmp_path, summary)
    assert summary["twin"] == "0/0" and any(k == "WARN" and "no smoke scenarios" in m for k, m in seen)


# ======================================================================= packing (code-size headroom)
def test_packed_text_alphabet_is_safe_and_shorter_than_base64():
    import base64
    import os
    import zlib
    a = bundle._QALPHA
    assert len(a) == len(set(a)) == 85 and not set(a) & set("{}'\"\\<>& `\n")
    for n in range(0, 13):
        raw = os.urandom(n)
        assert bundle._unb85(bundle._b85(raw)) == raw
    snippet = bundle.make_snippet({"v": 1, "spec": SPEC_AB, "wiring": {}}, encoding="json", max_bytes=0)
    packed = bundle.pack_snippet(snippet)
    co = zlib.compressobj(9, zlib.DEFLATED, -15, 9)
    b64 = len(base64.b64encode(co.compress(snippet.encode()) + co.flush()))
    m = __import__("re").search(r"_qb\('([^']*)'\)", packed)
    assert len(m.group(1)) < b64 * 0.95
    assert bundle.unpack_snippet(packed) == snippet
    assert "\ndef _qb(s):\n a = " in packed                                    # one space per indent level
    for fb in (False, True):
        v = {}
        exec(compile(bundle.pack_snippet("vars['nx'] = 'ok'\n", force_fallback=fb), "<ctl>", "exec"), {"vars": v})
        assert v["nx"] == "ok"


def test_graph_builds_nodes_for_every_dated_variant():
    sp = copy.deepcopy(SPEC_A)
    assert sp["notes"]["enabled"] is False and sp["products"]["max"] == 1
    sp["dated"] = [{"from": "2026-11-16", "path": "/notes/enabled", "value": True},
                   {"from": "2026-11-16", "path": "/products/max", "value": 3}]
    assert _validate(sp)["errors"] == []
    w = graph.wiring(sp, CATALOG)
    assert len(w["api"]["promise"]) == 3 and len(w["api"]["note"]) == 3
    assert brain.dated_spec(sp, TODAY)["notes"]["enabled"] is False          # the runtime still decides per call


def test_negation_inside_a_wide_keyword_match_is_seen():
    it = {"keywords": [r"\b(i'?m|i am) (\w+ )?(ill|sick)\b", r"\bcan't work\b"]}
    assert brain._b_kw_void(it, "I'm not sick, I just don't want to pay.", False)
    assert not brain._b_kw_void(it, "I'm really sick.", False)
    assert not brain._b_kw_void(it, "I can't work at the moment.", False)


def test_brief_dictated_pre_verification_line_unbans_its_own_word():
    sp = copy.deepcopy(SPEC_A)
    sp["banned"]["before_verification"] = sp["banned"]["before_verification"] + ["card"]
    sp["identity"]["fail_line"] = "Please call the number on the back of your card."
    brief = (ROOT / "kit" / "briefs" / "brief-a.md").read_text()
    errs = _validate(sp, brief_text=brief + "\nFail line: Please call the number on the back of your card.")
    assert errs["errors"] == [] and "card" not in errs["spec"]["banned"]["before_verification"]
    errs = _validate(sp, brief_text=brief)                                     # a paraphrase stays an error
    assert any("banned word" in e for e in errs["errors"])


def test_close_mode_points_an_undefined_callback_situation_at_no_callback():
    sp = copy.deepcopy(SPEC_A)
    sp["third_party"].update(mode="close", close_line="We will try again another time.")
    del sp["situations"]["S_CALLBACK"]
    r = _validate(sp)
    assert r["errors"] == [] and r["spec"]["third_party"]["situations"]["callback"] == "S_NO_CALLBACK"


def test_intent_line_product_placeholder_uses_the_pending_offer():
    sp = copy.deepcopy(SPEC_A)
    _intent(sp, "forbidden_offer")["action"]["say"] = "I can't offer that for your <product>."
    d = run_a(P07_ID + ["Can I get a discount?"], cid="PUB-07", spec=sp)
    assert "for your personal loan." in d.lines[-1], d.lines
    sp = copy.deepcopy(SPEC_AB)
    _intent(sp, "forbidden_offer")["action"]["say"] = "I can't offer that for your <product>."
    d = run_a(P11_ID + ["Can I get a discount?"], cid="PUB-11", spec=sp)  # no single product under discussion
    assert "for your credit card ending 2288, personal loan and car loan." in d.lines[-1], d.lines


def test_after_record_with_open_products_and_a_hardship_reply():
    sp = _sp(SPEC_AB, after_record="ask_anything_else")
    d = run_a(P12_ID + ["I can pay the credit card tomorrow.", "No.", "No.", "No.", "Yes.", "No, thank you."],
              cid="PUB-12", spec=sp)
    assert d.ended and d.ledger()["outcome"] == "promise" and len(d.ledger()["notes"]) == 2, d.lines
    sp = _sp(after_record="ask_anything_else")
    d = run_a(P01_ID + ["Yes, I can pay it all today.", "Yes.", "Actually I lost my job last month.", "Yes, please."],
              spec=sp, expected=exp("transferred", "support", transfers=[{"queue": "support"}],
                                    promises=[{"product_id": "p1", "amount": 420.0, "date": "2026-10-14"}]))
    assert d.score()["pass"], (d.score(), d.lines)


def test_edge_inputs_of_the_new_helpers():
    q = {"key": "year", "kind": "year", "wire_format": "%Y", "length": 4, "pattern": ""}
    assert id_answer(q, "nineteen", "", TODAY)["status"] == "none"
    assert V.collapse_doublets(None) is None
    meta = {"warnings": []}
    spec = {}
    extract.merge_dated(spec, "F3", extract.FACETS["F3"], ["junk", {"from": "2026-11-16", "until": "", "pointer": "/bands/0/x",
                                                                     "value_json": "ten", "quote": ""}], "", meta)
    assert spec["dated"] == [{"from": "2026-11-16", "path": "/bands/0/x", "value": "ten"}]
    sp = copy.deepcopy(SPEC_A)
    sp["dated"] = [{"from": "2026-13-45", "path": "/bands/0/deadline/n", "value": 3}]
    assert _validate(sp)["errors"] == [] and len(graph._variants(sp)) == 1
    sp = copy.deepcopy(SPEC_A)
    sp["third_party"]["reach_ask"] = "Thanks. Goodbye."
    sp["third_party"]["close_line"] = "We will call again."
    assert _validate(sp)["spec"]["third_party"]["close_line"] == "We will call again."
    sp = copy.deepcopy(SPEC_A)
    sp["identity"]["questions"][1] = dict(sp["identity"]["questions"][1], **dict(POSTCODE, pattern="^(AB|CD)$"))
    r = _validate(sp)
    assert not any("never completes" in w for w in r["warnings"])          # unsupported pattern: not sampled
    assert "GEN-happy" not in [g["id"] for g in scenarios.generate(sp, CATALOG)]


def test_no_goodbye_keeps_the_briefs_per_situation_line():
    sp = copy.deepcopy(SPEC_A)
    sp["closing"]["no_goodbye"] = ["S_NO_CALLBACK"]
    sp["closing"]["per_situation"] = {"S_NO_CALLBACK": "We will try again another time. Goodbye."}
    sp["third_party"].update(mode="close", close_line="We will try again another time.")
    d = run_a(["No."], spec=sp)
    assert d.ended and d.lines[-1] == "We will try again another time. Goodbye.", d.lines


def test_runtime_spec_drops_build_time_only_fields():
    from builder.compiler import snippet
    sp = copy.deepcopy(SPEC_A)
    sp["dated"] = [{"from": "2026-11-16", "path": "/bands/0/deadline/n", "value": 10, "source": "memo item 5"}, "junk"]
    sp["call_variables"]["declared"].append("junk")
    rs = snippet.runtime_spec(sp, {})["spec"]
    assert "banned" not in rs and rs["dated"][0] == {"from": "2026-11-16", "path": "/bands/0/deadline/n", "value": 10}
    assert all("meaning" not in d for d in rs["call_variables"]["declared"] if isinstance(d, dict))
    assert "banned" in sp and sp["dated"][0]["source"] == "memo item 5"                 # the input is untouched


def test_call_level_close_after_a_recorded_promise_notes_only_the_open_products():
    sp = _sp(SPEC_AB, after_record="ask_anything_else")
    sp["situations"]["S_CUSTOM_1"] = {"outcome": "no_promise", "reason": "hardship", "queue": "", "note_reason": "hardship"}
    sp["intents"].append({"id": "insolvent", "keywords": [r"\bbankrupt\w*\b"], "scope": ["neg", "conf"],
                          "precedence": 900, "product_scoped": False,
                          "action": {"kind": "close_now", "say": "I understand.", "situation": "S_CUSTOM_1"}})
    d = run_a(P12_ID + ["I can pay the credit card tomorrow.", "No.", "No.", "No.", "Yes.", "I am bankrupt, by the way."],
              cid="PUB-12", spec=sp)
    L = d.ledger()
    assert d.ended and L["outcome"] == "promise" and len(L["promises"]) == 1, d.lines
    assert sorted((n["product_id"], n["reason"]) for n in L["notes"]) == [("p2", "hardship"), ("p3", "hardship")]


def test_product_placeholder_before_the_account_is_read_names_nothing():
    # no product is known before get_account (and none may be named before verification): the placeholder is empty
    sp = copy.deepcopy(SPEC_A)
    _intent(sp, "scam")["action"]["say"] = "Call us about your <product>."
    d = run_a(P01_ID[:2] + ["Is this a scam?"], spec=sp)
    assert "<product>" not in d.lines[-1] and "card" not in d.lines[-1], d.lines


def test_identity_check_warns_when_the_length_repair_is_not_enough():
    # quality refactor of validate._identity_checks: the length is repaired, the pattern still never matches -> warn
    sp = copy.deepcopy(SPEC_A)
    sp["identity"]["questions"][1] = dict(sp["identity"]["questions"][1], **dict(POSTCODE, length=9))
    sp["identity"]["questions"][1]["pattern"] = "^[a-z]{3}$"
    r = _validate(sp)
    assert r["spec"]["identity"]["questions"][1]["length"] == 0
    assert any("length" in f for f in r["fixes"]) and any("never completes" in w for w in r["warnings"])


def test_validate_helpers_keep_their_behaviour_after_the_quality_split():
    s = {"intents": [{"action": {"kind": "offer_transfer", "say": "Goodbye now.", "question": 3}},
                     {"action": {"kind": "resolve_product", "say": "x"}}],
         "right_party": {"reask": "Is that you?"}, "identity": {"questions": ["bad", {"ask": "Your code?"}]},
         "third_party": {"mode": "close", "reach_ask": "Bye."}}
    assert [p for _, _, p in V._nonterminal_lines(s)] == [
        "/intents/0/action/say", "/right_party/reask", "/identity/questions/1/ask"]
    assert V._resolve_parent({"a": [{"b": 1}]}, "/a/0/b") == {"b": 1}
    assert V._resolve_parent({"a": [1]}, "/a/5/b") is None and V._resolve_parent({"a": 1}, "/a/b") is None
    errors = []
    V._dated_checks({"dated": [{"from": "2026-11-16", "path": "/bands/nope/x", "value": 1}]}, errors)
    assert errors and "does not resolve" in errors[0]
    assert V._kw_hits("(", "text") is False and V._kw_hits("sick", 3) is False and V._kw_hits("sick", "Sick") is True
    warnings = []
    V._keyword_checks([{"id": "h", "action": {"kind": "offer_transfer"}, "keywords": ["sick"],
                        "negatives": ["I am not sick", "sick leave pay"]}], warnings)
    assert len(warnings) == 1 and "sick leave pay" in warnings[0]
