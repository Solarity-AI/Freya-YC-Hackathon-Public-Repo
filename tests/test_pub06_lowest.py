"""PUB-06 official sim 9e911d50 (2026-10-11): with the floor pending, "You tell me what the lowest amount is." was
taken as a restructuring request (the extracted topic) and transferred. A question for the lowest / least / minimum
amount with no plan or instalment words is answered with the floor, the offer stays pending, no attempt is used."""
import pytest
from runtime import brain
from runtime.parse import asks_less
from test_brain import SPEC_A, exp, run_case
from test_pub06_once import ID6, P06, floor_offers

TM = "The full amount is too much for me right now."
FLOOR = brain._b_money(63750, SPEC_A)
LOWEST = FLOOR + " is the lowest amount I can record."
XFER = exp("transferred", "restructuring", transfers=[{"queue": "restructuring"}])


@pytest.mark.parametrize("ask", [
    {"t": "You tell me what the lowest amount is.", "u_topic": "restructuring", "u_act": "question"},   # 9e911d50
    {"t": "You tell me what the lowest amount is.", "u_topic": "restructuring"},
    {"t": "What's the least I can pay?", "u_topic": "restructuring"},
    {"t": "What is the minimum then?", "u_topic": "restructuring"},
    {"t": "Can I pay less?", "u_topic": "restructuring"},
    "You tell me what the lowest amount is.",
    "What's the least I can pay?",
    "What is the minimum then?",
    "Can I pay less?",
])
def test_lowest_amount_question_with_the_floor_pending_is_answered_not_transferred(ask):
    d = run_case("PUB-06", ID6 + [TM, ask, "Okay, Friday works.", "Yes, I confirm.", "No, thank you."],
                 expected=P06)
    assert "restructuring" not in " ".join(d.lines), d.lines
    reply = d.lines[5]
    assert LOWEST in reply and SPEC_A["lines"]["neutral_reask"] in reply, d.lines
    assert len([x for x in floor_offers(d) if LOWEST not in x]) == 1, d.lines   # no second offer: no attempt used
    assert d.score()["pass"], d.lines


@pytest.mark.parametrize("ask", [
    {"t": "I want lower monthly instalments.", "u_topic": "restructuring"},
    {"t": "Can we set up a payment plan?", "u_topic": "restructuring"},
    {"t": "What's the lowest monthly payment on a new plan?", "u_topic": "restructuring"},
    "I want lower monthly instalments.",
    "Can we set up a new payment plan?",
])
def test_a_real_restructuring_request_still_transfers(ask):
    d = run_case("PUB-06", ID6 + [TM, ask], expected=XFER)
    assert "restructuring" in d.lines[-1], d.lines
    assert d.score()["pass"], d.lines


def test_lowest_question_after_the_full_amount_gets_the_floor_offer():
    d = run_case("PUB-06", ID6 + [{"t": "What's the least I can pay?", "u_topic": "restructuring"}])
    assert FLOOR in d.lines[-1] and "restructuring" not in d.lines[-1], d.lines


def test_asking_twice_then_accepting_keeps_the_floor():
    d = run_case("PUB-06", ID6 + [TM, "You tell me what the lowest amount is.", "Is that really the minimum?",
                                  "Okay, Friday works.", "Yes, I confirm.", "No, thank you."], expected=P06)
    assert LOWEST in d.lines[5], d.lines
    assert d.score()["pass"], d.lines


@pytest.mark.parametrize("t,want", [
    ("You tell me what the lowest amount is.", True), ("what's the least I can pay?", True),
    ("what is the minimum then?", True), ("can I pay less?", True), ("Tell me the minimum.", True),
    ("I can pay the minimum on Friday.", False), ("The minimum is fine.", False),
])
def test_asks_less(t, want):
    assert asks_less(t) is want


@pytest.mark.parametrize("t,want", [
    ("You tell me what the lowest amount is.", True), ("Can I pay less?", True),
    ("What's the lowest monthly instalment?", False), ("Can I pay less every month?", False),
    ("Could I spread it, what is the least?", False), ("Can I pay less with a payment plan?", False),
])
def test_asks_lowest_needs_no_plan_words(t, want):
    assert brain._b_asks_lowest(t) is want
