"""Regression tests for the TR final-rehearsal fixes: locale connectors and field rendering, half days (calendar and
validate), the 2-digit birth-year pivot, and linear replacements of regexes Sonar flagged for backtracking (S8786)."""
import datetime
import re
import time

import pytest

from builder import contract, ingest
from builder.pipeline import validate as V
from runtime import brain, cal
from runtime.ident import id_answer
from runtime.locale import and_word, date_phrase, money_digits
from runtime.parse import parse_dob, parse_year

TODAY = datetime.date(2026, 10, 11)
TR = {"bank": {"language": "tr", "currency": {"symbol": "TL", "word": "", "position": "after"}}}


# ------------------------------------------------------------------------------------------------ spoken output
def test_list_connector_follows_the_call_language():
    assert and_word("tr") == "ve" and and_word("en") == "and" and and_word("xx") == "and"
    assert brain._b_and(["A", "B", "C"], "tr") == "A, B ve C"
    assert brain._b_and(["A", "B"]) == "A and B"


def test_iso_field_is_spoken_as_a_date_and_amount_fields_keep_their_cents():
    assert brain._b_field_text("2026-10-15", TR, TODAY) == date_phrase(datetime.date(2026, 10, 15), TODAY, "tr")
    assert brain._b_field_text("2026-10-15T00:00:00", TR, TODAY) == "15 Ekim Perşembe"
    assert brain._b_field_text(3120.9, TR, TODAY) == "3.120,90"
    assert brain._b_field_text(14200.0, TR, TODAY) == "14.200"
    assert brain._b_field_text("5502", TR, TODAY) == "5502"
    assert brain._b_field_text("2026-10-1x", TR, TODAY) == "2026-10-1x"
    out = brain.render("<f:son_odeme_tarihi>", {"spec": TR, "today": TODAY,
                                                 "prod": {"f": {"son_odeme_tarihi": "2026-09-24"}}})
    assert out == "24 Eylül Perşembe" and not re.search(r"\d{4}-\d\d", out)


def test_money_has_two_decimals_only_with_cents():
    assert money_digits(535000, "tr") == "5.350" and money_digits(535050, "tr") == "5.350,50"
    assert money_digits(535005, "tr") == "5.350,05"


def test_date_phrase_adds_the_year_only_when_it_differs():
    assert date_phrase(datetime.date(2026, 11, 5), TODAY, "tr") == "5 Kasım Perşembe"
    assert date_phrase(datetime.date(2027, 1, 4), TODAY, "tr") == "4 Ocak 2027 Pazartesi"


# ------------------------------------------------------------------------------------------------ half days
CB = {"include_today": True, "business_days_ahead": 1, "windows": [{"from": "09:00", "to": "20:00", "days": "any"}]}


def _cal(**kw):
    c = {"business_weekdays": [0, 1, 2, 3, 4], "holidays": ["2026-10-29"],
         "half_days": [{"date": "2026-10-28", "from": "12:31"}]}
    c.update(kw)
    return cal.prepare(c, datetime.date(2026, 10, 27))


def test_callback_on_a_half_day_afternoon_is_outside():
    c, today = _cal(), datetime.date(2026, 10, 27)
    assert cal.callback_check(c, CB, today, 600, "2026-10-28", 19 * 60) == "outside"
    assert cal.callback_check(c, CB, today, 600, "2026-10-28", 12 * 60 + 31) == "outside"
    assert cal.callback_check(c, CB, today, 600, "2026-10-28", 12 * 60 + 30) == "ok"
    assert cal.callback_check(c, CB, today, 600, "2026-10-28", 11 * 60) == "ok"
    assert cal.callback_check(c, CB, today, 600, "2026-10-27", 19 * 60) == "ok"     # an ordinary day


def test_half_day_business_day_flag():
    d = datetime.date(2026, 10, 28)
    assert cal.is_bd(_cal(), d)                                          # default: still a business day
    assert not cal.is_bd(_cal(half_day_is_business_day=False), d)
    assert cal.prepare({"half_days": [{"date": "bad", "from": "13:00"}, "x"]}, TODAY)["half"] == {}


def _spec(lang="tr"):
    return {"bank": {"language": lang}, "calendar": {"holidays": []}}


def test_validate_takes_half_days_from_the_national_calendar_with_the_brief_time():
    s, dec = _spec(), []
    brief = ("Geri arama 09:00 ile 20:00 arasında yapılır, arife günleri de dahil.\n"
             "Arife günlerinde (yarım gün) geri arama yalnızca 09:00 ile 12:30 arası yapılabilir.")
    V._half_days(s, brief, dec)
    hd = s["calendar"]["half_days"]
    assert {"date": "2026-10-28", "from": "12:31"} in hd and all(h["from"] == "12:31" for h in hd)
    assert s["calendar"]["half_day_is_business_day"] is True and dec


def test_validate_half_days_default_time_and_no_ops():
    s = _spec()
    V._half_days(s, "Arife günleri yarım gündür.", [])
    assert s["calendar"]["half_days"][0]["from"] == "13:00"
    kept = {"bank": {"language": "tr"}, "calendar": {"half_days": [{"date": "2026-10-28", "from": "12:00"}]}}
    V._half_days(kept, "Arife günleri yarım gündür.", [])
    assert kept["calendar"]["half_days"] == [{"date": "2026-10-28", "from": "12:00"}]
    for spec, text in ((_spec(), "Normal iş günleri."), (_spec("en"), "Half days are short."), (_spec(), "")):
        V._half_days(spec, text, [])
        assert "half_days" not in spec["calendar"]


# ------------------------------------------------------------------------------------------------ birth-year pivot
@pytest.mark.parametrize("text,year", [("86", 1986), ("05", 2005), ("83", 1983), ("99", 1999)])
def test_two_digit_year_pivot(text, year):
    assert parse_year(text, TODAY) == year
    q = {"key": "year", "kind": "year", "wire_format": "%Y", "length": 4, "pattern": "", "two_digit_year": "pivot"}
    assert id_answer(q, text, "", TODAY) == {"status": "complete", "wire": str(year)}


def test_two_digit_dob_pivot_never_gives_a_future_or_child_birth_date():
    assert parse_dob("02.06.86", "DMY", TODAY)["y"] == 1986
    assert parse_dob("15.03.05", "DMY", TODAY)["y"] == 2005
    assert parse_dob("15.03.30", "DMY", TODAY)["y"] == 1930                       # 2030 is in the future
    assert parse_dob("15.03.10", "DMY", TODAY)["kind"] == "incomplete"            # 2010: under 18, 1910: over 100


# ------------------------------------------------------------------------------------------------ S8786 regexes
def _fast(fn, *a):
    t = time.perf_counter()
    fn(*a)
    return time.perf_counter() - t < 0.05


def test_br_lines_matches_the_old_regex_and_is_linear():
    old = lambda s: re.sub(r"\s*\n\s*", " <br> ", s)  # noqa: E731
    for t in ["a\nb", "a \n \n b", "\na", "a\n", "\n", "a\r\n b", "x", "a\n  \n\n c \n d"]:
        assert ingest._br_lines(t) == old(t)
    assert ingest._cell("a\n\n b|c") == "a <br> b\\|c"
    assert _fast(ingest._br_lines, " " * 200000 + "\n" + " " * 200000 + "x")


def test_question_line_matches_the_old_regex_and_is_linear():
    old = lambda ln: bool(re.match(r"^\s*(#+|\*\*|\d+[.)])?.{3,200}\?\s*(\*\*)?\s*$", ln))  # noqa: E731
    for t in ["What is it?", "**What?**", "1. How much is due?", "ab?", "   ab?", "# Q?", "x" * 250 + "?",
              "no question", "Is it? yes", "Why? **", "##" + "y" * 199 + "?"]:
        assert ingest._question_line(t) == old(t), t
    assert _fast(ingest._question_line, "#" * 200000 + "?" * 3)
    assert _fast(ingest._question_line, " " * 200000 + "a" * 200000 + "?")


def test_qa_line_regex_is_linear():
    assert ingest._QA_LINE_RE.match("S1: Arife iş günü mü?") and ingest._QA_LINE_RE.match("Soru 12) x")
    assert ingest._QA_LINE_RE.match("C : evet") and not ingest._QA_LINE_RE.match("Sorular burada")
    assert _fast(ingest._QA_LINE_RE.match, "soru" + " " * 100000 + "1" + " " * 100000)


def test_xml_number_is_regex_free():
    assert ingest._xml_number("ppt/slides/slide12.xml") == 12 and ingest._xml_number("slide.xml") == 0
    assert _fast(ingest._xml_number, "9" * 100000 + "x.xml")


def test_fenced_blocks_match_the_old_regex_and_are_linear():
    old = lambda t: re.findall(r"```(?:json|yaml|yml)?\s*\n(.*?)```", t or "", flags=re.S)  # noqa: E731
    for t in ["```json\n{a}\n```", "x ```yaml\nb: 1\n``` y ```\nc\n```", "```python\nx\n```\n{j}\n```",
              "```json\n{open", "````json\n{a}```", "```JSON\n{}\n```", "", None]:
        assert [x.strip() for x in contract._fenced_blocks(t)] == [x.strip() for x in old(t)], t
    assert _fast(contract._fenced_blocks, "```json\n" + "x" * 200000)
    assert _fast(contract._fenced_blocks, "```" * 50000)
    assert contract._openapi_in_text('```json\n{"openapi": "3.0.0", "paths": {}}\n```')["openapi"] == "3.0.0"
