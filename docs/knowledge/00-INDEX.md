# 00 · Index: how to master this kit before system design

This page is the entry point to the knowledge base in `knowledge/`. It does not replace the chapters. It gives the shape of the whole thing, the facts that decide the score, the vocabulary, every known contradiction, and the ten open questions with the experiment that settles each.

**How it was made.** I read chapters 01 to 08 in full. I spot-checked the load-bearing citations against the primary sources: `research/hackathon-page.md`, `README.md` lines 55-104, `tools/score.py` in full, and selected lines of `workflow-format.md`, `tools-and-code.md`, `api.md`, `brief-a.md` and `brief-b.md`. Every spot check matched. **No network call of any kind was made.** Facts from the earlier live probes of the mock bank stay labelled [PROBED-earlier] and were not repeated.

---

## 0. Citation keys and labels

All kit paths are under `kit/build-the-builder/`.

| Key | File |
|---|---|
| `page:N §Tab` | `research/hackathon-page.md` line N (the official page text, a capture; some bullets are condensed) |
| `README:N` | `README.md` |
| `A:N`, `B:N` | `briefs/brief-a.md`, `briefs/brief-b.md` |
| `OA:N` | `tools/openapi.json` (the practice tool API) |
| `PTS:N` | `public-test-set.json` (the 13 practice cases) |
| `SC:N`, `RC:N` | `tools/score.py`, `tools/run_cases.py` |
| `FP:N` | `freya.py` |
| `WF:N`, `TC:N`, `API:N` | `docs/workflow-format.md`, `docs/tools-and-code.md`, `docs/api.md` |
| `BA:N`, `AB:N`, `SK:N` | `examples/base-agent.json`, `examples/agent_builder.py`, `.claude/skills/build-phone-agent/SKILL.md` |
| `RAT:N` | `research/read-api-and-testing.md`, used **only** for its live-probe facts, labelled [PROBED-earlier] |
| `ch0N §x` | the knowledge chapter and section that covers the fact in depth |

| Label | Meaning |
|---|---|
| [DOC] | Stated in a kit document, a brief, the README or the hackathon page |
| [CODE] | Read from kit code or kit JSON |
| [PROBED-earlier] | From the earlier live calls to the mock bank (PUB-01 and PUB-11 only, RAT:5). Not repeated |
| [INFERRED] | Reasoning from cited facts |
| [UNCERTAIN] | Not settled by any source; the text says what is unknown |

---

## 1. The kit and the competition in ten lines

1. **Task.** Write a *builder*: one command that reads a bank's brief plus its tool API file and creates a *phone agent* (a Freya workflow) with no manual edits. Only the phone agent is scored (page:10, :14 §Overview; README:9-10) [DOC].
2. **The call.** A debt-collection call: confirm who is on the line, verify identity, state what is owed, negotiate a payment promise inside the bank's rules, record it, close with the right outcome (page:7, :9; A:9) [DOC].
3. **The platform.** A workflow is a graph of nodes. Each user message triggers extraction, routing and dialogue model calls. Tools are HTTP calls to a Freya-hosted mock bank, which records everything in a ledger (WF:9, :15-36; OA:6) [DOC].
4. **The kit.** Two briefs (A: one product, 47 rules; B: up to three products, 11 rules on top of A), the 7-tool OpenAPI file, 13 practice customers, three docs, a 2-node example agent, an example Claude Agent SDK builder, the `freya.py` client and the `run_cases.py`/`score.py` harness (README:42-53; page:19 §Data) [DOC].
5. **Scoring.** A case passes only if the ledger matches exactly **and** a judge model says the transcript kept the policy and was honest. No partial credit (README:57-65; SC:17-34; RC:97) [DOC][CODE].
6. **Final.** 2 hidden briefs (one clean spec, one raw bank material with "a memo that changes it" and "a code list"), 30 customers each, 1-3 products, several calendar days, 3 runs per case, all must pass. Score = cases passed / 60 (page:27 §Evaluation; README:71-77) [DOC].
7. **What changes.** Identity questions, numbers and limits, deadlines, calendar, outcome table, tool fields and allowed values. What stays: the seven tool names, English, the `now` variable, the agent model (page:12, :14; README:71-72) [DOC].
8. **Timeline (UTC).** Started Sat 10 Oct 10:00. Hidden briefs open Sun 11 Oct 17:00. Submissions close Sun 20:00. "The three hours are for running the builder and fixing bugs, not for tuning it to the new briefs." (page:13) [DOC]
9. **Submission.** Per hidden brief: the exported workflow and the trace of the builder run that made it, plus repo, commit and `python3 builder/build.py {brief_path} {tool_api_path}`. 30 minutes per brief including self-tests. Top ten are rebuilt from the commit and checked against the trace (page:31-34; README:89-91) [DOC].
10. **Tie-breaks.** Total promised amount on passed cases, then shorter total build time from the traces, then earlier submission (README:90; page:27) [DOC].

---

## 2. Reading order

Read in this order. The first three chapters tell you what must come out of the agent; the next three tell you what the platform can do; the last two tell you how to test and what is still unknown.

| # | Chapter | One line |
|---|---|---|
| 1 | `01-hackathon-and-scoring.md` | The competition end to end: goal, timeline, the eight ledger checks line by line, the judge, the 3-of-3 arithmetic, tie-breaks, submission form, trace, verification, limits, all rules and the FAQ. |
| 2 | `06-brief-rules.md` | Brief A's 47 rules and Brief B's 11, each quoted with requirement, interpretation, precedence and the public cases that test it; the calendar and every computed date; the outcome table; the persuasion ladder; verbatim sentences; banned words; 33 ambiguities (U-1..U-33); a 29-component generic schema (G1..G29) for any brief of this kind. |
| 3 | `07-practice-cases.md` | The 13 practice cases one by one: data, persona text, the ideal call turn by turn, the expected ledger, how each judge check maps to rules and turns, ways to fail, behaviour under each of the five speech styles; then the cases side by side and the full date derivation. |
| 4 | `05-bank-and-tool-api.md` | The mock bank: the OpenAPI file field by field, every enum and policy-bearing string, response and error semantics, session state, the ledger, fault injection, what the hidden tool files will likely change, and the 24 earlier probe facts. |
| 5 | `02-workflow-engine.md` | The Freya workflow model: three model calls per turn, every top-level key and node field, prompts, entry behaviour, variables and `{{var}}` substitution, transitions and every operator, passthrough, global nodes, extraction, end-call nodes, limits, the docs' complete example, `base-agent.json` line by line, and 48 open engine questions. |
| 6 | `03-tools-hooks-code.md` | Tools: placement, baking of parameters, body fields, the result envelope and automatic variables, routing on results, counters, retries, pre/post Python hooks, code nodes and `vars`, lifecycle tools, the "silence after a tool result" fix, and 34 open questions. |
| 7 | `04-api-and-test-harness.md` | The Freya REST API (all 16 routes), publish semantics, `freya.py` function by function, the persona/simulation/iteration/run/call model, chat, the event log, `run_cases.py` and `score.py` in full, what testing is possible during practice and during a 30-minute hidden-brief build. |
| 8 | `08-open-questions.md` | Every open question ranked (Q-01..Q-23 platform, I-01..I-45 brief interpretation, T-01..T-22 low impact, O-1..O-7 for organisers), 26 already-resolved points, the 51-item contradiction register, the 86 errors in the earlier summaries, and a minimal experiment plan. |
| (ref) | `_corrections-and-uncertainties.md`, `notes/` | Working material behind the chapters (per-file corrections of the earlier research summaries; deep-read notes). Consult only to trace where a claim came from. The chapters supersede them. |

---

## 3. The 50 facts that matter most

Ordered by importance for winning. Each is one line: the fact, its source, its label, and the chapter that covers it.

1. **3 of 3 or nothing:** each case runs 3 times and counts only if all 3 pass, so a per-run pass rate p gives p³ (0.90 → 0.73; 0.966 needed for 0.90) — page:27; README:76 [DOC]; arithmetic [INFERRED] · ch01 §7
2. **Two gates per run:** the ledger check list must be empty **and** the judge's run `outcome` must be `"pass"`; a missing verdict is a fail ("conversation: no verdict") — RC:96-97 [CODE]; README:57-63 [DOC] · ch01 §4.1
3. **The ledger is compared exactly, as multisets:** `(outcome, reason)`; promises `(product_id, round(amount,2), date)`; notes `(product_id, reason)` (text ignored); callbacks `(date, time)`; transfers by `queue` only; extras or duplicates fail — SC:19-27 [CODE] · ch01 §5.3
4. **`close_call` must be the last ledger call**, exactly one, and "Nothing is accepted after it" — SC:28-29 [CODE]; A:106; OA:411 [DOC] · ch05 §3.7
5. **One `get_account` or `create_promise` answered "identity not verified" fails the case**, even if a later retry succeeds — SC:30-32 [CODE]; RAT:154 [PROBED-earlier] · ch01 §5.3
6. **In a not-reached case any `verify_identity` or `get_account` call fails it** (outcome names `not_reached`, `no_contact`, `unreached` all trigger this) — SC:33 [CODE] · ch01 §5.3
7. **`reason` must be null for `promise` and `paid`**: leave the key out — SC:19-20 [CODE]; OA:435 [DOC]; PTS:30, :337 [CODE] · ch05 §3.7
8. **Hidden briefs change identity questions, limits, deadlines, calendar, outcome table, tool fields and enums; only the seven tool names stay** — page:12; README:71-72 [DOC] · ch06 §14
9. **One hidden brief is raw bank material**: a mail, a policy extract, "a memo that changes it", a code list, in ONE Markdown file with its own tool API file — README:71; page:27, :43 [DOC] · ch06 §14.3 G1
10. **Nothing from a hidden brief may enter the builder after 17:00** (no rule, value or name; holiday dates and outcome names are the stated examples); the reviewer checks the commit — README:73; page:14, :37 [DOC] · ch01 §13.3
11. **Run command and budget:** `python3 builder/build.py {brief_path} {tool_api_path}`, at most 30 minutes per brief including self-tests — page:31, :34; README:89 [DOC] · ch01 §9.2, §12
12. **No trace, not ranked.** The trace needs start and end time, every model call (model + one-line purpose), workflow id, agent id, number of steps and tools, every self-test with its result; plain text; remove API keys — page:32, :37; README:91 [DOC] · ch01 §10
13. **What you export is what is scored** (`freya.export_workflow`, loaded into the organisers' workspace) — README:75; page:31 [DOC] · ch04 §11.7
14. **Top ten are rebuilt from the commit on the same briefs; a reviewer agent reads every trace; "If their run scores clearly below yours, entry removed"** — page:33 [DOC] · ch01 §11
15. **Tie-breaks:** total promised amount on passed cases, then shorter total build time, then earlier submission — README:90; page:27 [DOC] · ch01 §8
16. **The bank does not enforce the brief** (holidays, past-deadline dates, below-floor amounts are recorded); every rule is the agent's job — OA:6; page:25 [DOC] · ch05 §1.1
17. **Bank business errors are HTTP 200 with `ok:false`**; HTTP 500 means "Nothing was recorded. The call may be repeated."; route on `data.ok`, never on the envelope `status` — OA:51, :84 [DOC]; RAT:144 [PROBED-earlier] · ch05 §4
18. **Booleans arrive as strings ("true"/"True"); `equals` is `str(a)==str(b)`; a mismatch fails silently** — WF:296, :372; TC:286 [DOC] · ch02 §10.4
19. **Three separate model calls per user message:** extraction, routing, dialogue; routing never sees `task_message`, so routing rules in prompts do nothing — WF:15-36 [DOC] · ch02 §2.1
20. **Only the current node's `tools` are callable; `tools` survive only on conversation nodes and `pre_actions` only on api_request/code nodes; misplaced arrays are stripped with no error** — WF:35, :79-84; TC:153; API:87 [DOC] · ch03 §1.2
21. **Baking:** a tool parameter whose `default` is a literal or a `{{var}}` set at node entry is sent as-is and hidden from the model; an unset `{{var}}` makes the model fill it; `const` sends nothing — TC:80-93, :99 [DOC] · ch03 §3
22. **Routing runs again right after a tool result, in the same turn**, so a result transition fires "before any further model turn" — WF:410; TC:291 [DOC] · ch02 §10.5
23. **All variables live in one call-wide table and are never cleared on a transition** — WF:178 [DOC] · ch02 §9.1
24. **Passthrough nodes route without waiting; they must end with an `always` transition or they deadlock** — WF:464-468; TC:209, :315 [DOC] · ch02 §11
25. **No `null`; a PUT replaces the whole definition (omitted keys, `test_variables` included, are deleted); an update is not live until published** — WF:64; API:101, :103 [DOC]; README:98 [DOC] · ch04 §4-5
26. **The judge gets only the case's `checks` list ("All of these are true: …"), not the brief; hidden cases have their own unseen checks** — RC:47 [CODE]; page:24, :43 [DOC] · ch07 §1.5
27. **The simulated customer knows no amounts, products or dates and says "Yes, I confirm." to any read-back that matches the conversation**, so only the ledger catches a wrong value — RC:13-24 [CODE] · ch07 §1.3
28. **Final customers "talk like people"**: numbers in pieces, corrections, chatter with a decoy "30th", questions back, words for numbers; the facts and the expected ledger never change with the style — README:78; RC:26-33 [DOC][CODE] · ch07 §1.4
29. **The event's agent model sometimes says nothing after a tool result, or ignores a negative result; the customer then hangs up.** Fix: a post-hook adding a `what_to_do_next` line, plus the prompt rule "never end a turn with nothing" — TC:568-575; README:100, :104 [DOC] · ch03 §18
30. **Latency costs cases:** silence → `customer-ended-call`; an upper-median slowest turn above 10 s triggers a warning, and organisers throw slow runs away ("organisers: a run made while the model was slow is thrown away") — README:100; RC:66-69, :116-118 [DOC][CODE] · ch04 §13.7
31. **Every date rule uses the call variable `now`, never the real clock; `{{system.*}}` dates are the real clock** — A:20; page:14; WF:240 [DOC] · ch02 §9.7
32. **Business days are Mon-Fri minus listed holidays; deadlines count business days strictly after today** (public `now` Wed 2026-10-14: late 7th = 2026-10-23, early 12th = 2026-11-02, attempt-1 date = 2026-10-16) — A:53-60 [DOC]; PTS:165, :622 [CODE]; dates [INFERRED] · ch06 §3
33. **Freya's built-in date extraction turns vague periods into dates and its "today" may be the real clock**, against A rule 21; compute dates in code from `now` — WF:577-578 [DOC]; anchor [UNCERTAIN] · ch02 §13.5
34. **Five sentences are verbatim:** "Am I speaking with {title} {last_name}?", "I am sorry for your loss.", "Can you make this payment today?", "Do you confirm?", "You will receive a text message confirming this promise." — A:25, :35, :77, :88, :92 [DOC] · ch06 §8.1
35. **Before identity is verified nobody (relatives included) may hear "collections", "debt", "payment" or the product; the first sentence must say digital assistant + Freya Bank + call is recorded** — A:24 [DOC]; BA:105 omits "recorded" [CODE] · ch06 §4.1
36. **Identity:** date of birth then phone last 4, one at a time; DOB sent `YYYY-MM-DD`, numbers read day-month-year; 3 wrong in total end the check; a phone answer in words was counted wrong — A:40-43 [DOC]; RAT:151 [PROBED-earlier] · ch06 §4.3
37. **Persuasion ladder:** early band (1-7 days) 1 attempt, late band (8-45) 2; attempt 1 = full amount (or the floor after "too much") on the last business day of this week; attempt 2 = floor on the deadline; a customer's own date or amount is never a refusal — A:59-60, :78-82 [DOC] · ch06 §7
38. **Hardship (illness, a death in the family, job loss) comes before persuasion and restructuring:** one sympathy sentence, offer support once, no attempts — A:83 [DOC]; PTS:212-215 [CODE] · ch06 §4.7
39. **Recording:** read back product, amount, date; "Do you confirm?"; `create_promise` only after a clear yes; say "recorded" only after `ok: true`; one retry; `maxRetries: 0` on writes — A:88, :91 [DOC]; TC:365 [DOC] · ch06 §4.8
40. **Outcome table:** 6 outcomes and 14 reason codes; queue `general` closes with reason `human`; a transfer after a recorded promise closes `transferred` — A:99, :108-117 [DOC] · ch06 §6
41. **Notes:** Brief A never uses `add_note`; Brief B notes every product without a promise (even with one product), writes no note on any transfer, and aggregates the close (`promise` wins; all `paid` → `paid`; else first non-`paid` note's reason) — A:119; B:16-18, :23 [DOC] · ch06 §5
42. **`close_call` as a lifecycle tool is documented two ways:** an unresolved field is "dropped" (TC:115; WF:202) or "one model call fills the parameters" (TC:561); make every field resolve from a variable code sets — [DOC]; BA relies on the fill [INFERRED] · ch03 §5.3
43. **Product ids come only from `get_account` (`p1`, `p2`, …); an invented id gets `unknown product_id`** — README:102 [DOC]; RAT:155 [PROBED-earlier] · ch05 §3.2
44. **Hidden briefs have no practice customers; the only named self-test is `POST /api/v2/chat/message`, which "may skip" a first code step** — page:43 §FAQ; API:252 [DOC] · ch04 §17.3
45. **Practice limits:** one simulation at a time per workspace, 3-11 min per ten cases, one workspace and one Freya key per team, "Do not probe or load-test the platform." — README:88; page:28, :37 [DOC] · ch04 §17.1
46. **Workflows:** 200 per workspace, update in place; `save_workflow` keeps state in `.freya-agents.json` in the current directory, and its first save creates without an explicit publish or model patch — README:87; FP:36-47, :55-60 [DOC][CODE] · ch04 §11.5
47. **Agent model is fixed** (`experimental-5`, `AGENT_LLM`); practice customer and judge are `gemini-3-flash-preview`; leave `agent_config` out of what you send — FP:83-85; README:85, :103 [CODE][DOC] · ch04 §1.3
48. **`examples/base-agent.json` is weak** (2 of 13 in one run): it lacks `add_note`, `schedule_callback`, `transfer_to_agent`, its outcome enum lacks `paid`/`transferred`, its opening omits "recorded", and it carries nulls and undocumented keys — README:34 [DOC]; BA:105, :145, :362-367 [CODE] · ch02 §18
49. **The example builder is not final-ready:** it reads `tools/openapi.json` instead of a passed tool file, its self-test is `run_cases` (useless on hidden briefs), its trace lacks an end time and per-call purposes, and up to 4 test runs can exceed 30 min — SK:12, :22-23; AB:34-38; page:31 [DOC][CODE] · ch04 §16.4
50. **The practice set never exercises** `transferred/human`, `transferred/support`, `no_promise/refused|dispute|service_error`, `not_verified/declined`, `not_reached/no_callback|wrong_number|deceased|unclear`, the swap hint, or B rules 9-11; green practice runs say nothing about them — PTS expected blocks vs A:108-115 [CODE][DOC] · ch07 §15.2

---

## 4. Glossary

Every platform and brief term the chapters use. "Brief" terms come from Brief A/B and change in hidden briefs; their *kind* is expected to stay.

### 4.1 Competition and kit

| Term | Meaning | Source |
|---|---|---|
| Builder | The program you write: reads a brief and its tool API file, creates the phone agent, no manual edits | page:10, :14 [DOC] |
| Phone agent | "software that talks to the customer; a Freya workflow (steps, prompts, tools)". The only thing scored | page:10, :14 [DOC] |
| Brief | "the bank's specification (who to ask for, identity check, allowed payment dates, how to close)" | page:10 [DOC] |
| Clean spec / raw bank material | The two forms of hidden brief. Raw material = a mail, a policy extract, a memo that changes it, a code list, in one Markdown file | README:71; page:43 [DOC] |
| Memo that changes it | An amendment inside the raw brief; the effective rule is the amended one (like B over A: "Every rule of Brief A applies unless a rule below replaces it") | README:71; B:5 [DOC] |
| Code list | A list of codes (likely outcome or reason codes) inside the raw brief | README:71 [DOC]; content [INFERRED] |
| Tool API file | The bank's OpenAPI file; practice = `tools/openapi.json`; each hidden brief has its own | README:44, :72 [DOC] |
| Case | One simulated customer. Practice cases PUB-01..PUB-13 | README:12; PTS [DOC][CODE] |
| Hidden brief / hidden case | The two Sunday briefs and their 30 unseen customers each | page:27 [DOC] |
| Score | Cases passed / 60 | page:27 [DOC] |
| Run (benchmark sense) | One of the 3 repetitions of a case; all 3 must pass | page:27; README:76 [DOC] |
| Tie-break | Promised amount on passed cases → build time → submission time | README:90 [DOC] |
| Build time | Start-to-end time of the builder run, read from the trace | page:32 [DOC] |
| Trace | The builder's log of one run: times, model calls with purpose, what it created, its tests | page:32; README:91 [DOC] |
| Verification / rerun | Top ten rebuilt from the commit; a reviewer agent reads every trace | page:33 [DOC] |
| Probing | Calls made to map or stress the platform; forbidden ("Do not probe or load-test the platform") | page:37 [DOC] |
| Team key | `FREYA_BANK_TEAM_KEY`, a self-made 16+ character secret sent as `x-team-key` to the practice bank | env.example:3; SC:12 [DOC][CODE] |
| Working builder | The unnamed builder behind "Verified in a working builder" statements in the docs (6-node workflow, passed its practice cases). Not BA | WF:5; TC:5 [DOC] |
| BA | `examples/base-agent.json`, the 2-node, 4-tool example agent | README:34 [DOC] |
| Example builder / skill | `examples/agent_builder.py` (Claude Agent SDK) driven by `.claude/skills/build-phone-agent/SKILL.md` | README:47-48 [DOC] |

### 4.2 Freya platform and API

| Term | Meaning | Source |
|---|---|---|
| Workflow | The agent definition: `initial_node`, `nodes`, optional `system_prompt`, `global_nodes`, `test_variables`, `tools`, `agent_config`, … | WF:40-60 [DOC] |
| Agent / agent id | Created with the workflow; simulations take the agent id, chat takes the workflow id | API:54, :210, :247 [DOC] |
| Version / publish | Each PUT saves a new version; only the published version runs in simulations, calls and chat | API:103, :242 [DOC] |
| Slot | `save_workflow`'s own label mapping to one workflow id in `.freya-agents.json` | FP:36-47 [CODE] |
| Export | `freya.export_workflow(id, path)` writes `{workflow_id, agent_id, updated_at, workflow}`; the scored artefact | FP:65-68 [CODE]; README:75 [DOC] |
| `agent_config` | Model, voice and timeout settings; omit it; `update_workflow` patches only the model to `AGENT_LLM` | WF:62; FP:55-60 [DOC][CODE] |
| Node | One step of the call, with its own prompt; types `conversation`, `api_request`, `code`, `end_call` | WF:9, :72-75 [DOC] |
| Conversation node | A dialogue step; carries `task_message`, `tools`, `extraction_schema`, `transitions` | WF:72 [DOC] |
| api_request / code node | Runs `pre_actions` (an HTTP call or a `code_exec` snippet) on entry; normally passthrough | WF:73-74, :464 [DOC] |
| end_call node | Hangs up via its `terminal` function; its `function.name` becomes the call's `endedReason` | WF:613, :652 [DOC] |
| `task_message` / `system_prompt` / `role_message` | Dialogue prompt parts; the engine inserts `## Current Task` between role and task | WF:119-126 [DOC] |
| `on_enter` | Entry behaviour: `llm` (default), `tts` (fixed line, no model call), `silent`, `audio` | WF:159-162 [DOC] |
| `on_enter_first_entry_only` | Run the entry behaviour only on the first visit | WF:95, :164 [DOC] |
| Transition | `{target_node, description, condition, is_tool_call}` in a node's ordered `transitions` list | WF:281-288 [DOC] |
| Condition / operators | Deterministic: `equals`, `not_equals`, `greater_than`, `less_than`, `contains`, `is_set`, `is_not_set`, `always`; semantic: `matches_intent`. Top-level group must be `"logic": "or"` | WF:294-347 [DOC] |
| `matches_intent` | Routing model judges whether the user's last message matches a description; all intents of one evaluation in one call | WF:309-311 [DOC] |
| `always` / self-transition | Unconditional route; a trailing `always` to the node itself keeps the caller there | WF:318, :420 [DOC] |
| Passthrough | `passthrough: true`: routes right after entry without waiting; needs `passthrough_default_transition` and a final `always` | WF:464-468 [DOC] |
| Global node | Interrupt handler checked after the node's own transitions; `excluded_nodes`; `__previous__` returns to the interrupted node | WF:486-526 [DOC] |
| `loop_condition` / `loop_prompt` | Intent for staying in a node / replacement for `task_message` from the second turn (contested) | WF:98-99, :430-432 [DOC] |
| `routing_prompt` | Node-level routing instruction ("extra context" vs "replaces": contested) | WF:97, :416 [DOC] |
| `extraction_schema` | Variables the extraction model fills from user speech; `min_confidence` defaults to 0.95 | WF:530-580 [DOC] |
| Variable table / call variables | One call-wide table; call variables (e.g. `customer_id`, `now`) come with the call or simulation | WF:178-207 [DOC] |
| `now` | The call's date and time variable; every date rule uses it | page:14; A:20 [DOC] |
| `test_variables` | Workflow-level defaults merged "On a web call"; a passed value wins | WF:209 [DOC] |
| System variables | `{{system.*}}` (real clock), `{{call.*}}`, `{{<node>.current_turns}}` | WF:227-240 [DOC] |
| `{{var}}` / `{{var:json}}` | Substitution as string / JSON-encoded; unresolved behaves differently by location | WF:191-203 [DOC] |
| Tool (function object) | `{type:"function", config, function:{name, handler, description, parameters}, response_mapping, pre/post_process_code}` | TC:11-58 [DOC] |
| Handler | `__function__:api_call` (HTTP), `__function__:code_exec` (Python), `__function__:end_call` (hang up) | TC:60-66 [DOC] |
| `pre_actions` | Calls the engine runs on entry to an api_request/code node, before any model turn | TC:149; WF:102 [DOC] |
| Baking | At node entry each parameter `default` is resolved and moved out of the model-visible schema | TC:80-93 [DOC] |
| Model-filled parameter | A parameter with no default or an unset `{{var}}` default; the model supplies it | TC:84-85 [DOC] |
| `response_mapping` | `[{path, variable}]` copying result fields into variables; paths start with `data.`; on the tool for `tools`, on the node for `pre_actions` | TC:223-246, :283 [DOC] |
| Envelope | An `api_call` result: `{status, data, message, status_code, header}`; `data` is the API body | TC:250-262 [DOC] |
| Flattened keys | Automatic variables `<tool>_args.*`, `<tool>_response.*`, `<tool>_status_code` | TC:264-279 [DOC] |
| Success / failure counters | `<tool>_success_count`, `<tool>_failure_count` (`<nodeId>_…` for pre_actions); what counts as failure is undocumented | TC:321-328 [DOC] |
| Lifecycle tool | Workflow-level tool with `config.alwaysRunsAt`: `start_of_call`, `end_of_call` (`each_turn` never fires); never shown to the model | TC:514-564 [DOC] |
| Pre-hook / post-hook | `pre_process_code` (gets `vars`, `config` = the request) / `post_process_code` (gets `result` = the envelope); only on `api_call` | TC:367-416 [DOC] |
| `what_to_do_next` | A line a post-hook adds to `result["data"]` so the model knows what to say next | TC:573 [DOC] |
| `vars` | The dict a code snippet reads and writes; every assigned key becomes a workflow variable | TC:456-460 [DOC] |
| `suppress_tool_results` | Model sees only `{status: "success"}` instead of the result; variables still mapped | TC:341 [DOC] |
| `maxRetries` / `timeoutMs` / `connect_retries` | Tool-level retries (default undocumented) / attempt timeout / transport retries (default 2, cap 5, baked parameter) | TC:347-363 [DOC] |
| `max_node_turns` / `max_turn_transition` | Turn cap (default 10) and its target; without a target the cap does nothing | WF:106-107, :662-663 [DOC] |
| `terminal` / `message_mode` / `spoken_message` | End-call function; `custom` (say `spoken_message`), `llm`, `none` | WF:639-646 [DOC] |
| `endedReason` | Why a call ended: the terminal's `function.name`, or `customer-ended-call` | WF:652; README:100 [DOC] |
| Persona | Simulated caller: `name`, `prompt`, `successCriteria`, `tags` | API:143-164 [DOC] |
| `successCriteria` | Text the judge checks; run_cases builds it as "All of these are true:\n- " + checks | API:161; RC:47 [DOC][CODE] |
| Simulation | One test job: agent vs personas, `mode: "chat"`, per-persona call variables, model overrides | API:180-226 [DOC] |
| Iteration | "one execution of the simulation" | API:264 [DOC] |
| Run (platform sense) | "one call with one persona", with the judge's `outcome` and `reason` | API:276-290 [DOC] |
| Call / event log | `GET /api/v2/call/{id}`: `messages` (with `node_enter`, `function_call_start`, `function_call_complete`, `route_evaluated`, `error`), `transcript`, `endedReason` | API:292-336 [DOC] |
| Chat | `POST /api/v2/chat/message`: one turn against the published workflow, no simulation, no queue, not judged | API:240-252 [DOC] |
| Judge | The simulation's analysis model (`gemini-3-flash-preview` in practice) checking `successCriteria` | FP:85, :95 [CODE] |
| Slowest turn | Per call, the longest gap from a customer message to the agent's next reply; run_cases reports median and worst | RC:101-118 [CODE] |

### 4.3 Mock bank and harness

| Term | Meaning | Source |
|---|---|---|
| Mock bank | Freya-hosted mock at `https://freya-bank-mock.freyavoice.workers.dev/v1`; seven POST tools, no key; `customer_id` is "the secret of one call" | OA:6, :10 [DOC] |
| Ledger | The bank's record of one customer: `outcome`, `reason`, `promises`, `notes`, `callbacks`, `transfers`, `calls[]` (every call, rejected ones included), `verified`, `wrong`, `hinted`, `failures`, … | SC:17-34 [CODE]; RAT:133-141 [PROBED-earlier] |
| Practice session | `POST /v1/practice/sessions {"case": "PUB-xx"}` with the team key: a fresh single-use customer; `now` fixed at 2026-10-14T11:00 | RC:86 [CODE]; RAT:126-130, :159 [PROBED-earlier] |
| `expected` / `checks` / `faults` | Per case: the ledger the scorer wants / the judge's success criteria / injected failures (`fail_first_n`) | PTS [CODE] |
| Style | One of `pieces`, `corrects`, `talkative`, `asks_back`, `in_words`; changes how the customer speaks, never the facts | RC:26-33 [CODE] |
| `--reps N` / `--rerun-if-slow K` | Require all N runs to pass / discard and repeat a slow run up to K times | RC:50, :65-73 [CODE] |
| `ok` / `error` | Every bank 200 response: `ok` false "when the action was not carried out", with an `error` string | OA:51 [DOC]; RAT:144 [PROBED-earlier] |
| `all_verified` / `wrong_answers_left` / `hint` | `verify_identity` response fields; `hint` enum `day_month_swapped` | OA:57-77 [DOC] |
| Fault injection | Server-side failure of a tool per case (PUB-10: first `create_promise`); its HTTP form is unknown | PTS:435-440 [CODE] |

### 4.4 Brief terms (Brief A/B; values change in hidden briefs)

| Term | Meaning | Source |
|---|---|---|
| Opening sentence | First sentence: digital assistant + calling from Freya Bank + call is recorded | A:24 [DOC] |
| Banned words | "collections", "debt", "payment" or the product, before identity is verified, to everyone | A:24 [DOC] |
| Confirmation ask | "Am I speaking with {title} {last_name}?"; only "yes", "that's me", "speaking" or the own name confirm; 2 asks | A:25-26 [DOC] |
| Third party | Someone else answers: say nothing beyond the opening, ask when the customer can be reached | A:31-36 [DOC] |
| Callback window | Today or the next business day, 10:00-19:00 inclusive, strictly later than `now`; time `HH:MM` | A:32; OA:317 [DOC] |
| Identity check / security questions | DOB then phone last 4, one at a time; 3 wrong in total end it | A:40-41 [DOC] |
| Decline | Refusing the security questions, or asking what the call is about instead of answering; a second closes `not_verified`/`declined` | A:44 [DOC] |
| Debt statement | Collections team + late payment + product in words + past-due amount + days late | A:49 [DOC] |
| Product name templates | "credit card ending {card_last4}", "personal loan", "car loan" | A:49 [DOC] |
| Business day | Monday to Friday except the brief's holidays | A:53 [DOC] |
| Band | Early (`days_late` 1-7) or late (8-45); decides deadline and attempts | A:55-60 [DOC] |
| Deadline | Latest valid promise date: 12th (early) or 7th (late) business day after today | A:59-60 [DOC] |
| Floor | Lowest acceptable amount: `minimum_payment` (card) or `instalment_amount` (loans) | A:71 [DOC] |
| "Too much" | Customer says the full amount is too much: offer the floor once, say the rest stays overdue | A:72 [DOC] |
| First ask | "Can you make this payment today?" (B: one combined ask for all products) | A:77; B:12 [DOC] |
| Proposal | A date or amount the customer proposes; "never a refusal" | A:78 [DOC] |
| Flat refusal | A no (or non-answer) with no date and no amount; uses one persuasion attempt | A:79 [DOC] |
| Attempt (persuasion attempt) | An agent proposal after a flat refusal: attempt 1 = last business day of this week; attempt 2 (late only) = floor on the deadline | A:79-81 [DOC] |
| Attempts used up | Stop, never repeat a refused offer, close `no_promise`/`refused` (B: note `refused`) | A:82 [DOC] |
| Hardship | Illness, a death in the family, job loss: one sympathy sentence, no persuasion, offer support | A:83 [DOC] |
| Read-back | Product, amount and date read back, then "Do you confirm?"; create only after a clear yes | A:88 [DOC] |
| Text-message sentence | "You will receive a text message confirming this promise.", after a recorded promise | A:92 [DOC] |
| Already paid | "I already paid" this past-due amount: one business day to appear, close `paid` | A:96 [DOC] |
| Dispute | Not mine / never had it / closed or paid off in the past: no argument, `no_promise`/`dispute` | A:97 [DOC] |
| Restructuring | A new plan or lower instalments: transfer queue `restructuring` | A:98 [DOC] |
| Human request | Ask once whether you can help; if they insist, queue `general`, reason `human` | A:99 [DOC] |
| Outcome / reason | The `close_call` pair from the brief's outcome table | A:108-115 [DOC] |
| Note | Brief B `add_note(product_id, reason)` for a product without a promise | B:16 [DOC] |
| Closing aggregation (B) | `promise` wins; all `paid` → `paid`; else reason of the first non-`paid` note in `get_account` order | B:23 [DOC] |
| B6 clamp | One date for all, past one product's deadline: that product goes on its own deadline, said in the read-back | B:14 [DOC] |

---

## 5. Contradictions between sources, and their status

Sources that disagree with each other, or chapters that disagree with each other. "Open" items link to the open-question IDs of chapter 08. C-numbers are chapter 08's register (ch08 §8).

### 5.1 Source against source

| ID | Side 1 | Side 2 | Status |
|---|---|---|---|
| C-01 | An unresolved field in a lifecycle tool is dropped (TC:115; WF:202) | "one model call fills the parameters" (TC:561) | **Open** → Q-01. BA's 2/13 pass implies the fill happened [INFERRED]. Design: make every field resolve |
| C-02 | Any unset engine-run field is dropped (TC:115) | Only an exact single placeholder is dropped; a mixed value is sent with the literal `{{x}}` (WF:202) | Open in detail; avoided by never mixing text with a possibly unset variable (WF:203) |
| C-03 | "Transitions are checked in list order" (WF:406); self-`always` waits "until an earlier transition matches" (WF:420) | "Deterministic conditions are evaluated first" (WF:407) | **Open** → Q-04. Never mix `matches_intent` with a trailing `always` until settled |
| C-04 | `routing_prompt` is "Extra context" (WF:97) | It "replaces the default intent-matching instruction" (WF:416) | Open → Q-17. Avoid it |
| C-05 | `loop_prompt` applies "from the second turn" (WF:99, :133, :432) | Applies when `loop_condition` matches (WF:398); with no match the agent answers "from the same `task_message`" (WF:412) | Open → Q-17. Avoid it |
| C-06 | A first passthrough code node runs before the agent speaks (verified, WF:484) | Chat "may skip it" (seen, not guaranteed, API:252) | **Open** → Q-05, Q-14. Chat is not a faithful copy of a simulation |
| C-07 | "A `null` fails validation" (WF:64) | README posts BA unchanged (README:23) with 4 nulls (BA:145, :151, :320, :326) and reports a run (README:34) | Open → Q-08(f). Send no nulls anyway |
| C-08 | "The schema is strict" (WF:64) | Fields that do not belong are stripped silently (WF:79-84; API:87; TC:153) | Open → Q-08(g). Read the stored workflow back after save |
| C-09 | `save_workflow` updates and publishes (API:115; README:98) | A new slot only calls `create_workflow` (FP:45-46) | Open → Q-08(a). Simulations still ran right after a first save (README:22-24), so create probably publishes [INFERRED] |
| C-10 | Workspace parameter name "not confirmed" (API:139) | `workspaceId` used (API:107; FP:57, :61, :67) | Resolved in practice: `workspaceId` on those routes |
| C-11 | "The reference client does not call this route" (GET workflow, API:127) | freya.py calls it (FP:57, :67) | Resolved: api.md is stale here [INFERRED] |
| C-12 | Fall back to the bare payload for `workflow` (API:44) | freya.py indexes `["workflow"]` directly (FP:33, :57, :67) | Moot unless a `KeyError` appears |
| C-13 | `get_iteration` "compares with runsTotal" (API:288) | It reads until a short page and never compares (FP:72-78) | Resolved: the code wins |
| C-14 | A PUT deletes a platform-filled `agent_config` (API:101) | "The platform fills in a default agent_config" (FP:55) | Open → Q-08(c) |
| C-15 | "Leave `agent_config` out" (WF:62; README:103; SK:19) | `update_workflow` PUTs `agent_config` back with the event model (FP:60) | Not a real conflict: builder omits it, client sets only the model. Whether the export should carry it is open (O-7) |
| C-16 | Reference client "prints the response body" on a dry-run error (API:85) | `validate_workflow` raises `RuntimeError` (FP:19, :48) | Resolved: the code wins |
| C-17 | `run_simulation` docstring: 2 return values (FP:88) | Returns 3 (FP:106; RC:88 unpacks 3) | Resolved: 3 |
| C-18 | `code` is templated and an unset `{{var}}` crashes (TC:116) | "The internal sources disagree" (TC:494); the tool form resolves at call time (TC:512) | Moot: never write `{{` or `}}` in code |
| C-19 | Pre-hook `vars` "fills the `{{var}}` placeholders of the request" (TC:395) | `config` is "the substituted request" (TC:395) | Open → Q-12. Edit `config['body']` directly, as BA does (BA:395) |
| C-20 | Internal reference: post-hook `result` is the body (TC:407) | Working builder: it is the envelope (TC:409) | Resolved: envelope (verified) |
| C-21 | Post-hook name table lists only `result` (TC:396) | A post-hook reads and writes variables (TC:416, seen) | Open → Q-12 (under which name) |
| C-22 | `suppress_tool_results` shows only `{status: "success"}` (TC:341) | The silence fix needs the model to read `what_to_do_next` (TC:573) | Open → Q-20. Do not combine them |
| C-23 | Example post-hook tests `d.get('verified')` by truthiness (TC:389) | "Booleans arrive as strings" (TC:286) | Open → Q-12 (native types inside the hook are likely) |
| C-24 | Routing runs "After each user message" (WF:395) | It also runs after a tool result (WF:410; TC:291) | Not contradictory; what the post-result pass includes is open → Q-03 |
| C-25 | "two integer variables per call target" (TC:321) | The seen table lists only `_success_count` (TC:277) | Open → Q-02 |
| C-26 | `connect_retries` default 2 (TC:353) | The example declaration uses `default: 0` (TC:363), which disables it | Resolved by declaring it explicitly |
| C-27 | A malformed lifecycle tool is dropped at run time; "Validate with a dry run" (TC:564) | A dry run checks only the write-time schema (API:75, :87) | Open → Q-01. Check the ledger after every publish |
| C-28 | Same-turn routing "Seen in a trial call" (TC:291) | "Verified in a working builder" for mapped variables (WF:410) | Evidence grade only |
| C-29 | Tool description is "The only text the model reads about the tool" (TC:167) | Parameter descriptions and enums are shown too (TC:85) | Not a real conflict: write both levels |
| C-30 | "Every call is written to the ledger" (OA:6) | A 500 means "Nothing was recorded" (OA:84) | Reconciled [INFERRED]: the call log yes, the business record no → Q-11 |
| C-31 | "The service does not enforce the brief" (OA:6) | The bank enforces the identity gate, one promise per product, nothing after close (OA:91, :174, :411) and the outcome/reason pair (RAT:159) | Reconciled: data validity is enforced, policy is not |
| C-32 | `reason` is not in `required` (OA:438-441) | "Required for every outcome except promise and paid" (OA:435) | The practice bank enforces the pair [PROBED-earlier]. Build `reason` from the brief's table |
| C-33 | A 500 "may be repeated", no limit (OA:84) | "If it fails, try once more" (A:91) | Resolved: the brief sets the policy (at most 2 tries) |
| C-34 | BA's `close_call` outcome enum has 4 values (BA:362-367) | OA has 6 (OA:424-431); BA's own pre-hook handles `paid` (BA:395) | Fact: BA is stale. Generate enums from the tool file |
| C-35 | BA's identity prompt defers "what is this about" (BA:140) | Rule 15 counts that question as declining (A:44) | Fact: follow the brief |
| C-36 | BA has no `end_call` node and caps turns with no target (BA:142, :145) | "Every path must reach an `end_call` node" (WF:680); cap needs a target (WF:672) | Fact: do not copy BA |
| C-37 | "Run your builder once on each" (README:74; page:12) | "You may run it more than once and submit the phone agent of one run" (README:89; page:31) | Resolved: several runs allowed; submit one run's agent with that run's trace |
| C-38 | Example builder takes only brief paths; skill reads `tools/openapi.json` (AB:33; SK:12) | Final run command passes `{tool_api_path}` (page:31) | Resolved for our builder: take both arguments |
| C-39 | Pass both briefs for B (README:29) | The skill tests with `--brief B`, which runs only PUB-11..13 (SK:22) | Irrelevant to our builder |
| C-40 | run_cases "prints the slowest agent turn per call" (README:100; page:45) | It prints only the median and worst; per-call values only in `--out` (RC:114-117) | Resolved: the code wins |
| C-41 | "offer the floor, once" (A:72) | Attempt 1 is "for the floor" after "too much" (A:79); "Attempt 2 may name the floor again" (A:72) | **Open** → I-21 (see also §5.2 row K-1) |
| C-42 | Rule 15: "a second such question closes the call" (A:44); rule 3 allows two asks (A:26) | `asks_back` asks twice then answers, with the same expected outcome (RC:26, :31; README:78) | **Open** → I-03, I-04. Count only questions or refusals that *replace* an answer |
| C-43 | "except rule 10 above" (B:23) | A:117 covers any transfer after a promise; B:18 lists "any transfer (restructuring, support, human)" | Open → I-34. Default: any transfer closes `transferred` with its reason |
| C-44 | Vague period → ask once for the exact day (A:64) | Built-in extraction turns "next week" into a date (WF:578) | Design issue → Q-13. Resolve dates in code |
| C-45 | WF's example combines `on_enter_first_entry_only`, a self-`always` and a turn cap (WF:701, :707-708, :726) | `current_turns` "Resets on every transition" (WF:237) | Open → Q-15 |
| C-46 | WF's `offer` node tells the model to report the booking after the tool result (WF:773) | The same-turn transition goes to a silent `none` end node (WF:808, :815, :823) | **Open** → Q-03. Put required sentences in entry lines of the next node |
| C-47 | "payment" banned before verification "for everyone, including relatives" (A:24) | A relative offers to pay (A:36; PTS:73) and the natural refusal uses the word | Wording → I-10: refuse without naming anything |
| C-48 | Page example: "Can you pay today?" and a read-back without the product (page:8) | Brief: verbatim "Can you make this payment today?" (A:77); read-back names the product (A:88) | Resolved: the brief governs; the page example is illustrative |
| C-49 | `test_variables` merged "On a web call" (WF:209) | The channels used are chat simulations (`call.direction` = `web`, WF:234) and `chat/message` | Open → Q-05(d). Seed state in code instead |
| C-50 | Every persona's DOB sentence carries the example "'14 March 1988'" (RC:41) | That is PUB-01's real DOB (PTS:15) and the dashboard customer's (page:42) | Data trap → I-42 |
| C-51 | `talkative`: "wedding is on the 30th … never offer it as a payment day" (RC:30) | PUB-13's customer really wants 30 October (PTS:609) | Data trap → I-43 |

### 5.2 Chapter against chapter, and chapter against source

These were found while building this index. Where a chapter disagrees with a primary source, the source wins.

| ID | Disagreement | Evidence | Resolution |
|---|---|---|---|
| K-1 | **Is the single floor offer itself attempt 1?** ch06 (U-1, §7) and ch08 (I-21 default (a)) say yes: one floor offer on the attempt-1 date. ch07 §7(d)/§7(i) uses the opposite reading: floor for today first, then attempt 1 proposes only the Friday date. | A:72, :79; PTS:247-260 fit both | **Open.** Pick one reading for the whole builder. The behaviour differs only after a refusal of the floor. Settle with two agent variants on `--only PUB-06 --reps 3` (I-21) |
| K-2 | **How rule 15 counts declines.** ch06 §4.3 rule 15 reads one shared counter where "any two declines close the call" (the strict reading). ch06 U-4, ch07 §1.9(6) and ch08 I-04 default to a lenient count (only consecutive questions or refusals that replace an answer). | A:44; RC:31 | Use the lenient count; the strict one fails `asks_back` cases whose expected outcome is unchanged (RC:26) |
| K-3 | **Are call variables other than `now` verified in code?** ch08 Q-19 (last row) and its verdict on earlier error 9.3-15 say only `vars.get("now")` is verified. ch02 §9.3 and ch03 §22.1 #1 cite WF:221, which verifies `vars.get("customer_id")`. | WF:221: "Verified in a working builder: call variables are readable as `{{customer_id}}` … and as `vars.get("customer_id")` in code." | **ch08 is wrong on this point; WF:221 settles it.** Call variables are in `vars` [DOC] |
| K-4 | **Sets or multisets.** ch08 I-40 says "The ledger compares sets (SC:23-24)". | SC:22-27 compare sorted lists, so duplicates count (ch06 N1) | Multisets. A duplicate note, promise, callback or transfer fails the case |
| K-5 | **Rule 21 citation.** ch06 §11 table cites "(A:83)" for "If they still give none, propose the deadline." | That sentence is A:64; A:83 is the hardship rule | Citation error in ch06; the fact is right |
| K-6 | **Who speaks first in a chat simulation.** One case note says "The agent speaks first" [INFERRED]; other notes and ch07 §1.9(1) mark it [UNCERTAIN]; ch08 Q-14 gives "agent first via `on_enter`" as a best guess. | RC:13 (persona waits); BA:104-107 (tts entry line); API:247 (chat example sends "Hello?" first) | Open → Q-14. Design so either order works; a customer "Hello?" is not a confirmation (A:26) |
| K-7 | **Calls after `close_call` in the ledger.** ch01 Q10 says they are "likely" logged [INFERRED]; ch04, ch05 and ch08 keep it [UNCERTAIN]. | OA:411; SC:29; RAT:154, :159 | Same conclusion either way: no tool may run after `close_call` |
| K-8 | **Earlier status of PUB-06.** An earlier version of ch08 listed "the floor offer is not itself a persuasion attempt" as resolved; ch08 R-06 now says only the expected promise (637.5 on 10-16) is settled. | ch08 R-06 | Treat as open (K-1) |
| K-9 | **The earlier research summaries** (`research/read-*.md`) contain 86 errors, mostly overstatements: 19 in RAT, 15 in RRC, 22 in RTC, 30 in RWF. One case note has five wrong line citations. | ch08 §9-10 | Never copy a claim from those files without checking the kit |

---

## 6. The top 10 open questions and the experiment that settles each

All are chapter 08's Tier 1 (ch08 §2). Every experiment is normal kit usage once a Freya key exists: our own workflow, our own practice sessions, documented routes, no probing (page:37). Toolkit: **E-RUN** (`run_cases.py … --out`), **E-EVENTS** (`freya.get_call(id)["messages"]`), **E-LEDGER** (`GET /v1/practice/ledger/{customer_id}`), **E-CHAT** (`/api/v2/chat/message` with a fresh practice session's variables), **E-SAVE** (dry run, save, versions GET, export), **E-LAB** (one lab workflow in one fixed slot). Chapter 08 §11 batches them: S-1 save/diff, S-2 one chat, R-1 BA on Brief A, R-2 BA on Brief B, L-1 lab chats, R-3 PUB-10 with a diagnostic hook, R-4 styles × `--reps 3`.

| Rank | ID | Question | Why it matters | Current best guess | Experiment that settles it | Cost |
|---|---|---|---|---|---|---|
| 1 | Q-01 | How does `close_call` get `outcome`/`reason` when its fields are unresolved (dropped, TC:115/WF:202, or model-filled, TC:561)? Does an `end_of_call` tool fire on a customer hang-up or the 420 s limit? Do hooks run on lifecycle tools? | Every case needs `close_call` last with the exact pair (SC:19-20, :28-29) | Model fill is real (BA passes some cases with nothing set) [INFERRED]. Never depend on it: bake every field from variables code sets | Save BA unchanged; `run_cases.py <agent> --brief A --out results/base-a.json`. Per row read the ledger's `calls[-1]` args and the `close_call` `function_call_start` event: outcome present and varied = fill; absent = drop; `paid`/`transferred` present = enum does not bind the filler; promise row with null reason = pre-hook ran after fill. Check rows with `ended = customer-ended-call` still end in `close_call` | Part of the first normal run (3-11 min) |
| 2 | Q-02 | What does a failed tool call look like: HTTP 500 (OA:84) or 200 `ok:false` (RAT:144)? What envelope, counters, mapping and post-hook behaviour does Freya show? Does `maxRetries` re-send invisibly? | Honesty and the one-retry rule (A:91; PTS:432-433) depend on detecting failure | PUB-10's fault is a 500 [INFERRED]. Treat anything but an explicit `ok` true from the latest call as failure; `maxRetries: 0` on writes | Agent with `create_promise` `maxRetries: 0` and a post-hook writing `dbg_status`, `dbg_code`, `dbg_dtype`, `hook_ran` into `result['data']`; a code step sets the mapped flag to `pending` first. `--only PUB-10 --out`. Read both `function_call_complete` events, the next `route_evaluated.variable_table` (`create_promise_failure_count`, `_status_code`, mapped flag) and the ledger `calls[]`/`failures`. Optional rerun with `maxRetries: 1` | One short run |
| 3 | Q-03 | After a tool result moves the call to another node in the same turn (TC:291), does the old node's model speak? Does a silent target leave dead air? Does the post-result pass re-judge intents and globals? | Every check-named sentence after a tool result ("recorded", the text-message sentence, app-or-branch, goodbye) depends on it; silence → hang-up | The old node does not speak again; the target's entry line speaks [INFERRED]. Put fixed sentences in `tts` entry lines of nodes reachable only on the success flag | In the R-1 events for PUB-01, look between the second `verify_identity` `function_call_complete` and `node_enter collection`. E-LAB: copy WF's `offer`→`goodbye_booked` pattern around `schedule_callback` (`data.ok → cb_ok`, `cb_ok is_set` → silent `none` end node) on a fresh PUB-02 session in one chat; see whether an assistant message follows the tool | First run + one chat |
| 4 | Q-04 | Route order: list order (WF:406) or deterministic first (WF:407)? Does a trailing self-`always` pre-empt intents and block global nodes? How does same-target merging (WF:408) place the merged route? | Decides whether interrupts (robot, scam, human, hardship, dispute, paid, restructuring) can be intents or globals | [UNCERTAIN]. Never mix `matches_intent` with a trailing `always`; fork on an extracted enum with `equals` (WF:584) | E-LAB, three short chats: (1) `[matches_intent "says banana" → t_a (tts A-HERE), always → self]`, send "banana"; (2) add global `g_x` ("says mango", tts G-HERE, `__previous__`), send "mango" from a node with and without a self-`always`; (3) `[equals flag "on" → X, intent "orange" → Y, always → X]` with `flag` unset, send "orange". Read `route_evaluated` `branches`/`target`/`reason` | Three chats |
| 5 | Q-05 | Can an agent for a hidden brief be self-tested? Do chat turns run tools against the bank? Does chat skip a first code node (API:252 vs WF:484)? Does `get_call` work on chat ids? Is `test_variables` merged? What is the body of later turns? | Hidden briefs have no practice cases (page:43); 30-minute budget | Chat runs tools but may skip a first code step [INFERRED]. Realistic self-test = static checks + dry run + read-back diff + a few pre-identity chat turns | Fresh PUB-01 session variables. Lab workflow: initial passthrough code node writes `vars['boot']='ran'`; next node tts "BOOT {{boot}}" with `verify_identity`; `test_variables` `tv_check: "TV-OK"`. Turns: "Hello?", then `{callId, message: "Yes, speaking."}`, then "14 March 1988". "BOOT ran" vs "BOOT {{boot}}" shows the skip; read `get_call`, ledger `calls[]`, `variable_table`; end with `/chat/end` | About one minute |
| 6 | Q-06 | Variable values: which writers produce `"true"` vs `"True"`; are stale flattened keys cleared when a later response lacks them (RAT:153); does `""` count as set; `equals` on `"420"` vs `"420.0"`; automatic key names for `pre_actions` calls; form of a mapped list | Every deterministic route rests on these; mismatches fail silently (WF:372) | Route only on string flags our own code writes; reset flags before every call | E-LAB chat: code writes `vars['f_bool']=True`, `vars['e']=''`, `vars['t']='abc'`; a tool maps `data.verified → v_map`; routes test `is_set e`, `greater_than t 1`, `equals` on numbers; on PUB-01, re-verify DOB after verification and diff `variable_table`; map `data.products` and have code write its type | Lab chats |
| 7 | Q-07 | Can code-computed values be baked into tool arguments? When are defaults resolved (node entry, TC:93)? Does `""` bake empty? Is `{{x}}` sent as a string and `{{x:json}}` as a number? Which name does the model see when key ≠ placeholder? | The surest way to stop invented ids, amounts and dates (README:102) | Yes if set before the node is entered [DOC]; use `{{amount:json}}` for numbers [INFERRED]; keep key = placeholder (TC:95) | PUB-01 session after verification: a code step sets `cp_pid='p1'`, `cp_amt=420.0`, `cp_date='2026-10-14'`; a pre-action `create_promise` bakes them; read `function_call_start.body` and ledger `promises[].amount`; repeat with `:json` on a second session; test a value set mid-node and a self-transition re-entry | Lab chats |
| 8 | Q-08 | Save/publish/`agent_config`: does create publish? Is the default model the event model after create? Is `agent_config` absent or re-filled after a PUT? Is a null or unknown key rejected or stripped? Which fields are required? What does a dry run return? Does GET return the newest or the published version? | A workflow that cannot start a call scores zero (README:103); "what you export is what we score" (README:75) | Create probably publishes; run `update_workflow` once after create to patch the model; never send nulls or unknown keys | After the first `save_workflow`, versions GET (`isPublished`), GET the workflow (`agent_config.llmConfig`), dry-run BA as-is and without nulls, save a node with one unknown key and read it back, export and diff against what was sent | Seconds, no simulation |
| 9 | Q-09 | What will the hidden briefs and cases look like (identity fields, outcome names, calendar, host and paths of the tool file, `now` format, per-case styles)? | Everything taken from the public briefs instead of the input brief breaks | Same mock family; different identity enum and outcome table; possibly business customers (RC:43); possibly a renamed not-reached outcome (SC:33) [INFERRED] | **Not settleable** before Sun 17:00 UTC. Robustness only: mutated or raw-material rewrites of Brief A on the practice bank, a custom cases file with per-case `style` (run without `--style`), a harness change that re-dates `now` | — |
| 10 | Q-10 | What does the judge see (transcript text or tool events)? Does it fail rules no check lists? Same model and prompt in the final? Do `successCriteriaResult` and the run outcome agree? | Decides whether tool facts must also be spoken, and how literal wording must be | Follow every brief rule; speak outcomes so the transcript agrees with the ledger; say fixed sentences word for word [INFERRED] | No extra run: in R-1, compare judge `reason` for PUB-01, PUB-02, PUB-09, PUB-10 with the spoken transcript and the events. A reason citing a tool call nobody spoke about means the judge sees events. Compare `successCriteriaResult` with run outcomes | Free with R-1 |

Questions only the organisers can answer (ch08 §6): O-1 may a test copy call our own mock; O-2 slow-run repeat count and threshold; O-3 final judge model and prompt; O-4 `now` format and hidden call variables; O-5 will hidden tool files keep the mock host and paths; O-6 persona limit or delete route; O-7 should the export carry `agent_config`.

---

## 7. Where to go next

- For any fact above, open the chapter named after it; every chapter cites file and line.
- For the brief side of the design, ch06 §14 (the 29-component schema G1-G29) is the bridge from Brief A/B to "any brief of this kind".
- For the platform side, the traps lists at the end of ch02 (46), ch03 (48), ch04 (46), ch05 (20), ch06 (39), ch07 (51) and ch08 (36) are the condensed checklists.
- Before designing, run the ch08 §11 batch (S-1, S-2, R-1, R-2) once; it settles Q-01, Q-02, Q-03 step 1, Q-05, Q-08, Q-10 and part of Q-06 with normal kit use.
