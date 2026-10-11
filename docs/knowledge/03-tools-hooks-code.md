# Chapter 3. Tools, parameters, hooks and code

How a Freya workflow calls HTTP APIs and runs Python: the tool object, how each parameter gets its value, results and the variables they create, routing on results, counters, retries, hooks, code nodes, lifecycle tools, and what the model does after a result.

Primary source: `kit/build-the-builder/docs/tools-and-code.md` (cited **TC:line**). It was re-read in full, line by line, for this chapter. The deep-read notes `knowledge/notes/tc-1.md` and `tc-2.md` were checked against it. Where a note and the source disagree, the source wins, and §22 lists those cases. No network calls were made.

---

## In short

- Every external action is one JSON **tool function** (TC:9). Its **placement** decides who fires it. In `pre_actions` on `api_request`/`code` nodes, the engine fires it on entry. In `tools` on `conversation` nodes, the dialogue model fires it when it decides to. In the workflow-level `tools` with `config.alwaysRunsAt`, the engine fires it at call start or end. An array in the wrong node type is **stripped without an error** (TC:147-153).
- **One key decides each parameter: `default`** (TC:80). A literal, or a `{{var}}` that has a value when the node is entered, is **baked** and hidden from the model. An unset `{{var}}`, or no `default`, makes the **model** fill it. `const` **never sends anything** (TC:82-93).
- An `api_call` result is an **envelope** `{status, data, message, status_code, header}`, where `data` is the API's JSON body (TC:250-262). You map it with **`data.`** paths: on the tool for `tools`, on the node for `pre_actions`. The engine also writes `<tool>_args.*`, `<tool>_response.*`, `<tool>_status_code` and success/failure counters by itself. **Booleans arrive as strings**, so test both `"true"` and `"True"` (TC:264-287).
- **Routing runs again right after a tool result**, in the same turn (TC:291). Every passthrough node must end with an `always` transition, or it deadlocks (TC:209, TC:315).
- `pre_process_code` and `post_process_code` are server-side Python hooks, honoured **only on `api_call`** (and the integration and knowledge-search handlers). The post-hook sees the envelope. Adding a `what_to_do_next` line to `result["data"]` fixes the agent's silence after a result and its habit of ignoring negative results (TC:367-416, TC:566-575).
- Code nodes run a `code_exec` snippet with a `vars` dict. Output reaches the workflow **only through `vars`**. The rules: no `{{` or `}}` in the code, never raise, string flags for routing. `json`, `re` and `datetime` are verified. The default timeout is 30 000 ms (TC:418-512).
- Lifecycle tools fire at `start_of_call` or `end_of_call`. `each_turn` never fires. At `end_of_call` no `response_mapping` is applied. A malformed lifecycle tool is dropped silently. An unresolved placeholder in one is "filled by one model call" (TC:514-564). Two other passages contradict that last rule (§5.3).
- Much is **undocumented**: what counts as a failure, the envelope on errors, what happens when a hook raises, the sandbox limits, and stale result keys. §23 lists each open point and how normal kit use could settle it.

---

## 0. Sources, labels and evidence grades

### 0.1 Citation keys

| Key | File |
|---|---|
| TC:n | `kit/build-the-builder/docs/tools-and-code.md`, line n |
| WF:n | `kit/build-the-builder/docs/workflow-format.md` |
| API:n | `kit/build-the-builder/docs/api.md` |
| BA:n | `kit/build-the-builder/examples/base-agent.json` |
| OA:n | `kit/build-the-builder/tools/openapi.json` (the bank's tool API) |
| PTS:n | `kit/build-the-builder/public-test-set.json` |
| SC:n | `kit/build-the-builder/tools/score.py` |
| FR:n | `kit/build-the-builder/freya.py` |
| SK:n | `kit/build-the-builder/.claude/skills/build-phone-agent/SKILL.md` |
| README:n | `kit/build-the-builder/README.md` |
| HP §Section (line n) | `research/hackathon-page.md`, the official hackathon page text |
| RAT:n | `research/read-api-and-testing.md`. Used **only** for facts an earlier agent obtained by live calls, labelled [PROBED-earlier] |

### 0.2 Labels

| Label | Meaning |
|---|---|
| [DOC] | Stated in the kit docs (TC, WF, API, OA, SK, README) or on the hackathon page |
| [DOC, verified] | TC or WF says "verified in a working builder" |
| [DOC, seen] | TC or WF says "seen in a trial call", or "seen in practice runs" |
| [CODE] | Read from kit code or JSON (BA, PTS, SC, FR) |
| [PROBED-earlier] | From earlier live calls recorded in RAT. Kept as they are. Not repeated |
| [INFERRED] | Reasoning from the cited facts |
| [UNCERTAIN] | No source settles it. The text says exactly what is unknown |

### 0.3 The doc's own evidence grades

- "Verified in a working builder" refers to "a builder that created a 6-node workflow through the REST API". That workflow "has code nodes, `api_call` tools, post-hooks and transitions on tool results", and "Its agent passed its practice cases" (TC:5). [DOC]
- "Seen in a trial call" means the statement comes from "the event log of a simulation call made with that builder" (TC:5). [DOC]
- **The working builder is not `examples/base-agent.json`.** [DOC]/[CODE]
  - BA is "an agent, not a builder", a two-step workflow that "passed 2 of the 13 practice customers" in one run (README:34). README:46 describes it as "two steps, four tools".
  - BA has no code nodes, no `post_process_code`, no `response_mapping` anywhere (BA:143, BA:318, and none on any tool) and no `what_to_do_next`.
  - Its only hook is the `pre_process_code` of `close_call` (BA:395).
  - So BA shows a valid shape, not the verified patterns.

### 0.4 Hackathon facts that constrain tools

| Fact | Label | Source |
|---|---|---|
| "Agent may call only the kit's tool API; a call to any other service fails the case." | [DOC] | HP §Rules (line 37) |
| "Do not probe or load-test the platform." | [DOC] | HP §Rules (line 37) |
| In the hidden briefs, "The seven tool names stay the same; their fields and allowed values can change." | [DOC] | HP §Overview (line 12) |
| "The phone agent gets the date/time of the call as variable `now`; every date rule uses it." | [DOC] | HP §Overview (line 14) |
| "calculations such as business days can run as code instead of being left to the model" | [DOC] | HP §Overview (line 15) |
| The scorer reads the bank's record, not what the agent says | [DOC] | HP §Data (line 20) |
| "The bank's API does not enforce the brief." Keeping the rules is the agent's job | [DOC] | HP §Evaluation (line 25); OA:6 |
| "The seven tool calls need no key: the customer_id in the body is the secret of one call." | [DOC] + [PROBED-earlier] | OA:6; RAT:94 |
| "Take every tool field and allowed value from `tools/openapi.json`." (example builder's skill) | [DOC] | SK:18 |
| "Move to the next step on a tool result, not on what the customer says." | [DOC] | SK:17 |
| "When a tool call fails, the agent must say so. It must never tell the customer something is recorded when it is not." | [DOC] | SK:29 |
| "Prefer rules in routes and code over rules in prompts." | [DOC] | SK:30 |
| Every phone agent runs on the same Freya model, `experimental-5` in the kit client | [DOC] + [CODE] | HP §Overview (line 14); FR:84 |

---

## 1. Where a tool lives, and who fires it

### 1.1 Placements

"The placement decides who fires the call." (TC:145) [DOC]

| Placement | Node type | Who calls it | When | Source |
|---|---|---|---|---|
| `pre_actions` | `api_request`, `code` | The engine | On node entry, before any model turn | TC:149 |
| `tools` | `conversation` | The dialogue model | During a turn, when the model decides to | TC:150 |
| Workflow-level `tools` with `config.alwaysRunsAt` | none | The engine | At call start or call end | TC:151 |
| `terminal` of an `end_call` node | `end_call` | The engine | When the node is reached | TC:64; WF:108; WF:613-635 |

- "The shape is the same wherever you attach it." (TC:9) [DOC]
- The fourth row is not in TC's placement table. The `end_call` handler is "Used in the `terminal` of an `end_call` node" (TC:64), and WF:622-635 shows the function object there. [DOC]
- BA also uses an `end_call`-handler tool inside a conversation node's `tools` (BA:67-102, BA:264-299). See §2.4. [CODE]

### 1.2 Silent stripping

- TC:153 [DOC]: "The platform removes `tools` from non-conversation nodes and `pre_actions` from conversation nodes. It does so without an error: the JSON you sent looks fine, the create call succeeds, and the stored node has an empty array. A node cannot use both."
- WF:79-84 states the same [DOC]:
  - `tools` is kept only on `conversation` nodes.
  - `pre_actions` is kept only on `api_request` and `code` nodes, "and the other non-conversation action types" (WF:82).
- The dry run behaves the same way. Validation "removes fields that do not belong to a node type without reporting them. For example `pre_actions` on a `conversation` node is dropped. Read a created workflow back if you are unsure what was stored." (API:87) [DOC]
- BA's conversation nodes carry `"pre_actions": []` (BA:115, BA:312), which is consistent with stripping. [CODE]

### 1.3 When to use which

- "**Use `pre_actions`** when the call must always run and the model has nothing to decide. Example: after the order number is known, always fetch the order." (TC:155) [DOC]
- "**Use `tools`** when the call depends on what the user says. Example: cancel the order only if the caller asks for it." (TC:157) [DOC]
- "To run a fixed call before a tool-driven conversation, use a passthrough `api_request` node and transition from it into the conversation node." (TC:169) [DOC]
- "Do not build a long chain of passthrough nodes for optional actions. Put those into one conversation node with several tools." (TC:169) [DOC]
- WF:84 says the same: "If a call must run before a conversation node, put it in its own `api_request` node in front." WF:684: "Keep related optional actions together in one conversation node with several tools." [DOC]

### 1.4 Behavioural differences (TC:161-167) [DOC]

| | `pre_actions` | `tools` |
|---|---|---|
| Can be skipped | No | Yes. "The model may not call it if the description and the prompt do not push for it" |
| Timing | Node entry | Inside a turn. "The model can call a tool, speak, then call another" |
| Result in the conversation | "A tool call and tool result pair is added to the history" | The same |
| `response_mapping` lives | On the **node** | On the **tool** |
| `description` | Ignored | "The only text the model reads about the tool" |

- [DOC] A `pre_actions` result enters the history as a tool-call/result pair: "A tool call and tool result pair is added to the history" (TC:165).
- [UNCERTAIN] Whether that pair is still in the history once the call moves to the next conversation node. When the conversation moves from node A to node B, WF:170 says only "User and assistant messages are kept." Tool-call/result pairs are not mentioned (WF:168-172). So the docs do not say whether a passthrough `api_request` node's raw result reaches the next conversation node's dialogue model. Chapter 02 also leaves this open (its Q25).
- [DOC] Only mapped variables are sure to carry over: "Variables also stay for the whole call" (WF:174).
- [DOC] `suppress_tool_results` is "A node-level boolean for nodes that run API calls" (TC:341). It belongs to the node that ran the call, here the passthrough `api_request` node, and not to the conversation node that follows (§12).
- [INFERRED] Design consequence: map everything the next node needs into variables. Do not rely on the raw `pre_actions` result being visible after the transition.
- [INFERRED] "The only text the model reads about the tool" refers to tool-level text. The parameter-level `description`, `type` and `enum` are also shown to the model for model-filled parameters (TC:85).

### 1.5 A full `pre_actions` node (TC:171-207) [DOC]

```json
{
  "name": "fetch_order",
  "node_type": "api_request",
  "passthrough": true,
  "passthrough_default_transition": "present",
  "on_enter": { "type": "silent" },
  "pre_actions": [
    {
      "type": "function",
      "config": { "timeoutMs": 10000, "maxRetries": 2 },
      "function": {
        "name": "get_order",
        "handler": "__function__:api_call",
        "description": "Get the order.",
        "parameters": {
          "type": "object",
          "properties": {
            "url": { "type": "string", "default": "https://api.example.com/v1/get_order" },
            "method": { "type": "string", "default": "POST" },
            "headers": { "type": "object", "properties": { "Content-Type": { "type": "string", "default": "application/json" } } },
            "body": { "type": "object", "properties": { "order_number": { "type": "string", "default": "{{order_number}}" } }, "required": [] }
          }
        }
      }
    }
  ],
  "response_mapping": [ { "path": "data.items", "variable": "items" } ],
  "transitions": [
    { "target_node": "present", "description": "always", "condition": { "operator": "always" } }
  ]
}
```

Points to notice:

- `response_mapping` is a **sibling of `pre_actions`**, at node level, and not inside the `pre_actions` entry (TC:244). [DOC]
- `description: "Get the order."` is present but ignored (TC:50). [DOC]
- "The last `always` transition is mandatory. A passthrough node with no matching transition deadlocks." (TC:209) [DOC]
- The node has **both** `passthrough_default_transition: "present"` and an `always` transition to `present`. [INFERRED] So `passthrough_default_transition` alone does not prevent the deadlock. Set both. WF:466-467 requires both too. [DOC]
- WF's passthrough rules (WF:464-468) [DOC]:
  - The node routes right after its entry actions.
  - Set `passthrough_default_transition` to the next node.
  - End `transitions` with `always`.
  - Set `on_enter` to `{"type": "silent"}` "or to a short fixed line that covers the wait".

### 1.6 What the dialogue model can call

- "The dialogue model can call only the tools in the current node's `tools` array. Everything else (API calls on entry, code, ending the call) is run by the workflow engine." (WF:35) [DOC]
- The dialogue call sees `system_prompt`, `role_message`, `task_message`, the full conversation history and the node's `tools` (WF:30). [DOC]
- Routing and extraction are separate model calls that "do not share a prompt" (WF:15). [DOC]

---

## 2. The tool function object

### 2.1 Canonical example (TC:11-43) [DOC]

```json
{
  "type": "function",
  "config": { "timeoutMs": 10000, "maxRetries": 2 },
  "function": {
    "name": "lookup_order",
    "handler": "__function__:api_call",
    "description": "Look up one order. CALL it when the caller asks about a specific order.",
    "parameters": {
      "type": "object",
      "properties": {
        "url": { "type": "string", "default": "https://api.example.com/v1/orders/lookup" },
        "method": { "type": "string", "default": "POST" },
        "headers": {
          "type": "object",
          "properties": { "Content-Type": { "type": "string", "default": "application/json" } }
        },
        "body": {
          "type": "object",
          "properties": {
            "customer_id": { "type": "string", "default": "{{customer_id}}" },
            "order_number": { "type": "string", "description": "Order number, digits only", "default": "{{order_number}}" }
          },
          "required": ["order_number"]
        }
      }
    }
  },
  "response_mapping": [
    { "path": "data.status", "variable": "order_status" }
  ]
}
```

What the example implies [INFERRED]:

- `url`, `method` and `Content-Type` are literal defaults, so they are baked.
- `customer_id` is baked if a `customer_id` variable exists at node entry.
- `order_number` is model-filled if no `order_number` variable exists at node entry.
- Nesting goes two levels deep: `parameters.properties.headers.properties.<Header>` and `parameters.properties.body.properties.<field>`.
- `required` sits **inside `body`**, not at the `parameters` level.
- `response_mapping`, `pre_process_code` and `post_process_code` are top-level siblings of `function` and `config` (TC:243, TC:369).

### 2.2 Field table (TC:45-58) [DOC]

| Field | Meaning (as stated) |
|---|---|
| `type` | Always `"function"` |
| `function.name` | Tool name. "The model calls it by this name. Result variables are named after it" |
| `function.handler` | Which runtime executes the tool |
| `function.description` | "Read by the dialogue model when the tool is in `tools`. Ignored in `pre_actions`" |
| `function.parameters` | JSON-schema object. `properties` holds the parameters |
| `config.timeoutMs` | "Timeout of one attempt, in milliseconds". Default not documented (TC:351) |
| `config.maxRetries` | "Tool-level retries of a failed call". Default not documented (TC:352) |
| `config.interruptible` | "`false` makes the tool run in the background" (§13) |
| `config.alwaysRunsAt` | "Makes the tool a lifecycle tool" (§17) |
| `response_mapping` | "Tool level, for tools in `tools`. Maps the result to variables" (§8) |
| `pre_process_code` | "Python hook that runs before the call" (§15) |
| `post_process_code` | "Python hook that runs after the call" (§15) |

### 2.3 Handlers (TC:60-66) [DOC]

| Handler | Runs |
|---|---|
| `__function__:api_call` | An HTTP request |
| `__function__:code_exec` | A Python snippet in a sandbox |
| `__function__:end_call` | Hangs up. "Used in the `terminal` of an `end_call` node" |

- "Handlers for integrations, knowledge search, call transfer and rescheduling also exist. They are not needed here." (TC:66) [DOC]
- WF:77 lists the other node types that exist: `transfer_call`, `integration`, `knowledge_base`, `reschedule_call`, `invoke_agent` and `exit`. [DOC]

### 2.4 `end_call` as a model tool (BA only) [CODE]

TC documents `end_call` only in a `terminal`. BA also lists it in both conversation nodes' `tools` (BA:67-102, BA:264-299):

| Parameter | Default in BA | Documented? |
|---|---|---|
| `message_mode` | `"none"` | Yes, WF:641: `custom`, `llm` or `none` |
| `interruptible` | `true` | Yes, WF:644: "`true` opens a short window after the farewell in which the user can still speak" |
| `trigger_pattern` | `"Have a good day\|have a good day"` | **No.** Undocumented [UNCERTAIN] |
| `trigger_timeout` | `3` | Yes, WF:645: "Length of that window in seconds" |
| `trigger_pattern_both` | `"goodbye\|bye\|have a good day\|you too\|thank you\|thanks\|take care"` | Yes, WF:646: farewell phrases "that do not cancel the close" |

- `config` is `{timeoutMs: 10000}`, with no `maxRetries` (BA:69-71, BA:266-268).
- The description reads: "Ends the call. You normally do NOT call this: the phrase \"Have a good day.\" ends the call by itself. Call it without any text only if the customer answers after your goodbye." (BA:100, BA:297).
- [INFERRED] from that description: `trigger_pattern` makes the agent's own phrase "Have a good day" end the call automatically. Not documented anywhere.
- [INFERRED] A call's `endedReason` is the terminal's `function.name` (WF:652; API:310). With this tool form, the name would presumably be `end_call`. Not stated.
- WF rules for `end_call` (WF:650-656) [DOC]:
  - "The farewell comes from the terminal, not from `on_enter`."
  - "If you set `interruptible`, also set `trigger_pattern_both`. Without a phrase list every polite reply cancels the hang-up."
  - The window "is timed on a wall clock and a chat simulation cannot measure it."

### 2.5 `api_call` parameters (TC:68-76) [DOC]

| Parameter | Meaning |
|---|---|
| `url` | Request URL. "`{{var}}` works" |
| `method` | HTTP method |
| `headers` | Object. "Each header is a property with a `default`" |
| `body` | Object. "Each body field is a property under `body.properties`" |
| `connect_retries` | Transport retries (§14.2). A baked parameter, **not** a `config` field (TC:363) |

- "**Use `default` for fixed backend config** such as `url`, `method` and auth headers." (TC:91) [DOC]
- The bank's seven tools need **no** auth header (OA:6). [DOC]
- Two TC examples declare no `headers` at all: the hook example (TC:382-384) and the lifecycle example (TC:540-547). [UNCERTAIN] Whether `Content-Type: application/json` is sent by default when no header is declared. BA declares it on every `api_call` tool.

---

## 3. How a parameter gets its value ("baking")

### 3.1 The decision table (TC:80-87) [DOC]

"One key decides, per parameter: `default`."

| Declaration | Who supplies the value | Does the model see the parameter |
|---|---|---|
| `default` with a literal, or with a `{{var}}` that has a value | The workflow. The value is **baked** | No |
| `default` with a `{{var}}` that has no value when the node is entered | The model | Yes, **named after the variable**, with the property's `type`, `description` and `enum` |
| no `default` | The model | Yes |
| `const` | Nobody. `const` does **not** bake | It only constrains the model's own output |

### 3.2 Rules and mechanism (TC:91-93) [DOC]

- The mechanism: "At registration the engine moves every `default` into the tool's base config, resolves `{{var}}` from the variable table, and removes the field from the schema the model sees." (TC:91)
- "**Never use `const` for a value you want sent.** The engine reads only `default`." (TC:92)
  - "A `{{var}}` inside a `const` never resolves."
  - "An `api_call` whose `url` is a `const` fails with "URL is required"."
- "**Baking happens when the node is entered.** A `{{var}}` default is resolved against the variable table at that moment." (TC:93)
- Exceptions to "at node entry", by placement [DOC]:
  - For a `code_exec` **tool** in `tools`, "the `code` field resolves `{{var}}` when the tool is called" (TC:512).
  - Lifecycle tools [UNCERTAIN]. TC:561 states only the fallback: "If a `{{var}}` parameter is still unresolved, one model call fills the parameters. If everything resolves, the handler runs directly." It does **not** say when a lifecycle tool's placeholders are resolved. It could be when the tool fires, at registration ("At registration the engine moves every `default` into the tool's base config, resolves `{{var}}` from the variable table", TC:91), or at some other moment.
  - [INFERRED] Fire time is the likely reading. TC:563 says the order is "call analysis, then `end_of_call` tools", and that an `end_of_call` tool "can use `{{call.analysis.summary}}`" and the other `call.*` values. Those values exist only after call analysis. This is not stated outright.
  - Why it matters: an `end_of_call` tool must bake values that are set late in the call, such as the outcome. If resolution happened earlier, those values would be missing, and the model fill of TC:561 would supply them instead.

### 3.3 The working builder's pattern (TC:95) [DOC, verified]

- `customer_id` has `"default": "{{customer_id}}"` and is baked from a call variable.
- "Every other body field has `"default": "{{<field name>}}"`, where no variable of that name exists, so the model fills it."
- BA follows the same pattern [CODE]:
  - `verify_identity`: `field` → `{{field}}`, `answer` → `{{answer}}`, `customer_id` → `{{customer_id}}` (BA:29-46).
  - `create_promise`: `date`, `amount`, `product_id` and `customer_id`, each defaulting to its own placeholder (BA:225-243).

### 3.4 Where the model's arguments are stored (TC:97) [DOC, seen]

- "the model's arguments are stored as `<tool>_args.<field>` in the variable table, for example `lookup_order_args.order_number`. They were not stored under the bare field name."
- This comes from one trial call. [UNCERTAIN] It is not stated whether `<field>` is the property key or the placeholder's variable name, because they were identical in the example. Also unknown: whether baked fields appear under `_args` too (TC:268 says "Each argument the model sent").

### 3.5 The name-collision trap (TC:99) [DOC]

"Take care that a model-filled field does not share its name with a variable that is already set when the node is entered. The value would be baked and the model would never see the parameter."

[INFERRED] Consequences:

- **All variables are call-wide and never cleared.** "All variables live in one table for the whole call. There is no per-node scope. A variable is never cleared on a transition. A later write with the same name overwrites it." (WF:178) [DOC]
  - So once any extraction, mapping, code snippet or call variable writes a name, every later node that uses `{{that_name}}` as a default bakes it.
- **A literal `default` always hides the parameter.** You cannot offer the model a "suggested default". A literal means "baked".
- **The model-visible name comes from the placeholder, not the property key** (TC:85). With `body.properties.day` and `default: "{{wanted_day}}"`, the model would see a parameter called `wanted_day`.
  - [UNCERTAIN] Under which key the value is then sent.
  - The safe pattern is to keep the key and the placeholder identical, as the working builder does (TC:95).
- To control a field you have exactly two levers:
  - **Bake it:** make sure the variable is set *before* the node is entered.
  - **Let the model fill it:** make sure no variable of that name is set at entry.

### 3.6 Substitution forms and formatting (from WF) [DOC]

| Form | Result | Source |
|---|---|---|
| `{{customer_name}}` | "The value as a string" | WF:195 |
| `{{amount:json}}` | "The value JSON-encoded. Use it inside request bodies" | WF:196 |

- `{{var}}` works in "prompts, `on_enter.text`, transition descriptions, URLs, headers and request bodies" (WF:191). [DOC]
- "Date values are formatted for speech in the agent's language when they are substituted into a prompt." (WF:200) [DOC]
  - [UNCERTAIN] Whether a date-typed variable is also reformatted when baked into a request body. WF's own example bakes the date-typed extracted `wanted_day` (WF:705) into a body as `"day": "{{wanted_day}}"` (WF:754), but the format that was sent is not stated.
  - [INFERRED] For bank fields that require `YYYY-MM-DD`, an ISO string computed in code is the safer source.
- [UNCERTAIN] For a `type: number` leaf with a baked `"{{x}}"`, it is unknown whether the value goes out as a JSON number or as a string.
  - [PROBED-earlier] The bank accepted a string amount `"220"` (RAT:156).
  - [CODE] The scorer compares amounts as `round(float(p["amount"]), 2)` (SC:21), so a numeric string scores the same as a number.
- Call variables are readable "as `{{customer_id}}` in prompts and tool parameters, and as `vars.get("customer_id")` in code". This is verified in a working builder (WF:221). [DOC, verified]
- "No `null` values. The schema is strict." A `null` fails validation (WF:64). [DOC]
  - [CODE] BA, which is the workflow as stored in the workspace (README:34), does contain node-level nulls such as `"max_turn_transition": null` (BA:145). [UNCERTAIN] Whether the platform's stored form differs from what create accepts. Do not write `null` in tool JSON.

### 3.7 Open points on baking [UNCERTAIN]

- Whether `""` counts as "has a value" for a **model-called** tool, which would bake the field empty and hide it. TC:115 treats `""` as a value for engine-run calls: "The field is sent empty".
- What happens when a placeholder's variable gets set **during** the node, for example by extraction, after the parameter was offered to the model.
- Whether re-entering a node re-bakes.

---

## 4. `api_call` body fields

### 4.1 Rules (TC:101-107) [DOC]

- "Declare each body field as a leaf under `body.properties.<field>`." (TC:103)
- "Put the field's `type`, `description` and `enum` on that leaf. Put required fields in `body.required`." (TC:104)
- "Give each leaf its own `default`." (TC:105)

### 4.2 The `body.default` anti-pattern

- "Do not put a field spec at the top level of `parameters.properties` next to a `body.default` template object." (TC:106) [DOC]
  - "The engine looks for the spec at `body.properties.<field>`, does not find it, and the model sees only "Template variable: name"."
  - "The `enum` and `description` are lost **while the call still works**." So the failure is **silent**.
- "A body that exists only as one `body.default` object also shows as an empty form in the dashboard editor. Saving from there removes the tool." (TC:107) [DOC]
- [UNCERTAIN] Whether "name" in "Template variable: name" is literal text or the variable's name. It does not matter if `body.default` is never used.

### 4.3 `code_exec` parameters differ

"A `code_exec` tool is different: its parameters are true top-level arguments. Declare a model-filled one as a top-level property without `default`." (TC:109) [DOC]

### 4.4 `required`, as BA uses it [CODE]

- `verify_identity`: `required: ["field","answer"]`, without the baked `customer_id` (BA:24-27).
- `create_promise`: `required: ["product_id","amount","date"]`, without `customer_id` (BA:219-223).
- `get_account`: `required: []` (BA:175).
- `close_call` (lifecycle): `required: ["outcome"]` (BA:352-354).
  - `outcome` defaults to `{{outcome}}`, but nothing in BA ever sets it (§17.6). So it is effectively model-filled at end of call.
- [UNCERTAIN] Whether listing a field in `required` has any effect when the field is baked. [INFERRED] The working convention is that `required` lists the model-filled fields.

---

## 5. When a baked variable has no value

### 5.1 TC's table (TC:111-116) [DOC]

| Field type | Variable unset | Variable is `""` |
|---|---|---|
| Normal field in an engine-run call (`pre_actions`, lifecycle tool) | "The field is dropped from the request. No error" | "The field is sent empty" |
| `code` of `code_exec` | "The literal text `{{var}}` stays in the Python source and the snippet crashes" | *(cell empty: not documented)* |

- TC:118, the fix [DOC]: "make sure an earlier node always sets the variable, even to a sentinel value. In code, read variables from `vars` and do not splice them in with `{{var}}`."
- [INFERRED] The table covers **engine-run** calls. For a model-called tool in `tools`, an unset placeholder means "the model fills it" (TC:85), not "dropped".

### 5.2 WF refines "dropped" (WF:201-203) [DOC]

- "In a field of an engine-run call (a `pre_actions` call or a lifecycle tool) an unresolved placeholder behaves in two ways":
  - "If the value is exactly one placeholder (`"{{x}}"`), the whole field is dropped from the request."
  - "If the value mixes text and a placeholder (`"Status: {{x}}"`), the request goes out with the literal `{{x}}` in it."
- "Do not reference a variable in a mixed value unless an earlier node always sets it." (WF:203)
- Prompts behave differently: "An unresolved variable in a prompt stays as the literal text `{{variable_name}}`. The model sees the placeholder. In a fixed spoken line (`on_enter.text`, a terminal `spoken_message`) the agent says it aloud." (WF:201)
- [INFERRED] TC:115 and WF:202 conflict only on mixed values. WF:202 is the more precise rule, so follow it.

### 5.3 The lifecycle-tool contradiction

| Passage | Says | Source |
|---|---|---|
| TC:115 | An unset variable in a lifecycle tool field is "dropped from the request. No error" | [DOC] |
| WF:202 | Same for "a lifecycle tool": an exact placeholder is dropped | [DOC] |
| TC:561 | "If a `{{var}}` parameter is still unresolved, one model call fills the parameters. If everything resolves, the handler runs directly." | [DOC] |

[INFERRED] Evidence from BA favours TC:561, at least for BA's `close_call`:

- BA never sets `outcome` or `reason`:
  - no `extraction_schema` (BA:144, BA:319);
  - no `response_mapping` (BA:143, BA:318);
  - no code nodes;
  - neither name is in `test_variables` (BA:401-406).
- Yet BA passed 2 of 13 cases (README:34).
- A pass requires the ledger outcome to equal the expected one (SC:20) and `close_call` to be the last ledger call (SC:29).
- Only a model fill could have produced a valid `outcome`.
- This is reasoning, not a documented verification. Which model does the fill, and what context it sees, are both unknown (§23).

---

## 6. Constraining model-filled parameters

### 6.1 Options (TC:120-126) [DOC]

"When a value must be one of a known set, do not use a free string. The model sometimes invents a value that looks plausible." (TC:122)

1. "Use an `enum` on the leaf, and list the values in the `description` as well." (TC:124)
2. "Or use a `number` that is an index into a list, with the valid range in the description. A pre-hook or the backend turns the index into the real value." (TC:125)
3. "If neither is possible, name the exact source in the description and tell the model to copy the value unchanged." (TC:126)

### 6.2 Example (TC:128-141) [DOC]

```json
{
  "type": "object",
  "properties": {
    "queue": {
      "type": "string",
      "description": "Team that takes over. One of: billing, delivery, returns.",
      "enum": ["billing", "delivery", "returns"],
      "default": "{{queue}}"
    }
  },
  "required": ["queue"]
}
```

[INFERRED] This bare object schema plays the role of the `body` object of an `api_call` (TC:103).

### 6.3 Hackathon specifics

- [INFERRED] The bank API is fixed, so a pre-hook is the only place to turn an index into a real value.
- The real `transfer_to_agent.queue` enum is `restructuring`, `general`, `support` (OA:369-373). [DOC]
- Fields and enums can change in the hidden briefs (HP §Overview, line 12). [DOC]
- The bank **enforces** enums [PROBED-earlier]:
  - `add_note` and `transfer_to_agent` reject unknown values with `"unknown reason"` and `"unknown queue"` (RAT:157).
  - `close_call` rejects an unknown outcome with `"unknown outcome"` (RAT:159).
- [CODE] BA's `close_call.outcome` enum is `promise`, `no_promise`, `not_verified`, `not_reached` (BA:362-367). The tool API's enum also has `paid` and `transferred` (OA:424-431). BA's own pre-hook tests for `'paid'` (BA:395) although its enum omits it.
  - BA is stale against the tool API file. Take values from the tool API file (SK:18).
- [UNCERTAIN] Whether the engine enforces `enum`, or `const`, on the model's output. TC:87 says `const` "only constrains the model's own output". Whether an out-of-enum value is blocked or sent is not stated.

---

## 7. Tool descriptions, prompts and availability

### 7.1 Description rules (TC:211-217) [DOC]

- "In `tools`, the `description` decides whether the model calls the tool." (TC:213)
- "Write it as an instruction with the trigger: "CALL it every time the caller gives an order number."" (TC:215)
- "A plain description such as "Looks up an order" lets the model acknowledge the request in words and never call the tool. That is the most common failure of nodes with many tools." (TC:216)
- "If two tools could match, say which one not to use and name the other." (TC:217)

### 7.2 Prompt rules [DOC]

- "In `task_message`, put the tool rules before long reference text and state: when a rule says to use a tool, call the tool." (TC:218)
- The working builder "tells the model to call one tool per message and to speak after every tool result" (TC:219). [DOC, verified]
- "If the node has tools, refer to them by name and say when to call them. Do not repeat the tool descriptions." (WF:141)
- "In a node without tools, state that no tool call is allowed in this turn. If the node has a `loop_prompt`, put that rule in both prompts." (WF:142)
- "after every tool result, speak to the customer or call the next tool. Never end a turn with nothing." (TC:575)

### 7.3 Availability and error strings

- "a model turn with no text and no tool call produced the error event "The model returned no speakable content"." (TC:219) [DOC, seen]
- "A tool is available only in the nodes that list it." (TC:221) [DOC]
- "the model called a tool that the current node did not list. The result was the text "The function `<name>` is not currently available."" (TC:221) [DOC, seen]
  - [INFERRED] The model probably saw that tool's name earlier in the history, for example in an earlier node. History persists across nodes (WF:168-174).

### 7.4 Description wording, compared

| Source | Description | Style |
|---|---|---|
| TC:18 | "Look up one order. CALL it when the caller asks about a specific order." | Trigger in capitals |
| TC:378 | "Check one answer. CALL it every time the caller answers the question." | Trigger in capitals |
| WF:781 | "Book one slot. CALL it only after the caller confirmed the read-back." | Trigger and precondition |
| WF:773 (prompt) | "...Then CALL book_appointment. Saying that it is booked is not enough. After the tool result, tell the caller whether the booking worked and say goodbye." | Prompt-side reinforcement |
| BA:64 | "Check one security answer. Call it once for each answer the customer gives." | Plainer [CODE] |
| BA:198 | "The customer's late products. Call it once, before you say anything about the account." | [CODE] |
| BA:261 | "Record a payment promise. Call it only after the customer said yes to the read-back of amount and date." | [CODE] |
| TC:216 | "Looks up an order" | **Anti-example** |

---

## 8. `response_mapping`

### 8.1 Shape (TC:223-239) [DOC]

"`response_mapping` copies values from a call result into named variables. It needs no model call." (TC:225)

```json
{
  "response_mapping": [
    { "path": "data.status", "variable": "order_status" },
    { "path": "data.items", "variable": "items" }
  ]
}
```

| Field | Meaning |
|---|---|
| `path` | "Dot path into the tool result" |
| `variable` | "Name of the variable to set" |

No other item fields are documented.

### 8.2 Placement (TC:241-246) [DOC]

- For a tool in `tools`: "inside the tool object, next to `function` and `config`."
- For `pre_actions`: "at the **node level**. A `response_mapping` nested inside a `pre_actions` entry is ignored and the variable never appears."
- "`extraction_schema` follows the same placement rule if you use it on a call result."
  - TC never describes how extraction runs on a call result. WF:609 says: "Use extraction for user speech. For API responses use `response_mapping` ... It is deterministic and needs no model call."
- For `start_of_call` lifecycle tools, mapping is applied. For `end_of_call` it is not (TC:562).

### 8.3 Which paths work (TC:281-285)

| Statement | Label | Source |
|---|---|---|
| "**Start the path at the envelope, with `data.`**". For a body `{"ok": true}` map `data.ok`; for `{"products": [...]}` map `data.products`. Verified on a tool-level **and** a node-level mapping | [DOC, verified] | TC:283 |
| A path without `data.` (`ok` for the same body) "is not confirmed". "A smaller example builder uses it." In an early trial call the mapped variables stayed unset and the transitions on them never fired, but "The mapping paths of that call are not recorded." "The builder that passed uses `data.` paths." | [DOC] | TC:284 |
| "The flattened key can be used directly as a transition variable: `check_answer_response.data.verified`." The working builder "tests the mapped variable and the flattened key in the same OR group as a safeguard." | [DOC, verified] | TC:285 |
| "Mapping paths still start with `data.` when a post-hook is present." | [DOC, verified] | TC:412 |

- [INFERRED] The early trial's failure **cannot** be blamed on bare paths, because its paths are not recorded. The safe fact is that `data.` paths are verified and bare paths are unconfirmed.
- [INFERRED] The "smaller example builder" is probably the old `examples/minimal_builder.py`, which v2 replaced (README:6).

### 8.4 Booleans, numbers and lists

- "Booleans arrive as strings. The trial call showed `true` in lower case in the flattened keys. Test both `"true"` and `"True"`, or map a string field." (TC:286) [DOC, seen]
- "`equals` compares strings. A boolean can arrive as `"True"` or as `"true"`, depending on how it was written into the table. A mismatch fails silently: the branch never fires and nothing reports an error." (WF:372) [DOC]
- "A mapped list or object: the exact form it has later inside `vars` is not confirmed. The working builder reads it defensively. It accepts a list, a JSON string, and flattened keys." (TC:287) [DOC]
- [UNCERTAIN]
  - Whether a **mapped** boolean is stored as `"true"` or `"True"`. Only the flattened keys were seen, in lower case.
  - Whether numbers such as `attempts_left: 3` are stored as strings.
  - How arrays are flattened, for example whether indexed keys like `…data.products.0.product_id` exist.

### 8.5 A path that is missing in the response [UNCERTAIN]

- TC does not say what a mapping does when its path is absent. It might leave the variable untouched, unset it, or set it empty.
- [INFERRED] WF's complete example relies on "absent → not set". It maps `data.booking_id → booking_id` (WF:800-802) and leaves the node on `booking_id is_set` (WF:808).
- Combined with "never cleared" (WF:178), a value mapped by an **earlier** call would survive a later call that lacks the path.

---

## 9. The result envelope and the automatic variables

### 9.1 The envelope (TC:248-262) [DOC, seen]

```json
{
  "status": "success",
  "data": { "ok": true, "verified": true, "attempts_left": 3 },
  "message": "Successfully executed POST request",
  "status_code": 200,
  "header": { "Content-Type": "application/json" }
}
```

- "`data` is the JSON body the API returned. `header` holds the HTTP response headers." (TC:262) [DOC]
- [INFERRED] The `message` text probably embeds the method, for example "…GET request".
- [UNCERTAIN] Only the **success** envelope is documented. The `status`, `data`, `message` and `status_code` on an HTTP 500, a 404, a timeout or a connection failure are not.

### 9.2 Automatically written variables (TC:264-277) [DOC, seen]

"The engine also writes every result into the variable table by itself, flattened with dots. You do not need a mapping for these." (TC:264)

Below is the table for a tool `check_answer` whose API returned `{"ok": true, "verified": true, "attempts_left": 3}`:

| Variable | Value |
|---|---|
| `check_answer_args.<field>` | "Each argument the model sent" |
| `check_answer_response.status` | `success` |
| `check_answer_response.data.ok` | `true` **(a string)** |
| `check_answer_response.data.verified` | `true` **(a string)** |
| `check_answer_response.data.attempts_left` | `3` (string or number not stated) |
| `check_answer_response.message` | `Successfully executed POST request` |
| `check_answer_response.status_code` | `200` |
| `check_answer_response.header.<Header-Name>` | One variable per response header |
| `check_answer_status_code` | `200` |
| `check_answer_success_count` | "Number of successful calls so far" |

- There is **no `check_answer_failure_count`** in this seen table, although TC:321 promises two counters per call target (§11). [UNCERTAIN]
- Each variable-table entry has `value`, `confidence`, `source` and `source_node` (API:334). [DOC]

### 9.3 Overwriting and staleness

- "Each call of the same tool overwrites the previous `_args` and `_response` values." (TC:279) [DOC]
- [UNCERTAIN] Whether a later call whose response **lacks** a key clears the old flattened key, or only overwrites the keys present.
  - This matters in practice. [PROBED-earlier] One re-verify of an already-verified field "returned no `all_verified` key at all" (RAT:153).
- Variables are never cleared on a transition (WF:178). [DOC]

### 9.4 Naming by placement (consolidated)

| Placement | `_args` | `_response.*` and `_status_code` | Counters | Evidence |
|---|---|---|---|---|
| Model-called `api_call` in `tools` | `<tool>_args.<field>` (TC:97, TC:268) | `<tool>_response.*`, `<tool>_status_code` (TC:269-276) | `<tool>_success_count`, `<tool>_failure_count` (TC:326) | success_count [DOC, seen]; failure_count [DOC] only |
| `api_call` in `pre_actions` of an `api_request` node | [UNCERTAIN] | [UNCERTAIN]: named after the node or the tool? | `<nodeId>_success_count`, `<nodeId>_failure_count` (TC:325) | [DOC], not seen for this node type |
| `code_exec` in a `code` node | n/a | `<node>_response.*`, `<node>_status_code` (TC:483-487) | `<node>_success_count` (TC:488) | [DOC, seen] |
| `code_exec` as a tool | [UNCERTAIN] | [UNCERTAIN] | [UNCERTAIN] | TC:512 |
| Lifecycle tool | [UNCERTAIN] | [UNCERTAIN] | [UNCERTAIN] | TC:562 says only that `end_of_call` has no mapping |

- "For a code node the automatic keys are named after the **node**, not after `code_exec`." (TC:490) [DOC]
- WF's complete example routes on `find_slots_failure_count` (WF:766). There the node and its `pre_actions` tool are **both** named `find_slots` (WF:729, WF:741), so the example cannot show which name the engine uses. [DOC]/[INFERRED]
- [INFERRED] Give a `pre_actions` node and its single tool the same name. The question then does not arise.
- [INFERRED] `<nodeId>` presumably means the node key. WF:90 says to use the same value for `name` and the key, so keep them identical.

### 9.5 Business errors arrive as HTTP 200 (hackathon bank)

- "`ok` is false when the action was not carried out." This is the 200-response description of every bank tool (OA:51, OA:112, OA:208, OA:275, OA:331, OA:386, OA:448). [DOC]
- Business errors come back as HTTP 200 with `ok:false`. The only exceptions are unknown `customer_id` (404) and key errors (401) (RAT:144). [PROBED-earlier]
- [INFERRED] An `ok:false` answer therefore very likely yields `status: "success"`, `status_code: 200` and a success-count increment. Routing must test `data.ok` and the other body fields, not only `status` or the counters.

### 9.6 How to see what actually happened [DOC]

- `function_call_start` carries `function` and `args`. "For an `api_call` the args are the full request: `url`, `method`, `headers`, `body`" (API:327). This is the way to see what was baked.
- `function_call_complete` carries `function` and `result` (API:328).
- `route_evaluated` carries `matched`, `from_node`, `target`, `reason`, "a `branches` list with the result of every condition, and `variable_table` with all variables at that moment" (API:329).
- User and assistant messages carry `workflowSnapshot.variableTable` (API:334).
- "To check whether a variable arrived, read `variable_table` or `variableTable`. Finding the variable's name in a prompt or in a code body proves nothing about its value." (API:336)
- The practice ledger records `calls[{n, tool, args, status, result}]` and `failures{tool: n}` (RAT:139-140). [PROBED-earlier]

---

## 10. Routing on tool results

### 10.1 The same-turn rule

- "Routing runs again after a tool result arrives. A transition on a result variable fires in the same turn, before any further model turn. Seen in a trial call." (TC:291) [DOC, seen]
- "Routing also runs after a tool result arrives. Verified in a working builder: a transition on a variable that a tool's `response_mapping` sets fires in the same turn, without a further user message." (WF:410) [DOC, verified]
- This extends the general rule that routing runs "After each user message" (WF:395).

### 10.2 Example (TC:293-311) [DOC]

```json
{
  "transitions": [
    {
      "target_node": "load_order",
      "description": "The check passed",
      "condition": {
        "logic": "or",
        "conditions": [
          { "variable": "check_passed", "operator": "equals", "operand": "true" },
          { "variable": "check_passed", "operator": "equals", "operand": "True" },
          { "variable": "check_answer_response.data.verified", "operator": "equals", "operand": "true" },
          { "variable": "check_answer_response.data.verified", "operator": "equals", "operand": "True" }
        ]
      }
    }
  ]
}
```

- The mapped variable (`check_passed`) and the flattened key are ORed, and each is tested in both spellings. The operands are **strings**.
- [CODE] BA's only transition tests **only** the flattened key `verify_identity_response.data.all_verified`, against `"true"` and `"True"` (BA:116-137). Each of its conditions carries an extra `"mode": "exact"` key (BA:122, BA:128), which neither TC nor WF documents.

### 10.3 Rules (TC:313-317) [DOC]

1. "On a passthrough node, end with an `always` transition so that a failed or empty response does not deadlock." (TC:315)
2. "Use a tool result to leave a conversation node." The pattern "a closing tool sets a variable, a transition on that variable leads to an `end_call` node" is verified in a working builder. (TC:316) [DOC, verified]
3. "To leave a node that carries out an action, do not re-test the user's earlier intent with `matches_intent`. The router looks at the latest user message and can route away before the tool was called. Extract a follow-up enum with a default such as `stay`, and branch with `equals`." (TC:317)

### 10.4 Operator semantics needed here (WF:294-311) [DOC]

| Operator | True when |
|---|---|
| `equals` | `str(value) == str(operand)` |
| `not_equals` | The inverse of `equals` |
| `greater_than` | `float(value) > float(operand)` |
| `less_than` | `float(value) < float(operand)` |
| `contains` | `operand` is a substring of the value, ignoring case |
| `is_set` | "The variable has any value" |
| `is_not_set` | "The variable has no value" |
| `always` | Always |
| `matches_intent` (semantic) | The routing model judges that "the user's last message matches the description" |

- The top-level group always uses `"logic": "or"`. For AND, nest a group inside it, and "Never put `"logic": "and"` at the top level." (WF:331, WF:347)
- "`greater_than` and `less_than` convert both sides to numbers, so `2` and `"2"` behave the same. Use them for counters." (WF:391)
- "Deterministic conditions are evaluated first. If one matches, no routing model call is made." (WF:407)
- Transitions with the same `target_node` are merged at load time into one OR. If any one of them is unconditional, the merged transition is unconditional (WF:408).
- "When nothing matches, there is no fallback. The agent stays and answers from the same `task_message`." (WF:412)

### 10.5 Tool-call transitions (related mechanism) [DOC]

- With `is_tool_call: true`, "The dialogue model then sees the transition as a tool named `transition_to_<node>` and triggers it by calling that tool. The router does not evaluate it after each turn." (WF:449)
- "The agent can acknowledge and move in the same message. The target node's `on_enter` then asks the next question." (WF:460)

### 10.6 Who speaks after a result-driven transition [UNCERTAIN]

- TC:291 does not say whether text the model produced in the same turn as the tool call is spoken.
- A model "can call a tool, speak, then call another" (TC:164).
- The target node's default `on_enter` is `{"type": "llm"}` (WF:94, WF:159), so it normally speaks unless it is set to `silent`. [DOC]
- BA's target node `collection` uses a fixed `tts` line (BA:301-304). [CODE]
- Also unknown: whether the post-result routing pass re-evaluates `loop_condition`, global nodes and `matches_intent`. If it does, `matches_intent` would be judged again on the same last user message.

---

## 11. Success and failure counters

- "The engine keeps two integer variables per call target. No mapping is needed." (TC:321) [DOC]

| Placement | Variables | Source |
|---|---|---|
| `pre_actions` node | `<nodeId>_success_count`, `<nodeId>_failure_count` | TC:325 |
| Tool in `tools` with handler `api_call` | `<toolName>_success_count`, `<toolName>_failure_count` | TC:326 |

- Seen in a trial call [DOC, seen] (TC:328):
  - `check_answer_success_count` was `2` after two successful calls, so the counter is cumulative within a call.
  - A code node named `setup` produced `setup_success_count` with the value `1`.
- Example (TC:330-337) [DOC]:

```json
{
  "transitions": [
    { "target_node": "give_up", "description": "The lookup failed three times", "condition": { "logic": "or", "conditions": [ { "variable": "lookup_order_failure_count", "operator": "greater_than", "operand": 2 } ] } },
    { "target_node": "ask_again", "description": "always", "condition": { "operator": "always" } }
  ]
}
```

  - The operand is the **number** `2`. `greater_than` uses `float()`, so a number or a numeric string behaves the same (WF:391).
- WF's example uses `find_slots_failure_count greater_than 0` → `goodbye_no_booking` as the first transition of a passthrough node, followed by an `always` fallback (WF:766-767). [DOC]
- [UNCERTAIN] Not documented:
  - What increments `_failure_count`: HTTP 4xx or 5xx, a timeout, a connection failure, or `ok:false` at HTTP 200.
  - Whether `_failure_count` exists, as `0`, before the first failure. It is absent from the seen table (TC:266-277).
  - What `greater_than` does on an unset variable. `float()` of nothing could be false or an error.
  - Whether engine retries (`maxRetries`) count once or once per attempt.
  - Whether `code_exec` tools, lifecycle tools or `end_call` get counters.
- [INFERRED] Because bank business errors are HTTP 200 with `ok:false` (§9.5), counters very likely do **not** see them. Route on `data.ok`.

---

## 12. `suppress_tool_results`

- "A node-level boolean for nodes that run API calls. With `true` the dialogue model sees only a short `{status: "success"}` summary in place of the raw response. Variables are still mapped and routing still sees them. Use it for large responses, or when the mapped variables already hold everything the model needs." (TC:341) [DOC]
- The default is `false` (WF:110): "Hide raw call results from the dialogue model". [DOC]
- BA sets it to `false` on both nodes (BA:147, BA:322). [CODE]
- [UNCERTAIN]
  - What the summary says when the call **failed**.
  - Whether it applies to model-called `tools` in a conversation node, or only to `pre_actions`.
  - Whether a post-hook's `what_to_do_next` is also hidden.
  - Whether setting it on a passthrough `api_request` node changes anything that a **later** conversation node sees. It is not stated that tool-call/result pairs are kept across a transition (WF:168-172; §1.4).
- [INFERRED] If `what_to_do_next` is hidden, suppression would defeat the fix in §18.

---

## 13. Background tools, and the three `interruptible` fields

- "A tool with `"config": {"interruptible": false}` runs in the background. A user interruption does not cancel it. Its result arrives one or more turns later. The mapped variables, the `_response` keys and the counters are filled as usual, but not in the same turn. A transition that reads them right after the call can find them unset. Gate on the variable with `is_set`." (TC:345) [DOC]
- [UNCERTAIN] The default of `config.interruptible` is not stated. [INFERRED] It is presumably foreground, since only `false` is described.
- [INFERRED] Background mode breaks the same-turn routing of §10. It is a poor fit for any call whose result decides the next step.

Three different fields share the name `interruptible`. Do not confuse them:

| Where | Meaning | Source |
|---|---|---|
| Tool `config.interruptible` | `false` makes the tool run in the background | TC:54, TC:345 [DOC] |
| `end_call` handler parameter `interruptible` | `true` "opens a short window after the farewell in which the user can still speak" | WF:644 [DOC]; BA:82, BA:279 [CODE] |
| Node-level `interruptible` | **Undocumented.** It is not in WF's node-field table (WF:88-113). BA sets it to `false` on `identity` (BA:141) and `true` on `collection` (BA:316) | [CODE]/[UNCERTAIN] |

---

## 14. Retries and timeouts

### 14.1 Settings (TC:347-354) [DOC]

| Setting | Where | Default | What it does |
|---|---|---|---|
| `timeoutMs` | `config` | "not documented" | Time limit of one attempt, in milliseconds |
| `maxRetries` | `config` | "not documented" | "Tool-level retries after a failed response" |
| `connect_retries` | `parameters.properties`, as a baked parameter | `2` | Retries when the connection could not be established |
| `timeout_ms` | `code_exec` parameter | `30000` | Time limit of a code snippet (also WF:667) |

### 14.2 `connect_retries` in detail (TC:356-363) [DOC]

- "It retries only failures to establish the connection: connection refused, or reset during the TCP or TLS handshake. The request never reached the server, so a repeat is safe even for POST."
- "HTTP error statuses and timeouts are not retried by it."
- "Hard cap `5`. `0` means a single attempt."
- "Back-off is 150 ms times the attempt number, with a new connection each time."
- "All attempts share one 30 second budget for the request."
- "Declare it next to `url` and `method`: `"connect_retries": {"type": "number", "default": 0}`. It is not a `config` field."
- [INFERRED] **Trap:** copying the doc's declaration as written sets `0`, a single attempt, which turns off the default of `2`. Omit the parameter, or declare the value you want.

### 14.3 `maxRetries` in practice

- The working builder sets `maxRetries` to `0` on tools that write data and to `2` on its read-only `pre_actions` call. "A retried write can record the same thing twice if the API is not idempotent." (TC:365) [DOC, verified]
- TC's own examples [DOC]:
  - `timeoutMs 10000`, `maxRetries 2` on reads (TC:14, TC:183).
  - `timeoutMs 10000`, `maxRetries 0` on the hook example (TC:374).
  - `book_appointment`, a write: `timeoutMs 10000`, `maxRetries 0` (WF:777). `find_slots`, a read: `timeoutMs 10000`, `maxRetries 2` (WF:739).
- BA [CODE]:
  - **Every** `api_call` tool has `timeoutMs: 12000` and `maxRetries: 0`, including the reads `get_account` and `verify_identity` (BA:8-11, BA:159-162, BA:203-206, BA:333-335).
  - Both `end_call` tools have `timeoutMs: 10000` and no `maxRetries` (BA:69-71, BA:266-268).

### 14.4 Hackathon facts that bear on retries

- Every bank tool documents its HTTP 500 as "The service failed. Nothing was recorded. The call may be repeated." (OA:84, OA:167, OA:229, OA:293, OA:349, OA:404, OA:466). [DOC]
- `create_promise` is "One per product." (OA:174). [DOC] A second promise for the same product fails with `"this product already has a promise"` (RAT:156). [PROBED-earlier]
- Practice case **PUB-10** is titled "The promise service fails on the first call" (PTS:392-440). [CODE]
  - `faults: [{tool: "create_promise", fail_first_n: 1}]` (PTS:435-440).
  - Checks: "exactly one promise in the ledger after the retry" and "agent does not say 'recorded' before a successful call" (PTS:432-433).
  - [UNCERTAIN] Whether the injected failure is an HTTP 500 or a 200 with `ok:false`.
  - The ledger counts injected failures in `failures{tool: n}` (RAT:139). [PROBED-earlier]

### 14.5 Unknowns [UNCERTAIN]

- What "failed response" means for `maxRetries`: 5xx, timeout or 4xx.
- Whether engine retries appear as separate `function_call_*` events or separate ledger calls.
- How `timeoutMs` interacts with the 30-second `connect_retries` budget.
- Whether `config.timeoutMs` applies to a `code_exec` entry. The code-node example has **no `config` at all** (TC:430-443).

---

## 15. Pre and post Python hooks

### 15.1 Where they sit (TC:367-391) [DOC]

"An `api_call` tool can carry two Python snippets. They run on the server, in a sandbox, right before and right after the call. They are top-level fields of the tool object." (TC:369)

```json
{
  "type": "function",
  "config": { "timeoutMs": 10000, "maxRetries": 0 },
  "function": {
    "name": "check_answer",
    "handler": "__function__:api_call",
    "description": "Check one answer. CALL it every time the caller answers the question.",
    "parameters": {
      "type": "object",
      "properties": {
        "url": { "type": "string", "default": "https://api.example.com/v1/check_answer" },
        "method": { "type": "string", "default": "POST" },
        "body": { "type": "object", "properties": { "answer": { "type": "string", "description": "The caller's answer", "default": "{{answer}}" } }, "required": ["answer"] }
      }
    }
  },
  "pre_process_code": "vars['member_code'] = str(vars.get('member_code') or '').strip().upper()",
  "post_process_code": "try:\n    if isinstance(result, dict):\n ... (see below)"
}
```

The post-hook from TC:389, unescaped:

```python
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            d['what_to_do_next'] = 'Ask the next question.' if d.get('verified') else 'Ask the same question again.'
except Exception:
    pass
```

- [INFERRED] The example pre-hook edits `member_code`, which this request never uses. So the example does **not** show that writing to `vars` changes the request.
- [INFERRED] The post-hook tests `d.get('verified')` for truth. That works only if values inside `result['data']` are native booleans. If they were strings such as `"false"`, the test would pass wrongly. See §15.4 and §23.

### 15.2 Names available inside a hook (TC:393-396) [DOC]

| Hook | Names available | Use |
|---|---|---|
| `pre_process_code` | `vars`: "mutable dict that fills the `{{var}}` placeholders of the request". `config`: "the substituted request with `url`, `method`, `headers`, `body`" | "Clean a value, or rewrite the whole request" |
| `post_process_code` | `result`: "the tool result, mutable" | "Reshape, shorten or extend the result" |

- [INFERRED] **Name clash:** inside a pre-hook, `config` is the *request* (`url`, `method`, `headers`, `body`). It is **not** the tool's `config` object (`timeoutMs`, `maxRetries`, …).
- [UNCERTAIN] `vars` "fills the placeholders" while `config` is "the substituted request". It is not stated whether a write to `vars` in the pre-hook still changes the request, or whether only edits to `config` do.

### 15.3 Documented behaviour (TC:398-403) [DOC]

- "The post-hook runs before `response_mapping` and extraction see the result." [INFERRED] So mapped variables reflect the hook's changes.
- "An empty or whitespace-only string means no hook."
- "Hooks are honoured only on `api_call` tools (and on the integration and knowledge search handlers). The platform removes them from any other handler when the workflow is saved."
  - [INFERRED] "Any other handler" includes `code_exec` and `end_call`.
- "In a pre-hook, setting `config['body']` to a string sends that string as the raw body, with no JSON encoding. Set the `Content-Type` header yourself in that case."
- [INFERRED] The restriction is by **handler**, not by placement. A hook on an `api_call` in `pre_actions`, or on a lifecycle tool, should run too. BA relies on this for `close_call` (BA:395). Not verified.

### 15.4 What `result` looks like in a post-hook (TC:405-412)

- "The internal reference shows `result` as the response body. A working builder shows otherwise." The kit sides with the builder. [DOC]
- Verified in a working builder [DOC, verified]:
  - "For an `api_call`, `result` is the envelope described above: a dict with `status`, `data`, `message`, `status_code` and `header`. The API's JSON body is `result["data"]`."
  - "A key that the hook adds inside `result["data"]` reaches the dialogue model as part of the tool result." The working builder adds a `what_to_do_next` sentence there, and its prompt tells the model to obey it.
  - "`result.pop("header", None)` removes the response headers." The working builder does this **on every tool**, so that headers do not take up space in the model's context.
  - "Mapping paths still start with `data.` when a post-hook is present."
- [UNCERTAIN] Whether values inside `result['data']` are native Python types (`True`, `3`) or already strings. The flattened variable table holds strings (TC:270-271), but the post-hook sees `result` before flattening.

### 15.5 Variables inside a post-hook

- "Seen in a test on 10 October: a post-hook can read call variables and write new variables, and a later pre-hook reads them." (TC:416) [DOC, seen]
- [UNCERTAIN] The **name** under which a post-hook reaches the variables. TC:396 lists only `result`. `vars` is a guess.
- "Not confirmed: whether a change to `result` also changes the flattened `<tool>_response.*` variables." (TC:416) [DOC]/[UNCERTAIN] This includes whether popping `header` removes the `…header.*` variables.

### 15.6 Error handling

- "The working builder writes every hook inside `try` and `except Exception: pass` and checks types with `isinstance` before use. What the platform does when a hook raises is not documented." (TC:414) [DOC]
- [UNCERTAIN] No mechanism to **abort** a call from a pre-hook is documented. "Cannot abort" is not established either. It is simply unknown.
- [INFERRED] Whether hooks are templated like `code` is not stated. Applying the same rule (no `{{` or `}}`) to hooks is prudent.

### 15.7 BA's only hook, on the lifecycle `close_call` (BA:395) [CODE]

```python
try:
    b = config.get('body')
    if isinstance(b, dict) and b.get('outcome') in ('promise', 'paid'):
        b.pop('reason', None)
except Exception:
    pass
```

- It drops `reason` from the request when the outcome is `promise` or `paid`. That matches the tool API's rule: "Required for every outcome except promise and paid." (OA:435). [DOC]
- It uses the documented `config['body']` access, with try/except and `isinstance`.

---

## 16. Code nodes and `code_exec`

### 16.1 A code node (TC:418-449) [DOC]

"A `code` node runs a Python snippet when it is entered. The snippet is a `code_exec` function in `pre_actions`." (TC:420)

```json
{
  "name": "compute_delivery",
  "node_type": "code",
  "passthrough": true,
  "passthrough_default_transition": "tell_delivery",
  "on_enter": { "type": "silent" },
  "pre_actions": [
    {
      "type": "function",
      "function": {
        "name": "code_exec",
        "handler": "__function__:code_exec",
        "parameters": {
          "type": "object",
          "properties": {
            "code": { "type": "string", "default": "<python source, see below>" },
            "timeout_ms": { "type": "number", "default": 10000 }
          }
        }
      }
    }
  ],
  "transitions": [
    { "target_node": "tell_delivery", "description": "always", "condition": { "operator": "always" } }
  ]
}
```

The snippet from TC:438, unescaped:

```python
import datetime
try:
    start = datetime.date.fromisoformat(str(vars.get('shipped_on'))[:10])
    eta = start + datetime.timedelta(days=3)
    vars['delivery_day'] = eta.isoformat()
    vars['delivery_state'] = 'known'
except Exception:
    vars['delivery_day'] = ''
    vars['delivery_state'] = 'unknown'
```

- The `pre_actions` entry has **no `config` and no `description`** (TC:430-443). [DOC]
- The example has one `code_exec` entry. TC states no limit of one, and documents no behaviour with several. [UNCERTAIN]
- [INFERRED] If `shipped_on` is unset, `str(None)` gives `'None'`, parsing raises, and the `except` branch writes the fallbacks. Every variable a later step reads gets a value on every path.
- `on_enter` is `silent`, and the node ends with an `always` transition. This matches the rule "Treat a code node like an API node" (TC:499).

### 16.2 Parameters (TC:451-454) [DOC]

| Parameter | Meaning |
|---|---|
| `code` | "The Python source, as a baked `default` string" |
| `timeout_ms` | Time limit in milliseconds. Default `30000` |

### 16.3 Reading and writing variables (TC:456-460) [DOC]

- "The snippet gets a dict named `vars`. It holds the current workflow variables."
- "Read with `vars.get("name")`. A variable that was never set is absent."
- "Write with `vars["name"] = value`. Every key the snippet assigns becomes a workflow variable."
- WF:186 says the same: "A code node or `code_exec` tool writes into `vars`".

### 16.4 Verified facts (TC:462-468) [DOC, verified]

1. "Call variables are in `vars`. The builder reads `vars.get("now")`, a call variable passed with the simulation."
   - WF:221 also verifies `vars.get("customer_id")` in code. [DOC, verified]
2. "The result of an earlier `api_request` node is reachable from `vars` in a later code node."
   - The builder looks for it under the mapped variable name first, and under the flattened result keys second.
   - "Which of the two held the data is not recorded."
3. "A string written to `vars["date_facts"]` in a code node resolves as `{{date_facts}}` in the `task_message` of later conversation nodes. Multi-line strings work."
4. "The standard modules `json`, `re` and `datetime` can be imported."
5. "The same snippet can run in two code nodes at different points of the call. The later run sees the variables added in between."
6. A passthrough `code` node can be the `initial_node`. "It runs before the agent says anything." (WF:484)

### 16.5 What a code node returns (TC:470-490) [DOC, seen]

```json
{ "status": "success", "data": null, "message": "Code executed successfully", "status_code": 200 }
```

- "The snippet's output is not in `data`. Its values reach the workflow only through `vars`." (TC:478)

The variable table after a code node named `setup` ran:

| Variable | Value |
|---|---|
| each key the snippet wrote, for example `date_facts` | the value, with source `tool_result` and source node `setup` |
| `setup_response.status` | `success` |
| `setup_response.data` | `null` |
| `setup_response.message` | `Code executed successfully` |
| `setup_response.status_code` | `200` |
| `setup_status_code` | `200` |
| `setup_success_count` | `1` |

- "For a code node the automatic keys are named after the **node**, not after `code_exec`." (TC:490)
- [UNCERTAIN] The result on an exception or a timeout is not documented: its `status`, whether `<node>_failure_count` increments, and whether `vars` writes made before the error persist.

### 16.6 Rules for snippets (TC:492-499) [DOC]

1. "**Do not write `{{` or `}}` in the code.**"
   - "The internal sources disagree on whether the `code` field is templated." One says it is exempt. Another says placeholders are resolved when the code runs, and that an unset one is left as literal text, which breaks the Python.
   - "The working builder removes every `{{` and `}}` from generated code (a nested dict literal such as `{'a': {'b': 1}}` ends in `}}`) and reads all values from `vars`."
   - [INFERRED] Other sources of doubled braces: f-string `{{` escapes, and embedded JSON. Single braces such as `{}` and `{'a': 1}` are fine.
   - The kit is itself inconsistent. TC:116 states the literal-text crash as fact. TC:494 calls it disputed. TC:512 says the `code_exec` **tool** form resolves `{{var}}` at call time.
2. "**Never let a snippet raise.** Wrap the body in `try` and `except`, and write a fallback value for every variable that a later prompt or condition reads. A prompt that references an unset variable shows the literal placeholder to the model."
3. "**Write strings for routing flags**, such as `known` and `unknown`. Do not route on a Python boolean." See WF "Do not route on a boolean" (WF:370-389).
4. "Keep snippets fast. They block the conversation."
5. "Do arithmetic, date calculation and counting in code, and give the model the finished facts as text." Verified: the working builder computes a block of date facts in a code node and places it in the prompts. [DOC, verified]
6. "Treat a code node like an API node: `passthrough: true`, a `passthrough_default_transition`, and a last `always` transition."

### 16.7 Sandbox limits (TC:501-508) [DOC]

| Limit | Value |
|---|---|
| Time | `timeout_ms`, default `30000` |
| Modules | `json`, `re` and `datetime` are verified in a working builder. "The full list is not documented" |
| Network and file access | "Not documented" |
| Memory and output size | "Not documented" |

- [INFERRED] Even if network access were possible, a call to any service other than the kit's tool API fails the case (HP §Rules, line 37).
- [UNCERTAIN] Whether hooks share this sandbox, its module list and its time limit. TC:369 says only that hooks run "in a sandbox".
- [UNCERTAIN] How non-string values written to `vars` (bool, int, list, `None`) are stored. Also unknown: whether `del vars[k]` unsets a variable, and whether `None` counts as "set" for `is_set`.

### 16.8 `code_exec` as a model tool (TC:510-512) [DOC]

- "`code_exec` can also be a tool in the `tools` array of a conversation node, called by the model."
- "Its parameters are top-level arguments, declared without `default` so the model fills them."
- "For such a tool the `code` field resolves `{{var}}` when the tool is called, against the current variable table."
- "The working builder does not use this form, so nothing about it is verified here."
- [INFERRED] Hooks on it would be stripped (TC:402).
- [UNCERTAIN] How the model's arguments reach the snippet, what result the model sees, and what the automatic keys and counters are named. The `data: null` result was seen only for a code **node** (TC:472-476).

### 16.9 The chat route and code steps [DOC]

- "Seen in tests, not guaranteed: ... when the first step is a code step the chat route may skip it, so values that step computes are empty." (API:252)
- [INFERRED] `POST /api/v2/chat/message` is unrepresentative for a workflow whose `initial_node` is a code node. Simulations do not carry this caveat, and WF:484 verifies a code node as `initial_node` in that context.

---

## 17. Lifecycle tools

### 17.1 Definition and values (TC:514-522) [DOC]

"A tool whose `config.alwaysRunsAt` is a non-empty list is never shown to the model. The engine fires it at a fixed point of the call." (TC:516)

| Value | When |
|---|---|
| `start_of_call` | "During call setup, before the first turn" |
| `end_of_call` | "After the call has ended" |
| `each_turn` | "Accepted by the schema but not implemented. It never fires" |

### 17.2 Placement (TC:524, TC:559-560) [DOC]

- "Put a lifecycle tool that must run on every call into the workflow's top-level `tools` array." (TC:524)
- "A workflow-level tool without `alwaysRunsAt` never runs and the model never sees it." (TC:559)
- "A lifecycle tool in a node's `tools` runs for `start_of_call` only on the `initial_node`, and for `end_of_call` only on the node in which the call ended." (TC:560)
- The top-level key is `tools`, an array of "Workflow-level lifecycle tools" (WF:58).

### 17.3 Rules (TC:561-564) [DOC]

- "If a `{{var}}` parameter is still unresolved, one model call fills the parameters. If everything resolves, the handler runs directly." This contradicts TC:115 and WF:202; see §5.3.
- "`response_mapping` is applied for `start_of_call`. It is not applied for `end_of_call`."
- "A malformed lifecycle tool is dropped at run time without an error. Validate with a dry run (api.md)."
  - The dry run is `POST /api/v2/workflow?dryRun=true`. It "runs its write validation and stores nothing" (API:73-75), and "The fields of the dry-run result are not documented" (API:85).
  - [UNCERTAIN] Whether the dry run catches what run time drops.

### 17.4 The end-of-call sequence and `call.*` variables (TC:563) [DOC]

- "At the end of a call the order is: call analysis, then `end_of_call` tools, then success-criteria judging."
- An `end_of_call` tool can use these variables:

| Placeholder |
|---|
| `{{call.analysis.summary}}` |
| `{{call.analysis.structured_data_str}}` |
| `{{call.call_end_reason}}` |
| `{{call.call_end_reason_category}}` |
| `{{call.call_tags}}` |
| `{{call.duration}}`. WF:235 says "Whole seconds since call start" |

### 17.5 Example (TC:526-555) [DOC]

```json
{
  "initial_node": "greeting",
  "nodes": {},
  "tools": [
    {
      "type": "function",
      "config": { "alwaysRunsAt": ["end_of_call"] },
      "function": {
        "name": "push_call_result",
        "handler": "__function__:api_call",
        "parameters": {
          "type": "object",
          "properties": {
            "url": { "type": "string", "default": "https://api.example.com/v1/call-results" },
            "method": { "type": "string", "default": "POST" },
            "body": {
              "type": "object",
              "properties": {
                "summary": { "type": "string", "default": "{{call.analysis.summary}}" },
                "reason": { "type": "string", "default": "{{call.call_end_reason}}" }
              }
            }
          }
        }
      }
    }
  ]
}
```

The example has no `description`, no `headers`, and no `timeoutMs` or `maxRetries`.

### 17.6 BA's `close_call` and what scoring needs [CODE]

- BA's workflow-level `close_call` (BA:330-397):
  - `config`: `{timeoutMs: 12000, maxRetries: 0, alwaysRunsAt: ["end_of_call"]}`.
  - `Content-Type` is declared.
  - `reason` defaults to `{{reason}}`, `outcome` to `{{outcome}}` (with an enum), and `customer_id` to `{{customer_id}}`.
  - `description`: "Record how the call ended, from the conversation." (BA:393).
  - It carries the pre-hook from §15.7.
- Nothing in BA sets `outcome` or `reason`, so at end of call both are filled by the one model call of TC:561 (§5.3). [INFERRED]
  - [INFERRED] The parameter descriptions (BA:359, BA:370) are therefore what that model reads.
- The scorer requires certain things of `close_call` and the tools before it:
  - The ledger's last call must be `close_call`, or the case fails with "the call was not closed with close_call" (SC:29).
  - `(outcome, reason)` must equal the expected pair (SC:19-20).
  - `get_account` or `create_promise` answered with the error "identity not verified" fails the case (SC:31-32).
- `close_call` is "Always the last tool call. Nothing is accepted after it." (OA:411) [DOC]. After a close, every tool returns `"the call is already closed"` (RAT:159). [PROBED-earlier]
- [INFERRED] `end_of_call` fires however the call ends, including a hang-up mid-flow (TC:521). Any variable it bakes must therefore hold the correct current value at every moment of the call. Otherwise the fill model decides.

### 17.7 Unknowns [UNCERTAIN]

- Which model performs the lifecycle fill, what context it sees, and whether it can invent values.
- When a lifecycle tool's `{{var}}` placeholders are resolved: at fire time, at registration (TC:91), or at node entry (TC:93). TC:561 states only the model-fill fallback (§3.2).
- Whether a `start_of_call` result enters the history the model sees, and whether its mapped values are available to the initial node's `on_enter` text.
- Automatic keys and counters for lifecycle tools.

---

## 18. Tool results and the next turn

- "After a tool call returns, the model sees the result and has to produce the next turn itself." (TC:568) [DOC]
- Two failures were "seen in practice runs with the hackathon's agent model" (TC:568-571) [DOC, seen]:
  1. "**The agent says nothing after the tool call.** The result arrives, no assistant message follows, and the simulated customer hangs up after waiting. It happens more often when the result is bare data such as `{"ok": true, "verified": true}`."
  2. "**The agent ignores a negative result.** For example it reads `"verified": false` and moves on to the next question as if the answer had passed."
- The fix (TC:573) [DOC, verified]: "a post-hook on the tool that adds one plain instruction line to the result before the model sees it, for example a `what_to_do_next` field that says what the answer means and what to say or call next. The model then has something to act on."
- "Also say it in the step's prompt: after every tool result, speak to the customer or call the next tool. Never end a turn with nothing." (TC:575) [DOC]
- Related: a turn with no text and no tool call produces the error event "The model returned no speakable content" (TC:219). [DOC, seen]
- Kit skill rule: "When a tool call fails, the agent must say so. It must never tell the customer something is recorded when it is not." (SK:29) [DOC]
- [INFERRED] The doc's example sentences are `'Ask the next question.'` and `'Ask the same question again.'` (TC:389). TC:573 says "a post-hook on the tool". "Every tool" is stated only for `result.pop("header", None)` (TC:411).

---

## 19. Timing: when values become available

| Event | What is available, and when | Source |
|---|---|---|
| Node entry | Baked defaults are resolved against the variable table | TC:93 |
| `pre_actions` / code node runs | At node entry, before any model turn | TC:149, TC:420 |
| Pre-hook | Right before the call | TC:369 |
| Post-hook | Right after the call, before `response_mapping` and extraction | TC:400 |
| Foreground tool returns | Mapped variables, flattened keys and counters are set. Routing runs again in the same turn, before any further model turn | TC:291; WF:410 |
| Background tool (`config.interruptible: false`) | One or more turns later. Gate with `is_set` | TC:345 |
| Extracted variable | Available to the same node's transitions in the same turn, and to every later node | WF:580 |
| `start_of_call` lifecycle tool | During setup, before the first turn. `response_mapping` is applied | TC:520, TC:562 |
| `end_of_call` lifecycle tool | After call analysis, before success judging. No mapping | TC:563 |
| `code_exec` **tool** `code` placeholders | Resolved when the tool is called | TC:512 |
| `max_node_turns` | "Only user messages count. Tool results and agent messages do not." | WF:662 |

---

## 20. Exact strings to recognise

| String | Where it appears | Source |
|---|---|---|
| `URL is required` | Error when `url` is a `const` | TC:92 |
| `Template variable: name` | The only description the model sees under the `body.default` anti-pattern | TC:106 |
| `The model returned no speakable content` | Error event after a turn with no text and no tool call | TC:219 |
| ``The function `<name>` is not currently available.`` | Result when the model calls a tool the node does not list | TC:221 |
| `Successfully executed POST request` | `message` of a successful `api_call` envelope | TC:256, TC:273 |
| `Code executed successfully` | `message` of a successful `code_exec` | TC:475 |
| `CALL it every time the caller gives an order number.` | Recommended description style | TC:215 |
| `Looks up an order` | Anti-example of a plain description | TC:216 |
| `The service failed. Nothing was recorded. The call may be repeated.` | Bank tools' HTTP 500 description | OA:84 and repeats |
| `` `ok` is false when the action was not carried out. `` | Bank tools' HTTP 200 description | OA:51 and repeats |
| `the call was not closed with close_call` | Scorer failure reason | SC:29 |
| `identity not verified` | Bank error the scorer fails on, for `get_account` or `create_promise` | SC:32; RAT:154 |
| `Have a good day` | BA's `end_call` `trigger_pattern` phrase | BA:88, BA:100 |

---

## 21. The doc's checklist, verbatim (TC:577-587) [DOC]

1. "Fixed values use `default`, never `const`."
2. "Each `api_call` body field is a leaf under `body.properties` with its own `default`, `description` and `enum`."
3. "`tools` only on `conversation` nodes. `pre_actions` only on `api_request` and `code` nodes."
4. "`response_mapping` on the tool for `tools`, on the node for `pre_actions`."
5. "Mapping paths start with `data.`."
6. "Booleans from results are tested as `"true"` and `"True"`, or replaced by string fields."
7. "Every passthrough node ends with an `always` transition."
8. "Code reads and writes through `vars`, never raises, and contains no `{{` or `}}`."
9. "Tool descriptions say when to call the tool."

---

## 22. Corrections

### 22.1 Where the deep-read notes were wrong or incomplete (the source wins)

| # | Note claim | Verdict | What the source says |
|---|---|---|---|
| 1 | tc-2 §1 #8: "`customer_id` in code is [INFERRED] … not verified" | **Wrong** | WF:221: "Verified in a working builder: call variables are readable as `{{customer_id}}` in prompts and tool parameters, and as `vars.get("customer_id")` in code." The earlier summary was right on this point, and tc-2's correction was not. |
| 2 | tc-1 §1: "There are three places to attach a tool" | Incomplete | A fourth location holds a function object: the `terminal` of an `end_call` node (TC:64; WF:108; WF:622-635). BA also puts the `end_call` handler in `tools` (BA:67-102). |
| 3 | tc-1 and tc-2 label "the seven tools need no key" and "business errors come back as HTTP 200 with `ok:false`" as [PROBED-earlier] only | Under-labelled | Both are also [DOC] in the tool API file: OA:6 ("The seven tool calls need no key…") and OA:51 and each tool's 200 response ("`ok` is false when the action was not carried out."). Only the 404 and 401 exceptions remain [PROBED-earlier] (RAT:144). |
| 4 | tc-1 §3: BA's `close_call.outcome` is "a baked field" | Imprecise | Nothing in BA ever sets `outcome` (BA:143-144, BA:318-319, BA:401-406). At end of call it is unresolved, so it is model-filled under TC:561. |
| 5 | tc-1 U1 and tc-2 K1 present the lifecycle contradiction as fully open | Narrowed | BA's 2-of-13 pass (README:34), together with the scorer's outcome and last-call checks (SC:20, SC:29), implies that the model fill happened. This is [INFERRED], not verified (§5.3). |
| 6 | tc-1 U2 lists TC:115 against WF:202 as a contradiction | Overstated | They conflict only if TC:115 is read as covering mixed values. WF:202 is the more precise rule (§5.2). |
| 7 | tc-2 K9 cites WF:393 for "After each user message" | Line off | The sentence is WF:395. WF:393 is the heading. |

Everything else in tc-1 and tc-2 that this chapter uses was re-checked against TC, WF, API, BA, OA, PTS, SC and HP, and matches.

### 22.2 Errors in the earlier summary `research/read-tools-and-code.md`

These errors were confirmed by the notes and re-checked here against the sources.

| Earlier claim | Verdict | Correct statement |
|---|---|---|
| The OR of mapped variable and flattened key: "BA does exactly this" | Wrong | BA tests only the flattened key, with `"mode": "exact"`. BA has no mappings at all (BA:116-137, BA:143, BA:318). The OR pattern is the working builder's (TC:285). |
| "Paths without `data.` … failed in one early trial" | Overstated | The paths of that trial are "not recorded" (TC:284). Bare paths are unconfirmed, not shown to fail. |
| `_args` are "never" stored under the bare name | Overstated | One trial call: "They were not stored under the bare field name" (TC:97). |
| "Baking happens once … not baked unless re-entered" | Unsupported | TC:93 says only "when the node is entered". Re-entry and late setting are unknown. |
| "In engine calls the field is silently dropped" | Incomplete | Only an exact single placeholder is dropped. A mixed value is sent with the literal `{{x}}` (WF:202). Lifecycle tools may be model-filled instead (TC:561). |
| "Stale result variables persist and can fire later transitions" | Unsupported as doc | TC:279 says only that each call overwrites. Key removal is undocumented (§9.3). |
| "The old node's model does not speak, so the target node must" | Unsupported | TC:291 is silent on who speaks (§10.6). |
| "Hidden briefs change fields and enums" placed under TC | Mis-attributed | The source is HP §Overview (line 12), not TC. |
| BA "`maxRetries` 0 on all writes; `timeoutMs` 12000" | Imprecise | **All** BA `api_call` tools, reads included, use 0 and 12000. Its `end_call` tools use 10000 and no `maxRetries` (§14.3). |
| A code node holds "one" `code_exec` | Overstated | No limit is stated (TC:420). |
| "f-string `{{` escapes, embedded JSON" listed as doc traps | Not in doc | TC:494 names only the nested dict literal. The others are sound [INFERRED] additions. |
| `code_exec` tool "result is `data:null`, so the model gets no feedback" | Overstated | `data: null` was seen for a code **node** only. The tool form is unverified (TC:512). |
| "A post-hook on **every** tool adds `what_to_do_next`", with quoted sentences | Overstated, invented quotes | TC:573 says "a post-hook on the tool". The doc's sentences are `'Ask the next question.'` and `'Ask the same question again.'` (TC:389). |
| "If the request is invalid, it cannot be aborted" | Overstated | Abort is undocumented, and so is the effect of a raising hook (TC:414). Nothing is established either way. |
| "The meaning of `maxRetries` is undocumented" | Half wrong | It is "Tool-level retries after a failed response" (TC:352). Undocumented: its default, and what counts as "failed". |

---

## 23. Open questions

Each question below can be settled later through **normal kit use**: your own test workflow, `tools/run_cases.py`, or `POST /api/v2/chat/message` (HP §FAQ, line 43). You then read the call's `function_call_start` / `function_call_complete` / `route_evaluated` events (API:327-329), `variableTable` (API:334) and your own practice ledger `calls[]` (RAT:140). Nothing here needs, or allows, probing the platform (HP §Rules, line 37). Several questions can share one self-test workflow.

| # | Question | Why it matters | Sources | How it could be settled |
|---|---|---|---|---|
| Q1 | Lifecycle tool with an unset `{{var}}`: is the field dropped, or model-filled? | Determinism of `close_call` | TC:115, TC:561, WF:202 | A practice case where `reason` is never set; read the ledger args of `close_call` |
| Q2 | Is a baked value typed (JSON number) or a string? Compare `{{x}}` with `{{x:json}}` | Numeric body fields | WF:195-196 | Bake `amount` both ways; read the `function_call_start` body |
| Q3 | Model-visible name, `_args` key and sent key when the property key differs from the placeholder | Naming of leaves | TC:85, TC:97 | Avoid the question: keep the key equal to the placeholder (TC:95) |
| Q4 | Does `""` count as "has a value" for a model tool? A variable set mid-node? Re-entry re-bakes? | Bake-or-ask control | TC:84-85, TC:93, TC:115 | Compare `function_call_start` args with the model's turns |
| Q5 | Do keys missing from a later response clear old `<tool>_response.*` keys? | Stale values can fake a success | TC:279; RAT:153 | Call the same tool twice; compare `variable_table` |
| Q6 | Spelling and type of **mapped** booleans and numbers | Silent `equals` mismatch | TC:286; WF:372 | Map `data.verified`; read `variableTable` |
| Q7 | Form of a mapped list or object in `vars`; how arrays are flattened | Code that iterates products | TC:287 | A code node writes `type(...).__name__` of the mapped value into a variable |
| Q8 | Do bare (non-`data.`) paths work? | Low: always use `data.` | TC:284 | Map both forms on one tool |
| Q9 | What counts as a failure for `_failure_count` and `maxRetries`? Does `_failure_count` exist before a failure? Are retries visible? | Retry and give-up routing; double-recording | TC:321-328, TC:352 | PUB-10 (PTS:392-440); read counters, events and ledger `calls[]` |
| Q10 | The envelope on 500, 404, timeout and `ok:false`. Does the post-hook run on a failure? Does mapping overwrite on a failure? | Honest failure handling | TC:250-262 | The same PUB-10 run, plus a deliberately wrong identity answer |
| Q11 | `_response.*` prefix of an `api_call` in an `api_request` node: node name or tool name? | Fallback transitions | TC:325, TC:490 | Avoid the question: name the node and the tool the same |
| Q12 | Does `_args` include baked fields? | Debugging | TC:268 | Read `variable_table` after a call |
| Q13 | Does the engine enforce `enum`? | Invented values | TC:87, TC:124 | Watch `function_call_start` args; the bank rejects unknown enums anyway (RAT:157-159) |
| Q14 | After a result-driven transition, is the old node's same-turn text spoken? Does the post-result routing pass re-judge `matches_intent`, `loop_condition` and global nodes? | Who speaks next | TC:164, TC:291; WF:395, WF:410 | Event order around a transition; the `branches` list in `route_evaluated` |
| Q15 | Pre-hook: does a write to `vars` change the request, or only edits to `config`? | Guard hooks | TC:395 | Two variants; compare the `function_call_start` body |
| Q16 | Post-hook: the name for variables; native or string types in `result['data']`; does a `result` change alter the flattened keys? | `what_to_do_next` correctness | TC:396, TC:416; TC:286 vs TC:389 | The post-hook writes `type(d.get('verified')).__name__` into `data`; map it and read it |
| Q17 | Does `suppress_tool_results` also hide `what_to_do_next`? What is shown on failure? Does it apply to model tools? | Conflicts with the §18 fix | TC:341, TC:573 | One chat turn with suppression on |
| Q18 | What happens when a hook raises? Can a hook abort a call? | Guarding writes | TC:414 | A pre-hook that raises, on a read-only tool in a throwaway test workflow |
| Q19 | Hook sandbox: imports and time limit; the same as `code_exec`? | Date maths in hooks | TC:369 | A post-hook writes an import result into `data` |
| Q20 | Modules beyond `json`/`re`/`datetime`; network, files, memory | Portability | TC:506-508 | Not needed if only `json`/`re`/`datetime` are used |
| Q21 | Storage of non-string `vars` writes; `del`; does `None` count for `is_set`? | Flags and fallbacks | TC:459-460 | A code node writes one of each type |
| Q22 | `code_exec` failure or timeout: the result, the counter, partial writes | Deadlock and fallback design | TC:470-490 | A code node that writes, then raises outside `try` |
| Q23 | The `code_exec` tool form: arguments, result, naming | Only if that form is used | TC:512 | Skip unless needed |
| Q24 | Lifecycle fill: which model, what context, can it invent values? | `close_call` correctness | TC:561 | Avoid the question: always set every variable `close_call` bakes |
| Q25 | Do hooks run on an `api_call` in `pre_actions` or in a lifecycle tool? | BA's `close_call` relies on it | TC:402; BA:395 | Check that a `promise` case's ledger `close_call` args lack `reason` |
| Q26 | `start_of_call`: is the result in the history? Are mapped values available to the initial `on_enter`? | Preloading data | TC:520, TC:562 | One chat turn |
| Q27 | Default of tool `config.interruptible`; meaning of node-level `interruptible` | Avoid surprises | TC:54, TC:345; BA:141, BA:316 | Leave them as BA has them, or omit them |
| Q28 | `timeoutMs` and `maxRetries` defaults; `timeoutMs` against the 30-second connect budget; `config` on `code_exec` | Explicit settings avoid this | TC:351-352, TC:362 | Not worth testing: always set them explicitly |
| Q29 | A mapping whose path is missing: is the variable left unset? | `is_set` routing on mapped ids | WF:800-808 | Read `variableTable` after an `ok:false` response |
| Q30 | Is a date-typed variable reformatted when baked into a body? | `YYYY-MM-DD` fields | WF:200, WF:754 | Read the `function_call_start` body |
| Q31 | Is `Content-Type` sent when no header is declared? | Bank JSON parsing | TC:382-384, TC:540-547 | Avoid the question: always declare it, as BA does |
| Q32 | What does `passthrough_default_transition` do, given that an `always` is still mandatory? | Low | TC:178, TC:209 | Not needed: always set both |
| Q33 | Does a dry run catch a malformed lifecycle tool? | Silent drop | TC:564; API:85 | After each publish, confirm `close_call` appears in a practice ledger |
| Q34 | How long the simulated customer waits after a silent agent turn | Cost of an empty turn | TC:570 | `secondsFromStart` around a silent turn (API:314) |

---

## Traps to remember

1. **`const` sends nothing.** Only `default` bakes. An `api_call` whose `url` is a `const` fails with "URL is required" (TC:87, TC:92).
2. **A literal `default` always hides the parameter from the model.** There is no "suggested default" (TC:84).
3. **Name collision.** A model-filled placeholder whose variable is already set at node entry is baked silently, and the model never sees the parameter (TC:99). Variables are call-wide and never cleared (WF:178), so one earlier write bakes that name in every later node.
4. **Baking happens at node entry** (TC:93). A value that arrives later in the node may not be used [UNCERTAIN]. The exception is the `code_exec` tool, which resolves at call time (TC:512). Lifecycle tools probably resolve when they fire, but the docs do not say so [UNCERTAIN] (§3.2).
5. **The model sees a parameter under its placeholder's name**, not the property key (TC:85). Keep the two identical (TC:95).
6. **The `body.default` template anti-pattern fails silently.** The model sees only "Template variable: name", the `enum` and `description` are lost, and the call still works. Saving from the dashboard editor deletes the tool (TC:106-107).
7. **`code_exec` parameters are top-level**, unlike `api_call` body leaves (TC:109).
8. **Unset placeholders in engine-run calls.** An exact `"{{x}}"` field is dropped with no error. A mixed `"text {{x}}"` field goes out with the literal placeholder. `""` is sent empty (TC:115; WF:202). In prompts the literal placeholder is shown to the model, and in fixed spoken lines it is said aloud (WF:201).
9. **Lifecycle tools contradict the drop rule.** An unresolved placeholder triggers "one model call" that fills the parameters (TC:561). BA's `close_call` depends on this, since nothing in BA sets `outcome` [INFERRED].
10. **Misplaced arrays are stripped without an error.** `tools` survives only on conversation nodes, `pre_actions` only on `api_request`/`code` nodes. The create call succeeds, and the dry run strips silently too (TC:153; API:87).
11. **`description` is ignored in `pre_actions`.** In `tools` it is the only tool-level text, and a plain description makes the model talk instead of calling (TC:50, TC:167, TC:216).
12. **A tool works only in the node that lists it.** Otherwise the result is "The function `<name>` is not currently available." (TC:221)
13. **A turn with no text and no tool call** produces "The model returned no speakable content", and the simulated customer hangs up (TC:219, TC:570).
14. **A `response_mapping` inside a `pre_actions` entry is ignored.** It must be at node level (TC:244).
15. **Mapping paths start with `data.`.** `result` and the mapping both see the envelope, not the body. Bare paths are unconfirmed (TC:283-284, TC:412).
16. **Booleans arrive as strings**, lower-case `true` in the flattened keys. Test both `"true"` and `"True"`, or route on string fields. A mismatch fails silently (TC:286; WF:372).
17. **HTTP 200 with `ok:false` is a business failure inside a "success" envelope** (OA:51; RAT:144). `status`, `status_code` and probably the counters will not show it. Route on `data.ok` and the other body fields [INFERRED].
18. **Stale values.** Each call overwrites `_args`/`_response` (TC:279), but whether missing keys are cleared is unknown. A re-verify once returned no `all_verified` key (RAT:153). Mapped variables are never cleared (WF:178).
19. **`_failure_count` is unreliable.** It was absent from the seen table, and what counts as a failure is undocumented (TC:266-277, TC:321).
20. **Automatic-key prefixes differ by placement.** It is the tool name for `tools`, `<nodeId>` for `pre_actions` counters, and the node name for code nodes, never `code_exec` (TC:325-326, TC:490). Name a `pre_actions` node and its tool the same [INFERRED].
21. **A passthrough node without a matching transition deadlocks**, even with `passthrough_default_transition` set. Always end with `always` (TC:209, TC:315).
22. **Do not leave an action node with `matches_intent` on the earlier intent.** The router reads the latest user message and can leave before the tool runs (TC:317).
23. **Background tools (`config.interruptible: false`) deliver their variables turns later.** Same-turn routing will not see them, so gate with `is_set` (TC:345). Three different `interruptible` fields exist (§13).
24. **`connect_retries` is a baked parameter, not a `config` field.** The doc's sample declaration `default: 0` turns off the default of 2. It never retries HTTP errors or timeouts, and all attempts share a 30-second budget (TC:353-363).
25. **The `timeoutMs` and `maxRetries` defaults are undocumented.** Set both explicitly. A retried write can record twice (TC:351-352, TC:365). The bank's HTTP 500 means "Nothing was recorded" (OA:84), and promises are "One per product" (OA:174).
26. **Hooks only survive on `api_call`** (and the integration and knowledge-search handlers). They are stripped from `code_exec` and `end_call` when the workflow is saved (TC:402).
27. **In a pre-hook, `config` is the request** (`url`, `method`, `headers`, `body`), not the tool's `config` (`timeoutMs`, …) (TC:395).
28. **A string `config['body']` is sent raw** with no JSON encoding. Set `Content-Type` yourself (TC:403).
29. **A raising hook has undocumented effects.** Wrap every hook in `try`/`except Exception` and check types with `isinstance` (TC:414).
30. **A post-hook's `result` is the envelope.** The "internal reference" says it is the body, and it is wrong per the working builder (TC:407-409). Types inside `result['data']` (bool or string) are unverified, so a truthiness test like `d.get('verified')` is a risk [UNCERTAIN].
31. **`suppress_tool_results: true` probably hides the `what_to_do_next` fix** (TC:341, TC:573) [INFERRED].
32. **No `{{` or `}}` anywhere in code.** Nested dict literals end in `}}`. Read every value from `vars` (TC:494). TC:116 says an unset placeholder in `code` crashes the snippet.
33. **A snippet must never raise.** Write a fallback for every variable a later prompt or condition reads (TC:495).
34. **A code node returns `data: null`.** Output exists only through `vars`, and its automatic keys are named after the node (TC:472-490).
35. **Route on string flags such as `known`/`unknown`, never Python booleans** (TC:496; WF:370-389).
36. **Snippets block the conversation.** Keep them fast. The default timeout is 30 000 ms (TC:497, TC:505).
37. **Only `json`, `re` and `datetime` are verified in the sandbox.** Network and files are undocumented, and any call outside the kit's tool API fails the case anyway (TC:506-507; HP §Rules, line 37).
38. **The chat route may skip a code node that is the first step**, which leaves its values empty (API:252).
39. **Lifecycle edge cases.** `each_turn` never fires. A workflow-level tool without `alwaysRunsAt` never runs. A malformed lifecycle tool is dropped silently. `end_of_call` applies no `response_mapping`. A lifecycle tool in a node's `tools` fires only on the initial node (start) or the ending node (end) (TC:522, TC:559-564).
40. **`end_of_call` fires however the call ends.** Every variable `close_call` bakes must be right at every moment. The scorer fails a case whose last ledger call is not `close_call` (SC:29) [INFERRED].
41. **The agent goes silent after bare-data results and ignores negative results.** Add a `what_to_do_next` line in a post-hook, and say in the prompt: after every result, speak or call the next tool (TC:568-575).
42. **Never claim something is recorded before the tool confirmed it.** PUB-10 checks exactly this (PTS:433; SK:29).
43. **Date substitution is speech-formatted in prompts** (WF:200). Its format in request bodies is unverified, so send ISO strings computed in code [INFERRED].
44. **`{{x}}` substitutes a string.** `{{x:json}}` is the JSON-encoded form meant for bodies (WF:195-196).
45. **No `null` in workflow JSON** (WF:64).
46. **Hidden briefs change tool fields and allowed values** (HP §Overview, line 12). Take them from the tool API file (SK:18). BA's `close_call` enum is already stale against it: it lacks `paid` and `transferred` (BA:362-367 vs OA:424-431).
47. **BA is not the "working builder".** The verified patterns (post-hooks, mappings, the OR safeguard, code nodes) are not in BA (TC:5; README:34).
48. **Seeing a variable's name in a prompt or code proves nothing.** Read `variable_table` / `variableTable` to know its value (API:336).
