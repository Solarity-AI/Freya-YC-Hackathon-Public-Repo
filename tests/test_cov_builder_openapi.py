"""Coverage round (builder/openapi_model.py): schema resolution, wire formats, role binding fallbacks, swagger 2.0,
and every CatalogError branch. Docs are generic mutations of the kit OpenAPI (no brief values asserted)."""
import copy
import json
import pathlib
import sys

import pytest

from builder import openapi_model as om

ROOT = pathlib.Path(__file__).resolve().parent.parent
KIT_DOC = json.loads((ROOT / "kit" / "tools" / "openapi.json").read_text())


def doc():
    return copy.deepcopy(KIT_DOC)


def req(d, tool):
    return d["paths"]["/" + tool]["post"]["requestBody"]["content"]["application/json"]["schema"]


def res(d, tool):
    return d["paths"]["/" + tool]["post"]["responses"]["200"]["content"]["application/json"]["schema"]


# ================================================================================================ parsing

def test_parse_text_yaml_and_bad_yaml():
    assert om._parse_text("openapi: 3.0.0\npaths: {}\n") == {"openapi": "3.0.0", "paths": {}}
    assert om._parse_text("key: [unclosed\n  - x: y: z") is None


def test_parse_text_without_pyyaml_returns_none(monkeypatch):
    monkeypatch.setitem(sys.modules, "yaml", None)                   # import yaml -> ImportError
    assert om._parse_text("openapi: 3.0.0\n") is None
    assert om._parse_text('{"openapi": "3.1.0",}') == {"openapi": "3.1.0"}   # JSON paths still work


def test_load_unreadable_path(tmp_path):
    with pytest.raises(om.CatalogError, match="cannot read tool API file"):
        om.load(tmp_path)                                            # a directory


def test_is_openapi_file_yaml_and_swagger(tmp_path):
    p = tmp_path / "api.yaml"
    p.write_text("swagger: '2.0'\nhost: h\n")
    assert om.is_openapi_file(p) is True
    q = tmp_path / "brief.md"
    q.write_text("# A brief that mentions nothing")
    assert om.is_openapi_file(q) is False
    assert om.is_openapi_file(tmp_path / "missing.json") is False


# ================================================================================================ resolution

def test_resolve_ref_edge_cases():
    d = {"components": {"schemas": {"A": {"type": "string"}, "L": ["not", "a", "dict"]}}}
    assert om._resolve_ref(d, "http://elsewhere/x") == {}
    assert om._resolve_ref(d, 12) == {}
    assert om._resolve_ref(d, "#/components/schemas/Missing") == {}
    assert om._resolve_ref(d, "#/components/schemas/L") == {}
    assert om._resolve_ref(d, "#/components/schemas/A") == {"type": "string"}


def test_resolve_ref_with_siblings_cycles_depth_oneof_const():
    d = {"components": {"schemas": {
        "Amt": {"type": "number", "required": ["a"]},
        "Loop": {"$ref": "#/components/schemas/Loop"},
        "Obj": {"properties": {"x": {"type": "string"}}}}}}
    r = om._resolve(d, {"$ref": "#/components/schemas/Amt", "description": "money", "required": ["a", "b"]})
    assert r == {"type": "number", "required": ["a", "b"], "description": "money"}
    assert om._resolve(d, {"$ref": "#/components/schemas/Loop"}) == {}
    assert om._resolve(d, {"type": "string"}, depth=31) == {}
    assert om._resolve(d, "not a schema") == {}
    one = om._resolve(d, {"oneOf": [{"type": "null"}, {"$ref": "#/components/schemas/Obj"}], "description": "o"})
    assert one == {"description": "o", "properties": {"x": {"type": "string"}}, "type": "object"}
    nul = om._resolve(d, {"anyOf": [{"type": "null"}]})
    assert nul == {"anyOf": [{"type": "null"}]}                       # nothing non-null to take
    assert om._resolve(d, {"type": ["null"]}) == {"type": "string"}
    assert om._resolve(d, {"const": "fixed"}) == {"const": "fixed", "enum": ["fixed"]}
    arr = om._resolve(d, {"type": "array", "items": {"$ref": "#/components/schemas/Amt"}})
    assert arr["items"]["type"] == "number"


def test_json_schema_media_types_and_swagger_response():
    d = {"components": {"responses": {"R": {"content": {"application/json": {"schema": {"type": "object"}}}}}}}
    assert om._json_schema(d, {"content": {"application/problem+json": {"schema": {"type": "integer"}},
                                           "text/plain": {"schema": {"type": "string"}}}}) == {"type": "integer"}
    assert om._json_schema(d, {"content": {"text/plain": {"schema": {"type": "string"}}}}) == {"type": "string"}
    assert om._json_schema(d, {"description": "x", "schema": {"type": "boolean"}}) == {"type": "boolean"}
    assert om._json_schema(d, {"$ref": "#/components/responses/R"}) == {"type": "object"}
    assert om._json_schema(d, None) == {} and om._json_schema(d, {"description": "no body"}) == {}


# ================================================================================================ leaves

def test_scalar_helpers():
    assert om._s(None) == "" and om._s(True) == "true" and om._s(False) == "false"
    assert om._s({"b": 1, "a": [2]}) == '{"a": [2], "b": 1}' and om._s(3) == "3"
    assert om._type({"properties": {}}) == "object" and om._type({"items": {}}) == "array"
    assert om._type({}) == "string" and om._type({"type": "integer"}) == "integer"
    assert om._example({"examples": ["e1", "e2"]}) == "e1" and om._example({"examples": []}) == ""
    assert om._example({"example": 0}) == 0


@pytest.mark.parametrize("name,leaf,want", [
    ("slot", {"format": "time"}, "%H:%M"),
    ("when", {"description": "Local DD.MM.YYYY"}, "%d.%m.%Y"),
    ("due_day", {"pattern": r"^\d{4}-\d{2}-\d{2}$"}, "%Y-%m-%d"),
    ("at_time", {"pattern": "^[0-9]{2}:[0-9]{2}$"}, "%H:%M"),
    ("pay_date", {"example": "2026-01-31"}, "%Y-%m-%d"),
    ("pay_date", {"example": "31/01/2026"}, "%d/%m/%Y"),
    ("call_time", {"example": "9:30"}, "%H:%M"),
    ("pay_date", {}, ""),                                             # date-like name, nothing to go on
    ("amount", {"example": "2026-01-31"}, ""),                       # not date-like at all
])
def test_wire_format_fallbacks(name, leaf, want):
    full = {"format": "", "description": "", "pattern": "", "example": ""}
    full.update(leaf)
    assert om._wire_format(name, full) == want


def test_response_leaves_nested_envelope_does_not_override_top_level():
    rs = {"properties": {"ok": {"type": "boolean"},
                         "result": {"type": "object", "properties": {"ok": {"type": "string"},
                                                                     "ref": {"type": "string"}}}}}
    leaves = om._response_leaves(rs)
    assert leaves["ok"] == {"type": "boolean", "path": "data.ok", "enum": [], "description": ""}
    assert leaves["ref"]["path"] == "data.result.ref"


def test_pred_kinds():
    leaf = {"type": "string", "enum": [], "format": ""}
    assert om._pred("datetime", dict(leaf, format="date-time"), "x") is True
    assert om._pred("datetime", leaf, "pay_timestamp") is True
    assert om._pred("datetime", leaf, "pay_at") is False
    assert om._pred("not_time", dict(leaf, format="date-time"), "d") is False
    assert om._pred("no_enum", dict(leaf, enum=["a"]), "t") is False
    assert om._pred("mystery", leaf, "t") is True


# ================================================================================================ binding

def _leaf(**kw):
    base = {"type": "string", "required": False, "enum": [], "format": "", "pattern": "", "description": "",
            "min_length": 0, "max_length": 0, "example": "", "wire_format": "", "scale": 1}
    base.update(kw)
    return base


def test_bind_request_fallbacks_on_a_write_tool():
    r = om._bind_request("create_promise", {
        "who": _leaf(description="The customer reference."),       # description mentions the customer
        "account_no": _leaf(),                                      # product by name pattern
        "amount": _leaf(type="number"),                             # exact role name
        "total_sum": _leaf(type="number"),                          # amount pattern, role already bound
        "selector": _leaf(),                                        # exact identity role name: not on this tool
        "start": _leaf(description="Start, HH:MM"),                 # time by description
        "when": _leaf(format="date"),                               # date by format
    })
    assert r == {"customer": "who", "product": "account_no", "amount": "amount", "date": "when", "time": "start"}


def test_bind_request_numeric_fallback_amount():
    r = om._bind_request("create_promise", {"customer_id": _leaf(), "units": _leaf(type="number")})
    assert r == {"customer": "customer_id", "amount": "units"}


def test_bind_request_identity_tool_skips_value_roles_and_per_field_needs_one_field():
    r = om._bind_request("verify_identity", {"customer_id": _leaf(), "birth_date": _leaf(), "postcode": _leaf()})
    assert r == {"customer": "customer_id"}                          # two free fields: per-field, no answer
    r1 = om._bind_request("verify_identity", {"customer_id": _leaf(), "birth_date": _leaf()})
    assert r1 == {"customer": "customer_id", "answer": "birth_date"}


def test_bind_response_all_exact_and_take_conflicts():
    r = om._bind_response("verify_identity", {
        "ok": {"type": "boolean", "enum": []}, "success": {"type": "boolean", "enum": []},   # second s ignored
        "all": {"type": "boolean", "enum": []}})
    assert r == {"s": "ok", "all": "all"}


def test_bind_items_type_by_enum_name():
    r = om._bind_items("get_account", {"ref_id": {"type": "string", "enum": []},
                                       "product_kind_code": {"type": "string", "enum": ["a", "b"]},
                                       "arrears": {"type": "number", "enum": []}})
    assert r == {"id": "ref_id", "type": "product_kind_code", "past_due": "arrears"}


def test_success_predicates():
    resp = {"state": {"type": "string", "enum": ["queued", "failed"]}}
    assert om._success(resp, {"s": "state"}) == {"role": "s", "kind": "http_ok_no_error", "values": []}
    resp2 = {"state": {"type": "string", "enum": ["Done", "failed"]}}
    assert om._success(resp2, {"s": "state"}) == {"role": "s", "kind": "enum_in", "values": ["Done"]}


def test_reasonless_variants():
    tool = {"roles": {"request": {}}, "request": {}}
    assert om._reasonless(tool, ["a", "b"]) == ["a", "b"]             # no reason field at all
    tool = {"roles": {"request": {"reason": "r"}}, "request": {"r": _leaf(description="Why the call ended.")}}
    assert om._reasonless(tool, ["a", "b"]) == []                     # optional but no exception phrase
    tool["request"]["r"]["description"] = "Not needed for a or c."
    assert om._reasonless(tool, ["a", "b", "c"]) == ["a", "c"]


# ================================================================================================ catalog

def test_swagger2_document_binds_body_parameters_and_host():
    d = doc()
    sw = {"swagger": "2.0", "host": "bank.example", "basePath": "/v2/", "schemes": ["http"], "paths": {},
          "parameters": {}}
    for path, item in d["paths"].items():
        op = item["post"]
        name = path.strip("/")
        body = op["requestBody"]["content"]["application/json"]["schema"]
        ok = op["responses"]["200"]["content"]["application/json"]["schema"]
        sw["parameters"][name] = {"in": "body", "name": "body", "schema": body}
        sw["paths"][path] = {"post": {"operationId": name, "parameters": [{"$ref": "#/parameters/" + name},
                                                                          {"in": "header", "name": "X"}],
                                      "responses": {"201": {"description": "ok", "schema": ok}}}}
    cat = om.build_catalog(sw)
    assert cat["server"] == "http://bank.example/v2"
    assert cat["tools"]["create_promise"]["url"] == "http://bank.example/v2/create_promise"
    assert cat["tools"]["create_promise"]["roles"]["request"]["amount"] == "amount"
    assert "create_promise: path/query parameters are not bound" in cat["warnings"]
    assert cat["tools"]["verify_identity"]["roles"]["response"]["s"] == "ok"


def test_other_2xx_response_and_response_without_properties():
    d = doc()
    p = d["paths"]["/create_promise"]["post"]
    p["responses"] = {"203": p["responses"]["200"], "500": p["responses"]["500"]}
    n = d["paths"]["/add_note"]["post"]
    n["responses"]["200"]["content"]["application/json"]["schema"] = {"type": "string"}
    cat = om.build_catalog(d)
    assert cat["tools"]["create_promise"]["roles"]["response"]["s"] == "ok"
    assert cat["tools"]["add_note"]["response"] == {}
    assert cat["tools"]["add_note"]["success"]["kind"] == "http_ok_no_error"


def test_missing_product_type_gives_empty_enum():
    d = doc()
    items = res(d, "get_account")["properties"]["products"]["items"]["properties"]
    del items["type"]
    cat = om.build_catalog(d)
    assert cat["enums"]["product_type"] == [] and "type" not in cat["tools"]["get_account"]["roles"]["item"]


def test_identity_tool_without_answer_field_raises():
    d = doc()
    req(d, "verify_identity")["properties"] = {"customer_id": {"type": "string"}}
    with pytest.raises(om.CatalogError, match="verify_identity: no answer field"):
        om.build_catalog(d)


def test_callback_date_without_time_raises():
    d = doc()
    del req(d, "schedule_callback")["properties"]["time"]
    with pytest.raises(om.CatalogError, match="schedule_callback: no request field for role time"):
        om.build_catalog(d)


def test_per_field_identity_with_several_answer_fields():
    d = doc()
    req(d, "verify_identity")["properties"] = {"customer_id": {"type": "string"}, "birth_date": {"type": "string"},
                                               "postcode": {"type": "string"}}
    cat = om.build_catalog(d)
    assert cat["identity_mode"] == "per_field" and cat["enums"]["identity_field"] == []
    assert cat["tools"]["verify_identity"]["roles"]["request"] == {"customer": "customer_id"}
    assert "verify_identity has no selector field: per_field identity mode" in cat["warnings"]
