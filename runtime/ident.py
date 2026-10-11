"""Right-party matcher, identity answer normalisation, verify-result classifier (docs/CONTRACTS.md C.4).
Owner: agent 2.

Rules: Python 3.8 syntax; stdlib only; no double curly braces; private helpers prefixed _i_; total on bad input.
"""
import re
import datetime
from .parse import norm, last_clause, parse_dob, parse_digits, parse_year, parse_alnum, yes_no, is_greeting_only
from .parse import is_question
from .cal import iso, wire_date

_I_FOLD = {"a": "àáâãäåā", "c": "çćč", "e": "èéêëēėę", "i": "ìíîïī", "n": "ñń", "o": "òóôõöøō",
           "u": "ùúûüū", "s": "śšß", "z": "źżž", "y": "ýÿ", "l": "ł", "g": "ğ"}
_I_FOLD_MAP = dict((ch, k) for k, v in _I_FOLD.items() for ch in v)

_I_NONE = ("", "pending", "none", "null", "undefined", "nan")

_I_Q_ROBOT = re.compile(r"\b(robot|a bot|bot\b|an ai\b|ai\?|artificial|machine|automated|recording|real person"
                        r"|computer|human\?)")
_I_Q_SCAM = re.compile(r"\b(scam|fraud|fake|legit|legitimate|really the bank|really from|how do i know|phishing)")
_I_Q_WHO = re.compile(r"\b(who is (this|it|that|calling|speaking)|who's (this|it|that|calling|speaking)"
                      r"|who are you|who am i speaking|who am i talking|whom am i|who's there|who is there"
                      r"|where are you calling from|where are you from|what company|which company"
                      r"|who did you say|what's your name|what is your name|who (do you|did you) want)")
_I_Q_WHY = re.compile(r"\b(what is (this|it) (about|regarding|for|concerning)|what's (this|it) (about|regarding|for)"
                      r"|what (is|was) this call|why are you calling|why do you (want|need|ask)|what do you want"
                      r"|what('s| is) the (reason|matter|call about)|reason for (the|your|this) call|regarding what"
                      r"|what about|how did you get (my|this) (number|name)|why\b)")
_I_TP = re.compile(
    r"\b((he|she|they)('s| is| are|'re)? (not|at|out|away|busy|in the|working|sleeping|asleep|unavailable|still"
    r"|on (holiday|vacation)|abroad|travelling|traveling|in hospital|gone|moved|left)"
    r"|(he|she|they) (isn't|is not|aren't|are not|can't|cannot|won't|will not|doesn't|does not|don't)"
    r"|not (here|home|in|available|around) (right now|now|at the moment|today)?"
    r"|isn't (here|home|in|available|around)|is not (here|home|in|available|around)"
    r"|i'm (his|her|their)\b|i am (his|her|their)\b|this is (his|her|their)\b|it's (his|her|their)\b"
    r"|it is (his|her|their)\b"
    r"|(my|our) (husband|wife|son|daughter|mother|father|mom|mum|dad|partner|brother|sister|boyfriend"
    r"|girlfriend|roommate|flatmate|housemate|colleague|boss|grandmother|grandfather|aunt|uncle|niece|nephew)"
    r"|take a message|leave (him|her|them) a message|pass (it|the message) on|tell (him|her|them)"
    r"|wrong person|not (him|her|them)\b|i'm not (him|her|mr|ms|mrs|miss|dr)\b|i am not (him|her|mr|ms|mrs|miss|dr)\b"
    r"|you want (my|his|her)|you're looking for (my|his|her)|speaking (?:to|with) (his|her|their)"
    r"|[a-z]+'s (husband|wife|son|daughter|mother|father|mom|mum|dad|partner|brother|sister|boyfriend|girlfriend"
    r"|roommate|flatmate|housemate|colleague|boss|assistant|secretary|carer|caregiver|neighbou?r|friend))")
_I_HOLD = re.compile(r"\b(hold on|hang on|one (second|sec|moment|minute)|just a (second|sec|moment|minute)"
                     r"|wait a (second|sec|moment|minute)|let me (get|fetch|grab|call) (him|her|them)"
                     r"|i'll (get|fetch|grab|call) (him|her|them)|i will (get|fetch|grab) (him|her|them)"
                     r"|(he|she)('s| is) (coming|right here|here now))")
_I_VOICEMAIL = re.compile(r"\b(leave (a|your) message|after the (tone|beep)|voicemail|mailbox|not available to take"
                          r"|cannot take your call|can't take your call|the person you are calling)")
_I_SELF = re.compile(r"\b(?:this is|it's|it is|i am|i'm|my name is|my name's|name's|you're speaking (?:to|with)"
                     r"|you are speaking (?:to|with))\s+(?:mr\.?|ms\.?|mrs\.?|miss|dr\.?)?\s*([a-z][a-z'\-]+)")
# "<name> speaking/here", scanned run by run by _i_self_post (one regex over the text retried every \b inside a long
# hyphen/apostrophe run and was quadratic there)
_I_RUN = re.compile(r"[a-z'\-]+")
_I_POST_TAIL = re.compile(r"\s+(?:speaking|here)\b")
_I_WORDCH = re.compile(r"\w")
_I_NOT_NAMES = set((
    "me", "him", "her", "he", "she", "they", "them", "not", "calling", "speaking", "fine", "good", "busy", "sorry",
    "yes", "correct", "right", "afraid", "just", "here", "the", "a", "an", "his", "their", "my", "your", "on",
    "at", "in", "home", "out", "away", "who", "what", "really", "actually", "still", "also", "so", "very", "ok",
    "okay", "sure", "well", "about", "is", "it", "this", "that", "be", "being", "there", "all", "only", "now",
    "back", "going", "getting", "having", "doing", "working", "listening", "fine", "great", "happy", "free",
    "available", "unavailable", "glad", "tired", "driving", "sick", "ill", "alone", "no", "nobody", "someone",
    "somebody", "everyone", "talking", "and", "but", "or", "phone", "line", "i", "we", "you", "speaker",
    "wife", "husband", "son", "daughter", "mother", "father", "mum", "mom", "dad", "partner", "brother", "sister",
    "i'm", "im", "we're", "you're", "he's", "she's", "they're", "it's", "that's", "there's", "nobody's", "who's",
))
_I_YES = re.compile(r"^(?:oh |well |um |uh |er |hi |hello |hey )*(yes|yeah|yep|yup|ya|yah|aye|correct|right"
                    r"|that's right|that is right|that's correct|that is correct|indeed|sure|certainly|affirmative"
                    r"|absolutely|mm-?hmm|uh-?huh|mhm|yes i am|that's true|true)\b"
                    # "I am." / "It is." / "You are." confirm only as the whole clause ("I am afraid not" denies)
                    r"|^(?:oh |well |um |uh |er )*(?:you are|you do|i am|it is)\W*$")
_I_STRONG = re.compile(r"\b(speaking(?! (?:to|with) (?:his|her|their|my)\b)|that's me|that is me|it's me|it is me|this is me|that'd be me|that would be me"
                       r"|you've got (him|her|me)|you have (him|her|me)|you're speaking (to|with) (him|her|me)"
                       r"|yes it is|yes i am|the one and only|in person)\b")
_I_GREETW = r"(?:hi|hello|hey|hiya|oh|well|um|uh|er|erm|ah)"
_I_YESW = r"(?:yes|yeah|yep|yup|ya|yah|aye|correct|that's right|that is right|that's correct|that is correct)"
_I_YES_LEAD = re.compile(r"^\W*(?:" + _I_GREETW + r"\W+)*" + _I_YESW + r"(?:\s*[,.!;]\s*\w|\s*[.!]?\s*$)", re.I)
_I_NOTME = re.compile(r"\b(?:i'm|i am|it's|it is|this is|that's|that is) not\b|\bwrong\b|\bno\b")
_I_DENY = re.compile(r"\b(?:no|nope|not (?:him|her|them|me)|wrong (?:person|guy|man|woman|one)|i'm not|i am not"
                     r"|this is (?:his|her|their)|i'm (?:his|her|their)|i am (?:his|her|their)|it's (?:his|her|their))\b")
_I_TITLES = frozenset(("mr", "ms", "mrs", "miss", "dr", "mister", "missus", "sir", "madam", "doctor", "it", "is", "this",
                 "speaking", "here"))
_I_NO = re.compile(r"^(?:oh |well |um |uh )*(no|nope|nah|negative|not really|incorrect|wrong|(?:i'm|i am) afraid not)\b")
_I_HEDGE = re.compile(r"\b(i think|maybe|perhaps|probably|might be|depends|who wants to know)\b")
_I_DEFAULT_LAST = re.compile(r"\blast\b")


def _i_self_post(t):
    """The names X of "X speaking" / "X here" in t, as the regex \\b([a-z][a-z'\\-]+)\\s+(?:speaking|here)\\b finds them
    with finditer. Within one run of [a-z'-] every start has the same continuation, so only the first start that
    the regex allows (a letter not preceded by a word character) is tried."""
    out, pos = [], 0
    while True:
        r = _I_RUN.search(t, pos)
        if not r:
            return out
        st = None
        for i in range(r.start(), r.end() - 1):
            if "a" <= t[i] <= "z" and (i == 0 or not _I_WORDCH.match(t[i - 1])):
                st = i
                break
        tail = _I_POST_TAIL.match(t, r.end()) if st is not None else None
        if tail:
            out.append(t[st:r.end()])
            pos = tail.end()
        else:
            pos = r.end()


def _i_fold(s):
    try:
        return "".join(_I_FOLD_MAP.get(c, c) for c in (s or "").lower())
    except Exception:
        return ""


def _i_text(text):
    try:
        return norm(_i_fold(text or ""))
    except Exception:
        return _i_fold(text or "").strip()


def _i_capitalised(raw, tok):
    """True when tok occurs in the raw text with an upper-case first letter (a spoken name, not a word)."""
    try:
        for m in re.finditer(r"[A-Za-z\u00c0-\u017f][A-Za-z\u00c0-\u017f'\-]*", raw or ""):
            w = m.group(0)
            if _i_fold(w).strip("'-") == tok and w[0].isupper():
                return True
    except Exception:
        pass
    return False


def _i_qtype(t):
    if _I_Q_ROBOT.search(t):
        return "robot"
    if _I_Q_SCAM.search(t):
        return "scam"
    if _I_Q_WHO.search(t):
        return "who"
    if _I_Q_WHY.search(t):
        return "why"
    return ""


def _i_name_tokens(name_tokens):
    out = set()
    for n in name_tokens or []:
        for p in re.split(r"[\s\-]+", _i_fold(str(n or ""))):
            p = p.strip(".'")
            if len(p) >= 2:
                out.add(p)
        whole = _i_fold(str(n or "")).strip()
        if whole:
            out.add(whole)
    return out


def rp_classify(text, _u_act, name_tokens):
    """-> {"cls": "confirm"|"deny"|"third_party"|"question"|"greeting"|"unclear",
           "q": "robot"|"scam"|"who"|"why"|"other"|"", "hold": bool, "close"?: "deceased"|"wrong_number"}. Code
    decides from the text alone; the extraction hint u_act (2nd argument, kept for the C.4 signature) is not used.
    "close" (third_party only): the speaker says the named customer has died, or does not know them."""
    try:
        return _i_rp(text, name_tokens)
    except Exception:
        return {"cls": "unclear", "q": "", "hold": False}


def _i_rp(text, name_tokens):
    raw = text or ""
    try:
        clause = last_clause(raw)
    except Exception:
        clause = raw
    t = _i_text(clause)
    full = _i_text(raw)
    res = {"cls": "unclear", "q": "", "hold": False}
    if not t:
        return res
    has_q = "?" in raw
    try:
        has_q = has_q or bool(is_question(clause))
    except Exception:
        pass
    q = _i_qtype(t)
    if _I_VOICEMAIL.search(full):
        return res
    names = _i_name_tokens(name_tokens)
    # "Yes... he passed away." / "I don't know who that is.": the named customer has died, or is unknown here.
    # A strong confirmation or the speaker's own name keeps the customer (the death is someone else's).
    selfref = _I_STRONG.search(full) or any(tok.strip("'-") in names for tok in
                                            [m.group(1) for m in _I_SELF.finditer(full)] + _i_self_post(full))
    if _I_TP.search(full) or not selfref or re.search(r"\bno (?:mr |ms |mrs |miss |dr )?[a-z'\-]+ here\b", full):
        if _i_dead_third(raw, full, names):
            res.update(cls="third_party", close="deceased")
            return res
        if _i_unknown(full, names):
            res.update(cls="third_party", close="wrong_number")
            return res
    # a strong first-sentence confirmation ("Yes, speaking. Sorry, my father died...") is not undone by later
    # chatter that mentions a relative; only an explicit denial undoes it
    first = _i_text(re.split(r"[.!?;]+", raw)[0])          # raw is a str here (non-str folds to "" above)
    if first and first != t and not _I_DENY.search(full):
        own_first = any(tok.strip("'-") in names for tok in
                        [m.group(1) for m in _I_SELF.finditer(first)] + _i_self_post(first))
        if _I_STRONG.search(first) or own_first or _i_yes_first(raw, first, full, names):
            res["cls"] = "confirm"
            res["q"] = q if has_q else ""
            return res
    # self-reference with a name: own name confirms, a different name means someone else (beats "yes")
    own = False
    other = False
    for tok in [m.group(1) for m in _I_SELF.finditer(t)] + _i_self_post(t):
        tok = tok.strip("'-")
        if tok.endswith("'s"):
            continue
        if tok in names:
            own = True
        elif tok not in _I_NOT_NAMES and len(tok) >= 2 and _i_capitalised(raw, tok):
            other = True
    if _I_HOLD.search(t) and not own:
        res["cls"] = "third_party"
        res["hold"] = True
        return res
    if other and not own:
        res["cls"] = "third_party"
        return res
    if _I_TP.search(t) and not own:
        res["cls"] = "third_party"
        return res
    if own:
        res["cls"] = "confirm"
        res["q"] = q if has_q else ""
        return res
    if _I_STRONG.search(t):
        res["cls"] = "confirm"
        res["q"] = q if has_q else ""
        return res
    # a leading "yes," clause followed by more words confirms, even with a question after it
    # ("Yes, what is this about?", "Hi, yes."); a lone "Yes?" does not
    if _I_YES_LEAD.match(raw) and not _I_HEDGE.search(t) and not _I_NOTME.search(full):
        res["cls"] = "confirm"
        res["q"] = q if has_q else ""
        return res
    if _i_bare_name(raw, names):
        res["cls"] = "confirm"
        return res
    if _I_YES.search(t):
        # "Yes?" / "yes" + a who/why question is not a confirmation
        if q or (has_q and len(t.split()) <= 3):
            res["cls"] = "question" if q else "greeting"
            res["q"] = q
            return res
        if has_q:
            res["cls"] = "question"
            res["q"] = "other"
            return res
        if _I_HEDGE.search(t):
            return res
        res["cls"] = "confirm"
        return res
    if q:
        res["cls"] = "question"
        res["q"] = q
        return res
    if _I_NO.search(t):
        res["cls"] = "deny"
        return res
    try:
        if is_greeting_only(raw):
            res["cls"] = "greeting"
            return res
    except Exception:
        pass
    if has_q:
        res["cls"] = "question"
        res["q"] = "other"
        return res
    return res


_I_RELATIVE = re.compile(r"\b(?:my|our) (?:husband|wife|son|daughter|mother|father|mom|mum|dad|partner|brother|sister"
                         r"|boyfriend|girlfriend|grandmother|grandfather|grandma|grandpa|gran|aunt|uncle|niece|nephew"
                         r"|cousin|friend|child|baby)\b")
# a death stated about a third person ("he passed away", "she's dead", "his funeral"): the named customer has died,
# unless a relative of the speaker is named before it ("Yes. My father died, he was ill." is the customer talking)
_I_DEAD_V = r"(?:passed away|passed on|passed|died|is dead|was dead|is deceased|was deceased|deceased)"
_I_DEAD3 = re.compile(r"\b(?:he|she|they)(?:'s| has| had| have|'ve)?\s+(?:\w+\s+)?" + _I_DEAD_V + r"\b"
                      r"|\b(?:he|she)(?:'s| is| was)\s+(?:sadly\s+|now\s+)?(?:dead|deceased|no longer (?:with us|alive|living))\b"
                      r"|\b(?:his|her) (?:death|passing|funeral)\b")
# the speaker does not know the named person: a wrong number
# ("I don't know who this is" / "who you are" is about the caller, not the customer, and stays a who-question)
_I_WHO_THAT = (r"who (?:that is|that's|that person is|he is|she is|you mean|you(?:'re| are) (?:talking about|looking for"
               r"|asking (?:for|about)|after))")
_I_UNKNOWN = re.compile(r"\b(?:i )?(?:don't|do not|dont) know (?:(?:him|her|anyone|anybody|any(?:one|body)? (?:by|called|named)"
                        r"|(?:that|this) (?:name|person|man|woman|guy)|" + _I_WHO_THAT + r")\b)"
                        r"|\bnever (?:heard of|met) (?:him|her|them|that|this|anyone|anybody|any)\b"
                        r"|\bno idea who (?:that is|that's|you mean|you(?:'re| are) (?:talking about|looking for))\b"
                        r"|\bno ?(?:one|body) (?:here |lives here )?(?:by|called|named) ")


def _i_dead_third(raw, full, names):
    """The turn says the named person (not a relative of the speaker) has died."""
    hits = [m.start() for m in _I_DEAD3.finditer(full)]
    for tok in names:
        if len(tok) >= 2 and " " not in tok:
            m = re.search(r"\b" + re.escape(tok) + r"(?:'s| has| had)?\s+(?:\w+\s+)?" + _I_DEAD_V + r"\b", full)
            if m and _i_capitalised(raw, tok):
                return True
    for pos in hits:
        if not _I_RELATIVE.search(full[:pos]):
            return True
    return False


def _i_unknown(full, names):
    """'I don't know who that is' / 'Never heard of him' / 'I don't know any <Name>' / 'There's no <Name> here':
    a wrong number."""
    if _I_UNKNOWN.search(full):
        return True
    for tok in names:
        if " " not in tok and re.search(r"\b(?:there(?:'s| is) no |(?:don't|do not|dont) know (?:any |a |an )?)"
                                        r"(?:mr |ms |mrs |miss |dr |mister )?" + re.escape(tok) + r"\b", full):
            return True
    return False


def _i_yes_first(raw, first, full, names):
    """'Yes. My father died last week.' / 'Yes, this is she. My husband passed away.': a plain yes-type first
    sentence ended by '.' or '!' confirms when the rest names no other person except the speaker's own relatives."""
    if not _I_YES_LEAD.match(first) or _I_HEDGE.search(first) or _I_NOTME.search(first):
        return False
    end = len(re.split(r"[.!?;]+", raw)[0])
    if raw[end:end + 1] not in (".", "!") or not re.search(r"[A-Za-z]", raw[end:]):
        return False
    rest = _I_RELATIVE.sub(" ", full[len(first):] if full.startswith(first) else full)
    for tok in [m.group(1) for m in _I_SELF.finditer(full)] + _i_self_post(full):
        tok = tok.strip("'-")
        if tok not in names and tok not in _I_NOT_NAMES and _i_capitalised(raw, tok):
            return False
    return not _I_TP.search(rest) and not _I_HOLD.search(rest)


def _i_bare_name(raw, names):
    """'<First>.', '<First> <Last>.', '<Title> <Last>.', 'Yes, <Last>.' -> True: every remaining word is one of the name tokens."""
    try:
        if "?" in (raw or "") or not names:
            return False
        t = _i_text(raw)
        t = re.sub(r"^\W*(?:" + _I_GREETW + r"\W+)*", "", t)
        t = re.sub(r"\b" + _I_YESW + r"\b", " ", t)
        toks = [x.strip("'-") for x in re.findall(r"[a-z][a-z'\-]*", t)]
        toks = [x for x in toks if x and x not in _I_TITLES]
        if not toks:
            return False
        hit = False
        for x in toks:
            if x in names:
                hit = True
            else:
                return False
        return hit
    except Exception:
        return False


def _i_is_last_n(q):
    s = (str(q.get("field_value", "")) + " " + str(q.get("key", "")) + " " + str(q.get("ask", ""))).lower()
    return bool(_I_DEFAULT_LAST.search(s.replace("_", " "))) or bool(re.search(r"last\d", s))


def _i_pattern_ok(q, wire):
    pat = q.get("pattern") or ""
    if not pat:
        return True
    try:
        return re.match(pat, wire) is not None
    except Exception:
        return True


def _i_done(q, wire):
    if wire and _i_pattern_ok(q, wire):
        return {"status": "complete", "wire": wire}
    return {"status": "invalid"}


def _i_date_wire(q, y, m, d):
    try:
        dd = datetime.date(int(y), int(m), int(d))
    except Exception:
        return ""
    fmt = q.get("wire_format") or "%Y-%m-%d"
    try:
        return wire_date(dd, fmt)
    except Exception:
        return iso(dd)


def _i_answer_date(q, text, frag, today):
    order = q.get("numeric_order") or "DMY"
    r = parse_dob(text, order, today) or {}
    if r.get("kind") != "date" and frag:
        r2 = parse_dob(frag + " " + (text or ""), order, today) or {}
        if r2.get("kind") in ("date", "incomplete"):
            r = r2
            text = frag + " " + (text or "")
    k = r.get("kind")
    if k == "incomplete":
        have = r.get("have") or {}
        y = _i_tens_year(text or "", today)
        if y and have.get("m") and have.get("d") and not have.get("y"):
            r = {"kind": "date", "y": y, "m": have.get("m"), "d": have.get("d")}
            k = "date"
    if k == "date":
        w = _i_date_wire(q, r.get("y"), r.get("m"), r.get("d"))
        if not w:
            return {"status": "invalid"}
        return _i_done(q, w)
    if k == "incomplete":
        return {"status": "incomplete", "frag": (text or "").strip()[-120:]}
    if k == "invalid":
        return {"status": "invalid"}
    return {"status": "none"}


_I_TENS = dict(ten=10, twenty=20, thirty=30, forty=40, fifty=50, sixty=60, seventy=70, eighty=80, ninety=90)
_I_TENS_YEAR = re.compile(r"\b(nineteen|twenty|two thousand(?: and)?)\s+(ten|twenty|thirty|forty|fifty|sixty|seventy"
                          r"|eighty|ninety)\s*[.!]?\s*$")


def _i_tens_year(text, today):
    """'... nineteen ninety' ending the turn (optional . or !) -> 1990; a trail-off (..., ',', '-') -> None."""
    try:
        m = _I_TENS_YEAR.search(_i_fold(text).strip())
        if not m:
            return None
        base = 1900 if m.group(1) == "nineteen" else 2000
        if m.group(1) == "twenty":
            base = 2000
        y = base + _I_TENS[m.group(2)]
        if today is not None and not (today.year - 110 <= y <= today.year):
            return None
        return y
    except Exception:
        return None


def _i_digits_only(s):
    """Only the ASCII digits 0-9 of s (other Unicode digits are dropped, as by [^0-9])."""
    return "".join(ch for ch in s if ch in "0123456789")


def _i_answer_digits(q, text, frag):
    n = int(q.get("length") or 0)
    d = parse_digits(text) or ""
    d = _i_digits_only(d)
    frag = _i_digits_only(frag or "")
    if not d:
        return {"status": "none"}
    if n <= 0:
        return _i_done(q, d)
    if len(d) == n:
        return _i_done(q, d)
    if len(d) > n:
        if _i_is_last_n(q):
            return _i_done(q, d[-n:])
        return {"status": "invalid"}
    merged = frag + d
    if len(merged) == n:
        return _i_done(q, merged)
    if len(merged) < n:
        return {"status": "incomplete", "frag": merged}
    return {"status": "incomplete", "frag": d}


_I_FULL_YEAR = re.compile(r"\b\d{4}\b|\b(?:nineteen|twenty|thousand|hundred)\b")
_I_DIGIT1 = re.compile(r"\b(?:zero|oh|one|two|three|four|five|six|seven|eight|nine|\d)\b")
_I_NUMW = re.compile(r"\d|\b(?:ten|eleven|twelve|\w+teen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)\b")


def _i_answer_year(q, text, frag, today=None):
    y = parse_year(text, today)
    if y is None and frag:
        y = parse_year(frag + " " + (text or ""), today)
    if y is None:
        # "Nineteen ninety." is left open by parse_year (it may go on); a finished utterance completes it
        y = _i_tens_year(((frag + " ") if frag else "") + (text or ""), today)
    t = _i_fold(((frag + " ") if frag else "") + (text or ""))
    if (q.get("two_digit_year") or "ask_full") == "ask_full" and not (
            _I_FULL_YEAR.search(t) or len(_I_DIGIT1.findall(t)) >= 4):
        # a two-digit year ("eighty-eight", "88", "ninety") is never guessed or sent: ask for the full year
        return {"status": "invalid"} if y is not None or _I_NUMW.search(t) else {"status": "none"}
    if y is None:
        return {"status": "none"}
    fmt = q.get("wire_format") or "%Y"
    w = str(int(y))
    if fmt not in ("%Y", "", "digits"):
        try:
            w = wire_date(datetime.date(int(y), 1, 1), fmt)
        except Exception:
            w = str(int(y))
    return _i_done(q, w)


def _i_answer_alnum(q, text, frag):
    a = parse_alnum(text) or ""
    if not a:
        return {"status": "none"}
    fmt = q.get("wire_format") or "upper_nospace"
    if fmt == "as_is":
        a = (text or "").strip()
    n = int(q.get("length") or 0)
    if n and len(a) < n:
        merged = re.sub(r"\s", "", frag or "") + a
        if len(merged) == n:
            return _i_done(q, merged)
        if len(merged) < n:
            return {"status": "incomplete", "frag": merged}
        return {"status": "invalid"}
    if n and len(a) > n:
        if _i_is_last_n(q):
            return _i_done(q, a[-n:])
        return {"status": "invalid"}
    return _i_done(q, a if fmt == "as_is" else _i_fit(q, a))


def _i_fit(q, a):
    """A code parsed without separators, split again to fit the Spec pattern ("LS62QT" -> "LS6 2QT"): one space or
    hyphen at the first position (from the right) that makes the whole value match; else unchanged."""
    if not q.get("pattern") or _i_pattern_ok(q, a):
        return a
    for sep in (" ", "-"):
        for i in range(len(a) - 1, 0, -1):
            if _i_pattern_ok(q, a[:i] + sep + a[i:]):
                return a[:i] + sep + a[i:]
    return a


def id_answer(q, text, frag, today):
    """q = Spec identity question. -> {"status": "complete", "wire": str} | {"status": "incomplete", "frag": str}
    | {"status": "invalid"} | {"status": "none"}. Never 'complete' unless wire matches q.pattern/length."""
    try:
        kind = (q or {}).get("kind") or "text"
        text = text or ""
        frag = frag or ""
        if kind == "date":
            return _i_answer_date(q, text, frag, today)
        if kind == "digits":
            return _i_answer_digits(q, text, frag)
        if kind == "year":
            return _i_answer_year(q, text, frag, today)
        if kind == "alnum":
            return _i_answer_alnum(q, text, frag)
        w = text.strip().strip(".!?,").strip()
        if not w:
            return {"status": "none"}
        return _i_done(q, w)
    except Exception:
        return {"status": "none"}


def _i_v(res, key):
    v = (res or {}).get(key)
    if v is None:
        return ""
    v = str(v).strip()
    if v.lower() in _I_NONE:
        return ""
    return v


def _i_int(v):
    try:
        return int(float(v))
    except Exception:
        return None


def verify_class(res):
    """res = {"s","verified","left","all","hint","err"} raw strings ('pending' = absent), optional "prev_left" ->
    'all_done' | 'verified' | 'hint:<value>' | 'wrong' | 'unreadable' | 'lockout' | 'transport_fail'."""
    try:
        s = _i_v(res, "s").lower()
        if not s:
            return "transport_fail"
        err = _i_v(res, "err").lower()
        left = _i_int(_i_v(res, "left"))
        prev = _i_int(_i_v(res, "prev_left"))
        hint = _i_v(res, "hint")
        ver = _i_v(res, "verified").lower()
        allv = _i_v(res, "all").lower()
        ok = s in ("true", "1", "yes", "ok", "success")
        if "lock" in err or "too many" in err or (left is not None and left <= 0 and ver != "true"):
            return "lockout"
        if hint and hint.lower() not in ("false", "0"):
            return "hint:" + hint
        if ok:
            if ver == "true" or (not ver and not err):
                if allv == "true":
                    return "all_done"
                return "verified"
            return "wrong"
        if re.search(r"(format|read|parse|invalid|unreadable|not a (valid )?date|iso|yyyy|must be|digits)", err):
            return "unreadable"
        if left is not None and prev is not None and left < prev:
            return "wrong"
        if re.search(r"(wrong|incorrect|does not match|doesn't match|mismatch)", err):
            return "wrong"
        return "unreadable"
    except Exception:
        return "transport_fail"


def id_model(q, val, done, frag, today):
    """A model-read identity answer (the extraction's normalised u_val: YYYY-MM-DD, YYYY, digits, upper-case code,
    or the words as said) validated against q like a parsed one. {"status": "none"} when it is missing or does not
    fit (the caller then parses the words). Never 'complete' unless the value passes the same checks."""
    try:
        kind = (q or {}).get("kind") or "text"
        v = str(val or "").strip()
        if not v or done == "none":
            return {"status": "none"}
        if kind == "date":
            m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", v)
            if not m or done == "partial":
                return {"status": "none"}
            dd = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if today is not None and not (today.year - 120 <= dd.year and dd <= today):
                return {"status": "none"}
            return _i_done(q, _i_date_wire(q, dd.year, dd.month, dd.day))
        if kind == "year":
            if not re.match(r"^\d{4}$", v) or done == "partial":
                return {"status": "none"}
            if today is not None and not (today.year - 120 <= int(v) <= today.year):
                return {"status": "none"}
            return _i_answer_year(q, v, "", today)
        if kind == "digits":
            d = _i_digits_only(v)
            return _i_answer_digits(q, d, frag) if d and len(d) * 2 >= len(re.sub(r"\s", "", v)) else {"status": "none"}
        if kind == "alnum":
            a = re.sub(r"[^A-Za-z0-9]", "", v).upper()
            return _i_answer_alnum(q, a, frag) if a else {"status": "none"}
        w = v.strip(".!?,").strip()
        return _i_done(q, w) if w and done != "partial" else {"status": "none"}
    except Exception:
        return {"status": "none"}
