# raw-ab: Brief A+B rewritten as raw bank material

A rehearsal for the hidden "raw" final brief. `brief.md` is one markdown file holding what a bank would forward: two mails (the second corrects the first), a policy extract for single-product calls, an addendum for up to three products, a memo that overrides one calendar date for all products, and a code list. The **effective rules equal Brief A+B**, so a correct extraction must reproduce `tests/golden/spec-ab.json` on its core leaves (see `expected.json`). `openapi.json` is the kit's `tools/openapi.json`, byte for byte.

| File | What it is |
|---|---|
| `brief.md` | The raw pack (mail 1, mail 2, COL-P-07 v4 extract, addendum A2, memo OPS-26-118, code list CL-COL-3) |
| `openapi.json` | Kit tool API, unchanged |
| `expected.json` | Core leaves under spec-ab key paths, plus `code_map` (internal code to enum value) and `must_not` (the traps) |
| `cases.json` | 12 customers in the `public-test-set.json` shape. RAB-01..03 mirror PUB-11..13 exactly; RAB-04..08 are new multi-product cases; RAB-09..12 are single-product cases on other days |

## How the raw form differs from Brief A / Brief B

Each change rewrites the form only. The effective rule stays the same.

1. **Layered documents instead of A + B files.** The precedence order is given in mail 1 (addendum over extract, memo over both for its date). The builder has to merge four documents.
2. **Renumbered and cross-referenced.** A rules 1-47 become extract sections 1-10 (e.g. A30 is 7.7, A41 is 9.3, A46 is 10.1). Every internal reference is renumbered ("This rule comes before 7.7 and 9.3"). B rules 1-11 plus the closing rule become A2.1-A2.13.
3. **Internal codes instead of enum values.** Outcomes (PRM, PDA, TRF, NOP, NVF, NRC), reasons (RST, HUM, ... UNC), queues (Q10/Q20/Q30), note reasons (REF, HRD, DSP, PDA, SVE), identity fields (ID1/ID2) and the hint (H-DMS) are used throughout. Only the code list maps them to the OpenAPI values. PDA is both a result code and a note reason. VMB (voicemail) is a distractor code with no system value.
4. **Mail correction.** Mail 1 says callbacks run until 18:00. Mail 2 corrects this to 19:00 with both ends included, which matches extract 3.2. Effective window: 10:00-19:00, the same as A.
5. **Holiday list split across documents.** Extract 6.1 lists only 11/11, 26/11, 25/12 and 01/01 (DD/MM/YYYY). Memo OPS-26-118 adds **2026-10-26** for all products, including callbacks and "next business day". It also mentions a **withdrawn draft date, 2026-11-02**, which must stay a business day. Effective list: the same as A.
6. **Single-product notes made explicit.** Extract 10.2 says no notes (A's "Brief A never uses add_note"). Addendum A2.8 replaces it: notes apply to every call from 14 Oct 2026, including single-product customers. This is the golden's `notes_scope: every_product_without_promise` reading, now written into the text.
7. **Hardship scope made explicit.** A2.12: a hardship mention covers every product without a promise, and each is noted HRD if support is declined. This matches the golden `multi_product.hardship_applies_to: all_remaining`. Brief B does not say it.
8. **Floor as a table** (product to field), product spoken names in code list part E, the deadline table with a column renamed to "Days late". Distractor: 1.3 (accounts over 45 days late go to Recoveries).
9. Verbatim sentences are unchanged: "Am I speaking with {title} {last_name}?", "Can you make this payment today?", "Do you confirm?", "I am sorry for your loss.", "You will receive a text message confirming this promise."

## What the cases cover

| Case | now | Products | Tests |
|---|---|---|---|
| RAB-01 | Wed 14 Oct | 3 | PUB-11: one date for all, three promises |
| RAB-02 | Wed 14 Oct | 3 | PUB-12: phone re-ask, partial promise, two `refused` notes, attempts per band |
| RAB-03 | Wed 14 Oct | 2 | PUB-13: one date, clamp the loan to 23 Oct. The card's early deadline is 2 Nov only if the memo is applied |
| RAB-04 | **Fri** 16 Oct | 2 | "next Friday" on a Friday gives 23 Oct. Attempt 1 on a Friday gives next week. The late deadline skips the memo holiday (28 Oct; it would be 27 Oct if the memo were missed) |
| RAB-05 | Tue 10 Nov (**day before holiday**) | 2 | "tomorrow" = 11 Nov holiday, so 12 Nov is offered. Car loan disputed: `dispute` note, the call continues |
| RAB-06 | Mon 30 Nov (**month end**) | 3 | Card already paid (`paid` note). Loan full amount too much: floor 320 on Fri 4 Dec. Car loan vague, then its deadline 16 Dec |
| RAB-07 | Wed 21 Oct | 2 | Restructuring mid-loop. The agreed car-loan promise is dropped. No notes |
| RAB-08 | Mon 19 Oct | 2 | Hardship at the all-today ask, support declined. `hardship` note on both products |
| RAB-09 | **Fri** 30 Oct | 1 | Single-product refusal. Attempt 1 gives Fri 6 Nov. A `refused` note on a single product (A2.8) |
| RAB-10 | **Fri** 23 Oct 18:30 | 1 | Third party proposes Monday (memo holiday, so not the next business day). One re-ask. Callback Tue 27 Oct 10:00 |
| RAB-11 | Thu 12 Nov | 1 | Wrong answers counted across both questions (1 date of birth + 2 phone): `not_verified/failed` |
| RAB-12 | Wed 21 Oct | 1 | 5 Nov is after the deadline. Clamped to **Mon 2 Nov** (the withdrawn draft date is a business day). Scam question |

Every expected date and amount was computed with a calendar script under these rules and checked: each promise is a business day, not before `now`, not after that product's deadline, and has an amount from the floor up to the full amount. The values these cases depend on: late-band deadline from 14 Oct = 23 Oct; early-band deadline from 14 Oct = 2 Nov; from 16 Oct (late) = 28 Oct; from 21 Oct (late) = 2 Nov; from 30 Nov (early) = 16 Dec. Scripts that accept "the date proposed" use a rung that the brief defines exactly (attempt 2 = floor on the deadline; vague, then the deadline).

## Not covered here
Changed OpenAPI fields or enums (the mutant fixtures cover those), `create_promise` faults, and right-party "unclear" or deceased closes.
