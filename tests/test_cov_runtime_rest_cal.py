"""Coverage + behaviour tests for runtime/cal.py (docs/CONTRACTS.md B.4, C.2): now parsing, business-day
helpers on degenerate calendars, holiday-rule expansion edge cases, date-rule totality and callback windows.
Every public function is "total on bad input": it returns its documented empty value instead of raising."""
import datetime

import pytest

from runtime import cal as C
from runtime.cal import (add_bd, callback_check, callback_dates, end_of_month, eval_date_rule,
                         expand_holiday_rules, from_iso, last_bd_of_month, last_bd_of_week, next_bd, parse_hhmm,
                         parse_now, prepare, prev_bd, week_start_of)

D = datetime.date
NO_BD = {"wd": [7], "hol": []}          # a calendar whose weekday list can never match: no business day at all


class _BadStr:
    def __str__(self):
        raise ValueError("unprintable")


# ------------------------------------------------------------------ parse_now / from_iso / parse_hhmm
@pytest.mark.parametrize("s,out", [
    ("2026-01-07 12:30 am", (D(2026, 1, 7), 30)),          # 12 am is minute 0 of the day
    ("2026-01-07 12:30 pm", (D(2026, 1, 7), 750)),
    ("7/1/2026 9:15 pm", (D(2026, 1, 7), 21 * 60 + 15)),   # d/m/yyyy, day first
    ("7/1/2026", (D(2026, 1, 7), 0)),                       # date only -> minute 0
    ("1/13/2026", (D(2026, 1, 13), 0)),                     # month first only when the second number is > 12
    ("2026-01-07 25:00", (None, None)),                   # hour out of range
    ("2026-13-01", (None, None)),                         # month out of range
    ("2026-01-07T11:00junk", (None, None)),
    ("7/1/2026x", (None, None)),
])
def test_parse_now_edges(s, out):
    assert parse_now(s) == out


def test_unprintable_values_are_rejected_not_raised():
    assert parse_now(_BadStr()) == (None, None)
    assert from_iso(_BadStr()) is None
    assert parse_hhmm(_BadStr()) is None


def test_parse_hhmm_bounds():
    assert parse_hhmm("24:00") == 1440
    assert parse_hhmm("25:00") is None
    assert parse_hhmm("09:60") is None


# ------------------------------------------------------------------ prepare
def test_prepare_does_not_duplicate_a_rule_holiday_already_listed():
    c = prepare({"holidays": ["2026-12-25"], "holiday_rules": [{"kind": "fixed_md", "month": 12, "day": 25}]},
                D(2026, 1, 1))
    assert c["hol"] == ["2025-12-25", "2026-12-25", "2027-12-25", "2028-12-25"]


# ------------------------------------------------------------------ business-day helpers on degenerate input
def test_helpers_without_any_business_day():
    assert next_bd(NO_BD, D(2026, 1, 1)) is None
    assert prev_bd(NO_BD, D(2026, 1, 1)) is None
    assert add_bd(NO_BD, D(2026, 1, 1), 2) is None
    assert add_bd(NO_BD, D(2026, 1, 1), 0) == D(2026, 1, 1)      # n == 0 -> d itself
    assert last_bd_of_week(NO_BD, D(2026, 1, 1)) is None
    assert last_bd_of_month(NO_BD, D(2026, 1, 1)) is None
    assert callback_dates(NO_BD, {"business_days_ahead": 3}, D(2026, 1, 1)) == []


def test_helpers_are_total_on_a_missing_date():
    assert prev_bd({}, None) is None
    assert next_bd({}, None) is None
    assert week_start_of({}, None) is None
    assert last_bd_of_week({}, None) is None
    assert last_bd_of_month({}, None) is None
    assert end_of_month(None) is None


# ------------------------------------------------------------------ expand_holiday_rules
def test_range_rule_is_capped_at_370_days():
    out = expand_holiday_rules([{"kind": "range", "from": "2026-01-01", "to": "2027-06-01"}], [2026])
    assert len(out) == 370
    assert out[0] == "2026-01-01" and out[-1] == "2027-01-05"


def test_overlapping_rules_are_deduplicated():
    out = expand_holiday_rules([{"kind": "range", "from": "2026-01-01", "to": "2026-01-03"},
                                {"kind": "range", "from": "2026-01-02", "to": "2026-01-04"}], [2026])
    assert out == ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]
    out = expand_holiday_rules([{"kind": "fixed_md", "month": 1, "day": 1},
                                {"kind": "fixed_md", "month": 1, "day": 1}], [2026])
    assert out == ["2026-01-01"]


def test_bad_rule_years_and_weekdays():
    # an unusable year skips that rule (the next rule still expands); unusable weekdays -> []
    out = expand_holiday_rules([{"kind": "fixed_md", "month": 1, "day": 1},
                                {"kind": "fixed_md", "month": 12, "day": 25}], ["x"])
    assert out == []
    out = expand_holiday_rules(["not a rule", {"kind": "fixed_md", "month": 12, "day": 25}], [2026])
    assert out == ["2026-12-25"]
    assert expand_holiday_rules([{"kind": "fixed_md", "month": 1, "day": 1}], [2026], 5) == []


def test_observed_shift_gives_up_when_every_candidate_is_taken():
    # Mondays only, and every Monday of the next 30 days is already a holiday: no observed day is added
    taken = [C.iso(D(2026, 1, 1) + datetime.timedelta(days=i)) for i in range(60)]
    assert C._c_observe(D(2026, 1, 4), "next_monday", [0], taken) is None
    rules = [{"kind": "range", "from": "2026-01-01", "to": "2026-03-01"},
             {"kind": "fixed_md", "month": 1, "day": 4, "observed": "next_monday"}]
    out = expand_holiday_rules(rules, [2026], [0])
    assert out == taken


# ------------------------------------------------------------------ eval_date_rule totality
def test_eval_date_rule_overflow_is_none():
    assert eval_date_rule({}, {"kind": "nth_calendar_day_after_today", "n": 5}, D(9999, 12, 30), {}) is None


# ------------------------------------------------------------------ callback_dates / callback_check
def test_callback_dates_merge_business_and_calendar_days():
    # Friday 2 Jan 2026: business days Mon 5, Tue 6; calendar days Sat 3, Sun 4, Mon 5 (deduplicated)
    out = callback_dates(None, {"business_days_ahead": 2, "calendar_days_ahead": 3}, D(2026, 1, 2))
    assert out == [D(2026, 1, 3), D(2026, 1, 4), D(2026, 1, 5), D(2026, 1, 6)]


def test_callback_dates_bad_today_is_empty():
    assert callback_dates(None, {"calendar_days_ahead": 3}, None) == []


def test_callback_window_with_unreadable_bounds_never_matches():
    cb = {"business_days_ahead": 5, "windows": [{"from": "nine", "to": "17:00"}]}
    assert callback_check(None, cb, D(2026, 1, 5), 600, D(2026, 1, 6), 720) == "outside"


def test_callback_non_business_window():
    cb = {"calendar_days_ahead": 7, "windows": [{"from": "10:00", "to": "14:00", "days": "non_business"}]}
    today = D(2026, 1, 5)                                             # Monday
    assert callback_check(None, cb, today, 600, D(2026, 1, 6), 720) == "outside"   # Tuesday is a business day
    assert callback_check(None, cb, today, 600, D(2026, 1, 10), 720) == "ok"       # Saturday
