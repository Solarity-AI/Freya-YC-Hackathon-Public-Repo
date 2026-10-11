"""Coverage + behaviour tests for runtime/brain.py from line ~1350 to the end (third party, identity, account,
negotiation ladder, intents, multi-product, confirmation, write chain, failures, outcome/notes, closing, dispatch).

Every test asserts behaviour against the golden Specs / docs/CONTRACTS.md (says, nx, state and ledger effects).
The brain is driven through its pure core (`brain.step`) or, for a single helper, through `brain._b_ctx` + the helper.
Brief values live only in tests (golden Specs, kit public cases)."""
import copy
import json
import pathlib

import pytest

from runtime import brain

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load(rel):
    return json.loads((ROOT / rel).read_text())


SPEC_A = _load("tests/golden/spec-a.json")
SPEC_AB = _load("tests/golden/spec-ab.json")
W_A = _load("tests/fixtures/wiring-a.json")
W_AB = _load("tests/fixtures/wiring-ab.json")
CASES = {c["id"]: c for c in _load("kit/public-test-set.json")}
NOW = "2026-10-14T11:00"  # Wednesday


def rspec(spec, wiring):
    spec = copy.deepcopy(spec)
    spec.pop("meta", None)
    for it in spec.get("intents", []):
        for k in ("label", "description", "examples", "negatives"):
            it.pop(k, None)
    for k in ("confirm_examples", "non_confirm_examples"):
        spec.get("right_party", {}).pop(k, None)
    return {"v": 1, "spec": spec, "wiring": copy.deepcopy(wiring)}


def RA():
    return rspec(SPEC_A, W_A)


def RAB():
    return rspec(SPEC_AB, W_AB)


def call_vars(cid="PUB-11", now=NOW):
    v = dict(CASES[cid]["variables"])
    v["customer_id"] = "cust-1"
    v["now"] = now
    return v


def inp(text="", act="", topic="", cid="PUB-11", now=NOW, results=None, **sens):
    s = {"u_text": text, "u_act": act, "u_topic": topic}
    for k in ("u_date", "u_amt", "u_time", "u_ans"):
        s[k] = sens.get(k, "")
    return {"call": call_vars(cid, now), "sensors": s, "results": results or {}, "entered_from": ""}


def ctx(R, st=None, text="", act="", topic="", cid="PUB-11", now=NOW, results=None, **sens):
    return brain._b_ctx(R, st if st is not None else {}, inp(text, act, topic, cid, now, results, **sens))


def items_of(cid):
    out = []
    for i, p in enumerate(CASES[cid]["products"]):
        q = dict(p)
        q["product_id"] = "p%d" % (i + 1)
        out.append(q)
    return out


def neg_state(R, cid="PUB-11", now=NOW, products=None):
    """State right after the statement + first ask (phase NEG), built by the brain itself."""
    c = ctx(R, {}, cid=cid, now=now)
    c["st"]["ph"] = "ACCT"
    c["st"]["prods"] = brain._b_build_prods(c, products if products is not None else items_of(cid))
    brain._b_statement(c)
    st = c["st"]
    st["turns"] = 5
    return json.loads(json.dumps(st))


def turn(R, st, text, act="", topic="", cid="PUB-11", now=NOW, results=None, **sens):
    """One customer turn through the pure core. -> (new_st, writes)."""
    return brain.step(R, st, inp(text, act, topic, cid, now, results, **sens))


def result(R, st, results, cid="PUB-11", now=NOW):
    """Re-entry after an api node (no customer text)."""
    return brain.step(R, st, inp("", "", "", cid, now, results))


def fail_res():
    return {"s": "pending", "err": "pending"}


def tp_state(R):
    st, w = turn(R, {}, "No, she's not here.")
    assert st["ph"] == "TP" and w["nx"] == "s_tp"
    return st


# ======================================================================= small text helpers
def test_xparts_splits_lead_and_question_only_when_last_sentence_is_a_question():
    assert brain._b_xparts("I'm sorry. Would you like help?") == ("I'm sorry.", "Would you like help?")
    assert brain._b_xparts("Would you like help?") == ("", "Would you like help?")
    assert brain._b_xparts("I'm sorry. I will help.") == ("", "I'm sorry. I will help.")


# ======================================================================= stash of post-verification intents (RP)
def test_stash_post_skips_answer_continue_intents_and_stashes_nothing():
    R = RAB()
    c = ctx(R, {"ph": "RP"}, "Yes, it's me. Are you a robot?")
    assert brain._b_stash_post(c) == []
    assert "stash" not in c["st"]


def test_stash_post_keeps_the_first_stash_and_never_repeats_sympathy():
    R = RAB()
    c = ctx(R, {"ph": "RP", "stash": "dispute"}, "Yes, it's me. I lost my job.")
    assert brain._b_stash_post(c) == []
    assert c["st"]["stash"] == "dispute"
    c = ctx(R, {"ph": "RP", "symp": 1}, "Yes, it's me. I lost my job.")
    assert brain._b_stash_post(c) == []
    assert c["st"]["stash"] == "hardship"


def test_stash_post_resolve_product_is_stashed_without_a_say():
    R = RAB()
    c = ctx(R, {"ph": "RP"}, "Yes, speaking. That card is not mine.")
    assert brain._b_stash_post(c) == []
    assert c["st"]["stash"] == "dispute"


def test_stash_post_offer_without_lead_sentence_says_nothing_now():
    R = RAB()
    for it in R["spec"]["intents"]:
        if it["id"] == "hardship":
            it["action"]["say"] = "Would you like me to connect you with our customer support team?"
    c = ctx(R, {"ph": "RP"}, "Yes, it's me. I lost my job.")
    assert brain._b_stash_post(c) == []
    assert c["st"]["stash"] == "hardship" and not c["st"].get("symp")


def test_rp_confirm_with_hardship_says_sympathy_once_then_identity():
    R = RAB()
    st, w = turn(R, {}, "Yes, this is me. I lost my job.")
    assert st["ph"] == "ID" and st["stash"] == "hardship" and st["symp"] == 1
    assert w["say"].startswith("I'm sorry to hear that.")
    assert w["say"].endswith("could you please tell me your date of birth?")
    assert "connect you" not in w["say"]


# ======================================================================= third party
def test_tp_hold_restarts_right_party_with_hold_line():
    R = RAB()
    st, w = turn(R, tp_state(R), "Hold on, let me get her.")
    assert w["say"] == "One moment, please." and w["nx"] == "s_rp"
    assert st["ph"] == "RP" and st["rp"] == {"asks": 0, "restart": 1}
    st2, w2 = turn(R, tp_state(R), "hmm", topic="hold")
    assert w2["nx"] == "s_rp" and st2["rp"]["restart"] == 1


def test_tp_non_close_intent_in_tp_scope_never_transfers():
    R = RAB()
    R["spec"]["intents"].append({"id": "x_tp", "keywords": ["\\bmanager\\b"], "scope": ["tp"], "precedence": 30,
                                 "action": {"kind": "transfer", "say": "Transferring.", "queue": "general",
                                            "situation": "S_HUMAN_TRANSFER"}})
    st, w = turn(R, tp_state(R), "Can I talk to a manager?")
    assert st["ph"] == "TP" and w["nx"] == "s_tp"
    assert "Transferring" not in w["say"] and not st.get("xfer")
    assert w["say"].endswith("when I could reach Ms Almeida?")


def test_tp_parser_crash_is_treated_as_no_time(monkeypatch):
    R = RAB()
    st0 = tp_state(R)

    def boom(*a, **k):
        raise ValueError("parser")
    monkeypatch.setattr(brain, "parse_day_and_time", boom)
    st, w = turn(R, st0, "ok then")
    assert w["nx"] == "s_tp" and st["tp"]["idle"] == 1 and "dbg_err" not in w


def test_tp_grounded_u_time_with_day_books_that_day():
    R = RAB()
    st, w = turn(R, tp_state(R), "Tomorrow at 3pm, sorry I mean, whenever", u_time="tomorrow at 3pm")
    assert st["cb"] == {"d": "2026-10-15", "t": 900, "try": 0}
    assert w["nx"] == "a_cb_1" and w["b_a_cb_1_date"] == "2026-10-15" and w["b_a_cb_1_time"] == "15:00"
    assert w["wn_a_cb_1"] == "s_bye" and w["r_a_cb_1_s"] == "pending"
    assert "Thursday, 15 October at 15:00" in w["say"] and w["say"].endswith("Goodbye.")
    assert (w["co"], w["cr"]) == ("not_reached", "callback")


def test_tp_grounded_u_time_outside_window_is_outside():
    R = RAB()
    st, w = turn(R, tp_state(R), "Call at 9am tomorrow, sorry I mean tomorrow", u_time="9am")
    # the day can still hold a callback, so it is kept for a following time-only answer (C4 follow-up)
    assert st["tp"]["outside"] == 1 and st["tp"]["d"] == "2026-10-15"
    assert w["say"].startswith("I'm sorry, I can only arrange a call back")


def test_tp_u_time_reparse_crash_is_ignored(monkeypatch):
    R = RAB()
    st0 = tp_state(R)
    real = brain.parse_day_and_time
    calls = []

    def second_boom(text, *a):
        calls.append(text)
        if len(calls) == 2:
            raise ValueError("boom")
        return real(text, *a)
    monkeypatch.setattr(brain, "parse_day_and_time", second_boom)
    st, w = turn(R, st0, "ok then", u_time="ok then")
    assert len(calls) == 2 and w["nx"] == "s_tp" and "cb" not in st


def test_tp_callback_check_crash_skips_candidate_then_outside(monkeypatch):
    R = RAB()
    st0 = tp_state(R)

    def boom(*a, **k):
        raise ValueError("cal")
    monkeypatch.setattr(brain, "callback_check", boom)
    st, w = turn(R, st0, "Tomorrow at 3pm.")
    assert "cb" not in st and st["tp"]["outside"] == 1


def test_tp_past_day_with_part_of_day_is_outside():
    R = RAB()
    st, w = turn(R, tp_state(R), "yesterday afternoon")
    assert st["tp"]["outside"] == 1 and st["tp"]["d"] == ""
    assert w["say"].startswith("I'm sorry, I can only arrange a call back")


def test_tp_turn_budget_closes_no_callback_on_vague_and_on_idle_turns():
    R = RAB()
    st0 = tp_state(R)
    st0["tp"]["turns"] = 5
    for text in ("sometime later", "ok"):
        st, w = turn(R, json.loads(json.dumps(st0)), text)
        assert st["csit"] == "S_NO_CALLBACK" and w["nx"] == "s_bye"
        assert (w["co"], w["cr"]) == ("not_reached", "no_callback")
        assert w["say"] == "Thank you for your time. Goodbye."


def test_tp_part_of_day_asked_twice_then_outside():
    R = RAB()
    st = tp_state(R)
    st, w = turn(R, st, "tomorrow afternoon")
    assert w["say"] == "What time would be best to reach Ms Almeida?" and st["tp"]["tq"] == 1
    st, w = turn(R, st, "in the afternoon")
    assert w["say"] == "Could you give me an exact time?" and st["tp"]["tq"] == 2
    st, w = turn(R, st, "afternoon I said")
    assert st["tp"]["outside"] == 1 and w["nx"] == "s_tp"


def test_tp_vague_after_vague_line_with_known_day_asks_time_then_books():
    R = RAB()
    st = tp_state(R)
    st, w = turn(R, st, "sometime later")
    assert w["say"] == "Could you tell me the exact day and time?"
    st, w = turn(R, st, "tomorrow sometime later")
    assert w["say"] == "What time would be best to reach Ms Almeida?" and st["tp"]["tq"] == 1
    st, w = turn(R, st, "at 3pm")
    assert st["cb"]["t"] == 900 and w["nx"] == "a_cb_1"


def test_tp_second_vague_without_a_day_counts_as_outside():
    R = RAB()
    st = tp_state(R)
    st, _w = turn(R, st, "sometime later")
    st, w = turn(R, st, "sometime later")
    assert st["tp"]["outside"] == 1 and w["say"].startswith("I'm sorry, I can only arrange")


def test_tp_vague_after_time_ask_counts_as_outside_then_closes():
    R = RAB()
    st = tp_state(R)
    st, _ = turn(R, st, "sometime later")
    st, _ = turn(R, st, "tomorrow sometime later")
    st, w = turn(R, st, "sometime later")
    assert st["tp"]["outside"] == 1 and w["nx"] == "s_tp"
    st, w = turn(R, st, "sometime later")
    assert st["csit"] == "S_NO_CALLBACK" and w["nx"] == "s_bye"


def test_tp_vague_answer_about_rejected_day_counts_as_outside():
    R = RAB()
    st = tp_state(R)
    st, _ = turn(R, st, "sometime later")
    st, _ = turn(R, st, "next Monday")          # not a callback day -> outside #1, the day stays remembered
    assert st["tp"]["outside"] == 1
    st, w = turn(R, st, "sometime later")      # vague again: must count as outside #2 -> no_callback
    assert st.get("csit") == "S_NO_CALLBACK"


def test_tp_why_question_on_later_turn_gets_why_answer():
    R = RAB()
    st, w = turn(R, tp_state(R), "Why do you want her?")
    assert w["say"] == ("I can only explain that to Ms Almeida. Is there another time today or on the next "
                        "business day, between 10:00 and 19:00, when I could reach Ms Almeida?")
    assert st["tp"]["idle"] == 0


def test_tp_two_idle_turns_close_no_callback():
    R = RAB()
    st, w = turn(R, tp_state(R), "ok")
    assert st["tp"]["idle"] == 1 and w["nx"] == "s_tp"
    st, w = turn(R, st, "ok")
    assert st["csit"] == "S_NO_CALLBACK" and w["nx"] == "s_bye"


def test_tp_slot_check_crash_assumes_slot_ok(monkeypatch):
    R = RAB()
    c = ctx(R, {"ph": "TP"})

    def boom(*a, **k):
        raise ValueError("x")
    monkeypatch.setattr(brain, "callback_check", boom)
    import datetime
    assert brain._b_tp_slot_ok(c, datetime.date(2026, 10, 15), "morning") is True


def test_tp_book_without_callback_nodes_closes_no_callback():
    R = RAB()
    R["wiring"]["api"]["cb"] = []
    st, w = turn(R, tp_state(R), "Tomorrow at 3pm.")
    assert st["cb"]["failed"] == 1 and st["csit"] == "S_NO_CALLBACK"
    assert w["nx"] == "s_bye" and (w["co"], w["cr"]) == ("not_reached", "no_callback")
    assert "We will call back" not in w["say"]


def test_tp_grounded_u_time_without_exact_time_is_not_booked():
    R = RAB()
    st, w = turn(R, tp_state(R), "In the afternoon, sorry I mean, whenever", u_time="in the afternoon")
    assert "cb" not in st and w["nx"] == "s_tp" and st["ph"] == "TP"


# ======================================================================= identity
def id_state(R, qi=0):
    st, w = turn(R, {}, "Yes, speaking.")
    assert st["ph"] == "ID" and w["nx"] == "s_id"
    st["id"]["qi"] = qi
    return st


def sent_state(R, answer="14 March 1988", qi=0):
    st, w = turn(R, id_state(R, qi), answer)
    assert w["nx"].startswith("a_verify_"), w
    return st, w


def vres(node="a_verify_1", **kw):
    r = {"s": "true", "err": "pending", "verified": "true", "left": "3", "all": "false", "hint": "pending"}
    r.update(kw)
    return {node: r}


def alnum_spec(length=6, pattern="^[A-Z0-9]{6}$"):
    R = RAB()
    q = R["spec"]["identity"]["questions"][1]
    q.update({"key": "code", "kind": "alnum", "wire_format": "upper_nospace", "length": length, "pattern": pattern,
              "ask": "What is your customer code?", "ask_full": "Could you give me the full customer code?"})
    return R


def test_id_without_questions_goes_straight_to_account():
    R = RAB()
    R["spec"]["identity"]["questions"] = []
    st, w = turn(R, {}, "Yes, speaking.")
    assert st["ph"] == "ACCT" and w["nx"] == "a_acct_1" and w["r_a_acct_1_s"] == "pending"
    assert st["acct_try"] == 1


def test_qre_prefers_spec_reask_else_strips_thank_you():
    R = RAB()
    c = ctx(R, {"ph": "ID"})
    assert brain._b_qre(c, {"reask": "Your date of birth, please?", "ask": "x"}) == "Your date of birth, please?"
    assert brain._b_qre(c, {"ask": "Thank you. What are the last four digits?"}) == "What are the last four digits?"


def test_id_turn_past_last_question_goes_to_account():
    R = RAB()
    st, w = turn(R, id_state(R, qi=5), "whatever")
    assert w["nx"] == "a_acct_1" and st["ph"] == "ACCT"


def test_id_unhandled_action_intent_falls_through_to_the_answer():
    R = RAB()
    R["spec"]["intents"].append({"id": "x_id", "keywords": ["\\bzebra\\b"], "scope": ["id"], "precedence": 30,
                                 "action": {"kind": "resolve_product", "say": "Noted.", "situation": "S_DISPUTE"}})
    st, w = turn(R, id_state(R), "zebra, 14 March 1988")
    assert w["nx"] == "a_verify_1" and w["b_a_verify_1_answer"] == "1988-03-14"
    assert w["b_a_verify_1_field"] == "date_of_birth" and "Noted" not in json.dumps(st.get("carry"))


def test_id_help_question_then_insist_without_human_intent_resumes_identity():
    R = RAB()
    R["spec"]["intents"] = [it for it in R["spec"]["intents"] if it["id"] != "human"]
    st = id_state(R)
    st["help"] = 1
    st, w = turn(R, st, "No.", act="no")
    assert st["ph"] == "ID" and w["nx"] == "s_id" and not st.get("xfer")
    assert w["say"] == "Before we continue, could you please tell me your date of birth?"


def test_id_turn_budget_closes_declined_without_fail_line():
    R = RAB()
    st = id_state(R)
    st["id"]["turns"] = 12
    st, w = turn(R, st, "hmm")
    assert st["csit"] == "S_ID_DECLINED" and w["nx"] == "s_bye"
    assert (w["co"], w["cr"]) == ("not_verified", "declined")
    assert "could not verify" not in w["say"] and w["say"] == "Thank you for your time. Goodbye."


def test_id_post_intent_with_existing_stash_keeps_first_and_acknowledges():
    R = RAB()
    st = id_state(R)
    st["stash"] = "dispute"
    st, w = turn(R, st, "I lost my job.")
    assert st["stash"] == "dispute"
    assert w["say"] == "I understand. Before we continue, could you please tell me your date of birth?"


def test_id_alnum_code_with_digits_is_sent():
    R = alnum_spec()
    st, w = turn(R, id_state(R, qi=1), "AB12CD")
    assert w["nx"] == "a_verify_1" and w["b_a_verify_1_answer"] == "AB12CD"


def test_id_alnum_letters_only_matching_pattern_and_length_is_sent():
    R = alnum_spec()
    st, w = turn(R, id_state(R, qi=1), "a b c d e f")
    assert w["nx"] == "a_verify_1" and w["b_a_verify_1_answer"] == "ABCDEF"


def test_id_alnum_spelled_letters_without_digits_or_pattern_are_not_a_code():
    R = alnum_spec(length=0, pattern="")
    st, w = turn(R, id_state(R, qi=1), "a b c")
    assert w["nx"] == "s_id" and "sent" not in st["id"]
    assert w["say"] == "What is your customer code?"


def test_id_alnum_refusal_is_a_decline_not_an_answer():
    R = alnum_spec()
    st, w = turn(R, id_state(R, qi=1), "I won't tell you")
    assert w["nx"] == "s_id" and st["id"]["dec"]["code"] == 1
    assert w["say"] == "These questions protect your account. What is your customer code?"


def test_id_text_question_answer_is_sent_verbatim():
    R = RAB()
    q = R["spec"]["identity"]["questions"][1]
    q.update({"key": "maiden", "kind": "text", "length": 0, "pattern": "", "ask": "What is your mother's maiden name?"})
    st, w = turn(R, id_state(R, qi=1), "Smith.")
    assert w["nx"] == "a_verify_1" and w["b_a_verify_1_answer"] == "Smith"


def test_id_ungrounded_u_ans_is_ignored_and_grounded_unparseable_reasks():
    R = RAB()
    st, w = turn(R, id_state(R), "blah blah", u_ans="blah blah")
    assert w["nx"] == "s_id" and "sent" not in st["id"]
    assert w["say"] == "Before we continue, could you please tell me your date of birth?"


def test_id_answer_with_purpose_question_carries_explanation_to_next_line():
    R = RAB()
    st, w = sent_state(R, "Why do you need that? It's 14 March 1988")
    assert st["carry"] == ["These questions protect your account."]
    st, w = result(R, st, vres())
    assert w["say"] == ("These questions protect your account. Thank you. What are the last four digits of the "
                        "phone number on file?")


def test_id_who_question_gets_who_answer_and_exact_reask():
    R = RAB()
    st, w = turn(R, id_state(R), "Who are you?")
    assert w["say"] == ("I am Freya Bank's digital assistant. Before we continue, could you please tell me your "
                        "date of birth?")
    assert st["id"]["dec"] == {}


def test_id_decline_counting_total_spans_questions():
    R = RAB()
    R["spec"]["interpretation"]["decline_counting"] = "total"
    st = id_state(R)
    st, w = turn(R, st, "No.")
    assert st["id"]["dec"] == {"_all": 1} and w["nx"] == "s_id"
    st["id"]["qi"] = 1
    st, w = turn(R, st, "No.")
    assert st["csit"] == "S_ID_DECLINED" and w["nx"] == "s_bye"


def test_id_explanation_is_given_only_explain_times():
    R = RAB()
    R["spec"]["identity"]["decline"]["max_declines"] = 3
    st = id_state(R)
    st, w = turn(R, st, "No.")
    assert w["say"].startswith("These questions protect your account.")
    st, w = turn(R, st, "No.")
    assert w["say"] == "Before we continue, could you please tell me your date of birth?"
    assert st["id"]["dec"]["dob"] == 2 and st["id"]["expl"] == 1
    st, w = turn(R, st, "No.")
    assert st["csit"] == "S_ID_DECLINED"


def test_id_verify_nodes_exhausted_fails_identity():
    R = RAB()
    st = id_state(R)
    st["id"]["vi"] = len(R["wiring"]["api"]["verify"])
    st, w = turn(R, st, "14 March 1988")
    assert st["csit"] == "S_ID_FAILED" and w["nx"] == "s_bye"
    assert w["say"].startswith("I'm sorry, I could not verify your identity.")
    assert (w["co"], w["cr"]) == ("not_verified", "failed")


def test_on_verify_with_no_current_question_goes_to_account():
    R = RAB()
    st, _w = sent_state(R)
    st["id"]["qi"] = 9
    st, w = result(R, st, vres())
    assert w["nx"] == "a_acct_1"


def test_verify_transport_failure_twice_closes_with_service_error():
    R = RAB()
    st, _w = sent_state(R)
    st, w = result(R, st, {"a_verify_1": fail_res()})
    assert w["nx"] == "a_verify_2" and w["b_a_verify_2_answer"] == "1988-03-14"
    st, w = result(R, st, {"a_verify_2": fail_res()})
    assert st["csit"] == "S_SERVICE_ERROR" and w["nx"] == "s_bye"
    assert w["say"].startswith("I'm sorry, I can't access the account details right now.")
    assert (w["co"], w["cr"]) == ("no_promise", "service_error")


def test_verified_last_question_without_all_flag_goes_to_account():
    R = RAB()
    st, _w = sent_state(R, "4471", qi=1)
    st, w = result(R, st, vres(all="false"))
    assert st["id"]["ver"] == ["phone"] and w["nx"] == "a_acct_1"


def hint_spec(**h):
    R = RAB()
    hints = [{"value": "other_hint", "counts_as_wrong": False, "say": "Other hint.", "max": 1}]
    base = {"value": "day_month_swapped", "counts_as_wrong": False,
            "say": "Could you say the month of your date of birth as a word, please?", "max": 1}
    base.update(h)
    R["spec"]["identity"]["hints"] = [base] + hints
    return R


def test_hint_counting_as_wrong_fails_at_the_wrong_limit():
    R = hint_spec(counts_as_wrong=True, max=5)
    st, _w = sent_state(R)
    st["id"]["wrong"] = 1
    st, w = result(R, st, vres(verified="false", hint="day_month_swapped", left="2"))
    assert st["id"]["wrong"] == 2 and w["say"] == "Could you say the month of your date of birth as a word, please?"
    st, w = turn(R, st, "the 15th of March 1988")
    assert w["nx"] == "a_verify_2"
    st, w = result(R, st, vres("a_verify_2", verified="false", hint="day_month_swapped", left="1"))
    assert st["csit"] == "S_ID_FAILED" and w["nx"] == "s_bye"


def test_hint_repeated_past_max_says_hint_again_and_is_not_wrong():
    R = hint_spec()
    st, _w = sent_state(R)
    st, w = result(R, st, vres(verified="false", hint="day_month_swapped"))
    assert st["id"]["hints"] == {"day_month_swapped": 1}
    st, w = turn(R, st, "the 15th of March 1988")
    assert w["nx"] == "a_verify_2"
    st, w = result(R, st, vres("a_verify_2", verified="false", hint="day_month_swapped"))
    assert st["id"]["wrong"] == 0 and w["nx"] == "s_id"
    assert w["say"] == "Could you say the month of your date of birth as a word, please?"


def test_unknown_hint_value_reasks_full_question():
    R = hint_spec()
    st, _w = sent_state(R)
    st, w = result(R, st, vres(verified="false", hint="mystery"))
    assert w["say"] == "Could you tell me your full date of birth, with the day, the month and the year?"
    assert st["id"]["wrong"] == 0


def test_wrong_answers_reach_total_limit_and_fail():
    R = RAB()
    st, _w = sent_state(R)
    st["id"]["wrong"] = 2
    st, w = result(R, st, vres(verified="false", left="1"))
    assert st["id"]["wrong"] == 3 and st["csit"] == "S_ID_FAILED" and w["nx"] == "s_bye"


def test_wrong_answer_below_limit_reasks_wrong_line():
    R = RAB()
    st, _w = sent_state(R)
    st, w = result(R, st, vres(verified="false", left="2"))
    assert w["say"] == "That does not match our records. Could you tell me your date of birth again?"
    assert st["id"]["wq"] == {"dob": 1}


def test_unreadable_answer_reasks_full_and_counts_nothing():
    R = RAB()
    st, _w = sent_state(R)
    st, w = result(R, st, vres(s="false", verified="pending", err="invalid date format", left="3"))
    assert w["say"] == "Could you tell me your full date of birth, with the day, the month and the year?"
    assert st["id"]["wrong"] == 0 and w["nx"] == "s_id"


# ======================================================================= account / statement / dates
def acct_state(R):
    st, _w = sent_state(R, "4471", qi=1)
    st, w = result(R, st, vres(all="true"))
    assert w["nx"] == "a_acct_1" and st["ph"] == "ACCT"
    return st


def acct_res(products, s="true", node="a_acct_1"):
    return {node: {"s": s, "err": "pending", "products": json.dumps(products) if not isinstance(products, str)
                   else products}}


def test_account_unreadable_or_empty_product_list_closes_with_service_error():
    R = RAB()
    for raw in ("garbage{", "[]"):
        st, w = result(R, acct_state(R), acct_res(raw))
        assert st["csit"] == "S_SERVICE_ERROR" and w["nx"] == "s_bye"
        assert w["say"] == ("I'm sorry, I can't access the account details right now. Thank you for your time. "
                            "Goodbye.")
        assert (w["co"], w["cr"]) == ("no_promise", "service_error")


def test_account_failure_retries_on_second_node_then_service_error():
    R = RAB()
    st, w = result(R, acct_state(R), acct_res("[]", s="false"))
    assert w["nx"] == "a_acct_2" and st["acct_try"] == 2
    st, w = result(R, st, acct_res("[]", s="false", node="a_acct_2"))
    assert st["csit"] == "S_SERVICE_ERROR" and w["nx"] == "s_bye"


def test_statement_with_stashed_transfer_intent_transfers_after_statement():
    R = RAB()
    st = acct_state(R)
    st["stash"] = "restructure"
    st, w = result(R, st, acct_res(items_of("PUB-13")))
    assert w["nx"] == "a_xfer_1" and w["b_a_xfer_1_queue"] == "restructuring" and w["wn_a_xfer_1"] == "s_bye"
    assert "Your personal loan is 20 days late, with 900 past due." in w["say"]
    assert "I will transfer you to our restructuring team." in w["say"]
    assert (w["co"], w["cr"]) == ("transferred", "restructuring")
    assert not any(k.startswith("b_a_note") for k in w)


def test_statement_with_unknown_stash_id_asks_first_question():
    R = RAB()
    st = acct_state(R)
    st["stash"] = "no_such_intent"
    st, w = result(R, st, acct_res(items_of("PUB-13")))
    assert w["nx"] == "s_neg" and w["say"].endswith("Can you pay all of them today?")
    assert "stash" not in st


def test_band_nearest_and_default():
    R = RAB()
    c = ctx(R)
    assert brain._b_band(c, 60)["key"] == "late"
    assert brain._b_band(c, 0)["key"] == "early"
    c["S"]["bands"] = []
    assert brain._b_band(c, 5) == {"key": "", "attempts": 1, "deadline": {"kind": "today"}}


def test_build_prods_missing_floor_field_uses_full_amount():
    R = RAB()
    c = ctx(R)
    p = brain._b_build_prods(c, [{"product_id": "x", "type": "credit_card", "past_due": 300.0, "days_late": 4}])[0]
    assert p["floor"] == 30000 and p["due"] == 30000 and p["band"] == "early"


def test_build_prods_deadline_crash_falls_back_to_today(monkeypatch):
    R = RAB()
    c = ctx(R)

    def boom(*a, **k):
        raise ValueError("x")
    monkeypatch.setattr(brain, "eval_date_rule", boom)
    p = brain._b_build_prods(c, items_of("PUB-01"))[0]
    assert p["dead"] == "2026-10-14"


def _prod(c, cid="PUB-13", j=0):
    return brain._b_build_prods(c, items_of(cid))[j]


def test_bounds_and_rung_date_survive_rule_crash(monkeypatch):
    R = RAB()
    c = ctx(R)
    p = _prod(c)

    def boom(*a, **k):
        raise ValueError("x")
    monkeypatch.setattr(brain, "eval_date_rule", boom)
    import datetime
    assert brain._b_bounds(c, p) == (datetime.date(2026, 10, 14), datetime.date.fromisoformat(p["dead"]))
    assert brain._b_valid_rung_date(c, {"kind": "today"}, p) == p["dead"]


def test_rung_date_is_clamped_into_promise_window():
    R = RAB()
    c = ctx(R)
    p = _prod(c)                                           # early band, deadline 2026-11-02
    assert brain._b_valid_rung_date(c, {"kind": "fixed", "date": "2026-12-01"}, p) == p["dead"]
    assert brain._b_valid_rung_date(c, {"kind": "fixed", "date": "2026-10-01"}, p) == "2026-10-14"
    assert brain._b_valid_rung_date(c, {"kind": "fixed", "date": "2026-10-17"}, p) == "2026-10-19"


def test_rung_date_on_weekend_kept_when_business_days_not_required():
    R = RAB()
    R["spec"]["promise_date"]["business_day_only"] = False
    c = ctx(R)
    assert brain._b_valid_rung_date(c, {"kind": "fixed", "date": "2026-10-17"}, _prod(c)) == "2026-10-17"


def test_rung_date_without_business_day_in_window_keeps_window_day():
    R = RAB()
    R["spec"]["promise_date"]["earliest"] = {"kind": "fixed", "date": "2026-10-17"}
    c = ctx(R)
    p = _prod(c)
    p["dead"] = "2026-10-17"                                # window = Saturday only
    assert brain._b_valid_rung_date(c, {"kind": "today"}, p) == "2026-10-17"


def test_rung_date_business_day_check_crash_keeps_date(monkeypatch):
    R = RAB()
    c = ctx(R)

    def boom(*a, **k):
        raise ValueError("x")
    monkeypatch.setattr(brain, "is_bd", boom)
    assert brain._b_valid_rung_date(c, {"kind": "fixed", "date": "2026-10-17"}, _prod(c)) == "2026-10-17"


def test_attempt1_date_without_matching_rung_is_deadline():
    R = RAB()
    R["spec"]["negotiation"]["ladder"][0]["bands"] = ["late"]
    c = ctx(R)
    p = _prod(c)                                            # early band
    assert brain._b_attempt1_date(c, p) == brain._b_valid_rung_date(c, {"kind": "deadline"}, p) == p["dead"]


def test_build_prods_unknown_type_owes_full_amount_and_is_spoken_generically():
    R = RAB()
    c = ctx(R)
    p = brain._b_build_prods(c, [{"product_id": "x", "type": "mortgage", "past_due": 300.0, "days_late": 4}])[0]
    assert p["floor"] == 30000 and brain._b_pname(c, p) == "account"


def test_statement_with_stash_of_non_post_intent_asks_first_question():
    R = RAB()
    st = acct_state(R)
    st["stash"] = "robot"
    st, w = result(R, st, acct_res(items_of("PUB-13")))
    assert w["nx"] == "s_neg" and w["say"].endswith("Can you pay all of them today?")


# ======================================================================= dispatch / finish / errors / main
def test_customer_turn_while_waiting_for_account_resends_account_read():
    R = RAB()
    st, w = turn(R, {"ph": "ACCT", "await": "", "turns": 3}, "hello?")
    assert w["nx"] == "a_acct_1" and st["acct_try"] == 1 and w["r_a_acct_1_s"] == "pending"


def test_listen_bye_mode_closes_on_next_turn_with_reason_or_without():
    R = RAB()
    R["wiring"]["bye_mode"] = "listen"
    st, w = turn(R, {"ph": "BYE", "await": "s_bye", "csit": "S_UNCLEAR", "turns": 3}, "bye")
    assert w["nx"] == "a_close_r" and st["ph"] == "CLOSE" and (w["co"], w["cr"], w["cmode"]) == (
        "not_reached", "unclear", "r")
    prods = [{"id": "p1", "rec": 1, "sit": "", "ag": [100, "2026-10-14"]}]
    st, w = turn(R, {"ph": "BYE", "await": "s_bye", "prods": prods, "turns": 3}, "bye")
    assert w["nx"] == "a_close_n" and (w["co"], w["cr"], w["cmode"]) == ("promise", "", "n")


def test_customer_turn_in_terminal_phase_without_plan_closes():
    R = RAB()
    st, w = turn(R, {"ph": "XFER", "await": "s_safe", "csit": "S_UNCLEAR", "turns": 3}, "hello?")
    assert w["nx"] == "s_bye" and st["ph"] == "BYE"
    assert w["say"] == "Thank you for your time. Goodbye." and (w["co"], w["cr"]) == ("not_reached", "unclear")


def test_result_of_unlisted_verify_node_is_classified_by_tool():
    R = RAB()
    st, _w = sent_state(R)
    R["wiring"]["api"]["verify"] = ["a_verify_9"]
    st, w = result(R, st, vres())
    assert st["id"]["ver"] == ["dob"] and w["say"] == "Thank you. What are the last four digits of the phone number on file?"


def test_result_of_unlisted_account_node_is_classified_by_role():
    R = RAB()
    st = acct_state(R)
    R["wiring"]["api"]["acct"] = ["a_acct_9"]
    st, w = result(R, st, acct_res(items_of("PUB-13")))
    assert w["nx"] == "s_neg" and len(st["prods"]) == 2


def test_result_of_other_node_without_plan_closes():
    R = RAB()
    st = {"ph": "NOTES", "await": "a_note_1", "csit": "S_UNCLEAR", "turns": 3}
    st, w = result(R, st, {"a_note_1": {"s": "true", "err": "pending"}})
    assert w["nx"] == "s_bye" and st["ph"] == "BYE"


def test_finish_without_next_node_goes_to_safe_listen():
    R = RAB()
    c = ctx(R, {"ph": "NEG"})
    st, w = brain._b_finish(c)
    assert w["nx"] == "s_safe" and w["u_act"] == "unclear" and w["u_topic"] == "none" and w["u_text"] == ""
    assert w["dbg_step"] == "ok:NEG:s_safe"


def test_second_consecutive_error_whose_close_also_fails_falls_back_to_listen():
    R = RAB()
    bad = {"call": call_vars(), "sensors": "not a dict", "results": {}, "entered_from": ""}
    st, w = brain.step(R, {"ph": "NEG", "await": "s_neg", "errs": 1, "turns": 3}, bad)
    assert st["errs"] == 2 and w["nx"] == "s_neg" and w["dbg_step"] == "error"
    assert w["say"] == "Sorry, could you say that again?" and w["dbg_err"]
    assert w["u_act"] == "unclear" and w["u_text"] == ""


def test_main_skips_declared_variables_without_name():
    R = RAB()
    R["spec"]["call_variables"]["declared"].append({"meaning": "unnamed"})
    vars_ = dict(call_vars())
    vars_.update({"u_text": "Yes, speaking.", "u_act": "yes"})
    brain.main(vars_, R)
    assert vars_["nx"] == "s_id" and vars_["ph"] == "ID"
    assert vars_["say"] == "Before we continue, could you please tell me your date of birth?"


def test_main_never_raises_on_unwritable_vars():
    assert brain.main(None, RAB()) is None

    class Picky(dict):
        def __setitem__(self, k, v):
            if k == "dbg_err":
                raise KeyError(k)
            dict.__setitem__(self, k, v)
    v = Picky()
    brain.main(v, "zz-not-hex")
    assert v["nx"] == "s_safe" and v["dbg_step"] == "start" and "dbg_err" not in v
