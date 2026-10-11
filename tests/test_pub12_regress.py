"""PUB-12 official sims (reps2 run 1, 2026-10-11, call f9a4f265): "nineteen October nineteen eighty three" grouped the
day 'nineteen' with the year's 'nineteen' ACROSS the month word -> year 1919 and no day -> the agent asked for the date
of birth again. A year is only built from adjacent number tokens; the group ending last wins (spoken dates say the
year last), a tie goes to the longer group; a numeric YMD date without a month word still takes the first group."""
import datetime

import pytest

from runtime import parse as P
from runtime.ident import id_answer

TODAY = datetime.date(2026, 10, 11)
Q_DOB = {"key": "dob", "kind": "date", "numeric_order": "DMY", "wire_format": "%Y-%m-%d",
         "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}


@pytest.mark.parametrize("text, order, exp", [
    ("nineteen October nineteen eighty three.", "DMY", (1983, 10, 19)),   # PUB-12 official run 1, verbatim
    ("nineteen October nineteen eighty three", "DMY", (1983, 10, 19)),    # unpunctuated voice turn
    ("nineteen October nineteen eighty three.", "MDY", (1983, 10, 19)),
    ("nineteenth of October nineteen eighty three", "DMY", (1983, 10, 19)),
    ("the nineteenth of October nineteen eighty three", "MDY", (1983, 10, 19)),
    ("October nineteen nineteen eighty three", "MDY", (1983, 10, 19)),
    ("October nineteen nineteen eighty three", "DMY", (1983, 10, 19)),
    ("twenty October twenty oh three", "DMY", (2003, 10, 20)),            # was silently 2020-10-03
    ("nineteen ten nineteen eighty three", "DMY", (1983, 10, 19)),
    ("19 10 1983", "DMY", (1983, 10, 19)),
    ("one nine one zero one nine eight three", "DMY", (1983, 10, 19)),
    ("twelve March nineteen eighty eight", "DMY", (1988, 3, 12)),
    ("nineteen eighty three October nineteenth", "DMY", (1983, 10, 19)),  # year first, then day
    ("1983 10 19", "YMD", (1983, 10, 19)),
])
def test_dob_cardinal_day_equal_to_century_word(text, order, exp):
    r = P.parse_dob(text, order, TODAY)
    assert r["kind"] == "date" and (r["y"], r["m"], r["d"]) == exp, r


@pytest.mark.parametrize("text", ["nineteen October nineteen eighty three.", "nineteen October nineteen eighty three",
                                  "nineteenth of October nineteen eighty three",
                                  "October nineteen nineteen eighty three"])
def test_pub12_id_answer_completes_first_time(text):
    assert id_answer(Q_DOB, text, "", TODAY) == {"status": "complete", "wire": "1983-10-19"}


@pytest.mark.parametrize("text", ["nineteen October nineteen", "nineteenth of October nineteen",
                                  "twenty October twenty"])
def test_year_never_spans_a_month_word(text):
    r = P.parse_dob(text, "DMY", TODAY)
    assert r.get("y") not in (1919, 2020) and r.get("have", {}).get("y") not in (1919, 2020), r


def test_find_year_adjacency_and_ordering():
    toks = {v: {"k": "n", "v": v, "s": str(v), "lit": False, "sc": False, "zw": False, "ord": False, "last": "tens",
                "c": None} for v in (19, 83, 10)}
    # positions 0, 2, 3: the month word sits at position 1
    items = [(0, toks[19]), (2, toks[19]), (3, toks[83])]
    assert P._p_find_year(items, [0, 2, 3], "DMY", True) == (1, 3, 1983)
    assert P._p_find_year(items) == (1, 3, 1983)                       # ends default to the start positions
    # numeric YMD without a month word: the first group wins even when a later one also reads as a year
    items = [(0, toks[19]), (1, toks[83]), (2, toks[19]), (3, toks[10])]
    assert P._p_find_year(items, [0, 1, 2, 3], "YMD", False) == (0, 2, 1983)
    assert P._p_find_year(items, [0, 1, 2, 3], "DMY", False) == (2, 4, 1910)
    assert P._p_find_year([], [], "DMY", False) is None
