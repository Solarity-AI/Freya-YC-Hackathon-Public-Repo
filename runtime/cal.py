"""Calendar, date rules and callback windows (docs/CONTRACTS.md B.4, C.2). Owner: agent 1.

Python 3.8 syntax; stdlib json/re/datetime only; no double curly braces anywhere; private names prefixed _c_;
total on bad input. Dates are datetime.date; times are minutes since midnight; weekdays Monday = 0.

CONTRACT NOTE (agent 1, readings chosen where docs/CONTRACTS.md C.2 is silent):
- parse_now: a date-only value gets minute 0; a zone suffix is dropped (no conversion); 'D/M/YYYY' is read
  day-first, month-first only when the second number is > 12.
- weekday_date accepts an int or an English weekday name. 'this'+next_occurrence = bare (today counts).
- eval_date_rule: last_business_day_of_week default if_today = 'next_week'; nth_business_day_after_today reads
  count_from from the rule first, then cal['count_from'].
- expand_holiday_rules(rules, years, wd=None): optional business weekdays for observed shifts (default Mon-Fri);
  an observed day is added next to the actual day, chained past other holidays.
- wire_date(d, fmt, minutes=None) also fills %H %M %S (from minutes, default 0) for date-time wire formats.
- callback_dates accepts the whole Spec.third_party.callback object or its date_rule.
- callback_check: d < today or (same day and t <= now when after_now) -> 'past'; inside the lead time -> 'outside'.
- Extras: parse_hhmm.
"""
import re
import datetime
from datetime import date, timedelta

_c_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_c_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
             "November", "December"]
# ISO-style now in three parts (one regex was too complex): the date, an optional time, then an optional zone + end.
# Each part is deterministic (a shorter digit run or an earlier stop is followed by a char the next part rejects).
_c_NOW_DATE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
_c_NOW_TIME = re.compile(r"[t ]+(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?\s*(am|pm)?")
_c_NOW_ZONE = re.compile(r"\s*(?:z|[+-]\d{2}:?\d{2})?$")
# d/m/yyyy now, split the same way: the date, then an optional time running to the end
_c_NOW_SLD = re.compile(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})")
_c_NOW_SLT = re.compile(r"[t ,]+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)?$")
_c_END = re.compile(r"$")
_c_LIMIT = 800


def _c_date(y, m, d):
    try:
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def _c_now_iso(t):
    """(year, month, day, hour|None, minute|None, am|pm|None) of an ISO-style now string, else None."""
    m = _c_NOW_DATE.match(t)
    if not m:
        return None
    tm = _c_NOW_TIME.match(t, m.end())
    if tm and _c_NOW_ZONE.match(t, tm.end()):
        return (m.group(1), m.group(2), m.group(3), tm.group(1), tm.group(2), tm.group(4))
    if _c_NOW_ZONE.match(t, m.end()):
        return (m.group(1), m.group(2), m.group(3), None, None, None)
    return None


def _c_now_slash(t):
    """(year, first number, second number, hour|None, minute|None, am|pm|None) of a d/m/yyyy now string, else None."""
    m = _c_NOW_SLD.match(t)
    if not m:
        return None
    tm = _c_NOW_SLT.match(t, m.end())
    if tm:
        return (m.group(3), m.group(1), m.group(2), tm.group(1), tm.group(2), tm.group(4))
    if _c_END.match(t, m.end()):
        return (m.group(3), m.group(1), m.group(2), None, None, None)
    return None


def parse_now(s):
    """'2026-01-07T11:00' (also ' ' separator, seconds, 'Z' or offset, date only) -> (date, minutes). Bad -> (None, None)."""
    try:
        t = str(s).strip().lower()
        parts = _c_now_iso(t)
        if parts:
            d = _c_date(parts[0], parts[1], parts[2])
        else:
            parts = _c_now_slash(t)
            if not parts:
                return (None, None)
            a, b = int(parts[1]), int(parts[2])
            d = _c_date(parts[0], a, b) if b > 12 else _c_date(parts[0], b, a)
        if d is None:
            return (None, None)
        if parts[3] is None:
            return (d, 0)
        h, mi = int(parts[3]), int(parts[4])
        if parts[5] == "pm" and h < 12:
            h += 12
        if parts[5] == "am" and h == 12:
            h = 0
        if h > 23 or mi > 59:
            return (None, None)
        return (d, h * 60 + mi)
    except Exception:
        return (None, None)


def iso(d):
    """date -> 'YYYY-MM-DD' ('' for anything else)."""
    try:
        return "%04d-%02d-%02d" % (d.year, d.month, d.day)
    except Exception:
        return ""


def from_iso(s):
    """'YYYY-MM-DD' (a longer date-time string is cut) -> date, or None."""
    if isinstance(s, date):
        return s
    try:
        m = re.match(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})", str(s))
        return _c_date(m.group(1), m.group(2), m.group(3)) if m else None
    except Exception:
        return None


def parse_hhmm(s):
    """'HH:MM' -> minutes, or None."""
    try:
        m = re.match(r"^\s*(\d{1,2}):(\d{2})", str(s))
        if not m or int(m.group(1)) > 24 or int(m.group(2)) > 59:
            return None
        return min(int(m.group(1)) * 60 + int(m.group(2)), 1440)
    except Exception:
        return None


def _c_int(x, lo, hi, dflt):
    try:
        v = int(x)
        return v if lo <= v <= hi else dflt
    except Exception:
        return dflt


def prepare(calendar, today):
    """Spec.calendar -> CAL = {"wd", "hol" (sorted iso; rules expanded for today.year-1 .. +2), "week_start",
    "count_from", "numeric_order", "this_next"}. Missing/bad keys get generic defaults (Mon-Fri, DMY, ...)."""
    c = calendar if isinstance(calendar, dict) else dict()
    wd = []
    for x in (c.get("business_weekdays") or []):
        v = _c_int(x, 0, 6, None)
        if v is not None and v not in wd:
            wd.append(v)
    if not wd:
        wd = [0, 1, 2, 3, 4]
    wd.sort()
    hol = []
    for h in (c.get("holidays") or []):
        d = from_iso(h)
        if d is not None and iso(d) not in hol:
            hol.append(iso(d))
    if isinstance(today, date):
        years = [today.year - 1, today.year, today.year + 1, today.year + 2]
    else:
        years = sorted(set([int(h[:4]) for h in hol]))
    for h in expand_holiday_rules(c.get("holiday_rules") or [], years, wd):
        if h not in hol:
            hol.append(h)
    half = dict()
    for h in (c.get("half_days") or []):
        h = h if isinstance(h, dict) else dict()
        d, m = from_iso(h.get("date")), parse_hhmm(h.get("from"))
        if d is not None and m is not None:
            half[iso(d)] = m
            if c.get("half_day_is_business_day", True) is False and iso(d) not in hol:
                hol.append(iso(d))                          # the brief counts a half day as a day off
    hol.sort()
    tn = c.get("this_next") if isinstance(c.get("this_next"), dict) else dict()
    th = tn.get("this") if tn.get("this") in ("current_week", "next_occurrence") else "current_week"
    nx = tn.get("next") if tn.get("next") in ("following_week", "first_after_today", "skip_one") else "following_week"
    tn2 = dict()
    tn2["this"] = th
    tn2["next"] = nx
    out = dict()
    out["wd"] = wd
    out["hol"] = hol
    out["week_start"] = _c_int(c.get("week_start", 0), 0, 6, 0)
    out["count_from"] = c.get("count_from") if c.get("count_from") in ("after_today", "including_today") else "after_today"
    out["numeric_order"] = c.get("numeric_order") if c.get("numeric_order") in ("DMY", "MDY", "YMD") else "DMY"
    out["this_next"] = tn2
    out["half"] = half
    return out


def _c_cal(cal):
    return cal if isinstance(cal, dict) else prepare(None, None)


def is_bd(cal, d):
    """True if d is a business weekday and not a holiday."""
    try:
        cal = _c_cal(cal)
        return d.weekday() in (cal.get("wd") or [0, 1, 2, 3, 4]) and iso(d) not in (cal.get("hol") or [])
    except Exception:
        return False


def next_bd(cal, d, include=False):
    """First business day > d (>= d when include); None if none within ~2 years."""
    try:
        x = d if include else d + timedelta(days=1)
        for _ in range(_c_LIMIT):
            if is_bd(cal, x):
                return x
            x += timedelta(days=1)
    except Exception:
        pass
    return None


def prev_bd(cal, d, include=False):
    """Last business day < d (<= d when include); None if none."""
    try:
        x = d if include else d - timedelta(days=1)
        for _ in range(_c_LIMIT):
            if is_bd(cal, x):
                return x
            x -= timedelta(days=1)
    except Exception:
        pass
    return None


def add_bd(cal, d, n):
    """The n-th business day strictly after d; n == 0 -> d."""
    try:
        n = int(n)
        x = d
        for _ in range(max(n, 0)):
            x = next_bd(cal, x)
            if x is None:
                return None
        return x
    except Exception:
        return None


def week_start_of(cal, d):
    """First day of d's week (cal['week_start'])."""
    try:
        ws = _c_cal(cal).get("week_start", 0)
        return d - timedelta(days=(d.weekday() - ws) % 7)
    except Exception:
        return None


def last_bd_of_week(cal, d):
    """Last business day in d's week, or None if that week has none."""
    try:
        s = week_start_of(cal, d)
        for i in range(6, -1, -1):
            x = s + timedelta(days=i)
            if is_bd(cal, x):
                return x
    except Exception:
        pass
    return None


def end_of_month(d):
    """Last calendar day of d's month."""
    try:
        first_next = date(d.year + (1 if d.month == 12 else 0), 1 if d.month == 12 else d.month + 1, 1)
        return first_next - timedelta(days=1)
    except Exception:
        return None


def last_bd_of_month(cal, d):
    """Last business day of d's month, or None."""
    try:
        x = end_of_month(d)
        while x.month == d.month:
            if is_bd(cal, x):
                return x
            x -= timedelta(days=1)
    except Exception:
        pass
    return None


def _c_rule_dates(r, y):
    k = r.get("kind")
    if k == "fixed_md":
        d = _c_date(y, r.get("month"), r.get("day"))
        return [d] if d else []
    if k in ("nth_weekday", "last_weekday"):
        m = _c_int(r.get("month"), 1, 12, None)
        wd = _c_int(r.get("weekday"), 0, 6, None)
        if m is None or wd is None:
            return []
        if k == "last_weekday":
            e = end_of_month(date(y, m, 1))
            return [e - timedelta(days=(e.weekday() - wd) % 7)]
        n = _c_int(r.get("n", 1), 1, 5, 1)
        f = date(y, m, 1)
        d = f + timedelta(days=(wd - f.weekday()) % 7 + 7 * (n - 1))
        return [d] if d.month == m else []
    return []


def _c_observe(d, mode, wd, taken):
    if mode not in ("next_monday", "nearest_weekday", "next_business_day") or d.weekday() in wd:
        return None
    if mode == "next_monday":
        x = d + timedelta(days=(7 - d.weekday()) % 7 or 7)
    elif mode == "nearest_weekday":
        x = d - timedelta(days=1) if d.weekday() == 5 else d + timedelta(days=1)
    else:
        x = d + timedelta(days=1)
    for _ in range(30):
        if x.weekday() in wd and iso(x) not in taken:
            return x
        x += timedelta(days=1)
    return None


def expand_holiday_rules(rules, years, wd=None):
    """HolidayRule list (fixed_md, nth_weekday, last_weekday, range; observed shifts) -> sorted iso strings.
    wd = business weekdays used for observed shifts (default Mon-Fri)."""
    out = []
    try:
        wd = list(wd) if wd else [0, 1, 2, 3, 4]
        obs = []
        for r in (rules or []):
            if not isinstance(r, dict):
                continue
            try:
                if r.get("kind") == "range":
                    a, b = from_iso(r.get("from")), from_iso(r.get("to"))
                    if a is None or b is None or b < a:
                        continue
                    x = a
                    for _ in range(370):
                        if x > b:
                            break
                        if iso(x) not in out:
                            out.append(iso(x))
                        x += timedelta(days=1)
                    continue
                for y in (years or []):
                    for d in _c_rule_dates(r, int(y)):
                        if iso(d) not in out:
                            out.append(iso(d))
                        if r.get("observed") and r.get("observed") != "none":
                            obs.append((d, r.get("observed")))
            except Exception:
                continue
        obs.sort(key=lambda p: p[0])
        for d, mode in obs:
            x = _c_observe(d, mode, wd, out)
            if x is not None and iso(x) not in out:
                out.append(iso(x))
        out.sort()
    except Exception:
        pass
    return out


def _c_roll(cal, d, roll):
    if d is None or roll in (None, "", "none") or is_bd(cal, d):
        return d
    return next_bd(cal, d) if roll == "next_bd" else prev_bd(cal, d) if roll == "prev_bd" else d


def eval_date_rule(cal, rule, today, ctx):
    """Evaluate a Spec DateRule (CONTRACTS B.4). ctx = {"deadline": date|None}. Unknown kind / bad input -> None."""
    try:
        return _c_eval(_c_cal(cal), rule, today, ctx if isinstance(ctx, dict) else dict(), 0)
    except Exception:
        return None


def _c_eval(cal, rule, today, ctx, depth):
    if not isinstance(rule, dict) or not isinstance(today, date) or depth > 8:
        return None
    k = rule.get("kind")
    if k == "today":
        return today
    if k == "next_business_day":
        return next_bd(cal, today)
    if k == "nth_business_day_after_today":
        n = _c_int(rule.get("n", 1), 0, 400, 1)
        cf = rule.get("count_from") or cal.get("count_from")
        if cf == "including_today" and n >= 1 and is_bd(cal, today):
            return today if n == 1 else add_bd(cal, today, n - 1)
        return add_bd(cal, today, n)
    if k == "nth_calendar_day_after_today":
        return _c_roll(cal, today + timedelta(days=_c_int(rule.get("n", 0), 0, 4000, 0)), rule.get("roll"))
    if k == "last_business_day_of_week":
        d = last_bd_of_week(cal, today)
        if d is None or d < today or (d == today and rule.get("if_today", "next_week") != "keep"):
            d = last_bd_of_week(cal, week_start_of(cal, today) + timedelta(days=7))
        return d
    if k == "end_of_month":
        return _c_roll(cal, end_of_month(today), rule.get("roll"))
    if k == "last_business_day_of_month":
        d = last_bd_of_month(cal, today)
        if d is None or d < today:
            d = last_bd_of_month(cal, end_of_month(today) + timedelta(days=1))
        return d
    if k == "deadline":
        d = ctx.get("deadline")
        return d if isinstance(d, date) else from_iso(d)
    if k == "fixed":
        return from_iso(rule.get("date"))
    if k in ("min", "max"):
        vals = []
        for a in (rule.get("args") or []):
            v = _c_eval(cal, a, today, ctx, depth + 1)
            if v is not None:
                vals.append(v)
        if not vals:
            return None
        return min(vals) if k == "min" else max(vals)
    return None


_c_WDN = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}


def weekday_date(cal, today, weekday, which):
    """which: 'bare' (nearest on/after today, today counts) | 'this' | 'next' (per cal['this_next'])."""
    try:
        cal = _c_cal(cal)
        w = weekday if isinstance(weekday, int) else _c_WDN.get(str(weekday).strip().lower()[:9], None)
        if w is None:
            for name in _c_WDN:
                if name.startswith(str(weekday).strip().lower()[:3]):
                    w = _c_WDN[name]
        if w is None or not 0 <= w <= 6:
            return None
        tn = cal.get("this_next") or dict()
        bare = today + timedelta(days=(w - today.weekday()) % 7)
        if which == "this":
            if tn.get("this") == "next_occurrence":
                return bare
            s = week_start_of(cal, today)
            return s + timedelta(days=(w - s.weekday()) % 7)
        if which == "next":
            first_after = today + timedelta(days=(w - today.weekday() - 1) % 7 + 1)
            if tn.get("next") == "first_after_today":
                return first_after
            if tn.get("next") == "skip_one":
                return first_after + timedelta(days=7)
            s = week_start_of(cal, today) + timedelta(days=7)
            return s + timedelta(days=(w - s.weekday()) % 7)
        return bare
    except Exception:
        return None


def spoken_date(d, today):
    """'Friday, 9 January' (+ ' 2027' when the year differs from today's). English tables, never strftime names."""
    try:
        s = "%s, %d %s" % (_c_DAYS[d.weekday()], d.day, _c_MONTHS[d.month - 1])
        if isinstance(today, date) and today.year != d.year:
            s += " %d" % d.year
        return s
    except Exception:
        return ""


def _c_fmt(fmt, vals):
    def rep(m):
        return vals.get(m.group(0), m.group(0))
    return re.sub(r"%[YmdyHMS]", rep, fmt)


def wire_date(d, fmt, minutes=None):
    """Format with numeric tokens %Y %m %d %y (and %H %M %S from minutes, default 0); other characters literal.
    Empty fmt -> '%Y-%m-%d'."""
    try:
        mi = int(minutes or 0)
        vals = dict()
        vals["%Y"] = "%04d" % d.year
        vals["%m"] = "%02d" % d.month
        vals["%d"] = "%02d" % d.day
        vals["%y"] = "%02d" % (d.year % 100)
        vals["%H"] = "%02d" % (mi // 60)
        vals["%M"] = "%02d" % (mi % 60)
        vals["%S"] = "00"
        return _c_fmt(fmt or "%Y-%m-%d", vals)
    except Exception:
        return ""


def wire_time(minutes, fmt="%H:%M"):
    """Format minutes with %H %M (zero padded; %S = 00); empty fmt -> '%H:%M'."""
    try:
        mi = int(minutes)
        vals = dict()
        vals["%H"] = "%02d" % ((mi // 60) % 24)
        vals["%M"] = "%02d" % (mi % 60)
        vals["%S"] = "00"
        return _c_fmt(fmt or "%H:%M", vals)
    except Exception:
        return ""


def callback_dates(cal, cb, today):
    """Spec.third_party.callback (or its date_rule) -> sorted list of allowed dates (CONTRACTS B.3)."""
    out = []
    try:
        cb = cb if isinstance(cb, dict) else dict()
        dr = cb.get("date_rule") if isinstance(cb.get("date_rule"), dict) else cb
        if dr.get("include_today") and (not dr.get("today_must_be_business_day") or is_bd(cal, today)):
            out.append(today)
        x = today
        for _ in range(_c_int(dr.get("business_days_ahead", 0), 0, 60, 0)):
            x = next_bd(cal, x)
            if x is None:
                break
            out.append(x)                                   # strictly after every earlier entry
        for i in range(1, _c_int(dr.get("calendar_days_ahead", 0), 0, 60, 0) + 1):
            x = today + timedelta(days=i)
            if x not in out:
                out.append(x)
        out.sort()
    except Exception:
        pass
    return out


def _c_in_window(cal, w, d, t):
    a, b = parse_hhmm(w.get("from")), parse_hhmm(w.get("to"))
    if a is None or b is None:
        return False
    days = w.get("days", "any")
    if days == "business" and not is_bd(cal, d):
        return False
    if days == "non_business" and is_bd(cal, d):
        return False
    lo_ok = t >= a if w.get("inclusive_from", True) else t > a
    hi_ok = t <= b if w.get("inclusive_to", True) else t < b
    return lo_ok and hi_ok


def callback_check(cal, cb, today, now_min, d, t_min):
    """-> 'ok' | 'outside' | 'past' for a proposed callback date d and time t_min."""
    try:
        cb = cb if isinstance(cb, dict) else dict()
        if d is None or t_min is None or today is None:
            return "outside"
        d = from_iso(d) if not isinstance(d, date) else d
        t = int(t_min)
        if d < today:
            return "past"
        if d == today and now_min is not None:
            if cb.get("after_now", True) and t <= int(now_min):
                return "past"
            if t < int(now_min) + _c_int(cb.get("min_lead_minutes", 0), 0, 1440, 0):
                return "outside"
        if d not in callback_dates(cal, cb, today):
            return "outside"
        if t >= (_c_cal(cal).get("half") or dict()).get(iso(d), 1440):
            return "outside"                                # the afternoon of a half day (arife) is off
        ws = cb.get("windows") or []
        if not ws:
            return "ok"
        for w in ws:
            if isinstance(w, dict) and _c_in_window(cal, w, d, t):
                return "ok"
        return "outside"
    except Exception:
        return "outside"
