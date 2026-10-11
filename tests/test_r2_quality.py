"""Quality round (2026-10-11): regression tests for the bugs found by the live-chat, review-audit, offline and
coverage passes. Each test names the finding it pins down; live lines are replayed word for word in the twin."""
import copy
import datetime

import pytest

from runtime import brain, bundle, parse
from runtime.cal import prepare
from runtime.ident import id_answer, rp_classify
from test_brain import (P05_ID, P07_ID, P10_ID, P11_ID, SPEC_A, SPEC_AB, W_A, W_AB, _textq_spec, exp, run_a,
                        run_case)

TODAY = datetime.date(2026, 10, 14)
CAL = prepare(None, TODAY)
NAMES = ["Daniel", "Reyes"]


def promises(d):
    return [(p["amount"], p["date"]) for p in d.ledger()["promises"]]


# ======================================================================= live PUB-04: "<weekday>, <date>"
@pytest.mark.parametrize("text", ["Yes, I can pay by Friday, 23 October.", "Friday, October 23",
                                  "Friday, 23rd of October", "Friday, the 23rd", "by Friday 23 October"])
def test_weekday_comma_date_is_one_date(text):
    assert parse.parse_date(text, TODAY, CAL) == {"kind": "date", "date": "2026-10-23"}


def test_weekday_comma_weekday_still_gives_alternatives():
    assert parse.parse_date("I can pay Friday, or Monday", TODAY, CAL) == \
        {"kind": "date", "date": "2026-10-16", "alts": ["2026-10-19"]}


PUB04_LIVE = ["Hello?", "Yes, this is Lena Hoffmann speaking.", "30 January 1984.", "2219.",
              "No, I cannot pay today, but my salary arrives on 6 November and I can pay then.",
              "Yes, I can pay by Friday, 23 October.",
              "No, the date should be Friday, 23 October, not 16 October.",
              "Yes, I confirm - 1,250 for my car loan on Friday, 23 October."]


def test_live_pub04_accepting_the_deadline_in_the_agents_format_records_that_date():
    d = run_case("PUB-04", PUB04_LIVE)
    assert d.score()["pass"], d.lines
    assert promises(d) == [(1250.0, "2026-10-23")]
    assert "Friday, 16 October" not in " ".join(d.lines)


def test_readback_correction_is_not_a_hedge_and_never_gets_a_bare_reask():
    yn = parse.yes_no("No, the date should be Friday, 23 October, not 16 October.")
    assert yn["yn"] == "no" and yn["corr"] is True and yn["hedge"] is False
    # read-back on 16 October, then the correction: the new date is read back in full
    d = run_a(P07_ID + ["I can pay on Friday.", "No, the date should be Friday, 23 October, not 16 October."],
              cid="PUB-07")
    assert d.lines[-1] != "Do you confirm?"
    assert "23 October" in d.lines[-1] and d.lines[-1].endswith("Do you confirm?")


def test_hedged_readback_answer_repeats_the_whole_readback():
    d = run_a(P07_ID + ["I can pay on Friday.", "I think so, maybe."], cid="PUB-07")
    assert d.lines[-1].startswith("So that is 540") and d.lines[-1].endswith("Do you confirm?")


# ======================================================================= live PUB-05: "right now" is not a date
def test_right_now_in_a_state_description_is_not_a_date():
    assert parse.parse_date("I'm having a hard time financially right now.", TODAY, CAL)["kind"] == "none"
    assert parse.parse_date("I am out of work right now and struggling", TODAY, CAL)["kind"] == "none"
    assert parse.parse_date("I can pay right now", TODAY, CAL)["date"] == "2026-10-14"
    assert parse.parse_date("Right now.", TODAY, CAL)["date"] == "2026-10-14"


PUB05_LIVE = ["Hello?", "Yes, this is Tomas Novak speaking.", "9 September 1990.", "8846.",
              "I'm afraid I can't make a payment today. I lost my job last month and I'm having a hard time "
              "financially right now. Is there any way you could work with me on a discount?",
              "No, I'd prefer not to be transferred. Isn't there anything you can do to help me?", "Yes, I confirm.",
              "Yes."]


def test_live_pub05_declined_hardship_offer_never_resumes_a_kept_today_proposal():
    d = run_case("PUB-05", PUB05_LIVE)
    assert d.score()["pass"], d.lines
    assert promises(d) == [] and d.ledger()["reason"] == "hardship"


def test_restated_offer_next_to_a_refusal_is_not_kept_at_the_transfer_offer():
    # "today" restates the pending first ask, so declining the support transfer closes hardship (no read-back)
    d = run_a(P05_ID + ["I can't pay today, I lost my job.", "No thanks."], cid="PUB-05")
    assert d.score(exp("no_promise", "hardship"))["pass"], d.lines


# ======================================================================= live PUB-09: keyword with filler words
PUB09_LIVE = ["Hello?", "Yes, speaking.", "11 August 1981.", "5560.",
              "I'm afraid I can't pay the full amount today. Could we discuss setting up lower monthly instalments "
              "instead?", "No, I can't pay that much by Friday. I really need to arrange lower monthly instalments "
              "that I can actually afford.", "I could try for 700 by the 23rd, but I need lower monthly payments "
              "going forward.", "Yes, I confirm."]


def test_live_pub09_restructure_keyword_with_a_filler_word_transfers():
    d = run_case("PUB-09", PUB09_LIVE)
    assert d.score()["pass"], d.lines
    assert d.ledger()["transfers"] == [{"queue": "restructuring"}] and promises(d) == []


def test_keyword_fallback_takes_out_fillers_and_contractions_only():
    it = {"keywords": [r"\blower (my )?instal?ments?\b", r"\bnot mine\b"]}
    assert brain._b_kw(it, "lower monthly instalments please")
    assert brain._b_kw(it, "that one isn't mine")
    assert not brain._b_kw(it, "lower interest")
    assert not brain._b_kw({"keywords": []}, "anything")


def test_topic_description_says_which_topic_wins():
    from builder.compiler import render
    desc = render._topic_description("neg", SPEC_A, render.topic_values("neg", SPEC_A))
    assert "If several topics fit, choose the first one listed." in desc
    assert desc.index("restructure:") < desc.index("too_much:")


# ======================================================================= C5: confirmed customer, relative's death
@pytest.mark.parametrize("text", ["Yes. My father died last week, it is a bad time.",
                                  "Yes, this is she. My husband passed away last month.",
                                  "Yes, that's right. My mum passed away on Monday."])
def test_yes_first_sentence_then_a_relatives_death_is_still_the_customer(text):
    assert rp_classify(text, None, NAMES)["cls"] == "confirm"
    d = run_a([text], cid="PUB-05")
    assert not d.ended and "date of birth" in d.lines[-1]


@pytest.mark.parametrize("text, cls", [("Yes. this is Sam.", "third_party"), ("Yes? Who is this?", "question"),
                                       ("Yes. He is not here right now.", "third_party"),
                                       ("Yes, this is his wife. He died.", "third_party"),
                                       ("I am afraid not.", "deny"), ("I am.", "confirm"), ("It is.", "confirm")])
def test_yes_first_rule_keeps_other_people_and_questions_apart(text, cls):
    assert rp_classify(text, None, NAMES)["cls"] == cls


@pytest.mark.parametrize("text", ["Mister Reyes, yes.", "Daniel, yes.", "Reyes, yes."])
def test_own_name_with_a_trailing_yes_confirms(text):
    assert rp_classify(text, None, NAMES)["cls"] == "confirm"
    assert "date of birth" in run_a([text]).lines[-1]


def test_round_decade_year_in_words_completes_from_a_fragment():
    q = {"kind": "year", "wire_format": "%Y", "pattern": "^[0-9]{4}$"}
    assert id_answer(q, "ninety.", "nineteen", TODAY) == {"status": "complete", "wire": "1990"}


# ======================================================================= C3 / C2: not an agreement, not a floor offer
@pytest.mark.parametrize("turn", ["Do I really have to pay today?", {"t": "Is the amount 365?", "u_act": "question"},
                                  "I can pay, but not this month.", "That is more than I can pay.",
                                  "The minimum is more than I can afford.", "The minimum? That's too much.",
                                  "Even the minimum is more than I can pay.", "I can't afford the minimum.",
                                  "Even the minimum payment is too high for me.", "What happens if I don't pay?"])
def test_first_ask_replies_that_agree_to_nothing(turn):
    d = run_a(P10_ID + [turn, "Yes."], cid="PUB-10")
    assert promises(d) == [], d.lines
    assert "Do you confirm?" not in d.lines[4]


def test_more_than_i_can_is_not_a_yes_and_is_too_much():
    assert parse.yes_no("That is more than I can pay.")["yn"] == ""
    assert parse.too_much("That is more than I can pay.") and not parse.too_much("I can pay the minimum.")
    d = run_a(P10_ID + ["That is more than I can pay."], cid="PUB-10")
    assert "109.50" in d.lines[-1]                       # the Spec's too-much rule: the floor is offered once


def test_named_floor_rejected_elsewhere_in_the_turn_is_no_amount():
    ctx = {"known": [36500, 10950], "full": 36500, "floor": 10950}
    assert parse.parse_amount("the minimum? that's too much.", ctx)["kind"] == "none"
    assert parse.parse_amount("the minimum is fine, the full amount is too much.", ctx)["cents"] == 10950
    assert parse.parse_amount("i can pay the minimum.", ctx)["cents"] == 10950


def test_offer_questions_keep_their_values():
    d = run_a(P10_ID + ["What about Friday?", "Yes."], cid="PUB-10")
    assert promises(d) == [(365.0, "2026-10-16")]
    d = run_a(P10_ID + ["Friday?", "Yes."], cid="PUB-10")
    assert promises(d) == [(365.0, "2026-10-16")]


# ======================================================================= M8: answerable questions, repeat, hold
@pytest.mark.parametrize("text, start", [("Can you repeat that?", "Your credit card ending 7740 is 8 days late"),
                                         ("Pardon?", "Your credit card ending 7740 is 8 days late"),
                                         ("Which account is this about?", "Your credit card ending 7740"),
                                         ("Who am I talking to?", "I am Freya Bank's digital assistant."),
                                         ("Hold on a second.", "Of course."),
                                         ("What happens if I don't pay?", "I'm sorry, I don't have that information.")])
def test_first_ask_questions_are_answered_then_the_ask_is_repeated(text, start):
    d = run_a(P10_ID + [text], cid="PUB-10")
    assert d.lines[-1].startswith(start), d.lines[-1]
    assert d.lines[-1].endswith("Can you make this payment today?")


def test_repeat_request_on_a_rung_offer_is_a_neutral_reask_not_a_second_offer():
    # PUB-06 (official sims): an amount offer is never said twice; the re-ask is the Spec's neutral_reask
    d = run_a(P10_ID + ["No.", "Sorry, could you repeat that?"], cid="PUB-10")
    assert d.lines[-1].endswith(SPEC_A["lines"]["neutral_reask"]) and d.lines[-1] != d.lines[-2], d.lines


# ======================================================================= M3: closure must be about the product
@pytest.mark.parametrize("text", ["My shop closed last month and I have no income.",
                                  "The branch near me closed, how do I pay?"])
def test_a_closed_shop_or_branch_is_not_a_dispute(text):
    d = run_a(P10_ID + [text], cid="PUB-10")
    assert not d.ended and d.ledger()["reason"] != "dispute", d.lines


def test_a_closed_account_is_still_a_dispute():
    d = run_a(P10_ID + ["I closed that card years ago."], cid="PUB-10", expected=exp("no_promise", "dispute"))
    assert d.score()["pass"], d.lines
    d = run_a(P11_ID + ["The credit card was closed last year."], cid="PUB-11")
    assert d.lines[-1].startswith("I understand.") or "dispute" in str(d.ledger()), d.lines


# ======================================================================= C4: callback day kept for a time-only answer
@pytest.mark.parametrize("second, time", [("Seven in the evening.", "19:00"), ("Half past six in the evening.", "18:30")])
def test_rejected_time_keeps_the_day_for_the_next_time(second, time):
    d = run_a(["No, this is her husband.", "Tomorrow at 9.", second], cid="PUB-02")
    assert d.ledger()["callbacks"] == [{"date": "2026-10-15", "time": time}], d.lines


# ======================================================================= M5: withdrawn human requests
@pytest.mark.parametrize("text", ["No, never mind, I don't need a human.", "No, it's okay, let's continue.",
                                  "No thanks, I'm fine.", "Never mind."])
def test_withdrawn_human_request_resumes(text):
    d = run_a(P10_ID + ["I want to speak to a human.", text], cid="PUB-10")
    assert not d.ended and d.ledger()["transfers"] == [], d.lines
    assert d.lines[-1].endswith("Can you make this payment today?")


def test_withdrawn_human_request_with_a_proposal_negotiates():
    d = run_a(P10_ID + ["I want to speak to a human.", "Forget the human, I'll pay on Friday.", "Yes."], cid="PUB-10")
    assert promises(d) == [(365.0, "2026-10-16")] and d.ledger()["transfers"] == []


def test_withdrawn_human_request_in_identity_resumes():
    d = run_a(["Yes, speaking.", "I want to speak to a human.", "No, I don't need a human."])
    assert not d.ended and "date of birth" in d.lines[-1]


# ======================================================================= M9: per-clause product situations
def _sits(d):
    return {n["product_id"]: n["reason"] for n in d.ledger()["notes"]}


def test_paid_card_and_disputed_loan_in_one_turn():
    d = run_a(P11_ID + ["The credit card is already paid. The car loan isn't mine.", "No.", "No."], cid="PUB-11")
    s = _sits(d)
    assert s.get("p1") == "paid" and s.get("p3") == "dispute", d.ledger()["notes"]


def test_clause_split_on_and_the_and_completed_payment_without_keyword():
    d = run_a(P11_ID + ["I paid the card yesterday and the car loan is not mine.", "No.", "No."], cid="PUB-11")
    s = _sits(d)
    assert s.get("p1") == "paid" and s.get("p3") == "dispute", d.ledger()["notes"]
    d = run_a(P11_ID + ["The car loan is not mine, and I paid the credit card yesterday.", "No.", "No."], cid="PUB-11")
    s = _sits(d)
    assert s.get("p1") == "paid" and s.get("p3") == "dispute", d.ledger()["notes"]


def test_paid_card_and_a_proposal_for_another_product():
    d = run_a(P11_ID + ["I already paid the card yesterday. The car loan I can pay tomorrow."], cid="PUB-11")
    assert d.lines[-1].startswith("Thank you. Payments can take")
    assert "personal loan" in d.lines[-1]                # the card is paid, the car loan agreed: next is the loan


def test_paid_future_rule_single_product_and_same_product():
    d = run_a(P10_ID + ["I have paid some and I will pay the rest tomorrow.", "Yes."], cid="PUB-10")
    assert d.ledger()["reason"] != "paid"


# ======================================================================= read-back: never mind / amount change
def test_never_mind_thats_correct_confirms_after_what_to_change():
    assert parse.yes_no("Never mind, that's correct.")["yn"] == "yes"
    assert parse.yes_no("Never mind.")["yn"] == "no"
    d = run_a(P07_ID + ["I can pay on Friday.", "No.", "Never mind, that's correct."], cid="PUB-07")
    assert promises(d) == [(540.0, "2026-10-16")], d.lines


def test_asked_change_amount_asks_for_the_amount():
    d = run_a(P07_ID + ["I can pay on Friday.", "No.", "Yes, the amount."], cid="PUB-07")
    assert d.lines[-1] == "What amount would you like to pay?"
    d = run_a(P07_ID + ["I can pay on Friday.", "No.", "Yes, I confirm."], cid="PUB-07")
    assert promises(d) == [(540.0, "2026-10-16")]


def test_corrected_value_equal_to_the_readback_reads_back_again():
    d = run_a(P07_ID + ["I can pay on Friday.", "No, the date should be Friday, 16 October."], cid="PUB-07")
    assert d.lines[-1] == d.lines[-2]


# ======================================================================= loop guard: amounts above the full amount
def test_amounts_above_full_are_offered_twice_then_refused():
    d = run_a(P07_ID + ["I can pay on Friday."] + ["No, make it 600.", "No, 550 then."] * 40, cid="PUB-07")
    assert d.ended and len(d.lines) < 15
    assert sum("Shall I record 540?" in x for x in d.lines) == 2


# ======================================================================= M10: every promise failed
def test_all_promises_failed_closing_is_one_honest_line():
    d = run_a(P11_ID + ["Yes, I can pay all of them today.", "Yes."], cid="PUB-11",
              faults=[{"tool": "create_promise", "fail_calls": [1, 2, 3, 4, 5, 6]}])
    assert d.lines[-1].startswith("I'm sorry, I could not record your promise.")
    d = run_a(P11_ID + ["Yes, I can pay all of them today.", "Yes."], cid="PUB-11",
              faults=[{"tool": "create_promise", "fail_calls": [1, 2, 3, 4]}])
    assert "credit card ending 2288 and personal loan." in d.lines[-1]


# ======================================================================= M12: free-text identity non-answers
@pytest.mark.parametrize("kind", ["text", "alnum"])
@pytest.mark.parametrize("text", ["Hold on.", "Pass.", "I paid it already.", "Skip it."])
def test_free_text_identity_never_sends_evasions(kind, text):
    d = run_a(["Yes.", text], spec=_textq_spec(kind))
    assert "verify_identity" not in d.tools(), d.lines


# ======================================================================= outcome values come from the Spec
def _renamed_spec():
    sp = copy.deepcopy(SPEC_AB)
    for s in sp["situations"].values():
        s["outcome"] = {"paid": "settled", "no_promise": "declined"}.get(s["outcome"], s["outcome"])
    return sp


def test_paid_and_dispute_detection_follow_the_spec_outcome_spelling():
    S = _renamed_spec()
    paid = next(it for it in S["intents"] if it["id"] == "paid")
    dispute = next(it for it in S["intents"] if it["id"] == "dispute")
    assert brain._b_np_outcome(S) == "declined"
    assert brain._b_is_paid_intent(S, paid["action"]) and not brain._b_is_paid_intent(S, dispute["action"])
    c = {"S": S}
    assert brain._b_dispute_intent(c, "neg")[1]["id"] == "dispute"
    S["situations"]["S_PAID_ALT"] = {"outcome": "settled", "reason": "", "queue": "", "note_reason": ""}
    assert brain._b_is_paid_intent(S, {"situation": "S_PAID_ALT"})


# ======================================================================= datetime request fields
def test_wire_dt_passes_an_unparseable_day_through():
    c = {"W": W_A}
    assert brain._b_wire_dt(c, "schedule_callback", "not a date", 0) == "not a date"


# ======================================================================= bundle: no inner cap for packed code
def test_large_spec_compiles_packed_without_the_inner_snippet_cap():
    from builder.compiler import snippet
    sp = copy.deepcopy(SPEC_AB)
    sp["lines"]["clarify"] = sp["lines"]["clarify"] + " " + ("Please say that once more. " * 1200)   # ~32 KB
    assert len(bundle.make_snippet(snippet.runtime_spec(sp, W_AB), encoding="json", max_bytes=0)) > bundle.MAX_BYTES - 40000
    code = snippet.build_ctl_code(sp, W_AB)
    assert len(code.encode()) <= bundle.PACK_MAX_BYTES


def test_make_snippet_and_pack_refuse_double_braces(monkeypatch):
    monkeypatch.setattr(bundle, "bundle_source", lambda minify=True: "X = '{{'\n")
    with pytest.raises(bundle.BundleError, match="not brace-safe"):
        bundle.make_snippet({"v": 1})
    monkeypatch.setattr(bundle, "_LOADER", bundle._LOADER + "\n# {{\n")
    with pytest.raises(bundle.BundleError, match="packed snippet not brace-safe"):
        bundle.pack_snippet("vars['nx'] = 'ok'\n")


def test_paid_claim_with_a_future_clause_about_the_same_product_is_not_paid():
    d = run_a(P11_ID + ["I already paid the card and I will pay the card again tomorrow."], cid="PUB-11")
    assert not d.lines[-1].startswith("Thank you. Payments can take"), d.lines[-1]


def test_closed_product_named_in_the_clause_is_a_dispute():
    from test_cov_brain_2 import RAB, ctx, neg_state
    R = RAB()
    c = ctx(R, neg_state(R), "The credit card closed down years ago.", cid="PUB-11")
    n = brain._b_norm(c["text"])
    assert brain._b_closed_product(c, c["text"], n)
    c = ctx(R, neg_state(R), "My shop closed down years ago.", cid="PUB-11")
    assert not brain._b_closed_product(c, c["text"], brain._b_norm(c["text"]))


def test_part_of_day_outside_the_window_without_a_day_is_outside():
    sp = copy.deepcopy(SPEC_A)
    sp["third_party"]["callback"]["windows"] = [{"from": "10:00", "to": "12:00", "inclusive_from": True,
                                                 "inclusive_to": True, "days": "any"}]
    d = run_a(["No, this is her husband.", "In the evening."], cid="PUB-02", spec=sp)
    assert d.lines[-1].startswith("I'm sorry, I can only arrange a call back"), d.lines[-1]


def test_paid_clause_that_is_itself_future_is_not_paid():
    from test_cov_brain_2 import RAB, ctx, neg_state
    R = RAB()
    c = ctx(R, neg_state(R), "I already paid the card and will pay again tomorrow.", cid="PUB-11")
    paid = next(it for it in R["spec"]["intents"] if it["id"] == "paid")
    assert brain._b_paid_future(c, paid, c["text"], True)
