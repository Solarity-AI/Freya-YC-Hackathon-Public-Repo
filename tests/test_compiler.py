"""Tests for builder/compiler/{graph,render,snippet}.py (agent 3): golden wiring fixtures, workflow structure,
flags, byte stability, mutated OpenAPI, render rules.

Edge cases: BRF-19 call-level notes, BRF-87 renamed customer key, OPS-30 unresolved placeholders,
OPS-52 cross-process byte stability.
"""
import copy
import json
import os
import pathlib
import subprocess
import sys

import pytest

from builder import openapi_model as om
from builder.compiler import graph, lint, render, snippet
from builder.spec import vocab
from tests.test_openapi_model import (HINTS, ID_FIELDS, NOTE_REASONS, OUTCOMES, QUEUES, TYPES, kit_doc,
                                      mutated_doc)

ROOT = pathlib.Path(__file__).resolve().parent.parent
STUB_CODE = "import json\ntry:\n    vars['nx'] = 's_safe'\nexcept Exception:\n    vars['nx'] = 's_safe'\n"


@pytest.fixture(scope="module")
def cat():
    return om.load(ROOT / "kit" / "tools" / "openapi.json")


def _golden(name):
    return json.loads((ROOT / "tests" / "golden" / name).read_text())


@pytest.fixture(scope="module")
def ctl_code():
    """The real bundled snippet when the runtime is ready, else a brace-safe stub."""
    spec, c = _golden("spec-a.json"), om.load(ROOT / "kit" / "tools" / "openapi.json")
    try:
        return snippet.build_ctl_code(spec, graph.wiring(spec, c))
    except Exception:
        return STUB_CODE


def compiled(spec, c, flags=None, code=STUB_CODE):
    return graph.compile_workflow(spec, c, flags, code=code)


def mutate_spec(spec):
    s = copy.deepcopy(spec)
    for sit in s["situations"].values():
        sit["outcome"] = OUTCOMES[sit["outcome"]]
        if sit["queue"]:
            sit["queue"] = QUEUES[sit["queue"]]
        if sit["note_reason"]:
            sit["note_reason"] = NOTE_REASONS[sit["note_reason"]]
    for it in s["intents"]:
        if "queue" in it["action"]:
            it["action"]["queue"] = QUEUES[it["action"]["queue"]]
    s["outcomes"]["reasonless_outcomes"] = [OUTCOMES[o] for o in s["outcomes"]["reasonless_outcomes"]]
    for q in s["identity"]["questions"]:
        q["field_value"] = ID_FIELDS[q["field_value"]]
    for h in s["identity"]["hints"]:
        h["value"] = HINTS[h["value"]]
    s["products"]["types"] = {TYPES[k]: v for k, v in s["products"]["types"].items()}
    s["call_variables"]["customer_key"] = "client_ref"                       # BRF-87
    for d in s["call_variables"]["declared"]:
        if d["name"] == "customer_id":
            d["name"] = "client_ref"
    return s


# ------------------------------------------------------------------------------------------------ wiring

@pytest.mark.parametrize("spec_name,fixture", [("spec-a.json", "wiring_a"), ("spec-ab.json", "wiring_ab")])
def test_wiring_matches_fixture(cat, spec_name, fixture, request):
    exp = request.getfixturevalue(fixture)
    got = graph.wiring(_golden(spec_name), cat)
    for k in exp:
        assert got[k] == exp[k], k
    assert set(got) == set(exp)


def test_wiring_n_verify_capped_at_12(cat):
    s = _golden("spec-a.json")
    s["identity"]["max_wrong_total"] = 20
    assert len(graph.wiring(s, cat)["api"]["verify"]) == 12


def test_wiring_call_scoped_notes(cat):                                     # BRF-19
    s = _golden("spec-ab.json")
    s["notes"]["scope"] = "call"
    w = graph.wiring(s, cat)
    assert w["api"]["note"] == [] and w["api"]["note_call"] == ["a_note_call_1"]
    assert w["nodes"]["a_note_call_1"]["body"] == {"reason": "b_a_note_call_1_reason"}
    assert "a_note_call_1" in w["chainable"]


def test_wiring_notes_text_adds_text_field(cat):
    s = _golden("spec-ab.json")
    s["notes"]["text"] = "Generic note text."
    w = graph.wiring(s, cat)
    assert w["nodes"]["a_note_1"]["body"]["text"] == "b_a_note_1_text"


def test_wiring_optional_spokes(cat):
    s = _golden("spec-a.json")
    del s["third_party"]["callback"]
    for sit in s["situations"].values():
        sit["queue"] = ""
    for it in s["intents"]:
        it["action"].pop("queue", None)
    w = graph.wiring(s, cat)
    assert w["api"]["cb"] == [] and w["api"]["xfer"] == []
    assert not any(n.startswith(("a_cb", "a_xfer")) for n in w["nodes"])


def test_wiring_chain_off_and_http_ok_tools(cat):
    s = _golden("spec-ab.json")
    w = graph.wiring(s, cat, {"write_chain": "off"})
    assert w["chain"] is False and w["chainable"] == []
    d = kit_doc()
    del d["paths"]["/transfer_to_agent"]["post"]["responses"]["200"]["content"]["application/json"]["schema"][
        "properties"]["ok"]
    w2 = graph.wiring(s, om.build_catalog(d))
    assert not any(n.startswith("a_xfer") for n in w2["chainable"])


def test_bad_flags_raise(cat):
    with pytest.raises(graph.CompileError):
        graph.wiring(_golden("spec-a.json"), cat, {"bye": "terminal"})
    with pytest.raises(graph.CompileError):
        graph.wiring(_golden("spec-a.json"), cat, {"nope": "x"})


# ------------------------------------------------------------------------------------------------ workflow shape

FLAG_SETS = [{}, {"bye": "apinode"}, {"bye": "listen"}, {"write_chain": "off"}, {"amount_tpl": "json"}]


@pytest.mark.parametrize("spec_name", ["spec-a.json", "spec-ab.json"])
@pytest.mark.parametrize("flags", FLAG_SETS)
def test_golden_compiles_lint_clean(cat, spec_name, flags, ctl_code):
    spec = _golden(spec_name)
    wf, w = compiled(spec, cat, flags, code=ctl_code)
    findings = lint.lint(wf, cat, spec, w)
    assert not lint.errors(findings), lint.errors(findings)
    assert not [f for f in findings if f["rule"] in ("disclosure_word", "byte_stable")], findings


def test_top_level_shape(cat):
    wf, _ = compiled(_golden("spec-a.json"), cat)
    assert set(wf) == {"initial_node", "system_prompt", "nodes", "global_nodes", "test_variables"}
    assert wf["initial_node"] == "s_open" and wf["global_nodes"] == {}
    assert wf["test_variables"] == {"customer_id": "c_test", "first_name": "Test", "last_name": "Test",
                                    "title": "Test", "now": graph.TEST_NOW}
    assert "null" not in json.dumps(wf)
    assert "matches_intent" not in json.dumps(wf)


def test_node_set_a(cat):
    wf, _ = compiled(_golden("spec-a.json"), cat)
    expect = {"s_open", "ctl", "s_rp", "s_tp", "s_id", "s_neg", "s_conf", "s_safe", "s_bye", "e_end",
              "a_acct_1", "a_acct_2", "a_promise_1_1", "a_promise_1_2", "a_cb_1", "a_cb_2", "a_xfer_1", "a_xfer_2",
              "a_close_r", "a_close_n"} | {"a_verify_%d" % i for i in range(1, 9)}
    assert set(wf["nodes"]) == expect
    for k, n in wf["nodes"].items():
        assert n["name"] == k


def test_open_node(cat):
    wf, _ = compiled(_golden("spec-a.json"), cat)
    n = wf["nodes"]["s_open"]
    line = ("Hello, I am a digital assistant calling from Freya Bank, and we record this call. "
            "Am I speaking with {{title}} {{last_name}}?")
    assert n["on_enter"] == {"type": "tts", "text": line}
    assert n["task_message"] == "Say exactly this and nothing else, and do not call any tool: \u00ab" + line + "\u00bb"
    assert n["transitions"] == [{"target_node": "ctl", "description": "always", "condition": {"operator": "always"}}]
    assert [x["name"] for x in n["extraction_schema"]] == ["u_text", "u_act", "u_topic"]
    assert not n.get("passthrough")


def test_listen_nodes(cat):
    spec = _golden("spec-ab.json")
    wf, _ = compiled(spec, cat)
    for st, slots in (("rp", []), ("tp", ["u_date", "u_time"]), ("id", ["u_ans"]), ("neg", ["u_date", "u_amt"]),
                      ("conf", ["u_date", "u_amt"])):
        n = wf["nodes"]["s_" + st]
        assert n["on_enter"] == {"type": "tts", "text": "{{say}}"}
        assert n["task_message"] == graph.LISTEN_TASK
        assert n["max_node_turns"] == 100 and n["max_turn_transition"] == "ctl"
        assert [x["name"] for x in n["extraction_schema"]] == ["u_text", "u_act", "u_topic"] + slots
        assert n["transitions"] == [graph._always("ctl")]
    safe = wf["nodes"]["s_safe"]
    assert safe["on_enter"]["text"] == spec["lines"]["clarify"]
    assert "{{say}}" not in safe["task_message"] and spec["lines"]["clarify"] in safe["task_message"]
    assert [x["name"] for x in safe["extraction_schema"]] == ["u_text", "u_act"]


def test_ctl_node(cat, ctl_code):
    wf, w = compiled(_golden("spec-ab.json"), cat, code=ctl_code)
    n = wf["nodes"]["ctl"]
    assert n["node_type"] == "code" and n["passthrough"] is True
    assert n["passthrough_default_transition"] == "s_safe"
    assert n["on_enter"] == {"type": "silent"}
    props = n["pre_actions"][0]["function"]["parameters"]["properties"]
    assert props["code"]["default"] == ctl_code and props["timeout_ms"]["default"] == 20000
    trs = n["transitions"]
    api = graph.api_nodes(w)
    assert [t["target_node"] for t in trs] == api + ["s_rp", "s_tp", "s_id", "s_neg", "s_conf", "s_bye", "s_safe"]
    first = trs[0]["condition"]
    assert first == {"logic": "or", "conditions": [{"logic": "and", "conditions": [
        {"variable": "nx", "operator": "equals", "operand": "a_verify_1"},
        {"variable": "r_a_verify_1_s", "operator": "equals", "operand": "pending"}]}]}
    assert trs[len(api)]["condition"] == {"logic": "or", "conditions": [
        {"variable": "nx", "operator": "equals", "operand": "s_rp"}]}
    assert trs[-1] == graph._always("s_safe")
    assert "s_open" not in [t["target_node"] for t in trs]


def test_api_node_binding(cat):
    wf, _ = compiled(_golden("spec-a.json"), cat)
    n = wf["nodes"]["a_promise_1_1"]
    assert n["node_type"] == "api_request" and n["passthrough"] is True
    assert n["suppress_tool_results"] is True and n["disable_inactivity_monitor"] is True
    assert n["passthrough_default_transition"] == "ctl"
    pa = n["pre_actions"][0]
    assert pa["config"] == {"timeoutMs": 12000, "maxRetries": 0}
    fn = pa["function"]
    assert fn["name"] == "create_promise" and fn["handler"] == "__function__:api_call"
    p = fn["parameters"]["properties"]
    assert p["url"]["default"] == "https://freya-bank-mock.freyavoice.workers.dev/v1/create_promise"
    assert p["method"]["default"] == "POST"
    body = p["body"]
    assert body["required"] == ["customer_id", "product_id", "amount", "date"]
    assert body["properties"] == {
        "customer_id": {"type": "string", "default": "{{customer_id}}"},
        "product_id": {"type": "string", "default": "{{b_a_promise_1_1_product_id}}"},
        "amount": {"type": "number", "default": "{{b_a_promise_1_1_amount}}"},
        "date": {"type": "string", "default": "{{b_a_promise_1_1_date}}"}}
    assert n["response_mapping"] == [{"path": "data.ok", "variable": "r_a_promise_1_1_s"},
                                     {"path": "data.error", "variable": "r_a_promise_1_1_err"},
                                     {"path": "data.promise_id", "variable": "r_a_promise_1_1_pid"}]
    acct = wf["nodes"]["a_acct_1"]["pre_actions"][0]
    assert acct["config"]["maxRetries"] == 1
    assert wf["nodes"]["a_verify_1"]["pre_actions"][0]["config"]["maxRetries"] == 0
    vb = wf["nodes"]["a_verify_3"]["pre_actions"][0]["function"]["parameters"]["properties"]["body"]["properties"]
    assert vb["field"] == {"type": "string", "default": "{{b_a_verify_3_field}}",
                           "enum": ["date_of_birth", "phone_last4"]}


def test_amount_tpl_json(cat):
    wf, _ = compiled(_golden("spec-a.json"), cat, {"amount_tpl": "json"})
    b = wf["nodes"]["a_promise_1_1"]["pre_actions"][0]["function"]["parameters"]["properties"]["body"]["properties"]
    assert b["amount"]["default"] == "{{b_a_promise_1_1_amount:json}}"
    assert b["date"]["default"] == "{{b_a_promise_1_1_date}}"


def test_close_nodes_and_bye(cat):
    wf, _ = compiled(_golden("spec-a.json"), cat)
    br = wf["nodes"]["a_close_r"]["pre_actions"][0]["function"]["parameters"]["properties"]["body"]
    bn = wf["nodes"]["a_close_n"]["pre_actions"][0]["function"]["parameters"]["properties"]["body"]
    assert br["properties"]["outcome"]["default"] == "{{co}}" and br["properties"]["reason"]["default"] == "{{cr}}"
    assert "reason" not in bn["properties"] and bn["required"] == ["customer_id", "outcome"]
    for k in ("a_close_r", "a_close_n"):
        assert wf["nodes"][k]["transitions"] == [graph._always("e_end")]
        assert wf["nodes"][k]["on_enter"] == {"type": "silent"}
    bye = wf["nodes"]["s_bye"]
    assert bye["passthrough"] is True and bye["on_enter"] == {"type": "tts", "text": "{{say}}"}
    assert [t["target_node"] for t in bye["transitions"]] == ["a_close_r", "a_close_n"]
    assert bye["transitions"][0]["condition"] == {"logic": "or", "conditions": [
        {"variable": "cmode", "operator": "equals", "operand": "r"}]}
    end = wf["nodes"]["e_end"]
    assert end["node_type"] == "end_call" and end["transitions"] == []
    assert end["terminal"]["function"]["name"] == "call_closed"
    assert end["terminal"]["function"]["parameters"]["properties"]["message_mode"]["default"] == "none"


def test_bye_apinode_and_listen(cat):
    wf, w = compiled(_golden("spec-a.json"), cat, {"bye": "apinode"})
    assert "s_bye" not in wf["nodes"] and w["bye"] == ""
    assert wf["nodes"]["a_close_n"]["on_enter"] == {"type": "tts", "text": "{{say}}"}
    assert "s_bye" not in [t["target_node"] for t in wf["nodes"]["ctl"]["transitions"]]
    assert "s_bye" not in [t["target_node"] for t in wf["nodes"]["a_promise_1_1"]["transitions"]]
    wf2, _ = compiled(_golden("spec-a.json"), cat, {"bye": "listen"})
    bye = wf2["nodes"]["s_bye"]
    assert not bye.get("passthrough") and bye["transitions"] == [graph._always("ctl")]


def test_chain_transitions(cat):
    wf, w = compiled(_golden("spec-ab.json"), cat)
    p11 = wf["nodes"]["a_promise_1_1"]["transitions"]
    targets = [t["target_node"] for t in p11]
    assert targets[-1] == "ctl" and graph._always("ctl") == p11[-1]
    assert "a_promise_1_1" not in targets
    assert {"a_promise_2_1", "a_note_1", "a_xfer_1", "s_bye", "a_close_r", "a_close_n"} <= set(targets)
    assert not any(t.startswith("a_cb") for t in targets)
    link = next(t for t in p11 if t["target_node"] == "a_promise_2_1")["condition"]
    assert link == {"logic": "or", "conditions": [
        {"logic": "and", "conditions": [
            {"variable": "wn_a_promise_1_1", "operator": "equals", "operand": "a_promise_2_1"},
            {"variable": "r_a_promise_1_1_s", "operator": "equals", "operand": v},
            {"variable": "r_a_promise_2_1_s", "operator": "equals", "operand": "pending"}]}
        for v in ("true", "True")]}
    to_bye = next(t for t in p11 if t["target_node"] == "s_bye")["condition"]["conditions"][0]["conditions"]
    assert len(to_bye) == 2                                                 # no pending guard into a listen node
    note_t = [t["target_node"] for t in wf["nodes"]["a_note_2"]["transitions"]]
    assert not any(t.startswith("a_promise") for t in note_t) and "a_note_1" in note_t
    assert [t["target_node"] for t in wf["nodes"]["a_cb_1"]["transitions"]] == ["s_bye", "a_close_r", "a_close_n",
                                                                                "ctl"]
    assert [t["target_node"] for t in wf["nodes"]["a_xfer_1"]["transitions"]] == ["s_bye", "a_close_r",
                                                                                  "a_close_n", "ctl"]
    # identity chain (vchain): all verified -> account read, verified -> ID listen node, else ctl
    assert [t["target_node"] for t in wf["nodes"]["a_verify_1"]["transitions"]] == ["a_acct_1", "a_acct_2", "s_id",
                                                                                    "ctl"]


def test_write_chain_off(cat):
    wf, _ = compiled(_golden("spec-ab.json"), cat, {"write_chain": "off"})
    for k, n in wf["nodes"].items():
        if n["node_type"] == "api_request" and not k.startswith("a_close"):
            assert n["transitions"] == [graph._always("ctl")], k


def test_compile_is_byte_stable_in_process(cat, ctl_code):
    a, wa = compiled(_golden("spec-ab.json"), cat, code=ctl_code)
    b, wb = compiled(_golden("spec-ab.json"), cat, code=ctl_code)
    assert graph.dumps(a) == graph.dumps(b) and graph.dumps(wa) == graph.dumps(wb)


def test_compile_is_byte_stable_across_processes():                         # OPS-52
    prog = ("import json,hashlib,sys\n"
            "from builder import openapi_model as om\n"
            "from builder.compiler import graph\n"
            "c = om.load('kit/tools/openapi.json')\n"
            "s = json.load(open('tests/golden/spec-ab.json'))\n"
            "wf, w = graph.compile_workflow(s, c, code='x = 1\\n')\n"
            "sys.stderr.write('SHA=' + hashlib.sha256(graph.dumps([wf, w]).encode()).hexdigest() + '\\n')\n")
    shas = set()
    for seed in ("1", "2", "987"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        r = subprocess.run([sys.executable, "-c", prog], cwd=ROOT, env=env, capture_output=True, text=True,
                           timeout=60)
        assert r.returncode == 0, r.stderr[-2000:]
        shas |= {ln for ln in r.stderr.splitlines() if ln.startswith("SHA=")}
    assert len(shas) == 1


def test_compile_does_not_mutate_inputs(cat):
    spec = _golden("spec-ab.json")
    s0, c0 = json.dumps(spec, sort_keys=True), json.dumps(cat, sort_keys=True)
    compiled(spec, cat)
    assert json.dumps(spec, sort_keys=True) == s0 and json.dumps(cat, sort_keys=True) == c0


def test_real_snippet_is_brace_safe_and_embeds_runtime_spec(cat):
    spec = _golden("spec-ab.json")
    w = graph.wiring(spec, cat)
    try:
        code = snippet.build_ctl_code(spec, w)
    except snippet.SnippetError:
        raise                                                   # our own re-check failed: a real defect
    except Exception as e:                                      # runtime bundler still in progress (agent 2)
        pytest.skip("runtime bundle not ready: %s: %s" % (type(e).__name__, str(e)[:200]))
    assert "{{" not in code and "}}" not in code
    compile(code, "ctl", "exec")
    rs = snippet.runtime_spec(spec, w)
    from runtime import bundle, brain
    assert len(code.encode()) <= lint.CODE_MAX_BYTES                 # live code_exec limit (code + data <= 128 KiB)
    inner = bundle.unpack_snippet(code)
    assert inner != code, "ctl code is not packed"
    ns = {}
    exec(inner.split("globals().update")[0], ns)                    # defines RSPEC_HEX (JSON text encoding)
    rs = dict(rs, wiring=bundle.compact_wiring(rs["wiring"]))       # conventional nodes ship compacted
    rs["spec"]["turn_cap"] = brain._b_dec(ns["RSPEC_HEX"])["spec"]["turn_cap"]     # the budget the 1st pack allows
    assert snippet.MIN_TURN_CAP <= rs["spec"]["turn_cap"] <= lint.turns_to_limit(code) - snippet.TURN_MARGIN + 1
    assert brain._b_dec(ns["RSPEC_HEX"]) == json.loads(json.dumps(rs))
    for n in w["nodes"]:                                            # ...and expand back to the full node
        assert brain._b_node(rs["wiring"], n) == w["nodes"][n], n
    v = {}
    exec(code, {"vars": v})                                          # the loader runs the inner snippet
    assert v.get("nx") and v.get("nx") != "s_safe" and "dbg_err" not in v, v


# ------------------------------------------------------------------------------------------------ mutated OpenAPI

def test_mutated_openapi_compiles_lint_clean():
    mc = om.build_catalog(mutated_doc(), "x")
    spec = mutate_spec(_golden("spec-ab.json"))
    wf, w = compiled(spec, mc)
    findings = lint.lint(wf, mc, spec, w)
    assert not lint.errors(findings), lint.errors(findings)
    p = wf["nodes"]["a_promise_2_1"]["pre_actions"][0]["function"]["parameters"]["properties"]
    assert p["url"]["default"] == "https://bank.example.test/api/v2/ops/create-promise"
    assert set(p["body"]["properties"]) == {"client_ref", "account_ref", "amount_cents", "pay_on"}
    assert p["body"]["properties"]["client_ref"]["default"] == "{{client_ref}}"
    assert w["wire"]["create_promise.amount_cents"] == {"type": "integer", "format": "", "scale": 100}
    vmap = wf["nodes"]["a_verify_1"]["response_mapping"]
    assert {"path": "data.attempts_remaining", "variable": "r_a_verify_1_left"} in vmap
    bn = wf["nodes"]["a_close_n"]["pre_actions"][0]["function"]["parameters"]["properties"]["body"]["properties"]
    assert set(bn) == {"client_ref", "result"} and bn["result"]["enum"] == list(OUTCOMES.values())
    assert w["roles"]["get_account"]["item"] == {"id": "account_ref", "type": "kind", "past_due": "amount_overdue",
                                                 "days_late": "days_overdue"}
    text = json.dumps(wf)
    for old in ("customer_id", "wrong_answers_left", "\"restructuring\"", "\"no_promise\""):
        assert old not in text, old


def test_golden_spec_against_mutated_openapi_fails_enum_lint():
    mc = om.build_catalog(mutated_doc(), "x")
    spec = _golden("spec-a.json")
    wf, w = compiled(spec, mc)
    rules = {f["rule"] for f in lint.errors(lint.lint(wf, mc, spec, w, stable=False))}
    assert "spec_enum" in rules


# ------------------------------------------------------------------------------------------------ render

def test_compile_line(cat):
    spec = _golden("spec-a.json")
    assert render.compile_line("<self> calling <bank>.", spec) == \
        "Freya Bank's digital assistant calling Freya Bank."
    assert render.compile_line("Hi <customer>, <v:first_name>!", spec) == "Hi {{title}} {{last_name}}, {{first_name}}!"
    assert render.compile_line("", spec) == ""
    for bad in ("<amount> due", "<f:x>", "<v:nope>", "<weird>", "{{x}}", "<v:bad-name>"):
        with pytest.raises(render.RenderError):
            render.compile_line(bad, spec)


def test_strip_runtime(cat):
    spec = _golden("spec-a.json")
    assert render.strip_runtime("Pay <amount> to <bank> by <date>.", spec) == "Pay to Freya Bank by ."


def test_system_prompt(cat):
    sp = render.system_prompt(_golden("spec-a.json"))
    assert "Speak English." in sp and "Never call a tool." in sp and "Freya Bank's digital assistant" in sp
    s = _golden("spec-a.json")
    s["bank"]["language"] = "de"
    assert "Speak German." in render.system_prompt(s)


def test_extraction_schema_shapes():
    spec = _golden("spec-ab.json")
    for st in render.STAGES:
        fields = render.extraction_schema(st, spec)
        for f in fields:
            assert f["type"] == "string" and "min_confidence" in f
        names = [f["name"] for f in fields]
        assert names[:2] == ["u_text", "u_act"]
        assert fields[0]["min_confidence"] == 0.3 and fields[1]["enum_values"] == list(vocab.U_ACT_VALUES)
    with pytest.raises(render.RenderError):
        render.extraction_schema("nope", spec)


def test_topic_values_order_and_builtins():
    spec = _golden("spec-ab.json")
    assert render.topic_values("rp", spec) == ["deceased", "wrong_number", "robot", "scam", "other_person",
                                               "unavailable", "hold", "none"]
    assert render.topic_values("id", spec) == ["human", "refuse_talk", "robot", "scam", "purpose_question", "none"]
    neg = render.topic_values("neg", spec)
    assert neg[0] == "hardship" and neg[-1] == "none" and len(neg) == 12
    assert neg.index("forbidden_offer") < neg.index("change_promise")    # precedence 6 before 5
    assert render.topic_values("safe", spec) == []


def test_topic_cap_keeps_highest_precedence():
    spec = _golden("spec-a.json")
    for i in range(6):
        spec["intents"].append({"id": "extra_%d" % i, "label": "x", "description": "x", "examples": [],
                                "negatives": [], "keywords": [], "scope": ["neg"], "precedence": 1,
                                "product_scoped": False, "action": {"kind": "answer_continue", "say": "Okay."}})
    vals = render.topic_values("neg", spec)
    assert len(vals) == vocab.TOPIC_CAP and vals[-1] == "none"
    assert not any(v.startswith("extra_") for v in vals)


def test_topic_description_is_brace_free_and_lists_examples():
    spec = _golden("spec-a.json")
    spec["intents"][0]["examples"] = ['He said "{{x}}" and died.']
    f = next(x for x in render.extraction_schema("rp", spec) if x["name"] == "u_topic")
    assert "{{" not in f["description"] and "deceased:" in f["description"] and "e.g." in f["description"]


# ------------------------------------------------------------------------------------------------ snippet

def test_runtime_spec_strips_meta_and_extraction_only_fields():
    spec = _golden("spec-a.json")
    rs = snippet.runtime_spec(spec, {"v": 1})
    assert rs["v"] == 1 and rs["wiring"] == {"v": 1}
    assert "meta" not in rs["spec"]
    for it in rs["spec"]["intents"]:
        assert not set(it) & {"label", "description", "examples", "negatives"}
        assert "keywords" in it
    assert "confirm_examples" not in rs["spec"]["right_party"]
    assert "meta" in spec and "label" in spec["intents"][0]                # input untouched


def test_check_code():
    assert snippet.check_code("x = 1\n") == []
    assert snippet.check_code("") == ["empty code"]
    assert any("braces" in p for p in snippet.check_code("d = {'a': {'b': 1}}\n"))
    assert any("compile" in p for p in snippet.check_code("def (:\n"))


def test_build_ctl_code_rejects_bad_bundle(monkeypatch):
    from runtime import bundle
    monkeypatch.setattr(bundle, "make_snippet", lambda rspec, **kw: "x = {'a': {'b': 1}}\n")
    with pytest.raises(snippet.SnippetError):
        snippet.build_ctl_code(_golden("spec-a.json"), {"v": 1})
