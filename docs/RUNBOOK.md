# Final runbook: one Turkish case, one agent, our own mock (2026-10-11, 17:00 to 20:00 UTC = 13:00 to 16:00 EDT)

All times are UTC (EDT = UTC − 4). Work from the repo root; every block works in bash and zsh.
The case: Freya Bank's credit card statement-debt line, in Turkish. It arrives as a zip holding a folder of Markdown,
Word, PDF and Excel files: BRIEF.md, README.md, the analysis, a flow drawing, announcements, the SERVICE CONTRACT,
TEST CUSTOMERS, Q&A and 6 example conversations. We deploy OUR mock of the bank's services on Cloudflare Workers and
keep it running until the results are out. The agent's tools call the mock: a wrong or unreachable mock fails calls.
Run command (the form's `run_command`): `python3 builder/build.py {case_folder} {mock_url}`.
Hard rules: after 17:00 nothing from the case goes into `builder/`, `runtime/` or `harness/`. Generic bug fixes are
allowed (a crash on a file type is a generic fix; the bank's field names or announcements are not). The mock
(`mock/*.json`) is ours and case-specific. Never edit the agent by hand. No simulations.

| Time  | Step |
|-------|------|
| 16:30 (12:30 EDT) | Pre-flight, including the Cloudflare login and a test deploy of the sample mock (section 1) |
| 17:00 (13:00 EDT) | Unzip the case and read BRIEF.md + README.md (section 2) |
| 17:10 (13:10 EDT) | Contract → mock config → real deploy → mock smoke (section 3) |
| 17:25 (13:25 EDT) | Build 1 with tee (section 4); trace + Spec review (section 5) |
| 17:45 (13:45 EDT) | Live chat on 2–3 example conversations against the mock (section 6) |
| 18:00–19:00 (14:00–15:00 EDT) | Generic fixes only, then rebuild (section 7). **Last builder fix commit 19:00** |
| 19:10 (15:10 EDT) | **Last rebuild start** (a build takes about 2.5 min) |
| 19:20 (15:20 EDT) | Reset the mock ledger, `tools/submit.py final`, commit, push (section 8) |
| 19:40 (15:40 EDT) | **submission.json sent.** The hard deadline is 20:00. Leave the mock deployed. |

## 1. Pre-flight (16:30)

If using a repository for submission, set `SUBMISSION_REPO` to its URL and `SUBMISSION_BRANCH` to its branch.
These values are deployment-specific; this source distribution does not include repository metadata.

```bash
# Run from the project root
git fetch origin && git status --short && git pull --ff-only origin "$SUBMISSION_BRANCH"
python3 -m venv .venv 2>/dev/null; . .venv/bin/activate
python3 -m pip install -q -r requirements.txt
source kit/env.sh                       # FREYA_API_KEY (never echo it)
python3 -c "
import sys; sys.path.insert(0, 'kit'); import freya
r = freya.api('GET', '/api/v2/api-keys/check')
print({k: r.get(k) for k in ('valid', 'workspaceId', 'expiresAt', 'rateLimit')})"
claude --version >/dev/null && echo "claude CLI present"
which pdftotext textutil node npx                            # PDF / old Word readers; node for the mock
npx --yes wrangler@4 whoami                                  # logged in? otherwise: npx --yes wrangler@4 login
tools/quality.sh                                             # want QUALITY OK (pytest green is enough if Sonar is down)
git tag -f pre-final && git rev-parse --short pre-final      # leak-check baseline
mkdir -p briefs traces submission
```
Deploy the sample mock once now, so the Cloudflare side (account, KV namespace, workers.dev subdomain) is proven
before 17:00. `deploy.sh` creates the KV namespace `LEDGER` once and writes its id into `mock/wrangler.toml`:
```bash
tools/mockgen/deploy.sh --name freya-bank-mock               # prints MOCK_URL=https://freya-bank-mock.<sub>.workers.dev
python3 tools/mockgen/smoke.py "$MOCK_URL" --all             # want OK ... 0 failed check(s)
```
The Cloudflare account is on Workers Paid (done 11 Oct), so the free plan's limit of about 1,000 KV writes a day does not apply. Otherwise the mock falls back to isolate memory, which is not
shared between instances (`/health` shows `kv_errors`).

## 2. Unzip and read (17:00)

`briefs/` is gitignored, so the case never lands in a commit. Unzip it with the builder's own safe extractor,
which repairs Turkish file names stored in the old zip encoding and drops `__MACOSX`:
```bash
ZIP=~/Downloads/<the case>.zip
CASE=$(python3 -c "import sys; sys.path.insert(0,'.'); from builder import ingest; print(ingest.extract_zip(sys.argv[1], 'briefs/final'))" "$ZIP")
echo "$CASE"; ls -la "$CASE"
python3 -c "import sys,json; sys.path.insert(0,'.'); from builder import ingest
c = ingest.load_case(sys.argv[1]); print('\n'.join(ingest.manifest_lines(c)))" "$CASE"
```
The manifest gives each file its kind (brief, readme, service_contract, test_customers, example_conversation, …), its
reader and its status. Check: every file is `read`; the contract and the test customers are classified as such; no
`WARN` you cannot explain. If a file type crashes or reads empty, that is a generic bug fix (section 7).
Read BRIEF.md and README.md yourself while the mock is being made.

## 3. Mock: contract → config → real deploy → smoke (17:10)

Derive the contract ONCE and serve it from the mock. The build then reads the same file from `<mock>/openapi.json`
(source `mock`), so the agent and the mock can never disagree. Running the LLM derivation twice can differ.
```bash
python3 -m builder.contract "$CASE" https://placeholder.invalid --out briefs/final/derived.openapi.json
#   prints the role map: verify / account / promise / note / callback / transfer / close -> operation.
#   An OpenAPI file in the case folder is used as is (no LLM). Check every role is bound to the right path,
#   and look at every `absent` stub, `synthetic` field and extra operation.
python3 tools/mockgen/make_config.py --openapi briefs/final/derived.openapi.json \
    --customers "$CASE" --contract "$CASE" --out mock
#   read the printed table: identity keys, customer count, UNMAPPED columns, error codes, close table, WARN lines.
#   Repair with --roles r.json / --columns c.json / --reasonless A,B / --reasons r.json / --max-wrong N.
#   CHECK the products' id column: if make_config lists it under UNMAPPED (e.g. kart_id vs the contract's urun_no),
#   map it with --columns c.json, or every product gets a made-up id p1/p2 and the agent's promise calls won't match.
node tools/mockgen/harness.mjs serve --dir mock --port 8787 --kv &      # local first
python3 tools/mockgen/smoke.py http://localhost:8787 --all && kill %1
tools/mockgen/deploy.sh                                  # real deploy (same name as at 16:30) -> MOCK_URL=...
export MOCK_URL=https://freya-bank-mock.<sub>.workers.dev
python3 tools/mockgen/smoke.py "$MOCK_URL" --all          # want OK, 0 failed
curl -s "$MOCK_URL/health"; curl -s "$MOCK_URL/openapi.json" | head -c 400
```
Mock checks by hand (copy one customer's answers from the test-customers file): a wrong identity answer counts; the
account read is refused before verification; one promise per product; close is single use; outcome/reason pairs
follow the contract's close table. `tools/mockgen/smoke.py` covers the happy path for every customer.
Commit `mock/` (the mock is ours; that is allowed): `git add mock/ && git commit -m "Final mock data"`.

## 4. Build (17:25)

```bash
set -o pipefail
python3 builder/build.py "$CASE" "$MOCK_URL" 2>&1 | tee traces/final.log; echo "exit=$?"
```
This is exactly the form's run command, with no extra flags. Each run creates a fresh workflow named after the case
folder. Exit 2 within a second with `preflight:` means a missing key, package or Claude login.

## 5. Read the trace and the Spec

```bash
grep -E " (START|INPUT|CATALOG|MODEL|SPEC|VALIDATE|WARN|ERROR|LINT|COMPILE|TWIN|FREYA|END) " traces/final.log | less
RD=$(sed -n 's/.* START .*run_dir=\(.*\) model_default=.*/\1/p' traces/final.log | head -1)
python3 tools/gonogo.py "$RD" "$RD/openapi.json"
```
- `INPUT … role=mock` reachable; `CATALOG service contract bound | source=mock …/openapi.json absent=[]`.
- `MODEL extract F1..F7 ok=True`; `VALIDATE errors=0`; `SPEC valid`.
- `COMPILE … ctl code N bytes`: up to about 87 KB is fine. The compiler bakes a turn budget into the Spec, and lint
  prints it as `code_turns … at about customer turn T`. T ≥ 20 is fine (the example conversations have ≤ 10 customer
  turns); a smaller T or a lint ERROR is NO-GO.
- `TWIN PASS GEN-*` 4/4; `FREYA built on Freya`; `smoke chat turn ok | reply=<Turkish opening>`.
  A smoke `warn` with HTTP 0 / 504 is the platform (seen 15:30–15:50 on every agent), not the build.
Spec review against BRIEF.md (`jq` on `$RD/spec.json`):
```bash
jq '{bank, call_variables, addressing, opening}' "$RD/spec.json"          # language "tr", Turkish lines, <ad> <hitap>
jq '.identity.questions[] | {field_value, kind, wire_format, pattern}' "$RD/spec.json"
jq '{calendar, bands, dated, promise_date, amounts}' "$RD/spec.json"     # holidays, deadlines, dated rule changes
jq '.situations | map_values({outcome, reason, queue, note_reason})' "$RD/spec.json"
jq '.outcomes.reasonless_outcomes, .banned' "$RD/spec.json"
jq '.pkind' "$RD/wiring.json"   # a promise-type enum (full/minimum/partial) when the contract has one, else null
```
Every outcome, reason, queue and note value must be a contract enum, and every required sentence must be word for
word. A date-dependent rule from the announcements must show in `dated` (or `meta.residual_rules`).

## 6. Live chat against the mock (17:45, sequential, 2–3 conversations)

Write a small cases file from the example conversations, outside the repo's tracked files (`briefs/` is ignored):
`briefs/final/cases.json` = `[{"id": "EX-1", "mock_customer": "<id>", "variables": {<call variables incl. now>},
"customer_lines": ["...", "..."], "expected_ledger": [{"op": "<operationId>", "body": {...}}]}]`.
```bash
WID=$(sed -n 's/.*built on Freya | workflow_id=\([^ ]*\).*/\1/p' traces/final.log | tail -1)
python3 -m harness.chat_e2e --workflow-id "$WID" --case EX-1,EX-2 --customer script \
    --mock "$MOCK_URL" --cases-file briefs/final/cases.json --spec "$RD/spec.json"
curl -s "$MOCK_URL/ledger/<customer id>" | python3 -m json.tool | head -80
```
The runner resets the customer on the mock, opens with "Alo?" and then says the case's `customer_lines`. It scores
the mock ledger against `expected_ledger`: every expected call is present with its values, nothing is recorded
twice, and failed calls do not count. Check by eye that the agent speaks Turkish, verifies through OUR mock, records
the promise once and closes.

## 7. Fix path (until 19:00)

Fix the cause generically: no name, number, date, phrase, enum value or field name from the case. Add a test with
made-up data. Then:
```bash
python3 -m pytest tests -q
python3 tools/leak_check.py --hidden "$CASE" --since pre-final --worktree     # every HIT reviewed by hand
git commit -am "Generic fix: ..." && git push origin "$SUBMISSION_BRANCH"
python3 builder/build.py "$CASE" "$MOCK_URL" 2>&1 | tee traces/final.log; echo "exit=$?"   # move the old log aside first
```
A mock bug (wrong role, missing column, close table) is fixed in `mock/` with make_config's flags and a redeploy. It
needs no builder change and no rebuild, unless the contract (`openapi.json`) changed.

## 8. Package, commit, send (19:20)

```bash
curl -s -X POST "$MOCK_URL/reset"                    # graders start from clean ledgers
python3 tools/submit.py final --members "Full Name 1, Full Name 2, Full Name 3"
```
`submit.py final` reads the run named by `traces/final.log` and checks that the build ended with exit 0 and was
deployed, with one workflow id that the export, `ids.json` and SUMMARY all agree on. It also checks that the newest
published version is the run's and is unchanged since the export (two read-only GETs). Then it scans the export, log
and `trace.jsonl` for keys, and checks `mock_url` (taken from the log's START line): https, not a tunnel or
placeholder, `/health` ok. It writes `submission/final.workflow.json`, `traces/final.trace.jsonl` and
`submission.json`:
```json
{"team": "Solarity-AI", "members": ["..."], "repo": "<repository-url>",
 "branch": "<branch>", "commit": "<HEAD>", "run_command": "python3 builder/build.py {case_folder} {mock_url}",
 "workflow": "submission/final.workflow.json", "trace": "traces/final.log", "mock_url": "https://...workers.dev"}
```
```bash
git add submission/final.workflow.json traces/final.log traces/final.trace.jsonl mock/ submission.json
git status --short                      # no briefs/, no env.sh, no state/
git commit -m "Final submission: agent, build trace, mock" && git push origin "$SUBMISSION_BRANCH"
python3 tools/submit.py final           # refreshes submission.json's commit to the pushed HEAD (members are kept)
git commit -am "submission.json: pushed commit" && git push origin "$SUBMISSION_BRANCH"
```
Send `submission.json` as the kit email says, before 20:00. Afterwards: do not touch the agent, keep the mock
deployed, do not reset it again.

## Never
- edit the agent by hand, or change its model or `agent_config`;
- write anything from the case into `builder/`, `runtime/`, `harness/` or the prompts;
- print or commit keys (`env.sh`, `state/`);
- submit a `trycloudflare.com` mock (`deploy.sh --temporary` dies with the process; rehearsal only).

---

# Appendix: the earlier two-brief form (brief + tool API)

The old command `python3 builder/build.py <brief.md> <openapi.json>` still works, and so does `tools/submit.py
hidden-N`. The original Sunday runbook for that form follows unchanged.

# Sunday runbook: hidden briefs (16:30 to 20:00 UTC, 2026-10-11)

All times are UTC. Work from the repo root. Each command block works in bash and zsh.
Hard rules: one Freya key, no probing, no simulations needed. After 17:00, nothing from a hidden brief may go into
`builder/`, `runtime/` or `harness/`; generic bug fixes are allowed. Never edit an agent after its run.

| Time  | Step |
|-------|------|
| 16:30 | Pre-flight (section 1) |
| 17:00 | Save the hidden files, start both builds (sections 2 and 3) |
| 17:10 | Read the traces and run the go/no-go checks (sections 4 and 5) |
| 17:30 | Optional second run and Spec diff (section 6) |
| 19:00 | **Last builder fix commit** (section 7) |
| 19:10 | **Last rebuild start** (a build takes about 2 min) |
| 19:20 | `tools/submit.py` for both briefs, commit, push (sections 8 and 9) |
| 19:40 | **Form sent** (section 9). The hard deadline is 20:00. |

## 1. Pre-flight (16:30)

If using a repository for submission, set `SUBMISSION_REPO` to its URL and `SUBMISSION_BRANCH` to its branch.
These values are deployment-specific; this source distribution does not include repository metadata.

```bash
# Run from the project root
git fetch origin && git status --short && git pull --ff-only origin "$SUBMISSION_BRANCH"       # clean tree, latest source
python3 -m venv .venv 2>/dev/null; . .venv/bin/activate                      # python3 is now the venv's
python3 -m pip install -q -r requirements.txt
source kit/env.sh                                       # FREYA_API_KEY (never echo it)
python3 -c "
import sys; sys.path.insert(0, 'kit'); import freya
r = freya.api('GET', '/api/v2/api-keys/check')
print({k: r.get(k) for k in ('valid', 'workspaceId', 'expiresAt', 'rateLimit')})"
# want: valid True, expiresAt in the future
claude --version >/dev/null && echo "claude CLI present"                    # the SDK uses this login
tools/quality.sh                                                              # want: QUALITY OK
git tag -f pre-hidden && git rev-parse --short pre-hidden                     # the leak-check baseline
mkdir -p briefs traces submission
```
If `quality.sh` fails only on SonarQube being down, `python3 -m pytest tests -q` green is enough to go on; note it.
A key check that says `valid: False` or an expired key: stop and fix the key before 17:00.

## 2. Save the hidden files (17:00)

Save each brief and its tool API exactly as received, under these names (the extension follows the file's format):
```
briefs/hidden-1.md   briefs/hidden-1.openapi.json      (or .yaml)
briefs/hidden-2.md   briefs/hidden-2.openapi.json
```
A brief that comes as several files: put them in a folder `briefs/hidden-1/` and pass the folder instead of the
`.md`. Do not open the builder code while reading the briefs. Do not commit `briefs/` (it is gitignored); the
organisers bring their own copies.

## 3. Build (17:00, both briefs, one after the other)

```bash
set -o pipefail
python3 builder/build.py briefs/hidden-1.md briefs/hidden-1.openapi.json 2>&1 | tee traces/hidden-1.log; echo "exit=$?"
python3 builder/build.py briefs/hidden-2.md briefs/hidden-2.openapi.json 2>&1 | tee traces/hidden-2.log; echo "exit=$?"
```
Exactly the form's `run_command`, no extra flags. Each run creates a fresh workflow named
`hidden-N-<sha8>-<UTC stamp>`, so the two briefs and any re-run never touch each other's agent.
Exit 2 within a second with `preflight:` in the ERROR line means a missing key, package or Claude login: fix and rerun.
Rehearsals before 17:00 use the same command with `export BUILDER_SLOT_PREFIX=fresh-` (workflows are then named
`fresh-hidden-N-...`). Run `unset BUILDER_SLOT_PREFIX` before the real builds: the trace's `START ... slot=` must read
`hidden-N-...`.

## 4. Read the trace

`grep -E " (START|MODEL|SPEC|DECISION|WARN|ERROR|LINT|TWIN|FREYA|END) " traces/hidden-1.log`
- `START ... preflight ok`: Python, Freya URL, where the Claude login came from (never a key).
- `MODEL`: seven `extract F1..F7` calls, all `ok=True`. An `ok=False` attempt followed by an `ok=True` retry is fine.
  `EXTRACT targeted re-extraction` means validation errors were repaired: read the `VALIDATE error:` lines before it.
- `SPEC ... valid` with the intent/situation/band counts. `WARN invalid Spec ... degraded` = parts were dropped to
  reach a valid Spec: read `decisions.md` in the run folder.
- `DECISION`: interpretation choices and defaults (e.g. a reason filled from its situation). Skim for anything that
  contradicts the brief.
- `LINT`: must say `0 errors`; warnings are advisory.
- `TWIN PASS/FAIL GEN-*`: the local twin's generated scenarios.
- `FREYA ... built on Freya`: workflow id, agent id, version, nodes, tools. `smoke chat turn ok | reply=...`: the
  agent's first line on a live chat.
- `END ... exit 0`, then the SUMMARY block.

## 5. Go / no-go (per brief)

```bash
python3 tools/gonogo.py --log traces/hidden-1.log briefs/hidden-1.openapi.json
python3 tools/gonogo.py --log traces/hidden-2.log briefs/hidden-2.openapi.json
```
GO needs all of: exit 0 and deployed; lint 0 errors; twin n/n with n > 0; smoke `ok`; every situation outcome,
close reason, queue and note reason inside the enum the builder bound, and every bound enum literally present in the
hidden OpenAPI. Then judge the printed notes by eye:
- the opening line is sane for this bank (name, purpose, recording notice as the brief asks);
- enum values "no situation uses": fine for rare outcomes, but an outcome the brief clearly needs is a NO-GO;
- the build time (expect about 80-100 s).

Smoke `warn` caused by the platform only (HTTP 0 timeout, 5xx): rerun the build once (section 6). If it fails the
same way again, keep the run whose other checks pass; the trace shows the failed smoke honestly.

## 6. Optional second run and Spec diff (17:30)

A second run makes a second, separate agent. Keep every log (the rules say keep everything the builder prints):
```bash
python3 builder/build.py briefs/hidden-1.md briefs/hidden-1.openapi.json 2>&1 | tee traces/hidden-1.try2.log; echo "exit=$?"
python3 tools/gonogo.py --log traces/hidden-1.try2.log briefs/hidden-1.openapi.json
A=$(sed -n 's/.* START .*run_dir=\(.*\) model_default=.*/\1/p' traces/hidden-1.log | head -1)
B=$(sed -n 's/.* START .*run_dir=\(.*\) model_default=.*/\1/p' traces/hidden-1.try2.log | head -1)
diff <(jq -S 'del(.meta)' "$A/spec.json") <(jq -S 'del(.meta)' "$B/spec.json") | head -80
```
Differences show where the brief is ambiguous to the extractor. Pick the run whose Spec matches the brief better.
To submit the second run, rename the logs so that `traces/hidden-1.log` is the chosen run's log:
`mv traces/hidden-1.log traces/hidden-1.try1.log && mv traces/hidden-1.try2.log traces/hidden-1.log`.

## 7. Fix path (until 19:00 at the latest)

Only when a run is NO-GO because of a builder bug.
1. The fix must be generic: no name, number, date, phrase, enum value or field name from a hidden file. Fix the
   cause (a parser, a default, a lint rule), add a test with made-up data, never a hidden-brief fixture.
2. `python3 -m pytest tests -q` (and `tools/quality.sh` if time allows), then commit.
3. Leak check, must be clean (exit 0). Review every HIT by hand; a generic word can collide:
   ```bash
   python3 tools/leak_check.py --hidden briefs/hidden-1.md briefs/hidden-1.openapi.json \
       briefs/hidden-2.md briefs/hidden-2.openapi.json --since pre-hidden
   ```
   Before committing, add `--worktree` to include uncommitted and untracked files.
4. `git push origin "$SUBMISSION_BRANCH"`.
5. Rebuild **both** briefs from the fix commit (section 3), even the one that was GO: every submitted agent and
   trace must come from the commit in the form. Move the old logs aside first (`traces/hidden-N.pre-fix.log`).
6. Last fix commit 19:00, last rebuild start 19:10. After that, submit what passed.

## 8. Package (19:20)

```bash
python3 tools/submit.py hidden-1
python3 tools/submit.py hidden-2
```
Each one reads the run named by `traces/hidden-N.log`, checks that the export's workflow id is the run's FREYA
workflow id, that the newest published version is the run's and the workflow is unchanged since the export (two
read-only GETs), scans the log, `trace.jsonl` and the export for `fak_`, `sk-ant-` and every key value in the
environment, then writes `submission/hidden-N.workflow.json` and `traces/hidden-N.trace.jsonl`. Any FAIL: nothing is
copied; fix the cause (never hand-edit an export or a trace).
WARN lines to act on: uncommitted builder changes, a run built from uncommitted or different builder code (rebuild),
HEAD not pushed (push).

## 9. Commit, push, form (by 19:40)

```bash
git add submission/ traces/
git status --short                    # only submission/ and traces/ files; no briefs/, no env.sh, no state/
git commit -m "Hidden-brief submission: agents and build traces"
git push origin "$SUBMISSION_BRANCH"
python3 tools/submit.py --form        # form JSON with the pushed HEAD; WARN if HEAD is not on the configured remote branch
```
Send the printed JSON with the form (address in the kit email) before 20:00. It has the shape:
```json
{"team": "Solarity-AI", "repo": "<repository-url>", "branch": "<branch>",
 "commit": "<HEAD>", "run_command": "python3 builder/build.py {brief_path} {tool_api_path}",
 "workflows": {"hidden-1": "submission/hidden-1.workflow.json", "hidden-2": "submission/hidden-2.workflow.json"},
 "traces": {"hidden-1": "traces/hidden-1.log", "hidden-2": "traces/hidden-2.log"}}
```
After sending: do not touch either agent, and do not push builder changes to the submitted branch.
