"""Compile-time text: system prompt, opening tts, fixed lines, extraction schemas (docs/CONTRACTS.md B.2, D.3, D.4).
Owner: agent 3.

Everything here is generic: values come from the Spec only.
"""
import re

from builder.spec import defaults as _defaults
from builder.spec import vocab


class RenderError(Exception):
    pass


LANGUAGES = {"en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian", "nl": "Dutch",
             "pt": "Portuguese", "tr": "Turkish", "pl": "Polish", "sv": "Swedish", "da": "Danish"}

_PH_RE = re.compile(r"<([^<>\s]+)>")
_VAR_RE = re.compile(r"^[A-Za-z_]\w*$", re.A)  # re.A: \w is [A-Za-z0-9_]


def _declared(spec):
    return [d.get("name", "") for d in (spec.get("call_variables") or {}).get("declared") or []]


def _bank_name(spec):
    return str((spec.get("bank") or {}).get("name") or "")


def _self_text(spec):
    s = str((spec.get("bank") or {}).get("assistant_self") or "")
    return s.replace("<bank>", _bank_name(spec))


def _var(name, spec):
    if not _VAR_RE.match(name):
        raise RenderError(f"bad call variable name {name!r}")
    if name not in _declared(spec):
        raise RenderError(f"<v:{name}> is not a declared call variable")
    return "{{" + name + "}}"


def compile_line(template, spec):
    """Render <bank> <self> <customer> <v:X> into Freya text ({{X}}). Runtime-only placeholders -> RenderError."""
    if template is None:
        return ""
    text = str(template)
    if "{{" in text or "}}" in text:
        raise RenderError(f"Freya braces are not allowed in a Spec line: {text!r}")

    def sub(m, depth=0):
        ph = m.group(1)
        if ph == "bank":
            return _bank_name(spec)
        if ph == "self":
            return _self_text(spec)
        if ph == "customer":
            cust = str((spec.get("addressing") or {}).get("customer") or "")
            if "<customer>" in cust:
                raise RenderError("addressing.customer refers to itself")
            return _PH_RE.sub(sub, cust)
        if ph.startswith("v:"):
            return _var(ph[2:], spec)
        if ph.startswith("f:") or ph in vocab.PLACEHOLDERS:
            raise RenderError(f"runtime-only placeholder <{ph}> in a compile-time line: {text!r}")
        raise RenderError(f"unknown placeholder <{ph}> in {text!r}")

    out = _PH_RE.sub(sub, text)
    return re.sub(r"\s+", " ", out).strip()


def strip_runtime(template, spec):
    """Like compile_line, but runtime-only placeholders are removed (used by lint on runtime lines)."""
    text = str(template or "")

    def sub(m):
        ph = m.group(1)
        try:
            return compile_line("<" + ph + ">", spec)
        except RenderError:
            return ""
    return re.sub(r"\s+", " ", _PH_RE.sub(sub, text)).strip()


def check_placeholders(template, spec):
    """-> list of problems with the placeholders of a Spec line (unknown names, undeclared <v:X>, braces)."""
    text = str(template or "")
    probs = []
    if "{{" in text or "}}" in text:
        probs.append("Freya braces in a Spec line")
    for ph in _PH_RE.findall(text):
        if ph.startswith("v:"):
            if not _VAR_RE.match(ph[2:]) or ph[2:] not in _declared(spec):
                probs.append(f"<{ph}> is not a declared call variable")
        elif ph.startswith("f:"):
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", ph[2:]):
                probs.append(f"bad field placeholder <{ph}>")
        elif ph not in vocab.PLACEHOLDERS:
            probs.append(f"unknown placeholder <{ph}>")
    return probs


def open_line(spec):
    """opening.line + ' ' + right_party.ask, compile-rendered."""
    first = compile_line((spec.get("opening") or {}).get("line") or "", spec)
    ask = compile_line((spec.get("right_party") or {}).get("ask") or "", spec)
    return (first + " " + ask).strip()


def open_task(spec):
    return "Say exactly this and nothing else, and do not call any tool: «" + open_line(spec) + "»"


def clarify_line(spec):
    lines = spec.get("lines") or {}
    return compile_line(lines.get("clarify") or _defaults.DEFAULT_LINES["clarify"], spec)


def system_prompt(spec):
    """Workflow system prompt: persona, language, 'never call a tool', 'repeat exactly the line you are given'."""
    bank = spec.get("bank") or {}
    lang = LANGUAGES.get(str(bank.get("language") or "en").lower()[:2], str(bank.get("language") or "English"))
    who = _self_text(spec) or "a digital assistant"
    parts = [
        f"You are {who}, speaking on the phone with a customer. Speak {lang}.",
        "Every line you say is given to you by the workflow. Say exactly the line you are given and nothing else.",
        "Never call a tool. Tool calls are made by the workflow, not by you.",
        "Never invent facts, amounts, dates or offers.",
        "Never mention the reason for the call, any account, product or amount before you are told that the "
        "identity check has passed.",
        "Keep every turn short.",
    ]
    return " ".join(parts)


# ------------------------------------------------------------------------------------------------ extraction (D.4)

U_TEXT_DESC = "The customer's most recent message, copied word for word, including numbers exactly as spoken."
U_ACT_DESC = ("Classify ONLY the most recent customer message. If it contains any answer to the agent's question, "
              "choose that answer; ignore small talk. yes: agrees or confirms. no: declines or denies. "
              "proposal: offers a day, a time or an amount. answer: answers a question with information. "
              "question: asks something. refuse: refuses to answer or to continue. chatter_only: small talk only. "
              "unclear: none of these.")
SLOT_DESC = {
    "u_date": "The day the customer proposes in this message, as said. Empty if none.",
    "u_amt": "The amount the customer proposes in this message, as said. Empty if none.",
    "u_time": "The time of day offered in this message, as said. Empty if none.",
    "u_ans": "The answer to the security question in this message only, as said. Empty if none.",
}
SLOT_CONF = 0.4
STAGES = ("rp", "tp", "id", "neg", "conf", "safe")


def _clean(s):
    s = str(s or "").replace("{{", "(").replace("}}", ")").replace('"', "'")
    return re.sub(r"\s+", " ", s).strip()


def _topic_entries(stage, spec):
    """Ordered (id, description, examples, negatives) for a stage, before the cap."""
    interp = spec.get("interpretation") or {}
    tie = list(interp.get("intent_tie") or [])
    intents = [it for it in spec.get("intents") or [] if stage in (it.get("scope") or [])]
    order = {it.get("id"): i for i, it in enumerate(spec.get("intents") or [])}

    def key(it):
        iid = it.get("id")
        return (-int(it.get("precedence") or 0), tie.index(iid) if iid in tie else len(tie), order.get(iid, 0))
    out, seen = [], set()
    for it in sorted(intents, key=key):
        iid = str(it.get("id") or "")
        if not iid or iid in seen:
            continue
        seen.add(iid)
        out.append((iid, it.get("description") or it.get("label") or iid, it.get("examples") or [],
                    it.get("negatives") or []))
    for bt in _defaults.BUILTIN_TOPICS.get(stage, []):
        if bt["id"] in seen:
            continue
        seen.add(bt["id"])
        out.append((bt["id"], bt.get("description") or bt["id"], bt.get("examples") or [], bt.get("negatives") or []))
    return out


def topic_values(stage, spec):
    """Ordered u_topic enum for a stage: Spec intents in scope (by precedence) + BUILTIN_TOPICS + 'none', <= 12."""
    if stage not in ("rp", "tp", "id", "neg", "conf"):
        return []
    entries = _topic_entries(stage, spec)
    cap = vocab.TOPIC_CAP - 1
    if len(entries) > cap:
        dropped = [e[0] for e in entries[cap:]]
        from builder import trace                       # trace.event never raises
        trace.event("DECISION", f"u_topic[{stage}] capped at {vocab.TOPIC_CAP}; regex backstop covers "
                    + ", ".join(dropped), where="LOCAL")
        entries = entries[:cap]
    return [e[0] for e in entries] + ["none"]


def _topic_description(stage, spec, values):
    by_id = {e[0]: e for e in _topic_entries(stage, spec)}
    parts = ["The topic of the most recent customer message. Choose none if no topic fits. "
             "If several topics fit, choose the first one listed."]
    for v in values:
        if v == "none":
            continue
        _, desc, ex, neg = by_id[v]
        item = f"{v}: {_clean(desc)}"
        extra = []
        if ex:
            extra.append("e.g. " + "; ".join('"' + _clean(x) + '"' for x in ex[:2]))
        if neg:
            extra.append("not " + '"' + _clean(neg[0]) + '"')
        if extra:
            item += " (" + "; ".join(extra) + ")"
        parts.append(item + ".")
    return " ".join(parts)


# Non-English calls (Spec bank.language != en): the extractor reads any language, so the model reads the values
# (typed, normalised) and code validates them (runtime/brain._b_mv_*, runtime/ident.id_model). The extractor's
# clock is the real one, not the call's `now`: it never resolves a relative day, code does (runtime/cal).
U_EN_DESC = ("The customer's most recent message translated into plain English with the same meaning. Write numbers "
             "as digits (1,250). Keep days as said ('next Friday', 'tomorrow', 'the 23rd', 'payday'); never turn "
             "them into a calendar date. Empty if the message is empty.")
MV_FIELDS = {
    "u_val": ("The answer to the security question the agent just asked, normalised: a date as YYYY-MM-DD (only "
              "when day, month and year were all said); a year as YYYY; a number or digit sequence as digits only "
              "(number words turned into digits, in the order said); a code as its letters and digits in upper case "
              "without spaces; a name or word exactly as said. Empty if the message gives no answer.", None),
    "u_done": ("Is the security answer in u_val complete? complete: the whole answer was given. partial: only part "
               "of it (e.g. no year, some digits missing). none: no answer in this message.",
               ["complete", "partial", "none"]),
    "u_amt": ("The amount of money the customer themself names to pay in this message, as a plain number with a dot "
              "for decimals (1250 or 1250.50); number words turned into digits ('bin iki yüz elli' -> 1250). Empty "
              "if the customer names no number ('all of it', 'the full amount' and amounts the agent said are "
              "empty).", None),
    "u_dkind": ("The kind of payment day the customer names in this message. absolute: a calendar date. weekday: a "
                "day of the week. relative_days: a day counted from today (today, tomorrow, in 3 days, next week = "
                "7). day_of_month: only a day number. vague: a period or event without a day (end of the month, "
                "payday, soon, when I get paid). none: no day.",
                ["none", "absolute", "weekday", "relative_days", "day_of_month", "vague"]),
    "u_dval": ("The day itself, by u_dkind: absolute -> MM-DD, or YYYY-MM-DD only when a year was said; weekday -> "
               "the English weekday name (Friday); relative_days -> the number of days from today (0 today, 1 "
               "tomorrow); day_of_month -> the day number. Never compute a date from today's date. Empty otherwise.",
               None),
    "u_dwhich": ("For a weekday: this (this week's), next (next week's), bare (just the weekday name).",
                 ["bare", "this", "next"]),
    "u_kind": ("What the most recent customer message does, ignoring small talk when it also answers. answer: gives "
               "a value or information. yes: agrees or confirms. no: declines or denies. hedge: maybe / I will try / "
               "not sure. refusal: refuses to pay or to continue. smalltalk: small talk only (weather, family, "
               "traffic), no answer. question: asks something. correction: corrects a value. hold: asks to wait. "
               "repeat: asks the agent to repeat. none: none of these.",
               ["none", "answer", "yes", "no", "hedge", "refusal", "smalltalk", "question", "correction", "hold",
                "repeat"]),
}
MV_STAGE_FIELDS = {"rp": (), "tp": (), "id": ("u_val", "u_done"),
                   "neg": ("u_amt", "u_dkind", "u_dval", "u_dwhich", "u_kind"),
                   "conf": ("u_amt", "u_dkind", "u_dval", "u_dwhich", "u_kind"), "safe": ()}
# the 'as said' slots that stay in a non-English call are said in English (grounded on u_en by the runtime)
MV_KEEP_SLOTS = {"tp": ("u_date", "u_time")}


def call_language(spec):
    """The Spec's call language code (bank.language), 'en' when unset."""
    from runtime.locale import lang_of
    return lang_of(spec)


def extraction_schema(stage, spec):
    """stage in rp, tp, id, neg, conf, safe -> list of extraction fields (D.4). A non-English call adds u_en (the
    English rendering) and the stage's typed model-read fields (MV_STAGE_FIELDS) instead of the 'as said' slots."""
    if stage not in STAGES:
        raise RenderError(f"unknown stage {stage!r}")
    if call_language(spec) != "en":
        return _extraction_schema_mv(stage, spec)
    fields = [
        {"name": "u_text", "type": "string", "description": U_TEXT_DESC, "min_confidence": 0.3},
        {"name": "u_act", "type": "string", "description": U_ACT_DESC, "enum_values": list(vocab.U_ACT_VALUES),
         "min_confidence": 0.5},
    ]
    if stage != "safe":
        vals = topic_values(stage, spec)
        fields.append({"name": "u_topic", "type": "string", "description": _topic_description(stage, spec, vals),
                       "enum_values": vals, "min_confidence": 0.5})
    for slot in vocab.STAGE_SLOTS.get(stage, ()):
        fields.append({"name": slot, "type": "string", "description": SLOT_DESC[slot], "min_confidence": SLOT_CONF})
    return fields


def _extraction_schema_mv(stage, spec):
    lang = LANGUAGES.get(call_language(spec), call_language(spec))
    fields = [
        {"name": "u_text", "type": "string", "min_confidence": 0.3,
         "description": U_TEXT_DESC + " Keep the customer's language (" + lang + ")."},
        {"name": "u_en", "type": "string", "description": U_EN_DESC, "min_confidence": 0.3},
        {"name": "u_act", "type": "string", "description": U_ACT_DESC, "enum_values": list(vocab.U_ACT_VALUES),
         "min_confidence": 0.5},
    ]
    if stage != "safe":
        vals = topic_values(stage, spec)
        fields.append({"name": "u_topic", "type": "string", "description": _topic_description(stage, spec, vals),
                       "enum_values": vals, "min_confidence": 0.5})
    for slot in MV_KEEP_SLOTS.get(stage, ()):
        fields.append({"name": slot, "type": "string", "min_confidence": SLOT_CONF,
                       "description": SLOT_DESC[slot].replace(", as said.", ", as said, in English.")})
    for name in MV_STAGE_FIELDS.get(stage, ()):
        desc, enum = MV_FIELDS[name]
        f = {"name": name, "type": "string", "description": desc, "min_confidence": SLOT_CONF}
        if enum:
            f["enum_values"] = list(enum)
        fields.append(f)
    return fields
