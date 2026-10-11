"""Coverage round (builder I/O): deploy.py error paths and llm.py transport / parsing paths. Fully offline."""
import asyncio
import copy
import json
import pathlib

import pytest

from builder import deploy, llm, trace

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["n"],
          "properties": {"n": {"type": "integer", "minimum": 1}}}


@pytest.fixture(autouse=True)
def _iso():
    prev = llm.set_backend(None)
    trace.close()
    yield
    trace.close()
    llm.set_backend(prev)


# ================================================================================================ deploy

WF = {"initial_node": "s_open", "nodes": {"s_open": {"name": "s_open", "node_type": "conversation",
                                                     "on_enter": {"type": "tts", "text": "Hi"}, "transitions": []}}}


class MiniFreya:
    """Kit-shaped fake: save_workflow / api / export_workflow / validate_workflow."""
    AGENT_LLM = None

    def __init__(self, ids=None, save_exc=None, versions=None, api_exc=None, stored=None):
        self.ids = {"workflow_id": "wf_9", "agent_id": "ag_9", "version": 1} if ids is None else ids
        self.save_exc = save_exc
        self.versions = [{"id": "v1", "versionNumber": 1, "isPublished": True}] if versions is None else versions
        self.api_exc = api_exc
        self.stored = copy.deepcopy(WF) if stored is None else stored
        self.saves = 0
        self.exports = []

    def workspace_id(self):
        return "ws"

    def validate_workflow(self, name, workflow):
        return {"valid": True, "dryRun": True}

    def save_workflow(self, slot, workflow, state_file=None):
        self.saves += 1
        if self.save_exc:
            raise self.save_exc
        pathlib.Path(state_file).write_text(json.dumps({slot: self.ids}))
        return dict(self.ids)

    def api(self, method, path, body=None, **params):
        if self.api_exc:
            raise self.api_exc
        if path.startswith("/api/v2/versions/workflow/"):
            return {"versions": self.versions}
        return {"workflow": {"workflow": self.stored}}

    def export_workflow(self, wid, path):
        self.exports.append(wid)
        pathlib.Path(path).write_text(json.dumps({"workflow_id": wid, "workflow": self.stored}))


def _deploy(fake, tmp_path, **kw):
    return deploy.deploy(copy.deepcopy(WF), "slot-x", tmp_path / "run", freya=fake, state_dir=tmp_path / "st", **kw)


def test_deploy_ok_with_mini_fake_and_no_llm_expectation(tmp_path):
    r = _deploy(MiniFreya(), tmp_path)
    assert r["workflow_id"] == "wf_9" and r["version"] == 1 and r["diff"] == [] and r["llm_ok"] is True
    assert r["created"] is True


def test_kit_is_imported_when_key_is_set(monkeypatch):
    sentinel = object()
    monkeypatch.setenv("FREYA_API_KEY", "fak_test_only_value")
    monkeypatch.setattr(deploy.paths, "import_kit", lambda name: sentinel if name == "freya" else None)
    assert deploy._kit(None) is sentinel


def test_save_raising_deploy_error_passes_through(tmp_path):
    err = deploy.DeployError("kit says no", {"why": 1})
    fake = MiniFreya(save_exc=err)
    with pytest.raises(deploy.DeployError) as ei:
        _deploy(fake, tmp_path)
    assert ei.value is err and ei.value.result == {"why": 1}


def test_save_without_workflow_id(tmp_path):
    fake = MiniFreya(ids={"agent_id": "a"})
    with pytest.raises(deploy.DeployError, match="no workflow_id"):
        _deploy(fake, tmp_path)


NO_VERSION = {"workflow_id": "wf_9", "agent_id": "ag_9"}


def test_no_versions_listed(tmp_path):
    # the kit returned no version number: the versions list is read (and must not be empty)
    fake = MiniFreya(ids=dict(NO_VERSION), versions=[])
    with pytest.raises(deploy.DeployError, match="no versions listed"):
        _deploy(fake, tmp_path)


def test_kit_version_number_means_no_extra_gets(tmp_path):
    fake = MiniFreya(api_exc=AssertionError("no api call expected"))
    r = _deploy(fake, tmp_path)
    assert r["version"] == 1 and r["diff"] == [] and fake.exports == ["wf_9"]


def test_unreadable_export_is_a_read_back_failure(tmp_path):
    class F(MiniFreya):
        def export_workflow(self, wid, path):
            pathlib.Path(path).write_text("not json")
    fake = F()
    with pytest.raises(deploy.DeployError, match="read-back failed"):
        _deploy(fake, tmp_path)


def test_read_back_transport_error_is_scrubbed(tmp_path, monkeypatch):
    monkeypatch.setenv("FREYA_API_KEY", "fak_SECRETSECRET99")
    fake = MiniFreya(ids=dict(NO_VERSION), api_exc=OSError("timeout talking with key fak_SECRETSECRET99"))
    with pytest.raises(deploy.DeployError) as ei:
        _deploy(fake, tmp_path)
    assert str(ei.value).startswith("read-back failed: ") and "SECRETSECRET" not in str(ei.value)
    assert fake.exports == []                                       # nothing exported after a failed read-back


def test_versions_as_bare_list_and_non_dicts_ignored():
    class F(MiniFreya):
        def api(self, method, path, body=None, **params):
            return [{"versionNumber": 3, "isPublished": True, "id": "v3"}, "junk", None]
    assert deploy._published_check(F(), "wf") == 3


def test_cond_projection_of_non_dict_and_nested():
    assert deploy._cond("raw") == "raw"
    c = {"logic": "or", "conditions": [{"variable": "nx", "operator": "equals", "operand": 3}, "odd"]}
    assert deploy._cond(c) == {"logic": "or", "conditions": [
        {"operator": "equals", "variable": "nx", "operand": "3"}, "odd"]}
    a = {"initial_node": "n", "nodes": {"n": {"transitions": [{"target_node": "m", "condition": "x"}]}}}
    b = copy.deepcopy(a)
    assert deploy.projected_diff(a, b) == []
    b["nodes"]["n"]["transitions"][0]["condition"] = "y"
    assert deploy.projected_diff(a, b) == ["node n: transitions differ (1 sent, 1 stored)"]


def test_false_success_walks_lists_and_dicts():
    r = {"results": [{"ok": True}, {"ok": False}], "valid": False, "nested": {"success": False}}
    assert deploy._false_success(r) == ["/results/1/ok", "/valid", "/nested/success"]
    assert deploy._false_success({"valid": True, "dryRun": True}) == []


# ================================================================================================ llm parsing

def test_schema_errors_long_message_truncated():
    sch = {"type": "object", "properties": {"k": {"enum": ["v%03d" % i for i in range(200)]}}}
    errs = llm.schema_errors({"k": "nope"}, sch)
    assert len(errs) == 1 and errs[0].startswith("/k: ") and errs[0].endswith("...")
    assert len(errs[0]) == len("/k: ") + 300


def test_schema_errors_broken_schema():
    errs = llm.schema_errors({}, {"type": 12})
    assert len(errs) == 1 and errs[0].startswith("<schema>: ")


def test_repair_prompt_truncates_huge_previous_answer():
    p = llm._repair_prompt("PROMPT", "x" * 70000, ["/n: bad"])
    assert p.startswith("PROMPT\n\n---\nYOUR PREVIOUS ANSWER WAS REJECTED.") and "- /n: bad" in p
    assert "x" * 60000 + " ...(truncated)" in p and "x" * 60001 not in p
    p2 = llm._repair_prompt("P", {"n": 0}, ["e"])
    assert '{"n": 0}' in p2


def test_fenced_blocks_and_parse_json_text_edges():
    assert llm._fenced_blocks("a ```json {\"n\": 1} ``` b ``` {\"n\": 2} ``` ```open") == ['{"n": 1}', '{"n": 2}']
    assert llm.parse_json_text(None) is None
    assert llm.parse_json_text({"a": 1}) == {"a": 1}
    assert llm.parse_json_text("[1, 2]") is None                 # a list is not an object
    assert llm.parse_json_text("noise {\"n\": 3} trailing") == {"n": 3}


def test_usage_brief():
    assert llm._usage_brief(None) == {}
    assert llm._usage_brief({"input_tokens": 1, "foo": 2, "output_tokens": 3}) == {"input_tokens": 1,
                                                                                   "output_tokens": 3}


def test_validate_hook_crash_is_repaired_then_fails():
    seen = []

    def fn(req):
        seen.append(req["prompt"])
        return {"n": 2}

    def bad_validate(obj):
        raise KeyError("missing piece")
    llm.set_backend(fn)
    with pytest.raises(llm.LLMError, match="<validate>: 'missing piece'"):
        llm.call_json("p", "s", "PROMPT", SCHEMA, timeout_s=5, validate=bad_validate)
    assert len(seen) == 1 + llm.MAX_REPAIRS and "<validate>" in seen[1]


def test_async_backend_and_future_outputs():
    async def coro_backend(req):
        return {"n": 4}
    llm.set_backend(coro_backend)
    assert llm.call_json("p", "s", "x", SCHEMA, timeout_s=5) == {"n": 4}
    llm.set_backend(lambda req: '```json\n{"n": 5}\n```')
    assert llm.call_json("p", "s", "x", SCHEMA, timeout_s=5) == {"n": 5}


def test_call_json_inside_a_running_loop_uses_a_thread():
    llm.set_backend(lambda req: {"n": 6})

    async def inner():
        return llm.call_json("p", "s", "x", SCHEMA, timeout_s=5)
    assert asyncio.run(inner()) == {"n": 6}


def test_run_parallel_empty():
    assert llm.run_parallel([]) == []


# ================================================================================================ llm SDK transport

def test_sdk_backend_without_skills_kwarg_text_blocks_and_result_text(monkeypatch):
    import claude_agent_sdk as sdk
    from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, TextBlock, ToolUseBlock
    made = []

    class OldOptions:
        def __init__(self, **kw):
            if "skills" in kw:
                raise TypeError("unexpected keyword argument 'skills'")
            made.append(kw)
            self.__dict__.update(kw)

    def fake_query(prompt, options):
        async def gen():
            yield SystemMessage(subtype="init", data={})                  # neither assistant nor result: ignored
            yield AssistantMessage(content=[TextBlock(text="thinking aloud"),
                                            ToolUseBlock(id="t", name="OtherTool", input={"n": 99})],
                                   model="m-used")
            yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                                session_id="s", result='here: {"n": 7}', structured_output=None)
        return gen()
    monkeypatch.setattr(sdk, "ClaudeAgentOptions", OldOptions)
    monkeypatch.setattr(sdk, "query", fake_query)
    out = asyncio.run(llm._sdk_backend({"system": "S", "schema": SCHEMA, "model": "m", "effort": "low",
                                        "prompt": "P"}))
    assert made and "skills" not in made[0] and made[0]["tools"] == [] and made[0]["max_turns"] == llm.MAX_TURNS
    assert out["data"] is None and out["model"] == "m-used"
    assert out["text"] == 'thinking aloud\nhere: {"n": 7}'               # OtherTool input is not the answer
    assert llm.call_json("p", "S", "P", SCHEMA, timeout_s=5) == {"n": 7}   # parsed from the text fallback


def test_sdk_backend_result_text_ignored_when_tool_result_present(monkeypatch):
    import claude_agent_sdk as sdk
    from claude_agent_sdk import AssistantMessage, ResultMessage, ToolUseBlock

    def fake_query(prompt, options):
        async def gen():
            yield AssistantMessage(content=[ToolUseBlock(id="t", name="StructuredOutput", input={"n": 8})], model="")
            yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                                session_id="s", result="final words", structured_output=None)
        return gen()
    monkeypatch.setattr(sdk, "query", fake_query)
    out = asyncio.run(llm._sdk_backend({"system": "S", "schema": SCHEMA, "model": "m0", "effort": "low",
                                        "prompt": "P"}))
    assert out["data"] == {"n": 8} and out["text"] == "" and out["model"] == "m0"
