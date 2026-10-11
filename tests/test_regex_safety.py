"""Regex safety (SonarQube python:S8786 / S5843 / S6353).

Customer text reaches the runtime parsers on every turn inside a time-limited code node, so no pattern may backtrack
super-linearly. Every rewritten pattern is checked two ways:
- differential: the old pattern (kept here only as a reference) and the new code agree on a seeded random corpus of
  near-matches, so matching behaviour is unchanged;
- timing: 8,000-char adversarial near-matches finish in under 50 ms (the old forms took 100 ms to seconds there:
  quadratic, and cubic for the brief heading pattern).
The brain also caps every sensor string before parsing (_B_MAX_TEXT), checked end to end at the bottom."""
import datetime
import json
import random
import re
import time

import pytest

from builder import llm
from builder.compiler import lint, render as crender
from builder.pipeline import segment, validate
from runtime import brain, cal, ident, parse

N = 8000            # adversarial input length (4x the 2,000-char target, so a quadratic form cannot pass)
BUDGET_MS = 50.0    # per call
RNG_SEED = 20261011


def _ms(fn, *a):
    t = time.perf_counter()
    fn(*a)
    return (time.perf_counter() - t) * 1000.0


def _fast(fn, *a):
    """Best of 3 runs (scheduler noise on a shared machine), in ms."""
    return min(_ms(fn, *a) for _ in range(3))


def _rep(unit, n=N):
    return (unit * (n // len(unit) + 1))[:n]


def _corpus(alphabet, count=1500, max_len=12, seed=RNG_SEED):
    rng = random.Random(seed)
    return ["".join(rng.choice(alphabet) for _ in range(rng.randint(0, max_len))) for _ in range(count)]


# ------------------------------------------------------------------------------------------- runtime/parse.py
OLD_TOK = re.compile(r"\d+(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d+(?:st|nd|rd|th)\b|\d+|[a-z]+(?:'[a-z]+)?|\.\.+|[.,:;/-]")


def test_tok_same_tokens_as_old_pattern():
    alpha = ["1", "12", "123", ",", ".", "st", "nd", "th", "a", "'", "s", " ", "-", "..", ":", "/", "rd", "x"]
    for s in _corpus(alpha) + ["1,234.56", "1,23", "12.5", "21st", "1st.", "1,234,567", "3rd", "don't", "1..2"]:
        assert parse._p_tokens(s) == OLD_TOK.findall(s), s


@pytest.mark.parametrize("unit", ["1", "1,", "1.", "1,123", "12th", "a'"])
def test_tok_linear(unit):
    assert _fast(parse._p_tokens, _rep(unit) + "x") < BUDGET_MS


def test_rtrim_same_as_old_pattern():
    alpha = [" ", ".", "-", "a", "1", "\t", "\n", " ", "x."]
    for s in _corpus(alpha):
        assert parse._p_rtrim(s) == re.sub(r"[\s.\-]+$", "", s), repr(s)


@pytest.mark.parametrize("unit", [" ", ".", "-", " .", ". -"])
def test_rtrim_linear(unit):
    assert _fast(parse._p_rtrim, _rep(unit) + "x") < BUDGET_MS
    assert _fast(parse._p_rtrim, _rep(unit)) < BUDGET_MS


def test_open_tail_same_as_old_pattern():
    alpha = [" ", ".", "-", "and", "point", "band", "a", "1", "\n", "x"]
    for s in _corpus(alpha):
        assert parse._p_open_tail(s) == bool(re.search(r"(?:\.\.+|-|\band|\bpoint)\s*$", s)), repr(s)


@pytest.mark.parametrize("unit", ["..", ". ", "- ", "and ", "1.."])
def test_open_tail_linear(unit):
    assert _fast(parse._p_open_tail, _rep(unit) + " 5") < BUDGET_MS


def _pieces(parts):
    return [x.strip() for x in parts]


OLD_DATE_SPLIT = (r"\s*(?:\.\.+|\.(?!\d)|,|;|\bbut\b|\banyway\b|\bthough\b|\balthough\b|\bhowever\b|\bso\b"
                  r"|\band (?=i\b|i'm|i'll|my\b|we\b|she\b|he\b))\s*")
NEW_DATE_SPLIT = (r"\.\.+|\.(?!\d)|,|;|\bbut\b|\banyway\b|\bthough\b|\balthough\b|\bhowever\b|\bso\b"
                  r"|\band (?=i\b|i'm|i'll|my\b|we\b|she\b|he\b)")


def test_date_clause_split_same_pieces_as_old_pattern():
    """Pieces are stripped and indexed by the caller: count and stripped text must match exactly."""
    alpha = [" ", ",", ".", "..", ";", "but", "so", "and ", "i", "my", "1", "x", "however", "though"]
    for s in _corpus(alpha):
        assert _pieces(re.split(NEW_DATE_SPLIT, s)) == _pieces(re.split(OLD_DATE_SPLIT, s)), repr(s)


def test_time_split_same_pieces_as_old_pattern():
    alpha = [" ", ",", ".", ";", "but", "so", "1", "x", "\t"]
    for s in _corpus(alpha):
        old = [x.strip() for x in re.split(r"\s*(?:,|;|\.(?!\d)|\bbut\b|\bso\b)\s*", s) if x.strip()]
        new = [x.strip() for x in re.split(r",|;|\.(?!\d)|\bbut\b|\bso\b", s) if x.strip()]
        assert new == old, repr(s)


@pytest.mark.parametrize("pat", [NEW_DATE_SPLIT, r",|;|\.(?!\d)|\bbut\b|\bso\b"])
@pytest.mark.parametrize("unit", [" ", "\t", " x", ". "])
def test_splits_linear(pat, unit):
    assert _fast(re.split, pat, _rep(unit) + "!") < BUDGET_MS


OLD_IN_DUR = re.compile(r"\bin (?:about |around |roughly |like )?(an?|\d+|half an?|a couple of|a few) "
                        r"(hours?|minutes?|mins?)\b( and a half)?")


def _new_in_dur(cs):
    m = parse._p_IN_DUR.search(cs)
    return m and (m.start(), m.group(1), m.group(2), cs.startswith(" and a half", m.end()))


def test_in_duration_same_as_old_pattern():
    alpha = ["in ", "about ", "an ", "a ", "half ", "2", "20 ", "hour", "hours", "minute", "mins", "s", " and a half",
             "a couple of ", "a few ", "x", " "]
    for s in _corpus(alpha, count=3000) + ["call me in an hour and a half", "in 20 minutes", "in a couple of hours"]:
        m = OLD_IN_DUR.search(s)
        old = m and (m.start(), m.group(1), m.group(2), m.group(3) is not None)
        assert _new_in_dur(s) == old, repr(s)


OLD_AFTBEF = re.compile(r"\b(after|before) (\d{1,2})(?: ?(am|pm))?\b(?! ?(?:th\b|days?|weeks?|dollars|percent|minutes"
                        r"|hours))")


def test_after_before_same_as_old_pattern():
    alpha = ["after ", "before ", "1", "12", "3", "am", "pm", " am", " pm", "th", " days", "day", " weeks", "dollars",
             " percent", " minutes", "hours", "x", " ", "5 "]
    extra = ["after 3 pm days", "after 5 days", "before the 10th", "after 10am", "after 3 pmdays", "after 123",
             "after after 5", "before 12 pm", "after 7 then", "after 3 percent"]
    for s in _corpus(alpha, count=4000) + extra:
        m = OLD_AFTBEF.search(s)
        old = m and (m.group(1), m.group(2), m.group(3))
        assert parse._p_after_before(s) == old, repr(s)


@pytest.mark.parametrize("unit", ["after 1 ", "after 12 days ", "in a ", "in 2 hours "])
def test_time_helpers_linear(unit):
    s = _rep(unit) + "x"
    assert _fast(parse._p_after_before, s) < BUDGET_MS
    assert _fast(parse._p_IN_DUR.search, s) < BUDGET_MS


# ------------------------------------------------------------------- whole parsers on adversarial near-matches
TODAY = datetime.date(2026, 3, 10)
CAL = cal.prepare({}, TODAY)
UNITS = [" ", ".", "-", " .", "...", "?", "1", "1,", "..1", "x-", "z'", "1 2 ", "in a ", "after 1 ", "paid the x ",
         "yes, ", "no ", "but ", ", ", "four hundred and ", "the ", "i'll pay ", "wait ", "sorry ", "1/", "\t", "a1"]
PARSERS = [
    ("amount", lambda t: parse.parse_amount(t, {"full": 46351, "floor": 10000, "known": [46351]})),
    ("date", lambda t: parse.parse_date(t, TODAY, CAL)),
    ("time", lambda t: parse.parse_time(t, 600)),
    ("day_and_time", lambda t: parse.parse_day_and_time(t, TODAY, 600, CAL)),
    ("yes_no", parse.yes_no),
    ("rp", lambda t: ident.rp_classify(t, "", ["john", "smith"])),
]


@pytest.mark.parametrize("name,fn", PARSERS, ids=[p[0] for p in PARSERS])
def test_parsers_bounded_on_adversarial_text(name, fn):
    """At the brain's text cap every parser stays fast on repeated near-matches (the old regexes took ~20 ms here
    and ~300 ms at 8,000 chars)."""
    worst = 0.0
    for u in UNITS:
        for tail in ("", "x", " 5", "!"):
            worst = max(worst, _fast(fn, _rep(u, brain._B_MAX_TEXT) + tail))
    assert worst < 4 * BUDGET_MS, (name, worst)


# ------------------------------------------------------------------------------------------- runtime/brain.py
def test_render_spacing_same_as_old_pattern():
    alpha = [" ", "  ", "\t", ".", ",", "?", "!", "a", "b ", "\n"]
    for s in _corpus(alpha):
        collapsed = re.sub(r"\s+", " ", s).strip()
        assert re.sub(r" ([.,?!])", r"\1", collapsed) == re.sub(r"\s+([.,?!])", r"\1", collapsed), repr(s)
    assert brain.render("Hello  <v:first_name> ,  how are you ?", {"call": {"first_name": "Ann"}}) == \
        "Hello Ann, how are you?"


def test_render_linear():
    assert _fast(brain.render, _rep(" \t") + "x", {}) < BUDGET_MS


OLD_OFFER = r"^\s*(?:would you like me to|do you want me to|shall i|should i|may i|can i)\s+(.+?)\s*\?\s*$"


def test_offer_action_same_as_old_pattern():
    alpha = ["would you like me to ", "Would you like me to", "shall i ", "Can I", "can is ", "transfer you", " ",
             "?", "  ", "now", "\n", "x", "?  "]
    corpus = _corpus(alpha, count=4000, max_len=6)
    corpus += ["Would you like me to connect you with our support team?", "Shall I transfer you now ?  ",
               "May I put you through?", "Can I help?", "Would you like me to?", "do you want me to do it??"]
    checked = 0
    for s in corpus:
        m = re.match(OLD_OFFER, s, re.I)
        old = m.group(1) if m else None
        if old is not None and not old.strip():
            continue        # "Shall I  ?" (no action; the renderer never produces the double space it needs)
        assert brain._b_offer_action(s) == old, repr(s)
        checked += old is not None
    assert checked > 50


@pytest.mark.parametrize("unit", [" ", "x ", "? ", "x?"])
def test_offer_action_linear(unit):
    assert _fast(brain._b_offer_action, "Would you like me to " + _rep(unit) + "!") < BUDGET_MS


def test_offer_turned_into_statement():
    c = {"S": {}, "call": {}, "today": TODAY}
    a = {"say": "I am sorry to hear that. Would you like me to connect you with our support team?"}
    assert brain._b_accept_say(c, a) == "I will connect you with our support team now."


def test_lit_parses_python_and_json_literals():
    rng = random.Random(RNG_SEED)

    def gen(d=0):
        k = rng.randint(0, 6 if d < 3 else 4)
        if k == 0:
            return rng.choice([True, False, None])
        if k == 1:
            return rng.randint(-10 ** 6, 10 ** 6)
        if k == 2:
            return rng.choice([0.5, -2.25, 1e-3, 123.0])
        if k in (3, 4):
            return rng.choice(["", "a", "it's", "x y", "1,2"])
        if k == 5:
            return [gen(d + 1) for _ in range(rng.randint(0, 4))]
        return dict((rng.choice("abcdef"), gen(d + 1)) for _ in range(rng.randint(0, 4)))
    for _ in range(400):
        v = gen()
        assert brain._b_lit(repr(v)) == v
        assert brain._b_lit(json.dumps(v)) == v
    assert brain._b_lit("[True, null, -3, 2.5e2]") == [True, None, -3, 250.0]
    assert brain._b_lit("[Truex]") is None
    assert brain._b_lit("[1, -]") is None


def test_lit_long_list_linear():
    """Products as a Python repr: each token was matched on a fresh slice of the rest of the string."""
    rows = [{"product_id": "p%d" % i, "amount": 123.45 + i, "active": True, "note": None} for i in range(3000)]
    s = repr(rows)
    assert brain._b_lit(s) == rows
    assert _ms(brain._b_lit, s) < 2000


def test_closed_split_same_as_old_pattern():
    old = re.compile(r"\b(paid (?:it |that |this |them |the \w+ |my \w+ )?off|closed|cancell?ed|shut down)\b")
    alpha = ["paid ", "it ", "that ", "the ", "my ", "card ", "off", "closed", "canceled", "cancelled", "shut down",
             "x", " ", "offx", "them "]
    for s in _corpus(alpha, count=3000):
        new = bool(brain._B_CLOSED_PAID.search(s) or brain._B_CLOSED_WORD.search(s))
        assert new == bool(old.search(s)), repr(s)


def test_placeholder_pattern_same_as_old():
    old = re.compile(r"<(v:[A-Za-z_][A-Za-z0-9_]*|f:[A-Za-z_][A-Za-z0-9_.]*|[a-z_]+)>")
    alpha = ["<", ">", "v:", "f:", "a", "Z", "_", "9", ".", "é", "١", "x", " ", "product"]
    for s in _corpus(alpha, count=3000):
        assert brain._B_PH.findall(s) == old.findall(s), repr(s)


OLD_CLAUSE = re.compile(r"(?:,?\s+\bbut\b\s+|;\s*|\.\s+|,\s+(?:and\s+)?(?=(?:i|i'm|i'll|i will|i can|not|the)\b)"
                        r"|\s+\bwhereas\b\s+|\s+\band\b\s+(?=(?:i'm|i am|i'll|i will|i can't|i cannot|i won't|not)\b))")


def test_clause_split_same_as_old_pattern():
    alpha = [" ", "  ", "\t", ",", ";", ".", "but", "and", "whereas", "i", "i'm", "not", "the", "x", "pay", "\n"]
    for s in _corpus(alpha, count=5000):
        assert brain._B_CLAUSE.split(s) == OLD_CLAUSE.split(s), repr(s)


@pytest.mark.parametrize("unit", [" ", "\t ", " x", ", "])
def test_clause_split_linear(unit):
    assert _fast(brain._B_CLAUSE.split, _rep(unit) + "!") < BUDGET_MS


# ------------------------------------------------------------------------------------- runtime/cal.py, ident.py
OLD_NOW = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[t ]+(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?\s*(am|pm)?)?"
                     r"\s*(?:z|[+-]\d{2}:?\d{2})?$")


def test_now_parts_same_as_old_pattern():
    alpha = ["2026-01-07", "2026-1-7", "t", " ", "11:00", "9:05", ":30", ".123", "am", "pm", "z", "+05:00", "-0500",
             "1", ":", "x", "t "]
    corpus = _corpus(alpha, count=4000, max_len=6)
    corpus = [s for s in corpus if s.startswith("2026")] + ["2026-01-07t11:00:00.5z", "2026-01-07 11:00 pm +0500",
                                                            "2026-01-071", "2026-01-07 t11:00", "2026-01-07"]
    hits = 0
    for s in corpus:
        m = OLD_NOW.match(s)
        old = m and (m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(7))
        assert cal._c_now_iso(s) == (old or None), repr(s)
        hits += bool(m)
    assert hits > 50
    assert cal.parse_now("2026-01-07T11:00:00Z") == (datetime.date(2026, 1, 7), 660)
    old_sl = re.compile(r"^(\d{1,2})[/.](\d{1,2})[/.](\d{4})(?:[t ,]+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)?)?$")
    heads = [a + s1 + b + s2 + y for a in ("7", "07", "13", "123") for b in ("1", "12", "") for s1 in "/." for s2 in "/-"
             for y in ("2026", "226")]
    tails = _corpus(["t", " ", ",", "11:00", "9:05", ":30", "am", "pm", "1", "x", ".5"], count=60, max_len=5)
    hits = 0
    for s in [h + t for h in heads for t in tails]:
        m = old_sl.match(s)
        old = m and (m.group(3), m.group(1), m.group(2), m.group(4), m.group(5), m.group(7))
        assert cal._c_now_slash(s) == (old or None), repr(s)
        hits += bool(m)
    assert hits > 20
    assert cal.parse_now("07/01/2026 2:30 pm") == (datetime.date(2026, 1, 7), 870)


def test_digits_only_same_as_old_pattern():
    for s in _corpus(["1", "a", " ", "١", "-", "9", "１"]):
        assert ident._i_digits_only(s) == re.sub(r"[^0-9]", "", s)


OLD_SELF_POST = re.compile(r"\b([a-z][a-z'\-]+)\s+(?:speaking|here)\b")


def test_self_post_names_same_as_old_pattern():
    alpha = ["a", "b", "x", "'", "-", " ", "  ", "speaking", "here", "1", "_", "é", "heres", "bob "]
    extra = ["jean-paul here", "'bob here", "1ab-cd here", "here-and here", "x-x here speaking", "anna speaking"]
    for s in _corpus(alpha, count=5000) + extra:
        assert ident._i_self_post(s) == [m.group(1) for m in OLD_SELF_POST.finditer(s)], repr(s)


@pytest.mark.parametrize("unit", ["x-", "z'", "ab-", "x-x "])
def test_self_post_linear(unit):
    assert _fast(ident._i_self_post, _rep(unit) + "!") < BUDGET_MS
    assert _fast(ident._i_self_post, _rep(unit) + " here") < BUDGET_MS


# --------------------------------------------------------------------------------------------- builder side
def test_lint_placeholders_same_as_old_pattern():
    old = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")
    for s in _corpus(["{{", "}}", "{", "}", " ", "a", "x:json", "\t", "b"], count=3000):
        assert lint._vars_in(s) == [v.strip() for v in old.findall(s)] == old.findall(s), repr(s)
    assert _fast(lint._vars_in, "{{" + _rep(" ") + "x") < BUDGET_MS


def test_fenced_blocks_same_as_old_pattern():
    old = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
    for s in _corpus(["```", "`", "json", " ", "\n", "{}", "a", "``"], count=3000):
        assert llm._fenced_blocks(s) == [m.group(1).strip() for m in old.finditer(s)], repr(s)
    assert _fast(llm._fenced_blocks, "```" + _rep(" \n")) < BUDGET_MS
    assert _fast(llm._fenced_blocks, "```" + _rep(" ") + "x") < BUDGET_MS
    assert _fast(llm._fenced_blocks, _rep("```x")) < BUDGET_MS
    assert llm.parse_json_text('text ```json\n{"a": 1}\n``` more') == {"a": 1}


def test_heading_same_as_old_pattern():
    old = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
    for s in _corpus(["#", "##", " ", "\t", "a", "b c", "\n", "x#"], count=4000):
        m = old.match(s)
        assert segment._heading(s) == (m and (len(m.group(1)), m.group(2))), repr(s)
    # the old lazy (.*?)\s*#*\s*$ was cubic here: 400 spaces took 55 ms, 2,000 about 7 s (one padded brief line)
    assert _fast(segment._heading, "# x" + _rep(" ") + "x") < BUDGET_MS
    assert _fast(segment._heading, "# x" + _rep(" #") + "x") < BUDGET_MS


def test_lexicon_numbers_same_as_old_pattern():
    old = re.compile(r"(?<![\w.])\d{1,3}(?:[,.]\d{3})*(?:[.,]\d+)?(?![\w])|(?<![\w.])\d+(?:\.\d+)?(?![\w])")
    for s in _corpus(["1", "12", "123", "1234", ",", ".", " ", "a", "_"], count=3000):
        assert segment._first_alt(segment._NUM_RE, s) == old.findall(s), repr(s)


def test_lexicon_times_same_as_old_pattern():
    old = re.compile(r"\b(?:[01]?\d|2[0-3])[:.][0-5]\d\b(?:\s*[ap]\.?m\.?)?|\b(?:1[0-2]|[1-9])\s*[ap]\.?m\.?\b", re.I)
    alpha = ["1", "2", "9", "12", "23", "24", ":", ".", "30", "5", " ", "a", "p", "m", "M", "x", "."]
    for s in _corpus(alpha, count=5000):
        assert segment._first_alt(segment._TIME_RE, s) == old.findall(s), repr(s)


def test_lexicon_ranges_same_as_old_pattern():
    old = re.compile(r"\b\d+\s*(?:-|–|—|to)\s*\d+\b|\b\d+\+|[≤≥<>]=?\s*\d+")
    alpha = ["1", "12", " ", "-", "–", "—", "to", "+", "<", ">=", "≤", "=", "x", "a"]
    for s in _corpus(alpha, count=5000):
        assert segment._first_alt(segment._RANGE_RE, s) == old.findall(s), repr(s)
    lex = segment.build_lexicon("Pay 1,234.50 by 17:30 or 5pm; 3-5 days, 10+ or <= 20.")
    assert lex["times"] == ["17:30", "5pm"]
    assert lex["ranges"] == ["3-5", "10+", "<= 20"]
    old_num = r"(?<![\w.])\d{1,3}(?:[,.]\d{3})*(?:[.,]\d+)?(?![\w])|(?<![\w.])\d+(?:\.\d+)?(?![\w])"
    assert lex["numbers"] == segment._uniq(re.findall(old_num, "Pay 1,234.50 by 17:30 or 5pm; 3-5 days, 10+ or <= 20."))


def test_ascii_word_classes_same_as_old_patterns():
    for s in _corpus(["a", "Z", "_", "9", "é", "١", "{", "}", " ", " ", "<f:", ">"], count=3000):
        assert bool(crender._VAR_RE.match(s)) == bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", s)), repr(s)
        assert validate._BRACE_VAR_RE.findall(s) == \
            re.findall(r"\{\{?\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}?\}", s), repr(s)
        assert re.findall(r"<f:(\w+)>", s, re.A) == re.findall(r"<f:([A-Za-z0-9_]+)>", s), repr(s)


# ------------------------------------------------------------------------------------- the text-length guard
def test_sensor_cap_cuts_long_text_at_a_space():
    long = "I can pay " + "really " * 400 + "tomorrow"
    cut = brain._b_cap(long)
    assert len(cut) <= brain._B_MAX_TEXT
    assert long.startswith(cut)
    assert cut.endswith("really")
    assert brain._b_cap("short text") == "short text"
    assert brain._b_cap(None) is None
    assert brain._b_cap(5) == 5
    nospace = "9" * 5000
    assert brain._b_cap(nospace) == nospace[:brain._B_MAX_TEXT]


def test_brain_turn_caps_and_stays_fast_on_huge_text():
    """A 40,000-char adversarial customer turn in every phase: the brain answers within the time budget."""
    from tests.test_brain import run_a
    for unit in (". ", "x-", "1,", " .", "after 1 "):
        huge = _rep(unit, 40000)
        d = run_a([])
        for text in (huge, "Yes, speaking.", huge, "14 March 1988", "4471", huge):
            if d.ended:
                break
            t = time.perf_counter()
            out = d.turn(text)
            assert (time.perf_counter() - t) < 1.0, (unit, text[:20])
            assert out
            assert all(isinstance(x, str) for x in out)
