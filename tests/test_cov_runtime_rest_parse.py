"""Coverage + behaviour tests for runtime/parse.py (docs/CONTRACTS.md C.3): number-word lexer corners, named /
relative amounts with brief floor words, calendar phrases (named days, nth weekday of a month, week phrases),
time readings that must be rejected, and the "total on bad input" guard of every public parser (checked by
injecting a failure into the helper each parser delegates to)."""
import datetime

import pytest

from runtime import parse as P
from runtime.cal import prepare

D = datetime.date
TODAY = D(2026, 10, 14)            # a Wednesday
CAL = prepare({}, TODAY)
NONE = {"kind": "none"}


def _boom(*_a, **_k):
    raise RuntimeError("injected")


class _BadStr:
    def __str__(self):
        raise ValueError("unprintable")


# ------------------------------------------------------------------ lexer helpers
def test_dec_cents_rounding():
    assert P._p_dec_cents("") is None
    assert P._p_dec_cents("5") == 50
    assert P._p_dec_cents("124") == 12
    assert P._p_dec_cents("125") == 13          # third decimal >= 5 rounds the cents up


def test_number_words_conversion_corners():
    assert P._p_conv("eleven first") == "11 1th"   # an ordinal cannot extend a teen: two numbers
    assert P._p_conv("a dozen") == "a dozen"
    assert P._p_tail_open("hello there") is False  # no number at all -> nothing left open
    assert P._p_tail_open("five and") is True


def test_decimal_with_tens_word():
    assert P.parse_amount("twelve point twenty three dollars")["cents"] == 1223
    assert P.parse_amount("twelve point five dollars")["cents"] == 1250


# ------------------------------------------------------------------ amounts: ctx options
def test_brief_floor_words_name_the_floor_and_bad_regexes_are_skipped():
    ctx = {"floor": 5000, "full": 90000, "floor_words": ["([", "nothing matches this", "smallest payment"]}
    r = P.parse_amount("I will make the smallest payment", ctx)
    assert r["kind"] == "amount" and r["cents"] == 5000 and r["named"] == "floor"


def test_unusable_drop_values_are_ignored():
    # a bare number listed in drop (e.g. days late) is not an offer; non-numeric drop entries are skipped
    assert P.parse_amount("I can pay 50", {"drop": ["x"]}) == {"kind": "amount", "cents": 5000, "hedged": False}
    assert P.parse_amount("I can pay 50", {"drop": ["x", 50]}) == NONE
    # an explicit currency word still makes it an amount
    assert P.parse_amount("I can pay 50 dollars", {"drop": [50]})["cents"] == 5000


# ------------------------------------------------------------------ date helpers
def test_day_of_month_skips_short_months():
    assert P._p_dom(D(2026, 2, 1), 31) == D(2026, 3, 31)
    assert P._p_dom(D(2026, 2, 1), 32) is None


def test_year_text_and_numeric_dates():
    assert P._p_year_txt("26") == 2026
    assert P._p_year_txt("abc") is None
    assert P._p_numdate("5", "6", "26", "DMY") == D(2026, 6, 5)   # two-digit year -> 20xx
    assert P._p_numdate("x", "6", "26", "DMY") is None


@pytest.mark.parametrize("text,today,out", [
    ("christmas", D(2026, 12, 28), {"kind": "date", "date": "2027-12-25"}),   # already passed -> next year
    ("the last friday of next month", TODAY, {"kind": "date", "date": "2026-11-27"}),
    ("the 5th friday of february", TODAY, NONE),                             # Feb 2027 has four Fridays
    ("in a couple of days", TODAY, {"kind": "vague", "what": "later"}),
    ("in 500 days", TODAY, NONE),                                            # beyond 400 days: ignored
    ("next week tuesday", TODAY, {"kind": "date", "date": "2026-10-20"}),
    ("this week friday", TODAY, {"kind": "date", "date": "2026-10-16"}),
])
def test_calendar_phrases(text, today, out):
    assert P.parse_date(text, today, prepare({}, today)) == out


# ------------------------------------------------------------------ times that must not be read
@pytest.mark.parametrize("text", ["at 25:30", "between 11 and 9", "half past 13", "25 oclock", "try 40"])
def test_impossible_times_are_none(text):
    assert P.parse_time(text) == NONE


def test_time_readings():
    assert P.parse_time("call at 7 30 pm") == {"kind": "exact", "min": 1170, "alts": [1170]}
    assert P.parse_time("half past 12 in the morning")["kind"] == "exact"


# ------------------------------------------------------------------ dob / alnum / yes-no corners
def test_dob_year_first_with_ordinal_day():
    assert P.parse_dob("1990 the 5th", "DMY", TODAY) == {"kind": "incomplete", "have": {"y": 1990, "d": 5}}


def test_alnum_double_digit_and_letters():
    assert P.parse_alnum("double 5 A") == "55A"
    assert P.parse_alnum("A double 5") == "A55"


def test_short_positive_word_is_yes():
    assert P.yes_no("great")["yn"] == "yes"
    assert P.yes_no("lovely thanks")["yn"] == "yes"


# ------------------------------------------------------------------ totality guards
def test_norm_and_match_any_on_bad_values():
    assert P.norm(_BadStr()) == ""
    assert P.match_any(5, "text") is False                 # patterns not iterable -> False
    assert P.match_any(["([", "foo"], "FOO bar") is True   # invalid regex skipped, the next one matches


@pytest.mark.parametrize("helper,call,expected", [
    ("_p_clauses", lambda: P.last_clause("sorry, I mean Friday"), ""),
    ("_p_amount", lambda: P.parse_amount("50 dollars"), NONE),
    ("_p_date_clause", lambda: P.parse_date("tomorrow", TODAY, CAL), NONE),
    ("_p_time_segs", lambda: P.parse_time("at 3pm"), NONE),
    ("_p_dob_clause", lambda: P.parse_dob("14 march 1990", "DMY", TODAY), NONE),
    ("parse_dob", lambda: P.parse_year("1990", TODAY), None),
    ("_p_digits_clause", lambda: P.parse_digits("one two three"), ""),
    ("_p_zero_marks", lambda: P.parse_alnum("A B 1"), ""),
    ("_p_income", lambda: P.has_completed_payment("I paid it yesterday"), False),
])
def test_public_parsers_are_total(monkeypatch, helper, call, expected):
    monkeypatch.setattr(P, helper, _boom)
    assert call() == expected


def test_day_and_time_is_total(monkeypatch):
    monkeypatch.setattr(P, "parse_date", _boom)
    assert P.parse_day_and_time("tomorrow at 3pm", TODAY, 600, CAL) == \
        {"date": "", "date_kind": "none", "time": NONE}


def test_turn_shape_helpers_are_total(monkeypatch):
    monkeypatch.setattr(P, "norm", _boom)
    assert P.yes_no("yes") == {"yn": "", "hedge": False, "cond": False, "corr": False, "cant": False,
                               "question": False}
    assert P.is_greeting_only("hello") is False
    assert P.is_question("can you") is False
    assert P.is_question("can you?") is True               # a '?' needs no normalisation
