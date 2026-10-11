"""Twin (harness/twin.py): local executor with the E1 engine semantics. Owner: agent 4.
Uses small hand-made workflows and the generic toy hub (harness/toy.py), never the compiler."""
import copy
import json

import pytest

from harness.mockbank import MockBank
from harness.toy import hub_workflow
from harness.twin import Twin, TwinError, eval_condition, run_script, substitute

CID = "c_t"


def _case(public_cases, cid="PUB-01"):
    c = copy.deepcopy(public_cases[cid])
    c["variables"]["customer_id"] = CID
    return c


def _vars(case):
    return dict(case["variables"])


PUB01_PLAN = [
    ["say", "Could you tell me your date of birth?", "s_l"],
    ["call", "verify_identity", {"field": "date_of_birth", "answer": "1988-03-14"}],
    ["say", "And the last four digits?", "s_l"],
    ["call", "verify_identity", {"field": "phone_last4", "answer": "4471"}],
    ["call", "get_account", {}],
    ["say", "It is 6 days late. Can you pay today?", "s_l"],
    ["say", "So that is 420 today. Do you confirm?", "s_l"],
    ["call", "create_promise", {"product_id": "p1", "amount": "420.00", "date": "2026-10-14"}],
    ["close", "promise", "", "Your promise is recorded. Goodbye."],
]


@pytest.fixture
def toy(catalog_kit, public_cases):
    case = _case(public_cases)
    bank = MockBank(catalog_kit, case)
    return Twin(hub_workflow(catalog_kit, PUB01_PLAN), bank, _vars(case)), bank


# ---------------------------------------------------------------- conditions / substitution
@pytest.mark.parametrize("cond,expected", [
    ({"operator": "always"}, True),
    ({"logic": "or", "conditions": [{"variable": "a", "operator": "equals", "operand": "1"}]}, True),
    ({"logic": "or", "conditions": [{"variable": "a", "operator": "equals", "operand": 1}]}, True),
    ({"logic": "or", "conditions": [{"variable": "b", "operator": "equals", "operand": "true"}]}, False),
    ({"logic": "or", "conditions": [{"variable": "b", "operator": "equals", "operand": "True"}]}, True),
    ({"logic": "and", "conditions": [{"variable": "a", "operator": "equals", "operand": "1"},
                                     {"variable": "zz", "operator": "is_set"}]}, False),
    ({"logic": "and", "conditions": []}, False),
    ({"logic": "or", "conditions": [{"logic": "and", "conditions": [
        {"variable": "a", "operator": "equals", "operand": "1"}, {"variable": "s", "operator": "contains",
                                                                   "operand": "HELLO"}]}]}, True),
    ({"variable": "a", "operator": "not_equals", "operand": "2"}, True),
    ({"variable": "missing", "operator": "not_equals", "operand": "2"}, True),
    ({"variable": "missing", "operator": "equals", "operand": ""}, False),
    ({"variable": "n", "operator": "greater_than", "operand": 2}, True),
    ({"variable": "n", "operator": "less_than", "operand": "2"}, False),
    ({"variable": "s", "operator": "greater_than", "operand": 2}, False),
    ({"variable": "missing", "operator": "less_than", "operand": 2}, False),
    ({"variable": "empty", "operator": "is_set"}, True),
    ({"variable": "missing", "operator": "is_not_set"}, True),
    ({"variable": "missing", "operator": "contains", "operand": "x"}, False),
])
def test_eval_condition(cond, expected):
    vars = {"a": "1", "b": "True", "n": "3", "s": "say hello", "empty": ""}
    assert eval_condition(cond, vars) is expected


@pytest.mark.parametrize("cond", [{"operator": "matches_intent", "description": "x"}, {}, None,
                                  {"variable": "a", "operator": "regex", "operand": "x"},
                                  {"logic": "xor", "conditions": []}])
def test_eval_condition_errors(cond):
    with pytest.raises(TwinError):
        eval_condition(cond, {"a": "1"})


def test_substitute_forms():
    v = {"x": "4", "o": {"k": 1}, "b": "True"}
    assert substitute("a {{x}} b {{ x }}", v) == "a 4 b 4"
    assert substitute("{{x:json}}", v) == '"4"'
    assert substitute("{{o}}", v) == '{"k": 1}'
    assert substitute("{{nope}} left", v) == "{{nope}} left"
    assert substitute("{{nope}}", v, drop_if_unset=True) is None
    assert substitute(" {{x}} ", v, drop_if_unset=True) == " 4 "
    assert substitute("Status: {{nope}}", v, drop_if_unset=True) == "Status: {{nope}}"
    assert substitute(None, v) is None


# ---------------------------------------------------------------- hub loop (E1)
def test_sim_hub_one_line_per_turn_and_ledger(toy, public_cases):
    twin, bank = toy
    assert twin.start() == ["Hello, am I speaking with Daniel?"]
    out = [twin.turn(s) for s in ["Yes", "14 March 1988", "4471", "Yes", "Yes, I confirm."]]
    assert all(len(lines) == 1 for lines in out)
    assert out[-1] == ["Your promise is recorded. Goodbye."]
    assert twin.ended and not twin.errors
    assert twin.hops == [1, 2, 4, 6, 2, 6]
    from harness.score import score_ledger
    assert score_ledger(public_cases["PUB-01"], bank.ledger())["pass"]
    assert twin.turn("hello?") == [] and "after the call ended" in twin.errors[-1]
    assert [r for r, _ in twin.transcript].count("customer") == 5


def test_chat_mode_first_turn_speaks_task_message_without_routing(catalog_kit, public_cases):
    case = _case(public_cases)
    twin = Twin(hub_workflow(catalog_kit, PUB01_PLAN), MockBank(catalog_kit, case), _vars(case), mode="chat")
    assert twin.start() == []
    assert twin.turn("Hello?") == ["Hello, am I speaking with Daniel?"]
    assert "u_text" not in twin.vars and twin.node == "s_open"
    assert twin.turn("Yes") == ["Could you tell me your date of birth?"]
    assert twin.vars["u_text"] == "Yes"


def test_chat_mode_without_guillemets_is_an_error(catalog_kit, public_cases):
    case = _case(public_cases)
    wf = hub_workflow(catalog_kit, PUB01_PLAN)
    wf["nodes"]["s_open"]["task_message"] = "Greet the caller."
    twin = Twin(wf, MockBank(catalog_kit, case), _vars(case), mode="chat")
    twin.start()
    assert twin.turn("Hello?") == ["Hello, am I speaking with Daniel?"]
    assert any("task_message" in e for e in twin.errors)


def test_extraction_sensors_restricted_to_schema_and_extractor(catalog_kit, public_cases):
    case = _case(public_cases)
    seen = []

    def extractor(node, schema, text, vars):
        seen.append((node, [f["name"] for f in schema]))
        return {"u_act": "yes"}
    twin = Twin(hub_workflow(catalog_kit, PUB01_PLAN), MockBank(catalog_kit, case), _vars(case), extractor=extractor)
    twin.start()
    twin.turn("Yes it's me", {"u_topic": "other_person", "u_text": "override"})
    assert twin.vars["u_act"] == "yes" and twin.vars["u_text"] == "override"
    assert "u_topic" not in twin.vars
    assert seen == [("s_open", ["u_text", "u_act"])]
    assert any(e["event"] == "sensors_ignored" and e["names"] == ["u_topic"] for e in twin.events)


def test_default_extractor_blanks_other_fields(toy):
    twin, _ = toy
    twin.start()
    twin.vars["u_act"] = "stale"
    twin.turn("Yes")
    assert twin.vars["u_act"] == ""


# ---------------------------------------------------------------- api nodes
def _api_events(twin, tool):
    return [e for e in twin.events if e["event"] == "function_call_start" and e.get("function") == tool]


def test_api_body_baked_mapping_and_flat_keys(toy):
    twin, bank = toy
    twin.start()
    twin.turn("Yes")
    twin.turn("14 March 1988")
    ev = _api_events(twin, "verify_identity")[0]
    assert ev["args"]["body"] == {"customer_id": CID, "field": "date_of_birth", "answer": "1988-03-14"}
    v = twin.vars
    assert v["r_a_verify_identity_s"] == "true" and v["r_a_verify_identity_left"] == "3"
    assert v["verify_identity_response.data.all_verified"] == "false"
    assert v["a_verify_identity_response.data.ok"] == "true"
    assert v["a_verify_identity_success_count"] == "1" and v["verify_identity_status_code"] == "200"
    assert v["verify_identity_args.field"] == "date_of_birth"
    twin.turn("4471")
    assert twin.vars["a_verify_identity_success_count"] == "2"
    prods = json.loads(twin.vars["r_a_get_account_products"])
    assert prods[0]["product_id"] == "p1" and prods[0]["past_due"] == 420
    assert twin.vars["get_account_response.data.products.0.product_id"] == "p1"


def test_styles_title_pyrepr_node_only(catalog_kit, public_cases):
    case = _case(public_cases)
    twin = Twin(hub_workflow(catalog_kit, PUB01_PLAN), MockBank(catalog_kit, case), _vars(case),
                bool_style="title", list_style="pyrepr", flat_keys="node")
    run_script(twin, ["Yes", "14 March 1988", "4471"])
    assert twin.vars["r_a_verify_identity_all"] == "True"
    assert twin.vars["r_a_get_account_products"].startswith("[{'product_id': 'p1'")
    assert not any(k.startswith("get_account_response") for k in twin.vars)
    assert twin.vars["a_get_account_response.data.products.0.type"] == "credit_card"


def test_bad_style_option_rejected(toy, catalog_kit, public_cases):
    case = _case(public_cases)
    with pytest.raises(TwinError):
        Twin(hub_workflow(catalog_kit, PUB01_PLAN), MockBank(catalog_kit, case), _vars(case), flat_keys="all")
    with pytest.raises(TwinError):
        Twin(hub_workflow(catalog_kit, PUB01_PLAN), MockBank(catalog_kit, case), _vars(case), mode="voice")


def test_http500_leaves_mapping_untouched_and_counts_failure(catalog_kit, public_cases):
    case = _case(public_cases, "PUB-10")
    plan = [["say", "dob?", "s_l"],
            ["call", "verify_identity", {"field": "date_of_birth", "answer": "1989-02-23"}],
            ["call", "verify_identity", {"field": "phone_last4", "answer": "9904"}],
            ["call", "get_account", {}],
            ["call", "create_promise", {"product_id": "p1", "amount": "365", "date": "2026-10-16"}],
            ["say", "first try done", "s_l"],
            ["call", "create_promise", {"product_id": "p1", "amount": "365", "date": "2026-10-16"}],
            ["close", "promise", "", "bye"]]
    bank = MockBank(catalog_kit, case)
    twin = Twin(hub_workflow(catalog_kit, plan), bank, _vars(case))
    run_script(twin, ["yes", "x"])
    v = twin.vars
    assert v["r_a_create_promise_s"] == "pending"                       # mapping untouched on 500
    assert v["a_create_promise_failure_count"] == "1" and v["create_promise_status_code"] == "500"
    assert "create_promise_response.data.ok" not in v
    twin.turn("ok")
    assert twin.ended and v["r_a_create_promise_s"] == "true"
    assert len(bank.ledger()["promises"]) == 1 and not twin.errors


def test_read_tool_max_retries_resends_on_500(catalog_kit, public_cases):
    case = _case(public_cases)
    case["faults"] = [{"tool": "get_account", "fail_first_n": 1}]
    bank = MockBank(catalog_kit, case)
    twin = Twin(hub_workflow(catalog_kit, PUB01_PLAN), bank, _vars(case))
    run_script(twin, ["Yes", "14 March 1988", "4471"])
    assert len(_api_events(twin, "get_account")) == 2                   # max_retries 1 on the read tool
    assert twin.vars["r_a_get_account_s"] == "true"


def test_unset_single_placeholder_drops_field_mixed_kept_literal(catalog_kit, public_cases):
    case = _case(public_cases)
    wf = hub_workflow(catalog_kit, [["call", "add_note", {"product_id": "p1"}], ["say", "ok", "s_l"]])
    body = wf["nodes"]["a_add_note"]["pre_actions"][0]["function"]["parameters"]["properties"]["body"]["properties"]
    body["text"]["default"] = "Note: {{not_set_anywhere}}"
    bank = MockBank(catalog_kit, case)
    twin = Twin(wf, bank, _vars(case))
    twin.start()
    twin.turn("hi")
    sent = _api_events(twin, "add_note")[0]["args"]["body"]
    assert "reason" not in sent and sent["text"] == "Note: {{not_set_anywhere}}"
    assert any("literal" in e for e in twin.errors)
    assert bank.ledger()["calls"][0]["result"]["error"] == "missing reason"


def test_json_placeholder_sends_decoded_value(catalog_kit, public_cases):
    case = _case(public_cases)
    wf = hub_workflow(catalog_kit, [["call", "create_promise", {"product_id": "p1", "amount": "420.5", "date": "d"}],
                                    ["say", "ok", "s_l"]])
    body = wf["nodes"]["a_create_promise"]["pre_actions"][0]["function"]["parameters"]["properties"]["body"]
    body["properties"]["amount"]["default"] = "{{b_a_create_promise_amount:json}}"
    twin = Twin(wf, MockBank(catalog_kit, case), _vars(case))
    twin.start()
    twin.turn("hi")
    assert _api_events(twin, "create_promise")[0]["args"]["body"]["amount"] == 420.5


def test_url_mismatch_and_missing_tool_are_errors(catalog_kit, public_cases):
    case = _case(public_cases)
    wf = hub_workflow(catalog_kit, [["call", "get_account", {}], ["say", "ok", "s_l"]])
    props = wf["nodes"]["a_get_account"]["pre_actions"][0]["function"]["parameters"]["properties"]
    props["url"]["default"] = "https://elsewhere.example/v1/get_account"
    twin = Twin(wf, MockBank(catalog_kit, case), _vars(case))
    twin.start()
    twin.turn("hi")
    assert any("catalog url" in e for e in twin.errors)
    wf["nodes"]["a_get_account"]["pre_actions"] = []
    twin = Twin(wf, MockBank(catalog_kit, case), _vars(case))
    twin.start()
    twin.turn("hi")
    assert any("no api_call pre_action" in e for e in twin.errors)


def test_suppress_tool_results_required(catalog_kit, public_cases):
    case = _case(public_cases)
    wf = hub_workflow(catalog_kit, [["call", "get_account", {}], ["say", "ok", "s_l"]])
    del wf["nodes"]["a_get_account"]["suppress_tool_results"]
    twin = Twin(wf, MockBank(catalog_kit, case), _vars(case))
    twin.start()
    twin.turn("hi")
    assert any("suppress_tool_results" in e for e in twin.errors)


# ---------------------------------------------------------------- code nodes and graph errors
def _mini(code, extra_nodes=None, ctl_trs=None):
    nodes = {
        "s_open": {"node_type": "conversation", "on_enter": {"type": "tts", "text": "Hi {{name}}"},
                   "extraction_schema": [{"name": "u_text"}], "transitions": [
                       {"target_node": "ctl", "condition": {"operator": "always"}}]},
        "ctl": {"node_type": "code", "passthrough": True, "passthrough_default_transition": "s_l",
                "pre_actions": [{"type": "function", "function": {
                    "name": "code_exec", "handler": "__function__:code_exec",
                    "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": code}}}}}],
                "transitions": ctl_trs or [{"target_node": "s_l", "condition": {"operator": "always"}}]},
        "s_l": {"node_type": "conversation", "on_enter": {"type": "tts", "text": "{{say}}"},
                "extraction_schema": [{"name": "u_text"}], "transitions": [
                    {"target_node": "ctl", "condition": {"operator": "always"}}]},
    }
    nodes.update(extra_nodes or {})
    return {"initial_node": "s_open", "nodes": nodes, "test_variables": {"name": "Sam"}}


class _NoBank:
    catalog = {"tools": {}}

    def call(self, tool, body):
        raise AssertionError("no bank call expected")


def test_code_node_runs_with_shared_vars_and_test_variables():
    code = "vars['say'] = 'You said ' + vars.get('u_text', '') + ' to ' + vars.get('name', '')\n"
    twin = Twin(_mini(code), _NoBank(), {"name": "Alex"})
    assert twin.start() == ["Hi Alex"]
    assert twin.turn("ping") == ["You said ping to Alex"]
    assert twin.vars["ctl_success_count"] == "1" and not twin.errors


def test_code_raise_keeps_partial_writes_and_records_error():
    code = "vars['say'] = 'partial'\nraise ValueError('boom')\n"
    twin = Twin(_mini(code), _NoBank(), {})
    twin.start()
    assert twin.turn("x") == ["partial"]
    assert twin.vars["ctl_failure_count"] == "1"
    assert any("raised ValueError" in e for e in twin.errors)


def test_code_non_string_write_and_braces_are_errors():
    code = "vars['say'] = 'n'\nvars['count'] = 3\nd = {'a': {'b': 1}}\n"
    twin = Twin(_mini(code), _NoBank(), {})
    twin.start()
    twin.turn("x")
    assert any("non-string" in e and "count" in e for e in twin.errors)
    assert any("'{{' or '}}'" in e for e in twin.errors)


def test_unresolved_tts_spoken_literally():
    twin = Twin(_mini("x = 1\n"), _NoBank(), {})
    assert twin.start() == ["Hi Sam"]
    assert twin.turn("x") == ["{{say}}"]
    assert any("unresolved say" in e for e in twin.errors)


def test_hop_limit_is_an_error():
    trs = [{"target_node": "ctl", "condition": {"operator": "always"}}]
    twin = Twin(_mini("vars['say'] = 'x'\n", ctl_trs=trs), _NoBank(), {}, max_hops=5)
    twin.start()
    assert twin.turn("x") == []
    assert twin.stuck and any("hop limit" in e for e in twin.errors)
    assert twin.turn("again") == [] and "stuck" in twin.errors[-1]


def test_passthrough_default_used_and_deadlock_detected():
    trs = [{"target_node": "s_l", "condition": {"logic": "or", "conditions": [
        {"variable": "nx", "operator": "equals", "operand": "s_l"}]}}]
    twin = Twin(_mini("vars['say'] = 'fallback'\n", ctl_trs=trs), _NoBank(), {})
    twin.start()
    assert twin.turn("x") == ["fallback"]                                 # default transition
    wf = _mini("vars['say'] = 'x'\n", ctl_trs=trs)
    del wf["nodes"]["ctl"]["passthrough_default_transition"]
    twin = Twin(wf, _NoBank(), {})
    twin.start()
    assert twin.turn("x") == [] and any("deadlock" in e for e in twin.errors)


def test_matches_intent_transition_is_error_and_false():
    trs = [{"target_node": "s_l", "condition": {"operator": "matches_intent", "description": "anything"}},
           {"target_node": "s_l", "condition": {"operator": "always"}}]
    twin = Twin(_mini("vars['say'] = 'ok'\n", ctl_trs=trs), _NoBank(), {})
    twin.start()
    assert twin.turn("x") == ["ok"]
    assert any("matches_intent" in e for e in twin.errors)


def test_duplicate_targets_merged_unconditional_wins():
    trs = [{"target_node": "s_l", "condition": {"logic": "or", "conditions": [
        {"variable": "nx", "operator": "equals", "operand": "never"}]}},
        {"target_node": "s_end", "condition": {"logic": "or", "conditions": [
            {"variable": "go", "operator": "equals", "operand": "1"}]}},
        {"target_node": "s_l", "condition": {"operator": "always"}}]
    end = {"s_end": {"node_type": "end_call", "transitions": []}}
    twin = Twin(_mini("vars['say'] = 'ok'\nvars['go'] = '1'\n", end, trs), _NoBank(), {})
    twin.start()
    assert twin.turn("x") == ["ok"]                                       # merged always jumped the queue
    assert any(e["event"] == "merged_transitions" for e in twin.events)


def test_listen_node_without_match_stays_and_errors():
    wf = _mini("vars['say'] = 'ok'\n")
    wf["nodes"]["s_open"]["transitions"] = []
    twin = Twin(wf, _NoBank(), {})
    twin.start()
    assert twin.turn("x") == [] and twin.node == "s_open"
    assert any("no transition matched" in e for e in twin.errors)


def test_static_errors_and_bad_initial():
    wf = _mini("x = 1\n")
    wf["nodes"]["s_l"]["transitions"].append({"target_node": "ghost", "condition": {"operator": "always"}})
    twin = Twin(wf, _NoBank(), {})
    assert any("ghost" in e for e in twin.errors)
    wf["initial_node"] = "nowhere"
    with pytest.raises(TwinError):
        Twin(wf, _NoBank(), {})


def test_llm_on_enter_and_unknown_node_type_are_errors():
    wf = _mini("vars['say'] = 'ok'\n")
    wf["nodes"]["s_l"]["on_enter"] = {"type": "llm"}
    twin = Twin(wf, _NoBank(), {})
    twin.start()
    assert twin.turn("x") == [] and any("model-generated" in e for e in twin.errors)
    wf = _mini("vars['say'] = 'ok'\n")
    wf["nodes"]["s_l"]["node_type"] = "transfer_call"
    twin = Twin(wf, _NoBank(), {})
    twin.start()
    twin.turn("x")
    assert twin.stuck and any("unsupported node_type" in e for e in twin.errors)


def test_first_entry_only_and_silent():
    wf = _mini("vars['say'] = 'again'\n")
    wf["nodes"]["s_l"]["on_enter_first_entry_only"] = True
    twin = Twin(wf, _NoBank(), {})
    twin.start()
    assert twin.turn("a") == ["again"]
    assert twin.turn("b") == []
    wf["nodes"]["s_l"]["on_enter"] = {"type": "silent"}
    twin = Twin(wf, _NoBank(), {})
    twin.start()
    assert twin.turn("a") == [] and not twin.errors


def test_call_vars_override_test_variables_and_turn_without_start():
    twin = Twin(_mini("vars['say'] = vars['name']\n"), _NoBank(), {"name": "Kim"})
    assert twin.turn("hello") == ["Kim"]                                  # implicit start, opening not returned
    assert twin.transcript[0] == ("agent", "Hi Kim")
