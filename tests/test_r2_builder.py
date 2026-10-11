"""Quality round (2026-10-11): regression tests for the builder / harness findings (BUILD SPEED addendum, deploy
read-back, smoke turn, chat transport, facet split, validation clean-ups)."""
import argparse
import contextlib
import copy
import json
import pathlib

import pytest

from builder import build, llm, trace
from builder.pipeline import extract, validate as V
from harness import chat_e2e, persona as hp

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRIEF_A = ROOT / "kit" / "briefs" / "brief-a.md"
API = ROOT / "kit" / "tools" / "openapi.json"
GOLDEN_A = json.loads((ROOT / "tests" / "golden" / "spec-a.json").read_text())


def _events(run_dir):
    return [json.loads(x) for x in (pathlib.Path(run_dir) / "trace.jsonl").read_text().splitlines()]


@pytest.fixture(autouse=True)
def _iso(monkeypatch, tmp_path):
    prev = llm.set_backend(lambda req: pytest.fail("unexpected LLM call: " + req["purpose"]))
    monkeypatch.setattr(build.paths, "STATE", tmp_path / "state")
    monkeypatch.setattr(build.paths, "RUNS", tmp_path / "runs")
    yield
    llm.set_backend(prev)
    trace.close()


# ======================================================================= facet split (BUILD SPEED: F5 was the wave)
def test_facets_cover_every_top_level_spec_key_once():
    keys = [k for f in extract.FACETS.values() for k in f] + \
        [k for f in extract.FACET_OPTIONAL_KEYS.values() for k in f]
    assert len(keys) == len(set(keys))
    # dated: each facet returns its own dated entries next to its values; code merges them (extract.py)
    assert set(V.schema()["properties"]) - set(keys) == {"meta", "spec_version", "dated"}
    assert extract.FACETS["F5"] == ["intents"] and "situations" in extract.FACETS["F7"]
    for f in extract.FACETS:
        assert extract.load_prompt(f + ".md").startswith("Facet " + f)


def test_undefined_situation_reextracts_both_owners():
    assert V.facets_with_errors(["/intents/2/action/situation: 'S_X' is used but not defined"]) == ["F5", "F7"]


# ======================================================================= model / effort per facet (item 4)
def test_facet_overrides_from_the_environment(monkeypatch):
    monkeypatch.setenv("BUILDER_FACET_MODEL", "F3=claude-sonnet-5-5, junk ,F9=")
    monkeypatch.setenv("BUILDER_FACET_EFFORT", "F1=medium,F2=turbo")
    assert llm.facet_overrides() == {"model": {"F3": "claude-sonnet-5-5"},
                                     "effort": {"F1": "medium", "F5": "medium"}}
    assert llm.choice("F3") == ("claude-sonnet-5-5", llm.DEFAULT_EFFORT)
    assert llm.choice("F1") == (llm.DEFAULT_MODEL, "medium")
    assert llm.choice("F1", model="m", effort="low") == ("m", "low")
    call = extract.facet_call("F3", {"numbered": "", "docs": []}, {}, None)
    assert call["model"] == "claude-sonnet-5-5" and call["effort"] == llm.DEFAULT_EFFORT


# ======================================================================= critic re-extraction keeps only flagged values
def test_copy_pointers_takes_only_the_flagged_values():
    src = {"a": {"b": [1, 2, {"c": "new"}], "x": "src-x"}, "k": "src-k"}
    dst = {"a": {"b": [1, 2, {"c": "old"}], "x": "dst-x"}, "k": "dst-k"}
    out = build._copy_pointers(src, dst, ["/a/b/2/c", "/missing/y", "", "/a/b/9"])
    assert out == {"a": {"b": [1, 2, {"c": "new"}], "x": "dst-x"}, "k": "dst-k"}
    assert dst["a"]["b"][2]["c"] == "old"               # the input is not changed


# ======================================================================= build CLI: stages, warnings, compile, out-dir
def test_stages_record_each_stage_once_per_start(tmp_path):
    trace.init(tmp_path / "t", echo=False)
    summ = {}
    st = build.Stages(summ)
    st.start("a")
    st.start("b")
    st.start("a")
    st.stop()
    st.stop()
    trace.close()
    assert set(summ["stages"]) == {"a", "b"}
    assert [r["msg"] for r in _events(tmp_path / "t") if r["kind"] == "STAGE"] == ["a", "b", "a"]


def _args(**kw):
    d = dict(spec_in="", no_critic=False, critic=False, dev=False)
    d.update(kw)
    return argparse.Namespace(**d)


def test_validation_warnings_are_traced(tmp_path, monkeypatch):
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(GOLDEN_A))
    monkeypatch.setattr(V, "validate", lambda *a, **k: {"spec": GOLDEN_A, "errors": [], "warnings": ["w-one"],
                                                         "defaults_applied": []})
    trace.init(tmp_path / "t", echo=False)
    bdoc = {"text": "x", "examples": []}
    build.stage_spec(_args(spec_in=str(p)), bdoc, {}, None, tmp_path)
    trace.close()
    assert any(r["kind"] == "VALIDATE" and r["msg"] == "warning: w-one" for r in _events(tmp_path / "t"))


def test_compile_failure_is_a_traced_lint_exit(tmp_path, monkeypatch):
    from builder.compiler import graph
    p = tmp_path / "golden.json"
    p.write_text(json.dumps(GOLDEN_A))

    def boom(*a, **k):
        raise ValueError("snippet is 999999 bytes")
    monkeypatch.setattr(graph, "compile_workflow", boom)
    code = build.main([str(BRIEF_A), str(API), "--out-dir", str(tmp_path / "runs"), "--slot", "s", "--no-deploy",
                       "--no-twin", "--spec-in", str(p)])
    assert code == build.EXIT_LINT
    rd = sorted((tmp_path / "runs" / "s").glob("r*"))[-1]
    assert any(r["kind"] == "ERROR" and "compile failed" in r["msg"] for r in _events(rd))


def test_run_folder_that_cannot_be_made_is_an_input_error(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "s").write_text("a file where the slot folder should go")
    code = build.main([str(BRIEF_A), str(API), "--out-dir", str(out), "--slot", "s", "--no-deploy"])
    assert code == build.EXIT_INPUT
    assert list((tmp_path / "runs" / "_input_errors").rglob("trace.txt"))


# ======================================================================= smoke turn (item 3)
class FakeChat:
    def __init__(self, reply="Hello, I am a digital assistant. Am I speaking with you?", exc=None, call_id="c1",
                 lock_exc=None):
        self.reply, self.exc, self.call_id, self.lock_exc = reply, exc, call_id, lock_exc
        self.sent, self.ended = [], []

    @contextlib.contextmanager
    def chat_lock(self, wait_s=None):
        if self.lock_exc:
            raise self.lock_exc
        yield

    def chat_turn(self, wid, msg, variables, call_id, timeout_s):
        self.sent.append((wid, msg, variables, timeout_s))
        if self.exc:
            raise self.exc
        return self.reply, self.call_id

    def end_chat(self, call_id):
        self.ended.append(call_id)


def test_smoke_turn_ok_ends_the_call(tmp_path):
    trace.init(tmp_path / "t", echo=False)
    fc = FakeChat()
    assert build.smoke_turn("w1", GOLDEN_A, chat=fc) == "ok"
    assert fc.sent == [("w1", "Hello?", {}, build.SMOKE_TIMEOUT_S)] and fc.ended == ["c1"]


@pytest.mark.parametrize("fc, want", [
    (FakeChat(reply=""), "warn: reply"),
    (FakeChat(reply=GOLDEN_A["lines"]["clarify"] + " Am I speaking with you?"), "warn: reply"),
    (FakeChat(exc=chat_e2e.ChatTransportError("chat turn HTTP 0: timeout")), "warn: chat turn HTTP 0"),
    (FakeChat(lock_exc=chat_e2e.ChatError("another live chat holds x")), "warn: another live chat"),
])
def test_smoke_turn_problems_are_advisory_warnings(tmp_path, fc, want):
    trace.init(tmp_path / "t", echo=False)
    assert build.smoke_turn("w1", GOLDEN_A, chat=fc).startswith(want)
    trace.close()
    assert any(r["kind"] == "WARN" and "smoke" in r["msg"] for r in _events(tmp_path / "t"))


def test_deployed_build_runs_the_smoke_turn_unless_switched_off(tmp_path, monkeypatch):
    from builder import deploy
    p = tmp_path / "golden.json"
    p.write_text(json.dumps(GOLDEN_A))
    monkeypatch.setenv("FREYA_API_KEY", "test-not-a-key")
    monkeypatch.setattr(deploy, "deploy", lambda wf, slot, rd, dry_run=True: {
        "workflow_id": "w1", "agent_id": "a1", "version": 2, "export_path": "x", "diff": [], "llm_ok": True})
    seen = []
    monkeypatch.setattr(build, "smoke_turn", lambda wid, spec: seen.append(wid) or "ok")
    argv = [str(BRIEF_A), str(API), "--out-dir", str(tmp_path / "runs"), "--slot", "s", "--no-twin", "--spec-in", str(p)]
    assert build.main(argv) == build.EXIT_OK and seen == ["w1"]
    rd = sorted((tmp_path / "runs" / "s").glob("r*"))[-1]
    summ = [r for r in _events(rd) if r["kind"] == "SUMMARY"][0]
    assert summ["smoke"] == "ok" and "smoke" in summ["stages"]
    assert build.main(argv + ["--no-smoke"]) == build.EXIT_OK and seen == ["w1"]


# ======================================================================= chat transport (slow platform)
def test_recover_reply_polls_until_the_reply_is_stored(monkeypatch):
    stored = [
        [{"role": "user", "message": "Hello?"}],
        [{"role": "user", "message": "Hello?"}],
        [{"role": "user", "message": "Hello?"}, {"role": "assistant", "message": "Hi there."}],
    ]
    calls, sleeps = [], []

    def get_call(cid):
        calls.append(cid)
        if len(calls) == 2:
            raise chat_e2e.ChatError("get call HTTP 502")
        return {"messages": stored[min(len(calls) - 1, 2)]}
    monkeypatch.setattr(chat_e2e, "get_call", get_call)
    assert chat_e2e._recover_reply("c1", poll_s=4, max_s=60, sleep=sleeps.append) == "Hi there."
    assert len(calls) == 3 and sleeps == [4, 4, 4]


def test_recover_reply_gives_up_after_the_window(monkeypatch):
    monkeypatch.setattr(chat_e2e, "get_call", lambda cid: {"messages": [{"role": "user", "message": "x"}]})
    sleeps = []
    assert chat_e2e._recover_reply("c1", poll_s=5, max_s=20, sleep=sleeps.append) is None
    assert sleeps == [5, 5, 5, 5]


def test_chat_lock_is_exclusive_across_holders(tmp_path):
    path = tmp_path / "lock"
    with chat_e2e.chat_lock(path=path):
        with pytest.raises(chat_e2e.ChatError, match="another live chat"):
            with chat_e2e.chat_lock(wait_s=0, path=path):
                pass                                                    # pragma: no cover
    with chat_e2e.chat_lock(wait_s=0, path=path):
        pass


def test_chat_lock_waits_then_gives_up(tmp_path, monkeypatch):
    import fcntl
    path = tmp_path / "lock"
    times = iter([0.0, 0.5, 2.0, 2.0])
    monkeypatch.setattr(chat_e2e.time, "time", lambda: next(times))
    monkeypatch.setattr(chat_e2e.time, "sleep", lambda s: None)
    with open(path, "a+") as other:
        fcntl.flock(other.fileno(), fcntl.LOCK_EX)
        with pytest.raises(chat_e2e.ChatError):
            with chat_e2e.chat_lock(wait_s=1, path=path):
                pass                                                    # pragma: no cover


def test_persona_retries_once_after_a_timeout(monkeypatch):
    replies = iter([TimeoutError("slow"), "Yes, speaking."])

    async def ask(*a):
        r = next(replies)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(hp, "_ask", ask)
    assert hp.next_utterance("p", [("agent", "hi")], timeout_s=1) == "Yes, speaking."


# ======================================================================= validation clean-ups
def test_sentence_forbidden_offers_are_dropped(catalog_kit):
    sp = copy.deepcopy(GOLDEN_A)
    sp["negotiation"]["forbidden_offers"] = ["discount", "any term that is not in this brief",
                                             "a much longer description of an offer"]
    r = V.validate(sp, catalog_kit)
    assert r["spec"]["negotiation"]["forbidden_offers"] == ["discount"]
    assert any("forbidden_offers: sentences dropped" in f for f in r["fixes"])
    assert V._offer_is_sentence("") and not V._offer_is_sentence("fee waiver")


def test_nth_business_day_without_any_business_day_is_no_date():
    import datetime
    from harness import scenarios as sc
    today = datetime.date(2026, 1, 7)
    cal = {"business_weekdays": [0], "holidays": [(datetime.date(2026, 1, 12) + datetime.timedelta(weeks=w)).isoformat()
                                                  for w in range(60)]}
    assert sc._eval_simple_date({"kind": "nth_business_day_after_today", "n": 2}, cal, today) is None


def test_copy_pointers_with_repeated_segment_names():
    src = {"a": {"a": "new"}}
    assert build._copy_pointers(src, {"a": {"a": "old", "b": 1}}, ["/a/a"]) == {"a": {"a": "new", "b": 1}}


def test_intents_facet_runs_at_the_measured_effort_unless_overridden(monkeypatch):
    monkeypatch.delenv("BUILDER_FACET_EFFORT", raising=False)
    assert llm.choice("F5")[1] == "medium" and llm.choice("F1")[1] == llm.DEFAULT_EFFORT
    monkeypatch.setenv("BUILDER_FACET_EFFORT", "F5=high")
    assert llm.choice("F5")[1] == "high"
