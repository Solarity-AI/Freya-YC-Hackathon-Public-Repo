"""tools/submit.py: packages one hidden-brief build (export + traces) only after every consistency, secret and
published-version check passes, and prints the hackathon form JSON."""
import importlib.util
import io
import json
import pathlib
import subprocess
import contextlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("tools_submit", ROOT / "tools" / "submit.py")
submit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(submit)

WID, AGENT, UPDATED = "0f1e2d3c-aaaa-bbbb-cccc-111122223333", "a9b8c7d6-agent", "2026-10-11T17:05:00.000Z"


def make_run(root, name="hidden-1", run_id="r20261011T170501Z", wid=WID, agent=AGENT, version=3, exit_code=0,
             export_wid=None, commit="abc123", slot_sha="abcdef12"):
    rd = root / "runs" / ("%s-%s-20261011T170500" % (name, slot_sha)) / run_id
    rd.mkdir(parents=True)
    recs = [{"kind": "START", "msg": "build", "commit": commit, "run_dir": str(rd)},
            {"kind": "MODEL", "msg": "extract F1", "model": "claude-opus-5-5"},
            {"kind": "FREYA", "msg": "created workflow %s" % wid, "agent_id": agent},
            {"kind": "FREYA", "msg": "built on Freya", "workflow_id": wid, "agent_id": agent, "nodes": 28, "tools": 6},
            {"kind": "END", "msg": "exit %d" % exit_code},
            {"kind": "SUMMARY", "exit": exit_code, "deployed": True, "workflow_id": wid, "agent_id": agent,
             "version": version}]
    (rd / "trace.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\nnot json\n")
    txt = ("[+0.0s] START builder.build._run | build | argv=[] slot=s run_dir=%s model_default=claude-opus-5-5\n"
           "[+60.0s] FREYA builder.deploy.deploy | created workflow %s | agent_id=%s\n"
           "[+70.0s] END builder.build.run | exit %d | slot=s exit=%d\n" % (rd, wid, agent, exit_code, exit_code))
    (rd / "trace.txt").write_text(txt)
    (rd / "workflow.export.json").write_text(json.dumps({"workflow_id": export_wid or wid, "agent_id": agent,
                                                         "updated_at": UPDATED, "workflow": {"nodes": {}}}))
    (rd / "ids.json").write_text(json.dumps({"workflow_id": wid, "agent_id": agent, "version": version}))
    return rd


def tee_log(root, rd, name="hidden-1"):
    (root / "traces").mkdir(exist_ok=True)
    p = root / "traces" / (name + ".log")
    p.write_text((rd / "trace.txt").read_text() + "some stderr line\n")
    return p


class FakeFreya:
    def __init__(self, versions=None, updated=UPDATED):
        self.versions = versions if versions is not None else [{"id": "v2", "versionNumber": 2, "isPublished": True},
                                                               {"id": "v3", "versionNumber": 3, "isPublished": True}]
        self.updated, self.calls = updated, []

    def workspace_id(self):
        return "ws"

    def api(self, method, path, body=None, **params):
        self.calls.append((method, path))
        if "/versions/" in path:
            return {"versions": self.versions}
        return {"workflow": {"id": WID, "updatedAt": self.updated}}


def run_main(argv, root, fr=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = submit.main(argv, root=root, fr=fr)
    return code, out.getvalue(), err.getvalue()


# ----------------------------------------------------------------------------------------------- happy paths

def test_package_from_tee_log_offline(tmp_path):
    rd = make_run(tmp_path)
    make_run(tmp_path, run_id="r20261011T180000Z", wid="ffffffff-later-run")      # newer, but the log names rd
    tee_log(tmp_path, rd)
    code, out, err = run_main(["hidden-1", "--offline"], tmp_path)
    assert code == 0, err
    assert json.loads((tmp_path / "submission" / "hidden-1.workflow.json").read_text())["workflow_id"] == WID
    assert (tmp_path / "traces" / "hidden-1.trace.jsonl").read_text() == (rd / "trace.jsonl").read_text()
    assert "some stderr line" in (tmp_path / "traces" / "hidden-1.log").read_text()      # the tee'd log is kept
    form = json.loads(out)
    assert form == {"team": "Solarity-AI", "repo": submit.REPO,
                    "branch": submit.BRANCH, "commit": form["commit"],
                    "run_command": "python3 builder/build.py {brief_path} {tool_api_path}",
                    "workflows": {"hidden-1": "submission/hidden-1.workflow.json"},
                    "traces": {"hidden-1": "traces/hidden-1.log"}}


def test_package_online_checks_the_published_version(tmp_path):
    rd = make_run(tmp_path)
    tee_log(tmp_path, rd)
    fr = FakeFreya()
    code, _, err = run_main(["hidden-1"], tmp_path, fr=fr)
    assert code == 0 and "is the published newest one" in err
    assert [m for m, _ in fr.calls] == ["GET", "GET"]                               # read-only


def test_without_log_latest_run_and_trace_txt_fallback(tmp_path):
    make_run(tmp_path, run_id="r20261011T170501Z", wid="11111111-old")
    make_run(tmp_path, run_id="r20261011T180000Z")
    make_run(tmp_path, name="hidden-10", wid="22222222-other")                     # hidden-10 is not hidden-1
    code, _, err = run_main(["hidden-1", "--offline"], tmp_path)
    assert code == 0 and "is missing" in err
    assert WID in (tmp_path / "traces" / "hidden-1.log").read_text()


def test_explicit_run_dir_and_form_lists_every_slot_in_order(tmp_path):
    for n, wid in (("hidden-2", "22222222-two"), ("hidden-10", "10101010-ten"), ("hidden-1", WID)):
        rd = make_run(tmp_path, name=n, wid=wid)
        tee_log(tmp_path, rd, n)
        assert run_main([n, "--offline", "--run-dir", str(rd)], tmp_path)[0] == 0
    (tmp_path / "submission" / "hidden-3.workflow.json").write_text("{}")          # no trace: not in the form
    code, out, _ = run_main(["--form"], tmp_path)
    assert code == 0 and list(json.loads(out)["workflows"]) == ["hidden-1", "hidden-2", "hidden-10"]


# ----------------------------------------------------------------------------------------------- refusals

def _refused(tmp_path, needle, argv=("hidden-1", "--offline"), fr=None):
    code, out, err = run_main(list(argv), tmp_path, fr=fr)
    assert code == 1 and out == "" and needle in err, err
    assert not (tmp_path / "submission" / "hidden-1.workflow.json").exists()


@pytest.mark.parametrize("kw, needle", [
    (dict(export_wid="99999999-other"), "workflow id mismatch"),
    (dict(exit_code=4), "the build exited 4"),
])
def test_inconsistent_run_is_refused(tmp_path, kw, needle):
    make_run(tmp_path, **kw)
    _refused(tmp_path, needle)


def _rewrite(rd, fn):
    recs = [json.loads(x) for x in (rd / "trace.jsonl").read_text().splitlines() if x.startswith("{")]
    (rd / "trace.jsonl").write_text("\n".join(json.dumps(r) for r in fn(recs)) + "\n")


def test_run_without_summary_is_refused(tmp_path):
    _rewrite(make_run(tmp_path), lambda recs: [r for r in recs if r["kind"] != "SUMMARY"])
    _refused(tmp_path, "has no SUMMARY")


def test_run_with_two_workflow_ids_is_refused(tmp_path):
    _rewrite(make_run(tmp_path), lambda recs: [{"kind": "FREYA", "msg": "updated workflow 88888888-second"}] + recs)
    _refused(tmp_path, "expected one workflow id")


def test_run_with_another_agent_is_refused(tmp_path):
    _rewrite(make_run(tmp_path), lambda recs: recs[:-1] + [dict(recs[-1], agent_id="other-agent")])
    _refused(tmp_path, "export agent_id")


def test_run_without_export_is_refused(tmp_path):
    (make_run(tmp_path) / "workflow.export.json").unlink()
    _refused(tmp_path, "no workflow.export.json")


def test_log_problems_are_refused(tmp_path):
    rd = make_run(tmp_path)
    log = tee_log(tmp_path, rd)
    log.write_text("no start line here\n")
    _refused(tmp_path, "has no START line")
    other = make_run(tmp_path, run_id="r20261011T190000Z")
    log.write_text((rd / "trace.txt").read_text().replace(rd.name, other.name))
    _refused(tmp_path, "names another run", argv=("hidden-1", "--offline", "--run-dir", str(rd)))
    log.write_text((rd / "trace.txt").read_text().replace("exit 0", "exit 5"))
    _refused(tmp_path, "no 'END ... | exit 0' line")
    log.write_text((rd / "trace.txt").read_text().replace(WID, "<id>"))
    _refused(tmp_path, "never mentions workflow")
    log.write_text("[+0.0s] START builder.build._run | build | run_dir=%s/gone model_default=x\n" % tmp_path)
    _refused(tmp_path, "has no trace.jsonl")


def test_no_run_at_all(tmp_path):
    _refused(tmp_path, "no run of brief hidden-1")


def test_secrets_are_refused(tmp_path, monkeypatch):
    rd = make_run(tmp_path)
    tee_log(tmp_path, rd).write_text((rd / "trace.txt").read_text() + "key=fak_" + "AbCdEf123\n")
    _refused(tmp_path, "a fak_ key")
    tee_log(tmp_path, rd)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "plain-secret-value-1")
    (rd / "trace.jsonl").write_text((rd / "trace.jsonl").read_text() + '{"x": "plain-secret-value-1"}\n')
    code, _, err = run_main(["hidden-1", "--offline"], tmp_path)
    assert code == 1 and "the value of ANTHROPIC_API_KEY" in err and "plain-secret-value-1" not in err


def test_scan_ignores_masked_and_short_values(tmp_path):
    f = tmp_path / "t.log"
    f.write_text("FREYA_API_KEY=*** export FREYA_API_KEY=fak_... sk-ant-*** short\n")
    assert submit.scan_secrets([f], env={"FREYA_API_KEY": "short"}) == []


@pytest.mark.parametrize("fr, needle", [
    (FakeFreya(versions=[]), "no versions listed"),
    (FakeFreya(versions=[{"id": "v3", "versionNumber": 3, "isPublished": False}]), "is not published"),
    (FakeFreya(versions=[{"id": "v4", "versionNumber": 4, "isPublished": True}]), "edited after the run"),
    (FakeFreya(updated="2026-10-11T18:00:00.000Z"), "updatedAt is"),
])
def test_published_check_refusals(tmp_path, fr, needle):
    tee_log(tmp_path, make_run(tmp_path))
    _refused(tmp_path, needle, argv=("hidden-1",), fr=fr)


def test_online_needs_a_key(tmp_path, monkeypatch):
    tee_log(tmp_path, make_run(tmp_path))
    monkeypatch.delenv("FREYA_API_KEY", raising=False)
    _refused(tmp_path, "FREYA_API_KEY is not set", argv=("hidden-1",))


def test_kit_client_is_loaded_with_a_key(monkeypatch):
    monkeypatch.setenv("FREYA_API_KEY", "test-not-a-key")
    assert hasattr(submit._kit_freya(ROOT), "export_workflow")


def test_versions_as_a_bare_list():
    fr = FakeFreya()
    fr.api = lambda method, path, body=None, **p: ([{"versionNumber": 1, "isPublished": True}] if "/versions/" in path
                                                   else {"workflow": {}})
    assert submit.check_published(fr, WID, None, None) == 1


# ----------------------------------------------------------------------------------------------- usage + git

@pytest.mark.parametrize("argv, code", [([], 2), (["brief-a"], 2), (["--bogus"], 2), (["--help"], 0)])
def test_usage(tmp_path, argv, code):
    assert run_main(argv, tmp_path)[0] == code


def test_run_dir_from_log_with_spaces():
    line = "[+0.0s] START builder.build._run | build | argv=[] run_dir=/a b/runs/x/r1 model_default=m\n"
    assert submit.run_dir_from_log("noise\n" + line) == pathlib.Path("/a b/runs/x/r1")
    assert submit.run_dir_from_log("[+0.0s] START m | build | run_dir=/x/r2\n") == pathlib.Path("/x/r2")
    assert submit.run_dir_from_log("[+0.0s] START m | build | nothing\n") is None


def _git(root, *args):
    subprocess.run(["git", "-C", str(root)] + list(args), check=True, capture_output=True)


def test_git_warnings(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "builder").mkdir()
    (tmp_path / "builder" / "a.py").write_text("x = 1\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "one")
    first = submit.git_head(tmp_path)
    (tmp_path / "builder" / "a.py").write_text("x = 2\n")
    _git(tmp_path, "commit", "-qam", "two")
    w = submit.git_warnings(tmp_path, first + "+dirty")
    assert any("UNCOMMITTED" in x for x in w) and any("changed between" in x for x in w)
    assert any("not on origin/%s" % submit.BRANCH in x for x in w) and not any("uncommitted changes" in x for x in w)
    (tmp_path / "builder" / "a.py").write_text("x = 3\n")
    w = submit.git_warnings(tmp_path, submit.git_head(tmp_path))
    assert any("uncommitted changes" in x for x in w) and not any("changed between" in x for x in w)
    assert submit.git_head(tmp_path / "nope") == "unknown"


def test_gitignore_keeps_submission_files():
    if not (ROOT / ".gitignore").exists():
        pytest.skip("source distribution has no ignore rules")
    paths = ["traces/hidden-1.log", "traces/hidden-2.trace.jsonl", "submission/hidden-1.workflow.json"]
    for p in paths:
        r = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "--no-index", "-q", p], capture_output=True)
        assert r.returncode == 1, p                             # 1 = not ignored
    r = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "--no-index", "-q", "debug.log"], capture_output=True)
    assert r.returncode == 0                                    # *.log elsewhere stays ignored


def test_latest_run_honours_the_rehearsal_slot_prefix(tmp_path, monkeypatch):
    make_run(tmp_path, name="fresh-hidden-1", run_id="r20261011T180000Z", wid="33333333-fresh")
    monkeypatch.setenv("BUILDER_SLOT_PREFIX", "fresh-")
    rd = submit.latest_run(tmp_path, "hidden-1")
    assert rd is not None and rd.parent.name.startswith("fresh-hidden-1-")
    monkeypatch.delenv("BUILDER_SLOT_PREFIX")
    assert submit.latest_run(tmp_path, "hidden-1") is None


# ----------------------------------------------------------------------------------------------- platform down

class DownFreya(FakeFreya):
    """kit freya.api raises RuntimeError on an HTTP error status (e.g. a 5xx)."""

    def api(self, method, path, body=None, **params):
        self.calls.append((method, path))
        raise RuntimeError("GET %s -> 503: upstream unavailable" % path)


class SlowFreya(FakeFreya):
    """A hung platform: the kit's urlopen would wait 120 s."""

    def api(self, method, path, body=None, **params):
        import time
        self.calls.append((method, path))
        time.sleep(2)
        return super().api(method, path, body, **params)


def test_freya_api_error_is_a_fail_line_suggesting_offline(tmp_path):
    tee_log(tmp_path, make_run(tmp_path))
    code, out, err = run_main(["hidden-1"], tmp_path, fr=DownFreya())
    assert code == 1 and out == ""
    assert "FAIL hidden-1: Freya API error (" in err and "503" in err and "--offline" in err, err
    assert "Traceback" not in err
    assert not (tmp_path / "submission" / "hidden-1.workflow.json").exists()
    assert not (tmp_path / "traces" / "hidden-1.trace.jsonl").exists()


def test_published_check_has_a_short_deadline(tmp_path, monkeypatch):
    import time
    tee_log(tmp_path, make_run(tmp_path))
    monkeypatch.setattr(submit, "PUBLISHED_CHECK_TIMEOUT_S", 0.05)
    t0 = time.monotonic()
    code, out, err = run_main(["hidden-1"], tmp_path, fr=SlowFreya())
    assert time.monotonic() - t0 < 1.5
    assert code == 1 and out == "" and "did not answer within 0.05s" in err and "--offline" in err, err
    assert not (tmp_path / "submission" / "hidden-1.workflow.json").exists()


def test_bounded_check_passes_results_and_errors_through():
    fr = FakeFreya()
    assert submit.check_published_bounded(fr, WID, 3, UPDATED, timeout=5) == 3
    empty, down = FakeFreya(versions=[]), DownFreya()
    with pytest.raises(submit.SubmitError, match="no versions listed"):
        submit.check_published_bounded(empty, WID, 3, UPDATED, timeout=5)
    with pytest.raises(RuntimeError, match="503"):
        submit.check_published_bounded(down, WID, 3, UPDATED, timeout=5)
