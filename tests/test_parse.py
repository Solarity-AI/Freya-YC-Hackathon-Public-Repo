"""Tests for runtime/parse.py (agent 1): amounts, dates, times, DOB/years, digits, codes, yes/no.
Corpus drawn from docs/edge-cases/EDGE-CASES.md (AMT-*, DAT-*, IDV-*, OPN-*) and the kit run_cases.py STYLES
(pieces, corrects, talkative, asks_back, in_words). Test data only; runtime code stays generic."""
from datetime import date

import pytest

from runtime import cal as C
from runtime import parse as P

D = date.fromisoformat
CAL_SPEC = {
    "business_weekdays": [0, 1, 2, 3, 4],
    "holidays": ["2026-10-26", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01"],
    "holiday_rules": [], "week_start": 0, "count_from": "after_today", "numeric_order": "DMY",
    "this_next": {"this": "current_week", "next": "following_week"},
}
WED = D("2026-10-14")


def cal_at(today, **over):
    spec = dict(CAL_SPEC)
    spec.update(over)
    return C.prepare(spec, today)


def amt(text, **ctx):
    return P.parse_amount(text, ctx or None)


def cents(text, **ctx):
    r = amt(text, **ctx)
    assert r["kind"] == "amount", (text, r)
    return r["cents"]


def pdate(text, today=WED, **opts):
    return P.parse_date(text, today, cal_at(today), opts or None)


def dd(text, today=WED, **opts):
    r = pdate(text, today, **opts)
    assert r["kind"] == "date", (text, r)
    return r["date"]


# ---------------------------------------------------------------- norm / clauses / words

def test_norm():
    assert P.norm("  Hello’s   WORLD—ok… ") == "hello's world - ok..."
    assert P.norm("50% & more?") == "50 percent and more."
    assert P.norm("6 p.m. sharp") == "6 pm sharp"
    assert P.norm(None) == "" and P.norm(123) == "123"
    assert P.norm("café #1 $5") == "caf 1 5"


@pytest.mark.parametrize("text,exp", [
    ("Friday, sorry, I mean Monday", "monday"),
    ("the 21st, sorry, I mean the 20th", "the 20th"),
    ("two hundred, no wait, three hundred", "three hundred"),
    ("Tuesday, actually make that Wednesday", "wednesday"),
    ("I can pay on Friday", "i can pay on friday"),
    ("Four hundred... or rather four fifty", "four fifty"),
    ("", ""),
])
def test_last_clause(text, exp):
    assert P.last_clause(text) == exp


# ---------------------------------------------------------------- amounts

@pytest.mark.parametrize("text,exp", [
    ("I can do two hundred and fifty dollars", 25000),
    ("I could do seven hundred and fifty dollars and twenty-five cents on Friday", 75025),  # AMT-01
    ("Not all of it, but I can pay seven hundred fifty dollars and twenty five cents on Friday", 75025),
    ("I'll send 450 bucks Friday", 45000),  # AMT-05
    ("$450", 45000), ("450.00 USD", 45000), ("four hundred fifty dollars even", 45000),
    ("four fifty quid", 45000), ("450 euros", 45000),
    ("I'll pay five hundred on Friday, just to be safe", 50000),  # AMT-06
    ("I can do one hundred twenty-six on Friday", 12600),  # AMT-08
    ("I'll pay four hundred twenty on the twentieth", 42000),
    ("Not all of it, but I can pay two hundred on Friday", 20000),  # AMT-09
    ("I can only manage a hundred on Friday", 10000),  # AMT-10
    ("I can do fifty, that's it", 5000),
    ("I can pay two hundred, sorry, I mean three hundred on Friday", 30000),  # AMT-24
    ("I can pay three hundred, sorry, I mean two hundred, on Friday", 20000),  # AMT-60a
    ("I can pay $1,250 on Friday", 125000),  # AMT-44
    ("I can do 1,000 on Friday", 100000),
    ("I can pay two hundred on the twenty-second", 20000),  # AMT-26
    ("on the sixteenth, three hundred", 30000),
    ("fifty on the fifth", 5000),
    ("seven hundred and fifty dollars and five on Friday", 75005),  # AMT-71
    ("six thirty-seven point five", 63750),
    ("seven fifty point oh five", 75005),
    ("750 dollars and 5", 75005),
    ("about 99.5", 9950),
    ("2,125.10", 212510),
    ("twelve dollars fifty", 1250),
    ("a hundred and fifty", 15000),
    ("one fifty", 15000),
    ("two twenty on the card", 22000),
    ("four thousand", 400000),
    ("4 grand", 400000),
    ("2k", 200000),
    ("two thousand, one hundred and twenty-five", 212500),
    ("I can pay four hundred and sixty three fifty one on Friday", 46351),  # AMT-03 joined
    ("twenty five cents", 25),
    ("Yes, three hundred and fifty on Friday, that's right", 35000),  # AMT-46
    ("Hmm, actually make it five hundred", 50000),  # AMT-22
    ("Wait, can we do just a hundred instead?", 10000),  # AMT-23
    ("No, but I can do seven hundred on Friday", 70000),  # AMT-36
    ("I can pay four hundred on the 6th of November", 40000),  # AMT-37
    ("That's wrong, I only owe three hundred. I'll pay the three hundred on Friday.", 30000),  # AMT-64
    ("I could pay four hundred and sixty-three... fifty-one. On Friday.", 46351),
])
def test_amount_values(text, exp):
    assert cents(text) == exp


@pytest.mark.parametrize("text", [
    "I could probably pay around three hundred on Friday", "about 99.5", "maybe two hundred", "two hundred-ish",
    "roughly five hundred", "something like 300"])
def test_amount_hedged(text):
    r = amt(text)
    assert r["kind"] == "amount" and r["hedged"] is True


def test_amount_not_hedged():
    assert amt("I can pay three hundred on Friday")["hedged"] is False


def test_amount_colloquial_ranking():
    # AMT-02: 'twelve fifty' -> known figure first, then range, then the larger reading
    assert cents("I can pay twelve fifty on Friday") == 125000
    assert cents("twelve fifty", known=[125000], lo=10000, hi=200000) == 125000
    assert cents("twelve fifty", known=[1250]) == 1250
    assert cents("twelve fifty", lo=500, hi=5000) == 1250
    assert cents("six thirty-seven fifty") == 63750
    assert cents("twenty-one twenty-five") == 212500
    assert cents("seven oh five") == 70500


def test_amount_snaps_to_stated_figure():
    # AMT-07: customer drops the cents of a figure the agent stated
    r = amt("Fine, I'll pay the twenty-one twenty-five on Friday", known=[212510, 63750])
    assert r["cents"] == 212510 and r.get("snapped") is True
    r = amt("OK, six thirty-seven then", known=[212510, 63750])
    assert r["cents"] == 63750 and r.get("snapped") is True
    assert amt("six hundred thirty-seven fifty", known=[63750])["cents"] == 63750
    assert "snapped" not in amt("four hundred", known=[42000])


def test_amount_relative_and_named():
    assert cents("I could pay half of it on Friday", full=78000) == 39000  # AMT-13
    assert cents("half of it", full=212510) == 106255
    assert cents("a quarter of it", full=42000) == 10500
    assert cents("I can do thirty percent on Friday", full=212510) == 63753  # AMT-14
    assert cents("ten percent", full=212510) == 21251
    assert cents("I can do half of that", ref=42000, full=99999) == 21000  # AMT-63
    assert amt("I could pay half of it on Friday")["kind"] == "none"  # no base -> no figure invented
    r = amt("I'll pay just the minimum on Friday", floor=6600, full=22000)  # AMT-35
    assert r["cents"] == 6600 and r["named"] == "floor"
    assert cents("I'll pay all of it on Friday", floor=6600, full=22000) == 22000
    assert cents("I'll pay my instalment", floor=26000, full=78000) == 26000
    assert cents("I'll pay the basic charge", floor=500, full=900, floor_words=[r"basic charge"]) == 500
    assert amt("not all of it", floor=6600, full=22000)["kind"] == "none"
    assert amt("what's the minimum?", floor=6600, full=22000)["kind"] == "none"
    assert amt("half past six", full=10000)["kind"] == "none"


def test_amount_named_reference_with_wrong_figure():
    # AMT-62: the named floor wins (the agent states the real figure); the spoken figure is kept in alts
    r = amt("I'll just pay the minimum, the six hundred, on Friday", floor=63750, full=212510)
    assert r["kind"] == "amount" and r["cents"] == 63750 and r["named"] == "floor" and r["alts"] == [60000]
    assert amt("I'll just pay the minimum, the six hundred, on Friday")["cents"] == 60000  # no floor known


@pytest.mark.parametrize("text", [
    "nothing at all", "Zero. I can't pay anything right now.", "zero", "I can't pay anything", "not a penny",
    "none", "I have no money"])
def test_amount_zero(text):
    assert amt(text)["kind"] == "zero"


@pytest.mark.parametrize("text", [
    "my wedding is on the 30th",  # decoy event date
    "I can't pay anything until my salary comes in",  # AMT-59: vague date, never zero
    "Nothing until payday",
    "The one ending nineteen-oh-three? Twelve days, really? Fine, I'll pay it Friday after five.",  # AMT-69
    "I already paid the minimum, the 126, this morning in the app.",  # AMT-65 past tense
    "I lost my job on the 3rd and my rent went out on the 1st",
    "It took me forty-five minutes",
    "at 5 pm", "call me at five", "in 2 weeks", "the 23rd of October", "October 20", "on the 20th",
    "my card number is 4111 1111 1111 1111", "4111111111111111", "I've been with you for 12 years",
    "First of all, I can't do today. Give me a second.", "I'll pay the whole thing in one go",
    "two zero two six", "", None, "hello", "the one on the left",
    "I could do three hundred, actually no, I can't",  # AMT-60b retraction
])
def test_amount_none(text):
    assert amt(text)["kind"] == "none", text


def test_amount_decoys_in_talkative_turn():
    t = ("Traffic took me forty-five minutes, my rent just went up by two hundred, my cousin's wedding is on the 30th... "
         "anyway, I can do one fifty on Friday.")
    assert cents(t) == 15000  # AMT-25
    assert cents("I paid 200 last week and I can pay 300 on Friday") == 30000
    assert cents("My cousin's wedding is on the 30th, but yes, I can do two hundred") == 20000


def test_amount_drop_list():
    assert amt("twelve", drop=[12])["kind"] == "none"
    assert cents("twelve dollars", drop=[12]) == 1200
    assert cents("I can pay 100, it's 12 days late", drop=[12]) == 10000


def test_amount_alternatives():
    r = amt("I could do two hundred, maybe two-fifty, on Friday")  # AMT-61
    assert r["cents"] == 20000 and r["alts"] == [25000]
    r = amt("I can't do 400 but I can do 200")
    assert r["cents"] == 20000


def test_amount_incomplete_and_join():
    r = amt("I could pay four hundred and sixty-three...")  # AMT-03 pieces
    assert r["kind"] == "incomplete" and "sixty" in r["frag"] and not r["frag"].endswith(".")
    assert cents("...fifty-one. On Friday.", frag=r["frag"]) == 46351
    r2 = amt("I can pay four hundred and...")
    assert r2["kind"] == "incomplete"
    assert cents("twenty", frag=r2["frag"]) == 42000
    r3 = amt("four hundred and sixty-")
    assert r3["kind"] == "incomplete"
    assert cents("three", frag=r3["frag"]) == 46300
    assert amt("I can pay four hundred on Friday...")["kind"] == "amount"


@pytest.mark.parametrize("bad", [None, 5, [], {}, "\u0000\u0001", "$$$", "..."])
def test_amount_total_on_bad_input(bad):
    assert amt(bad)["kind"] in ("none", "zero")
    assert P.parse_amount("200", "not a dict")["cents"] == 20000
    assert P.parse_amount("200", {"known": ["x", None], "lo": None})["cents"] == 20000


# ---------------------------------------------------------------- dates

@pytest.mark.parametrize("text,today,exp", [
    ("this Friday", "2026-01-07", "2026-01-09"),
    ("next Friday", "2026-01-07", "2026-01-16"),
    ("the 20th", "2026-01-07", "2026-01-20"),
    ("the 5th", "2026-01-07", "2026-02-05"),
    ("Friday, sorry, I mean Monday", "2026-01-07", "2026-01-12"),
    ("Not today... I can do it tomorrow.", "2026-11-10", "2026-11-11"),  # DAT-01 (holiday handled by caller)
    ("Not today. Can I do Monday the second of November?", "2026-10-14", "2026-11-02"),  # DAT-04
    ("Tuesday the 3rd", "2026-10-14", "2026-11-03"),
    ("I can do Friday the 20th.", "2026-11-10", "2026-11-20"),  # DAT-05
    ("Next Friday, the 23rd.", "2026-10-14", "2026-10-23"),  # DAT-06
    ("I can pay next Monday.", "2026-10-21", "2026-10-26"),  # DAT-11a
    ("Tomorrow.", "2026-11-10", "2026-11-11"),
    ("Can't today, tomorrow.", "2026-10-23", "2026-10-24"),  # DAT-12
    ("Monday the 26th", "2026-10-14", "2026-10-26"),  # DAT-13
    ("Saturday the 24th", "2026-10-14", "2026-10-24"),
    ("Saturday the 31st.", "2026-10-21", "2026-10-31"),  # DAT-14
    ("I can pay on the 26th.", "2026-10-14", "2026-10-26"),  # DAT-15
    ("the 26th", "2026-10-27", "2026-11-26"),
    ("I get paid on the 5th, I'll pay then.", "2026-10-14", "2026-11-05"),  # DAT-16
    ("Monday.", "2026-10-14", "2026-10-19"),  # DAT-17a
    ("I can do Friday.", "2026-10-16", "2026-10-23"),  # DAT-17b bare weekday strictly after today
    ("the 4th", "2026-12-28", "2027-01-04"),  # DAT-19
    ("New Year's Day", "2026-12-28", "2027-01-01"),
    ("the 8th of January", "2026-12-28", "2027-01-08"),
    ("Christmas Eve", "2026-12-18", "2026-12-24"),
    ("The 31st.", "2026-10-14", "2026-10-31"),  # DAT-21
    ("My salary comes on the 25th, I'll pay then.", "2026-10-14", "2026-10-25"),  # DAT-22
    ("a week from today", "2026-10-14", "2026-10-21"),  # DAT-24
    ("in ten days", "2026-10-14", "2026-10-24"),
    ("Crazy month, my cousin's wedding is on the 30th... but yes, Friday is fine.", "2026-10-14", "2026-10-16"),  # DAT-25
    ("First of all, I can't do today. Give me a second... I can do Friday.", "2026-10-14", "2026-10-16"),  # DAT-27
    ("I'll pay the whole thing in one go, the twenty-second.", "2026-10-14", "2026-10-22"),
    ("Friday's no good, I'm away till Tuesday. Could I do Wednesday?", "2026-10-14", "2026-10-21"),  # DAT-28
    ("Tuesday the 27th, sorry, I mean Monday the 26th.", "2026-10-14", "2026-10-26"),  # DAT-29
    ("the 21st, sorry, I mean the 20th", "2026-10-14", "2026-10-20"),
    ("Friday, sorry, tomorrow", "2026-10-14", "2026-10-15"),
    ("Actually can we make it Saturday?", "2026-10-14", "2026-10-17"),  # DAT-30
    ("the twenty-first of October", "2026-10-14", "2026-10-21"),  # DAT-32 in_words
    ("the thirty-first", "2026-10-14", "2026-10-31"),
    ("November the second", "2026-10-14", "2026-11-02"),
    ("two hundred on the twenty-second", "2026-10-14", "2026-10-22"),
    ("Thursday the 23rd.", "2026-10-14", "2026-10-23"),  # DAT-33 number wins
    ("Yes, I'll do it in the app tonight.", "2026-10-14", "2026-10-14"),  # DAT-34
    ("She's back tomorrow, call around three.", "2026-10-16", "2026-10-17"),
    ("next Friday", "2026-10-24", "2026-10-30"),  # DAT-49a
    ("next Monday", "2026-10-25", "2026-10-26"),
    ("Can I do it on the sixteenth?", "2026-10-16", "2026-10-16"),  # DAT-51 bare number = today
    ("Friday the 16th.", "2026-10-16", "2026-10-16"),
    ("maybe the 6th of November when my redundancy money comes", "2026-10-14", "2026-11-06"),  # DAT-52
    ("Not the 23rd, I'm away. Saturday the 17th?", "2026-10-14", "2026-10-17"),  # DAT-53
    ("I can do the card today, and the loan on the 30th.", "2026-10-14", "2026-10-14"),
    ("the last Friday of the month", "2026-10-14", "2026-10-30"),  # DAT-58
    ("the last working day of the month", "2026-10-14", "2026-10-30"),
    ("the first Monday in November", "2026-10-14", "2026-11-02"),
    ("I'll have it paid by Friday.", "2026-10-14", "2026-10-16"),  # DAT-59
    ("Friday at the latest.", "2026-10-14", "2026-10-16"),
    ("Straight after this call", "2026-10-14", "2026-10-14"),  # DAT-60
    ("later this afternoon", "2026-10-14", "2026-10-14"),
    ("First thing tomorrow morning", "2026-10-14", "2026-10-15"),
    ("Friday week.", "2026-10-14", "2026-10-23"),  # DAT-71
    ("A fortnight today.", "2026-10-14", "2026-10-28"),
    ("A week on Monday.", "2026-10-14", "2026-10-26"),
    ("on the 30/10", "2026-10-14", "2026-10-30"),  # DAT-72
    ("20/10/2026", "2026-10-14", "2026-10-20"),
    ("20.10.2026", "2026-10-14", "2026-10-20"),
    ("2026-10-20", "2026-10-14", "2026-10-20"),
    ("two hundred on the twenty-third of October, two zero two six", "2026-10-14", "2026-10-23"),
    ("the 23rd of October 2026", "2026-10-14", "2026-10-23"),
    ("October 23rd", "2026-10-14", "2026-10-23"),
    ("Oct 23", "2026-10-14", "2026-10-23"),
    ("the day after tomorrow", "2026-10-14", "2026-10-16"),
    ("in 2 weeks", "2026-10-14", "2026-10-28"),
    ("Friday next week", "2026-10-14", "2026-10-23"),
    ("this coming Monday", "2026-10-14", "2026-10-19"),
    ("Monday after next", "2026-10-14", "2026-10-26"),
    ("I can't pay until Friday", "2026-10-14", "2026-10-16"),
    ("Boxing Day?", "2026-12-21", "2026-12-26"),
    ("New Year's Eve.", "2026-12-21", "2026-12-31"),
])
def test_date_exact(text, today, exp):
    assert dd(text, D(today)) == exp


def test_date_bare_weekday_option():
    assert dd("I can do Friday.", D("2026-10-16"), bare_today=True) == "2026-10-16"
    assert dd("Wednesday", WED) == "2026-10-21"
    assert dd("Wednesday", WED, bare_today=True) == "2026-10-14"


@pytest.mark.parametrize("text,today,exp", [
    ("I can pay this Monday", "2026-10-14", "2026-10-12"),  # DAT-18
    ("on the 12th of October", "2026-10-14", "2026-10-12"),
    ("this Friday", "2026-10-24", "2026-10-23"),  # DAT-49b
    ("yesterday", "2026-10-14", "2026-10-13"),
    ("last Friday", "2026-10-14", "2026-10-09"),
    ("12/10/2026", "2026-10-14", "2026-10-12"),
])
def test_date_past(text, today, exp):
    r = pdate(text, D(today))
    assert r == {"kind": "past", "date": exp}


@pytest.mark.parametrize("text,what", [
    ("end of the month", "end_of_month"),  # DAT-20
    ("I don't know, just end of the month.", "end_of_month"),
    ("End of the month... or the beginning of next month.", "end_of_month"),  # DAT-44
    ("next week", "next_week"),
    ("sometime next week", "next_week"),
    ("end of the week", "this_week"),
    ("I can sort it at the weekend.", "weekend"),  # DAT-23
    ("early November", "next_month"),
    ("beginning of next month", "next_month"),
    ("when my salary comes", "payday"),
    ("on payday", "payday"),
    ("I can't pay anything until my salary comes in", "payday"),  # AMT-59
    ("As soon as I can", "later"),  # DAT-60
    ("ASAP", "later"),
    ("in a couple of weeks", "later"),  # DAT-24c
    ("in a few days", "later"),
    ("later", "later"),
    ("Sometime before the 23rd.", "before"),  # DAT-59c
    ("mid month", "mid_month"),
])
def test_date_vague(text, what):
    assert pdate(text) == {"kind": "vague", "what": what}


def test_date_alternatives():
    r = pdate("Thursday or Friday, I'm not sure which.")  # DAT-61
    assert r["kind"] == "date" and r["date"] == "2026-10-15" and r["alts"] == ["2026-10-16"]


def test_date_incomplete_and_join():
    r = pdate("Friday the...")  # DAT-31 pieces
    assert r["kind"] == "incomplete"
    assert dd("...twenty-third.", WED, frag=r["frag"]) == "2026-10-23"
    r = pdate("The twenty...")
    assert r["kind"] == "incomplete"
    assert dd("...seventh", WED, frag=r["frag"]) == "2026-10-27"
    r = pdate("on the -")
    assert r["kind"] == "incomplete"


def test_date_bare_number_option():
    assert pdate("Thirty.")["kind"] == "none"
    assert dd("Thirty.", WED, bare_number=True) == "2026-10-30"  # DAT-72
    assert dd("Erm, twenty-seven?", WED, bare_number=True) == "2026-10-27"


@pytest.mark.parametrize("text", [
    "I lost my job on the 3rd and my rent went out on the 1st, I can't pay.",  # DAT-26
    "I paid it on Monday.", "my wedding is on the 30th", "Not today.", "no", "", None, "hello there",
    "I can pay two hundred", "First of all, give me a second", "Friday's no good",
    "I'm away till Tuesday", "two hundred dollars", "my birthday is on the 20th",
])
def test_date_none(text):
    assert pdate(text)["kind"] == "none", text


@pytest.mark.parametrize("bad", [None, 5, [], "\u0000", "the 45th", "the 0th", "31/02/2026", "99/99"])
def test_date_total_on_bad_input(bad):
    assert pdate(bad)["kind"] in ("none", "vague", "date", "past")


def test_date_bad_today_and_cal():
    assert P.parse_date("Friday", None, None) == {"kind": "none"}
    assert P.parse_date("Friday", WED, None)["date"] == "2026-10-16"
    assert P.parse_date("Friday", WED, "junk")["date"] == "2026-10-16"


def test_date_numeric_order():
    mdy = C.prepare(dict(CAL_SPEC, numeric_order="MDY"), WED)
    assert P.parse_date("10/20/2026", WED, mdy)["date"] == "2026-10-20"
    assert P.parse_date("20/10/2026", WED, mdy)["date"] == "2026-10-20"  # invalid in MDY -> swapped reading
    assert dd("05/11", WED) == "2026-11-05"
    assert P.parse_date("05/11", WED, mdy)["date"] == "2027-05-11"


def test_date_this_next_rules():
    cal = C.prepare(dict(CAL_SPEC, this_next={"this": "current_week", "next": "first_after_today"}), WED)
    assert P.parse_date("next Friday", WED, cal)["date"] == "2026-10-16"  # DAT-68


# ---------------------------------------------------------------- times

@pytest.mark.parametrize("text,now,exp", [
    ("around half past six", None, [390, 1110]),
    ("She gets home at seven.", None, [420, 1140]),  # DAT-37a
    ("Tomorrow at ten.", None, [600, 1320]),
    ("Half past seven tonight.", None, [1170]),
    ("Call back at eleven today.", None, [660, 1380]),
    ("In about an hour.", 660, [720]),
    ("in half an hour", 660, [690]),
    ("in 90 minutes", 660, [750]),
    ("in two hours", 660, [780]),
    ("an hour and a half", 660, None),
    ("Monday at three then.", None, [180, 900]),
    ("Two o'clock then.", None, [120, 840]),
    ("half ten tomorrow", None, [630, 1350]),  # DAT-71d
    ("quarter to five", None, [285, 1005]),
    ("quarter past five", None, [315, 1035]),
    ("twenty past four", None, [260, 980]),
    ("6.30 pm", None, [1110]),
    ("18:30", None, [1110]),
    ("at 6:30", None, [390, 1110]),
    ("noon", None, [720]),
    ("Try her at noon.", None, [720]),
    ("midnight", None, [0]),
    ("six thirty", None, [390, 1110]),
    ("at six fifteen", None, [375, 1095]),
    ("around eleven", None, [660, 1380]),
    ("Try at four, this afternoon", None, [960]),
    ("ten in the morning", None, None),
    ("at 10 am", None, [600]),
    ("2pm", None, [840]),
    ("seven", None, [420, 1140]),
    ("Around eleven, sorry, I mean twelve", None, [720]),
    ("five-ish", None, [300, 1020]),
    ("at 12", None, [720]),
    ("at 15", None, [900]),
    ("Monday at noon then.", None, [720]),
])
def test_time_exact(text, now, exp):
    r = P.parse_time(text, now)
    if exp is None:
        assert r["kind"] in ("exact", "part", "none")
        return
    assert r["kind"] == "exact", (text, r)
    assert r["alts"] == exp and r["min"] == exp[0]


def test_time_ten_in_the_morning():
    r = P.parse_time("at ten in the morning")
    assert r["kind"] == "exact" and r["alts"] == [600]


def test_time_relative_past_midnight():
    r = P.parse_time("in an hour", 1410)
    assert r["kind"] == "exact" and r["min"] == 30 and r["day_offset"] == 1
    assert P.parse_time("in an hour")["kind"] != "exact"  # no now -> no relative time


@pytest.mark.parametrize("text,lo,hi", [
    ("between two and four", 840, 960),
    ("from 10 to 12", 600, 720),
    ("between 9am and 11am", 540, 660),
])
def test_time_range(text, lo, hi):
    assert P.parse_time(text) == {"kind": "range", "lo": lo, "hi": hi}


@pytest.mark.parametrize("text,lo", [("any time after 2pm", 840), ("after three", 900), ("only after seven tonight", 1140)])
def test_time_after_is_exclusive_range(text, lo):
    assert P.parse_time(text) == {"kind": "range", "lo": lo, "hi": 1439, "lo_excl": True}


def test_time_before_range_uses_now():
    assert P.parse_time("before five", 660) == {"kind": "range", "lo": 660, "hi": 1020}


@pytest.mark.parametrize("text,kind", [
    ("after lunch", "vague"), ("sometime after lunch", "vague"), ("later", "vague"), ("any time", "vague"),
    ("when she gets home", "vague"), ("whenever", "vague"), ("lunchtime", "vague"),
    ("Try her tomorrow morning", "part"), ("this evening", "part"), ("in the afternoon", "part"),
    ("tonight", "part"), ("hello", "none"), ("", "none"), (None, "none"), ("the 26th", "none"),
    ("three hundred dollars", "none"), ("for 2 days", "none"),
])
def test_time_kinds(text, kind):
    assert P.parse_time(text)["kind"] == kind


def test_time_part_value():
    assert P.parse_time("Try her tomorrow morning") == {"kind": "part", "part": "morning"}
    assert P.parse_time("tonight") == {"kind": "part", "part": "evening"}


def test_day_and_time():
    t = D("2026-10-14")
    cal = cal_at(t)
    r = P.parse_day_and_time("Tomorrow at ten.", t, 660, cal)
    assert r["date"] == "2026-10-15" and r["date_kind"] == "date" and r["time"]["alts"] == [600, 1320]
    r = P.parse_day_and_time("She gets home at seven.", t, 660, cal)
    assert r["date"] == "" and r["date_kind"] == "none" and r["time"]["min"] == 420
    r = P.parse_day_and_time("in an hour", t, 1410, cal)
    assert r["date"] == "2026-10-15" and r["time"]["min"] == 30
    r = P.parse_day_and_time("Monday at three then.", D("2026-10-16"), 900, cal_at(D("2026-10-16")))
    assert r["date"] == "2026-10-19" and r["time"]["alts"] == [180, 900]
    r = P.parse_day_and_time("Try her the day after tomorrow, around noon.", D("2026-11-10"), 900, cal_at(D("2026-11-10")))
    assert r["date"] == "2026-11-12" and r["time"]["min"] == 720
    r = P.parse_day_and_time(None, None, None, None)
    assert r == {"date": "", "date_kind": "none", "time": {"kind": "none"}}


# ---------------------------------------------------------------- dates of birth / years

@pytest.mark.parametrize("text,order,exp", [
    ("the third of May nineteen seventy-nine", "DMY", (1979, 5, 3, True)),
    ("03/05/1979", "DMY", (1979, 5, 3, False)),
    ("03/05/1979", "MDY", (1979, 3, 5, False)),
    ("14 March 1988", "DMY", (1988, 3, 14, True)),
    ("the fourteenth of March, one nine eight eight", "DMY", (1988, 3, 14, True)),  # IDV-09
    ("the fourteenth of March, nineteen hundred and eighty-eight", "DMY", (1988, 3, 14, True)),
    ("the first of May, two thousand and five", "DMY", (2005, 5, 1, True)),
    ("fifth of May twenty oh three", "DMY", (2003, 5, 5, True)),
    ("fourteen, oh three, eighty-eight", "DMY", (1988, 3, 14, False)),  # IDV-10
    ("14/3/88", "DMY", (1988, 3, 14, False)),
    ("one four zero three eight eight", "DMY", (1988, 3, 14, False)),
    ("five, twelve, oh five", "DMY", (2005, 12, 5, False)),
    ("March fourteenth, nineteen eighty-eight", "DMY", (1988, 3, 14, True)),  # IDV-14
    ("March the 14th, '88", "DMY", (1988, 3, 14, True)),
    ("fourteen March eighty-eight", "DMY", (1988, 3, 14, True)),
    ("the fourteenth of the third, eighty-eight", "DMY", (1988, 3, 14, False)),  # IDV-15
    ("fourteenth, third month, 1988", "DMY", (1988, 3, 14, False)),
    ("The twenty-first of June, sorry, July, nineteen ninety-two", "DMY", (1992, 7, 21, True)),  # IDV-16
    ("six, three, nineteen eighty-seven", "DMY", (1987, 3, 6, False)),  # IDV-12 read D-M-Y
    ("six, three, eighty-seven", "MDY", (1987, 6, 3, False)),  # IDV-56
    ("June, the third of June, 1987", "DMY", (1987, 6, 3, True)),
    ("nineteen eighty-eight, oh three, fourteen", "DMY", (1988, 3, 14, False)),  # IDV-57
    ("eighty-eight, three, fourteen", "DMY", (1988, 3, 14, False)),
    ("88/03/14", "DMY", (1988, 3, 14, False)),
    ("1988-03-14", "DMY", (1988, 3, 14, False)),
    ("Christmas Day, nineteen seventy-five", "DMY", (1975, 12, 25, True)),  # IDV-84
    ("New Year's Day 1990", "DMY", (1990, 1, 1, True)),
    ("nineteen eighty-eight March fourteen", "DMY", (1988, 3, 14, True)),
    ("It's the 2nd of November 1979", "DMY", (1979, 11, 2, True)),
    ("14031988", "DMY", (1988, 3, 14, False)),
    ("I'm thirty-eight, my birthday is the fourteenth of March 1988", "DMY", (1988, 3, 14, True)),
])
def test_dob_complete(text, order, exp):
    r = P.parse_dob(text, order, WED)
    assert r["kind"] == "date", (text, r)
    got = (r["y"], r["m"], r["d"], r["month_word"])
    assert got == exp


@pytest.mark.parametrize("text,have", [
    ("May the third", {"m": 5, "d": 3}),
    ("Nineteen eighty-eight...", {"y": 1988}),  # IDV-01 year first, day/month to follow
    ("The fourteenth of March, nineteen eighty...", {"d": 14, "m": 3}),  # IDV-02
    ("The fourteenth of March, nineteen...", {"d": 14, "m": 3}),  # IDV-58
    ("The first of May, two thousand...", {"d": 1, "m": 5}),
    ("the fourteenth of March", {"d": 14, "m": 3}),
    ("I'm thirty-eight, my birthday's the fourteenth of March.", {"d": 14, "m": 3}),  # IDV-84 age is not a year
    ("fourteen, three", {"d": 14, "m": 3}),
    ("14/3", {"d": 14, "m": 3}),
    ("June", {"m": 6}),
])
def test_dob_incomplete(text, have):
    r = P.parse_dob(text, "DMY", WED)
    assert r == {"kind": "incomplete", "have": have}


def test_dob_pieces_join():
    a = P.parse_dob("Nineteen eighty-eight...", "DMY", WED)
    assert a["kind"] == "incomplete"
    r = P.parse_dob("Nineteen eighty-eight... the fourteenth of March.", "DMY", WED)
    assert (r["kind"], r.get("y"), r.get("m"), r.get("d")) == ("date", 1988, 3, 14)
    r = P.parse_dob("The fourteenth of March, nineteen eighty... eight.", "DMY", WED)
    assert (r["y"], r["m"], r["d"]) == (1988, 3, 14)


@pytest.mark.parametrize("text", [
    "three, fourteen, eighty-eight",  # IDV-11 impossible D-M-Y
    "31/02/1990", "the thirtieth of February 1990", "45/01/1990"])
def test_dob_invalid(text):
    assert P.parse_dob(text, "DMY", WED) == {"kind": "invalid"}


@pytest.mark.parametrize("text", ["", None, "I'm not telling you", "no", "why do you need that?", [], "first of all"])
def test_dob_none(text):
    assert P.parse_dob(text, "DMY", WED) == {"kind": "none"}


@pytest.mark.parametrize("text,today,exp", [
    ("nineteen eighty-eight", None, 1988), ("one nine eight eight", None, 1988), ("1988", None, 1988),
    ("eighty-eight", WED, 1988), ("eighty-eight", None, 1988), ("oh five", WED, 2005),
    ("two thousand and nine", None, 2009), ("fourteenth of March 1988", None, 1988), ("twenty oh three", None, 2003),
    ("I was born in 1975", None, 1975), ("hello", None, None), ("", None, None), (None, None, None),
    ("I'm thirty-eight", WED, None), ("nineteen...", None, None),
])
def test_parse_year(text, today, exp):
    assert P.parse_year(text, today) == exp


# ---------------------------------------------------------------- digits / codes

@pytest.mark.parametrize("text,exp", [
    ("oh three five eight", "0358"), ("zero three five eight", "0358"), ("nought three five eight", "0358"),
    ("O three five eight", "0358"), ("it's oh three five eight", "0358"),
    ("double two seven nine", "2279"), ("double four seven one", "4471"), ("two two double eight", "2288"),
    ("twenty-two double eight", "2288"), ("triple eight two", "8882"),
    ("forty-four seventy-one", "4471"), ("sixty-six oh four", "6604"), ("forty-four ten", "4410"),
    ("four thousand four hundred and seventy-one", "4471"), ("twenty-two, eighty-eight", "2288"),
    ("for four seven one", "4471"), ("to to ate ate", "2288"), ("4-4-7-1", "4471"), ("44 71", "4471"),
    ("four forty-seven one", "4471"), ("six six thirty", "6630"), ("4471", "4471"), ("0358", "0358"),
    ("It's oh seven seven double oh, nine double eight, four four seven one.", "077009884471"),  # IDV-08
    ("four four oh one, no sorry, four four one oh", "4410"),  # IDV-16
    ("zero, three, fifty-eight", "0358"),
    ("my number ends in 4471", "4471"),
    ("nineteen-oh-three", "1903"),
    ("", ""), (None, ""), ("I don't know", ""), ("hello there", ""), ("the third", ""),
])
def test_parse_digits(text, exp):
    assert P.parse_digits(text) == exp


@pytest.mark.parametrize("text,exp", [
    ("S W one A, one A A", "SW1A1AA"), ("sierra whiskey one alpha, one alpha alpha", "SW1A1AA"),
    ("SW1A 1AA", "SW1A1AA"), ("E one, oh A X", "E10AX"), ("S C one two three four five six", "SC123456"),
    ("zero eight one two three four five six", "08123456"), ("my postcode is SW1A 1AA", "SW1A1AA"),
    ("double A one", "AA1"), ("", ""), (None, ""), ("I'm not sure", ""),
])
def test_parse_alnum(text, exp):
    assert P.parse_alnum(text) == exp


# ---------------------------------------------------------------- yes / no and turn shapes

@pytest.mark.parametrize("text,yn,flags", [
    ("Yes, but I can't do it today", "yes", {"cant": True}),
    ("I suppose so, maybe", "yes", {"hedge": True}),
    ("Yes, I confirm", "yes", {}), ("Yeah", "yes", {}), ("Sure.", "yes", {}), ("OK", "yes", {}),
    ("That's right", "yes", {}), ("No problem", "yes", {}), ("Not a problem at all", "yes", {}),
    ("Go ahead", "yes", {}), ("Fine", "yes", {}), ("Sounds good", "yes", {}), ("I do", "yes", {}),
    ("Yes, I'll try", "yes", {"hedge": True}), ("Yes if I get paid", "yes", {"cond": True}),
    ("Yes, actually Saturday's better", "yes", {"corr": True}),
    ("Yes, that's... oh hang on, Friday's no good, make it Thursday.", "yes", {"corr": True}),
    ("No.", "no", {}), ("Nope", "no", {}), ("Not today", "no", {}), ("I can't", "no", {"cant": True}),
    ("I can't do it", "no", {"cant": True}), ("Of course not", "no", {}), ("Absolutely not", "no", {}),
    ("No, I can't afford that", "no", {"cant": True}), ("Not really", "no", {}),
    ("I don't know", "", {"hedge": True}), ("Hmm", "", {}), ("", "", {}), (None, "", {}),
    ("Why do you need that?", "", {"question": True}), ("Is this a scam?", "", {"question": True}),
    ("Should be fine", "yes", {"hedge": True}), ("Probably", "", {"hedge": True}),
])
def test_yes_no(text, yn, flags):
    r = P.yes_no(text)
    assert set(r) == {"yn", "hedge", "cond", "corr", "cant", "question"}
    assert r["yn"] == yn, (text, r)
    for k, v in flags.items():
        assert r[k] is v, (text, k, r)


@pytest.mark.parametrize("text,exp", [
    ("Hello?", True), ("hi", True), ("Hello", True), ("Yes?", True), ("Yeah?", True), ("Go ahead", True),
    ("Who's this?", True), ("Hello, who is calling?", True), ("Yes? Who is this?", True), ("Good morning!", True),
    ("Yes.", False), ("Yes, speaking", False), ("Speaking.", False), ("This is Jordan", False),
    ("Hello, yes, it's me", False), ("No", False), ("", False), (None, False), ("Is this about my account?", False),
])
def test_is_greeting_only(text, exp):
    assert P.is_greeting_only(text) is exp


@pytest.mark.parametrize("text,exp", [
    ("Who is this?", True), ("why do you need that", True), ("Can I pay Friday", True), ("Is this a scam", True),
    ("Fine.", False), ("I can do Friday", False), ("Do it", False), ("", False), (None, False),
    ("What's the latest I can pay this by", True), ("how much is that altogether", True),
])
def test_is_question(text, exp):
    assert P.is_question(text) is exp


@pytest.mark.parametrize("text,exp", [
    ("I already paid it.", True), ("I paid it on Monday.", True), ("I've paid that this morning", True),
    ("I sent it yesterday", True), ("It was paid last week", True), ("I made the payment on Friday", True),
    ("I'll pay in the app", False), ("I'll pay tonight", False), ("I get paid on Friday", False),
    ("I haven't paid yet", False), ("I didn't pay", False), ("Have I paid?", False),
    ("I'm going to pay tomorrow", False), ("I will have paid it by Friday", False), ("", False), (None, False),
    ("I paid it, I'll send proof tomorrow", False),
])
def test_has_completed_payment(text, exp):
    assert P.has_completed_payment(text) is exp


def test_match_any():
    assert P.match_any([r"\brobot\b", "("], "Are you a ROBOT?")
    assert not P.match_any(["(", "[a-"], "anything")
    assert P.match_any(r"scam", "is this a scam")
    assert not P.match_any([], "x")
    assert not P.match_any(None, "x")
    assert not P.match_any(["x"], None)





# ---------------------------------------------------------------- style corpus (run_cases STYLES)

STYLE_AMOUNTS = [
    # (style, text, ctx, expected kind, expected cents)
    ("pieces", "I could pay four hundred and sixty-three...", {}, "incomplete", None),
    ("pieces", "Two hundred and...", {}, "incomplete", None),
    ("corrects", "the 21st, sorry, I mean the 20th, two hundred, no wait, two fifty", {}, "amount", 25000),
    ("corrects", "Three hundred, sorry, three hundred and fifty", {}, "amount", 35000),
    ("talkative", "Busy day at work, the traffic took me an hour. Anyway I can do four hundred on Friday.", {}, "amount", 40000),
    ("talkative", "My cousin's wedding is on the 30th, can you believe it? Two hundred on Friday works.", {}, "amount", 20000),
    ("asks_back", "Why do you need that? Fine, three hundred on Friday.", {}, "amount", 30000),
    ("asks_back", "Which account is this about?", {}, "none", None),
    ("in_words", "four hundred and fifty-five", {}, "amount", 45500),
    ("in_words", "two thousand one hundred and twenty-five dollars and ten cents", {}, "amount", 212510),
    ("in_words", "six hundred and thirty-seven dollars and fifty cents on the twenty-second of October", {}, "amount", 63750),
]


@pytest.mark.parametrize("style,text,ctx,kind,exp", STYLE_AMOUNTS)
def test_style_amounts(style, text, ctx, kind, exp):
    r = P.parse_amount(text, ctx)
    assert r["kind"] == kind, (style, text, r)
    if exp is not None:
        assert r["cents"] == exp


STYLE_DATES = [
    ("pieces", "Friday the...", "incomplete", None),
    ("corrects", "the 21st, sorry, I mean the 20th", "date", "2026-10-20"),
    ("talkative", "Work has been mad, my cousin's wedding is on the 30th, but I can pay on Friday.", "date", "2026-10-16"),
    ("asks_back", "Why does that matter? Monday then.", "date", "2026-10-19"),
    ("in_words", "the twenty-second of October", "date", "2026-10-22"),
    ("in_words", "on the twenty-third of October, two zero two six", "date", "2026-10-23"),
    ("in_words", "the second of November", "date", "2026-11-02"),
]


@pytest.mark.parametrize("style,text,kind,exp", STYLE_DATES)
def test_style_dates(style, text, kind, exp):
    r = pdate(text)
    assert r["kind"] == kind, (style, text, r)
    if exp:
        assert r["date"] == exp


def test_fuzz_total():
    import random
    rnd = random.Random(7)
    vocab = ["the", "21st", "of", "may", "twelve", "fifty", "oh", "double", "...", "-", "sorry", "i mean", "$",
             "1,250", "2,125.10", "/", "10/20", "half", "past", "at", "seven", "pm", "tomorrow", "friday", "next",
             "?", "nineteen", "eighty", "thousand", "hundred", "and", "point", "five", "cents", "dollars", "no",
             "yes", "can't", "%", "’", "—", "88", "'", "0", "zero", "a", "week", "on", "monday"]
    cal = cal_at(WED)
    for _ in range(1500):
        s = " ".join(rnd.choice(vocab) for _ in range(rnd.randint(0, 12)))
        assert isinstance(P.parse_amount(s, {"known": [125000], "lo": 100, "hi": 999999, "full": 5000, "ref": 300}), dict)
        assert isinstance(P.parse_date(s, WED, cal, {"bare_number": True}), dict)
        assert isinstance(P.parse_time(s, 660), dict)
        assert isinstance(P.parse_dob(s, "DMY", WED), dict)
        assert isinstance(P.parse_digits(s), str)
        assert isinstance(P.parse_alnum(s), str)
        assert isinstance(P.yes_no(s), dict)
        assert P.parse_year(s, WED) is None or isinstance(P.parse_year(s, WED), int)


def test_runtime_rules_brace_and_import_safety():
    import ast
    import pathlib
    src = pathlib.Path(P.__file__).read_text()
    assert "{{" not in src and "}}" not in src
    assert "datetime.now" not in src and "date.today" not in src
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Import):
            assert all(a.name in ("re", "datetime", "json") for a in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module in ("datetime", "cal") and (node.module == "datetime" or node.level == 1)
    names = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    names += [t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)]
    csrc = pathlib.Path(C.__file__).read_text()
    ctree = ast.parse(csrc)
    cnames = [n.name for n in ctree.body if isinstance(n, ast.FunctionDef)]
    cnames += [t.id for n in ctree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)]
    assert not (set(names) & set(cnames)), set(names) & set(cnames)
    for n in names:
        assert n.startswith("_p_") or n in PUBLIC_PARSE, n
    for n in cnames:
        assert n.startswith("_c_") or n in PUBLIC_CAL, n


PUBLIC_PARSE = {"norm", "last_clause", "parse_amount", "parse_date", "parse_time", "parse_day_and_time",
                "parse_dob", "parse_digits", "parse_year", "parse_alnum", "yes_no", "is_greeting_only", "is_question",
                "has_completed_payment", "match_any", "too_much", "asks_less"}
PUBLIC_CAL = {"parse_now", "iso", "from_iso", "parse_hhmm", "prepare", "is_bd", "next_bd", "prev_bd", "add_bd",
              "week_start_of", "last_bd_of_week", "end_of_month", "last_bd_of_month", "expand_holiday_rules",
              "eval_date_rule", "weekday_date", "spoken_date", "wire_date", "wire_time", "callback_dates",
              "callback_check"}


def test_py38_syntax():
    import ast
    import pathlib
    for mod in (P, C):
        ast.parse(pathlib.Path(mod.__file__).read_text(), feature_version=(3, 8))


@pytest.mark.parametrize("text", ["Mm-hm", "uh-huh", "mhm, go on"])
def test_yes_backchannels(text):
    assert P.yes_no(text)["yn"] == "yes"


def _bundled_namespaces():
    """(label, name -> object) for the plain and the minified/renamed bundle the ctl node runs."""
    import io
    import tokenize
    from runtime import bundle as B
    try:
        plain = B.bundle_source(minify=False)
        mini = B.bundle_source()
    except (NotImplementedError, TypeError):
        pytest.skip("bundler not available")
    out = []
    g = {}
    exec(compile(plain, "ctl_plain", "exec"), g)
    out.append(("plain", g))
    try:  # mirror the bundler's renaming to look the public functions up in the minified code
        seen, bodies = [], []
        for name in B.MODULE_ORDER:
            h, body, names = B._module_body(name)
            seen += list(names)
            bodies.append(body)
        joined = "\n".join(bodies)
        all_names = set(t[1] for t in tokenize.generate_tokens(io.StringIO(joined).readline) if t[0] == tokenize.NAME)
        keep = getattr(B, "KEEP_NAMES", ("main",))
        rename = B._short_names(sorted(n for n in seen if n not in keep), all_names)
    except Exception:
        return out
    gm = {}
    exec(compile(mini, "ctl_min", "exec"), gm)
    out.append(("minified", dict((k, gm[rename.get(k, k)]) for k in seen if rename.get(k, k) in gm)))
    return out


def test_bundled_runtime_matches_modules():
    """The ctl node runs the bundled (minified, renamed) copy: it must give the same answers as the modules."""
    cal = cal_at(WED)
    texts = [x[0] for x in STYLE_AMOUNTS] + [x[1] for x in STYLE_AMOUNTS] + [x[1] for x in STYLE_DATES] + [
        "I can pay twelve fifty on Friday", "Friday the 23rd at half past six", "the third of May nineteen seventy-nine",
        "oh three five eight", "S W one A, one A A", "Yes, but I can't", "Hello?", "I already paid it.",
        "between two and four tomorrow", "nineteen eighty...", "Sometime before the 23rd.", "in an hour",
        "She left at nine this morning, she's usually back by six.", "half of it", "the minimum", "Thursday or Friday"]
    for label, g in _bundled_namespaces():
        gcal = g["prepare"](CAL_SPEC, WED)
        assert gcal == cal, label
        ctx = {"known": [125000], "full": 50000, "floor": 10000}
        for t in texts:
            assert g["parse_amount"](t, ctx) == P.parse_amount(t, ctx), (label, t)
            assert g["parse_date"](t, WED, gcal) == P.parse_date(t, WED, cal), (label, t)
            assert g["parse_time"](t, 660) == P.parse_time(t, 660), (label, t)
            assert g["parse_dob"](t, "DMY", WED) == P.parse_dob(t, "DMY", WED), (label, t)
            assert g["parse_digits"](t) == P.parse_digits(t), (label, t)
            assert g["parse_alnum"](t) == P.parse_alnum(t), (label, t)
            assert g["yes_no"](t) == P.yes_no(t), (label, t)
            assert g["parse_year"](t, WED) == P.parse_year(t, WED), (label, t)
        assert g["eval_date_rule"](gcal, {"kind": "nth_business_day_after_today", "n": 12}, WED, {}) == D("2026-11-02")
        cb = {"date_rule": {"include_today": True, "business_days_ahead": 1}, "after_now": True}
        assert g["callback_check"](gcal, cb, WED, 660, WED, 1140) == C.callback_check(cal, cb, WED, 660, WED, 1140) == "ok"


@pytest.mark.parametrize("text,now,exp", [
    ("She left at nine this morning, she's usually back by six.", 660, [360, 1080]),  # OPN-48
    ("I'm off at two, but she'll be home at five.", 660, [300, 1020]),
    ("Call her at four, not nine like last time.", 660, [240, 960]),
    ("Tomorrow at ten, sorry, I mean eleven.", 660, [660, 1380]),  # OPN-16 corrects
    ("eleven o'clock tomorrow morning", 660, [660]),  # OPN-16 in_words
    ("Eleven-ish.", 660, [660, 1380]),  # OPN-46
    ("Call back in twenty minutes.", 660, [680]),  # OPN-20d
    ("half eleven", 660, [690, 1410]),  # OPN-19
    ("quarter to seven", 660, [405, 1125]),
    ("She starts at nine, ring her at half nine.", 525, [570, 1290]),  # OPN-49
    ("Seven on the dot is fine", 660, [420, 1140]),
])
def test_time_clause_filters(text, now, exp):
    r = P.parse_time(text, now)
    assert r["kind"] == "exact" and r["alts"] == exp, (text, r)


def test_r1_floor_named_to_reject_or_ask_less_is_not_an_amount():
    ctx = {"floor": 10950, "full": 36500}
    for t in ("The minimum is too much for me.", "Even the minimum is too much.", "I want smaller instalments.",
              "Can I get lower instalments instead?"):
        assert P.parse_amount(t.lower(), ctx).get("kind") != "amount", t
    assert P.parse_amount("i can pay the minimum on friday", ctx)["cents"] == 10950


def test_r1_yes_no_zero_and_not_today():
    assert P.yes_no("I can pay nothing.")["yn"] == "no"
    assert P.yes_no("I can pay zero.")["cant"]
    r = P.yes_no("Yes, I can pay it, just not today.")
    assert r["yn"] == "yes" and r["cant"]
    assert P.yes_no("Fine, whatever.")["hedge"]


def test_r1_hour_in_the_evening_is_exact():
    assert P.parse_time("then 8 in the evening.", 660) == {"kind": "exact", "min": 1200, "alts": [1200]}
    assert P.parse_time("3 in the afternoon", 660)["min"] == 900
