"""PUB-12 official sims (2026-10-11, 1 of 3 reps): "It's October 19th, 1983. What is this about?" is a complete answer
to the date-of-birth question plus a purpose question. An extracted id-scope count_then_close intent
(asks_call_purpose) pre-empted the answer, so the date of birth was asked twice (Messages 4 and 6); two such turns
closed the call as declined with correct answers on record."""
import copy

import pytest
from test_brain import CASES, SPEC_A, SPEC_AB, W_AB, Driver, run_a

PURPOSE = {
    "id": "asks_call_purpose", "scope": ["id"], "precedence": 350, "product_scoped": False,
    "description": "Instead of answering a security question, the customer asks what the call is about.",
    "examples": ["What is this call about?"], "negatives": ["Is this a scam?"],
    "keywords": [r"\bwhat('?s| is) (this|the call|it)( call)? about\b", r"\bwhy are you calling\b"],
    "action": {"kind": "count_then_close", "say": "I can only tell you once you have answered the security questions.",
               "limit": 2, "situation": "S_ID_DECLINED", "situation_pre_verification": "S_ID_DECLINED"}}
EXPLAIN = SPEC_AB["identity"]["decline"]["explain"]


def _spec(base=SPEC_AB):
    sp = copy.deepcopy(base)
    sp["intents"] = list(sp.get("intents") or []) + [copy.deepcopy(PURPOSE)]
    return sp


def _play(turns, spec=None):
    d = Driver(spec or _spec(), W_AB, copy.deepcopy(CASES["PUB-12"]))
    d.play(turns)
    return d


@pytest.mark.parametrize("dob, ph", [
    ("It's October 19th, 1983. What is this about?", "4410."),               # the diagnosed live line
    ("19 October 1983.", "4410. What's this about?"),                         # fresh variant: on the digits question
    ("It's 19 October 1983. What is this about?", "4410. Why are you calling?"),  # two in one call must not close
    ("Nineteenth of October 1983 - why are you calling me?", "4410."),       # fresh variant
])
def test_identity_answer_with_a_purpose_question_is_an_answer_not_a_deflection(dob, ph):
    d = _play(["Yes.", dob, "4401", ph, "I can pay the credit card tomorrow.", "No.", "No.", "No.", "Yes."])
    assert sum("date of birth" in x.lower() for x in d.lines) == 1, d.lines
    assert d.tools()[:4] == ["verify_identity"] * 3 + ["get_account"], d.tools()
    assert d.score()["pass"], d.lines


def test_the_purpose_question_gets_the_explanation_with_the_next_question():
    d = _play(["Yes.", "It's October 19th, 1983. What is this about?"])
    assert EXPLAIN in d.lines[-1] and "only tell you once" not in d.lines[-1], d.lines
    assert d.tools() == ["verify_identity"], d.tools()


def test_bare_purpose_question_during_identity_still_deflects_and_reasks():
    d = _play(["Yes.", "What is this about?"])
    assert "only tell you once" in d.lines[-1] and "date of birth" in d.lines[-1].lower(), d.lines
    assert "verify_identity" not in d.tools()


def test_two_bare_deflections_still_close_declined():
    d = _play(["Yes.", "What is this about?", "Why are you calling?"])
    assert d.ended and "verify_identity" not in d.tools(), d.lines


def test_an_incomplete_answer_with_a_purpose_question_is_still_a_deflection():
    d = _play(["Yes.", "October 1983. What is this about?"])
    assert "only tell you once" in d.lines[-1] and "verify_identity" not in d.tools(), d.lines


def test_refuse_to_talk_with_a_complete_answer_is_an_answer():
    # golden Brief A: the refuse_talk intent (count_then_close) with the date of birth in the same turn
    d = run_a(["Yes, speaking.", "I don't want to talk long, it's 14 March 1988.", "4471", "Yes, I can pay it all today.",
               "Yes."], cid="PUB-01", spec=copy.deepcopy(SPEC_A))
    assert d.tools()[:3] == ["verify_identity", "verify_identity", "get_account"], (d.tools(), d.lines)
    assert d.score()["pass"], d.lines
