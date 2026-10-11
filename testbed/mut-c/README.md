# testbed/mut-c — Northwind Credit Union (mutated clean brief)

Rehearsal fixture for the hidden "clean specification" brief: the same kind of call as Brief A+B, with different
rules and a mutated OpenAPI. Nothing in the builder was changed to make it; nothing here has been run.

| File | What it is |
|---|---|
| `brief.md` | The whole brief in one markdown file (A and B merged, then mutated). |
| `openapi.json` | `kit/tools/openapi.json` with the mutations below. Same 7 tool names, same `servers` URL. |
| `expected.json` | Core Spec leaves a correct extraction must produce, at `spec-ab.json` key paths. `_derived` holds resolved holidays, deadlines and floors; `_tool_binding` holds the wire names and enums. |
| `cases.json` | 12 members in `kit/public-test-set.json` shape (`identity` keys are the new field values). Each expected promise has `amount` + `date` (kit `score.py` keys) **and** `amount_cents` + `promise_date` (the wire values). |

## Mutations vs Brief A/B

**Bank and opening**
- Bank "Northwind Credit Union"; self-name "Northwind Credit Union's automated assistant". Amounts are in pounds.
- New opening sentence, verbatim: "Hello, this is the automated assistant of Northwind Credit Union, and this call is recorded."
- Right-party ask uses first and last name ("Am I speaking with {first_name} {last_name}?"); title + last name only after confirmation.
- Banned words before verification now include "arrears", "overdue", "late", "owe" and the new product names.

**Identity**
- Questions: date of birth, then **postcode** (UK alphanumeric; spelled letters, NATO words, "M fourteen"). Wire is capital letters with one space before the last 3 characters. A partial postcode is never sent.
- **Two** wrong answers in total end the check (was three). `day_month_swapped` still does not count.
- Fail line points to "the number on the back of your Northwind card or a branch" (was app or branch).

**Products, amounts**
- Types `credit_card`, `overdraft`, `auto_loan` (was credit_card, personal_loan, car_loan).
- Card floor = **25% of past_due rounded UP to the penny** (`percent_of_full`, `ceil`). `get_account` still returns `minimum_payment` as a **decoy**; cases set it far below 25%.
- Overdraft has **no floor** (floor = full; "too much" on an overdraft is a flat refusal).
- Auto loan floor = `instalment_amount`.
- "The rest stays outstanding." (was "overdue").

**Calendar, bands, dates**
- Three bands: 1–10 / 11–30 / 31–60 days late. Deadlines: 10th / 5th / 3rd business day after today. Attempts 1 / 2 / 2.
- Attempt 1 date = last business day of the week **capped at the deadline** (a 3-day deadline can come before Friday).
- Holidays partly as rules: fixed 19 Oct 2026; "first Monday of November" (2 Nov 2026); 25 Dec, 26 Dec, 1 Jan with "next Monday if on a weekend" (26 Dec 2026 is a Saturday, so it falls on **Mon 28 Dec**).
- Callback: 09:00–17:30 (both included), **business days only**, today (if a business day) or the next **two** business days (was 10:00–19:00, today or the next business day, any day).

**Flow and closing**
- First ask: "Could you pay the full amount today?" / "Could you pay all of them today?". Read-back question: "Is that correct?" (verbatim).
- Required sentence after a promise: "You will receive an email confirming this promise." Deceased: "Please accept our condolences."
- **Required closing sentence on every call**: "Thank you for your time, and thank you for choosing Northwind Credit Union. Goodbye."
- "Already paid": payments take **two** business days to appear.
- Hardship also covers injury and **cut working hours**.
- **Notes for single-product members too** (Brief A had no notes at all); notes go after the last create_promise and before close_call; none on any transfer.
- New intent **complaint**: say "I will put you through to our complaints team.", transfer to queue `complaints`, close `transferred` / `complaint`. Applies from right-party confirmation onwards, including during the security questions.
- New intent **bankruptcy / IVA / DRO**: verbatim sentence, no more offers, drop unrecorded promises, note every unpromised product `insolvency`, close `no_promise_to_pay` / `insolvency` (or `promise_to_pay` if one was already recorded). It takes precedence over hardship.

**OpenAPI**
- `verify_identity.field` enum `[date_of_birth, postcode]`; the `answer` description gives the postcode wire format; the summary says two wrong answers.
- `get_account` product `type` enum `[credit_card, overdraft, auto_loan]`; `minimum_payment` described as informational.
- `create_promise`: `amount` → **`amount_cents`** (integer pence), `date` → **`promise_date`**; required updated.
- `add_note.reason` enum `[refused, hardship, dispute, already_paid, service_error, insolvency]` (`paid` → `already_paid`, + `insolvency`).
- `transfer_to_agent.queue` enum adds `complaints`.
- `close_call.outcome` enum `[promise_to_pay, no_promise_to_pay, transferred, paid, id_failed, no_contact]`; `close_call.reason` is now an **enum** with renamed values (`failed` → `wrong_answers`, `callback` → `callback_booked`) and new ones (`complaint`, `insolvency`).

## Cases

| id | now | Tests |
|---|---|---|
| NW-01 | Wed 14 Oct | Happy path, spelled postcode, `amount_cents` wire, closing sentence |
| NW-02 | Thu 24 Dec (day before a holiday) | Third party; Monday is the observed Boxing Day, so a re-ask; inclusive 17:30 → 29 Dec 17:30 |
| NW-03 | Thu 29 Oct | Swap hint not counted; 2 wrong postcodes end the check (no 3rd ask) |
| NW-04 | Thu 29 Oct | Rule-defined holiday (first Monday of Nov) → Tue 3 Nov; scam question |
| NW-05 | Thu 24 Dec | 25% ceil floor 308.65 vs decoy minimum 61.73; 250 below floor; attempt-1 date rolls to Thu 31 Dec |
| NW-06 | Tue 3 Nov | Hardship (hours cut) declined → single-product `hardship` note |
| NW-07 | Wed 25 Nov | Paid + dispute on two products → notes `already_paid`, `dispute`; close `dispute` |
| NW-08 | Fri 30 Oct (Friday, month end) | "next Friday" = 6 Nov agreed, then restructuring → unrecorded promise dropped, no notes |
| NW-09 | Mon 30 Nov (month end) | 3 products, numeric DOB, 2 promises (one exactly on the deadline), auto loan attempt 1 capped at the deadline (Thu 3 Dec) |
| NW-10 | Fri 16 Oct | One date for both; auto loan clamped to 22 Oct across Founders' Day; robot question |
| NW-11 | Wed 21 Oct | Complaint → queue `complaints`, reason `complaint`, no notes |
| NW-12 | Tue 10 Nov | Job loss + bankruptcy → insolvency wins, two `insolvency` notes |

## Known harness gap (finding, not fixed here)

`harness/mockbank.py` `_t_create_promise` stores the bound amount as-is. With `amount_cents` the ledger would
hold `42000`, not `420.0`, so a local scorer comparing `amount` fails unless the mock divides by the catalog
`scale` (100). The kit scorer keys are `amount`/`date`; the cases carry both forms.

## Independent check (recomputed with python)

Every expected deadline, attempt-1 date, floor, callback slot, promise and note in `cases.json` and `_derived` was
recomputed from `brief.md` alone (holidays 2026-10-19, 2026-11-02, 2026-12-25, 2026-12-28 observed Boxing Day,
2027-01-01) and matches. `openapi.json` passes `openapi-spec-validator` (3.0.3) and its enums match `_tool_binding`.

Fixed during the check:
- `brief.md` rule 50 said "close as `no_promise_to_pay` / `refused`" even after a recorded promise, contradicting the
  closing table and `expected.json` `outcomes.precedence`. It now adds "or as `promise_to_pay` if a promise was
  recorded earlier in the call" (same wording as rule 46).
- `expected.json`: the insolvency intent's `action.kind` (`resolve_product_or_close`) is not a value of the Spec
  schema's `Action.kind` enum; it now carries a `_schema_gap` note. `_about` now defines the `*_must_include` /
  `*_must_convey` suffix conventions.

More builder gaps this fixture is expected to expose (findings, not fixed here):
- `builder/spec/schema.json` has no call-level, non-transfer intent kind for rule 46 (insolvency).
- `builder/prompts/F2.md` tells the extractor to use `wire_format: "upper_nospace"` for alnum answers; that sends
  `LS62QT`, but this brief and `openapi.json` require `LS6 2QT` (one space before the last three characters).
