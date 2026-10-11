# testbed/tr-final: Turkish rehearsal case for the final

This is a synthetic case shaped like the announced final: "Freya Bank credit card statement-debt line, in Turkish", delivered as a folder of md, docx, pdf, xlsx and drawio files. It does not guess the final's content. Everything is generated from `case_data.py` by `make_case.py`, so the conversations, ledgers, test customers and answer keys always agree.

    .venv/bin/python testbed/tr-final/make_case.py            # regenerate everything (deterministic except the PDF bytes)
    .venv/bin/python testbed/tr-final/check_case.py           # self-check: rules, files, keys, leakage (exit 1 on problems)
    .venv/bin/python -m pytest testbed/tr-final -q            # 29 tests (not under tests/, so run them explicitly)
    .venv/bin/python builder/build.py testbed/tr-final/FreyaBank-Rehearsal/ <mock_url>   # rehearse the final command

## Files

| Path | What it is |
|---|---|
| `FreyaBank-Rehearsal/` | The case folder: `BRIEF.md`, `README.md`, `analiz.docx`, `akis.drawio`, `duyurular.pdf`, `servis-sozlesmesi.docx`, `test-musterileri.xlsx`, `soru-cevap.md` and `ornek-konusma-1..6.md` |
| `FreyaBank-Rehearsal-md/` | The same folder with the contract as `servis-sozlesmesi.md` and `akis.drawio` in the compressed form diagrams.net saves by default |
| `FreyaBank-Rehearsal.zip` | The case folder zipped, the way the final is delivered |
| `reference/openapi.json` | The correct reading of the Word contract as OpenAPI 3: the target for the contract agent and the mock |
| `reference/mock-customers.json` | The test customers in mock data shape. Identity answers use the contract's wire format (`GG.AA.YYYY`), and the fault flag marks the E500 customer |
| `cases.json` | 13 cases, TRF-01 to TRF-13. Each has `variables`, `identity`, kit-shaped `products`, `customer_lines` for replay, `service_calls`, `expected_ledger` (contract names) and `expected` (kit system values) |
| `expected.json` | Core values: Spec leaves as JSON pointers, `tool_roles`, `tool_fields`, the code list and closing pairs, verbatim sentences, superseded values, dated overrides, residual rules, rejected changes, distractors and file traps |

## What it exercises

- **Renamed services, all Turkish:** `KimlikDogrula`, `EkstreBorcSorgula`, `OdemeSozuKaydet`, `GeriAramaPlanla`, `CagriAktar`, `NotEkle`, `GorusmeKapat`. The fields are `musteri_no`, `soru`/`cevap`, `basarili`/`hata_kodu`, `kartlar[]`, `kart_id` and `tutar`/`odeme_tarihi`. The contract is a Word document with tables, not OpenAPI.
- **A derived enum:** `soz_tipi` is `TAMAMI`, `ASGARI` or `KISMI`, set from the promised amount.
- **Date wire format:** the date of birth goes on the wire as `GG.AA.YYYY`. Spoken digits are read day-month-year, and two-digit years become 19xx.
- **Swap hint:** `ipucu: GUN_AY_YER_DEGISTI` comes back when day and month are swapped.
- **Call variables and addressing:** the variables are `musteri_no`, `ad`, `soyad`, `hitap` and `now`. After the right-party check, the agent says "{ad} {hitap}" (for example "Ayşe Hanım").
- **Closing codes:** an outcome/reason table sits inside a Word content control. The queue `MUSTERI_TEMSILCISI` closes with the reason `TEMSILCI`. Two retired codes are listed and must not be used.
- **Turkish calendar:**
  - 29 Ekim is a holiday.
  - The arife (28 Ekim) is a business day for promises, but callbacks that day are allowed only 09:00 to 12:30.
  - "gelecek çarşamba" means Wednesday of the next calendar week.
- **Announcements in the PDF:**
  - DUY-2026-031, from 19 Oct, is in force at every case date: the callback window is 09:00 to 20:00 (TRF-13).
  - DUY-2026-034, from 2 Nov, is a dated override: the late-band deadline moves from the 3rd to the 2nd business day (TRF-06, against TRF-02 and TRF-12).
  - DUY-2026-028 has expired, DUY-2026-035 was rejected, and DUY-2026-036 says 31 Dec is not a holiday.
- **Two cards (TRF-06):**
  - The most overdue card comes first.
  - The attempt-1 date is capped at the deadline.
  - The second card is disputed, which adds a `NotEkle ITIRAZ` note for that card, and the call still closes `SOZ_ALINDI`.
- **Turkish morphology:** the banned words count with their suffixes too (borcunuz, ödemeniz, kartınızın). The scam answer is phrased so it avoids "kart".
- **File traps:**
  - xlsx dates are real date cells (serial number plus a `dd.mm.yyyy` format).
  - `tckn_son4` "0285" is stored as text, so the leading zero survives.
  - The drawio comes in two forms: uncompressed, and compressed (base64 + raw deflate + URL-encoding).
  - `builder/ingest.py` (as of 11 Oct 15:30 UTC) classifies all 14 files correctly in all three forms and converts the dates.

## Case map (expected ledger, contract names)

| Case | now | Example | Ledger / close |
|---|---|---|---|
| TRF-01 | Wed 21 Oct 10:30 | 1 | promise 8450.75 on 2026-10-21 TAMAMI; SOZ_ALINDI |
| TRF-02 | Tue 27 Oct 14:00 | 2 | "Buyurun" asked again. Says "too much", so the minimum is offered. The customer names 29 Oct (a holiday), so 30 Oct is proposed: promise 2140.00 on 2026-10-30 ASGARI; SOZ_ALINDI |
| TRF-03 | Tue 27 Oct 17:15 | 3 | Spouse answers and asks for 19:00 on the arife, which is outside its window. One re-ask: callback 2026-10-28 11:00; ULASILAMADI/GERI_ARAMA |
| TRF-04 | Thu 22 Oct 11:00 | 4 | Swap hint, then verified. "Already paid": note ODENDI_BEYANI; ODEME_YAPILMIS |
| TRF-05 | Wed 21 Oct 15:00 | 5 | Robot question, then job loss: transfer FINANSAL_DESTEK; AKTARILDI/FINANSAL_DESTEK |
| TRF-06 | Tue 3 Nov 10:00 | 6 | Scam question. Card 5502: promise 14200.00 on 2026-11-05 (the DUY-034 deadline). Card 1187: note ITIRAZ; SOZ_ALINDI |
| TRF-07 | Wed 21 Oct 11:30 | | OdemeSozuKaydet returns E500 twice; SOZ_ALINAMADI/SISTEM_HATASI (never "kaydedildi") |
| TRF-08 | Wed 21 Oct 12:00 | | Three wrong dates of birth; DOGRULANAMADI/HATALI_CEVAP |
| TRF-09 | Wed 21 Oct 16:00 | | Early band, 1 attempt (full amount on Fri 23 Oct) refused; SOZ_ALINAMADI/REDDETTI |
| TRF-10 | Tue 27 Oct 15:30 | | Asks to pay in instalments: transfer YAPILANDIRMA; AKTARILDI/YAPILANDIRMA |
| TRF-11 | Thu 22 Oct 09:45 | | "gelecek çarşamba" = 28 Oct (the arife) with 2000 TL, below the minimum. The minimum is offered: promise 2904.10 on 2026-10-28 ASGARI |
| TRF-12 | Wed 21 Oct 13:00 | | Asks for 30 Oct, after the deadline; the deadline is offered: promise 9875.00 on 2026-10-26 TAMAMI |
| TRF-13 | Wed 21 Oct 11:00 | | Son answers, "19:30 tonight": callback 2026-10-21 19:30. It is inside DUY-031's window but outside the BRIEF's 18:00, so a stale build fails |

Rehearsal values stay in `testbed/`. `check_case.check_leak` (and the test that wraps it) fails if a distinctive token appears in `builder/`, `runtime/` or `harness/`.
