"""Coverage + behaviour for harness/twin.py: engine semantics on small hand-made workflows (docs/CONTRACTS.md E.1)."""
import pytest

from harness.twin import Twin, TwinError, _merge_transitions, _walk, eval_condition, run_script, substitute

URL = "https://bank.example/v1/"


def _always(t):
    return {"target_node": t, "condition": {"operator": "always"}}


def _eq(t, var, val):
    return {"target_node": t, "condition": {"logic": "or", "conditions": [
        {"variable": var, "operator": "equals", "operand": val}]}}


def _listen(text, trs, schema=None, **kw):
    n = {"node_type": "conversation", "on_enter": {"type": "tts", "text": text},
         "extraction_schema": schema if schema is not None else [{"name": "u_text"}], "transitions": trs}
    n.update(kw)
    return n


def _code(code, trs, passthrough=True, handler="__function__:code_exec", extra_pre=None):
    pre = list(extra_pre or [])
    pre.append({"type": "function", "function": {"name": "code_exec", "handler": handler, "parameters": {
        "type": "object", "properties": {"code": {"type": "string", "default": code}}}}})
    return {"node_type": "code", "passthrough": passthrough, "pre_actions": pre, "transitions": trs}


def _api(tool, body_props, mapping, trs, url=None, retries=0):
    return {"node_type": "api_request", "passthrough": True, "suppress_tool_results": True,
            "pre_actions": [{"type": "function", "config": {"maxRetries": retries}, "function": {
                "name": tool, "handler": "__function__:api_call", "parameters": {"type": "object", "properties": {
                    "url": {"type": "string", "default": url if url is not None else URL + tool},
                    "method": {"type": "string", "default": "POST"},
                    "body": {"type": "object", "properties": body_props}}}}}],
            "response_mapping": mapping, "transitions": trs}


class Bank:
    def __init__(self, replies=None, tools=("get_account",)):
        self.catalog = {"tools": {t: {"url": URL + t} for t in tools}}
        self.replies = list(replies or [(200, {"ok": True})])
        self.sent = []

    def call(self, tool, body):
        self.sent.append((tool, body))
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


def _wf(nodes, init="s_open", tv=None):
    return {"initial_node": init, "nodes": nodes, "test_variables": tv or {}}


# ---------------------------------------------------------------- pure helpers
def test_substitute_stringifies_like_the_engine():
    vars = {"n": None, "f": 3.0, "g": 2.5, "b": False, "l": [1, "a"], "d": {"k": 1}, "i": 7}
    assert substitute("{{n}}|{{f}}|{{g}}|{{b}}|{{l}}|{{d}}|{{i}}", vars) == '|3|2.5|false|[1, "a"]|{"k": 1}|7'
    assert substitute("{{f:json}} {{ b }}", vars) == "3.0 false"
    assert substitute(5, vars) == 5
    assert substitute("{{missing}}", vars, drop_if_unset=True) is None
    assert substitute("{{n}}", vars, drop_if_unset=True) == ""


@pytest.mark.parametrize("cond,want", [
    ({"variable": "x", "operator": "greater_than", "operand": "2"}, True),
    ({"variable": "x", "operator": "less_than", "operand": 2}, False),
    ({"variable": "s", "operator": "greater_than", "operand": "1"}, False),      # non-numeric: false, no error
    ({"variable": "nope", "operator": "less_than", "operand": "1"}, False),
    ({"variable": "x", "operator": "is_not_set"}, False),
    ({"variable": "nope", "operator": "is_not_set"}, True),
    ({"variable": "s", "operator": "contains", "operand": "EL"}, True),
    ({"variable": "nope", "operator": "contains", "operand": ""}, False),
])
def test_eval_condition_comparisons(cond, want):
    assert eval_condition(cond, {"x": "3", "s": "hello"}) is want


def test_eval_condition_unknown_logic_and_operator():
    with pytest.raises(TwinError, match="unknown logic"):
        eval_condition({"logic": "xor", "conditions": []}, {})
    with pytest.raises(TwinError, match="unknown operator"):
        eval_condition({"variable": "a", "operator": "starts_with", "operand": "x"}, {})


def test_merge_two_conditional_transitions_to_same_target_is_or():
    trs = [_eq("A", "x", "1"), _eq("B", "y", "1"), _eq("A", "x", "2")]
    out = _merge_transitions(trs)
    assert [t["target_node"] for t in out] == ["A", "B"] and out[0]["_merged"]
    assert eval_condition(out[0]["condition"], {"x": "2"}) and eval_condition(out[0]["condition"], {"x": "1"})
    assert not eval_condition(out[0]["condition"], {"x": "3"})
    assert "_merged" not in trs[0]                                         # input is not mutated


def test_walk_dicts_and_lists():
    obj = {"data": {"products": [{"id": "p1"}, {"id": "p2"}]}}
    assert _walk(obj, "data.products.1.id") == (True, "p2")
    assert _walk(obj, "data.products.2.id") == (False, None)
    assert _walk(obj, "data.products.x") == (False, None)
    assert _walk(obj, "data.products.0.id.more") == (False, None)


# ---------------------------------------------------------------- conversation / routing
def test_routing_error_counts_false_and_next_transition_wins():
    bad = {"target_node": "s_bad", "condition": {"variable": "u_text", "operator": "regex", "operand": "x"}}
    nodes = {"s_open": _listen("Hi", [bad, _always("s_two")]), "s_bad": _listen("bad", []),
             "s_two": _listen("Two", [])}
    tw = Twin(_wf(nodes), Bank(), {})
    assert tw.start() == ["Hi"]
    assert tw.turn("x") == ["Two"]
    assert tw.errors == ["node s_open: unknown operator 'regex'"]


def test_transition_to_missing_node_makes_the_twin_stuck():
    nodes = {"s_open": _listen("Hi", [_always("ghost")])}
    tw = Twin(_wf(nodes), Bank(), {})
    assert tw.errors == ["node s_open: transition target 'ghost' does not exist"]
    tw.start()
    assert tw.turn("x") == [] and tw.stuck
    assert tw.errors[-1] == "transition to unknown node 'ghost'"
    assert tw.turn("again") == [] and tw.errors[-1] == "customer turn while the twin is stuck"


def test_end_call_spoken_message_is_said_and_later_turns_are_errors():
    nodes = {"s_open": _listen("Hi {{first_name}}", [_always("e_end")]),
             "e_end": {"node_type": "end_call", "spoken_message": "Bye {{first_name}}.", "transitions": []}}
    tw = Twin(_wf(nodes, tv={"first_name": "Test"}), Bank(), {"first_name": "Ana"})
    assert run_script(tw, ["ok", "ignored"]) == [["Hi Ana"], ["Bye Ana."]]              # stops once ended
    assert tw.ended and tw.turn("late") == [] and tw.errors == ["customer turn after the call ended"]


def test_run_script_tuple_turns_pass_sensors():
    schema = [{"name": "u_text"}, {"name": "u_act"}]
    nodes = {"s_open": _listen("Hi", [_eq("s_yes", "u_act", "yes"), _always("s_no")], schema),
             "s_yes": _listen("Yes path", []), "s_no": _listen("No path", [])}
    tw = Twin(_wf(nodes), Bank(), {})
    assert run_script(tw, [("words", {"u_act": "yes"})]) == [["Hi"], ["Yes path"]]
    tw = Twin(_wf(nodes), Bank(), {})
    assert run_script(tw, [("words",)]) == [["Hi"], ["No path"]]
    assert tw.vars["u_act"] == "" and tw.vars["u_text"] == "words"


def test_chat_first_turn_without_guillemets_or_tts_says_nothing():
    nodes = {"s_open": {"node_type": "conversation", "on_enter": {"type": "llm"}, "task_message": "Greet them.",
                        "transitions": [_always("s_open")]}}
    tw = Twin(_wf(nodes), Bank(), {}, mode="chat")
    assert tw.start() == [] and tw.turn("Hello?") == []
    assert tw.errors == ["chat turn 1: initial node has no «…» task_message; nothing would be said reliably"]
    assert tw.hops == [0, 0]


def test_extractor_value_none_written_as_empty_string():
    schema = [{"name": "u_text"}, {"name": "u_amt"}]
    nodes = {"s_open": _listen("Hi", [_always("s_open")], schema)}
    tw = Twin(_wf(nodes), Bank(), {}, extractor=lambda key, sch, text, vars: {"u_amt": None, "u_text": "X"})
    tw.start()
    tw.turn("raw")
    assert tw.vars["u_amt"] == "" and tw.vars["u_text"] == "X"


def test_bad_mode_rejected():
    wf, bank = _wf({"s_open": _listen("Hi", [])}), Bank()
    with pytest.raises(TwinError, match="mode must be sim or chat"):
        Twin(wf, bank, {}, mode="voice")


# ---------------------------------------------------------------- code nodes
def test_code_node_not_passthrough_is_error_but_still_routes():
    nodes = {"s_open": _listen("Hi", [_always("ctl")]),
             "ctl": _code("vars['say'] = 'done'\n", [_always("s_l")], passthrough=False),
             "s_l": _listen("{{say}}", [])}
    tw = Twin(_wf(nodes), Bank(), {})
    tw.start()
    assert tw.turn("x") == ["done"]
    assert tw.errors == ["node ctl: code node is not passthrough"]


def test_code_node_without_code_exec_default_counts_failure():
    other = {"type": "function", "function": {"name": "log", "handler": "__function__:log"}}
    nodes = {"s_open": _listen("Hi", [_always("ctl")]),
             "ctl": _code(None, [_always("s_l")], handler="__function__:other", extra_pre=[other]),
             "s_l": _listen("Next", [])}
    tw = Twin(_wf(nodes), Bank(), {})
    tw.start()
    assert tw.turn("x") == ["Next"]
    assert tw.errors == ["code node ctl: no code_exec default code"]
    assert tw.vars["ctl_failure_count"] == "1" and "ctl_success_count" not in tw.vars


def test_code_write_outside_enum_is_reverted_like_the_platform():
    enum_schema = [{"name": "u_text"}, {"name": "phase", "enum_values": ["a", "b"]},
                   {"name": "mode", "enum_values": [1]}, "not-a-dict"]
    code = "vars['phase'] = 'zzz'\nvars['mode'] = 'bad'\nvars['say'] = vars['phase']\n"
    nodes = {"s_open": _listen("Hi", [_always("ctl")]),
             "ctl": _code(code, [_always("s_l")]), "s_l": _listen("{{say}}", [], enum_schema)}
    tw = Twin(_wf(nodes), Bank(), {"phase": "a"})
    tw.start()
    assert tw.turn("x") == ["zzz"]                                       # `say` is not an enum variable
    assert tw.vars["phase"] == "a" and "mode" not in tw.vars             # old value stays; a new key is removed
    assert sorted(tw.errors) == ["code node ctl wrote 'bad' to enum variable mode (platform rejects it)",
                                 "code node ctl wrote 'zzz' to enum variable phase (platform rejects it)"]
    done = [e for e in tw.events if e.get("event") == "function_call_complete"][-1]
    assert done["writes"].get("say") == "zzz" and "phase" not in done["writes"] and "mode" not in done["writes"]


def test_code_enum_write_inside_enum_is_kept():
    enum_schema = [{"name": "u_text"}, {"name": "phase", "enum_values": ["a", "b"]}]
    nodes = {"s_open": _listen("Hi", [_always("ctl")]),
             "ctl": _code("vars['phase'] = 'b'\nvars['say'] = 'ok'\n", [_always("s_l")]),
             "s_l": _listen("{{say}}", [], enum_schema)}
    tw = Twin(_wf(nodes), Bank(), {"phase": "a"})
    tw.start()
    assert tw.turn("x") == ["ok"]
    assert tw.vars["phase"] == "b" and not tw.errors


def test_counter_with_non_numeric_value_restarts_at_one():
    nodes = {"s_open": _listen("Hi", [_always("ctl")]),
             "ctl": _code("vars['say'] = 'ok'\n", [_always("s_l")]), "s_l": _listen("{{say}}", [])}
    tw = Twin(_wf(nodes), Bank(), {"ctl_success_count": "many"})
    tw.start()
    tw.turn("x")
    assert tw.vars["ctl_success_count"] == "1"
    assert tw.vars["ctl_response.status"] == "success" and tw.vars["ctl_status_code"] == "200"


# ---------------------------------------------------------------- api nodes
def _api_wf(api_node, after="{{say}}"):
    return _wf({"s_open": _listen("Hi", [_always("a_x")]), "a_x": api_node, "s_l": _listen(after, [])})


def test_api_body_defaults_json_mixed_and_literal_values():
    body = {"customer_id": {"type": "string", "default": "{{cid}}"},
            "amount": {"type": "number", "default": "{{amt:json}}"},
            "raw": {"type": "string", "default": "{{bad:json}}"},
            "label": {"type": "string", "default": "pay {{amt}} now"},
            "flag": {"type": "boolean", "default": True},
            "nodefault": {"type": "string"}}
    mapping = [{"path": "data.products.0.past_due", "variable": "due"}, {"path": "data.note", "variable": "note"},
               {"path": "data.products", "variable": "plist"}, {"path": "data.missing.0", "variable": "m"},
               {"path": "data.ok"}]
    bank = Bank([(200, {"ok": True, "note": None, "products": [{"past_due": 420.0}]})])
    tw = Twin(_api_wf(_api("get_account", body, mapping, [_always("s_l")])), bank,
              {"cid": "c1", "amt": "12.50", "bad": "{oops", "say": "next"})
    tw.start()
    assert tw.turn("x") == ["next"]
    assert bank.sent == [("get_account", {"customer_id": "c1", "amount": 12.5, "raw": "{oops", "label": "pay 12.50 now",
                                          "flag": True})]
    assert tw.vars["due"] == "420" and tw.vars["note"] == "None" and tw.vars["plist"] == '[{"past_due": 420.0}]'
    assert "m" not in tw.vars and not tw.errors
    assert tw.vars["get_account_args.flag"] == "true" and tw.vars["a_x_response.data.products.0.past_due"] == "420"


def test_api_mapping_path_must_start_with_data_and_tool_must_be_in_catalog():
    mapping = [{"path": "status_code", "variable": "sc"}]
    tw = Twin(_api_wf(_api("mystery_tool", {}, mapping, [_always("s_l")])), Bank(), {"say": "n"})
    tw.start()
    tw.turn("x")
    assert tw.errors == ["api node a_x: tool 'mystery_tool' is not in the bank catalog",
                         "api node a_x: mapping path 'status_code' does not start with data."]
    assert tw.vars["sc"] == "200"                                          # walked on the envelope anyway


def test_api_node_without_api_call_counts_failure_and_defaults_route():
    node = _api("get_account", {}, [], [_always("s_l")])
    node["pre_actions"][0]["function"]["handler"] = "__function__:code_exec"
    tw = Twin(_api_wf(node), Bank(), {"say": "n"})
    tw.start()
    assert tw.turn("x") == ["n"]
    assert tw.errors == ["api node a_x: no api_call pre_action"] and tw.vars["a_x_failure_count"] == "1"


def test_api_non_2xx_after_retries_has_error_envelope():
    bank = Bank([(503, None), (502, None), (404, {"error": "x"})])
    mapping = [{"path": "data.ok", "variable": "r_ok"}]
    tw = Twin(_api_wf(_api("get_account", {}, mapping, [_always("s_l")], retries=5)), bank, {"say": "n"})
    tw.start()
    tw.turn("x")
    assert len(bank.sent) == 3                                             # 4xx stops the retries
    done = [e for e in tw.events if e.get("event") == "function_call_complete"][-1]["result"]
    assert done == {"status": "error", "data": None, "message": "Request failed with status code 404",
                    "status_code": 404}
    assert "r_ok" not in tw.vars and tw.vars["get_account_status_code"] == "404"
    assert tw.vars["a_x_failure_count"] == "1"
