"""Service contract -> ToolCatalog whose tools call OUR bank mock (final format). Owner: contract workstream.

The bank's services come from the case folder's SERVICE CONTRACT: an OpenAPI document (JSON/YAML), or a Word / PDF /
Markdown description (endpoint tables, field lists, enums, error codes). The tools must call our mock at mock_url.

CONTRACT NOTE (how other workstreams call this module):
- build_catalog(case, mock_url, run_dir=None, *, budget=None, fetch=None, use_llm=True) -> ToolCatalog
    case: a CaseDocs dict from builder.ingest.load_case, a case folder / .zip / file path, or a list of
    {"name", "text"} docs. Source of the OpenAPI, in order: an OpenAPI document in the case folder,
    else GET <mock_url>/openapi.json (fetch=False disables it), else ONE structured LLM call (prompt
    builder/prompts/contract.md) that turns the contract docs into an operation list, checked by code against the
    contract text (paths, field names, enum values copied exactly) and converted into OpenAPI 3.
    The result is the same ToolCatalog as builder.openapi_model (D.1) plus:
      catalog["contract"] = {source, op_map {tool: "METHOD /path"}, absent [tools], extra_operations ["METHOD /path"],
                             identity_design, synthetic_fields [...], openapi_path, notes [...]}
      tools[t]["absent"] = True for a role the contract has no operation for (a stub on OUR mock, path
      /_freya/<tool>, answering {"ok": true}); tools[t]["item_extras"] = {floor|total|due_date|limit: item leaf}.
    Raises openapi_model.CatalogError when no usable contract exists or a core service (identity check, account
    read, promise) cannot be bound.
- derive_openapi(case, run_dir, *, budget=None, mock_url=None, fetch=False) -> path | None: build.py's hook; runs
    build_catalog and returns run_dir/openapi.json, annotated (x-freya-tool / x-freya-role / stubs) so that
    openapi_model.load(path) binds every tool even when the bank renamed them; run_dir/contract.json = the report.
- derive_openapi_doc(contract_docs, *, budget=None) -> OpenAPI dict (the LLM path alone).
- map_operations(doc, *, budget=None, use_llm=True) -> (op_map, report): operation -> tool role, by exact name,
    x-freya-tool, multilingual name/description words (English + Turkish), and an LLM tie-break when ambiguous.
- normalize_for_mock(doc) -> (doc, changes): every operation becomes POST + JSON body (path/query parameters
    folded into the body, {param} segments dropped from the path), because the engine's api nodes send a JSON body
    to a literal URL. The derived OpenAPI (run_dir/openapi.json) is what OUR mock must implement.
- CLI: python -m builder.contract <case_folder> <mock_url> [--out openapi.json] [--no-llm] [--no-fetch]
    writes the derived OpenAPI (for deploying the mock before the build) and prints the role map.

Generic only: role words are banking / call-centre vocabulary in English and Turkish; nothing of a specific case.
"""
import copy
import hashlib
import json
import pathlib
import re
import sys

from builder import openapi_model as OM
from builder.openapi_model import CatalogError, fold
from builder.spec import vocab

PROMPT_PATH = pathlib.Path(__file__).resolve().parent / "prompts" / "contract.md"
CORE_TOOLS = ("verify_identity", "get_account", "create_promise")
OPTIONAL_TOOLS = ("add_note", "schedule_callback", "transfer_to_agent", "close_call")
STUB_PREFIX = "/_freya/"
METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
MAX_CONTRACT_CHARS = 150_000

# Operation role words (ASCII-folded, matched as word prefixes; short words match whole words only).
ROLE_WORDS = {
    "verify_identity": ["verify", "verification", "identity", "authenticate", "authentication", "auth", "identify",
                        "kimlik", "dogrula", "teyit", "kimlik_dogrulama"],
    "get_account": ["account", "accounts", "balance", "debt", "debts", "statement", "summary", "products", "arrears",
                    "hesap", "hesab", "borc", "bakiye", "ekstre", "ozet", "urunler", "sorgu", "bilgi", "detay"],
    "create_promise": ["promise", "ptp", "commitment", "commit", "pledge", "arrangement",
                       "soz", "sozu", "taahhut", "taahhud", "odeme_sozu", "odeme_taahhut"],
    "add_note": ["note", "notes", "comment", "memo", "annotate", "not", "notu", "aciklama", "yorum"],
    "schedule_callback": ["callback", "call_back", "recall", "appointment", "geri_arama", "geri_ara", "randevu",
                          "tekrar_ara", "arama_planla"],
    "transfer_to_agent": ["transfer", "handoff", "hand_off", "escalate", "escalation", "agent", "human", "operator",
                          "aktar", "aktarim", "yonlendir", "temsilci", "devret", "baglan"],
    "close_call": ["close", "end", "wrap", "wrapup", "disposition", "finish", "hangup", "terminate",
                   "kapat", "kapanis", "sonlandir", "bitir", "sonuc"],
}
# Two-word phrases matched on the folded text with spaces/underscores (descriptions).
_SHORT_EXACT = 4                                         # words shorter than this match whole tokens only


def _log(kind, msg, **fields):
    from builder import trace
    fields.setdefault("mod", "builder.contract." + sys._getframe(1).f_code.co_name)
    trace.event(kind, msg, **fields)


# ----------------------------------------------------------------------------------------------------------------
# Case input

def _coerce_case(case, mock_url=None):
    """CaseDocs | path | [{"name","text"}] -> {"docs", "contract_docs", "openapi", "openapi_path"}."""
    if isinstance(case, dict) and "docs" in case:
        return case
    if isinstance(case, (str, pathlib.Path)):
        from builder import ingest
        return ingest.load_case(str(case), mock_url=mock_url)
    docs = []
    for d in case or []:
        if isinstance(d, dict):
            docs.append({"name": str(d.get("name") or d.get("rel") or "doc"), "rel": str(d.get("rel") or d.get("name") or "doc"),
                         "text": str(d.get("text") or ""), "kind": d.get("kind") or "",
                         "is_openapi": bool(d.get("is_openapi"))})
    oa, oa_path = None, None
    for d in docs:
        doc = _openapi_in_text(d["text"])
        if doc is not None:
            oa, oa_path = doc, d["rel"]
            break
    contract = [d for d in docs if d.get("kind") == "service_contract"] or [d for d in docs if _contractish(d)]
    return {"docs": docs, "contract_docs": contract, "openapi": oa, "openapi_path": oa_path, "mock_url": mock_url}


_FENCE = "```"
_FENCE_LANGS = ("json", "yaml", "yml")
_JSON_CT = "application/json"
_OPENAPI_JSON = "openapi.json"


def _fenced_blocks(text):
    """The bodies of ```json / ```yaml / ```yml / bare ``` fenced blocks, in order; a linear form of
    re.findall(r"```(?:json|yaml|yml)?\\s*\\n(.*?)```", text, re.S), whose lazy body backtracked."""
    text = text or ""
    out = []
    i, nl, tail = text.find(_FENCE), -1, -1
    while i >= 0:
        if nl < i + 3:
            nl = text.find("\n", i + 3)                 # reused by every opener before it (keeps the scan linear)
            if nl < 0:
                break
            tail = nl                                   # start of the whitespace that ends the line
            while tail > i + 3 and text[tail - 1].isspace():
                tail -= 1
        lang = next((w for w in _FENCE_LANGS if text.startswith(w, i + 3)), "")
        end = text.find(_FENCE, nl + 1) if tail <= i + 3 + len(lang) else -2
        if end == -1:
            break
        if end >= 0:
            out.append(text[nl + 1:end])
            i = text.find(_FENCE, end + 3)
        else:
            i = text.find(_FENCE, i + 1)
    return out


def _openapi_in_text(text):
    """An OpenAPI document as the whole text, or inside a fenced ```json / ```yaml block."""
    cands = [text] + _fenced_blocks(text)
    for c in cands:
        if not re.search(r"(?i)[\"']?\b(openapi|swagger)[\"']?\s*:", c or ""):
            continue
        doc = OM._parse_text(c)
        if isinstance(doc, dict) and ("openapi" in doc or "swagger" in doc) and isinstance(doc.get("paths"), dict):
            return doc
    return None


_CONTRACT_NAME_WORDS = ("contract", "service", "api", "endpoint", "integration", "interface", "sozlesme", "servis",
                        "hizmet", "entegrasyon", "arayuz", "uc_nokta", "web_servis")


def _contractish(doc):
    name = fold(doc.get("name") or doc.get("rel") or "")
    name = re.sub(r"[^a-z0-9]+", "_", name)
    if any(w in name for w in _CONTRACT_NAME_WORDS):
        return True
    text = doc.get("text") or ""
    return len(re.findall(r"\b(GET|POST|PUT|PATCH|DELETE)\s+/", text)) >= 2


# ----------------------------------------------------------------------------------------------------------------
# Contract text checks (code, not the model)

_PATH_RX = r"/[A-Za-z0-9_\-{}.]+(?:/[A-Za-z0-9_\-{}.]+)*/?"


def mentioned_paths(text):
    """Paths the contract text names: after an HTTP method, in `backticks`, or alone in a table cell."""
    text = text or ""
    found = []
    pats = [r"\b(?:GET|POST|PUT|PATCH|DELETE)\b[\s`*|:]*(" + _PATH_RX + ")",
            r"`(" + _PATH_RX + r")`",
            r"\|\s*(" + _PATH_RX + r")\s*(?=\|)"]
    for rx in pats:
        for m in re.finditer(rx, text):
            p = m.group(1).rstrip("/.") or "/"
            if re.fullmatch(r"/\d+(/\d+)*", p) or p.count("/") == 0:
                continue
            if p not in found:
                found.append(p)
    return found


def mentioned_identifiers(text):
    """Field-like identifiers in `backticks` (snake_case or camelCase): what the contract names as fields."""
    out = []
    for m in re.finditer(r"`([A-Za-z_][A-Za-z0-9_.]*)`", text or ""):
        tok = m.group(1)
        if ("_" in tok or re.search(r"[a-z][A-Z]", tok)) and tok not in out:
            out.append(tok)
    return out


def _same_path(a, b):
    na = re.sub(r"\{[^}]*\}", "{}", a.rstrip("/").lower())
    nb = re.sub(r"\{[^}]*\}", "{}", b.rstrip("/").lower())
    return na == nb or na.endswith(nb) or nb.endswith(na)


def check_operations(model, text):
    """Hard errors (fed back to the model) and soft warnings for an operation list against the contract text."""
    errors, warnings = [], []
    ops = model.get("operations") or []
    if not ops:
        errors.append("/operations: empty; the contract describes at least one operation")
    seen = set()
    names = set()
    for i, op in enumerate(ops):
        p = "/operations/%d" % i
        path = str(op.get("path") or "")
        if not path.startswith("/"):
            errors.append("%s/path: %r must start with '/'" % (p, path))
        key = (str(op.get("method") or "POST").upper(), path.rstrip("/"))
        if key in seen:
            errors.append("%s: duplicate operation %s %s" % (p, key[0], path))
        seen.add(key)
        names.add(str(op.get("name") or ""))
        for side in ("request", "response"):
            for j, f in enumerate(op.get(side) or []):
                fp = "%s/%s/%d" % (p, side, j)
                for leaf, lp in [(f, fp)] + [(c, fp + "/items/%d" % k) for k, c in enumerate(f.get("items") or [])] \
                        + [(c, fp + "/fields/%d" % k) for k, c in enumerate(f.get("fields") or [])]:
                    nm = str(leaf.get("name") or "")
                    names.add(nm)
                    if not nm:
                        errors.append("%s/name: empty" % lp)
                    elif nm not in text:
                        errors.append("%s/name: %r is not written in the contract; copy field names exactly" % (lp, nm))
                    for v in leaf.get("enum") or []:
                        names.add(str(v))
                        if str(v) not in text:
                            errors.append("%s/enum: %r is not written in the contract; copy enum values exactly"
                                          % (lp, v))
        succ = op.get("success") or {}
        for v in succ.get("values") or []:
            if str(v) not in text and str(v).lower() not in ("true", "false"):
                errors.append("%s/success/values: %r is not written in the contract" % (p, v))
    op_paths = [str(op.get("path") or "") for op in ops]
    for mp in mentioned_paths(text):
        if not any(_same_path(mp, op) for op in op_paths):
            errors.append("/operations: the contract names the path %r but no operation has it" % mp)
    for ident in mentioned_identifiers(text):
        if ident not in names and not any(ident in p for p in op_paths) and ident.split(".")[-1] not in names:
            warnings.append("contract names %r but no operation field / enum carries it" % ident)
    return errors, warnings


# ----------------------------------------------------------------------------------------------------------------
# LLM derivation (one structured call)

_ALL_ROLES = [""] + list(vocab.REQUEST_ROLES) + [r for r in vocab.RESPONSE_ROLES if r not in vocab.REQUEST_ROLES] \
    + [r for r in vocab.ITEM_ROLES if r not in vocab.REQUEST_ROLES and r not in vocab.RESPONSE_ROLES]
_TYPES = ["string", "number", "integer", "boolean", "array", "object"]


def _leaf_schema(nested):
    props = {
        "name": {"type": "string"},
        "type": {"type": "string", "enum": _TYPES},
        "required": {"type": "boolean"},
        "enum": {"type": "array", "items": {"type": "string"}},
        "format": {"type": "string"},
        "description": {"type": "string"},
        "role": {"type": "string", "enum": _ALL_ROLES},
    }
    if nested:
        props["items"] = {"type": "array", "items": _leaf_schema(False)}
        props["fields"] = {"type": "array", "items": _leaf_schema(False)}
    return {"type": "object", "required": ["name", "type"], "properties": props}


OPS_SCHEMA = {
    "type": "object",
    "required": ["operations"],
    "properties": {
        "operations": {"type": "array", "items": {
            "type": "object",
            "required": ["name", "method", "path", "tool", "request", "response"],
            "properties": {
                "name": {"type": "string"},
                "method": {"type": "string", "enum": list(METHODS)},
                "path": {"type": "string"},
                "summary": {"type": "string"},
                "tool": {"type": "string", "enum": list(vocab.TOOLS) + ["other"]},
                "request": {"type": "array", "items": _leaf_schema(True)},
                "response": {"type": "array", "items": _leaf_schema(True)},
                "success": {"type": "object", "properties": {"field": {"type": "string"},
                                                             "values": {"type": "array", "items": {"type": "string"}}}},
                "errors": {"type": "array", "items": {"type": "object", "properties": {
                    "code": {"type": "string"}, "meaning": {"type": "string"}}}},
            }}},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
}


def contract_text(docs):
    parts = []
    for d in docs:
        parts.append("=== %s ===\n%s" % (d.get("rel") or d.get("name") or "document", (d.get("text") or "").strip()))
    return "\n\n".join(parts)[:MAX_CONTRACT_CHARS]


def derive_operations(docs, *, budget=None, timeout_s=420):
    """ONE structured LLM call (repaired by builder.llm when check_operations finds hard errors) -> operation list."""
    from builder import llm
    text = contract_text(docs)
    if not any((d.get("text") or "").strip() for d in docs):
        raise CatalogError("no service contract text to derive the tool API from")
    system = PROMPT_PATH.read_text()
    prompt = "Service contract documents:\n\n" + text
    model, effort = llm.choice("contract")

    def validate(obj):
        return check_operations(obj, text)[0]

    out = llm.call_json("contract", system, prompt, OPS_SCHEMA, timeout_s=timeout_s, effort=effort, model=model,
                        budget=budget, validate=validate)
    _, warns = check_operations(out, text)
    for w in warns:
        _log("WARN", w)
    return out


def _schema_of(leaf, side):
    t = leaf.get("type") or "string"
    sch = {"type": t}
    if leaf.get("enum"):
        sch["enum"] = [str(v) for v in leaf["enum"]]
    if leaf.get("format"):
        sch["format"] = str(leaf["format"])
    if leaf.get("description"):
        sch["description"] = str(leaf["description"])
    role = leaf.get("role") or ""
    allowed = {"request": vocab.REQUEST_ROLES, "response": vocab.RESPONSE_ROLES, "item": vocab.ITEM_ROLES}[side]
    if role in allowed:
        sch["x-freya-role"] = role
    if t == "array" and leaf.get("items"):
        sch["items"] = _object_of(leaf["items"], "item")
    elif t == "object" and leaf.get("fields"):
        sch.update(_object_of(leaf["fields"], side))
    return sch


def _object_of(leaves, side):
    props, req = {}, []
    for leaf in leaves or []:
        nm = str(leaf.get("name") or "")
        if not nm:
            continue
        props[nm] = _schema_of(leaf, side)
        if leaf.get("required"):
            req.append(nm)
    out = {"type": "object", "properties": props}
    if req:
        out["required"] = req
    return out


def operations_to_openapi(model, title="Service contract"):
    """Operation list (OPS_SCHEMA) -> OpenAPI 3 dict (x-freya-tool / x-freya-role / x-freya-success annotations)."""
    paths = {}
    for op in model.get("operations") or []:
        path = "/" + str(op.get("path") or op.get("name") or "op").lstrip("/")
        method = str(op.get("method") or "POST").lower()
        body = _object_of(op.get("request") or [], "request")
        res = _object_of(op.get("response") or [], "response")
        succ = op.get("success") or {}
        sf = str(succ.get("field") or "")
        if sf and sf in res["properties"] and succ.get("values"):
            res["properties"][sf]["x-freya-success"] = [str(v) for v in succ["values"]]
            res["properties"][sf].setdefault("x-freya-role", "s")
        entry = {"operationId": str(op.get("name") or path.strip("/").replace("/", "_")),
                 "summary": str(op.get("summary") or ""),
                 "requestBody": {"required": True, "content": {_JSON_CT: {"schema": body}}},
                 "responses": {"200": {"description": "success",
                                       "content": {_JSON_CT: {"schema": res}}}}}
        if op.get("tool") in vocab.TOOLS:
            entry["x-freya-tool-hint"] = op["tool"]
        if op.get("errors"):
            entry["x-freya-errors"] = [{"code": str(e.get("code") or ""), "meaning": str(e.get("meaning") or "")}
                                       for e in op["errors"]]
        paths.setdefault(path, {})[method] = entry
    return {"openapi": "3.0.3", "info": {"title": title, "version": "derived"}, "paths": paths,
            "x-freya-notes": [str(n) for n in model.get("notes") or []]}


_DERIVED = {}                    # (build budget id, contract text sha256) -> derived OpenAPI: one LLM call per build


def derive_openapi_doc(contract_docs, *, budget=None):
    """The LLM path alone; within one build (same budget object) the same contract text is derived once."""
    if budget is None:
        return operations_to_openapi(derive_operations(contract_docs, budget=budget))
    key = (id(budget), hashlib.sha256(contract_text(contract_docs).encode("utf-8")).hexdigest())
    if key not in _DERIVED:
        _DERIVED[key] = operations_to_openapi(derive_operations(contract_docs, budget=budget))
    return copy.deepcopy(_DERIVED[key])


def derive_openapi(case, run_dir=None, *, budget=None, mock_url=None, fetch=False):
    """build.py hook: the whole contract stage -> path of run_dir/openapi.json (servers = mock, every operation
    annotated with x-freya-tool, stubs for absent services, synthetic fields), loadable by openapi_model.load; the
    contract report goes to run_dir/contract.json. None (logged) when no catalog can be built."""
    import tempfile
    run_dir = pathlib.Path(run_dir or tempfile.mkdtemp(prefix="contract_"))
    if mock_url is None and isinstance(case, dict):
        mock_url = case.get("mock_url")
    try:
        cat = build_catalog(case, mock_url, run_dir, budget=budget, fetch=fetch)
    except Exception as e:                                  # noqa: BLE001 - the caller reports "gave nothing"
        _log("ERROR", "contract stage failed: %s" % str(e)[:300])
        return None
    (run_dir / "contract.json").write_text(json.dumps(cat["contract"], indent=1, ensure_ascii=False) + "\n")
    return cat["contract"]["openapi_path"]


# ----------------------------------------------------------------------------------------------------------------
# Normalisation for our mock (POST + JSON body, literal URL)

def normalize_for_mock(doc):
    """-> (doc copy, [change strings]). GET/DELETE or parameterised operations become POST with every parameter in
    the JSON body; '{param}' path segments are dropped (collisions get the method appended)."""
    doc = copy.deepcopy(doc)
    changes = []
    new_paths = {}
    for path in sorted(doc.get("paths") or {}, key=str):
        item = doc["paths"][path] or {}
        shared = [OM._resolve(doc, p) if isinstance(p, dict) and "$ref" in p else p
                  for p in (item.get("parameters") or [])] if isinstance(item, dict) else []
        for method in [m for m in OM.HTTP_METHODS if isinstance(item, dict) and isinstance(item.get(m), dict)]:
            op = copy.deepcopy(item[method])
            params = shared + [OM._resolve(doc, p) if isinstance(p, dict) and "$ref" in p else p
                               for p in (op.get("parameters") or [])]
            params = [p for p in params if isinstance(p, dict) and p.get("in") in ("path", "query")]
            literal = re.sub(r"/\{[^}]*\}", "", path) or "/"
            if method == "post" and not params and literal == path:
                new_paths.setdefault(path, {})[method] = op
                continue
            body = OM._json_schema(doc, op.get("requestBody") or {}) if op.get("requestBody") else {}
            body = {"type": "object", "properties": dict(body.get("properties") or {}),
                    "required": list(body.get("required") or [])}
            for prm in params:
                nm = str(prm.get("name") or "")
                if not nm or nm in body["properties"]:
                    continue
                sch = dict(OM._resolve(doc, prm.get("schema") or {}) or {"type": "string"})
                if prm.get("description") and "description" not in sch:
                    sch["description"] = prm["description"]
                body["properties"][nm] = sch
                if prm.get("required") or prm.get("in") == "path":
                    body["required"].append(nm)
            if not body["required"]:
                body.pop("required")
            op.pop("parameters", None)
            op["requestBody"] = {"required": True, "content": {_JSON_CT: {"schema": body}}}
            op["x-freya-original"] = {"method": method.upper(), "path": path}
            target = literal
            if target in new_paths and "post" in new_paths[target]:
                target = literal.rstrip("/") + "_" + method
            new_paths.setdefault(target, {})["post"] = op
            changes.append("%s %s -> POST %s (parameters in the JSON body)" % (method.upper(), path, target))
    doc["paths"] = new_paths
    return doc, changes


# ----------------------------------------------------------------------------------------------------------------
# Operation -> tool role

def _tokens(text):
    t = fold(re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(text or "")))
    return [w for w in re.split(r"[^a-z0-9]+", t) if w]


def _word_hits(tokens, words):
    joined = "_" + "_".join(tokens) + "_"
    n = 0
    for w in words:
        if "_" in w:
            if "_" + w in joined:
                n += 1
        elif len(w) < _SHORT_EXACT:
            n += sum(1 for t in tokens if t == w)
        else:
            n += sum(1 for t in tokens if t.startswith(w))
    return n


def op_scores(path, op):
    """-> {tool: score} from the operation's id / last path segment (x3), other path segments (x1), summary and
    description (x1)."""
    segs = [s for s in path.strip("/").split("/") if s and not s.startswith("{")]
    last = segs[-1] if segs else ""
    strong = _tokens(op.get("operationId") or "") + _tokens(last)
    weak = _tokens(" ".join(segs[:-1]))
    text = _tokens(" ".join(str(op.get(k) or "") for k in ("summary", "description")))
    out = {}
    for tool, words in ROLE_WORDS.items():
        sc = 3 * _word_hits(strong, words) + _word_hits(weak, words) + _word_hits(text, words)
        if op.get("x-freya-tool-hint") == tool:
            sc += 4
        if sc:
            out[tool] = sc
    return out


def _all_ops(doc):
    out = []
    for path in sorted(doc.get("paths") or {}, key=str):
        item = doc["paths"][path] or {}
        for method in OM.HTTP_METHODS:
            if isinstance(item, dict) and isinstance(item.get(method), dict):
                out.append(("%s %s" % (method.upper(), path), path, method, item[method]))
    return out


def map_operations(doc, *, budget=None, use_llm=True):
    """-> (op_map {tool: "METHOD /path"}, report {decisions, extra, ambiguous, verify_ops}).

    Order: x-freya-tool, exact tool name (operationId / last path segment), then role words with a unique best
    operation per tool (an operation serves one tool). Ties / unassigned scored operations go to one LLM tie-break
    when allowed, validated (only offered candidates, one operation per tool); else the deterministic best."""
    ops = _all_ops(doc)
    op_map, used, decisions = {}, set(), []

    def take(tool, key, why):
        op_map[tool] = key
        used.add(key)
        decisions.append("%s -> %s (%s)" % (tool, key, why))

    for key, path, method, op in ops:
        t = op.get("x-freya-tool")
        if t in vocab.TOOLS and t not in op_map and key not in used:
            take(t, key, "x-freya-tool")
    for key, path, method, op in ops:
        for c in (str(op.get("operationId") or ""), path.rstrip("/").rsplit("/", 1)[-1]):
            if c in vocab.TOOLS and c not in op_map and key not in used:
                take(c, key, "exact name")
                break
    scores = {key: op_scores(path, op) for key, path, _method, op in ops}
    verify_ops = [k for k, s in scores.items() if s and max(s, key=s.get) == "verify_identity"]
    ambiguous = []
    for _round in range(len(vocab.TOOLS)):
        best = []
        for tool in vocab.TOOLS:
            if tool in op_map:
                continue
            cands = sorted(((s.get(tool, 0), k) for k, s in scores.items() if k not in used and s.get(tool, 0) > 0),
                           reverse=True)
            if cands:
                best.append((cands[0][0], tool, cands[0][1], cands))
        if not best:
            break
        best.sort(key=lambda b: (-b[0], vocab.TOOLS.index(b[1])))
        sc, tool, key, cands = best[0]
        own = scores[key]
        rival_tool = max((v for t, v in own.items() if t != tool and t not in op_map), default=0)
        rival_op = cands[1][0] if len(cands) > 1 else 0
        if sc <= rival_tool or sc <= rival_op:
            ambiguous.append({"tool": tool, "candidates": [k for _, k in cands[:4]]})
        take(tool, key, "role words (score %d)" % sc)
    extra = [k for k, *_ in ops if k not in used]
    if use_llm and (ambiguous or [k for k in extra if scores.get(k)]):
        llm_map = _llm_tiebreak(doc, ops, op_map, budget)
        if llm_map:
            for tool, key in llm_map.items():
                if op_map.get(tool) != key:
                    decisions.append("%s -> %s (LLM tie-break, was %s)" % (tool, key, op_map.get(tool) or "none"))
            op_map = {t: k for t, k in llm_map.items() if k}
            used = set(op_map.values())
            extra = [k for k, *_ in ops if k not in used]
    for d in decisions:
        _log("DECISION", "tool role " + d, where="LOCAL")
    return op_map, {"decisions": decisions, "extra": extra, "ambiguous": ambiguous, "verify_ops": verify_ops}


TIEBREAK_SCHEMA = {
    "type": "object", "required": ["map"],
    "properties": {"map": {"type": "array", "items": {
        "type": "object", "required": ["tool", "operation"],
        "properties": {"tool": {"type": "string", "enum": list(vocab.TOOLS)},
                       "operation": {"type": "string"}}}}},
}
TIEBREAK_SYSTEM = (
    "You map a bank's web-service operations to the fixed service roles of a phone collections agent. Roles: "
    "verify_identity (checks identity answers), get_account (reads the customer's debt / products / statement), "
    "create_promise (records a promise to pay), add_note (adds a note), schedule_callback (books a call back), "
    "transfer_to_agent (hands the call to a human), close_call (records the call outcome / ends the call). "
    "Answer {\"map\": [{\"tool\", \"operation\"}]}: at most one operation per role, each operation at most once, "
    "operation copied exactly from the list (\"METHOD /path\"), \"\" when no operation plays the role.")


def _llm_tiebreak(doc, ops, current, budget):
    from builder import llm
    keys = [k for k, *_ in ops]
    lines = []
    for key, path, method, op in ops:
        body = OM._json_schema(doc, op.get("requestBody") or {})
        fields = ", ".join(sorted((body.get("properties") or {}).keys()))
        lines.append("- %s | id=%s | %s | fields: %s" % (key, op.get("operationId") or "", (op.get("summary") or
                     op.get("description") or "")[:200], fields))
    prompt = ("Operations:\n" + "\n".join(lines) + "\n\nCurrent guess (by name words): "
              + json.dumps(current, ensure_ascii=False))

    def validate(obj):
        errs, seen_t, seen_o = [], set(), set()
        for i, row in enumerate(obj.get("map") or []):
            op = row.get("operation") or ""
            if op and op not in keys:
                errs.append("/map/%d/operation: %r is not one of the listed operations" % (i, op))
            if row.get("tool") in seen_t:
                errs.append("/map/%d/tool: %s mapped twice" % (i, row.get("tool")))
            if op and op in seen_o:
                errs.append("/map/%d/operation: %s used for two roles" % (i, op))
            seen_t.add(row.get("tool"))
            seen_o.add(op)
        return errs

    try:
        model, effort = llm.choice("contract_map", effort="medium")
        out = llm.call_json("contract_map", TIEBREAK_SYSTEM, prompt, TIEBREAK_SCHEMA, timeout_s=180,
                            effort=effort, model=model, budget=budget, validate=validate)
    except Exception as e:                                  # noqa: BLE001 - deterministic mapping stays
        _log("WARN", "tool-role tie-break failed; keeping the name-word mapping", err=str(e)[:200])
        return None
    return {r["tool"]: r.get("operation") or "" for r in out.get("map") or [] if r.get("tool") in vocab.TOOLS}


# ----------------------------------------------------------------------------------------------------------------
# Stubs, synthetic fields, identity design

def _op_at(doc, key):
    method, path = key.split(" ", 1)
    return doc["paths"][path][method.lower()]


def _customer_field(doc, op_map):
    for tool in ("get_account", "verify_identity", "create_promise"):
        if tool in op_map:
            body = OM._json_schema(doc, _op_at(doc, op_map[tool]).get("requestBody") or {})
            req = {k: OM._request_leaf(k, v, False) for k, v in (body.get("properties") or {}).items()}
            f = OM._bind_request(tool, req, OM._role_hints(body.get("properties"))).get("customer")
            if f:
                return f
    return "customer_id"


STUB_FIELDS = {
    "verify_identity": [("selector", "string"), ("answer", "string")],
    "get_account": [],
    "create_promise": [("product", "string"), ("amount", "number"), ("date", "string")],
    "add_note": [("reason", "string"), ("text", "string")],
    "schedule_callback": [("date", "string"), ("time", "string")],
    "transfer_to_agent": [("queue", "string")],
    "close_call": [("outcome", "string"), ("reason", "string")],
}


def _stub_op(tool, customer):
    props = {customer: {"type": "string", "x-freya-role": "customer"}}
    for role, typ in STUB_FIELDS[tool]:
        props[role] = {"type": typ, "x-freya-role": role}
        if role == "date":
            props[role]["format"] = "date"
        if role == "time":
            props[role]["description"] = "HH:MM"
    res = {"ok": {"type": "boolean", "x-freya-role": "s"}, "error": {"type": "string", "x-freya-role": "err"}}
    if tool == "get_account":
        res["products"] = {"type": "array", "x-freya-role": "products", "items": {"type": "object", "properties": {
            "id": {"type": "string", "x-freya-role": "id"}, "past_due": {"type": "number", "x-freya-role": "past_due"}}}}
    return {"operationId": tool, "summary": "not in the service contract: stub on our mock (always ok)",
            "x-freya-tool": tool, "x-freya-absent": True,
            "requestBody": {"required": True, "content": {_JSON_CT: {"schema": {
                "type": "object", "properties": props, "required": [customer]}}}},
            "responses": {"200": {"description": "ok", "content": {_JSON_CT: {"schema": {
                "type": "object", "properties": res}}}}}}


# problem text (openapi_model._check_roles) -> request role to synthesise on a present optional tool
_PROBLEM_RX = re.compile(r"^(\w+): no request field for role ([a-z/]+)$")


def _add_synthetic_field(doc, key, role):
    op = _op_at(doc, key)
    body = op.setdefault("requestBody", {"required": True, "content": {_JSON_CT: {"schema": {}}}})
    content = body.setdefault("content", {})
    media = content.setdefault(_JSON_CT, {})
    sch = media.get("schema") or {}
    if "$ref" in sch:
        sch = OM._resolve(doc, sch)
    sch = dict(sch)
    props = dict(sch.get("properties") or {})
    name = role if role not in props else "freya_" + role
    props[name] = {"type": "string", "x-freya-role": role, "x-freya-synthetic": True,
                   "description": "not in the service contract; added for the engine (our mock ignores it)"}
    if role == "date":
        props[name]["format"] = "date"
    if role == "time":
        props[name]["description"] = "HH:MM"
    sch["properties"] = props
    sch.setdefault("type", "object")
    media["schema"] = sch
    return name


# problem text -> the account list (or its item leaves) is not described: synthesise generic item leaves
_ITEM_PROBLEM_RX = re.compile(r"^get_account: no (product item leaf for role (\w+)|response leaf for role products)$")
# generic item leaves served by our mock when the contract leaves the account list undescribed (role, name, type)
SYNTH_ITEM_LEAVES = (("id", "id", "string"), ("type", "type", "string"), ("past_due", "past_due", "number"),
                     ("days_late", "days_late", "integer"), ("floor", "minimum_due", "number"))


def _response_schema_holder(doc, op):
    """-> the (mutable) media dict of the operation's 2xx response (the one openapi_model reads), created when
    absent; a $ref'd response is inlined first."""
    responses = op.setdefault("responses", {})
    key = next((k for k in ("200", "201", "202") if k in responses), None) or \
        next((k for k in sorted(responses, key=str) if str(k).startswith("2")), None) or "200"
    resp = responses.setdefault(key, {"description": "success"})
    if not isinstance(resp, dict) or "$ref" in resp:
        resp = responses[key] = copy.deepcopy(OM._resolve(doc, resp) if isinstance(resp, dict) else {})
    content = resp.setdefault("content", {})
    if _JSON_CT not in content and content:                 # same media choice as openapi_model._json_schema
        return content[next((k for k in content if "json" in k), None) or next(iter(content))]
    return content.setdefault(_JSON_CT, {})


def _add_synthetic_items(doc, key, tool_cat):
    """get_account returns no product list, or one whose items lack id / past_due: add the generic item leaves
    (x-freya-synthetic, served by our mock) for every item role still unbound. Only called where the binding
    failed. -> ([added 'list[].leaf' strings], [binding decisions])."""
    op = _op_at(doc, key)
    media = _response_schema_holder(doc, op)
    res = OM._resolve(doc, media.get("schema") or {}) if media.get("schema") else {}
    res = copy.deepcopy(res) if isinstance(res, dict) else {}
    res.setdefault("type", "object")
    props = res.setdefault("properties", {})
    roles = (tool_cat or {}).get("roles") or {}
    list_name = (roles.get("response") or {}).get("products")
    holder = props
    if list_name and list_name not in props:                # inside one envelope object
        holder = next((v["properties"] for v in props.values() if isinstance(v, dict)
                       and isinstance(v.get("properties"), dict) and list_name in v["properties"]), props)
    added, bound = [], []
    if not list_name:                                       # one unbound array leaf: that is the product list
        arrays = [k for k, v in props.items() if isinstance(v, dict) and OM._type(OM._resolve(doc, v)) == "array"]
        if len(arrays) == 1:
            list_name = arrays[0]
            props[list_name] = dict(OM._resolve(doc, props[list_name]), **{"x-freya-role": "products"})
            bound.append(list_name + " -> response role products (the only list in the answer)")
    if not list_name or list_name not in holder:
        list_name = "products" if "products" not in props else "freya_products"
        holder = props
        holder[list_name] = {"type": "array", "x-freya-role": "products", "x-freya-synthetic": True,
                             "description": "not in the service contract; product list served by our mock"}
        added.append(list_name + " (response role products)")
    arr = holder[list_name] = dict(OM._resolve(doc, holder[list_name]) or {})
    arr["type"] = "array"
    items = OM._resolve(doc, arr.get("items") or {}) if isinstance(arr.get("items"), dict) else {}
    items = copy.deepcopy(items) if isinstance(items, dict) else {}
    items["type"] = "object"
    iprops = items.setdefault("properties", {})
    bound_roles = set(((tool_cat or {}).get("roles") or {}).get("item", {}))
    if (tool_cat or {}).get("item_extras", {}).get("floor"):
        bound_roles.add("floor")
    for role, name, typ in SYNTH_ITEM_LEAVES:
        if role in bound_roles:
            continue
        nm = name if name not in iprops else "freya_" + name
        leaf = {"type": typ, "x-freya-synthetic": True,
                "description": "not in the service contract; generic item leaf served by our mock"}
        if role in vocab.ITEM_ROLES:
            leaf["x-freya-role"] = role
        iprops[nm] = leaf
        added.append("%s[].%s (item role %s)" % (list_name, nm, role))
    arr["items"] = items
    media["schema"] = res
    return added, bound


_KEYISH = re.compile(r"(^|_)(id|key|token|session|ref|no)$|^(session|oturum|token)")


def _shared_customer_key(doc, op_map):
    """A request field present in every contract (non-stub) operation's body and id/key/session-like: the
    customer/session key the runtime bakes from the call variable (never filled by the model). None if absent."""
    keys = [k for k in op_map.values() if not k.split(" ", 1)[1].startswith(STUB_PREFIX)]
    if len(keys) < 2:
        return None
    common = None
    for k in keys:
        body = OM._json_schema(doc, _op_at(doc, k).get("requestBody") or {})
        names = set((body.get("properties") or {}))
        common = names if common is None else common & names
    cands = sorted(f for f in common or () if _KEYISH.search(OM._n(f)))
    return cands[0] if len(cands) == 1 else None


def _bind_customer_hint(doc, op_map, field):
    """x-freya-role customer on `field` in every operation's request body ($ref'd parts inlined, never shared)."""
    for key in op_map.values():
        op = _op_at(doc, key)
        rb = op.get("requestBody") or {}
        if "$ref" in rb:
            rb = op["requestBody"] = copy.deepcopy(OM._resolve(doc, rb))
        content = rb.get("content") or {}
        body = content.get(_JSON_CT) or next((v for k, v in content.items() if "json" in k), None) or \
            next(iter(content.values()), None) or {}
        sch = body.get("schema") or {}
        if "$ref" in sch:
            sch = body["schema"] = copy.deepcopy(OM._resolve(doc, sch))
        prop = (sch.get("properties") or {}).get(field)
        if isinstance(prop, dict) and "$ref" in prop:
            prop = sch["properties"][field] = copy.deepcopy(OM._resolve(doc, prop))
        if isinstance(prop, dict) and not prop.get("x-freya-role"):
            prop["x-freya-role"] = "customer"


def identity_design(catalog, report):
    """'selector' (field + answer), 'per_field' (one optional answer field per question), 'all_at_once' (several
    required answer fields in one call), 'multi_op' (one verify operation per question)."""
    if len(report.get("verify_ops") or []) > 1:
        return "multi_op"
    t = (catalog.get("tools") or {}).get("verify_identity") or {}
    if catalog.get("identity_mode") == "selector":
        return "selector"
    roles = set((t.get("roles") or {}).get("request", {}).values())
    req = [f for f in t.get("required") or [] if f not in roles]
    return "all_at_once" if len(req) >= 2 else "per_field"


# ----------------------------------------------------------------------------------------------------------------
# Main entry

def _source_doc(case, mock_url, fetch, use_llm, budget):
    if case.get("openapi"):
        return copy.deepcopy(case["openapi"]), "case folder OpenAPI (%s)" % (case.get("openapi_path") or "?"), True
    if mock_url and fetch is not False:
        from builder import ingest
        getter = fetch or ingest.fetch_json
        try:
            got = getter(mock_url.rstrip("/") + "/openapi.json")
            if isinstance(got, dict) and ("openapi" in got or "swagger" in got) and got.get("paths"):
                return got, "mock %s/openapi.json" % mock_url.rstrip("/"), False
        except Exception as e:                              # noqa: BLE001
            _log("WARN", "mock serves no openapi.json", err=str(e)[:160])
    docs = case.get("contract_docs") or []
    if not docs:
        docs = [d for d in case.get("docs") or [] if _contractish(d)]
    if not docs:
        raise CatalogError("no service contract found in the case folder (no OpenAPI, no contract document)")
    if not use_llm:
        raise CatalogError("service contract is prose and the LLM derivation is disabled")
    _log("CATALOG", "deriving the tool API from the contract text", docs=[d.get("rel") or d.get("name") for d in docs])
    return derive_openapi_doc(docs, budget=budget), "LLM from " + ", ".join(str(d.get("rel") or d.get("name")) for d in docs), True


def build_catalog(case, mock_url, run_dir=None, *, budget=None, fetch=None, use_llm=True):
    """Case (CaseDocs / path / docs list) + our mock URL -> ToolCatalog (see the module docstring)."""
    case = _coerce_case(case, mock_url)
    doc, source, ours = _source_doc(case, mock_url, fetch, use_llm, budget)
    notes = list(doc.get("x-freya-notes") or [])
    doc, changes = normalize_for_mock(doc)
    for c in changes:
        _log("DECISION" if ours else "WARN", "mock shape: " + c + ("" if ours else
             " (the mock serves another shape: it must accept this call)"), where="LOCAL")
    if mock_url:
        from builder import ingest
        doc = ingest.with_server(doc, mock_url)
    op_map, report = map_operations(doc, budget=budget, use_llm=use_llm)
    for tool, key in op_map.items():
        _op_at(doc, key)["x-freya-tool"] = tool
    absent = [t for t in vocab.TOOLS if t not in op_map]
    customer = _customer_field(doc, op_map)
    for tool in absent:
        doc.setdefault("paths", {})[STUB_PREFIX + tool] = {"post": _stub_op(tool, customer)}
        op_map[tool] = "POST " + STUB_PREFIX + tool
        level = "ERROR" if tool in CORE_TOOLS else "WARN"
        _log(level, "service %s has no operation in the contract: built without it (stub on our mock)" % tool)
    synthetic = []
    cat = OM.build_catalog(doc, "", strict=False, annotate=True)
    for _ in range(3):
        problems = cat.get("problems") or []
        if not problems:
            break
        fixed = False
        shared = None
        # The two repairs below run only on problems that used to end the build (CatalogError): a core tool with
        # no customer field, or an account list whose items the contract does not describe.
        if any(p in ("verify_identity: no request field for role customer",
                     "get_account: no request field for role customer") for p in problems):
            shared = _shared_customer_key(doc, op_map)
            if shared:
                _bind_customer_hint(doc, op_map, shared)
                _log("WARN", "no customer field bound: the key %s shared by every operation is bound to the "
                     "customer role (baked from the call variable, never filled by the model)" % shared)
                fixed = True
        if any(_ITEM_PROBLEM_RX.match(p) for p in problems) and "get_account" in op_map:
            added, bound = _add_synthetic_items(doc, op_map["get_account"],
                                                (cat.get("tools") or {}).get("get_account"))
            for b in bound:
                _log("DECISION", "get_account: " + b, where="LOCAL")
            for leaf in added:
                synthetic.append("get_account." + leaf)
                _log("WARN", "get_account: the contract does not describe the account list items; synthetic leaf "
                     "%s served by our mock" % leaf)
            fixed = bool(added or bound) or fixed
        for prob in problems:
            if _ITEM_PROBLEM_RX.match(prob) or (shared and prob.endswith("no request field for role customer")):
                continue
            m = _PROBLEM_RX.match(prob)
            if m and m.group(1) in OPTIONAL_TOOLS + ("create_promise",):
                role = m.group(2).split("/")[0]
                name = _add_synthetic_field(doc, op_map[m.group(1)], role)
                synthetic.append("%s.%s (role %s)" % (m.group(1), name, role))
                _log("WARN", "%s: contract has no field for role %s; synthetic optional field %s sent to our mock"
                     % (m.group(1), role, name))
                fixed = True
        if not fixed:
            break
        cat = OM.build_catalog(doc, "", strict=False, annotate=True)
    if cat.get("problems"):
        raise CatalogError("service contract roles: " + "; ".join(cat["problems"]))
    raw = OM.dumps(doc).encode("utf-8")
    cat = OM.build_catalog(doc, hashlib.sha256(raw).hexdigest(), strict=True, annotate=True)
    out_path = None
    if run_dir:
        out_path = pathlib.Path(run_dir) / _OPENAPI_JSON
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(raw + b"\n")
    cat["contract"] = {
        "source": source,
        "op_map": dict(op_map),
        "absent": absent,
        "extra_operations": [k for k in report["extra"] if k not in op_map.values()],
        "identity_design": identity_design(cat, report),
        "synthetic_fields": synthetic,
        "mock_shape_changes": changes,
        "decisions": report["decisions"],
        "ambiguous": report["ambiguous"],
        "openapi_path": str(out_path) if out_path else None,
        "notes": notes,
    }
    _log("CATALOG", "service contract bound", source=source, absent=absent,
         extra=cat["contract"]["extra_operations"], identity_design=cat["contract"]["identity_design"],
         synthetic=len(synthetic), server=cat.get("server"))
    return cat


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="python -m builder.contract",
                                 description="Service contract -> derived OpenAPI for our mock + tool-role map")
    ap.add_argument("case")
    ap.add_argument("mock_url")
    ap.add_argument("--out", default=_OPENAPI_JSON)
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--no-fetch", action="store_true")
    a = ap.parse_args(argv)
    out_dir = pathlib.Path(a.out).resolve().parent
    tmp = out_dir / ".contract_run"
    cat = build_catalog(a.case, a.mock_url, tmp, fetch=False if a.no_fetch else None, use_llm=not a.no_llm)
    pathlib.Path(a.out).write_bytes((tmp / _OPENAPI_JSON).read_bytes())
    print(json.dumps({k: cat["contract"][k] for k in ("source", "op_map", "absent", "extra_operations",
                                                      "identity_design", "synthetic_fields", "mock_shape_changes")},
                     indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":                                  # pragma: no cover
    raise SystemExit(main())
