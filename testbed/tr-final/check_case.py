"""Self-check for the Turkish rehearsal case: the conversations obey the BRIEF's own rules, the generated files say
what case_data says, and no rehearsal token leaked into builder/ runtime/ harness/.

    .venv/bin/python testbed/tr-final/check_case.py      # prints problems, exit 1 if any
Also used by testbed/tr-final/test_tr_final_case.py. Standard library only (pdftotext optional).
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
import zlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))

import case_data as C  # noqa: E402

CASE = HERE / "FreyaBank-Rehearsal"
CASE_MD = HERE / "FreyaBank-Rehearsal-md"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
BANNED_STEMS = ["borç", "borc", "ödem", "ekstre", "kart", "gecik", "tahsilat", "asgari", "tutar", "faiz"]


def tr_lower(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def banned_hits(text: str) -> list[str]:
    low = tr_lower(text)
    return [b for b in BANNED_STEMS if re.search(r"(?<![a-zçğıöşü])" + b, low)]


# ---------------------------------------------------------------- readers (independent of the builder's ingest)
def docx_text(path) -> str:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    out = []
    for p in root.iter(W + "p"):
        t = "".join(x.text or "" for x in p.iter(W + "t"))
        if t.strip():
            out.append(t)
    return "\n".join(out)


def xlsx_rows(path) -> dict:
    """{sheet name: [[cell values]]}; date-formatted numbers come back as ISO dates."""
    with zipfile.ZipFile(path) as z:
        shared = ["".join(t.text or "" for t in si.iter(S + "t"))
                  for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(S + "si")]
        st = ET.fromstring(z.read("xl/styles.xml"))
        fmts = {nf.get("numFmtId"): nf.get("formatCode") for nf in st.iter(S + "numFmt")}
        xfs = [xf.get("numFmtId") for xf in st.find(S + "cellXfs").findall(S + "xf")]

        def is_date(s):
            if s is None:
                return False
            nid = xfs[int(s)]
            code = fmts.get(nid, "")
            return nid in {"14", "15", "16", "17", "22"} or ("yy" in code.lower() and "d" in code.lower())
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        names = [sh.get("name") for sh in wb.iter(S + "sheet")]
        out = {}
        for i, name in enumerate(names):
            rows = []
            for row in ET.fromstring(z.read(f"xl/worksheets/sheet{i + 1}.xml")).iter(S + "row"):
                vals = []
                for c in row.findall(S + "c"):
                    v = c.find(S + "v")
                    if c.get("t") == "s":
                        vals.append(shared[int(v.text)])
                    elif is_date(c.get("s")):
                        vals.append((dt.date(1899, 12, 30) + dt.timedelta(days=int(float(v.text)))).isoformat())
                    else:
                        x = float(v.text)
                        vals.append(int(x) if x.is_integer() and "." not in v.text else x)
                rows.append(vals)
            out[name] = rows
        return out


def drawio_labels(path) -> list[str]:
    root = ET.fromstring(pathlib.Path(path).read_text())
    labels = []
    for diagram in root.iter("diagram"):
        model = diagram.find("mxGraphModel")
        if model is None and (diagram.text or "").strip():
            raw = zlib.decompress(base64.b64decode(diagram.text.strip()), -15)
            model = ET.fromstring(urllib.parse.unquote(raw.decode()))
        for cell in model.iter("mxCell"):
            v = cell.get("value")
            if v:
                labels.append(re.sub(r"<br\s*/?>", " ", v))
    return labels


# ---------------------------------------------------------------- conversation rules
def check_conversation(conv) -> list[str]:
    bad = []
    cid = conv["id"]
    c = C.BY_ID[conv["musteri_no"]]
    cards = {k["kart_id"]: k for k in c["kartlar"]}
    now = conv["now"]
    today = C.d(now)
    turns = conv["turns"]
    agent = [t[1] for t in turns if t[0] == "A"]
    services = [t for t in turns if t[0] == "S"]
    if not agent or not agent[0].startswith(C.OPENING):
        bad.append(f"{cid}: first agent line does not start with the opening sentence")
    # banned words before verification
    verified = False
    for t in turns:
        if t[0] == "S" and t[1] == "KimlikDogrula" and t[3].get("tum_sorular_tamam"):
            verified = True
        if t[0] == "A" and not verified and banned_hits(t[1]):
            bad.append(f"{cid}: banned word before verification {banned_hits(t[1])}: {t[1]!r}")
    # identity answers consistent with the test customer
    wrong = 0
    for t in services:
        if t[1] != "KimlikDogrula":
            continue
        q, ans, r = t[2]["soru"], t[2]["cevap"], t[3]
        truth = C.ddmmyyyy(c["dogum_tarihi"]) if q == "DOGUM_TARIHI" else c["tckn_son4"]
        if r.get("dogrulandi") != (ans == truth):
            bad.append(f"{cid}: KimlikDogrula response disagrees with the customer data for {ans}")
        if q == "DOGUM_TARIHI" and not re.fullmatch(r"\d\d\.\d\d\.\d{4}", ans):
            bad.append(f"{cid}: DOB not in GG.AA.YYYY: {ans}")
        swapped = q == "DOGUM_TARIHI" and ans != truth and ans[3:5] + "." + ans[:2] + ans[5:] == truth
        if swapped != (r.get("ipucu") == "GUN_AY_YER_DEGISTI"):
            bad.append(f"{cid}: swap hint wrong for {ans}")
        if ans != truth and not swapped:
            wrong += 1
            if r.get("kalan_hak") != 3 - wrong:
                bad.append(f"{cid}: kalan_hak should be {3 - wrong}")
    if any(t[1] == "EkstreBorcSorgula" for t in services) and not verified:
        bad.append(f"{cid}: statement read before verification")
    # service order: exactly one close, last
    closes = [i for i, t in enumerate(services) if t[1] == "GorusmeKapat"]
    if len(closes) != 1 or closes[0] != len(services) - 1:
        bad.append(f"{cid}: GorusmeKapat must be called exactly once, last")
    close = services[closes[-1]][2] if closes else {}
    if (close.get("sonuc_kodu"), close.get("gerekce_kodu")) not in [(o, r) for o, r, _ in C.CLOSE_TABLE]:
        bad.append(f"{cid}: close pair not in the closing table: {close}")
    # promises
    promised = set()
    for i, t in enumerate(turns):
        if t[0] != "S" or t[1] != "OdemeSozuKaydet":
            continue
        b = t[2]
        k = cards.get(b["kart_id"])
        if not k:
            bad.append(f"{cid}: promise on unknown card {b['kart_id']}")
            continue
        day = C.d(b["odeme_tarihi"])
        dl = C.deadline(now, k["gecikme_gun_sayisi"])
        if not (today <= day <= dl and C.is_bd(day)):
            bad.append(f"{cid}: promise date {day} not a business day in [{today}, {dl}]")
        if not (k["asgari_odeme_tutari"] <= b["tutar"] <= k["ekstre_borcu"]):
            bad.append(f"{cid}: promise amount {b['tutar']} outside [asgari, borç]")
        tip = ("TAMAMI" if b["tutar"] == k["ekstre_borcu"] else "ASGARI" if b["tutar"] == k["asgari_odeme_tutari"]
               else "KISMI")
        if b["soz_tipi"] != tip:
            bad.append(f"{cid}: soz_tipi {b['soz_tipi']} should be {tip}")
        prev_agent = [x[1] for x in turns[:i] if x[0] == "A"][-1]
        if C.CONFIRM_Q not in prev_agent or k["kart_son4"] not in prev_agent or C.tl(b["tutar"]) not in prev_agent:
            bad.append(f"{cid}: no read-back with card, amount and '{C.CONFIRM_Q}' before the promise")
        ok = t[3].get("basarili") and t[4] == 200
        if ok:
            if b["kart_id"] in promised:
                bad.append(f"{cid}: two promises on one card")
            promised.add(b["kart_id"])
            nxt = [x[1] for x in turns[i + 1:] if x[0] == "A"]
            if not nxt or C.SMS not in nxt[0] or "kaydedildi" not in nxt[0]:
                bad.append(f"{cid}: SMS sentence not said right after a recorded promise")
    fails = [t for t in services if t[1] == "OdemeSozuKaydet" and not t[3].get("basarili")]
    if fails:
        if len(fails) != 2 or close.get("gerekce_kodu") != "SISTEM_HATASI":
            bad.append(f"{cid}: failed promise must be retried once then closed SISTEM_HATASI")
        if any("kaydedildi" in a for a in agent):
            bad.append(f"{cid}: says 'kaydedildi' although the promise failed")
    if any(C.SMS in a for a in agent) != bool(promised):
        bad.append(f"{cid}: SMS sentence said without a recorded promise (or missing)")
    # outcome vs ledger
    transfers = [t for t in services if t[1] == "CagriAktar"]
    if transfers and close.get("sonuc_kodu") != "AKTARILDI":
        bad.append(f"{cid}: transfer done but close is not AKTARILDI")
    if promised and not transfers and close.get("sonuc_kodu") != "SOZ_ALINDI":
        bad.append(f"{cid}: promise recorded but close is not SOZ_ALINDI")
    # callbacks
    for t in services:
        if t[1] != "GeriAramaPlanla":
            continue
        day = C.d(t[2]["tarih"])
        hhmm = t[2]["saat"]
        if day not in (today, C.nth_bd_after(today, 1)) or not C.is_bd(day):
            bad.append(f"{cid}: callback day {day} not today / next business day")
        if not any(a <= hhmm <= b for a, b in C.callback_windows(now, day)):
            bad.append(f"{cid}: callback {day} {hhmm} outside {C.callback_windows(now, day)}")
        if dt.datetime.fromisoformat(f"{day}T{hhmm}") <= dt.datetime.fromisoformat(now):
            bad.append(f"{cid}: callback not after now")
    # first ask verbatim right after the statement is read
    if any(t[1] == "EkstreBorcSorgula" for t in services) and not any(C.FIRST_ASK in a for a in agent):
        bad.append(f"{cid}: first ask not said verbatim")
    for a in agent:
        for phrase in C.NEVER_ASK:
            if tr_lower(phrase.rstrip("?")) in tr_lower(a):
                bad.append(f"{cid}: forbidden question: {a!r}")
    if not any(C.GOODBYE in a or "İyi akşamlar" in a or "İyi günler" in a for a in agent[-2:]):
        bad.append(f"{cid}: no thanks / goodbye before closing")
    return bad


# ---------------------------------------------------------------- files
def check_files() -> list[str]:
    bad = []
    expect = ["BRIEF.md", "README.md", "analiz.docx", "akis.drawio", "duyurular.pdf", "servis-sozlesmesi.docx",
              "test-musterileri.xlsx", "soru-cevap.md"] + [f"ornek-konusma-{i}.md" for i in range(1, 7)]
    have = sorted(p.name for p in CASE.iterdir())
    if sorted(expect) != have:
        bad.append(f"case folder files {have} != {sorted(expect)}")
    have_md = sorted(p.name for p in CASE_MD.iterdir())
    if sorted(x if x != "servis-sozlesmesi.docx" else "servis-sozlesmesi.md" for x in expect) != have_md:
        bad.append(f"md variant files {have_md}")
    # xlsx round trip
    rows = xlsx_rows(CASE / "test-musterileri.xlsx")
    if list(rows) != ["Müşteriler", "Kartlar", "Açıklamalar"]:
        bad.append(f"xlsx sheets {list(rows)}")
    m = {r[0]: r for r in rows["Müşteriler"][1:]}
    for c in C.CUSTOMERS:
        r = m.get(c["musteri_no"])
        if not r or r[1:6] != [c["ad"], c["soyad"], c["hitap"], c["dogum_tarihi"], c["tckn_son4"]]:
            bad.append(f"xlsx customer row mismatch {c['musteri_no']}: {r}")
    cards = [r for r in rows["Kartlar"][1:]]
    want = [[c["musteri_no"], k["kart_id"], k["urun"], k["kart_son4"], k["ekstre_borcu"], k["asgari_odeme_tutari"],
             k["son_odeme_tarihi"], k["gecikme_gun_sayisi"]] for c in C.CUSTOMERS for k in c["kartlar"]]
    if cards != want:
        bad.append("xlsx card rows differ from case_data")
    if not 8 <= len(C.CUSTOMERS) <= 10:
        bad.append("8-10 test customers expected")
    # docx contract: every op, path, enum value and error code
    ct = docx_text(CASE / "servis-sozlesmesi.docx")
    tokens = ["KimlikDogrula", "EkstreBorcSorgula", "OdemeSozuKaydet", "GeriAramaPlanla", "CagriAktar", "NotEkle",
              "GorusmeKapat", "/kimlik/dogrula", "/odeme-sozu/kaydet", "GUN_AY_YER_DEGISTI", "TAMAMI", "KISMI",
              "MUSTERI_TEMSILCISI", "ODENDI_BEYANI", "E004", "E500"] + list(C.OUTCOMES) + list(C.REASONS)
    bad += [f"contract docx lacks {t}" for t in tokens if t not in ct]
    cm = (CASE_MD / "servis-sozlesmesi.md").read_text()
    bad += [f"contract md lacks {t}" for t in tokens if t not in cm]
    with zipfile.ZipFile(CASE / "servis-sozlesmesi.docx") as z:
        if b"<w:sdt>" not in z.read("word/document.xml"):
            bad.append("contract docx: closing table is not inside a content control")
    an = docx_text(CASE / "analiz.docx")
    if "Süreç Analizi" not in an or "Finansal Destek" not in an:
        bad.append("analiz.docx text")
    # drawio, both forms
    for folder in (CASE, CASE_MD):
        labels = " ".join(drawio_labels(folder / "akis.drawio"))
        for t in ("KimlikDogrula", "OdemeSozuKaydet", "GorusmeKapat", "arife"):
            if t not in labels:
                bad.append(f"{folder.name}/akis.drawio lacks {t}")
    if "<mxGraphModel" in (CASE_MD / "akis.drawio").read_text():
        bad.append("md variant drawio should be the compressed form")
    # pdf
    pdf = (CASE / "duyurular.pdf").read_bytes()
    if not pdf.startswith(b"%PDF"):
        bad.append("duyurular.pdf is not a PDF")
    if shutil.which("pdftotext"):
        txt = subprocess.run(["pdftotext", str(CASE / "duyurular.pdf"), "-"], capture_output=True, text=True).stdout
        for t in ("DUY-2026-031", "DUY-2026-034", "ONAYLANMADI", "09:00–20:00", "2. iş günüdür", "31 Aralık 2026"):
            if t not in txt:
                bad.append(f"duyurular.pdf text lacks {t}")
    # examples: 6 files, each matching its conversation
    convs = {c["ornek"]: c for c in C.conversations() if c["ornek"]}
    for i in range(1, 7):
        text = (CASE / f"ornek-konusma-{i}.md").read_text()
        for t in convs[i]["turns"]:
            if t[0] in "AM" and t[1] not in text:
                bad.append(f"ornek-konusma-{i}.md lacks line {t[1][:40]!r}")
    # brief content
    br = (CASE / "BRIEF.md").read_text()
    for t in (C.OPENING, C.FIRST_ASK, C.CONFIRM_Q, C.SMS, C.REST_OVERDUE, C.SCAM, "GG.AA.YYYY", "7. iş günü",
              "3. iş günü", "09:00 ile 18:00", "09:00 ile 12:30", "29 Ekim 2026"):
        if t not in br:
            bad.append(f"BRIEF lacks {t!r}")
    return bad


def check_json() -> list[str]:
    bad = []
    cases = json.loads((HERE / "cases.json").read_text())
    if [c["id"] for c in cases] != [f"TRF-{i:02d}" for i in range(1, 14)]:
        bad.append("cases.json ids")
    if sum(1 for c in cases if c["source"]) != 6:
        bad.append("cases.json: 6 cases must come from the example conversations")
    for c in cases:
        if c["expected_ledger"][-1]["op"] != "GorusmeKapat":
            bad.append(f"{c['id']}: ledger must end with GorusmeKapat")
        if c["mock_customer"] not in C.BY_ID:
            bad.append(f"{c['id']}: unknown mock customer")
    exp = json.loads((HERE / "expected.json").read_text())
    ref = exp["reference_now"]
    if exp["leaves"]["/third_party/callback/windows/0/to"] != C.callback_windows(ref, C.d(ref))[0][1]:
        bad.append("expected callback window disagrees with the announcement in force at reference_now")
    oa = json.loads((HERE / "reference" / "openapi.json").read_text())
    ops = sorted(op["post"]["operationId"] for op in oa["paths"].values())
    if ops != sorted(exp["tool_roles"].values()):
        bad.append(f"reference openapi ops {ops} != tool_roles")
    return bad


LEAK_TOKENS = ["FB-240117", "FB-240699", "KRT-240", "KimlikDogrula", "EkstreBorcSorgula", "OdemeSozuKaydet",
               "GeriAramaPlanla", "GorusmeKapat", "GUN_AY_YER_DEGISTI", "SOZ_ALINDI", "SOZ_ALINAMADI",
               "ODEME_YAPILMIS", "DOGRULANAMADI", "ULASILAMADI", "DUY-2026-0", "FINANSAL_DESTEK", "MUSTERI_TEMSILCISI",
               "ODENDI_BEYANI", "tum_sorular_tamam", "asgari_odeme_tutari", "gecikme_gun_sayisi", "8.450,75"]


def check_leak() -> list[str]:
    """Rehearsal tokens must never appear in the builder's own code (builder/ runtime/ harness/)."""
    bad = []
    for top in ("builder", "runtime", "harness"):
        for p in (ROOT / top).rglob("*"):
            if not p.is_file() or "__pycache__" in p.parts or p.suffix not in {".py", ".md", ".json", ".txt", ".yaml"}:
                continue
            text = p.read_text(errors="replace")
            for t in LEAK_TOKENS:
                if t in text:
                    bad.append(f"leak: {t!r} in {p.relative_to(ROOT)}")
    return bad


def run_all() -> list[str]:
    bad = []
    for conv in C.conversations():
        bad += check_conversation(conv)
    return bad + check_files() + check_json() + check_leak()


if __name__ == "__main__":
    problems = run_all()
    for p in problems:
        print("PROBLEM", p)
    print(f"check_case: {len(problems)} problem(s)")
    sys.exit(1 if problems else 0)
