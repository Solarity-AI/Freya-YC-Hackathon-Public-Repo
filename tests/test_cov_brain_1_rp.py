"""Coverage tests for runtime/brain.py lines 1-1350, part 3: the right-party phase (B.3 right_party, C.6 per-turn
accounting) driven turn by turn through brain.step, plus the ctx/listen plumbing it uses.

Rules exercised (docs/CONTRACTS.md B.3 / C.6 and STATUS "Fix round 1" C5, M1):
- ask #1 is the opening; a greeting-only reply re-asks and counts (reask_counts) unless reask_free;
- a question gets its answer plus the next ask; after the last ask anything but a confirmation -> on_unresolved
  (counts_as_unclear), unless answer_and_allow_one_more;
- third-person / not-here / bare "No." -> TP; hold -> "One moment" and a restart (opening + ask, counters reset);
- close_now intents (deceased, wrong number) apply only without a confirmation."""
import copy
import json
import pathlib

from runtime import brain

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load(rel):
    return json.loads((ROOT / rel).read_text())


SPEC = _load("tests/golden/spec-a.json")
SPEC.pop("meta", None)
W = _load("tests/fixtures/wiring-a.json")
CALL = {"customer_id": "c-1", "first_name": "Ann", "last_name": "Lee", "title": "Ms", "now": "2026-01-07T11:00"}
RP = SPEC["right_party"]
ASK = "Am I speaking with Ms Lee?"
OPENING = "Hello, I am a digital assistant calling from Freya Bank, and we record this call."
DOB_ASK = SPEC["identity"]["questions"][0]["ask"]


def turn(st, text, spec=SPEC, call=None, **sens):
    s = {"u_text": text}
    s.update(sens)
    R = {"v": 1, "spec": spec, "wiring": W}
    return brain.step(R, st, {"call": dict(call or CALL), "sensors": s, "results": {}, "entered_from": ""})


def play(texts, spec=SPEC, **sens):
    st, w = {}, None
    out = []
    for t in texts:
        st, w = turn(st, t, spec, **sens)
        out.append(w)
    return st, out


class TestFirstReply:
    def test_confirmation_goes_to_identity(self):
        st, w = turn({}, "Yes, speaking.")
        assert st["ph"] == "ID" and w["nx"] == "s_id"
        assert w["say"] == DOB_ASK
        assert st["rp"] == {"asks": 1}  # first ctl entry is the reply to ask #1 (C.7)

    def test_greeting_re_asks_and_counts(self):
        st, w = turn({}, "Hello?")
        assert w["nx"] == "s_rp" and w["say"] == ASK
        assert st["rp"]["asks"] == 2

    def test_greeting_re_ask_free_when_configured(self):
        spec = copy.deepcopy(SPEC)
        spec["interpretation"]["rp_greeting_first_turn"] = "reask_free"
        st, w = turn({}, "Hello?", spec)
        assert w["say"] == ASK and st["rp"]["asks"] == 1

    def test_who_question_is_answered_then_re_asked(self):
        st, w = turn({}, "Who is calling?")
        assert w["say"] == "I am Freya Bank's digital assistant. " + ASK
        assert st["rp"]["asks"] == 2

    def test_why_question_gets_the_pre_verification_answer(self):
        st, w = turn({}, "Why are you calling?")
        assert w["say"] == "I can only explain that to Ms Lee. " + ASK
        assert "collections" not in w["say"].lower()

    def test_other_question_gets_the_generic_answer(self):
        st, w = turn({}, "What's the weather like?")
        assert w["say"] == RP["answers"]["other"] + " " + ASK

    def test_question_with_an_answer_intent_uses_the_intent_answer_only(self):
        st, w = turn({}, "Is this a scam?")
        assert w["say"] == ("You can verify this call by phoning Freya Bank's customer service number. " + ASK)

    def test_reask_line_used_after_the_first_ask(self):
        spec = copy.deepcopy(SPEC)
        spec["right_party"]["reask"] = "Sorry, is this <customer>?"
        st, w = turn({}, "Hello?", spec)
        assert w["say"] == "Sorry, is this Ms Lee?"


class TestThirdParty:
    def test_not_here_goes_to_third_party_with_the_reach_ask(self):
        st, w = turn({}, "He's not here right now")
        assert st["ph"] == "TP" and w["nx"] == "s_tp"
        assert w["say"] == "When would be a good time to reach Ms Lee?"

    def test_bare_no_is_third_party(self):
        st, w = turn({}, "No.")
        assert st["ph"] == "TP"

    def test_bare_no_can_be_configured_otherwise(self):
        spec = copy.deepcopy(SPEC)
        spec["right_party"]["bare_no"] = "unclear"
        st, w = turn({}, "No.", spec)
        assert st["ph"] == "RP" and w["say"] == ASK and st["rp"]["asks"] == 2

    def test_other_person_topic_without_confirmation_is_third_party(self):
        st, w = turn({}, "hmm", u_topic="other_person")
        assert st["ph"] == "TP"

    def test_other_person_topic_does_not_override_a_confirmation(self):
        st, w = turn({}, "Yes, this is Ann", u_topic="other_person")
        assert st["ph"] == "ID"


class TestHoldAndRestart:
    def test_hold_then_restart_with_opening_and_ask(self):
        st, outs = play(["Hold on, let me get her.", "Hello?"])
        assert outs[0]["say"] == "One moment, please." and outs[0]["nx"] == "s_rp"
        assert outs[1]["say"] == OPENING + " " + ASK
        assert st["rp"] == {"asks": 1}  # counters reset (C.6 RESTART)

    def test_hold_topic_also_holds(self):
        st, w = turn({}, "hmm", u_topic="hold")
        assert w["say"] == "One moment, please." and st["rp"]["restart"] == 1

    def test_restart_turn_can_confirm(self):
        st, outs = play(["Hold on.", "Yes, this is Ann Lee."])
        assert st["ph"] == "ID" and outs[1]["say"] == DOB_ASK


class TestLastAsk:
    def test_two_unclear_replies_close_unresolved(self):
        st, outs = play(["Hello?", "Hmm?"])
        assert outs[1]["nx"] == "s_bye"
        assert outs[1]["say"] == SPEC["closing"]["goodbye"]
        assert (outs[1]["co"], outs[1]["cr"]) == ("not_reached", "unclear")
        assert st["csit"] == RP["on_unresolved"]

    def test_question_after_the_last_ask_counts_as_unclear(self):
        st, outs = play(["Hello?", "Who is this?"])
        assert outs[1]["nx"] == "s_bye" and outs[1]["cr"] == "unclear"

    def test_question_after_the_last_ask_allowed_once_more_when_configured(self):
        spec = copy.deepcopy(SPEC)
        spec["interpretation"]["rp_question_after_last_ask"] = "answer_and_allow_one_more"
        st, outs = play(["Hello?", "Who is this?", "Why do you ask?"], spec)
        assert outs[1]["say"] == "I am Freya Bank's digital assistant. " + ASK
        assert st["rp"]["extra"] == 1
        assert outs[2]["nx"] == "s_bye" and outs[2]["cr"] == "unclear"  # only one extra

    def test_confirmation_on_the_last_ask_still_verifies(self):
        st, outs = play(["Hello?", "Yes."])
        assert st["ph"] == "ID"


class TestCloseNowAndConfirmation:
    def test_wrong_number_closes(self):
        st, w = turn({}, "You have the wrong number.")
        assert w["nx"] == "s_bye"
        assert w["say"] == "I'm sorry for the inconvenience. " + SPEC["closing"]["goodbye"]
        assert (w["co"], w["cr"]) == ("not_reached", "wrong_number")

    def test_deceased_closes_with_the_required_sentence_once(self):
        st, w = turn({}, "She passed away last month.")
        assert w["say"] == "I am sorry for your loss. " + SPEC["closing"]["goodbye"]
        assert (w["co"], w["cr"]) == ("not_reached", "deceased")

    def test_confirmed_customer_mentioning_a_wrong_number_is_still_verified(self):
        st, w = turn({}, "Yes. Wrong number on the letter though.")
        assert st["ph"] == "ID"

    def test_non_close_intent_actions_are_ignored_before_verification(self):
        spec = copy.deepcopy(SPEC)
        spec["intents"].append({"id": "rp_human", "scope": ["rp"], "precedence": 99,
                                "keywords": ["\\bmanager\\b"],
                                "action": {"kind": "ask_then_transfer", "question": "Anything else?",
                                           "say": "Transferring.", "situation": "S_HUMAN_TRANSFER",
                                           "queue": "general"}})
        st, w = turn({}, "Get me your manager, you have the wrong number", spec)
        # the transfer intent is not acted on in RP; the close_now intent after it still is
        assert (w["co"], w["cr"]) == ("not_reached", "wrong_number")
        st, w = turn({}, "Get me your manager", spec)
        assert st["ph"] == "RP" and w["nx"] == "s_rp"

    def test_confirmation_with_who_question_answers_it(self):
        st, w = turn({}, "Yes, who is this?")
        assert st["ph"] == "ID"
        assert w["say"] == "I am Freya Bank's digital assistant. " + DOB_ASK

    def test_confirmation_with_why_question_uses_why_confirmed_or_default(self):
        st, w = turn({}, "Yes, what is this about?")
        assert w["say"].endswith(DOB_ASK)
        assert w["say"].startswith("I can explain once I have confirmed your identity.")
        spec = copy.deepcopy(SPEC)
        spec["right_party"]["answers"]["why_confirmed"] = "I will explain after a quick check."
        st, w = turn({}, "Yes, what is this about?", spec)
        assert w["say"] == "I will explain after a quick check. " + DOB_ASK

    def test_hardship_mentioned_at_confirmation_is_stashed_with_sympathy_once(self):
        st, w = turn({}, "Yes, it's me. I lost my job last month.")
        assert st["stash"] == "hardship" and st["symp"] == 1
        assert w["say"] == "I'm sorry to hear that. " + DOB_ASK
        assert "customer support" not in w["say"]  # the offer question waits for after the statement

    def test_paid_claim_at_confirmation_is_stashed_silently(self):
        st, w = turn({}, "Yes it's me, I already paid")
        assert st["stash"] == "paid"
        assert w["say"] == DOB_ASK


class TestCtxPlumbing:
    def test_bad_now_falls_back_to_a_found_date_or_a_fixed_day(self):
        R = {"v": 1, "spec": SPEC, "wiring": W}
        c = brain._b_ctx(R, {}, {"call": dict(CALL, now="call on 2026-02-03 please"), "sensors": {}})
        assert str(c["today"]) == "2026-02-03" and c["now"] == 0
        c = brain._b_ctx(R, {}, {"call": dict(CALL, now="garbage"), "sensors": {}})
        assert str(c["today"]) == "2000-01-03" and c["now"] == 0

    def test_neutral_sensor_values_read_as_empty(self):
        R = {"v": 1, "spec": SPEC, "wiring": W}
        c = brain._b_ctx(R, {}, {"call": CALL, "sensors": {"u_act": "Unclear", "u_topic": "none"}})
        assert c["act"] == "" and c["topic"] == ""
        c = brain._b_ctx(R, {}, {"call": CALL, "sensors": {"u_act": "Yes", "u_topic": "Paid"}})
        assert c["act"] == "yes" and c["topic"] == "paid"

    def test_long_customer_text_is_capped_at_a_space(self):
        R = {"v": 1, "spec": SPEC, "wiring": W}
        text = ("word " * 400).strip()
        c = brain._b_ctx(R, {}, {"call": CALL, "sensors": {"u_text": text}})
        assert len(c["text"]) <= brain._B_MAX_TEXT and not c["text"].endswith(" ") and c["text"].endswith("word")

    def test_listen_carries_queued_lines_and_uses_safe_for_unknown_phases(self):
        R = {"v": 1, "spec": SPEC, "wiring": W}
        c = brain._b_ctx(R, {"carry": ["Earlier."]}, {"call": CALL, "sensors": {}})
        brain._b_listen(c, "WRITE", ["Now."])
        assert c["nx"] == "s_safe" and c["st"]["await"] == "s_safe"
        assert c["say"] == ["Earlier.", "Now."] and "carry" not in c["st"]
