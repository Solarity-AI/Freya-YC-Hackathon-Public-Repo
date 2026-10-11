"""Build the ctl code string (docs/CONTRACTS.md C.1, C.8). Owner: agent 3."""
import copy

INTENT_EXTRACTION_ONLY = ("label", "description", "examples", "negatives")
RP_EXTRACTION_ONLY = ("confirm_examples", "non_confirm_examples")


class SnippetError(Exception):
    pass


def runtime_spec(spec, wiring_):
    """-> rspec dict {"v": 1, "spec": spec without meta and extraction-only fields, "wiring": wiring_} (C.8)."""
    s = copy.deepcopy(spec)
    s.pop("meta", None)
    for it in s.get("intents") or []:
        _drop(it, INTENT_EXTRACTION_ONLY)
    _drop(s.get("right_party"), RP_EXTRACTION_ONLY)
    # never read by the runtime (checked at build time only): every byte of the rspec ships in the ctl code
    s.pop("banned", None)
    for d in (s.get("call_variables") or {}).get("declared") or []:
        _drop(d, ("meaning",))
    for d in s.get("dated") or []:
        _drop(d, ("source",))
    return {"v": 1, "spec": s, "wiring": copy.deepcopy(wiring_)}


def _drop(d, keys):
    """Remove `keys` from d in place when d is a dict (anything else is left alone)."""
    if isinstance(d, dict):
        for k in keys:
            d.pop(k, None)


def check_code(code):
    """-> list of problems: braces, compile errors. Empty list = OK."""
    problems = []
    if not isinstance(code, str) or not code.strip():
        return ["empty code"]
    for i, line in enumerate(code.splitlines(), 1):
        if "{{" in line or "}}" in line:
            problems.append(f"line {i}: Freya braces in code")
    try:
        compile(code, "ctl", "exec")
    except SyntaxError as e:
        problems.append(f"compile error: {e}")
    return problems


# customer turns kept free below the live code_exec limit (lint.turns_to_limit), and the smallest budget ever set
TURN_MARGIN = 4
MIN_TURN_CAP = 12


def turn_cap(code, lang="en"):
    """The safe customer-turn budget for this packed ctl code: the turn a long multi-product call would pass the
    platform's code_exec limit (live constants in lint; faster growth in a non-English call), minus TURN_MARGIN.
    The runtime wraps up there."""
    from builder.compiler import lint
    return max(MIN_TURN_CAP, lint.turns_to_limit(code, lang) - TURN_MARGIN)


def build_ctl_code(spec, wiring_):
    """runtime.bundle.make_snippet(runtime_spec(...)); re-checks brace safety and compile(). Packed twice: the first
    pack measures the code, the second carries the turn budget it allows (spec.turn_cap)."""
    from runtime import bundle
    code = _pack(bundle, runtime_spec(spec, wiring_))
    rs = runtime_spec(spec, wiring_)
    from runtime.locale import lang_of
    rs["spec"]["turn_cap"] = turn_cap(code, lang_of(spec))
    return _pack(bundle, rs)


def _pack(bundle, rs):
    # no cap on the inner snippet: only the packed code meets the platform (PACK_MAX_BYTES, lint projection).
    # compact=True: conventional wiring nodes ship as {tool, bf} (the runtime expands them), about 0.7 KB packed.
    inner = bundle.make_snippet(rs, encoding="json", max_bytes=0, compact=True)
    problems = check_code(inner)
    if problems:
        raise SnippetError("; ".join(problems[:5]))
    # LIVE FACT 2026-10-11: code_exec refuses code + data over 131072 bytes, so the ~170 KB snippet ships packed
    # (raw DEFLATE + an 85-letter text encoding + an exec() loader). See runtime.bundle.pack_snippet.
    try:
        code = bundle.pack_snippet(inner)
    except Exception as e:                                           # noqa: BLE001
        raise SnippetError("pack failed: %s" % e) from None
    problems = check_code(code)
    if problems:
        raise SnippetError("; ".join(problems[:5]))
    return code
