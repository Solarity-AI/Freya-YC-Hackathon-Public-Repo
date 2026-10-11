"""builder/contract.py: service contract (OpenAPI or prose) -> ToolCatalog calling OUR mock; operation -> tool roles
(English + Turkish names), degrade for absent services, synthetic fields, mock shape normalisation, LLM derivation
(mocked via llm.set_backend). Plus the Turkish role words added to builder/openapi_model.py."""
import copy
import json
import pathlib

import pytest

from builder import contract as C
from builder import llm
from builder import openapi_model as OM

ROOT = pathlib.Path(__file__).resolve().parent.parent
KIT = json.loads((ROOT / "kit" / "tools" / "openapi.json").read_text())
MOCK = "https://bank-mock.example.workers.dev"


@pytest.fixture
def no_llm():
    prev = llm.set_backend(lambda req: pytest.fail("unexpected LLM call: " + req["purpose"]))
    yield
    llm.set_backend(prev)


@pytest.fixture
def fake_llm():
    """Install a backend answering by purpose: {purpose: dict | callable(req) -> dict}. Records the requests."""
    prev = llm.set_backend(None)
    calls = []

    def install(answers):
        def backend(req):
            calls.append(req)
            a = answers[req["purpose"]]
            return {"data": a(req) if callable(a) else copy.deepcopy(a)}
        llm.set_backend(backend)
        return calls
    yield install
    llm.set_backend(prev)


def docs_of(doc, name="openapi.json"):
    return [{"name": name, "text": json.dumps(doc)}]


# ---------------------------------------------------------------------------------------------------------- kit

def test_kit_openapi_catalog_points_at_mock_and_matches_openapi_model(tmp_path, no_llm):
    cat = C.build_catalog(docs_of(KIT), MOCK + "/", tmp_path, fetch=False)
    ref = OM.build_catalog(KIT)
    assert cat["server"] == MOCK
    for t in ref["tools"]:
        assert cat["tools"][t]["url"] == MOCK + "/" + t
        assert cat["tools"][t]["roles"] == ref["tools"][t]["roles"]
        assert cat["tools"][t]["success"] == ref["tools"][t]["success"]
        assert cat["tools"][t]["request"] == ref["tools"][t]["request"]
        assert not cat["tools"][t].get("absent")
    assert cat["enums"] == ref["enums"]
    assert cat["identity_mode"] == "selector"
    con = cat["contract"]
    assert con["absent"] == [] and con["extra_operations"] == [] and con["synthetic_fields"] == []
    assert con["identity_design"] == "selector"
    assert con["source"].startswith("case folder OpenAPI")
    written = json.loads((tmp_path / "openapi.json").read_text())
    assert written["servers"] == [{"url": MOCK}]
    assert set(written["paths"]) == set(KIT["paths"])                       # relative paths kept
    assert cat["tools"]["get_account"]["item_extras"]["floor"] == "minimum_payment"


def test_kit_catalog_via_openapi_model_load_unchanged(catalog_kit, kit_openapi_path):
    cat = OM.load(kit_openapi_path)
    assert set(cat["tools"]["get_account"]) == set(catalog_kit["tools"]["get_account"])   # no extra keys in D.1
    assert cat["tools"] == catalog_kit["tools"]


def test_casedocs_dict_input_uses_its_openapi(tmp_path, no_llm):
    case = {"docs": [], "contract_docs": [], "openapi": KIT, "openapi_path": "api/openapi.json"}
    cat = C.build_catalog(case, MOCK, tmp_path, fetch=False)
    assert "api/openapi.json" in cat["contract"]["source"]


def test_openapi_inside_markdown_fence(no_llm):
    text = "# Servisler\n\n```json\n" + json.dumps(KIT) + "\n```\n"
    cat = C.build_catalog([{"name": "Servis_Sozlesmesi.md", "text": text}], MOCK, None, fetch=False)
    assert cat["contract"]["absent"] == []
    assert cat["contract"]["openapi_path"] is None


def test_mock_served_openapi_used_when_case_has_none(tmp_path, no_llm):
    seen = []

    def fetch(url):
        seen.append(url)
        return KIT
    case = [{"name": "README.md", "text": "Belgeler listesi."}]
    cat = C.build_catalog(case, MOCK, tmp_path, fetch=fetch)
    assert seen == [MOCK + "/openapi.json"]
    assert cat["contract"]["source"].startswith("mock ")
    assert cat["tools"]["close_call"]["url"] == MOCK + "/close_call"


def test_mock_fetch_failure_falls_through_to_error_without_contract(no_llm):
    def fetch(url):
        raise OSError("unreachable")
    with pytest.raises(OM.CatalogError, match="no service contract"):
        C.build_catalog([{"name": "README.md", "text": "nothing"}], MOCK, None, fetch=fetch)


def test_prose_contract_with_llm_disabled_is_an_error(no_llm):
    with pytest.raises(OM.CatalogError, match="disabled"):
        C.build_catalog([{"name": "Servis_Sozlesmesi.md", "text": PROSE}], MOCK, None, fetch=False, use_llm=False)


# ------------------------------------------------------------------------------------- renamed Turkish OpenAPI

def turkish_variant():
    """The kit API with Turkish operation names / paths / fields, a GET with a query parameter and an extra op."""
    def body(props, req):
        return {"required": True, "content": {"application/json": {"schema": {
            "type": "object", "properties": props, "required": req}}}}

    def res(props):
        return {"200": {"description": "ok", "content": {"application/json": {"schema": {
            "type": "object", "properties": props}}}}}
    base = {"basarili": {"type": "boolean"}, "hata_mesaji": {"type": "string"}}
    m = {"musteri_no": {"type": "string"}}
    return {
        "openapi": "3.0.3", "info": {"title": "Banka servisleri", "version": "1"},
        "servers": [{"url": "https://banka.example.com/api/v2"}],
        "paths": {
            "/kimlik/dogrula": {"post": {"operationId": "kimlikDogrula", "summary": "Kimlik sorusunu doğrular",
                "requestBody": body(dict(m, soru={"type": "string", "enum": ["dogum_tarihi", "telefon_son4"]},
                                         cevap={"type": "string"}), ["musteri_no", "soru", "cevap"]),
                "responses": res(dict(base, dogrulandi={"type": "boolean"}, kalan_hak={"type": "integer"},
                                      tum_sorular_dogru={"type": "boolean"},
                                      ipucu={"type": "string", "enum": ["gun_ay_ters"]}))}},
            "/musteri/borc-ozeti": {"get": {"operationId": "borcOzeti", "summary": "Müşterinin borç özeti",
                "parameters": [{"name": "musteri_no", "in": "query", "required": True, "schema": {"type": "string"}}],
                "responses": res(dict(base, urunler={"type": "array", "items": {"type": "object", "properties": {
                    "urun_no": {"type": "string"}, "urun_tipi": {"type": "string", "enum": ["KART", "KREDI"]},
                    "gecikmis_tutar": {"type": "number"}, "gecikme_gunu": {"type": "integer"},
                    "asgari_odeme": {"type": "number"}, "son_odeme_tarihi": {"type": "string"},
                    "donem_borcu": {"type": "number"}}}}))}},
            "/odeme-sozu/kaydet": {"post": {"operationId": "odemeSozuKaydet",
                "requestBody": body(dict(m, urun_no={"type": "string"}, tutar={"type": "number"},
                                         odeme_tarihi={"type": "string", "format": "date"}),
                                    ["musteri_no", "urun_no", "tutar", "odeme_tarihi"]),
                "responses": res(dict(base, soz_no={"type": "string"}))}},
            "/musteri/not-ekle": {"post": {"operationId": "notEkle",
                "requestBody": body(dict(m, urun_no={"type": "string"},
                                         neden={"type": "string", "enum": ["RET", "ODEDI", "ITIRAZ"]},
                                         aciklama={"type": "string"}), ["musteri_no", "neden"]),
                "responses": res(base)}},
            "/geri-arama/planla": {"post": {"operationId": "geriAramaPlanla",
                "requestBody": body(dict(m, tarih={"type": "string", "format": "date"},
                                         saat={"type": "string", "description": "HH:MM"}),
                                    ["musteri_no", "tarih", "saat"]),
                "responses": res(base)}},
            "/temsilciye-aktar": {"post": {"operationId": "temsilciyeAktar",
                "requestBody": body(dict(m, kuyruk={"type": "string", "enum": ["GENEL", "DESTEK"]}),
                                    ["musteri_no", "kuyruk"]),
                "responses": res(base)}},
            "/gorusme/kapat": {"post": {"operationId": "gorusmeKapat",
                "requestBody": body(dict(m, sonuc={"type": "string", "enum": ["SOZ", "ODENDI", "SOZ_YOK"]},
                                         kapanis_nedeni={"type": "string"}), ["musteri_no", "sonuc"]),
                "responses": res(base)}},
            "/kampanya/liste": {"post": {"operationId": "kampanyaListe", "responses": res(base)}},
        },
    }


def test_turkish_variant_maps_every_role_without_llm(tmp_path, no_llm):
    cat = C.build_catalog(docs_of(turkish_variant()), MOCK, tmp_path, fetch=False, use_llm=False)
    con = cat["contract"]
    assert con["op_map"] == {
        "verify_identity": "POST /kimlik/dogrula", "get_account": "POST /musteri/borc-ozeti",
        "create_promise": "POST /odeme-sozu/kaydet", "add_note": "POST /musteri/not-ekle",
        "schedule_callback": "POST /geri-arama/planla", "transfer_to_agent": "POST /temsilciye-aktar",
        "close_call": "POST /gorusme/kapat"}
    assert con["absent"] == [] and con["extra_operations"] == ["POST /kampanya/liste"]
    t = cat["tools"]
    assert t["verify_identity"]["roles"]["request"] == {"customer": "musteri_no", "selector": "soru", "answer": "cevap"}
    assert t["verify_identity"]["roles"]["response"] == {"s": "basarili", "err": "hata_mesaji",
                                                        "verified": "dogrulandi", "left": "kalan_hak",
                                                        "all": "tum_sorular_dogru", "hint": "ipucu"}
    assert t["get_account"]["roles"]["item"] == {"id": "urun_no", "type": "urun_tipi", "past_due": "gecikmis_tutar",
                                                 "days_late": "gecikme_gunu"}
    assert t["get_account"]["item_extras"] == {"floor": "asgari_odeme", "total": "donem_borcu",
                                               "due_date": "son_odeme_tarihi"}
    assert t["create_promise"]["roles"]["request"] == {"customer": "musteri_no", "product": "urun_no",
                                                      "amount": "tutar", "date": "odeme_tarihi"}
    assert t["create_promise"]["roles"]["response"]["pid"] == "soz_no"
    assert t["add_note"]["roles"]["request"] == {"customer": "musteri_no", "product": "urun_no", "reason": "neden",
                                                "text": "aciklama"}
    assert t["schedule_callback"]["roles"]["request"] == {"customer": "musteri_no", "date": "tarih", "time": "saat"}
    assert t["transfer_to_agent"]["roles"]["request"]["queue"] == "kuyruk"
    assert t["close_call"]["roles"]["request"] == {"customer": "musteri_no", "reason": "kapanis_nedeni",
                                                  "outcome": "sonuc"}
    assert cat["enums"]["outcome"] == ["SOZ", "ODENDI", "SOZ_YOK"]
    assert cat["enums"]["queue"] == ["GENEL", "DESTEK"]
    assert all(t[x]["success"]["kind"] == "bool_true" for x in t)
    # GET + query parameter -> POST with the parameter in the JSON body, at the same literal path, on our mock
    acct = t["get_account"]
    assert acct["method"] == "POST" and acct["url"] == MOCK + "/musteri/borc-ozeti"
    assert acct["roles"]["request"] == {"customer": "musteri_no"}
    assert con["mock_shape_changes"] == ["GET /musteri/borc-ozeti -> POST /musteri/borc-ozeti (parameters in the JSON body)"]
    written = json.loads((tmp_path / "openapi.json").read_text())
    op = written["paths"]["/musteri/borc-ozeti"]["post"]
    assert op["x-freya-original"] == {"method": "GET", "path": "/musteri/borc-ozeti"}
    assert op["x-freya-tool"] == "get_account"
    assert written["servers"] == [{"url": MOCK}]


def test_path_parameter_segment_dropped_and_folded_into_body(no_llm):
    doc = turkish_variant()
    op = doc["paths"].pop("/musteri/borc-ozeti")["get"]
    op["parameters"][0]["in"] = "path"
    doc["paths"]["/musteri/{musteri_no}/borc"] = {"get": op}
    out, changes = C.normalize_for_mock(doc)
    assert "/musteri/borc" in out["paths"] and "/musteri/{musteri_no}/borc" not in out["paths"]
    body = out["paths"]["/musteri/borc"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert body["properties"]["musteri_no"] == {"type": "string"} and body["required"] == ["musteri_no"]
    assert changes == ["GET /musteri/{musteri_no}/borc -> POST /musteri/borc (parameters in the JSON body)"]


def test_normalize_collision_and_shared_params():
    doc = {"openapi": "3.0.0", "paths": {
        "/x": {"post": {"operationId": "a"}},
        "/x/{id}": {"parameters": [{"name": "id", "in": "path", "schema": {"type": "string"}, "description": "d"}],
                    "get": {"operationId": "b", "parameters": [{"name": "q", "in": "query"}, {"name": "h", "in": "header"}]}}}}
    out, changes = C.normalize_for_mock(doc)
    assert set(out["paths"]) == {"/x", "/x_get"}
    props = out["paths"]["/x_get"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]
    assert props == {"id": {"type": "string", "description": "d"}, "q": {"type": "string"}}
    assert len(changes) == 1


def test_mock_served_openapi_with_get_is_reshaped_with_warning(tmp_path, no_llm, monkeypatch):
    events = []
    monkeypatch.setattr(C, "_log", lambda kind, msg, **f: events.append((kind, msg)))
    doc = turkish_variant()
    cat = C.build_catalog([{"name": "README.md", "text": "x"}], MOCK, tmp_path, fetch=lambda u: doc, use_llm=False)
    assert cat["tools"]["get_account"]["method"] == "POST"                # the engine sends a JSON body
    assert len(cat["contract"]["mock_shape_changes"]) == 1
    assert any(k == "WARN" and "the mock serves another shape" in m for k, m in events)


# ---------------------------------------------------------------------------------- absent services / degrade

def test_absent_optional_services_become_stubs_on_our_mock(tmp_path, no_llm):
    doc = turkish_variant()
    for p in ("/musteri/not-ekle", "/geri-arama/planla", "/temsilciye-aktar", "/gorusme/kapat", "/kampanya/liste"):
        doc["paths"].pop(p)
    cat = C.build_catalog(docs_of(doc), MOCK, tmp_path, fetch=False, use_llm=False)
    con = cat["contract"]
    assert con["absent"] == ["add_note", "schedule_callback", "transfer_to_agent", "close_call"]
    for t in con["absent"]:
        tool = cat["tools"][t]
        assert tool["absent"] is True
        assert tool["url"] == MOCK + "/_freya/" + t
        assert tool["roles"]["request"]["customer"] == "musteri_no"         # same customer field as the real ones
        assert tool["success"]["kind"] == "bool_true"
    assert not cat["tools"]["create_promise"].get("absent")
    assert cat["enums"]["outcome"] == [] and cat["enums"]["queue"] == []
    written = json.loads((tmp_path / "openapi.json").read_text())
    assert written["paths"]["/_freya/close_call"]["post"]["x-freya-absent"] is True


def test_absent_core_service_is_stubbed_with_error_trace(tmp_path, no_llm, monkeypatch):
    events = []
    monkeypatch.setattr(C, "_log", lambda kind, msg, **f: events.append((kind, msg)))
    doc = turkish_variant()
    doc["paths"].pop("/odeme-sozu/kaydet")
    cat = C.build_catalog(docs_of(doc), MOCK, tmp_path, fetch=False, use_llm=False)
    assert cat["tools"]["create_promise"]["absent"] is True
    assert any(k == "ERROR" and "create_promise" in m for k, m in events)


def test_missing_optional_role_gets_synthetic_field(tmp_path, no_llm):
    doc = turkish_variant()
    sch = doc["paths"]["/musteri/not-ekle"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    sch["properties"].pop("neden")
    sch["required"] = ["musteri_no"]
    cat = C.build_catalog(docs_of(doc), MOCK, tmp_path, fetch=False, use_llm=False)
    note = cat["tools"]["add_note"]
    assert note["roles"]["request"]["reason"] == "reason"
    assert not note["request"]["reason"]["required"]
    assert cat["contract"]["synthetic_fields"] == ["add_note.reason (role reason)"]


def test_core_role_problem_raises(no_llm):
    doc = turkish_variant()
    doc["paths"]["/musteri/borc-ozeti"]["get"]["parameters"] = []       # get_account loses its customer key
    docs = docs_of(doc)
    with pytest.raises(OM.CatalogError, match="get_account"):
        C.build_catalog(docs, MOCK, None, fetch=False, use_llm=False)


def test_missing_product_list_is_synthesised_not_fatal(no_llm):
    doc = turkish_variant()
    items = doc["paths"]["/musteri/borc-ozeti"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    items["properties"].pop("urunler")
    cat = C.build_catalog(docs_of(doc), MOCK, None, fetch=False, use_llm=False)
    acct = cat["tools"]["get_account"]
    assert acct["roles"]["response"]["products"] == "products"
    assert acct["roles"]["item"] == {"id": "id", "type": "type", "past_due": "past_due", "days_late": "days_late"}
    assert acct["item_extras"]["floor"] == "minimum_due"
    assert "get_account.products (response role products)" in cat["contract"]["synthetic_fields"]


# --------------------------------------------------------------------------------- identity designs

def test_identity_design_per_field_and_all_at_once(no_llm):
    doc = turkish_variant()
    v = doc["paths"]["/kimlik/dogrula"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    v["properties"] = {"musteri_no": {"type": "string"}, "dogum_tarihi": {"type": "string"},
                       "telefon_son4": {"type": "string"}}
    v["required"] = ["musteri_no"]
    cat = C.build_catalog(docs_of(doc), MOCK, None, fetch=False, use_llm=False)
    assert cat["identity_mode"] == "per_field" and cat["contract"]["identity_design"] == "per_field"
    v["required"] = ["musteri_no", "dogum_tarihi", "telefon_son4"]
    cat = C.build_catalog(docs_of(doc), MOCK, None, fetch=False, use_llm=False)
    assert cat["contract"]["identity_design"] == "all_at_once"


def test_identity_design_multi_op_with_llm_tiebreak(fake_llm):
    doc = turkish_variant()
    op = copy.deepcopy(doc["paths"]["/kimlik/dogrula"]["post"])
    op["operationId"] = "kimlikDogrulaTelefon"
    doc["paths"]["/kimlik/dogrula-telefon"] = {"post": op}
    calls = fake_llm({"contract_map": lambda req: {"map": [
        {"tool": "verify_identity", "operation": "POST /kimlik/dogrula"}] + [
        {"tool": t, "operation": k} for t, k in (
            ("get_account", "POST /musteri/borc-ozeti"), ("create_promise", "POST /odeme-sozu/kaydet"),
            ("add_note", "POST /musteri/not-ekle"), ("schedule_callback", "POST /geri-arama/planla"),
            ("transfer_to_agent", "POST /temsilciye-aktar"), ("close_call", "POST /gorusme/kapat"))]}})
    cat = C.build_catalog(docs_of(doc), MOCK, None, fetch=False)
    assert [c["purpose"] for c in calls] == ["contract_map"]
    assert "POST /kimlik/dogrula-telefon" in calls[0]["prompt"]
    assert cat["contract"]["identity_design"] == "multi_op"
    assert cat["contract"]["op_map"]["verify_identity"] == "POST /kimlik/dogrula"
    assert "POST /kimlik/dogrula-telefon" in cat["contract"]["extra_operations"]


def test_tiebreak_invalid_answer_is_repaired_then_failure_keeps_word_mapping(fake_llm):
    doc = turkish_variant()
    doc["paths"]["/hesap/ozet"] = {"post": {"operationId": "hesapOzet", "summary": "hesap özeti"}}
    calls = fake_llm({"contract_map": {"map": [{"tool": "get_account", "operation": "POST /yok"}]}})
    cat = C.build_catalog(docs_of(doc), MOCK, None, fetch=False)
    assert len(calls) == 1 + llm.MAX_REPAIRS                                 # validated, repaired, then given up
    assert "is not one of the listed operations" in calls[1]["prompt"]
    assert cat["contract"]["op_map"]["get_account"] in ("POST /musteri/borc-ozeti", "POST /hesap/ozet")


# ------------------------------------------------------------------------------------ prose contract (LLM path)

PROSE = """# Servis Sözleşmesi

Tüm servisler JSON alır ve döner. Taban adres ortama göre değişir.

| Servis | Yöntem | Yol | Açıklama |
|---|---|---|---|
| Kimlik doğrulama | POST | /v1/kimlik-dogrula | Bir kimlik sorusunun cevabını kontrol eder |
| Borç sorgulama | POST | /v1/borc-sorgula | Müşterinin ürünlerini ve gecikmiş borcunu döner |
| Ödeme sözü | POST | /v1/odeme-sozu | Ödeme sözünü kaydeder |
| Görüşme sonu | POST | /v1/gorusme-sonu | Görüşme sonucunu kaydeder |

## POST /v1/kimlik-dogrula
Girdi: `musteri_no` (zorunlu), `soru_tipi` (DOGUM_TARIHI veya TEL_SON4), `cevap` (zorunlu).
Çıktı: `sonuc_kodu` = BASARILI | HATALI, `dogrulandi` (bool), `kalan_deneme` (sayı).

## POST /v1/borc-sorgula
Girdi: `musteri_no`. Çıktı: `sonuc_kodu`, `urun_listesi`: her biri `urun_no`, `urun_turu` (KART | KREDI),
`gecikmis_tutar` (TL), `gecikme_gun_sayisi`, `asgari_tutar`.

## POST /v1/odeme-sozu
Girdi: `musteri_no`, `urun_no`, `soz_tutari` (TL), `soz_tarihi` (YYYY-MM-DD). Çıktı: `sonuc_kodu`, `soz_no`.

## POST /v1/gorusme-sonu
Girdi: `musteri_no`, `sonuc` (SOZ_ALINDI | SOZ_YOK | DOGRULANAMADI), `aciklama`. Çıktı: `sonuc_kodu`.

Hata kodları: 400 eksik alan, 404 müşteri yok.
"""


def leaf(name, type_="string", required=False, enum=None, role="", description="", fmt="", items=None):
    d = {"name": name, "type": type_, "required": required, "enum": enum or [], "format": fmt,
         "description": description, "role": role}
    if items is not None:
        d["items"] = items
    return d


def prose_answer():
    ok = {"field": "sonuc_kodu", "values": ["BASARILI"]}
    sk = leaf("sonuc_kodu", enum=["BASARILI", "HATALI"])
    return {"operations": [
        {"name": "kimlik-dogrula", "method": "POST", "path": "/v1/kimlik-dogrula", "tool": "verify_identity",
         "summary": "Kimlik doğrulama",
         "request": [leaf("musteri_no", required=True, role="customer"),
                     leaf("soru_tipi", required=True, enum=["DOGUM_TARIHI", "TEL_SON4"], role="selector"),
                     leaf("cevap", required=True, role="answer")],
         "response": [sk, leaf("dogrulandi", "boolean", role="verified"), leaf("kalan_deneme", "integer", role="left")],
         "success": ok, "errors": [{"code": "404", "meaning": "müşteri yok"}]},
        {"name": "borc-sorgula", "method": "POST", "path": "/v1/borc-sorgula", "tool": "get_account",
         "request": [leaf("musteri_no", required=True, role="customer")],
         "response": [sk, leaf("urun_listesi", "array", role="products", items=[
             leaf("urun_no", role="id"), leaf("urun_turu", enum=["KART", "KREDI"], role="type"),
             leaf("gecikmis_tutar", "number", role="past_due"), leaf("gecikme_gun_sayisi", "integer", role="days_late"),
             leaf("asgari_tutar", "number")])],
         "success": ok},
        {"name": "odeme-sozu", "method": "POST", "path": "/v1/odeme-sozu", "tool": "create_promise",
         "request": [leaf("musteri_no", required=True, role="customer"), leaf("urun_no", required=True, role="product"),
                     leaf("soz_tutari", "number", True, role="amount"),
                     leaf("soz_tarihi", required=True, fmt="date", description="YYYY-MM-DD", role="date")],
         "response": [sk, leaf("soz_no", role="pid")], "success": ok},
        {"name": "gorusme-sonu", "method": "POST", "path": "/v1/gorusme-sonu", "tool": "close_call",
         "request": [leaf("musteri_no", required=True, role="customer"),
                     leaf("sonuc", required=True, enum=["SOZ_ALINDI", "SOZ_YOK", "DOGRULANAMADI"], role="outcome"),
                     leaf("aciklama", role="text")],
         "response": [sk], "success": ok},
    ], "notes": ["400 eksik alan"]}


def test_prose_contract_derived_by_one_llm_call(tmp_path, fake_llm):
    calls = fake_llm({"contract": prose_answer()})
    cat = C.build_catalog([{"name": "Servis_Sozlesmesi.md", "text": PROSE},
                           {"name": "BRIEF.md", "text": "Görev tanımı."}], MOCK, tmp_path, fetch=False)
    assert [c["purpose"] for c in calls] == ["contract"]
    assert "Servis_Sozlesmesi.md" in calls[0]["prompt"] and "Görev tanımı" not in calls[0]["prompt"]
    assert "credit" not in calls[0]["system"].lower()
    con = cat["contract"]
    assert con["source"] == "LLM from Servis_Sozlesmesi.md"
    assert con["op_map"]["verify_identity"] == "POST /v1/kimlik-dogrula"
    assert con["absent"] == ["add_note", "schedule_callback", "transfer_to_agent"]
    assert con["notes"] == ["400 eksik alan"]
    t = cat["tools"]
    assert t["create_promise"]["url"] == MOCK + "/v1/odeme-sozu"
    assert t["create_promise"]["roles"]["request"] == {"customer": "musteri_no", "product": "urun_no",
                                                      "amount": "soz_tutari", "date": "soz_tarihi"}
    assert t["create_promise"]["request"]["soz_tarihi"]["wire_format"] == "%Y-%m-%d"
    assert t["create_promise"]["success"] == {"role": "s", "kind": "enum_in", "values": ["BASARILI"]}
    assert t["verify_identity"]["roles"]["request"]["selector"] == "soru_tipi"
    assert cat["enums"]["identity_field"] == ["DOGUM_TARIHI", "TEL_SON4"]
    assert t["get_account"]["roles"]["item"] == {"id": "urun_no", "type": "urun_turu", "past_due": "gecikmis_tutar",
                                                 "days_late": "gecikme_gun_sayisi"}
    assert t["get_account"]["item_extras"]["floor"] == "asgari_tutar"
    assert cat["enums"]["outcome"] == ["SOZ_ALINDI", "SOZ_YOK", "DOGRULANAMADI"]
    assert t["close_call"]["roles"]["request"]["outcome"] == "sonuc"
    written = json.loads((tmp_path / "openapi.json").read_text())
    assert written["paths"]["/v1/odeme-sozu"]["post"]["x-freya-tool"] == "create_promise"
    assert written["paths"]["/v1/kimlik-dogrula"]["post"]["x-freya-errors"] == [{"code": "404", "meaning": "müşteri yok"}]


def test_prose_contract_hallucinations_are_repaired(fake_llm):
    bad = prose_answer()
    bad["operations"][0]["request"][1]["enum"] = ["dogum_tarihi", "TEL_SON4"]       # value not copied exactly
    bad["operations"][1]["request"].append(leaf("kanal_kodu"))                     # field not in the contract
    bad["operations"].pop(3)                                                      # a named path missing
    answers = [bad, prose_answer()]
    calls = fake_llm({"contract": lambda req: answers[min(req["attempt"], 2) - 1]})
    cat = C.build_catalog([{"name": "Servis_Sozlesmesi.md", "text": PROSE}], MOCK, None, fetch=False)
    assert len(calls) == 2
    repair = calls[1]["prompt"]
    assert "'dogum_tarihi' is not written in the contract" in repair
    assert "'kanal_kodu' is not written in the contract" in repair
    assert "'/v1/gorusme-sonu' but no operation has it" in repair
    assert cat["contract"]["absent"] == ["add_note", "schedule_callback", "transfer_to_agent"]


def test_check_operations_rules():
    m = prose_answer()
    assert C.check_operations(m, PROSE)[0] == []
    m["operations"].append(copy.deepcopy(m["operations"][0]))
    m["operations"][-1]["path"] = "v1/kimlik-dogrula"
    errs, _ = C.check_operations(m, PROSE)
    assert any("must start with '/'" in e for e in errs)
    assert C.check_operations({"operations": []}, "x")[0][0].startswith("/operations: empty")
    dup = prose_answer()
    dup["operations"].append(copy.deepcopy(dup["operations"][0]))
    assert any("duplicate operation" in e for e in C.check_operations(dup, PROSE)[0])
    s = prose_answer()
    s["operations"][0]["success"]["values"] = ["XQZW"]
    assert any("success/values" in e for e in C.check_operations(s, PROSE)[0])
    _, warns = C.check_operations(prose_answer(), PROSE + "\nAyrıca `ek_alan_adi` alanı.")
    assert warns == ["contract names 'ek_alan_adi' but no operation field / enum carries it"]


def test_mentioned_paths_and_identifiers():
    text = ("GET /a/b and `POST` `/c-d/{id}` | /e_f | x\nhttps://host.example/v1/zz 10/11/2026 ve/veya /1/2 "
            "`musteri_no` `camelCase` `plain` `a.b_c`")
    assert C.mentioned_paths(text) == ["/a/b", "/c-d/{id}", "/e_f"]
    assert C.mentioned_identifiers(text) == ["musteri_no", "camelCase", "a.b_c"]


def test_operations_to_openapi_shapes():
    doc = C.operations_to_openapi(prose_answer())
    op = doc["paths"]["/v1/borc-sorgula"]["post"]
    res = op["responses"]["200"]["content"]["application/json"]["schema"]
    assert res["properties"]["urun_listesi"]["items"]["properties"]["urun_no"]["x-freya-role"] == "id"
    assert res["properties"]["sonuc_kodu"]["x-freya-success"] == ["BASARILI"]
    assert op["x-freya-tool-hint"] == "get_account"
    nested = C.operations_to_openapi({"operations": [{"name": "n", "method": "POST", "path": "x", "tool": "other",
        "request": [leaf("")], "response": [{"name": "veri", "type": "object", "fields": [leaf("ic", role="s")]}]}]})
    sch = nested["paths"]["/x"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert sch["properties"]["veri"]["properties"]["ic"]["x-freya-role"] == "s"
    assert "x-freya-tool-hint" not in nested["paths"]["/x"]["post"]


def test_contract_docs_selection_without_kinds():
    case = C._coerce_case([{"name": "Ekler/API_Tanimi.docx", "text": "x"}, {"name": "notlar.md",
                           "text": "POST /a\nPOST /b"}, {"name": "README.md", "text": "y"}])
    assert [d["name"] for d in case["contract_docs"]] == ["Ekler/API_Tanimi.docx", "notlar.md"]
    with pytest.raises(OM.CatalogError, match="no service contract text"):
        C.derive_operations([{"name": "x", "text": "  "}])


def test_case_folder_path_goes_through_ingest(tmp_path, no_llm):
    (tmp_path / "BRIEF.md").write_text("Görev.")
    (tmp_path / "servis.json").write_text(json.dumps(turkish_variant()))
    cat = C.build_catalog(str(tmp_path), MOCK, tmp_path / "run", fetch=False, use_llm=False)
    assert cat["contract"]["op_map"]["close_call"] == "POST /gorusme/kapat"
    assert (tmp_path / "run" / "openapi.json").exists()


def test_cli_writes_derived_openapi(tmp_path, no_llm, capsys):
    case = tmp_path / "case"
    case.mkdir()
    (case / "servis.json").write_text(json.dumps(turkish_variant()))
    out = tmp_path / "mock" / "openapi.json"
    out.parent.mkdir()
    assert C.main([str(case), MOCK, "--out", str(out), "--no-llm", "--no-fetch"]) == 0
    doc = json.loads(out.read_text())
    assert doc["servers"] == [{"url": MOCK}] and "/musteri/borc-ozeti" in doc["paths"]
    outtxt = capsys.readouterr().out
    printed = json.loads(outtxt[outtxt.index("{\n"):])
    assert printed["op_map"]["get_account"] == "POST /musteri/borc-ozeti"


# ---------------------------------------------------------------------------------- scoring / words

@pytest.mark.parametrize("path,op_id,summary,tool", [
    ("/kimlik/dogrulama", "", "", "verify_identity"),
    ("/api/verifyCustomer", "", "", "verify_identity"),
    ("/hesap/ekstre", "", "", "get_account"),
    ("/x/y", "getDebtSummary", "", "get_account"),
    ("/taahhut/olustur", "", "", "create_promise"),
    ("/x/promiseToPay", "", "", "create_promise"),
    ("/kayit/notu", "", "", "add_note"),
    ("/randevu", "", "", "schedule_callback"),
    ("/x", "", "Müşteriyi temsilciye yönlendirir", "transfer_to_agent"),
    ("/cagri/sonlandir", "", "", "close_call"),
    ("/x/wrapUp", "", "", "close_call"),
])
def test_op_scores_best_tool(path, op_id, summary, tool):
    sc = C.op_scores(path, {"operationId": op_id, "summary": summary})
    assert max(sc, key=sc.get) == tool


def test_short_words_match_whole_tokens_only():
    assert "add_note" not in C.op_scores("/nothing/notify", {})
    assert C.op_scores("/x", {"x-freya-tool-hint": "add_note"}) == {"add_note": 4}


def test_turkish_fold_and_name_normalisation():
    assert OM.fold("MÜŞTERİ Iğdır çÖz") == "musteri igdir coz"
    assert OM._n("müşteriNo") == "musteri_no"
    assert OM._n("daysLate") == "days_late"


@pytest.mark.parametrize("field,role", [
    ("musteri_numarasi", "customer"), ("kart_no", "product"), ("odeme_tutari", "amount"),
    ("vade_tarihi", "date"), ("arama_saati", "time"), ("hedef_ekip", "queue"), ("gorusme_sonucu", "outcome"),
    ("kapanis_kodu", "outcome"), ("ret_sebebi", "reason"), ("not_metni", "text"),
])
def test_turkish_request_field_roles(field, role):
    req = {field: OM._request_leaf(field, {"type": "string"}, True)}
    assert OM._bind_request("create_promise", req) == {role: field}


def test_item_debt_fallback_and_floor_not_past_due():
    items = {"kart_no": {"type": "string", "enum": [], "description": ""},
             "asgari_tutar": {"type": "number", "enum": [], "description": ""},
             "toplam_borc": {"type": "number", "enum": [], "description": ""}}
    roles = OM._bind_items("get_account", items)
    assert roles == {"id": "kart_no", "past_due": "toplam_borc"}
    assert OM._item_extras(items, roles) == {"floor": "asgari_tutar"}


def test_x_freya_role_hints_win():
    req = {"alan1": OM._request_leaf("alan1", {"type": "string"}, True)}
    assert OM._bind_request("create_promise", req, {"alan1": "amount", "yok": "date"}) == {"amount": "alan1"}
    assert OM._bind_response("x", {"a": {"type": "string", "enum": []}}, {"a": "pid"}) == {"pid": "a"}
    assert OM._bind_items("x", {"a": {"type": "number", "enum": []}}, {"a": "past_due", "b": "bogus"}) == \
        {"past_due": "a"}


def test_success_hint_and_turkish_success_words():
    resp = {"durum": {"type": "string", "enum": ["ISLENDI", "RED"], "description": "", "path": "data.durum"}}
    roles = OM._bind_response("x", resp)
    assert roles == {"s": "durum"}
    assert OM._success(resp, roles) == {"role": "s", "kind": "enum_in", "values": ["ISLENDI"]}
    assert OM._success(resp, roles, ["RED"]) == {"role": "s", "kind": "enum_in", "values": ["RED"]}
    assert OM._success(resp, roles, ["NOPE"])["values"] == ["ISLENDI"]
    env = {"properties": {"sonuc": {"type": "object", "properties": {"kod": {"x-freya-success": ["00", None]}}}}}
    assert OM._success_hint(env, "kod") == ["00"]
    assert OM._success_hint({}, "kod") == []


def test_non_strict_build_reports_missing_and_problems():
    doc = copy.deepcopy(KIT)
    doc["paths"].pop("/add_note")
    out = OM.build_catalog(doc, strict=False)
    assert out["missing_tools"] == ["add_note"] and out["tools"] == {}
    with pytest.raises(OM.CatalogError):
        OM.build_catalog(doc)


# --------------------------------------------------------------------------------------------- build.py hook

def test_derive_openapi_hook_returns_loadable_annotated_file(tmp_path, no_llm):
    case = {"docs": [], "contract_docs": [], "openapi": turkish_variant(), "openapi_path": "servis.json",
            "mock_url": MOCK}
    path = C.derive_openapi(case, tmp_path)
    assert path == str(tmp_path / "openapi.json")
    cat = OM.load(path)                                   # strict D.1 load binds the renamed operations
    assert cat["tools"]["close_call"]["url"] == MOCK + "/gorusme/kapat"
    assert cat["tools"]["create_promise"]["roles"]["request"]["amount"] == "tutar"
    report = json.loads((tmp_path / "contract.json").read_text())
    assert report["extra_operations"] == ["POST /kampanya/liste"]


def test_derive_openapi_hook_with_absent_services_still_loads(tmp_path, no_llm):
    doc = turkish_variant()
    doc["paths"].pop("/gorusme/kapat")
    path = C.derive_openapi({"docs": [], "openapi": doc, "mock_url": MOCK}, tmp_path)
    cat = OM.load(path)
    assert cat["tools"]["close_call"]["url"] == MOCK + "/_freya/close_call"


def test_derive_openapi_hook_failure_returns_none(tmp_path, no_llm):
    assert C.derive_openapi({"docs": [{"name": "README.md", "text": "x"}], "mock_url": MOCK}, tmp_path) is None
