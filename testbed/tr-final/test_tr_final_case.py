"""Tests for the Turkish rehearsal case (testbed/tr-final). Run explicitly (pytest.ini's testpaths is tests/):

    .venv/bin/python -m pytest testbed/tr-final -q

They prove the case is internally consistent (conversations obey the BRIEF, files agree with case_data, the answer
keys match), that the checker really catches rule breaks (mutations), and that no rehearsal token leaked into
builder/ runtime/ harness/.
"""
import copy
import datetime as dt
import hashlib
import json
import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import case_data as C  # noqa: E402
import check_case as K  # noqa: E402
import make_case as M  # noqa: E402

D = C.d


@pytest.fixture(scope="module", autouse=True)
def generated():
    """Regenerate once; the files on disk must be byte-identical (except the Chrome-printed PDF)."""
    files = [p for p in HERE.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".py"]
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    M.main()
    after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.exists()}
    yield before, after


def test_regeneration_is_deterministic(generated):
    before, after = generated
    changed = [str(p.relative_to(HERE)) for p in before if before[p] != after.get(p)]
    assert not changed, changed


def test_whole_case_has_no_problems():
    assert K.run_all() == []


# ---------------------------------------------------------------- calendar facts the cases rely on
@pytest.mark.parametrize("now,days_late,want", [
    ("2026-10-21T10:30", 6, "2026-11-02"),    # erken: 7th business day, skips 29 Ekim
    ("2026-10-21T13:00", 44, "2026-10-26"),   # geç before DUY-2026-034: 3rd business day
    ("2026-10-27T14:00", 22, "2026-11-02"),   # 28 (arife counts), 30, 2 Kasım
    ("2026-11-02T09:00", 30, "2026-11-04"),   # DUY-2026-034 from its effective day: 2nd business day
    ("2026-11-03T10:00", 40, "2026-11-05"),
    ("2026-11-03T10:00", 8, "2026-11-12"),
    ("2026-10-22T09:45", 3, "2026-11-03"),
])
def test_deadlines(now, days_late, want):
    assert C.deadline(now, days_late) == D(want)


def test_band_edges():
    assert C.band(1)[0] == "erken" and C.band(15)[0] == "erken" and C.band(16)[0] == "geç" and C.band(60)[0] == "geç"
    with pytest.raises(ValueError):
        C.band(61)


def test_arife_is_business_day_holiday_is_not():
    assert C.is_bd(D("2026-10-28")) and not C.is_bd(D("2026-10-29")) and C.is_bd(D("2026-12-31"))
    assert C.next_bd_on_or_after(D("2026-10-29")) == D("2026-10-30")


def test_last_business_day_of_week():
    assert C.last_bd_of_week(D("2026-10-21")) == D("2026-10-23")
    assert C.last_bd_of_week(D("2026-10-23")) == D("2026-10-30")      # today is that day -> next week
    assert C.last_bd_of_week(D("2026-11-03")) == D("2026-11-06")


def test_callback_windows_follow_announcement_and_arife():
    assert C.callback_windows("2026-10-16T10:00", D("2026-10-16")) == [("09:00", "18:00")]
    assert C.callback_windows("2026-10-19T10:00", D("2026-10-19")) == [("09:00", "20:00")]
    assert C.callback_windows("2026-10-27T17:15", D("2026-10-28")) == [("09:00", "12:30")]


def test_turkish_formats():
    assert C.tl(8450.75) == "8.450,75 TL" and C.tl(14200) == "14.200,00 TL" and C.tl(926.24) == "926,24 TL"
    assert C.tr_date(D("2026-10-30")) == "30 Ekim 2026 Cuma"
    assert C.ddmmyyyy("1990-11-30") == "30.11.1990"


def test_banned_word_morphology():
    assert K.banned_hits("Borcunuz var") == ["borc"]
    assert set(K.banned_hits("Kartınızın ödemesi gecikmeli")) == {"kart", "ödem", "gecik"}
    assert K.banned_hits("İyi günler, KREDİ KARTI") == ["kart"]
    assert K.banned_hits("Güvenliğiniz için iki soru soracağım.") == []


# ---------------------------------------------------------------- the checker catches rule breaks
def _conv(cid):
    return copy.deepcopy(next(c for c in C.conversations() if c["id"] == cid))


def _set_turn(conv, pred, fn):
    for i, t in enumerate(conv["turns"]):
        if pred(t):
            conv["turns"][i] = fn(t)
            return conv
    raise AssertionError("turn not found")


def test_mutation_banned_word_before_verification():
    conv = _conv("TRF-03")
    conv = _set_turn(conv, lambda t: t[0] == "A" and "ulaşabiliriz" in t[1],
                     lambda t: ("A", "Zeynep Hanım'ın kart borcu hakkında arıyorum."))
    assert any("banned word" in x for x in K.check_conversation(conv))


def test_mutation_promise_on_holiday():
    conv = _conv("TRF-02")
    conv = _set_turn(conv, lambda t: t[0] == "S" and t[1] == "OdemeSozuKaydet",
                     lambda t: ("S", t[1], dict(t[2], odeme_tarihi="2026-10-29"), t[3], t[4]))
    assert any("not a business day" in x for x in K.check_conversation(conv))


def test_mutation_stale_late_band_deadline():
    """A build that ignores DUY-2026-034 offers 6 Kasım (3rd business day) on 3 Kasım: caught."""
    conv = _conv("TRF-06")
    conv = _set_turn(conv, lambda t: t[0] == "S" and t[1] == "OdemeSozuKaydet",
                     lambda t: ("S", t[1], dict(t[2], odeme_tarihi="2026-11-06"), t[3], t[4]))
    assert any("not a business day in" in x for x in K.check_conversation(conv))


def test_mutation_wrong_soz_tipi_and_amount():
    conv = _conv("TRF-11")
    conv = _set_turn(conv, lambda t: t[0] == "S" and t[1] == "OdemeSozuKaydet",
                     lambda t: ("S", t[1], dict(t[2], tutar=2000.0, soz_tipi="ASGARI"), t[3], t[4]))
    bad = K.check_conversation(conv)
    assert any("outside [asgari" in x for x in bad) and any("soz_tipi" in x for x in bad)


def test_mutation_callback_on_arife_evening():
    conv = _conv("TRF-03")
    conv = _set_turn(conv, lambda t: t[0] == "S" and t[1] == "GeriAramaPlanla",
                     lambda t: ("S", t[1], dict(t[2], saat="19:00"), t[3], t[4]))
    assert any("outside" in x for x in K.check_conversation(conv))


def test_mutation_close_pair_and_order():
    conv = _conv("TRF-07")
    conv = _set_turn(conv, lambda t: t[0] == "S" and t[1] == "GorusmeKapat",
                     lambda t: ("S", t[1], dict(t[2], gerekce_kodu="TEMSILCI"), t[3], t[4]))
    assert any("closing table" in x or "SISTEM_HATASI" in x for x in K.check_conversation(conv))
    conv = _conv("TRF-01")
    conv["turns"].append(("S", "NotEkle", {"musteri_no": "x"}, {"basarili": True}, 200))
    assert any("exactly once, last" in x for x in K.check_conversation(conv))


def test_mutation_recorded_said_after_failure():
    conv = _conv("TRF-07")
    conv = _set_turn(conv, lambda t: t[0] == "A" and t[1].startswith("Üzgünüm"),
                     lambda t: ("A", "Ödeme sözünüz kaydedildi. " + C.SMS))
    bad = K.check_conversation(conv)
    assert any("kaydedildi" in x for x in bad)


def test_mutation_identity_response_and_swap_hint():
    conv = _conv("TRF-04")
    conv = _set_turn(conv, lambda t: t[0] == "S" and t[2].get("cevap") == "04.09.1979",
                     lambda t: ("S", t[1], t[2], {"basarili": True, "dogrulandi": False, "kalan_hak": 2,
                                                  "tum_sorular_tamam": False}, 200))
    assert any("swap hint" in x for x in K.check_conversation(conv))


# ---------------------------------------------------------------- files and answer keys
def test_xlsx_dates_are_real_date_cells():
    """The trap the ingest must handle: dates are serial numbers with a date format, not strings."""
    import zipfile
    with zipfile.ZipFile(HERE / "FreyaBank-Rehearsal" / "test-musterileri.xlsx") as z:
        sheet = z.read("xl/worksheets/sheet1.xml").decode()
    serial = (dt.date(1986, 2, 14) - dt.date(1899, 12, 30)).days
    assert f"<v>{serial}</v>" in sheet and "1986" not in sheet
    rows = K.xlsx_rows(HERE / "FreyaBank-Rehearsal" / "test-musterileri.xlsx")
    assert rows["Müşteriler"][1][4] == "1986-02-14"
    assert any(r[5] == "0285" for r in rows["Müşteriler"][1:])       # leading zero kept (text cell)


def test_drawio_both_forms_decode():
    a = K.drawio_labels(HERE / "FreyaBank-Rehearsal" / "akis.drawio")
    b = K.drawio_labels(HERE / "FreyaBank-Rehearsal-md" / "akis.drawio")
    assert a == b and len(a) > 15


def test_cases_json_matches_conversations():
    cases = json.loads((HERE / "cases.json").read_text())
    convs = {c["id"]: c for c in C.conversations()}
    for case in cases:
        conv = convs[case["id"]]
        assert case["expected_ledger"] == C.ledger(conv)
        assert case["customer_lines"] == [t[1] for t in conv["turns"] if t[0] == "M"]
        assert case["variables"]["now"] == conv["now"]
    by = {c["id"]: c["expected"] for c in cases}
    assert by["TRF-01"]["promises"] == [{"product_id": "KRT-240117-01", "amount": 8450.75, "date": "2026-10-21"}]
    assert by["TRF-02"]["promises"][0]["date"] == "2026-10-30"
    assert by["TRF-03"]["callbacks"] == [{"date": "2026-10-28", "time": "11:00"}]
    assert (by["TRF-04"]["outcome"], by["TRF-04"]["notes"][0]["reason"]) == ("paid", "paid")
    assert by["TRF-05"]["transfers"] == [{"queue": "support"}] and by["TRF-05"]["reason"] == "support"
    assert by["TRF-06"]["promises"][0]["date"] == "2026-11-05" and by["TRF-06"]["notes"][0]["reason"] == "dispute"
    assert by["TRF-07"]["promises"] == [] and by["TRF-07"]["reason"] == "service_error"
    assert by["TRF-08"]["outcome"] == "not_verified" and by["TRF-09"]["reason"] == "refused"
    assert by["TRF-10"]["transfers"] == [{"queue": "restructuring"}]
    assert by["TRF-11"]["promises"][0] == {"product_id": "KRT-241142-01", "amount": 2904.1, "date": "2026-10-28"}
    assert by["TRF-12"]["promises"][0]["date"] == "2026-10-26"
    assert by["TRF-13"]["callbacks"] == [{"date": "2026-10-21", "time": "19:30"}]


def test_expected_json_core_values():
    exp = json.loads((HERE / "expected.json").read_text())
    L = exp["leaves"]
    assert L["/bank/language"] == "tr" and L["/call_variables/customer_key"] == "musteri_no"
    assert L["/identity/questions/0/wire_format"] == "%d.%m.%Y"
    assert L["/calendar/holidays"][0] == "2026-10-29" and "2026-10-28" not in L["/calendar/holidays"]
    assert "2026-12-31" not in L["/calendar/holidays"]
    assert [b["deadline"]["n"] for b in L["/bands"]] == [7, 3]
    assert exp["dated_overrides"][0]["value"] == 2 and exp["dated_overrides"][0]["effective_from"] == "2026-11-02"
    assert exp["code_list"]["queue"]["MUSTERI_TEMSILCISI"] == "general"
    assert ["AKTARILDI", "TEMSILCI"] in exp["code_list"]["close_pairs"]


def test_mock_reference_data():
    mock = json.loads((HERE / "reference" / "mock-customers.json").read_text())
    assert len(mock) == len(C.CUSTOMERS)
    selin = next(m for m in mock if m["customer_id"] == "FB-240744")
    assert selin["faults"] == {"OdemeSozuKaydet": "E500"} and selin["identity"]["DOGUM_TARIHI"] == "04.08.1995"
    oa = json.loads((HERE / "reference" / "openapi.json").read_text())
    body = oa["paths"]["/odeme-sozu/kaydet"]["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert body["properties"]["soz_tipi"]["enum"] == ["TAMAMI", "ASGARI", "KISMI"]
    assert set(body["required"]) == {"musteri_no", "kart_id", "tutar", "odeme_tarihi", "soz_tipi"}


def test_no_rehearsal_token_in_builder_runtime_harness():
    assert K.check_leak() == []
