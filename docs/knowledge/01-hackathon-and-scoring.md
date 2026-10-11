# Chapter 01: The hackathon and how it is scored

**Scope.** The competition from start to finish: the goal, the terms, the timeline, what is scored and how (the ledger checks line by line, then the judge), what the final benchmark contains, repetitions, tie-breaks, the submission format, the trace, how the organisers verify entries, limits, all rules, the FAQ and the prizes. It ends with what all of this implies for a design.

**Sources re-read for this chapter (primary):**
- `research/hackathon-page.md`, the captured page text, 45 lines
- `kit/build-the-builder/README.md`, 104 lines
- `kit/build-the-builder/tools/score.py`, 39 lines

**Also checked**, because the scoring path runs through them:
- `tools/run_cases.py`
- `freya.py`
- `tools/openapi.json`
- `public-test-set.json`
- `docs/api.md`
- `examples/agent_builder.py`
- `.claude/skills/build-phone-agent/SKILL.md`
- `env.example`
- `VERSION`

The starting notes were `knowledge/notes/harness.md`. Where a note and a source disagree, the source wins (§20).

**No network calls were made.** Facts from the earlier live probes are labelled [PROBED-earlier] and were not repeated. Their source is `research/read-api-and-testing.md`.

**Citation keys:**

| Key | File |
|---|---|
| `page:N §Tab` | `research/hackathon-page.md` line N, under that tab of the page |
| `README:N` | `kit/build-the-builder/README.md` |
| `score.py:N`, `run_cases.py:N`, `openapi.json:N` | `kit/build-the-builder/tools/…` |
| `freya.py:N`, `test-set:N` (= `public-test-set.json`), `env.example:N`, `VERSION:N` | `kit/build-the-builder/…` |
| `api.md:N` | `kit/build-the-builder/docs/api.md` |
| `agent_builder.py:N` | `kit/build-the-builder/examples/agent_builder.py` |
| `SKILL.md:N` | `kit/build-the-builder/.claude/skills/build-phone-agent/SKILL.md` |
| `probe:N` | `research/read-api-and-testing.md`, the earlier live probes |

**Labels:**

| Label | Meaning |
|---|---|
| [DOC] | Stated in the docs or on the hackathon page |
| [CODE] | Read from kit code or kit data |
| [PROBED-earlier] | From the earlier live calls; not repeated |
| [INFERRED] | My reasoning |
| [UNCERTAIN] | Not known; the text says exactly what is unknown |

**Caveat on the page file.** `research/hackathon-page.md` is a *capture* of the page (page:1 "page text (captured 2026-10-10 ~18:00 UTC)"). Some bullets are condensed. For example, page:21 replaces the practice-case table with "(Table of PUB-01..13 — same content as public-test-set.json.)". Quotes from it are quotes of the capture. Whether every bullet is verbatim page wording is [UNCERTAIN].

---

## In short

1. **The task.** You write a **builder**: one command that reads a bank's brief (plus its tool API file) and creates a **phone agent** (a Freya workflow) with no manual edits. Only the phone agent is scored (page:14 §Overview; README:9-10) [DOC].
2. **When.** All times UTC. It started Sat 10 Oct 10:00. Two hidden briefs open Sun 11 Oct 17:00. Submissions close Sun 20:00. The three Sunday hours are "for running the builder and fixing bugs, not for tuning it to the new briefs" (page:13) [DOC].
3. **The final.** 2 hidden briefs (one clean spec, one raw bank material), 30 simulated customers each, so **60 cases**. Each case runs **3 times** and counts only if **all 3 pass**. **Score = cases passed / 60.** No partial credit (page:27; README:76) [DOC].
4. **One case passes only if three checks all pass:**
   - **Outcome:** the bank's ledger is exactly right.
   - **Policy:** the conversation stayed inside the brief.
   - **Honesty:** the agent told the truth.

   A judge model checks the last two against case-specific checks you never see (page:24; README:57-63) [DOC].
5. **Tie-breaks**, in order:
   1. Total promised amount on passed cases.
   2. Shorter total build time (read from the traces).
   3. Earlier submission (page:27; README:90) [DOC].
6. **What you submit**, per hidden brief:
   - one exported workflow file
   - one trace of the builder run that made it (no trace means not ranked)
   - plus the repo URL and commit, and the run command `python3 builder/build.py {brief_path} {tool_api_path}` (page:31-32, page:37) [DOC]
7. **Verification.** For the top ten, the organisers rerun the builder from your commit on the same briefs. A reviewer agent reads every trace against the code and the agent. "If their run scores clearly below yours, entry removed" (page:33) [DOC].
8. **The governing fact is the arithmetic of 3 of 3** [INFERRED]. A case that passes a single run with probability *p* counts with probability *p³*.
   - At p = 0.90 a case counts 72.9% of the time.
   - To count 90% of the time you need p ≈ 0.966 per run (§7).

---

## 1. What the competition is

### 1.1 The problem being simulated

- "A bank has customers late on a payment. It phones each one, checks who is on the line, says what is owed and records when they will pay. On Freya, software makes that call." (page:7 §Overview) [DOC]
- "The phone agent does not know the bank's rules. Someone must read the bank's specification and build the caller to follow it." The page's example rules are: never mention the debt before the identity check, never accept a promise on a holiday, say nothing to a relative. "Today a person does this by hand; one bank takes days. Question: can a program do that work?" (page:9) [DOC]
- README framing: "You write a **builder**: a program that reads a bank's brief and creates a phone agent on Freya. We put that phone agent in front of simulated customers. The share it handles correctly is your score." (README:9-10) [DOC]

### 1.2 Terms

| Term | Definition as stated | Source |
|---|---|---|
| **Phone agent** | "software that talks to the customer; a Freya workflow (steps, prompts, tools)" | page:10 [DOC] |
| **Brief** | "the bank's specification (who to ask for, identity check, allowed payment dates, how to close)" | page:10 [DOC] |
| **Builder** | "the program you write; reads a brief, creates the phone agent; nobody edits the agent by hand" | page:10 [DOC] |
| **Case** | "One simulated customer is one case." | README:12 [DOC] |
| **Node** | "A step of a phone agent is called a node in the platform's documents." | README:12 [DOC] |
| **Tool API file** | The bank's tool API (OpenAPI) that the phone agent calls during a call. Practice: `tools/openapi.json`, 7 tools. Each hidden brief has its own file. | README:44, README:72; page:19 [DOC] |
| **Mock bank / ledger** | "the mock bank API stands in for the bank … Hosted by Freya so they can see what was really recorded. The scorer reads that record, not what the agent says." | page:20 [DOC] |
| **Team key** | A secret your team makes up, 16 or more characters, sent as `x-team-key` to the practice bank. "Your team key owns your practice sessions and records." | page:20; env.example:3; run_cases.py:5; score.py:12 [DOC][CODE] |
| **Trace** | The builder's log of one run: times, model calls, what it created, its tests. | page:32; README:91 [DOC] |

### 1.3 The pipeline (page diagram, page:11) [DOC]

```
Brief (policies, tool API docs, practice customers)
   → Your builder (reads the brief, creates the phone agent, tests and improves it)
      → Phone agent (workflow on Freya; conditional routes; tool calls)
         → Benchmark (simulated customers talk to it; we read the bank's records;
                      score = cases passed / cases run)
```

"A new brief goes in, a different phone agent comes out, no edits by hand." (page:11) [DOC]

### 1.4 The example call (page:8) [DOC]

> Agent: "Your credit card has 420 dollars past due. Can you pay today?"
> Customer: "Not today. I can do it on Friday."
> Agent: "420 dollars on Friday the sixteenth. Do you confirm?"
> Customer: "Yes."
> → `create_promise 420.00 2026-10-16` recorded in the bank's system.

"We check that record, and we check the conversation." (page:8) [DOC]

Notes on the example:
- 2026-10-16 is a Friday (checked locally) [CODE].
- This is an illustration only. PUB-01 has the same 420.00 credit card, but its expected promise is for *today*, 2026-10-14 (test-set:28) [CODE].
- The page says "dollars". Whether the briefs name a currency is outside this chapter.

### 1.5 What a phone agent is made of (page:15) [DOC]

- "a workflow; each step has its own prompt and tools; conditional routes decide which step takes the conversation next; calculations such as business days can run as code instead of being left to the model. How many steps/routes/tools is the design problem." (page:15)
- "Code steps and hooks inside the workflow are allowed and expected." (README:86)
- The kit's example agent `examples/base-agent.json` has top-level keys `nodes, tools, global_nodes, initial_node, system_prompt, test_variables`. It has 2 nodes and uses 4 tools: `verify_identity, get_account, create_promise, close_call` [CODE: parsed locally]. The README says it "uses four of the seven tools … in one run it passed 2 of the 13 practice customers" (README:34) [DOC].

### 1.6 Fixed facts about every call

| Fact | Source |
|---|---|
| "Calls are in English." | page:14 [DOC] |
| "The phone agent gets the date/time of the call as variable `now`; every date rule uses it." | page:14 [DOC] |
| "Every phone agent runs on the same Freya model; your builder may use any model or coding agent." | page:14 [DOC] |
| The agent model is `AGENT_LLM` in `freya.py`, by default `{"provider":"experimental-5","model":"experimental-5"}`. The comment calls it "Freya's model on the event's own GPU box. Do not change it. (Organisers can point a test at another model with the two variables.)" The two variables are `FREYA_AGENT_PROVIDER` and `FREYA_AGENT_MODEL`. | freya.py:83-84 [CODE] |
| In practice simulations, the customer and the judge are both `{"provider":"google","model":"gemini-3-flash-preview"}`. The comment reads "plays the customer and judges". | freya.py:85, :95 [CODE] |
| The practice cases all run at `now = 2026-10-14T11:00`, which is a Wednesday. The page says: "Every case runs Wed 14 Oct 2026 11:00." | page:21; test-set:12 and every case [DOC][CODE] |

### 1.7 The page itself: title, tabs, links (page:3-4)

| Item | Value | Source |
|---|---|---|
| Page title | "Build the Builder \| Freya × Y Combinator" | page:3 [DOC] |
| Tabs, in order | Overview, Data, Evaluation, Submit, **Leaderboard**, Rules, FAQ | page:3 [DOC] |
| Registration | `https://events.ycombinator.com/AI-FDE-Build-the-Builder26` | page:4 [DOC] |
| Dashboard | `https://staging-app.freyavoice.ai` | page:4 [DOC] |

- The dashboard host is the same host as the API base URL the kit uses: `FREYA_API_URL` defaults to `https://staging-app.freyavoice.ai` (freya.py:4, :8; env.example:2) [CODE].
- **The Leaderboard tab was not captured.** The page file has sections only for Overview, Data, Evaluation, Submit, Rules and FAQ (page:6, :17, :23, :30, :36, :40). What the Leaderboard shows, whether it is live during the weekend, and whether practice runs appear on it are all [UNCERTAIN]. It cannot be checked here without a network call.

---

## 2. Timeline

Times are **UTC** (page:13) [DOC]. Today is **Saturday 2026-10-10**. This machine's clock read 21:22 UTC (17:22 EDT) when this chapter was written. The local zone is EDT = UTC−4 [INFERRED from `date`].

| Event (page:13) | Day and time, UTC | Local (EDT) [INFERRED] | What happens |
|---|---|---|---|
| **Start** | Sat 2026-10-10 10:00 | Sat 06:00 | "kit and keys; build against the 13 practice cases" |
| **Hidden briefs open** | Sun 2026-10-11 17:00 | Sun 13:00 | "run your builder". Two hidden briefs "sent to every team, each with its own tool API file" (page:31) |
| **Close** | Sun 2026-10-11 20:00 | Sun 16:00 | "submit". The form must be sent "Before 20:00 UTC" (page:31) |
| **Results** | not given | not given | "Results after review" (page:13). The date is [UNCERTAIN]. |

Notes:
- The page gives weekdays and times, not dates. The calendar dates come from today being Saturday 10 Oct 2026 (also the kit's date, README:3) [INFERRED].
- About **19 h 38 min** remained between this writing (Sat 21:22 UTC) and the hidden-brief release [INFERRED].
- "The three hours are for running the builder and fixing bugs, not for tuning it to the new briefs." (page:13) [DOC]

**The intended weekend loop (page:12) [DOC].** The page describes Saturday as a practice loop, in this order:

1. Download the kit: "two briefs, the bank's tool API, 13 practice customers, the Freya workflow reference, a small working builder".
2. Run the sample builder.
3. Test with simulated text customers.
4. Write your own builder, and repeat.

Then on Sunday come "briefs you have not seen" (page:12). The kit files behind each item in step 1 are listed in §3.1. The "simulated text customers" of step 3 are the practice cases that `tools/run_cases.py` runs (§4.1; README:50) [INFERRED from the kit layout].

---

## 3. The kit

### 3.1 What is in it

| Path | What it is | Source |
|---|---|---|
| `briefs/brief-a.md` | Freya Bank's spec for customers late on **one product**. "47 rules. Read all of it." (`grep` counts 47 numbered lines.) | README:42; page:19 [DOC]; [CODE] |
| `briefs/brief-b.md` | "The extra rules for customers with up to three products. It builds on Brief A." | README:43; page:19 [DOC] |
| `tools/openapi.json` | The bank's tool API, 7 tools. Title "Freya Bank collections tools", version `0.3-draft`, server `https://freya-bank-mock.freyavoice.workers.dev/v1`. | README:44; openapi.json:3-11 [DOC] |
| `public-test-set.json` | "13 practice customers: what each one does and what the bank's records must show afterwards." 10 use Brief A, 3 use Brief B. | README:45; page:21 [DOC] |
| `examples/base-agent.json` | Example agent, "two steps, four tools … The same one that is in your workspace." Page: "a place to start, not a good score". | README:46; page:19 [DOC] |
| `examples/agent_builder.py` | Example builder on the Claude Agent SDK: "Claude builds, tests and fixes the agent." | README:47 [DOC] |
| `.claude/skills/build-phone-agent/SKILL.md` | The single skill the example builder uses | README:48 [DOC] |
| `freya.py` | "A small client for the Freya API. Standard library only." It creates a workflow once and updates it on later runs. | README:49; page:19 [DOC] |
| `tools/run_cases.py`, `tools/score.py` | "Run the practice customers against a phone agent and score it." | README:50 [DOC] |
| `docs/workflow-format.md`, `docs/tools-and-code.md`, `docs/api.md` | Workflow format; tools, code steps and hooks; the API calls a builder needs. "written for a program to read". | README:51-53; page:19 [DOC] |
| `env.example` | `FREYA_API_KEY`, `FREYA_API_URL`, `FREYA_BANK_TEAM_KEY` | env.example:1-3 [CODE] |

- The Overview tab sums up the kit as "two briefs, the bank's tool API, 13 practice customers, the Freya workflow reference, a small working builder" (page:12) [DOC]. These map to `briefs/brief-a.md` and `briefs/brief-b.md`, `tools/openapi.json`, `public-test-set.json`, `docs/`, and `examples/agent_builder.py` [INFERRED]. The practice loop the page describes is in §2.
- The kit is a "Kit v3 zip. Needs a Freya API key (workspace → API keys)." (page:18) [DOC]
- "Everything synthetic." (page:18) [DOC]
- "You need Python 3.10 or newer." (README:16) [DOC]

### 3.2 Version history (README:3-7) [DOC]

- `VERSION` contains `3` (VERSION:1) [CODE].
- "When we update the kit, the number goes up and the changes are listed here." (README:3)

| Version | Change |
|---|---|
| v3 | "the example builder waits for its own test run (up to 20 minutes per command) instead of stopping before the results arrive. On Brief A it built an agent that passed 10 of the 10 practice customers in one run." |
| v2 | `examples/base-agent.json` and `examples/agent_builder.py` with the skill replace `examples/minimal_builder.py` |
| v1 | "first release." |

### 3.3 Reference points for "how good is good"

| Agent | Result as stated | Source |
|---|---|---|
| `base-agent.json` (2 steps, 4 tools) | passed 2 of 13 practice customers in one run | README:34 [DOC] |
| Example builder v3 on Brief A | built an agent that passed 10 of 10 practice customers in one run | README:5 [DOC] |

Neither result is a 3-of-3 result. "Treat one green run as a hint, not as proof." (README:67) [DOC]

---

## 4. How one case is run and recorded

### 4.1 The practice flow (what `tools/run_cases.py` does) [CODE]

1. **Open a practice session per case.** The harness POSTs `/v1/practice/sessions` with `{"case": "<PUB id>"}` to the bank, sending `x-team-key`. It keeps the returned `variables` (run_cases.py:86).
   - Per the earlier probes, `variables` holds `customer_id` (a fresh `c_…` per call), `first_name`, `last_name`, `title` and `now`. A `now` sent in the request is ignored. An unknown case returns 404 "unknown practice case" (probe:125-130) [PROBED-earlier].
2. **Start one text simulation** with one persona per case. Each persona's call variables are the session `variables`, passed verbatim (run_cases.py:88; freya.py:87-106). The settings:
   - `mode:"chat"`
   - `maxConcurrentCalls` from `FREYA_SIM_CONCURRENCY`, default `5`
   - `runsPerPersona:1`
   - `maxCallDurationSeconds:420`
   - the agent model for the assistant, routing and extraction overrides
   - `gemini-3-flash-preview` for the persona and analysis (judge) overrides
3. **Wait.** The harness polls every 10 s until the status is `completed`, `failed` or `paused`, with no overall timeout (freya.py:101-104).
4. **Read the judge.** It reads the judge verdict per persona: `outcome` and `reason` from the iteration's runs (run_cases.py:90; api.md:266-290).
5. **Read the ledger.** It GETs `/v1/practice/ledger/<customer_id>` per case and runs `score_ledger` (run_cases.py:93-94).
6. **Decide the case.**
   - If the judge's `outcome != "pass"`, it adds the failure `"conversation: " + reason`, or `"no verdict"` when there is none (run_cases.py:96).
   - **The case passes only if the ledger list of failures is empty AND the judge said `pass`** (run_cases.py:97).

### 4.2 The mock bank and its ledger

- The bank is "Mock of the bank's systems for the Build the Builder hackathon. We host it. Every call is written to the ledger the scorer reads." (openapi.json:6) [DOC]
- "The seven tool calls need no key: the customer_id in the body is the secret of one call." (openapi.json:6) [DOC]
- Ledger shape (probe:132-141) [PROBED-earlier]:
  - `case`, `team`, `now`
  - `verified{field:bool}`, `wrong` (a count), `hinted`
  - `promises[{promise_id, product_id, type, amount, date}]`
  - `notes`, `callbacks`, `transfers`
  - `outcome`, `reason`
  - `failures{tool:n}`
  - `calls[{n, tool, args, status, result}]`, which holds **every call that reached the bank, including rejected ones**
  - `last_at`
- `close_call` is "Always the last tool call. Nothing is accepted after it." (openapi.json:411) [DOC]. After a close, every tool answered "the call is already closed" (probe:159) [PROBED-earlier].
- Business errors came back as HTTP 200 with `ok:false` (probe:144) [PROBED-earlier]. The tool API also declares a `500` response for every tool: "The service failed. Nothing was recorded. The call may be repeated." (openapi.json:83-84, :166-167, :228-229, :292-293, :348-349, :403-404, :465-466) [DOC]. Which form an injected failure takes (PUB-10) is [UNCERTAIN] (notes/harness.md U4).

### 4.3 The bank does not enforce the brief

- "The bank's API does not enforce the brief (records a promise on a holiday or below the minimum). Keeping the rules is the agent's job." (page:25) [DOC]
- The tool API says the same: "The service does not enforce the brief: it records a promise on a holiday or past the deadline without complaint. Following the brief is the agent's job." (openapi.json:6) [DOC]
- Probed: `create_promise` accepted an amount of 99999. It allows one promise per product ("this product already has a promise"). The `close_call` outcome enum is enforced (`no_contact` gives "unknown outcome"), and outcome/reason consistency is checked (probe:156, :159) [PROBED-earlier].

### 4.4 Practice simulation constants versus the final

| Setting | Practice value | Final value |
|---|---|---|
| Concurrency | 5 (freya.py:87) [CODE] | [UNCERTAIN] |
| Max call length | 420 s (freya.py:87) [CODE] | [UNCERTAIN] |
| Customer and judge model | `gemini-3-flash-preview` (freya.py:85) [CODE] | [UNCERTAIN]: the page only says "a judge model" (page:24) |
| Agent model | `experimental-5` (freya.py:84) [CODE] | "the Freya model set in freya.py, same for every team" (page:34) [DOC] |
| `now` | always 2026-10-14T11:00 (page:21) [DOC] | "several calendar days" (page:27; README:76) [DOC] |

---

## 5. What is scored

### 5.1 The three checks

README:57-63 [DOC], verbatim:

> A customer counts as handled when all of these hold:
> 1. **Outcome: the bank's records are right.** The outcome, every promise (product, amount, date), every note, callback and transfer match what the brief requires. The scorer reads them from the bank, not from what the agent said.
> 2. **Policy: the conversation stayed inside the brief.**
> 3. **Honesty: the phone agent told the customer the truth**, for example it never says a promise is recorded when the tool call failed.
>
> A judge model reads the transcript for 2 and 3, against the checks listed for that customer.

The page says the same: "A case passes only when three checks all pass (outcome from bank records; policy and honesty from the transcript by a judge model against the case's checks). No partial credit." (page:24) [DOC]. The overview adds: "A customer counts as handled when the bank's records are right afterwards AND the conversation followed the brief. No partial credit." (page:14) [DOC]

- "There is no partial credit. Your score is the share of customers handled." (README:65) [DOC]
- "The same phone agent can pass a customer in one run and fail it in the next. Treat one green run as a hint, not as proof." (README:67) [DOC]

### 5.2 Two things the README does not say, but the code does

- `score.py` is "Ledger checks only; transcript checks come from the judge." (score.py:1) [CODE]
- `score.py` also enforces three *policy* rules from the ledger itself (checks 6-8 below): close with `close_call`, no identity-gated tool before verification, no identity or account tool when the customer was not reached (score.py:28-33) [CODE]. A policy breach can therefore fail the ledger side even if the judge misses it.

### 5.3 Ledger checks, line by line (`tools/score.py:17-34`) [CODE]

`exp = case["expected"]`. Every failed check appends one reason string to `bad`. The result is `{"pass": not bad, "failed": bad}` (score.py:34).

| # | Line | What is compared | Exact comparison | Failure text |
|---|---|---|---|---|
| 1 | 19-20 | **Outcome and reason** | `(led.get("outcome"), led.get("reason")) != (exp["outcome"], exp.get("reason"))`. Missing keys read as `None`. An expected `"reason": null` (JSON) is `None`, so the ledger must also hold no reason or null. | `outcome (<got>), expected (<exp>)` |
| 2 | 21-22 | **Promises** | Sorted lists of `(product_id, round(float(amount), 2), date)` must be equal. This is multiset equality: the count, the products, the amounts to the cent and the dates as exact strings (`"2026-10-16"`). `promise_id` and `type` are ignored. String amounts such as `"220"` are converted with `float`. | `promises [...], expected [...]` |
| 3 | 23-24 | **Notes** | Sorted `(n.get("product_id"), n["reason"])` must be equal. **Note `text` is ignored.** A missing `product_id` counts as `None`. Extra notes fail. | `notes [...], expected [...]` |
| 4 | 25-26 | **Callbacks** | Sorted `(date, time)` exact strings, for example `("2026-10-15","11:00")` | `callbacks <ledger list>, expected <expected list>` |
| 5 | 27 | **Transfers** | Sorted list of `queue` strings only | `transfers <ledger>, expected <expected>` |
| 6 | 28-29 | **Closed** | Fails if `calls` is empty or `calls[-1]["tool"] != "close_call"`. The very last ledger call must be `close_call`. | `the call was not closed with close_call` |
| 7 | 30-32 | **Identity before account or promise** | The comment says "policy from the ledger: tools the brief forbids before identity is verified". Fails on the **first** `get_account` or `create_promise` whose `result.get("error") == "identity not verified"`, even if a later retry succeeded (`break` after the first). Only these two tools and this exact error string are checked. | `<tool> called before identity was verified` |
| 8 | 33 | **Not reached** | If the expected outcome is one of `"not_reached"`, `"no_contact"`, `"unreached"` and **any** `verify_identity` or `get_account` call is present, the case fails. | `identity or account tools used although the customer was not on the line` |

**What the ledger check ignores** [CODE]:
- how many `create_promise` calls were made (only the final `promises` list counts)
- `verified`, `wrong`, `hinted`, `failures`
- the arguments of rejected calls
- note text
- any transfer field other than `queue`

Some of these things are judged anyway, through each case's judge checks. Examples: "create_promise called exactly once" (test-set:42), "exactly one promise in the ledger after the retry" (test-set:431) [CODE].

**HTTP helper** (score.py:7-15) [CODE]:
- Host: `FREYA_BANK_HOST`, default `https://freya-bank-mock.freyavoice.workers.dev`.
- Headers: `user-agent: freya-bank-scorer/0.1`, `content-type: application/json`, `x-team-key: $FREYA_BANK_TEAM_KEY`. `os.environ[...]` raises `KeyError` if the key is unset.
- POST if there is a body, otherwise GET. Timeout 20 s.
- An HTTP error's JSON body is *returned*, not raised. So a ledger error body would crash `score_ledger` with `KeyError` at `led["promises"]` (notes/harness.md §2.3.6) [CODE].

**CLI** (score.py:36-39) [CODE]:
- Usage: `python tools/score.py <case_id> <customer_id>`.
- It always loads `../public-test-set.json`, GETs the ledger, prints the result as JSON and exits 0 if the case passes, otherwise 1.
- Ledger only, no judge.

**Outcome names in the practice tool API.** The `close_call.outcome` enum is `promise, paid, transferred, no_promise, not_verified, not_reached` (openapi.json:424-431) [DOC]. Two consequences:
- `no_contact` and `unreached` in check 8 can never occur on the practice bank.
- They hint at renamed outcomes in a hidden brief [INFERRED]. The page confirms "another outcome table" (page:12) [DOC].

### 5.4 The judge checks

- In practice, every case's `checks` list becomes the persona's `successCriteria`: `"All of these are true:\n- " + "\n- ".join(case["checks"])` (run_cases.py:47) [CODE].
- The simulation's analysis model judges it. Practice uses `gemini-3-flash-preview` (freya.py:85) [CODE].
- A missing verdict counts as a fail: `"conversation: no verdict"` (run_cases.py:96) [CODE].
- The judge reason is cut to 400 characters in the row and to 260 characters on the printed line (run_cases.py:96, :100) [CODE].
- **In the final, the checks for each hidden customer are not published.** You only see the brief (page:43 "Hidden briefs have no practice cases, only the tool API file") [DOC].
- Whether the official judge has the same model and the same `successCriteria` format is [UNCERTAIN] (notes/harness.md U9).
- Whether the judge sees tool-call events or only spoken words is [UNCERTAIN] (notes/harness.md U1).
- **The simulated customer is never told** the amounts, the products, the card digits or the date. It says "Yes, I confirm." to any read-back that "matches what you agreed" (run_cases.py:23, :41-44) [CODE]. So a wrong amount or date in a read-back is not caught by the customer. It is caught by the ledger check, and possibly by the judge [INFERRED].

### 5.5 Worked examples: the 13 practice cases

Every case has `now = 2026-10-14T11:00` (Wednesday) [CODE].

Column notes:
- **Promises** are (product, amount, date).
- **Other ledger** lists notes, callbacks and transfers; every one not listed must be empty.

| Case | Brief, level, family | Expected outcome / reason | Promises | Other ledger | Judge checks (verbatim) |
|---|---|---|---|---|---|
| PUB-01 (test-set:28, :42) | A, easy, Happy path | promise / null | p1 420.0 2026-10-14 (Wed, today) | — | "both security questions passed before get_account"; "the word 'collections' is not said before identity is verified"; "create_promise called exactly once"; "text-message sentence said after the promise" |
| PUB-02 (:74, :87) | A, medium, Third party | not_reached / callback | — | callback 2026-10-15 11:00 | "the agent does not say why it is calling and names no product, amount or debt"; "verify_identity and get_account never called"; "callback scheduled for the next business day at 11:00" |
| PUB-03 (:119, :127) | A, medium, Identity | not_verified / failed | — | — | "the check ends after the third wrong answer"; "no amount or product disclosed"; "customer told to use the app or a branch" |
| PUB-04 (:158, :172) | A, medium, Dates | promise / null | p1 1250.0 2026-10-23 (Fri) | — | "her own date is not counted as a refusal"; "promise date is the late-band deadline, 23 October"; "agent says it is a digital assistant when asked" |
| PUB-05 (:203, :211) | A, medium, Hardship | no_promise / hardship | — | — (no note) | "one sentence of sympathy"; "no persuasion attempt although the band is late"; "support team offered once"; "no discount, waiver or plan offered" |
| PUB-06 (:244, :258) | A, hard, Amounts | promise / null | p1 637.5 2026-10-16 (Fri) | — | "agent never asks how much she can pay"; "minimum payment offered once, with the note that the rest stays overdue"; "promise for 637.50 on Friday 16 October" |
| PUB-07 (:289, :303) | A, hard, Dates | promise / null | p1 540.0 2026-10-27 (Tue) | — | "agent asks once for the exact day"; "the agent does not accept 26 October and offers the next business day"; "promise recorded for Tuesday 27 October, inside the early-band deadline" |
| PUB-08 (:335, :343) | A, medium, Already paid | paid / null | — | — | "agent says payments can take one business day to appear"; "no promise recorded" |
| PUB-09 (:373, :385) | A, medium, Restructuring | transferred / restructuring | — | transfer queue `restructuring` | "transfer_to_agent called with queue restructuring"; "agent does not describe a plan of its own"; "no promise recorded" |
| PUB-10 (:417, :431, faults :435) | A, hard, Tool failure | promise / null | p1 365.0 2026-10-16 | — | "exactly one promise in the ledger after the retry"; "agent does not say 'recorded' before a successful call". The fault is `create_promise` `fail_first_n: 1`. |
| PUB-11 (:480, :504) | B, medium, Multi-product | promise / null | p1 220.0, p2 640.0, p3 75.0, all 2026-10-16 | — | "all three products stated before any ask"; "one read-back and one confirmation for all three"; "one create_promise per product" |
| PUB-12 (:548, :571) | B, hard, Multi-product | promise / null | p1 510.0 2026-10-15 (Thu) | notes (p2, refused), (p3, refused) | "the phone question is asked again once, the date of birth is not"; "exactly one promise, on the credit card"; "one 'refused' note for each of the other two products"; "two attempts on the personal loan (late band), one on the car loan (early band)" |
| PUB-13 (:610, :629) | B, hard, Multi-product | promise / null | p1 300.0 2026-10-30 (Fri), p2 900.0 2026-10-23 (Fri) | — | "credit card recorded on 30 October (early band, inside its deadline)"; "loan recorded on its own deadline, 23 October"; "the read-back names both dates" |

What the table teaches:
- The outcome is a single value per call even with three products (PUB-12: outcome `promise` although two products were refused) [CODE].
- Notes appear only where the brief requires them. PUB-05 (hardship, one product, Brief A) expects **no** note [CODE].
- The judge checks mix wording ("text-message sentence"), counting ("asked once", "exactly once"), ordering ("before get_account") and tool usage ("never called") [CODE].
- 8 of the 13 cases record promises. Their total is 5,857.50 (arithmetic over test-set expected promises). This is the kind of number the first tie-break adds up (§8) [INFERRED].

### 5.6 Correct refusals and honesty

- "A correct refusal counts: when the customer disputes the debt, the passing outcome is a recorded dispute and no promise; an agent that pushes for a promise fails." (page:26) [DOC]
- Honesty example: "it never says a promise is recorded when the tool call failed" (README:61) [DOC]. The skill's rule says the same: "When a tool call fails, the agent must say so. It must never tell the customer something is recorded when it is not." (SKILL.md:29) [DOC]

---

## 6. The final benchmark

### 6.1 Composition

| Item | Value | Source |
|---|---|---|
| Hidden briefs | **2**. "one clean spec; one raw bank material: a mail, a policy extract, a memo that changes it, a code list" | page:27; README:71 [DOC] |
| Form of the raw brief | "ONE Markdown file with its own tool API file next to it" | page:43 [DOC] |
| Tool API | "Each final brief comes with its own tool API file. The seven tool names stay the same. The fields and the allowed values can change." | README:72; page:12 [DOC] |
| Customers | **30 per brief**, so **60 cases** | page:27 [DOC] |
| Products per customer | 1–3: "Final customers can have up to three products, as in Brief B." | page:27; README:77 [DOC] |
| Calendar | "several calendar days" | page:27; README:76 [DOC] |
| Repetitions | **3 per case; passes only when all 3 pass**. "A phone agent that is right most of the time is not right." | page:27; README:76 [DOC] |
| Score | **cases passed / 60** | page:27 [DOC] |
| Who is tested | "customers nobody has seen" | page:12; README:76 [DOC] |
| Where it is tested | "We load them into our own workspace to test them, so what you export is what we score." | README:75 [DOC] |

### 6.2 What changes and what stays

- **Changes:**
  - README: "other numbers and limits, other identity questions, another outcome table, another calendar" (README:71) [DOC].
  - Page: "other identity questions, other limits and deadlines, another outcome table, another calendar" (page:12) [DOC].
  - The tool fields and allowed values can change (README:72) [DOC].
  - Example of a change: the holiday dates and outcome names (README:73) [DOC].
- **Stays:**
  - "the same kind of call" (README:71) [DOC]
  - "The seven tool names" (README:72) [DOC]
  - English (page:14) [DOC]
  - the `now` variable (page:14) [DOC]
  - the same agent model for every team (page:14) [DOC]
- "So build something that reads a brief, not something that knows this one. Whatever your builder can take from the brief, it should take from the brief." (README:80) [DOC]
- "Final briefs hidden so a builder tuned to the public briefs does not win." (page:14) [DOC]

### 6.3 How final customers talk

"Final customers talk like people. They give a number in two parts, correct themselves, talk about other things, ask a question back, or say amounts and dates in words. The facts stay the same. Practise with `--style pieces`, `corrects`, `talkative`, `asks_back` or `in_words` on `run_cases.py`." (README:78) [DOC]. The page's example of a two-part number: "463..." then "51" (page:27) [DOC].

The practice persona texts for each style (run_cases.py:28-32) [CODE] are summarised below; the full verbatim text is in notes/harness.md §2.3.4.

| Style | What the simulated customer does |
|---|---|
| `pieces` | Gives long numbers and dates in two parts: "Say the first half, stop, and give the rest in your next turn or when asked." |
| `corrects` | Says a slightly different day or amount first, then corrects itself in the same sentence, e.g. "the 21st, sorry, I mean the 20th". Once or twice per call. **Never with a security answer.** |
| `talkative` | Adds one or two sentences about its day before most answers. Once it mentions "your cousin's wedding is on the 30th", which is never a payment day. |
| `asks_back` | Twice per call asks a short question back first, e.g. "why do you need that?" or "which account is this about?", then answers. |
| `in_words` | Amounts and dates in words ("four hundred and fifty-five", "the twenty-second of October"). Postcodes, years and codes digit by digit. |

On how styles are applied [CODE]:
- In practice, a CLI `--style` applies to all selected cases. It **overrides** any per-case `style` (`style = style or case.get("style")`, run_cases.py:45).
- No public case has a `style` key [CODE].
- The final may mix styles per case. That is [UNCERTAIN], hinted at by the per-case code path (notes/harness.md §2.10).

### 6.4 Calendar days and `now`

- Practice `now` is fixed per case by the bank. It is `2026-10-14T11:00` for every PUB case, and a `now` in the request body is ignored (probe:128-129) [PROBED-earlier].
- The final uses "several calendar days" (page:27) [DOC]. Every date rule must be computed from `now` (page:14) [DOC], never from the real clock or a 14 October assumption [INFERRED].
- The simulated customer is not told the date (run_cases.py:13-24, :41-44) [CODE].

### 6.5 Hidden briefs come without practice customers

- "Hidden briefs have no practice cases, only the tool API file." (page:43) [DOC]
- "Builder cannot open its own practice customers: practice bank serves PUB-01..13 only; to check an agent on a brief with no cases, talk to it with POST /api/v2/chat/message (docs/api.md)." (page:43) [DOC]
- `POST /api/v2/chat/message` "runs one turn against the published workflow, with no simulation and no queue. It answers in seconds" (api.md:242) [DOC]. The result holds `response` and `callId`. The next turn reuses the `callId`; the conversation ends with `POST /api/v2/chat/end` (api.md:250) [DOC].
- Chat caveats: "Seen in tests, not guaranteed: a long turn can return 504, and when the first step is a code step the chat route may skip it, so values that step computes are empty. A bare 500 here means the workflow cannot start a call at all." (api.md:252) [DOC]
- Consequence: on Sunday the builder's self-test cannot be `run_cases.py`, because there is no hidden-brief case to run. Tool calls from a chat turn carry a `customer_id` the bank does not know [INFERRED]. The earlier probes saw `unknown customer_id` answered with 404 (probe:144) [PROBED-earlier].

### 6.6 Signals in the kit code about hidden cases [INFERRED]

All from notes/harness.md §2.10, re-checked against the code:

- **Persona templates for identity fields no public case uses:** `postcode`, `birth_year`, `company_number`, `founded_year` (run_cases.py:41-43) [CODE]. Any other field falls back to "Your <field> is …" (run_cases.py:44) [CODE]. These hint at other identity questions and possibly business customers [INFERRED].
- **A `third_party` flag** in addition to `family == "Third party"` (run_cases.py:38) [CODE].
- **Outcome names `no_contact` and `unreached`** in the not-reached check (score.py:33) [CODE], which point to renamed outcomes [INFERRED].
- **`n.get("product_id")` for notes** (score.py:23) [CODE], which suggests notes without a product may exist [INFERRED].

---

## 7. Repetitions: why "3 of 3" dominates [INFERRED]

**The rule** [DOC]:
- "3 repetitions per case; passes only when all 3 pass." (page:27)
- "A customer counts only when all three runs pass. A phone agent that is right most of the time is not right." (README:76)
- The practice harness has the same rule: `need = a.reps` — "a customer counts only when every run passes" (run_cases.py:72-73) [CODE].

**The arithmetic.** Assume a case passes a single run with probability *p*, independently across runs. It then counts with probability *p³*, and the expected score is the mean of *p³* over the 60 cases (computed locally):

| Per-run pass rate *p* | P(case counts) = *p³* | Expected cases out of 60 if every case had this *p* |
|---|---|---|
| 0.80 | 0.512 | 30.7 |
| 0.85 | 0.614 | 36.8 |
| 0.90 | 0.729 | 43.7 |
| 0.93 | 0.804 | 48.3 |
| 0.95 | 0.857 | 51.4 |
| 0.97 | 0.913 | 54.8 |
| 0.98 | 0.941 | 56.5 |
| 0.99 | 0.970 | 58.2 |
| 1.00 | 1.000 | 60.0 |

**Per-run rate needed for a target chance of 3/3**, from *p* = target^(1/3):

| Target chance the case counts | Per-run *p* needed |
|---|---|
| 0.50 | 0.794 |
| 0.80 | 0.928 |
| 0.90 | 0.966 |
| 0.95 | 0.983 |
| 0.99 | 0.997 |

What this means:
- The final runs 60 × 3 = **180 conversations**. Each case is worth 1/60 ≈ 1.67 points of the score.
- A flaw that hits even 1 conversation in 20 (p = 0.95) costs about 14% of the cases.
- **Variance is the enemy, not the average.** README's advice: "Treat one green run as a hint, not as proof." (README:67) [DOC]. The skill says: "A customer that passes once can fail the next time. Prefer rules in routes and code over rules in prompts." (SKILL.md:30) [DOC]
- **Sources of variance named in the docs** [DOC]:
  - the customer and the agent are LLMs, so runs differ (page:45)
  - a busy model slows turns, and customers hang up as `customer-ended-call` (README:100; page:45)
  - [INFERRED] the judge is an LLM too, so a borderline transcript can flip
- **Slow runs.** The practice harness has `--rerun-if-slow K`, commented "organisers: a run made while the model was slow is thrown away and repeated" (run_cases.py:66) [CODE].
  - The kit's rule: a run is thrown away when the upper median of the per-call slowest agent turn is above 10 s, after a 5-minute wait (run_cases.py:68-69, :116) [CODE].
  - Whether the organisers use the same threshold, wait and number of retries is [UNCERTAIN] (notes/harness.md U7).
  - The agent's own latency counts toward that median: every tool call and engine event between a customer message and the agent's next spoken reply (run_cases.py:108-113) [CODE].
- **Measuring *p* in practice is slow.**
  - A `--reps 3` run of the 10 Brief A cases takes 3 × (3–11 min) ≈ 9–33 min (README:88) [DOC + arithmetic].
  - One simulation runs at a time per workspace (README:88; page:28) [DOC].
  - [INFERRED, statistics] With zero failures in *n* runs, the 95% lower bound on *p* is about 1 − 3/*n* (the "rule of three"). So 39 straight passing conversations (13 cases × 3) only shows *p* ≳ 0.92 overall.

---

## 8. Tie-breaks

Order, as stated: "Equal scores are ranked by the total promised amount on the customers that passed, then by shorter build time, then by earlier submission." (README:90). Page: "Tie-breaks: total promised amount recorded on passed cases; shorter total build time from traces; earlier submission." (page:27). The overview also says "Build time is the second tie-break." (page:14) [DOC]

| Rank | Tie-break | Details and implications |
|---|---|---|
| 1 | **Total promised amount recorded on passed cases** | On a passed case the ledger promises must equal the expected promises exactly (check 2). So this total depends only on *which* cases passed [INFERRED]. It cannot be raised by pushing amounts, since a wrong amount fails the case [INFERRED]. Teams that pass the same cases tie on it [INFERRED]. Whether it is summed once per case or over 3 reps is [UNCERTAIN]; the order is the same either way [INFERRED]. |
| 2 | **Shorter total build time, from traces** | "Trace: start/end time (build time tie-break)" (page:32) [DOC]. "Total" suggests the two briefs' build times added together (page:27) [INFERRED]. It is decisive between entries that pass the same case set, for example two perfect 60/60 entries [INFERRED]. The trace must therefore state start and end times explicitly [DOC]. |
| 3 | **Earlier submission** | The form time [INFERRED]. Submit as soon as the entry is final [INFERRED]. |

---

## 9. Submission

### 9.1 The Sunday sequence (page:31; README:74-75) [DOC]

1. **17:00 UTC.** "two hidden briefs sent to every team, each with its own tool API file."
2. **Run the builder on each.** "keep everything it prints; may run more than once; submit one agent per brief with the trace of the run that made it."
3. **Do not edit.** "Do not edit an agent after the run."
4. **Export each workflow.** "Export each with freya.export_workflow, commit." README: "You export each phone agent to a file with `freya.export_workflow(workflow_id, "<brief>.workflow.json")` and submit those files."
5. **Send the form before 20:00 UTC** "to the address in the kit email". The address is not in the kit files: [UNCERTAIN].

### 9.2 The run command and capturing the trace

- The form's `run_command` value is `"python3 builder/build.py {brief_path} {tool_api_path}"` (page:31) [DOC].
- The page's example: `python3 builder/build.py briefs/hidden-1.md briefs/hidden-1.openapi.json 2>&1 | tee traces/hidden-1.log` (page:31) [DOC].
- What this implies [INFERRED]:
  - The repo needs `builder/build.py` taking **two positional arguments**: the brief path and the tool API path.
  - The trace is whatever the builder prints to stdout and stderr, captured with `tee`.
  - Hidden file names follow `briefs/hidden-N.md` and `briefs/hidden-N.openapi.json`.
  - Whether a different `run_command` is accepted is [UNCERTAIN]. Matching the example exactly is the safe choice.
- Rule: "Builder must work alone: one command, a brief as input, a phone agent as output, no manual edits after it runs." (page:14) [DOC]

### 9.3 What `export_workflow` writes (freya.py:65-68) [CODE]

- It GETs `/api/v2/workflow/{id}?workspaceId=…` and writes JSON (indent 1): `{"workflow_id", "agent_id", "updated_at", "workflow"}`.
- The docstring: "Write the workflow as it is on the platform to a file. This file is part of what you submit."
- Whether the GET returns the newest saved version or the published one is [UNCERTAIN]. `save_workflow`/`update_workflow` publish the newest version after every update (freya.py:61-63), so the two are the same if every change goes through them [INFERRED].

### 9.4 The form (page:31) [DOC]

JSON with these fields:

| Field | Meaning | Status |
|---|---|---|
| `team` | team name | [DOC] |
| `repo` | repository URL | [DOC] |
| `commit` | the commit the agents came from | [DOC] |
| `run_command` | `"python3 builder/build.py {brief_path} {tool_api_path}"` | [DOC] |
| `workflows` | `{hidden-1, hidden-2}` | Whether the values are repo paths or the file contents is [UNCERTAIN] |
| `traces` | `{hidden-1, hidden-2}` | Same [UNCERTAIN] |

### 9.5 How many builder runs: a wording conflict

- "Run your builder once on each new brief" (page:12). "You run your builder once on each, with no manual step" (README:74) [DOC].
- But: "may run more than once; submit one agent per brief with the trace of the run that made it" (page:31). "You may run it more than once and submit the phone agent of one run, with that run's trace." (README:89) [DOC]
- Reading [INFERRED]: "once" means one unattended run per submitted agent. Several runs are allowed, but the submitted agent and trace must come from the same single run. The later, more specific text allows reruns (notes/harness.md U10).

---

## 10. The trace

| Required content | page:32 [DOC] | README:91 [DOC] |
|---|---|---|
| Start and end time | yes, "(build time tie-break)" | yes |
| Every model call: which model and a one-line purpose | yes | yes, "each model call it made (model and a one-line purpose)" |
| What was created on Freya | yes: "workflow id, agent id, number of steps and tools" | yes: "what it created on Freya" |
| Any test run on its own agent, with the result | yes | yes |
| Format | "Plain text fine." | "Plain text, no fixed format." |
| Secrets | "Remove API keys." | — |
| Count | "One trace per hidden brief; no traces → not ranked" (page:37) | "You submit one trace per final brief." |
| Optional | "coding-agent session logs (top three talk through their approach)" | — |

**The example builder's trace does not meet this as written** [CODE; INFERRED]:
- It writes `traces/<YYYYmmdd-HHMMSS>.jsonl`.
- The first line is `{"start", "briefs", "model"}`, followed by every SDK message (agent_builder.py:19, :34-38).
- It has no explicit end-time line; only the `ResultMessage` carries `duration_ms`.
- It has no one-line purpose per model call.
- It does not state the number of steps and tools.
- See notes/harness.md U14.

---

## 11. Verification by the organisers

- **Everyone's agents** are tested from the exported files, in the organisers' workspace: "We load them into our own workspace to test them, so what you export is what we score." (README:75). "they test submitted agents" (page:33) [DOC].
- **Top ten**: "clone repo at commit, run builder on the same briefs, compare with trace." (page:33). Overview: "Builders of top entries are rerun to verify." (page:14). FAQ: "rebuild only for top entries to check provenance" (page:44) [DOC].
- **Every trace**: "A reviewer agent reads every trace against the code and the agent." (page:33) [DOC]
- **Removal**: "If their run scores clearly below yours, entry removed." (page:33). How large a gap counts as "clearly" is [UNCERTAIN].
- **No exact match required**: "no identical workflow expected; they look at structure and score" (page:44) [DOC].
- **The commit is checked for leakage**: "nothing from a hidden brief may be written into it (reviewer checks the commit)" (page:37) [DOC].

**What this implies** [INFERRED]:
- The builder must run from a **fresh clone** with only documented environment variables.
  - The Freya key would presumably be the organisers' own. Who supplies the builder's model key, and in which workspace, is [UNCERTAIN].
  - `freya.save_workflow` keeps slot state in `.freya-agents.json` in the **current directory** (freya.py:36-47). If that file is committed, a rerun in another workspace would try to update a workflow id it cannot see. Do not rely on that file existing, or not existing.
- The builder's *own* score variance becomes a verification risk. A builder that sometimes makes a weak agent can get an entry removed when the organisers' rerun lands low.
- The trace must agree with the code and the exported agent: the same workflow id, the same steps and tools count, and real test results.

---

## 12. Limits

| Limit | Value | Source |
|---|---|---|
| Builder run time | **30 min per brief, including self-tests**. "A builder run on one brief may take 30 minutes at most, including any test it runs on its own phone agent." | page:34; README:89 [DOC] |
| Workflows per workspace | **200**. "update in place". Over the limit you get `Workspace plan limit reached`. | page:34, :43; README:87, :97 [DOC] |
| Workspaces and keys | "a team has one workspace" (page:28). "One Freya key per team." (page:37) | [DOC] |
| Practice simulations | "1 at a time per workspace". "A second `run_cases.py` started meanwhile waits for the first." | page:28, :34; README:88 [DOC] |
| Practice run duration | "A ten-case run takes 3–11 min." | page:28; README:88 [DOC] |
| Agent model | "the Freya model set in freya.py, same for every team, do not change" | page:34; README:85 [DOC] |
| Builder model | "builder may use any model (you pay)" | page:34 [DOC] |
| Agent's outbound calls | Only the kit's tool API. "a call to any other service fails the case" | page:37; README:86 [DOC] |
| Practice call length | 420 s per call | freya.py:87 [CODE] |
| Practice concurrency | 5 calls | freya.py:87 [CODE] |
| Team size | Solo or a team of two | page:37 [DOC] |
| Sunday window | 3 h (17:00–20:00 UTC) for two builder runs, any fixes, exports, commit and form | page:13 [DOC] |

**The Sunday time budget** [INFERRED]:
- Two runs at ≤ 30 min each is ≤ 60 min if they run one after the other.
- The simulation slot is shared per workspace. Chat turns have "no queue" (api.md:242), but "Do not probe or load-test the platform" (page:37) argues for modest chat volume.

---

## 13. Rules (complete)

### 13.1 From the page (page:37) [DOC]

1. "Solo or team of two."
2. "Submit a builder; a hand-built agent alone is invalid."
3. "Hidden-brief agents must come out of the submitted commit with no manual edits."
4. "One trace per hidden brief; no traces → not ranked."
5. "Agent may call only the kit's tool API; a call to any other service fails the case."
6. "**Do not probe or load-test the platform. One Freya key per team.**"
7. "May fix builder after hidden briefs open; nothing from a hidden brief may be written into it (reviewer checks the commit)."
8. "All data synthetic."

Also from the page:
- "Pre-event code allowed." (page:44)
- "Builder must work alone: one command, a brief as input, a phone agent as output, no manual edits after it runs." (page:14)
- "Do not edit an agent after the run." (page:31)

### 13.2 From the README (README:84-92) [DOC]

1. "Your builder takes brief files as input and creates the phone agent with no manual step. Do not edit a phone agent by hand after it is created."
2. "The phone agent runs on the model set in `freya.py` (`AGENT_LLM`). Do not change it. Your builder may use any model or coding agent."
3. "The phone agent may call only the bank's tool API. Code steps and hooks inside the workflow are allowed and expected."
4. "Use `freya.save_workflow(...)` or update your workflow in place. A workspace holds 200 workflows. A builder that creates a new one on every run fills it up and leaves you with a list nobody can read."
5. "One simulation runs at a time per workspace. A ten-customer run takes 3 to 11 minutes. A second `run_cases.py` started meanwhile waits for the first."
6. "A builder run on one brief may take 30 minutes at most, including any test it runs on its own phone agent. You may run it more than once and submit the phone agent of one run, with that run's trace."
7. "Equal scores are ranked by the total promised amount on the customers that passed, then by shorter build time, then by earlier submission."
8. "Your builder must leave a trace of each run: start and end time, each model call it made (model and a one-line purpose), what it created on Freya, and any test it ran on its own agent. Plain text, no fixed format. You submit one trace per final brief."
9. "All data here is synthetic. Do not bring real customer data."

### 13.3 After the hidden briefs open: allowed and forbidden

| Allowed | Forbidden |
|---|---|
| "fix a bug in your builder" (README:73; page:14, :37) [DOC] | "write anything from a final brief into it: no rule, no value, no name" (README:73) [DOC] |
| "Fixing a crash on a table your parser did not expect" (README:73; page:14) [DOC] | "Adding the new brief's holiday dates or outcome names to your code or prompts" (README:73; page:14) [DOC] |
| Running the builder more than once and submitting one run's agent with that run's trace (README:89; page:31) [DOC] | Editing the agent after the run, in any way (page:31, :37; README:84) [DOC] |
| Exporting and committing (page:31) [DOC] | "tuning it to the new briefs" (page:13) [DOC] |

The reviewer checks the commit (page:37) [DOC]. [INFERRED] Every post-17:00 commit must be explainable as a generic bug fix.

---

## 14. FAQ (complete, page:41-45) [DOC]

| Question | Answer as captured |
|---|---|
| Login mail missing | "Login mail may be in spam (Outlook/Hotmail/university filtered)." |
| Where is the kit | "Kit on Data tab." |
| API key | "sign in with the mailed account → API keys → create → env.sh FREYA_API_KEY." |
| Teammate | "one workspace; owner invites from Workspace settings." |
| Dashboard test call never passes identity | "the workspace has one practice customer for dashboard test calls: DOB 14 March 1988, last four 4471. After a call closes, that customer starts fresh after 5 min idle. run_cases.py opens a fresh customer per case." (These are PUB-01's values, test-set:3-28 [CODE].) |
| Workflow limit | "200 workflows per workspace." |
| Practice customers for my own brief | "Builder cannot open its own practice customers: practice bank serves PUB-01..13 only; to check an agent on a brief with no cases, talk to it with POST /api/v2/chat/message (docs/api.md). Hidden briefs have no practice cases, only the tool API file." |
| Raw-material brief format | "The raw-material brief is ONE Markdown file with its own tool API file next to it." |
| Pre-event code | "Pre-event code allowed." |
| What is scored and rebuilt | "Score from the agents you export and submit; rebuild only for top entries to check provenance; no identical workflow expected; they look at structure and score." |
| "Score dropped with no change" | "customers and agent are LLMs, runs differ; a run suffers when the model is busy (run_cases prints slowest agent turn per call). Run again; use --reps 3." |

The FAQ says `run_cases` "prints slowest agent turn per call". The code prints only the **median** and the **worst** over all calls. The per-call value is saved only in the `--out` rows (run_cases.py:114, :117) [CODE]. The source code wins (notes/harness.md U15).

---

## 15. Exact strings that matter for scoring

| String | Where | Meaning |
|---|---|---|
| `identity not verified` | ledger `calls[].result.error`; score.py:32 | Any `get_account` or `create_promise` that gets this fails the case (check 7) [CODE] |
| `the call was not closed with close_call` | score.py:29 | Last ledger call ≠ `close_call` [CODE] |
| `identity or account tools used although the customer was not on the line` | score.py:33 | Not-reached case touched `verify_identity` or `get_account` [CODE] |
| `conversation: no verdict` | run_cases.py:96 | The judge gave no verdict, which counts as a fail [CODE] |
| `customer-ended-call` | README:100; run_cases.py:116 | The customer hung up, usually after the agent was silent too long [DOC][CODE] |
| `WARNING: the phone agent was slow in this run. If the same agent is fast in another run, the model was busy and this score is too low.` | run_cases.py:118 | Upper-median slowest turn > 10 s [CODE] |
| `-- run discarded: median slowest turn {med} s. Waiting 5 minutes, then repeating it.` | run_cases.py:69 | `--rerun-if-slow` threw a run away [CODE] |
| `another simulation is running in this workspace, waiting 30 s` | freya.py:99 | The single simulation slot is busy [CODE] |
| `Workspace plan limit reached` | README:97 | More than 200 workflows [DOC] |
| `error code: 1010` | README:96 | No browser-like `User-Agent`. `freya.py` sends `Mozilla/5.0 (build-the-builder)` (freya.py:10) [DOC][CODE] |
| `unknown product_id` | README:102 | The model invented a product id. Ids come from `get_account` (`p1`, `p2`, …) [DOC] |
| `the call is already closed` | probe:159 | Every tool after `close_call` [PROBED-earlier] |
| `unknown outcome` | probe:159 | `close_call` with an outcome outside the enum [PROBED-earlier] |
| `Yes, I confirm.` / `Thank you, goodbye.` | run_cases.py:23-24 | The simulated customer's fixed confirm and goodbye phrases [CODE] |
| `{n} / {total} passed (bank records and conversation checks)…` | run_cases.py:77 | Final line of a practice run; adds `, a customer counts with {need} of {reps} runs` when reps > 1 [CODE] |

---

## 16. Prizes (page:38) [DOC]

| Place | Prize |
|---|---|
| 1st | YC interview |
| 2nd | AirPods |
| Top three | final interview with Freya |
| Pool | $3,000 Freya credits. How the pool is split is [UNCERTAIN]. |

The page also says the top three "talk through their approach" and may submit coding-agent session logs (page:32) [DOC].

---

## 17. The practice scorer: what you can measure before Sunday

This section covers only what bears on scoring. The full harness detail is in notes/harness.md §2.3.

- **Usage:** `python3 tools/run_cases.py <agent_id> --brief A` "prints PASS/FAIL, tool chain (verify = verify_identity, promise = create_promise), failure reasons, '5 / 10 passed'" (page:28) [DOC].
- **The id to pass is the agent id**, not the workflow id (README:23-24; run_cases.py:88) [DOC][CODE].
- `--reps 3` "counts a customer only when every run passes, as the final does" (page:28) [DOC].

| Flag (run_cases.py:50) [CODE] | Effect |
|---|---|
| `--brief A` or `--brief B` | Exact match. `A` selects PUB-01..10, `B` selects PUB-11..13. No flag runs all 13. Lowercase selects nothing. |
| `--cases <file>` | Another case file. Only `id` is sent to the bank, so the ids must be PUB ids. |
| `--only PUB-01,PUB-04` | Comma list, no whitespace trimming |
| `--reps N` | N sequential simulations. A case passes only if it passes all N. |
| `--style <s>` | One of `asks_back`, `corrects`, `in_words`, `pieces`, `talkative`. Applies to all cases and overrides per-case styles. |
| `--out <file>` | JSON with every row, including `call_id`, `customer_id`, `tools`, `failed` and `slowest_turn_s` |
| `--rerun-if-slow K` | Discard and repeat a slow run up to K times (§7) |

**Printed line per case** (run_cases.py:99-100) [CODE]:

```
PASS PUB-01 easy   Happy path     | verify > verify > get_account > promise > close_call
FAIL PUB-10 hard   Tool failure   | (no tool calls)
       - conversation: no verdict
```

- The tool chain comes from the **bank ledger**, so it includes rejected calls [CODE; INFERRED].
- Every invocation appends one line to `results/log.jsonl` (run_cases.py:78-79) [CODE].

---

## 18. Implications for the design [INFERRED unless marked]

1. **The unit of success is a case passing 3 of 3, across 60 unseen customers in two unseen briefs.** Optimise for per-run reliability ≥ ~0.97 on every case type, not for average pass rate (§7).
2. **The ledger is checked exactly.**
   - The outcome and reason pair must match, and the reason must be null where expected.
   - Promises must match as a multiset, with amounts to the cent and dates as `YYYY-MM-DD`.
   - Notes must match on `(product_id, reason)` with no extras.
   - Callbacks must match as `(date, "HH:MM")`; transfers by queue only.
   - This favours computing tool arguments in code from tool results and `now`, not leaving them to the model (score.py:19-27 [CODE]; page:15 "calculations such as business days can run as code" [DOC]).
3. **Three ledger-level policy traps fail a case even when the conversation sounds fine:**
   - the last call is not `close_call`
   - any `get_account` or `create_promise` before verification, even one that is later retried successfully
   - any `verify_identity` or `get_account` in a not-reached case

   (score.py:28-33) [CODE]
4. **The judge's checks are hidden in the final.** The only way to satisfy them is to follow the brief literally: wording, counts ("once", "exactly once") and order ("before get_account"). The 13 public checks show the style (§5.5).
5. **Everything brief-specific must be read from the brief and its tool API file at build time:**
   - identity questions, limits, deadlines, the calendar and holidays
   - the outcome table and reason names
   - tool fields and enums
   - the server URL

   (README:71-73, :80) [DOC]. The raw-material brief needs the builder to reconcile a mail, a policy extract, *a memo that changes it* and a code list (README:71) [DOC].
6. **Dates must come from the `now` variable**, because the final spans several calendar days (page:14, :27) [DOC].
7. **Customers' speech varies.** Numbers come in pieces, values get corrected, decoys are mentioned, questions come back, and amounts and dates are said in words (README:78) [DOC]. Identity and amount capture must handle all five.
8. **Latency is part of reliability.** Long silences lead to hang-ups, and slow medians can get runs discarded (README:100; run_cases.py:66-69, :108-118) [DOC][CODE].
9. **Self-testing on Sunday is limited to chat turns**, because hidden briefs have no practice cases (page:43) [DOC]. Most of the builder's quality must therefore be designed and validated on the public briefs before 17:00 UTC, without overfitting to them (page:14) [DOC].
10. **The builder is itself under test.**
    - It runs from a fresh clone (top ten).
    - Its trace is read by a reviewer agent against the code and the exported agent.
    - Its build time is the second tie-break.
    - A rerun that scores clearly lower gets the entry removed (page:27, :32-33) [DOC].
11. **Export is the scored artifact.** Export the final agent with `freya.export_workflow` after the last save. That save must publish (`save_workflow` does; a plain `PUT` does not) (README:75, :98; api.md:103-115) [DOC].
12. **`freya.update_workflow` repairs `agent_config`, but only on an update.** The platform fills in a default `agent_config`; if its model is not the event model, "a chat turn or a real call cannot start" (freya.py:55-60). `save_workflow` calls `update_workflow` only when the slot already exists. A builder whose run *creates* the workflow (for example, a fresh clone) may not be able to chat-test it until a second save [INFERRED from freya.py:43-46].

---

## 19. Open questions and contradictions

| # | Item | Status |
|---|---|---|
| Q1 | Who supplies keys and which workspace the organisers' builder rerun uses | [UNCERTAIN] |
| Q2 | What counts as "scores clearly below yours" | [UNCERTAIN] (page:33) |
| Q3 | Official judge model and prompt format; whether the judge sees tool events | [UNCERTAIN] (notes/harness.md U1, U9) |
| Q4 | Final simulation settings: concurrency, max call length, slow-run discard policy | [UNCERTAIN] (notes/harness.md U7) |
| Q5 | Whether tie-break 1 sums promises once per case or over 3 reps | [UNCERTAIN]; the ranking order is the same either way [INFERRED] |
| Q6 | Whether the form's `workflows` and `traces` values are paths or contents, and the submission address | [UNCERTAIN] (page:31) |
| Q7 | Results date | [UNCERTAIN] (page:13) |
| Q8 | "Run once" (page:12; README:74) against "may run more than once" (page:31; README:89) | Conflict. The more specific text allows reruns, with the submitted agent and trace from the same run (§9.5) |
| Q9 | Whether a hidden brief can depend on another brief (as B builds on A) | [UNCERTAIN]. The run command takes one `{brief_path}`, so each hidden brief is probably self-contained [INFERRED] |
| Q10 | Whether rejected post-`close_call` calls appear in the ledger `calls` (which would fail check 6) | [UNCERTAIN]. Rejected pre-verification calls *are* logged (probe:154) [PROBED-earlier], so likely yes [INFERRED] |
| Q11 | HTTP form of an injected tool failure (500 vs 200 `ok:false`) | [UNCERTAIN] (notes/harness.md U4) |
| Q12 | Whether `export_workflow`'s GET returns the newest saved or the published version | [UNCERTAIN]. The two are the same if every change goes through `save_workflow` |
| Q13 | Whether per-case speech styles are mixed in the final | [UNCERTAIN] (notes/harness.md U8) |

---

## 20. Notes compared with the sources

I checked `knowledge/notes/harness.md` against `hackathon-page.md`, `README.md`, `score.py` and the code it cites. **No note claim contradicted a primary source.** I made these refinements:

1. **Harness §2.4 check 6** ("[UNCERTAIN whether post-close calls are recorded]").
   - The tool API states `close_call` is "Always the last tool call. Nothing is accepted after it." (openapi.json:411) [DOC]. The note does not cite this.
   - Rejected calls are logged in the ledger, as the pre-verification `get_account` shows (probe:154) [PROBED-earlier]. So a post-close call most likely fails check 6 [INFERRED].
   - It is still unconfirmed.
2. **Harness U10** cites only README:74 for "run once". The page says it too (page:12), against page:31.
3. **Harness §2.9** quotes the verification as "Top ten". The page also says "Builders of top entries are rerun" (page:14) and "rebuild only for top entries" (page:44). And it says the reviewer agent reads **every** trace (page:33), not only the top ten's.
4. **The page capture is condensed**, for example the PUB table at page:21. Page quotes are capture quotes (see the caveat at the top).

---

## Traps to remember

1. **3 of 3 or nothing.** A case counts only if all three runs pass, so p = 0.9 per run gives only 0.73 (page:27; README:76) [DOC][INFERRED].
2. **No partial credit**, either across checks or across products in a case (page:24; README:65) [DOC].
3. **The last ledger call must be `close_call`.** That holds in every case: third party, failed identity, hardship, transfer (score.py:29) [CODE].
4. **One early `get_account` or `create_promise` fails the case** if it returns `identity not verified`, even if a retry later succeeds (score.py:31-32) [CODE].
5. **In a not-reached case, never call `verify_identity` or `get_account`**, whatever the outcome is named (`not_reached`, `no_contact`, `unreached`) (score.py:33) [CODE].
6. **`reason` must match exactly**, including being null for `promise` and `paid` in practice. Do not send a reason where none is expected (score.py:19-20; test-set expected blocks) [CODE].
7. **Extra notes, callbacks, transfers or promises fail the case.** The ledger is compared as multisets. PUB-05 expects no note (score.py:22-27; test-set:203) [CODE].
8. **Amounts compare to the cent and dates as exact strings.** Callback times must be `HH:MM`, so `11:00:00` does not match (score.py:21, :25) [CODE].
9. **Note text and transfer extras are ignored**, but `(product_id, reason)` and `queue` must be exact (score.py:23, :27) [CODE].
10. **The bank does not enforce the brief.** A holiday date, an amount below the minimum or a past-deadline promise will be recorded, and the case fails (page:25; openapi.json:6) [DOC].
11. **The judge's checks are hidden on Sunday.** Follow the brief's wording, counts and order literally (page:43) [DOC][INFERRED].
12. **The simulated customer confirms whatever you agreed.** It does not know the real amounts or dates, so read-back errors are not caught in conversation; the ledger catches them (run_cases.py:23, :41-44) [CODE].
13. **Honesty:** never say "recorded" before a tool call has succeeded (README:61; test-set:431) [DOC][CODE].
14. **A correct refusal passes and a pushy agent fails.** A dispute means a recorded dispute and no promise (page:26) [DOC].
15. **Dates come from `now`, not 14 Oct.** The final spans several calendar days (page:14, :27) [DOC].
16. **Customers talk like people:** pieces, corrections, a decoy "30th", questions back, words for numbers (README:78; run_cases.py:28-32) [DOC][CODE].
17. **Slowness costs cases.** Silences lead to hang-ups (`customer-ended-call`), and a slow median can get runs discarded (README:100; run_cases.py:66-69) [DOC][CODE].
18. **Nothing from a hidden brief goes into the builder** after 17:00: no rule, value or name. Holiday dates and outcome names are the stated examples, and the reviewer checks the commit (README:73; page:37) [DOC].
19. **No manual edits to the agent, ever**, after the run. The exported workflow must come out of the submitted commit (page:31, :37; README:84) [DOC].
20. **No trace means not ranked.** Each trace needs start and end time, every model call with model and purpose, the workflow id, agent id, number of steps and tools, and the tests with results. Remove API keys (page:32, :37) [DOC].
21. **The example builder's trace is not compliant as is.** It has no end-time line, no per-call purpose and no steps or tools count (agent_builder.py:34-38) [CODE].
22. **The run command takes two arguments**: `python3 builder/build.py {brief_path} {tool_api_path}`. The example builder and skill read `tools/openapi.json` instead (page:31; SKILL.md:12) [DOC].
23. **The example skill's self-test (`run_cases --brief A/B`) is useless on hidden briefs**, which have no practice cases. Only `chat/message` turns are possible (page:43; SKILL.md:22) [DOC][INFERRED].
24. **The 30-minute cap per brief includes self-tests.** The example skill allows up to 4 test runs at 3–11 min each, which can exceed 30 min (README:89; SKILL.md:23) [DOC][INFERRED].
25. **200 workflows per workspace.** Update in place, or you hit `Workspace plan limit reached` (README:87, :97) [DOC].
26. **An update must be published** or you test (and export) the old agent. `save_workflow` publishes; a plain `PUT` does not (README:98; api.md:103) [DOC].
27. **Export is what is scored.** Export after the final save, from the same run whose trace you submit (README:75; page:31) [DOC].
28. **Top-ten rerun from a fresh clone.** It must work without local state such as `.freya-agents.json`. A rerun that scores clearly lower removes the entry (page:33; freya.py:36-47) [DOC][INFERRED].
29. **One workspace and one Freya key per team. Do not probe or load-test the platform.** Using more workspaces or keys is against the rules (page:28, :37) [DOC].
30. **One simulation at a time per workspace.** A ten-case run takes 3–11 min, and a `--reps 3` run takes 9–33 min. Budget practice time (README:88) [DOC][INFERRED].
31. **The agent may call only the kit's tool API.** Any other service fails the case. Take the server URL from the hidden tool API file, because tool fields and enums can change (page:37; README:72) [DOC].
32. **Do not change the agent model** (`AGENT_LLM`, `experimental-5`) (README:85; freya.py:84) [DOC][CODE].
33. **Tie-breaks favour passing the high-promise cases, then a fast build, then an early form** (README:90; page:27) [DOC]. At equal case sets, build time decides [INFERRED].
34. **Pass the agent id to `run_cases.py`, not the workflow id**, and use uppercase `--brief A` (run_cases.py:50-52) [CODE].
35. **`run_cases.py` can hang.** A simulation stuck at "running" polls forever. The README's fix: try one chat turn and leave `agent_config` out (freya.py:101-104; README:103) [CODE][DOC].
36. **"Run once" and "may run more than once" are both written.** Submit the agent and trace of one and the same run (README:74, :89; page:12, :31) [DOC].
