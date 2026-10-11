"""BriefDoc + ToolCatalog -> Spec draft via 6 parallel facet calls (docs/CONTRACTS.md F). Owner: agent 5.
Single route (MVP). Prompts live in builder/prompts/ and contain only synthetic examples.

Each facet call returns {"values": {<facet keys>}, "sources": [{"pointer", "quote"}], "decisions": [...],
"residual": [{"text", "class"}]}. Code then:
- keeps only the facet's own keys, merges the facets into one Spec draft;
- verifies every quote is a (normalised) substring of the brief: unverified quotes are dropped and logged;
- checks quote coverage of the value-critical leaves (bands, identity questions, ladder, situations, required
  sentences, callback rules, calendar) and that numbers in band rows occur in their quote: gaps are warnings;
- fills meta (inputs, openapi_sha256, sources, decisions, residual_rules, warnings) and products.fields (catalog).
"""
import copy
import json
import re

from builder import llm, paths, trace
from builder.pipeline import segment as seg
from builder.spec import defaults as spec_defaults
from builder.spec import vocab

FACETS = {
    "F1": ["bank", "call_variables", "addressing", "opening", "banned", "right_party", "third_party"],
    "F2": ["identity"],
    "F3": ["products", "statement", "calendar", "bands"],
    "F4": ["promise_date", "amounts", "negotiation"],
    "F5": ["intents"],
    "F6": ["confirmation", "recording", "required_sentences", "closing", "lines"],
    # split from F5 (BUILD SPEED): the intents alone set the length of the parallel wave
    "F7": ["situations", "outcomes", "notes", "multi_product"],
}
FACET_OPTIONAL_KEYS = {"F5": ["interpretation"]}      # CONTRACT NOTE: brief overrides of §5.3 rows ride on F5
FACET_TIMEOUT_S = 300   # one stuck facet must leave time for its retry inside the 26-min cap
_DEFS = "$defs"
_ENUM_BIT = "enum %s"      # catalog view: one enum annotation

# Leaves whose value must be backed by a quote (pointer prefixes; a covering parent or child source counts).
CRITICAL_PREFIXES = ("/bands", "/identity/questions", "/identity/max_wrong_total", "/identity/hints",
                     "/negotiation/ladder", "/negotiation/first_ask", "/situations", "/required_sentences",
                     "/third_party/callback", "/calendar/holidays", "/calendar/business_weekdays",
                     "/products/types", "/call_variables", "/opening", "/right_party/ask", "/confirmation/question",
                     "/amounts/too_much", "/amounts/below_floor", "/recording/tries", "/intents")

_NUM_WORD = {1: ("one", "first", "once"), 2: ("two", "second", "twice"), 3: ("three", "third"),
             4: ("four", "fourth"), 5: ("five", "fifth"), 6: ("six", "sixth"), 7: ("seven", "seventh"),
             8: ("eight", "eighth"), 9: ("nine", "ninth"), 10: ("ten", "tenth"), 11: ("eleven", "eleventh"),
             12: ("twelve", "twelfth"), 0: ("zero", "no", "none")}


def _schema():
    return json.loads(paths.SCHEMA.read_text())


def _prune_required(node, dflt):
    """Drop 'required' entries that DEFAULTS can fill (recursively for inline objects)."""
    if not isinstance(node, dict) or not isinstance(dflt, dict):
        return node
    node = copy.deepcopy(node)
    if isinstance(node.get("required"), list):
        node["required"] = [k for k in node["required"] if k not in dflt]
    props = node.get("properties") or {}
    for k, sub in props.items():
        if k in dflt and isinstance(dflt[k], dict):
            props[k] = _prune_required(sub, dflt[k])
    return node


def facet_schema(facet):
    """JSON sub-schema for one facet: the facet's top-level properties of spec/schema.json + all $defs.
    products.fields is removed (bound by code); keys DEFAULTS can fill are not required."""
    full = _schema()
    keys = FACETS[facet]
    props = {}
    for k in keys + FACET_OPTIONAL_KEYS.get(facet, []):
        props[k] = copy.deepcopy(full["properties"][k])
    if "products" in props:
        p = props["products"]
        p["properties"].pop("fields", None)
        p["required"] = [r for r in p.get("required", []) if r != "fields"]
    obj = {"type": "object", "additionalProperties": False, "required": list(keys), "properties": props}
    obj = _prune_required(obj, spec_defaults.DEFAULTS)
    obj[_DEFS] = copy.deepcopy(full[_DEFS])
    return obj


def output_schema(facet):
    """The structured-output schema of one facet call (values + sources + decisions + residual)."""
    fs = facet_schema(facet)
    defs = fs.pop(_DEFS)
    return {
        "type": "object", "additionalProperties": False,
        "required": ["values", "sources", "decisions", "residual"],      # "dated" is optional
        "properties": {
            "values": fs,
            "sources": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["pointer", "quote"],
                "properties": {"pointer": {"type": "string"}, "quote": {"type": "string"}}}},
            "decisions": {"type": "array", "items": {"type": "string"}},
            "residual": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": ["text", "class"],
                "properties": {"text": {"type": "string"}, "class": {"enum": ["speech", "flow"]}}}},
            "dated": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "required": ["from", "until", "pointer", "value_json", "quote"],
                "properties": {"from": {"type": "string", "description": "YYYY-MM-DD, first day the change applies"},
                               "until": {"type": "string", "description": "YYYY-MM-DD it stops applying, or ''"},
                               "pointer": {"type": "string", "description": "JSON pointer into values"},
                               "value_json": {"type": "string", "description": "the new value at the pointer, as JSON"},
                               "quote": {"type": "string"}}}},
        },
        _DEFS: defs,
    }


# ----------------------------------------------------------------------------------------------- prompts

def load_prompt(name):
    return (paths.PROMPTS / name).read_text()


def catalog_summary(catalog):
    """Compact, model-readable view of the ToolCatalog (tools, fields, enums, descriptions, roles)."""
    out = ["server: %s   identity_mode: %s" % (catalog.get("server", ""), catalog.get("identity_mode", ""))]
    for name, t in (catalog.get("tools") or {}).items():
        out.append("\n## tool %s  (%s %s)%s" % (name, t.get("method", "POST"), t.get("path", ""),
                                                 "  - " + t["summary"] if t.get("summary") else ""))
        out.append("request fields:")
        for f, d in (t.get("request") or {}).items():
            bits = [d.get("type", "")]
            if d.get("required"):
                bits.append("required")
            if d.get("enum"):
                bits.append(_ENUM_BIT % d["enum"])
            if d.get("format"):
                bits.append("format %s" % d["format"])
            if d.get("description"):
                bits.append('"%s"' % d["description"])
            out.append("  - %s: %s" % (f, ", ".join(b for b in bits if b)))
        out.append("response leaves (data.*):")
        for f, d in (t.get("response") or {}).items():
            bits = [d.get("type", "")]
            if d.get("enum"):
                bits.append(_ENUM_BIT % d["enum"])
            if d.get("description"):
                bits.append('"%s"' % d["description"])
            out.append("  - %s: %s" % (f, ", ".join(b for b in bits if b)))
            for leaf, ld in (d.get("items") or {}).items():
                lb = [ld.get("type", "")]
                if ld.get("enum"):
                    lb.append(_ENUM_BIT % ld["enum"])
                if ld.get("description"):
                    lb.append('"%s"' % ld["description"])
                out.append("      item %s: %s" % (leaf, ", ".join(b for b in lb if b)))
        roles = t.get("roles") or {}
        out.append("roles: %s" % json.dumps(roles, sort_keys=True))
    out.append("\nenums: %s" % json.dumps(catalog.get("enums") or {}, sort_keys=True))
    if catalog.get("reasonless_outcomes_hint"):
        out.append("outcomes the API documents as sent without a reason: %s" % catalog["reasonless_outcomes_hint"])
    for w in catalog.get("warnings") or []:
        out.append("note: %s" % w)
    return "\n".join(out)


def defaults_for(facet):
    d = {k: spec_defaults.DEFAULTS[k] for k in FACETS[facet] if k in spec_defaults.DEFAULTS}
    if facet == "F5":
        d["interpretation"] = spec_defaults.DEFAULT_INTERPRETATION
    return json.dumps(d, indent=1, sort_keys=True) if d else "(none for this facet)"


def format_feedback(feedback):
    if not feedback:
        return ""
    items = feedback if isinstance(feedback, (list, tuple)) else [feedback]
    lines = []
    for it in items[:40]:
        if isinstance(it, dict):
            it = "%s: %s%s" % (it.get("pointer", ""), it.get("problem", ""),
                               (' (brief: "%s")' % it["quote"]) if it.get("quote") else "")
        lines.append("- " + str(it))
    return ("\n# Corrections required (a previous extraction of this facet was rejected)\n\n"
            + "\n".join(lines) + "\n\nFix these while keeping everything else faithful to the brief.\n")


def build_prompt(facet, bdoc, catalog, feedback=None):
    common = load_prompt("facet_common.md")
    common = (common.replace("@@FACET@@", facet)
              .replace("@@KEYS@@", ", ".join(FACETS[facet]))
              .replace("@@DEFAULTS@@", defaults_for(facet))
              .replace("@@FACET_TEXT@@", load_prompt(facet + ".md"))
              .replace("@@FEEDBACK@@", format_feedback(feedback)))
    return ("# The brief (numbered lines; when quoting, copy only the text after \"| \")\n\n" + bdoc["numbered"]
            + "\n# Bank API catalog (parsed from the tool API file)\n\n" + catalog_summary(catalog) + "\n\n"
            + common)


# ----------------------------------------------------------------------------------------------- checks

def _resolve(obj, ptr):
    cur = obj
    for part in [p.replace("~1", "/").replace("~0", "~") for p in ptr.split("/")[1:]]:
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return None, False
    return cur, True


def verify_sources(sources, values, hay_norm, facet):
    """-> (verified {pointer: quote}, warnings)."""
    ok, warns = {}, []
    for s in sources or []:
        ptr = str(s.get("pointer", "")).strip()
        quote = str(s.get("quote", ""))
        if not ptr.startswith("/"):
            ptr = "/" + ptr
        _, exists = _resolve(values, ptr)
        if not exists:
            warns.append("%s source for missing pointer %s dropped" % (facet, ptr))
            continue
        if not seg.quote_in(quote, hay_norm):
            warns.append("%s unverified quote for %s dropped: %r" % (facet, ptr, quote[:120]))
            continue
        if ptr in ok and ok[ptr] != quote:
            ok[ptr] = ok[ptr] + " ... " + quote
        else:
            ok[ptr] = quote
    return ok, warns


def _covered(ptr, sources):
    return any(ptr.startswith(q) or q.startswith(ptr) for q in sources)


def coverage_gaps(values, sources):
    """Value-critical pointers present in `values` without any quote at, above or below them."""
    gaps = []
    for pref in CRITICAL_PREFIXES:
        v, exists = _resolve(values, pref)
        if not exists or v in ([], {}, "", None):
            continue
        if isinstance(v, list):
            for i in range(len(v)):
                if not _covered("%s/%d" % (pref, i), sources):
                    gaps.append("%s/%d" % (pref, i))
        elif isinstance(v, dict) and pref in ("/situations", "/products/types"):
            for k in v:
                if not _covered("%s/%s" % (pref, k), sources):
                    gaps.append("%s/%s" % (pref, k))
        elif not _covered(pref, sources):
            gaps.append(pref)
    return gaps


def _num_in_quote(n, quote):
    q = quote.lower()
    if re.search(r"(?<!\d)%d(?!\d)" % n, q):
        return True
    return any(re.search(r"\b%s\b" % w, q) for w in _NUM_WORD.get(n, ()))


def number_gaps(values, sources):
    """Band rows: days_late bounds, deadline n and attempts should be derivable from the row's quote."""
    out = []
    for i, b in enumerate(values.get("bands") or []):
        if not isinstance(b, dict):
            continue
        qs = " ".join(q for p, q in sources.items() if p.startswith("/bands/%d" % i) or p == "/bands")
        if not qs:
            continue
        nums = [b.get("days_late_min"), b.get("days_late_max"), b.get("attempts"),
                (b.get("deadline") or {}).get("n")]
        for n in nums:
            if isinstance(n, int) and not _num_in_quote(n, qs):
                out.append("/bands/%d: %d not found in its quote" % (i, n))
    return out


# ----------------------------------------------------------------------------------------------- extract

def facet_call(facet, bdoc, catalog, budget, feedback=None):
    t = FACET_TIMEOUT_S if budget is None else budget.call_timeout(FACET_TIMEOUT_S)
    model, effort = llm.choice(facet)                  # BUILDER_FACET_MODEL / BUILDER_FACET_EFFORT, else the defaults
    return {"purpose": "extract %s (%s)" % (facet, ", ".join(FACETS[facet])),
            "system": load_prompt("system.md"), "prompt": build_prompt(facet, bdoc, catalog, feedback),
            "schema": output_schema(facet), "timeout_s": t, "effort": effort, "model": model, "budget": budget}


def extract(bdoc, catalog, budget, only=None, feedback=None, base=None):
    """Run facet calls (all, or `only` facet ids with validator `feedback`) -> merged Spec draft dict.
    Fills meta.inputs and products.fields (from catalog roles.item) by code.

    base: a previous draft to merge into (re-extraction keeps the other facets). feedback: list of error strings
    or critic issue dicts, given to every facet in `only`."""
    facets = [f for f in (only or list(FACETS)) if f in FACETS]
    spec = copy.deepcopy(base) if base else {}
    meta = spec.setdefault("meta", {})
    meta["inputs"] = [{"path": d["path"], "sha256": d["sha256"]} for d in bdoc["docs"]]
    if catalog.get("openapi_sha256"):
        meta["openapi_sha256"] = catalog["openapi_sha256"]
    for k in ("decisions", "warnings"):
        meta.setdefault(k, [])
    meta.setdefault("residual_rules", [])
    meta.setdefault("sources", {})
    if budget is not None and budget.call_timeout(FACET_TIMEOUT_S) <= 0:
        trace.event("BUDGET", "no time left for extraction", facets=facets)
        meta["warnings"].append("extraction skipped: budget")
        if not base:
            from builder.budget import BudgetExceeded
            raise BudgetExceeded("no time left for the first extraction")
        return spec
    if base:
        # a re-extracted facet replaces its own residual rules and decisions instead of appending a second copy
        meta["residual_rules"] = [r for r in meta["residual_rules"]
                                  if not (isinstance(r, dict) and r.get("bound_to") in facets)]
        meta["decisions"] = [d for d in meta["decisions"]
                             if not any(str(d).startswith(f + ": ") for f in facets)]
    calls = [facet_call(f, bdoc, catalog, budget, feedback) for f in facets]
    trace.event("EXTRACT", "facet calls start", facets=facets, reextract=bool(only),
                prompt_chars=[len(c["prompt"]) for c in calls])
    results = llm.run_parallel(calls, max_concurrency=6)
    hay = seg.norm_quote_text(bdoc.get("text") or "\n".join(d["text"] for d in bdoc["docs"]))
    failed = []
    for facet, res in zip(facets, results):
        if isinstance(res, Exception):
            failed.append(facet)
            msg = "facet %s failed: %s" % (facet, str(res)[:300])
            meta["warnings"].append(msg)
            trace.event("ERROR", msg, mod="builder.pipeline.extract.extract")
            continue
        values = res.get("values") or {}
        allowed = FACETS[facet] + FACET_OPTIONAL_KEYS.get(facet, [])  # the output schema rejects foreign keys
        # replace this facet's keys (drop stale ones from base)
        for k in allowed:
            spec.pop(k, None)
        meta["sources"] = {p: q for p, q in meta["sources"].items()
                           if p.split("/")[1:2] and p.split("/")[1] not in allowed}
        for k in allowed:
            if k in values:
                spec[k] = values[k]
        src, warns = verify_sources(res.get("sources"), values, hay, facet)
        meta["sources"].update(src)
        gaps = coverage_gaps(values, src)
        ngaps = number_gaps(values, src)
        for w in warns + ["%s no quote for %s" % (facet, g) for g in gaps] + ngaps:
            meta["warnings"].append(w)
        merge_dated(spec, facet, allowed, res.get("dated"), hay, meta)
        meta["decisions"] += ["%s: %s" % (facet, d) for d in res.get("decisions") or []]
        for r in res.get("residual") or []:
            if isinstance(r, dict) and r.get("text"):
                meta["residual_rules"].append({"text": r["text"], "class": r.get("class", "flow"),
                                               "bound_to": facet})
        trace.event("EXTRACT", "facet %s ok" % facet, keys=[k for k in allowed if k in values],
                    sources=len(src), dropped_quotes=len(warns), coverage_gaps=len(gaps), number_gaps=len(ngaps))
    if failed:
        meta["failed_facets"] = failed                  # transient; removed by validate()-time cleanup
    spec["spec_version"] = vocab.SPEC_VERSION
    return spec


def merge_dated(spec, facet, allowed, entries, hay, meta):
    """A facet's dated entries -> Spec.dated (replacing that facet's earlier entries). The pointer must be inside the
    facet's own keys; value_json is parsed (plain text if it is not JSON); an unverified quote is a warning."""
    keep = [d for d in spec.get("dated") or [] if str(d.get("path", "")).split("/")[1:2] and
            str(d.get("path", "")).split("/")[1] not in allowed]
    for e in entries or []:
        d = _dated_entry(facet, allowed, e, hay, meta) if isinstance(e, dict) else None
        if d is not None:
            keep.append(d)
    if keep:
        spec["dated"] = keep
    else:
        spec.pop("dated", None)


def _dated_entry(facet, allowed, e, hay, meta):
    """One extracted dated entry -> a Spec.dated item, or None (pointer outside the facet: dropped with a warning)."""
    ptr = "/" + str(e.get("pointer", "")).strip().lstrip("/")
    if ptr.split("/")[1] not in allowed:
        meta["warnings"].append("%s dated entry outside the facet dropped: %s" % (facet, ptr))
        return None
    try:
        val = json.loads(e.get("value_json", ""))
    except (TypeError, ValueError):
        val = e.get("value_json", "")
    d = {"from": str(e.get("from", "")).strip(), "path": ptr, "value": val}
    if str(e.get("until") or "").strip():
        d["until"] = str(e["until"]).strip()
    q = str(e.get("quote") or "")
    if q:
        d["source"] = q
        if not seg.quote_in(q, hay):
            meta["warnings"].append("%s unverified quote for dated %s: %r" % (facet, ptr, q[:120]))
    return d


def failed_facets(spec):
    return list(((spec or {}).get("meta") or {}).get("failed_facets") or [])


def clean_meta(spec):
    """Remove transient meta keys so the Spec validates against the schema."""
    m = (spec or {}).get("meta")
    if isinstance(m, dict):
        m.pop("failed_facets", None)
    return spec
