# 08 · Open questions, contradictions and known errors

## In short

1. Ten platform behaviours that the kit leaves open would change the shape of the phone agent. The four that matter most are listed here. How `close_call` gets its `outcome` and `reason`: an unresolved value is "dropped" (WF:202, TC:115) but also "filled by one model call" (TC:561). What a failed tool call looks like: HTTP 500 (OA:84) or HTTP 200 with `ok:false` [PROBED-earlier]. Who speaks after a tool result has moved the call to another step (TC:291). Whether a step's routes run in list order or with deterministic conditions first (WF:406 against WF:407).
2. Two normal practice runs of the example agent with `--out` (Brief A, then Brief B) settle most of these. So does one small lab workflow taken through a few chat turns, reading the event log and the bank ledger (§11). None of it needs probing.
3. How to self-test an agent for a hidden brief is itself an open question. Do chat turns reach the bank? Does chat skip a first code step (API:252)? Which customer can the agent be tested on, given that "Hidden briefs have no practice cases" (HP:43)?
4. 45 questions about how to read the briefs (§4) cannot be settled by experiment. Local runs score against our own expected results and our own checks. Each one has a careful-reader default.
5. The four earlier summaries (`research/read-*.md`) contain 86 errors, mostly overstatements (§9). One knowledge note also has five wrong line citations (§10).
6. Some questions are cheap to make irrelevant. Examples: set every variable a tool bakes, route on string flags that our own code writes, put no `{{` in code, and take every enum from the tool API file. Where that is possible, the design should do it instead of depending on the answer.

---

## 0. How to read this chapter

### 0.1 Sources and citation keys

All kit paths are under `kit/`. `A:24` means `briefs/brief-a.md` line 24.

| Key | File | Status |
|---|---|---|
| A, B | `briefs/brief-a.md`, `briefs/brief-b.md` | source of truth |
| OA | `tools/openapi.json` | source of truth |
| PTS | `public-test-set.json` | source of truth |
| WF, TC, API | `docs/workflow-format.md`, `docs/tools-and-code.md`, `docs/api.md` | source of truth |
| RM | `README.md` | source of truth |
| FP, RC, SC | `freya.py`, `tools/run_cases.py`, `tools/score.py` | source of truth |
| BA, AB, SK | `examples/base-agent.json`, `examples/agent_builder.py`, `.claude/skills/build-phone-agent/SKILL.md` | source of truth (BA is an example agent, "a place to start, not a good score", HP:19) |
| HP | `research/hackathon-page.md` (official page text), cited by line, e.g. HP:43 (§FAQ) | source of truth |
| RAT, RRC, RTC, RWF | `research/read-api-and-testing.md`, `read-rules-and-cases.md`, `read-tools-and-code.md`, `read-workflow-format.md` | earlier agent summaries; may contain errors. Only RAT's live-probe facts are kept, as [PROBED-earlier] |
| N:… | knowledge notes in `knowledge/notes/`: N:api, N:ba (base-agent), N:briefs, N:c0102, N:c0308, N:c0407, N:c0509, N:c0610, N:c11 (case notes), N:harness, N:openapi, N:tc1, N:tc2, N:wf1, N:wf2 | written for this knowledge base and re-checked here; the source wins when they disagree |

The task text calls `research/read-*.md` "primary sources". The ground rules say they are earlier summaries that may be wrong. So they were re-checked line by line against the kit and the page. Every disagreement is listed in §9, and the kit or page wins.

### 0.2 Labels

| Label | Meaning |
|---|---|
| [DOC] | Stated in the kit docs, briefs, README, tool API or hackathon page |
| [CODE] | Read from kit code or kit JSON |
| [PROBED-earlier] | From the few live calls to the **mock bank** an earlier agent made on 2026-10-10 (RAT:5 says they used PUB-01 and PUB-11 only). No Freya route was ever called (RAT:7). Not repeated |
| [INFERRED] | Reasoning in this chapter or in a note |
| [UNCERTAIN] | Not settled; the text says exactly what is unknown |

### 0.3 What "an experiment" means here: the toolkit and its limits

Every experiment below is normal kit usage once a Freya key exists. Each one uses our own workflow, our own practice sessions and the documented routes. No probing and no load. The rules say: "Do not probe or load-test the platform. One Freya key per team." (HP:37).

| Tool | What it is | Source |
|---|---|---|
| **E-RUN** | `python3 tools/run_cases.py <agent_id> --brief A\|B [--only IDs] [--style S] [--reps N] --out results/<name>.json`. It prints PASS/FAIL, the ledger's tool chain and the failure reasons. `--out` keeps every call id and customer id | RC:3, RC:50, RC:80-82, RC:99-100; RM:99 |
| **E-CASES** | A custom `--cases file.json` that reuses a PUB id and changes `script`, `checks` and `expected` | RC:50, RC:52 |
| **E-EVENTS** | `freya.get_call(call_id)["messages"]`. System events: `node_enter`, `function_call_start` (for an `api_call` this carries the full `url`/`method`/`headers`/`body`), `function_call_complete`, `route_evaluated` (with `branches` and `variable_table`), and `error`. A trial call also showed a `workflowSnapshot` with `variableTable` | FP:79-81; API:306-336 |
| **E-LEDGER** | `score.http("/v1/practice/ledger/" + customer_id)`, the same GET that run_cases makes. It returns `calls[{n, tool, args, status, result}]`, `failures{tool:n}`, `promises`, `notes`, `callbacks`, `transfers`, `outcome`, `reason`, `wrong` and `hinted`. For pass/fail only: `python3 tools/score.py <case> <customer_id>` | SC:10-15, SC:36-39; RC:93; [PROBED-earlier] RAT:133-141 |
| **E-CHAT** | `freya.api("POST", "/api/v2/chat/message", {"workflowId": …, "message": …, "customerVariables": …})` runs one turn against the **published** workflow. `result` has `response` and `callId`. End with `POST /api/v2/chat/end` and `{"callId"}`. Customer variables come from a fresh practice session: `score.http("/v1/practice/sessions", {"case": "PUB-xx"})["variables"]`, the same call RC:86 makes | API:240-252; HP:43 |
| **E-SAVE** | `freya.validate_workflow` (dry run), `freya.save_workflow`, `freya.export_workflow`, and the versions GET inside `update_workflow` | FP:36-68; API:71-127 |
| **E-LAB** | One experiment workflow in one fixed slot (for example `lab`), updated in place. Several test nodes are bundled into it | RM:87; FP:36-47 |

**Limits that shape every experiment:**
- One simulation at a time per workspace, and one workspace per team. A ten-case run takes 3 to 11 minutes (RM:88; HP:28) [DOC].
- The practice bank serves PUB-01..13 only (HP:43) [DOC]. An unknown case returns 404 "unknown practice case" [PROBED-earlier RAT:129]. A custom cases file therefore keeps that PUB id's identity, products and faults.
- `run_cases.py` keys everything by case id, so one run holds one variant per PUB id (RC:53, RC:62) [CODE].
- Practice sessions are single use. After `close_call` every tool returns "the call is already closed" [PROBED-earlier RAT:159]. run_cases opens new sessions on every run (RC:86) [CODE].
- Local runs check the ledger against **our** `expected` and the judge reads **our** `checks` (RC:47, RC:94-96) [CODE]. So a run shows mechanics and agent behaviour. It cannot show what the organisers intend.
- Every new persona text creates a Freya persona that is never deleted (RC:54-61) [CODE]. The persona limit is unknown (Q-23).
- The builder may take at most 30 minutes per brief, self-tests included (HP:34; RM:89) [DOC].

### 0.4 How the questions are ranked

| Tier | Meaning | IDs |
|---|---|---|
| 1 | Decides the architecture: where state lives, how steps connect, how the agent closes, how the builder tests | Q-01 … Q-10 |
| 2 | Decides how one mechanism is built safely | Q-11 … Q-23 |
| 3 | Decides wording or a branch policy. These are brief interpretations that no kit experiment can settle | I-01 … I-45 |
| 4 | Low impact, or avoided by design | T-01 … T-22 |

Every question lists its **source items**, the IDs in the notes where it was first raised, so nothing is lost in deduplication.

---

## 1. Master ranking

| Rank | ID | Question (short) | Current best guess | Cost to settle |
|---|---|---|---|---|
| 1 | Q-01 | How `close_call` gets `outcome`/`reason`, and whether it always fires | Unresolved lifecycle values are model-filled [INFERRED]. Never rely on it | Part of the first normal run |
| 2 | Q-02 | What a failed tool call looks like (500 or `ok:false`) and what the engine does with it | PUB-10's fault is HTTP 500 [INFERRED]. Treat anything except an explicit `ok` true as failure | One `--only PUB-10` run |
| 3 | Q-03 | Who speaks after a tool result moves the call, and whether required sentences get said | The old step does not speak again. The target step's entry line speaks [INFERRED] | First normal run, plus one chat |
| 4 | Q-04 | Route order: list order or deterministic first; self-loops against intents and global nodes | [UNCERTAIN]. Avoid mixing intents with a trailing `always` | Three short chats |
| 5 | Q-05 | Whether and how a hidden-brief agent can be self-tested (chat fidelity, which customer) | Chat runs tools but may skip a first code step [INFERRED] | One chat session |
| 6 | Q-06 | Variable values: boolean spelling, stale keys, empty strings, automatic key names | Route only on string flags our own code writes | Lab chat |
| 7 | Q-07 | Whether code-computed values can be baked into tool arguments (timing, types) | Yes if set before the step is entered [DOC]. Types unknown | Lab chat |
| 8 | Q-08 | Save, publish and `agent_config`: what the platform stores and runs | Create probably publishes. Patch the model once after create | Seconds, no simulation |
| 9 | Q-09 | What the hidden briefs and cases look like | Different identity fields and outcome table. Same tool names | Not settleable |
| 10 | Q-10 | What the judge sees and how strictly it judges | Satisfy every rule and say outcomes aloud | Read the first run's reasons |
| 11 | Q-11 | Mock bank contract details (identity limit, hint, malformed phone, reason on promise/paid, calls after close) | Send canonical values. Omit `reason` for promise/paid | Normal runs |
| 12 | Q-12 | Hook semantics (pre-hook `vars` vs `config`, post-hook names and types, raise, imports) | Edit `config['body']` directly. Wrap everything in try | Lab chat |
| 13 | Q-13 | Extraction semantics (date anchor, vague dates, stale values) | Do not trust `date` extraction against a synthetic `now` | Lab chat |
| 14 | Q-14 | How a call starts (who speaks first, initial code step, `start_of_call`) | Agent speaks first via `on_enter` [INFERRED] | First run events |
| 15 | Q-15 | Self-transition, re-entry and turn caps | [UNCERTAIN]. Pair every cap with a target | Lab chat |
| 16 | Q-16 | `matches_intent` inputs (which description, how much history) | Write the same text in both fields | Lab chat |
| 17 | Q-17 | `loop_condition`, `loop_prompt`, `routing_prompt` semantics | Avoid them, or settle first | Lab chat |
| 18 | Q-18 | Prompt substitution and history (date reformatting of `{{now}}`, resolution timing) | `{{now}}` may be reworded. Give the model precomputed text | Lab chat |
| 19 | Q-19 | Code sandbox (modules, value types, failure behaviour) | json/re/datetime only. Never raise | Lab chat |
| 20 | Q-20 | `suppress_tool_results` against `what_to_do_next` | Suppression probably hides the instruction. Do not combine | Lab chat |
| 21 | Q-21 | Global nodes, tool-call transitions, `passthrough_default_transition` | Always end a passthrough step with `always` | Lab chat |
| 22 | Q-22 | Ending a call (end_call node or tool, `trigger_pattern`, `endedReason`, max duration) | Use end_call nodes. `endedReason` = terminal `function.name` [DOC] | Normal runs |
| 23 | Q-23 | Harness and operations (organiser reruns, statuses, limits, persona cap, timeouts) | Keep kit defaults. Keep the median slowest turn under 10 s | Normal runs, or organisers |
| — | I-01…I-45 | Brief-interpretation questions | Careful-reader defaults in §4 | Interpretation only (some: behaviour runs) |
| — | T-01…T-22 | Low-impact unknowns | Design around them | — |

---

## 2. Tier 1: questions that decide the architecture

### Q-01. How `close_call` gets its values, and whether it always fires

**What is unknown**
- **Contradiction C-01.** For an engine-run call (`pre_actions` or a lifecycle tool), a field whose variable is unset "is dropped from the request. No error" (TC:115) [DOC]. WF:202 says the same for a value that is exactly one placeholder [DOC]. TC:561 says, for lifecycle tools: "If a `{{var}}` parameter is still unresolved, one model call fills the parameters. If everything resolves, the handler runs directly." [DOC]
- What that filling model sees, and whether it obeys the leaf's `enum`, is not stated in TC [UNCERTAIN]. The phrase "from the conversation" is BA's own tool description (BA:393), not TC.
- Whether `pre_process_code` runs on a lifecycle tool, and whether it sees the filled values [UNCERTAIN]. TC:402 honours hooks on `api_call` tools by handler. BA's `close_call` is an `api_call` lifecycle tool (BA:330-397) whose pre-hook pops `reason` when `outcome` is `promise` or `paid` (BA:395) [CODE].
- Whether an `end_of_call` tool fires when the customer hangs up (`customer-ended-call`, RM:100) or when the 420-second limit ends the call (FP:87, FP:93) [UNCERTAIN]. TC:521 says only "After the call has ended".
- Framing facts [DOC]:
  - `end_of_call` runs after call analysis and before success-criteria judging (TC:563).
  - `response_mapping` is **not** applied for `end_of_call` (TC:562), so the workflow can never see `close_call`'s own result.
  - "A malformed lifecycle tool is dropped at run time without an error" (TC:564). A dry run checks only the write-time schema (API:75, API:87). That is contradiction C-27.
  - A lifecycle tool in a node's `tools` fires for `end_of_call` "only on the node in which the call ended" (TC:560).
  - A workflow-level tool without `alwaysRunsAt` never runs (TC:559).

**Why it matters for the design**
- Every case needs `close_call` as the last ledger call (SC:28-29), with exactly the expected `(outcome, reason)` pair (SC:19-20) [CODE].
- For `promise` and `paid` the expected reason is `null` (PTS:30, PTS:337). OA:435 says `reason` is "Required for every outcome except promise and paid" [DOC].
- A wrong or missing value fails the case on every run, and the final needs 3 of 3 runs (HP:27).
- The answer decides where closing lives. There are two candidates:
  - a workflow-level `end_of_call` lifecycle tool. This is BA's choice. It fires once, after the call, so it is naturally last [INFERRED];
  - an engine-run `pre_actions` call in an `api_request` step before each `end_call` step. This is deterministic, but it never runs if the customer hangs up first [INFERRED].
- The practice bank enforces the outcome enum and checks outcome/reason consistency [PROBED-earlier RAT:159]. A guessed pair can be refused.

**Current best guess** [INFERRED]
- The model fill is real. BA leaves `{{outcome}}` and `{{reason}}` unset on every path, and `outcome` is required (OA:438-441). Yet BA passed 2 of 13 in one run (RM:34). A passing case needs a valid outcome, so the fill must have happened for BA.
- Whichever reading is true, a safe design never triggers either behaviour. Every `close_call` field resolves from a variable that code sets on every path, starting from an early default.

**Experiment that settles it** (cost: part of the very first normal run)
1. Save BA unchanged (RM:23), then run `python3 tools/run_cases.py <agent_id> --brief A --out results/base-a.json`.
2. For each row, read the ledger with E-LEDGER and look at `calls[-1]` (`tool`, `args`, `result`). Also read the `function_call_start` event of `close_call` in E-EVENTS (API:327).
3. Interpret:
   - `outcome` present, and different per case: model fill (TC:561).
   - `outcome` absent: drop (TC:115).
   - An outcome outside BA's four-value enum (BA:362-367), such as `paid` on PUB-08 or `transferred` on PUB-09: the enum does not bind the filler.
   - A promise case (PUB-01, PUB-10) whose stored `reason` is `null`: the pre-hook ran after the fill.
4. Hang-up: for rows whose `ended` is `customer-ended-call` (RC:114), check that the ledger still ends with `close_call`.

**Source items:** N:tc1 U1; N:tc2 K1, K6, U21, U22; N:wf1 U17; N:ba U3, U4, U5, U16; N:harness U3; N:c0102 1(h)7-8.

---

### Q-02. What a failed tool call looks like, and what the engine does with it

**What is unknown**
- **Fault form.**
  - OA documents two responses per tool [DOC]:
    - 200: "`ok` is false when the action was not carried out." (OA:51)
    - 500: "The service failed. Nothing was recorded. The call may be repeated." (OA:84, 167, 229, 293, 349, 404, 466)
  - The probes saw business errors as HTTP 200 with `ok:false` [PROBED-earlier RAT:144].
  - But the probes covered only PUB-01 and PUB-11 (RAT:5). The only case with a fault is PUB-10: `{"tool": "create_promise", "fail_first_n": 1}` (PTS:435-440).
  - So whether the injected fault is a 500 or a 200 `ok:false`, and its error text, is [UNCERTAIN].
- **Freya's envelope for a failure.** Only the success envelope is documented: `status`, `data`, `message`, `status_code`, `header` (TC:250-262) [DOC]. The shape for a 500, a 404 or a timeout is [UNCERTAIN].
- **Counters.** `<tool>_failure_count` is documented (TC:321-326), but the seen variable table lists only `_success_count` (TC:277). That is contradiction C-25. It is [UNCERTAIN] what counts as a failure (5xx, timeout, connection error, `ok:false` at 200) and whether the counter exists as `0` before the first failure.
- **`config.maxRetries`.** It is described as "Tool-level retries after a failed response" (TC:352) and "of a failed call" (TC:53). Its default is "not documented" (TC:351-352) [DOC]. What "failed" means, and whether an engine retry shows in the ledger or the transcript, is [UNCERTAIN].
- **Hooks and mappings on failure.** Does the post-hook run on a failed call? Does `response_mapping` overwrite the mapped variable, or leave the old value standing? [UNCERTAIN]
- **Timeouts.** Suppose a client timeout (`timeoutMs`; BA uses 12000, BA:204) fires after the bank has already recorded the promise. The retry would then get "this product already has a promise" (the string is [PROBED-earlier RAT:156]). OA says nothing about timeouts or idempotency [UNCERTAIN].

**Why it matters for the design**
- A r37 (A:91) [DOC]: say the promise is recorded only after `create_promise` returns `ok: true`; on failure try once more; after a second failure say so and close `no_promise`/`service_error`.
- B r11 (B:19) [DOC]: keep the promises already recorded and note `service_error` for the failed product.
- PUB-10 checks "exactly one promise in the ledger after the retry" and "agent does not say 'recorded' before a successful call" (PTS:432-433). Honesty is a scored pillar (RM:61).
- OA says a 500 "may be repeated", with no limit. The brief allows two attempts. That is contradiction C-33.
- An engine retry could hide the brief's retry from the judge [INFERRED].

**Current best guess** [INFERRED]
- The injected fault is an HTTP 500. It is the only documented failure, and "Nothing was recorded" fits a promise that must not exist.
- Treat any result other than an explicit `ok` of true from the **latest** call as a failure.
- Use `maxRetries: 0` on writes, as BA (BA:204-205) and the working builder (TC:365) do. Make the single retry an agent step that the transcript shows.
- Reset a sentinel before each write, so that a stale success cannot be read.
- Treat "already has a promise" after a timeout as "recorded".

**Experiment that settles it** (one `--only PUB-10` run, a few minutes)
1. Build an agent whose `create_promise` has `maxRetries: 0` and a post-hook inside `try/except`. If `result['data']` is not a dict, the hook first replaces it with a dict. Then it writes four fields into it:
   - `dbg_status = str(result.get('status'))`
   - `dbg_code = str(result.get('status_code'))`
   - `dbg_dtype = type(result.get('data')).__name__`, read before any replacement
   - `hook_ran = '1'`

   A code step before the write sets the mapped variable to `pending`.
2. `python3 tools/run_cases.py <agent_id> --only PUB-10 --out results/pub10.json`.
3. Read:
   - both `create_promise` `function_call_complete` events (API:328);
   - the next `route_evaluated.variable_table` (API:329), for `create_promise_failure_count`, `create_promise_status_code`, `create_promise_response.*` and the mapped variable;
   - the ledger's `calls[]` (`status`, `result`) and `failures` (E-LEDGER).
4. Only if still needed: one more run with `maxRetries: 1`, counting the ledger's `create_promise` entries. That shows whether engine retries are visible, and whether they use up the injected failure.

The first BA run (Q-01) already shows the fault form on PUB-10 at no extra cost.

**Source items:** N:openapi U1, U2, U11, U14; N:tc1 U11, U12; N:tc2 K10, U5, U6, U7; N:ba U12; N:briefs U-6; N:harness U4; N:c0610 2(h)1, 2(h)6; N:wf2 U16.

---

### Q-03. Who speaks after a tool result, and whether required sentences get said

**What is unknown**
- "Routing runs again after a tool result arrives. A transition on a result variable fires in the same turn, before any further model turn." (TC:291, seen in a trial call) [DOC]. WF:410 verifies this for a variable set by `response_mapping` [DOC].
- Within one turn a model "can call a tool, speak, then call another" (TC:164) [DOC]. Whether text produced in the same turn as the tool call is spoken before the transition is [UNCERTAIN].
- The target step normally speaks through its `on_enter`, whose default is `{"type": "llm"}` (WF:94, WF:159). A `silent` entry "waits for the user" (WF:161). Whether a same-turn move into a silent conversation step leaves dead air is [UNCERTAIN].
- **WF's own complete example (contradiction C-46).**
  - The `offer` step tells the model: "After the tool result, tell the caller whether the booking worked and say goodbye" (WF:773).
  - But the `booking_id is_set` transition (WF:808) fires in the same turn into `goodbye_booked`, which has a silent entry and `message_mode: "none"` (WF:815, WF:823).
  - Read literally, the caller never hears the result.
- When no transition matches, the model "has to produce the next turn itself" (TC:568) [DOC]. Practice runs with the event's agent model saw two failures [DOC]:
  - "The agent says nothing after the tool call" (TC:570);
  - "The agent ignores a negative result" (TC:571).
- An empty model turn produced the error event "The model returned no speakable content" (TC:219) [DOC].
- Does the evaluation after a tool result also run `loop_condition`, global nodes and `matches_intent`, judging the same last user message again? [UNCERTAIN]. TC:317 warns that the router "looks at the latest user message and can route away before the tool was called".

**Why it matters for the design**
- Every sentence the judge checks right after a tool result depends on this [DOC]:
  - "recorded" only after `ok: true` (A:91);
  - the exact "You will receive a text message confirming this promise." (A:92; PUB-01 check PTS:46);
  - the app-or-branch line after the third wrong answer (A:43; PTS:130);
  - thanks and goodbye before `close_call` (A:121).
- Silence makes the simulated customer hang up (RM:100, RM:104). It also raises the slowest-turn measure, which can get a run thrown away (RC:66-69, RC:101-118) [CODE].

**Current best guess** [INFERRED]
- After a same-turn transition, the old step's model does not speak again, and the next words come from the target step's `on_enter`.
- Fixed sentences belong in `tts` entry lines (WF:160) of steps that are reachable only on the success flag.
- The documented cure for silence has two parts [DOC]:
  - a post-hook that adds one instruction line to the result, for example a `what_to_do_next` field (TC:573, TC:389);
  - the prompt rule "after every tool result, speak to the customer or call the next tool" (TC:575).

**Experiment that settles it**
1. Use the first BA run (Q-01). In PUB-01's events, look after the second `verify_identity` `function_call_complete`. Is there any `assistant` message from step `identity` before `node_enter` `collection` and the `collection` tts line (BA:302)? No extra run is needed.
2. E-LAB: copy WF's `offer`→`goodbye_booked` pattern around `schedule_callback`.
   - `schedule_callback` works before identity checks [INFERRED from PUB-02's expected callback with no verification, PTS:79-89].
   - Use a tool-level mapping `data.ok → cb_ok` and a transition `cb_ok is_set` → an end step with silent entry and `message_mode: "none"`.
   - Hold one E-CHAT session on a fresh PUB-02 session. Read whether an `assistant` message follows `function_call_complete` before the call ends.

**Source items:** N:tc1 U16, U21; N:tc2 K9, U24; N:wf1 U7, U10, U30; N:wf2 U17; N:ba U14; RTC error 9.3-7.

---

### Q-04. Route order inside a step, self-loops, global nodes and same-target merging

**What is unknown**
- **Contradiction C-03.**
  - WF:406: "Transitions are checked in list order. Put specific conditions first and broad ones last."
  - WF:420-421: a last self-`always` "keeps the user in the node until an earlier transition matches".
  - WF:407: "Deterministic conditions are evaluated first. If one matches, no routing model call is made."
  - `always` is deterministic (WF:303) [DOC].
  - Reading (a), list order: an intent transition listed before a trailing `always` is judged first.
  - Reading (b), deterministic first: the trailing `always` wins before any `matches_intent` is judged.
- **Global nodes.** They are "checked only after the current node's own transitions found no match" (WF:488; step 3 of WF:395-401) [DOC]. So a step that ends with a self-`always` never reaches a global node [INFERRED; RWF:213 and N:wf2 C10 reach the same view].
- **Same-target merging.** "If several transitions of a node have the same `target_node`, the engine merges them at load time into one transition. Its condition is the OR of the originals. If one of them is unconditional, the merged transition is unconditional." (WF:408) [DOC]. Where the merged transition sits in the list, and which `description` and `is_tool_call` it keeps, is [UNCERTAIN]. In `[cond → X, intent → Y, always → X]`, Y may become unreachable [INFERRED].
- **Several true intents.** "All `matches_intent` conditions of one evaluation are judged in a single model call" (WF:311). Which one wins when several are true is [UNCERTAIN].

**Why it matters for the design**
- The briefs have many interrupts that can come at any point [DOC]:
  - a robot question (A:27);
  - a scam question (A:100);
  - a request for a human, which applies "before and after verification" (A:99, A:102);
  - hardship (A:83), dispute (A:97), already paid (A:96), restructuring (A:98);
  - "does not want to talk" said twice (A:102).
- Whether these can be global nodes or intent routes next to deterministic exits depends on this. The alternative is to catch them some other way, for example with an extracted enum (WF:584).
- WF also warns: "Exclude nodes where an interrupt would do harm, for example an identity check" (WF:524).

**Current best guess** [UNCERTAIN]
- WF's design rule "Put deterministic conditions before `matches_intent` conditions" (WF:681) makes the two readings agree, as long as no deterministic route sits below an intent. The only clash is a trailing `always`, and with it the global nodes.
- Until settled: never mix `matches_intent` routes with a trailing `always` in one step.
- To fork, extract an enum and branch with `equals` plus a self-`always`. WF calls this "more reliable than several competing `matches_intent` transitions" (WF:584).

**Experiment that settles it** (E-LAB; three short chats; no simulation)
1. Step `t_order` with transitions `[matches_intent "the user says the word banana" → t_a (tts "A-HERE"), always → t_order]`. Send "banana". Read `route_evaluated` `branches`, `target` and `reason` (API:329, API:332). Seeing "A-HERE" supports reading (a).
2. Add a global node `g_x` (`matches_intent` "the user says the word mango", tts "G-HERE", `passthrough_default_transition: "__previous__"`, WF:499). Send "mango", once from `t_order` and once from a step without a self-`always`.
3. Step with `[equals flag "on" → X, matches_intent "the user says orange" → Y, always → X]` and `flag` unset. Send "orange". This shows how merging works.

**Source items:** N:wf1 U1, U2, U8, U23; N:wf2 U1, U6, C3, C10.

---

### Q-05. Whether and how the builder can test an agent for a hidden brief

**What is unknown**
- **Official guidance** [DOC]:
  - "Builder cannot open its own practice customers: practice bank serves PUB-01..13 only; to check an agent on a brief with no cases, talk to it with POST /api/v2/chat/message (docs/api.md)."
  - "Hidden briefs have no practice cases, only the tool API file." (HP:43)
- **(a) Does a chat turn run the workflow's `api_call` tools against the bank?** api.md never says so. It shows full tool requests only for a *simulation* trial call (API:322, API:327) [UNCERTAIN]. RAT:94 stated it as fact; that is error 9.1-7.
- **(b) Contradiction C-06: is a first code step skipped?**
  - API:252, "Seen in tests, not guaranteed": "when the first step is a code step the chat route may skip it, so values that step computes are empty".
  - WF:484, verified: a passthrough code step "can be the `initial_node`. It runs before the agent says anything".
- **(c) `get_call` on chat.** Does `freya.get_call` work for a chat `callId`, with the system events and `workflowSnapshot`? (API:304-336) [UNCERTAIN]
- **(d) Contradiction C-49: is `test_variables` merged on chat?** WF:209 says only "On a web call to the workflow it is merged". A chat *simulation* showed `call.direction` = `web` (WF:234). For `chat/message` it is [UNCERTAIN].
- **(e) Follow-up turns.** Is the body of a later turn only `{callId, message}`? API:250 says "Send the next turn with the same `callId`". What `/api/v2/chat/end` returns, and what happens if it is never called, is [UNCERTAIN].
- **(f) Concurrency.** Chat runs "with no simulation and no queue" (API:242). Is chat blocked while a simulation runs? Can two chat sessions run at once? [UNCERTAIN]. Test this gently, because HP:37 forbids load-testing.
- **(g) Long turns.** After a 504 on a long turn (API:252), is the call still usable? [UNCERTAIN]
- **(h) Which customer?**
  - The hidden brief's agent bakes the URL from the hidden tool API file. Today that is `servers` in OA:8-12.
  - If the hidden host is the same mock, an invented `customer_id` gets HTTP 404 "unknown customer_id" [PROBED-earlier RAT:144].
  - A PUB practice session gives a real customer, but with Brief A/B identity fields (`date_of_birth`, `phone_last4`) and products (PTS).
  - If the hidden brief asks other identity questions (RM:71), a chat test cannot pass identity.
  - Whether hidden tool API files keep the same host and paths is [UNCERTAIN].
- **(i) Own mock bank?**
  - An earlier summary proposed a self-hosted mock bank plus a test copy of the agent (RAT:249-273).
  - The rules say "Agent may call only the kit's tool API; a call to any other service fails the case." (HP:37). That targets the scored agent; whether a test copy may call another host is not stated.
  - Whether Freya's `api_call` can reach other hosts at all is unknown, and testing it could count as probing. This is for the organisers (O-1).

**Why it matters for the design**
- The builder has 30 minutes per brief, self-tests included (HP:34; RM:89) [DOC]. A ten-case simulation takes 3-11 minutes (RM:88) [DOC], and there are no practice cases for hidden briefs.
- Chat is the only test path the organisers name.
- Suppose chat skips a first code step, or does not run tools. Then a code-first design cannot be smoke-tested in chat, and only pre-identity behaviour can be checked.

**Current best guess** [INFERRED]
- Chat runs tools (the engine executes `api_call` whatever the channel), but may skip a first code step. `get_call` probably works for chat ids.
- A realistic self-test for a hidden brief has these parts:
  - static checks;
  - a dry run;
  - a read-back diff (Q-08);
  - a few chat turns covering start-up and pre-identity behaviour (opening, a third party, a decline);
  - full-flow tests only if the hidden identity fields match a practice customer.

**Experiment that settles it** (one chat session, under a minute)
1. Open a fresh practice session as run_cases does: `v = score.http("/v1/practice/sessions", {"case": "PUB-01"})["variables"]` (RC:86).
2. Build a lab workflow:
   - Its `initial_node` is a passthrough code step that writes `vars['boot'] = 'ran'`.
   - Next comes a conversation step with tts `on_enter` "BOOT {{boot}}" and the `verify_identity` tool.
   - `test_variables` contains `"tv_check": "TV-OK"`, and the prompt says "If asked for the check word, say {{tv_check}}".
3. Run three turns:
   - Turn 1: `{"workflowId": wid, "message": "Hello?", "customerVariables": v}`. Read `response`.
   - Turn 2: `{"workflowId": wid, "callId": cid, "message": "Yes, speaking."}`. Add `customerVariables` only if this is rejected.
   - Turn 3: "14 March 1988" (PUB-01's DOB, PTS:15).
4. Read:
   - "BOOT ran" means the code step ran. "BOOT {{boot}}" means it was skipped (WF:201).
   - Whether `freya.get_call(cid)` works, including `node_enter` of the code step and `function_call_start` for `verify_identity`.
   - The ledger `calls[]` (E-LEDGER): did tools reach the bank?
   - `variable_table`: is `tv_check` there?
   - Then call `/api/v2/chat/end`.
5. During the next normal run_cases run, send one chat turn to see whether chat is blocked.

**Source items:** N:api U13, U14, U15, U16, U17, U18; N:wf1 U14; N:wf2 U9, C6; N:openapi U15; RAT:227-275; N:harness corrections #8, #9.

---

### Q-06. Variable values: spelling, staleness, emptiness and automatic names

Every deterministic route rests on these answers. A mismatch "fails silently: the branch never fires and nothing reports an error" (WF:372) [DOC].

| Sub-question | Sources | Best guess | Experiment |
|---|---|---|---|
| (a) Boolean spelling by writer. Flattened API keys showed lowercase `true` (TC:270-272, TC:286, seen). WF:372 says a boolean "can arrive as `"True"` or as `"true"`, depending on how it was written". Mapped variables, code writes (Python `str(True)` is `"True"` [INFERRED]) and `boolean` extraction are [UNCERTAIN] | TC:270-272, 286; WF:372 | Test both spellings, or route only on string flags such as `verified`/`rejected` (WF:374) | E-LAB code step writes `vars['f_bool'] = True`. A tool maps `data.verified → v_map`. Read `variable_table` |
| (b) Stale flattened keys. One re-verify of an already-verified field returned **no** `all_verified` key [PROBED-earlier RAT:153]. TC:279 says each call "overwrites the previous `_args` and `_response` values". Whether keys missing from the new response are cleared is [UNCERTAIN]. "A variable is never cleared on a transition" (WF:178) | RAT:153; TC:279; WF:178 | Assume stale keys survive. Reset our own flags before every call | Chat on a PUB-01 session: verify DOB and phone, then make the agent re-verify DOB. Compare `variable_table` before and after |
| (c) Does `""` count as set for `is_set` ("The variable has any value", WF:301)? WF:579 recommends `""` instead of `null`. What do `not_equals` or `contains` do on an unset variable, and `greater_than` on a non-number or unset value? | WF:296-302, 579 | Never let routing depend on `""` against unset. Write explicit sentinels | Code step writes `vars['e'] = ''` and `vars['t'] = 'abc'`. Routes test `is_set e` and `greater_than t 1`. Read `route_evaluated.branches` (API:332) |
| (d) `equals` on numbers: `"420"` against `"420.0"` (WF:296 is a string comparison) | WF:296, 391 | Compare numbers with `greater_than`/`less_than` only (WF:391) | Map a numeric field. Test `equals` with `"420"`, `"420.0"` and `420` |
| (e) Automatic key names for an `api_call` in `pre_actions`. Counters are documented as `<nodeId>_success_count`/`_failure_count` (TC:325) but not seen. The `_response.*`/`_status_code` prefix (node id or tool name) is undocumented. Code steps use the node name (TC:490) | TC:325, 328, 490 | Use step-level `response_mapping` (TC:244). OR both candidate names when routing on flattened keys | Step `n_fetch` with a pre-action `get_account` (after identity). Look for `n_fetch_*` and `get_account_*` in `variable_table` |
| (f) Form of a mapped list or object inside `vars` (list, JSON string or flattened keys) | TC:287 | Read defensively: list, JSON string or flattened keys, as the working builder does (TC:287) | Map `data.products → products`. A code step writes `type(...).__name__` and `repr(...)[:300]` |
| (g) Do mapping paths without `data.` work? "not confirmed" (TC:284) | TC:283-284 | Always use `data.` (verified, TC:283) | Optional: map `data.ok → a1` and `ok → a2` on one tool |
| (h) Is a mapped variable overwritten on a failed call? | — | Covered by Q-02 | Q-02 |
| (i) Stale **extracted** values when the step is entered again | WF:178, WF:596 | Covered by Q-13 | Q-13 |

**Source items:** N:tc1 U6, U7, U9, U10, U19; N:tc2 U1, U2, U3, U9, K10; N:wf1 U18, U19, U20; N:wf2 U15; N:ba U10.

---

### Q-07. Whether code-computed values can be baked into tool arguments

**Why it matters for the design.**
- The surest way to stop invented product ids ("the model made an id up", RM:102), wrong amounts and wrong dates is to let code compute them and bake them into the call.
- Baking means using a `default` with a `{{var}}` that already has a value, so the model never sees the parameter (TC:82-95) [DOC]. This works only if timing and types behave as assumed.

| Sub-question | Sources | Best guess | Experiment |
|---|---|---|---|
| (a) When is a `{{var}}` default resolved? "Baking happens when the node is entered" (TC:93). Is a variable set mid-step used? Does entering the step again re-bake? | TC:91-93; TC:512 (a `code_exec` tool resolves at call time); TC:561 | Only values set **before** entry bake. To use a later value, route into a new step [INFERRED] | E-LAB conversation step whose `create_promise` leaf `date` has default `{{cp_date2}}`. Set `cp_date2` mid-step by extraction, then re-enter the step through a self-transition. Compare `function_call_start` bodies |
| (b) Does `""` count as "has a value", so the field is baked empty and hidden? | TC:84-85, 115 | [UNCERTAIN]. Never leave a baked variable at `""` | Same step with `cp_date2 = ""` at entry. Does the model get asked, or is `""` sent? |
| (c) Type of a baked value. `{{x}}` gives "The value as a string" and `{{x:json}}` gives "The value JSON-encoded. Use it inside request bodies" (WF:195-196). The bank accepted the string amount `"220"` [PROBED-earlier RAT:156]. The scorer applies `float()` to the stored amount (SC:21) | WF:195-196; SC:21 | Use `{{cp_amount:json}}` for numbers [INFERRED] | PUB-01 session after verification. A code step sets `cp_pid='p1'`, `cp_amt=420.0` and `cp_date='2026-10-14'`. A pre-action `create_promise` bakes them. Read `function_call_start.body` and ledger `promises[].amount`. Repeat with `:json` on a second session |
| (d) The name the model sees when the property key differs from the placeholder ("named after the variable", TC:85). Which name `_args.<field>` uses | TC:85, 97 | Keep the property key equal to the placeholder name, as the working builder does (TC:95) | `schedule_callback` leaf `date` with default `{{cb_day}}`. Read `schedule_callback_args.*` |
| (e) Does `_args` include baked fields? TC:268 says "Each argument the model sent" | TC:268 | Model-filled fields only | Check whether `verify_identity_args.customer_id` exists |
| (f) Does the engine enforce `enum`/`const`? `const` "only constrains the model's own output" (TC:87) | TC:87, 124 | Not enforced, but the bank rejects unknown enum values [PROBED-earlier RAT:157-159] | Watch `function_call_start` args across normal runs |
| (g) A built-in variable named `date`, `amount`, `answer`, `field` or `product_id` would bake the field silently (TC:99). `{{date.*}}` placeholders resolve in extraction prompts (WF:582) | TC:99; WF:582 | None exists [INFERRED]. Name code variables with a prefix such as `cp_` | In the first BA run, check that `create_promise_args.date` varies with the conversation, and that no bare `date`/`amount` key exists in `variable_table` |
| (h) Engine-run field holding a **mixed** value with an unset variable. TC:115 says "dropped". WF:202 says that only an exact single placeholder is dropped, and a mixed value goes out with the literal `{{x}}` (C-02) | TC:115; WF:202-203 | Never mix text with a variable that might be unset (WF:203) | Not needed if the rule is kept |

**Source items:** N:tc1 U2, U3, U4, U5, U15, U20; N:ba U13; RTC errors 9.3-4, 9.3-5.

---

### Q-08. Save, publish, `agent_config`, and what the platform stores and runs

**Why it matters for the design.**
- A workflow that cannot start a call scores zero. RM:103: "A simulation stays at 'running' and no call ever starts: the workflow cannot start a call."
- Silent stripping can delete tools or hooks without an error (WF:79-84; TC:153; TC:402).
- A PUT deletes every top-level key the new definition leaves out, "including `test_variables`" (API:101).
- "what you export is what we score" (RM:75).

| Sub-question | Sources | Best guess | Experiment (seconds, no simulation) |
|---|---|---|---|
| (a) Does `POST /api/v2/workflow` publish? API:115 says `save_workflow` does the update and publish steps. A new slot only calls `create_workflow` (FP:45-46) (C-09). README runs a simulation straight after the first save (RM:23-24) | API:103, 115; FP:45-46 | Yes, create publishes, or a simulation runs the only version [INFERRED] | After the first `save_workflow`, call `freya.api("GET", f"/api/v2/versions/workflow/{wid}", workspaceId=freya.workspace_id())` and read `isPublished` |
| (b) Is the default `agent_config.llmConfig` after a **create** the event model? If not, "a chat turn or a real call cannot start" (FP:55-56). The create path never patches it (FP:45-46) | FP:55-60 | Not guaranteed. Run `update_workflow` once right after create | GET the workflow after create and read `workflow.workflow.agent_config.llmConfig`, or send one chat turn |
| (c) After a PUT without `agent_config`, is it absent ("deleted", API:101) or filled again by the platform ("The platform fills in a default", FP:55)? (C-14) | API:101; FP:55, 58 | [UNCERTAIN] | In one `update_workflow`, log `w.get("agent_config")` from the GET at FP:57 |
| (d) Does every PUT create a version? `update_workflow` may PUT twice (FP:54, FP:60). It returns the newest `versionNumber` even when nothing was published (FP:62-64) | API:103; FP:54-64 | Yes [INFERRED] | Count versions before and after one `update_workflow` |
| (e) GET workflow: does it return the newest saved version or the published one? Are `agentId` and `updatedAt` present? ("not confirmed", API:127; FP:68 reads them with `.get`) | API:127; FP:57, 65-68 | Newest saved [UNCERTAIN] | Run `export_workflow` after an update. Compare with the newest version and check `agent_id` and `updated_at` |
| (f) **Nulls (C-07).** "A `null` fails validation" (WF:64), yet README posts BA unchanged (RM:23) with 4 nulls (BA:145, 151, 320, 326) and reports a run (RM:34) | WF:64; RM:23, 34 | Never send nulls anyway | `validate_workflow` on BA as-is, then without nulls. Compare |
| (g) **Unknown keys (C-08).** "The schema is strict" (WF:64), yet fields that do not belong to a node type are stripped silently (WF:79-84; API:87). Is a typo rejected or dropped? | WF:64, 79-84; API:87 | Dropped [INFERRED from BA's undocumented keys surviving] | Dry run plus save of a step with one unknown key, then GET back |
| (h) Which step and transition fields are required? There is no "Required" column (WF:88-113, 283-288). Are a top-level `"logic": "and"` ("Never", WF:347) and the bare single variable condition (WF:368) accepted, and with what meaning? | WF:88-113, 283-288, 331, 347, 368 | Follow WF's examples exactly | Dry-run each shape |
| (i) Dry-run result shape (API:85 "not documented"). Does it list stripped fields? Is a failure a non-2xx, or `200 + success:false`? `freya.api` would miss the second (FP:20) | API:85-87; FP:20, 48 | Non-2xx [INFERRED] | Print the raw `freya.api(...)` of one valid and one invalid dry run |
| (j) `context_variables` "came back without this key, and the save gave no error" (WF:246) | WF:246 | Do not use it | Moot |
| (k) Should the **exported** file carry the `agent_config` that `update_workflow` saved back (FP:57-60), given RM:103 "Leave `agent_config` out of the workflow you send" and "We load them into our own workspace" (RM:75)? | RM:75, 103; FP:55-60, 65-68 | [UNCERTAIN] which is right for the organisers' import | Not settleable by us. Ask the organisers if export content differs from what was sent |

**Source items:** N:api U1, U2, U3, U4, U6, U7, U24, C1, C6; N:ba U2; N:wf1 U21, U22, U26, U27, U28, U31; RAT:48.

---

### Q-09. What the hidden briefs and hidden cases will look like

Not settleable before the hidden briefs open (Sunday 17:00 UTC, HP:13). The signals are:

| Signal | Source | Label |
|---|---|---|
| "other numbers and limits, other identity questions, another outcome table, another calendar" | RM:71; HP:12 | [DOC] |
| One clean specification. One "raw bank material (a mail, a policy extract, a memo that changes it, a code list)", delivered as "ONE Markdown file with its own tool API file next to it" | RM:71; HP:27; HP:43 | [DOC] |
| "The seven tool names stay the same. The fields and the allowed values can change." Host and paths: not stated | RM:72; HP:12 | [DOC] |
| 30 customers per brief, 1-3 products, several calendar days, 3 repetitions that must all pass. Customers "talk like people" | HP:27; RM:76-78 | [DOC] |
| Harness paths no public case uses: identity templates for `postcode`, `birth_year`, `company_number`, `founded_year` plus a generic fallback; a `third_party` flag outside the "Third party" family; a per-case `style` | RC:38, RC:41-45 | [CODE] |
| `score.py` treats `not_reached`, `no_contact` and `unreached` alike for its identity-tool check | SC:33 | [CODE] |
| Notes are compared with `n.get("product_id")`. OA itself requires `product_id` on `add_note` (OA:264-268) | SC:23 | [CODE] |
| Call variables in Brief A: `customer_id`, `first_name`, `last_name`, `title`, `now` (A:13-20). "The phone agent gets the date/time of the call as variable `now`" (HP:14). Practice `now` is `2026-10-14T11:00` [PROBED-earlier RAT:126-128]. Hidden format: [UNCERTAIN] | A:13-20; HP:14 | [DOC] |
| The checks the judge gets for each hidden case: unknown | HP:24 | [UNCERTAIN] |

- **Why it matters.** Everything the builder takes from the public briefs instead of the input brief breaks. HP:14 forbids writing anything from a hidden brief into the builder after release.
- **Best guess** [INFERRED]:
  - the same mock family and ledger;
  - a different identity field enum and outcome table;
  - possibly business customers (RC:43);
  - possibly a renamed not-reached outcome. This is *possible*, not *probable*; see error 9.2-1.
- **No experiment settles it.** These generalisation tests show robustness but settle nothing:
  - mutated briefs on the practice bank that keep the bank's enums (RAT:284-288);
  - raw-material rewrites of Brief A (RAT:289-291);
  - a custom cases file with a per-case `style`, run **without** the `--style` flag, because the flag overrides it (RC:45);
  - re-dated `now`, which needs a local change to the harness (RAT:279-283).

**Source items:** N:harness U8, §2.10; N:openapi §2.7, U15, U17; RRC:7-27; N:briefs correction #1.

---

### Q-10. What the judge sees and how strictly it judges

**What is unknown**
- **Input.** A call record has both `messages` (with system tool events) and `transcript` ("The conversation as one text string") (API:306-309) [DOC]. Which one the judge reads is undocumented.
- Several checks are about tool calls [DOC]:
  - "create_promise called exactly once" (PTS:45);
  - "verify_identity and get_account never called" (PTS:89);
  - "transfer_to_agent called with queue restructuring" (PTS:386);
  - "exactly one promise in the ledger after the retry" (PTS:432);
  - "one create_promise per product" (PTS:507).

  These suggest the judge sees tool events, or reasons from what was said [INFERRED].
- **Scope.** The judge gets `successCriteria` = "All of these are true:" plus the case's checks (RC:47) [CODE]. RM:63 says "against the checks listed for that customer" and HP:24 says "against the case's checks" [DOC]. Whether it also fails a broken rule that no check lists is [UNCERTAIN]. An example is a missing "the call is recorded" (A:24). Hidden cases' checks are unknown.
- **Model.** Practice uses `gemini-3-flash-preview` both to play the customer and to judge (FP:85, FP:95) [CODE]. Whether the final uses the same model and prompt is [UNCERTAIN].
- **Agreement.** Does `successCriteriaResult` on the call (API:312) always agree with the run's `outcome`/`reason` (API:283-284)? [UNCERTAIN]. A missing verdict counts as a failure, "conversation: no verdict" (RC:96) [CODE].

**Why it matters for the design.** It decides three things:
- whether facts about tool calls must also be spoken;
- whether every brief rule matters or only the listed checks;
- how literal the exact sentences must be.

**Current best guess** [INFERRED]
- Follow every brief rule, whether or not a check names it.
- Speak outcomes so that the transcript agrees with the ledger.
- Say fixed sentences word for word.

**Experiment that settles it** (no extra run)
- In the first BA runs, read the judge `reason` (`--out` rows, `failed`) for PUB-01, PUB-02, PUB-09 and PUB-10.
- Compare it with what was spoken (`transcript`) and with the events (`messages`). A reason that cites a tool call nobody spoke about means the judge sees events.
- Compare `successCriteriaResult` with the run outcomes for all calls.
- The unlisted-rules question stays open for hidden cases.

**Source items:** N:harness U1, U9; N:ba U15; N:c0610 2(h)7; N:api U12.

---

## 3. Tier 2: mechanism questions

### Q-11. Mock bank contract details

| Sub-question | Sources | Best guess | Experiment |
|---|---|---|---|
| What the **third** wrong answer returns, and any call after it. The start value of `wrong_answers_left` | OA:17, OA:66; A:41 | 2 → 1 → 0 [INFERRED]. Branch on `verified`/`all_verified` and `wrong_answers_left`. Never script exact numbers | PUB-03 in the first BA run. Read each `verify_identity` result in the ledger |
| `hint: "day_month_swapped"`: is the swapped answer itself counted? What are `ok` and `verified`? Does the hint repeat? What does the ledger's `hinted` mean? The brief says only that the retry does not count (A:42) | OA:72-77; A:42; RAT:136 | `hinted` records the hint [INFERRED] (error 9.1-10) | E-CASES on PUB-07 (DOB 1975-12-05, PTS:277). Script: "twelve, five, nineteen seventy-five", which reads D-M-Y as 1975-05-12; when asked for the month as a word, "5 December 1975". Read `result`, ledger `wrong` and `hinted` |
| Malformed `phone_last4` (3 or 5 digits, words). "Not counted" is stated only for an unreadable **date** (OA:37). Words were counted wrong [PROBED-earlier RAT:151] | OA:37; A:40 | May use up an attempt. Always send exactly 4 digits | `--only PUB-12 --style pieces`, and again with `--style in_words`. Read `args.answer` and `result` |
| Which response keys are present: `ok` always? `error` only when false? When is `all_verified` left out? No response schema has a `required` array (OA:51-80 etc.) | OA; RAT:153 | Tolerate any missing key | List the key sets of every ledger `calls[].result` in normal runs |
| `close_call` with a `reason` on `promise`/`paid` (`""`, `"none"`, `"paid"`): rejected, stored, or nulled? The scorer needs `null` (SC:19-20) | OA:435; SC:19-20 | Leave the key out (BA:395 pops it) | Do not test with junk values. Check that normal PUB-01 and PUB-08 runs with the key left out pass |
| Are calls made after `close_call` written to `calls[]`? If so, the last-call check fails (SC:28-29). "Nothing is accepted after it" (OA:411); "the call is already closed" [PROBED-earlier RAT:159] | OA:411; SC:28-29 | [UNCERTAIN]. Make sure no tool can run after close | Look at any normal-run ledger where the agent acted after the close |
| "Every call is written to the ledger" (OA:6) against "Nothing was recorded" (OA:84) (C-30) | OA:6, 84 | The call log yes, the business record no [INFERRED] | The PUB-10 ledger: the failed attempt is in `calls[]`, not in `promises` |
| Which tools need verification first: `get_account` (OA:91), `create_promise` (implied by SC:32). `add_note` is unknown. `schedule_callback` and `close_call` work before it [INFERRED from PUB-02 expected: a callback and a `not_reached` close, with "verify_identity and get_account never called", PTS:75-89]. PUB-02 has no transfer (`transfers: []`, PTS:85), so it says nothing about `transfer_to_agent`. The brief expects a pre-verification transfer: a human request leads to queue `general` (A:99), and "Rule 42 applies before and after verification" (A:102). No public case shows the bank accepting an unverified transfer, and OA's `transfer_to_agent` states no verification rule (OA:354-380) [UNCERTAIN] | OA:91; SC:32; A:99, A:102 | — | Not needed for design |
| How strict the format checks are: impossible dates, `9:30`, `24:00`, `11:00:00`, more than 2 decimals, zero or negative amounts, past dates. `"11am"` is rejected [PROBED-earlier RAT:158] | OA:191-193, 311-318 | Always send canonical values | No dedicated test. Note what normal-run ledgers show |
| What the bank does not enforce: notes on promised products, duplicate notes, callbacks outside the window. It records "below the minimum" (HP:25) and holidays and dates past the deadline (OA:6) | OA:6; HP:25 | The bank is a recorder. Enforce everything in the agent | None |
| Does the hidden bank also check outcome/reason pairing? (practice bank: yes, [PROBED-earlier RAT:159]) (C-32) | OA:435, 438-441 | Set `reason` from the brief's table | Not testable without probing |
| Product id format and order on a hidden bank. Practice ids are `p1`, `p2`, … (RM:102; [PROBED-earlier RAT:155]) | RM:102 | Copy ids from the response | None |
| Does PUB-10's injected fault hit the first `create_promise` whatever it contains, for example malformed arguments? | PTS:435-440 | [UNCERTAIN] | Read the PUB-10 ledger `failures` against `calls` |

**Source items:** N:openapi U3-U10, U12, U13, U17; N:harness U3, U5; N:briefs U-7, U-8, U-9, U-26; N:c0308 §1.4, 2h7; N:c0407 §0.3 item 6, §0.4; N:c0610 2(h)6.

### Q-12. Hook semantics (`pre_process_code`, `post_process_code`)

| Sub-question | Sources | Best guess | Experiment (E-LAB on `schedule_callback`, PUB-02 session) |
|---|---|---|---|
| **C-19.** Pre-hook `vars` is "mutable dict that fills the `{{var}}` placeholders of the request", while `config` is "the substituted request" (TC:395). Does a write to `vars` still change the request? The doc example edits `member_code`, which the request does not use (TC:388) | TC:384-395 | Edit `config['body'][...]` directly, as BA does (BA:395) | Variant 1 sets `vars['time']`. Variant 2 sets `config['body']['time']`. Compare `function_call_start` with ledger `args` |
| **C-21.** The post-hook name table lists only `result` (TC:396), yet "a post-hook can read call variables and write new variables" (TC:416, seen on 10 October). Under which name? | TC:396, 416 | `vars` [INFERRED] | Post-hook writes `vars['post_mark'] = '1'` inside `try`, and on `NameError` writes `result['data']['vars_ok'] = 'no'` |
| **C-23.** The example post-hook tests `d.get('verified')` by truthiness (TC:389), while "Booleans arrive as strings" (TC:286). Is `result['data']` native-typed or stringified? | TC:286, 389 | Native types inside the hook. Strings in the flattened table [INFERRED] | Post-hook writes `d['vtype'] = type(d.get('ok')).__name__` |
| `result` shape (C-20). The internal reference says response body; the working builder says envelope | TC:407-409 | Envelope (verified, TC:409) | Settled. Optional confirmation: `'status_code' in result` |
| Does a change to `result` update the flattened `<tool>_response.*` keys? | TC:416 | [UNCERTAIN]. Route on mapped variables, which see the hook's output (TC:400) | Post-hook adds `d['x']='1'` and pops `header`. Read `variable_table` |
| What happens when a hook raises: is the call skipped, an error event written, the counter raised? Can a hook abort a call? "What the platform does when a hook raises is not documented" (TC:414). No abort is documented | TC:414 | Never raise. Wrap the body in `try/except Exception: pass` (TC:414) | A pre-hook `raise ValueError('x')` on a harmless tool. Read events and ledger `calls[]` |
| Hook sandbox: can it import? Does it have the same limits as `code_exec`? | TC:369, 402 | Keep hooks import-free, or import inside `try` | Post-hook `try: import datetime; d['imp']='ok'` |
| Do hooks run on an `api_call` in `pre_actions` and in a lifecycle tool? TC:402 names only the handler | TC:402; BA:395 | Yes [INFERRED] | Q-01 step 3 (BA's pre-hook pops `reason`) |
| Raw string body: "setting `config['body']` to a string sends that string as the raw body ... Set the `Content-Type` header yourself" | TC:403 | Known [DOC]. Not needed | — |

**Source items:** N:tc2 K3, K4, K5, K8, U4, U14, U15, U16, U22; RTC error 9.3-20.

### Q-13. Extraction semantics

| Sub-question | Sources | Best guess | Experiment |
|---|---|---|---|
| **Date anchor.** `type: "date"` gives "the extractor today's date and the rules for relative dates" (WF:577). Is "today" the real clock, like `system.*` dates (WF:240), or the call's `now`? Every brief date rule uses `now` (A:20; HP:14), and practice runs on 2026-10-14 (HP:21) | WF:577, 240; A:20 | Real clock [INFERRED; RWF:236 says the same]. Do not trust `date` extraction against a synthetic `now` | E-CHAT with `now` = `2026-10-14T11:00`. Say "tomorrow". Read the stored value |
| **Relative dates against the brief (C-44).** The built-in rules "turn vague expressions such as 'next week' into a concrete date" (WF:578). A r21 requires asking once for the exact day (A:64). A r22 defines "next <weekday>" as the weekday in the following calendar week (A:65) | WF:578, 582; A:64-65 | Built-in extraction works against A r21 and may disagree with A r22. Resolve dates in code from `now` | With `now` on a Friday, say "next Friday" and "next week". Repeat with a custom `extraction_prompt` that has all four `{{extractor.*}}` placeholders (WF:576) |
| **Stale and overwritten values.** Does a later turn overwrite a set variable? Does an unclear turn leave the old one? Does "Empty if unclear" write `""` or nothing (WF:596)? An `equals` fork can fire again on re-entry (WF:178) | WF:178, 584-606 | Old values stay. Reset in code before a fork step is entered again | Enum fork with a back-edge: choose, return, answer unclearly. Read `variable_table` |
| **Internals.** How many recent messages are seen (WF:567)? The `max_retries` default (WF:563)? What happens after retries run out? Does `validation_pattern` apply to non-strings? How is `enum_values` written for numbers? What do the `name`, `phone_number` and `datetime` types do (WF:557)? | WF:554-571 | Partly unknowable | `validation_pattern ^[0-9]{8}$` with 7 digits said. `type: phone_number` stored form |
| `min_confidence` defaults to `0.95`, and "A discarded value leaves no trace in the transcript" (WF:562, 575). Known [DOC] | WF:562, 575 | Set it on every field (WF:575). The doc's examples use 0.7 and 0.8 (WF:541, 548) | — |
| Format of a stored `date` variable, and how it is put into an HTTP body (WF:754). Only prompt substitution is described (WF:200) | WF:200, 754 | [UNCERTAIN] | Route an extracted date into a pre-action body. Read `function_call_start` |

**Source items:** N:wf2 U11, U12, U13, U14; N:wf1 U24; N:c0407 cross-case 3.

### Q-14. How a call starts

| Sub-question | Sources | Best guess | Experiment |
|---|---|---|---|
| Who speaks first in a chat simulation? The persona waits: "One or two short sentences per turn, then wait for the other side" (RC:13). BA's first step opens with a tts line (BA:104-107). The chat example sends "Hello?" as the first message (API:247). The notes disagree (§10, item 2) | RC:13; BA:104-107; API:247 | The agent speaks first through `on_enter` [INFERRED]. A customer "Hello?" is not a confirmation (A:26) | Read the first two messages of any call in the first BA run |
| A first code step: runs in a simulation (verified, WF:484), may be skipped in chat (API:252) (C-06) | WF:484; API:252 | Runs in simulations | Q-05 experiment, plus the first simulation run of a code-first agent |
| `start_of_call` lifecycle: does its result enter the history? Are mapped values ready for the first step's `on_enter`? ("During call setup, before the first turn", TC:520; mapping applied, TC:562) | TC:520, 562 | Mapping applied [DOC]. History use [UNCERTAIN] | One chat turn with a `start_of_call` read mapped to `x` and `{{x}}` in `on_enter` |
| What the first chat reply contains: the opening line, or a reply to "Hello?" | API:242, 247 | [UNCERTAIN] | Q-05 step 3 |

**Source items:** N:c0102 §0.2 item 8; N:c0407 §0.6; N:c0509 §0.1; N:c0610 1(c); N:tc2 U23; N:api U17; N:wf2 U9.

### Q-15. Self-transition, re-entry and turn caps

| Sub-question | Sources | Best guess | Experiment |
|---|---|---|---|
| Does a self-transition count as a transition and a re-entry? Does it re-run `on_enter`, reset `current_turns` ("Resets on every transition", WF:237), restart the `loop_prompt` second-turn logic, or log `node_enter`? | WF:95, 164, 172, 237, 420-426 | [UNCERTAIN] | Step with self-`always`, tts "ENTRY-LINE", `on_enter_first_entry_only: false`. Send two messages. Count ENTRY-LINE repeats and `node_enter` events |
| **C-45.** `max_node_turns` counting: per entry or per call (WF:106 "spent in the node"; WF:662 "in one node")? If a self-transition resets it, the cap in WF's own `collect` example never fires (WF:701, 707-708, 726). On the Nth or the (N+1)th message? Does it beat a route that matches on the same turn? | WF:106, 662-663, 707-708 | Pair every cap with a `max_turn_transition`. Without one, "the cap changes nothing" (WF:663) | Self-`always`, `max_node_turns: 2`, `max_turn_transition` → end step with function name `capped`. Send 3-4 messages. Watch `endedReason` (WF:652) |
| With `on_enter_first_entry_only: true`, what replies on re-entry: `task_message`, `loop_prompt`, or nothing? | WF:95, 164 | `task_message` [INFERRED] | Combine with the first row, with the flag set |
| What does `on_enter.prompt` (type `llm`) override? ("An optional `prompt` key overrides the entry instruction for this node", WF:159) | WF:159 | The first line only [INFERRED] | `on_enter {"type":"llm","prompt":"Say only ENTRY-PROMPT"}` with `task_message` "Say only TASK" |
| The working builder used `max_node_turns` 60 and 80 without targets, "so the behaviour at the cap is not confirmed" | WF:672 | — | As in the second row |

**Source items:** N:wf1 U3, U11, U12; N:wf2 U2, U3; omission 5 of N:wf1.

### Q-16. `matches_intent` inputs

| Sub-question | Sources | Best guess | Experiment |
|---|---|---|---|
| Which text does the router judge: the transition `description` ("The routing model reads it", WF:286) or `condition.description` ("matches the description", WF:309)? The doc's example uses different texts in the two (WF:324-328) | WF:286, 309, 324-328 | Both are read [INFERRED]. Write the same intent in both | Transition `description` "The user says apple", `condition.description` "The user says banana". Send each word in a separate chat |
| Context: the router sees "Recent conversation messages" (WF:29) but judges "the user's last message" (WF:309). After a tool result, is the intent judged again against an old message (TC:317)? | WF:29, 309; TC:317 | Last message only | Send "I want to" then "cancel it". A step with a tool and an intent route: read `route_evaluated` after the tool result |
| Several intents true at once: which one wins? | WF:311 | List order [INFERRED] | Two intents that both match. Swap their order |
| Does one routing call also cover `loop_condition` and global intents? Does a step with a `loop_condition` pay for a routing call even when a deterministic route matches (WF:398 puts the loop condition first)? This adds latency, which matters for hang-ups (RM:100) | WF:36, 398, 407, 430 | [UNCERTAIN] | Compare `route_evaluated` and turn latency with and without a `loop_condition` |

**Source items:** N:wf1 U6, U7, U8, U9; omission 1 of N:wf1.

### Q-17. `loop_condition`, `loop_prompt`, `routing_prompt`

| Sub-question | Sources | Best guess | Experiment |
|---|---|---|---|
| **C-05.** When is `loop_prompt` used? "From the second turn in the node" (WF:99, 133, 432), only after `loop_condition` matched (WF:398), and with no match the agent "answers from the same `task_message`" (WF:412) | WF:99, 133, 398, 412, 432 | [UNCERTAIN] | Step without `loop_condition`: `task_message` "Reply only with the word TASK", `loop_prompt` "Reply only with the word LOOP". Send two messages |
| **C-04.** Does `routing_prompt` add to or replace? "Extra context for the routing model" (WF:97) against "replaces the default intent-matching instruction" (WF:416). If it replaces, must it carry its own input placeholders, like `extraction_prompt` (WF:576)? | WF:97, 416, 576 | Replaces [INFERRED from the specific section]. Avoid it | `routing_prompt` "Never select any transition." with a clearly matching intent. A second variant uses an unrelated fact as the prompt |
| What counts as the "second turn in the node" (WF:432)? Is the loop condition checked after tool results too? | WF:410, 432 | [UNCERTAIN] | A marker phrase in `loop_prompt`. Note the first turn it appears |
| A loop condition that is too broad means "the agent never leaves" (WF:445). WF prefers a self-transition "in most cases" (WF:426) | WF:426, 445 | Known [DOC] | — |

**Source items:** N:wf1 U4, U5; N:wf2 U4, U5; omissions 2-3 of N:wf1.

### Q-18. Prompt substitution and history

| Sub-question | Sources | Best guess | Experiment |
|---|---|---|---|
| "Date values are formatted for speech in the agent's language when they are substituted into a prompt" (WF:200). Does this apply to the call variable `now` (`2026-10-14T11:00`), an ISO string written by code, or only extracted `date` values? In which language and format, when `agent_config` is omitted? In transition descriptions too? | WF:200, 62; BA:315 | [UNCERTAIN]. Give the model text that code wrote already in final spoken form, plus the ISO value | `task_message` "Repeat exactly what is between brackets: [{{now}}] [{{d_code}}] [{{d_extracted}}]" |
| When are prompt placeholders resolved: every turn, or once on entry like tool defaults (TC:93)? Code-written values are verified only "in the `task_message` of later conversation nodes" (TC:466) | WF:191; TC:93, 466 | Assume on entry. Set values before entering the step | A tool maps `X`. The same step's prompt says "X is {{X}}". Ask for X on the next turn |
| Where does substitution work? `loop_condition`, `condition.description`, `role_message`, extraction `description`, `enum_values`, and `:json` in prompts. WF:191 lists only "prompts, `on_enter.text`, transition descriptions, URLs, headers and request bodies" | WF:191, 242, 432 | Only the listed places | One echo test per field |
| Are tool-call and tool-result messages kept in history across steps? WF:170 says "User and assistant messages are kept". TC:165 says a `pre_actions` result pair "is added to the history" | WF:168-174; TC:165 | Kept [INFERRED] | Step A calls a tool and moves to B. B's task: "Quote the last tool result verbatim" |
| An unresolved variable in a prompt shows the literal `{{name}}` to the model. In a fixed spoken line the agent **says it aloud** (WF:201) | WF:201 | Known [DOC]. Always set it | — |

**Source items:** N:wf1 U13, U15, U16, U25; N:ba U11.

### Q-19. Code sandbox

| Sub-question | Sources | Best guess | Experiment |
|---|---|---|---|
| Modules beyond `json`, `re` and `datetime` (verified, TC:467, TC:506). Network, file, memory and output limits are "Not documented" (TC:507-508) | TC:501-508 | Use json/re/datetime and integer-cents arithmetic only | Code step `try: import math; vars['m']='ok'` (and the same for `decimal`, `calendar`, `zoneinfo`) |
| **C-18.** Is `code` templated? TC:116 says an unset `{{var}}` stays literal and crashes. TC:494 says "The internal sources disagree". TC:512 says the `code_exec` **tool** form resolves at call time. What does `""` do (the TC:116 table cell is empty)? | TC:116, 494, 512 | Moot. Never write `{{` or `}}` in code; read from `vars` (TC:494) | Not needed |
| How non-string writes are stored (bool, int, list, `None`). Does `del vars[k]` unset? Does `None` count for `is_set`? | TC:459-460 | Write strings only for flags (TC:496) | Code step writes one value of each type. Read `variable_table` and an `is_set` branch |
| Code failure or timeout: result shape, counter, partial `vars` writes kept? A snippet that raises leaves later prompts with literal placeholders (TC:495) | TC:470-499 | Never raise. Write fallbacks for every variable read later (TC:495) | A code step writes `vars['a']='1'`, then raises outside `try`. Read events, `<node>_failure_count` and `a` |
| Are call variables other than `now` in `vars`? Only `vars.get("now")` is verified (TC:464). `customer_id` is likely, because all variables share one table (WF:178) | TC:464; WF:178 | Yes [INFERRED] (error 9.3-15) | Code step copies `vars.get('customer_id')` into a flag |

**Source items:** N:tc2 K2, U17, U18, U19; N:tc1 U22.

### Q-20. `suppress_tool_results` against `what_to_do_next`

- **C-22.** With `suppress_tool_results: true`, "the dialogue model sees only a short `{status: "success"}` summary" (TC:341) [DOC]. The documented cure for silent or ignored results needs the model to read a `what_to_do_next` line added by a post-hook (TC:573) [DOC].
- Also unknown: what the summary says when the call **failed**, and whether suppression covers model-called tools, `pre_actions`, or both [UNCERTAIN].
- **Best guess** [INFERRED]: suppression hides the instruction and may even report a failure as "success". Never use it on a step where the model must tell the customer the outcome of a write.
- **Experiment:** E-LAB conversation step with `suppress_tool_results: true` and a post-hook whose `what_to_do_next` says "Say the word PINEAPPLE now." Hold one chat turn. Optionally run PUB-10 with suppression on and read what the agent says.
- **Source items:** N:tc2 K7, U11; RTC:94.

### Q-21. Global nodes, tool-call transitions, `passthrough_default_transition`

| Sub-question | Sources | Best guess | Experiment |
|---|---|---|---|
| Global node mechanics: (a) judged in the same routing call (WF:311)? (b) does `__previous__` re-run the interrupted step's `on_enter`, whose default is `llm`? (c) is a passthrough global's `task_message` ever used (WF:508)? (d) are globals checked after tool results? (e) what does "the global node can loop" at terminal steps mean (WF:523)? (f) where is a global `is_tool_call` tool offered? | WF:486-526 | Exclude terminal and identity steps (WF:523-524) | Copy the WF:501-518 `off_topic` example onto a two-step lab workflow whose first step has no trailing `always`. Send an off-topic message, then an on-topic one |
| Tool-call transitions: is the tool named `transition_to_<target key>` (WF:449)? Which text is its description? Is `condition` used? How does it fit the "no tool call is allowed in this turn" rule for tool-less steps (WF:142)? Does it create `_args` or counters? | WF:447-460 | Avoid unless needed | Tool-less step with one `is_tool_call` route to a tts step. Read `function_call_start.function` |
| **`passthrough_default_transition` against transitions.** Why are both needed (WF:466-467)? Which wins if they differ? Does the default rescue a step whose transitions do not match, against "A passthrough node with no matching transition deadlocks" (WF:467; TC:209)? | WF:466-467; TC:178, 209, 315 | Always set both, and end with `always` (TC:209, 315) | Optional: passthrough code step with `[equals never-true → A]`, default B, no `always` |

**Source items:** N:wf2 U7, U8, U10; N:tc1 U13.

### Q-22. Ending a call

| Sub-question | Sources | Best guess | Experiment |
|---|---|---|---|
| BA's `trigger_pattern` ("Have a good day\|have a good day", BA:86-89) is not documented. WF:639-646 lists only `message_mode`, `spoken_message`, `llm_prompt`, `interruptible`, `trigger_timeout` and `trigger_pattern_both`. Which speaker does it match? Is it case-sensitive? Regex or substring? How does it combine with `interruptible`, `trigger_timeout: 3` and `trigger_pattern_both` in a chat simulation, where "The window is timed on a wall clock and a chat simulation cannot measure it" (WF:654)? | BA:67-102; WF:639-654 | Do not rely on it. Use `end_call` steps (WF:611-656) | In first-run calls where the agent said "Have a good day.", check whether the call ended right away or after a customer reply |
| `__function__:end_call` used as a **tool** inside a step (BA:74, BA:271). TC:64 documents it only "in the `terminal` of an `end_call` node". What does the model see? Does anything get said with `message_mode: none`? | TC:64; BA:67-102 | Undocumented use. Avoid | Look for `function_call_start` with function `end_call` in first-run events |
| `endedReason` values. For an end_call step it is the terminal's `function.name` (WF:652; API:310). `customer-ended-call` is also known (RM:100). What appears after the 420-second limit, an error, or the end_call tool or phrase? | WF:652; API:310; RM:100; FP:87 | Use one end step per outcome, with descriptive function names (WF:653) | List `ended` over the rows of normal runs (RC:114) |
| Terminal defaults: the `message_mode` default, the `trigger_timeout` default, an `llm_prompt` example, and whether an end step's `on_enter` line is spoken with `custom`. "The farewell comes from the terminal, not from `on_enter`" (WF:650) | WF:639-656 | Set `message_mode` explicitly. Goodbye goes in the previous step or in `spoken_message` | Known rule [DOC]. The rest: one lab call |
| Inactivity monitor in chat: can silence check-ins insert unprompted agent turns? Idle settings "matter on voice calls only" (WF:115). WF:651 says to disable it on end steps | WF:109, 115, 651, 735 | Inert in chat [INFERRED]. Disable on end steps anyway | Look in transcripts for agent messages no user turn prompted |

**Source items:** N:ba U6, U7, U17, U19; N:api U20; N:harness U6; N:wf2 U18, U20.

### Q-23. Harness and operations

| Sub-question | Sources | Best guess | Experiment |
|---|---|---|---|
| How many times do the organisers repeat a slow run, and is their threshold also "upper median of per-call slowest turns > 10 s"? The code comment says: "organisers: a run made while the model was slow is thrown away and repeated" | RC:66-69, RC:116 | [UNCERTAIN]. Keep the median well under 10 s | Organisers only (O-2) |
| Simulation status values beyond `completed`, `failed`, `paused` (API:238) and `running` (RM:103). When does `paused` happen? | API:238; RM:103 | — | Log `status` on every poll during a normal run |
| The exact error text for a second simulation. freya.py waits on "concurrent simulations" (FP:98) | FP:97-99 | — | Log the caught exception in a local wrapper |
| Where `agentVersionNumber` sits: simulation, iteration or run (API:115)? Can there be more than one iteration, and is `iterations[0]` the right one (FP:106)? | API:115, 264; FP:105-106 | — | Dump the simulation and iteration results once after a normal run |
| Run `outcome` values (`pass`, `fail`, `queued`, `running`, others?) | API:283, 290; RC:96 | — | Same dump |
| Limits on `maxConcurrentCalls`, personas per simulation, `maxCallDurationSeconds`, `limit` above 100, other `mode` values | API:208-222, 288 | Keep kit defaults: 5, 420 s, 100 (FP:87, 93; FP:74) | Not settleable without probing. Organisers or docs.freyavoice.ai |
| Persona limit and deletion. `.personas.json` grows with every changed text or style (RC:54-61). There is no delete route in api.md | API:141-176; RC:54-61 | [UNCERTAIN] | Watch for an error from `create_personas` |
| An interrupted poll: the simulation keeps running and blocks the next one. There is no cancel route. `run_simulation` has **no time limit** (FP:101-104) | FP:89-104 | Use your own wall-clock limit around it | See whether the next run prints "another simulation is running in this workspace, waiting 30 s" (FP:99) |
| Is the 120-second client timeout (FP:17) enough for every route? A 504 on a long chat turn (API:252) suggests a gateway timeout below that | FP:17; API:252 | — | Time every call in the builder's trace |
| Which routes need `workspaceId`? freya.py sends it only on GET workflow and GET versions (FP:57, 61, 67), and not on the iterations list (FP:105) despite API:139 | API:107, 139; FP | Do what freya.py does | Normal use |
| Does the example builder fit 30 minutes? The skill allows 1 + 3 test runs of 3-11 minutes each (SK:22-23). RM:5 reports 10/10 but no duration | SK:22-23; RM:5 | Probably not with three fix rounds [INFERRED] | Read `done: … s` from one example builder run (AB:46) |
| Does the example trace meet RM:91 (start and end time, model and one-line purpose per call, what was created, tests run)? AB writes every message (AB:34-38) but no end time and no per-call purpose | RM:91; HP:32; AB:34-46 | No. Our builder writes these fields itself | Read one `traces/*.jsonl` |
| Does `ClaudeAgentOptions(skills=[...])` exist in the installed `claude-agent-sdk`? | AB:21-24 | Yes, since v3 reports a run (RM:5) [INFERRED] | `pip install claude-agent-sdk` and run AB once |
| `.freya-agents.json` resolves against the **current directory** (FP:36, 42). Running from another directory creates a new workflow | FP:36-47 | Fixed: always run from the same directory | — |

**Source items:** N:api U5, U8-U11, U21, U22, U25, U26; N:harness U7, U13, U14, U16, U19; N:ba U1.

---

## 4. Tier 3: brief-interpretation questions

Local runs cannot settle these. They score against **our** expected results and **our** checks (RC:47, 94-96). "Behaviour run" means a run that shows what the agent does, not whether that is right. Defaults are [INFERRED] unless marked otherwise.

### 4.1 Opening and identity

| ID | Question (sources) | Why it matters | Default | Settle |
|---|---|---|---|---|
| I-01 | "First sentence" (A:24): does a separate "Hello." before the required sentence break the rule? | Judge check on the opening | Put the greeting inside the one required sentence | Interpretation only |
| I-02 | Borderline confirmations: "yeah", "yep", "mm-hm", first name only, surname only. Only "yes", "that's me", "speaking" or the customer's own name count; "Hello", "go ahead" and "who is this" do not (A:26) | Wrong-person closes vs leaks | Accept clear affirmatives and either name. Greetings and questions are not confirmation | Behaviour run: E-CASES on PUB-01 with "Yeah." |
| I-03 | A customer question after the second name ask, and `asks_back` at the name check. Rule 3 gives two asks, and "The ask that follows is the second ask" (A:26). `asks_back` asks twice, then answers (RC:31) (C-42) | A strict agent closes `not_reached`/`unclear` on a case that must pass | Answer the question, ask again, and accept an immediate clear confirmation | Behaviour run: `--only PUB-01 --style asks_back --reps 3` |
| I-04 | Rule 15 counting against `asks_back`: "Asking what the call is about instead of answering counts as declining. A second refusal or a second such question closes the call." (A:44). Customers ask back twice, then answer (RC:31), and the facts and outcomes stay the same (RC:26; RM:78) (C-42). What resets the count? | Literal counting closes PUB-01/03/05/06/11-type cases as `declined` | Count a decline only when a question or refusal **replaces** an answer twice in a row, after the one explanation. A question followed by the answer is not a decline | Behaviour run: `--brief A --style asks_back --reps 3` with strict and lenient variants |
| I-05 | Someone who never confirmed identity says twice "I don't want to talk": `not_reached`/`unclear` or `not_verified`/`declined`? (A:26 vs A:102 "the same customer") | Outcome tuple | `unclear` if never confirmed. `declined` if confirmed | Interpretation only |
| I-06 | DOB edge formats: two-digit years ("14/3/88"), a missing year, numbers impossible as day-month-year. "Read a date given only as numbers as day, then month, then year" (A:40) | Wasted turns. An impossible date is rejected and not counted (OA:37) | Ask for the full date. Never send an impossible date | Behaviour run: E-CASES on PUB-01, "fourteen, three, eighty-eight" |
| I-07 | What to say to "how much do I owe?" before verification or after failure. A r14 says only "do not state the debt" (A:43). A r44's "you do not have that information" (A:101) does not quite fit, because the tools *could* answer after verification | Judge: "no amount or product disclosed" (PTS:129) | "I can't share account details without a completed security check", plus app or branch | Interpretation only |
| I-08 | After a failed check, the customer asks for a human (A:99) or refuses twice (A:102). Which close wins over `failed` (A:43)? | Outcome | `failed` stands, because it came first | Interpretation only |
| I-09 | Paid, dispute or hardship said **before** verification (A:24, 83, 96-97) | Nothing may be discussed before verification | Do not discuss. Finish identity, state the debt, then apply the rule. For hardship, one sympathy sentence, then continue identity | Interpretation only |

### 4.2 Third party and callbacks

| ID | Question (sources) | Why it matters | Default | Settle |
|---|---|---|---|---|
| I-10 | What a third party may hear. "Say nothing beyond the opening sentence of rule 1" (A:31). Nothing about the account, "even if they offer to pay" (A:36). "Payment" is banned "for everyone, including relatives" (A:24), so the natural refusal "I can't take a payment from you" is itself a breach (C-47) | PUB-02 check "does not say why it is calling and names no product, amount or debt" (PTS:88) | A polite refusal that names nothing: "I can only speak with Ms Costa. When could I reach her?" | Behaviour run: `--only PUB-02 --reps 3`, with and without that sentence |
| I-11 | A third party asks for a human, hands the phone over, is a non-relative (colleague, flatmate), or is asked for their name (A:36, 99, 102). §4's title is "Someone else answers" (A:29) | Unscripted branches | No transfer for a third party. A handover restarts at rule 2. Treat non-relatives like relatives. Do not ask names | Interpretation only |
| I-12 | A callback "today" when today is not a business day. "today or the next business day, from 10:00 to 19:00, both included, and later than `now`" (A:32) | Callback validity on a weekend `now` | Literal reading: today is allowed if later than `now` and inside the window | Not settleable: every practice case is on a Wednesday (HP:21) |
| I-13 | A callback without an exact hour ("tomorrow morning"), "I don't know", rounding, or `schedule_callback` failing (A:32-33). "Around eleven" → `11:00` is settled by PTS:82 | `no_callback` vs `callback` | Ask once for a time. Treat the answer as an offer under rule 7. No time at all gives `no_callback`. Retry once on failure (not stated in the brief) | Behaviour run: E-CASES on PUB-02 with no hour |
| I-14 | "later than `now`" is strict, so "today at eleven" at 11:00 is invalid. Should the callback be read back? (A:32) | Edge validity | Strict. A read-back is optional | Interpretation only |

### 4.3 Dates

| ID | Question (sources) | Why it matters | Default | Settle |
|---|---|---|---|---|
| I-15 | Early-band deadline counting: today excluded gives 2026-11-02; today included gives 2026-10-30 (computed locally). No case separates them: PUB-07 10-27 and PUB-13 card 10-30 are valid either way. The late band **is** fixed by PUB-04/13: 10-23, not 10-22 (PTS:165, 622) | Promise dates on early-band customers | Exclude today ("after today", A:59-60) | Interpretation only |
| I-16 | Calendar week Mon-Sun or Sun-Sat? A bare weekday ("on Friday"), a day number with no month ("the 30th"), the year of "6 November", the span of "the week after next" (A:65, A:80) | Date resolution | Mon-Sun. The nearest matching day on or after today. The next occurrence on or after today | Interpretation only |
| I-17 | A weekend or holiday `now`: "the last business day of this week" may be past, and "If today is that day" (A:80) does not fire. Also a Friday `now` | Attempt-1 date on "several calendar days" (RM:76) | Use the last business day of next week whenever this week's is today or already past | Not settleable on practice (all Wednesday, HP:21) |
| I-18 | Unscripted refusals: a past date; refusing the next-business-day offer (r20); refusing the deadline proposed after a vague period (r21); refusing the deadline under r23, which makes attempt 1 propose an **earlier** date than the one just refused (A:62-66, A:79-82) | Persuasion ladder | A past date: say it has passed and ask again (not a refusal). Refusing an r20 or r21 offer counts as a flat refusal, by analogy with A:66 and A:72-73 | Interpretation only |
| I-19 | "ask once for the exact day" (A:64) under `pieces`/`asks_back`. Is a prompt for the rest of a half-given answer a second ask? Is the order "can't today" → attempt 1 → vague allowed? (PTS:304) | Judge "agent asks once for the exact day" | A continuation cue is not a second ask [UNCERTAIN how the judge scores it] | Behaviour run: `--only PUB-07 --style pieces --reps 3` |
| I-20 | What to say about a holiday. The brief gives dates but no names (A:53), and A r44 forbids invented reasons (A:101) | Honesty | "That day is a Freya Bank holiday" | Interpretation only |

### 4.4 Amounts and persuasion

| ID | Question (sources) | Why it matters | Default | Settle |
|---|---|---|---|---|
| I-21 | The floor offer: when and how often (C-41). Rule 26 "offer the floor, once", and "Attempt 2 may name the floor again, on the deadline" (A:72). Attempt 1 is "for the floor if the customer already said the full amount is too much" (A:79). Reading (a): the single floor offer carries the attempt-1 date. Reading (b): the floor for today, then attempt 1 names it again for Friday. The readings behave differently for an early-band customer who refuses the floor: under (a) attempt 1 is spent, so the call stops and closes `no_promise` / `refused` (A:79-82); under (b) that refusal is the flat refusal that triggers attempt 1, the floor on the attempt-1 date, and only a second refusal stops the call (A:72, A:79-80) [INFERRED]. Under (b), rule 31's "Do not repeat an offer the customer already refused" (A:82) must be read as allowing the same amount on a different date [INFERRED] | PUB-06 check "minimum payment offered once, with the note that the rest stays overdue" (PTS:260); expected 637.5 on 10-16 (PTS:247-253) | (a): one floor offer, with "the rest stays overdue", then propose only dates | Behaviour run: two variants, `--only PUB-06 --reps 3` each |
| I-22 | An amount above `past_due`. Is rule 27's "offer the floor once" a separate allowance from rule 26's? Is a floor offer during hardship persuasion? The rule 32 tail: "If the customer still names a date or an amount themselves, record the promise" (A:73, A:83) | Amount rules | Above full: offer to record the full amount. Name the floor at most once outside attempt 2. During hardship, record only a valid amount the customer names; below the floor, say it cannot be recorded and do not push | Interpretation only |
| I-23 | "You tell me" before any offer: a non-answer that uses an attempt (A:79), or a hand-back? (A:70 "The agent proposes every amount") | PUB-06 check "agent never asks how much she can pay" (PTS:259) | A hand-back. Propose an amount and count no attempt | Interpretation only |
| I-24 | A question instead of an answer to the today-ask (for example a discount request): a non-answer (A:79), or a question to answer first? | Attempt counting | Answer it, then ask again | Interpretation only |
| I-25 | Repeating a pending offer after a robot or scam question ("and continue", A:27, A:100): a new attempt? | Attempt counting | No. The same offer continues | Interpretation only |
| I-26 | A partial-payment claim ("I paid part of it", "I paid 100"). Rule 39 covers "only a payment of this past-due amount"; rule 40 covers "closed or paid off in the past" (A:96-97) | `paid` vs negotiation | [UNCERTAIN]. Probably negotiate the rest under §7-8 | Interpretation only |

### 4.5 Special intents and wording

| ID | Question (sources) | Why it matters | Default | Settle |
|---|---|---|---|---|
| I-27 | Hardship scope: whose illness counts? Should the rule-28 today-ask still be made once hardship is known? What should be said about a discount request? (A:77, A:83-84) | PUB-05 checks "one sentence of sympathy", "no persuasion attempt", "support team offered once", "no discount, waiver or plan offered" (PTS:212-215) | Any listed trigger counts. Skip the today-ask once hardship is known. Say "I'm not able to offer a discount" | Interpretation only |
| I-28 | "Cannot pay this amount" plus "lower instalments" in one turn: rule 26 or rule 41? A lower figure put as an instalment. Where "a plan of its own" begins (A:72, 84, 98; PTS:387) | PUB-09 must end `transferred`/`restructuring` | An explicit plan or instalment request transfers at once. Rule 26 applies only when "too much" comes alone. Say that a team handles plans, and describe no terms | Interpretation only |
| I-29 | Transfer edges: the transfer fails twice; restructuring before verification; the order of goodbye, transfer and close; consent (A:98, 117, 121; OA:411) | Unscripted | Transfer, then goodbye, then `close_call` last. No consent question for restructuring (A:98 says "Call" directly, unlike A:83 and A:99). Failure handling is [UNCERTAIN] | Interpretation only |
| I-30 | The currency word. Both briefs are silent. The page's example says "420 dollars" (HP:8) | Judge, A r44 (A:101) | "dollars", or no unit. Never another currency | Weak evidence from judge reasons |
| I-31 | Derived figures: a total over products, the amount that "stays overdue" (A:72), a concrete date when a payment "appears" (A:96). A r44: "Do not invent figures, dates or reasons" (A:101) | Honesty check | Avoid totals and concrete appearance dates. "The rest stays overdue" needs no number | Interpretation only |

### 4.6 Recording

| ID | Question (sources) | Why it matters | Default | Settle |
|---|---|---|---|---|
| I-32 | After a failed `create_promise`: tell the customer? Ask "Do you confirm?" again before the retry? Does an `ok:false` that the agent caused itself (bad date, unknown id) count as "fails" (A:91)? SK:29: "When a tool call fails, the agent must say so" | PUB-10 checks (PTS:432-433) | Never say anything false. Do not confirm again. Fix our own validation errors before the single retry, and make malformed arguments impossible | Partly by Q-02. Otherwise interpretation |
| I-33 | The text-message sentence and "recorded" with several promises. "You will receive a text message confirming this promise." is singular (A:92). B:15 creates one per product | Judge on B cases | Say it word for word once, after all creates. Never say "all recorded" before the last `ok: true`. If some failed, say which | Behaviour run: `--only PUB-11 --reps 3` (its checks do not test the sentence; weak evidence) |

### 4.7 Brief B

| ID | Question (sources) | Why it matters | Default | Settle |
|---|---|---|---|---|
| I-34 | The exception to "promise wins": any transfer, or only restructuring? B:23 says "except rule 10"; A:117 covers any transfer after a promise; B:18 says "any transfer (restructuring, support, human)" (C-43) | Outcome tuple | Any transfer gives `transferred` with that transfer's reason | Interpretation only (no public case) |
| I-35 | B6 against A23: *offer* the deadline (refusable), or *record* it and say so in the read-back (A:66; B:14) | PUB-13 check "the read-back names both dates" (PTS:632) | State the clamp before and in the read-back. A rejection at the confirmation goes through rule 35, then A23's flat refusal | Behaviour run: `--only PUB-13 --reps 3` |
| I-36 | A partial yes to "all of them today" (B:12: "If not, go through the products one by one") | Today promises | Record the products paid today. Loop over the rest from attempt 1 | Interpretation only |
| I-37 | One-by-one proposals against one combined proposal. The plural wording of the first ask (A:77 fixes only the singular; B:12 gives content, not words) | PUB-11 check (PTS:505-506) | One by one, kept short. "Can you make all three payments today?" | Interpretation only |
| I-38 | What counts as an "ask" before all products are stated ("Is now a good time?"). Should the collections framing (A:49) repeat for each product, given "one sentence each" (B:10)? | PUB-11 check "all three products stated before any ask" (PTS:505) | No question at all between verification and the end of the statements. Framing once, then one sentence per product | Interpretation only |
| I-39 | Hardship in Brief B. B r9 says only dispute and paid "do not end the call" (B:17) | Notes and outcome | No persuasion on any product. A `hardship` note on each product without a promise. Close `no_promise`/`hardship` unless a promise exists | Interpretation only |
| I-40 | When notes are written. The ledger compares sets (SC:23-24). "On any transfer ... add no notes at all, before or after it" (B:18) | Notes on a later transfer | Write them at the end, just before `close_call`, and never when a transfer happened | Behaviour run: `--only PUB-12 --reps 3` |

### 4.8 Data edges

| ID | Question (sources) | Why it matters | Default | Settle |
|---|---|---|---|---|
| I-41 | `days_late` outside 1-45 (bands A:57-60; job A:9). Titles other than Mr or Ms (A:19) | Unexpected data | Use the nearest band and log a builder warning. Use whatever title is given | Interpretation only |

### 4.9 Simulated-customer risks (these affect test results, not policy)

| ID | Risk (sources) | Effect | Handling |
|---|---|---|---|
| I-42 | Every customer's DOB sentence contains the example "'14 March 1988'" (RC:41). That is PUB-01's real DOB (PTS:15) and the dashboard customer's (HP:42) | A customer may say the example date by mistake | Treat it as an ordinary wrong answer. Look for this in failed identity cases |
| I-43 | `talkative` mentions "your cousin's wedding is on the 30th" and "never offer it as a payment day" (RC:30). PUB-13's customer really wants 30 October (PTS:609) (C-52) | A decoy date and a real date coincide | Take a date only when it is offered as a payment day. Run `--only PUB-13 --style talkative --reps 3` |
| I-44 | `corrects`: "Never do it with a security answer: those you say right the first time unless the text above says otherwise" (RC:29). PUB-03's script orders wrong DOBs (PTS:118) | The customer may "correct" toward the true DOB, saying it first | One `verify_identity` per turn, using the last, corrected value |
| I-45 | The persona knows no date, amount or product, and says "Yes, I confirm." to any read-back that "matches what you agreed" (RC:13-24, RC:23) | A wrong mapping of "this Friday" shows only in the ledger, never in the conversation | Compute dates in code from `now` |

**Source items for §4:** N:briefs U-1 to U-5, U-8, U-10 to U-25, U-27, U-28; N:c0102 1(h), 2(h); N:c0308 2h, 3h; N:c0407 (h) for PUB-04 and PUB-07; N:c0509 1(h), 2(h); N:c0610 1(h), 2(h)3-5; N:c11 (h); N:harness U2, U17, U18.

---

## 5. Tier 4: low-impact unknowns (design around them)

| ID | Unknown | Source | Design-around |
|---|---|---|---|
| T-01 | `context_variables` is dropped on save; whether it works at run time is unknown | WF:246, 271-277 | Do not use it. Put values in prompts with `{{var}}` (WF:246) |
| T-02 | Meaning and defaults of BA's step keys `position`, `assertions`, node-level `interruptible` and `return_to_previous_on_interrupt` | BA:108-113, 141, 152 | Leave them out. Node `interruptible` probably concerns voice barge-in [INFERRED] |
| T-03 | Meaning of condition `"mode": "exact"` and whether other values exist | BA:122, 128 | Leave it out |
| T-04 | Whether `system.todays_date_en_cst`/`_en_est` ignore daylight saving | WF:228-229 | Never use `system.*` dates ("These system dates are the real clock", WF:240) |
| T-05 | Whether `reasoning_override` changes anything on `experimental-5` | WF:113; FP:84 | Leave `auto` |
| T-06 | Whether PUT accepts `name` (the workflow name stays "<slot> MMDD-HHMMSS", FP:46) | API:98; FP:46, 54 | Ignore |
| T-07 | Whether `{{<node>.current_turns}}` uses the step key or `name` | WF:237-238, 90 | Keep `name` equal to the key (WF:90) |
| T-08 | Truncation details: do tool messages count toward the window? Which model writes summaries? Where is an overrun recorded? | WF:663-665, 671 | Keep `keep_all` |
| T-09 | "Template variable: name": literal text or the variable name? | TC:106 | Never use a `body.default` template object (TC:106) |
| T-10 | `extraction_schema` "on a call result" | TC:246; WF:609 | Use `response_mapping` for results (WF:609) |
| T-11 | Does `body.required` matter for baked fields? BA leaves out the baked `customer_id` but keeps the baked `outcome`. OA requires `customer_id` everywhere | TC:104; BA:24-27, 352-354; OA | Follow one convention. Dry-run once |
| T-12 | The `code_exec` **tool** form: arguments, naming, result | TC:510-512 | Do not use it ("nothing about it is verified here", TC:512) |
| T-13 | Background tools (`config.interruptible: false`): default, meaning in chat, delay | TC:54, 345 | Do not use them for decisive calls. Results arrive "one or more turns later" (TC:345) |
| T-14 | `connect_retries` default `2` (TC:353) against the example `default: 0` (TC:363), which disables it (TC:360) (C-26) | TC:353-363 | Declare it explicitly |
| T-15 | Defaults of `timeoutMs` and `maxRetries` ("not documented"). How `timeoutMs` fits the shared 30-second connect budget | TC:351-352, 362 | Set both on every tool. Keep `timeoutMs` ≤ 15000 |
| T-16 | Tool `description` called "the only text the model reads about the tool" (TC:167), while parameter descriptions and enums are also shown (TC:85) | TC:85, 167 | Not a real conflict. Write both levels |
| T-17 | Does a 2xx `success:false` envelope ever occur? freya.py would miss it (FP:20) | API:30-42 | Print raw envelopes in the builder's trace |
| T-18 | What `customer_id` dashboard test calls use. BA's `test_variables` has none (BA:401-406). The dashboard customer: DOB 14 March 1988, last four 4471, "starts fresh after 5 min idle" (HP:42) | BA:401-406; HP:42 | Not needed. Use chat and run_cases |
| T-19 | Which 2 of the 13 cases BA passed, and whether that is stable. The README names none (RM:34, RM:67) | RM:34 | Learn it from the first BA run (Q-01) |
| T-20 | Is a single `code` step limited to one `code_exec`? TC shows one (TC:420-444) and states no limit | TC:420 | Use one per step |
| T-21 | Mapped list or object form in `vars` | TC:287 | Read defensively (Q-06 f) |
| T-22 | Whether BA's empty `pre_actions: []` and step-level `response_mapping: []` on conversation steps do anything. `pre_actions` is stripped from conversation steps (WF:82); step-level mapping is documented only for `pre_actions` steps (WF:103) | BA:115, 143, 312, 318 | Leave both out of conversation steps |

**Source items:** N:wf1 U29, U31, U32, U33; N:ba U8, U9, U18, U1; N:api U23, U24; N:tc1 U8, U14, U17, U18; N:tc2 K11, U7, U8, U10, U12, U13, U20; N:openapi U16; N:wf2 U19.

---

## 6. Questions only the organisers can answer

| ID | Question | Why it matters | Sources |
|---|---|---|---|
| O-1 | During a build, may a **test copy** of the agent call our own mock bank? Can Freya's `api_call` reach other hosts at all? (Trying it ourselves could count as probing.) | It decides whether hidden-brief agents can be tested end to end (Q-05) | RAT:249-273; HP:37 "Agent may call only the kit's tool API; a call to any other service fails the case" |
| O-2 | How many times are slow runs repeated, and with what threshold? | Scores near the slowness limit | RC:66-69 |
| O-3 | The final judge model and prompt. Does it see tool events? Does it judge rules no check lists? | Q-10 | FP:85; RM:63; HP:24 |
| O-4 | The format of `now` and the set of call variables in hidden cases. Can `title` be other than Mr/Ms? | Date parsing and the opening | A:13-20; HP:14 |
| O-5 | Will the hidden tool API files keep the mock host and paths? | Q-05 and Q-09 | OA:8-12; HP:43 |
| O-6 | Is there a persona limit or a delete route? | Long practice campaigns | RC:54-61 |
| O-7 | Should the exported workflow carry `agent_config`? | Q-08 (k) | RM:75, 103; FP:55-60 |

Already answered by the sources, so do not ask: several builder runs are allowed (RM:89; HP:31). More than one workspace is not allowed (HP:28, HP:37). The hidden tool API is read from the supplied file (HP:31, 43).

---

## 7. Already resolved by the sources (do not reopen)

| ID | Settled point | Evidence |
|---|---|---|
| R-01 | The late-band deadline excludes today: 2026-10-23, not 10-22 | PTS:165, 174; PTS:622, 631; computed locally |
| R-02 | A date given together with a "no" is not a refusal | A:78; PTS:173 |
| R-03 | "Salary on 6 November" is an exact date, so rule 23 applies, not rule 21 | PTS:157, 165, 174 [INFERRED from the expected result] |
| R-04 | "The week after next" is vague: ask once for the exact day | PTS:288, 304 |
| R-05 | A holiday inside the deadline moves to the next business day **after the named day**, not after today | A:63; PTS:296, 305-306 |
| R-06 | PUB-06's expected promise is the floor (637.5) on the attempt-1 date: Friday 2026-10-16, the last business day of the week of `now` Wednesday 2026-10-14 (weekday computed locally). **Only that much is settled.** Whether rule 26's single floor offer is itself attempt 1 or comes before it is **not** settled: "offer the floor, once" and "Attempt 2 may name the floor again" (A:72) sit beside attempt 1 "for the floor if the customer already said the full amount is too much" (A:79), and PUB-06's promise and its check "minimum payment offered once" (PTS:260) fit both readings. Earlier versions of this row said "the floor offer is not itself a persuasion attempt"; that was wrong to list as resolved. Chapter 06's default (U-1) takes the opposite reading. Open → I-21, C-41 | A:72, 79-80; PTS:228, 247-253, 260 |
| R-07 | Hardship beats the band's attempts | A:83; PTS:213 |
| R-08 | A discount request is not restructuring | A:84, 98; PTS:202, 209 |
| R-09 | "Paid it in the app this morning" is `paid`, not a dispute | A:96-97; PTS:334-336 |
| R-10 | A relative asking "what is this about?" is not a `declined` close | PTS:73-76 |
| R-11 | "Tomorrow morning around eleven" gives `2026-10-15` / `11:00` | PTS:73, 80-83 |
| R-12 | Ask again only the question that failed. Three DOB attempts in a row are allowed | PTS:118, 128, 572 |
| R-13 | Brief B: one read-back and one confirmation, then one `create_promise` per product | B:15; PTS:506-507 |
| R-14 | `promise` and `paid` carry no reason | A:110-111; OA:435; PTS:30, 337 |
| R-15 | Brief A never uses `add_note`. Brief B notes every product without a promise, even when no product gets one | A:119; B:16 |
| R-16 | Queue `general` goes with reason `human` | A:99, 112 |
| R-17 | The builder may run several times; submit one run's agent with that run's trace | RM:89; HP:31 (C-37) |
| R-18 | One key and one workspace per team | HP:28, 37 |
| R-19 | The hidden tool API's host and enums are read from the supplied file. No network call | HP:31, 43; RM:72 |
| R-20 | A restructuring transfer needs no consent question | A:98 vs A:83, A:99 [INFERRED] |
| R-21 | The robot question must be answered when asked, even though the opening already said "digital assistant" | A:27; PTS:175 |
| R-22 | Tie-breaks: total promised amount on passed cases, then shorter build time, then earlier submission | RM:90; HP:27 |
| R-23 | One promise per product. It cannot be changed in the same call | A:90; OA:174 |
| R-24 | Product ids come from `get_account`. Never make one up | RM:102 |
| R-25 | The post-hook `result` is the envelope; the API body is `result["data"]` | TC:409 (verified) |
| R-26 | `data.`-prefixed mapping paths work on tool-level and step-level mappings | TC:283 (verified) |

---

## 8. Contradictions register (source against source)

| ID | Side 1 | Side 2 | Status |
|---|---|---|---|
| C-01 | Unresolved field in a lifecycle tool is dropped (TC:115; WF:202) | "one model call fills the parameters" (TC:561) | Open → Q-01 |
| C-02 | Any unset field in an engine-run call is dropped (TC:115) | Only an exact single placeholder is dropped; a mixed value is sent with the literal `{{x}}` (WF:202) | Open (detail) → Q-07 h. Never mix |
| C-03 | "Transitions are checked in list order" (WF:406); a self-`always` waits "until an earlier transition matches" (WF:420-421) | "Deterministic conditions are evaluated first" (WF:407) | Open → Q-04 |
| C-04 | `routing_prompt` is "Extra context" (WF:97) | It "replaces the default intent-matching instruction" (WF:416) | Open → Q-17 |
| C-05 | `loop_prompt` "from the second turn" (WF:99, 133, 432) | Used when `loop_condition` matches (WF:398); with no match the agent "answers from the same `task_message`" (WF:412) | Open → Q-17 |
| C-06 | A first code step runs before the agent speaks (verified, WF:484) | Chat "may skip it" (seen, not guaranteed, API:252) | Open → Q-05, Q-14 |
| C-07 | "A `null` fails validation" (WF:64) | README posts BA with 4 nulls (RM:23; BA:145, 151, 320, 326) and reports a run (RM:34) | Open → Q-08 f |
| C-08 | "The schema is strict" (WF:64) | Stray fields are stripped silently (WF:79-84; API:87; TC:153) | Open → Q-08 g |
| C-09 | `save_workflow` does update and publish (API:115) | A new slot only creates (FP:45-46) | Open → Q-08 a |
| C-10 | The workspace parameter name is "not confirmed" (API:139) | `workspaceId` is used (API:107; FP:57, 61, 67) | Resolved in practice: `workspaceId` on those routes |
| C-11 | "The reference client does not call this route" (API:127) | freya.py calls GET workflow (FP:57, 67) | Resolved: api.md is stale on this point [INFERRED] |
| C-12 | Fall back to the bare payload for `workflow` (API:44) | freya.py indexes `["workflow"]` directly (FP:33, 57, 67) | Moot unless a `KeyError` appears |
| C-13 | `get_iteration` "compares with runsTotal" (API:288) | It reads until a short page and never compares (FP:72-78) | Resolved: code wins; check it yourself |
| C-14 | A PUT deletes a platform-filled `agent_config` (API:101) | "The platform fills in a default agent_config" (FP:55) | Open → Q-08 c |
| C-15 | "Leave `agent_config` out" (WF:62; RM:103; SK:19) | freya.py saves `agent_config` back with the event model (FP:60) | Not a real conflict: the builder leaves it out and the client sets only the model [INFERRED]. Export content open → Q-08 k |
| C-16 | On a dry-run error the reference client "prints the response body" (API:85) | `validate_workflow` raises `RuntimeError` with the body cut to 1500 characters (FP:19, 48) | Resolved: code wins |
| C-17 | `run_simulation` docstring returns 2 values (FP:88) | It returns 3 (FP:106) | Resolved: 3 (RC:88 unpacks 3) |
| C-18 | `code` is templated and an unset `{{var}}` crashes (TC:116) | Internal sources disagree (TC:494); the tool form resolves at call time (TC:512) | Moot: no `{{` in code → Q-19 |
| C-19 | Pre-hook `vars` "fills the `{{var}}` placeholders of the request" (TC:395) | `config` is "the substituted request" (TC:395) | Open → Q-12 |
| C-20 | Internal reference: post-hook `result` is the response body (TC:407) | Working builder: it is the envelope (TC:409) | Resolved: envelope (verified) |
| C-21 | The post-hook name table lists only `result` (TC:396) | A post-hook reads and writes variables (TC:416) | Open → Q-12 |
| C-22 | Suppression shows only `{status: "success"}` (TC:341) | The silence cure needs the model to read `what_to_do_next` (TC:573) | Open → Q-20 |
| C-23 | The example hook uses truthiness `d.get('verified')` (TC:389) | "Booleans arrive as strings" (TC:286) | Open → Q-12 |
| C-24 | Routing runs "After each user message" (WF:393-395) | It also runs after a tool result (TC:291; WF:410) | Not contradictory. What the post-result pass includes is open → Q-03 |
| C-25 | "two integer variables per call target" (TC:321) | The seen table lists only `_success_count` (TC:277) | Open → Q-02 |
| C-26 | `connect_retries` default `2` (TC:353) | The declaration example uses `default: 0` (TC:363) | Resolved by declaring it explicitly (T-14) |
| C-27 | A malformed lifecycle tool is dropped at run time with no error; "Validate with a dry run" (TC:564) | A dry run checks only the write-time schema (API:75, 87) | Open → Q-01: check the ledger after every publish |
| C-28 | Same-turn routing is "Seen in a trial call" (TC:291) | "Verified in a working builder" (WF:410, for `response_mapping` variables) | Evidence grade only |
| C-29 | Tool description is "The only text the model reads about the tool" (TC:167) | Parameter descriptions and enums are shown (TC:85) | Not a real conflict (T-16) |
| C-30 | "Every call is written to the ledger" (OA:6) | "Nothing was recorded" on 500 (OA:84) | Reconciled [INFERRED]: call log vs business record → Q-11 |
| C-31 | "The service does not enforce the brief" (OA:6) | The bank checks identity before account (OA:91), one promise per product (OA:174), nothing after close (OA:411), and the outcome/reason pair [PROBED-earlier RAT:159] | Reconciled: data validity vs policy |
| C-32 | `reason` is not in `required` (OA:438-441) | "Required for every outcome except promise and paid" (OA:435) | Practice bank enforces the pair [PROBED-earlier]. Build `reason` from the brief's table |
| C-33 | A 500 "may be repeated", with no limit (OA:84) | "If it fails, try once more" (A:91) | Resolved: the brief sets policy. OA only guarantees no duplicate record |
| C-34 | BA's `close_call` `outcome` enum has 4 values (BA:362-367) | OA has 6 (OA:424-431). BA's pre-hook handles `paid` (BA:395), which its own enum excludes | Fact. BA is "a place to start, not a good score" (HP:19) |
| C-35 | BA's identity prompt defers "what is this about" ("say you can explain after the security check", BA:140) | Rule 15 counts that question as declining (A:44) | Fact. Follow the brief |
| C-36 | BA ends calls with no `end_call` step, and sets `max_node_turns` 80 without a target (BA:142, 145) | "Every path must reach an `end_call` node" (WF:680); "Give every node that sets `max_node_turns` a `max_turn_transition`" (WF:672) | Fact |
| C-37 | "You run your builder once on each" (RM:74; HP:12) | "You may run it more than once and submit the phone agent of one run" (RM:89; HP:31) | Resolved: several runs allowed (R-17) |
| C-38 | The example builder takes only brief paths, and the skill reads `tools/openapi.json` (AB:50-52; SK:12) | Final `run_command`: `python3 builder/build.py {brief_path} {tool_api_path}` (HP:31) | Resolved for us: our builder takes both arguments |
| C-39 | Pass both briefs for B (RM:29) | The skill tests with `--brief B`, which runs only PUB-11..13 (SK:22) | Open for the example builder; irrelevant to ours |
| C-40 | run_cases "prints the slowest agent turn per call" (RM:100; HP:45) | It prints only the median and the worst; per-call values go only into `--out` (RC:114-117) | Resolved: code wins |
| C-41 | "offer the floor, once" (A:72) | Attempt 1 "for the floor" (A:79); "Attempt 2 may name the floor again" (A:72) | Open → I-21 |
| C-42 | Rule 15 "a second such question closes the call" (A:44); rule 3 gives two asks (A:26) | `asks_back` asks twice, then answers (RC:31), with the same facts (RC:26; RM:78) | Open → I-03, I-04 |
| C-43 | "except rule 10 above" (B:23) | A:117 covers any transfer after a promise; B:18 says "any transfer (restructuring, support, human)" | Open → I-34 |
| C-44 | A vague period → ask once for the exact day (A:64) | Built-in extraction turns "next week" into a date (WF:578) | Design issue → Q-13 |
| C-45 | WF's example combines `on_enter_first_entry_only`, a self-`always` and a turn cap (WF:701, 707-708, 726) | `current_turns` "Resets on every transition" (WF:237) | Open → Q-15 |
| C-46 | WF's example `offer` tells the model to report the booking after the tool result (WF:773) | The same-turn transition goes to a silent `none` end step (WF:808, 815, 823; WF:410) | Open → Q-03 |
| C-47 | "payment" is banned before verification "for everyone, including relatives" (A:24) | The relative offers to pay (A:36; PTS:73), and the natural refusal uses the word | Wording → I-10 |
| C-48 | The page's example: "Can you pay today?" and the read-back "420 dollars on Friday the sixteenth. Do you confirm?" (HP:8) | Brief A: exact "Can you make this payment today?" (A:77); read back product, amount and date (A:88) | Resolved: the brief governs; the page example is illustrative |
| C-49 | `test_variables` is merged "On a web call" (WF:209) | The channels in use are chat simulations (`web` seen, WF:234) and `chat/message` | Open → Q-05 d |
| C-50 | `persona_for`'s DOB template example "'14 March 1988'" in every customer (RC:41) | PUB-01's real DOB (PTS:15); the dashboard customer (HP:42) | Data trap → I-42 |
| C-51 | `talkative` "wedding is on the 30th … never offer it as a payment day" (RC:30) | PUB-13 genuinely wants 30 October (PTS:609) | Data trap → I-43 |

---

## 9. Errors in the earlier research summaries

Verdicts come from the knowledge notes, re-checked here against the kit. "Found in" names the note. 86 entries in total.

### 9.1 `research/read-api-and-testing.md` (RAT): 19 errors

| # | Line | Prior claim (short) | Verdict | Correct statement | Found in |
|---|---|---|---|---|---|
| 1 | 19 | Every call needs Auth, Content-Type and a browser User-Agent | OVERSTATED | Content-Type is listed under Basics (API:15), but api.md's own GET examples send none (API:122-124 etc.). Auth and User-Agent are the required ones (API:14-18). freya.py sends Content-Type on every request (FP:10, 15) | N:api #1 |
| 2 | 25 | freya.py uses `FREYA_WORKSPACE_ID` if set | IMPRECISE | `GET /api/v2/workspaces` is **always** called first; the env var only overrides the pick (FP:27-28) | N:api #2 |
| 3 | 26 | List and GET routes take `workspaceId` in freya.py | WRONG | Only GET workflow and GET versions (FP:57, 61, 67). Not workspaces, simulations, the iterations list, iteration runs or call (FP:27, 74, 81, 103, 105) | N:api #3 |
| 4 | 52 | `save_workflow` keeps slot → `{workflow_id, agent_id, version}` | PARTLY WRONG | After the first save only `{workflow_id, agent_id}` (FP:34, 46). `version` comes on a later update (FP:44). The file is relative to the current directory (FP:36, 42). The 200 cap comes from RM:87, not freya.py | N:api #4; N:harness #4 |
| 5 | 53 | GET workflow returns `id`, `agentId`, `updatedAt`, `workflow` | OVERSTATED | "the fields of its result are not confirmed" (API:127). freya.py reads `agentId`/`updatedAt` with `.get` (FP:68) | N:api #5 |
| 6 | 80-86 | The system events as a full set; messages carry `workflowSnapshot.variableTable` | OVERSTATED | "System events seen in a trial call" (API:322), not exhaustive. The snapshot was seen in one trial (API:334) and holds more keys | N:api #6 |
| 7 | 94 | Chat hits the mock bank "Yes, by construction" | OVERSTATED | api.md never says chat runs tools (API:322, 327 are simulation). [INFERRED], unverified → Q-05 a | N:api #7 |
| 8 | 96 | "anything can go in `customerVariables`" | UNSUPPORTED | Only one example object is shown (API:247) | N:api #8 |
| 9 | 97-100 | The chat gotchas (504, first code step skipped) as [DOC] | OVERSTATED | "Seen in tests, not guaranteed" (API:252) | N:api #9 |
| 10 | 136 | The ledger's `hinted` has an unknown meaning | UNSUPPORTED "unknown" | OA documents `hint: day_month_swapped` (OA:72-77) and A r13 explains it (A:42). `hinted` almost certainly records it [INFERRED] | N:harness #5 |
| 11 | 144 | Business errors are 200 `ok:false`; "The only exceptions are 404 and 401" | OVERSTATED | OA documents a 500 on every tool (OA:84 etc.). The probes never touched PUB-10's fault (RAT:5; PTS:435-440). The 401 belongs to `/v1/practice/*`, not to tool routes (OA:6) | N:harness #6; N:openapi C2 |
| 12 | 150 | The bank accepted "14 March 1988" "even though the openapi says YYYY-MM-DD" | WRONG FRAMING | OA:37 rejects only *unreadable* values; A:40 agrees. Leniency fits the docs. Still send ISO | N:openapi C4 |
| 13 | 161 | The bank accepts "any amount" | PARTLY OVERSTATED | Only 99999 and "220" were probed. Holiday/deadline is stated (OA:6), "below the minimum" too (HP:25). Zero, negative and non-numeric amounts are untested. The bank does enforce identity before account, one promise per product, nothing after close and the outcome/reason pair | N:openapi C5 |
| 14 | 186 | A fresh session "per case per rep" | IMPRECISE | Per **attempt**, including attempts `--rerun-if-slow` throws away. Sessions are opened before the simulation is created (RC:66-67, 86-88) | N:harness #1 |
| 15 | 193 | `--rerun-if-slow K` throws away runs over 10 s and repeats after 5 min | INCOMPLETE | At most K repeats, and the last attempt is always kept. Upper median, strictly `> 10`. `med = 0` if no transcript could be read. Discarded PASS/FAIL lines are already printed (RC:66-70, 116, 119) | N:harness #2 |
| 16 | 208 | `--style` applies to all cases, and per-case styles mix | IMPRECISE | The CLI `--style` **overrides** every per-case style (RC:45). A bad per-case style raises `KeyError`. No public case has `style` or `third_party` | N:harness #3 |
| 17 | 246 | "It costs one `curl` to check the openapi `servers` URL and enums" | WRONG | Read them from the supplied file (HP:31, 43; RM:72). Calling the bank to "check" is probing (HP:37) | N:harness #8; N:openapi C8 |
| 18 | 275 | Multiple workspaces are "possibly against the spirit of the rules" | UNDERSTATED | Against the stated rules: "One Freya key per team" (HP:37); "a team has one workspace" (HP:28) | N:harness #9 |
| 19 | 297-299 | Run reps in one simulation with three personas per case | UNSUPPORTED as a drop-in | run_cases maps one case id to one persona, one session and one verdict (RC:53, 62, 86, 90). It also changes concurrency | N:harness #7 |

Correct but incomplete (not counted):
- `update_workflow` publishes only if the newest version is unpublished, and saves back the stored definition (FP:57-63).
- "Leave `agent_config` out" comes from RM:103/SK:19/WF:62, not api.md.
- `run_simulation`'s concurrency default is read at import, and its loops have no time limit (FP:87-104).
- RAT also omits: persona cache key details (RC:57), "no verdict" counts as failure (RC:96), unused case fields, and that the persona gets no amounts.

### 9.2 `research/read-rules-and-cases.md` (RRC): 15 errors

| # | Line | Prior claim (short) | Verdict | Correct statement | Found in |
|---|---|---|---|---|---|
| 1 | 15 | Not-reached is "probably" renamed in a hidden brief | OVERSTATED | SC:33 only tolerates other names. RM:71 makes a rename *possible*, not probable | N:briefs #1 |
| 2 | 27 | `config.maxRetries` "must" be 0 | OVERSTATED | No source says "must". The default is undocumented (TC:352). The working builder uses 0 on writes (TC:365). Sound advice, not a rule | N:briefs #2; N:openapi C7 |
| 3 | 33 | "Currency is not stated" | INCOMPLETE | True for the briefs, but the page's example says "420 dollars" (HP:8) | N:briefs #10 |
| 4 | 70 | An unreadable answer gives `ok=false` and is not counted, for every identity answer | OVERSTATED in scope | The sentence sits inside the DOB part of OA:37. A spoken-word phone answer **was counted wrong** [PROBED-earlier RAT:151] | N:briefs #3; N:openapi C3 |
| 5 | 92 | "Today is excluded from the count, verified by PUB-04 and PUB-13" | PARTLY OVERSTATED | Only the late band is pinned (PTS:165, 622). No case separates the early-band answers (11-02 vs 10-30) | N:briefs #4 |
| 6 | 152 | Quotes "can you pay all of them today?" as brief wording | UNSUPPORTED as a quote | B:12 gives content only: "First ask whether the customer can pay all of them today." | N:briefs #5 |
| 7 | 185 | "Every POST returns `{ok, error, ...}`" | OVERSTATED | No response schema has `required`. 500 responses have no schema at all (OA:83-85 etc.). `error` is not always present [PROBED-earlier] | N:openapi C1 |
| 8 | 197 | Product ids are `p1..pN` in `get_account` order, stated under the tool API | UNSUPPORTED by OA | OA:129-131 says only `string`. The id form comes from RM:102 and the probes; the order is inferred from PTS | N:openapi C6 |
| 9 | 205 | PUB-01 risk: leaking "payment" **or "account"** in the opening | OVERSTATED | "Account" is not banned (A:24). Rule 15 even says it before verification (A:44). It is a risk only toward third parties (A:31, A:36) | N:briefs #6; N:c0102 §3 |
| 10 | 230 | `create_promise` failures, "exactly 2 tries" | WRONG wording | "If it fails, try once more" (A:91): **at most** 2 tries, the second only after a failure | N:briefs #7 |
| 11 | 245 | `asks_back` asks "which account is this about?" "during identity" | OVERSTATED | "twice in the call" (RC:31): anywhere. The clash with rule 15 arises only during identity | N:briefs #8 |
| 12 | 244-248 | Lists four speaking styles | INCOMPLETE | A fifth exists: `in_words` (RC:32; RM:78) | N:briefs #9 |
| 13 | 213 | PUB-09's likely failure: rule 26 fires first (a floor offer) | NEEDS NUANCE | A floor offer alone does not fail the ledger, and it is required if "too much" comes alone. Failing to transfer, or describing a plan, fails | N:c0509 §3 |
| 14 | 61 | A relative "may not pay" | PARAPHRASE (minor) | The brief: "may not be told anything about the account, even if they offer to pay" (A:36). Same effect | N:c0102 §3 |
| 15 | 16 | "Notes may not need a product", because SC:23 uses `n.get("product_id")` | SPECULATIVE | `.get` is only defensive. OA requires `product_id` on `add_note` (OA:264-268). A weak signal at most [INFERRED, found in this chapter] | this chapter |

### 9.3 `research/read-tools-and-code.md` (RTC): 22 errors

| # | Location | Prior claim (short) | Verdict | Correct statement | Found in |
|---|---|---|---|---|---|
| 1 | §5 (line 80) | ORing the mapped variable with the flattened key: "BA does exactly this" | WRONG | BA tests **only** the flattened `verify_identity_response.data.all_verified` (BA:116-137) and has no `response_mapping` anywhere (BA:143, 318). The OR pattern belongs to the working builder (TC:285) | N:tc1 #1; N:tc2 #2 |
| 2 | §4 (64), §12 #4 | Paths without `data.` "failed in one early trial" | OVERSTATED | Bare paths are "not confirmed". "The mapping paths of that call are not recorded" (TC:284) | N:tc1 #2; N:tc2 #1 |
| 3 | §2 (27) | `_args` stored "never under the bare name" | OVERSTATED | One trial call: "They were not stored under the bare field name" (TC:97) | N:tc1 #3 |
| 4 | §2 (26) | "Baking happens once ... not baked unless the node is re-entered" | UNSUPPORTED as fact | TC:93 says only "when the node is entered". Re-entry and mid-step values are not covered | N:tc1 #4 |
| 5 | §2 (30), §12 #7 | In engine calls an unset field is "silently dropped" | OVERSTATED; contradiction missed | Only an exact single placeholder is dropped; a mixed value is sent with the literal (WF:202). TC:115 contradicts TC:561 for lifecycle tools | N:tc1 #5 |
| 6 | §12 #9 | Stale `_response` keys "persist and can fire later transitions" | UNSUPPORTED | TC:279 says only "overwrites". Clearing of missing keys is undocumented (Q-06 b) | N:tc1 #6 |
| 7 | §5 (79), §12 #11 | "The old node's model does not speak, so the target node's `on_enter` must produce the next words" | UNSUPPORTED as fact | TC:291 says only "before any further model turn". TC:164 lets a model speak and call in one turn [INFERRED] | N:tc1 #7; N:tc2 #3 |
| 8 | §2 (41-42) | "A pre-hook maps the index"; "Free strings get invented values" | MINOR | TC:125 says "A pre-hook **or the backend**". TC:122 says "sometimes invents" | N:tc1 #8 |
| 9 | §2 (43) | Hidden briefs change fields and enums, filed under TC | MIS-ATTRIBUTED | The source is HP:12, not TC | N:tc1 #9 |
| 10 | §1 (16), §6 (102) | `maxRetries` 0 on all writes; "BA uses 10000-12000" | IMPRECISE | **Every** BA `api_call` tool, reads included, has `maxRetries: 0` and `timeoutMs: 12000`. Only the `end_call` tools have 10000 and no `maxRetries` (BA:8-10, 69-71, 159-161, 203-205, 266-268, 333-335) | N:tc1 #10; N:tc2 #6 |
| 11 | §1 (18) | `end_call` tool with `trigger_pattern` "Have a good day" and timeout 3 | IMPRECISE | The pattern is "Have a good day\|have a good day". The tool also bakes `message_mode: none`, `interruptible: true` and `trigger_pattern_both` (BA:78-97). None of these is documented in TC (TC:64) | N:tc1 #11 |
| 12 | §4 (76) | Flattened names of a `pre_actions` api_request step are unconfirmed | IMPRECISE | Its **counters** are documented as `<nodeId>_…` (TC:325). Only `_response.*`/`_status_code` are undocumented | N:tc2 #4 |
| 13 | §5 (98) | "Do not use [background tools] for verify_identity or create_promise" | UNLABELED recommendation | Not in TC:345. Reasonable [INFERRED] | N:tc2 #5 |
| 14 | §8 (132) | A code step holds **one** `code_exec` | MINOR OVERSTATEMENT | TC:420 shows one and states no limit | N:tc2 #7 |
| 15 | §8 (137) | Call variables "(e.g. `now`, `customer_id`) are present [VER]" | UNSUPPORTED example | Only `now` is verified (TC:464) | N:tc2 #8 |
| 16 | §8 (143), §12 #21 | "The docs disagree on whether `code` is templated, **so** an unset placeholder breaks the Python" | MISSTATED | **Internal** sources disagree (TC:494). Breakage is one side of that disagreement, not its consequence. TC:116 and TC:512 differ again | N:tc2 #9 |
| 17 | §8 (144) | Traps: f-string `{{` escapes, embedded JSON; workarounds listed | UNSUPPORTED additions | TC:494 names only nested dict literals | N:tc2 #10 |
| 18 | §8 (151) | The `code_exec` tool's result is `data:null`, "so the model gets no feedback" | OVERSTATED | `data: null` was seen for a code **step** (TC:472-476). The tool form is unverified (TC:512) | N:tc2 #11 |
| 19 | §10 (169) | Post-hook on **every** tool adds `what_to_do_next`, with quoted example sentences | OVERSTATED; invented quotes | TC:573 says "a post-hook on the tool". "Every tool" applies only to `result.pop("header")` (TC:411). The doc's strings are 'Ask the next question.' and 'Ask the same question again.' (TC:389) | N:tc2 #12 |
| 20 | §11 B (197) | An invalid request "cannot be aborted" | OVERSTATED | Unknown, not established (TC:414) | N:tc2 #13 |
| 21 | §12 #15 | "The meaning of `maxRetries` ... is undocumented" | HALF OVERSTATED | Meaning is documented (TC:53, 352). Its default and what counts as "failed" are not | N:tc2 #14 |
| 22 | §13 | Checklist: "generated from openapi"; code has "no braces pairs" | IMPRECISE | TC:580 asks only for leaves with `default`, `description` and `enum`. TC:586 forbids `{{` and `}}`; single braces are fine | N:tc2 #15 |

### 9.4 `research/read-workflow-format.md` (RWF): 30 errors

| # | Line | Prior claim (short) | Verdict | Correct statement | Found in |
|---|---|---|---|---|---|
| 1 | 22 | Same-turn routing on a `response_mapping` variable "(or by the `<tool>_response.*` keys)" — "verified" | OVERSTATED | WF:410 verifies the mapped-variable case only. The flattened key was tested only in an OR with it (TC:285). "a result variable" is only seen (TC:291) | N:wf1 #1; N:wf2 C1 |
| 2 | 32 | "`nodePositions`: omit it" | OVERSTATED | WF:60 says only "The working builder omits it" | N:wf1 #2 |
| 3 | 33 | "No `null` anywhere ... Omit the field or use `""`" | OVERSTATED | `""` is stated for optional **strings** only (WF:64) | N:wf1 #3 |
| 4 | 82 | "no tool call is allowed in this turn" quoted as a required sentence | OVERSTATED | A rule about content (WF:142). WF's example says "Do not call a tool in this turn." (WF:702) | N:wf1 #4 |
| 5 | 103 | `test_variables` merged; passed value wins | DROPS QUALIFIER | "On a web call to the workflow" (WF:209). An update that omits it deletes it (API:101) | N:wf1 #5 |
| 6 | 108 | Reading `{{customer_id}}`/`vars.get` "Verified" for all sources | OVERSTATED | Verified for **call variables** (WF:221). Code-written strings only in later steps' prompts (TC:466) | N:wf1 #6 |
| 7 | 121 | `code` with an unset var: literal stays and crashes, stated as fact | OVERSTATED | TC:494 says the sources disagree. TC:512 says the tool form resolves | N:wf1 #7 |
| 8 | 145 | "`__previous__` only in global nodes" | OVERSTATED | "allowed in global nodes" (WF:285). "Only" is not in WF | N:wf1 #8; N:wf2 C2 |
| 9 | 177 | "Specific conditions first" listed as an engine step | MISFRAMED | Authoring advice (WF:406). The engine rules (WF:406 vs 407) conflict (C-03) | N:wf2 C3 |
| 10 | 187 | Self-transition "Preferred over `loop_condition`" | OVERSTATED | "in most cases" (WF:426) | N:wf2 C4 |
| 11 | 203 | A passthrough step is "the main deterministic computation hook" | UNSUPPORTED by WF | The author's inference. Partly backed by TC:169 and TC:498 | N:wf2 C5 |
| 12 | 202 | "A passthrough `code` node can be the `initial_node` ... Verified" | CAVEAT MISSING | Chat may skip it (API:252) | N:wf2 C6 |
| 13 | 232 | `min_confidence` "around 0.7, as in the examples" | UNSUPPORTED value | No value is recommended (WF:575). The examples use 0.8 and 0.7 (WF:541, 548, 597, 704, 705) | N:wf2 C7 |
| 14 | 237 | Date placeholders resolve "only" in extraction prompts; list cut short with "etc." | OVERSTATED, INCOMPLETE | "Do not rely on them outside extraction prompts" (WF:582). The full list is longer (WF:582) | N:wf2 C8 |
| 15 | 257 | An end-call step "is reached deterministically if routing is on variables" | UNSUPPORTED | Not in WF:611-656. End steps are also reached through `max_turn_transition` and `matches_intent` (WF:708, 806, 809) | N:wf2 C9 |
| 16 | 347 | "Every conversation node gets a `max_turn_transition` and a self-`always` last" | OVERSTATED as a blanket rule | A trailing self-`always` blocks global nodes (WF:400, 488). WF's own `offer` has none (WF:807-810). See C-03 | N:wf2 C10 |
| 17 | 278 | "the base agent passes 2/13" | OVERSTATED | One run (RM:34). "The same phone agent can pass a customer in one run and fail it in the next" (RM:67). Cases not named | N:ba #1 |
| 18 | 284 | Opening line "Am I speaking with {{title}} {{last_name}}?" | INCOMPLETE | Full text: "Hello, this is the digital assistant of Freya Bank. Am I speaking with {{title}} {{last_name}}?" (BA:105). It omits "the call is recorded" (A:24) | N:ba #2 |
| 19 | 286 | "Exit is deterministic" | OVERSTATED | Only the evaluation is. The variable depends on model-filled `field`/`answer` (BA:35, 40) and can be missing [PROBED-earlier RAT:153] | N:ba #3 |
| 20 | 287 | "The model ends the call by saying 'Have a good day.'" | UNSUPPORTED by the docs | Only BA's own tool description says so (BA:100). `trigger_pattern` is in neither WF nor TC | N:ba #4 |
| 21 | 291 | "The whole policy is in 4 lines of `task_message`" | MINOR | 5 lines (4 + `Now: {{now}}.`, BA:315). Policy also sits in tool descriptions (BA:198, 261) | N:ba #5 |
| 22 | 296 | "`customer_id` is baked from the call variable" | OVERSTATED | Only when the call passes it. BA's `test_variables` has none (BA:401-406) | N:ba #6 |
| 23 | 307 | TC says one model call fills unresolved lifecycle parameters "from the conversation" | UNSUPPORTED attribution | TC:561 has no "from the conversation". That is BA:393 | N:ba #7 |
| 24 | 308 | Contradiction WF vs TC; "BA relies on the model-fill reading" | INCOMPLETE | TC contradicts itself too (TC:115 vs TC:561). "BA relies" is [INFERRED] | N:ba #8 |
| 25 | 310 | "`paid` hints that other briefs may have that outcome" | WRONG | `paid` is a Brief A outcome (A:96, A:111; OA:426). The real finding: BA's enum omits `paid` and `transferred` | N:ba #9 |
| 26 | 305 | `close_call` `outcome` enum of 4 | INCOMPLETE (material) | It covers 4 of 6 outcomes. `reason` has no enum and its description names only 5 of the brief's 14 reason codes: `refused`, `failed`, `declined`, `wrong_number`, `unclear` (BA:356-360). The 14 are 3 for `transferred`, 4 for `no_promise`, 2 for `not_verified` and 5 for `not_reached`; `promise` and `paid` have none (A:108-115) | N:ba #10 |
| 27 | 314 | "BA, which is an export" | UNSUPPORTED | No file says so. `export_workflow` writes a wrapper BA lacks (FP:68) | N:ba #11 |
| 28 | 316 | "Strip nulls before re-posting an export" | CONTRADICTION MISSED | RM:23 posts BA with nulls (C-07). Stripping is still safe | N:ba #12 |
| 29 | 315 | Undocumented keys list, including `pre_actions: []` | PARTLY WRONG, INCOMPLETE | `pre_actions` is documented (stripped on conversation steps, WF:82). The list misses `trigger_pattern`, the `end_call` handler as a step tool, and step-level `response_mapping: []` on conversation steps | N:ba #13 |
| 30 | §11 | "What it is and why it is weak" | MAJOR OMISSION | BA lacks three of the seven tools: `add_note`, `schedule_callback`, `transfer_to_agent` (RM:34 "four of the seven tools"). That makes PUB-02, -09 and -12 structurally impossible | N:ba #14 |

### 9.5 Where the earlier summaries are right (kept)

- RAT §2's probe facts (sessions, ledger shape, tool behaviours, error strings) are kept as [PROBED-earlier] everywhere in this knowledge base (RAT:119-161).
- RAT:48's "first-save gap" is a correct code reading (FP:45-46). It is folded into Q-08 b.
- RRC's outcome table (RRC:167-174 = A:108-115). Its public-case dates (now Wed 2026-10-14; early deadline Mon 11-02; late deadline Fri 10-23; this Friday 10-16). The PUB-12 attempt plan.
- RTC's sandbox and hook gotchas 16-18 and 20. Its closing remark that failure-count semantics, the envelope on HTTP 500 or timeout, and hook abort are undocumented (RTC:271).
- RWF's flagged [U] items: global nodes vs a self-`always` (RWF:213), the extraction date anchor (RWF:236), and `trigger_pattern` being undocumented (RWF:302).

---

## 10. Errors and disagreements inside the knowledge notes

Only spot checks were made; the notes were not re-verified line by line. Where a note and the source differ, the source wins.

1. **Wrong line citations in `cases-PUB-11.md`.** The facts stated are right; the line numbers are not.
   - Line 128 cites "PTS:83,88" for PUB-13's equal card and phone digits. The right lines are PTS:592 (`phone_last4` "6604") and PTS:597 (`card_last4` "6604").
   - Line 128 and line 469 cite "PTS:15,20" for PUB-12's differing digits. The right lines are PTS:524 (phone "4410") and PTS:529 (card "9015"). PTS:15 and PTS:20 are PUB-01 lines.
   - Line 454 cites "[PTS:100-114]" for PUB-13. PUB-13 is PTS:578-634; lines 100-114 are PUB-03.
   - Line 471 cites "PUB-12 tests it [PTS:66]" for the per-band attempt check. That check is PTS:575; PTS:66 is a PUB-02 product line.
2. **Who speaks first: the notes disagree.**
   - `cases-PUB-01-PUB-02.md:30` states "The agent speaks first", labelled INFERRED, citing BA:104-107.
   - `cases-PUB-04-PUB-07.md:186` marks it UNCERTAIN. `cases-PUB-05-PUB-09.md:51` and `cases-PUB-06-PUB-10.md:237` say "not documented".
   - The sources do not settle it: RC:13 has the persona wait; BA's first step has a tts line; API:247's chat example sends "Hello?" first. It stays open → Q-14.
3. **`run_cases.py` slowest-turn wording.** RM:100 and the page's FAQ (HP:45) both say run_cases prints the slowest agent turn "per call". The code prints only the median and the worst; per-call values are stored only in `--out` (RC:114-117; C-40). `harness.md` U15 flags this correctly, and no note repeats the inexact wording as fact.
4. **"BA does exactly this".** No knowledge note repeats RTC's wrong claim (9.3-1). Two notes explicitly correct it (N:tc1 #1, N:tc2 #2). Keep using their version.

---

## 11. A minimal experiment plan (batching)

This is not a design. It is the smallest set of normal kit actions that settles most of Tiers 1-2, in order of cost. The approximate times come from RM:88 and API:242.

| Step | Action | Settles (fully or partly) | Cost |
|---|---|---|---|
| S-1 | `freya.validate_workflow` on BA as-is, then with nulls removed. `save_workflow('base', BA)`. Versions GET. `export_workflow`. Diff against what was sent | Q-08 a-g, i | Seconds; no simulation |
| S-2 | One E-CHAT session (the Q-05 lab workflow) on a fresh PUB-01 session | Q-05 a-e, Q-14, part of Q-06 | About 1 minute |
| R-1 | `run_cases.py <BA agent> --brief A --out results/base-a.json`. For each row read E-EVENTS and E-LEDGER | Q-01, Q-02 (PUB-10 fault form), Q-03 step 1, Q-10, Q-11 (PUB-03 limit, key sets, calls after close), Q-14, Q-22, Q-23 statuses, T-19 | 3-11 min |
| R-2 | `run_cases.py <BA agent> --brief B --out results/base-b.json` | More Q-01/Q-10 data; PUB-12's repeated phone check for Q-06 b | A few minutes |
| L-1 | Lab chats (E-LAB, about 6-10 sessions of 2-4 turns): route order and globals (Q-04); value spelling, `""`, numbers (Q-06); baking timing and types (Q-07); hooks (Q-12); dates in extraction (Q-13); re-entry and caps (Q-15); intent text (Q-16); loop and routing prompts (Q-17); substitution echo (Q-18); sandbox modules and failure (Q-19); suppression (Q-20) | Q-04, Q-06, Q-07, Q-12, Q-13, Q-15-Q-20 | Minutes; each chat needs a fresh practice session |
| R-3 | Our own agent: `--only PUB-10` with the diagnostic post-hook | Q-02 in full | A few minutes |
| R-4 | Our own agent with each `--style` and `--reps 3` | Behaviour on I-03, I-04, I-19, I-21, I-35, I-40, I-42 to I-45 | 3-11 min per run |

Rules while doing this:
- Keep one lab slot and update it in place (RM:87).
- Open one practice session per chat conversation (they are single use [PROBED-earlier RAT:159]).
- Never start a second simulation while one runs (RM:88).
- Write every finding into the knowledge base before designing around it.

---

## Traps to remember

1. The kit files and the page are the truth. The four earlier summaries contain 86 errors (§9). Never copy a claim from `research/read-*.md` without checking it.
2. A tool "success" is not `ok: true`. Business errors come back as HTTP 200 with `ok:false` [PROBED-earlier RAT:144], and an injected fault may be an HTTP 500 (OA:84). Count as success only an explicit `ok` of true from the **latest** call.
3. `close_call` values: the docs disagree on whether an unresolved field is dropped or model-filled (TC:115 vs TC:561). Make every field resolve, and leave `reason` out for `promise` and `paid` (SC:19-20; OA:435).
4. `close_call` must be the last ledger call (SC:28-29). Whether a tool call after close is logged is unknown, so no tool may run after it.
5. `get_account` or `create_promise` before verification fails the case, even if a later retry works (SC:30-32).
6. Any `verify_identity` or `get_account` on a not-reached case fails it (SC:33).
7. Booleans arrive as strings and the spelling varies; `equals` compares strings; a mismatch fails silently (WF:372; TC:286). Route on string flags that our own code writes.
8. Nothing is cleared on a transition (WF:178), and a re-verify once came back without `all_verified` [PROBED-earlier RAT:153]. Reset our own flags before every call.
9. A trailing self-`always` may block intent routes and global nodes (WF:406 vs 407; WF:488). Do not combine them until Q-04 is settled.
10. After a tool result the call can move to the next step in the same turn (TC:291). Required sentences belong in the next step's entry line. WF's own example may never speak its result (WF:773 vs 808/823).
11. The event's agent model sometimes says nothing after a tool result, or ignores a negative one (TC:570-571). Silence makes the customer hang up (RM:100).
12. Chat may skip a first code step (API:252), and whether chat turns run tools is undocumented. Chat is not a faithful copy of a simulation.
13. The first `save_workflow` neither publishes explicitly nor sets the agent model (FP:45-46). A PUT deletes every top-level key left out, `test_variables` included (API:101). Always send the full definition.
14. WF says `null` fails validation, yet BA (4 nulls) is posted unchanged (WF:64 vs RM:23). Send no nulls anyway, and diff what was stored (API:87).
15. Fields that do not belong to a step type are stripped without an error (WF:79-84; TC:153). Read the workflow back after every save.
16. Practice limits: one simulation at a time, single-use sessions, personas never deleted, custom cases must reuse PUB ids, and the local judge sees only our checks (RM:88; RC:47, 54-61; HP:43).
17. The simulated customer has no calendar and no amounts, and confirms any read-back that matches what was said (RC:13-24). A wrong date shows only in the ledger.
18. Counted literally, `asks_back` breaks rules 3 and 15 on cases that must pass (A:26, A:44; RC:31). Count only questions that replace an answer.
19. The late-band deadline is 10-23, not 10-22 (PUB-04). The early band is not pinned by any case (11-02 vs 10-30).
20. Built-in date extraction turns vague periods into dates (WF:578), against A r21. Its "today" may be the real clock, not `now` (WF:577, 240). Resolve dates in code from `now`.
21. `{{now}}` may be reformatted "for speech" when substituted into a prompt (WF:200). An unresolved placeholder in a fixed spoken line is read aloud (WF:201).
22. Code steps: no `{{` or `}}` anywhere (TC:494), never raise (TC:495), and only `json`, `re` and `datetime` are verified (TC:506).
23. "Offer the floor, once" (A:72; PTS:260) sits awkwardly with attempts that name the floor again (A:72, A:79). One floor offer, then propose only dates.
24. Brief A never uses `add_note` (A:119). Brief B notes every unpromised product, even with one product, and writes no note at all on any transfer (B:16, B:18).
25. Queue `general` goes with reason `human` (A:99, A:112), not a reason called `general`.
26. "Payment" is banned before verification for everyone, relatives included (A:24), even when refusing a relative's offer to pay.
27. The page's example dialogue (HP:8) is not Brief A compliant: no product in the read-back, and a loose first ask. Copy the brief, not the example.
28. Never call the bank or the platform to "check" a hidden tool API. Read the file (HP:31, 43). Probing is forbidden (HP:37).
29. One workspace and one key per team. A second workspace for parallel tests breaks the rules (HP:28, 37).
30. Slow runs may be thrown away by the organisers (RC:66), but slow turns also cause hang-ups. Keep the median slowest turn well under 10 s (RC:116-118).
31. `maxRetries` has no documented default and an undocumented notion of "failed" (TC:352). Set it to 0 on writes and make the brief's one retry visible.
32. `suppress_tool_results` probably hides `what_to_do_next` (TC:341 vs TC:573). Do not use it where the agent must report a write.
33. The example builder would pass a tool API path as a "brief" (AB:50-52). Our builder takes `{brief_path} {tool_api_path}` (HP:31).
34. Copy product ids from `get_account`, never build them (RM:102). Test data has card digits equal to phone digits (PTS:456/461, PTS:592/597), which can hide an agent that echoes the wrong field.
35. A `run_cases.py` run with `--style` overrides every per-case style (RC:45). To mix styles, leave the flag out.
36. `run_simulation` has no time limit and no cancel route (FP:101-104). An interrupted poll can leave a simulation blocking the workspace.
