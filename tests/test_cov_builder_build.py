"""Coverage round (builder/build.py): stage_spec branches with fake extract/validate/critic, input edge cases,
budget export helper and the input-error trace fallback. No LLM, no network."""
import argparse
import json
import pathlib
import shutil

import pytest

from builder import build, llm, trace
from builder.pipeline import critic, extract, validate as V

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRIEF_A = ROOT / "kit" / "briefs" / "brief-a.md"
API = ROOT / "kit" / "tools" / "openapi.json"
GOLDEN_A = json.loads((ROOT / "tests" / "golden" / "spec-a.json").read_text())


@pytest.fixture(autouse=True)
def _iso(monkeypatch, tmp_path):
    prev = llm.set_backend(lambda req: pytest.fail("unexpected LLM call: " + req["purpose"]))
    monkeypatch.setattr(build.paths, "STATE", tmp_path / "state")
    yield
    llm.set_backend(prev)
    trace.close()


class Bud:
    def __init__(self, allow=True):
        self.allow = allow
        self.asked = []

    def check(self, stage=""):
        pass

    def go(self, stage):
        self.asked.append(stage)
        return self.allow


def _args(**kw):
    d = dict(spec_in="", no_critic=False, critic=True, dev=False)
    d.update(kw)
    return argparse.Namespace(**d)


BDOC = {"text": "brief text", "examples": []}


def _events(tmp_path):
    trace.close()
    return [json.loads(x) for x in (tmp_path / "t" / "trace.jsonl").read_text().splitlines()]


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    """extract.extract returns drafts from a queue; validate errors come from spec['_errs']."""
    state = {"drafts": [], "extract_calls": [], "validated": []}

    def fake_extract(bdoc, catalog, bud, only=None, feedback=None, base=None):
        state["extract_calls"].append({"only": only, "feedback": feedback, "base": base})
        return state["drafts"].pop(0)

    def fake_validate(spec, catalog, brief_text=None, examples=None):
        state["validated"].append(spec)
        return {"spec": dict(spec), "errors": list(spec.get("_errs") or [])}
    monkeypatch.setattr(extract, "extract", fake_extract)
    monkeypatch.setattr(V, "validate", fake_validate)
    trace.init(tmp_path / "t", echo=False)
    return state


def test_errors_without_facets_skip_reextraction(fakes, tmp_path):
    fakes["drafts"] = [{"_errs": ["no pointer error"], "meta": {}}]
    spec, errs = build.stage_spec(_args(), BDOC, {}, Bud(), tmp_path)
    assert errs == ["no pointer error"] and len(fakes["extract_calls"]) == 1
    assert json.loads((tmp_path / "spec.draft.json").read_text())["_errs"] == ["no pointer error"]
    msgs = [r["msg"] for r in _events(tmp_path)]
    assert "error: no pointer error" in msgs and not any("re-extraction" in m for m in msgs)


def test_reextraction_with_more_errors_is_reverted(fakes, tmp_path):
    fakes["drafts"] = [{"_errs": ["/lines/ack: bad"], "v": 1},
                       {"_errs": ["/lines/ack: bad", "/lines/hold: bad"], "v": 2}]
    spec, errs = build.stage_spec(_args(), BDOC, {}, Bud(), tmp_path)
    assert errs == ["/lines/ack: bad"] and spec["v"] == 1
    second = fakes["extract_calls"][1]
    assert second["only"] == V.facets_with_errors(["/lines/ack: bad"]) and second["feedback"] == ["/lines/ack: bad"]
    assert any("re-extraction reverted (more errors)" in r["msg"] for r in _events(tmp_path))


def _critic(monkeypatch, rejected, residual=None):
    monkeypatch.setattr(critic, "critique", lambda bdoc, spec, cat, bud: {"issues": ["i"], "residual": residual or []})
    monkeypatch.setattr(critic, "apply_and_check", lambda spec, issues, check: (dict(spec), [], rejected))


NEED = [{"why": "no usable op", "pointer": "/lines/ack", "problem": "ack wording"}]


def test_critic_driven_reextraction_kept_when_value_changes(fakes, monkeypatch, tmp_path):
    _critic(monkeypatch, NEED + [{"why": "more errors", "pointer": "/x", "problem": "p2"}],
            residual=["not a dict", {"text": ""}, {"text": "rule from critic"}])
    fakes["drafts"] = [{"lines": {"ack": "old"}}, {"lines": {"ack": "new"}}]
    bud = Bud()
    spec, errs = build.stage_spec(_args(), BDOC, {}, bud, tmp_path)
    assert errs == [] and spec["lines"]["ack"] == "new"
    assert fakes["extract_calls"][1]["feedback"] == NEED and fakes["extract_calls"][1]["base"] == {"lines": {"ack": "old"}}
    assert spec["meta"]["residual_rules"] == [{"text": "rule from critic", "class": "flow", "bound_to": "critic"}]
    assert bud.asked == ["critic", "reextract"]
    ev = _events(tmp_path)
    assert any("critic-driven re-extraction" in r["msg"] for r in ev)
    assert any(r["msg"].startswith("rejected: p2") and r.get("why") == "more errors" for r in ev)


def test_critic_driven_reextraction_ignored_when_value_unchanged(fakes, monkeypatch, tmp_path):
    _critic(monkeypatch, NEED)
    fakes["drafts"] = [{"lines": {"ack": "same"}}, {"lines": {"ack": "same"}, "other": 1}]
    spec, errs = build.stage_spec(_args(), BDOC, {}, Bud(), tmp_path)
    assert errs == [] and "other" not in spec
    assert any("critic re-extraction ignored" in r["msg"] for r in _events(tmp_path))


def test_critic_driven_reextraction_with_errors_reverted(fakes, monkeypatch, tmp_path):
    _critic(monkeypatch, NEED)
    fakes["drafts"] = [{"lines": {"ack": "a"}}, {"lines": {"ack": "b"}, "_errs": ["/lines/ack: worse"]}]
    spec, errs = build.stage_spec(_args(), BDOC, {}, Bud(), tmp_path)
    assert errs == [] and spec["lines"]["ack"] == "a"
    assert any("critic re-extraction reverted" in r["msg"] for r in _events(tmp_path))


def test_critic_reextraction_needs_a_facet_and_budget(fakes, monkeypatch, tmp_path):
    _critic(monkeypatch, [{"why": "no usable op", "pointer": "no-pointer", "problem": "p"}])
    fakes["drafts"] = [{"lines": {"ack": "a"}}]
    spec, errs = build.stage_spec(_args(), BDOC, {}, Bud(), tmp_path)
    assert errs == [] and len(fakes["extract_calls"]) == 1          # no facet -> no second extraction
    _critic(monkeypatch, NEED)
    fakes["drafts"] = [{"lines": {"ack": "a"}}]
    bud = Bud(allow=True)
    bud.go = lambda stage: stage == "critic"                         # no budget for a re-extraction
    spec, errs = build.stage_spec(_args(), BDOC, {}, bud, tmp_path)
    assert errs == [] and len(fakes["extract_calls"]) == 2


def test_critic_result_with_validation_errors_is_reverted(fakes, monkeypatch, tmp_path):
    monkeypatch.setattr(critic, "critique", lambda *a: {"issues": [], "residual": [{"text": "r"}]})
    monkeypatch.setattr(critic, "apply_and_check",
                        lambda spec, issues, check: (dict(spec, _errs=["/x: broken by critic"]), [{"problem": "p"}], []))
    fakes["drafts"] = [{"lines": {"ack": "a"}}]
    spec, errs = build.stage_spec(_args(), BDOC, {}, Bud(), tmp_path)
    assert errs == [] and spec == {"lines": {"ack": "a"}}               # pre-critic Spec, no critic residuals
    assert any("critic result reverted (validation errors)" in r["msg"] for r in _events(tmp_path))


def test_count_errors_helpers(monkeypatch):
    monkeypatch.setattr(V, "validate", lambda spec, cat, brief_text=None, examples=None: {
        "spec": spec, "errors": ["e1", "e2"] if spec.get("bad") else []})
    assert build._count_errors({}, "t")({"bad": 1}) == 2
    assert build._count_errors_list({}, "t")({"bad": 1}) == ["e1", "e2"]
    assert build._count_errors_list({}, "t")({}) == []


def test_at_json_pointer():
    spec = {"a": {"b/c": [10, {"d~e": "x"}]}}
    assert build._at(spec, "/a/b~1c/1/d~0e") == '"x"'
    assert build._at(spec, "/a/b~1c/0") == "10"
    assert build._at(spec, "/a/missing") is None
    assert build._at(spec, "/a/b~1c/7") is None
    assert build._at(spec, "") == json.dumps(spec, sort_keys=True)


# ----------------------------------------------------------------------------------------------- budget export

def test_export_last_published_without_workflow_id(tmp_path, monkeypatch):
    from builder import deploy
    st = tmp_path / "state"
    st.mkdir()
    (st / "s1.json").write_text(json.dumps({"s1": {"agent_id": "a"}}))
    monkeypatch.setattr(deploy, "export", lambda *a, **k: pytest.fail("no export without an id"))
    assert build._export_last_published("s1", tmp_path / "run") is None
    (st / "s1.json").write_text(json.dumps(["not", "a", "dict"]))
    assert build._export_last_published("s1", tmp_path / "run") is None


def test_export_last_published_failure_is_a_warning(tmp_path, monkeypatch):
    from builder import deploy
    st = tmp_path / "state"
    st.mkdir()
    (st / "s1.json").write_text(json.dumps({"s1": {"workflow_id": "w1"}}))

    def boom(wid, path, freya=None):
        raise deploy.DeployError("export failed: 502")
    monkeypatch.setattr(deploy, "export", boom)
    trace.init(tmp_path / "t", echo=False)
    assert build._export_last_published("s1", tmp_path / "run") is None
    assert any(r["kind"] == "WARN" and "export of last published failed: export failed: 502" in r["msg"]
               for r in _events(tmp_path))


# ----------------------------------------------------------------------------------------------- _run inputs

@pytest.fixture
def fake_compile(monkeypatch):
    from builder.compiler import graph, lint
    monkeypatch.setattr(graph, "compile_workflow", lambda spec, cat, flags=None: (
        {"initial_node": "s_open", "nodes": {"s_open": {}}}, {"listen": {}}))
    monkeypatch.setattr(lint, "lint", lambda wf, cat, spec, w: [])


def _spec_in(tmp_path):
    p = tmp_path / "golden.json"
    p.write_text(json.dumps(GOLDEN_A))
    return p


def _main(tmp_path, inputs, *extra):
    argv = [str(p) for p in inputs] + ["--out-dir", str(tmp_path / "runs"), "--slot", "t1"] + list(extra)
    code = build.main(argv)
    runs = sorted((tmp_path / "runs" / "t1").glob("r*"))
    recs = [json.loads(x) for x in (runs[-1] / "trace.jsonl").read_text().splitlines()] if runs else []
    return code, recs


def test_brief_directory_input(tmp_path, fake_compile):
    d = tmp_path / "briefs"
    d.mkdir()
    shutil.copy(BRIEF_A, d / "brief.md")
    code, recs = _main(tmp_path, [d, API], "--no-deploy", "--no-twin", "--spec-in", str(_spec_in(tmp_path)))
    assert code == build.EXIT_OK
    assert any(r["kind"] == "INPUT" and r.get("role") == "brief_dir" for r in recs)
    assert any(r["kind"] == "SEGMENT" and r["msg"].endswith("brief.md") for r in recs)


def test_unreadable_brief_exit_2(tmp_path, fake_compile, monkeypatch):
    from builder.pipeline import segment

    def boom(paths_):
        raise OSError("permission denied")
    monkeypatch.setattr(segment, "segment", boom)
    code, recs = _main(tmp_path, [BRIEF_A, API], "--no-deploy")
    assert code == build.EXIT_INPUT
    assert any(r["kind"] == "ERROR" and "cannot read brief: permission denied" in r["msg"] for r in recs)


def test_empty_brief_text_exit_2(tmp_path, fake_compile, monkeypatch):
    from builder.pipeline import segment
    monkeypatch.setattr(segment, "segment", lambda paths_: {"docs": [{"path": "x"}], "text": "  \n"})
    code, recs = _main(tmp_path, [BRIEF_A, API], "--no-deploy")
    assert code == build.EXIT_INPUT and any(r["msg"] == "brief input is empty" for r in recs)


def test_twin_all_passing_has_no_warning(tmp_path, fake_compile, monkeypatch):
    import harness.scenarios as sc
    monkeypatch.setattr(sc, "generate", lambda spec, cat: [{"id": "s1"}])
    monkeypatch.setattr(sc, "run_suite", lambda scen, wf, cat, spec=None: {
        "passed": 1, "total": 1, "results": [{"id": "s1", "pass": True}]})
    code, recs = _main(tmp_path, [BRIEF_A, API], "--no-deploy", "--spec-in", str(_spec_in(tmp_path)))
    assert code == build.EXIT_OK
    assert any(r["kind"] == "TWIN" and r["msg"] == "PASS s1" for r in recs)
    assert not any("twin smoke scenarios failing" in r["msg"] for r in recs)
    assert [r for r in recs if r["kind"] == "SUMMARY"][0]["twin"] == "1/1"


def test_input_error_trace_falls_back_to_stdout(tmp_path, monkeypatch, capsys):
    blocker = tmp_path / "runs_is_a_file"
    blocker.write_text("x")
    monkeypatch.setattr(build.paths, "RUNS", blocker)                # mkdir under a file fails
    code = build.main([str(tmp_path / "missing.md"), str(API)])
    assert code == build.EXIT_INPUT
    out = capsys.readouterr().out
    assert "ERROR builder.build.main | input: input file(s) not found" in out


def test_tool_api_found_inside_a_brief_folder(tmp_path):
    d = tmp_path / "material"
    (d / "sub").mkdir(parents=True)
    shutil.copy(BRIEF_A, d / "brief.md")
    shutil.copy(API, d / "sub" / "tools.json")
    (d / "notes.json").write_text('{"not": "an api"}')
    ns = build.parse_args([str(d)])
    assert ns.api == str(d / "sub" / "tools.json") and ns.briefs == [str(d)]


def test_unusable_out_dir_is_an_input_error(tmp_path):
    blocker = tmp_path / "out_is_a_file"
    blocker.write_text("x")
    code = build.main([str(BRIEF_A), str(API), "--out-dir", str(blocker), "--slot", "t1", "--no-deploy"])
    assert code == build.EXIT_INPUT
