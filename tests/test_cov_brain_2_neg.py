"""Coverage + behaviour tests for runtime/brain.py negotiation (C.6): value parsing, product mentions, proposals,
ladder, too_much / floor, transfer offers, resolve_product, human help question, confirmation and read-back.
Helpers come from tests/test_cov_brain_2.py (same owner)."""
import json

import pytest

from runtime import brain
from test_cov_brain_2 import RA, RAB, ctx, neg_state, turn, id_state


def run(R, st, texts, cid="PUB-11", **kw):
    w = None
    for t in texts:
        st, w = turn(R, st, t, cid=cid, **kw)
    return st, w


def at_neg(R, cid="PUB-11", texts=()):
    return run(R, neg_state(R, cid), texts, cid)


def ag(st):
    return [p.get("ag") for p in st["prods"]]


def sits(st):
    return [p.get("sit") for p in st["prods"]]


def neg_ctx(R, st, text, cid="PUB-11", **kw):
    return ctx(R, json.loads(json.dumps(st)), text, cid=cid, **kw)


# ======================================================================= product mentions
def test_mentions_by_unique_last_word():
    R = RAB()
    c = neg_ctx(R, neg_state(R), "")
    assert brain._b_mentions(c, "I'll pay the card tomorrow") == [0]
    assert brain._b_mentions(c, "the loan") == []          # 'loan' is shared by two products
    st, w = turn(R, neg_state(R), "I can pay the card tomorrow")
    assert ag(st)[0] == [22000, "2026-10-15"]
    assert w["say"] == "For your personal loan: Could you pay 640 by Friday, 16 October?"


def test_mentions_untyped_product_and_unnamed_product():
    R = RAB()
    st = neg_state(R)
    st["prods"][1]["type"] = ""                                       # spoken as unknown_type_spoken 'account'
    c = neg_ctx(R, st, "")
    assert brain._b_mentions(c, "the account") == [1]
    R["spec"]["products"]["unknown_type_spoken"] = ""
    c = neg_ctx(R, st, "")
    assert brain._b_mentions(c, "the account") == []


# ======================================================================= value parsing
def test_values_survive_parser_crashes(monkeypatch):
    R = RAB()
    c = neg_ctx(R, neg_state(R), "Yes, I can pay 100 tomorrow?")

    def boom(*a, **k):
        raise ValueError("x")
    for name in ("parse_amount", "parse_date", "yes_no", "is_question"):
        monkeypatch.setattr(brain, name, boom)
    v = brain._b_values(c)
    assert v["amt"] is None and v["date"] is None and v["dk"] == "" and v["yn"] == {} and v["zero"] is False


def test_isq_survives_question_parser_crash(monkeypatch):
    R = RAB()
    c = neg_ctx(R, neg_state(R), "hmm")

    def boom(*a, **k):
        raise ValueError("x")
    monkeypatch.setattr(brain, "is_question", boom)
    assert brain._b_isq(c) is False
    c["act"] = "question"
    assert brain._b_isq(c) is True


def test_values_use_grounded_slots_only_when_text_has_no_value():
    R = RA()
    st = neg_state(R, "PUB-01")
    v = brain._b_values(neg_ctx(R, st, "I can pay 200, sorry I mean, whatever", "PUB-01", u_amt="200"))
    assert v["amt"] == 20000
    v = brain._b_values(neg_ctx(R, st, "nothing, sorry I mean, whatever", "PUB-01", u_amt="nothing"))
    assert v["amt"] is None
    v = brain._b_values(neg_ctx(R, st, "tomorrow, sorry I mean, whatever", "PUB-01", u_date="tomorrow"))
    assert (v["dk"], v["date"]) == ("date", "2026-10-15")
    v = brain._b_values(neg_ctx(R, st, "whatever, sorry I mean, whatever", "PUB-01", u_date="whatever"))
    assert v["dk"] == "" and v["date"] is None
    v = brain._b_values(neg_ctx(R, st, "I can pay 200, sorry I mean, whatever", "PUB-01", u_amt="350"))
    assert v["amt"] is None                                 # a slot not grounded in the text is never used


def test_values_product_count_is_not_an_amount():
    R = RAB()
    st = neg_state(R)
    v = brain._b_values(neg_ctx(R, st, "I can pay all three on Friday"))
    assert v["amt"] is None and v["all"] is True and v["date"] == "2026-10-16"
    v = brain._b_values(neg_ctx(R, st, "I can pay 5 for all three on Friday"))
    assert v["amt"] == 500


def test_clause_mentions_single_clause_and_repeated_product():
    R = RAB()
    st = neg_state(R)
    v = brain._b_values(neg_ctx(R, st, "the card and the car loan tomorrow"))
    assert v["prods"] == [0, 2]
    v = brain._b_values(neg_ctx(R, st, "I'll pay the card today, but the card again tomorrow"))
    assert v["prods"] == [0]


def test_clause_mentions_parse_crash_falls_back_to_all_mentions(monkeypatch):
    R = RAB()
    c = neg_ctx(R, neg_state(R), "I'll pay the card tomorrow, but not the car loan")

    def boom(*a, **k):
        raise ValueError("x")
    monkeypatch.setattr(brain, "parse_amount", boom)
    v = brain._b_values(c)
    assert v["date"] == "2026-10-15" and v["prods"] == [0, 2]


def test_question_about_named_product_answers_that_product_only():
    R = RAB()
    st, w = turn(R, neg_state(R), "How much is the car loan?")
    assert w["say"] == "Your car loan is 3 days late, with 75 past due. Can you pay all of them today?"


# ======================================================================= proposals (C.6 step 3)
def test_below_floor_offer_without_ack_prefix_in_floor_line():
    R = RA()
    R["spec"]["lines"]["floor_offer"] = "Could you pay <floor> by <date>?"
    st, w = turn(R, neg_state(R, "PUB-01"), "I can pay 50 today", cid="PUB-01")
    assert w["say"] == "I'm afraid I can't record an amount below 126. Could you pay 126 by Wednesday, 14 October?"
    assert st["offer"]["kind"] == "floor" and st["prods"][0]["fo"] == 1


def test_below_floor_twice_is_flat_refusal_to_next_rung():
    R = RA()
    st, w = at_neg(R, "PUB-01", ["I can pay 50 today", "I can pay 50 today"])
    assert st["offer"]["kind"] == "rung:r1" and w["say"] == "Could you pay 126 by Friday, 16 October?"
    st, w = turn(R, st, "no", cid="PUB-01")
    assert sits(st) == ["S_REFUSED_EXHAUSTED"] and w["nx"] == "s_bye"


def test_above_full_with_out_of_window_date_offers_full_on_pending_date():
    R = RA()
    st, w = turn(R, neg_state(R, "PUB-01"), "I can pay 500 on the 20th of December", cid="PUB-01")
    assert w["say"] == "The amount past due is 420. Shall I record 420?"
    assert st["offer"] == {"kind": "above_full", "k": 0, "amt": 42000, "date": "2026-10-14", "line": w["say"]}


def test_past_date_three_times_is_refusal():
    R = RA()
    st, w = at_neg(R, "PUB-01", ["On the 1st of October", "On the 2nd of October"])
    assert w["say"] == "That date has already passed. Which day would work for you?"
    st, w = turn(R, st, "on the 3rd of October", cid="PUB-01")
    assert st["offer"]["kind"] == "rung:r1" and st["prods"][0]["used"] == 1


def test_date_before_earliest_three_times_is_refusal():
    R = RA()
    R["spec"]["promise_date"]["earliest"] = {"kind": "next_business_day"}
    st = neg_state(R, "PUB-01")
    st, w = turn(R, st, "I can pay today", cid="PUB-01")
    assert w["say"] == "That date has already passed. Which day would work for you?"
    st["prods"][0]["pdc"] = 2
    st, w = turn(R, st, "I can pay today", cid="PUB-01")
    assert st["offer"]["kind"].startswith("rung:") and st["prods"][0]["used"] == 1


def test_vague_date_twice_offers_deadline():
    R = RA()
    st, w = turn(R, neg_state(R, "PUB-01"), "Sometime next month", cid="PUB-01")
    assert w["say"] == "Which exact day would work for you?" and st["offer"]["kind"] == "vague_ask"
    st, w = turn(R, st, "sometime next month", cid="PUB-01")
    assert w["say"] == "The latest date I can record is Monday, 2 November. Could you pay 420 by then?"
    assert st["offer"]["kind"] == "deadline" and st["prods"][0]["dlo"] == 1


def test_vague_answer_to_exact_day_ask_after_deadline_offer_is_refusal():
    R = RA()
    st = neg_state(R, "PUB-01")
    st, _w = turn(R, st, "Sometime next month", cid="PUB-01")
    st["prods"][0]["dlo"] = 1
    st, w = turn(R, st, "I don't know", cid="PUB-01")
    assert st["offer"]["kind"] == "rung:r1" and st["prods"][0]["used"] == 1


def test_weekend_date_refused_when_spec_says_refuse():
    R = RA()
    R["spec"]["promise_date"]["non_business_within_deadline"] = "refuse"
    st, w = turn(R, neg_state(R, "PUB-01"), "this Saturday", cid="PUB-01")
    assert st["offer"]["kind"] == "rung:r1" and "not a business day" not in w["say"]


def test_pick_rung_beyond_band_attempts_is_none():
    R = RAB()
    R["spec"]["negotiation"]["ladder"][1]["bands"] = ["all"]
    st = neg_state(R)
    c = neg_ctx(R, st, "")
    p = c["st"]["prods"][2]                                # early band: 1 attempt
    p["used"] = 1
    assert brain._b_pick_rung(c, p) is None


def test_cue_keeps_line_that_already_names_the_product():
    R = RAB()
    c = neg_ctx(R, neg_state(R), "")
    p = c["st"]["prods"][1]
    assert brain._b_cue(c, p, "Your personal loan: pay 640?") == "Your personal loan: pay 640?"
    assert brain._b_cue(c, p, "Pay 640?") == "For your personal loan: Pay 640?"


def test_refuse_without_current_product_and_nothing_open_closes():
    R = RAB()
    st = neg_state(R)
    for p in st["prods"]:
        p["sit"] = "S_DISPUTE"
    c = neg_ctx(R, st, "no")
    brain._b_refuse(c, [])
    assert c["st"]["ph"] in ("NOTES", "BYE") and c["nx"] == "a_note_1"


def test_refuse_of_already_refused_pair_and_resolved_product_moves_on():
    R = RAB()
    st = neg_state(R)
    st["offer"] = {"kind": "rung:r1", "k": 0, "amt": 22000, "date": "2026-10-16", "line": "x"}
    st["prods"][0]["ref"] = [[22000, "2026-10-16"]]
    st["prods"][0]["sit"] = "S_DISPUTE"
    c = neg_ctx(R, st, "no")
    brain._b_refuse(c, [])
    assert c["st"]["prods"][0]["ref"] == [[22000, "2026-10-16"]]
    assert c["st"]["offer"]["k"] == 1 and c["st"]["offer"]["kind"] == "rung:r1"


def test_refusal_repeating_the_pending_values_is_a_refusal_not_a_proposal():
    R = RAB()
    st = neg_state(R)
    st["offer"] = {"kind": "first_ask", "k": 0, "amt": None, "date": None, "line": "Can you pay it today?"}
    st, w = turn(R, st, "No, I can't pay 220 today")
    assert st["offer"]["kind"] == "rung:r1" and st["prods"][0]["used"] == 1 and ag(st)[0] is None
    assert w["say"] == "For your credit card ending 2288: Could you pay 220 by Friday, 16 October?"


def test_yes_to_combined_first_ask_agrees_all_products_today():
    R = RAB()
    st, w = turn(R, neg_state(R), "Yes")
    assert ag(st) == [[22000, "2026-10-14"], [64000, "2026-10-14"], [7500, "2026-10-14"]]
    assert w["nx"] == "s_conf" and w["say"].endswith("Do you confirm?")


def test_even_the_minimum_is_too_much_with_floor_pair_already_refused():
    R = RA()
    st = neg_state(R, "PUB-01")
    c = neg_ctx(R, st, "", "PUB-01")
    pair = [12600, brain._b_attempt1_date(c, c["st"]["prods"][0])]
    st["prods"][0]["ref"] = [pair]
    st, w = turn(R, st, "Even the minimum is too much", cid="PUB-01")
    assert st["prods"][0]["ref"].count(pair) == 1 and st["prods"][0]["fo"] == 1
    assert sits(st) == ["S_REFUSED_EXHAUSTED"]


def test_interjection_answer_without_value_repeats_pending_ask():
    R = RAB()
    st, w = turn(R, neg_state(R), "Are you a robot?")
    assert w["say"] == "I am Freya Bank's digital assistant. Can you pay all of them today?"
    assert st["offer"]["kind"] == "first_ask"


# ======================================================================= too_much (C.6 step 4)
def test_too_much_without_open_product_is_refusal():
    R = RAB()
    st = neg_state(R)
    for p in st["prods"]:
        p["sit"] = "S_DISPUTE"
    c = neg_ctx(R, st, "too much")
    brain._b_too_much(c, [], {"prods": [], "all": False}, c["st"]["offer"])
    assert c["nx"] == "a_note_1"


def test_too_much_floor_date_customer_else_pending():
    R = RA()
    R["spec"]["interpretation"]["floor_offer_date"] = "customer_else_pending_else_attempt_1"
    st, w = turn(R, neg_state(R, "PUB-01"), "That's too much for today", cid="PUB-01")
    assert st["offer"]["kind"] == "floor" and st["offer"]["date"] == "2026-10-14"
    assert w["say"] == "I understand. Could you pay 126 by Wednesday, 14 October? The rest stays overdue."
    st, w = turn(RA(), neg_state(RA(), "PUB-01"), "That's too much for today", cid="PUB-01")
    assert st["offer"]["date"] == "2026-10-16"             # default: the attempt-1 date


def test_too_much_floor_date_pending_mode_uses_pending_date():
    R = RA()
    R["spec"]["amounts"]["too_much"]["date"] = "pending"
    st = neg_state(R, "PUB-01")
    st, w = turn(R, st, "That's too much", cid="PUB-01")
    assert st["offer"]["kind"] == "floor" and st["offer"]["date"] == "2026-10-14"
    assert st["prods"][0]["ref"] == [[42000, "2026-10-14"]]


def test_too_much_pending_pair_already_refused_is_not_duplicated():
    R = RA()
    st = neg_state(R, "PUB-01")
    st["prods"][0]["ref"] = [[42000, "2026-10-14"]]
    st, w = turn(R, st, "That's too much", cid="PUB-01")
    assert st["prods"][0]["ref"] == [[42000, "2026-10-14"]] and st["offer"]["kind"] == "floor"


def test_too_much_after_floor_offer_is_flat_refusal():
    R = RA()
    st = neg_state(R, "PUB-01")
    st["prods"][0]["fo"] = 1
    st, w = turn(R, st, "That's too much", cid="PUB-01")
    assert st["offer"]["kind"] == "rung:r1" and st["prods"][0]["used"] == 1
    assert w["say"] == "Could you pay 126 by Friday, 16 October?"


# ======================================================================= multi-product proposals
def test_proposal_for_recorded_product_only_repeats_ask():
    R = RAB()
    st = neg_state(R)
    st["prods"][0]["rec"] = 1
    st, w = turn(R, st, "I can pay the card tomorrow")
    assert w["say"] == "Can you pay all of them today?" and st["offer"]["kind"] == "first_ask"
    assert ag(st) == [None, None, None]


def test_value_for_other_product_while_current_open_acknowledges_and_reasks():
    R = RAB()
    st, w = at_neg(R, "PUB-11", ["No", "I can pay the car loan tomorrow"])
    assert ag(st)[2] == [7500, "2026-10-15"] and st["offer"]["k"] == 0
    assert w["say"] == "I understand. Would that work for you?"


def test_one_low_amount_for_all_offers_floor_of_first_product_only():
    R = RAB()
    st, w = turn(R, neg_state(R), "I can pay 10 for all of them tomorrow")
    assert st["offer"]["kind"] == "floor" and st["offer"]["k"] == 0
    assert w["say"] == ("For your credit card ending 2288: I'm afraid I can't record an amount below 66. Could you "
                        "pay 66 by Thursday, 15 October?")


def test_floor_flag_set_only_for_the_product_whose_floor_was_offered():
    R = RAB()
    st, _w = turn(R, neg_state(R), "I can pay 10 for all of them tomorrow")
    assert [p["fo"] for p in st["prods"]] == [1, 0, 0]


# ======================================================================= intents in NEG / CONF
def add_intent(R, **it):
    base = {"scope": ["neg", "conf"], "precedence": 30, "product_scoped": False}
    base.update(it)
    R["spec"]["intents"].append(base)
    return R




def close_now_spec():
    return add_intent(RAB(), id="x_close", keywords=["\\bgoodbye forever\\b"], scope=["id", "neg", "conf"],
                      action={"kind": "close_now", "say": "Understood.", "situation": "S_REFUSED_TO_TALK"})


def test_close_now_intent_in_identity_closes_the_call():
    R = close_now_spec()
    st, w = turn(R, id_state(R), "goodbye forever")
    assert w["nx"] == "s_bye" and w["say"] == "Understood. Thank you for your time. Goodbye."


def test_close_now_intent_in_negotiation_closes_with_its_situation():
    R = close_now_spec()
    st, w = turn(R, neg_state(R), "goodbye forever")
    assert st["csit"] == "S_REFUSED_TO_TALK" and w["nx"] == "a_note_1"
    assert w["say"] == "Understood. Thank you for your time. Goodbye."
    assert (w["co"], w["cr"]) == ("no_promise", "refused")
    assert [w["b_a_note_%d_reason" % i] for i in (1, 2, 3)] == ["refused"] * 3


def test_unknown_action_kind_is_ignored_and_negotiation_continues():
    R = add_intent(RAB(), id="x_odd", keywords=["\\bbanana\\b"], action={"kind": "mystery", "say": "?"})
    st, w = turn(R, neg_state(R), "banana, no")
    assert st["offer"]["kind"] == "rung:r1" and st["prods"][0]["used"] == 1
    c = neg_ctx(R, neg_state(R), "banana")
    assert brain._b_dispatch_common(c, R["spec"]["intents"][-1], [], verified=True) is None


def test_transfer_without_dropping_unrecorded_agreement_keeps_it_when_spec_keeps():
    R = RAB()
    R["spec"]["interpretation"]["agreed_before_terminal"] = "keep"
    for it in R["spec"]["intents"]:
        if it["id"] == "restructure":
            it["action"]["drop_unrecorded"] = False
    st, w = at_neg(R, "PUB-11", ["Yes", "I want a payment plan"])
    assert ag(st)[0] == [22000, "2026-10-14"] and st["xfer"]["q"] == "restructuring"
    assert w["nx"] == "a_xfer_1"


def test_transfer_drops_unrecorded_agreement_by_default():
    R = RAB()
    st, w = at_neg(R, "PUB-11", ["Yes", "I want a payment plan"])
    assert ag(st) == [None, None, None] and w["nx"] == "a_xfer_1"
    assert w["say"] == "I will transfer you to our restructuring team. Thank you for your time. Goodbye."


def test_help_question_then_confirm_at_readback_records():
    R = RAB()
    st, w = at_neg(R, "PUB-11", ["Yes", "Can I talk to a human?"])
    assert st["offer"]["kind"] == "help_first" and st["ph"] == "CONF"
    st, w = turn(R, st, "Yes I confirm")
    assert w["nx"] == "a_promise_1_1" and st["ph"] == "WRITE"
    assert [w["b_a_promise_%d_1_amount" % i] for i in (1, 2, 3)] == ["220.00", "640.00", "75.00"]


def test_help_question_then_nothing_repeats_the_readback():
    R = RAB()
    st, w = at_neg(R, "PUB-11", ["Yes", "Can I talk to a human?", "hmm"])
    assert st["offer"]["kind"] == "readback" and st["ph"] == "CONF"
    assert w["say"].startswith("So that is 220") and w["say"].endswith("Do you confirm?")


def test_help_question_then_value_is_not_insisting():
    R = RAB()
    st, w = at_neg(R, "PUB-11", ["Can I talk to a human?", "I can pay 100 tomorrow"])
    assert not st.get("xfer") and ag(st)[0] == [10000, "2026-10-15"]
    assert st["offer"]["kind"] == "floor" and st["offer"]["k"] == 1


def test_help_question_insist_without_human_intent_resumes():
    R = RAB()
    R["spec"]["intents"] = [it for it in R["spec"]["intents"] if it["id"] != "human"]
    st = neg_state(R)
    st["saved"] = st["offer"]
    st["offer"] = {"kind": "help_first", "k": -1, "amt": None, "date": None, "line": "Anything else?"}
    st, w = turn(R, st, "No.")
    assert not st.get("xfer") and st["offer"]["kind"] == "first_ask"
    assert w["say"] == "Can you pay all of them today?"


def test_help_question_then_amount_question_is_answered():
    R = RAB()
    st, w = at_neg(R, "PUB-11", ["Can I talk to a human?", "How much do I owe?"])
    assert "past due" in w["say"] or "don't have that information" in w["say"]


def test_insists_helper_rules():
    R = RAB()
    c = neg_ctx(R, neg_state(R), "How much do I owe?")
    assert brain._b_insists(c, {"amt": 100, "dk": ""}) is False
    assert brain._b_insists(c, {"amt": None, "dk": "", "yn": {}}) is False
    c = neg_ctx(R, neg_state(R), "Put me through to someone.")
    assert brain._b_insists(c, None) is True


def test_human_transfer_without_ask_then_transfer_intent_is_none():
    R = RAB()
    R["spec"]["intents"] = []
    assert brain._b_human_transfer(neg_ctx(R, neg_state(R), "no"), []) is None


# ======================================================================= resolve_product
def test_clause_situations_need_several_products_and_clauses():
    R = RAB()
    assert brain._b_clause_sits(neg_ctx(R, neg_state(R), "That's not mine."), "neg") == {}
    c = neg_ctx(R, neg_state(R), "The card is not mine. I already paid the card yesterday.")
    got = brain._b_clause_sits(c, "neg")
    assert list(got) == [0] and got[0]["id"] == "dispute"
    c = neg_ctx(R, neg_state(R), "The card is not mine. The car loan I can pay tomorrow.")
    assert list(brain._b_clause_sits(c, "neg")) == [0]
    c = neg_ctx(RA(), neg_state(RA(), "PUB-01"), "Not mine. Not mine.", "PUB-01")
    assert brain._b_clause_sits(c, "neg") == {}


def test_per_clause_situations_skip_recorded_and_say_each_once():
    R = RAB()
    R["spec"]["required_sentences"].append({"id": "disp_rs", "text": "We will look into it.", "verbatim": True,
                                            "trigger": "on_intent:dispute", "once": True})
    for it in R["spec"]["intents"]:
        if it["id"] == "paid":
            it["action"]["say"] = "I understand. I won't take a promise for that one."
    st = neg_state(R)
    st["prods"][1]["rec"] = 1
    st, w = turn(R, st, "I already paid the card yesterday. The personal loan is not mine. The car loan is not mine.")
    assert sits(st) == ["S_PAID", "", "S_DISPUTE"] and st["prods"][1]["rec"] == 1
    assert w["say"].count("I won't take a promise for that one.") == 1
    assert w["say"].count("We will look into it.") == 1


def test_per_clause_situations_close_when_spec_does_not_continue():
    R = RAB()
    R["spec"]["multi_product"]["dispute_or_paid_continues"] = False
    st, w = turn(R, neg_state(R), "I already paid the card yesterday. The car loan is not mine.")
    assert sits(st)[0] == "S_PAID" and sits(st)[2] == "S_DISPUTE"
    assert w["nx"] in ("a_note_1", "a_note_2") and w["say"].endswith("Goodbye.")


def test_single_dispute_closes_multi_call_when_spec_does_not_continue():
    R = RAB()
    R["spec"]["multi_product"]["dispute_or_paid_continues"] = False
    st, w = turn(R, neg_state(R), "The car loan is not mine.")
    assert sits(st) == ["", "", "S_DISPUTE"] and w["say"].endswith("Goodbye.")
    assert [w.get("b_a_note_%d_reason" % i) for i in (1, 2, 3)] == ["refused", "refused", "dispute"]


def test_dispute_at_readback_without_mention_applies_to_all_unrecorded():
    R = RAB()
    st, w = at_neg(R, "PUB-11", ["Yes", "That's not mine."])
    assert sits(st) == ["S_DISPUTE"] * 3 and ag(st) == [None, None, None]
    st, w = at_neg(R, "PUB-11", ["Yes", "The car loan is not mine."])
    assert sits(st) == ["", "", "S_DISPUTE"] and w["nx"] == "s_conf"


def test_dispute_at_readback_with_single_agreement_targets_it():
    R = RAB()
    st = neg_state(R)
    st, _ = run(R, st, ["No", "Yes"])                     # card agreed on rung 1, then loan rung
    st["prods"][1]["sit"] = "S_REFUSED_EXHAUSTED"
    st["prods"][2]["sit"] = "S_REFUSED_EXHAUSTED"
    c = neg_ctx(R, st, "")
    brain._b_readback(c, [])
    st2 = c["st"]
    st2, w = turn(R, st2, "That's not mine.")
    assert sits(st2)[0] == "S_DISPUTE"


def test_dispute_of_other_product_keeps_current_offer():
    R = RAB()
    st, w = at_neg(R, "PUB-11", ["No", "The car loan is not mine."])
    assert sits(st) == ["", "", "S_DISPUTE"] and st["offer"]["k"] == 0
    assert w["say"] == "I understand. I won't take a promise for that one. Would that work for you?"


def test_paid_clause_survives_future_clause_about_other_product():
    R = RAB()
    st, w = turn(R, neg_state(R), "I already paid the card yesterday. The car loan I can pay tomorrow.")
    assert sits(st)[0] == "S_PAID"


# ======================================================================= transfer offer (offer_transfer)
def test_hardship_twice_repeats_only_the_offer_question():
    R = RAB()
    st, w = at_neg(R, "PUB-11", ["No", "I lost my job"])
    assert w["say"] == ("I'm sorry to hear that. Would you like me to connect you with our customer support team?")
    st, w = turn(R, st, "I lost my job")
    assert w["say"] == R["spec"]["lines"]["neutral_reask"]                # offered once (PUB-05)


def test_second_hardship_intent_after_offer_was_handled_only_acknowledges():
    R = RAB()
    st = neg_state(R)
    st["xoffered"] = 1
    st, w = turn(R, st, "I lost my job")
    assert w["say"] == "I understand. Can you pay all of them today?" and st["offer"]["kind"] == "first_ask"


def test_hardship_offer_without_suspending_persuasion():
    R = RAB()
    for it in R["spec"]["intents"]:
        if it["id"] == "hardship":
            it["action"]["suspend_persuasion"] = False
    st, w = at_neg(R, "PUB-11", ["No", "I lost my job"])
    assert st["offer"]["kind"] == "transfer_offer" and not st.get("suspend")


def test_hardship_with_value_keeps_valid_agreement_then_decline_reads_back():
    R = RAB()
    st, w = at_neg(R, "PUB-11", ["No", "I lost my job but I can pay 100 tomorrow"])
    assert ag(st)[0] == [10000, "2026-10-15"] and st["offer"]["kind"] == "transfer_offer"
    st, w = turn(R, st, "No")
    assert sits(st) == ["", "S_HARDSHIP_DECLINED", "S_HARDSHIP_DECLINED"]
    assert w["say"] == ("So that is 100 for your credit card ending 2288 on Thursday, 15 October. Do you confirm?")


def test_hardship_with_invalid_value_drops_it():
    R = RAB()
    st, w = at_neg(R, "PUB-11", ["No", "I lost my job, I can pay 5 tomorrow"])
    assert ag(st)[0] is None and st["offer"]["kind"] == "transfer_offer"


def test_question_during_transfer_offer_is_answered_then_offer_repeated():
    R = RAB()
    st, w = at_neg(R, "PUB-11", ["No", "I lost my job", "How much do I owe?"])
    assert w["say"] == ("Your credit card ending 2288 is 9 days late, with 220 past due. Would you like me to "
                        "connect you with our customer support team?")


def test_value_during_transfer_offer_declines_offer_and_keeps_value():
    R = RAB()
    st, w = at_neg(R, "PUB-11", ["No", "I lost my job", "No, but I can pay 100 tomorrow"])
    assert ag(st)[0] == [10000, "2026-10-15"]
    assert sits(st) == ["", "S_HARDSHIP_DECLINED", "S_HARDSHIP_DECLINED"]
    assert w["nx"] == "s_conf"


def test_higher_ranked_transfer_preempts_pending_transfer_offer():
    R = RAB()
    for it in R["spec"]["intents"]:
        if it["id"] == "restructure":
            it["precedence"] = 95
    st, w = at_neg(R, "PUB-11", ["No", "I lost my job"])
    st["prods"][0]["ag"] = None
    st, w = turn(R, st, "Actually I want a payment plan")
    assert st["xfer"]["q"] == "restructuring" and w["nx"] == "a_xfer_1"
    assert (w["co"], w["cr"]) == ("transferred", "restructuring")


def test_lower_ranked_transfer_does_not_preempt_transfer_offer():
    R = RAB()
    st, w = at_neg(R, "PUB-11", ["No", "I lost my job", "I want a payment plan"])
    assert not st.get("xfer") and w["say"] == R["spec"]["lines"]["neutral_reask"]


def test_higher_ranked_unhandled_intent_during_offer_reasks():
    R = add_intent(RAB(), id="x_hi", keywords=["\\bzebra\\b"], precedence=99,
                   action={"kind": "transfer", "say": "", "queue": "general", "situation": "S_HUMAN_TRANSFER"})
    st, w = at_neg(R, "PUB-11", ["No", "I lost my job"])
    st, w = turn(R, st, "zebra")
    assert st["xfer"]["q"] == "general"


def test_prec_and_xintent_helpers():
    assert brain._b_prec({"precedence": "abc"}) == 0.0
    assert brain._b_prec(None) == 0.0
    assert brain._b_prec({"precedence": "7"}) == 7.0
    R = RAB()
    c = neg_ctx(R, neg_state(R), "")
    c["st"]["xint"] = "nope"
    assert brain._b_xintent(c) is None


def test_hardship_decline_applies_to_current_product_only_when_spec_says_so():
    R = RAB()
    R["spec"]["multi_product"]["hardship_applies_to"] = "current"
    st, w = at_neg(R, "PUB-11", ["No", "I lost my job"])
    st["prods"][2]["sit"] = "S_DISPUTE"
    st, w = turn(R, st, "No")
    # current product declined; the next open product is not persuaded (suspended) and gets the decline too
    assert sits(st) == ["S_HARDSHIP_DECLINED", "S_HARDSHIP_DECLINED", "S_DISPUTE"]
    assert w["say"].endswith("Goodbye.") and w["nx"] == "a_note_1"
    assert [w["b_a_note_%d_reason" % i] for i in (1, 2, 3)] == ["hardship", "hardship", "dispute"]


# ======================================================================= confirmation (read-back)
def readback_state(R, cid="PUB-11"):
    st, w = turn(R, neg_state(R, cid), "Yes", cid=cid)
    assert st["ph"] == "CONF" and st["offer"]["kind"] == "readback"
    return st


def test_readback_loop_guard_reopens_negotiation():
    R = RA()
    st = neg_state(R, "PUB-01")
    st["rbc"] = 4
    st, w = turn(R, st, "Yes", cid="PUB-01")
    assert st["ph"] == "NEG" and st["prods"][0]["ref"] == [[42000, "2026-10-14"]]
    assert w["say"] == "Could you pay 420 by Friday, 16 October?"


def test_reopen_only_named_products_and_without_agreement_moves_on():
    R = RAB()
    st = readback_state(R)
    st["prods"][0]["ref"] = [[22000, "2026-10-14"]]
    c = neg_ctx(R, st, "")
    brain._b_reopen(c, [], only=[0])
    assert c["st"]["prods"][0]["ref"] == [[22000, "2026-10-14"]] and c["st"]["prods"][0]["ag"] is None
    assert c["st"]["prods"][1]["ag"] == [64000, "2026-10-14"]
    st = neg_state(R)
    for p in st["prods"]:
        p["sit"] = "S_DISPUTE"
    c = neg_ctx(R, st, "")
    brain._b_reopen(c, [])
    assert c["nx"] == "a_note_1"


def test_conf_without_agreement_moves_to_next_step():
    R = RAB()
    st = readback_state(R)
    for p in st["prods"]:
        p["ag"] = None
    st, w = turn(R, st, "Yes")
    assert st["offer"]["kind"] == "rung:r1" and st["prods"][0]["used"] == 1


def test_conf_new_date_reads_back_again():
    R = RA()
    st = readback_state(R, "PUB-01")
    st, w = turn(R, st, "Yes, but make it tomorrow", cid="PUB-01")
    assert ag(st) == [[42000, "2026-10-15"]] and st["offer"]["kind"] == "readback"
    assert w["say"] == "So that is 420 for your credit card ending 4821 on Thursday, 15 October. Do you confirm?"


def test_conf_change_later_with_interjection_keeps_answer():
    R = RAB()
    st, w = turn(R, readback_state(R), "Are you a robot? I'll change it later")
    assert w["say"] == "I am Freya Bank's digital assistant. Do you confirm?"
    st, w = turn(R, readback_state(R), "Yes, but I'll change it later")
    assert w["say"] == ("A recorded promise cannot be changed in this call. You can change it in the mobile app. "
                        "Do you confirm?")


def test_conf_change_for_named_product_only_revalidates_it():
    R = RAB()
    st, w = turn(R, readback_state(R), "The card on Friday instead")
    assert ag(st)[0] == [22000, "2026-10-16"] and ag(st)[1] == [64000, "2026-10-14"]
    assert w["nx"] == "s_conf"


def test_conf_change_to_invalid_amount_after_floor_offer_is_refusal():
    R = RA()
    st = readback_state(R, "PUB-01")
    st["prods"][0]["fo"] = 1
    st, w = turn(R, st, "Actually I can only pay 50", cid="PUB-01")
    assert ag(st) == [None] and st["offer"]["kind"] == "rung:r1"
    assert st["prods"][0]["ref"] == [[42000, "2026-10-14"]]


def test_conf_change_to_low_amount_offers_floor():
    R = RAB()
    st, w = turn(R, readback_state(R), "I can only pay 10 for the card")
    assert st["offer"]["kind"] == "floor" and ag(st)[0] is None and ag(st)[1] == [64000, "2026-10-14"]
    assert w["nx"] == "s_neg"


def test_conf_too_much_offers_floor_for_named_or_first_product():
    R = RAB()
    st, w = turn(R, readback_state(R), "That's too much for the card")
    assert st["offer"]["kind"] == "floor" and st["offer"]["k"] == 0 and ag(st)[0] is None
    assert "Could you pay 66 by Friday, 16 October?" in w["say"]
    st = readback_state(R)
    st["prods"][0]["ag"] = None
    st["prods"][0]["sit"] = "S_DISPUTE"
    st, w = turn(R, st, "That's too much for the card")
    assert st["offer"]["k"] == 1 and ag(st)[1] is None


def test_conf_question_is_answered_then_question_repeated():
    R = RAB()
    st, w = turn(R, readback_state(R), "How much is the car loan?")
    assert w["say"] == "Your car loan is 3 days late, with 75 past due. Do you confirm?"


def test_conf_hedge_twice_reopens():
    R = RAB()
    st, w = turn(R, readback_state(R), "maybe")
    # the whole read-back is repeated, so a later "yes" confirms what is actually recorded (quality round)
    assert w["say"].startswith("So that is 220") and w["say"].endswith("Do you confirm?") and st["conf"]["hedge"] == 1
    st, w = turn(R, st, "maybe")
    assert st["ph"] == "NEG" and ag(st) == [None, None, None]


def test_conf_unclear_repeats_readback_with_clarify_and_answer_continue_keeps_question():
    R = RAB()
    st, w = turn(R, readback_state(R), "hmm")
    assert w["say"].startswith("Sorry, could you say that again? So that is 220") and st["unc"] == 1
    st, w = turn(R, st, "Are you a robot?")
    assert w["say"] == "I am Freya Bank's digital assistant. Do you confirm?"


def test_conf_no_for_one_named_product_reopens_only_it():
    R = RAB()
    st, w = turn(R, readback_state(R), "No, not the card")
    assert ag(st)[0] is None and ag(st)[1] == [64000, "2026-10-14"] and st["offer"]["k"] == 0


# ======================================================================= remaining NEG/CONF branches
def test_grounded_slot_parse_crash_is_ignored(monkeypatch):
    R = RA()
    st = neg_state(R, "PUB-01")
    real_a, real_d = brain.parse_amount, brain.parse_date

    def amt(text, ctx=None):
        if text == "200":
            raise ValueError("slot")
        return real_a(text, ctx)

    def dat(text, *a):
        if text == "tomorrow":
            raise ValueError("slot")
        return real_d(text, *a)
    monkeypatch.setattr(brain, "parse_amount", amt)
    monkeypatch.setattr(brain, "parse_date", dat)
    v = brain._b_values(neg_ctx(R, st, "I can pay 200, sorry I mean, whatever", "PUB-01", u_amt="200"))
    assert v["amt"] is None
    v = brain._b_values(neg_ctx(R, st, "tomorrow, sorry I mean, whatever", "PUB-01", u_date="tomorrow"))
    assert v["dk"] == "" and v["date"] is None


def test_clause_mentions_same_product_in_two_value_clauses():
    R = RAB()
    v = brain._b_values(neg_ctx(R, neg_state(R), "I'll pay the card today, but the card and the car loan tomorrow"))
    assert v["prods"] == [0, 2]


def test_vague_date_after_exact_day_ask_was_used_offers_deadline():
    R = RA()
    st = neg_state(R, "PUB-01")
    st["prods"][0]["va"] = 1
    st, w = turn(R, st, "Sometime next month", cid="PUB-01")
    assert st["offer"]["kind"] == "deadline"
    assert w["say"] == "The latest date I can record is Monday, 2 November. Could you pay 420 by then?"


def test_insists_on_plain_no_act():
    R = RAB()
    c = neg_ctx(R, neg_state(R), "nope", act="no")
    assert brain._b_insists(c, {"amt": None, "dk": "", "yn": {}}) is True


def test_clause_without_product_mention_is_skipped():
    R = RAB()
    c = neg_ctx(R, neg_state(R), "I already paid yesterday. The car loan is not mine.")
    got = brain._b_clause_sits(c, "neg")
    assert list(got) == [2] and got[2]["id"] == "dispute"


def test_per_clause_required_sentence_shared_by_two_intents_is_said_once():
    R = RAB()
    for iid in ("dispute", "paid"):
        R["spec"]["required_sentences"].append({"id": "rs_" + iid, "text": "We will look into it.", "verbatim": True,
                                                "trigger": "on_intent:" + iid, "once": True})
    st, w = turn(R, neg_state(R), "I already paid the card yesterday. The car loan is not mine.")
    assert w["say"].count("We will look into it.") == 1


def test_dispute_of_recorded_product_leaves_it_recorded():
    R = RAB()
    st = neg_state(R)
    st["prods"][0]["rec"] = 1
    st, w = turn(R, st, "The card is not mine.")
    assert st["prods"][0]["rec"] == 1 and sits(st)[0] == ""


def test_yes_to_combined_ask_skips_resolved_products():
    R = RAB()
    st = neg_state(R)
    st["prods"][2]["sit"] = "S_DISPUTE"
    st, w = turn(R, st, "Yes")
    assert ag(st) == [[22000, "2026-10-14"], [64000, "2026-10-14"], None]
    assert "car loan" not in w["say"]


def test_statement_interjection_without_question_repeats_ask_in_neg_and_conf():
    R = RAB()
    st, w = turn(R, neg_state(R), "This is fake.")
    assert w["say"] == ("You can verify this call by phoning Freya Bank's customer service number. Can you pay all "
                        "of them today?")
    st, w = turn(R, readback_state(R), "This is fake.")
    assert w["say"] == ("You can verify this call by phoning Freya Bank's customer service number. Do you confirm?")
