"""OpenAPI 3.x (JSON, or YAML if PyYAML is installed) -> ToolCatalog (docs/CONTRACTS.md D.1). Owner: agent 3.

The expected output for the kit OpenAPI is tests/fixtures/catalog-kit.json. Bindings are generic (names, synonyms,
types, formats, descriptions); every binding decision is reported via builder.trace (kind CATALOG / DECISION).

CONTRACT NOTE (agent 3, simplest readings chosen where D.1 is silent):
- Tools are keyed by operationId when it is one of the 7 fixed tool names, else by the last path segment.
  Only the first operation per tool is used; query/path parameters are not bound (warned).
- `write` = the tool changes bank state (every fixed tool except the identity check and the account read).
  `max_retries` = 1 only for a read whose request carries nothing but the customer role (idempotent read),
  else 0 (an identity check counts attempts, so it is never retried).
- Role binding order per leaf: exact role-like names first, then generic name patterns, then type/format.
  A leaf binds to at most one role and a role to at most one leaf.
- `wire_format` is derived only for date/time-like fields (format, a date/time role or name); other fields keep "".
- `reasonless_outcomes_hint` = outcome enum values named in the close reason's description after "except"
  (or "not required for"), in enum order; [] when the reason is a required field.
- Missing tool or missing required role -> CatalogError (contract D.1), never a silent degrade.
"""
import copy
import hashlib
import json
import pathlib
import re

from builder.spec import vocab


class CatalogError(Exception):
    """A required tool or role cannot be bound."""


CATALOG_VERSION = 1
HTTP_METHODS = ("post", "put", "patch", "get", "delete")
WRITE_TOOLS = ("create_promise", "add_note", "schedule_callback", "transfer_to_agent", "close_call")

# Roles that must bind, per tool. Tuples inside mean "one of".
REQUIRED_REQUEST_ROLES = {
    "verify_identity": ["customer"],
    "get_account": ["customer"],
    "create_promise": ["customer", "product", "amount", ("date", "datetime")],
    "add_note": ["customer", "reason"],
    "schedule_callback": ["customer", ("date", "datetime")],
    "transfer_to_agent": ["customer", "queue"],
    "close_call": ["customer", "outcome"],
}
REQUIRED_RESPONSE_ROLES = {"get_account": ["products"]}
REQUIRED_ITEM_ROLES = {"get_account": ["id", "past_due"]}

SUCCESS_WORDS = ("ok", "success", "succeeded", "successful", "recorded", "accepted", "done", "created", "completed",
                 "scheduled", "transferred", "closed", "added", "saved", "booked", "verified", "confirmed",
                 # Turkish (ASCII-folded by _n)
                 "basarili", "tamam", "tamamlandi", "kaydedildi", "olusturuldu", "onaylandi", "alindi", "aktarildi",
                 "kapatildi", "planlandi", "eklendi", "dogrulandi", "kabul_edildi", "islendi")


def _log(kind, msg, **fields):
    import sys
    from builder import trace
    fields.setdefault("mod", "builder.openapi_model." + sys._getframe(1).f_code.co_name)
    trace.event(kind, msg, **fields)                    # never raises


# ----------------------------------------------------------------------------------------------------------------
# Loading

def _parse_text(text):
    text = text.lstrip("﻿")
    try:
        return json.loads(text)
    except ValueError:
        pass
    # JSON with // or /* */ comments and trailing commas
    stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    stripped = re.sub(r"(?m)^\s*//.*$", "", stripped)
    stripped = re.sub(r",(\s*[}\]])", r"\1", stripped)
    try:
        return json.loads(stripped)
    except ValueError:
        pass
    try:
        import yaml  # optional dependency
    except ImportError:
        _log("WARN", "tool API file is not JSON and PyYAML is not installed")
        return None
    try:
        return yaml.safe_load(text)
    except Exception:
        return None


def is_openapi_file(path):
    """True if the file parses as JSON/YAML mapping with an 'openapi' key (any extension)."""
    try:
        raw = pathlib.Path(path).read_bytes()
        text = raw.decode("utf-8", errors="replace")
        if not re.search(r"(?i)[\"']?\b(openapi|swagger)[\"']?\s*:", text):
            return False                                   # cheap pre-check: briefs never reach the parser
        doc = _parse_text(text)
    except Exception:
        return False
    return isinstance(doc, dict) and ("openapi" in doc or "swagger" in doc)


def load(path):
    """Read and parse the tool API file (detected by content: a mapping with an 'openapi' key). -> ToolCatalog dict."""
    p = pathlib.Path(path)
    try:
        raw = p.read_bytes()
    except OSError as e:
        raise CatalogError(f"cannot read tool API file {p}: {e}") from None
    doc = _parse_text(raw.decode("utf-8", errors="replace"))
    if not isinstance(doc, dict) or not ("openapi" in doc or "swagger" in doc):
        raise CatalogError(f"{p.name}: not an OpenAPI document (no 'openapi' key)")
    cat = build_catalog(doc, hashlib.sha256(raw).hexdigest())
    _log("CATALOG", f"{len(cat['tools'])} tools bound from {p.name}", server=cat["server"],
         identity_mode=cat["identity_mode"], warnings=len(cat["warnings"]))
    return cat


# ----------------------------------------------------------------------------------------------------------------
# Schema resolution

def _resolve_ref(doc, ref):
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return {}
    node = doc
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(node, dict) or part not in node:
            return {}
        node = node[part]
    return node if isinstance(node, dict) else {}


def _resolve(doc, schema, seen=None, depth=0):
    """Resolve $ref and allOf (merged), normalise 3.1 type arrays and nullable. Cycle-guarded."""
    if not isinstance(schema, dict) or depth > 30:
        return {}
    seen = set(seen or ())
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref in seen:
            return {}
        seen.add(ref)
        base = _resolve(doc, _resolve_ref(doc, ref), seen, depth + 1)
        extra = {k: v for k, v in schema.items() if k != "$ref"}
        if extra:
            base = _merge(base, _resolve(doc, extra, seen, depth + 1))
        return base
    out = {k: v for k, v in schema.items() if k not in ("allOf",)}
    for sub in schema.get("allOf") or []:
        out = _merge(out, _resolve(doc, sub, seen, depth + 1))
    for key in ("oneOf", "anyOf"):
        if key in out and "type" not in out and "properties" not in out:
            subs = [_resolve(doc, s, seen, depth + 1) for s in out.get(key) or []]
            subs = [s for s in subs if s.get("type") != "null"]
            if subs:
                merged = {k: v for k, v in out.items() if k != key}
                out = _merge(merged, subs[0])
    t = out.get("type")
    if isinstance(t, list):
        non_null = [x for x in t if x != "null"]
        out["type"] = non_null[0] if non_null else "string"
    if "properties" in out and isinstance(out["properties"], dict):
        out["properties"] = {k: _resolve(doc, v, seen, depth + 1) for k, v in out["properties"].items()}
        out.setdefault("type", "object")
    if "items" in out and isinstance(out["items"], dict):
        out["items"] = _resolve(doc, out["items"], seen, depth + 1)
    if "const" in out and "enum" not in out:
        out["enum"] = [out["const"]]
    return out


def _merge(a, b):
    out = dict(a)
    for k, v in b.items():
        if k == "properties" and isinstance(v, dict):
            props = dict(out.get("properties") or {})
            props.update(v)
            out["properties"] = props
        elif k == "required" and isinstance(v, list):
            req = list(out.get("required") or [])
            req += [x for x in v if x not in req]
            out["required"] = req
        else:
            out[k] = v
    return out


def _json_schema(doc, holder):
    """requestBody or response object -> resolved JSON schema (application/json preferred)."""
    holder = _resolve(doc, holder) if isinstance(holder, dict) and "$ref" in holder else (holder or {})
    content = holder.get("content") if isinstance(holder, dict) else None
    if isinstance(content, dict) and content:
        media = content.get("application/json")
        if media is None:
            media = next((v for k, v in content.items() if "json" in k), None) or next(iter(content.values()))
        return _resolve(doc, (media or {}).get("schema") or {})
    if isinstance(holder, dict) and "schema" in holder:      # swagger 2.0 response
        return _resolve(doc, holder["schema"])
    return {}


# ----------------------------------------------------------------------------------------------------------------
# Leaves

def _s(x):
    if x is None:
        return ""
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, (dict, list)):
        return json.dumps(x, sort_keys=True)
    return str(x)


def _type(sch):
    t = sch.get("type")
    if isinstance(t, str) and t:
        return t
    if "properties" in sch:
        return "object"
    if "items" in sch:
        return "array"
    return "string"


def _wire_format(name, leaf):
    fmt = leaf.get("format") or ""
    desc = leaf.get("description") or ""
    pat = leaf.get("pattern") or ""
    ex = leaf.get("example") or ""
    lname = name.lower()
    datey = fmt in ("date", "date-time", "time") or re.search(r"(date|time|day|when)", lname) is not None
    if not datey:
        return ""
    if fmt == "date":
        return "%Y-%m-%d"
    if fmt == "date-time":
        return "%Y-%m-%dT%H:%M:%S"
    tokens = [("YYYY-MM-DD", "%Y-%m-%d"), ("DD/MM/YYYY", "%d/%m/%Y"), ("MM/DD/YYYY", "%m/%d/%Y"),
              ("DD.MM.YYYY", "%d.%m.%Y"), ("YYYYMMDD", "%Y%m%d"), ("HH:MM:SS", "%H:%M:%S"), ("HH:MM", "%H:%M"),
              ("HH:mm", "%H:%M")]
    for tok, out in tokens:
        if tok in desc:
            return out
    if fmt == "time":
        return "%H:%M"
    pat_map = [(r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"), (r"[0-9]{4}-[0-9]{2}-[0-9]{2}", "%Y-%m-%d"),
               (r"\d{2}:\d{2}", "%H:%M"), (r"[0-9]{2}:[0-9]{2}", "%H:%M")]
    for needle, out in pat_map:
        if needle in pat:
            return out
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", ex):
        return "%Y-%m-%d"
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", ex):
        return "%d/%m/%Y"
    if re.fullmatch(r"\d{1,2}:\d{2}", ex):
        return "%H:%M"
    return ""


_MINOR_TOKENS = {"cent", "cents", "minor", "pence", "penny", "kurus", "kurush"}


def _scale(name, leaf):
    """100 when the amount travels in minor units (cents / pence / kurus), else 1."""
    text = (name + " " + (leaf.get("description") or "")).lower()
    if re.search(r"\b(cents?|minor[ _]units?|pence|kurus)\b|_cents\b|cents_", text):
        return 100
    # What the pattern above misses (it used to give 1): a minor-unit word as a name token ('total_kurus',
    # 'valueMinor', 'fee_pence') or the Turkish 'kuruş' in the description; only on a leaf that can be an amount.
    if leaf.get("type", "number") not in ("number", "integer", "string"):
        return 1
    if _MINOR_TOKENS & set(_n(name).split("_")) or re.search(r"\bkurus\b", fold(leaf.get("description") or "")):
        return 100
    return 1


def _example(sch):
    if "example" in sch:
        return sch.get("example")
    ex = sch.get("examples")
    if isinstance(ex, list) and ex:
        return ex[0]
    return ""


def _request_leaf(name, sch, required):
    t = _type(sch)
    leaf = {
        "type": t,
        "required": bool(required),
        "enum": [_s(v) for v in (sch.get("enum") or []) if v is not None],
        "format": _s(sch.get("format")),
        "pattern": _s(sch.get("pattern")),
        "description": _s(sch.get("description")),
        "min_length": int(sch.get("minLength") or 0),
        "max_length": int(sch.get("maxLength") or 0),
        "example": _s(_example(sch)),
        "wire_format": "",
        "scale": 1,
    }
    leaf["wire_format"] = _wire_format(name, leaf)
    leaf["scale"] = _scale(name, leaf)
    return leaf


def _response_leaves(res_schema):
    """Top-level response properties, plus the children of nested plain objects (an envelope such as
    {"result": {...}}) as their own leaves with a dotted path, unless the name is already taken."""
    props = res_schema.get("properties") or {}
    out = {k: _response_leaf(k, v) for k, v in props.items()}
    for k, v in props.items():
        if _type(v) == "object" and isinstance(v.get("properties"), dict):
            for ck, cv in v["properties"].items():
                if ck not in out:
                    out[ck] = _response_leaf(ck, cv, "data." + k + "." + ck)
    return out


def _response_leaf(name, sch, path=None):
    leaf = {"type": _type(sch), "path": path or ("data." + name),
            "enum": [_s(v) for v in (sch.get("enum") or []) if v is not None],
            "description": _s(sch.get("description"))}
    items = sch.get("items") if isinstance(sch.get("items"), dict) else None
    if leaf["type"] == "array" and items and isinstance(items.get("properties"), dict):
        leaf["items"] = {k: {"type": _type(v), "enum": [_s(e) for e in (v.get("enum") or []) if e is not None],
                             "description": _s(v.get("description"))}
                         for k, v in items["properties"].items()}
    return leaf


# ----------------------------------------------------------------------------------------------------------------
# Role binding (generic patterns only; never a specific bank's field names)

_TR_FOLD = str.maketrans({"ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "İ": "i", "ö": "o", "Ö": "o",
                          "ş": "s", "Ş": "s", "ü": "u", "Ü": "u", "â": "a", "î": "i", "û": "u"})


def fold(text):
    """Lower-case ASCII folding of Turkish letters (language support, not case content): 'Müşteri' -> 'musteri'."""
    return str(text or "").translate(_TR_FOLD).lower()


def _n(name):
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(name or ""))          # camelCase -> camel_case
    return re.sub(r"[^a-z0-9]+", "_", fold(name)).strip("_")


_ID_SUFFIX = r"(_?(id|ref|key|number|no|numarasi|numara|kodu|kod))?"
REQ_PATTERNS = [
    # (role, regex on normalised name, extra predicate). English words, then Turkish ones (ASCII-folded by _n):
    # generic banking/call-centre vocabulary only, never a specific bank's field names.
    ("customer", r"^(customer|client|member|user|debtor|account_holder|holder)(_?(id|ref|key|number|no))?$", None),
    ("customer", r"^(customer|client|debtor)\w*$", None),
    ("customer", r"^(musteri|borclu|uye|kart_?sahibi|hesap_?sahibi)" + _ID_SUFFIX + "$", None),
    ("customer", r"^musteri\w*$", None),
    ("product", r"^(product|account|loan|contract|item|facility)(_?(id|ref|key|number|no))?$", None),
    ("product", r"^\w*(product|account|loan|contract|facility)_?(id|ref|key|number|no)$", None),
    ("product", r"^(urun|kart|hesap|hesab|kredi|sozlesme|kredi_karti)" + _ID_SUFFIX + "$", None),
    ("product", r"^\w*(urun|kart|hesap|hesab|kredi|sozlesme)\w*_(id|ref|no|numarasi|kodu)$", None),
    ("amount", r"^\w*(amount|sum|value|total)\w*$", "num_or_str"),
    ("amount", r"^\w*(tutar|miktar|meblag|bedel)\w*$", "num_or_str"),
    ("datetime", r"^\w*(datetime|date_time|timestamp|at)$", "datetime"),
    ("datetime", r"^\w*(tarih_?saat|zaman_?damgasi)\w*$", "datetime"),
    ("date", r"^\w*(date|day)\w*$", "not_time"),
    ("date", r"^\w*(tarih|gun)\w*$", "not_time"),
    ("time", r"^\w*(time|hour|slot)\w*$", None),
    ("time", r"^\w*(saat|zaman|aralik)\w*$", None),
    ("queue", r"^\w*(queue|team|department|desk|group|skill)\w*$", None),
    ("queue", r"^\w*(kuyruk|ekip|birim|departman|bolum|takim|grup)\w*$", None),
    ("outcome", r"^\w*(outcome|result|disposition|status)\w*$", None),
    ("outcome", r"^(?!\w*(neden|sebep|sebeb|gerekce))\w*(sonuc|durum|kapanis)\w*$", None),
    ("reason", r"^\w*(reason|code|cause)\w*$", None),
    ("reason", r"^\w*(neden|sebep|sebeb|gerekce|kod|kodu)\w*$", None),
    ("text", r"^\w*(text|note|comment|message|details?|body|memo|remark)\w*$", "no_enum"),
    ("text", r"^(\w*_)?(not|notu|notlar|aciklama|metin|mesaj|yorum|detay|icerik)(_\w*)?$", "no_enum"),
]


def _is_customer_name(nm):
    return any(re.match(rx, nm) for role, rx, _p in REQ_PATTERNS if role == "customer")


def _pred(kind, leaf, name):
    if kind is None:
        return True
    if kind == "num_or_str":
        return leaf["type"] in ("number", "integer", "string") and not leaf["enum"]
    if kind == "datetime":
        return leaf["format"] == "date-time" or "datetime" in name or "date_time" in name or "timestamp" in name
    if kind == "not_time":
        return leaf["format"] != "date-time"
    if kind == "no_enum":
        return not leaf["enum"]
    return True


def _bind_request(tool, request, hints=None):
    roles, used = {}, set()

    def take(role, field, why):
        if role in roles or field in used:
            return False
        roles[role] = field
        used.add(field)
        _log("DECISION", f"bind {tool}.{field} -> request role {role} ({why})", where="LOCAL")
        return True

    # 0. explicit x-freya-role hints (written by builder.contract into the derived OpenAPI)
    for field, role in (hints or {}).items():
        if field in request and role in vocab.REQUEST_ROLES:
            take(role, field, "x-freya-role")

    # 1. exact role names (and the date/time formats)
    for field, leaf in request.items():
        nm = _n(field)
        if nm in vocab.REQUEST_ROLES and nm != "customer":
            if tool == "verify_identity" or nm not in ("selector", "answer"):
                take(nm, field, "exact name")
        elif leaf["format"] == "date-time":
            take("datetime", field, "format date-time")
        elif leaf["format"] == "date":
            take("date", field, "format date")
    # 2. identity check: selector = an enum field (not the customer), answer = the free field
    if tool == "verify_identity":
        for field, leaf in request.items():
            if field in used:
                continue
            nm = _n(field)
            if _is_customer_name(nm):
                continue
            if leaf["enum"] and "selector" not in roles:
                take("selector", field, "enum field on the identity tool")
        for field, leaf in request.items():
            if field in used:
                continue
            nm = _n(field)
            if _is_customer_name(nm):
                continue
            if "selector" in roles and not leaf["enum"] and re.search(r"(answer|value|response|input|cevap|yanit|deger|girdi)", nm):
                take("answer", field, "answer-like name")
    # 3. generic patterns
    for role, rx, pred in REQ_PATTERNS:                 # (REQ_PATTERNS has no selector/answer role)
        for field, leaf in request.items():
            if field in used:
                continue
            nm = _n(field)
            if re.match(rx, nm) and _pred(pred, leaf, nm):
                if role in ("product", "amount", "date", "time", "datetime", "queue", "outcome", "reason", "text") \
                        and tool == "verify_identity":
                    continue
                take(role, field, "name pattern")
    # 4. identity check without a selector: per-field mode (each non-customer field is one question's answer)
    if tool == "verify_identity" and "selector" not in roles and "answer" not in roles:
        rest = [f for f in request if f not in used]
        if len(rest) == 1:
            take("answer", rest[0], "only remaining field")
    # 5. type/description leftovers
    for field, leaf in request.items():
        if field in used:
            continue
        d = leaf["description"].lower()
        if "HH:MM" in leaf["description"] and "time" not in roles:
            take("time", field, "description HH:MM")
        elif leaf["type"] in ("number", "integer") and "amount" not in roles and tool == "create_promise":
            take("amount", field, "only numeric field")
        elif "customer" not in roles and "customer" in d:
            take("customer", field, "description mentions the customer")
    order = [r for r in vocab.REQUEST_ROLES if r in roles]
    return {r: roles[r] for r in order}


def _bind_response(tool, response, hints=None):
    roles, used = {}, set()

    def take(role, leaf_name, why):
        if role in roles or leaf_name in used:
            return False
        roles[role] = leaf_name
        used.add(leaf_name)
        _log("DECISION", f"bind {tool} response {leaf_name} -> role {role} ({why})", where="LOCAL")
        return True

    for leaf_name, role in (hints or {}).items():
        if leaf_name in response and role in vocab.RESPONSE_ROLES:
            take(role, leaf_name, "x-freya-role")
    names = list(response)
    # s: boolean success-like leaf
    for k in names:
        nm = _n(k)
        if response[k]["type"] == "boolean" and nm in ("ok", "success", "succeeded", "successful", "recorded",
                                                       "accepted", "done", "created", "saved", "booked",
                                                       "basarili", "basari", "tamam", "kaydedildi", "olusturuldu",
                                                       "islem_basarili", "kabul_edildi"):
            take("s", k, "boolean success-like name")
    if "s" not in roles:
        for k in names:
            nm = _n(k)
            if response[k]["enum"] and re.search(r"(status|state|result|outcome|durum|sonuc)", nm):
                take("s", k, "status enum")
                break
    # all_*: all questions passed
    for k in names:
        if response[k]["type"] == "boolean" and re.match(r"^(all|fully|every|tum|tumu|hepsi|tamami)_[_a-z]*$", _n(k)):
            take("all", k, "all_* boolean")
        elif _n(k) == "all":
            take("all", k, "exact name")
    for k in names:
        nm = _n(k)
        if response[k]["type"] in ("integer", "number", "string") and re.search(r"(left|remaining|attempts|tries|kalan|hak)", nm):
            take("left", k, "*left*/*remaining* name")
    for k in names:
        if re.search(r"(hint|ipucu|ipuclari)", _n(k)):
            take("hint", k, "*hint* name")
    for k in names:
        nm = _n(k)
        if response[k]["type"] == "boolean" and re.search(r"(verified|match|matched|correct|valid|passed|dogrula|eslesti|eslesme|gecerli|dogru)", nm):
            take("verified", k, "verified-like boolean")
    for k in names:
        leaf = response[k]
        if leaf["type"] == "array" and leaf.get("items"):
            take("products", k, "array of objects")
    for k in names:
        nm = _n(k)
        if response[k]["type"] == "string" and re.search(r"(error|message|detail|reason|err|hata|mesaj|aciklama)", nm):
            take("err", k, "error-like name")
    for k in names:
        nm = _n(k)
        if response[k]["type"] in ("string", "integer") and re.search(r"(^id$|_id$|_ref$|^reference$|^referans|_no$|_numarasi$)", nm):
            take("pid", k, "id-like name")
    order = [r for r in vocab.RESPONSE_ROLES if r in roles]
    return {r: roles[r] for r in order}


def _bind_items(tool, items, hints=None):
    roles, used = {}, set()

    def take(role, leaf_name, why):
        if role in roles or leaf_name in used:
            return False
        roles[role] = leaf_name
        used.add(leaf_name)
        _log("DECISION", f"bind {tool} item {leaf_name} -> item role {role} ({why})", where="LOCAL")
        return True

    for leaf_name, role in (hints or {}).items():
        if leaf_name in items and role in vocab.ITEM_ROLES:
            take(role, leaf_name, "x-freya-role")
    names = list(items)
    for k in names:
        if _n(k) in ("id", "product_id", "account_id", "item_id", "urun_id", "urun_no", "kart_no", "hesap_no",
                     "kart_id", "hesap_id"):
            take("id", k, "id name")
    for k in names:
        if items[k]["type"] in ("string", "integer") and re.search(r"(_id|_ref|_no|_numarasi)$", _n(k)):
            take("id", k, "*_id name")
    for k in names:
        nm = _n(k)
        if items[k]["type"] in ("integer", "number") and re.search(
                r"(days?_(late|overdue|past_due|in_arrears)|dpd|late_days|overdue_days|gecikme_?gun|gun_?gecikme"
                r"|geciken_?gun|gecikme_?suresi|gecikmedeki_?gun)", nm):
            take("days_late", k, "days-late name")
    for k in names:
        nm = _n(k)
        if items[k]["type"] in ("number", "integer", "string") and re.search(
                r"(past_?due|overdue|arrears|amount_due|due_amount|outstanding|gecikmis|vadesi_?gecmis|geciken_?tutar"
                r"|odenmemis|gecikme_?tutari)", nm):
            take("past_due", k, "past-due name")
    for k in names:                                       # no overdue leaf: the debt / balance leaf
        nm = _n(k)
        if items[k]["type"] in ("number", "integer") and re.search(
                r"(balance|debt|amount|borc|bakiye|tutar)", nm) and not re.search(r"(min|asgari|limit|faiz|interest)", nm):
            take("past_due", k, "debt/balance name (no overdue leaf)")
    for k in names:
        nm = _n(k)
        if nm in ("type", "kind", "category", "product_type", "tur", "tip", "tipi", "turu", "urun_tipi", "urun_turu",
                  "kategori") or (items[k]["enum"] and re.search(r"(type|kind|category|tip|tur|kategori)", nm)):
            take("type", k, "type name")
    order = [r for r in vocab.ITEM_ROLES if r in roles]
    return {r: roles[r] for r in order}


def _success_hint(res_schema, leaf_name):
    """x-freya-success [values] on the success leaf (written by builder.contract from the contract text)."""
    props = res_schema.get("properties") or {}
    cands = [props.get(leaf_name)] + [v["properties"].get(leaf_name) for v in props.values()
                                      if isinstance(v, dict) and isinstance(v.get("properties"), dict)]
    for c in cands:
        if isinstance(c, dict) and isinstance(c.get("x-freya-success"), list):
            return [_s(v) for v in c["x-freya-success"] if v is not None and _s(v) != ""]
    return []


def _success(response, res_roles, hint=None):
    leaf_name = res_roles.get("s")
    if leaf_name:
        leaf = response[leaf_name]
        if hint and leaf["type"] != "boolean":
            vals = [v for v in hint if not leaf["enum"] or v in leaf["enum"]]
            if vals:
                return {"role": "s", "kind": "enum_in", "values": vals}
        if leaf["type"] == "boolean":
            return {"role": "s", "kind": "bool_true", "values": ["true", "True"]}
        # _bind_response binds s only to a boolean or a non-empty status enum
        vals = [v for v in leaf["enum"] if _n(v) in SUCCESS_WORDS]
        if vals:
            return {"role": "s", "kind": "enum_in", "values": vals}
    return {"role": "s", "kind": "http_ok_no_error", "values": []}


def _reasonless(close_tool, outcomes):
    roles = close_tool["roles"]["request"]
    rf = roles.get("reason")
    if not rf:
        return list(outcomes)
    leaf = close_tool["request"][rf]
    if leaf["required"]:
        return []
    desc = leaf["description"]
    m = re.search(r"(?:except(?: for)?|not (?:required|needed) (?:for|with|when)|optional for|omit(?:ted)? for)\s+(.*?)(?:\.|;|$)",
                  desc, flags=re.I)
    if not m:
        return []
    span = m.group(1).lower()
    return [o for o in outcomes if re.search(r"\b" + re.escape(o.lower()) + r"\b", span)]


# ----------------------------------------------------------------------------------------------------------------

def _server(doc, warnings):
    servers = doc.get("servers")
    if isinstance(servers, list) and servers and isinstance(servers[0], dict):
        url = _s(servers[0].get("url"))
        for var, spec in (servers[0].get("variables") or {}).items():
            url = url.replace("{" + var + "}", _s((spec or {}).get("default")))
        return url.rstrip("/")
    if doc.get("host"):                                   # swagger 2.0
        scheme = (doc.get("schemes") or ["https"])[0]
        return (scheme + "://" + doc["host"] + _s(doc.get("basePath"))).rstrip("/")
    warnings.append("no servers[0].url: tool URLs are relative")
    return ""


def _operations(doc):
    """-> {tool_name: (path, method, op)} for the 7 fixed tools. An operation's `x-freya-tool` (written by
    builder.contract after mapping renamed operations to tool roles) wins over its operationId / last path segment."""
    found = {}
    paths = doc.get("paths") or {}
    for path in sorted(paths, key=str):
        item = paths[path] or {}
        for method in HTTP_METHODS:
            op = item.get(method) if isinstance(item, dict) else None
            if isinstance(op, dict) and op.get("x-freya-tool") in vocab.TOOLS and op["x-freya-tool"] not in found:
                found[op["x-freya-tool"]] = (path, method, op)
    claimed = {(v[0], v[1]) for v in found.values()}
    for path in sorted(paths, key=str):
        item = paths[path] or {}
        for method in HTTP_METHODS:
            op = item.get(method)
            if not isinstance(op, dict) or (path, method) in claimed or op.get("x-freya-tool"):
                continue
            cand = []
            if op.get("operationId"):
                cand.append(_s(op["operationId"]))
            cand.append(path.rstrip("/").rsplit("/", 1)[-1])
            for c in cand:
                if c in vocab.TOOLS and c not in found:
                    found[c] = (path, method, op)
                    break
    return found


def _role_hints(props):
    return {k: v["x-freya-role"] for k, v in (props or {}).items()
            if isinstance(v, dict) and isinstance(v.get("x-freya-role"), str)}


def _response_hints(res_schema):
    props = res_schema.get("properties") or {}
    hints = _role_hints(props)
    for k, v in props.items():                            # envelope children (see _response_leaves)
        if isinstance(v, dict) and isinstance(v.get("properties"), dict):
            for ck, cr in _role_hints(v["properties"]).items():
                hints.setdefault(ck, cr)
    return hints


def _item_hints(res_schema, products_leaf):
    """x-freya-role hints on the product list's item properties (top-level or inside one envelope object)."""
    props = res_schema.get("properties") or {}
    cands = [props.get(products_leaf)] + [v.get("properties", {}).get(products_leaf) for v in props.values()
                                           if isinstance(v, dict) and isinstance(v.get("properties"), dict)]
    for c in cands:
        if isinstance(c, dict) and isinstance(c.get("items"), dict):
            return _role_hints(c["items"].get("properties"))
    return {}


# Extra product-item leaves the runtime has no role for, reported for the extraction/compiler (generic words).
ITEM_EXTRA = [
    ("floor", r"(minimum|min_pay|min_due|asgari|en_az)"),
    ("total", r"(total|statement_balance|balance|toplam|donem_borcu|ekstre_borcu|bakiye)"),
    ("due_date", r"(due_date|payment_due|son_odeme|vade_tarihi|odeme_tarihi)"),
    ("limit", r"(limit)"),
]


def _item_extras(items, item_roles):
    out = {}
    taken = set(item_roles.values())
    for key, rx in ITEM_EXTRA:
        for k in items:
            if k in taken:
                continue
            if re.search(rx, _n(k)):
                out[key] = k
                taken.add(k)
                break
    return out


def build_catalog(doc, sha256="", strict=True, annotate=False):
    """Parsed OpenAPI dict -> ToolCatalog dict (resolves $ref/allOf, binds roles, success predicates, wire formats).

    strict=False (builder.contract): a missing tool or an unbound required role does not raise; the catalog then
    lists them in `missing_tools` / `problems` (the caller degrades or repairs and rebuilds).
    annotate=True (builder.contract) adds per tool `item_extras` {floor|total|due_date|limit: item leaf} and
    `absent: true` for a stub operation (x-freya-absent); D.1 catalogs (annotate=False) keep the exact key set."""
    if not isinstance(doc, dict):
        raise CatalogError("OpenAPI document is not a mapping")
    doc = copy.deepcopy(doc)
    warnings = []
    server = _server(doc, warnings)
    ops = _operations(doc)
    missing = [t for t in vocab.TOOLS if t not in ops]
    if missing and strict:
        raise CatalogError("missing tools in the OpenAPI: " + ", ".join(missing))
    if missing:
        return {"catalog_version": CATALOG_VERSION, "missing_tools": missing, "problems": [], "tools": {},
                "warnings": warnings, "server": server}
    tools = {}
    for name in vocab.TOOLS:
        path, method, op = ops[name]
        if op.get("parameters"):
            warnings.append(f"{name}: path/query parameters are not bound")
        req_schema = _json_schema(doc, op.get("requestBody") or {})
        if not req_schema and op.get("parameters"):            # swagger 2.0 body parameter
            for prm in op["parameters"]:
                prm = _resolve(doc, prm) if "$ref" in prm else prm
                if prm.get("in") == "body":
                    req_schema = _resolve(doc, prm.get("schema") or {})
        required = [_s(x) for x in (req_schema.get("required") or [])]
        props = req_schema.get("properties") or {}
        request = {k: _request_leaf(k, v, k in required) for k, v in props.items()}
        responses = op.get("responses") or {}
        ok_key = next((k for k in ("200", "201", "202") if k in responses), None)
        if ok_key is None:
            ok_key = next((k for k in sorted(responses, key=str) if str(k).startswith("2")), None)
        res_schema = _json_schema(doc, responses.get(ok_key) or {}) if ok_key else {}
        if not isinstance(res_schema.get("properties"), dict):
            res_schema = {}
        response = _response_leaves(res_schema)
        req_roles = _bind_request(name, request, _role_hints(props))
        res_roles = _bind_response(name, response, _response_hints(res_schema))
        item_roles, extras = {}, {}
        if "products" in res_roles:
            items = response[res_roles["products"]].get("items") or {}
            item_roles = _bind_items(name, items, _item_hints(res_schema, res_roles["products"]))
            extras = _item_extras(items, item_roles)
        success = _success(response, res_roles, _success_hint(res_schema, res_roles.get("s")))
        write = name in WRITE_TOOLS
        only_customer = set(req_roles) <= {"customer"}
        tools[name] = {
            "method": method.upper(),
            "path": path,
            "url": server + (path if path.startswith("/") else "/" + path),
            "summary": _s(op.get("summary") or op.get("description")),
            "request": request,
            "required": [r for r in required if r in request],
            "response": response,
            "roles": {"request": req_roles, "response": res_roles, "item": item_roles},
            "success": success,
            "write": write,
            "max_retries": 1 if (not write and only_customer) else 0,
        }
        if extras and annotate:
            tools[name]["item_extras"] = extras
        if op.get("x-freya-absent") and annotate:
            tools[name]["absent"] = True
        if success["kind"] == "http_ok_no_error":
            warnings.append(f"{name}: no success leaf; success = HTTP 2xx with an empty error")
    problems = _check_roles(tools, raise_=strict)
    if problems:
        return {"catalog_version": CATALOG_VERSION, "missing_tools": [], "problems": problems, "tools": tools,
                "warnings": warnings, "server": server}
    enums = _enums(tools)
    reasonless = _reasonless(tools["close_call"], enums["outcome"])
    close_reason = tools["close_call"]["roles"]["request"].get("reason")
    if close_reason and not tools["close_call"]["request"][close_reason]["enum"]:
        warnings.append("close_call.reason has no enum: free string bound from the brief's outcome table")
    verify = tools["verify_identity"]["roles"]["request"]
    identity_mode = "selector" if "selector" in verify else "per_field"
    if identity_mode == "per_field":
        warnings.append("verify_identity has no selector field: per_field identity mode")
    return {
        "catalog_version": CATALOG_VERSION,
        "openapi_sha256": sha256,
        "server": server,
        "identity_mode": identity_mode,
        "tools": tools,
        "enums": enums,
        "reasonless_outcomes_hint": reasonless,
        "warnings": warnings,
    }


def _check_roles(tools, raise_=True):
    problems = []
    for tool, req in REQUIRED_REQUEST_ROLES.items():
        have = tools[tool]["roles"]["request"]
        for r in req:
            alts = r if isinstance(r, tuple) else (r,)
            if not any(a in have for a in alts):
                problems.append(f"{tool}: no request field for role {'/'.join(alts)}")
    for tool, req in REQUIRED_RESPONSE_ROLES.items():
        for r in req:
            if r not in tools[tool]["roles"]["response"]:
                problems.append(f"{tool}: no response leaf for role {r}")
    for tool, req in REQUIRED_ITEM_ROLES.items():
        for r in req:
            if r not in tools[tool]["roles"]["item"]:
                problems.append(f"{tool}: no product item leaf for role {r}")
    vroles = tools["verify_identity"]["roles"]["request"]
    if "selector" in vroles and "answer" not in vroles:
        problems.append("verify_identity: selector field but no answer field")
    if "selector" not in vroles and "answer" not in vroles:
        free = [f for f in tools["verify_identity"]["request"] if f not in vroles.values()]
        if not free:
            problems.append("verify_identity: no answer field")
    sch = tools["schedule_callback"]["roles"]["request"]
    if "date" in sch and "time" not in sch and "datetime" not in sch:
        problems.append("schedule_callback: no request field for role time")
    if problems and raise_:
        raise CatalogError("; ".join(problems))
    return problems


def _enum_of(tools, tool, role, where="request"):
    t = tools[tool]
    if where == "request":
        f = t["roles"]["request"].get(role)
        return list(t["request"][f]["enum"]) if f else []
    if where == "response":
        f = t["roles"]["response"].get(role)
        return list(t["response"][f]["enum"]) if f else []
    plist = t["roles"]["response"].get("products")
    f = t["roles"]["item"].get(role)
    if not plist or not f:
        return []
    return list((t["response"][plist].get("items") or {}).get(f, {}).get("enum") or [])


def _enums(tools):
    return {
        "identity_field": _enum_of(tools, "verify_identity", "selector"),
        "hint": _enum_of(tools, "verify_identity", "hint", "response"),
        "product_type": _enum_of(tools, "get_account", "type", "item"),
        "note_reason": _enum_of(tools, "add_note", "reason"),
        "queue": _enum_of(tools, "transfer_to_agent", "queue"),
        "outcome": _enum_of(tools, "close_call", "outcome"),
        "close_reason": _enum_of(tools, "close_call", "reason"),
    }


def dumps(catalog):
    """Stable JSON text of a catalog (for run_dir/catalog.json)."""
    return json.dumps(catalog, indent=1, ensure_ascii=False)
