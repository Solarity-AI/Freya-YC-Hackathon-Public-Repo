"""tools/gonogo.py: a run is GO only when it exited 0, deployed, is lint-clean, passed the twin and the smoke turn,
and every situation value sits in an enum that the hidden tool API file itself declares."""
import importlib.util
import io
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("tools_gonogo", ROOT / "tools" / "gonogo.py")
gonogo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gonogo)

API = {"openapi": "3.0.0", "paths": {"/close_call": {"post": {"requestBody": {"content": {"application/json": {
    "schema": {"$ref": "#/components/schemas/Close"}}}}}}},
       "components": {"schemas": {"Close": {"type": "object", "properties": {
           "outcome": {"type": "string", "enum": ["promise", "no_promise", "not_reached"]},
           "queue": {"type": "string", "enum": ["general", "hardship"]}}}}}}


def make_run(tmp_path, summary=None, situations=None, enums=None):
    rd = tmp_path / "runs" / "hidden-1-abcdef12-20261011T170500" / "r20261011T170501Z"
    rd.mkdir(parents=True)
    summ = {"kind": "SUMMARY", "exit": 0, "deployed": True, "lint_errors": 0, "twin": "4/4", "smoke": "ok",
            "build_s": 81.2, "workflow_id": "w1", "agent_id": "a1", "nodes": 28}
    summ.update(summary or {})
    recs = [{"kind": "START", "msg": "build"}, {"kind": "FREYA", "msg": "smoke chat turn ok", "reply": "Hello, Ana?"},
            summ]
    (rd / "trace.jsonl").write_text("\n".join(json.dumps(r) for r in recs) + "\ngarbage\n")
    (rd / "spec.json").write_text(json.dumps({"opening": {"line": "Hello, this is <self>."}, "situations": situations or {
        "S_PROMISE": {"outcome": "promise", "reason": "", "queue": ""},
        "S_TRANSFER": {"outcome": "no_promise", "reason": "hardship", "queue": "hardship"}}}))
    (rd / "catalog.json").write_text(json.dumps({"enums": enums if enums is not None else {
        "outcome": ["promise", "no_promise", "not_reached"], "queue": ["general", "hardship"], "close_reason": []}}))
    (tmp_path / "api.json").write_text(json.dumps(API))
    (tmp_path / "trace.log").write_text("[+0.0s] START builder.build._run | build | argv=[] run_dir=%s model_default=m\n"
                                        % rd)
    return rd


def run(argv):
    out = io.StringIO()
    return gonogo.main(argv, out=out), out.getvalue()


def test_go(tmp_path):
    rd = make_run(tmp_path)
    code, out = run([str(rd), str(tmp_path / "api.json")])
    assert code == 0 and out.rstrip().endswith("gonogo: GO")
    assert "smoke reply: Hello, Ana?" in out and "opening line: Hello, this is <self>." in out
    assert "outcome values no situation uses: not_reached" in out and "queue values no situation uses: general" in out
    assert "reason: no enum in the tool API (used: hardship)" in out and "build time: 81.2 s" in out


def test_go_from_the_log_and_yaml_api(tmp_path):
    make_run(tmp_path)
    import yaml
    (tmp_path / "api.yaml").write_text(yaml.safe_dump(API))
    code, out = run(["--log", str(tmp_path / "trace.log"), str(tmp_path / "api.yaml")])
    assert code == 0, out


@pytest.mark.parametrize("summary, needle", [
    ({"exit": 4}, "build exit 4"),
    ({"deployed": False}, "deployed=False"),
    ({"lint_errors": 2}, "lint errors: 2"),
    ({"twin": "3/4"}, "twin: 3/4"),
    ({"twin": "0/0"}, "twin: 0/0"),
    ({"smoke": "warn: chat turn HTTP 0: TimeoutError"}, "smoke chat turn: warn"),
])
def test_no_go_on_run_results(tmp_path, summary, needle):
    rd = make_run(tmp_path, summary=summary)
    code, out = run([str(rd), str(tmp_path / "api.json")])
    assert code == 1 and needle in out and "NO-GO (1)" in out


def test_no_go_on_enums(tmp_path):
    rd = make_run(tmp_path, situations={"S_X": {"outcome": "callback_set", "queue": "general"}},
                  enums={"outcome": ["promise", "no_promise", "not_reached"], "queue": ["general", "vip"]})
    code, out = run([str(rd), str(tmp_path / "api.json")])
    assert code == 1 and "situation outcome value(s) ['callback_set'] not in the tool API enum" in out
    assert "bound queue enum ['general', 'vip'] is not an enum of the tool API file" in out


@pytest.mark.parametrize("argv", [["only-one-path"], ["--log", "missing.log", "api.json"], ["a", "b", "c"]])
def test_unreadable_input(tmp_path, argv):
    assert run(argv)[0] == 2


def test_log_without_run_dir_and_help(tmp_path):
    (tmp_path / "x.log").write_text("[+0.0s] START m | build | nothing\n")
    code, out = run(["--log", str(tmp_path / "x.log"), "api.json"])
    assert code == 2 and "names no run_dir" in out
    assert run(["--help"])[0] == 0 and run([])[0] == 2
    (tmp_path / "y.log").write_text("[+0.0s] START m | build | run_dir=/x/r1\n")
    assert gonogo.run_dir_from_log(tmp_path / "y.log") == pathlib.Path("/x/r1")
