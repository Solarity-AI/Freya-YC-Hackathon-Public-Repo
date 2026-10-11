"""tools/mockgen + mock/src/engine.js: the Cloudflare Worker bank mock and its config generator.

The engine runs under Node through tools/mockgen/harness.mjs (no wrangler, no network). Kit semantics are checked
against the kit OpenAPI + the 13 PUB customers (test fixture only); a made-up Turkish contract (paths, fields, codes
invented here) checks the generic, renamed-operation path; the rehearsal folder (testbed/tr-final) is used when present.
"""
import json
import pathlib
import shutil
import socket
import subprocess
import sys
import time
import zipfile

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.mockgen import make_config as mc        # noqa: E402
from tools.mockgen import tables as tbl            # noqa: E402

HARNESS = ROOT / "tools" / "mockgen" / "harness.mjs"
KIT_OPENAPI = ROOT / "kit" / "tools" / "openapi.json"
KIT_CASES = ROOT / "kit" / "public-test-set.json"
TR_REF = ROOT / "testbed" / "tr-final"
NODE = shutil.which("node")

needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed")


def run_mock(mock_dir, steps, **kw):
    spec = {"dir": str(mock_dir), "steps": steps, "do": kw.pop("do", True), "kv": kw.pop("kv", False), **kw}
    p = subprocess.run([NODE, str(HARNESS), "run"], input=json.dumps(spec), capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def post(path, body):
    return {"method": "POST", "path": path, "body": body}


def get(path):
    return {"method": "GET", "path": path}


@pytest.fixture(scope="module")
def kit_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("kitmock")
    rep = mc.generate(KIT_OPENAPI, [KIT_CASES], out)
    assert rep["errors"] == []
    return out


@pytest.fixture(scope="module")
def kit_cfg(kit_dir):
    return json.loads((kit_dir / "config.json").read_text())


def V(cid, field, answer):
    return post("/v1/verify_identity", {"customer_id": cid, "field": field, "answer": answer})


def verified(cid, dob, phone):
    return [V(cid, "date_of_birth", dob), V(cid, "phone_last4", phone)]


# ------------------------------------------------------------------------------------------------ config (kit)

def test_kit_config_roles_fields_and_rules(kit_cfg):
    ops = {o["role"]: o for o in kit_cfg["ops"]}
    assert list(ops) == ["verify", "account", "promise", "note", "callback", "transfer", "close"]
    assert ops["verify"]["fields"] == {"customer": "customer_id", "selector": "field", "answer": "answer"}
    assert ops["verify"]["response"]["left"] == "wrong_answers_left" and ops["verify"]["hint_value"] == "day_month_swapped"
    assert ops["promise"]["fields"]["product"] == "product_id" and ops["promise"]["one_per"] == "product"
    assert ops["promise"]["request"]["date"]["wire_format"] == "%Y-%m-%d"
    assert ops["close"]["reasonless"] == ["promise", "paid"] and ops["close"]["reason_required"] is True
    assert ops["account"]["needs_verified"] and ops["promise"]["needs_verified"]
    assert not ops["note"]["needs_verified"] and not ops["callback"]["needs_verified"]
    assert kit_cfg["base_paths"] == ["/v1"] and kit_cfg["lang"] == "en" and kit_cfg["max_wrong"] == 3
    assert kit_cfg["statuses"]["unknown_customer"] == 404 and kit_cfg["statuses"]["invalid"] == 200
    assert mc.identity_keys(kit_cfg) == ["date_of_birth", "phone_last4"]


def test_kit_customers_shape(kit_dir):
    cs = {c["customer_id"]: c for c in json.loads((kit_dir / "customers.json").read_text())}
    assert len(cs) == 13
    assert cs["PUB-02"]["identity"]["phone_last4"] == "0358"            # leading zero kept
    assert [p["product_id"] for p in cs["PUB-11"]["products"]] == ["p1", "p2", "p3"]
    assert cs["PUB-10"]["faults"] == [{"fail_first_n": 1, "op": "create_promise"}]
    assert cs["PUB-01"]["variables"]["first_name"] == "Daniel"


# ------------------------------------------------------------------------------------------------ engine (kit)

@needs_node
def test_health_openapi_cors_and_routing(kit_dir):
    r = run_mock(kit_dir, [get("/health"), get("/openapi.json"), get("/v1/openapi.json"),
                           {"method": "OPTIONS", "path": "/v1/close_call", "want_headers": True},
                           post("/nope", {}), {"method": "POST", "path": "/v1/get_account", "raw": "{not json"},
                           get("/customers")])
    h = r[0]["body"]
    assert h["ok"] and h["customers"] == 13 and len(h["operations"]) == 7 and h["storage"] == "durable_object"
    assert r[1]["body"]["servers"] == [{"url": "https://mock.test"}]
    assert r[2]["body"]["servers"] == [{"url": "https://mock.test/v1"}]
    assert r[3]["status"] == 204 and r[3]["headers"]["access-control-allow-origin"] == "*"
    assert r[4]["status"] == 404
    assert r[5]["status"] == 400 and r[5]["body"]["ok"] is False
    assert len(r[6]["body"]["customers"]) == 13


@needs_node
def test_identity_gate_and_happy_path(kit_dir):
    r = run_mock(kit_dir, [post("/v1/get_account", {"customer_id": "PUB-01"}),
                           post("/v1/create_promise", {"customer_id": "PUB-01", "product_id": "p1", "amount": 1,
                                                       "date": "2026-10-14"})]
                 + verified("PUB-01", "1988-03-14", "4471")
                 + [post("/get_account", {"customer_id": "PUB-01"}), get("/ledger/PUB-01")])
    assert r[0]["body"] == {"ok": False, "error": "identity not verified"}
    assert r[1]["body"] == {"ok": False, "error": "identity not verified"}
    assert r[2]["body"] == {"ok": True, "verified": True, "wrong_answers_left": 3, "all_verified": False}
    assert r[3]["body"]["all_verified"] is True
    prods = r[4]["body"]["products"]
    assert prods == [{"product_id": "p1", "type": "credit_card", "card_last4": "4821", "past_due": 420,
                      "days_late": 6, "minimum_payment": 126}]
    led = r[5]["body"]
    assert [c["tool"] for c in led["calls"]] == ["get_account", "create_promise", "verify_identity",
                                                  "verify_identity", "get_account"]
    assert led["verified"] == {"date_of_birth": True, "phone_last4": True}


@needs_node
def test_day_month_swap_hint_unreadable_and_lenient_dates(kit_dir):
    r = run_mock(kit_dir, [V("PUB-02", "date_of_birth", "1979-02-11"),      # swapped -> hint, not counted
                           V("PUB-02", "date_of_birth", "garbage"),         # unreadable, not counted
                           V("PUB-02", "date_of_birth", "2 November 1979"),
                           V("PUB-01", "date_of_birth", "14 Mart 1988"),
                           V("PUB-01", "date_of_birth", "14.03.1988")])
    assert r[0]["body"] == {"ok": True, "verified": False, "wrong_answers_left": 3, "all_verified": False,
                            "hint": "day_month_swapped"}
    assert r[1]["body"]["ok"] is False and r[1]["body"]["wrong_answers_left"] == 3
    assert r[2]["body"]["verified"] is True
    assert r[3]["body"]["verified"] is True and r[4]["body"]["verified"] is True


@needs_node
def test_wrong_answers_lockout(kit_dir):
    r = run_mock(kit_dir, [V("PUB-12", "phone_last4", "1111"), V("PUB-12", "phone_last4", "2222"),
                           V("PUB-12", "date_of_birth", "1950-01-01"),
                           V("PUB-12", "phone_last4", "1111"), get("/ledger/PUB-12")])
    assert r[0]["body"] == {"ok": True, "verified": False, "wrong_answers_left": 2, "all_verified": False}
    assert r[1]["body"]["wrong_answers_left"] == 1
    assert r[2]["body"] == {"ok": False, "error": "too many wrong answers", "verified": False,
                            "wrong_answers_left": 0, "all_verified": False}
    assert r[3]["body"]["ok"] is False and "over" in r[3]["body"]["error"]
    assert r[4]["body"]["wrong"] == 3


@needs_node
def test_digits_wrong_length_not_counted_and_reverify_omits_all(kit_dir):
    r = run_mock(kit_dir, [V("PUB-02", "phone_last4", "358"), V("PUB-02", "phone_last4", "03 58"),
                           V("PUB-02", "phone_last4", "0358"), V("PUB-02", "field_x", "1")])
    assert r[0]["body"] == {"ok": False, "error": "unreadable answer", "verified": False, "wrong_answers_left": 3}
    assert r[1]["body"]["verified"] is True and "all_verified" in r[1]["body"]
    assert "all_verified" not in r[2]["body"]                              # re-verify of a verified field
    assert r[3]["body"] == {"ok": False, "error": "unknown field"}


@needs_node
def test_promise_rules(kit_dir):
    base = {"customer_id": "PUB-11"}
    steps = verified("PUB-11", "1987-06-03", "2288") + [
        post("/v1/create_promise", {**base, "product_id": "p9", "amount": 10, "date": "2026-10-15"}),
        post("/v1/create_promise", {**base, "product_id": "p1", "amount": 10, "date": "15/10/2026"}),
        post("/v1/create_promise", {**base, "product_id": "p1", "amount": "abc", "date": "2026-10-15"}),
        post("/v1/create_promise", {**base, "product_id": "p1", "amount": 0, "date": "2026-10-15"}),
        post("/v1/create_promise", {**base, "product_id": "p1", "amount": "220", "date": "2026-10-15"}),
        post("/v1/create_promise", {**base, "product_id": "p1", "amount": 220, "date": "2026-10-16"}),
        post("/v1/create_promise", {**base, "product_id": "p2", "amount": 99999, "date": "2026-02-30"}),
        post("/v1/create_promise", {**base, "product_id": "p2", "amount": 109.5}),
        post("/v1/create_promise", {**base, "product_id": "p2", "amount": 109.5, "date": "2026-10-20"}),
        get("/ledger/PUB-11")]
    r = run_mock(kit_dir, steps)[2:]
    assert r[0]["body"] == {"ok": False, "error": "unknown product_id"}
    assert r[1]["body"] == {"ok": False, "error": "date must be YYYY-MM-DD"}
    assert r[2]["body"] == {"ok": False, "error": "amount must be a number"}
    assert r[3]["body"]["ok"] is False and "more than zero" in r[3]["body"]["error"]
    assert r[4]["body"] == {"ok": True, "promise_id": "pr1"}
    assert r[5]["body"] == {"ok": False, "error": "this product already has a promise"}
    assert r[6]["body"]["error"] == "date must be YYYY-MM-DD"
    assert r[7]["body"] == {"ok": False, "error": "missing date"}
    assert r[8]["body"] == {"ok": True, "promise_id": "pr2"}
    proms = [(p["product_id"], p["amount"], p["date"], p["type"]) for p in r[9]["body"]["promises"]]
    assert proms == [("p1", 220, "2026-10-15", "credit_card"), ("p2", 109.5, "2026-10-20", "personal_loan")]


@needs_node
def test_note_callback_transfer_not_gated_and_validated(kit_dir):
    c = {"customer_id": "PUB-02"}
    r = run_mock(kit_dir, [post("/v1/add_note", {**c, "product_id": "p1", "reason": "angry"}),
                           post("/v1/add_note", {**c, "product_id": "p7", "reason": "paid"}),
                           post("/v1/add_note", {**c, "product_id": "p1", "reason": "paid", "text": "t"}),
                           post("/v1/schedule_callback", {**c, "date": "2026-10-15", "time": "11am"}),
                           post("/v1/schedule_callback", {**c, "date": "2026-10-15", "time": "9:30"}),
                           post("/v1/schedule_callback", {**c, "date": "2026-10-15", "time": "11:00"}),
                           post("/v1/transfer_to_agent", {**c, "queue": "boss"}),
                           post("/v1/transfer_to_agent", {**c, "queue": "general"}),
                           get("/ledger/PUB-02")])
    assert r[0]["body"] == {"ok": False, "error": "unknown reason"}
    assert r[1]["body"] == {"ok": False, "error": "unknown product_id"}
    assert r[2]["body"] == {"ok": True}
    assert r[3]["body"] == {"ok": False, "error": "date must be YYYY-MM-DD and time HH:MM"}
    assert r[4]["body"]["ok"] is False
    assert r[5]["body"] == {"ok": True}
    assert r[6]["body"] == {"ok": False, "error": "unknown queue"}
    assert r[7]["body"] == {"ok": True}
    led = r[8]["body"]
    assert [(n["product_id"], n["reason"], n["text"]) for n in led["notes"]] == [("p1", "paid", "t")]
    assert [(x["date"], x["time"]) for x in led["callbacks"]] == [("2026-10-15", "11:00")]
    assert [x["queue"] for x in led["transfers"]] == ["general"]


@needs_node
def test_close_rules_and_single_use(kit_dir):
    c = {"customer_id": "PUB-03"}
    r = run_mock(kit_dir, [post("/v1/close_call", {**c, "outcome": "no_contact"}),
                           post("/v1/close_call", {**c, "outcome": "no_promise"}),
                           post("/v1/close_call", {**c, "outcome": "promise", "reason": "whatever"}),
                           post("/v1/close_call", {**c, "outcome": "promise"}),
                           post("/v1/schedule_callback", {**c, "date": "2026-10-15", "time": "11:00"}),
                           get("/ledger/PUB-03")])
    assert r[0]["body"] == {"ok": False, "error": "unknown outcome"}
    assert r[1]["body"] == {"ok": False, "error": "a reason is required for outcome no_promise"}
    assert r[2]["body"] == {"ok": True}
    assert r[3]["body"] == {"ok": False, "error": "the call is already closed"}
    assert r[4]["body"] == {"ok": False, "error": "the call is already closed"}
    led = r[5]["body"]
    assert led["outcome"] == "promise" and led["reason"] is None and led["closed"] is True
    assert led["callbacks"] == [] and led["calls"][-1]["tool"] == "schedule_callback"


@needs_node
def test_fault_injection_pub10_and_admin_fault(kit_dir):
    c = {"customer_id": "PUB-10"}
    body = {**c, "product_id": "p1", "amount": 365, "date": "2026-10-14"}
    r = run_mock(kit_dir, verified("PUB-10", "1989-02-23", "9904") + [
        post("/v1/create_promise", body), post("/v1/create_promise", body), get("/ledger/PUB-10"),
        post("/admin/fault/PUB-01", {"op": "transfer_to_agent", "fail_first_n": 1, "mode": "ok_false"}),
        post("/v1/transfer_to_agent", {"customer_id": "PUB-01", "queue": "general"}),
        post("/v1/transfer_to_agent", {"customer_id": "PUB-01", "queue": "general"})])[2:]
    assert r[0]["status"] == 500 and r[0]["body"] == {"ok": False, "error": "the service failed"}
    assert r[1]["body"] == {"ok": True, "promise_id": "pr1"}
    led = r[2]["body"]
    assert len(led["promises"]) == 1 and led["failures"] == {"create_promise": 1}
    assert r[3]["body"]["ok"] is True
    assert r[4]["status"] == 200 and r[4]["body"] == {"ok": False, "error": "the service failed"}
    assert r[5]["body"] == {"ok": True}


@needs_node
def test_unknown_customer_not_logged_and_never_crashes(kit_dir):
    r = run_mock(kit_dir, [post("/v1/verify_identity", {"customer_id": "nobody", "field": "date_of_birth",
                                                        "answer": "x"}),
                           post("/v1/get_account", {}),
                           post("/v1/verify_identity", {"customer_id": 12, "field": None, "answer": None}),
                           {"method": "POST", "path": "/v1/get_account", "raw": "[1,2]"},
                           post("/v1/create_promise", {"customer_id": "PUB-01", "product_id": {"x": 1},
                                                       "amount": [1], "date": 5}),
                           get("/ledger/nobody")])
    assert r[0]["status"] == 404 and r[0]["body"] == {"ok": False, "error": "unknown customer_id"}
    assert r[1]["status"] == 404 and r[2]["status"] == 404 and r[3]["status"] == 404
    assert r[4]["status"] == 200 and r[4]["body"]["ok"] is False
    assert r[5]["body"]["calls"] == []
    assert all(x["status"] != 500 for x in r)


@needs_node
def test_sessions_roll_over_between_calls(kit_dir):
    c = {"customer_id": "PUB-01"}
    close = post("/v1/close_call", {**c, "outcome": "promise"})
    r = run_mock(kit_dir, verified("PUB-01", "1988-03-14", "4471") + [
        close,
        post("/v1/get_account", c),                              # same call, after close: refused
        V("PUB-01", "date_of_birth", "1988-03-14"),              # a new call starts with the identity check
        post("/v1/get_account", c),                              # new session: not verified yet
        post("/v1/close_call", {**c, "outcome": "not_verified", "reason": "failed"}),
        {"advance_s": 20},
        post("/v1/transfer_to_agent", {**c, "queue": "general"}),  # closed + grace over: a third call
        {"advance_s": 300},
        post("/v1/transfer_to_agent", {**c, "queue": "support"}),  # idle: a fourth call
        get("/ledger/PUB-01")])
    assert r[3]["body"]["error"] == "the call is already closed"
    assert r[4]["body"]["verified"] is True
    assert r[5]["body"]["error"] == "identity not verified"
    assert r[6]["body"] == {"ok": True}
    assert r[8]["body"] == {"ok": True} and r[10]["body"] == {"ok": True}
    led = r[11]["body"]
    assert led["session"] == 4 and [x["queue"] for x in led["transfers"]] == ["support"]
    assert [h["session"] for h in led["history"]] == [1, 2, 3]
    assert led["history"][0]["outcome"] == "promise" and led["history"][1]["reason"] == "failed"


@needs_node
def test_reset_endpoints_and_admin_token(kit_dir):
    c = {"customer_id": "PUB-04"}
    r = run_mock(kit_dir, [post("/v1/transfer_to_agent", {**c, "queue": "general"}),
                           post("/reset/PUB-04", {}), get("/ledger/PUB-04"),
                           post("/v1/transfer_to_agent", {**c, "queue": "general"}),
                           post("/reset", {}), get("/ledger/PUB-04")])
    assert r[1]["body"] == {"ok": True, "customer_id": "PUB-04"}
    assert r[2]["body"]["calls"] == [] and r[5]["body"]["calls"] == []
    assert r[4]["body"]["ok"] is True
    r = run_mock(kit_dir, [post("/reset/PUB-04", {}),
                           {"method": "POST", "path": "/reset/PUB-04", "headers": {"x-admin-token": "s3"}}],
                 admin_token="s3")
    assert r[0]["status"] == 401 and r[1]["status"] == 200


@needs_node
def test_kv_persists_across_isolates_and_kv_failure_falls_back(kit_dir):
    steps = verified("PUB-01", "1988-03-14", "4471") + [{"reset_memory": True},
                                                        post("/v1/get_account", {"customer_id": "PUB-01"})]
    assert run_mock(kit_dir, steps, do=False, kv=True)[3]["body"]["ok"] is True   # KV carried the session
    assert run_mock(kit_dir, steps, do=False, kv=False)[3]["body"]["ok"] is False  # memory only: a new isolate forgets
    assert run_mock(kit_dir, steps, do=True)[3]["body"]["ok"] is True          # the Durable Object carried it
    r = run_mock(kit_dir, verified("PUB-01", "1988-03-14", "4471") + [
        post("/v1/get_account", {"customer_id": "PUB-01"}), get("/health")], do=False, kv_fail=True)
    assert r[2]["body"]["ok"] is True
    assert r[3]["body"]["kv_errors"] > 0


@needs_node
def test_durable_object_ledger_is_per_customer_and_survives_isolates(kit_dir):
    """Production storage: the Worker forwards each customer's requests to that customer's Durable Object."""
    c1 = {"customer_id": "PUB-01"}
    r = run_mock(kit_dir, [
        post("/v1/get_account", c1),                                              # 0 refused before verification
        *verified("PUB-01", "1988-03-14", "4471"),                                # 1, 2
        {"reset_memory": True},                                                   # 3 a fresh Worker isolate
        post("/v1/get_account", c1),                                              # 4 ok: the DO kept the session
        post("/v1/get_account", {"customer_id": "PUB-04"}),                       # 5 another customer: own DO, refused
        post("/v1/get_account", {"customer_id": "NOPE-9"}),                       # 6 unknown customer answers locally
        get("/ledger/PUB-01"),                                                    # 7
        post("/reset", {}),                                                       # 8 fans out to every customer's DO
        post("/v1/get_account", c1),                                              # 9 refused again after the reset
        get("/ledger/NOPE-9"),                                                    # 10 unknown id: empty, no DO
        get("/health"),                                                           # 11
    ], do=True)
    assert r[0]["body"]["ok"] is False and r[1]["body"]["ok"] is True and r[2]["body"]["ok"] is True
    assert r[4]["body"]["ok"] is True and r[5]["body"]["ok"] is False
    assert r[6]["body"]["ok"] is False
    assert len(r[7]["body"]["calls"]) == 4
    assert r[8]["body"]["ok"] is True and r[8]["body"]["reset"] == 13
    assert r[9]["body"]["ok"] is False
    assert r[10]["body"]["calls"] == []
    assert r[11]["body"]["storage"] == "durable_object"


@needs_node
def test_session_key_header_separates_parallel_calls(tmp_path, kit_dir):
    cfg = json.loads((kit_dir / "config.json").read_text())
    cfg["session"]["key_headers"] = ["x-call-id"]
    for f in ("customers.json", "openapi.json"):
        shutil.copy(kit_dir / f, tmp_path / f)
    (tmp_path / "config.json").write_text(json.dumps(cfg))

    def hv(call, step):
        return {**step, "headers": {"x-call-id": call}}
    r = run_mock(tmp_path, [hv("A", V("PUB-01", "date_of_birth", "1988-03-14")),
                            hv("A", V("PUB-01", "phone_last4", "4471")),
                            hv("B", post("/v1/get_account", {"customer_id": "PUB-01"})),
                            hv("A", post("/v1/get_account", {"customer_id": "PUB-01"})),
                            get("/ledger/PUB-01?session=A")])
    assert r[2]["body"]["ok"] is False and r[3]["body"]["ok"] is True
    assert len(r[4]["body"]["calls"]) == 3


# ------------------------------------------------------------------------------------------------ made-up Turkish

def tr_openapi():
    """An invented Turkish contract: renamed operations, a GET with a path parameter, status-enum success, error
    codes in the body, a per-field identity check, DD.MM.YYYY promise dates and documented 400/409 answers."""
    ok = {"durum": {"type": "string", "enum": ["TAMAM", "RED"]}, "hata": {"type": "string"}}

    def op(props, required, res=None, codes=("200", "500"), summary="", method="post"):
        o = {"summary": summary, "responses": {c: {"description": c} for c in codes}}
        o["responses"]["200"] = {"description": "ok", "content": {"application/json": {"schema": {
            "type": "object", "properties": {**ok, **(res or {})}}}}}
        if method == "post":
            o["requestBody"] = {"content": {"application/json": {"schema": {
                "type": "object", "properties": props, "required": required}}}}
        return o

    paths = {
        "/musteri/kimlik-kontrol": {"post": op(
            {"musteri_no": {"type": "string"}, "dogum_tarihi": {"type": "string"},
             "anne_kizlik_soyadi": {"type": "string"}}, ["musteri_no"],
            {"dogrulandi": {"type": "boolean"}, "kalan_hak": {"type": "integer"}},
            summary="Kimlik kontrolü. Toplam iki yanlış cevap kontrolü bitirir.", codes=("200", "400", "500"))},
        "/musteri/{musteri_no}/kartlar": {"get": {**op({}, [], {"kartlar": {"type": "array", "items": {
            "type": "object", "properties": {"kart_no": {"type": "string"}, "borc": {"type": "number"},
                                             "asgari": {"type": "number"}}}}}, method="get"),
            "parameters": [{"name": "musteri_no", "in": "path", "required": True, "schema": {"type": "string"}}]}},
        "/taahhut/kaydet": {"post": op(
            {"musteri_no": {"type": "string"}, "kart_no": {"type": "string"},
             "tutar": {"type": "number", "minimum": 1}, "tarih": {"type": "string", "description": "GG.AA.YYYY"}},
            ["musteri_no", "kart_no", "tutar", "tarih"], {"kayit_no": {"type": "string"}},
            codes=("200", "400", "409", "500"))},
        "/gorusme/sonlandir": {"post": op(
            {"musteri_no": {"type": "string"}, "sonuc": {"type": "string", "enum": ["ODEME_SOZU", "RED", "ULASILAMADI"]},
             "neden": {"type": "string", "enum": ["ISTEMIYOR", "YANLIS_KISI"]}}, ["musteri_no", "sonuc"])},
        "/sms/gonder": {"post": op({"musteri_no": {"type": "string"}, "metin": {"type": "string"}}, ["musteri_no"])},
    }
    return {"openapi": "3.0.3", "info": {"title": "Örnek banka servisleri", "version": "1"},
            "servers": [{"url": "https://banka.example/api/v2"}], "paths": paths}


def write_xlsx(path, rows, date_cols=()):
    """Minimal xlsx: shared strings for text, numbers as numbers, date columns as styled serials."""
    import datetime as dt
    strings, idx = [], {}

    def sidx(s):
        if s not in idx:
            idx[s] = len(strings)
            strings.append(s)
        return idx[s]
    xml_rows = []
    for r, row in enumerate(rows, start=1):
        cells = []
        for c, v in enumerate(row):
            ref = chr(65 + c) + str(r)
            if v is None:
                continue
            if isinstance(v, dt.date):
                serial = (v - dt.date(1899, 12, 30)).days
                cells.append(f'<c r="{ref}" s="1"><v>{serial}</v></c>')
            elif isinstance(v, (int, float)):
                cells.append(f'<c r="{ref}"><v>{v}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="s"><v>{sidx(v)}</v></c>')
        xml_rows.append(f'<row r="{r}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rns = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {ns} {rns}><sheets><sheet name="Müşteriler" sheetId="1" '
                                      f'r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
                   '2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/styles.xml", f'<styleSheet {ns}><cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="14"/>'
                                    f'</cellXfs></styleSheet>')
        z.writestr("xl/sharedStrings.xml", f'<sst {ns}>' + "".join(f"<si><t>{s}</t></si>" for s in strings)
                   + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {ns}><sheetData>{"".join(xml_rows)}</sheetData>'
                                               f'</worksheet>')


def write_docx(path, paras_and_tables):
    W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = []
    for item in paras_and_tables:
        if isinstance(item, str):
            body.append(f"<w:p><w:r><w:t>{item}</w:t></w:r></w:p>")
        else:
            rows = "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>" for c in r)
                           + "</w:tr>" for r in item)
            body.append(f"<w:tbl>{rows}</w:tbl>")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f"<w:document {W}><w:body>{''.join(body)}</w:body></w:document>")


@pytest.fixture(scope="module")
def tr_case(tmp_path_factory):
    import datetime as dt
    d = tmp_path_factory.mktemp("trcase")
    (d / "contract.openapi.json").write_text(json.dumps(tr_openapi(), ensure_ascii=False))
    write_xlsx(d / "musteriler.xlsx", [
        ["Test müşterileri"],
        ["Müşteri No", "Ad", "Soyad", "Doğum Tarihi", "Anne Kızlık Soyadı", "Kart No", "Borç", "Asgari"],
        ["M-1", "Ece", "Demir", dt.date(1990, 5, 7), "Kara", "K-1", 1500.5, 450],
        ["M-1", "Ece", "Demir", dt.date(1990, 5, 7), "Kara", "K-2", "2.000,00", "600,25"],
        ["M-2", "Can", "Ak", dt.date(1985, 12, 1), "Ay", "K-9", 99, 30],
    ], date_cols=(3,))
    write_docx(d / "sozlesme.docx", [
        "Hata kodları",
        [["Kod", "Anlamı"], ["H01", "Müşteri bulunamadı."], ["H02", "Kimlik doğrulaması yapılmadı."],
         ["H03", "Doğrulama hakkı bitti."], ["H04", "Geçersiz biçim."], ["H05", "Kart bulunamadı."],
         ["H06", "Bu kart için zaten söz var."], ["H07", "Geçersiz değer (geçmiş tarih dahil)."]],
        "Kapanış tablosu",
        [["sonuc", "neden"], ["ODEME_SOZU", "—"], ["RED", "ISTEMIYOR"], ["ULASILAMADI", "YANLIS_KISI"]],
    ])
    rep = mc.generate(d / "contract.openapi.json", [d / "musteriler.xlsx"], d / "mock", contract=[d / "sozlesme.docx"])
    return d, rep


def test_tr_config_generic_binding(tr_case):
    _, rep = tr_case
    assert rep["errors"] == []
    cfg = rep["config"]
    ops = {o["path"]: o for o in cfg["ops"]}
    assert {o["role"] for o in cfg["ops"]} == {"verify", "account", "promise", "close", "stub"}
    assert ops["/musteri/kimlik-kontrol"]["role"] == "verify"
    assert ops["/musteri/kimlik-kontrol"]["identity_fields"] == {"dogum_tarihi": "dogum_tarihi",
                                                                 "anne_kizlik_soyadi": "anne_kizlik_soyadi"}
    assert ops["/musteri/{musteri_no}/kartlar"]["role"] == "account"
    assert ops["/taahhut/kaydet"]["fields"] == {"customer": "musteri_no", "product": "kart_no", "amount": "tutar",
                                                "date": "tarih"}
    assert ops["/taahhut/kaydet"]["request"]["tarih"]["wire_format"] == "%d.%m.%Y"
    assert ops["/taahhut/kaydet"]["reject_past_dates"] is True
    assert ops["/sms/gonder"]["role"] == "stub"
    assert ops["/taahhut/kaydet"]["s_values"] == {"ok": "TAMAM", "fail": "RED"}
    assert cfg["lang"] == "tr" and cfg["max_wrong"] == 2 and cfg["customer_field"] == "musteri_no"
    assert cfg["base_paths"] == ["/api/v2"]
    assert cfg["statuses"]["invalid"] == 400 and cfg["statuses"]["conflict"] == 409
    assert cfg["statuses"]["unknown_customer"] == 200
    assert cfg["error_codes"] == {"unknown_customer": "H01", "not_verified": "H02", "locked": "H03",
                                  "format": "H04", "unknown_product": "H05", "duplicate": "H06",
                                  "invalid_value": "H07"}
    close = ops["/gorusme/sonlandir"]
    assert close["reasons_by_outcome"] == {"ODEME_SOZU": [], "RED": ["ISTEMIYOR"], "ULASILAMADI": ["YANLIS_KISI"]}
    assert close["reasonless"] == ["ODEME_SOZU"] and close["reason_required"] is False


def test_tr_customers_from_xlsx(tr_case):
    _, rep = tr_case
    cs = {c["customer_id"]: c for c in rep["customers"]}
    assert list(cs) == ["M-1", "M-2"]
    m1 = cs["M-1"]
    assert m1["identity"] == {"dogum_tarihi": "1990-05-07", "anne_kizlik_soyadi": "Kara"}
    assert m1["products"] == [{"kart_no": "K-1", "borc": 1500.5, "asgari": 450.0},
                              {"kart_no": "K-2", "borc": 2000.0, "asgari": 600.25}]
    assert m1["variables"] == {"first_name": "Ece", "last_name": "Demir"}


@needs_node
def test_tr_engine_flow(tr_case):
    d, _ = tr_case
    m = {"musteri_no": "M-1"}
    r = run_mock(d / "mock", [
        {"method": "GET", "path": "/api/v2/musteri/M-1/kartlar"},
        post("/api/v2/musteri/kimlik-kontrol", {**m, "dogum_tarihi": "07.05.1990", "anne_kizlik_soyadi": "kara"}),
        {"method": "POST", "path": "/musteri/kartlar", "body": m},           # builder.contract's POST shape
        post("/taahhut/kaydet", {**m, "kart_no": "K-1", "tutar": 100, "tarih": "2026-10-20"}),
        post("/taahhut/kaydet", {**m, "kart_no": "K-1", "tutar": 0.5, "tarih": "20.10.2026"}),
        post("/taahhut/kaydet", {**m, "kart_no": "K-7", "tutar": 100, "tarih": "20.10.2026"}),
        post("/taahhut/kaydet", {**m, "kart_no": "K-1", "tutar": 100, "tarih": "20.10.2026"}),
        post("/taahhut/kaydet", {**m, "kart_no": "K-1", "tutar": 100, "tarih": "21.10.2026"}),
        post("/sms/gonder", {**m, "metin": "x"}),
        post("/sms/gonder", {"musteri_no": "nobody"}),
        post("/gorusme/sonlandir", {**m, "sonuc": "RED", "neden": "YANLIS_KISI"}),
        post("/gorusme/sonlandir", {**m, "sonuc": "RED"}),
        post("/gorusme/sonlandir", {"musteri_no": "M-404", "sonuc": "RED"}),
        get("/ledger/M-1")])
    assert r[0]["body"] == {"durum": "RED", "hata": "H02"}
    assert r[1]["body"] == {"durum": "TAMAM", "dogrulandi": True, "kalan_hak": 2}
    assert r[2]["body"]["kartlar"][1]["kart_no"] == "K-2"
    assert r[3]["status"] == 400 and r[3]["body"] == {"durum": "RED", "hata": "H04"}
    assert r[4]["status"] == 400 and r[4]["body"]["hata"] == "H07"
    assert r[5]["body"]["hata"] == "H05"
    assert r[6]["body"] == {"durum": "TAMAM", "kayit_no": "pr1"}
    assert r[7]["status"] == 409 and r[7]["body"]["hata"] == "H06"
    assert r[8]["body"] == {"durum": "TAMAM"} and r[9]["body"] == {"durum": "TAMAM"}
    assert r[10]["body"]["hata"] == "H07"                                     # reason not allowed for RED
    assert r[11]["body"] == {"durum": "TAMAM"}                                # reason optional here
    assert r[12]["status"] == 200 and r[12]["body"]["hata"] == "H01"
    led = r[13]["body"]
    assert led["promises"][0]["date"] == "2026-10-20" and led["promises"][0]["amount"] == 100
    assert len(led["stubs"]) == 1 and led["stubs"][0]["args"] == {"musteri_no": "M-1", "metin": "x"}


@needs_node
def test_tr_wrong_answer_limit_two_and_turkish_messages(tr_case, tmp_path):
    d, rep = tr_case
    cfg = dict(rep["config"])
    cfg.pop("error_codes")
    for f in ("customers.json", "openapi.json"):
        shutil.copy(d / "mock" / f, tmp_path / f)
    (tmp_path / "config.json").write_text(json.dumps(cfg))
    m = {"musteri_no": "M-2"}
    r = run_mock(tmp_path, [post("/musteri/kimlik-kontrol", {**m, "anne_kizlik_soyadi": "Gün"}),
                            post("/musteri/kimlik-kontrol", {**m, "anne_kizlik_soyadi": "Su"}),
                            post("/musteri/kimlik-kontrol", {**m, "anne_kizlik_soyadi": "Ay"}),
                            post("/musteri/kartlar", m)])
    assert r[0]["body"] == {"durum": "TAMAM", "dogrulandi": False, "kalan_hak": 1}
    assert r[1]["body"]["hata"] == "çok fazla yanlış cevap" and r[1]["body"]["kalan_hak"] == 0
    assert r[2]["body"]["durum"] == "RED"                                     # locked even when right
    assert r[3]["body"]["hata"] == "kimlik doğrulanmadı"


def test_past_date_needs_call_now(tr_case):
    # covered in the engine by customer variables.now; without it nothing is refused (server clock never used)
    _, rep = tr_case
    assert "now" not in rep["customers"][0]["variables"]


@needs_node
def test_past_date_refused_against_call_now(tr_case, tmp_path):
    d, _ = tr_case
    cs = json.loads((d / "mock" / "customers.json").read_text())
    cs[0]["variables"]["now"] = "2026-10-14T11:00"
    for f in ("config.json", "openapi.json"):
        shutil.copy(d / "mock" / f, tmp_path / f)
    (tmp_path / "customers.json").write_text(json.dumps(cs))
    m = {"musteri_no": "M-1"}
    r = run_mock(tmp_path, [post("/musteri/kimlik-kontrol", {**m, "dogum_tarihi": "1990-05-07",
                                                              "anne_kizlik_soyadi": "Kara"}),
                            post("/taahhut/kaydet", {**m, "kart_no": "K-1", "tutar": 5, "tarih": "13.10.2026"}),
                            post("/taahhut/kaydet", {**m, "kart_no": "K-1", "tutar": 5, "tarih": "14.10.2026"})])
    assert r[1]["body"]["hata"] == "H07" and r[2]["body"]["durum"] == "TAMAM"


# ------------------------------------------------------------------------------------------------ derived OpenAPI

def test_x_freya_annotations_stub_and_synthetic_alias():
    doc = tr_openapi()
    doc["paths"]["/islem/bir"] = {"post": {
        "x-freya-tool": "add_note", "summary": "",
        "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {
            "musteri_no": {"type": "string"}, "tur": {"type": "string", "enum": ["A", "B"]},
            "reason": {"type": "string", "x-freya-role": "reason", "x-freya-synthetic": True}},
            "required": ["musteri_no", "tur"]}}}},
        "responses": {"200": {"description": "ok"}}}}
    doc["paths"]["/_freya/transfer_to_agent"] = {"post": {
        "x-freya-tool": "transfer_to_agent", "x-freya-absent": True, "summary": "stub",
        "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {
            "musteri_no": {"type": "string", "x-freya-role": "customer"}}}}}},
        "responses": {"200": {"description": "ok", "content": {"application/json": {"schema": {
            "type": "object", "properties": {"ok": {"type": "boolean", "x-freya-role": "s"}}}}}}}}}
    cfg, warnings = mc.build_config(doc)
    ops = {o["path"]: o for o in cfg["ops"]}
    note = ops["/islem/bir"]
    assert note["role"] == "note" and note["fields"]["reason"] == "tur"
    assert note["aliases"] == {"reason": "tur"} and note["ignored_fields"] == ["reason"]
    assert "reason" not in note["request"]
    stub = ops["/_freya/transfer_to_agent"]
    assert stub["role"] == "stub" and stub["for_role"] == "transfer"
    assert any("absent" in w for w in warnings)


@needs_node
def test_alias_and_stub_in_engine(tmp_path):
    doc = tr_openapi()
    doc["paths"]["/islem/bir"] = {"post": {
        "x-freya-tool": "add_note",
        "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": {
            "musteri_no": {"type": "string"}, "tur": {"type": "string", "enum": ["A", "B"]},
            "reason": {"type": "string", "x-freya-role": "reason", "x-freya-synthetic": True}},
            "required": ["musteri_no", "tur"]}}}},
        "responses": {"200": {"description": "ok", "content": {"application/json": {"schema": {
            "type": "object", "properties": {"ok": {"type": "boolean"}}}}}}}}}
    cfg, _ = mc.build_config(doc)
    mc.write(tmp_path, cfg, [{"customer_id": "M-1", "identity": {"anne_kizlik_soyadi": "Kara"}, "products": []}], doc)
    r = run_mock(tmp_path, [post("/islem/bir", {"musteri_no": "M-1", "reason": "B"}),
                            post("/islem/bir", {"musteri_no": "M-1", "reason": "C"}), get("/ledger/M-1")])
    assert r[0]["body"] == {"ok": True}
    assert r[1]["body"]["ok"] is False
    assert r[2]["body"]["notes"][0]["reason"] == "B"


# ------------------------------------------------------------------------------------------------ readers

def test_md_csv_json_tables(tmp_path):
    (tmp_path / "a.md").write_text("# Müşteriler\n\nmetin\n\n| Müşteri No | Doğum Tarihi |\n|---|---|\n"
                                   "| `M-1` | 07.05.1990 |\n| M-2 | **1 Aralık 1985** |\n\nson\n")
    (tmp_path / "b.csv").write_text("musteri_no;telefon_son4\nM-1;0123\n")
    (tmp_path / "c.json").write_text(json.dumps({"customers": [{"id": "M-3", "dob": "1990-01-01"}]}))
    ts = tbl.read_tables(tmp_path)
    by = {pathlib.Path(t["source"]).name: t for t in ts}
    assert by["a.md"]["name"] == "Müşteriler"
    assert by["a.md"]["rows"] == [{"Müşteri No": "M-1", "Doğum Tarihi": "07.05.1990"},
                                  {"Müşteri No": "M-2", "Doğum Tarihi": "1 Aralık 1985"}]
    assert by["b.csv"]["rows"] == [{"musteri_no": "M-1", "telefon_son4": "0123"}]
    assert by["c.json"]["rows"] == [{"id": "M-3", "dob": "1990-01-01"}]


def test_xlsx_reader_dates_gaps_and_numbers(tmp_path):
    import datetime as dt
    write_xlsx(tmp_path / "x.xlsx", [["a", "b", "c"], [1, None, dt.date(2026, 10, 14)], [358.0, "x", 2.5]])
    t = tbl.read_tables(tmp_path / "x.xlsx")[0]
    assert t["rows"] == [{"a": "1", "b": "", "c": "2026-10-14"}, {"a": "358", "b": "x", "c": "2.5"}]


def test_docx_reader(tmp_path):
    write_docx(tmp_path / "d.docx", ["Başlık", [["k", "v"], ["1", "bir"]], "Diğer", [["x", "y"], ["2", "iki"]]])
    ts = tbl.read_tables(tmp_path / "d.docx")
    assert [t["name"] for t in ts] == ["Başlık", "Diğer"]
    assert ts[1]["rows"] == [{"x": "2", "y": "iki"}]


@pytest.mark.parametrize("raw,want", [("1.234,56 TL", 1234.56), ("1,234.56", 1234.56), ("₺420,50", 420.5),
                                      ("1.500", 1500.0), ("2125.1", 2125.1), ("abc", None), ("-5", -5.0)])
def test_parse_number(raw, want):
    assert mc.parse_number(raw) == want


@pytest.mark.parametrize("raw,want", [("14.03.1988", "1988-03-14"), ("1988-03-14", "1988-03-14"),
                                      ("14 Mart 1988", "1988-03-14"), ("3 June 1987", "1987-06-03"),
                                      ("31.02.1990", None), ("garbage", None)])
def test_parse_date(raw, want):
    assert mc.parse_date(raw) == want


# ------------------------------------------------------------------------------------------------ validation + LLM

def test_validate_catches_bad_data(kit_cfg):
    errs = mc.validate(kit_cfg, [{"customer_id": "A", "identity": {"pin": "1"}, "products": []},
                                 {"customer_id": "A", "identity": {}, "products": [{"product_id": "p1"},
                                                                                  {"product_id": "p1"}]}])
    assert any("not one the verify operation asks" in e for e in errs)
    assert any("duplicate id" in e for e in errs)
    assert any("no identity answers" in e for e in errs)
    assert any("duplicate product ids" in e for e in errs)


def test_missing_customer_column_is_an_error(tmp_path):
    (tmp_path / "c.csv").write_text("name,dob\nX,1990-01-01\n")
    rep = mc.generate(KIT_OPENAPI, [tmp_path / "c.csv"], tmp_path / "out")
    assert rep["customers"] == [] and "no customers" in rep["errors"]
    assert rep["files"] == {} and not (tmp_path / "out").exists()


def test_column_override_and_role_override(tmp_path):
    (tmp_path / "c.csv").write_text("kod,gizli\nZ-1,1990-01-01\n")
    rep = mc.generate(KIT_OPENAPI, [tmp_path / "c.csv"], tmp_path / "out", write_files=False,
                      column_map={"kod": "customer_id", "gizli": "identity:date_of_birth"})
    assert rep["customers"][0]["identity"] == {"date_of_birth": "1990-01-01"}


def test_validate_llm_keeps_only_real_names(kit_cfg):
    ops = mc.operations(json.loads(KIT_OPENAPI.read_text()))
    out = mc.validate_llm({"operations": [{"path": "/add_note", "role": "note"}, {"path": "/x", "role": "note"}],
                           "columns": [{"column": "a", "target": "identity:date_of_birth"},
                                       {"column": "b", "target": "identity:pin"}],
                           "reasonless": ["promise", "nope"],
                           "reasons_by_outcome": {"no_promise": ["refused", "bogus"], "zzz": ["a"]},
                           "max_wrong": 99}, ops, kit_cfg)
    assert out["role_overrides"] == {"note": "/add_note"}
    assert out["column_map"] == {"a": "identity:date_of_birth"}
    assert out["reasonless"] == ["promise"]
    assert out["reasons_by_outcome"] == {"no_promise": ["refused", "bogus"]}      # no reason enum in the kit
    assert out["max_wrong"] is None and len(out["rejected"]) >= 3


def test_llm_fill_uses_builder_llm_backend(tmp_path):
    from builder import llm
    seen = {}

    def fake(req):
        seen["purpose"] = req["purpose"]
        return {"data": {"operations": [], "columns": [{"column": "gizli", "target": "identity:phone_last4"}],
                         "reasonless": ["promise", "paid"], "max_wrong": 3}}
    prev = llm.set_backend(fake)
    try:
        (tmp_path / "c.csv").write_text("customer_id,gizli\nQ-1,0042\n")
        rep = mc.generate(KIT_OPENAPI, [tmp_path / "c.csv"], tmp_path / "out", use_llm=True, write_files=False)
    finally:
        llm.set_backend(prev)
    assert seen["purpose"] == "mockgen.map"
    assert rep["customers"][0]["identity"] == {"phone_last4": "0042"}


def test_cli_writes_files_and_exit_codes(tmp_path, capsys):
    code = mc.main(["--openapi", str(KIT_OPENAPI), "--customers", str(KIT_CASES), "--out", str(tmp_path)])
    assert code == 0
    assert {p.name for p in tmp_path.iterdir()} == {"config.json", "customers.json", "openapi.json"}
    assert "customers: 13" in capsys.readouterr().out
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps([{"customer_id": "A", "identity": {"x": "1"}}, {"customer_id": "A",
                                                                               "identity": {"y": "2"}}]))
    assert mc.main(["--openapi", str(KIT_OPENAPI), "--customers", str(bad), "--out", str(tmp_path / "o2"),
                    "--check"]) == 2


# ------------------------------------------------------------------------------------------------ rehearsal folder

@pytest.mark.skipif(not (TR_REF / "reference" / "openapi.json").exists(), reason="no rehearsal folder")
def test_rehearsal_reference_contract_and_xlsx(tmp_path):
    rep = mc.generate(TR_REF / "reference" / "openapi.json",
                      [TR_REF / "FreyaBank-Rehearsal" / "test-musterileri.xlsx"], tmp_path,
                      contract=[TR_REF / "FreyaBank-Rehearsal"])
    assert rep["errors"] == []
    ref = {c["customer_id"]: c for c in json.loads((TR_REF / "reference" / "mock-customers.json").read_text())}
    got = {c["customer_id"]: c for c in rep["customers"]}
    assert set(got) == set(ref)
    plist = rep["config"]["products"]["list"]
    for cid, c in ref.items():
        assert got[cid]["products"] == c[plist]
        for k, v in c["identity"].items():
            assert got[cid]["identity"][k] == (mc.parse_date(v) or v)
    codes = rep["config"]["error_codes"]
    assert codes["not_verified"] != codes["duplicate"] and set(codes) >= {"not_verified", "duplicate", "format",
                                                                            "fault", "locked"}


# ------------------------------------------------------------------------------------------------ live (local server)

def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@needs_node
def test_smoke_against_local_server(kit_dir, tr_case):
    from tools.mockgen import smoke
    for d in (kit_dir, tr_case[0] / "mock"):
        port = _free_port()
        proc = subprocess.Popen([NODE, str(HARNESS), "serve", "--dir", str(d), "--port", str(port)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            for _ in range(50):
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                    break
                except OSError:
                    time.sleep(0.1)
            cfg = json.loads((d / "config.json").read_text())
            cs = json.loads((d / "customers.json").read_text())
            lines = []
            fails = smoke.run(f"http://127.0.0.1:{port}", cfg, cs[0], log=lines.append)
            assert fails == [], lines
        finally:
            proc.terminate()
            proc.wait(timeout=10)


@needs_node
def test_smoke_all_customers_incl_injected_promise_fault(kit_dir):
    """smoke --all over a local server (emulated Durable Objects): a customer whose data injects a create_promise
    fault (fail_first_n) expects that failure first, then the promise records and a second one is refused."""
    from tools.mockgen import smoke
    cfg = json.loads((kit_dir / "config.json").read_text())
    cs = json.loads((kit_dir / "customers.json").read_text())
    faulty = [c for c in cs if any(f.get("op") == "create_promise" and f.get("fail_first_n") for f in c.get("faults") or [])]
    assert faulty, "the kit data has a create_promise fault customer"
    port = _free_port()
    proc = subprocess.Popen([NODE, str(HARNESS), "serve", "--dir", str(kit_dir), "--port", str(port)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)
        for c in cs:
            lines = []
            fails = smoke.run(f"http://127.0.0.1:{port}", cfg, c, log=lines.append)
            assert fails == [], lines
            if c in faulty:
                assert any(ln.startswith("PASS") and "injected promise fault 1/1" in ln for ln in lines), lines
            else:
                assert not any("injected promise fault" in ln for ln in lines), lines
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_worker_entry_imports_the_three_data_files():
    src = (ROOT / "mock" / "src" / "worker.js").read_text()
    for f in ("../config.json", "../openapi.json", "../customers.json", "./engine.js"):
        assert f in src
    toml = (ROOT / "mock" / "wrangler.toml").read_text()
    assert 'main = "src/worker.js"' in toml and 'name = "LEDGER_DO"' in toml and 'class_name = "Ledger"' in toml
    assert 'new_sqlite_classes = ["Ledger"]' in toml and "[[kv_namespaces]]" not in toml
    assert "export class Ledger" in src and "this.ctx.storage" in src


def test_mockgen_has_no_case_values():
    """Generic words only: the generator and engine name no kit/rehearsal customer, value or code."""
    text = "".join(p.read_text() for p in [ROOT / "tools/mockgen/make_config.py", ROOT / "tools/mockgen/tables.py",
                                            ROOT / "mock/src/engine.js", ROOT / "tools/mockgen/smoke.py"])
    for bad in ("PUB-", "Daniel", "Reyes", "4471", "1988-03-14", "FB-24", "KRT-", "E002", "E006",
                "SOZ_ALINDI", "kimlik/dogrula", "TCKN_SON4", "day_month_swapped", "credit_card"):
        assert bad not in text, bad
