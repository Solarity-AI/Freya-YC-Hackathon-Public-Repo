"""Call-language rendering and small language tables (generic language support; no brief or case content).

Rules: Python 3.8 syntax; stdlib only; no double curly braces; private helpers prefixed _l_; nothing raises.

- lang_of(spec): the Spec's call language as a 2-letter ISO code (bank.language), "en" when unset.
- date_phrase(d, today, lang): English "Friday, 23 October"; Turkish "23 Ekim Cuma" (+ the year when it differs
  from today's: "23 Ekim 2027 Cuma").
- money_digits(cents, lang): English "1,250" / "1,250.50"; Turkish (and other comma-decimal languages) "1.250" /
  "1.250,50". The currency word or sign is added by the caller from the Spec.
- weekday_index(name): 0-6 for an English or Turkish weekday name (any case, with or without Turkish letters).
- and_word(lang): the list connector ('and', Turkish 've').
- lang_lower(s, lang): lower case with the Turkish dotted/dotless i rules for Turkish.
"""
import re

_L_DAYS = dict(
    en=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    tr=["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"])
_L_MONTHS = dict(
    en=["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
        "November", "December"],
    tr=["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım",
        "Aralık"])
# (thousands separator, decimal mark) per language; anything not listed writes like English
_L_SEP = dict(en=(",", "."), tr=(".", ","), de=(".", ","), es=(".", ","), it=(".", ","), nl=(".", ","),
              pt=(".", ","), da=(".", ","), fr=(" ", ","), pl=(" ", ","), sv=(" ", ","))
# the word joining the last two items of a list ("A, B and C"); anything not listed joins like English
_L_AND = dict(en="and", tr="ve", de="und", es="y", fr="et", it="e", nl="en", pt="e", da="og", sv="och", pl="i")
_L_FOLD = {"ı": "i", "ş": "s", "ç": "c", "ğ": "g", "ü": "u", "ö": "o", "â": "a", "î": "i", "û": "u"}


def lang_of(spec):
    """The Spec's call language (bank.language) as a lower-case 2-letter code; 'en' when unset or unreadable."""
    try:
        v = str(((spec or {}).get("bank") or {}).get("language") or (spec or {}).get("language") or "en")
        v = v.strip().lower()[:2]
        return v if re.match(r"^[a-z]{2}$", v) else "en"
    except Exception:
        return "en"


def and_word(lang="en"):
    """The list connector of the call language ('and', Turkish 've')."""
    return _L_AND.get(lang, _L_AND["en"])


def lang_lower(s, lang="en"):
    """Lower case; Turkish (and Azerbaijani) map I -> ı and İ -> i before lowering (str.lower would give i and i̇)."""
    try:
        s = str(s or "")
        if lang in ("tr", "az"):
            s = s.replace("I", "ı").replace("İ", "i")
        return s.lower().replace("i̇", "i")
    except Exception:
        return ""


def lang_fold(s):
    """Lower case without Turkish letters and accents ('Çarşamba' -> 'carsamba'); for loose name lookups."""
    t = lang_lower(s, "tr")
    return "".join(_L_FOLD.get(ch, ch) for ch in t)


def weekday_index(name):
    """0 (Monday) .. 6 for an English or Turkish weekday name or a 3-letter English abbreviation, else None."""
    f = lang_fold(name).strip(" .,!?")                  # lang_fold never raises
    if not f:
        return None
    for tab in _L_DAYS.values():
        for i, dn in enumerate(tab):
            if f == lang_fold(dn):
                return i
    for i, dn in enumerate(_L_DAYS["en"]):
        if len(f) >= 3 and dn.lower().startswith(f):
            return i
    return None


def date_phrase(d, today, lang="en"):
    """The spoken date in the call language; '' on bad input. English: 'Friday, 23 October' (+ ' 2027')."""
    try:
        y = (" %d" % d.year) if (today is not None and getattr(today, "year", d.year) != d.year) else ""
        if lang in _L_DAYS and lang != "en":
            return "%d %s%s %s" % (d.day, _L_MONTHS[lang][d.month - 1], y, _L_DAYS[lang][d.weekday()])
        return "%s, %d %s%s" % (_L_DAYS["en"][d.weekday()], d.day, _L_MONTHS["en"][d.month - 1], y)
    except Exception:
        return ""


def money_digits(cents, lang="en"):
    """Integer cents -> grouped digits with the language's marks ('1,250.50' / '1.250,50'); decimals only when the
    amount has cents. '' on bad input."""
    try:
        cents = int(cents)
        neg = cents < 0
        cents = abs(cents)
        th, dec = _L_SEP.get(lang, _L_SEP["en"])
        s = format(cents // 100, ",").replace(",", th)
        if cents % 100:
            s = s + dec + "%02d" % (cents % 100)
        return ("-" if neg else "") + s
    except Exception:
        return ""

