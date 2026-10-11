# 07 · The 13 practice cases (PUB-01 to PUB-13)

## In short

- The kit ships 13 practice customers: PUB-01 to PUB-10 use Brief A (one product) and PUB-11 to PUB-13 use Brief B (up to three products). Every one runs at `now = 2026-10-14T11:00`, a Wednesday [CODE PTS:1-635; DOC HP §Data L21].
- A case passes only if two separate checks pass. First, `score.py` compares the bank's ledger with the case's `expected` block: outcome and reason, promises, notes, callbacks, transfer queues, `close_call` as the last tool call, no early `get_account`, and no identity tools when nobody was reached. Second, a judge model reads the transcript against the case's `checks`, and its verdict must be `"pass"` [CODE SC:17-34; RC:93-97].
- The judge is given only the case's `checks` list, not the brief [CODE RC:47]. The checks test exact behaviour: one sympathy sentence, one support offer, the floor offered once, the exact-day question asked once, two attempts on one loan and one on the other, and the exact text-message sentence.
- Most cases are decided by date arithmetic the bank does not enforce. The late-band deadline is 2026-10-23, the early-band deadline 2026-11-02, "this Friday" is 2026-10-16, the next business day is 2026-10-15, and 2026-10-26 is a holiday [INFERRED from A:53-60, computed locally; see §16].
- Four cases are won by not running the persuasion ladder: PUB-05 (hardship), PUB-08 (already paid), PUB-09 (restructuring) and PUB-03 (identity failed). Two are won by stopping at the brief's limits: PUB-04 (deadline) and PUB-07 (holiday). PUB-10 tests one honest retry. PUB-02 tests silence towards a relative.
- Brief B adds a fixed order: state every product first, ask once about today, go product by product, give one combined read-back and one confirmation, make one `create_promise` per product, and call `add_note` once for each product without a promise (PUB-11, PUB-12, PUB-13) [DOC B r2-r8, B:10-16]. The note's reason is chosen by situation from five values: `refused`, `hardship`, `dispute`, `paid` or `service_error` (B r8, B:16). On any transfer (restructuring, support, human) no note is written at all (B r10, B:18). In the public set only PUB-12 writes notes, two `refused` ones [CODE PTS:558-567].
- Every customer can be replayed with five speech styles (`pieces`, `corrects`, `talkative`, `asks_back`, `in_words`). The facts and the expected ledger never change with the style [CODE RC:26-33; DOC RM:78].
- The hardest unresolved question: Brief A rule 15 says a second question in place of an answer closes the call as `declined`. Under `asks_back` that happens in a case where a `declined` close would fail [DOC A:44; CODE RC:31; INFERRED].

---

## 0. How to read this chapter

### 0.1 Sources and shorthand

Every kit path is under `kit/`.

| Short | File |
|---|---|
| PTS | `public-test-set.json` (the 13 cases). This file and the hackathon page are the primary sources for this chapter. |
| A | `briefs/brief-a.md` |
| B | `briefs/brief-b.md` |
| OA | `tools/openapi.json` |
| RC | `tools/run_cases.py` |
| SC | `tools/score.py` |
| FR | `freya.py` |
| RM | `README.md` |
| TC | `docs/tools-and-code.md` |
| WF | `docs/workflow-format.md` |
| API | `docs/api.md` |
| BA | `examples/base-agent.json` |
| SK | `.claude/skills/build-phone-agent/SKILL.md` |
| HP | `research/hackathon-page.md`, the official page text, cited by § and line (L) |
| RAT | `research/read-api-and-testing.md`. It is used **only** for facts its author probed live, relabelled [PROBED-earlier]. |

Citations are `file:line`. "A r14" means Brief A rule 14 and "B r6" means Brief B rule 6. §0.3 maps each rule to its line.

### 0.2 Labels

| Label | Meaning |
|---|---|
| [DOC] | Stated in a brief, a kit doc, `openapi.json` or the hackathon page. |
| [CODE] | Read from kit code or kit data (`run_cases.py`, `score.py`, `freya.py`, `public-test-set.json`, `base-agent.json`), or produced by running that code locally with no network. |
| [PROBED-earlier] | Seen in live calls an earlier agent made on 2026-10-10 (RAT:5 says these touched only PUB-01 and PUB-11). Kept, not repeated. |
| [INFERRED] | Reasoning from the sources. |
| [UNCERTAIN] | Not settled by any source. The text says exactly what is unknown. |

**No network call of any kind was made for this chapter.** Persona texts were rebuilt by AST-extracting `PERSONA`, `STYLES` and `persona_for` from RC and running them locally. Dates came from local `python3`. The ledger examples for PUB-12 and PUB-13 came from calling the kit's own `score_ledger` on hand-made ledgers.

### 0.3 Where each brief rule sits

| Brief A rule | Line | Brief A rule | Line | Brief A rule | Line |
|---|---|---|---|---|---|
| Call variables table | A:15-20 | r17 debt statement | A:49 | r33 no discount/plan | A:84 |
| r1 opening sentence, banned words | A:24 | Business days, holidays | A:53 | r34 read-back, "Do you confirm?" | A:88 |
| r2 "Am I speaking with…" | A:25 | r18 bands table | A:55-60 | r35 change at read-back | A:89 |
| r3 what counts as confirmation | A:26 | r19 valid promise date | A:62 | r36 one promise per product | A:90 |
| r4 robot/AI | A:27 | r20 weekend/holiday | A:63 | r37 recorded only after ok, retry once | A:91 |
| r5 third party: say nothing | A:31 | r21 vague period | A:64 | r38 text-message sentence | A:92 |
| r6 callback window | A:32 | r22 this/next weekday | A:65 | r39 already paid | A:96 |
| r7 callback outside window | A:33 | r23 date after deadline | A:66 | r40 dispute | A:97 |
| r8 wrong number | A:34 | r24 full amount first | A:70 | r41 restructuring | A:98 |
| r9 deceased | A:35 | r25 floor | A:71 | r42 human | A:99 |
| r10 relative told nothing | A:36 | r26 "too much" → floor once | A:72 | r43 scam | A:100 |
| r11 two questions, ISO DOB | A:40 | r27 customer-proposed amount | A:73 | r44 cannot answer → no invention | A:101 |
| r12 three wrong in total | A:41 | r28 "Can you make this payment today?" | A:77 | r45 does not want to talk | A:102 |
| r13 `day_month_swapped` | A:42 | r29 proposal is never a refusal | A:78 | r46 exactly one `close_call`, last | A:106 |
| r14 failed identity | A:43 | r30 flat refusal, attempts 1 and 2 | A:79-81 | Outcome table | A:108-115 |
| r15 declines identity | A:44 | r31 attempts used up → refused | A:82 | Transfer after a promise | A:117 |
| r16 `get_account` after both pass | A:48 | r32 hardship | A:83 | "Brief A never uses `add_note`." | A:119 |
| | | | | r47 thank and goodbye before close | A:121 |

| Brief B | Line |
|---|---|
| "Every rule of Brief A applies unless a rule below replaces it." | B:5 |
| B r1 one to three products | B:9 |
| B r2 state every product first | B:10 |
| B r3 band and deadline per product | B:11 |
| B r4 one today-ask, then product by product | B:12 |
| B r5 attempts per product | B:13 |
| B r6 one date after one product's deadline | B:14 |
| B r7 one read-back, one `create_promise` per product | B:15 |
| B r8 notes for products without a promise | B:16 |
| B r9 dispute or paid on one product | B:17 |
| B r10 restructuring; no notes on any transfer | B:18 |
| B r11 `create_promise` fails twice | B:19 |
| Closing | B:23 |

### 0.4 About the input notes, and where the source overrode them

- The task named seven note files `knowledge/notes/cases-*.md`. **Only six exist**: `cases-PUB-01-PUB-02.md`, `cases-PUB-03-PUB-08.md`, `cases-PUB-04-PUB-07.md`, `cases-PUB-05-PUB-09.md`, `cases-PUB-06-PUB-10.md` and `cases-PUB-11.md` [CODE: directory listing]. **No note covers PUB-12 or PUB-13.** Sections 13 and 14 of this chapter were written directly from PTS, the briefs, RC and SC, with the scorer run locally.
- Every case's data, script, expected block and checks were re-checked line by line against PTS. They match the notes. The disagreements found are listed below; in each, the source wins.

| Note and claim | Source says | Correction |
|---|---|---|
| `cases-PUB-11.md:128`: "PUB-13 has the same coincidence (6604, PTS:83,88). PUB-12 does not (9015 against 4410, PTS:15,20)" | PTS:83 and PTS:88 belong to PUB-02. The lines are PTS:592/597 (PUB-13: phone 6604, card 6604) and PTS:524/529 (PUB-12: phone 4410, card 9015). | The facts are right, the line numbers are wrong. |
| `cases-PUB-11.md:57`: "PUB-13's expected 2026-10-23 (PTS:113)" | The loan's date is at PTS:622. | Line number wrong. |
| `cases-PUB-11.md:454`: "PUB-13, where the move does happen [PTS:100-114]" | PUB-13 is PTS:578-634. | Line numbers wrong. |
| `cases-PUB-11.md:471`: "PUB-12 tests it [PTS:66]" | The check "two attempts on the personal loan (late band), one on the car loan (early band)" is PTS:575. | Line number wrong. |
| `cases-PUB-11.md` §0.2 cites the floor rule as `brief-a.md:72` | Rule 25 (the floor) is A:71. A:72 is rule 26. | Line number off by one. |
| `cases-PUB-01-PUB-02.md` §0.2 item 8: "The agent speaks first" [INFERRED] | No kit file states who speaks first in a chat simulation. Other notes mark it [UNCERTAIN]. | Treated here as [UNCERTAIN], with the inference that the agent opens because BA's initial node has an `on_enter` line (BA:104-105, 399). |
| `cases-PUB-03-PUB-08.md` §2c gives `wrong_answers_left` 2, 1, 0 as values | No source gives the values. The note itself marks them [INFERRED]. | Kept as [INFERRED]; the starting value is [UNCERTAIN]. |

---

## 1. What every case shares

### 1.1 How one practice case runs

1. `run_cases.py` filters the cases by `--brief` and `--only` (a comma-separated id list) [CODE RC:50-52].
2. It builds one persona per case with `persona_for`. It caches each persona in `.personas.json` under `id + ":" + sha1(json.dumps(spec, sort_keys=True))[:10]`. A changed text, including a changed style, makes a new persona [CODE RC:54-61]. The keys computed locally are in the appendix.
3. For each run, it opens one fresh practice session per case: `POST /v1/practice/sessions {"case": "<id>"}`, and keeps the returned `variables` [CODE RC:86].
   - The reply is `{ok, variables:{customer_id:"c_<uuid-ish>", first_name, last_name, title, now}}`. Every call makes a new `customer_id`. `now` is fixed per case at `2026-10-14T11:00`, and a `now` sent in the body is ignored. The bank keeps products, identity and fault injection on its own side [PROBED-earlier RAT:126-130].
   - The case file's own `variables` block (which has **no** `customer_id`) is used only to write the persona's name [CODE RC:36-37].
4. It starts one simulation with all cases [CODE RC:88; FR:87-95]:
   - `"mode": "chat"` (text, not voice)
   - `runsPerPersona: 1`
   - `maxCallDurationSeconds: 420`
   - `maxConcurrentCalls` from `FREYA_SIM_CONCURRENCY`, default 5
   - `customerVariablesMap`: the session variables, keyed by persona id
   - the phone agent's dialogue, routing and extraction model: `experimental-5` [CODE FR:84, 94]
   - the customer and the judge: `gemini-3-flash-preview` [CODE FR:85, 95]
5. A workspace runs one simulation at a time. A second one waits in 30-second steps [CODE FR:89-99; DOC RM:88].
6. After the simulation, for each case [CODE RC:92-99]:
   - it reads the ledger with `GET /v1/practice/ledger/{customer_id}` and runs `score_ledger`;
   - if the judge's `outcome` is not `"pass"`, it adds `"conversation: " + reason[:400]`, or `"no verdict"` when there is no reason;
   - the case passes only if the failure list is empty;
   - it prints `PASS`/`FAIL`, the id, level, family and the tool chain, with `verify_identity` shown as `verify` and `create_promise` as `promise`.
7. It reads each call's messages and reports the slowest agent turn. It warns when the median is above 10 s [CODE RC:101-118]. With `--rerun-if-slow N`, a run whose median slowest turn is above 10 s is thrown away and repeated after 5 minutes [CODE RC:50, 66-69].
8. With `--reps N`, a customer counts only when every run passes [CODE RC:72-73]. The final runs every hidden customer 3 times and requires all 3 to pass [DOC HP §Evaluation L27; RM:76].
9. A ten-case Brief A run takes 3 to 11 minutes [DOC RM:24, 88; HP §Evaluation L28].
10. Kit history: v3 of the example builder "built an agent that passed 10 of the 10 practice customers in one run" on Brief A [DOC RM:5]. The example agent `base-agent.json` "passed 2 of the 13 practice customers" in one run [DOC RM:34].

### 1.2 What the phone agent receives

- Only the call variables `customer_id`, `first_name`, `last_name`, `title` and `now`. "Nothing else is known before the tools are called." [DOC A:13-20]
- `customer_id`: "Pass it to every tool call." `title`: "Address the customer as title plus last name." `now`: "All date rules use this, never the real clock." [DOC A:17-20]
- The agent never sees the case's `products`, `identity`, `script`, `expected`, `checks` or `faults` [CODE RC:86-88].
- Product ids come from `get_account` as `p1`, `p2`, … [DOC RM:102; PROBED-earlier RAT:155]. The expected blocks use `p1`, `p2`, `p3` in the order the products are listed in PTS [CODE PTS].
- Platform traps around dates [DOC]:
  - `{{system.*}}` dates are the real clock: "If your task supplies its own "now" as a call variable, use that variable." [WF:240]
  - "Date values are formatted for speech in the agent's language when they are substituted into a prompt." [WF:200]. Whether the `now` string is treated as a date value and reformatted is [UNCERTAIN].

### 1.3 The persona template, verbatim

`persona_for` fills this template [CODE RC:13-24]:

```
OUTPUT RULE: Write only the words you say on the phone. No stage directions, no brackets. One or two short sentences per turn, then wait for the other side.

WHO YOU ARE: {who}

WHAT HAPPENS IN THIS CALL: {script}

RULES:
- Answer what you are asked. Do not volunteer information nobody asked for.
- When you give a number or a date, say all of it in one turn. Never stop halfway through.
- Do not invent dates, amounts or facts that are not written above. If asked something that is not covered, give a short neutral answer.
- If the caller reads something back and it matches what you agreed, say "Yes, I confirm."
- When the caller says goodbye, say "Thank you, goodbye." and say nothing more.
```

How `{who}` is built [CODE RC:36-44]:
- If `family == "Third party"` or the case has a `third_party` key: `"You are NOT {first} {last}. You answered this phone. You do not know {first} {last}'s security answers and you would not give them. The text below says who you are."` Only PUB-02 takes this branch.
- Otherwise: `"You are {first} {last}. "`, then one sentence per identity key in file order, then `" Give these only when asked, and give the wrong ones where the text below says so."`
  - `date_of_birth` → `"Your date of birth is {} (say it in words, like '14 March 1988')."` The DOB is inserted in ISO form, and the persona model turns it into words.
  - `phone_last4` → `"The last four digits of your phone number on file are {}."`
  - The map also holds templates for `postcode`, `birth_year`, `company_number` and `founded_year`, and a generic fallback `"Your <key> is {}."` [CODE RC:41-44]. No public case uses them. [INFERRED] The organisers' harness is ready for other identity questions, which matches "other identity questions" in the final briefs [DOC HP §Overview L12; RM:71].
- Persona object [CODE RC:47]: `name` = `id + " " + title`, plus `" [style]"` when a style is set; `prompt` as above; `successCriteria` = `"All of these are true:\n- " + "\n- ".join(checks)`; `tags` = `["hackathon", "brief-" + brief]`.

What every persona knows and does not know [INFERRED from the template]:
- It knows its own name (not its title), its true identity answers, and the one-line script.
- It does **not** know the products, card digits, amounts, days late, floors, deadlines, `now` or the calendar. Whether the simulator passes the call variables to the persona is [UNCERTAIN]; `customerVariablesMap` is documented only as "the object of call variables for that persona's call" [DOC API:214].
- So it can only say "the full amount", "today", "tomorrow", "this Friday" or a date written in its script. When asked something not covered, it gives "a short neutral answer" [CODE RC:22].
- "Do not volunteer" means facts usually come as answers to questions, so script beats may arrive later or split across turns [INFERRED from RC:20].
- After the agent's goodbye it says exactly "Thank you, goodbye." and then nothing [CODE RC:24]. A matching read-back gets exactly "Yes, I confirm." [CODE RC:23].

### 1.4 The five speech styles, verbatim

| Style | Exact text appended after a blank line [CODE RC:28-32, 46] |
|---|---|
| `pieces` | "HOW YOU TALK: you give long numbers and dates in two parts. Say the first half, stop, and give the rest in your next turn or when asked. This replaces the rule about saying all of it in one turn." |
| `corrects` | "HOW YOU TALK: the first time you say a day or an amount, you say a slightly different one first and correct yourself in the same sentence, like 'the 21st, sorry, I mean the 20th'. The corrected value is the one written above. Do this once or twice in the call, not more. Never do it with a security answer: those you say right the first time unless the text above says otherwise." |
| `talkative` | "HOW YOU TALK: you talk a lot. Before most answers you add one or two sentences about your day, the traffic or how busy work is. Once in the call you mention that your cousin's wedding is on the 30th. It has nothing to do with any payment, and you never offer it as a payment day." |
| `asks_back` | "HOW YOU TALK: twice in the call, before you answer, you ask a short question back, like 'why do you need that?' or 'which account is this about?'. Whatever the caller replies, you then give your answer." |
| `in_words` | "HOW YOU TALK: you say every amount and every date in words and never in digits, like 'four hundred and fifty-five' and 'the twenty-second of October'. Postcodes, years and other codes you say digit by digit." |

- "The facts of the case stay the same, only the way of saying them changes." [CODE RC:26]. "The facts stay the same." [DOC RM:78]. So **the expected ledger is identical under every style**.
- One `--style` applies to every case in a run. A case could carry its own `style` key [CODE RC:45], but no public case does [CODE PTS].
- The final's customers "give a number in two parts ("463..." then "51"), corrections, talk about other things, a question back, amounts and dates in words" [DOC HP §Evaluation L27; RM:78].
- The styles that recur in every case, and what they force [INFERRED]:
  - `pieces`: never call a tool, validate or read back on half a value; join the halves.
  - `corrects`: use the value after "sorry, I mean". The first value is often a valid but wrong date.
  - `talkative`: "the 30th" is 2026-10-30, a Friday business day. It is after the late deadline and inside the early deadline. It must never become a payment or callback date. "Busy at work" is not hardship.
  - `asks_back`: answer the question, then repeat the pending ask. Do not count it as a refusal, a non-answer or an unclear identity (§1.9 item 6).
  - `in_words`: convert to ISO dates and digit strings. A phone answer sent as words is counted wrong [PROBED-earlier RAT:151].

### 1.5 How a run is scored: `score_ledger` line by line

`score_ledger(case, led)` [CODE SC:17-34] adds one failure per mismatch:

| SC line | Comparison | What it means in practice |
|---|---|---|
| 19-20 | `(led.get("outcome"), led.get("reason")) == (exp["outcome"], exp.get("reason"))` | Exact tuple match. For `promise` and `paid` the expected reason is JSON `null`, so the ledger reason must be null or absent. `""`, `"none"` or `"promise"` fail if the bank stores them [UNCERTAIN whether it stores, nulls or rejects them]. |
| 21-22 | Sorted `(product_id, round(float(amount), 2), date)` of promises equals the expected list | A multiset compare. Order is free. `220`, `220.0`, `"220"` and `220.004` all pass. The date is an exact string: `"2026-10-16T00:00"` fails [CODE, run locally]. An amount `float()` cannot parse (for example `"1,250"`) would raise [INFERRED]. |
| 23-24 | Sorted `(product_id, reason)` of notes equals expected | Note `text` is ignored. Duplicates count: two `(p2, refused)` notes fail [CODE, run locally]. Any note in a Brief A case fails, because every Brief A expected block has `notes: []`. |
| 25-26 | Sorted `(date, time)` of callbacks equals expected | Exact strings, for example `("2026-10-15", "11:00")`. |
| 27 | Sorted transfer `queue`s equal expected | A missing or a duplicate transfer fails. |
| 28-29 | `calls` non-empty and `calls[-1]["tool"] == "close_call"` | Message: "the call was not closed with close_call". |
| 30-32 | No `get_account` or `create_promise` whose `result.error == "identity not verified"` | One early call fails the case **even if a later call succeeds**. |
| 33 | If the expected outcome is `not_reached`, `no_contact` or `unreached`: no `verify_identity` or `get_account` at all | Only PUB-02 is affected. Rejected calls count, because `calls` logs them [PROBED-earlier RAT:140]. |

What `score.py` does **not** check: how many times a tool was called (a duplicate `create_promise` rejected with "this product already has a promise" adds nothing), wrong identity answers, wording, read-backs or turn order. Those are left to the judge, and only as far as the case's checks reach [CODE SC:17-34; INFERRED].

The judge [CODE RC:47, 95-96; DOC RM:61-63, API:161]:
- receives `successCriteria = "All of these are true:\n- " + "\n- ".join(checks)`, "Text that the judge model checks after the call";
- reads the transcript "for 2 and 3" (policy and honesty) "against the checks listed for that customer";
- is **not** given the brief. So a rule that no check names is probably not judged in practice [INFERRED]. The hidden cases have their own checks [DOC HP §Evaluation L24], so every rule still matters.
- Whether the judge sees tool-call events or only spoken text is [UNCERTAIN]. A call record holds both `messages`, which include `function_call_start` and `function_call_complete` events, and `transcript`, a plain text string [DOC API:306-330; RM:99]. The safe assumption is that every fact a check names must also be **spoken** [INFERRED].
- At the end of a call the order is: call analysis, then `end_of_call` tools, then success-criteria judging [DOC TC:563].
- "The same phone agent can pass a customer in one run and fail it in the next." [DOC RM:67]

### 1.6 The ledger and the bank's behaviour [PROBED-earlier]

`GET /v1/practice/ledger/{cid}` returns [RAT:133-141]:

| Field | Content |
|---|---|
| `case`, `team`, `now` | Session meta. `team` is a hash of the team key [RAT:123]. |
| `verified` | `{field: bool}` |
| `wrong` | Count of wrong answers |
| `hinted` | Meaning unknown [UNCERTAIN] |
| `promises` | `[{promise_id, product_id, type, amount, date}]` |
| `notes`, `callbacks`, `transfers` | What was recorded |
| `outcome`, `reason` | From `close_call` |
| `failures` | `{tool: n}`, the injected-failure counters ("PUB-10 fails the first `create_promise`") |
| `calls` | `[{n, tool, args, status, result}]`: every tool call with its exact arguments, including rejected ones |
| `last_at` | Time of the last call |

Bank behaviour [PROBED-earlier RAT:144-161]:
- Business errors are **HTTP 200 with `ok:false`**. The exceptions are `unknown customer_id` (404) and key errors (401).
- `verify_identity`: returns `{ok, verified, wrong_answers_left, all_verified}`. A DOB in words (`"14 March 1988"`, `"3 June 1987"`) was accepted, but the spec says ISO. `"garbage"` gave `ok:false` and was not counted. The phone answer `"two two eight eight"` **was counted wrong**. An unknown field gives `"field must be date_of_birth or phone_last4"`. One re-verify of an already-verified field returned **no `all_verified` key**.
- `get_account` before verification: `{ok:false, error:"identity not verified"}`, logged. Ids are `p1..p3`.
- `create_promise`: `{ok, promise_id:"pr1"}`. A string amount `"220"` is accepted. Amounts are not checked (99999 was accepted). Errors: `"date must be YYYY-MM-DD"`, `"unknown product_id"`, `"this product already has a promise"`.
- `add_note` and `transfer_to_agent`: enums enforced (`"unknown reason"`, `"unknown queue"`).
- `schedule_callback`: `"11am"` gives `"date must be YYYY-MM-DD and time HH:MM"`.
- `close_call`: the enum is enforced (`"no_contact"` gives `"unknown outcome"`). Outcome and reason are checked for consistency, and the error names the allowed reasons (`no_promise` needs one of `refused, hardship, dispute, service_error`). After a close, every tool returns `"the call is already closed"`.
- The bank does not enforce the brief: it accepts holidays, dates past the deadline and any amount [PROBED-earlier RAT:161]. This is also documented: "it records a promise on a holiday or past the deadline without complaint. Following the brief is the agent's job." [DOC OA:6] and "records a promise on a holiday or below the minimum" [DOC HP §Evaluation L25].

### 1.7 The tool contracts the cases use

All seven tools are `POST https://freya-bank-mock.freyavoice.workers.dev/v1/<tool>` with a JSON body. They need no key: "the customer_id in the body is the secret of one call" [DOC OA:6, 8-12]. Every 200 says "`ok` is false when the action was not carried out." Every 500 says "The service failed. Nothing was recorded. The call may be repeated." [DOC OA:51, 83-85 and the same for each tool].

| Tool | Request (required marked *) | Response fields | Summary line |
|---|---|---|---|
| `verify_identity` | `customer_id`*, `field`* ∈ {`date_of_birth`, `phone_last4`}, `answer`* string: "For date_of_birth: the date as YYYY-MM-DD. Callers say dates in words, the agent converts. An unreadable value is rejected with ok=false and is not counted as a wrong answer. For phone_last4: four digits." [OA:15-46] | `ok`, `error`, `verified`, `wrong_answers_left` (int), `all_verified`, `hint` ∈ {`day_month_swapped`} [OA:57-77] | "Check one security answer. Three wrong answers in total end the check." [OA:17] |
| `get_account` | `customer_id`* [OA:97-105] | `ok`, `error`, `products[]`: `product_id`, `type` ∈ {`credit_card`, `personal_loan`, `car_loan`}, `card_last4` ("credit cards only"), `past_due`, `days_late`, `minimum_payment` ("credit cards only"), `instalment_amount` ("loans only") [OA:117-160] | "The late products. Refused until both questions are passed." [OA:91] |
| `create_promise` | `customer_id`*, `product_id`*, `amount`* (number), `date`* (format date) [OA:180-201] | `ok`, `error`, `promise_id` [OA:213-223] | "Record a payment promise. One per product." [OA:174] |
| `add_note` | `customer_id`*, `product_id`*, `reason`* ∈ {`refused`, `hardship`, `dispute`, `paid`, `service_error`}, `text` (optional) [OA:242-268] | `ok`, `error` | "Brief B: record why a product ended without a promise." [OA:236] |
| `schedule_callback` | `customer_id`*, `date`* (format date), `time`* ("HH:MM") [OA:306-325] | `ok`, `error` | "Book a callback." [OA:300] |
| `transfer_to_agent` | `customer_id`*, `queue`* ∈ {`restructuring`, `general`, `support`} [OA:362-379] | `ok`, `error` | "Hand the call to a person." [OA:356] |
| `close_call` | `customer_id`*, `outcome`* ∈ {`promise`, `paid`, `transferred`, `no_promise`, `not_verified`, `not_reached`}, `reason` string: "Required for every outcome except promise and paid. See the table in the brief." [OA:417-441] | `ok`, `error` | "End the call. Always the last tool call. Nothing is accepted after it." [OA:411] |

Inside a Freya workflow [DOC]:
- An `api_call` result is an envelope `{status, data, message, status_code, header}`. The API body sits in `data` [TC:250-258].
- Results are flattened into variables such as `<tool>_response.data.ok`. **Booleans arrive as strings**, so test both `"true"` and `"True"` [TC:262-286].
- The engine keeps `<tool>_success_count` and `<tool>_failure_count` [TC:319-327]. What increments `_failure_count` (HTTP status or `ok:false`) is [UNCERTAIN].
- "Each call of the same tool overwrites the previous `_args` and `_response` values." [TC:279]. Whether keys missing from the later response are cleared is [UNCERTAIN].
- "The working builder sets `maxRetries` to `0` on tools that write data… A retried write can record the same thing twice if the API is not idempotent." [TC:365]. BA sets `maxRetries: 0` [CODE BA:10, 161, 205, 335].

### 1.8 The common call skeleton and the exact sentences

Every Brief A customer case (all except PUB-02) follows this skeleton [DOC A:24-121; INFERRED for the order]:

Two kinds of wording appear in the last column [DOC; same split as `06-brief-rules.md` §8.1/§8.2]. **Bold** = verbatim: the brief quotes the sentence itself and tells the agent to say or ask it. The brief has exactly five: "Am I speaking with {title} {last_name}?" (A:25), "I am sorry for your loss." (A:35), "Can you make this payment today?" (A:77), "Do you confirm?" (A:88) and "You will receive a text message confirming this promise." (A:92). The product-name templates in A:49 are also quoted. *Content only* = the brief writes "say that …" or "say …" without quotation marks, so the content is required but the wording is free.

| Step | What happens | Wording: **verbatim**, or *content only* |
|---|---|---|
| 1 Opening | First sentence: digital assistant + Freya Bank + recorded. No "collections", "debt", "payment" or product before identity is verified. "This applies to everyone, including relatives." (A r1) | none fixed; a safe form is "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded." [INFERRED] |
| 2 Name check | (A r2) | **"Am I speaking with {title} {last_name}?"** |
| 3 Confirmation | Only "yes", "that's me", "speaking" or the customer's own name counts. "Hello", "go ahead" and "who is this" do not. Ask once more. Answer a customer's question first; the ask that follows is the second ask. Still unclear → `not_reached`/`unclear`. (A r3) | — |
| 4 Identity | Two questions, one at a time, DOB first, then the last four digits of the phone on file. DOB sent as `YYYY-MM-DD`. A date in numbers only is read day, month, year. (A r11-r15) | — |
| 5 Account | `get_account` only after both pass. (A r16) | — |
| 6 Debt statement | Collections team + late payment + product in words ("credit card ending 4821", "personal loan", "car loan") + past-due amount + days late. (A r17) | **the product-name templates** quoted in A:49 ("credit card ending {card_last4}", "personal loan", "car loan"); the rest of the debt statement is *content only* |
| 7 First ask | Full amount first; never "how much can you pay?" (A r24) | **"Can you make this payment today?"** (A r28) |
| 8 Negotiation | Dates (A r19-r23), amounts (A r25-r27), attempts (A r29-r31), hardship and other triggers (A r32-r33, r39-r45) | *content only*: the latest date you can record is the deadline, and offer it (A r23: "say the latest date you can record is the deadline and offer it", A:66). Not a fixed sentence. |
| 9 Read-back | Product, amount and date, then the question. `create_promise` only after a clear yes. (A r34) | **"Do you confirm?"** |
| 10 Record | Say "recorded" only after `ok: true`. On failure, try once more. If it fails again, say you could not record it and close `no_promise`/`service_error`. (A r37) | — |
| 11 SMS sentence | After a recorded promise (A r38) | **"You will receive a text message confirming this promise."** |
| 12 Goodbye | Thank and say goodbye before `close_call`. (A r47) | — |
| 13 Close | Exactly one `close_call`, the last tool call. Reason only where the table lists one. (A r46) | — |

Sentences outside the skeleton [DOC]:

| Sentence | Kind | Source | Reached by a public case? |
|---|---|---|---|
| **"I am sorry for your loss."** | verbatim (quoted in the brief) | A r9, A:35 | no (no deceased case) |
| *payments can take one business day to appear* | content only: "say that payments can take one business day to appear" | A r39, A:96 | yes, PUB-08. Its check repeats the words ("agent says payments can take one business day to appear", PTS:344), so staying close to them is safest [INFERRED]. |
| *that you are Freya Bank's digital assistant* (robot or AI question) | content only: "say that you are Freya Bank's digital assistant and continue" | A r4, A:27 | yes, PUB-04 (check "agent says it is a digital assistant when asked", PTS:175) |
| *they can verify the call by phoning Freya Bank's customer service number* (scam question) | content only: "say they can verify the call by phoning Freya Bank's customer service number, and continue" | A r43, A:100 | no |

**Closing timing [INFERRED]:** after the agent's goodbye the persona says "Thank you, goodbye." and goes silent [CODE RC:24]. `close_call` must therefore come in the same turn as the goodbye (after the goodbye words) or in the very next turn. If the call ends first, the ledger has no `close_call` and SC:28-29 fails. A silent agent is hung up on (`customer-ended-call`) [DOC RM:100]. BA runs `close_call` as an `end_of_call` lifecycle tool, which fires after the call ends and is therefore always last [CODE BA:333-337]. A lifecycle tool with an unresolved `{{var}}` gets its parameters from one model call [DOC TC:561]. BA's pre-hook removes `reason` when the outcome is `promise` or `paid` [CODE BA:395].

### 1.9 Open questions that touch every case

1. **Who speaks first** in a chat simulation is not documented [UNCERTAIN]. BA opens with an `on_enter` line in its initial node, so the agent speaks first in that design [CODE BA:104-105, 399]. If the customer opens with "Hello?", that is not a confirmation (A r3).
2. **Whether the judge sees tool events** [UNCERTAIN] (§1.5). Checks such as "create_promise called exactly once" and "transfer_to_agent called with queue restructuring" name tools, which suggests the organisers expect it [INFERRED].
3. **What the bank does with a `reason` sent with `promise` or `paid`**: stores it, nulls it or rejects the call [UNCERTAIN]. The scorer needs null. Omit the key.
4. **The starting value of `wrong_answers_left`**, and what `verify_identity` returns at and after the third wrong answer [UNCERTAIN]. 3 → 2 → 1 → 0 is the natural reading of "three wrong answers in total" [INFERRED].
5. **The currency word.** Neither brief names a currency [DOC A, B]. The page's example says "420 dollars" [DOC HP §Overview L8]. A r44 forbids inventing figures, and a unit is not a figure [INFERRED]. Whether a judge would object to "dollars" is [UNCERTAIN]. The ideal calls below say "dollars", following the page.
6. **A r15 against the `asks_back` style.** A r15: "Asking what the call is about instead of answering counts as declining. A second refusal or a second such question closes the call." [DOC A:44]. The style makes the customer ask back twice and then answer anyway [CODE RC:31], and the expected outcome stays the same [CODE RC:26]. If both questions fall in the identity phase, a literal agent closes `not_verified`/`declined` and fails. The reading that keeps every case passable [INFERRED]: a question **followed by the answer** is a question, not a decline. Only a refusal or a purpose question that still leaves the answer missing after the one explanation counts. The same tension exists with A r3's two-ask limit when both questions fall on the name check [INFERRED; UNCERTAIN how the judge would score it].
7. **Whether calls made after `close_call` are logged in `calls`** [UNCERTAIN]. If they are, they become `calls[-1]` and SC:28-29 fails.
8. **The hidden final's checks** may differ from the public ones [DOC HP §Evaluation L24; UNCERTAIN in content].

### 1.10 Key dates at a glance (full derivation in §16)

`now` = Wednesday 2026-10-14 11:00. Business days are Monday to Friday except 2026-10-26, 2026-11-11, 2026-11-26, 2026-12-25 and 2027-01-01 [DOC A:53]. Counting "after today" excludes today [INFERRED; confirmed by PUB-04 and PUB-13, see §16].

| Fact | Date |
|---|---|
| Today | Wed 2026-10-14 (a business day) |
| Next business day / "tomorrow" | Thu 2026-10-15 |
| "This Friday" = last business day of this week = attempt-1 date | Fri 2026-10-16 |
| "Next Friday" = late-band deadline (7th business day after today) | Fri 2026-10-23 |
| Holiday | Mon 2026-10-26 |
| Next business day after 10-26 | Tue 2026-10-27 |
| "The 30th" (talkative decoy; PUB-13's real date) | Fri 2026-10-30 |
| Early-band deadline (12th business day after today) | Mon 2026-11-02 |
| PUB-04's "6 November" | Fri 2026-11-06 (after both deadlines) |


---

## 2. PUB-01 · "Confirms identity and pays the full amount today"

Brief A · Happy path · easy. The baseline: every step of the skeleton, with no branch.

### 2(a) Case data [CODE PTS:2-48]

| Field | Value | PTS line |
|---|---|---|
| `id` / `brief` / `family` / `level` | `PUB-01` / `A` / `Happy path` / `easy` | 3-6 |
| `title` | "Confirms identity and pays the full amount today" | 7 |
| `variables` | `first_name` "Daniel", `last_name` "Reyes", `title` "Mr", `now` "2026-10-14T11:00" | 8-13 |
| `identity` | `date_of_birth` "1988-03-14", `phone_last4` "4471" | 14-17 |
| product (p1) | `type` `credit_card`, `card_last4` "4821" (a string), `past_due` 420.0, `days_late` 6, `minimum_payment` 126.0 | 18-26 |
| `script` | "Confirms he is Daniel Reyes. Date of birth 14 March 1988, last four digits 4471. Says he can pay the full amount today. Confirms at the read-back." | 27 |
| `expected` | `outcome` "promise", `reason` null, `promises` [{p1, 420.0, "2026-10-14"}], `notes` [], `callbacks` [], `transfers` [] | 28-41 |
| `checks` | 1 "both security questions passed before get_account"; 2 "the word 'collections' is not said before identity is verified"; 3 "create_promise called exactly once"; 4 "text-message sentence said after the promise" | 42-47 |
| `faults` | absent | — |

Side facts [DOC]:
- The dashboard's single practice customer has the same answers: "DOB 14 March 1988, last four 4471" [HP §FAQ L42].
- The page's example call uses this customer's numbers: "Your credit card has 420 dollars past due. Can you pay today?" … "420 dollars on Friday the sixteenth. Do you confirm?" → `create_promise 420.00 2026-10-16` [HP §Overview L8]. That is a different date from PUB-01's expected "today".
- The brief's own example product name is "credit card ending 4821" [A:49], the same digits as this card.

### 2(b) Derived values [INFERRED from A:55-60, A:71; dates §16]

| Fact | Value |
|---|---|
| Band | early (6 is in 1 to 7) |
| Deadline | 12th business day after today = Mon 2026-11-02 |
| Persuasion attempts | 1 |
| Floor | 126.0 (`minimum_payment`) |
| Attempt 1, if needed | 420.0 on Fri 2026-10-16 |
| Promise date "today" | 2026-10-14: today or later, a business day, not after 11-02, so valid (A r19) |

None of the persuasion values are used on the ideal path.

### 2(c) Persona [CODE RC:35-47, rebuilt locally]

- `name`: `PUB-01 Confirms identity and pays the full amount today` (plus ` [style]`). `tags`: `["hackathon", "brief-A"]`.
- `WHO YOU ARE`: "You are Daniel Reyes. Your date of birth is 1988-03-14 (say it in words, like '14 March 1988'). The last four digits of your phone number on file are 4471. Give these only when asked, and give the wrong ones where the text below says so."
- `successCriteria`: "All of these are true:\n- both security questions passed before get_account\n- the word 'collections' is not said before identity is verified\n- create_promise called exactly once\n- text-message sentence said after the promise"
- The persona does not know 420, the card or the date. It can say only "the full amount" and "today". If asked "how much can you pay?", it can only say "the full amount", and the agent has broken A r24 [INFERRED].

### 2(d) The ideal call

A = agent, C = customer, T = tool call. `<cid>` = the session's `customer_id`.

| # | Who | Line or call | Rules |
|---|---|---|---|
| A1 | A | "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with Mr Reyes?" | A r1: digital assistant + Freya Bank + recorded, in the first sentence. Putting "Hello" inside that sentence keeps it the first sentence [INFERRED]. A r2 exact ask. Title + last name (A:19). |
| C1 | C | "Yes, speaking." (or "That's me." / "This is Daniel Reyes.") | A r3 |
| A2 | A | "Thank you, Mr Reyes. I need to ask you two security questions. First, what is your date of birth?" | A r11. No purpose words (A r1). "Account" is allowed to the customer, because A r15 itself says the questions protect "their account" [A:44; INFERRED]. |
| C2 | C | "14 March 1988." | The persona says DOBs in words [RC:41]. |
| T1 | T | `verify_identity {"customer_id":"<cid>","field":"date_of_birth","answer":"1988-03-14"}` → `{"ok":true,"verified":true,"wrong_answers_left":<n>,"all_verified":false}` | A r11 ISO; OA:37. Response keys [PROBED-earlier RAT:149]. `<n>` [UNCERTAIN]. No swap is possible: 14 cannot be a month. |
| A3 | A | "Thank you. And what are the last four digits of the phone number we have on file for you?" | A r11. Speak after every tool result [DOC TC:219, 570, 575]. |
| C3 | C | "4471." | |
| T2 | T | `verify_identity {"customer_id":"<cid>","field":"phone_last4","answer":"4471"}` → `{…,"verified":true,"all_verified":true}` | Four digits, never words [PROBED-earlier RAT:151]. |
| T3 | T | `get_account {"customer_id":"<cid>"}` → `{"ok":true,"products":[{"product_id":"p1","type":"credit_card","card_last4":"4821","past_due":420.0,"days_late":6,"minimum_payment":126.0}]}` | A r16; SC:30-32. |
| A4 | A | "Thank you, Mr Reyes. I am calling from the collections team about a late payment on your credit card ending 4821. The past-due amount is 420 dollars, and it is 6 days late. Can you make this payment today?" | A r17, A r24, A r28 exact. No floor, no "how much". |
| C4 | C | "Yes, I can pay the full amount today." | Script |
| — | logic | Date = 2026-10-14 (valid). Amount = 420.0 = the full amount (inside [126.0, 420.0]). No attempt used. | A r19, A r27 |
| A5 | A | "Thank you. To confirm: 420 dollars on your credit card ending 4821, today, Wednesday 14 October. Do you confirm?" | A r34 exact question |
| C5 | C | "Yes, I confirm." | RC:23 |
| T4 | T | `create_promise {"customer_id":"<cid>","product_id":"p1","amount":420.0,"date":"2026-10-14"}` → `{"ok":true,"promise_id":"pr1"}` | A r34 (after a clear yes), A r36. `pr1` [PROBED-earlier RAT:156]. |
| A6 | A | "Your promise is recorded. You will receive a text message confirming this promise. Thank you for your time, Mr Reyes. Goodbye." | A r37, A r38 verbatim, A r47 |
| C6 | C | "Thank you, goodbye." | RC:24 |
| T5 | T | `close_call {"customer_id":"<cid>","outcome":"promise"}` (no `reason` key) → `{"ok":true}` | A r46; table A:110; OA:435 |

### 2(e) Final ledger and `score.py`

Expected ledger. Values come from the case; the shape is [PROBED-earlier]; `hinted` and `failures` are [UNCERTAIN], probably empty:

```json
{"case":"PUB-01","now":"2026-10-14T11:00",
 "verified":{"date_of_birth":true,"phone_last4":true},"wrong":0,
 "promises":[{"promise_id":"pr1","product_id":"p1","type":"credit_card","amount":420,"date":"2026-10-14"}],
 "notes":[],"callbacks":[],"transfers":[],"outcome":"promise","reason":null,
 "calls":[{"n":1,"tool":"verify_identity"},{"n":2,"tool":"verify_identity"},{"n":3,"tool":"get_account"},
          {"n":4,"tool":"create_promise"},{"n":5,"tool":"close_call"}]}
```

`run_cases.py` prints `verify > verify > get_account > promise > close_call` [CODE RC:99].

| SC line | PUB-01 comparison |
|---|---|
| 19-20 | `("promise", None)`. A reason of `""` or `"none"` fails if stored. |
| 21-22 | `[("p1", 420.0, "2026-10-14")]`. `420`, `420.0` and `"420"` pass. A second stored promise of any kind fails. |
| 23-27 | notes, callbacks and transfers all `[]` |
| 28-29 | the last call is `close_call` |
| 30-32 | no `get_account`/`create_promise` with "identity not verified" |
| 33 | not applied |

### 2(f) Judge checks → rules → turns

| Check (exact) | Rules | Turns | What the judge needs to see |
|---|---|---|---|
| both security questions passed before get_account | A r11, A r16 | T1 → T2 (`all_verified:true`) → T3 | Tool events in order [UNCERTAIN whether visible]. SC:30-32 covers part of the same ground from the ledger. |
| the word 'collections' is not said before identity is verified | A r1, A r17 | A1, A2, A3 contain no banned word; "collections" first appears in A4 | "Verified" means after **both** answers. "Collections" said between T1 and T2 fails [INFERRED]. A r1 also bans "debt", "payment" and the product; the check names only "collections". |
| create_promise called exactly once | A r34, A r36, A r37 | T4 only | A first call rejected for format (`"date must be YYYY-MM-DD"`) followed by a good retry is **two** calls. The ledger passes; the judge check fails [INFERRED]. So the first call must already be well formed. |
| text-message sentence said after the promise | A r37, A r38 | A6, after T4 returned `ok:true` | Verbatim, after the tool result, not in the read-back. |

### 2(g) Ways to fail, most likely first [INFERRED unless cited]

1. **Silence after a tool result.** The customer hangs up and there is no `close_call` (SC:28-29). This is documented: "more often when the result is bare data such as `{"ok": true, "verified": true}`" [DOC TC:570]. A model turn with nothing produced "The model returned no speakable content" [DOC TC:219].
2. **The text-message sentence** is paraphrased ("you'll get an SMS"), left out, said before T4, or said in the read-back (check 4).
3. **A non-null `reason`** on `close_call` (SC:19-20), or the bank rejects the close so none is recorded [UNCERTAIN which].
4. **Wrong promise date**: the real clock instead of `now` [DOC WF:240]; a non-ISO date (`"14/10/2026"`, `"2026-10-14T11:00"`) rejected with `"date must be YYYY-MM-DD"` [PROBED-earlier RAT:156], then either a dishonest "recorded" or a retry that breaks check 3.
5. **`create_promise` without the read-back** and "Do you confirm?" (A r34). No public check names it; a hidden one may.
6. **Purpose leaked before verification**: "before we discuss your payment", "your credit card", or "collections" between T1 and T2 (A r1; check 2 if the word is "collections").
7. **Identity mechanics**: both questions in one turn; phone sent as words (counted wrong); `get_account` after T1 only (SC:30-32).
8. **Invented `product_id`** (`"credit_card_4821"`) → `unknown product_id` [DOC RM:102]; the retry makes 2 calls (check 3).
9. **Incomplete debt statement** (no days late, no "ending 4821", no amount), against A r17. No public check.
10. **Floor mentioned or "how much can you pay?" asked**, against A r24 and A r26. No public check.
11. **Wrong exact wording** of "Am I speaking with Mr Reyes?", "Can you make this payment today?" or "Do you confirm?". No public check; a hidden one may.
12. **"Daniel"** instead of "Mr Reyes" (A r2, A:19).
13. **A tool call after `close_call`**, or a second `close_call`. The bank refuses it, and if it is logged it becomes `calls[-1]` [UNCERTAIN].
14. **Engine retries** on `create_promise` (`maxRetries` > 0) could repeat a call. BA uses 0 [CODE BA:335].
15. **Over 420 s**, from a slow model or a talkative style [CODE FR:87].

### 2(h) Under each speech style

| Style | What changes | What the agent must do |
|---|---|---|
| `pieces` | "Fourteenth of March…" / "1988"; "44…" / "71". He never says an amount. | Never call `verify_identity` on half an answer. "14 March" with a guessed year (for example 2026) is readable but **wrong**, and uses one of three attempts. "44" alone is very likely counted wrong [INFERRED from PROBED-earlier RAT:151]. Ask "And the year?" / "And the last two digits?" and join. |
| `corrects` | No change to security answers. Likely at C4: "I can pay it tomorrow, sorry, I mean today." | Keep the corrected value. The first value gives a ledger date of 2026-10-15 and fails. If in doubt, fix it at the read-back (A r35). |
| `talkative` | Chatter; "my cousin's wedding is on the 30th". | Pull the answer out of the chatter. "Busy at work" is not hardship (A r32 names illness, a death in the family and job loss). "The 30th" = 2026-10-30, a valid-looking but **wrong** date. Turns grow towards 420 s. |
| `asks_back` | After A1: "Which account is this about?" | Answer without purpose words ("I can only discuss that with Mr Reyes. Am I speaking with Mr Reyes?"). That ask is the second ask (A r3). |
| | After A2/A3: "Why do you need that?" | Explain once that the questions protect his account (A r15), then re-ask. See §1.9 item 6 for the `declined` trap. |
| | After A4: "Which account is this about?" | Verification is done, so answer: "Your credit card ending 4821." Then repeat the ask. It is not a refusal or non-answer (A r30). |
| `in_words` | DOB "the fourteenth of March, one nine eight eight"; phone "four four seven one". | Send `1988-03-14` and `"4471"`. |

### 2(i) Ambiguities this case resolves or exposes

1. **Today is a valid promise date** and needs no persuasion (A r19 "today or later") [resolved].
2. **"Identity verified" means both answers passed** (the check's wording) [resolved].
3. **"Account" before verification**: allowed to the customer, since A r15 uses it [A:44]; risky only towards third parties (A r10) [INFERRED].
4. **"This payment" in A r28 is the full past-due amount** (A r24; expected 420.0) [resolved].
5. **"First sentence"** [A:24]: a separate "Hello." would technically be the first sentence. Whether a judge counts it is [UNCERTAIN]; put the greeting inside the required sentence [INFERRED].
6. **"Exactly once" against a retry after the agent's own format error**: the ledger cannot tell them apart; the judge can [INFERRED].
7. **Order R37 → R38 → R47 → R46**: "recorded", then the SMS sentence, then thanks and goodbye, then `close_call` last. The persona's silence after its goodbye makes the timing of `close_call` a real design question [INFERRED].
8. **The reason on `promise`**: the table says "none" [A:110]; the expected value is null; the bank's handling of a string is [UNCERTAIN].

---

## 3. PUB-02 · "A relative answers"

Brief A · Third party · medium. The only public case where the customer is never reached, and the only one with a callback [CODE PTS].

### 3(a) Case data [CODE PTS:49-92]

| Field | Value | PTS line |
|---|---|---|
| `id` / `brief` / `family` / `level` | `PUB-02` / `A` / `Third party` / `medium` | 50-53 |
| `title` | "A relative answers" | 54 |
| `variables` | `first_name` "Maria", `last_name` "Costa", `title` "Ms", `now` "2026-10-14T11:00" | 55-60 |
| `identity` | `date_of_birth` "1979-11-02", `phone_last4` "0358". **Never used**: the third-party persona branch ignores them [CODE RC:38-39], and the agent must not ask. | 61-64 |
| product (p1) | `type` `personal_loan`, `past_due` 310.5, `days_late` 11, `instalment_amount` 103.5. No `card_last4` (loans have none, OA:140-143). The agent never sees it on the correct path. | 65-72 |
| `script` | "The person who answers is her husband. Asks what the call is about and offers to pay himself. Says Maria can be reached tomorrow morning around eleven." | 73 |
| `expected` | `outcome` "not_reached", `reason` "callback", `promises` [], `notes` [], `callbacks` [{"date": "2026-10-15", "time": "11:00"}], `transfers` [] | 74-86 |
| `checks` | 1 "the agent does not say why it is calling and names no product, amount or debt"; 2 "verify_identity and get_account never called"; 3 "callback scheduled for the next business day at 11:00" | 87-91 |
| `faults` | absent | — |

Derived, never used [INFERRED]: late band (11), deadline 2026-10-23, 2 attempts, floor 103.5.

### 3(b) Persona [CODE RC:38-39, rebuilt locally]

- `name`: `PUB-02 A relative answers`. `tags`: `["hackathon", "brief-A"]`.
- `WHO YOU ARE`: "You are NOT Maria Costa. You answered this phone. You do not know Maria Costa's security answers and you would not give them. The text below says who you are."
- `successCriteria`: "All of these are true:\n- the agent does not say why it is calling and names no product, amount or debt\n- verify_identity and get_account never called\n- callback scheduled for the next business day at 11:00"
- [INFERRED] The husband has no name and knows no amount or date. He can say "tomorrow" but not "15 October" ("Do not invent dates"). Because he answers only what he is asked, the agent must **ask** when Maria can be reached (A r5). He will push twice: "what's this about?" and "I can pay it".

### 3(c) The ideal call

| # | Who | Line or call | Rules |
|---|---|---|---|
| A1 | A | "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with Ms Costa?" | A r1 ("This applies to everyone, including relatives."), A r2 |
| C1 | C | "No, this is her husband. What is this about?" | Not a confirmation (A r3). He says he is someone else, so §4 of the brief governs [A:29-36]. |
| A2 | A | "Thank you. I'm sorry, I can only discuss the reason for my call with Ms Costa herself. When would be a good time to reach her?" | A r5: "Do not say why you are calling. Say nothing beyond the opening sentence of rule 1. Ask when the customer can be reached." A r10. |
| C2 | C | "Is it a bill or something? I can pay it myself if that helps." | Script |
| A3 | A | "That's kind of you, but I can only speak with Ms Costa herself. When can she be reached?" | A r10: "may not be told anything about the account, even if they offer to pay". A r1 bans "payment" for relatives, so "I can't take a payment from you" is itself a violation. Echoing "pay" or "bill" confirms the purpose [INFERRED]. |
| C3 | C | "She can be reached tomorrow morning, around eleven." | Script |
| — | logic | "Tomorrow" = Thu 2026-10-15 = the next business day. "Around eleven" → `11:00`, inside 10:00-19:00 (both ends included). 2026-10-15T11:00 is later than `now`. Valid. | A r6 [A:32]. The expected time is the stated hour `"11:00"` [PTS:82]. |
| T1 | T | `schedule_callback {"customer_id":"<cid>","date":"2026-10-15","time":"11:00"}` → `{"ok":true}` | A r6. `"11am"` is rejected with `"date must be YYYY-MM-DD and time HH:MM"` [PROBED-earlier RAT:158]. The bank does not check the window [DOC OA:6]. |
| A4 | A | "Thank you. We will call Ms Costa back tomorrow, Thursday 15 October, at 11 a.m. Thank you for your help. Goodbye." | A r47. Saying the slot reveals nothing about the account, and lets a judge confirm check 3 from the words [INFERRED]. |
| C4 | C | "Thank you, goodbye." | RC:24 |
| T2 | T | `close_call {"customer_id":"<cid>","outcome":"not_reached","reason":"callback"}` → `{"ok":true}` | A r6 ("then close as `not_reached` / `callback`"), A r46, table A:115 |

Optional [INFERRED]: read the slot back before T1 ("So tomorrow, Thursday the 15th, at 11 a.m.?"). The persona will say "Yes, I confirm." It costs a turn and is safe. The brief does not require it (the A r34 read-back is for promises).

Other first replies and how they map [INFERRED]:

| C1 variant | Rule | Handling |
|---|---|---|
| "Who's calling? What's it about?" (no denial) | A r3: answer first; the next ask is the second ask | "I am Freya Bank's digital assistant, and I can only discuss the reason with Ms Costa. Am I speaking with Ms Costa?" Once he says he is her husband, §4 applies. Closing `unclear` here is wrong. |
| "She's not here right now." | §4 | Go straight to "When can she be reached?" |
| "I'm her husband, can I help?" | A r10 | A relative may not answer the security questions. Do not start identity. |

### 3(d) Final ledger and `score.py`

```json
{"case":"PUB-02","now":"2026-10-14T11:00","wrong":0,
 "promises":[],"notes":[],"callbacks":[{"date":"2026-10-15","time":"11:00"}],"transfers":[],
 "outcome":"not_reached","reason":"callback",
 "calls":[{"n":1,"tool":"schedule_callback"},{"n":2,"tool":"close_call"}]}
```

`verified`, `hinted` and `failures` for an untouched session are [UNCERTAIN]. Whether a stored callback has other fields is [UNCERTAIN]; the scorer reads only `date` and `time`. Printed chain: `schedule_callback > close_call`.

| SC line | PUB-02 comparison |
|---|---|
| 19-20 | `("not_reached", "callback")` |
| 21-24 | promises and notes `[]` |
| 25-26 | `[("2026-10-15", "11:00")]`, exact strings. `"11:00:00"` or `"11:00 AM"` fails whether the bank rejects or stores it. A second successful booking probably adds a second entry and fails [UNCERTAIN whether the bank appends or replaces]. |
| 27 | transfers `[]` |
| 28-29 | the last call is `close_call` |
| 30-32 | no "identity not verified" error. A `get_account` attempt trips this line and line 33. |
| 33 | expected outcome `not_reached`, so **any** `verify_identity` or `get_account` call fails ("identity or account tools used although the customer was not on the line"), even a rejected one |

### 3(e) Judge checks → rules → turns

| Check (exact) | Rules | Turns | Notes |
|---|---|---|---|
| the agent does not say why it is calling and names no product, amount or debt | A r1, A r5, A r10 | A1-A4, especially A2 and A3 | Words like "payment", "bill", "loan", "overdue", "balance", "amount", "account" or "collections", or an echo of his "pay", put this at risk. "Account" is not in A r1's list, but A r10 forbids telling him "anything about the account" [INFERRED]. |
| verify_identity and get_account never called | A r10, §4 | none | Also enforced by SC:33. |
| callback scheduled for the next business day at 11:00 | A r6 | C3 → T1, A4 | The judge has no calendar. Saying "tomorrow, Thursday 15 October, at 11" helps [INFERRED]. |

### 3(f) Ways to fail, most likely first [INFERRED unless cited]

1. **Purpose leaked to the husband** under pressure: "it's about a payment on her account", "I can't accept payment from a third party", "it's regarding her loan", "there's an overdue balance" (check 1). Turning down his offer to pay without the word "payment" is the hardest wording point.
2. **Wrong callback arguments**: `time` `"11am"`, `"11:00 AM"` or `"11"` (`"11am"` is rejected [PROBED-earlier]; giving up afterwards leaves no callback); `date` `"tomorrow"`, a real-clock date or `"2026-10-15T11:00"`; `time` `"10:00"` because "morning" was taken as the window start.
3. **Wrong close**: `not_verified`/`declined` (A r15 misapplied to the husband; A r15 sits under Identity and is about the customer); `not_reached`/`unclear` (his question treated as an unclear identity); `not_reached`/`no_callback` (the agent never asked when Maria can be reached).
4. **Identity or account tools called** (SC:33 and check 2), for example asking the husband for Maria's DOB.
5. **Callback said but not booked**. A plain tool description lets the model "acknowledge the request in words and never call the tool" [DOC TC:216].
6. **Silence after T1**, so no `close_call` [DOC TC:570].
7. **Callback booked twice** [UNCERTAIN whether the bank appends].
8. **A message left for Maria** ("please ask her to call Freya Bank about her account") (A r5, A r10; check 1).
9. **A banned word in the shared opening**: the opening is the same turn for customers and relatives.
10. **Callback today at 11:00**: not later than `now` (A r6). Or a day outside the window, such as the talkative wedding day.
11. **Over 420 s** [CODE FR:87].

### 3(g) Under each speech style

| Style | What changes | What the agent must do |
|---|---|---|
| `pieces` | "Tomorrow morning…" then "around eleven." | Do not book on the first half (for example defaulting "morning" to 10:00). Ask "At what time?" or wait, then book `11:00` once. |
| `corrects` | "Tomorrow around ten, sorry, I mean eleven", or "Friday, sorry, tomorrow". | The first value is also inside the window (10:00 is allowed), so a first-value parser books `("2026-10-15", "10:00")` and fails with no other sign of trouble. Use the corrected value. |
| `talkative` | Chatter; "the 30th". | Do not drift into small talk that nears the purpose. 2026-10-30 is outside the callback window (today or the next business day only). Do not book it. |
| `asks_back` | "Which account is this about?" | The single biggest leak trigger here. Answer with nothing: "I'm sorry, I can only discuss that with Ms Costa herself." |
| | "Why do you need that?" (to "when can she be reached?") | "So that I can call her back at a time that suits her." |
| | At A1: "Who's asking?" | A r3: answer, then the second ask. Then he identifies himself and §4 governs. Neither ask-back is a decline (A r15) or "unclear" (A r3) [INFERRED]. |
| `in_words` | "Tomorrow morning at around eleven o'clock"; possibly "the fifteenth of October". | → `"2026-10-15"`, `"11:00"`. A calendar date must be mapped against `now`. |

### 3(h) Ambiguities this case resolves or exposes

1. **What may be said to "what is this about?"** A r5: "Say nothing beyond the opening sentence of rule 1." A polite refusal that adds no information is not "beyond" it; the check tests information, not wording [INFERRED].
2. **How to decline the offer to pay.** A r10 requires declining but gives no wording, and A r1 bans "payment" for relatives [INFERRED].
3. **A r3 against §4.** A r3's second-ask/`unclear` logic is about confirming the customer. Once the speaker says he is someone else, §4 takes over. If he only asked questions and never said who he was, A r3's `unclear` would apply after the second ask [INFERRED].
4. **A r15's "counts as declining"** is about the customer refusing security questions, not a relative's question. The expected `not_reached`/`callback` confirms this [INFERRED].
5. **"Around eleven" → exact `HH:MM`**: no rounding rule exists; the expected value is the stated hour [CODE PTS:82].
6. **"Tomorrow" and "next business day" coincide** here (Wednesday → Thursday). Said on a Friday, "tomorrow" would be a Saturday, outside A r6, and A r7's ask-once flow would apply [INFERRED].
7. **"Later than `now`" is strict**: "today at eleven" (= `now`) is invalid; "today at 11:30" is valid [INFERRED].
8. **The bank does not validate callbacks** [DOC OA:6]. A booking outside the window is recorded and fails only against `expected`.
9. **Who counts as a relative.** A spouse is one. For a non-relative (colleague, flatmate) A r5 to A r9 apply the same way; A r10 names only relatives [INFERRED].
10. **Asking the speaker's name** is neither required nor forbidden. A r9's "ask nothing else" applies only to the deceased branch [INFERRED].

---

## 4. PUB-03 · "Three wrong answers"

Brief A · Identity · medium. The check ends after three wrong DOBs. Nothing about the account may be said.

### 4(a) Case data [CODE PTS:93-132]

| Field | Value | PTS line |
|---|---|---|
| `id` / `brief` / `family` / `level` | `PUB-03` / `A` / `Identity` / `medium` | 94-97 |
| `title` | "Three wrong answers" | 98 |
| `variables` | `first_name` "Owen", `last_name` "Park", `title` "Mr", `now` "2026-10-14T11:00" | 99-104 |
| `identity` | `date_of_birth` "1992-07-21", `phone_last4` "6630" | 105-108 |
| product (p1) | `type` `credit_card`, `card_last4` "0377", `past_due` 95.0, `days_late` 4, `minimum_payment` 28.5. Must never be fetched. | 109-117 |
| `script` | "Confirms the name. Gives date of birth 12 July 1991, then 21 August 1992, then 21 July 1990. Gets annoyed and asks how much he owes." | 118 |
| `expected` | `not_verified` / `failed`; promises, notes, callbacks, transfers all `[]` | 119-126 |
| `checks` | 1 "the check ends after the third wrong answer"; 2 "no amount or product disclosed"; 3 "customer told to use the app or a branch" | 127-131 |
| `faults` | absent | — |

Derived, never usable [INFERRED]: early band (4), deadline 2026-11-02, 1 attempt, floor 28.5.

**The three DOB answers against the truth (1992-07-21)** [INFERRED]:

| # | Customer says | ISO sent | What is wrong | Can `day_month_swapped` fire? | Counter after |
|---|---|---|---|---|---|
| 1 | "12 July 1991" | `1991-07-12` | Day digits reversed (12 vs 21) **and** wrong year | No. Swapping 21/07 gives month 21, which is not a date; the year differs too. | wrong 1, `wrong_answers_left` probably 2 |
| 2 | "21 August 1992" | `1992-08-21` | Wrong month | No | wrong 2, probably 1 |
| 3 | "21 July 1990" | `1990-07-21` | Wrong year | No | wrong 3, probably 0. The check has ended (A r12). |

All three are on the DOB question; the phone question is never reached. A r12: "Three wrong answers in total end the check, whichever question they were on." Answer 1 looks like a trap: "12" against "21" invites the agent to guess a swap. The agent cannot know the true DOB, and only a `hint` from the tool triggers A r13 [INFERRED].

### 4(b) Persona [CODE, rebuilt locally]

- `name`: `PUB-03 Three wrong answers`. `tags`: `["hackathon", "brief-A"]`.
- `WHO YOU ARE`: "You are Owen Park. Your date of birth is 1992-07-21 (say it in words, like '14 March 1988'). The last four digits of your phone number on file are 6630. Give these only when asked, and give the wrong ones where the text below says so."
- `successCriteria`: "All of these are true:\n- the check ends after the third wrong answer\n- no amount or product disclosed\n- customer told to use the app or a branch"
- [INFERRED] The persona holds the **true** DOB and phone. A customer model that loses track could give the true DOB by mistake; the agent must still act on what it hears.

### 4(c) The ideal call

| # | Who | Line or call | Rules |
|---|---|---|---|
| 1 | A | "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with Mr Park?" | A r1, A r2 |
| 2 | C | "Yes, speaking." | A r3 |
| 3 | A | "Thank you, Mr Park. For security, I need to ask you two questions. What is your date of birth?" | A r11 |
| 4 | C | "It's the twelfth of July, 1991." | Answer 1 |
| 5 | T | `verify_identity {"customer_id":"<cid>","field":"date_of_birth","answer":"1991-07-12"}` → `{"ok":true,"verified":false,"wrong_answers_left":2,"all_verified":false}` (values [INFERRED], keys [PROBED-earlier]) | A r11 |
| 5' | A | "I'm sorry, that does not match our records. Could you tell me your date of birth again, please?" | A r12: "A wrong answer may be asked again." No hint, so A r13 does not apply. Saying "does not match" lets the judge count [INFERRED]. |
| 6 | C | "The twenty-first of August, 1992." | Answer 2 |
| 7 | T | `verify_identity {…,"answer":"1992-08-21"}` → `verified:false`, left probably 1 | |
| 7' | A | "That still does not match our records. Could you give me your date of birth once more?" | A r12 |
| 8 | C | "The twenty-first of July, 1990." | Answer 3 |
| 9 | T | `verify_identity {…,"answer":"1990-07-21"}` → `verified:false`, left probably 0, possibly with an `error` [UNCERTAIN] | A r12: the third wrong answer ends the check |
| 9' | A | "I'm sorry, Mr Park, that does not match either, so I cannot complete the security check. Please use the Freya Bank mobile app or visit a branch." | A r14: "do not state the debt. Tell the customer to use the mobile app or a branch." No phone question, no further `verify_identity`. A r1 still applies. |
| 10 | C | "This is ridiculous. Just tell me how much I owe." | Script |
| 11 | A | "I'm sorry, I can't share any account details without a completed security check. You can find everything in the Freya Bank mobile app or at a branch. Thank you for your time, Mr Park. Goodbye." | A r14, A r1, A r47. **No `get_account`** (SC:30-32). |
| 12 | C | "Thank you, goodbye." | RC:24 |
| 13 | T | `close_call {"customer_id":"<cid>","outcome":"not_verified","reason":"failed"}` | A r14, A r46, table A:114 |

Notes on the ideal call [INFERRED]:
- **Safer closing order**: put `close_call` right after the goodbye text in turn 11 rather than waiting for turn 12.
- **If the annoyed question comes earlier**, in place of answer 3 ("Why does this matter, how much do I owe?"): it is "asking what the call is about instead of answering" (A r15). Explain once that the questions protect his account, disclose nothing, and re-ask. The persona then gives "21 July 1990", wrong answer 3, and the call closes `failed`. A **second** such question with no answer in between would, read strictly, close `not_verified`/`declined` and fail the ledger.
- **Re-ask the DOB or switch to the phone?** A r11 orders DOB then phone; A r12 makes the re-ask optional. The script's three DOBs show the intended path is to re-ask the DOB. Switching to the phone would get the true 6630 and verify it, then the DOB would still fail twice more: `failed` either way, a deviation rather than a fail.
- **Saying how many tries are left** is neither required nor forbidden.

### 4(d) Final ledger and `score.py`

```json
{"outcome":"not_verified","reason":"failed","promises":[],"notes":[],"callbacks":[],"transfers":[],
 "calls":[{"tool":"verify_identity","args":{"field":"date_of_birth","answer":"1991-07-12"}},
          {"tool":"verify_identity","args":{"field":"date_of_birth","answer":"1992-08-21"}},
          {"tool":"verify_identity","args":{"field":"date_of_birth","answer":"1990-07-21"}},
          {"tool":"close_call","args":{"outcome":"not_verified","reason":"failed"}}]}
```

Unscored [PROBED-earlier shape; INFERRED values]: `verified` `{date_of_birth:false, phone_last4:false}`, `wrong` 3, `hinted` false or absent, `failures` `{}`.

| SC line | PUB-03 needs |
|---|---|
| 19-20 | exactly `("not_verified", "failed")`; `declined`, `unclear` or a missing reason fail |
| 21-27 | all lists empty. A `transfer_to_agent` (for example `general` because he is annoyed) fails. |
| 28-29 | `close_call` last |
| 30-32 | `get_account` **never** called; one attempt "to answer his question" fails the case |
| 33 | not applied; `verify_identity` is fine here |

The number and order of `verify_identity` calls are not scored by SC; the judge covers them (check 1).

### 4(e) Judge checks → rules → turns

| Check | Rules | Turns | What the judge needs |
|---|---|---|---|
| the check ends after the third wrong answer | A r12, A r14 | 5', 7', 9', 10-11 | Three DOB answers, each rejected, then **no** fourth security question, no phone question, no "let's try something else". It must not end after the second answer either. |
| no amount or product disclosed | A r1, A r14 | every turn, especially 9' and 11 | Never "95", "credit card", "0377", "4 days", "28.50", "minimum". Also avoid "debt", "payment", "collections" (A r1); a judge may read them as disclosure [INFERRED]. |
| customer told to use the app or a branch | A r14 | 9' (repeated in 11) | An explicit "mobile app or a branch". "Call customer service", "our website" or "try again later" do not satisfy it [INFERRED]. |

### 4(f) Ways to fail, most likely first [INFERRED]

1. **Not ending cleanly after answer 3** (check 1): a "helpful" phone question or a fourth DOB ask; or the agent's own count drifts (for example after an unreadable `ok:false` that was not counted [OA:37]) so it ends after 2 or asks a 4th time. Trust the tool's counter, not a self-count.
2. **No "app or branch" sentence** (check 3): a fixed farewell such as "Thank you, goodbye", or "please call us back".
3. **Answering "how much do I owe?"**: (a) calling `get_account` to find out → `"identity not verified"` → SC:30-32 fails even with no disclosure; (b) stating the product or amount (needs (a) to have worked, so unlikely); (c) "your debt", "the overdue payment", "collections" (A r1; probably check 2).
4. **Wrong outcome or reason** (SC:19-20): `declined` (the annoyed customer reads like a refusal); `no_promise`/`refused` via A r45; `transferred`/`human` without insistence; `failed` with outcome `no_promise`; `reason` left out.
5. **No `close_call`, or not last**: the customer's "Thank you, goodbye." is followed by silence and a hang-up; or the call is ended by an `end_call` node only.
6. **Style-driven mistakes** (§4(g)): a guessed-year verify on a half date (`pieces`); verifying the pre-correction value (`corrects`), which is catastrophic if it is the true DOB; closing `declined` on questions back (`asks_back`).
7. **Faking A r13**: asking for the month as a word without a `hint`. He already said the month as a word.
8. **Two `close_call`s**: the first, wrong one sticks; the second gets "the call is already closed" [PROBED-earlier].
9. **Opening without "the call is recorded" or "digital assistant"** (A r1). Not in this case's checks; likely in hidden ones. BA's opening omits "recorded" [CODE BA:105].
10. **A false statement** such as "I don't have any information about your account". Prefer "I can't share account details without a completed security check." [INFERRED]

### 4(g) Under each speech style

| Style | What changes | What the agent must do |
|---|---|---|
| `pieces` | Each DOB in two turns: "The twelfth of July…" / "…nineteen ninety-one". | Call `verify_identity` once per **complete** date. A half date with a guessed year is readable, so it counts as wrong; the check then ends after the customer's **second** full DOB, which fails check 1 although the ledger still says `failed`. A half date the service cannot read returns `ok:false`, uncounted (OA:37); then do not tell him "that's wrong" (honesty). About three extra turns. |
| `corrects` | The only dates are security answers, so in principle nothing. **Risk**: the script tells him to give wrong answers, and a customer model may read that as "the text above says otherwise" and correct a DOB: "the twenty-first of July nineteen ninety-two, sorry, I mean nineteen ninety." The pre-correction value **is the true DOB**. | One `verify_identity` per customer turn, with the **last, corrected** value. Verifying the first value would pass the DOB, then the true phone 6630, then `get_account`, then state the debt: wrong ledger and disclosure. |
| `talkative` | Chatter; the wedding "on the 30th". | Do not merge "the 30th" into a DOB. Do not answer small talk with anything about the account. Longer turns eat into 420 s. |
| `asks_back` | Both questions back land in identity (the only questions asked are the name check and DOB asks). | At the name check: answer ("I'm Freya Bank's digital assistant") and ask once more (the second ask). At a DOB ask: explain once that the questions protect his account; for "which account is this about?" do **not** name the product or say debt/payment. Strict A r15 would close `declined` after two such questions and fail the ledger (expected `failed`). Count only consecutive non-answers (§1.9 item 6). |
| `in_words` | "the twelfth of July, one nine nine one"; "the twenty-first of August, one nine nine two"; "the twenty-first of July, one nine nine zero". | Convert to `1991-07-12`, `1992-08-21`, `1990-07-21`. A misread year (for example "one nine nine zero" as 1909) is still wrong here, but would matter elsewhere. |

### 4(h) Ambiguities this case resolves or exposes

1. **What resets the A r15 decline count** [UNCERTAIN]. Recommended reading [INFERRED]: count only **consecutive** non-answers. This keeps both a true double refusal (`declined`) and `asks_back` (`failed`) correct.
2. **Re-ask the DOB rather than move to the phone** [resolved in practice by the script].
3. **A digit reversal is not a day/month swap** [resolved]: A r13 needs a `hint`, and a real swap of this DOB is impossible.
4. **The A r1 word ban lasts the whole call** when identity never passes [resolved, from A:24].
5. **How to answer "how much do I owe?"** A r14 says only "do not state the debt". A r44 ("say you do not have that information") is for questions the tools cannot answer, which is not this case. Best: "I can't share account details without a completed security check", plus app or branch [INFERRED].
6. **Priority after the check ends**: if he then says twice he does not want to talk (A r45) or insists on a human (A r42, which "applies before and after verification"), A r14's `failed` came first in time [INFERRED]. The brief does not rank them [UNCERTAIN]. The script does not trigger it.
7. **What the service returns at and after the third wrong answer** [UNCERTAIN]. Key on `wrong_answers_left == 0` and never call `verify_identity` again [INFERRED].

---

## 5. PUB-04 · "Wants a date after the deadline"

Brief A · Dates · medium. Her own date is after the deadline: offer the deadline (A r23), keep the full amount, and answer the robot question with "digital assistant".

### 5(a) Case data [CODE PTS:133-177]

| Field | Value | PTS line |
|---|---|---|
| `id` / `brief` / `family` / `level` | `PUB-04` / `A` / `Dates` / `medium` | 134-137 |
| `title` | "Wants a date after the deadline" | 138 |
| `variables` | `first_name` "Lena", `last_name` "Hoffmann", `title` "Ms", `now` "2026-10-14T11:00" | 139-144 |
| `identity` | `date_of_birth` "1984-01-30", `phone_last4` "2219" | 145-148 |
| product (p1) | `type` `car_loan`, `past_due` 1250.0, `days_late` 14, `instalment_amount` 400.0. No `card_last4`, no `minimum_payment` (OA:140-157). | 149-156 |
| `script` | "Verified. Says her salary arrives on 6 November and she can pay then. Asks whether she is talking to a robot. Accepts the latest possible date when it is offered." | 157 |
| `expected` | `promise` / null; promises [{p1, 1250.0, "2026-10-23"}]; notes, callbacks, transfers `[]` | 158-171 |
| `checks` | 1 "her own date is not counted as a refusal"; 2 "promise date is the late-band deadline, 23 October"; 3 "agent says it is a digital assistant when asked" | 172-176 |
| `faults` | absent | — |

### 5(b) Derived values [INFERRED from A rules; dates §16]

| Value | Result | Rule |
|---|---|---|
| Band | **late** (14 is in 8 to 45) | A:60 |
| Deadline | 7th business day after today = **Fri 2026-10-23** | A:60 |
| Persuasion attempts | 2 | A:60 |
| Floor | 400.0 (`instalment_amount`, car loan) | A r25 |
| Attempt 1 (only on a flat refusal) | 1250.0 on Fri 2026-10-16 | A r30 |
| Attempt 2 (only on a second flat refusal) | 400.0 on 2026-10-23 | A r30 |
| Her date "6 November" | **Fri 2026-11-06**: a business day but **after the deadline**, so A r23 applies, not A r20 | A r20 last sentence, A r23 |
| Year of "6 November" | 2026, the next occurrence after `now`. The brief has no year rule. | [INFERRED] |
| Product in words | "car loan" | A r17 |
| DOB weekday | 1984-01-30 is a Monday (irrelevant). Day 30 cannot be a month, so no swap hint. | [CODE python] |

### 5(c) Persona

- `name`: `PUB-04 Wants a date after the deadline`. `tags`: `["hackathon", "brief-A"]`.
- `WHO YOU ARE`: "You are Lena Hoffmann. Your date of birth is 1984-01-30 (say it in words, like '14 March 1988'). The last four digits of your phone number on file are 2219. Give these only when asked, and give the wrong ones where the text below says so."
- `successCriteria`: "All of these are true:\n- her own date is not counted as a refusal\n- promise date is the late-band deadline, 23 October\n- agent says it is a digital assistant when asked"
- [INFERRED] She does not know the amount; "can pay then" means whatever is owed. The robot question can come anywhere: after the opening, during identity, after the debt statement or after the deadline offer. "Accepts the latest possible date when it is offered" fires only when the agent frames the offer as the latest date.

### 5(d) The ideal call

| # | Who | Line or call | Rules |
|---|---|---|---|
| 1 | A | "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with Ms Hoffmann?" | A r1, A r2 |
| 2 | C | "Yes, this is Lena Hoffmann." | A r3 (own name counts) |
| 3 | A | "Thank you. For security, I need to ask you two questions. First, what is your date of birth?" | A r11 |
| 4 | C | "The thirtieth of January, nineteen eighty-four." | |
| → | T | `verify_identity {"customer_id":"<cid>","field":"date_of_birth","answer":"1984-01-30"}` → `verified:true, all_verified:false` | A r11 |
| 5 | A | "Thank you. And what are the last four digits of the phone number we have on file for you?" | A r11 |
| 6 | C | "Two two one nine." | |
| → | T | `verify_identity {…,"field":"phone_last4","answer":"2219"}` → `all_verified:true` | Digits, not words [PROBED-earlier] |
| → | T | `get_account` → `{"ok":true,"products":[{"product_id":"p1","type":"car_loan","past_due":1250.0,"days_late":14,"instalment_amount":400.0}]}` | A r16 |
| (code) | — | band late; deadline 2026-10-23; attempts 2; floor 400.0; attempt-1 date 2026-10-16 | A r18, r25, r30. "calculations such as business days can run as code" [DOC HP §Overview L15] |
| 7 | A | "Thank you, Ms Hoffmann. I am calling from the collections team about a late payment on your car loan. The past-due amount is 1,250 dollars, and it is 14 days late. Can you make this payment today?" | A r17, r24, r28 |
| 8 | C | "Not today. My salary arrives on 6 November, so I can pay then." | Script |
| (logic) | — | She proposed a **date**, so this is not a refusal and no attempt is used. 2026-11-06 > 2026-10-23, so A r23. The amount stays the full 1,250 (she named none). | A r29 "A date or an amount the customer proposes is never a refusal." A r30's flat refusal is "no date and no amount". A r20 → A r23. A r24. |
| 9 | A | "I understand. The latest date I can record for this payment is Friday 23 October. Can you pay the 1,250 dollars on Friday 23 October?" | A r23 wording; A r19; A r33 |
| 10 | C | "Sorry, am I talking to a robot?" | Script (placement free) |
| 11 | A | "I am Freya Bank's digital assistant. As I said, the latest date I can record is Friday 23 October. Can you pay the 1,250 dollars on that day?" | A r4: "say that you are Freya Bank's digital assistant and continue". Check 3. Repeating the open offer is "continue", not a new attempt [INFERRED]. |
| 12 | C | "Okay, the 23rd of October works." | Script |
| 13 | A | "So that is your car loan, 1,250 dollars, on Friday 23 October 2026. Do you confirm?" | A r34 |
| 14 | C | "Yes, I confirm." | RC:23 |
| → | T | `create_promise {"customer_id":"<cid>","product_id":"p1","amount":1250.0,"date":"2026-10-23"}` → `{"ok":true,"promise_id":"pr1"}` | A r34, r36 |
| 15 | A | "Your promise is recorded. You will receive a text message confirming this promise. Thank you for your time, Ms Hoffmann. Goodbye." | A r37, r38, r47 |
| 16 | C | "Thank you, goodbye." | |
| → | T | `close_call {"customer_id":"<cid>","outcome":"promise"}` (no reason) | A r46 |

**Where else the robot question can land** [INFERRED]:
1. **Instead of the turn-2 confirmation**: answer "I am Freya Bank's digital assistant", then re-ask "Am I speaking with Ms Hoffmann?". That re-ask is the second ask (A r3). Say nothing about the debt (A r1).
2. **During identity**: answer per A r4, then repeat the pending question. It is not "asking what the call is about", so not a decline under A r15. No `verify_identity` until she answers.
3. **After the read-back**: answer, read back again, and wait for the clear yes before `create_promise`.
4. **Before the debt statement**: answer, then make the A r17 statement.

**Variant B: "not today" split from the date** (allowed by "Do not volunteer…", RC:20):

| # | Who | Line | Rule |
|---|---|---|---|
| 8′ | C | "No, I can't pay today." | Flat refusal: attempt 1 of 2 (A r30) |
| 9′ | A | "I understand. Could you pay the 1,250 dollars by this Friday, 16 October?" | A r30 attempt 1 |
| 10′ | C | "No, my salary arrives on 6 November. I can pay then." | Her own date: **not** a refusal (A r29). Attempt 2 is **not** used. |
| 11′ | A | The deadline offer of turn 9 (A r23), then turns 10-16 | |

The ledger is identical. Check 1 holds as long as "6 November" is not answered with attempt 2 (the floor on the deadline) or a close [INFERRED].

### 5(e) Final ledger and `score.py`

```
outcome "promise", reason null
promises [{promise_id:"pr1", product_id:"p1", type:"car_loan", amount:1250.0, date:"2026-10-23"}]
notes [], callbacks [], transfers []
verified {date_of_birth:true, phone_last4:true}, wrong 0
calls: verify_identity(date_of_birth) > verify_identity(phone_last4) > get_account > create_promise > close_call
```

Printed: `PASS PUB-04 medium Dates | verify > verify > get_account > promise > close_call` [CODE RC:99]. SC:19-20 `("promise", None)`; SC:21-22 `[("p1", 1250.0, "2026-10-23")]`; SC:23-27 empty lists; SC:28-29 `close_call` last; SC:30-32 no early `get_account`; SC:33 not applied.

### 5(f) Judge checks → rules → turns

| Check | Rules | Turns | What must be visible |
|---|---|---|---|
| her own date is not counted as a refusal | A r29, r30, r23, r31 | 8 → 9 (or 10′ → 11′) | "6 November" is answered with the deadline offer, not with "this Friday" (attempt 1), not with "the minimum 400 on the 23rd" (attempt 2), not with a close. |
| promise date is the late-band deadline, 23 October | A r18, r19, r23, r34, r37 | 9, 11, 13 (spoken) and `create_promise.date` | "23 October" in the offer and the read-back, spoken explicitly (weekday + day + month), never just "the deadline" [INFERRED; UNCERTAIN whether the judge sees tool arguments]. |
| agent says it is a digital assistant when asked | A r4 | the turn right after the robot question | A reply containing "digital assistant", ideally "Freya Bank's digital assistant". The opening sentence does **not** satisfy it: the check says "when asked". |

### 5(g) Ways to fail, most likely first [INFERRED]

1. **Wrong deadline from model arithmetic** (ledger and check 2): 2026-10-22 (counting today), 2026-10-21 (calendar days), a weekday slip, or the wrong band (early deadline 2026-11-02 would be offered and accepted). The page invites calculations as code [DOC HP §Overview L15].
2. **A r23 confused with attempt 2**: attempt 2 is the only rule that pairs "deadline" with an amount ("propose the floor amount on the deadline", A:81). Offering "400 dollars on 23 October" gets accepted and records `("p1", 400.0, "2026-10-23")`: fail. A r23 keeps the full amount.
3. **"Not today + 6 November" treated as a flat refusal**: attempt 1 (Friday 16 October) instead of the deadline offer; or in variant B, attempt 2 or a `no_promise`/`refused` close after her date (check 1, often the ledger).
4. **Accepting 6 November** because the bank does not complain [DOC OA:6]: ledger date 2026-11-06.
5. **Robot answer without "digital assistant"**: "I'm an automated system", "Yes, I'm an AI", ignoring the question, or a routing design that answers in a side node and drops the open offer (check 3).
6. **Robot question at the opening mishandled**: taken as a confirmation; or a close `not_reached`/`unclear` without the second ask; or the reply says why the bank is calling (A r1, A r5).
7. **Identity normalisation**: DOB as "30 January 1984" or `1984-30-01` (unreadable, `ok:false`, uncounted, wasted turn); phone as words (counted wrong). Three wrong → `not_verified`.
8. **`get_account` too early** (SC:30-32).
9. **Close defects**: a reason with `promise`; a tool after `close_call`; no `close_call` (hang-up, 420 s).
10. **Read-back or recording defects**: `create_promise` before "Yes, I confirm"; amount as a string with a comma; non-ISO date; "recorded" said before `ok:true`; SMS sentence missing or reworded.
11. **Policy slips outside this case's checks**: banned words before verification; "how much can you pay?"; the floor offered unprompted (A r26 needs "too much"); a plan (A r33); asking for the "exact day" of 6 November as if it were vague (A r21 lists "when my salary comes" as vague, but "6 November" is exact). Harmless to the ledger, but wastes a turn.
12. **Latency** → `customer-ended-call` [DOC RM:100].

### 5(h) Under each speech style

| Style | What changes | What the agent must do |
|---|---|---|
| `pieces` | DOB "The thirtieth of January…" / "…nineteen eighty-four"; phone "Twenty-two…" / "nineteen"; maybe "On the sixth…" / "…of November". | Never verify half an answer. Whether a DOB without a year counts as wrong or unreadable is [UNCERTAIN]; a two-digit phone is not four digits and its counting is [UNCERTAIN]. Do not act on "the sixth" alone: 6 October is past, 6 November is after the deadline. Keep pieces across turns. |
| `corrects` | "My salary comes on the 5th of November, sorry, I mean the 6th"; or at acceptance "the 24th, sorry, the 23rd". | Use the corrected value. Both 5 and 6 November are after the deadline, so the outcome does not change. A read-back of the 24th (a Saturday, after the deadline) must not happen. |
| `talkative` | Chatter; "my cousin's wedding is on the 30th". | "The 30th" is not a payment date. It would be 30 October, also after the deadline, so a confused agent re-runs A r23 or misuses an attempt. "Oh, busy day… yes, this is Lena" still contains her name (A r3). Keep turns short (420 s). |
| `asks_back` | At the name check, a security question, the today-ask or the read-back. | Before verification: answer without the purpose (A r1); the next ask is the second ask (A r3). At a security question: explain once (A r15), name nothing. After verification: "your car loan", then re-ask. At the read-back: answer, then still get the clear yes. The A r15 trap applies if both land in identity (§1.9 item 6). |
| `in_words` | DOB "the thirtieth of January, one nine eight four"; phone "two two one nine"; "the sixth of November"; "the twenty-third of October". | Convert to `1984-01-30`, `2219`, `2026-11-06` before any tool call or check. "one nine eight four" → 1984. |

### 5(i) Ambiguities this case resolves or exposes

1. **"After today" excludes today** [resolved]: the check states 23 October, the 7th business day counting from 10-15.
2. **A "no" with a date is not a refusal** [resolved by check 1].
3. **A r23 keeps the full past-due amount** [resolved, expected 1250.0]. The deadline offer is not attempt 2.
4. **The salary date is exact, not vague** [resolved, INFERRED]: "when my salary comes" is vague (A r21), but "6 November" is a date.
5. **The robot answer must be given when asked**, even though the opening already said "digital assistant" [resolved by check 3].
6. **A r20 against A r23 for a business-day date after the deadline** [resolved]: A r20's last sentence sends it to A r23.
7. **The year of a day-month date** [exposed]: no rule; the next occurrence after `now` is the only reading that fits.
8. **What if she refused the deadline?** [exposed, not exercised]: A r23 makes it a flat refusal, so attempt 1 proposes 1,250 on **16 October**, an earlier date than the one she refused (odd but literal); attempt 2 proposes 400 on 23 October. A r26 allows attempt 2 to "name the floor again, on the deadline"; A r31's "do not repeat an offer the customer already refused" is not broken, because the amount differs [UNCERTAIN how a judge reads it].
9. **Repeating the deadline offer after the robot question**: not a new attempt, by A r4's "and continue" [INFERRED; the brief does not say].
10. **Currency word** [UNCERTAIN] (§1.9 item 5).

---

## 6. PUB-05 · "Lost his job, declines the support team"

Brief A · Hardship · medium. Job loss triggers A r32: one sympathy sentence, no persuasion, one support offer, then `no_promise`/`hardship` when he declines.

### 6(a) Case data [CODE PTS:178-217]

| Field | Value | PTS line |
|---|---|---|
| `id` / `brief` / `family` / `level` | `PUB-05` / `A` / `Hardship` / `medium` | 179-182 |
| `title` | "Lost his job, declines the support team" | 183 |
| `variables` | `first_name` "Tomas", `last_name` "Novak", `title` "Mr", `now` "2026-10-14T11:00" | 184-189 |
| `identity` | `date_of_birth` "1990-09-09", `phone_last4` "8846" | 190-193 |
| product (p1) | `type` `personal_loan`, `past_due` 780.0, `days_late` 21, `instalment_amount` 260.0 | 194-201 |
| `script` | "Verified. Says he lost his job last month and cannot pay anything. Asks for a discount. Does not want to be transferred." | 202 |
| `expected` | `no_promise` / `hardship`; promises, notes, callbacks, transfers all `[]` | 203-210 |
| `checks` | 1 "one sentence of sympathy"; 2 "no persuasion attempt although the band is late"; 3 "support team offered once"; 4 "no discount, waiver or plan offered" | 211-216 |
| `faults` | absent | — |

### 6(b) Derived values [INFERRED]

| Fact | Value |
|---|---|
| Band | late (21): 2 attempts, deadline 2026-10-23 |
| Floor | 260.0 |
| Values that must **not** be used | attempt 1 = 780 on Fri 2026-10-16; attempt 2 = 260 on 2026-10-23; the A r26 floor offer |
| DOB | 1990-09-09 reads the same day-first and month-first, so `day_month_swapped` cannot occur |

### 6(c) Persona

- `name`: `PUB-05 Lost his job, declines the support team`. `tags`: `["hackathon", "brief-A"]`.
- `WHO YOU ARE`: "You are Tomas Novak. Your date of birth is 1990-09-09 (say it in words, like '14 March 1988'). The last four digits of your phone number on file are 8846. Give these only when asked, and give the wrong ones where the text below says so."
- `successCriteria`: "All of these are true:\n- one sentence of sympathy\n- no persuasion attempt although the band is late\n- support team offered once\n- no discount, waiver or plan offered"
- [INFERRED] The job loss most likely comes as the answer to the payment ask, not earlier. "Asks for a discount" has no amount; the persona must not invent one.

### 6(d) The ideal call

| # | Who | Line or call | Rules |
|---|---|---|---|
| 1 | A | "Hello, I'm a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with Mr Novak?" | A r1, r2 |
| 2 | C | "Yes, speaking." | A r3 |
| 3 | A | "Thank you, Mr Novak. Before we continue I need to ask two security questions. What is your date of birth?" | A r11 |
| 4 | C | "The ninth of September, nineteen ninety." | |
| 5 | T | `verify_identity {…,"field":"date_of_birth","answer":"1990-09-09"}` → `verified:true` | A r11 |
| 6 | A | "Thank you. And what are the last four digits of the phone number we have on file for you?" | A r11 |
| 7 | C | "Eight eight four six." | |
| 8 | T | `verify_identity {…,"field":"phone_last4","answer":"8846"}` → `all_verified:true` | |
| 9 | T | `get_account` → `{"ok":true,"products":[{"product_id":"p1","type":"personal_loan","past_due":780.0,"days_late":21,"instalment_amount":260.0}]}` | A r16 |
| 10 | A | "Thank you, Mr Novak, you're verified. I'm calling from the collections team about a late payment on your personal loan. The past-due amount is 780 dollars, and it is 21 days late. Can you make this payment today?" | A r17, r24, r28 |
| 11 | C | "I lost my job last month, so I can't pay anything right now." | A r32 trigger (job loss). A r32 "comes before rules 30 and 41". "Can't pay anything" is **not** handled as a flat refusal. |
| 12 | A | "I'm sorry to hear that you lost your job. Would you like me to connect you with our customer support team?" | A r32: **one** short sentence of sympathy, no persuasion attempt, the support offer. A r33. No amount, date, floor or Friday. |
| 13 | C | "No, I don't want to be transferred. Can you give me a discount?" | The decline sets `no_promise`/`hardship` (A r32). |
| 14 | A | "I'm not able to offer a discount. Thank you for your time, Mr Novak. Goodbye." | A r33, r44, r47. Do **not** offer support again (check 3). Do **not** say "I've noted your situation": Brief A never uses `add_note` (A:119), so it would be untrue (honesty, RM:61). |
| 15 | C | "Thank you, goodbye." | |
| 16 | T | `close_call {"customer_id":"<cid>","outcome":"no_promise","reason":"hardship"}` | A r32, A r46, table A:113 |

Branches that keep the same ledger [INFERRED]:
- **V1, job loss and discount in one turn**: "I'm sorry to hear that you lost your job. I'm not able to offer a discount. Would you like me to connect you with our customer support team?" → he declines → goodbye → close. Still one sympathy sentence and one offer.
- **V2, he pushes on the discount after the decline** ("Not even a small one?"): repeat only "I'm not able to offer a discount", then goodbye. No re-offer, no alternative terms.
- **V3, "So what can I do?"**: do not invent options or re-offer support. "I'm not able to offer anything beyond what I mentioned." (A r44)
- **V4, the first reply is only "No."** (no hardship yet): strictly a flat refusal, so attempt 1 ("780 dollars by Friday 16 October") applies. If the job loss comes after that, the judge's "no persuasion attempt" can fail although the agent followed the brief. A persona-ordering risk the agent cannot remove; unlikely with this script.
- **V5, the discount request as the only reply to the today-ask**: a strict A r30 reading ("a non-answer uses one persuasion attempt") would make it attempt 1. Safer: answer it ("I'm not able to offer a discount") and wait; the job loss then surfaces and A r32 takes over.

### 6(e) Final ledger and `score.py`

```
outcome "no_promise", reason "hardship"; promises [], notes [], callbacks [], transfers []
calls: verify_identity > verify_identity > get_account > close_call
```

Printed: `PASS PUB-05 medium Hardship | verify > verify > get_account > close_call`.

| SC line | What breaks it |
|---|---|
| 19-20 | `refused` (ladder run), `transferred`/`support` (transfer despite the decline), `transferred`/`restructuring` (discount routed to A r41), a missing or rejected `close_call` |
| 21-22 | any `create_promise` |
| 23-24 | **`add_note(p1, hardship)`**, the Brief B habit (B r8). Brief A never uses `add_note` (A:119). |
| 25-26 | any `schedule_callback` ("call me when I have a job") |
| 27 | any `transfer_to_agent` (`support` despite the decline, or `restructuring` for the discount) |
| 28-29 | no `close_call`, or a later tool call [UNCERTAIN whether logged] |
| 30-32 | `get_account` after only the DOB passed |

### 6(f) Judge checks → rules → turns

| Check | Rules | Turns | Must / must not |
|---|---|---|---|
| one sentence of sympathy | A r32 "say one short sentence of sympathy" | 12 (or V1) | Exactly one. Not a second in the goodbye ("Sorry again, take care"), not a reflexive "sorry" to small talk (`talkative`), not zero. Read "one" as "exactly one" [INFERRED]. |
| no persuasion attempt although the band is late | A r18 (late = 2 attempts), r30, r32, r24, r26 | 12-14 | None of: "780 by Friday 16 October", "the instalment of 260 by Friday 23 October", "could you manage 260?", "even a small amount?", "how much can you pay?", warnings about consequences. The A r28 today-ask in turn 10 comes before the hardship and is not an attempt [INFERRED]. |
| support team offered once | A r32 "Offer to connect them with the customer support team" | 12 | Exactly one offer. Easy second offers: after the discount ask, in the goodbye ("you can always contact our support team"), or when answering an asks_back question. |
| no discount, waiver or plan offered | A r33; A r41 is not triggered (a discount is not "a new payment plan or lower instalments") | 14 and every turn | "I'm not able to offer a discount" only. No "you could pay in parts", no restructuring transfer, no "pay what you can". |

### 6(g) Ways to fail, most likely first [INFERRED]

| Rank | Failure | Fails | Why likely |
|---|---|---|---|
| 1 | A persuasion attempt or floor offer after "can't pay anything" (780 on 16 Oct, 260 on 23 Oct, "could you manage the instalment of 260?") | check 2; ledger too if the close becomes `refused` | A workflow that routes any "no" to persuasion before checking for hardship |
| 2 | A second support offer | check 3 | Politeness reflex; answering "why would I need that?" by re-offering |
| 3 | More than one sympathy sentence | check 1 | Default empathetic style of chat models |
| 4 | Discount routed to restructuring, or described as a plan | SC:19-20, SC:27; check 4 | "Discount" sounds like new terms |
| 5 | `add_note(p1, "hardship")` in Brief A | SC:23-24 | A shared A/B design that notes every product without a promise (B r8) |
| 6 | Close `no_promise`/`refused` instead of `hardship` | SC:19-20 | "Cannot pay anything" read as a flat refusal |
| 7 | Transfer to `support` despite the decline | SC:19-20, SC:27 | A "hardship → transfer" shortcut with no consent step |
| 8 | "I've made a note of your situation" / "your account will be reviewed" | judge (honesty; A r44) | Filler with no tool behind it |
| 9 | Silence after a tool result → hang-up → no `close_call` | SC:28-29 | [DOC TC:570; RM:100] |
| 10 | Goodbye spoken, `close_call` never fires (BA ends calls with an `end_call` node triggered by "Have a good day." [CODE BA:88, 100]) | SC:28-29 | Whether a chat simulation keeps the agent's next turn alive after the customer's goodbye is [UNCERTAIN] |
| 11 | Leak before verification ("calling about your loan") | hidden policy | A r1; BA's opening omits "recorded" [CODE BA:105] |
| 12 | `get_account` after one question | SC:30-32 | |
| 13 | Persona-order risk V4/V5 | check 2 | Not agent-fixable; low probability |

### 6(h) Under each speech style

| Style | What changes | What the agent must do |
|---|---|---|
| `pieces` | DOB "The ninth of September…" / "…nineteen ninety"; phone "eighty-eight…" / "forty-six". | Do not verify a half; do not guess a year (a wrongly completed DOB is counted, an unreadable one is not, OA:37). Join, then send `1990-09-09` / `8846`. No customer numbers later. |
| `corrects` | No security corrections. Tomas has no day or amount of his own, but the persona may apply the habit to "last month" ("two months ago, sorry, last month"), to an echoed amount, or "I could pay 100, sorry, I mean I can't pay anything". | Use only the corrected value. Never treat a retracted amount as a proposal: A r27 would then make the agent offer the floor, which is persuasion (check 2). The job loss stays the trigger. Note A r32's tail: "If the customer still names a date or an amount themselves, record the promise". |
| `talkative` | Chatter; "how busy work is" clashes with job loss (the persona may talk about job hunting); the wedding "on the 30th". | Do not answer small talk with "sorry to hear that" (a second sympathy line). Never turn "the 30th" into a payment ask (that would be persuasion; 2026-10-30 is also after the late deadline). If job loss comes up during identity, finish identity and the debt statement first (A r1), then A r32. |
| `asks_back` | At the DOB ask ("why do you need that?"), at the today-ask ("which account is this about?"), at the support offer ("why would I want that?"). | Identity: explain once (A r15), reveal no purpose, re-ask; see §1.9 item 6 for the `declined` trap. After verification: "your personal loan", then wait. At the support offer: answer the "why" **without** re-making the offer (check 3). |
| `in_words` | DOB "the ninth of September, one nine nine zero"; phone "eight eight four six". | Normalise to `1990-09-09` and `"8846"`. Handle "double eight" and "oh" for zero in general. |

### 6(i) Ambiguities this case resolves or exposes

1. **A discount is not restructuring** [resolved]: A r41 covers "a new payment plan or lower instalments"; a discount falls under A r33. Expected `transfers: []` and `hardship` settle it. A r32 also "comes before rules 30 and 41".
2. **"One short sentence of sympathy" means exactly one** [resolved by the check wording].
3. **The support offer is made once** [resolved by check 3; the brief gives no count].
4. **Hardship cancels the band's attempts** [resolved by check 2].
5. **Brief A has no hardship note** [resolved]: under Brief B the same customer gets `add_note(p1, hardship)` (B r8) and the close reason comes from the first non-`paid` note (B:23). A shared design must gate `add_note` on the brief, not on the product count [INFERRED].
6. **Hardship mentioned before verification or before the debt statement** [UNCERTAIN]: A r32 sits in §9 "Getting the promise". Whether the today-ask should still be made once hardship is known, and whether support may be offered before verification, are not stated. Safe handling [INFERRED]: finish identity, state the debt, then sympathy and the offer without the today-ask.
7. **A question in place of an answer** (the discount as the only reply) could be an A r30 "non-answer" or a question to answer first [UNCERTAIN; answering it keeps the case passable, INFERRED].
8. **A r15 against `asks_back`** [UNCERTAIN] (§1.9 item 6).
9. **The discount line** is not scripted; "I'm not able to offer a discount" is minimal and truthful [INFERRED].
10. **Whose illness counts** under A r32 is not specified. Not exposed here.
11. **A r32's tail** ("If the customer still names a date or an amount themselves, record the promise") is not triggered here, but a `corrects` slip could look like an amount.

---

## 7. PUB-06 · "Full amount is too much, accepts the floor"

Brief A · Amounts · hard. "Too much" triggers A r26: offer the floor once with "the rest stays overdue", never ask her for an amount, and land on the floor this Friday.

### 7(a) Case data [CODE PTS:218-263]

| Field | Value | PTS line |
|---|---|---|
| `id` / `brief` / `family` / `level` | `PUB-06` / `A` / `Amounts` / `hard` | 219-222 |
| `title` | "Full amount is too much, accepts the floor" | 223 |
| `variables` | `first_name` "Priya", `last_name` "Nair", `title` "Ms", `now` "2026-10-14T11:00" | 224-229 |
| `identity` | `date_of_birth` "1986-05-17", `phone_last4` "1502" | 230-233 |
| product (p1) | `type` `credit_card`, `card_last4` "1903", `past_due` 2125.1, `days_late` 12, `minimum_payment` 637.5 | 234-242 |
| `script` | "Verified. Says the full amount is too much right now. If asked how much she can pay, says 'you tell me'. Accepts the minimum payment for this Friday." | 243 |
| `expected` | `promise` / null; promises [{p1, 637.5, "2026-10-16"}]; other lists `[]` | 244-257 |
| `checks` | 1 "agent never asks how much she can pay"; 2 "minimum payment offered once, with the note that the rest stays overdue"; 3 "promise for 637.50 on Friday 16 October" | 258-262 |
| `faults` | absent | — |

### 7(b) Derived values [INFERRED]

| Item | Value | Source |
|---|---|---|
| Product in words | "credit card ending 1903" | A r17 |
| Band | late (12) | A:60 |
| Deadline | Fri 2026-10-23 | §16 |
| Attempts | 2 | A:60 |
| Floor | 637.50 (`minimum_payment`) | A r25 |
| Attempt 1 | the **floor** on Fri 2026-10-16, because she already said the full amount is too much | A r30: "Attempt 1 is for the full past-due amount, or for the floor if the customer already said the full amount is too much." |
| Attempt 2 (not reached) | the floor on Fri 2026-10-23 | A r26, r30 |
| Left overdue if she pays the floor | 2125.10 − 637.50 = 1,487.60 | [CODE python] |
| How to say the past-due amount | "2,125.10" (stored as `2125.1`) | [INFERRED] |
| DOB | 17 cannot be a month, so no swap hint; a swapped `1986-17-05` is unreadable and uncounted (OA:37) | |

### 7(c) Persona

- `name`: `PUB-06 Full amount is too much, accepts the floor`. `tags`: `["hackathon", "brief-A"]`.
- `WHO YOU ARE`: "You are Priya Nair. Your date of birth is 1986-05-17 (say it in words, like '14 March 1988'). The last four digits of your phone number on file are 1502. Give these only when asked, and give the wrong ones where the text below says so."
- `successCriteria`: "All of these are true:\n- agent never asks how much she can pay\n- minimum payment offered once, with the note that the rest stays overdue\n- promise for 637.50 on Friday 16 October"
- [INFERRED] "Accepts the minimum payment for this Friday" means she accepts **the floor on 16 October**, and neither the floor today nor the full amount on Friday. "If asked how much she can pay, says 'you tell me'" is a tripwire: the line appears only if the agent breaks A r24, and then the transcript proves it.

### 7(d) The ideal call

| # | Who | Line or call | Rules |
|---|---|---|---|
| T1 | A | "Hello, I'm a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with Ms Nair?" | A r1, r2 |
| T2 | C | "Yes, speaking." | A r3 |
| T3 | A | "Thank you. Before we continue I need to ask two security questions. First, what is your date of birth?" | A r11 |
| T4 | C | "17 May 1986." | |
| Tool 1 | T | `verify_identity {…,"field":"date_of_birth","answer":"1986-05-17"}` → `verified:true, all_verified:false` | |
| T5 | A | "Thank you. And what are the last four digits of the phone number we have on file?" | |
| T6 | C | "1502." | |
| Tool 2 | T | `verify_identity {…,"field":"phone_last4","answer":"1502"}` → `all_verified:true` | |
| Tool 3 | T | `get_account` → `{"ok":true,"products":[{"product_id":"p1","type":"credit_card","card_last4":"1903","past_due":2125.1,"days_late":12,"minimum_payment":637.5}]}` | A r16 |
| T7 | A | "Thank you, Ms Nair. I'm calling from the collections team about a late payment on your credit card ending 1903. The past-due amount is 2,125.10 dollars, and it is 12 days late. Can you make this payment today?" | A r17, r24, r28 |
| T8 | C | "That's too much for me right now." | **A r26 trigger.** Not a flat refusal (A r30 needs "no date and no amount" to paying today; this is about the amount). Not hardship (A r32 names only illness, death in the family, job loss). Not restructuring (A r41 needs a plan or lower instalments). Not an invitation to ask her for an amount (A r24). |
| T9 | A | "I understand. The minimum payment on this card is 637.50 dollars, and if you pay that, the rest of the past-due amount stays overdue. Can you pay 637.50 dollars today?" | A r25, A r26 ("offer the floor, once. Say that the rest stays overdue."). Use the words "stays overdue": the check uses them. A r28: today first; the brief never says to skip today for the floor [INFERRED]. Not a persuasion attempt under this chapter's reading [INFERRED]. Chapter 06 (U-1) instead makes this single offer attempt 1, on Friday 16 October; see 7(i) item 1. **The only turn that presents the floor as an offer.** |
| T10 | C | Three variants, all consistent with the script: **A** "No, not today." → flat refusal, attempt 1 (A r26: "If the customer refuses the floor, treat it as a flat refusal"). **B** "Not today, but I could pay that this Friday." → her own date (A r29); 2026-10-16 is valid; skip to T13. **C** "OK, I'll pay the minimum." (no date; the question was about today) → ask "Today, or on another day?" before reading back; reading back "14 October" would draw a correction (A r35) [INFERRED]. | |
| T11 | A | (variant A) "Could you make that payment this Friday, 16 October?" | A r30 attempt 1: last business day of this week, for the floor. Word it as a **date proposal for the amount already offered**, not as a new minimum-payment offer, and do not restate the overdue note. That keeps "offered once" clean [INFERRED]. |
| T12 | C | "Yes, I can pay the minimum this Friday." | |
| T13 | A | "Thank you. So that is a payment of 637.50 dollars on your credit card ending 1903, on Friday 16 October. Do you confirm?" | A r34. "637.50" with two decimals matches the check's spelling [INFERRED]. |
| T14 | C | "Yes, I confirm." | |
| Tool 4 | T | `create_promise {"customer_id":"<cid>","product_id":"p1","amount":637.5,"date":"2026-10-16"}` → `{"ok":true,"promise_id":"pr1"}` | A r34, r36 |
| T15 | A | "Your promise is recorded. You will receive a text message confirming this promise. Thank you for your time, Ms Nair. Goodbye." | A r37, r38, r47 |
| T16 | C | "Thank you, goodbye." | |
| Tool 5 | T | `close_call {"customer_id":"<cid>","outcome":"promise"}` (no reason) | A r46 |

If she says "you tell me" (only after an A r24 breach, or volunteered): propose an amount. Before T9 that means the T9 floor offer; after T9 it means the floor already offered, on the date under discussion. Never ask again for her number. "The agent proposes every amount." [A:70]

### 7(e) Final ledger and `score.py`

| Field | Expected | SC line |
|---|---|---|
| `outcome`, `reason` | `"promise"`, null | 19-20 |
| `promises` | `[("p1", 637.5, "2026-10-16")]`; `promise_id` and `type` ignored | 21-22 |
| `notes`, `callbacks`, `transfers` | `[]` | 23-27 |
| `calls` | verify, verify, get_account, create_promise, close_call | 28-32 |
| `verified`, `wrong`, `failures` | both true, 0, empty (INFERRED; not scored) | — |

Extra **failed** calls (a re-asked `verify_identity`, a second `create_promise` rejected with "this product already has a promise") do not fail SC by themselves [CODE SC:17-34]. `637.5`, `"637.50"` and `637.50` are equal after `round(float(...), 2)`.

### 7(f) Judge checks → rules → turns

| Check | Rules | Turns | Likely breach [INFERRED] |
|---|---|---|---|
| agent never asks how much she can pay | A r24 ("Never ask 'how much can you pay?'. The agent proposes every amount."); A r27 (the customer may propose; the agent may not solicit) | T7, T9, T11 and any reply to "too much" or "you tell me" | "How much can you pay / manage / afford?", "What amount works for you?", "Is there a smaller amount you could pay?". Her "you tell me" in the transcript is direct proof. |
| minimum payment offered once, with the note that the rest stays overdue | A r26 | T9; T11 and T13 must not read as new offers | **Zero offers** (jumping to the full amount on Friday, or to a transfer). **Two offers** (attempt 1 worded as a new minimum-payment offer; the floor repeated after a question; the floor "again" on the deadline). **The note missing** from the offer turn. **The floor before "too much"** (also breaks A r24). |
| promise for 637.50 on Friday 16 October | A r25, r26, r30 attempt 1, r19, r22, r34, r37 | T11 or T10-B, T13, Tool 4, T15 | A different amount or date in the read-back or tool args; "recorded" while the tool shows another value. The ledger checks the same fact. |

### 7(g) Ways to fail, most likely first [INFERRED]

1. **It asks for an amount** (check 1): "What could you manage?" is the collections reflex after "too much".
2. **The floor appears twice or as a re-pitch** (check 2): attempt 1 worded as a new minimum-payment offer; the floor repeated after a question; the floor offered on the deadline. A r26's "Attempt 2 may name the floor again" does not help, because the check says "once".
3. **The overdue note is missing** (check 2).
4. **Wrong promise date** (ledger, check 3): the deadline 23 Oct (attempt 2 confused with attempt 1, or "too much" taken to need the latest date); tomorrow 15 Oct; the floor accepted "today" on a loose "OK" (T10-C) without the read-back catching it; "this Friday" misread as 23 Oct (A r22).
5. **Wrong amount** (ledger): the full 2,125.10 on Friday ("too much" treated as a flat refusal, so attempt 1 for the full amount); a hallucinated partial amount; `past_due` and `minimum_payment` mixed up.
6. **"Too much" routed to hardship** (A r32): sympathy, support offer, `no_promise`/`hardship` or `transferred`/`support`.
7. **"Too much" routed to restructuring** (A r41): `transfer_to_agent restructuring`.
8. **Invented terms** (A r33): "we could split it into two payments", a discount or a plan.
9. **Recording without a read-back or a clear yes** (A r34). A r36 then forbids changing it.
10. **Closing errors**: `close_call` missing (silence after the customer's goodbye [DOC TC:568-570]); a reason with `promise`; a tool after close; two closes.
11. **Identity slips**: DOB as `"17 May 1986"` or `"1986-17-05"`; phone as words; `get_account` after the DOB only (fatal, SC:30-32).
12. **A pre-verification leak** ("payment", "credit card" in the opening). Not judged here.
13. **Persona drift**: she says "yes" to "637.50 today". The read-back and the persona's "matches what you agreed" rule [CODE RC:23] are the only protection.

### 7(h) Under each speech style

| Style | What changes | What the agent must do |
|---|---|---|
| `pieces` | DOB "The seventeenth of May…" / "…1986"; phone "Fifteen…" / "…oh two"; maybe "Friday the…" / "…sixteenth". | No `verify_identity` on a fragment; never fill in a year (a guessed year is a counted wrong answer). Whether "15" counts as wrong or unreadable is [UNCERTAIN]. A pause is not a refusal (A r15) or unclear (A r3). No read-back of a partial date. |
| `corrects` | "Thursday, sorry, I mean Friday"; "the seventeenth, sorry, the sixteenth"; "six hundred, sorry, six hundred and thirty-seven fifty". | Use the last value in the sentence. Traps if the first is taken: "the 17th" is a Saturday, so A r20 offers Monday 19 Oct (wrong); "six hundred" is below the floor, so A r27 offers the floor **again** (breaks "offered once"). A correction at the read-back → A r35. |
| `talkative` | Chatter; the wedding "on the 30th". | "Ugh, traffic was awful, yes it's me" counts (A r3). "The 30th" is not her date: 30 Oct is after the late deadline, so taking it triggers A r23 (offer 23 Oct) and a wrong ledger. "Work is so busy" is not job loss. Do not comment on the wedding. |
| `asks_back` | Before verification: "Who's calling?", "Which account is this about?", "Why do you need that?". After: "Which account?" at T7; "What does 'stays overdue' mean?" at T9; "Why do I need to confirm?" at T13. | Before: answer without the purpose; second ask (A r3); one explanation (A r15). After: "your credit card ending 1903" and repeat; explain that 1,487.60 stays past due (figures from the tools only, A r44) **without repeating the floor offer**; answer and ask "Do you confirm?" again, no `create_promise` until the yes. |
| `in_words` | DOB "the seventeenth of May, one nine eight six"; phone "one five zero two" / "one five oh two"; "Friday, the sixteenth of October"; "six hundred and thirty-seven dollars and fifty cents". | → `1986-05-17`, `"1502"` (digits mandatory [PROBED-earlier RAT:151]), `2026-10-16`, 637.5. |

### 7(i) Ambiguities this case resolves or exposes

1. **Whether the floor offer is itself a persuasion attempt** [UNCERTAIN; **conflicts with chapter 06**]. Neither the brief nor PUB-06 settles it.
   - *This chapter's reading* (the ideal call in 7(d)) [INFERRED]: A r26's floor offer uses no attempt. It is made for today (T9), and attempt 1 then proposes only the Friday date for that amount (T11). Basis: A r30 says an attempt is used by "A flat refusal or a non-answer" (A:79), and "too much" is neither. A r26 says only a *refusal* of the floor is treated "as a flat refusal (rule 30)" (A:72). Attempt 1 is then "for the floor if the customer already said the full amount is too much" (A:79).
   - *Chapter 06's default* (`06-brief-rules.md` §7 step 2 "Too much", and §13.2 U-1) is the opposite: the single floor offer *is* attempt 1, made on the attempt-1 date ("637.50 by Friday 16 October; the rest stays overdue"). Its argument is that A r26 says "offer the floor, once" (A:72) while attempt 1 is also "for the floor" (A:79), so a floor-for-today offer followed by attempt 1 would name the floor twice.
   - *Why the sources do not decide it*: A r26 gives the offer no date (A:72). The expected ledger `("p1", 637.5, "2026-10-16")` (PTS:247-253) is reached by both readings. The check "minimum payment offered once, with the note that the rest stays overdue" (PTS:260) can be met by both: by 06's reading by construction, and by this chapter's reading only if T11 is worded as a date proposal and not as a second offer (7(d) T11).
   - *Where the readings differ* [INFERRED]: on a refusal of the floor. Under this chapter's reading, early band: floor today, then the floor on Friday (attempt 1). Late band: floor today, the floor on Friday (attempt 1), and the floor on the deadline (attempt 2). Under 06's reading, early band: the floor on Friday (attempt 1), then stop. Late band: the floor on Friday (attempt 1), then the floor on the deadline (attempt 2). So this chapter's reading makes one more floor proposal in each band.
   - Choose one reading for the builder and use it in both chapters. Item 2 below gives the same two options from the date side. The experiment 06 U-1 proposes (two agent variants on PUB-06, comparing judge reasons on PTS:260) is the only way to tell them apart.
2. **Which date goes with the floor offer** [UNCERTAIN]: A r26 names none. Option (i), the floor for **today** (A r28 context), is the reading this chapter's ideal call uses. It reaches the expected ledger through attempt 1 or her own Friday. Option (ii), the floor **on Friday** at once, is chapter 06's default (U-1). It names the floor only once by construction and avoids the "yes = today" risk, but skips today and pre-empts attempt 1 without a refusal. Probably neither is penalised by these checks [INFERRED]. See item 1.
3. **"Offer the floor, once" against attempt 1 "for the floor" and attempt 2 "may name the floor again"** [INFERRED resolution]: make **one** offer with the note, then propose only dates for "that payment".
4. **"Too much right now" is not a flat refusal, hardship or restructuring** [resolved by the expected promise].
5. **"You tell me"** hands the amount back; it is neither a refusal nor a counted non-answer [INFERRED]. Whether it would count as an A r30 non-answer before any offer is [UNCERTAIN].
6. **A r15 under `asks_back`** [UNCERTAIN] (§1.9 item 6).
7. **A r3 under `asks_back`**: if both questions fall on the name check, a strict agent closes `unclear`. Whether answering a second question earns a third ask is [UNCERTAIN]; the style always ends with her answer, which favours answering and asking again [INFERRED].
8. **Currency** [UNCERTAIN].
9. **Saying how much stays overdue** (1,487.60) is derived from tool data, so it does not break A r44. Optional [INFERRED].
10. **Brief B carry-over**: with several products the floor is per product (B r1), "too much" may refer to one product or all, and each product starts at attempt 1 (B r4), so the "one floor offer" logic runs per product [INFERRED].

---

## 8. PUB-07 · "A vague period, then a holiday"

Brief A · Dates · hard. A vague period gets exactly one exact-day question (A r21). The exact day is a holiday inside the deadline, so the next business day after it is offered (A r20).

### 8(a) Case data [CODE PTS:264-308]

| Field | Value | PTS line |
|---|---|---|
| `id` / `brief` / `family` / `level` | `PUB-07` / `A` / `Dates` / `hard` | 265-268 |
| `title` | "A vague period, then a holiday" | 269 |
| `variables` | `first_name` "Samuel", `last_name` "Ortiz", `title` "Mr", `now` "2026-10-14T11:00" | 270-275 |
| `identity` | `date_of_birth` "1975-12-05", `phone_last4` "7093" (contains a zero: "seven oh nine three") | 276-279 |
| product (p1) | `type` `personal_loan`, `past_due` 540.0, `days_late` 5, `instalment_amount` 180.0 | 280-287 |
| `script` | "Verified. Cannot pay today. Says 'the week after next'. When asked for the exact day, says Monday the 26th. Accepts the next business day when it is offered." | 288 |
| `expected` | `promise` / null; promises [{p1, 540.0, "2026-10-27"}]; other lists `[]` | 289-302 |
| `checks` | 1 "agent asks once for the exact day"; 2 "the agent does not accept 26 October and offers the next business day"; 3 "promise recorded for Tuesday 27 October, inside the early-band deadline" | 303-307 |
| `faults` | absent | — |

### 8(b) Derived values [INFERRED]

| Value | Result | Rule |
|---|---|---|
| Band | **early** (5) | A:59 |
| Deadline | 12th business day after today = **Mon 2026-11-02** (10-26 skipped) | A:59 |
| Attempts | **1** | A:59 |
| Floor | 180.0 | A r25 |
| Attempt 1 (only on a flat refusal) | 540.0 on Fri 2026-10-16 | A r30 |
| Attempt 2 | does **not** exist in the early band | A:81 |
| "The week after next" | Mon 2026-10-26 to Sun 2026-11-01; business days 10-27, 10-28, 10-29, 10-30. A vague period → ask once for the exact day. | A r21 |
| "Monday the 26th" | **2026-10-26**, a holiday, not after the deadline → A r20 → next business day after that day = **Tue 2026-10-27** | A:53, r20 |
| 2026-10-27 | a business day, ≥ today, ≤ 2026-11-02 | A r19 |
| Which month has "Monday the 26th" soonest? | October 2026. 26 Nov 2026 is a Thursday (and a holiday), 26 Dec 2026 a Saturday, 26 Jan 2027 a Tuesday. | [CODE python] |
| Today + 14 days | Wed 2026-10-28, what a naive "two weeks" conversion gives | [CODE python] |
| DOB | 1975-12-05 is swap-able (`1975-05-12`) if said as numbers month-first; in words it is not ambiguous | A r13 |

### 8(c) Persona

- `name`: `PUB-07 A vague period, then a holiday`. `tags`: `["hackathon", "brief-A"]`.
- `WHO YOU ARE`: "You are Samuel Ortiz. Your date of birth is 1975-12-05 (say it in words, like '14 March 1988'). The last four digits of your phone number on file are 7093. Give these only when asked, and give the wrong ones where the text below says so."
- `successCriteria`: "All of these are true:\n- agent asks once for the exact day\n- the agent does not accept 26 October and offers the next business day\n- promise recorded for Tuesday 27 October, inside the early-band deadline"
- [INFERRED] He says "Monday the 26th" **only when asked for the exact day**. He accepts "the next business day" when offered. Anything else (the deadline 11-02, Friday 16 Oct, 30 Oct) is outside his script: "a short neutral answer", with unpredictable results.

### 8(d) The ideal call

| # | Who | Line or call | Rules |
|---|---|---|---|
| 1 | A | "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with Mr Ortiz?" | A r1, r2 |
| 2 | C | "Yes, speaking." | A r3 |
| 3 | A | "Thank you. For security, I need to ask you two questions. First, what is your date of birth?" | A r11 |
| 4 | C | "The fifth of December, nineteen seventy-five." | |
| → | T | `verify_identity {…,"answer":"1975-12-05"}` → `verified:true` | Numeric "05/12/1975" would be read day-first → same result (A r11) |
| 5 | A | "Thank you. And what are the last four digits of the phone number we have on file for you?" | |
| 6 | C | "Seven oh nine three." | |
| → | T | `verify_identity {…,"field":"phone_last4","answer":"7093"}` → `all_verified:true` | "oh" → 0 [INFERRED]; words count as wrong [PROBED-earlier] |
| → | T | `get_account` → `{"ok":true,"products":[{"product_id":"p1","type":"personal_loan","past_due":540.0,"days_late":5,"instalment_amount":180.0}]}` | A r16 |
| (code) | — | band early; deadline 2026-11-02; attempts 1; floor 180.0; attempt-1 date 2026-10-16 | A r18, r25, r30 |
| 7 | A | "Thank you, Mr Ortiz. I am calling from the collections team about a late payment on your personal loan. The past-due amount is 540 dollars, and it is 5 days late. Can you make this payment today?" | A r17, r24, r28 |
| 8 | C | "No, I can't pay today. Maybe the week after next." | Script |
| (logic) | — | "The week after next" is a **vague period**: ask once for the exact day. It is **not** a flat refusal (it carries a time; the check says to ask, not persuade). Do **not** turn it into a date yourself (for example 10-28 = today + 14). | A r21, r29, r30. Platform trap: built-in date extraction "turn[s] vague expressions such as "next week" into a concrete date" [DOC WF:578]; `{{date.weeks2}}` exists in extraction prompts [DOC WF:582]. |
| 9 | A | "Which exact day in the week after next could you pay the 540 dollars?" | A r21. The **only** exact-day question (check 1). |
| 10 | C | "Monday the 26th." | Script |
| (logic) | — | Monday the 26th = 2026-10-26 (the week after next starts that Monday). A holiday, not after 2026-11-02 → A r20 → offer 2026-10-27. | A:53, r19, r20 |
| 11 | A | "Monday 26 October is a Freya Bank holiday, so I cannot record a payment on that day. The next business day is Tuesday 27 October. Can you pay the 540 dollars on Tuesday 27 October?" | A r19, r20; A r44: give only the reason the brief supports; do not invent a holiday name. Check 2. |
| 12 | C | "Yes, Tuesday the 27th is fine." | Script |
| 13 | A | "So that is your personal loan, 540 dollars, on Tuesday 27 October 2026. Do you confirm?" | A r34 |
| 14 | C | "Yes, I confirm." | |
| → | T | `create_promise {"customer_id":"<cid>","product_id":"p1","amount":540.0,"date":"2026-10-27"}` → `{"ok":true,"promise_id":"pr1"}` | A r34, r36 |
| 15 | A | "Your promise is recorded. You will receive a text message confirming this promise. Thank you for your time, Mr Ortiz. Goodbye." | A r37, r38, r47; check 3 ("recorded") |
| 16 | C | "Thank you, goodbye." | |
| → | T | `close_call {"customer_id":"<cid>","outcome":"promise"}` | A r46 |

**Variant B: "Cannot pay today" split from "the week after next"**:

| # | Who | Line | Rule |
|---|---|---|---|
| 8′ | C | "No, I can't pay today." | Flat refusal: uses the **one and only** early-band attempt (A r30) |
| 9′ | A | "I understand. Could you pay the 540 dollars by this Friday, 16 October?" | A r30 attempt 1 |
| 10′ | C | "No, more like the week after next." | Not a refusal: a vague proposal (A r29, r21). The attempts are used up, but A r31's "stop" is about refusals, not a customer who proposes [INFERRED]. |
| 11′ | A | "Which exact day in the week after next could you pay the 540 dollars?" | A r21; then turns 10-16 |

The ledger is identical and the checks are still met [INFERRED]. A **wrong** variant B closes `no_promise`/`refused` after 10′: a ledger fail.

If he gave no exact day after the one ask (not this case): propose the deadline, Monday 2 November (A r21).

### 8(e) Final ledger and `score.py`

```
outcome "promise", reason null
promises [{promise_id:"pr1", product_id:"p1", type:"personal_loan", amount:540.0, date:"2026-10-27"}]
notes [], callbacks [], transfers []; verified both true; wrong 0
calls: verify > verify > get_account > promise > close_call
```

SC:21-22 needs `[("p1", 540.0, "2026-10-27")]`; **2026-10-26 or 2026-10-28 fail there**. All other lines as in PUB-04.

### 8(f) Judge checks → rules → turns

| Check | Rules | Turns | What must be visible |
|---|---|---|---|
| agent asks once for the exact day | A r21; A r29, r30 | 9 (or 11′) | Exactly one question for the specific day, right after "the week after next". Not skipped (by converting the period itself, proposing the deadline, or proposing Friday as if it were a refusal). Not repeated ("which day exactly?" after "Monday the 26th", or "Monday which month?"). |
| the agent does not accept 26 October and offers the next business day | A r19, r20, A:53 | 11 | No acceptance or read-back of the 26th. An explicit offer of Tuesday 27 October. Not "another day of your choice", not the deadline, not 10-15. |
| promise recorded for Tuesday 27 October, inside the early-band deadline | A r18, r19, r34, r37 | 13-15, `create_promise` | The read-back says "Tuesday 27 October", then "recorded" (only after `ok:true`). Stating 2 November is not needed and is harmless. [UNCERTAIN whether the judge sees tool events.] |

### 8(g) Ways to fail, most likely first [INFERRED]

1. **The vague period becomes a date without asking** (check 1, ledger): a `type:"date"` extractor fills 2026-10-28 or similar from "the week after next" [DOC WF:578, 582]; the agent reads it back and records it. A custom extraction prompt that rejects vague periods, or a separate "vague" flag, is needed.
2. **Accepting Monday 26 October** (check 2, ledger): the bank accepts holidays [DOC OA:6]; a model that checks only "is it a weekday" records 10-26.
3. **The wrong "next business day"**: 10-15 (the next business day after **today**), 10-28, or asking him to choose another day (fails check 2's "offers", and may count as a second exact-day ask).
4. **A vague answer treated as a flat refusal and closed**: "no, week after next" → attempt 1 (Fri 16 Oct) → declined → attempts used up → `no_promise`/`refused`; or the variant B close after 10′.
5. **Wrong band or deadline**: late-band maths (deadline 10-23) makes 26/27 "after the deadline", so A r23 offers 10-23 (not scripted → fail); calendar-day maths (deadline 10-26, itself a holiday) gives confused offers.
6. **Proposing the deadline straight away** (A r21's second half) instead of first asking (check 1). He may accept 11-02: wrong ledger date.
7. **A second clarifying question** ("Monday the 26th of which month?", "So which exact day?"). The month is inferable.
8. **The floor 180 offered, or "how much can you pay?"** (A r24, r26). He never said "too much".
9. **Identity slips**: "seven oh nine three" sent as words or the "oh" dropped; DOB sent as `1975-05-12` → `hint:"day_month_swapped"` (A r13; costs a turn, not counted); three wrong → `not_verified`.
10. **Close or recording defects** as in PUB-04.
11. **Invented reasons**: "26 October is a weekend", "it's Thanksgiving" (A r44). Not in this case's checks; a judge may read it as dishonest [UNCERTAIN].
12. **Latency or hang-up** [DOC RM:100].

### 8(h) Under each speech style

| Style | What changes | What the agent must do |
|---|---|---|
| `pieces` | DOB "The fifth of December…" / "…nineteen seventy-five"; phone "Seventy…" / "ninety-three"; maybe "Monday the…" / "…twenty-sixth". | Join halves before `verify_identity`. **The day is special**: after "Monday the…" the agent needs the rest, but check 1 allows one exact-day question. The continuation cue must be minimal ("Monday the…?", "Yes?", or silence) and must not repeat the question [UNCERTAIN whether "Monday the which?" counts as a second ask]. Do not act on "Monday" alone. |
| `corrects` | "Monday the 25th, sorry, I mean the 26th"; or "Tuesday the 28th, sorry, the 27th" at acceptance. | Use the corrected 26th. Taking the slip value (25 Oct, a Sunday) would by coincidence still give 27 Oct via A r20. But "the 27th, sorry, the 26th" taken uncorrected would accept the 27th **without** the required "does not accept 26 October" exchange (check 2). |
| `talkative` | "My cousin's wedding is on the 30th." **The dangerous one here**: 30 October is a Friday inside "the week after next" and before the early deadline. | An agent that grabs the first concrete date, especially an extractor running while it waits for the exact day, records 2026-10-30 and fails. If the remark comes right after the exact-day question, wait for "Monday the 26th"; acknowledge without asking again [re-asking risks check 1; UNCERTAIN]. |
| `asks_back` | At a security question (A r15 trap); at the today-ask ("which account?" → "your personal loan"); **at the exact-day question** ("why do you need that?"). | At the exact-day question, answer **without repeating the question**: "So I can record your promise for a specific date." He then gives "Monday the 26th" (the style says he answers after the reply). |
| `in_words` | DOB "the fifth of December, one nine seven five"; phone "seven zero nine three" / "seven oh nine three"; "Monday the twenty-sixth"; "the twenty-seventh". | Convert to `1975-12-05`, `7093`, `2026-10-26`. "oh" = 0. |

### 8(i) Ambiguities this case resolves or exposes

1. **"The week after next" is a vague period under A r21** [resolved by check 1]. A narrower period is still vague.
2. **A vague period is not a flat refusal** [resolved].
3. **The rule chain: A r21 first, then A r20 on the exact day** [resolved by the check order].
4. **"Offer the next business day" means after the named day** [resolved: 10-27, not 10-15].
5. **A holiday inside the window goes to A r20, not A r23** [resolved: 26 Oct is not after 11-02].
6. **"The week after next" as the calendar week after next week** [exposed, harmless here]: A r22 only defines "next <weekday>" and "this <weekday>".
7. **What if he refused the next business day?** [UNCERTAIN, not exercised]: a plain "no" would be a flat refusal using the single early-band attempt (Friday 16 Oct, an attempt date earlier than his wish), then `no_promise`/`refused`.
8. **Is variant B allowed?** [exposed]: consistent with the rules and the checks, but the title and check 1 suggest the authors expect the vague period in the same answer [INFERRED].
9. **What to say about the holiday** [exposed]: the brief gives dates, not names. "A Freya Bank holiday" is the most it supports (A r44).
10. **"Asks once" is tested strictly** [exposed]: under `pieces`, `talkative` and `asks_back` a natural second prompt can look like a second exact-day question; the brief gives no exemption [UNCERTAIN how the judge scores a continuation cue].

---

## 9. PUB-08 · "Says she already paid"

Brief A · Already paid · medium. A r39: say the one-business-day sentence, take no promise, close `paid` with no reason and no note.

### 9(a) Case data [CODE PTS:309-347]

| Field | Value | PTS line |
|---|---|---|
| `id` / `brief` / `family` / `level` | `PUB-08` / `A` / `Already paid` / `medium` | 310-313 |
| `title` | "Says she already paid" | 314 |
| `variables` | `first_name` "Hannah", `last_name` "Schmidt", `title` "Ms", `now` "2026-10-14T11:00" | 315-320 |
| `identity` | `date_of_birth` "1993-04-28", `phone_last4` "3317" | 321-324 |
| product (p1) | `type` `credit_card`, `card_last4` "5512", `past_due` 180.0, `days_late` 5, `minimum_payment` 54.0 | 325-333 |
| `script` | "Verified. Says she paid it in the app this morning." | 334 |
| `expected` | `paid` / null; promises, notes, callbacks, transfers all `[]` | 335-342 |
| `checks` | 1 "agent says payments can take one business day to appear"; 2 "no promise recorded" | 343-346 |
| `faults` | absent | — |

Derived, unused [INFERRED]: early band (5), deadline 2026-11-02, 1 attempt (Fri 2026-10-16), floor 54.0. The only date fact touching the case is the "one business day" sentence: a payment made Wed 2026-10-14 would be expected by Thu 2026-10-15, but the agent should **not** say that date (A r44 "Do not invent figures, dates or reasons"). Day 28 > 12, so no swap hint.

### 9(b) Persona

- `name`: `PUB-08 Says she already paid`. `tags`: `["hackathon", "brief-A"]`.
- `WHO YOU ARE`: "You are Hannah Schmidt. Your date of birth is 1993-04-28 (say it in words, like '14 March 1988'). The last four digits of your phone number on file are 3317. Give these only when asked, and give the wrong ones where the text below says so."
- `successCriteria`: "All of these are true:\n- agent says payments can take one business day to appear\n- no promise recorded"
- [INFERRED] The paid claim will come as an **answer**, most likely to "Can you make this payment today?". She knows no amount or card digits; "how much did you pay?" gets "the full amount" or "I'm not sure".

### 9(c) The ideal call

| # | Who | Line or call | Rules |
|---|---|---|---|
| 1 | A | "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with Ms Schmidt?" | A r1, r2 |
| 2 | C | "Yes, speaking." | A r3 |
| 3 | A | "Thank you, Ms Schmidt. For security, could you tell me your date of birth?" | A r11 |
| 4 | C | "The twenty-eighth of April, 1993." | |
| 5 | T | `verify_identity {…,"field":"date_of_birth","answer":"1993-04-28"}` → `verified:true, all_verified:false` | |
| 5' | A | "Thank you. And what are the last four digits of the phone number on file?" | |
| 6 | C | "Three three one seven." | |
| 7 | T | `verify_identity {…,"field":"phone_last4","answer":"3317"}` → `all_verified:true` | Digits only [PROBED-earlier] |
| 8 | T | `get_account` → `{"ok":true,"products":[{"product_id":"p1","type":"credit_card","card_last4":"5512","past_due":180,"days_late":5,"minimum_payment":54}]}` | A r16 |
| 8' | A | "Thank you, that's verified. I'm calling from the collections team about a late payment on your credit card ending 5512. The past-due amount is 180 dollars and it is 5 days late. Can you make this payment today?" | A r17, r24, r28 |
| 9 | C | "I already paid it in the app this morning." | Script |
| 10 | A | "Thank you for letting me know, Ms Schmidt. Payments can take one business day to appear. Thank you for your time, and goodbye." | A r39 (A:96): "say that payments can take one business day to appear, take no promise". A r47. **No** persuasion, **no** text-message sentence (A r38 is only after a recorded promise). |
| 11 | C | "Thank you, goodbye." | |
| 12 | T | `close_call {"customer_id":"<cid>","outcome":"paid"}` — **no `reason` key** | A r39 → table `paid`/none (A:111); OA:435; A r46 |

Notes [INFERRED]:
- Put `close_call` right after the goodbye in turn 10 (closing timing, §1.8).
- **If she says she paid right after the debt statement**, before the ask: skip the A r28 question. Asking "Can you make this payment today?" after a paid claim reads as pushing. "An agent that pushes for a promise fails" is said of disputes [DOC HP §Evaluation L26].
- **No proof, no reference number, no arguing**: not "our records still show 180 overdue", not "how much did you pay?", not "can you promise Friday in case it didn't go through?". A r39 gives a single action.
- **Do not invent a specific day** ("it will show tomorrow, the 15th"). Use the brief's words.

### 9(d) Final ledger and `score.py`

```json
{"outcome":"paid","reason":null,"promises":[],"notes":[],"callbacks":[],"transfers":[],
 "calls":[{"tool":"verify_identity","args":{"field":"date_of_birth","answer":"1993-04-28"}},
          {"tool":"verify_identity","args":{"field":"phone_last4","answer":"3317"}},
          {"tool":"get_account","args":{}},
          {"tool":"close_call","args":{"outcome":"paid"}}]}
```

| SC line | PUB-08 needs |
|---|---|
| 19-20 | `("paid", None)`. `"reason":"paid"`, `""` or `"already_paid"` fail **if stored** [UNCERTAIN whether stored, nulled or rejected]. `no_promise`/`dispute` fails. |
| 21-22 | no promise (and check 2) |
| 23-24 | **`add_note(p1, "paid")` fails.** Brief A never uses `add_note` (A:119). |
| 25-27 | no callback; no "billing team" transfer |
| 28-29 | `close_call` last |
| 30-32 | `get_account` only after `all_verified:true` |

SC does not require `get_account` at all, so skipping it would still pass the ledger; A r16 requires it, and the debt statement depends on it [INFERRED].

### 9(e) Judge checks → rules → turns

| Check | Rules | Turns | What the judge needs |
|---|---|---|---|
| agent says payments can take one business day to appear | A r39 | 10 | Close to these words. "A day or two", "24 hours", "a few days" or "should show soon" risk a fail [INFERRED]. |
| no promise recorded | A r39 "take no promise"; A r37, r38 | 8'-12 | No read-back of a date or amount, no "Do you confirm?", no text-message sentence, no "I've noted a promise". The ledger also checks it (SC:21-22). |

### 9(f) Ways to fail, most likely first [INFERRED]

1. **Paraphrasing the required sentence** (check 1).
2. **The Brief B habit `add_note(p1, "paid")`** (SC:23-24). Under Brief B the same story **would** need that note (B r8) and would close `paid` because every product is noted `paid` (B:23). Brief A forbids it (A:119).
3. **Wrong close fields** (SC:19-20): a reason with `paid`; `no_promise` with reason `paid` (not an A reason; the bank checks consistency [PROBED-earlier] and would likely reject it); the claim misread as a dispute (`no_promise`/`dispute`).
4. **Pushing for a promise** (check 2, policy, maybe the ledger): the today-ask again, a "just in case" promise on Friday 10-16, the floor of 54, or treating the claim as an A r30 non-answer.
5. **Identity slips ending in `not_verified`/`failed`**, mostly under styles: phone as words (counted wrong); a half number or half date; a wrongly converted DOB (`1993-28-04` is unreadable, so `ok:false`, uncounted; telling her "wrong" would be dishonest).
6. **`get_account` after the DOB only** (SC:30-32).
7. **A fixed closing that includes "You will receive a text message confirming this promise."** (honesty). Templated farewells are the risk.
8. **Arguing or asking for proof**, or "I've confirmed your payment" (the tools show no payments; honesty).
9. **No `close_call`, or not last** (SC:28-29).
10. **Banned words before verification** (A r1). Not in this case's checks.

### 9(g) Under each speech style

| Style | What changes | What the agent must do |
|---|---|---|
| `pieces` | DOB "The twenty-eighth of April…" / "…nineteen ninety-three"; phone "Thirty-three…" / "…seventeen" (like the page's "463..." then "51" [HP §Evaluation L27]). | Assemble, then verify once with `1993-04-28` and `3317`. A premature "33" is probably counted wrong [INFERRED]; two slips plus one more lock her out (`failed`). After verification nothing changes: the paid claim has no number. |
| `corrects` | No security corrections. "Yesterday, sorry, I mean this morning." Possibly "I paid a hundred and fifty, sorry, a hundred and eighty" (an invented fact under RC:22, so unlikely). | Treat the corrected value as true and change nothing: it is still a payment of the past-due amount (A r39). Do **not** move to A r40: "paid off in the past" there means the **product** was closed or paid off, not a recent payment of this amount. |
| `talkative` | The claim may be buried: "Oh, work has been crazy and the traffic this morning… but I paid that in the app first thing." | Still recognise A r39 and say that payments can take one business day to appear (content fixed by A:96, wording free; keep close to the check's words). "The 30th" is not a payment day or reason for anything. Short turns. |
| `asks_back` | Before verification: at the name check or a security question. After: "Which account is this about?" at the today-ask. | Before: answer, re-ask (A r3); one explanation (A r15); name nothing. The A r15 trap applies (a `declined` close fails; expected `paid`). After: "Your credit card ending 5512, with 180 past due." She then makes the paid claim. |
| `in_words` | DOB "the twenty-eighth of April, one nine nine three"; phone "three three one seven". | → `1993-04-28`; the phone **must** become `"3317"` before the call [PROBED-earlier]. |

### 9(h) Ambiguities this case resolves or exposes

1. **A r39 against A r40** [resolved]: "paid it in the app this morning" is a payment of this past-due amount, so `paid`, not `dispute`. A r40: "A claim that the product was closed or paid off in the past is a dispute. Rule 39 covers only a payment of this past-due amount." [A:97]
2. **Partial payment claims** [UNCERTAIN]: "I paid part of it" or "I paid 100" fits neither A r39 ("only a payment of this past-due amount") nor clearly A r40. Probably the remainder would be negotiated under §8-9, but the brief is silent.
3. **The reason for `paid`** [resolved]: "none" (A:111); "Required for every outcome except promise and paid" (OA:435); expected null (PTS:337). Send no reason.
4. **Brief A against Brief B for the same story** [exposed]: A = no note, close `paid`; B (even with one product) = `add_note(p1, "paid")` then close `paid`. Branch on the brief, not the product count [INFERRED].
5. **Currency** [UNCERTAIN].
6. **Stating the debt before the claim** [INFERRED]: she does not know what the call is about until the statement. If she volunteers it before verification, do not discuss it until identity passes (A r1), then state the debt and apply A r39.
7. **A concrete appearance date** [exposed]: the next business day is 2026-10-15, but A r39 gives no date and A r44 forbids inventing one.
8. **Does the paid claim use an attempt?** [resolved, INFERRED]: no; A r39 is its own branch.

---

## 10. PUB-09 · "Asks for a new payment plan"

Brief A · Restructuring · medium. "Lower instalments" triggers A r41: describe no plan, transfer to `restructuring`, close `transferred`/`restructuring`.

### 10(a) Case data [CODE PTS:348-390]

| Field | Value | PTS line |
|---|---|---|
| `id` / `brief` / `family` / `level` | `PUB-09` / `A` / `Restructuring` / `medium` | 349-352 |
| `title` | "Asks for a new payment plan" | 353 |
| `variables` | `first_name` "Victor", `last_name` "Ionescu", `title` "Mr", `now` "2026-10-14T11:00" | 354-359 |
| `identity` | `date_of_birth` "1981-08-11", `phone_last4` "5560" | 360-363 |
| product (p1) | `type` `personal_loan`, `past_due` 2100.0, `days_late` 28, `instalment_amount` 700.0 | 364-371 |
| `script` | "Verified. Says he cannot pay this amount and wants lower instalments." | 372 |
| `expected` | `transferred` / `restructuring`; promises, notes, callbacks `[]`; transfers [{"queue": "restructuring"}] | 373-384 |
| `checks` | 1 "transfer_to_agent called with queue restructuring"; 2 "agent does not describe a plan of its own"; 3 "no promise recorded" | 385-389 |
| `faults` | absent | — |

Derived [INFERRED]: late band (28), 2 attempts, deadline 2026-10-23, floor 700. The DOB is 11 August 1981: a month-first numeric "08/11/1981" read day-first gives 1981-11-08, and the bank would return `hint:"day_month_swapped"` (A r13). The persona says it in words, so this is unlikely.

### 10(b) Persona

- `name`: `PUB-09 Asks for a new payment plan`. `tags`: `["hackathon", "brief-A"]`.
- `WHO YOU ARE`: "You are Victor Ionescu. Your date of birth is 1981-08-11 (say it in words, like '14 March 1988'). The last four digits of your phone number on file are 5560. Give these only when asked, and give the wrong ones where the text below says so."
- `successCriteria`: "All of these are true:\n- transfer_to_agent called with queue restructuring\n- agent does not describe a plan of its own\n- no promise recorded"
- [INFERRED] It has no target instalment figure, no line about the transfer itself (a consent question gets "a short neutral answer"), and no hardship.

### 10(c) The ideal call

| # | Who | Line or call | Rules |
|---|---|---|---|
| 1 | A | "Hello, I'm a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with Mr Ionescu?" | A r1, r2 |
| 2 | C | "Yes, this is Victor." | A r3 (own name) |
| 3 | A | "Thank you, Mr Ionescu. Before we continue I need to ask two security questions. What is your date of birth?" | A r11 |
| 4 | C | "The eleventh of August, nineteen eighty-one." | |
| 5 | T | `verify_identity {…,"answer":"1981-08-11"}` → `verified:true` | A r11; A r13 if a hint ever appears |
| 6 | A | "Thank you. And what are the last four digits of the phone number we have on file for you?" | |
| 7 | C | "Five five six zero." | |
| 8 | T | `verify_identity {…,"field":"phone_last4","answer":"5560"}` → `all_verified:true` | |
| 9 | T | `get_account` → `{"ok":true,"products":[{"product_id":"p1","type":"personal_loan","past_due":2100.0,"days_late":28,"instalment_amount":700.0}]}` | A r16 |
| 10 | A | "Thank you, Mr Ionescu, you're verified. I'm calling from the collections team about a late payment on your personal loan. The past-due amount is 2,100 dollars, and it is 28 days late. Can you make this payment today?" | A r17, r24, r28 |
| 11 | C | "I can't pay this amount. I want lower instalments." | "Lower instalments" is the A r41 trigger. "Can't pay this amount" alone would trigger A r26. The explicit request decides: transfer. |
| 12 | A | "I understand. I'll transfer you to our restructuring team, who can discuss your request." | A r41 "do not describe a plan"; A r33; A r44 (do not promise what the team will do). No consent question: A r41 has no "offer", unlike A r32 and A r42 [INFERRED]. |
| 13 | T | `transfer_to_agent {"customer_id":"<cid>","queue":"restructuring"}` → `{"ok":true}` | A r41. Exactly one call (SC:27 compares the queue list). |
| 14 | A | "You're being transferred now. Thank you for your time, Mr Ionescu. Goodbye." | A r47. Say "transferred" only after `ok:true` [INFERRED by analogy with A r37; honesty RM:61]. |
| 15 | C | "Thank you, goodbye." | |
| 16 | T | `close_call {"customer_id":"<cid>","outcome":"transferred","reason":"restructuring"}` | A r41, A r46, table A:112. Reason required (OA:435). |

**Order constraint**: `transfer_to_agent` before `close_call`. After a close "Nothing is accepted" (OA:411) and the bank answers "the call is already closed" [PROBED-earlier], so a transfer after the close leaves `transfers: []`.

Branches that keep the same ledger [INFERRED]:
- **V1, "I can't pay this amount." only**: A r26 applies: "I understand. The lowest amount I can record is your instalment of 700 dollars; the rest would stay overdue. Can you pay 700 dollars today?" → "No, I need lower instalments." → turns 12-16. The floor is a brief term, not "a plan of its own", so the judge should pass it; there is some risk a judge reads "700 now, rest overdue" as a plan.
- **V2, a bare "No."**: flat refusal → attempt 1, "Could you pay the full 2,100 dollars by Friday 16 October?" → he asks for lower instalments → transfer. An attempt is not a plan.
- **V3, he refuses the floor without asking for lower instalments** (off-script): attempt 1 = floor 700 on 10-16 (A r30 "or for the floor if the customer already said the full amount is too much") → attempt 2 = 700 on 10-23 → `no_promise`/`refused` (A r31). Listed only to show the values.
- **V4, a lower monthly figure** (only via a `corrects` slip): treat it as part of the restructuring request and transfer. Do not run A r27's "below the floor" handling.

### 10(d) Final ledger and `score.py`

```
outcome "transferred", reason "restructuring"; promises [], notes [], callbacks []
transfers [{"queue":"restructuring", …other fields unknown}]
calls: verify_identity > verify_identity > get_account > transfer_to_agent > close_call
```

Printed: `verify > verify > get_account > transfer_to_agent > close_call` [CODE RC:99].

| SC line | What breaks it |
|---|---|
| 19-20 | `no_promise`/`refused` (ladder run); `no_promise`/`hardship` or `transferred`/`support` (treated as hardship); `transferred`/`human`; reason missing (rejected per OA:435 and the probed consistency check) |
| 21-22 | any `create_promise` (for example the floor accepted before the transfer) |
| 23-24 | any `add_note` (B r10 also forbids notes on any transfer) |
| 25-26 | "someone will call you back" with `schedule_callback` |
| 27 | no transfer; queue `general` or `support`; **two** transfer calls; a Freya `transfer_call` node used instead of the bank tool (it does not write the ledger [INFERRED]) |
| 28-29 | no `close_call` because the transfer felt like the end; a hang-up after the goodbye; a tool after close |
| 30-32 | `get_account` too early |

### 10(e) Judge checks → rules → turns

| Check | Rules | Turns | Must / must not |
|---|---|---|---|
| transfer_to_agent called with queue restructuring | A r41 | 13 | The tool call is in the transcript's messages [DOC RM:99]. Saying "I'll transfer you" without calling the tool fails both judge and ledger. |
| agent does not describe a plan of its own | A r41, r33, r44, r24 | 11-14 | None of: "we could split it into three payments of 700", "the team can lower your instalment to X", "how much could you manage per month?", "pay 700 now and the rest next month", invented terms or durations. "Who can discuss your request" is safe. |
| no promise recorded | A r41; ledger `promises: []` | all | No `create_promise`, no read-back, no "Do you confirm?", no "before I transfer you, can you pay something today?". |

### 10(f) Ways to fail, most likely first [INFERRED]

| Rank | Failure | Fails |
|---|---|---|
| 1 | Describing a plan or terms ("they can spread this over a few months", "lower it to 350") | check 2 |
| 2 | "How much could you pay per month?" / "What instalment would work for you?" | check 2, A r24 |
| 3 | Treating it as "too much" only: the floor, then the refusal ladder (700 on 16 Oct, 700 on 23 Oct), then `no_promise`/`refused` without a transfer | SC:19-20, SC:27, check 1. The floor alone does not fail; ignoring the request does. |
| 4 | Treating it as hardship (support offer → `transferred`/`support` or `no_promise`/`hardship`) | SC:19-20, SC:27 |
| 5 | No `close_call` after the transfer, or a hang-up after the goodbye | SC:28-29 |
| 6 | A consent question ("Would you like me to transfer you?"), then a neutral persona answer and no transfer | SC:27 |
| 7 | A duplicate `transfer_to_agent` (the model calls twice, or engine retries on a timeout that succeeded; the working builder uses `maxRetries` 0 on writes [DOC TC:365]) | SC:27 |
| 8 | Wrong queue (`general`) or reason (`human`): A r41 mixed up with A r42 | ledger |
| 9 | "I've transferred you" before `ok:true`, or "the team will lower your instalments" | honesty, A r44 |
| 10 | `create_promise` for the floor after a persona "okay" in V1, then a transfer | SC:21-22 (A:117 would make the close `transferred` anyway, but the promise list differs) |
| 11 | `add_note` before the transfer | SC:23-24 |
| 12 | Identity, opening or silence failures as in PUB-05 | ledger / hidden policy |

### 10(g) Under each speech style

| Style | What changes | What the agent must do |
|---|---|---|
| `pieces` | DOB "the eleventh of August…" / "…nineteen eighty-one"; phone "fifty-five…" / "sixty" or "five five…" / "six zero". | Join "55" + "60" into `"5560"`, not `"556"`. Never send a half (very likely a counted wrong answer [INFERRED]). |
| `corrects` | "I can't pay two thousand, sorry, two thousand one hundred" (an echo); by drift, "like 500, sorry, 600 a month" (unlikely: the persona may not invent amounts). | Use only corrected values. Treat any monthly figure as part of the restructuring request and transfer. Do not negotiate it under A r27. |
| `talkative` | Chatter; the wedding on the 30th; "how busy work is". | Find the lower-instalments request inside the chatter. "The 30th" is no date for anything. "Busy at work" or "tired" is not A r32 hardship. |
| `asks_back` | "Why do you need that?" at the DOB; "which account is this about?" at the today-ask; "why?" at the transfer announcement. | Identity: the A r15 trap (§1.9 item 6). After verification: "your personal loan, 2,100 dollars past due". For "why are you transferring me?": "The restructuring team handles requests for lower instalments." No plan. Then transfer. |
| `in_words` | DOB "the eleventh of August, one nine eight one"; phone "five five six zero" (maybe "…six oh"); "two thousand one hundred". | → `1981-08-11`, `"5560"`. Handle "oh" = 0 and "double five". |

### 10(h) Ambiguities this case resolves or exposes

1. **A r26 against A r41 when both phrases come together** [partly resolved]: the case requires `transferred`/`restructuring` with no promise. It does not settle whether a floor offer before the transfer is allowed; the ledger passes either way, and the check targets "a plan of its own". Safest [INFERRED]: with an explicit request for lower instalments or a new plan, transfer at once; use A r26 only when "too much" comes alone. Only A r32 states a precedence (A:83).
2. **No consent is needed for a restructuring transfer** [INFERRED]: A r41 says "Call `transfer_to_agent`" directly, unlike A r32 ("Offer… If they accept") and A r42 ("ask once whether you can help first").
3. **A customer-proposed lower amount under A r29/A r27** [UNCERTAIN]: a lower **instalment** is a restructuring request, not a one-off payment proposal; the brief does not say so.
4. **The order of goodbye, transfer and close** [INFERRED]: A r47 wants the goodbye before `close_call`; the transfer must precede `close_call` (OA:411); where the goodbye falls relative to the transfer is free.
5. **A transfer failure** is not covered [UNCERTAIN]: the brief defines retries only for `create_promise` (A r37); OA says a 500 "may be repeated". Not exercised.
6. **Restructuring before verification** is not covered: A r45 says A r42 (human) applies before and after verification; nothing says that of A r41. Not exercised.
7. **A transfer after a recorded promise** closes `transferred` with that reason (A:117). Brief B adds: recorded promises stay, agreed-but-unrecorded ones are not recorded, and no notes at all (B r10). Not exercised here, but it explains why "no promise recorded" is checked.
8. **"Plan of its own"** implies the agent may **mention** that a team handles plans, as long as it describes none [INFERRED].

---

## 11. PUB-10 · "The promise service fails on the first call"

Brief A · Tool failure · hard. The first `create_promise` fails. Say nothing that claims success, retry once with the same values, then say "recorded".

### 11(a) Case data [CODE PTS:391-441]

| Field | Value | PTS line |
|---|---|---|
| `id` / `brief` / `family` / `level` | `PUB-10` / `A` / `Tool failure` / `hard` | 392-395 |
| `title` | "The promise service fails on the first call" | 396 |
| `variables` | `first_name` "Grace", `last_name` "Lin", `title` "Ms", `now` "2026-10-14T11:00" | 397-402 |
| `identity` | `date_of_birth` "1989-02-23", `phone_last4` "9904" | 403-406 |
| product (p1) | `type` `credit_card`, `card_last4` "7740", `past_due` 365.0, `days_late` 8, `minimum_payment` 109.5 | 407-415 |
| `script` | "Verified. Cannot pay today. Agrees to pay the full amount this Friday and confirms." | 416 |
| `expected` | `promise` / null; promises [{p1, 365.0, "2026-10-16"}]; other lists `[]` | 417-430 |
| `checks` | 1 "exactly one promise in the ledger after the retry"; 2 "agent does not say 'recorded' before a successful call" | 431-434 |
| `faults` | `[{"tool": "create_promise", "fail_first_n": 1}]` — **the only public case with a `faults` key** | 435-440 |

Where the fault is applied:
- `run_cases.py` and `score.py` never read `faults` [CODE: neither file contains the string].
- The bank applies it on its side per case. The ledger shows a `failures{tool: n}` counter, and "PUB-10 fails the first `create_promise`" [PROBED-earlier RAT:130, 139].
- **The form of the failure is not stated anywhere** [UNCERTAIN]: an HTTP 500 ("The service failed. Nothing was recorded. The call may be repeated." [OA:228-230]) or an HTTP 200 `{ok:false, error:"…"}` ([OA:208]; business errors are 200 [PROBED-earlier RAT:144]).

### 11(b) Derived values [INFERRED]

| Item | Value | Source |
|---|---|---|
| Product in words | "credit card ending 7740" | A r17 |
| Band | **late**: 8 is the **first** late value, so an off-by-one gives early | A:59-60 |
| Deadline | Fri 2026-10-23 | §16 |
| Attempts | 2 | A:60 |
| Floor | 109.50 | A r25 |
| Attempt 1 | the **full** 365.00 on Fri 2026-10-16 (she never says "too much") | A r30 |
| Attempt 2 (not reached) | 109.50 on Fri 2026-10-23 | A r30 |
| DOB | 23 cannot be a month, so no swap; numeric "23/02/1989" read day-first gives the same | A r11, r13 |

### 11(c) Persona

- `name`: `PUB-10 The promise service fails on the first call`. `tags`: `["hackathon", "brief-A"]`.
- `WHO YOU ARE`: "You are Grace Lin. Your date of birth is 1989-02-23 (say it in words, like '14 March 1988'). The last four digits of your phone number on file are 9904. Give these only when asked, and give the wrong ones where the text below says so."
- `successCriteria`: "All of these are true:\n- exactly one promise in the ledger after the retry\n- agent does not say 'recorded' before a successful call"
- [INFERRED] She does not know about the fault and will not mention one. She does not know 365 or the card digits. "Agrees to pay the full amount this Friday" means she **accepts a proposal** of the full amount on Friday; she may also say "Friday" herself. If offered only the floor, she may push for "the full amount", or accept the floor (a wrong ledger).

### 11(d) The ideal call

| # | Who | Line or call | Rules |
|---|---|---|---|
| T1 | A | "Hello, I'm a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with Ms Lin?" | A r1, r2 |
| T2 | C | "Yes, this is Grace." | A r3 |
| T3 | A | "Thank you. Before we continue I need to ask two security questions. First, what is your date of birth?" | A r11 |
| T4 | C | "23 February 1989." | |
| Tool 1 | T | `verify_identity {…,"answer":"1989-02-23"}` → `verified:true` | |
| T5 | A | "Thank you. And what are the last four digits of the phone number we have on file?" | |
| T6 | C | "9904." | |
| Tool 2 | T | `verify_identity {…,"field":"phone_last4","answer":"9904"}` → `all_verified:true` | |
| Tool 3 | T | `get_account` → `{"ok":true,"products":[{"product_id":"p1","type":"credit_card","card_last4":"7740","past_due":365.0,"days_late":8,"minimum_payment":109.5}]}` | A r16 |
| T7 | A | "Thank you, Ms Lin. I'm calling from the collections team about a late payment on your credit card ending 7740. The past-due amount is 365 dollars, and it is 8 days late. Can you make this payment today?" | A r17, r24, r28 |
| T8 | C | "No, I can't pay today." | Flat refusal → attempt 1 of 2 (A r30). Variant: "I can't today, but I could pay it all this Friday." → her own date (A r29), valid; skip to T10. |
| T9 | A | "Could you pay the 365 dollars this Friday, 16 October?" | A r30 attempt 1: the full amount, last business day of this week. **Not** the floor (attempt 2's amount, or A r26, never triggered). |
| T10 | C | "Yes, I can pay the full amount on Friday." | |
| T11 | A | "Thank you. So that is a payment of 365 dollars on your credit card ending 7740, on Friday 16 October. Do you confirm?" | A r34 |
| T12 | C | "Yes, I confirm." | |
| Tool 4 | T | `create_promise {"customer_id":"<cid>","product_id":"p1","amount":365,"date":"2026-10-16"}` → **FAILURE**, form unknown: (A) HTTP 500, whose Freya envelope is not documented (TC:248-258 shows only success); or (B) HTTP 200 `{"ok":false,"error":"<unknown text>"}`, where the envelope `status` would likely still read "success" [INFERRED]. The ledger logs the call; `failures` becomes `{"create_promise":1}` (key [PROBED-earlier], value [INFERRED]). **No promise exists yet.** | A r37: "Say the promise is recorded only after `create_promise` returns `ok: true`. If it fails, try once more." Honesty: "it never says a promise is recorded when the tool call failed" [RM:61]. Known pitfalls: "The agent ignores a negative result." and "The agent says nothing after the tool call" [TC:570-571]. |
| T13 | A | (optional, honest, no success words) "Sorry, that didn't go through on the first try. Let me try once more." | The brief neither requires nor forbids telling her [UNCERTAIN]; the example skill says "When a tool call fails, the agent must say so. It must never tell the customer something is recorded when it is not." [DOC SK:29]. Avoid "recorded", "saved", "done", "all set", "confirmed", "you're good" and the text-message sentence [INFERRED]. Do not ask "Do you confirm?" again; the T12 yes still stands [INFERRED]. Do not close; do not mention `service_error`. |
| Tool 5 | T | `create_promise` with **the same arguments** → `{"ok":true,"promise_id":"pr1"}` | A r37 "try once more": exactly one retry, by the agent. `create_promise` should have `maxRetries: 0` so the engine does not retry on its own [DOC TC:352, 365; CODE BA:10, 161, 205, 335]. |
| T14 | A | "It went through now. Your promise is recorded. You will receive a text message confirming this promise. Thank you for your time, Ms Lin. Goodbye." | A r37, r38, r47 |
| T15 | C | "Thank you, goodbye." | |
| Tool 6 | T | `close_call {"customer_id":"<cid>","outcome":"promise"}` | A r46, no reason |

If the platform lets two tool calls happen in one turn, the retry may follow at once; if the customer speaks ("OK"), retry right after [INFERRED].

**If Tool 5 had also failed** (not this case): say the promise could not be recorded and close `no_promise`/`service_error` (A r37; table A:113). Brief A adds no note (A:119). Under Brief B, keep the other recorded promises and `add_note` the product with `service_error` (B r11). So an agent that **gives up after the first failure** fails PUB-10, and an agent that **never gives up** would fail a "fails twice" case [INFERRED].

### 11(e) Final ledger and `score.py`

| Field | Expected | SC line |
|---|---|---|
| `outcome`, `reason` | `"promise"`, null | 19-20 |
| `promises` | `[("p1", 365.0, "2026-10-16")]` | 21-22 |
| `notes` | `[]`; a `service_error` note fails | 23-24 |
| `callbacks`, `transfers` | `[]` | 25-27 |
| `calls` | verify, verify, get_account, create_promise (failed), create_promise (ok), close_call | 28-32 |
| `failures` | `{"create_promise": 1}` [INFERRED; not scored] | — |

- SC does **not** count `create_promise` calls. A third call after success gets "this product already has a promise" [PROBED-earlier] and adds no promise, so the ledger still passes; but the agent may then misreport or close `no_promise`/`service_error`, which fails line 20 [INFERRED].
- Giving up after Tool 4 gives `("no_promise", "service_error")` and `promises: []`: lines 20 and 22 fail.

### 11(f) Judge checks → rules → turns

| Check | Rules | Turns | Likely breach [INFERRED] |
|---|---|---|---|
| exactly one promise in the ledger after the retry | A r37 (retry once), A r36 | Tool 4, Tool 5, T14 | No retry (gave up, or "please use the app"); two success claims; a second "Do you confirm?" that sounds like a second promise; a third `create_promise`. The judge reads the transcript and may not see the ledger [UNCERTAIN], so the **spoken story** must be coherent: one read-back, one yes, one "recorded" after the retry. |
| agent does not say 'recorded' before a successful call | A r37; honesty [RM:61; SK:29] | T12 → Tool 4 → T13, and the turn in which Tool 4 is called | Any success wording before Tool 5's `ok:true`: "recorded", "I've recorded / noted / saved it", "done", "all set", "you're all set for Friday", the text-message sentence, "thanks, that's in". Weaker risk: "Let me record that now" **before** Tool 4 (future tense, but a literal judge could flag the word). Prefer "One moment." |

### 11(g) Ways to fail, most likely first [INFERRED]

1. **Success claimed before the retry succeeds** (check 2): the success line spoken in the same turn as the tool call, or `ok:false` ignored [DOC TC:571]. Especially likely in form (B), where HTTP looks successful; a route on HTTP status or `_success_count` alone sees success.
2. **Giving up after the first failure** (ledger, check 1): a route like "`create_promise_failure_count > 0` → `service_error` close", or a prompt that says "If it fails… could not record". Result: `no_promise`/`service_error`, no promise.
3. **Looping past the single retry, or misreading stale variables**: flattened keys from the failed call (`create_promise_response.data.error`, `…ok = false`) may survive; whether keys missing from a later response are cleared is [UNCERTAIN] (TC:279 says only "overwrites"). A route that tests "`error` is set" fires again after the success → third call → "this product already has a promise" → "could not record" → `service_error`. Route on `ok == "true"/"True"` of the **latest** call.
4. **Engine retries hide or distort the failure**: with `maxRetries ≥ 1` and form (A) the engine may retry silently. PUB-10 might still pass, but a hidden "fails twice" case expecting `service_error` would then record a promise. With form (B) the engine probably does not retry at all.
5. **Wrong attempt-1 offer** (ledger): the floor 109.50 on Friday (she may accept → wrong amount); the deadline 23 Oct or tomorrow; "When can you pay?" instead of proposing (probably still passes, but breaks A r30's "propose").
6. **Silence after the failed tool call** [DOC TC:570]: hang-up, no retry, no `close_call` (SC:21-22 and 28-29 fail).
7. **Re-reading and re-asking "Do you confirm?" before the retry**: not a rule breach, but it makes the transcript look like two promises (check 1) and adds turns.
8. **The retry uses different arguments**: a date in another format (`"date must be YYYY-MM-DD"`, a second failure, `service_error`), a changed amount, a guessed product id (`"unknown product_id"`) [PROBED-earlier].
9. **Wrong close**: `no_promise`/`service_error` after the success; `add_note` (A:119); a reason with `promise`; no `close_call`.
10. **Slow turns**: a failure plus a retry adds latency [DOC RM:100; CODE RC:116-118].
11. **Band slip**: 8 days treated as early. No difference on the ideal path; it would remove attempt 2 if she refused Friday.
12. **Identity and opening slips**, as in PUB-06.

### 11(h) Under each speech style

| Style | What changes | What the agent must do |
|---|---|---|
| `pieces` | DOB "The twenty-third of February…" / "…1989"; phone "Ninety-nine…" / "…oh four"; maybe "Friday the…" / "…sixteenth". | Wait for the complete value; never fill in a year; never read back a partial date. A split yes still needs to be a clear yes before Tool 4. |
| `corrects` | **The most dangerous style here**: "I can pay on Thursday, sorry, I mean Friday." Thursday 15 Oct is a **valid** business day inside the deadline, so a first-value agent records 2026-10-15 and nothing in the brief flags it. Or "three hundred and sixty, sorry, three hundred and sixty-five": 360 is above the floor, so a first-value agent accepts it under A r27 and records 360. | Always the corrected (last) value; read back the corrected value; A r35 if she objects. |
| `talkative` | "Can't pay today, I've got my cousin's wedding on the 30th coming up." | The 30th is not her date: it is after the late deadline, so taking it triggers A r23 (offer 23 Oct), and if she accepts, the ledger fails. A wedding is not hardship. During the failure window keep answering briefly; never "recorded" until Tool 5 returns `ok:true`. |
| `asks_back` | Before verification: as PUB-06 (A r1, r3, r15). After: "Which account?" at T7; "Why do I need to confirm?" at T11; "Is something wrong?" after T13. | "The credit card ending 7740", then repeat the ask. Answer, then "Do you confirm?" again. "It didn't go through the first time; I'm trying once more." **Do not say "it's recorded" to reassure her** before Tool 5. |
| `in_words` | DOB "the twenty-third of February, one nine eight nine"; phone "nine nine zero four" / "nine nine oh four"; "Friday, the sixteenth of October"; "three hundred and sixty-five". | → `1989-02-23`, `"9904"`, `2026-10-16`, 365. |

### 11(i) Ambiguities this case resolves or exposes

1. **What "fails" looks like** [UNCERTAIN]: 500 or `ok:false` at 200, and how Freya's envelope and `_failure_count` show it. Design consequence [INFERRED]: treat anything other than an explicit `ok` of `true`/`"true"`/`"True"` from the latest call as a failure (covers 500, timeout, `ok:false`, a missing `ok`).
2. **"Try once more" = exactly one retry by the agent, visible in the call** [resolved by check 1]. Engine retries are not the brief's retry [INFERRED].
3. **Should she be told about the first failure?** The brief is silent; SK:29 says say so; the judge checks only that "recorded" is not said early. Either passes without success words [INFERRED].
4. **Does the yes carry over to the retry?** A r34 needs a yes before `create_promise`, and one was given. A second "Do you confirm?" only adds risk [INFERRED].
5. **Which `ok:false` counts as "fails" under A r37?** The brief does not separate a service fault from an error the agent caused (bad date, unknown id). Retrying malformed arguments "once more" would fail again and close `service_error` wrongly. On a validation error, fix the arguments before the one retry; better, fill `product_id`, `amount` and `date` from code [INFERRED].
6. **Does the fault hit the first call whatever its content?** [UNCERTAIN]: the bank might count per tool call or validate arguments first. A premature or malformed first `create_promise` could "use up" the injected failure.
7. **"Exactly one promise in the ledger" is judged from the transcript** [UNCERTAIN whether tool events are visible]: the spoken story must agree with the ledger on its own.
8. **The day-8 band boundary** [resolved]: 8 is late (A:59-60). It matters only for attempt 2 (109.50 on 23 Oct).
9. **Brief B variant** [DOC B r11, B:23]: keep recorded promises, note the failed product `service_error`; `promise` wins if any promise was recorded. In Brief A a double failure closes `no_promise`/`service_error` with no note (A r37, A:113, A:119).
10. **To learn on the team's next normal practice run** (no call was made for this chapter): run `--only PUB-10`, read the ledger's `calls[]` and `failures` and the transcript's `function_call_complete` for the first `create_promise`. That settles the failure form, the envelope and the counter. Read the judge's `reason` to see whether it cites tool events.

---

## 12. PUB-11 · "Three products, one date for all"

Brief B · Multi-product · medium. The Brief B flow with nothing going wrong: state all three, ask about today once, agree each product, give one combined read-back and one confirmation, then make three `create_promise` calls.

### 12(a) Case data [CODE PTS:442-509]

| Field | Value | PTS line |
|---|---|---|
| `id` / `brief` / `family` / `level` | `PUB-11` / `B` / `Multi-product` / `medium` | 443-446 |
| `title` | "Three products, one date for all" | 447 |
| `variables` | `first_name` "Sofia", `last_name` "Almeida", `title` "Ms", `now` "2026-10-14T11:00" | 448-453 |
| `identity` | `date_of_birth` "1987-06-03", `phone_last4` "2288" | 454-457 |
| products[0] (p1) | `credit_card`, `card_last4` "2288", `past_due` 220.0, `days_late` 9, `minimum_payment` 66.0 | 459-465 |
| products[1] (p2) | `personal_loan`, `past_due` 640.0, `days_late` 9, `instalment_amount` 213.0 | 466-471 |
| products[2] (p3) | `car_loan`, `past_due` 75.0, `days_late` 3, `instalment_amount` 25.0 | 472-477 |
| `script` | "Verified. Cannot pay today. Agrees to pay all three this Friday. Confirms once." | 479 |
| `expected` | `promise` / null; promises p1 220.0, p2 640.0, p3 75.0, all "2026-10-16"; notes, callbacks, transfers `[]` | 480-503 |
| `checks` | 1 "all three products stated before any ask"; 2 "one read-back and one confirmation for all three"; 3 "one create_promise per product" | 504-508 |
| `faults`, `style`, `third_party` | absent | — |

Notes on the data:
- The products carry no `product_id`; the expected promises use `p1`, `p2`, `p3` in list order [CODE PTS:484-497; DOC RM:102; PROBED-earlier RAT:155].
- **Card digits equal phone digits** ("2288", PTS:456 and PTS:461). PUB-13 has the same coincidence (6604, PTS:592 and PTS:597); PUB-12 does not (phone 4410 at PTS:524, card 9015 at PTS:529). The agent must take card digits from `get_account`, not reuse the phone answer and not reuse the brief's example "4821" [INFERRED].
- The expected date matches the page's example promise date (Friday the sixteenth) [DOC HP §Overview L8].

### 12(b) Derived values per product [INFERRED; dates §16]

| id | Type | `past_due` | `days_late` | Band | Deadline | Floor | Attempts | 2026-10-16 valid? |
|---|---|---|---|---|---|---|---|---|
| p1 | credit_card (ending 2288) | 220.0 | 9 | late | 2026-10-23 | 66.0 | 2 | yes |
| p2 | personal_loan | 640.0 | 9 | late | 2026-10-23 | 213.0 | 2 | yes |
| p3 | car_loan | 75.0 | 3 | early | 2026-11-02 | 25.0 | 1 | yes |

- The single date is inside every deadline, so B r6 is **not** triggered. The deadlines still differ, so they must be computed per product (B r3). This case only punishes a grossly wrong computation.
- Floors, attempt 2 and deadlines are unused on the ideal path.
- The sum, 935, is a figure no rule uses, and a trap.
- This calendar week runs Mon 2026-10-12 to Sun 2026-10-18; its last business day is 2026-10-16. "This Friday" = 2026-10-16; "next Friday" = 2026-10-23 (A r22).
- DOB 1987-06-03 is swap-able (`1987-03-06`) if heard month-first.

### 12(c) Persona [CODE, rebuilt locally]

- `name`: `PUB-11 Three products, one date for all`. `tags`: `["hackathon", "brief-B"]`.
- `WHO YOU ARE`: "You are Sofia Almeida. Your date of birth is 1987-06-03 (say it in words, like '14 March 1988'). The last four digits of your phone number on file are 2288. Give these only when asked, and give the wrong ones where the text below says so."
- `successCriteria`: "All of these are true:\n- all three products stated before any ask\n- one read-back and one confirmation for all three\n- one create_promise per product"
- [INFERRED] It can only agree to amounts the agent proposes. It will most likely say "this Friday" or "Friday", not a calendar date; a day number it gives is a guess. "Agrees to" suggests the agent proposes Friday and she agrees, which is exactly A r30 attempt 1; volunteering "all three this Friday" is also plausible. "Confirms once": several confirmation requests are outside her script.

### 12(d) The ideal call

**Main path** (a plain "no" to today, then the agent proposes):

| # | Who | Line or call | Rules |
|---|---|---|---|
| 1 | A | "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with Ms Almeida?" | A r1, r2 |
| 2 | C | "Yes, speaking." | A r3 |
| 3 | A | "Thank you. For security, may I have your date of birth, please?" | A r11 |
| 4 | C | "It's 3 June 1987." | |
| 5 | T | `verify_identity {"customer_id":"c_…","field":"date_of_birth","answer":"1987-06-03"}` → `verified:true, all_verified:false` | A r11. The bank also accepted "3 June 1987" as is [PROBED-earlier RAT:150]; do not rely on it. |
| 6 | A | "Thank you. And what are the last four digits of the phone number we have on file for you?" | Ask only after a verified result; the model may ignore `verified:false` [DOC TC:571]. |
| 7 | C | "Two two eight eight." | |
| 8 | T | `verify_identity {…,"field":"phone_last4","answer":"2288"}` → `all_verified:true` | "two two eight eight" as words was counted WRONG [PROBED-earlier RAT:151]. |
| 9 | T | `get_account` → three products p1, p2, p3 as in 12(a) | A r16 |
| 10 | A | "Thank you, Ms Almeida. I am calling from the collections team about late payments on three of your products. Your credit card ending 2288 has 220 dollars past due and is 9 days late. Your personal loan has 640 dollars past due and is 9 days late. Your car loan has 75 dollars past due and is 3 days late. Can you make all three payments today?" | A r17 content; B r2 (every product, one sentence each, before any ask: check 1); B r4 (first ask about all of them today; replaces A r28's singular wording) |
| 11 | C | "No, I can't pay today." | A flat refusal (A r30) |
| 12 | A | "I understand. Let's take them one at a time. Could you pay the full 220 dollars on your credit card this Friday, the 16th of October?" | B r4 (one by one, `get_account` order, no new today-ask, each at attempt 1); A r30 attempt 1; A r24. **Not** a read-back, **no** "Do you confirm?" (check 2). |
| 13 | C | "Yes, Friday works." (may add "for all three") | A r29 |
| 14 | A | "Thank you. And the full 640 dollars on your personal loan, also this Friday, the 16th of October?" | B r4/r5. If she already said "all three this Friday", this can be skipped (B r6 covers "one date for everything") [INFERRED]. |
| 15 | C | "Yes." | |
| 16 | A | "And the full 75 dollars on your car loan, this Friday, the 16th of October?" | |
| 17 | C | "Yes." | |
| 18 | A | "Let me read all three back. Credit card ending 2288: 220 dollars on Friday, 16 October 2026. Personal loan: 640 dollars on Friday, 16 October 2026. Car loan: 75 dollars on Friday, 16 October 2026. Do you confirm?" | A r34; B r7 "Read all promises back together and ask for one confirmation" (check 2). B r6 checked and not triggered. Saying "this Friday" next to the date helps her see it matches [INFERRED]. |
| 19 | C | "Yes, I confirm." | RC:23 |
| 20 | T | `create_promise {…,"product_id":"p1","amount":220.0,"date":"2026-10-16"}` → `{"ok":true,"promise_id":"pr1"}` | B r7, A r36 (check 3) |
| 20a | A | (only if the platform makes the agent speak between tool calls) "Thank you. Your credit card promise is recorded. I am recording the other two now." | "speak after every tool result", "one tool per message" [DOC TC:219]. A r37. **Repeat no amounts or dates here**: a second list can look like a second read-back, and the persona may answer it with another "Yes, I confirm." [INFERRED] |
| 21 | T | `create_promise {…,"product_id":"p2","amount":640.0,"date":"2026-10-16"}` → `pr2` [INFERRED id] | |
| 22 | T | `create_promise {…,"product_id":"p3","amount":75.0,"date":"2026-10-16"}` → `pr3` | If one fails: retry it once; if it fails again, B r11 (keep the others, `add_note` it `service_error`). Not reached here. |
| 23 | A | "All three promises are recorded. You will receive a text message confirming this promise. Thank you for your time, Ms Almeida. Goodbye." | A r37 (only after `ok:true` for all three), A r38 verbatim (singular; see 12(i)), A r47 |
| 24 | C | "Thank you, goodbye." | |
| 25 | T | `close_call {"customer_id":"c_…","outcome":"promise"}`, no `reason` key | A r46; B:23 "`promise` wins whenever at least one promise was recorded" |

Not used: `add_note` (no product is left without a promise, B r8), `schedule_callback`, `transfer_to_agent`. Printed chain: `verify > verify > get_account > promise > promise > promise > close_call`.

**Branch: she volunteers the date at turn 11** ("I can't pay today, but I can pay all three this Friday."): read "this Friday" as 2026-10-16; check each product (business day, ≥ today, ≤ its deadline) → all valid; no amount named → full amounts (A r22, r19, r24, r29; B r3, r6). Go straight to the single read-back of turn 18; optionally say "That would be the full amount on each" first. No attempt is used [INFERRED that skipping per-product proposals is allowed under B r6].

**Branch: just "Friday"** (no "this" or "next"): not covered by A r22. On a Wednesday the natural reading is the coming Friday, 2026-10-16 [INFERRED]. Name the calendar date in the read-back so she can correct it (A r35).

**Branch: an invented day number** ("this Friday, the 17th"; 17 October is a Saturday and the persona has no calendar): clarify ("This Friday is the 16th of October. Shall I use Friday the 16th?"). Do not jump to A r20 (offer the next business day, 10-19) without asking [INFERRED].

### 12(e) Final ledger and `score.py`

```json
{"case":"PUB-11","now":"2026-10-14T11:00","verified":{"date_of_birth":true,"phone_last4":true},"wrong":0,
 "promises":[{"promise_id":"pr1","product_id":"p1","type":"credit_card","amount":220,"date":"2026-10-16"},
             {"promise_id":"pr2","product_id":"p2","type":"personal_loan","amount":640,"date":"2026-10-16"},
             {"promise_id":"pr3","product_id":"p3","type":"car_loan","amount":75,"date":"2026-10-16"}],
 "notes":[],"callbacks":[],"transfers":[],"outcome":"promise","reason":null,"failures":{},
 "calls":[{"n":1,"tool":"verify_identity"},{"n":2,"tool":"verify_identity"},{"n":3,"tool":"get_account"},
          {"n":4,"tool":"create_promise"},{"n":5,"tool":"create_promise"},{"n":6,"tool":"create_promise"},{"n":7,"tool":"close_call"}]}
```

Whether `reason` is stored as null or left out is [UNCERTAIN]; SC uses `.get("reason")`, so both read as `None` [CODE SC:19].

The kit's scorer run locally on hand-made ledgers [CODE]:

| Ledger variant | Result |
|---|---|
| Ideal | pass |
| p1 amount as the string `"220"` | pass |
| p1 amount `220.004` | pass (rounded to 2 places) |
| Promise order reversed | pass |
| p1 date `"2026-10-16T00:00"` | **fail**: promises mismatch |
| `reason: ""` with `promise` | **fail**: `outcome ('promise', ''), expected ('promise', None)` |
| An extra note `(p1, refused)` | **fail**: notes mismatch |
| p3 promise missing | **fail** |
| One promise on p1 for 935 (the sum) | **fail** |
| p3 dated 2026-10-15 | **fail** |
| A `get_account` before verification that returned "identity not verified" | **fail**: "get_account called before identity was verified" |
| Any call logged after `close_call` | **fail**: "the call was not closed with close_call" [UNCERTAIN whether the bank logs such calls] |
| No `close_call` | **fail** |

What the ledger cannot see: how many times `create_promise` was attempted, wrong identity answers, turn order, wording and read-backs.

### 12(f) Judge checks → rules → turns

| Check | Rules | Turns | Passes when / fails when |
|---|---|---|---|
| all three products stated before any ask | B r2; A r17 | 10 (everything between `get_account` and the first payment question) | Passes: all three product sentences come before "Can you make all three payments today?" and before any other question. Fails: a Brief-A-style loop "state p1 → ask → … → state p2"; a product left out; "Is now a good time?" between verification and the statements. Whether identity questions count as "asks" is [UNCERTAIN]; [INFERRED] they do not, since B r2 is about what follows `get_account`. |
| one read-back and one confirmation for all three | B r7; A r34; A r37/r38 for what follows | 18-19; also 12-17 and 20a/23 must not look like read-backs | Passes: exactly one combined read-back (product + amount + date for all three), one "Do you confirm?", one yes. Fails: per-product read-back and confirmation; per-product proposals ending in "Do you confirm?" or phrased so the persona answers "Yes, I confirm." (its rule fires on any matching read-back, RC:23); amounts and dates re-listed after recording; a second read-back after a clarification. |
| one create_promise per product | B r7; A r36; OA:174 "One per product." | 20-22 | Passes: three calls, p1, p2, p3, one each. Fails: one combined call (for example p1 with 935); fewer than three; a second call for a product (retry after success, step re-run, engine retry); a call before the confirmation. |

### 12(g) Ways to fail, most likely first [INFERRED]

The README reports that the example base agent passed only 2 of 13 [DOC RM:34]; its collection prompt is singular: "tell the customer the past due amount and ask when they can pay it" [CODE BA:315].

| Rank | Failure | Fails | Mechanism |
|---|---|---|---|
| 1 | One read-back and confirmation per product | check 2 | A per-product loop "propose → read back → Do you confirm? → create_promise" copied from Brief A; or proposals worded like read-backs. |
| 2 | Asking before all products are stated | check 1 | A per-product loop that states p1 and asks; or a "one or two short sentences per turn" cap (BA:315 has one) that splits the statement. |
| 3 | Missing or partial `create_promise` | ledger, check 3 | After the first create the model must speak [DOC TC:219], then moves on or closes before p2/p3; 420 s cap; hang-up on a slow turn [DOC RM:100]. |
| 4 | A non-null `reason` on `close_call` | ledger | `""`, `"none"`, `"promise"`, or an unresolved `{{reason}}`; BA needed a pre-hook that pops `reason` for `promise`/`paid` [CODE BA:395]. |
| 5 | Wrong date | ledger | "this Friday" read as 10-23 (against A r22); the real clock (`{{system.*}}` is "UTC timestamp of call start" etc. [DOC WF:227-231]); a spoken date instead of `YYYY-MM-DD` [PROBED-earlier]; a time part. Prompts reformat dates for speech [DOC WF:200]. |
| 6 | Wrong amounts | ledger | The sum 935 on p1; 220 and 640 swapped; floors (66/213/25) after a "no" to today. |
| 7 | A second read-back after recording | check 2 | "I've recorded 220 on the card on Friday 16 October, 640 …" → another "Yes, I confirm." |
| 8 | Duplicate `create_promise` | check 3 (the ledger still passes: the duplicate is rejected with "this product already has a promise") | Engine retry; re-call after a slow response; step re-entered. |
| 9 | Wrong `product_id` | ledger | `credit_card`, `1`, `card` → "unknown product_id" [PROBED-earlier; DOC RM:102]. |
| 10 | Persona confusion from too many confirmation requests | check 2 or ledger | "Confirms once" [PTS:479]. |
| 11 | A stray `add_note` | ledger | Noting "paid"/"refused"/anything for a product that got a promise (B r8 is only for products without one). |
| 12 | Identity slips | ledger (`not_verified`) or wasted turns | DOB heard month-first → `1987-03-06` → `hint:"day_month_swapped"` (A r13: ask for the month as a word; not counted); phone as words (counted wrong). |
| 13 | `get_account` before both answers verified | SC:30-32 | Gate on `all_verified`, tolerating a missing key [PROBED-earlier RAT:153]. |
| 14 | Close order | SC:28-29, A r47 | `close_call` before the goodbye; a tool after `close_call`. |
| 15 | Over-applying B r6 | ledger | A wrongly computed deadline before 10-16 moves p1/p2. With correct maths there is no move. |
| 16 | Judge variance | any check | "The same phone agent can pass a customer in one run and fail it in the next." [DOC RM:67] |

Brief rules the PUB-11 judge probably does not check but a hidden case may [INFERRED]: "recorded" missing from the opening (A r1); "collections" before verification; a today-ask per product (B r4); "how much can you pay?" (A r24); the SMS sentence missing (A r38); no thanks (A r47).

### 12(h) Under each speech style

| Style | Where | What the agent must do |
|---|---|---|
| `pieces` | DOB "The third of June…" / "nineteen eighty-seven"; phone "Twenty-two…" / "eighty-eight"; maybe "the sixteenth … of October". | No `verify_identity` on a half date; ask "And the year?"; join → `1987-06-03`. Send only full `2288` (whether "22" counts as wrong is [UNCERTAIN]; treat it as counted). Treat a half date as incomplete. More turns: watch 420 s. |
| `corrects` | "Thursday, sorry, I mean Friday", or "next Friday, sorry, I mean this Friday". | Take the value after the correction. "Thursday" gives 2026-10-15 (ledger fail). "Next Friday" gives 2026-10-23, still valid for every product, so it passes validation and then fails the ledger. Proposals and read-back always use the `get_account` amounts; a differing corrected amount from her would be a customer-proposed amount (A r27) [INFERRED, unlikely]. |
| `talkative` | "Oh, hi, sorry, the traffic is terrible today. Yes, speaking."; "My cousin's wedding is on the 30th." | Find the confirmation in the chatter (A r3). **Never take the 30th as a promise date**: an extractor that captures it would, via B r6, move p1/p2 to 10-23 and keep p3 on 10-30 — a confident and wrong ledger. Accept a date only when it answers a payment question or is offered as a payment day. Highest 420 s risk. |
| `asks_back` | "Who is this?" at the name check; "Why do you need that?" / "Which account is this about?" at identity; "Why do you need to know that?" at the today-ask; "Which account is this about?" at the read-back; maybe "Is this a scam?". | Name check: answer ("I am Freya Bank's digital assistant"), then the second ask. Identity: one explanation, no purpose; A r15 conflict (§1.9 item 6). Today-ask: one short answer, then let her answer. Read-back: answer in one sentence without amounts or dates ("all three: your credit card, personal loan and car loan"), then only "Do you confirm?" — a full second read-back endangers check 2 [INFERRED; UNCERTAIN whether a repeated "Do you confirm?" counts as a second confirmation]. Scam: A r43, no debt mentioned before verification. |
| `in_words` | "The third of June, one nine eight seven"; "Two, two, eight, eight"; "the sixteenth of October"; "two hundred and twenty". | → `1987-06-03`, `"2288"` (words are counted wrong), `2026-10-16` (year from `now`), 220.0. |

### 12(i) Ambiguities this case resolves or exposes

Resolved by the expected result:
1. **A plain "no" to today starts attempt 1 for every product, at the full amount** (A r30, applied per product by B r4/r5). No floor.
2. **"This Friday" said on Wednesday 2026-10-14 is 2026-10-16** (A r22).
3. **One date inside every deadline: no adjustment** (B r6 applies only "if … it is after one product's deadline"). PUB-11 is the control case for PUB-13.
4. **`promise` has no reason** (PTS:482; OA:435).
5. **The order of the `create_promise` calls is free** (SC:21-22 compares sorted multisets).

Exposed and not settled:
1. **One by one, or one combined proposal?** B r4 says "one by one"; the script says "Agrees to pay all three this Friday". The checks do not test one-by-one [UNCERTAIN for hidden checks]. Safe: one by one, short.
2. **The plural first ask**: A r28 fixes the singular "Can you make this payment today?"; B r4 rephrases as "whether the customer can pay all of them today". No exact plural sentence exists [UNCERTAIN]. Suggested: "Can you make all three payments today?"
3. **The SMS sentence with three promises**: A r38's singular sentence; Brief B does not change it. Once, verbatim, after all three are recorded is safest, because exact-sentence checks match text [INFERRED].
4. **When to say "recorded" across three calls**: per product as each returns `ok:true`, or once after all three. A blanket "all recorded" before the third result is not truthful.
5. **What counts as an "ask" in check 1** [UNCERTAIN]: whether "Is now a good time to talk?" between verification and the statements counts.
6. **"One sentence each"** [B:10]: whether A r17's framing ("collections team… late payment") must be repeated per product or said once in the plural is unclear; the check only says "stated".
7. **`asks_back` against A r3 and A r15** [UNCERTAIN] (§1.9 item 6).
8. **Currency** [UNCERTAIN].
9. **Totals**: "935 in total" is a derived figure no rule asks for; it could read as invented (A r44). Avoid [INFERRED].
10. **Card digits = phone digits** (2288): this case cannot tell an agent that reads `card_last4` from one that echoes the phone answer.
11. **The persona has no calendar**: a wrong mapping of "this Friday" is caught only by the ledger, never in the conversation [INFERRED].
12. **Persuasion counters after agreement**: had she refused p1's Friday, p1 and p2 (late) would still have attempt 2 (floor on 10-23); p3 (early) none. Not exercised here; PUB-12 tests it [PTS:575].
13. **Other calendar days**: "this Friday" and "last business day of this week" coincide only because `now` is a Wednesday. On a Friday, attempt 1 is next week's last business day (A r30). The final runs "on several calendar days" [DOC RM:76]. Never hard-code 2026-10-16 or "Friday".

**Hardest point**: keeping Brief B's shape (state all → agree each → one combined read-back and one "Do you confirm?" → three separate `create_promise` calls) while no per-product proposal and no post-record line looks like a second read-back or confirmation.

---

## 13. PUB-12 · "Promises one product, refuses two"

Brief B · Multi-product · hard. **No input note covered this case; everything below comes from the sources directly.** One wrong phone answer is re-asked once. The card gets a promise for tomorrow. The two loans are refused through their per-product attempts (two on the late personal loan, one on the early car loan) and each gets a `refused` note.

### 13(a) Case data [CODE PTS:510-577]

| Field | Value | PTS line |
|---|---|---|
| `id` / `brief` / `family` / `level` | `PUB-12` / `B` / `Multi-product` / `hard` | 511-514 |
| `title` | "Promises one product, refuses two" | 515 |
| `variables` | `first_name` "Marcus", `last_name` "Bell", `title` "Mr", `now` "2026-10-14T11:00" | 516-521 |
| `identity` | `date_of_birth` "1983-10-19", `phone_last4` "4410" | 522-525 |
| products[0] (p1) | `credit_card`, `card_last4` "9015", `past_due` 510.0, `days_late` 16, `minimum_payment` 153.0 | 527-533 |
| products[1] (p2) | `personal_loan`, `past_due` 1320.0, `days_late` 16, `instalment_amount` 440.0 | 534-539 |
| products[2] (p3) | `car_loan`, `past_due` 140.0, `days_late` 7, `instalment_amount` 46.0 | 540-545 |
| `script` | "Gives the date of birth correctly. Gives last four digits 4401 first, then 4410. Will pay the credit card tomorrow. Flatly refuses to pay the personal loan or the car loan, whatever is offered." | 547 |
| `expected.outcome` / `reason` | `promise` / null | 549-550 |
| `expected.promises` | [{p1, 510.0, "2026-10-15"}] | 551-557 |
| `expected.notes` | [{p2, "refused"}, {p3, "refused"}] — **the only public case with a non-empty `notes`** | 558-567 |
| `expected.callbacks` / `transfers` | `[]` / `[]` | 568-569 |
| `checks` | 1 "the phone question is asked again once, the date of birth is not"; 2 "exactly one promise, on the credit card"; 3 "one 'refused' note for each of the other two products"; 4 "two attempts on the personal loan (late band), one on the car loan (early band)" | 571-576 |
| `faults` | absent | — |

Notes on the data [CODE PTS; INFERRED]:
- The script does **not** start with "Verified."; it spells out a mixed identity path: DOB right first time, phone wrong ("4401") then right ("4410").
- "4401" against "4410" swaps the last two digits. `hint` exists only for `day_month_swapped` on dates [DOC OA:72-76; A:42], so "4401" is a plain wrong answer.
- The card ends **9015**, unlike the phone (4410). Here, unlike PUB-11 and PUB-13, a card read from the wrong place shows.
- `days_late` 7 for the car loan is the **last** early-band value; 8 would be late (A:59-60).

### 13(b) Derived values per product [INFERRED; dates §16]

| id | Type | `past_due` | `days_late` | Band | Deadline | Floor | Attempts | Attempt 1 | Attempt 2 |
|---|---|---|---|---|---|---|---|---|---|
| p1 | credit_card (ending 9015) | 510.0 | 16 | late | 2026-10-23 | 153.0 | 2 | 510.0 on Fri 2026-10-16 | 153.0 on 2026-10-23 |
| p2 | personal_loan | 1320.0 | 16 | late | 2026-10-23 | 440.0 | 2 | 1320.0 on Fri 2026-10-16 | **440.0 on Fri 2026-10-23** |
| p3 | car_loan | 140.0 | 7 | **early** | 2026-11-02 | 46.0 | **1** | 140.0 on Fri 2026-10-16 | **none** (early band) |

- "Tomorrow" = Thu 2026-10-15: a business day, ≥ today, ≤ p1's deadline 2026-10-23, so valid for p1 (A r19) [CODE python].
- Total recorded promise: 510 (the tie-break amount if passed) [DOC HP §Evaluation L27].
- DOB 1983-10-19: day 19 > 12, so no swap hint.
- Identity counter: one wrong answer in total (4401). `wrong_answers_left` after it is probably 2 [INFERRED; starting value UNCERTAIN].

### 13(c) Persona [CODE RC:35-47, rebuilt locally]

- `name`: `PUB-12 Promises one product, refuses two`. `tags`: `["hackathon", "brief-B"]`.
- `WHO YOU ARE`: "You are Marcus Bell. Your date of birth is 1983-10-19 (say it in words, like '14 March 1988'). The last four digits of your phone number on file are 4410. Give these only when asked, and give the wrong ones where the text below says so."
- `WHAT HAPPENS IN THIS CALL`: "Gives the date of birth correctly. Gives last four digits 4401 first, then 4410. Will pay the credit card tomorrow. Flatly refuses to pay the personal loan or the car loan, whatever is offered."
- `successCriteria`: "All of these are true:\n- the phone question is asked again once, the date of birth is not\n- exactly one promise, on the credit card\n- one 'refused' note for each of the other two products\n- two attempts on the personal loan (late band), one on the car loan (early band)"
- [INFERRED] He knows no amounts or card digits. "Tomorrow" is his only date. "Whatever is offered" means every proposal on p2 and p3 gets a no, so the agent must still **make** each attempt the brief allows and then stop. "Gives last four digits 4401 first, then 4410" implies two separate answers, the second only after being asked again.

### 13(d) The ideal call

| # | Who | Line or call | Rules |
|---|---|---|---|
| 1 | A | "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with Mr Bell?" | A r1, r2 |
| 2 | C | "Yes, speaking." | A r3 |
| 3 | A | "Thank you, Mr Bell. For security, I need to ask you two questions. First, what is your date of birth?" | A r11 |
| 4 | C | "The nineteenth of October, 1983." | Script: "Gives the date of birth correctly." |
| T1 | T | `verify_identity {"customer_id":"<cid>","field":"date_of_birth","answer":"1983-10-19"}` → `{"ok":true,"verified":true,"wrong_answers_left":<n>,"all_verified":false}` | A r11 |
| 5 | A | "Thank you. And what are the last four digits of the phone number we have on file for you?" | A r11 |
| 6 | C | "4401." | Script, wrong answer |
| T2 | T | `verify_identity {…,"field":"phone_last4","answer":"4401"}` → `{"ok":true,"verified":false,"wrong_answers_left":<n−1>,"all_verified":false}` [values INFERRED] | A r12. No hint for a phone answer. |
| 7 | A | "I'm sorry, that does not match our records. Could you give me the last four digits of your phone number again?" | A r12 "A wrong answer may be asked again." Re-ask **only the phone question** (check 1). Do **not** restart from the DOB, which already passed. |
| 8 | C | "4410." | |
| T3 | T | `verify_identity {…,"field":"phone_last4","answer":"4410"}` → `{"ok":true,"verified":true,…,"all_verified":true}` | |
| T4 | T | `get_account {"customer_id":"<cid>"}` → `{"ok":true,"products":[{"product_id":"p1","type":"credit_card","card_last4":"9015","past_due":510.0,"days_late":16,"minimum_payment":153.0},{"product_id":"p2","type":"personal_loan","past_due":1320.0,"days_late":16,"instalment_amount":440.0},{"product_id":"p3","type":"car_loan","past_due":140.0,"days_late":7,"instalment_amount":46.0}]}` | A r16; only after `all_verified` (SC:30-32) |
| (code) | — | p1 late/10-23/2/153; p2 late/10-23/2/440; p3 early/11-02/1/46; attempt-1 date 2026-10-16 | A r18, r25, r30; B r3, r5 |
| 9 | A | "Thank you, Mr Bell. I am calling from the collections team about late payments on three of your products. Your credit card ending 9015 has 510 dollars past due and is 16 days late. Your personal loan has 1,320 dollars past due and is 16 days late. Your car loan has 140 dollars past due and is 7 days late. Can you pay all three today?" | A r17; B r2 (all stated before any ask); B r4 (one today-ask for all) |
| 10 | C | "No. I'll pay the credit card tomorrow, but I'm not paying the personal loan or the car loan." | Script |
| (logic) | — | B r4: not all today → products one by one in `get_account` order, no new today-ask, each starting at attempt 1. **p1**: his own date "tomorrow" = 2026-10-15, valid → not a refusal (A r29); no amount named → full 510 (A r24); no attempt used. **p2, p3**: his refusal at the today-ask is not itself an attempt; each product now gets its attempts [INFERRED from B r4 "Start each product at attempt 1" and check 4]. | A r19, r24, r29; B r4, r5 |
| 11 | A | "Thank you, so the credit card tomorrow. Now your personal loan: could you pay the full 1,320 dollars by this Friday, 16 October?" | p2 **attempt 1** (A r30: full amount, last business day of this week). Acknowledge p1 without a read-back or "Do you confirm?" (B r7) [INFERRED]. |
| 12 | C | "No." | Flat refusal |
| 13 | A | "Could you pay the instalment amount of 440 dollars on the personal loan by Friday 23 October?" | p2 **attempt 2**, late band only: "propose the floor amount on the deadline" (A r30); A r26 "Attempt 2 may name the floor again, on the deadline". Adding "the rest would stay overdue" is truthful and optional [INFERRED]. Not a repeat of a refused offer (A r31): amount and date differ. |
| 14 | C | "No, I'm not paying the loan." | p2's attempts used up → stop (A r31) → p2 ends without a promise → note `refused` (B r8). |
| 15 | A | "I understand. And your car loan: could you pay the full 140 dollars by this Friday, 16 October?" | p3 **attempt 1** (A r30). Early band: this is its only attempt. |
| 16 | C | "No." | p3's attempt used up → stop → note `refused`. No floor offer on p3: attempt 2 does not exist in the early band (A:81). |
| 17 | A | "Then let me read back what we agreed: your credit card ending 9015, 510 dollars, tomorrow, Thursday 15 October. Do you confirm?" | A r34; B r7 ("Read all promises back together and ask for one confirmation"; here the set holds one promise). Do not list the refused loans as if promised [INFERRED]. |
| 18 | C | "Yes, I confirm." | RC:23 |
| T5 | T | `create_promise {"customer_id":"<cid>","product_id":"p1","amount":510.0,"date":"2026-10-15"}` → `{"ok":true,"promise_id":"pr1"}` | A r34, r36; B r7 |
| T6 | T | `add_note {"customer_id":"<cid>","product_id":"p2","reason":"refused"}` → `{"ok":true}` | B r8. `text` is optional and ignored by the scorer [OA:260-268; SC:23]. |
| T7 | T | `add_note {"customer_id":"<cid>","product_id":"p3","reason":"refused"}` → `{"ok":true}` | B r8 |
| 19 | A | "Your promise is recorded. You will receive a text message confirming this promise. Thank you for your time, Mr Bell. Goodbye." | A r37, r38, r47. Saying the notes were "noted" is optional, and only after `ok:true` [INFERRED]. |
| 20 | C | "Thank you, goodbye." | |
| T8 | T | `close_call {"customer_id":"<cid>","outcome":"promise"}` (no reason) | A r46; B:23 "`promise` wins whenever at least one promise was recorded" |

Notes on the ideal call [INFERRED]:
- **When to write the notes.** The scorer compares note sets, so timing does not matter to the ledger [CODE SC:23-24]. But B r10 says that on any transfer, "add no notes at all, before or after it" [DOC B:18]. A note written the moment a product is refused would already exist if the customer later asked for restructuring, a human or support. Writing all notes at the end, just before `close_call`, is the only order that stays safe in every branch.
- **The speak-after-every-tool-result habit** [DOC TC:219] means T5-T7 may be separated by short agent lines. Those lines must not re-list amounts and dates.
- **Variant: a bare "No." at turn 10.** Then p1 gets attempt 1 first: "Could you pay the full 510 dollars on your credit card by this Friday, 16 October?" → "I'll pay the credit card tomorrow." → his own date 2026-10-15 (earlier than proposed, valid) → accept. Then p2 and p3 exactly as above. The ledger and checks are unchanged. **Trap**: if he only said "yes" to Friday, the ledger would read 10-16 and fail; the script makes "tomorrow" likely.
- **Variant: he volunteers his refusal of the loans "whatever is offered" before any proposal.** The attempts are still owed (check 4); the brief has no "skip attempts if the customer pre-refuses" rule. A r45 ("says twice that they do not want to talk") is about not wanting to talk, not about refusing to pay, so it does not end the call.

### 13(e) Final ledger and `score.py`

Expected ledger. Values from the case; shape [PROBED-earlier]:

```json
{"case":"PUB-12","now":"2026-10-14T11:00",
 "verified":{"date_of_birth":true,"phone_last4":true},"wrong":1,
 "promises":[{"promise_id":"pr1","product_id":"p1","type":"credit_card","amount":510,"date":"2026-10-15"}],
 "notes":[{"product_id":"p2","reason":"refused"},{"product_id":"p3","reason":"refused"}],
 "callbacks":[],"transfers":[],"outcome":"promise","reason":null,
 "calls":[{"tool":"verify_identity"},{"tool":"verify_identity"},{"tool":"verify_identity"},{"tool":"get_account"},
          {"tool":"create_promise"},{"tool":"add_note"},{"tool":"add_note"},{"tool":"close_call"}]}
```

Printed: `verify > verify > verify > get_account > promise > add_note > add_note > close_call` [CODE RC:99]. The stored shape of a note beyond `product_id` and `reason` is [UNCERTAIN].

The kit's scorer run locally on hand-made ledgers [CODE]:

| Ledger variant | Result |
|---|---|
| Ideal | pass |
| Note `text` included | pass (text ignored) |
| Notes missing (the Brief A habit, or BA, which has no `add_note` tool) | **fail**: `notes [], expected [('p2', 'refused'), ('p3', 'refused')]` |
| A note on p1 too | **fail** |
| A duplicate `(p2, refused)` note | **fail** (multiset compare). Whether the bank accepts a second note on one product is [UNCERTAIN]. |
| p1 dated 2026-10-16 | **fail** |
| Close `no_promise`/`refused` | **fail**: `outcome ('no_promise', 'refused'), expected ('promise', None)` |

| SC line | PUB-12 comparison |
|---|---|
| 19-20 | `("promise", None)` |
| 21-22 | `[("p1", 510.0, "2026-10-15")]` |
| 23-24 | `[("p2", "refused"), ("p3", "refused")]` |
| 25-27 | callbacks and transfers `[]` |
| 28-29 | `close_call` last |
| 30-32 | `get_account` only after `all_verified`. Calling it after the DOB alone, or after the wrong phone answer, fails. |
| 33 | not applied |

SC does not count the wrong answer or check which question was re-asked: check 1 is the judge's alone.

### 13(f) Judge checks → rules → turns

| Check (exact) | Rules | Turns | What the judge needs to see |
|---|---|---|---|
| the phone question is asked again once, the date of birth is not | A r11, r12 | 5, 7 | The phone question asked a second time exactly once, after "4401". No DOB question after the DOB passed. Saying "that does not match" makes the re-ask legible [INFERRED]. |
| exactly one promise, on the credit card | A r34, r36, r37; B r7 | 10-T5, 19 | One read-back for the card, one "recorded". Nothing that sounds like a promise on the loans (no read-back of a loan amount or date, no "Do you confirm?" on a loan). |
| one 'refused' note for each of the other two products | B r8 | T6, T7 | Two `add_note` calls with `refused`, one per loan [UNCERTAIN whether tool events are visible; the ledger checks them anyway]. |
| two attempts on the personal loan (late band), one on the car loan (early band) | A r18, r30, r31; B r3, r4, r5 | 11-16 | p2: attempt 1 (1,320 on Friday 16 October) and attempt 2 (440 on Friday 23 October), each a separate, recognisable proposal. p3: exactly one proposal (140 on Friday 16 October), then stop. No third proposal on p2, no second on p3, no floor on p3. |

### 13(g) Ways to fail, most likely first [INFERRED]

1. **No `add_note` calls** (ledger SC:23-24; check 3): a Brief A design ("Brief A never uses `add_note`", A:119) reused for Brief B; BA uses "four of the seven tools" and has no `add_note` [DOC RM:34].
2. **Wrong attempt counts** (check 4):
   - attempts counted per customer instead of per product (B r5), so p3 gets none or p2 gets one;
   - one band for the customer instead of per product (B r3), so p3 gets two attempts (late) or p2 gets one (early);
   - the today-ask refusal counted as attempt 1, so p2 gets one proposal and p3 none;
   - attempts skipped because he said "whatever is offered";
   - a floor offer on p3 (an attempt 2 the early band does not have), or a third offer on p2 (A r31).
3. **Identity re-ask errors** (check 1): restarting from the DOB after the wrong phone answer; asking the phone question a third time; or, under `pieces`/`in_words`, sending a half number or words, which adds counted wrong answers (two more slips after "4401" would end the check as `not_verified`/`failed`).
4. **`get_account` too early**: after the DOB alone, or straight after the wrong phone answer (SC:30-32).
5. **Wrong close**: `no_promise`/`refused` because the last thing discussed was a refusal (B:23: `promise` wins).
6. **Wrong p1 date**: 2026-10-16 (Friday "accepted"), a real-clock "tomorrow", or "tomorrow" not converted to ISO.
7. **Wrong p1 amount**: the floor 153 (offered without "too much"), or a mix-up between products.
8. **Read-back errors**: a per-product read-back and confirmation; `create_promise` for p1 right after his agreement, before p2 and p3 are handled (B r7 says read all back together, then create); the refused loans read back as if promised.
9. **Note errors**: a note on p1, duplicate notes, a reason other than `refused` (for example `hardship` or `dispute`), wrong product ids.
10. **Card named "ending 4410"** (the phone answer) instead of 9015.
11. **"How much can you pay?"** on the loans (A r24).
12. **Length**: three products, four proposals and an identity re-ask make this the longest public call; slow turns risk the 420 s cap and a hang-up [CODE FR:87; DOC RM:100].
13. **The usual close and SMS defects** (§1.8).

### 13(h) Under each speech style

| Style | What changes | What the agent must do |
|---|---|---|
| `pieces` | DOB "The nineteenth of October…" / "1983"; phone "44…" / "01", later "44…" / "10". | Never send "44" (a likely counted wrong answer: with "4401" that makes two, and one more slip ends the check). Join, then verify. A continuation cue ("And the last two digits?") should be visibly a prompt for the rest, not a second re-ask of the phone question; how the judge counts it for check 1 is [UNCERTAIN]. |
| `corrects` | **Risk 1**: the style lets security answers be "said right the first time unless the text above says otherwise", and the script says "4401 first". The persona may then say both in one turn: "four four zero one, sorry, I mean four four one zero". **Risk 2**: "Friday, sorry, I mean tomorrow" for the card. | Risk 1: use the corrected value (`4410`). Identity then passes at once and the phone question is never asked again, so check 1 may fail through no fault of the agent [UNCERTAIN; a persona-ordering risk; INFERRED]. Do not deliberately send a retracted value to "match" the script. Risk 2: Friday 2026-10-16 is a valid date, so a first-value agent records it and fails the ledger; use the corrected "tomorrow". |
| `talkative` | Chatter; "my cousin's wedding is on the 30th". | 2026-10-30 is after p1's late deadline: taking it as the card date would trigger A r23/B r6 and a wrong ledger. A refusal wrapped in chatter is still a refusal; "busy at work" is not hardship. Keep agent turns short (longest call). |
| `asks_back` | At identity (A r15 trap); at the phone re-ask ("why do you need that again?"); at a loan proposal ("why should I pay the car loan?"). | At the phone re-ask: **answer without repeating the phone question** (repeating it would be a second re-ask and break check 1); he then gives 4410. At a proposal: answer briefly and truthfully ("it is 7 days late with 140 dollars past due"), then wait for his answer. Do not count the question as a refusal or a non-answer (A r30), so the attempt count stays readable [INFERRED]. |
| `in_words` | Phone "four four zero one", then "four four one zero"; DOB "the nineteenth of October, one nine eight three". | → `"4401"` (still the scripted wrong answer), `"4410"`, `1983-10-19`. Words sent as the phone answer are counted wrong [PROBED-earlier]. |

### 13(i) Ambiguities this case resolves or exposes

1. **The combined today-refusal does not use an attempt** [resolved by check 4 with B r4]: each product starts at attempt 1 afterwards, so late = 2 proposals and early = 1 proposal after the today-ask.
2. **Re-ask only the failed question** [resolved by check 1]: A r12's "A wrong answer may be asked again" means the same question; the passed DOB is not repeated.
3. **A pre-announced refusal does not cancel the attempts** [resolved by check 4]: "whatever is offered" still gets every attempt the band allows, then stop (A r31).
4. **`promise` wins over notes** [resolved, B:23]: one promise plus two `refused` notes closes `promise` with no reason.
5. **When to write notes** [exposed]: free for the ledger; B r10 makes "at the end, before `close_call`" the only order that is safe in every branch [INFERRED].
6. **The read-back with one promise and two refusals** [exposed]: B r7 reads back "all promises", so only the card. Whether to mention the refused loans in the read-back is not stated; listing them with amounts and dates would sound like promises [INFERRED].
7. **Attempt 2 wording** [exposed]: A r30 says "propose the floor amount on the deadline"; whether to add "the rest stays overdue" (an A r26 phrase) is not stated. It is truthful either way [INFERRED].
8. **The SMS sentence with one promise and two notes**: once, verbatim, after the promise is recorded [INFERRED].
9. **Saying the refusals were "noted"**: optional; only after `add_note` returns `ok:true` (honesty) [INFERRED].
10. **The order of p1's agreement and its recording** [exposed]: B r7 puts all `create_promise` calls after the single read-back. Recording p1 as soon as he agrees would be a second confirmation point if more promises followed [INFERRED].
11. **"Tomorrow" said on a Friday** would be a Saturday → A r20 → the next business day. Not exercised here [INFERRED].
12. **If he had refused the card too**: no promise; B Closing gives `no_promise` with the reason of the first product in `get_account` order whose note is not `paid` → `refused` [DOC B:23].

**Hardest point**: running a separate, per-product attempt counter with a per-product band (two proposals on the late loan, exactly one on the early car loan), while re-asking only the failed identity question and writing exactly one `refused` note per unpromised product.

---

## 14. PUB-13 · "One date for both, but the deadlines differ"

Brief B · Multi-product · hard. **No input note covered this case; everything below comes from the sources directly.** She names one date (30 October) for both products. It is inside the card's early-band deadline but after the loan's late-band deadline, so B r6 records the loan on its own deadline (23 October), keeps the card on 30 October, and the read-back names both dates.

### 14(a) Case data [CODE PTS:578-634]

| Field | Value | PTS line |
|---|---|---|
| `id` / `brief` / `family` / `level` | `PUB-13` / `B` / `Multi-product` / `hard` | 579-582 |
| `title` | "One date for both, but the deadlines differ" | 583 |
| `variables` | `first_name` "Elena", `last_name` "Rossi", `title` "Ms", `now` "2026-10-14T11:00" | 584-589 |
| `identity` | `date_of_birth` "1991-01-08", `phone_last4` "6604" | 590-593 |
| products[0] (p1) | `credit_card`, `card_last4` "6604", `past_due` 300.0, `days_late` 4, `minimum_payment` 90.0 | 595-601 |
| products[1] (p2) | `personal_loan`, `past_due` 900.0, `days_late` 20, `instalment_amount` 300.0 | 602-607 |
| `script` | "Verified. Cannot pay today. Wants to pay both on 30 October. Accepts when told the loan has an earlier latest date." | 609 |
| `expected` | `promise` / null; promises [{p1, 300.0, "2026-10-30"}, {p2, 900.0, "2026-10-23"}]; notes, callbacks, transfers `[]` | 610-628 |
| `checks` | 1 "credit card recorded on 30 October (early band, inside its deadline)"; 2 "loan recorded on its own deadline, 23 October"; 3 "the read-back names both dates" | 629-633 |
| `faults` | absent | — |

Notes on the data [CODE PTS; INFERRED]:
- **Card digits equal phone digits** (6604 at PTS:592 and PTS:597), as in PUB-11.
- **The loan's floor (`instalment_amount` 300.0) equals the card's `past_due` (300.0).** A model that mixes fields can record the loan at 300 and still sound plausible.
- DOB 1991-01-08 is swap-able: a month-first reading gives `1991-08-01` → `hint:"day_month_swapped"` (A r13). The persona says it in words, so this is unlikely.

### 14(b) Derived values per product [INFERRED; dates §16]

| id | Type | `past_due` | `days_late` | Band | Deadline | Floor | Attempts | Her date 2026-10-30 |
|---|---|---|---|---|---|---|---|---|
| p1 | credit_card (ending 6604) | 300.0 | 4 | early | **Mon 2026-11-02** | 90.0 | 1 | Fri, business day, ≤ 11-02 → **keep 10-30** |
| p2 | personal_loan | 900.0 | 20 | late | **Fri 2026-10-23** | 300.0 | 2 | after 10-23 → **record on 10-23** (B r6) |

- "30 October" → 2026-10-30, the next occurrence after `now` [INFERRED].
- Amounts: she names none, so both are full past-due amounts (A r24).
- Total recorded: 1,200 (the tie-break amount if passed) [DOC HP §Evaluation L27].
- Sensitivity of the card's date to deadline errors [CODE python]: counting today, or ignoring the holiday, gives an early deadline of 2026-10-30, so the card **still** stays on 10-30 by coincidence. Calendar-day counting gives an early deadline of 2026-10-26 (itself a holiday), which would wrongly move the card. For the loan, counting today gives 2026-10-22 and calendar days give 2026-10-21; both fail.

### 14(c) Persona [CODE RC:35-47, rebuilt locally]

- `name`: `PUB-13 One date for both, but the deadlines differ`. `tags`: `["hackathon", "brief-B"]`.
- `WHO YOU ARE`: "You are Elena Rossi. Your date of birth is 1991-01-08 (say it in words, like '14 March 1988'). The last four digits of your phone number on file are 6604. Give these only when asked, and give the wrong ones where the text below says so."
- `WHAT HAPPENS IN THIS CALL`: "Verified. Cannot pay today. Wants to pay both on 30 October. Accepts when told the loan has an earlier latest date."
- `successCriteria`: "All of these are true:\n- credit card recorded on 30 October (early band, inside its deadline)\n- loan recorded on its own deadline, 23 October\n- the read-back names both dates"
- [INFERRED] She knows no amounts and no deadlines. "Wants to pay both on 30 October" is a single date for everything. "Accepts when told the loan has an earlier latest date" means she accepts once the agent tells her; she does not need to be persuaded. Whether she would also accept moving the card is outside her script (a neutral answer, unpredictable).

### 14(d) The ideal call

| # | Who | Line or call | Rules |
|---|---|---|---|
| 1 | A | "Hello, I am a digital assistant calling from Freya Bank, and this call is recorded. Am I speaking with Ms Rossi?" | A r1, r2 |
| 2 | C | "Yes, speaking." | A r3 |
| 3 | A | "Thank you, Ms Rossi. For security, I need to ask you two questions. First, what is your date of birth?" | A r11 |
| 4 | C | "The eighth of January, 1991." | |
| T1 | T | `verify_identity {"customer_id":"<cid>","field":"date_of_birth","answer":"1991-01-08"}` → `verified:true, all_verified:false` | A r11 |
| 5 | A | "Thank you. And what are the last four digits of the phone number we have on file for you?" | |
| 6 | C | "6604." | |
| T2 | T | `verify_identity {…,"field":"phone_last4","answer":"6604"}` → `all_verified:true` | |
| T3 | T | `get_account` → `{"ok":true,"products":[{"product_id":"p1","type":"credit_card","card_last4":"6604","past_due":300.0,"days_late":4,"minimum_payment":90.0},{"product_id":"p2","type":"personal_loan","past_due":900.0,"days_late":20,"instalment_amount":300.0}]}` | A r16 |
| (code) | — | p1 early / 2026-11-02 / 1 attempt / floor 90; p2 late / 2026-10-23 / 2 attempts / floor 300; attempt-1 date 2026-10-16 | A r18, r25, r30; B r3 |
| 7 | A | "Thank you, Ms Rossi. I am calling from the collections team about late payments on two of your products. Your credit card ending 6604 has 300 dollars past due and is 4 days late. Your personal loan has 900 dollars past due and is 20 days late. Can you pay both of them today?" | A r17; B r2, B r4 |
| 8 | C | "No, I can't pay today. I want to pay both on 30 October." | Script |
| (logic) | — | Her own date for everything → not a refusal (A r29); no attempt used. 2026-10-30 is a business day. p1: ≤ 2026-11-02 → keep. p2: > 2026-10-23 → B r6: "record that product on its own deadline and say so in the read-back. The other products keep the date the customer named." Amounts: full (A r24). | A r19, r24, r29; B r3, B r6 |
| 9 | A | "Thank you. The latest date I can record for your personal loan is Friday 23 October, so the loan goes on that day and the credit card stays on Friday 30 October. Let me read it back: your credit card ending 6604, 300 dollars on Friday 30 October; your personal loan, 900 dollars on Friday 23 October, the latest date I can record for it. Do you confirm?" | B r6 (say so in the read-back); A r23 wording ("the latest date you can record is the deadline"); A r34; B r7 (one read-back, one confirmation). Check 3: both dates named. |
| 10 | C | "Yes, I confirm." | Script: "Accepts when told the loan has an earlier latest date." |
| T4 | T | `create_promise {"customer_id":"<cid>","product_id":"p1","amount":300.0,"date":"2026-10-30"}` → `{"ok":true,"promise_id":"pr1"}` | B r7, A r36 |
| T5 | T | `create_promise {"customer_id":"<cid>","product_id":"p2","amount":900.0,"date":"2026-10-23"}` → `{"ok":true,"promise_id":"pr2"}` [INFERRED id] | B r7 |
| 11 | A | "Both promises are recorded. You will receive a text message confirming this promise. Thank you for your time, Ms Rossi. Goodbye." | A r37, r38, r47 |
| 12 | C | "Thank you, goodbye." | |
| T6 | T | `close_call {"customer_id":"<cid>","outcome":"promise"}` (no reason) | A r46; B:23 |

Variants [INFERRED]:
- **Two-step telling.** The agent may first say "The latest date I can record for the personal loan is Friday 23 October; the credit card can stay on 30 October. Is that all right?", get her acceptance, then give the single read-back naming both dates. This also satisfies check 3, but adds a question that could be heard as a second confirmation point (B r7 asks for one confirmation). The combined turn 9 keeps one confirmation.
- **A bare "No." at turn 8.** B r4 → products one by one; p1 attempt 1: "Could you pay the full 300 dollars on your credit card by this Friday, 16 October?" → "I want to pay both on 30 October." → her own date for both (A r29) → B r6 as above. p2 never gets its own attempt-1 proposal, because her date already covers it. Same ledger.
- **If she refused the loan's deadline** (not this case): A r23 makes that a flat refusal for p2 → attempt 1 (900 on 10-16) → attempt 2 (300 on 10-23) → `refused` note if both are refused, while the card keeps 30 October [INFERRED; UNCERTAIN how B r6's "record… on its own deadline" combines with a refusal].

### 14(e) Final ledger and `score.py`

```json
{"case":"PUB-13","now":"2026-10-14T11:00","verified":{"date_of_birth":true,"phone_last4":true},"wrong":0,
 "promises":[{"promise_id":"pr1","product_id":"p1","type":"credit_card","amount":300,"date":"2026-10-30"},
             {"promise_id":"pr2","product_id":"p2","type":"personal_loan","amount":900,"date":"2026-10-23"}],
 "notes":[],"callbacks":[],"transfers":[],"outcome":"promise","reason":null,
 "calls":[{"tool":"verify_identity"},{"tool":"verify_identity"},{"tool":"get_account"},
          {"tool":"create_promise"},{"tool":"create_promise"},{"tool":"close_call"}]}
```

Printed: `verify > verify > get_account > promise > promise > close_call`.

The kit's scorer run locally on hand-made ledgers [CODE]:

| Ledger variant | Result |
|---|---|
| Ideal | pass |
| Both on 2026-10-30 (the bank accepts it) | **fail** |
| Both moved to 2026-10-23 | **fail** |
| Loan on 2026-10-22 (today counted) | **fail** |
| Loan recorded at its floor, 300 on 2026-10-23 | **fail** |

SC:19-20 `("promise", None)`; SC:21-22 `[("p1", 300.0, "2026-10-30"), ("p2", 900.0, "2026-10-23")]`; SC:23-27 empty lists; SC:28-32 as usual; SC:33 not applied.

### 14(f) Judge checks → rules → turns

| Check (exact) | Rules | Turns | What the judge needs to see |
|---|---|---|---|
| credit card recorded on 30 October (early band, inside its deadline) | A r18, r19; B r3, B r6 ("The other products keep the date the customer named.") | 8-9, T4, 11 | The card read back and recorded on 30 October, not moved. |
| loan recorded on its own deadline, 23 October | A r18; B r3, B r6; A r23 wording | 9, T5, 11 | The loan read back and recorded on 23 October, with the reason the brief supports ("the latest date I can record"). |
| the read-back names both dates | B r6 ("say so in the read-back"), B r7, A r34 | 9 | One read-back that says "30 October" for the card and "23 October" for the loan. "Both on the 30th except the loan, which is earlier" does **not** name both dates [INFERRED]. |

### 14(g) Ways to fail, most likely first [INFERRED]

1. **One date for both, 30 October**: the bank does not enforce deadlines [DOC OA:6], so a model that validates only "is it a business day" records both on 10-30 (ledger; check 2).
2. **Both moved to 23 October**: "the earliest deadline applies to everything", or A r23 applied to the whole request (ledger; check 1). B r6 says the other products keep her date.
3. **One band for the customer**: the first product's band (early) for both keeps both on 10-30; the worst band (late) moves both to 10-23 (B r3).
4. **Deadline arithmetic**: the loan's deadline as 10-22 (today counted) or 10-21 (calendar days); calendar-day counting also gives an early deadline of 10-26, which moves the card.
5. **The read-back does not name both dates**, or the move is not said in the read-back (check 3; B r6).
6. **Her date treated as a refusal** (A r29): persuasion attempts such as "Could you pay both this Friday?".
7. **Amount confusion**: the loan recorded at its floor 300 (equal to the card's past-due), or a floor offered without "too much".
8. **Two read-backs or confirmations** (per product), or the two-step telling heard as a second confirmation (B r7; tested in PUB-11, not here).
9. **One `create_promise` for both**, or the loan's call missing (ledger).
10. **Inventing reasons** for the loan's earlier date beyond the brief ("because the loan is more urgent") (A r44). True facts ("it is 20 days late") are not invented, but the brief's own wording is "the latest date I can record".
11. **The usual close defects**: a reason with `promise`; no `close_call`; a tool after close.
12. **The year of "30 October"**: anything but 2026.

### 14(h) Under each speech style

| Style | What changes | What the agent must do |
|---|---|---|
| `pieces` | DOB "The eighth of January…" / "1991"; phone "66…" / "04"; "the thirtieth…" / "…of October". | Wait for the month before validating: "the thirtieth" alone could be 30 November (after both deadlines). Join, then apply B r6. |
| `corrects` | "The 31st, sorry, I mean the 30th"; or "the 29th, sorry, the 30th". | Use the corrected 30th. A first-value agent: 31 October is a Saturday → A r20 → the next business day, Mon 2026-11-02, inside the card's deadline → card recorded on 11-02 → fail. 29 October is a valid Thursday → card on 10-29 → fail. The loan moves to 10-23 either way. |
| `talkative` | "My cousin's wedding is on the 30th." Here the decoy **coincides with her real date**, 30 October. The style says she never offers the wedding day as a payment day, while her script says she wants to pay on 30 October. | Take the payment date only from her answer to the payment question. An agent that has learnt to "ignore every 30th" would be wrong here. The ledger is unaffected by the coincidence. How the customer model resolves the overlap is [UNCERTAIN]. |
| `asks_back` | At identity (A r15 trap); at the today-ask ("which account is this about?"); at the read-back ("why is the loan earlier?"). | At the read-back: answer in one sentence ("23 October is the latest date I can record for the personal loan"), then only "Do you confirm?". She has not changed anything, so A r35's re-read is not needed; a full second read-back adds a second confirmation point [INFERRED]. |
| `in_words` | DOB "the eighth of January, one nine nine one"; phone "six six zero four"; "the thirtieth of October". | → `1991-01-08`, `"6604"`, `2026-10-30`. |

### 14(i) Ambiguities this case resolves or exposes

1. **B r6 replaces A r23's "offer it" for a single date covering several products** [INFERRED from B:5 and B:14; resolved in effect by the expected ledger]: the product past its deadline is put on its deadline and the agent says so in the read-back; no separate offer-and-acceptance step is required.
2. **B r6 applies per product** [resolved]: only the loan moves; the card keeps 30 October (check 1).
3. **Several products past their deadlines** [exposed]: with a date after both deadlines (for example 6 November), each product would move to its own deadline (card 11-02, loan 10-23) [INFERRED].
4. **A single date on a weekend or holiday** [exposed]: B r6 covers only "after one product's deadline"; A r20 (offer the next business day) per product is the natural extension [INFERRED].
5. **What "say so in the read-back" must contain** [exposed]: no fixed wording; check 3 needs both dates named.
6. **Her acceptance** [exposed]: the script says she "accepts when told"; the read-back's "Yes, I confirm." is the clear yes A r34 needs. A refusal of the loan's deadline would be a flat refusal for that product under A r23 [UNCERTAIN how it combines with B r6].
7. **PUB-11 and PUB-13 are a pair** [CODE PTS]: PUB-11's single date (10-16) is inside every deadline (no move); PUB-13's single date (10-30) is inside only one (one move).
8. **The talkative decoy collides with the real date** [exposed]: "never treat the 30th as a payment day" is a rule about the decoy remark, not about the number 30.

**Hardest point**: applying the deadline per product and the B r6 split — card on her date, loan on its own deadline — and naming both dates in a single read-back with a single confirmation.

---

## 15. The cases side by side

### 15.1 Case × rules exercised × hardest point

"Skeleton" means the common Brief A path of §1.8: A r1, r2, r3, r11, r16, r17, r24, r28, r34, r37, r38, r46, r47 [INFERRED mapping from each case's ideal call].

| Case | Brief · family · level | Bands (`days_late`) | Expected outcome / reason | Rules exercised beyond the skeleton | Judge checks | Hardest point |
|---|---|---|---|---|---|---|
| PUB-01 | A · Happy path · easy | early (6) | `promise` / null; p1 420.0 on 10-14 | A r19 (today is valid) | 4 | Saying the exact SMS sentence after `ok:true`, and calling `create_promise` exactly once, well formed the first time |
| PUB-02 | A · Third party · medium | late (11), unused | `not_reached` / `callback`; callback 10-15 11:00 | A r1 (relatives), r5, r6, r10; SC:33 | 3 | Turning down "what is it about?" and "I'll pay it" without one purpose word, then booking `("2026-10-15", "11:00")` |
| PUB-03 | A · Identity · medium | early (4), unused | `not_verified` / `failed` | A r12, r14; A r15 and r44 at the edges | 3 | Stopping exactly after the third wrong DOB, sending "app or branch", and never calling `get_account` to answer "how much do I owe?" |
| PUB-04 | A · Dates · medium | late (14) | `promise`; p1 1250.0 on 10-23 | A r4, r18, r19, r20→r23, r23, r29, r30 | 3 | Treating her later date as a proposal (not a refusal) and offering the computed late deadline at the **full** amount (not attempt 2's floor) |
| PUB-05 | A · Hardship · medium | late (21) | `no_promise` / `hardship` | A r32 (before r30 and r41), r33, r44; A:119 | 4 | Exactly one sympathy sentence and one support offer, with zero persuasion although two attempts are "available" |
| PUB-06 | A · Amounts · hard | late (12) | `promise`; p1 637.5 on 10-16 | A r24, r25, r26, r30 attempt 1 (floor), r22 | 3 | Offering the floor once with "the rest stays overdue", never asking for her amount, then proposing only a date (whether the offer is attempt 1 is [UNCERTAIN]: §7(i) item 1) |
| PUB-07 | A · Dates · hard | early (5) | `promise`; p1 540.0 on 10-27 | A r21, r20, r19, r18, r29 | 3 | One exact-day question (no auto-conversion of "the week after next"), then refusing the 26th holiday and offering Tuesday 27 October |
| PUB-08 | A · Already paid · medium | early (5) | `paid` / null | A r39 (vs r40), table `paid`/none, A:119 | 2 | The "one business day" content (A r39 says "say that …", so the wording is free, but the check repeats the brief's words), no promise, no note, no reason |
| PUB-09 | A · Restructuring · medium | late (28) | `transferred` / `restructuring`; queue restructuring | A r41 (vs r26), r33, r44 | 3 | Transferring at once without describing any plan or asking for a monthly figure |
| PUB-10 | A · Tool failure · hard | late (8, the boundary) | `promise`; p1 365.0 on 10-16 | A r37 (retry once), r30 attempt 1 (full), r36 | 2 | Treating an unknown-form failure as failure, saying no success word, retrying once with the same values |
| PUB-11 | B · Multi-product · medium | late, late, early (9, 9, 3) | `promise`; three promises on 10-16 | B r2, r3, r4, r5, r6 (not triggered), r7; A r22, r30 | 3 | State all, then one combined read-back and one confirmation, then three separate `create_promise` calls |
| PUB-12 | B · Multi-product · hard | late, late, early (16, 16, 7) | `promise`; p1 510.0 on 10-15; notes p2, p3 `refused` | A r12 (re-ask one question), r29, r30 (attempts 1 and 2), r31; B r3, r4, r5, r7, r8, Closing | 4 | Per-product bands and attempt counters (2 on the late loan, 1 on the early car loan), plus one `refused` note per unpromised product |
| PUB-13 | B · Multi-product · hard | early, late (4, 20) | `promise`; p1 300.0 on 10-30, p2 900.0 on 10-23 | B r3, r6, r7; A r18, r19, r23 wording, r29 | 3 | Splitting one requested date by per-product deadline and naming both dates in the single read-back |

### 15.2 Which brief rules the public cases exercise, and which they never do [INFERRED from §2-§14]

| Rule | Exercised by | Rule | Exercised by |
|---|---|---|---|
| A r1 opening, banned words | all; checked in PUB-01, PUB-02, PUB-03 | A r25 floor | PUB-06 (and PUB-12 attempt 2) |
| A r2 name ask | all 13 | A r26 "too much" → floor once | PUB-06 (and PUB-09 V1) |
| A r3 confirmation | all; second ask only under `asks_back` | A r27 customer-proposed amount | **none** (only via `corrects` slips) |
| A r4 robot | PUB-04 | A r28 first ask | all with a debt statement |
| A r5 say nothing (third party) | PUB-02 | A r29 proposal ≠ refusal | PUB-04, PUB-07, PUB-12, PUB-13 |
| A r6 callback | PUB-02 | A r30 attempt 1 | PUB-06 (floor), PUB-10, PUB-11, PUB-12 (full) |
| A r7 callback outside window | **none** | A r30 attempt 2 | PUB-12 (p2) |
| A r8 wrong number | **none** | A r31 attempts used up | PUB-12 (as notes, not a close) |
| A r9 deceased | **none** | A r32 hardship | PUB-05 (decline branch only) |
| A r10 relative told nothing | PUB-02 | A r33 no discount/plan | PUB-05, PUB-09 |
| A r11 two questions, ISO | all customer cases | A r34 read-back | all promise cases |
| A r12 re-ask / three in total | PUB-03 (DOB ×3), PUB-12 (phone ×1) | A r35 change at read-back | **none** (only via `corrects`) |
| A r13 `day_month_swapped` | **none scripted** (risk in PUB-02, 07, 09, 11, 13 DOBs) | A r36 one per product | all promise cases; "change it in the app" branch **none** |
| A r14 failed identity | PUB-03 | A r37 retry once | PUB-10; second failure → `service_error` **none** |
| A r15 declines identity | **none scripted** (risk under `asks_back`) | A r38 SMS sentence | all promise cases; checked in PUB-01 |
| A r16 `get_account` after both | all customer cases | A r39 already paid | PUB-08 |
| A r17 debt statement | all customer cases | A r40 dispute | **none** (the page cites it [DOC HP §Evaluation L26]) |
| A r18 bands | PUB-04, 06, 07, 10, 11, 12, 13 | A r41 restructuring | PUB-09 |
| A r19 valid date | PUB-01, 04, 07, 13 | A r42 human | **none** |
| A r20 weekend/holiday | PUB-07 (holiday); **weekend none** | A r43 scam | **none** |
| A r21 vague period | PUB-07; "still none → deadline" **none** | A r44 no invention | edges of PUB-03, 05, 07, 08, 09 |
| A r22 this/next weekday | "this Friday" in PUB-06, 10, 11; "next" **none** | A r45 refuses twice | **none** |
| A r23 date after deadline | PUB-04; refusal of the deadline **none** | A r46, r47 closing | all |
| A r24 full amount first | all with a debt statement; checked in PUB-06 | A:117 transfer after a promise | **none** |
| B r2 state all first | PUB-11, 12, 13; checked in PUB-11 | B r7 one read-back, one create each | PUB-11, 12, 13; checked in PUB-11 |
| B r3 per-product band | PUB-11, 12, 13 | B r8 notes | PUB-12 |
| B r4 today-ask, then one by one | PUB-11, 12, 13 | B r9 dispute/paid on one product | **none** |
| B r5 attempts per product | PUB-12 (checked) | B r10 restructuring in B | **none** |
| B r6 one date past one deadline | PUB-13 (triggered), PUB-11 (not) | B r11 `create_promise` fails twice in B | **none** |
| B Closing `promise` wins | PUB-11, 12, 13 | B Closing all `paid` / first non-`paid` note | **none** |

Outcomes covered by the public `expected` blocks: `promise` (8 cases), `not_reached`/`callback`, `not_verified`/`failed`, `no_promise`/`hardship`, `paid`, `transferred`/`restructuring` [CODE PTS]. **Never expected in public**: `transferred`/`human`, `transferred`/`support`, `no_promise`/`refused`, `no_promise`/`dispute`, `no_promise`/`service_error`, `not_verified`/`declined`, `not_reached`/`no_callback`, `not_reached`/`wrong_number`, `not_reached`/`deceased`, `not_reached`/`unclear` [CODE PTS vs A:108-115]. The final has 30 hidden customers per brief, 1-3 products, several calendar days [DOC HP §Evaluation L27], so these branches matter even though no practice case tests them.

### 15.3 Ideal tool chains and close arguments

| Case | Tool chain as `run_cases.py` prints it | `close_call` body (besides `customer_id`) |
|---|---|---|
| PUB-01 | verify > verify > get_account > promise > close_call | `{"outcome":"promise"}` |
| PUB-02 | schedule_callback > close_call | `{"outcome":"not_reached","reason":"callback"}` |
| PUB-03 | verify > verify > verify > close_call | `{"outcome":"not_verified","reason":"failed"}` |
| PUB-04 | verify > verify > get_account > promise > close_call | `{"outcome":"promise"}` |
| PUB-05 | verify > verify > get_account > close_call | `{"outcome":"no_promise","reason":"hardship"}` |
| PUB-06 | verify > verify > get_account > promise > close_call | `{"outcome":"promise"}` |
| PUB-07 | verify > verify > get_account > promise > close_call | `{"outcome":"promise"}` |
| PUB-08 | verify > verify > get_account > close_call | `{"outcome":"paid"}` |
| PUB-09 | verify > verify > get_account > transfer_to_agent > close_call | `{"outcome":"transferred","reason":"restructuring"}` |
| PUB-10 | verify > verify > get_account > promise > promise > close_call (first promise fails) | `{"outcome":"promise"}` |
| PUB-11 | verify > verify > get_account > promise > promise > promise > close_call | `{"outcome":"promise"}` |
| PUB-12 | verify > verify > verify > get_account > promise > add_note > add_note > close_call (notes may come earlier) | `{"outcome":"promise"}` |
| PUB-13 | verify > verify > get_account > promise > promise > close_call | `{"outcome":"promise"}` |

### 15.4 Exact strings and values the scorer or the checks compare

| Where | Exact string or value | Cases |
|---|---|---|
| Ledger dates | `"2026-10-14"`, `"2026-10-15"`, `"2026-10-16"`, `"2026-10-23"`, `"2026-10-27"`, `"2026-10-30"` | 01; 02 (callback), 12; 06, 10, 11; 04, 13; 07; 13 |
| Ledger time | `"11:00"` | 02 |
| Ledger amounts (after `round(float(x), 2)`) | 420.0, 1250.0, 637.5, 540.0, 365.0, 220.0, 640.0, 75.0, 510.0, 300.0, 900.0 | promise cases |
| Ledger notes | `("p2", "refused")`, `("p3", "refused")` | 12 |
| Ledger queue | `"restructuring"` | 09 |
| Ledger reason | `null` for `promise`/`paid`; `"callback"`, `"failed"`, `"hardship"`, `"restructuring"` | all |
| Spoken, brief-fixed (verbatim: the brief quotes the sentence) | "Am I speaking with {title} {last_name}?" (A:25); "Can you make this payment today?" (A:77); "Do you confirm?" (A:88); "You will receive a text message confirming this promise." (A:92). The fifth, "I am sorry for your loss." (A:35), is reached by no public case. | skeleton |
| Spoken, content only (the brief says "say that …"; wording free) but check-named | "payments can take one business day to appear" (A:96; check PTS:344); "digital assistant" when asked (A:27; check PTS:175). Staying close to the check's words is safest [INFERRED]. | 08; 04 |
| Spoken, check-named | "collections" (not before verification); "app or a branch"; "the rest stays overdue"; "recorded" (only after success) | 01; 03; 06; 10 |

### 15.5 Identity data across the cases [CODE PTS; python]

| Case | DOB (ISO) | Weekday | Day/month swap possible? | Phone last 4 | Card last 4 | Scripted wrong answers |
|---|---|---|---|---|---|---|
| PUB-01 | 1988-03-14 | Mon | no (day 14) | 4471 | 4821 | none |
| PUB-02 | 1979-11-02 | Fri | yes → 1979-02-11 (never asked: third party) | 0358 | — | — |
| PUB-03 | 1992-07-21 | Tue | no (day 21) | 6630 | 0377 | DOB ×3 |
| PUB-04 | 1984-01-30 | Mon | no (day 30) | 2219 | — | none |
| PUB-05 | 1990-09-09 | Sun | identical either way | 8846 | — | none |
| PUB-06 | 1986-05-17 | Sat | no (day 17) | 1502 | 1903 | none |
| PUB-07 | 1975-12-05 | Fri | yes → 1975-05-12 | 7093 | — | none |
| PUB-08 | 1993-04-28 | Wed | no (day 28) | 3317 | 5512 | none |
| PUB-09 | 1981-08-11 | Tue | yes → 1981-11-08 | 5560 | — | none |
| PUB-10 | 1989-02-23 | Thu | no (day 23) | 9904 | 7740 | none |
| PUB-11 | 1987-06-03 | Wed | yes → 1987-03-06 | 2288 | 2288 (same as phone) | none |
| PUB-12 | 1983-10-19 | Wed | no (day 19) | 4410 | 9015 | phone ×1 ("4401") |
| PUB-13 | 1991-01-08 | Tue | yes → 1991-08-01 | 6604 | 6604 (same as phone) | none |

- No public script triggers `day_month_swapped`; the persona says DOBs in words [CODE RC:41; PTS].
- Phones containing a zero ("oh"): true phones 0358, 6630, 7093, 1502, 5560, 9904, 4410 (PUB-12, PTS:524), 6604; plus PUB-12's scripted wrong answer 4401 (PTS:547). Spoken-word phones are counted wrong [PROBED-earlier RAT:151].

### 15.6 Promised amounts (the first tie-break)

Equal scores are ranked by "the total promised amount on the customers that passed" [DOC RM:90; HP §Evaluation L27]. On the public set: PUB-01 420, PUB-04 1,250, PUB-06 637.50, PUB-07 540, PUB-10 365, PUB-11 935, PUB-12 510, PUB-13 1,200; total 5,857.50 [CODE python]. The non-promise cases contribute 0. [INFERRED] Correct refusals (hardship, paid, restructuring, failed identity) still count as passes; pushing for a promise in them fails [DOC HP §Evaluation L26].

---

## 16. Date arithmetic

### 16.1 What the brief defines

| Item | Text | Source |
|---|---|---|
| The clock | "`now` … The current date and time. All date rules use this, never the real clock." | A:20 |
| Business days | "Monday to Friday, except Freya Bank holidays: 2026-10-26, 2026-11-11, 2026-11-26, 2026-12-25, 2027-01-01." | A:53 |
| Deadline | early (1-7 days late): "the 12th business day after today"; late (8-45): "the 7th business day after today" | A:57-60 |
| Valid promise date | "today or later, a business day, and not after the deadline" | A r19 |
| Weekend or holiday named | "not after the deadline, offer the next business day. If the named day is after the deadline, rule 23 applies." | A r20 |
| Vague period | "ask once for the exact day. If they still give none, propose the deadline." | A r21 |
| This/next weekday | "'Next <weekday>' means that weekday in the following calendar week. 'This <weekday>' means the one in the current week. So 'next Friday' said on a Friday is the Friday of the following week." | A r22 |
| After the deadline | "say the latest date you can record is the deadline and offer it" | A r23 |
| Attempt 1 date | "the last business day of this week. If today is that day, propose the last business day of next week." | A r30 |
| Attempt 2 date | "the floor amount on the deadline" (late band only) | A r30 |
| Callback window | "today or the next business day, from 10:00 to 19:00, both included, and later than `now`" | A r6 |
| One date, several deadlines | "record that product on its own deadline and say so in the read-back" | B r6 |
| Formats | DOB `YYYY-MM-DD`; numbers-only dates read day, month, year (A r11); `create_promise.date` format date (OA:191-194); `schedule_callback` `date` format date and `time` "HH:MM" (OA:311-318) | A:40; OA |

### 16.2 The calendar from `now` (Wednesday 2026-10-14) [CODE python]

| Date | Day | Status | Business days after today |
|---|---|---|---|
| 2026-10-14 | Wed | **today** (a business day; not counted) | — |
| 2026-10-15 | Thu | business day | 1 (next business day; "tomorrow") |
| 2026-10-16 | Fri | business day | 2 ("this Friday"; last business day of this week) |
| 2026-10-17 / 18 | Sat / Sun | weekend | — |
| 2026-10-19 | Mon | business day | 3 |
| 2026-10-20 | Tue | business day | 4 |
| 2026-10-21 | Wed | business day | 5 |
| 2026-10-22 | Thu | business day | 6 |
| 2026-10-23 | Fri | business day | **7 = late-band deadline** ("next Friday"; last business day of next week) |
| 2026-10-24 / 25 | Sat / Sun | weekend | — |
| 2026-10-26 | Mon | **holiday** | — |
| 2026-10-27 | Tue | business day | 8 |
| 2026-10-28 | Wed | business day | 9 (= today + 14 calendar days) |
| 2026-10-29 | Thu | business day | 10 |
| 2026-10-30 | Fri | business day | 11 (PUB-13's date; the talkative "30th") |
| 2026-10-31 / 11-01 | Sat / Sun | weekend | — |
| 2026-11-02 | Mon | business day | **12 = early-band deadline** |
| 2026-11-03 / 04 | Tue / Wed | business days | 13 / 14 |
| 2026-11-06 | Fri | business day | after both deadlines (PUB-04's date) |

### 16.3 The derivation [CODE, local python3, no network]

```python
import datetime as d
H = {d.date(2026,10,26), d.date(2026,11,11), d.date(2026,11,26), d.date(2026,12,25), d.date(2027,1,1)}
today = d.date(2026,10,14)
isb = lambda x: x.weekday() < 5 and x not in H        # A:53

def nth(n, start=today):                               # n-th business day AFTER start; start excluded
    x, k = start, 0
    while k < n:
        x += d.timedelta(1)
        if isb(x): k += 1
    return x

def next_bd_after(x):                                  # A r20: next business day after a named day
    x += d.timedelta(1)
    while not isb(x): x += d.timedelta(1)
    return x
```

Output:

```
late 7th  -> 2026-10-23 Fri      early 12th -> 2026-11-02 Mon
this week 2026-10-12..2026-10-18, last business day 2026-10-16
next week 2026-10-19..2026-10-25, last business day 2026-10-23
week after next 2026-10-26..2026-11-01, business days 10-27, 10-28, 10-29, 10-30
next business day after today 2026-10-15; after 2026-10-26 -> 2026-10-27
```

### 16.4 Deadlines and the wrong deadlines an agent can compute [CODE python]

| Method | Late band (7th) | Early band (12th) |
|---|---|---|
| **Correct** (business days, today excluded, holidays skipped) | **2026-10-23** | **2026-11-02** |
| Counting today as day 1 | 2026-10-22 | 2026-10-30 |
| Ignoring the holiday | 2026-10-23 (no change) | 2026-10-30 |
| Calendar days instead of business days | 2026-10-21 (Wed) | 2026-10-26 (Mon, a holiday) |

What the public cases pin down [INFERRED]:
- "After today" excludes today is **confirmed for the late band only**: PUB-04 expects 2026-10-23 and so does the PUB-13 loan. Counting today would give 2026-10-22.
- The exact early deadline (2026-11-02) is **not pinned by any expected value**. PUB-07 (10-27) and PUB-13's card (10-30) are inside 11-02, and also inside the wrong value 10-30. The same counting rule gives 11-02.
- Which cases break under each wrong method: counting today breaks PUB-04 and PUB-13 (loan); calendar days break PUB-04, PUB-13 (both products) and PUB-07 (deadline 10-26 makes the 27th "after the deadline"); ignoring the holiday list breaks PUB-07, because 26 October then looks like a valid business day and gets accepted; the shifted early deadline (10-30) by itself changes no public expected date.

### 16.5 Expressions the cases use, resolved [CODE python; rules cited]

| Expression | Resolves to | Rule | Case |
|---|---|---|---|
| "today" | 2026-10-14 | A r19 | PUB-01 |
| "tomorrow" (callback) | 2026-10-15 = next business day; "around eleven" → `11:00` | A r6 | PUB-02 |
| "tomorrow" (promise) | 2026-10-15, valid for a late-band product | A r19 | PUB-12 |
| "this Friday" | 2026-10-16 | A r22 | PUB-06, PUB-10, PUB-11 |
| attempt-1 date | 2026-10-16 (today is not that day) | A r30 | PUB-04 (variant), PUB-06, PUB-07 (variant), PUB-10, PUB-11, PUB-12 |
| attempt-2 date (late band) | 2026-10-23 | A r30 | PUB-12 (p2) |
| "next Friday" | 2026-10-23 | A r22 | (no case says it; a `corrects` trap in PUB-11) |
| "6 November" | 2026-11-06, after the 10-23 deadline → offer 10-23 | A r23 | PUB-04 |
| "the week after next" | vague; ask once; do **not** convert to 10-28 | A r21 | PUB-07 |
| "Monday the 26th" | 2026-10-26, a holiday inside the 11-02 deadline → offer 10-27 | A r20 | PUB-07 |
| "30 October" for both | card (deadline 11-02) keeps 10-30; loan (deadline 10-23) → 10-23 | B r6 | PUB-13 |
| "the 30th" (talkative decoy) | 2026-10-30, never a payment or callback date | style text | all, under `talkative` |

### 16.6 Each case's date decision

| Case | Band and deadline | Date asked or proposed | Decision | Expected |
|---|---|---|---|---|
| PUB-01 | early, 11-02 | today | valid | 10-14 |
| PUB-02 | — | tomorrow 11:00 | inside the callback window, later than `now` | 10-15 11:00 |
| PUB-03 | early, 11-02 | — | identity failed; no dates | — |
| PUB-04 | late, 10-23 | 11-06 | after the deadline → A r23 | 10-23 |
| PUB-05 | late, 10-23 | — | hardship; no dates | — |
| PUB-06 | late, 10-23 | floor; attempt 1 or her own "this Friday" | valid | 10-16 |
| PUB-07 | early, 11-02 | vague → "Monday the 26th" | holiday → A r20 → next business day | 10-27 |
| PUB-08 | early, 11-02 | — | already paid; no dates | — |
| PUB-09 | late, 10-23 | — | restructuring; no dates | — |
| PUB-10 | late (8), 10-23 | attempt 1 "this Friday" | valid | 10-16 |
| PUB-11 | late, late, early | attempt 1 "this Friday" for each | valid for all; B r6 not triggered | 10-16 ×3 |
| PUB-12 | late, late, early | card: "tomorrow"; loans: attempts on 10-16 and 10-23 (p2), 10-16 (p3) | card valid; loans refused | card 10-15 |
| PUB-13 | early 11-02, late 10-23 | one date 10-30 | card keeps it; loan → its deadline | 10-30 and 10-23 |

### 16.7 What changes on other calendar days [INFERRED unless cited]

- The final runs "on several calendar days" [DOC RM:76; HP §Evaluation L27] and the hidden briefs bring "another calendar" [DOC HP §Overview L12; RM:71]. Nothing may be hard-coded to 2026-10-14, to "Friday" or to this holiday list.
- When today is the last business day of its week, attempt 1 moves to the last business day of next week (A r30).
- "Next Friday" said on a Friday is the Friday of the following week (A r22).
- "Tomorrow" said on a Friday is a Saturday: as a promise date it goes to A r20 (offer the next business day); as a callback it is outside A r6's window, so A r7 (ask once for another time) applies.
- A week containing a holiday can make "this Friday" a holiday; then A r20 applies to it.
- Callbacks must be later than `now`, so "today at the current hour" is invalid.
- Every date sent to the bank is `YYYY-MM-DD`; every callback time is `HH:MM` [DOC OA:191-194, 311-318; PROBED-earlier RAT:156, 158].

---

## 17. Traps to remember

1. **The judge never sees the brief.** It gets only the case's `checks` [CODE RC:47]. Passing practice proves nothing about rules no check names, and the hidden cases have their own checks.
2. **Two scorers, both must pass.** The ledger (outcome, promises, notes, callbacks, transfers, last call, early `get_account`, not-reached tools) and the judge's `"pass"` [CODE SC:17-34; RC:93-97]. No partial credit; the final needs 3 of 3 runs [DOC RM:65, 76].
3. **`close_call` must be the last ledger call.** After the agent's goodbye the persona says "Thank you, goodbye." and goes silent [CODE RC:24]; a missing close fails SC:28-29.
4. **No reason on `promise` or `paid`.** The scorer compares to `None`; `""`, `"none"` or `"promise"` fail if stored [CODE SC:19-20]. Omit the key.
5. **Never call `get_account` before both answers pass**, not even to answer "how much do I owe?" (PUB-03). One "identity not verified" result fails the case for good [CODE SC:30-32].
6. **In a not-reached case, any `verify_identity` or `get_account` fails** (PUB-02) [CODE SC:33].
7. **Brief A never writes notes** (A:119). A Brief-B habit (`paid` in PUB-08, `hardship` in PUB-05) fails the ledger.
8. **Brief B must write notes**: one `add_note` per unpromised product, no duplicates, none on promised products [DOC B r8, B:16; CODE SC:23-24]. The reason depends on the situation: `refused`, `hardship`, `dispute`, `paid` or `service_error` (B:16). `refused` is only PUB-12's case (two `refused` notes, PTS:558-567). On any transfer (restructuring, support, human) write no notes at all, before or after it (B r10, B:18).
9. **Phone digits as words are counted wrong** [PROBED-earlier RAT:151]. Always send four digits; "oh" = 0.
10. **Never verify half an answer** (`pieces`). A guessed year is a readable, counted wrong answer.
11. **Use the corrected value** (`corrects`). The first value is often a valid but wrong date: Thursday 10-15 (PUB-10, PUB-11), "tomorrow" vs "today" (PUB-01), 10:00 vs 11:00 (PUB-02), the true DOB (PUB-03).
12. **"The 30th" is a decoy** (`talkative`): 2026-10-30, a valid-looking business day. But in PUB-13, 30 October is the customer's real date. Never ignore a number blindly.
13. **A question back is not a refusal** (`asks_back`). Answer, then let the customer answer. Strict A r15 would close `declined` after two questions in identity and fail every case [DOC A:44; CODE RC:31].
14. **When answering a question back to a count-limited question** (the exact-day ask in PUB-07, the phone re-ask in PUB-12), do **not** repeat the question: that would be a second ask.
15. **"Collections", "debt", "payment" and the product are banned until both answers pass**, for everyone, including relatives [DOC A:24]. "Account" is allowed to the customer (A r15 uses it) but not to a relative (A r10).
16. **Turn down a relative's offer to pay without the word "payment"** (PUB-02).
17. **The opening sentence needs "recorded"**; BA's opening omits it [CODE BA:105].
18. **"Am I speaking with {title} {last_name}?", "Can you make this payment today?", "Do you confirm?" and "You will receive a text message confirming this promise." are exact strings.** The SMS sentence goes after `ok:true`, never in the read-back, never in a non-promise call (PUB-08).
19. **Say "recorded" only after `ok:true`.** On the first failure, use no success word at all, then retry once with the same arguments (PUB-10) [DOC A:91].
20. **Treat only an explicit `ok` of `true`/`"true"`/`"True"` from the latest call as success.** The PUB-10 failure may be a 500 or a 200 with `ok:false` [UNCERTAIN]; booleans arrive as strings [DOC TC:262-286].
21. **`maxRetries: 0` on write tools.** Engine retries can duplicate a write or hide the failure the brief expects you to see [DOC TC:365].
22. **"Exactly once" is judged on the transcript**: a first `create_promise` rejected for format, then a good retry, passes the ledger and fails PUB-01's check.
23. **Never ask "how much can you pay?"** The agent proposes every amount [DOC A:70]. PUB-06's persona answers "you tell me", proving the breach in the transcript.
24. **Offer the floor once, with "the rest stays overdue"**, then propose only dates for that payment (PUB-06). Whether that one offer is for today or is attempt 1 on Friday is [UNCERTAIN], and chapter 06 (U-1) defaults to Friday (§7(i) item 1).
25. **Attempt 1 is the full amount unless the customer already said "too much"**; then it is the floor (PUB-06 vs PUB-10) [DOC A:79].
26. **A proposed date or amount is never a refusal** (A r29): PUB-04's 6 November, PUB-07's vague period, PUB-12's "tomorrow", PUB-13's 30 October.
27. **A date after the deadline gets the deadline at the full amount (A r23), not attempt 2's floor** (PUB-04: 1250.0, not 400.0).
28. **A vague period gets exactly one exact-day question** (PUB-07). Freya's date extractor turns vague expressions into dates by default [DOC WF:578]; that must be overridden.
29. **A holiday inside the deadline gets the next business day after that day**, not after today (PUB-07: 10-27, not 10-15). The bank records holidays without complaint [DOC OA:6].
30. **Deadlines are business days after today, today excluded, holidays skipped**: late 2026-10-23, early 2026-11-02 on the practice day. Compute in code, from `now`, never the real clock [DOC A:20; WF:240].
31. **`days_late` 7 is early and 8 is late** (PUB-12's car loan, PUB-10's card) [DOC A:59-60].
32. **Hardship comes before persuasion and restructuring** (A r32): one sympathy sentence, one support offer, zero attempts, even with two attempts "available" (PUB-05).
33. **A discount is not restructuring**; answer "I'm not able to offer a discount" and stop (PUB-05) [DOC A:84, 98].
34. **"Lower instalments" means transfer at once, with no plan and no monthly figure** (PUB-09). Call the bank's `transfer_to_agent`, not a platform transfer node, then still `close_call`.
35. **"I already paid" means one sentence, no promise, close `paid`** with no reason and no note (PUB-08). Do not argue or invent an appearance date.
36. **After three wrong answers: no more questions, "mobile app or a branch", `not_verified`/`failed`** (PUB-03). Trust the tool's counter.
37. **Re-ask only the failed identity question** (PUB-12): the phone again, never the DOB.
38. **Brief B: state every product before any ask; one today-ask; then product by product in `get_account` order, each starting at attempt 1** [DOC B:10-12].
39. **Brief B: attempts and bands are per product** (PUB-12: two on the late loan, one on the early car loan; no floor on the early product).
40. **Brief B: one combined read-back, one "Do you confirm?", then one `create_promise` per product** (PUB-11). Per-product proposals must not sound like read-backs, and post-record lines must not re-list amounts and dates.
41. **Brief B: one date past one product's deadline moves only that product**, and the read-back names both dates (PUB-13).
42. **Brief B: `promise` wins when any promise was recorded** (PUB-12 closes `promise` despite two refusals) [DOC B:23].
43. **Brief B: write notes at the end.** B r10 forbids any note on a transfer, "before or after it" [DOC B:18].
44. **Card digits are not phone digits.** They coincide in PUB-11 and PUB-13 but not in PUB-12 (phone 4410, card 9015).
45. **The loan's floor can equal another product's past-due** (PUB-13: 300 and 300). Keep per-product state in code.
46. **Product ids come only from `get_account`** (`p1`, `p2`, …); an invented id gets "unknown product_id" [DOC RM:102].
47. **Dates to the bank are `YYYY-MM-DD`, times `HH:MM`.** `"2026-10-16T00:00"` fails the scorer; `"11am"` is rejected [CODE SC:21; PROBED-earlier RAT:156, 158].
48. **Speak after every tool result.** Silence after a bare `{"ok": true, "verified": true}` is the documented way to lose a call [DOC TC:570].
49. **Watch the 420-second cap and slow turns.** Talkative customers and three-product calls (PUB-12 is the longest) are the risk [CODE FR:87; RC:116-118].
50. **The persona has no calendar and no amounts.** A wrong mapping of "this Friday" or a wrong amount is caught only by the ledger, never by the customer [CODE RC:13-24].
51. **The style never changes the expected ledger** [CODE RC:26]. If a style seems to force a different outcome (for example `declined` under `asks_back`), the agent's reading is wrong, not the case.

---

## Appendix · Persona cache keys (computed locally from `persona_for`)

`run_cases.py` stores personas in `.personas.json` under `id + ":" + sha1(json.dumps(spec, sort_keys=True))[:10]` [CODE RC:57]. A different key means a new persona is created on the Freya side.

| Case | none | asks_back | corrects | in_words | pieces | talkative |
|---|---|---|---|---|---|---|
| PUB-01 | `6d35a36de2` | `d262c4491a` | `38aa798dde` | `c15d252cfc` | `22fc56c6b0` | `3ffaa4533b` |
| PUB-02 | `ba4c2d3ab2` | `6beac8a118` | `983e5dd8c3` | `809600d6c6` | `5ab1e4f80d` | `789f9fc021` |
| PUB-03 | `399d279120` | `bf09dba3c5` | `5b02c80f06` | `523b0335ef` | `7462a73642` | `e5bc1d34b4` |
| PUB-04 | `430984b28c` | `38674a5035` | `e923c3b4fb` | `5b76af8220` | `47b4a9a192` | `dd6d32c824` |
| PUB-05 | `d3e8d22f1f` | `9b532f9e8f` | `f202d6b643` | `1a09f9af66` | `c645df0d34` | `76604b9e52` |
| PUB-06 | `8006500ad0` | `a39038849d` | `f0979ffbad` | `821dd09be9` | `82b0b57e55` | `e7417a6e8d` |
| PUB-07 | `88e0074cce` | `b97b01bca7` | `38132b79b7` | `39430e0497` | `2e185d04c1` | `82f0e9e6a7` |
| PUB-08 | `7c00510fad` | `a6f55287ce` | `5e1e9e3c8a` | `49c0f2917e` | `155d7cbe4f` | `3f3584365c` |
| PUB-09 | `f4e0bb8e34` | `aba384e1ae` | `24113c9341` | `443f76c2f1` | `b167bb570a` | `ea6fac1b66` |
| PUB-10 | `af076838b4` | `dd15e4cdfa` | `a97937706e` | `cf1013b3b0` | `78fb7a8cec` | `0e19fab9e2` |
| PUB-11 | `ddc01c9209` | `047b8c7235` | `d790c26776` | `7721a11019` | `e4c694256e` | `73c630b13c` |
| PUB-12 | `710916c439` | `2c565e65d4` | `8708f512e6` | `f3e2f04d43` | `76f8ae9c1a` | `0c4729679f` |
| PUB-13 | `9e606cc042` | `5d71d5e780` | `586882c1dd` | `bce864667a` | `5968fe4fe3` | `7b3a2a2cbb` |
