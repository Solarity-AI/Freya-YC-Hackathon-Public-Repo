"""Organiser rebuild readiness: builder.preflight fail-fast checks, the trace's start/end time + commit + Freya summary
(what the hackathon trace must show), the per-run default slot and the workflow counts."""
import json
import pathlib
import re
import subprocess
import types

import pytest

from builder import build, llm, preflight, trace

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRIEF_A = ROOT / "kit" / "briefs" / "brief-a.md"
API = ROOT / "kit" / "tools" / "openapi.json"
GOLDEN_A = json.loads((ROOT / "tests" / "golden" / "spec-a.json").read_text())


def _run(rc):
    return lambda *a, **kw: types.SimpleNamespace(returncode=rc, stdout="", stderr="")


# ----------------------------------------------------------------------------------------------- auth source

@pytest.mark.parametrize("env, want", [
    ({"ANTHROPIC_API_KEY": "x"}, "env:ANTHROPIC_API_KEY"),
    ({"CLAUDE_CODE_OAUTH_TOKEN": "x"}, "env:CLAUDE_CODE_OAUTH_TOKEN"),
    ({"CLAUDE_CODE_USE_BEDROCK": "1"}, "env:CLAUDE_CODE_USE_BEDROCK"),
    ({"CLAUDE_CODE_USE_VERTEX": "true"}, "env:CLAUDE_CODE_USE_VERTEX"),
])
def test_auth_from_environment(env, want, tmp_path):
    assert preflight.claude_auth_source(env, home=tmp_path, platform="linux") == want


def test_auth_provider_flag_must_be_truthy(tmp_path):
    assert preflight.claude_auth_source({"CLAUDE_CODE_USE_BEDROCK": "0"}, home=tmp_path, platform="linux") is None


def test_auth_from_credentials_file_and_config_dir(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / ".credentials.json").write_text("{}")
    assert preflight.claude_auth_source({}, home=tmp_path, platform="linux") == "file:.credentials.json"
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    assert preflight.claude_auth_source({"CLAUDE_CONFIG_DIR": str(cfg)}, home=tmp_path, platform="linux") is None
    (cfg / "settings.json").write_text(json.dumps({"apiKeyHelper": "/bin/echo"}))
    assert preflight.claude_auth_source({"CLAUDE_CONFIG_DIR": str(cfg)}, platform="linux") == "settings:apiKeyHelper"


def test_auth_settings_unreadable_or_without_helper(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text("{not json")
    assert preflight.claude_auth_source({}, home=tmp_path, platform="linux") is None
    (tmp_path / ".claude" / "settings.json").write_text("[]")
    assert preflight.claude_auth_source({}, home=tmp_path, platform="linux") is None


def test_auth_from_macos_keychain(tmp_path):
    seen = []

    def run(cmd, **kw):
        seen.append(cmd)
        return types.SimpleNamespace(returncode=0)
    assert preflight.claude_auth_source({}, home=tmp_path, platform="darwin", run=run) == "keychain"
    assert seen == [["security", "find-generic-password", "-s", preflight.KEYCHAIN_SERVICE]]   # no -w: no secret
    assert preflight.claude_auth_source({}, home=tmp_path, platform="darwin", run=_run(44)) is None

    def broken(*a, **kw):
        raise subprocess.TimeoutExpired("security", 10)
    assert preflight.claude_auth_source({}, home=tmp_path, platform="darwin", run=broken) is None
    assert preflight.claude_auth_source({}, home=tmp_path, platform="linux", run=run) is None


def test_auth_default_environment_is_os_environ(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert preflight.claude_auth_source(home=tmp_path) == "env:ANTHROPIC_API_KEY"


# ----------------------------------------------------------------------------------------------- check

def _found(name):
    return object()


def test_check_ok_reports_sources_only():
    facts = preflight.check(True, True, env={"FREYA_API_KEY": "fak_secretvalue", "FREYA_API_URL": "https://x"},
                            version=(3, 11), find_spec=_found, auth_source=lambda env: "env:ANTHROPIC_API_KEY")
    assert facts == {"python": "3.11", "freya_url": "https://x", "claude_auth": "env:ANTHROPIC_API_KEY"}
    assert "fak_" not in json.dumps(facts)


def test_check_without_llm_or_freya_needs_nothing():
    facts = preflight.check(False, False, env={}, version=(3, 10))
    assert facts["claude_auth"] == "not needed" and facts["freya_url"] == preflight.DEFAULT_FREYA_URL


@pytest.mark.parametrize("kw, msg", [
    (dict(need_llm=False, need_freya=False, version=(3, 9)), "Python 3.10+ is required (this is 3.9)"),
    (dict(need_llm=False, need_freya=True), "FREYA_API_KEY is not set"),
    (dict(need_llm=True, need_freya=False, find_spec=lambda n: None if n == "claude_agent_sdk" else object()),
     "Claude Agent SDK is not installed"),
    (dict(need_llm=False, need_freya=False, find_spec=lambda n: None), "missing Python package(s) jsonschema"),
    (dict(need_llm=True, need_freya=False, find_spec=_found, auth_source=lambda env: None), "no Claude login found"),
])
def test_check_failures_have_fix_it_messages(kw, msg):
    kw.setdefault("version", (3, 12))
    with pytest.raises(preflight.PreflightError, match=re.escape(msg)):
        preflight.check(env={}, **kw)


def test_check_auth_escape_hatch():
    facts = preflight.check(True, False, env={preflight.SKIP_AUTH_ENV: "1"}, version=(3, 12), find_spec=_found,
                            auth_source=lambda env: pytest.fail("must not be called"))
    assert facts["claude_auth"].startswith("unchecked")


def test_check_defaults_use_this_interpreter(monkeypatch):
    monkeypatch.delenv("FREYA_API_KEY", raising=False)
    with pytest.raises(preflight.PreflightError, match="FREYA_API_KEY"):
        preflight.check(False, True)


# ----------------------------------------------------------------------------------------------- build wiring

@pytest.fixture
def iso(monkeypatch, tmp_path):
    prev = llm.set_backend(lambda req: pytest.fail("unexpected LLM call"))
    monkeypatch.setattr(build.paths, "STATE", tmp_path / "state")
    yield
    llm.set_backend(prev)
    trace.close()


def _recs(tmp_path, slot):
    rd = sorted((tmp_path / "runs" / slot).glob("r*"))[-1]
    return rd, [json.loads(x) for x in (rd / "trace.jsonl").read_text().splitlines()]


def test_build_fails_fast_without_freya_key(tmp_path, monkeypatch, iso):
    monkeypatch.delenv("FREYA_API_KEY", raising=False)
    argv = [str(BRIEF_A), str(API), "--out-dir", str(tmp_path / "runs"), "--slot", "p1"]
    assert build.main(argv) == build.EXIT_INPUT
    rd, recs = _recs(tmp_path, "p1")
    assert [r["kind"] for r in recs] == ["START", "ERROR", "END", "SUMMARY"]
    assert "preflight: FREYA_API_KEY is not set" in recs[1]["msg"]
    assert not (rd / "catalog.json").exists()                       # nothing ran


def test_build_fails_fast_without_claude_login(tmp_path, monkeypatch, iso):
    llm.set_backend(None)                                           # the real SDK transport
    monkeypatch.setattr(preflight, "claude_auth_source", lambda env=None: None)
    monkeypatch.setattr(preflight.importlib.util, "find_spec", lambda name: object())
    argv = [str(BRIEF_A), str(API), "--out-dir", str(tmp_path / "runs"), "--slot", "p2", "--no-deploy"]
    assert build.main(argv) == build.EXIT_INPUT
    _, recs = _recs(tmp_path, "p2")
    assert any(r["kind"] == "ERROR" and "no Claude login found" in r["msg"] for r in recs)


def test_deployed_build_traces_times_commit_and_freya_summary(tmp_path, monkeypatch, iso):
    from builder import deploy
    monkeypatch.setenv("FREYA_API_KEY", "test-not-a-key")
    spec = tmp_path / "golden.json"
    spec.write_text(json.dumps(GOLDEN_A))
    monkeypatch.setattr(deploy, "deploy", lambda wf, slot, rd, dry_run=True: {
        "workflow_id": "w1", "agent_id": "a1", "version": 2, "export_path": str(rd) + "/x.json", "diff": [],
        "llm_ok": True, "created": True})
    monkeypatch.setattr(build, "smoke_turn", lambda wid, spec: "ok")
    argv = [str(BRIEF_A), str(API), "--out-dir", str(tmp_path / "runs"), "--slot", "p3", "--no-twin",
            "--spec-in", str(spec)]
    assert build.main(argv) == build.EXIT_OK
    rd, recs = _recs(tmp_path, "p3")
    start = recs[0]
    assert start["kind"] == "START" and start["started_at"].endswith("Z") and start["commit"]
    pre = [r for r in recs if r["kind"] == "START" and r["msg"] == "preflight ok"][0]
    assert pre["claude_auth"] == "not needed" and "FREYA_API_KEY" not in json.dumps(pre)
    built = [r for r in recs if r["kind"] == "FREYA" and r["msg"] == "built on Freya"][0]
    assert built["workflow_id"] == "w1" and built["agent_id"] == "a1" and built["nodes"] > 10 and built["tools"] >= 5
    summ = recs[-1]
    assert summ["kind"] == "SUMMARY" and summ["agent_id"] == "a1" and summ["ended_at"].endswith("Z")
    assert summ["build_s"] >= 0 and summ["nodes"] == built["nodes"] and "verify_identity" in summ["tools"]
    end = [r for r in recs if r["kind"] == "END"][0]
    assert end["ended_at"] and "build_s" in end
    txt = (rd / "trace.txt").read_text()
    assert "agent_id:        a1" in txt and "started_at:" in txt and "ended_at:" in txt


# ----------------------------------------------------------------------------------------------- helpers

def test_git_commit_variants(tmp_path):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        out = "abc123\n" if "rev-parse" in cmd else (" M builder/x.py\n" if len(calls) == 2 else "")
        return types.SimpleNamespace(returncode=0, stdout=out)
    assert build.git_commit(tmp_path, run=run) == "abc123+dirty"
    def clean(cmd, **kw):
        return types.SimpleNamespace(returncode=0, stdout="def\n" if "rev-parse" in cmd else "")
    assert build.git_commit(tmp_path, run=clean) == "def"
    assert build.git_commit(tmp_path, run=_run(128)) == "unknown"

    def boom(*a, **kw):
        raise OSError("no git")
    assert build.git_commit(tmp_path, run=boom) == "unknown"
    assert build.git_commit() != ""                                  # the real repo (or 'unknown' outside git)


def test_workflow_counts():
    wf = {"nodes": {"a": {"pre_actions": [{"function": {"name": "get_account"}}, {"function": {"name": "code_exec"}}]},
                    "b": {"tools": [{"name": "close_call"}, {"function": {"name": "get_account"}}]}, "c": "junk"},
          "global_nodes": {"g": {"pre_actions": [{"function": {"name": "add_note"}}]}},
          "tools": [{"function": {"name": "transfer_to_agent"}}, "junk"]}
    assert build.workflow_counts(wf) == {"nodes": 4, "tool_calls": 5,
                                         "tools": ["add_note", "close_call", "get_account", "transfer_to_agent"]}
    assert build.workflow_counts(None) == {"nodes": 0, "tool_calls": 0, "tools": []}
    assert build.workflow_counts({"nodes": {}, "global_nodes": []})["nodes"] == 0


def test_default_slot_is_fresh_per_run_and_named_after_the_brief():
    import datetime as dt
    t1 = dt.datetime(2026, 10, 11, 17, 5, 1, tzinfo=dt.timezone.utc)
    t2 = dt.datetime(2026, 10, 12, 17, 5, 1, tzinfo=dt.timezone.utc)
    s1, s2 = build.default_slot([str(BRIEF_A)], str(API), t1), build.default_slot([str(BRIEF_A)], str(API), t2)
    assert s1.startswith("brief-a-") and s1.endswith("-20261011T170501") and s1 != s2


def test_llm_uses_sdk_flag():
    prev = llm.set_backend(lambda req: {})
    try:
        assert llm.uses_sdk() is False
        llm.set_backend(None)
        assert llm.uses_sdk() is True
    finally:
        llm.set_backend(prev)


def test_default_slot_rehearsal_prefix_from_env():
    import datetime as dt
    t = dt.datetime(2026, 10, 11, 17, 5, 1, tzinfo=dt.timezone.utc)
    s = build.default_slot([str(BRIEF_A)], str(API), t, env={"BUILDER_SLOT_PREFIX": "fresh/x "})
    assert s.startswith("fresh-x-brief-a-") and s.endswith("-20261011T170501")
    assert build.default_slot([str(BRIEF_A)], str(API), t, env={}).startswith("brief-a-")
