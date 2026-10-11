"""Tests for builder/deploy.py (agent 3), fully offline: a fake kit `freya` module records every call.

Edge cases: OPS-04 per-slot state file, OPS-06 transport errors, OPS-07 stripped fields (read-back diff),
OPS-09 publish the newest version, OPS-11 wrong agent model, OPS-22 secrets never in error text, OPS-68 second save.
"""
import copy
import json
import pathlib

import pytest

from builder import deploy

AGENT_LLM = {"provider": "experimental-5", "model": "experimental-5"}


def small_wf():
    return {
        "initial_node": "s_open",
        "system_prompt": "x",
        "global_nodes": {},
        "test_variables": {"customer_id": "c_test"},
        "nodes": {
            "s_open": {"name": "s_open", "node_type": "conversation", "on_enter": {"type": "tts", "text": "Hi"},
                       "task_message": "t", "extraction_schema": [{"name": "u_text", "type": "string",
                                                                    "description": "d", "min_confidence": 0.3}],
                       "transitions": [{"target_node": "ctl", "description": "always",
                                        "condition": {"operator": "always"}}]},
            "ctl": {"name": "ctl", "node_type": "code", "passthrough": True, "passthrough_default_transition": "e_end",
                    "on_enter": {"type": "silent"},
                    "pre_actions": [{"type": "function", "function": {
                        "name": "code_exec", "handler": "__function__:code_exec", "parameters": {
                            "type": "object", "properties": {"code": {"type": "string", "default": "x = 1\n"},
                                                             "timeout_ms": {"type": "number", "default": 20000}}}}}],
                    "transitions": [{"target_node": "a_x", "description": "g", "condition": {
                        "logic": "or", "conditions": [{"variable": "n", "operator": "greater_than", "operand": 2}]}},
                        {"target_node": "e_end", "description": "always", "condition": {"operator": "always"}}]},
            "a_x": {"name": "a_x", "node_type": "api_request", "passthrough": True,
                    "passthrough_default_transition": "e_end", "on_enter": {"type": "silent"},
                    "pre_actions": [{"type": "function", "config": {"timeoutMs": 12000, "maxRetries": 0}, "function": {
                        "name": "close_call", "handler": "__function__:api_call", "parameters": {
                            "type": "object", "properties": {
                                "url": {"type": "string", "default": "https://h/v1/close_call"},
                                "method": {"type": "string", "default": "POST"},
                                "body": {"type": "object", "properties": {
                                    "customer_id": {"type": "string", "default": "{{customer_id}}"}}}}}}}],
                    "response_mapping": [{"path": "data.ok", "variable": "r_a_x_s"}],
                    "suppress_tool_results": True,
                    "transitions": [{"target_node": "e_end", "description": "always",
                                     "condition": {"operator": "always"}}]},
            "e_end": {"name": "e_end", "node_type": "end_call", "on_enter": {"type": "silent"}, "transitions": [],
                      "terminal": {"type": "function", "function": {"name": "call_closed",
                                                                    "handler": "__function__:end_call"}}},
        },
    }


class FakeFreya:
    """Mimics the kit module surface used by deploy.py."""
    AGENT_LLM = AGENT_LLM

    def __init__(self, dry=None, dry_exc=None, publish_ok=True, stored_edit=None, llm=None, save_exc=None,
                 never_published=False):
        self.calls = []
        self.dry = {"valid": True} if dry is None else dry
        self.dry_exc = dry_exc
        self.publish_ok = publish_ok
        self.never_published = never_published
        self.stored_edit = stored_edit
        self.llm = llm or dict(AGENT_LLM)
        self.save_exc = save_exc
        self.versions = []
        self.stored = None
        self.n_create = 0

    def workspace_id(self):
        return "ws_1"

    def validate_workflow(self, name, workflow):
        self.calls.append(("validate", name))
        if self.dry_exc:
            raise self.dry_exc
        return self.dry

    def save_workflow(self, slot, workflow, state_file=".freya-agents.json"):
        self.calls.append(("save", slot, state_file))
        if self.save_exc:
            raise self.save_exc
        f = pathlib.Path(state_file)
        state = json.loads(f.read_text()) if f.exists() else {}
        self.stored = copy.deepcopy(workflow)
        if self.stored_edit:
            self.stored_edit(self.stored)
        self.stored["agent_config"] = {"llmConfig": dict(self.llm)}
        if slot in state:
            n = len(self.versions) + 1
            self.versions.append({"id": "v%d" % n, "versionNumber": n,
                                  "isPublished": self.publish_ok and not self.never_published})
            state[slot]["version"] = n
        else:
            self.n_create += 1
            self.versions.append({"id": "v1", "versionNumber": 1, "isPublished": False})
            state[slot] = {"workflow_id": "wf_1", "agent_id": "ag_1"}
        f.write_text(json.dumps(state))
        return state[slot]

    def api(self, method, path, body=None, **params):
        self.calls.append(("api", method, path, params.get("limit")))
        if method == "GET" and path.startswith("/api/v2/versions/workflow/"):
            return {"versions": list(reversed(self.versions))}
        if method == "POST" and path.endswith("/publish"):
            if not self.never_published:
                for v in self.versions:
                    if v["id"] == body["versionId"]:
                        v["isPublished"] = True
            return {}
        if method == "GET" and path.startswith("/api/v2/workflow/"):
            return {"workflow": {"id": "wf_1", "agentId": "ag_1", "workflow": self.stored}}
        raise AssertionError("unexpected call " + method + " " + path)

    def export_workflow(self, workflow_id, path):
        self.calls.append(("export", workflow_id, path))
        pathlib.Path(path).write_text(json.dumps({"workflow_id": workflow_id, "workflow": self.stored}))
        return path


def kinds(fake):
    return [c[0] for c in fake.calls]


def test_create_saves_twice_publishes_and_exports(tmp_path):                 # OPS-68
    fake = FakeFreya()
    r = deploy.deploy(small_wf(), "brief-a-1234", tmp_path / "run", dry_run=True, freya=fake, state_dir=tmp_path / "st")
    assert kinds(fake)[:3] == ["validate", "save", "save"]
    assert r["workflow_id"] == "wf_1" and r["agent_id"] == "ag_1" and r["created"] is True
    assert r["version"] == 2 and r["diff"] == [] and r["llm_ok"] is True
    assert pathlib.Path(r["export_path"]).exists() and r["export_path"].endswith("workflow.export.json")
    ids = json.loads((tmp_path / "run" / "ids.json").read_text())
    assert ids == {"workflow_id": "wf_1", "agent_id": "ag_1", "version": 2, "created": True}
    assert r["state_file"] == str(tmp_path / "st" / "brief-a-1234.json")          # OPS-04
    # BUILD SPEED item 5: the kit's save returned the published version; the export is the only read-back GET
    assert [c for c in fake.calls if c[0] == "api"] == [] and kinds(fake).count("export") == 1


def test_update_saves_once(tmp_path):
    fake = FakeFreya()
    deploy.deploy(small_wf(), "slot", tmp_path / "r1", freya=fake, state_dir=tmp_path)
    fake.calls.clear()
    r = deploy.deploy(small_wf(), "slot", tmp_path / "r2", dry_run=False, freya=fake, state_dir=tmp_path)
    assert kinds(fake).count("save") == 1 and "validate" not in kinds(fake)
    assert r["created"] is False and r["version"] == 3


def test_dry_run_failure_stops_before_save(tmp_path):
    fake = FakeFreya(dry={"result": {"nodes": [{"success": False, "error": "bad node"}]}})
    with pytest.raises(deploy.DeployError, match="dry run"):
        deploy.deploy(small_wf(), "s", tmp_path, freya=fake, state_dir=tmp_path)
    assert "save" not in kinds(fake)


def test_dry_run_http_error_is_scrubbed(tmp_path, monkeypatch):              # OPS-06, OPS-22
    monkeypatch.setenv("FREYA_API_KEY", "fak_supersecretvalue123")
    fake = FakeFreya(dry_exc=RuntimeError("POST /api/v2/workflow -> 422: key fak_supersecretvalue123 bad"))
    with pytest.raises(deploy.DeployError) as ei:
        deploy.deploy(small_wf(), "s", tmp_path, freya=fake, state_dir=tmp_path)
    assert "fak_supersecretvalue123" not in str(ei.value) and "422" in str(ei.value)


def test_save_failure(tmp_path):
    fake = FakeFreya(save_exc=RuntimeError("PUT -> 503"))
    with pytest.raises(deploy.DeployError, match="save_workflow failed"):
        deploy.deploy(small_wf(), "s", tmp_path, dry_run=False, freya=fake, state_dir=tmp_path)


def _no_version(fake):
    save = fake.save_workflow

    def wrapped(*a, **k):
        ids = dict(save(*a, **k))
        ids.pop("version", None)
        return ids
    fake.save_workflow = wrapped
    return fake


def test_unpublished_newest_is_published_once(tmp_path):                    # OPS-09
    fake = _no_version(FakeFreya(publish_ok=False))
    r = deploy.deploy(small_wf(), "s", tmp_path, dry_run=False, freya=fake, state_dir=tmp_path)
    publishes = [c for c in fake.calls if c[0] == "api" and c[2].endswith("/publish")]
    assert len(publishes) == 1 and r["version"] == 2
    assert ("api", "GET", "/api/v2/versions/workflow/wf_1", 100) in fake.calls      # OPS-09 limit=100


def test_never_published_raises(tmp_path):
    fake = _no_version(FakeFreya(never_published=True))
    with pytest.raises(deploy.DeployError, match="not published"):
        deploy.deploy(small_wf(), "s", tmp_path, dry_run=False, freya=fake, state_dir=tmp_path)


def test_stripped_fields_show_in_diff(tmp_path):                            # OPS-07
    def strip(wf):
        wf["nodes"]["s_open"]["pre_actions"] = []
        wf["nodes"]["a_x"]["pre_actions"] = []
        wf["nodes"]["ctl"]["transitions"] = wf["nodes"]["ctl"]["transitions"][1:]
        del wf["nodes"]["e_end"]
    fake = FakeFreya(stored_edit=strip)
    r = deploy.deploy(small_wf(), "s", tmp_path, dry_run=False, freya=fake, state_dir=tmp_path)
    text = "\n".join(r["diff"])
    assert "node a_x: 1 pre_actions sent, 0 stored" in text
    assert "node ctl: transitions differ" in text
    assert "node e_end: missing after save" in text
    assert pathlib.Path(r["export_path"]).exists()


def test_strict_raises_after_export(tmp_path):
    def edit(wf):
        wf["nodes"]["s_open"]["on_enter"]["text"] = "changed"
    fake = FakeFreya(stored_edit=edit)
    with pytest.raises(deploy.DeployError) as ei:
        deploy.deploy(small_wf(), "s", tmp_path, dry_run=False, freya=fake, state_dir=tmp_path, strict=True)
    assert "export" in kinds(fake)
    assert ei.value.result["diff"] == ["node s_open: on_enter differs"]


def test_wrong_agent_model_is_a_diff(tmp_path):                             # OPS-11
    fake = FakeFreya(llm={"provider": "openai", "model": "x"})
    r = deploy.deploy(small_wf(), "s", tmp_path, dry_run=False, freya=fake, state_dir=tmp_path)
    assert r["llm_ok"] is False and any("llmConfig" in d for d in r["diff"])


def test_slot_is_sanitised_and_empty_rejected(tmp_path):
    fake = FakeFreya()
    r = deploy.deploy(small_wf(), "../brief a!", tmp_path, dry_run=False, freya=fake, state_dir=tmp_path / "st")
    assert pathlib.Path(r["state_file"]).parent == tmp_path / "st"
    assert pathlib.Path(r["state_file"]).name == "brief_a.json"
    with pytest.raises(deploy.DeployError):
        deploy.deploy(small_wf(), "///", tmp_path, freya=FakeFreya(), state_dir=tmp_path)


def test_missing_api_key_without_injected_client(tmp_path, monkeypatch):
    monkeypatch.delenv("FREYA_API_KEY", raising=False)
    with pytest.raises(deploy.DeployError, match="FREYA_API_KEY"):
        deploy.deploy(small_wf(), "s", tmp_path, state_dir=tmp_path)


def test_corrupt_state_file_stops_before_any_save(tmp_path):
    (tmp_path / "s.json").write_text("{not json")
    fake = FakeFreya()
    with pytest.raises(deploy.DeployError, match="unreadable"):
        deploy.deploy(small_wf(), "s", tmp_path, dry_run=False, freya=fake, state_dir=tmp_path)
    assert "save" not in kinds(fake)


def test_export_wrapper(tmp_path):
    fake = FakeFreya()
    fake.stored = small_wf()
    p = deploy.export("wf_9", tmp_path / "sub" / "x.json", freya=fake)
    assert pathlib.Path(p).exists() and fake.calls[-1] == ("export", "wf_9", p)

    class Bad(FakeFreya):
        def export_workflow(self, workflow_id, path):
            raise RuntimeError("GET -> 500")
    with pytest.raises(deploy.DeployError, match="export failed"):
        deploy.export("wf_9", tmp_path / "y.json", freya=Bad())


# ------------------------------------------------------------------------------------------------ projected_diff

def test_projected_diff_identical_and_extra_keys_ignored():
    a = small_wf()
    b = copy.deepcopy(a)
    b["agent_config"] = {"x": 1}
    b["nodes"]["s_open"]["nodePositions"] = {"x": 1}
    b["nodes"]["ctl"]["transitions"][0]["condition"]["conditions"][0]["operand"] = "2"   # str vs int
    b["nodes"]["ctl"]["transitions"][0]["description"] = "rewritten"
    assert deploy.projected_diff(a, b) == []


def test_projected_diff_detects_each_field():
    a = small_wf()
    cases = {
        "node_type": lambda w: w["nodes"]["s_open"].__setitem__("node_type", "code"),
        "passthrough": lambda w: w["nodes"]["ctl"].__setitem__("passthrough", False),
        "response_mapping": lambda w: w["nodes"]["a_x"]["response_mapping"].clear(),
        "extraction": lambda w: w["nodes"]["s_open"]["extraction_schema"].clear(),
        "pre_action 0 url": lambda w: w["nodes"]["a_x"]["pre_actions"][0]["function"]["parameters"]["properties"][
            "url"].__setitem__("default", "x"),
        "pre_action 0 code": lambda w: w["nodes"]["ctl"]["pre_actions"][0]["function"]["parameters"]["properties"][
            "code"].__setitem__("default", "y = 2\n"),
        "pre_action 0 body": lambda w: w["nodes"]["a_x"]["pre_actions"][0]["function"]["parameters"]["properties"][
            "body"]["properties"]["customer_id"].__setitem__("default", "c1"),
        "pre_action 0 name": lambda w: w["nodes"]["a_x"]["pre_actions"][0]["function"].__setitem__("name", "z"),
        "initial_node": lambda w: w.__setitem__("initial_node", "ctl"),
        "unexpected node": lambda w: w["nodes"].__setitem__("extra", {"node_type": "conversation"}),
    }
    for needle, edit in cases.items():
        b = copy.deepcopy(a)
        edit(b)
        d = deploy.projected_diff(a, b)
        assert any(needle in x for x in d), (needle, d)


def test_projected_diff_handles_empty_inputs():
    assert deploy.projected_diff({}, {}) == []
    assert deploy.projected_diff(small_wf(), None)
