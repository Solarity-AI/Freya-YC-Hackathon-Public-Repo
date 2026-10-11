"""Phase machine, negotiation, outcome resolution, rendering and the ctl entry point (docs/CONTRACTS.md C.5-C.8).
Owner: agent 2.

Rules: Python 3.8 syntax; stdlib only; no double curly braces; private helpers prefixed _b_; main() never raises.

CONTRACT NOTE (simplest readings chosen where docs/CONTRACTS.md is open; also logged in docs/contract-issues.md):
- st is stored as JSON written with indent=0 so nested objects never put two closing braces next to each other
  (the platform's template engine might see them); it is still plain JSON for every reader.
- read_result() takes an optional tool_fallback flag. The brain uses the tool-level flattened key
  (<tool>_response.data.<leaf>) only for read tools (products): for verify and write tools a tool-level key can be
  stale from an earlier call of the same tool and would give a false result.
- The C.6 "neutral re-ask" is used after interjections for every pending offer except the first ask, the vague-date
  ask and the read-back question, which are repeated exactly.
- A failed add_note (one node per product) is skipped and the chain continues; promise/transfer/callback failures
  use the next unrolled node, then an honest close (C.8).
- On a transfer, schedule_callback or account failure after the last try the call closes with recording.on_all_failed
  as call situation (service error), or third_party.situations.no_callback for a callback.
- Products mentioned by name in a turn (spoken form, type words, display digits) receive a proposal or product-scoped
  intent; without a mention it applies to the current product, or to every open product at the combined ask.
- First ctl entry (phase OPEN) is the reply to ask #1 (C.7): RP starts with asks = 1.
"""
import json
import re
import datetime
from .cal import parse_now, prepare, eval_date_rule, spoken_date, wire_date, wire_time, is_bd, next_bd, prev_bd
from .cal import iso, from_iso, callback_check, _c_DAYS, _c_MONTHS
from .parse import parse_amount, parse_date, parse_day_and_time, yes_no, match_any, last_clause, norm, is_question
from .parse import has_completed_payment, too_much, asks_less
from .ident import rp_classify, id_answer, verify_class, id_model
from .locale import lang_of, date_phrase, money_digits, weekday_index, and_word

_B_NONE = ("", "pending", "none", "null", "undefined", "nan")
_B_SENSORS = ("u_text", "u_act", "u_topic", "u_date", "u_amt", "u_time", "u_ans")
# LIVE 2026-10-11: writing "" to an enum-typed extraction variable is "rejected by schema validation" and the stale
# value stays. Reset enum sensors to their always-present neutral value instead (u_act has "unclear", u_topic
# ends with "none"; the brain treats both like "").
_B_RESET = dict(u_act="unclear", u_topic="none", u_done="none", u_dkind="none", u_dwhich="bare", u_kind="none")
_B_RDATA = "_response.data."  # flattened api-result variable infix: <node|tool>_response.data.<leaf>


def _b_neutral(v, name):
    v = _b_s(v).strip().lower()
    return "" if v == _B_RESET.get(name) else v
_B_STAGE = {"RP": "rp", "TP": "tp", "ID": "id", "NEG": "neg", "CONF": "conf"}
_B_MAX_TURNS = 40
_B_MAX_READBACKS = 4
# Longest customer text (per sensor) the parsers see. A spoken turn is far shorter (1500 chars is about 100 s of
# speech); the cap bounds the per-turn regex cost in the time-limited code node whatever the transcript holds.
_B_MAX_TEXT = 1500
_B_PH = re.compile(r"<(v:[A-Za-z_]\w*|f:[A-Za-z_][\w.]*|[a-z_]+)>", re.A)  # re.A: \w is [A-Za-z0-9_]
_B_ALL = re.compile(r"\b(all of them|them all|all three|all four|all five|all the (products|accounts|loans|cards|debts)"
                    r"|both|each|every one|everything|the lot|the rest|for all|all together|altogether)\b")
_B_FUTURE = re.compile(r"\b(will|i'll|ill|going to|gonna|tomorrow|next|tonight|later|can pay|could pay|shall)\b")
_B_TALK = re.compile(r"\b(talk|speak|call|calling|hang up|leave me alone|bother|conversation|phone)\b")
_B_AGENT_Q = re.compile(r"\bare you (a |an )?(real|human|person|robot|bot|machine|ai|computer)\b")
_B_REFUSE = re.compile(r"\b(no|not|won't|wont|will not|don't|dont|do not|refuse|rather not|not going to"
                       r"|none of your business|not telling|not giving|why should i|can't tell|cannot tell"
                       r"|no way|forget it|i decline|not comfortable)\b")
# (?<!\s): a whitespace-led separator is tried only where its whitespace run starts (a later start in the same run
# has the same continuation, so the splits are unchanged; retrying every position was quadratic on long gaps)
_B_CLAUSE = re.compile(r"(?:,?(?<!\s)\s+\bbut\b\s+|;\s*|\.\s+|,\s+(?:and\s+)?(?=(?:i|i'm|i'll|i will|i can|not|the)\b)"
                       r"|(?<!\s)\s+\bwhereas\b\s+|(?<!\s)\s+\band\b\s+"
                       r"(?=(?:i'm|i am|i'll|i will|i can't|i cannot|i won't|not)\b))")
_B_NEGCL = re.compile(r"\b(not|no|can't|cannot|won't|will not|don't|do not|refuse|never)\b")
_B_DUNNO = re.compile(r"\b(don't know|do not know|dunno|no idea|not sure|no clue|can't say|cannot say|who knows)\b")
_B_PAY = re.compile(r"\b(pay|paying|settle|cover|money|owe|debt)\b")
_B_WHYQ = re.compile(r"\b(what is (this|it) (about|regarding|for)|what's (this|it) (about|regarding|for)|why"
                     r"|what do you want|what('s| is) the (reason|matter)|regarding what|what for|reason)\b")


# ----------------------------------------------------------------------------------------------- small helpers
def _b_s(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def _b_cap(v):
    """A sensor string cut to _B_MAX_TEXT characters, at a space near the cut so no word or number is split."""
    if not isinstance(v, str) or len(v) <= _B_MAX_TEXT:
        return v
    cut = v[:_B_MAX_TEXT]
    sp = cut.rfind(" ", _B_MAX_TEXT - 80)
    return cut[:sp] if sp > 0 else cut


def _b_has(v):
    return _b_s(v).strip().lower() not in _B_NONE


def _b_int(v, dflt=None):
    try:
        return int(float(_b_s(v).strip()))
    except Exception:
        return dflt


def _b_cents(v):
    """Money value (number or string) -> integer cents, or None."""
    try:
        if v is None or isinstance(v, bool):
            return None
        if isinstance(v, int):
            return v * 100
        if isinstance(v, float):
            return int(round(v * 100.0))
        s = re.sub(r"[^0-9.\-]", "", _b_s(v))
        m = re.match(r"^(-?)(\d*)(?:\.(\d*))?$", s)
        if not m or not (m.group(2) or m.group(3)):
            return None
        whole = int(m.group(2) or "0")
        frac = (m.group(3) or "")
        c = whole * 100 + int((frac + "00")[:2])
        if len(frac) > 2 and frac[2] >= "5":
            c += 1
        return -c if m.group(1) else c
    except Exception:
        return None


def _b_dec(rspec):
    if isinstance(rspec, dict):
        return rspec
    t = _b_s(rspec).strip()
    if t[:1] == "\x7b":
        return json.loads(t)
    return json.loads(bytes.fromhex(t).decode("utf-8"))


def _b_load_st(raw):
    if isinstance(raw, dict):
        return raw
    try:
        if _b_has(raw):
            st = json.loads(_b_s(raw))
            if isinstance(st, dict):
                return st
    except Exception:
        pass
    return {}


def _b_dump(st):
    return json.dumps(st, indent=0, separators=(",", ":"), sort_keys=True)


def _b_copy(x):
    return json.loads(json.dumps(x))


def _b_lc(text):
    return last_clause(text or "") or (text or "")       # last_clause / norm never raise (parse catches all)


def _b_norm(text):
    return norm(text or "")


def _b_join(parts):
    out = []
    for p in parts:
        p = re.sub(r"\s+", " ", _b_s(p)).strip()
        if p and (not out or p != out[-1]):
            out.append(p)
    return " ".join(out).strip()


def _b_and(items, lang="en"):
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " " + and_word(lang) + " " + items[-1]


def _b_grounded(slot, text):
    """A slot value is used only when its tokens also occur in u_text (C.5 step 3)."""
    if not _b_has(slot):
        return False
    st = re.findall(r"[a-z0-9]+", _b_norm(slot))
    tt = set(re.findall(r"[a-z0-9]+", _b_norm(text)))
    if not st or not tt:
        return False
    digits = [t for t in st if t.isdigit()]
    if any(d not in tt and d not in "".join(sorted(tt)) for d in digits):
        if not all(d in re.sub(r"\D", "", _b_norm(text)) for d in digits):
            return False
    hit = sum(1 for t in st if t in tt)
    return hit * 10 >= len(st) * 6


# ----------------------------------------------------------------------------------------------- rendering
def _b_money(cents, spec):
    if cents is None:
        return ""
    neg = cents < 0
    cents = abs(int(cents))
    s = money_digits(cents, lang_of(spec))
    cur = (spec or {}).get("bank", {}).get("currency", {}) or {}
    pos = cur.get("position", "none")
    sym = _b_s(cur.get("symbol"))
    if pos == "before" and sym:
        # a letter code is a word of its own ("USD 348"); a sign is not ("$348")
        s = sym + (" " if sym[-1:].isalnum() else "") + s
    elif pos == "after":
        if cur.get("word"):
            s = s + " " + cur.get("word")
        elif sym:
            s = s + (" " if sym[:1].isalnum() else "") + sym
    elif pos == "none" and cur.get("word"):
        s = s + " " + cur.get("word")
    return ("-" if neg else "") + s


def _b_date_obj(v):
    if isinstance(v, datetime.date):
        return v
    return from_iso(_b_s(v)[:10])                      # from_iso never raises (None on bad input)


_B_ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def _b_field_text(v, spec, today):
    """A raw API field spoken in the call language: an ISO date as the spoken date, a fractional amount with the
    language's marks (2 decimals when it has cents), anything else as it is."""
    if isinstance(v, float):
        return money_digits(int(round(v * 100)), lang_of(spec))
    t = _b_s(v)
    if _B_ISO_DAY.fullmatch(t[:10]) and (len(t) == 10 or t[10:11] in ("T", " ")):
        d = from_iso(t[:10])
        if d is not None:
            return date_phrase(d, today or d, lang_of(spec))
    return t


def render(template, ctx):
    """Render a Spec line (B.2 placeholders). Unknown placeholder -> removed. Never raises."""
    try:
        return re.sub(r"(?<![\d.,])\b1 days\b", "1 day", _b_render(template, ctx or {}, 0))
    except Exception:
        try:
            return re.sub(r"\s+", " ", _B_PH.sub("", _b_s(template))).strip()
        except Exception:
            return ""


def _b_render(template, ctx, depth):
    spec = ctx.get("spec") or {}
    call = ctx.get("call") or {}
    prod = ctx.get("prod") or {}
    today = ctx.get("today")

    def money_of(key, pkey):
        v = ctx.get(key)
        if v is None and prod:
            v = prod.get(pkey)
        return _b_money(v, spec) if v is not None else ""

    def date_of(key, pkey):
        v = ctx.get(key)
        if v is None and prod and pkey:
            v = prod.get(pkey)
        d = _b_date_obj(v)
        if d is None:
            return ""
        return date_phrase(d, today or d, lang_of(spec))

    def rep(m):
        k = m.group(1)
        if k.startswith("v:"):
            return _b_s(call.get(k[2:], ""))
        if k.startswith("f:"):
            return _b_field_text((prod.get("f") or {}).get(k[2:], ""), spec, today)
        if k == "bank":
            return _b_s(spec.get("bank", {}).get("name", ""))
        if k == "self":
            return _b_s(spec.get("bank", {}).get("assistant_self", "")).replace(
                "<bank>", _b_s(spec.get("bank", {}).get("name", "")))
        if k == "customer":
            if depth > 2:
                return ""
            return _b_render(spec.get("addressing", {}).get("customer", ""), ctx, depth + 1)
        if k == "product":
            if depth > 2 or not prod:
                return ""
            tdef = (spec.get("products", {}).get("types", {}) or {}).get(prod.get("type", ""))
            tpl = tdef.get("spoken", "") if tdef else spec.get("products", {}).get("unknown_type_spoken", "")
            sub = dict(ctx)
            return _b_render(tpl, sub, depth + 1)
        if k == "amount":
            return money_of("amount", "due")
        if k == "floor":
            return money_of("floor", "floor")
        if k == "past_due":
            return money_of("past_due", "due")
        if k == "rest":
            if ctx.get("rest") is not None:
                return _b_money(ctx.get("rest"), spec)
            if prod and ctx.get("amount") is not None:
                return _b_money(max(0, (prod.get("due") or 0) - ctx.get("amount")), spec)
            return ""
        if k == "date":
            return date_of("date", "")
        if k == "deadline":
            return date_of("deadline", "dead")
        if k == "days_late":
            v = ctx.get("days_late")
            if v is None and prod:
                v = prod.get("dl")
            return _b_s(v)
        if k == "time":
            v = ctx.get("time")
            if isinstance(v, int):
                return wire_time(v, "%H:%M")
            return _b_s(v)
        if k == "items":
            return _b_s(ctx.get("items", ""))
        return ""

    out = _B_PH.sub(rep, _b_s(template))
    out = re.sub(r"\s+", " ", out).strip()
    out = re.sub(r" ([.,?!])", r"\1", out)  # whitespace is single spaces here (a \s+ form backtracks)
    return out


# ----------------------------------------------------------------------------------------------- amounts / outcome
def eval_amount(rule, prod, st):
    """Spec AmountRule -> integer cents for product `prod` (B.5)."""
    try:
        return _b_amount(rule or {}, prod or {}, st or {}, 0)
    except Exception:
        return (prod or {}).get("due") or 0


def _b_amount(rule, prod, st, depth):
    k = rule.get("kind", "full")
    full = prod.get("due") or 0
    if k == "full":
        return full
    if k == "floor":
        f = prod.get("floor")
        return min(f, full) if f is not None else full
    if k == "field":
        v = _b_cents((prod.get("f") or {}).get(rule.get("field", "")))
        return v if v is not None else full
    if k == "percent_of_full":
        pct = float(rule.get("pct", 100))
        exact = full * pct / 100.0
        rnd = rule.get("rounding", "half_up")
        base = int(exact)
        if rnd == "ceil":
            return base + (1 if exact > base else 0)
        if rnd == "floor":
            return base
        return int(exact + 0.5)
    if k == "fixed":
        v = _b_cents(rule.get("value"))
        return v if v is not None else full
    if k in ("min", "max") and depth < 6:
        vals = [_b_amount(a, prod, st, depth + 1) for a in rule.get("args", []) or []]
        if not vals:
            return full
        return min(vals) if k == "min" else max(vals)
    if k == "floor_if_too_much_else_full":
        if prod.get("tm"):
            f = prod.get("floor")
            return min(f, full) if f is not None else full
        return full
    return full


def _b_psit(spec, p):
    if p.get("sit"):
        return p["sit"]
    if p.get("rec"):
        return ""
    return spec.get("outcomes", {}).get("unresolved_product_situation", "")


def _b_phase_default(spec, st):
    ph = st.get("ph", "OPEN")
    if ph in ("OPEN", "RP"):
        return spec.get("right_party", {}).get("on_unresolved", "")
    if ph == "TP":
        return spec.get("third_party", {}).get("situations", {}).get("no_callback", "")
    if ph == "ID":
        return spec.get("identity", {}).get("on_declined", "")
    return ""


def _b_outcome_sit(spec, st):
    prods = st.get("prods") or []
    xf = st.get("xfer") or {}
    csit = st.get("csit") or ""
    rec = any(p.get("rec") for p in prods)
    if not csit and not xf.get("sit") and not rec and not prods:
        d = _b_phase_default(spec, st)
        if d:
            return d
    for row in spec.get("outcomes", {}).get("precedence", []) or []:
        when = row.get("when", "")
        use = row.get("use", "")
        ok = False
        if when == "transfer_done":
            ok = bool(xf.get("sit")) and not xf.get("failed")
        elif when == "any_promise_recorded":
            ok = rec
        elif when == "call_situation":
            ok = bool(csit)
        elif when.startswith("all_products:"):
            s = when.split(":", 1)[1]
            ok = bool(prods) and all(_b_psit(spec, p) == s for p in prods)
        elif when.startswith("any_product:"):
            s = when.split(":", 1)[1]
            ok = any(_b_psit(spec, p) == s for p in prods)
        elif when == "else":
            ok = True
        if not ok:
            continue
        if use == "transfer_situation":
            return xf.get("sit", "")
        if use == "call_situation":
            return csit
        if use.startswith("situation:"):
            return use.split(":", 1)[1]
        if use.startswith("first_product_excluding:"):
            excl = use.split(":", 1)[1].split(",")
            for p in prods:
                s = _b_psit(spec, p)
                if s and s not in excl:
                    return s
            if prods:
                return _b_psit(spec, prods[0]) or spec.get("outcomes", {}).get("unresolved_product_situation", "")
            return spec.get("outcomes", {}).get("unresolved_product_situation", "")
    return _b_phase_default(spec, st) or spec.get("outcomes", {}).get("unresolved_product_situation", "")


def resolve_outcome(spec, st):
    """-> (co, cr, cmode) from spec.outcomes.precedence over the call state (B.3)."""
    try:
        sid = _b_outcome_sit(spec, st or {})
        sit = (spec.get("situations") or {}).get(sid) or {}
        co = _b_s(sit.get("outcome", ""))
        cr = _b_s(sit.get("reason", ""))
        if co in (spec.get("outcomes", {}).get("reasonless_outcomes") or []):
            cr = ""
        return co, cr, ("r" if cr else "n")
    except Exception:
        return "", "", "n"


def _b_node(W, node):
    """Wiring node; a compact node {tool, bf: [fields]} (bundle.compact_wiring) is expanded by naming convention."""
    try:
        n = ((W or {}).get("nodes") or {}).get(node)
        if not n:
            return dict()
        if "bf" not in n:
            return n
        tool = n.get("tool", "")
        roles = ((W.get("roles") or {}).get(tool) or {}).get("res") or {}
        full = {"tool": tool, "body": dict(), "res": dict(), "res_leaf": dict(roles)}
        for f in n.get("bf") or []:
            full["body"][f] = "b_" + node + "_" + f
        for role in roles:
            full["res"][role] = "r_" + node + "_" + role
        return full
    except Exception:
        return dict()


# ----------------------------------------------------------------------------------------------- tool results
def read_result(vars, wiring, node, role, tool_fallback=True):
    """Mapped r_<node>_<role>, then '<node>_response.data.<leaf>', then '<tool>_response.data.<leaf>', else 'pending'."""
    try:
        n = _b_node(wiring, node)
        var = (n.get("res") or {}).get(role) or ("r_" + node + "_" + role)
        v = vars.get(var)
        if _b_has(v):
            return _b_s(v)
        leaf = (n.get("res_leaf") or {}).get(role)
        if not leaf:
            leaf = ((wiring.get("roles") or {}).get(n.get("tool", ""), {}).get("res") or {}).get(role, role)
        for key in (node + _B_RDATA + leaf, node + "_response." + leaf):
            if _b_has(vars.get(key)):
                return _b_s(vars.get(key))
        if tool_fallback and n.get("tool"):
            key = n.get("tool") + _B_RDATA + leaf
            if _b_has(vars.get(key)):
                return _b_s(vars.get(key))
        return "pending"
    except Exception:
        return "pending"


_B_LITWORDS = ("True", "False", "None", "true", "false", "null")
_B_LITNUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _b_lit(s):
    """Parse a JSON or Python-repr literal string (dict/list/str/num/True/False/None) without eval."""
    s = _b_s(s).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    pos = [0]

    def ws():
        while pos[0] < len(s) and s[pos[0]] in " \t\r\n":
            pos[0] += 1

    def val():
        ws()
        ch = s[pos[0]]
        if ch in "[(":
            close = "]" if ch == "[" else ")"
            pos[0] += 1
            out = []
            ws()
            if s[pos[0]] == close:
                pos[0] += 1
                return out
            while True:
                out.append(val())
                ws()
                if s[pos[0]] == ",":
                    pos[0] += 1
                    ws()
                    if s[pos[0]] == close:
                        pos[0] += 1
                        return out
                    continue
                if s[pos[0]] == close:
                    pos[0] += 1
                    return out
                raise ValueError("list")
        if ch == "\x7b":
            pos[0] += 1
            out = dict()
            ws()
            if s[pos[0]] == "\x7d":
                pos[0] += 1
                return out
            while True:
                k = val()
                ws()
                if s[pos[0]] != ":":
                    raise ValueError("colon")
                pos[0] += 1
                out[_b_s(k)] = val()
                ws()
                if s[pos[0]] == ",":
                    pos[0] += 1
                    ws()
                    if s[pos[0]] == "\x7d":
                        pos[0] += 1
                        return out
                    continue
                if s[pos[0]] == "\x7d":
                    pos[0] += 1
                    return out
                raise ValueError("dict")
        if ch in "'\"":
            q = ch
            pos[0] += 1
            buf = []
            while s[pos[0]] != q:
                if s[pos[0]] == "\\":
                    pos[0] += 1
                    e = s[pos[0]]
                    buf.append({"n": "\n", "t": "\t"}.get(e, e))
                else:
                    buf.append(s[pos[0]])
                pos[0] += 1
            pos[0] += 1
            return "".join(buf)
        # match at pos: slicing s[pos:] per token made long literals quadratic
        t = next((w for w in _B_LITWORDS if s.startswith(w, pos[0])), None)
        if t is None:
            m = _B_LITNUM.match(s, pos[0])
            if not m:
                raise ValueError("token")
            t = m.group(0)
        pos[0] += len(t)
        if t in ("True", "true"):
            return True
        if t in ("False", "false"):
            return False
        if t in ("None", "null"):
            return None
        return float(t) if ("." in t or "e" in t or "E" in t) else int(t)

    try:
        return val()
    except Exception:
        return None


def read_products(vars, wiring, node):
    """Products list from a list, JSON string, python-repr string or flattened keys -> list of dicts."""
    try:
        n = _b_node(wiring, node)
        tool = n.get("tool", "")
        leaf = (n.get("res_leaf") or {}).get("products") or (
            (wiring.get("roles") or {}).get(tool, {}).get("res") or {}).get("products", "products")
        var = (n.get("res") or {}).get("products") or ("r_" + node + "_products")
        cands = [vars.get(var), vars.get(node + _B_RDATA + leaf), vars.get(tool + _B_RDATA + leaf)]
        for v in cands:
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
            if isinstance(v, dict):
                return [v]
            if _b_has(v):
                lit = _b_lit(v)
                if isinstance(lit, list):
                    return [x for x in lit if isinstance(x, dict)]
                if isinstance(lit, dict):
                    if isinstance(lit.get(leaf), list):
                        return [x for x in lit.get(leaf) if isinstance(x, dict)]
                    return [lit]
        for prefix in (var, node + _B_RDATA + leaf, tool + _B_RDATA + leaf):
            rows = dict()
            pat = re.compile("^" + re.escape(prefix) + r"[.\[](\d+)\]?\.(.+)$")
            for k in list(vars.keys()):
                m = pat.match(_b_s(k))
                if m:
                    rows.setdefault(int(m.group(1)), dict())[m.group(2)] = vars.get(k)
            if rows:
                return [rows[i] for i in sorted(rows)]
        return []
    except Exception:
        return []


# ----------------------------------------------------------------------------------------------- context
def dated_spec(spec, today):
    """Spec.dated: [{from, until?, path, value}] - a rule that changes on an effective date. Every entry in force
    on `today` (from <= today < until) sets the JSON pointer `path` of a copy of the Spec to `value` (later `from`
    wins). The Spec itself is not changed. A bad entry is skipped."""
    t = iso(today)
    ds = sorted([d for d in spec.get("dated") or [] if isinstance(d, dict)
                 and _b_s(d.get("from")) <= t < (_b_s(d.get("until")) or "9")], key=lambda d: _b_s(d.get("from")))
    if not ds:
        return spec
    spec = _b_copy(spec)
    for d in ds:
        try:
            ks = [k.replace("~1", "/").replace("~0", "~") for k in _b_s(d.get("path")).split("/")[1:]]
            cur = spec
            for k in ks[:-1]:
                cur = cur[int(k)] if isinstance(cur, list) else cur[k]
            cur[int(ks[-1]) if isinstance(cur, list) else ks[-1]] = _b_copy(d.get("value"))
        except Exception:
            continue
    return spec


def _b_ctx(R, st, inp):
    spec = R.get("spec") or {}
    W = R.get("wiring") or {}
    call = dict((inp or {}).get("call") or {})
    nowvar = spec.get("call_variables", {}).get("now", "now")
    today, now_min = parse_now(call.get(nowvar, ""))
    if today is None:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", _b_s(call.get(nowvar, "")))
        try:
            today = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            today = datetime.date(2000, 1, 3)
        now_min = 0
    spec = dated_spec(spec, today)
    cal = prepare(spec.get("calendar") or {}, today)
    c = {"R": R, "S": spec, "W": W, "st": st, "inp": inp or {}, "call": call,
         "res": (inp or {}).get("results") or {}, "today": today, "now": now_min, "cal": cal,
         "w": dict(), "say": [], "nx": "", "co": None}
    _b_sens(c, (inp or {}).get("sensors") or {})
    return c


def _b_sens(c, raw):
    sensors = {k: _b_cap(v) for k, v in raw.items()}
    c["sens"] = sensors
    c["text"] = _b_s(sensors.get("u_text", ""))
    c["raw"] = c["text"]
    c["act"] = _b_neutral(sensors.get("u_act", ""), "u_act")
    c["topic"] = _b_neutral(sensors.get("u_topic", ""), "u_topic")
    c["lang"] = lang_of(c.get("S"))
    c["mv"] = None
    _B_RAW["g"], _B_RAW["r"] = c["text"], ""
    if c["lang"] != "en":
        # another call language: the extraction's English rendering (u_en) feeds the English parsers as a fallback
        # and cross-check; the typed model-read values (u_val, u_amt, u_dkind ...) are primary (_b_mv_*), and the
        # Spec's keywords are matched on the customer's own words too (_b_kw)
        en = _b_s(sensors.get("u_en", "")).strip()
        if en and _b_has(en):
            c["text"] = en
        elif money_digits(100000, c["lang"])[1:2] == ".":
            # no rendering: the customer's own words, with the language's 1.250,50 written as 1250.50 for the parsers
            t = re.sub(r"\b\d{1,3}(?:\.\d{3})+\b(?!\.\d)", lambda m: m.group(0).replace(".", ""), c["text"])
            c["text"] = re.sub(r"\b(\d+),(\d\d?)\b(?![.,]\d)", r"\1.\2", t)
        _B_RAW["g"], _B_RAW["r"] = c["text"], c["raw"]
        mv = {k: _b_mv_val(sensors, k) for k in _B_MV}
        c["mv"] = mv
        kind = mv.get("kind")
        if kind in _B_KIND_ACT and (kind != "smalltalk" or not (mv.get("amt") or mv.get("dkind"))):
            c["act"] = _B_KIND_ACT[kind]


# typed model-read sensors of a non-English call (render.extraction_schema), read as c["mv"][<name without u_>]
_B_MV = ("val", "done", "amt", "dkind", "dval", "dwhich", "kind")
_B_SENS_X = ("u_en", "u_val", "u_done", "u_dkind", "u_dval", "u_dwhich", "u_kind")
_B_KIND_ACT = dict(yes="yes", no="no", refusal="refuse", question="question", smalltalk="chatter_only")
_B_RAW = dict(g="", r="")                               # this turn's text for the parsers (g) and the raw words (r)


def _b_sensor_names(spec):
    """The sensor variables ctl reads and resets: the extra typed ones only exist in a non-English workflow."""
    return _B_SENSORS + (_B_SENS_X if lang_of(spec) != "en" else ())


def _b_mv_val(sensors, k):
    """The typed value of sensor u_<k> ('' when it holds nothing)."""
    v = sensors.get("u_" + k, "")
    v = _b_neutral(v, "u_" + k) if ("u_" + k) in _B_RESET else _b_s(v).strip()
    return v if _b_has(v) else ""


def _b_rctx(c, **kw):
    d = {"spec": c["S"], "call": c["call"], "today": c["today"]}
    d.update(kw)
    return d


_B_PROD = "<product>"


def _b_r(c, template, **kw):
    if "prod" not in kw and _B_PROD in _b_s(template):
        # an intent line names the product under discussion (the pending offer's, or the only one)
        ps = c["st"].get("prods") or []
        k = (c["st"].get("offer") or {}).get("k", -1)
        k = 0 if len(ps) == 1 else k
        if isinstance(k, int) and 0 <= k < len(ps):
            kw["prod"] = ps[k]
        elif ps:                                        # no one product under discussion: name the open ones
            open_ = [p for p in ps if _b_unresolved(p)] or ps
            template = _b_s(template).replace(_B_PROD, _b_and([_b_pname(c, p) for p in open_], lang_of(c["S"])))
    return render(template, _b_rctx(c, **kw))


def _b_pname(c, p):
    """The spoken name of product p (the <product> placeholder)."""
    return _b_r(c, _B_PROD, prod=p)


def _b_line(c, slot, **kw):
    return _b_r(c, (c["S"].get("lines") or {}).get(slot, ""), **kw)


def _b_interp(c, key, dflt=None):
    return (c["S"].get("interpretation") or {}).get(key, dflt)


def _b_listen(c, ph, parts):
    st = c["st"]
    st["ph"] = ph
    key = _B_STAGE.get(ph, "safe")
    node = (c["W"].get("listen") or {}).get(key) or (c["W"].get("listen") or {}).get("safe", "s_safe")
    st["await"] = node
    c["nx"] = node
    carry = st.pop("carry", None) or []
    parts = list(parts)
    note = c.pop("wdm", "")
    if note and parts and note not in (st.get("wdn") or []):
        # the weekday / relative day the customer named does not fit the date: say so (once per call) before the
        # question that reads it back
        st.setdefault("wdn", []).append(note)
        parts.insert(len(parts) - 1, note)
    c["say"] = list(carry) + parts
    return True


def _b_route_api(c, node, vals):
    """Route to api node `node`: write its b_* (vals: {role or '@field': value}) and preset its r_* to pending."""
    W = c["W"]
    n = _b_node(W, node)
    roles = ((W.get("roles") or {}).get(n.get("tool", ""), {}).get("req") or {})
    body = n.get("body") or {}
    for role, val in vals.items():
        field = role[1:] if role.startswith("@") else roles.get(role)
        var = body.get(field) if field else None
        if var and var not in ("co", "cr"):
            c["w"][var] = _b_s(val)
    for role, var in (n.get("res") or {}).items():
        c["w"][var] = "pending"
    c["st"]["await"] = node
    c["nx"] = node
    return True


def _b_success(c, node, raw):
    W = c["W"]
    tool = _b_node(W, node).get("tool", "")
    succ = (W.get("success") or {}).get(tool) or {"kind": "bool_true", "values": ["true", "True"]}
    if succ.get("kind") == "http_ok_no_error":
        r = c["res"].get(node) or {}
        return not _b_has(r.get("err")) and any(_b_has(v) for v in r.values())
    vals = [_b_s(v).lower() for v in succ.get("values") or ["true"]]
    return _b_s(raw).strip().lower() in vals


def _b_node_res(c, node):
    return c["res"].get(node) or {}


# ----------------------------------------------------------------------------------------------- required sentences
def _b_intent_req(c, it):
    """Required sentences triggered by intent `it` (trigger on_intent:<id>)."""
    return _b_req(c, ["on_intent:" + it.get("id", "")])


_B_PROMN = re.compile(r"\b(this|that|the|your) promise\b( is| was| has)?", re.I)
_B_PLUR = {"this": "these", "that": "those", " is": " are", " was": " were", " has": " have"}


def _b_plural(text):
    """'confirming this promise' -> 'confirming these promises' once several promises were recorded."""
    def rep(m):
        d = _B_PLUR.get(m.group(1).lower(), m.group(1).lower())
        d = d.capitalize() if m.group(1)[0].isupper() else d
        return d + " promises" + _B_PLUR.get((m.group(2) or "").lower(), "")
    return _B_PROMN.sub(rep, text)


def _b_req(c, triggers, persist=True, n=0):
    st = c["st"]
    said = st.setdefault("said", [])
    out = []
    for rs in c["S"].get("required_sentences") or []:
        if rs.get("trigger") not in triggers:
            continue
        rid = rs.get("id", "")
        if rs.get("once", True) and rid in said:
            continue
        line = _b_r(c, rs.get("text", ""))
        # several promises: plural, except a sentence the brief dictates word for word (verbatim)
        out.append(_b_plural(line) if n > 1 and not rs.get("verbatim") else line)
        if persist and rs.get("once", True):
            said.append(rid)
    return out


_B_STOP = frozenset(("the", "and", "you", "your", "for", "this", "that", "with", "our", "are", "can", "could", "would",
               "will", "please", "or", "a", "an", "to", "of", "is", "it", "be", "on", "in", "at", "i", "we"))


def _b_ckey(sentence):
    w = re.findall(r"[a-z0-9][a-z0-9.,]*", _b_s(sentence).lower())
    return [x.strip(".,") for x in w if x.strip(".,") and x.strip(".,") not in _B_STOP]


def _b_dupe(sentence, seen):
    k = _b_ckey(sentence)
    if not k:
        return False
    ks = set(k)
    for o in seen:
        if k == o:
            return True
        os_ = set(o)
        if len(ks) >= 3 and len(os_) >= 3 and (len(ks & os_) * 4 >= len(ks | os_) * 3 or ks <= os_):
            return True
    return False


def _b_compose(c):
    parts = []
    seen = []
    for p in c["say"]:
        p = _b_s(p).strip()
        if not p or p in " ".join(parts):
            continue
        keep = []
        for snt in _b_sentences(p):
            if _b_dupe(snt, seen) and not snt.endswith("?"):
                continue
            seen.append(_b_ckey(snt))
            keep.append(snt)
        if keep:
            parts.append(" ".join(keep))
    return _b_join(parts)


# ----------------------------------------------------------------------------------------------- intents
def _b_intents(c, stage):
    S = c["S"]
    text = c["text"]
    topic = c["topic"]
    tie = _b_interp(c, "intent_tie", []) or []
    out = []
    agent_q = bool(_B_AGENT_Q.search(_b_norm(text)))
    for idx, it in enumerate(S.get("intents") or []):
        if stage not in (it.get("scope") or []):
            continue
        kw = _b_kw(it, text)
        tp = topic == _b_s(it.get("id")).lower()
        a = it.get("action") or {}
        kind = a.get("kind", "")
        if not (kw or tp) and kind == "resolve_product" and _b_is_paid_intent(S, a) and _B_PAIDOBJ.search(_b_norm(text)):
            # "I paid it last week, didn't you get it?": a completed payment of this debt, in words the keywords miss
            tp = has_completed_payment(text)
        if not (kw or tp):
            continue
        if kind == "resolve_product" and _b_is_paid_intent(S, a) and _b_interp(c, "paid_requires_completed_tense", True):
            if _b_paid_future(c, it, text, kw):
                continue
            if not kw and not has_completed_payment(text):
                continue
        if kind == "offer_transfer" and _b_interp(c, "hardship_requires_cause", True) and not kw and not (
                tp and _B_CAUSE.search(_b_norm(text))):
            # the extracted topic alone is not hardship ("I can't afford it"); a named cause is (job, illness, death)
            continue
        if kw and not tp and kind in ("offer_transfer", "close_now") and _b_kw_void(it, text, kind == "close_now"):
            # "I'm not sick", "I'm sick of these calls", "her husband died last year": the keyword is not the claim
            continue
        if kw and not tp and kind in ("ask_then_transfer", "transfer", "answer_continue") and (
                (c["act"] == "proposal" and (c["sens"].get("u_date") or c["sens"].get("u_amt")))
                or topic in [_b_s(x.get("id")).lower() for x in S.get("intents") or []]):
            # a word the keywords share ("my advisor says I can pay Friday") does not interrupt a proposal or
            # override another intent the extractor named
            continue
        if kind == "count_then_close" and _b_interp(c, "refuse_to_talk_requires_talk_words", True):
            if not kw and not _B_TALK.search(_b_norm(text)):
                continue
        if kind in ("ask_then_transfer", "transfer") and ((agent_q and not tp) or _b_req_withdrawn(it, text)):
            continue
        if kind in ("ask_then_transfer", "transfer") and tp and not kw and _b_asks_lowest(text):
            # "You tell me what the lowest amount is": a question about the amount, not a request for a new plan
            # or a person (the extracted topic alone does not transfer it; plan / instalment words still do)
            continue
        rank = tie.index(it.get("id")) if it.get("id") in tie else 999
        out.append((-int(it.get("precedence", 0)), rank, idx, it))
    out = _b_closure_dispute(c, stage, text, out, tie)
    out.sort(key=lambda x: (x[0], x[1], x[2]))
    return [x[3] for x in out]


# words that make a question about paying less a request for a new plan ("lower monthly instalments", "a payment
# plan", "spread it over time", "smaller payments over time")
_B_PLANW = re.compile(r"\b(?:plans?|instal+ments?|monthly|restructur\w*|spread\w*|over time|reschedul\w*|"
                      r"smaller payments|every month|per month|a month)\b")


def _b_asks_lowest(text):
    """A question asking for the lowest / least / minimum amount (or to pay less) with no plan or instalment words."""
    return asks_less(text) and not _B_PLANW.search(_b_norm(text))


# a transfer request said only to be turned down: "I don't need a person", "no need for an agent", "not asking
# for a payment plan" (negation before it in its clause), or taken back after it ("... a person? Never mind.")
_B_RQNEG = re.compile(r"\b(?:don't|do not|dont|doesn't|does not|didn't|did not|no|not|never|won't|wouldn't)\s+"
                      r"(?:\w+\s+){0,2}?(?:need|want|ask(?:ing)? for|looking for|require|after)\b|\bno need\b|\bwithout\b"
                      r"|\bnot (?:asking|looking|after)\b")
_B_RQSPLIT = re.compile(r"[,.;!?]|\bbut\b")


def _b_spans(it, lc):
    spans = []
    for p in (it.get("keywords") or []):
        try:
            spans += [(m.start(), m.end()) for m in re.finditer(p, lc, re.I)]
        except Exception:
            continue
    return spans


# a cause of hardship named in the turn (an extracted hardship topic needs one when hardship_requires_cause)
_B_CAUSE = re.compile(r"\b(?:jobs?|work|employ\w*|unemploy\w*|redundan\w*|laid off|let go|fired|sacked|income|ill|illness"
                      r"|unwell|sick(?! of| and tired)|hospital\w*|surgery|operation|diagnos\w*|cancer|medical|disab\w*"
                      r"|injur\w*|accident|bereave\w*|funeral|died|death|passed(?: away)?)\b")
# a keyword hit that is negated ("not sick", "never been ill"), an idiom ("sick of"), or (close_now) a relative's
# death ("her husband died", "my father passed")
_B_KWNEG = re.compile(r"(?:\bnot|\bnever|n't)\s+(?:(?:been|be|really|that|so|very|too|feeling|even)\s+)?$")
_B_IDIOM = re.compile(r"\s*(?:of\b|and tired\b|to death\b)")
_B_RELD = re.compile(r"\b(?:my|his|her|their|our|your)(?:\s+\w+){1,2}\s+(?:(?:has|had|just)\s+)?$")


def _b_kw_void(it, text, rel):
    lc = " ".join(_b_s(text).lower().split())
    sp = _b_spans(it, lc)
    if not sp:
        return False
    for a, b in sp:
        h = _B_RQSPLIT.split(lc[:a])[-1]
        if not (_B_KWNEG.search(h) or re.search(r"\b(?:not|never)\b", lc[a:b]) or _B_IDIOM.match(lc[b:])
                or (rel and _B_RELD.search(h))):
            return False
    return True


def _b_req_withdrawn(it, text):
    """Every mention of a transfer intent's keywords (or of a person/agent) is negated or taken back."""
    lc = _b_s(text).lower()
    spans = _b_spans(it, lc)
    if not spans:
        spans = [(m.start(), m.end()) for m in _B_INSIST.finditer(lc)]
    if not spans:
        return False
    for a, b in spans:
        head = _B_RQSPLIT.split(lc[:a])[-1]
        if not (_B_RQNEG.search(head) or _B_WITHDRAW.search(_b_norm(lc[b:]))):
            return False
    return True


def _b_withdrawn_rest(c, stage):
    """None when the turn withdraws no transfer request; else the turn without the withdrawn request and its
    'never mind' words ('' when nothing else is left)."""
    text = c["text"]
    its = []
    for it in c["S"].get("intents") or []:
        a = it.get("action") or {}
        if a.get("kind") in ("ask_then_transfer", "transfer") and stage in (it.get("scope") or []) and (
                _b_kw(it, text) or c["topic"] == _b_s(it.get("id")).lower()) and _b_req_withdrawn(it, text):
            its.append(it)
    if not its:
        return None
    keep = []
    for sg in re.split(r"[,.;!?]+", text):
        n = _b_norm(sg)
        if not re.search(r"[a-z0-9]", n) or any(_b_kw(it, sg) for it in its) or _B_INSIST.search(n):
            continue
        if (_B_WITHDRAW.search(n) and len(n.split()) <= 4) or re.match(r"^\W*(actually|ok|okay|so|well|no)\W*$", n):
            continue
        keep.append(sg.strip())
    return ", ".join(keep)


# filler words a Spec keyword regex rarely allows between its words ("lower monthly instalments")
_B_FILLER = re.compile(r"\b(?:monthly|weekly|fortnightly|yearly|regular|really|actually|just|simply|honestly)\s+")


_B_NOT = re.compile(r"\b(is|are|was|were|do|does|did|has|have|had)n't\b")


def _b_kw(it, text):
    """The intent's keyword regexes match the turn, also with filler words taken out."""
    kws = it.get("keywords") or []
    if not kws:
        return False
    if match_any(kws, text):
        return True
    if _B_RAW["r"] and text == _B_RAW["g"] and match_any(kws, _B_RAW["r"]):
        return True                                     # the Spec's own-language keywords on the customer's words
    lc = _b_lc(text)
    t2 = _B_NOT.sub(r"\1 not", _B_FILLER.sub("", lc))
    return t2 != lc and match_any(kws, t2)


def _b_paid_future(c, it, text, kw):
    """A paid claim with a future marker ('I have paid some and will pay the rest tomorrow') is not paid, unless the
    future clauses are about other products than the paid one ('I already paid the card. The other one I can pay
    tomorrow.')."""
    if not _B_FUTURE.search(_b_norm(_b_lc(text))):
        return False
    if not kw or len(c["st"].get("prods") or []) <= 1:
        return True
    parts = [x for x in _B_CLAUSE.split(_b_s(text).lower()) if x and x.strip()]
    paid = [x for x in parts if _b_kw(it, x)]
    fut = [x for x in parts if _B_FUTURE.search(_b_norm(x))]
    if not paid or any(x in fut for x in paid):
        return True
    pm = {j for x in paid for j in _b_mentions(c, x)}
    fms = [set(_b_mentions(c, x)) for x in fut]
    return not (pm and all(fm and not (fm & pm) for fm in fms))


_B_PAIDOBJ = re.compile(r"\b(?:paid|sent|transferred|settled|cleared)\s+(?:it|this|that|them|everything|the (?:money|payment"
                        r"|amount|balance|debt|whole thing|lot|full amount)|already|in full|it all)\b"
                        r"|^\W*(?:i|we) (?:have |'ve )?(?:already |just )?paid\W*(?:\.|$)")
_B_CLOSED_PAID = re.compile(r"\bpaid (?:(?:it|that|this|them) |(?:the|my) \w+ )?off\b")
_B_CLOSED_WORD = re.compile(r"\b(?:closed|cancell?ed|shut down)\b")
# the closure is about the account or product: an object after the verb, or a subject before it
_B_CLOSED_OBJ = re.compile(r"\b(?:closed|cancell?ed|shut down)\s+(?:it|that|this|them|the (?:account|card|loan|debt)|my \w+)\b"
                           r"|\b(?:it|that|this|they|account|card|loan|debt)\s+(?:was|were|is|has been|have been|got)\s+"
                           r"(?:closed|cancell?ed|shut down|paid off)\b")
_B_RECENT = re.compile(r"\b(today|this morning|yesterday|last night|just now|an hour ago|earlier today)\b")


def _b_closed_product(c, text, n):
    """'I closed that card' / 'the account was closed years ago' - not 'my shop closed last month'."""
    if _B_CLOSED_OBJ.search(n):
        return True
    for part in _B_CLAUSE.split(_b_s(text).lower()):
        if part and _B_CLOSED_WORD.search(_b_norm(_b_lc(part))) and _b_mentions(c, part):
            return True
    return False


def _b_dispute_intent(c, stage):
    S = c["S"]
    sits = S.get("situations") or {}
    best = None
    for idx, it in enumerate(S.get("intents") or []):
        a = it.get("action") or {}
        if a.get("kind") != "resolve_product" or stage not in (it.get("scope") or []) or _b_is_paid_intent(S, a):
            continue
        sit = sits.get(a.get("situation", "")) or {}
        if sit.get("outcome") != _b_np_outcome(S):
            continue
        tag = (_b_s(sit.get("reason")) + " " + _b_s(sit.get("note_reason")) + " " + _b_s(it.get("id"))).lower()
        if "disput" in tag:
            return idx, it
        if best is None:
            best = (idx, it)
    return best


def _b_closure_dispute(c, stage, text, out, tie):
    """Interpretation past_closure_is_dispute: 'I paid that off last year' / 'I closed that card' is a dispute, not
    a payment of this past-due amount."""
    if not _b_interp(c, "past_closure_is_dispute", False):
        return out
    n = _b_norm(_b_lc(text))
    if not (_B_CLOSED_PAID.search(n) or _b_closed_product(c, text, n)) or _B_RECENT.search(n) or _B_FUTURE.search(n):
        return out
    got = _b_dispute_intent(c, stage)
    if got is None:
        return out
    idx, dit = got
    S = c["S"]
    keep = [x for x in out if not ((x[3].get("action") or {}).get("kind") == "resolve_product"
                                   and _b_is_paid_intent(S, x[3].get("action") or {}))]
    if not any(x[3] is dit for x in keep):
        rank = tie.index(dit.get("id")) if dit.get("id") in tie else 999
        keep.append((-int(dit.get("precedence", 0)), rank, idx, dit))
    return keep


def _b_intents_on(c, stage, text):
    """Intents matched on a piece of the turn (keywords only, no extracted topic)."""
    saved = (c["text"], c["topic"])
    c["text"], c["topic"] = text, ""
    try:
        return _b_intents(c, stage)
    finally:
        c["text"], c["topic"] = saved


def _b_sit_field(spec, sid, key, dflt):
    return _b_s(((spec.get("situations") or {}).get(sid) or {}).get(key)) or dflt


def _b_np_outcome(spec):
    """The tool API's 'no promise' outcome value: the outcome of the Spec's exhausted-negotiation situation."""
    ex = (spec.get("negotiation") or {}).get("on_exhausted", "") or "S_REFUSED_EXHAUSTED"
    return _b_sit_field(spec, ex, "outcome", "") or _b_sit_field(spec, "S_DISPUTE", "outcome", "no_promise")


def _b_is_paid_intent(S, a):
    """The intent resolves a product as already paid: the canonical S_PAID situation, or a situation that shares
    its outcome / note reason (values come from the Spec, not from fixed enum spellings)."""
    sid = a.get("situation", "")
    sit = (S.get("situations") or {}).get(sid) or {}
    po = _b_sit_field(S, "S_PAID", "outcome", "paid")
    pn = _b_sit_field(S, "S_PAID", "note_reason", "paid")
    return sid == "S_PAID" or sit.get("outcome") == po or (
        sit.get("note_reason") == pn and sit.get("outcome") != _b_np_outcome(S))


def _b_split_intents(c, hits):
    """-> (answer_continue says, action intents (excluding too_much), too_much flag)."""
    ans, acts, tm = [], [], False
    for it in hits:
        k = (it.get("action") or {}).get("kind", "")
        if k == "answer_continue":
            say = _b_r(c, it["action"].get("say", ""))
            if re.search(r"\brecorded\b", say, re.I) and not any(p.get("rec") for p in c["st"].get("prods") or []):
                continue
            ans.append(say)
            ans.extend(_b_intent_req(c, it))
        elif k == "too_much":
            tm = True
        else:
            acts.append(it)
    return ans, acts, tm


# ----------------------------------------------------------------------------------------------- closing / plans
def _b_notes_apply(c):
    N = c["S"].get("notes") or {}
    if not N.get("enabled"):
        return False
    xf = c["st"].get("xfer") or {}
    if xf.get("sit") and not xf.get("failed") and (N.get("skip_if_transfer", True) or xf.get("suppress")):
        return False
    return True


def _b_note_items(c, have):
    """Plan items for notes of products without a recorded/planned promise."""
    S, W, st = c["S"], c["W"], c["st"]
    items = []
    if not _b_notes_apply(c):
        return items
    N = S.get("notes") or {}
    sits = S.get("situations") or {}
    if N.get("scope", "product") == "product":
        rows = (W.get("api") or {}).get("note") or []
        for j, p in enumerate(st.get("prods") or []):
            if p.get("rec") or p.get("noted") or j in have or j >= len(rows) or not rows[j]:
                continue
            reason = (sits.get(_b_psit(S, p)) or {}).get("note_reason", "")
            if reason:
                items.append({"t": "note", "j": j, "n": rows[j][0], "reason": reason})
    else:
        rows = (W.get("api") or {}).get("note_call") or []
        if rows and not st.get("cnoted") and not any(p.get("rec") for p in st.get("prods") or []):
            reason = (sits.get(_b_outcome_sit(S, st)) or {}).get("note_reason", "")
            if reason:
                items.append({"t": "cnote", "n": rows[0], "reason": reason})
    return items


def _b_close(c, pre=None):
    """Close flow: notes (if any apply), transfer (if pending), then s_bye."""
    st = c["st"]
    if pre:
        st.setdefault("bye_pre", []).extend([p for p in pre if p])
    for p in st.get("prods") or []:
        if p.get("ag") and not p.get("rec") and _b_interp(c, "agreed_before_terminal", "drop") == "drop":
            p["ag"] = None
    items = _b_note_items(c, [])
    xf = st.get("xfer") or {}
    if xf.get("sit") and not xf.get("done") and not xf.get("failed"):
        rows = (c["W"].get("api") or {}).get("xfer") or []
        t = int(xf.get("try", 0))
        if t < len(rows):
            items.append({"t": "xfer", "n": rows[t], "try": t})
        else:
            xf["failed"] = 1
            st["bye_pre"] = []
            st["csit"] = (c["S"].get("recording") or {}).get("on_all_failed", "") or st.get("csit", "")
            items = _b_note_items(c, [])
    st["ph"] = "BYE" if not items else st.get("ph_close", "NOTES")
    return _b_emit_plan(c, items)


def _b_bye_target(c):
    W = c["W"]
    if W.get("bye_mode") == "apinode":
        _, _, cm = c["co"] or resolve_outcome(c["S"], c["st"])
        api = W.get("api") or {}
        return api.get("close_r", "a_close_r") if cm == "r" else api.get("close_n", "a_close_n")
    return W.get("bye", "s_bye")


def _b_hyp(c, items):
    """Hypothetical state where every planned item succeeds (for co/cr and the bye line)."""
    h = _b_copy(c["st"])
    for it in items:
        t = it.get("t")
        if t == "promise":
            h["prods"][it["j"]]["rec"] = 1
        elif t == "note":
            h["prods"][it["j"]]["noted"] = 1
        elif t == "xfer":
            h.setdefault("xfer", dict())["done"] = 1
        elif t == "cb":
            h.setdefault("cb", dict())["done"] = 1
    return h


def _b_bye_say(c, hyp):
    S, st = c["S"], c["st"]
    parts = list(st.get("carry") or []) + list(st.get("bye_pre") or [])
    cb = hyp.get("cb") or {}
    if cb.get("done") and not cb.get("failed"):
        parts.append(_b_r(c, S.get("third_party", {}).get("booked_line", ""), date=cb.get("d"), time=cb.get("t")))
    prods = hyp.get("prods") or []
    nrec = sum(1 for p in prods if p.get("rec"))
    parts += _b_rec_lines(c, prods)
    saved = st.get("said")
    st["said"] = list(saved or [])
    trig = []
    if nrec and (not st.get("smsd") or any(p.get("rec") and not p.get("ann") for p in prods)):
        # once after all creates: not again when _b_post already said it for these promises
        trig.append("after_promise_recorded")
    sid = _b_outcome_sit(S, hyp)
    sits = []
    for s in [hyp.get("csit"), (hyp.get("xfer") or {}).get("sit")] + [p.get("sit") for p in prods] + [sid]:
        if s and s not in sits:
            sits.append(s)
    trig.extend(["on_situation:" + s for s in sits])
    trig.append("before_close")
    co = ((S.get("situations") or {}).get(sid) or {}).get("outcome", "")
    if co:
        trig.append("on_outcome:" + co)
    parts.extend(_b_req(c, trig, True, nrec))
    st["said"] = saved if saved is not None else []
    CL = S.get("closing") or {}
    per = (CL.get("per_situation") or {}).get(sid)
    if per:
        parts.append(_b_r(c, per))
    # closing.no_goodbye: the brief's own line for this situation is all that is said (e.g. condolences only)
    good = "" if sid in (CL.get("no_goodbye") or []) else _b_r(c, CL.get("goodbye", ""))
    body = [p for p in parts if p and p != good]
    gl = (_b_sentences(good) or [""])[-1]
    gk = _b_ckey(gl)
    if gk and any(_b_ckey(x) == gk for b in body for x in _b_sentences(b)):
        # a line already says goodbye (a brief's own closing sentence): that goodbye moves to the very end
        body = [" ".join(x for x in _b_sentences(b) if _b_ckey(x) != gk) for b in body]
        good = gl
    c["say"] = body + [good]
    carry = st.pop("carry", None)
    if carry:
        # keep the carried lines for a re-plan after a failed write, which rebuilds this goodbye
        st["bye_pre"] = list(carry) + list(st.get("bye_pre") or [])


def _b_rec_lines(c, prods):
    """'Your promise is recorded.' / the failed-promise line, for products not announced yet."""
    REC = c["S"].get("recording") or {}
    out = []
    nrec = sum(1 for p in prods if p.get("rec") and not p.get("ann"))
    if nrec:
        out.append(_b_r(c, REC.get("recorded_multi") if nrec > 1 and REC.get("recorded_multi") else REC.get("recorded", "")))
    failed = [p for p in prods if p.get("failed") and not p.get("ann")]
    if failed and nrec:
        # one sentence naming every failed product (separate sentences would be dropped as near-duplicates)
        line = _b_r(c, REC.get("failed_item") or "I'm sorry, I could not record the promise for your <product>.",
                    prod=failed[0])
        first = _b_pname(c, failed[0])
        if len(failed) > 1 and first and first in line:
            line = line.replace(first, _b_and([_b_pname(c, p) for p in failed], lang_of(c["S"])), 1)
        out.append(line)
    elif failed:
        out.append(_b_r(c, REC.get("failed", "")))
    return out


def _b_post(c):
    """interpretation.after_record = ask_anything_else: the promises are written; say so (with the required
    sentences) and ask whether there is anything else, instead of closing in the same turn."""
    st = c["st"]
    ps = st.get("prods") or []
    if st.pop("cont", None) and any(_b_unresolved(p) for p in ps):
        # one product at a time: its promise is recorded; say so and go on with the next product (the text
        # message sentence waits until every promise is created)
        st["post"] = 0
        pre = list(st.pop("bye_pre", None) or []) + _b_rec_lines(c, ps)
        for p in ps:
            if p.get("rec") or p.get("failed"):
                p["ann"] = 1
        st["plan"], st["pm"] = [], []
        st["offer"] = {"kind": "", "k": -1}
        return _b_next(c, pre)
    st["post"] = 2
    st["smsd"] = 1
    pre = list(st.pop("bye_pre", None) or []) + _b_rec_lines(c, ps) + _b_req(
        c, ["after_promise_recorded"], True, sum(1 for p in ps if p.get("rec")))
    for p in ps:
        if p.get("rec") or p.get("failed"):
            p["ann"] = 1
    q = _b_line(c, "anything_else") or "Is there anything else I can help you with?"
    st["offer"] = {"kind": "post", "k": -1, "line": q}
    st["plan"], st["pm"] = [], []
    return _b_listen(c, "NEG", pre + [q])


def _b_emit_plan(c, items):
    """C.8 write chain: b_* for every planned node, r_* pending, wn_* links, bye say, co/cr/cmode, nx = first."""
    st, W = c["st"], c["W"]
    post = st.get("post") == 1                         # its plan holds promises only (notes wait, _b_write)
    if post and not items:
        if any(p.get("rec") for p in st.get("prods") or []):
            return _b_post(c)
        st["post"] = 0
        return _b_close(c, [])
    hyp = _b_hyp(c, items)
    co, cr, cm = resolve_outcome(c["S"], hyp)
    c["co"] = (co, cr, cm)
    _b_bye_say(c, hyp)
    bye = _b_bye_target(c)
    nodes = []
    for it in items:
        n = it["n"]
        vals = _b_item_vals(c, it)
        _b_route_api(c, n, vals)
        nodes.append(n)
    plan = nodes + ["" if post else bye]
    chain = bool(W.get("chain", True))
    for i, n in enumerate(nodes):
        c["w"]["wn_" + n] = plan[i + 1] if chain else ""
    st["plan"] = plan
    st["pm"] = items
    st["await"] = plan[0]
    c["nx"] = plan[0]
    if not items:
        st["ph"] = "BYE"
        st["plan"] = []
        st["pm"] = []
    return True


def _b_wire_amount(c, tool, field, cents):
    wk = (c["W"].get("wire") or {}).get(tool + "." + field) or {}
    if int(wk.get("scale", 1) or 1) == 100:
        return str(int(cents))
    return "%d.%02d" % (int(cents) // 100, int(cents) % 100)


def _b_wire_date(c, tool, field, d):
    wk = (c["W"].get("wire") or {}).get(tool + "." + field) or {}
    fmt = wk.get("format") or "%Y-%m-%d"
    dd = _b_date_obj(d)
    if dd is None:
        return _b_s(d)
    return wire_date(dd, fmt)


def _b_wire_time(c, tool, field, m):
    wk = (c["W"].get("wire") or {}).get(tool + "." + field) or {}
    return wire_time(_b_int(m, 0), wk.get("format") or "%H:%M")


def _b_wire_dt(c, tool, d, m):
    """A date-time request field (role datetime): the day plus the booked minute of the day (0 = midnight)."""
    wk = (c["W"].get("wire") or {}).get(tool + "." + _b_field(c, tool, "datetime")) or {}
    dd = _b_date_obj(d)
    if dd is None:
        return _b_s(d)
    return wire_date(dd, wk.get("format") or "%Y-%m-%dT%H:%M:%S", _b_int(m, 0))


def _b_field(c, tool, role):
    return (((c["W"].get("roles") or {}).get(tool) or {}).get("req") or {}).get(role, role)


def _b_item_vals(c, it):
    st = c["st"]
    t = it.get("t")
    if t == "promise":
        p = st["prods"][it["j"]]
        tool = "create_promise"
        n = _b_node(c["W"], it["n"])
        tool = n.get("tool", tool)
        out = {"product": p.get("id", ""), "amount": _b_wire_amount(c, tool, _b_field(c, tool, "amount"), p["ag"][0]),
               "date": _b_wire_date(c, tool, _b_field(c, tool, "date"), p["ag"][1]),
               "datetime": _b_wire_dt(c, tool, p["ag"][1], 0)}
        pk = c["W"].get("pkind")
        if pk:
            a, due, fl = _b_int(p["ag"][0], 0), _b_int(p.get("due"), 0), p.get("floor")
            k = "min" if fl is not None and a == _b_int(fl, -1) else "part"
            if a >= due:
                k = "full"
            out["@" + pk["field"]] = pk.get(k) or pk.get("part") or pk.get("min") or pk.get("full")
        return out
    if t in ("note", "cnote"):
        vals = {"reason": it.get("reason", "")}
        if t == "note":
            vals["product"] = st["prods"][it["j"]].get("id", "")
        txt = (c["S"].get("notes") or {}).get("text", "")
        if txt:
            p = st["prods"][it["j"]] if t == "note" else None
            vals["text"] = _b_r(c, txt, prod=p) if p else _b_r(c, txt)
        else:
            vals["text"] = it.get("reason", "")        # no wording in the Spec: the note says its reason
        return vals
    if t == "xfer":
        return {"queue": (st.get("xfer") or {}).get("q", "")}
    if t == "cb":
        cb = st.get("cb") or {}
        n = _b_node(c["W"], it["n"])
        tool = n.get("tool", "schedule_callback")
        vals = {"date": _b_wire_date(c, tool, _b_field(c, tool, "date"), cb.get("d")),
                "time": _b_wire_time(c, tool, _b_field(c, tool, "time"), cb.get("t", 0)),
                "datetime": _b_wire_dt(c, tool, cb.get("d"), cb.get("t", 0))}
        return vals
    return {}


def _b_reconcile(c):
    """Re-entry with st.plan set: first non-success planned node (plan order) is the failed one (C.8).
    Without the chain only the first planned node ran (each api node returns to ctl)."""
    st, W = c["st"], c["W"]
    items = st.get("pm") or []
    chain = bool(W.get("chain", True))
    idx_fail = None
    done = 0
    for i, it in enumerate(items):
        r = _b_node_res(c, it["n"])
        if _b_success(c, it["n"], r.get("s", "pending")):
            _b_mark_done(c, it, r)
            done = i + 1
            if not chain:
                break
            continue
        idx_fail = i
        break
    rest = items[done:]
    if idx_fail is not None:
        failed = items[idx_fail]
        rest = items[idx_fail + 1:]
        repl = _b_on_fail(c, failed)
        rest = repl + rest
        if failed.get("t") == "promise" and not repl and st.get("post") != 1:
            have = [x.get("j") for x in rest if x.get("t") in ("note", "promise")]
            rest = rest + _b_note_items(c, have)
    elif not rest and W.get("bye_mode") == "listen" and (chain or st.get("ph") == "BYE") and st.get("post") != 1:
        # every planned node succeeded and the chain ended in s_bye, which already spoke: close (D.3)
        api = W.get("api") or {}
        co = resolve_outcome(c["S"], st)
        c["co"] = co
        st["plan"] = []
        st["pm"] = []
        st["ph"] = "CLOSE"
        c["nx"] = api.get("close_r", "a_close_r") if co[2] == "r" else api.get("close_n", "a_close_n")
        return None
    seen = []
    clean = []
    for it in rest:
        key = [it.get("t"), it.get("j"), it.get("n")]
        if key not in seen:
            seen.append(key)
            clean.append(it)
    return _b_emit_plan(c, clean)


def _b_mark_done(c, it, r):
    st = c["st"]
    t = it.get("t")
    if t == "promise":
        p = st["prods"][it["j"]]
        p["rec"] = 1
        p["pid"] = _b_s(r.get("pid", ""))
    elif t == "note":
        st["prods"][it["j"]]["noted"] = 1
    elif t == "cnote":
        st["cnoted"] = 1
    elif t == "xfer":
        st.setdefault("xfer", dict())["done"] = 1
    else:                                               # cb (plan items are promise/note/cnote/xfer/cb only)
        st.setdefault("cb", dict())["done"] = 1


def _b_on_fail(c, it):
    """-> replacement items for a failed planned item."""
    st, W, S = c["st"], c["W"], c["S"]
    t = it.get("t")
    api = W.get("api") or {}
    if t == "promise":
        j = it["j"]
        rows = (api.get("promise") or [])[j] if j < len(api.get("promise") or []) else []
        nt = it.get("try", 0) + 1
        tries = int((S.get("recording") or {}).get("tries", 2) or 1)
        if nt < tries and nt < len(rows):
            return [{"t": "promise", "j": j, "n": rows[nt], "try": nt}]
        p = st["prods"][j]
        p["failed"] = 1
        p["sit"] = (S.get("recording") or {}).get("on_all_failed", "")
        p["ag"] = None
        return []
    if t == "xfer":
        rows = api.get("xfer") or []
        nt = it.get("try", 0) + 1
        xf = st.setdefault("xfer", dict())
        xf["try"] = nt
        if nt < len(rows):
            return [{"t": "xfer", "n": rows[nt], "try": nt}]
        xf["failed"] = 1
        st["bye_pre"] = []
        st["csit"] = (S.get("recording") or {}).get("on_all_failed", "") or st.get("csit", "")
        return _b_note_items(c, [])
    if t == "cb":
        rows = api.get("cb") or []
        nt = it.get("try", 0) + 1
        cb = st.setdefault("cb", dict())
        if nt < len(rows):
            return [{"t": "cb", "n": rows[nt], "try": nt}]
        cb["failed"] = 1
        st["bye_pre"] = []
        st["csit"] = S.get("third_party", {}).get("situations", {}).get("no_callback", "")
        return []
    if t == "note":
        st["prods"][it["j"]]["note_failed"] = 1
        return []
    st["cnote_failed"] = 1                              # cnote: the only kind left
    return []


# ----------------------------------------------------------------------------------------------- RP / TP
def _b_name_tokens(c):
    out = []
    for v in c["S"].get("addressing", {}).get("name_vars") or []:
        if _b_has(c["call"].get(v)):
            out.append(_b_s(c["call"].get(v)))
    return out


def _b_rp_ask(c, first=False):
    RP = c["S"].get("right_party") or {}
    return _b_r(c, RP.get("ask") if first else (RP.get("reask") or RP.get("ask", "")))


def _b_close_now(c, it, pre):
    st = c["st"]
    a = it.get("action") or {}
    st["csit"] = a.get("situation", "") or st.get("csit", "")
    if ((c["S"].get("situations") or {}).get(st["csit"]) or {}).get("note_reason"):
        # a call-level close with a note reason (e.g. insolvency) is every open product's note reason too
        for p in st.get("prods") or []:
            if not p.get("rec"):
                p["sit"] = st["csit"]
    say = _b_r(c, a.get("say", ""))
    return _b_close(c, list(pre) + [say] + _b_intent_req(c, it))


# close_now intents found by what they close (id, situation, reason) when the Spec's keywords miss the wording
_B_CLOSE_TAG = {"deceased": re.compile(r"deceas|dead|death|died|passed"), "wrong_number": re.compile(r"wrong|unknown|number")}


def _b_close_intent(c, stage, kind):
    """The Spec's close_now intent for an ident close signal ("deceased" / "wrong_number"), or None."""
    S = c["S"]
    rx = _B_CLOSE_TAG.get(kind)
    for it in S.get("intents") or []:
        a = it.get("action") or {}
        if rx is None or a.get("kind") != "close_now" or stage not in (it.get("scope") or []):
            continue
        sit = (S.get("situations") or {}).get(a.get("situation", "")) or {}
        tag = " ".join((_b_s(it.get("id")), _b_s(a.get("situation")), _b_s(sit.get("reason")))).lower()
        if rx.search(tag):
            return it
    return None


def _b_rp_close(c, r, acts, stage):
    """A close_now intent of the turn (keywords / topic), else the one the ident close signal names; or None."""
    for it in acts:
        if (it.get("action") or {}).get("kind") == "close_now":
            return _b_close_now(c, it, [])
    it = _b_close_intent(c, stage, r.get("close", ""))
    return _b_close_now(c, it, []) if it is not None else None


def _b_rp_turn(c):
    S, st = c["S"], c["st"]
    RP = S.get("right_party") or {}
    rp = st.setdefault("rp", {"asks": 1})
    hits = _b_intents(c, "rp")
    ans, acts, _tm = _b_split_intents(c, hits)
    r = rp_classify(c["text"], c["act"], _b_name_tokens(c))
    cls = r.get("cls", "unclear")
    q = r.get("q", "")
    # a confirmed customer who mentions a death in the family or a wrong number is still the customer:
    # close_now intents (deceased / wrong number) apply only without a confirmation
    if cls != "confirm":
        done = _b_rp_close(c, r, acts, "rp")
        if done is not None:
            return done
    if c["topic"] in ("other_person", "unavailable") and cls != "confirm":
        cls = "third_party"
    hold = bool(r.get("hold")) or c["topic"] == "hold"
    if hold and cls != "confirm":
        st["rp"] = {"asks": 0, "restart": 1}
        return _b_listen(c, "RP", [_b_line(c, "hold")])
    if cls == "confirm":
        pre = list(ans)
        if q in ("who", "robot", "scam") and not ans:
            pre.append(_b_r(c, (RP.get("answers") or {}).get("who", "")))
        elif q == "why" and not ans:
            pre.append(_b_r(c, (RP.get("answers") or {}).get("why_confirmed")
                            or "I can explain once I have confirmed your identity."))
        pre += _b_stash_post(c)
        return _b_id_start(c, pre)
    if cls == "third_party" or (cls == "deny" and RP.get("bare_no", "third_party") == "third_party"):
        return _b_tp_enter(c, ans)
    if rp.get("restart"):
        st["rp"] = {"asks": 1}
        return _b_listen(c, "RP", ans + [_b_r(c, S.get("opening", {}).get("line", "")), _b_rp_ask(c, True)])
    pre = list(ans)
    if cls == "question" and not ans:
        A = RP.get("answers") or {}
        if q in ("who", "robot", "scam"):
            pre.append(_b_r(c, A.get("who", "")))
        elif q == "why":
            pre.append(_b_r(c, A.get("why", "")))
        else:
            pre.append(_b_r(c, A.get("other", "")))
    max_asks = int(RP.get("max_asks", 2) or 2)
    asks = int(rp.get("asks", 1))
    if asks >= max_asks:
        if (cls == "question" and _b_interp(c, "rp_question_after_last_ask") == "answer_and_allow_one_more"
                and not rp.get("extra")):
            rp["extra"] = 1
            return _b_listen(c, "RP", pre + [_b_rp_ask(c)])
        st["csit"] = RP.get("on_unresolved", "")
        return _b_close(c, [])
    if not (cls == "greeting" and asks == 1 and _b_interp(c, "rp_greeting_first_turn") == "reask_free"):
        rp["asks"] = asks + 1
    return _b_listen(c, "RP", pre + [_b_rp_ask(c)])


def _b_sentences(text):
    return [x for x in re.split(r"(?<=[.!?])\s+", _b_s(text).strip()) if x]


def _b_xparts(say):
    """Split an offer say into (lead sentences, question): 'I'm sorry to hear that. Would you like...?'."""
    ss = _b_sentences(say)
    if len(ss) >= 2 and ss[-1].endswith("?"):
        return " ".join(ss[:-1]), ss[-1]
    return "", " ".join(ss)


def _b_stash_post(c):
    """Before verification: remember a post-verification intent (hardship, paid, dispute, transfer) for after the
    statement. A hardship offer's sympathy sentence is said now, once; the offer question waits."""
    st = c["st"]
    out = []
    for it in _b_intents(c, "neg") + _b_intents(c, "conf"):
        a = it.get("action") or {}
        if a.get("kind") in ("offer_transfer", "resolve_product", "transfer"):
            if not st.get("stash"):
                st["stash"] = it.get("id", "")
                if a.get("kind") == "offer_transfer" and not st.get("symp"):
                    lead, _q = _b_xparts(_b_r(c, a.get("say", "")))
                    if lead:
                        st["symp"] = 1
                        out.append(lead)
            break
    return out


def _b_tp_enter(c, ans):
    st = c["st"]
    st["ph"] = "TP"
    st["tp"] = {"turns": 0, "outside": 0, "vague": 0, "idle": 0, "d": ""}
    return _b_tp_turn(c, first=True, pre=ans)


def _b_tp_close(c, pre, sit):
    c["st"]["csit"] = sit
    return _b_close(c, pre)


def _b_tp_turn(c, first=False, pre=None):
    S, st = c["S"], c["st"]
    TP = S.get("third_party") or {}
    cb = TP.get("callback") or {}
    sits = TP.get("situations") or {}
    tp = st.setdefault("tp", {"turns": 0, "outside": 0, "vague": 0, "idle": 0, "d": ""})
    tp["turns"] = int(tp.get("turns", 0)) + 1
    ans = list(pre or [])
    if TP.get("mode") == "close":
        # the brief never asks a third party anything and never books: one line, then the call ends
        return _b_tp_close(c, ans + [_b_r(c, TP.get("close_line") or TP.get("reach_ask", ""))], sits.get("no_callback", ""))
    if not first:
        hits = _b_intents(c, "tp")
        a2, acts, _tm = _b_split_intents(c, hits)
        ans += a2
        r = rp_classify(c["text"], c["act"], _b_name_tokens(c))
        done = _b_rp_close(c, r, acts, "tp")
        if done is not None:
            return done
        if r.get("hold") or c["topic"] == "hold":
            st["rp"] = {"asks": 0, "restart": 1}
            return _b_listen(c, "RP", [_b_line(c, "hold")])
    reach = _b_r(c, TP.get("reach_ask", "")) if first else _b_r(c, TP.get("reach_reask") or TP.get("reach_ask", ""))
    try:
        cal = c["cal"]
        r = parse_day_and_time(_b_lc(c["text"]), c["today"], c["now"], cal) or {}
    except Exception:
        r = {}
    tm = (r.get("time") or {})
    tk = tm.get("kind", "none")
    if r.get("date"):
        tp["d"] = r.get("date")
    dkind = r.get("date_kind", "none")
    if tk not in ("exact", "range") and _b_has(c["sens"].get("u_time")) and _b_grounded(c["sens"].get("u_time"), c["text"]):
        try:
            r2 = parse_day_and_time(c["sens"].get("u_time"), c["today"], c["now"], c["cal"]) or {}
            if (r2.get("time") or {}).get("kind") in ("exact", "range"):
                tm = r2.get("time")
                tk = tm.get("kind")
                if r2.get("date") and not tp.get("d"):
                    tp["d"] = r2.get("date")
        except Exception:
            pass
    budget = int(TP.get("turn_budget", 6) or 6)
    if tk in ("exact", "range"):
        d = _b_date_obj(tp.get("d")) or c["today"]
        cands = []
        if tk == "exact":
            cands = list(tm.get("alts") or []) or [tm.get("min")]      # parse_time sets min = alts[0]
        else:
            lo, hi = int(tm.get("lo", 0)), int(tm.get("hi", 0))
            m = lo + 15 if tm.get("lo_excl") else lo
            while m <= hi and len(cands) < 200:
                cands.append(m)
                m += 15
        got = None
        for m in cands:
            try:
                if m is not None and callback_check(c["cal"], cb, c["today"], c["now"], d, int(m)) == "ok":
                    got = int(m)
                    break
            except Exception:
                continue
        if got is not None:
            return _b_book(c, d, got, ans)
        if not tp.get("d") or not _b_tp_slot_ok(c, d, ""):
            # keep a day that can still hold a callback ("Tomorrow at 9." outside the window, then "Seven in the
            # evening." books tomorrow); forget a day that cannot
            tp["d"] = ""
        return _b_tp_outside(c, ans)
    dunno = bool(_B_DUNNO.search(_b_norm(c["text"]))) and not r.get("date") and tk not in ("part",)
    if not dunno and (tk in ("part", "vague") or dkind == "vague" or (tp.get("d") and r.get("date"))):
        if dkind == "past":
            tp["d"] = ""
            return _b_tp_outside(c, ans)
        if tp["turns"] >= budget:
            return _b_tp_close(c, ans, sits.get("no_callback", ""))
        d = _b_date_obj(tp.get("d"))
        time_ask = _b_r(c, TP.get("time_ask") or "What time would be best to reach <customer>?")
        if tk == "part" or (d is not None and tk == "none" and dkind != "vague"):
            # a day and/or a part of the day that can hold a callback: ask for the time (free, twice at most)
            if not _b_tp_slot_ok(c, d or c["today"], tm.get("part", "") if tk == "part" else ""):
                if d is not None and not _b_tp_slot_ok(c, d, ""):
                    tp["d"] = ""
                return _b_tp_outside(c, ans)
            if int(tp.get("tq", 0)) < 2:
                tp["tq"] = int(tp.get("tq", 0)) + 1
                if tp["tq"] > 1:
                    time_ask = _b_r(c, TP.get("time_reask") or "Could you give me an exact time?")
                return _b_listen(c, "TP", ans + [time_ask])
            return _b_tp_outside(c, ans)
        if int(tp.get("vague", 0)) < int(cb.get("vague_asks", 1) or 0):
            tp["vague"] = int(tp.get("vague", 0)) + 1
            return _b_listen(c, "TP", ans + [_b_r(c, TP.get("vague_line", ""))])
        if d is not None and int(tp.get("tq", 0)) < 1 and _b_tp_slot_ok(c, d, ""):
            tp["tq"] = 1
            return _b_listen(c, "TP", ans + [time_ask])
        return _b_tp_outside(c, ans)
    if tp["turns"] >= budget:
        return _b_tp_close(c, ans, sits.get("no_callback", ""))
    n = _b_norm(c["text"])
    if _B_PAY.search(n):
        return _b_listen(c, "TP", ans + [_b_r(c, TP.get("offer_to_pay_line", "")), _b_r(c, TP.get("reach_ask", ""))])
    if first:
        if not ans and "?" in c["text"] and _B_WHYQ.search(n):
            ans.append(_b_r(c, (S.get("right_party", {}).get("answers") or {}).get("why", "")))
        return _b_listen(c, "TP", ans + [reach])
    isq = "?" in c["text"]
    if ans or isq:
        if isq and not ans and _B_WHYQ.search(n):
            ans.append(_b_r(c, (S.get("right_party", {}).get("answers") or {}).get("why", "")))
        return _b_listen(c, "TP", ans + [reach])
    if _b_chatter(c) and int(tp.get("chat", 0)) < _B_CHAT_MAX:
        # small talk ("The traffic was a nightmare") is not a refusal to give a time: ask again, uncounted
        tp["chat"] = int(tp.get("chat", 0)) + 1
        tp["turns"] -= 1
        return _b_listen(c, "TP", ans + [reach])
    tp["idle"] = int(tp.get("idle", 0)) + 1
    if tp["idle"] >= 2:
        return _b_tp_close(c, ans, sits.get("no_callback", ""))
    return _b_listen(c, "TP", ans + [reach])


def _b_tp_outside(c, ans):
    S, st = c["S"], c["st"]
    TP = S.get("third_party") or {}
    tp = st["tp"]
    tp["outside"] = int(tp.get("outside", 0)) + 1
    lim = int((TP.get("callback") or {}).get("reask_limit", 1) or 0)
    if tp["outside"] > lim or tp["turns"] >= int(TP.get("turn_budget", 6) or 6):
        return _b_tp_close(c, ans, (TP.get("situations") or {}).get("no_callback", ""))
    return _b_listen(c, "TP", ans + [_b_r(c, TP.get("outside_line", "")), _b_r(c, TP.get("reach_reask", ""))])


_B_PARTS = {"morning": (360, 719), "afternoon": (720, 1079), "evening": (1080, 1380)}


def _b_tp_slot_ok(c, d, part):
    """True when some quarter-hour on day d (within the part of the day, if given) passes the callback check."""
    cb = (c["S"].get("third_party") or {}).get("callback") or {}
    lo, hi = _B_PARTS.get(part, (0, 1439))
    m = lo
    while m <= hi:
        try:
            if callback_check(c["cal"], cb, c["today"], c["now"], d, m) == "ok":
                return True
        except Exception:
            return True
        m += 15
    return False


def _b_book(c, d, m, ans):
    S, st, W = c["S"], c["st"], c["W"]
    rows = (W.get("api") or {}).get("cb") or []
    st["cb"] = {"d": iso(d), "t": int(m), "try": 0}
    st["csit"] = (S.get("third_party", {}).get("situations") or {}).get("callback", "")
    st.setdefault("bye_pre", []).extend(ans)
    st["ph"] = "WRITE"
    if not rows:
        st["cb"]["failed"] = 1
        st["csit"] = (S.get("third_party", {}).get("situations") or {}).get("no_callback", "")
        return _b_close(c, [])
    return _b_emit_plan(c, [{"t": "cb", "n": rows[0], "try": 0}])


# ----------------------------------------------------------------------------------------------- identity
def _b_q(c):
    qs = c["S"].get("identity", {}).get("questions") or []
    i = int(c["st"].get("id", {}).get("qi", 0))
    return qs[i] if 0 <= i < len(qs) else None


def _b_id_start(c, pre):
    st = c["st"]
    st["ph"] = "ID"
    st["id"] = {"qi": 0, "wrong": 0, "wq": {}, "hints": {}, "dec": {}, "expl": 0, "frag": "", "vi": 0, "turns": 0,
                "retry": 0, "ver": []}
    q = _b_q(c)
    if q is None:
        return _b_acct_start(c)
    return _b_listen(c, "ID", list(pre) + [_b_r(c, q.get("ask", ""))])


def _b_id_fail(c, sit, line_key="fail_line"):
    S, st = c["S"], c["st"]
    st["csit"] = sit
    line = _b_r(c, S.get("identity", {}).get(line_key, "")) if line_key else ""
    return _b_close(c, [line] if line else [])


def _b_qre(c, q):
    """Re-ask an identity question after a non-answer: the Spec's reask, else the ask without a thank-you lead-in."""
    if _b_has(q.get("reask")):
        return _b_r(c, q.get("reask"))
    return re.sub(r"^\s*(thank you|thanks)( very much)?[.!,]\s*", "", _b_r(c, q.get("ask", "")), flags=re.I)


def _b_id_turn(c):
    S, st = c["S"], c["st"]
    I = S.get("identity") or {}
    idn = st.setdefault("id", {"qi": 0, "wrong": 0, "wq": {}, "hints": {}, "dec": {}, "expl": 0, "frag": "",
                               "vi": 0, "turns": 0, "retry": 0, "ver": []})
    idn["turns"] = int(idn.get("turns", 0)) + 1
    q = _b_q(c)
    if q is None:
        return _b_acct_start(c)
    hits = _b_intents(c, "id")
    ans, acts, _tm = _b_split_intents(c, hits)
    if not int(idn.get("vi", 0)) and _B_NOTCUST.search(_b_norm(c["text"])):
        # "I am not Maria, I am her husband": not the customer after all; the third-party rules, not a decline
        return _b_tp_enter(c, ans)
    top = acts[0] if acts else None
    deflect = top is not None and _b_id_answer_wins(c, q, idn, top)
    if deflect:
        # "14 March 1988. What is this about?": the answer is given, so the deflection is not counted
        acts = [x for x in acts if (x.get("action") or {}).get("kind") != "count_then_close"]
        top = acts[0] if acts else None
    helped = st.pop("help", None)
    if helped and top is not None and (top.get("action") or {}).get("kind") == "ask_then_transfer" \
            and not _b_insists(c, None):
        top = None
    if top is not None and _b_id_scoped(c, top):
        # "Why should I tell you?" matched an id-scoped decline intent: the decline counter and its rules count it
        purpose = c["topic"] == "purpose_question" or rp_classify(c["text"], c["act"], []).get("q") == "why"
        say = _b_r(c, (top.get("action") or {}).get("say", ""))
        return _b_id_decline(c, q, idn, ans + ([say] if say else []) + _b_intent_req(c, top),
                             not purpose or (I.get("decline") or {}).get("purpose_question_counts", True))
    if top is not None:
        r = _b_dispatch_common(c, top, ans, verified=False)
        if r is not None:
            return r
    if helped and top is None and _b_insists(c, None):
        r = _b_human_transfer(c, ans)
        if r is not None:
            return r
    if idn["turns"] > int(I.get("turn_budget", 12) or 12):
        return _b_id_fail(c, I.get("on_declined", ""), None)
    post = [it for it in _b_intents(c, "neg") + _b_intents(c, "conf")]
    for it in post:
        if (it.get("action") or {}).get("kind") in ("offer_transfer", "resolve_product", "transfer"):
            if not st.get("stash"):
                st["stash"] = it.get("id", "")
            break
    r = rp_classify(c["text"], c["act"], [])
    qt = r.get("q", "")
    qkind = q.get("kind") or "text"
    am = {"status": "none"}
    if c.get("mv") is not None and c["act"] not in ("refuse", "question"):
        # a non-English call: the extraction's normalised answer first, validated like a parsed one
        am = id_model(q, c["mv"].get("val"), c["mv"].get("done"), idn.get("frag", ""), c["today"])
    if am.get("status") in ("complete", "incomplete"):
        a = am
    elif qkind in ("text", "alnum"):
        # a free-text / code answer accepts anything, so refusals, questions and chatter must be caught first
        n0 = _b_norm(c["text"])
        nonans = bool(qt) or c["topic"] == "purpose_question" or c["act"] in ("refuse", "no", "question") \
            or bool(_B_REFUSE.search(n0)) or bool(post) or _b_isq(c) or bool(_B_TALK.search(n0)) \
            or bool(_B_HOLDON.search(n0)) or bool(_B_EVADE.search(n0)) or bool(has_completed_payment(c["text"]))
        a = {"status": "none"}
        if not nonans:
            src = c["sens"].get("u_ans") if _b_grounded(c["sens"].get("u_ans"), c["text"]) else c["text"]
            a = id_answer(q, src, idn.get("frag", ""), c["today"]) or {}
            if qkind == "alnum" and a.get("status") == "complete":
                w = _b_s(a.get("wire"))
                ln = int(q.get("length", 0) or 0)
                if not (re.search(r"\d", w) or (q.get("pattern") and ln and len(w) == ln)):
                    a = {"status": "none"}
    else:
        a = id_answer(q, c["text"], idn.get("frag", ""), c["today"]) or {}
        if a.get("status") in ("none", None) and _b_grounded(c["sens"].get("u_ans"), c["text"]):
            a = id_answer(q, c["sens"].get("u_ans"), idn.get("frag", ""), c["today"]) or {}
    stt = a.get("status")
    key = q.get("key", "")
    if stt == "complete" and idn.get("hintwire") and _b_s(a.get("wire")) == idn.get("hintwire"):
        # the same value the service flagged with a hint: do not send it again
        return _b_listen(c, "ID", ans + [idn.get("hintsay") or _b_r(c, q.get("ask_full", "") or q.get("ask", ""))])
    if stt == "complete":
        idn["frag"] = ""
        idn["dec"][key] = 0
        if not ans and (qt == "why" or c["topic"] == "purpose_question" or (
                (deflect or "?" in c["text"]) and _B_WHYQ.search(_b_norm(c["text"])))):
            ans.append(_b_r(c, (I.get("decline") or {}).get("explain", "")))
        st["carry"] = ans
        return _b_verify_route(c, q, a.get("wire", ""))
    if stt == "incomplete":
        idn["frag"] = a.get("frag", "")
        line = _b_line(c, "continue_prompt") if q.get("kind") in ("digits", "alnum") else _b_r(c, q.get("ask_full", ""))
        return _b_listen(c, "ID", ans + [line])
    if stt == "invalid":
        idn["frag"] = ""
        return _b_listen(c, "ID", ans + [_b_r(c, q.get("ask_full", "") or q.get("ask", ""))])
    if helped:
        return _b_listen(c, "ID", ans + [_b_qre(c, q)])
    n = _b_norm(c["text"])
    D = I.get("decline") or {}
    purpose = c["topic"] == "purpose_question" or (qt == "why")
    if qt in ("robot", "scam", "who") and not purpose:
        if not ans:
            ans.append(_b_r(c, (S.get("right_party", {}).get("answers") or {}).get("who", "")))
        return _b_listen(c, "ID", ans + [_b_qre(c, q)])
    if post:
        return _b_listen(c, "ID", ans + [_b_line(c, "ack"), _b_qre(c, q)])
    refusal = c["act"] in ("refuse",) or bool(_B_REFUSE.search(n)) or (c["act"] == "no")
    if (purpose and D.get("purpose_question_counts", True)) or refusal:
        return _b_id_decline(c, q, idn, ans)
    return _b_listen(c, "ID", ans + [_b_qre(c, q)])


def _b_id_decline(c, q, idn, ans, count=True):
    """A declined security question: counted on the identity decline counter (decline_counting, max_declines), the
    explanation given explain_times, then the question again."""
    I = c["S"].get("identity") or {}
    D = I.get("decline") or {}
    key = "_all" if _b_interp(c, "decline_counting") == "total" else q.get("key", "")
    if count:
        idn["dec"][key] = int(idn["dec"].get(key, 0)) + 1
        if idn["dec"][key] >= int(D.get("max_declines", 2) or 2):
            return _b_id_fail(c, I.get("on_declined", ""), None)
    parts = list(ans)
    if int(idn.get("expl", 0)) < int(D.get("explain_times", 1) or 0):
        idn["expl"] = int(idn.get("expl", 0)) + 1
        # the identity question follows, so the explanation must not carry a question of its own
        parts.append(" ".join(x for x in _b_sentences(_b_r(c, D.get("explain", ""))) if not x.endswith("?")))
    return _b_listen(c, "ID", parts + [_b_qre(c, q)])


def _b_id_scoped(c, it):
    """A count_then_close intent of the identity check (scoped to it only, or closing as identity declined): during
    identity it is a decline of the question, not a refusal to talk."""
    a = it.get("action") or {}
    return a.get("kind") == "count_then_close" and (not {"neg", "conf"} & set(it.get("scope") or []) or a.get(
        "situation") == (c["S"].get("identity") or {}).get("on_declined"))


# the speaker says they are someone else (a relative, "speaking with her husband"), not "I'm not sure"
_B_NOTCUST = re.compile(r"\b(?:i'm|i am|this is|it's|it is) (?:not (?:him|her|mr|ms|mrs|miss|dr)\b|(?:his|her|their) "
                        r"(?:husband|wife|son|daughter|mother|father|mom|mum|dad|partner|brother|sister|friend|carer"
                        r"|assistant|colleague|neighbou?r|roommate|flatmate)\b)|\bspeaking (?:to|with) (?:his|her|their) \w")


def _b_id_answer_wins(c, q, idn, top):
    """A deflection intent (count_then_close) said with a complete answer to the pending security question does not
    replace the answer. Only for strictly parsed kinds (date, digits, year): a free-text answer accepts anything."""
    if (top.get("action") or {}).get("kind") != "count_then_close" or (q.get("kind") or "text") not in (
            "date", "digits", "year"):
        return False
    return (id_answer(q, c["text"], idn.get("frag", ""), c["today"]) or {}).get("status") == "complete"


def _b_verify_route(c, q, wire):
    S, st, W = c["S"], c["st"], c["W"]
    idn = st["id"]
    nodes = (W.get("api") or {}).get("verify") or []
    vi = int(idn.get("vi", 0))
    if vi >= len(nodes):
        return _b_id_fail(c, S.get("identity", {}).get("on_failed", ""))
    node = nodes[vi]
    idn["vi"] = vi + 1
    idn["sent"] = {"key": q.get("key", ""), "wire": wire}
    st["ph"] = "ID"
    if W.get("identity_mode") == "per_field":
        vals = {"@" + q.get("field_value", ""): wire}
    else:
        vals = {"selector": q.get("field_value", ""), "answer": wire}
    _b_route_api(c, node, vals)
    _b_varm(c, node)
    return True


def _b_varm(c, node):
    """Identity chain (wiring vchain): verify node `node` goes straight to the armed account read (wn_) when all is
    verified, or to the ID listen node (wl_) with the next question computed here, when this answer verified."""
    st, W, w = c["st"], c["W"], c["w"]
    if not (W.get("vchain") or {}).get("t"):
        return
    rows = (W.get("api") or {}).get("acct") or []
    t = int(st.get("acct_try", 0))
    a = rows[t] if t < len(rows) else ""
    w["wn_" + node] = a
    if a:
        for var in (_b_node(W, a).get("res") or {}).values():
            w[var] = "pending"
        st["vc"] = a
    c2 = dict(c, st=_b_copy(st), w=dict(), say=[], nx="", inp=dict())
    c2["res"] = {node: dict(s="true", verified="true", all="false")}
    c2.pop("wdm", None)
    _b_on_verify(c2, node)
    lid = (W.get("listen") or {}).get("id", "s_id")
    w["wl_" + node] = lid if c2["nx"] == lid else ""
    if c2["nx"] == lid:
        c["vsay"] = _b_compose(c2)
        st["vs"] = {k: v for k, v in c["sens"].items() if v}


def _b_on_verify(c, node):
    S, st = c["S"], c["st"]
    I = S.get("identity") or {}
    idn = st.setdefault("id", {})
    res = dict(_b_node_res(c, node))
    vf = c["inp"].get("vf", "")
    a = st.pop("vc", None)
    vs = st.pop("vs", None)
    if vs is not None and vf != "l":
        _b_sens(c, vs)                                  # the chain did not speak: the answer turn's own sensors
    if vf:
        res["hint"] = res["err"] = ""                   # the graph chained on ok/verified/all alone
    if vf == "a":
        c["vc"] = a
    res["prev_left"] = _b_s(idn.get("left", ""))
    cls = verify_class(res)
    left = _b_int(res.get("left"))
    if left is not None:
        idn["left"] = left
    q = _b_q(c)
    if q is None:
        return _b_acct_start(c)
    if cls == "transport_fail":
        idn["retry"] = int(idn.get("retry", 0)) + 1
        sent = idn.get("sent") or {}
        if idn["retry"] <= 1 and sent.get("wire"):
            return _b_verify_route(c, q, sent.get("wire"))
        st["csit"] = (S.get("recording") or {}).get("on_all_failed", "") or I.get("on_failed", "")
        return _b_close(c, [_b_line(c, "account_error")])
    idn["retry"] = 0
    if cls == "all_done":
        idn.setdefault("ver", []).append(q.get("key", ""))
        return _b_acct_start(c)
    if cls == "verified":
        idn["hintwire"] = ""
        idn.setdefault("ver", []).append(q.get("key", ""))
        idn["qi"] = int(idn.get("qi", 0)) + 1
        idn["frag"] = ""
        q2 = _b_q(c)
        if q2 is None:
            return _b_acct_start(c)
        return _b_listen(c, "ID", [_b_r(c, q2.get("ask", ""))])
    if cls.startswith("hint:"):
        hv = cls.split(":", 1)[1]
        h = None
        for x in I.get("hints") or []:
            if _b_s(x.get("value")) == hv:
                h = x
        cnt = int(idn.setdefault("hints", {}).get(hv, 0))
        idn["hintwire"] = _b_s((idn.get("sent") or {}).get("wire", ""))
        idn["hintsay"] = _b_r(c, h.get("say", "")) if h is not None else ""
        if h is not None and cnt < int(h.get("max", 1) or 0):
            idn["hints"][hv] = cnt + 1
            if h.get("counts_as_wrong"):
                idn["wrong"] = int(idn.get("wrong", 0)) + 1
                if idn["wrong"] >= int(I.get("max_wrong_total", 3) or 3):
                    return _b_id_fail(c, I.get("on_failed", ""))
            return _b_listen(c, "ID", [_b_r(c, h.get("say", ""))])
        # the hint repeats: it is not a wrong answer, so say the hint (or the full ask) again
        return _b_listen(c, "ID", [idn.get("hintsay") or _b_r(c, q.get("ask_full", "") or q.get("ask", ""))])
    if cls == "wrong":
        key = q.get("key", "")
        idn["wrong"] = int(idn.get("wrong", 0)) + 1
        idn.setdefault("wq", {})[key] = int(idn["wq"].get(key, 0)) + 1
        lim = int(I.get("max_wrong_total", 3) or 3)
        qmax = int(q.get("max_wrong", 0) or 0)
        if idn["wrong"] >= lim or (left is not None and left <= 0) or (qmax and idn["wq"][key] >= qmax):
            return _b_id_fail(c, I.get("on_failed", ""))
        return _b_listen(c, "ID", [_b_r(c, q.get("reask_wrong", "") or q.get("ask", ""))])
    if cls == "lockout":
        return _b_id_fail(c, I.get("on_failed", ""))
    return _b_listen(c, "ID", [_b_r(c, q.get("ask_full", "") or q.get("ask", ""))])


# ----------------------------------------------------------------------------------------------- account / statement
def _b_acct_start(c):
    st, W = c["st"], c["W"]
    st["ph"] = "ACCT"
    rows = (W.get("api") or {}).get("acct") or []
    t = int(st.get("acct_try", 0))
    if t >= len(rows):
        st["csit"] = (c["S"].get("recording") or {}).get("on_all_failed", "")
        return _b_close(c, [_b_line(c, "account_error")])
    st["acct_try"] = t + 1
    if c.pop("vc", "") == rows[t]:
        return _b_on_acct(c, rows[t])                   # the identity chain already read the account
    return _b_route_api(c, rows[t], {})


def _b_band(c, dl):
    bands = c["S"].get("bands") or []
    for b in bands:
        if int(b.get("days_late_min", 0)) <= dl <= int(b.get("days_late_max", 0)):
            return b
    best, bd = None, None
    for b in bands:
        d = min(abs(dl - int(b.get("days_late_min", 0))), abs(dl - int(b.get("days_late_max", 0))))
        if bd is None or d < bd:
            best, bd = b, d
    if best:
        return best
    dflt = {"key": "", "attempts": 1}
    dflt["deadline"] = {"kind": "today"}
    return dflt


def _b_build_prods(c, items):
    S = c["S"]
    P = S.get("products") or {}
    F = P.get("fields") or {}
    out = []
    mx = int(P.get("max", 5) or 5)
    for it in items[:mx]:
        f = dict()
        for k, v in it.items():
            f[_b_s(k)] = _b_s(v)
        due = _b_cents(it.get(F.get("past_due", "past_due")))
        dl = _b_int(it.get(F.get("days_late", "days_late")), 0)
        typ = _b_s(it.get(F.get("type", "type")))
        p = {"id": _b_s(it.get(F.get("id", "product_id"))), "type": typ, "due": due or 0, "dl": dl, "f": f,
             "used": 0, "fo": 0, "tm": 0, "ref": [], "va": 0, "sit": "", "ag": None, "rec": 0}
        tdef = (P.get("types") or {}).get(typ) or {}
        fl = eval_amount(tdef.get("floor") or {"kind": "full"}, p, {}) if tdef else p["due"]
        if tdef and (tdef.get("floor") or {}).get("kind") == "field":
            if _b_cents(f.get((tdef.get("floor") or {}).get("field", ""))) is None:
                fl = p["due"]
        p["floor"] = min(fl, p["due"]) if fl is not None else p["due"]
        b = _b_band(c, dl)
        p["band"] = b.get("key", "")
        p["att"] = int(b.get("attempts", 1) or 0)
        dd = None
        try:
            dd = eval_date_rule(c["cal"], b.get("deadline") or {"kind": "today"}, c["today"], {"deadline": None})
        except Exception:
            dd = None
        latest = _b_date_obj(dd) or c["today"]
        p["dead"] = iso(latest)
        out.append(p)
    return out


def _b_on_acct(c, node):
    S, st = c["S"], c["st"]
    res = _b_node_res(c, node)
    ok = _b_success(c, node, res.get("s", "pending"))
    items = []
    try:
        items = json.loads(res.get("products") or "[]")
    except Exception:
        items = []
    if ok and items:
        st["prods"] = _b_build_prods(c, items)
        return _b_statement(c)
    if ok and not items:
        st["csit"] = (S.get("recording") or {}).get("on_all_failed", "")
        return _b_close(c, [_b_line(c, "account_error")])
    return _b_acct_start(c)


def _b_first_amt(c, p):
    return eval_amount((c["S"].get("negotiation", {}).get("first_ask") or {}).get("amount") or {"kind": "full"}, p, c["st"])


def _b_first_date(c, p):
    rule = (c["S"].get("negotiation", {}).get("first_ask") or {}).get("date") or {"kind": "today"}
    return _b_valid_rung_date(c, rule, p)


def _b_one_at_a_time(c, key):
    """multi_product.<key> (state_all_first / readback_together) is false: products are handled one at a time."""
    return len(c["st"].get("prods") or []) > 1 and (c["S"].get("multi_product") or {}).get(key, True) is False


def _b_first_ask_one(c, j):
    """State product j and ask the single-product first question about it (the offer is product j's)."""
    S, st = c["S"], c["st"]
    p = st["prods"][j]
    p["stated"] = 1
    FA = S.get("negotiation", {}).get("first_ask") or {}
    st["offer"] = {"kind": "first_ask", "k": j, "amt": _b_first_amt(c, p), "date": _b_first_date(c, p),
                   "line": _b_r(c, FA.get("single", ""), prod=p)}
    st["k"] = j
    return _b_r(c, S.get("statement", {}).get("item", ""), prod=p)


def _b_state_next(c, j, ans):
    """state_all_first=false: the next open product is stated and asked about on its own."""
    item = _b_first_ask_one(c, j)
    return _b_listen(c, "NEG", list(ans) + [item, c["st"]["offer"]["line"]])


def _b_statement(c):
    S, st = c["S"], c["st"]
    prods = st["prods"]
    parts = [_b_r(c, S.get("identity", {}).get("verified_prefix", "")),
             _b_r(c, S.get("statement", {}).get("intro", ""))]
    one = _b_one_at_a_time(c, "state_all_first")
    if one:
        parts.append(_b_first_ask_one(c, 0))
    else:
        for p in prods:
            parts.append(_b_r(c, S.get("statement", {}).get("item", ""), prod=p))
    parts += _b_req(c, ["after_verified", "after_statement"])
    FA = S.get("negotiation", {}).get("first_ask") or {}
    if len(prods) > 1 and not one:                     # one at a time: _b_first_ask_one set product 0's offer
        st["offer"] = {"kind": "first_ask", "k": -1, "amt": None, "date": None, "line": _b_r(c, FA.get("multi", ""))}
        st["k"] = -1
    elif not one:
        p = prods[0]
        st["offer"] = {"kind": "first_ask", "k": 0, "amt": _b_first_amt(c, p), "date": _b_first_date(c, p),
                       "line": _b_r(c, FA.get("single", ""), prod=p)}
        st["k"] = 0
    sid = st.pop("stash", None)
    if sid:
        st["ph"] = "NEG"
        for it in S.get("intents") or []:
            if it.get("id") != sid:
                continue
            kind = (it.get("action") or {}).get("kind", "")
            if kind == "offer_transfer":
                return _b_xoffer_start(c, it, parts, dict())
            if kind == "resolve_product":
                return _b_resolve_product(c, it, parts, dict(prods=[]))
            if kind == "transfer":
                return _b_dispatch_common(c, it, parts, verified=True)
    return _b_listen(c, "NEG", parts + [st["offer"]["line"]])


# ----------------------------------------------------------------------------------------------- dates for offers
def _b_bounds(c, p):
    S = c["S"]
    PD = S.get("promise_date") or {}
    dead = _b_date_obj(p.get("dead")) or c["today"]
    ctx = {"deadline": dead}
    try:
        lo = eval_date_rule(c["cal"], PD.get("earliest") or {"kind": "today"}, c["today"], ctx) or c["today"]
    except Exception:
        lo = c["today"]
    try:
        hi = eval_date_rule(c["cal"], PD.get("latest") or {"kind": "deadline"}, c["today"], ctx) or dead
    except Exception:
        hi = dead
    return _b_date_obj(lo) or c["today"], _b_date_obj(hi) or dead


def _b_valid_rung_date(c, rule, p):
    """Evaluate a rung/offer DateRule and clamp it into [earliest, latest] on a business day (iso)."""
    lo, hi = _b_bounds(c, p)
    try:
        d = eval_date_rule(c["cal"], rule, c["today"], {"deadline": _b_date_obj(p.get("dead"))})
    except Exception:
        d = None
    d = _b_date_obj(d) or hi
    if d > hi:
        d = hi
    if d < lo:
        d = lo
    if (c["S"].get("promise_date") or {}).get("business_day_only", True):
        try:
            if not is_bd(c["cal"], d):
                n = next_bd(c["cal"], d)
                if n is not None and n <= hi:
                    d = n
                else:
                    b = prev_bd(c["cal"], hi, True)
                    if b is not None and b >= lo:
                        d = b
        except Exception:
            pass
    return iso(d)


def _b_attempt1_date(c, p):
    for r in (c["S"].get("negotiation") or {}).get("ladder") or []:
        if int(r.get("attempt", 0)) == 1 and _b_rung_ok(r, p):
            return _b_valid_rung_date(c, r.get("date") or {"kind": "deadline"}, p)
    return _b_valid_rung_date(c, {"kind": "deadline"}, p)


def _b_rung_ok(r, p):
    bands = r.get("bands") or ["all"]
    return "all" in bands or p.get("band") in bands


# ----------------------------------------------------------------------------------------------- negotiation
def _b_unresolved(p):
    return not p.get("sit") and not p.get("ag") and not p.get("rec")


def _b_mentions(c, text):
    prods = c["st"].get("prods") or []
    if len(prods) <= 1:
        return []
    t = " " + _b_norm(text) + " "
    words = []
    for p in prods:
        ws = set()
        typ = _b_s(p.get("type", "")).replace("_", " ").strip().lower()
        if typ:
            ws.add(typ)
        sp = _b_norm(_b_pname(c, p))
        if sp:
            ws.add(sp)
            sp2 = re.sub(r"\d+", " ", sp).strip()
            toks = sp2.split()
            if len(toks) >= 2:
                ws.add(" ".join(toks[:2]))
        for d in re.findall(r"\d{3,}", sp or ""):
            ws.add(d)
        words.append(ws)
    lasts = []
    for ws in words:
        lt = set()
        for w in ws:
            if not w.isdigit():
                lt.add(w.split()[-1])
        lasts.append(lt)
    out = []
    for j, ws in enumerate(words):
        hit = any(re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", t) for w in ws if w)
        if not hit:
            for lw in lasts[j]:
                if sum(1 for o in lasts if lw in o) == 1 and re.search(r"(?<![a-z0-9])" + re.escape(lw) + r"s?(?![a-z0-9])", t):
                    hit = True
        if hit:
            out.append(j)
    return out


def _b_values(c):
    st = c["st"]
    text = c["text"]
    lc = _b_lc(text)
    prods = st.get("prods") or []
    known, lo, hi = [], None, None
    for p in prods:
        known += [p.get("due"), p.get("floor")]
        lo = p.get("floor") if lo is None else min(lo, p.get("floor") or 0)
        hi = p.get("due") if hi is None else max(hi, p.get("due") or 0)
    known = [k for k in known if k is not None]
    ctx = {"known": known, "lo": lo, "hi": hi}
    O = st.get("offer") or {}
    k = O.get("k", -1)
    if (k is None or k < 0) and len(prods) == 1:
        k = 0
    if k is not None and 0 <= k < len(prods):
        cp = prods[k]
        ctx["full"] = cp.get("due")
        ctx["floor"] = cp.get("floor")
        if O.get("amt") is not None:
            ctx["ref"] = O.get("amt")
    drop = []
    for p in prods:
        drop.append(p.get("dl"))
        for d in re.findall(r"\d{3,}", _b_pname(c, p)):
            drop.append(int(d))
    ctx["drop"] = drop
    a = {}
    try:
        a = parse_amount(lc, ctx) or {}
    except Exception:
        a = {}
    if a.get("kind") != "amount" and _b_grounded(c["sens"].get("u_amt"), text):
        try:
            a2 = parse_amount(c["sens"].get("u_amt"), ctx) or {}
            if a2.get("kind") == "amount":
                a = a2
        except Exception:
            pass
    d = {}
    try:
        d = parse_date(lc, c["today"], c["cal"]) or {}
    except Exception:
        d = {}
    if d.get("kind") in (None, "none", "incomplete") and _b_grounded(c["sens"].get("u_date"), text):
        try:
            d2 = parse_date(c["sens"].get("u_date"), c["today"], c["cal"]) or {}
            if d2.get("kind") in ("date", "past", "vague"):
                d = d2
            elif c["act"] == "proposal":
                # a period the customer names in words the parser does not know is still a time, never a
                # refusal: the Spec's vague-date rule (ask for the exact day, then the deadline)
                d = {"kind": "vague", "what": "other"}
        except Exception:
            pass
    try:
        yn = yes_no(text) or {}
    except Exception:
        yn = {}
    if c.get("mv") is not None:
        a, d, yn = _b_mv_values(c, ctx, a, d, yn)
    try:
        oblq = bool(is_question(text)) and bool(_B_OBLQ.search(_b_norm(lc)))
    except Exception:
        oblq = False
    if oblq or _b_plain_question(c, lc):
        a, d = {}, {}
    amt = a.get("cents") if a.get("kind") == "amount" else None
    dk = d.get("kind") if d.get("kind") in ("date", "past", "vague") else ""
    if c.get("lang", "en") != "en":
        pass                                            # the weekday / relative-day notes are English sentences
    elif dk == "date" and d.get("wd_said") is not None:
        c["wdm"] = _b_wd_note(d.get("date"), d.get("wd_said"))
    elif dk == "date":
        c["wdm"] = _b_rel_note(c, lc, d.get("date"))
    return {"amt": amt, "zero": a.get("kind") == "zero", "date": d.get("date") if dk in ("date", "past") else None,
            "dk": dk, "yn": yn, "prods": _b_clause_mentions(c, text, amt is not None or bool(dk)),
            "all": bool(_B_ALL.search(_b_norm(lc)))}


def _b_mv_values(c, ctx, a, d, yn):
    """A non-English turn: the model-read amount, date and kind are primary, validated here; the values parsed from
    the English rendering stay only where the model read none. Small talk carries no value and no answer."""
    mv = c["mv"]
    cents = _b_mv_cents(mv.get("amt"))
    hi = ctx.get("hi") or 0
    if cents == 0:
        a = {"kind": "zero"}
    elif cents is not None and 0 < cents and (not hi or cents <= hi * 100):
        a = {"kind": "amount", "cents": cents}
    md = _b_mv_date(c)
    if md is not None:
        d = md
    kind = mv.get("kind")
    yn = dict(yn or {})
    if kind == "smalltalk" and cents is None and md is None:
        return {}, {}, {"yn": "", "hedge": False, "cond": False, "corr": False, "cant": False, "question": False}
    if kind in ("yes", "no") and not yn.get("yn"):
        yn["yn"] = kind
    elif kind == "yes" and yn.get("yn") == "no" and not yn.get("cant"):
        yn["yn"] = "yes"
    elif kind == "no" and yn.get("yn") == "yes":
        yn["yn"] = "no"
    if kind == "hedge":
        yn["hedge"] = True
    if kind == "correction":
        yn["corr"] = True
    if kind == "refusal" and not yn.get("yn"):
        yn["yn"] = "no"
    if kind == "question":
        yn["question"] = True
    return a, d, yn


def _b_mv_cents(v):
    """A model-read amount -> cents. Dot decimals are asked for; '1.250' (dot thousands) and '1.250,50' / '12,5'
    (comma decimals) are read the way the customer's language writes them. None when it is not a number."""
    t = re.sub(r"[^0-9.,]", "", _b_s(v))
    if not t or not re.search(r"\d", t):
        return None
    if re.match(r"^\d{1,3}(\.\d{3})+(,\d+)?$", t):
        t = t.replace(".", "").replace(",", ".")
    elif re.match(r"^\d{1,3}(,\d{3})+(\.\d+)?$", t):
        t = t.replace(",", "")
    elif re.match(r"^\d+,\d{1,2}$", t):
        t = t.replace(",", ".")
    if not re.match(r"^\d+(\.\d+)?$", t):
        return None
    return _b_cents(t)


def _b_mv_date(c):
    """The model-read date of a non-English turn (u_dkind/u_dval/u_dwhich) resolved from the call's now by the same
    date parser as English words, so every date rule applies unchanged. None when the model read no usable date."""
    mv = c["mv"]
    k, v = mv.get("dkind"), _b_s(mv.get("dval")).strip()
    if k == "vague":
        return {"kind": "vague", "what": "other"}
    phrase = ""
    try:
        if k == "absolute":
            m = re.match(r"^(?:(\d{4})-)?(\d{1,2})-(\d{1,2})$", v)
            if m:
                y = int(m.group(1)) if m.group(1) else c["today"].year
                datetime.date(y, int(m.group(2)), int(m.group(3)))          # must exist
                phrase = "%d %s" % (int(m.group(3)), _c_MONTHS[int(m.group(2)) - 1]) + (
                    " %d" % y if m.group(1) else "")
        elif k == "weekday":
            i = weekday_index(v)
            if i is not None:
                which = mv.get("dwhich") if mv.get("dwhich") in ("this", "next") else ""
                phrase = (which + " " + _c_DAYS[i]).strip()
        elif k == "relative_days":
            n = int(float(v))
            if 0 <= n <= 366:
                phrase = {0: "today", 1: "tomorrow", 2: "the day after tomorrow"}.get(n, "in %d days" % n)
        elif k == "day_of_month":
            n = int(float(v))
            if 1 <= n <= 31:
                suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
                phrase = "the %d%s" % (n, suf)
    except Exception:
        phrase = ""
    if not phrase:
        return None
    r = parse_date(phrase.lower(), c["today"], c["cal"]) or {}
    return r if r.get("kind") in ("date", "past") else None


def _b_wd_note(iso_d, said):
    """'Friday the 22nd' when the 22nd is a Thursday: the date the customer named is kept (it is read back with its
    real weekday and must be confirmed), and the mismatch is said once so the customer can correct it."""
    d = _b_date_obj(iso_d)
    if d is None or not 0 <= int(said) <= 6:
        return ""
    n = d.day
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return "Just to note, the %d%s is a %s, not a %s." % (n, suf, _c_DAYS[d.weekday()], _c_DAYS[int(said)])


_B_RELDAY = re.compile(r"\b(?:the day after tomorrow|tomorrow|today)\b")


def _b_rel_note(c, lc, iso_d):
    """'Tomorrow, October 11th' when tomorrow is the 15th: the relative day is kept (it is read back) and its real
    date is said, so the customer can correct the other one."""
    m = _B_RELDAY.search(_b_norm(lc))
    if not m:
        return ""
    other = parse_date(_B_RELDAY.sub(" ", _b_norm(lc)), c["today"], c["cal"]) or {}
    if other.get("kind") not in ("date", "past") or other.get("date") == iso_d or _b_date_obj(iso_d) is None:
        return ""
    return "Just to note, %s is %s." % (m.group(0), spoken_date(_b_date_obj(iso_d), c["today"]))


def _b_plain_question(c, lc):
    """'Is the amount 365?': a question that names a value without offering it carries no proposal (C.6 step 6).
    Short questions ('Friday?') and offer questions ('Can I pay on Friday?') keep their values."""
    try:
        isq = bool(is_question(c["text"])) or c["act"] == "question"
    except Exception:
        isq = c["act"] == "question"
    n = _b_norm(lc)
    return isq and len(n.split()) > 3 and not _B_OFFERQ2.search(n)


def _b_clause_mentions(c, text, has_value):
    """Products mentioned in the turn. With a value in the turn, only mentions in the clauses that carry a value
    count (\"I'll pay the A tomorrow, but not the B\" -> [A])."""
    allm = _b_mentions(c, text)
    if len(allm) <= 1 or not has_value:
        return allm
    parts = [x for x in _B_CLAUSE.split(_b_s(text).lower()) if x and x.strip()]
    if len(parts) <= 1:
        return allm
    out = []
    for part in parts:
        ms = _b_mentions(c, part)
        if not ms:
            continue
        val = False
        try:
            a = parse_amount(part, None) or {}
            d = parse_date(part, c["today"], c["cal"]) or {}
            val = a.get("kind") == "amount" or d.get("kind") in ("date", "vague", "past")
        except Exception:
            val = False
        neg = bool(_B_NEGCL.search(_b_norm(part)))
        if val and not neg:
            for j in ms:
                if j not in out:
                    out.append(j)
    return out or allm


def _b_is_yes(yn, c=None):
    if yn.get("question") or (c is not None and c.get("act") in ("question", "refuse")):
        return False
    return yn.get("yn") == "yes" and not (yn.get("hedge") or yn.get("cond") or yn.get("cant") or yn.get("corr"))


_B_PRESENCE = re.compile(r"\b(are you (still )?there|can you hear me|you still there|is anyone there|hello\s*\?)")
_B_AMTQ = re.compile(r"\b(how much|what do i owe|what i owe|do i owe|how many days|how late|what is the (amount|balance|total)"
                     r"|is (the|that the) (amount|balance|total)|which (account|loan|card|product|debt)"
                     r"|what (account|loan|card|product|debt) is (this|it)"
                     r"|what's the (amount|balance|total)|the amount again|past due|overdue)\b")
_B_OBLQ = re.compile(r"^\s*(do|does|must|should|have|would|will) i (?:really |actually |even |still |just )?"
                     r"(have to|need to|got to|must|owe)\b|\bhave i got to\b"
                     r"|\bwhen (do|must|should|would) i\b|\bdo i owe\b|\bhow much\b|\bby when\b")
# a question that offers a payment ("Can I pay 100 on Friday?", "What about Friday?", "Would Friday work?")
_B_OFFERQ2 = re.compile(r"\b(?:can|could|may|shall) (?:i|we) (?:pay|do|make|send|manage|give|settle|cover)\b"
                        r"|\b(?:how|what) about\b|\bwhat if i (?:pay|paid|do|did|send)\b|\bif i (?:pay|paid)\b"
                        r"|\bi (?:can |could |will |'ll )?pay\b"
                        r"|\b(?:work|ok|okay|fine|alright|all right|acceptable|enough|do)\W*$")
_B_REPEAT = re.compile(r"\b(repeat|say (that|it) again|pardon|what did you say|didn't (catch|hear)|come again)\b"
                       r"|^\W*(sorry|what|huh|eh)\W*$")
_B_HOLDON = re.compile(r"^\W*(?:(?:um|uh|oh|ok|okay)\W+)?(?:hold on|hang on|wait|one (?:second|sec|moment|minute)"
                       r"|just a (?:second|sec|moment|minute)|give me a (?:second|sec|moment|minute))\b(?:\W+\w+){0,3}\W*$")
# evasions that a free-text identity answer must not send to the bank ("Pass.", "Skip it.", "Not telling.")
_B_EVADE = re.compile(r"^\W*(?:pass|skip(?: it| that)?|next(?: question)?|not telling(?: you)?|no comment|none of your business"
                      r"|why do you need (?:that|it|to know)|i forgot|i forget|i can't remember|i don't remember)\W*$")
_B_WHOQ = re.compile(r"\b(who (am i|are you|is this|is calling|is speaking)|who's (this|calling|speaking))\b")
_B_INSIST = re.compile(r"\b(transfer|put me through|connect me|i insist|insist|human|real person|an agent|a person|"
                       r"someone real|operator|a colleague|just (a|the) (person|human))\b")
_B_FLOORW = re.compile(r"\b(minimum|min payment|instal+ments?|lowest (amount|payment))\b")
_B_CHANGE_LATER = re.compile(r"\b(change|cancel|move|modify|update)\b.{0,30}\b(later|afterwards|after that|another time)\b")


_B_CONFW = re.compile(r"\b(i confirm|confirmed|that's correct|that is correct|that's right|that is right|it's correct"
                      r"|it is correct|all correct)\b")


def _b_isq(c):
    isq = "?" in c["text"] or c["act"] == "question"
    try:
        isq = isq or bool(is_question(c["text"]))
    except Exception:
        pass
    return isq


def _b_qanswer(c, allow_noinfo=True):
    """Answer a question from what the tools returned: amounts / days late -> the statement item, purpose -> intro +
    item, presence -> 'Yes, I am here.'; anything else -> no_info (rule: never invent)."""
    S, st = c["S"], c["st"]
    n = _b_norm(c["text"])
    if _B_PRESENCE.search(n) or re.match(r"^\s*(hello|hi)\W*$", n):
        return [_b_line(c, "presence") or "Yes, I am here."]
    if _B_WHOQ.search(n) and _b_has((S.get("right_party", {}).get("answers") or {}).get("who")):
        return [_b_r(c, S["right_party"]["answers"]["who"])]
    prods = st.get("prods") or []
    k = (st.get("offer") or {}).get("k", -1)
    sel = [prods[k]] if k is not None and 0 <= k < len(prods) else list(prods)
    ment = _b_mentions(c, c["text"])
    if ment:
        sel = [prods[j] for j in ment if j < len(prods)]
    items = [_b_r(c, S.get("statement", {}).get("item", ""), prod=p) for p in sel]
    if _B_REPEAT.search(n):
        # the pending offer line itself is repeated by the caller; the first ask also restates the amounts
        return items if (st.get("offer") or {}).get("kind") in ("first_ask", "", None) else []
    if _B_WHYQ.search(n) and items:
        return [_b_r(c, S.get("statement", {}).get("intro", ""))] + items
    if _B_AMTQ.search(n) and items:
        return items
    return [_b_line(c, "no_info")] if allow_noinfo else []


def _b_offer(c, j, kind, amt, date, line):
    st = c["st"]
    if kind in ("floor", "next_bd", "deadline", "above_full"):
        line = _b_cue(c, st["prods"][j], line)
    st["k"] = j
    st["offer"] = {"kind": kind, "k": j, "amt": amt, "date": date, "line": line}
    st["ph"] = "NEG"
    return line


def _b_eval_prop(c, j, A, D, dk, O, clamp_all=False):
    """Validate a customer proposal for product j (C.6 step 3).
    -> {"t": "agreed"} | {"t": "offer", "line"} | {"t": "say", "line"} | {"t": "refuse"}."""
    S, st = c["S"], c["st"]
    p = st["prods"][j]
    PD = S.get("promise_date") or {}
    AM = S.get("amounts") or {}
    oamt = O.get("amt") if O.get("k") == j and O.get("amt") is not None else None
    if oamt is None:
        oamt = p["ag"][0] if p.get("ag") else _b_first_amt(c, p)
    odate = O.get("date") if O.get("k") == j and O.get("date") else None
    if odate is None:
        odate = p["ag"][1] if p.get("ag") else _b_first_date(c, p)
    amt = A if A is not None else oamt
    lo, hi = _b_bounds(c, p)
    if dk == "date" and D:
        date = D
    else:
        date = odate
    if A is not None:
        if A < (p.get("floor") or 0):
            p["tm"] = 1
            if not p.get("fo") and (p.get("floor") or 0) < p.get("due", 0):
                p["fo"] = 1
                fd = date if (dk == "date" and D and lo <= (_b_date_obj(D) or lo) <= hi
                              and is_bd(c["cal"], _b_date_obj(D))) else _b_attempt1_date(c, p)
                bf = AM.get("below_floor") or {}
                fl = _b_line(c, "floor_offer", prod=p, floor=p["floor"], amount=p["floor"], date=fd)
                ack = _b_line(c, "ack")
                if ack and fl.startswith(ack):
                    fl = fl[len(ack):].strip()
                bs = _b_s(bf.get("say", ""))
                if "<date>" in bs:
                    # the Spec's below-floor line is itself the dated floor offer: say it once
                    rest = _b_r(c, (AM.get("too_much") or {}).get("say_rest", ""), prod=p, amount=p["floor"])
                    fl = "" if rest in bs else rest
                elif "?" in bs:
                    # an undated question in it would be a second question before the floor offer: keep statements
                    bs = " ".join(x for x in _b_sentences(bs) if not x.endswith("?"))
                line = _b_join([_b_r(c, bs, prod=p, floor=p["floor"], amount=A, date=fd), fl])
                line = _b_offer(c, j, "floor", p["floor"], fd, line)
                return {"t": "offer", "line": line}
            return {"t": "refuse"}
        if A > p.get("due", 0):
            p["afo"] = int(p.get("afo", 0)) + 1
            if p["afo"] > 2:
                # loop guard: the full amount was offered twice already and the customer keeps naming more
                return {"t": "refuse"}
            dd = _b_date_obj(date)
            if dd is None or dd < lo or dd > hi:
                date = odate
            line = _b_line(c, "above_full_offer", prod=p, past_due=p["due"], amount=p["due"], date=date)
            line = _b_offer(c, j, "above_full", p["due"], date, line)
            return {"t": "offer", "line": line}
    if dk == "past":
        p["pdc"] = int(p.get("pdc", 0)) + 1
        if p["pdc"] > 2:
            return {"t": "refuse"}
        line = _b_line(c, "past_date", prod=p)
        _b_offer(c, j, "date_ask", amt, odate, line)
        return {"t": "say", "line": line}
    if dk == "vague":
        VG = PD.get("vague") or {}
        if int(p.get("va", 0)) < int(VG.get("ask_exact_times", 1) or 0):
            p["va"] = int(p.get("va", 0)) + 1
            line = _b_line(c, "date_ask_exact", prod=p)
            _b_offer(c, j, "vague_ask", amt, odate, line)
            return {"t": "offer", "line": line}
        return _b_deadline_offer(c, j, amt)
    d = _b_date_obj(date) or c["today"]
    if d < lo:
        p["pdc"] = int(p.get("pdc", 0)) + 1
        if p["pdc"] > 2:
            return {"t": "refuse"}
        line = _b_line(c, "past_date", prod=p)
        _b_offer(c, j, "date_ask", amt, odate, line)
        return {"t": "say", "line": line}
    if d > hi:
        MP = S.get("multi_product") or {}
        if clamp_all and MP.get("one_date_for_all", "clamp_to_own_deadline_and_say") == "clamp_to_own_deadline_and_say":
            p["ag"] = [amt, iso(hi)]
            p["clamp"] = 1
            return {"t": "agreed"}
        return _b_deadline_offer(c, j, amt)
    if PD.get("business_day_only", True) and not is_bd(c["cal"], d):
        if PD.get("non_business_within_deadline", "offer_next_business_day") == "refuse":
            return {"t": "refuse"}
        n = next_bd(c["cal"], d)
        if n is None or n > hi:
            return _b_deadline_offer(c, j, amt)
        line = _b_line(c, "next_bd_offer", prod=p, amount=amt, date=n)
        line = _b_offer(c, j, "next_bd", amt, iso(n), line)
        return {"t": "offer", "line": line}
    p["ag"] = [amt, iso(d)]
    return {"t": "agreed"}


def _b_deadline_offer(c, j, amt):
    p = c["st"]["prods"][j]
    dl = _b_valid_rung_date(c, {"kind": "deadline"}, p)
    if p.get("dlo"):
        # the deadline was already offered and the customer answered with another impossible date: that refuses
        # the deadline (flat refusal), it is not offered again
        pair = [amt, dl]
        if pair not in [list(x) for x in p.get("ref") or []]:
            p.setdefault("ref", []).append(pair)
        return {"t": "refuse"}
    p["dlo"] = 1
    line = _b_line(c, "deadline_offer", prod=p, amount=amt, deadline=dl, date=dl)
    line = _b_offer(c, j, "deadline", amt, dl, line)
    return {"t": "offer", "line": line}


def _b_pick_rung(c, p):
    lad = sorted((c["S"].get("negotiation") or {}).get("ladder") or [], key=lambda r: int(r.get("attempt", 0)))
    norep = (c["S"].get("negotiation") or {}).get("no_repeat_refused_offer", True)
    for r in lad:
        att = int(r.get("attempt", 0))
        if att <= int(p.get("used", 0)) or not _b_rung_ok(r, p):
            continue
        if att > int(p.get("att", 0)):
            return None
        amt = eval_amount(r.get("amount") or {"kind": "full"}, p, c["st"])
        date = _b_valid_rung_date(c, r.get("date") or {"kind": "deadline"}, p)
        if norep and [amt, date] in [list(x) for x in p.get("ref") or []]:
            p["used"] = att
            continue
        return r, amt, date
    return None


def _b_next_rung(c, j, ans):
    S, st = c["S"], c["st"]
    p = st["prods"][j]
    if st.get("suspend"):
        p["sit"] = st.get("xdecl") or (S.get("negotiation") or {}).get("on_exhausted", "")
        return _b_next(c, ans)
    got = _b_pick_rung(c, p)
    if got is None or int(p.get("used", 0)) >= int(p.get("att", 0)):
        p["sit"] = (S.get("negotiation") or {}).get("on_exhausted", "")
        p["ag"] = None
        return _b_next(c, ans)
    r, amt, date = got
    p["used"] = int(r.get("attempt", 0))
    line = _b_r(c, r.get("line", ""), prod=p, amount=amt, date=date, floor=p.get("floor"))
    line = _b_cue(c, p, line)
    _b_offer(c, j, "rung:" + _b_s(r.get("key")), amt, date, line)
    return _b_listen(c, "NEG", list(ans) + [line])


def _b_cue(c, p, line):
    """With several products, make sure an offer names its product (generic English cue)."""
    if len(c["st"].get("prods") or []) <= 1:
        return line
    name = _b_pname(c, p)
    if not name or name.lower() in line.lower():
        return line
    cue = _b_s((c["S"].get("lines") or {}).get("product_cue", ""))
    if cue:
        return _b_r(c, cue, prod=p) + " " + line
    if lang_of(c["S"]) == "en":
        return "For your " + name + ": " + line
    return name + ": " + line


def _b_next(c, ans):
    st = c["st"]
    if _b_one_at_a_time(c, "readback_together") and any(p.get("ag") and not p.get("rec") for p in st["prods"]):
        return _b_readback(c, ans)                     # each agreed product is read back before the next one
    for j, p in enumerate(st.get("prods") or []):
        if _b_unresolved(p):
            if not p.get("stated") and _b_one_at_a_time(c, "state_all_first"):
                return _b_state_next(c, j, ans)
            return _b_next_rung(c, j, ans)
    if any(p.get("ag") and not p.get("rec") for p in st.get("prods") or []):
        return _b_readback(c, ans)
    return _b_close(c, list(ans))


_B_REPEATABLE = ("first_ask", "vague_ask", "date_ask", "readback", "help_first")


def _b_reask(c):
    """The question put again after an interjection. An ask with no amount offer is repeated word for word; a pending
    amount offer (floor, rung, deadline, next business day, above full) is never said twice: the neutral re-ask."""
    O = c["st"].get("offer") or {}
    if O.get("kind", "") in _B_REPEATABLE:
        return O.get("line") or _b_line(c, "neutral_reask")
    return _b_line(c, "neutral_reask")


def _b_refuse(c, ans):
    st = c["st"]
    O = st.get("offer") or {}
    k = O.get("k", -1)
    prods = st.get("prods") or []
    if k is None or k < 0 or k >= len(prods):
        for j, p in enumerate(prods):
            if _b_unresolved(p):
                return _b_next_rung(c, j, ans)
        return _b_next(c, ans)
    p = prods[k]
    if O.get("amt") is not None and O.get("date"):
        pair = [O.get("amt"), O.get("date")]
        if pair not in [list(x) for x in p.get("ref") or []]:
            p.setdefault("ref", []).append(pair)
    if not _b_unresolved(p):
        return _b_next(c, ans)
    return _b_next_rung(c, k, ans)


def _b_targets(c, vals, O):
    prods = c["st"].get("prods") or []
    k = O.get("k", -1)
    if vals.get("prods"):
        return [j for j in vals["prods"] if j < len(prods) and not prods[j].get("rec")]
    if vals.get("all") or k is None or k < 0:
        return [j for j, p in enumerate(prods) if _b_unresolved(p) or (p.get("ag") and not p.get("rec"))]
    return [k] if k < len(prods) else []


def _b_dispatch_common(c, top, ans, verified=True):
    """Action intents shared by ID/NEG/CONF. -> result of a routing helper, or None when not handled."""
    st = c["st"]
    a = top.get("action") or {}
    kind = a.get("kind", "")
    req = _b_intent_req(c, top)
    if kind == "close_now":
        return _b_close_now(c, top, ans)
    if kind == "transfer":
        return _b_transfer(c, a.get("queue", ""), a.get("situation", ""), ans + [_b_r(c, a.get("say", ""))] + req,
                           a.get("drop_unrecorded", True), a.get("suppress_notes", True))
    if kind == "ask_then_transfer":
        if st.get("human"):
            return _b_transfer(c, a.get("queue", ""), a.get("situation", ""), ans + [_b_r(c, a.get("say", ""))] + req,
                               True, True)
        st["human"] = 1
        st["help"] = 1
        st["hid"] = top.get("id", "")
        line = _b_r(c, a.get("question", ""))
        if st.get("ph") in ("NEG", "CONF"):
            st["saved"] = st.get("offer")
            st["offer"] = {"kind": "help_first", "k": (st.get("offer") or {}).get("k", -1), "amt": None,
                           "date": None, "line": line}
        return _b_listen(c, st.get("ph", "ID"), ans + req + [line])
    if kind == "count_then_close":
        st["talk"] = int(st.get("talk", 0)) + 1
        if st["talk"] >= int(a.get("limit", 2) or 2):
            st["csit"] = a.get("situation", "") if verified else a.get("situation_pre_verification", "")
            return _b_close(c, ans + req)
        if st.get("ph") == "ID":
            q = _b_q(c)
            return _b_listen(c, "ID", ans + [_b_r(c, a.get("say", ""))] + req + [_b_qre(c, q or {})])
        return _b_listen(c, st.get("ph", "NEG"), ans + [_b_r(c, a.get("say", ""))] + req + [_b_reask(c)])
    return None


_B_WITHDRAW = re.compile(r"\b(never ?mind|forget (it|that|the \w+)|it's (ok|okay|fine|alright)|that's (ok|okay|fine)"
                         r"|let's (continue|carry on|go on)|(i'm|i am) (fine|ok|okay|good)|no need|don't need)\b")


def _b_insists(c, vals):
    """After 'is there anything I can help you with?': a plain no, a refusal or a transfer request is insisting;
    a value proposal or a real question is not."""
    if vals is not None and (vals.get("amt") is not None or vals.get("dk")):
        return False
    n = _b_norm(c["text"])
    if _B_WITHDRAW.search(n):
        return False
    m = _B_INSIST.search(n)
    if m:
        # "No, just put me through." insists; "I don't need a human." does not
        return not _B_NEGCL.search(re.split(r"[,.;!?]", n[:m.start()])[-1])
    if _b_isq(c):
        return False
    yn = (vals or {}).get("yn") or {}
    if c["act"] in ("no", "refuse"):
        return True
    return yn.get("yn") == "no" and len(n.split()) <= 5


def _b_human_transfer(c, ans):
    st = c["st"]
    it = None
    for x in c["S"].get("intents") or []:
        if x.get("id") == st.get("hid") or (it is None and (x.get("action") or {}).get("kind") == "ask_then_transfer"):
            it = x
    if it is None:
        return None
    a = it.get("action") or {}
    req = _b_intent_req(c, it)
    return _b_transfer(c, a.get("queue", ""), a.get("situation", ""), ans + [_b_r(c, a.get("say", ""))] + req, True, True)


def _b_transfer(c, queue, sit, pre, drop=True, suppress=True):
    st = c["st"]
    if drop:
        for p in st.get("prods") or []:
            if p.get("ag") and not p.get("rec"):
                p["ag"] = None
    st["xfer"] = {"q": queue, "sit": sit, "done": 0, "try": 0, "suppress": 1 if suppress else 0}
    st["ph_close"] = "XFER"
    return _b_close(c, pre)


def _b_neg_turn(c):
    st = c["st"]
    stage = "conf" if st.get("ph") == "CONF" else "neg"
    hits = _b_intents(c, stage)
    echo = _b_all_echo(c)
    if echo and any(_b_is_tm(it) for it in hits):
        # "No, I can't pay all of them today." echoes the multi-product first ask: a no to today, not too much
        bare = _B_ALLQ.sub(" ", _b_norm(c["text"]))
        if not too_much(bare) and not any(_b_is_tm(it) for it in _b_intents_on(c, stage, bare)):
            hits = [it for it in hits if not _b_is_tm(it)]
    ans, acts, tm = _b_split_intents(c, hits)
    rest = _b_withdrawn_rest(c, stage)
    if rest is not None and (st.get("offer") or {}).get("kind") not in ("help_first", "transfer_offer"):
        # "I don't need a person, it's fine.": nothing was asked for; go on with the pending question
        if not rest and not acts:
            return _b_listen(c, st.get("ph", "NEG"), ans + [_b_reask(c)])
        c["text"] = rest or c["text"]
    tmt = c["text"]
    if echo:
        # "Could you pay all of them today?" - "not all of them": which products, not how much
        tmt = _B_ALLQ.sub(" ", _b_norm(tmt))
    if not tm and too_much(tmt) and any((it.get("action") or {}).get("kind") == "too_much"
                                               and stage in (it.get("scope") or []) for it in c["S"].get("intents") or []):
        # "that is more than I can afford" / "the minimum is too high": the Spec's too-much rule, said differently
        tm = True
    O = st.get("offer") or {"kind": "first_ask", "k": -1}
    vals = _b_values(c)
    top = acts[0] if acts else None
    if O.get("kind") == "help_first" and top is not None and (top.get("action") or {}).get("kind") == "ask_then_transfer" \
            and not _b_insists(c, vals):
        acts = acts[1:]
        top = acts[0] if acts else None
    if O.get("kind") == "help_first" and not (top is not None and (top.get("action") or {}).get("kind") == "ask_then_transfer"):
        st.pop("help", None)
        if top is None and _b_insists(c, vals):
            r = _b_human_transfer(c, ans)
            if r is not None:
                return r
        st["offer"] = st.pop("saved", None) or {"kind": "first_ask", "k": -1}
        O = st["offer"]
        if O.get("kind") == "readback":
            st["ph"] = "CONF"
            stage = "conf"
        if top is None and vals["amt"] is None and not vals["dk"] and not tm and vals["yn"].get("yn") in ("no", "") \
                and not _b_isq(c):
            return _b_listen(c, st["ph"], ans + [_b_reask(c)])
    if O.get("kind") == "transfer_offer":
        return _b_xoffer_reply(c, ans, top, vals)
    if O.get("kind") == "post":
        return _b_post_turn(c, ans, top, vals)
    if top is not None:
        kind = (top.get("action") or {}).get("kind", "")
        if kind == "offer_transfer":
            return _b_xoffer_start(c, top, ans, vals)
        if kind == "resolve_product":
            return _b_resolve_product(c, top, ans, vals)
        r = _b_dispatch_common(c, top, ans, verified=True)
        if r is not None:
            return r
    if stage == "conf":
        return _b_conf_core(c, ans, vals, tm)
    return _b_negotiate(c, ans, vals, tm)


def _b_post_turn(c, ans, top, vals):
    """The reply to 'anything else?': a transfer / hardship / refusal intent is handled as usual (a transfer after
    a recorded promise closes as the transfer); a question is answered and the question asked again (twice at
    most); anything else closes the call."""
    st = c["st"]
    k = (top.get("action") or {}).get("kind", "") if top is not None else ""
    if k == "offer_transfer":
        return _b_xoffer_start(c, top, ans, vals)
    r = _b_dispatch_common(c, top, ans, verified=True) if k and k != "resolve_product" else None
    if r is not None:
        return r
    st["pt"] = int(st.get("pt", 0)) + 1
    if (ans or _b_isq(c)) and st["pt"] < 3:
        return _b_listen(c, "NEG", (ans or _b_qanswer(c)) + [st["offer"].get("line", "")])
    return _b_close(c, ans)


_B_ALLQ = re.compile(r"\b(?:all|every|each) (?:of )?(?:them|those|these|three|two|four|five|the \w+s|it|that)\b|\ball that\b"
                     r"|\bit all\b|\beverything\b|\bboth\b|\ball today\b")


def _b_is_tm(it):
    return (it.get("action") or {}).get("kind") == "too_much"


def _b_all_echo(c):
    """The pending ask is the multi-product first ask ("Can you pay all of them today?"), so "all of them",
    "everything" or "both" in the reply echoes the ask: which products, not how much."""
    st = c["st"]
    O = st.get("offer") or {}
    return O.get("kind", "first_ask") == "first_ask" and (O.get("k") is None or O.get("k", -1) < 0) and sum(
        1 for p in st.get("prods") or [] if _b_unresolved(p)) > 1
_B_AND_THE = re.compile(r" and (?=(?:the|my) )")    # on single-spaced lower-case text (see _b_clause_sits)


def _b_clause_sits(c, stage):
    """With several products, give each product the resolve_product intent of its own clause
    ('I paid the first one yesterday. The other one is not mine.') -> {j: intent}."""
    prods = c["st"].get("prods") or []
    out = {}
    if len(prods) <= 1:
        return out
    parts = [x for y in _B_CLAUSE.split(_b_s(c["text"]).lower()) if y
             for x in _B_AND_THE.split(" ".join(y.split())) if x and x.strip()]
    if len(parts) <= 1:
        return out
    for part in parts:
        ms = _b_mentions(c, part)
        if not ms:
            continue
        hits = [it for it in _b_intents_on(c, stage, part) if (it.get("action") or {}).get("kind") == "resolve_product"]
        if not hits and has_completed_payment(part) and not _B_FUTURE.search(_b_norm(_b_lc(part))):
            # "I paid the card yesterday": a completed payment of the product named in this clause
            hits = [it for it in c["S"].get("intents") or [] if stage in (it.get("scope") or [])
                    and (it.get("action") or {}).get("kind") == "resolve_product"
                    and _b_is_paid_intent(c["S"], it.get("action") or {})]
        if not hits:
            continue
        for j in ms:
            if j not in out:
                out[j] = hits[0]
    return out


def _b_resolve_product(c, top, ans, vals):
    S, st = c["S"], c["st"]
    a = top.get("action") or {}
    O = st.get("offer") or {}
    prods = st.get("prods") or []
    per = _b_clause_sits(c, "conf" if st.get("ph") == "CONF" else "neg")
    if per:
        says = []
        for j in sorted(per):
            it = per[j]
            if j < len(prods) and not prods[j].get("rec"):
                prods[j]["sit"] = (it.get("action") or {}).get("situation", "")
                prods[j]["ag"] = None
            sy = _b_rp(c, (it.get("action") or {}).get("say", ""), [x for x in sorted(per) if per[x] is it])
            if sy and sy not in says:
                says.append(sy)
            for rq in _b_intent_req(c, it):
                if rq not in says:
                    says.append(rq)
        pre = list(ans) + says
        MP = S.get("multi_product") or {}
        if not MP.get("dispute_or_paid_continues", False):
            return _b_close(c, pre)
        # a value for the other products in the same turn ("... The other one I can pay tomorrow.") is a proposal
        rest = [j for j in (vals.get("prods") or []) if j not in per]
        if rest and (vals.get("amt") is not None or vals.get("dk")):
            v2 = dict(vals)
            v2["prods"] = rest
            return _b_proposal(c, pre, v2, False, {"kind": "", "k": rest[0]})
        return _b_next(c, pre)
    if vals.get("prods"):
        targets = vals["prods"]
    elif O.get("k", -1) is not None and 0 <= O.get("k", -1) < len(prods):
        targets = [O["k"]]
    elif st.get("ph") == "CONF":
        ag = [j for j, p in enumerate(prods) if p.get("ag") and not p.get("rec")]
        targets = ag[:1] if len(ag) == 1 else [j for j, p in enumerate(prods) if not p.get("rec")]
    else:
        targets = [j for j, p in enumerate(prods) if _b_unresolved(p)]
    for j in targets:
        if j < len(prods) and not prods[j].get("rec"):
            prods[j]["sit"] = a.get("situation", "")
            prods[j]["ag"] = None
    pre = list(ans) + [_b_rp(c, a.get("say", ""), targets)] + _b_intent_req(c, top)
    MP = S.get("multi_product") or {}
    if len(prods) > 1 and not MP.get("dispute_or_paid_continues", False):
        return _b_close(c, pre)
    cur = O.get("k", -1)
    if cur is not None and 0 <= cur < len(prods) and _b_unresolved(prods[cur]) and st.get("ph") == "NEG":
        return _b_listen(c, "NEG", pre + [_b_reask(c)])
    return _b_next(c, pre)


def _b_rp(c, t, js):
    """An intent line about products js: <product> names all of them ('your X and your Y')."""
    ps = c["st"].get("prods") or []
    return _b_r(c, _b_s(t).replace(_B_PROD, _b_and([_b_pname(c, ps[j]) for j in js if j < len(ps)],
                                                      lang_of(c["S"]))))


def _b_xoffer_start(c, top, ans, vals):
    st = c["st"]
    a = top.get("action") or {}
    if st.get("xoffered"):
        return _b_listen(c, st.get("ph", "NEG"), ans + [_b_line(c, "ack"), _b_reask(c)])
    st["xoffered"] = 1
    if a.get("suspend_persuasion", True):
        st["suspend"] = 1
    st["xint"] = top.get("id", "")
    st["xdecl"] = a.get("decline_situation", "")
    O = st.get("offer") or {}
    if (vals.get("amt") is not None or vals.get("dk") == "date") and not _b_restates(c, vals, False, O):
        for j in _b_targets(c, vals, O):
            saved = _b_copy(st.get("offer") or {})
            r = _b_eval_prop(c, j, vals.get("amt"), vals.get("date"), vals.get("dk"), O)
            st["offer"] = saved
            if r.get("t") != "agreed":
                st["prods"][j]["ag"] = None
    st["saved"] = st.get("offer")
    full = _b_r(c, a.get("say", ""))
    _, qline = _b_xparts(full)
    st["offer"] = {"kind": "transfer_offer", "k": O.get("k", -1), "amt": None, "date": None, "line": qline}
    say = qline if st.get("symp") else full
    st["symp"] = 1
    return _b_listen(c, st.get("ph", "NEG"), ans + [say] + _b_intent_req(c, top))


def _b_accept_say(c, a):
    """What to say when a transfer offer is accepted: the Spec's accept_say, else the offer question turned into a
    statement ('Would you like me to connect you with X?' -> 'I will connect you with X now.')."""
    if _b_has(a.get("accept_say")):
        return _b_r(c, a.get("accept_say"))
    if c.get("lang", "en") != "en":
        return ""                                       # the statement below is built from English words
    _lead, qline = _b_xparts(_b_r(c, a.get("say", "")))
    act = _b_offer_action(qline)
    return "I will " + act + " now." if act else ""


_B_OFFERQ = re.compile(r"\s*(?:would you like me to|do you want me to|shall i|should i|may i|can i)(?=\s)", re.I)


def _b_offer_action(qline):
    """X in 'Would you like me to X?' (also do you want me to / shall / should / may / can I), else None.
    A linear form of ^\\s*(?:...)\\s+(.+?)\\s*\\?\\s*$, whose lazy group backtracked on long lines."""
    m = _B_OFFERQ.match(qline)
    if not m:
        return None
    body = qline[m.end():].rstrip()
    if not body.endswith("?"):
        return None
    act = body[:-1].strip()
    return act if act and "\n" not in act else None


def _b_prec(it):
    try:
        return float((it or dict()).get("precedence", 0) or 0)
    except Exception:
        return 0.0


def _b_xintent(c):
    for it in c["S"].get("intents") or []:
        if it.get("id") == c["st"].get("xint"):
            return it
    return None


def _b_xoffer_reply(c, ans, top, vals):
    st = c["st"]
    it = _b_xintent(c) or dict(action=dict())
    a = it.get("action") or {}
    # A new intent pre-empts the pending offer only when the Spec ranks it above the offering intent
    # (e.g. "this rule comes before rule N": a declined offer is not overridden by a lower-ranked transfer).
    if top is not None and (top.get("action") or {}).get("kind") in ("transfer", "ask_then_transfer", "close_now") \
            and _b_prec(top) > _b_prec(it):
        st["offer"] = st.pop("saved", None) or {}
        return _b_dispatch_common(c, top, ans, verified=True) or _b_listen(c, st.get("ph", "NEG"), ans + [_b_reask(c)])
    yn = vals.get("yn") or {}
    if vals.get("amt") is not None or vals.get("dk") == "date":
        saved = st.pop("saved", None) or {}
        st["offer"] = saved
        for j in _b_targets(c, vals, saved):
            r = _b_eval_prop(c, j, vals.get("amt"), vals.get("date"), vals.get("dk"), saved)
            if r.get("t") in ("offer", "say"):
                # the offer is declined, but the customer named a value: the corrective offer for it (deadline,
                # next business day, floor) is not persuasion; a no to it is the decline (persuasion stays off)
                return _b_listen(c, "NEG", ans + [r["line"]])
            st["offer"] = saved
        return _b_xdecline(c, ans, a)
    if _b_is_yes(yn, c):
        req = _b_intent_req(c, it)
        return _b_transfer(c, a.get("queue", ""), a.get("accept_situation", ""), ans + [_b_accept_say(c, a)] + req,
                           True, True)
    if yn.get("yn") == "no" or yn.get("cant") or c["act"] in ("no", "refuse"):
        st.pop("saved", None)
        return _b_xdecline(c, ans, a)
    # anything else: answer what can be answered, then the neutral re-ask (the offer is made once, PUB-05)
    if not ans and top is None and _b_isq(c):
        ans = ans + _b_qanswer(c, allow_noinfo=False)
    _lead, qline = _b_xparts(_b_r(c, a.get("say", "")))
    return _b_listen(c, st.get("ph", "NEG"), ans + [qline if ans else (_b_line(c, "neutral_reask") or qline)])


def _b_xdecline(c, ans, a):
    S, st = c["S"], c["st"]
    MP = S.get("multi_product") or {}
    prods = st.get("prods") or []
    O = st.get("offer") or {}
    cur = O.get("k", -1)
    for j, p in enumerate(prods):
        if not _b_unresolved(p):
            continue
        if MP.get("hardship_applies_to", "all_remaining") == "all_remaining" or j == cur or cur in (None, -1):
            p["sit"] = a.get("decline_situation", "")
    st["offer"] = {"kind": "", "k": -1}
    return _b_next(c, ans)


def _b_negotiate(c, ans, vals, tm):
    st = c["st"]
    O = st.get("offer") or {"kind": "first_ask", "k": -1}
    prods = st.get("prods") or []
    yn = vals.get("yn") or {}
    has_val = vals.get("amt") is not None or vals.get("dk") in ("date", "past", "vague")
    if has_val and _b_restates(c, vals, tm, O):
        has_val = False
    if not (vals.get("dk") == "vague" and O.get("kind") == "vague_ask") and has_val and not vals.get("zero"):
        st["unc"] = 0
        return _b_proposal(c, ans, vals, tm, O)
    if O.get("kind") == "vague_ask" and not ans:
        st["unc"] = 0
        j = O.get("k", 0)
        r = _b_deadline_offer(c, j, O.get("amt") if O.get("amt") is not None else prods[j].get("due"))
        if r.get("t") == "refuse":
            return _b_refuse(c, ans)
        return _b_listen(c, "NEG", ans + [r["line"]])
    if vals.get("zero"):
        st["unc"] = 0
        return _b_refuse(c, ans)
    if _b_is_yes(yn, c) and not tm and O.get("kind") not in ("help_first", "", "vague_ask", "date_ask"):
        st["unc"] = 0
        k = O.get("k", -1)
        if k is None or k < 0:
            for p in prods:
                if _b_unresolved(p):
                    p["ag"] = [_b_first_amt(c, p), _b_first_date(c, p)]
        else:
            p = prods[k]
            p["ag"] = [O.get("amt") if O.get("amt") is not None else _b_first_amt(c, p),
                       O.get("date") or _b_first_date(c, p)]
        return _b_next(c, ans)
    low = _b_lowest_answer(c, vals, O)
    if low:
        # "You tell me what the lowest amount is." with the floor pending: the floor is the lowest; say so, keep the
        # offer pending and ask again, neutrally (no attempt is used)
        st["unc"] = 0
        return _b_listen(c, "NEG", ans + [low, _b_reask(c)])
    if _b_not_this_offer(c, vals, tm, O):
        # "I can't pay the full amount" / "You tell me." with a smaller offer pending: not a no to that offer
        st["unc"] = 0
        return _b_listen(c, "NEG", (ans or [_b_line(c, "ack")]) + [_b_reask(c)])
    if tm and _B_FLOORW.search(_b_norm(c["text"])) and not asks_less(c["text"]):
        # "even the minimum is too much": the floor is refused before it is offered
        st["unc"] = 0
        for j in _b_targets(c, vals, O):
            p = prods[j]
            p["tm"] = 1
            p["fo"] = 1
            pair = [p.get("floor"), _b_attempt1_date(c, p)]
            if pair not in [list(x) for x in p.get("ref") or []]:
                p.setdefault("ref", []).append(pair)
        return _b_refuse(c, ans)
    if tm:
        st["unc"] = 0
        return _b_too_much(c, ans, vals, O)
    nm = _b_norm(c["text"])
    if _B_HOLDON.search(nm) or _B_REPEAT.search(nm):
        # "Hold on a second." / "Sorry, could you repeat that?": the pending question again (neutral after an offer)
        st["unc"] = 0
        pre = ans or (["Of course."] if _B_HOLDON.search(nm) else _b_qanswer(c, allow_noinfo=False))
        return _b_listen(c, "NEG", pre + [_b_reask(c)])
    if _b_isq(c) and not yn.get("cant") and (yn.get("yn") != "no" or yn.get("cond")) and c["act"] != "refuse":
        # "What happens if I don't pay?" is a question, not a refusal: answer (or no_info), then re-ask
        st["unc"] = 0
        return _b_listen(c, "NEG", (ans or _b_qanswer(c)) + [_b_reask(c)])
    if not ans and _b_small_talk(c, vals, st):
        # "I've been so busy at work and ...": small talk is no refusal and no non-answer; ask again, neutrally
        return _b_listen(c, "NEG", [_b_reask(c)])
    nonans = yn.get("hedge") and _b_interp(c, "hedge_is_non_answer", True)
    if yn.get("yn") == "no" or yn.get("cant") or nonans or c["act"] in ("no", "refuse") or vals.get("zero") or (
            yn.get("yn") == "yes" and (yn.get("cond") or yn.get("cant"))):
        st["unc"] = 0
        return _b_refuse(c, ans)
    if ans:
        st["unc"] = 0
        return _b_listen(c, "NEG", ans + [_b_reask(c)])
    st["unc"] = int(st.get("unc", 0)) + 1
    if st["unc"] >= 2:
        st["unc"] = 0
        return _b_refuse(c, ans)
    return _b_listen(c, "NEG", [_b_line(c, "clarify"), _b_reask(c)])


# words that make a turn about the payment (or a yes / no / refusal); a turn of 4+ words without one is small talk
_B_PAYTALK = re.compile(r"\b(?:pay\w*|paid|money|afford\w*|amount|owe\w*|debt|bill|balance|cash|funds?|salary|wages?|income"
                        r"|instal\w*|minimum|promise|offer|deal|yes|yeah|ok|okay|sure|fine|no|nope|not|never|can't|cannot"
                        r"|won't|refuse\w*|maybe|perhaps|think|know|try|them|those)\b|\b(?:it|that|this)\b(?!'s been| has been"
                        r"| was\b| took\b)|\?")
_B_CHAT_MAX = 3


def _b_chatter(c):
    """Four or more words and none about the payment, a yes / no, a refusal or a question."""
    n = _b_norm(c["text"])
    return len(n.split()) >= 4 and not _B_PAYTALK.search(n)


def _b_small_talk(c, vals, st):
    """Chatter about the customer's day with nothing about the payment (no value, yes/no, question or payment
    word), at most _B_CHAT_MAX turns in a row; a turn that is not small talk resets the count."""
    yn = vals.get("yn") or {}
    chat = c["act"] not in ("yes", "proposal", "question") and not (yn.get("yn") or yn.get("cant") or yn.get("cond")) \
        and _b_chatter(c) and not _b_intents_on(c, "neg", _b_norm(c["text"]))
    st["chat"] = int(st.get("chat", 0)) + 1 if chat else 0
    return chat and st["chat"] <= _B_CHAT_MAX


_B_FULLREF = re.compile(r"\b(?:the |that |this )?(?:full|whole|entire|total)(?: past[- ]due)? (?:amount|balance|sum|debt"
                        r"|bill|thing|lot)\b|\ball of it\b|\bin full\b|\beverything\b")
_B_DEFER = re.compile(r"\b(?:you tell me|you decide|you choose|(?:it's |that's )?up to you|"
                      r"what (?:do|would) you (?:suggest|recommend|propose|think)|whatever you (?:think|say|suggest))\b")
# a word that points at the pending offer; never "it's"/"that's" (the full amount just named) or "this week"
_B_OFFERREF = re.compile(r"\b(?:even|still|either|minimum|min payment|lowest)\b|\b(?:that|this|it)\b(?!'s\b| is\b"
                         r"| was\b| (?:month|week|weekend|year|time|morning|afternoon|evening"
                         r"|(?:mon|tues|wednes|thurs|fri|satur|sun)day)\b)")


_B_LOWEST_MAX = 2


def _b_lowest_answer(c, vals, off):
    """The answer to a question for the lowest / least / minimum amount while the floor itself is the pending offer
    ('<floor> is the lowest amount I can record.'), else ''. The Spec's line when it has one; at most _B_LOWEST_MAX
    times per call, then the turn is handled as before."""
    st = c["st"]
    prods = st.get("prods") or []
    k = off.get("k", -1)
    if vals.get("amt") is not None or vals.get("dk") or vals.get("zero") or not _b_asks_lowest(c["text"]):
        return ""
    if off.get("amt") is None or not off.get("date") or k is None or not 0 <= k < len(prods):
        return ""
    p = prods[k]
    if p.get("floor") is None or off.get("amt") != p.get("floor") or int(st.get("lq", 0)) >= _B_LOWEST_MAX:
        return ""
    L = c["S"].get("lines") or {}
    tpl = next((_b_s(L.get(x)) for x in ("lowest_amount", "floor_is_lowest", "floor_lowest") if _b_has(L.get(x))), "")
    if not tpl:
        lang = _b_s((c["S"].get("bank") or {}).get("language") or "en").lower()
        if not lang.startswith("en"):
            return ""
        tpl = "<floor> is the lowest amount I can record."
    st["lq"] = int(st.get("lq", 0)) + 1
    return _b_r(c, tpl, prod=p, floor=p["floor"], amount=p["floor"], date=off.get("date"))


def _b_not_this_offer(c, vals, tm, off):
    """A turn that is not a no to the pending smaller offer: a no / can't / too-much aimed at the full amount (the
    objection this offer already answers), or the choice handed back ("you tell me"). Once per kind per call
    (st["nto"]); a second such turn is handled as before."""
    prods = c["st"].get("prods") or []
    k = off.get("k", -1)
    if (vals.get("amt") is not None and not _b_full_named(c, vals, k)) or vals.get("dk") or vals.get("zero"):
        return False
    if off.get("amt") is None or not off.get("date") or off.get("kind", "") in _B_REPEATABLE or k is None \
            or not 0 <= k < len(prods):
        return False
    nm = _b_norm(c["text"])
    yn = vals.get("yn") or {}
    kind = ""
    if _B_DEFER.search(nm) and not _B_NEGCL.search(_B_DEFER.sub(" ", nm)):
        kind = "defer"
    elif off["amt"] < (prods[k].get("due") or 0) and (tm or yn.get("cant") or yn.get("yn") == "no") \
            and _B_FULLREF.search(nm) and not _B_OFFERREF.search(_B_FULLREF.sub(" ", nm)):
        kind = "full"
    used = c["st"].setdefault("nto", [])
    if not kind or kind in used:
        return False
    used.append(kind)
    return True


def _b_restates(c, vals, tm, offer):
    """A refusal or too-much turn whose only values restate the pending offer ("I can't pay the full amount today")
    carries no proposal."""
    yn = vals.get("yn") or {}
    if not (tm or yn.get("cant") or yn.get("yn") == "no") or vals.get("dk") not in ("", "date"):
        return False
    prods = c["st"].get("prods") or []
    cur = offer.get("date") or (iso(c["today"]) if offer.get("kind") in ("first_ask", None, "") else "")
    same_d = vals.get("dk") == "" or vals.get("date") in (cur, iso(c["today"]))
    oamt = offer.get("amt")
    k = offer.get("k") if offer.get("k") is not None else -1
    if oamt is None and 0 <= k < len(prods):
        oamt = prods[k].get("due")
    full = vals.get("dk") == "" and (tm or yn.get("cant")) and _b_full_named(c, vals, k)
    return same_d and (vals.get("amt") is None or vals.get("amt") == oamt or full)


def _b_full_named(c, vals, k):
    """The turn's amount is product k's full amount, named in words ("the full amount"): an objection, not a value."""
    prods = c["st"].get("prods") or []
    return k is not None and 0 <= k < len(prods) and vals.get("amt") == prods[k].get("due") and bool(
        _B_FULLREF.search(_b_norm(c["text"])))


def _b_too_much(c, ans, vals, O):
    S, st = c["S"], c["st"]
    prods = st.get("prods") or []
    k = O.get("k", -1)
    targets = _b_targets(c, vals, O)
    for j in targets:
        prods[j]["tm"] = 1
    if k is None or k < 0 or k >= len(prods) or not _b_unresolved(prods[k]):
        k = targets[0] if targets else -1
    if k is None or k < 0:
        return _b_refuse(c, ans)
    p = prods[k]
    p["tm"] = 1
    TMR = (S.get("amounts") or {}).get("too_much") or {}
    if not p.get("fo") and (p.get("floor") or 0) < p.get("due", 0) and int(TMR.get("times", 1) or 0) > 0:
        p["fo"] = 1
        mode = TMR.get("date", "attempt_1")
        if _b_interp(c, "floor_offer_date") == "customer_else_pending_else_attempt_1":
            mode = "customer_else_pending"
        fd = None
        if mode in ("pending", "customer_else_pending") and O.get("k") == k and O.get("date"):
            fd = O.get("date")
        if mode == "customer_else_pending" and vals.get("dk") == "date" and vals.get("date"):
            fd = vals.get("date")
        if not fd:
            fd = _b_attempt1_date(c, p)
        fo_t = (S.get("lines") or {}).get("floor_offer", "")
        rest = "" if "<rest>" in _b_s(fo_t) else _b_r(c, TMR.get("say_rest", ""), prod=p, amount=p["floor"])
        line = _b_join([_b_line(c, "floor_offer", prod=p, floor=p["floor"], amount=p["floor"], date=fd), rest])
        line = _b_offer(c, k, "floor", p["floor"], fd, line)
        if O.get("k") == k and O.get("amt") is not None and O.get("date"):
            pair = [O.get("amt"), O.get("date")]
            if pair not in [list(x) for x in p.get("ref") or []]:
                p.setdefault("ref", []).append(pair)
        return _b_listen(c, "NEG", ans + [line])
    st["offer"] = O if O.get("k") == k else {"kind": "first_ask", "k": k, "amt": None, "date": None}
    return _b_refuse(c, ans)


def _b_proposal(c, ans, vals, tm, O):
    st = c["st"]
    prods = st.get("prods") or []
    targets = _b_targets(c, vals, O)
    if not targets:
        return _b_listen(c, st.get("ph", "NEG"), ans + [_b_reask(c)])
    if tm:
        for j in targets:
            prods[j]["tm"] = 1
    clamp_all = len(targets) > 1
    first_other = None
    saved = _b_copy(O)
    for j in targets:
        st["offer"] = _b_copy(saved)
        snap = _b_copy(prods[j])
        r = _b_eval_prop(c, j, vals.get("amt"), vals.get("date"), vals.get("dk"), saved, clamp_all)
        if r.get("t") == "agreed":
            continue
        if r.get("t") in ("offer", "say") and first_other is not None:
            # only the first product's offer is spoken: the others keep their one floor offer / date asks
            prods[j].clear()
            prods[j].update(snap)
            continue
        if r.get("t") == "refuse":
            st["offer"] = {"kind": "floor", "k": j, "amt": prods[j].get("floor"), "date": None}
            pend = _b_copy(saved)
            first_other = first_other or ("refuse", j, None, pend)
            continue
        first_other = (r.get("t"), j, r.get("line"), _b_copy(st.get("offer")))
    if first_other is not None:
        t, j, line, off = first_other
        if t == "refuse":
            st["offer"] = {"kind": "floor", "k": j, "amt": prods[j].get("floor"), "date": None}
            return _b_refuse(c, ans)
        st["offer"] = off
        st["k"] = j
        st["ph"] = "NEG"
        return _b_listen(c, "NEG", ans + [line])
    cur = saved.get("k", -1)
    if cur is not None and 0 <= cur < len(prods) and _b_unresolved(prods[cur]):
        st["offer"] = saved
        return _b_listen(c, "NEG", ans + [_b_line(c, "ack"), _b_reask(c)])
    return _b_next(c, ans)


# ----------------------------------------------------------------------------------------------- confirmation
def _b_readback(c, ans):
    S, st = c["S"], c["st"]
    C = S.get("confirmation") or {}
    MP = S.get("multi_product") or {}
    items, pre = [], list(ans)
    for p in st.get("prods") or []:
        if p.get("ag") and not p.get("rec"):
            if p.get("clamp") and not p.get("clamp_said"):
                p["clamp_said"] = 1
                pre.append(_b_r(c, MP.get("clamp_line", ""), prod=p, deadline=p["ag"][1], date=p["ag"][1]))
            items.append(_b_r(c, C.get("readback_item", ""), prod=p, amount=p["ag"][0], date=p["ag"][1]))
    line = _b_join([_b_r(c, C.get("readback", ""), items=_b_and(items, lang_of(S))), _b_r(c, C.get("question", ""))])
    st["rbc"] = int(st.get("rbc", 0)) + 1
    if st["rbc"] > _B_MAX_READBACKS:
        # loop guard: a customer who keeps rejecting read-backs has refused this promise (flat refusal)
        return _b_reopen(c, pre)
    st["offer"] = {"kind": "readback", "k": -2, "amt": None, "date": None, "line": line}
    st["conf"] = {"no": 0, "hedge": 0}
    st["unc"] = 0
    return _b_listen(c, "CONF", pre + [line])


def _b_reopen(c, ans, only=None):
    """Flat refusal of the read-back: every agreed (unrecorded) product (or only `only`) refuses its agreed pair
    -> next rungs."""
    st = c["st"]
    first = None
    for j, p in enumerate(st.get("prods") or []):
        if p.get("ag") and not p.get("rec") and (only is None or j in only):
            pair = list(p["ag"])
            if pair not in [list(x) for x in p.get("ref") or []]:
                p.setdefault("ref", []).append(pair)
            p["ag"] = None
            if first is None:
                first = j
    st["ph"] = "NEG"
    if first is None:
        return _b_next(c, ans)
    return _b_next_rung(c, first, ans)


def _b_conf_core(c, ans, vals, tm):
    S, st = c["S"], c["st"]
    C = S.get("confirmation") or {}
    prods = st.get("prods") or []
    agreed = [j for j, p in enumerate(prods) if p.get("ag") and not p.get("rec")]
    if not agreed:
        return _b_next(c, ans)
    conf = st.setdefault("conf", {"no": 0, "hedge": 0})
    yn = vals.get("yn") or {}
    differs = False
    if vals.get("amt") is not None or vals.get("dk") in ("date", "past", "vague"):
        tg = [j for j in (vals.get("prods") or agreed) if j in agreed] or agreed
        for j in tg:
            ag = prods[j]["ag"]
            if vals.get("amt") is not None and vals["amt"] != ag[0]:
                differs = True
            if vals.get("dk") == "date" and vals.get("date") != ag[1]:
                differs = True
            if vals.get("dk") in ("past", "vague"):
                differs = True
    # the turn names only values the read-back already holds ("No, we agreed on <the date read back>")
    same_val = not differs and (vals.get("amt") is not None or vals.get("dk") == "date")
    if _B_CHANGE_LATER.search(_b_norm(c["text"])):
        if not ans:
            ans = ans + [_b_r(c, C.get("recorded_cannot_change", "")) or _b_line(c, "no_info")]
        return _b_listen(c, "CONF", ans + [_b_r(c, C.get("question", ""))])
    if conf.get("asked_change") and not differs and not tm and yn.get("yn") != "no" and not yn.get("cant") \
            and c["act"] != "refuse":
        # a yes to "What would you like to change?" is not a confirmation: ask for the new value or read back again;
        # an explicit "I confirm" / "never mind, that's correct" is
        conf["asked_change"] = 0
        if _b_is_yes(yn, c) and _B_CONFW.search(_b_norm(c["text"])):
            return _b_write(c, ans)
        if same_val:
            # "I need the date to be <the date read back>": nothing to change, read back again
            return _b_readback(c, ans)
        if re.search(r"\b(amount|how much|sum)\b", _b_norm(c["text"])):
            conf["asked_change"] = 1
            return _b_listen(c, "CONF", ans + [_b_line(c, "amount_change_ask") or "What amount would you like to pay?"])
        if re.search(r"\b(date|day|when)\b", _b_norm(c["text"])):
            conf["asked_change"] = 1
            return _b_listen(c, "CONF", ans + [_b_line(c, "date_ask_exact")])
        return _b_listen(c, "CONF", ans + [(st.get("offer") or {}).get("line", "") or _b_r(c, C.get("question", ""))])
    if _b_is_yes(yn, c) and not differs and not tm:
        return _b_write(c, ans)
    if differs:
        tg = [j for j in (vals.get("prods") or []) if j in agreed]
        if not tg:
            tg = agreed if (len(agreed) == 1 or vals.get("all") or vals.get("amt") is None) else agreed[:1]
        clamp_all = len(tg) > 1
        for j in tg:
            O = {"kind": "readback", "k": j, "amt": prods[j]["ag"][0], "date": prods[j]["ag"][1]}
            r = _b_eval_prop(c, j, vals.get("amt"), vals.get("date"), vals.get("dk"), O, clamp_all)
            if r.get("t") in ("offer", "say"):
                prods[j]["ag"] = None
                return _b_listen(c, "NEG", ans + [r.get("line", "")])
            if r.get("t") == "refuse":
                prods[j]["ag"] = None
                st["offer"] = O
                return _b_refuse(c, ans)
        return _b_readback(c, ans)
    if tm:
        j = (vals.get("prods") or agreed)[0]
        if j not in agreed:
            j = agreed[0]
        p = prods[j]
        O = {"kind": "readback", "k": j, "amt": p["ag"][0], "date": p["ag"][1], "line": ""}
        p["ag"] = None
        st["offer"] = O
        return _b_too_much(c, ans, {"prods": [j], "all": False, "dk": "", "date": None}, O)
    if yn.get("yn") == "no" and not yn.get("hedge") or c["act"] == "refuse" or yn.get("cant"):
        ment = [j for j in (vals.get("prods") or []) if j in agreed]
        if ment and len(ment) < len(agreed):
            return _b_reopen(c, ans, ment)
        if same_val and (yn.get("corr") or not (yn.get("cant") or c["act"] == "refuse")):
            # "No, the date should be <the date read back>" / "No, we agreed on <it>": the read-back already says
            # that; read it back again (the read-back loop guard still ends a customer who never confirms)
            return _b_readback(c, ans)
        conf["no"] = int(conf.get("no", 0)) + 1
        if conf["no"] == 1 and not yn.get("cant") and c["act"] != "refuse":
            conf["asked_change"] = 1
            return _b_listen(c, "CONF", ans + [_b_r(c, C.get("what_to_change", ""))])
        return _b_reopen(c, ans)
    if _b_isq(c) and not yn.get("hedge"):
        return _b_listen(c, "CONF", (ans or _b_qanswer(c)) + [_b_r(c, C.get("question", ""))])
    if yn.get("hedge") or yn.get("cond") or (yn.get("yn") == "yes"):
        conf["hedge"] = int(conf.get("hedge", 0)) + 1
        if conf["hedge"] >= 2:
            return _b_reopen(c, ans)
        # repeat the whole read-back, so a "yes" confirms what is actually recorded
        return _b_listen(c, "CONF", ans + [(st.get("offer") or {}).get("line", "") or _b_r(c, C.get("question", ""))])
    if ans:
        return _b_listen(c, "CONF", ans + [_b_r(c, C.get("question", ""))])
    if same_val:
        # "I need the date to be <the date read back>": it was heard; read back again, no "could you say that again"
        return _b_readback(c, ans)
    st["unc"] = int(st.get("unc", 0)) + 1
    return _b_listen(c, "CONF", [_b_line(c, "clarify"), (st.get("offer") or {}).get("line", "")])


def _b_write(c, ans):
    st, W = c["st"], c["W"]
    rows = (W.get("api") or {}).get("promise") or []
    items = []
    for j, p in enumerate(st.get("prods") or []):
        if p.get("ag") and not p.get("rec") and j < len(rows) and rows[j]:
            items.append({"t": "promise", "j": j, "n": rows[j][0], "try": 0})
    have = [it["j"] for it in items]
    more = _b_one_at_a_time(c, "readback_together") and any(
        _b_unresolved(p) for j, p in enumerate(st.get("prods") or []) if j not in have)
    if items and more and not st.get("cap"):
        st["post"], st["cont"] = 1, 1                   # this product's promise first, then the next product
    elif items and _b_interp(c, "after_record", "close") == "ask_anything_else" and not st.get("cap"):
        st["post"] = 1                                  # notes and the goodbye wait for the reply (_b_post)
    else:
        items += _b_note_items(c, have)
    st.setdefault("bye_pre", []).extend([a for a in ans if a])
    st["ph"] = "WRITE"
    return _b_emit_plan(c, items)


# ----------------------------------------------------------------------------------------------- dispatch
def _b_on_turn(c):
    st = c["st"]
    st["turns"] = int(st.get("turns", 0)) + 1
    ph = st.get("ph", "OPEN")
    if ph == "OPEN":
        st["ph"] = "RP"
        st["rp"] = {"asks": 1}
        ph = "RP"
    if st["turns"] >= min(int(c["S"].get("turn_cap") or 0) or _B_MAX_TURNS, _B_MAX_TURNS) and ph in (
            "RP", "TP", "ID", "NEG", "CONF"):
        return _b_wrap_up(c, ph)
    if st["turns"] > _B_MAX_TURNS:
        return _b_close(c, [])
    if ph == "RP":
        return _b_rp_turn(c)
    if ph == "TP":
        return _b_tp_turn(c)
    if ph == "ID":
        return _b_id_turn(c)
    if ph in ("NEG", "CONF"):
        return _b_neg_turn(c)
    if ph == "ACCT":
        return _b_acct_start(c)
    W = c["W"]
    if W.get("bye_mode") == "listen" and ph == "BYE":
        _, _, cm = resolve_outcome(c["S"], st)
        api = W.get("api") or {}
        st["ph"] = "CLOSE"
        c["nx"] = api.get("close_r", "a_close_r") if cm == "r" else api.get("close_n", "a_close_n")
        return None
    return _b_close(c, [])


def _b_wrap_up(c, ph):
    """The safe turn budget (Spec turn_cap, set by the compiler below the platform's code_exec limit) is used up:
    end the call properly now instead of going silent later. Agreed promises are recorded, every open product is
    refused, and before that the phase's own situation closes the call; close_call stays the last call."""
    S, st = c["S"], c["st"]
    st["cap"] = 1
    prods = st.get("prods") or []
    if ph in ("NEG", "CONF"):
        for p in prods:
            if _b_unresolved(p):
                p["sit"] = (S.get("negotiation") or {}).get("on_exhausted", "")
        st["offer"] = {"kind": "", "k": -1}
        if any(p.get("ag") and not p.get("rec") for p in prods):
            return _b_write(c, [])
        return _b_close(c, [])
    sit = {"RP": (S.get("right_party") or {}).get("on_unresolved"),
           "TP": ((S.get("third_party") or {}).get("situations") or {}).get("no_callback"),
           "ID": (S.get("identity") or {}).get("on_declined")}.get(ph)
    if sit and not st.get("csit"):
        st["csit"] = sit
    return _b_close(c, [])


def _b_on_result(c, node):
    W = c["W"]
    tool = _b_node(W, node).get("tool", "")
    api = W.get("api") or {}
    if node in (api.get("verify") or []):
        return _b_on_verify(c, node)
    if node in (api.get("acct") or []):
        return _b_on_acct(c, node)
    if tool == "verify_identity" or (W.get("roles") or {}).get(tool, {}).get("res", {}).get("verified"):
        return _b_on_verify(c, node)
    if (W.get("roles") or {}).get(tool, {}).get("res", {}).get("products"):
        return _b_on_acct(c, node)
    return _b_close(c, [])


def _b_finish(c):
    st, W = c["st"], c["W"]
    w = c["w"]
    if not c["nx"]:
        c["nx"] = (W.get("listen") or {}).get("safe", "s_safe")
    listen_nodes = list((W.get("listen") or {}).values()) + [W.get("bye", "s_bye")]
    if c["nx"] in listen_nodes:
        for s in _b_sensor_names(c["S"]):
            w[s] = _B_RESET.get(s, "")
        w["say"] = _b_compose(c)
    elif c.get("vsay") is not None:
        for s in _b_sensor_names(c["S"]):
            w[s] = _B_RESET.get(s, "")
        w["say"] = c["vsay"]
    elif c["say"]:
        w["say"] = _b_compose(c)
    co = c["co"] or resolve_outcome(c["S"], st)
    w["co"], w["cr"], w["cmode"] = co[0], co[1], co[2]
    st["errs"] = 0
    w["ph"] = _b_s(st.get("ph", ""))
    w["dbg_step"] = "ok:" + _b_s(st.get("ph", "")) + ":" + _b_s(c["nx"])
    w["st"] = _b_dump(st)
    w["nx"] = c["nx"]
    return st, w


def step(rspec, st, inp):
    """Pure core. inp = {"call": {...}, "sensors": {...}, "results": node -> (role -> raw string), "entered_from": str}.
    -> (new_st: dict, writes: dict[str, str])."""
    R = _b_dec(rspec)
    orig = _b_copy(st or {})
    try:
        c = _b_ctx(R, _b_copy(orig), inp)
        st1 = c["st"]
        if st1.get("plan"):
            _b_reconcile(c)
        else:
            W = c["W"]
            aw = st1.get("await", "")
            if aw and aw in (W.get("nodes") or {}) and st1.get("ph") not in ("RP", "TP", "NEG", "CONF", "OPEN"):
                _b_on_result(c, aw)
                if c["inp"].get("vf") == "l":
                    # the identity chain already asked the next question: this entry is the customer's reply
                    c["say"], c["nx"] = [], ""
                    _b_on_turn(c)
            else:
                _b_on_turn(c)
        return _b_finish(c)
    except Exception as e:
        return _b_on_error(R, orig, inp, e)


def _b_on_error(R, orig, inp, e):
    st = _b_copy(orig)
    st["errs"] = int(st.get("errs", 0)) + 1
    W = R.get("wiring") or {}
    S = R.get("spec") or {}
    safe = (W.get("listen") or {}).get("safe", "s_safe")
    w = {"dbg_err": _b_s(e)[:200]}
    if st["errs"] >= 2:
        try:
            c = _b_ctx(R, st, inp)
            st["plan"] = []
            _b_close(c, [])
            st2, w2 = _b_finish(c)
            st2["errs"] = st["errs"]
            w2["st"] = _b_dump(st2)
            w2["dbg_err"] = w["dbg_err"]
            nx = w2.pop("nx")
            w2["nx"] = nx
            return st2, w2
        except Exception:
            pass
    aw = st.get("await", "")
    listen = list((W.get("listen") or {}).values())
    nx = aw if aw in listen and aw != (W.get("listen") or {}).get("open") else safe
    for s in _b_sensor_names(S):
        w[s] = _B_RESET.get(s, "")
    w["say"] = _b_s((S.get("lines") or {}).get("clarify", ""))
    co, cr, cm = resolve_outcome(S, st)                 # resolve_outcome never raises
    w["co"], w["cr"], w["cmode"] = co, cr, cm
    w["ph"] = _b_s(st.get("ph", ""))
    w["dbg_step"] = "error"
    w["st"] = _b_dump(st)
    w["nx"] = nx
    return st, w


def _b_inputs(vars, R, st):
    spec = R.get("spec") or {}
    W = R.get("wiring") or {}
    call = dict()
    for d in spec.get("call_variables", {}).get("declared") or []:
        n = d.get("name", "")
        if n:
            call[n] = _b_s(vars.get(n, ""))
    sensors = {s: _b_s(vars.get(s, "")) for s in _b_sensor_names(spec)}
    nodes = [it.get("n") for it in (st.get("pm") or []) if it.get("n")]
    aw = st.get("await", "")
    if aw and aw in (W.get("nodes") or {}):
        nodes.append(aw)
    if st.get("vc"):
        nodes.append(st["vc"])
    results = dict()
    for n in nodes:
        nd = _b_node(W, n)
        tool = nd.get("tool", "")
        roles = ((W.get("roles") or {}).get(tool) or {}).get("res") or {}
        is_read = bool(roles.get("products"))
        r = dict()
        for role in (nd.get("res") or {}):
            if role == "products":
                r[role] = json.dumps(read_products(vars, W, n))
            else:
                r[role] = read_result(vars, W, n, role, tool_fallback=is_read)
        results[n] = r
    return {"call": call, "sensors": sensors, "results": results, "entered_from": "", "vf": _b_vfired(vars, W, st)}


def _b_vfired(vars, wiring, st):
    """Which identity-chain transition the graph took out of the awaited verify node: 'a' (account read),
    'l' (ID listen node) or ''. Same test as the graph (the mapped strings, one spelling per group); 'l' also needs
    a customer turn (ctl reset u_text before the verify node, so an empty one means the graph came back here)."""
    vc = wiring.get("vchain") or {}
    aw = st.get("await", "")
    if aw not in ((wiring.get("api") or {}).get("verify") or []):
        return ""
    res = _b_node(wiring, aw).get("res") or {}
    s, v, a = [_b_s(vars.get(res.get(k, ""))) for k in ("s", "verified", "all")]
    for t, f in zip(vc.get("t") or [], vc.get("f") or []):
        if s == t and v == t:
            if a == t and st.get("vc"):
                return "a"
            if a == f and st.get("vs") is not None and _b_s(vars.get("u_text")).strip():
                return "l"                              # ...and the ID listen node heard the customer
    return ""


def main(vars, rspec):
    """ctl entry point. rspec = hex string (as embedded) or dict. Reads/writes `vars` per CONTRACTS C.7.
    Writes vars['nx'] = <safe node> first and the real nx last. Never raises."""
    try:
        vars["nx"] = "s_safe"
        vars["dbg_step"] = "start"
    except Exception:
        return
    try:
        R = _b_dec(rspec)
        W = R.get("wiring") or {}
        vars["nx"] = (W.get("listen") or {}).get("safe", "s_safe")
        st = _b_load_st(vars.get("st"))
        inp = _b_inputs(vars, R, st)
        _, w = step(R, st, inp)
        nx = w.pop("nx", None) or (W.get("listen") or {}).get("safe", "s_safe")
        for k in sorted(w.keys()):
            vars[k] = _b_s(w[k])
        vars["nx"] = _b_s(nx)
    except Exception as e:
        try:
            vars["dbg_err"] = _b_s(e)[:200]
            vars["say"] = ""
            vars["nx"] = "s_safe"
        except Exception:
            pass
