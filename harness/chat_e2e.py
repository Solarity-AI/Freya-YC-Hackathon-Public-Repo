"""Live chat end-to-end runner on bank practice sessions (docs/CONTRACTS.md E.4). Owner: agent 4.

python -m harness.chat_e2e --workflow-id W --case PUB-01 [--case PUB-02,...] [--customer persona|script]
                           [--script f.json] [--style pieces] [--max-turns 30] [--out results/chat/<case>.json]
                           [--spec spec.json (banned-word lint)] [--model claude-haiku-4-5]
Sequential only. Never starts simulations. Credentials from the environment (kit env.sh), never logged.

CONTRACT NOTE (choices where E.4 is silent; simplest reading):
- HTTP goes through `_request` (urllib) with the kit's base URL, bearer header and browser-like User-Agent built from
  the environment at call time, instead of `freya.api`, because `freya.api` has a fixed 120 s timeout and E.4
  wants 45 s per turn. Same routes, same envelope ({data: {result}}).
- Transport errors (timeout, 5xx, 504) are not re-sent blindly (a re-send could run the turn twice): the runner polls
  the call (GET /api/v2/call/{id}) every 4 s for up to 60 s and takes the assistant messages after THIS turn's user
  message as the reply. Only when the stored call still does not hold this turn's user message after that window
  (the platform rejected it, e.g. HTTP 503 "API key validation is temporarily unavailable") is the turn re-sent,
  once. Otherwise (or with no call id yet) the case stops with a transport error.
- Live chat is sequential across every process of the workspace: run_cases and the build's smoke turn hold
  state/chat.lock (an exclusive file lock) while a call is live.
- The persona's script list (--script) holds the customer turns AFTER the fixed first turn "Hello?". A JSON file
  holds either a list (all cases) or {case_id: list}.
- Stop: after an empty agent reply or one containing a goodbye word, the ledger is read; the case stops when its
  last call is close_call. Otherwise at --max-turns or when the script runs out. /chat/end runs in `finally`.
- Reports: results/chat/<case>-<UTC stamp>.json per case (or --out for a single case) and
  results/chat/summary-<UTC stamp>.json for the run.
"""
import argparse
import contextlib
import datetime
import fcntl
import json
import os
import pathlib
import socket
import sys
import time
import urllib.error
import urllib.request

from builder.paths import ROOT, bank_host
from harness import persona as hpersona
from harness import score as hscore
from harness.scenarios import public_case

FREYA_UA = "Mozilla/5.0 (build-the-builder)"
BANK_UA = "freya-bank-scorer/0.1"
JSON_CT = "application/json"
USER_AGENT = FREYA_UA                                   # default for any request without one (not Python-urllib)
TURN_TIMEOUT_S = 45
GAP_S = 1.0
RESULTS = ROOT / "results" / "chat"
LOCK_PATH = ROOT / "state" / "chat.lock"
RECOVER_POLL_S = 4.0
RECOVER_MAX_S = 60.0


class ChatError(Exception):
    pass


class ChatTransportError(ChatError):
    def __init__(self, msg, code=0, call_id=None):
        super().__init__(msg)
        self.code, self.call_id = code, call_id


def _request(method, url, body=None, headers=None, timeout=TURN_TIMEOUT_S):
    """-> (status, parsed JSON or text). Network failures -> (0, error text)."""
    data = json.dumps(body).encode() if body is not None else None
    hdrs = dict(headers or {})
    if not any(k.lower() == "user-agent" for k in hdrs):
        hdrs["User-Agent"] = USER_AGENT                 # Cloudflare answers 403 / error 1010 to Python-urllib
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw, status = r.read().decode("utf-8", "replace"), r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode("utf-8", "replace"), e.code
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
        return 0, "%s: %s" % (type(e).__name__, e)
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


def _need(name):
    v = os.environ.get(name)
    if not v:
        raise ChatError("environment variable %s is not set (source the kit env.sh)" % name)
    return v


def _freya_url(path):
    return os.environ.get("FREYA_API_URL", "https://staging-app.freyavoice.ai").rstrip("/") + path


def _freya_headers():
    return {"Authorization": "Bearer " + _need("FREYA_API_KEY"), "Content-Type": JSON_CT,
            "User-Agent": FREYA_UA}


def _bank_headers():
    return {"x-team-key": _need("FREYA_BANK_TEAM_KEY"), "content-type": JSON_CT, "user-agent": BANK_UA}


def _result(out):
    if isinstance(out, dict):
        d = out.get("data")
        if isinstance(d, dict) and "result" in d:
            return d["result"]
    return out


def create_session(case_id):
    """POST {bank}/v1/practice/sessions {"case": id} with x-team-key -> variables dict."""
    status, out = _request("POST", bank_host() + "/v1/practice/sessions", {"case": case_id}, _bank_headers(), 20)
    if status != 200 or not isinstance(out, dict) or not isinstance(out.get("variables"), dict):
        raise ChatError("practice session for %s failed: HTTP %s %s" % (case_id, status, str(out)[:200]))
    return out["variables"]


def chat_turn(workflow_id, message, variables, call_id=None, timeout_s=TURN_TIMEOUT_S):
    """POST /api/v2/chat/message -> (response_text, call_id)."""
    body = {"workflowId": workflow_id, "message": message, "customerVariables": variables}
    if call_id:
        body["callId"] = call_id
    status, out = _request("POST", _freya_url("/api/v2/chat/message"), body, _freya_headers(), timeout_s)
    if status != 200:
        raise ChatTransportError("chat turn HTTP %s: %s" % (status, str(out)[:300]), status, call_id)
    res = _result(out)
    if not isinstance(res, dict):
        raise ChatTransportError("chat turn: unexpected body %s" % str(out)[:200], status, call_id)
    return (res.get("response") or ""), (res.get("callId") or call_id)


def end_chat(call_id):
    if not call_id:
        return None
    status, out = _request("POST", _freya_url("/api/v2/chat/end"), {"callId": call_id}, _freya_headers(), 30)
    return {"status": status, "result": _result(out) if status == 200 else str(out)[:200]}


_WS = None


def workspace_id():
    global _WS
    if _WS:
        return _WS
    _WS = os.environ.get("FREYA_WORKSPACE_ID")
    if not _WS:
        status, out = _request("GET", _freya_url("/api/v2/workspaces"), None, _freya_headers(), 30)
        r = _result(out)
        items = (r.get("workspaces") or r.get("items")) if isinstance(r, dict) else r
        if status != 200 or not items:
            raise ChatError("cannot read the workspace id: HTTP %s" % status)
        _WS = items[0]["id"]
    return _WS


def get_call(call_id):
    status, out = _request("GET", _freya_url("/api/v2/call/%s?workspaceId=%s" % (call_id, workspace_id())), None,
                           _freya_headers(), 30)
    if status != 200:
        raise ChatError("get call HTTP %s" % status)
    r = _result(out)
    return r.get("call", r) if isinstance(r, dict) else {}


def get_ledger(customer_id):
    status, out = _request("GET", bank_host() + "/v1/practice/ledger/" + customer_id, None, _bank_headers(), 20)
    if status != 200 or not isinstance(out, dict):
        raise ChatError("ledger HTTP %s: %s" % (status, str(out)[:200]))
    return out


def _closed(ledger):
    if isinstance((ledger or {}).get("closed"), bool):                    # our mock (mock/src/engine.js)
        return ledger["closed"]
    calls = (ledger or {}).get("calls") or []
    return bool(calls) and calls[-1].get("tool") == "close_call"


# ----------------------------------------------------------------------------------------------- our own mock
# The final: the agent calls OUR Cloudflare mock (mock/), not the kit's practice bank. A case then comes from a
# cases file (testbed/<case>/cases.json shape: id, variables, customer_lines, expected_ledger [{op, body}]);
# the session is a POST <mock>/reset/<customer> and the ledger GET <mock>/ledger/<customer>.

def mock_session(mock_url, case):
    """Reset the customer's ledger on the mock -> the call variables of the case."""
    variables = dict(case.get("variables") or {})
    cid = case.get("mock_customer") or variables.get("customer_id") or ""
    status, out = _request("POST", mock_url.rstrip("/") + "/reset/" + cid, {}, {"content-type": JSON_CT,
                                                                          "user-agent": FREYA_UA}, 20)
    if status != 200:
        raise ChatError("mock reset for %s failed: HTTP %s %s" % (cid, status, str(out)[:200]))
    return variables, cid


def mock_ledger(mock_url, customer_id):
    status, out = _request("GET", mock_url.rstrip("/") + "/ledger/" + customer_id, None, {"user-agent": FREYA_UA},
                           20)
    if status != 200 or not isinstance(out, dict):
        raise ChatError("mock ledger HTTP %s: %s" % (status, str(out)[:200]))
    return out


def _same(want, got):
    if isinstance(want, (int, float)) and not isinstance(want, bool):
        try:
            return abs(float(got) - float(want)) < 0.005
        except (TypeError, ValueError):
            return False
    return str(want) == str(got)


def score_mock(case, ledger):
    """Every expected {op, body} has a successful call of that operation whose args carry those values (free text
    fields such as a note's description are only checked for presence). -> {"pass", "failed"}."""
    calls = [c for c in (ledger or {}).get("calls") or [] if int(c.get("status") or 0) < 300
             and next(iter((c.get("result") or {}).values()), True) is not False]
    failed = []
    for exp in case.get("expected_ledger") or []:
        mine = [c for c in calls if c.get("tool") == exp.get("op")]
        if not mine:
            failed.append("missing call %s" % exp.get("op"))
            continue
        body = exp.get("body") or {}

        def misses(c, body=body):
            args = c.get("args") or {}
            return ["%s.%s want %r got %r" % (exp["op"], k, v, args.get(k)) for k, v in body.items()
                    if not (k in args if isinstance(v, str) and len(v) > 40 else _same(v, args.get(k)))]
        failed += min((misses(c) for c in mine), key=len)
    want_ops = [e.get("op") for e in case.get("expected_ledger") or []]
    for op in sorted({c.get("tool") for c in calls}):
        n_got, n_want = sum(c.get("tool") == op for c in calls), want_ops.count(op)
        if n_want and n_got > n_want:
            failed.append("%s recorded %d times (want %d)" % (op, n_got, n_want))
    return {"pass": not failed, "failed": failed}


def load_cases_file(path):
    data = json.loads(pathlib.Path(path).read_text())
    rows = data if isinstance(data, list) else data.get("cases") or []
    return {c["id"]: c for c in rows}


def _norm(text):
    return " ".join((text or "").split()).lower()


def _reply_after_last_user(msgs, sent=None):
    """Assistant messages after the last user message. With `sent`, that user message must be the one this turn
    sent; otherwise the turn is not stored (yet) and the older reply must not be taken for it -> None."""
    users = [i for i, m in enumerate(msgs) if m.get("role") == "user"]
    last_user = max(users or [-1])
    if sent is not None and (last_user < 0 or _norm(msgs[last_user].get("message")) != _norm(sent)):
        return None
    texts = [m.get("message") or "" for m in msgs[last_user + 1:] if m.get("role") == "assistant"]
    return " ".join(t for t in texts if t) if texts else None


def _turn_stored(call_id, sent):
    """True when the call's last user message is `sent` (the platform took the turn), False when it is not, None
    when the call cannot be read."""
    try:
        msgs = get_call(call_id).get("messages") or []
    except ChatError:
        return None
    users = [m for m in msgs if m.get("role") == "user"]
    return bool(users) and _norm(users[-1].get("message")) == _norm(sent)


def _recover_reply(call_id, poll_s=None, max_s=None, sleep=None, sent=None):
    """Assistant messages after the last user message of the stored call, polled every poll_s seconds for up to
    max_s (a slow platform stores the turn late); None when nothing comes. The turn is never re-sent here.
    With `sent`, only a reply to that user message counts (a rejected turn must not take the previous reply)."""
    poll_s = RECOVER_POLL_S if poll_s is None else poll_s
    max_s = RECOVER_MAX_S if max_s is None else max_s
    sleep = sleep or time.sleep
    waited = 0.0
    while waited < max_s:
        sleep(poll_s)
        waited += poll_s
        try:
            reply = _reply_after_last_user(get_call(call_id).get("messages") or [], sent)
        except ChatError:
            continue
        if reply is not None:
            return reply
    return None


def _send_turn(workflow_id, msg, variables, call_id, timeout_s, errors, n):
    """One customer turn -> (reply or None, call_id). A transport error is recovered from the stored call. When the
    platform never stored the turn (e.g. HTTP 503 before processing) it is re-sent ONCE: it cannot run twice."""
    for attempt in (1, 2):
        try:
            return chat_turn(workflow_id, msg, variables, call_id, timeout_s)
        except ChatTransportError as e:
            errors.append("turn %d: %s" % (n, e))
            call_id = call_id or e.call_id
            if not call_id:
                return None, None
            reply = _recover_reply(call_id, sent=msg)
            if reply is not None:
                return reply, call_id
            if attempt == 1 and _turn_stored(call_id, msg) is False:
                errors.append("turn %d: not stored by the platform; re-sent once" % n)
                continue
            return None, call_id
    return None, call_id                                # pragma: no cover (the loop always returns)


@contextlib.contextmanager
def chat_lock(wait_s=None, path=None):
    """Exclusive workspace-wide lock for live chat (one live call at a time across agents and builds).
    wait_s=None waits as long as needed; otherwise ChatError after wait_s seconds."""
    p = pathlib.Path(path or LOCK_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a+") as fh:
        t0 = time.time()
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if wait_s is not None and time.time() - t0 >= wait_s:
                    raise ChatError("another live chat holds %s" % p) from None
                time.sleep(1.0)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def run_case(workflow_id, case, customer="persona", script=None, style=None, max_turns=30, spec=None,
             catalog=None, persona_fn=None, timeout_s=TURN_TIMEOUT_S, gap_s=GAP_S, out=None, mock_url=None,
             first="Hello?"):
    """-> {"case", "call_id", "transcript", "nodes", "ledger", "score": {"pass", "failed"}, "lints": [...]}.
    mock_url: the case is a cases-file dict, its customer lives on our mock (reset + ledger there)."""
    if isinstance(case, str):
        case = public_case(case)
    if mock_url:
        ledger_of = lambda cid: mock_ledger(mock_url, cid)                              # noqa: E731
    else:
        ledger_of = get_ledger
    t_start = time.time()
    report = {"case": case["id"], "workflow_id": workflow_id, "customer": customer, "style": style,
              "call_id": None, "customer_id": None, "transcript": [], "nodes": [], "ledger": None,
              "score": {"pass": False, "failed": []}, "lints": [], "errors": [], "turns": 0,
              "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    transcript = report["transcript"]
    call_id = None
    try:
        if mock_url:
            variables, report["customer_id"] = mock_session(mock_url, case)
        else:
            variables = create_session(case["id"])
            report["customer_id"] = variables.get("customer_id")
        if customer == "persona":
            ptext = hpersona.persona_prompt(case, style)
            persona_fn = persona_fn or (lambda tr: hpersona.next_utterance(ptext, tr))
        else:
            queue = list(script or [])
            persona_fn = persona_fn or (lambda tr: queue.pop(0) if queue else None)
        msg, last = first, 0.0
        for n in range(1, max_turns + 1):
            wait = gap_s - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
            last = time.time()
            transcript.append(("customer", msg))
            report["turns"] = n
            reply, call_id = _send_turn(workflow_id, msg, variables, call_id, timeout_s, report["errors"], n)
            report["call_id"] = call_id
            if reply is None:
                report["errors"].append("turn %d: no reply recovered; case stopped" % n)
                break
            report["call_id"] = call_id
            transcript.append(("agent", reply))
            if not reply.strip() or hscore.GOODBYE_RE.search(reply):
                try:
                    if _closed(ledger_of(report["customer_id"])):
                        break
                except ChatError as e:
                    report["errors"].append("ledger: %s" % e)
            try:
                msg = persona_fn(list(transcript))
            except hpersona.PersonaError as e:
                report["errors"].append("persona: %s" % e)
                break
            if not msg:
                break
    except ChatError as e:
        report["errors"].append(str(e))
    finally:
        if call_id:
            try:
                end_chat(call_id)
            except Exception as e:                            # noqa: BLE001
                report["errors"].append("chat end: %s" % e)
    messages = []
    if call_id:
        try:
            messages = get_call(call_id).get("messages") or []
        except ChatError as e:
            report["errors"].append("get call: %s" % e)
    report["messages"] = messages
    report["nodes"] = hscore.node_path(messages)
    if report["customer_id"]:
        try:
            report["ledger"] = ledger_of(report["customer_id"])
        except ChatError as e:
            report["errors"].append(str(e))
    if report["ledger"] is not None:
        report["score"] = (score_mock if mock_url else hscore.score_ledger)(case, report["ledger"])
    else:
        report["score"] = {"pass": False, "failed": ["no ledger"]}
    banned = ((spec or {}).get("banned") or {}).get("before_verification")
    report["lints"] = hscore.lint_messages(messages, banned, catalog)
    report["seconds"] = round(time.time() - t_start, 1)
    _save(report, out)
    return report


def _stamp():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _save(obj, out=None, name=None):
    path = pathlib.Path(out) if out else RESULTS / (name or "%s-%s.json" % (obj.get("case", "run"), _stamp()))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, default=str))
    obj["_saved"] = str(path)
    return path


def run_cases(workflow_id, case_ids, customer="persona", scripts=None, style=None, max_turns=30, spec=None,
              out=None, printer=print, catalog=None, mock_url=None, cases=None, first="Hello?"):
    """Sequential (and serialised with every other live chat through chat_lock). -> summary dict (also saved).
    mock_url + cases ({id: case} from a cases file): customers on our mock; a scripted customer without --script
    says the case's own customer_lines."""
    rows = []
    for cid in case_ids:
        script = (scripts or {}).get(cid) if isinstance(scripts, dict) else scripts
        case = (cases or {}).get(cid, cid)
        if script is None and isinstance(case, dict):
            script = case.get("customer_lines")
        with chat_lock():
            rep = run_case(workflow_id, case, customer, script, style, max_turns, spec, catalog=catalog,
                           out=out if (out and len(case_ids) == 1) else None, mock_url=mock_url, first=first)
        tools = [c.get("tool") for c in ((rep.get("ledger") or {}).get("calls") or [])]
        rows.append({"case": cid, "pass": bool(rep["score"]["pass"]) and not rep["lints"],
                     "ledger_pass": bool(rep["score"]["pass"]), "turns": rep["turns"], "tools": tools,
                     "failed": rep["score"]["failed"] + rep["lints"] + rep["errors"], "report": rep.get("_saved")})
        printer(format_row(rows[-1]))
    summary = {"workflow_id": workflow_id, "style": style, "customer": customer,
               "passed": sum(r["pass"] for r in rows), "total": len(rows), "rows": rows}
    _save(summary, None, "summary-%s.json" % _stamp())
    printer("%d / %d passed (ledger + transcript lints)" % (summary["passed"], summary["total"]))
    return summary


def format_row(r):
    chain = " > ".join(t.replace("verify_identity", "verify").replace("create_promise", "promise")
                       for t in r["tools"]) or "(no tool calls)"
    lines = ["%s %-7s turns=%-3d | %s" % ("PASS" if r["pass"] else "FAIL", r["case"], r["turns"], chain)]
    lines += ["       - " + str(f)[:240] for f in r["failed"]]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m harness.chat_e2e")
    ap.add_argument("--workflow-id", required=True)
    ap.add_argument("--case", action="append", required=True, help="case id; repeat or comma-separate")
    ap.add_argument("--customer", choices=["persona", "script"], default="persona")
    ap.add_argument("--script")
    ap.add_argument("--style", choices=["pieces", "corrects", "talkative", "asks_back", "in_words"])
    ap.add_argument("--max-turns", type=int, default=30)
    ap.add_argument("--out")
    ap.add_argument("--spec")
    ap.add_argument("--model")
    ap.add_argument("--tools", default=str(ROOT / "kit" / "tools" / "openapi.json"),
                    help="tool API (OpenAPI) for the transcript lint's verification point")
    ap.add_argument("--mock", help="our mock's URL: customers, reset and ledger live there (the final)")
    ap.add_argument("--cases-file", help="cases JSON (testbed/tr-final/cases.json shape); needs --mock")
    ap.add_argument("--first", default=None, help="the customer's first line (default Hello?, with --mock Alo?)")
    a = ap.parse_args(argv)
    if bool(a.mock) != bool(a.cases_file):
        ap.error("--mock and --cases-file go together")
    if a.model:
        os.environ["HARNESS_PERSONA_MODEL"] = a.model
    cases = [c.strip() for x in a.case for c in x.split(",") if c.strip()]
    scripts = json.loads(pathlib.Path(a.script).read_text()) if a.script else None
    if a.customer == "script" and scripts is None and not a.cases_file:
        ap.error("--customer script needs --script")
    spec = json.loads(pathlib.Path(a.spec).read_text()) if a.spec else None
    try:
        table = load_cases_file(a.cases_file) if a.cases_file else None
        for cid in cases:
            try:
                table[cid] if table is not None else public_case(cid)
            except KeyError:
                raise ChatError("unknown case %s" % cid) from None
        catalog = None
        if a.tools and pathlib.Path(a.tools).exists() and not a.mock:
            from builder import openapi_model
            catalog = openapi_model.load(a.tools)
        extra = {}
        if a.mock:
            extra = {"mock_url": a.mock, "cases": table, "first": a.first or "Alo?"}
        elif a.first:
            extra = {"first": a.first}
        summary = run_cases(a.workflow_id, cases, a.customer, scripts, a.style, a.max_turns, spec, a.out,
                            catalog=catalog, **extra)
    except ChatError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
