"""PUB-03 official sims (reps2 run 3, 2026-10-11, call 0fbd5167): voice STT gives a spoken date with no final
punctuation ("twenty one July nineteen ninety"). The tens-year was held open as if the customer might go on, so the
third wrong date of birth was answered with 'tell me your full date of birth' instead of verify -> lockout -> close.
A finished turn ends the year; only an explicit trail-off (..., -, ',') keeps it open."""
import datetime

import pytest
from test_brain import run_a

from runtime.ident import id_answer

TODAY = datetime.date(2026, 10, 11)
Q = {"kind": "date", "numeric_order": "DMY", "wire_format": "%Y-%m-%d", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}


@pytest.mark.parametrize("text, wire", [
    ("twenty one July nineteen ninety", "1990-07-21"),          # the live line, no punctuation
    ("the fourteenth of March nineteen eighty", "1980-03-14"),
    ("first of May twenty twenty", "2020-05-01"),
])
def test_unpunctuated_tens_year_completes_the_date(text, wire):
    assert id_answer(Q, text, "", TODAY) == {"status": "complete", "wire": wire}


@pytest.mark.parametrize("text", ["twenty one July nineteen ninety...", "twenty one July nineteen ninety,",
                                  "twenty one July nineteen ninety -", "twenty one July nineteen"])
def test_explicit_trail_off_still_waits(text):
    assert id_answer(Q, text, "", TODAY)["status"] == "incomplete"


def test_pub03_third_wrong_spoken_date_locks_out_without_another_prompt():
    d = run_a(["Yes, this is Owen Park.",
               {"t": "twelve July nineteen ninety one", "u_act": "answer", "u_ans": "twelve July nineteen ninety one"},
               {"t": "twenty one August nineteen ninety two", "u_act": "answer",
                "u_ans": "twenty one August nineteen ninety two"},
               {"t": "twenty one July nineteen ninety", "u_act": "answer", "u_ans": "twenty one July nineteen ninety"},
               {"t": "This is ridiculous. Just tell me how much I owe.", "u_act": "question"}], cid="PUB-03")
    assert d.ended and len(d.turn_lines) == 4, d.lines           # the call closes on the third answer's turn
    assert d.tools() == ["verify_identity"] * 3 + ["close_call"], d.tools()
    last = d.turn_lines[-1][-1].lower()
    assert "branch" in last and "date of birth" not in last, d.lines
    assert d.score()["pass"], d.lines
