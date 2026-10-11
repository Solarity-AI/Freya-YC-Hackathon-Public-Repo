"""Fix round 2 (2026-10-11): chat_e2e must never take an older reply for a turn the platform rejected (live PUB-09:
HTTP 503 "API key validation is temporarily unavailable" on turn 2, and the turn-1 opening was recovered as the
answer to it). A turn that is provably not stored is re-sent once; a stored turn is never re-sent."""
import json

import pytest

from harness import chat_e2e as ce
from test_chat_e2e import FakeNet, env  # noqa: F401  (fixture)

REJECT = (503, {"success": False, "data": {"message": "API key validation is temporarily unavailable.",
                                           "result": None}})


class RejectingNet(FakeNet):
    """FakeNet whose listed chat turns are rejected BEFORE the platform stores them (no user message is kept)."""

    def __init__(self, replies, reject_calls, close_after=None):
        super().__init__(replies, close_after)
        self.reject_calls = set(reject_calls)
        self.chat_calls = 0

    def __call__(self, method, url, body=None, headers=None, timeout=45):
        if url.endswith("/api/v2/chat/message"):
            self.chat_calls += 1
            if self.chat_calls in self.reject_calls:
                self.calls.append({"method": method, "url": url, "body": body})
                return REJECT
        return super().__call__(method, url, body, headers, timeout)


def _run(net, monkeypatch, public_cases, script):
    monkeypatch.setattr(ce, "_request", net)
    monkeypatch.setattr(ce, "RECOVER_MAX_S", 8.0)
    return ce.run_case("wf1", public_cases["PUB-03"], customer="script", script=script, gap_s=0)


def test_rejected_turn_is_resent_once_and_never_takes_the_older_reply(env, monkeypatch, public_cases):
    net = RejectingNet(["Am I speaking with Mr Park?", "Your date of birth?", "Goodbye."], reject_calls=[2])
    rep = _run(net, monkeypatch, public_cases, ["Yes, speaking.", "12 July 1991"])
    agent = [t for r, t in rep["transcript"] if r == "agent"]
    assert agent == ["Am I speaking with Mr Park?", "Your date of birth?", "Goodbye."]
    assert any("re-sent once" in e for e in rep["errors"]) and any("HTTP 503" in e for e in rep["errors"])
    sent = [c["body"]["message"] for c in net.calls if c["url"].endswith("/chat/message")]
    assert sent == ["Hello?", "Yes, speaking.", "Yes, speaking.", "12 July 1991"]


@pytest.mark.parametrize("rejects", [[2, 3], [3, 4]])
def test_a_turn_rejected_twice_stops_the_case_without_a_stale_reply(env, monkeypatch, public_cases, rejects):
    net = RejectingNet(["Am I speaking with Mr Park?", "Your date of birth?", "x", "y"], reject_calls=rejects,
                       close_after=99)
    rep = _run(net, monkeypatch, public_cases, ["Yes, speaking.", "12 July 1991", "z"])
    agent = [t for r, t in rep["transcript"] if r == "agent"]
    assert len(set(agent)) == len(agent)                    # no reply was taken twice
    assert rep["errors"][-1].endswith("no reply recovered; case stopped")
    assert sum("re-sent once" in e for e in rep["errors"]) == 1
    assert rep["call_id"] == "call1"


def test_a_stored_turn_without_a_reply_is_never_resent(env, monkeypatch, public_cases):
    net = FakeNet(["Am I speaking with Mr Park?", (0, "TimeoutError: timed out")], close_after=99)
    rep = _run(net, monkeypatch, public_cases, ["Yes, speaking."])
    sent = [c["body"]["message"] for c in net.calls if c["url"].endswith("/chat/message")]
    assert sent == ["Hello?", "Yes, speaking."]
    assert not any("re-sent" in e for e in rep["errors"])
    assert rep["errors"][-1].endswith("no reply recovered; case stopped")


def test_reply_after_last_user_checks_the_sent_message():
    msgs = [{"role": "user", "message": "Hello?"}, {"role": "assistant", "message": "Opening."}]
    assert ce._reply_after_last_user(msgs) == "Opening."
    assert ce._reply_after_last_user(msgs, sent="Hello?") == "Opening."
    assert ce._reply_after_last_user(msgs, sent="  hello? ") == "Opening."        # whitespace and case
    assert ce._reply_after_last_user(msgs, sent="Yes, speaking.") is None
    assert ce._reply_after_last_user([{"role": "assistant", "message": "Hi"}], sent="Hello?") is None


def test_turn_stored_states(env, monkeypatch):
    def net(msgs, status=200):
        return lambda m, u, b=None, h=None, t=45: (status, {"data": {"result": {"call": {"messages": msgs}}}})
    monkeypatch.setattr(ce, "_request", net([{"role": "user", "message": "A"}, {"role": "user", "message": "B"}]))
    assert ce._turn_stored("c1", "b") is True
    assert ce._turn_stored("c1", "A") is False
    monkeypatch.setattr(ce, "_request", net([]))
    assert ce._turn_stored("c1", "A") is False
    monkeypatch.setattr(ce, "_request", net([], status=503))
    assert ce._turn_stored("c1", "A") is None


def test_unreadable_call_after_a_rejection_is_not_resent(env, monkeypatch, public_cases):
    net = RejectingNet(["Am I speaking with Mr Park?", "never"], reject_calls=[2], close_after=99)
    orig = net.__call__

    def broken_get(method, url, body=None, headers=None, timeout=45):
        if "/api/v2/call/" in url:
            return 503, "down"
        return orig(method, url, body, headers, timeout)
    monkeypatch.setattr(ce, "RECOVER_MAX_S", 8.0)
    monkeypatch.setattr(ce, "_request", broken_get)
    rep = ce.run_case("wf1", public_cases["PUB-03"], customer="script", script=["Yes."], gap_s=0)
    assert not any("re-sent" in e for e in rep["errors"])
    assert json.dumps(rep["transcript"]).count("Am I speaking with Mr Park?") == 1
