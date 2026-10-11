

# api — Corrections
Every claim in `research/read-api-and-testing.md` that concerns api.md or freya.py was checked. Most are correct. The ones below are wrong, overstated or unsupported.

| # | Prior claim (line) | Verdict | Correct statement |
|---|---|---|---|
| 1 | "Every call needs `Authorization`…, `Content-Type: application/json`, and a browser-like `User-Agent`" (L19) | OVERSTATED | api.md lists `Content-Type: application/json` under Basics (api.md:15). However, its own GET examples send no Content-Type (api.md:122-124, 134-136, 171-173, 233-235, 259-261, 271-273, 299-301). `freya.py` sends Content-Type on every request, GET included, because it uses one fixed header dict (freya.py:10, 15). Auth and User-Agent are the headers documented as required (api.md:14, 16, 18). [DOC][CODE] |
| 2 | "`freya.py` caches the first entry's id, or uses `FREYA_WORKSPACE_ID` if set" (L25) | IMPRECISE / misleading | The env var takes precedence, but `GET /api/v2/workspaces` is **always** called first, even when `FREYA_WORKSPACE_ID` is set (freya.py:27 runs before freya.py:28). Setting the env var therefore skips no request, and a failure of that GET still raises. The env var is read lazily on the first call, not at import (freya.py:28). [CODE] |
| 3 | "List and GET routes take a `workspaceId=` query parameter in `freya.py`" (L26) | WRONG | `freya.py` passes `workspaceId` on exactly two routes: `GET /api/v2/workflow/{id}` (freya.py:57, 67) and `GET /api/v2/versions/workflow/{id}` (freya.py:61). It does **not** pass it on `GET /api/v2/workspaces` (27), `GET /api/v2/simulations/{id}` (103), `GET /api/v2/simulations/{id}/iterations` (105, a list route), `GET …/iterations/{itId}` (74), or `GET /api/v2/call/{id}` (81). api.md:139 says "List routes need the workspace id as a query parameter. The name of that parameter is not confirmed here." Yet the iterations list in freya.py goes without it. [CODE][DOC] |
| 4 | "`save_workflow(slot, wf)` keeps slot → `{workflow_id, agent_id, version}`" (L52) | PARTLY WRONG | After the **first** save (the create path) the slot holds only `{workflow_id, agent_id}` (freya.py:46, 34). `version` is added only by a later update (freya.py:44). The state file is `.freya-agents.json` **relative to the current working directory** (freya.py:36, 42). Running from another directory starts a fresh state and creates a new workflow. (The "at most 200 workflows" part is right, but it comes from README.md:87 and hackathon-page.md §Submit/Limits, not from freya.py. freya.py:39-40 only says "a limited number".) [CODE][DOC] |
| 5 | "`GET /api/v2/workflow/{id}?workspaceId=` returns `result.workflow` with `id`, `agentId`, `updatedAt`, `workflow`" (L53) | OVERSTATED (presented as confirmed) | api.md:127 says "The reference client does not call this route, so the fields of its result are not confirmed." The shape is only what freya.py *expects*: `result.workflow.id` and `result.workflow.workflow` are read as required keys (freya.py:57, 68). `agentId` and `updatedAt` are read with `.get`, so they may be missing (freya.py:68). The inner definition carries `agent_config.llmConfig.{provider, model}` only as freya.py expects (freya.py:58). [DOC][CODE] |
| 6 | System events listed as the full set, and "User and assistant messages carry `workflowSnapshot.variableTable`" (L80-86) | OVERSTATED | api.md labels the event table "System events seen in a trial call" (api.md:322), so it is not exhaustive. The snapshot sentence reads "User and assistant messages **in the trial call also carried** a `workflowSnapshot`" (api.md:334). That is one observation, not a guaranteed contract. The snapshot holds more than `variableTable`: `currentNode`, `previousNode`, `nodeTurnCount`, `totalTurnCount`, `transitionHistory`, `enteredNodes`, `variableTable` (api.md:334). [DOC] |
| 7 | "Does [chat] hit the mock bank? **Yes, by construction.** … puts the chat's tool calls into that session's ledger" (L94) | OVERSTATED (inference stated as fact) | api.md never says that chat turns execute `api_call` tools. It shows the full tool request only for a *simulation* trial call (api.md:322, 327). It also warns that chat may behave differently from a simulation, for example by skipping a first code step (api.md:252). So "chat tool calls reach the bank and show in the ledger" is [INFERRED], probably right but unverified. The no-key and `customer_id` binding facts are [PROBED-earlier] mock-bank facts and are kept as such. |
| 8 | "anything can go in `customerVariables`" (L96) | UNSUPPORTED | api.md shows one example object only: `customer_id`, `first_name`, `last_name`, `title`, `now` (api.md:247). It says nothing about arbitrary keys, types or limits. For simulations, api.md:214 says only that each value is "the object of call variables for that persona's call". [DOC] |
| 9 | The chat gotchas tagged plain "[DOC]": 504 on a long turn, a first code node skipped (L97-100) | OVERSTATED (hedge dropped) | api.md introduces them as "**Seen in tests, not guaranteed**: a long turn can return 504, and when the first step is a code step the chat route may skip it…" (api.md:252). They are observations, not documented behaviour. The 500 sentence is stated without that hedge: "A bare 500 here means the workflow cannot start a call at all." (api.md:252). [DOC] |

Claims that are **correct but incomplete**. These are not counted as corrections; the details are in §2.
- `update_workflow` "publishes the newest version" (L43-47). It publishes only if that version is not already published (freya.py:63). Its second PUT sends back the definition **as the platform stored it**, not the caller's object (freya.py:57, 60). It returns `versionNumber` whether or not it published anything (freya.py:64).
- The "first-save gap" (L48) is a correct code reading. In addition, the create path never publishes explicitly (freya.py:45-46). That contradicts api.md:115, which says `freya.save_workflow` does the update and publish steps. See U1 and U2.
- "Leave `agent_config` out" (L31) is not in api.md. It comes from README.md:103, SKILL.md:19 and workflow-format.md:62. freya.py itself sends `agent_config` in its patch PUT (freya.py:60).
- `run_simulation` (L64-69): the concurrency default is read **at import time** (freya.py:87). Both the retry loop and the polling loop have **no time limit** (freya.py:89-99, 101-104).

---

# api — Uncertainties
Each item says what is unknown and how normal kit use, once a key exists, would settle it. No extra probing is needed beyond calls a builder makes anyway. Print the raw result of `freya.api(...)` where noted.

| # | Unknown or contradiction | Sources | Experiment that settles it (normal use) |
|---|---|---|---|
| U1 | Does `POST /api/v2/workflow` publish the first version? (api.md:115 says `save_workflow` publishes; freya.py:45-46 does not on a create) | api.md:103, 115; freya.py:45-46; README.md:22-24 | After the first `save_workflow(slot, …)`, call `freya.api("GET", f"/api/v2/versions/workflow/{wid}", workspaceId=freya.workspace_id())` and read `isPublished` |
| U2 | Is the default `agent_config.llmConfig` after a **create** the event model? If not, the first-ever chat turn fails until a second save | freya.py:55-56; prior L48 | After the first create, GET the workflow (as `update_workflow` does) and read `workflow.workflow.agent_config.llmConfig`. Or send one chat turn right after creating |
| U3 | After a PUT without `agent_config`, is it absent (api.md:101 "deleted") or re-filled with defaults (freya.py:55)? Which keys does it have? | api.md:101; freya.py:55, 58 | Inside one `update_workflow` call, log `w.get("agent_config")` from the GET at freya.py:57 |
| U4 | Does every PUT create a version, so the patch fires after each update and makes two versions? | api.md:103; freya.py:54, 60 | Compare the version count before and after one `update_workflow`, and log whether the line-60 PUT ran |
| U5 | Which routes need `workspaceId`, and is that the parameter name everywhere? (api.md:139 vs 107; freya.py skips it on the iterations list) | api.md:107, 122, 139, 176; freya.py:57, 61, 67, 105 | Normal `update_workflow` and `run_simulation` calls confirm the routes freya.py uses as written. For the personas list, one GET with `workspaceId` during normal use |
| U6 | Shape of the GET workflow result (`agentId`, `updatedAt` present?). Does it return the newest saved version or the published one? | api.md:127; freya.py:57, 67-68 | Run `export_workflow` after an update and check `agent_id` / `updated_at` for null. Compare the definition with the newest version from the versions list |
| U7 | Dry-run result fields. Does invalid input give a non-2xx status or `200 + success:false`? Does the response list stripped fields? | api.md:85, 87; freya.py:20, 48 | Run `validate_workflow` on the real candidate and on one with a known defect (for example a `null` value, workflow-format.md:64). Print the raw `freya.api(...)` output |
| U8 | Exact error status and text when a second simulation is created | freya.py:98 | When run_cases waits ("another simulation is running…"), log the caught exception's text in a local wrapper |
| U9 | Other simulation status values (`running` is known from README.md:103; any `queued` or `pending`?) and when `paused` happens | api.md:238; README.md:103 | Log `s.get("status")` on every poll during a normal run_cases run |
| U10 | Where `agentVersionNumber` sits (simulation, iteration or run) | api.md:115, 278-286 | Dump the `get_iteration` result and the simulation GET once after a normal run |
| U11 | Can a simulation have more than one iteration, and is `iterations[0]` the right one (list order)? | api.md:264; freya.py:106 | Dump the iterations list after a normal run |
| U12 | Full set of run `outcome` values (pass, fail, queued, running, others?). Does `successCriteriaResult` on the call always agree with the run's `outcome`/`reason`? | api.md:283, 290, 312; run_cases.py:96 | Compare `get_iteration` runs with `get_call(callId)["successCriteriaResult"]` for the calls of a normal run |
| U13 | Chat follow-up turns: is the body `{callId, message}` only, or are `workflowId` and `customerVariables` needed again? What does `/chat/end` return, and what happens if it is never called? | api.md:250 | One normal chat session: send turn 2 with `{callId, message}`. If rejected, add `workflowId`. Print the `/chat/end` result |
| U14 | Does chat execute `api_call` tools against the bank and appear in the practice ledger? Does chat really skip an initial code node? | api.md:252; prior L94 | One chat session on a fresh practice session's variables, then read that session's ledger with score.py's `http(...)`. Inspect `get_call(callId)` events for `node_enter` of the code node |
| U15 | Does `get_call` work for chat call ids, and does it carry the `system` events and `workflowSnapshot`? | api.md:304-334 | `freya.get_call(callId)` after a chat session |
| U16 | Is chat blocked while a simulation runs, and can chat sessions run in parallel? | api.md:242 ("no queue") | During a normal run_cases run, send one chat turn. Parallel chats: open a second chat session before ending the first, kept small to respect "no load-testing" (hackathon-page.md §Rules) |
| U17 | Does chat merge `test_variables` (is it a "web call")? What does the first assistant reply contain (opening line, or a reply to "Hello?")? | workflow-format.md:209, 234; api.md:242, 247 | Chat turn 1 with `customerVariables` that omit one key present in `test_variables`; inspect `variableTable` via `get_call`. Read `response` of turn 1 |
| U18 | After a 504 on a long chat turn, does the turn finish server-side so the `callId` stays usable? | api.md:252 | If a 504 happens in normal use, call `get_call(callId)` or send the next turn with the same `callId` |
| U19 | Is a query parameter needed to receive `workflowSnapshot`? | api.md:334 | Check whether `get_call` output from a normal run has `workflowSnapshot` on user/assistant messages |
| U20 | `endedReason` values beyond the terminal `function.name` and `customer-ended-call` (for example max duration reached, error) | api.md:310; README.md:100 | Tabulate `endedReason` over the calls of normal runs |
| U21 | Limits on `maxConcurrentCalls`, personas per simulation, `maxCallDurationSeconds`, `limit` above 100; other `mode` values | api.md:208-222, 288 | Not settleable without probing. Keep to kit defaults (5, 420 s, 100), check docs.freyavoice.ai when network use is allowed, or ask organisers |
| U22 | Persona limit and persona deletion (`.personas.json` grows with every style or text change) | api.md:141-176; run_cases.py:54-61 | Not settleable by normal use. Check docs.freyavoice.ai or ask organisers |
| U23 | Does PUT accept `name`? (the platform name stays `"<slot> MMDD-HHMMSS"` forever) | api.md:98; freya.py:46, 54 | Low value. Leave it |
| U24 | Does a 2xx `success:false` envelope ever occur? freya.py would miss it | api.md:30-42; freya.py:20 | Covered by U7: print the raw envelope on a failing dry run |
| U25 | Is the 120 s client timeout enough for every route (create/PUT of a big workflow, a chat turn)? A 504 suggests a gateway timeout below 120 s | freya.py:17; api.md:252 | Time each call in the builder's own trace during normal use |
| U26 | If the polling loop is interrupted, is the simulation still running on the platform (blocking the next one)? There is no cancel route | freya.py:97-104; api.md (no cancel route) | Observe whether the next `run_simulation` prints the "another simulation is running" wait after an interrupted run |
| C1 | Contradiction: api.md:115 says `save_workflow` publishes; on a create it does not | api.md:115; freya.py:45-46 | Settled by U1 |
| C2 | Contradiction: api.md:139 says the parameter name is not confirmed, while api.md:107 and freya.py use `workspaceId` | api.md:107, 139; freya.py:57, 61, 67 | Settled by U5. Normal `update_workflow` use confirms `workspaceId` on the two routes freya.py uses |
| C3 | Contradiction: api.md:127 says the reference client never calls GET workflow; freya.py does | api.md:127; freya.py:57, 67 | Settled by U6. A successful `update_workflow` shows the route works |
| C4 | Contradiction: api.md:44 asks for a bare-payload fallback on `workflow`; freya.py indexes `["workflow"]` directly | api.md:44; freya.py:33, 57, 67 | If create/update ever raise `KeyError: 'workflow'`, the fallback is needed. Otherwise moot |
| C5 | Contradiction: api.md:288 says `get_iteration` compares with `runsTotal`; it does not | api.md:288; freya.py:72-78 | After a normal run, check `len(out["runs"]) == out["runsTotal"]` |
| C6 | Tension: api.md:101 says a platform-filled `agent_config` is deleted on PUT; freya.py:55 says the platform fills one in | api.md:101; freya.py:55 | Settled by U3 |
| C7 | Internal: the `run_simulation` docstring says it returns 2 values; it returns 3 | freya.py:88, 106 | No experiment needed: the code returns 3 and run_cases unpacks 3 |

# base-agent — Corrections
The scope is PRIOR §11 (PRIOR:278-317), plus PRIOR:134, the one other line about the base agent. PRIOR:134 ("BA uses `Now: {{now}}`") is correct (BA:315), but only the `collection` node has the line. Claims not listed below were checked and are correct.

| # | Prior claim (PRIOR line) | Verdict | Correct statement, with citation |
|---|---|---|---|
| 1 | "the base agent passes 2/13" (278) | OVERSTATED | RM:34 says "in one run it passed 2 of the 13 practice customers". That is a single run, and RM:67 warns that "The same phone agent can pass a customer in one run and fail it in the next". No kit file says *which* two passed. [DOC] |
| 2 | Opening line is "Am I speaking with {{title}} {{last_name}}?" (284) | INCOMPLETE | The full tts text is "Hello, this is the digital assistant of Freya Bank. Am I speaking with {{title}} {{last_name}}?" (BA:105). Brief A rule 1 also requires saying "that the call is recorded" (BRA:24), and the base agent never says it. [CODE][DOC] |
| 3 | "Exit is deterministic: `verify_identity_response.data.all_verified` equals `"true"` OR `"True"`" (286) | OVERSTATED | Only the *evaluation* of the condition is deterministic (WF:292, WF:36). Whether the variable is ever set depends on two model calls: the model must call `verify_identity` and fill `field` and `answer` correctly, because both are model-filled (BA:35, BA:40; TC:85). A re-verify of an already-verified field once returned no `all_verified` key at all [PROBED-earlier, RAT:153]. The variable is an automatic flattened key (TC:264-277), not a `response_mapping`; BA's `response_mapping` is `[]` (BA:143). [CODE][DOC][INFERRED] |
| 4 | "The model ends the call by saying 'Have a good day.'" (287) | UNSUPPORTED by the docs | The only source is BA's own `end_call` tool description (BA:100). The `trigger_pattern` key (BA:86-89) appears in neither WF nor TC. PRIOR flags this later (302), but line 287 states it as fact. [CODE][DOC] |
| 5 | "The whole policy is in 4 lines of `task_message` with `Now: {{now}}`" (291) | OVERSTATED (minor) | The `collection` `task_message` has 5 newline-separated lines: 4 instruction lines and then `Now: {{now}}.` (BA:315). Policy also sits in the tool descriptions, for example "Call it once, before you say anything about the account." (BA:198) and "Call it only after the customer said yes to the read-back of amount and date." (BA:261). [CODE] |
| 6 | "`customer_id` is baked from the call variable" (296) | OVERSTATED | It is baked only when the call passes `customer_id`. `run_cases.py` does pass it (practice-session variables, RC:86-88; the session has `customer_id`, `first_name`, `last_name`, `title` and `now` [PROBED-earlier, RAT:126]). BA's own `test_variables` has **no** `customer_id` (BA:401-406). A call that does not pass one leaves `{{customer_id}}` unresolved. Per TC:85 the model is then asked for it on the node tools. On `close_call` it is dropped or model-filled, which is contested (TC:115 vs TC:561). [CODE][DOC][INFERRED] |
| 7 | "Per TC, one model call fills unresolved lifecycle parameters 'from the conversation'" (307) | UNSUPPORTED attribution | TC:561 says only: "If a `{{var}}` parameter is still unresolved, one model call fills the parameters." The words "from the conversation" come from BA's tool description (BA:393: "Record how the call ended, from the conversation."). TC does not say what that model call sees. [DOC][CODE] |
| 8 | "[U] Contradiction: WF §Variables says … dropped; TC §Lifecycle says one model call fills it. BA relies on the model-fill reading." (308) | INCOMPLETE | TC contradicts itself as well. TC:115 says an unset variable in a "Normal field in an engine-run call (`pre_actions`, lifecycle tool)" means "The field is dropped from the request". TC:561 says a model fills it. WF:202 matches TC:115. "BA relies on the model-fill reading" is [INFERRED]. Two things support it. First, BA writes model-facing descriptions on `outcome` and `reason` (BA:359, BA:370). Second, the reported pass (RM:34) needs a valid `outcome`: OAS:438-441 makes `outcome` required, and SC:20 compares it. If both fields were dropped, no case could pass. [DOC][INFERRED] |
| 9 | "`paid` hints that other briefs may have that outcome" (310) | WRONG | `paid` is a Brief A outcome: rule 39 "close as `paid`" (BRA:96) and the outcome table (BRA:111). It is also in the tool API enum (OAS:426). The real finding is that BA's `outcome` enum omits `paid` and `transferred` (BA:362-367 against OAS:424-431). The hook's `paid` branch (BA:395) can therefore only run if the filler ignores the enum. PUB-08 expects `paid` (PTS:336). [DOC][CODE] |
| 10 | close_call has "`outcome` (enum `promise`, `no_promise`, `not_verified`, `not_reached`)" (305) | INCOMPLETE (material omission) | This omits that the enum covers only 4 of the 6 outcomes in Brief A's table (BRA:108-115) and in OAS:424-431. It also omits that `reason` has **no** enum: it is a free string (BA:356-360). Its description names only 5 of the 15 reasons in the table: `refused`, `failed`, `declined`, `wrong_number` and `unclear` (BA:359). Missing are `hardship`, `dispute`, `service_error`, `callback`, `no_callback`, `deceased`, `restructuring`, `human` and `support`. [CODE][DOC] |
| 11 | "BA, which is an export" (314) | UNSUPPORTED | No kit file calls it an export. RM:34 and RM:46 call it "the same two-step workflow that is already in your workspace". `freya.export_workflow` writes a wrapper `{workflow_id, agent_id, updated_at, workflow}` (FP:68), and BA has no such wrapper. [INFERRED] It does look like a workflow object read back from platform storage. Every object except `test_variables` has its keys in PostgreSQL-`jsonb` order (shorter key first, then bytewise), which I checked with a local script. `test_variables` is in insertion order (`first_name`, `last_name`, `title`, `now`; BA:402-405). That suggests `test_variables` was added or edited by hand. [CODE][INFERRED] |
| 12 | "WF says `null` fails validation. Strip nulls before re-posting an export." (316) | OVERSTATED: a contradiction is missed | WF:64 does say "A `null` fails validation". But RM:23 tells you to post BA unchanged with `freya.save_workflow('base', json.load(open('examples/base-agent.json')))`, and RM:34 reports a run of it. BA has 4 nulls: `max_turn_transition` and `passthrough_default_transition` in both nodes (BA:145, 151, 320, 326). Either the platform accepts `null` in these two fields, or the README command fails. This is unresolved, see U2. Stripping the nulls is still safe advice. [DOC][CODE] |
| 13 | Undocumented keys: "`position`, `assertions`, node `interruptible`, `return_to_previous_on_interrupt`, `pre_actions:[]` on conversation nodes, `"mode":"exact"`" (315) | PARTLY WRONG and INCOMPLETE | `pre_actions` is a **documented** field. The docs say it is stripped from conversation nodes without an error (WF:82, TC:153, API:87). So it is a documented key in a stripped place, not an undocumented key. The list misses three things. (a) `trigger_pattern` (BA:86-89, BA:283-286): WF:639-646 lists only `message_mode`, `spoken_message`, `llm_prompt`, `interruptible`, `trigger_timeout` and `trigger_pattern_both`. (b) Using handler `__function__:end_call` as a model-callable tool inside a node's `tools` (BA:74, BA:271): TC:64 documents that handler only "in the `terminal` of an `end_call` node". (c) Node-level `response_mapping: []` on conversation nodes (BA:143, 318): WF:103 documents node-level mapping only "For `pre_actions` nodes". [CODE][DOC] |
| 14 | §11 as a whole ("what it is and why it is weak") | INCOMPLETE (major omission) | It never mentions that BA lacks three of the seven bank tools: `add_note`, `schedule_callback` and `transfer_to_agent`. RM:34 says "It uses four of the seven tools, so it handles only the simplest customers"; the seven are listed at OAS:15-470. Together with the 4-value outcome enum, this makes four public cases impossible on the ledger, whatever the model does (PUB-02, -09, -12, and practically -08; see §2.18). [DOC][CODE][INFERRED] |

**Count: 14 corrections.**

---

# base-agent — Uncertainties
Every experiment below uses only normal kit usage once an API key exists:
- `freya.save_workflow`, `freya.validate_workflow` (dry run, FP:48), `freya.export_workflow`
- `tools/run_cases.py … --out`, `freya.get_call(call_id)` (event log, API:296-336)
- the ledger read that `run_cases.py`/`score.py` already performs (SC:10-15, RC:93)
- `POST /api/v2/chat/message` (API:240-252)

None of them probes or load-tests the platform (HP:37).

| # | What is unknown or contradictory | Sources in tension | Experiment that settles it |
|---|---|---|---|
| U1 | Which 2 of 13 cases BA passed, and whether that is stable | RM:34 (one run, cases not named), RM:67 | Deploy as RM:23. Run `run_cases.py <agent_id> --brief A --out results/base-a.json`, then `--brief B`. Repeat with `--reps 3`. Read each FAIL reason against §2.18 |
| U2 | Whether `null` in `max_turn_transition` and `passthrough_default_transition` is accepted, and what the platform stores (it may fill `assertions`, `position`, `mode` and so on, and may drop `test_variables`) | WF:64 vs RM:23 and RM:34; API:87 (silent stripping) | `freya.validate_workflow('base-check', ba)` as-is, then with the nulls removed; compare. After `save_workflow`, run `export_workflow` and diff against BA |
| U3 | What happens to an unresolved single-placeholder field in a lifecycle tool: dropped, or filled by one model call | WF:202 and TC:115 vs TC:561 | After a BA run, read each case's ledger `calls[-1]` (`tool: close_call`, `args`); the ledger stores exact args [PROBED-earlier, RAT:140]. Also read `function_call_start` for `close_call` in `get_call(...)["messages"]`. An `outcome` that is present and varies by case means model fill |
| U4 | What the end-of-call filler sees (transcript? descriptions? `enum`?) and whether it is bound by the `enum` | TC:561 (silent on inputs), TC:85 (enum shown for node tools) | Check PUB-08's and PUB-09's `close_call` args from U1's run. An outcome outside BA's 4-value enum (`paid`, `transferred`) means the enum is not binding |
| U5 | Whether `pre_process_code` runs after the model fill, so that the `reason` pop takes effect | TC:395 (`config` = "the substituted request"), TC:561 | In promise cases (PUB-01, -10, -11), check that the ledger shows `reason` null. If any shows a filled reason with `outcome: promise`, the hook ran before the fill or did not run |
| U6 | `trigger_pattern` semantics: which speaker it matches, case sensitivity, regex or substring, interplay with `interruptible`, `trigger_timeout` 3 and `trigger_pattern_both` in a chat simulation | Undocumented (BA:86-89, BA:100); WF:644-654 covers terminals only and says the wall-clock window is not measurable in chat | Read `get_call` messages and `endedReason` for BA calls in which the agent said "Have a good day." Check whether the call ended right after that message or after a customer reply. In a chat session (API:240-250), drive the agent to its goodbye and see whether later `chat/message` turns are still answered |
| U7 | `endedReason` when a call ends through the `end_call` **tool** or phrase rather than an end_call node | WF:652 and API:310 cover end_call nodes only | `get_call(call_id)["endedReason"]` for the calls in U1 (RC:114 already records it as `ended`) |
| U8 | What `mode: "exact"` means and whether other values exist | Undocumented (BA:122, 128) | Save a workflow whose conditions omit `mode`, then `export_workflow`. If `"mode":"exact"` appears, it is the default. Other values cannot be learned without probing, so leave them unknown and never rely on them |
| U9 | Meaning and defaults of the node fields `position`, `assertions`, `interruptible` and `return_to_previous_on_interrupt` | Undocumented (BA:108-113, 141, 152) | Same save-and-export diff as U2 with these keys omitted. That shows the defaults, not the behaviour. Node `interruptible` probably concerns voice barge-in, which a chat simulation cannot test, so treat it as inert for scoring |
| U10 | Whether a later `verify_identity` response that lacks `all_verified` (the re-verify quirk) clears or keeps the earlier flattened key | RAT:153 [PROBED-earlier]; TC:279 ("Each call of the same tool overwrites the previous `_args` and `_response` values"), which does not say what happens to keys missing from the new response | Check PUB-12 (the phone question is retried) in `get_call` events. Read `route_evaluated.variable_table` after each `verify_identity` for `verify_identity_response.data.all_verified` |
| U11 | Whether `Now: {{now}}` is rewritten "for speech" when substituted (it is a string call variable that looks like a date), which would change what the model computes from | WF:200 | In a chat session that reaches `collection`, ask the agent to repeat the current date and time exactly as given to it. Compare with `2026-10-14T11:00` |
| U12 | How the PUB-10 fault appears to the workflow (HTTP 500 vs 200 `ok:false`), and whether `maxRetries: 0` means no engine retry | OAS "500 … may be repeated" (OAS:228-230); RAT:144 (business errors are 200 `ok:false`) [PROBED-earlier]; TC:53 | PUB-10 from U1's run: read `function_call_complete.result` for the first `create_promise`, the ledger's `failures` and `calls`, and count `create_promise` attempts per agent turn |
| U13 | Whether any built-in variable named `date`, `amount`, `answer`, `field` or `product_id` exists and would bake the field, hiding it from the model | TC:99; WF:582 (`date.*` placeholders resolve only in extraction prompts) | In U1's `get_call` events, check that the `create_promise` and `verify_identity` args vary with the conversation, and that `route_evaluated.variable_table` has no bare `date`, `amount` or `answer` key |
| U14 | Whether `identity`'s dialogue model can speak again after the second `verify_identity` result before the transition (which would give a double reply) | TC:291 says routing fires "before any further model turn" | In PUB-01's transcript, the event after the second `function_call_complete` should be `node_enter` `collection` and then the tts line, with no `identity` assistant message in between |
| U15 | Whether the judge fails brief violations that are not in a case's `checks`, such as a missing "call is recorded" | RC:47 (successCriteria = checks only); RM:63 ("against the checks listed for that customer"); hidden-case checks unknown (HP:27) | Partly: compare judge `reason` texts across U1 runs for any mention of unlisted rules. It cannot be settled for hidden cases, so satisfy every brief rule anyway |
| U16 | Whether `close_call` (`end_of_call`) still fires, and with what outcome, when the customer hangs up or the 420 s limit is hit | TC:521 ("After the call has ended"); FP:87 | Find U1 calls with `ended == "customer-ended-call"` (RC:114-117 prints them). Check that their ledgers still end with `close_call` |
| U17 | How the model sees the `end_call` node tool (zero parameters?) and whether calling it says anything with `message_mode: "none"` | TC:64 (terminal use only); WF:641 | Look for `function_call_start` with `function: end_call` in U1's events and the messages around it |
| U18 | What `customer_id` dashboard test calls use, given that `test_variables` has none | BA:401-406; HP:42 (a dashboard practice customer exists) | One dashboard test call, then `get_call` → `function_call_start` → `args.body.customer_id` for `verify_identity` |
| U19 | Whether `disable_inactivity_monitor: false` (silence check-ins) acts in chat simulations and could inject agent turns | WF:109, WF:115 (idle settings "matter on voice calls only") | Look for agent messages in U1 transcripts that no user turn prompted, after long customer pauses |

**Contradictions inside the base agent.** These are facts, so no experiment is needed. [CODE][DOC]
- The `pre_process_code` handles `outcome == 'paid'` (BA:395), but the `outcome` enum excludes `paid` (BA:362-367).
- The identity prompt answers "what is this about?" with a deferral (BA:140). Rule 15 counts that question as declining (BRA:44).
- BA ends calls without any `end_call` node, against WF:680 ("Every path must reach an `end_call` node").
- BA sets `max_node_turns` 80 with no `max_turn_transition`, against WF:672 ("Give every node that sets `max_node_turns` a `max_turn_transition`"). The cap therefore does nothing (WF:663).

**Count: 19 uncertainties** (U1-U19), plus the 4 base-agent contradictions above.

# briefs — Corrections
Every brief-related claim in `PRIOR` was checked against the sources. The claims below are wrong, overstated, unsupported or incomplete. The claims after the table were checked and are correct.

| # | Prior claim | Verdict | Correct statement |
|---|---|---|---|
| 1 | PRIOR:15: "The not-reached outcome is **probably** renamed in at least one hidden brief." | OVERSTATED | `score.py:33` accepts `("not_reached","no_contact","unreached")` for the "identity tools forbidden" check **[CODE]**. That shows only that the scorer tolerates other names. README:71 says final briefs have "another outcome table" **[DOC]**, so a rename is *possible*. Nothing makes it *probable*. |
| 2 | PRIOR:27: "Tool `config.maxRetries` **must** be 0." | OVERSTATED | No document says "must". tac:352 gives the `maxRetries` default as "not documented" **[DOC]**. tac:365 says "The working builder sets `maxRetries` to `0` on tools that write data and to `2` on its read-only `pre_actions` call. A retried write can record the same thing twice" **[DOC]**. Setting 0 on write tools is sound advice **[INFERRED]**, because A:91 allows exactly one retry, made by the agent. It is not a stated requirement. No public case fails `create_promise` twice: PUB-10 has `fail_first_n: 1` (PTS:438). |
| 3 | PRIOR:70: "An unreadable answer comes back `ok=false` and is not counted (from the API) [S]", applied to every identity answer. | OVERSTATED | OA:37 places that sentence inside the date-of-birth part of the `answer` description: "For date_of_birth: … An unreadable value is rejected with ok=false and is not counted as a wrong answer. For phone_last4: four digits." **[DOC]** A:40 likewise speaks only of dates: "The service rejects anything it cannot read as a date." The result for a malformed `phone_last4` (3 digits, letters) is **[UNCERTAIN]** (see U-9). |
| 4 | PRIOR:92: "Today is excluded from the count, verified by PUB-04 and PUB-13." | OVERSTATED (partly) | Only the late band (7th business day) is pinned by a case. PUB-04 expects 2026-10-23 (PTS:165). Counting today would give 10-22. PUB-13's loan (late band) also expects 10-23 (PTS:622). No public case separates the early-band answers. Counting from tomorrow gives 11-02 and counting today gives 10-30, and the early-band dates used in cases (PUB-07 10-27, PUB-13 card 10-30) are valid under both. "after today" (A:59-60) still supports excluding today for both bands **[INFERRED]**. |
| 5 | PRIOR:152 quotes "can you pay all of them today?" as if it were brief wording. | UNSUPPORTED (as a quote) | B:12 gives no fixed wording: "First ask whether the customer can pay all of them today." **[DOC]** Only A's sentence "Can you make this payment today?" (A:77) is verbatim. In B the ask is a content requirement. |
| 6 | PRIOR:205 (PUB-01): "second risk is leaking 'payment' **or 'account'** in the opening". | OVERSTATED | Rule 1 bans "collections", "debt", "payment" and the product (A:24) **[DOC]**. "Account" is not banned. A:44 even has the agent say, before verification, that the questions "protect their account" **[DOC]**. "Account" is a risk only toward a third party: A:31 says "Say nothing beyond the opening sentence", and the PUB-02 check is "does not say why it is calling" (PTS:88) **[DOC]**. The opening is the same for every listener, so keep it free of purpose words **[INFERRED]**. |
| 7 | PRIOR:230: "create_promise failures (**exactly** 2 tries)". | WRONG (wording) | A:91: "If it fails, try once more." **[DOC]** That means at most 2 tries per product. A second try happens only after a failure. |
| 8 | PRIOR:245: "'asks_back' asks 'which account is this about?' **during identity**". | OVERSTATED | run_cases.py:31: "twice in the call, before you answer, you ask a short question back … Whatever the caller replies, you then give your answer." **[CODE]** The question can come anywhere in the call. The clash with rule 15 arises only when it lands on a security question (see U-4). |
| 9 | PRIOR:244-248 lists speaking styles `talkative`, `corrects`, `pieces` and `asks_back`. | INCOMPLETE | A fifth style exists. `in_words` (run_cases.py:32, README:78): "you say every amount and every date in words and never in digits … Postcodes, years and other codes you say digit by digit." **[CODE]** It matters for date-of-birth and amount parsing. |
| 10 | PRIOR:33: "Currency is not stated in A or B [?]." | INCOMPLETE | The statement is true: neither brief names a currency. But the official page's example dialogue says "Your credit card has 420 dollars past due" and "420 dollars on Friday the sixteenth" (HP §Overview) **[DOC]**. Brief A's rule texts never require saying a currency (see U-25). |

**Checked and correct** (no action needed):

- The rule paraphrases in PRIOR sections B–Q, with the caveats above.
- The outcome table (PRIOR:167-174 matches A:108-115).
- All public-case dates: now Wed 2026-10-14, early deadline Mon 11-02, late deadline Fri 10-23, this Friday 10-16. These are recomputed in §2.1.
- The scorer facts at PRIOR:17-26, which match `score.py:19-33`.
- The PUB-12 attempt plan: the loan gets full on 10-16 then the floor of 440 on 10-23, the car loan gets 1 attempt, and two `refused` notes. This matches PTS:547-575 and A:79-81.

---

# briefs — Uncertainties
### About experiments

"Normal kit usage" means the following:

- `python3 tools/run_cases.py <agent_id> [--only ID] [--reps N] [--style S] [--cases file.json] [--out f.json]` (run_cases.py:3, 50).
- Reading transcripts with tool results through `freya.get_call(call_id)["messages"]` (README:99).
- Single agent turns through `POST /api/v2/chat/message` (README:101).

Limits on what experiments can show:

- The practice bank serves only PUB-01..13 (HP §FAQ). A custom `--cases` file must reuse a PUB id. The persona `script` can change, but the session's identity and products stay fixed.
- The local scorer uses *our* `expected` block and the judge uses *our* `checks`. Custom cases therefore reveal **mechanics** (what the API returns, what the agent does) but **cannot reveal the organisers' intended interpretation**.
- For pure interpretation questions, no experiment settles them. The entry says so, and gives the careful-reader default.

### The list

**U-1. How many times the floor is named (A:72 vs A:79).**

- **Unknown:** Rule 26 says "offer the floor, once", and only attempt 2 "may name the floor again". Yet attempt 1 is "for the floor if the customer already said the full amount is too much". The date of the rule 26 offer is unstated.
- **Two readings:**
  - (a) The single floor offer is made with the attempt-1 date ("637.50 by Friday 16 October; the rest stays overdue").
  - (b) The floor is offered for today, and on refusal attempt 1 names the floor again for Friday.
- **Evidence:** PUB-06 expects 637.5 on 10-16 (PTS:247-253), and its check says "minimum payment offered once" (PTS:260). That favours (a).
- **Default:** (a).
- **Settle:** build two variants, run `run_cases.py <id> --only PUB-06 --reps 3` on each, and compare the judge reasons for PTS:260.

**U-2. Borderline confirmations (A:26).**

- **Unknown:** whether "yeah", "yep", "mm-hm", a first name alone ("Daniel here") or a surname alone count as confirmation.
- **Default:** accept clear affirmatives and either name. Treat greetings and questions as non-confirmation.
- **Settle:** the public personas only "Confirm" plainly, so a custom script on PUB-01 ("answers the identity question only with 'Yeah.'") run with `--reps 3` shows how the agent behaves. Whether that is *correct* is not settleable by the kit.

**U-3. A customer question after the second ask (A:26).**

- **Unknown:** the rule gives no third ask. Must the agent close `unclear`, or answer and accept a later yes?
- **Default:** answer, and accept only an immediate clear confirmation in that same exchange; otherwise close `unclear`.
- **Settle:** interpretation only; no kit experiment decides it.

**U-4. Rule 15 vs the `asks_back` style.**

- **Contradiction:** A:44 says a second "what is this about" in place of an answer closes the call as `declined`. `asks_back` customers ask "why do you need that?" or "which account is this about?" twice, then answer (run_cases.py:31). The facts, and so the expected outcome, stay the same (README:78).
- **Default:** count a decline only on an explicit refusal, or on a question with no answer after the protective explanation. Answer the question, re-ask, and do not close while the customer is still engaging.
- **Settle:** run `run_cases.py <id> --brief A --style asks_back --reps 3` with the strict and lenient policies. Read the judge reasons and the ledger outcomes for cases where the question lands during identity.

**U-5. B closing: is any transfer an exception to "promise wins", or only restructuring?**

- **Unknown:** B:23 names only "rule 10", whose first sentences concern restructuring. A:117 says "If a transfer follows a recorded promise, close as `transferred` with that transfer's reason". It is not replaced by B, and B:18's last sentence covers "any transfer (restructuring, support, human)".
- **Default:** any transfer gives `transferred`.
- **Settle:** no public case combines a recorded promise with a support or human transfer. This is interpretation only.

**U-6. What a create_promise failure looks like (A:91).**

- **Unknown:** whether the PUB-10 fault (PTS:435-440) arrives as `ok:false` with an `error` string or as HTTP 500 (OA:229), and whether platform `maxRetries` would hide it.
- **Settle:** run `--only PUB-10 --out results/pub10.json`. Read the `create_promise` tool results in `freya.get_call(call_id)["messages"]`. The run's tool chain line also shows how many `promise` calls the ledger saw (run_cases.py:99).

**U-7. Is the swapped answer counted by the API? (A:42, OA:66)**

- **Unknown:** whether `wrong_answers_left` drops on a `day_month_swapped` answer. The brief says the retry does not count. The API's bookkeeping is not documented.
- **Settle:** use a custom `--cases` file reusing **PUB-11** (DOB 1987-06-03), with the script changed to "When asked your date of birth, first say it as numbers, month first: zero six, zero three, nineteen eighty-seven; when asked for the month as a word, say June." Run it once and read the `verify_identity` result in the transcript (`hint`, `wrong_answers_left`).

**U-8. Date-of-birth edge formats (A:40).**

- **Unknown:** two-digit years ("14/3/88"), missing years, and numbers-only dates that are impossible as day-month-year ("03/14/1988").
- **Default:** ask for the full date. Do not send impossible dates. Sending one is harmless (`ok:false`, not counted, OA:37), but it wastes a turn.
- **Settle:** a custom-script run on PUB-01 (DOB 1988-03-14) with the persona saying "fourteen, three, eighty-eight". Read what the agent sent and what came back.

**U-9. A malformed phone answer (OA:37, A:40).**

- **Unknown:** whether a 3-digit or 5-digit `phone_last4` is rejected without counting or counted as wrong. The "not counted" sentence sits under date of birth only.
- **Default:** never send anything but exactly 4 digits. Ask again instead.
- **Settle:** run `run_cases.py <id> --only PUB-12 --style pieces --reps 3` (numbers in two halves, run_cases.py:28). Inspect whether a partial answer was ever sent and the resulting `wrong_answers_left`.

**U-10. A callback "today" when today is not a business day (A:32).**

- **Unknown:** "today or the next business day" may or may not require today to be a business day.
- **Settle:** all public cases are Wednesdays (HP §Data), so the kit cannot settle it. This is interpretation only. The literal default allows today, if later than `now` and inside 10:00–19:00.

**U-11. Callback without an exact time, or a failed schedule (A:32-33).**

- **Unknown:** what to do with "tomorrow morning" with no hour, "I don't know when", or `schedule_callback` returning `ok:false`.
- **Default:** ask for a specific time once, and treat the answer like an offer under rule 7. With no time at all, close `no_callback`. On a failed tool call, retrying once is reasonable, but the rule does not say so.
- **Settle:** a PUB-02 custom script ("says she can be reached tomorrow morning", with no hour) shows the agent's behaviour. Correctness is not settleable by the kit.

**U-12. Week definition and bare weekdays (A:65, A:80).**

- **Unknown:**
  - whether the "calendar week" is Monday–Sunday or Sunday–Saturday (this changes "next Monday" said on a Sunday);
  - how to resolve a bare weekday ("on Friday") or a day number without a month ("the 30th").
- **Default:**
  - Monday–Sunday;
  - a bare weekday is the nearest one on or after today;
  - a day number is the next occurrence on or after today.
- **Settle:** interpretation only. Public cases are all on a Wednesday, where the readings agree.

**U-13. A weekend or holiday `now` (A:80).**

- **Unknown:** on a Saturday, "the last business day of this week" is in the past, and "If today is that day" does not fire.
- **Default:** use the last business day of next week.
- **Settle:** cannot be tested; all practice cases run on Wed 2026-10-14. Final cases run on "several calendar days" (README:76), so this matters.

**U-14. A past date, a refused next-business-day offer, a refused vague-deadline proposal (A:62-64).**

- **Unknown:** none of these responses is specified.
- **Default:**
  - a past date: say it has passed and ask for a day; this is not a refusal;
  - a refused offer from rule 20 or rule 21: treat it as a flat refusal (by analogy with A:66, A:72-73), which uses the next attempt.
- **Settle:** interpretation only.

**U-15. What a third party may hear (A:31).**

- **Unknown:** whether a sentence like "I can only discuss this with Ms Costa" breaks "Say nothing beyond the opening sentence".
- **Settle:** run `--only PUB-02 --reps 3` with and without such a sentence, and read the judge reasons for PTS:88.

**U-16. A third party asking for a human, or handing over the phone (A:36, A:99, A:102).**

- **Unknown:** rule 42 "applies before and after verification", but its scope ("the same customer", A:102) suggests the customer. A phone handover is not covered at all.
- **Default:**
  - a third party asking for a human: no transfer; ask when the customer can be reached;
  - a handover: restart at rule 2.
- **Settle:** interpretation only.

**U-17. An amount above `past_due`, and a second floor offer (A:72-73).**

- **Unknown:**
  - how to handle a proposal above the full amount;
  - whether rule 27's "offer the floor once" is a separate allowance from rule 26's "once";
  - whether offering the floor during hardship counts as persuasion.
- **Default:**
  - above full: offer to record the full past-due amount;
  - the floor is named at most once outside attempt 2;
  - during hardship, record only what the customer names if it is valid. If the named amount is below the floor, say it cannot be recorded and do not push.
- **Settle:** interpretation only.

**U-18. Hardship mentioned before verification (A:83).**

- **Unknown:** rule 32 sits in §9, after the debt statement.
- **Default:** say one sympathy sentence and continue the identity check. The support offer and outcome logic apply only once verified, though the rule does not say so.
- **Settle:** interpretation only.

**U-19. Hardship in Brief B (A:83, B:16-17).**

- **Unknown:** B9 says only dispute and paid "do not end the call". Hardship is about the customer, not a product. Open questions:
  - Does a declined support offer end the call, with every product noted `hardship`?
  - Or does the agent continue with the other products, which seems to contradict "make no persuasion attempt"?
- **Default:** no persuasion on any remaining product, a `hardship` note on each product without a promise, and close `no_promise`/`hardship` unless a promise exists.
- **Settle:** interpretation only.

**U-20. The text-message sentence in B (A:92, B:15).**

- **Unknown:** whether to say it once after all creates or once per promise ("this promise" is singular).
- **Default:** once, after all creates succeed. If some failed, say it for the recorded ones and say which product could not be recorded.
- **Settle:** run `--only PUB-11 --reps 3`. Its checks (PTS:505-507) do not mention the sentence, so the judge may not test it. That makes the result weak evidence.

**U-21. Does B6 replace A23's offer-and-refuse flow? (A:66, B:14)**

- **Unknown:** in B, with one date for everything, whether the agent should *offer* the deadline (A23, refusable) or simply *record* it and say so in the read-back (B6).
- **Default:** state the clamp before the read-back and repeat it in the read-back. If the customer rejects the clamped date at the confirmation, handle it as a change under rule 35, then as A23's flat refusal.
- **Settle:** run `--only PUB-13 --reps 3` and read the judge reasons for PTS:632.

**U-22. B: some products today, others not (B:12).**

- **Unknown:** "If not, go through the products one by one" does not cover a partial yes.
- **Default:** record the products the customer will pay today as promises for today. Loop over the rest from attempt 1.
- **Settle:** interpretation only.

**U-23. `days_late` outside 1–45, and titles other than Mr/Ms (A:9, A:19, A:57-60).**

- **Unknown:** no band is defined outside 1–45.
- **Default:** use the nearest band, and log a warning in the builder.
- **Settle:** interpretation only. No public case has such data.

**U-24. When B notes are written (B:16-18).**

- **Unknown:** the timing of notes. The ledger compares only sets (score.py:23-24).
- **Default:** write them at the end, just before `close_call`, and never when a transfer happened. This is forced by B:18's "before or after it".
- **Settle:** run `--only PUB-12 --reps 3`. A pass with deferred notes confirms the judge accepts it.

**U-25. The currency word when speaking amounts.**

- **Unknown:** the briefs never name a currency. The official page's example says "dollars" (HP §Overview).
- **Default:** say the amount with "dollars", or with no unit. Never another currency.
- **Settle:** read the judge reasons on any run for complaints. Weak evidence; interpretation otherwise.

**U-26. Reason values for promise and paid (A:106, OA:435, score.py:19-20).**

- **Unknown:** whether sending `reason: ""` or `"paid"` is stored and so fails the exact tuple match.
- **Default:** omit the field, as the example agent does (base-agent:395).
- **Settle:** a normal `--only PUB-08` run with the field omitted should pass. Do not experiment with sending junk reasons.

**U-27. The not-verified closing after a not-confirmed refusal (A:26, A:102).**

- **Unknown:** whether a person who never confirmed identity but says twice "I don't want to talk" is `not_reached`/`unclear` or `not_verified`/`declined`.
- **Default:** `unclear` if they never confirmed; `declined` if they confirmed. This follows "the same customer" at A:102.
- **Settle:** interpretation only.

**U-28. Early-band deadline counting (A:59).**

- **Unknown:** no public case separates 11-02 (today excluded) from 10-30 (today included).
- **Default:** exclude today, per "after today" and the late-band evidence (PUB-04, PUB-13).
- **Settle:** interpretation only. A custom PUB-07 script naming "Monday the 2nd of November" would show agent behaviour, but our own `expected` block decides the local score.

# harness — Corrections
The prior summary is mostly accurate about `run_cases.py` and `score.py`. Below are the claims that are wrong, overstated, unsupported or imprecise. Items marked *adjacent* concern files next to my sources (`freya.py`, `tools/openapi.json`, the page), and they matter for how the harness behaves.

| # | Prior claim (line) | Verdict | Correct statement | Citation |
|---|---|---|---|---|
| 1 | L186: "`run_once` creates a fresh practice session per case per rep" | IMPRECISE (understated) | A session is opened per case on every call to `run_once`. That means per **attempt**, including attempts that `--rerun-if-slow` later throws away. Sessions are opened *before* the simulation is created, so they are used up even if the simulation then waits in the queue or fails. | `tools/run_cases.py:66-67`, `:86-88` [CODE] |
| 2 | L193: "`--rerun-if-slow K` throws away a run whose median slowest agent turn is over 10 s and repeats it after 5 min" | OVERSTATED / incomplete | Details below the table. | `tools/run_cases.py:66-70`, `:116`, `:119` [CODE] |
| 3 | L208: "`--style` applies to all cases in a run. A cases file can also set `style` per case … so styles can be mixed in one simulation" | IMPRECISE | Details below the table. | `tools/run_cases.py:45-46`, `:50` [CODE]; `public-test-set.json` [CODE] |
| 4 | L52: "`save_workflow(slot, wf)` keeps slot → `{workflow_id, agent_id, version}` in `.freya-agents.json`" (*adjacent*; SKILL step 5 depends on it) | OVERSTATED | Details below the table. | `freya.py:36-47` [CODE] |
| 5 | L136: "`hinted` (meaning unknown) [UNVERIFIED]" (*adjacent*) | UNSUPPORTED ("unknown") | The tool API documents a `verify_identity` response field `hint` whose only allowed value is `day_month_swapped`. Brief A rule 13 explains it: "If the customer gives day and month the other way round, `verify_identity` returns `hint: "day_month_swapped"` … That retry does not count as a wrong answer." The ledger's `hinted` almost certainly records that hint [INFERRED]. | `tools/openapi.json:72-77`; `briefs/brief-a.md:42` [DOC] |
| 6 | L144: business errors come back as HTTP 200 with `ok:false`; "The only exceptions are `unknown customer_id` (404) and the key errors (401)" (*adjacent*) | OVERSTATED | Details below the table. | `tools/openapi.json:83-84`, `:167`, `:229`, `:293`, `:349`, `:404`, `:466` [DOC]; `public-test-set.json` (PUB-10 `faults`) [CODE] |
| 7 | L297-299: "run reps inside **one** simulation by creating three differently named personas per case, each with its own session" | UNSUPPORTED as a drop-in | Details below the table. | `tools/run_cases.py:52-62`, `:86`, `:88`, `:90` [CODE] |
| 8 | L246: "It costs one `curl` to check the openapi `servers` URL and enums at build time." | UNSUPPORTED, and conflicts with the rules | Each hidden brief arrives with its own tool API file, so the servers URL and the enums can be read from that local file with no network call. Extra calls to the platform or bank to "check" things go against the rule quoted below the table. | README.md:72 [DOC]; page §Submit, §FAQ, §Rules [DOC] |
| 9 | L275: "Multiple workspaces … [UNVERIFIED and possibly against the spirit of the rules]" | UNDERSTATED | The page says it directly. Using more than one workspace is against the stated rules, not just their spirit. | page §Rules; page §Evaluation [DOC] |

**Detail for #2 (`--rerun-if-slow`):**
- It repeats at most **K** times, and the last (K+1-th) attempt is always kept, even if it is still slow: `if med <= 10 or attempt == a.rerun_if_slow: break`.
- The test is strictly `med > 10`, where `med` is the **upper** median: `waits[len(waits)//2]`.
- If no call transcript could be fetched, `med` is `0` and the run is never thrown away.
- The PASS/FAIL lines of a thrown-away attempt are already printed. That attempt does not count, and its time is left out of the reported total. The total adds only the kept attempt's `took`.
- The organisers' comment is quoted correctly: "organisers: a run made while the model was slow is thrown away and repeated".

**Detail for #3 (`--style`):**
- A CLI `--style` **overrides** every per-case `style`, because the code is `style = style or case.get("style")`. Mixing styles works only when `--style` is *not* passed.
- A per-case `style` must be one of the five keys, or `STYLES[style]` raises `KeyError`. Argparse `choices` only checks the CLI value.
- No public case has a `style` key, and none has a `third_party` key.

**Detail for #4 (`save_workflow`):**
- The first save of a slot stores only `{workflow_id, agent_id}`, which is what `create_workflow` returns.
- `version` is added only on a later save, through `update_workflow`.
- The state file `.freya-agents.json` is resolved against the **current directory**, while `.personas.json` is fixed at the kit root (`tools/run_cases.py:54`).

**Detail for #6 (HTTP status of failures):**
- `tools/openapi.json` declares a `500` response for every one of the seven tools: "The service failed. Nothing was recorded. The call may be repeated."
- The earlier probes touched PUB-01 and PUB-11 only (prior L5). They never exercised the PUB-10 failure injection (`faults: [{"tool":"create_promise","fail_first_n":1}]`).
- So an injected failure may arrive as HTTP 500, not as 200 with `ok:false`. This is [UNCERTAIN] (U4).

**Detail for #7 (three personas per case in one simulation):**
- `run_cases.py` maps each case id to exactly **one** persona id: `ids = {c["id"]: ids[key[c["id"]]] ...}`.
- It opens one session per case id with `{"case": c["id"]}`.
- It reads one judge verdict per persona: `{r["personaId"]: r ...}`.
- A cases file cannot hold three copies of a PUB id, because the dict by id collapses them. A new id would be refused by the bank: "unknown practice case" [PROBED-earlier].
- So the idea needs a modified harness.
- It also tests at concurrency 15 instead of three sequential runs of 5. That changes the latency conditions that the median-slowness check watches [INFERRED].

**Rule quoted in #8:** "Do not probe or load-test the platform." (page §Rules)

**Rules quoted in #9:**
- "One Freya key per team." (page §Rules)
- "a team has one workspace" (page §Evaluation)

**Omissions in the prior summary (not counted as corrections, but needed for completeness):**
- The persona cache key is the first **10** hex characters of the sha1 of `json.dumps(spec, sort_keys=True)`. The spec is `{name, prompt, successCriteria, tags}`, so changing a case's `title`, `checks`, `brief`, `identity` or `script` also makes a new persona. Old personas are never deleted. The cache is not keyed by API key or workspace (`tools/run_cases.py:54-62`).
- A missing judge verdict counts as a failure: `"conversation: no verdict"` (`tools/run_cases.py:96`).
- `run_simulation` polls with **no overall timeout**. A simulation stuck at "running" hangs `run_cases.py` forever (`freya.py:101-104`; README.md:103).
- The case fields `products`, `faults`, `variables.title` and `variables.now` are never read by the harness (§2.3.3).
- The summary says nothing about `agent_builder.py` beyond the trace path (§2.6).
- The persona is given no amounts, products, card digits or date (§2.3.4).

---

# harness — Uncertainties
Each item says what is unknown and an experiment that would settle it, using normal kit usage once an API key exists. That means `run_cases.py`, the `score.py` CLI, `freya.get_call`, `--out` files, the example builder, or chat as documented. No probing.

| # | Unknown or contradiction | Experiment that would settle it |
|---|---|---|
| U1 | Whether the judge sees tool events or only spoken words. Several checks are about tool calls ("verify_identity and get_account never called", "create_promise called exactly once"). | After a normal run with `--out`, compare a failing run's `reason` with `freya.get_call(call_id)` (`transcript` against `messages`). See whether the judge cites tool calls that were never spoken. |
| U2 | How the customer model knows "today" or weekdays. The persona gets no date (§2.3.4). | Run PUB-04 and PUB-07 with `--out` and read the transcripts. See whether the customer ever states or checks a weekday, and how it answers "what day suits you". |
| U3 | What the ledger stores as `reason` when the agent sends `""` or no reason for `promise` or `paid`. This affects check 1. | After a normal PUB-01 run, run `python3 tools/score.py PUB-01 <customer_id>` on that run's customer and read the outcome line. Then check the `close_call` arguments in `freya.get_call(...)`. |
| U4 | For an injected failure (PUB-10), whether the tool returns HTTP 500 (as `tools/openapi.json` documents) or 200 with `ok:false`. Also what the ledger's `calls[].result` looks like then. `score.py` assumes a dict. | Run `--only PUB-10 --out ...`. Read the `function_call_complete` event in `get_call` and the ledger through the `score.py` CLI. |
| U5 | Whether calls made after `close_call` are recorded in the ledger. If they are, check 6 fails the case. | Look at an existing failing transcript whose agent spoke or acted after closing, and read that case's ledger through the `score.py` CLI. |
| U6 | The `endedReason` value when a call hits `maxCallDurationSeconds` 420, and whether the `customer-ended-call` count includes it. | Read the `ended` field over several `--out` files. |
| U7 | How many reruns the organisers allow for slow runs (their K), and whether their threshold is the same `> 10` s upper median. | Not settleable by experiment. Ask the organisers, or treat it as fixed and keep the median well under 10 s. Measure it from `--out` rows (`slowest_turn_s`). |
| U8 | Whether the final uses per-case mixed styles, `third_party`, the four extra identity templates and the alternate outcome names (§2.10). | Not settleable before Sunday. Practise with each `--style` and with a custom cases file that sets `style` per case, without `--style` (§2.3.3). |
| U9 | Whether the official judge has the same model and `successCriteria` format as `run_cases.py`. | Not settleable. Inferred from `freya.py:85` and README.md:63. |
| U10 | **Contradiction.** README.md:74 says "You run your builder once on each", while README.md:89 and page §Submit say "You may run it more than once and submit the phone agent of one run, with that run's trace". | The later, more specific text (README.md:89, page §Submit) allows several runs. Confirm with the organisers if it matters. |
| U11 | **Contradiction.** The example builder takes only brief paths, and the skill always reads `tools/openapi.json`. The final gives each brief its own tool API file, and the submission `run_command` is `python3 builder/build.py {brief_path} {tool_api_path}`. Passing the tool API path to `agent_builder.py` would put it in the prompt as a "brief". | Run `examples/agent_builder.py briefs/brief-a.md tools/openapi.json` and read the trace to see how Claude interprets it. Our own builder should take both arguments explicitly. |
| U12 | **Contradiction.** README.md:29 says to pass both briefs for B. The skill's step 6 says "use `--brief B` when you were given Brief B", which tests only PUB-11..13 and never the 10 A-only customers. The slot name with two briefs ("the brief's file name") is ambiguous. | Run `examples/agent_builder.py briefs/brief-a.md briefs/brief-b.md` and read the trace for the slot name and the `run_cases` arguments used. |
| U13 | Whether the example builder fits the 30-minute limit. The skill allows 1 + 3 test runs of 3-11 minutes each, and README v3 reports a 10/10 run but no duration. | Run the example builder once and read `done: … s` (the `ResultMessage` `duration_ms`). |
| U14 | Whether the example trace meets README.md:91. It has no explicit end time and no one-line purpose per model call. | Read a produced `traces/*.jsonl`. Our builder should write these fields explicitly. |
| U15 | **Inexact README wording.** README.md:100 says `run_cases.py` "prints the slowest agent turn per call". The code prints only the median and worst over calls. The per-call value is saved only in `--out` rows (`tools/run_cases.py:114`, `:117`). | No experiment needed: it is code. |
| U16 | Whether `ClaudeAgentOptions(skills=[...])` exists in the installed `claude-agent-sdk` version. README v3 implies the example ran. | `pip install claude-agent-sdk` (the README step) and run the example builder once. |
| U17 | Persona-template risk. Every customer's date-of-birth sentence contains the example `'14 March 1988'` (PUB-01's real DOB) beside the ISO value. A customer might occasionally say the example date. | Look across many `--out` transcripts for identity failures on cases other than PUB-01 where the customer said "14 March 1988". |
| U18 | Decoy overlap. The `talkative` decoy "wedding on the 30th" collides with PUB-13's real wish to pay "on 30 October". It is unclear how the customer model resolves this. | Run `--only PUB-13 --style talkative --reps 3` and read the transcripts. |
| U19 | Whether a persona limit exists, since `.personas.json` and Freya personas only ever grow. | No experiment. Watch for an error from `create_personas` during normal runs, and reuse personas: only change the text when needed. |
| U20 | **Inexact docstring.** `run_simulation` says it returns `(simulation_id, iteration_id)` but returns three values including `status` (`freya.py:88`, `:106`). | No experiment needed: it is code. |

# openapi — Corrections
### 1.1 Claims that are wrong, overstated or unsupported

There are 8 corrections. Two of them (C4 and C7) are minor.

**C1. `read-rules-and-cases.md:185`: "Every POST returns `{ok, error, ...}`."**
- **Verdict:** OVERSTATED.
- **What the file says:**
  - Every 200 schema lists `ok` (boolean) and `error` (string) as properties: L57–62, 118–123, 214–219, 280–285, 336–341, 391–396, 453–458.
  - No response schema has a `required` array, so the schema guarantees no field at all.
  - The 500 responses have no `content` or schema at all: L83–85, 166–168, 228–230, 292–294, 348–350, 403–405, 465–467. [DOC]
- **Probe evidence:**
  - Earlier probes saw `verify_identity` results with no `error` key.
  - One re-verify result had no `all_verified` key. [PROBED-earlier]
- **Correct statement:** a 200 body may carry `ok`, `error` and tool-specific fields, and every one of them is optional per the schema. Expect `error` only when `ok` is false [INFERRED]. A 500 body is undocumented.

**C2. `read-api-and-testing.md:144`: "Business errors come back as HTTP 200 with `ok:false`. The only exceptions are `unknown customer_id` (404) and the key errors (401)."**
- **Verdict:** OVERSTATED and incomplete.
- **What the file says:**
  - Every tool documents exactly two responses: 200 ("`ok` is false when the action was not carried out.", L51 and repeated) and 500.
  - The 500 text, on every tool, is "The service failed. Nothing was recorded. The call may be repeated." (L84, 167, 229, 293, 349, 404, 466). [DOC]
- **Why the claim misses the 500:**
  - The probes touched only PUB-01 and PUB-11 (`read-api-and-testing.md:5`).
  - Neither case has `faults`. Only PUB-10 does: `public-test-set.json:435–438`, `{"tool":"create_promise","fail_first_n":1}`.
  - So the probes could never have seen a 500.
- **The 404 and the 401:**
  - The 404 for an unknown `customer_id` is real [PROBED-earlier], but the file does not document it.
  - A 401 cannot come from a tool call. "The seven tool calls need no key" (L6). The 401 belongs to `/v1/practice/*`, which are not in this file.
- **Correct statement:** the file documents two outcomes, 200 (check `ok`) and 500 (nothing recorded, safe to repeat). A 404 for an unknown `customer_id` also happens but is undocumented.

**C3. `read-rules-and-cases.md:70`: "An unreadable answer comes back ok=false and is not counted (from the API) [S]."**
- **Verdict:** OVERSTATED in scope.
- **Where the sentence sits:** inside the `date_of_birth` instruction of the `answer` description (L37):
  > For date_of_birth: the date as YYYY-MM-DD. Callers say dates in words, the agent converts. An unreadable value is rejected with ok=false and is not counted as a wrong answer. For phone_last4: four digits.
- **Probe evidence:** for `phone_last4`, the spoken answer `"two two eight eight"` was **counted as wrong** [PROBED-earlier].
- **Correct statement:** only an unreadable **date** is documented as rejected and not counted. A malformed phone answer can use up an attempt, so normalise it to exactly 4 digits before calling.

**C4 (minor). `read-api-and-testing.md:150`: "The bank accepted '14 March 1988' and '3 June 1987' as verified, even though the openapi says YYYY-MM-DD."**
- **Verdict:** wrong framing. There is no contradiction.
- **What the sources say:**
  - L37 tells the agent to send YYYY-MM-DD. It says only an *unreadable* value is rejected.
  - `briefs/brief-a.md:40` agrees: "The service rejects anything it cannot read as a date."
- **Correct statement:** leniency on readable non-ISO dates fits the docs. The advice to always send ISO stands.

**C5. `read-api-and-testing.md:161`: "The bank does not enforce the brief: it accepts holiday dates, dates past the deadline, any amount."**
- **Verdict:** partly OVERSTATED.
- **What is stated:**
  - L6 states the holiday and deadline cases: "it records a promise on a holiday or past the deadline without complaint".
  - `hackathon-page.md §Evaluation` adds "below the minimum". [DOC]
- **Why "any amount" goes too far:** only 99999 (above `past_due`) and the string `"220"` were probed [PROBED-earlier]. Zero, negative and non-numeric amounts are untested.
- **What the bank does enforce:**
  - Identity before `get_account`: "Refused until both questions are passed." (L91).
  - One promise per product: "One per product." (L174).
  - Nothing after `close_call`: "Nothing is accepted after it." (L411).
  - The pairing of outcome and reason [PROBED-earlier].
- **Correct statement:** the bank enforces data validity and some table consistency, but not dates or amounts against policy.

**C6. `read-rules-and-cases.md:197`: "Product ids are `p1..pN` in `get_account` order", given under "Tool API (openapi 0.3-draft)".**
- **Verdict:** UNSUPPORTED by this file.
- **What the file says:** L129–131 declares `product_id` as a plain `string`, with no pattern, example or ordering note.
- **Where the claim comes from:**
  - The id form comes from `README.md:102`: "Product ids come from `get_account` (`p1`, `p2`, ...)" [DOC].
  - The probes also saw it [PROBED-earlier].
  - "In `get_account` order" is inferred from `public-test-set.json` (the expected `p1/p2/p3` follow the listed product order) [INFERRED].
- **Correct statement:** a hidden bank may use other ids. Always copy ids from the response.

**C7 (minor). `read-rules-and-cases.md:27`: "Tool `config.maxRetries` must be 0."**
- **Verdict:** OVERSTATED as a rule. It is a sound recommendation.
- **What the sources say:**
  - No source requires it.
  - `docs/tools-and-code.md:365` reports that a working builder used 0 on write tools.
  - `docs/tools-and-code.md:352` defines `maxRetries` only as "Tool-level retries after a failed response". Whether a 500 or an `ok:false` counts as "failed" is undocumented.
- **How the pieces fit:**
  - Per L84 and the other 500 descriptions, an automatic retry after a 500 would not duplicate a record.
  - It would, however, hide failures from the brief's count of two attempts (`briefs/brief-a.md:91`).
- **Correct statement:** set it to 0 on write tools so the agent counts failures itself (recommendation).

**C8. `read-api-and-testing.md:246`: "It costs one `curl` to check the openapi `servers` URL and enums at build time."**
- **Verdict:** WRONG method.
- **What the sources say:**
  - The hidden tool API arrives as a **file**:
    - `hackathon-page.md §Submit`: "each with its own tool API file".
    - The run command takes `{tool_api_path}`. The page's example is `briefs/hidden-1.openapi.json`.
    - `hackathon-page.md §FAQ`: "its own tool API file next to it".
  - Calling the bank to inspect it would be probing: `hackathon-page.md §Rules`, "Do not probe or load-test the platform."
- **Correct statement:** read `servers[0].url` and the enums from the supplied file. No network call is needed.

### 1.2 Prior claims checked and found correct

| Prior claim | Check |
|---|---|
| Server `https://freya-bank-mock.freyavoice.workers.dev/v1`, no auth, `customer_id` is the secret (`read-rules:185`) | L10, L6, L13 (`components` is empty; no security). L6 says "the secret of **one call**". |
| A 500 means nothing was recorded and the call may be repeated (`read-rules:185`) | L84 and the other 500 descriptions. |
| `verify_identity` request and response fields and enums (`read-rules:189`) | L25–44 and L57–77. |
| `get_account` is refused until both questions pass; product fields and "cards only" / "loans only" (`read-rules:190`) | L91 and L129–157. |
| `create_promise` fields, `date` has `format: date`, returns `promise_id` (`read-rules:191`) | L182–201 and L220–222. |
| `add_note` reason enum; `text` optional (`read-rules:192`) | L250–268. `text` is not in `required`. |
| `schedule_callback` time is "HH:MM" (`read-rules:193`) | L315–318. |
| `transfer_to_agent` queue enum (`read-rules:194`) | L367–379. |
| `close_call` outcome enum of 6; `reason` is a free string required except for promise and paid (`read-rules:195`) | L422–441. |
| `api_call` "success" does not mean `ok:true`; branch on `ok` (`read-api:145`) | Follows from L51 [INFERRED]. |
| `FREYA_BANK_HOST` defaults to the mock host; the tool base path is `/v1` (`read-api:119`) | `tools/score.py:7` and L10. This variable affects only the scorer and `run_cases`, not the agent's tool URLs [CODE]. |
| `get_account` before verification fails the case even if the agent later retries correctly (`read-api:154`) | `tools/score.py:31–32` scans every call [CODE]. |

### 1.3 Material the prior summaries left out (now covered in §2)

- **The 500 response is missing from both tool tables.** The table in `read-rules` §2 has no error column. The table in `read-api` §2 omits the 500 entirely.
- **Policy text in `summary` strings is not carried over.**
  - "Three wrong answers in total end the check." (L17)
  - "Refused until both questions are passed." (L91)
  - "One per product." (L174)
  - "Brief B: record why a product ended without a promise." (L236)
  - "Always the last tool call. Nothing is accepted after it." (L411)
- **Policy text in `info.description` (L6) is not carried over.**
  - "Every call is written to the ledger the scorer reads."
  - "the secret of one call"
- **`reason` is not in `close_call`'s `required` array** (L438–441), even though its description makes it conditionally required.
- **The response tables omit fields.**
  - The `get_account` row omits `ok` and `error`.
  - The `create_promise` row omits `ok` and `error`.
- **Mapping trap:** the transfer queue `general` corresponds to the close reason `human`, not to a reason called `general`.
- **Leading zeros:** `card_last4` and the phone answer are strings, and leading zeros matter.
  - `public-test-set.json:63`: phone `"0358"`.
  - `public-test-set.json:112`: card `"0377"`.

---

# openapi — Uncertainties
**How to run the experiments**
- Each experiment below uses normal kit usage once a Freya key exists:
  - `tools/run_cases.py` with `--only` or a custom `--cases` file that reuses a PUB id. That fixes the bank customer and its faults, while the script and checks can change.
  - The chat route `POST /api/v2/chat/message` with a practice-session `customer_id`.
  - `freya.get_call(call_id)["messages"]`, where `function_call_complete` events show the envelope.
  - The ledger read `python3 tools/score.py <case> <customer_id>`, or `score.http("/v1/practice/ledger/<cid>")`. The ledger's `calls[{n, tool, args, status, result}]` shows exactly what was sent and returned.
- No experiment needs direct calls to the tool endpoints.
- Several experiments fit into one simulation through a custom cases file.

**U1. How a 500 looks inside Freya.**
- *Unknown:*
  - The body of a 500 (the file has no schema).
  - Freya's envelope for it: the `status` value, whether `data` is set, and `status_code`.
  - Whether `<tool>_failure_count` goes up.
  - Whether `config.maxRetries` re-sends on a 500 or on `ok:false`.
- *Why it matters:* every failure route depends on this. `docs/tools-and-code.md:352` defines `maxRetries` only as "retries after a failed response".
- *Experiment:* run PUB-10 (`fail_first_n: 1` on `create_promise`) with a post-hook that copies `result["status"]`, `result.get("status_code")` and `result.get("data")` into `result["data"]["debug"]`. Then read the `function_call_complete` event and the variable table in `get_call`. Run once with `maxRetries: 0` and once with `1`, and compare the ledger `calls[]` count for `create_promise`.

**U2. How the kit injects faults.**
- *Unknown:* whether PUB-10's injected failure is an HTTP 500 (as the file's 500 text suggests) or an HTTP 200 with `ok:false`, and what its error string is.
- *Why it matters:* the hidden cases will likely inject failures the same way, possibly on other tools.
- *Experiment:* the same PUB-10 run. Read the ledger's `calls[0..]` entries for `create_promise` (`status`, `result`) and the `failures` counter.

**U3. Contradiction: "Every call is written to the ledger" (L6) against "Nothing was recorded" (L84).**
- *Reading that reconciles them* [INFERRED]: the call log `calls[]` records every call, but no business record (promise, note and so on) is made on a 500.
- *Also unknown:* whether calls made *after* `close_call` (rejected with "the call is already closed") still go into `calls[]`. If they do, `score.py:29`'s `calls[-1]["tool"] == "close_call"` check fails.
- *Experiment:*
  - In the PUB-10 ledger, check that the failed attempt appears in `calls[]` but not in `promises`.
  - For calls after close, use a throwaway test workflow in a spare slot that calls `close_call` and then `add_note`, run it on one practice session through chat, and read `calls[]`.

**U4. `verify_identity` at the limit.**
- *Unknown:*
  - What the third wrong answer returns: `ok` true or false? `verified: false` with `wrong_answers_left: 0`? An `error` string?
  - What any later call returns, including a correct answer after the limit.
- *Experiment:* run PUB-03 normally (three wrong DOBs) and read each `verify_identity` entry's `result` in the ledger. For later calls, add a custom-case variant of PUB-03 whose script gives the right DOB as a fourth answer, with an agent that keeps asking, such as `base-agent.json`.

**U5. `hint: "day_month_swapped"` semantics.**
- *Unknown:*
  - Whether the swapped answer itself reduces `wrong_answers_left`.
  - Whether `verified` is false and `ok` is true.
  - Whether the hint fires more than once (the ledger has a `hinted` field [PROBED-earlier] whose meaning is unknown).
  - What a "swapped" date that is not valid returns.
- *Experiment:* use a custom case on PUB-07, DOB `1975-12-05` (`public-test-set.json:277`). The script gives the DOB as numbers only, "twelve, five, nineteen seventy-five", which reads D-M-Y as 12 May 1975 → `1975-05-12`. When asked for the month as a word, the persona says "5 December 1975".
  - Read `result` (with `wrong_answers_left`, `hint`, `verified`) and the ledger's `wrong` and `hinted`.
  - A second variant repeats the swapped answer twice.

**U6. Malformed phone answers.**
- *Unknown:* whether the "unreadable, not counted" rule (L37) applies to `phone_last4` at all. A spoken-digit answer was counted wrong [PROBED-earlier]. 3-digit, 5-digit and space-separated answers are untested.
- *Experiment:* run PUB-12 (phone `4401`, then `4410`) with `--style pieces` and `--style in_words`, and read what `args.answer` the agent actually sent and the `result` for each. To settle the bank's rule on a 3-digit answer, a throwaway agent without a pre-hook guard on a PUB-12 session through chat, with the user typing "four four one" as the answer.

**U7. Which response keys are present.**
- *Unknown:* whether `ok` is always present, whether `error` is absent when `ok` is true, and when `all_verified` is omitted (it was seen missing once [PROBED-earlier]).
- *Experiment:* from any normal run, list the key sets of every `calls[].result` in the ledger.

**U8. `close_call` `reason` with `promise` or `paid`.**
- *Unknown:* if a reason (`""`, `"none"` or `"paid"`) is sent with `promise` or `paid`, does the bank reject it, store it, or null it? The scorer needs `reason == null` (`score.py:19–20`).
- *Experiment:* a throwaway agent whose `close_call` sends `reason: ""` with `outcome: "paid"`, run once on a PUB-08 session (the customer says she already paid). Read the ledger's `outcome` and `reason` and the call `result`.
- *Until then:* omit the key, as `base-agent.json:395` does.

**U9. Which tools are gated on verification.**
- *Stated:* only `get_account` is gated in the file (L91).
- *Implied:* `create_promise` returns `"identity not verified"` before verification (`score.py:32`) [CODE].
- *Inferred as not gated:* `schedule_callback`, `transfer_to_agent` and `close_call` (PUB-02 and `brief-a.md:102`) [INFERRED].
- *Unknown:* `add_note`.
- *Experiment:* not needed for design, because the agent never calls these before `get_account`. If wanted, use the ledger of a throwaway chat session that calls `add_note` before verifying. Low priority.

**U10. How strictly formats are validated.**
- *Known:* `"11am"` is rejected [PROBED-earlier].
- *Unknown:*
  - Impossible dates such as `2026-02-30`.
  - `"9:30"` against `"09:30"`, `"24:00"`, and `"11:00:00"`.
  - Amounts with more than 2 decimals, zero or negative amounts, and non-numeric strings.
  - Past dates.
- *Why it matters:* the agent should always send canonical values, so these are robustness questions only. `score.py:21` rounds amounts to 2 decimals.
- *Experiment:* not worth a dedicated test. Note what `args` and `result` show in ledgers from `--style in_words` and `corrects` runs.

**U11. Timeouts and idempotency.**
- *Unknown:* if `create_promise` times out on the client side (`timeoutMs`, for example 12000 in `base-agent.json`) after the bank has recorded it, the retry returns `"this product already has a promise"`. The agent would then report a failure and possibly note `service_error`, and the ledger would disagree.
- *Why it is open:* the file says nothing about timeouts or idempotency keys.
- *Experiment:* this cannot be triggered on demand by normal use. Watch the ledgers for an `already has a promise` error after a timeout, and design for it: after a timed-out attempt, treat that error as "recorded" [INFERRED].

**U12. Contradiction: "The service does not enforce the brief" (L6) against the checks the bank does make.**
- *The checks:* identity gating (L91), one promise per product (L174), nothing after close (L411), and the pairing of outcome and reason [PROBED-earlier].
- *How far non-enforcement goes is unknown:* notes on promised products, duplicate notes, callbacks outside the window, amounts below the floor (stated as accepted in `hackathon-page.md §Evaluation`).
- *Experiment:* none needed for design. Treat the bank as a recorder and enforce every brief rule in the agent. The ledger of any run shows whatever was accepted.

**U13. Contradiction: `close_call.reason` is optional in the schema (L438–441) but "Required for every outcome except promise and paid" (L435).**
- *Known:* on the practice bank, a mismatch is rejected [PROBED-earlier].
- *Unknown:* whether the hidden bank also validates the pairing.
- *Experiment:* the practice behaviour can be read from the ledger `calls[]` of any run that closes `no_promise`. The hidden bank cannot be tested without probing. Design so that `reason` is set from the brief's table, conditionally required, with a pre-hook that adds or removes it.

**U14. Contradiction in retry guidance: the file's 500 "The call may be repeated" (no limit) against `brief-a.md:91` ("try once more. If it fails again ... `service_error`").**
- *Resolution:* the brief's count governs.
- *Unknown:* whether an `ok:false` (as opposed to a 500) counts as "fails" for that rule, for example `"date must be YYYY-MM-DD"` caused by the agent's own bad input.
- *Experiment:* U2 shows how injected faults arrive. If they arrive as 500s, count only 500s and timeouts as service failures, and fix the agent's own `ok:false` errors instead [INFERRED].

**U15. The hidden tool API's host and whether practice customers can be used with it.**
- *Unknown:* whether hidden files keep `https://freya-bank-mock.freyavoice.workers.dev/v1` and the same paths.
- *Stated:* `hackathon-page.md §FAQ` says "Hidden briefs have no practice cases, only the tool API file."
- *Experiment:* none possible before Sunday 17:00 UTC without probing. At build time, read `servers[0].url` from the supplied file. No call is needed.

**U16. Do the example's `required` arrays matter on Freya?**
- *Unknown:* `base-agent.json` leaves the baked `customer_id` out of `body.required`. Whether putting it in `required` changes what the dialogue model sees or must fill is undocumented.
- *Experiment:* do a dry run, then create and GET back two variants of one tool (`customer_id` in `required` or not). Make one chat turn on a practice session, then inspect the `function_call_start` body in `get_call` and the `<tool>_args.*` variables.

**U17. Product id format and order on a hidden bank.**
- *Unknown:* whether ids stay `p1..pN` in response order (`README.md:102` [DOC], [PROBED-earlier] on practice).
- *Experiment:* none for hidden banks. Design to copy `product_id` from the `get_account` response, never to build it.

# tc-1 — Corrections
The prior summary checked here is `research/read-tools-and-code.md`. Only claims about TC lines 1–317 are judged. Items 10 and 11 are claims about BA that the prior summary placed under "TC §Tool function shape", so they are included too.

| # | Prior claim (where) | Verdict | Correct statement | Citation |
|---|---|---|---|---|
| 1 | "Safeguard pattern [VER]: test the mapped variable and the flattened key (e.g. `verify_identity_response.data.all_verified`) together in one OR group, each with "true" and "True". BA does exactly this." (prior §5) | **WRONG** (the BA part) | BA tests **only the flattened key** `verify_identity_response.data.all_verified`, with operands `"true"` and `"True"`. Each of those conditions also has a `"mode": "exact"` field, which TC never mentions. BA has **no `response_mapping` anywhere**: node-level mapping is `[]` on both nodes and no tool has a mapping. So BA tests no mapped variable. The OR of a mapped variable and the flattened key is the **working builder's** pattern (VWB, TC:285). TC's own example ORs `check_passed` with `check_answer_response.data.verified`. BA is not the working builder | BA:116-137, BA:143, BA:318; TC:285; TC:296-306; README:34 |
| 2 | "Paths without `data.` are unconfirmed and failed in one early trial." (prior §4). Also gotcha #4, "Mapping paths need `data.`" (prior §12) | **OVERSTATED** | TC says a path without `data.` "is not confirmed". In an early trial call the mapped variables stayed unset, but "The mapping paths of that call are not recorded." So that failure **cannot** be blamed on bare paths. The facts are: `data.` paths are verified, and bare paths are unconfirmed. A "smaller example builder" uses bare paths | TC:283-284 |
| 3 | "[SEEN] The model's arguments are stored as `<tool>_args.<field>`, **never** under the bare name." (prior §2) | **OVERSTATED** | This comes from one trial call: "They were not stored under the bare field name." "Never" generalises from that one call. It is also unknown whether `<field>` is the property key or the placeholder's variable name. They were identical in the example (`lookup_order_args.order_number`) | TC:97; TC:85 |
| 4 | "Baking happens **once**, at node entry. A value that becomes known later in the same node is not baked unless the node is re-entered." (prior §2) | **UNSUPPORTED as fact** (an inference stated without a label) | TC says only: "Baking happens when the node is entered. A `{{var}}` default is resolved against the variable table at that moment." TC does not say what happens to a model-visible parameter whose variable gets set later in the same node, or whether re-entry re-bakes. Resolution time also differs by placement. A `code_exec` **tool** resolves `code` "when the tool is called" (TC:512). Lifecycle tools resolve when fired, and may fall back to a model fill (TC:561) | TC:91, TC:93; TC:512; TC:561 |
| 5 | "In an engine-run call (`pre_actions`, lifecycle tools), an unset variable drops the field from the request with no error." (prior §2). Gotcha #7, "In engine calls the field is silently dropped." (prior §12) | **OVERSTATED / INCOMPLETE**, and an unflagged contradiction | (a) WF narrows the rule. A field is dropped only if its value is **exactly one placeholder** (`"{{x}}"`). A **mixed** value (`"Status: {{x}}"`) "goes out with the literal `{{x}}` in it". (b) For lifecycle tools TC contradicts itself. TC:115 says the field is dropped, but TC:561 says "If a `{{var}}` parameter is still unresolved, one model call fills the parameters." The prior summary repeats both claims (§2 and §9, gotchas #7 and #18) without noting the conflict | TC:115; TC:561; WF:202-203 |
| 6 | "`_args` and `_response` are overwritten per call, and stale result variables persist and can fire later transitions or fake a success." (prior §12 #9) | **UNSUPPORTED** (the part about stale `_response` keys) | TC says only: "Each call of the same tool overwrites the previous `_args` and `_response` values." It does not say whether a later call whose response **lacks** a key clears the old flattened key, or overwrites only the keys present. WF:178 says variables are never cleared on a transition, which supports persistence of mapped variables between nodes. It says nothing about key removal inside `<tool>_response.*`. The danger is real because of an earlier probe: one re-verify returned no `all_verified` key at all [PROBED-earlier RAT:153]. But the claim as written is not documented | TC:279; WF:178 |
| 7 | "The old node's model does not speak, so the target node's `on_enter` (or prompt) must produce the next words." (prior §5) | **UNSUPPORTED as fact** (inference stated without a label) | TC: the transition fires "in the same turn, before any further model turn". TC does not say whether text the model produced *in the same turn as the tool call* is spoken. TC:164 says a model "can call a tool, speak, then call another". The target node's default `on_enter` is `{"type": "llm"}` (WF:94, WF:159), so the next node normally speaks anyway, unless it is set to silent | TC:291; TC:164; WF:94; WF:159 |
| 8 | "Or use a `number` index into a list… A pre-hook maps the index to the real value." and "Free strings get invented values." (prior §2) | **Minor overstatement / omission** | TC: "A pre-hook **or the backend** turns the index into the real value." TC also says the model "**sometimes** invents a value that looks plausible", not always. In the hackathon only the pre-hook option is open, because the bank API is fixed [INFERRED] | TC:122; TC:125 |
| 9 | "Hidden briefs change fields and enums… The 7 tool names stay fixed." Placed under "TC §Constrain model-filled parameters" (prior §2) | **MIS-ATTRIBUTED** (true, but not in TC) | TC says nothing about hidden briefs. The source is HP §Weekend: "The seven tool names stay the same; their fields and allowed values can change." The advice to "generate every leaf from openapi.json in code, not by hand or by LLM" is the prior author's own recommendation [INFERRED] | HP:12 |
| 10 | "`maxRetries` is 0 on all writes; `timeoutMs` is 12000." (prior §1, about BA) | **IMPRECISE** | In BA, **every** `api_call` tool, including the reads `get_account` and `verify_identity`, has `maxRetries: 0` and `timeoutMs: 12000`. Both `end_call` tools have `timeoutMs: 10000` and no `maxRetries`. The working builder sets 0 on writes and 2 on its read-only `pre_actions` call (TC:365), so the two builders differ | BA:8-10, BA:69-71, BA:159-161, BA:203-205, BA:266-268, BA:333-335; TC:365 |
| 11 | "`end_call` is a tool inside conversation nodes with `trigger_pattern` "Have a good day" and `trigger_timeout` 3." (prior §1, about BA) | **IMPRECISE** | `trigger_pattern` is `"Have a good day\|have a good day"`. The tool also bakes `message_mode` `"none"`, `interruptible` `true`, and `trigger_pattern_both` `"goodbye\|bye\|have a good day\|you too\|thank you\|thanks\|take care"`. None of these `end_call` parameters is documented in TC 1–300. TC:64 says only that `end_call` "Hangs up. Used in the `terminal` of an `end_call` node" | BA:78-97, BA:275-294; TC:64 |

### Prior claims checked and confirmed

These claims in the prior summary match the source:

- Tool shape, and `response_mapping` plus hooks as top-level siblings of `function` (TC:11-58, TC:243).
- The three handlers (TC:60-64).
- `function.name`'s double role (TC:48).
- The `api_call` parameters (TC:68-76). `connect_retries` as a baked parameter (TC:353, TC:363).
- The four-row value table (TC:82-87). `const` does not bake, and "URL is required" (TC:87, TC:92).
- The name-collision gotcha (TC:99).
- The `code_exec` crash on an unset `{{var}}` (TC:116).
- The body-leaf rules and "Template variable: name" (TC:103-106). `code_exec` top-level parameters (TC:109).
- The enum advice (TC:124, TC:126).
- `pre_actions` vs `tools` placement and silent stripping (TC:147-153). That `description` is ignored in `pre_actions` (TC:50, TC:167). Where `response_mapping` goes (TC:166, TC:243-244).
- The passthrough recipe and the mandatory `always` transition (TC:177-209, TC:315).
- All tool-description advice and both trial error strings (TC:213-221).
- The envelope shape (TC:253-262). The automatic variables list (TC:266-277). Overwrite per call (TC:279).
- Booleans arrive as strings and both spellings should be tested (TC:286). The mapped list form is unconfirmed (TC:287).
- Routing re-runs after a tool result (TC:291). Leaving via a tool-result variable (TC:316). The `matches_intent` warning (TC:317).
- The WF operator semantics (WF:294-311). `is_tool_call` (WF:449).

### Omissions in the prior summary (not errors, not counted)

- TC:91 gives the mechanism. "At registration the engine moves every `default` into the tool's base config, resolves `{{var}}` from the variable table, and removes the field from the schema the model sees." TC:92 adds: "The engine reads only `default`."
- TC:106 ends "…while the call still works". So the `body.default` anti-pattern fails quietly.
- TC:107: a body that exists only as one `body.default` object "shows as an empty form in the dashboard editor. Saving from there removes the tool."
- TC:165: for **both** placements, "A tool call and tool result pair is added to the history". So a `pre_actions` result is in the conversation history that later model turns see.
- TC:164: within a turn, "The model can call a tool, speak, then call another."
- TC:66: handlers also exist for "integrations, knowledge search, call transfer and rescheduling", and "They are not needed here."
- TC:262: `header` holds the HTTP response headers.
- TC:277: `<tool>_success_count` is the "Number of successful calls so far".
- TC:116: the cell for "`code` of `code_exec`" with variable `""` is **empty**. That behaviour is undocumented.
- TC:285: a flattened key "can be used directly as a transition variable" (VWB).
- WF:195-196: `{{x}}` substitutes "The value as a string". `{{x:json}}` substitutes "The value JSON-encoded. Use it inside request bodies". This bears on numeric body fields (see U3).

---

# tc-1 — Uncertainties
Each experiment below fits normal kit usage once an API key exists:

- save the workflow (`freya.save_workflow`), publish it, and read it back with `GET /api/v2/workflow/{id}`;
- run a turn-by-turn `POST /api/v2/chat/message` against a practice session's `customer_id` (HP:43 names this route as the way to check an agent), or run one practice simulation;
- read `GET /api/v2/call/{callId}` events: `function_call_start` args, which for an `api_call` are the full `url`/`method`/`headers`/`body` (api.md:327); `function_call_complete` result; and `route_evaluated` `variable_table` or `workflowSnapshot.variableTable` (api.md:329, api.md:334-336);
- read the practice ledger's `calls[{n, tool, args, status, result}]` [PROBED-earlier RAT:140].

Several items can be checked together in **one** self-test workflow and one or two chat sessions, so the rule against probing the platform (HP:37) is respected.

| # | What is unknown or contradictory | Sources | Experiment that settles it |
|---|---|---|---|
| U1 | **An unset variable in a lifecycle tool: dropped, or filled by a model?** TC:115 and WF:202 say a single-placeholder field is dropped with no error. TC:561 says one model call fills the parameters | TC:115; TC:561; WF:202 | Workflow-level `end_of_call` `close_call` whose `reason` default `{{reason}}` is never set. End a practice chat, then read the ledger `calls[].args` for `close_call`. Absent `reason` means dropped; a reason value means model-filled |
| U2 | **A mixed placeholder in an engine-run call.** TC:115 says "dropped". WF:202 says a mixed value is sent with the literal `{{x}}` | TC:115; WF:202 | In a practice session, `pre_actions` `add_note` with `text` default `"Note: {{never_set}}"`. Read the `function_call_start` body and the ledger `notes` |
| U3 | **Type of a baked value.** For a `type: number` leaf with `default: "{{cp_amount}}"`, is the value sent as a JSON number or a string? WF:195 says `{{x}}` gives "the value as a string", and `{{x:json}}` exists "inside request bodies". The bank accepts a string amount `"220"` [PROBED-earlier RAT:156], but the ledger's stored amount type is unknown | TC:84; WF:195-196 | Bake `amount` from a code-set variable in a `pre_actions` `create_promise`, once as `{{cp_amount}}` and once as `{{cp_amount:json}}` (two practice sessions). Read `function_call_start` body and ledger `promises[].amount` |
| U4 | **Name the model sees when the property key differs from the placeholder** (TC:85 "named after the variable"). Also which name `_args.<field>` uses, and whether the request body uses the property key | TC:85; TC:97 | Conversation tool `schedule_callback` with `body.properties.date.default = "{{cb_day}}"`. Read the `function_call_start` body and the `variable_table` (`schedule_callback_args.*`). Design workaround if never tested: keep the key equal to the placeholder (TC:95) |
| U5 | **Does `""` count as "has a value" for a model tool**, so the field is baked as empty and hidden? Also: when a placeholder's variable gets set *during* the node, does the call use the model's argument or the new value? Does re-entering the node re-bake? | TC:84-85; TC:93; TC:115 | A node with `create_promise` whose `{{cp_date}}` is `""` at entry. Then a node where `cp_amount` is set mid-node by extraction. Then a self-transition re-entry. Compare `function_call_start` bodies with the model's turns |
| U6 | **Stale flattened keys.** Does a later call clear `<tool>_response.data.<k>` keys that are missing from its response, or overwrite only the keys present? This matters because a re-verify returned no `all_verified` [PROBED-earlier RAT:153] | TC:279; WF:178 | In one practice chat, call `verify_identity` twice so the second response lacks a key. Compare `variable_table` before and after |
| U7 | **Spelling and type of results in the table.** Flattened booleans were `true` as a string. Is a *mapped* boolean `"true"` or `"True"`? Is `attempts_left` `3` stored as a string or a number? | TC:271-272; TC:286; WF:372 | Map `data.verified → v_map` on `verify_identity`. Read `v_map` and `verify_identity_response.data.*` in `variableTable` |
| U8 | **Does `body.required` matter for baked fields?** BA leaves the baked `customer_id` out of `required`, yet puts the baked `outcome` in `close_call.required`. TC:104 says only "Put required fields in `body.required`" | TC:104; BA:24-27; BA:352-354 | Dry run plus a readback of a tool with a baked field in `required`; check the stored schema. Low priority: follow "required = model-filled fields" |
| U9 | **How lists are flattened, and the form of a mapped list.** Indexed keys? A JSON string in `vars`? TC:287 says the form in `vars` "is not confirmed" | TC:264; TC:287 | `get_account` with `data.products → products`. Read `variableTable`, and in a following code node write `vars['p_type'] = type(vars.get('products')).__name__` |
| U10 | **Do bare (non-`data.`) mapping paths work?** | TC:284 | On one tool, map both `data.ok → a1` and `ok → a2`. Read `variable_table`. (Design does not depend on it: always use `data.`) |
| U11 | **Failure counter: what counts, and when it appears.** It is absent from the trial table. What counts as failure (HTTP 500, timeout, `ok:false` at 200)? | TC:277; TC:326 | Practice case PUB-10 fails the first `create_promise` [PROBED-earlier RAT:139]. Read `create_promise_success_count` / `_failure_count` and the envelope in `function_call_complete` |
| U12 | **Envelope on errors.** `status`, `data`, `message` and `status_code` for HTTP 500, 404, timeout, and 200 with `ok:false`. Only the success envelope is documented | TC:250-262 | Same PUB-10 run, plus a deliberately wrong answer in `verify_identity` (`ok` true, `verified` false). Read `function_call_complete` |
| U13 | **What `passthrough_default_transition` does**, given that TC says a passthrough node with no matching transition deadlocks even with it set | TC:178; TC:209; WF:466-467 | No experiment needed. Always set both fields and end with `always` |
| U14 | **"Template variable: name"**: is "name" literal text or the variable's name? | TC:106 | No experiment needed. Never use `body.default` |
| U15 | **Are `enum` / `const` enforced by the engine?** When the model outputs a value outside the enum, is it blocked or sent? TC says `const` only "constrains the model's own output" | TC:87; TC:124 | Watch `function_call_start` args across practice runs for any value outside the enum. The bank rejects unknown enum values anyway [PROBED-earlier RAT:157-159] |
| U16 | **Same-turn routing and pending speech.** If the model spoke and called a tool in one turn, is the text spoken before the transition? Is the old node's model ever given another turn? | TC:164; TC:291; WF:410 | In a practice chat, read the event order (`assistant` message, `function_call_start`, `function_call_complete`, `route_evaluated`, `node_enter`) around the identity→next-node transition |
| U17 | **What "only text the model reads about the tool" means** (TC:167), given that parameter `description`/`enum` are also shown (TC:85). Probably not a real conflict: the first is tool-level, the second is parameter-level | TC:85; TC:167 | No experiment needed. Write both tool and parameter descriptions |
| U18 | **`extraction_schema` "on a call result".** How it would run on a tool result, and where it sits for a tool in `tools`, is undefined. WF:609 says to use `response_mapping` for API responses | TC:246; WF:609 | No experiment needed. Do not use extraction on results |
| U19 | **Flattened key prefix for a `pre_actions` `api_request` node**: node id or tool name? Counters for `pre_actions` nodes are named after the node id (TC:325). Code nodes use the node name (TC:490). The `api_request` case is undocumented | TC:264; TC:325; TC:490 | `pre_actions` `get_account` in node `fetch_acct`. Look for `fetch_acct_response.*` vs `get_account_response.*` in `variable_table` |
| U20 | **Does `_args` include baked fields?** TC:268 says "Each argument the model sent", which suggests model-filled fields only | TC:268 | After `verify_identity`, check whether `verify_identity_args.customer_id` exists in `variable_table` |
| U21 | **Evidence-grade mismatch.** Same-turn routing is labelled "Seen in a trial call" in TC:291 and "Verified in a working builder" in WF:410. Both support the claim; WF:410 is specifically about a variable set by a tool's `response_mapping` | TC:291; WF:410 | Covered by U16 |
| U22 | **What a `code_exec` `code` does when its variable is `""`.** The table cell is empty. TC:494 also says the sources disagree on whether `code` is templated at all | TC:116; TC:494 | No experiment needed. Never put `{{` or `}}` in code; read from `vars` |

# tc-2 — Corrections
Only claims that concern TC:280-587 were checked. Fifteen claims are wrong, overstated or unsupported.

| # | Prior claim (location) | Verdict | Correct statement, with citation |
|---|---|---|---|
| 1 | "**Paths must start with `data.`** [VER] … Paths without `data.` are unconfirmed and failed in one early trial." (PRIOR:64; repeated as gotcha 4, PRIOR:236) | OVERSTATED | `data.` paths are verified, on both a tool-level and a node-level mapping (TC:283). A bare path is "not confirmed" (TC:284). In the early trial the mapped variables stayed unset, but "The mapping paths of that call are not recorded" (TC:284), so that failure **cannot be attributed** to the missing prefix. Bare paths are unconfirmed, not shown to fail. (The `data.promise_id` example is the summarizer's, not TC's.) |
| 2 | "Safeguard pattern [VER]: test the mapped variable and the flattened key … in one OR group … **BA does exactly this.**" (PRIOR:80) | WRONG about BA | The OR-group safeguard belongs to the unnamed working builder (TC:285). BA's only transition (BA:116-135) tests **only** the flattened key `verify_identity_response.data.all_verified`, with `"true"` and `"True"` (and an extra `"mode": "exact"` field). BA has no mapped variable to test: node `response_mapping` is `[]` (BA:143, BA:318) and no tool carries one. |
| 3 | "The old node's model does not speak, so the target node's `on_enter` (or prompt) must produce the next words." (PRIOR:79; gotcha 11, PRIOR:243) | UNSUPPORTED as a doc fact | TC:291 says only that a result transition "fires in the same turn, before any further model turn". TC says nothing about who speaks next. The conclusion is [INFERRED]. It is consistent with BA, whose target node `collection` has a `tts` `on_enter` (BA:301), but no doc states it. The old node's model may already have spoken earlier in the same turn: "The model can call a tool, speak, then call another" (TC:164). |
| 4 | "Flattened key names for a **`pre_actions` api_request node** (node id or tool name) are unconfirmed [UNC]." (PRIOR:76) | IMPRECISE | The **counters** of a `pre_actions` node are documented as `<nodeId>_success_count` and `<nodeId>_failure_count` (TC:325) [DOC]. They are not seen for an api_request node: only the code-node case was seen (TC:328). Only the `_response.*` and `_status_code` naming of an api_request node is undocumented. TC:490 states node naming for **code** nodes only. |
| 5 | "Do **not** use this [background tools] for verify_identity or create_promise." (PRIOR:98) | UNSUPPORTED (unlabeled recommendation) | TC:345 gives no such rule. It is a reasonable [INFERRED] recommendation, because results arrive "one or more turns later" and a transition right after the call "can find them unset" (TC:345). |
| 6 | "`config.timeoutMs` … always set it (**BA uses 10000-12000**)." (PRIOR:102) | IMPRECISE | BA uses `timeoutMs: 12000` on **all four** `api_call` tools: verify_identity (BA:9), get_account (BA:160), create_promise (BA:204), close_call (BA:334). `10000` appears only on its two `end_call` tools (BA:70, BA:267), which have no `maxRetries`. BA also sets `maxRetries: 0` on the read-only get_account (BA:160-161), not only on writes. |
| 7 | "A `code` node holds **one** `code_exec` function in `pre_actions`." (PRIOR:132) | OVERSTATED (minor) | TC:420 says "The snippet is a `code_exec` function in `pre_actions`". The example has one entry (TC:429-444). No limit of one is stated, and no behaviour with several is documented. |
| 8 | "Call variables (e.g. `now`, **`customer_id`**) are present [VER]." (PRIOR:137) | UNSUPPORTED example | Only `now` is cited: "The builder reads `vars.get("now")`, a call variable passed with the simulation" (TC:464). `customer_id` in code is [INFERRED]. It is likely, since all variables share one table (WF:178), but it is not verified. |
| 9 | "The docs disagree on whether `code` is templated, **so** an unset placeholder is left as text and breaks the Python." (PRIOR:143; gotcha 21 "breaks it", PRIOR:253) | MISSTATED | TC:494 says the **internal sources** (the platform's references, not the kit docs) disagree. One says `code` is exempt from templating. Another says placeholders resolve at run time and an unset one stays as literal text, which breaks the Python. Breakage is one side of a disagreement, not a consequence of it. The kit doc is itself inconsistent: TC:116 states the literal-text crash as fact, and TC:512 says the model-called `code_exec` tool's `code` "resolves `{{var}}` when the tool is called". |
| 10 | "Hidden traps: nested dict literals …, **f-string `{{` escapes, and embedded JSON**. Write `{'a': {'b': 1} }`, use `dict()`, or build strings with `+` or `%`." (PRIOR:144) | UNSUPPORTED additions | TC:494 names only the nested dict literal (`{'a': {'b': 1}}` ends in `}}`). It says the builder "removes every `{{` and `}}` from generated code" without saying how. f-strings, embedded JSON and the specific workarounds are [INFERRED]. They are sound, but they are not doc. |
| 11 | "`code_exec` as a model-called tool … it cannot carry hooks, and **its result is `data:null`, so the model gets no feedback**." (PRIOR:151) | OVERSTATED | The `data: null` result was seen for a **code node's** `code_exec` in `pre_actions` (TC:472-476). For the tool form, TC:512 says "nothing about it is verified here". "Cannot carry hooks" is supported by TC:402. The no-feedback claim is an extrapolation. |
| 12 | "The fix [VER]: a post-hook on **every** tool adds `data.what_to_do_next`, … ('Not verified; X wrong answers left; ask the same question again' / 'Recorded; tell the customer…')." (PRIOR:169) | OVERSTATED / invented quotes | TC:573 says "a post-hook on the tool that adds one plain instruction line … for example a `what_to_do_next` field". "Every tool" is stated only for `result.pop("header", None)` (TC:411). The quoted sentences are not in TC. The doc's example strings are `'Ask the next question.'` and `'Ask the same question again.'` (TC:389). |
| 13 | "If the request is invalid, it **cannot be aborted** (abort is undocumented)." (PRIOR:197) | OVERSTATED / self-contradictory | No abort mechanism is documented, and neither is the effect of a hook that raises: "What the platform does when a hook raises is not documented" (TC:414). "Cannot be aborted" is unknown, not established. |
| 14 | "The **meaning of `maxRetries`** and of the failure counters is undocumented." (gotcha 15, PRIOR:247) | OVERSTATED (half) | `maxRetries` is documented as "Tool-level retries after a failed response" (TC:352) and "Tool-level retries of a failed call" (TC:53). Undocumented: its **default** (TC:352, "not documented") and what counts as "failed". Counter semantics are indeed undocumented (TC:321-328). |
| 15 | Checklist: "body field … **generated from openapi**" and "Code … contains **no braces pairs**" (PRIOR:258, PRIOR:263) | IMPRECISE | TC:580 requires only that each body field be a leaf under `body.properties` with its own `default`, `description` and `enum`. Generation from openapi is an addition. TC:586 forbids `{{` and `}}` (doubled braces) only. Single braces such as `{}` and `{'a': 1}` are fine, so "no braces pairs" could be misread as banning all dict literals. |

Checked and found correct (no correction):
- PRIOR:74-75, 81-83, 87-88, 90, 93-94, 97, 99, 103-109, 114-129, 133-136, 138-141, 145-149, 154-162, 166-167
- Gotchas 16-18 and 20
- The closing paragraph (PRIOR:271): failure-count semantics, the envelope on HTTP 500 or timeout, and hook abort really are undocumented.

---

# tc-2 — Uncertainties
Every experiment below uses normal kit usage once an API key exists:
- build and publish your own test workflow with `freya.py`;
- run `tools/run_cases.py` or `POST /api/v2/chat/message`;
- read `GET /api/v2/call/{callId}` events (`function_call_start` args, `function_call_complete` result, `route_evaluated` `variable_table`, `workflowSnapshot.variableTable`, API:294-336);
- read your own practice ledger (`calls[{n, tool, args, status, result}]`, `failures{tool:n}`, [PROBED-earlier] RAT:132-141).

No load testing, no calls outside the kit's tool API (HP:37).

### Contradictions inside the sources

| # | Contradiction | Cites | Experiment that settles it |
|---|---|---|---|
| K1 | An unset `{{var}}` in a lifecycle tool is **dropped from the request** (TC:115) versus **filled by one model call** (TC:561). | TC:115, TC:561 | Publish a workflow where `reason` is never set and `close_call` bakes `{{reason}}`. Run one practice case and read the ledger's `calls[]` args for `close_call`: absent field = TC:115; plausible model-written value = TC:561. |
| K2 | Is `code` templated? TC:116 says yes (an unset `{{var}}` stays literal and crashes); internal sources disagree (TC:494); the `code_exec` tool form resolves at call time (TC:512); baking happens at node entry (TC:93). | TC:93, 116, 494, 512 | Only if ever needed: a code node with `x = "{{now}}"` writes `vars['tpl_probe'] = x`; read `variableTable`. Otherwise avoid all `{{`/`}}` and the question is moot. |
| K3 | Pre-hook `vars` "fills the placeholders of the request", yet `config` is "the substituted request". Does a `vars` write still change the request? The doc example edits `member_code`, which the request does not use. | TC:384, 388, 395 | Pre-hook sets `vars['answer'] = 'X'` and, separately, `config['body']['answer'] = 'Y'` in a second variant. Compare `function_call_start` args and the ledger args. Also check whether `vars['ph_mark'] = '1'` written in a pre-hook appears in `variableTable`. |
| K4 | `result` in a post-hook: internal reference = response body; working builder = envelope. | TC:407-409 | Post-hook adds `result['data']['shape'] = 'env' if 'status_code' in result else 'body'`; map `data.shape` and read it. |
| K5 | The post-hook name table lists only `result` (TC:396), but a post-hook "can read call variables and write new variables" (TC:416). Under what name? | TC:396, 416 | Post-hook in `try: vars['post_mark'] = '1'` with `except NameError`, writing `result['data']['vars_ok'] = 'no'`. Read `variableTable` and the mapped flag. |
| K6 | A malformed lifecycle tool is "dropped at run time without an error", yet the advice is "Validate with a dry run". Dry run checks write-time schema only (API:75-86). | TC:564, API:71-86 | After every publish, run one practice case and confirm the ledger shows `outcome` set by `close_call`. That proves it fired. |
| K7 | `suppress_tool_results` shows the model only `{status: "success"}` (TC:341), while the fix for silent or ignored results needs the model to read `what_to_do_next` (TC:573). Combined, the fix is probably hidden. | TC:341, 573 | Conversation node with `suppress_tool_results: true` and a post-hook whose `what_to_do_next` says "Say the word PINEAPPLE now." Chat one turn and see whether the agent says it. |
| K8 | The example post-hook uses truthiness `d.get('verified')` (TC:389), while "Booleans arrive as strings" (TC:286). Is `result['data']` native-typed (bool) or stringified? | TC:286, 389 | Post-hook writes `d['vtype'] = type(d.get('verified')).__name__`; read `<tool>_response.data.vtype`. |
| K9 | Routing runs "After each user message" (WF:393) versus "Routing runs again after a tool result arrives" (TC:291). Does the post-result evaluation include `loop_condition`, global nodes and `matches_intent` (re-judged on the same last user message)? | WF:393-398, TC:291, TC:317 | Read the `route_evaluated` event right after a `function_call_complete`. Its `branches` list shows which conditions were evaluated (API:329). |
| K10 | The seen trial table lists `_success_count` but no `_failure_count` (TC:277), while TC:321 says "two integer variables per call target". Does `_failure_count` exist as `0` before any failure? If unset, what does `greater_than` (float of nothing) do? | TC:277, 321, WF:298 | Read `variableTable` after one successful call. Then use a transition on `<tool>_failure_count greater_than 0` and read its branch result in `route_evaluated`. |
| K11 | `connect_retries` default is `2` (TC:353), but the doc's declaration example uses `default: 0` (TC:363), which would disable it. | TC:353, 363 | No experiment needed. Declare `2` explicitly, or omit it, assuming omission means 2 [UNCERTAIN]. |

### Open unknowns

| # | Unknown | Why it matters | Experiment |
|---|---|---|---|
| U1 | Whether a mapping path without `data.` works (TC:284). | A wrong path leaves variables unset silently. | One tool with two mappings, `data.ok → a` and `ok → b`; read `variable_table`. (Or just always use `data.`.) |
| U2 | The form of a mapped list or object inside `vars`: list, JSON string, or flattened keys (TC:287). | Code that iterates products. | Map `data.products → products`. A code node writes `vars['pt'] = type(vars.get('products')).__name__` and `vars['pr'] = repr(vars.get('products'))[:300]`; read `variableTable`. |
| U3 | The spelling of a boolean in a **mapped** variable (`true` or `True`) versus the flattened key (`true` seen, TC:286; WF:372 says either). | Silent `equals` mismatch. | Map `data.verified → v`; read both `v` and `<tool>_response.data.verified` in `variable_table`. Until then, test both spellings. |
| U4 | Types inside the post-hook's `result['data']` (see K8). | `what_to_do_next` correctness. | As in K8. |
| U5 | What `_failure_count` and `maxRetries` treat as failure: HTTP 5xx, timeout, connection failure, 4xx, or `ok:false` at 200 (TC:321-328, 352). | Retry/give-up routing; double-recording. | Run PUB-10 (PTS:392-440: `faults: [{tool: create_promise, fail_first_n: 1}]`, check "exactly one promise in the ledger after the retry") with `maxRetries: 0`. Read the `function_call_complete` result, `create_promise_failure_count`, `create_promise_response.status_code`, and the ledger `calls[]`/`failures`. Repeat with `maxRetries: 1` and count ledger calls to see whether engine retries are visible and duplicate. |
| U6 | The envelope on failure (`status`, `data`, `message`, `status_code` on 500 or timeout); whether the post-hook runs on failed calls; whether `response_mapping` overwrites or leaves the old mapped value on failure. | Stale `ok` values can fake success. | Same PUB-10 run, plus a post-hook that sets `vars`/`result['data']['hook_ran'] = '1'`, and a mapped var pre-set to the sentinel `pending` by a code node. Read the values after the failed call. |
| U7 | Defaults of `timeoutMs` and `maxRetries` (TC:351-352). | Unknown engine retries on writes. | Not worth testing. Always set both explicitly (`maxRetries: 0` on writes, TC:365). |
| U8 | How `timeoutMs` interacts with the 30 s connect budget (TC:362); whether `config.timeoutMs` applies to `code_exec` (example has no `config`, TC:430-443). | Edge timing only. | Not testable without a slow endpoint. Keep `timeoutMs` ≤ 15000 and snippets fast. |
| U9 | Naming of `_response.*`, `_status_code` and counters for an `api_call` in `pre_actions` of an api_request node: node id (TC:325 says, for counters) or tool name? | Fallback transitions on flattened keys. | api_request node `n_fetch` with tool `get_account`. After entry, read `variable_table` for both `n_fetch_*` and `get_account_*`. |
| U10 | Counters and automatic keys for the `code_exec` tool form, lifecycle tools and `end_call`. | Only matters if those forms are used. | Read `variableTable` in a run that uses them. Low priority. |
| U11 | `suppress_tool_results`: content on failure, and scope (model-called tools vs `pre_actions`) (TC:341). | Honesty about failed writes. | As in K7, plus a run on PUB-10 with suppression on, checking what the agent says. |
| U12 | Default of `config.interruptible`; what "user interruption" means in text chat simulations; how many turns later a background result lands (TC:345). | Avoid background tools for decisive calls. | Not needed if background tools are not used. Otherwise one chat run that reads `variableTable` per turn. |
| U13 | Meaning of node-level `interruptible` (BA:141, BA:316; absent from WF:87-113). | BA uses it; unknown effect on barge-in or tools. | Cannot be measured in text chat (WF:654 says wall-clock windows are not measurable in chat). Leave BA's values or omit it. |
| U14 | What happens when a hook raises: call skipped, error event, result unchanged, counter incremented? Also whether a hook can abort a call at all (TC:414; no abort documented). | Guard pre-hooks on writes. | On a read-only tool (get_account) in a throwaway test workflow, a pre-hook `raise ValueError('x')`. Read the events (`error`, `function_call_complete`) and the ledger `calls[]` to see whether the request was sent. |
| U15 | Whether a change to `result` changes the flattened `<tool>_response.*` keys (TC:416). | Routing on flattened keys after reshaping. | Post-hook sets `d['x'] = '1'` and pops `header`; read `variable_table` for `<tool>_response.data.x` and `<tool>_response.header.*`. |
| U16 | The hook sandbox: imports, time limit, same limits as `code_exec`? (TC:369). | Date math in a get_account post-hook. | Post-hook `try: import datetime; d['imp'] = 'ok'` with `except Exception: d['imp'] = 'no'`; map `data.imp`. |
| U17 | Sandbox modules beyond `json`/`re`/`datetime`, network, files, memory and output size (TC:506-508). | Snippet portability. | A code node with `try: import math` → `vars['m'] = 'ok'`/`'no'` (same for `decimal`, `calendar`, `zoneinfo`). Read `variableTable`. Not required if only json/re/datetime are used. |
| U18 | Storage of non-string `vars` writes (bool, int, list, `None`); whether `del vars[k]` unsets; whether `None` counts for `is_set` (TC:459-460). | Routing flags and fallbacks. | A code node writes one of each type; read `variableTable` values and an `is_set` branch result. |
| U19 | `code_exec` failure or timeout result and counter behaviour; whether partial `vars` writes persist (TC:470-490). | Deadlock and fallback design. | A code node that writes `vars['a'] = '1'` and then raises outside `try`. Read events, `<node>_failure_count`, and whether `a` exists. |
| U20 | The `code_exec` tool form: how model arguments reach the snippet, what the model sees, and naming (TC:512). | Only if that form is used. | Not recommended. Skip unless needed. |
| U21 | Lifecycle model fill (TC:561): which model, what context it sees, and whether it can invent values. | Deterministic `close_call`. | As in K1. Ensure every `{{var}}` used by `close_call` is always set, so the fill never triggers. |
| U22 | Whether hooks on an `api_call` placed in `pre_actions` or in a lifecycle tool run (TC:402 names only the handler). | BA's `close_call` pre-hook depends on it (BA:395). | Run a case ending in `promise` and check that the ledger `close_call` args lack `reason`. |
| U23 | `start_of_call`: whether its result enters the history the model sees, and whether mapped values are available to the initial node's `on_enter` text. | Optional preload of data. | One chat turn with a `start_of_call` read tool mapped to `x` and `{{x}}` in `on_enter`. Read the first response. |
| U24 | The hackathon agent model's silence after tool results (TC:570): how long before the simulated customer hangs up. | The cost of an empty turn. | Read `secondsFromStart` around a silent turn in any failed run's events (API:314). |

# wf-1 — Corrections
Every claim in PRIOR sections 1-6 that concerns WF 1-430 was checked against the source. Nothing in those sections is flatly wrong. Eight claims are overstated or claim more support than the source gives.

| # | PRIOR line | Prior claim | Verdict | Correct statement | Source |
|---|---|---|---|---|---|
| 1 | PRIOR:22 | A transition on a variable set by a tool's `response_mapping` "(or by the `<tool>_response.*` keys)" fires in the same turn. "This is verified." | OVERSTATED | WF verifies only the `response_mapping` case: "Verified in a working builder: a transition on a variable that a tool's `response_mapping` sets fires in the same turn, without a further user message." For the flattened `<tool>_response.*` keys the support is weaker. The verified builder tests the flattened key in the same OR group as the mapped variable "as a safeguard", so the key was never tested alone. Same-turn firing on "a result variable" is only "Seen in a trial call". | WF:410; TC:285; TC:291 |
| 2 | PRIOR:32 | "`nodePositions`: omit it." | OVERSTATED | WF does not tell you to omit it. It says: "Layout for the visual editor. The working builder omits it". It is optional (Required = no). Omitting it is sensible [INFERRED], but WF gives no rule. | WF:60 |
| 3 | PRIOR:33 | "No `null` anywhere ... Omit the field or use `""`." | OVERSTATED | WF: "Leave an optional field out, or set an optional **string** to `""`. A `null` fails validation." The `""` alternative is stated for optional strings only. Nothing says `""` is valid for an optional boolean, integer, object or array. | WF:64 |
| 4 | PRIOR:82 | "In a node without tools, state **"no tool call is allowed in this turn"**" (in quotes, as if a required sentence) | OVERSTATED | WF says "state that no tool call is allowed in this turn". That is a rule about what to say, not a required literal sentence. WF's own complete example uses different wording: "Do not call a tool in this turn." The part of the claim that is correct: when the node has a `loop_prompt`, the rule goes in both prompts. | WF:142; WF:702 |
| 5 | PRIOR:103 | "`test_variables` (merged in; a value passed with the call wins)" | OVERSTATED (drops a qualifier) | WF: "**On a web call to the workflow** it is merged into the call variables. A value passed with the call wins over a test variable of the same name." WF states the merge for web calls only. It does not say whether chat simulations, `POST /api/v2/chat/message` or the hidden benchmark merge it. A chat simulation reported `call.direction` = `web`, which suggests the merge applies there but does not prove it. Also, an update that leaves `test_variables` out deletes it. | WF:209; WF:234; API:101 |
| 6 | PRIOR:108 | Under the list of all variable sources: "`{{customer_id}}` in prompts and tool parameters, `vars.get("customer_id")` in code. Verified." | OVERSTATED (generalised) | The verification covers **call variables** only: "Verified in a working builder: call variables are readable as `{{customer_id}}` in prompts and tool parameters, and as `vars.get("customer_id")` in code." TC separately verifies one more case: a string written by a code node resolves as `{{name}}` in later nodes' `task_message`. WF verifies nothing for extraction or system variables. | WF:221; TC:466 |
| 7 | PRIOR:121 | Table row "`code` of `code_exec` (TC): literal stays in the Python source and the snippet crashes", stated as fact | OVERSTATED (outside WF, but inside the Variables section being checked) | TC:116 says this in a table. TC:494 then says "The internal sources disagree on whether the `code` field is templated. One says it is exempt." TC:512 says that for a `code_exec` **tool** the `code` field resolves `{{var}}` when the tool is called (not verified). The safe rule does not change: no `{{` or `}}` in code, and read values from `vars`. | TC:116; TC:494; TC:512 |
| 8 | PRIOR:145 | "`__previous__` only in global nodes" | OVERSTATED | WF: "`__previous__` is allowed in global nodes". WF does not say it is forbidden elsewhere. Its documented meaning, "returns to the node that was interrupted" (WF:499), only makes sense for a global node [INFERRED], so the advice is sound. The word "only" is not in WF. | WF:285; WF:499 |

### Claims checked and confirmed (for the record)

These PRIOR claims match the source:

- PRIOR:7-17 (three calls, what each one sees and produces): WF:15-30.
- PRIOR:19-21 (consequences): WF:34-36.
- PRIOR:25-31 and PRIOR:34 (top-level keys, `agent_config`, request body): WF:50-66.
- PRIOR:36-48 (node types and stripping): WF:70-84.
- PRIOR:52-72 (node fields and their defaults): WF:88-115. The D/M marks are PRIOR's own labelling.
- PRIOR:75-90 (prompt assembly, `task_message` rules other than #4 above, `on_enter` table): WF:119-162.
- PRIOR:93-97 (history across nodes): WF:168-174.
- PRIOR:100, PRIOR:110-120 (one table; substitution; date trap; placeholder behaviour taken from WF): WF:178, WF:191-203.
- PRIOR:126-134 (system variables, the clock trap, BA uses `Now: {{now}}`): WF:225-240; BA:315.
- PRIOR:136-141 (`context_variables`): WF:246-277.
- PRIOR:146-183 (transition fields other than #8, operators, shapes, the boolean trap, evaluation order, merging, no fallback): WF:283-412.
- PRIOR:185-187 (`routing_prompt`, self-transition): WF:416-426.
- PRIOR:213, the [U] about global nodes and a self-`always`: this is a correct inference from WF:395-402, WF:420 and WF:488, and PRIOR labels it correctly as an inference.

### Omissions in the prior summary

These are not counted as corrections. A designer needs them all the same.

1. `matches_intent` is judged on "the user's **last** message" (WF:309), even though the routing call sees "recent conversation messages" (WF:29).
2. WF contradicts itself on `routing_prompt`. The node-field table calls it "Extra context for the routing model" (WF:97). The section on it says it "**replaces** the default intent-matching instruction" (WF:416). PRIOR gives only the second reading.
3. WF contradicts itself on when `loop_prompt` is used. WF:99, WF:133 and WF:432 say "from the second turn in the node". WF:398 says it is used when `loop_condition` matches. WF:412 says that when nothing matches, the agent answers "from the same `task_message`".
4. Two rules in step 2 of the evaluation order can conflict: "Transitions are checked in list order" (WF:406) and "Deterministic conditions are evaluated first. If one matches, no routing model call is made" (WF:407). A trailing self-`always` is deterministic (WF:303), so it could pre-empt an earlier `matches_intent` transition. See U1.
5. The complete example (WF:700-701, 707-708, 726) combines `on_enter_first_entry_only: true`, a self-`always` and `max_node_turns` with a `max_turn_transition`. This implies a self-transition counts as a re-entry. If it does, `current_turns` "Resets on every transition" (WF:237), which could stop the turn cap from ever firing. See U3.
6. `system_prompt` and `task_message` are part of the dialogue call only. Extraction and routing never see them (WF:15, WF:28-30).
7. `## Current Task` is a literal heading the engine inserts between `role_message` and `task_message` (WF:124).
8. The kit client does not leave `agent_config` alone. `freya.update_workflow` re-saves the workflow with the platform-filled `agent_config`, with its `llmConfig` set to the event model, because "a chat turn or a real call cannot start" otherwise (FP:54-60). RM:103 still says "Leave `agent_config` out of the workflow you send."
9. The system date variables use fixed offsets (`en_cst` is UTC-6, `en_est` is UTC-5) and are based on the real clock, while the practice cases run on Wed 14 Oct 2026 11:00 (HP §Data). See the notes on system variables.
10. Variables are never cleared (WF:178). An enum extracted on an earlier visit stays set and can re-fire an `equals` fork when the node is re-entered. See U24.

---

# wf-1 — Uncertainties
How to run the experiments, all of it normal kit usage once an API key exists:

- Keep one experiment workflow and update it in place with `freya.save_workflow("wf-experiments", wf)`. It publishes after each update (FP:36-63), and a workspace holds at most 200 workflows (HP §Submit, §FAQ).
- Validate shapes with the dry run `freya.validate_workflow` (FP:48; API:71-85).
- Drive turns with `POST /api/v2/chat/message` and `customerVariables` (API:240-252). The chat route "may skip" a first code step (API:252), so start experiments with a conversation node.
- Read the `route_evaluated` events (`branches`, `variable_table`) and the `workflowSnapshot` (`nodeTurnCount`, `totalTurnCount`, `enteredNodes`, `transitionHistory`, `variableTable`) from `freya.get_call(callId)` (API:304-336; FP:79-81). [UNCERTAIN] whether `get_call` accepts a chat `callId`. A one-case `run_cases.py` simulation gives the same data.
- Bundle several questions into one workflow so that only a few turns are needed. HP §Rules forbids probing or load-testing the platform.

| # | What is unknown or contradictory | Sources | Why it matters | Experiment that would settle it |
|---|---|---|---|---|
| U1 | **List order or deterministic first?** If an `always`, or another deterministic transition, is listed **after** a `matches_intent` transition and both would be true, which wins? Is a model call made at all? | WF:406 vs WF:407; WF:420; WF:681 | The recommended self-`always` (WF:426) may silently disable every intent transition in the node | Node X with `[matches_intent "the user says the word banana" -> A, always -> X]`. Send "banana". Read the `route_evaluated` `branches`/`target` and see whether A was entered. Repeat with `[matches_intent -> A, equals(flag) -> B]` with the flag set |
| U2 | Can a global node ever fire from a node that ends in a self-`always`? | WF:400, WF:420 vs WF:488 | Global interrupts (off-topic, dispute, wrong person) would be dead on every collecting node | Add a global `matches_intent` node. From a node ending in self-`always`, send a matching message. Repeat from a node without the self-`always` |
| U3 | Does a self-transition count as a transition or re-entry? Does it re-run `on_enter`, reset `current_turns`, remove the `loop_prompt`, or reset the counter that `max_node_turns` uses? Does that counter use current or total turns? | WF:95, WF:106, WF:164, WF:172, WF:237-238; example WF:701, WF:707-708, WF:726 | Decides whether the turn cap in the doc's own example can ever fire, and whether opening lines repeat | Node with `on_enter` `tts` "ENTRY-LINE" (first-entry-only `false`), a self-`always`, `max_node_turns: 2` and `max_turn_transition` to an `end_call`. Send 3 messages. Count the ENTRY-LINE repeats, and read `nodeTurnCount`/`totalTurnCount` and whether the cap target is entered |
| U4 | **When is `loop_prompt` used?** "From the second turn in the node" (always), or only after `loop_condition` matched? With no match, is the reply "from the same `task_message`"? | WF:99, WF:133, WF:432 vs WF:398 vs WF:412 | A `loop_prompt` without a `loop_condition` might be dead text, or might silently replace the task | Node without a `loop_condition`, with `task_message` "Reply only with the word TASK" and `loop_prompt` "Reply only with the word LOOP". Send two messages and compare the replies |
| U5 | **Does `routing_prompt` add to or replace the instruction?** If it replaces it, must it carry its own input placeholders, like `extraction_prompt` must (WF:576)? Does it also govern `loop_condition` and global intents? | WF:97 ("Extra context") vs WF:416 ("replaces") | A replacing prompt without inputs could blind the router, the way a bad `extraction_prompt` blinds extraction (WF:576) | Node with a clearly matching `matches_intent` and `routing_prompt` "Never select any transition." Send a match and see whether routing still moves. Then try a `routing_prompt` that includes `{{system.conversation.last-5}}` |
| U6 | Which text does the routing model judge for `matches_intent`: the transition `description` or `condition.description`? | WF:286 ("The routing model reads it") vs WF:309 ("matches the description"); example WF:324-328 uses different texts | Decides which field must carry the intent wording | Transition `description` "The user says apple", `condition.description` "The user says banana". Send "banana" in one chat and "apple" in another |
| U7 | Context for `matches_intent`: "the user's last message" against "recent conversation messages". After a tool result, is the intent judged again against the stale message? | WF:29 vs WF:309; WF:410; TC:317 | An intent split over two messages may be missed. Post-tool routing may re-fire an old intent | (a) Send "I want to" then "cancel it", and see whether `matches_intent` "wants to cancel" fires on message 2. (b) A node with a tool and a `matches_intent` transition: read the `route_evaluated` after the tool result |
| U8 | Several `matches_intent` conditions are true in the single call. Which wins? | WF:311; WF:395, WF:406 | Ordering of competing intents | Two intents that both match one message. Swap their order and compare the targets |
| U9 | Does "one evaluation" (WF:311) include `loop_condition` and global intents? Does a node with a `loop_condition` pay a routing call even when a deterministic transition matches? | WF:36, WF:407 vs WF:398, WF:430 | Latency (calls end when the agent is slow, RM:100) and determinism | Compare `route_evaluated` `reason` and the turn latency for a node with and without a `loop_condition` that has a matching deterministic transition |
| U10 | In a turn that moves A to B, where B is a conversation node with `on_enter` `silent`, does the agent reply in that turn or say nothing? Does node A's dialogue run first? | WF:17-24, WF:161, WF:460 | A silent conversation node could create dead air, and the customer hangs up (RM:100) | A conversation node with `always -> B`. B has `silent` entry and `task_message` "Say B-HERE". Send one message and check whether any assistant text returns |
| U11 | What does `on_enter.prompt` (type `llm`) override: the `task_message` for the first line, or an internal entry instruction? | WF:159 | Lets a node open with a different line than its task | `on_enter` `{"type":"llm","prompt":"Say only ENTRY-PROMPT"}`, `task_message` "Say only TASK". Enter the node |
| U12 | With `on_enter_first_entry_only: true`, what produces the reply on re-entry: the dialogue model from `task_message`, from `loop_prompt`, or nothing? | WF:95, WF:164 | Re-entering nodes (back-edges, self-transitions) | Combine with U3: set the flag to `true` and observe turns 2 and 3 |
| U13 | **Date formatting on substitution.** Which values count as "date values": extracted `date`/`datetime` only, or any ISO string such as call variable `now` = `2026-10-14T11:00`? What language and format apply when `agent_config` is omitted? Does it apply in transition descriptions and the routing prompt? | WF:200; WF:62 | `Now: {{now}}` (BA:315) might reach the model reworded, not as ISO. Code-written ISO dates in prompts might be reformatted | `task_message` "Repeat exactly what is between brackets: [{{now}}] [{{d_code}}] [{{d_extracted}}]", where `d_code` is an ISO string written by code and `d_extracted` is a `type: date` extraction. Compare with the variable table |
| U14 | Is `test_variables` merged outside "a web call": in chat simulations, `chat/message`, and the hidden benchmark? | WF:209; WF:234 | Defaults for state variables would only be safe if the merge always happens | `test_variables {"tv_check": "TV-OK"}`, `task_message` "Say {{tv_check}}". Run one `chat/message` without passing it, then one practice simulation |
| U15 | **When are prompt placeholders resolved?** Every turn, or once at node entry, the way tool defaults are baked (TC:93)? | WF:191; TC:93; TC:466 (later nodes only) | A value mapped mid-node may never reach the current node's `task_message` | Node with a tool whose `response_mapping` sets X, and `task_message` "X is {{X}}. When asked, repeat X." Call the tool, then ask for X on the next turn without leaving the node |
| U16 | Exactly where substitution works: `loop_condition`, `condition.description` of `matches_intent`, `role_message`, extraction `description`, `enum_values`, `:json` inside prompts | WF:191, WF:242, WF:432 | Unknown fields may carry a literal `{{x}}` | An echo test per field. For routing fields, use a description that only matches when the substituted value is present |
| U17 | **Unresolved parameter in a lifecycle tool**: WF says the field is dropped, TC says one model call fills it | WF:202 vs TC:561 | The outcome recorded by an end-of-call tool (BA's `close_call`) is either missing or model-guessed | Run the base agent on one practice case. Read the `function_call_start` args of `close_call` in `get_call(...).messages` (API:327) to see whether `outcome`/`reason` were dropped or filled |
| U18 | Semantics on edge values: `is_set` for `""`. `not_equals`/`contains` on an unset variable (`str(None)` is `"None"`?). `greater_than` on a non-number (error or false?) | WF:296-302 | Sentinel and empty values are common, and a wrong guess fails silently (WF:372) | A code node writes `vars["e"] = ""` and `vars["t"] = "abc"`. Transitions test `is_set e`, `not_equals unset_var x`, `greater_than t 1`. Read `route_evaluated.branches` (API:332) |
| U19 | Which writers produce `"True"` and which `"true"`: code (Python `str(True)` = `"True"` [INFERRED]), extraction `type: boolean`, API flattening (lower case per TC:270) | WF:372; TC:270, TC:286 | Choosing operands for booleans | A code node writes `vars["b"] = True`, plus extract a boolean. Read `variable_table` |
| U20 | `equals` on numbers: `"3"` vs `"3.0"` vs `"3.00"` (e.g. amounts mapped from the API) | WF:296; WF:360 (numeric operand) | Silent mismatches on amounts | Map a numeric API field, test `equals` with `"420"`, `"420.0"` and `420`, and read the branches |
| U21 | Consequence of a top-level `"logic": "and"` (rejected? treated as OR? never fires?). Deeper nesting. `matches_intent` inside a group mixed with variable checks | WF:331, WF:347 | Builders that generate conditions need the legal grammar | Dry-run each shape. For the ones accepted, test the behaviour in chat |
| U22 | Is the bare single variable condition (WF:368) accepted, with the same semantics? | WF:368 | A simpler generator, if it works | Dry run, then chat with the variable set and unset |
| U23 | Same-target merge details: the list position of the merged transition, which `description`/`is_tool_call` is kept, and whether a `matches_intent` original keeps its intent text | WF:408 | `[cond -> X, intent -> Y, always -> X]` may make Y unreachable [INFERRED] | Build that node. Send a message matching Y with the cond false. Read `route_evaluated` |
| U24 | **Stale values.** When a later message yields no value, does the old extracted value stay? Does "Empty if unclear" write `""`, or nothing? | WF:178; WF:596 | Re-entering a fork node can re-fire the old choice at once | In the menu fork (WF:588-606), choose "cancel", route back to the menu, send an unclear message. Read `variable_table` and the route |
| U25 | Are tool-call and tool-result messages kept in history across nodes, or only user and assistant messages? | WF:170 | Whether node B can quote a result fetched in node A, or needs a mapped `{{var}}` | Node A calls a tool and moves to B. B's task: "Quote the last tool result verbatim" |
| U26 | `agent_config`: "omit it" (WF:62; RM:103), yet the kit re-saves it with the event model because a chat turn cannot start otherwise (FP:54-60), and an update without it deletes the platform-filled one (API:101). Is the default re-filled after such an update? Which model does the benchmark use? | WF:62; FP:54-60; API:101; HP §Submit | A first-time `create_workflow` (no patch) may give an agent whose chat turns fail | After `save_workflow`, `export_workflow` and inspect `agent_config.llmConfig`. Send one chat turn after the first create and again after an update |
| U27 | Strict schema vs silent stripping: is an unknown key rejected or silently dropped? (BA exports carry undocumented keys such as `"mode": "exact"`) | WF:64 vs WF:79; BA:122, BA:128 | Whether a generator's typo fails loudly or silently | Dry-run a node with an unknown key, then GET the saved workflow |
| U28 | Which node and transition fields are required? WF has no "Required" column for them | WF:88-113; WF:283-288 | Generator validation | Dry-run a minimal node (`node_type` only), then add fields until it passes |
| U29 | Does `{{<node>.current_turns}}` use the node key or `name`? | WF:237-238; WF:90 | Moot if `name` equals the key | Keep `name` equal to the key (WF:90). Test only if a design ever needs them to differ |
| U30 | After a same-turn post-tool transition into an `end_call` with `message_mode: "none"`, does the dialogue model still speak the result first? The complete example asks the model to "tell the caller whether the booking worked and say goodbye" after the tool, while routing on `booking_id` `is_set` moves at once to a silent hang-up | WF:410; WF:773; WF:808; WF:823; WF:656 | The closing sentence (confirmation of the promise) may never be said, which hurts the transcript check (HP §Evaluation) | Copy the `offer` and `goodbye_booked` pattern in chat. Check whether an assistant message follows the `function_call_complete` before the call ends |
| U31 | `context_variables`: is it dropped only from the stored copy, or is it also inactive at run time? How would "written once" `pre_history` survive the per-node system-message replacement? | WF:246; WF:273 vs WF:171 | Moot while the advice is "do not rely on it" | Save with the key and GET it back. If it is absent, stop there |
| U32 | Do `todays_date_en_cst`/`_en_est` really ignore daylight saving? (The WF example implies fixed offsets during US DST) [INFERRED] | WF:228-229 | Only if `system.*` dates were used, and they should not be (WF:240) | One chat turn echoing `{{system.iso_utc_now}}` and `{{system.todays_date_en_est}}`, comparing the hour gap |
| U33 | Does `reasoning_override` change anything on the event model `experimental-5`? | WF:113; API:200-202 | Possible latency or quality tuning per node | Two runs of the same node with `enabled` and `disabled`, comparing turn latency and output |

# wf-2 — Corrections
Only claims in PS that concern WF lines 400-859, or that rest on them, are checked here. Ten claims are WRONG, OVERSTATED or UNSUPPORTED.

| # | PS location and claim | Verdict | Correct statement, with citation |
|---|---|---|---|
| C1 | PS:22. Routing after a tool result fires on a variable set by `response_mapping` "(or by the `<tool>_response.*` keys) ... This is verified." | OVERSTATED | WF:410 verifies only "a variable that a tool's `response_mapping` sets". Same-turn firing on "a result variable" is only "Seen in a trial call" (TC:291). TC:285 does verify the flattened `_response` key as a transition variable. However, the working builder "tests the mapped variable and the flattened key in the same OR group". So it is not isolated which of the two fired. |
| C2 | PS:145. "`__previous__` only in global nodes." | OVERSTATED | WF:285 says "`__previous__` is allowed in global nodes". WF:499 says that, as a `target_node` or `passthrough_default_transition`, it "returns to the node that was interrupted". The docs never say it is forbidden elsewhere. "Only" is an inference. It is plausible, because only a global node interrupts. |
| C3 | PS:177. Lists "Specific conditions first, broad ones last" as a step of the engine's evaluation. | OVERSTATED (misframed) | This is authoring advice: "Put specific conditions first and broad ones last" (WF:406). The engine behaviour has two parts. (1) "Transitions are checked in list order" (WF:406). (2) "Deterministic conditions are evaluated first. If one matches, no routing model call is made" (WF:407). These two can conflict (see U1). PS does not flag the conflict. |
| C4 | PS:187. Self-transition is "Preferred over `loop_condition`". | OVERSTATED | The source says "Prefer this to `loop_condition` **in most cases**" (WF:426). |
| C5 | PS:203. A passthrough node is "the main deterministic computation hook: preload the account and compute dates, limits and holidays into variables before speaking." | UNSUPPORTED by WF | WF §Passthrough nodes (WF:462-484) says nothing of the kind. This is the PS author's inference and should be labelled so. It is partly backed by TC:169 (a passthrough `api_request` before a tool conversation) and TC:498 (do arithmetic and dates in code). |
| C6 | PS:202. "A passthrough `code` node can be the `initial_node` and runs before the first word. Verified." | OVERSTATED (caveat missing) | WF:484 does say this, as verified in a working builder. But API:252 adds: "when the first step is a code step the chat route may skip it, so values that step computes are empty". That is "Seen in tests, not guaranteed". So on `POST /api/v2/chat/message` the claim may not hold. See U9. |
| C7 | PS:232. "Set `min_confidence` on every variable (around 0.7, as in the examples)." | UNSUPPORTED value | WF:575 says only "Set `min_confidence` on every variable", with no recommended value. The examples use 0.8 (WF:541) and 0.7 (WF:548, 597, 704, 705). |
| C8 | PS:237. Date placeholders "resolve only inside `extraction_prompt`". The list is also cut short with "etc.". | OVERSTATED and incomplete | WF:582 says they resolve inside `extraction_prompt` and "Do not rely on them outside extraction prompts". Whether they resolve elsewhere is unstated. The full list (WF:582) also includes `{{time.now}}`, `{{date.day_of_week}}`, `{{date.yesterday}}`, `{{date.day_after_tomorrow}}`, `{{date.next_week}}`, `{{date.end_of_month}}`, `{{date.first_next_month}}`, `last_mon..last_sun`, `fnm_mon..fnm_sun`, `weeks2`, `weeks3`, `weeks2_ago` and `weeks3_ago`. See N10.5. |
| C9 | PS:257. An end-call node "is reached deterministically if routing is on variables." | UNSUPPORTED | §End-call nodes (WF:611-656) says nothing of this; it is an unlabelled inference. End nodes are also reached in other ways: through `max_turn_transition` (WF:708, 806) and through `matches_intent` (WF:809). Moreover, routing on variables is deterministic only once the variable is set, and the variable may come from model-run extraction. |
| C10 | PS:347. Design rule "Every conversation node gets a `max_turn_transition` and a self-`always` last." | OVERSTATED as a blanket rule | Three problems. (1) A trailing self-`always` always matches in step 2. Global nodes (step 3, WF:400, WF:488 "checked only after the current node's own transitions found no match") then become unreachable from that node. PS itself suspects this at PS:213. (2) The source's own example leaves the self-`always` out of `offer` (WF:807-810). (3) WF:407 suggests a deterministic `always` might be evaluated before earlier `matches_intent` transitions (U1). A further, separate question is whether a self-transition resets the turn count that `max_node_turns` uses (U3). |

**Material omissions in PS (not errors, not counted):**
- The complete example (WF:686-859) is not explained at all.
- These details are missing:
  - `keep_recent` and `summarize` semantics (WF:664).
  - The `interruptible` default (WF:644).
  - The rule that anything outside the `trigger_pattern_both` phrases "cancels the close and returns the turn to the agent" (WF:646).
  - `llm_prompt` (WF:643).
  - Extraction steps 1-2 (WF:567-568).
  - No `null` in extraction (WF:579).
  - The `loop_condition` example has `"transitions": []` (WF:441).
  - The passthrough example has `"pre_actions": []` (WF:477).
- These contradictions are not flagged:
  - `routing_prompt` "replaces" (WF:416) versus "Extra context" (WF:97).
  - API:252 versus WF:484.
- Two related facts are missing: README:100 and RC:116 show a second `endedReason` value, `customer-ended-call`. BA:142 and BA:317 set `max_node_turns: 80` with `max_turn_transition: null`.

---

# wf-2 — Uncertainties
Every experiment below is meant as part of normal builder self-testing once a Freya key exists. Each one is a small test workflow created with `freya.py`, run through one turn-by-turn chat (`POST /api/v2/chat/message`, API:242-250) or a single-persona simulation. It is read back with `GET /api/v2/call/{callId}` events: `node_enter`, `function_call_start`, `function_call_complete`, and `route_evaluated` with `branches` and `variable_table` (API:322-330).

Batch several questions into one test workflow to keep the call count small. The hackathon forbids probing or load-testing the platform (HP §Rules line 37) and allows one practice simulation at a time (HP §Submit line 34).

| # | Uncertainty / contradiction | Experiment that would settle it |
|---|---|---|
| U1 | **List order versus "deterministic first".** WF:406 says transitions are checked in list order, and WF:421 says a trailing self-`always` waits "until an earlier transition matches". WF:407 says "Deterministic conditions are evaluated first. If one matches, no routing model call is made", and `always` is deterministic (WF:303). Two readings are possible. (a) A trailing `always` pre-empts every earlier `matches_intent`. (b) A deterministic match lower in the list beats an intent match higher in the list. | Node with transitions [`matches_intent` "the caller says the word banana" → A, `always` → self]. Send "banana" and read `route_evaluated.branches` and the target. Second variant: [`matches_intent` → A, `is_set X` → B], with X preset by a code node and a matching message. |
| U2 | **Is a self-transition a re-entry?** The open points are whether `on_enter` re-runs (hinted at by `on_enter_first_entry_only` in WF:701), whether `{{node.current_turns}}` resets (WF:237, "Resets on every transition"), whether the `loop_prompt` second-turn logic restarts (WF:432), and whether a `node_enter` event is logged. | Node with a self-`always`, `on_enter` tts "ENTRY LINE", `on_enter_first_entry_only: false`. Send two messages. Check whether "ENTRY LINE" repeats, count the `node_enter` events, and read `<node>.current_turns` in `variable_table`. |
| U3 | **`max_node_turns` counting and firing.** Is the count per entry or per call (WF:662 "in one node"; WF:106 "spent in the node")? If a self-transition resets the per-entry count, the cap in the complete example's `collect` (WF:707-708, 726) would never fire. Also unknown: whether it fires on the Nth or (N+1)th user message, whether it beats a transition that matches on the same turn, and where "the overrun" is recorded (WF:663). | Node with a self-`always`, `max_node_turns: 2`, `max_turn_transition` → end node with `function.name` "capped". Send 3-4 off-topic messages and note when `endedReason` becomes `capped`. Repeat without the self-transition. |
| U4 | **`routing_prompt`: replace or add?** WF:416 says it "replaces the default intent-matching instruction". WF:97 says "Extra context for the routing model". | Two copies of a node with the same `matches_intent` transition and a clearly matching message. One copy has a `routing_prompt` holding only an unrelated fact, for example "The clinic is in Berlin." If intent matching breaks or degrades, the field replaces the default; if it stays normal, it adds context. Compare `route_evaluated.reason`. The result may be ambiguous and needs a few repeats. |
| U5 | **`loop_condition` details.** What does "second turn in the node" count (WF:432)? Is the loop condition checked after tool results too (WF:410)? Does it cost a routing call even when a deterministic transition would match (WF:398 puts it first)? | Node with a `loop_condition`, a `loop_prompt` containing a marker phrase, and a deterministic exit on a variable set by extraction. Inspect `route_evaluated` order and the turn on which the marker first appears. |
| U6 | **Same-target merging details** (WF:408). Unknown: where the merged transition sits in the list, how descriptions combine, and how `is_tool_call` mixes with a routed transition. | Transitions [`matches_intent` → A, `equals` → B, `always` → A]. If the merge is unconditional and sits at the first position, B never fires even when its variable matches. Read the branches in `route_evaluated`. |
| U7 | **Tool-call transition details** (WF:449-460). Unknown: whether the tool name is `transition_to_<target_node key>`, which text the model sees as its description, whether `condition` is used at all, how it fits the "no tool call is allowed" rule for tool-less nodes (WF:142), and whether calling it creates `_args` or `_success_count` variables. | Conversation node without tools plus one `is_tool_call` transition to a tts node. Prompt the move. Read the `function_call_start.function` name, the following `node_enter`, and `variable_table`. |
| U8 | **`passthrough_default_transition` versus transitions.** Why are both needed (WF:466-467)? Which wins if they differ? Does the default rescue a node whose transitions do not match, which would contradict "deadlocks" (WF:467)? | Passthrough code node with transitions [`equals` never-true → A] and default B, no `always`. Run one chat turn and see whether it reaches B or stalls. End the chat with `/chat/end`. A second variant uses `always` → A with default B. |
| U9 | **Initial passthrough code node on the chat route.** WF:484 (verified) says it runs before the agent speaks. API:252 says the chat route may skip a first code step. | Initial code node sets `vars['marker']='set'`. The next node's tts says "Marker {{marker}}". Compare the first `chat/message` response with a one-persona simulation transcript. |
| U10 | **Global node mechanics.** (a) Are global `matches_intent` conditions judged in the same routing call (WF:311)? (b) Does `__previous__` re-run the interrupted node's `on_enter` (default `llm`)? (c) Is a passthrough global's `task_message` ever used (WF:508)? (d) Are globals checked after tool results? (e) What does "the global node can loop" at terminal nodes mean (WF:523)? (f) Where is a global `is_tool_call` tool offered? | Copy the WF:501-518 `off_topic` global onto a two-node test workflow whose first node has no trailing `always`. Send an off-topic message, then an on-topic one. Read the `node_enter` sequence, the assistant messages after the tts line, and `route_evaluated`. |
| U11 | **Extraction date anchor and date format.** Is "today's date" given to the extractor (WF:577) the real clock, like the system dates (WF:240), or the call's `now` that every brief date rule uses (HP §Overview line 14)? In what format is a `date` variable stored, and how is it substituted into an HTTP body (WF:754)? Only prompt substitution is described (WF:200). | Extraction node with `type: date`. Chat with `customerVariables.now` = a date different from the real date, for example `2026-10-14T11:00`. Say "tomorrow", then read `variable_table`. Then route into an `api_request` node whose body uses `{{the_date}}`, sent to the kit's own tool API in a normal practice test, and read `function_call_start.args.body`. |
| U12 | **Relative-date semantics.** `{{date.next_mon}}`, `{{date.next_week}}`, `{{date.weeks2}}` and the built-in rules are undefined (WF:582). Brief rules need "next <weekday>" to mean the following calendar week (BRA:65) and need vague periods to be **asked about**, not converted (BRA:64). WF:578 says built-in rules convert "next week". | With `now` set on a Friday, say "next Friday", then "next week". Read the extracted values. Then repeat with a custom `extraction_prompt` (with all four `extractor.*` placeholders) that rejects vague periods. |
| U13 | **Extraction overwrite and stale values.** Does a later extraction overwrite a set variable when the caller changes their mind? Does an unclear turn leave the old value in place (variables are never cleared, WF:178)? The fork-on-enum `menu` (WF:586-606) would re-fire on a stale value at re-entry. | Enum fork node with a back-edge. Choose "cancel", return, then answer unclearly. Read `variable_table` and the route. |
| U14 | **Extraction internals.** Unknown: how many "recent messages" are seen (WF:567), the default of `max_retries` (WF:563), what happens after retries run out, whether `validation_pattern` applies to non-strings, how `enum_values` is written for numeric types, and what the `name`, `phone_number` and `datetime` types do (WF:557). | Partly settleable. Use `validation_pattern ^[0-9]{8}$` and say 7 digits, then check that the variable stays unset. Use `type: phone_number` and read the stored form. Retry counts are probably not visible in events. |
| U15 | **Does `""` count as set?** `is_set` is true when "The variable has any value" (WF:301). WF:579 recommends `""` instead of `null`, and the fork example's description says "Empty if unclear" (WF:596). | Code node sets `vars['x']=''`. Transitions [`is_set x` → A, `always` → B]. Run one chat turn and see which node is entered. |
| U16 | **Failure-counter semantics** (WF:766; TC:321-326). Is `find_slots_failure_count` unset or `0` before a failure? How does `greater_than` treat an unset variable? Is a failure counted per attempt or per call after `maxRetries`? What counts as a failure (HTTP 4xx/5xx, timeout, connection error)? Is the counter named after the node or the function, given that they coincide in the example? | A passthrough `api_request` node, whose node id differs from its function name, calls the kit's tool API with a request the bank rejects in normal use (for example a missing required field). Read `variable_table` for both names and the route taken. |
| U17 | **Same-turn routing versus speaking after the tool.** The example's `offer` tells the model "After the tool result, tell the caller whether the booking worked and say goodbye" (WF:773). But `booking_id is_set` fires in the same turn (WF:410), "before any further model turn" (TC:291), into `goodbye_booked`, which hangs up silently with `message_mode: none` (WF:815, 823). The caller may never hear the result. WF:656 says the goodbye belongs in the previous node. | Build an analogous node around the kit's write tool (normal practice use): a tool-level mapping of a returned id, then a transition to a silent `none` end node. Read the message order: `function_call_complete`, then any assistant message, then `node_enter`. |
| U18 | **End-call parameter defaults.** Unknown: the default of `message_mode`, the default of `trigger_timeout`, an `llm_prompt` example, whether an end node's `on_enter` line is ever spoken with `custom`, and whether `trigger_pattern_both` is regex or literal and case-sensitive. The base agent uses an undocumented `trigger_pattern` (BA:86-89) and lists both cases, which hints at case sensitivity. The wall-clock window "a chat simulation cannot measure" (WF:654). | Partly settleable. End node with `message_mode` omitted and an `on_enter` tts line: read the transcript. The interruptible window cannot be tested in chat (WF:654). Avoid relying on it. |
| U19 | **Truncation and overrun details.** Do tool-call and tool-result messages count toward `truncation_window_size` (WF:664-665)? Which model writes the `summarize` summary? Where is the cap "overrun" recorded (WF:663)? | Low priority. Look for an overrun event in the `messages` of a capped test from U3. Truncation can stay at the default `keep_all`, avoiding the question. |
| U20 | **Inactivity monitor in chat.** WF:651 says to disable it on end nodes, and the example also disables it on `find_slots` (WF:735). Its effect in chat-mode simulations is undocumented, while README:100 shows that silent agents get `customer-ended-call`. | Compare `messages` for system check-in events in a chat run with and without `disable_inactivity_monitor` on a conversation node where the caller goes quiet. That needs a persona that pauses, so it may not be settleable in chat. |