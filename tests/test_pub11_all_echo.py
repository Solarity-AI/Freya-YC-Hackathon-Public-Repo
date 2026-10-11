"""PUB-11 official sims (2026-10-11, 1 of 3 reps): "No, I can't pay all of them today." echoes the multi-product
first ask ("Can you pay all of them today?"). It is a no to today (attempt 1 is the full amount), not a too-much that
earns the card its floor (the rep recorded p1 at 66 instead of 220)."""
import pytest
from test_brain import exp, run_a

ID11 = ["Yes.", "3 June 1987", "2288"]
FRIDAY_ALL = exp("promise", promises=[{"product_id": "p1", "amount": 220.0, "date": "2026-10-16"},
                                      {"product_id": "p2", "amount": 640.0, "date": "2026-10-16"},
                                      {"product_id": "p3", "amount": 75.0, "date": "2026-10-16"}])


@pytest.mark.parametrize("no_today", [
    "No, I can't pay all of them today.",                                   # the diagnosed live line
    "No, I can't pay all of that today.",
    "No, I can't pay all three today.",
    {"t": "No, I can't pay all of them today.", "u_topic": "too_much"},     # the extractor's topic rests on the echo
    "No, not everything today.",                                            # fresh variant
    "Sorry, I can't pay it all today.",                                     # fresh variant
    "I can't afford all of them today.",                                    # same echo, other verb
])
def test_multi_first_ask_all_echo_is_no_to_today_not_too_much(no_today):
    d = run_a(ID11 + [no_today, "I can pay all three this Friday.", "Yes."], cid="PUB-11", expected=FRIDAY_ALL)
    assert d.score()["pass"], d.lines
    assert "66" not in d.lines[4], d.lines


@pytest.mark.parametrize("too_much", ["No, I can't pay all of them, it's too much.",
                                      "All of them is more than I can afford right now."])
def test_a_real_too_much_beside_the_echo_still_gets_the_floor(too_much):
    d = run_a(ID11 + [too_much], cid="PUB-11")
    assert "66" in d.lines[-1], d.lines


def test_echo_strip_does_not_apply_once_a_product_offer_is_pending():
    # after a per-product offer, "I can't pay all of it" is about that product's amount: too much -> its floor
    d = run_a(ID11 + ["No.", "I can't pay all of it, that's too much."], cid="PUB-11")
    assert "66" in d.lines[-1], d.lines


def test_both_echo_with_two_products_is_a_no_to_today():
    both = {"t": "No, I can't pay both today.", "u_topic": "too_much"}
    d = run_a(["Yes.", "8 January 1991", "6604", both], cid="PUB-13")
    assert "Could you pay 300 " in d.lines[-1] and "overdue" not in d.lines[-1], d.lines
