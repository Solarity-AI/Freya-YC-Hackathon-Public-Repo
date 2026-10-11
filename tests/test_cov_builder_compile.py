"""Coverage round (builder compile + pipeline): lint rule branches, graph per-field / baked-literal bodies,
critic English + patch errors, extract helpers. Generic mutations of the golden Specs; no LLM, no network."""
import copy
import json
import pathlib

import pytest

from builder import llm, openapi_model as om, trace
from builder.compiler import graph, lint
from builder.pipeline import critic, extract, segment

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


def mut(base):
    return tuple(copy.deepcopy(x) for x in base)


def find(out, rule, level=None, where=None):
    return [f for f in out if f["rule"] == rule and (level is None or f["level"] == level)
            and (where is None or f["where"] == where)]


def run(cat, spec, wf, w):
    return lint.lint(wf, cat, spec, w, stable=False)


# ================================================================================================ lint helpers

def test_strings_and_conds_on_odd_inputs():
    assert list(lint._strings(5)) == [] and list(lint._strings({"a": ["x", {"b": "y"}]})) == ["x", "y"]
    assert lint._conds("not a condition") == []
    assert lint._conds({"conditions": [{"variable": "a"}, {"conditions": [{"variable": "b"}]}]}) == \
        [{"variable": "a"}, {"variable": "b"}]


def test_projected_code_bytes_non_json_code_falls_back_to_str():
    wf = {"nodes": {}}
    base_bytes = lint.DATA_BASE_BYTES + lint.MAX_TURNS * lint.DATA_PER_TURN_BYTES
    assert lint.projected_code_bytes(b"abc", wf) == len(str(b"abc")) + base_bytes
    assert lint.projected_code_bytes("abc", wf) == len('"abc"') + base_bytes


# ================================================================================================ lint rules

def test_initial_node_not_s_open_is_a_warning(cat, base):
    spec, wf, w = mut(base)
    wf["initial_node"] = "s_rp"
    out = run(cat, spec, wf, w)
    assert find(out, "initial", "warn") and not find(out, "initial", "error")


def test_node_name_mismatch_and_non_list_transitions(cat, base):
    spec, wf, w = mut(base)
    wf["nodes"]["s_rp"]["name"] = "renamed"
    wf["nodes"]["s_tp"]["transitions"] = {"oops": 1}
    out = run(cat, spec, wf, w)
    assert find(out, "node_type", "warn", "s_rp")[0]["msg"] == "node name differs from its key"
    assert any(f["msg"] == "transitions is not a list" for f in find(out, "target_missing", "error", "s_tp"))


def test_top_level_logic_must_be_or(cat, base):
    spec, wf, w = mut(base)
    tr = next(t for t in wf["nodes"]["ctl"]["transitions"] if not lint._is_always(t))
    tr["condition"]["logic"] = "and"
    out = run(cat, spec, wf, w)
    assert any("top-level logic must be 'or'" in f["msg"] for f in find(out, "target_missing", "error", "ctl"))


def test_end_node_message_mode_and_inactivity_monitor(cat, base):
    spec, wf, w = mut(base)
    e = wf["nodes"]["e_end"]
    e["terminal"]["function"]["parameters"]["properties"]["message_mode"]["default"] = "goodbye"
    e.pop("disable_inactivity_monitor", None)
    msgs = {f["msg"] for f in find(run(cat, spec, wf, w), "end_node", "warn", "e_end")}
    assert msgs == {"end_call message_mode is not 'none'", "end_call without disable_inactivity_monitor"}


def test_code_that_does_not_unpack(cat, base, monkeypatch):
    from runtime import bundle

    def boom(code):
        raise ValueError("bad base64")
    monkeypatch.setattr(bundle, "unpack_snippet", boom)
    spec, wf, w = mut(base)
    out = run(cat, spec, wf, w)
    assert any("packed code does not unpack: bad base64" in f["msg"] for f in find(out, "code_compile", "error"))


def test_now_attribute_on_other_objects_is_not_a_clock_call(cat, base):
    spec, wf, w = mut(base)
    code = STUB_CODE + "import datetime\nx = vars.now\ny = datetime.date.today()\n"
    wf["nodes"]["ctl"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"] = code
    nd = find(run(cat, spec, wf, w), "nondeterminism", "error")
    assert [f["msg"] for f in nd] == ["real clock call date.today"]


def test_api_tool_differs_from_wiring(cat, base):
    spec, wf, w = mut(base)
    w["nodes"]["a_acct_1"]["tool"] = "verify_identity"
    out = run(cat, spec, wf, w)
    assert any("differs from wiring verify_identity" in f["msg"] for f in find(out, "api_tool", "error", "a_acct_1"))


def test_system_prompt_variable_without_writer(cat, base):
    spec, wf, w = mut(base)
    wf["system_prompt"] += " Hello {{nobody_writes_me}}."
    out = run(cat, spec, wf, w)
    assert any(f["where"] == "system_prompt" and "nobody_writes_me" in f["msg"]
               for f in find(out, "var_writer", "error"))


def test_bad_placeholder_in_a_pre_verification_spec_line(cat, base):
    spec, wf, w = mut(base)
    spec["right_party"]["reask"] = "Is this <zork>?"
    out = run(cat, spec, wf, w)
    assert [f["msg"] for f in find(out, "placeholder", "error", "/right_party/reask")] == ["unknown placeholder <zork>"]


def test_spec_enums_in_per_field_identity_mode(cat):
    spec = _golden("spec-a.json")
    c = copy.deepcopy(cat)
    c["identity_mode"] = "per_field"
    out = []
    lint._lint_spec_enums(spec, c, out)
    req = c["tools"]["verify_identity"]["request"]
    bad = [i for i, q in enumerate(spec["identity"]["questions"]) if q["field_value"] not in req]
    assert bad, "golden questions name selector values, not request fields"
    assert [f["where"] for f in out if f["rule"] == "spec_enum" and "is not a request field" in f["msg"]] == \
        ["/identity/questions/%d/field_value" % i for i in bad]


def test_line_repeat_only_for_sentences_inside_fail_line():
    spec = {"identity": {"fail_line": "I could not confirm your identity. Goodbye."},
            "closing": {"per_situation": {"S_A": "I could not confirm your identity. Have a nice evening, friend."}}}
    out = []
    lint._lint_spec_lines(spec, out)
    assert [(f["rule"], f["where"]) for f in out] == [("line_repeat", "/closing/per_situation/S_A")]


def test_intent_scope_warning_and_bad_keyword_regex():
    spec = {"intents": [
        {"id": "I_REC", "action": {"kind": "answer_continue", "say": "Your promise is recorded."},
         "keywords": ["(unclosed", "change the (date|amount)"]},
        {"id": "I_OK", "action": {"kind": "answer_continue", "say": "It is recorded."}, "keywords": ["refund"]},
        {"id": "I_BAD", "action": {"kind": "answer_continue", "say": "Recorded."}, "keywords": ["[bad"]}]}
    out = []
    lint._lint_spec_lines(spec, out)
    assert [(f["rule"], f["where"]) for f in out] == [("intent_scope", "/intents/I_REC")]


def test_reach_sources_for_call_notes_and_missing_close_nodes():
    def node(*targets):
        return {"transitions": [{"target_node": t, "condition": {"operator": "always"}} for t in targets]}
    wf = {"initial_node": "s_open", "nodes": {"s_open": node("ctl", "a_note_call_1"), "ctl": node("a_note_call_1"),
                                              "a_note_call_1": node("ctl")}}
    w = {"api": {"note_call": ["a_note_call_1"], "close_r": "", "close_n": None}, "chainable": [], "bye": ""}
    out = []
    lint._lint_reach(wf, w, out)
    assert [(f["rule"], f["where"], f["msg"]) for f in out] == [
        ("reach_source", "a_note_call_1", "entered from unexpected nodes ['s_open']")]


def test_byte_stable_recompile_failure(cat, base, monkeypatch):
    spec, wf, w = mut(base)

    def boom(*a, **k):
        raise graph.CompileError("cannot compile")
    monkeypatch.setattr(graph, "compile_workflow", boom)
    out = lint.lint(wf, cat, spec, w, stable=True)
    assert [f["msg"] for f in find(out, "byte_stable", "error")] == ["recompile failed: cannot compile"]


# ================================================================================================ graph

def test_per_field_verify_body_binds_every_unbound_field(cat):
    c = copy.deepcopy(cat)
    c["identity_mode"] = "per_field"
    v = c["tools"]["verify_identity"]
    v["request"]["postcode"] = dict(v["request"]["answer"])
    v["roles"]["request"] = {"customer": "customer_id"}
    ent = graph._node_entry("a_verify_1", "verify_identity", c, _golden("spec-a.json"))
    assert ent["body"] == {"field": "b_a_verify_1_field", "answer": "b_a_verify_1_answer",
                           "postcode": "b_a_verify_1_postcode"}
    sel = graph._node_entry("a_verify_1", "verify_identity", cat, _golden("spec-a.json"))
    assert "postcode" not in sel["body"] and set(sel["body"]) == {"field", "answer"}


def test_required_field_without_source_gets_a_baked_literal(cat, tmp_path):
    c = copy.deepcopy(cat)
    t = c["tools"]["create_promise"]
    t["request"]["channel"] = {"type": "string", "required": True, "enum": [], "format": "", "pattern": "",
                               "description": "", "min_length": 0, "max_length": 0, "example": "voice",
                               "wire_format": "", "scale": 1}
    t["request"]["mode"] = dict(t["request"]["channel"], example="", enum=["m1", "m2"])
    t["request"]["note"] = dict(t["request"]["channel"], required=False)
    t["required"] += ["channel", "mode"]
    trace.init(tmp_path / "t", echo=False)
    wf, w = graph.compile_workflow(_golden("spec-a.json"), c, code=STUB_CODE)
    trace.close()
    fn = wf["nodes"]["a_promise_1_1"]["pre_actions"][0]["function"]
    body = fn["parameters"]["properties"]["body"]
    assert body["properties"]["channel"] == {"type": "string", "default": "voice"}
    assert body["properties"]["mode"] == {"type": "string", "default": "m1"}
    assert "note" not in body["properties"] and {"channel", "mode"} <= set(body["required"])
    assert "required field channel has no source; baked literal 'voice'" in (tmp_path / "t" / "trace.txt").read_text()


def test_make_test_variables_skips_nameless_declarations():
    spec = {"call_variables": {"customer_key": "cid", "declared": [{"name": "cid"}, {"meaning": "no name"},
                                                                   {"name": ""}]}}
    tv = graph.make_test_variables(spec)
    assert tv["cid"] == "c_test" and "" not in tv and len(tv) == 1


# ================================================================================================ critic

@pytest.mark.parametrize("rule,words", [
    ({"kind": "next_business_day"}, "the next business day"),
    ({"kind": "nth_calendar_day_after_today", "n": 3}, "today + 3 calendar days (roll none)"),
    ({"kind": "end_of_month", "roll": "back"}, "the end of the month (roll back)"),
    ({"kind": "last_business_day_of_month"}, "the last business day of the month"),
    ({"kind": "fixed", "date": "2030-01-02"}, "2030-01-02"),
    ({"kind": "max", "args": [{"kind": "today"}, {"kind": "deadline"}]}, "the latest of (today; the deadline)"),
    ({"kind": "someday"}, "someday"),
    ("not a rule", "?"),
])
def test_date_rule_words(rule, words):
    assert critic._dr(rule) == words


@pytest.mark.parametrize("rule,words", [
    ({"kind": "percent_of_full", "pct": 30}, "30% of the past-due amount (rounding half_up)"),
    ({"kind": "fixed", "value": 50}, "the fixed amount 50"),
    ({"kind": "floor_if_too_much_else_full"},
     "the floor if the customer said the full amount is too much, else the full amount"),
    ({"kind": "max", "args": [{"kind": "full"}, {"kind": "floor"}]}, "the larger of (the full past-due amount; the floor)"),
    (None, "?"),
])
def test_amount_rule_words(rule, words):
    assert critic._ar(rule) == words


@pytest.mark.parametrize("op,msg", [
    ({"op": "replace", "path": "/a/zz/b", "value": 1}, "path not found"),
    ({"op": "move", "path": "/a/k"}, "unsupported op 'move'"),
    ({"op": "add", "path": "/l/9", "value": 1}, "index out of range"),
    ({"op": "replace", "path": "/l/2", "value": 1}, "index out of range"),
    ({"op": "remove", "path": "/l/2"}, "index out of range"),
    ({"op": "copy", "path": "/l/0"}, "unsupported op 'copy'"),
    ({"op": "add", "path": "/l/x", "value": 1}, "bad list index"),
    ({"op": "add", "path": "/s/x", "value": 1}, "parent is not a container"),
])
def test_patch_errors(op, msg):
    with pytest.raises(critic.PatchError, match=msg):
        critic.apply_patches({"a": {"k": 1}, "l": [1, 2], "s": "str"}, [op])


def test_patch_list_ops():
    doc = {"l": [1, 2]}
    assert critic.apply_patches(doc, [{"op": "add", "path": "/l/2", "value": 3}]) == {"l": [1, 2, 3]}
    assert critic.apply_patches(doc, [{"op": "replace", "path": "/l/0", "value": 9}]) == {"l": [9, 2]}
    assert critic.apply_patches(doc, [{"op": "remove", "path": "/l/1"}]) == {"l": [1]}
    assert critic.apply_patches(doc, [{"op": "add", "path": "/l/-", "value": 0}]) == {"l": [1, 2, 0]}
    assert doc == {"l": [1, 2]}


# ================================================================================================ extract

def test_prune_required_non_dict_passthrough():
    assert extract._prune_required(["x"], {}) == ["x"]
    assert extract._prune_required({"required": ["a", "b"]}, "not a dict") == {"required": ["a", "b"]}
    assert extract._prune_required({"required": ["a", "b"]}, {"a": 1}) == {"required": ["b"]}


def test_catalog_summary_response_descriptions_and_no_hint():
    cat = {"server": "https://h", "identity_mode": "selector", "tools": {"t": {
        "method": "POST", "path": "/t", "request": {},
        "response": {"ok": {"type": "boolean", "description": "true when done"},
                     "list": {"type": "array", "items": {"k": {"type": "string", "description": "item key"}}}}}}}
    s = extract.catalog_summary(cat)
    assert '  - ok: boolean, "true when done"' in s and '      item k: string, "item key"' in s
    assert "sent without a reason" not in s and "\nenums: {}" in s


def test_resolve_and_number_gaps_edge_cases():
    assert extract._resolve({"a": [{"b": 1}]}, "/a/0/b") == (1, True)
    assert extract._resolve({"a": [1]}, "/a/3") == (None, False)
    vals = {"bands": ["not a band", {"days_late_min": 3}]}
    assert extract.number_gaps(vals, {"/bands/1": "from day three"}) == []
    assert extract.number_gaps(vals, {"/bands/1": "from day 4"}) == ["/bands/1: 3 not found in its quote"]


def test_clean_meta_and_failed_facets_on_odd_meta():
    assert extract.clean_meta({"meta": "str"}) == {"meta": "str"}
    assert extract.clean_meta(None) is None
    assert extract.failed_facets(None) == []


BRIEF_A = ROOT / "kit" / "briefs" / "brief-a.md"


def test_extract_without_catalog_sha_and_empty_residual_text():
    golden = _golden("spec-a.json")
    vals = {k: copy.deepcopy(golden[k]) for k in extract.FACETS["F1"]}

    def fn(req):
        return {"values": vals, "sources": [], "decisions": [],
                "residual": [{"text": "", "class": "flow"}, {"text": "kept rule", "class": "speech"}]}
    prev = llm.set_backend(fn)
    try:
        draft = extract.extract(segment.segment([str(BRIEF_A)]), {}, None, only=["F1"])
    finally:
        llm.set_backend(prev)
    assert "openapi_sha256" not in draft["meta"]
    assert draft["meta"]["residual_rules"] == [{"text": "kept rule", "class": "speech", "bound_to": "F1"}]
    assert all(draft[k] == golden[k] for k in extract.FACETS["F1"])


def test_unknown_amount_kind_and_nested_list_paths():
    assert critic._ar({"kind": "weird_rule"}) == "weird_rule"
    doc = {"rows": [{"k": 1, "drop": True}]}
    assert critic.apply_patches(doc, [{"op": "replace", "path": "/rows/0/k", "value": 2},
                                      {"op": "remove", "path": "/rows/0/drop"}]) == {"rows": [{"k": 2}]}
    with pytest.raises(critic.PatchError, match="remove of missing key"):
        critic.apply_patches(doc, [{"op": "remove", "path": "/rows/0/nope"}])
