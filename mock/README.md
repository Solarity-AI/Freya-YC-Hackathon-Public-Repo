# Bank mock (Cloudflare Worker)

The final's phone agent calls OUR mock of the bank's services. The Worker is generic (`src/engine.js`); everything
case-specific is data written by `tools/mockgen/make_config.py`:

| file | what |
|---|---|
| `config.json` | operations (method + path -> role verify/account/promise/note/callback/transfer/close), field roles, request rules (required, enum, type, pattern, wire date/time format), response leaf names, HTTP status per refusal kind, close reason rules, session rules |
| `customers.json` | `[{customer_id, identity:{key: answer}, products:[...], account:{...}, variables:{...}, faults:[...]}]` |
| `openapi.json` | the contract, served at `/openapi.json` with `servers[0].url` = this mock |

The sample data in this folder is the kit OpenAPI + the 13 PUB customers (a smoke fixture). Regenerate for the case.

## Generate (after the case arrives)

    # a prose contract (Word/PDF/Markdown): derive the OpenAPI the agent will call first (same as the build does)
    .venv/bin/python -m builder.contract <CaseFolder> https://placeholder --out /tmp/derived.openapi.json
    .venv/bin/python tools/mockgen/make_config.py --openapi <contract OpenAPI, derived OpenAPI or run dir> \
        --customers <case folder or the test-customers file> --contract <CaseFolder> --out mock \
        [--llm --docs <case folder>]

`--contract` reads the contract's tables: an error-code table (code + meaning -> `config.error_codes`, e.g. the
code for "identity not verified", "already has a promise", "invalid format"; a meaning that mentions a past date
makes the promise refuse dates before the customer's `now`) and the close table (outcome + reason ->
`reasons_by_outcome`; a dash = no reason). The derived OpenAPI's `x-freya-tool` / `x-freya-role` annotations win
over name guessing; `x-freya-absent` stubs and operations with no role answer ok (`stub`); `x-freya-synthetic`
fields are ignored, or stand in for the contract field of the same role (`aliases`).

Read the printed table: every role bound to the right path, identity keys, customer count, `UNMAPPED` columns,
`WARN` lines. Force a mapping with `--roles roles.json` ({role: path}), `--columns cols.json` ({column: target}),
`--reasonless a,b`, `--reasons reasons.json` ({outcome: [allowed reasons]}), `--max-wrong N`.

## Run locally

    node tools/mockgen/harness.mjs serve --dir mock --port 8787           # emulated DOs; or: cd mock && npx wrangler dev --local
    .venv/bin/python tools/mockgen/smoke.py http://localhost:8787 --all

## Deploy (keep it running until the results are out)

    npx wrangler login                     # once
    tools/mockgen/deploy.sh --name <worker-name>   # deploy (Durable Object ledger, Workers Paid), /health; prints MOCK_URL=...
    .venv/bin/python tools/mockgen/smoke.py <MOCK_URL> --all
    tools/mockgen/deploy.sh --temporary    # rehearsal only: wrangler dev --local behind a trycloudflare.com tunnel

## Routes

- the contract's operations (any `servers` base path such as `/v1` is accepted with or without the prefix; a path
  with `{param}` segments also answers at the literal path without them, parameters in the JSON body)
- `GET /health`, `GET /openapi.json`, `GET /customers` (ids + variables, no identity answers)
- `GET /ledger/<customer_id>[?session=<call key>]`: the current call (`verified`, `wrong`, `promises`, `notes`,
  `callbacks`, `transfers`, `outcome`, `reason`, `closed`, `failures`, `calls[]`) plus `history` of earlier calls
- `POST /reset/<customer_id>`, `POST /reset` (all); `POST /admin/fault/<customer_id>` `{op, fail_first_n, mode}`
  (`http500` or `ok_false`). Set the `ADMIN_TOKEN` secret to require header `x-admin-token` on these.

## Behaviour (same semantics as harness/mockbank.py)

- One ledger per customer per phone call. A new call starts when a verify arrives after `close`, 15 s after a
  close, or after 240 s idle (config `session`). Parallel calls on one customer need a call key
  (`session.key_headers` / `session.key_fields`).
- Identity: wrong answers count across fields; at `max_wrong` the check is over. An unreadable date or digits of the
  wrong length are refused and not counted; a day/month swap returns the contract's hint value, not counted.
- Errors: `{<ok leaf>: false | <fail status value>, <error leaf>: <the contract's code for the kind, else text>}`;
  HTTP statuses from the contract's documented response codes (400/409/... else 200); unknown customer 404 unless
  the contract's error table has a code for it. Messages are Turkish when the contract is (`lang`).
- Account read and promise are refused until every identity answer passed. One promise per product (per call when
  the promise has no product field). Close is single use; outcomes named "except ..." in the reason description
  take no reason (stored as null).
- The ledger lives in a SQLite-backed Durable Object (binding `LEDGER_DO`, class `Ledger` exported from
  src/worker.js), one instance per customer id (`idFromName`). The Worker forwards every request that touches a
  customer's ledger (tool calls, `/ledger/<id>`, `/reset/<id>`, `/admin/fault/<id>`; `/reset` fans out to every
  customer in customers.json) to that DO, which runs the same engine on its transactional `ctx.storage`: one writer
  per customer, so a verify is always visible to the next get_account. `/health` reports `storage: "durable_object"`.
  KV (binding `LEDGER`) is no longer used: it is eventually consistent (a write could be invisible for ~60 s). The
  engine still falls back to KV, then isolate memory, when no DO binding exists. Never answers 500 except an
  injected fault.
