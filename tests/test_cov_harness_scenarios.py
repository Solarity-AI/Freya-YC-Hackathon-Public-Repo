"""Coverage + behaviour for harness/scenarios.py: runner options and the generic Spec-driven generator."""
import copy
import datetime

import pytest

from harness import scenarios as sc
from harness import toy

D = datetime.date
TODAY = D(2026, 1, 7)                                   # generator's fixed today: a Wednesday
WEEK = {"business_weekdays": [0, 1, 2, 3, 4], "holidays": []}

PUB01 = [["say", "Before we continue, could you please tell me your date of birth?", "s_l"],
         ["call", "verify_identity", {"field": "date_of_birth", "answer": "1988-03-14"}],
         ["say", "Thank you. What are the last four digits of the phone number on file?", "s_l"],
         ["call", "verify_identity", {"field": "phone_last4", "answer": "4471"}],
         ["call", "get_account", {}],
         ["say", "Can you pay 420 today?", "s_l"],
         ["say", "So that is 420 today. Do you confirm?", "s_l"],
         ["call", "create_promise", {"product_id": "p1", "amount": "420.00", "date": "2026-10-14"}],
         ["close", "promise", "", "Your promise is recorded. Goodbye."]]

TURNS = [{"say": "Yes, speaking.", "x": {"u_act": "yes"}},
         {"say": "14 March 1988.", "x": {"u_act": "answer"}},
         {"say": "4471.", "x": {"u_act": "answer"}},
         {"say": "Yes, today.", "x": {"u_act": "yes"}},
         {"say": "Yes, I confirm.", "x": {"u_act": "yes"}}]


# ---------------------------------------------------------------- runner
def test_run_with_custom_customer_key_passes_only_that_variable(catalog_kit):
    spec = {"call_variables": {"customer_key": "cust_ref"}}
    s = {"id": "K1", "pub": "PUB-01", "turns": TURNS, "transcript": {}}
    wf = toy.hub_workflow(catalog_kit, PUB01, customer_key="cust_ref")
    r = sc.run(s, wf, catalog_kit, spec)
    assert r["pass"], r["failed"]
    assert {c["args"]["customer_id"] for c in r["ledger"]["calls"]} == {"c_twin_pub_01"}
    # a workflow that reads {{customer_id}} does not get it: only the Spec's customer key is a call variable
    r2 = sc.run(s, toy.hub_workflow(catalog_kit, PUB01), catalog_kit, spec)
    assert not r2["pass"] and r2["ledger"]["calls"] == []                 # every request was a 404 (not logged)


def test_run_without_transcript_flags_checks_only_ledger_and_end(catalog_kit):
    plan = [["say", "Date of birth?", "s_l"], ["say", "Again?", "s_l"]]
    s = {"id": "K2", "pub": "PUB-01", "turns": TURNS[:2], "transcript": {}}
    r = sc.run(s, toy.hub_workflow(catalog_kit, plan), catalog_kit, None)
    assert r["failed"][0] == "the call did not end (node s_l)"
    assert not any("banned" in f or "agent lines" in f or "hops" in f for f in r["failed"])
    assert r["lines_per_turn"] == [1, 1, 1] and r["notes"] == []


def test_run_scenario_banned_list_and_twin_options(catalog_kit):
    plan = copy.deepcopy(PUB01)
    plan[0][1] = "About your arrears: what is your date of birth?"
    s = {"id": "K3", "pub": "PUB-01", "turns": TURNS, "banned": ["arrears"], "twin": {"bool_style": "title"},
         "transcript": {"no_banned_before_verified": True}}
    r = sc.run(s, toy.hub_workflow(catalog_kit, plan), catalog_kit, None)
    assert r["failed"] == ["banned before verification ['arrears'] in "
                           "'About your arrears: what is your date of birth?'"]


# ---------------------------------------------------------------- date / amount helpers
def test_next_bd_skips_weekend_and_holidays_and_gives_up():
    assert sc._next_bd(WEEK, D(2026, 1, 9)) == D(2026, 1, 12)              # Friday -> Monday
    cal = {"business_weekdays": [0], "holidays": [(D(2026, 1, 12) + datetime.timedelta(weeks=w)).isoformat()
                                                  for w in range(60)]}
    assert sc._next_bd(cal, TODAY) is None                                 # no business day within 400 days


@pytest.mark.parametrize("rule,cal,want", [
    ({"kind": "today"}, WEEK, TODAY),
    ({"kind": "next_business_day"}, dict(WEEK, holidays=["2026-01-08"]), D(2026, 1, 9)),
    ({"kind": "nth_business_day_after_today", "n": 3}, WEEK, D(2026, 1, 12)),
    ({"kind": "nth_business_day_after_today", "n": 3}, dict(WEEK, count_from="including_today"), D(2026, 1, 9)),
    ({"kind": "nth_business_day_after_today", "n": 1}, dict(WEEK, count_from="including_today"), TODAY),
    ({"kind": "fixed", "date": "2026-02-01"}, WEEK, D(2026, 2, 1)),
    ({"kind": "fixed", "date": "1 Feb"}, WEEK, None),
    ({"kind": "fixed"}, WEEK, None),
    ({"kind": "last_business_day_of_week"}, WEEK, None),
    (None, WEEK, None),
    ({"kind": "today"}, dict(WEEK, holiday_rules=[{"kind": "easter"}]), None),
])
def test_eval_simple_date(rule, cal, want):
    assert sc._eval_simple_date(rule, cal, TODAY) == want


def test_nth_business_day_including_today_on_a_weekend_counts_fully():
    sat = D(2026, 1, 10)
    assert sc._eval_simple_date({"kind": "nth_business_day_after_today", "n": 1},
                                dict(WEEK, count_from="including_today"), sat) == D(2026, 1, 12)


@pytest.mark.parametrize("rule,want", [({"kind": "full"}, 250.0), ({"kind": "floor"}, 75.0),
                                       ({"kind": "fixed", "value": "99.5"}, 99.5), ({"kind": "fixed"}, 0.0),
                                       ({"kind": "percent_of_full", "pct": 33}, 82.5),
                                       ({"kind": "percent_of_full"}, 250.0),
                                       ({"kind": "floor_if_too_much_else_full"}, None), (None, None)])
def test_eval_simple_amount(rule, want):
    assert sc._eval_simple_amount(rule, {"_full": 250.0}, 75.0) == want


def test_floor_amount_never_above_full():
    assert sc._eval_simple_amount({"kind": "floor"}, {"_full": 50.0}, 75.0) == 50.0


def test_resolve_product_outcome_precedence(golden_a):
    assert sc._resolve_product_outcome(golden_a, "S_PAID") == "S_PAID"                 # all_products:S_PAID rule
    assert sc._resolve_product_outcome(golden_a, "S_DISPUTE") == "S_DISPUTE"           # first_product_excluding
    spec = {"outcomes": {"precedence": [{"when": "any_product:S_X", "use": "situation:S_Y"},
                                        {"when": "else", "use": "call_situation"},
                                        {"when": "else", "use": "first_product_excluding:S_A,S_B"}],
                         "unresolved_product_situation": "S_U"}}
    assert sc._resolve_product_outcome(spec, "S_X") == "S_Y"
    assert sc._resolve_product_outcome(spec, "S_B") == "S_U"
    assert sc._resolve_product_outcome(spec, "S_C") == "S_C"
    assert sc._resolve_product_outcome({"outcomes": {"precedence": [{"when": "else", "use": "odd"}]}}, "S_C") == "S_C"
    assert sc._resolve_product_outcome({}, "S_Q") == "S_Q"


def test_promise_situation_lookup(golden_a):
    assert sc._promise_situation(golden_a) == "S_PROMISE"
    assert sc._promise_situation({"outcomes": {"precedence": [{"when": "any_promise_recorded", "use": "x"}]}}) is None
    assert sc._promise_situation({}) is None


def test_situation_expect_reason_blank_is_none(golden_a):
    assert sc._situation_expect(golden_a, "S_PROMISE") == ("promise", None)
    assert sc._situation_expect(golden_a, "S_DISPUTE") == ("no_promise", "dispute")
    assert sc._situation_expect(golden_a, "S_NOPE") == (None, None)


def test_wire_date_and_ordinals():
    assert sc._wire_date(D(2026, 1, 7), "%d.%m.%y") == "07.01.26"
    assert sc._wire_date(D(2026, 1, 7), None) == "2026-01-07"
    assert [sc._ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 111, 101)] == \
        ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "23rd", "111th", "101st"]


def test_id_value_defaults_and_unknown_kind():
    assert sc._id_value({"kind": "digits"}, 0) == ("1234", "1 2 3 4", "1234")
    assert sc._id_value({"kind": "digits", "length": 12}, 0)[0] == "123456789055"
    assert sc._id_value({"kind": "alnum"}, 1) == ("ZX98YW", "Z X 9 8 Y W", "ZX98YW")
    assert sc._id_value({"kind": "year"}, 2) == ("1994", "1994", "1994")
    assert sc._id_value({"kind": "date"}, 1) == ("1981-02-16", "16 February 1981", "16 February 1981")
    assert sc._id_value({"kind": "voiceprint"}, 0) is None
    wrong = {sc._id_value({"kind": "digits", "length": 4}, k)[0] for k in range(1, 11)}
    assert "1234" not in wrong                                              # a wrong answer is never the true one


# ---------------------------------------------------------------- callback slots
WIN = [{"from": "10:00", "to": "19:00", "days": "any"}]


def test_callback_slot_today_only_after_now_plus_lead():
    cb = {"date_rule": {"include_today": True}, "windows": WIN}
    assert sc._callback_slot(cb, WEEK, TODAY, 11 * 60) == (TODAY, "14:00")
    assert sc._callback_slot(dict(cb, min_lead_minutes=240), WEEK, TODAY, 11 * 60) is None


def test_callback_slot_today_must_be_business_day():
    sat = D(2026, 1, 10)
    cb = {"date_rule": {"include_today": True, "today_must_be_business_day": True}, "windows": WIN}
    assert sc._callback_slot(cb, WEEK, sat, 0) is None
    assert sc._callback_slot(cb, WEEK, TODAY, 0) == (TODAY, "14:00")


def test_callback_slot_calendar_days_and_day_filters():
    cb = {"date_rule": {"include_today": False, "calendar_days_ahead": 3},
          "windows": [{"from": "09:00", "to": "12:00", "days": "business"},
                      {"from": "10:00", "to": "14:00", "days": "non_business"}]}
    # candidates Thu 8, Fri 9, Sat 10 -> latest first: Saturday only matches the non_business window
    assert sc._callback_slot(cb, WEEK, TODAY, 0) == (D(2026, 1, 10), "12:00")
    cb["date_rule"]["calendar_days_ahead"] = 2
    assert sc._callback_slot(cb, WEEK, TODAY, 0) == (D(2026, 1, 9), "10:00")
    cb["windows"] = cb["windows"][1:]                              # weekend-only window, weekday candidates
    assert sc._callback_slot(cb, WEEK, TODAY, 0) is None


def test_callback_slot_window_too_narrow_for_a_clear_hour():
    cb = {"date_rule": {"business_days_ahead": 1}, "windows": [{"from": "10:00", "to": "10:30"}]}
    assert sc._callback_slot(cb, WEEK, TODAY, 0) is None


def test_callback_slot_no_business_day_found_for_one_day_ahead():
    cal = {"business_weekdays": [0], "holidays": [(D(2026, 1, 12) + datetime.timedelta(weeks=w)).isoformat()
                                                  for w in range(60)]}
    cb = {"date_rule": {"business_days_ahead": 1}, "windows": WIN}
    assert sc._callback_slot(cb, cal, TODAY, 0) is None


def test_callback_slot_no_business_day_two_days_ahead_returns_none():
    cal = {"business_weekdays": [0], "holidays": [(D(2026, 1, 12) + datetime.timedelta(weeks=w)).isoformat()
                                                  for w in range(60)]}
    cb = {"date_rule": {"business_days_ahead": 2}, "windows": WIN}
    assert sc._callback_slot(cb, cal, TODAY, 0) is None


# ---------------------------------------------------------------- generate on minimal Specs
CAT = {"tools": {"get_account": {"roles": {"item": {"type": "type", "past_due": "past_due"}}}}}


def _spec(**over):
    s = {"call_variables": {"declared": [{"name": "first_name"}, {"name": "ref"}]},
         "calendar": dict(WEEK),
         "products": {"types": {"loan": {"spoken": "loan <f:acct> <f:branch>", "floor": {"kind": "percent"}}}},
         "identity": {"questions": [{"field_value": "pin", "kind": "digits", "length": 4, "pattern": "^[0-9]{4}$"}],
                      "max_wrong_total": 2},
         "negotiation": {"first_ask": {"amount": {"kind": "fixed", "value": 100}, "date": {"kind": "next_business_day"}}},
         "outcomes": {"precedence": [{"when": "any_promise_recorded", "use": "situation:S_P"}]},
         "situations": {"S_P": {"outcome": "promise", "reason": ""}, "S_F": {"outcome": "not_verified",
                                                                         "reason": "failed"},
                        "S_R": {"outcome": "no_promise", "reason": "refused"}}}
    s.update(over)
    return s


def test_generate_minimal_spec_happy_only():
    gen = sc.generate(_spec(), CAT)
    assert [g["id"] for g in gen] == ["GEN-happy"]
    g = gen[0]
    assert g["case"]["variables"] == {"first_name": "Tester", "ref": "Tester", "customer_id": "c_gen",
                                      "now": "2026-01-07T11:00"}
    assert g["case"]["products"] == [{"type": "loan", "past_due": 250.0, "acct": "1234", "branch": "1234"}]
    assert g["case"]["identity"] == {"pin": "1234"}
    assert g["turns"][0]["say"] == "Yes, this is Alex speaking." and g["turns"][1]["say"] == "1 2 3 4"
    assert g["expect"] == {"outcome": "promise", "reason": None,
                           "promises": [{"product_id": "p1", "amount": 100.0, "date": "2026-01-08"}]}


def test_generate_custom_keys_names_and_bands():
    cat = {"tools": {"get_account": {"roles": {"item": {"type": "kind", "past_due": "due", "days_late": "dl"}}}}}
    spec = _spec(call_variables={"customer_key": "cref", "now": "today_is"},
                 addressing={"name_vars": ["given", "family", "middle", "extra"]})
    g = sc.generate(spec, cat)[0]
    assert g["case"]["variables"] == {"cref": "c_gen", "today_is": "2026-01-07T11:00", "given": "Alex",
                                      "family": "Morgan", "middle": "Jordan", "extra": "Alex"}
    assert g["case"]["products"][0]["dl"] == 5                         # no bands: a generic 5 days late
    g2 = sc.generate(dict(spec, bands=[{"days_late_min": 31}]), cat)[0]
    assert g2["case"]["products"][0]["dl"] == 31


def test_generate_without_derivable_offer_or_promise_situation():
    no_amt = _spec(negotiation={"first_ask": {"amount": {"kind": "floor_if_too_much_else_full"}}},
                   identity=dict(_spec()["identity"], on_failed="S_F"))
    gen = sc.generate(no_amt, CAT)
    assert [g["id"] for g in gen] == ["GEN-id-failed"]
    f = gen[0]
    assert len(f["turns"]) == 1 + 2 + 1 and f["expect"] == {"outcome": "not_verified", "reason": "failed"}
    assert [t["x"]["u_ans"] for t in f["turns"][1:3]] == ["8765", "7650"]
    no_psit = _spec(outcomes={"precedence": []})
    assert sc.generate(no_psit, CAT) == []


def test_generate_refused_note_only_when_situation_has_note_reason():
    neg = dict(_spec()["negotiation"], on_exhausted="S_R", ladder=[{"key": "r1"}, {"key": "r2"}])
    spec = _spec(negotiation=neg, notes={"enabled": True, "scope": "product"})
    ref = {g["id"]: g for g in sc.generate(spec, CAT)}["GEN-refused"]
    assert ref["expect"] == {"outcome": "no_promise", "reason": "refused", "notes": []}
    assert [t["x"]["u_act"] for t in ref["turns"]].count("no") == 2 + 3
    spec["situations"]["S_R"]["note_reason"] = "refused"
    ref = {g["id"]: g for g in sc.generate(spec, CAT)}["GEN-refused"]
    assert ref["expect"]["notes"] == [{"product_id": "p1", "reason": "refused"}]
    spec["notes"]["scope"] = "call"
    ref = {g["id"]: g for g in sc.generate(spec, CAT)}["GEN-refused"]
    assert ref["expect"]["notes"] == []


def test_generate_skips_identity_scenarios_when_pattern_rejects_value():
    spec = _spec(identity={"questions": [{"field_value": "pin", "kind": "digits", "length": 4,
                                          "pattern": "^[A-Z]+$"}], "on_failed": "S_F"})
    assert sc.generate(spec, CAT) == []


def test_generate_callback_only_spec_without_identity():
    spec = _spec(identity={"questions": []},
                 third_party={"callback": {"date_rule": {"business_days_ahead": 1}, "windows": WIN},
                              "situations": {"callback": "S_CB"}},
                 situations={"S_CB": {"outcome": "not_reached", "reason": "callback"}})
    gen = sc.generate(spec, CAT)
    assert [g["id"] for g in gen] == ["GEN-callback"]
    cb = gen[0]
    assert cb["expect"] == {"outcome": "not_reached", "reason": "callback",
                            "callbacks": [{"date": "2026-01-08", "time": "14:00"}]}
    assert cb["turns"][1]["say"] == "Please call back on Thursday the 8th of January at 14:00."
    no_sid = dict(spec, third_party={"callback": spec["third_party"]["callback"]})
    assert sc.generate(no_sid, CAT) == []


def test_generate_needs_item_type_and_past_due_roles():
    assert sc.generate(_spec(), {"tools": {}}) == []
    assert sc.generate(_spec(), {"tools": {"get_account": {"roles": {"item": {"type": "type"}}}}}) == []
