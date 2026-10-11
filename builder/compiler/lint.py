"""L0 lint and structural invariants on a compiled workflow (docs/CONTRACTS.md D.6 'Lint rules'). Owner: agent 3.

Every finding: {"level": "error"|"warn", "rule": <id>, "where": <node or spec pointer>, "msg": <text>}.
Rule ids (stable, used by tests and the trace):
  null, initial, global_nodes, forbidden_key, node_type, target_missing, passthrough_always, dup_target,
  fallback_target, matches_intent, tools_present, pre_action_placement, pre_action_shape, suppress_results,
  code_braces, code_compile, code_imports, code_size, api_tool, api_url, api_method, api_body_field, api_enum,
  api_required, api_max_retries, api_timeout, response_mapping, entry_guard, close_reason, var_writer,
  listen_node, end_node, banned_word, disclosure_word, spec_enum, reasonless_reason, required_sentence,
  placeholder, reach, reach_source, byte_stable, workflow_size, nondeterminism, line_repeat, line_question,
  intent_scope, opening_sentence, hop_bound
"""
import ast
import json
import re

from builder.compiler import graph, render
from builder.spec import vocab

ALLOWED_IMPORTS = ("json", "re", "datetime")
# LIVE FACT 2026-10-11: code_exec refuses code + data (variable table) over 131072 bytes; leave >= 30 KB for data.
# warn just under the pack cap (runtime.bundle.PACK_MAX_BYTES = 85_000), so the warning means "close to the limit"
CODE_WARN_BYTES = 82_000
CODE_MAX_BYTES = 100_000
# The platform counts the JSON-escaped code plus the variable table (about 16 KB at the start, about 250-300 B more
# per customer turn, about 1 KB of response headers per api tool) against CODE_EXEC_LIMIT.
CODE_EXEC_LIMIT = 131_072
CODE_PROJECTED_MAX = 122_880
DATA_BASE_BYTES = 16_384
DATA_PER_TURN_BYTES = 300
DATA_PER_API_BYTES = 1_024
MAX_TURNS = 40
# LIVE FACT 2026-10-11 (Brief A+B, talkative customer, 3 products): code_exec was refused at customer turn 41 with
# 80,393 B of escaped code. The variable table the platform adds grew 230-700 B per customer turn (about 470 on
# average: it carries the conversation), from about 31 KB once a 3-product account was read; the Spec's own variables
# stay near 6 KB. The projection above under-counts such a call, so lint also reports the turn the limit is reached.
LIVE_DATA_BASE_MULTI = 31_000
LIVE_DATA_PER_TURN = 470
LIVE_DATA_PER_TURN_X = 700          # estimate for a non-English call (not measured live)
# fewer turns than this before the limit is a lint error (snippet.MIN_TURN_CAP 12 + snippet.TURN_MARGIN 4)
MIN_SAFE_TURNS = 16
# Per customer turn, node entries the twin allows (harness.scenarios.DEFAULT_MAX_HOPS); each hop costs platform time.
HOP_BOUND = 24
WORKFLOW_WARN_BYTES = 1_000_000
NODE_TYPES = ("conversation", "api_request", "code", "end_call")
FORBIDDEN_TOP = ("context_variables", "agent_config", "tools")
# Generic disclosure lexicon (warn level): words that hint at the call's purpose before verification.
DISCLOSURE = ("debt", "debts", "collection", "collections", "overdue", "arrears", "owe", "owed", "owing", "balance",
              "payment", "payments", "loan", "card", "late", "outstanding", "bill", "amount", "due")
# the same lexicon in other call languages (dictionary forms; endings are matched by word_rx)
DISCLOSURE_BY_LANG = {"tr": ("borç", "ödeme", "gecikme", "gecikmiş", "tahsilat", "bakiye", "kredi", "kart", "vade",
                             "tutar", "icra", "taksit")}
VAR_RE = re.compile(r"\{\{([^{}]*)\}\}")  # inner text; callers strip it (a lazy \s*-wrapped group backtracks)
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*(:json)?$")
CTL_WRITES = ("say", "nx", "st", "ph", "co", "cr", "cmode", "dbg_step", "dbg_err")


def _vars_in(t):
    """The {{...}} placeholder names in t, surrounding whitespace removed."""
    return [v.strip() for v in VAR_RE.findall(t)]


def errors(findings):
    return [f for f in findings if f.get("level") == "error"]


def _f(level, rule, where, msg):
    return {"level": level, "rule": rule, "where": str(where), "msg": str(msg)}


# ------------------------------------------------------------------------------------------------ helpers

def _walk_nulls(x, path, out):
    if x is None:
        out.append(path or "/")
    elif isinstance(x, dict):
        for k, v in x.items():
            _walk_nulls(v, path + "/" + str(k), out)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            _walk_nulls(v, path + "/" + str(i), out)


def _strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)


def _conds(cond):
    """Flatten a condition into leaf conditions."""
    if not isinstance(cond, dict):
        return []
    if "conditions" in cond:
        out = []
        for c in cond.get("conditions") or []:
            out += _conds(c)
        return out
    return [cond]


def _is_always(tr):
    return (tr.get("condition") or {}).get("operator") == "always"


def _code_of(node):
    for pa in node.get("pre_actions") or []:
        fn = pa.get("function") or {}
        if fn.get("handler") == "__function__:code_exec":
            return ((fn.get("parameters") or {}).get("properties") or {}).get("code", {}).get("default")
    return None


def _api_fn(node):
    pas = node.get("pre_actions") or []
    if len(pas) != 1:
        return None
    return pas[0].get("function") or {}


def _body_props(fn):
    props = ((fn.get("parameters") or {}).get("properties") or {})
    return props, ((props.get("body") or {}).get("properties") or {}), (props.get("body") or {}).get("required") or []


# Languages that attach endings to a word stem: a banned word is caught with any ending, and (Turkish) with its last
# consonant softened before a vowel ending: borç -> borcu / borcunuz, kitap -> kitabı, ödeme -> ödemeniz.
SUFFIXING = ("tr", "az", "fi", "hu", "et", "uz", "kk")
_SOFTEN = {"ç": "c", "k": "ğ", "p": "b", "t": "d", "g": "ğ"}


def word_rx(word, lang="en"):
    """Compiled regex for one banned word (or phrase) in the call language, matched on lang_lower()ed text. English
    and other languages: whole words. Suffixing languages: the stem plus any ending, the softened stem too."""
    from runtime.locale import lang_lower
    w = lang_lower(str(word or "").strip(), lang)
    if not w:
        return None
    if lang in SUFFIXING:
        stems = {re.escape(w)}
        if len(w) >= 3 and w[-1] in _SOFTEN:
            stems.add(re.escape(w[:-1] + _SOFTEN[w[-1]]))
        if w.endswith("nk"):
            stems.add(re.escape(w[:-1] + "g"))
        return re.compile(r"(?<!\w)(?:" + "|".join(sorted(stems)) + r")\w*")
    return re.compile(r"(?<![^\W_])" + re.escape(w) + r"(?![^\W_])")


def words_hit(words, text, lang="en"):
    """The banned `words` that occur in `text` (case-insensitive; Turkish I/İ handled; endings in suffixing
    languages, see word_rx). Shared by lint and validate."""
    from runtime.locale import lang_lower
    t = lang_lower(text or "", lang)
    out = []
    for w in words or []:
        rx = word_rx(w, lang) if w else None
        if rx is not None and rx.search(t):
            out.append(w)
    return out


def _words_hit(words, text, lang="en"):
    if lang == "en":
        t = text.lower()
        return [w for w in words if w and re.search(r"(?<![a-z0-9])" + re.escape(w.lower()) + r"(?![a-z0-9])", t)]
    return words_hit(words, text, lang)


# <bank> and <self> are fixed text the line's author knows ("<bank>'ın" is fine); every other slot is a value
_SLOT_SUFFIX = re.compile(r"<(?!(?:bank|self)>)(?:[a-z_]+|v:\w+|f:[\w.]+)>['’]?[^\W\d_]", re.U)


def slot_suffixes(spec):
    """(pointer, text) of every Spec line where an ending is attached to a placeholder ('<amount>'ı, '<date>de'):
    in a suffixing language the ending cannot follow the value's sound, so the slot must stand alone."""
    from runtime.locale import lang_of
    if lang_of(spec) not in SUFFIXING:
        return []
    out = []

    def walk(x, ptr):
        if isinstance(x, dict):
            for k, v in x.items():
                if k != "meta":
                    walk(v, ptr + "/" + str(k))
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, ptr + "/" + str(i))
        elif isinstance(x, str) and _SLOT_SUFFIX.search(x):
            out.append((ptr, x))
    walk(spec, "")
    return out


def _pre_verification_lines(spec):
    """(pointer, template) of every Spec line spoken before verification (B.2), plus generic RP/ID lines."""
    out = []
    op = spec.get("opening") or {}
    out.append(("/opening/line", op.get("line")))
    rp = spec.get("right_party") or {}
    for k in ("ask", "reask"):
        out.append(("/right_party/" + k, rp.get(k)))
    for k, v in (rp.get("answers") or {}).items():
        out.append(("/right_party/answers/" + k, v))
    tp = spec.get("third_party") or {}
    for k in ("reach_ask", "reach_reask", "outside_line", "vague_line", "booked_line", "offer_to_pay_line"):
        if k in tp:
            out.append(("/third_party/" + k, tp.get(k)))
    idn = spec.get("identity") or {}
    for i, q in enumerate(idn.get("questions") or []):
        for k in ("ask", "reask_wrong", "ask_full"):
            out.append(("/identity/questions/%d/%s" % (i, k), q.get(k)))
    for i, h in enumerate(idn.get("hints") or []):
        out.append(("/identity/hints/%d/say" % i, h.get("say")))
    out.append(("/identity/decline/explain", (idn.get("decline") or {}).get("explain")))
    out.append(("/identity/fail_line", idn.get("fail_line")))
    for i, it in enumerate(spec.get("intents") or []):
        if set(it.get("scope") or []) & {"rp", "tp", "id"}:
            act = it.get("action") or {}
            for k in ("say", "question"):
                if k in act:
                    out.append(("/intents/%d/action/%s" % (i, k), act.get(k)))
    lines = spec.get("lines") or {}
    for k in ("clarify", "continue_prompt", "hold"):
        if k in lines:
            out.append(("/lines/" + k, lines.get(k)))
    return [(p, t) for p, t in out if isinstance(t, str) and t]


# ------------------------------------------------------------------------------------------------ rule groups

def _lint_top(wf, out):
    nulls = []
    _walk_nulls(wf, "", nulls)
    for p in nulls[:20]:
        out.append(_f("error", "null", p, "null value (the platform rejects null)"))
    nodes = wf.get("nodes") or {}
    if wf.get("initial_node") not in nodes:
        out.append(_f("error", "initial", "initial_node", f"initial node {wf.get('initial_node')!r} does not exist"))
    elif wf.get("initial_node") != vocab.LISTEN_NODES["open"]:
        out.append(_f("warn", "initial", "initial_node", "initial node is not s_open"))
    if wf.get("global_nodes"):
        out.append(_f("error", "global_nodes", "global_nodes", "global nodes are not used by the MVP graph"))
    for k in FORBIDDEN_TOP:
        if k in wf:
            out.append(_f("error", "forbidden_key", k, f"top-level key {k!r} must not be sent"))
    size = len(json.dumps(wf, separators=(",", ":")))
    if size > WORKFLOW_WARN_BYTES:
        out.append(_f("warn", "workflow_size", "workflow", f"workflow JSON is {size} bytes"))


def _lint_structure(wf, out):
    nodes = wf.get("nodes") or {}
    for key, n in nodes.items():
        _lint_node(wf, nodes, key, n, out)
    if not any(n.get("node_type") == "end_call" for n in nodes.values()):
        out.append(_f("error", "end_node", "nodes", "no end_call node"))


def _lint_node(wf, nodes, key, n, out):
    nt = n.get("node_type")
    trs = _lint_node_basics(nodes, key, n, out)
    _lint_transitions(nodes, key, trs, out)
    _lint_passthrough(key, n, trs, out)
    if n.get("tools"):
        out.append(_f("error", "tools_present", key, "model-callable tools are not allowed"))
    if n.get("pre_actions") and nt not in ("api_request", "code"):
        out.append(_f("error", "pre_action_placement", key, "pre_actions on a %s node are stripped" % nt))
    if nt in ("api_request", "code") and not n.get("passthrough"):
        out.append(_f("error", "pre_action_placement", key, "api/code node must be passthrough"))
    if nt == "code" and _code_of(n) is None:
        out.append(_f("error", "pre_action_shape", key, "code node without a code_exec pre_action"))
    if nt == "api_request":
        _lint_api_node(key, n, out)
    if nt == "conversation" and not n.get("passthrough"):
        _lint_listen_node(wf, key, n, out)
    if nt == "end_call":
        _lint_end_node(key, n, trs, out)


def _lint_node_basics(nodes, key, n, out):
    """node_type, name and the transition list itself. -> the transitions (a list)."""
    nt = n.get("node_type")
    if nt not in NODE_TYPES:
        out.append(_f("error", "node_type", key, f"node_type {nt!r} is not used by this builder"))
    if n.get("name") != key:
        out.append(_f("warn", "node_type", key, "node name differs from its key"))
    trs = n.get("transitions")
    if not isinstance(trs, list):
        out.append(_f("error", "target_missing", key, "transitions is not a list"))
        trs = []
    for fld in ("passthrough_default_transition", "max_turn_transition"):
        if fld in n and n[fld] not in nodes:
            out.append(_f("error", "target_missing", key, f"{fld} -> {n[fld]!r} does not exist"))
    return trs


def _lint_transitions(nodes, key, trs, out):
    seen = set()
    for i, tr in enumerate(trs):
        t = tr.get("target_node")
        if t not in nodes:
            out.append(_f("error", "target_missing", key, f"transition {i} -> {t!r} does not exist"))
        if t in seen:
            out.append(_f("error", "dup_target", key, f"two transitions target {t!r} (the engine merges them)"))
        seen.add(t)
        _lint_transition(key, i, tr, len(trs), out)


def _lint_transition(key, i, tr, n_trs, out):
    t = tr.get("target_node")
    cond = tr.get("condition") or {}
    n_mi = sum(1 for c in _conds(cond) if c.get("operator") == "matches_intent")
    out.extend(_f("error", "matches_intent", key, "matches_intent is not allowed") for _ in range(n_mi))
    if _is_always(tr):
        if i != n_trs - 1:
            out.append(_f("error", "passthrough_always", key, f"'always' transition {i} is not the last one"))
        return
    if t in (vocab.LISTEN_NODES["safe"], vocab.LISTEN_NODES["open"]):
        out.append(_f("error", "fallback_target", key, f"conditional transition into {t}"))
    if cond.get("logic") not in ("or", None):
        out.append(_f("error", "target_missing", key, f"transition {i}: top-level logic must be 'or'"))


def _lint_passthrough(key, n, trs, out):
    if not n.get("passthrough"):
        return
    if not trs or not _is_always(trs[-1]):
        out.append(_f("error", "passthrough_always", key, "passthrough node does not end with 'always'"))
    elif n.get("passthrough_default_transition") != trs[-1].get("target_node"):
        out.append(_f("error", "passthrough_always", key,
                      "passthrough_default_transition differs from the final 'always' target"))


def _lint_api_node(key, n, out):
    fn = _api_fn(n)
    if fn is None or fn.get("handler") != "__function__:api_call":
        out.append(_f("error", "pre_action_shape", key, "api node needs exactly one api_call pre_action"))
    if n.get("suppress_tool_results") is not True:
        out.append(_f("error", "suppress_results", key, "suppress_tool_results must be true"))


def _lint_listen_node(wf, key, n, out):
    if not n.get("task_message"):
        out.append(_f("error", "listen_node", key, "listen node without task_message"))
    names = [x.get("name") for x in n.get("extraction_schema") or []]
    if "u_text" not in names:
        out.append(_f("error", "listen_node", key, "extraction has no u_text"))
    for x in n.get("extraction_schema") or []:
        if "min_confidence" not in x:
            out.append(_f("error", "listen_node", key, f"extraction {x.get('name')} has no min_confidence"))
        if x.get("type") != "string":
            out.append(_f("error", "listen_node", key, f"extraction {x.get('name')} must be type string"))
        if len(x.get("enum_values") or []) > vocab.TOPIC_CAP:
            out.append(_f("error", "listen_node", key, f"extraction {x.get('name')} has > {vocab.TOPIC_CAP} values"))
    if key != wf.get("initial_node") and not n.get("max_turn_transition"):
        out.append(_f("warn", "listen_node", key, "listen node without max_turn_transition"))


def _lint_end_node(key, n, trs, out):
    term = ((n.get("terminal") or {}).get("function") or {})
    mm = (((term.get("parameters") or {}).get("properties") or {}).get("message_mode") or {}).get("default")
    if trs:
        out.append(_f("error", "end_node", key, "end_call node has transitions"))
    if term.get("handler") != "__function__:end_call":
        out.append(_f("error", "end_node", key, "end_call terminal handler missing"))
    if mm != "none":
        out.append(_f("warn", "end_node", key, "end_call message_mode is not 'none'"))
    if n.get("disable_inactivity_monitor") is not True:
        out.append(_f("warn", "end_node", key, "end_call without disable_inactivity_monitor"))


def _lint_code(wf, out):
    for key, n in (wf.get("nodes") or {}).items():
        if n.get("node_type") != "code":
            continue
        code = _code_of(n)
        if not isinstance(code, str):
            continue
        _lint_code_text(key, code, out)
        tree = _code_tree(key, code, out)
        if tree is not None:
            _lint_code_ast(key, tree, out)
        _lint_code_size(wf, key, code, out)


def _lint_code_text(key, code, out):
    for i, line in enumerate(code.splitlines(), 1):
        if "{{" in line or "}}" in line:
            out.append(_f("error", "code_braces", key, f"line {i} contains Freya braces"))
            break
    try:
        compile(code, key, "exec")
    except SyntaxError as e:
        out.append(_f("error", "code_compile", key, f"does not compile: {e}"))


def _code_tree(key, code, out):
    """AST of the code the node runs (the unpacked snippet for packed code), or None when it does not parse."""
    try:
        from runtime import bundle as _rb
        inner = _rb.unpack_snippet(code)
    except Exception as e:                                       # noqa: BLE001
        out.append(_f("error", "code_compile", key, f"packed code does not unpack: {e}"))
        inner = code
    try:
        tree = ast.parse(inner)
        if inner is not code:
            compile(inner, key, "exec")
        return tree
    except SyntaxError as e:
        out.append(_f("error", "code_compile", key, f"does not compile: {e}"))
        return None


def _lint_code_ast(key, tree, out):
    for node in ast.walk(tree):
        for m in _imported(node):
            if m.split(".")[0] not in ALLOWED_IMPORTS:
                out.append(_f("error", "code_imports", key, f"import {m!r} is not allowed"))
        if isinstance(node, ast.Attribute) and node.attr in ("now", "today", "utcnow") and \
                isinstance(node.value, (ast.Name, ast.Attribute)):
            base = node.value.id if isinstance(node.value, ast.Name) else node.value.attr
            if base in ("datetime", "date"):
                out.append(_f("error", "nondeterminism", key, f"real clock call {base}.{node.attr}"))


def _imported(node):
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    if isinstance(node, ast.ImportFrom):
        return [node.module or ""] if node.level == 0 else ["." + (node.module or "")]
    return []


def _lint_code_size(wf, key, code, out):
    size = len(code.encode("utf-8"))
    proj = projected_code_bytes(code, wf)
    turns = turns_to_limit(code)
    if proj > CODE_PROJECTED_MAX:
        # the runtime wraps a call up at its turn budget (compiler/snippet.turn_cap), so a code size that only a
        # 40-turn call would push past the limit is a warning; one that leaves too few turns is an error
        lvl = "error" if turns < MIN_SAFE_TURNS else "warn"
        out.append(_f(lvl, "code_size", key, f"projected code+data {proj} bytes at turn {MAX_TURNS} "
                                             f"(> {CODE_PROJECTED_MAX}; platform limit {CODE_EXEC_LIMIT})"))
    if turns < MAX_TURNS:
        out.append(_f("warn", "code_turns", key, f"a long multi-product call reaches the {CODE_EXEC_LIMIT}-byte "
                                                 f"code_exec limit at about customer turn {turns} (< {MAX_TURNS})"))
    if size > CODE_MAX_BYTES:
        out.append(_f("error", "code_size", key, f"code is {size} bytes (> {CODE_MAX_BYTES})"))
    elif size > CODE_WARN_BYTES:
        out.append(_f("warn", "code_size", key, f"code is {size} bytes (> {CODE_WARN_BYTES})"))


def turns_to_limit(code, lang="en"):
    """Customer turns until JSON-escaped code + the live multi-product variable table pass CODE_EXEC_LIMIT. A call in
    another language grows the table faster per turn (the customer's words twice: u_text and u_en, plus non-ASCII
    letters escaped), so its per-turn growth is LIVE_DATA_PER_TURN_X."""
    try:
        esc = len(json.dumps(code))
    except Exception:                                                # noqa: BLE001
        esc = len(str(code))
    per = LIVE_DATA_PER_TURN if lang == "en" else LIVE_DATA_PER_TURN_X
    return max(0, (CODE_EXEC_LIMIT - esc - LIVE_DATA_BASE_MULTI) // per)


def projected_code_bytes(code, wf):
    """JSON-escaped code + the variable table the platform adds by the last allowed turn."""
    try:
        esc = len(json.dumps(code))
    except Exception:                                                # noqa: BLE001
        esc = len(str(code))
    n_api = sum(1 for n in (wf.get("nodes") or {}).values() if n.get("node_type") == "api_request")
    tools = set()
    for n in (wf.get("nodes") or {}).values():
        if n.get("node_type") == "api_request":
            fn = _api_fn(n) or {}
            tools.add(str(fn.get("url") or fn.get("name") or id(n)))
    return esc + DATA_BASE_BYTES + MAX_TURNS * DATA_PER_TURN_BYTES + DATA_PER_API_BYTES * max(len(tools), min(n_api, 8))


def _sentences(text):
    return [x for x in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if x]


def _lint_spec_lines(spec, out):
    """Spoken-line hygiene the runtime cannot fully repair (warn: the runtime drops near-duplicate sentences)."""
    _lint_fail_line_repeats(spec, out)
    _lint_rest_and_explain(spec, out)
    _lint_change_intents(spec, out)
    _lint_opening(spec, out)


def _lint_fail_line_repeats(spec, out):
    fail = str((spec.get("identity") or {}).get("fail_line") or "").strip().lower()
    if not fail:
        return
    for sid, line in ((spec.get("closing") or {}).get("per_situation") or {}).items():
        for snt in _sentences(line):
            if len(snt) > 12 and snt.lower().strip(" .") in fail:
                out.append(_f("warn", "line_repeat", f"/closing/per_situation/{sid}", "repeats identity.fail_line"))


def _lint_rest_and_explain(spec, out):
    I = spec.get("identity") or {}
    lines = spec.get("lines") or {}
    tm = (spec.get("amounts") or {}).get("too_much") or {}
    if "<rest>" in str(lines.get("floor_offer") or "") and str(tm.get("say_rest") or "").strip():
        out.append(_f("warn", "line_repeat", "/lines/floor_offer", "contains <rest> and amounts.too_much.say_rest is set"))
    if str((I.get("decline") or {}).get("explain") or "").strip().endswith("?"):
        out.append(_f("warn", "line_question", "/identity/decline/explain", "ends with a question; the ask follows it"))


def _lint_change_intents(spec, out):
    for it in spec.get("intents") or []:
        a = it.get("action") or {}
        if a.get("kind") == "answer_continue" and re.search(r"\brecorded\b", str(a.get("say") or ""), re.I) \
                and any(_kw_matches_change(kw) for kw in it.get("keywords") or []):
            out.append(_f("warn", "intent_scope", f"/intents/{it.get('id')}",
                          "recorded-promise answer matches an ordinary date/amount change"))


def _kw_matches_change(kw):
    try:
        return bool(re.search(kw, "can i change the date to monday", re.I) or re.search(kw, "change the amount", re.I))
    except re.error:
        return False


def _lint_opening(spec, out):
    op = spec.get("opening") or {}
    conv = op.get("must_convey") or []
    first = (_sentences(render.strip_runtime(op.get("line", ""), spec)) or [""])[0].lower()
    if "recorded" in conv and "record" not in first:
        out.append(_f("warn", "opening_sentence", "/opening/line", "first sentence does not say the call is recorded"))


def _lint_api(wf, catalog, wiring_, spec, out):
    nodes = wf.get("nodes") or {}
    tools = catalog.get("tools") or {}
    server = catalog.get("server", "")
    cust_key = (spec.get("call_variables") or {}).get("customer_key") or "customer_id"
    wnodes = wiring_.get("nodes") or {}
    for key, n in nodes.items():
        if n.get("node_type") != "api_request":
            continue
        fn = _api_fn(n) or {}
        tname = fn.get("name")
        if tname not in tools:
            out.append(_f("error", "api_tool", key, f"tool {tname!r} is not in the catalog"))
            continue
        tool = tools[tname]
        if key in wnodes and wnodes[key]["tool"] != tname:
            out.append(_f("error", "api_tool", key, f"tool {tname} differs from wiring {wnodes[key]['tool']}"))
        props, body, required = _body_props(fn)
        url = (props.get("url") or {}).get("default")
        if url != tool["url"] or url != server + tool["path"]:
            out.append(_f("error", "api_url", key, f"url {url!r} != server + path {server + tool['path']!r}"))
        if (props.get("method") or {}).get("default") != tool["method"]:
            out.append(_f("error", "api_method", key, f"method differs from the catalog ({tool['method']})"))
        cfg = (n.get("pre_actions") or [{}])[0].get("config") or {}
        cap = graph.IDEMPOTENT_WRITE_RETRIES.get(tname, 0)
        mr = cfg.get("maxRetries")
        if tool.get("write") and not (type(mr) is int and 0 <= mr <= cap):
            out.append(_f("error", "api_max_retries", key, f"a write tool must have maxRetries 0..{cap} "
                          "(only a write that is idempotent by contract may be retried)"))
        if not cfg.get("timeoutMs"):
            out.append(_f("warn", "api_timeout", key, "no explicit timeoutMs"))
        froles = {f: r for r, f in tool["roles"]["request"].items()}
        for field, p in body.items():
            leaf = tool["request"].get(field)
            if leaf is None:
                out.append(_f("error", "api_body_field", key, f"body field {field!r} is not in the catalog"))
                continue
            if p.get("enum") and set(p["enum"]) - set(leaf.get("enum") or []):
                out.append(_f("error", "api_enum", key, f"{field}: enum values outside the catalog"))
            if froles.get(field) == "customer" and p.get("default") != "{{" + cust_key + "}}":
                out.append(_f("error", "api_body_field", key, f"customer field {field} is not baked from {cust_key}"))
        for field in tool.get("required") or []:
            is_reason = froles.get(field) == "reason" and tname == "close_call"
            if field not in body and not is_reason:
                out.append(_f("error", "api_required", key, f"required field {field!r} missing from the body"))
        missing_req = [f for f in required if f not in body]
        if missing_req:
            out.append(_f("error", "api_required", key, f"body.required lists absent fields {missing_req}"))
        # response mapping
        for m in n.get("response_mapping") or []:
            path = str(m.get("path") or "")
            paths_ok = {lf.get("path") for lf in tool["response"].values()}
            if not path.startswith("data.") or path not in paths_ok:
                out.append(_f("error", "response_mapping", key, f"mapping path {path!r} is not a catalog leaf"))
            if not str(m.get("variable") or "").startswith("r_" + key + "_"):
                out.append(_f("error", "response_mapping", key, f"mapping variable {m.get('variable')!r} not r_{key}_*"))
        # close reason rules
        if tname == "close_call":
            rf = tool["roles"]["request"].get("reason")
            if key == vocab.CLOSE_N and rf and rf in body:
                out.append(_f("error", "close_reason", key, "a_close_n must not carry the reason leaf"))
            if key == vocab.CLOSE_R and rf and (body.get(rf) or {}).get("default") != "{{cr}}":
                out.append(_f("error", "close_reason", key, "a_close_r must send the reason from {{cr}}"))


def _guard_var(wiring_, target):
    ent = (wiring_.get("nodes") or {}).get(target) or {}
    return (ent.get("res") or {}).get("s", "r_%s_s" % target)


def _lint_guards(wf, wiring_, out):
    nodes = wf.get("nodes") or {}
    exempt = {wiring_.get("bye") or vocab.BYE_NODE}
    for key, n in nodes.items():
        if key in exempt:
            continue
        for tr in n.get("transitions") or []:
            t = tr.get("target_node")
            if (nodes.get(t) or {}).get("node_type") != "api_request":
                continue
            gv = _guard_var(wiring_, t)
            cond = tr.get("condition") or {}
            groups = cond.get("conditions") if cond.get("logic") == "or" else None
            ok = bool(groups)
            for g in groups or []:
                leaves = _conds(g)
                if not any(c.get("variable") == gv and c.get("operator") == "equals" and
                           str(c.get("operand")) == vocab.PENDING for c in leaves):
                    ok = False
            if not ok:
                out.append(_f("error", "entry_guard", key, f"transition into {t} lacks the '{gv} equals pending' guard"))


def _wiring_writers(wiring_):
    """Variables ctl writes for the wiring: api bodies/results, chain links and the identity-chain links."""
    w = set()
    for ent in (wiring_.get("nodes") or {}).values():
        w |= set(ent.get("body", {}).values())
        w |= set(ent.get("res", {}).values())
    w |= {"wn_" + n for n in wiring_.get("chainable") or []}
    if (wiring_.get("vchain") or {}).get("t"):
        for n in (wiring_.get("api") or {}).get("verify") or []:
            w |= {"wn_" + n, "wl_" + n}
    return w


def _node_writers(wf):
    """Variables the platform writes: response mappings, extraction fields, test variables."""
    w = set()
    for n in (wf.get("nodes") or {}).values():
        w |= {m.get("variable") for m in n.get("response_mapping") or []}
        w |= {x.get("name") for x in n.get("extraction_schema") or []}
    w |= set((wf.get("test_variables") or {}).keys())
    return w


def _writers(wf, wiring_, spec):
    w = set(CTL_WRITES) | set(vocab.SENSOR_VARS) | set(vocab.SENSOR_VARS_X)
    w |= {d.get("name") for d in (spec.get("call_variables") or {}).get("declared") or []}
    return w | _wiring_writers(wiring_) | _node_writers(wf)


def _lint_vars(wf, wiring_, spec, out):
    writers = _writers(wf, wiring_, spec)
    for key, n in (wf.get("nodes") or {}).items():
        texts = []
        oe = n.get("on_enter") or {}
        if oe.get("type") == "tts":
            texts.append(oe.get("text") or "")
        texts.append(n.get("task_message") or "")
        if n.get("node_type") == "api_request":
            texts += list(_strings((_api_fn(n) or {}).get("parameters") or {}))
        for t in texts:
            for v in _vars_in(t):
                if not IDENT_RE.match(v):
                    out.append(_f("error", "placeholder", key, f"malformed placeholder {{{{{v}}}}}"))
                    continue
                name = v.split(":")[0]
                if name not in writers:
                    out.append(_f("error", "var_writer", key, f"{{{{{name}}}}} has no writer"))
        for tr in n.get("transitions") or []:
            for c in _conds(tr.get("condition") or {}):
                var = c.get("variable")
                if var is not None and var not in writers:
                    out.append(_f("error", "var_writer", key, f"condition variable {var!r} has no writer"))
    for t in _strings(wf.get("system_prompt") or ""):
        for v in _vars_in(t):
            if v.split(":")[0] not in writers:
                out.append(_f("error", "var_writer", "system_prompt", f"{{{{{v}}}}} has no writer"))


def _lint_text(wf, spec, out):
    from runtime.locale import lang_of
    lang = lang_of(spec)
    for ptr, text in slot_suffixes(spec):
        out.append(_f("warn", "slot_suffix", ptr, f"an ending is attached to a placeholder (write the sentence so the "
                                                  f"slot stands alone): {text[:80]!r}"))
    banned = list((spec.get("banned") or {}).get("before_verification") or [])
    always = list((spec.get("banned") or {}).get("always") or [])
    ph_re = re.compile(vocab.PLACEHOLDER_RE)
    nodes = wf.get("nodes") or {}
    for key, n in nodes.items():
        oe = n.get("on_enter") or {}
        tts = oe.get("text") if oe.get("type") == "tts" else ""
        for label, t in (("tts", tts), ("task_message", n.get("task_message") or "")):
            if not t:
                continue
            if ph_re.search(t):
                out.append(_f("error", "placeholder", key, f"unresolved Spec placeholder in {label}: {t[:80]!r}"))
            if t.count("«") != t.count("»"):
                out.append(_f("error", "placeholder", key, f"unbalanced quote marks in {label}"))
        if tts and "{{say}}" not in tts:
            hits = _words_hit(banned + always, tts, lang)
            if hits:
                out.append(_f("error", "banned_word", key, f"compile-time tts contains {hits}"))
    sp = wf.get("system_prompt") or ""
    if ph_re.search(sp):
        out.append(_f("error", "placeholder", "system_prompt", "unresolved Spec placeholder"))
    bank_words = set(w.lower() for w in re.findall(r"[A-Za-z]+", str((spec.get("bank") or {}).get("name") or "")))
    for ptr, tpl in _pre_verification_lines(spec):
        for prob in render.check_placeholders(tpl, spec):
            out.append(_f("error", "placeholder", ptr, prob))
        text = render.strip_runtime(tpl, spec)
        hits = _words_hit(banned, text, lang)
        if hits:
            out.append(_f("error", "banned_word", ptr, f"pre-verification line contains {hits}: {text[:80]!r}"))
        soft = [h for h in _words_hit(DISCLOSURE_BY_LANG.get(lang, DISCLOSURE), text, lang)
                if h not in bank_words and h not in hits]
        if soft:
            out.append(_f("warn", "disclosure_word", ptr, f"pre-verification line contains {soft}: {text[:80]!r}"))


def _lint_spec_enums(spec, catalog, out):
    en = catalog.get("enums") or {}
    reasonless = set((spec.get("outcomes") or {}).get("reasonless_outcomes") or [])
    for sid, s in (spec.get("situations") or {}).items():
        s = s or {}
        ptr = "/situations/" + sid
        if en.get("outcome") and s.get("outcome") not in en["outcome"]:
            out.append(_f("error", "spec_enum", ptr, f"outcome {s.get('outcome')!r} not in the OpenAPI enum"))
        if s.get("queue") and en.get("queue") and s["queue"] not in en["queue"]:
            out.append(_f("error", "spec_enum", ptr, f"queue {s['queue']!r} not in the OpenAPI enum"))
        if s.get("note_reason") and en.get("note_reason") and s["note_reason"] not in en["note_reason"]:
            out.append(_f("error", "spec_enum", ptr,
                          f"note_reason {s['note_reason']!r} not in the OpenAPI enum"))
        if s.get("reason") and en.get("close_reason") and s["reason"] not in en["close_reason"]:
            out.append(_f("error", "spec_enum", ptr, f"reason {s['reason']!r} not in the OpenAPI enum"))
        if s.get("outcome") in reasonless and s.get("reason"):
            out.append(_f("error", "reasonless_reason", ptr,
                          f"outcome {s['outcome']} is reasonless but a reason is set"))
    for i, it in enumerate(spec.get("intents") or []):
        q = (it.get("action") or {}).get("queue")
        if q and en.get("queue") and q not in en["queue"]:
            out.append(_f("error", "spec_enum", "/intents/%d/action/queue" % i, f"queue {q!r} not in the OpenAPI enum"))
    idn = spec.get("identity") or {}
    if catalog.get("identity_mode") == "selector":
        for i, q in enumerate(idn.get("questions") or []):
            if q.get("field_value") not in (en.get("identity_field") or []):
                out.append(_f("error", "spec_enum", "/identity/questions/%d/field_value" % i,
                              f"{q.get('field_value')!r} not in the OpenAPI enum"))
    else:
        req = (catalog["tools"]["verify_identity"]["request"])
        for i, q in enumerate(idn.get("questions") or []):
            if q.get("field_value") not in req:
                out.append(_f("error", "spec_enum", "/identity/questions/%d/field_value" % i,
                              f"{q.get('field_value')!r} is not a request field of the identity tool"))
    for i, h in enumerate(idn.get("hints") or []):
        if h.get("value") not in (en.get("hint") or []):
            out.append(_f("error", "spec_enum", "/identity/hints/%d/value" % i, f"{h.get('value')!r} not in the OpenAPI enum"))
    types = set(((spec.get("products") or {}).get("types") or {}).keys())
    if en.get("product_type") and types - set(en["product_type"]):
        out.append(_f("error", "spec_enum", "/products/types", f"types {sorted(types - set(en['product_type']))} not in the OpenAPI enum"))
    if en.get("product_type") and set(en["product_type"]) - types:
        out.append(_f("warn", "spec_enum", "/products/types", f"OpenAPI types without a Spec entry: {sorted(set(en['product_type']) - types)}"))


def _lint_required_sentences(spec, wiring_, out):
    sits = set((spec.get("situations") or {}).keys())
    ids = {it.get("id") for it in spec.get("intents") or []}
    outcomes = {(s or {}).get("outcome") for s in (spec.get("situations") or {}).values()}
    trig_re = re.compile(vocab.TRIGGER_RE)
    for i, rs in enumerate(spec.get("required_sentences") or []):
        ptr = "/required_sentences/%d" % i
        trig = str(rs.get("trigger") or "")
        if not str(rs.get("text") or "").strip():
            out.append(_f("error", "required_sentence", ptr, "empty text"))
        if not trig_re.match(trig):
            out.append(_f("error", "required_sentence", ptr, f"unknown trigger {trig!r}"))
            continue
        if trig.startswith("on_situation:") and trig.split(":", 1)[1] not in sits:
            out.append(_f("error", "required_sentence", ptr, f"trigger situation {trig} is not defined"))
        if trig.startswith("on_intent:") and trig.split(":", 1)[1] not in ids:
            out.append(_f("error", "required_sentence", ptr, f"trigger intent {trig} is not defined"))
        if trig.startswith("on_outcome:") and trig.split(":", 1)[1] not in outcomes:
            out.append(_f("error", "required_sentence", ptr, f"no situation produces outcome {trig}"))
        if trig == "after_promise_recorded" and not (wiring_.get("api") or {}).get("promise"):
            out.append(_f("error", "required_sentence", ptr, "no promise node: the trigger can never fire"))
        for prob in render.check_placeholders(rs.get("text") or "", spec):
            out.append(_f("error", "required_sentence", ptr, prob))


def _lint_reach(wf, wiring_, out):
    nodes = wf.get("nodes") or {}
    start = wf.get("initial_node")
    edges = {}
    for k, n in nodes.items():
        tg = [tr.get("target_node") for tr in n.get("transitions") or []]
        for fld in ("passthrough_default_transition", "max_turn_transition"):
            if n.get(fld):
                tg.append(n[fld])
        edges[k] = [t for t in tg if t in nodes]
    seen, stack = set(), [start] if start in nodes else []
    while stack:
        k = stack.pop()
        if k in seen:
            continue
        seen.add(k)
        stack += edges.get(k, [])
    for k in nodes:
        if k not in seen:
            out.append(_f("error" if nodes[k].get("node_type") == "end_call" else "warn", "reach", k,
                          "node is unreachable from the initial node"))
    # structural sources per spoke (C.6 tool reachability, mirrored)
    incoming = {k: set() for k in nodes}
    for k, n in nodes.items():
        for tr in n.get("transitions") or []:
            t = tr.get("target_node")
            if t in incoming:
                incoming[t].add(k)
    api = wiring_.get("api") or {}
    chainable = set(wiring_.get("chainable") or [])
    bye = wiring_.get("bye") or ""
    allowed = {}
    vsrc = set(api.get("verify") or []) if (wiring_.get("vchain") or {}).get("t") else set()
    for k in api.get("verify") or []:
        allowed[k] = {vocab.CTL_NODE}
    for k in api.get("acct") or []:
        allowed[k] = {vocab.CTL_NODE} | vsrc               # identity chain: all verified -> account read
    for k in list(api.get("cb") or []) + list(api.get("xfer") or []):
        allowed[k] = {vocab.CTL_NODE} | chainable
    for row in (api.get("promise") or []) + (api.get("note") or []):
        for k in row:
            allowed[k] = {vocab.CTL_NODE} | chainable
    for k in api.get("note_call") or []:
        allowed[k] = {vocab.CTL_NODE} | chainable
    for k in (api.get("close_r"), api.get("close_n")):
        if k:
            allowed[k] = {vocab.CTL_NODE, bye} | chainable
    for k, srcs in allowed.items():
        bad = sorted(incoming.get(k, set()) - srcs)
        if bad:
            out.append(_f("error", "reach_source", k, f"entered from unexpected nodes {bad}"))
    for k in api.get("cb") or []:
        for src in incoming.get(k, set()):
            if src in chainable and (wiring_.get("nodes") or {}).get(src, {}).get("tool") != "schedule_callback":
                out.append(_f("error", "reach_source", k, f"callback chained from {src}"))


def _pt_edges(nodes):
    """Edges between silent passthrough nodes (ctl excluded): the walk one ctl decision sets off."""
    pt = {k for k, n in nodes.items() if k != vocab.CTL_NODE and n.get("passthrough")}
    edges = {}
    for k in pt:
        n = nodes[k]
        tg = [tr.get("target_node") for tr in n.get("transitions") or []] + [n.get("passthrough_default_transition")]
        edges[k] = sorted({t for t in tg if t in pt})
    return edges


def _pt_cycle(nodes, edges):
    """-> a node on a passthrough cycle that no api node's pending guard breaks, else None."""
    free = {k: [t for t in v if nodes[t].get("node_type") != "api_request"] for k, v in edges.items()}
    state = {}

    def cyc(k):
        state[k] = 1
        for t in free[k]:
            if state.get(t) == 1 or (t not in state and cyc(t)):
                return True
        state[k] = 2
        return False
    for k in sorted(free):
        if k not in state and cyc(k):
            return k
    return None


def _walk_size(edges, start):
    """Number of passthrough nodes reachable from `start` (0 when it is not a passthrough node)."""
    seen, stack = set(), [start] if start in edges else []
    while stack:
        k = stack.pop()
        if k not in seen:
            seen.add(k)
            stack += edges[k]
    return len(seen)


def _lint_hops(wf, out):
    """hop_bound: every walk that one ctl decision sets off must end, within HOP_BOUND node entries.
    An edge into an api node carries the pending guard (entry_guard), so each api node runs at most once per walk;
    a cycle through any other edge could spin until the platform's hop limit. Bound per ctl target = ctl + the
    passthrough nodes reachable from that target + the node that ends the walk."""
    nodes = wf.get("nodes") or {}
    edges = _pt_edges(nodes)
    k = _pt_cycle(nodes, edges)
    if k is not None:
        out.append(_f("error", "hop_bound", k, "unguarded passthrough cycle: the walk may never stop"))
        return
    worst, at = 0, ""
    for tr in (nodes.get(vocab.CTL_NODE) or {}).get("transitions") or []:
        t = tr.get("target_node")
        n = _walk_size(edges, t) + 2
        if n > worst:
            worst, at = n, t
    if worst > HOP_BOUND:
        out.append(_f("error", "hop_bound", at, f"one ctl decision can take {worst} hops (> {HOP_BOUND})"))


def _lint_stable(wf, catalog, spec, wiring_, out):
    code = _code_of((wf.get("nodes") or {}).get(vocab.CTL_NODE) or {})
    if code is None:
        return
    try:
        a, wa = graph.compile_workflow(spec, catalog, wiring_.get("flags"), code=code)
        b, wb = graph.compile_workflow(spec, catalog, wiring_.get("flags"), code=code)
    except Exception as e:
        out.append(_f("error", "byte_stable", "workflow", f"recompile failed: {e}"))
        return
    if graph.dumps(a) != graph.dumps(b) or graph.dumps(wa) != graph.dumps(wb):
        out.append(_f("error", "byte_stable", "workflow", "two compiles of the same input differ"))
    elif graph.dumps(a) != graph.dumps(wf):
        out.append(_f("warn", "byte_stable", "workflow", "workflow differs from a fresh compile of the same Spec"))


# ------------------------------------------------------------------------------------------------ entry point

def lint(workflow, catalog, spec, wiring_, stable=True):
    """-> list of {"level": "error"|"warn", "rule": str, "where": str, "msg": str}. Empty errors = shippable."""
    out = []
    try:
        _lint_top(workflow, out)
        _lint_structure(workflow, out)
        _lint_code(workflow, out)
        _lint_api(workflow, catalog, wiring_, spec, out)
        _lint_guards(workflow, wiring_, out)
        _lint_vars(workflow, wiring_, spec, out)
        _lint_text(workflow, spec, out)
        _lint_spec_enums(spec, catalog, out)
        _lint_required_sentences(spec, wiring_, out)
        _lint_spec_lines(spec, out)
        _lint_reach(workflow, wiring_, out)
        _lint_hops(workflow, out)
        if stable:
            _lint_stable(workflow, catalog, spec, wiring_, out)
    except Exception as e:                          # a lint crash is itself an error, never an exception
        out.append(_f("error", "lint_crash", "lint", f"{type(e).__name__}: {e}"))
    from builder import trace                           # trace.event never raises
    errs = errors(out)
    trace.event("LINT", f"{len(errs)} errors, {len(out) - len(errs)} warnings", where="LOCAL",
                mod="builder.compiler.lint.lint")
    for f in out:
        trace.event("ERROR" if f["level"] == "error" else "WARN", f"[{f['rule']}] {f['where']}: {f['msg']}",
                    mod="builder.compiler.lint.lint")
    return out
