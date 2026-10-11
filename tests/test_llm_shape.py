"""LLM-shaped code with a fake transport (agent 5): builder.llm, pipeline.extract, pipeline.critic.
No network: llm.set_backend() swaps the Claude Agent SDK transport for a function."""
import asyncio
import copy
import json
import pathlib
import time

import jsonschema
import pytest

from builder import llm, trace
from builder.budget import Budget
from builder.pipeline import critic, extract, segment, validate as V

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRIEF_A = ROOT / "kit" / "briefs" / "brief-a.md"
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["n"],
          "properties": {"n": {"type": "integer", "minimum": 1}, "s": {"type": "string"}}}


@pytest.fixture(autouse=True)
def _reset(tmp_path):
    prev = llm.set_backend(None)
    trace.init(tmp_path / "trace", echo=False)
    yield
    trace.close()
    llm.set_backend(prev)


def events(tmp_path, kind=None):
    trace.close()
    recs = [json.loads(x) for x in (tmp_path / "trace" / "trace.jsonl").read_text().splitlines()]
    trace.init(tmp_path / "trace", echo=False)
    return [r for r in recs if kind is None or r["kind"] == kind]


class Clock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


# ================================================================================================ llm

def test_call_json_structured_data(tmp_path):
    seen = []

    def fake(req):
        seen.append(req)
        return {"data": {"n": 3}, "text": "", "usage": {"input_tokens": 5, "output_tokens": 2, "x": 1},
                "cost": 0.01, "model": "m-x"}
    llm.set_backend(fake)
    assert llm.call_json("p1", "sys", "prompt", SCHEMA, timeout_s=30) == {"n": 3}
    assert seen[0]["model"] == llm.DEFAULT_MODEL == "claude-opus-5-5" and seen[0]["effort"] == "high"
    assert seen[0]["schema"] is SCHEMA and seen[0]["attempt"] == 1
    ev = events(tmp_path, "MODEL")
    assert len(ev) == 1 and ev[0]["msg"] == "p1" and ev[0]["ok"] is True and ev[0]["model"] == "m-x"
    assert ev[0]["usage"] == {"input_tokens": 5, "output_tokens": 2} and "prompt" not in json.dumps(ev[0])


def test_plain_dict_and_fenced_text_answers():
    llm.set_backend(lambda req: {"n": 2})
    assert llm.call_json("p", "s", "x", SCHEMA, timeout_s=5) == {"n": 2}
    llm.set_backend(lambda req: "Here you go:\n```json\n{\"n\": 4}\n```\nthanks")
    assert llm.call_json("p", "s", "x", SCHEMA, timeout_s=5) == {"n": 4}


def test_repair_loop_then_success(tmp_path):
    prompts = []

    def fake(req):
        prompts.append(req["prompt"])
        return {"n": 0} if req["attempt"] == 1 else {"n": 1}
    llm.set_backend(fake)
    assert llm.call_json("p", "s", "ORIGINAL", SCHEMA, timeout_s=5) == {"n": 1}
    assert prompts[0] == "ORIGINAL"
    assert prompts[1].startswith("ORIGINAL") and "REJECTED" in prompts[1] and "/n:" in prompts[1]
    assert [e["ok"] for e in events(tmp_path, "MODEL")] == [False, True]


def test_gives_up_after_two_repairs():
    calls = []
    llm.set_backend(lambda req: calls.append(1) or {"bad": True})
    with pytest.raises(llm.LLMError) as ei:
        llm.call_json("purpose-x", "s", "p", SCHEMA, timeout_s=5)
    assert len(calls) == 3 and "purpose-x" in str(ei.value)


def test_no_json_at_all_is_repaired():
    llm.set_backend(lambda req: "I cannot answer" if req["attempt"] == 1 else '{"n": 9}')
    assert llm.call_json("p", "s", "p", SCHEMA, timeout_s=5) == {"n": 9}


def test_timeout_and_exception_are_retried():
    async def slow(req):
        if req["attempt"] == 1:
            await asyncio.sleep(1)
        if req["attempt"] == 2:
            raise RuntimeError("boom")
        return {"n": 5}
    llm.set_backend(slow)
    t = time.monotonic()
    assert llm.call_json("p", "s", "p", SCHEMA, timeout_s=0.1) == {"n": 5}
    assert time.monotonic() - t < 1


def test_all_timeouts_raise():
    async def slow(req):
        await asyncio.sleep(1)
    llm.set_backend(slow)
    with pytest.raises(llm.LLMError, match="timeout"):
        llm.call_json("p", "s", "p", SCHEMA, timeout_s=0.05)


def test_budget_exhausted_no_call(tmp_path):
    calls = []
    llm.set_backend(lambda req: calls.append(req) or {"n": 1})
    b = Budget(hard_s=100, soft_s=50, reserve_s=10, clock=Clock(95))
    b.start, b.hard_at = 0, 100
    with pytest.raises(llm.LLMError):
        llm.call_json("p", "s", "p", SCHEMA, timeout_s=60, budget=b)
    assert calls == [] and events(tmp_path, "BUDGET")


def test_budget_caps_timeout_and_blocks_short_retries():
    c = Clock(0)
    b = Budget(hard_s=100, soft_s=80, reserve_s=10, clock=c)
    seen = []

    def fake(req):
        seen.append(req["timeout_s"])
        c.t = 75                                       # time passes: only 15 s left before the reserve
        return {"bad": 1}
    llm.set_backend(fake)
    with pytest.raises(llm.LLMError):
        llm.call_json("p", "s", "p", SCHEMA, timeout_s=300, budget=b)
    assert seen == [90.0]                              # capped by remaining - reserve; retry refused (< 20 s)


def test_validate_hook_errors_are_repaired():
    llm.set_backend(lambda req: {"n": 1} if req["attempt"] == 1 else {"n": 2})
    out = llm.call_json("p", "s", "p", SCHEMA, timeout_s=5, validate=lambda d: [] if d["n"] == 2 else ["/n: odd"])
    assert out == {"n": 2}


def test_run_parallel_order_errors_and_concurrency():
    state = {"cur": 0, "max": 0}

    async def fake(req):
        state["cur"] += 1
        state["max"] = max(state["max"], state["cur"])
        await asyncio.sleep(0.02)
        state["cur"] -= 1
        if req["purpose"] == "c2":
            return {"bad": 1}
        return {"n": int(req["purpose"][1:]) + 1}
    llm.set_backend(fake)
    calls = [{"purpose": "c%d" % i, "system": "s", "prompt": "p", "schema": SCHEMA, "timeout_s": 5} for i in range(7)]
    out = llm.run_parallel(calls, max_concurrency=3)
    assert [o if isinstance(o, Exception) else o["n"] for o in out][:2] == [1, 2]
    assert isinstance(out[2], llm.LLMError) and [o["n"] for o in out[3:]] == [4, 5, 6, 7]
    assert state["max"] == 3
    assert llm.run_parallel([]) == []


def test_parse_json_text_cases():
    assert llm.parse_json_text('{"a": 1}') == {"a": 1}
    assert llm.parse_json_text('noise {"a": {"b": 2}} tail') == {"a": {"b": 2}}
    assert llm.parse_json_text("```\n{\"a\": 3}\n```") == {"a": 3}
    assert llm.parse_json_text("[1, 2]") is None and llm.parse_json_text(None) is None
    assert llm.parse_json_text("{broken") is None and llm.parse_json_text({"x": 1}) == {"x": 1}


def test_schema_errors_format():
    errs = llm.schema_errors({"n": "x", "z": 1}, SCHEMA)
    assert any(e.startswith("/n:") for e in errs) and any(e.startswith("/:") for e in errs)
    assert llm.schema_errors({"n": 1}, SCHEMA) == []
    assert llm.schema_errors({}, {"type": "bogus"})[0].startswith("<schema>")


def test_sdk_backend_options_and_result(monkeypatch):
    import claude_agent_sdk as sdk
    from claude_agent_sdk import ResultMessage, AssistantMessage, ToolUseBlock
    seen = {}

    def fake_query(prompt, options):
        seen["prompt"], seen["opts"] = prompt, options

        async def gen():
            yield AssistantMessage(content=[ToolUseBlock(id="t1", name="StructuredOutput", input={"n": 8})],
                                   model="claude-opus-5-5")
            yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=2,
                                session_id="s", usage={"input_tokens": 3}, total_cost_usd=0.5,
                                structured_output=None)
        return gen()
    monkeypatch.setattr(sdk, "query", fake_query)
    assert llm.call_json("p", "SYS", "PROMPT", SCHEMA, timeout_s=5, effort="medium") == {"n": 8}
    o = seen["opts"]
    assert seen["prompt"] == "PROMPT" and o.system_prompt == "SYS" and o.tools == []
    assert o.output_format == {"type": "json_schema", "schema": SCHEMA} and o.model == "claude-opus-5-5"
    assert o.effort == "medium" and o.setting_sources == [] and o.max_turns == llm.MAX_TURNS
    assert getattr(o, "thinking", None) in (None,) or o.thinking.get("type") != "disabled"   # never disabled


def test_sdk_backend_error_result(monkeypatch):
    import claude_agent_sdk as sdk
    from claude_agent_sdk import ResultMessage

    def fake_query(prompt, options):
        async def gen():
            yield ResultMessage(subtype="error_max_turns", duration_ms=1, duration_api_ms=1, is_error=True,
                                num_turns=4, session_id="s")
        return gen()
    monkeypatch.setattr(sdk, "query", fake_query)
    with pytest.raises(llm.LLMError, match="sdk result error"):
        llm.call_json("p", "s", "p", SCHEMA, timeout_s=5)


def test_sdk_backend_structured_output_field(monkeypatch):
    import claude_agent_sdk as sdk
    from claude_agent_sdk import ResultMessage

    def fake_query(prompt, options):
        async def gen():
            yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=2,
                                session_id="s", structured_output={"n": 11})
        return gen()
    monkeypatch.setattr(sdk, "query", fake_query)
    assert llm.call_json("p", "s", "p", SCHEMA, timeout_s=5) == {"n": 11}


# ================================================================================================ extract

def full_schema():
    return json.loads((ROOT / "builder" / "spec" / "schema.json").read_text())


def test_facets_partition_the_spec():
    keys = [k for ks in extract.FACETS.values() for k in ks]
    assert len(keys) == len(set(keys))
    assert set(keys) == set(full_schema()["required"]) - {"spec_version", "meta"}


@pytest.mark.parametrize("facet", list(extract.FACETS))
def test_facet_and_output_schemas_are_valid(facet):
    fs = extract.facet_schema(facet)
    jsonschema.Draft202012Validator.check_schema(fs)
    jsonschema.Draft202012Validator.check_schema(extract.output_schema(facet))
    assert set(fs["properties"]) == set(extract.FACETS[facet] + extract.FACET_OPTIONAL_KEYS.get(facet, []))


def test_facet_schema_details():
    f3 = extract.facet_schema("F3")["properties"]["products"]
    assert "fields" not in f3["properties"] and "fields" not in f3["required"]
    assert "interpretation" in extract.facet_schema("F5")["properties"]
    assert "interpretation" not in extract.facet_schema("F5")["required"]
    f6 = extract.facet_schema("F6")
    assert "lines" not in f6["required"] and "readback" in f6["properties"]["confirmation"]["required"]
    rp = extract.facet_schema("F1")["properties"]["right_party"]
    assert "answers" not in rp["required"] and "ask" in rp["required"]


def golden_values(golden, facet):
    vals = {k: copy.deepcopy(golden[k]) for k in extract.FACETS[facet] if k in golden}
    if facet == "F5":
        vals["interpretation"] = copy.deepcopy(golden["interpretation"])
    if "products" in vals:
        vals["products"].pop("fields", None)
    return vals


@pytest.mark.parametrize("facet", list(extract.FACETS))
def test_golden_a_is_expressible_per_facet(golden_a, facet):
    out = {"values": golden_values(golden_a, facet), "sources": [], "decisions": [], "residual": []}
    assert llm.schema_errors(out, extract.output_schema(facet)) == []


def test_prompts_are_complete_and_generic(catalog_kit):
    bdoc = segment.segment([str(BRIEF_A)])
    for f in extract.FACETS:
        p = extract.build_prompt(f, bdoc, catalog_kit, feedback=["/bands/0: wrong", {"pointer": "/x", "problem": "y",
                                                                                      "quote": "q"}])
        assert "@@" not in p and "brief-a.md:1| # Brief A" in p and "## tool verify_identity" in p
        assert "Facet %s" % f in p and "Corrections required" in p and '- /x: y (brief: "q")' in p
        assert p.index("brief-a.md:1|") < p.index("# Task")          # long document first
    for name in ("system.md", "facet_common.md", "critic.md") + tuple(f + ".md" for f in extract.FACETS):
        txt = extract.load_prompt(name)
        assert "{{" not in txt and "}}" not in txt
    assert extract.format_feedback(None) == ""


def test_catalog_summary_mentions_enums_and_items(catalog_kit):
    s = extract.catalog_summary(catalog_kit)
    for tok in ("enum", "item ", "roles:", "outcomes the API documents as sent without a reason"):
        assert tok in s


def fake_extractor(golden, quote="Every customer, debt and payment here is synthetic.", fail=(), bad_quote=(),
                   foreign=()):
    def fn(req):
        if not req["purpose"].startswith("extract "):
            raise AssertionError("unexpected purpose " + req["purpose"])
        facet = req["purpose"].split()[1]
        if facet in fail:
            raise RuntimeError("facet down")
        vals = golden_values(golden, facet)
        if facet in foreign:
            vals["zzz"] = 1
        src = [{"pointer": "/" + k, "quote": quote} for k in vals]
        if facet in bad_quote:
            src.append({"pointer": "/" + extract.FACETS[facet][0], "quote": "this sentence is not in the brief"})
            src.append({"pointer": "/nope/0", "quote": quote})
        return {"values": vals, "sources": src, "decisions": ["%s decided" % facet],
                "residual": [{"text": "a %s rule" % facet, "class": "flow"}]}
    return fn


def test_extract_with_fake_llm_reproduces_golden(golden_a, catalog_kit, tmp_path):
    llm.set_backend(fake_extractor(golden_a))
    bdoc = segment.segment([str(BRIEF_A)])
    draft = extract.extract(bdoc, catalog_kit, Budget())
    assert extract.failed_facets(draft) == []
    r = V.validate(extract.clean_meta(draft), catalog_kit, brief_text=bdoc["text"])
    assert r["errors"] == []
    body = {k: v for k, v in r["spec"].items() if k != "meta"}
    assert body == {k: v for k, v in golden_a.items() if k != "meta"}
    m = r["spec"]["meta"]
    assert m["inputs"][0]["path"].endswith("brief-a.md") and len(m["inputs"][0]["sha256"]) == 64
    assert "/bands" in m["sources"] and m["openapi_sha256"] == catalog_kit["openapi_sha256"]
    assert "F3: F3 decided" in m["decisions"] and len(m["residual_rules"]) == len(extract.FACETS)
    assert {e["msg"] for e in events(tmp_path, "EXTRACT")} >= {"facet calls start", "facet F1 ok"}


def test_extract_drops_bad_quotes_and_foreign_keys(golden_a, catalog_kit):
    llm.set_backend(fake_extractor(golden_a, bad_quote=("F2",), foreign=("F4",)))
    draft = extract.extract(segment.segment([str(BRIEF_A)]), catalog_kit, None)
    w = draft["meta"]["warnings"]
    assert any("unverified quote" in x for x in w) and any("missing pointer /nope/0" in x for x in w)
    assert extract.failed_facets(draft) == ["F4"] and "zzz" not in draft      # schema rejects foreign keys
    assert any("facet F4 failed" in x for x in w)


def test_failed_facet_then_targeted_reextraction(golden_a, catalog_kit):
    llm.set_backend(fake_extractor(golden_a, fail=("F2",)))
    bdoc = segment.segment([str(BRIEF_A)])
    draft = extract.extract(bdoc, catalog_kit, None)
    assert extract.failed_facets(draft) == ["F2"] and "identity" not in draft
    r = V.validate(extract.clean_meta(copy.deepcopy(draft)), catalog_kit)
    assert "F2" in V.facets_with_errors(r["errors"])
    prompts = []

    def fn(req):
        prompts.append(req["prompt"])
        return fake_extractor(golden_a)(req)
    llm.set_backend(fn)
    draft2 = extract.extract(bdoc, catalog_kit, None, only=["F2"], feedback=r["errors"], base=draft)
    assert len(prompts) == 1 and "Corrections required" in prompts[0]
    assert draft2["identity"] == golden_a["identity"] and draft2["bands"] == golden_a["bands"]
    r2 = V.validate(extract.clean_meta(draft2), catalog_kit)
    assert r2["errors"] == []


def test_extract_skipped_without_budget(catalog_kit):
    # review fix round 1: no time for the FIRST extraction is a budget exit (6), a re-extraction is just skipped
    from builder.budget import BudgetExceeded
    llm.set_backend(lambda req: pytest.fail("no call expected"))
    b = Budget(hard_s=10, soft_s=5, reserve_s=20)
    bdoc = segment.segment([str(BRIEF_A)])
    with pytest.raises(BudgetExceeded):
        extract.extract(bdoc, catalog_kit, b)
    draft = extract.extract(segment.segment([str(BRIEF_A)]), catalog_kit, b, only=["F1"], base={"meta": {}})
    assert "extraction skipped: budget" in draft["meta"]["warnings"]


def test_coverage_and_number_gaps():
    values = {"bands": [{"key": "a", "days_late_min": 1, "days_late_max": 7, "attempts": 1,
                         "deadline": {"kind": "nth_business_day_after_today", "n": 12}},
                        {"key": "b", "days_late_min": 8, "days_late_max": 45, "attempts": 2,
                         "deadline": {"kind": "nth_business_day_after_today", "n": 7}}],
              "situations": {"S_A": {}, "S_B": {}}, "opening": {"line": "x"}}
    src = {"/bands/0": "| 1 to 7 | a | the twelfth business day | once |", "/situations/S_A/outcome": "x"}
    assert extract.coverage_gaps(values, src) == ["/bands/1", "/situations/S_B", "/opening"]
    src["/bands/1"] = "| 8 to 45 | b | the 7th business day after today | 3 |"
    assert extract.number_gaps(values, src) == ["/bands/1: 2 not found in its quote"]


def test_verify_sources_merges_duplicate_pointers():
    hay = segment.norm_quote_text("alpha beta. gamma delta.")
    ok, warns = extract.verify_sources([{"pointer": "a", "quote": "alpha beta"}, {"pointer": "/a", "quote": "gamma"}],
                                       {"a": 1}, hay, "F1")
    assert ok == {"/a": "alpha beta ... gamma"} and warns == []


# ================================================================================================ critic

def test_spec_to_english_golden(golden_a):
    t1, t2 = critic.spec_to_english(golden_a), critic.spec_to_english(copy.deepcopy(golden_a))
    assert t1 == t2
    for frag in ("BAND early: 1-7 days late; deadline the business day number 12 after today; 1 persuasion",
                 "ATTEMPT 2 (r2, bands ['late']): propose the floor on the deadline",
                 "SITUATION S_UNCLEAR = close not_reached / unclear", "IDENTITY Q1 (dob)",
                 "the last business day of this week (next week's if today is that day)",
                 "INTENT hardship (precedence 90", "accept_situation S_HARDSHIP_TRANSFER = close transferred / support, "
                 "queue support"):
        assert frag in t1, frag


def test_spec_to_english_total_on_partial_specs():
    assert "BANK" in critic.spec_to_english({})
    s = critic.spec_to_english({"bands": [{"key": "x", "deadline": {"kind": "min", "args": [{"kind": "today"},
                                                                                             {"kind": "fixed",
                                                                                              "date": "2030-01-01"}]}}],
                                "intents": [{"id": "i", "action": {"kind": "close_now", "situation": "S_X"}}],
                                "amounts": {"first": {"kind": "percent_of_full", "pct": 50}}})
    assert "the earliest of (today; 2030-01-01)" in s and "S_X (UNDEFINED)" in s and "50% of the past-due" in s


def test_apply_patches_ops():
    doc = {"a": {"b": 1}, "l": [1, 2, 3], "meta": {}}
    out = critic.apply_patches(doc, [{"op": "replace", "path": "/a/b", "value": 2},
                                     {"op": "add", "path": "/a/c", "value": [1]},
                                     {"op": "remove", "path": "/l/0"},
                                     {"op": "add", "path": "/l/-", "value": 9},
                                     {"op": "add", "path": "/l/0", "value": 0}])
    assert out == {"a": {"b": 2, "c": [1]}, "l": [0, 2, 3, 9], "meta": {}} and doc["a"]["b"] == 1
    assert critic.apply_patches(doc, [{"op": "add", "path": "/x~1y", "value": 1}])["x/y"] == 1


@pytest.mark.parametrize("op", [
    {"op": "replace", "path": "/zz", "value": 1}, {"op": "remove", "path": "/a/zz"}, {"op": "add", "path": "/q/r",
                                                                                     "value": 1},
    {"op": "move", "path": "/a"}, {"op": "replace", "path": "/l/9", "value": 1}, {"op": "add", "path": "",
                                                                                 "value": 1},
    {"op": "replace", "path": "/meta/x", "value": 1}, {"op": "add", "path": "/a/b/c", "value": 1},
    {"op": "replace", "path": "/a"}, {"op": "add", "path": "/l/x", "value": 1}, {"op": "add", "path": "a",
                                                                                 "value": 1}])
def test_apply_patches_errors(op):
    with pytest.raises(critic.PatchError):
        critic.apply_patches({"a": {"b": 1}, "l": [1], "meta": {}}, [op])


def test_apply_and_check_keeps_only_harmless_patches(golden_a, catalog_kit):
    def check(spec):
        return len(V.validate(spec, catalog_kit)["errors"])
    issues = [{"problem": "ok", "op": {"op": "replace", "path": "/identity/max_wrong_total", "value": 4}},
              {"problem": "bad", "op": {"op": "replace", "path": "/situations/S_PAID/outcome", "value": "nope"}},
              {"problem": "none", "op": {}},
              {"problem": "broken", "op": {"op": "replace", "path": "/nothing/here", "value": 1}}]
    new, applied, rejected = critic.apply_and_check(golden_a, issues, check)
    assert [i["problem"] for i in applied] == ["ok"] and new["identity"]["max_wrong_total"] == 4
    assert {i["problem"]: i["why"] for i in rejected} == {
        "bad": "patch adds validation errors", "none": "no usable op", "broken": "path not found: /nothing/here"}
    assert golden_a["identity"]["max_wrong_total"] == 3


def test_critique_drops_unquoted_issues(golden_a, catalog_kit, tmp_path):
    def fn(req):
        assert req["purpose"].startswith("critic") and "The Spec in plain English" in req["prompt"]
        assert '"meta"' not in req["prompt"]
        return {"issues": [{"quote": "Three wrong answers in total end the check", "problem": "p1", "pointer": "/x",
                            "op": {}},
                           {"quote": "invented text", "problem": "p2", "pointer": "/y", "op": {}}],
                "residual": [{"text": "r", "class": "speech"}]}
    llm.set_backend(fn)
    out = critic.critique(segment.segment([str(BRIEF_A)]), golden_a, catalog_kit, Budget())
    assert [i["problem"] for i in out["issues"]] == ["p1"] and [i["problem"] for i in out["dropped"]] == ["p2"]
    assert out["residual"] == [{"text": "r", "class": "speech"}]
    assert any("dropped_unquoted=1" in e["msg"] for e in events(tmp_path, "CRITIC"))


def test_critique_skipped_without_time(golden_a, catalog_kit):
    llm.set_backend(lambda req: pytest.fail("no call expected"))
    out = critic.critique(segment.segment([str(BRIEF_A)]), golden_a, catalog_kit,
                          Budget(hard_s=10, soft_s=5, reserve_s=20))
    assert out["issues"] == []


def test_critic_schema_valid():
    jsonschema.Draft202012Validator.check_schema(critic.CRITIC_SCHEMA)
    assert critic.usable_op({"op": "remove", "path": "/a"}) and not critic.usable_op({"op": "add", "path": "/a"})
    assert not critic.usable_op({}) and not critic.usable_op(None)
