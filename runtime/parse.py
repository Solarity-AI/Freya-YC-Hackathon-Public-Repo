"""Text -> values: amounts (integer cents), dates, times, digit strings, years, yes/no (docs/CONTRACTS.md C.3).
Owner: agent 1. Python 3.8 syntax; stdlib json/re/datetime only; no double curly braces; private names _p_;
every function is total on arbitrary text (returns the documented 'none' result, never raises).

CONTRACT NOTE (agent 1, readings chosen where C.3 is silent; all additions are optional and backward compatible):
- norm also maps ?!; to '.', '%' to ' percent', '&' to ' and', 'a.m./p.m.' to am/pm.
- Corrections: each parser walks the correction clauses from the last one back and uses the first clause that holds
  its kind of value (so 'four hundred on Friday, sorry, three hundred' keeps Friday); a last clause that is a bare
  retraction ("no, I can't") yields 'none'. parse_dob overlays the clauses component by component.
- parse_amount ctx (all optional): known [cents], lo, hi, frag (text of an earlier incomplete fragment to join),
  drop [whole-unit ints to ignore, e.g. display digits], ref (cents of the last figure the agent named, for
  'half of that'), full / floor (cents; enable 'the minimum' / 'all of it' and fractions/percent of the debt),
  floor_words [extra regexes naming the floor]. Extra result keys: alts [other cents], snapped, named, rel.
  A whole-dollar figure equal to a known figure without its cents snaps to that figure (snapped=True).
- parse_date(text, today, cal, opts=None): opts bare_today (default False: a bare weekday is strictly after today, per
  EDGE-CASES #26; pass True when answering the today-ask with yes; cal.weekday_date 'bare' itself keeps today),
  bare_number (a lone 1-31 answer is a day of the month), frag (earlier incomplete date fragment). Extra key
  'alts' (other exact dates named, e.g. 'Thursday or Friday'). Month+day in the past by <= 60 days -> 'past',
  further back -> next year. A numeric date invalid in numeric_order is read swapped if that is valid.
- parse_time: a bare number is a time only after at/around/about/by/call/try..., before o'clock/am/pm/ish, or as
  the whole answer; ranges with no am/pm read hours 1-7 as pm; 'in N minutes/hours' adds key day_offset when it
  passes midnight; 'after H' ranges carry lo_excl. Pieces in the past tense, first person or negated are skipped
  ('she left at nine, back by six' -> six); a piece with call/ring/try wins. parse_year(text, today=None): 2-digit
  years only with today (age 18-100 rule).
- parse_digits returns the longest digit cluster (clusters break at non-number words), so a recited full number
  keeps every digit for the caller to take the trailing N.
"""
import re
import datetime
from datetime import date, timedelta
from .cal import weekday_date, from_iso, iso, end_of_month, last_bd_of_month, prepare

_p_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
_p_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
_p_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
_p_ORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14, "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18, "nineteenth": 19, "twentieth": 20, "thirtieth": 30}
_p_SCALES = {"hundred": 100, "thousand": 1000, "grand": 1000, "million": 1000000}
_p_ZW = ("oh", "o", "nought", "naught", "zero")
_p_MONTHS = {"january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3, "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7, "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9, "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12}
_p_WDAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tues": 1, "tue": 1, "wednesday": 2, "weds": 2, "wed": 2, "thursday": 3, "thurs": 3, "thur": 3, "thu": 3, "friday": 4, "fri": 4, "saturday": 5, "sunday": 6}
_p_W = "monday|tuesday|wednesday|thursday|friday|saturday|sunday|tues|tue|weds|wed|thurs|thur|thu|fri|mon"
_p_M = ("january|february|march|april|may|june|july|august|september|october|november|december|sept|sep|jan|feb"
        "|mar|apr|jun|jul|aug|oct|nov|dec")
_p_CUR = ("dollars", "dollar", "bucks", "buck", "quid", "euros", "euro", "pounds", "pound", "usd", "eur", "gbp")
_p_CENTW = ("cents", "cent", "pence", "p")
_p_TIMEU = ("minutes", "minute", "mins", "min", "hours", "hour", "hrs", "hr", "days", "day", "weeks", "week",
            "months", "month", "years", "year", "yrs", "times", "o'clock", "oclock", "am", "pm", "seconds", "people",
            "kids", "miles", "km")
# Tokens, as one regex  \d+(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d+(?:st|nd|rd|th)\b|\d+|[a-z]+(?:'[a-z]+)?|\.\.+|[.,:;/-]
# would find them. Every digit-led alternative needs the maximal digit run, so _p_tokens matches the run once
# (_p_TOK) and then the optional number suffix (_p_NUMSUF) in the same alternative order.
_p_TOK = re.compile(r"\d+|[a-z]+(?:'[a-z]+)?|\.\.+|[.,:;/-]")
_p_NUMSUF = re.compile(r"(?:,\d{3})+(?:\.\d+)?|\.\d+|(?:st|nd|rd|th)\b")
_p_CORR = re.compile(r"\bsorry\b|\bi mean\b|\bi meant\b|\bno wait\b|\bwait\b|\bactually\b|\bor rather\b|\brather\b"
                     r"|\bmake that\b|\bmake it\b|\bscratch that\b|\bhang on\b|\bhold on\b|\bcorrection\b|\bno,")
_p_RETRACT = re.compile(r"n't\b|\bcannot\b|\bnot\b|\bno\b|\bnever\b|\bforget it\b|\bnone\b|\bnothing\b")
_p_PAST = re.compile(r"\b(?:paid|was|were|went|had|did|ago|lost|happened|spent|took|used to|earlier|"
                     r"last (?:week|month|year|time|night))\b")
_p_GETPAID = re.compile(r"\b(?:get|gets|getting|be|been|being|i'm|am|is) paid\b")
_p_EVENT = re.compile(r"\b(?:wedding|birthday|appointment|party|funeral|anniversary|interview|surgery|operation|"
                      r"exam|vacation|trip|flight|concert|rent|bills?|mortgage|traffic|commute|meeting|went up)\b")
_p_INCOME = re.compile(r"\b(?:get paid|gets paid|getting paid|payday|pay day|salary|wages|paycheck|pay check|"
                       r"pension|benefits|money comes|money arrives|redundancy|paid on)\b")
_p_PAYW = re.compile(r"\b(?:pay|paying|payment|do|manage|afford|send|transfer|put|settle|clear|cover|make|give|"
                     r"can|could|will|i'll|i'd|would|able|offer|try|sort)\b")
_p_NEGD = re.compile(r"n't\b|\bnot\b|\bno good\b|\bcannot\b|\bnever\b|\bbusy\b|\baway\b|\bunavailable\b|\bexcept\b"
                     r"|\bout of town\b|\bno\b(?! problem| worries)")
_p_UNTIL = re.compile(r"\b(?:until|till|til|not before|no earlier than)\b")
_p_AWAY = re.compile(r"\b(?:away|busy|out of town|on holiday|travelling|traveling|working|abroad|in hospital)\b")
_p_HEDGE = re.compile(r"\b(?:about|around|roughly|approximately|approx|maybe|probably|perhaps|possibly|"
                      r"something like|or so|give or take|ish|close to|i think|i guess|i suppose|might|hopefully)\b")
_p_SEGW = ("but", "anyway", "though", "although", "because", "cause", "cos", "however", "so", "except")
_p_PRON = ("i", "i'm", "i'll", "i've", "my", "we", "she", "he", "it's", "they")


def _p_income(s):
    """Replace 'get paid'-style phrases with ' income ' so they do not read as a past-tense payment."""
    return _p_GETPAID.sub(" income ", s)


def _p_tokens(s):
    out, pos = [], 0
    while True:
        m = _p_TOK.search(s, pos)
        if not m:
            return out
        pos = m.end()
        if m.group(0)[0].isdigit():
            x = _p_NUMSUF.match(s, pos)
            if x:
                pos = x.end()
        out.append(s[m.start():pos])


def _p_none():
    r = dict()
    r["kind"] = "none"
    return r


def _p_rtrim(s):
    """s without its trailing run of whitespace, '.' and '-' (a linear scan; the regex [\\s.\\-]+$ backtracks
    quadratically on long runs that do not reach the end)."""
    i = len(s)
    while i and (s[i - 1].isspace() or s[i - 1] in ".-"):
        i -= 1
    return s[:i]


_p_OPEN_WORD = re.compile(r"\b(?:and|point)\Z")


def _p_open_tail(c):
    """True when c ends (before trailing whitespace) with '..', '-', 'and' or 'point': a number still being said."""
    t = c.rstrip()
    return t.endswith("..") or t.endswith("-") or _p_OPEN_WORD.search(t) is not None


def norm(text):
    """Lowercase, unify quotes/dashes, collapse spaces, keep [a-z0-9 :./,'-] ('?!;' become '.')."""
    try:
        s = text if isinstance(text, str) else ("" if text is None else str(text))
        s = s.lower()
        s = s.replace("’", "'").replace("‘", "'").replace("`", "'")
        s = s.replace("–", "-").replace("—", " - ").replace("…", "...")
        s = s.replace("%", " percent ").replace("&", " and ")
        s = re.sub(r"\b([ap])\.\s?m\b\.?", r"\1m", s)
        s = re.sub(r"[?!;]", ".", s)
        s = re.sub(r"[^a-z0-9 :./,'-]+", " ", s)
        return re.sub(r"\s+", " ", s).strip()
    except Exception:
        return ""


def _p_clauses(s):
    parts = [p.strip(" ,") for p in _p_CORR.split(s)]
    parts = [p for p in parts if p]
    return parts or [s]


def last_clause(text):
    """Text after the last correction marker (sorry, I mean, no wait, actually, rather, make that, ...), else text."""
    try:
        return _p_clauses(norm(text))[-1]
    except Exception:
        return ""


def _p_retract(clauses, idx):
    return idx == len(clauses) - 1 and len(clauses) > 1 and _p_RETRACT.search(clauses[idx]) is not None


# ---------------------------------------------------------------- lexer: words and digits -> number tokens

def _p_isnum(w):
    return w in _p_UNITS or w in _p_TEENS or w in _p_TENS or w in _p_ORDS or w[:1].isdigit() or w in _p_SCALES


def _p_numlit(w):
    t = {"k": "n", "ord": False, "lit": True, "sc": False, "zw": w == "0", "last": "dig", "c": None, "dec": ""}
    m = re.match(r"^(\d+)(st|nd|rd|th)$", w)
    if m:
        t["v"] = int(m.group(1))
        t["s"] = m.group(1)
        t["ord"] = True
        return t
    body = w.replace(",", "")
    if "." in body:
        a, b = body.split(".", 1)
        t["v"] = int(a or "0")
        t["dec"] = b
        t["c"] = _p_dec_cents(b)
    else:
        t["v"] = int(body)
    t["s"] = body
    return t


def _p_dec_cents(ds):
    ds = re.sub(r"\D", "", ds or "")
    if not ds:
        return None
    c = int((ds + "00")[:2])
    if len(ds) > 2 and int(ds[2]) >= 5:
        c += 1
    return c


def _p_zero_marks(raw):
    n = len(raw)
    z = [w in ("nought", "naught", "zero") for w in raw]

    def nb(i, step):
        j = i + step
        while 0 <= j < n and raw[j] in (",", "-", "..", "..."):
            j += step
        return j if 0 <= j < n else -1
    for _ in range(3):
        for i in range(n):
            if raw[i] in ("oh", "o") and not z[i]:
                for j in (nb(i, -1), nb(i, 1)):
                    if j >= 0 and ((_p_isnum(raw[j]) and raw[j] not in _p_SCALES) or z[j]
                                   or raw[j] in ("double", "triple", "point")):
                        z[i] = True
    return z


def _p_words(raw, z, i):
    n = len(raw)
    total, small, last, ordf, sc, dec = 0, 0, None, False, False, ""
    while i < n:
        w = raw[i]
        nxt = raw[i + 1] if i + 1 < n else ""
        if w[:2] == ".." or w == "-":
            if last in ("tens", "scale", "and") and nxt and ((last == "tens" and _p_UNITS.get(nxt, 0) > 0) or (
                    last != "tens" and (nxt in _p_UNITS or nxt in _p_TEENS or nxt in _p_TENS or nxt in _p_ORDS))):
                i += 1
                continue
            break
        if nxt[:2] == ".." or nxt == "-":
            nxt = raw[i + 2] if i + 2 < n else ""
        if z[i]:
            if last is None:
                last = "zero"
                i += 1
            break
        if w in _p_UNITS:
            v = _p_UNITS[w]
            if last is None:
                small = v
            elif (last == "tens" and v > 0) or last in ("scale", "and"):
                small += v
            else:
                break
            last = "unit"
        elif w in _p_TEENS or w in _p_TENS:
            v = _p_TEENS.get(w) or _p_TENS.get(w)
            if last is None:
                small = v
            elif last in ("scale", "and"):
                small += v
            else:
                break
            last = "teen" if w in _p_TEENS else "tens"
        elif w in _p_ORDS:
            v = _p_ORDS[w]
            if last is None:
                small = v
            elif (last == "tens" and v < 10) or last in ("scale", "and"):
                small += v
            else:
                break
            ordf = True
            last = "ord"
            i += 1
            break
        elif w in _p_SCALES:
            if w == "hundred":
                if small >= 100:
                    break
                small = (small or 1) * 100
            else:
                total += (small or 1) * _p_SCALES[w]
                small = 0
            last = "scale"
            sc = True
        elif w in ("a", "an") and last is None and nxt in _p_SCALES:
            last = "a"
        elif w == "and" and last == "scale" and (nxt in _p_UNITS or nxt in _p_TEENS or nxt in _p_TENS or nxt in _p_ORDS):
            last = "and"
        elif w == "point" and last not in (None, "a", "and") and i + 1 < n:
            j, ds = i + 1, ""
            while j < n:
                x = raw[j]
                if z[j]:
                    ds += "0"
                elif x in _p_UNITS:
                    ds += str(_p_UNITS[x])
                elif x in _p_TEENS or x in _p_TENS:
                    v = _p_TEENS.get(x) or _p_TENS.get(x)
                    if x in _p_TENS and j + 1 < n and _p_UNITS.get(raw[j + 1], 0) > 0:
                        v += _p_UNITS[raw[j + 1]]
                        j += 1
                    ds += str(v)
                elif x.isdigit():
                    ds += x
                else:
                    break
                j += 1
            if ds:
                dec = ds
                i = j
            break
        else:
            break
        i += 1
    v = total + small
    t = {"k": "n", "v": v, "ord": ordf, "lit": False, "sc": sc, "zw": last == "zero", "last": last, "dec": dec}
    t["c"] = _p_dec_cents(dec) if dec else None
    t["s"] = "0" if last == "zero" else str(v)
    return t, i


def _p_lex(s):
    """Normalised text -> tokens: {"k": "w"|"p", "w"} or number {"k": "n", "v", "c", "s", "ord", "lit", "sc",
    "zw", "last", "dec"}. Number words group like speech: 'twelve fifty' -> two tokens, 'two hundred and fifty' -> one."""
    raw = _p_tokens(re.sub(r"(?<=[a-z0-9])-(?=[a-z0-9])", " ", s))
    z = _p_zero_marks(raw)
    out, i, n = [], 0, len(raw)
    while i < n:
        w = raw[i]
        if w[:1].isdigit():
            t = _p_numlit(w)
            i += 1
            if i < n and not t["ord"] and (raw[i] in _p_SCALES or raw[i] == "k"):
                mul = _p_SCALES.get(raw[i], 1000)
                cents = t["v"] * 100 + (t["c"] or 0)
                t["v"], t["c"], t["sc"] = (cents * mul) // 100, ((cents * mul) % 100) or None, True
                t["s"] = str(t["v"])
                i += 1
            out.append(t)
            continue
        if (w in _p_UNITS or w in _p_TEENS or w in _p_TENS or w in _p_ORDS or z[i] or w in ("hundred", "thousand")
                or (w in ("a", "an") and i + 1 < n and raw[i + 1] in _p_SCALES)):
            t, j = _p_words(raw, z, i)
            if j > i:
                out.append(t)
                i = j
                continue
        out.append({"k": "p" if not w[:1].isalpha() else "w", "w": w})
        i += 1
    return out


def _p_wtxt(t):
    return t.get("w", "") if t["k"] != "n" else t["s"] + ("th" if t["ord"] else "")


def _p_conv(s):
    """Number words -> digits ('the twenty-first of may' -> 'the 21th of may'); punctuation kept."""
    return " ".join([_p_wtxt(t) for t in _p_lex(s)])


def _p_tail_open(s):
    toks = [t for t in _p_lex(s) if not (t["k"] == "p" and t["w"] in (",", ".", "..", "...", "-"))]
    if not any(t["k"] == "n" for t in toks):
        return False
    tail = toks[-1]
    if tail["k"] == "w":
        return tail["w"] in ("and", "point", "double", "triple", "oh")
    return tail["k"] == "n" and (tail["last"] == "tens" or (tail["last"] == "teen" and tail["v"] == 19)
                                 or (tail["last"] == "scale" and tail["v"] == 2000))


# ---------------------------------------------------------------- segments and clause flags

def _p_segments(toks, seps=None):
    segs, cur = [], []
    sep = "^"
    for i, t in enumerate(toks):
        if t["k"] == "p" and t["w"] in (".", ",", ";", ":", "..", "...", "-") or (t["k"] == "p" and t["w"].startswith("..")):
            prev = cur[-1] if cur else None
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            if t["w"] != "." and prev is not None and nxt is not None and prev["k"] == "n" and nxt["k"] == "n":
                cur.append(t)
                continue
            segs.append(cur)
            if seps is not None and cur:
                seps.append(sep)
            sep = t["w"]
            cur = []
            continue
        if t["k"] == "w" and (t["w"] in _p_SEGW or (t["w"] == "and" and i + 1 < len(toks) and toks[i + 1].get("w") in _p_PRON)):
            segs.append(cur)
            if seps is not None and cur:
                seps.append(sep)
            sep = "w"
            cur = []
            continue
        cur.append(t)
    segs.append(cur)
    if seps is not None and cur:
        seps.append(sep)
    return [x for x in segs if x]


def _p_segtext(seg):
    return " ".join([_p_wtxt(t) for t in seg])


# ---------------------------------------------------------------- amounts

_p_FLOORW = re.compile(r"\b(?:the )?(?:minimum(?: payment| amount)?|min payment|(?:the |my )?instal+ments?(?: amount)?|"
                       r"lowest(?: amount)?)\b")
_p_FULLW = re.compile(r"\b(?:all of it|all of that|the full amount|in full|the whole (?:thing|amount|lot|balance|sum)|"
                      r"everything|the lot|the full (?:thing|balance|sum)|the entire (?:amount|thing|balance)|full amount)\b")
_p_QTM = re.compile(r"\b(?:what's|what is|how much|what|which)\b")
_p_FRAC = re.compile(r"\b(half|a half|one half|a third|one third|a quarter|one quarter|three quarters|two thirds)\b"
                     r"(?! past| an hour| hour)(?: of (it|that|this|the (?:amount|debt|balance|total)|what i owe))?")
_p_FRACV = {"half": (1, 2), "third": (1, 3), "quarter": (1, 4), "quarters": (3, 4), "thirds": (2, 3)}
# the amount named is more than the customer can pay ("more than I can afford", "too high", "can't afford the minimum")
_p_TM_CORE = (r"\bmore than i (?:can|could) (?:pay|afford|manage|do)\b|\btoo (?:high|steep|expensive|much)\b"
              r"|\b(?:can't|cannot|can not|couldn't|not able to|unable to) (?:even )?(?:pay|afford|manage) (?:even )?"
              r"(?:all|the whole|that much|the full|it all|the (?:minimum|lowest|instal\w*)|my instal\w*)\b"
              r"|\bnot the whole\b|\bnot all of it\b|\bthat(?:'s| is) a lot\b|\bless than that\b|\bsomething smaller\b")
_p_TMC = re.compile(_p_TM_CORE)
# only part of the full amount ("not the full amount", "only some", "part of it now") and asking to pay less
# ("what's the least I can pay?", "can I pay less?"): too much, but no rejection of a named floor
_p_TM_PART = (r"\bnot (?:the )?(?:full|whole|entire|total)\b|\bnot (?:all|everything)\b(?! right| good| ok| fine| is\b| was\b)"
              r"|\bonly (?:some|part|a (?:part|portion|bit|little))\b|\b(?:some|part|a (?:part|portion|bit)) of (?:it|that|the (?:amount|money|balance|debt))\b"
              r"|\bpart (?:of it|now|today|payment)\b|\bpartial(?:ly| payment| amount)?\b|\bjust (?:some|part)\b(?! (?:time|day|point))")
_p_LESSQ = re.compile(r"\b(?:what(?:'s| is)? (?:the|your) (?:least|lowest|smallest|minimum)|how little\b|pay (?:a bit |a little |something )?less\b"
                      r"|(?:how much|what) is (?:the|your) (?:least|lowest|smallest|minimum)\b"
                      r"|tell me (?:the|your) (?:least|lowest|smallest|minimum)\b"
                      r"|(?:a )?(?:lower|smaller|reduced) (?:amount|payment|sum)|is there (?:a |any )?(?:minimum|lower|smaller)"
                      r"|less than (?:the full|the whole|all|that|this|the total)\b)")
_p_TMQ = re.compile(_p_TM_PART + r"|" + _p_LESSQ.pattern)
_p_TOOMUCH = re.compile(r"(?:can't|cannot|can not|couldn't|not able to|unable to) (?:pay|afford|manage|do) (?:all|the whole|that much|the full|it all|that)"
                        r"|\btoo much\b|\bnot the whole\b|\bnot all of it\b|\bthat's a lot\b|\bthat is a lot\b|\bwhat's the (?:least|minimum)\b"
                        r"|\bwhat is the (?:least|minimum)\b|\byou tell me\b|\bpart of it\b|\bwhatever i can\b|\bsome of it\b"
                        r"|\bcan't even pay the minimum\b|\bcan't afford (?:that|it|this)\b|\bless than that\b|\bsomething smaller\b"
                        r"|" + _p_TM_CORE + r"|" + _p_TMQ.pattern)
_p_FUTW = re.compile(r"\b(?:i'll|i will|will|i can|can i|i could|could|going to|gonna|i'd|would|shall)\b")
_p_IDIOM = re.compile(r"\b(?:in one go|one go|the one|this one|that one|which one|no one|anyone|someone|every ?one|"
                      r"one of (?:them|those|these|the|my)|one (?:second|sec|moment|minute|min)|a (?:second|sec|moment|minute)|"
                      r"one more thing|one thing|one day|one time|at one point|first of all|one by one)\b")
_p_ZERO = re.compile(r"\b(?:nothing|none|not a (?:penny|cent|dime|thing)|not one (?:penny|cent)|"
                     r"(?:can't|cannot|won't|not) pay anything|no money)\b")


_p_NAMEDX = re.compile(r"\b(?:lower|smaller|reduced?|reduction|new|different|cheaper|less|even|another|other|"
                       r"plan|restructur\w*)\b")


def _p_floor_rejected(s):
    """A too-much phrase that is not about the full amount ("the full amount is too much" keeps "the minimum")."""
    for m in _p_TMC.finditer(s):
        if not _p_FULLW.search(s[max(0, m.start() - 40):m.start()]):
            return True
    return False


def too_much(text):
    """True when the customer says the amount is more than they can pay, offers only part of it, or asks to pay
    less (generic English, any segment)."""
    t = norm(text)                                      # norm never raises
    return _p_TMC.search(t) is not None or _p_TMQ.search(t) is not None


def asks_less(text):
    """True for a question or request to pay less ("What's the least I can pay?", "Is there a minimum?"): naming
    the floor there asks for it, it does not reject it."""
    return _p_LESSQ.search(norm(text)) is not None


def _p_named(seg, extra):
    # naming the floor to reject it or to ask for less is not an offer ("the minimum is too much", "even the
    # minimum", "smaller instalments", "a new instalment plan")
    if _p_NEGD.search(seg) or _p_QTM.search(seg) or _p_TOOMUCH.search(seg) or _p_NAMEDX.search(seg):
        return ""
    if _p_FLOORW.search(seg):
        return "floor"
    for p in (extra or []):
        try:
            if re.search(p, seg, re.I):
                return "floor"
        except Exception:
            continue
    if _p_FULLW.search(seg):
        return "full"
    return ""


def _p_rhu(num, den):
    return (2 * num + den) // (2 * den) if den else 0


def _p_rank(readings, ctx):
    known = []
    for x in (ctx.get("known") or []):
        try:
            known.append(int(x))
        except Exception:
            continue
    for r in readings:
        if r in known:
            return r, False
    for r in readings:
        if r % 100 == 0:
            for k in known:
                if k % 100 and k - k % 100 == r:
                    return k, True
    lo, hi = ctx.get("lo"), ctx.get("hi")
    if lo is not None or hi is not None:
        for r in readings:
            if (lo is None or r >= int(lo)) and (hi is None or r <= int(hi)):
                return r, False
    return readings[0], False


def _p_run_readings(run):
    g = run
    if len(g) == 1:
        return [g[0]["v"] * 100 + (g[0]["c"] or 0)]
    if any(x["c"] is not None for x in g[:-1]):
        return []
    if len(g) == 2:
        a, b = g
        if a["sc"] and a["v"] >= 1000 and a["v"] % 1000 == 0 and b["v"] < 1000 and not b["zw"]:
            return [(a["v"] + b["v"]) * 100 + (b["c"] or 0)]
        if (a["sc"] or a["v"] >= 100) and b["v"] < 100 and b["c"] is None:
            return [a["v"] * 100 + b["v"]]
        if a["v"] < 100 and not a["sc"] and (10 <= b["v"] <= 99 or b["zw"]) and not b["sc"]:
            return [(a["v"] * 100 + b["v"]) * 100 + (b["c"] or 0), a["v"] * 100 + b["v"]]
        return []
    if len(g) == 3:
        a, b, c = g
        if a["v"] < 100 and not a["sc"] and 10 <= b["v"] <= 99 and 10 <= c["v"] <= 99 and c["c"] is None:
            return [(a["v"] * 100 + b["v"]) * 100 + c["v"]]
        if a["v"] < 100 and b["zw"] and c["v"] < 10:
            return [(a["v"] * 100 + c["v"]) * 100 + (c["c"] or 0)]
    return []


def _p_skip_run(run, pw, pw2, nw, cur, drop):
    v0 = run[0]
    if pw in _p_MONTHS or nw in _p_MONTHS or (pw == "the" and (pw2 in ("on", "by", "until", "till") or nw == "of" or pw2 in _p_MONTHS)):
        return True
    if nw in _p_TIMEU or (pw in ("past", "to") and pw2 in ("half", "quarter", "ten", "twenty", "five")):
        return True
    if len(run) == 1 and v0["v"] <= 24 and v0["c"] is None and not cur and pw in ("at", "after", "before", "until", "till", "til", "past", "by", "from"):
        return True
    if pw in ("ending", "ends", "ended") or (pw in ("in", "with") and pw2 in ("ending", "ends")):
        return True
    if any(x["lit"] and len(re.sub(r"\D", "", x["s"])) >= 8 for x in run):
        return True
    if len(run) >= 3 and all(x["v"] < 10 and not x["sc"] for x in run) and (len(run) >= 4 or not any(x["zw"] for x in run[1:-1])):
        return True
    if sum([len(re.sub(r"\D", "", x["s"])) for x in run if x["lit"]]) >= 8:
        return True
    return len(run) == 1 and v0["c"] is None and v0["v"] in drop and not cur


def _p_seg_past(txt):
    return (_p_PAST.search(_p_income(txt)) or _p_EVENT.search(txt)) and not _p_FUTW.search(txt)


def _p_amount_seg(seg, si, ctx, cands, zeros, inherit=False):
    txt = _p_segtext(seg)
    if _p_seg_past(txt) or (inherit and not _p_PAYW.search(txt)):
        return
    score = 1 + (1 if _p_PAYW.search(txt) else 0) - (2 if _p_NEGD.search(txt) else 0)
    hedged = _p_HEDGE.search(txt) is not None
    drop = []
    for x in (ctx.get("drop") or []):
        try:
            drop.append(int(x))
        except Exception:
            continue
    found = False
    n, j = len(seg), 0
    while j < n:
        if seg[j]["k"] != "n" or seg[j]["ord"]:
            j += 1
            continue
        run, k = [seg[j]], j + 1
        while k < n and (seg[k]["k"] == "n" or (seg[k]["k"] == "p" and seg[k]["w"] in ("..", "...", "-", ",") and k + 1 < n and seg[k + 1]["k"] == "n")):
            if seg[k]["k"] == "n":
                if seg[k]["ord"]:
                    break
                run.append(seg[k])
            k += 1
        pw = seg[j - 1].get("w", "") if j > 0 else ""
        pw2 = seg[j - 2].get("w", "") if j > 1 else ""
        nw = seg[k].get("w", "") if k < n else ""
        start = j
        j = k
        v0 = run[0]
        cur = pw in _p_CUR or nw in _p_CUR
        if _p_skip_run(run, pw, pw2, nw, cur, drop):
            continue
        if nw == "percent":
            base = ctx.get("ref") if re.search(r"percent of (?:that|this)", txt) else (ctx.get("full") or ctx.get("ref"))
            if base is not None and len(run) == 1:
                pct100 = v0["v"] * 100 + (v0["c"] or 0)
                cands.append({"c": _p_rhu(int(base) * pct100, 10000), "sc": score, "si": si, "pos": start, "h": hedged, "rel": True, "end": k, "cur": False})
                found = True
            continue
        if len(run) == 1 and v0["v"] == 0 and v0["c"] is None:
            zeros.append(si)
            continue
        readings = _p_run_readings(run)
        if not readings:
            for x in run:
                if not x["zw"] and x["v"] > 0:
                    cands.append({"rd": [x["v"] * 100 + (x["c"] or 0)], "sc": score, "si": si, "pos": start, "h": hedged, "end": k, "cur": cur})
                    found = True
            continue
        if len(run) == 1 and v0["c"] is None and nw in _p_CENTW and v0["v"] < 100 and not (pw in _p_CUR):
            readings = [v0["v"]]
        elif nw in _p_CUR and run[-1]["c"] is None:
            q = k + 1
            if q < n and seg[q].get("w") == "and":
                q += 1
            if q < n and seg[q]["k"] == "n" and not seg[q]["ord"] and seg[q]["v"] < 100 and seg[q]["c"] is None:
                if all(r % 100 == 0 for r in readings):
                    readings = [r + seg[q]["v"] for r in readings]
                    j = q + 1
        cands.append({"rd": readings, "sc": score + (1 if cur else 0), "si": si, "pos": start, "h": hedged, "end": k, "cur": cur})
        found = True
    if not found:
        m = _p_FRAC.search(txt)
        if m and not re.search(r"\bhalf (?:past|an hour|\d)", txt):
            word = m.group(1).split()[-1]
            num, den = _p_FRACV.get(word, (1, 2))
            ref = m.group(2) or ""
            base = ctx.get("ref") if ref in ("that", "this") else (ctx.get("full") or ctx.get("ref"))
            if base is not None:
                cands.append({"c": _p_rhu(int(base) * num, den), "sc": score, "si": si, "pos": 0, "h": hedged, "rel": True, "end": n, "cur": False})
                found = True
    if not found:
        nm = _p_named(txt, ctx.get("floor_words"))
        if nm and ctx.get(nm) is not None:
            cands.append({"c": int(ctx.get(nm)), "sc": score, "si": si, "pos": 0, "h": hedged, "named": nm, "end": n, "cur": False})


def parse_amount(text, ctx=None):
    """-> {"kind": "amount", "cents": int, "hedged": bool} | {"kind": "zero"} | {"kind": "incomplete", "frag": str}
    | {"kind": "none"}. ctx = {"known": [cents], "lo", "hi", ...} (see CONTRACT NOTE). Integer cents throughout."""
    try:
        return _p_amount(text, ctx if isinstance(ctx, dict) else dict())
    except Exception:
        return _p_none()


def _p_amount(text, ctx):
    raw = (text if isinstance(text, str) else "")
    raw = re.sub(r"\$", " dollars ", raw)
    s = norm(raw)
    if ctx.get("frag"):
        s = norm(ctx.get("frag")) + " " + re.sub(r"^[\s.\-]+", "", s)
    s = _p_IDIOM.sub(" ", s)
    if not s.strip():
        return _p_none()
    clauses = _p_clauses(s)
    for idx in range(len(clauses) - 1, -1, -1):
        r = _p_amount_clause(clauses[idx], ctx, idx == len(clauses) - 1)
        if r.get("named") == "floor" and _p_floor_rejected(s):
            # "The minimum? That's too much.": the named amount is rejected elsewhere in the turn
            return _p_none()
        if r["kind"] != "none":
            return r
        if _p_retract(clauses, idx):
            return _p_none()
    return _p_none()


def _p_amount_clause(c, ctx, is_last):
    toks = _p_lex(c)
    seps = []
    segs = _p_segments(toks, seps)
    cands, zeros = [], []
    prev_past = False
    for si, seg in enumerate(segs):
        inherit = prev_past and si < len(seps) and seps[si] == ","
        _p_amount_seg(seg, si, ctx, cands, zeros, inherit)
        prev_past = bool(_p_seg_past(_p_segtext(seg))) or inherit
    if not cands:
        if (zeros or _p_ZERO.search(c)) and not re.search(r"\b(?:until|till|til|before|unless|when|after|once)\b", c):
            r = dict()
            r["kind"] = "zero"
            return r
        return _p_none()
    best = None
    for cd in cands:
        if best is None or cd["sc"] > best["sc"]:
            best = cd
    for cd in cands:
        cd["val"] = cd["c"] if "c" in cd else _p_rank(cd["rd"], ctx)[0]
    snapped = False
    if "c" in best:
        cents = best["c"]
    else:
        cents, snapped = _p_rank(best["rd"], ctx)
    if is_last and best["si"] == len(segs) - 1 and _p_open_tail(c):
        tail = segs[-1][best["end"]:]
        if all(t["k"] == "p" or t.get("w") in ("and", "point") or t.get("w") in _p_CUR for t in tail):
            r = dict()
            r["kind"] = "incomplete"
            r["frag"] = _p_rtrim(c)
            return r
    vals = []
    for cd in cands:
        if cd is not best and cd["val"] != cents and cd["val"] not in vals and cd["sc"] >= 0:
            vals.append(cd["val"])
    r = dict()
    r["kind"] = "amount"
    r["cents"] = int(cents)
    r["hedged"] = bool(best["h"])
    if vals:
        r["alts"] = vals
    if snapped:
        r["snapped"] = True
    if best.get("named"):
        r["named"] = best["named"]
    if best.get("rel"):
        r["rel"] = True
    return r


# ---------------------------------------------------------------- dates

def _p_dom(today, n):
    """Next occurrence (on/after today) of day-of-month n."""
    if not 1 <= n <= 31:
        return None
    y, m = today.year, today.month
    while True:                                         # day n (1..31) exists within two months
        try:
            d = date(y, m, n)
            if d >= today:
                return d
        except ValueError:
            pass
        m += 1
        if m > 12:
            m, y = 1, y + 1


def _p_year_txt(s):
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace(" ", "")
    if len(s) == 4 and s.isdigit():
        return int(s)
    if len(s) == 2 and s.isdigit():
        return 2000 + int(s)
    return None


def _p_md(today, m, d, ytxt=None):
    try:
        y = _p_year_txt(ytxt)
        if y:
            return date(y, m, d)
        x = date(today.year, m, d)
        if x < today and (today - x).days > 60:
            x = date(today.year + 1, m, d)
        return x
    except Exception:
        return None


def _p_numdate(a, b, c, order):
    """Numeric parts -> date; YMD when the first part has 4 digits; order fallback swap if invalid."""
    try:
        if len(a) == 4:
            return date(int(a), int(b), int(c))
        y = int(c) if c else None
        if y is not None and y < 100:
            y += 2000
        p, q = int(a), int(b)
        d, m = (q, p) if order == "MDY" else (p, q)
        for dd, mm in ((d, m), (m, d)):
            if 1 <= mm <= 12:
                try:
                    if y is None:
                        return ("md", mm, dd)
                    return date(y, mm, dd)
                except Exception:
                    continue
    except Exception:
        pass
    return None


_p_NAMED_DAYS = (("christmas eve", 12, 24), ("christmas day", 12, 25), ("christmas", 12, 25), ("boxing day", 12, 26),
                 ("new year's eve", 12, 31), ("new years eve", 12, 31), ("new year's day", 1, 1), ("new years day", 1, 1),
                 ("new year's", 1, 1), ("new years", 1, 1), ("new year", 1, 1))
_p_VAGUE = (
    (r"\bend of (?:the |this )?month\b|\bmonth end\b|\bend of month\b", "end_of_month"),
    (r"\b(?:the|this|at the|over the|on the|next) weekend\b|\bweekend\b", "weekend"),
    (r"\bend of (?:the |this )?week\b|\bthis week\b|\blater this week\b|\bby the weekend\b", "this_week"),
    (r"\b(?:next|following) week\b|\bweek after next\b", "next_week"),
    (r"\b(?:beginning|start|early|first week|first of) (?:of )?(?:next|the) month\b|\bnext month\b|\bearly (?:" + _p_M + r")\b"
     r"|\bin (?:" + _p_M + r")\b|\bbeginning of (?:" + _p_M + r")\b", "next_month"),
    (r"\bmid(?:dle of)?(?: the)? month\b|\bmid month\b", "mid_month"),
    (r"\bpay ?day\b|\bwhen i(?:'m| am)? (?:get )?paid\b|\b(?:once|after|until|till) i get paid\b|\b(?:when|once|after|until|till) (?:my|the|our) (?:[a-z]+ ){0,2}?"
     + r"(?:salary|wages|pay|paycheck|pay check|pension|benefits|bonus|money|check|cheque)\b|\bsalary day\b|\bnext pay"
     + r"|\bnext (?:salary|wages)\b|\bget my (?:salary|wages|pay)\b|\bwhen i get my\b", "payday"),
    (r"\blater\b|\bsoon\b|\bsome ?time\b|\basap\b|\ba s a p\b|\bas soon as\b|\bat some point\b|\bin a (?:few|couple of) (?:days|weeks)\b"
     r"|\b(?:few|couple of) (?:days|weeks)\b|\bwhenever\b|\beventually\b|\bone of these days\b|\bwhen i can\b"
     r"|\bwhen i have (?:the )?money\b|\bnot sure when\b", "later"),
)


_p_NOWW = ("right now", "straight away", "right away")


def _p_blank(g, m):
    return g[:m.start()] + " " * (m.end() - m.start()) + g[m.end():]


def _p_wd(name):
    return _p_WDAYS.get((name or "").replace("'s", ""))


def _p_date_mentions(g, today, cal, opts, numd):
    out = []

    def add(pos, d, what="", pri=50, wd=None):
        if d is None and not what:
            return
        item = {"pos": pos, "d": d, "what": what, "pri": pri}
        if wd and d is not None and _p_wd(wd) is not None and _p_wd(wd) != d.weekday():
            item["wd"] = _p_wd(wd)          # "Friday the 22nd" when the 22nd is a Thursday
        out.append(item)
    for m in re.finditer(r"\bqqd([a-z])\b", g):
        x = numd[ord(m.group(1)) - 97] if ord(m.group(1)) - 97 < len(numd) else None
        if isinstance(x, tuple):
            x = _p_md(today, x[1], x[2])
        add(m.start(), x)
        g = _p_blank(g, m)
    for m in re.finditer(r"\b(?:some ?time )?before the \d{1,2}th\b|\bsome ?time before\b", g):
        add(m.start(), None, "before", 0)
        g = _p_blank(g, m)
    for name, mo, dy in _p_NAMED_DAYS:
        for m in re.finditer(r"\b" + name + r"\b", g):
            x = _p_md(today, mo, dy)
            if x is not None and x < today:
                x = _p_md(today, mo, dy, str(today.year + 1))
            add(m.start(), x)
            g = _p_blank(g, m)
    for m in re.finditer(r"\b(last|[1-5]th) (" + _p_W + r")(?:'s)? (?:of|in) (the month|this month|next month|" + _p_M + r")\b", g):
        w = _p_wd(m.group(2))
        tgt = m.group(3)
        if tgt in ("the month", "this month"):
            base = date(today.year, today.month, 1)
        elif tgt == "next month":
            base = end_of_month(today) + timedelta(days=1)
        else:
            mo = _p_MONTHS[tgt]
            base = date(today.year + (1 if mo < today.month else 0), mo, 1)
        if m.group(1) == "last":
            e = end_of_month(base)
            x = e - timedelta(days=(e.weekday() - w) % 7)
        else:
            x = base + timedelta(days=(w - base.weekday()) % 7 + 7 * (int(m.group(1)[0]) - 1))
            if x.month != base.month:
                x = None
        add(m.start(), x)
        g = _p_blank(g, m)
    for m in re.finditer(r"\blast (?:(working|business) )?day of (?:the |this )?month\b", g):
        x = last_bd_of_month(cal, today) if m.group(1) else end_of_month(today)
        add(m.start(), x)
        g = _p_blank(g, m)
    pat_dm = (r"\b(?:(" + _p_W + r")(?:'s)?,? )?(?:the )?(\d{1,2})(?:th)?\b (?:of )?(?:the )?(" + _p_M +
              r")\b(?:,? (\d{4}|\d\d \d\d|\d \d \d \d)\b)?")
    pat_md = (r"\b(?:(" + _p_W + r")(?:'s)?,? )?(" + _p_M + r") (?:the )?(\d{1,2})(?:th)?\b(?! ?(?:dollars|bucks|percent|hundred))"
              r"(?:,? (\d{4}|\d\d \d\d)\b)?")
    for m in re.finditer(pat_dm, g):
        add(m.start(), _p_md(today, _p_MONTHS[m.group(3)], int(m.group(2)), m.group(4)), wd=m.group(1))
        g = _p_blank(g, m)
    for m in re.finditer(pat_md, g):
        add(m.start(), _p_md(today, _p_MONTHS[m.group(2)], int(m.group(3)), m.group(4)), wd=m.group(1))
        g = _p_blank(g, m)
    for m in re.finditer(r"\bin (\d+) (days?|weeks?)\b|\bin a (week|fortnight)\b|\ba (week|fortnight) (?:from )?(?:today|now)\b"
                         r"|\ba (week|fortnight) today\b|\bin a couple of days\b", g):
        if m.group(1):
            k = int(m.group(1)) * (7 if m.group(2).startswith("week") else 1)
        elif "couple" in m.group(0):
            add(m.start(), None, "later")
            g = _p_blank(g, m)
            continue
        else:
            unit = m.group(3) or m.group(4) or m.group(5)
            k = 14 if unit == "fortnight" else 7
        if k <= 400:
            add(m.start(), today + timedelta(days=k))
        g = _p_blank(g, m)
    for m in re.finditer(r"\b(" + _p_W + r")(?:'s)? (week|after next|next week|this week)\b|\ba week on (" + _p_W + r")\b"
                         r"|\b(next|this) week (" + _p_W + r")\b", g):
        if m.group(3):
            x = weekday_date(cal, today, _p_wd(m.group(3)), "bare") + timedelta(days=7)
        elif m.group(5):
            s0 = today - timedelta(days=(today.weekday() - cal.get("week_start", 0)) % 7)
            s0 += timedelta(days=7 if m.group(4) == "next" else 0)
            x = s0 + timedelta(days=(_p_wd(m.group(5)) - s0.weekday()) % 7)
        else:
            w = _p_wd(m.group(1))
            kind = m.group(2)
            if kind == "week":
                x = weekday_date(cal, today, w, "bare") + timedelta(days=7)
            elif kind == "after next":
                x = today + timedelta(days=(w - today.weekday() - 1) % 7 + 8)
            else:
                s0 = today - timedelta(days=(today.weekday() - cal.get("week_start", 0)) % 7)
                s0 += timedelta(days=7 if kind == "next week" else 0)
                x = s0 + timedelta(days=(w - s0.weekday()) % 7)
        add(m.start(), x)
        g = _p_blank(g, m)
    for m in re.finditer(r"\b(?:(?:this coming|this|next|coming|on|by|last) )?(" + _p_W + r")(?:'s)?,? (?:the )?(\d{1,2})th\b"
                         r"|\b(?:on |by |for |until |till |from )?the (\d{1,2})th\b|\b(?:on|by|until|till) (\d{1,2})th\b"
                         r"|^(\d{1,2})th$", g):
        # "on thirtieth" / a lone "thirtieth..." (a date said in pieces) is the day of the month too
        add(m.start(), _p_dom(today, int(m.group(2) or m.group(3) or m.group(4) or m.group(5))), wd=m.group(1))
        g = _p_blank(g, m)
    for m in re.finditer(r"\bon the (\d{1,2})\b(?! ?(?:th\b|percent|dollars|bucks|hundred|thousand|grand|\.\d|,\d|:|[ap]m))", g):
        add(m.start(), _p_dom(today, int(m.group(1))))
        g = _p_blank(g, m)
    for m in re.finditer(r"\b(?:the )?day after tomorrow\b|\btomorrow\b|\btmrw\b|\btonight\b|\btoday\b|\bthis (?:morning|afternoon|evening)\b"
                         r"|\bright now\b|\bstraight away\b|\bright away\b|\bafter this call\b|\blater today\b|\byesterday\b", g):
        w = m.group(0)
        k = 2 if "after" in w and "tomorrow" in w else 1 if ("tomorrow" in w or w == "tmrw") else -1 if w == "yesterday" else 0
        if w in _p_NOWW and not (_p_PAYW.search(g) or len(g.split()) <= 3):
            # "I'm having a hard time right now": a state, not a payment date
            g = _p_blank(g, m)
            continue
        add(m.start(), today + timedelta(days=k))
        g = _p_blank(g, m)
    for m in re.finditer(r"\b(?:(this coming|this|next|coming|on|by|last|until|till) )?(" + _p_W + r")(?:'s)?\b", g):
        mod = m.group(1) or ""
        w = _p_wd(m.group(2))
        if mod == "this":
            x = weekday_date(cal, today, w, "this")
        elif mod == "next":
            x = weekday_date(cal, today, w, "next")
        elif mod == "last":
            x = today - timedelta(days=((today.weekday() - w) % 7) or 7)
        else:
            x = weekday_date(cal, today, w, "bare")
            if x == today and not opts.get("bare_today", False):
                x = today + timedelta(days=7)
        add(m.start(), x)
        g = _p_blank(g, m)
    for pri, pw in enumerate(_p_VAGUE):
        for m in re.finditer(pw[0], g):
            add(m.start(), None, pw[1], pri + 1)
            g = _p_blank(g, m)
    if opts.get("bare_number"):
        m = re.match(r"^\s*(?:the |on the |um |erm |uh |er )?(\d{1,2})(?:th)?\s*$", g)
        if m:
            add(0, _p_dom(today, int(m.group(1))))
    return out


def parse_date(text, today, cal, opts=None):
    """-> {"kind": "date", "date": iso} | {"kind": "vague", "what": str} | {"kind": "past", "date": iso}
    | {"kind": "incomplete", "frag": str} | {"kind": "none"}. cal = cal.prepare(...) output; opts: CONTRACT NOTE."""
    try:
        if not isinstance(today, date):
            return _p_none()
        if not isinstance(cal, dict):
            cal = prepare(None, today)
        opts = opts if isinstance(opts, dict) else dict()
        s = norm(text)
        if opts.get("frag"):
            s = norm(opts.get("frag")) + " " + re.sub(r"^[\s.\-]+", "", s)
        clauses = _p_clauses(s)
        for idx in range(len(clauses) - 1, -1, -1):
            r = _p_date_clause(clauses[idx], today, cal, opts, idx == len(clauses) - 1)
            if r["kind"] != "none":
                return r
            if _p_retract(clauses, idx):
                return _p_none()
    except Exception:
        pass
    return _p_none()


def _p_date_clause(c, today, cal, opts, is_last):
    numd = []

    def numrep(m):
        x = _p_numdate(m.group(1), m.group(2), m.group(3) or "", cal.get("numeric_order", "DMY"))
        numd.append(x)
        return " qqd%s " % chr(97 + len(numd) - 1)
    c2 = re.sub(r"\b(\d{1,4})[/.-](\d{1,2})[/.-](\d{2,4})\b|\b(\d{1,2})/(\d{1,2})\b(?!/)", lambda m: numrep(m) if m.group(1)
                else numrep(re.match(r"(\d+)/(\d+)()", m.group(0))), c)
    cs = _p_conv(c2)
    # "<weekday>, the 23rd" / "<weekday>, 23 October" / "<weekday>, October 23" are one mention (the agent's own
    # read-back format), not a bare weekday plus a second date
    cs = re.sub(r"\b(" + _p_W + r")('s)? , (?=the \d|\d{1,2}(?:th)? (?:of )?(?:the )?(?:" + _p_M + r")\b|(?:" + _p_M
                + r") (?:the )?\d)", r"\1 ", cs)
    # no \s* around the separators: every piece is stripped below, and \s* made the split quadratic on long gaps
    segs = re.split(r"\.\.+|\.(?!\d)|,|;|\bbut\b|\banyway\b|\bthough\b|\balthough\b|\bhowever\b|\bso\b"
                    r"|\band (?=i\b|i'm|i'll|my\b|we\b|she\b|he\b)", cs)
    if is_last and (re.search(r"\bthe\s*[.\-]*$", cs) or re.search(r"\bthe (?:20|30)\s*(?:\.\.+|-)\s*$", cs)
                    or re.search(r"\b(?:on|the)\s*(?:\.\.+|-)\s*$", cs)):
        r = dict()
        r["kind"] = "incomplete"
        r["frag"] = _p_rtrim(c)
        return r
    exact, vague = [], []
    for si, g in enumerate(segs):
        g = (g or "").strip()
        if not g:
            continue
        gp = _p_income(g)
        neg = _p_NEGD.search(g) is not None
        if neg and not (_p_UNTIL.search(g) and not _p_AWAY.search(g)):
            continue
        if (_p_PAST.search(gp) and not _p_FUTW.search(g)) or (_p_EVENT.search(g) and not re.search(r"\bpay\b|\bpayment\b", g)):
            continue
        score = 1 if _p_INCOME.search(g) else (3 if _p_PAYW.search(g) else 2)
        for mt in _p_date_mentions(g, today, cal, opts, numd):
            mt["sc"] = score
            mt["si"] = si
            (exact if mt["d"] is not None else vague).append(mt)
    if exact:
        fut = [x for x in exact if x["d"] >= today]
        pool = fut or exact
        best = sorted(pool, key=lambda x: (-x["sc"], x["si"], x["pos"]))[0]
        r = dict()
        r["kind"] = "date" if best["d"] >= today else "past"
        r["date"] = iso(best["d"])
        alts = []
        for x in fut:
            if x["d"] != best["d"] and iso(x["d"]) not in alts and x["sc"] >= 2:
                alts.append(iso(x["d"]))
        if alts and r["kind"] == "date":
            r["alts"] = alts
        if "wd" in best:
            r["wd_said"] = best["wd"]
        return r
    if vague:
        r = dict()
        r["kind"] = "vague"
        r["what"] = sorted(vague, key=lambda x: (x["pri"], -x["sc"], x["si"], x["pos"]))[0]["what"]
        return r
    return _p_none()


# ---------------------------------------------------------------- times

def _p_hm(h, mi, ampm, part):
    """-> sorted-by-preference list of minute readings."""
    if h > 24 or mi > 59:
        return []
    if ampm == "pm":
        return [((h % 12) + 12) * 60 + mi]
    if ampm == "am":
        return [(h % 12) * 60 + mi]
    if h >= 13 or h == 0:
        return [(h % 24) * 60 + mi]
    if h == 12:
        return [720 + mi]
    if part in ("afternoon", "evening"):
        return [(h + 12) * 60 + mi]
    if part == "morning":
        return [h * 60 + mi]
    return [h * 60 + mi, (h + 12) * 60 + mi]


def _p_part(s):
    m = re.search(r"\b(morning|afternoon|evening|tonight|night|arvo)\b", s)
    if not m:
        return ""
    return {"tonight": "evening", "night": "evening", "arvo": "afternoon"}.get(m.group(1), m.group(1))


def _p_exact(alts, off=0):
    r = dict()
    r["kind"] = "exact"
    r["min"] = alts[0]
    r["alts"] = alts
    if off:
        r["day_offset"] = off
    return r


def parse_time(text, now_min=None):
    """-> {"kind": "exact", "min": int, "alts": [int]} | {"kind": "range", "lo": int, "hi": int}
    | {"kind": "part", "part": "morning"|"afternoon"|"evening"} | {"kind": "vague"} | {"kind": "none"}."""
    try:
        clauses = _p_clauses(norm(text))
        for idx in range(len(clauses) - 1, -1, -1):
            r = _p_time_segs(clauses[idx], now_min)
            if r["kind"] != "none":
                return r
    except Exception:
        pass
    return _p_none()


_p_TSKIP = re.compile(r"\b(?:left|went|was|were|had|did|ago|last time|usually leaves|i'm|i am|i'll be|i finish|i get|"
                      r"my shift|not)\b|n't\b")


def _p_time_segs(c, now_min):
    """Times in past-tense, first-person or negated pieces ('she left at nine', 'I'm off at two', 'not nine') are skipped;
    the first exact/range time wins, else the first part-of-day/vague answer."""
    segs = [x.strip() for x in re.split(r",|;|\.(?!\d)|\bbut\b|\bso\b", c) if x.strip()]
    soft = None
    bare = [g for g in segs if _p_part(g) and not re.search(r"\d", _p_conv(g))]
    ctx_part = _p_part(bare[0]) if bare else ""
    callw = re.compile(r"\b(?:call|ring|try|phone|reach|catch)\b")
    segs = [g for g in segs if callw.search(g)] + [g for g in segs if not callw.search(g)]
    for g in segs:
        if len(segs) > 1 and _p_TSKIP.search(_p_GETPAID.sub(" ", g)) and not re.search(r"\b(?:she|he|her|him|they|them|call|ring|try)\b", g):
            continue
        if len(segs) > 1 and re.search(r"\b(?:left|ago|last time|not)\b", g):
            continue
        r = _p_time_clause(g, now_min, ctx_part)
        if r["kind"] in ("exact", "range"):
            return r
        if soft is None and r["kind"] != "none":
            soft = r
    return soft or _p_none()


def _p_range(lo, hi):
    r = dict()
    r["kind"] = "range"
    r["lo"] = lo
    r["hi"] = hi
    return r


# "in (about) an hour / 20 minutes"; a trailing " and a half" is checked after the match
_p_IN_DUR = re.compile(r"\bin (?:about |around |roughly |like )?(an?|\d+|half an?|a couple of|a few) ((?:hour|minute|min)s?)\b")
_p_AFTBEF = re.compile(r"\b(after|before) (\d{1,2})")
_p_AMPM_AT = re.compile(r" ?(am|pm)\b")
_p_NOT_HOUR = re.compile(r" ?(?:th\b|days?|weeks?|dollars|percent|minutes|hours)")
_p_WORDB = re.compile(r"\b")


def _p_after_before(cs):
    """("after"|"before", hour digits, "am"|"pm"|None) for the first "after/before H [am|pm]" that is not a count of
    something else ("after 5 days", "before the 10th"); the split form of one regex that Sonar rated too complex.
    The 1-2 digit run is always taken whole (a shorter run is followed by a digit, which neither branch accepts)."""
    for m in _p_AFTBEF.finditer(cs):
        e = m.end()
        a = _p_AMPM_AT.match(cs, e)
        if a and not _p_NOT_HOUR.match(cs, a.end()):
            return (m.group(1), m.group(2), a.group(1))
        if _p_WORDB.match(cs, e) and not _p_NOT_HOUR.match(cs, e):
            return (m.group(1), m.group(2), None)
    return None


def _p_time_clause(c, now_min, part=""):
    part = _p_part(c) or part
    c = re.sub(r"\b(?:on the dot|sharp|exactly|is fine|works|would work|is good|then|please|okay|ok|yes|yeah|fine)\b", " ", c)
    c = re.sub(r"\s+", " ", c).strip()
    cs = _p_conv(c)
    m = _p_IN_DUR.search(cs)
    if m and now_min is not None:
        q = m.group(1)
        k = 1 if q in ("a", "an") else 0.5 if q.startswith("half") else 2 if q == "a couple of" else 3 if q == "a few" else int(q)
        mins = int(k * (60 if m.group(2).startswith("hour") else 1)) + (30 if cs.startswith(" and a half", m.end()) else 0)
        t = int(now_min) + mins
        return _p_exact([t % 1440], t // 1440)
    if re.search(r"\b(?:noon|midday|twelve noon)\b", c):
        return _p_exact([720])
    if re.search(r"\bmidnight\b", c):
        return _p_exact([0])
    m = re.search(r"\b(\d{1,2})[:.](\d{2})\s*(am|pm)?\b", c)
    if m and (":" in m.group(0) or m.group(3) or re.search(r"\b(?:at|around|about|by|after|call|ring|try)\s+\d{1,2}\.\d{2}", c)):
        alts = _p_hm(int(m.group(1)), int(m.group(2)), m.group(3), part)
        if alts:
            return _p_exact(alts)

    def fix(h, ap):
        if ap:
            return _p_hm(h, 0, ap, "")[0]
        if part in ("afternoon", "evening") or 1 <= h <= 7:
            return (h % 12 + 12) * 60
        return h * 60
    rng = re.search(r"\b(?:between|from) (\d{1,2})(?: ?(am|pm))? (?:and|to|till|until|-) (\d{1,2})(?: ?(am|pm))?\b", cs)
    if rng and int(rng.group(1)) <= 12 and int(rng.group(3)) <= 12:
        lo, hi = fix(int(rng.group(1)), rng.group(2) or rng.group(4)), fix(int(rng.group(3)), rng.group(4))
        if hi >= lo:
            return _p_range(lo, hi)
    m = re.search(r"\b(half|quarter|\d{1,2}) (past|after|to|before) (\d{1,2})\b", cs)
    if m:
        q = m.group(1)
        mi = 30 if q == "half" else 15 if q == "quarter" else int(q)
        h = int(m.group(3))
        if mi < 60 and h <= 12:
            if m.group(2) in ("to", "before"):
                h, mi = (h - 1) % 12 or 12, 60 - mi
            return _p_exact(_p_hm(h, mi, None, part))  # h <= 12, mi < 60: _p_hm always has readings
    m = re.search(r"\bhalf (\d{1,2})\b(?! (?:hour|an hour|of|dollars|percent))", cs)
    if m and int(m.group(1)) <= 12:
        return _p_exact(_p_hm(int(m.group(1)), 30, None, part))
    m = _p_after_before(cs)
    if m and int(m[1]) <= 12:
        v = fix(int(m[1]), m[2] or ("am" if part == "morning" else None))
        if m[0] == "after":
            r = _p_range(v, 1439)
            r["lo_excl"] = True
            return r
        return _p_range(int(now_min) if now_min is not None else 0, v)
    hint = re.search(r"\b(?:at|around|about|by|for|call|ring|try|say|maybe|roughly)\s+(?:about |around |roughly )?\d", cs)
    whole = r"^\s*(?:um |erm |uh |er |at |around |about |say )?%s\s*(?:then|tomorrow|today|tonight|please|ish)?\s*$"
    m = re.search(r"\b(\d{1,2}) (?:0 (\d)|(\d{2}))\b ?(am|pm)?(?! ?(?:th\b|dollars|bucks|percent|days|weeks|minutes))", cs)
    if m and int(m.group(1)) <= 12 and (hint or m.group(4) or re.match(whole % r"\d{1,2} (?:0 \d|\d{2})\s*(?:am|pm)?", cs)):
        mi = int(m.group(2) if m.group(2) is not None else m.group(3))
        alts = _p_hm(int(m.group(1)), mi, m.group(4), part)
        if alts:
            return _p_exact(alts)
    m = re.search(r"\b(\d{1,2}) ?(o'clock|oclock|am|pm|ish)\b", cs)
    if m and int(m.group(1)) <= 24:
        return _p_exact(_p_hm(int(m.group(1)), 0, m.group(2) if m.group(2) in ("am", "pm") else None, part))
    m = re.search(r"\b(\d{1,2})(?: o'clock| oclock)? (?:in the (?:morning|afternoon|evening)|at night|tonight)\b", cs)
    if m and 1 <= int(m.group(1)) <= 12:
        return _p_exact(_p_hm(int(m.group(1)), 0, None, part))
    m = re.search(r"\b(?:at|around|about|by|for|call|ring|try|say|maybe|roughly)\s+(?:about |around |roughly )?(\d{1,2})\b"
                  r"(?! ?(?:th\b|days?|weeks?|minutes|hours|dollars|bucks|percent|hundred|thousand|grand|people|of))", cs)
    if not m:
        m = re.match(whole % r"(\d{1,2})", cs)
    if m and int(m.group(1)) <= 24:
        return _p_exact(_p_hm(int(m.group(1)), 0, None, part))
    if re.search(r"\b(?:after lunch|lunch ?time|later|some ?time|any ?time|whenever|in a bit|in a while|end of the day|soon"
                 r"|after work|when (?:she|he|they)(?:'s|'re| is| are| gets?| get) (?:back|home|in)|not sure|don't know)\b", c):
        r = dict()
        r["kind"] = "vague"
        return r
    if part:
        r = dict()
        r["kind"] = "part"
        r["part"] = part
        return r
    return _p_none()


def parse_day_and_time(text, today, now_min, cal):
    """-> {"date": iso or "", "date_kind": parse_date kind, "time": parse_time(...) result}."""
    r = dict()
    r["date"] = ""
    r["date_kind"] = "none"
    r["time"] = _p_none()
    try:
        d = parse_date(text, today, cal)
        t = parse_time(text, now_min)
        r["date_kind"] = d.get("kind", "none")
        r["date"] = d.get("date", "")
        r["time"] = t
        if t.get("day_offset") and d.get("kind") == "none" and isinstance(today, date):
            r["date"] = iso(today + timedelta(days=int(t["day_offset"])))
            r["date_kind"] = "date"
    except Exception:
        pass
    return r


# ---------------------------------------------------------------- dates of birth, years, digits, codes

def _p_century(yy, today):
    if isinstance(today, date):
        for base in (2000, 1900):
            if 18 <= today.year - (base + yy) <= 100:
                return base + yy
        return None
    return 1900 + yy if yy > 30 else 2000 + yy


def _p_year_strict(cs):
    """A full year from number tokens (all used): 1988, 'nineteen eighty-eight', 'twenty oh three', '1 9 8 8'."""
    n = len(cs)
    if not n or any(t["ord"] for t in cs):
        return None
    if n == 1:
        t = cs[0]
        if 1900 <= t["v"] <= 2099 and (t["sc"] or (t["lit"] and len(t["s"]) == 4)):
            return t["v"]
        return None
    a = cs[0]
    if a["v"] in (19, 20) and not a["sc"] and not a["zw"] and not a.get("zp"):
        if n == 2 and ((10 <= cs[1]["v"] <= 99 and not cs[1]["sc"]) or cs[1].get("zp")):
            return a["v"] * 100 + cs[1]["v"]
        if n == 3 and cs[1]["zw"] and cs[2]["v"] < 10:
            return a["v"] * 100 + cs[2]["v"]
    if n == 4 and all(t["v"] < 10 and not t["sc"] and not t.get("zp") for t in cs):
        y = int("".join([t["s"] for t in cs]))
        if 1900 <= y <= 2099:
            return y
    return None


def _p_year_comps(cs, today):
    """Year from leftover number tokens. -> (year | None, open) where open = the phrase may continue."""
    if not cs:
        return None, False
    y = _p_year_strict(cs)
    if y:
        return y, len(cs) == 1 and cs[0]["last"] == "scale"
    if len(cs) == 1:
        t = cs[0]
        if not t["lit"] and t["v"] in (19, 20) and t["last"] in ("teen", "tens"):
            return None, True
        if t["v"] < 100 and not t["zw"] and not t["sc"]:
            return _p_century(t["v"], today), False
        return None, False
    if len(cs) < 4 and all(t["v"] < 10 and not t["sc"] for t in cs):
        return None, True
    return None, False


def _p_find_year(items, ends=None, order="DMY", mw=False):
    """A year is a run of ADJACENT number tokens (a month word or 'of' between two numbers ends the run). Among the
    candidates the one ending last wins (a spoken date says the year last), then the longest; a numeric YMD date
    without a month word takes the first."""
    ends = ends or [i for i, _ in items]
    best = None
    for a in range(len(items)):
        for b in range(a + 1, min(a + 4, len(items)) + 1):
            if any(items[k + 1][0] != ends[k] + 1 for k in range(a, b - 1)):
                break
            y = _p_year_strict([t for _, t in items[a:b]])
            if y:
                key = (-a, b - a) if order == "YMD" and not mw else (b, b - a)
                if best is None or key > best[0]:
                    best = (key, (a, b, y))
    return best[1] if best else None


_p_AGEW = ("i'm", "im", "aged", "age", "turning", "turned", "be")


def _p_dob_toks(c):
    toks = _p_lex(c)
    out = []
    for i, t in enumerate(toks):
        if t["k"] == "n":
            pw = toks[i - 1].get("w", "") if i > 0 else ""
            nw = toks[i + 1].get("w", "") if i + 1 < len(toks) else ""
            if pw in _p_AGEW or nw in ("years", "year", "yrs", "yr"):
                continue
            out.append(t)
        elif t.get("w") in _p_MONTHS or t.get("w") in ("of", "the", "month"):
            out.append(t)
    return out


def _p_mk(s):
    return {"k": "n", "v": int(s), "s": s, "lit": True, "sc": False, "zw": False, "ord": False, "last": "dig", "c": None}


def _p_dob_clause(c, order, today):
    """-> dict with optional y m d, mw (month word), open."""
    r = dict()
    c = re.sub(r"'(\d\d)\b", r" \1", c)
    for name, mo, dy in _p_NAMED_DAYS:
        if re.search(r"\b" + name + r"\b", c):
            r["m"], r["d"], r["mw"] = mo, dy, True
            c = re.sub(r"\b" + name + r"\b", " ", c)
            break
    m = re.search(r"\b(\d{1,4})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?\b", c)
    if m:
        a, b, y = m.group(1), m.group(2), m.group(3)
        if len(a) == 4 or order == "YMD" or int(a) > 31:
            r["y"] = int(a) if len(a) == 4 else _p_century(int(a), today)
            r["m"] = int(b)
            if y:
                r["d"] = int(y)
            return r
        p, q = int(a), int(b)
        r["d"], r["m"] = (q, p) if order == "MDY" else (p, q)
        if y:
            r["y"] = int(y) if len(y) == 4 else _p_century(int(y), today)
        return r
    toks = _p_dob_toks(c)
    mpos = -1
    for i, t in enumerate(toks):
        w = t.get("w", "")
        if w in _p_MONTHS:
            near = (i > 0 and toks[i - 1]["k"] == "n") or (i + 1 < len(toks) and toks[i + 1]["k"] == "n") or (
                i + 2 < len(toks) and toks[i + 1].get("w") == "the" and toks[i + 2]["k"] == "n") or (
                i > 1 and toks[i - 1].get("w") == "of" and toks[i - 2]["k"] == "n")
            if w != "may" or near:
                mpos = i
                r["m"] = _p_MONTHS[w]
                r["mw"] = True
                break
    nums = []
    for i, t in enumerate(toks):
        if t["k"] != "n":
            continue
        prev = toks[i - 1].get("w", "") if i > 0 else ""
        prev2 = toks[i - 2].get("w", "") if i > 1 else ""
        nxt = toks[i + 1].get("w", "") if i + 1 < len(toks) else ""
        if "m" not in r and ((prev == "the" and prev2 == "of" and t["ord"]) or nxt == "month"):
            r["m"] = t["v"]
            continue
        nums.append((i, t))
    if len(nums) >= 6 and all(t["v"] < 10 and not t["sc"] for _, t in nums):
        ds = "".join([t["s"] for _, t in nums])
        nums = [(k, _p_mk(p)) for k, p in enumerate([ds[0:2], ds[2:4], ds[4:]] if len(ds) in (6, 8) else [])]
    elif len(nums) == 1 and nums[0][1]["lit"] and len(nums[0][1]["s"]) in (6, 8) and "m" not in r:
        ds = nums[0][1]["s"]
        parts = [ds[0:4], ds[4:6], ds[6:8]] if order == "YMD" and len(ds) == 8 else [ds[0:2], ds[2:4], ds[4:]]
        nums = [(k, _p_mk(p)) for k, p in enumerate(parts)]
    items = []
    ends = []
    for i, t in nums:
        if items and items[-1][1]["zw"] and not items[-1][1].get("zp") and t["v"] < 10 and not t["ord"] and not t["zw"]:
            z = dict(t)
            z["s"] = "0" + t["s"]
            z["zp"] = True
            items[-1] = (items[-1][0], z)
            ends[-1] = i
            continue
        items.append((i, t))
        ends.append(i)
    fy = _p_find_year(items, ends, order, "m" in r)
    used = set()
    if fy:
        r["y"] = fy[2]
        used = set(range(fy[0], fy[1]))
    rest = [(k, it) for k, it in enumerate(items) if k not in used]
    if "m" in r:
        day = None
        for k, it in rest:
            if it[1]["ord"] and it[1]["v"] <= 31:
                day = k
                break
        if day is None:
            best = None
            for k, it in rest:
                dist = abs(it[0] - mpos) if mpos >= 0 else 0
                if 1 <= it[1]["v"] <= 31 and not it[1]["zw"] and dist <= 2:
                    key = (dist, 0 if it[0] > mpos else 1, k)
                    if best is None or key < best:
                        best = key
            day = best[2] if best else None
        if day is not None:
            r["d"] = items[day][1]["v"]
        left = [it[1] for k, it in rest if k != day]
        if "y" not in r:
            y, op = _p_year_comps(left, today)
            if y:
                r["y"] = y
            if op:
                r["open"] = True
        elif fy and fy[1] - fy[0] == 1 and items[fy[0]][1]["last"] == "scale":
            r["open"] = True
        return r
    comps = [it[1] for k, it in rest]
    if fy:
        if items[fy[0]][1]["last"] == "scale" and fy[1] - fy[0] == 1:
            r["open"] = True
        if len(comps) >= 2:
            a, b = comps[0]["v"], comps[1]["v"]
            if fy[0] == 0 or order == "YMD":
                r["m"], r["d"] = a, b
            else:
                r["d"], r["m"] = (b, a) if order == "MDY" else (a, b)
        elif len(comps) == 1 and comps[0]["ord"]:
            r["d"] = comps[0]["v"]
        return r
    if not comps:
        return r if r else None
    first = comps[0]
    if (order == "YMD" or first["v"] > 31) and len(comps) >= 3 and first["v"] < 100:
        r["y"] = _p_century(first["v"], today)
        r["m"], r["d"] = comps[1]["v"], comps[2]["v"]
        return r
    if len(comps) >= 2:
        a, b = comps[0]["v"], comps[1]["v"]
        r["d"], r["m"] = (b, a) if order == "MDY" else (a, b)
        y, op = _p_year_comps(comps[2:], today)
        if y:
            r["y"] = y
        if op:
            r["open"] = True
        return r
    y, op = _p_year_comps(comps, today)
    if first["ord"] and first["v"] <= 31:
        r["d"] = first["v"]
    elif y:
        r["y"] = y
    if op:
        r["open"] = True
    return r


def parse_dob(text, numeric_order, today):
    """-> {"kind": "date", "y", "m", "d", "month_word": bool} | {"kind": "incomplete", "have": dict}
    | {"kind": "invalid"} | {"kind": "none"}. Corrections overlay component by component; a year phrase that stops
    on a century/tens word ('nineteen eighty...', 'two thousand...') is not complete."""
    try:
        order = numeric_order if numeric_order in ("DMY", "MDY", "YMD") else "DMY"
        s = _p_IDIOM.sub(" ", norm(text))
        acc = dict()
        mw, op = False, False
        for c in _p_clauses(s):
            r = _p_dob_clause(c, order, today)
            if not r:
                continue
            for k in ("y", "m", "d"):
                if r.get(k) is not None:
                    acc[k] = r[k]
            mw = mw or bool(r.get("mw"))
            op = bool(r.get("open"))
        if (op or "y" in acc) and _p_tail_open(s):
            acc.pop("y", None)
            op = True
        if not acc and not op:
            return _p_none()
        if "m" in acc and not 1 <= acc["m"] <= 12:
            return {"kind": "invalid"}
        if "d" in acc and not 1 <= acc["d"] <= 31:
            return {"kind": "invalid"}
        if all(k in acc for k in ("y", "m", "d")):
            try:
                date(acc["y"], acc["m"], acc["d"])
            except Exception:
                return {"kind": "invalid"}
            out = {"kind": "date", "y": acc["y"], "m": acc["m"], "d": acc["d"]}
            out["month_word"] = mw
            return out
        out = {"kind": "incomplete"}
        out["have"] = acc
        return out
    except Exception:
        return _p_none()


def parse_year(text, today=None):
    """-> int year or None (2-digit years only when today is given)."""
    try:
        r = parse_dob(text, "DMY", today)
        if r.get("kind") == "date":
            return r["y"]
        if r.get("kind") == "incomplete" and r["have"].get("y"):
            return r["have"]["y"]
        return None
    except Exception:
        return None


def _p_digit_words(s):
    raw = _p_tokens(re.sub(r"(?<=[a-z0-9])-(?=[a-z0-9])", " ", s))
    homo = {"to": "two", "too": "two", "won": "one", "ate": "eight", "tree": "three", "fore": "four"}
    homo["for"] = "four"
    real = [(_p_isnum(w) and w not in _p_SCALES) or w in _p_ZW for w in raw]
    mark = list(real)
    for _ in range(4):
        for i, w in enumerate(raw):
            if w in homo and not mark[i]:
                if (i > 0 and mark[i - 1]) or (i + 1 < len(raw) and mark[i + 1]):
                    mark[i] = True
    i = 0
    while i < len(raw):
        if raw[i] in homo and not mark[i]:
            j = i
            while j < len(raw) and raw[j] in homo:
                j += 1
            if j - i >= 3:
                for q in range(i, j):
                    mark[q] = True
            i = j
        else:
            i += 1
    return " ".join([homo[w] if (w in homo and mark[i] and not real[i]) else w for i, w in enumerate(raw)])


def parse_digits(text):
    """Spoken digits -> digit string ('oh'/'zero', 'double', 'triple', pairs like 'forty-four'); '' if none.
    The longest digit cluster wins (clusters break at other words); corrections: last clause with digits."""
    try:
        clauses = _p_clauses(norm(text))
        for idx in range(len(clauses) - 1, -1, -1):
            d = _p_digits_clause(clauses[idx])
            if d:
                return d
    except Exception:
        pass
    return ""


_p_DFILL = ("and", "um", "uh", "er", "erm", "its", "it's", "is", "then", "like", "dash")


def _p_digits_clause(c):
    toks = _p_lex(_p_digit_words(c))
    clusters, cur, rep = [], "", 1
    for t in toks:
        if t["k"] == "n":
            if t["ord"]:
                if cur:
                    clusters.append(cur)
                cur, rep = "", 1
                continue
            ds = re.sub(r"\D", "", t["s"]) if t["lit"] else t["s"]
            cur += ds * rep
            rep = 1
        elif t.get("w") in ("double", "triple"):
            rep = 2 if t["w"] == "double" else 3
        elif t["k"] == "p" or t.get("w") in _p_DFILL:
            continue
        else:
            if cur:
                clusters.append(cur)
            cur, rep = "", 1
    if cur:
        clusters.append(cur)
    best = ""
    for x in clusters:
        if len(x) > len(best):
            best = x
    return best


_p_NATO = {"alpha": "a", "alfa": "a", "bravo": "b", "charlie": "c", "delta": "d", "echo": "e", "foxtrot": "f", "golf": "g", "hotel": "h", "india": "i", "juliet": "j", "juliett": "j", "kilo": "k", "lima": "l", "mike": "m", "november": "n", "oscar": "o", "papa": "p", "quebec": "q", "romeo": "r", "sierra": "s", "tango": "t", "uniform": "u", "victor": "v", "whiskey": "w", "whisky": "w", "xray": "x", "yankee": "y", "zulu": "z"}


def parse_alnum(text):
    """Letters (incl. NATO words, 'double A') + digits -> uppercase string without spaces; the longest code cluster."""
    try:
        s = norm(text).replace("x-ray", "xray")
        words = re.findall(r"[a-z0-9]+(?:'[a-z]+)?|[,.\-]", s)
        z = _p_zero_marks(words)
        clusters, cur, rep, numbuf = [], [], 1, []

        def flush_num():
            if numbuf:
                for t in _p_lex(" ".join(numbuf)):
                    if t["k"] == "n":
                        cur.append(re.sub(r"\D", "", t["s"]) if t["lit"] else t["s"])
                del numbuf[:]
        for i, w in enumerate(words):
            isnum = (_p_isnum(w) and w not in _p_SCALES and w not in _p_ORDS) or z[i]
            if isnum and not re.search(r"[a-z]", w[:1]) and re.search(r"[a-z]", w):
                isnum = False
            if isnum:
                numbuf.append("zero" if z[i] else w)
                if rep > 1:
                    flush_num()
                    if cur:
                        cur[-1] = cur[-1] * rep
                    rep = 1
                continue
            flush_num()
            if w in ("double", "triple"):
                rep = 2 if w == "double" else 3
                continue
            if w in (",", ".", "-"):
                continue
            tok = None
            if w in _p_NATO:
                tok = _p_NATO[w]
            elif len(w) == 1 and w.isalpha():
                tok = w
            elif re.match(r"^(?=.*\d)(?=.*[a-z])[a-z0-9]+$", w):
                tok = w
            if tok is None:
                if cur:
                    clusters.append("".join(cur))
                cur = []
                rep = 1
                continue
            cur.append(tok * rep)
            rep = 1
        flush_num()
        if cur:
            clusters.append("".join(cur))
        best = ""
        for x in clusters:
            if len(x) > len(best):
                best = x
        return best.upper()
    except Exception:
        return ""


# ---------------------------------------------------------------- yes / no and turn shapes

_p_YES = re.compile(r"\b(?:yes|yeah|yea|yep|yup|ya|aye|sure|ok|okay|alright|all right|fine|correct|absolutely|definitely|"
                    r"certainly|of course|agreed|deal|i confirm|confirmed|confirm|go ahead|sounds good|works for me|that works|"
                    r"perfect|great|mhm|mm-?hm|uh-? ?huh|affirmative|please do|let's do it|do it|i do|will do|that's right|thats right|"
                    r"that is right|exactly|indeed|that's me|it's me|speaking|i suppose so|i guess so|i think so|"
                    r"i can(?!'t| not|not)|i will(?! not)|yes please|that's fine|that's good|that'll work|go for it)\b")
_p_YESSWAP = re.compile(r"\b(?:no problem|not a problem|no worries|why not|no doubt)\b")
_p_NOSTRONG = re.compile(r"\b(?:of course not|absolutely not|definitely not|certainly not|no way|not at all|no thanks|no thank you)\b")
_p_NO = re.compile(r"\b(?:no|nope|nah|not really|negative|not possible|not today|not now|i won't|i will not|i don't|i do not|"
                   r"never|not that|i'd rather not|rather not|not happening)\b")
_p_CANT = re.compile(r"\b(?:can't|cant|cannot|can not|unable|won't be able|not able|couldn't|won't|wont|can't afford|no way)\b")
_p_NEGQ = re.compile(r"(?:^|[.,;!?] *)(?:why |how come )?(?:can't|cannot|couldn't|won't|wouldn't|don't|doesn't|isn't|aren't)"
                     r" (?=(?:you|we|they|it|there|the bank|i)\b)")
_p_HEDGEY = re.compile(r"\b(?:maybe|perhaps|probably|possibly|i think|i guess|i suppose|i'll try|i will try|try|trying|"
                       r"hopefully|should be|should|might|not sure|i don't know|dunno|we'll see|do my best|kind of|sort of|"
                       r"i hope|if i can|i believe|whatever|if you say so|i don't care)\b")
_p_ZEROPAY = re.compile(r"\b(?:pay|give|afford|manage|send)\s+(?:you\s+)?(?:nothing|zero|0|not a (?:penny|cent|dime|thing)|"
                        r"not one (?:penny|cent))\b|\bnot a (?:penny|cent|dime)\b")
_p_NOTNOW = re.compile(r"(?:\b(?:just|but|only|simply)\s+)?\bnot (?:today|now|right now|this (?:week|month)|next (?:week|month)"
                       r"|yet|until|before)\b")
_p_NEVERMIND = re.compile(r"\b(?:never ?mind|forget (?:it|that)|no matter)\b")
_p_THANICAN = re.compile(r"\bthan i (?:can|could)\b")
# "No, the date should be Friday": a correction, not a hedge
_p_NOCORR = re.compile(r"^\W*(?:no|nope|nah)\b.{0,40}?\b(?:should be|should say|was supposed to be)\b")
_p_COND = re.compile(r"\b(?:if|as long as|provided|providing|assuming|unless|depends|only if|on condition)\b")
_p_CORRY = re.compile(r"\b(?:sorry|i mean|no wait|wait|actually|instead|rather|hang on|hold on|scratch that|make it|make that|change)\b")


def yes_no(text):
    """-> {"yn": "yes"|"no"|"", "hedge": bool, "cond": bool, "corr": bool, "cant": bool, "question": bool}."""
    r = {"yn": "", "hedge": False, "cond": False, "corr": False, "cant": False, "question": False}
    try:
        t = norm(text)
        t2 = _p_YESSWAP.sub(" yes ", t)
        t3 = re.sub(r"\b(?:i don't know|not sure|dunno)\b", " ", t2)
        t3 = _p_THANICAN.sub(" ", t3)
        if _p_NEVERMIND.search(t3) and _p_YES.search(_p_NEVERMIND.sub(" ", t3)):
            # "Never mind, that's correct." takes back an objection
            t3 = _p_NEVERMIND.sub(" ", t3)
        if is_question(text):
            # "Can't you give me a discount?" asks; it is not a refusal (nor is "Why can't we...")
            t3 = _p_NEGQ.sub(" ", t3)
        cant = _p_CANT.search(t3) is not None
        my = _p_YES.search(t3)
        mn = _p_NO.search(t3)
        short = len(t.split()) <= 3
        if not my and short and re.search(r"\b(?:right|good|great|fine|cool|grand|lovely)\b", t3):
            my = re.search(r"\b(?:right|good|great|fine|cool|grand|lovely)\b", t3)
        if _p_NOSTRONG.search(t3):
            r["yn"] = "no"
        elif my and (mn or cant):
            first_no = min([x.start() for x in (mn, _p_CANT.search(t3)) if x is not None])
            r["yn"] = "yes" if my.start() < first_no else "no"
        elif my:
            r["yn"] = "yes"
        elif mn or cant:
            r["yn"] = "no"
        if _p_ZEROPAY.search(t3):
            r["yn"] = "no"
            cant = True
        if r["yn"] == "yes" and _p_NOTNOW.search(t3):
            cant = True
        r["cant"] = cant
        r["hedge"] = _p_HEDGEY.search(t2) is not None
        r["cond"] = _p_COND.search(t) is not None
        r["corr"] = _p_CORRY.search(t) is not None
        if _p_NOCORR.search(t):
            r["hedge"] = False
            r["corr"] = True
        r["question"] = is_question(text)
    except Exception:
        pass
    return r


_p_GREET = re.compile(r"\b(?:hello there|hi there|hello|hallo|hullo|hi|hey|hiya|howdy|yo|good (?:morning|afternoon|evening|day)|"
                      r"who's this|who is this|who's that|who is that|who's calling|who is calling|who's speaking|who is speaking|"
                      r"who are you|who's there|go ahead|yes|yeah|yep|yup|um|uh|erm|er|hm+|sorry|pardon|speaking|can i help you|"
                      r"how can i help|what's this|what is this)\b")


def is_greeting_only(text):
    """True for 'hello?', 'hi', 'yes?' (with a question mark), 'go ahead', 'who's this' with no answer content."""
    try:
        raw = text if isinstance(text, str) else ""
        t = norm(raw)
        if not t:
            return False
        rest = re.sub(r"[\s.,'-]+", "", _p_GREET.sub(" ", t))
        if rest:
            return False
        if re.search(r"\b(?:yes|yeah|yep|yup|speaking)\b", t) and "?" not in raw:
            return False
        return True
    except Exception:
        return False


def is_question(text):
    """True if the turn asks something ('?' or an interrogative opening)."""
    try:
        raw = text if isinstance(text, str) else ""
        if "?" in raw:
            return True
        t = norm(raw)
        if re.match(r"^(?:do it|will do|can do|could do with)\b", t):
            return False
        return re.match(r"^(?:what|why|who|whom|whose|how|when|where|which|is|are|am|can|could|do|does|did|would|should|"
                        r"shall|may)\b", t) is not None
    except Exception:
        return False


_p_PAIDRE = re.compile(r"\b(?:paid|sent (?:it|the money|the payment|that|this)|i sent|i've sent|we sent|made (?:the|a|that) payment|"
                       r"transferred|settled (?:it|that|this|up)|cleared (?:it|that|this|the))\b")
_p_PAIDNEG = re.compile(r"\b(?:haven't|have not|hasn't|has not|didn't|did not|not paid|never paid|not yet|yet to|wasn't|isn't|"
                        r"won't|can't)\b")
_p_FUT = re.compile(r"\b(?:will|i'll|we'll|she'll|he'll|going to|gonna|tomorrow|tonight|later|next|soon|plan to|planning to|"
                    r"want to|would like to|i'd)\b")


_p_PAIDSPLIT = re.compile(r"[,;.!?]+|\bbut\b")
# a negated tag question about the money after the claim ("didn't you get it?", "can't you see it?")
_p_PAIDQ = re.compile(r"n't (?:you|it|they)\b|\b(?:did|have|has|can) not (?:you|it|they)\b")


def has_completed_payment(text):
    """True if the text claims a completed payment (past/perfect pay verb, no negation, no future marker)."""
    try:
        raw = text if isinstance(text, str) else ""
        t = _p_income(norm(raw))
        if not _p_PAIDRE.search(t) or _p_FUT.search(t):
            return False
        if "?" in raw and re.match(r"^\s*(?:have|has|did|was|is|were|do|does)\b", norm(raw)):
            return False
        # the negation must be in a clause that carries the pay verb: "I paid it last week, didn't you get it?"
        # is a paid claim; "I haven't paid yet" / "paid? no, not yet" are not
        for cl in _p_PAIDSPLIT.split(raw.lower()):
            c2 = _p_income(norm(cl))
            if _p_PAIDRE.search(c2) and not _p_PAIDNEG.search(c2):
                return not _p_PAIDNEG.search(t) or _p_PAIDQ.search(t) is not None
        return False
    except Exception:
        return False


def match_any(patterns, text):
    """Case-insensitive regex search over patterns (str or list); invalid regexes are ignored."""
    try:
        if isinstance(patterns, str):
            patterns = [patterns]
        t = text if isinstance(text, str) else ("" if text is None else str(text))
        for p in (patterns or []):
            try:
                if p and re.search(p, t, re.I):
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False
