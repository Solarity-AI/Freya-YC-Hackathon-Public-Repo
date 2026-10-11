"""Coverage + behaviour for harness/persona.py and harness/score.py (offline; the persona model is faked)."""
import asyncio
import json
import sys
import types

import pytest

from harness import persona as hp
from harness import score as hs


# ---------------------------------------------------------------- persona: prompt text
def _case(public_cases, cid="PUB-12", now=None):
    c = json.loads(json.dumps(public_cases[cid]))
    if now is not None:
        c["variables"]["now"] = now
    return c


def test_persona_prompt_states_the_call_today_with_weekday_and_time(public_cases):
    p = hp.persona_prompt(_case(public_cases, now="2026-10-14T11:05"))
    # 14 October 2026 is a Wednesday: relative days must count from the scenario's today, not the model's clock
    assert p.endswith("In this call, today is Wednesday, 2026-10-14 (time 11:05). Relative days ('tomorrow', "
                      "'Friday') count from this date.")


def test_persona_prompt_date_only_now_has_unknown_time(public_cases):
    p = hp.persona_prompt(_case(public_cases, now="2026-10-16"))
    assert "today is Friday, 2026-10-16 (time unknown)" in p


def test_persona_prompt_unparseable_or_empty_now_adds_nothing(public_cases):
    bad = hp.persona_prompt(_case(public_cases, now="next tuesday"))
    assert "In this call" not in bad
    empty = hp.persona_prompt(_case(public_cases, now=""))
    assert "In this call" not in empty
    import builder.paths as bp
    kit = bp.import_kit("run_cases")
    c = _case(public_cases, now="next tuesday")
    assert bad == kit.persona_for(c, {"identity": c["identity"]}, None)["prompt"]


def test_render_transcript_roles():
    assert hp.render_transcript([("agent", "Hi"), ("customer", "Yo"), ("agent", "Ok")]) == \
        "Caller: Hi\nYou: Yo\nCaller: Ok"
    assert hp.render_transcript([]) == ""


@pytest.mark.parametrize("raw,want", [
    ("me: hello", "hello"),
    ("CUSTOMER : Yes", "Yes"),
    ("'Single quoted.'", "Single quoted."),
    ("*laughs* Sure, go ahead.", "Sure, go ahead."),
    ('"', '"'),                                  # a lone quote is not a quoted string
    ("  [pause]  ", ""),
    (None, ""),
    ("First.\nSecond.", "First."),
])
def test_clean_variants(raw, want):
    assert hp.clean(raw) == want


# ---------------------------------------------------------------- persona: model call through a fake SDK
class _Text:
    def __init__(self, text):
        self.text = text


class _Other:
    pass


class _Assistant:
    def __init__(self, content):
        self.content = content


class _Result:
    def __init__(self, result):
        self.result = result


class _Opts:
    def __init__(self, **kw):
        self.kw = kw


def _fake_sdk(monkeypatch, messages, seen):
    mod = types.ModuleType("claude_agent_sdk")
    mod.AssistantMessage, mod.ResultMessage, mod.TextBlock, mod.ClaudeAgentOptions = _Assistant, _Result, _Text, _Opts

    async def query(prompt, options):
        seen.append({"prompt": prompt, "options": options.kw})
        for m in messages:
            yield m
    mod.query = query
    monkeypatch.setitem(sys.modules, "claude_agent_sdk", mod)


def test_ask_joins_text_blocks_and_passes_one_turn_no_tool_options(monkeypatch):
    seen = []
    _fake_sdk(monkeypatch, [_Assistant([_Text("Yes, "), _Other(), _Text("speaking.")]), object(),
                            _Result("ignored when text exists")], seen)
    out = asyncio.run(hp._ask("SYSTEM", "PROMPT", "m1"))
    assert out == "Yes, speaking."
    o = seen[0]["options"]
    assert seen[0]["prompt"] == "PROMPT"
    assert o == {"system_prompt": "SYSTEM", "model": "m1", "max_turns": 1, "tools": [], "allowed_tools": [],
                 "setting_sources": []}


def test_ask_falls_back_to_result_then_empty(monkeypatch):
    _fake_sdk(monkeypatch, [_Assistant([]), _Result("From result.")], [])
    assert asyncio.run(hp._ask("s", "p", "m")) == "From result."
    _fake_sdk(monkeypatch, [_Result(None)], [])
    assert asyncio.run(hp._ask("s", "p", "m")) == ""


def test_next_utterance_model_choice_env_and_default(monkeypatch):
    seen = []
    _fake_sdk(monkeypatch, [_Assistant([_Text("You: \"Fine.\"")])], seen)
    monkeypatch.delenv("HARNESS_PERSONA_MODEL", raising=False)
    assert hp.next_utterance("P", [("agent", "Hello?")]) == "Fine."
    assert seen[-1]["options"]["model"] == hp.DEFAULT_MODEL == "claude-haiku-4-5"
    assert "Caller: Hello?" in seen[-1]["prompt"] and seen[-1]["prompt"].endswith("no stage directions.")
    monkeypatch.setenv("HARNESS_PERSONA_MODEL", "env-model")
    hp.next_utterance("P", [("agent", "Hello?")])
    assert seen[-1]["options"]["model"] == "env-model"
    hp.next_utterance("P", [("agent", "Hello?")], model="explicit")
    assert seen[-1]["options"]["model"] == "explicit"


def test_next_utterance_timeout_is_persona_error(monkeypatch):
    async def slow(*a):
        await asyncio.sleep(5)
        return "late"
    monkeypatch.setattr(hp, "_ask", slow)
    with pytest.raises(hp.PersonaError, match="TimeoutError"):
        hp.next_utterance("p", [("agent", "hi")], timeout_s=0.01)


def test_next_utterance_only_stage_direction_is_empty_error(monkeypatch):
    async def stage(*a):
        return "[hangs up]"
    monkeypatch.setattr(hp, "_ask", stage)
    with pytest.raises(hp.PersonaError, match="empty persona reply"):
        hp.next_utterance("p", [("agent", "hi")], timeout_s=1)


# ---------------------------------------------------------------- score adapter
def test_score_ledger_fills_missing_lists_and_none_ledger(public_cases):
    exp = public_cases["PUB-03"]["expected"]                       # not_verified / failed, nothing recorded
    led = {"outcome": exp["outcome"], "reason": exp["reason"], "calls": [{"tool": "close_call", "result": {}}]}
    assert hs.score_ledger(exp, led) == {"pass": True, "failed": []}
    r = hs.score_ledger(exp, None)
    assert r["pass"] is False and r["failed"] and not any("crashed" in f for f in r["failed"])


def test_banned_hits_none_and_phrases():
    assert hs.banned_hits(None, ["debt"]) == []
    assert hs.banned_hits("Your Late Payment", None) == []
    assert hs.banned_hits("Your Late Payment.", ["late payment", "pay"]) == ["late payment"]


def test_ok_true_shapes():
    assert hs._ok_true({"ok": True}, "ok") and hs._ok_true({"ok": "TRUE"}, "ok")
    assert not hs._ok_true({"ok": False}, "ok") and not hs._ok_true("true", "ok") and not hs._ok_true(None, "ok")


def test_lines_before_verified_get_account_and_default_leaf(catalog_kit):
    ev = [{"event": "say", "text": "a"},
          {"event": "function_call_complete", "function": "get_account", "result": {"data": {"ok": False}}},
          {"event": "say"},
          {"event": "function_call_complete", "function": "verify_identity", "result": None},
          {"event": "node_enter", "node": "x"},
          {"event": "function_call_complete", "function": "get_account", "result": {"data": {"ok": True}}},
          {"event": "say", "text": "after"}]
    assert hs.lines_before_verified(ev, catalog_kit) == ["a", ""]
    assert hs.lines_before_verified(ev, None) == ["a", ""]            # default success leaf "ok"
    renamed = {"tools": {"get_account": {"roles": {"response": {"s": "success"}}}}}
    assert hs.lines_before_verified(ev, renamed) == ["a", "", "after"]  # "ok" is not the success leaf there


def _sys(ev):
    return {"role": "system", "message": json.dumps(ev)}


def test_lint_messages_resolves_api_call_by_url_path_and_last_segment(catalog_kit):
    url = catalog_kit["tools"]["verify_identity"]["url"]
    msgs = [{"role": "assistant", "message": "Hello about your debt"},
            {"role": "tool", "message": "ignored role"},
            {"role": "user", "message": "hi"},
            _sys({"event": "function_call_start", "function": "api_call", "args": {"url": url}}),
            _sys({"event": "function_call_complete", "function": "api_call",
                  "result": {"data": {"ok": True, "all_verified": False}}}),
            {"role": "assistant", "message": "still before: debt"},
            {"role": "user", "message": "1234"},
            _sys({"event": "function_call_start", "function": "api_call",
                  "args": {"url": "https://proxy.example/v9/verify_identity"}}),       # path match
            _sys({"event": "function_call_complete", "function": "api_call",
                  "result": {"data": {"ok": True, "all_verified": "true"}}}),
            {"role": "assistant", "message": "Verified, your debt is 10."}]
    fails = hs.lint_messages(msgs, ["debt"], catalog_kit)
    assert [f.split(" in ")[0] for f in fails] == ["banned before verification ['debt']"] * 2


def test_lint_messages_without_catalog_uses_url_last_segment():
    msgs = [_sys({"event": "function_call_start", "args": {"url": "https://bank.example/v1/get_account/"}}),
            _sys({"event": "function_call_complete", "name": "api_call", "result": {"data": {"ok": "true"}}}),
            {"role": "assistant", "message": "your debt"}]
    assert hs.lint_messages(msgs, ["debt"]) == []
    # no url: the tool stays unknown and the line is still before verification
    msgs[0] = _sys({"event": "function_call_start", "args": {}})
    assert len(hs.lint_messages(msgs, ["debt"])) == 1


def test_lint_messages_non_dict_result_and_failed_reads(catalog_kit):
    msgs = [_sys({"event": "function_call_complete", "function": "get_account", "result": "error text"}),
            _sys({"event": "function_call_complete", "function": "get_account", "result": {"data": {"ok": False}}}),
            _sys({"event": "function_call_complete", "function": "verify_identity",
                  "result": {"data": {"ok": True, "all_verified": True}}}),
            {"role": "assistant", "message": "debt"}]
    assert hs.lint_messages(msgs, ["debt"], None) != []               # no catalog: no `all` leaf known
    assert hs.lint_messages(msgs, ["debt"], catalog_kit) == []
    assert hs.lint_messages(None) == []


def test_lint_counts_only_the_second_extra_assistant_message():
    msgs = [{"role": "assistant", "message": "a"}, {"role": "assistant", "message": "b"},
            {"role": "assistant", "message": None}, {"role": "user", "message": "x"},
            {"role": "assistant", "message": "c"}]
    fails = hs.lint_messages(msgs)
    assert fails == ["more than one assistant message after a customer turn: 'b'"]


def test_parse_event_and_node_path_fallbacks():
    assert hs.parse_event({"message": "[1, 2]"}) == {}
    assert hs.parse_event({"message": None}) == {}
    assert hs.parse_event({"message": 5}) == {}
    assert hs.parse_event({}) == {}
    msgs = [_sys({"event": "node_enter", "node_id": "n_id"}), _sys({"event": "node_enter"}),
            {"role": "assistant", "message": json.dumps({"event": "node_enter", "node": "no"})},
            _sys({"event": "say", "node": "no"})]
    assert hs.node_path(msgs) == ["n_id", ""]
    assert hs.node_path(None) == []
