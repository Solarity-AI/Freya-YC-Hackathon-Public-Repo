# Chapter 6: The brief rules (Brief A and Brief B), complete

## In short

1. **Brief A** has 47 numbered rules for a call to a customer who is 1 to 45 days late on one product. The agent opens without any purpose words and confirms who is on the line (at most 2 asks). It verifies identity (date of birth, then the phone's last 4; 3 wrong answers in total end the check) and then calls `get_account`. It states the debt and asks the verbatim "Can you make this payment today?". It negotiates inside the date and amount rules and a persuasion ladder that depends on the band. It reads back and asks "Do you confirm?", then calls `create_promise` (one retry allowed) and says the verbatim text-message sentence. It thanks the customer and says goodbye, then makes exactly one `close_call` with an outcome and reason taken from a 6-row table (A:9-121).
2. **Brief B** adds 11 rules that change A. The customer has 1 to 3 products, each with its own band, deadline, floor and attempt count. B uses one combined "all of them today?" ask, then goes product by product in `get_account` order. It does one combined read-back and one `create_promise` per product. Every product without a promise gets an `add_note`, but no note is written on any transfer. The closing aggregates: `promise` wins, "all noted `paid`" gives `paid`, and otherwise the reason is that of the first product whose note is not `paid` (B:5-23).
3. **Dates are computed, never guessed.** Business days are Monday to Friday minus 5 listed holidays. Deadlines count business days *after* today: the 12th for the early band (1–7 days late, 1 attempt) and the 7th for the late band (8–45, 2 attempts). For every public case (`now` = Wed 2026-10-14T11:00) the early deadline is **2026-11-02**, the late deadline is **2026-10-23**, and the attempt-1 date is **2026-10-16** (A:53-81).
4. **Five sentences must be said verbatim**, plus three product-name templates. Until identity is verified the agent must not say "collections", "debt", "payment" or the product, to anyone. It must never ask "how much can you pay?" (A:24-92).
5. **Precedence:** hardship comes before persuasion and before restructuring. A transfer after a recorded promise closes as `transferred`. A claim that the debt was paid off in the past is a dispute, not `paid`. A date or amount the customer proposes is never a refusal. The queue `general` maps to the reason `human` (A:78-117).
6. **33 points are ambiguous** (U-1 to U-33). Each is listed with a careful default in §13.
7. **What any brief of this kind specifies:** a schema of 29 components, G1 to G29 (§14). The organisers say what will change: identity questions, limits, deadlines, calendar, outcome table, tool fields and enums, and the form of the brief. They say what stays: the seven tool names, `now`, English, at most 3 products, scoring by ledger and transcript (HP §Overview, README:71-78).

---

## 0. How to read this chapter

### 0.1 Sources

Only the sources below were used. No network call of any kind was made for this chapter. All paths are relative to `kit/build-the-builder/` unless shown otherwise.

| Shorthand | File |
|---|---|
| `A:n` | `briefs/brief-a.md`, line n (121 lines, read in full) |
| `B:n` | `briefs/brief-b.md`, line n (23 lines, read in full) |
| `PTS:n` | `public-test-set.json`, line n (read in full) |
| `OA:n` | `tools/openapi.json`, line n (read in full) |
| `score.py:n` | `tools/score.py`, line n (read in full) |
| `run_cases.py:n` | `tools/run_cases.py`, line n (read in full) |
| `README:n` | `README.md`, line n (read in full) |
| `base-agent:n` | `examples/base-agent.json`, line n (cited lines checked) |
| `tac:n` / `wf:n` | `docs/tools-and-code.md` / `docs/workflow-format.md`, line n (cited lines checked) |
| `HP §X` | `research/hackathon-page.md`, section X (the official page text, read in full) |
| `RAT:n` | `research/read-api-and-testing.md`, line n. Used **only** for facts it marks as live-probed. Those facts are relabelled [PROBED-earlier] here and were not repeated. |
| `NOTES` | `knowledge/notes/briefs.md`, the reading notes this chapter re-checks |

### 0.2 Labels

| Label | Meaning |
|---|---|
| **[DOC]** | Stated in a document: a brief, the README, the hackathon page, the docs, or a description string in the OpenAPI file. |
| **[CODE]** | Read from kit code or kit data: `score.py`, `run_cases.py`, the test-set JSON, the example agent. |
| **[PROBED-earlier]** | Seen in live calls to the mock bank by an earlier agent on 2026-10-10 (RAT:5). These calls were not repeated. Caveat: RAT's "Ledger" field list (RAT:132-140, including `wrong`, `hinted` and `failures`) is not tagged [PROBED] there. It can only come from the live ledger reads described at RAT:5, so it is used here with this caveat. |
| **[INFERRED]** | My reasoning from the sources. All computed dates are [INFERRED]: they were worked out offline with Python's `datetime` and the holiday list in A:53. |
| **[UNCERTAIN]** | The sources do not settle the point. Each entry says exactly what is unknown. |

---

## 1. Where the notes were wrong, imprecise or incomplete (the source wins)

Every brief quotation in `NOTES` was compared with A and B line by line. **No note misquotes or contradicts the brief text.** The problems below are about precision and about evidence the notes left out.

| # | Note claim | Verdict | What the source says |
|---|---|---|---|
| N1 | NOTES §2.4 B8 and U-24: the scorer compares "the **set** of (product_id, reason) pairs", and "the ledger compares only sets". | IMPRECISE | score.py:22-27 compares **sorted lists**, not sets [CODE]. That is a multiset comparison, so duplicates count. Two `refused` notes for the same product, a promise recorded twice, two transfers, or two identical callbacks each fail the case even when the set of values is right. Order does not matter; count does. |
| N2 | NOTES §0 Labels: "[PROBED-earlier] … The prior summary marks no fact as probed, so this label does not appear below." | INCOMPLETE | That holds for `research/read-rules-and-cases.md`. But `research/read-api-and-testing.md` holds live-probed facts that bear directly on brief rules. A phone answer said in words ("two two eight eight") was **counted as wrong** (RAT:151). The bank accepted a spoken date of birth "14 March 1988" (RAT:150). `close_call` checks outcome/reason consistency (RAT:159). A second promise on a product returns "this product already has a promise" (RAT:156). "11am" is rejected for a callback (RAT:158). The ledger has a `hinted` field (RAT:136). These are added under the relevant rules below. |
| N3 | NOTES U-9: the result of a malformed `phone_last4` is fully [UNCERTAIN]. | PARTLY SETTLED | [PROBED-earlier] RAT:151: a phone answer in words was counted as a wrong answer, using up one of the three. So the "not counted" protection of OA:37 does **not** cover the phone field, at least for word input. The result for 3 or 5 digits is still unknown. |
| N4 | NOTES rule 45 and U-27: "the same customer" (A:102) means "someone who already confirmed". | OVER-READ | Grammatically, "the same customer" at A:102 points back to "the customer [who] says twice that they do not want to talk". The phrase itself says nothing about confirmation. The confirmed/unconfirmed split is still the best reading, but it comes from the outcome names: `not_verified` presupposes someone reached, and `not_reached`/`unclear` is rule 3's outcome for no confirmation. It does not come from the words "the same customer". The label stays [INFERRED]. |
| N5 | NOTES rule 13: whether the API counts a `day_month_swapped` answer is unknown. | ADD EVIDENCE | Still [UNCERTAIN]. But the practice ledger keeps a `hinted` field next to `wrong` (RAT:135-136) [PROBED-earlier]. That suggests the bank tracks hints separately from wrong answers. Its meaning was not probed. |

The notes' own corrections of the earlier summary (NOTES §1, items 1–10) were re-checked against the sources and stand.

---

## 2. Rule index (one line per rule)

Every requirement in these tables is a [DOC] paraphrase of the cited line. The "Public cases" column is [CODE], read from `public-test-set.json`; the mapping of a case to a rule is [INFERRED]. Full quotes and labels are in §4 and §5.

### 2.1 Brief A

| Rule | Line | One-line requirement | Outcome it can produce | Public cases |
|---|---|---|---|---|
| (front) | A:3-5, 9, 13 | Synthetic data. "Read all of it." Scope: 1–45 days late, one product. Only the call variables are known before tools run | – | all |
| 1 | A:24 | First sentence: digital assistant, Freya Bank, the call is recorded. No "collections"/"debt"/"payment"/product before verification, to anyone | – | all; checks PUB-01, 02, 03 |
| 2 | A:25 | Ask "Am I speaking with {title} {last_name}?" | – | all |
| 3 | A:26 | Only yes / that's me / speaking / own name confirm. 2 asks maximum. An answered question makes the next ask the 2nd | `not_reached`/`unclear` | none reach it |
| 4 | A:27 | Robot/AI question: "Freya Bank's digital assistant", continue | – | PUB-04 |
| 5 | A:31 | Third party: say nothing beyond the opening; ask when the customer can be reached | – | PUB-02 |
| 6 | A:32 | Callback today or next business day, 10:00–19:00 inclusive, later than `now`; `schedule_callback` | `not_reached`/`callback` | PUB-02 |
| 7 | A:33 | Slot outside the window: ask once more; still outside → no booking | `not_reached`/`no_callback` | none |
| 8 | A:34 | Number not the customer's | `not_reached`/`wrong_number` | none |
| 9 | A:35 | Customer died: "I am sorry for your loss.", ask nothing else | `not_reached`/`deceased` | none |
| 10 | A:36 | A relative answers no security questions and is told nothing, even if they offer to pay | – | PUB-02 |
| 11 | A:40 | Date of birth then phone last 4, one at a time; send the date as `YYYY-MM-DD`; numbers read day-month-year | – | all verified |
| 12 | A:41 | A wrong answer may be re-asked; 3 wrong in total end the check | – | PUB-03, PUB-12 |
| 13 | A:42 | `hint: "day_month_swapped"` → ask for the month as a word; that retry is not counted | – | none |
| 14 | A:43 | After 3 wrong: no debt, point to the app or a branch | `not_verified`/`failed` | PUB-03 |
| 15 | A:44 | Declines: explain once; a 2nd decline or a 2nd "what is it about" closes | `not_verified`/`declined` | none |
| 16 | A:48 | `get_account` only after both questions pass | – | all verified |
| 17 | A:49 | Collections team, late payment, product in words, past-due amount, days late | – | all verified |
| (cal) | A:53 | Business days: Mon–Fri except 5 holidays | – | date cases |
| 18 | A:55-60 | Band by `days_late` → deadline (12th or 7th business day after today) and attempts (1 or 2) | – | PUB-04…13 |
| 19 | A:62 | A promise date is today or later, a business day, not after the deadline | – | PUB-01, 04, 07, 13 |
| 20 | A:63 | A weekend or holiday on or before the deadline → offer the next business day | – | PUB-07 |
| 21 | A:64 | Vague period → ask once for the exact day; still none → propose the deadline | – | PUB-07 |
| 22 | A:65 | "Next <weekday>" = following calendar week; "This <weekday>" = current week | – | PUB-06, 10, 11 |
| 23 | A:66 | After the deadline → say the deadline is the latest and offer it; refusing it is a flat refusal | – | PUB-04 |
| 24 | A:70 | Full amount first; never "how much can you pay?"; the agent proposes every amount | – | PUB-06 |
| 25 | A:71 | Floor = `minimum_payment` (card) or `instalment_amount` (loans) | – | PUB-06, 12 |
| 26 | A:72 | "Too much" → offer the floor once, say the rest stays overdue; refusing it is a flat refusal | – | PUB-06 |
| 27 | A:73 | Customer amount in [floor, full] → accept; below the floor → "cannot be recorded", offer the floor once | – | none |
| 28 | A:77 | First ask: "Can you make this payment today?" | – | all promise cases |
| 29 | A:78 | A proposed date or amount is never a refusal | – | PUB-04, 07, 12, 13 |
| 30 | A:79-81 | Flat refusal or non-answer uses an attempt. Attempt 1 = last business day of this week; attempt 2 (late only) = floor on the deadline | – | PUB-06, 10, 11, 12 |
| 31 | A:82 | Attempts used up → stop, never repeat a refused offer | `no_promise`/`refused` | PUB-12 (as notes) |
| 32 | A:83 | Hardship: one sympathy sentence, no persuasion, offer support; comes before rules 30 and 41 | `transferred`/`support` or `no_promise`/`hardship` | PUB-05 |
| 33 | A:84 | Never offer a discount, waiver, instalment plan or any term not in the brief | – | PUB-05, 09 |
| 34 | A:88 | Read back product, amount, date; "Do you confirm?"; create only after a clear yes | – | all promise cases |
| 35 | A:89 | A change at the read-back → re-check, read back again | – | none (style `corrects`) |
| 36 | A:90 | One promise per product; no change or cancel in the call; point to the app | – | PUB-01, 11 |
| 37 | A:91 | "Recorded" only after `ok: true`; one retry; second failure → say so | `no_promise`/`service_error` | PUB-10 |
| 38 | A:92 | "You will receive a text message confirming this promise." | – | PUB-01 |
| 39 | A:96 | "I already paid": one business day to appear, no promise | `paid` | PUB-08 |
| 40 | A:97 | Not mine / never had it / closed or paid off in the past: no argument, no promise | `no_promise`/`dispute` | none |
| 41 | A:98 | New plan or lower instalments: no plan described; transfer `restructuring` | `transferred`/`restructuring` | PUB-09 |
| 42 | A:99 | Human: ask once if you can help; insists → queue `general` | `transferred`/`human` | none |
| 43 | A:100 | Scam: verify by phoning Freya Bank's customer service number; continue | – | none |
| 44 | A:101 | Not answerable from the tools: say you do not have that information; invent nothing | – | none |
| 45 | A:102 | Twice "don't want to talk" → `no_promise`/`refused`; before verification `not_verified`/`declined` | as stated | none |
| 46 | A:106 | Exactly one `close_call`, last, with outcome and (where listed) reason | – | all |
| (table) | A:108-117 | Outcome table; a transfer after a recorded promise → `transferred` | – | all |
| (notes) | A:119 | "Brief A never uses `add_note`." | – | all A |
| 47 | A:121 | Thank and say goodbye before `close_call` | – | all |

### 2.2 Brief B

| Rule | Line | One-line requirement | Public cases |
|---|---|---|---|
| (front) | B:3, B:5 | Synthetic data. "Every rule of Brief A applies unless a rule below replaces it." | – |
| B1 | B:9 | `get_account` returns 1–3 products, each with its own `past_due`, `days_late` and floor | PUB-11, 12, 13 |
| B2 | B:10 | State every late product, one sentence each, before asking for anything | PUB-11 |
| B3 | B:11 | Band and deadline per product | PUB-11, 12, 13 |
| B4 | B:12 | One combined today-ask. Then products one by one in `get_account` order, no per-product today-ask, each starting at attempt 1 | PUB-11, 12, 13 |
| B5 | B:13 | Attempts counted per product | PUB-12 |
| B6 | B:14 | One date for everything that is past one product's deadline → that product goes on its own deadline, said in the read-back | PUB-13 |
| B7 | B:15 | One combined read-back and confirmation, then `create_promise` once per product | PUB-11, 13 |
| B8 | B:16 | `add_note` (`refused`/`hardship`/`dispute`/`paid`/`service_error`) for each product without a promise, even when none gets one | PUB-12 |
| B9 | B:17 | A dispute or "already paid" on one product: note it, continue | none |
| B10 | B:18 | Restructuring still transfers. Recorded promises stay; agreed-but-unrecorded are dropped. No notes on any transfer | none |
| B11 | B:19 | `create_promise` fails twice → keep the recorded ones, `service_error` note for the failed product | none |
| Closing | B:23 | A's table applies. No promise: all `paid` → `paid`, else `no_promise` + the first non-`paid` note's reason. `promise` wins except rule 10 | PUB-11, 12, 13 |

---

## 3. The calendar and every computed date

### 3.1 The definitions [DOC]

- "Business days are Monday to Friday, except Freya Bank holidays: 2026-10-26, 2026-11-11, 2026-11-26, 2026-12-25, 2027-01-01." (A:53)
- `now`: "The current date and time. All date rules use this, never the real clock." Example `2026-10-14T11:00` (A:20). The format is `YYYY-MM-DDTHH:MM`, with no seconds and no time zone [INFERRED from the example and PTS:12].
- wf:240 [DOC]: "There is no `{{current_date}}` placeholder. These system dates are the real clock. If your task supplies its own "now" as a call variable, use that variable."
- [PROBED-earlier] RAT:128: `now` is fixed per case (`2026-10-14T11:00` for all PUB cases), and a `now` sent in the session request is ignored.
- HP §Data: "Every case runs Wed 14 Oct 2026 11:00." HP §Evaluation: the final has "several calendar days". README:76: "on several calendar days, three times each."

### 3.2 The holidays [INFERRED, computed]

| Date | Weekday | Effect |
|---|---|---|
| 2026-10-26 | Monday | Next business day after Fri 10-23 is **Tue** 10-27. PUB-07's "Monday the 26th" lands here. |
| 2026-11-11 | Wednesday | Breaks mid-week counting. |
| 2026-11-26 | Thursday | The week of 11-23 has only 4 business days. The day after Wed 11-25 is Fri 11-27. |
| 2026-12-25 | Friday | That week's last business day is Thu 12-24. |
| 2027-01-01 | Friday | That week's last business day is Thu 12-31. |

[INFERRED] The list ends at 2027-01-01. Any later date is an ordinary weekday or weekend day, because no later holiday is listed.

### 3.3 Business days counted from the public `now` (Wed 2026-10-14) [INFERRED, computed]

| Date | Day | Business day? | Business days after today | Meaning |
|---|---|---|---|---|
| 10-14 | Wed | yes | (today) | "Today" is a valid promise date (PUB-01) |
| 10-15 | Thu | yes | 1 | Next business day: callback "tomorrow" (PUB-02); PUB-12 card "tomorrow" |
| 10-16 | Fri | yes | 2 | Last business day of this week: **attempt-1 date** |
| 10-17/18 | Sat/Sun | no | – | |
| 10-19 | Mon | yes | 3 | |
| 10-20 | Tue | yes | 4 | |
| 10-21 | Wed | yes | 5 | |
| 10-22 | Thu | yes | 6 | The wrong late deadline you get if today is counted |
| 10-23 | Fri | yes | **7** | **Late-band deadline** (PUB-04, PUB-13 loan) |
| 10-24/25 | Sat/Sun | no | – | |
| 10-26 | Mon | **holiday** | – | |
| 10-27 | Tue | yes | 8 | PUB-07 promise date |
| 10-28 | Wed | yes | 9 | |
| 10-29 | Thu | yes | 10 | |
| 10-30 | Fri | yes | 11 | The wrong early deadline you get if today is counted; also PUB-13's card date |
| 10-31/11-01 | Sat/Sun | no | – | |
| 11-02 | Mon | yes | **12** | **Early-band deadline** |

"After today" rules out counting today. The late band is pinned by PUB-04 (expects 10-23 at PTS:165) and the PUB-13 loan (10-23 at PTS:622). No public case separates the early-band answers 11-02 and 10-30 (see U-28).

### 3.4 "This" and "next" said on Wed 10-14 (A:65) [INFERRED, Monday–Sunday week]

| Phrase | Date | Note |
|---|---|---|
| this Monday / this Tuesday | 10-12 / 10-13 | in the past (U-14) |
| this Wednesday | 10-14 | today |
| this Thursday / this Friday | 10-15 / 10-16 | PUB-06, 10, 11 say "this Friday" = 10-16 |
| this Saturday / this Sunday | 10-17 / 10-18 | not business days → rule 20 |
| next Monday … next Friday | 10-19 … 10-23 | "next Friday" = 10-23 = the late deadline |
| "the week after next" | (vague) | PUB-07: rule 21 applies, ask once for the exact day |

### 3.5 The same quantities for other `now` values [INFERRED, computed; illustrative, because the final runs on "several calendar days"]

| `now` (date) | Business day? | Next business day | Early deadline (12th) | Late deadline (7th) | Attempt-1 date |
|---|---|---|---|---|---|
| Wed 2026-10-14 | yes | Thu 10-15 | Mon 11-02 | Fri 10-23 | Fri 10-16 |
| Fri 2026-10-16 | yes | Mon 10-19 | Wed 11-04 | Wed 10-28 | Fri 10-23 (today is this week's last business day, so next week's) |
| Fri 2026-10-23 | yes | **Tue 10-27** (Monday is a holiday) | Thu 11-12 (skips 11-11) | Wed 11-04 | Fri 10-30 |
| Sat 2026-10-24 | **no** | Tue 10-27 | Thu 11-12 | Wed 11-04 | This week's last business day is Fri 10-23, **already past** (U-13) |
| Sun 2026-10-25 | **no** | Tue 10-27 | Thu 11-12 | Wed 11-04 | Same problem as Saturday (U-13) |
| Tue 2026-11-10 | yes | **Thu 11-12** (Wed is a holiday) | Mon 11-30 | Fri 11-20 | Fri 11-13 |
| Wed 2026-11-25 | yes | **Fri 11-27** (Thu is a holiday) | Mon 12-14 | Mon 12-07 | Fri 11-27 |
| Thu 2026-12-24 | yes | Mon 12-28 | Wed 2027-01-13 | Wed 2027-01-06 | Thu 12-31. Fri 12-25 is a holiday, so today is this week's last business day. Next week's would be Fri 01-01, also a holiday, so Thu 12-31. |
| Thu 2026-12-31 | yes | Mon 2027-01-04 | Tue 2027-01-19 | Tue 2027-01-12 | Fri 2027-01-08. Fri 01-01 is a holiday, so today is this week's last business day. |

[INFERRED] Attempt 1 always falls on or before the deadline under A's numbers. It is at most 5 business days after today, and the shortest deadline is the 7th business day. A hidden brief with a shorter deadline could break this (§14).

---

## 4. Brief A, rule by rule

Each rule below gives:

- **Text**: the rule exactly as written.
- **Requirement**: what must happen.
- **Interpretation**: how ambiguities are resolved.
- **Precedence**: how the rule interacts with others.
- **Tested by**: the public cases.
- **Compute**: the deterministic work it needs.

### 4.0 Front matter and call variables (A:1-20)

- A:1 [DOC] Title: "Brief A: Freya Bank, early-stage collections, one product".
- A:3 [DOC] "Freya Bank is fictional. Every customer, debt and payment here is synthetic."
- A:5 [DOC] "This brief has the density of a real bank specification. Read all of it. Most failed cases come from one rule that was skipped."
  - README:42 [DOC] calls it "47 rules. Read all of it."
  - README:65 [DOC]: "There is no partial credit."
- A:9 [DOC] "Freya Bank calls customers who are 1 to 45 days late on one product. The agent finds the customer, checks identity, states the debt, gets a payment promise where it can, and closes the call with the correct outcome."
  - [INFERRED] The sentence lists five phases in order: find, verify, state, promise, close.
  - [INFERRED] "Where it can" means a non-promise outcome is often the correct one. HP §Evaluation [DOC]: "A correct refusal counts: when the customer disputes the debt, the passing outcome is a recorded dispute and no promise; an agent that pushes for a promise fails."
  - [INFERRED] The range 1–45 is exactly the union of the two bands (A:59-60). A `days_late` outside it has no band (U-23).
- A:13 [DOC] "Every call starts with these. Nothing else is known before the tools are called."

| Variable | Example | Meaning (verbatim) | Notes |
|---|---|---|---|
| `customer_id` | `c_4f2a...` | "Pass it to every tool call." (A:17) | [DOC] All seven tools require it (OA:40-44, 103-105, 196-201, 264-268, 320-324, 376-379, 438-441). OA:6: "the customer_id in the body is the secret of one call." |
| `first_name`, `last_name` | `Daniel`, `Reyes` | "The person to ask for." (A:18) | [INFERRED] The first name is used only to recognise "the customer's own name" as a confirmation (A:26). The agent addresses the customer by title and last name. |
| `title` | `Mr` or `Ms` | "Address the customer as title plus last name." (A:19) | [INFERRED] "Mr Reyes", never "Daniel". [UNCERTAIN] whether titles other than Mr or Ms can occur. Every public case uses one of the two (PTS:11, 58, …). |
| `now` | `2026-10-14T11:00` | "The current date and time. All date rules use this, never the real clock." (A:20) | See §3.1. |

[CODE] The example agent fills the identity question with `{{title}} {{last_name}}` (base-agent:105) and passes `Now: {{now}}` into the second step's prompt (base-agent:315).

### 4.1 Opening and who is on the line (brief A §3, A:22-27)

#### Rule 1 (A:24): the opening sentence and the pre-verification word ban

- **Text** [DOC]: "First sentence: say you are a digital assistant calling from Freya Bank, and that the call is recorded. Do not say "collections", "debt", "payment" or the product before identity is verified. This applies to everyone, including relatives."
- **Requirement**:
  - The first sentence carries three facts:
    1. you are a digital assistant;
    2. you are calling from Freya Bank;
    3. the call is recorded.
  - The wording is free: the rule says "say … that", not "say this sentence".
  - Until identity is verified, nobody may hear the words "collections", "debt" or "payment", or any naming of the product.
- **Interpretation**:
  - [INFERRED] "Identity is verified" means both security questions passed. The API reports this as `all_verified: true` (OA:69-71), and A:48 says "After both questions pass".
  - [INFERRED] "The product" covers any product word: "credit card", "card ending NNNN", "personal loan", "car loan". The agent cannot know the product before `get_account` anyway, but it must not guess one.
  - [INFERRED] Treat the whole purpose vocabulary as off limits before verification, even though only three words are listed: owe, overdue, late, arrears, balance, amount, bill. Rule 5 bans saying why you call to a third party, and the PUB-02 check bans it too: "the agent does not say why it is calling and names no product, amount or debt" (PTS:88). The opening is the same for every listener.
  - [DOC] "account" is **not** banned. A:44 itself has the agent say, before verification, that the questions "protect their account". "Account" is a risk only toward a third party (rule 5, rule 10).
  - [INFERRED] The ban lasts the whole call when identity never passes. That covers the rule 14 message, the rule 15 explanation, rule 43's scam answer, the goodbye, and every `not_reached` call.
  - [INFERRED] Rule 2's question can follow in the same turn, as the second sentence.
- **Precedence**:
  - The ban constrains the wording of rules 3, 4, 14, 15, 42, 43 and 45 whenever they fire before verification.
  - The verbatim "Can you make this payment today?" (rule 28) contains "payment". It is legal only because it comes after verification.
  - [CODE] Trap: the kit's example agent opens with "Hello, this is the digital assistant of Freya Bank. Am I speaking with {{title}} {{last_name}}?" (base-agent:105). It **omits "the call is recorded"**. README:34 says that agent passed 2 of 13.
- **Tested by**: every case. PUB-01 check "the word 'collections' is not said before identity is verified" (PTS:44). PUB-02 check (PTS:88). PUB-03 check "no amount or product disclosed" (PTS:129).
- **Compute**: a fixed opening template. A pre-verification output guard for the banned words is a design option [INFERRED].

#### Rule 2 (A:25): the identity question

- **Text** [DOC]: Ask "Am I speaking with {title} {last_name}?".
- **Requirement**: a verbatim template filled from the call variables, for example "Am I speaking with Mr Reyes?" (PUB-01, PTS:9-11) or "Am I speaking with Ms Costa?" (PUB-02, PTS:56-58).
- **Interpretation**: [INFERRED] The second ask under rule 3 repeats the same question.
- **Tested by**: every case.
- **Compute**: substitute `title` and `last_name`.

#### Rule 3 (A:26): what counts as confirmation; 2 asks; answer questions first

- **Text** [DOC]: "Only "yes", "that's me", "speaking" or the customer's own name counts as confirmation. "Hello", "go ahead" and "who is this" do not. Ask once more. If it is still unclear after the second ask, close as `not_reached` / `unclear`. Answer a question from the customer first (rules 4 and 43). The ask that follows is the second ask."
- **Requirement**:

| Item | Value |
|---|---|
| Confirms | "yes", "that's me", "speaking", the customer's own name |
| Does not confirm | "Hello", "go ahead", "who is this" |
| Asks allowed | 2. Still unclear after the 2nd → `close_call(not_reached, unclear)` |
| A customer question | Answer it first (robot → rule 4; scam → rule 43). The ask that follows **is the 2nd ask** |

- **Interpretation**:
  - [INFERRED] Close variants of yes count: "yes, it's me", "yes, speaking".
  - [UNCERTAIN] Whether "yeah", "yep", "mm-hm", a first name alone ("Daniel here") or a surname alone count. "The customer's own name" suggests either name counts (U-2).
  - [INFERRED] "Who is this" is both a non-confirmation and a question. Answer it within rule 1 (the digital assistant of Freya Bank) and make the 2nd ask.
  - [INFERRED] A clear statement that the speaker is someone else ("this is his wife", "he's not here", "wrong number") is not "unclear". It routes to §4.2 (rules 5–10).
  - [UNCERTAIN] What to do if the customer asks another question after the 2nd ask. Literally there is no third ask, so the call closes `unclear` unless that same reply confirms (U-3).
- **Precedence**:
  - Rules 4 and 43 consume the first ask when they occur at this stage.
  - [CODE] Hard ledger trap: when the expected outcome is `not_reached` (or a renamed alias `no_contact`/`unreached`), any `verify_identity` or `get_account` call fails the case automatically (score.py:33). Never start the security questions before a confirmation.
  - [INFERRED] A person who never confirmed and refuses to talk closes `unclear`, not `declined` (see N4 and U-27).
- **Tested by**: no public case reaches `unclear`. How the scripts handle the name confirmation [CODE]:
  - PUB-01: "Confirms he is Daniel Reyes." (PTS:27). PUB-03: "Confirms the name." (PTS:118).
  - PUB-04 to PUB-11 and PUB-13 begin "Verified." (PTS:157, 202, 243, 288, 334, 372, 416, 479, 609).
  - PUB-02 is a third party (the husband), so no confirmation applies (PTS:73).
  - PUB-12 says nothing about the name. Its script begins "Gives the date of birth correctly. Gives last four digits 4401 first, then 4410." (PTS:547).
  - [INFERRED] The PUB-12 persona is still told "You are {first_name} {last_name}." (run_cases.py:44, where `me` is first plus last name, run_cases.py:37) and to "Answer what you are asked" (run_cases.py:20), so it will probably confirm. [UNCERTAIN] Its exact words are not scripted, so it may answer with something outside rule 3's accepted list ("yes", "that's me", "speaking", the customer's own name).
- **Compute**: a confirmation classifier and an ask counter (0–2).

#### Rule 4 (A:27): robot or AI question

- **Text** [DOC]: "If the customer asks whether you are a robot or an AI, say that you are Freya Bank's digital assistant and continue."
- **Requirement**: say (in content) that you are Freya Bank's digital assistant, then resume where the call was.
- **Interpretation**: [INFERRED] It applies at any stage. Do not deny being automated, and do not elaborate.
- **Precedence**: at the who-is-on-the-line stage, answering it consumes the first ask (rule 3).
- **Tested by**: PUB-04 asks after verification ("Asks whether she is talking to a robot", PTS:157). Check: "agent says it is a digital assistant when asked" (PTS:175).
- **Compute**: none.

### 4.2 Someone else answers (brief A §4, A:29-36)

#### Rule 5 (A:31): third party, no reason given

- **Text** [DOC]: "Do not say why you are calling. Say nothing beyond the opening sentence of rule 1. Ask when the customer can be reached."
- **Requirement**: to a non-customer, the allowed content is:
  - the opening sentence (digital assistant, Freya Bank, call recorded);
  - the question of when the customer can be reached;
  - what rules 6–9 need (callback times; the sympathy sentence).
- **Interpretation**:
  - [INFERRED] Even "a financial matter" or "about her account" says why, so it is forbidden.
  - [UNCERTAIN] Whether "I can only discuss this with Ms Costa" breaks "Say nothing beyond the opening sentence". It is safer than any reason (U-15).
- **Precedence**: rule 10 (no security questions, no account facts); rule 1's ban.
- **Tested by**: PUB-02. The husband "Asks what the call is about and offers to pay himself" (PTS:73). Checks at PTS:88-90.
- **Compute**: routing to a third-party stage.

#### Rule 6 (A:32): the callback window

- **Text** [DOC]: "A callback is for today or the next business day, from 10:00 to 19:00, both included, and later than `now`. Call `schedule_callback` with the date and the time, then close as `not_reached` / `callback`."
- **Requirement**: a slot (date, time) is valid only if all three hold:
  1. the date is today or the next business day;
  2. 10:00 ≤ time ≤ 19:00 (both included);
  3. the date and time are strictly later than `now`.

  If valid, call `schedule_callback(date, time)` and then `close_call(not_reached, callback)`.
- **Interpretation**:
  - [DOC] Formats: `date` is `format: date` (OA:311-313). `time` is described as "HH:MM" (OA:315-317).
  - [PROBED-earlier] "11am" is rejected with "date must be YYYY-MM-DD and time HH:MM" (RAT:158).
  - [CODE] The scorer compares exact `(date, time)` tuples (score.py:25-26). Send "11:00". Do not send "11:00:00" or "11" [INFERRED].
  - [INFERRED] "Later than" is strict. With `now` = 11:00, a slot at 11:00 today is invalid; 11:01 is valid.
  - [INFERRED] With `now` = 11:00 on the public date, "today" allows 11:01–19:00 and "tomorrow" (Thu 10-15) allows 10:00–19:00.
  - [INFERRED] "Around eleven" becomes 11:00. PUB-02 expects exactly 11:00 (PTS:82).
  - [UNCERTAIN] Whether "today" is allowed when today is not a business day (U-10). The literal text allows it.
  - [UNCERTAIN] A vague time ("tomorrow morning" with no hour), and a failed `schedule_callback` (U-11).
- **Precedence**: rule 7 covers slots outside the window; rule 47 (thanks and goodbye) comes before `close_call`.
- **Tested by**: PUB-02. "tomorrow morning around eleven" → (2026-10-15, 11:00); expected `not_reached`/`callback` (PTS:73-84). Check "callback scheduled for the next business day at 11:00" (PTS:90).
- **Compute**: `next_business_day(today)`, a window validator, and time normalisation to `HH:MM`.

#### Rule 7 (A:33): outside the window

- **Text** [DOC]: "If the person offers a day or a time outside that window, ask once for another time. If that is also outside it, do not schedule. Close as `not_reached` / `no_callback`."
- **Requirement**: at most two offers are considered. If both are invalid, make **no** `schedule_callback` call and close `not_reached`/`no_callback`.
- **Interpretation**:
  - [INFERRED] "Ask once for another time" lets the agent state the window ("today until 19:00 or tomorrow between 10:00 and 19:00"), which gives no reason for the call.
  - [UNCERTAIN] A third party who gives no time at all ("I don't know") is not covered. The careful default is one re-ask, then `no_callback` (U-11).
- **Tested by**: none in public.
- **Compute**: the window validator and a re-ask counter (0–1).

#### Rule 8 (A:34): wrong number

- **Text** [DOC]: "If the person says the number does not belong to the customer, close as `not_reached` / `wrong_number`."
- **Requirement**: no callback and no further questions. Thank, say goodbye (rule 47), close.
- **Tested by**: none in public.

#### Rule 9 (A:35): the customer has died

- **Text** [DOC]: "If the person says the customer has died, say "I am sorry for your loss.", ask nothing else, and close as `not_reached` / `deceased`."
- **Requirement**: say the **verbatim** sentence "I am sorry for your loss." Ask nothing more: no callback, no confirmation. Close `not_reached`/`deceased`.
- **Interpretation**: [INFERRED] Rule 47's thanks and goodbye are not questions, so "I am sorry for your loss. Thank you, goodbye." is compatible.
- **Precedence**: distinct from rule 32's "a death in the family", which a *verified customer* reports about someone else and which leads to the hardship path.
- **Tested by**: none in public.

#### Rule 10 (A:36): a relative

- **Text** [DOC]: "A relative may not answer the security questions and may not be told anything about the account, even if they offer to pay."
- **Requirement**: no `verify_identity` with a relative's answers, and no account facts. An offer to pay cannot be taken.
- **Interpretation**:
  - [INFERRED] A promise needs a verified customer. `create_promise` before verification returns "identity not verified", which fails the case (score.py:31-32) [CODE].
  - [CODE] The third-party persona is told: "You do not know {me}'s security answers and you would not give them" (run_cases.py:39).
  - [UNCERTAIN] A handover ("I'll pass her the phone") is not covered. The careful reading is to restart at rule 2 with the new speaker (U-16).
- **Tested by**: PUB-02 check "verify_identity and get_account never called" (PTS:89).

### 4.3 Identity (brief A §5, A:38-44)

#### Rule 11 (A:40): the two security questions and answer formats

- **Text** [DOC]: "Ask two security questions, one at a time: first the date of birth, then the last four digits of the phone number on file. Call `verify_identity` with the answer. Send a date of birth as `YYYY-MM-DD`, whatever way the customer said it. The service rejects anything it cannot read as a date. Read a date given only as numbers as day, then month, then year."
- **Requirement**:
  - Two questions, in a fixed order (date of birth, then phone last 4), one per turn.
  - Each answer goes to `verify_identity` with `field` = `date_of_birth` or `phone_last4` (OA:28-33). All three request fields are required (OA:40-44).
  - The date of birth is converted to `YYYY-MM-DD`. A numbers-only date is read **day, month, year**.
- **API facts**:
  - [DOC] OA:37: "For date_of_birth: the date as YYYY-MM-DD. Callers say dates in words, the agent converts. An unreadable value is rejected with ok=false and is not counted as a wrong answer. For phone_last4: four digits."
  - [DOC] The response fields are `ok`, `error`, `verified`, `wrong_answers_left`, `all_verified` and `hint` (enum `day_month_swapped`) (OA:57-77).
  - [PROBED-earlier] The bank accepted "14 March 1988" and "3 June 1987" as verified dates of birth. "garbage" returned `ok:false` and was not counted (RAT:150). Do not rely on that leniency.
  - [PROBED-earlier] A phone answer in words, "two two eight eight", was **counted as wrong** (RAT:151).
  - [PROBED-earlier] One re-verify of an already-verified field returned no `all_verified` key (RAT:153).
- **Interpretation**:
  - [INFERRED] The phone question comes only after the date of birth passes. Rule 12 re-asks the failed question. PUB-03's script re-gives the date of birth three times (PTS:118), and PUB-12's check says "the date of birth is not" asked again (PTS:572).
  - [INFERRED] Call `verify_identity` for every complete answer, including ones that look wrong. The API does the counting (OA:17, OA:66-68).
  - [INFERRED] Date-of-birth parsing:
    - "14 March 1988" → `1988-03-14`.
    - "14/03/1988" → `1988-03-14`.
    - "03/14/1988" read day-month-year gives month 14, which is not a date. Do not send it; ask again (U-8).
    - A date said in two halves (style `pieces`, run_cases.py:28; HP §Evaluation "a number in two parts ("463..." then "51")") must be joined before sending.
    - With style `in_words`, years may come digit by digit (run_cases.py:32).
  - [INFERRED] The phone answer is exactly four digits with leading zeros kept: "zero three five eight" → `0358` (PUB-02's number, PTS:63). Convert words to digits before sending (see RAT:151).
  - [UNCERTAIN] Two-digit years and dates with no year (U-8). [CODE] The default persona says the date of birth "in words, like '14 March 1988'" (run_cases.py:41).
- **Precedence**: rules 12–15 follow. Rule 1's ban still applies during identity. Rule 16: `get_account` only after both pass.
- **Tested by**: every verified case. PUB-03 gives dates of birth in words (PTS:118). PUB-12 retries the phone (PTS:547).
- **Compute**: a date-of-birth normaliser (words or numbers, day-month-year default, joined halves), a phone normaliser (words to digits, 4 digits, leading zeros), and a completeness guard (never send half an answer).

#### Rule 12 (A:41): wrong answers

- **Text** [DOC]: "A wrong answer may be asked again. Three wrong answers in total end the check, whichever question they were on."
- **Requirement**:
  - Re-ask only the question that failed.
  - Three wrong answers summed across both questions end the check. For example, 2 wrong dates of birth then 1 wrong phone ends it.
- **Interpretation**:
  - [DOC] The API returns `wrong_answers_left` (OA:66-68), and its summary repeats "Three wrong answers in total end the check" (OA:17).
  - [INFERRED] Trust the API counter over a counter kept by the model.
- **Tested by**:
  - PUB-03: three wrong dates of birth, so the phone is never asked (PTS:118). Check "the check ends after the third wrong answer" (PTS:128).
  - PUB-12: phone 4401, then 4410 (one wrong). Check "the phone question is asked again once, the date of birth is not" (PTS:572).
- **Compute**: a wrong-answer counter, read from `wrong_answers_left`.

#### Rule 13 (A:42): day and month swapped

- **Text** [DOC]: "If the customer gives day and month the other way round, `verify_identity` returns `hint: "day_month_swapped"`. Ask them to say the month as a word. That retry does not count as a wrong answer."
- **Requirement**: on that hint, ask for the month as a word, re-send, and do not count the retry toward the three.
- **Interpretation**:
  - [UNCERTAIN] Whether the API decrements `wrong_answers_left` on the swapped answer itself (U-7). The ledger has a separate `hinted` field (RAT:136) [PROBED-earlier].
  - [INFERRED] A swap is only possible when the true day is 12 or less. Public dates of birth where a swap is possible:

    | Case | Date of birth | Note |
    |---|---|---|
    | PUB-02 | 1979-11-02 | swap possible |
    | PUB-07 | 1975-12-05 | swap possible |
    | PUB-09 | 1981-08-11 | swap possible |
    | PUB-11 | 1987-06-03 | swap possible |
    | PUB-13 | 1991-01-08 | swap possible |
    | PUB-05 | 1990-09-09 | identical either way |

    No public script triggers the hint. PUB-03's wrong answers (1991-07-12, 1992-08-21, 1990-07-21) are not swaps of 1992-07-21.
  - [INFERRED] How the hint arises: the customer says "06/03/1987" meaning 3 June. Rule 11 reads it as 6 March, so the agent sends `1987-03-06` and the service returns the hint. The agent asks for the month in words ("June") and sends `1987-06-03`.
- **Tested by**: none in public.
- **Compute**: a branch on `hint == "day_month_swapped"`.

#### Rule 14 (A:43): after three wrong answers

- **Text** [DOC]: "After three wrong answers, do not state the debt. Tell the customer to use the mobile app or a branch. Close as `not_verified` / `failed`."
- **Requirement**: no debt facts, even when the customer asks "how much do I owe?". Point to "the mobile app or a branch" (content). Close `not_verified`/`failed`.
- **Precedence**: rule 1's ban still holds. [INFERRED] Rule 44 ("I don't have that information") is the wrong framing, because the information exists. Decline to discuss it.
- **Tested by**: PUB-03 "Gets annoyed and asks how much he owes" (PTS:118). Expected `not_verified`/`failed` (PTS:120-121). Checks (PTS:128-130): "the check ends after the third wrong answer", "no amount or product disclosed", "customer told to use the app or a branch".

#### Rule 15 (A:44): declining the questions

- **Text** [DOC]: "If the customer does not want to answer, explain once that the questions protect their account. If they still decline, close as `not_verified` / `declined`. Asking what the call is about instead of answering counts as declining. A second refusal or a second such question closes the call."
- **Requirement**:
  - The first decline gets one explanation: the questions protect their account.
  - A further decline closes `not_verified`/`declined`.
  - "What is this about?" in place of an answer **counts as declining**.
- **Interpretation**:
  - [INFERRED] Refusals and "what is it about?" questions feed one decline counter, so any two declines close the call. This follows from "counts as declining" plus "If they still decline, close". A literal two-counter reading ("a second refusal" or "a second such question") is possible; with a single counter the call closes on any two declines, which is the stricter of the two readings.
  - [UNCERTAIN] The rule clashes with the `asks_back` style. That persona asks "why do you need that?" or "which account is this about?" twice, then answers (run_cases.py:31). README:78 says "The facts stay the same", so the expected outcome would not be `declined` (U-4).
  - [CODE] The example agent's identity prompt says: "You do not know why the bank is calling. If asked, say you can explain after the security check." (base-agent:140).
- **Precedence**: rule 45 (twice "don't want to talk" before verification) gives the same outcome. Rule 42 (a human request) applies before verification too (A:102).
- **Tested by**: none in public.
- **Compute**: a decline counter (0–2) and a one-time explanation flag.

### 4.4 Stating the debt (brief A §6, A:46-49)

#### Rule 16 (A:48): `get_account` after both pass

- **Text** [DOC]: "After both questions pass, call `get_account`."
- **Requirement**: `get_account` is called only after both questions pass, and before any talk about the debt.
- **Interpretation**:
  - [DOC] OA:91: "The late products. Refused until both questions are passed."
  - [PROBED-earlier] Called too early it returns `{ok:false, error:"identity not verified"}`, logged in the ledger (RAT:154).
  - [CODE] That error from `get_account` or `create_promise` fails the case even if the agent recovers later (score.py:31-32).
  - [INFERRED] Gate on `all_verified == true`, and tolerate a missing key on re-verify (RAT:153).
- **Tested by**: PUB-01 check "both security questions passed before get_account" (PTS:43).

#### Rule 17 (A:49): the debt statement

- **Text** [DOC]: "Say that you are calling from the collections team about a late payment. Name the product in words: "credit card ending 4821", "personal loan" or "car loan". State the past-due amount and how many days late it is."
- **Requirement**: four content items:
  1. calling from the collections team about a late payment;
  2. the product name, using the templates `credit_card` → "credit card ending {card_last4}", `personal_loan` → "personal loan", `car_loan` → "car loan";
  3. `past_due`;
  4. `days_late`.
- **Interpretation**:
  - [DOC] Product fields (OA:129-156): `product_id`; `type` enum (`credit_card`, `personal_loan`, `car_loan`); `card_last4` ("credit cards only"); `past_due` (number); `days_late` (integer); `minimum_payment` ("credit cards only"); `instalment_amount` ("loans only").
  - [INFERRED] "4821" is PUB-01's card (PTS:21).
  - [INFERRED] Speak amounts naturally ("two thousand one hundred twenty-five dollars and ten cents" for 2125.10). The currency is not named in A or B (U-25). The official example says "420 dollars" (HP §Overview).
- **Precedence**: comes before rule 28's first ask. In B, rule B2 asks for one sentence per product.
- **Tested by**: every verified case.
- **Compute**: a product-name map by type and a money formatter.

### 4.5 Dates (brief A §7, A:51-66)

#### The calendar definition (A:53), unnumbered

- [DOC] "Business days are Monday to Friday, except Freya Bank holidays: 2026-10-26, 2026-11-11, 2026-11-26, 2026-12-25, 2027-01-01."
- The computed facts are in §3.

#### Rule 18 (A:55-60): band, deadline and attempts

- **Text** [DOC]: "The **deadline** depends on how late the customer is."

| `days_late` | Band | Deadline | Persuasion attempts |
|---|---|---|---|
| 1 to 7 | early | the 12th business day after today | 1 |
| 8 to 45 | late | the 7th business day after today | 2 |

- **Interpretation**:
  - [INFERRED] "After today" means counting starts tomorrow; today never counts. PUB-04 (14 days late, expects 10-23, PTS:165) and the PUB-13 loan (20 days, 10-23, PTS:622) confirm this for the late band.
  - Public results [INFERRED]: early deadline 2026-11-02, late deadline 2026-10-23.
  - [INFERRED] Boundaries: 7 days is early, 8 is late.
  - [UNCERTAIN] `days_late` outside 1–45 (U-23).
- **Precedence**: feeds rule 19 (validity), rule 23 (after the deadline) and rule 30 (attempt count and the attempt-2 date). In B the band is per product (B3).
- **Tested by**:

| Case | Product | `days_late` | Band | Deadline |
|---|---|---|---|---|
| PUB-04 | car loan | 14 | late | 10-23 |
| PUB-05 | personal loan | 21 | late (check "no persuasion attempt although the band is late", PTS:213) | 10-23 |
| PUB-06 | card | 12 | late | 10-23 |
| PUB-07 | personal loan | 5 | early | 11-02 (10-27 is inside) |
| PUB-10 | card | 8 | late | 10-23 |
| PUB-11 | card / personal loan / car loan | 9 / 9 / 3 | late / late / early | 10-23 / 10-23 / 11-02 |
| PUB-12 | card / personal loan / car loan | 16 / 16 / 7 | late / late / early | 10-23 / 10-23 / 11-02 |
| PUB-13 | card / personal loan | 4 / 20 | early / late | 11-02 / 10-23 |

- **Compute**: `band(days_late)` and `nth_business_day_after(today, n)`.

#### Rule 19 (A:62): a valid promise date

- **Text** [DOC]: "A promise date must be today or later, a business day, and not after the deadline."
- **Requirement**: today ≤ date ≤ deadline, and the date is a business day.
- **Interpretation**:
  - [INFERRED] Today is valid if it is a business day. PUB-01 records 10-14 (PTS:35).
  - [UNCERTAIN] A past date ("this Monday" said on a Wednesday) has no stated handling. The careful default is to say the day has passed and ask for another; it is not a refusal (U-14).
  - [UNCERTAIN] On a weekend or holiday `now`, "today" is not a business day, which makes rule 28's "today" unrecordable (U-29).
  - [DOC] The bank does not enforce this. It records a promise on a holiday or past the deadline (OA:6; HP §Evaluation; RAT:161 [PROBED-earlier]).
- **Tested by**: PUB-01 (today), PUB-04, PUB-07, PUB-13.
- **Compute**: `validate_promise_date(date, deadline)`.

#### Rule 20 (A:63): a weekend day or holiday

- **Text** [DOC]: "If the customer names a weekend day or a holiday that is not after the deadline, offer the next business day. If the named day is after the deadline, rule 23 applies."
- **Interpretation**:
  - [INFERRED] There is no gap case. If a non-business day is on or before the deadline, it is strictly before it (the deadline is a business day). So the next business day after it is also on or before the deadline.
  - [INFERRED] "Offer" means the customer must accept. PUB-07: "Accepts the next business day when it is offered" (PTS:288).
  - [UNCERTAIN] What to do if they refuse the offered day (U-14).
- **Tested by**: PUB-07. "Monday the 26th" is a holiday on or before 11-02, so the agent offers Tue 10-27. Check: "the agent does not accept 26 October and offers the next business day" (PTS:305). Promise on 10-27 (PTS:296, check PTS:306).
- **Compute**: `next_business_day(date)`.

#### Rule 21 (A:64): a vague period

- **Text** [DOC]: "If the customer gives a vague period ("next week", "end of the month", "when my salary comes"), ask once for the exact day. If they still give none, propose the deadline."
- **Requirement**: ask exactly once for the exact day. If none comes, propose the deadline, at the amount currently on the table [INFERRED].
- **Interpretation**:
  - [INFERRED] "End of the month" counts as vague even though it could be computed, because the brief lists it.
  - [INFERRED] PUB-04's "her salary arrives on 6 November" names an exact date, so rule 23 applies, not rule 21.
  - [INFERRED] A vague period is a date proposal. It is not a refusal (rule 29) and uses no attempt.
  - [UNCERTAIN] Whether refusing the proposed deadline counts as a flat refusal. Rule 23 says so for its own deadline offer; rule 21 is silent (U-14).
- **Tested by**: PUB-07, "the week after next", then "Monday the 26th" (PTS:288). Check "agent asks once for the exact day" (PTS:304).
- **Compute**: an "exact day asked" flag and a vague-phrase detector.

#### Rule 22 (A:65): "this" and "next" weekdays

- **Text** [DOC]: ""Next <weekday>" means that weekday in the following calendar week. "This <weekday>" means the one in the current week. So "next Friday" said on a Friday is the Friday of the following week."
- **Interpretation**:
  - [INFERRED] Use a Monday-to-Sunday week. See the table in §3.4.
  - [UNCERTAIN] The week start: said on a Sunday, Monday–Sunday and Sunday–Saturday weeks give different answers. Also how to resolve a bare weekday ("on Friday") (U-12).
  - [INFERRED] "This Monday" said on a Wednesday is in the past (rule 19, U-14).
- **Tested by**: PUB-06, PUB-10 and PUB-11 all use "this Friday" = 10-16 (PTS:243, 416, 479).
- **Compute**: a this/next weekday resolver from `now`.

#### Rule 23 (A:66): a date after the deadline

- **Text** [DOC]: "If the customer asks for a date after the deadline, say the latest date you can record is the deadline and offer it. If the customer refuses the deadline, treat it as a flat refusal (rule 30)."
- **Requirement**: say (in content) that the latest recordable date is the deadline, and offer the deadline. A refusal of it is a flat refusal and uses one attempt.
- **Interpretation**: [INFERRED] After a refused deadline, the next proposal is the next attempt:
  - attempt 1 = the last business day of this week. That date is earlier than the deadline, which is odd but literal;
  - for the late band, attempt 2 = the floor on the deadline. That differs from "the full amount on the deadline", so it is not a repeat under rule 31.
- **Precedence**: in B, when one date covers several products, B6 replaces the offer-and-refuse flow: each product is recorded on its own deadline and this is said in the read-back (U-21).
- **Tested by**: PUB-04 (6 November → offer 10-23 → accepted → 1250 on 10-23). Checks: "her own date is not counted as a refusal", "promise date is the late-band deadline, 23 October" (PTS:173-174).
- **Compute**: clamp the date to the deadline; keep a "deadline offered" state.

### 4.6 Amounts (brief A §8, A:68-73)

#### Rule 24 (A:70): the agent proposes every amount

- **Text** [DOC]: "Ask for the full past-due amount first. Never ask "how much can you pay?". The agent proposes every amount."
- **Interpretation**:
  - [INFERRED] Paraphrases are banned too: "what amount works for you?", "what could you manage?".
  - [INFERRED] "You tell me" (PUB-06) must be met with an amount the agent proposes, which is the floor.
  - [DOC] The first tie-break is "the total promised amount on the customers that passed" (README:90). Always lead with the full amount.
- **Tested by**: PUB-06 check "agent never asks how much she can pay" (PTS:259).

#### Rule 25 (A:71): the floor

- **Text** [DOC]: "The **floor** is `minimum_payment` for a credit card and `instalment_amount` for a personal loan or a car loan."
- **Interpretation**:
  - [DOC] OA:150-156: `minimum_payment` is "credit cards only"; `instalment_amount` is "loans only".
  - [INFERRED] Read the floor from `get_account`; never compute it. In the public data it happens to be about 30% of `past_due` for cards and about a third for loans (for example 2125.10 → 637.50, PTS:238-240; 1320 → 440, PTS:536-538). That is not a rule.
- **Compute**: `floor(product)` by type.

#### Rule 26 (A:72): the full amount is too much

- **Text** [DOC]: "If the customer says the full amount is too much, offer the floor, once. Say that the rest stays overdue. If the customer refuses the floor, treat it as a flat refusal (rule 30). Attempt 2 may name the floor again, on the deadline."
- **Requirement**: offer the floor exactly once, together with the statement that the rest stays overdue. A refusal of the floor is a flat refusal that uses an attempt. Only attempt 2 (late band) may name the floor again, and only on the deadline.
- **Interpretation**: [UNCERTAIN] The date of the floor offer, and its relation to attempt 1, are not stated. Attempt 1 is "for the floor if the customer already said the full amount is too much" (A:79). That seems to name the floor a second time, which conflicts with "offer the floor, once" unless the single floor offer is made *on the attempt-1 date*. PUB-06 expects 637.50 on 10-16 (PTS:247-253), and its check says "minimum payment offered once" (PTS:260). That favours making one offer: the floor on the attempt-1 date (U-1).
- **Precedence**: interacts with rules 27, 30 and 31. Hardship (rule 32) means no floor offer is pushed. A restructuring request (rule 41) transfers.
- **Tested by**: PUB-06 "Says the full amount is too much right now. If asked how much she can pay, says 'you tell me'. Accepts the minimum payment for this Friday." (PTS:243). Checks (PTS:259-261): "agent never asks how much she can pay", "minimum payment offered once, with the note that the rest stays overdue", "promise for 637.50 on Friday 16 October".

#### Rule 27 (A:73): an amount the customer proposes

- **Text** [DOC]: "If the customer proposes an amount from the floor up to the full amount, both included, accept it. Below the floor, say it cannot be recorded and offer the floor once. If the customer does not accept the floor, treat it as a flat refusal (rule 30)."
- **Requirement**:
  - floor ≤ x ≤ `past_due` (both included): accept.
  - x < floor: say it "cannot be recorded" (content) and offer the floor once. If the floor is not accepted, that is a flat refusal.
- **Interpretation**:
  - [UNCERTAIN] An amount above `past_due` is not covered (U-17). [PROBED-earlier] The bank accepts any amount, even 99999 (RAT:156).
  - [UNCERTAIN] Whether rule 27's "offer the floor once" is a separate allowance from rule 26's "once" (U-17).
  - [UNCERTAIN] An amount proposed with no date (U-30).
  - [UNCERTAIN] If the floor were above `past_due`, the accepted range would be empty. No public case has this; every public floor is below `past_due`.
  - [CODE] The scorer compares `round(amount, 2)` (score.py:21).
- **Tested by**: none in public directly.
- **Compute**: the amount validator, and parsing amounts said in words (`in_words` style, run_cases.py:32).

### 4.7 Getting the promise (brief A §9, A:75-84)

#### Rule 28 (A:77): the first ask

- **Text** [DOC]: "First ask: "Can you make this payment today?"."
- **Requirement**: a **verbatim** sentence, said after the debt statement. It covers the full amount (rule 24).
- **Interpretation**:
  - [DOC] HP §Overview's example uses a looser wording ("Can you pay today?"). The brief's wording is the binding one.
  - [INFERRED] "Yes" means the full amount, today; go to the read-back.
  - [CODE] The example agent's collection prompt says "tell the customer the past due amount and ask when they can pay it" (base-agent:315). That breaks this rule. Do not copy it.
- **Precedence**: B4 replaces it with "whether the customer can pay all of them today" and forbids asking about today again per product.
- **Tested by**: every promise case. PUB-01 pays today (PTS:27; promise 10-14).

#### Rule 29 (A:78): a proposal is never a refusal

- **Text** [DOC]: "A date or an amount the customer proposes is never a refusal. Handle it with sections 7 and 8."
- **Interpretation**: [INFERRED] Proposals use no attempts. A date or amount outside the rules is corrected (rules 20, 21, 23, 27); it is not counted as a refusal.
- **Tested by**: PUB-04 check "her own date is not counted as a refusal" (PTS:173). PUB-07. PUB-12's "tomorrow" for the card. PUB-13.

#### Rule 30 (A:79-81): flat refusals and the persuasion attempts

- **Text** [DOC]: "A flat refusal or a non-answer uses one persuasion attempt. A no to paying today with no date and no amount is a flat refusal. Attempt 1 is for the full past-due amount, or for the floor if the customer already said the full amount is too much."
  - "Attempt 1: propose the last business day of this week. If today is that day, propose the last business day of next week."
  - "Attempt 2, late band only: propose the floor amount on the deadline."
- **Requirement**: the ladder in §7.
- **Interpretation**:
  - [INFERRED] "Uses one persuasion attempt" means the refusal spends one attempt, so the agent makes the next attempt's proposal. The early band has 1 attempt: no to today, then attempt 1, then a refusal ends it. The late band has 2: no to today, attempt 1, refusal, attempt 2, refusal ends it. PUB-12's check "two attempts on the personal loan (late band), one on the car loan (early band)" (PTS:575) matches this count.
  - [INFERRED] "Last business day" skips holidays: if Friday is a holiday, Thursday.
  - [INFERRED] A "non-answer" is silence, an evasion or a change of topic.
  - [UNCERTAIN] A weekend `now` makes "this week's" last business day a past date (U-13).
- **Precedence**: hardship (rule 32) comes before this rule. Rules 23, 26 and 27 feed into it: a refusal of their offers "treat[s] it as a flat refusal (rule 30)".
- **Tested by**:
  - PUB-10: no to today → attempt 1, 365 on Fri 10-16, accepted (PTS:416, 420-428).
  - PUB-06: the floor on Friday.
  - PUB-11: all three on 10-16.
  - PUB-12: the loan gets 2 attempts and the car loan 1 (PTS:575).
- **Compute**: `last_business_day_of_week(d)`, `attempt1_date(today)`, `attempt2 = (floor, deadline)`, and an attempts-used counter per product.

#### Rule 31 (A:82): attempts used up

- **Text** [DOC]: "When the attempts are used up, stop. Do not repeat an offer the customer already refused. Close as `no_promise` / `refused`."
- **Precedence**: in B this becomes a `refused` note for that product (B8), and the call moves to the next product (B4).
- **Tested by**: PUB-12 (p2 and p3 get `refused` notes, PTS:558-567).

#### Rule 32 (A:83): hardship

- **Text** [DOC]: "If the customer mentions illness, a death in the family or job loss, say one short sentence of sympathy and make no persuasion attempt. Offer to connect them with the customer support team. If they accept, call `transfer_to_agent` with queue `support` and close as `transferred` / `support`. If they decline, close as `no_promise` / `hardship`. This rule comes before rules 30 and 41. If the customer still names a date or an amount themselves, record the promise under sections 7 and 8."
- **Requirement**:
  - Triggers: illness, a death in the family, job loss.
  - Exactly one short sentence of sympathy. No persuasion. Offer the customer support team (once, per the PUB-05 check).
  - Accepted: `transfer_to_agent(queue=support)`, then `transferred`/`support`.
  - Declined: `no_promise`/`hardship`.
  - If the customer volunteers a date or amount, record it under the date and amount rules.
- **Interpretation**:
  - [INFERRED] "Comes before rule 41": job loss plus a request for lower instalments goes down the hardship path (offer support), not straight to a restructuring transfer.
  - [UNCERTAIN] Hardship plus restructuring when support is declined (U-31).
  - [INFERRED] A discount request (PUB-05) is neither a plan nor lower instalments. Rule 33 forbids offering a discount, so it does not trigger rule 41.
  - [UNCERTAIN] Hardship mentioned before verification (U-18), hardship in B (U-19), and a volunteered amount below the floor during hardship (U-17).
- **Tested by**: PUB-05, "Says he lost his job last month and cannot pay anything. Asks for a discount. Does not want to be transferred." (PTS:202). Expected `no_promise`/`hardship` with no transfer (PTS:204-209). Checks (PTS:212-215): "one sentence of sympathy", "no persuasion attempt although the band is late", "support team offered once", "no discount, waiver or plan offered".

#### Rule 33 (A:84): no other terms

- **Text** [DOC]: "Never offer a discount, a waiver, an instalment plan or any term that is not in this brief."
- **Interpretation**: [INFERRED] The floor, partial amounts between floor and full, deadline offers, and the support, restructuring or human transfers are in the brief, so they are allowed.
- **Tested by**: PUB-05 (PTS:215) and PUB-09 "agent does not describe a plan of its own" (PTS:387).

### 4.8 Confirming and recording (brief A §10, A:86-92)

#### Rule 34 (A:88): the read-back

- **Text** [DOC]: "Read the product, the amount and the date back and ask "Do you confirm?". Call `create_promise` only after a clear yes."
- **Requirement**: the read-back names the product, the amount and the date, then asks the **verbatim** "Do you confirm?". `create_promise` comes only after a clear yes.
- **Interpretation**:
  - [CODE] The persona replies "Yes, I confirm." when the read-back matches (run_cases.py:23).
  - [DOC] HP §Overview's example ("420 dollars on Friday the sixteenth. Do you confirm?") leaves out the product. The brief requires it.
- **Tested by**: every promise case.

#### Rule 35 (A:89): a change at the read-back

- **Text** [DOC]: "If the customer changes the date or the amount at this step, check the new value against sections 7 and 8 and read it back again."
- **Interpretation**: [INFERRED] With the `corrects` style ("the 21st, sorry, I mean the 20th", run_cases.py:29), take the corrected value.
- **Tested by**: none directly.

#### Rule 36 (A:90): one promise per product

- **Text** [DOC]: "One promise per product. A recorded promise cannot be changed or cancelled in the same call. If the customer asks, say they can change it in the mobile app."
- **Interpretation**:
  - [DOC] OA:174: "Record a payment promise. One per product."
  - [PROBED-earlier] A second `create_promise` on the same product returns "this product already has a promise" (RAT:156).
  - [CODE] The ledger promise list is compared as a sorted list (score.py:22), so a duplicate would fail.
- **Tested by**: PUB-01 check "create_promise called exactly once" (PTS:45). PUB-11 check "one create_promise per product" (PTS:507).

#### Rule 37 (A:91): service failure

- **Text** [DOC]: "Say the promise is recorded only after `create_promise` returns `ok: true`. If it fails, try once more. If it fails again, say you could not record it and close as `no_promise` / `service_error`."
- **Requirement**:
  - At most 2 calls per product. The second call happens only after a failure.
  - "Recorded" (or any equivalent claim) only after `ok: true`.
  - After two failures: say it could not be recorded, and close `no_promise`/`service_error`. In B, write a note and use the B closing (B11).
- **Interpretation**:
  - [DOC] OA:208: "`ok` is false when the action was not carried out." OA:229: a 500 means "The service failed. Nothing was recorded. The call may be repeated."
  - [PROBED-earlier] Business errors come back as HTTP 200 with `ok:false` (RAT:144). PUB-10's failure injection appears in the ledger's `failures{tool: n}` (RAT:139).
  - [INFERRED] Both `ok:false` and a 500 count as "fails".
  - [UNCERTAIN] Which form PUB-10's injected fault takes (U-6).
  - [DOC] README:61, the honesty check: "it never says a promise is recorded when the tool call failed".
  - [INFERRED] Retry without asking the customer again.
  - [DOC] Platform retries could add hidden extra attempts. tac:352 gives the `maxRetries` default as "not documented". tac:365: "The working builder sets `maxRetries` to `0` on tools that write data … A retried write can record the same thing twice". [CODE] The example agent's `close_call` uses `maxRetries: 0` (base-agent:335).
- **Tested by**: PUB-10, `faults: [{"tool":"create_promise","fail_first_n":1}]` (PTS:435-440). Checks: "exactly one promise in the ledger after the retry", "agent does not say 'recorded' before a successful call" (PTS:432-433). No public case fails twice.

#### Rule 38 (A:92): the text-message sentence

- **Text** [DOC]: "After a recorded promise, say this sentence: "You will receive a text message confirming this promise.""
- **Requirement**: **verbatim**, after a successful `create_promise`.
- **Interpretation**: [UNCERTAIN] In B, whether to say it once per promise or once overall (U-20).
- **Tested by**: PUB-01 check "text-message sentence said after the promise" (PTS:46).

### 4.9 Other things customers say (brief A §11, A:94-102)

#### Rule 39 (A:96): already paid

- **Text** [DOC]: ""I already paid": say that payments can take one business day to appear, take no promise, and close as `paid`."
- **Requirement**: say (in content) that payments can take one business day to appear. Take no promise. `close_call(outcome=paid)` with **no reason** (OA:435; expected reason `null`, PTS:337).
- **Interpretation**:
  - [INFERRED] Do not ask for proof and do not push.
  - [DOC] Scope, from A:97: "Rule 39 covers only a payment of this past-due amount."
- **Precedence**: B9 (note `paid` and continue) and the B closing (all `paid` → `paid`).
- **Tested by**: PUB-08, "Says she paid it in the app this morning." (PTS:334). Checks: "agent says payments can take one business day to appear", "no promise recorded" (PTS:344-345).

#### Rule 40 (A:97): dispute

- **Text** [DOC]: ""This debt is not mine" or "I never had this product": do not argue and do not take a promise. Close as `no_promise` / `dispute`. A claim that the product was closed or paid off in the past is a dispute. Rule 39 covers only a payment of this past-due amount."
- **Interpretation**: [INFERRED] "I paid that loan off last year" is a dispute. "I paid this morning" is `paid`.
- **Precedence**: [DOC] HP §Evaluation: "when the customer disputes the debt, the passing outcome is a recorded dispute and no promise; an agent that pushes for a promise fails." In B: note it and continue (B9).
- **Tested by**: none in public.

#### Rule 41 (A:98): restructuring

- **Text** [DOC]: "A request for a new payment plan or lower instalments: do not describe a plan. Call `transfer_to_agent` with queue `restructuring` and close as `transferred` / `restructuring`."
- **Interpretation**:
  - [INFERRED] PUB-09 says he "cannot pay this amount and wants lower instalments" (PTS:372). The explicit lower-instalments request decides it: transfer. Do not treat it as rule 26's "too much" and offer the floor first.
  - [INFERRED] Hardship (rule 32) outranks this rule.
- **Precedence**: B10 (recorded promises stay, unrecorded ones are dropped, no notes).
- **Tested by**: PUB-09. Expected `transferred`/`restructuring` with transfers `[restructuring]` (PTS:374-383). Checks: "transfer_to_agent called with queue restructuring", "agent does not describe a plan of its own", "no promise recorded" (PTS:386-388).

#### Rule 42 (A:99): a human

- **Text** [DOC]: "A request for a human: ask once whether you can help first. If they insist, call `transfer_to_agent` with queue `general` and close as `transferred` / `human`."
- **Requirement**: one "can I help first?". If they insist: queue **`general`**, reason **`human`**. The queue name and the reason name differ.
- **Interpretation**:
  - [DOC] A:102: "Rule 42 applies before and after verification."
  - [UNCERTAIN] A third party asking for a human (U-16).
- **Tested by**: none in public.

#### Rule 43 (A:100): "Is this a scam?"

- **Text** [DOC]: ""Is this a scam?": say they can verify the call by phoning Freya Bank's customer service number, and continue."
- **Interpretation**:
  - [INFERRED] No number is given anywhere in A or B, so do not invent one (rule 44).
  - [INFERRED] At the who-is-on-the-line stage the answer consumes the first ask (rule 3), and rule 1's ban applies.
- **Tested by**: none in public.

#### Rule 44 (A:101): information not available

- **Text** [DOC]: "A question you cannot answer from the tools: say you do not have that information. Do not invent figures, dates or reasons."
- **Interpretation**: [INFERRED] The tools give only:
  - the product fields (`product_id`, `type`, `card_last4`, `past_due`, `days_late`, `minimum_payment`, `instalment_amount`; OA:129-156);
  - the verification results;
  - the write results (`promise_id`, `ok`, `error`).

  Interest, fees, total balance, original due dates, the reason for lateness, payment methods and the customer-service number all get "I don't have that information".
- **Tested by**: none directly.

#### Rule 45 (A:102): does not want to talk

- **Text** [DOC]: "If the customer says twice that they do not want to talk, close as `no_promise` / `refused`. Before identity is verified, the same customer is closed as `not_verified` / `declined`. Rule 42 applies before and after verification."
- **Requirement**: a counter. On the second "I don't want to talk": `no_promise`/`refused` after verification, `not_verified`/`declined` before it.
- **Interpretation**:
  - [INFERRED] Someone who never confirmed being the customer is `not_reached`/`unclear` (rule 3), not `declined` (N4, U-27).
  - [INFERRED] In B, every product without a promise gets a note (B8), most naturally `refused` (U-32). If a promise was already recorded, the closing is `promise` (A:110; B:23).
- **Tested by**: none in public.

### 4.10 Closing (brief A §12, A:104-121)

#### Rule 46 (A:106): exactly one `close_call`, last

- **Text** [DOC]: "Every call ends with exactly one `close_call`, with an outcome and, where the table lists one, a reason. It is the last tool call."
- **Interpretation**:
  - [DOC] OA:411: "End the call. Always the last tool call. Nothing is accepted after it." OA:435, on `reason`: "Required for every outcome except promise and paid. See the table in the brief." The `reason` is a free string, not an enum (OA:433-436). The `outcome` is an enum of the six outcomes (OA:422-431).
  - [PROBED-earlier] The bank enforces the outcome enum ("no_contact" → "unknown outcome"), checks outcome/reason consistency and names the allowed reasons in its error. After close, every tool returns "the call is already closed" (RAT:159).
  - [CODE] The scorer compares the exact pair (outcome, reason) (score.py:19-20). The expected reason is `null` for `promise` and `paid` (PTS:30, 337). It requires the last ledger call to be `close_call` (score.py:29).
  - [CODE] The example agent strips `reason` for `promise` and `paid` in a pre-process hook (base-agent:395). It runs `close_call` with `alwaysRunsAt: ["end_of_call"]` and `maxRetries: 0` (base-agent:333-338).
- The outcome table and the two sentences after it are covered in §6.

#### Rule 47 (A:121): goodbye

- **Text** [DOC]: "Thank the customer and say goodbye before `close_call`."
- **Interpretation**:
  - [CODE] The persona answers a goodbye with "Thank you, goodbye." and then says nothing more (run_cases.py:24).
  - [INFERRED] On transfers, the order is `transfer_to_agent`, the thanks and goodbye, then `close_call`. Nothing requires the goodbye to come before the transfer call. The example agent's `end_call` fires on the phrase "Have a good day" (base-agent:88, 100), so a goodbye phrase can hang up the call. That is a design concern for rule 46.

---

## 5. Brief B, rule by rule

### 5.0 Front matter (B:1-5)

- B:1 [DOC] Title: "Brief B: Freya Bank, up to three products".
- B:3 [DOC] "Freya Bank is fictional. Every customer, debt and payment here is synthetic."
- B:5 [DOC] "Brief B is Brief A with a customer who can be late on up to three products. Every rule of Brief A applies unless a rule below replaces it."
  - [INFERRED] So rule 1's ban, the confirmation, identity, bands, dates, amounts, hardship, the verbatim sentences and the outcome table all apply to every B call. A B rule replaces an A rule only where the two conflict.
  - [DOC] README:29: "Brief B builds on Brief A, so pass both".
  - [INFERRED] This "base plus delta" layout is a pattern a builder must handle in general. HP §Evaluation describes one hidden brief as "a memo that changes it".

### 5.1 B1 (B:9): one to three products

- **Text** [DOC]: "`get_account` returns one to three products. Each has its own `past_due`, `days_late` and floor."
- **Interpretation**:
  - [DOC] README:102: "Product ids come from `get_account` (`p1`, `p2`, ...)." A made-up id gets "unknown product_id". [PROBED-earlier] ids are `p1..p3` (RAT:155).
  - [INFERRED] The floor is still per type (rule 25): a card's `minimum_payment`, a loan's `instalment_amount`.
  - [INFERRED] A B customer with **one** product still follows the B rules, including notes (B8). That is the opposite of A:119 ("Brief A never uses `add_note`").
- **Tested by**: PUB-11 (3 products), PUB-12 (3), PUB-13 (2).

### 5.2 B2 (B:10): state every product first

- **Text** [DOC]: "State every late product, one sentence each, before asking for anything."
- **Interpretation**:
  - [INFERRED] The collections-team framing (rule 17) comes once. Then one sentence per product with its name, `past_due` and days late, all before any ask, including the today-ask.
  - [INFERRED] State them in `get_account` order, the order B4 uses for the loop.
- **Tested by**: PUB-11 check "all three products stated before any ask" (PTS:505).

### 5.3 B3 (B:11): band and deadline per product

- **Text** [DOC]: "The band and the deadline are per product, from that product's `days_late`. Two products of the same customer can have different deadlines."
- **Tested by**: PUB-13 (card 4 days, early → 11-02; loan 20 days, late → 10-23). Checks: "credit card recorded on 30 October (early band, inside its deadline)", "loan recorded on its own deadline, 23 October" (PTS:630-631). Also PUB-11 and PUB-12 (see the table under rule 18).

### 5.4 B4 (B:12): the combined today-ask and the per-product loop

- **Text** [DOC]: "First ask whether the customer can pay all of them today. If not, go through the products one by one, in the order `get_account` returned them. Do not ask about today again for each product. Start each product at attempt 1 of Brief A rule 30."
- **Requirement**:
  - One combined today-ask. B gives content, not a verbatim sentence; it replaces rule 28's wording.
  - On "no": loop over the products in `get_account` order. Each product opens at attempt 1: the full amount (or the floor if "too much" was already said for it) on the attempt-1 date.
  - No per-product today question.
- **Interpretation**:
  - [INFERRED] A single proposal that covers everything ("all three this Friday", PUB-11) is a proposal under rule 29. It is applied per product, using B6 if it is past a product's deadline.
  - [UNCERTAIN] A partial yes ("I can pay the card today, not the others") is not covered (U-22).
  - [INFERRED] Rule 24's ban still applies: never "how much can you pay for each?".
- **Tested by**:
  - PUB-11: "Cannot pay today. Agrees to pay all three this Friday. Confirms once." (PTS:479).
  - PUB-12: the card "tomorrow"; the loan and the car loan go through their attempts (PTS:547).
  - PUB-13: one date for both (PTS:609).

### 5.5 B5 (B:13): attempts per product

- **Text** [DOC]: "Persuasion attempts are counted per product."
- **Tested by**: PUB-12 check "two attempts on the personal loan (late band), one on the car loan (early band)" (PTS:575).

### 5.6 B6 (B:14): one date for everything, past one product's deadline

- **Text** [DOC]: "If the customer names one date for everything and it is after one product's deadline, record that product on its own deadline and say so in the read-back. The other products keep the date the customer named."
- **Interpretation**:
  - [INFERRED] Apply it per product: every product whose deadline is earlier than the named date goes on its own deadline.
  - [INFERRED] A weekend or holiday date gets rule 20 per product.
  - [INFERRED] The customer accepts at the combined read-back (B7). PUB-13: "Accepts when told the loan has an earlier latest date" (PTS:609).
  - [INFERRED] B6 replaces rule 23's offer-and-refuse flow in this situation, because the agent records the clamped date without a separate offer. Since a read-back plus a clear yes is still required, the customer can still object. Default: state the clamp before the read-back and repeat it in the read-back (U-21).
- **Tested by**: PUB-13. Card 300 on 10-30, loan 900 on 10-23 (PTS:613-624). Check "the read-back names both dates" (PTS:632).

### 5.7 B7 (B:15): one read-back, one confirmation, then one create per product

- **Text** [DOC]: "Read all promises back together and ask for one confirmation. Then call `create_promise` once per product."
- **Interpretation**:
  - [INFERRED] One combined read-back with product, amount and date for each promise, then the verbatim "Do you confirm?" once.
  - [INFERRED] Then create in `get_account` order. Each create can fail on its own (B11), with rule 37's one retry each.
  - [UNCERTAIN] The text-message sentence: once overall or once per promise (U-20).
- **Tested by**: PUB-11 checks "one read-back and one confirmation for all three" and "one create_promise per product" (PTS:506-507). PUB-13 check "the read-back names both dates" (PTS:632).

### 5.8 B8 (B:16): notes for products without a promise

- **Text** [DOC]: "The customer may promise some products and refuse others. For each product without a promise call `add_note` with that `product_id` and a reason: `refused`, `hardship`, `dispute`, `paid` or `service_error`. This also applies when no product gets a promise."
- **Interpretation**:
  - [DOC] The reason enum matches OA:252-258. `text` is optional (OA:260). The required fields are `customer_id`, `product_id` and `reason` (OA:264-268). OA:236: "Brief B: record why a product ended without a promise."
  - [PROBED-earlier] The bank rejects an unknown reason ("unknown reason", RAT:157).
  - [CODE] The scorer compares the sorted list of (product_id, reason) pairs (score.py:23-24). Order and timing are not scored, but duplicates are (N1).
  - [INFERRED] Which reason fits which situation:

| Reason | When | Source rule |
|---|---|---|
| `refused` | Attempts used up; "don't want to talk" twice | A31, A45 |
| `hardship` | Hardship and the support offer declined | A32 |
| `dispute` | Not mine, never had it, closed or paid off in the past | A40 |
| `paid` | Already paid this past-due amount | A39 |
| `service_error` | `create_promise` failed twice | A37, B11 |

  - [INFERRED] In a `not_verified` or `not_reached` B call no notes can be written, because the product ids come only from `get_account`, which is refused before verification (OA:91).
  - [UNCERTAIN] When to write the notes (U-24). B10 forces them to the end (see 5.10).
- **Tested by**: PUB-12, two `refused` notes (PTS:558-567). Check "one 'refused' note for each of the other two products" (PTS:574).

### 5.9 B9 (B:17): a dispute or "already paid" on one product

- **Text** [DOC]: "A dispute or an "already paid" claim on one product does not end the call. Note it and continue with the others."
- **Interpretation**: [INFERRED] For a `paid` product, still say rule 39's sentence (payments can take one business day to appear). For a `dispute`, still do not argue (rule 40).
- **Tested by**: none in public.

### 5.10 B10 (B:18): restructuring, and no notes on any transfer

- **Text** [DOC]: "A restructuring request still transfers the call (Brief A rule 41). Promises recorded before the request stay. Promises agreed but not yet recorded are not recorded. Close as `transferred` / `restructuring`. On any transfer (restructuring, support, human) add no notes at all, before or after it."
- **Interpretation**:
  - [INFERRED] **Design consequence: write every note only at the very end, once it is certain no transfer happens.** A note written mid-call (say, a dispute on p1) would break "no notes at all, before or after it" if p2 then leads to a transfer.
  - [INFERRED] Because of B7, promises are normally created at the end, so "promises recorded before the request" is rare. It applies when the request comes after the creates.
  - [INFERRED] "Not recorded" means the agent must not call `create_promise` for agreed-but-unconfirmed or confirmed-but-not-yet-created promises once a restructuring request arrives.
  - [INFERRED] For support and human transfers, recorded promises stay too (they cannot be undone, rule 36), and A:117 closes as `transferred`.
- **Tested by**: none in public.

### 5.11 B11 (B:19): one create fails twice

- **Text** [DOC]: "If one `create_promise` fails twice, keep the promises that were recorded and call `add_note` with reason `service_error` for the failed product."
- **Interpretation**: [INFERRED] Rule 37 still requires saying that this product's promise could not be recorded, and saying "recorded" only for the ones that returned `ok: true`. The closing follows B:23: `promise` if any were recorded.
- **Tested by**: none in public.

### 5.12 The B closing paragraph (B:21-23)

- [DOC] "The outcome table of Brief A applies. With no promise recorded: if every product is noted `paid`, close as `paid`. Otherwise close as `no_promise` with the reason of the first product, in `get_account` order, whose note is not `paid`. With several products, `promise` wins whenever at least one promise was recorded, except rule 10 above."
- [INFERRED] Combined with A:117 (not replaced by B), any transfer (restructuring, support or human) closes as `transferred` with that transfer's reason. B:23 names only "rule 10"; B:18's last sentence covers all three transfer kinds (U-5).
- Worked examples are in §6.8.

---

## 6. Outcomes, closing and precedence (A and B)

### 6.1 The outcome table, verbatim (A:108-115) [DOC]

| Outcome | Reason | When |
|---|---|---|
| `promise` | none | at least one promise was recorded |
| `paid` | none | rule 39 |
| `transferred` | `restructuring`, `human`, `support` | rules 41, 42, 32 |
| `no_promise` | `refused`, `hardship`, `dispute`, `service_error` | rules 31 and 45, 32, 40, 37 |
| `not_verified` | `failed`, `declined` | rules 14, 15 |
| `not_reached` | `callback`, `no_callback`, `wrong_number`, `deceased`, `unclear` | rules 6, 7, 8, 9, 3 |

The same table with each reason on its own line and its rule:

| Outcome / reason | Rule | Trigger |
|---|---|---|
| `promise` (no reason) | 37 (`ok:true`) | At least one promise recorded |
| `paid` (no reason) | 39 | "I already paid" this past-due amount |
| `transferred` / `restructuring` | 41 | New plan or lower instalments |
| `transferred` / `human` | 42 | Insists on a human (queue `general`) |
| `transferred` / `support` | 32 | Hardship, support offer accepted |
| `no_promise` / `refused` | 31, 45 | Attempts used up; twice "don't want to talk" after verification |
| `no_promise` / `hardship` | 32 | Hardship, support offer declined |
| `no_promise` / `dispute` | 40 | Not mine, never had it, closed or paid off in the past |
| `no_promise` / `service_error` | 37 | `create_promise` failed twice |
| `not_verified` / `failed` | 14 | 3 wrong answers in total |
| `not_verified` / `declined` | 15, (45) | 2nd decline; twice "don't want to talk" before verification |
| `not_reached` / `callback` | 6 | Valid callback booked |
| `not_reached` / `no_callback` | 7 | Two offers outside the window |
| `not_reached` / `wrong_number` | 8 | Number does not belong to the customer |
| `not_reached` / `deceased` | 9 | Customer has died |
| `not_reached` / `unclear` | 3 | No confirmation after the 2nd ask |

[INFERRED] The table's `not_verified` row lists only rules 14 and 15. Rule 45's own text also leads to `not_verified`/`declined` (A:102). The `no_promise`/`refused` row does list rule 45.

### 6.2 The sentences after the table, verbatim [DOC]

- A:117: "If a transfer follows a recorded promise, close as `transferred` with that transfer's reason."
- A:119: "Brief A never uses `add_note`."
- B:23: see §5.12.

### 6.3 What the API and the scorer add

| Fact | Label | Source |
|---|---|---|
| `outcome` is an enum of exactly the six outcomes | [DOC] | OA:422-431 |
| `reason` is a free string, "Required for every outcome except promise and paid. See the table in the brief." | [DOC] | OA:433-436 |
| `close_call` is "Always the last tool call. Nothing is accepted after it." | [DOC] | OA:411 |
| The bank rejects an unknown outcome and checks outcome/reason consistency, naming the allowed reasons in its error | [PROBED-earlier] | RAT:159 |
| After close, every tool returns "the call is already closed" | [PROBED-earlier] | RAT:159 |
| The scorer compares (outcome, reason) exactly; expected reason `null` for `promise` and `paid` | [CODE] | score.py:19-20; PTS:30, 337 |
| The last ledger call must be `close_call` | [CODE] | score.py:29 |
| Transfers are compared by queue only, as a sorted list | [CODE] | score.py:27 |
| Promises, notes and callbacks are compared as sorted lists (multisets) | [CODE] | score.py:21-26 |
| Any `verify_identity`/`get_account` call fails a case whose expected outcome is `not_reached` (or `no_contact`/`unreached`) | [CODE] | score.py:33 |
| `get_account` or `create_promise` returning "identity not verified" fails the case | [CODE] | score.py:31-32 |

### 6.4 Queue-to-reason map [DOC]

| Rule | `transfer_to_agent` queue (OA:367-373) | `close_call` reason |
|---|---|---|
| 41 | `restructuring` | `restructuring` |
| 42 | **`general`** | **`human`** |
| 32 | `support` | `support` |

### 6.5 Precedence, all in one place

| # | Situation | Winner | Source |
|---|---|---|---|
| P1 | Hardship together with a flat refusal, persuasion or a restructuring request | Hardship path (sympathy, support offer, no persuasion) | A:83 "This rule comes before rules 30 and 41" [DOC] |
| P2 | Hardship, but the customer names a date or amount | Record the promise under the date and amount rules | A:83 [DOC] |
| P3 | "Paid off / closed in the past" | Dispute, not `paid` | A:97 [DOC] |
| P4 | A transfer after a recorded promise | `transferred` with that transfer's reason | A:117 [DOC] |
| P5 | B: at least one promise recorded, no transfer | `promise` | B:23 [DOC] |
| P6 | B: any transfer | No notes at all; with restructuring, agreed-but-unrecorded promises are dropped | B:18 [DOC] |
| P7 | B: no promise, every product noted `paid` | `paid` | B:23 [DOC] |
| P8 | B: no promise otherwise | `no_promise` + reason of the first product (in `get_account` order) whose note is not `paid` | B:23 [DOC] |
| P9 | A date or amount the customer proposes | Never a refusal; handled by the date and amount rules | A:78 [DOC] |
| P10 | A date after the deadline (one product) | Offer the deadline; refusing it is a flat refusal | A:66 [DOC] |
| P11 | B: one date for all, past one product's deadline | Record that product on its deadline; say so in the read-back | B:14 [DOC] |
| P12 | A question before confirmation | Answer it; the next ask is the 2nd | A:26 [DOC] |
| P13 | A human request | Applies before and after verification | A:102 [DOC] |
| P14 | "Don't want to talk" twice | `no_promise`/`refused` after verification; `not_verified`/`declined` before | A:102 [DOC] |
| P15 | Rule 1's ban vs any pre-verification rule (3, 4, 14, 15, 42, 43, 45) | The ban holds | A:24 [INFERRED scope] |
| P16 | Explicit lower-instalment request vs "too much" | Restructuring transfer (rule 41), no floor offer first | A:98, PUB-09 [INFERRED] |
| P17 | Hardship-death ("a death in the family", rule 32) vs customer death (rule 9) | Rule 9 is a third party reporting the customer's death; rule 32 is the verified customer reporting a relative's death | A:35, A:83 [INFERRED] |
| P18 | B: the closing's derived reason vs a reason the triggering rule names (for example rule 45's `refused`) | The B closing (first non-`paid` note in `get_account` order) | B:23 [INFERRED] |

### 6.6 Outcome resolver (first matching line wins) [INFERRED, assembled from A:106-117, B:16-23 and rules 3–45]

```
# Not the customer (no verify_identity / get_account may have been called)
third party says customer died                          -> not_reached / deceased      (A9)
person says number is not the customer's                -> not_reached / wrong_number  (A8)
valid callback booked (schedule_callback ok)             -> not_reached / callback      (A6)
two callback offers both outside the window              -> not_reached / no_callback   (A7)
no confirmation after 2nd ask                            -> not_reached / unclear       (A3)

# Any transfer, at any stage (A:117, B:18, B:23)
transfer_to_agent(support)  after hardship, accepted     -> transferred / support
transfer_to_agent(restructuring) plan / lower instalments -> transferred / restructuring
transfer_to_agent(general)  insisted on a human          -> transferred / human
   B: no add_note at all; restructuring drops agreed-but-unrecorded promises

# Confirmed customer, identity not passed
3 wrong answers in total                                 -> not_verified / failed       (A14)
2nd decline (refusal or "what is it about")              -> not_verified / declined     (A15)
2nd "don't want to talk" before verification             -> not_verified / declined     (A45)

# Verified, Brief A (one product)
promise recorded (ok:true)                               -> promise   (no reason)
"already paid" (this past-due amount)                    -> paid      (no reason)
dispute (not mine / never had / closed or paid off)      -> no_promise / dispute
hardship, support declined                               -> no_promise / hardship
create_promise failed twice                              -> no_promise / service_error
attempts used up, or 2nd "don't want to talk"            -> no_promise / refused

# Verified, Brief B (1-3 products); one note per product without a promise, written at the end
>= 1 promise recorded                                    -> promise   (no reason)
no promise and every product noted paid                  -> paid      (no reason)
otherwise                                                -> no_promise / <reason of first product in get_account order whose note != paid>
```

Always: thank and say goodbye (A47), then exactly one `close_call`, last (A46). Omit `reason` for `promise` and `paid`.

### 6.7 What the ledger must show for each outcome [INFERRED from score.py:17-34 and the expected blocks]

| Outcome | promises | notes (B) | callbacks | transfers | Forbidden tool calls |
|---|---|---|---|---|---|
| `promise` | ≥1, exact (product, amount, date) | one per product without a promise | none | none (unless a later transfer → `transferred`) | – |
| `paid` | none | A: none; B: every product `paid` | none | none | – |
| `transferred` | only those recorded before the transfer | **none** | none | exactly one, with the right queue | `add_note` (B) |
| `no_promise` | none | A: none; B: every product | none | none | – |
| `not_verified` | none | none | none | none | `get_account` (fails as "identity not verified") |
| `not_reached` | none | none | one only for `callback` | none | `verify_identity`, `get_account` (score.py:33) |

### 6.8 Worked closing examples

| # | Situation | Close | Notes written (B) |
|---|---|---|---|
| E1 | A: PUB-01, 420 today, `ok:true` | `promise` | – |
| E2 | A: PUB-08, paid this morning | `paid` | – |
| E3 | A: PUB-05, job loss, declines support | `no_promise`/`hardship` | – |
| E4 | A: promise recorded, then insists on a human | `transferred`/`human` | – |
| E5 | B: PUB-12, p1 promised, p2 and p3 refused | `promise` | (p2, `refused`), (p3, `refused`) |
| E6 | B: p1 paid, p2 paid | `paid` | (p1, `paid`), (p2, `paid`) |
| E7 | B: p1 paid, p2 dispute, p3 refused | `no_promise`/`dispute` | three notes |
| E8 | B: p1 refused; p2 agreed but its create failed twice | `no_promise`/`refused` (p1 is first) | (p1, `refused`), (p2, `service_error`) |
| E9 | B: p1 dispute; p2 hardship, accepts support | `transferred`/`support` | **none**, not even p1's dispute |
| E10 | B: p1 and p2 agreed (not yet created); p3 lower instalments | `transferred`/`restructuring` | none; the agreed promises are **not** recorded |
| E11 | B: all three created; customer then asks for a new plan | `transferred`/`restructuring` | none; the three promises stay |
| E12 | B: p1 paid; then "I don't want to talk" twice | `no_promise`/`refused` (p2 is the first non-`paid`; see U-32) | (p1, `paid`), (p2, `refused`), (p3, `refused`) |
| E13 | Any brief: a relative answers, no time in the window after one re-ask | `not_reached`/`no_callback` | – |

---

## 7. The persuasion ladder (one product) [INFERRED from A:70-84, B:12-13]

This is the ladder for one product in A, or for each product in B after the combined "all today?" got a no. In B, step 1 is replaced by the combined ask, and each product enters at step 3.

1. **First ask** (after the debt statement): "Can you make this payment today?" (full amount, today).
2. **Branch on the answer:**
   - **Yes**: full amount, today → read-back (rule 34).
   - **The customer proposes a date and/or an amount** (rule 29): uses no attempt. Validate it with the date and amount rules. A valid proposal → read-back. Otherwise:
     - a weekend or holiday on or before the deadline → offer the next business day (rule 20);
     - a date after the deadline → say the latest recordable date is the deadline and offer it (rule 23);
     - a vague period → ask once for the exact day, then propose the deadline (rule 21);
     - a past date → say it has passed and ask for a day (U-14);
     - an amount below the floor → "cannot be recorded", offer the floor once (rule 27).
   - **"Too much"** → offer the floor once and say the rest stays overdue (rule 26). Default reading (U-1): this offer *is* attempt 1, on the attempt-1 date. Set `too_much = true`. Accepted → read-back. Refused → a flat refusal (rule 26): late band → step 4 (attempt 2 may name the floor again, on the deadline); early band → step 5.
   - **Restructuring request** → transfer `restructuring` (rule 41), unless hardship applies.
   - **Hardship** → rule 32. No persuasion.
   - **Paid, dispute, human, "don't want to talk", scam, unanswerable question** → rules 39, 40, 42, 45, 43, 44.
   - **A flat no or a non-answer** (including "no" to today with no date and no amount) → uses an attempt. Go to step 3.
3. **Attempt 1**: amount = the full amount, or the floor if `too_much`. Date = the last business day of this week, or of next week if today is that day.
   - Accepted → read-back.
   - A proposal → back to step 2 (no attempt used).
   - A flat refusal → early band: step 5; late band: step 4.
4. **Attempt 2** (late band only): the floor on the deadline.
   - Accepted → read-back.
   - A proposal → step 2.
   - A refusal → step 5.
5. **Attempts used up**: stop, and never repeat a refused offer (rule 31).
   - A: close `no_promise`/`refused`.
   - B: the product will get a `refused` note (written at the end; see B10), and the loop moves to the next product.

A refusal of an offer made by rule 23, 26 or 27 is "a flat refusal (rule 30)" and uses the next attempt.

**Worked examples** (public data; dates computed) [INFERRED]:

| Case | Product | Band | Deadline | Floor | Path |
|---|---|---|---|---|---|
| PUB-01 | card 420 | early (6) | 11-02 | 126 | Yes to today → 420 on 10-14 → read-back → yes → create → text-message sentence. |
| PUB-04 | car loan 1250 | late (14) | 10-23 | 400 | Proposes 6 Nov (after the deadline) → "latest date I can record is 23 October" → accepted → 1250 on 10-23. No attempt used. |
| PUB-06 | card 2125.10 | late (12) | 10-23 | 637.50 | "Too much" → floor once, "the rest stays overdue", for Fri 10-16 → accepted (PTS:243-261). |
| PUB-07 | personal loan 540 | early (5) | 11-02 | 180 | No today; "the week after next" → ask once for the exact day → "Monday the 26th" (holiday) → offer Tue 10-27 → accepted. |
| PUB-10 | card 365 | late (8) | 10-23 | 109.50 | No to today → attempt 1: 365 on Fri 10-16 → accepted → create fails once → retry → `ok:true`. |
| PUB-12 | card 510 | late (16) | 10-23 | 153 | (after the combined no) proposes "tomorrow" = 10-15, valid → agreed. |
| PUB-12 | personal loan 1320 | late (16) | 10-23 | 440 | Attempt 1: 1320 on 10-16 → refused. Attempt 2: 440 on 10-23 → refused. Note `refused`. |
| PUB-12 | car loan 140 | early (7) | 11-02 | 46 | Attempt 1: 140 on 10-16 → refused. Note `refused`. |
| PUB-13 | card 300 / loan 900 | early / late | 11-02 / 10-23 | 90 / 300 | Proposes 30 Oct for both → card keeps 10-30; loan clamped to 10-23 and said so (B6) → one read-back → yes → two creates. |

---

## 8. Every quoted string in the briefs, and its role

### 8.1 Must be said verbatim (the brief quotes the sentence and says "say" or "ask" it) [DOC]

| # | String | Source | When |
|---|---|---|---|
| V1 | "Am I speaking with {title} {last_name}?" | A:25 | Who is on the line, asks 1 and 2 |
| V2 | "I am sorry for your loss." | A:35 | A third party says the customer died |
| V3 | "Can you make this payment today?" | A:77 | First ask after the debt statement (A). In B, the content "whether the customer can pay all of them today" (B:12) replaces it |
| V4 | "Do you confirm?" | A:88 | After every read-back (B: once, for all promises) |
| V5 | "You will receive a text message confirming this promise." | A:92 | After a recorded promise (`ok:true`) |

**Product-name templates** (A:49), verbatim: "credit card ending 4821" (that is, `credit card ending {card_last4}`), "personal loan", "car loan".

[INFERRED] Each verbatim sentence must be said exactly as written. A model left to paraphrase may drift. HP §Overview's own example uses "Can you pay today?", which is not V3.

### 8.2 Content the agent must convey (the wording is free: "say that …", "tell", "explain", "ask") [DOC]

| Content | Source |
|---|---|
| Digital assistant + calling from Freya Bank + the call is recorded (first sentence) | A:24 |
| That it is Freya Bank's digital assistant (robot or AI question) | A:27 |
| When can the customer be reached (third party) | A:31 |
| Ask once for another time (callback slot outside the window) | A:33 |
| Ask the customer to say the month as a word (`day_month_swapped`) | A:42 |
| Use the mobile app or a branch (after 3 wrong answers) | A:43 |
| The questions protect their account (first decline, once) | A:44 |
| Calling from the collections team about a late payment; the product name; the past-due amount; days late | A:49 |
| Offer the next business day (weekend or holiday named) | A:63 |
| Ask once for the exact day (vague period); then propose the deadline | A:64 |
| The latest date you can record is the deadline, and offer it | A:66 |
| The rest stays overdue (with the floor offer) | A:72 |
| It cannot be recorded (an amount below the floor), and offer the floor | A:73 |
| One short sentence of sympathy; an offer to connect with the customer support team (hardship) | A:83 |
| Read back the product, the amount and the date | A:88 |
| They can change it in the mobile app (asked to change or cancel a recorded promise) | A:90 |
| The promise is recorded (only after `ok:true`); that you could not record it (after 2 failures) | A:91 |
| Payments can take one business day to appear (already paid) | A:96 |
| Ask once whether you can help first (human request) | A:99 |
| They can verify the call by phoning Freya Bank's customer service number (scam) | A:100 |
| You do not have that information (unanswerable question) | A:101 |
| Thank the customer and say goodbye | A:121 |
| B: every late product, one sentence each, before any ask | B:10 |
| B: whether the customer can pay all of them today | B:12 |
| B: in the read-back, that a product is recorded on its own deadline | B:14 |
| B: all promises read back together; one confirmation | B:15 |

### 8.3 Customer-side quoted strings (what the agent must recognise) [DOC]

| Role | Strings | Source |
|---|---|---|
| Confirms identity | "yes", "that's me", "speaking", the customer's own name | A:26 |
| Does not confirm | "Hello", "go ahead", "who is this" | A:26 |
| Vague periods | "next week", "end of the month", "when my salary comes" | A:64 |
| Weekday phrases | "Next <weekday>", "This <weekday>", "next Friday" | A:65 |
| Already paid | "I already paid" | A:96 |
| Dispute | "This debt is not mine", "I never had this product" | A:97 |
| Scam | "Is this a scam?" | A:100 |
| Hardship triggers (not quoted, described) | illness, a death in the family, job loss | A:83 |
| Restructuring triggers (described) | a new payment plan, lower instalments | A:98 |

### 8.4 Forbidden quoted string [DOC]

- "how much can you pay?" (A:70). [INFERRED] Paraphrases are forbidden too.

### 8.5 Tool and enumeration strings named in the briefs [DOC]

- `hint: "day_month_swapped"` (A:42); `ok: true` (A:91).
- Queues `support`, `restructuring`, `general` (A:83, A:98, A:99).
- Outcomes and reasons (A:108-115).
- Note reasons `refused`, `hardship`, `dispute`, `paid`, `service_error` (B:16).
- Product field names `minimum_payment`, `instalment_amount` (A:71), `past_due`, `days_late` (B:9, B:11).
- Call variables `customer_id`, `first_name`, `last_name`, `title`, `now` (A:17-20).

---

## 9. Banned words, phrases and actions

| Ban | Scope | Source |
|---|---|---|
| "collections", "debt", "payment", the product | Before identity is verified; to everyone, relatives included | A:24 [DOC] |
| Any other purpose word (owe, overdue, late, amount, balance) | Before verification and to third parties | A:31, PTS:88 [INFERRED] |
| Anything beyond the opening sentence; the reason for the call | Toward a third party | A:31 [DOC] |
| Security questions to a relative; anything about the account, even if they offer to pay | Relative | A:36 [DOC] |
| Any further question after "I am sorry for your loss." | Deceased path | A:35 [DOC] |
| `verify_identity` / `get_account` | Any call that ends `not_reached` (automatic ledger fail) | score.py:33 [CODE] |
| `get_account` before both questions pass | Always | A:48, OA:91 [DOC]; score.py:31-32 [CODE] |
| Stating the debt | After 3 wrong answers (and whenever unverified) | A:43 [DOC] |
| Sending a half or non-digit phone answer | Identity | A:40 [DOC]; RAT:151 [PROBED-earlier] |
| "how much can you pay?" (and any question that lets the customer choose the amount) | Always | A:70 [DOC] |
| Persuasion attempts | Hardship | A:83 [DOC] |
| A discount, a waiver, an instalment plan, any term not in the brief | Always | A:84 [DOC] |
| Describing a plan | Restructuring request | A:98 [DOC] |
| Arguing; taking a promise | Dispute | A:97 [DOC] |
| Taking a promise | Already paid | A:96 [DOC] |
| Inventing figures, dates, reasons (or a phone number) | Always | A:101 [DOC]; A:100 [INFERRED] |
| Saying "recorded" before `ok:true` | Always | A:91 [DOC]; README:61 [DOC] |
| More than one retry of `create_promise` per product | Always | A:91 [DOC] |
| Repeating an offer already refused | Persuasion | A:82 [DOC] |
| Naming the floor more than once outside attempt 2 | Amounts | A:72 [DOC] |
| More than one promise per product; changing or cancelling a recorded promise | Always | A:90 [DOC] |
| `create_promise` before a clear yes | Always | A:88 [DOC] |
| A promise date that is past, not a business day, or after the deadline | Always | A:62 [DOC] |
| A callback outside today/next business day, 10:00–19:00, or not later than `now` | Third party | A:32 [DOC] |
| `add_note` | Brief A | A:119 [DOC] |
| Any note on a transfer (before or after it) | Brief B | B:18 [DOC] |
| Recording agreed-but-unrecorded promises after a restructuring request | Brief B | B:18 [DOC] |
| Asking about today again for each product | Brief B | B:12 [DOC] |
| Using the real clock | Always | A:20 [DOC]; wf:240 [DOC] |
| Any tool call after `close_call`; more than one `close_call` | Always | A:106, OA:411 [DOC]; RAT:159 [PROBED-earlier] |
| A `reason` on `promise` or `paid` | Always | OA:435 [DOC]; score.py:19-20, PTS:30, 337 [CODE] |

---

## 10. Every count and limit

Values are [DOC] from the cited line unless marked [CODE].

| Item | Value | Source |
|---|---|---|
| Days late in scope | 1–45 | A:9 |
| Products | A: 1; B: 1–3 | A:9, B:9 |
| Rules | A: 47 numbered; B: 11 numbered + closing | A:24-121, B:9-23; README:42 |
| Who-is-on-the-line asks | 2 (a question answered in between makes the next ask the 2nd) | A:26 |
| Callback days | today or the next business day | A:32 |
| Callback hours | 10:00–19:00, both included, strictly later than `now` | A:32 |
| Callback time format | `HH:MM` | OA:317 |
| Callback re-asks | 1 | A:33 |
| Security questions | 2, in order: date of birth, phone last 4 | A:40 |
| Date-of-birth format sent | `YYYY-MM-DD`; numbers read day-month-year | A:40, OA:37 |
| Phone answer format | four digits | OA:37 |
| Wrong answers allowed | 3 in total across both questions | A:41, OA:17 |
| Swapped-date retry | not counted | A:42 |
| Decline explanation | once; the 2nd decline closes | A:44 |
| Holidays | 5 dates, 2026-10-26 to 2027-01-01 | A:53 |
| Early band | `days_late` 1–7; 12th business day after today; 1 attempt | A:59 |
| Late band | `days_late` 8–45; 7th business day after today; 2 attempts | A:60 |
| Exact-day re-ask for a vague period | 1 | A:64 |
| Floor offers | once (rule 26); once (rule 27); attempt 2 may name it again | A:72-73 |
| Accepted customer amount | floor ≤ x ≤ `past_due`, both included | A:73 |
| Attempt 1 date | last business day of this week (next week's if today is that day) | A:80 |
| Attempt 2 | the floor, on the deadline, late band only | A:81 |
| Sympathy | one short sentence | A:83 |
| Support offer | once (per the PUB-05 check) | PTS:214 |
| Promises per product | 1 | A:90, OA:174 |
| `create_promise` tries per product | at most 2 | A:91 |
| Already-paid lag | one business day | A:96 |
| "Can I help first?" before a human transfer | once | A:99 |
| "Don't want to talk" before closing | 2 | A:102 |
| `close_call` | exactly 1, last | A:106, OA:411 |
| B: product statements | one sentence per product, all before any ask | B:10 |
| B: today-asks | 1 in total | B:12 |
| B: read-backs and confirmations | 1 combined | B:15 |
| B: `create_promise` | once per product (plus rule 37's retry) | B:15, B:19 |
| B: notes | 1 per product without a promise; 0 on any transfer | B:16, B:18 |
| Promise amounts compared | rounded to 2 decimals | score.py:21 [CODE] |
| Final runs per customer | 3; a customer passes only if all 3 pass | README:76, HP §Evaluation |

---

## 11. Public cases: the rules each one tests

The data, expected ledgers and checks are [CODE] from `public-test-set.json`. The "Rules tested" column is [INFERRED].

| Case | Brief | Key data | Rules tested | Expected ledger | Judge checks |
|---|---|---|---|---|---|
| PUB-01 | A | Card 4821; 420; 6 days (early); floor 126; DOB 1988-03-14; phone 4471 | 1, 2, 11, 16, 17, 28, 34, 36, 38, 46, 47 | `promise`; (p1, 420.0, 2026-10-14) | PTS:43-46 |
| PUB-02 | A | Husband answers; personal loan 310.5, 11 days (never disclosed) | 1, 5, 6, 10, (3) | `not_reached`/`callback`; callback (2026-10-15, 11:00) | PTS:88-90 |
| PUB-03 | A | DOB 1992-07-21; answers 12 July 1991, 21 August 1992, 21 July 1990 | 11, 12, 14, 1 | `not_verified`/`failed` | PTS:128-130 |
| PUB-04 | A | Car loan 1250; 14 days (late; 10-23); floor 400; salary on 6 Nov; robot question | 23, 29, 4, 18 | `promise`; (p1, 1250.0, 2026-10-23) | PTS:173-175 |
| PUB-05 | A | Personal loan 780; 21 days (late); floor 260; job loss; discount; declines transfer | 32, 33 | `no_promise`/`hardship`; no transfer | PTS:212-215 |
| PUB-06 | A | Card 1903; 2125.10; 12 days (late); floor 637.50; "you tell me" | 24, 26, 30, 22 | `promise`; (p1, 637.5, 2026-10-16) | PTS:259-261 |
| PUB-07 | A | Personal loan 540; 5 days (early; 11-02); floor 180 | 21, 20, 19, 29 | `promise`; (p1, 540.0, 2026-10-27) | PTS:304-306 |
| PUB-08 | A | Card 5512; 180; 5 days; paid in the app this morning | 39 | `paid`, reason null | PTS:344-345 |
| PUB-09 | A | Personal loan 2100; 28 days; floor 700; lower instalments | 41, 33 | `transferred`/`restructuring`; transfers [restructuring] | PTS:386-388 |
| PUB-10 | A | Card 7740; 365; 8 days (late); floor 109.5; `create_promise` fails once | 30, 37, 38 | `promise`; (p1, 365.0, 2026-10-16) | PTS:432-433 |
| PUB-11 | B | Card 2288 (220, 9 days, late); personal loan 640 (9, late); car loan 75 (3, early); phone 2288 | B2, B4, B7, 22 | `promise`; p1, p2, p3 at full amounts, all on 2026-10-16 | PTS:505-507 |
| PUB-12 | B | Card 9015 (510, 16, late); personal loan 1320 (16, late, floor 440); car loan 140 (7, early, floor 46); phone 4401 then 4410 | 12, B4, B5, B8, 30, 31 | `promise`; (p1, 510.0, 2026-10-15); notes (p2, refused), (p3, refused) | PTS:572-575 |
| PUB-13 | B | Card 6604 (300, 4 days, early: 11-02); personal loan 900 (20, late: 10-23); phone 6604 | B3, B6, B7, 19 | `promise`; (p1, 300.0, 2026-10-30), (p2, 900.0, 2026-10-23) | PTS:630-632 |

Notes on the cases:

- [CODE] In PUB-11 and PUB-13 the phone's last four digits equal the card's last four (2288 at PTS:456/461; 6604 at PTS:592/597). [INFERRED] This is harmless, but a model may confuse the two.
- [CODE] The judge's success criteria are exactly the case's `checks` list (run_cases.py:47). [DOC] Hidden cases have their own checks, judged "against the case's checks" (HP §Evaluation).
- [DOC] Ten cases use Brief A and three use B (HP §Data). `run_cases.py --brief A` runs the ten A cases (run_cases.py:52).
- [CODE] Rules with **no** public case: 3 (unclear), 7, 8, 9, 13, 15, 27, 35, 40, 42, 43, 44, 45, B9, B10, B11. The hidden set has 30 customers per brief (HP §Evaluation), so these rules are likely to be exercised there [INFERRED].
- [CODE] Branches of rules that **are** partly tested, but that no public script or `faults` entry reaches (checked against all 13 scripts, PTS:27, 73, 118, 157, 202, 243, 288, 334, 372, 416, 479, 547, 609, and the only `faults` entry, PTS:435-440):

| Rule | Branch no public case reaches | Brief text | What the public cases do instead |
|---|---|---|---|
| A:117 | A transfer after a recorded promise → `transferred` with that transfer's reason | "If a transfer follows a recorded promise, close as `transferred` with that transfer's reason." (A:117) | The only transfer (PUB-09) has no promise (PTS:374-383) |
| B closing | No promise recorded and every product noted `paid` → `paid` | "if every product is noted `paid`, close as `paid`" (B:23) | All three B cases (PUB-11, 12, 13) record a promise and close `promise` (PTS:481, 549, 611) |
| B closing | No promise recorded → `no_promise` with the reason of the first product, in `get_account` order, whose note is not `paid` | "Otherwise close as `no_promise` with the reason of the first product, in `get_account` order, whose note is not `paid`." (B:23) | Same as above |
| 36 | The customer asks to change or cancel a recorded promise → say they can change it in the mobile app | "If the customer asks, say they can change it in the mobile app." (A:90) | No script asks to change a promise after it is recorded |
| 21 | Still no exact day after the one ask → propose the deadline | "If they still give none, propose the deadline." (A:83) | PUB-07 gives an exact day ("Monday the 26th") when asked (PTS:288) |
| 23 | The customer refuses the deadline → flat refusal (rule 30) | "If the customer refuses the deadline, treat it as a flat refusal (rule 30)." (A:66) | PUB-04 accepts the deadline (PTS:157) |
| 20 | A **weekend** day on or before the deadline → next business day | "If the customer names a weekend day or a holiday that is not after the deadline, offer the next business day." (A:63) | PUB-07 names a holiday (Mon 2026-10-26, A:53). Every other named date is a weekday: 10-15 Thu, 10-16 Fri, 10-30 Fri, 11-06 Fri [INFERRED from the calendar] |
| 22 | "Next <weekday>" = that weekday in the following calendar week | "'Next <weekday>' means that weekday in the following calendar week." (A:65) | Only "this Friday" appears (PUB-06, 10, 11; PTS:243, 416, 479) |
| 37 | The second `create_promise` failure → say it could not be recorded, close `no_promise` / `service_error` | "If it fails again, say you could not record it and close as `no_promise` / `service_error`." (A:91) | PUB-10 fails once only (`fail_first_n: 1`, PTS:438) |
| 32 | The customer accepts the support offer → `transfer_to_agent` queue `support`, close `transferred` / `support` | "If they accept, call `transfer_to_agent` with queue `support` and close as `transferred` / `support`." (A:83) | PUB-05 declines the transfer → `no_promise`/`hardship` (PTS:202-209) |

- [INFERRED] These branches matter as much as the untested rules above: the hidden set has "30 customers per brief, 1–3 products, several calendar days" (HP §Evaluation). Most branches above change the ledger or the closing outcome (A:117, B closing, 21, 23, 20, 22, 37, 32). Rule 36's branch changes only what is said, so only the judge would catch it.

---

## 12. The deterministic computations the briefs require (code, not model judgement) [INFERRED]

1. **Time base** (A:20): parse `now` (`YYYY-MM-DDTHH:MM`) into today's date, the time and the weekday.
2. **Business-day calendar** (A:53):
   - `is_business_day(d)` = Monday–Friday and not a holiday;
   - `next_business_day(d)` = the first business day strictly after `d`;
   - `nth_business_day_after(today, n)` = count n business days starting tomorrow; today is excluded.
3. **Band and deadline per product** (A:57-60, B:11): from `days_late`, the band, the deadline and the number of attempts.
4. **Attempt dates** (A:80-81):
   - `last_business_day_of_week(d)`: Monday–Sunday week, holidays skipped;
   - `attempt1_date(today)`: this week's, or next week's if today is that day (and, by default, next week's if this week's is already past, U-13);
   - `attempt2 = (floor, deadline)`.
5. **Date expression resolution** (A:63-66):
   - "this"/"next" weekday (A:65), "today", "tomorrow";
   - ordinal days ("Monday the 26th", "30 October", "the twenty-second of October");
   - classifying a phrase as vague (A:64);
   - validation: today ≤ d ≤ deadline and d is a business day (A:62). Otherwise shift to the next business day (A:63) or clamp to the deadline (A:66; B:14 per product).
6. **Amounts** (A:70-73):
   - `floor(product)` by type;
   - validation floor ≤ x ≤ `past_due`;
   - parsing amounts said in words (`in_words`, run_cases.py:32);
   - rounding to 2 decimals (score.py:21);
   - formatting money for speech.
7. **Identity normalisation** (A:40-42):
   - date of birth → `YYYY-MM-DD`, day-month-year for numbers, joining halves;
   - phone → exactly 4 digits from digits or words, keeping leading zeros;
   - send only complete answers;
   - the swapped-hint branch.
8. **Callback validation** (A:32-33): date ∈ {today, next business day}; 10:00 ≤ t ≤ 19:00; (date, t) > `now`; output `HH:MM`.
9. **Counters and flags**:
   - confirmation asks (≤2);
   - wrong answers (read from `wrong_answers_left`);
   - declines (≤2) and the explanation given (≤1);
   - "don't want to talk" (≤2);
   - "can I help first" asked (≤1);
   - callback re-ask (≤1);
   - exact-day asked (≤1);
   - deadline offered;
   - `too_much`;
   - floor offered (≤1 outside attempt 2);
   - attempts used per product;
   - `create_promise` tries per product (≤2);
   - sympathy said (≤1);
   - support offered (≤1).
10. **Product data**: ids only from `get_account` (README:102), the product-name map (A:49), per-product deadlines, and the B6 clamp.
11. **Closing resolver** (§6.6): the B notes plan is computed at the end and is empty on any transfer. Omit `reason` for `promise` and `paid`. Exactly one final `close_call`.
12. **Tool-order guards**:
    - no `verify_identity` before a confirmation;
    - no `get_account` before `all_verified`;
    - no `create_promise` before a clear yes, and at most 2 per product;
    - no `add_note` in A;
    - no notes on any transfer in B;
    - `close_call` last.

---

## 13. Uncertainties and contradictions

### 13.1 What experiments can and cannot settle

No experiment was run for this chapter. The "Settle" lines below name normal kit usage only:

- `python3 tools/run_cases.py <agent_id> [--only ID] [--reps N] [--style S] [--cases file.json] [--out f.json]` (run_cases.py:3, 50);
- reading a transcript with `freya.get_call(call_id)["messages"]` (README:99).

Two limits apply to every such experiment:

- The practice bank serves only PUB-01..13 (HP §FAQ). A custom `--cases` file must reuse a PUB id. Its persona `script` can change, but the session's identity and products stay fixed.
- The local scorer uses **our** `expected` block, and the judge uses **our** `checks`. A custom case can show **mechanics** (what the API returns, what the agent does). It **cannot** show the organisers' intended interpretation. Pure interpretation questions are marked "interpretation only", with a careful default.

### 13.2 The list

| ID | Unknown | Sources | Careful default | Settle |
|---|---|---|---|---|
| U-1 | How many times the floor is named. Rule 26 says "offer the floor, once" and only attempt 2 "may name the floor again", yet attempt 1 is "for the floor if the customer already said the full amount is too much". The date of rule 26's offer is unstated. Also unstated: what happens when "too much" comes only after attempt 1 (the full amount on the attempt-1 date) was proposed. | A:72, A:79 | (a) The single floor offer *is* attempt 1, made on the attempt-1 date ("637.50 by Friday 16 October; the rest stays overdue"). PUB-06 expects 637.5 on 10-16 with "minimum payment offered once" (PTS:247-260). Reading (b), the floor for today then the floor again at attempt 1, would name it twice. "Too much" after attempt 1: offer the floor once on the same date; a refusal is a flat refusal, so attempt 2 (late band) or stop (early band). | Two agent variants, `--only PUB-06 --reps 3`; compare judge reasons on PTS:260 |
| U-2 | Borderline confirmations: "yeah", "yep", "mm-hm", a first name alone, a surname alone. | A:26 | Accept clear affirmatives and either name; treat greetings and questions as non-confirmation. | Mechanics only (custom PUB-01 script) |
| U-3 | A customer question after the 2nd ask (there is no 3rd ask). | A:26 | Answer it; accept only an immediate clear confirmation in that same reply; otherwise close `unclear`. | Interpretation only |
| U-4 | Rule 15 vs the `asks_back` style ("why do you need that?" asked twice before answering) while "The facts stay the same". | A:44; run_cases.py:31; README:78 | Count a decline only on an explicit refusal, or on a question with no answer after the protective explanation. Answer the question, re-ask, and do not close while the customer still engages. | `--style asks_back --reps 3`, strict vs lenient variants |
| U-5 | B closing: is every transfer an exception to "`promise` wins", or only restructuring ("except rule 10")? | B:18, B:23, A:117 | Any transfer → `transferred` with its reason (A:117 is not replaced; B:18 names all three transfer kinds). | Interpretation only |
| U-6 | The form of a `create_promise` failure (`ok:false` at HTTP 200, or HTTP 500), and whether platform retries would hide it. | A:91; OA:208, OA:229; RAT:144 [PROBED-earlier] | Treat both as failure; `maxRetries: 0` on writes (tac:365). | `--only PUB-10 --out …`, read the tool results |
| U-7 | Whether `wrong_answers_left` drops on a `day_month_swapped` answer. The ledger has a separate `hinted` field (RAT:136) [PROBED-earlier]. | A:42; OA:66 | Follow the brief: do not count it; trust the API counter for real wrong answers. | Custom PUB-11 script (DOB 1987-06-03) said month-first in numbers |
| U-8 | Date-of-birth edge formats: two-digit years, missing year, numbers impossible as day-month-year ("03/14/1988"). | A:40; OA:37 | Ask for the full date; never send an impossible date (sending one is harmless, `ok:false` and not counted, but wastes a turn). | Custom PUB-01 script |
| U-9 | A malformed `phone_last4`. **Partly settled**: a word answer ("two two eight eight") was counted wrong (RAT:151) [PROBED-earlier]. 3 or 5 digits: unknown. | A:40; OA:37 | Send exactly 4 digits, converted from words; otherwise ask again. | `--only PUB-12 --style pieces --reps 3` |
| U-10 | A callback "today" when today is not a business day. | A:32 | Literal: allowed if later than `now` and within 10:00–19:00. | Interpretation only (all practice cases are on a Wednesday) |
| U-11 | A callback with no hour ("tomorrow morning"), "I don't know", or `schedule_callback` returning `ok:false`. | A:32-33 | Ask once for a specific time and treat the answer like an offer under rule 7; no time at all → `no_callback`; one retry on a failed tool call (not stated). | Mechanics only (custom PUB-02 script) |
| U-12 | The week definition (Mon–Sun or Sun–Sat), a bare weekday ("on Friday"), a day number without a month ("the 30th"). | A:65, A:80 | Mon–Sun; a bare weekday = the nearest one on or after today; a day number = its next occurrence on or after today. | Interpretation only |
| U-13 | A weekend or holiday `now`: "the last business day of this week" may be in the past, and "If today is that day" does not fire. | A:80; README:76 | Use the last business day of next week. | Not testable with practice cases |
| U-14 | A past date ("this Monday" on a Wednesday); refusal of a rule-20 next-business-day offer; refusal of a rule-21 deadline proposal. | A:62-64 | Past date: say it has passed and ask for a day (not a refusal). Refused rule 20/21 offer: a flat refusal by analogy with A:66, A:72-73. | Interpretation only |
| U-15 | Whether "I can only discuss this with Ms Costa" breaks "Say nothing beyond the opening sentence". | A:31; PTS:88 | Avoid it; repeat only the opening and ask when the customer can be reached. | `--only PUB-02 --reps 3` with and without |
| U-16 | A third party asking for a human; a phone handover. | A:36, A:99, A:102 | Third-party human request: no transfer, ask when the customer can be reached. Handover: restart at rule 2. | Interpretation only |
| U-17 | An amount above `past_due`; whether rule 27's "offer the floor once" is a separate allowance from rule 26's; a floor offer during hardship. | A:72-73, A:83; RAT:156 [PROBED-earlier] (bank accepts any amount) | Above full: offer to record the full past-due amount. Name the floor at most once outside attempt 2. During hardship, record only what the customer names if valid; below the floor say it cannot be recorded and do not push. | Interpretation only |
| U-18 | Hardship mentioned before verification (rule 32 sits after the debt statement). | A:83 | One sympathy sentence, continue the identity check; the support offer and outcome logic apply once verified. | Interpretation only |
| U-19 | Hardship in Brief B: does a declined support offer end the call with every product noted `hardship`, or does the call continue (which would seem to break "make no persuasion attempt")? | A:83; B:16-17 | No persuasion on any remaining product; a `hardship` note on each product without a promise; close `no_promise` with the B closing reason (`hardship` unless an earlier product's note says otherwise), or `promise` if one exists. | Interpretation only |
| U-20 | The text-message sentence in B: once overall, or once per promise ("this promise" is singular). | A:92; B:15 | Once, after all creates succeed. If some failed, say it for the recorded ones and say which product could not be recorded. | Weak: PUB-11 checks do not mention it |
| U-21 | Does B6 replace rule 23's offer-and-refuse flow? | A:66; B:14 | State the clamp before the read-back and repeat it in the read-back; a rejection at the confirmation is a change (rule 35), then rule 23's flat refusal. | `--only PUB-13 --reps 3`, judge reasons on PTS:632 |
| U-22 | B: some products today, others not. | B:12 | Record the ones for today as promises for today; loop over the rest from attempt 1. | Interpretation only |
| U-23 | `days_late` outside 1–45; titles other than Mr/Ms. | A:9, A:19, A:57-60 | Use the nearest band and log a warning in the builder; use the title as given. | Interpretation only |
| U-24 | When B notes are written (the ledger compares lists, not timing). | B:16-18; score.py:23-24 | At the end, just before `close_call`, and never on a transfer (forced by B:18's "before or after it"). | `--only PUB-12 --reps 3` |
| U-25 | The currency word when speaking amounts. | none in A/B; HP §Overview says "420 dollars" | Say "dollars", or no unit. Never another currency. | Weak; judge reasons |
| U-26 | Whether `reason: ""` or `reason: "paid"` on `promise`/`paid` is stored and fails the exact match. The bank checks outcome/reason consistency (RAT:159) [PROBED-earlier]. | A:106; OA:435; score.py:19-20 | Omit the field (as base-agent:395 does). | A normal `--only PUB-08` run with the field omitted |
| U-27 | A person who never confirmed being the customer but says twice "I don't want to talk": `unclear` or `declined`? | A:26, A:102 | `unclear` if never confirmed; `declined` if confirmed (see N4). | Interpretation only |
| U-28 | Early-band deadline counting: no public case separates 11-02 (today excluded) from 10-30 (today included). | A:59 | Exclude today, per "after today" and the late-band evidence (PTS:165, 622). | Interpretation only |
| U-29 | A weekend or holiday `now` makes "today" an invalid promise date (rule 19), yet rule 28 asks "Can you make this payment today?". | A:62, A:77 | Still say V3 verbatim; if the customer says yes, offer the next business day (by analogy with rule 20) and do not count it as a refusal. | Interpretation only |
| U-30 | A customer amount with no date ("I can pay 200"), or a date with no amount. | A:73, A:78 | Date without amount: the amount on the table (full, or floor if `too_much`). Amount without date: ask once which day; that asks for a day, not an amount, so rule 24 is not broken. | Interpretation only |
| U-31 | Hardship plus a restructuring request when the support offer is declined. | A:83, A:98 | Rule 32 "comes before" rule 41: close `no_promise`/`hardship`, no restructuring transfer. | Interpretation only |
| U-32 | B: the note reason for products never discussed because the call ended early (twice "don't want to talk", hardship). | A:102, A:83, B:16 | `refused` after rule 45; `hardship` after rule 32 declined. | Interpretation only |
| U-33 | Before verification, whether a "don't want to answer" (rule 15) and a "don't want to talk" (rule 45) add to one counter. Both lead to `not_verified`/`declined`. | A:44, A:102 | One counter: two declines of any kind close the call. | Interpretation only |

---

## 14. Generalised schema: what any brief of this kind specifies

### 14.1 What the organisers say will change and what will stay

| Statement (verbatim or close) | Source | Label |
|---|---|---|
| "Brief = the bank's specification (who to ask for, identity check, allowed payment dates, how to close)." | HP §Overview | [DOC] |
| "Same kind of call, different rules: other identity questions, other limits and deadlines, another outcome table, another calendar. The seven tool names stay the same; their fields and allowed values can change." | HP §Overview | [DOC] |
| "They are the same kind of call with different rules: other numbers and limits, other identity questions, another outcome table, another calendar. Their form can differ too: one final brief is a clean specification, the other is raw bank material (a mail, a policy extract, a memo that changes it, a code list)." | README:71 | [DOC] |
| "Each final brief comes with its own tool API file. The seven tool names stay the same. The fields and the allowed values can change." | README:72 | [DOC] |
| "Fixing a crash on a table your parser did not expect is allowed. Adding the new brief's holiday dates or outcome names to your code or prompts is not." | README:73; HP §Overview | [DOC] |
| "Final customers can have up to three products, as in Brief B." | README:77 | [DOC] |
| "Final customers talk like people. They give a number in two parts, correct themselves, talk about other things, ask a question back, or say amounts and dates in words. The facts stay the same." | README:78 | [DOC] |
| "So build something that reads a brief, not something that knows this one. Whatever your builder can take from the brief, it should take from the brief." | README:80 | [DOC] |
| "Calls are in English. The phone agent gets the date/time of the call as variable `now`; every date rule uses it." | HP §Overview | [DOC] |
| Examples of brief rules: "never mention the debt before the identity check, never accept a promise on a holiday, say nothing to a relative". | HP §Overview | [DOC] |
| "calculations such as business days can run as code instead of being left to the model." | HP §Overview | [DOC] |
| Final: 2 hidden briefs, 30 customers each, 1–3 products, several calendar days, 3 repetitions per case. | HP §Evaluation | [DOC] |
| "The raw-material brief is ONE Markdown file with its own tool API file next to it." "Hidden briefs have no practice cases, only the tool API file." | HP §FAQ | [DOC] |

### 14.2 Signals in the kit code about hidden briefs [CODE]

| Signal | Source | What it suggests [INFERRED] |
|---|---|---|
| Persona text exists for identity fields `postcode`, `birth_year`, `company_number`, `founded_year`, besides `date_of_birth` and `phone_last4`; any other field falls back to "Your <field> is X" | run_cases.py:41-44 | Hidden identity questions may use these fields. `company_number` and `founded_year` point to business (company) customers. |
| `exp["outcome"] in ("not_reached", "no_contact", "unreached")` | score.py:33 | The not-reached outcome may be renamed in a hidden outcome table. [PROBED-earlier] The practice bank rejects `no_contact` (RAT:159), so a renamed outcome would come with its own tool API enum. |
| `n.get("product_id")` for notes | score.py:23 | A hidden brief may use notes without a product id. |
| `case.get("third_party")` | run_cases.py:38 | Third-party callers can occur outside the "Third party" family. |
| `case.get("style")` | run_cases.py:45 | A speaking style can be set per case. |
| Transfers compared by `queue` only | score.py:27 | The queue enum matters in the ledger; the close reason is checked separately. |

### 14.3 The schema, component by component

**P** = parametric: the values change between briefs. **S** = structural: the slot or the mechanism is expected to stay. A component can be S in shape and P in values.

| # | Component | What A/B specify | P/S | Evidence | What a builder must extract |
|---|---|---|---|---|---|
| G1 | Document form and layering | A: one clean spec. B: a delta ("Every rule of Brief A applies unless a rule below replaces it", B:5) | **S** (base + amendments exist); **P** (form: spec, mail, policy extract, memo, code list) | README:71; HP §Evaluation; B:5 | The effective rule set after applying every amendment, with the replaced rules removed |
| G2 | Bank and agent identity | "Freya Bank", "digital assistant", call recorded | **P** values [INFERRED]; **S** presence of an opening rule [INFERRED] | A:24 | Bank name, self-description, required disclosures |
| G3 | Call variables | `customer_id`, `first_name`, `last_name`, `title`, `now` | **S** for `now` and `customer_id`; **P** for the name fields (a company name is possible [INFERRED from run_cases.py:43]) | HP §Overview; OA required fields; A:17-20 | The variable list, how to address the person, the `now` format |
| G4 | Opening sentence | 3 required facts; free wording | **P** content | A:24 | Required facts or a verbatim sentence |
| G5 | Pre-verification disclosure ban | 3 words + the product; applies to everyone | **P** list; **S** existence (HP's example "never mention the debt before the identity check") | A:24; HP §Overview | The banned word list and its scope (before what event, toward whom) |
| G6 | Reach confirmation | Question template; confirm/non-confirm lists; 2 asks; questions consume an ask; outcome `not_reached`/`unclear` | **P** | A:25-27 | Template, accepted and rejected replies, ask limit, outcome code |
| G7 | Third-party handling | No reason given; ask when reachable; callback window (today or next business day, 10:00–19:00 inclusive, > `now`); 1 re-ask; wrong number; deceased sentence; relative restrictions | **P** values; **S** that third parties occur ("say nothing to a relative") | A:29-36; HP §Overview | Allowed disclosure, window (days, hours, inclusivity, strictness), re-ask count, outcome codes, verbatim sentences |
| G8 | Identity check | 2 questions in order (DOB, phone last 4); formats (`YYYY-MM-DD`; day-month-year for numbers; 4 digits); 3 wrong in total; swapped-date hint not counted; failure message (app or branch); decline handling (explain once; 2nd closes; "what is it about" = decline) | **P** ("other identity questions"; the `field` enum is in the tool file) | A:38-44; README:71; OA:28-37 | Question list and order, field names, normalisation rules, wrong-answer budget (total or per question), hints and their handling, failure and decline outcomes |
| G9 | Account gate | `get_account` only after both questions pass | **S** [INFERRED]: the tool names stay; the number of questions may change | A:48; OA:91 | The verification condition that unlocks the account |
| G10 | Product model | Types `credit_card`, `personal_loan`, `car_loan`; `card_last4`; floor fields by type; naming templates | **P** (enums and fields in the tool file can change) | OA:129-156; A:49, A:71 | Product types, per-type fields, naming templates, floor field per type |
| G11 | Debt statement | Collections team, late payment, product, past due, days late; B: one sentence per product before any ask | **P** content | A:49; B:10 | The required items and their order |
| G12 | Calendar | Mon–Fri minus 5 holidays | **P** ("another calendar"; "holiday dates") | A:53; README:71, 73 | The working-day definition and the holiday list (possibly other years, possibly other weekend days [INFERRED possible]) |
| G13 | Bands, deadlines, attempts | 1–7: 12th business day, 1 attempt; 8–45: 7th business day, 2 attempts; "after today" | **P** ("other limits and deadlines") | A:55-60 | The band ranges, the deadline formula (unit, n, whether today counts), attempts per band |
| G14 | Promise-date rules | Today or later, business day, ≤ deadline; weekend/holiday → next business day; vague → ask once then deadline; this/next weekday; after deadline → offer the deadline (refusal = flat) | **P** details; **S** kind [INFERRED] ("never accept a promise on a holiday") | A:62-66; HP §Overview | Each validity condition and each correction behaviour |
| G15 | Amount policy | Full first; never "how much can you pay?"; floor; "too much" → floor once + "rest stays overdue"; accept [floor, full]; below floor → "cannot be recorded" + floor once | **P** | A:70-73 | Opening amount, banned questions, floor definition, accepted range, offers and their counts |
| G16 | The first ask | "Can you make this payment today?"; B: combined | **P** string | A:77; B:12 | The verbatim first ask and the multi-product variant |
| G17 | Refusal definition and persuasion ladder | Flat refusal/non-answer uses an attempt; "no to today" with no date or amount is flat; proposals never are; attempt 1 = full (or floor) on the last business day of the week; attempt 2 (late) = floor on the deadline; stop, never repeat | **P** | A:78-82 | What counts as a refusal, each attempt's (amount, date) formula, attempts per band, stop rule |
| G18 | Hardship | Illness, a death in the family, job loss; one sympathy sentence; no persuasion; offer support; accept → transfer `support`; decline → `hardship`; precedence over 30 and 41; volunteered terms recorded | **P** | A:83 | Triggers, required sentences, queue, outcomes, explicit precedence |
| G19 | Forbidden offers | Discount, waiver, instalment plan, anything not in the brief | **P** list | A:84 | The forbidden list |
| G20 | Confirmation and recording | Read back product, amount, date; "Do you confirm?"; change → re-check; one promise per product; no change or cancel (→ mobile app); "recorded" only after `ok:true`; 1 retry; failure → `service_error`; verbatim text-message sentence | **P** strings and counts; **S** honesty (README:61 is a scoring dimension) | A:86-92; README:61 | Read-back items, verbatim strings, retry count, failure outcome |
| G21 | Special customer statements | Paid (one business day lag); dispute (incl. closed or paid off in the past); restructuring; human (ask once, queue `general`); scam (customer service number); unknown info; not wanting to talk (twice) | **P** | A:94-102 | Each trigger, response content, tool call and outcome, and its stage scope (before or after verification) |
| G22 | Transfer queues | `restructuring`, `general`, `support` → reasons `restructuring`, `human`, `support` | **P** (queue enum in the tool file) | OA:367-373; A:83, 98-99 | Queue per trigger and the close reason per queue (they can differ) |
| G23 | Notes policy | A: never. B: one per product without a promise; reasons `refused`/`hardship`/`dispute`/`paid`/`service_error`; none on any transfer | **P** (enum; product id possibly optional) | A:119; B:16-18; OA:234-268; score.py:23 | When notes are used, the reason per situation, timing constraints |
| G24 | Multi-product policy | State all first; per-product bands, deadlines, attempts; one today-ask; `get_account` order; B6 clamp; one read-back; create per product; dispute/paid continue; transfers drop notes; closing aggregation | **S** that 1–3 products occur (README:77); **P** the rules | B:9-23 | Each per-product vs per-call rule and the aggregation rule for the closing |
| G25 | Outcome table | 6 outcomes, 14 reason codes, rule references; no reason for `promise` and `paid`; transfer after a promise → `transferred` | **P** ("another outcome table"); the outcome enum is in the tool file; `reason` is a free string (OA:433-436), so the reason list can come **only** from the brief | A:106-117; README:71; OA:422-436 | Outcome codes, reason codes per outcome, the triggering rule of each, reason-less outcomes, cross-outcome precedence |
| G26 | Closing protocol | Thank and goodbye; exactly one `close_call`, last | **S** (OA:411; score.py:29 is generic) | A:106, A:121 | Any required closing sentences |
| G27 | Verbatim sentences | 5 sentences + 3 templates | **S** pattern (a quoted sentence introduced by "say this sentence" or "ask"); **P** content | A:25, 35, 49, 77, 88, 92 | Every quoted must-say string, kept exactly, separate from "say that …" content |
| G28 | Tool API | 7 tools; their fields, enums, formats | **S** names; **P** fields and allowed values | README:72; OA | Every field, enum and format from the brief's own tool file |
| G29 | Explicit precedence statements | "This rule comes before rules 30 and 41"; "Rule 42 applies before and after verification"; "Rule 39 covers only …" | **S** pattern; **P** content | A:83, 97, 102 | Each precedence and scope statement as an ordering constraint |

### 14.4 Where an A/B-shaped builder would break on a different brief [INFERRED]

- **Deadline formula**: a different n, calendar days instead of business days, or "including today". The "after today" reading must be taken from the text, not assumed.
- **Attempt-1 date past the deadline**: harmless under A's numbers (attempt 1 is at most 5 business days out, the shortest deadline is 7). A brief with a 3rd-business-day deadline would make "the last business day of this week" invalid at times. That clash would have to be resolved from that brief's text.
- **Queue ≠ reason**: `general` → `human` here. Another brief can pair them differently.
- **Reason-less outcomes**: here `promise` and `paid`. Another table can differ, and `reason` is a free string in the API.
- **Renamed outcomes**: for example a not-reached outcome named `no_contact` or `unreached` (score.py:33).
- **Identity fields**: a postcode (letters, spaces, case), a birth year (4 digits), a company number, a founding year (run_cases.py:41-43). Each needs its own normalisation and its own "read as" rule.
- **Notes without a product** (score.py:23).
- **Another calendar**: other holidays, another year, possibly other weekend days.
- **Raw material**: rules scattered over a mail, a policy extract, a memo that **changes** earlier text, and a code list (outcome or reason codes). The effective rule is the amended one.
- **Verbatim strings**: different sentences, possibly more of them; they must be found as quoted must-say strings, not paraphrased.

---

## 15. Traps to remember

Each trap restates a fact from the body; its label is the one given there. Traps 5, 7, 28, 34 and 38 rely partly on [PROBED-earlier] facts (RAT lines). Traps 3, 24 and 28 rely on [CODE] (score.py).

1. **The opening must say the call is recorded.** The kit's example agent leaves it out (A:24 vs base-agent:105).
2. **"Payment" is banned before verification**, yet the verbatim first ask "Can you make this payment today?" contains it. It is said only after verification (A:24, A:77). "Account" is not banned (A:44).
3. **No identity tool on a not-reached call.** Any `verify_identity` or `get_account` call fails a `not_reached` case automatically (score.py:33). Confirm the person first.
4. **A relative gets nothing**: no reason for the call, no security questions, no account facts, even if they offer to pay (A:31, A:36; PUB-02).
5. **The callback time is `HH:MM`, strictly later than `now`, 10:00–19:00 inclusive, today or the next business day.** "11am" is rejected (RAT:158) and the scorer matches the exact string (score.py:25-26).
6. **"I am sorry for your loss." and then no more questions** (A:35). This is a third party reporting the customer's death, not rule 32's hardship.
7. **Send dates of birth as `YYYY-MM-DD`, reading numbers day-month-year. Send phone answers as exactly 4 digits.** A phone answer in words was counted as wrong (RAT:151); a half answer wastes one of the 3.
8. **3 wrong answers in total, across both questions.** Re-ask only the failed question. A `day_month_swapped` retry does not count (A:41-42).
9. **"What is this about?" instead of an answer is a decline.** Two declines close `not_verified`/`declined` (A:44). Mind the `asks_back` tension (U-4).
10. **Never state the debt after a failed check**, even when asked "how much do I owe?". Point to the app or a branch (A:43; PUB-03).
11. **Deadlines count business days after today.** Counting today gives 10-22 instead of 10-23 (late) and 10-30 instead of 11-02 (early) (A:59-60; PTS:165).
12. **10-26 is a holiday.** "Monday the 26th" → offer Tue 10-27 (A:53; PUB-07). With `now` on Fri 10-23, the "next business day" for a callback is Tue 10-27, not Mon 10-26, and "tomorrow" (a Saturday) is outside the callback window (A:32).
13. **"Salary on 6 November" is an exact date** → rule 23 (offer the deadline), not rule 21's vague path (PTS:157).
14. **A date or amount the customer proposes is never a refusal**, so it uses no attempt (A:78; PTS:173).
15. **Never ask "how much can you pay?"** or any paraphrase. "You tell me" gets the floor, proposed by the agent (A:70; PUB-06).
16. **The floor is named once** (with "the rest stays overdue"); only attempt 2 may name it again, on the deadline (A:72; PTS:260).
17. **The early band gets 1 attempt, the late band 2.** In B, attempts are counted per product (A:59-60; B:13; PTS:575).
18. **Attempt 1 is the last business day of this week** (next week's if today is that day; skip holidays). On the public date it is Fri 10-16 (A:80).
19. **Never repeat a refused offer**, and stop when the attempts are used up (A:82).
20. **Hardship comes before persuasion and before restructuring.** One sympathy sentence, the support offer once, no floor push. A discount request is not restructuring and must never be offered (A:83-84; PUB-05).
21. **"Lower instalments" or "a new plan" → transfer `restructuring` without describing a plan** (A:98; PUB-09).
22. **Queue `general` maps to reason `human`** (A:99, A:112). The queue and reason names differ.
23. **"I paid it off last year" is a dispute; "I paid this morning" is `paid`** (A:96-97).
24. **`paid` and `promise` carry no reason.** Omit the field (OA:435; PTS:30, 337; base-agent:395).
25. **"Do you confirm?" and a clear yes before `create_promise`.** The read-back names the product too (A:88). HP's example omits the product; the brief requires it.
26. **Say "recorded" only after `ok: true`. Retry exactly once.** Two failures → say so and close `service_error`, or in B write a `service_error` note (A:91; B:19; PUB-10). Keep platform retries off write tools (tac:365).
27. **The text-message sentence is verbatim and comes after a recorded promise** (A:92; PTS:46).
28. **One promise per product; it cannot be changed in the call.** A second create returns "this product already has a promise" (A:90; RAT:156). The scorer compares lists, so duplicates fail (score.py:22).
29. **Brief A never uses `add_note`. Brief B needs a note for every product without a promise, even with one product and even when none is promised, and no note at all on any transfer.** Write notes at the end (A:119; B:16, B:18).
30. **B asks about today once in total.** Each product then starts at attempt 1, in `get_account` order (B:12).
31. **B: one date for all, past one product's deadline → that product on its own deadline, said in the read-back. One combined read-back, one "Do you confirm?", then one create per product** (B:14-15; PUB-13).
32. **B: `promise` wins if any promise was recorded, except on a transfer. With no promise: all `paid` → `paid`; otherwise the reason of the first product in `get_account` order whose note is not `paid`** (B:23). This can override the triggering rule's own reason (E7, E12).
33. **A restructuring request in B drops agreed-but-unrecorded promises.** Recorded ones stay (B:18).
34. **Exactly one `close_call`, as the last tool call, after the thanks and goodbye.** Nothing is accepted after it (A:106, A:121; OA:411; RAT:159). A goodbye phrase can trigger the platform's hang-up (base-agent:88).
35. **Never invent**: no customer-service number, no fees, no interest, no due dates, no reasons (A:100-101).
36. **All date rules use `now`, never the real clock** (A:20; wf:240). The final runs on several calendar days (README:76), so weekend and holiday edge cases (U-13, U-29) are live.
37. **Do not copy the example agent's wording.** It omits "the call is recorded" (base-agent:105) and asks "when they can pay" instead of the verbatim first ask (base-agent:315).
38. **The bank does not enforce the brief.** It records holidays, dates past the deadline and any amount (OA:6; HP §Evaluation; RAT:156, 161). Every rule is the agent's job.
39. **Nothing from A or B may be hard-coded for the hidden briefs.** Identity questions, limits, deadlines, calendar, outcome table, queues, enums and the brief's form all change; only the seven tool names, `now`, English and "up to three products" are promised to stay (README:71-80; HP §Overview).
