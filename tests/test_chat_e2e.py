"""Live chat runner (harness/chat_e2e.py), persona and score adapter — offline, with a fake HTTP layer.
Owner: agent 4. Nothing here touches the network."""
import json

import pytest

from harness import chat_e2e as ce
from harness import persona as hp
from harness import score as hs


class FakeNet:
    """Answers the routes chat_e2e uses. `replies` = agent lines per chat turn (str, or (status, body))."""

    def __init__(self, replies, close_after=None):
        self.replies = list(replies)
        self.calls = []
        self.turn = 0
        self.close_after = close_after if close_after is not None else len(replies)
        self.messages = []

    def __call__(self, method, url, body=None, headers=None, timeout=45):
        self.calls.append({"method": method, "url": url, "body": body, "headers": headers, "timeout": timeout})
        if url.endswith("/v1/practice/sessions"):
            return 200, {"ok": True, "variables": {"customer_id": "c_fake", "first_name": "A", "last_name": "B",
                                                   "title": "Mr", "now": "2026-10-14T11:00"}}
        if url.endswith("/api/v2/chat/message"):
            self.turn += 1
            self.messages.append({"role": "user", "message": body["message"]})
            r = self.replies[self.turn - 1]
            if isinstance(r, tuple):
                return r
            self.messages.append({"role": "system", "message": json.dumps({"event": "node_enter", "node": "n%d" % self.turn})})
            self.messages.append({"role": "assistant", "message": r})
            return 200, {"success": True, "data": {"message": "ok", "result": {"response": r, "callId": "call1"}}}
        if url.endswith("/api/v2/chat/end"):
            return 200, {"data": {"result": {"ok": True}}}
        if url.endswith("/api/v2/workspaces"):
            return 200, {"data": {"result": {"workspaces": [{"id": "ws1"}]}}}
        if "/api/v2/call/" in url:
            assert "workspaceId=ws1" in url
            return 200, {"data": {"result": {"call": {"messages": list(self.messages)}}}}
        if "/v1/practice/ledger/" in url:
            closed = self.turn >= self.close_after
            calls = [{"tool": "verify_identity", "result": {"ok": True}}]
            if closed:
                calls.append({"tool": "close_call", "result": {"ok": True}})
            return 200, {"outcome": "not_verified" if closed else None, "reason": "failed" if closed else None,
                         "promises": [], "notes": [], "callbacks": [], "transfers": [], "calls": calls}
        return 404, {"error": "unexpected " + url}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("FREYA_API_KEY", "test-not-a-key")
    monkeypatch.setenv("FREYA_BANK_TEAM_KEY", "test-team-key-0000")
    monkeypatch.setenv("FREYA_WORKSPACE_ID", "ws1")
    monkeypatch.setattr(ce, "RESULTS", tmp_path / "chat")
    monkeypatch.setattr(ce, "_WS", None)
    monkeypatch.setattr(ce.time, "sleep", lambda s: None)
    return tmp_path


def _case(public_cases):
    return public_cases["PUB-03"]


def test_run_case_scripted_until_close(env, monkeypatch, public_cases):
    net = FakeNet(["Hello, am I speaking with Mr Park?", "Your date of birth?", "That does not match.",
                   "I could not verify your identity. Goodbye."])
    monkeypatch.setattr(ce, "_request", net)
    rep = ce.run_case("wf1", _case(public_cases), customer="script",
                      script=["Yes.", "12 July 1991", "21 July 1990", "never sent"], gap_s=0)
    assert rep["score"] == {"pass": True, "failed": []}
    assert rep["transcript"][0] == ("customer", "Hello?")
    assert rep["transcript"][-1] == ("agent", "I could not verify your identity. Goodbye.")
    assert rep["turns"] == 4 and rep["call_id"] == "call1" and rep["nodes"] == ["n1", "n2", "n3", "n4"]
    chats = [c for c in net.calls if c["url"].endswith("/chat/message")]
    assert "callId" not in chats[0]["body"] and chats[1]["body"]["callId"] == "call1"
    assert chats[0]["body"]["customerVariables"]["customer_id"] == "c_fake" and chats[0]["timeout"] == 45
    assert any(c["url"].endswith("/chat/end") for c in net.calls)
    sess = net.calls[0]
    assert sess["headers"]["x-team-key"] == "test-team-key-0000" and sess["body"] == {"case": "PUB-03"}
    saved = json.loads(open(rep["_saved"]).read())
    assert saved["case"] == "PUB-03" and saved["ledger"]["outcome"] == "not_verified"


def test_goodbye_without_close_continues_and_lints(env, monkeypatch, public_cases):
    net = FakeNet(["Hi. Goodbye for now.", "Still here.", "Bye."], close_after=3)
    net.messages.append({"role": "assistant", "message": "extra"})
    monkeypatch.setattr(ce, "_request", net)
    spec = {"banned": {"before_verification": ["debt"]}}
    net.replies[1] = "About your debt."
    rep = ce.run_case("wf1", _case(public_cases), customer="script", script=["a", "b", "c"], gap_s=0, spec=spec)
    assert rep["turns"] == 3
    assert any("banned before verification ['debt']" in x for x in rep["lints"])


def test_max_turns_and_script_exhaustion(env, monkeypatch, public_cases):
    monkeypatch.setattr(ce, "_request", FakeNet(["one", "two", "three"], close_after=99))
    rep = ce.run_case("wf1", _case(public_cases), customer="script", script=["x", "y", "z"], max_turns=2, gap_s=0)
    assert rep["turns"] == 2 and not rep["score"]["pass"]
    monkeypatch.setattr(ce, "_request", FakeNet(["one", "two", "three"], close_after=99))
    rep = ce.run_case("wf1", _case(public_cases), customer="script", script=["x"], gap_s=0)
    assert rep["turns"] == 2                                     # "Hello?" + the one scripted line


def test_504_recovers_reply_from_the_stored_call(env, monkeypatch, public_cases):
    net = FakeNet(["Hello?", (504, "Gateway Timeout"), "Goodbye."])
    orig = net.__call__

    def wrapped(method, url, body=None, headers=None, timeout=45):
        out = orig(method, url, body, headers, timeout)
        if url.endswith("/chat/message") and net.turn == 2:      # the platform finished the turn anyway
            net.messages.append({"role": "assistant", "message": "Late reply."})
        return out
    monkeypatch.setattr(ce, "_request", wrapped)
    rep = ce.run_case("wf1", _case(public_cases), customer="script", script=["a", "b"], gap_s=0)
    assert ("agent", "Late reply.") in rep["transcript"]
    assert any("HTTP 504" in e for e in rep["errors"])
    assert rep["score"]["pass"]


def test_transport_error_on_first_turn_stops(env, monkeypatch, public_cases):
    monkeypatch.setattr(ce, "_request", FakeNet([(500, {"error": "boom"})], close_after=99))
    rep = ce.run_case("wf1", _case(public_cases), customer="script", script=["a"], gap_s=0)
    assert rep["turns"] == 1 and rep["call_id"] is None
    assert any("no reply recovered" in e for e in rep["errors"])
    assert not rep["score"]["pass"]


def test_persona_error_and_session_error(env, monkeypatch, public_cases):
    monkeypatch.setattr(ce, "_request", FakeNet(["Hello", "x"], close_after=99))

    def bad(tr):
        raise hp.PersonaError("model down")
    rep = ce.run_case("wf1", _case(public_cases), customer="persona", persona_fn=bad, gap_s=0)
    assert any("persona: model down" in e for e in rep["errors"]) and rep["turns"] == 1

    def no_session(method, url, body=None, headers=None, timeout=45):
        return 404, {"error": "unknown practice case"}
    monkeypatch.setattr(ce, "_request", no_session)
    rep = ce.run_case("wf1", _case(public_cases), customer="script", script=[], gap_s=0)
    assert "practice session" in rep["errors"][0] and rep["score"]["failed"] == ["no ledger"]


def test_missing_credentials_are_reported_not_printed(monkeypatch, tmp_path, public_cases):
    monkeypatch.delenv("FREYA_BANK_TEAM_KEY", raising=False)
    monkeypatch.setattr(ce, "RESULTS", tmp_path)
    monkeypatch.setattr(ce, "_request", lambda *a, **k: pytest.fail("no request without credentials"))
    rep = ce.run_case("wf1", _case(public_cases), customer="script", script=[], gap_s=0)
    assert "FREYA_BANK_TEAM_KEY is not set" in rep["errors"][0]


def test_run_cases_summary_and_main(env, monkeypatch, capsys, public_cases):
    nets = []
    script_file = env / "s.json"
    script_file.write_text(json.dumps({"PUB-03": ["Yes."], "PUB-08": ["Yes."]}))
    nets.append(FakeNet(["Hi", "Goodbye."] * 2, close_after=2))

    def req(method, url, body=None, headers=None, timeout=45):
        n = nets[-1]
        if url.endswith("/v1/practice/sessions"):
            nets.append(FakeNet(["Hi", "Goodbye."], close_after=2))
            n = nets[-1]
        return n(method, url, body, headers, timeout)
    monkeypatch.setattr(ce, "_request", req)
    code = ce.main(["--workflow-id", "wf1", "--case", "PUB-03,PUB-08", "--customer", "script",
                    "--script", str(script_file)])
    out = capsys.readouterr().out
    assert "PASS PUB-03" in out and "PUB-08" in out and "passed" in out
    assert code in (0, 1)
    summaries = list((env / "chat").glob("summary-*.json"))
    assert len(summaries) == 1 and json.loads(summaries[0].read_text())["total"] == 2
    with pytest.raises(SystemExit):
        ce.main(["--workflow-id", "wf1", "--case", "PUB-01", "--customer", "script"])


def test_format_row_and_closed():
    row = {"case": "PUB-01", "pass": False, "turns": 3, "tools": ["verify_identity", "create_promise", "close_call"],
           "failed": ["outcome x"]}
    s = ce.format_row(row)
    assert "FAIL PUB-01" in s and "verify > promise > close_call" in s and "- outcome x" in s
    assert ce._closed({"calls": [{"tool": "close_call"}]}) and not ce._closed({"calls": []})
    assert not ce._closed(None)


def test_request_handles_network_error():
    status, out = ce._request("GET", "http://127.0.0.1:9/never", timeout=1)
    assert status == 0 and isinstance(out, str)


# ---------------------------------------------------------------- persona
def test_persona_prompt_is_kit_text(public_cases):
    p = hp.persona_prompt(public_cases["PUB-01"])
    assert "OUTPUT RULE" in p and public_cases["PUB-01"]["script"] in p
    p2 = hp.persona_prompt(public_cases["PUB-01"], "pieces")
    assert "HOW YOU TALK" in p2


def test_persona_user_prompt_and_clean():
    up = hp.build_user_prompt([("agent", "Hello?"), ("customer", "Hi")])
    assert "Caller: Hello?" in up and "You: Hi" in up
    assert hp.clean('You: "Yes, I confirm."') == "Yes, I confirm."
    assert hp.clean("[sighs] Fine.\nSecond line") == "Fine."
    assert hp.clean("") == ""


def test_next_utterance_errors(monkeypatch):
    async def boom(*a):
        raise RuntimeError("no cli")
    monkeypatch.setattr(hp, "_ask", boom)
    with pytest.raises(hp.PersonaError):
        hp.next_utterance("p", [("agent", "hi")], timeout_s=1)

    async def empty(*a):
        return "  "
    monkeypatch.setattr(hp, "_ask", empty)
    with pytest.raises(hp.PersonaError):
        hp.next_utterance("p", [("agent", "hi")], timeout_s=1)

    async def ok(*a):
        return "Customer: Yes, speaking."
    monkeypatch.setattr(hp, "_ask", ok)
    assert hp.next_utterance("p", [("agent", "hi")], timeout_s=1) == "Yes, speaking."


# ---------------------------------------------------------------- score adapter
def test_score_adapter_accepts_expected_or_case_and_survives_bad_ledger(public_cases):
    exp = public_cases["PUB-05"]["expected"]
    led = {"outcome": "no_promise", "reason": "hardship", "calls": [{"tool": "close_call", "result": {}}]}
    assert hs.score_ledger(exp, led)["pass"]
    assert hs.score_ledger(public_cases["PUB-05"], led)["pass"]
    bad = hs.score_ledger(exp, {"promises": [{"product_id": "p1"}]})
    assert not bad["pass"] and "scorer crashed" in bad["failed"][0]


def test_lint_messages_and_node_path():
    msgs = [{"role": "assistant", "message": "Hello, about your loan"},
            {"role": "user", "message": "yes"},
            {"role": "system", "message": json.dumps({"event": "node_enter", "node": "ctl"})},
            {"role": "system", "message": json.dumps({"event": "function_call_complete", "function": "get_account",
                                                      "result": {"data": {"ok": "True"}}})},
            {"role": "assistant", "message": "Your loan is late."},
            {"role": "assistant", "message": "Second line."},
            {"role": "system", "message": "not json"}]
    fails = hs.lint_messages(msgs, ["loan"])
    assert any("banned before verification ['loan']" in f for f in fails)
    assert sum("banned" in f for f in fails) == 1                  # after get_account ok: allowed
    assert any("more than one assistant message" in f for f in fails)
    assert hs.node_path(msgs) == ["ctl"]
    assert hs.banned_hits("Card, cards", ["card"]) == ["card"] and hs.banned_hits("discard", ["card"]) == []
    assert hs.parse_event({"message": {"event": "x"}}) == {"event": "x"}


def test_lines_before_verified_from_twin_events(catalog_kit):
    ev = [{"event": "say", "text": "a"},
          {"event": "function_call_complete", "function": "verify_identity",
           "result": {"data": {"ok": True, "all_verified": False}}},
          {"event": "say", "text": "b"},
          {"event": "function_call_complete", "function": "verify_identity",
           "result": {"data": {"ok": True, "all_verified": True}}},
          {"event": "say", "text": "c"}]
    assert hs.lines_before_verified(ev, catalog_kit) == ["a", "b"]
    assert hs.lines_before_verified(ev, None) == ["a", "b", "c"]
