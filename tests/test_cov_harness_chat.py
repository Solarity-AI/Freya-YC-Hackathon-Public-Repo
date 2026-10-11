"""Coverage + behaviour for harness/chat_e2e.py with a fake network (urllib and the `_request` seam are faked;
nothing here touches the platform or the bank)."""
import io
import json
import runpy
import socket
import sys
import urllib.error

import pytest

from harness import chat_e2e as ce


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("FREYA_API_KEY", "test-not-a-key")
    monkeypatch.setenv("FREYA_BANK_TEAM_KEY", "test-team-key-0000")
    monkeypatch.setenv("FREYA_WORKSPACE_ID", "ws1")
    monkeypatch.setenv("FREYA_API_URL", "https://freya.example/")
    monkeypatch.setattr(ce, "RESULTS", tmp_path / "chat")
    monkeypatch.setattr(ce, "_WS", None)
    monkeypatch.setattr(ce.time, "sleep", lambda s: None)
    return tmp_path


class Net:
    """Route table: handlers[route] = callable(method, url, body) -> (status, body) or a fixed (status, body)."""

    def __init__(self, **handlers):
        self.h = handlers
        self.calls = []

    def __call__(self, method, url, body=None, headers=None, timeout=45):
        self.calls.append((method, url, body, timeout))
        for key, route in (("session", "/v1/practice/sessions"), ("chat", "/api/v2/chat/message"),
                           ("end", "/api/v2/chat/end"), ("ws", "/api/v2/workspaces"), ("call", "/api/v2/call/"),
                           ("ledger", "/v1/practice/ledger/")):
            if route in url:
                h = self.h.get(key)
                if h is None:
                    return 404, {"error": "no route " + key}
                return h(method, url, body) if callable(h) else h
        return 404, "unexpected"


SESSION = (200, {"variables": {"customer_id": "c_fake", "now": "2026-10-14T11:00"}})
CLOSED = (200, {"outcome": "not_verified", "reason": "failed", "promises": [], "notes": [], "callbacks": [],
                "transfers": [], "calls": [{"tool": "close_call", "result": {"ok": True}}]})


def _chat(*replies):
    it = iter(replies)

    def h(method, url, body):
        r = next(it)
        if isinstance(r, tuple):
            return r
        return 200, {"data": {"result": {"response": r, "callId": "call1"}}}
    return h


# ---------------------------------------------------------------- _request (urllib faked)
class _Resp:
    def __init__(self, raw, status=200):
        self.raw, self.status = raw, status

    def read(self):
        return self.raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_request_parses_json_and_sends_body_headers(monkeypatch):
    seen = {}

    def urlopen(req, timeout):
        seen.update(url=req.full_url, data=req.data, method=req.get_method(), timeout=timeout,
                    ua=req.get_header("User-agent"))
        return _Resp(b'{"a": 1}', 201)
    monkeypatch.setattr(ce.urllib.request, "urlopen", urlopen)
    assert ce._request("POST", "https://x.example/p", {"k": "v"}, {"User-Agent": "ua"}, 7) == (201, {"a": 1})
    assert seen == {"url": "https://x.example/p", "data": b'{"k": "v"}', "method": "POST", "timeout": 7, "ua": "ua"}


def test_request_non_json_body_is_text(monkeypatch):
    monkeypatch.setattr(ce.urllib.request, "urlopen", lambda req, timeout: _Resp(b"plain \xff text"))
    status, out = ce._request("GET", "https://x.example/p")
    assert status == 200 and out == "plain � text"


def test_request_http_error_returns_its_status_and_body(monkeypatch):
    def urlopen(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 504, "Gateway Timeout", {}, io.BytesIO(b'{"error": "slow"}'))
    monkeypatch.setattr(ce.urllib.request, "urlopen", urlopen)
    assert ce._request("GET", "https://x.example/p") == (504, {"error": "slow"})


@pytest.mark.parametrize("exc", [socket.timeout("timed out"), ConnectionResetError("reset"),
                                 urllib.error.URLError("dns")])
def test_request_transport_errors_are_status_zero(monkeypatch, exc):
    def urlopen(req, timeout):
        raise exc
    monkeypatch.setattr(ce.urllib.request, "urlopen", urlopen)
    status, out = ce._request("GET", "https://x.example/p")
    assert status == 0 and out.startswith(type(exc).__name__ + ": ")


# ---------------------------------------------------------------- small helpers
def test_result_unwraps_only_the_envelope():
    assert ce._result({"data": {"result": {"x": 1}}}) == {"x": 1}
    assert ce._result({"data": {"other": 1}}) == {"data": {"other": 1}}
    assert ce._result({"data": [1]}) == {"data": [1]}
    assert ce._result("text") == "text"


def test_freya_url_default_and_override(monkeypatch):
    monkeypatch.delenv("FREYA_API_URL", raising=False)
    assert ce._freya_url("/a") == "https://staging-app.freyavoice.ai/a"
    monkeypatch.setenv("FREYA_API_URL", "https://f.example///")
    assert ce._freya_url("/a") == "https://f.example/a"


def test_chat_turn_unexpected_body_is_transport_error(env, monkeypatch):
    monkeypatch.setattr(ce, "_request", Net(chat=(200, {"data": {"result": "not a dict"}})))
    with pytest.raises(ce.ChatTransportError) as ei:
        ce.chat_turn("wf", "hi", {}, call_id="c9")
    assert "unexpected body" in str(ei.value) and ei.value.code == 200 and ei.value.call_id == "c9"


def test_chat_turn_keeps_call_id_and_empty_response(env, monkeypatch):
    monkeypatch.setattr(ce, "_request", Net(chat=(200, {"data": {"result": {"response": None}}})))
    assert ce.chat_turn("wf", "hi", {}, call_id="c9") == ("", "c9")


def test_end_chat_without_call_id_sends_nothing(env, monkeypatch):
    monkeypatch.setattr(ce, "_request", lambda *a, **k: pytest.fail("no request"))
    assert ce.end_chat(None) is None


def test_end_chat_error_status_reports_text(env, monkeypatch):
    monkeypatch.setattr(ce, "_request", Net(end=(500, {"error": "x"})))
    assert ce.end_chat("c1") == {"status": 500, "result": "{'error': 'x'}"}


def test_workspace_id_lookup_list_items_and_cache(env, monkeypatch):
    monkeypatch.delenv("FREYA_WORKSPACE_ID")
    net = Net(ws=(200, {"data": {"result": {"items": [{"id": "wsA"}, {"id": "wsB"}]}}}))
    monkeypatch.setattr(ce, "_request", net)
    assert ce.workspace_id() == "wsA" and ce.workspace_id() == "wsA"
    assert len(net.calls) == 1                                       # cached after the first lookup
    monkeypatch.setattr(ce, "_WS", None)
    monkeypatch.setattr(ce, "_request", Net(ws=(200, {"data": {"result": [{"id": "wsL"}]}})))
    assert ce.workspace_id() == "wsL"


@pytest.mark.parametrize("resp", [(401, {"error": "auth"}), (200, {"data": {"result": {"workspaces": []}}}),
                                  (200, {"data": {"result": {}}})])
def test_workspace_id_failures(env, monkeypatch, resp):
    monkeypatch.delenv("FREYA_WORKSPACE_ID")
    monkeypatch.setattr(ce, "_request", Net(ws=resp))
    with pytest.raises(ce.ChatError, match="cannot read the workspace id: HTTP %s" % resp[0]):
        ce.workspace_id()


def test_get_call_error_and_shapes(env, monkeypatch):
    monkeypatch.setattr(ce, "_request", Net(call=(500, "boom")))
    with pytest.raises(ce.ChatError, match="get call HTTP 500"):
        ce.get_call("c1")
    monkeypatch.setattr(ce, "_request", Net(call=(200, {"data": {"result": {"messages": [1]}}})))
    assert ce.get_call("c1") == {"messages": [1]}                    # no "call" wrapper
    monkeypatch.setattr(ce, "_request", Net(call=(200, {"data": {"result": "x"}})))
    assert ce.get_call("c1") == {}


def test_get_ledger_errors(env, monkeypatch):
    monkeypatch.setattr(ce, "_request", Net(ledger=(404, {"error": "unknown customer"})))
    with pytest.raises(ce.ChatError, match="ledger HTTP 404"):
        ce.get_ledger("c_x")
    monkeypatch.setattr(ce, "_request", Net(ledger=(200, "not json")))
    with pytest.raises(ce.ChatError, match="ledger HTTP 200: not json"):
        ce.get_ledger("c_x")


def test_create_session_rejects_body_without_variables(env, monkeypatch):
    monkeypatch.setattr(ce, "_request", Net(session=(200, {"variables": "nope"})))
    with pytest.raises(ce.ChatError, match="practice session for PUB-01 failed: HTTP 200"):
        ce.create_session("PUB-01")


def test_recover_reply_variants(env, monkeypatch):
    msgs = [{"role": "assistant", "message": "old"}, {"role": "user", "message": "u1"},
            {"role": "assistant", "message": "A"}, {"role": "system", "message": "{}"},
            {"role": "assistant", "message": ""}, {"role": "assistant", "message": "B"}]
    monkeypatch.setattr(ce, "_request", Net(call=(200, {"data": {"result": {"call": {"messages": msgs}}}})))
    assert ce._recover_reply("c1") == "A B"
    monkeypatch.setattr(ce, "_request", Net(call=(200, {"data": {"result": {"call": {"messages": msgs[:2]}}}})))
    assert ce._recover_reply("c1") is None                           # nothing after the last user message
    no_user = [{"role": "assistant", "message": "Hi"}]
    monkeypatch.setattr(ce, "_request", Net(call=(200, {"data": {"result": {"call": {"messages": no_user}}}})))
    assert ce._recover_reply("c1") == "Hi"
    monkeypatch.setattr(ce, "_request", Net(call=(503, "down")))
    assert ce._recover_reply("c1") is None


# ---------------------------------------------------------------- run_case error paths
def _msgs_handler(msgs):
    return lambda m, u, b: (200, {"data": {"result": {"call": {"messages": list(msgs)}}}})


def test_goodbye_ledger_error_is_reported_and_case_continues(env, monkeypatch, public_cases):
    state = {"n": 0}

    def ledger(m, u, b):
        state["n"] += 1
        return (500, "bank down") if state["n"] == 1 else CLOSED
    net = Net(session=SESSION, chat=_chat("Goodbye then.", "Goodbye."), end=(200, {}), call=_msgs_handler([]),
              ledger=ledger)
    monkeypatch.setattr(ce, "_request", net)
    rep = ce.run_case("wf", public_cases["PUB-03"], customer="script", script=["still here"], gap_s=0)
    assert rep["errors"][0].startswith("ledger: ledger HTTP 500")
    assert rep["turns"] == 2 and rep["score"]["pass"]               # 2nd goodbye: ledger closed -> stop


def test_end_chat_exception_and_final_reads_fail(env, monkeypatch, public_cases):
    state = {"ledger": 0}

    def end(m, u, b):
        raise RuntimeError("socket closed")

    def ledger(m, u, b):
        state["ledger"] += 1
        return 503, "down"
    net = Net(session=SESSION, chat=_chat("Hello"), end=end, call=(500, "x"), ledger=ledger)
    monkeypatch.setattr(ce, "_request", net)
    rep = ce.run_case("wf", "PUB-03", customer="script", script=[], gap_s=0)
    errs = rep["errors"]
    assert "chat end: socket closed" in errs
    assert "get call: get call HTTP 500" in errs
    assert any(e.startswith("ledger HTTP 503") for e in errs)
    assert rep["messages"] == [] and rep["nodes"] == [] and rep["ledger"] is None
    assert rep["score"] == {"pass": False, "failed": ["no ledger"]} and rep["case"] == "PUB-03"


def test_transport_error_recovered_empty_reply_checks_ledger(env, monkeypatch, public_cases):
    msgs = [{"role": "user", "message": "Hello?"}, {"role": "assistant", "message": "Hi there"},
            {"role": "user", "message": "more"}, {"role": "assistant", "message": ""}]
    net = Net(session=SESSION, chat=_chat("Hi there", (504, "Gateway Timeout")), end=(200, {}),
              call=_msgs_handler(msgs), ledger=CLOSED)
    monkeypatch.setattr(ce, "_request", net)
    rep = ce.run_case("wf", public_cases["PUB-03"], customer="script", script=["more"], gap_s=0)
    # turn 2 timed out; the stored call holds an empty assistant line -> "" reply -> ledger closed -> stop
    assert rep["transcript"][-1] == ("agent", "") and rep["turns"] == 2
    assert rep["errors"] == ["turn 2: chat turn HTTP 504: Gateway Timeout"]


def test_persona_mode_uses_kit_persona_and_next_utterance(env, monkeypatch, public_cases):
    seen = []

    def nxt(ptext, tr):
        seen.append((ptext, list(tr)))
        return None                                                  # the persona has nothing more to say
    monkeypatch.setattr(ce.hpersona, "next_utterance", nxt)
    net = Net(session=SESSION, chat=_chat("Am I speaking with Ms Costa?"), end=(200, {}), call=_msgs_handler([]),
              ledger=CLOSED)
    monkeypatch.setattr(ce, "_request", net)
    rep = ce.run_case("wf", public_cases["PUB-02"], customer="persona", style="pieces", gap_s=0)
    assert rep["turns"] == 1 and len(seen) == 1
    assert "HOW YOU TALK" in seen[0][0] and seen[0][1] == [("customer", "Hello?"),
                                                           ("agent", "Am I speaking with Ms Costa?")]


def test_gap_between_turns_sleeps(env, monkeypatch, public_cases):
    sleeps = []
    monkeypatch.setattr(ce.time, "sleep", lambda s: sleeps.append(s))
    net = Net(session=SESSION, chat=_chat("one", "two"), end=(200, {}), call=_msgs_handler([]), ledger=CLOSED)
    monkeypatch.setattr(ce, "_request", net)
    ce.run_case("wf", public_cases["PUB-03"], customer="script", script=["x"], gap_s=5)
    assert len(sleeps) == 1 and 4 < sleeps[0] <= 5                   # only before the 2nd turn


# ---------------------------------------------------------------- run_cases / main
def test_run_cases_single_case_writes_out_and_rows(env, monkeypatch, public_cases):
    net = Net(session=SESSION, chat=_chat("Goodbye."), end=(200, {}), call=_msgs_handler([]), ledger=CLOSED)
    monkeypatch.setattr(ce, "_request", net)
    lines = []
    out = env / "one.json"
    s = ce.run_cases("wf", ["PUB-03"], "script", ["x"], out=str(out), printer=lines.append)
    assert json.loads(out.read_text())["case"] == "PUB-03"
    assert s["passed"] == 1 and s["rows"][0]["tools"] == ["close_call"] and s["rows"][0]["report"] == str(out)
    assert lines[0].startswith("PASS PUB-03") and lines[-1] == "1 / 1 passed (ledger + transcript lints)"


def test_run_cases_lint_failure_makes_row_fail(env, monkeypatch, public_cases):
    msgs = [{"role": "assistant", "message": "a"}, {"role": "assistant", "message": "b"}]
    net = Net(session=SESSION, chat=_chat("Goodbye."), end=(200, {}), call=_msgs_handler(msgs), ledger=CLOSED)
    monkeypatch.setattr(ce, "_request", net)
    s = ce.run_cases("wf", ["PUB-03"], "script", {"PUB-03": ["x"]}, printer=lambda x: None)
    row = s["rows"][0]
    assert row["ledger_pass"] and not row["pass"] and s["passed"] == 0
    assert any("more than one assistant message" in f for f in row["failed"])


def test_format_row_without_tools():
    s = ce.format_row({"case": "PUB-09", "pass": True, "turns": 12, "tools": [], "failed": []})
    assert s == "PASS PUB-09  turns=12  | (no tool calls)"


def test_main_model_spec_missing_tools_and_exit_codes(env, monkeypatch):
    monkeypatch.delenv("HARNESS_PERSONA_MODEL", raising=False)
    seen = {}

    def fake_run_cases(wf, cases, customer, scripts, style, max_turns, spec, out, catalog=None):
        seen.update(wf=wf, cases=cases, customer=customer, scripts=scripts, style=style, max_turns=max_turns,
                    spec=spec, out=out, catalog=catalog)
        return {"passed": 1, "total": 2}
    monkeypatch.setattr(ce, "run_cases", fake_run_cases)
    spec = env / "spec.json"
    spec.write_text(json.dumps({"banned": {"before_verification": ["debt"]}}))
    code = ce.main(["--workflow-id", "W", "--case", "PUB-01, PUB-02", "--case", "PUB-03", "--model", "m-x",
                    "--spec", str(spec), "--tools", str(env / "missing.json"), "--max-turns", "4",
                    "--style", "corrects"])
    assert code == 1
    assert seen["cases"] == ["PUB-01", "PUB-02", "PUB-03"] and seen["catalog"] is None
    assert seen["spec"] == {"banned": {"before_verification": ["debt"]}} and seen["max_turns"] == 4
    assert seen["style"] == "corrects" and seen["customer"] == "persona" and seen["scripts"] is None
    assert ce.os.environ["HARNESS_PERSONA_MODEL"] == "m-x"
    monkeypatch.delenv("HARNESS_PERSONA_MODEL")


def test_main_loads_default_kit_tools_catalog(env, monkeypatch):
    seen = {}

    def fake_run_cases(*a, catalog=None):
        seen["catalog"] = catalog
        return {"passed": 1, "total": 1}
    monkeypatch.setattr(ce, "run_cases", fake_run_cases)
    assert ce.main(["--workflow-id", "W", "--case", "PUB-01"]) == 0
    assert set(seen["catalog"]["tools"]) >= {"verify_identity", "get_account", "close_call"}


def test_module_entry_point_runs_main(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["chat_e2e", "--help"])
    monkeypatch.delitem(sys.modules, "harness.chat_e2e", raising=False)
    with pytest.raises(SystemExit) as ei:
        runpy.run_module("harness.chat_e2e", run_name="__main__")
    assert ei.value.code == 0 and "--workflow-id" in capsys.readouterr().out


def test_main_unknown_case_id_is_a_clean_error(env, monkeypatch, capsys):
    monkeypatch.setattr(ce, "_request", lambda *a, **k: pytest.fail("no request for an unknown case"))
    assert ce.main(["--workflow-id", "W", "--case", "PUB-99", "--customer", "script", "--script",
                    str(_script_file(env))]) == 2
    assert "PUB-99" in capsys.readouterr().err


def _script_file(env):
    p = env / "s.json"
    p.write_text(json.dumps(["x"]))
    return p


# ----------------------------------------------------------------------------------------------- our mock (final)
MOCK_CASE = {"id": "TRF-X", "mock_customer": "FB-1", "variables": {"musteri_no": "FB-1", "ad": "Ayşe", "now": "2026-10-21T10:30"},
             "customer_lines": ["Evet, benim.", "Tamam."],
             "expected_ledger": [{"op": "Promise", "body": {"musteri_no": "FB-1", "tutar": 10.5, "tip": "TAMAMI"}},
                                 {"op": "Close", "body": {"musteri_no": "FB-1", "sonuc": "OK"}}]}


def _mock_ledger(closed=True, calls=None):
    return {"customer_id": "FB-1", "closed": closed, "calls": calls if calls is not None else [
        {"tool": "Verify", "status": 200, "args": {}, "result": {"ok": True}},
        {"tool": "Promise", "status": 200, "args": {"musteri_no": "FB-1", "tutar": "10.50", "tip": "TAMAMI"},
         "result": {"ok": True}},
        {"tool": "Close", "status": 200, "args": {"musteri_no": "FB-1", "sonuc": "OK"}, "result": {"ok": True}}]}


class MockNet:
    def __init__(self, ledger, reset=(200, {"ok": True})):
        self.ledger, self.reset, self.calls, self.n = ledger, reset, [], 0

    def __call__(self, method, url, body=None, headers=None, timeout=45):
        self.calls.append((method, url, body))
        if "/reset/" in url:
            return self.reset
        if "/ledger/" in url:
            return 200, self.ledger
        if "/chat/message" in url:
            self.n += 1
            return 200, {"data": {"result": {"response": "Hoşça kalın." if self.n > 1 else "Merhaba.",
                                              "callId": "call-1"}}}
        if "/chat/end" in url:
            return 200, {"data": {"result": {"ok": True}}}
        if "/api/v2/call/" in url:
            return 200, {"data": {"result": {"call": {"messages": []}}}}
        return 404, "no route"


def test_score_mock_pass_and_failures():
    assert ce.score_mock(MOCK_CASE, _mock_ledger()) == {"pass": True, "failed": []}
    bad = _mock_ledger(calls=[{"tool": "Promise", "status": 200, "args": {"musteri_no": "FB-1", "tutar": 9,
                                                                          "tip": "KISMI"}, "result": {"ok": True}},
                              {"tool": "Promise", "status": 200, "args": {}, "result": {"ok": False}},
                              {"tool": "Close", "status": 500, "args": {}, "result": {}}])
    got = ce.score_mock(MOCK_CASE, bad)["failed"]
    assert "Promise.tutar want 10.5 got 9" in got and "Promise.tip want 'TAMAMI' got 'KISMI'" in got
    assert "missing call Close" in got
    twice = _mock_ledger()
    twice["calls"].insert(1, dict(twice["calls"][1]))
    assert ce.score_mock(MOCK_CASE, twice)["failed"] == ["Promise recorded 2 times (want 1)"]


def test_score_mock_long_text_only_needs_presence():
    case = {"expected_ledger": [{"op": "Note", "body": {"text": "x" * 50}}]}
    led = {"calls": [{"tool": "Note", "status": 200, "args": {"text": "anything"}, "result": {"ok": True}}]}
    assert ce.score_mock(case, led)["pass"]
    assert not ce.score_mock(case, {"calls": [{"tool": "Note", "status": 200, "args": {}, "result": {}}]})["pass"]


def test_same_numbers_and_text():
    assert ce._same(10.5, "10.50") and not ce._same(10.5, "abc") and ce._same("A", "A") and not ce._same(1, None)


def test_closed_reads_the_mock_flag():
    assert ce._closed({"closed": True, "calls": []}) is True
    assert ce._closed({"closed": False, "calls": [{"tool": "close_call"}]}) is False


def test_mock_session_and_ledger(env, monkeypatch):
    net = MockNet(_mock_ledger())
    monkeypatch.setattr(ce, "_request", net)
    variables, cid = ce.mock_session("https://m.example/", MOCK_CASE)
    assert cid == "FB-1" and variables["musteri_no"] == "FB-1"
    assert net.calls[0][:2] == ("POST", "https://m.example/reset/FB-1")
    assert ce.mock_ledger("https://m.example", "FB-1")["closed"] is True
    monkeypatch.setattr(ce, "_request", MockNet(_mock_ledger(), reset=(404, {"error": "unknown"})))
    with pytest.raises(ce.ChatError):
        ce.mock_session("https://m.example", MOCK_CASE)
    monkeypatch.setattr(ce, "_request", lambda *a, **k: (500, "down"))
    with pytest.raises(ce.ChatError):
        ce.mock_ledger("https://m.example", "FB-1")


def test_run_case_on_the_mock(env, monkeypatch):
    net = MockNet(_mock_ledger())
    monkeypatch.setattr(ce, "_request", net)
    rep = ce.run_case("W", MOCK_CASE, "script", ["Evet, benim."], mock_url="https://m.example", first="Alo?",
                      gap_s=0)
    assert rep["customer_id"] == "FB-1" and rep["score"]["pass"], rep
    sent = [c[2]["message"] for c in net.calls if "/chat/message" in c[1]]
    assert sent[0] == "Alo?" and sent[1] == "Evet, benim."
    assert not any("/v1/practice" in c[1] for c in net.calls)


def test_main_mock_mode_uses_case_lines(env, monkeypatch, tmp_path):
    cf = tmp_path / "cases.json"
    cf.write_text(json.dumps([MOCK_CASE]))
    seen = {}

    def fake_run_cases(wf, case_ids, customer, scripts, style, max_turns, spec, out, catalog=None, **kw):
        seen.update(kw, case_ids=case_ids, catalog=catalog)
        return {"passed": 1, "total": 1}
    monkeypatch.setattr(ce, "run_cases", fake_run_cases)
    assert ce.main(["--workflow-id", "W", "--case", "TRF-X", "--customer", "script", "--mock", "https://m",
                    "--cases-file", str(cf)]) == 0
    assert seen["mock_url"] == "https://m" and seen["first"] == "Alo?" and "TRF-X" in seen["cases"]
    assert seen["catalog"] is None
    assert ce.main(["--workflow-id", "W", "--case", "NOPE", "--mock", "https://m", "--cases-file", str(cf)]) == 2
    with pytest.raises(SystemExit):
        ce.main(["--workflow-id", "W", "--case", "TRF-X", "--mock", "https://m"])
    seen.clear()
    assert ce.main(["--workflow-id", "W", "--case", "PUB-01", "--first", "Hi", "--tools", ""]) == 0
    assert seen["first"] == "Hi"


def test_run_cases_takes_the_case_lines(env, monkeypatch):
    got = {}

    def fake_run_case(wf, case, customer, script, *a, **kw):
        got.update(case=case, script=script, **kw)
        return {"score": {"pass": True, "failed": []}, "lints": [], "errors": [], "turns": 2, "ledger": {"calls": []}}
    monkeypatch.setattr(ce, "run_case", fake_run_case)
    s = ce.run_cases("W", ["TRF-X"], "script", None, cases={"TRF-X": MOCK_CASE}, mock_url="https://m",
                     printer=lambda *_: None)
    assert s["passed"] == 1 and got["script"] == MOCK_CASE["customer_lines"] and got["mock_url"] == "https://m"
