"""builder/build.py CLI and pipeline orchestration with fakes (agent 5): exit codes, artifacts, trace, budget."""
import copy
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

from builder import build, llm, trace
from builder import budget as budget_mod
from builder.pipeline import extract

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRIEF_A = ROOT / "kit" / "briefs" / "brief-a.md"
API = ROOT / "kit" / "tools" / "openapi.json"
REAL_BUDGET = budget_mod.Budget
GOLDEN_A = json.loads((ROOT / "tests" / "golden" / "spec-a.json").read_text())


@pytest.fixture(autouse=True)
def _iso(monkeypatch, tmp_path):
    prev = llm.set_backend(lambda req: pytest.fail("unexpected LLM call: " + req["purpose"]))
    monkeypatch.setattr(build.paths, "STATE", tmp_path / "state")
    monkeypatch.setenv("FREYA_API_KEY", "test-not-a-key")     # the preflight needs a key for a deploying run
    yield
    llm.set_backend(prev)
    trace.close()


@pytest.fixture
def fake_compile(monkeypatch):
    from builder.compiler import graph, lint
    calls = {}

    def compile_workflow(spec, catalog, flags=None):
        calls["flags"] = flags
        return {"initial_node": "s_open", "nodes": {"s_open": {}}}, {"listen": {}}
    monkeypatch.setattr(graph, "compile_workflow", compile_workflow)
    monkeypatch.setattr(lint, "lint", lambda wf, cat, spec, w: [{"level": "warn", "rule": "x", "where": "n",
                                                                  "msg": "fyi"}])
    return calls


def golden_values(facet):
    vals = {k: copy.deepcopy(GOLDEN_A[k]) for k in extract.FACETS[facet]}
    if facet == "F5":                                   # F5 carries the brief's interpretation choices
        vals["interpretation"] = copy.deepcopy(GOLDEN_A["interpretation"])
    if "products" in vals:
        vals["products"].pop("fields", None)
    return vals


def fake_llm(critic_issues=None, broken=None):
    """Extraction from golden A; facets in `broken` return a bad value on their first call."""
    seen = {"extract": [], "critic": 0, "prompts": []}

    def fn(req):
        seen["prompts"].append(req["prompt"])
        if req["purpose"].startswith("critic"):
            seen["critic"] += 1
            return {"issues": critic_issues or [], "residual": [{"text": "critic residual", "class": "flow"}]}
        facet = req["purpose"].split()[1]
        seen["extract"].append(facet)
        vals = golden_values(facet)
        if broken and facet in broken and seen["extract"].count(facet) == 1:
            broken[facet](vals)
        return {"values": vals, "sources": [{"pointer": "/" + k, "quote": "Read all of it."} for k in vals],
                "decisions": [], "residual": []}
    return fn, seen


def run_cli(tmp_path, *extra, inputs=None):
    argv = [str(p) for p in (inputs or [BRIEF_A, API])] + ["--out-dir", str(tmp_path / "runs"), "--slot", "t1"]
    code = build.main(argv + list(extra))
    runs = sorted((tmp_path / "runs" / "t1").glob("r*"))
    return code, (runs[-1] if runs else None)


def trace_recs(run_dir):
    return [json.loads(x) for x in (run_dir / "trace.jsonl").read_text().splitlines()]


# ----------------------------------------------------------------------------------------------- args

def test_parse_args_detects_api_by_content_anywhere(tmp_path):
    odd = tmp_path / "tools.txt"
    shutil.copy(API, odd)
    ns = build.parse_args([str(odd), str(BRIEF_A), "--no-deploy", "--flags", "bye=listen, write_chain=off"])
    assert ns.api == str(odd) and ns.briefs == [str(BRIEF_A)] and ns.no_deploy
    assert ns.flags == {"bye": "listen", "write_chain": "off"} and ns.slot == "" and not ns.dev
    ns = build.parse_args([str(BRIEF_A), str(ROOT / "kit" / "briefs" / "brief-b.md"), str(API)])
    assert len(ns.briefs) == 2 and ns.api == str(API)


@pytest.mark.parametrize("argv,msg", [
    (["missing.md", str(API)], "not found"),
    ([str(BRIEF_A)], "exactly one tool API"),
    ([str(BRIEF_A), str(API), str(API)], None),
    ([str(API)], "no brief"),
    ([str(BRIEF_A), str(API), "--flags", "oops"], "bad --flags"),
    ([str(BRIEF_A), str(API), "--spec-in", "nope.json"], "--spec-in"),
    ([str(BRIEF_A), str(API), "--bogus"], "bad arguments"),
])
def test_parse_args_rejects_bad_input(argv, msg, tmp_path):
    with pytest.raises(build.InputError) as ei:
        build.parse_args(argv)
    if msg:
        assert msg in str(ei.value)


def test_two_api_files(tmp_path):
    other = tmp_path / "api2.json"
    shutil.copy(API, other)
    with pytest.raises(build.InputError, match="found 2"):
        build.parse_args([str(BRIEF_A), str(API), str(other)])


def test_empty_brief_rejected(tmp_path):
    e = tmp_path / "empty.md"
    e.write_text("")
    with pytest.raises(build.InputError, match="empty"):
        build.parse_args([str(e), str(API)])


def test_main_bad_input_exit_2_no_run_dir(tmp_path):
    assert build.main(["nope.md", str(API), "--out-dir", str(tmp_path / "runs")]) == build.EXIT_INPUT
    assert not (tmp_path / "runs").exists()


def test_default_slot_shape():
    s1 = build.default_slot([str(BRIEF_A)], str(API))
    assert re.match(r"^brief-a-[0-9a-f]{8}-\d{8}T\d{6}$", s1)
    assert s1.split("-")[2] == build.default_slot([str(BRIEF_A)], str(API)).split("-")[2]
    s2 = build.default_slot([str(BRIEF_A), str(ROOT / "kit" / "briefs" / "brief-b.md")], str(API))
    assert s2.split("-")[2] != s1.split("-")[2]


def test_parse_flags():
    assert build.parse_flags("") == {} and build.parse_flags(" a=1 ,b = x=y ,") == {"a": "1", "b": "x=y"}


# ----------------------------------------------------------------------------------------------- full runs

def test_full_run_with_fake_llm(tmp_path, fake_compile):
    fn, seen = fake_llm()
    llm.set_backend(fn)
    code, rd = run_cli(tmp_path, "--no-deploy", "--no-twin", "--flags", "bye=listen")
    assert code == build.EXIT_OK
    for f in ("catalog.json", "spec.draft.json", "spec.json", "decisions.md", "wiring.json", "workflow.json",
              "trace.txt", "trace.jsonl"):
        assert (rd / f).exists(), f
    # BUILD SPEED item 2: a clean validation never calls the critic (one parallel wave of facet calls only)
    assert sorted(seen["extract"]) == sorted(extract.FACETS) and seen["critic"] == 0
    assert fake_compile["flags"] == {"bye": "listen"}
    spec = json.loads((rd / "spec.json").read_text())
    assert {k: v for k, v in spec.items() if k != "meta"} == {k: v for k, v in GOLDEN_A.items() if k != "meta"}
    recs = trace_recs(rd)
    kinds = [r["kind"] for r in recs]
    for k in ("START", "INPUT", "CATALOG", "SEGMENT", "EXTRACT", "MODEL", "VALIDATE", "SPEC", "COMPILE",
              "LINT", "DEPLOY", "STAGE", "END", "SUMMARY"):
        assert k in kinds, k
    assert "CRITIC" not in kinds and not any(r["kind"] == "MODEL" and r["msg"].startswith("critic") for r in recs)
    assert kinds.count("MODEL") == len(extract.FACETS) and kinds[-2:] == ["END", "SUMMARY"]
    assert all(r.get("effort") == llm.choice(r["msg"].split()[1])[1] for r in recs if r["kind"] == "MODEL")
    start = [r for r in recs if r["kind"] == "START"][0]
    assert start["effort_default"] == llm.DEFAULT_EFFORT and start["critic"] is False
    stages = [r for r in recs if r["kind"] == "SUMMARY"][0]["stages"]
    assert set(stages) >= {"input", "extract", "validate", "compile", "lint", "deploy"}
    txt = (rd / "trace.txt").read_text()
    assert "SUMMARY" in txt and "exit:            0" in txt and "lint_warnings:   1" in txt


def test_spec_in_skips_llm(tmp_path, fake_compile):
    p = tmp_path / "golden.json"
    p.write_text(json.dumps(GOLDEN_A))
    code, rd = run_cli(tmp_path, "--no-deploy", "--no-twin", "--spec-in", str(p))
    assert code == build.EXIT_OK
    assert "--spec-in" in (rd / "trace.txt").read_text()


def test_invalid_spec_exit_3(tmp_path, fake_compile):
    bad = copy.deepcopy(GOLDEN_A)
    bad["situations"]["S_PAID"]["outcome"] = "maybe"
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    code, rd = run_cli(tmp_path, "--no-deploy", "--spec-in", str(p))
    assert code == build.EXIT_SPEC
    assert "maybe" in (rd / "decisions.md").read_text() and not (rd / "workflow.json").exists()


def test_reextraction_fixes_a_facet(tmp_path, fake_compile):
    def breaker(vals):
        vals["identity"]["questions"][0]["field_value"] = "favourite_colour"
    fn, seen = fake_llm(broken={"F2": breaker})
    llm.set_backend(fn)
    code, rd = run_cli(tmp_path, "--no-deploy", "--no-twin", "--no-critic")
    assert code == build.EXIT_OK and seen["extract"].count("F2") == 2 and len(seen["extract"]) == len(extract.FACETS) + 1
    assert "Corrections required" in seen["prompts"][-1] and "favourite_colour" in seen["prompts"][-1]
    assert any("targeted re-extraction" in r["msg"] for r in trace_recs(rd))


def test_persistent_bad_leaf_is_degraded_not_fatal(tmp_path, fake_compile):
    # review fix round 1: one bad leaf that survives re-extraction is dropped (degraded Spec), the build goes on
    def always(req):
        if req["purpose"].startswith("critic"):
            return {"issues": [], "residual": []}
        vals = golden_values(req["purpose"].split()[1])
        if "identity" in vals:
            vals["identity"]["hints"][0]["value"] = "made_up_hint"
        return {"values": vals, "sources": [], "decisions": [], "residual": []}
    llm.set_backend(always)
    code, rd = run_cli(tmp_path, "--no-deploy")
    assert code == build.EXIT_OK
    assert "made_up_hint" in (rd / "decisions.md").read_text()
    spec = json.loads((rd / "spec.json").read_text())
    assert all(h.get("value") != "made_up_hint" for h in spec["identity"]["hints"])
    assert any(d.startswith("degraded: ") for d in spec["meta"]["decisions"])
    assert '"degraded": true' in (rd / "trace.jsonl").read_text()


def test_persistent_unfixable_error_exit_3(tmp_path, fake_compile):
    def always(req):
        if req["purpose"].startswith("critic"):
            return {"issues": [], "residual": []}
        vals = golden_values(req["purpose"].split()[1])
        if "identity" in vals:
            for q in vals["identity"]["questions"]:
                q["field_value"] = "made_up_field"
        return {"values": vals, "sources": [], "decisions": [], "residual": []}
    llm.set_backend(always)
    code, rd = run_cli(tmp_path, "--no-deploy")
    assert code == build.EXIT_SPEC
    assert "made_up_field" in (rd / "decisions.md").read_text()


def test_critic_patch_applied_and_bad_patch_reverted(tmp_path, fake_compile):
    issues = [{"quote": "Three wrong answers in total end the check", "problem": "goodbye wording",
               "pointer": "/closing/goodbye", "op": {"op": "replace", "path": "/closing/goodbye",
                                                     "value": "Thank you. Goodbye."}},
              {"quote": "Three wrong answers in total end the check", "problem": "bad outcome",
               "pointer": "/situations/S_PAID/outcome",
               "op": {"op": "replace", "path": "/situations/S_PAID/outcome", "value": "nonsense"}}]
    fn, _ = fake_llm(critic_issues=issues)
    llm.set_backend(fn)
    code, rd = run_cli(tmp_path, "--no-deploy", "--no-twin", "--critic")
    assert code == build.EXIT_OK
    spec = json.loads((rd / "spec.json").read_text())
    assert spec["closing"]["goodbye"] == "Thank you. Goodbye." and spec["situations"]["S_PAID"]["outcome"] == "paid"
    assert any("critic: goodbye wording" in d for d in spec["meta"]["decisions"])


def test_critic_crash_keeps_spec(tmp_path, fake_compile):
    fn, _ = fake_llm()

    def crashing(req):
        if req["purpose"].startswith("critic"):
            raise RuntimeError("critic down")
        return fn(req)
    llm.set_backend(crashing)
    code, rd = run_cli(tmp_path, "--no-deploy", "--no-twin", "--critic")
    assert code == build.EXIT_OK
    assert any("critic failed" in r["msg"] for r in trace_recs(rd))


def test_lint_error_exit_4(tmp_path, fake_compile, monkeypatch):
    from builder.compiler import lint
    monkeypatch.setattr(lint, "lint", lambda *a: [{"level": "error", "rule": "L1", "where": "ctl", "msg": "bad"}])
    p = tmp_path / "golden.json"
    p.write_text(json.dumps(GOLDEN_A))
    code, rd = run_cli(tmp_path, "--no-deploy", "--spec-in", str(p))
    assert code == build.EXIT_LINT
    assert any(r["kind"] == "LINT" and "L1" in r["msg"] for r in trace_recs(rd))


def test_deploy_paths(tmp_path, fake_compile, monkeypatch):
    from builder import deploy
    p = tmp_path / "golden.json"
    p.write_text(json.dumps(GOLDEN_A))
    monkeypatch.setenv("FREYA_API_KEY", "fak_secret_value_123456")
    got = {}

    def ok(workflow, slot, run_dir, dry_run=True):
        got.update(slot=slot, dry_run=dry_run)
        return {"workflow_id": "w1", "agent_id": "a1", "version": 2, "export_path": str(run_dir) + "/x.json",
                "diff": []}
    monkeypatch.setattr(deploy, "deploy", ok)
    code, rd = run_cli(tmp_path, "--no-twin", "--spec-in", str(p))
    assert code == build.EXIT_OK and got == {"slot": "t1", "dry_run": True}
    assert "workflow_id:     w1" in (rd / "trace.txt").read_text()

    def bad(workflow, slot, run_dir, dry_run=True):
        raise deploy.DeployError("rejected with key fak_secret_value_123456")
    monkeypatch.setattr(deploy, "deploy", bad)
    code, rd = run_cli(tmp_path, "--no-twin", "--spec-in", str(p))
    assert code == build.EXIT_DEPLOY
    blob = (rd / "trace.txt").read_text() + (rd / "trace.jsonl").read_text()
    assert "fak_secret" not in blob and "deploy failed" in blob

    # review fix round 1: a structural read-back difference (e.g. a stripped pre_action) fails the build (exit 5)
    def stripped(workflow, slot, run_dir, dry_run=True):
        return {"workflow_id": "w1", "agent_id": "a1", "version": 3, "export_path": str(run_dir) + "/x.json",
                "diff": ["node a_verify_1: pre_actions differ"], "llm_ok": True}
    monkeypatch.setattr(deploy, "deploy", stripped)
    code, rd = run_cli(tmp_path, "--no-twin", "--spec-in", str(p))
    assert code == build.EXIT_DEPLOY
    assert "structural difference" in (rd / "trace.txt").read_text()


def test_input_error_writes_trace(tmp_path, monkeypatch):
    # review fix round 1: exit 2 still leaves a trace under runs/_input_errors/
    monkeypatch.setattr(build.paths, "RUNS", tmp_path / "runs")
    code = build.main([str(tmp_path / "nope.md"), str(build.paths.ROOT / "kit" / "tools" / "openapi.json")])
    assert code == build.EXIT_INPUT
    traces = list((tmp_path / "runs" / "_input_errors").rglob("trace.txt"))
    assert traces and "not found" in traces[0].read_text()


def test_hard_cap_after_lint_still_deploys(tmp_path, fake_compile, monkeypatch):
    from builder import deploy
    p = tmp_path / "golden.json"
    p.write_text(json.dumps(GOLDEN_A))
    clock = {"t": 0.0}
    monkeypatch.setattr(budget_mod, "Budget", lambda: REAL_BUDGET(hard_s=1560, soft_s=1200, reserve_s=0,
                                                                  clock=lambda: clock["t"]))

    def ok(workflow, slot, run_dir, dry_run=True):
        return {"workflow_id": "w1", "agent_id": "a1", "version": 2, "export_path": str(run_dir) + "/x.json",
                "diff": [], "llm_ok": True}
    monkeypatch.setattr(deploy, "deploy", ok)
    from builder.compiler import lint as lint_mod
    real = lint_mod.lint

    def late_lint(*a, **kw):
        clock["t"] = 1600.0
        return real(*a, **kw)
    monkeypatch.setattr(lint_mod, "lint", late_lint)
    code, rd = run_cli(tmp_path, "--no-twin", "--spec-in", str(p))
    assert code == build.EXIT_OK
    assert "deploying the finished workflow anyway" in (rd / "trace.txt").read_text()


def test_budget_exceeded_exit_6(tmp_path, fake_compile, monkeypatch):
    monkeypatch.setattr(budget_mod, "Budget", lambda: REAL_BUDGET(hard_s=0, soft_s=0, reserve_s=0))
    fn, seen = fake_llm()
    llm.set_backend(fn)
    code, rd = run_cli(tmp_path, "--no-deploy")
    assert code == build.EXIT_BUDGET and seen["extract"] == []
    recs = trace_recs(rd)
    assert any(r["kind"] == "BUDGET" and "hard cap" in r["msg"] for r in recs)
    assert any(r["kind"] == "BUDGET" and "no published workflow" in r["msg"] for r in recs)


def test_budget_exit_exports_last_published(tmp_path, fake_compile, monkeypatch):
    from builder import deploy
    (tmp_path / "state").mkdir()
    key = deploy._safe_slot("t1")
    (tmp_path / "state" / (key + ".json")).write_text(json.dumps({key: {"workflow_id": "w9"}}))
    exported = {}
    monkeypatch.setattr(deploy, "export", lambda wid, path, **kw: exported.setdefault("wid", wid) and str(path))
    monkeypatch.setattr(budget_mod, "Budget", lambda: REAL_BUDGET(hard_s=0, soft_s=0, reserve_s=0))
    code, rd = run_cli(tmp_path, "--no-deploy")
    assert code == build.EXIT_BUDGET and exported == {"wid": "w9"}


def test_soft_cap_skips_optional_stages(tmp_path, fake_compile, monkeypatch):
    monkeypatch.setattr(budget_mod, "Budget", lambda: REAL_BUDGET(hard_s=1560, soft_s=0, reserve_s=0))
    fn, seen = fake_llm()
    llm.set_backend(fn)
    code, rd = run_cli(tmp_path, "--no-deploy", "--critic")
    assert code == build.EXIT_OK and seen["critic"] == 0
    s = [r for r in trace_recs(rd) if r["kind"] == "SUMMARY"][0]
    assert set(s["budget"]["skipped"]) >= {"critic", "twin"}


def test_internal_error_exit_1(tmp_path, fake_compile, monkeypatch):
    from builder.pipeline import segment
    monkeypatch.setattr(segment, "segment", lambda paths: (_ for _ in ()).throw(ValueError("kaput")))
    code, rd = run_cli(tmp_path, "--no-deploy", "--dev")
    assert code == build.EXIT_INTERNAL
    recs = trace_recs(rd)
    assert any(r["kind"] == "ERROR" and "kaput" in r["msg"] and "Traceback" in r["msg"] for r in recs)
    assert recs[-1]["kind"] == "SUMMARY" and recs[-1]["exit"] == 1


def test_unusable_tool_api_exit_2(tmp_path):
    doc = json.loads(API.read_text())
    doc["paths"] = {k: v for k, v in doc["paths"].items() if "close_call" not in k}
    p = tmp_path / "api.json"
    p.write_text(json.dumps(doc))
    code, rd = run_cli(tmp_path, "--no-deploy", inputs=[BRIEF_A, p])
    assert code == build.EXIT_INPUT
    assert any(r["kind"] == "ERROR" and "tool API" in r["msg"] for r in trace_recs(rd))


def test_twin_stage_is_advisory(tmp_path, fake_compile, monkeypatch):
    import harness.scenarios as sc
    p = tmp_path / "golden.json"
    p.write_text(json.dumps(GOLDEN_A))
    monkeypatch.setattr(sc, "generate", lambda spec, cat: [{"id": "s1"}])
    monkeypatch.setattr(sc, "run_suite", lambda scen, wf, cat, spec=None: {
        "passed": 0, "total": 1, "results": [{"id": "s1", "pass": False, "failed": ["x"]}]})
    code, rd = run_cli(tmp_path, "--no-deploy", "--spec-in", str(p))
    assert code == build.EXIT_OK and json.loads((rd / "twin_report.json").read_text())["total"] == 1
    recs = trace_recs(rd)
    assert any(r["kind"] == "TWIN" and r.get("where") == "LOCAL" for r in recs)
    monkeypatch.setattr(sc, "run_suite", lambda *a, **k: 1 / 0)
    code, rd = run_cli(tmp_path, "--no-deploy", "--spec-in", str(p))
    assert code == build.EXIT_OK and any("twin stage failed" in r["msg"] for r in trace_recs(rd))


def test_cli_subprocess_exit_codes(tmp_path):
    env = dict(os.environ)
    r = subprocess.run([sys.executable, str(ROOT / "builder" / "build.py"), "nope.md", str(API)], cwd=str(tmp_path),
                       capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 2 and "not found" in r.stdout
    r = subprocess.run([sys.executable, str(ROOT / "builder" / "build.py"), "--help"], capture_output=True,
                       text=True, timeout=60)
    assert r.returncode == 2 or "usage" in (r.stdout + r.stderr).lower()


def test_help_exits_zero_without_an_error_trace(capsys):
    with pytest.raises(SystemExit) as ei:
        build.main(["--help"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert "usage: build.py" in out and "ERROR" not in out
