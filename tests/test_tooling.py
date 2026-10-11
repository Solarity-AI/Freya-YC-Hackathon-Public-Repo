"""tools/quality.sh: runs every step and exits non-zero when ANY gate fails (tests/coverage, vulture, the SonarQube
scanner, the quality gate API). Each scenario runs the real script in a scratch copy of the repo with stub `python`,
`docker` and `curl` commands, so nothing here runs the test suite, docker or the network."""
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOKEN = "tok-SECRET-123"

PY_STUB = """#!/bin/bash
echo "python $*" >> "$Q_LOG"
if [ "$1" = "-" ]; then exec "{real}" "$@"; fi
case "$2" in
  pytest) echo "pytest ran cov=$COVERAGE_FILE"; exit "${{Q_PYTEST_RC:-0}}";;
  coverage) echo '<coverage/>' > coverage.xml; exit "${{Q_XML_RC:-0}}";;
  vulture) printf '%s' "${{Q_VULTURE_OUT:-}}"; exit "${{Q_VULTURE_RC:-0}}";;
esac
exit 99
"""

DOCKER_STUB = """#!/bin/bash
echo "docker $*" >> "$Q_LOG"
case "$1" in
  inspect) echo "${Q_SONAR_RUNNING:-true}";;
  run) [ "$SONAR_TOKEN" = "%s" ] && echo "docker-token-from-env" >> "$Q_LOG"
       echo "INFO  Sensor Cobertura Sensor for Python coverage [python]"
       echo "INFO  EXECUTION SUCCESS"; exit "${Q_SCAN_RC:-0}";;
esac
exit 0
""" % TOKEN

CURL_STUB = """#!/bin/bash
cfg="$(cat)"
echo "curl $*" >> "$Q_LOG"
case "$cfg" in *%s*) echo "curl-token-from-stdin" >> "$Q_LOG";; esac
[ "${Q_CURL_RC:-0}" = 0 ] || exit "$Q_CURL_RC"
case "$*" in
  *project_status*) printf '{"projectStatus":{"status":"%%s","conditions":[{"metricKey":"new_violations",
    "status":"%%s","actualValue":"3","comparator":"GT","errorThreshold":"0"}]}}' "${Q_GATE:-OK}" "${Q_GATE:-OK}";;
  *measures*) printf '{"component":{"measures":[{"metric":"coverage","value":"99.9"},
    {"metric":"duplicated_lines_density","value":"0.0"},{"metric":"bugs","value":"0"},{"metric":"code_smells",
    "value":"128"}]}}';;
esac
""" % TOKEN


def _exe(path, text):
    path.write_text(text)
    path.chmod(0o755)


@pytest.fixture
def run_quality(tmp_path):
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    (repo / ".venv" / "bin").mkdir(parents=True)
    shutil.copy(ROOT / "tools" / "quality.sh", repo / "tools" / "quality.sh")
    shutil.copy(ROOT / ".coveragerc", repo / ".coveragerc")
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "sonar.env").write_text("SONAR_TOKEN=%s\n" % TOKEN)
    _exe(repo / ".venv" / "bin" / "python", PY_STUB.format(real=sys.executable))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _exe(bin_dir / "docker", DOCKER_STUB)
    _exe(bin_dir / "curl", CURL_STUB)
    log = tmp_path / "calls.log"

    def run(**knobs):
        log.write_text("")
        env = {k: v for k, v in os.environ.items() if not k.startswith(("Q_", "SONAR_", "COVERAGE_"))}
        env.update(PATH=str(bin_dir) + os.pathsep + env["PATH"], Q_LOG=str(log), **knobs)
        r = subprocess.run(["bash", str(repo / "tools" / "quality.sh")], env=env, capture_output=True, text=True,
                           timeout=60)
        return r.returncode, r.stdout + r.stderr, log.read_text()
    run.repo = repo
    return run


def test_all_green_exits_zero_with_summary(run_quality):
    rc, out, calls = run_quality()
    assert rc == 0, out
    assert "QUALITY OK" in out and "vulture: clean" in out
    assert "sonar: gate=OK  coverage=99.9  duplicated_lines_density=0.0  bugs=0  vulnerabilities=?  " \
           "code_smells=128" in out
    assert "-Dsonar.qualitygate.wait=true" in calls
    assert "/api/qualitygates/project_status?projectKey=freya-builder" in calls
    assert "Cobertura Sensor" in out                     # the scanner's coverage lines are shown


def test_token_never_on_argv_or_in_output(run_quality):
    rc, out, calls = run_quality()
    assert rc == 0, out
    assert TOKEN not in out and TOKEN not in calls        # calls.log records every stub's argv
    assert "docker-token-from-env" in calls and "curl-token-from-stdin" in calls


def test_coverage_data_file_is_private_and_xml_has_repo_relative_paths(run_quality):
    rc, out, calls = run_quality()
    assert rc == 0, out
    cov = next(l for l in out.splitlines() if l.startswith("pytest ran cov="))
    assert "freya-quality." in cov and str(run_quality.repo) not in cov
    assert "-m coverage xml --rcfile=" in calls and "-o coverage.xml" in calls
    assert (run_quality.repo / "coverage.xml").exists()


@pytest.mark.parametrize("rc_text,kept", [
    ("[run]\nsource = builder,runtime,harness\nbranch = True\n\n[report]\nshow_missing = True\n",
     ("branch = True", "show_missing = True")),
    ("", ()),
])
def test_xml_rcfile_drops_source_and_keeps_relative_files(tmp_path, rc_text, kept):
    """The rcfile the script writes for `coverage xml`: no `source` (so paths stay builder/..., runtime/...)."""
    script = (ROOT / "tools" / "quality.sh").read_text()
    body = script.split("<<'PYCFG'\n", 1)[1].split("\nPYCFG", 1)[0]
    (tmp_path / ".coveragerc").write_text(rc_text)
    subprocess.run([sys.executable, "-", str(tmp_path / "out.rc")], input=body, text=True, cwd=tmp_path, check=True)
    out = (tmp_path / "out.rc").read_text()
    assert "source" not in out and "relative_files = True" in out
    assert all(k in out for k in kept)


@pytest.mark.parametrize("knobs,reason", [
    ({"Q_PYTEST_RC": "1"}, "pytest/coverage (exit 1)"),
    ({"Q_PYTEST_RC": "2"}, "pytest/coverage (exit 2)"),
    ({"Q_XML_RC": "1"}, "coverage.xml (exit 1)"),
    ({"Q_VULTURE_OUT": "builder/x.py:3: unused function 'f' (60% confidence)\n"}, "vulture: 1 finding(s) (exit 0)"),
    ({"Q_VULTURE_RC": "3"}, "vulture: 0 finding(s) (exit 3)"),
    ({"Q_SCAN_RC": "3"}, "SonarQube scanner (exit 3)"),
    ({"Q_SONAR_RUNNING": "false"}, "SonarQube scanner (exit 125)"),
    ({"Q_GATE": "ERROR"}, "SonarQube quality gate is not OK"),
    ({"Q_GATE": "WARN"}, "SonarQube quality gate is not OK"),
    ({"Q_CURL_RC": "22"}, "SonarQube API unreachable (curl exit 22)"),
])
def test_any_failing_gate_exits_non_zero(run_quality, knobs, reason):
    rc, out, _calls = run_quality(**knobs)
    assert rc == 1, out
    assert "FAIL: " + reason in out
    assert "QUALITY FAILED" in out and "QUALITY OK" not in out


def test_failed_tests_do_not_skip_later_steps(run_quality):
    rc, out, calls = run_quality(Q_PYTEST_RC="1", Q_GATE="ERROR")
    assert rc == 1
    assert "-m vulture" in calls and "docker run" in calls and "project_status" in calls
    assert "QUALITY FAILED (2)" in out
    assert "gate condition new_violations: 3 (threshold GT 0)" in out


@pytest.mark.parametrize("env_text", ["OTHER=1\n", None])
def test_missing_token_or_env_file_fails_without_calling_sonar(run_quality, tmp_path, env_text):
    env_file = tmp_path / "state" / "sonar.env"
    if env_text is None:
        env_file.unlink()
    else:
        env_file.write_text(env_text)
    rc, out, calls = run_quality()
    assert rc == 1 and "FAIL: SONAR_TOKEN missing from ../state/sonar.env" in out, out
    assert "docker run" not in calls and "curl" not in calls


def test_exit_trap_keeps_the_failure_status():
    """bash 3.2 (macOS /usr/bin/env bash) returns the EXIT trap's status unless the trap re-exits with $?."""
    script = (ROOT / "tools" / "quality.sh").read_text()
    assert """trap 'status=$?; rm -rf "$work"; exit "$status"' EXIT""" in script
