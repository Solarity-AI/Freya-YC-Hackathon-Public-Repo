"""Latency round: node hops per customer turn (identity chain `vchain`, twin hop paths, lint hop_bound).

A verify node whose result says the answer verified no longer goes back to ctl: all verified -> the account read
ctl armed (then ctl once, which also composes the statement); verified with questions left -> the ID listen node,
which speaks the next question ctl computed before the call. Behaviour must not change: transcripts and ledgers
are compared with the chain on and off."""
import copy
import json
import pathlib

import pytest

from builder.compiler import graph, lint
from harness import scenarios as sc
from harness.twin import Twin
from runtime import brain
from test_brain import CASES, CATALOG, PUB_SCRIPTS, SPEC_A, SPEC_AB, W_A, W_AB, Driver, run_case

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _wiring_off(w):
    w = copy.deepcopy(w)
    w["vchain"] = {}
    return w


def _vars_st(d):
    return json.loads(d.vars["st"])


# ---------------------------------------------------------------------------------------------- wiring / graph
def test_wiring_carries_the_identity_chain_spellings():
    w = graph.wiring(SPEC_A, CATALOG)
    assert w["vchain"] == {"t": ["true", "True"], "f": ["false", "False"]}
    assert w["flags"]["vchain"] == "on"


@pytest.mark.parametrize("flags", [{"vchain": "off"}, {"write_chain": "off"}])
def test_identity_chain_off_by_flag(flags):
    w = graph.wiring(SPEC_A, CATALOG, flags)
    assert w["vchain"] == {}
    wf, _ = graph.compile_workflow(SPEC_A, CATALOG, flags, code="vars['nx'] = 's_safe'\n")
    for n in w["api"]["verify"]:
        assert [t["target_node"] for t in wf["nodes"][n]["transitions"]] == ["ctl"]


def test_identity_chain_needs_a_bool_identity_tool_with_verified_and_all_leaves():
    cat = copy.deepcopy(CATALOG)
    cat["tools"]["verify_identity"]["success"] = {"role": "s", "kind": "enum_in", "values": ["ok"]}
    assert graph.wiring(SPEC_A, cat)["vchain"] == {}
    cat = copy.deepcopy(CATALOG)
    del cat["tools"]["verify_identity"]["roles"]["response"]["all"]
    assert graph.wiring(SPEC_A, cat)["vchain"] == {}
    cat = copy.deepcopy(CATALOG)
    cat["tools"]["verify_identity"]["success"]["values"] = ["True"]
    assert graph.wiring(SPEC_A, cat)["vchain"] == {"t": ["True"], "f": ["False"]}


def test_verify_node_transitions_are_guarded_and_deterministic():
    wf, w = graph.compile_workflow(SPEC_AB, CATALOG, code="vars['nx'] = 's_safe'\n")
    trs = wf["nodes"]["a_verify_2"]["transitions"]
    assert [t["target_node"] for t in trs] == ["a_acct_1", "a_acct_2", "s_id", "ctl"]
    assert trs[0]["condition"] == {"logic": "or", "conditions": [{"logic": "and", "conditions": [
        {"variable": "wn_a_verify_2", "operator": "equals", "operand": "a_acct_1"},
        {"variable": "r_a_verify_2_s", "operator": "equals", "operand": t},
        {"variable": "r_a_verify_2_verified", "operator": "equals", "operand": t},
        {"variable": "r_a_verify_2_all", "operator": "equals", "operand": t},
        {"variable": "r_a_acct_1_s", "operator": "equals", "operand": "pending"}]} for t in ("true", "True")]}
    assert trs[2]["condition"] == {"logic": "or", "conditions": [{"logic": "and", "conditions": [
        {"variable": "wl_a_verify_2", "operator": "equals", "operand": "s_id"},
        {"variable": "r_a_verify_2_s", "operator": "equals", "operand": t},
        {"variable": "r_a_verify_2_verified", "operator": "equals", "operand": t},
        {"variable": "r_a_verify_2_all", "operator": "equals", "operand": f}]} for t, f in (("true", "false"),
                                                                                           ("True", "False"))]}
    ops = {c["operator"] for tr in trs[:-1] for g in tr["condition"]["conditions"] for c in g["conditions"]}
    assert ops == {"equals"}
    assert graph.vchain_transitions("a_acct_1", w) == [] and graph.vchain_transitions("a_promise_1_1", w) == []


# ---------------------------------------------------------------------------------------------- lint
@pytest.mark.parametrize("spec", [SPEC_A, SPEC_AB], ids=["a", "ab"])
@pytest.mark.parametrize("flags", [{}, {"vchain": "off"}, {"bye": "apinode"}, {"bye": "listen"},
                                   {"write_chain": "off"}])
def test_golden_lint_clean_with_and_without_the_chain(spec, flags):
    wf, w = graph.compile_workflow(spec, CATALOG, flags)
    assert lint.errors(lint.lint(wf, CATALOG, spec, w, stable=False)) == []


def test_lint_rejects_a_chain_the_wiring_does_not_declare():
    wf, w = graph.compile_workflow(SPEC_A, CATALOG, code="vars['nx'] = 's_safe'\n")
    errs = lint.errors(lint.lint(wf, CATALOG, SPEC_A, _wiring_off(w), stable=False))
    rules = {(f["rule"], f["where"]) for f in errs}
    assert ("reach_source", "a_acct_1") in rules and ("var_writer", "a_verify_1") in rules


def test_lint_hop_bound_unguarded_cycle():
    wf, w = graph.compile_workflow(SPEC_A, CATALOG, code="vars['nx'] = 's_safe'\n")
    bye = wf["nodes"]["s_bye"]
    bye["transitions"].insert(0, {"target_node": "s_bye", "description": "loop",
                                  "condition": {"logic": "or", "conditions": [
                                      {"variable": "cmode", "operator": "equals", "operand": "x"}]}})
    f = [x for x in lint.lint(wf, CATALOG, SPEC_A, w, stable=False) if x["rule"] == "hop_bound"]
    assert f and f[0]["level"] == "error" and "cycle" in f[0]["msg"]


def test_lint_hop_bound_long_walk(monkeypatch):
    wf, w = graph.compile_workflow(SPEC_AB, CATALOG, code="vars['nx'] = 's_safe'\n")
    assert not [x for x in lint.lint(wf, CATALOG, SPEC_AB, w, stable=False) if x["rule"] == "hop_bound"]
    monkeypatch.setattr(lint, "HOP_BOUND", 5)
    f = [x for x in lint.lint(wf, CATALOG, SPEC_AB, w, stable=False) if x["rule"] == "hop_bound"]
    assert f and f[0]["where"].startswith("a_promise") and "> 5" in f[0]["msg"]


def test_pt_edges_leave_ctl_out():
    wf, _ = graph.compile_workflow(SPEC_A, CATALOG, code="vars['nx'] = 's_safe'\n")
    e = lint._pt_edges(wf["nodes"])
    assert "ctl" not in e and all("ctl" not in v for v in e.values())
    assert e["a_verify_1"] == ["a_acct_1", "a_acct_2"]     # s_id is not passthrough: the walk ends there


# ---------------------------------------------------------------------------------------------- brain (Driver)
def _ctl_per_turn(d):
    out, cur = [], 0
    for k in d.path:
        if k == "ctl":
            cur += 1
        elif k in d.listen:
            out.append(cur)
            cur = 0
    return out


@pytest.mark.parametrize("cid", sorted(PUB_SCRIPTS))
def test_practice_cases_say_and_record_the_same_with_fewer_ctl_entries(cid):
    sp, w = (SPEC_A, W_A) if CASES[cid]["brief"] == "A" else (SPEC_AB, W_AB)
    on = Driver(sp, w, CASES[cid], faults=CASES[cid].get("faults")).play(PUB_SCRIPTS[cid])
    off = Driver(sp, _wiring_off(w), CASES[cid], faults=CASES[cid].get("faults")).play(PUB_SCRIPTS[cid])
    assert on.lines == off.lines
    assert on.ledger() == off.ledger()
    if "get_account" in on.tools():
        assert on.path.count("ctl") == off.path.count("ctl") - 2



@pytest.mark.parametrize("fault", [
    {"tool": "get_account", "fail_first_n": 1}, {"tool": "get_account", "fail_first_n": 2},
    {"tool": "get_account", "fail_first_n": 1, "mode": "ok_false"},
    {"tool": "get_account", "fail_first_n": 1, "mode": "empty"},
    {"tool": "verify_identity", "fail_calls": [1]}, {"tool": "verify_identity", "fail_calls": [2]},
    {"tool": "verify_identity", "fail_calls": [2], "mode": "ok_false"},
    {"tool": "verify_identity", "fail_calls": [1, 2], "mode": "timeout"}],
    ids=lambda f: "%s-%s-%s" % (f["tool"], f.get("fail_first_n", f.get("fail_calls")), f.get("mode", "500")))
@pytest.mark.parametrize("bool_style", ["lower", "title"])
def test_faults_behave_the_same_with_the_chain(fault, bool_style):
    turns = PUB_SCRIPTS["PUB-01"]
    on = Driver(SPEC_A, W_A, CASES["PUB-01"], faults=[fault], bool_style=bool_style).play(turns)
    off = Driver(SPEC_A, _wiring_off(W_A), CASES["PUB-01"], faults=[fault], bool_style=bool_style).play(turns)
    assert on.lines == off.lines and on.ledger() == off.ledger()


def test_first_answer_arms_the_chain_and_the_listen_node_speaks_the_next_question():
    d = Driver(SPEC_A, W_A, CASES["PUB-01"])
    d.opening()
    d.turn("Yes, speaking.")
    out = d.turn("14 March 1988")
    assert out == [d.vars["say"]] and "phone number" in out[0]
    assert d.vars["wn_a_verify_1"] == "a_acct_1" and d.vars["wl_a_verify_1"] == "s_id"
    assert d.vars["r_a_acct_1_s"] == "pending"
    assert d.vars["u_act"] == "unclear" and d.vars["u_topic"] == "none"     # sensors reset before s_id listens
    st = _vars_st(d)
    assert st["vc"] == "a_acct_1" and st["vs"]["u_text"] == "14 March 1988" and st["await"] == "a_verify_1"
    assert _ctl_per_turn(d)[-1] == 1                                        # ctl -> a_verify_1 -> s_id
    out = d.turn("4471")                                                    # ctl -> a_verify_2 -> a_acct_1 -> ctl
    assert d.tools() == ["verify_identity", "verify_identity", "get_account"]
    assert d.vars["wl_a_verify_2"] == "" and _ctl_per_turn(d)[-1] == 2
    assert "vc" not in _vars_st(d) and "vs" not in _vars_st(d)
    assert _vars_st(d)["ph"] == "NEG" and _vars_st(d)["acct_try"] == 1


def test_no_chain_in_the_wiring_means_no_arming():
    d = run_case("PUB-01", PUB_SCRIPTS["PUB-01"][:2])
    assert "wn_a_verify_1" in d.vars
    d = Driver(SPEC_A, _wiring_off(W_A), CASES["PUB-01"]).play(PUB_SCRIPTS["PUB-01"][:2])
    assert "wn_a_verify_1" not in d.vars and "wl_a_verify_1" not in d.vars
    assert "vs" not in _vars_st(d)


def test_arming_without_an_account_row_left():
    d = Driver(SPEC_A, W_A, CASES["PUB-01"]).play(PUB_SCRIPTS["PUB-01"][:1])
    R = {"v": 1, "spec": d.spec, "wiring": W_A}
    st = json.loads(d.vars["st"])
    st["acct_try"] = 9
    c = brain._b_ctx(R, st, {"call": {"now": d.vars.get("now", "")}, "sensors": {"u_text": "14 March 1988"}})
    brain._b_varm(c, "a_verify_1")
    assert c["w"]["wn_a_verify_1"] == "" and "vc" not in st and c["w"]["wl_a_verify_1"] == "s_id"


# ---------------------------------------------------------------------------------------------- brain (units)
def _armed_vars(**over):
    st = {"ph": "ID", "await": "a_verify_1", "vc": "a_acct_1", "vs": {"u_text": "x"}}
    v = {"r_a_verify_1_s": "true", "r_a_verify_1_verified": "true", "r_a_verify_1_all": "true", "u_text": "hi"}
    v.update(over)
    return v, st


def test_vfired_matches_the_graph_condition():
    v, st = _armed_vars()
    assert brain._b_vfired(v, W_A, st) == "a"
    v, st = _armed_vars(r_a_verify_1_all="false")
    assert brain._b_vfired(v, W_A, st) == "l"
    v, st = _armed_vars(r_a_verify_1_all="false", u_text="")
    assert brain._b_vfired(v, W_A, st) == ""                    # the graph came back to ctl: nobody spoke
    v, st = _armed_vars(r_a_verify_1_s="True", r_a_verify_1_verified="True", r_a_verify_1_all="True")
    assert brain._b_vfired(v, W_A, st) == "a"
    v, st = _armed_vars(r_a_verify_1_s="True")                 # mixed spellings: no group matches
    assert brain._b_vfired(v, W_A, st) == ""
    v, st = _armed_vars(r_a_verify_1_verified="false")
    assert brain._b_vfired(v, W_A, st) == ""
    v, st = _armed_vars()
    st.pop("vc")
    assert brain._b_vfired(v, W_A, st) == ""                    # nothing armed
    v, st = _armed_vars(r_a_verify_1_all="false")
    st.pop("vs")
    assert brain._b_vfired(v, W_A, st) == ""
    v, st = _armed_vars()
    st["await"] = "a_acct_1"
    assert brain._b_vfired(v, W_A, st) == ""
    v, st = _armed_vars()
    assert brain._b_vfired(v, _wiring_off(W_A), st) == ""


def _id_ctx(vf, res, vs=None):
    R = {"v": 1, "spec": brain._b_dec({"v": 1, "spec": SPEC_A, "wiring": W_A})["spec"], "wiring": W_A}
    st = {"ph": "ID", "await": "a_verify_1", "turns": 2,
          "id": {"qi": 0, "wrong": 0, "wq": {}, "hints": {}, "dec": {}, "expl": 0, "frag": "", "vi": 1, "turns": 1,
                 "retry": 0, "ver": []}}
    if vs is not None:
        st["vs"], st["vc"] = vs, "a_acct_1"
    inp = {"call": {"now": "2026-10-14T10:00"}, "sensors": {"u_text": ""}, "results": {"a_verify_1": res},
           "vf": vf}
    return brain._b_ctx(R, st, inp)


def test_unfired_chain_restores_the_answer_turn_sensors():
    c = _id_ctx("", {"s": "true", "verified": "false", "all": "false", "left": "2", "hint": "", "err": ""},
                vs={"u_text": "14 March 1988", "u_act": "answer"})
    brain._b_on_verify(c, "a_verify_1")
    assert c["text"] == "14 March 1988" and c["act"] == "answer"
    assert "vs" not in c["st"] and "vc" not in c["st"]
    c = _id_ctx("l", {"s": "true", "verified": "true", "all": "false", "left": "", "hint": "", "err": ""},
                vs={"u_text": "14 March 1988"})
    brain._b_on_verify(c, "a_verify_1")
    assert c["text"] == "" and c["st"]["id"]["qi"] == 1         # the reply to the chained question is kept


def test_fired_chain_ignores_hint_and_error_leaves():
    hinted = {"s": "true", "verified": "true", "all": "true", "left": "", "hint": "format", "err": "locked"}
    c = _id_ctx("a", dict(hinted), vs={})
    c["res"]["a_acct_1"] = {"s": "pending"}
    brain._b_on_verify(c, "a_verify_1")
    assert c["st"]["ph"] == "ACCT" and c["nx"] == "a_acct_2"   # the chained read failed: the 2nd row is next
    c = _id_ctx("", dict(hinted))
    brain._b_on_verify(c, "a_verify_1")
    assert c["nx"] != "a_acct_1" and c["st"]["ph"] != "ACCT"


# ---------------------------------------------------------------------------------------------- twin
def _twin_flags(flags):
    return {k: graph.compile_workflow(s, CATALOG, flags)[0] for k, s in (("a", SPEC_A), ("ab", SPEC_AB))}


@pytest.fixture(scope="module")
def wfs():
    return {"on": _twin_flags({}), "off": _twin_flags({"vchain": "off"})}


SCN = {s["id"]: s for s in sc.load(ROOT / "tests" / "scenarios")}


@pytest.mark.parametrize("sid", ["A-PUB-01", "A-PUB-03", "A-PUB-10", "AB-PUB-12"])
def test_twin_same_call_fewer_hops(sid, wfs):
    s = SCN[sid]
    spec = SPEC_A if s["spec"] == "a" else SPEC_AB
    on = sc.run(s, wfs["on"][s["spec"]], CATALOG, spec)
    off = sc.run(s, wfs["off"][s["spec"]], CATALOG, spec)
    assert on["pass"] and off["pass"]
    assert on["transcript"] == off["transcript"] and on["ledger"] == off["ledger"]
    saved = 0 if sid == "A-PUB-03" else 2                   # PUB-03: the first answer is wrong, never verified
    assert sum(on["hops"]) == sum(off["hops"]) - saved and sum(on["ctl_hops"]) == sum(off["ctl_hops"]) - saved
    for p in on["paths"]:
        assert "a_acct_1" not in p or p[p.index("a_acct_1") - 1].startswith("a_verify")


def test_twin_records_paths_and_ctl_hops(wfs):
    r = sc.run(SCN["A-PUB-01"], wfs["on"]["a"], CATALOG, SPEC_A)
    assert r["paths"][0] == ["s_open"] and len(r["paths"]) == len(r["hops"])
    assert [len(p) for p in r["paths"]] == r["hops"]
    assert r["paths"][2] == ["ctl", "a_verify_1", "s_id"]
    assert r["paths"][3] == ["ctl", "a_verify_2", "a_acct_1", "ctl", "s_neg"]
    assert r["ctl_hops"] == [0, 1, 1, 2, 1, 1]
    rc = sc.run(SCN["A-PUB-01-chat"], wfs["on"]["a"], CATALOG, SPEC_A)
    assert rc["paths"][:2] == [[], []] and rc["ctl_hops"][:2] == [0, 0]


def test_scenario_max_ctl_hops_check(wfs):
    s = copy.deepcopy(SCN["A-PUB-01"])
    s.setdefault("transcript", {})["max_ctl_hops"] = 1
    r = sc.run(s, wfs["on"]["a"], CATALOG, SPEC_A)
    assert not r["pass"] and any("ctl entries 2 > max_ctl_hops 1" in f for f in r["failed"])


def test_twin_hop_limit_path_records_the_stuck_node():
    code = "vars['say'] = 'x'\n"
    wf = {"initial_node": "s", "nodes": {
        "s": {"node_type": "conversation", "on_enter": {"type": "tts", "text": "hi"},
              "transitions": [{"target_node": "c", "condition": {"operator": "always"}}]},
        "c": {"node_type": "code", "passthrough": True, "passthrough_default_transition": "c",
              "pre_actions": [{"type": "function", "function": {"name": "code_exec",
                                                                  "handler": "__function__:code_exec",
                                                                  "parameters": {"type": "object", "properties": {
                                                                      "code": {"type": "string",
                                                                               "default": code}}}}}],
              "transitions": [{"target_node": "c", "condition": {"operator": "always"}}]}}}

    class Bank:
        catalog = {"tools": {}}
    t = Twin(wf, Bank(), {}, max_hops=4)
    t.start()
    t.turn("x")
    assert t.stuck and t.paths[1] == ["c"] * 5 and t.ctl_hops()[1] == 5


# ---------------------------------------------------------------------------------------------- coverage keep
@pytest.mark.parametrize("text", ["No, he passed away last year.", "Mary Ann died last year."])
def test_two_word_customer_name_still_finds_a_death(text):
    """ident._i_dead_third skips multi-word name tokens for its per-name pattern (the whole name is also a token)."""
    from runtime.ident import rp_classify
    r = rp_classify(text, "", ["Mary Ann", "Reyes"])
    assert r["cls"] == "third_party" and r["close"] == "deceased"
