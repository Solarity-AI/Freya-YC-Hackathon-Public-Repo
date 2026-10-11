"""Unit tests for runtime/ident.py (agent 2): right-party matcher, identity answers, verify-result classifier.
Edge cases drawn from docs/edge-cases/EDGE-CASES.md (OPN, IDV)."""
import datetime

import pytest

from runtime.ident import rp_classify, id_answer, verify_class

TODAY = datetime.date(2026, 10, 14)
NAMES = ["Jordan", "Lee"]

Q_DATE = {"key": "dob", "field_value": "<date field>", "kind": "date", "numeric_order": "DMY",
          "wire_format": "%Y-%m-%d", "length": 0, "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
          "ask": "a", "reask_wrong": "b", "ask_full": "c", "max_wrong": 0}
Q_DIG4 = {"key": "tail", "field_value": "number_last4", "kind": "digits", "numeric_order": "DMY",
          "wire_format": "digits", "length": 4, "pattern": "^[0-9]{4}$", "ask": "What are the last four digits?",
          "reask_wrong": "b", "ask_full": "c", "max_wrong": 0}
Q_DIG6 = dict(Q_DIG4, key="pin", field_value="member_code", length=6, pattern="^[0-9]{6}$", ask="Your member code?")
Q_YEAR = {"key": "yr", "field_value": "<year field>", "kind": "year", "numeric_order": "DMY", "wire_format": "%Y",
          "length": 0, "pattern": "^[0-9]{4}$", "ask": "a", "reask_wrong": "b", "ask_full": "c", "max_wrong": 0}
Q_ALNUM = {"key": "pc", "field_value": "<code field>", "kind": "alnum", "numeric_order": "DMY",
           "wire_format": "upper_nospace", "length": 0, "pattern": "", "ask": "a", "reask_wrong": "b",
           "ask_full": "c", "max_wrong": 0}
Q_TEXT = {"key": "town", "field_value": "<text field>", "kind": "text", "numeric_order": "DMY", "wire_format": "as_is",
          "length": 0, "pattern": "", "ask": "a", "reask_wrong": "b", "ask_full": "c", "max_wrong": 0}


# ------------------------------------------------------------------ rp_classify
@pytest.mark.parametrize("text,act,cls,q", [
    ("This is Jordan speaking", "yes", "confirm", ""),                 # contract example
    ("Yes? Who is this?", "question", "question", "who"),             # contract example
    ("She's at work", "no", "third_party", ""),                       # contract example
    ("Yes, speaking.", "yes", "confirm", ""),
    ("Yeah that's me.", "yes", "confirm", ""),
    ("Speaking.", "", "confirm", ""),
    ("Jordan here.", "", "confirm", ""),
    ("It's Lee.", "", "confirm", ""),
    ("Correct.", "yes", "confirm", ""),
    ("Hello?", "chatter_only", "greeting", ""),
    ("Hi.", "", "greeting", ""),
    ("Go ahead.", "", "greeting", ""),
    ("Who is this?", "question", "question", "who"),
    ("Who's calling please?", "question", "question", "who"),
    ("What is this about?", "question", "question", "why"),
    ("Are you a robot?", "question", "question", "robot"),
    ("Is this a scam?", "question", "question", "scam"),
    ("No.", "no", "deny", ""),
    ("No, he's not here right now.", "no", "third_party", ""),
    ("This is his wife.", "", "third_party", ""),
    ("I'm her husband, what's this about?", "", "third_party", ""),
    ("Yes, this is Maria.", "yes", "third_party", ""),                # a different first name beats 'yes'
    ("You've reached the voicemail of Jordan Lee, please leave a message after the tone.", "", "unclear", ""),
    ("", "yes", "unclear", ""),
    ("Hello, hello?", "", "greeting", ""),
])
def test_rp_classify_table(text, act, cls, q):
    r = rp_classify(text, act, NAMES)
    assert r["cls"] == cls, (text, r)
    if q:
        assert r["q"] == q, (text, r)


def test_rp_classify_confirm_with_question_keeps_question_type():
    r = rp_classify("Yes, speaking. Who is this?", "yes", NAMES)
    assert r["cls"] == "confirm" and r["q"] == "who"


def test_rp_classify_hold_is_flagged():
    r = rp_classify("Hold on, I'll get her.", "", NAMES)
    assert r["cls"] == "third_party" and r["hold"] is True


def test_rp_classify_possessive_name_is_not_confirmation():
    r = rp_classify("This is Jordan's wife.", "yes", NAMES)
    assert r["cls"] == "third_party"


def test_rp_classify_u_act_is_only_a_hint():
    assert rp_classify("Hello?", "yes", NAMES)["cls"] == "greeting"
    assert rp_classify("She's at work", "yes", NAMES)["cls"] == "third_party"


def test_rp_classify_correction_uses_last_clause():
    r = rp_classify("No wait, sorry, yes that's me.", "", NAMES)
    assert r["cls"] == "confirm"


def test_rp_classify_accent_folding():
    r = rp_classify("This is José speaking", "", ["Jose", "Garcia"])
    assert r["cls"] == "confirm"


@pytest.mark.parametrize("bad", [None, 12, "   ", "???", "\x00\x01"])
def test_rp_classify_total_on_bad_input(bad):
    r = rp_classify(bad, None, None)
    assert r["cls"] in ("unclear", "greeting", "question", "deny")


# ------------------------------------------------------------------ id_answer
def test_digits_complete_with_leading_zero():
    assert id_answer(Q_DIG4, "it's oh three five eight", "", TODAY) == {"status": "complete", "wire": "0358"}


def test_digits_pieces_are_buffered():
    a = id_answer(Q_DIG4, "oh three", "", TODAY)
    assert a == {"status": "incomplete", "frag": "03"}
    b = id_answer(Q_DIG4, "five eight", a["frag"], TODAY)
    assert b == {"status": "complete", "wire": "0358"}


def test_digits_plain_and_spaced_forms():
    assert id_answer(Q_DIG4, "4471", "", TODAY)["wire"] == "4471"
    assert id_answer(Q_DIG4, "4-4-7-1", "", TODAY)["wire"] == "4471"
    assert id_answer(Q_DIG4, "44 71", "", TODAY)["wire"] == "4471"


def test_digits_last_n_takes_trailing_digits_of_longer_string():
    a = id_answer(Q_DIG4, "the number is 0712344471", "", TODAY)
    assert a == {"status": "complete", "wire": "4471"}


def test_digits_too_long_for_non_last_question_is_invalid():
    assert id_answer(Q_DIG6, "1234567", "", TODAY)["status"] == "invalid"


def test_digits_none_when_no_digits():
    assert id_answer(Q_DIG4, "I don't want to tell you", "", TODAY)["status"] == "none"


def test_date_words_to_iso():
    a = id_answer(Q_DATE, "the third of May nineteen seventy-nine", "", TODAY)
    assert a == {"status": "complete", "wire": "1979-05-03"}


def test_date_numeric_read_in_numeric_order():
    assert id_answer(Q_DATE, "03/05/1979", "", TODAY)["wire"] == "1979-05-03"
    mdy = dict(Q_DATE, numeric_order="MDY")
    assert id_answer(mdy, "03/05/1979", "", TODAY)["wire"] == "1979-03-05"


def test_date_impossible_numeric_is_never_sent():
    a = id_answer(Q_DATE, "03/14/1988", "", TODAY)          # DMY: month 14
    assert a["status"] in ("invalid", "incomplete", "none")
    assert a.get("wire") is None


def test_date_without_year_is_incomplete_then_merged():
    a = id_answer(Q_DATE, "May the third", "", TODAY)
    assert a["status"] == "incomplete"
    b = id_answer(Q_DATE, "nineteen seventy-nine", a["frag"], TODAY)
    assert b == {"status": "complete", "wire": "1979-05-03"}


def test_date_wire_format_custom():
    q = dict(Q_DATE, wire_format="%d.%m.%Y", pattern="^[0-9]{2}\\.[0-9]{2}\\.[0-9]{4}$")
    assert id_answer(q, "14 March 1988", "", TODAY)["wire"] == "14.03.1988"


def test_pattern_mismatch_is_invalid_never_complete():
    q = dict(Q_DIG4, pattern="^9[0-9]{3}$")
    assert id_answer(q, "4471", "", TODAY)["status"] == "invalid"


def test_year_question():
    assert id_answer(Q_YEAR, "nineteen eighty-eight", "", TODAY) == {"status": "complete", "wire": "1988"}


def test_alnum_question():
    a = id_answer(Q_ALNUM, "A B one two", "", TODAY)
    assert a["status"] == "complete" and a["wire"].replace(" ", "") == a["wire"]


def test_text_question():
    assert id_answer(Q_TEXT, "Springfield.", "", TODAY) == {"status": "complete", "wire": "Springfield"}
    assert id_answer(Q_TEXT, "   ", "", TODAY)["status"] == "none"


@pytest.mark.parametrize("q", [Q_DATE, Q_DIG4, Q_YEAR, Q_ALNUM, Q_TEXT, {}, None])
@pytest.mark.parametrize("text", [None, "", "\u0000", "!!!", 42])
def test_id_answer_total_on_bad_input(q, text):
    r = id_answer(q, text, None, TODAY)
    assert r["status"] in ("none", "invalid", "incomplete", "complete")


# ------------------------------------------------------------------ verify_class
def _res(**kw):
    base = {"s": "pending", "verified": "pending", "left": "pending", "all": "pending", "hint": "pending",
            "err": "pending"}
    base.update(kw)
    return base


@pytest.mark.parametrize("res,cls", [
    (_res(s="true", verified="false", left="2", all="false"), "wrong"),                       # contract example
    (_res(), "transport_fail"),                                                              # contract example
    (_res(s="true", verified="true", left="3", all="false"), "verified"),
    (_res(s="True", verified="True", left="3", all="True"), "all_done"),
    (_res(s="true", verified="true", all="true"), "all_done"),
    (_res(s="true", verified="true"), "verified"),                                          # all leaf missing
    (_res(s="true", verified="false", left="3", hint="day_month_swapped"), "hint:day_month_swapped"),
    (_res(s="true", verified="true", hint="some_hint"), "hint:some_hint"),                  # hint overrides
    (_res(s="false", verified="false", left="0"), "lockout"),
    (_res(s="true", verified="false", left="0"), "lockout"),
    (_res(s="false", err="identity check locked"), "lockout"),
    (_res(s="false", err="answer must be YYYY-MM-DD"), "unreadable"),
    (_res(s="false", err="could not read the date"), "unreadable"),
    (_res(s="false", err="something odd"), "unreadable"),
    (_res(s="false", err="answer does not match"), "wrong"),
    (_res(s="", verified="true"), "transport_fail"),
    (_res(s="None"), "transport_fail"),
    (_res(s="null"), "transport_fail"),
])
def test_verify_class_table(res, cls):
    assert verify_class(res) == cls


def test_verify_class_counted_by_left_drop():
    r = _res(s="false", err="nope", left="1")
    r["prev_left"] = "2"
    assert verify_class(r) == "wrong"


@pytest.mark.parametrize("bad", [None, {}, {"s": None}, {"s": 5, "left": "x"}, "junk"])
def test_verify_class_total_on_bad_input(bad):
    assert verify_class(bad) in ("transport_fail", "unreadable", "verified", "wrong", "lockout", "all_done")


@pytest.mark.parametrize("text,cls,q", [
    ("Hi, yes.", "confirm", ""), ("Yes, what is this about?", "confirm", "why"), ("Yes, who is this?", "confirm", "who"),
    ("Yes?", "greeting", ""), ("Daniel.", "confirm", ""), ("Mr Reyes.", "confirm", ""), ("Reyes?", "question", "other"),
    ("Yes, speaking. Sorry, my father died last week.", "confirm", ""), ("Yes, this is his son.", "third_party", ""),
    ("Yes, but I'm not him.", "third_party", ""),
])
def test_r1_right_party_review_cases(text, cls, q):
    r = rp_classify(text, "", ["Daniel", "Reyes"])
    assert (r["cls"], r["q"]) == (cls, q), r
