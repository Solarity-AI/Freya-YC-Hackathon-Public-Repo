"""PUB-11 partial write chain (official sims 2026-10-11, call 87b5c862): a transient bank 5xx on close_call lost the
close. close_call is idempotent by contract (a 5xx records nothing; a repeated close answers 'already closed'), so the
close nodes may re-send on HTTP >= 500 (maxRetries 2). Every other write stays at maxRetries 0, and lint I3 now reads
'non-idempotent writes maxRetries 0'."""
import copy
import json
import pathlib

import pytest

from builder import openapi_model as om
from builder.compiler import graph, lint
from harness import scenarios as sc

ROOT = pathlib.Path(__file__).resolve().parent.parent
STUB_CODE = "import json\ntry:\n    vars['nx'] = 's_safe'\nexcept Exception:\n    vars['nx'] = 's_safe'\n"


@pytest.fixture(scope="module")
def cat():
    return om.load(ROOT / "kit" / "tools" / "openapi.json")


def _golden(name):
    return json.loads((ROOT / "tests" / "golden" / name).read_text())


def _cfg(wf, key):
    return wf["nodes"][key]["pre_actions"][0]["config"]


def _tool(wf, key):
    return wf["nodes"][key]["pre_actions"][0]["function"]["name"]


@pytest.mark.parametrize("name", ["spec-a.json", "spec-ab.json"])
def test_close_nodes_retry_other_writes_never(cat, name):
    wf, w = graph.compile_workflow(_golden(name), cat, code=STUB_CODE)
    api = w["api"]
    for k in (api["close_r"], api["close_n"]):
        assert _tool(wf, k) == "close_call" and _cfg(wf, k)["maxRetries"] == 2, k
    seen = set()
    for k, n in wf["nodes"].items():
        if n.get("node_type") != "api_request":
            continue
        t = _tool(wf, k)
        if cat["tools"][t]["write"] and t != "close_call":
            seen.add(t)
            assert _cfg(wf, k)["maxRetries"] == 0, (k, t)
    assert {"create_promise", "add_note"} <= seen or name == "spec-a.json"
    assert "create_promise" in seen


def _lint_rules(cat, spec, wf, w):
    return {f["rule"] for f in lint.lint(wf, cat, spec, w) if f["level"] == "error"}


def test_lint_i3_non_idempotent_writes_only(cat):
    spec = _golden("spec-ab.json")
    wf, w = graph.compile_workflow(spec, cat, code=STUB_CODE)
    assert "api_max_retries" not in _lint_rules(cat, spec, wf, w)          # close at 2 is clean
    note = next(k for k in wf["nodes"] if wf["nodes"][k].get("node_type") == "api_request"
                and _tool(wf, k) == "add_note")
    for key, bad in (("a_promise_1_1", 1), ("a_promise_1_1", 2), (note, 1), (w["api"]["close_n"], 3),
                     (w["api"]["close_r"], -1), (w["api"]["close_r"], None)):
        wf2 = copy.deepcopy(wf)
        _cfg(wf2, key)["maxRetries"] = bad
        assert "api_max_retries" in _lint_rules(cat, spec, wf2, w), (key, bad)
    wf2 = copy.deepcopy(wf)
    _cfg(wf2, w["api"]["close_r"])["maxRetries"] = 0                        # 0..2 allowed for the close
    _cfg(wf2, w["api"]["close_n"])["maxRetries"] = 1
    assert "api_max_retries" not in _lint_rules(cat, spec, wf2, w)


def test_max_retries_helper():
    assert graph.max_retries("close_call", {"write": True}) == 2
    assert graph.max_retries("create_promise", {"write": True}) == 0
    assert graph.max_retries("add_note", {"write": True, "max_retries": 3}) == 0
    assert graph.max_retries("get_account", {"write": False, "max_retries": 1}) == 1
    assert graph.max_retries("verify_identity", {"write": False}) == 0


# ---------------------------------------------------------------- twin: the compiled workflow re-sends the close
def _scenario(faults):
    s = copy.deepcopy(next(x for x in sc.load(ROOT / "tests" / "scenarios") if x["id"] == "AB-PUB-11"))
    s["faults"] = faults
    return s


def _closes(r):
    return [e for e in r["events"] if e.get("event") == "function_call_start" and e.get("function") == "close_call"]


@pytest.fixture(scope="module")
def wf_ab():
    try:
        wf, _ = graph.compile_workflow(_golden("spec-ab.json"), json.loads(
            (ROOT / "tests" / "fixtures" / "catalog-kit.json").read_text()))
    except Exception as e:                                       # noqa: BLE001
        pytest.skip("compile_workflow failed: %s" % e)
    return wf


def test_transient_close_5xx_is_retried(wf_ab):
    catalog = json.loads((ROOT / "tests" / "fixtures" / "catalog-kit.json").read_text())
    spec = _golden("spec-ab.json")
    r = sc.run(_scenario([{"tool": "close_call", "fail_first_n": 1}]), wf_ab, catalog, spec)
    assert r["pass"], r["failed"]
    assert [e["attempt"] for e in _closes(r)] == [1, 2]
    # without the retry the same fault loses the close (the official-run failure)
    wf0 = copy.deepcopy(wf_ab)
    for k, n in wf0["nodes"].items():
        if n.get("node_type") == "api_request" and _tool(wf0, k) == "close_call":
            _cfg(wf0, k)["maxRetries"] = 0
    assert not sc.run(_scenario([{"tool": "close_call", "fail_first_n": 1}]), wf0, catalog, spec)["pass"]


def test_close_retry_never_double_closes(wf_ab):
    catalog = json.loads((ROOT / "tests" / "fixtures" / "catalog-kit.json").read_text())
    r = sc.run(_scenario([]), wf_ab, catalog, _golden("spec-ab.json"))
    assert r["pass"], r["failed"]
    assert [e["attempt"] for e in _closes(r)] == [1]
