# testbed/mut-d: Harbor Bank (raw-material rehearsal, hardest)

A rehearsal for the hidden RAW brief: one markdown file containing a forwarded mail chain, a scanned policy extract, a memo that changes the policy from an effective date, and a code list. The OpenAPI keeps the 7 tool names, but field names and enums are changed.

| File | Content |
|---|---|
| `brief.md` | The bank material, as one file: mail chain (Dana / Raj), policy HB-COL-POL-014 rev. 6 extract, memo COL-2026-031, outcome code list v3 |
| `openapi.json` | `kit/tools/openapi.json` with the Harbor mutations applied |
| `expected.json` | Expected core spec leaves (key paths as in `tests/golden/spec-a.json`). Keys starting with `_` are values the schema cannot hold, or grading notes |
| `cases.json` | 12 customers in the `kit/public-test-set.json` shape (`brief: "HARBOR"`), with `now` values from 20 Oct to 30 Nov 2026 |

Nothing here has been run. No build, no live calls. The hosted Freya mock does not implement the mutated fields, so run these cases only against `harness/mockbank.py` (the identity keys in `cases.json` are `account_last4` and `birth_year`).

## What it tests

1. **Raw-material extraction with precedence.** The mail is a summary "from memory" and is wrong on purpose: it says the late band is "about 10 days" and paraphrases the confirmation sentence. The brief says the policy and the memo win over the mail. Values are written the scanned-policy way ("seven (7) calendar days"), and the band table is broken across lines.
2. **An effective-dated memo.** From `now >= 2026-11-16`, the card floor becomes `max(minimum_due, 25% of past_due)` and 27 Nov 2026 becomes a holiday. HB-07 (12 Nov) must use the old floor: 150 is accepted against 120, although the memo floor would be 200. HB-08 (19 Nov) must use the new floor: 300, not 180. The spec has one floor per product type, so no single static floor passes both cases. The builder has to express the date condition, or at least raise it as a residual rule or warning. This is a deliberate probe of a schema gap.
3. **Calendar-day deadlines that move back.** The deadline is 14 or 7 calendar days, and when it lands on a weekend or holiday it moves to the previous business day (`nth_calendar_day_after_today` + `roll: prev_bd`). Because 7 and 14 keep the weekday, only holidays trigger the roll. HB-05 rolls back over 11 Nov. HB-09 rolls back over two holidays in a row (27 Nov from the memo, then 26 Nov), so it lands on 25 Nov.
4. **Code-list mapping.** The closing values are the bracketed `(outcome / reason)` pairs, not the codes. One line is broken (`system_` / `error`). `NCT-CBK` is retired. Note values come from a separate Part B.
5. **Behaviour flips compared with Brief A / B.** No third-party callbacks at all. A human request transfers straight away, with no "can I help first" question. Notes are always on, single-product calls included (Brief A never notes). Kept the same as A/B on purpose, and still probed: a transfer after a recorded promise closes as `transferred` (HB-04), and the closing reason skips products noted `paid` (HB-11).

## Every mutation compared with Brief A / B

### OpenAPI
- `verify_identity.field` enum is `[account_last4, birth_year]` (was `date_of_birth, phone_last4`). The `answer` description now covers 4 digits with leading zeros, and a 4-digit year (a two-digit year is rejected and not counted). The `hint` response leaf (`day_month_swapped`) is removed.
- `get_account` product `type` enum is `[credit_card, personal_loan, auto_loan]` (`car_loan` becomes `auto_loan`). `minimum_payment` becomes `minimum_due` (cards), and `instalment_amount` becomes `monthly_payment` (loans).
- `add_note.reason` enum: `service_error` becomes `system_error`.
- `transfer_to_agent.queue` enum is `[restructuring, agent, care]` (was `restructuring, general, support`).
- `close_call.outcome` enum is `[promise_taken, already_paid, transferred, no_promise, identity_failed, no_contact]`.
- `close_call.reason` is now an **enum**: `restructuring, agent, care, refused, hardship, dispute, system_error, failed, declined, third_party, wrong_number, deceased, unclear` (there is no `callback`, `no_callback`, `human`, `support` or `service_error`).
- `schedule_callback` is unchanged in the API, but the brief forbids using it.

### Brief
| Topic | Brief A / B | Harbor (mut-d) |
|---|---|---|
| Format | clean numbered spec | mail chain + scanned policy + memo + code list in one file; mail is non-authoritative |
| Right-party ask | "Am I speaking with {title} {last_name}?" | "Am I speaking with {first_name} {last_name}?" (title + last name only after) |
| Banned before verification | includes product names, "amount", "balance", "owe" | collections, debt, overdue, late, payment, plus any product or amount (2.1); "account number" is explicitly allowed, and the bare word "card" is not banned (fail and scam lines use it) |
| Third party | ask when reachable, callback today/next BD 10:00–19:00 | say nothing, never ask, never book; always `no_contact / third_party` |
| Identity | DOB (date, DMY, swap hint), then phone last 4 | account last 4 (not the card number), then birth year (words to YYYY, two-digit year re-asked) |
| Identity fail line | mobile app or branch | "call the number on the back of your card or visit a branch" |
| Decline explanation | "These questions protect your account." | "These questions keep your account safe." |
| Bands | 1–7 / 8–45 | 1–14 / 15–45 |
| Deadline | 12th / 7th business day after today | 14 / 7 **calendar** days, moved back to the previous business day |
| Holidays | 26 Oct, 11 Nov, 26 Nov, 25 Dec, 1 Jan | 3 Nov, 11 Nov, 26 Nov, 25 Dec, 1 Jan + 27 Nov (memo, from 16 Nov) |
| "Next Friday" / "this Friday" | the Friday of the following week / of the current week | the first Friday after today / the nearest Friday from today on, today included |
| First ask | "Can you make this payment today?" | "Can you pay this today?" |
| Floor | min payment / instalment | `minimum_due` / `monthly_payment`; cards from 16 Nov: max(minimum_due, 25% past due) |
| Too-much line | "The rest stays overdue." | "The remaining balance stays overdue." |
| Confirmation question | "Do you confirm?" | "Is that correct?" |
| Post-promise sentence | text-message sentence | "Harbor Bank will send you a confirmation by email within one business day." |
| Paid line | one business day | "up to two (2) business days" |
| Hardship | queue `support`, `transferred/support` | queue `care`, `transferred/care` |
| Human | ask once, then queue `general` | transfer at once, queue `agent`, `transferred/agent` |
| Scam / change-promise lines | customer service number / mobile app | "number on the back of your Harbor Bank card" / "Harbor online banking" |
| Notes | Brief A: never; Brief B: every product without a promise | always on (single-product too), never on a transfer call |
| Outcome values | promise / paid / transferred / no_promise / not_verified / not_reached | promise_taken / already_paid / transferred / no_promise / identity_failed / no_contact, mapped from composite codes |

## Cases (now / rule probed / expected)

| Id | now | Probe | Expected |
|---|---|---|---|
| HB-01 | Tue 20 Oct | happy path, year in words, new verbatim lines | promise 340.00 on 20 Oct |
| HB-02 | Thu 22 Oct | third party asks for a callback | no_contact / third_party, no callback |
| HB-03 | Fri 23 Oct | gives the card last 4 as the account; 3 wrong across both questions | identity_failed / failed |
| HB-04 | Fri 30 Oct (month end) | attempt 1 jumps to next week; two-digit year; human after recorded promise | promise 525.00 on 6 Nov; transferred / agent |
| HB-05 | Wed 4 Nov | deadline 11 Nov (holiday) moves back to 10 Nov; leading-zero account | promise 870.00 on 10 Nov |
| HB-06 | Tue 10 Nov (day before holiday) | "tomorrow" is a holiday, so next business day | promise 260.00 on 12 Nov |
| HB-07 | Thu 12 Nov (pre-memo) | old card floor; "next Friday" = 13 Nov; loan refused through 2 attempts | promise p1 150.00 on 13 Nov; note p2 refused |
| HB-08 | Thu 19 Nov (post-memo) | memo card floor 300 on the attempt-1 date | promise 300.00 on 20 Nov |
| HB-09 | Fri 20 Nov | one date for both; loan deadline rolls over 27 Nov and 26 Nov | p1 400.00 on 30 Nov, p2 660.00 on 25 Nov |
| HB-10 | Mon 23 Nov | hardship declined, waiver asked | no_promise / hardship; note p1 hardship |
| HB-11 | Tue 24 Nov | p1 paid, p2 dispute; closing skips the paid product | no_promise / dispute; notes paid + dispute |
| HB-12 | Mon 30 Nov (month end) | restructuring drops the agreed but unrecorded card promise | transferred / restructuring, no promises, no notes |

The effective date (16 Nov) falls between HB-07 and HB-08. No case before 16 Nov can reach 27 Nov, so the memo holiday is never ambiguous.
