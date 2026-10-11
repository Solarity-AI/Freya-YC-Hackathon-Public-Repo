"""PUB-06 official sims 0/3 (2026-10-11): the floor is offered once; nothing after it restates it."""
import pytest
from test_brain import SPEC_A, exp, run_case

P06 = exp("promise", promises=[{"product_id": "p1", "amount": 637.5, "date": "2026-10-16"}])
ID6 = ["Yes, this is Priya Nair.", "Seventeenth of May nineteen eighty six.", "One five zero two."]


def floor_offers(d):
    return [x for x in d.lines if "637.50" in x and "Do you confirm" not in x and "recorded" not in x]


@pytest.mark.parametrize("rest", [
    ["That full amount is too much for me right now.", "I can't pay the full amount",
     {"t": "You tell me.", "u_act": "refuse"}, "I can do that this Friday.", "Yes, I confirm."],      # ec22f848
    ["The full amount is too much for me to pay right now.", "you tell me.", "I can do that this Friday.",
     "Yes, I confirm."],                                                                              # bc6ccc74
    ["The full amount is too much right now.", "I can't do the full amount, you tell",
     "I can do that this Friday.", "Yes, I confirm."],                                                # 4bc6c14b
    ["The full amount is too much right now.", "I just can't afford the whole balance.", "Okay, Friday works.",
     "Yes, I confirm."],                                                                              # fresh variant
    ["That's too much for me.", "Honestly, what do you suggest?", "Fine, I'll do that on Friday.",
     "Yes, I confirm."],                                                                              # fresh variant
])
def test_pub06_live_transcripts_offer_the_floor_once(rest):
    d = run_case("PUB-06", ID6 + rest, expected=P06)
    assert len(floor_offers(d)) == 1, d.lines
    assert d.score()["pass"], d.lines


@pytest.mark.parametrize("reply", ["Blue elephants.", "Sorry, could you repeat that?", "Hold on a second.",
                                   "What happens if I don't pay?"])
def test_any_reask_after_the_floor_is_neutral(reply):
    d = run_case("PUB-06", ID6 + ["The full amount is too much.", reply, "Yes.", "Yes."], expected=P06)
    assert len(floor_offers(d)) == 1 and d.score()["pass"], d.lines
    assert SPEC_A["lines"]["neutral_reask"] in d.lines[5], d.lines


@pytest.mark.parametrize("reply", ["No, even that is too much.", "I can't pay that either.", "No, I can't."])
def test_a_refusal_of_the_floor_itself_still_uses_the_attempt(reply):
    d = run_case("PUB-06", ID6 + ["The full amount is too much.", reply, "No."], expected=exp("no_promise", "refused"))
    assert d.score()["pass"], d.lines


def test_full_amount_restated_twice_is_a_refusal_the_second_time():
    d = run_case("PUB-06", ID6 + ["The full amount is too much.", "I can't pay the full amount.",
                                  "I can't pay the full amount.", "No."], expected=exp("no_promise", "refused"))
    assert d.score()["pass"], d.lines


def test_too_much_to_the_first_ask_still_gets_the_floor():
    d = run_case("PUB-06", ID6 + ["I can't pay the full amount."])
    assert "637.50" in d.lines[-1] and "overdue" in d.lines[-1], d.lines
