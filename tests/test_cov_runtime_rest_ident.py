"""Coverage + behaviour tests for runtime/ident.py (docs/CONTRACTS.md C.4): right-party classifier branches,
identity answer normalisation (date / digits / year / alnum / text) and the verify-result classifier.

Fault-injection tests (monkeypatching a helper to raise) check the module rule "total on bad input": the
classifier and normaliser must degrade to a safe answer instead of crashing the ctl node."""
import datetime

import pytest

from runtime import ident as I
from runtime.ident import id_answer, rp_classify, verify_class

TODAY = datetime.date(2026, 10, 14)
NAMES = ["Jordan", "Lee"]

Q_DATE = {"key": "dob", "kind": "date", "numeric_order": "DMY", "wire_format": "%Y-%m-%d",
          "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}
Q_DIG4 = {"key": "tail", "field_value": "number_last4", "kind": "digits", "length": 4, "pattern": "^[0-9]{4}$",
          "ask": "What are the last four digits?"}
Q_CODE4 = {"key": "code", "field_value": "member_code", "kind": "digits", "length": 4, "pattern": "^[0-9]{4}$",
           "ask": "Your member code?"}
Q_YEAR = {"key": "yr", "kind": "year", "wire_format": "%Y", "pattern": "^[0-9]{4}$"}
Q_ALNUM6 = {"key": "pc", "field_value": "code", "kind": "alnum", "wire_format": "upper_nospace", "length": 6,
            "pattern": "", "ask": "Your reference?"}


def _boom(*_a, **_k):
    raise RuntimeError("injected")


# ------------------------------------------------------------------ rp_classify: remaining branches
@pytest.mark.parametrize("text,cls,q", [
    # "yes" + a question without a known type, longer than three words -> a question, not a confirmation
    ("yes is this about my account?", "question", "other"),
    # "yes" with a hedge is not a confirmation
    ("yeah maybe", "unclear", ""),
    ("yes, I think it might be", "unclear", ""),
    # a lone "Yeah?" is a greeting, "Yes, <why question>" confirms and carries the why
    ("Yeah?", "greeting", ""),
    ("Yes, but what do you want with me exactly then?", "confirm", "why"),
    # strong first sentence + own name in "<name> here" form (any case) confirms
    ("Yes. Lee here.", "confirm", ""),
    ("Yes. jordan here.", "confirm", ""),
    # a strong first-sentence confirmation is not undone by later chatter about a relative
    ("Yes, speaking. My wife is out.", "confirm", ""),
    # title + surname / first + last name alone confirms
    ("Mr Lee.", "confirm", ""),
    ("Jordan Lee.", "confirm", ""),
    # a different capitalised first name -> someone else, even after "yes"
    ("Yes. this is Sam.", "third_party", ""),
    # an unrecognised question with no yes -> question/other
    ("umm okay then?", "question", "other"),
])
def test_rp_classify_more_branches(text, cls, q):
    r = rp_classify(text, None, NAMES)
    assert r["cls"] == cls, (text, r)
    assert r["q"] == q, (text, r)
    assert r["hold"] is False


def test_rp_classify_lowercase_other_name_is_not_someone_else():
    # "it's raining": the token after "it's" is not capitalised, so it is not a (different) name
    r = rp_classify("oh it's raining here", None, NAMES)
    assert r["cls"] != "third_party"


def test_rp_classify_survives_norm_failure(monkeypatch):
    # _i_text falls back to a folded, stripped copy of the text when norm() fails
    monkeypatch.setattr(I, "norm", _boom)
    assert I._i_text("  Yes, SPEAKING  ") == "yes, speaking"
    assert rp_classify("Yes, speaking.", None, NAMES)["cls"] == "confirm"


def test_rp_classify_survives_last_clause_failure(monkeypatch):
    # the whole text is classified when the clause splitter fails
    monkeypatch.setattr(I, "last_clause", _boom)
    assert rp_classify("No.", None, NAMES)["cls"] == "deny"
    assert rp_classify("She's at work", None, NAMES)["cls"] == "third_party"


def test_rp_classify_survives_is_question_failure(monkeypatch):
    # without is_question a who-question with no '?' is still recognised by its wording
    monkeypatch.setattr(I, "is_question", _boom)
    r = rp_classify("who is this", None, NAMES)
    assert r == {"cls": "question", "q": "who", "hold": False}


def test_rp_classify_survives_is_greeting_failure(monkeypatch):
    monkeypatch.setattr(I, "is_greeting_only", _boom)
    assert rp_classify("Hi.", None, NAMES) == {"cls": "unclear", "q": "", "hold": False}
    # an explicit '?' still makes it a question
    assert rp_classify("Hm?", None, NAMES)["cls"] in ("greeting", "question")


def test_rp_classify_total_on_internal_error(monkeypatch):
    monkeypatch.setattr(I, "_i_rp", _boom)
    assert rp_classify("Yes, speaking.", None, NAMES) == {"cls": "unclear", "q": "", "hold": False}


def test_name_tokens_skip_initials_and_empty_values():
    # parts shorter than 2 letters are dropped, the whole value is kept; None / '' add nothing
    assert I._i_name_tokens(["J Lee"]) == {"lee", "j lee"}
    assert I._i_name_tokens([None, ""]) == set()
    assert I._i_name_tokens(None) == set()


def test_self_post_names():
    # "<name> here/speaking": a run glued to a digit has no word start, so it is not a name
    assert I._i_self_post("sam here") == ["sam"]
    assert I._i_self_post("yes, jordan speaking") == ["jordan"]
    assert I._i_self_post("9abc here") == []
    assert I._i_self_post("") == []


def test_capitalised_and_bare_name_are_total():
    assert I._i_capitalised("Yes this is Sam", "sam") is True
    assert I._i_capitalised("yes this is sam", "sam") is False
    assert I._i_capitalised(123, "sam") is False          # non-text raw -> False, no exception
    assert I._i_bare_name("Jordan.", 5) is False           # unusable name container -> False
    assert I._i_bare_name("Jordan.", {"jordan"}) is True
    assert I._i_bare_name("Mr.", {"jordan"}) is False       # only titles left -> not a name
    assert I._i_bare_name("Jordan?", {"jordan"}) is False


@pytest.mark.parametrize("text", [
    "I am afraid not.",
    "You are calling the wrong number.",
    "It is his phone.",
    "I am not sure.",
])
def test_rp_classify_denials_are_not_confirmations(text):
    assert rp_classify(text, None, NAMES)["cls"] != "confirm"


# ------------------------------------------------------------------ id_answer: date
def test_date_tens_year_completes_a_finished_utterance():
    assert id_answer(Q_DATE, "the fourteenth of march nineteen ninety.", "", TODAY) == \
        {"status": "complete", "wire": "1990-03-14"}
    assert id_answer(Q_DATE, "fourteenth of march twenty twenty.", "", TODAY) == \
        {"status": "complete", "wire": "2020-03-14"}


def test_date_tens_year_on_impossible_day_is_invalid():
    # 31 February: parse_dob leaves it incomplete, the tens year makes it a full (impossible) date -> invalid
    assert id_answer(Q_DATE, "the thirty first of february nineteen ninety.", "", TODAY) == {"status": "invalid"}


def test_date_fragment_join_and_no_value():
    r = id_answer(Q_DATE, "march", "fourteenth", TODAY)
    assert r == {"status": "incomplete", "frag": "fourteenth march"}
    # neither the text nor fragment+text is a date -> none, fragment ignored
    assert id_answer(Q_DATE, "banana", "hmm", TODAY) == {"status": "none"}


def test_date_wire_format_and_pattern():
    q = dict(Q_DATE, wire_format="%d/%m/%Y", pattern="")
    assert id_answer(q, "14 march 1990", "", TODAY) == {"status": "complete", "wire": "14/03/1990"}
    # the wire must match q.pattern, else invalid (never 'complete' with a bad wire)
    assert id_answer(dict(Q_DATE, pattern="^x"), "14 march 1990", "", TODAY) == {"status": "invalid"}
    # an unusable regex pattern is ignored
    assert id_answer(dict(Q_DATE, pattern="(["), "14 march 1990", "", TODAY) == \
        {"status": "complete", "wire": "1990-03-14"}


def test_date_wire_falls_back_to_iso(monkeypatch):
    monkeypatch.setattr(I, "wire_date", _boom)
    assert I._i_date_wire({"wire_format": "%d.%m.%Y"}, 1990, 3, 14) == "1990-03-14"
    assert I._i_date_wire({}, 1990, 2, 30) == ""


def test_tens_year_helper():
    assert I._i_tens_year("nineteen ninety.", None) == 1990
    assert I._i_tens_year("twenty twenty!", TODAY) == 2020
    assert I._i_tens_year("two thousand and ten.", TODAY) == 2010
    assert I._i_tens_year("nineteen ninety", TODAY) == 1990          # unpunctuated voice turn ends the year (PUB-03)
    assert I._i_tens_year("nineteen ninety...", TODAY) is None       # explicit trail-off -> may continue
    assert I._i_tens_year("nineteen ninety,", TODAY) is None
    assert I._i_tens_year("nineteen ten.", TODAY) is None            # more than 110 years ago
    assert I._i_tens_year("nineteen ninety.", "not a date") is None  # bad today -> None, no exception


# ------------------------------------------------------------------ id_answer: digits
def test_digits_without_length_take_everything():
    q = dict(Q_DIG4, length=0, pattern="")
    assert id_answer(q, "one two three", "", TODAY) == {"status": "complete", "wire": "123"}


def test_digits_too_long_last_n_vs_exact():
    assert id_answer(Q_DIG4, "one two three four five", "", TODAY) == {"status": "complete", "wire": "2345"}
    assert id_answer(Q_CODE4, "one two three four five", "", TODAY) == {"status": "invalid"}


def test_digits_fragment_overflow_restarts_from_the_new_digits():
    # 123 + 45 = five digits for a four-digit answer: keep only the new piece as the fragment
    assert id_answer(Q_DIG4, "four five", "123", TODAY) == {"status": "incomplete", "frag": "45"}
    assert id_answer(Q_CODE4, "four five", "123", TODAY) == {"status": "incomplete", "frag": "45"}
    assert id_answer(Q_DIG4, "four", "123", TODAY) == {"status": "complete", "wire": "1234"}
    assert id_answer(Q_DIG4, "banana", "12", TODAY) == {"status": "none"}


# ------------------------------------------------------------------ id_answer: year
def test_year_fragment_and_formats():
    assert id_answer(Q_YEAR, "1990", "", TODAY) == {"status": "complete", "wire": "1990"}
    assert id_answer(dict(Q_YEAR, wire_format="%y", pattern=""), "1990", "", TODAY) == \
        {"status": "complete", "wire": "90"}
    assert id_answer(dict(Q_YEAR, wire_format="%Y-%m", pattern=""), "1990", "", TODAY) == \
        {"status": "complete", "wire": "1990-01"}
    assert id_answer(Q_YEAR, "banana", "", TODAY) == {"status": "none"}


def test_year_fragment_used_when_text_alone_has_no_year(monkeypatch):
    seen = []

    def fake_parse_year(text, today=None):
        seen.append(text)
        return 1992 if text.startswith("nineteen") else None
    monkeypatch.setattr(I, "parse_year", fake_parse_year)
    assert id_answer(Q_YEAR, "two", "nineteen ninety", TODAY) == {"status": "complete", "wire": "1992"}
    assert seen == ["two", "nineteen ninety two"]


def test_year_wire_falls_back_to_digits(monkeypatch):
    monkeypatch.setattr(I, "wire_date", _boom)
    assert id_answer(dict(Q_YEAR, wire_format="%y", pattern=""), "1990", "", TODAY) == \
        {"status": "complete", "wire": "1990"}


def test_year_round_decade_in_words():
    assert id_answer(Q_YEAR, "Nineteen ninety.", "", TODAY) == {"status": "complete", "wire": "1990"}


# ------------------------------------------------------------------ id_answer: alnum / text / bad input
def test_alnum_lengths():
    assert id_answer(Q_ALNUM6, "A B 1", "", TODAY) == {"status": "incomplete", "frag": "AB1"}
    assert id_answer(Q_ALNUM6, "C 2 3", "AB1", TODAY) == {"status": "complete", "wire": "AB1C23"}
    assert id_answer(Q_ALNUM6, "C 2 3 4", "AB1", TODAY) == {"status": "invalid"}
    assert id_answer(Q_ALNUM6, "A B C 1 2 3 4", "", TODAY) == {"status": "invalid"}
    q_last = dict(Q_ALNUM6, field_value="ref_last6")
    assert id_answer(q_last, "A B C 1 2 3 4", "", TODAY) == {"status": "complete", "wire": "BC1234"}
    assert id_answer(Q_ALNUM6, "??", "", TODAY) == {"status": "none"}


def test_alnum_as_is_keeps_the_text():
    q = dict(Q_ALNUM6, wire_format="as_is", length=0)
    assert id_answer(q, " ab12 ", "", TODAY) == {"status": "complete", "wire": "ab12"}


def test_text_answers_and_bad_input():
    assert id_answer({"kind": "text"}, "  ...  ", "", TODAY) == {"status": "none"}
    assert id_answer({"kind": "text", "pattern": "^[A-Z]"}, "london.", "", TODAY) == {"status": "invalid"}
    assert id_answer(None, "Paris.", "", TODAY) == {"status": "none"}          # no question -> none, no crash
    assert id_answer("not a question", "x", "", TODAY) == {"status": "none"}


# ------------------------------------------------------------------ verify_class
@pytest.mark.parametrize("res,out", [
    (None, "transport_fail"),
    ({"s": "pending"}, "transport_fail"),
    ({"s": "true", "verified": "true", "all": "true"}, "all_done"),
    ({"s": "true"}, "verified"),
    ({"s": "true", "verified": "false"}, "wrong"),
    ({"s": "true", "err": "mismatch"}, "wrong"),
    ({"s": "true", "verified": "true", "left": "0"}, "verified"),
    ({"s": "false", "err": "Account locked"}, "lockout"),
    ({"s": "false", "err": "Too many attempts"}, "lockout"),
    ({"s": "false", "left": "0"}, "lockout"),
    ({"s": "false", "hint": "use YYYY-MM-DD"}, "hint:use YYYY-MM-DD"),
    ({"s": "false", "hint": "false", "err": "bad format"}, "unreadable"),
    ({"s": "false", "left": "1", "prev_left": "2"}, "wrong"),
    ({"s": "false", "left": "2.0", "prev_left": "2"}, "unreadable"),
    ({"s": "false", "err": "does not match"}, "wrong"),
    ({"s": "false", "err": "something odd"}, "unreadable"),
    ({"s": "false", "left": "abc"}, "unreadable"),
    ("not a dict", "transport_fail"),
])
def test_verify_class_table(res, out):
    assert verify_class(res) == out
