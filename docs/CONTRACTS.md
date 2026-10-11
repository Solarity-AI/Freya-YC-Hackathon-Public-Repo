# CONTRACTS (MVP = M1 + M2) — read this before writing any code

Status: v1, 2026-10-10, written by the lead architect. Binding for agents 1-5.
Design background: `docs/SYSTEM-DESIGN.md` (v3), `docs/edge-cases/EDGE-CASES.md` ("Design changes, ranked"), kit docs `kit/docs/*.md`.
Where this file and SYSTEM-DESIGN.md disagree, **this file wins** (it is the MVP cut).

MVP cut: single extraction route (no dual routes / adjudication / oracle / docmap / consolidate), validate + critic,
runtime brain, compiler, lint, deploy, trace, build.py, local twin harness, chat end-to-end harness.
Deferred to M3+: `q_*` LLM answer nodes, raw-material consolidation, dated overrides, Expr escape hatch, lifecycle hang-up net, `split_ctl`.

---

## 0. Ground rules (all agents)

1. **No Brief A/B values in `builder/` or `runtime/`** (code, prompts, docstrings, comments, defaults). Values come from the Spec.
   `tests/test_contracts.py::test_no_brief_leakage` greps for a token list (bank name, product type values, field names,
   holiday dates, the brief's verbatim sentences, PUB customer names). Examples in docstrings must be generic
   (`<type value>`, `<field value>`, "the 3rd business day"). Brief A/B values live only in `tests/` (golden specs,
   fixtures, scenarios). `harness/` code must also be generic (scenario JSON with A/B data goes in `tests/scenarios/`).
2. **Do not edit files you do not own** (section F). Shared fixtures are read-only. If a contract is wrong or missing,
   implement the most conservative reading, and append one entry under your agent heading in
   `docs/contract-issues.md` (create it if absent; append-only).
3. **Live use.** Never start a Freya simulation. Chat calls (`/api/v2/chat/message`) and bank practice sessions are allowed,
   strictly sequential, normal kit usage only. Credentials: `source kit/env.sh`.
   Never print, copy, log or commit key values. Never write keys into any file under the repo.
4. Python: venv at `repo/.venv` (`.venv/bin/python -m pytest`). Builder/harness code may use 3.11+ features.
   **`runtime/` must be 3.8-compatible syntax, stdlib `json`, `re`, `datetime` only** (no `typing`, no dataclasses,
   no `match`, no walrus in comprehensions, no f-strings containing `{{`/`}}`).
5. No git commits or pushes (the orchestrator does it). `runs/`, `state/`, `results/` are gitignored.
6. Every module function that touches the network must take explicit timeouts and never retry silently more than the contract says.

---

## A. Repo layout

```text
repo/
  builder/                      # the submitted builder (generic)
    __init__.py
    paths.py                    # [lead, done] ROOT, KIT, RUNS, STATE, import_kit()
    build.py                    # CLI orchestrator                                  [agent 5]
    llm.py                      # Claude Agent SDK wrapper, structured JSON output   [agent 5]
    trace.py                    # trace.txt + trace.jsonl, secret scrubbing          [agent 5]
    budget.py                   # wall-clock budget, per-call timeouts               [agent 5]
    openapi_model.py            # OpenAPI -> ToolCatalog                             [agent 3]
    deploy.py                   # kit freya.py wrapper: dry run, save x2, read-back, export [agent 3]
    spec/
      schema.json               # [lead, done] Spec JSON schema (mvp-1)
      vocab.py                  # [lead, done] closed vocabularies (placeholders, situations, kinds)
      defaults.py               # [lead: DEFAULTS data done; agent 5: apply_defaults()]
    pipeline/
      segment.py                # brief files -> BriefDoc                            [agent 5]
      extract.py                # BriefDoc + ToolCatalog -> Spec draft (6 facet calls) [agent 5]
      validate.py               # schema + catalog binding + lexicon checks + defaults [agent 5]
      critic.py                 # brief vs rendered Spec -> patches (1 call, <=1 re-extract) [agent 5]
    prompts/                    # facet/critic prompt templates (generic, synthetic examples only) [agent 5]
    compiler/
      graph.py                  # Spec + ToolCatalog + flags -> wiring + workflow JSON [agent 3]
      render.py                 # compile-time text: tts lines, task messages, extraction schemas, system prompt [agent 3]
      snippet.py                # builds the ctl code string via runtime.bundle      [agent 3]
      lint.py                   # L0 lint + invariants                               [agent 3]
  runtime/                      # pure-stdlib brain, bundled into ONE code node      [agents 1, 2]
    __init__.py
    cal.py                      # calendar + date rules + callback windows           [agent 1]
    parse.py                    # text -> values (amounts, dates, times, digits, yes/no) [agent 1]
    ident.py                    # right-party matcher, identity answers, verify-result classifier [agent 2]
    brain.py                    # phase machine, negotiation, outcome, render, main() [agent 2]
    bundle.py                   # concatenates modules into one brace-safe snippet   [agent 2]
  harness/                      # local + live test harness (generic code)            [agent 4]
    __init__.py
    twin.py                     # local executor of the workflow JSON (E1 semantics)
    mockbank.py                 # local bank from ToolCatalog + case data, kit ledger shape
    scenarios.py                # scenario loader/runner (+ generic generator from a Spec)
    persona.py                  # Claude-played customer (claude_agent_sdk), kit persona text
    chat_e2e.py                 # live chat runner on practice sessions + kit score
  tests/
    conftest.py                 # [lead, done] sys.path + fixtures loaders
    golden/spec-a.json, spec-ab.json        # [lead, done] the ONLY place A/B Spec values live
    fixtures/catalog-kit.json               # [lead, done] expected ToolCatalog for kit/tools/openapi.json
    fixtures/wiring-a.json, wiring-ab.json  # [lead, done] expected wiring for the golden specs
    scenarios/*.json                        # [agent 4] twin scenarios (A/B data allowed here)
    test_contracts.py                       # [lead, done]
    test_<module>.py                        # each agent owns the tests of its modules
  docs/CONTRACTS.md (this), docs/contract-issues.md (append-only)
  pytest.ini, requirements.txt
  kit/                          # vendored official kit, unchanged
```

Runtime outputs of one build: `runs/<slot>/<run_id>/{spec.json, catalog.json, wiring.json, workflow.json,
workflow.export.json, ids.json, twin_report.json, decisions.md, trace.txt, trace.jsonl}` (gitignored; submission
copying is the orchestrator's job). Trace files are named `trace.txt` / `trace.jsonl` (never `*.log`, which is gitignored).

---

## B. The Spec (`builder/spec/schema.json`, `spec_version: "mvp-1"`)

The schema is the source of truth for shape; this section gives **semantics**. Golden examples: `tests/golden/spec-a.json`
(Brief A) and `tests/golden/spec-ab.json` (A + B). Both validate against the schema (`tests/test_contracts.py`).

### B.1 Conventions

- Keys are semantic. Bank strings (outcome, reason, queue, note reason, product type, identity field value, hint value)
  appear only where the schema says "enum value"; `validate.py` checks each against the ToolCatalog enums
  (section D.1). `close_call.reason` has no enum in the kit OpenAPI: its values come from the brief's outcome table.
- Lists are keyed: bands by `key`, ladder rungs by `key`, intents by `id`, questions by `key`, required sentences by `id`.
- `meta` is filled by code (inputs/sha, defaults_applied, decisions, warnings, residual_rules, sources). The compiler
  strips `meta` before embedding the Spec in the runtime.
- `products.fields` is bound by code from the ToolCatalog (`roles.item`), never by the LLM.
- `interpretation` holds the §5.3 defaults (edge-case revisions applied). Missing keys are filled from
  `builder/spec/defaults.py:DEFAULT_INTERPRETATION` and logged.

### B.2 Line templates (closed placeholder vocabulary, `vocab.PLACEHOLDERS`)

| Placeholder | Compile time (`compiler/render.py`) | Runtime (`brain.render`) |
|---|---|---|
| `<bank>` | `bank.name` | same |
| `<self>` | `bank.assistant_self` (with `<bank>` expanded) | same |
| `<customer>` | `addressing.customer` with `<v:X>` -> `{{X}}` | with call-var values |
| `<v:X>` | `{{X}}` (X must be a declared call variable) | `vars[X]` |
| `<f:FIELD>` | not allowed (lint error) | current product's response leaf FIELD |
| `<product>` | not allowed | `products.types[type].spoken` rendered (else `unknown_type_spoken`) |
| `<amount>` `<floor>` `<past_due>` `<rest>` | not allowed | money (B.6) |
| `<date>` `<deadline>` | not allowed | spoken date (C.2 `cal.spoken_date`) |
| `<days_late>` | not allowed | integer |
| `<time>` | not allowed | `HH:MM` |
| `<items>` | not allowed | joined `confirmation.readback_item` renderings ("a, b and c") |

Unknown placeholders are validation errors. Freya `{{ }}` never appears in a Spec line.
Lines spoken before verification (opening, right_party.*, third_party.*, identity.* incl. `fail_line`, hints, and the
`say`/`question` of intents whose scope is within `rp`/`tp`/`id`) must not contain any `banned.before_verification`
word (whole-word, case-insensitive) — validate.py error, lint re-checks the rendered tts.

### B.3 Section semantics (only what is not obvious from the schema)

- `opening.line` + `" "` + `right_party.ask` is the initial tts (node `s_open`). Ask #1.
- `right_party`: `max_asks` counts every agent ask in RP (ask #1 is the opening). A greeting-only reply ("Hello?")
  -> re-ask that **counts** (`interpretation.rp_greeting_first_turn = reask_counts`). A question (robot/scam/who/why)
  -> answer + the next ask, which counts. After the last ask, anything but a clear confirmation -> `on_unresolved`
  (`rp_question_after_last_ask = counts_as_unclear`). A bare "No." -> TP (`bare_no = third_party`).
  Own-name confirmation only in a first-person frame ("this is X", "X speaking", "it's X") on any `name_vars` token.
- `third_party`: TP says nothing beyond the opening; every TP turn ends with the reach (re)ask unless the call closes.
  Callback validity: date in `callback_dates()` (C.2) and time inside a window, and strictly after now if `after_now`.
  An outside offer -> `outside_line` + `reach_reask`, counted against `reask_limit`; past it -> `situations.no_callback`.
  A vague answer -> `vague_line` (free `vague_asks` times), then counts as outside. Valid -> `schedule_callback`
  (book in the turn it is heard, no read-back), `booked_line` + goodbye, close `situations.callback`.
  `turn_budget` TP turns -> `no_callback`. TP intents (deceased, wrong_number) come from `intents` with scope `tp`.
- `identity`: asked one at a time in list order. Answer -> normalised to `wire_format` -> verify tool. Result classes
  (C.4). `max_wrong_total` = min(own count, bank `left` when present). Hints: `say` + re-ask, never counted if
  `counts_as_wrong=false`, at most `max` times. Decline: first refusal/purpose question -> `explain` + exact re-ask;
  `max_declines` consecutive refusals on the same question -> `on_declined`. Fail -> `fail_line` + goodbye -> `on_failed`.
- `statement`: after `all_verified` and `get_account`: `verified_prefix` + `intro` + one `item` per product (api order)
  + first ask (`negotiation.first_ask.single` or `.multi` when > 1 product). One line.
- `bands`: product band = first band with `days_late_min <= days_late <= days_late_max`; none -> nearest band.
  `deadline` is a DateRule evaluated at today (C.2). `attempts` = max ladder rungs proposed for that product.
- `amounts` / `negotiation` / `promise_date`: algorithm in C.6. Floor = `products.types[type].floor`; missing floor
  leaf -> full; `floor_eff = min(floor, full)`; when `floor_eff >= full` the floor offer is skipped (too_much = flat refusal).
- `intents`: evaluated every turn (C.5). `precedence` higher wins; ties broken by `interpretation.intent_tie` order.
  Action kinds:

  | kind | effect |
  |---|---|
  | `answer_continue` | prepend `say`; the pending ask is repeated (neutral if it is a counted offer). Composes with any other intent/act in the same turn. |
  | `resolve_product` | current (or mentioned) product gets situation `situation`; unrecorded agreement for it dropped; `say`; continue with next unresolved product, else close flow. With 1 product this closes the call. |
  | `transfer` | `say`; drop unrecorded agreements if `drop_unrecorded`; `transfer_to_agent(queue)`; no notes if `suppress_notes`; close with `situation`. |
  | `ask_then_transfer` | 1st time: `question` (pending ask `help_first`). Intent again (insists) -> as `transfer` with `say`/`queue`/`situation`. Any other reply -> resume normally. |
  | `offer_transfer` | `say` (sympathy + offer), pending ask `transfer_offer`; persuasion suspended (`suspend_persuasion`). Yes -> transfer to `queue`, close `accept_situation`. No -> products without promise get `decline_situation` (all remaining if `multi_product.hardship_applies_to = all_remaining`), close flow. A customer-named valid date/amount is still recorded (normal C.6). |
  | `count_then_close` | count; below `limit` -> `say` + re-ask; at `limit` -> close with `situation_pre_verification` before `all_verified`, else `situation`. |
  | `close_now` | `say` (+ goodbye), close with `situation` (TP/RP events). |
  | `too_much` | negotiation signal handled by C.6 (no say of its own). |

- `situations`: every SituationId used anywhere must be defined here. `reason: ""` means **no reason leaf** in close_call
  (node `a_close_n`). `note_reason` is the add_note reason when a product ends in this situation.
- `outcomes.precedence` (evaluated top-down, first match wins) — closed atoms:

  | `when` | true if | `use` |
  |---|---|---|
  | `transfer_done` | a transfer tool call succeeded (or was attempted and the call is closing as transfer) | `transfer_situation` |
  | `any_promise_recorded` | >= 1 create_promise succeeded | `situation:S_X` |
  | `call_situation` | a call-level situation was set (RP/TP/ID closes, refuse-to-talk, account error) | `call_situation` |
  | `all_products:S_X` / `any_product:S_X` | product situations | `situation:S_X` |
  | `else` | always | `first_product_excluding:S_A[,S_B]` = situation of the first product (api order) whose situation is not excluded; unresolved products count as `unresolved_product_situation` |

- Before any situation is decided, `resolve_outcome` returns a phase default so `co`/`cr` are always valid:
  RP -> `right_party.on_unresolved`; TP -> `third_party.situations.no_callback`; ID -> `identity.on_declined`;
  ACCT and later -> the precedence table (unresolved products = `unresolved_product_situation`).
- `notes`: when `enabled`, at close time (before the goodbye), unless a transfer happened and `skip_if_transfer`:
  one `add_note(product, situations[S].note_reason)` per product without a recorded promise (every product, any count,
  `notes_scope = every_product_without_promise`). `scope: call` -> one call-level note (`a_note_call_1`, no product field).
- `multi_product`: first ask covers all products; "yes" -> all full today; otherwise products one by one in api order,
  each starting at attempt 1; attempts per product. One named date for everything -> per product, clamp to its own
  deadline and say `clamp_line` before the read-back (and the read-back item uses the clamped date).
  `dispute_or_paid_continues` true -> `resolve_product` intents continue with other products.
- `confirmation`: read-back = `readback` with `<items>` + " " + `question`. Clear yes (C.6) -> record. A change ->
  revalidate (C.6) -> read back again. Bare no -> `what_to_change`.
- `recording`: `tries` per product; say "recorded" lines only after the success predicate is true. All tries failed ->
  product situation `on_all_failed` (A: closes no_promise/service_error; B: noted service_error, others kept).
- `required_sentences`: appended by trigger, `once` = emitted at most once per call; never appended if the composed
  say already contains the exact text. Triggers: `after_promise_recorded` (once, after all creates of the turn),
  `after_verified`, `after_statement`, `before_close`, `on_situation:S`, `on_intent:id`, `on_outcome:o`.
- `closing.goodbye` is always the last sentence before `close_call`. `per_situation[S]` is inserted before it.
- `lines`: canned runtime lines (closed slot set; generic defaults in `defaults.DEFAULT_LINES`).

### B.4 DateRule semantics (`cal.eval_date_rule`)

`today` = date of `now`. Business day = weekday in `calendar.business_weekdays` and not a holiday
(explicit `holidays` plus `holiday_rules` expanded for today.year-1 .. today.year+2).

| kind | result |
|---|---|
| `today` | today |
| `next_business_day` | first business day > today |
| `nth_business_day_after_today` (`n`) | `count_from=after_today`: the n-th business day strictly after today (today never counts). `including_today`: today counts as #1 if it is a business day |
| `nth_calendar_day_after_today` (`n`, `roll`) | today + n days, then roll (`none`/`next_bd`/`prev_bd`) |
| `last_business_day_of_week` (`if_today`) | last business day of today's week (week starts `week_start`); if that is today and `if_today=next_week`, or it is before today, use next week's |
| `end_of_month` (`roll`) | last calendar day of today's month, rolled |
| `last_business_day_of_month` | last business day of today's month (if < today: next month's) |
| `deadline` | the product's deadline (ctx) |
| `fixed` (`date`) | that date |
| `min` / `max` (`args`) | min/max of the evaluated args |

Example (generic): with Mon-Fri business days, no holidays, today Wednesday 2026-01-07: `nth_business_day_after_today n=3`
-> Monday 2026-01-12; `last_business_day_of_week` -> Friday 2026-01-09.

### B.5 AmountRule semantics (`brain.eval_amount`), integer cents

`full` = product `past_due`; `floor` = the type's floor rule evaluated (missing -> full) then `min(floor, full)`;
`field` = product leaf; `percent_of_full` = full * pct / 100 rounded by `rounding` (default half_up) to the cent;
`fixed` = value; `min`/`max` of args; `floor_if_too_much_else_full` = floor if the product's `too_much` flag is set else full.

### B.6 Money

Internally **integer cents** everywhere (parse, compare, store). Spoken: `"420"` when whole, `"2,125.10"` otherwise,
with `currency.symbol` before / `currency.word` after per `position`. Wire: `"%d.%02d"` (e.g. `"420.00"`) for a
`number` field with `scale` 1; integer cents string when `scale` 100.

### B.7 Defaults (`builder/spec/defaults.py`)

`DEFAULTS` = a partial Spec of generic values (lines, interpretation, budgets) merged into missing keys only.
`DEFAULT_INTERPRETATION`, `DEFAULT_LINES`, `BUILTIN_TOPICS` (generic code topics per stage, D.4) are data owned by the lead;
`apply_defaults(spec) -> (spec, applied_pointers)` is implemented by agent 5.

---

## C. Runtime contract (`runtime/`)

### C.1 Packaging and the ctl code node

- `runtime.bundle.make_snippet(rspec: dict) -> str` returns the complete `code` string for the `ctl` node:

  ```text
  import json
  import re
  import datetime
  <cal.py body>  <parse.py body>  <ident.py body>  <brain.py body>     (MODULE_ORDER)
  RSPEC_HEX = '<hex of json.dumps(rspec, separators=(",", ":"), ensure_ascii=True)>'
  try:
      main(vars, RSPEC_HEX)
  except Exception:
      vars['nx'] = 's_safe'
  ```
- Module rules for bundling: only stdlib `import json|re|datetime` / `from datetime import ...` lines (hoisted);
  sibling imports exactly `from .cal import a, b` (stripped by the bundler); no `if __name__` blocks; **top-level names
  unique across all runtime modules** (bundler asserts with `ast`); private helpers prefixed `_c_` (cal), `_p_` (parse),
  `_i_` (ident), `_b_` (brain). The bundled code must contain no `{{` and no `}}` anywhere (write nested literals across
  lines or build them stepwise; check with `bundle.check_brace_safe`), must `compile()`, and must stay
  <= 200 KB including the hex (lint warns above 100 KB; the platform's code-size limit is unknown, so keep the runtime
  lean: target <= 70 KB of bundled code; the A+B rspec is ~25 KB, i.e. ~51 KB as hex).
- Every runtime function must be **total on bad text input** (return the documented "none"/None result, never raise on
  odd strings). `brain.main` additionally wraps everything in try/except and never raises.

### C.2 `runtime/cal.py` (agent 1) — signatures (dates are `datetime.date`, times are minutes since midnight)

```python
def parse_now(s) -> tuple               # "2026-01-07T11:00" (also ' ' sep, seconds, 'Z') -> (date, minutes); bad -> (None, None)
def iso(d) -> str                       # date -> "YYYY-MM-DD"
def from_iso(s) -> object               # "YYYY-MM-DD" -> date | None
def prepare(calendar, today) -> dict    # Spec.calendar -> CAL = {"wd": [ints], "hol": [iso...] (sorted, rules expanded
                                        #   today.year-1..+2), "week_start", "count_from", "numeric_order", "this_next"}
def is_bd(cal, d) -> bool
def next_bd(cal, d, include=False) -> date      # first business day > d (>= d if include)
def prev_bd(cal, d, include=False) -> date
def add_bd(cal, d, n) -> date                   # n-th business day strictly after d; n == 0 -> d
def week_start_of(cal, d) -> date
def last_bd_of_week(cal, d) -> object           # last business day in d's week, or None if the week has none
def end_of_month(d) -> date
def last_bd_of_month(cal, d) -> object
def expand_holiday_rules(rules, years) -> list  # HolidayRule list -> sorted iso strings
def eval_date_rule(cal, rule, today, ctx) -> object   # B.4; ctx = {"deadline": date|None}; unknown kind -> None
def weekday_date(cal, today, weekday, which) -> date  # which in "bare" | "this" | "next"; uses cal["this_next"]
                                                      # bare = nearest on/after today (today counts)
def spoken_date(d, today) -> str        # "Friday, 9 January" (+ " 2027" if year != today.year); English tables, never strftime names
def wire_date(d, fmt) -> str            # numeric tokens only: %Y %m %d %y; anything else copied literally
def wire_time(minutes, fmt) -> str      # %H %M (zero padded); default "%H:%M"
def callback_dates(cal, cb, today) -> list            # Spec.third_party.callback.date_rule -> sorted list of dates
def callback_check(cal, cb, today, now_min, d, t_min) -> str   # "ok" | "outside" | "past"
```

### C.3 `runtime/parse.py` (agent 1) — text -> values

All functions take the raw `u_text` (or a slot) and are case/punctuation tolerant. Correction markers
(`sorry`, `I mean`, `no wait`, `actually`, `rather`, `make that`, `scratch that`, `or rather`) -> only the last clause
counts (`last_clause`). Past-tense / event-noun clauses (paid, was, last, ago, yesterday-with-past-verb; wedding,
birthday, appointment, party, salary day statements) are ignored for proposals.

```python
def norm(text) -> str                   # lowercase, unify quotes/dashes, collapse spaces, keep [a-z0-9 :./,'-]
def last_clause(text) -> str
def words_to_int(text) -> object        # "four hundred and twenty" -> 420; "twenty-one" -> 21; None if no number
def parse_amount(text, ctx=None) -> dict
    # ctx = {"known": [cents...], "lo": cents|None, "hi": cents|None}
    # -> {"kind": "amount", "cents": int, "hedged": bool} | {"kind": "zero"} | {"kind": "incomplete", "frag": str}
    #    | {"kind": "none"}
    # integer cents (Decimal-free integer math); "<w> dollars and <w> cents", "point five", "twelve fifty"
    # (ranked: known figure, then inside [lo, hi], then larger), "$", "bucks", "flat", "even" stripped,
    # thousands separators "1,250"; drops ordinals, numbers after "on the", time phrases, digit runs >= 8,
    # numbers equal to days_late-like small ints only when ctx says so.
def parse_date(text, today, cal) -> dict
    # -> {"kind": "date", "date": iso} | {"kind": "vague", "what": str} | {"kind": "past", "date": iso}
    #    | {"kind": "incomplete", "frag": str} | {"kind": "none"}
    # today/tonight/tomorrow/day after tomorrow; weekday names with this/next/bare (cal["this_next"]);
    # "the 20th", "20th of <month>", "<month> 20", "20/10", "20.10.2026" in cal["numeric_order"];
    # "in N days", "a week from today". Vague: next week, end of the month, when my salary comes, payday,
    # later, soon, sometime, in a few days, beginning of next month. Past date in the current reading -> "past".
def parse_time(text, now_min=None) -> dict
    # -> {"kind": "exact", "min": int, "alts": [int...]}   (bare hour: alts = [h*60, (h+12)*60] when h < 12)
    #  | {"kind": "range", "lo": int, "hi": int} | {"kind": "part", "part": "morning"|"afternoon"|"evening"}
    #  | {"kind": "vague"} | {"kind": "none"}
    # "half past six", "6.30 pm", "18:30", "quarter to five", "six thirty", "noon", hedges (around/about/-ish) = exact,
    # "in N minutes/hours" relative to now_min.
def parse_day_and_time(text, today, now_min, cal) -> dict   # {"date": iso|"", "date_kind": ..., "time": parse_time(...)}
def parse_dob(text, numeric_order, today) -> dict
    # -> {"kind": "date", "y": int, "m": int, "d": int, "month_word": bool}
    #  | {"kind": "incomplete", "have": {"y"?, "m"?, "d"?}} | {"kind": "invalid"} | {"kind": "none"}
    # years: digits, "nineteen eighty-eight", "eighty-eight" (2-digit -> century giving age 18-100),
    # "two thousand and five"; numeric-only dates read in numeric_order; month words win over order.
def parse_digits(text) -> str           # spoken digits -> "0358"; zero/oh/o/nought; double/triple; "forty-four seventy-one"
                                        # -> "4471"; homophones for/to/too/won/ate; "" if none
def parse_year(text) -> object          # int | None
def parse_alnum(text) -> str            # letters (incl. NATO words, "double A") + digits, uppercase, no spaces
def yes_no(text) -> dict                # {"yn": "yes"|"no"|"", "hedge": bool, "cond": bool, "corr": bool,
                                        #  "cant": bool, "question": bool}; "yes, but I can't" -> cant=True
def is_greeting_only(text) -> bool      # "hello?", "hi", "yes?" (with question mark), "go ahead", "who's this" -> True
def is_question(text) -> bool
def has_completed_payment(text) -> bool # past/perfect pay verb (paid, have paid, sent it) and no future marker
def match_any(patterns, text) -> bool   # case-insensitive regexes; invalid regex ignored
```

**Examples** (generic; today = Wednesday 2026-01-07, Mon-Fri business days, no holidays, DMY):

| Call | Result |
|---|---|
| `parse_amount("I can do two hundred and fifty dollars")` | `{"kind": "amount", "cents": 25000, "hedged": False}` |
| `parse_amount("about 99.5")` | `{"kind": "amount", "cents": 9950, "hedged": True}` |
| `parse_amount("twelve fifty", {"known": [125000], "lo": 10000, "hi": 200000})` | cents `125000` (known figure wins over 1250) |
| `parse_amount("nothing at all")` | `{"kind": "zero"}` |
| `parse_amount("my wedding is on the 30th")` | `{"kind": "none"}` |
| `parse_date("this Friday", today, cal)` | `{"kind": "date", "date": "2026-01-09"}` |
| `parse_date("next Friday", today, cal)` | `{"kind": "date", "date": "2026-01-16"}` (this_next.next = following_week) |
| `parse_date("the 20th", today, cal)` | `{"kind": "date", "date": "2026-01-20"}` |
| `parse_date("the 5th", today, cal)` | `{"kind": "date", "date": "2026-02-05"}` (bare day number = next occurrence) |
| `parse_date("end of the month", today, cal)` | `{"kind": "vague", "what": "end_of_month"}` |
| `parse_date("Friday, sorry, I mean Monday", today, cal)` | `{"kind": "date", "date": "2026-01-12"}` |
| `parse_time("around half past six")` | `{"kind": "exact", "min": 390, "alts": [390, 1110]}` |
| `parse_time("after lunch")` | `{"kind": "vague"}` |
| `parse_dob("the third of May nineteen seventy-nine", "DMY", today)` | `{"kind": "date", "y": 1979, "m": 5, "d": 3, "month_word": True}` |
| `parse_dob("03/05/1979", "DMY", today)` | `y 1979, m 5, d 3, month_word False` |
| `parse_dob("May the third", "DMY", today)` | `{"kind": "incomplete", "have": {"m": 5, "d": 3}}` |
| `parse_digits("oh three five eight")` | `"0358"` |
| `parse_digits("double two seven nine")` | `"2279"` |
| `yes_no("Yes, but I can't do it today")` | `{"yn": "yes", "cant": True, ...}` |
| `yes_no("I suppose so, maybe")` | `{"yn": "yes", "hedge": True, ...}` |
| `cal.add_bd(cal, today, 3)` | `2026-01-12` |
| `cal.callback_check(cal, cb, today, 660, from_iso("2026-01-07"), 600)` | `"past"` (10:00 < now 11:00) |

### C.4 `runtime/ident.py` (agent 2)

```python
def rp_classify(text, u_act, name_tokens) -> dict
    # {"cls": "confirm"|"deny"|"third_party"|"question"|"greeting"|"unclear", "q": "robot"|"scam"|"who"|"why"|"other"|""}
    # code decides; u_act is only a hint. Different first name in a self-reference beats "yes".
def id_answer(q, text, frag, today) -> dict
    # q = one Spec identity question. -> {"status": "complete", "wire": str} | {"status": "incomplete", "frag": str}
    #   | {"status": "invalid"} | {"status": "none"}. Never returns "complete" unless wire matches q.pattern/length.
    # "last N" questions: a longer digit string yields its trailing N digits.
def verify_class(res) -> str
    # res = {"s","verified","left","all","hint","err"} raw var strings ("pending" = absent).
    # -> "all_done" | "verified" | "hint:<value>" | "wrong" | "unreadable" | "lockout" | "transport_fail"
    # transport_fail: s absent/pending. unreadable: s false and not counted (left unchanged / err mentions format).
    # lockout: left == 0 or err says locked. hint: hint present (overrides verified/left).
```

**Examples:** `id_answer(q_digits_len4, "it's oh three five eight", "", today)` -> `{"status": "complete", "wire": "0358"}`;
`id_answer(q_digits_len4, "oh three", "", today)` -> `{"status": "incomplete", "frag": "03"}`, then
`id_answer(q_digits_len4, "five eight", "03", today)` -> complete `"0358"`;
`id_answer(q_date_iso, "the third of May nineteen seventy-nine", "", today)` -> complete `"1979-05-03"`;
`verify_class({"s": "true", "verified": "false", "left": "2", "all": "false", "hint": "pending", "err": "pending"})` -> `"wrong"`;
`verify_class({"s": "pending", ...})` -> `"transport_fail"`;
`rp_classify("This is Jordan speaking", "yes", ["Jordan", "Lee"])` -> `{"cls": "confirm", "q": ""}`;
`rp_classify("Yes? Who is this?", "question", [...])` -> `{"cls": "question", "q": "who"}`;
`rp_classify("She's at work", "no", [...])` -> `{"cls": "third_party", "q": ""}`.

### C.5 `runtime/brain.py` (agent 2)

```python
def main(vars, rspec) -> None           # rspec = hex string or dict. NEVER raises. Reads/writes vars per C.7.
def step(rspec, st, inp) -> tuple       # pure core for unit tests: -> (new_st, writes: dict[str,str])
    # inp = {"call": {call vars}, "sensors": {"u_text","u_act","u_topic","u_date","u_amt","u_time","u_ans"},
    #        "results": {node: {role: raw string}}, "entered_from": node key or ""}
def render(template, ctx) -> str       # B.2 placeholders; unknown placeholder -> left out, never raises
def eval_amount(rule, prod, st) -> int  # cents, B.5
def resolve_outcome(spec, st) -> tuple  # -> (co, cr, cmode) with cmode "r" if cr != "" else "n"
def plan_writes(rspec, st) -> dict      # write-chain plan (C.8) -> writes
def read_result(vars, wiring, node, role) -> str   # mapped var, then "<node>_response.data.<leaf>",
                                                   # then "<tool>_response.data.<leaf>", else "pending"
def read_products(vars, wiring, node) -> list      # list | JSON string | python-repr string | flattened keys
                                                   # "<prefix>.products.<i>.<leaf>" -> list of dicts
```

**Turn algorithm** (each `ctl` entry):
1. `vars['nx'] = <safe listen node>`, `vars['dbg_step'] = 'start'` first. Decode rspec, load `st` (JSON; empty -> new
   call in phase OPEN). `today, now_min = cal.parse_now(vars[spec.call_variables.now])`.
2. If `st.plan` is set (C.8): reconcile planned api nodes in plan order (success / first failure).
   Else if `st.await` is an api node: classify its result. Else: a customer turn — read sensors.
3. Customer turn: evaluate **all** intents every turn: candidates = (`u_topic` if in the stage's scope) ∪
   (intents whose `keywords` match `u_text`) ∪ built-in signals; resolve by precedence (+ `intent_tie`);
   `answer_continue` intents compose (their `say` is prepended) with the winning action / act handling.
   Built-in classification of the act from code (`parse.*`, `ident.*`), with `u_act` only as a hint.
   Values are parsed from `u_text` first; a slot (`u_date u_amt u_time u_ans`) is used only when it is grounded
   (its digits/words also occur in `u_text`), never the other way round.
4. Compose ONE `say` (order: interjection answers, results/acknowledgement, due required sentences, the next ask).
5. Decide `nx`; before routing to an api node W preset every `r_W_<role>` to `"pending"` and write its `b_W_<field>`;
   before routing to a listen node reset `u_text,u_act,u_topic,u_date,u_amt,u_time,u_ans` to `''`.
6. Always write `co`, `cr`, `cmode` (current `resolve_outcome`), `st`, `ph`; write `nx` **last**.
7. On any exception inside: `dbg_err` = message, `errs += 1`; say = `lines.clarify`, `nx` = the awaited listen node
   (or safe). Two consecutive errors -> close flow with the current outcome.

### C.6 Phases, negotiation and accounting

Phases (`st.ph`): `OPEN` (before first ctl) -> `RP` -> `TP` | `ID` -> `ACCT` -> `NEG` (per product `st.k`) -> `CONF`
-> `WRITE` -> `NOTES` -> `XFER` -> `BYE` -> `CLOSE`. Listen node per phase: RP `s_rp`, TP `s_tp`, ID `s_id`, NEG `s_neg`,
CONF `s_conf`, otherwise `s_safe`. Tools reachable per phase (structural guards, mirrored by lint): verify only from ID;
account only after `all_verified`; promise only after a clear yes in CONF; notes only in NOTES; callback only from TP;
transfer only from ID/NEG/CONF (never TP/unconfirmed RP); close only from BYE.

**Negotiation per product** (pending offer `O = {kind, amount, date}`; kinds `first_ask`, `rung:<key>`, `floor`,
`next_bd`, `deadline`, `vague_ask`, `above_full`, `pay_on_date`, `transfer_offer`, `help_first`):
1. Intents first (C.5 step 3); `offer_transfer` suspends persuasion for the rest of the call.
2. Clear acceptance of O (`parse.yes_no` yes, no hedge/condition/cant, no grounded different value) -> agreed = O.
3. Proposal (grounded future amount and/or date; never a refusal, `proposal_is_never_refusal`):
   amount = proposed or O.amount; date = proposed or O.date (first_ask: today).
   amount < floor_eff -> `below_floor.say` + floor offer once (shared `floor_offered` flag) else flat refusal;
   amount > full -> `above_full_offer`; past date -> `past_date`; vague -> `date_ask_exact` once then deadline offer;
   date > deadline -> `deadline_offer` (B multi one-date: clamp + `clamp_line`); non-business date <= deadline ->
   `next_bd_offer` with the next business day; all valid -> agreed (no attempt used).
4. `too_much`: if floor not yet offered and floor_eff < full -> floor offer (date per `too_much.date`) + `say_rest`;
   else flat refusal. A grounded in-range proposal in the same turn wins (`proposal_beats_too_much`).
5. Flat refusal or non-answer (hedge with no value): next ladder rung for the product's band whose attempt number is
   > attempts used and whose (amount, date) pair was not refused; propose it (attempts_used += 1). None left or
   attempts_used == band.attempts -> product situation `negotiation.on_exhausted`.
   Refusing a corrective offer (floor / next_bd / deadline / clamp / above_full) = flat refusal.
6. Question -> answer if intent, else `lines.no_info`, then neutral re-ask. Unclear -> `lines.clarify` + exact re-ask;
   2 consecutive unclear -> non-answer.
7. Product resolved (agreed or situation) -> next unresolved product (`first_ask` not repeated; rung 1 of attempt 1),
   else CONF if any agreed, else close flow.

**Per-turn accounting** (which turn class consumes which counter):

| Turn class | Phase | Counter consumed |
|---|---|---|
| greeting-only first reply | RP | `rp.asks` +1 (the re-ask counts) |
| non-confirming, non-TP reply | RP | `rp.asks` +1; at `max_asks` -> `on_unresolved` |
| question (robot/scam/who/why) | RP | none for the question; the following ask counts |
| third-person / not-here / handover | RP | none; go TP (or RESTART on handover: opening + ask, counters reset) |
| outside callback offer | TP | `tp.outside` +1 (limit `reask_limit`) |
| vague time | TP | `tp.vague` +1 (free up to `vague_asks`) |
| any TP turn | TP | `tp.turns` +1 (limit `turn_budget`) |
| verify result `wrong` | ID | `id.wrong` +1 (total and per question) |
| verify result `hint:*` | ID | `id.hints[value]` +1, not wrong |
| `unreadable` / incomplete / invalid answer | ID | none (`ask_full` / `continue_prompt`) |
| refusal / purpose question | ID | `id.declines[q]` +1 (consecutive; reset by an answer); explain once |
| robot/scam/who in ID | ID | none, exact re-ask |
| `transport_fail` | ID/ACCT/WRITE | `st.retries[node-kind]` +1; resend once via the next unrolled node, then service error |
| proposal / acceptance | NEG/CONF | none |
| flat refusal / non-answer | NEG | `prod.attempts_used` +1 when a rung is proposed |
| too_much / below floor | NEG | `prod.floor_offered` (once) |
| vague date | NEG | `prod.vague_asks` +1 |
| refuse-to-talk words | any | `talk_refusals` +1 (limit = intent `limit`) |
| human request | ID/NEG/CONF | `human_asked` (1st -> help question, 2nd -> transfer) |
| hedge at CONF | CONF | `conf.reasks` +1; 2nd -> flat refusal of the read-back offer |
| any customer turn | all | `st.turns` +1; hard cap 40 -> close with the resolved outcome |

### C.7 Variables contract (all values are strings)

Read by `ctl`: call variables (`spec.call_variables.declared`); `st`; sensors `u_text u_act u_topic u_date u_amt u_time u_ans`;
`r_<node>_<role>`; fallbacks `<node>_response.data.*`, `<tool>_response.data.*`, `<node>_success_count`, `<node>_failure_count`.

Written by `ctl`:

| Var | Meaning |
|---|---|
| `say` | the one line the next listen node / `s_bye` speaks via tts `{{say}}` |
| `nx` | next node key; **written last** |
| `st` | JSON state (brain-private shape, but must include `ph`, `await`, `turns`, `k`, `prods`, `plan`, `errs`) |
| `ph` | copy of `st.ph` (debug / twin assertions) |
| `co`, `cr`, `cmode` | close outcome, close reason (`''` if reasonless), `"r"` / `"n"` |
| `b_<node>_<field>` | request values baked into api node `<node>` (only runtime-sourced fields, see wiring.nodes) |
| `r_<node>_<role>` | preset to `"pending"` before entering/planning `<node>`; overwritten by response_mapping |
| `wn_<node>` | next node of the write chain after `<node>` succeeds (C.8) |
| `u_*` | reset to `''` before routing to a listen node |
| `dbg_step`, `dbg_err` | last step id, last caught exception text (<= 200 chars) |

Booleans from tools arrive as `"true"`/`"True"`/`"false"`/`"False"`; compare case-insensitively.
A value `"pending"`, `""`, `"None"`, `"null"` or an absent key means "no result".
The first ctl entry of every call (sim and chat alike) is the customer's reply to ask #1 spoken by `s_open`.

### C.8 Runtime Spec (`rspec`) and wiring

`rspec = {"v": 1, "spec": <Spec without meta>, "wiring": <wiring>}`. `snippet.runtime_spec` also strips
extraction-only fields (`intents[*].label/description/examples/negatives`, `right_party.confirm_examples/non_confirm_examples`);
the runtime must not read them (keywords stay). Wiring is produced by
`compiler.graph.wiring(spec, catalog, flags)`; exact expected output for the golden specs is in
`tests/fixtures/wiring-a.json` / `wiring-ab.json` (agent 2 develops against these). Keys:

```text
listen   {open, rp, tp, id, neg, conf, safe} -> node keys        bye "s_bye", bye_mode "pass"|"apinode"|"listen", end "e_end"
api      verify [N_v nodes], acct [2], promise [[per try] per product], note [[1] per product] (if notes product-scoped),
         note_call [1] (if call-scoped), cb [2], xfer [2], close_r, close_n
nodes    {node: {tool, body: {field: var}, res: {role: var}, res_leaf: {role: leaf}}}
         body lists ONLY runtime-sourced fields (customer is baked from the call variable; close uses co / cr)
roles    {tool: {req: {role: field}, res: {role: leaf}, item: {role: leaf}}}
success  {tool: {role, kind: "bool_true"|"enum_in"|"http_ok_no_error", values}}
wire     {"tool.field": {type, format, scale}}
identity_mode "selector" | "per_field"     chain bool     chainable [node keys]     flags {...}
```

N_v = min(12, questions + max_wrong_total + Σ hints.max + 2). Products: `products.max` rows; tries: `recording.tries`.

**Write chain** (`chain = true`): at the moment ctl decides to write (CONF clear yes, transfer, callback, close with notes),
it builds `plan = [promise try-1 nodes of agreed products (api order)] + [note nodes of products without promise,
if notes apply] + [xfer node if transferring] + ["s_bye"]`; writes `b_*` for every planned node, presets their `r_*`
to `"pending"`, writes `wn_<plan[i]> = plan[i+1]`, the final `say` for `s_bye` (results as if all succeed + required
sentences + goodbye), `co`/`cr`/`cmode` for the all-success path, `st.plan = plan`, and `nx = plan[0]`.
The graph follows the chain on success without re-entering ctl. On a failure the node's `always -> ctl` fires;
ctl reconciles the plan (first non-success node in plan order is the failed one), then retries (`a_promise_k_2`),
records service errors, and re-plans the rest. A tool kind whose success is `http_ok_no_error` is never chained.

---

## D. Graph template (compiler) and tool binding

### D.1 ToolCatalog (`builder/openapi_model.load(path) -> dict`, JSON-serialisable)

Exact expected output for the kit OpenAPI: `tests/fixtures/catalog-kit.json` (agent 3's test compares field by field).

```text
{catalog_version: 1, openapi_sha256, server (servers[0].url, no trailing /), identity_mode: "selector"|"per_field",
 tools: {<tool>: {method, path, url, summary, required: [...],
          request: {field: {type, required, enum, format, pattern, description, min_length, max_length, example,
                            wire_format, scale}},
          response: {leaf: {type, path: "data.<leaf>", enum, description, items?: {leaf: {type, enum, description}}}},
          roles: {request: {role: field}, response: {role: leaf}, item: {role: leaf}},
          success: {role: "s", kind, values}, write: bool, max_retries: int}},
 enums: {identity_field, hint, product_type, note_reason, queue, outcome, close_reason},
 reasonless_outcomes_hint: [...], warnings: [...]}
```

- The 7 tool names are fixed (`verify_identity, get_account, create_promise, add_note, schedule_callback,
  transfer_to_agent, close_call`); a missing one -> `CatalogError`. `$ref`/`allOf` resolved. YAML accepted if PyYAML
  is installed, else JSON only (log).
- Role vocabulary — request: `customer selector answer product amount date time datetime reason text queue outcome`;
  response: `s err verified left all hint products pid`; item: `id type past_due days_late`. Bound by exact name,
  then generic name patterns (`ok|success|recorded|accepted`; `error|message`; `*left*|*remaining*`;
  `all_*`; `*hint*`; arrays of objects for products), then type/format/description; each binding logged. Never
  hard-code a kit field name (the leakage test greps for them). Missing required roles -> `CatalogError`.
- `success`: boolean leaf named like ok/success/recorded -> `bool_true` values `["true","True"]`; status enum ->
  `enum_in` success-like values; none -> `http_ok_no_error`.
- `wire_format`: `format: date` -> `%Y-%m-%d`; `date-time` -> `%Y-%m-%dT%H:%M:%S`; description "HH:MM" -> `%H:%M`;
  else from pattern/example; else `""`. `scale` 100 when name/description says cents/minor units.

### D.2 Workflow top level

`{"initial_node": "s_open", "system_prompt": <render.system_prompt>, "nodes": {...}, "global_nodes": {},
"test_variables": {<declared call var>: "<generic placeholder>"}}` — no `agent_config` (deploy patches it via
kit `save_workflow`), no `null` anywhere, no `context_variables`, no `matches_intent`, no model-callable tools.

### D.3 Node table (default flags)

| Node | node_type | passthrough | on_enter | extraction | transitions (in order) | notes |
|---|---|---|---|---|---|---|
| `s_open` | conversation (initial) | no | tts: opening + rp ask (compile-time, `{{title}}`-style vars) | `X_rp` | `always -> ctl` | task_message: "Say exactly this and nothing else, and do not call any tool: «<same text>»" (chat route speaks this on turn 1) |
| `s_rp` `s_tp` `s_id` `s_neg` `s_conf` | conversation | no | tts `{{say}}` | `X_rp` / `X_tp` / `X_id` / `X_neg` / `X_conf` | `always -> ctl` | task_message `LISTEN_TASK` (E1-verified wording); `max_node_turns` 100, `max_turn_transition` "ctl" |
| `s_safe` | conversation | no | tts `lines.clarify` (compile-time) | `X_safe` (u_text, u_act) | `always -> ctl` | target of ctl's final `always` |
| `ctl` | code | yes | silent | – | (1) per api node W: `{and: [nx equals W, r_W_s equals pending]} -> W`; (2) per L in `s_rp s_tp s_id s_neg s_conf s_bye`: `nx equals L -> L` (never `s_open`, never `s_safe`); (3) `always -> s_safe` | pre_action `code_exec` with `code` default = snippet, `timeout_ms` 20000; `passthrough_default_transition` s_safe |
| `a_verify_i`, `a_acct_i`, `a_promise_k_t`, `a_note_k`, `a_note_call_1`, `a_cb_i`, `a_xfer_i` | api_request | yes | silent | – | chainable writers: per chain target T `{or: [{and: [wn_W equals T, r_W_s equals v, (r_T_s equals pending if T is api)]} for v in success.values]} -> T`; then `always -> ctl` | pre_action = bound tool (D.5); node-level `response_mapping` `data.<leaf> -> r_W_<role>`; `suppress_tool_results` true; `disable_inactivity_monitor` true; `passthrough_default_transition` ctl |
| `s_bye` (bye=pass) | conversation | yes | tts `{{say}}` | – | `cmode equals r -> a_close_r`; `always -> a_close_n` | task_message silent; `passthrough_default_transition` a_close_n |
| `a_close_r` / `a_close_n` | api_request | yes | silent | – | `always -> e_end` | close_call with `{{co}}` + `{{cr}}` / with `{{co}}` and **no reason leaf at all** |
| `e_end` | end_call | – | silent | – | `[]` | terminal `end_call`, `message_mode: none`, function name `call_closed`; `disable_inactivity_monitor` true |

Chain targets of a chainable writer = all other chainable writers + `s_bye` + `a_close_r` + `a_close_n`.
Lint forbids two transitions with the same target in one node (the engine merges them, and an unconditional merge
would jump the queue) and forbids `ctl`/`s_safe` as conditional targets of their own `always`.
Flags: `bye=apinode` (no s_bye; goodbye tts as on_enter of the close nodes, ctl routes straight to `a_close_*`),
`bye=listen` (s_bye is a normal listen node; ctl closes on the next turn). `write_chain=off` -> api nodes only `always -> ctl`.

`LISTEN_TASK` = "You have already said the line. Say nothing else and do not call any tool. No tool call is allowed in
this turn. If you must speak, repeat exactly: {{say}}"

### D.4 Extraction schemas (`render.extraction_schema(stage, spec)`)

All fields `type: "string"` (never `date`), every field has `min_confidence`.

| Field | Stages | Description (generic) | min_conf |
|---|---|---|---|
| `u_text` | all | "The customer's most recent message, copied word for word, including numbers exactly as spoken." | 0.3 |
| `u_act` | all | enum `yes, no, proposal, answer, question, refuse, chatter_only, unclear`; "Classify ONLY the most recent customer message..." | 0.5 |
| `u_topic` | rp tp id neg conf | enum = Spec intents whose `scope` contains the stage + `BUILTIN_TOPICS[stage]` + `none`; <= 12 values (if more: keep highest precedence, log; regex backstop covers the rest); description lists `value: description (e.g. "ex1"; not "neg1")` | 0.5 |
| `u_date` | tp neg conf | "The day the customer proposes in this message, as said. Empty if none." | 0.4 |
| `u_amt` | neg conf | "The amount the customer proposes in this message, as said. Empty if none." | 0.4 |
| `u_time` | tp | "The time of day offered in this message, as said. Empty if none." | 0.4 |
| `u_ans` | id | "The answer to the security question in this message only, as said. Empty if none." | 0.4 |

`BUILTIN_TOPICS` (generic, `defaults.py`): rp `other_person`, `unavailable`, `hold`; tp `unavailable`; id `purpose_question`.

### D.5 Tool binding on api nodes (from the ToolCatalog only)

```json
{"type": "function", "config": {"timeoutMs": 12000, "maxRetries": <catalog max_retries>},
 "function": {"name": "<tool>", "handler": "__function__:api_call", "description": "<summary>",
  "parameters": {"type": "object", "properties": {
    "url": {"type": "string", "default": "<catalog url>"},
    "method": {"type": "string", "default": "POST"},
    "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
    "body": {"type": "object", "required": [<catalog required ∩ emitted fields>], "properties": {
       "<customer field>": {"type": "string", "default": "{{<customer_key>}}"},
       "<field>": {"type": "<type>", "default": "{{b_<node>_<field>}}", "enum": [...], "description": "..."}}}}}}}
```

`url` must equal `server + path` of the catalog (lint). Writes have `maxRetries` 0, except the close nodes (`close_call` is idempotent by contract): 2. Close nodes use `{{co}}`/`{{cr}}`.
Optional fields with no runtime source are omitted. A required field with no role -> literal catalog example/enum[0],
logged as a WARN decision.

### D.6 Compiler entry points (agent 3)

```python
graph.FLAGS_DEFAULT = {"bye": "pass", "write_chain": "on", "qnodes": "off", "uvars": "reset", "amount_tpl": "plain"}
graph.wiring(spec, catalog, flags=None) -> dict                 # == tests/fixtures/wiring-*.json for the golden specs
graph.compile_workflow(spec, catalog, flags=None) -> (workflow: dict, wiring: dict)   # byte-stable (sorted, deterministic)
render.system_prompt(spec) -> str ; render.open_line(spec) -> str ; render.extraction_schema(stage, spec) -> list
render.compile_line(template, spec) -> str                      # B.2 compile-time column; raises RenderError on runtime-only placeholders
snippet.build_ctl_code(spec, wiring) -> str                     # strips meta, calls runtime.bundle.make_snippet
lint.lint(workflow, catalog, spec, wiring) -> list[dict]        # [{"level": "error"|"warn", "rule": id, "where": node, "msg": str}]
deploy.deploy(workflow, slot, run_dir, dry_run=True) -> dict    # {"workflow_id","agent_id","version","export_path","diff":[...]}
```

Lint rules (minimum): no `null`; no `{{`/`}}` in code; snippet `compile()`s; imports ⊆ json/re/datetime; every
transition target exists; every passthrough node ends with `always` and `passthrough_default_transition` = that target;
no duplicate targets per node; every `{{var}}` used in tts/body has a writer (call var, ctl write, or mapping);
body fields/enums match the catalog; URL = server + path; non-idempotent writes maxRetries 0 (close_call 0..2); `tools` only on conversation nodes
(none in MVP) and `pre_actions` only on api/code nodes; every api node `suppress_tool_results: true`; every transition
into an api node carries the `pending` guard; `a_close_n` has no reason leaf; compile-time tts contains no banned
pre-verification word; byte-stable compile (compile twice, compare).

Deploy (L3): `freya.validate_workflow` dry run (fail on any `success: false`), `freya.save_workflow(slot, wf,
state_file=STATE/<slot>.json)` **twice on create** (E0: the second call patches agent_config + publishes), versions
check `isPublished`, read-back projected diff (node keys, node_type, passthrough, on_enter, transitions,
pre_action names/url/body defaults, response_mapping, extraction names/enums; extra keys ignored), then
`freya.export_workflow(id, run_dir/workflow.export.json)`. Import the kit via `builder.paths.import_kit("freya")`.

---

## E. Harness contracts (agent 4)

### E.1 Twin (`harness/twin.py`) — local executor matching E1

```python
class Twin:
    def __init__(self, workflow, bank, call_vars, mode="sim", bool_style="lower", list_style="json",
                 flat_keys="both", max_hops=30, extractor=None): ...
    def start(self) -> list        # sim: enter initial node, return its tts lines; chat: [] (customer speaks first)
    def turn(self, text, sensors=None) -> list   # assistant lines produced by this customer turn
    ended: bool; vars: dict; events: list; transcript: list[(role, text)]; hops: list[int]; errors: list[str]
```
Semantics: at a listen node, a customer turn = extraction (sensors dict restricted to the node's schema names;
default extractor sets `u_text` = text, other schema fields `''`), then routing (deterministic operators only;
`matches_intent` -> error), then node entry loop until a non-passthrough conversation node is entered (speaks its tts
and waits) or `end_call`. Chat mode first turn at the initial node: routing is suppressed ("Missing prior assistant
message"); the twin answers with the «…» text of `s_open.task_message`. Code nodes: `exec(code, {"vars": vars})`;
non-string writes are contract errors. API nodes: bake body defaults (exactly `"{{x}}"` with x unset -> field dropped;
mixed text keeps the literal), call `bank.call(tool, body)`, envelope `{"status", "data", "status_code"}`, apply node
`response_mapping` (`data.` paths; bool -> "true"/"True" per `bool_style`; list/dict -> JSON or Python repr per
`list_style`), write flattened `<tool>_response.data.*` and/or `<node>_response.data.*` per `flat_keys`, counters
`<node>_success_count` / `<node>_failure_count`; 500 -> no data, mapping leaves vars untouched. Transition operators per
kit docs (`equals` = str compare, `greater_than` float, `is_set` = key present). Unresolved `{{var}}` in tts -> spoken
literally + error. Hop limit per customer turn -> error.

### E.2 Mock bank (`harness/mockbank.py`)

```python
class MockBank:
    def __init__(self, catalog, case, faults=None, fault_mode="http500", reasonless=None): ...
    def call(self, tool, body) -> tuple    # (status_code, body_dict | None)
    def ledger(self) -> dict               # kit shape: {outcome, reason, promises[{product_id, amount, date}],
                                           #  notes[{product_id, reason}], callbacks[{date, time}], transfers[{queue}],
                                           #  calls[{tool, args, result}]}
```
`case` = public-test-set shape (`variables`, `identity` {field value: answer}, `products` (ids assigned `p1..pn` if
absent), `faults` [{tool, fail_first_n}]). Behaviour (field names via catalog roles, never hard-coded): HTTP 200 +
`ok:false` + `error` for business errors; unknown customer -> 404; verify: selector must be a known identity field;
date-like expected answers require an ISO date else `ok:false` unreadable (not counted); match -> verified; the
day/month-swapped date -> `hint` = first hint enum value, not counted; else wrong (counted), `left = 3 - wrong`;
3 wrong -> locked (`ok:false`, left 0); `all` when every identity field verified. account before all verified ->
`"identity not verified"`. promise: same gate, unknown product, non-ISO date, one per product
(`"this product already has a promise"`), faults -> 500 with nothing recorded. note/queue/outcome enums from the catalog.
close: reason required unless outcome in `reasonless` (default `catalog.reasonless_outcomes_hint`); a reason sent with a
reasonless outcome is recorded (so the kit scorer fails it); nothing accepted after close.

### E.3 Scenarios (`tests/scenarios/*.json`, runner in `harness/scenarios.py`)

```json
{"id": "A-001", "spec": "a", "pub": "PUB-01", "case": {}, "mode": "sim",
 "turns": [{"say": "Yes, speaking."}, {"say": "14 March 1988", "x": {"u_act": "answer"}}],
 "expect": {"outcome": "promise", "reason": null, "promises": [], "notes": [], "callbacks": [], "transfers": []},
 "transcript": {"must": [[-1, "substring"]], "must_not": [[-1, "word"]], "no_banned_before_verified": true,
                "one_line_per_turn": true, "max_hops": 8},
 "twin": {"bool_style": "title", "list_style": "pyrepr", "flat_keys": "node"}}
```
`pub` loads the case from `kit/public-test-set.json` (expected block too unless `expect` overrides).
`run(scenario, workflow, catalog) -> {"pass", "failed": [...], "transcript", "ledger", "hops"}`; ledger scored with
kit `score.score_ledger` (import via `builder.paths.import_kit("score")`), plus the transcript checks.
`generate(spec, catalog) -> list[scenario]`: generic smoke scenarios built from Spec values only (happy path,
id failure, callback, refusal) for the build's L2 twin run.

### E.4 Chat end-to-end (`harness/chat_e2e.py`, live, sequential)

```text
python -m harness.chat_e2e --workflow-id W --case PUB-01 [--customer persona|script] [--script f.json]
                           [--style pieces] [--max-turns 30] [--out results/chat/<case>.json]
```
1. `POST {FREYA_BANK_HOST}/v1/practice/sessions` `{"case": id}` with header `x-team-key` -> `variables`.
2. Turn 1 sends `"Hello?"` (chat does not speak the initial tts first; s_open's task_message makes the dialogue model say
   the opening). Then customer turns from `harness.persona` (Claude via claude_agent_sdk, prompt =
   `run_cases.persona_for(case, {"identity": case["identity"]}, style)["prompt"]` + the transcript) or a scripted list.
   `POST /api/v2/chat/message {workflowId, message, customerVariables: variables, callId}` via `freya.api`; 45 s per
   turn timeout; >= 1 s between turns.
3. Stop when the ledger's last call is `close_call` (checked only after an assistant line containing a goodbye word, or
   an empty response), or at max turns. Then `POST /api/v2/chat/end {callId}`.
4. `GET /api/v2/call/{callId}?workspaceId=` -> save messages (node path from `node_enter` events).
5. `GET /v1/practice/ledger/{customer_id}` -> kit `score_ledger(case, ledger)` + transcript lints -> JSON report.
Never runs simulations; never runs two cases in parallel.

---

## F. Ownership

| Agent | Owns (create/edit) | Tests it owns |
|---|---|---|
| 1 runtime cal + parse | `runtime/cal.py`, `runtime/parse.py` | `tests/test_cal.py`, `tests/test_parse.py` |
| 2 runtime ident + brain + bundler | `runtime/ident.py`, `runtime/brain.py`, `runtime/bundle.py`, `runtime/__init__.py` | `tests/test_ident.py`, `tests/test_brain.py`, `tests/test_bundle.py` |
| 3 compiler + catalog + lint + deploy | `builder/openapi_model.py`, `builder/compiler/*.py`, `builder/deploy.py` | `tests/test_openapi_model.py`, `tests/test_compiler.py`, `tests/test_lint.py`, `tests/test_deploy.py` (offline, mocked `freya.api`) |
| 4 harness | `harness/*.py`, `tests/scenarios/*.json` | `tests/test_mockbank.py`, `tests/test_twin.py`, `tests/test_scenarios.py` |
| 5 pipeline + llm + trace + budget + build | `builder/build.py`, `builder/llm.py`, `builder/trace.py`, `builder/budget.py`, `builder/pipeline/*.py`, `builder/prompts/*`, `apply_defaults` in `builder/spec/defaults.py` | `tests/test_trace.py`, `tests/test_budget.py`, `tests/test_segment.py`, `tests/test_validate.py`, `tests/test_llm_shape.py`, `tests/test_build_cli.py` |
| lead (read-only for agents) | `docs/CONTRACTS.md`, `builder/spec/schema.json`, `builder/spec/vocab.py`, DEFAULT_* data in `defaults.py`, `builder/paths.py`, `tests/golden/*`, `tests/fixtures/*`, `tests/conftest.py`, `tests/test_contracts.py`, `pytest.ini`, `requirements.txt` | – |

Integration order (no agent waits): agent 2 develops `brain` against `tests/fixtures/wiring-*.json` + golden specs and
agent 1's signatures (stub locally until agent 1 lands); agent 4 develops the twin against small hand-made workflows
and `catalog-kit.json`, and the end-to-end golden scenario test (`compile golden -> twin`) may `pytest.skip` while
`compiler`/`brain` still raise `NotImplementedError`; agent 5 develops build.py with `--no-deploy` and fakes for
compiler/deploy. Cross-module calls only through the signatures above.

### Build CLI and supporting modules (agent 5)

```text
python3 builder/build.py <brief.md> [<brief.md> ...] <tool_api file> [--slot S] [--out-dir runs] [--no-deploy]
        [--no-twin] [--no-critic] [--flags k=v,...] [--spec-in path (skip extraction; dev)] [--dev]
exit: 0 ok | 2 input | 3 spec invalid | 4 lint | 5 deploy | 6 budget (last published exported)
```
Order: START -> catalog -> segment -> extract (6 facet calls, parallel <= 6) -> validate(+defaults) -> [one re-extract
of facets with errors] -> critic (1 call, patches re-validated, reverted if invalid) -> compile -> lint -> twin L2
(`harness.scenarios.generate`) -> deploy (L3) -> export -> END summary. The tool API file is detected by content
(`openapi` key), any extension. Default slot `<first brief stem>-<sha8(all input bytes)>-<UTC YYYYmmddTHHMMSS>` (a fresh workflow per run).

```python
trace.init(run_dir) ; trace.event(kind, msg="", **fields) ; trace.summary(**fields) ; trace.close()
#   kinds: START INPUT CATALOG SEGMENT MODEL EXTRACT VALIDATE DEFAULT CRITIC SPEC COMPILE LINT TWIN DEPLOY FREYA
#          EXPORT BUDGET DECISION WARN ERROR END; each line "[+12.3s] KIND module.function | msg | k=v";
#   fields "where": "LOCAL" | "ON-AGENT" for tests; secrets scrubbed (env values of FREYA_API_KEY,
#   FREYA_BANK_TEAM_KEY, ANTHROPIC_API_KEY; patterns fak_..., sk-ant-...) on every write; works before init (stdout only)
budget.Budget(hard_s=1560, soft_s=1200, reserve_s=180) ; .elapsed() ; .remaining() ; .call_timeout(cap_s) ; .go(stage) -> bool
llm.call_json(purpose, system, prompt, schema, *, timeout_s, effort="high", model=None) -> dict
llm.run_parallel(calls: list[dict], max_concurrency=6) -> list[dict | Exception]
#   claude_agent_sdk.query with ClaudeAgentOptions(system_prompt, output_format={"type": "json_schema", "schema": ...},
#   tools=[] / no tool use, max_turns small, effort); result from ResultMessage.structured_output, fallback: parse JSON
#   from the text; jsonschema-validated; <= 2 retries if the budget allows; MODEL trace event per call (purpose,
#   seconds, model, ok, usage). Never disable thinking.
segment.segment(paths) -> {"docs": [{"path", "sha256", "text", "lines", "sections": [{"title","level","line_start","line_end"}],
                           "tables": [{"line", "header", "rows"}]}], "numbered": "<path>:<n>| line\n..."}
extract.FACETS = {"F1": [...top-level keys...], ..., "F6": [...]}  ; extract.extract(bdoc, catalog, budget) -> dict
validate.validate(spec, catalog) -> {"spec", "errors", "warnings", "defaults_applied"}
critic.critique(bdoc, spec, catalog, budget) -> {"issues": [{"quote","problem","pointer","op"}], "residual": [...]}
critic.spec_to_english(spec) -> str
```
Facets: F1 bank, call_variables, addressing, opening, banned, right_party, third_party; F2 identity;
F3 products (types only; fields bound by code), statement, calendar, bands; F4 promise_date, amounts, negotiation;
F5 intents, situations, outcomes, notes, multi_product; F6 confirmation, recording, required_sentences, closing, lines.
Each facet call receives the generic system prompt, the numbered brief, the ToolCatalog enums, and the JSON sub-schema
(`schema.json` properties of its keys + all `$defs`). Prompts contain only synthetic examples (a made-up bank).

---

## G. Platform assumptions the MVP relies on (verify with website simulations / chat_e2e)

| # | Assumption | Status | Fallback flag |
|---|---|---|---|
| G1 | Listen node tts `{{say}}` + `always -> ctl` gives exactly one assistant line per customer turn | VERIFIED (E1, chat) | `speak=llm_echo` (M3) |
| G2 | Chat route does not speak the initial tts; turn 1 routing is suppressed and the dialogue model speaks `s_open`'s task_message | VERIFIED (E1) | – |
| G3 | A passthrough conversation node (`s_bye`) speaks its tts and then routes without a customer turn | UNVERIFIED | `bye=apinode`, `bye=listen` |
| G4 | Node-level `response_mapping` `data.<leaf>` sets `r_*` on api_request pre_actions | VERIFIED (kit working builder) | flattened-key fallback in `read_result` |
| G5 | Mapped list (products) arrives as list / JSON string / repr / flattened keys | UNCERTAIN | `read_products` reads all forms |
| G6 | AND groups nested in the top-level OR (entry guards, chain links) evaluate deterministically | DOCUMENTED | `write_chain=off` |
| G7 | Body defaults `{{b_*}}` are baked at node entry each time the node is entered | DOCUMENTED (unrolled nodes avoid relying on re-entry) | – |
| G8 | A number field baked from a string var is accepted by the bank (`"420.00"`) | PROBED earlier (bank accepts strings) | `amount_tpl=json` |
| G9 | Code node writes via a function receiving `vars` (same dict object) persist | ASSUMED (E1 wrote at top level) | inline writes at top level of the snippet |
| G10 | `ctl` runtime is 0.3-2.7 s per entry (E1); a happy-path confirm turn with the write chain enters ctl once | MEASURED (E1) | – |

---

## ADDENDUM (owner requirement, 2026-10-11 00:45 UTC): BUILD SPEED IS A TIE-BREAK

Official tie-breaks, in order: (1) total promised amount on passed cases, (2) **shorter total build time**, read from the builder's trace (start to end of each hidden-brief run), (3) earlier submission. Teams with equal scores are ranked by these, so the builder must be fast as well as correct. Binding requirements:

1. **Critical path budget.** Target ≤ 4 min wall clock for a clean brief and ≤ 7 min for a raw-material brief, including deploy and export. Measure it and print the stage timings in the trace.
2. **One parallel LLM wave.** Run every extraction call concurrently in a single wave, with the brief placed first so the prompt cache is reused. Run the critic and repair calls only when validation reports errors; never by default. No sequential chains of LLM calls when one call could do the job.
3. **No live self-tests on the default path.** The deterministic local checks (lint, invariants, twin on generated scenarios) take seconds and always run. The only default live check is one chat turn to prove the agent starts (≤ 10 s). Longer live tests sit behind an opt-in flag and are off for the Sunday run.
4. **Model and effort chosen by measurement.** Time each extraction call. Pick the fastest model/effort that keeps the golden-spec diff clean (compare Opus 5.5 with Sonnet 5.5, and lower effort on the simple facets). Make it configurable, and record the choice in the trace.
5. **Deploy fast.** Use one dry run, then create, second save, publish, and read-back. Make no redundant GETs or sleeps. Export right after publish.
6. **Runtime speed matters too.** The ctl snippet must be fast (no heavy loops per turn), and every listen node does exactly one extraction call. Slow agent turns make simulated customers hang up.
7. **Promised-amount tie-break.** Always ask for the full past-due amount first. Offer the floor only when the brief allows it. Never drop to a lower amount early.

---

## ADDENDUM (rehearsal round, 2026-10-11 ~10:30 UTC): Spec additions and their runtime semantics

All optional; a Spec without them behaves exactly as before.

| Leaf | Meaning | Where |
|---|---|---|
| `dated: [{from, until?, path, value, source?}]` | A rule that changes on an effective date. On a call whose date (from `now`) satisfies `from <= today < until` the runtime sets the JSON pointer `path` of a copy of the Spec to `value` before anything else is evaluated (`brain.dated_spec`, called in `_b_ctx`; later `from` wins). The base values hold the rule before the change. `path` must start with one of `validate.DATED_PREFIXES` (runtime-evaluated sections plus `/products/max` and `/notes/`; `graph.wiring` builds nodes for every dated variant). validate rejects a path outside them, a path that does not resolve, `until <= from`, and a Spec that is invalid once patched. | schema top level; each facet returns `dated` next to `values` (`extract.merge_dated`) |
| `interpretation.after_record` | `close` (default): the recording turn ends the call. `ask_anything_else`: the write plan holds only the promises; ctl then says the recorded line(s), the `after_promise_recorded` sentences and `lines.anything_else`, and listens (offer kind `post`). A transfer / hardship / refuse-to-talk intent is handled as usual (a transfer then closes as the transfer, the recorded promise stays); a question is answered and the question repeated (2 at most); anything else closes (notes + goodbye; the recorded line is not repeated, `p.ann`). validate derives `ask_anything_else` when absent and `transfer_done` ranks above `any_promise_recorded`. | brain `_b_write`, `_b_post`, `_b_post_turn` |
| `third_party.mode`, `third_party.close_line` | `close`: never ask, never book. Any third-party entry says `close_line` and closes with `situations.no_callback` in that turn; no `a_cb` nodes are compiled. validate coerces a zero-length callback window, or a reach ask that says goodbye, to `close`. | brain `_b_tp_turn`, graph `_uses_callback` |
| `closing.no_goodbye: [S_X]` | For these close situations no `closing.goodbye` is added (the brief's own line, and its per-situation line, end the call). | brain `_b_bye_say` |
| `IdQuestion.two_digit_year` | `ask_full` (default): a year answer without full-year evidence (4 digits, nineteen/twenty/hundred/thousand, or 4 single digits) is `invalid` (ask_full, not sent, not counted). `pivot`: the old century guess. | ident `_i_answer_year` |
| `lines.anything_else` | The post-record question (default "Is there anything else I can help you with?"). | defaults |

Runtime behaviour changes without a new leaf: an alnum answer is re-split to fit its pattern (`ident._i_fit`: one space or hyphen); a keyword-only `offer_transfer`/`close_now` hit that is negated, an idiom, or (close_now) a relative's death does not fire; an extracted hardship topic needs a cause word (`_B_CAUSE`) when the keywords miss; keyword-only transfer/answer intents do not interrupt a proposal; `<product>` in an intent line names the product under discussion (else the open ones); a below-floor line with `<date>` is the floor offer itself, one with an undated question loses that question; a `close_now` situation with a note reason is every open product's note reason; a declined hardship offer plus a named value gets the corrective offer (a no to it is the decline); a goodbye already in a line moves to the very end.

Packing: the DEFLATE stream is encoded in an 85-letter alphabet (`bundle._QALPHA`: printable ASCII without braces, quotes, backslash, `<`, `>`, `&`, backtick) instead of base64, and the loader is indented one space per level: about 4.8 KB less packed code for the same snippet.
