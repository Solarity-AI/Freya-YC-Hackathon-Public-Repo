"""Runtime audit round 3 (2026-10-11): regression tests for the 7 audit findings (each with 2+ variant inputs) and
for the failed live chat transcripts in results/chat/, replayed word for word in the twin."""
import copy
import datetime

import pytest

from runtime import brain, parse
from runtime.cal import prepare
from runtime.ident import rp_classify
from test_brain import P05_ID, P07_ID, SPEC_A, exp, run_a, run_case

TODAY = datetime.date(2026, 10, 14)
CAL = prepare(None, TODAY)
NAMES = ["Daniel", "Reyes"]


def promises(d):
    return [(p["amount"], p["date"]) for p in d.ledger()["promises"]]


def _spec(**intent_keywords):
    sp = copy.deepcopy(SPEC_A)
    for it in sp["intents"]:
        if it["id"] in intent_keywords:
            it["keywords"] = intent_keywords[it["id"]]
    return sp


# ======================================================================= 1 CRITICAL: yes + the customer has died
@pytest.mark.parametrize("text", ["Yes… he passed away.", "yes, this is his phone, he died last month.",
                                  "Yes. He passed away in June.", "Yes, but she died last year.",
                                  "Yeah. He's dead, he died in the summer.", "Yes, Daniel passed away last month."])
def test_yes_then_the_customer_died_is_deceased_not_a_confirmation(text):
    r = rp_classify(text, None, NAMES)
    assert r["cls"] == "third_party" and r["close"] == "deceased"
    d = run_a([text])
    assert d.ended and d.score(exp("not_reached", "deceased"))["pass"], d.lines
    assert d.lines[-1].startswith("I am sorry for your loss.")
    assert not any("date of birth" in x or "?" in x for x in d.lines[1:]), d.lines


@pytest.mark.parametrize("text", ["Yes. My father died last week, it is a bad time.",
                                  "Yes, speaking. My dad, he passed away last week.",
                                  "Yes, this is Daniel. My wife died, she was ill."])
def test_the_speakers_own_relative_dying_is_still_the_customer(text):
    assert rp_classify(text, None, NAMES)["cls"] == "confirm"
    d = run_a([text])
    assert not d.ended and "date of birth" in d.lines[-1]


@pytest.mark.parametrize("text", ["Yes. He died.", "Yes, she's no longer with us."])
def test_deceased_close_found_by_its_situation_when_the_keywords_miss(text):
    # the LLM-built Spec's keyword ("died (last|in|on|a)") does not match a bare "He died."
    d = run_a([text], spec=_spec(deceased=[r"\bpassed away\b"]))
    assert d.ended and d.score(exp("not_reached", "deceased"))["pass"], d.lines


def test_without_a_spec_deceased_intent_the_call_goes_to_third_party():
    sp = copy.deepcopy(SPEC_A)
    sp["intents"] = [it for it in sp["intents"] if it["id"] != "deceased"]
    d = run_a(["Yes. He died."], spec=sp)
    assert not d.ended and "date of birth" not in d.lines[-1], d.lines


def test_close_intent_lookup_is_by_tag_and_scope():
    c = {"S": SPEC_A}
    assert brain._b_close_intent(c, "rp", "deceased")["id"] == "deceased"
    assert brain._b_close_intent(c, "tp", "wrong_number")["id"] == "wrong_number"
    assert brain._b_close_intent(c, "neg", "deceased") is None
    assert brain._b_close_intent(c, "rp", "") is None


# ======================================================================= 7 minor: the caller does not know the customer
@pytest.mark.parametrize("text", ["I don't know who that is.", "I don't know any Daniel Reyes.", "Never heard of him.",
                                  "I don't know him", "There's no Daniel here.", "Sorry, no idea who you mean."])
def test_caller_who_does_not_know_the_customer_is_a_wrong_number(text):
    assert rp_classify(text, None, NAMES).get("close") == "wrong_number"
    d = run_a([text])
    assert d.ended and d.score(exp("not_reached", "wrong_number"))["pass"], d.lines


@pytest.mark.parametrize("text", ["I don't know who this is.", "I don't know.", "I don't know any details yet.",
                                  "I don't know any of that.", "Yes, speaking. I don't know him, the man you mentioned."])
def test_not_knowing_the_caller_or_the_details_is_not_a_wrong_number(text):
    assert rp_classify(text, None, NAMES).get("close") is None


def test_wrong_number_in_third_party_closes_too():
    d = run_a(["She's not here.", "Actually I don't know who that is, never heard of him."])
    assert d.ended and d.score(exp("not_reached", "wrong_number"))["pass"], d.lines


# ======================================================================= 2 MAJOR: part of the amount is too much
@pytest.mark.parametrize("text", ["Not the full amount.", "Only some.", "Some of it.", "Part of it now.",
                                  "I can pay part of it now.", "I can only do some of it today.",
                                  "Just part, maybe.", "A partial payment is all I can do."])
def test_offering_only_part_is_too_much_not_full_today(text):
    assert parse.too_much(text)
    d = run_a(P07_ID + [text], cid="PUB-07")
    assert "create_promise" not in d.tools() and not d.lines[-1].startswith("So that is 540"), d.lines
    assert "180" in d.lines[-1], d.lines            # the Spec's too_much rule: the floor offer


@pytest.mark.parametrize("text", ["Not all right now, call me later.", "Not everything is clear to me.",
                                  "Yes, the full amount.", "Not just yet."])
def test_part_phrases_do_not_overmatch(text):
    assert not parse.too_much(text)


def test_minimum_instead_of_full_is_still_a_floor_proposal():
    a = parse.parse_amount("I can pay the minimum, not the full amount",
                           {"known": [54000, 18000], "full": 54000, "floor": 18000})
    assert a["kind"] == "amount" and a["cents"] == 18000


# ======================================================================= 5 minor: asking to pay less
@pytest.mark.parametrize("text", ["What's the least I can pay?", "Can I pay less?", "Is there a minimum I could pay?",
                                  "What is the lowest amount I can pay today?", "Could I pay a smaller amount?"])
def test_asking_to_pay_less_triggers_the_too_much_rule(text):
    assert parse.too_much(text) and parse.asks_less(text)
    d = run_a(P07_ID + [text], cid="PUB-07")
    assert "don't have that information" not in d.lines[-1] and "180" in d.lines[-1], d.lines


def test_rejecting_the_minimum_is_still_a_refused_floor():
    assert not parse.asks_less("Even the minimum is too much.")
    d = run_a(P07_ID + ["Even the minimum is too much."], cid="PUB-07")
    assert "180" not in d.lines[-1], d.lines


# ======================================================================= 3 MAJOR: human request withdrawn in the turn
@pytest.mark.parametrize("text", ["I don't need a person, it's fine.", "No need for an agent, let's continue.",
                                  "Can I speak to a person? Actually never mind.", "I'm not asking for a human."])
def test_withdrawn_human_request_in_the_same_turn_resumes(text):
    d = run_a(P07_ID + [text], cid="PUB-07")
    assert not d.ended and "transfer" not in d.lines[-1].lower(), d.lines
    assert d.lines[-1] == "Can you make this payment today?", d.lines


def test_withdrawn_request_keeps_the_rest_of_the_turn():
    d = run_a(P07_ID + ["I don't want a human, I can pay Friday."], cid="PUB-07")
    assert d.lines[-1].startswith("So that is 540") and "16 October" in d.lines[-1], d.lines
    d = run_a(P07_ID + ["I don't need a person. I can't pay today."], cid="PUB-07")
    assert "540 by Friday, 16 October" in d.lines[-1], d.lines
    d = run_a(P07_ID + ["I don't want a payment plan, I can pay Friday."], cid="PUB-07")
    assert "transfer" not in " ".join(d.tools()) and d.lines[-1].startswith("So that is 540"), d.lines


@pytest.mark.parametrize("text", ["It's fine, I just want a person.", "I want to talk to a real person.",
                                  "No, put me through to a human."])
def test_real_human_requests_still_ask_the_help_question(text):
    d = run_a(P07_ID + [text], cid="PUB-07")
    assert d.lines[-1] == "Before I transfer you, is there anything I can help you with?", d.lines


def test_withdrawn_request_at_the_readback_reads_back_and_in_identity_reasks():
    d = run_a(P07_ID + ["I can pay on Friday.", "I don't need a person, it's fine."], cid="PUB-07")
    assert d.lines[-1].startswith("So that is 540") and d.lines[-1].endswith("Do you confirm?"), d.lines
    d = run_a(["Yes.", "I don't need a person, it's fine."], cid="PUB-07")
    assert "date of birth" in d.lines[-1] and "transfer" not in d.lines[-1], d.lines


def test_withdrawn_request_with_another_intent_still_acts_on_it():
    d = run_a(P05_ID + ["I don't need a person, but I lost my job."], cid="PUB-05")
    assert "customer support" in d.lines[-1] or "support" in d.lines[-1].lower(), d.lines


def test_withdrawn_helpers():
    it = {"keywords": [r"\ba person\b"]}
    assert brain._b_req_withdrawn(it, "I don't need a person")
    assert not brain._b_req_withdrawn(it, "I need a person")
    assert brain._b_req_withdrawn({"keywords": ["[bad"]}, "no need for a human")
    assert not brain._b_req_withdrawn({"keywords": []}, "nothing here")


# ======================================================================= 4 MAJOR: paid claim inside a question
@pytest.mark.parametrize("text", ["I paid it last week, didn't you get it?", "I paid it last week. Haven't you received it?",
                                  "I sent the money on Monday, can't you see it?", "I paid. Didn't it arrive?"])
def test_paid_claim_with_a_question_reaches_the_paid_situation(text):
    assert parse.has_completed_payment(text)
    d = run_a(P07_ID + [text], cid="PUB-07")
    assert d.ended and d.score(exp("paid"))["pass"], d.lines
    assert "don't have that information" not in " ".join(d.lines)


@pytest.mark.parametrize("text", ["I haven't paid yet.", "Paid? No, not yet.", "I paid but it didn't go through.",
                                  "I paid, didn't I?", "Did I pay?", "I didn't pay, I paid nothing"])
def test_negated_or_asked_payments_are_not_paid(text):
    assert not parse.has_completed_payment(text)


def test_paid_question_before_verification_is_kept_for_after_the_statement():
    d = run_a(["Yes.", "I paid it last week, didn't you get it?", "5 December 1975", "7093"], cid="PUB-07")
    assert d.ended and d.ledger()["outcome"] == "paid", d.lines


def test_paying_another_bill_is_not_a_paid_claim():
    d = run_a(P07_ID + ["I paid the electricity bill, so money is tight."], cid="PUB-07")
    assert not d.ended


# ======================================================================= 6 minor: weekday and date disagree
@pytest.mark.parametrize("text, iso_d, said", [("Friday the 22nd.", "2026-10-22", 4),
                                               ("Monday, 23 October", "2026-10-23", 0),
                                               ("I can pay on Thursday the 23rd", "2026-10-23", 3),
                                               ("Friday October 22", "2026-10-22", 4)])
def test_weekday_date_mismatch_keeps_the_date_and_flags_the_weekday(text, iso_d, said):
    assert parse.parse_date(text, TODAY, CAL) == {"kind": "date", "date": iso_d, "wd_said": said}


@pytest.mark.parametrize("text", ["Friday, 23 October", "Friday the 23rd", "the 22nd", "Thursday"])
def test_matching_weekday_or_none_has_no_flag(text):
    assert "wd_said" not in parse.parse_date(text, TODAY, CAL)


def test_mismatch_is_noted_once_before_the_readback_of_the_real_date():
    d = run_a(P07_ID + ["Friday the 22nd."], cid="PUB-07")
    assert d.lines[-1] == ("Just to note, the 22nd is a Thursday, not a Friday. So that is 540 for your personal loan "
                           "on Thursday, 22 October. Do you confirm?")
    d = run_a(P07_ID + ["Friday the 22nd.", "No.", "Friday the 22nd."], cid="PUB-07")
    assert "Just to note" not in d.lines[-1], d.lines
    d = run_a(P07_ID + ["Friday the 22nd.", "Yes."], cid="PUB-07")
    assert promises(d) == [(540.0, "2026-10-22")]


def test_wd_note_ordinals_and_bad_input():
    assert brain._b_wd_note("2026-10-21", 4).startswith("Just to note, the 21st is a Wednesday")
    assert "the 13th" in brain._b_wd_note("2026-11-13", 0)
    assert "the 3rd" in brain._b_wd_note("2026-11-03", 0)
    assert brain._b_wd_note("not a date", 1) == "" and brain._b_wd_note("2026-11-03", 9) == ""


def test_relative_day_that_disagrees_with_a_named_date_is_noted():
    d = run_a(P07_ID + ["I can pay tomorrow, the 11th of October."], cid="PUB-07")
    assert "Just to note, tomorrow is Thursday, 15 October." in d.lines[-1], d.lines
    d = run_a(P07_ID + ["I can pay tomorrow, the 15th."], cid="PUB-07")
    assert "Just to note" not in d.lines[-1]


# ======================================================================= CONF: a "no" that restates the read-back
PUB04_LIVE_031337 = ["Hello?", "Yes, this is Lena Hoffmann speaking.", "30 January, 1984.", "2219.",
                     "No, I cannot pay today, but my salary arrives on 6 November and I can pay the full amount then.",
                     "Yes, I can pay by Friday, 23 October.", "No, we agreed on Friday, 23 October, not the 16th.",
                     "I need the payment date to be Friday, 23 October, not the 16th.",
                     "Friday, 23 October is the date that works for me.",
                     "Friday, 23 October. Am I speaking with a robot?",
                     "No, that is not correct. We agreed on Friday, 23 October, not the 16th.",
                     "No, I cannot make a partial payment. My salary arrives on 6 November and I can pay the full "
                     "amount then."]


def test_live_pub04_031337_no_with_the_readback_date_reads_back_and_records():
    d = run_case("PUB-04", PUB04_LIVE_031337)
    assert d.score()["pass"], d.lines
    assert promises(d) == [(1250.0, "2026-10-23")]
    assert "16 October" not in " ".join(d.lines) and "Which exact day" not in " ".join(d.lines)
    assert "Sorry, could you say that again?" not in " ".join(d.lines)


def test_after_what_to_change_the_same_date_reads_back_again():
    d = run_a(P07_ID + ["I can pay on Friday.", "No.", "The date should be Friday, 16 October."], cid="PUB-07")
    assert d.lines[-2] == "What would you like to change?"
    assert d.lines[-1].startswith("So that is 540") and "Which exact day" not in d.lines[-1], d.lines


def test_a_real_refusal_naming_the_readback_date_still_reopens():
    d = run_a(P07_ID + ["I can pay on Friday.", "No, I can't pay on Friday, 16 October."], cid="PUB-07")
    assert not d.lines[-1].startswith("So that is"), d.lines


# ======================================================================= live transcripts cut by transport errors
@pytest.mark.parametrize("cid, prefix, rest, outcome", [
    ("PUB-03", ["Hello?", "Yes, that's me.", "12 July 1991.", "21 August 1992."], ["21 July 1990."],
     ("not_verified", "failed")),
    ("PUB-05", ["Hello?", "Yes, this is Tomas Novak speaking.", "9 September 1990."],
     ["8846.", "I lost my job last month and I cannot pay anything.", "No, I do not want to be transferred."],
     ("no_promise", "hardship")),
    ("PUB-06", ["Hello?", "Yes, this is Ms Nair speaking."],
     ["17 May 1986", "1502", "The full amount is too much right now.", "Yes, I can pay the minimum this Friday.",
      "Yes."], ("promise", None)),
])
def test_live_transcripts_cut_by_timeouts_complete_in_the_twin(cid, prefix, rest, outcome):
    d = run_case(cid, prefix + rest)
    assert d.score()["pass"], d.lines
    led = d.ledger()
    got = (led["outcome"], led["reason"])
    assert got == outcome


PUB12_LIVE_023512 = ["Hello?", "Yes, speaking.", "19 October 1983.", "4401.", "4410.",
                     "I can pay the credit card tomorrow, but I'm not paying the personal loan or the car loan.",
                     "No, I'm not paying the personal loan.", "No, I'm not paying the personal loan.",
                     "No, I'm not paying the car loan.", "No, I said tomorrow, which is October 11th.",
                     "The credit card payment is October 11th, tomorrow, not the 15th.",
                     "No, that's wrong. October 11th, not the 15th.", "October 11th, tomorrow.",
                     "No, I don't confirm. October 11th is tomorrow, not October 15th.",
                     "I want the payment for October 11th, tomorrow. That's what I said, and that's my offer.",
                     "No, I don't confirm. I said October 11th, not the 15th.",
                     "October 11th is tomorrow, and that's when I can pay the credit card.",
                     "No, that's still wrong. October 11th is tomorrow, not October 15th. That's my final answer."]


def test_live_pub12_persona_clock_bug_lines_get_the_real_date_and_end_by_the_loop_guards():
    # the persona read "tomorrow" off its own clock (11 October; fixed in the harness). The runtime now says what
    # tomorrow is, once, never records the past date and ends through its loop guards instead of 30 turns
    d = run_case("PUB-12", PUB12_LIVE_023512)
    said = " ".join(d.lines)
    assert d.ended and said.count("Just to note, tomorrow is Thursday, 15 October.") == 1
    assert all(p["date"] != "2026-10-11" for p in d.ledger()["promises"])
    assert len(d.lines) <= len(PUB12_LIVE_023512)


def test_live_pub01_code_size_era_lines_close_within_the_identity_budget():
    # every live reply was "Sorry, could you say that again?" (fixed: packed code), so the persona repeated its
    # confirmation; in the twin the identity question is re-asked and the call ends within the turn budget
    lines = ["Hello?"] + ["Yes, this is Daniel Reyes speaking.", "Yes, I am Daniel Reyes."] * 8
    d = run_case("PUB-01", lines)
    assert d.ended and d.ledger()["outcome"] == "not_verified"


def test_identity_help_question_answered_with_a_question_naming_a_spec_only_keyword_resumes():
    # the Spec's human keywords can name words the generic insist list does not ("manager"): a question is not insisting
    sp = _spec(human=[r"\b(real person|human|an agent|a person|operator|manager)\b"])
    d = run_a(["Yes.", "I want to talk to a real person.", "Can I talk to your manager?"], cid="PUB-07", spec=sp)
    assert not d.ended and "date of birth" in d.lines[-1], d.lines


def test_multi_word_name_tokens_are_skipped_by_the_name_death_rule():
    r = rp_classify("Yes. Mary Ann passed away.", None, ["Mary Ann", "Lee"])
    assert r["cls"] == "third_party" and r["close"] == "deceased"
    assert rp_classify("Yes, Lee died in May.", None, ["Mary Ann", "Lee"])["close"] == "deceased"


# ======================================================================= fix round 2: carried lines survive a re-plan
def _bye_ctx(st):
    from test_brain import W_A, runtime_spec
    r = brain._b_dec({"v": 1, "spec": runtime_spec(SPEC_A), "wiring": W_A})
    return brain._b_ctx(r, st, {"call": {}, "sensors": {}, "results": {}, "entered_from": ""})


@pytest.mark.parametrize("carry", [["We call about your account."], ["First line.", "Second line."]])
def test_carried_lines_are_said_again_when_a_failed_write_rebuilds_the_goodbye(carry):
    c = _bye_ctx({"prods": [{"j": 0}], "carry": list(carry), "bye_pre": ["Pre line."]})
    hyp = {"prods": [{"failed": 1}]}
    brain._b_bye_say(c, hyp)
    first = list(c["say"])
    assert "carry" not in c["st"]
    brain._b_bye_say(c, hyp)            # the re-plan after the failed write
    got = c["say"]
    assert got == first
    assert got[:len(carry) + 1] == carry + ["Pre line."]


def test_goodbye_without_carried_lines_leaves_bye_pre_alone():
    c = _bye_ctx({"prods": [{"j": 0}], "bye_pre": ["Pre line."]})
    brain._b_bye_say(c, {"prods": [{"failed": 1}]})
    assert c["st"]["bye_pre"] == ["Pre line."]
