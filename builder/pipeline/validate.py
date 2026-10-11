"""Spec validation + catalog binding + lexicon checks + defaults (docs/CONTRACTS.md B, F). Owner: agent 5.

validate(spec, catalog, brief_text=None) -> {"spec", "errors", "warnings", "defaults_applied", "fixes"}

Order: strip nulls -> code-bound fills (products.fields, spec_version, meta, intent_tie) -> apply_defaults (logged) ->
safe auto-fixes (enum spelling normalisation against the catalog, {var} -> <v:var>, reasonless reasons) ->
JSON schema -> enum bindings -> referential integrity -> placeholders -> banned words before verification ->
bands -> verbatim guard (needs brief_text) -> completeness warnings.

Every error string starts with the JSON pointer it is about ("/situations/S_X/outcome: ..."), which
facets_with_errors() maps back to extraction facets for one targeted re-extraction.
"""
import copy
import json
import re

import jsonschema

from builder import paths, trace
from builder.pipeline import segment as seg
from builder.spec import defaults as spec_defaults
from builder.spec import vocab

_SCHEMA = None
_MOD = "builder.pipeline.validate.validate"   # trace module tag

PRE_VERIFICATION_SCOPES = {"rp", "tp", "id"}
COMPILE_TIME_ONLY = ("opening/line", "right_party/ask")         # spoken by s_open: no runtime placeholders
_PH_RE = re.compile(r"<([^<>\s][^<>]*)>")
_BRACE_VAR_RE = re.compile(r"\{\{?\s*([A-Za-z_](?a:\w)*)\s*\}?\}")  # (?a:\w) is [A-Za-z0-9_]; \s stays Unicode
_SID_RE = re.compile(r"S_[A-Z][A-Z0-9_]*")
_INTENT_ACT_PTR = "/intents/%d/action/%s"
_TP_PTR = "/third_party/"
_RS_TEXT_PTR = "/required_sentences/%d/text"

# keys whose string values are NOT spoken templates (no placeholder check)
_NON_LINE_KEYS = {"examples", "negatives", "keywords", "confirm_examples", "non_confirm_examples", "meaning", "id",
                  "label", "description", "key", "field_value", "wire_format", "pattern", "kind", "value", "name",
                  "customer_key", "now", "name_vars", "before_verification", "always", "never_offer", "never_ask",
                  "when", "use", "trigger", "situation", "situation_pre_verification", "accept_situation",
                  "decline_situation", "queue", "outcome", "reason", "note_reason", "symbol", "word", "position",
                  "language", "field", "from", "to", "date", "holidays", "intent_tie", "reasonless_outcomes",
                  "forbidden_offers", "scope", "bands", "must_convey", "on_unresolved", "on_failed", "on_declined",
                  "on_exhausted", "on_all_failed", "unresolved_product_situation", "callback", "no_callback",
                  "numeric_order", "count_from", "this", "next", "rounding", "roll", "if_today", "days", "text"}


def schema():
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = json.loads(paths.SCHEMA.read_text())
    return _SCHEMA


# ----------------------------------------------------------------------------------------------- helpers

def _d(x):
    return x if isinstance(x, dict) else {}


def _l(x):
    return x if isinstance(x, list) else []


def esc(k):
    return str(k).replace("~", "~0").replace("/", "~1")


def strip_nulls(x):
    """Remove dict keys whose value is None and None list items (the workflow must never carry null)."""
    if isinstance(x, dict):
        return {k: strip_nulls(v) for k, v in x.items() if v is not None}
    if isinstance(x, list):
        return [strip_nulls(v) for v in x if v is not None]
    return x


def walk_strings(x, ptr=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from walk_strings(v, ptr + "/" + esc(k))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from walk_strings(v, ptr + "/" + str(i))
    elif isinstance(x, str):
        yield ptr, x


def norm_enum(s):
    s = str(s).strip().lower()
    s = re.sub(r"[\s\-./]+", "_", s)
    s = re.sub(r"[^a-z0-9_]", "", s)
    return s.strip("_")


def _loose(s):
    s = norm_enum(s)
    s = re.sub(r"_?(team|queue|desk|dept|department)$", "", s)
    s = re.sub(r"^(the_)", "", s)
    return s


def bind_enum(value, allowed):
    """value -> (bound value or None, how). Exact, then normalised, then loose (team/queue suffix) match."""
    if not allowed:
        return value, "free"
    if value in allowed:
        return value, "exact"
    nv = norm_enum(value)
    for a in allowed:
        if norm_enum(a) == nv:
            return a, "normalised"
    lv = _loose(value)
    hits = [a for a in allowed if _loose(a) == lv]
    if len(hits) == 1:
        return hits[0], "loose"
    return None, "none"


def tool_by_response_role(catalog, role):
    for name, t in _d(catalog.get("tools")).items():
        if role in _d(_d(t.get("roles")).get("response")):
            return name, t
    return None, None


def product_fields(catalog):
    """Code binding of Spec.products.fields from the account tool's roles (never the LLM)."""
    _, t = tool_by_response_role(catalog, "products")
    if not t:
        return None
    item = _d(t.get("roles")).get("item") or {}
    lst = t["roles"]["response"]["products"]
    out = {"list": lst}
    for role in ("id", "type", "past_due", "days_late"):
        out[role] = item.get(role, role)
    return out


def product_leaves(catalog):
    _, t = tool_by_response_role(catalog, "products")
    if not t:
        return set()
    lst = t["roles"]["response"]["products"]
    return set(_d(_d(_d(t.get("response")).get(lst)).get("items")))


def catalog_enums(catalog):
    e = dict(_d(catalog.get("enums")))
    for k in ("identity_field", "hint", "product_type", "note_reason", "queue", "outcome", "close_reason"):
        e.setdefault(k, [])
    return e


def identity_values(catalog):
    """Allowed IdQuestion.field_value: selector enum, or (per_field mode) the verify tool's answer-like fields."""
    enums = catalog_enums(catalog)
    if catalog.get("identity_mode") == "per_field":
        _, t = tool_by_response_role(catalog, "verified")
        if t:
            cust = _d(_d(t.get("roles")).get("request")).get("customer")
            return [f for f in _d(t.get("request")) if f != cust]
    return list(enums["identity_field"])


def derive_intent_tie(intents):
    """Non-answer_continue intents by precedence (desc), stable on list order."""
    items = [(i, it) for i, it in enumerate(intents or []) if isinstance(it, dict)
             and _d(it.get("action")).get("kind") != "answer_continue" and it.get("id")]
    items.sort(key=lambda p: (-int(p[1].get("precedence", 0) or 0), p[0]))
    return [it["id"] for _, it in items]


def _amount_rules(x, ptr=""):
    """Yield (pointer, rule) for every AmountRule of kind 'field'."""
    if isinstance(x, dict):
        if x.get("kind") == "field":
            yield ptr, x
        for k, v in x.items():
            yield from _amount_rules(v, ptr + "/" + esc(k))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _amount_rules(v, ptr + "/" + str(i))


def _line_pointers(spec):
    """(pointer, text) for every spoken template in the Spec."""
    for top, val in spec.items():
        if top in ("meta", "spec_version", "interpretation", "call_variables", "banned", "calendar", "situations",
                   "outcomes", "bands", "promise_date", "notes", "multi_product", "required_sentences", "intents",
                   "dated"):
            continue
        for ptr, s in walk_strings(val, "/" + top):
            leaf = ptr.rsplit("/", 1)[-1]
            if leaf in _NON_LINE_KEYS or leaf.isdigit() and ptr.split("/")[-2] in _NON_LINE_KEYS:
                continue
            yield ptr, s
    mp = _d(spec.get("multi_product"))
    if isinstance(mp.get("clamp_line"), str):
        yield "/multi_product/clamp_line", mp["clamp_line"]
    for i, it in enumerate(_l(spec.get("intents"))):
        if not isinstance(it, dict):
            continue
        act = it.get("action") if isinstance(it.get("action"), dict) else {}
        for k in ("say", "question"):
            if isinstance(act.get(k), str):
                yield _INTENT_ACT_PTR % (i, k), act[k]
    for i, rs in enumerate(_l(spec.get("required_sentences"))):
        if isinstance(rs, dict) and isinstance(rs.get("text"), str):
            yield _RS_TEXT_PTR % i, rs["text"]
    nt = _d(spec.get("notes")).get("text")
    if isinstance(nt, str) and nt:
        yield "/notes/text", nt


def pre_verification_lines(spec):
    """(pointer, text) of every line that can be spoken before identity is verified (B.2)."""
    out = []
    op = _d(spec.get("opening"))
    out.append(("/opening/line", op.get("line")))
    rp = _d(spec.get("right_party"))
    out += [("/right_party/ask", rp.get("ask")), ("/right_party/reask", rp.get("reask"))]
    for k, v in _d(rp.get("answers")).items():
        out.append(("/right_party/answers/" + k, v))
    tp = _d(spec.get("third_party"))
    for k in ("reach_ask", "reach_reask", "outside_line", "vague_line", "booked_line", "offer_to_pay_line"):
        out.append((_TP_PTR + k, tp.get(k)))
    idn = _d(spec.get("identity"))
    for i, q in enumerate(_l(idn.get("questions"))):
        for k in ("ask", "reask_wrong", "ask_full"):
            out.append(("/identity/questions/%d/%s" % (i, k), _d(q).get(k)))
    for i, h in enumerate(_l(idn.get("hints"))):
        out.append(("/identity/hints/%d/say" % i, _d(h).get("say")))
    out.append(("/identity/decline/explain", _d(idn.get("decline")).get("explain")))
    out.append(("/identity/fail_line", idn.get("fail_line")))
    for i, it in enumerate(_l(spec.get("intents"))):
        sc = set(_l(_d(it).get("scope")))
        if sc and sc <= PRE_VERIFICATION_SCOPES:
            act = _d(it.get("action"))
            for k in ("say", "question"):
                if k in act:
                    out.append((_INTENT_ACT_PTR % (i, k), act[k]))
    for i, rs in enumerate(_l(spec.get("required_sentences"))):
        trig = _d(rs).get("trigger", "")
        if trig.startswith("on_situation:"):
            sid = trig.split(":", 1)[1]
            if sid in _pre_verification_situations(spec):
                out.append((_RS_TEXT_PTR % i, rs.get("text")))
    return [(p, t) for p, t in out if isinstance(t, str)]


def _pre_verification_situations(spec):
    s = set()
    rp, tp, idn = _d(spec.get("right_party")), _d(spec.get("third_party")), _d(spec.get("identity"))
    s.add(rp.get("on_unresolved"))
    s.update(_d(tp.get("situations")).values())
    s.update([idn.get("on_failed"), idn.get("on_declined")])
    for it in _l(spec.get("intents")):
        sc = set(_l(_d(it).get("scope")))
        if sc and sc <= {"rp", "tp"}:
            s.add(_d(it.get("action")).get("situation"))
    s.discard(None)
    return s


_LANG_NAMES = {"english": "en", "turkish": "tr", "türkçe": "tr", "turkce": "tr", "german": "de", "deutsch": "de",
               "french": "fr", "spanish": "es", "italian": "it", "dutch": "nl", "portuguese": "pt", "polish": "pl",
               "swedish": "sv", "danish": "da"}


def _fix_language(s, fixes):
    """bank.language as a 2-letter code: 'Turkish' / 'tr-TR' / 'TR' -> 'tr'; missing -> 'en' (logged)."""
    bank = s.get("bank")
    if not isinstance(bank, dict):
        return
    v = bank.get("language")
    raw = str(v or "").strip()
    low = raw.lower()
    code = _LANG_NAMES.get(low) or (low[:2] if re.match(r"^[a-z]{2}([-_][a-z0-9]+)?$", low) else "")
    if not code:
        code = "en"
    if code != v:
        bank["language"] = code
        fixes.append("/bank/language: %r -> %r" % (v, code))


def _lang(spec):
    from runtime.locale import lang_of
    return lang_of(spec)


def _lint_banned_lines(spec, banned, flagged, errors):
    """The lint's banned_word rule (builder.compiler.lint) reads more lines than pre_verification_lines (an intent
    spoken before AND after verification, the generic clarify / continue / hold lines) on their rendered text. What
    it would reject (exit 4) is reported here, where the targeted re-extraction can still rewrite the line."""
    from builder.compiler import lint, render
    try:
        lines = lint._pre_verification_lines(spec)
    except Exception:                                   # noqa: BLE001 - a malformed Spec has its own errors
        return
    for ptr, tpl in lines:
        if ptr in flagged:
            continue
        try:
            text = render.strip_runtime(tpl, spec)
        except Exception:                               # noqa: BLE001 - the lint reports what it cannot render
            continue
        hits = lint._words_hit(banned, text, _lang(spec))
        if hits:
            errors.append("%s: pre-verification line contains banned word(s) %s: %r" % (ptr, hits, text))


def banned_hits(text, words, lang="en"):
    if lang != "en":
        from builder.compiler.lint import words_hit    # endings and softened stems in suffixing languages
        return words_hit(words, text, lang)
    low = text.lower()
    hits = []
    for w in words:
        w = (w or "").strip().lower()
        if w and re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", low):
            hits.append(w)
    return hits


# ----------------------------------------------------------------------------------------------- fixes

def _fix_brace_vars(spec, declared, fixes):
    """'{title}' / '{{title}}' in a line -> '<v:title>' when title is a declared call variable."""
    def fix(s):
        def rep(m):
            name = m.group(1)
            return "<v:%s>" % name if name in declared else m.group(0)
        return _BRACE_VAR_RE.sub(rep, s)

    def walk(x, ptr):
        if isinstance(x, dict):
            for k in list(x):
                if k in ("meta",):
                    continue
                v = x[k]
                if isinstance(v, str) and "{" in v:
                    nv = fix(v)
                    if nv != v:
                        x[k] = nv
                        fixes.append("%s/%s: {var} -> <v:var>" % (ptr, esc(k)))
                else:
                    walk(v, ptr + "/" + esc(k))
        elif isinstance(x, list):
            for i, v in enumerate(x):
                if isinstance(v, str) and "{" in v:
                    nv = fix(v)
                    if nv != v:
                        x[i] = nv
                        fixes.append("%s/%d: {var} -> <v:var>" % (ptr, i))
                else:
                    walk(v, ptr + "/" + str(i))
    walk(spec, "")


def _bind(spec_val, allowed, ptr, errors, fixes, what):
    if spec_val in ("", None):
        return spec_val
    bound, how = bind_enum(spec_val, allowed)
    if bound is None:
        errors.append("%s: %r is not a %s enum value (allowed: %s)" % (ptr, spec_val, what, ", ".join(allowed)))
        return spec_val
    if bound != spec_val:
        fixes.append("%s: %r -> %r (%s match to the %s enum)" % (ptr, spec_val, bound, how, what))
    return bound


# ----------------------------------------------------------------------------------------------- main

def _offer_is_sentence(x):
    """A forbidden-offer entry that is a rule sentence, not the name of an offer (more than 4 words, or 'any ...')."""
    words = str(x or "").strip().lower().split()
    return not words or len(words) > 4 or words[0] in ("any", "anything", "every", "no")


def validate(spec, catalog, brief_text=None, examples=None):
    """Never raises: an internal crash becomes one error ("/: validator crashed ...").
    -> {"spec": spec with defaults applied, "errors": [str], "warnings": [str], "defaults_applied": [str]}.
    Checks: JSON schema; enum bindings (outcome, queue, note_reason, identity field_value, hint, product types,
    AmountRule.field, <f:...>); referential integrity (situations, band keys, intent ids, triggers); placeholders;
    pre-verification lines free of banned words; band coverage; reasonless outcomes have reason ''."""
    try:
        return _validate(spec, catalog, brief_text, examples)
    except Exception as e:                              # noqa: BLE001
        trace.event("ERROR", "validator crashed: %s" % e, mod=_MOD)
        return {"spec": spec if isinstance(spec, dict) else {}, "errors": ["/: validator crashed: %s" % e],
                "warnings": [], "defaults_applied": [], "fixes": []}


def _validate(spec, catalog, brief_text, examples=None):
    errors, warnings, fixes, decisions = [], [], [], []
    s = strip_nulls(copy.deepcopy(spec if isinstance(spec, dict) else {}))
    s["spec_version"] = vocab.SPEC_VERSION
    meta = s.setdefault("meta", {})
    if not isinstance(meta, dict):
        meta = s["meta"] = {}
    meta.setdefault("inputs", [])
    for k in [k for k in meta if k not in schema()["properties"]["meta"]["properties"]]:
        warnings.append("/meta/%s: transient meta key removed" % k)
        meta.pop(k)
    if catalog.get("openapi_sha256"):
        meta.setdefault("openapi_sha256", catalog["openapi_sha256"])

    # --- code-bound fills
    pf = product_fields(catalog)
    if isinstance(s.get("products"), dict) and pf:
        if s["products"].get("fields") != pf:
            s["products"]["fields"] = pf
            decisions.append("products.fields bound from the catalog: %s" % json.dumps(pf, sort_keys=True))
    intents = s.get("intents") if isinstance(s.get("intents"), list) else []
    interp = s.setdefault("interpretation", {}) if isinstance(s.get("interpretation", {}), dict) else {}
    if not interp.get("intent_tie") and intents:
        interp["intent_tie"] = derive_intent_tie(intents)
        decisions.append("interpretation.intent_tie derived from intent precedence: %s" % interp["intent_tie"])
    elif interp.get("intent_tie"):
        ids = {it.get("id") for it in intents if isinstance(it, dict)}
        kept = [i for i in interp["intent_tie"] if i in ids]
        if kept != interp["intent_tie"]:
            warnings.append("/interpretation/intent_tie: unknown ids dropped %s" %
                            sorted(set(interp["intent_tie"]) - ids))
            interp["intent_tie"] = kept
    outs = s.get("outcomes")
    if isinstance(outs, dict) and "reasonless_outcomes" not in outs and isinstance(s.get("situations"), dict):
        outs["reasonless_outcomes"] = sorted({v.get("outcome") for v in s["situations"].values()
                                              if isinstance(v, dict) and v.get("reason") == "" and v.get("outcome")})
        decisions.append("outcomes.reasonless_outcomes derived from situations with reason ''")

    _derive_after_record(s, interp, decisions)

    # forbidden_offers names offers ("discount"); a sentence ("any term that is not in this brief") is not one
    neg = s.get("negotiation") if isinstance(s.get("negotiation"), dict) else {}
    if isinstance(neg.get("forbidden_offers"), list):
        keep = [x for x in neg["forbidden_offers"] if not _offer_is_sentence(x)]
        if keep != neg["forbidden_offers"]:
            fixes.append("/negotiation/forbidden_offers: sentences dropped %s" %
                         [x for x in neg["forbidden_offers"] if x not in keep])
            neg["forbidden_offers"] = keep

    _fix_language(s, fixes)

    # --- defaults
    s, applied = spec_defaults.apply_defaults(s)
    meta = s["meta"]                                    # apply_defaults returns a copy: re-bind references
    intents = [it for it in s["intents"] if isinstance(it, dict)] if isinstance(s.get("intents"), list) else []
    if applied:
        trace.event("DEFAULT", "%d defaults applied" % len(applied), mod=_MOD,
                    pointers=applied[:60])

    _decline_counting(s, brief_text, fixes, decisions)
    _half_days(s, brief_text, decisions)

    # --- safe fixes
    declared = {d.get("name") for d in _l(_d(s.get("call_variables")).get("declared")) if isinstance(d, dict)}
    _fix_brace_vars(s, declared, fixes)
    enums = catalog_enums(catalog)
    sits = s.get("situations") if isinstance(s.get("situations"), dict) else {}
    for sid, sv in sits.items():
        if not isinstance(sv, dict):
            continue
        p = "/situations/" + esc(sid)
        if "outcome" in sv:
            sv["outcome"] = _bind(sv["outcome"], enums["outcome"], p + "/outcome", errors, fixes, "close outcome")
        if sv.get("queue"):
            sv["queue"] = _bind(sv["queue"], enums["queue"], p + "/queue", errors, fixes, "transfer queue")
        if sv.get("note_reason"):
            sv["note_reason"] = _bind(sv["note_reason"], enums["note_reason"], p + "/note_reason", errors, fixes,
                                      "note reason")
        if sv.get("reason") and enums["close_reason"]:
            sv["reason"] = _bind(sv["reason"], enums["close_reason"], p + "/reason", errors, fixes, "close reason")
    for i, it in enumerate(intents):
        act = _d(it).get("action") if isinstance(it, dict) else None
        if isinstance(act, dict) and act.get("queue"):
            act["queue"] = _bind(act["queue"], enums["queue"], "/intents/%d/action/queue" % i, errors, fixes,
                                 "transfer queue")
    idn = s.get("identity") if isinstance(s.get("identity"), dict) else {}
    idv = identity_values(catalog)
    for i, q in enumerate(_l(idn.get("questions"))):
        if isinstance(q, dict) and "field_value" in q:
            q["field_value"] = _bind(q["field_value"], idv, "/identity/questions/%d/field_value" % i, errors, fixes,
                                     "identity field")
    for i, h in enumerate(_l(idn.get("hints"))):
        if isinstance(h, dict) and "value" in h:
            h["value"] = _bind(h["value"], enums["hint"], "/identity/hints/%d/value" % i, errors, fixes, "hint")
    prods = s.get("products") if isinstance(s.get("products"), dict) else {}
    types = prods.get("types") if isinstance(prods.get("types"), dict) else {}
    if enums["product_type"] and types:
        new_types = {}
        for k, v in types.items():
            b = _bind(k, enums["product_type"], "/products/types/" + esc(k), errors, fixes, "product type")
            new_types[b] = v
        prods["types"] = new_types
        missing = [t for t in enums["product_type"] if t not in new_types]
        if missing:
            warnings.append("/products/types: catalog product types without a Spec entry %s (spoken as "
                            "unknown_type_spoken, floor = full)" % missing)
    # note_reason left empty -> the note enum value equal to the situation's reason (or outcome), when one exists
    if enums["note_reason"]:
        for sid, sv in sits.items():
            if isinstance(sv, dict) and sv.get("note_reason", None) == "":
                for cand in (sv.get("reason"), sv.get("outcome")):
                    if not cand:
                        continue
                    bound, how = bind_enum(cand, enums["note_reason"])
                    if bound and how in ("exact", "normalised"):
                        sv["note_reason"] = bound
                        fixes.append("/situations/%s/note_reason: '' -> %r (matches the situation's %s)" % (
                            esc(sid), bound, "reason" if cand == sv.get("reason") else "outcome"))
                        break
    # structural scope guards: no transfer before verification, no product intents before the account is known
    for i, it in enumerate(intents):
        kind = _d(it.get("action")).get("kind") if isinstance(it.get("action"), dict) else None
        sc = it.get("scope") if isinstance(it.get("scope"), list) else None
        if sc is None:
            continue
        drop = set()
        if kind in ("transfer", "ask_then_transfer", "offer_transfer", "count_then_close"):
            drop = {"rp", "tp"}                         # never before the right party is confirmed
        elif kind in ("resolve_product", "too_much"):
            drop = {"rp", "tp", "id"}
        if drop & set(sc):
            new = [x for x in sc if x not in drop]
            if new:
                it["scope"] = new
                fixes.append("/intents/%d/scope: %s removed for a %s intent (structural guard)" % (
                    i, sorted(drop & set(sc)), kind))
            else:
                errors.append("/intents/%d/scope: a %s intent cannot apply only in %s" % (i, kind, sorted(sc)))
    # reasonless outcomes never carry a reason
    rl = set(_l(_d(s.get("outcomes")).get("reasonless_outcomes")))
    for sid, sv in sits.items():
        if isinstance(sv, dict) and sv.get("outcome") in rl and sv.get("reason"):
            errors.append("/situations/%s/reason: outcome %r is reasonless but reason is %r" % (
                esc(sid), sv["outcome"], sv["reason"]))

    _line_fixes(s, warnings, fixes)

    # --- schema
    v = jsonschema.Draft202012Validator(schema())
    for e in sorted(v.iter_errors(s), key=lambda e: [str(p) for p in e.absolute_path])[:60]:
        ptr = "/" + "/".join(esc(p) for p in e.absolute_path)
        msg = e.message if len(e.message) < 300 else e.message[:297] + "..."
        errors.append("%s: schema: %s" % (ptr, msg))

    # --- AmountRule.field and <f:FIELD>
    leaves = product_leaves(catalog)
    if leaves:
        for ptr, rule in _amount_rules(s):
            if rule.get("kind") == "field" and rule.get("field") not in leaves:
                errors.append("%s/field: %r is not a product response leaf (%s)" % (ptr, rule.get("field"),
                                                                                    ", ".join(sorted(leaves))))

    # --- referential integrity
    sids = set(sits)
    refs = {}
    for ptr, text in walk_strings({k: v for k, v in s.items() if k not in ("meta", "situations")}):
        for sid in _SID_RE.findall(text):
            refs.setdefault(sid, ptr)
    for sid in sorted(set(refs) - sids):
        errors.append("%s: situation %s is used but not defined in /situations" % (refs[sid], sid))
    bands = s.get("bands") if isinstance(s.get("bands"), list) else []
    band_keys = {b.get("key") for b in bands if isinstance(b, dict)}
    neg = s.get("negotiation") if isinstance(s.get("negotiation"), dict) else {}
    for i, r in enumerate(_l(neg.get("ladder"))):
        if isinstance(r, dict):
            bl = _l(r.get("bands"))
            if bl != ["all"] and not set(bl) <= band_keys:
                errors.append("/negotiation/ladder/%d/bands: unknown band keys %s" % (i, sorted(set(bl) - band_keys)))
    ids = [it.get("id") for it in intents if isinstance(it, dict)]
    dup = sorted({x for x in ids if ids.count(x) > 1})
    if dup:
        errors.append("/intents: duplicate intent ids %s" % dup)
    for i, rs in enumerate(_l(s.get("required_sentences"))):
        trig = _d(rs).get("trigger", "") if isinstance(rs, dict) else ""
        if trig.startswith("on_intent:") and trig.split(":", 1)[1] not in ids:
            errors.append("/required_sentences/%d/trigger: unknown intent %s" % (i, trig))
    for k in _d(_d(s.get("closing")).get("per_situation")):
        if k not in sids:
            errors.append("/closing/per_situation/%s: unknown situation" % esc(k))
    ladder_keys = [r.get("key") for r in neg.get("ladder") or [] if isinstance(r, dict)]
    if len(set(ladder_keys)) != len(ladder_keys):
        errors.append("/negotiation/ladder: duplicate rung keys")
    qkeys = [q.get("key") for q in idn.get("questions") or [] if isinstance(q, dict)]
    if len(set(qkeys)) != len(qkeys):
        errors.append("/identity/questions: duplicate question keys")
    nm = _d(s.get("addressing")).get("name_vars") or []
    for n in nm:
        if declared and n not in declared:
            errors.append("/addressing/name_vars: %r is not a declared call variable" % n)
    cv = _d(s.get("call_variables"))
    for k in ("customer_key", "now"):
        if cv.get(k) and declared and cv[k] not in declared:
            errors.append("/call_variables/%s: %r is not declared" % (k, cv[k]))

    # --- placeholders
    for ptr, text in _line_pointers(s):
        if "{{" in text or "}}" in text:
            errors.append("%s: Freya braces are not allowed in a Spec line" % ptr)
        for ph in _PH_RE.findall(text):
            if ph.startswith("v:"):
                if ph[2:] not in declared:
                    errors.append("%s: <%s> is not a declared call variable" % (ptr, ph))
            elif ph.startswith("f:"):
                if leaves and ph[2:] not in leaves:
                    errors.append("%s: <%s> is not a product response leaf" % (ptr, ph))
            elif ph not in vocab.PLACEHOLDERS:
                errors.append("%s: unknown placeholder <%s>" % (ptr, ph))
            elif any(ptr.endswith(c) for c in COMPILE_TIME_ONLY) and ph not in vocab.COMPILE_TIME_PLACEHOLDERS:
                errors.append("%s: runtime placeholder <%s> in a compile-time line" % (ptr, ph))
        if any(ptr.endswith(c) for c in COMPILE_TIME_ONLY) and "<f:" in text:
            errors.append("%s: <f:...> in a compile-time line" % ptr)
    addr = _d(s.get("addressing")).get("customer", "")
    addr = addr if isinstance(addr, str) else ""
    for ph in _PH_RE.findall(addr or ""):
        if not ph.startswith("v:"):
            errors.append("/addressing/customer: only <v:...> placeholders are allowed (found <%s>)" % ph)

    # --- banned words before verification
    banned = [w for w in _l(_d(s.get("banned")).get("before_verification")) if isinstance(w, str)]
    if brief_text and banned:
        # a word the brief itself puts in a line it dictates for before verification (e.g. "the number on the
        # back of your card") is not banned by that brief: drop it from the list instead of rejecting the line
        bhay = seg.norm_quote_text(brief_text)
        ok = {w for ptr, text in pre_verification_lines(s) if seg.quote_in(text, bhay)
              for w in banned_hits(text, banned, _lang(s))}
        if ok:
            banned = [w for w in banned if w not in ok]
            s["banned"]["before_verification"] = banned
            fixes.append("/banned/before_verification: %s removed (the brief's own pre-verification line uses it)"
                         % sorted(ok))
    flagged = set()
    for ptr, text in pre_verification_lines(s):
        hits = banned_hits(text, banned, _lang(s))
        if hits:
            flagged.add(ptr)
            errors.append("%s: pre-verification line contains banned word(s) %s: %r" % (ptr, hits, text))
    _lint_banned_lines(s, banned, flagged, errors)
    # --- call language: an ending attached to a placeholder in a suffixing language (lint has the same rule)
    from builder.compiler.lint import slot_suffixes
    for ptr, text in slot_suffixes(s):
        warnings.append("%s: an ending is attached to a placeholder; write the line so the slot stands alone: %r"
                        % (ptr, text))

    # --- bands
    good = [b for b in bands if isinstance(b, dict) and isinstance(b.get("days_late_min"), int)
            and isinstance(b.get("days_late_max"), int)]
    for i, b in enumerate(good):
        if b["days_late_min"] > b["days_late_max"]:
            errors.append("/bands/%d: days_late_min > days_late_max" % i)
    srt = sorted(good, key=lambda b: b["days_late_min"])
    for a, b in zip(srt, srt[1:]):
        if b["days_late_min"] <= a["days_late_max"]:
            errors.append("/bands: bands %s and %s overlap" % (a.get("key"), b.get("key")))
        elif b["days_late_min"] > a["days_late_max"] + 1:
            warnings.append("/bands: gap between %s and %s (days %d-%d use the nearest band)" % (
                a.get("key"), b.get("key"), a["days_late_max"] + 1, b["days_late_min"] - 1))
    for i, b in enumerate(good):
        n_rungs = len([r for r in neg.get("ladder") or [] if isinstance(r, dict)
                       and (r.get("bands") == ["all"] or b.get("key") in _l(r.get("bands")))])
        if isinstance(b.get("attempts"), int) and b["attempts"] > n_rungs:
            warnings.append("/bands/%d/attempts: %d attempts but only %d ladder rungs apply" % (
                i, b["attempts"], n_rungs))

    # --- verbatim guard + example values baked as constants
    if brief_text:
        hay = seg.norm_quote_text(collapse_doublets(brief_text)) + "\n" + seg.norm_quote_text(brief_text)
        for i, rs in enumerate(_l(s.get("required_sentences"))):
            if isinstance(rs, dict) and rs.get("verbatim") and isinstance(rs.get("text"), str):
                if not seg.quote_in(rs["text"], hay):
                    errors.append("/required_sentences/%d/text: verbatim sentence is not in the brief: %r" % (
                        i, rs["text"]))
        cq = _d(s.get("confirmation"))
        if cq.get("verbatim_question") and isinstance(cq.get("question"), str) and \
                not seg.quote_in(cq["question"], hay):
            warnings.append("/confirmation/question: marked verbatim but not found in the brief")

    # --- example values from the brief's tables must not be baked into lines or dates (BRF-71)
    ex = [x for x in (examples or []) if isinstance(x, str) and len(x.strip()) >= 3]
    if ex:
        # A value that the brief also writes outside its example cells (a rule that names a product type, a bank
        # name...) is a legitimate constant: warn only. Only a value seen nowhere but in example cells is an error.
        def _only_example(x):
            if not brief_text:
                return True
            pat = r"(?<![A-Za-z0-9_])" + re.escape(x) + r"(?![A-Za-z0-9_])"
            in_text = len(re.findall(pat, brief_text, re.I))
            in_cells = sum(len(re.findall(pat, e, re.I)) for e in (examples or []) if isinstance(e, str))
            return in_text <= in_cells
        ex_dates = {m for x in ex for m in re.findall(r"\d{4}-\d{2}-\d{2}", x)}
        for ptr, text in _line_pointers(s):
            for x in ex:
                if re.search(r"(?<![A-Za-z0-9_])" + re.escape(x) + r"(?![A-Za-z0-9_])", text):
                    msg = "%s: contains the brief's example value %r (values come from the call)" % (ptr, x)
                    (errors if _only_example(x) else warnings).append(msg)
        for ptr, val in walk_strings({k: v for k, v in s.items() if k not in ("meta", "dated")}):
            if re.match(r"^\d{4}-\d{2}-\d{2}$", val) and val in ex_dates:
                msg = "%s: date %s is the brief's example 'now', not a rule" % (ptr, val)
                (errors if _only_example(val) else warnings).append(msg)

    _dated_checks(s, errors)
    _residual_dates(s, warnings)
    _identity_checks(s, warnings, fixes)
    _keyword_checks(intents, warnings)

    # --- completeness warnings
    for it in intents:
        if isinstance(it, dict) and len(_l(it.get("keywords"))) == 0 and \
                _d(it.get("action")).get("kind") != "too_much":
            warnings.append("/intents/%s: no keywords (regex backstop) for this intent" % it.get("id"))
        for kw in _l(it.get("keywords")) if isinstance(it, dict) else []:
            try:
                re.compile(kw)
            except re.error as e:
                errors.append("/intents/%s/keywords: invalid regex %r (%s)" % (it.get("id"), kw, e))
    meta.setdefault("defaults_applied", [])
    meta["defaults_applied"] = sorted(set(meta["defaults_applied"]) | set(applied))
    meta.setdefault("decisions", [])
    meta["decisions"] = meta["decisions"] + [d for d in decisions + fixes if d not in meta["decisions"]]
    meta.setdefault("warnings", [])
    meta["warnings"] = meta["warnings"] + [w for w in warnings if w not in meta["warnings"]]
    for f in fixes:
        trace.event("DECISION", f, mod=_MOD)
    trace.event("VALIDATE", "errors=%d warnings=%d defaults=%d fixes=%d" % (
        len(errors), len(warnings), len(applied), len(fixes)), mod=_MOD)
    return {"spec": s, "errors": errors, "warnings": warnings, "defaults_applied": applied, "fixes": fixes}


# ----------------------------------------------------------------------------------------------- rehearsal fixes

# Sections the runtime evaluates on every call: only these may change on an effective date (Spec.dated). The rest
# is compiled into the graph (identity, intents, situations, call variables, opening, notes, products.max ...).
DATED_PREFIXES = ("/bands/", "/calendar/", _TP_PTR, "/promise_date/", "/amounts/", "/negotiation/",
                  "/products/types/", "/products/max", "/statement/", "/confirmation/", "/closing/", "/lines/",
                  "/multi_product/", "/recording/", "/notes/")        # graph.wiring builds nodes for every variant
_DATE_IN_TEXT = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}(?:st|nd|rd|th)? (?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|"
                           r"dec)[a-z]*\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]* \d{1,2}\b|\beffective\b",
                           re.I)


# identity declines add up across questions only when the brief says so in a sentence about declining
_DECL_SENT = re.compile(r"\b(?:declin\w*|refus\w*|(?:not|n't) (?:want to )?answer\w*)\b", re.I)
_DECL_ID = re.compile(r"\b(?:question|answer|identity|security|verif)", re.I)
_DECL_TOTAL = re.compile(r"\b(?:add(?:s|ed)? up|in total|cumulative(?:ly)?|combined|count(?:s|ed)? together|summed)\b"
                         r"|\bacross (?:all |both |the |different |separate |several )?(?:(?:security|identity) )?questions\b"
                         r"|\b(?:on|to|for|over) (?:any|different|separate|several) (?:(?:security|identity) )?questions?\b"
                         r"|\b(?:whichever|no matter which|regardless of which|regardless of the) question\b"
                         r"|\bnot (?:necessarily )?(?:on|to|for) the same question\b", re.I)


def _decline_counting(s, brief_text, fixes, decisions):
    """interpretation.decline_counting is decided in code, not by the LLM (it flipped between builds of one brief):
    per_question_consecutive unless a brief sentence about declining says the declines add up across questions."""
    interp = s.get("interpretation")
    if not brief_text or not isinstance(interp, dict):
        return
    hit = next((x.strip() for x in re.split(r"(?<=[.!?])\s+|\n", brief_text)
                if _DECL_SENT.search(x) and _DECL_ID.search(x) and _DECL_TOTAL.search(x)), "")
    want = "total" if hit else "per_question_consecutive"
    why = ("the brief adds declines up across questions: %r" % hit[:160]) if hit else \
        "the brief never says identity declines add up across questions"
    if interp.get("decline_counting") != want:
        fixes.append("/interpretation/decline_counting: %r -> %r (%s)" % (interp.get("decline_counting"), want, why))
        interp["decline_counting"] = want
    else:
        decisions.append("interpretation.decline_counting = %s (%s)" % (want, why))
        trace.event("DECISION", "interpretation.decline_counting = %s (%s)" % (want, why), mod=_MOD)


_HALF_WORD = re.compile(r"\b(?:arife\w*|yar[ıi]m g[üu]n\w*|half[- ]days?|half[- ]holidays?)", re.I)
_HHMM = re.compile(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b")


def _half_days(s, brief_text, decisions):
    """calendar.half_days absent: when the brief speaks of half days (e.g. a holiday's eve) and the country's
    calendar lists them, use those dates. The afternoon starts after the latest time the most restrictive half-day
    sentence of the brief allows (e.g. '... only between 08:00 and 11:45' -> from 11:46), else at 13:00.
    half_day_is_business_day defaults to true (the brief's own value, from F3, wins)."""
    from builder import calendars
    cal = s.get("calendar")
    if not brief_text or not isinstance(cal, dict) or cal.get("half_days"):
        return
    sents = [x for x in re.split(r"(?<=[.!?])\s|\n", brief_text) if _HALF_WORD.search(x)]
    if not sents:
        return
    country = calendars.country_for(_d(s.get("bank")).get("language", ""), brief_text)
    days = calendars.half_days(country)
    if not days:
        return
    # each half-day sentence's latest time; the most restrictive of them is the half day's end
    ends = [max(int(h) * 60 + int(m) for h, m in t) for t in (_HHMM.findall(x) for x in sents) if t]
    start = min(ends) + 1 if ends and min(ends) < 23 * 60 + 59 else 13 * 60
    frm = "%02d:%02d" % divmod(start, 60)
    cal["half_days"] = [{"date": d, "from": frm} for d in days]
    cal.setdefault("half_day_is_business_day", True)
    why = "calendar.half_days: the brief speaks of half days; %d %s half days, callbacks from %s are off" % (
        len(days), country, frm)
    decisions.append(why)
    trace.event("DECISION", why, mod=_MOD)


def _derive_after_record(s, interp, decisions):
    """interpretation.after_record absent: ask 'anything else?' after the promises are recorded when a transfer can
    still follow a recorded promise (outcomes.precedence ranks transfer_done above any_promise_recorded)."""
    if "after_record" in interp or not isinstance(s.get("outcomes"), dict):
        return
    whens = [_d(p).get("when") for p in _l(s["outcomes"].get("precedence"))]
    if "transfer_done" in whens and "any_promise_recorded" in whens and \
            whens.index("transfer_done") < whens.index("any_promise_recorded") and interp.get("transfer_beats_promise", True):
        interp["after_record"] = "ask_anything_else"
        decisions.append("interpretation.after_record = ask_anything_else: a transfer can follow a recorded promise "
                         "(transfer_done ranks above any_promise_recorded), so the call does not end in the recording turn")


_NUMW = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                     "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
_NUMW.update({w: 10 * (i + 2) for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())})
_DOUBLET = re.compile(r"\b([A-Za-z]+(?:-[A-Za-z]+)?) ?\((\d{1,3})\)")


def _word_value(w):
    parts = w.lower().split("-")
    if not all(x in _NUMW for x in parts) or len(parts) > 2:
        return None
    return sum(_NUMW[x] for x in parts)


def collapse_doublets(text):
    """Legal drafting 'two (2) business days' -> 'two business days' (TTS would read 'two two'); a bracketed number
    that is not the word's value is kept."""
    if not isinstance(text, str):
        return text
    return _DOUBLET.sub(lambda m: m.group(1) if _word_value(m.group(1)) == int(m.group(2)) else m.group(0), text)


def _sentences_of(text):
    return [x for x in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if x]


def _strip_goodbye(text, good):
    """Drop goodbye sentences from a line that is not the last thing said (the goodbye is added at close)."""
    gs = {x.strip().lower() for x in _sentences_of(good)}
    keep = [x for x in _sentences_of(text) if x.strip().lower() not in gs and not re.search(r"\bgoodbye\b", x, re.I)]
    return " ".join(keep)


_NONTERMINAL_KINDS = ("count_then_close", "answer_continue", "offer_transfer", "ask_then_transfer")


def _str_keys(cont, keys, ptr_of):
    """(cont, key, pointer) for each key of `keys` whose value in cont is a string."""
    return [(cont, k, ptr_of(k)) for k in keys if isinstance(cont.get(k), str)]


def _nonterminal_lines(s):
    """(container, key, pointer) of lines that are followed by a re-ask or more talk."""
    out = []
    for i, it in enumerate(_l(s.get("intents"))):
        act = _d(_d(it).get("action"))
        if act.get("kind") in _NONTERMINAL_KINDS:
            out += _str_keys(act, ("say", "question"), lambda k, i=i: _INTENT_ACT_PTR % (i, k))
    out += _str_keys(_d(s.get("right_party")), ("reask",), lambda k: "/right_party/" + k)
    for i, q in enumerate(_l(_d(s.get("identity")).get("questions"))):
        if isinstance(q, dict):
            out += _str_keys(q, ("ask", "reask_wrong", "ask_full", "reask"),
                             lambda k, i=i: "/identity/questions/%d/%s" % (i, k))
    tp = _d(s.get("third_party"))
    if tp.get("mode") != "close":
        out += _str_keys(tp, ("reach_ask", "reach_reask", "outside_line", "vague_line", "time_ask", "time_reask"),
                         lambda k: _TP_PTR + k)
    return out


def _tp_mode(s, warnings, fixes):
    """A brief that never books third-party callbacks was squeezed into the callback shape (a zero-length window,
    or the goodbye in the reach ask): third_party.mode = close, with that line as close_line."""
    tp = _d(s.get("third_party"))
    if not tp or tp.get("mode"):
        return
    cb = _d(tp.get("callback"))
    wins = [_d(w) for w in _l(cb.get("windows"))]
    zero = bool(wins) and all(w.get("from") and w.get("from") == w.get("to") for w in wins)
    bye = isinstance(tp.get("reach_ask"), str) and re.search(r"\bgoodbye\b", tp["reach_ask"], re.I)
    if zero or bye:
        tp["mode"] = "close"
        if not tp.get("close_line") and isinstance(tp.get("reach_ask"), str):
            tp["close_line"] = tp["reach_ask"]
        msg = "/third_party/mode: close (no callbacks: %s)" % ("zero-length callback window" if zero else
                                                             "the reach ask says goodbye")
        warnings.append(msg)
        fixes.append(msg)


def _line_fixes(s, warnings, fixes):
    _tp_mode(s, warnings, fixes)
    _tp_callback_situation(s, fixes)
    _goodbye_fixes(s, fixes)
    for ptr, text in _line_pointers(s):
        new = collapse_doublets(text)
        if new != text:
            _set_ptr(s, ptr, new)
            fixes.append("%s: number doublet spoken once (%r -> %r)" % (ptr, text, new))
    _required_sentence_dupes(s, fixes)
    _callback_today_rule(s, fixes)
    _success_word_fixes(s, warnings, fixes)


def _tp_callback_situation(s, fixes):
    """mode close never books, so the callback situation is never reached: point it at no_callback."""
    tp = _d(s.get("third_party"))
    tsit = _d(tp.get("situations"))
    if tp.get("mode") == "close" and tsit.get("callback") and tsit.get("callback") not in _d(s.get("situations")):
        fixes.append("/third_party/situations/callback: %s -> %s (mode close never books)" % (
            tsit["callback"], tsit.get("no_callback")))
        tsit["callback"] = tsit.get("no_callback") or tsit["callback"]


def _goodbye_fixes(s, fixes):
    good = _d(s.get("closing")).get("goodbye", "")
    ack = _d(s.get("lines")).get("ack") or "I understand."
    for cont, k, ptr in _nonterminal_lines(s):
        new = _strip_goodbye(cont[k], good) if good or "goodbye" in cont[k].lower() else cont[k]
        if new != cont[k]:
            fixes.append("%s: goodbye removed from a line the call goes on after (%r)" % (ptr, cont[k]))
            cont[k] = new or ack


def _required_sentence_dupes(s, fixes):
    """A required sentence that repeats the say of the product intent that sets its situation is said twice (the
    intent speaks it in its own turn, the sentence again at the close of a later turn): drop the sentence."""
    says = {}
    for it in _l(s.get("intents")):
        act = _d(_d(it).get("action"))
        if act.get("kind") != "resolve_product":
            continue
        for key in ("on_situation:" + str(act.get("situation", "")), "on_intent:" + str(_d(it).get("id", ""))):
            says.setdefault(key, []).append(str(act.get("say") or "").strip().lower())

    def dup(rs):
        t = str(rs.get("text", "")).strip().lower() if isinstance(rs, dict) else ""
        return bool(t) and any(t in x for x in says.get(rs.get("trigger"), []))

    rss = _l(s.get("required_sentences"))
    keep = [rs for rs in rss if not dup(rs)]
    if len(keep) != len(rss):
        fixes.append("/required_sentences: dropped %s (the intent's own line already says it)" %
                     [rs.get("id") for rs in rss if rs not in keep])
        s["required_sentences"] = keep


def _callback_today_rule(s, fixes):
    """One source of truth for 'callback today when today is not a business day': the date rule the runtime reads."""
    dr = _d(_d(_d(s.get("third_party")).get("callback")).get("date_rule"))
    interp = _d(s.get("interpretation"))
    if "today_must_be_business_day" in dr and interp:
        want = "refuse" if dr["today_must_be_business_day"] else "allow"
        if interp.get("callback_today_nonbd") != want:
            fixes.append("/interpretation/callback_today_nonbd: %r -> %r (follows third_party.callback.date_rule)" % (
                interp.get("callback_today_nonbd"), want))
            interp["callback_today_nonbd"] = want


def _set_ptr(s, ptr, value):
    cur = s
    parts = [p.replace("~1", "/").replace("~0", "~") for p in ptr.split("/")[1:]]
    for p in parts[:-1]:
        cur = cur[int(p)] if isinstance(cur, list) else cur[p]
    cur[int(parts[-1]) if isinstance(cur, list) else parts[-1]] = value


def _dated_checks(s, errors):
    """Spec.dated: each path is runtime-evaluated and resolves, and the Spec patched for every effective date is
    still valid. A bad entry is an error (the facet that owns the path is re-extracted)."""
    ds = _l(s.get("dated"))
    for i, d in enumerate(ds):
        _dated_entry_check(s, i, _d(d), errors)
    if not errors and ds:
        _dated_schema_check(s, ds, errors)


def _resolve_parent(s, path):
    """The container a JSON pointer's last key lives in, or None when the pointer does not resolve."""
    cur = s
    for part in [p.replace("~1", "/").replace("~0", "~") for p in path.split("/")[1:-1]]:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None
    return cur if isinstance(cur, (dict, list)) else None


def _dated_entry_check(s, i, d, errors):
    path = str(d.get("path", ""))
    if not path.startswith(DATED_PREFIXES):
        errors.append("%s: dated path %s is compiled into the graph; only %s can change on a date" % (
            path or "/dated/%d" % i, path, ", ".join(DATED_PREFIXES)))
        return
    if _resolve_parent(s, path) is None:
        errors.append("%s: dated path does not resolve in the Spec" % path)
    if d.get("until") and str(d.get("until")) <= str(d.get("from", "")):
        errors.append("%s: dated entry ends (%s) before it starts (%s)" % (path, d.get("until"), d.get("from")))


def _dated_schema_check(s, ds, errors):
    import datetime
    from runtime.brain import dated_spec
    v = jsonschema.Draft202012Validator(schema())
    for day in sorted({str(_d(d).get("from")) for d in ds}):
        try:
            patched = dated_spec(s, datetime.date.fromisoformat(day))
        except ValueError:
            continue
        for e in list(v.iter_errors(patched))[:5]:
            ptr = "/" + "/".join(esc(p) for p in e.absolute_path)
            errors.append("%s: schema (as dated from %s): %s" % (ptr, day, e.message[:200]))


def _residual_dates(s, warnings):
    if _l(s.get("dated")):
        return
    for r in _l(_d(s.get("meta")).get("residual_rules")):
        t = str(_d(r).get("text", ""))
        if _DATE_IN_TEXT.search(t):
            warnings.append("/meta/residual_rules: a rule with an effective date is not applied by the runtime "
                            "(no Spec.dated entry): %r" % t[:160])


def _pattern_atom(pat, i):
    """-> (one character the atom at pat[i] matches, index after it); atom None when unsupported."""
    ch = pat[i]
    if ch == "[":
        j = pat.find("]", i)
        if j < 0:
            return None, i
        body = pat[i + 1:j].replace("\\d", "0-9")
        return (body[0] if body and body[0] != "^" else None), j + 1
    if ch == "\\" and i + 1 < len(pat):
        return {"d": "0", "s": " ", "w": "A"}.get(pat[i + 1], pat[i + 1]), i + 2
    if ch in "()|.*+?{":
        return None, i
    return ch, i + 1


def _pattern_min_count(pat, i):
    """-> (the least repeat count of the quantifier at pat[i] (1 when there is none), index after it); None count
    when the quantifier is unsupported."""
    q = pat[i] if i < len(pat) else ""
    if q in ("?", "*"):
        return 0, i + 1
    if q == "+":
        return 1, i + 1
    if q != "{":
        return 1, i
    j = pat.find("}", i)
    try:
        return (int(pat[i + 1:j].split(",")[0]) if j >= 0 else None), j + 1
    except ValueError:
        return None, i


def _sample_from_pattern(pat):
    """A shortest string matching a simple anchored regex (classes, literals, ? * + {m,n}); None if unsupported."""
    out, i = [], 0
    pat = pat.strip("^$")
    while i < len(pat):
        atom, i = _pattern_atom(pat, i)
        if atom is None:
            return None
        lo, i = _pattern_min_count(pat, i)
        if lo is None:
            return None
        out.append(atom * lo)
    return "".join(out)


def _identity_checks(s, warnings, fixes):
    """An alnum identity question whose pattern a correct spoken answer can never satisfy is never verified (the agent
    re-asks forever). Try a sample made from the pattern; repair the length, else warn."""
    for i, q in enumerate(_l(_d(s.get("identity")).get("questions"))):
        q = _d(q)
        sample = _sample_from_pattern(str(q["pattern"])) if q.get("kind") == "alnum" and q.get("pattern") else None
        if sample:
            _identity_sample_check(i, q, sample, warnings, fixes)


def _identity_sample_check(i, q, sample, warnings, fixes):
    import datetime
    from runtime.ident import id_answer
    spoken = " ".join(re.sub(r"[^A-Za-z0-9]", "", sample))
    # (a missing separator is put back by the runtime itself: runtime.ident._i_fit)

    def completes():
        return id_answer(q, spoken, "", datetime.date(2000, 1, 3)).get("status") == "complete"

    if completes():
        return
    if q.get("length"):
        fixes.append("/identity/questions/%d/length: %r -> 0 (a valid answer has another length)" % (i, q["length"]))
        q["length"] = 0
        if completes():
            return
    warnings.append("/identity/questions/%d: a spoken answer matching the pattern %r never completes" % (
        i, q["pattern"]))


def _kw_hits(kw, neg):
    try:
        return isinstance(neg, str) and bool(re.search(kw, neg.lower(), re.I))
    except re.error:
        return False


def _keyword_checks(intents, warnings):
    """A keyword that fires on the intent's own negative example is too broad, unless the runtime's guard (negation,
    idiom, a relative's death) already ignores that hit."""
    from runtime.brain import _b_kw_void
    for it in intents:
        kind = _d(it.get("action")).get("kind")
        guarded = kind in ("offer_transfer", "close_now")
        for kw in _l(_d(it).get("keywords")):
            for neg in _l(it.get("negatives")):
                if _kw_hits(kw, neg) and not (guarded and _b_kw_void({"keywords": [kw]}, neg, kind == "close_now")):
                    warnings.append("/intents/%s/keywords: %r matches the intent's own negative %r" % (
                        it.get("id"), kw, neg))


# ----------------------------------------------------------------------------------------------- facets

def facets_with_errors(errors):
    """Map error messages (JSON pointers) back to facet ids for one targeted re-extraction."""
    from builder.pipeline.extract import FACETS
    key2facet = {k: f for f, keys in FACETS.items() for k in keys}
    out = set()
    for e in errors or []:
        for name in re.findall(r"'([a-z_]+)' is a required property", str(e)):
            if str(e).startswith("/:") and name in key2facet:
                out.add(key2facet[name])
        m = re.match(r"^/([^/:\s]+)", str(e))
        if not m:
            continue
        top = m.group(1).replace("~1", "/").replace("~0", "~")
        if top in key2facet:
            out.add(key2facet[top])
        elif top == "interpretation":
            out.add("F5")
        # banned-word errors on intents/identity/tp lines also concern F1 (the banned list itself)
        if "banned word" in str(e):
            out.add("F1")
        # a situation used but not defined: defined in F7, referenced by the intents in F5
        if "is used but not defined" in str(e):
            out.update(("F5", "F7"))
    return sorted(out)


# ----------------------------------------------------------------------------------------------- success word
# The success word ("recorded") may be said only after the promise is written (honesty rule). A pre-success line
# that uses it in another sense ("this call is recorded") reads as a false success claim to a literal checker.
_PARTICIPLE_AFTER_BE = re.compile(r"\b(?:is|are|was|were|been)\s+(?:now\s+|successfully\s+|all\s+)?([a-z]{3,}ed)\b", re.I)
_POST_SUCCESS_PTRS = ("/recording/", "/confirmation/recorded_cannot_change", "/lines/anything_else", "/notes/text")
_POST_SUCCESS_TRIGGERS = ("after_promise_recorded", "on_outcome:")
_VOWELS = "aeiouy"


def _word_re(w):
    return re.compile(r"\b%s\b" % re.escape(w), re.I)


def success_words(s):
    """The participles the Spec's own success lines (recording.recorded / recorded_multi) use, lower-case."""
    rec = _d(s.get("recording"))
    out = []
    for k in ("recorded", "recorded_multi"):
        for m in _PARTICIPLE_AFTER_BE.finditer(str(rec.get(k) or "")):
            if m.group(1).lower() not in out:
                out.append(m.group(1).lower())
    return out


def _base_verb(word, s):
    """'recorded' -> 'record', 'saved' -> 'save', 'logged' -> 'log': the Spec's own failure line names the verb
    ("I could not record ..."); otherwise a spelling rule."""
    rec = _d(s.get("recording"))
    said = set(re.findall(r"[a-z]+", " ".join(str(rec.get(k) or "") for k in ("failed", "failed_item")).lower()))
    for base in (word[:-2], word[:-1], word[:-3]):
        if base in said:
            return base
    stem = word[:-2]
    if stem.endswith("i"):
        return stem[:-1] + "y"
    if len(stem) > 2 and stem[-1] == stem[-2] and stem[-1] not in "ls" + _VOWELS:
        return stem[:-1]
    if len(stem) > 2 and stem[-1] not in _VOWELS + "wx" and stem[-2] in _VOWELS and stem[-3] not in _VOWELS and not (
            stem[-1] == "r" and stem[-2] == "e"):
        return stem + "e"           # the silent e of store, save, note and capture (enter and register have none)
    return stem


def _post_success_ptrs(s):
    """Pointers of lines spoken only after a successful write (or never spoken)."""
    out = set()
    for i, rs in enumerate(_l(s.get("required_sentences"))):
        if str(_d(rs).get("trigger", "")).startswith(_POST_SUCCESS_TRIGGERS):
            out.add(_RS_TEXT_PTR % i)
    words = success_words(s)
    for i, it in enumerate(_l(s.get("intents"))):
        act = _d(_d(it).get("action"))
        # an answer_continue line naming the success word is held back until a promise is recorded (runtime)
        if act.get("kind") == "answer_continue" and any(_word_re(w).search(str(act.get("say") or "")) for w in words):
            out.add(_INTENT_ACT_PTR % (i, "say"))
    for sid in _d(_d(s.get("closing")).get("per_situation")):
        if sid == "S_PROMISE":
            out.add("/closing/per_situation/" + esc(sid))
    return out


# a recording disclosure whose WHOLE subject is the call: it starts the text or a clause (after punctuation or a
# conjunction), so "an amount of this call ..." or "all calls ..." never match
_REC_LEAD = r"(?:^|(?<=[,;:.!?] )|(?<=\band )|(?<=\bbut )|(?<=\bthat )|(?<=\bso ))"
_REC_SUBJ = r"(this call|the call|calls|this conversation)"
_REC_VERB = r"(is|is being|are|are being|will be|(may|might|can|could) be)"


def _neg_use(w):
    """A negated use of the success word ('cannot be recorded', 'has not been recorded'): no success claim."""
    return re.compile(r"\b(?:not|never|cannot|can't|couldn't|won't|wouldn't|isn't|wasn't|aren't|weren't|hasn't|haven't"
                      r"|hadn't)\s+(?:(?:yet|be|been|being)\s+){0,2}%s\b" % re.escape(w), re.I)


def _active_voice(text, w, base):
    """'this call is recorded' -> 'we record this call'; 'the call may be recorded' -> 'we may record this call'.
    Only a disclosure whose whole subject is the call; never a negated clause (no success claim) and never one joined
    with 'and <participle>' ('recorded and monitored'): those are left as they are."""
    def rep(m):
        subj = "this " + m.group(1).lower()[4:] if m.group(1).lower().startswith("the ") else m.group(1).lower()
        out = "we %s%s %s" % (m.group(3).lower() + " " if m.group(3) else "", base, subj)
        return out[0].upper() + out[1:] if m.group(1)[0].isupper() else out
    pat = r"%s%s %s %s\b(?!,?\s+(?:and|or|and/or)\s+[a-z]+ed\b)" % (_REC_LEAD, _REC_SUBJ, _REC_VERB, re.escape(w))
    return re.sub(pat, rep, text, flags=re.I)


def _without_success_words(s, text, words):
    for w in words:
        if _word_re(w).search(text):
            text = _active_voice(text, w, _base_verb(w, s))
    return text


def _claims_success(text, w):
    """The success word is still said, outside a negated clause."""
    return bool(_word_re(w).search(_neg_use(w).sub(" ", text)))


def _pre_success_lines(s):
    """(pointer, text) of every line that can be spoken before a promise is recorded."""
    post = _post_success_ptrs(s)
    return [(p, t) for p, t in _line_pointers(s) if p not in post and not p.startswith(_POST_SUCCESS_PTRS)]


def _verbatim_ptrs(s):
    out = {"/opening/line"} if _d(s.get("opening")).get("verbatim") else set()
    return out | {_RS_TEXT_PTR % i for i, rs in enumerate(_l(s.get("required_sentences"))) if _d(rs).get("verbatim")}


def _success_word_fixes(s, warnings, fixes):
    """No line spoken before a successful write says the success word: a passive use of it is put in the active
    voice (meaning kept, 'record' still said); a line the brief dictates verbatim, or one the rule cannot rewrite,
    is only warned about."""
    words = success_words(s)
    if not words:
        return
    verbatim = _verbatim_ptrs(s)
    for ptr, text in _pre_success_lines(s):
        new = text if ptr in verbatim else _without_success_words(s, text, words)
        if new != text:
            _set_ptr(s, ptr, new)
            fixes.append("%s: success word said before success, active voice (%r -> %r)" % (ptr, text, new))
        left = [w for w in words if _claims_success(new, w)]
        if left:
            warnings.append("%s: says %s before a promise is recorded%s" % (
                ptr, "/".join(left), " (verbatim in the brief)" if ptr in verbatim else ""))
