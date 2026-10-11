# Chapter 4: The Freya REST API, `freya.py`, and the test harness

## In short

- The builder talks to one REST API at `https://staging-app.freyavoice.ai`. It needs a `fak_…` Bearer key and a browser-like `User-Agent`, or it gets an HTML `error code: 1010` page. Every JSON answer is `{success, data: {message, result}}`, and the payload is `data.result` (api.md:13-18, 30-42).
- `POST /api/v2/workflow` creates a workflow and its agent together. `PUT /api/v2/workflow/{id}` replaces the whole definition and saves a new version that is **not published**. Simulations, calls and chat all run the **published** version, so every update needs a publish (api.md:101-115, 242).
- `freya.update_workflow` does PUT, then a model fix, then publish. `freya.save_workflow` creates on the first call for a slot and updates afterwards, but its create path neither publishes nor fixes the model (freya.py:31-64).
- A **simulation** runs the agent (model `experimental-5`) against **personas**. A persona is a caller prompt plus success criteria. `gemini-3-flash-preview` plays the caller and judges the call. A workspace runs one simulation at a time, and a 10-customer run takes 3 to 11 minutes (freya.py:84-95; README.md:88).
- `POST /api/v2/chat/message` runs one turn in seconds against the published workflow. For a brief with no practice customers, it is the only documented way to talk to the agent (api.md:240-252; page §FAQ).
- `GET /api/v2/call/{id}` returns the transcript and the engine's events: `node_enter`, `function_call_start`, `function_call_complete`, `route_evaluated` and `error`. It is the main debugging tool (api.md:292-336).
- `tools/run_cases.py` turns each practice case into a persona, opens a fresh mock-bank session per case and runs one simulation. A case passes only when all eight ledger checks in `tools/score.py` pass **and** the judge says `pass`. `--reps N` requires every one of N runs to pass, as the final does (run_cases.py:84-99; score.py:17-34).
- In the final, the organisers test the exported workflows on 30 unseen customers per brief, 3 runs each (page §Evaluation; README.md:75-76).
- A hidden-brief build has 30 minutes including self-tests, and no practice customers. The rules say "Do not probe or load-test the platform." (README.md:89; page §FAQ, §Rules).
- The kit does not confirm many API details. Examples: the dry-run result, the GET-workflow fields, the body of later chat turns, the full set of status values, and the name of the workspace parameter. §18 lists every unknown.

---

## 0. Sources, labels and conventions

**Primary sources.** All were read in full. Paths are relative to `kit/build-the-builder/` unless they start with `research/` or `knowledge/`.

| Short name | File | Lines |
|---|---|---|
| api.md | `docs/api.md` | 349 |
| freya.py | `freya.py` | 106 |
| run_cases.py | `tools/run_cases.py` | 121 |
| score.py | `tools/score.py` | 39 |
| agent_builder.py | `examples/agent_builder.py` | 52 |
| SKILL.md | `.claude/skills/build-phone-agent/SKILL.md` | 30 |
| README.md | `README.md` | 104 |
| env.example | `env.example` | 3 |
| VERSION | `VERSION` | 1 (the value is `3`) |
| page §X | `research/hackathon-page.md`, the tab named X (Overview, Data, Evaluation, Submit, Rules, FAQ) | 45 |

I also cross-read the parts of `docs/workflow-format.md`, `docs/tools-and-code.md`, `tools/openapi.json`, `public-test-set.json` and `examples/base-agent.json` that the API and the harness depend on.

**Notes checked against the sources:** `knowledge/notes/api.md` and `knowledge/notes/harness.md`. Where a note and a source disagree, the source wins. §19 lists the disagreements. Facts marked [PROBED-earlier] come from `research/read-api-and-testing.md`. That file records live calls made on 2026-10-10 to the **mock bank only**. "There is no Freya key yet, so I could not test any Freya route" (research/read-api-and-testing.md:5-7). None of those calls was repeated.

**No network calls were made for this chapter.** I ran three offline checks in Python:
1. I rendered the persona text by loading `tools/run_cases.py` and calling only `persona_for`, which does no I/O.
2. I ran a copy of the slowest-turn loop on synthetic message lists.
3. I tested one `sorted()` edge case.

Nothing was written into the kit.

**Labels**

| Label | Meaning |
|---|---|
| [DOC] | Stated in a kit document (api.md, README, workflow-format.md, tools-and-code.md, SKILL.md, the openapi descriptions) or on the hackathon page |
| [CODE] | Read from kit code (freya.py, run_cases.py, score.py, agent_builder.py) or kit data (public-test-set.json, base-agent.json) |
| [PROBED-earlier] | From the earlier mock-bank calls in research/read-api-and-testing.md; not repeated |
| [INFERRED] | My reasoning from the sources |
| [UNCERTAIN] | Not known; the text says exactly what is missing |

---

## 1. The moving parts

### 1.1 Who talks to whom

```text
 Your builder (a program)
   |  REST, Bearer fak_ key, browser-like User-Agent
   v
 Freya platform  https://staging-app.freyavoice.ai
   |- workflow  (+ the agent created with it, + numbered versions, one published)
   |- personas  (caller prompt + success criteria)
   |- simulations -> iterations -> runs -> calls   (text calls, judged)
   |- chat turns  -> a call                        (one turn at a time, not judged [INFERRED])
   |
   |  the agent's api_call tools: HTTP sent by Freya during a call
   v
 Mock bank  https://freya-bank-mock.freyavoice.workers.dev
   |- /v1/<tool>      7 tools, no key; "the customer_id in the body is the secret of one call"
   |- /v1/practice/sessions, /v1/practice/ledger/{customer_id}   need x-team-key
   ^
   |  only the harness (run_cases.py / score.py) calls the practice routes
 Your machine
```

Sources:
- Freya base URL: api.md:13 [DOC].
- Bank tool server: `tools/openapi.json` `servers[0].url` = `https://freya-bank-mock.freyavoice.workers.dev/v1` (openapi.json:8-10) [DOC].
- "The seven tool calls need no key: the customer_id in the body is the secret of one call." (openapi.json:6) [DOC].
- Practice routes and `x-team-key`: score.py:7, 10-15; run_cases.py:86, 93 [CODE].
- "Your team key owns your practice sessions and records." (page §Data) [DOC].

### 1.2 Vocabulary

| Term | What it is | Source |
|---|---|---|
| Workflow | The phone agent's definition: nodes, prompts, tools, routes. JSON sent as `{"name": …, "workflow": {…}}` | workflow-format.md:66; api.md:54 [DOC] |
| Agent | Created by the platform together with the workflow. Its id (`agentId`) is what a simulation takes | api.md:54, 64-67; workflow-format.md:11 [DOC] |
| Version | Each update saves a new numbered version. Only the **published** version runs | api.md:103, 108 [DOC] |
| Workspace | The container your key belongs to. "a team has one workspace". It holds at most 200 workflows | page §Evaluation, §Submit Limits; README.md:87 [DOC] |
| Persona | The simulated caller: `name`, `prompt`, `successCriteria`, `tags` | api.md:143-164 [DOC] |
| Simulation | One test job: an agent against a set of personas, with call variables per persona | api.md:180-226 [DOC] |
| Iteration | "one execution of the simulation" | api.md:264 [DOC] |
| Run | "one call with one persona", with the judge's `outcome` and `reason` | api.md:276-290 [DOC] |
| Call | The transcript plus the engine events of one conversation | api.md:292-336 [DOC] |
| Chat session | Turn-by-turn conversation through `/api/v2/chat/message`, identified by a `callId` | api.md:240-252 [DOC] |
| Practice session | A fresh mock-bank customer for one practice case (`POST /v1/practice/sessions`) | run_cases.py:86 [CODE] |
| Ledger | The bank's record of one practice customer: every tool call and every promise, note, callback, transfer and outcome. The scorer reads it | score.py:1, 17-34 [CODE]; openapi.json:6 [DOC] |
| Team key | `FREYA_BANK_TEAM_KEY`. You make it up (16+ characters) and use the same one every time | env.example:3; run_cases.py:5 [DOC] |
| Judge | The model in `analysisLlmOverride`. It checks the persona's `successCriteria` after the call | api.md:161, 222; freya.py:85 [DOC][CODE] |

### 1.3 The models

| Role | Value in freya.py | Where it is set | Source |
|---|---|---|---|
| The phone agent's three per-turn model calls (dialogue, routing, extraction) | `{"provider": "experimental-5", "model": "experimental-5"}` = `AGENT_LLM` | `assistantLlmOverride`, `routingLlmOverride`, `extractionLlmOverride` on every simulation; patched into `agent_config.llmConfig` by `update_workflow` | freya.py:59-60, 84, 94 [CODE] |
| The caller (persona) and the judge (analysis) | `{"provider": "google", "model": "gemini-3-flash-preview"}` = `SIM_LLM`, commented "plays the customer and judges" | `personaLlmOverride`, `analysisLlmOverride` | freya.py:85, 95 [CODE] |

- freya.py:83, verbatim: "The model every team's phone agent runs on: Freya's model on the event's own GPU box. Do not change it. (Organisers can point a test at another model with the two variables.)" The two variables are `FREYA_AGENT_PROVIDER` and `FREYA_AGENT_MODEL` (freya.py:84) [CODE].
- Rule: "The phone agent runs on the model set in `freya.py` (`AGENT_LLM`). Do not change it. Your builder may use any model or coding agent." (README.md:85; page §Overview, §Submit Limits) [DOC].
- After each user message the platform makes **three separate model calls**: extraction, then routing, then dialogue. They do not share a prompt (workflow-format.md:15-31) [DOC]. That is why a simulation has three agent overrides.

---

## 2. API basics

### 2.1 Connection

| Item | Value | Source |
|---|---|---|
| Base URL | `https://staging-app.freyavoice.ai` | api.md:13; freya.py:8 (default); env.example:2 [DOC][CODE] |
| Auth header | `Authorization: Bearer <your API key>`. "Keys start with `fak_`" | api.md:14; freya.py:10 [DOC][CODE] |
| Content type | `Content-Type: application/json` | api.md:15 [DOC] |
| User-Agent | "Required, and it must look like a browser." Example: `Mozilla/5.0 (my-builder)` | api.md:16 [DOC] |
| Key location | "from your Freya workspace, under API keys" | env.example:1; page §FAQ [DOC] |

- **The 1010 trap.** "A request without a browser-like `User-Agent` is rejected before it reaches the API. The response is an HTML page with `error code: 1010`. Many HTTP libraries send a default agent that is rejected, so set the header yourself." (api.md:18; README.md:96) [DOC]. freya.py:9 says Cloudflare is what rejects it, and freya.py:10 sends `Mozilla/5.0 (build-the-builder)` [CODE]. [INFERRED] Python's default `Python-urllib/3.x` would be rejected.
- **Content-Type on GET.** api.md lists it under Basics, but its own GET examples send none (api.md:122-124, 134-136, 171-173, 233-235, 259-261, 271-273, 299-301). freya.py sends one fixed header dict, Content-Type included, on every request (freya.py:10, 15) [DOC][CODE].
- **Which headers are documented as required.** Only the User-Agent row says "Required" (api.md:16) [DOC]. The Basics table lists the auth header (api.md:14) and `Content-Type: application/json` (api.md:15) as connection items, without marking either one required or optional [DOC]. [INFERRED] The auth header is needed on every Freya route, since each route belongs to a key's workspace. Content-Type is probably needed only on requests with a JSON body, because the GET examples omit it. Neither point is stated in api.md. Sending all three on every request, as freya.py does, is the safe choice.
- **curl variables.** The examples use `FREYA_API_URL`, `FREYA_API_KEY` and `UA="Mozilla/5.0 (my-builder)"` (api.md:22-26). They also use `$WORKFLOW_ID`, `$WORKSPACE_ID`, `$SIM_ID`, `$ITERATION_ID` and `$CALL_ID`, which are never defined (api.md:94, 107, 233, 271, 299) [DOC].

### 2.2 The response envelope

```json
{ "success": true, "data": { "message": "text", "result": {} } }
```

- "Every JSON response has this shape" (api.md:30-39). "The payload is `data.result`. The field paths below are relative to `data.result`." (api.md:42) [DOC].
- Fallback rule: "The reference client reads the wrapper keys named below (`workflow`, `simulation`, `iterations`, `workspaces`) and falls back to the bare payload if a key is missing. Do the same in your client." (api.md:44) [DOC]. freya.py follows this only in part; see §11.12, M5.
- "An HTML response with status 404 means the route is wrong." (api.md:46) [DOC].
- **Route naming:** "the workflow and call routes are singular (`/api/v2/workflow`, `/api/v2/call`) and the persona and simulation routes are plural." (api.md:46). Also plural: `/api/v2/workspaces` (api.md:131). Other prefixes: `/api/v2/versions/workflow/…` (api.md:107) and `/api/v2/chat/…` (api.md:242, 250) [DOC].
- [UNCERTAIN] What an error looks like. api.md never shows `success: false`, and it does not say whether errors are non-2xx statuses with the same envelope. freya.py never reads `success` (freya.py:20) [CODE].

### 2.3 How confirmed is each line of api.md?

- "Every call on this page is taken from a client that was run against the platform, unless a line says 'not confirmed'." (api.md:7) [DOC].
- Lines that hedge [DOC]:

| Line | Hedge |
|---|---|
| 85 | Dry-run result fields not documented |
| 127 | GET workflow fields not confirmed |
| 139 | Workspace parameter name not confirmed |
| 176 | List personas not confirmed |
| 238 | "Other status values are not listed in the sources" |
| 252 | Chat quirks: "Seen in tests, not guaranteed" |
| 334 | Whether the call snapshots need a query parameter is not confirmed |

- Personas, simulations and calls are "documented in full at https://docs.freyavoice.ai". Workflow creation and the workflow JSON are **not** documented there (api.md:5; also 139, 176, 349) [DOC]. That site was not read for this chapter, because no network calls were made.
- [INFERRED] The "reference client" that api.md describes is probably an older client, not today's freya.py:
  - api.md:127 says that client never calls `GET /api/v2/workflow/{id}`, but freya.py does (freya.py:57, 67).
  - api.md:85 says the client "prints the response body", but freya.py raises instead (freya.py:19).
  - api.md:115 and api.md:288 do name `freya.*` functions.
  - File mtimes: api.md 2026-10-10 05:46, freya.py 07:12.

---

## 3. Endpoint reference: all 16 routes at a glance

Every route needs the Bearer key and a browser-like User-Agent (api.md:14-18). The payload is `data.result` (api.md:42).

| # | Method and path | Query | Body | `result` holds | Confirmed? | freya.py helper |
|---|---|---|---|---|---|---|
| 1 | `POST /api/v2/workflow` | none | `{name, workflow}` | `workflow.id`, `workflow.agentId` | yes | `create_workflow` (31-34) |
| 2 | `POST /api/v2/workflow?dryRun=true` | `dryRun=true` | same as #1 | undocumented (api.md:85) | route yes, result no | `validate_workflow` (48) |
| 3 | `PUT /api/v2/workflow/{workflowId}` | none | `{workflow}`, the full definition | not documented | yes | inside `update_workflow` (54, 60) |
| 4 | `GET /api/v2/workflow/{workflowId}` | none in api.md; `workspaceId` in freya.py | none | not confirmed (api.md:127). freya.py expects `workflow.{id, agentId?, updatedAt?, workflow}` | **no** | `update_workflow` (57), `export_workflow` (67) |
| 5 | `GET /api/v2/versions/workflow/{workflowId}` | `workspaceId` | none | `versions[]` with `id`, `versionNumber`, `isPublished` | yes | `update_workflow` (61) |
| 6 | `POST /api/v2/versions/workflow/{workflowId}/publish` | none | `{versionId}` | not documented | yes | `update_workflow` (63) |
| 7 | `GET /api/v2/workspaces` | none | none | `workspaces[]`, each with `id` | yes | `workspace_id` (27) |
| 8 | `POST /api/v2/personas` | none | `{personas: [{name, prompt, successCriteria, tags}]}` | `personas[]` in request order, each with `id` | yes | `create_personas` (69) |
| 9 | `GET /api/v2/personas` | the workspace parameter (name not confirmed) | none | not documented | **no** (api.md:176) | none |
| 10 | `POST /api/v2/simulations` | none | see §8.1 | `simulation.id` | yes | `run_simulation` (91-95) |
| 11 | `GET /api/v2/simulations/{simulationId}` | none | none | `simulation.status` | yes | `run_simulation` (103) |
| 12 | `POST /api/v2/chat/message` | none | `{workflowId, message, customerVariables}`; later turns carry the `callId` | `response`, `callId` | yes; the quirks are "not guaranteed" | none |
| 13 | `POST /api/v2/chat/end` | none | `{callId}` | not documented | stated (api.md:250) | none |
| 14 | `GET /api/v2/simulations/{simulationId}/iterations` | none | none | `iterations[]`, each with `id` | yes | `run_simulation` (105) |
| 15 | `GET /api/v2/simulations/{simulationId}/iterations/{iterationId}` | `limit` (default 30, max 100), `offset` | none | `iteration`, `runs[]`, `runsTotal` | yes | `get_iteration` (70-78) |
| 16 | `GET /api/v2/call/{callId}` | none (snapshot parameter unknown) | none | `call.{messages, transcript, endedReason, duration, successCriteriaResult}` | yes | `get_call` (79-81) |

**Not in api.md at all** [DOC by absence]:
- any DELETE route (workflow, persona or simulation)
- list workflows, list simulations
- cancel, stop or pause a simulation
- update a persona
- any `/agent` route
- any rate-limit statement
- any webhook or push notification (polling is the only way to wait)

---

## 4. Workflows: create, validate, update, publish, read

### 4.1 Create: `POST /api/v2/workflow` (api.md:50-69)

- **Body:** `{"name": "my agent", "workflow": {"initial_node": "start", "nodes": {}, "global_nodes": {}}}` (api.md:61). "The body holds a name and the workflow definition. The platform creates the agent together with the workflow." (api.md:54) [DOC].
- **Result** [DOC]:

  | Path in `result` | Meaning (api.md:64-67) |
  |---|---|
  | `workflow.id` | The workflow id |
  | `workflow.agentId` | "The id of the agent that was created with it. Pass this as `agentId` to a simulation" |

- "Put a complete workflow in `workflow`. The empty `nodes` object above only keeps the example short." (api.md:69) [DOC].
- **What goes in `workflow`** (workflow-format.md:50-60) [DOC]:

  | Key | Required |
  |---|---|
  | `initial_node` | yes |
  | `nodes` | yes |
  | `system_prompt` | no |
  | `global_nodes` | no |
  | `test_variables` | no |
  | `context_variables` | no |
  | `tools` | no |
  | `agent_config` | no |
  | `nodePositions` | no |

- "**`agent_config`**: omit it. The platform fills in defaults." (workflow-format.md:62). "**No `null` values.** The schema is strict… A `null` fails validation." (workflow-format.md:64) [DOC].
- **Workflow cap.** "A workspace holds 200 workflows. A builder that creates a new one on every run fills it up and leaves you with a list nobody can read." (README.md:87). When it is full the error is "`Workspace plan limit reached`: you created too many workflows. Update one in place." (README.md:97; page §Submit Limits, §FAQ) [DOC]. No delete route is documented, so a full workspace cannot be cleaned through the documented API [INFERRED].
- [UNCERTAIN] Whether a create publishes a first version, and what default `agent_config` (and model) it fills in. See §5.

### 4.2 Dry run: `POST /api/v2/workflow?dryRun=true` (api.md:71-87)

- "Same body as create. The platform runs its write validation and stores nothing." (api.md:75) [DOC].
- "The fields of the dry-run result are not documented. The reference client treats any HTTP error status as a failure and prints the response body." (api.md:85) [DOC].
- **Silent stripping:** "Validation checks the schema. It also removes fields that do not belong to a node type without reporting them. For example `pre_actions` on a `conversation` node is dropped. Read a created workflow back if you are unsure what was stored." (api.md:87) [DOC].
  - [INFERRED] A dry run stores nothing, so it cannot show what was stripped. Only a create or update followed by a GET shows it.
- tools-and-code.md:564: "A malformed lifecycle tool is dropped at run time without an error. Validate with a dry run (api.md)." [DOC]. [UNCERTAIN] The two statements sit uneasily together. Whether a dry run actually reports a malformed lifecycle tool, or whether such a tool passes validation and is only dropped when the call runs, is not stated.
- freya.py: `validate_workflow(name, workflow)` = `api("POST", "/api/v2/workflow", {"name": name, "workflow": workflow}, dryRun="true")` (freya.py:48) [CODE]. It returns the undocumented result. On an HTTP error status it raises `RuntimeError` with up to 1500 characters of the body. It does not print.
- [UNCERTAIN] Whether invalid input gives a non-2xx status or a 2xx with `success: false`. freya.py would miss the second (freya.py:20).

### 4.3 Update: `PUT /api/v2/workflow/{workflowId}` (api.md:89-115)

- Body: `{"workflow": {…}}`. The example has no `name` (api.md:98) [DOC]. [UNCERTAIN] whether a PUT can rename the workflow. freya.py never sends `name` on a PUT (freya.py:54, 60) [CODE].
- **Full replacement:** "The body replaces the whole definition. A top-level key that your new definition leaves out is deleted, including `test_variables` and an `agent_config` that the platform filled in. Send the complete definition every time." (api.md:101) [DOC].
- **Not published:** "An update saves a new version and does NOT publish it. Simulations and calls run the published version, so after an update alone you are still testing the old phone agent." (api.md:103) [DOC].

### 4.4 Versions and publish (api.md:105-115)

```bash
# newest version first
curl -s "$FREYA_API_URL/api/v2/versions/workflow/$WORKFLOW_ID?workspaceId=$WORKSPACE_ID" -H "Authorization: Bearer $FREYA_API_KEY" -H "User-Agent: $UA"
# result.versions[] has id, versionNumber, isPublished

curl -s -X POST "$FREYA_API_URL/api/v2/versions/workflow/$WORKFLOW_ID/publish" \
  -H "Authorization: Bearer $FREYA_API_KEY" -H "Content-Type: application/json" -H "User-Agent: $UA" \
  -d '{"versionId": "<id of the newest version>"}'
```

- The list takes `workspaceId` as a query parameter. Its result is `result.versions[]` with `id`, `versionNumber` and `isPublished`. The comment says "newest version first" (api.md:106-108) [DOC]. freya.py does not rely on that order; it takes `max(versionNumber)` (freya.py:62) [CODE].
- The publish call takes `{"versionId": …}` and no `workspaceId` (api.md:110-112). Its response is not documented [DOC].
- "`freya.update_workflow` and `freya.save_workflow` do both steps." (api.md:115) [DOC]. This is only partly true for `save_workflow`; see §5.
- "A run of a simulation reports the version it used as `agentVersionNumber`. Check it when a change seems to have no effect." (api.md:115) [DOC]. [UNCERTAIN] Where that field sits (on the simulation, the iteration or each run) is not stated. It is missing from the run-field table (api.md:278-286).

### 4.5 Get: `GET /api/v2/workflow/{workflowId}` (api.md:117-127)

- The curl example passes no query parameter (api.md:122-124). freya.py passes `workspaceId` (freya.py:57, 67) [DOC][CODE].
- "The path is the same as for update. The reference client does not call this route, so the fields of its result are not confirmed." (api.md:127) [DOC].
- What freya.py **expects** [CODE]:
  - `result.workflow.id`: required (freya.py:68)
  - `result.workflow.agentId`: optional, read with `.get` (freya.py:68)
  - `result.workflow.updatedAt`: optional (freya.py:68)
  - `result.workflow.workflow`: required; the stored definition (freya.py:57, 68)
  - inside that definition, `agent_config.llmConfig.provider` and `.model` (freya.py:58)
- [UNCERTAIN] Whether GET returns the newest saved version or the published one. After `update_workflow` the two are the same, because it publishes the newest.

---

## 5. Publish semantics in one place

### 5.1 What each action does

| Action | New version? | Published afterwards? | `agent_config` afterwards | Source |
|---|---|---|---|---|
| `POST /api/v2/workflow` (create) | Creates the workflow and agent; how versions start is not documented | [UNCERTAIN] | "The platform fills in defaults" (workflow-format.md:62); the model it picks is [UNCERTAIN] | api.md:54; workflow-format.md:62 |
| `PUT /api/v2/workflow/{id}` | Yes ("saves a new version") | **No** | If you leave it out it "is deleted" (api.md:101), yet freya.py:55 says "The platform fills in a default agent_config". Which one happens is [UNCERTAIN] | api.md:101-103; freya.py:55 |
| `POST /api/v2/versions/workflow/{id}/publish` | No | Yes, the chosen version | unchanged | api.md:110-112 |
| `freya.update_workflow(id, wf)` | 1 version, or 2 when the model patch fires [INFERRED] | Yes: the newest, unless it is already published | Model forced to `AGENT_LLM`; other `llmConfig` keys kept | freya.py:49-64 |
| `freya.save_workflow(slot, wf)`, **first call** for a slot | Create only | **Not explicitly** (no publish call) | **Not patched** | freya.py:43-46 |
| `freya.save_workflow(slot, wf)`, later calls | = `update_workflow` | Yes | Patched | freya.py:43-44 |

### 5.2 What runs which version

| Consumer | Version used | Source |
|---|---|---|
| Simulation | Published | api.md:103 [DOC] |
| Real call | Published | api.md:103 [DOC] |
| Chat (`/api/v2/chat/message`) | "the published workflow" | api.md:242 [DOC] |
| `export_workflow` (GET workflow) | [UNCERTAIN]: newest saved, or published | api.md:127; freya.py:67 |

### 5.3 The `agent_config` and model story

- **The builder should leave `agent_config` out:** "Leave `agent_config` out." (SKILL.md:19). "Leave `agent_config` out of the workflow you send." (README.md:103). "**`agent_config`**: omit it. The platform fills in defaults. It holds model, voice and timeout settings…" (workflow-format.md:62) [DOC].
- **The default model can be wrong.** freya.py:55-56, verbatim: "The platform fills in a default agent_config. If its model is not the event's model, a simulation still runs (it overrides the model), but a chat turn or a real call cannot start. Set the model and save once more." [CODE].
- **What `update_workflow` does about it** (freya.py:57-60) [CODE]:
  1. It reads the stored definition back.
  2. If `(llmConfig.provider, llmConfig.model)` differ from `AGENT_LLM`, it sets `llmConfig = {**old, **AGENT_LLM}`.
  3. It PUTs the **stored copy** plus the patched `agent_config`.
- **Related symptom:** "A simulation stays at 'running' and no call ever starts: the workflow cannot start a call. Try one chat turn. Leave `agent_config` out of the workflow you send." (README.md:103) [DOC].
  - [UNCERTAIN] How this relates to freya.py:55's claim that a simulation "still runs" with a wrong default model. The two may describe different failures:
    - a hand-written, broken `agent_config`, which makes a simulation hang;
    - a default model that is merely not the event's, which breaks only chat and real calls.
- **What ends up in the export.** The stored definition always holds an `agent_config` that the builder did not send, so a diff between the GET result and the builder's JSON always shows it [INFERRED]. After `update_workflow`, the export (§11.7) contains the patched `agent_config` [INFERRED].

### 5.4 The first-save gap

- **Contradiction.** api.md:115 says `save_workflow` updates and publishes. README.md:98 says "`freya.save_workflow` publishes. A plain `PUT` does not." Yet on the **first** save of a slot, `save_workflow` calls only `create_workflow`: no publish call and no model patch (freya.py:45-46) [DOC][CODE].
- **Evidence that a freshly created workflow can still be simulated** [DOC][INFERRED]:
  - The README's ten-minute start saves the base agent once and then runs `run_cases.py` straight away (README.md:22-24).
  - The skill also tests right after the first save (SKILL.md:20-22).
  - So either a create publishes its first version, or a simulation can run a workflow that has a single unpublished version. Which one is [UNCERTAIN].
- [UNCERTAIN] Whether a **chat** turn works right after a create. That depends on the default model, per freya.py:55-56. The earlier summary called this an unverified gap (research/read-api-and-testing.md:48).

### 5.5 Version bookkeeping facts

- The return value of `update_workflow` is `newest["versionNumber"]`, whether or not it published anything (freya.py:64). `save_workflow` stores it as `state[slot]["version"]` (freya.py:44) [CODE].
- When the model patch fires, one `update_workflow` creates two versions, because each PUT "saves a new version" (api.md:103). The published one is the patched one [INFERRED].
- No re-read confirms `isPublished` after the publish POST. An HTTP error raises; nothing else is checked [CODE].
- If another process saves a version between the PUT and the versions GET, "newest" may not be ours. There is no guard [INFERRED].
- To check what actually ran, read `agentVersionNumber` (api.md:115) and compare it with the number `update_workflow` returned [DOC][INFERRED].

---

## 6. Workspaces: `GET /api/v2/workspaces` (api.md:129-139)

- "lists the workspaces your key can see. The list is at `result.workspaces`. Each entry has an `id`." (api.md:131) [DOC].
- "List routes need the workspace id as a query parameter. The name of that parameter is not confirmed here. See https://docs.freyavoice.ai." (api.md:139) [DOC].
  - **Contradiction inside api.md:** the versions example uses `?workspaceId=$WORKSPACE_ID` (api.md:107). freya.py uses `workspaceId` too (freya.py:57, 61, 67).
  - freya.py does **not** send it on the iterations list, which is a list route (freya.py:105). It also skips it on the workspaces, simulation, iteration and call GETs (freya.py:27, 74, 81, 103) [CODE].
  - [UNCERTAIN] Which routes really need it.
- One workspace per team, and one key per team: "a team has one workspace" (page §Evaluation); "Teammate: one workspace; owner invites from Workspace settings" (page §FAQ); "One Freya key per team." (page §Rules) [DOC].
- freya.py `workspace_id()`: §11.3.

---

## 7. Personas (api.md:141-176)

"A persona plays the caller in a simulation. It has a prompt and success criteria." (api.md:143) [DOC].

### 7.1 Create: `POST /api/v2/personas`

The body is a **batch**:

```json
{"personas": [{"name": "Late parcel", "prompt": "You are Dana Reed. Your parcel is five days late. Answer what you are asked in one short sentence.", "successCriteria": "The agent states the new delivery day.", "tags": ["practice"]}]}
```
(api.md:154)

| Field | Meaning (api.md:157-162) |
|---|---|
| `personas[].name` | Persona name |
| `personas[].prompt` | "Instructions for the model that plays the caller" |
| `personas[].successCriteria` | "Text that the judge model checks after the call" |
| `personas[].tags` | Array of strings |

- Result: "The created personas are at `result.personas`, in request order. Each has an `id`." (api.md:164) [DOC]. run_cases relies on that order when it zips its request with the response (run_cases.py:60-61) [CODE].
- freya.py: `create_personas(personas)` returns the whole `result`; callers index `["personas"]` (freya.py:69; run_cases.py:60) [CODE].
- The minimal loop says to create personas "once. Keep the ids." (api.md:343) [DOC].

### 7.2 List: `GET /api/v2/personas`

"Not confirmed: the reference client only creates personas. The path above is the create route with `GET`. This is a list route, so it needs the workspace query parameter mentioned above. Take the parameters and result fields from https://docs.freyavoice.ai." (api.md:176) [DOC]. freya.py has no helper [CODE].

### 7.3 What is not documented

- No persona update or delete route, and no persona limit (api.md:141-176) [DOC by absence].
- [INFERRED] Personas only accumulate. run_cases creates new personas whenever a case's text or style changes and never deletes old ones (§13.5). Whether some limit exists is [UNCERTAIN].
- How run_cases builds its persona text: §13.4.

---

## 8. Simulations, iterations and runs

"A simulation runs your agent against personas. In `chat` mode the conversation is text only." (api.md:180) [DOC].

### 8.1 Create: `POST /api/v2/simulations` (api.md:182-226)

The full example body (api.md:191-205):

```json
{
  "agentId": "AGENT_ID",
  "name": "practice run 1",
  "mode": "chat",
  "selectedPersonaIds": ["PERSONA_ID"],
  "customerVariablesMap": {"PERSONA_ID": {"customer_id": "c_123", "first_name": "Dana"}},
  "maxConcurrentCalls": 5,
  "runsPerPersona": 1,
  "maxCallDurationSeconds": 420,
  "assistantLlmOverride": {"provider": "experimental-5", "model": "experimental-5"},
  "routingLlmOverride": {"provider": "experimental-5", "model": "experimental-5"},
  "extractionLlmOverride": {"provider": "experimental-5", "model": "experimental-5"},
  "personaLlmOverride": {"provider": "google", "model": "gemini-3-flash-preview"},
  "analysisLlmOverride": {"provider": "google", "model": "gemini-3-flash-preview"}
}
```

| Field | Meaning (api.md:208-222) [DOC] | What `freya.run_simulation` sends [CODE] |
|---|---|---|
| `agentId` | "`workflow.agentId` from the create call". The **agent** id, not the workflow id | `agent_id` argument (freya.py:92) |
| `name` | Name of the simulation | `name` argument. run_cases uses `f"cases {HH:MM:SS}"` (run_cases.py:88) |
| `mode` | `"chat"` for a text simulation | always `"chat"` (freya.py:92) |
| `selectedPersonaIds` | Persona ids to run | `list(variables_by_persona)`, the dict's keys in order (freya.py:92) |
| `customerVariablesMap` | "Object keyed by persona id. Each value is the object of call variables for that persona's call" | `variables_by_persona` itself (freya.py:93) |
| `maxConcurrentCalls` | How many calls run at the same time | `concurrency`: env `FREYA_SIM_CONCURRENCY`, default `5` (freya.py:87, 93) |
| `runsPerPersona` | Calls per persona | always `1` (freya.py:93) |
| `maxCallDurationSeconds` | Limit for one call | `max_seconds`, default `420` (freya.py:87, 93) |
| `assistantLlmOverride` | Model for the dialogue call. Object with `provider` and `model` | `AGENT_LLM` (freya.py:94) |
| `routingLlmOverride` | Model for the routing call | `AGENT_LLM` |
| `extractionLlmOverride` | Model for the extraction call | `AGENT_LLM` |
| `personaLlmOverride` | Model that plays the caller | `SIM_LLM` (freya.py:95) |
| `analysisLlmOverride` | Model that judges the success criteria | `SIM_LLM` |

- "Pass all three agent overrides (`assistantLlmOverride`, `routingLlmOverride`, `extractionLlmOverride`) on every simulation. An override you leave out falls back to the agent's default model. The values above are the ones the reference client uses. Use the models your event rules name." (api.md:224) [DOC]. The event rules name the freya.py model (README.md:85) [DOC].
- Result: "The simulation id is at `result.simulation.id`." (api.md:226) [DOC].
- **One simulation at a time.** "One simulation runs at a time per workspace. A ten-customer run takes 3 to 11 minutes. A second `run_cases.py` started meanwhile waits for the first." (README.md:88; page §Evaluation, §Submit Limits) [DOC].
  - freya.py recognises the refusal by the substring `"concurrent simulations"` in the error text (freya.py:98) [CODE].
  - The HTTP status and the full message are [UNCERTAIN].
- **Call variables.** `now`: "The phone agent gets the date/time of the call as variable `now`; every date rule uses it." (page §Overview) [DOC].
  - Call variables are readable as `{{customer_id}}` in prompts and tool parameters, and as `vars.get("customer_id")` in code. This is "Verified in a working builder" (workflow-format.md:221) [DOC].
  - `test_variables` "On a web call to the workflow… is merged into the call variables. A value passed with the call wins." (workflow-format.md:209) [DOC].
  - "A chat simulation in the trial showed `web`" as `{{call.direction}}` (workflow-format.md:234) [DOC]. [INFERRED] So `test_variables` probably fill any key that `customerVariablesMap` leaves out in a simulation.
- [INFERRED] With `runsPerPersona > 1`, every run of a persona would get the same variables object, because the map is keyed by persona id. All of those runs would then share one bank `customer_id`. Practice sessions are single-use after `close_call` [PROBED-earlier], so the second run's tools would fail.
- "The maximum call length in a simulation is set with `maxCallDurationSeconds` (api.md)." (workflow-format.md:674) [DOC].
- [UNCERTAIN] Limits on `maxConcurrentCalls`, on the number of personas per simulation and on `maxCallDurationSeconds`, and any `mode` other than `"chat"`.

### 8.2 Poll: `GET /api/v2/simulations/{simulationId}` (api.md:228-238)

- "Read `result.simulation.status`. Poll every 10 seconds until it is `completed`, `failed` or `paused`. Other status values are not listed in the sources." (api.md:238) [DOC].
- README.md:103 shows that `running` is a status ("A simulation stays at 'running' and no call ever starts") [DOC].
- How a simulation becomes `paused`, and whether `queued` or `pending` simulation statuses exist, is [UNCERTAIN].
- No cancel route is documented. A simulation you stop waiting for keeps the workspace busy until it ends [INFERRED].

### 8.3 List iterations: `GET /api/v2/simulations/{simulationId}/iterations` (api.md:254-264)

- "An iteration is one execution of the simulation. The list is at `result.iterations`. The reference client takes the first entry's `id` right after a simulation finishes." (api.md:264) [DOC].
- [UNCERTAIN] The list order, and whether one simulation can have more than one iteration.

### 8.4 An iteration's runs: `GET /api/v2/simulations/{simulationId}/iterations/{iterationId}` (api.md:266-290)

- "`result` has `iteration`, `runs` and `runsTotal`. A run is one call with one persona." (api.md:276) [DOC]. The fields of `iteration` are not documented.

| Field of a run | Meaning (api.md:278-286) [DOC] |
|---|---|
| `id` | Run id |
| `callId` | "Id of the call. Use it to fetch the transcript" |
| `personaId`, `personaName` | The persona that played the caller |
| `outcome` | "Result of the success criteria, for example `fail`" |
| `reason` | "The judge's explanation" |
| `turnCount` | Number of turns |
| `startedAt`, `endedAt` | Timestamps (format not stated) |

- **Outcome values:**
  - `pass` is the passing value that run_cases tests for (run_cases.py:96) [CODE]. api.md shows only `fail` [DOC].
  - "While a simulation is running, `outcome` is `queued` or `running` for the runs that have not finished." (api.md:290) [DOC].
  - Any other value is [UNCERTAIN].
- **Paging:** "The route returns 30 runs unless you ask for more. Pass `limit` (100 at most) and `offset`, and read until a page comes back short. Compare the number you read with `runsTotal`. `freya.get_iteration` does this for you." (api.md:288) [DOC]. In fact `get_iteration` never compares with `runsTotal` (§11.9) [CODE].
- The verdict appears twice. The run's `outcome`/`reason` is one copy. The call's `successCriteriaResult {success, reason}` (api.md:312) is the other. Whether they always agree is [UNCERTAIN]. run_cases reads only the run's copy (run_cases.py:90, 96) [CODE].
- **When judging happens.** "At the end of a call the order is: call analysis, then `end_of_call` tools, then success-criteria judging." (tools-and-code.md:563) [DOC].

---

## 9. Chat: talking to the workflow turn by turn (api.md:240-252)

### 9.1 The calls

```bash
curl -s -X POST "$FREYA_API_URL/api/v2/chat/message" \
  -H "Authorization: Bearer $FREYA_API_KEY" -H "Content-Type: application/json" -H "User-Agent: $UA" \
  -d '{"workflowId": "'$WORKFLOW_ID'", "message": "Hello?", "customerVariables": {"customer_id": "c_test", "first_name": "Daniel", "last_name": "Reyes", "title": "Mr", "now": "2026-10-14T11:00"}}'
```
(api.md:245-248)

- "`POST /api/v2/chat/message` runs one turn against the published workflow, with no simulation and no queue. It answers in seconds, so it is the fastest way to see whether a workflow starts at all and what it says first." (api.md:242) [DOC].
- It takes the **workflow** id (`workflowId`), not the agent id (api.md:247) [DOC].
- "`result` has `response` (what the phone agent said) and `callId`. Send the next turn with the same `callId`. End it with `POST /api/v2/chat/end` and `{"callId": "..."}`." (api.md:250) [DOC].

### 9.2 Quirks: observed, not guaranteed

api.md:252, verbatim: "Seen in tests, not guaranteed: a long turn can return 504, and when the first step is a code step the chat route may skip it, so values that step computes are empty. A bare 500 here means the workflow cannot start a call at all." [DOC]

- The 504 and the skipped code step are hedged observations. The 500 sentence is stated without a hedge.
- **Chat and simulation can differ on a first code node.** workflow-format.md:484 says "Verified in a working builder: a passthrough `code` node can be the `initial_node`. It runs before the agent says anything." So a code-first workflow works in a simulation, but its first chat turn may lack the values that node computes [DOC][INFERRED].

### 9.3 Where chat is endorsed

- "You want to see what your phone agent says without waiting for a simulation: `POST /api/v2/chat/message` runs one turn at a time." (README.md:101) [DOC].
- "A simulation stays at 'running' and no call ever starts… Try one chat turn." (README.md:103) [DOC].
- "to check an agent on a brief with no cases, talk to it with POST /api/v2/chat/message (docs/api.md)." (page §FAQ) [DOC].

### 9.4 What is not known about chat

| Unknown | Note |
|---|---|
| The body of later turns | Is `{callId, message}` enough, or must `workflowId` and `customerVariables` be sent again? [UNCERTAIN] |
| The `/chat/end` result, and what happens to a chat that is never ended | [UNCERTAIN] |
| Whether chat tool calls reach the bank | [INFERRED, probably yes] The agent's `api_call` tools send real HTTP to the URL in each tool (tools-and-code.md:95; base-agent.json `url` defaults), and the bank binds a call only by the `customer_id` in the body (openapi.json:6). api.md never states it for chat. The earlier summary said "Yes, by construction" (research/read-api-and-testing.md:94); that is an inference, not a test |
| `customer_id` in the api.md example | `"c_test"` is not a practice customer. The bank answers HTTP 404 for an unknown `customer_id` [PROBED-earlier] (research/read-api-and-testing.md:144). So a chat with that id cannot get past any tool call |
| Whether `get_call(callId)` works on a chat call, with events and snapshots | [UNCERTAIN] |
| Whether chat merges `test_variables` | It does if it counts as a "web call" (workflow-format.md:209) [UNCERTAIN] |
| What the first `response` is | The opening line, or a reply to the `message` sent? [UNCERTAIN] |
| Whether chat runs while a simulation is running, and whether chats can run in parallel | "no queue" (api.md:242) suggests yes. [UNCERTAIN] |
| Whether a 504 turn finishes on the server, so the `callId` stays usable | [UNCERTAIN] |
| Whether chat produces a judge verdict | Nothing says so [INFERRED: no] |
| A helper in freya.py | None exists. Use `freya.api("POST", "/api/v2/chat/message", {...})` [CODE][INFERRED] |

### 9.5 The dashboard practice customer

page §FAQ: "Dashboard test call never passes identity: the workspace has one practice customer for dashboard test calls: DOB 14 March 1988, last four 4471. After a call closes, that customer starts fresh after 5 min idle." [DOC]

- That identity is PUB-01's (public-test-set.json, PUB-01 `identity`) [CODE].
- The base agent's `test_variables` hold `first_name` Daniel, `last_name` Reyes, `title` Mr and `now` 2026-10-14T11:00, but **no** `customer_id` (examples/base-agent.json:401-406) [CODE].
- [UNCERTAIN] How a dashboard call binds to that customer, and whether a `/chat/message` call can use it. The FAQ speaks only of "dashboard test calls".

---

## 10. Calls and the event log: `GET /api/v2/call/{callId}` (api.md:292-336)

### 10.1 Fields

"The call is at `result.call`." (api.md:304) [DOC].

| Field | Meaning (api.md:306-312) |
|---|---|
| `messages` | "The event list of the call" |
| `transcript` | "The conversation as one text string" |
| `endedReason` | "Why the call ended. For an `end_call` node it is the terminal's `function.name`" |
| `duration` | Seconds |
| `successCriteriaResult` | Object with `success` and `reason` |

Known `endedReason` values:

| Value | Meaning | Source |
|---|---|---|
| the `terminal.function.name` of the `end_call` node | the agent ended the call. "The node name does not affect it. Pick a name that describes the outcome." | api.md:310; workflow-format.md:652 [DOC] |
| `customer-ended-call` | the customer hung up. "it was silent too long and the customer hung up, as a person would" | README.md:100; run_cases.py:116 [DOC][CODE] |
| anything else (time limit reached, engine error) | [UNCERTAIN] | |

**Two documented causes of `customer-ended-call`.**
- **A slow model.** README.md:100 ties the hang-up to slowness: "If the same phone agent is fast in the next run, the model was busy and the low score was not yours." [DOC]
- **A silent turn after a tool result.** README.md:104: "The agent says nothing after a tool call and the customer hangs up: see "Tool results and the next turn" in `docs/tools-and-code.md`." [DOC] That section (tools-and-code.md:566-575) says [DOC]:
  - After a tool call returns, "the model sees the result and has to produce the next turn itself" (tools-and-code.md:568).
  - Seen in practice runs with the hackathon's agent model: "The result arrives, no assistant message follows, and the simulated customer hangs up after waiting." This happens more often when the result is bare data such as `{"ok": true, "verified": true}` (tools-and-code.md:570).
  - A related failure: the agent ignores a negative result, for example it reads `"verified": false` and moves on as if the answer had passed (tools-and-code.md:571).
  - The fix that worked in a working builder: a post-hook on the tool that adds one plain instruction line to the result, for example a `what_to_do_next` field (tools-and-code.md:573). The step's prompt should also say it: "after every tool result, speak to the customer or call the next tool. Never end a turn with nothing." (tools-and-code.md:575)
- [INFERRED] A failed call of either kind is counted in run_cases' `hung` total (run_cases.py:116). A silent turn does not always show as a slow turn. The metric measures only from a customer message to a later message (run_cases.py:112-113), so if the customer says "Hello?" before hanging up, the gap restarts from that message (§13.7). A high `hung` count with a low median therefore suggests a silent turn more than a busy model; the transcript (`get_call`) settles it.

### 10.2 Messages

Each entry has `role`, `message`, `nodeId`, `messageId` and `secondsFromStart` (api.md:314) [DOC].

| `role` | `message` contains (api.md:316-320) |
|---|---|
| `assistant` | What the agent said |
| `user` | What the caller said |
| `system` | "A JSON string that describes one engine event". Parse it with `json.loads` [INFERRED] |

### 10.3 System events "seen in a trial call" (api.md:322-330): an observed set, not a full list

| `event` | Content |
|---|---|
| `node_enter` | `node`, `from_node`, `reason` |
| `function_call_start` | `function` and `args`. "For an `api_call` the args are the full request: `url`, `method`, `headers`, `body`" |
| `function_call_complete` | `function` and `result` |
| `route_evaluated` | `matched`, `from_node`, `target`, `reason`, a `branches` list with the result of every condition, and `variable_table` with all variables at that moment |
| `error` | `message` and `details` |

- "`route_evaluated` is the fastest way to learn why a transition did or did not fire. Each branch shows the variable, the operand and the result." (api.md:332) [DOC].
- [INFERRED] Because `function_call_start` logs full request headers, anything placed in an `api_call` header shows up in every transcript.

**Other strings seen in trial calls**, documented elsewhere in the kit [DOC]:
- An error event "The model returned no speakable content" appeared after a model turn with no text and no tool call (tools-and-code.md:219).
- "The function `<name>` is not currently available." appeared when the model called a tool that the current node did not list (tools-and-code.md:221).
- The `result` of an `api_call` is an envelope: `{"status": "success", "data": <the API's JSON body>, "message": "Successfully executed POST request", "status_code": 200, "header": {…}}` (tools-and-code.md:250-262).
- The `result` of a successful `code_exec` is `{"status": "success", "data": null, "message": "Code executed successfully", "status_code": 200}`. The snippet's values reach the workflow only through `vars` (tools-and-code.md:472-478).
- In the variable table, the model's arguments are stored as `<tool>_args.<field>` (tools-and-code.md:97, 266-275).

### 10.4 Snapshots and variables

- "User and assistant messages in the trial call also carried a `workflowSnapshot` with `currentNode`, `previousNode`, `nodeTurnCount`, `totalTurnCount`, `transitionHistory`, `enteredNodes` and `variableTable`. Each entry of `variableTable` has `value`, `confidence`, `source` and `source_node`. Whether a query parameter is needed to receive the snapshots is not confirmed." (api.md:334) [DOC]. This was one observation, not a guaranteed contract.
- "To check whether a variable arrived, read `variable_table` or `variableTable`. Finding the variable's name in a prompt or in a code body proves nothing about its value." (api.md:336) [DOC].
- "`freya.get_call(call_id)["messages"]` is the full transcript with the tool calls. `run_cases.py --out results/run.json` saves the call id of every customer." (README.md:99) [DOC].

### 10.5 The minimal loop that api.md suggests (api.md:338-349)

1. Build the workflow JSON.
2. `POST /api/v2/workflow?dryRun=true` and fix what it rejects.
3. `POST /api/v2/workflow`. Keep `workflow.agentId`.
4. `POST /api/v2/personas` once. Keep the ids.
5. `POST /api/v2/simulations` with the agent id, the persona ids and the call variables.
6. Poll `GET /api/v2/simulations/{id}` until the status is final.
7. `GET .../iterations`, then `GET .../iterations/{id}` for the runs.
8. For each failed run, `GET /api/v2/call/{callId}` and read the events.

"For everything else, see https://docs.freyavoice.ai." (api.md:349) [DOC].

[INFERRED] Step 3 creates a new workflow every time, and the loop never updates or publishes. Repeated as written, it fills the 200-workflow cap. The repeatable form is update and publish (§4.3-4.4), or `save_workflow`. Chat is not part of this loop.

---

## 11. `freya.py`, function by function

Docstring: "Thin client for the Freya API. Standard library only." It shows `export FREYA_API_KEY=fak_...` ("your workspace key") and `export FREYA_API_URL=https://staging-app.freyavoice.ai` ("default") (freya.py:1-5) [CODE].

Imports: `json, os, time, urllib.request, urllib.error, urllib.parse` (freya.py:6). `pathlib` is imported inside `save_workflow` (freya.py:41) [CODE].

### 11.1 Configuration and environment variables

| Variable | Line | When read | Default | Effect |
|---|---|---|---|---|
| `FREYA_API_URL` | 8 | at import | `https://staging-app.freyavoice.ai` | Base URL |
| `FREYA_API_KEY` | 10 | at import | `""`, which gives the header `"Bearer "` | Bearer token |
| `FREYA_WORKSPACE_ID` | 28 | on the first `workspace_id()` call | none | Overrides the first listed workspace. **The workspaces GET is still made first** |
| `FREYA_AGENT_PROVIDER` | 84 | at import | `experimental-5` | Agent model provider. "Organisers can point a test at another model" |
| `FREYA_AGENT_MODEL` | 84 | at import | `experimental-5` | Agent model name |
| `FREYA_SIM_CONCURRENCY` | 87 | at import, because it is a default argument | `5` | `maxConcurrentCalls`. A non-integer value crashes the import [INFERRED] |

- [INFERRED] The key and URL are fixed at import time. Setting `os.environ["FREYA_API_KEY"]` after `import freya` has no effect.
- `HEADERS` = `Authorization: "Bearer " + key`, `Content-Type: application/json`, `User-Agent: Mozilla/5.0 (build-the-builder)` (freya.py:10) [CODE].
- Not read by freya.py: `FREYA_BANK_TEAM_KEY` and `FREYA_BANK_HOST`. Those belong to score.py (score.py:7, 12) [CODE].

### 11.2 `api(method, path, body=None, **params)` (freya.py:12-20)

- Docstring: "Call the API and return the `result` part of its {success, data: {message, result}} envelope." [CODE]
- Query string: `"?" + urllib.parse.urlencode(params)` when keyword parameters are given (freya.py:14). Booleans go as strings, for example `dryRun="true"` (freya.py:48) [CODE].
- The request body is `json.dumps(body).encode()` only when `body is not None`, so GETs carry no body. The method is explicit, and the headers are always `HEADERS` (freya.py:15) [CODE].
- Timeout: `urlopen(req, timeout=120)`, which is **120 s per request** (freya.py:17) [CODE].
- **Errors:** any `urllib.error.HTTPError` (a non-2xx status) is re-raised as `RuntimeError(f"{method} {path} -> {e.code}: {e.read().decode()[:1500]}")` with `from None` (freya.py:18-19) [CODE].
  - The message holds the method, the path **without** the query string, the status code and the first 1500 characters of the body.
- **Not converted into `RuntimeError`** [CODE][INFERRED]:
  - network errors (`URLError`)
  - timeouts (`TimeoutError` / `socket.timeout`)
  - a 2xx body that is not JSON (`JSONDecodeError`)

  Callers that catch only `RuntimeError`, such as `run_simulation`'s retry loop, let these through.
- **Return value:** `out.get("data", {}).get("result", out) if isinstance(out, dict) else out` (freya.py:20) [CODE].

  | Response JSON | Returned |
  |---|---|
  | `data.result` present | `data.result`. This can be `None` if the JSON holds `null` |
  | no `data` key | the **whole envelope** |
  | `data` present without `result` | the **whole envelope**, not `data` |
  | `data` not a dict (for example `null`) | `AttributeError` |
  | top-level JSON not a dict | returned as is |

- `success` is never checked. No retries, no backoff, no rate-limit handling [CODE].

### 11.3 `workspace_id()` (freya.py:22-29)

- Docstring: "The workspace your key belongs to. List routes need it as a query parameter." [CODE]
- A module global `_ws` caches the value for the life of the process [CODE].
- First call: `r = api("GET", "/api/v2/workspaces")`, then `items = r.get("workspaces") or r.get("items") or r`, then `_ws = os.environ.get("FREYA_WORKSPACE_ID") or items[0]["id"]` [CODE].
  - It falls back to an undocumented `items` key, then to the bare result.
  - With `FREYA_WORKSPACE_ID` **unset**, an **empty** `workspaces` list is falsy, so the code falls through to the bare dict, and `items[0]` raises `KeyError` [INFERRED].
  - With `FREYA_WORKSPACE_ID` **set**, `or` short-circuits: `items[0]` is never evaluated, and line 28 raises nothing even if the list is empty (freya.py:28) [CODE]. Line 27 (the GET and the `.get` chain) still runs first.
  - The GET runs even when the env var is set. A failing GET still raises [CODE].
  - Only the first workspace is used, which fits "a team has one workspace" (page §Evaluation) [CODE][DOC].

### 11.4 `create_workflow(name, workflow)` (freya.py:31-34)

- Docstring: "Create a workflow. Freya creates its agent with it. Returns {workflow_id, agent_id}." [CODE]
- `POST /api/v2/workflow` with `{"name": name, "workflow": workflow}`, then `["workflow"]` with no bare-payload fallback. Returns `{"workflow_id": w["id"], "agent_id": w["agentId"]}`. Here `agentId` is required; in `export_workflow` it is optional [CODE].
- It does **not** publish, does **not** patch `agent_config`, and sends no `workspaceId` [CODE].

### 11.5 `save_workflow(slot, workflow, state_file=".freya-agents.json")` (freya.py:36-47)

Docstring, verbatim: "Create the workflow the first time, update the same one afterwards. Use this in your builder. `slot` is your own label, for example the brief's file name. A workspace holds a limited number of workflows, so a builder that creates a new one on every run stops working after a few runs." [CODE]

| Situation | What happens | Stored in the state file |
|---|---|---|
| State file missing | Starts from `{}` | |
| State file holds invalid JSON | `JSONDecodeError` | |
| Slot **new** | `create_workflow(f"{slot} {time.strftime('%m%d-%H%M%S')}", workflow)`. The platform name is the slot plus local-time `MMDD-HHMMSS`, with no year. **No publish, no model patch** | `{workflow_id, agent_id}`, with no `version` |
| Slot **exists** | `update_workflow(state[slot]["workflow_id"], workflow)` | `version` added or updated; `agent_id` unchanged |
| Update raises | The file is not rewritten, so the slot still points at the same workflow | unchanged |

- The state file is **relative to the current working directory** (freya.py:42) [CODE]. Running from another directory starts a fresh state and **creates a new workflow** [INFERRED]. The README and the skill run from the kit root (README.md:23; SKILL.md:8 "Work from the kit folder") [DOC].
- Return value: `state[slot]`, which is `{workflow_id, agent_id}` after a create and `{workflow_id, agent_id, version}` after an update (freya.py:47) [CODE]. README.md:22 says it prints `{"workflow_id": ..., "agent_id": ...}`; SKILL.md:21 says "The same slot updates the same workflow." [DOC]
- **The README's ten-minute start uses the slot `'base'`** (README.md:16-24) [DOC]. "You need Python 3.10 or newer." Then, from the kit root:
  1. `cp env.example env.sh`, with the comment "put your Freya API key in it, and a team key you make up" (README.md:19).
  2. `source env.sh` (README.md:20).
  3. `python3 -c "import freya,json; print(freya.save_workflow('base', json.load(open('examples/base-agent.json'))))"`. The README says it "prints {"workflow_id": ..., "agent_id": ...}" (README.md:22-23).
  4. `python3 tools/run_cases.py <agent_id> --brief A`, with the comment "ten practice customers, 3 to 11 minutes" (README.md:24).
  - [CODE] The first run of step 3 creates a workflow named `base MMDD-HHMMSS` and writes a `"base"` entry into `.freya-agents.json` in the current directory, which is the kit root (freya.py:42, 46). Running step 3 again finds the `"base"` slot and updates and publishes that same workflow instead of creating another (freya.py:43-44).
  - [INFERRED] The skill saves under a `<slot>` placeholder (SKILL.md:20), and freya.py's docstring suggests "the brief's file name" as the slot (freya.py:39). Unless the builder happens to pick `base`, its save creates a separate workflow and leaves the `base` one alone.
- If the stored workflow no longer exists on the platform, the update raises. Nothing re-creates it [INFERRED].
- There is no file locking, so two concurrent saves can race [INFERRED].
- The platform-side workflow name is never updated, because no PUT carries `name` [CODE].
- [INFERRED] A committed `.freya-agents.json` would point a fresh clone, such as the organisers' rerun of the top-ten builders (page §Submit), at **your** workflow ids. Without it, the first save in a fresh clone always creates.

### 11.6 `validate_workflow` (freya.py:48) and `update_workflow(workflow_id, workflow)` (freya.py:49-64)

`validate_workflow`: see §4.2.

`update_workflow` docstring, verbatim: "Update a workflow and publish the new version. Returns the published version number. An update alone only saves a new, unpublished version. Simulations and calls keep running the published one, so an update that is not published tests your old phone agent." [CODE]

Steps [CODE]:

1. `PUT /api/v2/workflow/{id}` with `{"workflow": workflow}`, the caller's definition (freya.py:54).
2. A comment about the default `agent_config` (freya.py:55-56; quoted in §5.3).
3. `GET /api/v2/workflow/{id}?workspaceId=<ws>`, then `["workflow"]["workflow"]` gives the stored definition `w` (freya.py:57). The first use of `workspace_id()` also triggers `GET /api/v2/workspaces`.
4. `ac = w.get("agent_config") or {}` and `llm = ac.get("llmConfig") or {}` (freya.py:58).
5. If `(llm.provider, llm.model) != (AGENT_LLM.provider, AGENT_LLM.model)`, it sets `ac["llmConfig"] = {**llm, **AGENT_LLM}` and PUTs `{"workflow": {**w, "agent_config": ac}}` (freya.py:59-60). This second PUT sends the **platform's stored copy**, already stripped by validation and holding any keys the platform added, not the caller's object.
6. `GET /api/v2/versions/workflow/{id}?workspaceId=<ws>`, then `["versions"]` with no fallback. An empty list makes `max()` raise `ValueError` (freya.py:61).
7. `newest = max(vs, key=lambda v: v["versionNumber"])` (freya.py:62).
8. If `not newest.get("isPublished")`: `POST /api/v2/versions/workflow/{id}/publish` with `{"versionId": newest["id"]}` and no `workspaceId` (freya.py:63).
9. It returns `newest["versionNumber"]` (freya.py:64).

HTTP calls per update: 3 (PUT, GET, versions GET) up to 6 (plus the workspaces GET on first use, the patch PUT and the publish POST) [INFERRED].

### 11.7 `export_workflow(workflow_id, path)` (freya.py:65-68)

- Docstring: "Write the workflow as it is on the platform to a file. This file is part of what you submit." [CODE]
- `GET /api/v2/workflow/{id}?workspaceId=<ws>`, then `["workflow"]` gives `w`. It writes `{"workflow_id": w["id"], "agent_id": w.get("agentId"), "updated_at": w.get("updatedAt"), "workflow": w["workflow"]}` with `indent=1` and returns `path` [CODE].
  - `agent_id` and `updated_at` become `null` if the keys are missing.
  - The file is opened without `with`; CPython closes it on garbage collection.
- "You export each phone agent to a file with `freya.export_workflow(workflow_id, "<brief>.workflow.json")` and submit those files. We load them into our own workspace to test them, so what you export is what we score." (README.md:75; page §Submit) [DOC].
- [UNCERTAIN] Whether the GET returns the newest saved version or the published one (§4.5), and whether the organisers' import keeps the exported `agent_config`.

### 11.8 `create_personas(personas)` (freya.py:69)

`api("POST", "/api/v2/personas", {"personas": personas})`. It returns the whole `result` [CODE].

### 11.9 `get_iteration(sim_id, it_id)` (freya.py:70-78)

- Docstring: "One iteration with ALL its runs. The route returns 30 runs by default and 100 at most, so this reads page by page." [CODE]
- Loop: `GET …/iterations/{it_id}?limit=100&offset=<off>`. The first page becomes `out`, keeping its `iteration` and `runsTotal`. Later pages' `runs` are appended. `off += 100`. It stops when a page holds fewer than 100 runs [CODE].
- It never compares with `runsTotal` [CODE]. If the total is an exact multiple of 100, one extra request returns an empty page. If the server capped `limit` below 100, the loop would stop after page one and silently truncate [INFERRED].
- No `workspaceId`. A missing `runs` key raises `KeyError` [CODE].

### 11.10 `get_call(call_id)` (freya.py:79-81)

Docstring: "One simulated call: `messages` holds the transcript, tool calls included. Run ids and call ids come from get_iteration()['runs']." The code is `GET /api/v2/call/{call_id}`, then `["call"]` with no fallback [CODE].

### 11.11 `run_simulation(agent_id, name, variables_by_persona, max_seconds=420, concurrency=int(os.environ.get("FREYA_SIM_CONCURRENCY", "5")))` (freya.py:87-106)

- The docstring says it returns `(simulation_id, iteration_id)`, but the code returns a **3-tuple** `(sim_id, its[0]["id"], s.get("status"))`. run_cases unpacks three values (freya.py:88, 106; run_cases.py:88) [CODE].
- **Create loop** (freya.py:89-99). The comment reads "a workspace runs one simulation at a time: wait for the running one instead of failing".
  - It POSTs the body from §8.1.
  - On a `RuntimeError` whose text contains `"concurrent simulations"`, it prints `another simulation is running in this workspace, waiting 30 s` and sleeps 30 s. There is **no retry cap**.
  - Any other `RuntimeError` is re-raised. Network errors and timeouts pass through.
- `sim_id = (sim.get("simulation") or sim)["id"]`, with a fallback to the bare payload (freya.py:100) [CODE].
- **Poll loop** (freya.py:101-104):
  - It sleeps 10 s **before** every GET, the first one included.
  - `s = s.get("simulation") or s`. It stops when `status` is `completed`, `failed` or `paused`.
  - There is **no overall timeout**. A simulation stuck at `running` (README.md:103) hangs the caller forever [CODE].
  - If the polling raises, the function aborts while the simulation keeps running on the platform. The next create then waits in the "concurrent simulations" loop [INFERRED].
- **Iterations** (freya.py:105-106): `its.get("iterations") or its.get("items") or its`, then `its[0]["id"]`. An empty `iterations` list falls through to the bare dict, and `its[0]` raises `KeyError` [INFERRED].
- `mode` is always `"chat"` and `runsPerPersona` always `1`. For anything else, call `api()` directly [CODE].
- One call blocks for the whole simulation, 3 to 11 minutes for ten customers (README.md:88) [DOC].

### 11.12 Mismatches between api.md and freya.py

| # | api.md says | freya.py does | Status |
|---|---|---|---|
| M1 | "`freya.update_workflow` and `freya.save_workflow` do both steps" (update + publish) (api.md:115) | On a new slot, `save_workflow` only creates: no publish, no model patch (freya.py:45-46) | Contradiction on the first save; see §5.4 |
| M2 | Workspace parameter name "not confirmed" (api.md:139); the GET-workflow example has none (api.md:122-124) | Uses `workspaceId` on GET workflow and GET versions (freya.py:57, 61, 67), as api.md:107 does | api.md contradicts itself |
| M3 | "List routes need the workspace id" (api.md:139) | The iterations **list** goes without it (freya.py:105) | Either the rule is too broad or that route is scoped by simulation id [UNCERTAIN] |
| M4 | "The reference client does not call this route" (GET workflow) (api.md:127) | Calls it (freya.py:57, 67) | api.md is stale [INFERRED] |
| M5 | Fall back to the bare payload when `workflow`, `simulation`, `iterations` or `workspaces` is missing (api.md:44) | Falls back for `simulation` (100, 103), `iterations` (105, plus `items`) and `workspaces` (27, plus `items`). **Not** for `workflow` (33, 57, 67), `versions` (61), `runs` (74-78) or `call` (81) | Partial; adds an undocumented `items` fallback |
| M6 | The reference client "prints the response body" on a dry-run error (api.md:85) | Raises `RuntimeError` with the body cut to 1500 characters (freya.py:19, 48) | Different behaviour |
| M7 | "Compare the number you read with `runsTotal`. `freya.get_iteration` does this for you." (api.md:288) | Reads until a short page; never compares (freya.py:72-78) | api.md overstates |
| M8 | A platform-filled `agent_config` is deleted when a PUT leaves it out (api.md:101) | "The platform fills in a default agent_config" (freya.py:55), and the code copes with absent or present (freya.py:58) | [UNCERTAIN] which happens |
| M9 | Leave `agent_config` out (README.md:103; SKILL.md:19; workflow-format.md:62) | freya.py sends `agent_config` in its patch PUT (freya.py:60) | Not a real conflict: the builder leaves it out and freya.py adds only the model |
| M10 | Poll "every 10 seconds" (api.md:238) | Sleeps 10 s before every poll (freya.py:102) | Consistent |
| M11 | Chat routes documented (api.md:240-252) | No helper | Gap |
| M12 | Personas list exists but is unconfirmed (api.md:166-176) | No helper | Gap |
| M13 | Example UA `Mozilla/5.0 (my-builder)` (api.md:16, 25) | `Mozilla/5.0 (build-the-builder)` (freya.py:10) | Any browser-like string works |
| M14 | Persona tags example `["practice"]` (api.md:154) | run_cases uses `["hackathon", "brief-X"]` (run_cases.py:47) | Tags are free-form |
| M15 | The `run_simulation` docstring says 2 values (freya.py:88) | Returns 3 (freya.py:106) | Internal mismatch |
| M16 | "stops working after a few runs" (freya.py:39-40) | The cap is 200 (README.md:87) | Loose wording |

### 11.13 What freya.py does not provide

[CODE] There are no helpers for:
- chat (`/chat/message`, `/chat/end`)
- listing personas
- reading a simulation's `agentVersionNumber`
- a simulation timeout or cancel
- reading the stored workflow back for a diff (`export_workflow` writes it to a file; `api("GET", …)` returns it)
- deleting anything

---

## 12. The practice mock bank, as the harness sees it

The bank's tools themselves (fields, enums, rules) belong to the tool-API chapter. This section covers only what the harness and the scorer touch.

### 12.1 Hosts, routes and keys

| Item | Value | Source |
|---|---|---|
| Host | `FREYA_BANK_HOST`, default `https://freya-bank-mock.freyavoice.workers.dev` | score.py:7 [CODE] |
| Tool base | `https://freya-bank-mock.freyavoice.workers.dev/v1`: `/verify_identity`, `/get_account`, `/create_promise`, `/add_note`, `/schedule_callback`, `/transfer_to_agent`, `/close_call` | openapi.json:8-10, 15, 89, 172, 234, 298, 354, 409 [DOC] |
| Tool auth | none: "The seven tool calls need no key: the customer_id in the body is the secret of one call." | openapi.json:6 [DOC] |
| Practice routes | `POST /v1/practice/sessions` with `{"case": "<id>"}`; `GET /v1/practice/ledger/<customer_id>` | run_cases.py:86, 93; score.py:38 [CODE] |
| Practice auth | header `x-team-key: $FREYA_BANK_TEAM_KEY` | score.py:12 [CODE] |
| Scorer User-Agent | `freya-bank-scorer/0.1` (not browser-like; the bank is a separate host) | score.py:8 [CODE] |
| Team key rule | "any secret of 16+ characters your team picks, the same one every time" | run_cases.py:5; env.example:3 [DOC] |
| Ownership | "Your team key owns your practice sessions and records." | page §Data [DOC] |
| What the bank is | "Mock of the bank's systems… We host it. Every call is written to the ledger the scorer reads. The service does not enforce the brief: it records a promise on a holiday or past the deadline without complaint. Following the brief is the agent's job." | openapi.json:6; page §Evaluation [DOC] |

### 12.2 Practice sessions

- The harness opens **one fresh session per case per simulation attempt**: "run_cases.py opens a fresh customer per case." (page §FAQ; run_cases.py:86) [DOC][CODE].
- What a session returns:
  - `{ok, variables: {customer_id: "c_<uuid-ish>", first_name, last_name, title, now}}`, with a fresh `customer_id` each time [PROBED-earlier] (research/read-api-and-testing.md:126-127).
  - `now` is fixed per case: `2026-10-14T11:00` for every PUB case. A `now` sent in the request body is **ignored** [PROBED-earlier] (research/read-api-and-testing.md:128). This matches "Every case runs Wed 14 Oct 2026 11:00." (page §Data) [DOC].
- Errors [PROBED-earlier] (research/read-api-and-testing.md:120-122, 129):
  - An unknown case, an empty body or a custom customer object gives 404 `"unknown practice case"`.
  - No key gives 401 "send X-Team-Key…".
  - A ledger read with the wrong key gives `"unknown customer_id for this team key"`.
- "Builder cannot open its own practice customers: practice bank serves PUB-01..13 only" (page §FAQ) [DOC].
- Products, identity answers and failure injection are held on the server, keyed by case id [PROBED-earlier] (research/read-api-and-testing.md:130). This fits the harness sending only `{"case": id}` (run_cases.py:86) [CODE].
- **Sessions are single-use.** After `close_call`, every tool returns `"the call is already closed"` [PROBED-earlier] (research/read-api-and-testing.md:159). The tool API says the same: "Always the last tool call. Nothing is accepted after it." (openapi.json:411) [DOC].
- [UNCERTAIN] Whether a practice session expires when unused. The "5 min idle" rule is stated only for the dashboard customer (page §FAQ).

### 12.3 The ledger

Fields seen in the earlier probe [PROBED-earlier] (research/read-api-and-testing.md:133-141):
- `case`, `team` (a hash of the key), `now`
- `verified {field: bool}`, `wrong` (count), `hinted`
- `promises[{promise_id, product_id, type, amount, date}]`, `notes`, `callbacks`, `transfers`
- `outcome`, `reason`
- `failures {tool: n}`
- `calls[{n, tool, args, status, result}]`
- `last_at`

`hinted` probably records the `verify_identity` response field `hint`. That field's only allowed value is `day_month_swapped` (openapi.json:72-77). Brief A rule 13 explains the hint (briefs/brief-a.md:42) [DOC][INFERRED].

Fields the scorer actually reads [CODE] (score.py:19-33):

| Ledger field | Used as |
|---|---|
| `outcome`, `reason` | check 1 |
| `promises[].product_id`, `.amount`, `.date` | check 2 |
| `notes[].product_id` (optional), `.reason` | check 3 |
| `callbacks[].date`, `.time` | check 4 |
| `transfers[].queue` | check 5 |
| `calls[].tool`, `calls[].result.error` | checks 6-8; also the printed tool chain (run_cases.py:98-99) |

### 12.4 Tool responses that matter to scoring

- Every tool documents a `200` response, "`ok` is false when the action was not carried out.", and a `500`, "The service failed. Nothing was recorded. The call may be repeated." (openapi.json:51, 83-85 and the same pair for each tool) [DOC].
- In the earlier probe, business errors came back as HTTP 200 with `ok: false` [PROBED-earlier] (research/read-api-and-testing.md:144). That probe touched only PUB-01 and PUB-11. It never exercised PUB-10's injected failure (`faults: [{"tool": "create_promise", "fail_first_n": 1}]`, public-test-set.json PUB-10) [CODE].
- [UNCERTAIN] Whether the injected failure arrives as an HTTP 500 (as documented) or as 200 with `ok: false`, and how it appears in `calls[].result`.
- `get_account` before verification returns `{ok: false, error: "identity not verified"}`, and that call is logged in the ledger [PROBED-earlier] (research/read-api-and-testing.md:154). score.py fails the case on it (§14.2, check 7).
- `close_call.outcome` enum in the **practice** tool API: `promise`, `paid`, `transferred`, `no_promise`, `not_verified`, `not_reached` (openapi.json:422-431). `reason`: "Required for every outcome except promise and paid. See the table in the brief." (openapi.json:433-435) [DOC].

---

## 13. `tools/run_cases.py`, in full

### 13.1 Docstring and usage (run_cases.py:1-6)

> "Run cases against an agent and score them from the bank's ledger and the judge's reading of the conversation."
>
> `python tools/run_cases.py <agent_id> [--brief A|B] [--cases public-test-set.json] [--out results/run.json] [--reps 3] [--style talkative]`
>
> "Needs FREYA_API_KEY (your workspace) and FREYA_BANK_TEAM_KEY (any secret of 16+ characters your team picks, the same one every time)."

The usage line leaves out `--only` and `--rerun-if-slow`, which exist (run_cases.py:50) [CODE].

**Imports and paths** (run_cases.py:7-11) [CODE]:
- `ROOT` is the kit root.
- `ROOT` and `ROOT/tools` go first on `sys.path`.
- It imports `freya` and `from score import http, score_ledger`.
- Importing reads environment variables and does nothing else.

### 13.2 Command line (run_cases.py:50)

| Argument | Type | Default | Behaviour [CODE] |
|---|---|---|---|
| `agent_id` | positional | required | The **agent** id, not the workflow id |
| `--brief` | str, no `choices` | `None` | Keeps cases whose `brief` equals the value exactly. `A` gives PUB-01..10, `B` gives PUB-11..13, and omitting it gives all 13. Lowercase `a` matches **nothing** [INFERRED: the run then has 0 cases and still calls the simulation API with an empty persona list] |
| `--cases` | path | `ROOT/public-test-set.json` | Case file. Ids must be practice-bank ids, since only `id` is sent to the bank |
| `--out` | path | `None` | JSON results file, relative to the **current directory**. Parent folders are created |
| `--only` | str | `None` | Comma-separated ids, tested as `c["id"] in a.only.split(",")`. **No whitespace trimming**: `"PUB-01, PUB-02"` drops PUB-02 |
| `--reps` | int | `1` | Number of sequential simulations. A case must pass every one |
| `--style` | choice | `None` | `asks_back`, `corrects`, `in_words`, `pieces` or `talkative`. Applies to every selected case and **overrides** any per-case `style` |
| `--rerun-if-slow` | int | `0` | How many times a slow attempt may be thrown away and repeated (§13.9) |

### 13.3 Which case fields the harness reads

| Case field | Used for | Line |
|---|---|---|
| `id` | Persona name, cache key, the `{"case": id}` session request, rows | 47, 57, 86, 98 |
| `title` | Persona name | 47 |
| `brief` | `--brief` filter; persona tag `"brief-" + brief` | 47, 52 |
| `family` | Third-party detection (`== "Third party"`, exact case); printed line; rows; `final` | 38, 73, 98-99 |
| `third_party` (optional) | Third-party detection by flag. **No public case has it** | 38 |
| `level` | Printed line; rows | 98-99 |
| `variables.first_name`, `variables.last_name` | Persona text only | 36-37 |
| `identity` (dict) | The persona's identity sentences. It is read for every case, third party included; a missing key gives `KeyError` | 36, 41-44, 53 |
| `script` | Persona "WHAT HAPPENS IN THIS CALL" | 46 |
| `checks` (list) | The judge's `successCriteria` | 47 |
| `style` (optional) | Persona style, used only when `--style` is unset. **No public case has it** | 45 |
| `expected` | Ledger scoring | score.py:18 |
| `products`, `faults`, `variables.title`, `variables.now` | **Never read.** The bank holds products, identity and faults on the server [PROBED-earlier], and `now`/`title` come from the session. Editing these in a custom cases file changes nothing | none |

Public case keys are exactly `brief, checks, expected, family, faults (PUB-10 only), id, identity, level, products, script, title, variables`. All 13 cases use only `date_of_birth` and `phone_last4` as identity keys (public-test-set.json) [CODE].

### 13.4 How a case becomes a persona (run_cases.py:13-47)

**Fixed template `PERSONA`** (run_cases.py:13-24), verbatim:

```text
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

**`{who}` for the customer** (run_cases.py:40-44) [CODE]:
- With `me = first_name + " " + last_name`, the text is `"You are {me}. "`.
- Then comes one sentence per identity key in the case's key order, joined by spaces.
- Then `" Give these only when asked, and give the wrong ones where the text below says so."`

| Identity key | Sentence, verbatim (`{}` = raw value from `case.identity`) |
|---|---|
| `date_of_birth` | `Your date of birth is {} (say it in words, like '14 March 1988').` |
| `phone_last4` | `The last four digits of your phone number on file are {}.` |
| `postcode` | `The postcode of your registered address is {}.` |
| `birth_year` | `Your year of birth is {}.` |
| `company_number` | `Your company number is {}.` |
| `founded_year` | `The company was founded in {}.` |
| any other key `k` | `"Your " + k.replace("_", " ") + " is {}."` |

- The date of birth is inserted in **ISO** form (for example `1988-03-14`), followed by the instruction to say it in words. The example in brackets is always `'14 March 1988'`, which is PUB-01's date of birth and also the dashboard practice customer's (page §FAQ) [CODE][DOC].
- Four templates (`postcode`, `birth_year`, `company_number`, `founded_year`) are unused by public cases [CODE]. [INFERRED] They hint at the "other identity questions" of the final (README.md:71).

**`{who}` for a third party** (run_cases.py:38-39). This applies when `family == "Third party"` or `case.get("third_party")` is truthy. Verbatim:

> `You are NOT {me}. You answered this phone. You do not know {me}'s security answers and you would not give them. The text below says who you are.`

No identity values are given [CODE].

**Styles** (run_cases.py:26-33, 45-46). With `style = style or case.get("style")`, a set style appends `"\n\n" + STYLES[style]` after the RULES block. The comment says "How a customer talks. The facts of the case stay the same, only the way of saying them changes." Verbatim:

| Key | Appended text |
|---|---|
| `pieces` | `HOW YOU TALK: you give long numbers and dates in two parts. Say the first half, stop, and give the rest in your next turn or when asked. This replaces the rule about saying all of it in one turn.` |
| `corrects` | `HOW YOU TALK: the first time you say a day or an amount, you say a slightly different one first and correct yourself in the same sentence, like 'the 21st, sorry, I mean the 20th'. The corrected value is the one written above. Do this once or twice in the call, not more. Never do it with a security answer: those you say right the first time unless the text above says otherwise.` |
| `talkative` | `HOW YOU TALK: you talk a lot. Before most answers you add one or two sentences about your day, the traffic or how busy work is. Once in the call you mention that your cousin's wedding is on the 30th. It has nothing to do with any payment, and you never offer it as a payment day.` |
| `asks_back` | `HOW YOU TALK: twice in the call, before you answer, you ask a short question back, like 'why do you need that?' or 'which account is this about?'. Whatever the caller replies, you then give your answer.` |
| `in_words` | `HOW YOU TALK: you say every amount and every date in words and never in digits, like 'four hundred and fifty-five' and 'the twenty-second of October'. Postcodes, years and other codes you say digit by digit.` |

A per-case `style` that is not one of these five keys raises `KeyError`. Argparse checks only the command-line value [CODE].

**The persona object** (run_cases.py:47) [CODE]:

| Field | Value |
|---|---|
| `name` | `id + " " + title`, plus `" [style]"` when a style is set. Example: `PUB-02 A relative answers [pieces]` |
| `prompt` | The text above |
| `successCriteria` | `"All of these are true:\n- " + "\n- ".join(checks)` |
| `tags` | `["hackathon", "brief-" + brief]`, for example `["hackathon", "brief-A"]` |

**Rendered example, PUB-01, no style** (local offline render) [CODE]:

```text
WHO YOU ARE: You are Daniel Reyes. Your date of birth is 1988-03-14 (say it in words, like '14 March 1988'). The last four digits of your phone number on file are 4471. Give these only when asked, and give the wrong ones where the text below says so.

WHAT HAPPENS IN THIS CALL: Confirms he is Daniel Reyes. Date of birth 14 March 1988, last four digits 4471. Says he can pay the full amount today. Confirms at the read-back.
```

- `successCriteria`: `"All of these are true:\n- both security questions passed before get_account\n- the word 'collections' is not said before identity is verified\n- create_promise called exactly once\n- text-message sentence said after the promise"`
- Cache keys computed: `PUB-01:6d35a36de2`, `PUB-02:ba4c2d3ab2`, `PUB-03:399d279120`.

**What the persona is never told** [CODE][INFERRED]:
- The amounts owed, the products, the card last-four, the current date, the weekday and `now`.
- So the customer cannot catch a wrong amount or a wrong weekday in a read-back. It says "Yes, I confirm." when a read-back "matches what you agreed", and what it agreed comes only from the conversation.
- Wrong amounts and dates are caught by the ledger check, not by the customer.
- Card last-four can equal phone last-four: PUB-11 has `2288` for both and PUB-13 has `6604` for both (public-test-set.json) [CODE].

**What the customer's rules imply for the agent** [INFERRED]:
- The customer volunteers nothing, so the agent must ask, for example for the exact day.
- Anything the script does not cover gets "a short neutral answer".
- After a goodbye from the agent, the customer says "Thank you, goodbye." and then nothing. A goodbye spoken before `close_call` leaves a silent customer.
- `talkative` adds a decoy "30th". PUB-13's real requested date is 30 October ("Wants to pay both on 30 October"), so a `talkative` PUB-13 has both.

### 13.5 The persona cache (run_cases.py:54-62)

- File: `ROOT/.personas.json`, at the kit root, independent of the current directory. It maps `"<case id>:<first 10 hex of sha1(json.dumps(spec, sort_keys=True))>"` to a Freya persona id [CODE].
- The comment says "a persona is recreated whenever its text changes, so an edited case never runs with a stale customer" [CODE].
- Steps [CODE]:
  1. Build the `spec` for every selected case.
  2. Compute each key.
  3. Find the cases whose key is missing.
  4. Make **one** `freya.create_personas([...])` call for all of them.
  5. Zip the request with `result.personas`, which come back in request order (api.md:164).
  6. Rewrite the file with `indent=1`.
- Any change to `name`, `prompt`, `successCriteria` or `tags` makes a new persona. That means a change to `title`, `checks`, `brief`, `identity`, `script`, first or last name, or style [CODE].
- Old entries and old personas are never removed [CODE].
- The cache is **not keyed by workspace**. Switching `FREYA_API_KEY` to another workspace would reuse persona ids from the old workspace [INFERRED].

### 13.6 One simulation: `run_once(agent_id, cases, ids)` (run_cases.py:84-119)

1. **Open practice sessions** (line 86). For each case: `http("/v1/practice/sessions", {"case": id})["variables"]`. If the bank returns an error body, `["variables"]` raises `KeyError` and the run crashes [CODE].
2. **Start the timer** (line 87). `t0` starts *after* the sessions are opened.
3. **Run the simulation** (line 88). `freya.run_simulation(agent_id, f"cases {HH:MM:SS}", {persona_id: session_variables})`.
   - The session's `variables` go in **verbatim** as that persona's call variables. So `customer_id` and `now` always come from the bank, never from the case file [CODE].
   - The rest is §11.11: `mode: "chat"`, concurrency 5 by default, 420 s per call, the agent model for the three agent overrides, gemini for persona and judge. It waits 30 s at a time while another simulation runs, polls every 10 s with no timeout, and takes `iterations[0]`.
4. **Duration** (line 89). `took` runs from after the sessions to the end of the simulation, so it includes queue waits and up to 10 s of polling slack [CODE].
5. **Judge verdicts** (line 90). `freya.get_iteration` reads all runs. Verdicts are keyed by `personaId` [CODE].
6. **Score each case** (lines 92-97):
   - `led = http("/v1/practice/ledger/" + customer_id)`.
   - `r = score_ledger(case, led)` (§14).
   - `j = judge.get(persona_id, {})`. If `j.get("outcome") != "pass"`, it appends `"conversation: " + <judge reason with whitespace collapsed, or "no verdict">`, cut to **400** characters.
   - `pass = not failed`. **A case passes only when every ledger check passes AND the judge says `pass`** [CODE].
7. **Row** (line 98): `{id, level, family, pass, failed, call_id (= run.callId), tools (ledger tool names in order), customer_id}` [CODE].
8. **Printed line** (lines 99-100):
   - `PASS|FAIL`, the id, the level padded to 6, the family padded to 14, `|`, then the **ledger's** tool chain joined by ` > `.
   - `verify_identity` is shown as `verify` and `create_promise` as `promise`. An empty chain shows `(no tool calls)`.
   - Each failure follows on its own line: seven spaces, `- `, then the reason cut to **260** characters.
   - Format illustration built from the print statements, not output of a real run:

   ```text
   PASS PUB-01 easy   Happy path     | verify > verify > get_account > promise > close_call
   FAIL PUB-10 hard   Tool failure   | (no tool calls)
          - conversation: no verdict
   ```

   - The chain shows only calls that reached the bank, rejected ones included.
   - [UNCERTAIN] Whether an injected 500 failure is logged in `calls`, so whether a retried `create_promise` shows twice.
9. **Slowest agent turn** (lines 101-114). See §13.7.
10. **Wait summary** (lines 115-118). See §13.7.
11. **Return** (line 119): `rows, sim_id, it_id, status, took, med`, with `med = 0` if no waits were measured [CODE].

- `run_once` never checks `status`. In a `failed` or `paused` simulation, the cases without a run show `conversation: no verdict` [INFERRED].
- `score_ledger` indexes `promises`, `notes`, `callbacks`, `transfers` and `calls` directly. A ledger error body crashes the whole run with `KeyError` [CODE].

### 13.7 The slowest-turn metric (run_cases.py:101-118)

The comment reads: "How long the phone agent kept the customer waiting. A call whose customer hung up after long silences says something about the speed of the model at that moment, not only about the agent." [CODE]

The algorithm, per row with a `call_id` [CODE]:
- `freya.get_call(call_id)`. Any exception skips that call silently.
- Walk `messages` and skip entries without `secondsFromStart`:
  - A `user` message sets `last_user = t`. Back-to-back user messages keep the later time.
  - Any other message (`system` or `assistant`) after a user message updates `worst = max(worst, t - last_user)`.
  - Only an `assistant` message resets `last_user`.
- The result is the longest gap from a customer message to the agent's next spoken reply. Tool calls and engine events in between count as part of the wait. The time before the first user message (the greeting) does not count.
- If the customer speaks and the agent never answers, for example a hang-up after a tool call, the gap runs to the last system event.
- Offline checks of a copy of the loop:

  | Messages | Result |
  |---|---|
  | user@2 → system@3, system@5 → assistant@6 | 4 |
  | user@2 → system@30 | 28 |
  | user@2, user@9 → assistant@10 | 1 |

- It stores `slowest_turn_s` (rounded to 0.1) and `ended = call.endedReason` on the row. **Every fetched call is added to `waits`**, including calls with no user message, which contribute 0 and pull the median down [CODE].

Summary (lines 115-118) [CODE]:
- `med = sorted(waits)[len(waits) // 2]`. This is the **upper** median: for `[1, 2, 30, 40]` it gives `30`.
- `hung` = the number of rows with `ended == "customer-ended-call"` that did not pass.
- It prints `slowest agent turn per call: median {med:.0f} s, worst {max:.0f} s. Failed calls where the customer hung up: {hung}.`
- If `med > 10` it also prints `WARNING: the phone agent was slow in this run. If the same agent is fast in another run, the model was busy and this score is too low.`
- README.md:100 says run_cases "prints the slowest agent turn per call". It actually prints only the median and the worst. Per-call values are kept only in the `--out` rows [DOC][CODE].

### 13.8 Repetitions, final verdict and output (run_cases.py:63-82)

- It creates `ROOT/results/`.
- For each rep it runs the attempt loop (§13.9), keeps the **last** attempt's rows and adds that attempt's `took`.
- With `reps > 1` it prints `-- run {k} of {N}: {passed} / {total} passed, {took:.0f} s` and a blank line.
- `need = a.reps`, commented "a customer counts only when every run passes".
- `final[k] = {id, family, passes, runs: N, pass: passes >= need}`.
- With `reps > 1` it prints one line per case: `PASS|FAIL <id> <passes>/<runs>`.
- The last line, after a blank line. Format illustration with made-up numbers, not a real run [CODE]:

  ```text
  9 / 10 passed (bank records and conversation checks), a customer counts with 3 of 3 runs. Last simulation <sim_id>, status completed, 1234 s.
  ```

  With `--reps 1` the clause ", a customer counts with…" is absent. The seconds are the sum of the kept attempts. The status is the last attempt's.
- **Edge case:** `--reps 0` never assigns `sim_id`, so line 77 raises `NameError` [CODE].

### 13.9 `--rerun-if-slow K` (run_cases.py:65-70)

```python
for attempt in range(1 + a.rerun_if_slow):   # organisers: a run made while the model was slow is thrown away and repeated
    rows, sim_id, it_id, status, took, med = run_once(...)
    if med <= 10 or attempt == a.rerun_if_slow: break
    print(f"-- run discarded: median slowest turn {med:.0f} s. Waiting 5 minutes, then repeating it.\n"); time.sleep(300)
```

- `K = 0` (the default) never repeats [CODE].
- An attempt is thrown away only when `med > 10` (the upper median). The last attempt is always kept, even if it is still slow [CODE].
- With no transcripts fetched, `med` is 0, so the attempt is never thrown away [CODE].
- A thrown-away attempt has already printed its PASS/FAIL lines and used up new practice sessions. It is left out of `log.jsonl`, `--out` and the total seconds [CODE].
- The repeat opens new sessions but **reuses the same personas** [CODE].
- [INFERRED] The comment "organisers: …" says the official scoring also throws away slow runs. How many repeats they allow is [UNCERTAIN].

### 13.10 Files written

| File | When | Content [CODE] |
|---|---|---|
| `ROOT/.personas.json` | When new personas are created | `{"<id>:<hash10>": "<persona id>", …}` |
| `ROOT/results/log.jsonl` | Always; one line appended per invocation ("one line per run, the record of how the score moved over time") | `{"at": local "%Y-%m-%d %H:%M:%S", "agent_id", "brief" (null if not given), "runs", "passed", "total", "seconds", "failed": [ids]}`. **The style and the case file are not recorded** |
| `--out` path | When `--out` is given | `{"agent_id", "simulation_id" (last), "iteration_id" (last), "seconds", "passed", "total", "runs", "final", "rows" (last rep), "all_rows" (every rep)}`. Rows hold `call_id`, `customer_id`, `tools`, `failed`, and `slowest_turn_s`/`ended` where the call was fetched. The simulation status and the style are not saved |

### 13.11 Network traffic per invocation [INFERRED from the code]

- N bank POSTs for sessions.
- 0 or 1 persona POST.
- 1 or more simulation POSTs: one every 30 s while the workspace is busy.
- One simulation GET every 10 s.
- 1 iterations GET and at least 1 iteration-page GET.
- N ledger GETs.
- N call GETs.

Timeouts: 20 s per bank call (score.py:14) and 120 s per Freya call (freya.py:17) [CODE]. All of this is multiplied by `reps × attempts`.

### 13.12 Other edge cases [CODE][INFERRED]

- A custom `--cases` file can change `script`, `checks`, `expected`, `title`, per-case `style` and `third_party` for a PUB id. The bank still serves that PUB customer's server-side products, identity and faults.
- Changing `identity` in a custom file changes only what the persona says. The bank would then reject those answers [INFERRED].
- A non-PUB id in a custom file makes the session request fail with "unknown practice case" [PROBED-earlier], and `["variables"]` raises `KeyError` [CODE].
- Two cases with the same id collapse into one entry in the `ident`, `spec`, `key` and `ids` dicts. So one simulation cannot hold three copies of one case [CODE].
- The judge dict is keyed by `personaId`. With `runsPerPersona > 1`, later runs would overwrite earlier ones [CODE].
- A missing `identity` key raises `KeyError` even for third-party cases (line 53) [CODE].

---

## 14. `tools/score.py`, in full

### 14.1 Header and HTTP helper (score.py:1-15)

- Docstring: "Score one finished session from the mock's ledger. Ledger checks only; transcript checks come from the judge." Signature: `score_ledger(case, ledger) -> {"pass": bool, "failed": [reasons]}` [CODE].
- `HOST` = env `FREYA_BANK_HOST` or `https://freya-bank-mock.freyavoice.workers.dev` (score.py:7) [CODE].
- Headers: `user-agent: freya-bank-scorer/0.1` and `content-type: application/json`, plus `x-team-key: os.environ["FREYA_BANK_TEAM_KEY"]`. That env var is **required**; if it is unset the result is `KeyError` (score.py:8, 12) [CODE].
- `http(path, body=None)` [CODE]:
  - It sends a POST with the JSON body when `body is not None`, otherwise a GET. The timeout is 20 s.
  - On an HTTP error it **returns the error body parsed as JSON** and does not raise.
  - A non-JSON error body raises a JSON decode error. Network errors and timeouts propagate.
  - It uses `urllib.error` without importing it; that works because `urllib.request` imports it.

### 14.2 The eight ledger checks (score.py:17-34)

`exp = case["expected"]`. Each failed check appends one reason.

| # | Check | Exact comparison [CODE] | Failure text |
|---|---|---|---|
| 1 | Outcome | `(led.get("outcome"), led.get("reason")) != (exp["outcome"], exp.get("reason"))`. Missing keys count as `None`. An expected `"reason": null` requires the ledger to hold no reason or null. [INFERRED] A `reason: ""` sent with `promise` or `paid` would fail if the bank stores it | `outcome (got), expected (exp)` |
| 2 | Promises | Sorted lists of `(product_id, round(float(amount), 2), date)` must be equal. This is multiset equality. A string amount like `"220"` becomes a float. Dates are compared as exact strings (`"2026-10-16"`). `promise_id` and `type` are ignored | `promises [...], expected [...]` |
| 3 | Notes | Sorted `(n.get("product_id"), n["reason"])` must be equal. **Note text is ignored.** A missing `product_id` counts as `None`. **Extra notes fail** | `notes [...], expected [...]` |
| 4 | Callbacks | Sorted `(date, time)` exact strings, for example `("2026-10-15", "11:00")`. `11:00:00` would not match | `callbacks <raw ledger list>, expected <raw list>` |
| 5 | Transfers | Sorted list of `queue` strings; other fields are ignored | `transfers <raw>, expected <raw>` |
| 6 | Closed | Fails if `calls` is empty or `calls[-1]["tool"] != "close_call"`. [UNCERTAIN] Whether rejected calls made after `close_call` are appended to `calls`; if they are, they fail this check | `the call was not closed with close_call` |
| 7 | No account or promise before identity | Commented "policy from the ledger: tools the brief forbids before identity is verified". The **first** `get_account` or `create_promise` whose `result.get("error") == "identity not verified"` fails the case, even if a later retry succeeds. Only these two tools and this exact error string count. It assumes `result` is a dict | `<tool> called before identity was verified` |
| 8 | Not on the line | If `exp["outcome"]` is `"not_reached"`, `"no_contact"` or `"unreached"`, **any** `verify_identity` or `get_account` call fails the case | `identity or account tools used although the customer was not on the line` |

It returns `{"pass": not bad, "failed": bad}`.

**What the ledger check does not look at** [CODE]:
- how many `create_promise` calls were made (it sees only the final `promises`)
- `verified`, `wrong`, `failures`
- the arguments of rejected calls
- anything about wording

Those belong to the judge, through `checks` such as "create_promise called exactly once" or "the phone question is asked again once, the date of birth is not" (public-test-set.json PUB-01, PUB-12).

**Outcome names in check 8.** The practice `close_call` enum has only `not_reached` (openapi.json:422-431). The bank rejects `no_contact` with "unknown outcome" [PROBED-earlier] (research/read-api-and-testing.md:159). So `no_contact` and `unreached` cannot occur on the practice bank. [INFERRED] They anticipate renamed outcomes in the final briefs ("another outcome table", README.md:71).

**Edge cases** [CODE][INFERRED]:
- If the ledger holds one note **with** a `product_id` and one **without**, sorting compares `None` with a string and raises `TypeError: '<' not supported between instances of 'str' and 'NoneType'`. The whole run crashes. I checked this offline with `sorted([(None, "refused"), ("p1", "refused")])`.
- A non-numeric ledger `amount` would raise `ValueError` in `float()`.

### 14.3 CLI (score.py:36-39)

`python tools/score.py <case_id> <customer_id>` [CODE]:
- It always loads `../public-test-set.json` next to the script and ignores any custom cases file.
- It GETs the ledger, prints `json.dumps(result, indent=1)`, and exits 0 on pass, 1 on fail.
- Ledger only: no judge.

### 14.4 What the 13 public cases expect from the ledger

All from public-test-set.json [CODE]. `now` = `2026-10-14T11:00` for all cases (a Wednesday, per page §Data).

| Case | Brief | Family | Expected `(outcome, reason)` | Promises `(product, amount, date)` | Notes | Callbacks | Transfers |
|---|---|---|---|---|---|---|---|
| PUB-01 | A | Happy path | `promise`, null | `p1 420.0 2026-10-14` | none | none | none |
| PUB-02 | A | Third party | `not_reached`, `callback` | none | none | `2026-10-15 11:00` | none |
| PUB-03 | A | Identity | `not_verified`, `failed` | none | none | none | none |
| PUB-04 | A | Dates | `promise`, null | `p1 1250.0 2026-10-23` | none | none | none |
| PUB-05 | A | Hardship | `no_promise`, `hardship` | none | **none** | none | none |
| PUB-06 | A | Amounts | `promise`, null | `p1 637.5 2026-10-16` | none | none | none |
| PUB-07 | A | Dates | `promise`, null | `p1 540.0 2026-10-27` | none | none | none |
| PUB-08 | A | Already paid | `paid`, null | none | **none** | none | none |
| PUB-09 | A | Restructuring | `transferred`, `restructuring` | none | none | none | `restructuring` |
| PUB-10 | A | Tool failure (fault: `create_promise` fails first 1) | `promise`, null | `p1 365.0 2026-10-16` | none | none | none |
| PUB-11 | B | Multi-product | `promise`, null | `p1 220.0`, `p2 640.0`, `p3 75.0`, all `2026-10-16` | none | none | none |
| PUB-12 | B | Multi-product | `promise`, null | `p1 510.0 2026-10-15` | `(p2, refused)`, `(p3, refused)` | none | none |
| PUB-13 | B | Multi-product | `promise`, null | `p1 300.0 2026-10-30`, `p2 900.0 2026-10-23` | none | none | none |

Checks 7 and 8 apply on top: check 8 bites on PUB-02 (no `verify_identity` and no `get_account` at all), and check 6 on every case.

---

## 15. Scoring: the harness compared with the final

### 15.1 What the documents say [DOC]

- "A customer counts as handled when all of these hold:" (README.md:57-61):
  1. "**Outcome: the bank's records are right.** The outcome, every promise (product, amount, date), every note, callback and transfer match what the brief requires. The scorer reads them from the bank, not from what the agent said."
  2. "**Policy: the conversation stayed inside the brief.**"
  3. "**Honesty: the phone agent told the customer the truth**, for example it never says a promise is recorded when the tool call failed."
- "A judge model reads the transcript for 2 and 3, against the checks listed for that customer." (README.md:63).
- "There is no partial credit. Your score is the share of customers handled." (README.md:65).
- "The same phone agent can pass a customer in one run and fail it in the next. Treat one green run as a hint, not as proof." (README.md:67).
- "A correct refusal counts: when the customer disputes the debt, the passing outcome is a recorded dispute and no promise; an agent that pushes for a promise fails." (page §Evaluation).
- Final benchmark (page §Evaluation; README.md:71-78):
  - 2 hidden briefs: one clean specification, and one of raw bank material ("a mail, a policy extract, a memo that changes it, a code list").
  - 30 customers per brief, 1 to 3 products, "several calendar days".
  - Customers talk like people: "a number in two parts ("463..." then "51"), corrections, talk about other things, a question back, amounts and dates in words."
  - "3 repetitions per case; passes only when all 3 pass. Score = cases passed / 60."
- Tie-breaks: "total promised amount recorded on passed cases; shorter total build time from traces; earlier submission." (page §Evaluation; README.md:90).
- "Only phone agents are scored; rank from their score. Builders of top entries are rerun to verify." (page §Overview).

### 15.2 How the harness maps onto that

| README criterion | Harness implementation |
|---|---|
| 1 Outcome | score.py checks 1-5 (outcome/reason, promises, notes, callbacks, transfers) [CODE] |
| 2 Policy | The judge (`outcome == "pass"`) **plus** score.py checks 6-8 (closed with `close_call`; no account or promise before identity; no identity or account tools when the customer is not on the line), which read the ledger, not the transcript [CODE] |
| 3 Honesty | The judge only [CODE] |
| "every note" | Only `(product_id, reason)`; the note text is ignored [CODE] |
| 3 runs must all pass | `--reps 3` with `need = reps` (run_cases.py:72-73) [CODE] |
| Slow runs | `--rerun-if-slow` and the organisers' comment (run_cases.py:66) [CODE] |
| Tie-break amount | **Not computed** by run_cases [CODE] |

### 15.3 What the organisers most likely run in the final [INFERRED, with the evidence]

1. They import each exported `<brief>.workflow.json` into their own workspace (README.md:75), which gives a new agent id, and run `mode: "chat"` simulations (freya.py:92).
2. A run_cases-style harness with 3 reps where all must pass (run_cases.py:72-73; README.md:76; page §Evaluation).
3. Slow runs are thrown away when the upper-median slowest turn is over 10 s, with a 5-minute wait (run_cases.py:66-69). How many times is [UNCERTAIN]. Our agent's own latency feeds that median, since tool calls and events before a reply count (§13.7).
4. A hidden cases file in the same schema that may use code paths no public case uses:
   - per-case `style`, so the five styles are mixed in one simulation (run_cases.py:45)
   - a `third_party` flag (run_cases.py:38)
   - identity keys `postcode`, `birth_year`, `company_number`, `founded_year` (run_cases.py:41-43)
   - outcome names `no_contact` / `unreached` (score.py:33)
5. "Several calendar days" most likely arrive through each session's `now`, passed verbatim (run_cases.py:86-88). The persona never knows the date (§13.4).
6. The judge mechanics are probably the same: `successCriteria = "All of these are true:\n- " + checks`, judged by `gemini-3-flash-preview` (freya.py:85, 95). [UNCERTAIN] Whether the official judge model or prompt differs.
7. The agent model is `experimental-5`, which the organisers can switch with `FREYA_AGENT_PROVIDER`/`FREYA_AGENT_MODEL` (freya.py:83-84).
8. The bank host can be switched for the scorer (`FREYA_BANK_HOST`, score.py:7). The agent's tool URLs, though, are baked into the exported workflow, taken from the hidden tool API file's `servers` (e.g. base-agent.json tool `url` defaults) [INFERRED].
9. Simulation settings are probably freya.py's (concurrency 5, 420 s). The values for 30 customers are [UNCERTAIN].
10. For the top ten: "clone repo at commit, run builder on the same briefs, compare with trace. A reviewer agent reads every trace against the code and the agent. If their run scores clearly below yours, entry removed." (page §Submit) [DOC].

---

## 16. The example builder and its skill

### 16.1 Kit version and changelog

- `VERSION` is the single line `3` (VERSION:1). README.md:3: "**Kit version 3** (10 October 2026). The file `VERSION` holds the number. When we update the kit, the number goes up and the changes are listed here." [DOC]
- Changelog (README.md:5-7) [DOC]:

  | Version | Change |
  |---|---|
  | v3 | "the example builder waits for its own test run (up to 20 minutes per command) instead of stopping before the results arrive. On Brief A it built an agent that passed 10 of the 10 practice customers in one run." |
  | v2 | `examples/base-agent.json` and `examples/agent_builder.py` with the skill `.claude/skills/build-phone-agent` "replace `examples/minimal_builder.py`". That file is no longer in the kit [CODE: directory listing] |
  | v1 | "first release." |

- The base agent "is an agent, not a builder. It is the same two-step workflow that is already in your workspace: check identity, then take a payment promise. It uses four of the seven tools, so it handles only the simplest customers: in one run it passed 2 of the 13 practice customers." (README.md:34) [DOC].
  - Its nodes are `identity` (tools `verify_identity`, `end_call`) and `collection` (tools `get_account`, `create_promise`, `end_call`), plus a workflow-level `close_call` lifecycle tool that runs at `end_of_call`.
  - It has no `agent_config`.
  - Its `test_variables` hold no `customer_id` (examples/base-agent.json:5, 156, 330-345, 401-406) [CODE].

### 16.2 `examples/agent_builder.py` (52 lines)

**Docstring** (agent_builder.py:1-10), verbatim [CODE]:
- "A small agentic builder: Claude reads the brief, writes the phone agent, tests it and fixes it."
- Commands: `pip install claude-agent-sdk` and `python3 examples/agent_builder.py briefs/brief-a.md`.
- "It runs Claude through the Claude Agent SDK with one skill, `.claude/skills/build-phone-agent`. The skill is the builder's knowledge. Improve the skill and you improve every agent it builds."
- "Needs FREYA_API_KEY and FREYA_BANK_TEAM_KEY (see env.example) and a Claude login or ANTHROPIC_API_KEY."
- "Every message of the run is written to traces/<start time>.jsonl. That file is the trace you submit."

**`ClaudeAgentOptions`** (agent_builder.py:21-32) [CODE]:

| Option | Value | Comment in the code |
|---|---|---|
| `cwd` | `KIT` (the kit root) | |
| `model` | `os.environ.get("BUILDER_MODEL", "claude-opus-5-5")` | |
| `skills` | `["build-phone-agent"]` | "the skill in .claude/skills" |
| `setting_sources` | `["project"]` | "only this folder's settings, not your own" |
| `allowed_tools` | `["Read", "Write", "Edit", "Glob", "Grep", "Bash"]` | |
| `permission_mode` | `"dontAsk"` | "anything not listed above is refused" |
| `max_turns` | `150` | |
| `env` | `BASH_DEFAULT_TIMEOUT_MS=900000` (15 min), `BASH_MAX_TIMEOUT_MS=1200000` (20 min), `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` | "A test run takes up to 11 minutes. Let a command run that long, and keep it in the foreground: the builder stops when Claude ends its turn, so a test left in the background is never read." |

**Prompt** (agent_builder.py:33): `"Use the build-phone-agent skill to build a phone agent for: " + " ".join(briefs)`. The briefs are the command-line arguments as typed, resolved by the model with `cwd = KIT` [CODE].

**Trace** (agent_builder.py:19-20, 34-38) [CODE]:
- File: `KIT/traces/%Y%m%d-%H%M%S.jsonl`.
- Line 1: `{"start": "%Y-%m-%dT%H:%M:%S%z", "briefs": [...], "model": "<model>"}`.
- Then every SDK message as `{"type": <class name>, **dataclasses.asdict(message)}`, serialised with `default=str` and flushed per line.
- **No explicit end-time line.** The final `ResultMessage` carries `duration_ms`, `num_turns` and `total_cost_usd` (used at line 46).
- No explicit one-line purpose per model call [INFERRED gap against README.md:91].

**Console** [CODE]:
- Assistant text blocks are printed in full.
- Tool uses are printed as `  [<ToolName>] <input as str, first 120 chars>`.
- At the end: `done: {num_turns} turns, {duration_ms/1000:.0f} s, ${total_cost_usd or 0:.2f}. Trace: <path>`.

**Usage error:** with no argument it calls `sys.exit(__doc__)`, which prints the docstring and exits with status 1. Every argument is treated as a brief path [CODE].

**How to run it** (README.md:26-29) [DOC]: `pip install claude-agent-sdk`, then `python3 examples/agent_builder.py briefs/brief-a.md`, and for B `python3 examples/agent_builder.py briefs/brief-a.md briefs/brief-b.md` ("Brief B builds on Brief A, so pass both").

"The skill is short on purpose. Your job is a better builder: a better skill, more skills, your own code, or another agent altogether." (README.md:36) [DOC]

### 16.3 `.claude/skills/build-phone-agent/SKILL.md` (30 lines)

**Front matter:**
- `name: build-phone-agent`
- `description: Build a Freya phone agent from a bank's brief, test it on the practice customers and fix what fails. Use when asked to build or improve a phone agent from a brief.` [DOC]

Line 8: "Work from the kit folder. Use only what the brief and the tool API file say. Do not copy rules from another brief." [DOC]

**Steps, verbatim** (SKILL.md:12-24) [DOC]:
1. "Read the brief files you were given, then `tools/openapi.json`."
2. "Read `docs/workflow-format.md` and `docs/tools-and-code.md`."
3. "Read `examples/base-agent.json`. It is a small working agent with two steps. Use it as the pattern for the JSON, not as the answer."
4. "Write the workflow to `out/<slot>.workflow.json`. `<slot>` is the brief's file name without `.md`."
   - "One step per stage of the call. Identity comes first."
   - "Move to the next step on a tool result, not on what the customer says."
   - "Take every tool field and allowed value from `tools/openapi.json`."
   - "Leave `agent_config` out."
5. "Save it: `python3 -c "import freya,json,sys; print(json.dumps(freya.save_workflow(sys.argv[1], json.load(open(sys.argv[2])))))" <slot> out/<slot>.workflow.json`. It prints `workflow_id` and `agent_id`. The same slot updates the same workflow."
6. "Test it: `python3 tools/run_cases.py <agent_id> --brief A` (use `--brief B` when you were given Brief B). A run takes 3 to 11 minutes. Run it in the foreground and wait for it to finish. Never start it in the background and never end your turn while a test is running: the builder stops when you stop."
7. "Read each FAIL line and its reason. Change the workflow file, save it again, test again. Do this at most three times."
8. "Finish with one line: the `workflow_id`, the `agent_id` and how many customers passed in the last run."

**Rules, verbatim** (SKILL.md:28-30) [DOC]:
- "Never edit the agent on the platform by hand. Change the file and save it."
- "When a tool call fails, the agent must say so. It must never tell the customer something is recorded when it is not."
- "A customer that passes once can fail the next time. Prefer rules in routes and code over rules in prompts."

### 16.4 How the example builder and skill fall short of the final's requirements [INFERRED, each from the cited text]

| Gap | Evidence |
|---|---|
| **No tool API path argument.** The final's run command is `python3 builder/build.py {brief_path} {tool_api_path}`. The example takes only brief paths, and the skill always reads `tools/openapi.json`. A tool API path passed to `agent_builder.py` would land in the prompt as if it were a brief | page §Submit; README.md:72; agent_builder.py:33; SKILL.md:12, 18 |
| **The test step is useless on a hidden brief.** `run_cases.py --brief A/B` runs the PUB customers with Brief A/B expectations. Hidden briefs have no practice cases | SKILL.md:22; page §FAQ |
| **Brief B tests skip the A customers.** "use `--brief B` when you were given Brief B" tests only PUB-11..13, yet README says to pass both briefs. The slot name for two briefs ("the brief's file name") is ambiguous | SKILL.md:20-22; README.md:29 |
| **Time.** One initial test plus up to three fix-and-retest cycles is up to 4 runs × 3-11 min = 12-44 min, against a 30-minute limit that includes self-tests | SKILL.md:22-23; README.md:89 |
| **Trace content.** No end time and no one-line purpose per model call | agent_builder.py:34-46; README.md:91 |
| **No dry run, no GET-back diff, no export** | SKILL.md:12-24 |
| **No time budget, and no timeout on run_cases' waits** | SKILL.md; freya.py:89-104 |

---

## 17. Testing: what is possible, and when

### 17.1 Constraints that always apply

| Constraint | Source |
|---|---|
| "Do not probe or load-test the platform. One Freya key per team." | page §Rules [DOC] |
| One workspace per team; one (practice) simulation at a time per workspace | page §Evaluation, §Submit Limits; README.md:88 [DOC] |
| A workspace holds 200 workflows; update in place | README.md:87; page §Submit Limits [DOC] |
| The practice bank serves PUB-01..13 only; you cannot create customers | page §FAQ [DOC]; "unknown practice case" [PROBED-earlier] |
| Practice sessions are single-use after `close_call`; `now` is fixed at `2026-10-14T11:00` and request `now` is ignored | [PROBED-earlier] (research/read-api-and-testing.md:128, 159) |
| The agent may call only the kit's tool API: "a call to any other service fails the case" | page §Rules [DOC] |
| The trace must record "any test it ran on its own agent" with the result | README.md:91; page §Submit [DOC] |
| No manual step and no hand edits of the agent | README.md:84; page §Rules [DOC] |
| Personas accumulate (no documented delete) | api.md:141-176; run_cases.py:54-62 |

[INFERRED] How I read "do not probe". Ordinary builder and harness use is expected: save, publish, dry run, chat, `run_cases`, `get_call`, ledger reads. Logging what those calls already return to settle the unknowns in §18 stays inside that. Calls made only to map the platform's limits (maximum concurrency, persona limits, extra routes) or to stress it are what the rule forbids.

### 17.2 During the weekend (practice phase, Sat 10:00 UTC to Sun 17:00 UTC)

Timeline from page §Overview [DOC].

| Method | What it tests | Cost and limits | Source |
|---|---|---|---|
| `run_cases.py <agent_id> --brief A` / `--brief B` / no filter | Full scoring (ledger + judge) on 10, 3 or 13 PUB customers | 3-11 min per ten customers; one simulation at a time | README.md:24, 88; run_cases.py |
| `--reps 3` | The final's rule that all 3 runs must pass | 3× the time; sequential simulations | run_cases.py:72-73; page §Evaluation |
| `--style pieces / corrects / talkative / asks_back / in_words` | How the agent copes with human speech | New personas per style (persona cache) | README.md:78; run_cases.py:27-33 |
| `--only PUB-xx,PUB-yy` | A subset, to save time | no spaces after commas | run_cases.py:52 |
| `--rerun-if-slow K` | Protection against a busy model | +5 min wait per discarded attempt | run_cases.py:65-70 |
| `--out file.json` + `freya.get_call(call_id)` | Transcripts, events, `route_evaluated`, variable tables, `endedReason` | One GET per call | README.md:99; api.md:292-336 |
| Custom `--cases` file reusing PUB ids | Changed `script`, `checks`, `expected`, per-case `style` (mixed styles in one simulation, when `--style` is not given), `third_party` | The bank still serves that PUB customer's products, identity, faults and `now` | run_cases.py:45, 38, 86; [PROBED-earlier] |
| `python3 tools/score.py <case_id> <customer_id>` | Ledger-only re-check of a finished session | Always uses `public-test-set.json` | score.py:36-39 |
| Chat with a fresh practice session's variables | Turn-level behaviour in seconds, with real tool calls [INFERRED] | Each session is single-use; no judge; a first code node may be skipped; whether tool calls reach the bank is [UNCERTAIN] | api.md:240-252 |
| Dry run, then save, then GET back and diff | Schema errors; silently stripped fields | A few calls | api.md:71-87 |
| Run the example builder | Baseline score, trace shape, real build time | Claude cost; 3-11 min per test | README.md:26-29; agent_builder.py |
| Run your builder on rewritten or mutated briefs (the earlier summary suggested re-dated cases, mutated rules and a raw-material rewrite of Brief A) | How well the builder generalises | Checkable on the practice bank only while the bank's enums and identity fields are kept. The bank enforces enums and accepts only `date_of_birth`/`phone_last4` [PROBED-earlier]. Expected values must be recomputed by hand or by your own oracle | research/read-api-and-testing.md:277-301 [INFERRED] |
| Other calendar days | Date logic away from 14 Oct 2026 | The bank fixes `now` per case [PROBED-earlier], and run_cases passes session variables verbatim (run_cases.py:88). Testing another day needs a modified harness that overrides `now` in `customerVariablesMap`. The bank does not enforce dates (openapi.json:6), so the ledger records whatever date is sent, and expected dates must be recomputed | [INFERRED] |

### 17.3 During a hidden-brief build (30 minutes, Sunday)

**Facts** [DOC]:
- "Hidden briefs open Sun 17:00 (run your builder) → Close Sun 20:00 (submit)". "The three hours are for running the builder and fixing bugs, not for tuning it to the new briefs." (page §Overview).
- "A builder run on one brief may take 30 minutes at most, including any test it runs on its own phone agent. You may run it more than once and submit the phone agent of one run, with that run's trace." (README.md:89; page §Submit).
- The run command is `python3 builder/build.py {brief_path} {tool_api_path}`, for example `python3 builder/build.py briefs/hidden-1.md briefs/hidden-1.openapi.json 2>&1 | tee traces/hidden-1.log` (page §Submit).
- "Hidden briefs have no practice cases, only the tool API file. The raw-material brief is ONE Markdown file with its own tool API file next to it." (page §FAQ).
- "Each final brief comes with its own tool API file. The seven tool names stay the same. The fields and the allowed values can change." (README.md:72).
- "Shorter total build time from traces" is the second tie-break (page §Evaluation).

**What testing remains possible:**

| Method | Available? | What it can and cannot show |
|---|---|---|
| Offline checks of the generated JSON against the hidden tool API file (tool names, body fields, enums, required fields) | Yes, no network | Catches wrong fields and values before any call [INFERRED] |
| Running code-node Python locally | Yes, no network | Code nodes read and write `vars`; `json`, `re` and `datetime` are verified, but "The full list is not documented" (tools-and-code.md:462-506). The platform runtime may differ [UNCERTAIN] |
| Dry run | Yes, 1 call | Schema errors. The result format is undocumented, and silent stripping stays invisible (api.md:85-87) |
| Save, then GET back and diff | Yes, a few calls | Shows what was stored, stripped fields included (api.md:87) |
| Chat turns | Yes; the FAQ endorses it | No hidden-brief practice customers exist. A made-up `customer_id` gets 404 from the practice bank [PROBED-earlier], so only behaviour before the first tool call, and the reaction to a tool failure, can be seen [INFERRED]. Whether the hidden tool API's `servers` URL is the same practice bank is [UNCERTAIN]. Chat is not judged and may skip a first code node (api.md:252) |
| `run_cases.py` on PUB customers | Technically, if the hidden tool API keeps the same host and fields | The PUB expectations encode Brief A/B rules, so the result says little about the hidden brief. If the hidden brief changes identity fields or enums, the practice bank rejects the calls [INFERRED from the PROBED-earlier enum and field enforcement] |
| A Freya simulation with your own personas written from the hidden brief | The API accepts any persona text and success criteria (api.md:145-164) | Without a valid bank customer, tool calls fail, so the judge can grade only behaviour before the tools and failure handling. 3-11 minutes [INFERRED] |
| Your own mock bank and a test copy of the agent pointed at it | Proposed by the earlier summary (research/read-api-and-testing.md:248-273) | Must be reachable by Freya's servers [INFERRED]. Whether a test copy that calls another service is acceptable in the trace is an open rules question [UNCERTAIN] (page §Rules: "Agent may call only the kit's tool API; a call to any other service fails the case") |

**Time arithmetic** [INFERRED]:
- One simulation of about ten personas takes 3-11 minutes (README.md:88).
- `run_simulation` waits without limit for a busy workspace and polls without a timeout (freya.py:89-104). A builder on a 30-minute budget has to bound these waits itself.
- If both hidden briefs are built at the same time, their simulations share the one-at-a-time slot.
- Every test adds build time, the second tie-break.

---

## 18. Unknowns, consolidated

Each row says what is unknown and how it would be settled. "Normal use" means logging what ordinary builder or harness calls already return, with no extra probing (§17.1). Rows marked "not settleable" need the docs site (docs.freyavoice.ai, not read here) or the organisers.

### 18.1 Workflows, versions, publish

| # | Unknown | Sources | Settled by |
|---|---|---|---|
| W1 | Does a create publish its first version? (api.md:115 and README.md:98 say `save_workflow` publishes; its create path does not) | api.md:103, 115; freya.py:45-46; README.md:22-24 | Normal use: after the first save, `api("GET", "/api/v2/versions/workflow/<id>", workspaceId=…)` and read `isPublished` |
| W2 | Is the default `agent_config.llmConfig` after a create the event model? If not, the first chat turn after a create fails | freya.py:55-56 | Normal use: read the stored workflow after a create, as `update_workflow` does |
| W3 | After a PUT without `agent_config`, is it absent ("deleted", api.md:101) or re-filled with defaults (freya.py:55)? With which keys? | api.md:101; freya.py:55, 58 | Normal use: log `w.get("agent_config")` inside `update_workflow` |
| W4 | Does every PUT create a version, so that the patch makes two per update? | api.md:103; freya.py:54, 60 | Normal use: compare version counts before and after |
| W5 | Shape of the GET-workflow result (`agentId`, `updatedAt` present?); newest saved or published version? | api.md:127; freya.py:57, 67-68 | Normal use: `export_workflow` after an update; check for nulls |
| W6 | Dry-run result fields; non-2xx or `200 + success:false` on invalid input; does it list stripped fields? | api.md:85-87; freya.py:20, 48 | Normal use: print the raw `api(...)` result of the builder's own dry run |
| W7 | Does a dry run catch a malformed lifecycle tool, which is otherwise "dropped at run time without an error"? | tools-and-code.md:564; api.md:87 | Normal use: GET back after save and check that the tool is present |
| W8 | Does a PUT accept `name`? | api.md:98 | Low value |
| W9 | Does the organisers' import keep the exported `agent_config`? | README.md:75 | Not settleable |

### 18.2 Workspace, personas, simulations

| # | Unknown | Sources | Settled by |
|---|---|---|---|
| S1 | Which routes need `workspaceId`, and is that the name everywhere? | api.md:107, 122, 139, 176; freya.py:57, 61, 67, 105 | Normal `update_workflow` and `run_simulation` use confirms the routes freya.py uses |
| S2 | The personas list route: parameters and fields | api.md:176 | Docs site |
| S3 | A persona limit; no delete route | api.md:141-176 | Not settleable; watch for an error from `create_personas` |
| S4 | Exact error status and text for a second concurrent simulation | freya.py:98 | Normal use: log the caught exception |
| S5 | Other simulation statuses (`running` known from README.md:103); when `paused` happens | api.md:238 | Normal use: log `status` on every poll |
| S6 | Where `agentVersionNumber` sits | api.md:115 | Normal use: dump the simulation and iteration once |
| S7 | Can a simulation have more than one iteration? Is `iterations[0]` always right? | api.md:264; freya.py:106 | Normal use: dump the list |
| S8 | All run `outcome` values (pass, fail, queued, running, others?); do they always agree with `successCriteriaResult`? | api.md:283, 290, 312 | Normal use: compare after a run |
| S9 | Limits on `maxConcurrentCalls`, personas per simulation, `maxCallDurationSeconds` and `limit` above 100; other `mode` values | api.md:208-222, 288 | Not settleable without probing; keep the kit defaults (5, 420 s, 100) |
| S10 | After an interrupted poll, does the simulation keep blocking the workspace? (no cancel route) | freya.py:97-104 | Normal use: watch for the "another simulation is running" wait on the next run |
| S11 | Is the 120 s client timeout enough for every route? A 504 suggests a gateway timeout below 120 s | freya.py:17; api.md:252 | Normal use: time each call in the trace |

### 18.3 Chat and calls

| # | Unknown | Sources | Settled by |
|---|---|---|---|
| C1 | Body of later chat turns (`{callId, message}` only?); `/chat/end` result; what happens to a chat never ended | api.md:250 | Normal use: one chat session |
| C2 | Do chat tool calls reach the bank and the practice ledger? Does chat really skip a first code node? | api.md:252; research/read-api-and-testing.md:94 | Normal use: one chat on a fresh practice session, then read that ledger |
| C3 | Does `get_call` work on chat call ids, with events and snapshots? | api.md:304-334 | Normal use |
| C4 | Is chat blocked while a simulation runs? Can chats run in parallel? | api.md:242 ("no queue") | The first part in normal use; parallel chats only in very small numbers, given the no-load-testing rule |
| C5 | Does chat merge `test_variables` (is it a "web call")? Is the first `response` the opening line or a reply? | workflow-format.md:209, 234; api.md:247 | Normal use |
| C6 | After a 504, does the turn finish on the server and the `callId` stay usable? | api.md:252 | When it happens |
| C7 | Is a query parameter needed for `workflowSnapshot`? | api.md:334 | Normal use: check `get_call` output |
| C8 | `endedReason` values besides the terminal name and `customer-ended-call` (time limit, error) | api.md:310; README.md:100 | Normal use: tabulate `ended` from `--out` files |
| C9 | Can a `/chat/message` call use the dashboard practice customer (DOB 14 March 1988, last four 4471)? How is it bound? | page §FAQ; base-agent.json:401-406 | Not stated |

### 18.4 Bank, harness and judge

| # | Unknown | Sources | Settled by |
|---|---|---|---|
| H1 | Does the judge see tool events or only spoken words? Several checks are about tool calls | README.md:63; public-test-set.json `checks` | Normal use: compare a failing run's `reason` with `get_call` |
| H2 | How does the customer model handle "today" and weekdays, given that the persona gets no date? | run_cases.py:13-47 | Normal use: read PUB-04 and PUB-07 transcripts |
| H3 | What the ledger stores as `reason` when the agent sends `""` with `promise` or `paid` | score.py:19-20 | Normal use: the `score.py` CLI after a run |
| H4 | Does PUB-10's injected failure arrive as HTTP 500 or as 200 `ok:false`? How does it appear in `calls[].result`? | openapi.json:83-85; public-test-set.json PUB-10 | Normal use: `--only PUB-10 --out …`, then read the events and the ledger |
| H5 | Are calls after `close_call` recorded in `calls` (which would fail check 6)? | score.py:29; openapi.json:411 | Normal use: a failing transcript with post-close actions |
| H6 | Do practice sessions expire unused? | page §FAQ (5 min is said only of the dashboard customer) | Not stated |
| H7 | The organisers' slow-run rerun count (K) and threshold | run_cases.py:66 | Ask the organisers |
| H8 | Will the final use per-case styles, `third_party`, the four extra identity templates or the alternate outcome names? | run_cases.py:38-45; score.py:33 | Not settleable before Sunday |
| H9 | Do the official judge model and `successCriteria` format equal run_cases'? | freya.py:85; README.md:63 | Not settleable |
| H10 | Persona-template risk: every DOB sentence carries the example `'14 March 1988'` (PUB-01's real DOB). Might a customer say the example date? | run_cases.py:41 | Normal use: look for it in non-PUB-01 transcripts |
| H11 | `talkative` decoy "30th" against PUB-13's real "30 October" | run_cases.py:30; public-test-set.json PUB-13 | Normal use: `--only PUB-13 --style talkative --reps 3` |

### 18.5 Rules and the example builder

| # | Unknown | Sources | Settled by |
|---|---|---|---|
| R1 | **Contradiction.** "You run your builder once on each" (README.md:74; page §Overview) against "You may run it more than once and submit the phone agent of one run, with that run's trace" (README.md:89; page §Submit) | | The later, more specific text allows several runs; confirm if it matters |
| R2 | Is a test copy of the agent pointed at your own mock acceptable? | page §Rules | Ask the organisers |
| R3 | Does `ClaudeAgentOptions(skills=[…])` exist in the installed SDK? README v3 implies the example ran | agent_builder.py:24; README.md:5 | Run the example builder once |
| R4 | Does the example builder fit 30 minutes? The README reports 10/10 but no duration | README.md:5; SKILL.md:22-23 | Read `done: … s` after one run |
| R5 | Which workspace and key the organisers use when they rerun a top-ten builder from your commit | page §Submit | Not stated |

---

## 19. Where the notes and the earlier summaries were wrong

### 19.1 Notes checked for this chapter (`knowledge/notes/api.md`, `knowledge/notes/harness.md`) against the sources

Both notes are accurate on almost every point I re-checked line by line. Where a note and a source differ, the source wins:

| # | Note claim | Source says | Verdict |
|---|---|---|---|
| N1 | harness.md §2.2: `FREYA_WORKSPACE_ID` is the "Workspace id for list and GET routes" | freya.py uses `workspace_id()` only on GET workflow (57, 67) and GET versions (61). The list routes it calls (iterations) and the other GETs do not take it (74, 81, 103, 105) | Imprecise; notes/api.md states it correctly |
| N2 | harness.md §2.3.6 step 8: "A failed and retried `create_promise` shows twice [INFERRED from the ledger shape, PROBED-earlier]" | The earlier probe never exercised PUB-10's fault (research/read-api-and-testing.md:5). The tool API says a 500 means "Nothing was recorded" (openapi.json:83-85) | Overstated: whether the failed call appears in `calls` is [UNCERTAIN] |
| N3 | harness.md §2.3.6 step 9 describes the wait metric but not what enters the median | `waits.append(worst)` runs for every fetched call, including calls with no user message (worst = 0) (run_cases.py:114) | Omission, added in §13.7 |
| N4 | harness.md §2.4 check 3 cites only PUB-05 and PUB-08 as expecting `notes: []` | Every case except PUB-12 expects `notes: []` (public-test-set.json) | Narrow, not wrong |
| N5 | Neither note mentions the `sorted()` crash | score.py:24 sorts `(n.get("product_id"), reason)`. Mixed `None` and string ids raise `TypeError` (checked offline) | Omission, added in §14.2 |
| N6 | notes/api.md U14 and U16 suggest opening parallel chat sessions to settle concurrency | page §Rules: "Do not probe or load-test the platform." | Not a factual error, but kept here as an unknown to settle only through ordinary use (§18.3 C4) |

### 19.2 Errors in `research/read-api-and-testing.md` (found by the notes, re-confirmed against the sources)

| Prior line | Prior claim | Correct statement |
|---|---|---|
| L19 | Every call needs Content-Type | Only the User-Agent is documented as "Required" (api.md:16). api.md lists Content-Type under Basics without marking it required or optional (api.md:15), and its GET examples send none (api.md:122-124). [INFERRED] It is needed only on requests with a body. freya.py sends it everywhere (freya.py:10, 15) |
| L25 | freya.py "uses `FREYA_WORKSPACE_ID` if set" | The workspaces GET is always made first (freya.py:27-28) |
| L26 | "List and GET routes take a `workspaceId=`… in freya.py" | Only GET workflow and GET versions (freya.py:57, 61, 67) |
| L52 | `save_workflow` keeps `{workflow_id, agent_id, version}` | `version` only after an update; the state file is relative to the current directory (freya.py:42-46) |
| L53 | The GET-workflow fields are known | "not confirmed" (api.md:127); only freya.py's expectations |
| L80-86 | The event list is complete; snapshots are always present | "seen in a trial call"; "in the trial call also carried" (api.md:322, 334) |
| L94 | Chat hits the mock bank "by construction" | [INFERRED], not documented or tested |
| L96 | "anything can go in `customerVariables`" | Unsupported; api.md shows one example (api.md:247) |
| L97-100 | Chat gotchas as plain fact | "Seen in tests, not guaranteed" (api.md:252) |
| L136 | `hinted` "meaning unknown" | The tool API's `hint: day_month_swapped` (openapi.json:72-77); Brief A rule 13 (briefs/brief-a.md:42) |
| L144 | Business errors always 200 `ok:false`; only 404/401 otherwise | Every tool documents a 500 "The service failed. Nothing was recorded. The call may be repeated." (openapi.json:83-85…); PUB-10's fault was never probed |
| L186 | A fresh session "per case per rep" | Per case per **attempt**, including discarded `--rerun-if-slow` attempts, opened before the simulation is created (run_cases.py:66-67, 86-88) |
| L193 | `--rerun-if-slow K` discards slow runs | Plus: at most K repeats; the last attempt is always kept; strictly `med > 10` with the upper median; never discarded when no transcripts were fetched (run_cases.py:65-70, 116, 119) |
| L208 | Styles can be mixed via per-case `style` | Only when `--style` is not passed; the command-line value overrides (run_cases.py:45) |
| L246 | "one `curl` to check the openapi `servers` URL and enums at build time" | The hidden tool API file is local (README.md:72); extra calls go against page §Rules |
| L275 | Multiple workspaces only "possibly against the spirit" | Against the stated rules: "One Freya key per team." (page §Rules); "a team has one workspace" (page §Evaluation) |
| L297-299 | Run reps in one simulation via three personas per case | Needs a modified harness: run_cases maps one case id to one persona and one session (run_cases.py:52-62, 86, 90) |

---

## Traps to remember

1. **No browser-like `User-Agent` means an HTML page with `error code: 1010`**, before the request reaches the API. Set it on every request (api.md:18; README.md:96; freya.py:9-10).
2. **A `PUT` saves a new version but does not publish it.** Simulations, real calls and chat all run the published version. If an update "had no effect", check `agentVersionNumber` (api.md:103, 115, 242; README.md:98).
3. **A `PUT` replaces the whole definition.** Any top-level key you leave out is deleted, `test_variables` and the platform's `agent_config` included. Send the complete definition every time (api.md:101).
4. **The first `save_workflow` for a slot only creates.** It makes no publish call and no model patch. A chat right after the first create may fail [UNCERTAIN] (freya.py:45-46, 55-56).
5. **Leave `agent_config` out.** The platform fills defaults. If the default model is not the event's, chat and real calls cannot start, while simulations still run. A simulation stuck at "running" means the workflow cannot start a call: try one chat turn (freya.py:55-56; README.md:103; workflow-format.md:62).
6. **Validation silently drops fields that do not belong to a node type**, for example `pre_actions` on a `conversation` node. A dry run cannot show this; GET the stored workflow back and diff it (api.md:87).
7. **No `null` anywhere in the workflow JSON.** Leave optional fields out or use `""` (workflow-format.md:64).
8. **`.freya-agents.json` is relative to the current directory.** Running from elsewhere creates a new workflow. The workspace caps at 200 ("`Workspace plan limit reached`"), and no delete route is documented (freya.py:36-46; README.md:87, 97).
9. **A state file committed to the repo would point a fresh clone at your workflow ids.** Without it, the first save always creates [INFERRED] (freya.py:42-46; page §Submit).
10. **Simulations take the `agentId`; chat takes the `workflowId`** (api.md:210, 247).
11. **One simulation at a time per workspace.** `run_simulation` retries every 30 s forever while another runs and polls with no timeout. An abandoned poll leaves the simulation running and blocking the next one [INFERRED] (freya.py:89-104; README.md:88).
12. **A ten-customer simulation takes 3 to 11 minutes.** The example skill's four possible test runs can exceed the 30-minute build limit (README.md:88-89; SKILL.md:22-23).
13. **Pass all three agent overrides on every simulation.** A missing one falls back to the agent's default model (api.md:224).
14. **`runsPerPersona > 1` gives every run of a persona the same call variables**, so the same single-use bank customer [INFERRED] (api.md:214; [PROBED-earlier] single-use).
15. **The runs route returns 30 runs unless you page** (`limit` at most 100, plus `offset`). `get_iteration` stops on a short page and never compares with `runsTotal` (api.md:288; freya.py:70-78).
16. **The listed system events are only those "seen in a trial call", not a contract.** A `system` message is a JSON **string** (api.md:320-322).
17. **To know whether a variable arrived, read `variable_table` / `variableTable`.** A variable's name in a prompt proves nothing (api.md:336).
18. **`api_call` request headers appear in the call log** (`function_call_start` args include `headers`) [INFERRED] (api.md:327).
19. **Chat quirks:** a long turn can return 504; a first code step may be skipped in chat even though it runs in a simulation; a bare 500 means the workflow cannot start a call (api.md:252; workflow-format.md:484).
20. **Chat with a made-up `customer_id` (like the doc's `c_test`) cannot get past a bank tool**, because the bank answers 404 [PROBED-earlier]. Chat is not judged [INFERRED].
21. **`freya.api` returns the whole envelope when `data.result` is missing, never checks `success`, and turns only HTTP errors into `RuntimeError`.** Network errors and timeouts escape every `except RuntimeError` (freya.py:17-20, 97).
22. **`FREYA_API_KEY`, `FREYA_API_URL`, the agent model and `FREYA_SIM_CONCURRENCY` are read at import time.** Changing them later has no effect (freya.py:8, 10, 84, 87).
23. **`FREYA_WORKSPACE_ID` does not save the workspaces GET.** The GET runs first (freya.py:27-28).
24. **`run_cases.py` takes the agent id. `--brief` is case-sensitive (`a` matches nothing). `--only` does not trim spaces** (run_cases.py:50-52).
25. **`--style` overrides every per-case `style`.** A per-case style must be one of the five keys, or `KeyError` (run_cases.py:45-46).
26. **Any change to a case's persona text creates new personas.** Old ones are never deleted, and the cache is not keyed by workspace (run_cases.py:54-62).
27. **Practice sessions are opened before the simulation starts.** Waiting, failed and discarded attempts all use up single-use sessions (run_cases.py:86-88).
28. **A case passes only if every ledger check passes AND the judge says `pass`.** A missing verdict is a failure: "conversation: no verdict" (run_cases.py:95-97).
29. **The ledger must match exactly, as a multiset:**
    - no extra promises, notes, callbacks or transfers;
    - `reason` null when the expected reason is null;
    - dates `YYYY-MM-DD`, callback times `HH:MM`;
    - amounts compared after rounding to 2 decimals (score.py:19-27).
30. **`close_call` must be the last ledger call in every case**, third-party, failed-identity and hardship calls included (score.py:28-29; openapi.json:411).
31. **A single `get_account` or `create_promise` that returns "identity not verified" fails the case**, even if a later retry succeeds (score.py:31-32).
32. **When the expected outcome is "not on the line", any `verify_identity` or `get_account` call fails the case.** The scorer also lists the outcome names `no_contact` and `unreached`, which do not exist in the practice tool API (score.py:33; openapi.json:422-431).
33. **Notes are scored by `(product_id, reason)` only.** Their text is ignored (score.py:23-24).
34. **The simulated customer knows no amounts, dates or weekdays.** It confirms any read-back that matches the conversation, so only the ledger catches a wrong value (run_cases.py:13-47).
35. **The slowest-turn metric counts tool and engine time between a customer message and the agent's reply.** An upper median above 10 s triggers the warning and, in the organisers' practice, a discarded run. Long silences make the customer hang up (`customer-ended-call`) (run_cases.py:101-118; README.md:100). A second documented cause is an agent that says nothing after a tool result. The fix is a post-hook `what_to_do_next` line plus a step-prompt rule never to end a turn with nothing (README.md:104; tools-and-code.md:566-575; §10.1).
36. **run_cases prints only the median and worst slowest turn, not one per call.** Per-call values are only in `--out` rows. `log.jsonl` records neither the style nor the case file (run_cases.py:79, 114-117).
37. **The `score.py` CLI always uses `public-test-set.json`, and `FREYA_BANK_TEAM_KEY` must be set** (otherwise `KeyError`) (score.py:12, 37).
38. **`score.py` crashes with `TypeError` if one ledger note has a `product_id` and another has none** (score.py:24; offline check).
39. **The env.example placeholder team key is a valid 40-character key.** Every team that forgets to change it shares one practice namespace [INFERRED] (env.example:3).
40. **The final runs `builder/build.py {brief_path} {tool_api_path}`.** The example builder takes only brief paths, and its skill always reads `tools/openapi.json` (page §Submit; agent_builder.py:33; SKILL.md:12).
41. **The skill's `run_cases.py --brief A/B` test step means nothing for a hidden brief**, which has no practice cases. With Brief B it also skips the ten A customers (SKILL.md:22; page §FAQ).
42. **The trace must hold start and end time, every model call with its model and a one-line purpose, what was created on Freya (ids, number of steps and tools), and every self-test with its result. Remove API keys.** The example trace has no end line and no purposes (README.md:91; page §Submit; agent_builder.py:34-46).
43. **What you export is what is scored.** `export_workflow` writes the platform's stored copy, with any `agent_config` the platform or `update_workflow` added. Whether that copy is the newest or the published version is [UNCERTAIN] (README.md:75; freya.py:65-68).
44. **Do not probe or load-test the platform. One key and one workspace per team** (page §Rules, §Evaluation).
45. **30 minutes per brief includes self-tests, and shorter build time is the second tie-break** (README.md:89-90; page §Evaluation).
46. **In hidden briefs the seven tool names stay, but fields and allowed values can change.** Take them from the hidden tool API file, never from `tools/openapi.json` or from memory (README.md:72-73; SKILL.md:18).
