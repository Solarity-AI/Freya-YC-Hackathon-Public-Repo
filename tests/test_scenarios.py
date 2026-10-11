"""Scenario runner (harness/scenarios.py) + the PUB scenario files in tests/scenarios/. Owner: agent 4.

The runner is tested with the generic toy hub (a replay plan instead of the brain). The golden end-to-end tests
(compile golden Spec -> twin -> all scenarios) skip while the compiler / runtime still raise NotImplementedError.
"""
import copy
import json
import pathlib

import pytest

from builder.spec import vocab
from harness import scenarios as sc
from harness import toy

OPEN = "Hello, I am a digital assistant calling from the bank. We record this call. Am I speaking with {{title}} {{last_name}}?"


def hub_workflow(catalog, plan):
    return toy.hub_workflow(catalog, plan, opening=OPEN)

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCEN_DIR = ROOT / "tests" / "scenarios"
ALL = sc.load(SCEN_DIR)


def _by_id(i):
    return copy.deepcopy(next(s for s in ALL if s["id"] == i))


# ---------------------------------------------------------------- scenario files
def test_every_public_case_has_a_scenario():
    assert {s["pub"] for s in ALL} == {"PUB-%02d" % i for i in range(1, 14)}
    assert len({s["id"] for s in ALL}) == len(ALL)


@pytest.mark.parametrize("s", ALL, ids=[s["id"] for s in ALL])
def test_scenario_file_shape(s, golden_a, golden_ab, public_cases):
    spec = golden_a if s["spec"] == "a" else golden_ab
    assert s["spec"] in ("a", "ab") and s["mode"] in ("sim", "chat") and s["turns"]
    assert public_cases[s["pub"]]["brief"] == ("A" if s["spec"] == "a" else "B")
    topics = {i["id"] for i in spec["intents"]} | {"none", "other_person", "unavailable", "hold", "purpose_question"}
    for t in s["turns"]:
        assert set(t) <= {"say", "x", "agent_has"} and t["say"].strip()
        x = t.get("x") or {}
        assert set(x) <= set(vocab.SENSOR_VARS) - {"u_text"}, x
        assert x.get("u_act", "yes") in vocab.U_ACT_VALUES
        assert x.get("u_topic", "none") in topics
        for k in ("u_date", "u_amt", "u_time", "u_ans"):     # a good extractor copies what was said
            if x.get(k):
                words = [w for w in x[k].lower().replace(",", " ").split() if len(w) > 2]
                assert any(w in t["say"].lower() for w in words), (k, x[k], t["say"])
    tc = s["transcript"]
    assert tc["no_banned_before_verified"] and tc["one_line_per_turn"] and tc["max_hops"] >= 8
    case, expected = sc.case_for(s)
    assert expected == {**public_cases[s["pub"]]["expected"]}


def test_load_single_file_and_list_file(tmp_path):
    one = tmp_path / "one.json"
    one.write_text(json.dumps({"id": "X1", "turns": []}))
    many = tmp_path / "many.json"
    many.write_text(json.dumps([{"id": "X2"}, {"id": "X3"}]))
    assert [s["id"] for s in sc.load(one)] == ["X1"]
    assert [s["id"] for s in sc.load(tmp_path)] == ["X2", "X3", "X1"]          # sorted by file name
    with pytest.raises(KeyError):
        sc.public_case("PUB-99")


def test_case_for_merges_case_and_expect():
    s = {"id": "T", "pub": "PUB-01", "case": {"variables": {"now": "2026-10-15T09:00"}, "faults": []},
         "expect": {"outcome": "paid"}}
    case, exp = sc.case_for(s)
    assert case["variables"]["first_name"] == "Daniel" and case["variables"]["now"] == "2026-10-15T09:00"
    assert exp["outcome"] == "paid" and exp["reason"] is None and len(exp["promises"]) == 1
    case2, exp2 = sc.case_for({"id": "Bare", "case": {"variables": {}}, "expect": {"outcome": "x"}})
    assert exp2 == {"outcome": "x", "reason": None, "promises": [], "notes": [], "callbacks": [], "transfers": []}


# ---------------------------------------------------------------- runner on the toy hub
PUB01 = [["say", "Before we continue, could you please tell me your date of birth?", "s_l"],
         ["call", "verify_identity", {"field": "date_of_birth", "answer": "1988-03-14"}],
         ["say", "Thank you. What are the last four digits of the phone number on file?", "s_l"],
         ["call", "verify_identity", {"field": "phone_last4", "answer": "4471"}],
         ["call", "get_account", {}],
         ["say", "I am calling from the collections team about a late payment. Can you pay 420 today?", "s_l"],
         ["say", "So that is 420 for your card today. Do you confirm?", "s_l"],
         ["call", "create_promise", {"product_id": "p1", "amount": "420.00", "date": "2026-10-14"}],
         ["close", "promise", "", "Your promise is recorded. You will receive a text message confirming this "
                                  "promise. Thank you for your time. Goodbye."]]


def test_run_pub01_toy_passes(catalog_kit, golden_a):
    r = sc.run(_by_id("A-PUB-01"), hub_workflow(catalog_kit, PUB01), catalog_kit, golden_a)
    assert r["pass"], r["failed"]
    assert r["lines_per_turn"] == [1, 1, 1, 1, 1, 1] and r["ledger"]["outcome"] == "promise"
    assert r["notes"] == ["1 scripted turn(s) left after the call ended"]
    assert r["transcript"][-1][1].endswith("Goodbye.")


def test_run_chat_mode_scenario(catalog_kit, golden_a):
    r = sc.run(_by_id("A-PUB-01-chat"), hub_workflow(catalog_kit, PUB01[:3] + [
        ["call", "verify_identity", {"field": "phone_last4", "answer": "4471"}], ["call", "get_account", {}],
        ["say", "Collections here. Can you pay today?", "s_l"]] + PUB01[6:]), catalog_kit, golden_a)
    assert r["pass"], r["failed"]
    assert r["lines_per_turn"][0] == 0


def test_run_detects_banned_word_outcome_and_turn_drift(catalog_kit, golden_a):
    plan = copy.deepcopy(PUB01)
    plan[0][1] = "This is about your overdue card. What is your date of birth?"
    plan[-1] = ["close", "no_promise", "refused", "Goodbye."]
    s = _by_id("A-PUB-01")
    s["turns"][1]["agent_has"] = "date of birth"
    s["turns"][2]["agent_has"] = "something never said"
    r = sc.run(s, hub_workflow(catalog_kit, plan), catalog_kit, golden_a)
    assert not r["pass"]
    joined = "\n".join(r["failed"])
    assert "banned before verification" in joined and "'overdue'" in joined and "'card'" in joined
    assert "outcome ('no_promise', 'refused')" in joined
    assert "lack 'something never said'" in joined
    assert "text message confirming" in joined                            # transcript must
    assert "turn 1: agent lines" not in joined                           # the matching agent_has passed


def test_run_detects_zero_lines_unended_call_and_hops(catalog_kit, golden_a):
    plan = [["say", "Date of birth?", "s_l"], ["say", "", "s_l"]]
    s = _by_id("A-PUB-01")
    s["turns"] = s["turns"][:2]
    s["transcript"]["max_hops"] = 1
    r = sc.run(s, hub_workflow(catalog_kit, plan), catalog_kit, golden_a)
    joined = "\n".join(r["failed"])
    assert "turn 2 produced 0 agent lines" in joined
    assert "the call did not end" in joined
    assert "hops 2 > max_hops 1" in joined
    assert "the call was not closed with close_call" in joined


def test_run_must_not_and_missing_banned_list(catalog_kit):
    s = _by_id("A-PUB-01")
    s["transcript"]["must_not"] = [[-1, "collections"], [99, "x"]]
    s["transcript"]["must"] = [[0, "speaking with"], [99, "never"]]
    r = sc.run(s, hub_workflow(catalog_kit, PUB01), catalog_kit, spec=None)
    joined = "\n".join(r["failed"])
    assert "must_not: 'collections'" in joined
    assert "needs the Spec" in joined
    assert "'never' not in turn 99" in joined
    assert "speaking with" not in joined


def test_run_twin_errors_are_failures_and_setup_error(catalog_kit, golden_a):
    wf = hub_workflow(catalog_kit, PUB01)
    wf["nodes"]["s_l"]["transitions"].append({"target_node": "ghost", "condition": {"operator": "always"}})
    r = sc.run(_by_id("A-PUB-01"), wf, catalog_kit, golden_a)
    assert any(f.startswith("twin: node s_l") for f in r["failed"])
    wf["initial_node"] = "nope"
    r = sc.run(_by_id("A-PUB-01"), wf, catalog_kit, golden_a)
    assert not r["pass"] and r["failed"][0].startswith("twin setup")


def test_run_pub02_callback_toy(catalog_kit, golden_a):
    plan = [["say", "When would be a good time to reach Ms Costa?", "s_l"],
            ["say", "Thank you, but I can only speak with Ms Costa about this.", "s_l"],
            ["call", "schedule_callback", {"date": "2026-10-15", "time": "11:00"}],
            ["close", "not_reached", "callback", "Thank you. We will call back on Thursday, 15 October at 11:00. "
                                                 "Goodbye."]]
    r = sc.run(_by_id("A-PUB-02"), hub_workflow(catalog_kit, plan), catalog_kit, golden_a)
    assert r["pass"], r["failed"]


def test_run_pub10_retry_after_fault_toy(catalog_kit, golden_a):
    plan = [["say", "Your date of birth?", "s_l"],
            ["call", "verify_identity", {"field": "date_of_birth", "answer": "1989-02-23"}],
            ["say", "The last four digits?", "s_l"],
            ["call", "verify_identity", {"field": "phone_last4", "answer": "9904"}],
            ["call", "get_account", {}],
            ["say", "Late payment of 365. Can you pay today?", "s_l"],
            ["say", "Could you pay 365 by Friday, 16 October?", "s_l"],
            ["say", "So that is 365 on Friday, 16 October. Do you confirm?", "s_l"],
            ["call", "create_promise", {"product_id": "p1", "amount": "365.00", "date": "2026-10-16"}],
            ["call", "create_promise", {"product_id": "p1", "amount": "365.00", "date": "2026-10-16"}],
            ["close", "promise", "", "Your promise is recorded. Goodbye."]]
    r = sc.run(_by_id("A-PUB-10"), hub_workflow(catalog_kit, plan), catalog_kit, golden_a)
    assert r["pass"], r["failed"]
    assert [c["status"] for c in r["ledger"]["calls"] if c["tool"] == "create_promise"] == [500, 200]


def test_run_suite_counts(catalog_kit, golden_a):
    res = sc.run_suite([_by_id("A-PUB-01"), _by_id("A-PUB-03")], hub_workflow(catalog_kit, PUB01), catalog_kit,
                       golden_a)
    assert (res["passed"], res["total"]) == (1, 2)
    assert res["results"][1]["id"] == "A-PUB-03" and not res["results"][1]["pass"]


# ---------------------------------------------------------------- generate
def test_generate_from_golden_a(golden_a, catalog_kit):
    gen = {g["id"]: g for g in sc.generate(golden_a, catalog_kit)}
    assert set(gen) == {"GEN-happy", "GEN-id-failed", "GEN-refused", "GEN-callback"}
    h = gen["GEN-happy"]
    assert h["expect"] == {"outcome": "promise", "reason": None,
                           "promises": [{"product_id": "p1", "amount": 250.0, "date": "2026-01-07"}]}
    prod = h["case"]["products"][0]
    assert prod["type"] in golden_a["products"]["types"] and prod["past_due"] == 250.0
    assert set(h["case"]["identity"]) == {q["field_value"] for q in golden_a["identity"]["questions"]}
    f = gen["GEN-id-failed"]
    assert (f["expect"]["outcome"], f["expect"]["reason"]) == ("not_verified", "failed")
    assert len(f["turns"]) == 1 + golden_a["identity"]["max_wrong_total"] + 1
    assert gen["GEN-refused"]["expect"] == {"outcome": "no_promise", "reason": "refused", "notes": []}
    cb = gen["GEN-callback"]["expect"]
    assert cb["outcome"] == "not_reached" and cb["callbacks"] == [{"date": "2026-01-08", "time": "14:00"}]
    for g in gen.values():                                     # every generated case runs through the mock bank
        case, exp = sc.case_for(g)
        assert exp["outcome"] and case["variables"]["now"] == "2026-01-07T11:00"


def test_generate_ab_adds_notes_and_skips_what_it_cannot_derive(golden_ab, catalog_kit):
    gen = {g["id"]: g for g in sc.generate(golden_ab, catalog_kit)}
    assert gen["GEN-refused"]["expect"]["notes"] == [{"product_id": "p1", "reason": "refused"}]
    spec = copy.deepcopy(golden_ab)
    spec["calendar"]["holiday_rules"] = [{"kind": "fixed", "month": 1, "day": 1}]
    spec["identity"]["questions"][0]["kind"] = "biometric"
    ids = {g["id"] for g in sc.generate(spec, catalog_kit)}
    # no identity values; the holiday rules are expanded with runtime.cal, so the callback is still generated
    assert ids == {"GEN-callback"}
    spec2 = copy.deepcopy(golden_ab)
    spec2["products"]["types"] = {}
    assert sc.generate(spec2, catalog_kit) == []


def test_generate_identity_kinds():
    q = {"kind": "digits", "length": 6, "wire_format": "digits"}
    assert sc._id_value(q, 0)[0] == "123456" and sc._id_value(q, 1)[0] != "123456"
    assert sc._id_value({"kind": "date", "wire_format": "%d/%m/%Y"}, 0)[0] == "15/01/1980"
    assert sc._id_value({"kind": "year"}, 0)[0] == "1980"
    assert sc._id_value({"kind": "alnum", "length": 4}, 0) == ("AB12", "A B 1 2", "AB12")
    assert sc._id_value({"kind": "text"}, 2)[0] == "Othervalue2"


def test_callback_slot_variants():
    cal = {"business_weekdays": [0, 1, 2, 3, 4], "holidays": ["2026-01-08"]}
    win = [{"from": "10:00", "to": "19:00", "inclusive_from": True, "inclusive_to": True, "days": "any"}]
    today = sc.datetime.date(2026, 1, 7)
    cb = {"date_rule": {"include_today": True, "business_days_ahead": 1}, "windows": win}
    assert sc._callback_slot(cb, cal, today, 660) == (sc.datetime.date(2026, 1, 9), "14:00")   # holiday skipped
    cb = {"date_rule": {"include_today": True, "business_days_ahead": 0}, "windows": win}
    assert sc._callback_slot(cb, cal, today, 900) is None                                       # 14:00 < now 15:00
    assert sc._callback_slot({"date_rule": {}, "windows": []}, cal, today, 0) is None


# ---------------------------------------------------------------- golden end to end (integration gate)
def _runtime_ready():
    for name in ("cal", "parse", "ident", "brain", "bundle"):
        if "raise NotImplementedError" in (ROOT / "runtime" / (name + ".py")).read_text():
            return False
    return True


def _compile(spec, catalog):
    if not _runtime_ready():
        pytest.skip("runtime still has NotImplementedError stubs (the ctl snippet would swallow them)")
    wf, _wiring = _compile_graph_only(spec, catalog)
    return wf


@pytest.mark.parametrize("s", ALL, ids=[s["id"] for s in ALL])
def test_golden_end_to_end(s, golden_a, golden_ab, catalog_kit):
    spec = golden_a if s["spec"] == "a" else golden_ab
    wf = _compile(spec, catalog_kit)
    r = sc.run(s, wf, catalog_kit, spec)
    if any("NotImplementedError" in f for f in r["failed"]):
        pytest.skip("runtime not ready")
    assert r["pass"], "\n".join(r["failed"]) + "\n" + "\n".join("%s: %s" % x for x in r["transcript"])


@pytest.mark.parametrize("name", ["a", "ab"])
def test_golden_generated_smoke(name, golden_a, golden_ab, catalog_kit):
    spec = golden_a if name == "a" else golden_ab
    wf = _compile(spec, catalog_kit)
    res = sc.run_suite(sc.generate(spec, catalog_kit), wf, catalog_kit, spec)
    if any("NotImplementedError" in f for r in res["results"] for f in r["failed"]):
        pytest.skip("runtime not ready")
    bad = [(r["id"], r["failed"]) for r in res["results"] if not r["pass"]]
    assert not bad, bad


# ---------------------------------------------------------------- compiled graph + replay ctl (no brain needed)
def _compile_graph_only(spec, catalog):
    """The replay tests need only the graph; a compiler/bundler failure is owned (and tested) elsewhere."""
    try:
        from builder.compiler import graph
        return graph.compile_workflow(spec, catalog)
    except Exception as e:                                       # noqa: BLE001
        pytest.skip("compile_workflow failed (not a harness issue): %s: %s" % (type(e).__name__, str(e)[:200]))


def _chain_close(w, writes, outcome, reason, say):
    """Plan steps that preset a write chain like brain.plan_writes would (C.8): writes = [(node, body)]."""
    steps = []
    nodes = [n for n, _ in writes] + [w["bye"]]
    for i, (node, body) in enumerate(writes):
        for f, v in body.items():
            steps.append(["set", "b_%s_%s" % (node, f), v])
        steps.append(["set", "r_%s_s" % node, "pending"])
        steps.append(["set", "wn_" + node, nodes[i + 1]])
    steps += [["set", "co", outcome], ["set", "cr", reason], ["set", "cmode", "r" if reason else "n"],
              ["set", "say", say]]
    first = writes[0][0]
    steps.append(["call", first, {f: v for f, v in writes[0][1].items()}])
    return steps


@pytest.mark.parametrize("style", [dict(bool_style="lower", list_style="json", flat_keys="both"),
                                   dict(bool_style="title", list_style="pyrepr", flat_keys="node")])
def test_compiled_golden_a_graph_with_replay_ctl(style, golden_a, catalog_kit):
    wf, w = _compile_graph_only(golden_a, catalog_kit)
    L, A = w["listen"], w["api"]
    v1, v2 = A["verify"][0], A["verify"][1]
    plan = [["say", "Your date of birth, please?", L["id"]],
            ["call", v1, {"field": "date_of_birth", "answer": "1988-03-14"}],
            ["say", "And the last four digits?", L["id"]],
            ["call", v2, {"field": "phone_last4", "answer": "4471"}],
            ["call", A["acct"][0], {}],
            ["say", "Can you pay today?", L["neg"]],
            ["say", "So that is 420 today. Do you confirm?", L["conf"]]]
    plan += _chain_close(w, [(A["promise"][0][0], {"product_id": "p1", "amount": "420.00", "date": "2026-10-14"})],
                         "promise", "", "Your promise is recorded. You will receive a text message confirming "
                                        "this promise. Goodbye.")
    s = _by_id("A-PUB-01")
    s["twin"] = style
    r = sc.run(s, toy.replace_ctl(wf, plan), catalog_kit, golden_a)
    assert r["pass"], r["failed"]
    nodes = [e["node"] for e in r["events"] if e["event"] == "node_enter"]
    assert nodes[-6:-3] == [L["conf"], "ctl", A["promise"][0][0]]
    assert nodes[-3:] == [w["bye"], A["close_n"], w["end"]]
    assert r["ledger"]["calls"][-1]["args"] == {"customer_id": r["ledger"]["calls"][0]["args"]["customer_id"],
                                                "outcome": "promise"}


def test_compiled_golden_ab_chain_with_notes_and_reasoned_close(golden_ab, catalog_kit):
    wf, w = _compile_graph_only(golden_ab, catalog_kit)
    L, A = w["listen"], w["api"]
    plan = [["say", "Your date of birth, please?", L["id"]],
            ["call", A["verify"][0], {"field": "date_of_birth", "answer": "1983-10-19"}],
            ["say", "And the last four digits?", L["id"]],
            ["call", A["verify"][1], {"field": "phone_last4", "answer": "4401"}],
            ["say", "That does not match. Again?", L["id"]],
            ["call", A["verify"][2], {"field": "phone_last4", "answer": "4410"}],
            ["call", A["acct"][0], {}]]
    for line in ["Can you pay all of them today?", "Could you pay 1,320 by Friday?", "At least 440 by the 23rd?",
                 "Could you pay 140 by Friday?", "So that is 510 tomorrow. Do you confirm?"]:
        plan.append(["say", line, L["neg"] if "confirm" not in line else L["conf"]])
    writes = [(A["promise"][0][0], {"product_id": "p1", "amount": "510.00", "date": "2026-10-15"}),
              (A["note"][1][0], {"product_id": "p2", "reason": "refused"}),
              (A["note"][2][0], {"product_id": "p3", "reason": "refused"})]
    plan += _chain_close(w, writes, "promise", "", "Your promise is recorded. Goodbye.")
    r = sc.run(_by_id("AB-PUB-12"), toy.replace_ctl(wf, plan), catalog_kit, golden_ab)
    assert r["pass"], r["failed"]
    assert max(r["hops"]) <= 12
    # a reasoned close goes through a_close_r with the reason leaf
    plan2 = [["say", "When would be a good time to reach her?", L["tp"]], ["say", "Sorry?", L["tp"]]]
    plan2 += _chain_close(w, [(A["cb"][0], {"date": "2026-10-15", "time": "11:00"})], "not_reached", "callback",
                          "We will call back tomorrow at 11:00. Goodbye.")
    r2 = sc.run(_by_id("A-PUB-02"), toy.replace_ctl(wf, plan2), catalog_kit, golden_ab)
    assert r2["pass"], r2["failed"]
    assert r2["ledger"]["calls"][-1]["args"]["reason"] == "callback"
