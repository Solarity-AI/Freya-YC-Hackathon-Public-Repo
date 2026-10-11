"""Tests for builder/openapi_model.py (agent 3): kit catalog fixture, generic binding on mutated OpenAPIs, errors.

Edge cases covered (docs/edge-cases/EDGE-CASES.md): BRF-08 minor units, BRF-09/OPS-32 server URL, BRF-10 reshaped
verify, BRF-16 reason required for every outcome, BRF-85/OPS-33/OPS-50 operationId, $ref, allOf, 3.1 type arrays,
BRF-86 nested response envelope, OPS-27/OPS-28 YAML/BOM/comments, OPS-31 missing tool.
"""
import copy
import json
import pathlib

import pytest

from builder import openapi_model as om

ROOT = pathlib.Path(__file__).resolve().parent.parent
KIT_OA = ROOT / "kit" / "tools" / "openapi.json"


def kit_doc():
    return json.loads(KIT_OA.read_text())


def _req(doc, path):
    return doc["paths"][path]["post"]["requestBody"]["content"]["application/json"]["schema"]


def _res(doc, path):
    return doc["paths"][path]["post"]["responses"]["200"]["content"]["application/json"]["schema"]


def _rename(props, old, new, **changes):
    items = list(props.items())
    props.clear()
    for k, v in items:
        if k == old:
            v = dict(v)
            v.update(changes)
            props[new] = v
        else:
            props[k] = v


def _rename_req(doc, path, old, new, **changes):
    sch = _req(doc, path)
    _rename(sch["properties"], old, new, **changes)
    sch["required"] = [new if r == old else r for r in sch.get("required", [])]


OUTCOMES = {"promise": "kept", "paid": "settled", "transferred": "handed_over", "no_promise": "declined",
            "not_verified": "unverified", "not_reached": "unreached"}
QUEUES = {"restructuring": "plans", "general": "front_desk", "support": "care"}
NOTE_REASONS = {"refused": "ref", "hardship": "hard", "dispute": "disp", "paid": "pd", "service_error": "svc"}
ID_FIELDS = {"date_of_birth": "dob", "phone_last4": "tel4"}
HINTS = {"day_month_swapped": "dm_swap"}
TYPES = {"credit_card": "cc", "personal_loan": "pl", "car_loan": "cl"}


def mutated_doc():
    """Every field and enum renamed, new server and paths, operationIds instead of path tails."""
    d = kit_doc()
    d["servers"] = [{"url": "https://bank.example.test/{base}/", "variables": {"base": {"default": "api"}}}]
    new_paths = {}
    for p, item in d["paths"].items():
        item["post"]["operationId"] = p.strip("/")
        new_paths["/v2/ops" + p.replace("_", "-")] = item
    d["paths"] = new_paths

    def P(tool):
        return "/v2/ops/" + tool.replace("_", "-")
    for tool in ("verify_identity", "get_account", "create_promise", "add_note", "schedule_callback",
                 "transfer_to_agent", "close_call"):
        _rename_req(d, P(tool), "customer_id", "client_ref")
        rs = _res(d, P(tool))["properties"]
        _rename(rs, "ok", "success")
        _rename(rs, "error", "message")
    _rename_req(d, P("verify_identity"), "field", "question", enum=list(ID_FIELDS.values()))
    _rename_req(d, P("verify_identity"), "answer", "spoken_value")
    rs = _res(d, P("verify_identity"))["properties"]
    _rename(rs, "verified", "matched")
    _rename(rs, "wrong_answers_left", "attempts_remaining")
    _rename(rs, "all_verified", "all_passed")
    _rename(rs, "hint", "hint_code", enum=list(HINTS.values()))
    rs = _res(d, P("get_account"))["properties"]
    _rename(rs, "products", "accounts")
    it = rs["accounts"]["items"]["properties"]
    _rename(it, "product_id", "account_ref")
    _rename(it, "type", "kind", enum=list(TYPES.values()))
    _rename(it, "past_due", "amount_overdue")
    _rename(it, "days_late", "days_overdue")
    _rename_req(d, P("create_promise"), "product_id", "account_ref")
    _rename_req(d, P("create_promise"), "amount", "amount_cents", type="integer", description="Amount in cents.")
    _rename_req(d, P("create_promise"), "date", "pay_on")
    _rename(_res(d, P("create_promise"))["properties"], "promise_id", "promise_ref")
    _rename_req(d, P("add_note"), "product_id", "account_ref")
    _rename_req(d, P("add_note"), "reason", "reason_code", enum=list(NOTE_REASONS.values()))
    _rename_req(d, P("add_note"), "text", "comment")
    _rename_req(d, P("schedule_callback"), "date", "callback_date")
    _rename_req(d, P("schedule_callback"), "time", "callback_time")
    _rename_req(d, P("transfer_to_agent"), "queue", "team", enum=list(QUEUES.values()))
    _rename_req(d, P("close_call"), "outcome", "result", enum=list(OUTCOMES.values()))
    _rename_req(d, P("close_call"), "reason", "reason_text",
                description="Required for every outcome except kept and settled.")
    return d


# ------------------------------------------------------------------------------------------------ kit fixture

def test_kit_catalog_matches_fixture_field_by_field(catalog_kit, kit_openapi_path):
    cat = om.load(kit_openapi_path)
    assert set(cat) == set(catalog_kit)
    for k in catalog_kit:
        if k != "tools":
            assert cat[k] == catalog_kit[k], k
    assert list(cat["tools"]) == list(catalog_kit["tools"])
    for t, exp in catalog_kit["tools"].items():
        got = cat["tools"][t]
        assert set(got) == set(exp), t
        for key in exp:
            assert got[key] == exp[key], (t, key)


def test_kit_catalog_is_json_serialisable_and_deterministic(kit_openapi_path):
    a = om.dumps(om.load(kit_openapi_path))
    b = om.dumps(om.load(kit_openapi_path))
    assert a == b
    json.loads(a)


def test_build_catalog_does_not_mutate_input():
    d = kit_doc()
    before = json.dumps(d, sort_keys=True)
    om.build_catalog(d)
    assert json.dumps(d, sort_keys=True) == before


# ------------------------------------------------------------------------------------------------ detection / load

def test_is_openapi_file(tmp_path, kit_openapi_path):
    assert om.is_openapi_file(kit_openapi_path)
    other = tmp_path / "x.md"
    other.write_text("# a brief\n")
    assert not om.is_openapi_file(other)
    js = tmp_path / "notoa.json"
    js.write_text('{"a": 1}')
    assert not om.is_openapi_file(js)
    assert not om.is_openapi_file(tmp_path / "missing.json")
    any_ext = tmp_path / "tools.txt"                          # detected by content, any extension
    any_ext.write_text(KIT_OA.read_text())
    assert om.is_openapi_file(any_ext)


def test_load_rejects_non_openapi(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{"paths": {}}')
    with pytest.raises(om.CatalogError):
        om.load(p)
    with pytest.raises(om.CatalogError):
        om.load(tmp_path / "missing.json")


def test_load_bom_comments_trailing_commas(tmp_path):                       # OPS-28
    text = KIT_OA.read_text()
    text = text.replace('"openapi": "3.0.3",', '// tool API\n "openapi": "3.0.3", /* note */')
    text = text.replace('"required": [\n         "customer_id"\n        ]', '"required": [\n "customer_id",\n]')
    p = tmp_path / "tools.json"
    p.write_bytes(("﻿" + text).encode("utf-8"))
    cat = om.load(p)
    assert set(cat["tools"]) >= {"verify_identity", "close_call"}


def test_yaml_without_pyyaml_is_a_catalog_error(tmp_path):                  # OPS-27
    try:
        import yaml  # noqa: F401
        pytest.skip("PyYAML installed")
    except ImportError:
        pass
    p = tmp_path / "tools.yaml"
    p.write_text("openapi: 3.0.3\npaths: {}\n")
    with pytest.raises(om.CatalogError):
        om.load(p)
    assert not om.is_openapi_file(p)


# ------------------------------------------------------------------------------------------------ mutated OpenAPI

@pytest.fixture
def mcat():
    return om.build_catalog(mutated_doc(), "x")


def test_mutated_server_variables_and_paths(mcat):                          # BRF-09, OPS-32, OPS-33
    assert mcat["server"] == "https://bank.example.test/api"
    assert mcat["tools"]["verify_identity"]["url"] == "https://bank.example.test/api/v2/ops/verify-identity"
    assert mcat["tools"]["close_call"]["path"] == "/v2/ops/close-call"


def test_mutated_request_roles(mcat):
    t = mcat["tools"]
    assert t["verify_identity"]["roles"]["request"] == {"customer": "client_ref", "selector": "question",
                                                        "answer": "spoken_value"}
    assert t["create_promise"]["roles"]["request"] == {"customer": "client_ref", "product": "account_ref",
                                                       "amount": "amount_cents", "date": "pay_on"}
    assert t["add_note"]["roles"]["request"] == {"customer": "client_ref", "product": "account_ref",
                                                 "reason": "reason_code", "text": "comment"}
    assert t["schedule_callback"]["roles"]["request"] == {"customer": "client_ref", "date": "callback_date",
                                                          "time": "callback_time"}
    assert t["transfer_to_agent"]["roles"]["request"] == {"customer": "client_ref", "queue": "team"}
    assert t["close_call"]["roles"]["request"] == {"customer": "client_ref", "outcome": "result",
                                                   "reason": "reason_text"}


def test_mutated_response_and_item_roles(mcat):
    t = mcat["tools"]
    assert t["verify_identity"]["roles"]["response"] == {"s": "success", "err": "message", "verified": "matched",
                                                         "left": "attempts_remaining", "all": "all_passed",
                                                         "hint": "hint_code"}
    assert t["get_account"]["roles"]["response"] == {"s": "success", "err": "message", "products": "accounts"}
    assert t["get_account"]["roles"]["item"] == {"id": "account_ref", "type": "kind", "past_due": "amount_overdue",
                                                 "days_late": "days_overdue"}
    assert t["create_promise"]["roles"]["response"]["pid"] == "promise_ref"
    assert t["verify_identity"]["response"]["attempts_remaining"]["path"] == "data.attempts_remaining"


def test_mutated_enums_and_reasonless(mcat):
    e = mcat["enums"]
    assert e["identity_field"] == list(ID_FIELDS.values())
    assert e["hint"] == list(HINTS.values())
    assert e["product_type"] == list(TYPES.values())
    assert e["note_reason"] == list(NOTE_REASONS.values())
    assert e["queue"] == list(QUEUES.values())
    assert e["outcome"] == list(OUTCOMES.values())
    assert mcat["reasonless_outcomes_hint"] == ["kept", "settled"]


def test_minor_units_scale_and_wire_formats(mcat):                          # BRF-08, OPS-35
    cp = mcat["tools"]["create_promise"]["request"]
    assert cp["amount_cents"]["scale"] == 100 and cp["amount_cents"]["type"] == "integer"
    assert cp["pay_on"]["wire_format"] == "%Y-%m-%d"
    assert mcat["tools"]["schedule_callback"]["request"]["callback_time"]["wire_format"] == "%H:%M"
    # an answer field whose description mentions a date format is not a date field
    assert mcat["tools"]["verify_identity"]["request"]["spoken_value"]["wire_format"] == ""


def test_wire_format_variants():
    d = kit_doc()
    sch = _req(d, "/schedule_callback")["properties"]
    sch["date"] = {"type": "string", "description": "Callback day as DD/MM/YYYY"}
    sch["time"] = {"type": "string", "example": "14:30"}
    sch["at"] = {"type": "string", "format": "date-time"}
    cat = om.build_catalog(d)
    req = cat["tools"]["schedule_callback"]["request"]
    assert req["date"]["wire_format"] == "%d/%m/%Y"
    assert req["time"]["wire_format"] == "%H:%M"
    assert req["at"]["wire_format"] == "%Y-%m-%dT%H:%M:%S"
    assert cat["tools"]["schedule_callback"]["roles"]["request"]["datetime"] == "at"


def test_reason_required_for_every_outcome_gives_no_reasonless():           # BRF-16
    d = kit_doc()
    sch = _req(d, "/close_call")
    sch["required"] = ["customer_id", "outcome", "reason"]
    sch["properties"]["reason"]["description"] = "Always required."
    cat = om.build_catalog(d)
    assert cat["reasonless_outcomes_hint"] == []


def test_close_reason_enum_listed():
    d = kit_doc()
    _req(d, "/close_call")["properties"]["reason"]["enum"] = ["refused", "callback"]
    cat = om.build_catalog(d)
    assert cat["enums"]["close_reason"] == ["refused", "callback"]
    assert not any("no enum" in w for w in cat["warnings"])


# ------------------------------------------------------------------------------------------------ structural variants

def test_refs_allof_and_31_type_arrays():                                   # BRF-85, OPS-50
    d = kit_doc()
    d["openapi"] = "3.1.0"
    sch = _req(d, "/create_promise")
    d["components"] = {"schemas": {
        "Base": {"type": "object", "properties": {"customer_id": {"type": ["string", "null"]}},
                 "required": ["customer_id"]},
        "Promise": {"allOf": [{"$ref": "#/components/schemas/Base"},
                              {"type": "object", "properties": {k: v for k, v in sch["properties"].items()
                                                                if k != "customer_id"},
                               "required": ["product_id", "amount", "date"]}]},
        "Loop": {"$ref": "#/components/schemas/Loop"},
    }}
    d["paths"]["/create_promise"]["post"]["requestBody"]["content"]["application/json"]["schema"] = {
        "$ref": "#/components/schemas/Promise"}
    _req(d, "/add_note")["properties"]["text"] = {"$ref": "#/components/schemas/Loop"}
    cat = om.build_catalog(d)
    cp = cat["tools"]["create_promise"]
    assert cp["required"] == ["customer_id", "product_id", "amount", "date"]
    assert cp["request"]["customer_id"]["type"] == "string"
    assert cp["roles"]["request"]["amount"] == "amount"


def test_nested_response_envelope():                                        # BRF-86
    d = kit_doc()
    rs = _res(d, "/create_promise")
    inner = rs["properties"]
    rs["properties"] = {"result": {"type": "object", "properties": inner}}
    cat = om.build_catalog(d)
    cp = cat["tools"]["create_promise"]
    assert cp["roles"]["response"]["s"] == "ok"
    assert cp["response"]["ok"]["path"] == "data.result.ok"


def test_status_enum_success_predicate():
    d = kit_doc()
    rs = _res(d, "/add_note")["properties"]
    del rs["ok"]
    rs["status"] = {"type": "string", "enum": ["recorded", "rejected"]}
    cat = om.build_catalog(d)
    assert cat["tools"]["add_note"]["success"] == {"role": "s", "kind": "enum_in", "values": ["recorded"]}
    assert cat["tools"]["add_note"]["roles"]["response"]["s"] == "status"


def test_no_success_leaf_is_http_ok_no_error():
    d = kit_doc()
    del _res(d, "/transfer_to_agent")["properties"]["ok"]
    cat = om.build_catalog(d)
    assert cat["tools"]["transfer_to_agent"]["success"]["kind"] == "http_ok_no_error"
    assert any("transfer_to_agent" in w for w in cat["warnings"])


def test_per_field_identity_mode():                                         # BRF-10
    d = kit_doc()
    sch = _req(d, "/verify_identity")
    sch["properties"] = {"customer_id": {"type": "string"}, "birth_date": {"type": "string", "format": "date"},
                         "phone_digits": {"type": "string"}}
    sch["required"] = ["customer_id"]
    cat = om.build_catalog(d)
    assert cat["identity_mode"] == "per_field"
    assert "selector" not in cat["tools"]["verify_identity"]["roles"]["request"]


def test_missing_servers_warns_and_relative_url():
    d = kit_doc()
    del d["servers"]
    cat = om.build_catalog(d)
    assert cat["server"] == ""
    assert cat["tools"]["get_account"]["url"] == "/get_account"
    assert any("servers" in w for w in cat["warnings"])


def test_trailing_slash_server():
    d = kit_doc()
    d["servers"] = [{"url": "https://h.example/v9/"}]
    cat = om.build_catalog(d)
    assert cat["tools"]["close_call"]["url"] == "https://h.example/v9/close_call"


# ------------------------------------------------------------------------------------------------ errors

def test_missing_tool_raises():                                             # OPS-31
    d = kit_doc()
    del d["paths"]["/schedule_callback"]
    with pytest.raises(om.CatalogError, match="schedule_callback"):
        om.build_catalog(d)


def test_missing_required_role_raises():
    d = kit_doc()
    del _req(d, "/create_promise")["properties"]["amount"]
    with pytest.raises(om.CatalogError, match="amount"):
        om.build_catalog(d)


def test_missing_products_list_raises():
    d = kit_doc()
    del _res(d, "/get_account")["properties"]["products"]
    with pytest.raises(om.CatalogError, match="products"):
        om.build_catalog(d)


def test_selector_without_answer_raises():
    d = kit_doc()
    sch = _req(d, "/verify_identity")
    del sch["properties"]["answer"]                                   # two enum fields, no free answer field
    sch["properties"]["zzz"] = {"type": "string", "enum": ["x"]}
    sch["required"] = ["customer_id", "field"]
    with pytest.raises(om.CatalogError):
        om.build_catalog(d)


def test_non_mapping_raises():
    with pytest.raises(om.CatalogError):
        om.build_catalog(["not", "a", "mapping"])


def test_extra_tool_ignored_and_other_method():
    d = kit_doc()
    d["paths"]["/ping"] = {"get": {"summary": "health", "responses": {}}}
    item = d["paths"].pop("/get_account")
    d["paths"]["/get_account"] = {"put": item["post"]}
    cat = om.build_catalog(d)
    assert "ping" not in cat["tools"]
    assert cat["tools"]["get_account"]["method"] == "PUT"
