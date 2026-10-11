"""Minimal non-OpenAPI-style contracts: an undescribed account list, an unrecognised shared session key and a
minor-unit amount must bind (synthetic item leaves, customer role on the shared key, scale 100), never fail.
Every contract here is made up; the repairs only run where the binding used to fail (CatalogError)."""
import copy
import json
import pathlib

import pytest

from builder import contract as C
from builder import llm
from builder import openapi_model as OM
from builder.compiler import graph
from harness.mockbank import MockBank
from runtime import brain
from tools.mockgen import make_config as MC

MOCK = "http://mock.invalid"
STUB_CODE = "x = 1\n"
GOLDEN_A = pathlib.Path(__file__).resolve().parent / "golden" / "spec-a.json"


def _golden_a():
    return json.loads(GOLDEN_A.read_text())


def _op(fields, res, method="post", query=False, types=None):
    props = {f: {"type": (types or {}).get(f, "string")} for f in fields}
    op = {"operationId": "x", "responses": {"200": {"description": "ok", "content": {"application/json": {
        "schema": {"type": "object", "properties": res}}}}}}
    if query:
        op["parameters"] = [{"name": f, "in": "query", "schema": props[f]} for f in fields]
    else:
        op["requestBody"] = {"content": {"application/json": {"schema": {"type": "object", "properties": props}}}}
    return {method: op}


DESCRIBED = {"done": {"type": "boolean"}, "things": {"type": "array", "items": {"type": "object", "properties": {
    "thing_id": {"type": "string"}, "arrears": {"type": "number"}}}}}


def tiny_contract(account_res=None, amount="sum_in_cents", key="customer_id", amount_type="string"):
    """Seven made-up operations named after the tools. Defaults: a recognised customer key and an account answer
    whose list has no item schema (only the item repair is needed)."""
    ok = {"done": {"type": "boolean"}}
    return {"openapi": "3.0.3", "info": {"title": "t", "version": "1"}, "paths": {
        "/verify_identity": _op([key, "pin"], dict(ok, passed={"type": "boolean"})),
        "/get_account": _op([key], account_res if account_res is not None else
                            dict(ok, things={"type": "array"}), method="get", query=True),
        "/create_promise": _op([key, "product_id", amount, "date"], ok, types={amount: amount_type}),
        "/add_note": _op([key, "note", "reason"], ok),
        "/schedule_callback": _op([key, "date", "time"], ok),
        "/transfer_to_agent": _op([key, "queue"], ok),
        "/close_call": _op([key, "outcome"], ok),
    }}


def _build(doc, tmp_path=None):
    return C.build_catalog({"openapi": doc, "openapi_path": "t.json", "docs": []}, MOCK, tmp_path,
                           fetch=False, use_llm=False)


@pytest.fixture
def fake_llm():
    """Backend answering by purpose: {purpose: dict}; any other purpose fails the test."""
    prev = llm.set_backend(None)
    calls = []

    def install(answers):
        def backend(req):
            calls.append(req)
            if req["purpose"] not in answers:
                pytest.fail("unexpected LLM call: " + req["purpose"])
            return {"data": copy.deepcopy(answers[req["purpose"]])}
        llm.set_backend(backend)
        return calls
    yield install
    llm.set_backend(prev)


# ------------------------------------------------------------------------------------- undescribed list items

def test_undescribed_account_list_gets_synthetic_item_leaves(tmp_path):
    cat = _build(tiny_contract(), tmp_path)
    acct = cat["tools"]["get_account"]
    assert acct["roles"]["response"]["products"] == "things"
    assert acct["roles"]["item"] == {"id": "id", "type": "type", "past_due": "past_due", "days_late": "days_late"}
    assert acct["item_extras"]["floor"] == "minimum_due"
    syn = cat["contract"]["synthetic_fields"]
    assert {"get_account.things[].%s (item role %s)" % (n, r) for r, n in
            (("id", "id"), ("type", "type"), ("past_due", "past_due"), ("days_late", "days_late"),
             ("floor", "minimum_due"))} <= set(syn)
    on_disk = json.loads((tmp_path / "openapi.json").read_text())
    item_props = on_disk["paths"]["/get_account"]["post"]["responses"]["200"]["content"]["application/json"][
        "schema"]["properties"]["things"]["items"]["properties"]
    assert all(v.get("x-freya-synthetic") for v in item_props.values())
    assert set(item_props) == {"id", "type", "past_due", "days_late", "minimum_due"}


def test_partly_described_items_keep_real_leaves():
    cat = _build(tiny_contract(account_res=DESCRIBED))
    roles = cat["tools"]["get_account"]["roles"]["item"]
    assert roles == {"id": "thing_id", "past_due": "arrears"}          # binds today: nothing synthesised
    assert not any("things[]" in f for f in cat["contract"]["synthetic_fields"])


def test_items_missing_only_the_id_keep_the_described_debt_leaf():
    res = {"done": {"type": "boolean"}, "things": {"type": "array", "items": {"type": "object", "properties": {
        "arrears": {"type": "number"}}}}}
    cat = _build(tiny_contract(account_res=res))
    roles = cat["tools"]["get_account"]["roles"]["item"]
    assert roles["past_due"] == "arrears" and roles["id"] == "id"
    syn = cat["contract"]["synthetic_fields"]
    assert "get_account.things[].id (item role id)" in syn
    assert not any("past_due" in f for f in syn)


def test_missing_account_list_is_added():
    cat = _build(tiny_contract(account_res={"done": {"type": "boolean"}}))
    assert cat["tools"]["get_account"]["roles"]["response"]["products"] == "products"
    assert cat["tools"]["get_account"]["roles"]["item"]["past_due"] == "past_due"


def test_mock_serves_the_synthetic_item_leaves(tmp_path):
    _build(tiny_contract(), tmp_path)
    doc = json.loads((tmp_path / "openapi.json").read_text())
    op = next(o for o in MC.operations(doc) if o["x_tool"] == "get_account")
    assert set(op["response"]["things"]["items"]) == {"id", "type", "past_due", "days_late", "minimum_due"}


def test_no_account_operation_still_stubs_not_crash():
    doc = tiny_contract()
    doc["paths"].pop("/get_account")
    cat = _build(doc)
    assert cat["tools"]["get_account"].get("absent") is True


def test_method_list_contract_via_llm_derivation(fake_llm):
    """A contract that is a plain method list (fields named, no schemas): the derived operations carry an array
    response without items; the build binds it with synthetic item leaves instead of failing."""
    contract = {"title": "Made-up desk API", "methods": {
        "POST /check_caller": {"request": ["visit_ref", "pin_code"], "response": ["done", "matched"]},
        "GET /holdings": {"query": ["visit_ref"], "response": ["done", "lines"]},
        "POST /pledge": {"request": ["visit_ref", "line_ref", "total_pence", "pay_on"], "response": ["done"]},
        "POST /memo": {"request": ["visit_ref", "memo_text", "reason"], "response": ["done"]},
        "POST /ring_back": {"request": ["visit_ref", "pay_on", "slot"], "response": ["done"]},
        "POST /hand_off": {"request": ["visit_ref", "queue"], "response": ["done"]},
        "POST /wrap_up": {"request": ["visit_ref", "outcome"], "response": ["done"]}}}

    def f(name, typ="string", role=""):
        return {"name": name, "type": typ, "role": role}

    def op(name, method, path, tool, req, res):
        return {"name": name, "method": method, "path": path, "tool": tool, "request": req, "response": res,
                "success": {"field": "done", "values": ["true"]}}
    done = f("done", "boolean", "s")
    ops = {"operations": [
        op("check_caller", "POST", "/check_caller", "verify_identity", [f("visit_ref"), f("pin_code")],
           [done, f("matched", "boolean", "verified")]),
        op("holdings", "GET", "/holdings", "get_account", [f("visit_ref")], [done, f("lines", "array")]),
        op("pledge", "POST", "/pledge", "create_promise",
           [f("visit_ref"), f("line_ref", role="product"), f("total_pence", "integer", "amount"),
            dict(f("pay_on", role="date"), format="date")], [done]),
        op("memo", "POST", "/memo", "add_note", [f("visit_ref"), f("memo_text", role="text"),
                                                f("reason", role="reason")], [done]),
        op("ring_back", "POST", "/ring_back", "schedule_callback",
           [f("visit_ref"), dict(f("pay_on", role="date"), format="date"), f("slot", role="time")], [done]),
        op("hand_off", "POST", "/hand_off", "transfer_to_agent", [f("visit_ref"), f("queue", role="queue")], [done]),
        op("wrap_up", "POST", "/wrap_up", "close_call", [f("visit_ref"), f("outcome", role="outcome")], [done]),
    ]}
    text = json.dumps(contract)
    assert C.check_operations(ops, text)[0] == []                      # what the derivation would accept
    calls = fake_llm({"contract": ops})
    cat = C.build_catalog([{"name": "service_contract.json", "text": text, "kind": "service_contract"}], MOCK,
                          None, fetch=False)
    assert [c["purpose"] for c in calls] == ["contract"]
    acct = cat["tools"]["get_account"]
    assert acct["roles"]["response"]["products"] == "lines"
    assert {"id", "past_due"} <= set(acct["roles"]["item"])
    assert acct["method"] == "POST" and "visit_ref" in acct["request"]
    for name, tool in cat["tools"].items():
        assert tool["roles"]["request"]["customer"] == "visit_ref", name
    promise = cat["tools"]["create_promise"]
    assert promise["roles"]["request"]["amount"] == "total_pence"
    assert promise["request"]["total_pence"]["scale"] == 100
    assert promise["request"]["total_pence"]["type"] == "integer"


# ------------------------------------------------------------------------------------- shared session-style key

def test_shared_session_key_binds_to_customer_role():
    cat = _build(tiny_contract(key="visit_token", account_res=DESCRIBED))
    for name, tool in cat["tools"].items():
        assert tool["roles"]["request"]["customer"] == "visit_token", name
    assert cat["contract"]["synthetic_fields"] == []                   # the items were described: no item repair


def test_shared_session_key_is_baked_from_the_customer_id_call_variable():
    """The key goes out as {{customer_id}} on every api node and is never a model-filled body variable (the
    identity tool in per_field mode would otherwise ask the caller for it as an answer)."""
    cat = _build(tiny_contract(key="visit_token", account_res=DESCRIBED))
    wf, w = graph.compile_workflow(_golden_a(), cat, code=STUB_CODE)
    api = [n for n in wf["nodes"] if n in w["nodes"]]
    assert {w["nodes"][n]["tool"] for n in api} >= {"verify_identity", "get_account", "create_promise", "close_call"}
    for n in api:
        assert "visit_token" not in w["nodes"][n]["body"], n
        fn = wf["nodes"][n]["pre_actions"][0]["function"]
        body = fn["parameters"]["properties"]["body"]["properties"]
        assert body["visit_token"] == {"type": "string", "default": "{{customer_id}}"}, n
    verify = next(n for n in api if w["nodes"][n]["tool"] == "verify_identity")
    assert set(w["nodes"][verify]["body"]) == {"pin"}


def test_shared_session_key_inside_referenced_schemas(tmp_path):
    """$ref'd request bodies / schemas (one shared component) get the role on an inlined copy."""
    doc = tiny_contract(key="visit_token", account_res=DESCRIBED)
    doc["components"] = {"schemas": {"Visit": {"type": "string"}},
                         "requestBodies": {"Wrap": {"content": {"application/json": {"schema": {
                             "type": "object", "properties": {"visit_token": {"$ref": "#/components/schemas/Visit"},
                                                              "outcome": {"type": "string"}}}}}}}}
    doc["paths"]["/close_call"]["post"]["requestBody"] = {"$ref": "#/components/requestBodies/Wrap"}
    doc["paths"]["/add_note"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"][
        "visit_token"] = {"$ref": "#/components/schemas/Visit"}
    cat = _build(doc, tmp_path)
    for name, tool in cat["tools"].items():
        assert tool["roles"]["request"]["customer"] == "visit_token", name
    written = json.loads((tmp_path / "openapi.json").read_text())
    assert "x-freya-role" not in json.dumps(written["components"])        # inlined copies, shared parts untouched


def test_recognised_customer_key_wins_over_a_shared_session_key():
    """Control: a recognised customer key binds as before; the shared-key repair never runs."""
    doc = tiny_contract(account_res=DESCRIBED)
    for item in doc["paths"].values():
        for op in item.values():
            if op.get("requestBody"):
                op["requestBody"]["content"]["application/json"]["schema"]["properties"]["visit_token"] = \
                    {"type": "string"}
            else:
                op["parameters"].append({"name": "visit_token", "in": "query", "schema": {"type": "string"}})
    cat = _build(doc)
    for name, tool in cat["tools"].items():
        assert tool["roles"]["request"]["customer"] == "customer_id", name
        assert "visit_token" not in tool["roles"]["request"].values(), name
    assert cat["contract"]["synthetic_fields"] == []


def test_ambiguous_shared_keys_do_not_bind():
    doc = tiny_contract(key="visit_token", account_res=DESCRIBED)
    for item in doc["paths"].values():
        for op in item.values():
            body = op.get("requestBody")
            if body:
                body["content"]["application/json"]["schema"]["properties"]["shift_ref"] = {"type": "string"}
            else:
                op["parameters"].append({"name": "shift_ref", "in": "query", "schema": {"type": "string"}})
    with pytest.raises(OM.CatalogError, match="customer"):
        _build(doc)


# ------------------------------------------------------------------------------------- minor-unit amount

def test_minor_unit_amount_scale():
    cat = _build(tiny_contract(account_res=DESCRIBED, amount="sum_pence"))
    req = cat["tools"]["create_promise"]
    f = req["roles"]["request"]["amount"]
    assert f == "sum_pence" and req["request"][f]["scale"] == 100
    for name, desc in (("taksit_kurus", ""), ("tutar", "kuruş cinsinden"), ("valueMinor", ""),
                       ("total_penny", ""), ("tutarKuruş", "")):
        assert OM._scale(name, {"description": desc}) == 100, name
    for name, desc in (("amount", "in minor units"), ("sum_in_cents", ""), ("fee_cents", "")):  # matched before too
        assert OM._scale(name, {"description": desc}) == 100, name
    for name in ("amount", "minimum_amount", "total", "percent_paid", "centre_code"):
        assert OM._scale(name, {"description": ""}) == 1, name
    assert OM._scale("is_minor", {"type": "boolean", "description": ""}) == 1     # not an amount


def test_minor_unit_amount_goes_on_the_wire_as_an_integer():
    """'pledge_minor' (made up) -> scale 100: the wire spec carries it, the runtime sends whole minor units
    (no decimal point) and the mock stores major units; a fractional value for an integer field is refused."""
    cat = _build(tiny_contract(account_res=DESCRIBED, amount="pledge_minor", amount_type="integer"))
    leaf = cat["tools"]["create_promise"]["request"]["pledge_minor"]
    assert cat["tools"]["create_promise"]["roles"]["request"]["amount"] == "pledge_minor"
    assert (leaf["type"], leaf["scale"]) == ("integer", 100)
    wf, w = graph.compile_workflow(_golden_a(), cat, code=STUB_CODE)
    assert w["wire"]["create_promise.pledge_minor"] == {"type": "integer", "format": "", "scale": 100}
    wired = brain._b_wire_amount({"W": w}, "create_promise", "pledge_minor", 125050)
    assert wired == "125050" and int(wired) == 125050
    bank = MockBank(cat, {"products": [{"thing_id": "p1", "arrears": 2000}]})
    ok = bank._t_create_promise({"product_id": "p1", "pledge_minor": 125050, "date": "2030-01-02"})
    assert ok[1]["done"] is True and bank.promises[0]["amount"] == 1250.5
    bad = bank._t_create_promise({"product_id": "p1", "pledge_minor": 1250.5, "date": "2030-01-02"})
    assert bad[1]["done"] is False


# ------------------------------------------------------------------------------------- GET + query -> POST body

def test_get_with_query_fields_becomes_post_body(tmp_path):
    """The whole minimal shape at once: GET with a query key, a shared session-style key, an undescribed list."""
    cat = _build(tiny_contract(key="visit_token"), tmp_path)
    acct = cat["tools"]["get_account"]
    assert acct["method"] == "POST" and acct["url"] == MOCK + "/get_account"
    assert "visit_token" in acct["request"] and acct["roles"]["request"]["customer"] == "visit_token"
    assert {"id", "past_due"} <= set(acct["roles"]["item"])
    change = next(c for c in cat["contract"]["mock_shape_changes"] if c.startswith("GET "))
    assert change == "GET %s -> POST %s (parameters in the JSON body)" % (acct["path"], acct["path"])
    op = json.loads((tmp_path / "openapi.json").read_text())["paths"]["/get_account"]["post"]
    assert "parameters" not in op
    assert op["x-freya-original"] == {"method": "GET", "path": "/get_account"}
    body = op["requestBody"]["content"]["application/json"]["schema"]["properties"]
    assert set(body) == {"visit_token"} and body["visit_token"]["x-freya-role"] == "customer"
