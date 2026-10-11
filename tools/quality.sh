#!/usr/bin/env bash
# Quality gate: tests + coverage (>=95%), dead code (vulture), SonarQube scan + quality gate (dup, smells, bugs).
# Exits non-zero when ANY step fails: a failing test or coverage < 95%, any vulture finding, a failed scanner run,
# or a SonarQube quality gate other than OK. Every step still runs, so one report shows all failures.
# Needs a local SonarQube container "freya-sonar" (127.0.0.1:9000) and ../state/sonar.env (SONAR_TOKEN); never commit
# that file and never print the token (it reaches docker and curl through the environment / stdin, not argv).
set -euo pipefail
cd "$(dirname "$0")/.."

PY=.venv/bin/python
SONAR_URL="${SONAR_URL:-http://127.0.0.1:9000}"
PROJECT_KEY=freya-builder
COV_MIN=95
failed=()

work="$(mktemp -d "${TMPDIR:-/tmp}/freya-quality.XXXXXX")"
trap 'status=$?; rm -rf "$work"; exit "$status"' EXIT
# A private coverage data file, so a parallel pytest run in the same repo cannot clobber this measurement.
export COVERAGE_FILE="$work/coverage.data"

step() { printf '\n== %s\n' "$1"; }
fail() { failed+=("$1"); printf 'FAIL: %s\n' "$1"; }

# --------------------------------------------------------------------------------------------- 1. tests + coverage
step "pytest + coverage (>= ${COV_MIN}%)"
pytest_rc=0
"$PY" -m pytest tests/ -q -p no:cacheprovider --cov --cov-report=term --cov-fail-under="$COV_MIN" \
  >"$work/pytest.log" 2>&1 || pytest_rc=$?
tail -40 "$work/pytest.log"
[ "$pytest_rc" -eq 0 ] || fail "pytest/coverage (exit $pytest_rc)"

# coverage.xml for SonarQube with repo-relative paths (builder/__init__.py, not __init__.py). .coveragerc's
# `source = builder,runtime,harness` makes coverage.py write paths relative to each package, so the three
# __init__.py files collide and the scanner cannot resolve them; the XML report is written without `source`.
"$PY" - "$work/xml.rc" <<'PYCFG'
import configparser, sys
c = configparser.ConfigParser()
c.read(".coveragerc")
if not c.has_section("run"):
    c.add_section("run")
c.remove_option("run", "source")
c.set("run", "relative_files", "True")
with open(sys.argv[1], "w") as f:
    c.write(f)
PYCFG
xml_rc=0
"$PY" -m coverage xml --rcfile="$work/xml.rc" -q -o coverage.xml >"$work/xml.log" 2>&1 || xml_rc=$?
if [ "$xml_rc" -ne 0 ]; then
  cat "$work/xml.log"; fail "coverage.xml (exit $xml_rc)"
fi

# --------------------------------------------------------------------------------------------- 2. dead code
step "vulture (dead code)"
vulture_rc=0
"$PY" -m vulture builder runtime harness tools/vulture_whitelist.py --min-confidence 60 >"$work/vulture.log" 2>&1 \
  || vulture_rc=$?
cat "$work/vulture.log"
if [ "$vulture_rc" -ne 0 ] || [ -s "$work/vulture.log" ]; then
  fail "vulture: $(grep -c . "$work/vulture.log" || true) finding(s) (exit $vulture_rc)"
else
  echo "vulture: clean"
fi

# --------------------------------------------------------------------------------------------- 3. SonarQube
# curl reads its config (incl. the token) from stdin, so the token never shows up in `ps`.
sonar_api() { printf 'user = "%s:"\n' "$SONAR_TOKEN" | curl -sS -f --max-time 30 -K - "$SONAR_URL$1"; }

sonar_scan() {      # the scanner waits for the server-side quality gate (sonar.qualitygate.wait) and fails on it
  local scan_rc=0
  if [ "$(docker inspect -f '{{.State.Running}}' freya-sonar 2>/dev/null || true)" != "true" ]; then
    scan_rc=125; echo "container freya-sonar is not running"
  else
    docker network inspect freya-net >/dev/null 2>&1 || docker network create freya-net >/dev/null
    docker network connect freya-net freya-sonar 2>/dev/null || true      # already connected is fine
    docker run --rm --network freya-net -e SONAR_HOST_URL=http://freya-sonar:9000 -e SONAR_TOKEN \
      -v "$PWD:/usr/src" sonarsource/sonar-scanner-cli -Dsonar.qualitygate.wait=true >"$work/scan.log" 2>&1 \
      || scan_rc=$?
    local shown='ANALYSIS SUCCESSFUL|QUALITY GATE|EXECUTION (SUCCESS|FAILURE)|ERROR'
    shown="$shown|Cobertura|coverage report|Cannot resolve"
    grep -E "$shown" "$work/scan.log" || true
  fi
  if [ "$scan_rc" -ne 0 ]; then
    # a failed gate is already shown above; any other scanner failure gets the log tail
    if [ -s "$work/scan.log" ] && ! grep -q 'QUALITY GATE STATUS' "$work/scan.log"; then tail -30 "$work/scan.log"; fi
    fail "SonarQube scanner (exit $scan_rc)"
  fi
}

sonar_gate() {      # independent check of the gate the server holds now, plus a one-line summary of key measures
  local api_rc=0 gate_rc=0 metrics=coverage,duplicated_lines_density,bugs,vulnerabilities,code_smells
  sonar_api "/api/qualitygates/project_status?projectKey=$PROJECT_KEY" >"$work/gate.json" || api_rc=$?
  sonar_api "/api/measures/component?component=$PROJECT_KEY&metricKeys=$metrics" >"$work/measures.json" || api_rc=$?
  if [ "$api_rc" -ne 0 ]; then
    fail "SonarQube API unreachable (curl exit $api_rc)"
    return 0
  fi
  "$PY" - "$work/gate.json" "$work/measures.json" <<'PYGATE' || gate_rc=$?
import json, sys
gate = json.load(open(sys.argv[1]))["projectStatus"]
measures = {m["metric"]: m.get("value", "?") for m in json.load(open(sys.argv[2]))["component"]["measures"]}
order = ("coverage", "duplicated_lines_density", "bugs", "vulnerabilities", "code_smells")
print("sonar: gate=%s  " % gate["status"] + "  ".join("%s=%s" % (k, measures.get(k, "?")) for k in order))
for c in gate.get("conditions", []):
    if c.get("status") not in ("OK", "NONE"):
        print("  gate condition %s: %s (threshold %s %s)" % (c.get("metricKey"), c.get("actualValue"),
                                                              c.get("comparator"), c.get("errorThreshold")))
sys.exit(0 if gate["status"] == "OK" else 1)
PYGATE
  if [ "$gate_rc" -ne 0 ]; then fail "SonarQube quality gate is not OK"; fi
}

step "SonarQube scan + quality gate"
if [ -f ../state/sonar.env ]; then set -a; source ../state/sonar.env; set +a; fi
if [ -z "${SONAR_TOKEN:-}" ]; then
  fail "SONAR_TOKEN missing from ../state/sonar.env"
else
  sonar_scan
  sonar_gate
fi

# --------------------------------------------------------------------------------------------- summary
step "summary"
if [ "${#failed[@]}" -gt 0 ]; then
  printf 'QUALITY FAILED (%d): %s\n' "${#failed[@]}" "$(IFS=';'; echo "${failed[*]}")"
  exit 1
fi
echo "QUALITY OK: tests + coverage >= ${COV_MIN}%, vulture clean, SonarQube scan + quality gate OK"
