"""OpenAPI service contract + test-customers table -> mock/config.json, mock/customers.json, mock/openapi.json.

    python3 tools/mockgen/make_config.py --openapi <contract.openapi.json | run dir | case folder>
                                         --customers <table file or folder> [...] [--out mock] [--llm --docs DIR]

Every decision is deterministic and printed; the optional LLM step (builder/llm.py, --llm) only fills gaps the rules
leave open (an operation with no role, a column with no target, the close-reason table) and its answer is validated
against the contract before use. Generic language words (English and Turkish) only: nothing from a specific case.

Python API (for other workstreams):
    build_config(doc, *, lang=None, max_wrong=None, reasonless=None, reasons_by_outcome=None, name=None)
        -> (config, warnings)
    load_customers(paths, config, *, column_map=None) -> (customers, warnings, unmapped)
    validate(config, customers) -> [error]
    write(out_dir, config, customers, doc) -> {name: path}
    generate(openapi_path, customer_paths, out_dir, **kw) -> report dict   (all of the above in one call)
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import datetime
import io
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from builder import openapi_model as om          # noqa: E402
from tools.mockgen import tables as tbl          # noqa: E402

ROLES = ("verify", "account", "promise", "note", "callback", "transfer", "close")
FIXED = {"verify": "verify_identity", "account": "get_account", "promise": "create_promise", "note": "add_note",
         "callback": "schedule_callback", "transfer": "transfer_to_agent", "close": "close_call"}
FIXED_TO_ROLE = {v: k for k, v in FIXED.items()}

# generic words per role (English + Turkish, ASCII-folded); matched on operationId, path and summary
ROLE_WORDS = {
    "verify": ["verify", "verification", "identity", "authenticate", "auth", "security", "kimlik", "dogrula",
               "dogrulama", "guvenlik"],
    "account": ["account", "balance", "statement", "debt", "products", "summary", "hesap", "borc", "ekstre", "bakiye",
                "urunler", "ozet", "kart_bilgi", "musteri_bilgi"],
    "promise": ["promise", "commitment", "pledge", "payment_plan", "soz", "odeme_sozu", "taahhut", "vaat"],
    "note": ["note", "comment", "remark", "not_ekle", "not", "aciklama", "yorum"],
    "callback": ["callback", "call_back", "schedule", "appointment", "geri_arama", "geri_ara", "randevu"],
    "transfer": ["transfer", "handoff", "hand_off", "escalate", "agent", "human", "aktar", "aktarim", "yonlendir",
                 "temsilci", "devret"],
    "close": ["close", "end_call", "finish", "hangup", "outcome", "disposition", "kapat", "bitir", "sonlandir",
              "sonuc"],
}

# extra request-field patterns (Turkish) for roles the builder's English patterns leave unbound
TR_REQ = [
    ("customer", r"^(musteri|mus)(_?(id|no|numarasi|kodu|kimlik))?$"),
    ("customer", r"^musteri\w*$"),
    ("product", r"^(urun|kart|hesap|kredi)(_?(id|no|numarasi|kodu))?$"),
    ("amount", r"^\w*(tutar|miktar|meblag|odeme_tutari)\w*$"),
    ("datetime", r"^\w*(tarih_saat|zaman)\w*$"),
    ("date", r"^\w*(tarih|gun)\w*$"),
    ("time", r"^\w*(saat)\w*$"),
    ("queue", r"^\w*(kuyruk|birim|ekip|departman|hedef)\w*$"),
    ("outcome", r"^\w*(sonuc|durum)\w*$"),
    ("reason", r"^\w*(neden|sebep|gerekce|kod)\w*$"),
    ("text", r"^\w*(not|aciklama|metin|yorum|mesaj)\w*$"),
    ("selector", r"^\w*(soru|alan|tip|tur)\w*$"),
    ("answer", r"^\w*(cevap|yanit|deger)\w*$"),
]
TR_RES = [
    ("s", "boolean", r"^(basarili|basari|tamam|sonuc_basarili)$"),
    ("err", "string", r"^\w*(hata|mesaj|aciklama)\w*$"),
    ("verified", "boolean", r"^\w*(dogrulandi|dogru|eslesti|gecti)\w*$"),
    ("left", None, r"^\w*(kalan|hak)\w*$"),
    ("all", "boolean", r"^(tum|tamami|hepsi)\w*$"),
    ("hint", None, r"^\w*(ipucu|uyari)\w*$"),
    ("pid", None, r"^\w*(_no|_id|numarasi|kodu)$"),
]
TR_ITEM_ID = r"^(urun|kart|hesap)(_?(id|no|numarasi|kodu))?$"

# column synonyms (normalised, ASCII-folded); a group is a set of names for one attribute
SYNONYMS = [
    {"customer_id", "customer", "customer_no", "customer_number", "client_id", "client", "musteri_id", "musteri_no",
     "musteri_numarasi", "musteri", "musteri_kodu", "id"},
    {"date_of_birth", "dob", "birth_date", "birthdate", "birthday", "dogum_tarihi", "dogum_gunu", "d_tarihi"},
    {"phone_last4", "phone_last_4", "phone_last_four", "last4_phone", "tel_son4", "tel_son_4", "telefon_son4",
     "telefon_son_4", "telefon_son_dort", "telefon_son_dort_hane", "son_4_hane", "telefon_son_4_hane"},
    {"first_name", "firstname", "given_name", "name", "ad", "adi", "isim"},
    {"last_name", "lastname", "surname", "family_name", "soyad", "soyadi"},
    {"full_name", "ad_soyad", "adi_soyadi", "isim_soyisim", "musteri_adi"},
    {"title", "salutation", "unvan", "hitap"},
    {"card_last4", "card_last_4", "kart_son4", "kart_son_4", "kart_son_dort", "kart_son_4_hane"},
    {"product_id", "urun_id", "urun_no", "product", "urun"},
    {"type", "product_type", "urun_tipi", "urun_turu", "tip", "tur"},
    {"now", "call_time", "arama_zamani", "arama_saati", "cagri_zamani"},
]
VARIABLE_NAMES = ["first_name", "last_name", "full_name", "title", "now", "gender", "language", "phone"]

TURKISH_CHARS = re.compile(r"[ğĞışŞİçÇöÖüÜ]")
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "bir": 1, "iki": 2, "uc": 3, "dort": 4,
                "bes": 5}


# ---------------------------------------------------------------------------------------------------- helpers

def fold(s):
    tr = str.maketrans("çÇğĞıİöÖşŞüÜâÂîÎûÛ", "cCgGiIoOsSuUaAiIuU")
    return str(s or "").translate(tr)


def norm(s):
    s = re.sub(r"\([^)]*\)", " ", fold(s)).lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _quiet(fn, *a, **kw):
    """Call a builder binding function without its trace lines on stdout."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def parse_doc(path):
    p = pathlib.Path(path)
    if p.is_dir():
        cands = sorted([f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in (".json", ".yaml", ".yml")
                        and om.is_openapi_file(f)], key=lambda f: (0 if "openapi" in f.name.lower() else 1, str(f)))
        if not cands:
            raise SystemExit(f"no OpenAPI file under {p}")
        p = cands[0]
    doc = om._parse_text(p.read_bytes().decode("utf-8", errors="replace"))
    if not isinstance(doc, dict) or not ("openapi" in doc or "swagger" in doc):
        raise SystemExit(f"{p}: not an OpenAPI document")
    return doc, p


def _num_words(text):
    t = norm(text).replace("_", " ")
    m = re.search(r"\b(\d+|one|two|three|four|five|bir|iki|uc|dort|bes)\s+(\w+\s+)?(wrong|incorrect|failed|yanlis|"
                  r"hatali|basarisiz)", t)
    if not m:
        m = re.search(r"\b(max|maximum|en fazla|limit)\D{0,20}(\d+)", t)
        return int(m.group(2)) if m else None
    w = m.group(1)
    return int(w) if w.isdigit() else NUMBER_WORDS.get(w)


# ---------------------------------------------------------------------------------------------------- operations

def _hints(props):
    """x-freya-role hints written by builder.contract into the derived OpenAPI."""
    return {k: v["x-freya-role"] for k, v in (props or {}).items()
            if isinstance(v, dict) and isinstance(v.get("x-freya-role"), str)}


def operations(doc):
    """-> [{name, method, path, op_id, summary, request{field: leaf}, required[], response{leaf}, codes[], hints,
    res_hints, synthetic[], x_tool, absent, x_success}]. Path/query parameters become request fields."""
    out = []
    for path in sorted(doc.get("paths") or {}, key=str):
        item = doc["paths"][path] or {}
        for method in om.HTTP_METHODS:
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            req_schema = om._json_schema(doc, op.get("requestBody") or {})
            props = dict(req_schema.get("properties") or {})
            required = [om._s(x) for x in (req_schema.get("required") or [])]
            for prm in (item.get("parameters") or []) + (op.get("parameters") or []):
                prm = om._resolve(doc, prm) if isinstance(prm, dict) and "$ref" in prm else prm
                if not isinstance(prm, dict) or prm.get("in") not in ("path", "query"):
                    if isinstance(prm, dict) and prm.get("in") == "body":       # swagger 2.0
                        sch = om._resolve(doc, prm.get("schema") or {})
                        props.update(sch.get("properties") or {})
                        required += [om._s(x) for x in (sch.get("required") or [])]
                    continue
                props[prm["name"]] = om._resolve(doc, prm.get("schema") or {"type": "string"})
                if prm.get("required") or prm.get("in") == "path":
                    required.append(prm["name"])
            synthetic = [k for k, v in props.items() if isinstance(v, dict) and v.get("x-freya-synthetic")]
            synthetic_roles = {k: props[k].get("x-freya-role") for k in synthetic if props[k].get("x-freya-role")}
            request = {}
            for k, v in props.items():
                if k in synthetic:
                    continue                                 # added for the engine only: the mock ignores it
                leaf = om._request_leaf(k, v, k in required)
                for src, dst in (("minimum", "minimum"), ("maximum", "maximum"), ("exclusiveMinimum", "exclusive_minimum")):
                    if isinstance(v.get(src), (int, float)) and not isinstance(v.get(src), bool):
                        leaf[dst] = v[src]
                request[k] = leaf
            responses = op.get("responses") or {}
            ok_key = next((k for k in ("200", "201", "202") if k in responses), None) or \
                next((k for k in sorted(responses, key=str) if str(k).startswith("2")), None)
            res_schema = om._json_schema(doc, responses.get(ok_key) or {}) if ok_key else {}
            res_props = res_schema.get("properties") if isinstance(res_schema.get("properties"), dict) else {}
            response = om._response_leaves(res_schema) if res_props else {}
            res_hints = _hints(res_props)
            item_hints, x_success = {}, None
            for k, v in res_props.items():
                if isinstance(v, dict) and isinstance(v.get("properties"), dict):
                    for ck, cr in _hints(v["properties"]).items():
                        res_hints.setdefault(ck, cr)
                if isinstance(v, dict) and isinstance(v.get("items"), dict):
                    item_hints.update(_hints((v["items"] or {}).get("properties")))
                if isinstance(v, dict) and isinstance(v.get("x-freya-success"), list):
                    x_success = [om._s(x) for x in v["x-freya-success"]]
            name = om._s(op.get("operationId")) or path.rstrip("/").rsplit("/", 1)[-1] or method
            out.append({"name": name, "method": method.upper(), "path": path, "op_id": om._s(op.get("operationId")),
                        "summary": om._s(op.get("summary")) + " " + om._s(op.get("description")),
                        "request": request, "required": [r for r in required if r in request],
                        "response": response, "codes": [str(c) for c in responses],
                        "hints": {k: r for k, r in _hints(props).items() if k in request},
                        "res_hints": res_hints, "item_hints": item_hints, "synthetic": synthetic,
                        "synthetic_roles": synthetic_roles,
                        "x_tool": om._s(op.get("x-freya-tool")), "absent": bool(op.get("x-freya-absent")),
                        "x_success": x_success})
    return out


def _role_scores(op):
    """-> {role: score}. x-freya-tool or an exact fixed tool name wins outright; then name words; then fields."""
    if op.get("x_tool") in FIXED_TO_ROLE:
        return {FIXED_TO_ROLE[op["x_tool"]]: 1000}
    names = {norm(op["op_id"]), norm(op["path"].rstrip("/").rsplit("/", 1)[-1])}
    for fixed, role in FIXED_TO_ROLE.items():
        if fixed in names:
            return {role: 100}
    text = "_" + "_".join([norm(op["op_id"]), norm(op["path"])]) + "_"
    summary = "_" + norm(op["summary"]) + "_"
    scores = {}
    for role, words in ROLE_WORDS.items():
        for w in words:
            if re.search(r"(^|_)" + re.escape(w), text):
                scores[role] = scores.get(role, 0) + 10
            if re.search(r"(^|_)" + re.escape(w), summary):
                scores[role] = scores.get(role, 0) + 2
    fields = {norm(f): leaf for f, leaf in op["request"].items()}
    has = lambda rx: any(re.search(rx, f) for f in fields)                                  # noqa: E731
    if has(r"(amount|tutar|miktar)") and has(r"(date|tarih|day|gun)"):
        scores["promise"] = scores.get("promise", 0) + 6
    if has(r"(queue|kuyruk|department|birim)"):
        scores["transfer"] = scores.get("transfer", 0) + 6
    if has(r"(outcome|sonuc|disposition)"):
        scores["close"] = scores.get("close", 0) + 6
    if has(r"(^time$|saat)") and not has(r"(amount|tutar)"):
        scores["callback"] = scores.get("callback", 0) + 4
    if has(r"(answer|cevap|yanit)") or has(r"(birth|dogum)"):
        scores["verify"] = scores.get("verify", 0) + 6
    if any(leaf["type"] == "array" for leaf in op["response"].values()) and len(op["request"]) <= 2:
        scores["account"] = scores.get("account", 0) + 4
    return scores


def assign_roles(ops, overrides=None):
    """-> ({role: op}, extra ops, warnings). Overrides first, then the best (score, role) pairs (x-freya-tool
    scores 1000); one op per role, one role per op. Unclaimed operations are returned as `extra`."""
    overrides = overrides or {}
    taken, roles, warnings = set(), {}, []
    for role, key in overrides.items():
        hit = next((o for o in ops if key in (o["name"], o["path"], o["method"] + " " + o["path"])), None)
        if hit and role in ROLES:
            roles[role] = hit
            taken.add(id(hit))
    pairs = sorted(((sc, role, i) for i, o in enumerate(ops) for role, sc in _role_scores(o).items()),
                   key=lambda x: (-x[0], ROLES.index(x[1]), x[2]))
    for sc, role, i in pairs:
        if role in roles or id(ops[i]) in taken or sc < 4:
            continue
        roles[role] = ops[i]
        taken.add(id(ops[i]))
    extra = [o for o in ops if id(o) not in taken]
    for role in ROLES:
        if role not in roles:
            warnings.append(f"no operation for role {role}")
    return roles, extra, warnings


def _call_bind(fn, tool, leaves, hints):
    try:
        return dict(_quiet(fn, tool, leaves, hints or None))
    except TypeError:                                       # an older binder without the hints argument
        return dict(_quiet(fn, tool, leaves))


def _bind_fields(role, op):
    """Request roles via the builder's binder (same decisions as the agent's catalog, x-freya-role hints first),
    then Turkish supplements for roles it leaves open."""
    req = op["request"]
    roles = _call_bind(om._bind_request, FIXED[role], req, op.get("hints"))
    used = set(roles.values())
    for r, rx in TR_REQ:
        if r in roles:
            continue
        if r in ("selector", "answer") and role != "verify":
            continue
        if role == "verify" and r not in ("customer", "selector", "answer"):
            continue
        for f, leaf in req.items():
            if f in used:
                continue
            if re.match(rx, norm(f)):
                if r == "selector" and not leaf["enum"]:
                    continue
                roles[r] = f
                used.add(f)
                break
    if role == "note" and "reason" not in roles:
        enum_f = next((f for f, leaf in req.items() if f not in used and leaf["enum"]), None)
        if enum_f:
            roles["reason"] = enum_f
            used.add(enum_f)
    if role == "verify" and "selector" in roles and "answer" not in roles:
        rest = [f for f in req if f not in used]
        if len(rest) == 1:
            roles["answer"] = rest[0]
    if "customer" not in roles:
        cands = [f for f in req if f not in used and re.search(r"(customer|client|musteri)", norm(f))]
        if cands:
            roles["customer"] = cands[0]
    return roles


SUCCESS_TR = ("basarili", "tamam", "onaylandi", "kaydedildi", "evet", "olumlu")


def _bind_response(role, op):
    """-> ({role: dotted response path}, s_values or None)."""
    res = op["response"]
    roles = _call_bind(om._bind_response, FIXED.get(role, "close_call"), res, op.get("res_hints"))
    used = set(roles.values())
    for r, typ, rx in TR_RES:
        if r in roles:
            continue
        for k, leaf in res.items():
            if k in used or (typ and leaf["type"] != typ):
                continue
            if re.match(rx, norm(k)):
                roles[r] = k
                used.add(k)
                break
    if "s" not in roles:
        k = next((k for k, leaf in res.items() if leaf["enum"] and k not in used
                  and re.match(r"^\w*(durum|sonuc|status|state|result)\w*$", norm(k))), None)
        if k:
            roles["s"] = k
    if "products" not in roles and role == "account":
        arr = [k for k, leaf in res.items() if leaf["type"] == "array"]
        if arr:
            roles["products"] = arr[0]
    s_values = None
    if roles.get("s") and res[roles["s"]]["type"] != "boolean":
        enum = res[roles["s"]]["enum"]
        good = [v for v in (op.get("x_success") or []) if v in enum] or \
            [v for v in enum if norm(v) in om.SUCCESS_WORDS or norm(v) in SUCCESS_TR]
        if good:
            bad = [v for v in enum if v not in good]
            s_values = {"ok": good[0], "fail": bad[0] if bad else "error"}
        else:
            roles.pop("s")                                  # no readable success value: leave the leaf out
    # dotted response paths for leaves inside an envelope object ("data.result.ok" -> "result.ok")
    return {r: res[k]["path"][5:] if res[k]["path"].startswith("data.") else k for r, k in roles.items()}, s_values


def _req_rules(op, field_roles):
    out = {}
    for f, leaf in op["request"].items():
        rule = {"type": leaf["type"], "required": leaf["required"]}
        for k in ("enum", "pattern", "min_length", "max_length", "minimum", "maximum", "exclusive_minimum"):
            if leaf.get(k) not in (None, "", [], 0) or (k in ("minimum", "maximum") and k in leaf):
                rule[k] = leaf[k]
        role = next((r for r, ff in field_roles.items() if ff == f), None)
        wire = leaf.get("wire_format") or ""
        if role in ("date", "time", "datetime"):
            wire = wire or _wire_from_text(leaf["description"] + " " + leaf.get("pattern", "") + " " + leaf.get("example", "")) \
                or {"date": "%Y-%m-%d", "time": "%H:%M", "datetime": "%Y-%m-%dT%H:%M:%S"}[role]
            rule["wire_format"] = wire
        elif wire and role not in ("answer", "selector"):
            rule["wire_format"] = wire
        if role == "amount" and leaf.get("scale", 1) != 1:
            rule["scale"] = leaf["scale"]
        out[f] = rule
    return out


def _wire_from_text(text):
    t = text.upper()
    for tok, out in (("YYYY-MM-DD", "%Y-%m-%d"), ("YYYY-AA-GG", "%Y-%m-%d"), ("DD.MM.YYYY", "%d.%m.%Y"),
                     ("GG.AA.YYYY", "%d.%m.%Y"), ("DD/MM/YYYY", "%d/%m/%Y"), ("GG/AA/YYYY", "%d/%m/%Y"),
                     ("YYYYMMDD", "%Y%m%d"), ("HH:MM", "%H:%M"), ("SS:DD", "%H:%M")):
        if tok in t:
            return out
    return ""


def _reasonless(close_op, outcome_field, reason_field):
    if not reason_field or not outcome_field:
        return []
    outcomes = close_op["request"][outcome_field]["enum"]
    leaf = close_op["request"][reason_field]
    if leaf["required"]:
        return []
    desc = leaf["description"] + " " + close_op["summary"]
    m = re.search(r"(?:except(?: for)?|not (?:required|needed) (?:for|with|when)|optional for|omit(?:ted)? for)"
                  r"\s+(.*?)(?:\.|;|$)", desc, flags=re.I)
    span = m.group(1) if m else ""
    m2 = re.search(r"([^.;]*?)\s+(?:dışında|disinda|hariç|haric)\b", desc, flags=re.I)
    if m2:
        span += " " + m2.group(1)
    if not span.strip():
        return []
    return [o for o in outcomes if re.search(r"(?<![\w])" + re.escape(o.lower()) + r"(?![\w])", span.lower())]


def _statuses(ops):
    """HTTP status per refusal kind, from the response codes the contract documents (union over operations)."""
    codes = set()
    for o in ops:
        codes |= set(o["codes"])
    st = {"ok": 200, "invalid": 200, "refused": 200, "not_verified": 200, "conflict": 200, "locked": 200,
          "closed": 200, "unknown_product": 200, "unknown_customer": 404, "unknown_operation": 404, "fault": 500}
    if "400" in codes or "422" in codes:
        st["invalid"] = 400 if "400" in codes else 422
    if "403" in codes or "401" in codes:
        st["not_verified"] = 403 if "403" in codes else 401
    if "409" in codes:
        st["conflict"] = st["closed"] = 409
    if "423" in codes:
        st["locked"] = 423
    elif "429" in codes:
        st["locked"] = 429
    if "404" in codes:
        st["unknown_product"] = 404
    if "503" in codes and "500" not in codes:
        st["fault"] = 503
    return st


def detect_lang(doc):
    text = json.dumps(doc, ensure_ascii=False)
    return "tr" if len(TURKISH_CHARS.findall(text)) >= 5 or re.search(r"\b(musteri|tutar|tarih|kimlik)\b", norm(text).replace("_", " ")) else "en"


def _stub_entry(op, for_role=None):
    fields = {}
    cf = next((f for f in op["request"] if re.search(r"(customer|client|musteri)", norm(f))), None)
    if op.get("hints"):
        cf = next((f for f, r in op["hints"].items() if r == "customer"), cf)
    if cf:
        fields["customer"] = cf
    response, s_values = _bind_response("stub", op)
    entry = {"name": op["name"], "role": "stub", "method": op["method"], "path": op["path"], "fields": fields,
             "request": {}, "response": {k: v for k, v in response.items() if k in ("s", "err")}}
    if s_values:
        entry["s_values"] = s_values
    if cf:
        entry["customer"] = cf
    if for_role:
        entry["for_role"] = for_role
    return entry


def build_config(doc, *, lang=None, max_wrong=None, reasonless=None, reasons_by_outcome=None, name=None,
                 role_overrides=None, session=None):
    """Parsed OpenAPI -> (config dict, [warning])."""
    ops = operations(doc)
    roles, extra, warnings = assign_roles(ops, role_overrides)
    # an unclaimed operation that reads as an identity check is a second verify operation (one question per
    # operation); any other unclaimed operation becomes a stub that always answers ok (never a 404 for the agent)
    extra_verify = [o for o in extra if not o["absent"] and (_role_scores(o).get("verify", 0) >= 10)
                    and max(_role_scores(o).items(), key=lambda x: x[1])[0] == "verify"]
    cfg_ops, customer_fields = [], []
    products = {"list": None, "id": "product_id", "type": "type", "id_prefix": "p"}
    plan = [(r, roles[r]) for r in ROLES if r in roles] + [("verify", o) for o in extra_verify]
    for role, op in plan:
        if op["absent"]:
            cfg_ops.append(_stub_entry(op, role))
            warnings.append(f"{role}: absent from the contract (x-freya-absent): stub, always ok")
            continue
        fields = _bind_fields(role, op)
        response, s_values = _bind_response(role, op)
        entry = {"name": op["name"], "role": role, "method": op["method"], "path": op["path"],
                 "fields": fields, "request": _req_rules(op, fields), "response": response}
        if s_values:
            entry["s_values"] = s_values
        if op["synthetic"]:
            entry["ignored_fields"] = op["synthetic"]
            # the agent fills a synthetic field (added by builder.contract) when its binder found no contract field
            # for a role; if the mock did bind a real field to that role, the synthetic value stands in for it
            aliases = {f: fields[r] for f, r in op["synthetic_roles"].items() if r in fields and fields[r] != f}
            if aliases:
                entry["aliases"] = aliases
                warnings.append(f"{role}: synthetic field(s) stand in for contract fields {aliases}")
        if fields.get("customer"):
            entry["customer"] = fields["customer"]
            customer_fields.append(fields["customer"])
        else:
            warnings.append(f"{role} {op['path']}: no customer field in the request")
        text = norm(op["summary"]).replace("_", " ")
        if role == "verify":
            if response.get("hint"):
                enum = op["response"].get(response["hint"].split(".")[-1], {}).get("enum") or []
                if enum:
                    entry["hint_value"] = enum[0]
            if "selector" not in fields:
                entry["identity_fields"] = {f: f for f in op["request"] if f not in fields.values()}
            mw = _num_words(op["summary"] + " " + " ".join(lf["description"] for lf in op["request"].values()))
            if mw and not max_wrong:
                max_wrong = mw
        if role == "account" and response.get("products"):
            leaf = op["response"].get(response["products"].split(".")[-1]) or {}
            items = leaf.get("items") or {}
            item_roles = _call_bind(om._bind_items, "get_account", items, op.get("item_hints")) if items else {}
            if "id" not in item_roles:
                tid = next((k for k in items if re.match(TR_ITEM_ID, norm(k))), None)
                if tid:
                    item_roles["id"] = tid
            products = {"list": response["products"], "id": item_roles.get("id") or "product_id",
                        "type": item_roles.get("type") or "type", "id_prefix": "p",
                        "fields": {k: v["type"] for k, v in items.items()}}
            entry["account_fields"] = {k: v["type"] for k, v in op["response"].items()
                                       if k not in [p.split(".")[-1] for p in response.values()]
                                       and v["type"] != "array"}
        elif role == "account":
            entry["account_fields"] = {k: v["type"] for k, v in op["response"].items()
                                       if k not in [p.split(".")[-1] for p in response.values()]}
        if role == "promise":
            entry["id_prefix"] = "pr"
            entry["one_per"] = "product" if fields.get("product") else "call"
            if "amount" not in fields:
                warnings.append("promise: no amount field bound")
            if not (fields.get("date") or fields.get("datetime")):
                warnings.append("promise: no date field bound")
        if role in ("account", "promise"):
            entry["needs_verified"] = True
        elif re.search(r"(refused|rejected|only) (until|after)|after (the )?(identity|verification)|"
                       r"dogrula\w* (sonra|olmadan)|kimlik dogrulan", text):
            entry["needs_verified"] = True
            warnings.append(f"{role}: gated on identity (summary says so)")
        else:
            entry["needs_verified"] = False
        if role == "close":
            entry["reasonless"] = list(reasonless) if reasonless is not None else \
                _reasonless(op, fields.get("outcome"), fields.get("reason"))
            if reasons_by_outcome:
                entry["reasons_by_outcome"] = reasons_by_outcome
            # a reason is demanded only when the contract says so (required field, or "required except ..." text);
            # otherwise a missing reason is accepted (a wrong reason for a known outcome is still refused)
            entry["reason_required"] = bool(fields.get("reason") and (op["request"][fields["reason"]]["required"]
                                                                       or entry["reasonless"]))
        cfg_ops.append(entry)
    for o in extra:
        if o in extra_verify:
            warnings.append(f"operation {o['method']} {o['path']}: a second identity-check operation")
            continue
        cfg_ops.append(_stub_entry(o))
        warnings.append(f"operation {o['method']} {o['path']} has no role: stub, always ok")
    server = _quiet(om._server, doc, [])
    base = re.sub(r"^[a-z]+://[^/]+", "", server or "").rstrip("/")
    cust_field = max(set(customer_fields), key=customer_fields.count) if customer_fields else "customer_id"
    cfg = {
        "version": 1,
        "name": name or "bank-mock",
        "lang": lang or detect_lang(doc),
        "customer_field": cust_field,
        "max_wrong": int(max_wrong or 3),
        "lenient_dates": True,
        "base_paths": [base] if base else [],
        "statuses": _statuses([o for _, o in plan]),
        "documents_404": any("404" in o["codes"] for _, o in plan),
        "session": {"idle_reset_s": 240, "closed_grace_s": 15, "new_call_on_verify_after_close": True,
                    "key_fields": [], "key_headers": [], "history": 20, **(session or {})},
        "products": products,
        "ops": cfg_ops,
    }
    return cfg, warnings


# ---------------------------------------------------------------------------------------------------- contract tables

# error meaning -> kind, first match wins (generic English + Turkish wording, ASCII-folded, lower case)
ERROR_KIND_RULES = [
    ("fault", r"(sistem hatasi|system error|service (failed|error|unavailable)|internal (server )?error|http 5\d\d)"),
    ("locked", r"(hakk?\w* (bitti|doldu|kalmadi|tukendi)|too many|attempts? (are )?(exhausted|used up)|kilit|locked)"),
    ("closed", r"(kapatil|kapanmis|already closed|call (is )?closed|gorusme (zaten )?kapa)"),
    ("duplicate", r"(zaten|already (has|exists|recorded)|duplicate|ikinci)"),
    ("not_verified", r"(dogrulama\w* (tamamlanmadi|yapilmadi|gerekli|gecilmedi)|kimlik\w* dogrulan|not verified|"
                     r"verification (is )?(required|not)|identity (is )?(not|required)|before (the )?identity)"),
    ("unknown_customer", r"(musteri\w* (bulunamadi|yok|kayitli degil|tanimsiz)|(customer|client)\w* (was )?"
                         r"(not found|unknown|does not exist)|unknown (customer|client))"),
    ("unknown_product", r"((kart|urun|hesap|product|card|account|loan)\w* (bulunamadi|yok|ait degil|tanimsiz|"
                        r"(was )?not found|unknown|does not belong)|unknown (product|card|account))"),
    ("format", r"(bicim|format|okunamayan|unreadable|cannot be read|parse)"),
    ("invalid_value", r"(gecersiz|invalid|izin verilen|allowed values|out of range|not allowed|must be)"),
]
CODE_RX = re.compile(r"^[A-Z]{1,6}[-_]?\d{1,4}$|^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$")
NONE_RX = re.compile(r"^(|[-—–]+|none|n/?a|null|yok|bos|gonderilmez|not sent|no reason|\(.*\))$")


def _clean(v):
    return re.sub(r"`|\*", "", str(v or "")).strip()


def error_codes_from_tables(tables):
    """-> ({kind: code}, reject_past_dates, [notes]). A table whose first column is codes (E001, ERR_12, ...) and
    whose longest column explains them."""
    codes, past, notes = {}, False, []
    for t in tables:
        rows = t.get("rows") or []
        if not rows or len(t.get("header") or []) < 2:
            continue
        h = t["header"]
        col = next((c for c in h if sum(1 for r in rows if CODE_RX.match(_clean(r.get(c)))) >= max(2, 0.6 * len(rows))), None)
        if not col:
            continue
        meaning = max((c for c in h if c != col), key=lambda c: sum(len(_clean(r.get(c))) for r in rows))
        for r in rows:
            code = _clean(r.get(col))
            text = re.sub(r"[^a-z0-9]+", " ", fold(r.get(meaning, "")).lower()).strip()   # parentheses kept
            if not CODE_RX.match(code):
                continue
            if re.search(r"(gecmis tarih|past date|in the past|date before)", text):
                past = True
            for kind, rx in ERROR_KIND_RULES:
                if re.search(rx, text):
                    if kind not in codes:
                        codes[kind] = code
                        notes.append(f"error code {code} -> {kind}")
                    break
    return codes, past, notes


def close_table_from_tables(tables, outcomes, reasons):
    """-> ({outcome: [reasons]} or {}, [notes]). A table with one column of outcome values and one of reason values;
    any other cell (a dash, 'not sent', empty) means the outcome takes no reason."""
    if not outcomes:
        return {}, []
    out, notes = {}, []
    oset, rset = set(outcomes), set(reasons or [])
    for t in tables:
        rows = t.get("rows") or []
        h = t.get("header") or []
        if len(rows) < 2 or len(h) < 2:
            continue
        count = lambda c, vals: sum(1 for r in rows if _clean(r.get(c)) in vals)        # noqa: E731
        ocol = max(h, key=lambda c: count(c, oset))
        if count(ocol, oset) < max(2, 0.6 * len(rows)):
            continue
        rcol = max((c for c in h if c != ocol), key=lambda c: count(c, rset)) if rset else None
        if not rcol or count(rcol, rset) == 0:
            continue
        for r in rows:
            o = _clean(r.get(ocol))
            if o not in oset:
                continue
            rv = _clean(r.get(rcol))
            lst = out.setdefault(o, [])
            if rv in rset and rv not in lst:
                lst.append(rv)
            elif rv not in rset and CODE_RX.match(rv):
                notes.append(f"close table: {o} lists reason {rv!r} outside the reason enum (ignored)")
        notes.append(f"close table from {t.get('source')}#{t.get('name')}")
    return out, notes


def apply_contract(config, paths):
    """Read the contract document(s) (or the whole case folder) and add error codes, the close table and the
    past-date rule to the config. -> [notes]."""
    tables = []
    for pth in paths or []:
        tables += [t for t in tbl.read_tables(pth) if not t.get("error") and "shaped" not in t]
    notes = []
    codes, past, n1 = error_codes_from_tables(tables)
    notes += n1
    if codes:
        config["error_codes"] = codes
        if "unknown_customer" in codes and config["statuses"].get("unknown_customer") == 404 \
                and not config.get("documents_404"):
            config["statuses"]["unknown_customer"] = 200      # the contract answers it with a code, not a 404
            notes.append("unknown customer: HTTP 200 + error code (the contract documents no 404)")
    close = op_of(config, "close")
    if close:
        of, rf = close["fields"].get("outcome"), close["fields"].get("reason")
        outcomes = close["request"].get(of, {}).get("enum") or []
        reasons = close["request"].get(rf, {}).get("enum") or []
        table, n2 = close_table_from_tables(tables, outcomes, reasons)
        notes += n2
        if table and not close.get("reasons_by_outcome"):
            close["reasons_by_outcome"] = table
            close["reasonless"] = sorted(set(close.get("reasonless") or []) | {o for o, rs in table.items() if not rs},
                                         key=outcomes.index)
    prom = op_of(config, "promise")
    if past and prom:
        prom["reject_past_dates"] = True
        notes.append("promise: a past date is refused (error table says so), against the customer's `now`")
    return notes


def identity_keys(config):
    """The identity attributes the verify operation(s) can ask about."""
    keys = []
    for op in config.get("ops") or []:
        if op.get("role") != "verify":
            continue
        sel = op["fields"].get("selector")
        new = list(op["request"].get(sel, {}).get("enum") or []) if sel else \
            list((op.get("identity_fields") or {}).values())
        keys += [k for k in new if k not in keys]
    return keys


def op_of(config, role):
    return next((o for o in config.get("ops") or [] if o.get("role") == role), None)


# ---------------------------------------------------------------------------------------------------- customers

def _targets(config):
    """-> {target: (kind, key, type)}; kind in customer|identity|product|account|variable."""
    t = {"customer_id": ("customer", "customer_id", "string")}
    for k in identity_keys(config):
        t["identity:" + k] = ("identity", k, "string")
    prod = config.get("products") or {}
    for k, typ in (prod.get("fields") or {}).items():
        t["product:" + k] = ("product", k, typ)
    acct = op_of(config, "account")
    for k, typ in ((acct or {}).get("account_fields") or {}).items():
        t["account:" + k] = ("account", k, typ)
    for v in VARIABLE_NAMES:
        t["variable:" + v] = ("variable", v, "string")
    return t


def _syn_group(n):
    for g in SYNONYMS:
        if n in g:
            return g
    return {n}


def map_columns(header, config, column_map=None):
    """-> ({column: target}, [unmapped column]). Exact name, then synonym group, then prefix match."""
    targets = _targets(config)
    cust_field = norm(config.get("customer_field") or "customer_id")
    out, used = {}, set()
    column_map = column_map or {}
    for col in header:
        if col in column_map and column_map[col] in targets:
            out[col] = column_map[col]
            used.add(column_map[col])
    order = ["customer", "identity", "product", "account", "variable"]
    tkeys = sorted(targets, key=lambda k: order.index(targets[k][0]))

    def key_names(tk):
        kind, key, _ = targets[tk]
        if kind == "customer":
            return {cust_field} | _syn_group("customer_id") | _syn_group(cust_field)
        return _syn_group(norm(key)) | {norm(key)}

    for stage in ("exact", "synonym", "prefix"):
        for col in header:
            if col in out:
                continue
            nc = norm(col)
            for tk in tkeys:
                if tk in used:
                    continue
                kind, key, _ = targets[tk]
                names = key_names(tk)
                hit = (stage == "exact" and nc == (cust_field if kind == "customer" else norm(key))) or \
                      (stage == "synonym" and nc in names) or \
                      (stage == "prefix" and any(len(n) >= 4 and (nc.startswith(n + "_") or nc.endswith("_" + n))
                                                 for n in names))
                if hit:
                    # a product and an account leaf can share a name: the product wins (rows are products)
                    out[col] = tk
                    used.add(tk)
                    break
    unmapped = [c for c in header if c not in out]
    return out, unmapped


def parse_number(s):
    """'1.234,56 TL' / '1,234.56' / '420' / '₺420,50' / '1.500' -> float or None. A lone separator followed by
    exactly three digits is a thousands separator (money is not written with three decimals)."""
    if s is None or isinstance(s, bool):
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = re.sub(r"[^\d,.\-]", "", str(s))
    if not re.search(r"\d", t):
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        parts = t.split(",")
        t = t.replace(",", ".") if len(parts) == 2 and len(parts[1]) != 3 else t.replace(",", "")
    elif t.count(".") > 1 or re.fullmatch(r"-?\d{1,3}\.\d{3}", t):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
          "september": 9, "october": 10, "november": 11, "december": 12, "ocak": 1, "subat": 2, "mart": 3,
          "nisan": 4, "mayis": 5, "haziran": 6, "temmuz": 7, "agustos": 8, "eylul": 9, "ekim": 10, "kasim": 11,
          "aralik": 12}


def parse_date(s):
    """A table cell -> 'YYYY-MM-DD' or None (ISO, D.M.YYYY, D/M/YYYY, '14 Mart 1988', '14 March 1988')."""
    t = fold(str(s or "")).strip().lower()
    m = re.fullmatch(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})(?:[ t].*)?", t)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.fullmatch(r"(\d{1,2})[-./](\d{1,2})[-./](\d{4})", t)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            m = re.fullmatch(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", t)
            if not m or m.group(2) not in MONTHS:
                return None
            d, mo, y = int(m.group(1)), MONTHS[m.group(2)], int(m.group(3))
    try:
        return datetime.date(y, mo, d).isoformat()
    except ValueError:
        return None


def _coerce(value, typ):
    if value is None:
        return None
    v = str(value).strip()
    if v == "" or v.lower() in ("-", "—", "null", "none", "yok"):
        return None
    if typ in ("number", "integer"):
        n = parse_number(v)
        if n is None:
            return v
        return int(n) if typ == "integer" and float(n).is_integer() else n
    if typ == "boolean":
        return v.lower() in ("true", "1", "yes", "evet", "var", "x")
    return v


def _fix_digits(customers, where, key):
    """Leading zeros lost in a spreadsheet: pad a digits-only column to the length its name states ("..._last4",
    "son4") or else to its most common length (ties: the longer)."""
    vals = []
    for c in customers:
        holders = c.get(where) if where == "products" else [c.get(where) or {}]
        for h in holders or []:
            v = h.get(key)
            if isinstance(v, str) and v.isdigit():
                vals.append(len(v))
    if not vals:
        return
    m = re.search(r"(?<!\d)([2-9]|1[0-2])(?!\d)", norm(key).replace("_", " "))
    m = m or re.search(r"[a-z]([2-9])$", norm(key))
    if m:
        common = int(m.group(1))
    else:
        common = max(set(vals), key=lambda n: (vals.count(n), n))
    for c in customers:
        holders = c.get(where) if where == "products" else [c.get(where) or {}]
        for h in holders or []:
            v = h.get(key)
            if isinstance(v, str) and v.isdigit() and len(v) < common:
                h[key] = v.zfill(common)


def customers_from_table(table, config, column_map=None):
    """-> (customers, warnings, unmapped). Rows are grouped by the customer column; product columns make products."""
    cmap, unmapped = map_columns(table["header"], config, column_map)
    targets = _targets(config)
    warnings = []
    id_col = next((c for c, t in cmap.items() if t == "customer_id"), None)
    if not id_col:
        return [], [f"{table['source']}#{table['name']}: no customer id column"], unmapped
    by_id, order = {}, []
    for row in table["rows"]:
        cid = row.get(id_col, "").strip()
        if not cid:
            continue
        if cid not in by_id:
            by_id[cid] = {"customer_id": cid, "identity": {}, "products": [], "account": {}, "variables": {}}
            order.append(cid)
        c = by_id[cid]
        prod = {}
        for col, tk in cmap.items():
            kind, key, typ = targets[tk]
            raw = row.get(col, "")
            if kind == "identity":
                val = raw.strip()
                d = parse_date(val) if re.search(r"\d", val) and re.search(r"[-./ ]", val) else None
                val = d or val
                if val and key not in c["identity"]:
                    c["identity"][key] = val
            elif kind == "product":
                val = _coerce(raw, typ)
                if val is not None:
                    prod[key] = val
            elif kind == "account":
                val = _coerce(raw, typ)
                if val is not None and key not in c["account"]:
                    c["account"][key] = val
            elif kind == "variable":
                if raw.strip() and key not in c["variables"]:
                    c["variables"][key] = raw.strip()
        if prod:
            c["products"].append(prod)
    customers = [by_id[i] for i in order]
    return customers, warnings, unmapped


def _shaped(data, config):
    """Customers already in the mock's shape (or the kit's case shape: id, variables, identity, products, faults)."""
    out = []
    ops_by_alias = {}
    for o in config.get("ops") or []:
        for alias in (o["name"], o["role"], FIXED.get(o["role"]), o["path"]):
            ops_by_alias[alias] = o["name"]
    for i, d in enumerate(data):
        var = dict(d.get("variables") or {})
        cid = d.get("customer_id") or var.pop("customer_id", None) or d.get("id") or "c%d" % (i + 1)
        plist = (config.get("products") or {}).get("list")
        prods = d.get("products") if isinstance(d.get("products"), list) else \
            (d.get(plist) if plist and isinstance(d.get(plist), list) else [])
        c = {"customer_id": str(cid), "identity": {k: str(v) for k, v in (d.get("identity") or {}).items()},
             "products": copy.deepcopy(prods), "account": copy.deepcopy(d.get("account") or {}),
             "variables": var}
        raw_faults = d.get("faults") or []
        if isinstance(raw_faults, dict):                    # {op: n} shorthand
            raw_faults = [{"op": k, "fail_first_n": v} for k, v in raw_faults.items()]
        faults = []
        for f in raw_faults:
            if not isinstance(f, dict):
                continue
            target = f.get("op") or f.get("tool") or f.get("role")
            if target in ops_by_alias:
                faults.append({**{k: v for k, v in f.items() if k not in ("tool", "role")}, "op": ops_by_alias[target]})
        if faults:
            c["faults"] = faults
        if d.get("max_wrong"):
            c["max_wrong"] = int(d["max_wrong"])
        out.append(c)
    return out


def _finish(customers, config):
    prod = config.get("products") or {}
    pid, prefix = prod.get("id") or "product_id", prod.get("id_prefix") or "p"
    for c in customers:
        for i, p in enumerate(c.get("products") or []):
            if p.get(pid) in (None, ""):
                p[pid] = p.pop("id", None) or "%s%d" % (prefix, i + 1)
            else:
                p[pid] = str(p[pid])
            # put the id first (readability of /ledger and get_account answers)
            items = [(pid, p[pid])] + [(k, v) for k, v in p.items() if k != pid]
            p.clear()
            p.update(items)
    for c in customers:
        for k, v in list((c.get("identity") or {}).items()):
            sv = str(v).strip()
            if re.fullmatch(r"\d{1,4}[-./]\d{1,2}[-./]\d{1,4}|\d{1,2} \w+ \d{4}", sv):
                iso = parse_date(sv)
                if iso:
                    c["identity"][k] = iso                  # the engine compares dates as ISO, any spoken format
    for key in identity_keys(config):
        _fix_digits(customers, "identity", key)
    for k, typ in (prod.get("fields") or {}).items():
        if typ == "string":
            _fix_digits(customers, "products", k)
    return customers


def load_customers(paths, config, *, column_map=None):
    """Files/folders -> (customers, warnings, unmapped columns per table)."""
    found, warnings, unmapped = [], [], {}
    for path in paths:
        for t in tbl.read_tables(path):
            if t.get("error"):
                warnings.append(f"{t['source']}: unreadable ({t['error']})")
                continue
            if "shaped" in t:
                found += _shaped(t["shaped"], config)
                continue
            cs, w, um = customers_from_table(t, config, column_map)
            if cs:
                found += cs
                if um:
                    unmapped[f"{t['source']}#{t['name']}"] = um
            if cs:
                warnings += w
    # several tables may describe the same customers (identity sheet + products sheet): merge by id
    merged, order = {}, []
    for c in found:
        cid = c["customer_id"]
        if cid not in merged:
            merged[cid] = c
            order.append(cid)
            continue
        m = merged[cid]
        for k in ("identity", "account", "variables"):
            for kk, vv in (c.get(k) or {}).items():
                m.setdefault(k, {}).setdefault(kk, vv)
        for p in c.get("products") or []:
            if p not in m.setdefault("products", []):
                m["products"].append(p)
        if c.get("faults"):
            m.setdefault("faults", []).extend(c["faults"])
    customers = _finish([merged[i] for i in order], config)
    if not customers:
        warnings.append("no customers found (no table with a customer id column)")
    return customers, warnings, unmapped


# ---------------------------------------------------------------------------------------------------- validation

def validate(config, customers):
    errs = []
    roles = [o.get("role") for o in config.get("ops") or []]
    for r in set(roles):
        if roles.count(r) > 1 and r not in ("verify", "stub"):
            errs.append(f"role {r} is bound to {roles.count(r)} operations")
    vs = [o for o in config.get("ops") or [] if o.get("role") == "verify"]
    if not vs:
        errs.append("no verify operation")
    for v in vs:
        if not v["fields"].get("selector") and not v.get("identity_fields"):
            errs.append(f"verify {v['path']}: neither a selector/answer pair nor identity fields")
        elif v["fields"].get("selector") and not v["fields"].get("answer"):
            errs.append(f"verify {v['path']}: selector field without an answer field")
    p = op_of(config, "promise")
    if p and "amount" not in p["fields"]:
        errs.append("promise: no amount field")
    if p and not (p["fields"].get("date") or p["fields"].get("datetime")):
        errs.append("promise: no date field")
    c = op_of(config, "close")
    if c and "outcome" not in c["fields"]:
        errs.append("close: no outcome field")
    if c:
        outcomes = c["request"].get(c["fields"].get("outcome", ""), {}).get("enum") or []
        reasons = c["request"].get(c["fields"].get("reason", ""), {}).get("enum") or []
        for o in c.get("reasonless") or []:
            if outcomes and o not in outcomes:
                errs.append(f"close: reasonless outcome {o!r} is not in the outcome enum")
        for o, rs in (c.get("reasons_by_outcome") or {}).items():
            if outcomes and o not in outcomes:
                errs.append(f"close: reasons_by_outcome names unknown outcome {o!r}")
            for r in rs or []:
                if reasons and r not in reasons:
                    errs.append(f"close: reason {r!r} for {o} is not in the reason enum")
    for o in config.get("ops") or []:
        if o.get("role") not in ROLES + ("stub",):
            errs.append(f"operation {o.get('path')}: unknown role {o.get('role')!r}")
        if not str(o.get("path", "")).startswith("/"):
            errs.append(f"operation {o.get('name')}: path must start with /")
    if not customers:
        errs.append("no customers")
    keys = identity_keys(config)
    seen = set()
    pid = (config.get("products") or {}).get("id") or "product_id"
    for cu in customers:
        cid = cu.get("customer_id")
        if not cid:
            errs.append("a customer without customer_id")
            continue
        if cid in seen:
            errs.append(f"customer {cid}: duplicate id")
        seen.add(cid)
        ident = cu.get("identity") or {}
        if not ident:
            errs.append(f"customer {cid}: no identity answers")
        for k, val in ident.items():
            if keys and k not in keys:
                errs.append(f"customer {cid}: identity key {k!r} is not one the verify operation asks ({', '.join(keys)})")
            if not str(val).strip():
                errs.append(f"customer {cid}: empty identity answer for {k}")
        ids = [str(x.get(pid)) for x in cu.get("products") or []]
        if len(ids) != len(set(ids)):
            errs.append(f"customer {cid}: duplicate product ids {ids}")
    return errs


def _soft_checks(config, customers):
    w = []
    keys = identity_keys(config)
    for k in keys:
        if customers and not any(k in (c.get("identity") or {}) for c in customers):
            w.append(f"identity key {k} is set for no customer")
    prod = config.get("products") or {}
    for c in customers:
        for p in c.get("products") or []:
            for k, typ in (prod.get("fields") or {}).items():
                if typ in ("number", "integer") and k in p and not isinstance(p[k], (int, float)):
                    w.append(f"customer {c['customer_id']}: product field {k}={p[k]!r} is not a number")
    return w


# ---------------------------------------------------------------------------------------------------- LLM gap filling

LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "operations": {"type": "array", "items": {"type": "object", "properties": {
            "method": {"type": "string"}, "path": {"type": "string"}, "role": {"type": "string", "enum": list(ROLES)}},
            "required": ["path", "role"]}},
        "columns": {"type": "array", "items": {"type": "object", "properties": {
            "column": {"type": "string"}, "target": {"type": "string"}}, "required": ["column", "target"]}},
        "reasonless": {"type": "array", "items": {"type": "string"}},
        "reasons_by_outcome": {"type": "object", "additionalProperties": {"type": "array", "items": {"type": "string"}}},
        "max_wrong": {"type": "integer"},
    },
    "required": ["operations", "columns"],
}


def llm_fill(doc, config, customer_paths, docs_text="", timeout_s=180):
    """One structured LLM call that proposes role/column/close-rule mappings; returns validated overrides."""
    from builder import llm
    ops = operations(doc)
    tables = []
    for pth in customer_paths:
        for t in tbl.read_tables(pth):
            if t.get("rows"):
                tables.append({"table": f"{t['source']}#{t['name']}", "header": t["header"], "sample": t["rows"][:3]})
    close = op_of(config, "close") or {}
    outcomes = close.get("request", {}).get(close.get("fields", {}).get("outcome", ""), {}).get("enum") or []
    prompt = json.dumps({
        "task": "Map a bank's service contract and test-customer tables onto a generic mock.",
        "roles": {"verify": "identity check", "account": "read the customer's debt/products",
                  "promise": "record a payment promise", "note": "record a note/reason", "callback": "book a callback",
                  "transfer": "hand over to a human/queue", "close": "end the call with an outcome"},
        "operations": [{"method": o["method"], "path": o["path"], "summary": o["summary"].strip(),
                        "request_fields": list(o["request"])} for o in ops],
        "current_roles": {o["role"]: o["path"] for o in config.get("ops") or []},
        "column_targets": sorted(_targets(config)),
        "tables": tables[:6],
        "close_outcomes": outcomes,
        "documents": docs_text[:30000],
        "answer": "operations: role per path (only paths that have a role). columns: target per column (only "
                  "columns that match a target). reasonless: outcomes that take no reason. reasons_by_outcome: the "
                  "allowed reasons per outcome if the documents give a table. max_wrong: wrong identity answers "
                  "allowed in total.",
    }, ensure_ascii=False)
    out = llm.call_json("mockgen.map", "You map API contracts to a mock configuration. Answer JSON only.", prompt,
                        LLM_SCHEMA, timeout_s=timeout_s)
    return validate_llm(out, ops, config)


def validate_llm(out, ops, config):
    """Keep only proposals that name real paths, real targets and enum values. -> overrides dict + rejected list."""
    paths = {(o["method"], o["path"]) for o in ops} | {(None, o["path"]) for o in ops}
    targets = set(_targets(config))
    close = op_of(config, "close") or {}
    outcomes = close.get("request", {}).get(close.get("fields", {}).get("outcome", ""), {}).get("enum") or []
    reasons = close.get("request", {}).get(close.get("fields", {}).get("reason", ""), {}).get("enum") or []
    res = {"role_overrides": {}, "column_map": {}, "reasonless": None, "reasons_by_outcome": None, "max_wrong": None,
           "rejected": []}
    for a in (out or {}).get("operations") or []:
        key = ((a.get("method") or "").upper() or None, a.get("path"))
        if a.get("role") in ROLES and (key in paths or (None, a.get("path")) in paths):
            res["role_overrides"][a["role"]] = a["path"]
        else:
            res["rejected"].append(f"operation {a}")
    for c in (out or {}).get("columns") or []:
        if c.get("target") in targets:
            res["column_map"][c.get("column")] = c["target"]
        else:
            res["rejected"].append(f"column {c}")
    rl = (out or {}).get("reasonless")
    if isinstance(rl, list) and all(isinstance(x, str) for x in rl):
        good = [x for x in rl if not outcomes or x in outcomes]
        res["reasonless"] = good
        res["rejected"] += [f"reasonless {x}" for x in rl if x not in good]
    rbo = (out or {}).get("reasons_by_outcome")
    if isinstance(rbo, dict) and rbo:
        clean = {}
        for o, rs in rbo.items():
            if (outcomes and o not in outcomes) or not isinstance(rs, list):
                res["rejected"].append(f"reasons_by_outcome {o}")
                continue
            clean[o] = [r for r in rs if isinstance(r, str) and (not reasons or r in reasons)]
        res["reasons_by_outcome"] = clean or None
    mw = (out or {}).get("max_wrong")
    if isinstance(mw, int) and 1 <= mw <= 10:
        res["max_wrong"] = mw
    return res


# ---------------------------------------------------------------------------------------------------- output

def write(out_dir, config, customers, doc):
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files = {"config.json": config, "customers.json": customers, "openapi.json": doc}
    paths = {}
    for name, data in files.items():
        p = out / name
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        paths[name] = str(p)
    return paths


def generate(openapi_path, customer_paths, out_dir, *, lang=None, max_wrong=None, reasonless=None,
             reasons_by_outcome=None, name=None, use_llm=False, docs=None, session=None, column_map=None,
             role_overrides=None, write_files=True, contract=None):
    doc, doc_path = parse_doc(openapi_path)
    config, warnings = build_config(doc, lang=lang, max_wrong=max_wrong, reasonless=reasonless,
                                    reasons_by_outcome=reasons_by_outcome, name=name, session=session,
                                    role_overrides=role_overrides)
    notes = apply_contract(config, contract) if contract else []
    customers, cw, unmapped = load_customers(customer_paths, config, column_map=column_map)
    warnings += cw
    llm_note = None
    if use_llm:
        docs_text = ""
        for d in docs or []:
            for t in tbl.read_tables(d) if pathlib.Path(d).suffix.lower() in (".xlsx", ".docx") else []:
                docs_text += "\n" + "\n".join(" | ".join(r.values()) for r in t["rows"])
            p = pathlib.Path(d)
            files = [p] if p.is_file() else sorted(x for x in p.rglob("*") if x.suffix.lower() in (".md", ".txt"))
            for f in files:
                if f.suffix.lower() in (".md", ".txt"):
                    docs_text += "\n=== " + f.name + " ===\n" + f.read_text(errors="replace")
        try:
            fill = llm_fill(doc, config, customer_paths, docs_text)
            llm_note = fill
            config, w2 = build_config(
                doc, lang=lang, max_wrong=max_wrong or fill["max_wrong"],
                reasonless=reasonless if reasonless is not None else fill["reasonless"],
                reasons_by_outcome=reasons_by_outcome or fill["reasons_by_outcome"], name=name, session=session,
                role_overrides={**fill["role_overrides"], **(role_overrides or {})})
            notes = apply_contract(config, contract) if contract else []
            customers, cw, unmapped = load_customers(customer_paths, config,
                                                     column_map={**fill["column_map"], **(column_map or {})})
            warnings = w2 + cw + [f"LLM proposal rejected: {r}" for r in fill["rejected"]]
        except Exception as e:                              # noqa: BLE001 - the rules' config stands
            warnings.append(f"LLM step failed, rule-based config kept: {e}")
    warnings += _soft_checks(config, customers)
    errors = validate(config, customers)
    paths = write(out_dir, config, customers, doc) if write_files and not errors else {}
    return {"openapi": str(doc_path), "config": config, "customers": customers, "warnings": warnings,
            "unmapped": unmapped, "errors": errors, "files": paths, "llm": llm_note, "notes": notes}


def summary(report):
    cfg = report["config"]
    lines = [f"openapi: {report['openapi']}", f"lang={cfg['lang']} customer_field={cfg['customer_field']} "
             f"max_wrong={cfg['max_wrong']} base_paths={cfg['base_paths']}"]
    for o in cfg["ops"]:
        lines.append(f"  {o['role']:<9} {o['method']} {o['path']}  fields={o['fields']}  response={o['response']}"
                     + (f"  reasonless={o.get('reasonless')}" if o["role"] == "close" else "")
                     + (f"  needs_verified" if o.get("needs_verified") else ""))
    lines.append(f"statuses: {cfg['statuses']}")
    lines.append(f"identity keys: {identity_keys(cfg)}; products: {cfg['products']}")
    lines.append(f"customers: {len(report['customers'])} " + ", ".join(c["customer_id"] for c in report["customers"][:20]))
    if cfg.get("error_codes"):
        lines.append(f"error codes: {cfg['error_codes']}")
    for n in report.get("notes") or []:
        lines.append(f"NOTE {n}")
    for t, cols in report["unmapped"].items():
        lines.append(f"UNMAPPED columns in {t}: {cols}")
    for w in report["warnings"]:
        lines.append(f"WARN {w}")
    for e in report["errors"]:
        lines.append(f"ERROR {e}")
    for n, p in report["files"].items():
        lines.append(f"wrote {p}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--openapi", required=True, help="contract OpenAPI file, or a folder holding one")
    ap.add_argument("--customers", nargs="+", required=True, help="test-customer table files or folders")
    ap.add_argument("--out", default=str(ROOT / "mock"))
    ap.add_argument("--name", default=None, help="service name shown at /health")
    ap.add_argument("--lang", choices=["en", "tr"], default=None)
    ap.add_argument("--max-wrong", type=int, default=None)
    ap.add_argument("--reasonless", default=None, help="comma list of outcomes that take no reason")
    ap.add_argument("--reasons", default=None, help="JSON file {outcome: [allowed reasons]}")
    ap.add_argument("--contract", nargs="*", default=[],
                    help="service-contract document(s) or the case folder: error-code and close tables")
    ap.add_argument("--columns", default=None, help="JSON file {column: target} to force column mappings")
    ap.add_argument("--roles", default=None, help="JSON file {role: path} to force operation roles")
    ap.add_argument("--session-key-field", action="append", default=[], help="body field that names one call")
    ap.add_argument("--session-key-header", action="append", default=[], help="header that names one call")
    ap.add_argument("--llm", action="store_true", help="let the LLM fill gaps (validated)")
    ap.add_argument("--docs", nargs="*", default=[], help="case documents for the LLM step (close-reason table)")
    ap.add_argument("--check", action="store_true", help="do not write files")
    a = ap.parse_args(argv)
    load = lambda p: json.loads(pathlib.Path(p).read_text()) if p else None          # noqa: E731
    session = {}
    if a.session_key_field:
        session["key_fields"] = a.session_key_field
    if a.session_key_header:
        session["key_headers"] = [h.lower() for h in a.session_key_header]
    report = generate(a.openapi, a.customers, a.out, lang=a.lang, max_wrong=a.max_wrong,
                      reasonless=[x for x in a.reasonless.split(",") if x] if a.reasonless is not None else None,
                      reasons_by_outcome=load(a.reasons), name=a.name, use_llm=a.llm, docs=a.docs,
                      session=session or None, column_map=load(a.columns), role_overrides=load(a.roles),
                      write_files=not a.check, contract=a.contract)
    print(summary(report))
    return 2 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
