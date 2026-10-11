"""Scoring adapter: kit `score.score_ledger` + generic transcript lints (twin events or live call messages).
Owner: agent 4. Generic: banned words and claim words come from the Spec / the caller, never from here.
"""
import json
import re

from builder.paths import import_kit

GOODBYE_RE = re.compile(r"\b(good\s?bye|bye)\b", re.I)


def score_ledger(case_or_expected, ledger):
    """Kit scorer. Accepts a full case (with `expected`) or a bare expected block."""
    case = case_or_expected if "expected" in case_or_expected else {"expected": case_or_expected}
    led = dict(ledger or {})
    for k in ("promises", "notes", "callbacks", "transfers", "calls"):
        led.setdefault(k, [])
    try:
        return import_kit("score").score_ledger(case, led)
    except Exception as e:                                    # noqa: BLE001 - a malformed ledger is a failure
        return {"pass": False, "failed": ["scorer crashed: %s: %s" % (type(e).__name__, e)]}


def banned_hits(text, banned):
    """Whole-word, case-insensitive hits of `banned` in text."""
    low = (text or "").lower()
    return [w for w in banned or [] if re.search(r"\b" + re.escape(w.lower()) + r"\b", low)]


def _ok_true(data, leaf):
    if not isinstance(data, dict):
        return False
    return str(data.get(leaf)).lower() == "true"


def lines_before_verified(events, catalog=None):
    """Agent lines spoken before identity was verified, from twin events.
    Verified = first verify result whose `all` leaf is true, or first successful account read."""
    all_leaf = acct_ok = None
    if catalog:
        t = catalog.get("tools") or {}
        all_leaf = ((t.get("verify_identity") or {}).get("roles") or {}).get("response", {}).get("all")
        acct_ok = ((t.get("get_account") or {}).get("roles") or {}).get("response", {}).get("s")
    out = []
    for ev in events:
        if ev.get("event") == "function_call_complete":
            data = (ev.get("result") or {}).get("data")
            if ev.get("function") == "verify_identity" and all_leaf and _ok_true(data, all_leaf):
                return out
            if ev.get("function") == "get_account" and _ok_true(data, acct_ok or "ok"):
                return out
        elif ev.get("event") == "say":
            out.append(ev.get("text", ""))
    return out


def lint_messages(messages, banned=None, catalog=None):
    """Live call messages (GET /api/v2/call) -> list of lint failures.
    - banned words in assistant lines before verification (needs `banned`)
    - more than one assistant message between two user messages
    """
    fails, verified, n_since_user = [], False, 0
    last_tool = None
    all_leaf = acct_ok = None
    if catalog:
        t = catalog.get("tools") or {}
        all_leaf = ((t.get("verify_identity") or {}).get("roles") or {}).get("response", {}).get("all")
        acct_ok = ((t.get("get_account") or {}).get("roles") or {}).get("response", {}).get("s")
    for m in messages or []:
        role = m.get("role")
        if role == "user":
            n_since_user = 0
        elif role == "assistant":
            n_since_user += 1
            if n_since_user == 2:
                fails.append("more than one assistant message after a customer turn: %r" % (m.get("message") or "")[:80])
            hits = [] if verified else banned_hits(m.get("message") or "", banned)
            if hits:
                fails.append("banned before verification %s in %r" % (hits, (m.get("message") or "")[:120]))
        elif role == "system":
            ev = parse_event(m)
            if ev.get("event") == "function_call_start":
                # LIVE: api nodes log function "api_call" with the tool URL in args.url (2026-10-11)
                url = str(((ev.get("args") or {}).get("url")) or "")
                last_tool = None
                for tn, td in ((catalog or {}).get("tools") or {}).items():
                    if url and (url == td.get("url") or (td.get("path") and url.endswith(td.get("path")))):
                        last_tool = tn
                if url and last_tool is None:
                    last_tool = url.rstrip("/").rsplit("/", 1)[-1]
            if ev.get("event") == "function_call_complete":
                fn = ev.get("function") or ev.get("name")
                if fn == "api_call" and last_tool:
                    fn = last_tool
                res = ev.get("result") or {}
                data = res.get("data") if isinstance(res, dict) else None
                if fn == "get_account" and _ok_true(data, acct_ok or "ok"):
                    verified = True
                if fn == "verify_identity" and all_leaf and _ok_true(data, all_leaf):
                    verified = True
    return fails


def parse_event(m):
    """A system message's JSON event (dict), or {}."""
    raw = m.get("message")
    if isinstance(raw, dict):
        return raw
    try:
        ev = json.loads(raw or "")
        return ev if isinstance(ev, dict) else {}
    except (TypeError, ValueError):
        return {}


def node_path(messages):
    """Node keys in node_enter order from live call messages."""
    out = []
    for m in messages or []:
        if m.get("role") == "system":
            ev = parse_event(m)
            if ev.get("event") == "node_enter":
                out.append(ev.get("node") or ev.get("node_id") or "")
    return out
