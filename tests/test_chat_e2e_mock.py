"""harness/chat_e2e mock mode (the final): customers, reset and ledger on OUR mock, cases from a cases file, the
scripted customer says the case's customer_lines, the score compares the mock ledger with expected_ledger."""
import json

import pytest

from harness import chat_e2e as ce

CASE = {"id": "TRX-01", "mock_customer": "C-1",
        "variables": {"musteri_no": "C-1", "ad": "Ayşe", "now": "2026-10-21T10:30"},
        "customer_lines": ["Evet, benim.", "Tamam."],
        "expected_ledger": [
            {"op": "SaveP", "body": {"musteri_no": "C-1", "tutar": 8450.75, "tarih": "2026-10-21", "tip": "TAM"}},
            {"op": "Close", "body": {"musteri_no": "C-1", "sonuc": "OK"}}]}


def _call(tool, args, status=200, result=None):
    return {"tool": tool, "args": args, "status": status, "result": result if result is not None else {"ok": True}}


GOOD = {"closed": True, "calls": [
    _call("Verify", {"musteri_no": "C-1"}),
    _call("SaveP", {"musteri_no": "C-1", "tutar": "8450.75", "tarih": "2026-10-21", "tip": "TAM"}),
    _call("Close", {"musteri_no": "C-1", "sonuc": "OK"})]}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("FREYA_API_KEY", "test-not-a-key")
    monkeypatch.setenv("FREYA_WORKSPACE_ID", "ws1")
    monkeypatch.setenv("FREYA_API_URL", "https://freya.example/")
    monkeypatch.setattr(ce, "RESULTS", tmp_path / "chat")
    monkeypatch.setattr(ce, "LOCK_PATH", tmp_path / "chat.lock")
    monkeypatch.setattr(ce.time, "sleep", lambda s: None)
    return tmp_path


class TestScore:
    def test_pass(self):
        assert ce.score_mock(CASE, GOOD) == {"pass": True, "failed": []}

    def test_wrong_value_and_missing_call(self):
        led = {"calls": [_call("SaveP", {"musteri_no": "C-1", "tutar": 100, "tarih": "2026-10-21", "tip": "TAM"})]}
        got = ce.score_mock(CASE, led)
        assert not got["pass"]
        assert "missing call Close" in got["failed"]
        assert any("SaveP.tutar want 8450.75 got 100" in f for f in got["failed"])

    def test_failed_calls_do_not_count(self):
        led = {"calls": [_call("SaveP", GOOD["calls"][1]["args"], result={"ok": False}),
                         _call("SaveP", GOOD["calls"][1]["args"], status=500), GOOD["calls"][2]]}
        assert "missing call SaveP" in ce.score_mock(CASE, led)["failed"]

    def test_recorded_twice(self):
        led = {"calls": GOOD["calls"] + [GOOD["calls"][1]]}
        assert ce.score_mock(CASE, led)["failed"] == ["SaveP recorded 2 times (want 1)"]

    def test_long_text_only_needs_presence(self):
        case = {"expected_ledger": [{"op": "Note", "body": {"aciklama": "x" * 60}}]}
        assert ce.score_mock(case, {"calls": [_call("Note", {"aciklama": "something else"})]})["pass"]
        assert not ce.score_mock(case, {"calls": [_call("Note", {})]})["pass"]

    def test_same(self):
        assert ce._same(1.0, "1.00") and not ce._same(1.0, "abc") and ce._same("A", "A")

    def test_closed_reads_the_mock_flag(self):
        assert ce._closed({"closed": True, "calls": []}) is True
        assert ce._closed({"closed": False, "calls": [{"tool": "close_call"}]}) is False
        assert ce._closed({"calls": [{"tool": "close_call"}]}) is True


class Net:
    def __init__(self, replies, ledger=GOOD, reset=200):
        self.replies, self.ledger, self.reset, self.calls = list(replies), ledger, reset, []

    def __call__(self, method, url, body=None, headers=None, timeout=45):
        self.calls.append((method, url, body))
        if "/reset/" in url:
            return self.reset, {"ok": self.reset == 200}
        if "/ledger/" in url:
            return 200, self.ledger
        if "/chat/message" in url:
            return 200, {"data": {"result": {"response": self.replies.pop(0) if self.replies else "",
                                             "callId": "call-1"}}}
        if "/chat/end" in url:
            return 200, {"data": {"result": {"ok": True}}}
        if "/api/v2/call/" in url:
            return 200, {"data": {"result": {"call": {"messages": []}}}}
        return 404, {}


class TestRun:
    def test_run_case_on_the_mock(self, env, monkeypatch):
        net = Net(["Merhaba.", "Görüşmek üzere, iyi günler."])
        monkeypatch.setattr(ce, "_request", net)
        rep = ce.run_case("W", CASE, "script", CASE["customer_lines"], mock_url="https://m.example/",
                          first="Alo?", gap_s=0)
        assert rep["score"]["pass"], rep
        assert rep["customer_id"] == "C-1"
        assert rep["transcript"][0] == ("customer", "Alo?")
        assert net.calls[0][:2] == ("POST", "https://m.example/reset/C-1")
        chat = [c for c in net.calls if "/chat/message" in c[1]]
        assert chat[0][2]["customerVariables"]["musteri_no"] == "C-1"

    def test_reset_failure_is_reported(self, env, monkeypatch):
        monkeypatch.setattr(ce, "_request", Net([], reset=500))
        rep = ce.run_case("W", CASE, "script", [], mock_url="https://m.example", gap_s=0)
        assert any("mock reset for C-1 failed" in e for e in rep["errors"])

    def test_ledger_failure(self, env, monkeypatch):
        net = Net(["Merhaba."])
        net.ledger = "not json"
        monkeypatch.setattr(ce, "_request", net)
        rep = ce.run_case("W", CASE, "script", [], mock_url="https://m.example", gap_s=0)
        assert rep["score"] == {"pass": False, "failed": ["no ledger"]}

    def test_main_with_cases_file(self, env, monkeypatch, tmp_path):
        f = tmp_path / "cases.json"
        f.write_text(json.dumps([CASE]))
        monkeypatch.setattr(ce, "_request", Net(["Merhaba.", "İyi günler."]))
        out = tmp_path / "r.json"
        assert ce.main(["--workflow-id", "W", "--case", "TRX-01", "--customer", "script", "--mock",
                        "https://m.example", "--cases-file", str(f), "--out", str(out)]) == 0
        assert json.loads(out.read_text())["transcript"][0] == ["customer", "Alo?"]
        assert ce.main(["--workflow-id", "W", "--case", "NOPE", "--mock", "https://m.example",
                        "--cases-file", str(f)]) == 2

    def test_main_flag_pairing(self, env):
        with pytest.raises(SystemExit):
            ce.main(["--workflow-id", "W", "--case", "X", "--mock", "https://m.example"])

    def test_main_first_without_mock(self, env, monkeypatch):
        seen = {}

        def fake(*a, catalog=None, **kw):
            seen.update(kw)
            return {"passed": 1, "total": 1}
        monkeypatch.setattr(ce, "run_cases", fake)
        assert ce.main(["--workflow-id", "W", "--case", "PUB-01", "--first", "Hi"]) == 0
        assert seen == {"first": "Hi"}

    def test_load_cases_file_dict_form(self, tmp_path):
        f = tmp_path / "c.json"
        f.write_text(json.dumps({"cases": [CASE]}))
        assert list(ce.load_cases_file(f)) == ["TRX-01"]
