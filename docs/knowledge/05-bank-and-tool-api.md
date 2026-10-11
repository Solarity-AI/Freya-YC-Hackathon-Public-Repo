# Chapter 5: The mock bank and its seven tools

## In short

- **What it is.** A Freya-hosted mock at `https://freya-bank-mock.freyavoice.workers.dev/v1` (`openapi.json:10`), the only service the agent may call (`README.md:86`). Every call goes into a ledger, and the scorer reads the ledger, not the transcript (`openapi.json:6`; `README.md:59`).
- **Seven tools.** Each is a `POST` with a JSON body and no key. `customer_id` in the body is "the secret of one call" (`openapi.json:6`). The names are fixed for the final; fields and enums can change, and each hidden brief ships its own OpenAPI file (`README.md:72`).
- **Answers.** HTTP 200 carries `ok`, and a refusal is `ok:false` plus `error`. HTTP 500 means "Nothing was recorded. The call may be repeated." (`openapi.json:51, 84`). An unknown `customer_id` gets an undocumented 404 [PROBED-earlier].
- **Enforcement.** The bank checks data and state: enums, formats, the identity gate on `get_account`, one promise per product, nothing after `close_call`, and the outcome/reason pairing. It does not check brief policy such as holidays, the deadline or the floor (`openapi.json:6`; `hackathon-page.md §Evaluation`).
- **Practice.** `POST /v1/practice/sessions` makes a single-use PUB customer, and `GET /v1/practice/ledger/{id}` (with the team key) shows every record and every call. It serves PUB-01..13 only; hidden briefs have none (`hackathon-page.md §FAQ`).
- **Kit scorer** (`score.py:17–34`). These must match exactly: outcome+reason, promises (product, amount to 2 dp, date), notes (product, reason), callbacks (date, time) and transfers (queue). The last call must be `close_call`, no "identity not verified" may appear, and a not-reached customer gets no identity or account calls.
- **Biggest unknowns.** How a 500 or an injected fault looks inside Freya, the bank's answer at the wrong-answer limit, and what the hidden files change.

---

## 0. Sources, labels and citations

**Primary sources (the truth)**

| Short name in citations | File |
|---|---|
| `openapi.json:NN` | `kit/tools/openapi.json` (kit v3, `info.version` `0.3-draft`) |
| `score.py:NN`, `run_cases.py:NN` | `kit/build-the-builder/tools/score.py`, `kit/build-the-builder/tools/run_cases.py` |
| `README.md:NN`, `brief-a.md:NN`, `brief-b.md:NN`, `public-test-set.json:NN`, `base-agent.json:NN`, `SKILL.md:NN`, `env.example:NN` | Files in `kit/build-the-builder/` (`briefs/`, `examples/`, `.claude/skills/build-phone-agent/`) |
| `tools-and-code.md:NN`, `api.md:NN` | `kit/build-the-builder/docs/` |
| `hackathon-page.md §Section` | `research/hackathon-page.md`, the official page text |
| `read-api-and-testing.md:NN` | `research/read-api-and-testing.md`. Used only for the probe facts it reports. Its other claims were re-checked. |

**Notes this chapter re-checks:** `knowledge/notes/openapi.md`. Where a note and a source disagree, the source wins, and §12 says so.

**Labels**

| Label | Meaning |
|---|---|
| [DOC] | Stated in a document: the OpenAPI file, the README, a brief, the docs or the hackathon page. |
| [CODE] | Read from kit code. |
| [PROBED-earlier] | Seen in the live probes of 2026-10-10 reported in `read-api-and-testing.md`. These probes are not repeated. Further probing is forbidden (`hackathon-page.md §Rules`: "Do not probe or load-test the platform."). |
| [INFERRED] | My own reasoning. |
| [UNCERTAIN] | Not known. The text says exactly what is missing. |

No network call was made to write this chapter.

---

## 1. What the bank is and where it sits

### 1.1 Its role

| Fact | Source | Label |
|---|---|---|
| "Mock of the bank's systems for the Build the Builder hackathon. We host it." | `openapi.json:6` | [DOC] |
| "Every call is written to the ledger the scorer reads." | `openapi.json:6` | [DOC] |
| "The service does not enforce the brief: it records a promise on a holiday or past the deadline without complaint. Following the brief is the agent's job." | `openapi.json:6` | [DOC] |
| The page adds "below the minimum" to the list of things the bank accepts. | `hackathon-page.md §Evaluation` | [DOC] |
| "The bank's tool API that the phone agent calls during a call." | `README.md:44` | [DOC] |
| The mock bank API "stands in for the bank". The agent calls it to check identity, read the debt and record a promise. Freya hosts it "so they can see what was really recorded". "The scorer reads that record, not what the agent says. Your team key owns your practice sessions and records." | `hackathon-page.md §Data` | [DOC] |
| Outcome check: "The scorer reads them from the bank, not from what the agent said." | `README.md:59` | [DOC] |
| "The phone agent may call only the bank's tool API." | `README.md:86` | [DOC] |
| "Agent may call only the kit's tool API; a call to any other service fails the case." | `hackathon-page.md §Rules` | [DOC] |
| Tie-break: "Equal scores are ranked by the total promised amount on the customers that passed". So the amounts recorded with `create_promise` matter beyond pass or fail. | `README.md:90`; `hackathon-page.md §Evaluation` | [DOC] |

### 1.2 Hosts and routes

| Route | Method | Key | Purpose | Source | Label |
|---|---|---|---|---|---|
| `{servers[0].url}/verify_identity`, `/get_account`, `/create_promise`, `/add_note`, `/schedule_callback`, `/transfer_to_agent`, `/close_call` | POST | none | The seven tools | `openapi.json:10, 14–471` | [DOC] |
| `/v1/practice/sessions` (on the bank host) | POST, body `{"case": "<PUB id>"}` | `X-Team-Key` | Creates a practice customer | `run_cases.py:86`; `score.py:10–15` [CODE]; `read-api-and-testing.md:126` [PROBED-earlier] | [CODE], [PROBED-earlier] |
| `/v1/practice/ledger/{customer_id}` | GET | `X-Team-Key` | Reads what was recorded | `score.py:38`; `run_cases.py:93` [CODE]; `read-api-and-testing.md:133` [PROBED-earlier] | [CODE], [PROBED-earlier] |
| `/` | GET | n/a | Returns 404 JSON | `read-api-and-testing.md:120` | [PROBED-earlier] |

**How the host is chosen**
- The tool server URL comes from the OpenAPI file, and it is the only server listed (`openapi.json:8–12`). [DOC]
- The scripts read the host from the environment: `HOST = os.environ.get("FREYA_BANK_HOST", "https://freya-bank-mock.freyavoice.workers.dev")` (`score.py:7`). [CODE]
  - This affects only the practice and ledger calls that `score.py` and `run_cases.py` make.
  - It does not change the URLs inside the agent, which are baked into each tool, for example `base-agent.json:20, 171, 215, 348`. [CODE]
- `FREYA_BANK_HOST` does not appear in `env.example` (`env.example:1–3`). [DOC]

**The URL is fixed at build time** [INFERRED]
- The exported workflow is what the organisers load and score (`README.md:75`).
- The bank URL baked into each tool must therefore be `servers[0].url` from the brief's own tool API file.

### 1.3 Keys, and what identifies one call

| Fact | Source | Label |
|---|---|---|
| "The seven tool calls need no key: the customer_id in the body is the secret of one call." | `openapi.json:6` | [DOC] |
| `customer_id` is a call variable such as `c_4f2a...`: "Pass it to every tool call." | `brief-a.md:17` | [DOC] |
| The bank ties a call to a customer only through `customer_id` in the body. | `read-api-and-testing.md:94` | [PROBED-earlier] |
| The team key is "a team key you make up for the practice bank". In `env.example` it is `FREYA_BANK_TEAM_KEY=pick-any-secret-of-16-or-more-characters`, with the comment "you make this up. Use the same one every time." | `hackathon-page.md §Data`; `env.example:3` | [DOC] |
| The scripts send the key as header `x-team-key`, with `user-agent: freya-bank-scorer/0.1` and `content-type: application/json`. The timeout is 20 s. | `score.py:8, 12, 14` | [CODE] |
| Every `/v1/practice/*` route checks `X-Team-Key` (16 or more characters) before routing. | `read-api-and-testing.md:120` | [PROBED-earlier] |
| A ledger is visible only under the key that created it. | `read-api-and-testing.md:305` | [PROBED-earlier] |
| The chat route never uses the team key. Setting `customerVariables.customer_id` to a real practice-session id puts the chat's tool calls into that session's ledger. | `read-api-and-testing.md:94–95` | [PROBED-earlier] for the bank side. Whether the chat route behaves this way is [INFERRED] by that summary; no chat call was made. |

---

## 2. The OpenAPI file

### 2.1 Document-level facts

| Item | Value (verbatim) | Line | Label |
|---|---|---|---|
| `openapi` | `"3.0.3"` | 2 | [DOC] |
| `info.title` | `"Freya Bank collections tools"` | 4 | [DOC] |
| `info.version` | `"0.3-draft"`. The kit itself is version 3 (`VERSION` holds `3`; `README.md:3`). | 5 | [DOC] |
| `info.description` | "Mock of the bank's systems for the Build the Builder hackathon. We host it. Every call is written to the ledger the scorer reads. The service does not enforce the brief: it records a promise on a holiday or past the deadline without complaint. Following the brief is the agent's job. The seven tool calls need no key: the customer_id in the body is the secret of one call." | 6 | [DOC] |
| `servers` | Exactly one entry: `{"url": "https://freya-bank-mock.freyavoice.workers.dev/v1"}` | 8–12 | [DOC] |
| `components` | `{}`: no shared schemas, no `securitySchemes` and no `$ref` anywhere | 13 | [DOC] |
| `paths` | 7 paths, each with only a `post` operation | 14–471 | [DOC] |
| File length | `wc -l` gives 471 because the last `}` (line 472) has no trailing newline. Line 6 is the longest line, at 391 characters. | n/a | [CODE] (measured locally) |

### 2.2 What the file does not contain

I checked this by walking every key in the JSON locally. [CODE]

The only keys used are: `openapi`, `info`, `title`, `version`, `description`, `servers`, `url`, `components`, `paths`, `post`, `summary`, `requestBody`, `required`, `content`, `application/json`, `schema`, `type`, `properties`, `enum`, `format`, `items`, `responses`, `200`, `500`, the seven paths, and the field names.

**Absent from the file:**
- `operationId`, `tags`, `security`, `parameters` (query, path or header), `example`/`examples`, `nullable`, `additionalProperties`
- `default`
- Every constraint keyword: `minimum`, `maximum`, `pattern`, `minLength`, `maxLength`, `minItems`, `maxItems`, `multipleOf`
- Any 4xx response
- Any `required` array on a response schema
- A body schema for any 500

**What follows for a parser** [INFERRED]
- The tool name is the path without its leading `/`, because there is no `operationId`.
- The URL to call is `servers[0].url + path`, for example `https://freya-bank-mock.freyavoice.workers.dev/v1/verify_identity`. That is exactly what `base-agent.json:20` hard-codes.
- The file uses `format` only twice, both times as `"date"`: on `create_promise.date` (`openapi.json:193`) and `schedule_callback.date` (`openapi.json:313`). In OpenAPI 3.0, `format: date` means an RFC 3339 full-date, `YYYY-MM-DD` [INFERRED from the OpenAPI specification]. The probed error string `date must be YYYY-MM-DD` agrees [PROBED-earlier].
- **Request fields with a description.** Only three have one: `verify_identity.answer` (L37), `schedule_callback.time` (L317) and `close_call.reason` (L435). [DOC]
- **Response fields with a description.** Only three have one: `card_last4`, `minimum_payment` and `instalment_amount` (L142, 152, 156). [DOC]
- **`summary` strings.** Every operation has one. Several of them carry policy (see §2.5). [DOC]

### 2.3 Conventions shared by all seven tools

| Convention | Detail | Lines in `openapi.json` | Label |
|---|---|---|---|
| Method | `POST` only | 16, 90, 173, 235, 299, 355, 410 | [DOC] |
| Request body | `requestBody.required: true`, `application/json`, `type: object` | 18–23, 92–97, 175–180, 237–242, 301–306, 357–362, 412–417 | [DOC] |
| `customer_id` | On all seven tools, always listed in `required`, `type: string`, no description | Property / required line: 25–27/41, 99–101/104, 182–184/197, 244–246/265, 308–310/321, 364–366/377, 419–421/439 | [DOC] |
| Authentication | None. "The seven tool calls need no key" | 6, 13 | [DOC] |
| 200 description | "`ok` is false when the action was not carried out." The text is identical on all seven. | 51, 112, 208, 275, 331, 386, 448 | [DOC] |
| 200 schema | An object with `ok` (boolean) and `error` (string), plus tool-specific fields. It has **no `required` list**. | `ok`/`error` at 57–62, 118–123, 214–219, 281–286, 337–342, 392–397, 454–459 | [DOC] |
| 500 | Description only, no `content`: "The service failed. Nothing was recorded. The call may be repeated." The text is identical on all seven. | 83–85, 166–168, 228–230, 292–294, 348–350, 403–405, 465–467 | [DOC] |
| Ledger | "Every call is written to the ledger the scorer reads." | 6 | [DOC] |

### 2.4 The seven tools on one page

| Tool | `summary` (verbatim) | Request fields (`*` = required) | 200 fields besides `ok`, `error` | Lines |
|---|---|---|---|---|
| `verify_identity` | "Check one security answer. Three wrong answers in total end the check." | `customer_id*`, `field*` enum `date_of_birth`/`phone_last4`, `answer*` | `verified` bool, `wrong_answers_left` int, `all_verified` bool, `hint` enum `day_month_swapped` | 15–88 |
| `get_account` | "The late products. Refused until both questions are passed." | `customer_id*` | `products[]` of {`product_id`, `type` enum, `card_last4`, `past_due`, `days_late`, `minimum_payment`, `instalment_amount`} | 89–171 |
| `create_promise` | "Record a payment promise. One per product." | `customer_id*`, `product_id*`, `amount*` number, `date*` string `format: date` | `promise_id` string | 172–233 |
| `add_note` | "Brief B: record why a product ended without a promise." | `customer_id*`, `product_id*`, `reason*` enum (5 values), `text` (optional) | none | 234–297 |
| `schedule_callback` | "Book a callback." | `customer_id*`, `date*` `format: date`, `time*` ("HH:MM") | none | 298–353 |
| `transfer_to_agent` | "Hand the call to a person." | `customer_id*`, `queue*` enum `restructuring`/`general`/`support` | none | 354–408 |
| `close_call` | "End the call. Always the last tool call. Nothing is accepted after it." | `customer_id*`, `outcome*` enum (6 values), `reason` (free string, **not** in `required`) | none | 409–470 |

All of these are [DOC].

### 2.5 Every policy-bearing string in the file

A hidden file may reword any of these. A builder should therefore pass them on to the agent and to its own rule extractor rather than ignore them [INFERRED].

1. "The service does not enforce the brief: it records a promise on a holiday or past the deadline without complaint. Following the brief is the agent's job." (L6)
2. "Every call is written to the ledger the scorer reads." (L6)
3. "The seven tool calls need no key: the customer_id in the body is the secret of one call." (L6)
4. "Check one security answer. Three wrong answers in total end the check." (L17)
5. "For date_of_birth: the date as YYYY-MM-DD. Callers say dates in words, the agent converts. An unreadable value is rejected with ok=false and is not counted as a wrong answer. For phone_last4: four digits." (L37)
6. The `hint` enum `day_month_swapped` (L72–77)
7. "The late products. Refused until both questions are passed." (L91)
8. "credit cards only" and "loans only". These say which product types carry which fields, so they decide the floor field and the spoken product name. (L142, 152, 156)
9. "Record a payment promise. One per product." (L174)
10. "Brief B: record why a product ended without a promise." (L236)
11. `"HH:MM"` (L317)
12. "Hand the call to a person." (L356)
13. "End the call. Always the last tool call. Nothing is accepted after it." (L411)
14. "Required for every outcome except promise and paid. See the table in the brief." (L435)
15. "`ok` is false when the action was not carried out." (L51, and the six repeats listed in §2.3)
16. "The service failed. Nothing was recorded. The call may be repeated." (L84, and the six repeats)

---

## 3. Tool reference

Each tool below follows the same order: request, response, the policy the tool encodes, what the earlier probes saw, how the kit scores it, and its traps.

### 3.1 `verify_identity` (`openapi.json:15–88`)

**Summary (L17):** "Check one security answer. Three wrong answers in total end the check." [DOC]

**Request**

| Field | Type | Enum / format | Required | Description (verbatim) | Lines |
|---|---|---|---|---|---|
| `customer_id` | string | n/a | yes | (none) | 25–27, 41 |
| `field` | string | `["date_of_birth", "phone_last4"]` | yes | (none) | 28–34, 42 |
| `answer` | string | no `format`, no pattern | yes | "For date_of_birth: the date as YYYY-MM-DD. Callers say dates in words, the agent converts. An unreadable value is rejected with ok=false and is not counted as a wrong answer. For phone_last4: four digits." | 35–38, 43 |

**Response 200** (no `required`; L57–77)

| Field | Type | Enum | What it means |
|---|---|---|---|
| `ok` | boolean | n/a | False when "the action was not carried out" (L51). [DOC] |
| `error` | string | n/a | Not described. Presumably the reason when `ok` is false [INFERRED]. It was absent from a probed success [PROBED-earlier]. |
| `verified` | boolean | n/a | Not described. Presumably whether *this* answer was right [INFERRED]. |
| `wrong_answers_left` | integer | n/a | Not described. Presumably how many wrong answers remain before the check ends [INFERRED]. The starting value was not recorded [UNCERTAIN]. |
| `all_verified` | boolean | n/a | Not described. Presumably true once every required question has passed, which is the gate for `get_account` (L91) [INFERRED]. |
| `hint` | string | `["day_month_swapped"]` | Not described in the file. `brief-a.md:42` explains it. |

**Response 500** (L83–85): "The service failed. Nothing was recorded. The call may be repeated." [DOC]

**Policy this tool encodes**
- **One answer per call:** "Check one security answer" (L17). [DOC]
- **A limit of three wrong answers in total, across fields:** "Three wrong answers in total end the check" (L17). This matches `brief-a.md:41`: "Three wrong answers in total end the check, whichever question they were on." [DOC]
- **The order of questions comes from the brief, not the file.** `brief-a.md:40`: "first the date of birth, then the last four digits of the phone number on file". [DOC]
- **The agent converts dates.**
  - "Callers say dates in words, the agent converts." (L37)
  - `brief-a.md:40`: "Send a date of birth as `YYYY-MM-DD`, whatever way the customer said it. The service rejects anything it cannot read as a date. Read a date given only as numbers as day, then month, then year." [DOC]
- **Day-month swap.** `brief-a.md:42`: "If the customer gives day and month the other way round, `verify_identity` returns `hint: "day_month_swapped"`. Ask them to say the month as a word. That retry does not count as a wrong answer." [DOC]
  - A swap can only be detected when both readings are valid dates, that is, when the day is 12 or less [INFERRED].
  - Public DOBs where a swap is possible: PUB-02 `1979-11-02` (`public-test-set.json:62`), PUB-07 `1975-12-05` (`:277`), PUB-09 `1981-08-11` (`:361`), PUB-11 `1987-06-03` (`:455`), PUB-13 `1991-01-08` (`:591`).
  - PUB-05 `1990-09-09` (`:191`) reads the same both ways. [DOC]
- **After three wrong answers.** `brief-a.md:43` says: do not state the debt, send the customer to the app or a branch, and close as `not_verified` / `failed`. [DOC]
- **Re-asking.** A wrong answer may be asked again (`brief-a.md:41`). PUB-12 checks that "the phone question is asked again once, the date of birth is not" (`public-test-set.json:572`). [DOC]

**What the earlier probes saw** (`read-api-and-testing.md:149–153`) [PROBED-earlier]
- A correct answer returns `{ok, verified, wrong_answers_left, all_verified}`, with no `error` key.
- `"14 March 1988"` (PUB-01's DOB) and `"3 June 1987"` (PUB-11's DOB) were **accepted as verified**, even though the file asks for YYYY-MM-DD.
- `"garbage"` as a date of birth returned `ok:false` and was **not counted**.
- `"two two eight eight"` for `phone_last4` (PUB-11's phone is `2288`) was **counted as wrong**. It used up one of the three attempts.
- An unknown `field` returns `"field must be date_of_birth or phone_last4"`.
- One re-verify of a field that was already verified came back with **no `all_verified` key at all**.

**How it is scored** [CODE]
- There is no direct check.
- `score.py:33`: if the expected outcome is `not_reached` (or `no_contact` / `unreached`), any `verify_identity` call fails the case.
- The ledger keeps `verified{field: bool}`, `wrong` and `hinted` [PROBED-earlier], but `score.py` does not read them.

**Traps**
- `answer` is a **string**. Leading zeros matter: PUB-02's phone is `"0358"` (`public-test-set.json:63`). Never send it as the number 358 [INFERRED].
- Only an unreadable **date** is documented as "not counted". A malformed phone answer can use up an attempt [PROBED-earlier]. Normalise it to exactly four digits before calling [INFERRED].
- The bank accepting non-ISO dates fits the docs, since only *unreadable* values are rejected. Still, always send ISO, because a hidden bank may be stricter [INFERRED].
- Routes must tolerate a missing `all_verified` key [PROBED-earlier → INFERRED].
- The kit docs' envelope example shows `attempts_left` (`tools-and-code.md:255`). That example comes from a different, made-up `check_answer` API. **The bank's field is `wrong_answers_left`** (`openapi.json:66`). [DOC]
- In two practice cases the card's last four digits equal the phone's last four: PUB-11 `2288` (`public-test-set.json:456, 461`) and PUB-13 `6604` (`:592, 597`). Do not treat this as a rule [INFERRED].

### 3.2 `get_account` (`openapi.json:89–171`)

**Summary (L91):** "The late products. Refused until both questions are passed." [DOC]

**Request**

| Field | Type | Required | Lines |
|---|---|---|---|
| `customer_id` | string | yes | 99–101, 103–105 |

**Response 200** (no `required` at any level; no `minItems` or `maxItems`)

| Field | Type | Enum | Description (verbatim) | Lines |
|---|---|---|---|---|
| `ok` | boolean | n/a | (none) | 118–120 |
| `error` | string | n/a | (none) | 121–123 |
| `products` | array of objects | n/a | (none) | 124–160 |
| `products[].product_id` | string | n/a | (none). No pattern or example. | 129–131 |
| `products[].type` | string | `["credit_card", "personal_loan", "car_loan"]` | (none) | 132–139 |
| `products[].card_last4` | string | n/a | "credit cards only" | 140–143 |
| `products[].past_due` | number | n/a | (none) | 144–146 |
| `products[].days_late` | integer | n/a | (none) | 147–149 |
| `products[].minimum_payment` | number | n/a | "credit cards only" | 150–153 |
| `products[].instalment_amount` | number | n/a | "loans only" | 154–157 |

**Response 500** (L166–168): the same text as the other tools. [DOC]

**Not in the response:** currency, customer name, due date, product name text, and any `required` list for the items. [DOC]

**Policy this tool encodes**
- **Identity gate.** "Refused until both questions are passed." The word "both" assumes two questions. [DOC]
- **Brief A order.** `brief-a.md:48`: "After both questions pass, call `get_account`." [DOC]
- **Only late products.** "The late products." (L91)
  - `brief-b.md:9`: "`get_account` returns one to three products. Each has its own `past_due`, `days_late` and floor."
  - `README.md:77`: "Final customers can have up to three products". [DOC]
- **Which field is the floor.** `brief-a.md:71`: "`minimum_payment` for a credit card and `instalment_amount` for a personal loan or a car loan". This matches "credit cards only" and "loans only". [DOC]
- **How products are named aloud.** `brief-a.md:49`: "credit card ending 4821", "personal loan" or "car loan". The agent also states the past-due amount and the days late. [DOC]
- **Product ids.** `README.md:102`: "The bank answers `unknown product_id`: the model made an id up. Product ids come from `get_account` (`p1`, `p2`, ...). Give them to the model in the tool result, or fill them in with code." [DOC]
- **Order matters in Brief B.**
  - Products are handled "in the order `get_account` returned them" (`brief-b.md:12`).
  - The closing reason is "the reason of the first product, in `get_account` order, whose note is not `paid`" (`brief-b.md:23`). [DOC]

**What the earlier probes saw** (`read-api-and-testing.md:154–155`) [PROBED-earlier]
- Before verification: `{ok:false, error:"identity not verified"}`, and the call is logged in the ledger.
- After verification: `{ok, products:[...]}`. On PUB-11 the ids were `p1`..`p3`. Each product had `type`, `past_due` and `days_late`, plus `card_last4` and `minimum_payment` for a `credit_card`, or `instalment_amount` for a `personal_loan` or `car_loan`.

**How it is scored** [CODE]
- `score.py:31–32` fails the whole case if any `get_account` (or `create_promise`) call returned exactly `"identity not verified"`. The scorer scans every call, so a later correct retry does not save the case.
- `score.py:33` fails the case if `get_account` is called at all when the expected outcome is not-reached.

**Value shapes in the public cases** [DOC]
- `past_due` can carry one decimal, for example `2125.1` (`public-test-set.json:238`) and `310.5` (`:68`).
- Floors such as `637.5` (`:240`), `28.5` (`:115`) and `109.5` (`:413`).
- Card digits with a leading zero: `"0377"` (`:112`).
- Saying these as currency with two decimals is an [INFERRED] choice. PUB-06's check says "promise for 637.50" (`public-test-set.json:261`).

**Traps**
- The order of product ids is [INFERRED]: in `public-test-set.json`, the expected `p1`/`p2`/`p3` follow the listed product order (PUB-11 to PUB-13). A hidden bank may use other ids. Always copy `product_id` from the response; never build it.
- Any missing field (for example no `card_last4` on a loan) is normal. Nothing in the response is `required`.

### 3.3 `create_promise` (`openapi.json:172–233`)

**Summary (L174):** "Record a payment promise. One per product." [DOC]

**Request**

| Field | Type | Format | Required | Lines |
|---|---|---|---|---|
| `customer_id` | string | n/a | yes | 182–184 |
| `product_id` | string | n/a | yes | 185–187 |
| `amount` | number | none: no min, max or precision | yes | 188–190 |
| `date` | string | `date` | yes | 191–194 |

The `required` array is at L196–201. None of these fields has a description. [DOC]

**Response 200:** `ok` (boolean, L214–216), `error` (string, L217–219), `promise_id` (string, L220–222). **Response 500:** L228–230. [DOC]

**Policy this tool encodes**
- **One promise per product.** `brief-a.md:90`: "One promise per product. A recorded promise cannot be changed or cancelled in the same call. If the customer asks, say they can change it in the mobile app." [DOC]
- **Only after a clear yes.** `brief-a.md:88`: "Read the product, the amount and the date back and ask "Do you confirm?". Call `create_promise` only after a clear yes." [DOC]
- **Brief B.** `brief-b.md:15`: "Read all promises back together and ask for one confirmation. Then call `create_promise` once per product." [DOC]
- **No policy checks.** The service records a promise on a holiday or past the deadline (L6), or below the minimum (`hackathon-page.md §Evaluation`). [DOC]
- **The brief's retry rule.** `brief-a.md:91`: "Say the promise is recorded only after `create_promise` returns `ok: true`. If it fails, try once more. If it fails again, say you could not record it and close as `no_promise` / `service_error`." [DOC]
- **Brief B on a double failure.** `brief-b.md:19`: "If one `create_promise` fails twice, keep the promises that were recorded and call `add_note` with reason `service_error` for the failed product." [DOC]
- **The sentence after success.** `brief-a.md:92`: "You will receive a text message confirming this promise." [DOC]
- **A restructuring request after promises.** `brief-b.md:18`: "Promises recorded before the request stay. Promises agreed but not yet recorded are not recorded." [DOC]

**What the earlier probes saw** (`read-api-and-testing.md:156`) [PROBED-earlier]
- A success returns `{ok, promise_id:"pr1"}`.
- The string amount `"220"` was accepted. `99999`, above `past_due`, was also accepted.
- Error strings seen: `"date must be YYYY-MM-DD"`, `"unknown product_id"` and `"this product already has a promise"`.

**How it is scored** [CODE]
- Each promise becomes the key `(product_id, round(float(amount), 2), date)`, and the keys are compared as a multiset with the expected ones (`score.py:21–22`).
- `float()` means a string amount still scores correctly.
- `date` is compared as an exact string.
- `score.py:31–32` also fails the case on a `create_promise` call that returned `"identity not verified"`. That error is implied for `create_promise` before verification, but it was never probed [INFERRED].

**Fault injection**
- PUB-10 declares `"faults": [{"tool": "create_promise", "fail_first_n": 1}]` (`public-test-set.json:435–440`). [DOC]
- Its checks: "exactly one promise in the ledger after the retry" and "agent does not say 'recorded' before a successful call" (`public-test-set.json:432–433`). [DOC]
- How the injected failure is delivered (HTTP 500, or 200 with `ok:false`) and with what error string is [UNCERTAIN] (see §6.6).

**Traps**
- Never use more than two attempts in total (`brief-a.md:91`). The file's 500 text ("may be repeated") puts no limit on repeats, but the brief does. [DOC]
- A client timeout is not a 500: the bank may already have recorded the promise. A retry would then get `"this product already has a promise"` [INFERRED from the probed error string]. The file says nothing about timeouts or idempotency [UNCERTAIN].
- Unprobed: amounts with more than two decimals, zero or negative amounts, non-numeric strings, impossible dates such as `2026-02-30`, and past dates [UNCERTAIN]. Always send canonical values.

### 3.4 `add_note` (`openapi.json:234–297`)

**Summary (L236):** "Brief B: record why a product ended without a promise." [DOC]

**Request**

| Field | Type | Enum | Required | Lines |
|---|---|---|---|---|
| `customer_id` | string | n/a | yes | 244–246 |
| `product_id` | string | n/a | yes | 247–249 |
| `reason` | string | `["refused", "hardship", "dispute", "paid", "service_error"]` | yes | 250–259 |
| `text` | string | n/a | **no** | 260–262 |

The `required` array is at L264–268. No field has a description. [DOC]

**Response 200:** `ok` and `error` (L281–286). **Response 500:** L292–294. [DOC]

**Policy this tool encodes**
- "Brief A never uses `add_note`." (`brief-a.md:119`) [DOC]
- **Brief B rule 8** (`brief-b.md:16`): "For each product without a promise call `add_note` with that `product_id` and a reason: `refused`, `hardship`, `dispute`, `paid` or `service_error`. This also applies when no product gets a promise." The enum matches this list exactly. [DOC]
- **Brief B rule 9** (`brief-b.md:17`): "A dispute or an "already paid" claim on one product does not end the call. Note it and continue with the others." [DOC]
- **Brief B rule 10** (`brief-b.md:18`): "On any transfer (restructuring, support, human) add no notes at all, before or after it." [DOC]
- **Brief B rule 11** (`brief-b.md:19`): a `service_error` note goes on a product whose `create_promise` failed twice. [DOC]

**What the earlier probes saw** (`read-api-and-testing.md:157`) [PROBED-earlier]: a reason outside the enum returns `"unknown reason"`.

**How it is scored** [CODE]
- Notes are compared as a multiset of `(product_id, reason)` (`score.py:23–24`). **`text` is ignored.**
- The scorer reads `n.get("product_id")`, so a note without a `product_id` would still produce a key. A hidden file might make `product_id` optional [INFERRED].

**Traps**
- The summary names "Brief B". Do not hard-code "notes only for multi-product customers". Follow the hidden brief [INFERRED].
- Whether the bank checks a note against a promise already recorded on the same product, or rejects duplicate notes, is [UNCERTAIN]. The scorer would count both.
- Whether `add_note` is gated on verification is [UNCERTAIN].

### 3.5 `schedule_callback` (`openapi.json:298–353`)

**Summary (L300):** "Book a callback." [DOC]

**Request**

| Field | Type | Format | Required | Description (verbatim) | Lines |
|---|---|---|---|---|---|
| `customer_id` | string | n/a | yes | (none) | 308–310 |
| `date` | string | `date` | yes | (none) | 311–314 |
| `time` | string | none; no pattern | yes | `"HH:MM"` | 315–318 |

The `required` array is at L320–324. [DOC]

**Response 200:** `ok` and `error` (L337–342). **Response 500:** L348–350. [DOC]

**What the request lacks:** a product, a phone number, a contact person and a time zone. [DOC]

**Policy (from the brief, not the file)**
- `brief-a.md:32`: "A callback is for today or the next business day, from 10:00 to 19:00, both included, and later than `now`. Call `schedule_callback` with the date and the time, then close as `not_reached` / `callback`." [DOC]
- `brief-a.md:33`: if the offered time is outside the window twice, "do not schedule. Close as `not_reached` / `no_callback`." [DOC]
- Business days are Monday to Friday except the brief's holidays (`brief-a.md:53`). [DOC]
- The bank does not enforce the window [INFERRED from L6].

**What the earlier probes saw** (`read-api-and-testing.md:158`) [PROBED-earlier]: `"11am"` returns `"date must be YYYY-MM-DD and time HH:MM"`.

**How it is scored** [CODE]
- Callbacks are compared as a multiset of `(date, time)`, both exact strings (`score.py:25–26`).
- PUB-02 expects `{"date": "2026-10-15", "time": "11:00"}` (`public-test-set.json:79–84`).

**Gating** [INFERRED]
- This tool must work without identity verification.
- PUB-02 expects a recorded callback, and `score.py:33` forbids `verify_identity` on that case.

**Traps** [INFERRED]
- Use 24-hour time with a two-digit hour, for example `"09:30"`.
- Never send `"11:00:00"` or `"11am"`. Whether `"9:30"` or `"11:00:00"` would be accepted and stored as sent, and so fail the exact match, is [UNCERTAIN].

### 3.6 `transfer_to_agent` (`openapi.json:354–408`)

**Summary (L356):** "Hand the call to a person." [DOC]

**Request**

| Field | Type | Enum | Required | Lines |
|---|---|---|---|---|
| `customer_id` | string | n/a | yes | 364–366 |
| `queue` | string | `["restructuring", "general", "support"]` | yes | 367–374 |

The `required` array is at L376–379. [DOC]

**Response 200:** `ok` and `error` (L392–397). **Response 500:** L403–405. [DOC]

**The queue does not have the same name as the close reason** [DOC]

| Queue sent | Close outcome / reason | Brief rule |
|---|---|---|
| `restructuring` | `transferred` / `restructuring` | `brief-a.md:98` (rule 41: new payment plan or lower instalments) |
| `general` | `transferred` / **`human`** | `brief-a.md:99` (rule 42: a request for a human, after asking once whether you can help) |
| `support` | `transferred` / `support` | `brief-a.md:83` (rule 32: illness, a death in the family or job loss, and the customer accepts) |

**More policy** [DOC]
- `brief-a.md:117`: "If a transfer follows a recorded promise, close as `transferred` with that transfer's reason."
- `brief-a.md:102`: "Rule 42 applies before and after verification."
- `brief-b.md:18`: no notes on any transfer. Promises recorded before a restructuring request stay.

**What the earlier probes saw** (`read-api-and-testing.md:157`) [PROBED-earlier]: a queue outside the enum returns `"unknown queue"`.

**How it is scored** [CODE]: by `queue` only, as a sorted list (`score.py:27`).

**Gating** [INFERRED]: this tool must work before verification, because of `brief-a.md:102`. That was never probed.

### 3.7 `close_call` (`openapi.json:409–470`)

**Summary (L411):** "End the call. Always the last tool call. Nothing is accepted after it." [DOC]

**Request**

| Field | Type | Enum | Required | Description (verbatim) | Lines |
|---|---|---|---|---|---|
| `customer_id` | string | n/a | yes | (none) | 419–421 |
| `outcome` | string | `["promise", "paid", "transferred", "no_promise", "not_verified", "not_reached"]` | yes | (none) | 422–432 |
| `reason` | string | **no enum** | **no** (not in `required`) | "Required for every outcome except promise and paid. See the table in the brief." | 433–436 |

The `required` array is at L438–441 and lists only `customer_id` and `outcome`. [DOC]

**Response 200:** `ok` and `error` (L454–459). **Response 500:** L465–467. [DOC]

**Policy this tool encodes** [DOC]
- It is the last tool call, and nothing is accepted after it (L411).
- `brief-a.md:106`, rule 46: "Every call ends with exactly one `close_call`, with an outcome and, where the table lists one, a reason. It is the last tool call."
- `brief-a.md:121`, rule 47: "Thank the customer and say goodbye before `close_call`."
- `reason` is conditionally required, and its vocabulary comes from the brief's table (`brief-a.md:108–115`; see §7.2).
- Brief B closing rule (`brief-b.md:23`): "With no promise recorded: if every product is noted `paid`, close as `paid`. Otherwise close as `no_promise` with the reason of the first product, in `get_account` order, whose note is not `paid`. With several products, `promise` wins whenever at least one promise was recorded, except rule 10 above." Rule 10 is the restructuring transfer.

**What the earlier probes saw** (`read-api-and-testing.md:159`) [PROBED-earlier]
- `"no_contact"` returns `"unknown outcome"`.
- The bank checks that the outcome and the reason fit together, and names the allowed reasons in its error. Example: `no_promise` needs one of `refused, hardship, dispute, service_error`. The exact wording of that error was not recorded [UNCERTAIN].
- After a close, every tool returns `"the call is already closed"`, so a session can be used only once.

**How it is scored** [CODE]
- `(led.get("outcome"), led.get("reason"))` must equal `(expected.outcome, expected.get("reason"))` (`score.py:19–20`).
- The expected reason is `null` for `promise` and `paid`, for example at `public-test-set.json:30` and `:337`. So the ledger's `reason` must be `null` for those two outcomes, not `""` and not `"none"`.
- `calls[-1]["tool"] == "close_call"` (`score.py:29`).

**Kit example** [CODE]
- `base-agent.json:395` has a `pre_process_code` that deletes `reason` from the body when the outcome is `promise` or `paid`.
- Its `close_call` is a workflow-level lifecycle tool with `alwaysRunsAt: ["end_of_call"]` (`base-agent.json:330–339`).
- The docs say that in an engine-run call an unset variable drops the field, but a variable set to `""` sends the field empty (`tools-and-code.md:113–115`). That is why the pre-hook is needed [INFERRED].
- For `end_of_call` lifecycle tools, `response_mapping` is not applied (`tools-and-code.md:562`). [DOC]

**A hint that the outcome may be renamed** [CODE]: `score.py:33` accepts `not_reached`, `no_contact` or `unreached` as the "not on the line" outcome. A hidden brief may rename `not_reached` [INFERRED].

**Traps**
- `reason` is optional in the schema but required by its description and by the practice bank [PROBED-earlier]. Build a per-outcome reason enum from the brief [INFERRED].
- Any tool call after `close_call` is rejected. Whether it is still logged in `calls[]` is [UNCERTAIN]. If it is, it breaks `score.py:29`'s last-call check.

---

## 4. Response shapes and error semantics

### 4.1 The kinds of answer

| Situation | What the bank does | Source | Label |
|---|---|---|---|
| Action carried out | HTTP 200, `ok: true`, plus the tool's fields | L51 | [DOC] |
| Action not carried out (validation, gating, an enum value, a duplicate, a closed call) | HTTP 200, `ok: false`, `error: "<text>"`. The call is still logged in the ledger: this was seen for `get_account` [PROBED-earlier], and assumed for the other tools [INFERRED]. | L51; `read-api-and-testing.md:144, 154` | [DOC], [PROBED-earlier] |
| Service failure | HTTP 500: "The service failed. Nothing was recorded. The call may be repeated." No body is documented. | L84 and its repeats | [DOC] |
| Unknown `customer_id` | HTTP 404, `"unknown customer_id"`. Not in the file. Whether the body also carries `ok:false` is [UNCERTAIN]. | `read-api-and-testing.md:144, 240` | [PROBED-earlier] |
| Missing team key (practice routes only) | HTTP 401, text beginning "send X-Team-Key…". The full text was truncated in the source. | `read-api-and-testing.md:121` | [PROBED-earlier] |
| Wrong team key on a ledger | `"unknown customer_id for this team key"`. The status code was not recorded [UNCERTAIN]. | `read-api-and-testing.md:122` | [PROBED-earlier] |
| Unknown practice case, empty body, or a custom customer object | HTTP 404, `"unknown practice case"` | `read-api-and-testing.md:129` | [PROBED-earlier] |
| `GET /` | 404 JSON | `read-api-and-testing.md:120` | [PROBED-earlier] |

A 401 cannot come from a tool call, because "The seven tool calls need no key" (L6). [DOC]

`score.py:15` parses the body of any HTTP error as JSON (`json.load(e)`). So the practice routes return JSON error bodies [CODE → INFERRED].

### 4.2 Known error strings

| Error string (exact) | Raised by | Label |
|---|---|---|
| `identity not verified` | `get_account` [PROBED-earlier]. `create_promise` is implied by `score.py:32` [CODE]. | [PROBED-earlier], [CODE] |
| `field must be date_of_birth or phone_last4` | `verify_identity` | [PROBED-earlier] |
| `date must be YYYY-MM-DD` | `create_promise` | [PROBED-earlier] |
| `unknown product_id` | `create_promise` (also `README.md:102` [DOC]) | [PROBED-earlier] |
| `this product already has a promise` | `create_promise` | [PROBED-earlier] |
| `unknown reason` | `add_note` | [PROBED-earlier] |
| `unknown queue` | `transfer_to_agent` | [PROBED-earlier] |
| `date must be YYYY-MM-DD and time HH:MM` | `schedule_callback` | [PROBED-earlier] |
| `unknown outcome` | `close_call` | [PROBED-earlier] |
| An error for an outcome and reason that do not fit together, listing the allowed reasons (exact wording not recorded) | `close_call` | [PROBED-earlier] |
| `the call is already closed` | Any tool after a close | [PROBED-earlier] |
| `unknown customer_id` (HTTP 404) | Any tool | [PROBED-earlier] |
| `unknown customer_id for this team key` | Ledger route with the wrong key | [PROBED-earlier] |
| `unknown practice case` (HTTP 404) | `/v1/practice/sessions` | [PROBED-earlier] |

All probe strings come from `read-api-and-testing.md:121–159`.

**Not yet seen** [UNCERTAIN]:
- The error, if any, at the wrong-answer limit.
- The error for an unreadable date.
- The error for an injected fault.
- Errors for any `ok:false` from `transfer_to_agent` or `close_call` other than the enum checks.

### 4.3 Which keys are present

- **The schema guarantees no key.** No response schema has a `required` list. [DOC]
- **Keys seen in the probes.** A probed `verify_identity` success had no `error` key. One re-verify had no `all_verified` key. [PROBED-earlier]
- **A likely pattern.** Expect `error` only when `ok` is false [INFERRED].
- **Not known** [UNCERTAIN]:
  - Whether `ok` is always present.
  - When exactly `all_verified` is left out.

### 4.4 How a bank response reaches the Freya workflow

This section is about the docs, not the bank, but every route depends on it.

| Fact | Source | Label |
|---|---|---|
| An `api_call` result is an envelope: `{status, data, message, status_code, header}`. `data` is the JSON body. The example shows `"status": "success"` and `"message": "Successfully executed POST request"`. | `tools-and-code.md:250–262` | [DOC] |
| The engine flattens every result into the variable table: `<tool>_args.<field>`, `<tool>_response.status`, `<tool>_response.data.<key>`, `<tool>_response.message`, `<tool>_response.status_code`, `<tool>_response.header.<Name>`, `<tool>_status_code` and `<tool>_success_count`. Each call of the same tool overwrites the previous `_args` and `_response`. | `tools-and-code.md:264–279` | [DOC] |
| Booleans arrive as strings such as `"true"`. Test both `"true"` and `"True"`. | `tools-and-code.md:270, 286, 584` | [DOC] |
| The base agent routes on `verify_identity_response.data.all_verified` equal to `"true"` OR `"True"`. | `base-agent.json:117–137` | [CODE] |
| Mapping paths start with `data.`. | `tools-and-code.md:283` | [DOC] |
| Per-tool counters `<toolName>_success_count` and `<toolName>_failure_count` | `tools-and-code.md:321–328` | [DOC] |
| A post-hook gets `result` as the envelope and can add keys inside `result["data"]`, which reach the model. A pre-hook gets `vars` and `config` (`url`, `method`, `headers`, `body`) and can rewrite the body. | `tools-and-code.md:393–416` | [DOC] |
| Bare results such as `{"ok": true, "verified": true}` sometimes leave the model silent, or it ignores `"verified": false`. A post-hook `what_to_do_next` line fixed this in a working builder. | `tools-and-code.md:566–575` | [DOC] |

**What follows** [INFERRED]
- An HTTP 200 with `ok:false` arrives as a **transport success**. The workflow must test `data.ok`, not the envelope `status`.
- It probably also counts as a success for `<tool>_success_count`.

**Not documented** [UNCERTAIN]:
- The envelope for a 500 or a 404: the `status` value, whether `data` is set, and `status_code`.
- Whether `<tool>_failure_count` rises on a 500.
- Whether the envelope differs on a timeout.

### 4.5 Retries, timeouts and idempotency

| Fact | Source | Label |
|---|---|---|
| `config.maxRetries`: "Tool-level retries of a failed call" / "Tool-level retries after a failed response". There is no documented default, and whether a 500 or an `ok:false` counts as "failed" is undocumented. | `tools-and-code.md:53, 352` | [DOC]; the gap is [UNCERTAIN] |
| `connect_retries` (default `2`, hard cap `5`) retries only connection failures. "HTTP error statuses and timeouts are not retried by it." All attempts share one 30-second budget. | `tools-and-code.md:353–363` | [DOC] |
| "The working builder sets `maxRetries` to `0` on tools that write data and to `2` on its read-only `pre_actions` call. A retried write can record the same thing twice if the API is not idempotent." | `tools-and-code.md:365` | [DOC] |
| The base agent uses `maxRetries: 0` and `timeoutMs: 12000` on `verify_identity`, `get_account`, `create_promise` and `close_call`. | `base-agent.json:9–10, 160–161, 204–205, 334–335` | [CODE] |
| The bank says a repeat after a 500 is safe ("Nothing was recorded"). | L84 | [DOC] |
| The brief allows two attempts in total for a promise. | `brief-a.md:91` | [DOC] |

**How these fit together** [INFERRED]
- The brief governs how many times to try. The 500 text only guarantees that a repeat cannot duplicate a record.
- An automatic platform retry would hide failures from the brief's count of two. So `maxRetries: 0` on write tools is the safe setting. It is a recommendation, not a rule.
- A client-side timeout is not covered: the bank may have recorded the call.
- Whether an `ok:false` caused by the agent's own bad input (for example `date must be YYYY-MM-DD`) counts as one of the brief's "fails" is [UNCERTAIN]. A reasonable design counts only 500s and timeouts as service failures, and fixes its own input errors.

---

## 5. Session state: what the bank accepts, and when

| State of one `customer_id` | `verify_identity` | `get_account` | `create_promise` | `add_note` | `schedule_callback` | `transfer_to_agent` | `close_call` |
|---|---|---|---|---|---|---|---|
| Fresh, not verified | accepted [DOC L17] | **refused**, `identity not verified` [PROBED-earlier]; fails the case (`score.py:31–32`) [CODE] | refused, `identity not verified` [INFERRED from `score.py:32`] | [UNCERTAIN] | accepted [INFERRED: PUB-02] | accepted [INFERRED: `brief-a.md:102`] | accepted [INFERRED: `not_reached`/`not_verified` outcomes need it] |
| Some answers right, not all | accepted | refused [DOC L91] | refused [INFERRED] | [UNCERTAIN] | accepted [INFERRED] | accepted [INFERRED] | accepted [INFERRED] |
| Three wrong answers used | [UNCERTAIN]: what a 4th answer returns, even a correct one | presumably refused [INFERRED] | presumably refused [INFERRED] | [UNCERTAIN] | [UNCERTAIN] | [UNCERTAIN] | accepted [INFERRED: `not_verified`/`failed`] |
| All verified | accepted; a re-verify may omit `all_verified` [PROBED-earlier] | accepted [PROBED-earlier] | accepted, once per product [DOC L174] | accepted [INFERRED] | accepted [INFERRED] | accepted [INFERRED] | accepted |
| Product already has a promise | n/a | n/a | refused, `this product already has a promise` [PROBED-earlier] | [UNCERTAIN] (whether a note on a promised product is refused) | n/a | n/a | n/a |
| After `close_call` | refused, `the call is already closed` [PROBED-earlier] | same | same | same | same | same | same ("Nothing is accepted after it", L411) |

A practice session is single-use: once closed, it cannot be reused (`read-api-and-testing.md:159, 303`). [PROBED-earlier]

---

## 6. Practice sessions and the ledger

### 6.1 Practice routes

| Route | What it does | Source | Label |
|---|---|---|---|
| `POST /v1/practice/sessions`, body `{"case": "PUB-xx"}`, header `x-team-key` | Returns `{ok, variables:{customer_id:"c_<uuid-ish>", first_name, last_name, title, now}}`. | `run_cases.py:86` [CODE]; `read-api-and-testing.md:126` | [CODE], [PROBED-earlier] |
| Same route, called again | Each call makes a fresh `customer_id`. | `read-api-and-testing.md:127` | [PROBED-earlier] |
| Same route with `now` in the body | `now` is ignored. It is fixed per case, at `2026-10-14T11:00` for every PUB case. | `read-api-and-testing.md:128` | [PROBED-earlier] |
| Same route with an unknown case, an empty body or a custom customer object | 404 `"unknown practice case"`. Custom customers cannot be created. | `read-api-and-testing.md:129` | [PROBED-earlier] |
| `GET /v1/practice/ledger/{customer_id}`, header `x-team-key` | The ledger, see §6.3 | `score.py:38` [CODE]; `read-api-and-testing.md:133` | [CODE], [PROBED-earlier] |

**Server-side data** [PROBED-earlier]
- The bank stores each case's products, identity and failure injection on the server (`read-api-and-testing.md:130`). This is the probe author's reading.
- The case file's own `products` and `identity` are assumed to match what the bank holds [INFERRED]. The PUB-01 and PUB-11 probes agree with the file.

**The page agrees** [DOC]
- "Builder cannot open its own practice customers: practice bank serves PUB-01..13 only" (`hackathon-page.md §FAQ`).
- "Every case runs Wed 14 Oct 2026 11:00" (`hackathon-page.md §Data`). 2026-10-14 is a Wednesday [CODE, checked locally].

### 6.2 Session variables

- **The fields.** `customer_id`, `first_name`, `last_name`, `title` and `now` [PROBED-earlier]. These match the brief's call variables (`brief-a.md:15–20`) [DOC].
- **What `run_cases` passes.** It gives the session's variables **verbatim** to the simulation as `customerVariablesMap[persona_id]` (`run_cases.py:86, 88`) [CODE].
- **Where `now` comes from.** It always comes from the bank, not from the case file. The case file's `variables` are used only for the persona's name (`run_cases.py:36–37`) [CODE].

### 6.3 Ledger fields

From `read-api-and-testing.md:133–141` [PROBED-earlier], cross-checked against the keys `score.py` reads [CODE]:

| Ledger key | Shape | Read by `score.py`? |
|---|---|---|
| `case` | the PUB id | no |
| `team` | a hash of the team key | no |
| `now` | the session's `now` | no |
| `verified` | `{field: bool}` | no |
| `wrong` | count of wrong answers | no |
| `hinted` | meaning unknown [UNCERTAIN] | no |
| `promises` | `[{promise_id, product_id, type, amount, date}]` | yes, `product_id`, `amount`, `date` (`score.py:21–22`) |
| `notes` | list; `score.py` reads `product_id` (via `.get`) and `reason` | yes (`score.py:23–24`) |
| `callbacks` | list; `score.py` reads `date` and `time` | yes (`score.py:25–26`) |
| `transfers` | list; `score.py` reads `queue` | yes (`score.py:27`) |
| `outcome`, `reason` | the values from `close_call` | yes, via `.get` (`score.py:19`) |
| `failures` | `{tool: n}`, the injected-failure counters (PUB-10 fails the first `create_promise`) | no |
| `calls` | `[{n, tool, args, status, result}]`: the exact arguments the agent sent, and what came back | yes, `tool` and `result.get("error")` (`score.py:28–33`); `run_cases.py:98–99` prints the tool chain |
| `last_at` | a timestamp | no |

**Code facts about the ledger**
- `score.py` uses `led["promises"]`, `led["notes"]`, `led["callbacks"]`, `led["transfers"]` and `led["calls"]` as hard keys, so they must always exist. `outcome` and `reason` are read with `.get` and may be missing. [CODE]
- `c["result"].get("error")` assumes every logged `result` is an object. What `result` holds for an injected 500 is [UNCERTAIN].

### 6.4 How the kit scorer reads the ledger

`score_ledger(case, led)` (`score.py:17–34`) [CODE]. A case passes the ledger part only when all eight hold:

1. `(outcome, reason)` exactly equals `(expected.outcome, expected.reason)`. The expected reason is `null` for `promise` and `paid` (L19–20).
2. Promises match as a sorted multiset of `(product_id, round(float(amount), 2), date)` (L21–22).
3. Notes match as a sorted multiset of `(product_id, reason)`. The note `text` is ignored (L23–24).
4. Callbacks match as a sorted multiset of `(date, time)` (L25–26).
5. Transfers match as a sorted list of `queue` (L27).
6. `calls` is not empty and `calls[-1]["tool"] == "close_call"` (L28–29).
7. No `get_account` or `create_promise` call has `result.error == "identity not verified"` (L31–32).
8. If the expected outcome is in `("not_reached", "no_contact", "unreached")`, there is no `verify_identity` or `get_account` call at all (L33).

**The whole verdict.** `run_cases.py:95–97` also requires the simulation judge's run `outcome == "pass"` [CODE]. The README states the three conditions for a handled customer: outcome, policy and honesty (`README.md:57–63`) [DOC].

**Running the scorer by hand.** `python tools/score.py <case_id> <customer_id>` (`score.py:36–39`). [CODE]

### 6.5 How `run_cases.py` uses sessions

- **One fresh session per run.** Each case gets a new session in every run (`run_once`, `run_cases.py:86`). [CODE]
- **Reps.** `--reps N` repeats the whole simulation N times (`run_cases.py:65`). A case counts only if it passes every rep (`run_cases.py:72–73`). [CODE]
- **The ledger.** It is read after the simulation finishes (`run_cases.py:93`). The printed tool chain shortens `verify_identity` to `verify` and `create_promise` to `promise` (`run_cases.py:99`). [CODE]
- **Why one persona cannot run several times.** `runsPerPersona` greater than 1 would share one `customer_id`. The second `close_call` would then be rejected with "the call is already closed" [INFERRED from PROBED-earlier, `read-api-and-testing.md:299`].

### 6.6 Fault injection

- **What is declared.**
  - Only PUB-10 has `faults`: `[{"tool": "create_promise", "fail_first_n": 1}]` (`public-test-set.json:435–440`). [DOC]
  - The bank applies it on the server, and the ledger counts it in `failures{tool: n}` (`read-api-and-testing.md:130, 139`). [PROBED-earlier]
- **Why the earlier probes never saw a 500.** They touched only PUB-01 and PUB-11 (`read-api-and-testing.md:5`), and neither case has `faults`. [DOC] + [INFERRED]
- **What is not known** [UNCERTAIN]:
  - Whether an injected failure is an HTTP 500 (as the file's 500 text suggests) or an HTTP 200 with `ok:false`.
  - Its body and error string.
  - Whether hidden cases inject faults on other tools. The page says hidden customers include the same kinds of call (`hackathon-page.md §Evaluation`), and a "Tool failure" family exists in the public set (`public-test-set.json:394`).
- **How to find out within the rules.** Read the PUB-10 ledger's `calls[]` and `failures` after a normal `run_cases.py --only PUB-10` run. [INFERRED]

### 6.7 The dashboard test customer

`hackathon-page.md §FAQ` [DOC]:
- "the workspace has one practice customer for dashboard test calls: DOB 14 March 1988, last four 4471." These are the same identity values as PUB-01 (`public-test-set.json:15–16`).
- "After a call closes, that customer starts fresh after 5 min idle."
- "run_cases.py opens a fresh customer per case."

How that customer's `customer_id` reaches a dashboard call is not stated [UNCERTAIN]. `base-agent.json:401–406` sets `test_variables` without a `customer_id`.

### 6.8 What practice can and cannot do

- **No practice customers for hidden briefs.** "Hidden briefs have no practice cases, only the tool API file." (`hackathon-page.md §FAQ`) [DOC]
- **Chat as a test route.** "to check an agent on a brief with no cases, talk to it with POST /api/v2/chat/message" (`hackathon-page.md §FAQ`; `api.md:240–252`). [DOC]
- **Chat with a made-up `customer_id`.** The bank answers 404 `"unknown customer_id"` (`read-api-and-testing.md:240`) [PROBED-earlier]. So only behaviour before the first tool call can be tested that way [INFERRED].
- **Practice customers on a hidden agent.** They work only if the hidden file keeps the same host, paths and identity fields [INFERRED].
- **No probing.** "Do not probe or load-test the platform." (`hackathon-page.md §Rules`) [DOC]
  - Normal kit usage, such as `run_cases.py` sessions and ledger reads, is how the kit is meant to be used.
  - Direct calls to inspect a hidden bank are not allowed. Read everything from the supplied file. [INFERRED]

---

## 7. Enums and how the brief and the scorer use them

### 7.1 Every enum in the file

| Enum | Values | Lines | Brief usage | Scorer usage |
|---|---|---|---|---|
| `verify_identity.field` | `date_of_birth`, `phone_last4` | 30–33 | Asked in this order, one at a time (`brief-a.md:40`) | Not scored directly; banned on not-reached cases (`score.py:33`) |
| `verify_identity` response `hint` | `day_month_swapped` | 74–76 | `brief-a.md:42` | n/a |
| `products[].type` | `credit_card`, `personal_loan`, `car_loan` | 134–138 | Spoken as "credit card ending {card_last4}", "personal loan", "car loan" (`brief-a.md:49`). Floor map at `brief-a.md:71`. | n/a (the ledger promise carries `type` [PROBED-earlier]) |
| `add_note.reason` | `refused`, `hardship`, `dispute`, `paid`, `service_error` | 252–258 | `brief-b.md:16` | `(product_id, reason)` (`score.py:23–24`) |
| `transfer_to_agent.queue` | `restructuring`, `general`, `support` | 369–373 | `brief-a.md:83, 98, 99` | `queue` (`score.py:27`) |
| `close_call.outcome` | `promise`, `paid`, `transferred`, `no_promise`, `not_verified`, `not_reached` | 424–431 | Outcome table (`brief-a.md:108–115`) | Exact `(outcome, reason)` (`score.py:19–20`) |
| `close_call.reason` | **not an enum**: a free string | 433–436 | The brief's table | Exact match; must be `null` for `promise` and `paid` |

### 7.2 The outcome and reason table (Brief A, `brief-a.md:108–115`) [DOC]

| Outcome | Reason | When |
|---|---|---|
| `promise` | none | at least one promise was recorded |
| `paid` | none | rule 39 |
| `transferred` | `restructuring`, `human`, `support` | rules 41, 42, 32 |
| `no_promise` | `refused`, `hardship`, `dispute`, `service_error` | rules 31 and 45, 32, 40, 37 |
| `not_verified` | `failed`, `declined` | rules 14, 15 |
| `not_reached` | `callback`, `no_callback`, `wrong_number`, `deceased`, `unclear` | rules 6, 7, 8, 9, 3 |

- "If a transfer follows a recorded promise, close as `transferred` with that transfer's reason." (`brief-a.md:117`)
- The `no_promise` reasons are exactly `add_note.reason` minus `paid` (`brief-b.md:16`) [DOC]. The probed allowed-reasons error for `no_promise` lists the same four [PROBED-earlier].

### 7.3 Queue to close reason

| Queue | Close reason |
|---|---|
| `restructuring` | `restructuring` |
| `general` | **`human`** |
| `support` | `support` |

Sources: `brief-a.md:83, 98, 99`. [DOC]

### 7.4 Brief B closing (`brief-b.md:23`) [DOC]

| Situation | Close as |
|---|---|
| At least one promise recorded | `promise`, unless a restructuring transfer happened (then `transferred` / `restructuring`, `brief-b.md:18`) |
| No promise; every product noted `paid` | `paid` |
| No promise; otherwise | `no_promise` with the reason of the first product, in `get_account` order, whose note is not `paid` |

---

## 8. What the bank holds for the 13 practice customers

Everything here is from `public-test-set.json` [DOC]. Product ids are not in the case file; `p1..pN` follows the listed order [INFERRED].

| Case (lines) | Brief | DOB / phone_last4 | Products: type, card_last4, past_due, days_late, floor | Faults | Expected ledger |
|---|---|---|---|---|---|
| PUB-01 (2–48) | A | 1988-03-14 / 4471 | p1 credit_card 4821, 420.0, 6, min 126.0 | none | `promise`/null; p1 420.0 2026-10-14 |
| PUB-02 (49–92) | A | 1979-11-02 / 0358 | p1 personal_loan, 310.5, 11, inst 103.5 | none | `not_reached`/`callback`; callback 2026-10-15 11:00 |
| PUB-03 (93–132) | A | 1992-07-21 / 6630 | p1 credit_card 0377, 95.0, 4, min 28.5 | none | `not_verified`/`failed` |
| PUB-04 (133–177) | A | 1984-01-30 / 2219 | p1 car_loan, 1250.0, 14, inst 400.0 | none | `promise`/null; p1 1250.0 2026-10-23 |
| PUB-05 (178–217) | A | 1990-09-09 / 8846 | p1 personal_loan, 780.0, 21, inst 260.0 | none | `no_promise`/`hardship` |
| PUB-06 (218–263) | A | 1986-05-17 / 1502 | p1 credit_card 1903, 2125.1, 12, min 637.5 | none | `promise`/null; p1 637.5 2026-10-16 |
| PUB-07 (264–308) | A | 1975-12-05 / 7093 | p1 personal_loan, 540.0, 5, inst 180.0 | none | `promise`/null; p1 540.0 2026-10-27 |
| PUB-08 (309–347) | A | 1993-04-28 / 3317 | p1 credit_card 5512, 180.0, 5, min 54.0 | none | `paid`/null |
| PUB-09 (348–390) | A | 1981-08-11 / 5560 | p1 personal_loan, 2100.0, 28, inst 700.0 | none | `transferred`/`restructuring`; transfer `restructuring` |
| PUB-10 (391–441) | A | 1989-02-23 / 9904 | p1 credit_card 7740, 365.0, 8, min 109.5 | `create_promise` `fail_first_n: 1` | `promise`/null; p1 365.0 2026-10-16 |
| PUB-11 (442–509) | B | 1987-06-03 / 2288 | p1 credit_card 2288, 220.0, 9, min 66.0; p2 personal_loan, 640.0, 9, inst 213.0; p3 car_loan, 75.0, 3, inst 25.0 | none | `promise`/null; p1 220.0, p2 640.0, p3 75.0, all on 2026-10-16 |
| PUB-12 (510–577) | B | 1983-10-19 / 4410 | p1 credit_card 9015, 510.0, 16, min 153.0; p2 personal_loan, 1320.0, 16, inst 440.0; p3 car_loan, 140.0, 7, inst 46.0 | none | `promise`/null; p1 510.0 2026-10-15; notes p2 `refused`, p3 `refused` |
| PUB-13 (578–634) | B | 1991-01-08 / 6604 | p1 credit_card 6604, 300.0, 4, min 90.0; p2 personal_loan, 900.0, 20, inst 300.0 | none | `promise`/null; p1 300.0 2026-10-30, p2 900.0 2026-10-23 |

**What the public expected ledgers never exercise** [DOC, by inspection; the consequence is INFERRED]

| Kind | Values never expected in any public case |
|---|---|
| Transfer queues | `general`, `support` |
| `add_note` reasons | `hardship`, `dispute`, `paid`, `service_error` (only `refused` appears, in PUB-12) |
| Outcome / reason pairs | `transferred`/`human`, `transferred`/`support`; `no_promise`/`refused`, `dispute`, `service_error`; `not_verified`/`declined`; `not_reached`/`no_callback`, `wrong_number`, `deceased`, `unclear` |
| Response field | `hint: day_month_swapped`. No public script describes a swapped answer. |

Rules that touch these tools therefore get no green or red signal from the practice set. They must come out right from the brief alone.

---

## 9. How the kit example differs from the file

These are traps for anyone who copies `examples/base-agent.json`. [CODE]

| Point | Example | File |
|---|---|---|
| `close_call.outcome` enum | 4 values: `promise`, `no_promise`, `not_verified`, `not_reached` (`base-agent.json:362–367`) | 6 values (L424–431). `README.md:34` says the example uses four tools and "handles only the simplest customers". |
| `close_call.reason` description | "Leave out for promise. no_promise: refused. not_verified: failed (wrong answers) or declined (would not answer). not_reached: wrong_number or unclear." This is incomplete (`base-agent.json:359`). | "Required for every outcome except promise and paid. See the table in the brief." (L435) |
| `close_call.outcome` description | "promise: a payment promise was recorded. no_promise: verified customer, no promise. not_verified: the identity check did not pass. not_reached: the right person was not on the line." (`base-agent.json:370`). It defines only the example's four outcomes; `paid` and `transferred` have no definition. [CODE] | `outcome` has **no** description, only the 6-value enum (L422–431). The meaning of each outcome lives in the brief's outcome table (§7.2). [DOC] |
| `close_call` tool-level text | `function.description`: "Record how the call ended, from the conversation." (`base-agent.json:393`). It drops both rules in the file's summary: "last tool call" and "Nothing is accepted after it". [CODE] | Path `summary`: "End the call. Always the last tool call. Nothing is accepted after it." (L411) [DOC] |
| `close_call` body defaults | `reason` → `"{{reason}}"` (`:358`); `outcome` → `"{{outcome}}"` (`:369`); `customer_id` → `"{{customer_id}}"` (`:374`). [CODE] A `{{var}}` default that has a value is baked and hidden from the model (`docs/tools-and-code.md:80–84`); if a `{{var}}` is still unresolved at a lifecycle run, "one model call fills the parameters" (`docs/tools-and-code.md:561`). Nothing in the example sets `outcome` or `reason`, so that model call fills them, reading the descriptions at `:359` and `:370` [INFERRED]. | No defaults on any field (L419–436) [DOC] |
| `required` lists in the body | `customer_id` is left out because it is baked from `{{customer_id}}`. `verify_identity` `["field","answer"]` (`:24–27`); `get_account` `[]` (`:175`); `create_promise` `["product_id","amount","date"]` (`:219–223`); `close_call` `["outcome"]` (`:352–354`). | `customer_id` is required on all seven. Whether including it changes what the model sees is [UNCERTAIN]. |
| Descriptions | Rewritten, for example `answer`: "date_of_birth as YYYY-MM-DD, phone_last4 as four digits." (`:41`); `product_id`: "product_id from the account result, for example p1." (`:238`) | See §3 |
| Retries and timeouts | `maxRetries: 0`, `timeoutMs: 12000` on the four bank tools (`:9–10, 160–161, 204–205, 334–335`) | Nothing about retries except the 500 text |
| `close_call` placement | Workflow-level lifecycle tool, `alwaysRunsAt: ["end_of_call"]` (`:330–339`), with a pre-hook that drops `reason` for `promise`/`paid` (`:395`) | n/a |
| URL | Hard-coded `https://freya-bank-mock.freyavoice.workers.dev/v1/<tool>` (`:20, 171, 215, 348`) | `servers[0].url` (L10) |

**A trap in the example builder** [DOC → INFERRED]
- The example skill reads the brief, "then `tools/openapi.json`" (`SKILL.md:12`), and takes "every tool field and allowed value from `tools/openapi.json`" (`SKILL.md:18`).
- The final run passes the hidden file as a separate argument: `python3 builder/build.py {brief_path} {tool_api_path}`, for example `briefs/hidden-1.openapi.json` (`hackathon-page.md §Submit`).
- A builder that always reads `tools/openapi.json` would build the hidden agent against the wrong file.

---

## 10. What the hidden OpenAPI files will likely change

### 10.1 What is stated [DOC]

- "Each final brief comes with its own tool API file. The seven tool names stay the same. The fields and the allowed values can change." (`README.md:72`; also `hackathon-page.md §Overview`)
- The rules will differ: "other numbers and limits, other identity questions, another outcome table, another calendar" (`README.md:71`).
- One final brief is "a clean specification". The other is "raw bank material (a mail, a policy extract, a memo that changes it, a code list)" (`README.md:71`).
- "The raw-material brief is ONE Markdown file with its own tool API file next to it." (`hackathon-page.md §FAQ`)
- Run command: `python3 builder/build.py {brief_path} {tool_api_path}` (`hackathon-page.md §Submit`).
- You may not write anything from a hidden brief into the builder: "no rule, no value, no name" (`README.md:73`).

### 10.2 Element by element

| Element (today) | Chance of change | Evidence | Builder handling [INFERRED] |
|---|---|---|---|
| The 7 paths and tool names | Stays | `README.md:72` [DOC] | Key everything by path name |
| `servers[0].url` | Unknown | Not stated | Always read it from the supplied file. Never hard-code the host. |
| `verify_identity.field` enum | **High** | "other identity questions" (`README.md:71`). Persona templates exist for `postcode`, `birth_year`, `company_number` and `founded_year`, plus a generic "Your <field> is X" (`run_cases.py:41–44`) [CODE]. | One question per enum value. Formats come from the `answer` description and the brief; order and count come from the brief. |
| `answer` description (formats) | **High** (follows `field`) | Same | Pass it verbatim into the tool description; build a per-field normaliser |
| Wrong-answer limit in the L17 summary | **High** | "other numbers and limits" | Take the number from the brief, cross-check it with the summary, and trust `wrong_answers_left` at run time |
| `hint` enum | Medium | Tied to the DOB field | Handle any `hint` generically, with the brief's rule for it |
| Response field names (`verified`, `wrong_answers_left`, `all_verified`) | Medium | "fields ... can change" | Route on whatever fields the file declares; tolerate missing keys |
| "both questions" in the L91 summary | Medium (follows the question count) | Same | Gate on the bank's "all verified" signal, not on a count |
| `products[].type` enum | Medium | "allowed values can change" | Build the spoken-name map and the floor map from the brief, keyed by enum value |
| Floor fields and the "cards only" / "loans only" notes | Medium | Same; the floor rule may become a percentage or a fixed value | Read field names and type notes from the file; take the floor rule from the brief |
| `create_promise` fields and "One per product" | Low to medium | Generic | Generic leaf generation; honour any extra required field |
| `add_note.reason` enum | **High** | Mirrors the outcome table ("another outcome table") | Generate it from the file |
| Whether `add_note.product_id` is required | Medium | `score.py:23` uses `n.get("product_id")` [CODE] | Follow the file's `required` list |
| `add_note` summary ("Brief B: ...") | Medium | It names the brief | Do not read "Brief B" as "notes only for multi-product customers" |
| `schedule_callback` date and time formats | Low to medium | Generic | Use the file's `format` and description |
| `transfer_to_agent.queue` enum | Medium to high | "allowed values can change" | Map queue to close reason from the brief's table, never by matching names |
| `close_call.outcome` enum | **High** | "another outcome table"; `score.py:33` also accepts `no_contact` and `unreached` [CODE] | Generate it from the file; join it with the brief's table |
| `close_call.reason` (free string; which outcomes need it) | **High** | The description defers to the brief | Build a per-outcome reason enum from the brief or its code list; leave `reason` out where the table has none |
| `info.description` and the 200/500 texts | Low | Same mock family [INFERRED] | Still handle `ok:false` and 500 generically |
| Schema structure (`$ref`, `components`, nested objects, YAML) | Unknown | Today everything is inline and `components` is empty (L13) | The parser should resolve `$ref`, tolerate missing descriptions, and handle nested and array leaves |
| Constraints (`minimum`, `pattern`, `default`) and 4xx responses | Unknown | None today (§2.2) | If present, copy them into the tool leaf and the pre-hook validation |

---

## 11. Earlier probe facts in one table

All of these come from `read-api-and-testing.md` [PROBED-earlier].
- **When and how.** The probes ran on 2026-10-10 with a scratch team key, on two practice sessions, PUB-01 and PUB-11 (line 5).
- **What they could not see.** They never touched a case with faults, so they never saw a 500.
- **Not to be repeated.** They are recorded here so nobody runs them again.

| # | Fact | Line |
|---|---|---|
| P1 | The bank ties a call to a customer only through `customer_id` in the body; the seven tool calls need no key | 94 |
| P2 | `GET /` returns 404 JSON | 120 |
| P3 | Every `/v1/practice/*` route checks `X-Team-Key` (16 or more characters) before routing; without it, 401 "send X-Team-Key…" | 120–121 |
| P4 | A wrong key on a ledger gives `"unknown customer_id for this team key"`; the ledger shows `team` as a hash of the key | 122–123 |
| P5 | `POST /v1/practice/sessions` `{"case":"PUB-xx"}` returns `{ok, variables:{customer_id:"c_<uuid-ish>", first_name, last_name, title, now}}`; each call makes a fresh `customer_id` | 126–127 |
| P6 | `now` is fixed per case (`2026-10-14T11:00` for every PUB case); a `now` in the request body is ignored | 128 |
| P7 | An unknown case, empty body or custom customer object gives 404 `"unknown practice case"` | 129 |
| P8 | Products, identity and failure injection are stored per case on the server | 130 |
| P9 | Ledger keys: `case`, `team`, `now`, `verified{field:bool}`, `wrong`, `hinted`, `promises[{promise_id, product_id, type, amount, date}]`, `notes`, `callbacks`, `transfers`, `outcome`, `reason`, `failures{tool:n}`, `calls[{n, tool, args, status, result}]`, `last_at` | 133–141 |
| P10 | Business errors are HTTP 200 with `ok:false`; the exceptions are unknown `customer_id` (404) and the key errors (401) | 144 |
| P11 | `verify_identity` success returns `{ok, verified, wrong_answers_left, all_verified}` | 149 |
| P12 | `"14 March 1988"` and `"3 June 1987"` were accepted as verified; `"garbage"` gave `ok:false`, not counted | 150 |
| P13 | `"two two eight eight"` for `phone_last4` was counted wrong | 151 |
| P14 | Unknown field: `"field must be date_of_birth or phone_last4"` | 152 |
| P15 | One re-verify of a verified field returned no `all_verified` key | 153 |
| P16 | `get_account` before verification gives `{ok:false, error:"identity not verified"}`, logged in the ledger | 154 |
| P17 | `get_account` returns `{ok, products:[...]}` with ids `p1..p3` and the fields described in §3.2 | 155 |
| P18 | `create_promise` returns `{ok, promise_id:"pr1"}`; string `"220"` accepted; `99999` accepted; errors `"date must be YYYY-MM-DD"`, `"unknown product_id"`, `"this product already has a promise"` | 156 |
| P19 | `add_note` and `transfer_to_agent` enforce their enums: `"unknown reason"`, `"unknown queue"` | 157 |
| P20 | `schedule_callback` with `"11am"` gives `"date must be YYYY-MM-DD and time HH:MM"` | 158 |
| P21 | `close_call`: `"no_contact"` gives `"unknown outcome"`; outcome/reason consistency is checked and the allowed reasons are named; after a close every tool returns `"the call is already closed"` | 159 |
| P22 | The bank accepts holiday dates, dates past the deadline and "any amount". "Any amount" is overstated: only 99999 and `"220"` were tried. | 161 |
| P23 | Chat with a made-up `customer_id` gets 404 `"unknown customer_id"` | 240 |
| P24 | Each probe or test uses up a single-use session; ledgers are visible only under the key that created them | 303–305 |

---

## 12. Corrections to earlier notes and summaries (the source wins)

### 12.1 Corrections to `knowledge/notes/openapi.md`

The notes were checked line by line against `openapi.json`. Their content is correct. Some line numbers are off by one:

| Note claim | Source says |
|---|---|
| 200 descriptions at "51, 112, 208, 274, 330, 385, 447" | The description lines are 51, 112, 208, **275, 331, 386, 448**. Lines 274, 330, 385 and 447 are the `"200": {` lines. |
| `ok`/`error` properties at "280–285, 336–341, 391–396, 453–458" | They are at **281–286, 337–342, 392–397, 454–459**. The other three tools (57–62, 118–123, 214–219) are right. |
| Request-body blocks at "19–23, 93–97, ..." | Correct as ranges of `required`..`type`. The `requestBody` key itself is one line earlier (18, 92, 175, 237, 301, 357, 412). |

### 12.2 Corrections to the earlier research summaries

The notes made eight corrections (C1 to C8). I re-checked each one, and each holds.

| # | Earlier claim | Verdict and correct statement |
|---|---|---|
| C1 | `read-rules-and-cases.md:185`: "Every POST returns `{ok, error, ...}`." | **Overstated.** No response schema has `required`, and a 500 has no body schema (§2.3). The probes saw a result with no `error` key and another with no `all_verified` key [PROBED-earlier]. |
| C2 | `read-api-and-testing.md:144`: business errors are 200 `ok:false`, "the only exceptions" being 404 and 401. | **Incomplete.** The file documents a 500 on every tool (L84 and repeats), which the probes could not see. The 401 belongs only to the practice routes, since tool calls need no key (L6). |
| C3 | `read-rules-and-cases.md:70`: "An unreadable answer comes back ok=false and is not counted." | **Too broad.** The sentence in L37 is about `date_of_birth` only. A spoken phone answer was counted wrong [PROBED-earlier]. |
| C4 | `read-api-and-testing.md:150` frames the acceptance of "14 March 1988" as contradicting the openapi. | **No contradiction.** Only *unreadable* values are rejected (L37; `brief-a.md:40`). Still send ISO. |
| C5 | `read-api-and-testing.md:161`: the bank accepts "any amount". | **Partly overstated.** Holiday and deadline dates are stated (L6), as is "below the minimum" (`hackathon-page.md §Evaluation`). Only 99999 and `"220"` were tried; zero, negative and non-numeric amounts are untested. The bank does enforce the identity gate, one promise per product, nothing after close, enums and the outcome/reason pairing. |
| C6 | `read-rules-and-cases.md:197`: "Product ids are `p1..pN` in `get_account` order" as an openapi fact. | **Not in the file.** L129–131 is a plain string. The id form comes from `README.md:102` and the probes; the order is inferred from the public cases. Copy ids from the response. |
| C7 | `read-rules-and-cases.md:27`: "Tool `config.maxRetries` must be 0." | **A recommendation, not a rule.** No source requires it. `tools-and-code.md:365` reports 0 on write tools in a working builder. |
| C8 | `read-api-and-testing.md:246`: "It costs one `curl` to check the openapi `servers` URL and enums at build time." | **Wrong method, and against the rules.** The hidden tool API arrives as a file (`hackathon-page.md §Submit`, `§FAQ`). Read `servers[0].url` and the enums from that file. Calling the bank to inspect it would be probing (`hackathon-page.md §Rules`). |

**Prior claims re-checked and found correct**
- Server URL, no auth, and `customer_id` as the secret (L6, L10, L13).
- 500 semantics (L84).
- Every request field and enum (§3).
- `reason` is free text and conditionally required (L433–441).
- `api_call` "success" does not mean `ok:true` (L51 + `tools-and-code.md:250–276`).
- `FREYA_BANK_HOST` affects only the scripts (`score.py:7`).
- A `get_account` before verification fails the case even after a correct retry (`score.py:31–32`).

---

## 13. Open questions

Each answer, if found, must come from normal kit usage: `run_cases.py`, ledger reads of our own practice sessions, or `get_call` events. Probing is not allowed (`hackathon-page.md §Rules`).

| # | Unknown | Why it matters | Where the answer would show up |
|---|---|---|---|
| U1 | How a 500 looks inside Freya: the body, the envelope `status`, `data`, `status_code`; whether `<tool>_failure_count` rises; whether `maxRetries` re-sends | Every failure route depends on it | The `function_call_complete` events and the variable table of a PUB-10 run (`get_call`) |
| U2 | Whether injected faults are 500s or 200 `ok:false`, and with which error string | Hidden cases will likely inject faults the same way, maybe on other tools | The PUB-10 ledger's `calls[]` and `failures` |
| U3 | "Every call is written to the ledger" (L6) against "Nothing was recorded" (L84) | Reading that reconciles them [INFERRED]: `calls[]` logs every call, but no business record is made on a 500. Also unknown: whether calls after `close_call` are logged, which would break `score.py:29`. | The PUB-10 ledger: the failed attempt should be in `calls[]` but not in `promises` |
| U4 | What the third wrong answer returns, and what any later call returns | The not-verified route | The PUB-03 ledger's `calls[].result` |
| U5 | `day_month_swapped` details: is the swapped answer counted, are `verified`/`ok` set, does it fire twice, and what does the ledger's `hinted` mean | The identity route | A custom-script case reusing PUB-07 (DOB `1975-12-05`) |
| U6 | Whether the "unreadable, not counted" rule applies to `phone_last4`; 3-digit, 5-digit and spaced answers | Wasted attempts | PUB-12 runs with `--style pieces` / `in_words` |
| U7 | Which response keys are always present | Route robustness | The key sets of `calls[].result` in any ledger |
| U8 | What the bank does with `reason` sent alongside `promise`/`paid` (`""`, `"none"`) | The scorer needs `null` | Until known, leave the key out (`base-agent.json:395`) |
| U9 | Whether `add_note` is gated on verification | Low; the agent never notes before `get_account` | Any ledger |
| U10 | How strict format checks are: `2026-02-30`, `"9:30"`, `"24:00"`, `"11:00:00"`, more than two decimals, zero or negative amounts, past dates | Robustness only, because the agent should always send canonical values | `args` and `result` in ledgers from `--style in_words` / `corrects` runs |
| U11 | Timeouts and idempotency: a timed-out `create_promise` that was in fact recorded | A retry would get "already has a promise"; treat that as "recorded" after a timeout [INFERRED] | Cannot be triggered on demand |
| U12 | How far "does not enforce the brief" goes: notes on promised products, duplicate notes, callbacks outside the window | Treat the bank as a recorder and enforce every brief rule in the agent [INFERRED] | Any ledger |
| U13 | Whether the hidden bank also checks the outcome/reason pairing | Cannot be tested without probing | Design `reason` from the brief, with a pre-hook that adds or removes it |
| U14 | Whether an `ok:false` (as opposed to a 500) counts as a "fail" for the brief's two-attempt rule | The retry route | Settled by U2 |
| U15 | The hidden files' host and paths | Whether practice customers can test a hidden agent | Only from the supplied file at build time |
| U16 | Whether listing `customer_id` in a Freya tool's `body.required` changes what the model sees | Tool generation | A dry run plus a `function_call_start` event |
| U17 | Product id format and order on a hidden bank | Id handling | Always copy from the response |
| U18 | How the dashboard test customer gets its `customer_id` (`hackathon-page.md §FAQ`) | Dashboard testing only | Not stated |

---

## Traps to remember

1. **Read `servers[0].url` from the supplied tool API file and bake it into every tool.** The final passes `{tool_api_path}` separately, for example `briefs/hidden-1.openapi.json` (`hackathon-page.md §Submit`). The example skill hard-codes `tools/openapi.json` (`SKILL.md:12, 18`), and a call to any other service fails the case (`hackathon-page.md §Rules`).
2. **An HTTP 200 is not a success.** Test `data.ok` on every tool. Freya treats `ok:false` as a transport success (L51; `tools-and-code.md:250–276`).
3. **Booleans arrive as strings.** Test both `"true"` and `"True"`, and tolerate a missing `all_verified` (`tools-and-code.md:286`; `read-api-and-testing.md:153`).
4. **Never call `get_account` (or `create_promise`) before the bank says identity is fully verified.** A single `"identity not verified"` anywhere in `calls[]` fails the case, even if a later retry succeeds (`score.py:31–32`).
5. **On a not-reached case (third party, wrong number, deceased, unclear), never call `verify_identity` or `get_account`** (`score.py:33`).
6. **`close_call` must be the last call, and only one.** After it, everything returns "the call is already closed" (L411; `score.py:29`; P21).
7. **Leave `reason` out (so it is null) for `promise` and `paid`.** An empty string is sent as `""` and fails the exact match (`score.py:19–20`; `tools-and-code.md:115`; `base-agent.json:395`). For every other outcome, `reason` is required even though the schema does not list it (L435–441).
8. **The transfer queue `general` closes with reason `human`, not `general`** (`brief-a.md:99`).
9. **Send dates as `YYYY-MM-DD` and times as zero-padded 24-hour `HH:MM`.** Callbacks and promise dates are compared as exact strings (`score.py:21–26`).
10. **Answers are strings, and leading zeros matter:** phone `"0358"`, card `"0377"` (`public-test-set.json:63, 112`).
11. **Normalise a phone answer to exactly four digits before calling.** Only an unreadable *date* is "not counted"; a spoken-digit phone answer used up an attempt (L37; P13).
12. **Copy `product_id` from the `get_account` response; never build it.** A made-up id gets `unknown product_id` (`README.md:102`).
13. **One promise per product, at most two attempts in total.** The 500 text says "may be repeated" without a limit, but the brief caps attempts at two (L174; `brief-a.md:91`). Use `maxRetries: 0` on write tools so the platform does not retry behind the agent's back (`tools-and-code.md:365`).
14. **A timeout is not a 500.** A recorded promise may come back as `"this product already has a promise"` on the retry (U11).
15. **The bank is a recorder, not a policeman.** It accepts holiday dates, dates past the deadline, amounts below the floor and out-of-window callbacks. Every brief rule must be enforced by the agent (L6; `hackathon-page.md §Evaluation`).
16. **The practice set never exercises** `general`/`support` transfers, most note reasons, `declined`, most `not_reached` reasons, `service_error`, or the `hint` (§8). Green practice runs say nothing about those routes.
17. **The hidden file can change every field, enum, description and summary, but not the seven tool names** (`README.md:72`). Generate tools from the file and join enums to the brief's tables. Never hard-code values from Brief A or B, which is also forbidden for hidden briefs (`README.md:73`).
18. **Do not probe the bank or call it to inspect a hidden file.** Use only normal kit usage (`hackathon-page.md §Rules`). Practice sessions are single-use and serve PUB-01..13 only; hidden briefs have none (P24; `hackathon-page.md §FAQ`).
19. **The docs' example field `attempts_left` belongs to a made-up API.** The bank's field is `wrong_answers_left` (`tools-and-code.md:255` vs `openapi.json:66`).
20. **Promised amounts are the first tie-break.** Recording the right amount, not just a valid one, matters (`README.md:90`).
