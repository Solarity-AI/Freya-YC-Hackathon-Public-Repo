# Build the Builder: feature list (v1, 2026-10-10)

P0 = needed to score at all. P1 = large gain in reliability or generalisation. P2 = nice to have.
Evidence for each platform fact is in `research/` (kit maps) and `kit/build-the-builder/docs/`.

## A. The builder (the program we submit)

| # | Feature | Pri | Notes |
|---|---|---|---|
| A1 | One command: `build.py <brief.md…> <openapi.json>` → exported workflow + trace | P0 | Brief B builds on A, so accept several brief files |
| A2 | Tools generated **from OpenAPI in code**: fields, types, enums, required, server URL | P0 | Hidden briefs change fields and enums; tool names stay the same |
| A3 | Brief → **typed Spec** (LLM extraction into a fixed JSON schema) | P0 | Opening text, banned words, identity questions/order/limits/hints, third party + callback window, calendar, bands → deadline + attempts, floors, attempt ladder, verbatim sentences, intents table, multi-product rules, notes, outcome table + precedence |
| A4 | **Raw-material mode**: email + policy extract + amending memo + code list → one Spec | P0 | Memo overrides (incl. "effective from" dates), code list → API enum mapping, conflict log |
| A5 | Spec validation: every outcome/reason/queue/field exists in the OpenAPI; tables complete; 2 extraction passes diffed | P1 | Unresolved items get a logged default, never a silent guess |
| A6 | **Deterministic compiler**: Spec → workflow JSON from templates | P0 | The LLM writes wording, never structure |
| A7 | Generic **code-node library**, parameterised by the Spec | P0 | Date engine, amount engine, callback window, outcome/precedence resolver, multi-product state machine (json/re/datetime only) |
| A8 | Static lint of the workflow | P0 | No `{{ }}` in code, py_compile, targets exist, every var has a source, passthrough ends with `always`, no `null`s, enums match OpenAPI |
| A9 | Local unit tests of the code nodes against a Spec oracle across many `now` values | P1 | Seconds, no simulation slot needed |
| A10 | Deploy: dry-run → save (update in place) → re-update after create (agent_config) → publish → read back + diff (stripped fields) → one live chat turn | P0 | |
| A11 | In-build **self-test + repair loop**: scenarios from the Spec, Claude plays the customer, ledger + own judge, fix, redeploy | P1 | Hard 30-min cap; build time is tie-break 2 |
| A12 | Time-budget manager: stop testing early and ship the best version so far | P1 | |
| A13 | **Trace**: start/end, every model call (model + purpose), Freya ids, #nodes/#tools, tests + results; secrets scrubbed | P0 | Reviewer agent reads it; top 10 get rebuilt |
| A14 | Export with `freya.export_workflow` into `submission/` | P0 | |
| A15 | Reproducibility: fixed prompts, cached Spec, deterministic compile | P1 | The organisers' rebuild must match ours |

## B. The generated phone agent (what the customer meets)

| # | Feature | Pri | Notes |
|---|---|---|---|
| B1 | Opening as a **fixed line** (assistant + bank + recorded); nothing pre-verification is free text | P0 | Avoids banned words before identity |
| B2 | Right-party check: accepted-yes list, 2-ask limit, answer robot/scam questions first, unclear → close | P0 | |
| B3 | Third-party branch: no disclosure, availability, callback window checked in code, one re-ask, wrong number, deceased sentence | P0 | Never call verify/get_account here (automatic scorer fail) |
| B4 | Identity: Spec-driven questions in order, one at a time; pre-hook normalisation (words→digits, DOB→ISO, D-M-Y); wait for complete answers; wrong-answer count from the API; hint handling; decline handling; fail message | P0 | `pieces` style must not burn an attempt |
| B5 | Account load **engine-fired** after verification; code computes per-product facts | P0 | Spoken name, floor, band, deadline, attempts, attempt proposals |
| B6 | Debt statement from a template (one sentence per product, before any ask) | P0 | |
| B7 | Negotiation engine: pay today → per-product ladder; date rules; amount rules (full first, floor once + "rest stays overdue", below floor → floor once); never "how much can you pay"; per-product attempt counts | P0 | Numbers and dates come from code, not the model |
| B8 | **Intents from the Spec's intent table**, not hard-coded: paid, dispute, restructuring, human, hardship (precedence), scam, robot, unknown info, refuses twice | P0 | Hidden briefs add or rename intents |
| B9 | Confirmation: one combined read-back, exact confirm question, clear-yes extraction, change → re-validate → read back again | P0 | |
| B10 | Recording: create_promise values **baked** from validated vars, maxRetries 0, one visible retry, honest failure message, never "recorded" before ok, required sentence after | P0 | |
| B11 | Notes (multi-product): one per product without a promise, none on any transfer, service_error note | P0 | |
| B12 | Closing: outcome/reason computed in code by precedence, reason omitted for promise/paid, goodbye, exactly one close_call as the last call, correct even if the customer hangs up | P0 | |
| B13 | Human-speech robustness: split numbers, corrections, amounts/dates in words, questions back, distractor dates | P0 | The final uses these styles |
| B14 | Turn-level guardrails: `what_to_do_next` post-hook on every tool, speak after every result, max_node_turns + escape, small fast prompts (silence → hang-up) | P1 | |
| B15 | Tie-break play: always lead with the full amount; floor only when the brief allows | P1 | Tie-break 1 = promised amount on passed cases |

## C. Weekend test bed (proves the builder generalises)

| # | Feature | Pri |
|---|---|---|
| C1 | 13 public cases × `--reps 3` × all 5 speech styles, logged per build | P0 |
| C2 | **Raw-material rewrite** of Briefs A and A+B (email / policy / memo / code list), with the same expected results | P0 |
| C3 | Mutated briefs (other bands, holidays, sentences, limits), reusing PUB customers with recomputed expectations | P1 |
| C4 | Re-dated cases (other `now` values) with our own oracle | P1 |
| C5 | Generic mock bank configured from any OpenAPI (other identity fields, enums, failure injection) | P1/P2 |
| C6 | Own Claude judge that mirrors the case checks | P2 |
| C7 | Leakage lint: fail if the builder's code or prompts contain brief-specific values | P0 |

## D. Ops and compliance

| # | Feature | Pri |
|---|---|---|
| D1 | One workspace, one slot per brief, update in place (cap of 200 workflows) | P0 |
| D2 | Secrets only in `env.sh`; trace scrubber; nothing secret in git | P0 |
| D3 | Sunday 17:00–20:00 runbook: build both briefs, check the outputs, export, commit, submit | P0 |

## E. Live experiments to run first (they decide parts of the design)

1. Does the chat API skip an initial code node? Can it run while a simulation is running, or in parallel?
2. Can an `api_call` reach our own host (needed for a mock bank in self-tests)?
3. What does `_failure_count` count, and what does the result envelope look like on a 500?
4. Can hooks import `datetime`?
5. Is `date` extraction anchored to the real clock or to `now`?
6. How does lifecycle `close_call` behave with an unset variable?
