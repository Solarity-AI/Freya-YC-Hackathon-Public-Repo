"""National public-holiday calendars (general public knowledge, not case content).

Used only when a brief refers to the country's public holidays without listing them, or to warn
when a brief's own list misses a national holiday. The brief's own list always wins.
"""
from .tr import TR_FULL_DAYS, TR_HALF_DAYS

CALENDARS = {"TR": (TR_FULL_DAYS, TR_HALF_DAYS)}

# Words a brief uses for "the country's public holidays" (generic, multilingual).
PUBLIC_HOLIDAY_WORDS = (
    "resmi tatil", "resmî tatil", "ulusal bayram", "dini bayram", "bayram tatili", "arife",
    "public holiday", "bank holiday", "national holiday", "official holiday",
)


def national_holidays(country, include_half_days=False):
    """Sorted ISO dates of the country's public holidays (full days; half-day eves on request)."""
    full, half = CALENDARS.get((country or "").upper(), ((), ()))
    days = set(full) | (set(half) if include_half_days else set())
    return sorted(days)


def half_days(country):
    return sorted(CALENDARS.get((country or "").upper(), ((), ()))[1])


def mentions_public_holidays(text):
    t = (text or "").lower()
    return any(w in t for w in PUBLIC_HOLIDAY_WORDS)


def country_for(language, text=""):
    """Best guess of the call's country from the Spec language (tr -> TR); None when unknown."""
    lang = (language or "").lower()
    if lang.startswith("tr"):
        return "TR"
    t = (text or "").lower()
    if "türkiye" in t or "turkiye" in t or " tl" in t or "türk lirası" in t:
        return "TR"
    return None


def merge(holidays, country, brief_text, decisions, warnings, window=None):
    """Return the holiday list to use.

    - brief lists no holidays but mentions public holidays -> national full-day list (DECISION)
    - brief lists holidays -> keep them; WARN for national holidays inside `window` (start, end ISO) that are missing
    """
    listed = sorted(set(holidays or []))
    nat = national_holidays(country)
    if not nat:
        return listed
    if not listed and mentions_public_holidays(brief_text):
        decisions.append(f"calendar.holidays: brief refers to public holidays without a list; using the {country} "
                         f"national calendar ({len(nat)} full days; half-day eves stay business days)")
        return nat
    if listed and window:
        lo, hi = window
        missing = [d for d in nat if lo <= d <= hi and d not in listed]
        if missing:
            warnings.append(f"calendar.holidays: {country} national holidays not in the brief's list within "
                            f"{lo}..{hi}: {', '.join(missing)} (brief wins; check the announcements)")
    return listed
