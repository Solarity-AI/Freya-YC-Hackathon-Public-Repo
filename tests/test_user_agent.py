"""Every urllib request to a mock URL sends a browser-like User-Agent: Cloudflare answers the default
"Python-urllib/x" with 403 / error 1010."""
import io
import json
import urllib.request

import pytest

from builder import ingest
from harness import chat_e2e
from tools.mockgen import smoke


class _Resp(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def seen(monkeypatch):
    got = []

    def fake(req, timeout=None):
        got.append(req)
        return _Resp(json.dumps({"ok": True}).encode())
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return got


def _ua(req):
    return req.get_header("User-agent") or ""


def _browser_like(ua):
    return ua.startswith("Mozilla/5.0") and "python" not in ua.lower()


def test_fetch_json_sends_browser_user_agent(seen):
    assert ingest.fetch_json("https://mock.example.invalid/openapi.json") == {"ok": True}
    assert _browser_like(_ua(seen[0]))


def test_smoke_http_sends_browser_user_agent(seen):
    status, _ = smoke.http("https://mock.example.invalid", "GET", "/health")
    assert status == 200 and _browser_like(_ua(seen[0]))


def test_chat_e2e_request_defaults_user_agent(seen):
    chat_e2e._request("GET", "https://mock.example.invalid/health")
    assert _browser_like(_ua(seen[0]))


def test_chat_e2e_request_keeps_given_user_agent(seen):
    chat_e2e._request("GET", "https://mock.example.invalid/health", None, {"user-agent": "x/1"})
    assert _ua(seen[0]) == "x/1"


def test_submit_fetch_json_sends_browser_user_agent(seen):
    from tools import submit
    assert submit._fetch_json("https://mock.example.invalid/health") == {"ok": True}
    assert _browser_like(_ua(seen[0]))
