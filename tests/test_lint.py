"""Tests for builder/compiler/lint.py (agent 3): every rule fires on a minimal mutation of a clean workflow,
and the clean golden workflows produce no finding.

Edge cases: OPS-07 stripped fields (pre_actions on the wrong node type), OPS-30 unresolved placeholders,
BRF-16 reasonless outcomes, the disclosure lexicon on pre-verification lines, real-clock calls in the snippet.
"""
import copy
import json
import pathlib

import pytest

from builder import openapi_model as om
from builder.compiler import graph, lint

ROOT = pathlib.Path(__file__).resolve().parent.parent
STUB_CODE = "import json\ntry:\n    vars['nx'] = 's_safe'\nexcept Exception:\n    vars['nx'] = 's_safe'\n"


@pytest.fixture(scope="module")
def cat():
    return om.load(ROOT / "kit" / "tools" / "openapi.json")


def _golden(name="spec-ab.json"):
    return json.loads((ROOT / "tests" / "golden" / name).read_text())


@pytest.fixture(scope="module")
def base(cat):
    spec = _golden()
    wf, w = graph.compile_workflow(spec, cat, code=STUB_CODE)
    return spec, wf, w


def run(cat, spec, wf, w, stable=False):
    return lint.lint(wf, cat, spec, w, stable=stable)


def rules(findings, level="error"):
    return {f["rule"] for f in findings if f["level"] == level}


def mut(base):
    spec, wf, w = base
    return copy.deepcopy(spec), copy.deepcopy(wf), copy.deepcopy(w)


def body(wf, node):
    return wf["nodes"][node]["pre_actions"][0]["function"]["parameters"]["properties"]["body"]


def test_clean_golden_has_no_findings(cat, base):
    spec, wf, w = base
    assert run(cat, spec, wf, w, stable=True) == []


def test_clean_golden_a(cat):
    spec = _golden("spec-a.json")
    wf, w = graph.compile_workflow(spec, cat, code=STUB_CODE)
    assert run(cat, spec, wf, w, stable=True) == []


def test_errors_helper():
    assert lint.errors([{"level": "warn"}, {"level": "error", "rule": "x"}]) == [{"level": "error", "rule": "x"}]


def test_null(cat, base):
    spec, wf, w = mut(base)
    wf["nodes"]["s_rp"]["role_message"] = None
    assert "null" in rules(run(cat, spec, wf, w))


def test_initial_and_forbidden_top_keys(cat, base):
    spec, wf, w = mut(base)
    wf["initial_node"] = "nowhere"
    wf["context_variables"] = {"items": []}
    wf["agent_config"] = {"x": 1}
    wf["global_nodes"] = {"g": {}}
    r = rules(run(cat, spec, wf, w))
    assert {"initial", "forbidden_key", "global_nodes"} <= r


def test_target_missing(cat, base):
    spec, wf, w = mut(base)
    wf["nodes"]["s_rp"]["transitions"][0]["target_node"] = "ghost"
    wf["nodes"]["s_id"]["max_turn_transition"] = "ghost2"
    out = run(cat, spec, wf, w)
    assert sum(1 for f in out if f["rule"] == "target_missing") >= 2


def test_passthrough_must_end_with_always(cat, base):
    spec, wf, w = mut(base)
    wf["nodes"]["a_verify_1"]["transitions"] = []
    wf["nodes"]["a_acct_1"]["passthrough_default_transition"] = "s_safe"
    out = [f for f in run(cat, spec, wf, w) if f["rule"] == "passthrough_always"]
    assert {f["where"] for f in out} >= {"a_verify_1", "a_acct_1"}


def test_always_not_last(cat, base):
    spec, wf, w = mut(base)
    trs = wf["nodes"]["ctl"]["transitions"]
    trs.insert(0, trs.pop())
    assert "passthrough_always" in rules(run(cat, spec, wf, w))


def test_dup_target(cat, base):
    spec, wf, w = mut(base)
    trs = wf["nodes"]["ctl"]["transitions"]
    trs.insert(0, copy.deepcopy(trs[0]))
    assert "dup_target" in rules(run(cat, spec, wf, w))


def test_fallback_target_and_matches_intent(cat, base):
    spec, wf, w = mut(base)
    trs = wf["nodes"]["s_rp"]["transitions"]
    trs.insert(0, {"target_node": "s_safe", "description": "x",
                   "condition": {"logic": "or", "conditions": [{"variable": "nx", "operator": "equals",
                                                                "operand": "s_safe"}]}})
    trs.insert(0, {"target_node": "s_id", "description": "x",
                   "condition": {"operator": "matches_intent", "description": "anything"}})
    r = rules(run(cat, spec, wf, w))
    assert {"fallback_target", "matches_intent"} <= r


def test_tools_and_pre_action_placement(cat, base):                         # OPS-07
    spec, wf, w = mut(base)
    wf["nodes"]["s_neg"]["tools"] = [{"type": "function"}]
    wf["nodes"]["s_conf"]["pre_actions"] = copy.deepcopy(wf["nodes"]["a_acct_1"]["pre_actions"])
    wf["nodes"]["a_acct_2"]["passthrough"] = False
    r = rules(run(cat, spec, wf, w))
    assert {"tools_present", "pre_action_placement"} <= r


def test_pre_action_shape(cat, base):
    spec, wf, w = mut(base)
    wf["nodes"]["a_acct_1"]["pre_actions"] = []
    wf["nodes"]["ctl"]["pre_actions"][0]["function"]["handler"] = "__function__:api_call"
    out = [f for f in run(cat, spec, wf, w) if f["rule"] == "pre_action_shape"]
    assert {f["where"] for f in out} >= {"a_acct_1", "ctl"}


def test_suppress_results(cat, base):
    spec, wf, w = mut(base)
    wf["nodes"]["a_note_1"]["suppress_tool_results"] = False
    assert "suppress_results" in rules(run(cat, spec, wf, w))


@pytest.mark.parametrize("code,rule", [
    ("d = {'a': {'b': 1}}\n", "code_braces"),
    ("def (:\n", "code_compile"),
    ("import os\nvars['nx'] = 's_safe'\n", "code_imports"),
    ("from subprocess import run\n", "code_imports"),
    ("import datetime\nx = datetime.date.today()\n", "nondeterminism"),
    ("import datetime\nx = datetime.datetime.now()\n", "nondeterminism"),
    ("x = '" + "a" * 200_100 + "'\n", "code_size"),
])
def test_code_rules(cat, base, code, rule):
    spec, wf, w = mut(base)
    wf["nodes"]["ctl"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"] = code
    assert rule in rules(run(cat, spec, wf, w))


def test_code_size_warn(cat, base):
    spec, wf, w = mut(base)
    wf["nodes"]["ctl"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"] = \
        "x = '" + "a" * 85_000 + "'\n"
    assert "code_size" in rules(run(cat, spec, wf, w), "warn")
    wf["nodes"]["ctl"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"] = \
        "x = '" + "a" * 120_000 + "'\n"
    assert "code_size" in rules(run(cat, spec, wf, w), "error")     # live code_exec limit: code + data <= 128 KiB


def test_api_url_method_retries(cat, base):
    spec, wf, w = mut(base)
    p = wf["nodes"]["a_promise_1_1"]["pre_actions"][0]
    p["function"]["parameters"]["properties"]["url"]["default"] = "https://evil.example/create_promise"
    p["function"]["parameters"]["properties"]["method"]["default"] = "GET"
    p["config"]["maxRetries"] = 2
    del wf["nodes"]["a_note_1"]["pre_actions"][0]["config"]["timeoutMs"]
    out = run(cat, spec, wf, w)
    assert {"api_url", "api_method", "api_max_retries"} <= rules(out)
    assert "api_timeout" in rules(out, "warn")


def test_api_tool_unknown(cat, base):
    spec, wf, w = mut(base)
    wf["nodes"]["a_xfer_1"]["pre_actions"][0]["function"]["name"] = "wire_money"
    assert "api_tool" in rules(run(cat, spec, wf, w))


def test_api_body_fields_and_enums(cat, base):
    spec, wf, w = mut(base)
    b = body(wf, "a_xfer_1")
    b["properties"]["queue"]["enum"] = ["general", "made_up_queue"]
    b["properties"]["extra"] = {"type": "string", "default": "x"}
    body(wf, "a_xfer_2")["properties"]["customer_id"]["default"] = "{{someone_else}}"
    r = rules(run(cat, spec, wf, w))
    assert {"api_enum", "api_body_field"} <= r


def test_api_required(cat, base):
    spec, wf, w = mut(base)
    b = body(wf, "a_promise_1_1")
    del b["properties"]["date"]
    b2 = body(wf, "a_promise_1_2")
    b2["required"] = b2["required"] + ["nonexistent"]
    out = [f for f in run(cat, spec, wf, w) if f["rule"] == "api_required"]
    assert {f["where"] for f in out} == {"a_promise_1_1", "a_promise_1_2"}


def test_response_mapping(cat, base):
    spec, wf, w = mut(base)
    wf["nodes"]["a_acct_1"]["response_mapping"].append({"path": "data.secret", "variable": "r_a_acct_1_x"})
    wf["nodes"]["a_acct_2"]["response_mapping"].append({"path": "ok", "variable": "other"})
    out = [f for f in run(cat, spec, wf, w) if f["rule"] == "response_mapping"]
    assert {f["where"] for f in out} == {"a_acct_1", "a_acct_2"}


def test_entry_guard(cat, base):
    spec, wf, w = mut(base)
    tr = next(t for t in wf["nodes"]["ctl"]["transitions"] if t["target_node"] == "a_promise_2_1")
    tr["condition"] = {"logic": "or", "conditions": [{"variable": "nx", "operator": "equals",
                                                      "operand": "a_promise_2_1"}]}
    link = next(t for t in wf["nodes"]["a_promise_1_1"]["transitions"] if t["target_node"] == "a_note_1")
    link["condition"]["conditions"][1]["conditions"].pop()
    out = [f for f in run(cat, spec, wf, w) if f["rule"] == "entry_guard"]
    assert {f["where"] for f in out} == {"ctl", "a_promise_1_1"}


def test_entry_guard_exempts_s_bye(cat, base):
    spec, wf, w = base
    assert not [f for f in run(cat, spec, wf, w) if f["where"] == "s_bye"]


def test_close_reason_rules(cat, base):                                     # BRF-16
    spec, wf, w = mut(base)
    body(wf, "a_close_n")["properties"]["reason"] = {"type": "string", "default": "{{cr}}"}
    body(wf, "a_close_r")["properties"]["reason"]["default"] = "refused"
    out = [f for f in run(cat, spec, wf, w) if f["rule"] == "close_reason"]
    assert {f["where"] for f in out} == {"a_close_n", "a_close_r"}


def test_var_writer(cat, base):                                             # OPS-30
    spec, wf, w = mut(base)
    wf["nodes"]["s_neg"]["on_enter"]["text"] = "{{say}} {{undefined_var}}"
    wf["nodes"]["s_bye"]["transitions"][0]["condition"]["conditions"][0]["variable"] = "mystery"
    body(wf, "a_cb_1")["properties"]["date"]["default"] = "{{b_a_cb_9_date}}"
    out = [f for f in run(cat, spec, wf, w) if f["rule"] == "var_writer"]
    assert {f["where"] for f in out} == {"s_neg", "s_bye", "a_cb_1"}


def test_malformed_placeholder(cat, base):
    spec, wf, w = mut(base)
    wf["nodes"]["s_tp"]["on_enter"]["text"] = "{{ two words }}"
    assert "placeholder" in rules(run(cat, spec, wf, w))


def test_unresolved_spec_placeholder_and_quotes(cat, base):                 # OPS-30
    spec, wf, w = mut(base)
    wf["nodes"]["s_safe"]["on_enter"]["text"] = "Could you pay <amount>?"
    wf["nodes"]["s_open"]["task_message"] = "Say exactly: «hello"
    wf["system_prompt"] += " <bank>"
    out = [f for f in run(cat, spec, wf, w) if f["rule"] == "placeholder"]
    assert {f["where"] for f in out} == {"s_safe", "s_open", "system_prompt"}


def test_banned_word_in_compile_time_tts(cat, base):
    spec, wf, w = mut(base)
    wf["nodes"]["s_open"]["on_enter"]["text"] += " It is about your overdue loan."
    out = [f for f in run(cat, spec, wf, w) if f["rule"] == "banned_word"]
    assert any(f["where"] == "s_open" for f in out)


def test_banned_word_in_spec_pre_verification_lines(cat, base):
    spec, wf, w = mut(base)
    spec["third_party"]["reach_ask"] = "When can I reach <customer> about the debt?"
    spec["identity"]["fail_line"] = "I could not verify you, so I cannot discuss your balance."
    spec["intents"][0]["action"]["say"] = "Sorry. We will close the card."
    out = [f for f in run(cat, spec, wf, w) if f["rule"] == "banned_word"]
    assert {f["where"] for f in out} == {"/third_party/reach_ask", "/identity/fail_line", "/intents/0/action/say"}


def test_disclosure_lexicon_warns(cat, base):
    spec, wf, w = mut(base)
    spec["banned"]["before_verification"] = []
    spec["right_party"]["answers"]["why"] = "It is about an outstanding bill."
    out = run(cat, spec, wf, w)
    hits = [f for f in out if f["rule"] == "disclosure_word"]
    assert hits and hits[0]["level"] == "warn" and hits[0]["where"] == "/right_party/answers/why"


def test_runtime_lines_after_verification_are_not_checked(cat, base):
    spec, wf, w = mut(base)
    spec["statement"]["intro"] = "I am calling about a late payment on your loan."
    assert not [f for f in run(cat, spec, wf, w) if f["rule"] in ("banned_word", "disclosure_word")]


def test_spec_enum_rules(cat, base):
    spec, wf, w = mut(base)
    spec["situations"]["S_PAID"]["outcome"] = "paid_in_full"
    spec["situations"]["S_HUMAN_TRANSFER"]["queue"] = "vip"
    spec["situations"]["S_DISPUTE"]["note_reason"] = "contested"
    spec["intents"][3]["action"]["queue"] = "nowhere"
    spec["identity"]["questions"][0]["field_value"] = "mothers_maiden_name"
    spec["identity"]["hints"][0]["value"] = "other_hint"
    spec["products"]["types"]["boat_loan"] = {"spoken": "boat", "floor": {"kind": "full"}}
    out = [f for f in run(cat, spec, wf, w) if f["rule"] == "spec_enum" and f["level"] == "error"]
    wheres = {f["where"] for f in out}
    assert {"/situations/S_PAID", "/situations/S_HUMAN_TRANSFER", "/situations/S_DISPUTE",
            "/intents/3/action/queue", "/identity/questions/0/field_value", "/identity/hints/0/value",
            "/products/types"} <= wheres


def test_spec_enum_missing_type_is_warn(cat, base):
    spec, wf, w = mut(base)
    spec["products"]["types"].pop(next(iter(spec["products"]["types"])))
    out = [f for f in run(cat, spec, wf, w) if f["rule"] == "spec_enum"]
    assert out and all(f["level"] == "warn" for f in out)


def test_close_reason_enum_checked(cat, base):
    spec, wf, w = mut(base)
    c2 = copy.deepcopy(cat)
    c2["enums"]["close_reason"] = ["refused"]
    out = [f for f in lint.lint(wf, c2, spec, w, stable=False) if f["rule"] == "spec_enum"]
    assert any("reason" in f["msg"] for f in out)


def test_reasonless_with_reason(cat, base):                                 # BRF-16
    spec, wf, w = mut(base)
    spec["situations"]["S_PROMISE"]["reason"] = "promise"
    assert "reasonless_reason" in rules(run(cat, spec, wf, w))


@pytest.mark.parametrize("trigger,text", [
    ("on_situation:S_NOT_DEFINED", "x."), ("on_intent:no_such_intent", "x."), ("on_outcome:teleported", "x."),
    ("whenever", "x."), ("after_verified", "  "), ("after_verified", "<v:undeclared> hi"),
])
def test_required_sentence_rules(cat, base, trigger, text):
    spec, wf, w = mut(base)
    spec["required_sentences"].append({"id": "x", "text": text, "verbatim": True, "trigger": trigger, "once": True})
    assert "required_sentence" in rules(run(cat, spec, wf, w))


def test_required_sentence_needs_promise_nodes(cat, base):
    spec, wf, w = mut(base)
    w["api"]["promise"] = []
    assert "required_sentence" in rules(run(cat, spec, wf, w))


def test_listen_node_rules(cat, base):
    spec, wf, w = mut(base)
    wf["nodes"]["s_rp"]["extraction_schema"] = wf["nodes"]["s_rp"]["extraction_schema"][1:]
    wf["nodes"]["s_tp"]["extraction_schema"][3]["type"] = "date"
    del wf["nodes"]["s_id"]["extraction_schema"][0]["min_confidence"]
    del wf["nodes"]["s_neg"]["task_message"]
    wf["nodes"]["s_conf"]["extraction_schema"][2]["enum_values"] = ["v%d" % i for i in range(13)]
    del wf["nodes"]["s_safe"]["max_turn_transition"]
    out = run(cat, spec, wf, w)
    errs = {f["where"] for f in out if f["rule"] == "listen_node" and f["level"] == "error"}
    assert errs == {"s_rp", "s_tp", "s_id", "s_neg", "s_conf"}
    assert any(f["where"] == "s_safe" for f in out if f["rule"] == "listen_node" and f["level"] == "warn")


def test_end_node_rules(cat, base):
    spec, wf, w = mut(base)
    wf["nodes"]["e_end"]["transitions"] = [{"target_node": "ctl", "description": "x", "condition": {"operator": "always"}}]
    wf["nodes"]["e_end"]["terminal"]["function"]["handler"] = "x"
    assert "end_node" in rules(run(cat, spec, wf, w))
    spec, wf, w = mut(base)
    wf["nodes"]["e_end"]["node_type"] = "conversation"
    assert "end_node" in rules(run(cat, spec, wf, w))


def test_node_type_unknown(cat, base):
    spec, wf, w = mut(base)
    wf["nodes"]["s_tp"]["node_type"] = "transfer_call"
    assert "node_type" in rules(run(cat, spec, wf, w))


def test_reach_and_sources(cat, base):
    spec, wf, w = mut(base)
    wf["nodes"]["orphan"] = {"name": "orphan", "node_type": "conversation", "on_enter": {"type": "silent"},
                             "task_message": "x", "extraction_schema": [
                                 {"name": "u_text", "type": "string", "description": "x", "min_confidence": 0.3}],
                             "max_turn_transition": "ctl", "transitions": [graph._always("ctl")]}
    wf["nodes"]["s_neg"]["transitions"].insert(0, {
        "target_node": "a_promise_1_1", "description": "x",
        "condition": {"logic": "or", "conditions": [{"logic": "and", "conditions": [
            {"variable": "nx", "operator": "equals", "operand": "a_promise_1_1"},
            {"variable": "r_a_promise_1_1_s", "operator": "equals", "operand": "pending"}]}]}})
    out = run(cat, spec, wf, w)
    assert any(f["rule"] == "reach" and f["where"] == "orphan" and f["level"] == "warn" for f in out)
    assert any(f["rule"] == "reach_source" and f["where"] == "a_promise_1_1" for f in out)


def test_callback_chained_from_promise_is_flagged(cat, base):
    spec, wf, w = mut(base)
    wf["nodes"]["a_promise_1_1"]["transitions"].insert(0, {
        "target_node": "a_cb_1", "description": "x",
        "condition": {"logic": "or", "conditions": [{"logic": "and", "conditions": [
            {"variable": "wn_a_promise_1_1", "operator": "equals", "operand": "a_cb_1"},
            {"variable": "r_a_cb_1_s", "operator": "equals", "operand": "pending"}]}]}})
    out = run(cat, spec, wf, w)
    assert any(f["rule"] == "reach_source" and f["where"] == "a_cb_1" for f in out)


def test_unreachable_end_is_error(cat, base):
    spec, wf, w = mut(base)
    for k in ("a_close_r", "a_close_n"):
        wf["nodes"][k]["transitions"] = [graph._always("ctl")]
        wf["nodes"][k]["passthrough_default_transition"] = "ctl"
    assert "reach" in rules(run(cat, spec, wf, w))


def test_byte_stable_warns_on_hand_edited_workflow(cat, base):
    spec, wf, w = mut(base)
    wf["nodes"]["s_rp"]["description_note"] = "edited by hand"
    out = run(cat, spec, wf, w, stable=True)
    assert any(f["rule"] == "byte_stable" and f["level"] == "warn" for f in out)


def test_byte_stable_error_on_nondeterministic_compile(cat, base, monkeypatch):
    spec, wf, w = mut(base)
    counter = {"n": 0}
    real = graph.make_test_variables

    def flaky(s):
        counter["n"] += 1
        out = real(s)
        out["x"] = str(counter["n"])
        return out
    monkeypatch.setattr(graph, "make_test_variables", flaky)
    assert "byte_stable" in rules(run(cat, spec, wf, w, stable=True))


def test_workflow_size_warn(cat, base, monkeypatch):
    spec, wf, w = mut(base)
    monkeypatch.setattr(lint, "WORKFLOW_WARN_BYTES", 1000)
    assert "workflow_size" in rules(run(cat, spec, wf, w), "warn")


def test_lint_never_raises_on_garbage(cat, base):
    spec, _, w = base
    out = lint.lint({}, cat, spec, w)
    assert lint.errors(out)
    out2 = lint.lint({"nodes": {"x": "not a dict"}}, cat, spec, w)
    assert any(f["rule"] == "lint_crash" for f in out2) or lint.errors(out2)
    out3 = lint.lint({"nodes": {}}, {}, {}, {})
    assert isinstance(out3, list)


def test_r1_spec_line_hygiene_warnings(base, cat):
    spec, wf, w = base
    sp = copy.deepcopy(spec)
    sp["identity"]["decline"]["explain"] = "These questions protect your account. Could you please answer?"
    sp["closing"]["per_situation"] = {"S_ID_FAILED": sp["identity"]["fail_line"].split(". ")[-1]}
    sp["lines"]["floor_offer"] = "Could you pay <floor> by <date>? The rest, <rest>, stays overdue."
    sp["opening"]["line"] = "Hello, I am a digital assistant calling from <bank>. This call is recorded."
    warns = rules(run(cat, sp, wf, w), "warn")
    assert {"line_question", "line_repeat", "opening_sentence"} <= warns


def test_r1_projected_code_size_counts_escaping_and_data(base, cat):
    spec, wf, w = base
    wf2 = copy.deepcopy(wf)
    big = "x = '" + ("\\n" * 45_000) + "'\n"        # small raw, large once JSON-escaped
    for n in wf2["nodes"].values():
        for pa in n.get("pre_actions") or []:
            fn = pa.get("function") or {}
            if fn.get("handler") == "__function__:code_exec":
                fn["parameters"]["properties"]["code"]["default"] = big
    assert lint.projected_code_bytes(big, wf2) > lint.CODE_PROJECTED_MAX
    assert "code_size" in rules(run(cat, spec, wf2, w))
