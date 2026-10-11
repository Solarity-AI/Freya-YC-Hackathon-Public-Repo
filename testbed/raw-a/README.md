# testbed/raw-a: Brief A delivered as raw bank material

Rehearsal for the hidden RAW brief (Sun 17:00 UTC): one markdown file holding a mail, a policy extract, a memo that changes the policy, and a code list.

At a call date of 2026-10-14 the effective rules are exactly Brief A's, so `tests/golden/spec-a.json` is the target spec at that date. The material reaches those rules only after the memo is applied and the codes are mapped. One memo change is future-dated, so the correct rules depend on `now`.

## Files

| File | What it is |
|---|---|
| `brief.md` | Part 1 cover mail, Part 2 policy COL-POL-003 v3 extract (§1-§12), Part 3 memo COL-2026-14 (2026-10-01), Part 4 code list |
| `openapi.json` | `kit/tools/openapi.json`, byte-identical (no mutations) |
| `expected.json` | Core leaves as JSON pointers into the Spec (same paths as spec-a), plus the code-list mapping, superseded values, rejected changes and the dated override |
| `cases.json` | 13 cases in `kit/public-test-set.json` shape. RAWA-01..10 are PUB-01..10 with the same variables and ledgers (except RAWA-02, whose callback moves from 11:00 to 18:30 to test memo Item 2), plus raw-specific checks. RAWA-11..13 test the dated override |

## Mutations vs Brief A

Rules that are unchanged but delivered differently:

1. **Format.** There is no single rulebook. The rules are spread over 4 documents with a stated precedence: memo > policy > mail. Each memo item applies from its own effective date, judged by the call date.
2. **Rules buried in the mail's prose** (also restated in the policy): the robot answer, the scam answer, the verbatim text-message sentence, "I am sorry for your loss.", relatives get nothing, never ask "how much can you pay?", the 5 call variables, and add_note not used.
3. **Distractor paraphrase.** The mail says we give people "about two weeks". The real limits are in the band table, and the mail itself says not to build from it.
4. **Numbers in words.** The band table says "one to seven", "eight to forty-five", "the twelfth / tenth business day", and "one / two" attempts.
5. **Holidays** are given as named rows with weekday and long-form dates ("Monday 26 October 2026"). They are the same 5 dates as Brief A.
6. **Currency strings.** The floor table carries "USD 420.00 / USD 126.00" examples, marked as illustrations only. The floor must still come from `minimum_payment` / `instalment_amount`. Brief A has no currency, so the currency leaf is free.
7. **Result codes instead of enum values.** Policy §3-§12 say "OUT-NRC / RSN-CBK", "Q-SUP" and so on. Part 4 maps them to `close_call.outcome`, `close_call.reason` and `transfer_to_agent.queue` values. Distractors: the retired `OUT-VML -> voicemail` and `RSN-LGL -> legal_hold` rows ("never send"), and the NTE-* note codes ("not used in this programme").
8. **Memo Item 1 (applies, past-dated).** Policy §7.3 says the late band gets "the tenth business day". The memo changes it to the **seventh**, effective 2026-10-05. RAWA-04 tests this: the deadline is 2026-10-23, where the stale value would give 2026-10-29.
9. **Memo Item 2 (applies, past-dated).** Policy §4.2 callback window is 10:00-18:00. The memo changes it to **10:00-19:00**, effective 2026-10-12. The spec-a leaf is `"19:00"`. RAWA-02 books a callback at 18:30 the next business day: correct under the memo, outside the stale 18:00 window (a stale build re-asks and ends with `no_callback`).
10. **Memo Item 3 (rejected).** A proposal to move the band boundary from 7 to 10 days late was **not approved**. The bands stay 1-7 / 8-45.
11. **Memo Item 4 (non-change).** 2026-12-24 is explicitly **not** a holiday.
12. **Memo Item 5 (future-dated).** For calls made on or after **2026-11-16**, the early band deadline goes from the 12th to the **10th** business day. This is decided by the call date, not the promise date. The Spec schema mvp-1 has no dated-override leaf, so a correct build must make the early deadline depend on `now`, or at least surface the rule in `meta.residual_rules` / `warnings`. It must never silently drop the rule or bake in either value.

## Case map

| Case | now | Tests |
|---|---|---|
| RAWA-01..10 | 2026-10-14 Wed | PUB-01..10 semantics and ledgers under the raw format: code mapping on every close and transfer, memo Item 2 callback at 18:30 (RAWA-02), memo Item 1 (RAWA-04), Founders' Day holiday (RAWA-07), floor from the API rather than the USD example (RAWA-06), create_promise fault (RAWA-10) |
| RAWA-11 | 2026-11-20 Fri 15:30 | Item 5 in force. The customer asks for Tue 8 Dec, which the old 12th-day rule (Dec 9) would accept. The correct deadline is the 10th business day, skipping Thanksgiving: **Mon 2026-12-07**. Credit card, 348.00 |
| RAWA-12 | 2026-11-25 Wed 10:15 (day before Thanksgiving) | Item 5 in force, vague-period path. The agent asks once for an exact day, then proposes the deadline: **Thu 2026-12-10** (old rule: Dec 14). The DOB is given as 04/08/1995 and must be read DMY as 1995-08-04 |
| RAWA-13 | 2026-10-30 Fri 16:45 (month end) | Item 5 **not yet** in force, although the deadline lands after 16 Nov. 12th business day, skipping Remembrance Day 11 Nov: **Wed 2026-11-18**. The customer's 18 Nov is accepted; a build that clamps to Nov 16 fails. Car loan, 455.25 |

All dates were computed with a business-day calendar (Mon-Fri minus the 5 holidays, counting from the day after today).

## Not covered here

The fixture is single-product because it is Brief A. Multi-product partial promises, add_note and per-product clamping are covered by the raw-B / spec-ab fixtures. RAWA-13 deliberately goes over the 12-case guideline: it is the only case showing that the future change is *not* applied early.
