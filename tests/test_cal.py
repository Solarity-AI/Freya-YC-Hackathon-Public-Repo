"""Tests for runtime/cal.py (agent 1). Scenarios mirror docs/edge-cases/EDGE-CASES.md (DAT-*) on a Mon-Fri calendar
with a fixed holiday list (test data only)."""
from datetime import date

import pytest

from runtime import cal as C

D = date.fromisoformat
CAL_SPEC = {
    "business_weekdays": [0, 1, 2, 3, 4],
    "holidays": ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"],
    "holiday_rules": [],
    "week_start": 0,
    "count_from": "after_today",
    "numeric_order": "DMY",
    "this_next": {"this": "current_week", "next": "following_week"},
}
CB = {
    "date_rule": {"include_today": True, "today_must_be_business_day": False, "business_days_ahead": 1,
                  "calendar_days_ahead": 0},
    "windows": [{"from": "10:00", "to": "19:00", "inclusive_from": True, "inclusive_to": True, "days": "any"}],
    "after_now": True, "min_lead_minutes": 0, "reask_limit": 1, "vague_asks": 1,
}


def cal_at(today, **over):
    spec = dict(CAL_SPEC)
    spec.update(over)
    return C.prepare(spec, D(today) if isinstance(today, str) else today)


# ---------------------------------------------------------------- parse_now / iso

@pytest.mark.parametrize("s,exp", [
    ("2026-10-14T11:00", ("2026-10-14", 660)),
    ("2026-10-14 11:00", ("2026-10-14", 660)),
    ("2026-10-14T11:00:00", ("2026-10-14", 660)),
    ("2026-10-14T11:00:00Z", ("2026-10-14", 660)),
    ("2026-10-14T11:00:00.000Z", ("2026-10-14", 660)),
    ("2026-10-14T11:00:00+01:00", ("2026-10-14", 660)),
    ("2026-11-10 11:00", ("2026-11-10", 660)),
    ("  2026-10-14T23:59  ", ("2026-10-14", 1439)),
    ("2026-10-14", ("2026-10-14", 0)),
    ("2026-10-14 07:30 pm", ("2026-10-14", 1170)),
    ("10/11/2026 11:00", ("2026-11-10", 660)),
    ("11/25/2026 11:00", ("2026-11-25", 660)),
])
def test_parse_now_ok(s, exp):
    d, m = C.parse_now(s)
    got = (C.iso(d), m)
    assert got == exp


@pytest.mark.parametrize("s", ["", None, "garbage", "2026-13-01T11:00", "2026-10-14T25:00", "2026-02-30T10:00",
                               "14 Oct 2026", 12345, "2026-10-14T11"])
def test_parse_now_bad(s):
    assert C.parse_now(s) == (None, None)


def test_iso_roundtrip_and_bad():
    assert C.iso(D("2027-01-04")) == "2027-01-04"
    assert C.from_iso("2027-01-04") == D("2027-01-04")
    assert C.from_iso("2026-10-14T11:00") == D("2026-10-14")
    assert C.from_iso(D("2026-10-14")) == D("2026-10-14")
    for bad in ("", None, "2026-02-30", "x", 5):
        assert C.from_iso(bad) is None
    assert C.iso(None) == ""
    assert C.iso("2026-10-14") == ""


def test_parse_hhmm():
    assert C.parse_hhmm("10:00") == 600
    assert C.parse_hhmm("19:00") == 1140
    assert C.parse_hhmm("bad") is None
    assert C.parse_hhmm(None) is None
    assert C.parse_hhmm("10:75") is None


# ---------------------------------------------------------------- prepare / holidays

def test_prepare_shape_and_defaults():
    cal = cal_at("2026-10-14")
    assert cal["wd"] == [0, 1, 2, 3, 4]
    assert cal["hol"] == sorted(CAL_SPEC["holidays"])
    assert cal["week_start"] == 0 and cal["count_from"] == "after_today" and cal["numeric_order"] == "DMY"
    assert cal["this_next"] == {"this": "current_week", "next": "following_week"}
    d = C.prepare(None, None)
    assert d["wd"] == [0, 1, 2, 3, 4] and d["hol"] == [] and d["numeric_order"] == "DMY"
    bad = C.prepare({"business_weekdays": [9, "x"], "holidays": ["nope", "2026-10-26", "2026-10-26"], "week_start": 12,
                     "count_from": "?", "numeric_order": "QQQ", "this_next": "x"}, D("2026-10-14"))
    assert bad["wd"] == [0, 1, 2, 3, 4] and bad["hol"] == ["2026-10-26"] and bad["week_start"] == 0
    assert bad["count_from"] == "after_today" and bad["numeric_order"] == "DMY"


def test_prepare_expands_rules_for_window_years():
    cal = C.prepare(dict(CAL_SPEC, holidays=[], holiday_rules=[{"kind": "fixed_md", "month": 12, "day": 25}]), D("2026-10-14"))
    assert cal["hol"] == ["2025-12-25", "2026-12-25", "2027-12-25", "2028-12-25"]


def test_expand_fixed_nth_last_range():
    rules = [{"kind": "fixed_md", "month": 7, "day": 4},
             {"kind": "nth_weekday", "month": 11, "weekday": 3, "n": 4},
             {"kind": "last_weekday", "month": 5, "weekday": 0},
             {"kind": "range", "from": "2026-12-24", "to": "2026-12-28"}]
    out = C.expand_holiday_rules(rules, [2026])
    assert "2026-07-04" in out and "2026-11-26" in out and "2026-05-25" in out
    for d in ("2026-12-24", "2026-12-25", "2026-12-26", "2026-12-27", "2026-12-28"):
        assert d in out
    assert out == sorted(out)


def test_expand_observed_shifts():
    out = C.expand_holiday_rules([{"kind": "fixed_md", "month": 7, "day": 4, "observed": "nearest_weekday"}], [2026])
    assert out == ["2026-07-03", "2026-07-04"]  # Saturday -> Friday
    out = C.expand_holiday_rules([{"kind": "fixed_md", "month": 7, "day": 5, "observed": "nearest_weekday"}], [2026])
    assert out == ["2026-07-05", "2026-07-06"]  # Sunday -> Monday
    out = C.expand_holiday_rules([{"kind": "fixed_md", "month": 12, "day": 26, "observed": "next_monday"}], [2026])
    assert out == ["2026-12-26", "2026-12-28"]
    # chained: both land on the weekend, the second is pushed past the first observed day
    rules = [{"kind": "fixed_md", "month": 12, "day": 26, "observed": "next_business_day"},
             {"kind": "fixed_md", "month": 12, "day": 27, "observed": "next_business_day"}]
    assert C.expand_holiday_rules(rules, [2026]) == ["2026-12-26", "2026-12-27", "2026-12-28", "2026-12-29"]
    # a weekday holiday is not shifted
    assert C.expand_holiday_rules([{"kind": "fixed_md", "month": 12, "day": 25, "observed": "next_monday"}], [2026]) == ["2026-12-25"]


def test_expand_bad_rules_ignored():
    rules = [{"kind": "fixed_md", "month": 2, "day": 30}, {"kind": "nth_weekday", "month": 2, "weekday": 0, "n": 5},
             {"kind": "nope"}, "junk", None, {"kind": "range", "from": "2026-12-28", "to": "2026-12-24"},
             {"kind": "nth_weekday", "month": 13, "weekday": 0}]
    assert C.expand_holiday_rules(rules, [2026]) == []
    assert C.expand_holiday_rules(None, None) == []


def test_holiday_rules_used_by_business_days():
    cal = C.prepare(dict(CAL_SPEC, holidays=[], holiday_rules=[{"kind": "range", "from": "2026-12-24", "to": "2027-01-01"}]),
                    D("2026-12-21"))
    assert C.next_bd(cal, D("2026-12-23")) == D("2027-01-04")


# ---------------------------------------------------------------- business days

def test_is_bd():
    cal = cal_at("2026-10-14")
    assert C.is_bd(cal, D("2026-10-14"))
    assert not C.is_bd(cal, D("2026-10-17"))
    assert not C.is_bd(cal, D("2026-10-26"))
    assert C.is_bd(None, D("2026-10-14"))
    assert not C.is_bd(cal, None)


def test_next_prev_bd():
    cal = cal_at("2026-11-10")
    assert C.next_bd(cal, D("2026-11-10")) == D("2026-11-12")  # DAT-01: tomorrow is a holiday
    assert C.next_bd(cal, D("2026-10-23")) == D("2026-10-27")  # DAT-12: weekend + Monday holiday
    assert C.next_bd(cal, D("2026-10-14"), include=True) == D("2026-10-14")
    assert C.prev_bd(cal, D("2026-10-27")) == D("2026-10-23")
    assert C.prev_bd(cal, D("2026-10-24"), include=True) == D("2026-10-23")
    assert C.next_bd(cal, None) is None


@pytest.mark.parametrize("today,n,exp", [
    ("2026-10-14", 12, "2026-11-02"),  # DAT-04 early deadline skips 10-26
    ("2026-10-14", 7, "2026-10-23"),
    ("2026-11-10", 7, "2026-11-20"),  # DAT-05
    ("2026-11-10", 12, "2026-11-30"),
    ("2026-10-24", 7, "2026-11-04"),  # DAT-09 weekend now
    ("2026-12-28", 7, "2027-01-07"),  # DAT-19 year rollover
    ("2026-10-14", 0, "2026-10-14"),
])
def test_add_bd(today, n, exp):
    assert C.add_bd(cal_at(today), D(today), n) == D(exp)


def test_add_bd_custom_week():
    cal = cal_at("2026-10-14", business_weekdays=[0, 1, 2, 3, 4, 5])  # DAT-67 Mon-Sat
    assert C.add_bd(cal, D("2026-10-14"), 7) == D("2026-10-22")
    assert C.is_bd(cal, D("2026-10-17"))
    assert C.add_bd(cal, D("2026-10-14"), "x") is None


def test_week_helpers_and_month_ends():
    cal = cal_at("2026-10-14")
    assert C.week_start_of(cal, D("2026-10-14")) == D("2026-10-12")
    assert C.week_start_of(cal_at("2026-10-14", week_start=6), D("2026-10-14")) == D("2026-10-11")
    assert C.last_bd_of_week(cal, D("2026-10-14")) == D("2026-10-16")
    assert C.last_bd_of_week(cal, D("2026-12-24")) == D("2026-12-24")  # Friday 12-25 is a holiday
    assert C.end_of_month(D("2026-02-10")) == D("2026-02-28")
    assert C.end_of_month(D("2026-12-03")) == D("2026-12-31")
    assert C.last_bd_of_month(cal, D("2026-10-14")) == D("2026-10-30")
    assert C.last_bd_of_month(cal, D("2027-01-05")) == D("2027-01-29")
    assert C.end_of_month(None) is None
    allhol = C.prepare(dict(CAL_SPEC, business_weekdays=[5]), D("2026-10-14"))
    assert C.last_bd_of_week(allhol, D("2026-10-12")) == D("2026-10-17")


# ---------------------------------------------------------------- date rules

R_ATT1 = {"kind": "last_business_day_of_week", "if_today": "next_week"}


@pytest.mark.parametrize("today,exp", [
    ("2026-10-14", "2026-10-16"),
    ("2026-10-16", "2026-10-23"),  # DAT-07 today is Friday
    ("2026-12-24", "2026-12-31"),  # DAT-08 Friday holiday, next week's Friday also a holiday
    ("2026-12-23", "2026-12-24"),
    ("2026-12-18", "2026-12-24"),
    ("2026-10-24", "2026-10-30"),  # weekend now
    ("2026-11-25", "2026-11-27"),
])
def test_rule_attempt1(today, exp):
    assert C.eval_date_rule(cal_at(today), R_ATT1, D(today), {}) == D(exp)


def test_rule_last_bd_of_week_keep_and_default():
    cal = cal_at("2026-10-16")
    assert C.eval_date_rule(cal, {"kind": "last_business_day_of_week", "if_today": "keep"}, D("2026-10-16"), {}) == D("2026-10-16")
    assert C.eval_date_rule(cal, {"kind": "last_business_day_of_week"}, D("2026-10-16"), {}) == D("2026-10-23")


def test_rule_kinds():
    t = D("2026-10-14")
    cal = cal_at(t)
    ev = lambda r, ctx=None: C.eval_date_rule(cal, r, t, ctx or {})
    assert ev({"kind": "today"}) == t
    assert ev({"kind": "next_business_day"}) == D("2026-10-15")
    assert ev({"kind": "nth_business_day_after_today", "n": 12}) == D("2026-11-02")
    assert ev({"kind": "nth_calendar_day_after_today", "n": 10}) == D("2026-10-24")
    assert ev({"kind": "nth_calendar_day_after_today", "n": 10, "roll": "prev_bd"}) == D("2026-10-23")  # DAT-50a
    assert ev({"kind": "nth_calendar_day_after_today", "n": 10, "roll": "next_bd"}) == D("2026-10-27")
    assert ev({"kind": "end_of_month"}) == D("2026-10-31")
    assert ev({"kind": "end_of_month", "roll": "prev_bd"}) == D("2026-10-30")
    assert ev({"kind": "last_business_day_of_month"}) == D("2026-10-30")
    assert ev({"kind": "deadline"}, {"deadline": D("2026-10-23")}) == D("2026-10-23")
    assert ev({"kind": "deadline"}, {"deadline": "2026-10-23"}) == D("2026-10-23")
    assert ev({"kind": "deadline"}) is None
    assert ev({"kind": "fixed", "date": "2026-12-01"}) == D("2026-12-01")
    mn = {"kind": "min", "args": [{"kind": "deadline"}, {"kind": "nth_business_day_after_today", "n": 3}]}
    assert ev(mn, {"deadline": D("2026-10-23")}) == D("2026-10-19")
    mx = {"kind": "max", "args": [{"kind": "today"}, {"kind": "fixed", "date": "2026-10-01"}, {"kind": "bogus"}]}
    assert ev(mx) == t
    assert ev({"kind": "min", "args": []}) is None


def test_rule_including_today_and_month_rollover():
    t = D("2026-10-14")
    cal = cal_at(t, count_from="including_today")
    assert C.eval_date_rule(cal, {"kind": "nth_business_day_after_today", "n": 10}, t, {}) == D("2026-10-28")
    assert C.eval_date_rule(cal, {"kind": "nth_business_day_after_today", "n": 1}, t, {}) == t
    sat = D("2026-10-24")
    assert C.eval_date_rule(cal_at(sat, count_from="including_today"),
                            {"kind": "nth_business_day_after_today", "n": 1}, sat, {}) == D("2026-10-27")
    late = D("2026-10-31")
    assert C.eval_date_rule(cal_at(late), {"kind": "last_business_day_of_month"}, late, {}) == D("2026-11-30")


@pytest.mark.parametrize("rule", [None, "x", {}, {"kind": "unknown"}, {"kind": "fixed", "date": "nope"},
                                  {"kind": "nth_business_day_after_today", "n": "abc"}])
def test_rule_bad_inputs_never_raise(rule):
    r = C.eval_date_rule(cal_at("2026-10-14"), rule, D("2026-10-14"), {})
    assert r is None or isinstance(r, date)


def test_rule_bad_today_and_deep_nesting():
    assert C.eval_date_rule(None, {"kind": "today"}, None, None) is None
    r = {"kind": "min", "args": [{"kind": "today"}]}
    for _ in range(20):
        r = {"kind": "min", "args": [r]}
    assert C.eval_date_rule(None, r, D("2026-10-14"), None) is None


# ---------------------------------------------------------------- weekday_date

@pytest.mark.parametrize("today,wd,which,tn,exp", [
    ("2026-10-14", 4, "bare", None, "2026-10-16"),
    ("2026-10-14", 2, "bare", None, "2026-10-14"),  # today counts in cal.weekday_date
    ("2026-10-14", 0, "bare", None, "2026-10-19"),
    ("2026-10-14", 4, "this", None, "2026-10-16"),
    ("2026-10-14", 0, "this", None, "2026-10-12"),  # DAT-18: this Monday has passed
    ("2026-10-14", 4, "next", None, "2026-10-23"),  # DAT-10a
    ("2026-10-16", 4, "next", None, "2026-10-23"),  # DAT-10b
    ("2026-10-16", 4, "this", None, "2026-10-16"),  # DAT-10c
    ("2026-10-24", 4, "next", None, "2026-10-30"),  # DAT-49a
    ("2026-10-24", 4, "this", None, "2026-10-23"),  # DAT-49b (past)
    ("2026-10-25", 0, "next", None, "2026-10-26"),  # DAT-49c
    ("2026-10-14", 4, "next", {"this": "current_week", "next": "first_after_today"}, "2026-10-16"),  # DAT-68
    ("2026-10-14", 4, "next", {"this": "current_week", "next": "skip_one"}, "2026-10-23"),
    ("2026-10-14", 2, "next", {"this": "current_week", "next": "first_after_today"}, "2026-10-21"),
    ("2026-10-14", 0, "this", {"this": "next_occurrence", "next": "following_week"}, "2026-10-19"),
    ("2026-10-14", "friday", "bare", None, "2026-10-16"),
    ("2026-10-14", "Fri", "next", None, "2026-10-23"),
])
def test_weekday_date(today, wd, which, tn, exp):
    cal = cal_at(today, this_next=tn) if tn else cal_at(today)
    assert C.weekday_date(cal, D(today), wd, which) == D(exp)


def test_weekday_date_bad():
    cal = cal_at("2026-10-14")
    assert C.weekday_date(cal, D("2026-10-14"), "blursday", "bare") is None
    assert C.weekday_date(cal, D("2026-10-14"), 9, "bare") is None
    assert C.weekday_date(cal, None, 1, "bare") is None


# ---------------------------------------------------------------- spoken / wire

def test_spoken_date():
    assert C.spoken_date(D("2026-01-09"), D("2026-01-07")) == "Friday, 9 January"
    assert C.spoken_date(D("2027-01-04"), D("2026-12-28")) == "Monday, 4 January 2027"
    assert C.spoken_date(D("2026-10-23"), None) == "Friday, 23 October"
    assert C.spoken_date(None, None) == ""


def test_wire_date_and_time():
    d = D("2026-11-02")
    assert C.wire_date(d, "%Y-%m-%d") == "2026-11-02"
    assert C.wire_date(d, "") == "2026-11-02"
    assert C.wire_date(d, "%d/%m/%Y") == "02/11/2026"  # DAT-65
    assert C.wire_date(d, "%Y%m%d") == "20261102"
    assert C.wire_date(d, "%m-%d-%y") == "11-02-26"
    assert C.wire_date(d, "%Y-%m-%dT%H:%M:%S", 660) == "2026-11-02T11:00:00"
    assert C.wire_date(d, "%Y-%m-%dT%H:%M:%S") == "2026-11-02T00:00:00"
    assert C.wire_date(d, "day %d %Q") == "day 02 %Q"
    assert C.wire_date(None, "%Y") == ""
    assert C.wire_time(660, "%H:%M") == "11:00"
    assert C.wire_time(65) == "01:05"
    assert C.wire_time(1140, "") == "19:00"
    assert C.wire_time(660, "%H:%M:%S") == "11:00:00"
    assert C.wire_time("bad", "%H:%M") == ""


# ---------------------------------------------------------------- callbacks

@pytest.mark.parametrize("today,exp", [
    ("2026-10-14", ["2026-10-14", "2026-10-15"]),
    ("2026-10-16", ["2026-10-16", "2026-10-19"]),  # DAT-35
    ("2026-10-23", ["2026-10-23", "2026-10-27"]),  # DAT-36 Monday holiday
    ("2026-10-24", ["2026-10-24", "2026-10-27"]),  # DAT-47 weekend now
    ("2026-11-10", ["2026-11-10", "2026-11-12"]),  # DAT-46b
])
def test_callback_dates(today, exp):
    assert [C.iso(x) for x in C.callback_dates(cal_at(today), CB, D(today))] == exp


def test_callback_dates_variants():
    t = D("2026-10-24")
    cal = cal_at(t)
    dr = {"include_today": True, "today_must_be_business_day": True, "business_days_ahead": 2, "calendar_days_ahead": 0}
    assert [C.iso(x) for x in C.callback_dates(cal, dr, t)] == ["2026-10-27", "2026-10-28"]
    dr = {"include_today": False, "today_must_be_business_day": False, "business_days_ahead": 0, "calendar_days_ahead": 3}
    assert [C.iso(x) for x in C.callback_dates(cal, {"date_rule": dr}, t)] == ["2026-10-25", "2026-10-26", "2026-10-27"]
    assert C.callback_dates(cal, None, t) == []


@pytest.mark.parametrize("now,d,t,exp", [
    ("2026-10-14T11:00", "2026-10-14", 1140, "ok"),  # DAT-37a 19:00 inclusive
    ("2026-10-14T11:00", "2026-10-15", 600, "ok"),  # DAT-37b 10:00 inclusive
    ("2026-10-14T11:00", "2026-10-14", 1170, "outside"),  # DAT-37c 19:30
    ("2026-10-14T11:00", "2026-10-14", 660, "past"),  # DAT-37d not later than now
    ("2026-10-14T11:00", "2026-10-14", 600, "past"),
    ("2026-10-14T11:00", "2026-10-14", 720, "ok"),
    ("2026-10-14T11:00", "2026-10-13", 720, "past"),
    ("2026-10-14T11:00", "2026-10-16", 720, "outside"),  # beyond the next business day
    ("2026-10-14T11:00", "2026-10-15", 599, "outside"),
    ("2026-10-16T15:00", "2026-10-17", 900, "outside"),  # DAT-35 Saturday
    ("2026-10-16T15:00", "2026-10-19", 900, "ok"),
    ("2026-10-23T17:00", "2026-10-26", 720, "outside"),  # DAT-36 holiday Monday
    ("2026-10-23T17:00", "2026-10-27", 660, "ok"),  # DAT-46a
    ("2026-10-14T19:30", "2026-10-14", 1230, "outside"),  # DAT-38
    ("2026-10-14T19:30", "2026-10-15", 1080, "ok"),
    ("2026-10-24T11:00", "2026-10-24", 960, "ok"),  # DAT-47a
    ("2026-10-24T11:00", "2026-10-25", 720, "outside"),
])
def test_callback_check(now, d, t, exp):
    today, nm = C.parse_now(now)
    assert C.callback_check(cal_at(today), CB, today, nm, D(d), t) == exp


def test_callback_check_windows_gaps_lead_and_exclusive():
    today, nm = C.parse_now("2026-10-14T11:30")  # DAT-66
    cb = dict(CB, min_lead_minutes=60, windows=[
        {"from": "09:00", "to": "12:00", "inclusive_from": True, "inclusive_to": True, "days": "business"},
        {"from": "14:00", "to": "18:00", "inclusive_from": True, "inclusive_to": False, "days": "business"}])
    cal = cal_at(today)
    assert C.callback_check(cal, cb, today, nm, today, 720) == "outside"  # inside window but inside the lead time
    assert C.callback_check(cal, cb, today, nm, today, 840) == "ok"
    assert C.callback_check(cal, cb, today, nm, today, 780) == "outside"  # gap
    assert C.callback_check(cal, cb, today, nm, today, 1080) == "outside"  # exclusive end
    sat, nm2 = C.parse_now("2026-10-24T09:00")
    assert C.callback_check(cal_at(sat), cb, sat, nm2, sat, 840) == "outside"  # business-day windows only
    nb = dict(CB, windows=[{"from": "10:00", "to": "12:00", "inclusive_from": False, "inclusive_to": True, "days": "non_business"}])
    assert C.callback_check(cal_at(sat), nb, sat, nm2, sat, 600) == "outside"
    assert C.callback_check(cal_at(sat), nb, sat, nm2, sat, 660) == "ok"


def test_callback_check_bad_inputs():
    t = D("2026-10-14")
    cal = cal_at(t)
    assert C.callback_check(cal, CB, t, 660, None, 700) == "outside"
    assert C.callback_check(cal, CB, t, 660, t, None) == "outside"
    assert C.callback_check(cal, None, t, 660, t, 700) == "outside"  # no date rule -> no allowed dates
    assert C.callback_check(cal, {"date_rule": CB["date_rule"]}, t, 660, t, 700) == "ok"  # no windows -> any time
    assert C.callback_check(cal, CB, None, 660, t, 700) == "outside"
    assert C.callback_check(cal, CB, t, 660, "2026-10-15", 700) == "ok"
    assert C.callback_check(cal, CB, t, 660, t, "x") == "outside"


def test_runtime_rules_brace_and_import_safety():
    import pathlib
    src = (pathlib.Path(C.__file__)).read_text()
    assert "{{" not in src and "}}" not in src
    assert "datetime.now" not in src and "date.today" not in src
    for line in src.splitlines():
        if line.startswith(("import ", "from ")):
            assert line in ("import re", "import datetime", "from datetime import date, timedelta"), line
