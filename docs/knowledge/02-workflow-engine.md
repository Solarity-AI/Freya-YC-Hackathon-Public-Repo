# 02 · The Freya workflow engine

What this chapter covers: the whole Freya workflow model. That means the execution model, every top-level key, the node types and node fields, how prompts, entry lines and history behave, variables and `{{var}}` substitution, transitions with every operator, condition shape and trap, passthrough nodes, global nodes, extraction, end-call nodes, limits, the design rules, the complete example from the docs, and `examples/base-agent.json` annotated line by line.

How it was made: the notes `knowledge/notes/wf-1.md`, `wf-2.md` and `base-agent.md` were re-checked against the primary sources. Where a note and a source disagree, the source wins, and §0.4 lists every such case. No network call of any kind was made while writing this chapter.

---

## In short

1. A workflow is a graph of **nodes**. Each node is one step with its own prompt. **Transitions** move the call between nodes on what the user said or on a variable's value (WF:9).
2. Each user message triggers up to **three separate model calls**: extraction (fills variables), routing (picks a transition), then dialogue (writes the reply or a tool call). They do not share a prompt. Routing never sees `task_message`, so any routing rule written in a prompt has no effect (WF:15-36).
3. Only the dialogue model calls tools, and only the tools of the current node. The engine runs everything else: `pre_actions` on entry, code nodes, end-call terminals and lifecycle tools (WF:35; TC:147-151).
4. All variables live in one table for the whole call. They are never cleared. A placeholder that is not resolved behaves differently by location: in a prompt it shows as literal text, in a fixed spoken line it is read aloud, and in an engine-run request field it is either dropped or sent as literal text (WF:178, WF:201-202).
5. Routing order is fixed: `loop_condition`, then the node's transitions in list order (deterministic checks run in code first), then global nodes, then "stay". There is no fallback. Routing also runs again right after a tool result, in the same turn (WF:395-412).
6. `equals` compares strings. A boolean can arrive as `"true"` or `"True"`, so test both spellings or route on string flags. The top-level condition group must be `"logic": "or"`, with AND nested inside it (WF:331, WF:347, WF:372-389).
7. Passthrough nodes (`api_request`, `code`) route without waiting for the user and must end with an `always` transition, or they deadlock. An `end_call` node hangs up, and its terminal `function.name` becomes the call's `endedReason` (WF:464-468, WF:652).
8. Several documented behaviours contradict each other or are unverified. Examples: list order against "deterministic first", whether a self-transition counts as re-entry, `routing_prompt` replacing or adding, and lifecycle parameters being dropped or model-filled. They are listed in §19, each with a safe design choice.
9. `base-agent.json` is a two-node, four-bank-tool agent. In one run it passed 2 of 13 practice cases (RM:34). It shows a valid shape, but it carries undocumented keys and `null` values, it has no end-call nodes, and its tool set and outcome enum are incomplete (§18).

---

## 0. Reading guide

### 0.1 Citation keys

All paths are under ``.

| Key | File |
|---|---|
| WF | `kit/build-the-builder/docs/workflow-format.md` (859 lines) |
| TC | `kit/build-the-builder/docs/tools-and-code.md` (587 lines) |
| API | `kit/build-the-builder/docs/api.md` (349 lines) |
| RM | `kit/build-the-builder/README.md` |
| FP | `kit/build-the-builder/freya.py` |
| BA | `kit/build-the-builder/examples/base-agent.json` (407 lines) |
| SK | `kit/build-the-builder/.claude/skills/build-phone-agent/SKILL.md` |
| OAS | `kit/build-the-builder/tools/openapi.json` |
| PTS | `kit/build-the-builder/public-test-set.json` |
| RC / SC | `kit/build-the-builder/tools/run_cases.py` / `tools/score.py` |
| BRA | `kit/build-the-builder/briefs/brief-a.md` |
| HP | `research/hackathon-page.md`, the official page text, cited as §Section:line |
| RAT | `research/read-api-and-testing.md`. Used **only** for facts it marks `[PROBED]`; those are relabelled [PROBED-earlier] here |

### 0.2 Labels

| Label | Meaning |
|---|---|
| [DOC] | Stated in a kit doc, the README, a brief or the hackathon page |
| [CODE] | Read from kit code or kit JSON (including local, offline checks of the JSON) |
| [PROBED-earlier] | From the few live calls made earlier against the mock bank (RAT). They were not repeated |
| [INFERRED] | My reasoning from the cited facts |
| [UNCERTAIN] | Unknown. The text states exactly what is unknown |

### 0.3 Evidence grades inside the docs

The docs mark how well each statement is supported. Keep the distinction in mind.

| Phrase in the docs | What it means | Source |
|---|---|---|
| "Verified in a working builder" | Comes from "a builder that created a 6-node workflow through the REST API and whose agent passed its practice cases" | [DOC] WF:5; TC:5 |
| "Seen in a trial call" | Comes from "the event log of a simulation call made with that builder". Observed once, not guaranteed | [DOC] TC:5 |
| "Seen in tests, not guaranteed" | Observed, explicitly not guaranteed | [DOC] API:252 |
| "Warning from a test on 10 October" | A late-found failure | [DOC] WF:246 |
| "The internal reference also shows ..." | Comes from platform reference material, not verified by the working builder | [DOC] WF:368; TC:407 |

- [INFERRED] The "working builder" is not named. It is probably not the kit's `examples/agent_builder.py`: TC:284 mentions "A smaller example builder" separately, and BA has only 2 nodes. RM:5 says the v3 example builder "built an agent that passed 10 of the 10 practice customers in one run" on Brief A.

### 0.4 Where the notes disagree with the sources (the source wins)

The three notes were checked claim by claim against WF, TC, API, BA and the other kit files. They are accurate apart from these points.

| # | Note and claim | Source says | Correction |
|---|---|---|---|
| 1 | wf-1 §15 labels "There is no `greater_or_equal`, `less_or_equal`, regex or `in` operator" as **[DOC]** | WF lists eight deterministic operators and one semantic operator (WF:294-309). It never says that others do not exist | The absence is **[INFERRED]** from the operator tables, not stated. Treat the listed operators as the only known ones |
| 2 | wf-2 N5 cites the self-transition sentence as WF:421 | The sentence "A last transition with `always` that targets the node itself keeps the user in the node until an earlier transition matches." is at WF:420 | Citation fixed to WF:420 |
| 3 | wf-2 N8 attributes the quote "so that a failed or empty response does not deadlock" to TC:209 and TC:315 | TC:209 says: "The last `always` transition is mandatory. A passthrough node with no matching transition deadlocks." The quoted words are only at TC:315 | Both lines support the rule, but the quote is TC:315 |
| 4 | wf-2 N11 says each terminal parameter is "set as a JSON-schema property with a `default`" as if the docs state it | WF:639-646 is a plain parameter table. The property-with-`default` form is shown only in the examples (WF:628-633, WF:823, WF:839-843) | The rule is **[INFERRED]** from the examples, not stated in the table |
| 5 | base-agent §2.4 supports the meaning of node `interruptible` with `research/read-tools-and-code.md:99` | That file is an earlier summary, not a source of truth | The citation is dropped. The meaning of node-level `interruptible` stays **[UNCERTAIN]** (§18.4, §18.12) |

Points the notes raise that are correct but easy to miss are kept and labelled in the body: the contradictions on `routing_prompt` and `loop_prompt`, the conflict between list order and "deterministic first", the `null` values in BA, and the chat route skipping a first code step.

---

## 1. What a workflow is

- [DOC] "A workflow describes a conversation as a graph. Each **node** is one step of the conversation and has its own prompt. **Transitions** move the conversation from one node to the next. A transition fires on what the user said or on the value of a variable." (WF:9)
- [DOC] "When you create a workflow through the API, the platform creates an agent for it. You run simulations against that agent." (WF:11). [CODE] `freya.create_workflow` returns `{workflow_id, agent_id}` (FP:31-34).
- [DOC] In the hackathon's words, a phone agent is "a Freya workflow (steps, prompts, tools)". "Each step has its own prompt and tools; conditional routes decide which step takes the conversation next; calculations such as business days can run as code instead of being left to the model. How many steps/routes/tools is the design problem." (HP §Overview:10, :15)
- [DOC] RM:12: "A step of a phone agent is called a node in the platform's documents."

---

## 2. Execution model

### 2.1 Three model calls per user message

[DOC] "After each user message the platform makes three separate model calls. They do not share a prompt." (WF:15)

```text
user message
    |
    v
1. EXTRACTION   reads the message, stores variables
2. ROUTING      decides whether to leave the node
3. DIALOGUE     writes the agent's reply
```

| Call | What it sees (WF:28-30) [DOC] | What it produces [DOC] |
|---|---|---|
| Extraction | "Recent conversation messages and the current node's `extraction_schema`" | Variable values |
| Routing | "Recent conversation messages and the transition descriptions. It does not see the dialogue prompt" | "The transition to take, or none" |
| Dialogue | "`system_prompt`, `role_message`, `task_message`, the full conversation history, and the node's `tools`" | "The reply, or a tool call" |

Consequences stated in the docs [DOC] (WF:34-36):

- "A routing instruction inside `task_message` has no effect on routing. Routing reads only transitions."
- "The dialogue model can call only the tools in the current node's `tools` array. Everything else (API calls on entry, code, ending the call) is run by the workflow engine."
- "Deterministic conditions (variable checks) need no model call. They are evaluated in code."

Additions and refinements from elsewhere:

- [DOC] Routing also reads `routing_prompt` (WF:97, WF:416) and `loop_condition` (WF:430). `matches_intent` is judged on "the user's **last** message" (WF:309), although the routing call sees "recent conversation messages" (WF:29).
- [DOC] If a deterministic transition matches, "no routing model call is made" (WF:407). [INFERRED] So "three model calls" is the general case. The routing call can be skipped, and a `tts` entry line makes "No model call" (WF:160).
- [DOC] With `is_tool_call: true` on a transition, "The dialogue model then sees the transition as a tool named `transition_to_<node>`" (WF:449). [INFERRED] So the dialogue model's tool list is the node's `tools` **plus** any injected transition tools.
- [DOC] "Full conversation history" is limited by `truncation_strategy`. "Truncation applies to the dialogue model only. Extraction and routing run before it." (WF:111, WF:664, WF:671)
- [INFERRED] How many messages "recent" means is not stated. The built-in extraction template uses `{{extractor.conversation.last-10}}` (WF:576), which suggests 10 for extraction. [UNCERTAIN] The routing window is unknown.

### 2.2 Which model runs each call

- [DOC] A simulation sets each call's model separately: `assistantLlmOverride` (dialogue), `routingLlmOverride` and `extractionLlmOverride`. "Pass all three agent overrides ... on every simulation. An override you leave out falls back to the agent's default model." (API:218-224). The reference values are `{"provider": "experimental-5", "model": "experimental-5"}` (API:200-202).
- [CODE] `freya.run_simulation` passes `AGENT_LLM` for all three and `gemini-3-flash-preview` for the persona and the analysis (judge) (FP:84-85, FP:94-95).
- [DOC] "The phone agent runs on the model set in `freya.py` (`AGENT_LLM`). Do not change it." (RM:85; HP §Submit:34)

### 2.3 Who fires what: engine or model

| Action | Who fires it | When | Source |
|---|---|---|---|
| Tool in a conversation node's `tools` | Dialogue model | During a turn, when it decides to | [DOC] TC:150, WF:35 |
| `pre_actions` (`api_request` / `code` node) | Engine | On node entry, "before any model turn" | [DOC] TC:149 |
| Workflow-level tool with `config.alwaysRunsAt` | Engine | `start_of_call`: "During call setup, before the first turn". `end_of_call`: "After the call has ended". `each_turn`: "never fires" | [DOC] TC:151, TC:516-522 |
| `terminal` of an `end_call` node | Engine | When the node is reached | [DOC] WF:613, WF:35 |
| Transition with `is_tool_call: true` | Dialogue model, as a tool call | When it decides to | [DOC] WF:449 |
| Deterministic conditions | Engine, in code | Each routing evaluation | [DOC] WF:36 |

### 2.4 One turn end to end [INFERRED composite, built from the cited [DOC] pieces]

**Call start**
1. Lifecycle tools with `start_of_call` run during setup (TC:520).
2. The engine enters `initial_node` (WF:52).
3. On entry to any node:
   - tool `default` placeholders are baked against the variable table (TC:93);
   - `pre_actions` run if it is an `api_request` or `code` node (TC:149);
   - the `on_enter` behaviour runs (WF:159-162);
   - a passthrough node then routes at once, without waiting for the user (WF:464).

**Each user message**
1. Extraction fills the current node's schema variables (WF:21, WF:530).
2. Routing runs in this order: `loop_condition`, then transitions (deterministic first, then one model call for all `matches_intent` checks), then global nodes, then stay (WF:395-411).
3. If a transition fires:
   - messages are kept and the system message is replaced by the target node's prompts (WF:170-172);
   - the target node is entered as above;
   - passthrough targets chain on.
4. Dialogue runs in the current node. The model sees `system_prompt`, `role_message`, `## Current Task`, `task_message` (or `loop_prompt`), the history and the node's tools (WF:30, WF:119-126).
5. If the dialogue model calls a tool:
   - the engine runs it (pre-hook, request, post-hook, mapping, automatic keys, counters; TC:248-345);
   - "Routing also runs after a tool result arrives" (WF:410). A transition on a result variable "fires in the same turn, before any further model turn" (TC:291);
   - if nothing fires, the model "has to produce the next turn itself" (TC:568).

**Call end**
1. The call ends in one of these ways: an `end_call` node's terminal, an `end_call` handler used as a tool (BA only, undocumented), the customer hanging up, or the call-length limit.
2. "the order is: call analysis, then `end_of_call` tools, then success-criteria judging" (TC:563).

[UNCERTAIN] Three timing points are not documented:
- After a transition into a conversation node, is the agent's reply the target's `on_enter` output, a dialogue turn, or both?
- What does a `silent` conversation target say?
- What happens on a re-entry when `on_enter_first_entry_only` is true?

WF:460 states only that, for a tool-call transition, "The target node's `on_enter` then asks the next question". See §19 Q10-Q12.

---

## 3. Top-level keys

[DOC] The example from WF:40-48:

```json
{
  "initial_node": "greeting",
  "system_prompt": "You are the assistant of a dental clinic. Speak English.",
  "nodes": {},
  "global_nodes": {},
  "test_variables": { "customer_id": "c_test" }
}
```

| Key | Type | Required | Meaning [DOC] | Notes |
|---|---|---|---|---|
| `initial_node` | string | yes | "Key of the node where every call starts" (WF:52) | It is the node **key** in `nodes` |
| `nodes` | object | yes | "Map of node key to node definition" (WF:53) | |
| `system_prompt` | string | no | "Global rules. Part of the dialogue prompt in every node" (WF:54) | Dialogue only. Extraction and routing never see it (WF:28-30) [INFERRED from DOC] |
| `global_nodes` | object | no | "Interrupt handlers that can fire from any node" (WF:55) | §12 |
| `test_variables` | object | no | "Default values for call variables" (WF:56) | §9.6 |
| `context_variables` | object | no | "A state block of chosen variables for the dialogue model" (WF:57) | **Unreliable**: dropped on save in a test (WF:246). §9.8 |
| `tools` | array | no | "Workflow-level lifecycle tools" (WF:58) | Without `alwaysRunsAt` such a tool "never runs and the model never sees it" (TC:559) |
| `agent_config` | object | no | "Model and call settings" (WF:59) | See below |
| `nodePositions` | object | no | "Layout for the visual editor. The working builder omits it" (WF:60) | WF gives no rule to omit it. Omitting it is sensible [INFERRED] |

**`agent_config`.**
- [DOC] WF:62 says: "omit it. The platform fills in defaults. It holds model, voice and timeout settings that a builder for this event does not need. In a simulation you choose the models with the override fields described in api.md."
- [DOC] RM:103 agrees: "Leave `agent_config` out of the workflow you send." SK:19 says the same: "Leave `agent_config` out."
- [CODE] However, `freya.update_workflow` reads the stored workflow back. If `agent_config.llmConfig` is not `AGENT_LLM`, it sets it and saves again. The code comment explains: "If its model is not the event's model, a simulation still runs (it overrides the model), but a chat turn or a real call cannot start." (FP:55-60)
- [CODE] `create_workflow` does **not** apply this patch (FP:31-34). Only the update path does, which `save_workflow` uses on the second and later saves (FP:43-46).
- [DOC] "The body replaces the whole definition. A top-level key that your new definition leaves out is deleted, including `test_variables` and an `agent_config` that the platform filled in. Send the complete definition every time." (API:101)

**No `null`.**
- [DOC] "The schema is strict. Leave an optional field out, or set an optional string to `""`. A `null` fails validation." (WF:64)
- [INFERRED] The `""` alternative is stated for optional **strings** only. For other types, leave the field out.
- [CODE] BA contains four `null` values (BA:145, BA:151, BA:320, BA:326), yet RM:23 posts BA unchanged. See §18.12 and §19 Q27.

**Request body.**
- [DOC] "The REST API takes the workflow inside a request body `{"name": "...", "workflow": {...}}`. The object described on this page is the value of `workflow`." (WF:66)
- [DOC] The update call sends `{"workflow": {...}}` without a name (API:98).

**Saving, publishing, exporting** [DOC/CODE]:
- A dry run, `POST /api/v2/workflow?dryRun=true`, "runs its write validation and stores nothing". The fields of its result are not documented (API:73-85). [CODE] `freya.validate_workflow` (FP:48).
- "Validation checks the schema. It also removes fields that do not belong to a node type without reporting them ... Read a created workflow back if you are unsure what was stored." (API:87)
- "An update saves a new version and does NOT publish it. Simulations and calls run the published version." (API:103). [CODE] `save_workflow` creates once, then updates and publishes (FP:36-64).
- "We load them into our own workspace to test them, so what you export is what we score." (RM:75). [CODE] `export_workflow` writes `{workflow_id, agent_id, updated_at, workflow}` (FP:65-68).
- "A workspace holds 200 workflows." Update in place (RM:87; HP §Submit:34).

---

## 4. Node types

| `node_type` | Purpose | Speaks to the user | Carries | Source |
|---|---|---|---|---|
| `conversation` | A dialogue step | yes | `task_message`, `tools`, `extraction_schema`, `transitions` | [DOC] WF:72 |
| `api_request` | Runs an HTTP call on entry | usually not | `pre_actions`, node-level `response_mapping`, `transitions` | [DOC] WF:73 |
| `code` | Runs a Python snippet on entry | usually not | `pre_actions` with a `code_exec` function, `transitions` | [DOC] WF:74 |
| `end_call` | Ends the call | optional farewell | `terminal` | [DOC] WF:75 |

- [DOC] "Other node types exist: `transfer_call`, `integration`, `knowledge_base`, `reschedule_call`, `invoke_agent`, `exit`. Telephony, voice settings, knowledge base and integrations also exist on the platform. You do not need any of them here and this page does not describe them." (WF:77)
- [DOC] **Silent stripping.** "The platform strips fields that do not belong to a node type, without an error" (WF:79):
  - "`tools` is kept only on `conversation` nodes." (WF:81)
  - "`pre_actions` is kept only on `api_request` and `code` nodes (and the other non-conversation action types)." (WF:82)
  - "So a node cannot have both. If a call must run before a conversation node, put it in its own `api_request` node in front." (WF:84)
  - TC:153 adds: "the JSON you sent looks fine, the create call succeeds, and the stored node has an empty array."
- [DOC] "`api_request` and `code` nodes are normally passthrough nodes." (WF:464)
- [INFERRED] "Usually not" speaks means a non-conversation node can still speak through `on_enter`. The global-node example is a passthrough node with a `tts` line (WF:509-510).

---

## 5. Node fields: full reference

WF has no "Required" column for node fields. A blank default means WF gives none.

| Field | Type | Default | Meaning (quoted gist) | Applies to | Notes and cross-references |
|---|---|---|---|---|---|
| `name` | string | | "Node name. Use the same value as the node's key, in `snake_case`" (WF:90) | all | Transitions target the **key** (WF:285) |
| `node_type` | string | | One of the types above (WF:91) | all | §4 |
| `task_message` | string | | "The instruction for the dialogue model in this node" (WF:92) | conversation | §6 |
| `role_message` | string | | "Extra persona text for this node. Rarely needed" (WF:93) | conversation | §6 |
| `on_enter` | object | `{"type": "llm"}` | What happens on entry (WF:94) | all | §7 |
| `on_enter_first_entry_only` | boolean | `false` | "Run the entry behaviour only on the first visit" (WF:95) | all | §7 |
| `transitions` | array | | "Outgoing transitions, in priority order" (WF:96) | all except end_call (`[]`) | §10 |
| `routing_prompt` | string | | "Extra context for the routing model in this node" (WF:97) | nodes with model routing | **Contradicted** by WF:416, "replaces". §10.6 |
| `loop_condition` | string | | "Intent description for staying in the node" (WF:98) | conversation | §10.8 |
| `loop_prompt` | string | | "Replaces `task_message` from the second turn in the node" (WF:99) | conversation | When it applies is contested. §10.8 |
| `extraction_schema` | array | | "Variables to extract from user speech in this node" (WF:100) | conversation | §13 |
| `tools` | array | | "Tools the dialogue model may call. `conversation` nodes only" (WF:101) | conversation | Stripped elsewhere (WF:81) |
| `pre_actions` | array | | "Calls the engine runs on entry. `api_request` and `code` nodes" (WF:102) | api_request, code | Stripped elsewhere (WF:82) |
| `response_mapping` | array | | "For `pre_actions` nodes: maps the call result to variables. Node level" (WF:103) | api_request, code | For `tools`, the mapping sits on the tool (TC:243) |
| `passthrough` | boolean | `false` | "Route right after entry, without waiting for the user" (WF:104) | mainly api_request, code | §11 |
| `passthrough_default_transition` | string | | "Target node for a passthrough node" (WF:105) | passthrough nodes | Also needs a final `always` (WF:467) |
| `max_node_turns` | integer | `10` | "Cap on user turns spent in the node" (WF:106) | all | Does nothing without a `max_turn_transition` (WF:663). §15 |
| `max_turn_transition` | string | | "Target node when the cap is reached" (WF:107) | all | §15 |
| `terminal` | object | | "The end-call function. `end_call` nodes only" (WF:108) | end_call | §14 |
| `disable_inactivity_monitor` | boolean | `false` | "Switch off silence check-ins for this node" (WF:109) | all | `true` on end-call nodes (WF:651) |
| `suppress_tool_results` | boolean | `false` | "Hide raw call results from the dialogue model" (WF:110) | nodes running calls | The model then sees "only a short `{status: "success"}` summary". "Variables are still mapped and routing still sees them" (TC:341) |
| `truncation_strategy` | string | `keep_all` | "How much history the dialogue model sees" (WF:111) | conversation | `keep_all`, `keep_recent`, `summarize` (WF:664) |
| `truncation_window_size` | integer | `10` | "Number of recent messages kept by `keep_recent` and `summarize`" (WF:112) | conversation | |
| `reasoning_override` | string | `auto` | "`enabled` or `disabled` forces model reasoning on or off for this node. Only models that support such a switch react to it" (WF:113) | all | [UNCERTAIN] whether `experimental-5` reacts |

- [DOC] "A per-node `idle_config` (silence timeouts) and per-node speech settings also exist. They matter on voice calls only." (WF:115)
- [CODE] BA also carries four node keys that WF never mentions: `position`, `assertions`, `interruptible` and `return_to_previous_on_interrupt` (§18.12).

---

## 6. Prompts

### 6.1 How the dialogue system message is built

[DOC] "The dialogue model receives one system message built from three parts" (WF:119-126):

```text
system_prompt        workflow level, the same in every node
role_message         node level, optional
## Current Task
task_message         node level, what to do now
```

- [DOC] `## Current Task` is a literal heading that the engine puts between `role_message` and `task_message` (WF:124). [INFERRED] So do not start `task_message` with your own "## Current Task".
- [DOC] `loop_prompt` "replaces `task_message` in the system message from the second turn in the node. The model sees one of the two, never both." (WF:432)
- [DOC] `context_variables` would add a `pre_history` block "written once into the system prompt" and a `post_history` block "rendered again on every turn after the chat history" (WF:273-274). It is unreliable (WF:246).
- [DOC] When the call moves from node A to node B, "The system message is replaced by node B's prompts." (WF:171)

### 6.2 Prompt fields

| Field | Level | Use it for (WF:130-134) [DOC] |
|---|---|---|
| `system_prompt` | workflow | "Identity, language, tone, rules that hold in every node" |
| `role_message` | node | "A different persona for one node. Most workflows leave it out" |
| `task_message` | node | "What the agent must do in this step" |
| `loop_prompt` | node | "A replacement for `task_message` after the first turn in the node" |
| `on_enter` | node | "What the agent does when it enters the node" |

### 6.3 Rules for `task_message` [DOC] (WF:138-142)

1. "Write instructions for the model, not a script."
2. "Cover this node's job only."
3. "Do not describe routing or name other nodes. The model does not know about nodes. Text such as "then move to the lookup node" makes it narrate steps that have not happened."
4. "If the node has tools, refer to them by name and say when to call them. Do not repeat the tool descriptions."
5. "In a node without tools, state that no tool call is allowed in this turn. If the node has a `loop_prompt`, put that rule in both prompts."
   - The wording is free. The complete example writes "Do not call a tool in this turn." (WF:702).

Related tool-prompt rules from TC [DOC]:
- "In `task_message`, put the tool rules before long reference text and state: when a rule says to use a tool, call the tool." (TC:218)
- The working builder "also tells the model to call one tool per message and to speak after every tool result" (TC:219).
- "Also say it in the step's prompt: after every tool result, speak to the customer or call the next tool. Never end a turn with nothing." (TC:575)

Example (WF:146-153) [DOC]:

```json
{
  "name": "collect_details",
  "node_type": "conversation",
  "task_message": "Ask which service the caller wants and on which day. Ask one question at a time. If the caller is unsure about the day, offer to check the next free days.",
  "transitions": []
}
```

### 6.4 Which call reads which text

| Text you write | Extraction | Routing | Dialogue | Source |
|---|---|---|---|---|
| `system_prompt`, `role_message` | no | no | yes | [DOC] WF:28-30, WF:54 |
| `task_message`, `loop_prompt` | no | no ("does not see the dialogue prompt") | yes | [DOC] WF:29-30, WF:34, WF:432 |
| `extraction_schema` items (`description`, `enum_values`, ...) | yes | no | no | [DOC] WF:28 |
| Transition `description` | no | yes ("The routing model reads it") | only if `is_tool_call: true`, as a tool [INFERRED] | [DOC] WF:286, WF:449 |
| `condition.description` of `matches_intent` | no | yes | no | [DOC] WF:309 |
| `routing_prompt` | no | yes | no | [DOC] WF:97, WF:416 |
| `loop_condition` | no | yes | no | [DOC] WF:430 |
| Tool `function.description` | no | no | yes, for tools in `tools`. Ignored in `pre_actions` | [DOC] TC:50, TC:167 |
| `on_enter.text` (`tts`) | | | Spoken verbatim, "No model call" | [DOC] WF:160 |

[INFERRED] Policy text in a prompt can steer only the dialogue model. Rules about leaving a node belong in transitions, conditions or `routing_prompt`. Rules about what to capture belong in the extraction schema.

---

## 7. Entry behaviour (`on_enter`)

| `on_enter` | Behaviour [DOC] (WF:159-162) |
|---|---|
| `{"type": "llm"}` | "The model writes the first line from `task_message`. Default. An optional `prompt` key overrides the entry instruction for this node" |
| `{"type": "tts", "text": "..."}` | "A fixed line is spoken. No model call. `{{var}}` works in `text`" |
| `{"type": "silent"}` | "Nothing is said. The node waits for the user, or routes at once if it is a passthrough node" |
| `{"type": "audio", "asset_id": "..."}` | "Plays a recorded asset. Not needed here" |

- [DOC] "Set `on_enter_first_entry_only` to `true` when a node can be re-entered and must not repeat its opening line. This works better than a prompt rule such as "do not greet twice"." (WF:164)
- [DOC] An unresolved `{{var}}` in `on_enter.text` is read aloud: "In a fixed spoken line (`on_enter.text`, a terminal `spoken_message`) the agent says it aloud." (WF:201)
- [DOC] Passthrough nodes: "Set `on_enter` to `{"type": "silent"}`, or to a short fixed line that covers the wait." (WF:468)
- [DOC] End-call nodes: the farewell comes from the terminal, not from `on_enter`. Use `silent` (WF:650).
- [DOC] The complete example opens with a `tts` line containing `{{first_name}}` and sets `on_enter_first_entry_only: true` on a node that ends with a self-`always` (WF:700-701, WF:726).
- [INFERRED] A `tts` entry line is the only way to make a sentence come out exactly as written. Use it where a brief fixes the wording. BA does this for its opening line (BA:105).
- [UNCERTAIN] Three points are open:
  - What `prompt` overrides: the first-line instruction, or `task_message`?
  - What produces the reply on a re-entry when the entry behaviour is skipped?
  - Whether a `silent` **conversation** node entered mid-turn produces any reply.

  See §19 Q10-Q12.

---

## 8. History across nodes and truncation

[DOC] When the conversation moves from node A to node B (WF:170-174):

- "User and assistant messages are kept."
- "The system message is replaced by node B's prompts."
- "A loop prompt from node A is removed."
- "So node B can refer to anything said earlier. Variables also stay for the whole call."

Related facts:

- [DOC] On tool results: "A tool call and tool result pair is added to the history", for both `pre_actions` and `tools` (TC:165).
- [UNCERTAIN] WF:170 names only user and assistant messages as kept across nodes. Whether tool-call and tool-result pairs survive the move is not stated (§19 Q25).
- [DOC] Truncation (WF:664-665, WF:671):
  - `keep_all` sends the full history.
  - `keep_recent` sends the "system message plus the last `truncation_window_size` messages".
  - `summarize`: "older messages are replaced by a model-written summary".
  - The window defaults to `10`.
  - Truncation applies to the dialogue model only.
- [UNCERTAIN] Whether tool messages count toward the window, and which model writes the summary, is not stated.

---

## 9. Variables

### 9.1 One table, never cleared

[DOC] "All variables live in one table for the whole call. There is no per-node scope. A variable is never cleared on a transition. A later write with the same name overwrites it." (WF:178)

[INFERRED] trap: a value from an earlier turn or visit stays live. Example: an extracted `next_action = cancel` still holds when the caller later returns to the menu node. An `equals` fork on it can fire again at once unless something overwrites it (§19 Q24).

### 9.2 Where variables come from

| Source | How it gets in [DOC] (WF:182-187) | Notes |
|---|---|---|
| Call variables | "Passed when the call or simulation starts" | `customerVariablesMap` per persona in a simulation (API:214). `customerVariables` on a chat turn (API:247) |
| `test_variables` | "Workflow-level defaults for call variables" | Merge rule in §9.6 |
| Extraction | `extraction_schema` on a node | §13 |
| Call results | `response_mapping`, and "the automatic result keys described in tools-and-code.md" | §9.4 |
| Code | "A code node or `code_exec` tool writes into `vars`" | TC:458-460 |
| System | "Set by the platform" | §9.7 |

- [DOC] Each entry of the variable table has `value`, `confidence`, `source` and `source_node` (API:334). A code node's written keys show "source `tool_result` and source node `setup`" (TC:482).
- [DOC] "To check whether a variable arrived, read `variable_table` or `variableTable`. Finding the variable's name in a prompt or in a code body proves nothing about its value." (API:336)

### 9.3 Code and variables (enough to read workflows; full detail in the tools chapter)

[DOC] (TC:458-468, TC:494-499)
- Snippets read with `vars.get("name")`. A never-set variable is absent.
- Snippets write with `vars["name"] = value`. "Every key the snippet assigns becomes a workflow variable."
- Verified in a working builder:
  - call variables are in `vars` (the builder reads `vars.get("now")`);
  - a string written to `vars["date_facts"]` "resolves as `{{date_facts}}` in the `task_message` of later conversation nodes. Multi-line strings work";
  - `json`, `re` and `datetime` import.
- "Do not write `{{` or `}}` in the code." "Never let a snippet raise." "Write strings for routing flags." "Do arithmetic, date calculation and counting in code."

### 9.4 Automatic result variables (from TC, needed to read transitions)

[DOC] The engine flattens every `api_call` result into the table, with no mapping needed (TC:264-279). Example for a tool named `check_answer`:

| Variable | Value |
|---|---|
| `check_answer_args.<field>` | Each argument the model sent |
| `check_answer_response.status` | `success` |
| `check_answer_response.data.<path>` | Body fields, for example `data.ok` = `true` **as a string** |
| `check_answer_response.message` | `Successfully executed POST request` |
| `check_answer_response.status_code` | `200` |
| `check_answer_response.header.<Header-Name>` | One per response header |
| `check_answer_status_code` | `200` |
| `check_answer_success_count` | Number of successful calls so far |

- [DOC] "Each call of the same tool overwrites the previous `_args` and `_response` values." (TC:279)
- [DOC] The counters `<nodeId>_success_count` / `<nodeId>_failure_count` exist for a `pre_actions` node, and `<toolName>_success_count` / `<toolName>_failure_count` for a tool in `tools` with handler `api_call` (TC:323-326). "For a code node the automatic keys are named after the **node**, not after `code_exec`." (TC:490)
- [DOC] The model's arguments are stored as `<tool>_args.<field>`, "not ... under the bare field name" (TC:97, seen in a trial call).
- [PROBED-earlier] One re-verify of an already-verified field "returned no `all_verified` key at all. Routes must tolerate a missing key." (RAT:153). [UNCERTAIN] Whether the old flattened key then survives or is cleared is not documented (TC:279 covers overwriting, not missing keys).
- [PROBED-earlier] Mock-bank business errors "come back as **HTTP 200 with `ok:false`**" (RAT:144). [INFERRED] So the `api_call` `status: success` and the success counter do not mean `ok: true`. Route on `data.ok` or a mapped string.

### 9.5 `{{var}}` substitution

[DOC] "Write `{{variable_name}}` in prompts, `on_enter.text`, transition descriptions, URLs, headers and request bodies. The engine replaces it before the model or the HTTP call sees the text." (WF:191). WF also names `loop_prompt` (WF:432) and `spoken_message` (WF:642), and suggests `{{system.conversation.last-N}}` in a `routing_prompt` (WF:242).

| Form | Result [DOC] (WF:195-196) |
|---|---|
| `{{customer_name}}` | "The value as a string" |
| `{{amount:json}}` | "The value JSON-encoded. Use it inside request bodies" |

Behaviour [DOC]:
- "Date values are formatted for speech in the agent's language when they are substituted into a prompt." (WF:200). [UNCERTAIN] Which values count as dates: extracted `date` values only, or any ISO-looking string such as `now`? (§19 Q13)
- "Do not reference a variable in a mixed value unless an earlier node always sets it." (WF:203). TC:118 adds: "even to a sentinel value".

**What an unresolved or empty placeholder does, by location**

| Location | Variable never set | Variable is `""` | Source |
|---|---|---|---|
| A prompt (`system_prompt`, `task_message`, `loop_prompt`, ...) | "stays as the literal text `{{variable_name}}`. The model sees the placeholder" | not stated | [DOC] WF:201 |
| Fixed spoken line (`on_enter.text`, terminal `spoken_message`) | "the agent says it aloud" | not stated | [DOC] WF:201 |
| Engine-run call field (`pre_actions`, lifecycle tool) that is **exactly** one placeholder, `"{{x}}"` | "the whole field is dropped from the request" | "The field is sent empty" | [DOC] WF:202; TC:115 |
| Engine-run call field mixing text and a placeholder, `"Status: {{x}}"` | "the request goes out with the literal `{{x}}` in it" | not stated | [DOC] WF:202 |
| Tool in a conversation node's `tools`, `default: "{{x}}"` with `x` unset **when the node is entered** | The model fills it. It sees the parameter "named after the variable, with the property's `type`, `description` and `enum`" | not stated | [DOC] TC:85 |
| Lifecycle tool parameter still unresolved | **Contradiction.** Dropped (WF:202; TC:115) **versus** "one model call fills the parameters" (TC:561) | | §19 Q17 |
| `code` of a `code_exec` pre-action | "The literal text `{{var}}` stays in the Python source and the snippet crashes" (TC:116). But "The internal sources disagree on whether the `code` field is templated" (TC:494) | | [DOC]. Safe rule: no `{{` or `}}` in code |
| `code` of a `code_exec` **tool** | "resolves `{{var}}` when the tool is called, against the current variable table". Not verified | | [DOC] TC:512 |

- [DOC] "Baking happens when the node is entered. A `{{var}}` default is resolved against the variable table at that moment." (TC:93)
- [DOC] "Take care that a model-filled field does not share its name with a variable that is already set when the node is entered. The value would be baked and the model would never see the parameter." (TC:99)
- [UNCERTAIN] Whether placeholders in **prompts** are resolved every turn or once at node entry is not stated (§19 Q15).

### 9.6 Call variables and `test_variables`

- [DOC] "Call variables are the inputs of one call, for example a customer id or the current time. In a simulation you pass them per persona in `customerVariablesMap`." (WF:207)
- [DOC] "`test_variables` is a top-level object of default values. **On a web call to the workflow** it is merged into the call variables. A value passed with the call wins over a test variable of the same name." (WF:209). Example (WF:211-219): `customer_id` `"c_test"`, `first_name` `"Dana"`, `now` `"2026-03-11T10:00"`.
- [DOC] "Verified in a working builder: call variables are readable as `{{customer_id}}` in prompts and tool parameters, and as `vars.get("customer_id")` in code." (WF:221). This covers **call variables** only.
- [UNCERTAIN] WF states the `test_variables` merge only for "a web call". Whether it also happens in chat simulations, in `POST /api/v2/chat/message` and in the hidden benchmark is not stated. A chat simulation reported `call.direction` = `web` (WF:234), which hints at yes but proves nothing.
- [DOC] An update without `test_variables` deletes it (API:101).

**For this event:**
- [DOC] "The phone agent gets the date/time of the call as variable `now`; every date rule uses it." (HP §Overview:14). "Every case runs Wed 14 Oct 2026 11:00." (HP §Data:21)
- [DOC] The final tests run "on several calendar days, three times each" (RM:76).
- [CODE] `run_cases.py` opens one practice session per case and passes its variables as the call variables (RC:86-88).
- [PROBED-earlier] A practice session returns `variables: {customer_id: "c_<uuid-ish>", first_name, last_name, title, now}`. "Each call makes a fresh customer_id." `now` is fixed per case: `2026-10-14T11:00` for all PUB cases (RAT:126-128).
- [DOC] The chat example passes `customer_id`, `first_name`, `last_name`, `title` and `now` (API:247).
- [INFERRED] Never hard-code a date. Every date must derive from `{{now}}` or `vars.get("now")`.

### 9.7 System variables

| Variable | Example | Meaning [DOC] (WF:227-238) |
|---|---|---|
| `{{system.iso_utc_now}}` | `2026-03-11T14:30:00Z` | "UTC timestamp of call start" |
| `{{system.todays_date_en_cst}}` | `11 March 2026 Wednesday 08:30` | "English date, UTC-6" |
| `{{system.todays_date_en_est}}` | `11 March 2026 Wednesday 09:30` | "English date, UTC-5" |
| `{{system.todays_date_tr}}` | (none given) | "Turkish date with day name and time, UTC+3" |
| `{{system.todays_date_tr.iso_8601}}` | `2026-03-11` | "ISO date, UTC+3" |
| `{{system.conversation}}` | `AGENT: hello\nUSER: hi` | "Transcript so far" |
| `{{system.conversation.last-N}}` | (none given) | "Last N turns. N is `1`, `5`, `10` or `20`" |
| `{{call.direction}}` | `web` | "`inbound`, `outbound`, `web` or `simulation`. A chat simulation in the trial showed `web`" |
| `{{call.duration}}` | `42` | "Whole seconds since call start" |
| `{{call.call_id}}` | (none given) | "Platform call id" |
| `{{<node>.current_turns}}` | `2` | "User turns in the node since the last entry. Resets on every transition" |
| `{{<node>.total_turns}}` | `5` | "User turns in the node over the whole call" |

- [DOC] "There is no `{{current_date}}` placeholder. These system dates are the real clock. If your task supplies its own "now" as a call variable, use that variable." (WF:240)
- [DOC] "`{{system.conversation.last-N}}` is useful in a transition description or a `routing_prompt` when the routing model needs more than the last message." (WF:242)
- [DOC] End-of-call lifecycle tools can also use `{{call.analysis.summary}}`, `{{call.analysis.structured_data_str}}`, `{{call.call_end_reason}}`, `{{call.call_end_reason_category}}`, `{{call.call_tags}}` and `{{call.duration}}` (TC:563).
- [DOC] The `{{date.*}}` placeholders are **not** system variables. They resolve inside `extraction_prompt`, and "Do not rely on them outside extraction prompts" (WF:582).
- [INFERRED] The system dates read the real clock, while the practice cases are pinned to 14 Oct 2026 11:00. Using them would give wrong dates. Use `now`.
- [INFERRED] The examples show fixed offsets. 14:30Z appears as 08:30 (UTC-6) and 09:30 (UTC-5) on 11 March 2026, when US daylight saving time was already in force (it began on 8 March 2026). So daylight saving time is probably ignored. This is moot if the system dates are not used.
- [INFERRED] `call.direction` cannot tell a simulation from a web call.
- [UNCERTAIN] Whether `<node>` is the node key or its `name`. This is moot if they are equal, as WF:90 advises.

### 9.8 `context_variables` (do not rely on it)

- [DOC] The section opens with a warning: "Warning from a test on 10 October: a workflow saved over the API came back without this key, and the save gave no error. Do not rely on it. Write the values the model needs into the prompt with `{{variable}}` instead." (WF:246)
- [DOC] The intended purpose: "It shows chosen variables to the dialogue model as a state block, so you do not have to write variable tables into prompt text." (WF:248)

Example (WF:250-261):

```json
{
  "context_variables": {
    "pre_history_description": "Static call context",
    "post_history_description": "Live state",
    "items": [
      { "name": "customer_tier", "placement": "pre_history", "description": "Customer tier" },
      { "name": "attempt_count", "placement": "post_history" }
    ]
  }
}
```

| Field | Meaning [DOC] (WF:265-268) |
|---|---|
| `items[].name` | A variable in the table. "Must match `^[a-zA-Z_]\w*$` and be unique across both placements" |
| `items[].placement` | `pre_history` or `post_history` |
| `items[].description` | Optional label |
| `pre_history_description`, `post_history_description` | "Heading text of each section" |

Rules [DOC] (WF:272-277):
- "An item points at a variable. It does not create one. If nothing sets the variable, the row is skipped without an error."
- "`pre_history` is written once into the system prompt. Use it only for values that never change during the call."
- "`post_history` is rendered again on every turn after the chat history and is not stored in the history. Use it for values that change."
- "The block is rendered as `<CONTEXT_VARIABLES>`, one line `- name (description): value` per populated item."
- "No other keys are allowed on an item. There is no `value`, `type` or `default`."
- "It does not affect extraction or tool parameter substitution."

[INFERRED] The name pattern excludes dotted keys such as `x_response.data.ok`.

---

## 10. Transitions

### 10.1 Transition fields

"A transition is an object in a node's `transitions` array." (WF:281)

| Field | Type | Meaning [DOC] (WF:285-288) |
|---|---|---|
| `target_node` | string | "Key of the next node. May be the node itself. `__previous__` is allowed in global nodes" |
| `description` | string | "What the transition is for. The routing model reads it" |
| `condition` | object | "When the transition fires" |
| `is_tool_call` | boolean | "The dialogue model triggers the transition by calling a tool" (§10.9) |

- [DOC] The `description` of an `always` transition is free text, not a fixed word. The examples use two styles:
  - The literal word `"always"` on forward and passthrough fallbacks (WF:318, WF:479, WF:514, WF:767; TC:204, TC:334, TC:446).
  - Descriptive text on self-loops and on the enum-fork fallback: `"Keep collecting"` (WF:423, WF:726) and `"Unclear, stay"` (WF:604).
- [INFERRED] WF says `__previous__` "is allowed in global nodes". It does not say it is forbidden elsewhere. Its meaning, "returns to the node that was interrupted" (WF:499), only makes sense in a global node.
- [UNCERTAIN] Which transition fields are required is not stated.

### 10.2 Condition operators

**Deterministic** operators are evaluated in code, with no model call (WF:292):

| Operator | Needs | True when [DOC] (WF:296-303) |
|---|---|---|
| `equals` | `variable`, `operand` | `str(value) == str(operand)` |
| `not_equals` | `variable`, `operand` | "The inverse of `equals`" |
| `greater_than` | `variable`, `operand` | `float(value) > float(operand)` |
| `less_than` | `variable`, `operand` | `float(value) < float(operand)` |
| `contains` | `variable`, `operand` | "`operand` is a substring of the value, ignoring case" |
| `is_set` | `variable` | "The variable has any value" |
| `is_not_set` | `variable` | "The variable has no value" |
| `always` | nothing | Always |

The **semantic** operator "uses the routing model" (WF:305):

| Operator | Needs | True when [DOC] (WF:309) |
|---|---|---|
| `matches_intent` | `description` | "The routing model judges that the user's last message matches the description" |

- [DOC] "All `matches_intent` conditions of one evaluation are judged in a single model call." (WF:311)
- [DOC] "`greater_than` and `less_than` convert both sides to numbers, so `2` and `"2"` behave the same. Use them for counters." (WF:391)

[INFERRED] consequences of the Python-style definitions:
- `equals` is case-sensitive and whitespace-sensitive. `contains` is the only case-insensitive check.
- `str(3)` is `"3"`, but `str(3.0)` is `"3.0"`. Using `equals` on amounts is fragile; use `greater_than`/`less_than` or a string flag.
- `str(True)` in Python is `"True"`, which explains the `"True"`/`"true"` split (§10.4).
- `float()` on a non-number raises an error in Python. WF does not say what the engine does then.
- No `>=`, `<=`, regex or "in list" operator is listed. Build `>=` as an OR of `greater_than` and `equals`, or as `greater_than` x−1 for integers.

[UNCERTAIN] Edge cases WF does not settle (§19 Q18):
- Is `is_set` true for `""`?
- What does `not_equals` do on an unset variable?
- What does `greater_than` do on an unset variable or a non-number? This matters for failure counters before the first failure.

### 10.3 Condition shapes

1. **Unconditional**, bare form (WF:318) [DOC]:
   ```json
   { "target_node": "next_step", "description": "always", "condition": { "operator": "always" } }
   ```
2. **Intent**, bare form (WF:324-328) [DOC]. In this example the transition `description` and the condition `description` are **different** texts:
   ```json
   {
     "target_node": "complaint",
     "description": "The user wants to complain",
     "condition": { "operator": "matches_intent", "description": "The user is unhappy or wants to file a complaint" }
   }
   ```
3. **Variable conditions go inside a group**. "The top-level group always uses `"logic": "or"`" (WF:331) [DOC]. In the WF:334-344 example, `order_status` `equals` `"shipped"` OR `"delivered"` leads to `order_found`:
   ```json
   {
     "target_node": "order_found",
     "description": "The lookup returned an order",
     "condition": {
       "logic": "or",
       "conditions": [
         { "variable": "order_status", "operator": "equals", "operand": "shipped" },
         { "variable": "order_status", "operator": "equals", "operand": "delivered" }
       ]
     }
   }
   ```
4. **AND**: "For AND, nest a group inside the top-level OR. Never put `"logic": "and"` at the top level." (WF:347) [DOC]. In the example (WF:349-365), `customer_tier` `equals` `"gold"` AND `days_late` `greater_than` `3` leads to `priority_desk`. The operand `3` is a JSON number:
   ```json
   {
     "target_node": "priority_desk",
     "description": "Gold customer with a late order",
     "condition": {
       "logic": "or",
       "conditions": [
         {
           "logic": "and",
           "conditions": [
             { "variable": "customer_tier", "operator": "equals", "operand": "gold" },
             { "variable": "days_late", "operator": "greater_than", "operand": 3 }
           ]
         }
       ]
     }
   }
   ```
5. **Bare single variable condition**: "The working builder uses the bare form for `always` and the grouped form for every variable check. The internal reference also shows a bare single variable condition (`{"variable": ..., "operator": ..., "operand": ...}`) directly under `condition`." (WF:368) [DOC]. This form is unverified.

Further notes:
- [DOC] A group with one condition is fine. The enum fork uses one-element OR groups (WF:601-603).
- [CODE] BA's conditions carry an extra key, `"mode": "exact"` (BA:122, BA:128). WF never documents it.
- [UNCERTAIN] What happens with a top-level `and`, with deeper nesting, or with `matches_intent` inside a group is not documented. Stick to shapes 1-4 (§19 Q21-Q22).

### 10.4 Do not route on a boolean

- [DOC] "`equals` compares strings. A boolean can arrive as `"True"` or as `"true"`, depending on how it was written into the table. A mismatch fails silently: the branch never fires and nothing reports an error." (WF:372)
- [DOC] "Prefer a string value such as `verified` or `rejected`, written by your code or by the API." (WF:374)
- [DOC] "If you must test a boolean that comes from an API response, test both spellings. Verified in a working builder" (WF:375). The example (WF:377-388):

```json
{
  "target_node": "wrap_up",
  "description": "The booking call succeeded",
  "condition": {
    "logic": "or",
    "conditions": [
      { "variable": "booking_ok", "operator": "equals", "operand": "true" },
      { "variable": "booking_ok", "operator": "equals", "operand": "True" }
    ]
  }
}
```

- [DOC] "Booleans arrive as strings. The trial call showed `true` in lower case in the flattened keys." (TC:286)
- [UNCERTAIN] Which writers produce which spelling is not documented: code writing `True`, extraction with `type: boolean`, API flattening (lower case per TC:286), or `response_mapping`.

### 10.5 Order of evaluation

[DOC] "After each user message, routing runs in this order. The first match wins and routing stops." (WF:395-402)

```text
1. loop_condition of the current node    match: stay in the node, use loop_prompt
2. the node's transitions, in list order match: go to target_node
3. global nodes                          match: enter the global node
4. nothing matched                       stay in the node, wait for the next user message
```

Rules within step 2 [DOC] (WF:406-408):
- "Transitions are checked in list order. Put specific conditions first and broad ones last."
- "Deterministic conditions are evaluated first. If one matches, no routing model call is made."
- "If several transitions of a node have the same `target_node`, the engine merges them at load time into one transition. Its condition is the OR of the originals. If one of them is unconditional, the merged transition is unconditional."

**After a tool result** [DOC]:
- "Routing also runs after a tool result arrives. Verified in a working builder: a transition on a variable that a tool's `response_mapping` sets fires in the same turn, without a further user message." (WF:410)
- TC adds: "A transition on a result variable fires in the same turn, before any further model turn. Seen in a trial call." (TC:291). The flattened key works as a transition variable, verified only when tested in the same OR group as the mapped variable (TC:285).

**No fallback** [DOC]: "When nothing matches, there is no fallback. The agent stays and answers from the same `task_message`. Make sure every realistic path has a matching transition." (WF:412)

Related rules elsewhere [DOC]:
- "Put deterministic conditions before `matches_intent` conditions." (WF:681)
- A global node "is checked only after the current node's own transitions found no match." (WF:488)
- "To leave a node that carries out an action, do not re-test the user's earlier intent with `matches_intent`. The router looks at the latest user message and can route away before the tool was called. Extract a follow-up enum with a default such as `stay`, and branch with `equals`." (TC:317)
- SK:17: "Move to the next step on a tool result, not on what the customer says."
- A background tool (`config.interruptible: false`) fills its variables "one or more turns later". "Gate on the variable with `is_set`." (TC:345)

[INFERRED] traps:
- **List order against "deterministic first."** `always` is deterministic (WF:303). One reading of WF:407 lets a trailing `always`, or any later deterministic match, win before an earlier `matches_intent` is judged. WF:420 ("until an earlier transition matches") and WF:681 suggest that list order rules. The docs never show `matches_intent` and `always` in one node: the `offer` node has `matches_intent` and no `always` (WF:807-810). See §19 Q1.
- **Merge trap.** Take `[cond → X, matches_intent → Y, always → X]`. The two X transitions merge into one unconditional X, so Y may become unreachable. Never give an `always` the same target as a conditional transition.
- **Stale intent after a tool result.** Post-tool routing judges `matches_intent` against the last user message, which by then is old (TC:317).
- **Silent no-match.** Step 4 keeps the agent in the node with the same prompt. A node whose exits all depend on variables that never get set loops until the turn cap, which does nothing without a `max_turn_transition` (WF:663).

### 10.6 `routing_prompt`

- [DOC] "A node-level string. It replaces the default intent-matching instruction of the routing model for this node. Use it when the transition descriptions cannot carry the rule, for example "stay here until both the name and the date are given"." (WF:416)
- [DOC] **Contradiction:** the node-field table calls it "Extra context for the routing model in this node" (WF:97). "Replaces" and "extra context" are different behaviours.
- [DOC] `{{system.conversation.last-N}}` is suggested for it (WF:242).
- [INFERRED] It can only matter when a routing model call happens: for `matches_intent`, `loop_condition` or a global intent. A node whose transitions are all deterministic never uses it.
- [INFERRED] If it truly replaces the instruction, a custom routing prompt might have to carry its own inputs, the way `extraction_prompt` must (WF:576). This is unknown (§19 Q5).

### 10.7 Self-transition

- [DOC] "A last transition with `always` that targets the node itself keeps the user in the node until an earlier transition matches." (WF:420)
  ```json
  { "target_node": "collect_details", "description": "Keep collecting", "condition": { "operator": "always" } }
  ```
- [DOC] "Prefer this to `loop_condition` in most cases. All routing then lives in one ordered list." (WF:426). Note the qualifier "in most cases".
- [INFERRED] Step 4 already keeps the user in the node when nothing matches (WF:401), so a self-`always` must change something else:
  - **Global nodes can never fire from that node.** Step 2 always matches, so step 3 is never reached (WF:400, WF:488).
  - It may count as a transition. That would re-run `on_enter` (hence `on_enter_first_entry_only: true` in the example, WF:701), reset `current_turns` ("Resets on every transition", WF:237), drop the loop prompt (WF:172) and perhaps reset the turn cap's count.
  - It may pre-empt earlier `matches_intent` transitions (§10.5).
- [UNCERTAIN] All of these effects are unverified (§19 Q1-Q3).

### 10.8 Loop conditions and `loop_prompt`

- [DOC] "`loop_condition` is an intent description. The routing model checks it before all transitions. When it matches, the agent stays in the node." (WF:430)
- [DOC] "`loop_prompt` replaces `task_message` in the system message from the second turn in the node. The model sees one of the two, never both. Write it so that it stands alone. `{{var}}` works in it, so it can show what was already collected." (WF:432)
- [DOC] Example (WF:434-443):
  ```json
  {
    "name": "collect_contact",
    "node_type": "conversation",
    "task_message": "Ask for the caller's full name and email address.",
    "loop_condition": "The user has not yet given both a full name and an email address",
    "loop_prompt": "Name so far: {{customer_name}}. Email so far: {{email}}. Ask only for what is still missing. When both are present, read them back once.",
    "transitions": []
  }
  ```
- [DOC] "Make the loop condition specific. "The user has not finished" matches everything and the agent never leaves." (WF:445)
- [DOC] In a node without tools, the "no tool call" rule goes into both prompts (WF:142). The loop prompt from node A is removed when moving to B (WF:172).
- [DOC] **Contradiction on when `loop_prompt` applies.**
  - WF:99, WF:133 and WF:432 say "from the second turn in the node", which reads as always.
  - WF:398 says it is used when `loop_condition` matches.
  - WF:412 says that with no match the agent answers "from the same `task_message`".
- [INFERRED] Points about the example:
  - It shows the loop fields only. With `"transitions": []` it has no exit except a global node.
  - Before extraction fills them, `{{customer_name}}` and `{{email}}` would show as literal text (WF:201).
  - The extraction schema that sets them is left out.
- [INFERRED] `loop_condition` is a model judgement made before the deterministic transitions. A node that has one probably pays a routing call every turn, and a wrong "stay" blocks even an exit whose variable is set. This is one more reason for WF:426.

### 10.9 Tool-call transitions

- [DOC] "Set `is_tool_call` to `true` on a transition. The dialogue model then sees the transition as a tool named `transition_to_<node>` and triggers it by calling that tool. The router does not evaluate it after each turn." (WF:449)
- [DOC] Example (WF:452-457):
  ```json
  {
    "target_node": "confirm_booking",
    "description": "The caller accepted the offered slot",
    "is_tool_call": true,
    "condition": { "operator": "matches_intent", "description": "The caller accepted the offered slot" }
  }
  ```
- [DOC] "Use it when the agent should decide to move, for example because of something it just said or computed. The agent can acknowledge and move in the same message. The target node's `on_enter` then asks the next question. Global nodes accept the same flag." (WF:460)
- [INFERRED] The move depends on the dialogue model choosing to call the tool, so it is not deterministic. It takes no routing call.
- [INFERRED] It conflicts with the "In a node without tools, state that no tool call is allowed" rule (WF:142), because such a node still offers a `transition_to_*` tool.
- [UNCERTAIN] Several details are not documented (§19 Q45):
  - whether `<node>` is the target's key;
  - which text becomes the tool's description;
  - whether `condition` is used at all;
  - whether calling it creates `_args` or counter variables.

---

## 11. Passthrough nodes

- [DOC] "A node with `"passthrough": true` routes right after its entry actions. It does not wait for the user. `api_request` and `code` nodes are normally passthrough nodes." (WF:464)
- [DOC] Three rules (WF:466-468):
  1. "Set `passthrough_default_transition` to the next node."
  2. "End `transitions` with an `always` transition. A passthrough node with no matching transition deadlocks."
  3. "Set `on_enter` to `{"type": "silent"}`, or to a short fixed line that covers the wait."

Example (WF:470-481) [DOC]:

```json
{
  "name": "prepare",
  "node_type": "code",
  "passthrough": true,
  "passthrough_default_transition": "greeting",
  "on_enter": { "type": "silent" },
  "pre_actions": [],
  "transitions": [
    { "target_node": "greeting", "description": "always", "condition": { "operator": "always" } }
  ]
}
```

- [INFERRED] The example's `pre_actions` is empty, so it shows the shape only. A real code node puts a `code_exec` function there (TC:420-448).
- [DOC] "Verified in a working builder: a passthrough `code` node can be the `initial_node`. It runs before the agent says anything." (WF:484)
- [DOC] **Caveat on the chat route:** "when the first step is a code step the chat route may skip it, so values that step computes are empty" ("Seen in tests, not guaranteed", API:252). [INFERRED] A chat turn may therefore behave differently from a simulation on such a workflow.
- [DOC] TC repeats the rule: "The last `always` transition is mandatory" (TC:209). "On a passthrough node, end with an `always` transition so that a failed or empty response does not deadlock." (TC:315). "Treat a code node like an API node: `passthrough: true`, a `passthrough_default_transition`, and a last `always` transition." (TC:499)
- [DOC] "To run a fixed call before a tool-driven conversation, use a passthrough `api_request` node and transition from it into the conversation node. Do not build a long chain of passthrough nodes for optional actions. Put those into one conversation node with several tools." (TC:169)
- [INFERRED] "Deadlock" means that no transition matched (step 4), so the call sits in a silent node waiting for the user. A simulated customer with nothing to answer may hang up (`customer-ended-call`, RM:100).
- [UNCERTAIN] Why both `passthrough_default_transition` and a final `always` are required, and which wins if they name different targets, is not documented. Always set both to the same target (§19 Q34).

---

## 12. Global nodes

- [DOC] "A global node is an interrupt handler. It can fire from any node. It is checked only after the current node's own transitions found no match." (WF:488)
- [DOC] A global node "has the same fields as a normal node, plus" (WF:490-497):

| Field | Meaning [DOC] |
|---|---|
| `condition` | "When the global node activates. Same format as a transition condition" |
| `description` | "Purpose of the node" |
| `excluded_nodes` | "Array of node keys where it must not fire" |
| `is_tool_call` | "Offer the global node to the dialogue model as a tool, not as a per-turn check" |

- [DOC] "`__previous__` as a `target_node` or as `passthrough_default_transition` returns to the node that was interrupted." (WF:499)

Example (WF:501-518) [DOC]:

```json
{
  "global_nodes": {
    "off_topic": {
      "name": "off_topic",
      "description": "Brings the caller back to the subject",
      "condition": { "operator": "matches_intent", "description": "The user talks about something unrelated to their order" },
      "task_message": "Redirect the caller to the subject.",
      "on_enter": { "type": "tts", "text": "I can only help with your order. Let us continue." },
      "passthrough": true,
      "passthrough_default_transition": "__previous__",
      "excluded_nodes": ["goodbye"],
      "transitions": [
        { "target_node": "__previous__", "description": "always", "condition": { "operator": "always" } }
      ]
    }
  }
}
```

Rules [DOC] (WF:523-526):
- "List terminal nodes in `excluded_nodes`, or the global node can loop."
- "Exclude nodes where an interrupt would do harm, for example an identity check."
- "For a plain redirect use a passthrough node with a fixed line. It is faster and more predictable than a model reply."
- "Use global nodes for interrupts that can happen anywhere. Do not copy the same transition into every node."

[INFERRED] consequences:
- A global node is unreachable from any node whose own transitions always match: a trailing self-`always`, or a matching `loop_condition`. This sits in tension with WF:426 ("Prefer this [self-transition]") and WF:526 ("Do not copy the same transition into every node"). A design must choose per node.
- In a passthrough global node with a `tts` line, `task_message` is probably never used, because no dialogue turn happens before it routes away.
- For this event, the brief forbids mentioning the debt before identity is verified (BRA:24; HP §Overview:9). Any global interrupt that could leak account content must exclude the identity steps.

[UNCERTAIN] Open points (§19 Q36):
- Are global `matches_intent` conditions judged in the same routing call as the node's?
- Does `__previous__` re-run the interrupted node's `on_enter`? The default `llm` entry would make the model speak again.
- Are globals checked after tool results?
- What exactly is the "loop" at terminal nodes?
- Where is a global `is_tool_call` tool offered?

---

## 13. Extraction schema

### 13.1 Purpose and example

- [DOC] "`extraction_schema` is an array on a node. After each user message the extraction model fills the listed variables from the conversation." (WF:530)
- [DOC] Extraction is the first of the three calls (WF:21, WF:28).

Example (WF:532-551) [DOC]:

```json
{
  "extraction_schema": [
    {
      "name": "order_number",
      "type": "string",
      "description": "The order number the caller reads out",
      "validation_pattern": "^[0-9]{8}$",
      "max_retries": 2,
      "min_confidence": 0.8
    },
    {
      "name": "request_type",
      "type": "string",
      "enum_values": ["status", "cancel", "change_address", "other"],
      "description": "What the caller wants to do with the order",
      "min_confidence": 0.7
    }
  ]
}
```

### 13.2 Item fields

| Field | Type | Meaning [DOC] (WF:556-563) | Default |
|---|---|---|---|
| `name` | string | Variable name | |
| `type` | string | `string`, `integer`, `float`, `boolean`, `date`, `datetime`, `name`, `phone_number` | not stated |
| `description` | string | What the variable is | |
| `enum_values` | array | "Allowed values. Works on every type. The old `enum` type is deprecated and becomes `string`" | |
| `extraction_prompt` | string | "A custom extraction template" | the built-in template |
| `validation_pattern` | string | "Regular expression the value must match" | |
| `min_confidence` | number | "0.0 to 1.0. Values below it are discarded." | **`0.95`** (WF:562, WF:666) |
| `max_retries` | integer | "Retries after a failed validation, with the error given to the model" | **not stated** |

[UNCERTAIN] Several semantics are not documented:
- what the `name` and `phone_number` types do (normalisation?);
- the `datetime` format;
- the stored format of a `date`;
- how `enum_values` is written for numeric types;
- whether `validation_pattern` applies to non-string types;
- what happens after the retries run out (presumably the value is dropped).

### 13.3 How it works [DOC] (WF:567-571), in order

1. "The extraction model sees recent messages and the schema."
2. "It returns structured values."
3. "Confidence is computed from the model's token probabilities, not from a self-report."
4. "Each value is checked against `validation_pattern` and `enum_values`."
5. "On failure the model retries, up to `max_retries`."

### 13.4 Rules [DOC] (WF:575-580)

- "**Set `min_confidence` on every variable.** The default of 0.95 is strict. A discarded value leaves no trace in the transcript, so it looks the same as "nothing was extracted"." WF recommends no value. The examples use 0.8 (WF:541) and 0.7 (WF:548, WF:597, WF:704, WF:705).
- "**`extraction_prompt` replaces the whole built-in template.** It is not appended."
  - A custom prompt must contain the input placeholders itself: `{{extractor.speech}}`, `{{extractor.conversation.last-10}}`, `{{extractor.type_preamble}}` and `{{extractor.variables_list}}`.
  - "Without them the extractor never sees the user's message and returns nothing on every turn, while dialogue and routing look healthy."
- "**Declare dates as `type: "date"`.** The date types give the extractor today's date and the rules for relative dates such as "tomorrow". A date typed as `string` gets no date anchor and the model guesses the year."
- "The built-in date rules turn vague expressions such as "next week" into a concrete date. If you need vague dates rejected, a custom prompt must say so and state that this overrides the general rules." (WF:578)
- "No `null`. Omit optional fields or use `""`." (WF:579)
- "An extracted variable is available to the same node's transitions in the same turn, and to every later node." (WF:580)

### 13.5 Date placeholders (inside `extraction_prompt` only) [DOC] (WF:582)

- `{{date.today}}`, `{{time.now}}` (note `time.`, not `date.`), `{{date.day_of_week}}`
- `{{date.yesterday}}`, `{{date.tomorrow}}`, `{{date.day_after_tomorrow}}`
- `{{date.next_week}}`, `{{date.end_of_month}}`, `{{date.first_next_month}}`
- `{{date.next_mon}}` to `{{date.next_sun}}`
- `{{date.last_mon}}` to `{{date.last_sun}}`
- `{{date.fnm_mon}}` to `{{date.fnm_sun}}` ("first such weekday of next month")
- `{{date.weeks2}}`, `{{date.weeks3}}`, `{{date.weeks2_ago}}`, `{{date.weeks3_ago}}`
- "Do not rely on them outside extraction prompts."

[UNCERTAIN] Several points are undefined:
- the meaning of `next_week`, `weeks2` and `weeks3`;
- whether `next_<day>` is the next occurrence or the day in the following calendar week;
- whether "today's date" given to the extractor is the real clock (like the system dates, WF:240) or the call's `now`.

[INFERRED, event impact] Two brief rules collide with the built-in date rules:
- Brief A rule 21 says that for a vague period ("next week", "end of the month") the agent must "ask once for the exact day" (BRA:64). The built-in rules would turn "next week" into a date (WF:578).
- Rule 22 defines "next <weekday>" as "that weekday in the following calendar week" (BRA:65). Whether the built-in rules agree is unknown.
- So either a custom `extraction_prompt` (with all four `extractor.*` placeholders) is needed, or date reasoning stays out of extraction and runs in code from `now` (TC:498; HP §Overview:15).

### 13.6 Fork on an extracted enum

[DOC] "To route from one node to several paths, extract an enum and branch with `equals`. This is more reliable than several competing `matches_intent` transitions." (WF:584)

Example (WF:586-607) [DOC]:

```json
{
  "name": "menu",
  "node_type": "conversation",
  "task_message": "Tell the caller the order status in one sentence. Then ask whether they want to change the delivery address, cancel the order, or end the call.",
  "extraction_schema": [
    {
      "name": "next_action",
      "type": "string",
      "enum_values": ["change_address", "cancel", "done"],
      "description": "What the caller chose. Empty if unclear.",
      "min_confidence": 0.7
    }
  ],
  "transitions": [
    { "target_node": "change_address", "description": "Change address", "condition": { "logic": "or", "conditions": [ { "variable": "next_action", "operator": "equals", "operand": "change_address" } ] } },
    { "target_node": "cancel_order", "description": "Cancel", "condition": { "logic": "or", "conditions": [ { "variable": "next_action", "operator": "equals", "operand": "cancel" } ] } },
    { "target_node": "goodbye", "description": "Done", "condition": { "logic": "or", "conditions": [ { "variable": "next_action", "operator": "equals", "operand": "done" } ] } },
    { "target_node": "menu", "description": "Unclear, stay", "condition": { "operator": "always" } }
  ]
}
```

- [DOC] "Use extraction for user speech. For API responses use `response_mapping` (tools-and-code.md). It is deterministic and needs no model call." (WF:609)
- [DOC] TC:246: "`extraction_schema` follows the same placement rule if you use it on a call result."
- [INFERRED] **Stale-value trap.** `next_action` persists (WF:178). If the flow returns to `menu` and the next answer is unclear or below confidence, the old value still holds and the fork fires again. Overwrite routing variables before re-entry, for example from a code node. Whether `""` counts as set is unknown (§19 Q18, Q24).
- [INFERRED] A trailing `always` back to `menu` also makes global nodes unreachable from `menu` (§10.7).

---

## 14. End-call nodes

[DOC] "An `end_call` node hangs up. It has a `terminal` object and no outgoing transitions." (WF:613)

Example (WF:616-636) [DOC]:

```json
{
  "name": "goodbye",
  "node_type": "end_call",
  "on_enter": { "type": "silent" },
  "disable_inactivity_monitor": true,
  "transitions": [],
  "terminal": {
    "type": "function",
    "function": {
      "name": "closing_end",
      "handler": "__function__:end_call",
      "parameters": {
        "type": "object",
        "properties": {
          "message_mode": { "type": "string", "default": "custom" },
          "spoken_message": { "type": "string", "default": "Thank you for calling. Goodbye." }
        }
      }
    }
  }
}
```

| Parameter | Meaning [DOC] (WF:641-646) |
|---|---|
| `message_mode` | `custom`: say `spoken_message`. `llm`: "the model writes the farewell from `llm_prompt`". `none`: "hang up without a farewell" |
| `spoken_message` | "The fixed farewell for `custom`. `{{var}}` works" |
| `llm_prompt` | "The instruction for `llm`" |
| `interruptible` | "`true` opens a short window after the farewell in which the user can still speak. Default: hang up as soon as the agent stops speaking" |
| `trigger_timeout` | "Length of that window in seconds" |
| `trigger_pattern_both` | "Farewell phrases, separated by `\|`, that do not cancel the close. Anything else the user says in the window cancels the close and returns the turn to the agent" |

[INFERRED from the examples] Each parameter is written as a property of `function.parameters.properties` with its value in `default` (WF:628-633).

Rules [DOC] (WF:650-654):
- "**The farewell comes from the terminal, not from `on_enter`.** A node with an `on_enter` line and `message_mode: "none"` hangs up silently. Put the sentence in `spoken_message` and set `on_enter` to `{"type": "silent"}`."
- "Set `disable_inactivity_monitor` to `true` and `transitions` to `[]`."
- "**The call's `endedReason` is the terminal's `function.name`.** The node name does not affect it. Pick a name that describes the outcome." API:310 says the same.
- "Use several end-call nodes with different farewells and function names when outcomes differ."
- "If you set `interruptible`, also set `trigger_pattern_both`. Without a phrase list every polite reply cancels the hang-up. The window is timed on a wall clock and a chat simulation cannot measure it."

- [DOC] "Verified in a working builder: `message_mode: "none"` with a silent `on_enter` ends the call when the node is reached. The agent says its goodbye in the previous conversation node." (WF:656)
- [DOC] TC:316: "The pattern "a closing tool sets a variable, a transition on that variable leads to an `end_call` node" is verified in a working builder."
- [DOC] TC:64: `__function__:end_call` "Hangs up. Used in the `terminal` of an `end_call` node."
- [DOC/CODE] Another `endedReason` value exists: `customer-ended-call`, when "it was silent too long and the customer hung up" (RM:100). `run_cases.py` counts failed calls that ended this way (RC:114-117).

[UNCERTAIN] Several points are open (§19 Q41):
- the default of `message_mode` when it is omitted;
- the default of `trigger_timeout`;
- whether phrase matching is case-sensitive or a regex;
- whether `on_enter` text is ever spoken on an end node with `custom`.

[INFERRED, event] Because `endedReason` is the terminal's `function.name`, one end node per outcome gives a readable trace. The scorer, however, reads the bank's ledger, including a `close_call` that must be the last call (SC:19-29). It does not read `endedReason`.

---

## 15. Limits

| Limit | Default | Notes [DOC] (WF:662-667) |
|---|---|---|
| `max_node_turns` | `10` | "Cap on user turns in one node. Only user messages count. Tool results and agent messages do not. There is no "unlimited" value" |
| `max_turn_transition` | none | "Where to go when the cap is reached. Without it the engine records the overrun and continues with normal routing, so the cap changes nothing" |
| `truncation_strategy` | `keep_all` | `keep_all`: full history. `keep_recent`: "system message plus the last `truncation_window_size` messages". `summarize`: "older messages are replaced by a model-written summary" |
| `truncation_window_size` | `10` | Used by `keep_recent` and `summarize` |
| Extraction `min_confidence` | `0.95` | §13 |
| Code `timeout_ms` | `30000` | TC:354, TC:454 |

Notes [DOC] (WF:671-674):
- "Truncation applies to the dialogue model only. Extraction and routing run before it."
- "Give every node that sets `max_node_turns` a `max_turn_transition`. The working builder sets `max_node_turns` to 60 and 80 on its conversation nodes without a `max_turn_transition`. Its calls ended well below those counts, so the behaviour at the cap is not confirmed by it."
- "Size the cap from real conversations. A node that handles a whole call can need dozens of user turns."
- "The maximum call length in a simulation is set with `maxCallDurationSeconds` (api.md)."
  - [DOC] It is a "Limit for one call" (API:217). [CODE] `run_simulation` defaults to 420 seconds (FP:87, FP:93).

Other limits worth knowing [DOC/CODE]:
- Tool `timeoutMs` and `maxRetries` have defaults that are "not documented". `connect_retries` defaults to 2, with a hard cap of 5 (TC:351-363).
- RC:118 warns when the median agent turn exceeds 10 seconds. RM:100 explains that slow or silent agents get hung up on.
- A builder run may take "30 minutes at most" per brief (RM:89).

[INFERRED] Without `max_turn_transition`, every node is effectively uncapped. With it, the cap becomes a deterministic exit to a fallback outcome.

[UNCERTAIN] Several cap questions are open (§19 Q44):
- Is the count per entry (`current_turns`) or per call (`total_turns`)?
- Does it fire on the Nth or the (N+1)th user message?
- Does it pre-empt a transition that matches on the same turn?
- Does a self-transition reset it?
- Where is "the overrun" recorded?

---

## 16. Design rules

### 16.1 WF's own rules [DOC] (WF:678-684), verbatim

- "Use `snake_case` node keys that describe the step."
- "Keep dialogue in `task_message`, routing in `transitions`, data capture in `extraction_schema`."
- "Every path must reach an `end_call` node."
- "Put deterministic conditions before `matches_intent` conditions."
- "Every passthrough node ends with an `always` transition."
- "A transition back to an earlier node is supported."
- "Split a step into its own node when it has strict rules of its own or forms a clear state. Keep related optional actions together in one conversation node with several tools."

### 16.2 Kit-level guidance that shapes workflow design [DOC]

| Guidance | Source |
|---|---|
| "One step per stage of the call. Identity comes first." | SK:16 |
| "Move to the next step on a tool result, not on what the customer says." | SK:17 |
| "Take every tool field and allowed value from `tools/openapi.json`." | SK:18 |
| "When a tool call fails, the agent must say so. It must never tell the customer something is recorded when it is not." | SK:29 |
| "Prefer rules in routes and code over rules in prompts." | SK:30 |
| "The phone agent may call only the bank's tool API. Code steps and hooks inside the workflow are allowed and expected." | RM:86; HP §Rules:37 ("a call to any other service fails the case") |
| "calculations such as business days can run as code instead of being left to the model" | HP §Overview:15 |
| "The bank's API does not enforce the brief ... Keeping the rules is the agent's job." | HP §Evaluation:25; OAS:6 |
| A post-hook adding `what_to_do_next` to a result fixed both the silence after a tool call and the ignored negative results | TC:568-575 |
| "Product ids come from `get_account` (`p1`, `p2`, ...). Give them to the model in the tool result, or fill them in with code." | RM:102 |
| Final briefs: "The seven tool names stay the same. The fields and the allowed values can change." | RM:72 |

---

## 17. The complete example (clinic booking), annotated

[DOC] Purpose: "A clinic assistant. It collects a service and a day, looks up free slots, lets the model book one with a tool, and ends the call." (WF:688)

### 17.1 Full JSON (WF:691-849), verbatim

```json
{
  "initial_node": "collect",
  "system_prompt": "You are the phone assistant of a dental clinic. Speak English. Keep every turn to one or two short sentences.",
  "test_variables": { "patient_id": "p_test", "first_name": "Dana" },
  "global_nodes": {},
  "nodes": {
    "collect": {
      "name": "collect",
      "node_type": "conversation",
      "on_enter": { "type": "tts", "text": "Hello {{first_name}}, this is the clinic. Which treatment would you like to book, and on which day?" },
      "on_enter_first_entry_only": true,
      "task_message": "Find out which treatment the caller wants (checkup, cleaning or filling) and on which day. Ask one question at a time. Do not call a tool in this turn.",
      "extraction_schema": [
        { "name": "treatment", "type": "string", "enum_values": ["checkup", "cleaning", "filling"], "description": "Treatment the caller wants", "min_confidence": 0.7 },
        { "name": "wanted_day", "type": "date", "description": "Day the caller wants the appointment", "min_confidence": 0.7 }
      ],
      "max_node_turns": 12,
      "max_turn_transition": "goodbye_no_booking",
      "transitions": [
        {
          "target_node": "find_slots",
          "description": "Treatment and day are known",
          "condition": {
            "logic": "or",
            "conditions": [
              {
                "logic": "and",
                "conditions": [
                  { "variable": "treatment", "operator": "is_set" },
                  { "variable": "wanted_day", "operator": "is_set" }
                ]
              }
            ]
          }
        },
        { "target_node": "collect", "description": "Keep collecting", "condition": { "operator": "always" } }
      ]
    },
    "find_slots": {
      "name": "find_slots",
      "node_type": "api_request",
      "passthrough": true,
      "passthrough_default_transition": "offer",
      "on_enter": { "type": "silent" },
      "disable_inactivity_monitor": true,
      "pre_actions": [
        {
          "type": "function",
          "config": { "timeoutMs": 10000, "maxRetries": 2 },
          "function": {
            "name": "find_slots",
            "handler": "__function__:api_call",
            "description": "Get free slots for a day.",
            "parameters": {
              "type": "object",
              "properties": {
                "url": { "type": "string", "default": "https://api.example.com/v1/slots" },
                "method": { "type": "string", "default": "POST" },
                "headers": { "type": "object", "properties": { "Content-Type": { "type": "string", "default": "application/json" } } },
                "body": {
                  "type": "object",
                  "properties": {
                    "treatment": { "type": "string", "default": "{{treatment}}" },
                    "day": { "type": "string", "default": "{{wanted_day}}" }
                  }
                }
              }
            }
          }
        }
      ],
      "response_mapping": [
        { "path": "data.slots_text", "variable": "slots_text" }
      ],
      "transitions": [
        { "target_node": "goodbye_no_booking", "description": "The lookup failed", "condition": { "logic": "or", "conditions": [ { "variable": "find_slots_failure_count", "operator": "greater_than", "operand": 0 } ] } },
        { "target_node": "offer", "description": "always", "condition": { "operator": "always" } }
      ]
    },
    "offer": {
      "name": "offer",
      "node_type": "conversation",
      "task_message": "Free slots: {{slots_text}}\n\nOffer the earliest slot. If the caller refuses it, offer the next one. When the caller accepts a slot, read back the treatment, the day and the time and wait for a clear yes. Then CALL book_appointment. Saying that it is booked is not enough. After the tool result, tell the caller whether the booking worked and say goodbye.",
      "tools": [
        {
          "type": "function",
          "config": { "timeoutMs": 10000, "maxRetries": 0 },
          "function": {
            "name": "book_appointment",
            "handler": "__function__:api_call",
            "description": "Book one slot. CALL it only after the caller confirmed the read-back.",
            "parameters": {
              "type": "object",
              "properties": {
                "url": { "type": "string", "default": "https://api.example.com/v1/bookings" },
                "method": { "type": "string", "default": "POST" },
                "headers": { "type": "object", "properties": { "Content-Type": { "type": "string", "default": "application/json" } } },
                "body": {
                  "type": "object",
                  "properties": {
                    "patient_id": { "type": "string", "default": "{{patient_id}}" },
                    "treatment": { "type": "string", "default": "{{treatment}}" },
                    "slot_time": { "type": "string", "description": "Start time of the accepted slot, HH:MM, 24 hour", "default": "{{slot_time}}" }
                  },
                  "required": ["slot_time"]
                }
              }
            }
          },
          "response_mapping": [
            { "path": "data.booking_id", "variable": "booking_id" }
          ]
        }
      ],
      "max_node_turns": 20,
      "max_turn_transition": "goodbye_no_booking",
      "transitions": [
        { "target_node": "goodbye_booked", "description": "The booking was recorded", "condition": { "logic": "or", "conditions": [ { "variable": "booking_id", "operator": "is_set" } ] } },
        { "target_node": "goodbye_no_booking", "description": "The caller does not want any slot", "condition": { "operator": "matches_intent", "description": "The caller refused all offered slots or does not want to book" } }
      ]
    },
    "goodbye_booked": {
      "name": "goodbye_booked",
      "node_type": "end_call",
      "on_enter": { "type": "silent" },
      "disable_inactivity_monitor": true,
      "transitions": [],
      "terminal": {
        "type": "function",
        "function": {
          "name": "booked",
          "handler": "__function__:end_call",
          "parameters": { "type": "object", "properties": { "message_mode": { "type": "string", "default": "none" } } }
        }
      }
    },
    "goodbye_no_booking": {
      "name": "goodbye_no_booking",
      "node_type": "end_call",
      "on_enter": { "type": "silent" },
      "disable_inactivity_monitor": true,
      "transitions": [],
      "terminal": {
        "type": "function",
        "function": {
          "name": "no_booking",
          "handler": "__function__:end_call",
          "parameters": {
            "type": "object",
            "properties": {
              "message_mode": { "type": "string", "default": "custom" },
              "spoken_message": { "type": "string", "default": "No appointment was booked. You can call us again at any time. Goodbye." }
            }
          }
        }
      }
    }
  }
}
```

### 17.2 The docs' own feature map [DOC] (WF:852-859)

| Node | Feature |
|---|---|
| `collect` | Fixed opening line, extraction with a `date` type, AND group, self-transition, turn cap with a target |
| `find_slots` | Passthrough `api_request` node, baked parameters, node-level `response_mapping`, failure counter, `always` fallback |
| `offer` | A tool the model calls, a model-filled body field, tool-level `response_mapping`, routing on the mapped variable |
| `goodbye_booked`, `goodbye_no_booking` | Two end-call nodes with different `endedReason` values |

### 17.3 Node by node

**Top level** (WF:692-696):
- `initial_node: "collect"`.
- The `system_prompt` sets identity, language and turn length.
- `test_variables`: `patient_id` `"p_test"` and `first_name` `"Dana"`. These are defaults; a call variable of the same name wins (WF:209).
- `global_nodes: {}` is present but empty.
- There are five nodes.

**`collect`** (conversation, WF:697-728):
- `on_enter`: `tts` "Hello {{first_name}}, this is the clinic. ..." This is a fixed line with no model call (WF:160). `on_enter_first_entry_only: true` (WF:701). [INFERRED] It guards against the self-transition re-running the entry line.
- The `task_message` ends with "Do not call a tool in this turn.", as WF:142 requires for nodes without tools.
- Extraction:
  - `treatment`: `string` with an `enum_values` of 3, `min_confidence 0.7`.
  - `wanted_day`: `type: "date"`, `min_confidence 0.7`. Dates are declared as `date`, as WF:577 requires.
- The cap is `max_node_turns: 12` with target `goodbye_no_booking`.
- Transition 1 → `find_slots`: an AND group (`treatment is_set` AND `wanted_day is_set`) nested in the top-level OR, as WF:347 requires.
- Transition 2 → `collect`: the self-`always`.
- [INFERRED] Extraction runs before routing and its values count in the same turn (WF:580). On the turn where the caller gives the last missing item, the AND group matches in code, with no routing call (WF:407).
- [INFERRED] Small inconsistency: the opening line asks two questions, while the task says "one question at a time".
- [UNCERTAIN] The self-`always` combined with the 12-turn cap is exactly the combination whose counting is unknown (§19 Q2, Q44).

**`find_slots`** (api_request, passthrough, WF:729-769):
- `passthrough: true`, `passthrough_default_transition: "offer"`, `on_enter: silent` and `disable_inactivity_monitor: true`.
- One `pre_actions` `api_call` named `find_slots`:
  - `config: {timeoutMs: 10000, maxRetries: 2}`;
  - `description` "Get free slots for a day." This is ignored, because a pre-action description is not read (TC:50, TC:167).
- All parameters are baked through `default`:
  - `url`, `method` and the `Content-Type` header;
  - `body.treatment` = `{{treatment}}` and `body.day` = `{{wanted_day}}`.
  - [INFERRED] Both variables are set at entry, because the only way in requires them (TC:93).
- Node-level `response_mapping`: `data.slots_text` → `slots_text`. It is at node level, as `pre_actions` require (TC:244), and the path starts with `data.` (TC:283).
- Transition 1 → `goodbye_no_booking` when `find_slots_failure_count greater_than 0`. This is the automatic counter, named `<nodeId>_failure_count` for a pre-actions node (TC:325). Here the node id and the function name are both `find_slots`.
- Transition 2 → `offer`, `always`: the mandatory fallback.
- [INFERRED] `maxRetries: 2` on this read and `0` on the write in `offer` follow TC:365: "A retried write can record the same thing twice".
- [INFERRED] Gap: if the API returns 200 without `data.slots_text`, the failure branch does not fire, `slots_text` stays unset, and `offer` shows a literal `{{slots_text}}` (WF:201).
- [UNCERTAIN] Is the failure counter unset or `0` before any failure? Is it counted per attempt or per call? What counts as a failure? In what format does a `date` variable go into an HTTP body?

**`offer`** (conversation, WF:770-811):
- There is no `on_enter`, so the default `llm` applies: the model writes the first line from `task_message` (WF:94, WF:159).
- `task_message` puts the data first ("Free slots: {{slots_text}}"). It then sets the read-back and "wait for a clear yes" rule, the explicit "Then CALL book_appointment. Saying that it is booked is not enough.", and the instruction to speak after the tool result.
- Tool `book_appointment`:
  - `maxRetries: 0`;
  - `description` "Book one slot. CALL it only after the caller confirmed the read-back.", an instruction with a trigger as TC:215 asks.
- Body fields:
  - `patient_id` = `{{patient_id}}` is baked from the call or test variable.
  - `treatment` = `{{treatment}}` is baked at node entry.
  - `slot_time` has the description "Start time of the accepted slot, HH:MM, 24 hour", `default "{{slot_time}}"` and `required: ["slot_time"]`. No variable `slot_time` exists, so the model fills it. WF:858 calls it "a model-filled body field" (TC:85, TC:95).
- Tool-level `response_mapping`: `data.booking_id` → `booking_id` (TC:243).
- The cap is `max_node_turns: 20` with target `goodbye_no_booking`.
- Transition 1 → `goodbye_booked` when `booking_id is_set`. It fires right after the tool result, in the same turn (WF:410).
- Transition 2 → `goodbye_no_booking` on `matches_intent` "The caller refused all offered slots or does not want to book".
- [INFERRED] There is no self-`always`. With no match the agent stays (WF:412), and global nodes stay reachable, though none exist here.
- [INFERRED] Gaps:
  - A failed booking has no deterministic exit: `book_appointment_failure_count` is unused. Only the refusal intent or the cap ends the call.
  - `treatment` is baked at entry, so a change of mind inside `offer` does not reach the request.
- [UNCERTAIN] The task tells the model to "tell the caller whether the booking worked and say goodbye" after the tool result. But the `booking_id` transition fires "before any further model turn" (TC:291), into a node that hangs up with `message_mode: none` (WF:823). The confirmation may never be spoken. WF:656 places the goodbye in the previous node, which is consistent only if the model speaks before the call (§19 Q30).

**`goodbye_booked`** (end_call, WF:812-826): `silent` entry, `disable_inactivity_monitor: true`, `transitions: []`. Terminal `function.name: "booked"` with `message_mode: none`, so the hangup is silent. The `endedReason` is `booked`.

**`goodbye_no_booking`** (end_call, WF:827-847): the same shape. Terminal `function.name: "no_booking"`, `message_mode: custom`, `spoken_message` "No appointment was booked. You can call us again at any time. Goodbye." The `endedReason` is `no_booking`. It is reached from the lookup failure (WF:766), the refusal intent (WF:809) and both turn caps (WF:708, WF:806).

### 17.4 Happy path [INFERRED from the rules above]

1. `collect` speaks its `tts` greeting.
2. The caller gives the treatment and the day. Extraction sets both, and the AND group routes to `find_slots`.
3. `find_slots` runs silently, maps `slots_text`, and routes to `offer` through `always`.
4. `offer`'s `llm` entry offers the earliest slot.
5. The caller accepts. The model reads back, the caller says yes, and the model calls `book_appointment(slot_time=...)`.
6. `booking_id` is mapped, and routing in the same turn goes to `goodbye_booked`.
7. The call hangs up silently. `endedReason` = `booked`.

[INFERRED, event] The `https://api.example.com` URLs are placeholders. In the event, the agent "may call only the kit's tool API" (HP §Rules:37).

---

## 18. `examples/base-agent.json`, annotated

### 18.1 What it is

- [DOC] "`examples/base-agent.json` is an agent, not a builder. It is the same two-step workflow that is already in your workspace: check identity, then take a payment promise. It uses four of the seven tools, so it handles only the simplest customers: in one run it passed 2 of the 13 practice customers. Read it to see what a valid workflow looks like." (RM:34)
- [DOC] The kit table calls it "An example phone agent: two steps, four tools." (RM:46). The page calls it "a place to start, not a good score" (HP §Data:19).
- [DOC] The skill says: "Use it as the pattern for the JSON, not as the answer." (SK:14)
- [DOC] Deploy it with `python3 -c "import freya,json; print(freya.save_workflow('base', json.load(open('examples/base-agent.json'))))"`, then `python3 tools/run_cases.py <agent_id> --brief A` (RM:23-24).
- [DOC] RM:67: "The same phone agent can pass a customer in one run and fail it in the next." No kit file says which 2 cases passed.
- [CODE] "Four tools" means four of the seven bank tools:
  - used: `verify_identity`, `get_account`, `create_promise` and `close_call`;
  - missing: `add_note`, `schedule_callback` and `transfer_to_agent`.
  - The seven paths are at OAS:15, 89, 172, 234, 298, 354 and 409. `end_call` is a platform handler, not a bank tool (TC:64).
- [INFERRED, from a local offline check] The keys of every object except `test_variables` are in PostgreSQL `jsonb` order (shorter keys first, then bytewise). `test_variables` is in insertion order. The node positions are fractional. Together this suggests the platform's stored form of a workflow made at least partly in the dashboard. No kit file calls it an export, and it lacks the `export_workflow` wrapper (FP:68).

### 18.2 Top-level keys

| Key | BA line | Value | Doc meaning | Note |
|---|---|---|---|---|
| `nodes` | 2-329 | `identity`, `collection` | Required (WF:53) [DOC] | Both are `conversation` nodes [CODE] |
| `tools` | 330-397 | one tool, `close_call` | Workflow-level lifecycle tools (WF:58) [DOC] | Has `alwaysRunsAt: ["end_of_call"]` (BA:336-338) [CODE] |
| `global_nodes` | 398 | `{}` | Interrupt handlers (WF:55) [DOC] | None [CODE] |
| `initial_node` | 399 | `"identity"` | Where every call starts (WF:52) [DOC] | [CODE] |
| `system_prompt` | 400 | `""` | Global dialogue rules (WF:54) [DOC] | Empty. Each `task_message` repeats the persona and language line instead (BA:140, BA:315) [CODE] |
| `test_variables` | 401-406 | `first_name` "Daniel", `last_name` "Reyes", `title` "Mr", `now` "2026-10-14T11:00" | Defaults. A passed value wins (WF:209) [DOC] | Exactly PUB-01's variables (PTS:8-13). **No `customer_id`**. `first_name` is never referenced [CODE] |
| `context_variables`, `agent_config`, `nodePositions` | absent | | WF:246, WF:62, WF:60 [DOC] | Correctly absent. BA uses an undocumented node-level `position` instead [CODE] |

### 18.3 Graph and call life cycle [CODE + INFERRED]

```text
[call start]
   |
   v
identity (conversation)    tools: verify_identity, end_call
   |  one transition, deterministic:
   |    verify_identity_response.data.all_verified == "true"  OR  == "True"
   v
collection (conversation)  tools: get_account, create_promise, end_call
   |  transitions: []  (no exit at all)
   v
[call ends by]: the agent says "Have a good day" (undocumented trigger_pattern)
                | the model calls the end_call tool | the customer hangs up | the max call duration
   |
   v
close_call (workflow-level lifecycle tool, end_of_call): outcome/reason model-filled or dropped (contested)
```

- [CODE] There are no `end_call` nodes, `api_request` or `code` nodes, global nodes, extraction, `response_mapping`, post-hooks or failure branches.
- [DOC] This breaks WF:680, "Every path must reach an `end_call` node", and WF:672, "Give every node that sets `max_node_turns` a `max_turn_transition`".

### 18.4 Node `identity`: every field (BA:3-153)

| Field | Line | Value | Documented meaning | Note |
|---|---|---|---|---|
| `name` | 4 | `"identity"` | Same as the key (WF:90) [DOC] | |
| `tools` | 5-103 | `verify_identity`, `end_call` | Model-callable tools (WF:101) [DOC] | §18.5, §18.6 |
| `on_enter` | 104-107 | `tts`: "Hello, this is the digital assistant of Freya Bank. Am I speaking with {{title}} {{last_name}}?" | Fixed line, no model call (WF:160). An unresolved var is said aloud (WF:201) [DOC] | Deterministic opening. It omits "the call is recorded", which Brief A rule 1 requires (BRA:24) [CODE][DOC] |
| `position` | 108-111 | `x` 498.0464451619148, `y` -590.6037491300582 | **Undocumented** | Probably editor layout [INFERRED] |
| `node_type` | 112 | `"conversation"` | (WF:72) [DOC] | |
| `assertions` | 113 | `[]` | **Undocumented** | Purpose unknown [UNCERTAIN] |
| `passthrough` | 114 | `false` | Default (WF:104) [DOC] | |
| `pre_actions` | 115 | `[]` | Stripped from conversation nodes without an error (WF:82; TC:153; API:87) [DOC] | Empty, so harmless |
| `transitions` | 116-138 | one transition | Ordered list (WF:96) [DOC] | §18.7 |
| `role_message` | 139 | `""` | "Rarely needed" (WF:93) [DOC] | |
| `task_message` | 140 | 4 lines (§18.8) | (WF:92) [DOC] | |
| `interruptible` | 141 | `false` | **Undocumented as a node field.** WF documents `interruptible` only as a terminal parameter (WF:644). TC documents `config.interruptible` for tools (TC:54, TC:345) | Meaning unknown, possibly voice barge-in [UNCERTAIN]. `collection` has `true` (BA:316) |
| `max_node_turns` | 142 | `80` | Default 10. Counts user messages only (WF:106, WF:662) [DOC] | |
| `response_mapping` | 143 | `[]` | Node level is "For `pre_actions` nodes" (WF:103) [DOC] | Empty |
| `extraction_schema` | 144 | `[]` | (WF:100) [DOC] | No extraction |
| `max_turn_transition` | 145 | `null` | Without one, "the cap changes nothing" (WF:663) [DOC] | `null` conflicts with WF:64 (§18.12) |
| `truncation_strategy` | 146 | `"keep_all"` | Default (WF:111) [DOC] | |
| `suppress_tool_results` | 147 | `false` | Default. The model sees the raw result (WF:110; TC:341) [DOC] | The model sees the whole envelope, including `header` (TC:252-262). There is no post-hook to trim it (cf. TC:411) [INFERRED] |
| `truncation_window_size` | 148 | `10` | Only used by `keep_recent`/`summarize` (WF:112) [DOC] | Inert under `keep_all` |
| `on_enter_first_entry_only` | 149 | `false` | Default (WF:95) [DOC] | The node is never re-entered [INFERRED] |
| `disable_inactivity_monitor` | 150 | `false` | Silence check-ins on (WF:109) [DOC] | Effect in chat simulations unknown [UNCERTAIN] |
| `passthrough_default_transition` | 151 | `null` | (WF:105) [DOC] | Not a passthrough node. `null` (§18.12) |
| `return_to_previous_on_interrupt` | 152 | `false` | **Undocumented** | Unknown [UNCERTAIN] |

- [CODE] Both nodes carry exactly the same 23 keys (checked locally).
- [DOC] Documented node fields that BA leaves out: `routing_prompt`, `loop_condition`, `loop_prompt`, `terminal`, `reasoning_override`, `idle_config` (WF:86-115).

### 18.5 Tool `verify_identity` (in `identity`, BA:6-66)

| Path | Line | Value | Meaning | Who supplies it |
|---|---|---|---|---|
| `type` | 7 | `"function"` | Always `"function"` (TC:47) [DOC] | |
| `config.timeoutMs` | 9 | `12000` | One attempt, in ms (TC:52) [DOC] | |
| `config.maxRetries` | 10 | `0` | Tool-level retries (TC:53) [DOC] | [INFERRED] Right for a call where wrong answers count (OAS:17) |
| `function.name` | 13 | `"verify_identity"` | Result variables are named after it (TC:48) [DOC] | Produces `verify_identity_response.*`, `verify_identity_args.*` and counters |
| `function.handler` | 14 | `"__function__:api_call"` | An HTTP request (TC:62) [DOC] | |
| `url` default | 18-21 | `https://freya-bank-mock.freyavoice.workers.dev/v1/verify_identity` | Baked (TC:84, TC:91) [DOC] | Workflow. It is OAS `servers[0].url` (OAS:10) + `/verify_identity` [CODE] |
| `body.required` | 24-27 | `["field", "answer"]` | Required fields go in `body.required` (TC:104) [DOC] | OAS also requires `customer_id`. BA lists only the model-filled fields [CODE][INFERRED] |
| `body.properties.field` | 29-37 | `enum` [`date_of_birth`, `phone_last4`], string, `default "{{field}}"`, "Which answer this is." | An unresolved default means the model fills it and sees `type`, `description` and `enum` (TC:85) [DOC] | **Model.** No variable `field` exists, and model arguments are stored as `verify_identity_args.field` (TC:97) [INFERRED] |
| `body.properties.answer` | 38-42 | string, `default "{{answer}}"`, "date_of_birth as YYYY-MM-DD, phone_last4 as four digits." | as above | **Model** |
| `body.properties.customer_id` | 43-46 | `default "{{customer_id}}"` | Baked when set at entry (TC:93, TC:95) [DOC] | **Workflow**, when the call passes `customer_id`. `run_cases.py` does (RC:86-88); `test_variables` does not [CODE] |
| `method` | 49-52 | `"POST"` | Baked [DOC] | Workflow |
| `headers.Content-Type` | 53-61 | `application/json` | "Each header is a property with a `default`" (TC:74) [DOC] | Workflow |
| `function.description` | 64 | "Check one security answer. Call it once for each answer the customer gives." | The only text the model reads about the tool (TC:167) [DOC] | Says when to call it, as TC:215 asks |
| absent: `response_mapping`, `pre_process_code`, `post_process_code`, `connect_retries` | | | `connect_retries` defaults to 2 (TC:353) [DOC] | No `what_to_do_next` post-hook (TC:568-575) [INFERRED] |

[DOC] The response fields are `ok`, `error`, `verified`, `wrong_answers_left`, `all_verified` and `hint` (OAS:57-77), inside the `{status, data, message, status_code, header}` envelope (TC:252-262). [CODE] BA reads only `all_verified` (BA:125, BA:131).

### 18.6 Tool `end_call` (byte-identical in both nodes: BA:67-102 and BA:264-299)

| Path | Line (identity / collection) | Value | Documented? |
|---|---|---|---|
| `config.timeoutMs` | 70 / 267 | `10000` | Field documented (TC:52). Effect on a hangup unknown |
| `function.name` | 73 / 270 | `"end_call"` | `endedReason` = terminal `function.name` is documented for end_call **nodes** only (WF:652; API:310) |
| `function.handler` | 74 / 271 | `"__function__:end_call"` | TC:64 documents it only "in the `terminal` of an `end_call` node". Use as a node **tool** is **undocumented** |
| `message_mode` | 78-81 / 275-278 | `"none"` | "`none`: hang up without a farewell" (WF:641) |
| `interruptible` | 82-85 / 279-282 | `true` | Opens "a short window after the farewell in which the user can still speak" (WF:644) |
| `trigger_pattern` | 86-89 / 283-286 | `"Have a good day\|have a good day"` | **Undocumented.** BA:100 says the phrase "ends the call by itself" |
| `trigger_timeout` | 90-93 / 287-290 | `3` | "Length of that window in seconds" (WF:645) |
| `trigger_pattern_both` | 94-97 / 291-294 | `"goodbye\|bye\|have a good day\|you too\|thank you\|thanks\|take care"` | Farewell phrases that "do not cancel the close" (WF:646) |
| `function.description` | 100 / 297 | "Ends the call. You normally do NOT call this: the phrase \"Have a good day.\" ends the call by itself. Call it without any text only if the customer answers after your goodbye." | Model-facing (TC:50) |

- [INFERRED] Every parameter has a literal default, so all are baked and the model sees a zero-parameter tool (TC:84, TC:91).
- [INFERRED] `trigger_pattern` lists both capitalisations, which hints at a case-sensitive, `|`-separated match. Because the tool sits in both nodes, the phrase trigger is armed for the whole call.
- [CODE] The simulated customer is told: "When the caller says goodbye, say "Thank you, goodbye." and say nothing more." (RC:24). Both "thank you" and "goodbye" are in `trigger_pattern_both`, so that reply should not cancel the close [INFERRED].
- [DOC] "The window is timed on a wall clock and a chat simulation cannot measure it." (WF:654)

### 18.7 The `identity` transition (BA:116-138)

```json
{
  "condition": {
    "logic": "or",
    "conditions": [
      { "mode": "exact", "operand": "true", "operator": "equals", "variable": "verify_identity_response.data.all_verified" },
      { "mode": "exact", "operand": "True", "operator": "equals", "variable": "verify_identity_response.data.all_verified" }
    ]
  },
  "description": "both security answers verified",
  "target_node": "collection"
}
```

- [DOC] This is the grouped form with a top-level `or` (WF:331). `equals` compares strings (WF:296). Testing both spellings is the WF:372-389 pattern.
- [DOC] The variable is the automatic flattened key `<tool>_response.data.<field>` (TC:264-277), which "can be used directly as a transition variable" (TC:285). It is not a mapping; BA's `response_mapping` is `[]`.
- [CODE] `mode: "exact"` is **undocumented**.
- [DOC] There is no `is_tool_call`, so the router evaluates the transition (WF:449). The condition is deterministic, so no routing call is needed when it matches (WF:407).
- [DOC] Timing: routing runs after the tool result, "before any further model turn" (TC:291). When the second answer makes `all_verified` true, the call moves to `collection`, whose `tts` line is spoken next [INFERRED].
- [INFERRED] Only the **evaluation** is deterministic. Whether the variable is ever set depends on the model calling `verify_identity` with correct `field` and `answer`. [PROBED-earlier] A re-verify response can lack `all_verified` entirely (RAT:153).
- [CODE] Missing branches:
  - no exit for a failed check, a decline, a third party or a wrong number;
  - no self-transition;
  - no `max_turn_transition`.

  With no match "the agent stays and answers from the same `task_message`" (WF:412).

### 18.8 `identity` `task_message` (BA:140), four lines

1. "You are the digital assistant of Freya Bank. Your only job here is to verify the customer's identity. Speak English, one or two short sentences per turn."
2. "Once the customer confirms who they are, ask for their date of birth, then the last four digits of their phone number, and call verify_identity for each answer."
3. "You do not know why the bank is calling. If asked, say you can explain after the security check."
4. "If the identity check fails, say goodbye, ending with \"Have a good day.\""

[INFERRED] What these lines do and miss:
- Line 3 keeps account words out of pre-verification talk, by design.
- Line 3 also conflicts with Brief A rule 15 (BRA:44): "Asking what the call is about instead of answering counts as declining."
- The `end_call` tool is not mentioned in the prompt. Its use is described only in the tool description.
- There is no `{{now}}` in this node.

### 18.9 Node `collection` (BA:154-328): differences from `identity`

| Field | Line | Value | Note |
|---|---|---|---|
| `tools` | 156-300 | `get_account`, `create_promise`, `end_call` | §18.10 |
| `on_enter` | 301-304 | `tts`: "Thank you, that's verified. I'm calling about your Freya Bank account, do you have a minute?" | Truthful, because the only way in is `all_verified` [INFERRED] |
| `position` | 305-308 | `x` 500, `y` 0 | Undocumented |
| `transitions` | 313 | `[]` | **No exit at all** [CODE] |
| `task_message` | 315 | 5 lines (below) | |
| `interruptible` | 316 | `true` | Undocumented node field |
| all others | 309-327 | same as `identity` | `max_node_turns` 80, `null` `max_turn_transition`, `keep_all`, 10, `false` flags, `null`s |

`task_message` (BA:315):
1. "You are the digital assistant of Freya Bank on a collection call. The customer is verified. Speak English, one or two short sentences per turn."
2. "First call get_account, then tell the customer the past due amount and ask when they can pay it."
3. "Get a payment date, read the amount and the date back, and call create_promise after the customer says yes."
4. "When the promise is recorded or the customer will not pay, say goodbye, ending with \"Have a good day.\""
5. "Now: {{now}}."
   - This is the only date anchor, as WF:240 recommends.
   - [UNCERTAIN] Whether the "formatted for speech" rule (WF:200) rewrites the ISO string is unknown.

### 18.10 Tools `get_account` (BA:157-200) and `create_promise` (BA:201-263)

**`get_account`**
- `config`: `timeoutMs` 12000, `maxRetries` 0.
- `url` `…/v1/get_account`, `body.required: []`, `customer_id` baked.
- [INFERRED] The model sees a zero-parameter tool.
- `description`: "The customer's late products. Call it once, before you say anything about the account."
- [DOC] It is a model-called tool, so it "Can be skipped" (TC:163). It exists only in `collection`; elsewhere the model gets "The function `<name>` is not currently available." (TC:221). [INFERRED] So it cannot be called before verification.
- [CODE] That matters: SC:31-32 fails a case if `get_account` or `create_promise` returns "identity not verified". [PROBED-earlier] That error is logged in the ledger (RAT:154).
- [CODE] There is no mapping. The model reads the raw result (`suppress_tool_results: false`).
- [PROBED-earlier] Product ids are `p1..p3` (RAT:155).

**`create_promise`**
- `config`: `timeoutMs` 12000, `maxRetries` 0. This follows TC:365.
- `url` `…/v1/create_promise`, `body.required: ["product_id", "amount", "date"]`.

| Field | Line | Declaration | Who supplies it |
|---|---|---|---|
| `date` | 225-229 | string, `default "{{date}}"`, "Payment date as YYYY-MM-DD." | Model (no `date` variable is set) [INFERRED] |
| `amount` | 230-234 | **number**, `default "{{amount}}"` (a string), "Amount the customer will pay." | Model. [PROBED-earlier] The bank accepts a string amount (RAT:156) |
| `product_id` | 235-239 | string, `default "{{product_id}}"`, "product_id from the account result, for example p1." | Model. No enum, although TC:120-126 recommends one |
| `customer_id` | 240-243 | `default "{{customer_id}}"` | Workflow |

- `description`: "Record a payment promise. Call it only after the customer said yes to the read-back of amount and date."
- [CODE] BA never branches on `ok` and has no failure instruction. [PROBED-earlier] Business errors come back as HTTP 200 with `ok:false`. Examples: "date must be YYYY-MM-DD", "unknown product_id", "this product already has a promise" (RAT:144, RAT:156).

### 18.11 Workflow-level lifecycle tool `close_call` (BA:331-396)

| Path | Line | Value | Meaning or note |
|---|---|---|---|
| `config.timeoutMs` / `maxRetries` | 334-335 | `12000` / `0` | |
| `config.alwaysRunsAt` | 336-338 | `["end_of_call"]` | Lifecycle tool: "never shown to the model". It fires "After the call has ended" (TC:516-521) [DOC] |
| `function.name` / `handler` | 341-342 | `close_call` / `api_call` | |
| `url` | 348 | `…/v1/close_call` | OAS:409 |
| `body.required` | 352-354 | `["outcome"]` | OAS requires `customer_id` and `outcome` (OAS:438-441) |
| `body.properties.reason` | 356-360 | string, **no enum**, `default "{{reason}}"`, description "Leave out for promise. no_promise: refused. not_verified: failed (wrong answers) or declined (would not answer). not_reached: wrong_number or unclear." | OAS: "Required for every outcome except promise and paid." (OAS:435) |
| `body.properties.outcome` | 361-371 | enum [`promise`, `no_promise`, `not_verified`, `not_reached`], `default "{{outcome}}"` | The OAS enum has 6 values (OAS:424-431). **`paid` and `transferred` are missing** |
| `body.properties.customer_id` | 372-375 | `default "{{customer_id}}"` | Baked when passed |
| `function.description` | 393 | "Record how the call ended, from the conversation." | Written for a model filler [INFERRED] |
| `pre_process_code` | 395 | below | Top-level field of the tool object (TC:369) |

**How `outcome` and `reason` get values.**
- [CODE] No variable named `outcome` or `reason` is ever set. There is no extraction, mapping or code for them, and they are not session variables.
- [DOC] Two documented readings conflict:
  - **drop**: "The field is dropped from the request" (TC:115; WF:202);
  - **model fill**: "If a `{{var}}` parameter is still unresolved, one model call fills the parameters." (TC:561)
- [INFERRED] The reported pass (RM:34) favours model fill. `outcome` is required (OAS:438-441), and the scorer compares `(outcome, reason)` (SC:19-20), so with dropped fields no case could pass.
- [DOC] "`response_mapping` is applied for `start_of_call`. It is not applied for `end_of_call`." (TC:562). "A malformed lifecycle tool is dropped at run time without an error." (TC:564)
- [INFERRED] Structural benefit: the model cannot call `close_call`, and it fires once, after the call. So "exactly one `close_call` ... the last tool call" (BRA:106; SC:29) holds by construction, provided it runs.

`pre_process_code` (BA:395):

```python
try:
    b = config.get('body')                         # config = the substituted request (TC:395)
    if isinstance(b, dict) and b.get('outcome') in ('promise', 'paid'):
        b.pop('reason', None)                      # outcomes that take no reason (OAS:435; BRA:110-111)
except Exception:
    pass
```

- [INFERRED] It keeps the ledger's `reason` null on a promise, which SC:19-20 requires.
- [INFERRED] The `'paid'` branch can only run if the filler ignores BA's own enum, which excludes `paid`.
- [UNCERTAIN] Whether the hook runs after the model fill is not documented.
- [DOC] Hooks are honoured on `api_call` tools (TC:402).

### 18.12 Undocumented, misplaced and `null` fields

| Item | Lines | Status |
|---|---|---|
| node `position` `{x, y}` | 108-111, 305-308 | Undocumented. WF documents only top-level `nodePositions` (WF:60) |
| node `assertions: []` | 113, 310 | Undocumented |
| node `interruptible` | 141, 316 | Undocumented as a node field |
| node `return_to_previous_on_interrupt: false` | 152, 327 | Undocumented |
| condition `mode: "exact"` | 122, 128 | Undocumented |
| `end_call` parameter `trigger_pattern` | 86-89, 283-286 | Undocumented (WF:639-646 lists the others) |
| `__function__:end_call` as a node **tool** | 74, 271 | Documented only for terminals (TC:64) |
| `pre_actions: []` on conversation nodes | 115, 312 | Documented to be stripped without an error (WF:82; TC:153; API:87) |
| node-level `response_mapping: []` on conversation nodes | 143, 318 | Documented only for `pre_actions` nodes (WF:103) |
| `null` values (4) | 145, 151, 320, 326 | Conflict with WF:64. Yet RM:23 posts BA unchanged and RM:34 reports a run. Either the platform accepts `null` in these two fields or the command fails [UNCERTAIN] |

### 18.13 Parameter supply matrix [INFERRED from TC:80-99]

| Tool | Baked by the workflow (model never sees it) | Filled by the model | Visible to the model |
|---|---|---|---|
| `verify_identity` | `url`, `method`, `headers`, `body.customer_id` | `body.field` (enum of 2), `body.answer` | yes |
| `end_call` | all five parameters | none | yes, with zero parameters |
| `get_account` | `url`, `method`, `headers`, `body.customer_id` | none | yes, with zero parameters |
| `create_promise` | `url`, `method`, `headers`, `body.customer_id` | `body.product_id`, `body.amount`, `body.date` | yes |
| `close_call` | `url`, `method`, `headers`, `body.customer_id` | `body.outcome` (enum of 4), `body.reason` (free text): one model call at the end, or dropped (contested) | no (lifecycle) |

[DOC] The working builder uses the same convention: `customer_id` is baked, and every other field gets `"{{<field name>}}"` with no such variable, so the model fills it (TC:95).

[INFERRED] trap: a model-filled name must not collide with a variable set at entry (TC:99). In a BA-style design, that rules out computed variables named `date`, `amount`, `answer`, `field`, `product_id`, `outcome` or `reason`.

### 18.14 What a happy-path call does [INFERRED, built from the cited DOC rules]

1. The engine enters `identity`, bakes `{{customer_id}}` into the node tools (TC:93) and speaks the `tts` line (WF:160).
2. Each user turn runs extraction (empty schema), routing (deterministic only) and dialogue. Dialogue sees an empty `system_prompt`, an empty `role_message`, `## Current Task`, the `task_message`, the history and the tools (WF:119-126).
3. The customer confirms. The model asks for the date of birth and calls `verify_identity(field=date_of_birth, answer=YYYY-MM-DD)`. It then asks for the phone digits and calls again; that response has `all_verified` = true.
4. Routing runs after the tool result. The `equals "true"` branch matches, and `collection` is entered in the same turn (TC:291). Its `tts` line is spoken.
5. The model calls `get_account`, states the amount, works out a date from `Now: {{now}}`, reads it back, and calls `create_promise` after a yes.
6. The model says "... Have a good day." The undocumented `trigger_pattern` hangs up, presumably after the 3-second interruptible window.
7. After the call has ended, the engine fires `close_call`. `outcome` and `reason` are model-filled or dropped, and the pre-hook pops `reason` for a promise.
8. The scorer compares the ledger with the expected outcome (SC:17-34). The judge reads the transcript against the case's `checks` (RC:47, RC:95-96).

### 18.15 Structural gaps against the tool API and Brief A [CODE/DOC; impact INFERRED]

| Gap | Evidence | Practice cases whose expected ledger it makes unreachable [CODE: PTS `expected`] |
|---|---|---|
| No `schedule_callback` tool | OAS:298 exists; BA has none | PUB-02 (`not_reached`/`callback`) |
| No `transfer_to_agent` tool; `transferred` not in the `outcome` enum | OAS:354, OAS:427; BA:362-367 | PUB-09 (`transferred`/`restructuring`) |
| No `add_note` tool | OAS:234 | PUB-12 (notes expected) |
| `paid` not in the `outcome` enum | OAS:426; BA:362-367 | PUB-08 (`paid`), unless the filler ignores the enum |
| No calendar, deadline or floor logic | Only `Now: {{now}}` (BA:315); BRA:53-73 | Dated cases such as PUB-04, PUB-07 and PUB-13 [INFERRED] |
| Required sentences missing from prompts ("call is recorded", text-message sentence) | BRA:24, BRA:92 vs BA:105, BA:315 | Judge checks on many cases [INFERRED] |
| No `ok:false` handling and no `what_to_do_next` | BA:205; TC:568-575; BRA:91 | Honesty checks, e.g. PUB-10 [INFERRED] |

### 18.16 What to keep and what to fix [INFERRED]

**Keep:**
- `tts` entry lines for wording the brief fixes;
- the both-spellings OR on flattened `<tool>_response.data.*` keys;
- `customer_id` baked through `"{{customer_id}}"`;
- model-filled fields through `"{{<field>}}"` with an `enum` and a format description;
- `maxRetries: 0` on writes;
- `close_call` as an `end_of_call` lifecycle tool, so there is exactly one close and it comes last;
- a defensive `pre_process_code`;
- account tools only in nodes reachable after verification.

**Fix:**
- Generate the tool set and enums from the tool API file.
- Make `outcome` and `reason` resolve to variables set deterministically, so they bake instead of depending on the contested model fill.
- Add failure, decline and third-party exits, `end_call` nodes and `max_turn_transition` targets.
- Compute dates, deadlines and floors in code.
- Add `what_to_do_next` post-hooks.
- Remove the `null` values and the undocumented keys.
- Put the brief's exact sentences into `tts` lines or prompts.

---

## 19. Open questions, with a safe choice for each

The hackathon forbids probing or load-testing the platform (HP §Rules:37). These questions should be settled only from what normal practice runs of your own agent show, for example the `route_evaluated` events with `branches` and `variable_table` (API:329), the `workflowSnapshot` (API:334) and the ledger. Until then, design so that the answer does not matter.

| # | Unknown or contradiction | Sources in tension | Safe design choice until known |
|---|---|---|---|
| Q1 | List order or "deterministic first": does a later deterministic match (including a trailing `always`) beat an earlier `matches_intent`? | WF:406 vs WF:407; WF:420; WF:681 | Never mix `matches_intent` and `always` in one node. Prefer an extracted enum plus `equals` (WF:584) |
| Q2 | Is a self-transition a re-entry? Does it re-run `on_enter`, reset `current_turns`, drop the `loop_prompt` or reset the cap's count? | WF:164, WF:172, WF:237; example WF:701, WF:726 | Set `on_enter_first_entry_only: true` on self-looping nodes. Do not depend on the cap firing in them |
| Q3 | Can a global node fire from a node that ends in a self-`always`? (Inferred: no) | WF:400, WF:420, WF:488 | Decide per node: either a self-`always` or global reachability |
| Q4 | When does `loop_prompt` apply: always from turn 2, or only when `loop_condition` matched? | WF:99, WF:133, WF:432 vs WF:398 vs WF:412 | Avoid `loop_prompt`, or write it so either reading is safe |
| Q5 | Does `routing_prompt` replace the default instruction or add to it? If it replaces, does it need its own input placeholders? | WF:97 vs WF:416 | Avoid it. Put routing logic in deterministic conditions |
| Q6 | Which text does `matches_intent` judge: the transition `description` or `condition.description`? | WF:286 vs WF:309; example WF:324-328 | Write the same text in both, as WF:454/456 does |
| Q7 | Context of `matches_intent`: the last message only? Is it re-judged against the stale message after a tool result? | WF:29 vs WF:309; WF:410; TC:317 | Do not leave action nodes on intent (TC:317) |
| Q8 | Several intents true in the single call: which wins? | WF:311, WF:406 | Make intents mutually exclusive, or use an enum |
| Q9 | Does `loop_condition` cost a routing call every turn, and is it part of the single intent call? | WF:398, WF:407, WF:430 | Prefer a self-`always` (WF:426) |
| Q10 | In a turn that moves A→B where B is a `silent` conversation node, does the agent reply? | WF:161, WF:460 | Give conversation nodes an `llm` or `tts` entry |
| Q11 | What `on_enter.prompt` overrides | WF:159 | Avoid. Use `tts` for fixed lines |
| Q12 | On a re-entry with `on_enter_first_entry_only: true`, what produces the reply? | WF:95, WF:164 | Make the `task_message` able to open by itself |
| Q13 | Which values the "formatted for speech" rule rewrites (only `date`-typed values, or any ISO string such as `now`?), in what format, and in which fields | WF:200 | Give the model pre-formatted date text computed in code |
| Q14 | Is `test_variables` merged outside "a web call" (chat, simulation, benchmark)? | WF:209, WF:234 | Seed state variables in a code node, not in `test_variables` |
| Q15 | Are prompt placeholders resolved every turn or once at node entry? | WF:191; TC:93; TC:466 | Pass mid-node results through the tool result (`what_to_do_next`) or move to a new node |
| Q16 | Exactly which fields support `{{var}}`: `loop_condition`, `condition.description`, `role_message`, extraction descriptions, `enum_values`, `:json` in prompts | WF:191, WF:242, WF:432 | Use placeholders only in the documented fields |
| Q17 | An unresolved lifecycle-tool parameter: dropped or model-filled? | WF:202, TC:115 vs TC:561 | Make every lifecycle parameter resolve to a variable set earlier |
| Q18 | Operator edge semantics: `is_set` on `""`, `not_equals`/`contains` on an unset variable, `greater_than` on an unset or non-numeric value | WF:296-303 | Seed every routed variable with a string sentinel, and route only on known strings |
| Q19 | Which writers produce `"True"` and which `"true"` | WF:372; TC:286 | Test both, or write string flags |
| Q20 | `equals` on numbers: `"3"` vs `"3.0"` | WF:296 | Use `greater_than`/`less_than` or string flags |
| Q21 | A top-level `and`, deeper nesting, or `matches_intent` inside a group | WF:331, WF:347 | Use only shapes 1-4 of §10.3 |
| Q22 | Is the bare single variable condition accepted? | WF:368 | Use the grouped form |
| Q23 | Same-target merge details: list position, kept description, `is_tool_call` | WF:408 | Never give two transitions the same target |
| Q24 | Stale values: does an unclear turn overwrite an extracted value? Does "Empty if unclear" write `""`? | WF:178; WF:596 | Reset routing variables in code before re-entry |
| Q25 | Are tool-call and tool-result messages kept across nodes? | WF:170; TC:165 | Carry needed results in mapped variables |
| Q26 | `agent_config`: "omit it", yet the kit patches it on update, and `create` does not patch | WF:62; RM:103; FP:55-60; API:101 | Omit it and save through `save_workflow`. If a chat turn will not start, save once more so the update path patches the model |
| Q27 | Strict schema vs silent stripping: are unknown keys and BA's `null`s rejected or dropped? | WF:64 vs WF:79; API:87; BA nulls | Send no `null` and no undocumented keys, and read the stored workflow back |
| Q28 | Which node and transition fields are required | WF:88-113, WF:283-288 | Always send `name`, `node_type`, `transitions`, and on every transition `target_node`, `description` and `condition` |
| Q29 | Does `{{<node>.current_turns}}` use the key or the `name`? | WF:237; WF:90 | Keep `name` equal to the key |
| Q30 | After a same-turn post-tool transition into a silent `none` end node, does the model speak the result first? | WF:410, WF:656, WF:773, WF:823; TC:291 | Say the required closing lines in a `custom` `spoken_message`, or in a `tts` line in a node reached before hangup |
| Q31 | `context_variables`: dropped only on save, or inactive at run time too? | WF:246 | Do not use it |
| Q32 | Do the system dates ignore daylight saving time? | WF:228-229 | Do not use system dates |
| Q33 | Does `reasoning_override` affect `experimental-5`? | WF:113 | Leave the default |
| Q34 | `passthrough_default_transition` vs a final `always`: why both, and which wins if they differ? | WF:466-467 | Set both to the same target |
| Q35 | Is an initial passthrough code node skipped on the chat route? | WF:484 vs API:252 | Do not rely on chat-route results for initial code values. Simulations are what is scored |
| Q36 | Global mechanics: same routing call? `__previous__` re-running `on_enter`? checked after tool results? the "loop" at terminals? where a global `is_tool_call` is offered? | WF:488-526 | Use passthrough global nodes with a `tts` line, and exclude terminal and identity nodes |
| Q37 | The extraction date anchor (real clock or `now`), the storage format of `date`, and the format in HTTP bodies | WF:577; WF:240; WF:754 | Compute dates in code from `now` |
| Q38 | Built-in relative-date semantics vs brief rules 21-22 | WF:578, WF:582; BRA:64-65 | Use a custom `extraction_prompt` with all four placeholders, or code |
| Q39 | Extraction internals: message window, `max_retries` default, behaviour after retries, `validation_pattern` on non-strings, numeric enums, `name`/`phone_number`/`datetime` semantics | WF:557-571 | Set every field explicitly. Prefer `string` with an enum or pattern |
| Q40 | Failure counter semantics: unset vs `0`, per attempt or per call, what counts as a failure, node or function naming | WF:766; TC:321-326 | Route on a mapped `ok` string, with the counter as a backup |
| Q41 | End-call defaults: `message_mode`, `trigger_timeout`, phrase matching (case, regex) | WF:641-646; BA:86-89 | Set `message_mode` explicitly. Avoid `interruptible` (it cannot be measured in chat, WF:654) |
| Q42 | Truncation details: whether tool messages count, and which model summarises | WF:664 | Keep `keep_all` |
| Q43 | Does the inactivity monitor act in chat simulations? | WF:109, WF:115 | Disable it on passthrough and end nodes, as the example does |
| Q44 | `max_node_turns` counting: per entry or total, Nth or (N+1)th message, pre-emption, where the overrun is recorded | WF:106, WF:662-663 | Set a generous cap with a `max_turn_transition`, and do not count on its exact timing |
| Q45 | Tool-call transition details: tool name, description, use of `condition`, conflict with WF:142, variables created | WF:449-460 | Prefer router-evaluated deterministic transitions |
| Q46 | `endedReason` when a call ends through the `end_call` **tool** or phrase | WF:652; API:310 | Use `end_call` nodes |
| Q47 | Meaning of `mode: "exact"`, `position`, `assertions`, node `interruptible`, `return_to_previous_on_interrupt` | BA only | Omit them |
| Q48 | `trigger_pattern` semantics | BA:86-89, BA:100 | Do not use it. End through `end_call` nodes |

---

## Traps to remember

1. **Routing rules in prompts do nothing.** Routing never sees `task_message`. Put routing in transitions (WF:29, WF:34).
2. **Never name other nodes or describe routing in `task_message`.** The model narrates steps that have not happened (WF:140).
3. **A tool-less node must say that no tool call is allowed**, and so must its `loop_prompt` (WF:142).
4. **The dialogue model can only call the current node's tools.** A tool listed elsewhere returns "The function `<name>` is not currently available." (WF:35; TC:221)
5. **`tools` on a non-conversation node and `pre_actions` on a conversation node are stripped silently.** The save succeeds anyway (WF:79-84; TC:153; API:87).
6. **No `null` anywhere** (WF:64; WF:579). BA has four, so do not copy it blindly (BA:145, BA:151, BA:320, BA:326).
7. **An update replaces the whole workflow.** Leaving out `test_variables` (or the filled `agent_config`) deletes it. An update is not live until it is published (API:101, API:103; FP:49-64).
8. **Leave `agent_config` out** (WF:62; RM:103). The kit's update path patches the model afterwards, and the first create does not (FP:31-34, FP:55-60).
9. **Variables are never cleared.** A stale extracted value can re-fire a fork when the node is re-entered (WF:178).
10. **An unresolved `{{var}}` is not an error.** In a prompt the model sees the literal placeholder. In `tts` or `spoken_message` it is read aloud. A single-placeholder engine field is dropped, and a mixed field is sent with the literal text (WF:201-202).
11. **A tool `default` is baked at node entry.** A model-filled field whose name matches a variable already set becomes invisible to the model (TC:93, TC:99).
12. **No `{{` or `}}` in Python code.** Read values from `vars` (TC:494).
13. **Do not use the `system.*` dates.** They read the real clock; use the `now` call variable. There is no `{{current_date}}` (WF:240; HP §Overview:14).
14. **`test_variables` merges are documented for web calls only.** A passed call variable always wins (WF:209).
15. **Do not rely on `context_variables`.** It vanished on save without an error (WF:246).
16. **The top-level condition group must be `"logic": "or"`.** AND goes in a nested group (WF:331, WF:347).
17. **`equals` is a string compare.** Booleans need both `"true"` and `"True"`. Numbers like `"3.0"` will not equal `"3"`. A mismatch fails silently (WF:372; TC:286).
18. **`contains` ignores case; `equals` does not** (WF:296, WF:300).
19. **The first match wins.** List specific conditions first and deterministic before `matches_intent` (WF:395, WF:406, WF:681).
20. **"Deterministic first" can conflict with list order.** Never put a `matches_intent` and an `always` in the same node until this is settled (WF:406-407).
21. **Same-target transitions merge into one OR.** An `always` sharing a target with a conditional transition makes it unconditional (WF:408).
22. **No fallback when nothing matches.** The agent stays with the same prompt. Cover every realistic path (WF:412).
23. **Routing runs again right after a tool result, in the same turn.** A result-variable transition fires "before any further model turn", so words the prompt wanted said after the tool may never be spoken (WF:410; TC:291).
24. **Do not leave an action node on `matches_intent`.** The router reads the last user message and can leave before the tool was called. Use an extracted enum or a tool result (TC:317; SK:17).
25. **A trailing self-`always` blocks every global node** from that node (WF:400, WF:420, WF:488) [INFERRED].
26. **A vague `loop_condition` traps the call.** "The user has not finished" matches everything (WF:445).
27. **`routing_prompt` and `loop_prompt` have contradictory documentation** (WF:97 vs WF:416; WF:432 vs WF:398/WF:412). Avoid relying on them.
28. **A passthrough node without a matching transition deadlocks.** End it with `always` and set `passthrough_default_transition` to the same target (WF:466-467; TC:209, TC:315).
29. **An initial code node may be skipped on the chat route** (API:252), even though simulations run it (WF:484).
30. **Global nodes: exclude terminal nodes** (or they can loop) **and identity steps** (WF:523-524).
31. **Set `min_confidence` on every extraction item.** The 0.95 default silently discards values (WF:575).
32. **A custom `extraction_prompt` replaces the whole template.** Without the four `{{extractor.*}}` placeholders, extraction returns nothing every turn while everything else looks fine (WF:576).
33. **Declare dates as `type: "date"`**, or the model guesses the year. The built-in rules also turn "next week" into a date, which Brief A rule 21 forbids (WF:577-578; BRA:64).
34. **`{{date.*}}` placeholders only work inside `extraction_prompt`** (WF:582).
35. **The farewell comes from the terminal, not `on_enter`.** `message_mode: "none"` plus an `on_enter` line hangs up silently (WF:650).
36. **`endedReason` is the terminal's `function.name`, not the node name.** Name terminals after outcomes (WF:652).
37. **`interruptible` without `trigger_pattern_both`** lets every polite reply cancel the hangup. The window cannot be measured in chat (WF:654).
38. **`max_node_turns` without `max_turn_transition` does nothing.** It defaults to 10, has no "unlimited" value, and counts only user messages (WF:662-663, WF:672).
39. **`suppress_tool_results: true` hides the result from the model, not from routing.** Variables are still mapped (TC:341).
40. **A `pre_actions` mapping goes at node level.** Nested inside the pre-action, it is ignored. Paths start with `data.` (TC:244, TC:283).
41. **A tool call's HTTP success is not the bank's `ok`.** Business errors are HTTP 200 with `ok:false`. Route on `ok`, not on the success counter [PROBED-earlier RAT:144].
42. **A re-verify response can lack `all_verified`.** Routes must tolerate a missing key [PROBED-earlier RAT:153].
43. **Every path must reach an `end_call` node** (WF:680). BA breaks this rule. Do not copy its phrase-trigger ending (`trigger_pattern` is undocumented).
44. **BA's `close_call` enum lacks `paid` and `transferred`, and BA lacks three bank tools.** Generate both from the tool API file (BA:362-367; OAS:424-431; RM:72).
45. **A lifecycle tool with unresolved parameters is documented two ways**, dropped or model-filled. Make every parameter resolve (WF:202; TC:115 vs TC:561).
46. **What you export is what is scored**, after the platform has stripped fields. Read the stored workflow back before trusting it (RM:75; API:87).
