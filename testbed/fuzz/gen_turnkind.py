"""Generate testbed/fuzz/turnkind.jsonl: labelled turn-classification utterances (negotiation + identity).

Reference now = 2026-10-14T11:00 (Wednesday). Gold schema per line:
  gold.stage  "neg" | "conf" | "id"
  gold.kind   primary label (what the agent must react to) = highest-precedence label in gold.kinds
  gold.kinds  every label present in the turn(s)
  gold.not    labels a naive parser is likely to assign but which are WRONG (optional)
  gold.yn     polarity toward the agent's yes/no question, only where unambiguous (optional)
  gold.hedge  true when the turn is non-committal (optional)
  gold.q      question subtype (optional): amount why who which_account consequence robot scam presence minimum
              obligation deadline clarify other
  gold.value  parsed value where the turn carries one (optional): amount_cents, date (ISO payment date), dob (ISO),
              digits (wire string), year (int)
  gold.turn_kinds  one label per customer turn for multi-turn cases (optional); for multi-turn cases kind/kinds
              describe the LAST turn read in the context of the earlier ones
"""
import json
import sys
from datetime import date, timedelta

NOW = date(2026, 10, 14)
assert NOW.weekday() == 2


def D(n):
    return (NOW + timedelta(days=n)).isoformat()


TODAY, TOM, FRI, MON, TUE20, WED21, FRI23, MON26, FRI30 = D(0), D(1), D(2), D(5), D(6), D(7), D(9), D(12), D(16)
SAT17 = D(3)
assert FRI == "2026-10-16" and MON == "2026-10-19" and TUE20 == "2026-10-20" and FRI30 == "2026-10-30"
assert FRI23 == "2026-10-23" and MON26 == "2026-10-26" and WED21 == "2026-10-21"

CTX = {
    "NEG_FULL": ("neg", "The past-due amount on your credit card is four hundred and fifty dollars. Are you able to pay that in full today?"),
    "NEG_FLOOR": ("neg", "I understand. Could you manage a smaller payment of one hundred and fifty dollars by this Friday, the sixteenth of October?"),
    "NEG_RUNG": ("neg", "Would two hundred dollars by Tuesday the twentieth of October work for you?"),
    "NEG_WHEN": ("neg", "When would you be able to pay the four hundred and fifty dollars?"),
    "NEG_HOWMUCH": ("neg", "How much would you be able to pay, and on which day?"),
    "HELP_Q": ("neg", "Of course. Before I transfer you, is there anything I can help you with myself?"),
    "CONF_A": ("conf", "So to confirm: four hundred and fifty dollars, paid this Friday, the sixteenth of October. Shall I record that?"),
    "CONF_B": ("conf", "Just to confirm, two hundred dollars on Tuesday the twentieth of October. Is that right?"),
    "ID_DOB": ("id", "Before we go on, could you please confirm your date of birth?"),
    "ID_L4": ("id", "Could you tell me the last four digits of the phone number we have on file?"),
    "ID_YEAR": ("id", "And what is your year of birth?"),
}

PREC = ["hardship", "dispute", "paid", "human", "refuse_talk", "callback", "proposal", "answer", "too_much", "incomplete",
        "decline_answer", "dont_know", "refuse_pay", "no", "question", "hold", "repeat", "withdraw", "yes", "hedge",
        "will_pay", "small_talk"]

CASES = []
COUNT = {}


def C(cat, ctx, turns, kind, kinds=None, not_=None, yn=None, hedge=None, value=None, tk=None, q=None, notes=""):
    COUNT[cat] = COUNT.get(cat, 0) + 1
    stage, ask = CTX[ctx]
    turns = [turns] if isinstance(turns, str) else list(turns)
    kinds = list(kinds) if kinds else [kind]
    g = {"stage": stage, "kind": kind, "kinds": kinds}
    if not_:
        g["not"] = list(not_)
    if yn is not None:
        g["yn"] = yn
    if hedge is not None:
        g["hedge"] = hedge
    if q:
        g["q"] = q
    if value:
        g["value"] = value
    if tk:
        g["turn_kinds"] = list(tk)
    CASES.append({"id": "tk-%s-%03d" % (cat, COUNT[cat]), "turns": turns, "context": ask, "gold": g, "notes": notes})


AMT = lambda c, d=None: dict([("amount_cents", c)] + ([("date", d)] if d else []))
DT = lambda d: {"date": d}
DOB = lambda s: {"dob": s}
DIG = lambda s: {"digits": s}

# ------------------------------------------------------------------ yes (clear acceptance / affirmation)
n = "plain yes to the pending offer"
C("yes", "NEG_FULL", "yes", "yes", yn="yes", hedge=False, notes=n)
C("yes", "NEG_FULL", "yeah that's fine", "yes", yn="yes", hedge=False, notes=n)
C("yes", "NEG_FULL", "yep I can do that", "yes", yn="yes", hedge=False, notes=n)
C("yes", "NEG_FULL", "sure go ahead", "yes", yn="yes", hedge=False, notes=n)
C("yes", "NEG_FULL", "okay yeah today's fine", "yes", yn="yes", hedge=False, notes="yes restating the offered day")
C("yes", "NEG_FULL", "yeah no problem", "yes", not_=["no"], yn="yes", hedge=False, notes="'no problem' is an affirmative")
C("yes", "NEG_FULL", "yeah no that's fine", "yes", not_=["no"], yn="yes", hedge=False,
  notes="'yeah no' is a spoken filler before agreement, not a refusal")
C("yes", "NEG_FULL", "uh huh", "yes", yn="yes", hedge=False, notes="backchannel affirmative, no punctuation")
C("yes", "NEG_FULL", "mhm yeah", "yes", yn="yes", hedge=False, notes=n)
C("yes", "NEG_FULL", "absolutely let's get it sorted", "yes", yn="yes", hedge=False, notes=n)
C("yes", "NEG_FULL", "yes I can pay the four fifty today", "yes", not_=["proposal"], yn="yes", hedge=False,
  value=AMT(45000, TODAY), notes="'four fifty' = the offered 450.00; restates the offer so it is acceptance, not a counter-proposal")
C("yes", "NEG_FULL", "of course", "yes", yn="yes", hedge=False, notes=n)
C("yes", "NEG_FULL", "yeah alright then", "yes", yn="yes", hedge=False, notes=n)
C("yes", "NEG_FULL", "go on then", "yes", yn="yes", hedge=False, notes="British idiom for agreeing")
C("yes", "NEG_FULL", "why not", "yes", not_=["question"], yn="yes", hedge=False,
  notes="'why not' is an agreement, not a why-question")
C("yes", "NEG_FULL", "fine yeah just take it today", "yes", yn="yes", hedge=False, notes="grudging but clear yes")
C("yes", "NEG_FLOOR", "yeah I can do a hundred and fifty by Friday", "yes", not_=["proposal"], yn="yes", hedge=False,
  value=AMT(15000, FRI), notes="restates the floor offer exactly")
C("yes", "NEG_FLOOR", "okay deal", "yes", yn="yes", hedge=False, notes=n)
C("yes", "NEG_RUNG", "yeah the twentieth works", "yes", not_=["proposal"], yn="yes", hedge=False, value=DT(TUE20),
  notes="names the offered date")
C("yes", "CONF_A", "yes that's right", "yes", yn="yes", hedge=False, notes="read-back confirmed")
C("yes", "CONF_A", "yep that's correct", "yes", yn="yes", hedge=False, notes="read-back confirmed")
C("yes", "CONF_A", "yes please record it", "yes", yn="yes", hedge=False, notes="read-back confirmed")
C("yes", "CONF_A", "correct", "yes", yn="yes", hedge=False, notes="one-word confirmation")
C("yes", "CONF_A", "that's right yeah", "yes", yn="yes", hedge=False, notes="read-back confirmed")
C("yes", "CONF_A", "yes sounds good", "yes", yn="yes", hedge=False, notes="read-back confirmed")
C("yes", "CONF_A", "yes friday the sixteenth four fifty", "yes", not_=["proposal"], yn="yes", hedge=False,
  value=AMT(45000, FRI), notes="echoes the read-back values")
C("yes", "CONF_A", "that works for me", "yes", yn="yes", hedge=False, notes="read-back confirmed")
C("yes", "CONF_B", "yes two hundred on the twentieth that's right", "yes", not_=["proposal"], yn="yes", hedge=False,
  value=AMT(20000, TUE20), notes="echoes the read-back values")
C("yes", "CONF_B", "spot on", "yes", yn="yes", hedge=False, notes="British idiom for correct")
C("yes", "CONF_B", "yeah yeah that's it", "yes", yn="yes", hedge=False, notes="read-back confirmed")
C("yes", "ID_DOB", "sure", "yes", not_=["answer"], yn="yes", hedge=False,
  notes="willing to answer but gave no value: agent must ask for the date itself, nothing to verify")
C("yes", "ID_L4", "yeah okay", "yes", not_=["answer"], yn="yes", hedge=False,
  notes="willing but no digits given; must not be sent to verify")
C("yes", "NEG_FULL", "I haven't paid it yet but I can today", "yes", not_=["paid"], yn="yes", hedge=False,
  value=DT(TODAY), notes="negated paid claim; accepts today")
C("yes", "NEG_FULL", "I can pay it now while we're on the phone", "yes", not_=["paid"], yn="yes", hedge=False,
  value=DT(TODAY), notes="'now' = today; future/present intent, not a completed payment")

# ------------------------------------------------------------------ no (declines the pending offer)
n = "plain decline of the pending offer (not a refusal to pay at all)"
C("no", "NEG_FULL", "no", "no", yn="no", hedge=False, notes=n)
C("no", "NEG_FULL", "nope", "no", yn="no", hedge=False, notes=n)
C("no", "NEG_FULL", "no I can't", "no", yn="no", hedge=False, notes=n)
C("no", "NEG_FULL", "no not today", "no", yn="no", hedge=False, notes="declines today only")
C("no", "NEG_FULL", "nah not happening today", "no", yn="no", hedge=False, notes=n)
C("no", "NEG_FULL", "I can't do that", "no", yn="no", hedge=False, notes=n)
C("no", "NEG_FULL", "not really no", "no", yn="no", hedge=False, notes=n)
C("no", "NEG_FULL", "no sorry I don't have it", "no", not_=["repeat"], yn="no", hedge=False,
  notes="'sorry' is an apology, not a repeat request")
C("no", "NEG_FULL", "I'm afraid not", "no", yn="no", hedge=False, notes=n)
C("no", "NEG_FULL", "not today no money's tight", "no", not_=["hardship"], yn="no", hedge=False,
  notes="tight money is no hardship cause (no job loss / illness / death)")
C("no", "NEG_FULL", "um no I don't think so", "no", not_=["hedge"], yn="no",
  notes="'I don't think so' is a polite no, not a hedge")
C("no", "NEG_FULL", "no can do", "no", not_=["yes"], yn="no", hedge=False, notes="'no can do' = no, despite 'can do'")
C("no", "NEG_FULL", "I wish I could but no", "no", not_=["yes"], yn="no", hedge=False, notes="'I could' is counterfactual")
C("no", "NEG_FULL", "no thanks", "no", yn="no", hedge=False, notes=n)
C("no", "NEG_FULL", "not at the moment no", "no", yn="no", hedge=False, notes=n)
C("no", "NEG_FULL", "I'm sorry but I just can't do it today", "no", not_=["repeat"], yn="no", hedge=False, notes=n)
C("no", "NEG_FULL", "sorry I can't", "no", not_=["repeat"], yn="no", hedge=False, notes="'sorry' as apology")
C("no", "NEG_FULL", "I lost my wallet so I can't pay today", "no", not_=["hardship"], yn="no", hedge=False,
  notes="'lost' my wallet is no hardship cause")
C("no", "NEG_FLOOR", "no that doesn't work either", "no", yn="no", hedge=False, notes=n)
C("no", "NEG_FLOOR", "no Friday's no good", "no", yn="no", hedge=False, notes=n)
C("no", "NEG_FLOOR", "I can't do Friday no", "no", yn="no", hedge=False, notes=n)
C("no", "NEG_FLOOR", "no I won't be able to", "no", yn="no", hedge=False, notes=n)
C("no", "NEG_RUNG", "not by the twentieth no", "no", not_=["proposal"], yn="no", hedge=False,
  notes="the date is named only to decline it")
C("no", "CONF_A", "no that's wrong", "no", yn="no", hedge=False, notes="read-back rejected without a new value")
C("no", "CONF_A", "nope", "no", yn="no", hedge=False, notes="read-back rejected")
C("no", "CONF_A", "no hang on that's not right", "no", not_=["hold"], yn="no", hedge=False,
  notes="'hang on' marks an objection here, not a request to wait")
C("no", "NEG_FULL", "I was going to pay it last week but my car broke down so I can't today", "no",
  not_=["paid", "hardship"], yn="no", hedge=False, notes="'was going to pay' is not a completed payment; a car repair is no hardship cause")
C("no", "NEG_FULL", "we're redoing the bathroom so money's tight. not today no", "no", kinds=["small_talk", "no"],
  not_=["hardship"], yn="no", hedge=False, notes="small talk + no")

# ------------------------------------------------------------------ hedge (non-committal)
n = "non-committal answer: neither a clear yes nor a refusal"
C("hedge", "NEG_FULL", "I think so", "hedge", yn="yes", hedge=True, notes=n)
C("hedge", "NEG_FULL", "I guess", "hedge", hedge=True, notes=n)
C("hedge", "NEG_FULL", "maybe", "hedge", hedge=True, notes=n)
C("hedge", "NEG_FULL", "maybe I'm not sure yet", "hedge", hedge=True, notes=n)
C("hedge", "NEG_FULL", "I'll try", "hedge", not_=["yes"], hedge=True, notes="'I'll try' is no commitment")
C("hedge", "NEG_FULL", "I'll try my best to get it in today", "hedge", not_=["yes"], hedge=True, notes=n)
C("hedge", "NEG_FULL", "probably yeah", "hedge", yn="yes", hedge=True, notes=n)
C("hedge", "NEG_FULL", "hopefully", "hedge", hedge=True, notes=n)
C("hedge", "NEG_FULL", "I suppose so", "hedge", yn="yes", hedge=True, notes=n)
C("hedge", "NEG_FULL", "should be okay I think", "hedge", yn="yes", hedge=True, notes=n)
C("hedge", "NEG_FULL", "possibly depends when my wages go in", "hedge", not_=["paid"], hedge=True,
  notes="conditional on income; 'wages go in' is not a payment")
C("hedge", "NEG_FULL", "I'm not sure to be honest", "hedge", not_=["no"], hedge=True, notes=n)
C("hedge", "NEG_FULL", "I don't know maybe", "hedge", not_=["no", "dont_know"], hedge=True,
  notes="'I don't know' about paying is uncertainty, not a refusal")
C("hedge", "NEG_FULL", "we'll see", "hedge", hedge=True, notes=n)
C("hedge", "NEG_FULL", "kind of depends on what comes in this week", "hedge", hedge=True, notes=n)
C("hedge", "NEG_FULL", "I might be able to", "hedge", hedge=True, notes=n)
C("hedge", "NEG_FULL", "if I can yeah", "hedge", not_=["yes"], hedge=True, notes="conditional yes = not a clear yes")
C("hedge", "NEG_FULL", "I'd have to check my account first", "hedge", not_=["hold"], hedge=True,
  notes="no request to wait now; it postpones the decision")
C("hedge", "NEG_FULL", "I guess so yeah", "hedge", yn="yes", hedge=True, notes=n)
C("hedge", "NEG_FULL", "I don't know if I can", "hedge", not_=["no"], hedge=True, notes="doubt, not a decline")
C("hedge", "NEG_FULL", "I'll do my best", "hedge", not_=["yes"], hedge=True, notes=n)
C("hedge", "NEG_FLOOR", "possibly I'd need to move some money around", "hedge", hedge=True, notes=n)
C("hedge", "NEG_FLOOR", "uh I think I can manage that", "hedge", yn="yes", hedge=True, notes=n)
C("hedge", "NEG_FLOOR", "should be fine hopefully", "hedge", yn="yes", hedge=True, notes=n)
C("hedge", "NEG_FLOOR", "not sure maybe", "hedge", not_=["no"], hedge=True, notes="'not sure' is not 'no'")
C("hedge", "NEG_RUNG", "I reckon so but don't hold me to it", "hedge", not_=["hold", "no"], hedge=True,
  notes="'don't hold me to it' is a hedge, not a hold request")
C("hedge", "CONF_A", "I think that's right", "hedge", yn="yes", hedge=True, notes="weak read-back confirmation")
C("hedge", "CONF_A", "I suppose that works", "hedge", yn="yes", hedge=True, notes=n)
C("hedge", "CONF_A", "um maybe can I think about it", "hedge", not_=["question"], hedge=True,
  notes="asking for time to think is a hedge, not an information question")
C("hedge", "CONF_A", "sounds okay I guess", "hedge", yn="yes", hedge=True, notes=n)
C("hedge", "CONF_B", "yeah probably", "hedge", yn="yes", hedge=True, notes=n)
C("hedge", "NEG_FLOOR", "I've been running around all day. I guess Friday could work", "hedge",
  kinds=["small_talk", "hedge"], hedge=True, notes="small talk + hedge on the offered day")
C("hedge", "NEG_FULL", "I've just got back from the gym. I think I can maybe", "hedge", kinds=["small_talk", "hedge"],
  hedge=True, notes="small talk + hedge")

# ------------------------------------------------------------------ small talk only
n = "small talk only: no answer, not a refusal, not a value"
C("smalltalk", "NEG_FULL", "sorry it's been such a long day I've only just got in from work", "small_talk",
  not_=["hardship", "refuse_pay", "no", "repeat"], notes=n + "; 'work' and 'sorry' are not hardship/repeat")
C("smalltalk", "NEG_FULL", "oh man the traffic on the way back was a nightmare", "small_talk", not_=["no", "refuse_pay"], notes=n)
C("smalltalk", "NEG_FULL", "the kids are running around like crazy here", "small_talk", not_=["no"], notes=n)
C("smalltalk", "NEG_WHEN", "my cousin's wedding is on the thirtieth so everything's a bit hectic", "small_talk",
  not_=["proposal"], notes=n + "; the 30th is the wedding day, never a payment date")
C("smalltalk", "NEG_FULL", "it's absolutely pouring down here today", "small_talk", not_=["proposal", "yes"],
  notes=n + "; 'today' is not acceptance")
C("smalltalk", "NEG_HOWMUCH", "I've been on my feet since six this morning", "small_talk", not_=["proposal"],
  notes=n + "; 'six' is a time, not an amount")
C("smalltalk", "NEG_FULL", "honestly work has been mental this week three people off sick", "small_talk",
  not_=["hardship"], notes=n + "; colleagues being sick is not the customer's hardship")
C("smalltalk", "NEG_FULL", "we just got back from my sister's birthday thing", "small_talk", not_=["paid"], notes=n)
C("smalltalk", "NEG_FULL", "sorry I was just making a cup of tea", "small_talk", not_=["repeat"], notes=n)
C("smalltalk", "NEG_FULL", "it's my day off so I'm just catching up on stuff", "small_talk", notes=n)
C("smalltalk", "NEG_FULL", "my phone's been playing up all week", "small_talk", notes=n)
C("smalltalk", "NEG_FULL", "I'm on my lunch break at the moment", "small_talk", not_=["callback"],
  notes=n + "; does not ask to be called back")
C("smalltalk", "NEG_WHEN", "my mum's visiting this weekend so the house is chaos", "small_talk", not_=["proposal"], notes=n)
C("smalltalk", "NEG_FULL", "ugh it's one of those weeks", "small_talk", notes=n)
C("smalltalk", "NEG_FULL", "the dog's going mad at the postman", "small_talk", not_=["hold"], notes=n)
C("smalltalk", "NEG_WHEN", "I've had my in-laws staying since Sunday", "small_talk", not_=["proposal"],
  notes=n + "; past Sunday, not a payment day")
C("smalltalk", "NEG_FULL", "I just got back from the school run", "small_talk", notes=n)
C("smalltalk", "NEG_FULL", "the wifi in this place is terrible", "small_talk", notes=n)
C("smalltalk", "NEG_FULL", "we've had builders in all week doing the kitchen", "small_talk", notes=n)
C("smalltalk", "NEG_FULL", "my boss has had us doing overtime every night", "small_talk", not_=["hardship"], notes=n)
C("smalltalk", "NEG_FULL", "I'm dying for a coffee honestly", "small_talk", not_=["hardship"], notes=n + "; idiom 'dying for'")
C("smalltalk", "ID_DOB", "sorry I'm just pulling into the car park", "small_talk", not_=["decline_answer", "repeat"],
  notes=n + "; identity question still pending, not a decline")
C("smalltalk", "ID_L4", "my reception's not great in the kitchen", "small_talk", not_=["decline_answer", "dont_know"], notes=n)
C("smalltalk", "CONF_A", "it's been one of those days honestly", "small_talk", not_=["yes", "no"], notes=n)
C("smalltalk", "NEG_FULL", "the football was on last night and I'm shattered", "small_talk", not_=["paid"], notes=n)
C("smalltalk", "NEG_FULL", "work is killing me this week", "small_talk", not_=["hardship"], notes=n + "; idiom 'killing me'")
C("smalltalk", "NEG_FULL", "I'm dead tired can we be quick", "small_talk", not_=["hardship"], notes=n + "; idiom 'dead tired'")
C("smalltalk", "NEG_FULL", "my phone died earlier so I missed your calls", "small_talk", not_=["hardship"],
  notes=n + "; a phone 'died'")
C("smalltalk", "NEG_FULL", "my old car finally died last week", "small_talk", not_=["hardship"], notes=n + "; a car 'died'")
C("smalltalk", "NEG_FULL", "the dog's been ill but he's fine now", "small_talk", not_=["hardship"], notes=n + "; a pet's illness")
C("smalltalk", "NEG_FULL", "I work in a hospital so I'm on nights this week", "small_talk", not_=["hardship"],
  notes=n + "; 'hospital' is the workplace")
C("smalltalk", "NEG_FULL", "I'm a funeral director so I'm always on call", "small_talk", not_=["hardship", "callback"],
  notes=n + "; 'funeral' is the job")
C("smalltalk", "NEG_FULL", "you sound like a real person", "small_talk", not_=["human"],
  notes=n + "; 'a real person' is a remark, not a transfer request")
C("smalltalk", "NEG_FULL", "a person from your bank called me yesterday about this", "small_talk", not_=["human", "paid"],
  notes=n + "; mentions 'a person', requests nothing")
C("smalltalk", "NEG_FULL", "I'm a busy person so let's get on with it", "small_talk", not_=["human"],
  notes=n + "; 'a busy person' is not a transfer request")

# ------------------------------------------------------------------ small talk + hold
n = "small talk plus a request to wait: hold, never a refusal"
C("hold", "NEG_FULL", "sorry the dog is barking one sec", "hold", kinds=["small_talk", "hold"],
  not_=["refuse_pay", "no", "repeat"], notes=n)
C("hold", "NEG_FULL", "sorry someone's at the door give me a moment", "hold", kinds=["small_talk", "hold"],
  not_=["no", "repeat"], notes=n)
C("hold", "NEG_FULL", "oh the baby's just woken up hang on a sec", "hold", kinds=["small_talk", "hold"], not_=["no"], notes=n)
C("hold", "ID_DOB", "oh sorry I'm driving give me a second to pull over", "hold", kinds=["small_talk", "hold"],
  not_=["decline_answer", "callback"], notes=n)

# ------------------------------------------------------------------ small talk + answer / yes / no
n = "small talk before the real answer: the answer counts"
C("stanswer", "NEG_FULL", "oh it's been a crazy day the traffic was unreal but yeah I can pay that today", "yes",
  kinds=["small_talk", "yes"], yn="yes", hedge=False, value=DT(TODAY), notes=n)
C("stanswer", "NEG_FULL", "sorry the kids are screaming um yeah go ahead today's fine", "yes", kinds=["small_talk", "yes"],
  not_=["repeat"], yn="yes", hedge=False, value=DT(TODAY), notes=n)
C("stanswer", "NEG_FULL", "work's been mad busy this week honestly. no I can't do it today", "no", kinds=["small_talk", "no"],
  yn="no", hedge=False, notes=n)
C("stanswer", "NEG_FULL", "we had the plumber round all morning nightmare. I could do two hundred on Friday though",
  "proposal", kinds=["small_talk", "proposal"], value=AMT(20000, FRI), notes=n)
C("stanswer", "NEG_WHEN", "my cousin's wedding is on the thirtieth so money's a bit everywhere but I can do a hundred and fifty on the twentieth",
  "proposal", kinds=["small_talk", "proposal"], value=AMT(15000, TUE20),
  notes=n + "; the 30th is the wedding, the payment date is the 20th")
C("stanswer", "NEG_FULL", "oh I'm so tired been up since five. Friday I can do the full thing", "proposal",
  kinds=["small_talk", "proposal"], value=AMT(45000, FRI), notes=n + "; 'five' is a time; full amount on Friday")
C("stanswer", "NEG_FULL", "the weather here is awful it hasn't stopped raining. anyway yes today is fine", "yes",
  kinds=["small_talk", "yes"], not_=["no"], yn="yes", hedge=False, value=DT(TODAY), notes=n + "; 'hasn't' is in the small talk")
C("stanswer", "NEG_WHEN", "busy busy the shop's been packed all week. I'd say Monday", "proposal",
  kinds=["small_talk", "proposal"], value=DT(MON), notes=n)
C("stanswer", "NEG_WHEN", "ah sorry I was miles away. the twenty third works", "proposal", kinds=["small_talk", "proposal"],
  not_=["repeat"], value=DT(FRI23), notes=n)
C("stanswer", "NEG_WHEN", "my daughter's birthday party was on Saturday so I'm a bit skint now. maybe Friday", "proposal",
  kinds=["small_talk", "proposal"], not_=["paid"], hedge=True, value=DT(FRI),
  notes=n + "; past Saturday is the party; hedged proposal for Friday the 16th")
C("stanswer", "NEG_HOWMUCH", "honestly it's been a rough month with the car and everything. I could probably do a hundred",
  "proposal", kinds=["small_talk", "proposal"], not_=["hardship"], hedge=True, value=AMT(10000), notes=n)
C("stanswer", "NEG_HOWMUCH", "I'm at my mum's at the moment she's doing her garden. fifty dollars on Friday", "proposal",
  kinds=["small_talk", "proposal"], value=AMT(5000, FRI), notes=n)
C("stanswer", "CONF_A", "oh sorry I was just feeding the cat. yes that's correct", "yes", kinds=["small_talk", "yes"],
  not_=["repeat"], yn="yes", hedge=False, notes=n)
C("stanswer", "CONF_A", "ha I nearly dropped the phone. yeah that's right", "yes", kinds=["small_talk", "yes"], yn="yes",
  hedge=False, notes=n)
C("stanswer", "CONF_A", "it's chucking it down here. no wait it should be the twentieth not the sixteenth", "proposal",
  kinds=["small_talk", "no", "proposal"], not_=["hold"], value=DT(TUE20),
  notes=n + "; 'wait' is a correction marker; the corrected date is the 20th")
C("stanswer", "ID_DOB", "sorry it's so noisy here I'm at the train station. it's twenty one July nineteen ninety", "answer",
  kinds=["small_talk", "answer"], not_=["incomplete", "repeat"], value=DOB("1990-07-21"),
  notes=n + "; complete without a full stop")
C("stanswer", "ID_DOB", "oh god I always hate these questions haha. fourteenth of march nineteen eighty eight", "answer",
  kinds=["small_talk", "answer"], not_=["decline_answer"], value=DOB("1988-03-14"), notes=n)
C("stanswer", "ID_DOB", "one sec I'm just parking right it's the nineteenth of October nineteen eighty three", "answer",
  kinds=["hold", "small_talk", "answer"], not_=["incomplete"], value=DOB("1983-10-19"),
  notes=n + "; the hold is moot, the answer follows in the same turn; year is 1983, not 1919")
C("stanswer", "ID_DOB", "my wife usually does all this stuff. it's the third of may seventy nine", "answer",
  kinds=["small_talk", "answer"], value=DOB("1979-05-03"), notes=n + "; two-digit year -> 1979")
C("stanswer", "ID_DOB", "ha same as my twin obviously. second of november nineteen seventy nine", "answer",
  kinds=["small_talk", "answer"], value=DOB("1979-11-02"), notes=n)
C("stanswer", "ID_L4", "I just got a new phone actually but the old number ends four four seven one", "answer",
  kinds=["small_talk", "answer"], value=DIG("4471"), notes=n)
C("stanswer", "ID_L4", "sorry I'm cooking hands are all floury. oh three five eight", "answer", kinds=["small_talk", "answer"],
  not_=["repeat"], value=DIG("0358"), notes=n)
C("stanswer", "ID_L4", "it's a work phone so I never remember it. it's six six three oh", "answer",
  kinds=["small_talk", "answer"], not_=["dont_know"], value=DIG("6630"), notes=n + "; says they never remember, then answers")
C("stanswer", "ID_L4", "it's been the same number for twenty years. it's two two one nine", "answer",
  kinds=["small_talk", "answer"], value=DIG("2219"), notes=n + "; 'twenty years' is not part of the digits")
C("stanswer", "ID_YEAR", "everyone says I look younger haha. nineteen eighty one", "answer", kinds=["small_talk", "answer"],
  value={"year": 1981}, notes=n)
C("stanswer", "NEG_FULL", "my sister just texted me sorry. what was the question", "repeat", kinds=["small_talk", "repeat"],
  notes="small talk + repeat request")
C("stanswer", "NEG_FULL", "I've been dying to sort this out actually. yes today is fine", "yes", kinds=["small_talk", "yes"],
  not_=["hardship"], yn="yes", hedge=False, value=DT(TODAY), notes="idiom 'dying to' + clear yes")
C("stanswer", "NEG_FULL", "I'm not ill or anything I just forgot to pay. I can do it today", "yes",
  kinds=["small_talk", "yes"], not_=["hardship", "paid"], yn="yes", hedge=False, value=DT(TODAY),
  notes="negated illness is no hardship; 'forgot to pay' is no paid claim")
C("stanswer", "NEG_FULL", "my job's fine I just forgot about it. I'll pay it today", "yes", kinds=["small_talk", "yes"],
  not_=["hardship"], yn="yes", hedge=False, value=DT(TODAY), notes="'my job's fine' is the opposite of job loss")

# ------------------------------------------------------------------ refuse to pay (at all)
n = "refuses to pay anything (not a refusal to talk)"
C("refpay", "NEG_FULL", "I'm not paying that", "refuse_pay", not_=["refuse_talk"], yn="no", notes=n)
C("refpay", "NEG_FULL", "I'm not paying you a penny", "refuse_pay", not_=["refuse_talk"], yn="no", notes=n)
C("refpay", "NEG_FULL", "no I'm not going to pay it simple as that", "refuse_pay", kinds=["no", "refuse_pay"],
  not_=["refuse_talk"], yn="no", notes=n)
C("refpay", "NEG_FULL", "I can't pay anything I've got nothing", "refuse_pay", not_=["hardship"], yn="no",
  notes=n + "; no cause named, so not hardship")
C("refpay", "NEG_HOWMUCH", "nothing. I can't pay anything right now", "refuse_pay", not_=["proposal"], yn="no", notes=n)
C("refpay", "NEG_HOWMUCH", "zero I've got zero", "refuse_pay", not_=["proposal"], notes=n + "; zero is no proposal")
C("refpay", "NEG_FULL", "I won't be paying anything this month or next", "refuse_pay", not_=["proposal"], yn="no", notes=n)
C("refpay", "NEG_FULL", "not a cent mate", "refuse_pay", yn="no", notes=n)
C("refpay", "NEG_FULL", "you can whistle for it", "refuse_pay", notes=n + "; idiom")
C("refpay", "NEG_FULL", "I'm not paying and that's final", "refuse_pay", not_=["refuse_talk"], yn="no", notes=n)
C("refpay", "NEG_FULL", "I don't have any money to give you", "refuse_pay", yn="no", notes=n)
C("refpay", "NEG_FULL", "I have literally no money", "refuse_pay", notes=n)
C("refpay", "NEG_FULL", "I'm skint can't pay a thing", "refuse_pay", yn="no", notes=n)
C("refpay", "NEG_FULL", "forget it I'm not paying", "refuse_pay", not_=["withdraw"], yn="no",
  notes=n + "; 'forget it' here withdraws nothing")
C("refpay", "NEG_FLOOR", "no and I'm not going to pay the minimum either", "refuse_pay", kinds=["no", "refuse_pay"],
  not_=["proposal"], yn="no", notes=n + "; naming the minimum only to refuse it")
C("refpay", "NEG_FULL", "I can't afford anything at all right now", "refuse_pay", not_=["too_much"], yn="no", notes=n)
C("refpay", "NEG_FULL", "send it to collections then I'm not paying", "refuse_pay", yn="no", notes=n)
C("refpay", "NEG_FULL", "nope not paying do what you want", "refuse_pay", yn="no", notes=n)
C("refpay", "NEG_HOWMUCH", "I can pay nothing", "refuse_pay", not_=["yes"], notes=n + "; 'I can' + nothing = zero")
C("refpay", "NEG_FULL", "I'm not in a position to pay anything", "refuse_pay", yn="no", notes=n)
C("refpay", "NEG_FULL", "I paid my rent yesterday so I've got nothing left", "refuse_pay", not_=["paid"],
  notes=n + "; the payment named is the rent, not this debt")
C("refpay", "NEG_FULL", "I'm not sick or anything I just don't have the money", "refuse_pay", not_=["hardship"], yn="no",
  notes=n + "; negated illness")

# ------------------------------------------------------------------ refuse to talk
n = "refuses the conversation (not a refusal to pay)"
C("reftalk", "NEG_FULL", "I don't want to talk about this", "refuse_talk", not_=["refuse_pay"], notes=n)
C("reftalk", "NEG_FULL", "stop calling me", "refuse_talk", not_=["refuse_pay"], notes=n)
C("reftalk", "NEG_FULL", "leave me alone", "refuse_talk", notes=n)
C("reftalk", "NEG_FULL", "I'm sick of you people calling me every day", "refuse_talk", not_=["hardship"],
  notes=n + "; idiom 'sick of'")
C("reftalk", "NEG_FULL", "I'm not discussing this over the phone", "refuse_talk", notes=n)
C("reftalk", "NEG_FULL", "I'm sick and tired of these calls", "refuse_talk", not_=["hardship"], notes=n + "; idiom")
C("reftalk", "NEG_FULL", "honestly I'm sick to death of you lot ringing", "refuse_talk", not_=["hardship"],
  notes=n + "; idiom 'sick to death'")
C("reftalk", "NEG_FULL", "I'm hanging up now", "refuse_talk", notes=n)
C("reftalk", "NEG_FULL", "don't ring this number again", "refuse_talk", notes=n)
C("reftalk", "NEG_FULL", "I don't want to speak to you", "refuse_talk", not_=["human"], notes=n)
C("reftalk", "NEG_FULL", "I'm not talking about money with a computer", "refuse_talk", not_=["human"], notes=n)
C("reftalk", "NEG_FULL", "I don't want to talk about it and I'm not paying", "refuse_talk",
  kinds=["refuse_talk", "refuse_pay"], yn="no", notes="both refusals; talk refusal wins")
C("reftalk", "NEG_FULL", "this is harassment stop phoning me", "refuse_talk", notes=n)
C("reftalk", "NEG_FULL", "I've got nothing to say to you", "refuse_talk", not_=["refuse_pay"],
  notes=n + "; 'nothing' is not a zero amount")
C("reftalk", "NEG_FULL", "please just take me off your list", "refuse_talk", notes=n)
C("reftalk", "NEG_FULL", "I've told you lot before I don't want these calls", "refuse_talk", notes=n)
C("reftalk", "NEG_FULL", "I don't wanna talk bye", "refuse_talk", notes=n)
C("reftalk", "NEG_FULL", "can you just stop bothering me", "refuse_talk", not_=["question"], notes=n + "; a request, not a question")
C("reftalk", "NEG_FULL", "I'm done with this conversation", "refuse_talk", notes=n)
C("reftalk", "CONF_A", "I'm not doing this anymore goodbye", "refuse_talk", not_=["no"], notes=n)
C("reftalk", "ID_DOB", "I don't want to talk to you lot, leave me alone", "refuse_talk", not_=["decline_answer"],
  notes=n + "; refuses the whole call, not only the question")

# ------------------------------------------------------------------ callback (cannot talk now)
n = "cannot talk now and wants a later call: neither refusal to pay nor to talk"
C("callback", "NEG_FULL", "I'm driving at the moment can you call me back later", "callback",
  not_=["refuse_talk", "question"], notes=n)
C("callback", "NEG_FULL", "I can't talk right now I'm at work", "callback", not_=["refuse_talk", "hardship", "no"], notes=n)
C("callback", "NEG_FULL", "now's not a good time I'm with a customer", "callback", not_=["refuse_talk", "no"], notes=n)
C("callback", "NEG_FULL", "can you ring me back in an hour", "callback", not_=["question"], notes=n)
C("callback", "NEG_FULL", "I'm just about to go into a meeting can we do this tomorrow", "callback",
  not_=["proposal"], notes=n + "; 'tomorrow' is when to talk, not a payment date")
C("callback", "NEG_FULL", "I'm in the middle of something call me back this afternoon", "callback", notes=n)
C("callback", "NEG_FULL", "sorry I'm at the doctor's can I call you back", "callback", not_=["hardship", "question"],
  notes=n + "; a doctor's visit is not a hardship claim")
C("callback", "NEG_FULL", "I can't really talk I'm on the train", "callback", not_=["refuse_talk", "no"], notes=n)
C("callback", "NEG_FULL", "this isn't a good time my shift starts in five minutes", "callback", not_=["refuse_talk"], notes=n)
C("callback", "NEG_FULL", "I'm putting the kids to bed can you call tomorrow morning", "callback", not_=["proposal"], notes=n)

# ------------------------------------------------------------------ questions back
C("question", "NEG_FULL", "how much is it again?", "question", q="amount", notes="question about the amount")
C("question", "NEG_FULL", "how much is it again", "question", q="amount", notes="same without a question mark (voice transcript)")
C("question", "NEG_FULL", "which account is this about", "question", q="which_account", not_=["dispute"], notes="no '?'")
C("question", "NEG_FULL", "what happens if I don't pay today?", "question", q="consequence", not_=["no", "refuse_pay"],
  notes="'don't pay' inside a question is no refusal")
C("question", "NEG_FULL", "why are you calling me about this", "question", q="why", notes="purpose question, no '?'")
C("question", "NEG_FULL", "who am I speaking to", "question", q="who", notes="identity of caller")
C("question", "NEG_FULL", "are you a robot?", "question", q="robot", not_=["human"], notes="robot question is not a transfer request")
C("question", "NEG_FULL", "is this a real person or a machine", "question", q="robot", not_=["human"],
  notes="asks what the agent is; no transfer request")
C("question", "NEG_FULL", "are you a real person", "question", q="robot", not_=["human"], notes="no '?'; not a transfer request")
C("question", "NEG_FULL", "is this a scam?", "question", q="scam", notes="scam question")
C("question", "NEG_FULL", "how do I know this is really the bank", "question", q="scam", notes="scam question, no '?'")
C("question", "NEG_FULL", "hello? are you still there?", "question", q="presence", notes="presence check")
C("question", "NEG_FULL", "can you hear me", "question", q="presence", not_=["repeat"], notes="presence check, no '?'")
C("question", "NEG_FULL", "what's the minimum I can pay", "too_much", kinds=["question", "too_much"], q="minimum",
  not_=["proposal"], notes="asks to pay less (the floor); names no amount; agent offers the floor")
C("question", "NEG_FULL", "how many days late is it?", "question", q="amount", notes="days-late question")
C("question", "NEG_FULL", "why is it four fifty what's that made up of", "question", q="amount",
  not_=["dispute", "proposal"], notes="asks for the breakdown; 'four fifty' is the amount being asked about")
C("question", "NEG_FULL", "can't you just give me a discount", "question", q="other", not_=["no", "refuse_pay"],
  notes="negated question asks; it is not a refusal")
C("question", "NEG_FULL", "do I really have to pay all of it today", "question", q="obligation", not_=["too_much", "no"],
  notes="obligation question")
C("question", "NEG_FULL", "when is the latest I can pay", "question", q="deadline", not_=["proposal"], notes="deadline question")
C("question", "NEG_FULL", "is there any way I could pay it in bits?", "question", q="other", not_=["proposal"],
  notes="asks about instalments; names no value")
C("question", "NEG_FULL", "sorry what's this regarding", "question", q="why", not_=["repeat"],
  notes="'sorry' opens a purpose question, not a repeat request")
C("question", "NEG_FULL", "what's the total including fees", "question", q="amount", notes="amount question")
C("question", "NEG_FULL", "how did you get this number", "question", q="other", notes="no '?'")
C("question", "NEG_FULL", "I'm dying to know who gave you my number", "question", q="other", not_=["hardship"],
  notes="idiom 'dying to know'")
C("question", "NEG_FULL", "I'm sick of waiting just tell me how much", "question", q="amount", not_=["hardship", "refuse_talk"],
  notes="'sick of waiting' is impatience; the request is the amount")
C("question", "NEG_FULL", "I don't need a person just tell me what I owe", "question", q="amount", not_=["human", "no"],
  notes="negated transfer request + amount question")
C("question", "NEG_FULL", "didn't I pay that already", "question", q="other", not_=["paid"],
  notes="asks; makes no paid claim")
C("question", "NEG_FULL", "maybe what happens if I don't", "question", kinds=["hedge", "question"], q="consequence",
  not_=["no"], hedge=True, notes="hedge + question: answer the question")
C("question", "NEG_FULL", "yes but what's the amount again", "question", kinds=["yes", "question"], q="amount",
  notes="a yes with a question is not a clear acceptance yet")
C("question", "ID_DOB", "why do you need that", "question", q="why", not_=["decline_answer"],
  notes="asks_back style: a question, not a decline")
C("question", "ID_DOB", "why should I tell you that", "question", q="why", not_=["answer"],
  notes="challenge question: explain why and ask again (not yet a decline)")
C("question", "ID_L4", "which phone number my mobile or the landline", "question", q="clarify", not_=["answer"],
  notes="clarifying question")
C("question", "ID_L4", "which number I've got two", "question", q="clarify", not_=["answer"], notes="'two' is not a digit answer")
C("question", "ID_DOB", "is this call recorded", "question", q="other", notes="question back during identity")
C("question", "ID_DOB", "hang on who did you say you were", "question", q="who", not_=["hold"],
  notes="'hang on' opens a question")
C("question", "ID_DOB", "how do I know you're not a scammer", "question", q="scam", not_=["decline_answer"],
  notes="scam question during identity")
C("question", "ID_L4", "the last four of my phone number", "question", q="clarify", not_=["answer"],
  notes="echo check of the question; no digits")
C("question", "CONF_A", "wait is that the sixteenth this week", "question", q="clarify", not_=["hold", "proposal"],
  notes="clarifies the read-back date")
C("question", "CONF_A", "and I'll get a text confirming that", "question", q="other", not_=["yes"],
  notes="statement-form question about confirmation; not a yes")
C("question", "NEG_WHEN", "what's today's date again", "question", q="other", not_=["proposal", "repeat"],
  notes="asks the calendar date")

# proposals phrased as questions (not questions)
n = "a proposal phrased as a question: a proposal, not a question"
C("qprop", "NEG_FULL", "can I pay two hundred on Friday instead?", "proposal", not_=["question"], value=AMT(20000, FRI), notes=n)
C("qprop", "NEG_RUNG", "what about the twenty third", "proposal", not_=["question"], value=DT(FRI23), notes=n)
C("qprop", "NEG_FULL", "would Monday work", "proposal", not_=["question"], value=DT(MON), notes=n)
C("qprop", "NEG_FULL", "could I do a hundred and fifty tomorrow", "proposal", not_=["question"], value=AMT(15000, TOM), notes=n)
C("qprop", "NEG_FULL", "if I paid three hundred on the twenty third would that be ok", "proposal",
  not_=["question", "paid"], value=AMT(30000, FRI23), notes=n + "; 'paid' is hypothetical")
C("qprop", "NEG_FLOOR", "how about a hundred on Friday and the rest next month", "proposal", not_=["question"],
  value=AMT(10000, FRI), notes=n)
C("qprop", "NEG_FULL", "is Friday okay", "proposal", not_=["question"], value=DT(FRI), notes=n)

# ------------------------------------------------------------------ hold
n = "asks the agent to wait"
C("hold", "NEG_FULL", "hold on", "hold", not_=["no"], notes=n)
C("hold", "NEG_FULL", "hang on a sec", "hold", notes=n)
C("hold", "NEG_FULL", "one moment please", "hold", notes=n)
C("hold", "NEG_FULL", "give me a second I'm just getting my card out", "hold", not_=["paid"], notes=n)
C("hold", "NEG_FULL", "wait let me check my banking app", "hold", not_=["paid"], notes=n)
C("hold", "NEG_FULL", "just a minute I need to find a pen", "hold", notes=n)
C("hold", "NEG_FULL", "can you hold on a sec", "hold", not_=["question"], notes=n + "; request, not a question")
C("hold", "NEG_FULL", "um hang on someone's at the door", "hold", kinds=["small_talk", "hold"], notes=n)
C("hold", "NEG_FULL", "bear with me", "hold", notes=n)
C("hold", "NEG_WHEN", "one sec let me look at my calendar", "hold", not_=["proposal"], notes=n)
C("hold", "NEG_FULL", "hold on hold on let me just sit down", "hold", notes=n)
C("hold", "ID_L4", "hang on let me check it's a new phone", "hold", not_=["dont_know", "decline_answer"], notes=n)
C("hold", "ID_L4", "one sec I've got to look it up", "hold", not_=["dont_know"], notes=n)
C("hold", "ID_DOB", "give me a moment", "hold", not_=["decline_answer"], notes=n)
C("hold", "CONF_A", "hmm let me think", "hold", not_=["no", "yes"], notes=n + "; asks for a moment")
C("hold", "NEG_FULL", "gimme two secs", "hold", not_=["proposal"], notes=n + "; 'two' is not an amount")
C("hold", "NEG_FULL", "just hang on while I grab my purse", "hold", notes=n)
# corrections that use wait / hold on / hang on (not holds)
n = "'wait/hold on/hang on' used as a correction marker inside an answer: not a hold"
C("holdtrap", "NEG_WHEN", "Thursday wait no Friday", "proposal", not_=["hold", "no"], value=DT(FRI), notes=n + "; corrected to Friday")
C("holdtrap", "NEG_HOWMUCH", "two hundred hold on make that two fifty", "proposal", not_=["hold"], value=AMT(25000),
  notes=n + "; corrected to 250")
C("holdtrap", "NEG_WHEN", "the twentieth hang on the twenty first", "proposal", not_=["hold"], value=DT(WED21),
  notes=n + "; corrected to the 21st")
C("holdtrap", "CONF_A", "hold on that's not right it was meant to be Monday", "proposal", kinds=["no", "proposal"],
  not_=["hold"], value=DT(MON), notes=n + "; 'was meant to be' names the intended day, Monday the 19th")
C("holdtrap", "NEG_FULL", "hang on I already paid that on Monday", "paid", not_=["hold", "proposal"],
  notes="paid claim; Monday is the past Monday 2026-10-12")
C("holdtrap", "NEG_FULL", "wait a minute this isn't even my account", "dispute", not_=["hold"], notes="dispute opened with 'wait'")
C("holdtrap", "NEG_FULL", "wait what", "repeat", not_=["hold"], notes="surprise / asks to hear it again; not a hold")
C("holdtrap", "ID_DOB", "it's the uh hang on it's the twenty first of July nineteen ninety", "answer", not_=["hold", "incomplete"],
  value=DOB("1990-07-21"), notes="self-interrupted but complete answer")

# ------------------------------------------------------------------ repeat
n = "asks the agent to say it again"
C("repeat", "NEG_FULL", "sorry?", "repeat", not_=["no"], notes=n)
C("repeat", "NEG_FULL", "pardon", "repeat", notes=n)
C("repeat", "NEG_FULL", "what?", "repeat", not_=["question"], notes=n)
C("repeat", "NEG_FULL", "come again", "repeat", notes=n)
C("repeat", "NEG_FULL", "can you say that again please", "repeat", not_=["question"], notes=n)
C("repeat", "NEG_FULL", "sorry I didn't catch that", "repeat", not_=["no"], notes=n)
C("repeat", "NEG_FULL", "you broke up a bit there what was the amount", "repeat", not_=["question"], notes=n)
C("repeat", "NEG_FULL", "sorry the line's really bad could you repeat that", "repeat", notes=n)
C("repeat", "NEG_FLOOR", "I missed the last bit what day did you say", "repeat", not_=["question"], notes=n)
C("repeat", "NEG_FULL", "say that again", "repeat", notes=n)
C("repeat", "NEG_FULL", "huh", "repeat", notes=n)
C("repeat", "NEG_FULL", "can you speak up a bit I can't hear you", "repeat", not_=["no", "refuse_pay"],
  notes=n + "; 'can't hear' is no refusal")
C("repeat", "NEG_FULL", "sorry you're going to have to repeat all of that", "repeat", notes=n)
C("repeat", "NEG_FULL", "sorry the dog was barking what did you say", "repeat", kinds=["small_talk", "repeat"], notes=n)
C("repeat", "NEG_RUNG", "what was the date again", "repeat", not_=["question"], notes=n)
C("repeat", "NEG_FULL", "sorry what was that I was miles away", "repeat", kinds=["small_talk", "repeat"], notes=n)
C("repeat", "ID_DOB", "sorry what did you need", "repeat", not_=["decline_answer"], notes=n)
C("repeat", "ID_L4", "the last four what sorry", "repeat", not_=["answer"], notes=n + "; 'four' is not a digit answer")
C("repeat", "CONF_A", "sorry can you read that back again", "repeat", not_=["no"], notes=n)
C("repeat", "NEG_FULL", "eh", "repeat", notes=n)
# 'sorry' that is not a repeat
C("repeattrap", "NEG_WHEN", "the nineteenth sorry I mean the twentieth", "proposal", not_=["repeat"], value=DT(TUE20),
  notes="'sorry, I mean' corrects the date; the 20th counts")
C("repeattrap", "NEG_FULL", "sorry to keep you yes go ahead", "yes", not_=["repeat"], yn="yes", hedge=False,
  notes="apology then clear yes")
C("repeattrap", "NEG_HOWMUCH", "a hundred sorry a hundred and twenty", "proposal", not_=["repeat"], value=AMT(12000),
  notes="corrected to 120")

# ------------------------------------------------------------------ paid (completed) vs future
n = "claims a completed payment of this debt"
C("paid", "NEG_FULL", "I already paid it", "paid", not_=["proposal", "yes"], notes=n)
C("paid", "NEG_FULL", "I paid that this morning in the app", "paid", not_=["proposal"], notes=n)
C("paid", "NEG_FULL", "I sent the money yesterday", "paid", not_=["proposal"], notes=n)
C("paid", "NEG_FULL", "I've paid it check your records", "paid", notes=n)
C("paid", "NEG_FULL", "it's been paid I did it on Monday", "paid", not_=["proposal"],
  notes=n + "; passive 'been paid' (not an income phrase); Monday = 2026-10-12, past")
C("paid", "NEG_FULL", "the payment went out this morning", "paid", notes=n + "; no 'paid' verb")
C("paid", "NEG_FULL", "I transferred it last night", "paid", notes=n)
C("paid", "NEG_FULL", "my husband paid it for me on Friday", "paid", not_=["proposal"],
  notes=n + "; past Friday 2026-10-09, not the coming Friday")
C("paid", "NEG_FULL", "I paid it last week didn't you get it", "paid", kinds=["paid", "question"], not_=["no"],
  notes=n + "; negated tag question about receipt")
C("paid", "NEG_FULL", "I cleared the balance on Monday", "paid", notes=n)
C("paid", "NEG_FULL", "I made the payment at the branch yesterday afternoon", "paid", notes=n)
C("paid", "NEG_FULL", "I set up the transfer last night should land tomorrow", "paid", not_=["proposal"],
  notes=n + "; already initiated, in transit; 'tomorrow' is arrival, not a promise")
C("paid", "NEG_FULL", "I'm pretty sure I paid that already", "paid", hedge=True, notes=n + "; hedged but still a paid claim")
C("paid", "NEG_FULL", "I paid it I've got the receipt right here", "paid", notes=n)
C("paid", "NEG_FULL", "the payment went through on Sunday", "paid", not_=["proposal"], notes=n + "; past Sunday 2026-10-11")
C("paid", "CONF_A", "no need I've just paid it all online", "paid", kinds=["no", "paid"], notes=n)
C("paid", "NEG_FLOOR", "I sent a hundred and fifty this morning", "paid", not_=["proposal"],
  notes=n + "; the amount is what was sent, not an offer")
C("paid", "NEG_FULL", "the bank transfer I did on Monday should have cleared by now", "paid", not_=["proposal"], notes=n)
C("paid", "NEG_FULL", "already done I paid it at lunch", "paid", notes=n)
C("paid", "NEG_FULL", "that's not right I paid it this morning", "paid", not_=["dispute", "no"], notes=n)
C("paid", "NEG_FULL", "I already sorted it on the app yesterday", "paid", notes=n + "; 'sorted it' = paid")
C("paid", "NEG_FULL", "my daughter settled it for me last week", "paid", notes=n)
C("paid", "ID_DOB", "I already paid this why do you need my date of birth", "paid", kinds=["paid", "question"],
  not_=["decline_answer"], notes=n + " during identity")
C("paid", "NEG_RUNG", "I've already paid two hundred last Thursday", "paid", not_=["proposal"],
  notes=n + "; past Thursday 2026-10-08")
n = "future or hypothetical payment: not a paid claim"
C("future", "NEG_FULL", "I'll pay it tomorrow", "proposal", not_=["paid"], value=DT(TOM), notes=n)
C("future", "NEG_FULL", "I'm going to pay it on Friday", "proposal", not_=["paid"], value=DT(FRI), notes=n)
C("future", "NEG_FULL", "I will pay just not today", "no", kinds=["will_pay", "no"], not_=["paid", "refuse_pay"], yn="no",
  notes=n + "; declines today, intends to pay")
C("future", "NEG_FULL", "I get paid on Friday so I can pay it then", "proposal", not_=["paid"], value=DT(FRI),
  notes=n + "; 'get paid' is income")
C("future", "NEG_WHEN", "I'm getting paid on the twentieth", "proposal", not_=["paid"], value=DT(TUE20),
  notes=n + "; salary day offered as the answer to 'when'")
C("future", "NEG_WHEN", "I'll have paid it by Friday", "proposal", not_=["paid"], value=DT(FRI),
  notes=n + "; future perfect is a promise, not a completed payment")
C("future", "NEG_FLOOR", "I've paid some of it already I'll pay the rest on Friday", "proposal", kinds=["proposal"],
  not_=["paid"], value=DT(FRI), notes="partial earlier payment + future date for the rest: not a full paid claim")
C("future", "NEG_WHEN", "I'll send it over tonight", "proposal", not_=["paid"], value=DT(TODAY), notes=n + "; tonight = today")
C("future", "NEG_FULL", "I'm gonna transfer it when I get home", "will_pay", not_=["paid", "proposal"],
  notes=n + "; no explicit day (agent should confirm today)")
C("future", "NEG_WHEN", "payday's Friday I'll sort it then", "proposal", not_=["paid"], value=DT(FRI), notes=n)
C("future", "NEG_FULL", "I'm going to pay it I promise", "will_pay", not_=["paid", "yes"], notes=n + "; no day named")
C("future", "NEG_FULL", "I'll pay it don't worry", "will_pay", not_=["paid", "yes"], notes=n + "; no day named")
C("future", "NEG_WHEN", "when my wages go in on the twenty third", "proposal", not_=["paid"], value=DT(FRI23), notes=n)

# ------------------------------------------------------------------ dispute
n = "disputes the debt / the account"
C("dispute", "NEG_FULL", "that's not my debt", "dispute", not_=["no"], notes=n)
C("dispute", "NEG_FULL", "I've never had a credit card with you", "dispute", notes=n)
C("dispute", "NEG_FULL", "I don't recognise that account at all", "dispute", notes=n)
C("dispute", "NEG_FULL", "I closed that account years ago", "dispute", not_=["paid"], notes=n)
C("dispute", "NEG_FULL", "that's not mine someone must have opened it in my name", "dispute", notes=n + " (fraud)")
C("dispute", "NEG_FULL", "I paid that card off in twenty nineteen and closed it", "dispute", not_=["paid"],
  notes=n + "; a closure years ago is a dispute, not a payment of this past-due amount")
C("dispute", "NEG_FULL", "the amount's wrong I only owe about two hundred", "dispute", not_=["proposal"],
  notes=n + "; the figure is what they believe they owe, not an offer")
C("dispute", "NEG_FULL", "those are fees you added I'm not paying fees I never agreed to", "dispute",
  kinds=["dispute", "refuse_pay"], notes=n)
C("dispute", "NEG_FULL", "I never took out a loan", "dispute", notes=n)
C("dispute", "NEG_FULL", "I'm not paying that I'm not even sure it's mine", "dispute", kinds=["dispute", "refuse_pay"],
  hedge=True, notes="hedged dispute")
C("dispute", "NEG_FULL", "that should have been cancelled when I moved", "dispute", notes=n)
C("dispute", "NEG_FULL", "that's my ex-husband's card not mine", "dispute", not_=["hardship"], notes=n)
C("dispute", "NEG_FULL", "I think there's been a mix-up I've never missed a payment", "dispute", not_=["paid"], notes=n)
C("dispute", "NEG_FULL", "this is a mistake the account was closed last year", "dispute", notes=n)
C("dispute", "NEG_FULL", "I've already disputed this with your fraud team", "dispute", not_=["paid"], notes=n)
C("dispute", "NEG_FULL", "I always pay on time I don't know why it says late", "dispute", not_=["paid", "dont_know"],
  notes=n + " (lateness)")
C("dispute", "NEG_FULL", "what is this debt I don't have any loan with you", "dispute", kinds=["dispute", "question"],
  notes=n + " with a question")
C("dispute", "CONF_A", "actually I want to check this is even mine first", "dispute", not_=["yes"], hedge=True,
  notes="doubts the debt at read-back")
C("dispute", "NEG_FULL", "I paid it off ages ago that card's closed", "dispute", not_=["paid"], notes=n)
C("disputetrap", "NEG_FULL", "which card is it I've got a few with you", "question", q="which_account", not_=["dispute"],
  notes="asks which product; disputes nothing")
C("disputetrap", "NEG_FULL", "yeah it's mine I just forgot. I can pay it today", "yes", not_=["dispute"], yn="yes", hedge=False,
  value=DT(TODAY), notes="owns the debt and accepts")
C("disputetrap", "NEG_FULL", "the amount isn't what I expected but fine I'll pay it today", "yes", not_=["dispute"], yn="yes",
  value=DT(TODAY), notes="surprise at the amount, still a yes")

# ------------------------------------------------------------------ hardship (named cause) vs idioms
n = "hardship with a named cause"
C("hardship", "NEG_FULL", "I lost my job last month and I can't pay anything", "hardship", kinds=["hardship", "refuse_pay"],
  notes=n + " (job loss)")
C("hardship", "NEG_FULL", "I got laid off two weeks ago", "hardship", notes=n + " (job loss)")
C("hardship", "NEG_FULL", "I was made redundant in September", "hardship", not_=["paid"], notes=n + " (redundancy)")
C("hardship", "NEG_FULL", "I've been in hospital for the last three weeks", "hardship", notes=n + " (illness)")
C("hardship", "NEG_FULL", "I'm off sick from work with my back I'm only on sick pay", "hardship", not_=["paid"],
  notes=n + " (illness; 'sick pay' is income)")
C("hardship", "NEG_FULL", "my husband died last month and everything's in his name", "hardship", notes=n + " (bereavement)")
C("hardship", "NEG_FULL", "my mum passed away on Saturday I really can't deal with this right now", "hardship",
  not_=["refuse_talk", "callback"], notes=n + " (bereavement)")
C("hardship", "NEG_FULL", "I've just been diagnosed with cancer", "hardship", notes=n + " (illness)")
C("hardship", "NEG_FULL", "I'm on chemo and can't work", "hardship", notes=n + " (illness)")
C("hardship", "NEG_FULL", "my hours got cut at work so I'm only getting half my wages", "hardship",
  notes=n + " (income cut)")
C("hardship", "NEG_FULL", "I've been out of work since the factory closed", "hardship", not_=["dispute"],
  notes=n + " (job loss); 'closed' is the factory, not the account")
C("hardship", "NEG_FULL", "I had an accident at work and I've been signed off", "hardship", notes=n + " (injury)")
C("hardship", "NEG_FULL", "my son's been really ill and I've had to stop working to look after him", "hardship",
  notes=n + " (family illness, lost income)")
C("hardship", "NEG_FULL", "we had a death in the family and the funeral took everything", "hardship", notes=n + " (bereavement)")
C("hardship", "NEG_FULL", "I'm unemployed at the moment", "hardship", notes=n + " (unemployment)")
C("hardship", "NEG_FULL", "I just had surgery and I'm not back at work till next month", "hardship", not_=["proposal"],
  notes=n + " (illness)")
C("hardship", "NEG_FULL", "they let me go at the end of September", "hardship", not_=["withdraw"], notes=n + " (job loss)")
C("hardship", "NEG_FULL", "I'm disabled and my benefits got stopped", "hardship", notes=n + " (disability, income)")
C("hardship", "NEG_FULL", "my wife is in hospital and I've had to take unpaid leave", "hardship", notes=n + " (family illness)")
C("hardship", "NEG_FULL", "I'm not working at the moment", "hardship", notes=n + "; negation describes unemployment, it does not void it")
C("hardship", "NEG_FULL", "I haven't had a job since June", "hardship", notes=n + "; negated sentence still states job loss")
C("hardship", "NEG_FULL", "no I've been off work with depression", "hardship", kinds=["no", "hardship"],
  notes=n + " (mental illness)")
C("hardship", "NEG_FULL", "I closed my shop last month and money's been really tight", "hardship", not_=["dispute"],
  notes=n + " (business closure = lost income); not an account closure")
C("hardship", "NEG_FLOOR", "I got sacked on Monday so even that's too much", "hardship", kinds=["hardship", "too_much"],
  notes=n + " (job loss); Monday is past")
C("hardship", "CONF_A", "actually I should tell you I'm being made redundant next month", "hardship", not_=["yes"],
  notes=n + " (upcoming redundancy) raised at read-back")
C("hardship", "ID_DOB", "I lost my job I really can't deal with this right now", "hardship", not_=["decline_answer", "refuse_talk"],
  notes=n + " during identity")
C("hardship", "NEG_HOWMUCH", "honestly nothing my dad died and I've been off work since", "hardship",
  kinds=["hardship", "refuse_pay"], not_=["proposal"], notes=n + " (bereavement)")
n = "idiom or unrelated use of a hardship word: not hardship"
C("hardtrap", "NEG_FULL", "I nearly died when I saw the amount it's way too much", "too_much", not_=["hardship"],
  notes=n + "; 'nearly died' is a reaction to the bill")
C("hardtrap", "NEG_FULL", "I'm sick of being chased for this", "refuse_talk", not_=["hardship"], notes=n)
C("hardtrap", "NEG_FULL", "this is doing my head in", "small_talk", not_=["hardship"], notes=n + "; venting, no answer")
C("hardtrap", "NEG_FULL", "I'm not unemployed or anything I just forgot", "small_talk", not_=["hardship"],
  notes=n + "; denies unemployment; no answer to the offer yet")
C("hardtrap", "NEG_FULL", "my neighbour lost her job so I've been helping out with her kids", "small_talk", not_=["hardship"],
  notes=n + "; the neighbour's job loss, not the customer's")
C("hardtrap", "NEG_FULL", "the job I'm on today is miles away so I'm in the van", "small_talk", not_=["hardship"],
  notes=n + "; 'job' is today's work")

# ------------------------------------------------------------------ human request / withdrawn
n = "asks for a human agent"
C("human", "NEG_FULL", "can I speak to a real person please", "human", not_=["question"], notes=n)
C("human", "NEG_FULL", "I want to talk to a human", "human", not_=["refuse_talk"], notes=n)
C("human", "NEG_FULL", "put me through to someone", "human", notes=n)
C("human", "NEG_FULL", "get me your manager", "human", notes=n)
C("human", "NEG_FULL", "I'd rather talk to an actual person about this", "human", notes=n)
C("human", "NEG_FULL", "is there someone real I can talk to", "human", not_=["question"], notes=n)
C("human", "NEG_FULL", "transfer me to an agent please", "human", notes=n)
C("human", "NEG_FULL", "I'm not doing this with a machine give me a person", "human", not_=["refuse_talk"], notes=n)
C("human", "NEG_FULL", "operator", "human", notes=n + " (one word)")
C("human", "NEG_FULL", "let me speak to a person I don't trust these robots", "human", not_=["question"], notes=n)
C("human", "NEG_FULL", "are you a robot? I want a human", "human", kinds=["question", "human"], q="robot", notes=n)
C("human", "NEG_FULL", "is there not a human I can talk to", "human", not_=["no", "question"], notes=n + "; negated question form")
C("human", "NEG_FULL", "I'd like to speak to your supervisor", "human", notes=n)
C("human", "ID_DOB", "I'm not giving my details to a bot put me through to a person", "human", kinds=["decline_answer", "human"],
  notes=n + " during identity")
C("human", "HELP_Q", "no just put me through", "human", kinds=["no", "human"], not_=["refuse_pay"],
  notes="insists on the transfer after the help question")
C("human", "HELP_Q", "no I'm good transfer me", "human", kinds=["no", "human"], notes="insists")
C("human", "HELP_Q", "nope", "human", kinds=["no", "human"],
  notes="a plain no to 'anything I can help with before I transfer you' keeps the transfer")
C("human", "HELP_Q", "no thanks I'd still like the person", "human", kinds=["no", "human"], notes="insists")
n = "a transfer request taken back: not a human request"
C("withdraw", "NEG_FULL", "can I speak to a person actually never mind let's just do it", "withdraw", not_=["human"], notes=n)
C("withdraw", "NEG_FULL", "I want a human. no wait forget it it's fine", "withdraw", not_=["human", "hold"], notes=n)
C("withdraw", "NEG_FULL", "put me through to someone actually no it's okay carry on", "withdraw", not_=["human", "no"], notes=n)
C("withdraw", "HELP_Q", "it's fine I don't need anyone let's sort it", "withdraw", not_=["human"], notes=n)
C("withdraw", "HELP_Q", "don't transfer me I'll deal with you", "withdraw", not_=["human"], notes=n)
C("withdraw", "HELP_Q", "actually no need let's just carry on", "withdraw", not_=["human", "no"], notes=n)
C("withdraw", "HELP_Q", "never mind I'll just pay it today", "proposal", kinds=["withdraw", "proposal"], not_=["human"],
  value=DT(TODAY), notes=n + "; and offers to pay today")
C("withdraw", "HELP_Q", "actually yeah how much do I owe", "question", kinds=["question"], q="amount", not_=["human"],
  notes="takes up the help offer with a question")
C("withdraw", "HELP_Q", "oh okay then I'll stay with you, can I do a hundred on the twentieth", "proposal",
  kinds=["withdraw", "proposal"], not_=["human"], value=AMT(10000, TUE20), notes=n + "; plus a proposal")
C("withdraw", "NEG_FULL", ["can I talk to a real person", "actually never mind go on"], "withdraw",
  not_=["human"], tk=["human", "withdraw"], notes="request in turn 1, withdrawn in turn 2 (agent asked the help question between)")
C("withdraw", "NEG_FULL", ["I want to speak to a human", "no just put me through"], "human", kinds=["no", "human"],
  tk=["human", "human"], notes="request, then insists after the help question")
C("withdraw", "NEG_FULL", ["is there a human I can speak to", "hmm actually it's okay what was the amount again"], "repeat",
  kinds=["withdraw", "repeat"], not_=["human"], tk=["human", "repeat"],
  notes="turn 2 withdraws the request and asks for a repeat")
C("withdraw", "NEG_FULL", ["get me a manager", "fine forget it, I'll pay on Friday"], "proposal",
  kinds=["withdraw", "proposal"], not_=["human"], value=DT(FRI), tk=["human", "proposal"],
  notes="turn 2 withdraws and proposes Friday 16th")

# ------------------------------------------------------------------ too much
n = "the amount is more than the customer can pay"
C("toomuch", "NEG_FULL", "that's way too much", "too_much", not_=["refuse_pay"], notes=n)
C("toomuch", "NEG_FULL", "I can't pay all of that", "too_much", not_=["refuse_pay"], notes=n)
C("toomuch", "NEG_FULL", "I can't afford four fifty", "too_much", not_=["proposal"], notes=n + "; the amount named is the one refused")
C("toomuch", "NEG_FULL", "I can only pay part of it", "too_much", not_=["yes"], notes=n)
C("toomuch", "NEG_FULL", "that's a lot of money for me right now", "too_much", notes=n)
C("toomuch", "NEG_FULL", "the full amount's too much but I could do some", "too_much", hedge=True, notes=n)
C("toomuch", "NEG_FLOOR", "even a hundred and fifty is too much", "too_much", not_=["proposal", "yes"],
  notes=n + "; the floor is refused")
C("toomuch", "NEG_FULL", "I can't do the whole thing at once", "too_much", notes=n)
C("toomuch", "NEG_FULL", "is there a way to pay less", "too_much", kinds=["question", "too_much"], q="minimum",
  notes="asks to pay less; agent offers the floor")
C("toomuch", "NEG_FULL", "four fifty no chance I can maybe do a bit of it", "too_much", not_=["proposal", "yes"], hedge=True,
  notes=n)
C("toomuch", "NEG_FULL", "I haven't got that kind of money", "too_much", not_=["paid"], notes=n)
C("toomuch", "NEG_RUNG", "two hundred is more than I can manage", "too_much", not_=["proposal"], notes=n)
C("toomuch", "NEG_FULL", "that's too much but I can do a hundred on Friday", "proposal", kinds=["too_much", "proposal"],
  value=AMT(10000, FRI), notes="a concrete smaller proposal in the same turn wins over too-much")
C("toomuch", "NEG_FULL", "not all of it no", "too_much", kinds=["no", "too_much"], notes=n)

# ------------------------------------------------------------------ identity answers (complete, in words, no punctuation)
n = "complete date of birth said in words without punctuation"
C("dob", "ID_DOB", "twenty one July nineteen ninety", "answer", not_=["incomplete"], value=DOB("1990-07-21"),
  notes=n + "; known bug: treated as incomplete without a full stop")
C("dob", "ID_DOB", "nineteen October nineteen eighty three", "answer", not_=["incomplete"], value=DOB("1983-10-19"),
  notes=n + "; known bug: read as year 1919")
C("dob", "ID_DOB", "the fourteenth of March nineteen eighty eight", "answer", value=DOB("1988-03-14"), notes=n)
C("dob", "ID_DOB", "March fourteenth nineteen eighty eight", "answer", value=DOB("1988-03-14"), notes=n)
C("dob", "ID_DOB", "it's the second of November seventy nine", "answer", value=DOB("1979-11-02"), notes=n + "; 2-digit year")
C("dob", "ID_DOB", "thirtieth of January nineteen eighty four", "answer", value=DOB("1984-01-30"), notes=n)
C("dob", "ID_DOB", "seventeenth may eighty six", "answer", value=DOB("1986-05-17"), notes=n)
C("dob", "ID_DOB", "fifth December nineteen seventy five", "answer", value=DOB("1975-12-05"), notes=n)
C("dob", "ID_DOB", "twenty eighth April ninety three", "answer", value=DOB("1993-04-28"), notes=n)
C("dob", "ID_DOB", "eleventh of August nineteen eighty one", "answer", value=DOB("1981-08-11"), notes=n)
C("dob", "ID_DOB", "twenty third Feb eighty nine", "answer", value=DOB("1989-02-23"), notes=n + "; abbreviated month")
C("dob", "ID_DOB", "third June nineteen eighty seven", "answer", value=DOB("1987-06-03"), notes=n)
C("dob", "ID_DOB", "eighth of January ninety one", "answer", value=DOB("1991-01-08"), notes=n)
C("dob", "ID_DOB", "nineteen ninety two July the twenty first", "answer", value=DOB("1992-07-21"), notes=n + "; year first")
C("dob", "ID_DOB", "two thousand and one the fifth of June", "answer", value=DOB("2001-06-05"), notes=n + "; 2000s year first")
C("dob", "ID_DOB", "um it's the uh twelfth of uh February nineteen sixty", "answer", value=DOB("1960-02-12"),
  notes=n + "; fillers")
C("dob", "ID_DOB", "ninth of September ninety", "answer", value=DOB("1990-09-09"), notes=n)
C("dob", "ID_DOB", "nineteenth of September nineteen eighty", "answer", value=DOB("1980-09-19"), notes=n)
C("dob", "ID_DOB", "September nineteen nineteen eighty", "answer", not_=["incomplete"], value=DOB("1980-09-19"),
  notes=n + "; 'nineteen nineteen eighty' = day 19 + year 1980, not year 1919")
C("dob", "ID_DOB", "first of the first two thousand", "answer", value=DOB("2000-01-01"), notes=n + "; ordinal month")
C("dob", "ID_DOB", "yeah sure it's the twenty first of July nineteen ninety", "answer", kinds=["yes", "answer"],
  value=DOB("1990-07-21"), notes=n + "; yes + value")
C("dob", "ID_DOB", "twelfth of July ninety one no sorry twenty first of July nineteen ninety", "answer",
  not_=["repeat", "no"], value=DOB("1990-07-21"), notes=n + "; self-correction: the last date counts")
C("dob", "ID_YEAR", "nineteen eighty one", "answer", value={"year": 1981}, notes="year of birth in words")
C("dob", "ID_YEAR", "eighty one", "answer", value={"year": 1981}, notes="2-digit year -> 1981 (age 45)")
C("dob", "ID_YEAR", "two thousand and four", "answer", value={"year": 2004}, notes="year in words (age 22)")
n = "complete digits answer"
C("digits", "ID_L4", "four four seven one", "answer", value=DIG("4471"), notes=n)
C("digits", "ID_L4", "forty four seventy one", "answer", value=DIG("4471"), notes=n + "; paired digits")
C("digits", "ID_L4", "oh three five eight", "answer", value=DIG("0358"), notes=n + "; 'oh' = 0")
C("digits", "ID_L4", "double two eight eight", "answer", value=DIG("2288"), notes=n)
C("digits", "ID_L4", "it ends in six six oh four", "answer", value=DIG("6604"), notes=n)
C("digits", "ID_L4", "my number's oh seven nine one one two three four four seven one", "answer", value=DIG("4471"),
  notes=n + "; recites the whole number, the last four count")
C("digits", "ID_L4", "four four seven one no sorry four four one oh", "answer", not_=["no", "repeat"], value=DIG("4410"),
  notes=n + "; self-correction")
C("digits", "ID_L4", "yeah it's nine nine oh four", "answer", kinds=["yes", "answer"], value=DIG("9904"), notes=n)
C("digits", "ID_L4", "fifteen oh two", "answer", value=DIG("1502"), notes=n + "; 'fifteen' + 'oh two'")
C("digits", "ID_L4", "eight eight four six", "answer", value=DIG("8846"), notes=n)
C("digits", "ID_L4", "three three one seven", "answer", value=DIG("3317"), notes=n)
C("digits", "ID_L4", "seven oh nine three", "answer", value=DIG("7093"), notes=n)
n = "declines or cannot answer the identity question"
C("idno", "ID_DOB", "I'm not giving that out over the phone", "decline_answer", not_=["refuse_talk", "refuse_pay"], notes=n)
C("idno", "ID_DOB", "I'd rather not say", "decline_answer", not_=["hedge"], notes=n)
C("idno", "ID_DOB", "no", "decline_answer", kinds=["no", "decline_answer"], yn="no", notes=n + "; plain no to the identity ask")
C("idno", "ID_L4", "pass", "decline_answer", notes=n)
C("idno", "ID_DOB", "you should have that already", "decline_answer", not_=["answer"], notes=n + "; pushback, no value")
C("idno", "ID_DOB", "I'm not telling you that", "decline_answer", not_=["refuse_talk"], notes=n)
C("idno", "ID_L4", "none of your business", "decline_answer", not_=["refuse_talk"], notes=n)
C("idno", "ID_L4", "I don't know it off the top of my head", "dont_know", not_=["no", "decline_answer"], notes=n)
C("idno", "ID_L4", "I can't remember it's a new phone", "dont_know", not_=["no", "decline_answer"], notes=n)
C("idno", "ID_L4", "honestly I don't know my own number", "dont_know", not_=["decline_answer", "no"], notes=n)
C("idno", "ID_L4", "no idea mate my wife set the account up", "dont_know", not_=["no"], notes=n)

# ------------------------------------------------------------------ two-part answers across turns (pieces style)
n = "two-part answer across turns: the first turn is a fragment (never a decline), the joined value counts"
C("pieces", "ID_DOB", ["twenty one July", "nineteen ninety"], "answer", not_=["decline_answer", "no"],
  value=DOB("1990-07-21"), tk=["incomplete", "answer"], notes=n)
C("pieces", "ID_DOB", ["the nineteenth of October", "nineteen eighty three"], "answer", not_=["decline_answer"],
  value=DOB("1983-10-19"), tk=["incomplete", "answer"], notes=n)
C("pieces", "ID_DOB", ["nineteen October", "nineteen eighty three"], "answer", not_=["decline_answer"],
  value=DOB("1983-10-19"), tk=["incomplete", "answer"], notes=n + "; 'nineteen October' is day+month, not a year")
C("pieces", "ID_DOB", ["fourteenth of March", "eighty eight"], "answer", value=DOB("1988-03-14"), tk=["incomplete", "answer"],
  notes=n)
C("pieces", "ID_DOB", ["it's the third of May", "nineteen seventy nine"], "answer", value=DOB("1979-05-03"),
  tk=["incomplete", "answer"], notes=n)
C("pieces", "ID_DOB", ["nineteen eighty six", "May the seventeenth"], "answer", value=DOB("1986-05-17"),
  tk=["incomplete", "answer"], notes=n + "; year first")
C("pieces", "ID_DOB", ["second of November", "seventy nine"], "answer", value=DOB("1979-11-02"), tk=["incomplete", "answer"],
  notes=n)
C("pieces", "ID_DOB", ["sorry the kids are shouting. it's the twenty eighth of April", "ninety three"], "answer",
  value=DOB("1993-04-28"), tk=["incomplete", "answer"], notes=n)
C("pieces", "ID_DOB", ["twenty one July", "sorry nineteen ninety"], "answer", not_=["repeat"], value=DOB("1990-07-21"),
  tk=["incomplete", "answer"], notes=n + "; 'sorry' is filler, it corrects nothing")
C("pieces", "ID_DOB", ["nineteenth", "of October nineteen eighty three"], "answer", value=DOB("1983-10-19"),
  tk=["incomplete", "answer"], notes=n)
C("pieces", "ID_DOB", ["the fifth of December", "um seventy five"], "answer", value=DOB("1975-12-05"),
  tk=["incomplete", "answer"], notes=n)
C("pieces", "ID_DOB", ["January", "the thirtieth nineteen eighty four"], "answer", value=DOB("1984-01-30"),
  tk=["incomplete", "answer"], notes=n + "; month alone first")
C("pieces", "ID_DOB", ["eleventh of August", "eighty one"], "answer", value=DOB("1981-08-11"), tk=["incomplete", "answer"],
  notes=n)
C("pieces", "ID_DOB", ["twenty third of February", "nineteen eighty nine"], "answer", value=DOB("1989-02-23"),
  tk=["incomplete", "answer"], notes=n)
C("pieces", "ID_L4", ["oh three", "five eight"], "answer", value=DIG("0358"), tk=["incomplete", "answer"], notes=n)
C("pieces", "ID_L4", ["double two", "one nine"], "answer", value=DIG("2219"), tk=["incomplete", "answer"], notes=n)
C("pieces", "ID_L4", ["forty four", "ten"], "answer", value=DIG("4410"), tk=["incomplete", "answer"], notes=n)
C("pieces", "ID_L4", ["four four", "seven one"], "answer", value=DIG("4471"), tk=["incomplete", "answer"], notes=n)
C("pieces", "ID_L4", ["it's six six", "three oh"], "answer", value=DIG("6630"), tk=["incomplete", "answer"], notes=n)
C("pieces", "ID_L4", ["eighty eight", "forty six"], "answer", value=DIG("8846"), tk=["incomplete", "answer"], notes=n)
n = "payment value given across two turns: the joined value counts (not the deadline, not the first fragment)"
C("pieces", "NEG_WHEN", ["the thirtieth", "of October"], "proposal", value=DT(FRI30), tk=["proposal", "proposal"],
  not_=["no"], notes=n + "; known bug: recorded on the deadline instead of the 30th")
C("pieces", "NEG_WHEN", ["on the", "twenty third"], "proposal", value=DT(FRI23), tk=["incomplete", "proposal"], notes=n)
C("pieces", "NEG_HOWMUCH", ["I can do two hundred and", "fifty on Friday"], "proposal", value=AMT(25000, FRI),
  tk=["incomplete", "proposal"], notes=n + "; 'and' leaves the number open")
C("pieces", "NEG_WHEN", ["the twentieth", "of October yeah"], "proposal", value=DT(TUE20), tk=["proposal", "proposal"], notes=n)
C("pieces", "NEG_WHEN", ["the twenty", "sixth"], "proposal", value=DT(MON26), tk=["incomplete", "proposal"],
  notes=n + "; 'twenty' + 'sixth' = the 26th")
C("pieces", "NEG_FULL", ["I'm going to pay", "on Friday"], "proposal", value=DT(FRI), tk=["will_pay", "proposal"],
  not_=["paid"], notes=n)
C("pieces", "NEG_HOWMUCH", ["three hundred", "on the thirtieth of October"], "proposal", value=AMT(30000, FRI30),
  tk=["proposal", "proposal"], notes=n)
C("pieces", "NEG_WHEN", ["Friday the", "thirtieth"], "proposal", value=DT(FRI30), tk=["incomplete", "proposal"],
  notes=n + "; Friday the 30th (consistent weekday)")

# ------------------------------------------------------------------ other multi-turn mixes
C("multi", "NEG_FULL", ["oh it's mad here the kids are off school", "anyway yeah today's fine"], "yes",
  tk=["small_talk", "yes"], yn="yes", value=DT(TODAY), notes="small talk turn, then yes")
C("multi", "NEG_FULL", ["hang on", "okay sorry I'm back. yes I can do that today"], "yes", tk=["hold", "yes"], yn="yes",
  value=DT(TODAY), notes="hold, then yes")
C("multi", "NEG_FULL", ["which account is this", "oh right okay yeah I'll pay it today"], "yes", tk=["question", "yes"],
  yn="yes", value=DT(TODAY), notes="asks_back, then yes")
C("multi", "NEG_FULL", ["sorry the dog is barking one sec", "right sorry about that. I can't do today but Friday's fine"],
  "proposal", kinds=["no", "proposal"], tk=["hold", "proposal"], value=DT(FRI), notes="hold turn, then a counter-proposal")
C("multi", "NEG_FULL", ["I'm driving give me a sec to pull over", "okay. what was the amount again"], "repeat",
  tk=["hold", "repeat"], notes="hold, then repeat request")
C("multi", "NEG_FULL", ["I think so", "yeah yes today is fine"], "yes", tk=["hedge", "yes"], yn="yes",
  value=DT(TODAY), notes="hedge firmed into a yes on the re-ask")
C("multi", "CONF_A", ["hmm let me think", "yeah okay that's right"], "yes", tk=["hold", "yes"], yn="yes", notes="hold, then yes")
C("multi", "ID_DOB", ["why do you need it", "fine. twenty first of July nineteen ninety"], "answer", tk=["question", "answer"],
  value=DOB("1990-07-21"), notes="asks_back, then answer")
C("multi", "ID_L4", ["hang on let me find it", "okay it's two two one nine"], "answer", tk=["hold", "answer"],
  value=DIG("2219"), notes="hold, then answer")
C("multi", "NEG_WHEN", ["my cousin's wedding is on the thirtieth so it's all go", "but I could pay on the twenty third"],
  "proposal", tk=["small_talk", "proposal"], not_=["no"], value=DT(FRI23),
  notes="the 30th is the wedding (small talk); the payment date is the 23rd")
C("multi", "NEG_FULL", ["no", "well maybe I can do a hundred on Friday"], "proposal", tk=["no", "proposal"], hedge=True,
  value=AMT(10000, FRI), notes="no, then a hedged counter-proposal")
C("multi", "NEG_FULL", ["sorry what", "oh right no I can't do today"], "no", tk=["repeat", "no"], yn="no",
  notes="repeat, then no")
C("multi", "ID_DOB", ["is this really the bank", "okay fine. fourteenth of March eighty eight"], "answer",
  tk=["question", "answer"], value=DOB("1988-03-14"), notes="scam question, then answer")
C("multi", "NEG_FULL", ["ugh what a day", "honestly I don't know if I can"], "hedge", tk=["small_talk", "hedge"], hedge=True,
  notes="small talk, then hedge")
C("multi", "NEG_FULL", ["hold on", "sorry that was my boss. no I can't today I just lost my job last week"], "hardship",
  kinds=["no", "hardship"], tk=["hold", "hardship"], notes="hold, then hardship (job loss)")
C("multi", "NEG_FULL", ["I already paid", "yeah on Monday through the app"], "paid", tk=["paid", "paid"], not_=["proposal"],
  notes="paid claim, then its past date (Monday 2026-10-12)")
C("multi", "NEG_FULL", ["can you hear me", "okay good. no I can't pay that today"], "no", tk=["question", "no"], not_=["yes"], yn="no",
  notes="presence check, then no")
C("multi", "ID_L4", ["pardon", "oh the last four. four four seven one"], "answer", tk=["repeat", "answer"],
  value=DIG("4471"), notes="repeat, then answer; 'four' in 'last four' is not a digit")
C("multi", "NEG_HOWMUCH", ["um let me think", "a hundred and twenty on the twentieth"], "proposal", tk=["hold", "proposal"],
  value=AMT(12000, TUE20), notes="hold, then proposal")
C("multi", "CONF_A", ["sorry the traffic's mad", "yes that's all correct"], "yes", tk=["small_talk", "yes"], yn="yes",
  notes="small talk, then yes")


DROP = {
    "yes": [4, 9, 10, 12, 13, 18, 21, 22, 24, 25, 27, 30], "no": [2, 4, 5, 7, 14, 15, 20, 22],
    "hedge": [4, 8, 12, 14, 16, 19, 21, 24, 31], "smalltalk": [2, 3, 5, 10, 11, 14, 17, 18, 19],
    "hold": [6, 7, 10, 13, 15], "stanswer": [2, 8, 12, 14, 20], "refpay": [2, 8, 10, 12, 13, 17, 18],
    "reftalk": [3, 5, 8, 9, 15, 17, 20], "callback": [4, 6], "question": [1, 15, 19, 22, 23, 33, 34, 39],
    "repeat": [4, 5, 10, 11, 13, 20], "paid": [4, 11, 14, 19], "dispute": [3, 9, 11, 15],
    "hardship": [2, 3, 8, 15, 16], "human": [3, 5, 7, 13], "toomuch": [4, 5, 14], "dob": [4, 8, 10, 12, 13],
    "digits": [10, 12], "idno": [6, 10],
}
_drop = set("tk-%s-%03d" % (k, i) for k, v in DROP.items() for i in v)
_n = len(CASES)
CASES[:] = [c for c in CASES if c["id"] not in _drop]
assert _n - len(CASES) == len(_drop), (_n, len(CASES), len(_drop))
COUNT.clear()
for c in CASES:
    cat = c["id"].split("-")[1]
    COUNT[cat] = COUNT.get(cat, 0) + 1
    c["id"] = "tk-%s-%03d" % (cat, COUNT[cat])

# ------------------------------------------------------------------ validate + write
LABELS = set(PREC)
ids = set()
for c in CASES:
    g = c["gold"]
    assert c["id"] not in ids, c["id"]
    ids.add(c["id"])
    for k in g["kinds"] + [g["kind"]] + g.get("not", []) + g.get("turn_kinds", []):
        assert k in LABELS, (c["id"], k)
    assert g["kind"] in g["kinds"], c["id"]
    top = min(g["kinds"], key=PREC.index)
    assert top == g["kind"], (c["id"], g["kinds"], g["kind"], top)
    assert not (set(g.get("not", [])) & set(g["kinds"])), c["id"]
    if "turn_kinds" in g:
        assert len(g["turn_kinds"]) == len(c["turns"]), c["id"]
    v = g.get("value", {})
    if "dob" in v:
        y, m, d = map(int, v["dob"].split("-"))
        dd = date(y, m, d)
        age = NOW.year - y - ((NOW.month, NOW.day) < (m, d))
        assert 18 <= age <= 100, (c["id"], age)
    if "date" in v:
        assert date.fromisoformat(v["date"]) >= NOW, c["id"]
    assert c["notes"] and "NOT USED" not in c["notes"], c["id"]

out = sys.argv[1]
with open(out, "w") as f:
    for c in CASES:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")
print(len(CASES), COUNT)
