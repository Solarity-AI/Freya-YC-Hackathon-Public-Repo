"""Generic call-flow runtime: the bank's flow drawing as data, run by code (no case content).

A Spec with mode "flow" carries spec.flow = {start, nodes {id: node}, global [...], on_error, on_unclear, ...}. The
ctl code node runs this interpreter on every entry: it reads the last bank-call result or the customer's reply
(typed sensors read by the phone model), walks the flow, and stops at the next bank call (an api node), the next
question (the listen node) or the last line (the bye node). Node types:
- call   {op, args {field: template}, save, next, on_status {"404": id}, on_error}
- branch {cases [{if: cond, next}], else}
- say    {text, parts [{if, text}], next}
- ask    {text, parts, choices [{id, keywords, next}], reask, on_fail}
- select {list, where, label, keys [{field, digits, ask}], ask, one, save, next, on_none, on_fail}
- set    {name, value, next}
- end    {text, parts}
Conditions: {op: eq|ne|gt|ge|lt|le, a, b} | {op: empty|nonempty, a} | {op: count_eq|count_gt|count_ge|count_lt, a, b}
| {op: and|or, args} | {op: not, arg} | {op: true}. An operand "$path" is a value (call.<var>, now, today,
<saved name>.<field>..., it.<field> inside select.where); anything else is a literal.
Templates: "<path|fmt:arg>" with fmt money[:CUR|$path], date, digits, last:n, spell, count, join[:field], or none.
Rules: Python 3.8 syntax; stdlib only; no double curly braces; private helpers prefixed _f_; main() never raises.
"""
import datetime
import json
import re

_F_MAXSTEP = 80
_F_RESET = dict(u_text="", u_en="", u_val="", u_intent="none", u_kind="none")
_F_ORD = dict(first=1, second=2, third=3, fourth=4, fifth=5, birinci=1, ilk=1, ikinci=2, ucuncu=3, dorduncu=4,
              besinci=5)
_F_YES = ("evet", "olur", "tabii", "tabi", "isterim", "lutfen", "dogru", "aynen", "yes", "sure", "please", "okay",
          "ok", "correct", "right")
_F_NO = ("hayir", "istemiyorum", "gerek yok", "istemem", "no", "nope", "don t", "do not")


def _f_s(v):
    try:
        return "" if v is None else (v if isinstance(v, str) else (json.dumps(v, ensure_ascii=False)
                                                                   if isinstance(v, (dict, list)) else str(v)))
    except Exception:
        return ""


def _f_has(v):
    s = _f_s(v).strip()
    return bool(s) and s.lower() not in ("none", "null", "nan", "undefined", "pending")


def _f_lit(v):
    """A mapped value: list / dict / number as it is; a JSON or Python-literal string parsed; else the string."""
    if isinstance(v, (list, dict, int, float)) and not isinstance(v, bool):
        return v
    s = _f_s(v).strip()
    if s[:1] in ("[", "{"):
        for f in (json.loads, lambda t: json.loads(t.replace("'", '"').replace("True", "true")
                                                   .replace("False", "false").replace("None", "null"))):
            try:
                return f(s)
            except Exception:
                pass
    return v


def _f_fold(s):
    try:
        from_ = "İIıŞşÇçĞğÜüÖöÂâÎîÛû"
        to = "iiissccgguuooaaiiuu"
        t = _f_s(s)
        t = "".join(to[from_.index(ch)] if ch in from_ else ch for ch in t).lower()
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9@._\- ]", " ", t)).strip()
    except Exception:
        return ""


def _f_num(v):
    """A number from an API value: 1250.5, '1250.50', '1.250,50', '1,250.50' -> float, else None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = _f_s(v).strip().replace(" ", "")
    s = re.sub(r"[^0-9.,\-]", "", s)
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if re.search(r",\d\d?$", s) else s.replace(",", "")
    elif s.count(".") > 1 or re.search(r"\.\d{3}$", s):
        s = s.replace(".", "") if not re.search(r"\.\d\d?$", s) else s
    try:
        return float(s)
    except Exception:
        return None


def _f_date(v):
    s = _f_s(v).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    try:
        if m:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.match(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})", s)
        if m:
            return datetime.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except Exception:
        return None
    return None


def _f_get(c, path):
    """The value at a dotted path: call.<var>, now, today, it.<f> (select item), <saved>.<field>.<index>..."""
    parts = [p for p in _f_s(path).strip().lstrip("$").split(".") if p != ""]
    if not parts:
        return None
    h = parts[0]
    if h == "now":
        cur = c["now_s"]
    elif h == "today":
        cur = c["today"].isoformat() if c.get("today") else ""
    elif h == "call":
        cur = c["call"]
    elif h == "it":
        cur = c.get("it")
    else:
        cur = c["st"].get("v", dict()).get(h)
    for p in parts[1:]:
        cur = _f_lit(cur)
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list):
            if p in ("length", "count"):
                cur = len(cur)
            elif re.match(r"^-?\d+$", p) and -len(cur) <= int(p) < len(cur):
                cur = cur[int(p)]
            else:
                return None
        else:
            return None
    return _f_lit(cur)


def _f_val(c, x):
    if isinstance(x, str) and x.startswith("$"):
        return _f_get(c, x[1:])
    return x


def _f_cmp(a, b):
    """-1/0/1 comparing numbers as numbers, ISO dates as dates, else folded text; None if either is missing."""
    if a is None or b is None:
        return None
    na, nb = _f_num(a), _f_num(b)
    da, db = _f_date(a), _f_date(b)
    if da is not None and db is not None:
        return (da > db) - (da < db)
    if na is not None and nb is not None and not (da or db):
        return (na > nb) - (na < nb)
    if isinstance(a, bool) or isinstance(b, bool) or _f_s(a).lower() in ("true", "false"):
        a, b = _f_s(a).lower(), _f_s(b).lower()
    fa, fb = _f_fold(a), _f_fold(b)
    return (fa > fb) - (fa < fb)


def _f_count(v):
    v = _f_lit(v)
    if isinstance(v, (list, dict)):
        return len(v)
    return 0 if not _f_has(v) else 1


def _f_cond(c, cd):
    try:
        if isinstance(cd, bool):
            return cd
        if not isinstance(cd, dict):
            return False
        op = _f_s(cd.get("op")).lower()
        if op == "true":
            return True
        if op == "and":
            return all(_f_cond(c, x) for x in cd.get("args") or [])
        if op == "or":
            return any(_f_cond(c, x) for x in cd.get("args") or [])
        if op == "not":
            return not _f_cond(c, cd.get("arg"))
        a = _f_val(c, cd.get("a"))
        if op == "empty":
            n = _f_num(a)
            return (not _f_has(a)) or _f_count(a) == 0 or (n is not None and n == 0 and
                                                            not isinstance(_f_lit(a), (list, dict)))
        if op == "nonempty":
            return not _f_cond(c, dict(op="empty", a=cd.get("a")))
        b = _f_val(c, cd.get("b"))
        if op.startswith("count_"):
            n, m = _f_count(a), _f_num(b)
            if m is None:
                return False
            return dict(eq=n == m, gt=n > m, ge=n >= m, lt=n < m, le=n <= m).get(op[6:], False)
        if op == "in":
            return any(_f_cmp(a, x) == 0 for x in (b if isinstance(b, list) else [b]))
        r = _f_cmp(a, b)
        if r is None:
            return op == "ne"
        return dict(eq=r == 0, ne=r != 0, gt=r > 0, ge=r >= 0, lt=r < 0, le=r <= 0).get(op, False)
    except Exception:
        return False


def _f_and(items, lang):
    items = [i for i in items if i]
    w = "ve" if lang == "tr" else "and"
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " " + w + " " + items[-1]


def _f_money(c, v, arg):
    n = _f_num(v)
    if n is None:
        return _f_s(v)
    F = c["F"]
    if _f_s(F.get("amount_unit")).lower() == "minor":
        n = n / 100.0
    cur = _f_s(_f_val(c, arg) if arg else F.get("currency") or "")
    lang = c["lang"]
    words = dict(F.get("currency_words") or dict())       # the Spec names the currencies (from the documents)
    cents = int(round(abs(n) * 100))
    th, dec = (".", ",") if lang in ("tr", "de", "es", "it", "nl", "pt", "da") else (",", ".")
    s = format(cents // 100, ",").replace(",", th)
    if cents % 100:
        s = s + dec + "%02d" % (cents % 100)
    word = words.get(cur.upper(), cur)
    return (("-" if n < 0 else "") + s + (" " + word if word else "")).strip()


def _f_datefmt(c, v):
    d = _f_date(v)
    if d is None:
        return _f_s(v)
    tr_m = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım",
            "Aralık"]
    tr_d = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
    en_m = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
            "November", "December"]
    en_d = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    t = c.get("today")
    y = (" %d" % d.year) if (t is not None and t.year != d.year) else ""
    if c["lang"] == "tr":
        return "%d %s%s %s" % (d.day, tr_m[d.month - 1], y, tr_d[d.weekday()])
    return "%s, %d %s%s" % (en_d[d.weekday()], d.day, en_m[d.month - 1], y)


def _f_fmt(c, v, fmt, arg):
    if fmt == "money":
        return _f_money(c, v, arg)
    if fmt == "date":
        return _f_datefmt(c, v)
    if fmt == "count":
        return str(_f_count(v))
    if fmt in ("digits", "last", "spell"):
        d = re.sub(r"\D", "", _f_s(v))
        if fmt == "last" or (fmt == "spell" and arg):
            try:
                d = d[-int(arg):]
            except Exception:
                pass
        return " ".join(d) if fmt == "spell" else d
    if fmt == "join":
        lst = _f_lit(v)
        if not isinstance(lst, list):
            return _f_s(v)
        vals = []
        for it in lst:
            x = it.get(arg) if (arg and isinstance(it, dict)) else it
            if _f_has(x) and _f_s(x) not in vals:
                vals.append(_f_s(x))
        return _f_and(vals, c["lang"])
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return _f_s(v)


def _f_tpl(c, text, extra=None):
    extra = extra or dict()

    def rep(m):
        body = m.group(1)
        if body in extra:
            return extra[body]
        path, _, f = body.partition("|")
        fmt, _, arg = f.partition(":")
        return _f_fmt(c, _f_get(c, path.strip()), fmt.strip(), arg.strip())
    try:
        return re.sub(r"<([^<>]+)>", rep, _f_s(text)).strip()
    except Exception:
        return _f_s(text)


def _f_text(c, nd, extra=None):
    out = []
    if _f_has(nd.get("text")):
        out.append(_f_tpl(c, nd.get("text"), extra))
    for p in nd.get("parts") or []:
        if isinstance(p, dict) and _f_cond(c, p.get("if", dict(op="true"))):
            out.append(_f_tpl(c, p.get("text"), extra))
    return " ".join(x for x in out if x)


# ------------------------------------------------------------------------------------------- the customer's reply
def _f_kw(c, kws):
    """True when any keyword (folded, whole-word prefix) is in the customer's own words or the English rendering."""
    hay = " " + c["ftext"] + " " + c["fen"] + " "
    for k in kws or []:
        fk = _f_fold(k)
        if fk and re.search(r"(?<![a-z0-9])" + re.escape(fk), hay):
            return True
    return False


def _f_yesno(c):
    """yes / no from the model's reading (u_kind), else from the words when only one side is present."""
    k = c["kind"]
    if k in ("yes", "no"):
        return k
    y, n = _f_kw(c, _F_YES), _f_kw(c, _F_NO)
    if y != n:
        return "yes" if y else "no"
    return ""


def _f_pick_choice(c, choices):
    """The choice the reply picks: the model's reading (u_intent), then the choices' words, then yes / no. A hedge
    ('I guess', 'maybe') is never a yes."""
    hedge = c["kind"] == "hedge"
    choices = [ch for ch in choices if not (hedge and (_f_s(ch.get("id")) == "yes" or _f_s(ch.get("when")) == "yes"))]
    ids = [_f_s(ch.get("id")) for ch in choices]
    if c["intent"] in ids:
        return choices[ids.index(c["intent"])]
    if hedge:
        return None
    hits = [ch for ch in choices if _f_kw(c, ch.get("keywords"))]
    if len(hits) == 1:
        return hits[0]
    yn = _f_yesno(c)
    for ch in choices:
        if yn and (_f_s(ch.get("id")) == yn or _f_s(ch.get("when")) == yn):
            return ch
    return hits[0] if hits else None


def _f_ahead(c, nd):
    """The customer answered a question that comes next ('change it?' -> 'the third week'): the one choice of this
    node whose path (through say / set / branch / a bank call's success) reaches an ask node with a choice the model
    read (u_intent). Never for a bare yes / no (that answers the question in hand), and only when one path fits."""
    if not c["intent"] or c["kind"] == "hedge" or c["intent"] in ("yes", "no"):
        return None
    nodes = c["F"].get("nodes") or dict()
    hits = []
    for ch in nd.get("choices") or []:
        todo, seen = [ch.get("next")], set()
        while todo and len(seen) < 24:        # every branch path: the data a later call fetches is not known yet
            nid = todo.pop(0)
            n = nodes.get(nid)
            if nid in seen or not isinstance(n, dict):
                continue
            seen.add(nid)
            t = _f_s(n.get("type"))
            if t == "ask":
                ids = [_f_s(x.get("id")) for x in n.get("choices") or []]
                if c["intent"] in ids:
                    hits.append(ch)
                    break
                if "yes" in ids:                # naming the later answer says yes to a yes / no step on the way
                    todo.append([x for x in n.get("choices") or [] if _f_s(x.get("id")) == "yes"][0].get("next"))
            elif t == "branch":
                todo += [cs.get("next") for cs in n.get("cases") or [] if isinstance(cs, dict)] + [n.get("else")]
            elif t in ("say", "set", "call"):
                todo.append(n.get("next"))
    return hits[0] if len(hits) == 1 else None


def _f_global(c, nd, by_words=True):
    """A flow-wide intent (transfer, goodbye, a question with a fixed answer): the model's reading (u_intent) names
    it, or (by_words) its keywords are in the reply. A choice of the node itself with the same id wins."""
    own = [_f_s(ch.get("id")) for ch in (nd or dict()).get("choices") or []]
    gl = [g for g in c["F"].get("global") or [] if _f_s(g.get("id")) and _f_s(g.get("id")) not in own]
    for g in gl:
        if c["intent"] == _f_s(g.get("id")):
            if _f_ends(c, g) and g.get("keywords") and not _f_kw(c, g.get("keywords")):
                return None         # a call-ending reading the customer's words do not show: not acted on
            return g
    if by_words and c["intent"] in ("", "none"):
        for g in gl:
            if _f_kw(c, g.get("keywords")):
                return g
    return None


def _f_ends(c, g):
    """True when the intent ends the call: it goes (through say / set nodes) to an end node."""
    nodes = c["F"].get("nodes") or dict()
    nid = g.get("next")
    for _ in range(6):
        n = nodes.get(nid)
        if not isinstance(n, dict):
            return False
        if n.get("type") == "end":
            return True
        if n.get("type") not in ("say", "set"):
            return False
        nid = n.get("next")
    return False


# ------------------------------------------------------------------------------------------------ select (lists)
def _f_items(c, nd):
    lst = _f_lit(_f_get(c, nd.get("list")))
    if isinstance(lst, dict):
        lst = [lst]
    if not isinstance(lst, list):
        return []
    out = []
    for i, it in enumerate(lst):
        c["it"] = it
        if not nd.get("where") or _f_cond(c, nd.get("where")):
            out.append(i)
    c["it"] = None
    return out


def _f_item(c, nd, i):
    lst = _f_lit(_f_get(c, nd.get("list")))
    lst = [lst] if isinstance(lst, dict) else lst
    return lst[i] if isinstance(lst, list) and 0 <= i < len(lst) else None


def _f_label(c, nd, it):
    """An item's spoken label: the field `label`, or a template over <it.field> paths."""
    lab = _f_s(nd.get("label"))
    if "<" in lab:
        c["it"] = it
        s = _f_tpl(c, lab)
        c["it"] = None
        return s
    return _f_s(it.get(lab) if isinstance(it, dict) else it)


def _f_by_label(c, nd, cands):
    """The candidates whose label the customer named (best overlap on the words that tell labels apart), or an
    ordinal; [] when unclear."""
    labels = [(i, _f_label(c, nd, _f_item(c, nd, i))) for i in cands]
    hay = (" " + c["ftext"] + " " + c["fen"] + " ")
    toks = dict((i, [t for t in _f_fold(lab).split() if len(t) >= 3 or t.isdigit()]) for i, lab in labels)
    distinct_labs = set(_f_fold(lab) for _, lab in labels)
    common = None
    for i, _ in labels:
        common = set(toks[i]) if common is None else common & set(toks[i])
    common = common or set()
    best, top = [], 0
    for i, lab in labels:
        tk = [t for t in toks[i] if t not in common or len(distinct_labs) == 1]
        sc = sum(1 for t in tk if re.search(r"(?<![a-z0-9])" + re.escape(t[:6]), hay))
        if sc and sc == top:
            best.append(i)
        elif sc > top:
            best, top = [i], sc
    if best:
        # several items share the winning label text: keep all of them (asked apart by the keys)
        names = set(_f_fold(lab) for i, lab in labels if i in best)
        return [i for i, lab in labels if _f_fold(lab) in names]
    distinct = []
    for i, lab in labels:
        if _f_fold(lab) not in [_f_fold(x[1]) for x in distinct]:
            distinct.append((i, lab))
    n = None
    for w, k in _F_ORD.items():
        if re.search(r"(?<![a-z])" + w, hay):
            n = k
    if re.search(r"(?<![a-z])(last|sonuncu|en son)", hay):
        n = len(distinct)
    if n and 1 <= n <= len(distinct):
        lab = _f_fold(distinct[n - 1][1])
        return [i for i, x in labels if _f_fold(x) == lab]
    return []


def _f_by_digits(c, nd, cands, key):
    d = re.sub(r"\D", "", c["val"]) or re.sub(r"\D", "", c["text"])
    if not d:
        return []
    n = int(key.get("digits") or 0) or len(d)
    d = d[-n:] if len(d) > n else d
    out = []
    for i in cands:
        it = _f_item(c, nd, i) or dict()
        fv = re.sub(r"\D", "", _f_s(it.get(key.get("field")) if isinstance(it, dict) else it))
        if fv and len(d) >= min(n, 2) and fv.endswith(d):
            out.append(i)
    return out


def _f_sel_ask(c, nd, sel):
    cands = sel["cands"]
    k = int(sel.get("k", -1))
    if k < 0:
        opts = []
        for i in cands:
            lab = _f_label(c, nd, _f_item(c, nd, i))
            if lab and lab not in opts:
                opts.append(lab)
        return _f_tpl(c, nd.get("ask"), dict(options=_f_and(opts, c["lang"])))
    keys = nd.get("keys") or []
    return _f_tpl(c, (keys[k] if k < len(keys) else dict()).get("ask"))


def _f_sel_done(c, nd, i):
    c["st"].setdefault("v", dict())[nd.get("save") or "selected"] = _f_item(c, nd, i)
    c["st"].pop("sel", None)
    return nd.get("next")


def _f_sel_next(c, nd, sel):
    """Narrowed to sel['cands']: done when one is left, else ask the label (k -1) or the next key that still tells
    them apart; 'fail' when nothing can."""
    cands = sel["cands"]
    if len(cands) == 1:
        return "go", _f_sel_done(c, nd, cands[0])
    keys = nd.get("keys") or []
    k = int(sel.get("k", -1))
    if k < 0:
        labs = set(_f_fold(_f_label(c, nd, _f_item(c, nd, i))) for i in cands)
        if len(labs) > 1:
            return "ask", None
        k = 0
    while k < len(keys):
        n = int(keys[k].get("digits") or 0)
        vals = set()
        for i in cands:
            it = _f_item(c, nd, i)
            d = re.sub(r"\D", "", _f_s(it.get(keys[k].get("field")) if isinstance(it, dict) else it))
            vals.add(d[-n:] if n else d)
        if len(vals) > 1 or k == len(keys) - 1:
            sel["k"] = k
            return "ask", None
        k += 1
    return "fail", None


# ------------------------------------------------------------------------------------------------- the machine
def _f_goto(c, nid):
    c["st"]["pc"] = _f_s(nid)


def _f_end(c, text):
    c["say"].append(text)
    c["st"]["pc"] = ""
    c["st"]["over"] = 1
    c["nx"] = c["W"].get("bye", "s_bye")


def _f_fail(c, key):
    """Go to the flow's on_error / on_unclear node, or end with the matching line."""
    F = c["F"]
    nid = F.get(key)
    if nid and nid in (F.get("nodes") or dict()) and c["st"].get("pc") != nid:
        _f_goto(c, nid)
        return True
    _f_end(c, _f_tpl(c, (c["S"].get("lines") or dict()).get("goodbye") or ""))
    return False


def _f_call(c, nd):
    W = c["W"]
    op = (W.get("ops") or dict()).get(_f_s(nd.get("op")))
    if not op:
        return _f_fail(c, "on_error")
    for field, var in (op.get("body") or dict()).items():
        tpl = (nd.get("args") or dict()).get(field)
        if tpl is None:
            continue
        v = _f_val(c, tpl) if isinstance(tpl, str) and tpl.startswith("$") else _f_tpl(c, tpl)
        c["w"][var] = _f_s(v)
    for var in (op.get("res") or dict()).values():
        c["w"][var] = ""
    c["st"]["aw"] = op.get("node")
    c["st"]["call"] = c["st"].get("pc")
    c["nx"] = op.get("node")
    c["st"]["ncalls"] = int(c["st"].get("ncalls", 0)) + 1
    return False


def _f_status(c, op):
    V = c["vars"]
    for k in (op.get("fname", "") + "_status_code", op.get("node", "") + "_status_code",
              op.get("fname", "") + "_response.status_code", op.get("node", "") + "_response.status_code"):
        n = _f_num(V.get(k))
        if n is not None:
            return int(n)
    return None


def _f_result(c):
    """The awaited api node returned: save its fields, route by HTTP status / success."""
    st = c["st"]
    nid = st.pop("call", "")
    st.pop("aw", None)
    F = c["F"]
    nd = (F.get("nodes") or dict()).get(nid) or dict()
    op = (c["W"].get("ops") or dict()).get(_f_s(nd.get("op"))) or dict()
    V = c["vars"]
    body = dict()
    for field, var in (op.get("res") or dict()).items():
        names = [var]
        for p in (op.get("fname", ""), op.get("node", "")):
            if p and p + "_response.data." + field not in names:
                names.append(p + "_response.data." + field)
        v = _f_read(V, names)
        if v is not None:
            body[field] = v
    code = _f_status(c, op)
    name = nd.get("save") or _f_s(nd.get("op"))
    st.setdefault("v", dict())[name] = body
    st["v"].setdefault("_status", dict())[name] = code
    bcode = _f_s(_f_get(c, name + "." + _f_s(nd.get("code")).lstrip("$").split(".", 1)[-1])) if nd.get("code") else ""
    ons = dict((_f_s(k), v) for k, v in (nd.get("on_status") or dict()).items())
    for k in (_f_s(code) if code is not None else "", bcode):
        if k and k in ons:
            _f_goto(c, ons[k])
            return
    ok = (200 <= code < 300) if code is not None else bool(body)
    if ok and nd.get("ok_if"):
        ok = _f_cond(c, nd.get("ok_if"))
    if ok:
        _f_goto(c, nd.get("next"))
    elif nd.get("on_error"):
        _f_goto(c, nd.get("on_error"))
    else:
        _f_fail(c, "on_error")


def _f_listify(x):
    """Dicts whose keys are all indexes back into lists (flattened '...cards.0.x' keys)."""
    if isinstance(x, dict):
        x = dict((k, _f_listify(v)) for k, v in x.items())
        if x and all(re.match(r"^\d+$", _f_s(k)) for k in x):
            return [x[k] for k in sorted(x, key=int)]
    return x


def _f_read(V, names):
    """A mapped answer field in whatever form the engine stored it: the variable as an object, a JSON or Python-literal
    text, or the engine's own flattened keys ('<name>.a.0.b' / '<name>[0].b'); a plain value last. None if absent."""
    for n in names:
        lv = _f_lit(V.get(n))
        if isinstance(lv, (dict, list)):
            return lv
    for n in names:
        root = dict()
        for k in list(V.keys()):
            ks = _f_s(k)
            if not (ks.startswith(n + ".") or ks.startswith(n + "[")):
                continue
            parts = [x for x in re.split(r"[.\[\]]+", ks[len(n):]) if x != ""]
            cur = root
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    cur[part] = V.get(k)
                else:
                    nxt = cur.get(part)
                    if not isinstance(nxt, dict):
                        nxt = dict()
                        cur[part] = nxt
                    cur = nxt
        if root:
            return _f_listify(root)
    for n in names:
        if _f_has(V.get(n)):
            return _f_lit(V.get(n))
    return None


def _f_listen(c, q):
    st = c["st"]
    st["q"] = q
    c["say"].append(q)
    c["nx"] = c["W"].get("listen", "s_flow")


def _f_run(c):
    """Walk the flow from st.pc until a bank call, a question or the end."""
    st, F = c["st"], c["F"]
    nodes = F.get("nodes") or dict()
    for _ in range(_F_MAXSTEP):
        if c["nx"]:
            return
        nid = st.get("pc", "")
        nd = nodes.get(nid)
        if not isinstance(nd, dict):
            _f_end(c, _f_tpl(c, (c["S"].get("lines") or dict()).get("goodbye") or ""))
            return
        t = _f_s(nd.get("type"))
        if t == "say":
            s = _f_text(c, nd)
            if s:
                c["say"].append(s)
            _f_goto(c, nd.get("next"))
        elif t == "branch":
            nxt = nd.get("else")
            for cs in nd.get("cases") or []:
                if isinstance(cs, dict) and _f_cond(c, cs.get("if")):
                    nxt = cs.get("next")
                    break
            _f_goto(c, nxt)
        elif t == "set":
            v = nd.get("value")
            st.setdefault("v", dict())[_f_s(nd.get("name"))] = (_f_val(c, v) if isinstance(v, str) and
                                                                v.startswith("$") else _f_tpl(c, v))
            _f_goto(c, nd.get("next"))
        elif t == "call":
            _f_call(c, nd)
            if not c["nx"] and st.get("pc") == nid:
                return
        elif t == "ask":
            st["re"] = 0
            ah = st.pop("ahead", None)
            ch = [x for x in nd.get("choices") or [] if ah and _f_s(x.get("id")) == ah]
            if ah and not ch:
                ch = [x for x in nd.get("choices") or [] if _f_s(x.get("id")) == "yes"]
                if ch:
                    st["ahead"] = ah            # a yes / no step on the way: yes, the answer is still ahead
            if ch:
                if ch[0].get("say"):
                    c["say"].append(_f_tpl(c, ch[0].get("say")))
                _f_goto(c, ch[0].get("next"))
                continue
            _f_listen(c, _f_text(c, nd))
        elif t == "select":
            cands = _f_items(c, nd)
            if not cands:
                _f_goto(c, nd.get("on_none") or nd.get("on_fail"))
                continue
            sel = dict(node=nid, cands=cands, k=-1)
            if len(cands) == 1:
                if _f_has(nd.get("one")):
                    c["it"] = _f_item(c, nd, cands[0])
                    c["say"].append(_f_tpl(c, nd.get("one")))
                    c["it"] = None
                _f_goto(c, _f_sel_done(c, nd, cands[0]))
                continue
            what, nxt = _f_sel_next(c, nd, sel)
            if what == "go":
                _f_goto(c, nxt)
                continue
            if what == "fail":
                _f_goto(c, nd.get("on_fail"))
                continue
            st["sel"] = sel
            st["re"] = 0
            _f_listen(c, _f_sel_ask(c, nd, sel))
        elif t == "end":
            _f_end(c, _f_text(c, nd))
        else:
            _f_end(c, _f_tpl(c, (c["S"].get("lines") or dict()).get("goodbye") or ""))
    if not c["nx"]:
        _f_fail(c, "on_error")


def _f_reask(c, nd):
    st, F = c["st"], c["F"]
    st["re"] = int(st.get("re", 0)) + 1
    if st["re"] > int(F.get("max_reasks") or 2):
        st.pop("sel", None)
        if nd.get("on_fail"):
            _f_goto(c, nd.get("on_fail"))
        else:
            _f_fail(c, "on_unclear")
        return
    lines = c["S"].get("lines") or dict()
    pre = _f_tpl(c, nd.get("reask") or lines.get("clarify") or "")
    q = st.get("q", "")
    if st.get("sel"):
        q = _f_sel_ask(c, nd, st["sel"])
    c["say"].append(pre)
    _f_listen(c, q)


def _f_reply(c):
    """The customer answered the question of node st.pc."""
    st, F = c["st"], c["F"]
    nid = st.get("pc", "")
    nd = (F.get("nodes") or dict()).get(nid) or dict()
    lines = c["S"].get("lines") or dict()
    if c["kind"] == "repeat" or c["intent"] == "repeat":
        c["say"].append(st.get("q", ""))
        c["nx"] = c["W"].get("listen", "s_flow")
        return
    if c["kind"] == "hold":
        c["say"].append(_f_tpl(c, lines.get("hold") or lines.get("ack") or ""))
        c["nx"] = c["W"].get("listen", "s_flow")
        return
    g = _f_global(c, nd, by_words=False)
    if g and g.get("resume") and c["kind"] != "question" and _f_s(nd.get("type")) == "ask" and [
            x for x in nd.get("choices") or [] if _f_kw(c, x.get("keywords"))]:
        g = None            # an answer to the question in hand, not a question: the node's own choice wins
    if g:
        _f_take_global(c, g)
        return
    t = _f_s(nd.get("type"))
    if t == "ask":
        ids = [_f_s(x.get("id")) for x in nd.get("choices") or []]
        ch = None
        if c["intent"] and c["intent"] not in ids:
            ch = _f_ahead(c, nd)                        # the model read an answer to the next question
            if ch is not None:
                st["ahead"] = c["intent"]
        if ch is None:
            ch = _f_pick_choice(c, nd.get("choices") or [])
        if ch is None:
            g = _f_global(c, nd)
            if g:
                _f_take_global(c, g)
                return
            _f_reask(c, nd)
            return
        if ch.get("say"):
            c["say"].append(_f_tpl(c, ch.get("say")))
        _f_goto(c, ch.get("next"))
        return
    if t == "select" and st.get("sel"):
        sel = st["sel"]
        k = int(sel.get("k", -1))
        keys = nd.get("keys") or []
        got = []
        if k < 0:
            got = _f_by_label(c, nd, sel["cands"])
            if not got:
                for key in keys:
                    got = _f_by_digits(c, nd, sel["cands"], key)
                    if got:
                        break
        else:
            got = _f_by_digits(c, nd, sel["cands"], keys[k]) if k < len(keys) else []
        if not got or len(got) == len(sel["cands"]) and k >= 0:
            g = _f_global(c, nd)
            if g:
                _f_take_global(c, g)
                return
            _f_reask(c, nd)
            return
        if len(got) == len(sel["cands"]):
            _f_reask(c, nd)
            return
        st["re"] = 0
        sel["cands"] = got
        if k >= 0 and len(got) > 1:
            sel["k"] = k + 1
        what, nxt = _f_sel_next(c, nd, sel)
        if what == "go":
            _f_goto(c, nxt)
            return
        if what == "fail":
            st.pop("sel", None)
            _f_goto(c, nd.get("on_fail"))
            return
        _f_listen(c, _f_sel_ask(c, nd, sel))
        return
    g = _f_global(c, nd)
    if g:
        _f_take_global(c, g)
        return
    _f_goto(c, nid)


def _f_take_global(c, g):
    st = c["st"]
    if g.get("say") and (g.get("resume") or not g.get("next")):
        c["say"].append(_f_tpl(c, g.get("say")))
        q = st.get("q", "")
        if st.get("sel"):
            nd = ((c["F"].get("nodes") or dict()).get(st.get("pc")) or dict())
            q = _f_sel_ask(c, nd, st["sel"])
        c["say"].append(q)
        c["nx"] = c["W"].get("listen", "s_flow")
        return
    if g.get("say"):
        c["say"].append(_f_tpl(c, g.get("say")))
    st.pop("sel", None)
    _f_goto(c, g.get("next"))


def _f_ctx(R, st, vars):
    S = R.get("spec") or dict()
    W = R.get("wiring") or dict()
    call = dict()
    for d in (S.get("call_variables") or dict()).get("declared") or []:
        n = _f_s((d or dict()).get("name"))
        if n:
            call[n] = _f_s(vars.get(n, ""))
    nowv = (S.get("call_variables") or dict()).get("now") or "now"
    now_s = _f_s(vars.get(nowv, "")) or _f_s(call.get(nowv, ""))
    today = _f_date(now_s)
    lang = _f_s((S.get("bank") or dict()).get("language") or "en").lower()[:2]
    sens = dict((k, _f_s(vars.get(k, ""))) for k in _F_RESET)
    kind = _f_fold(sens.get("u_kind"))
    intent = _f_s(sens.get("u_intent")).strip()
    c = dict(R=R, S=S, F=S.get("flow") or dict(), W=W, st=st, vars=vars, call=call, now_s=now_s, today=today,
             lang=lang, w=dict(), say=[], nx="", it=None, text=sens.get("u_text", ""),
             ftext=_f_fold(sens.get("u_text")), fen=_f_fold(sens.get("u_en")),
             val=sens.get("u_val", "") if _f_has(sens.get("u_val")) else "",
             kind=kind if kind not in ("", "none") else "", intent=intent if intent.lower() != "none" else "")
    return c


def step(R, st, vars):
    """-> (new state, writes). Never raises."""
    c = _f_ctx(R, st, vars)
    st = c["st"]
    F = c["F"]
    try:
        if st.get("over"):
            _f_end(c, "")
        elif st.get("aw"):
            _f_result(c)
            _f_run(c)
        elif not st.get("started"):
            st["started"] = 1
            g = _f_global(c, dict()) if (c["text"] or c["intent"]) else None
            _f_goto(c, F.get("start"))
            if g and g.get("next") and not g.get("resume"):
                if g.get("say"):
                    c["say"].append(_f_tpl(c, g.get("say")))
                _f_goto(c, g.get("next"))
            _f_run(c)
        else:
            st["turns"] = int(st.get("turns", 0)) + 1
            if st["turns"] > int(F.get("turn_cap") or (c["S"].get("turn_cap") or 40)):
                _f_fail(c, "on_unclear")
            else:
                _f_reply(c)
            _f_run(c)
    except Exception as e:
        c["w"]["dbg_err"] = _f_s(e)[:200]
        st["errs"] = int(st.get("errs", 0)) + 1
        if st["errs"] >= 2 or not st.get("q"):
            c["say"] = [_f_tpl(c, (c["S"].get("lines") or dict()).get("goodbye") or "")]
            st["over"] = 1
            c["nx"] = c["W"].get("bye", "s_bye")
        else:
            c["say"] = [_f_tpl(c, (c["S"].get("lines") or dict()).get("clarify") or ""), st.get("q", "")]
            c["nx"] = c["W"].get("listen", "s_flow")
    w = c["w"]
    if c["nx"] in (c["W"].get("listen", "s_flow"), c["W"].get("bye", "s_bye")):
        for k, v in _F_RESET.items():
            w[k] = v
        w["say"] = " ".join(s for s in c["say"] if s).strip()
    elif c["say"]:
        st["carry"] = (st.get("carry") or []) + [s for s in c["say"] if s]
    if c["nx"] in (c["W"].get("listen", "s_flow"), c["W"].get("bye", "s_bye")) and st.get("carry"):
        w["say"] = (" ".join(st.pop("carry")) + " " + w.get("say", "")).strip()
    w["st"] = json.dumps(st, ensure_ascii=False, separators=(",", ":"))
    w["nx"] = c["nx"] or c["W"].get("safe", "s_safe")
    w["dbg_step"] = "flow:" + _f_s(st.get("pc")) + ":" + _f_s(w["nx"])
    return st, w


def _f_dec(rspec):
    if isinstance(rspec, dict):
        return rspec
    s = _f_s(rspec).strip()
    if s[:1] == "{":
        return json.loads(s)
    return json.loads(bytes.fromhex(s).decode("utf-8"))


def main(vars, rspec):
    """ctl entry point (flow mode). Writes vars['nx'] = the safe node first and the real nx last. Never raises."""
    try:
        vars["nx"] = "s_safe"
        vars["dbg_step"] = "start"
    except Exception:
        return
    try:
        R = _f_dec(rspec)
        W = R.get("wiring") or dict()
        vars["nx"] = W.get("safe", "s_safe")
        raw = _f_s(vars.get("st", "")).strip()
        st = json.loads(raw) if raw[:1] == "{" else dict()
        _, w = step(R, st, vars)
        nx = w.pop("nx", None) or W.get("safe", "s_safe")
        for k in sorted(w.keys()):
            vars[k] = _f_s(w[k])
        vars["nx"] = _f_s(nx)
    except Exception as e:
        try:
            vars["dbg_err"] = _f_s(e)[:200]
            vars["nx"] = "s_safe"
        except Exception:
            pass
