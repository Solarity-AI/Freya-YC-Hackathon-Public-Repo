"""The only LLM client of the builder: Claude Agent SDK, structured JSON output (docs/CONTRACTS.md F). Owner: agent 5.

claude_agent_sdk.query with ClaudeAgentOptions(system_prompt, output_format={"type": "json_schema", "schema": ...},
no tools, small max_turns, effort). Result from ResultMessage.structured_output (fallback: JSON parsed from the text),
validated with jsonschema. Timeouts from builder.budget; <= 2 repair retries when the budget allows; one MODEL trace
event per attempt. Never disables thinking. Never logs full prompts or any secret.

Testing: set_backend(fn) swaps the transport. fn(req: dict) -> dict | str | awaitable of those, where req has
purpose, system, prompt, schema, timeout_s, effort, model, attempt. The parsing / validation / repair loop is shared.
"""
import asyncio
import json
import os
import re
import time

from builder import trace

DEFAULT_MODEL = os.environ.get("BUILDER_MODEL", "claude-opus-5-5")
DEFAULT_EFFORT = os.environ.get("BUILDER_EFFORT", "high")
EFFORTS = ("low", "medium", "high", "max")
# measured 2026-10-11 (BUILD SPEED item 4): the intents facet F5 at medium took 57.7 s (brief A) and 64.0 s (A+B)
# instead of 85-103 s at high, with the golden core-leaf diff unchanged (naming only) and the twin ledgers passing;
# BUILDER_FACET_EFFORT overrides it.
DEFAULT_FACET_EFFORT = {"F5": "medium"}


def _pairs(env):
    """'F1=a,F3=b' -> {"F1": "a", "F3": "b"} (malformed items are ignored)."""
    out = {}
    for item in os.environ.get(env, "").split(","):
        k, _, v = item.partition("=")
        if k.strip() and v.strip():
            out[k.strip()] = v.strip()
    return out


def facet_overrides():
    """Per-call model / effort chosen by measurement (BUILD SPEED item 4), from the environment:
    BUILDER_FACET_MODEL='F3=claude-sonnet-5-5,...' and BUILDER_FACET_EFFORT='F1=medium,...'. Recorded in the trace."""
    eff = dict(DEFAULT_FACET_EFFORT)
    eff.update({k: v for k, v in _pairs("BUILDER_FACET_EFFORT").items() if v in EFFORTS})
    return {"model": _pairs("BUILDER_FACET_MODEL"), "effort": eff}


def choice(key, model=None, effort=None):
    """-> (model, effort) for a call key (facet id or 'critic'): explicit argument > per-key override > default."""
    ov = facet_overrides()
    return (model or ov["model"].get(key) or DEFAULT_MODEL), (effort or ov["effort"].get(key) or DEFAULT_EFFORT)
MAX_CONCURRENCY = 6
MAX_REPAIRS = 2              # extra attempts after the first one
MIN_RETRY_S = 20.0           # do not start a retry with less time than this
MAX_TURNS = 4                # structured output uses a synthetic tool call: 2 turns + room for one self-repair
_MOD = "builder.llm.call_json"   # trace module tag of every LLM call


class LLMError(Exception):
    pass


_backend = None


def set_backend(fn):
    """Install a transport (tests). None restores the Claude Agent SDK transport. Returns the previous one."""
    global _backend
    prev = _backend
    _backend = fn
    return prev


def uses_sdk():
    """True when calls go to the Claude Agent SDK (no test transport installed): the build's preflight then checks
    that the SDK is installed and has a login."""
    return _backend is None


# ----------------------------------------------------------------------------------------------- parsing

def _fenced_blocks(s):
    """The stripped bodies of the ```[json] ... ``` blocks of s, in order: a str.find scan with the same matches as the
    regex ```(?:json)?\\s*(.*?)``` (re.S), which backtracked quadratically on unclosed fences."""
    out, i = [], 0
    while True:
        a = s.find("```", i)
        if a < 0:
            return out
        b = a + 3
        if s.startswith("json", b):
            b += 4
        e = s.find("```", b)
        if e < 0:                       # no closing fence after this one, so none after any later opening either
            return out
        out.append(s[b:e].strip())
        i = e + 3


def parse_json_text(text):
    """Best-effort JSON object from model text: whole text, fenced block, then the outermost {...}. None if none."""
    if text is None:
        return None
    if isinstance(text, (dict, list)):
        return text
    s = str(text).strip()
    cands = [s]
    cands += _fenced_blocks(s)
    i, j = s.find("{"), s.rfind("}")
    if 0 <= i < j:
        cands.append(s[i:j + 1])
    for c in cands:
        try:
            v = json.loads(c)
            if isinstance(v, dict):
                return v
        except Exception:                               # noqa: BLE001
            continue
    return None


def schema_errors(obj, schema, limit=25):
    """-> list of 'pointer: message' strings (empty = valid)."""
    import jsonschema                                   # lazy: the build's preflight reports a missing package first
    try:
        v = jsonschema.Draft202012Validator(schema)
        errs = sorted(v.iter_errors(obj), key=lambda e: [str(p) for p in e.absolute_path])
    except Exception as e:                              # noqa: BLE001 - a broken schema is a caller bug
        return ["<schema>: %s" % e]
    out = []
    for e in errs[:limit]:
        ptr = "/" + "/".join(str(p) for p in e.absolute_path)
        msg = e.message
        if len(msg) > 300:
            msg = msg[:297] + "..."
        out.append("%s: %s" % (ptr, msg))
    return out


def _repair_prompt(prompt, raw, errors):
    shown = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
    if len(shown) > 60000:
        shown = shown[:60000] + " ...(truncated)"
    return (prompt + "\n\n---\nYOUR PREVIOUS ANSWER WAS REJECTED.\nValidation errors:\n- " + "\n- ".join(errors)
            + "\n\nPrevious answer:\n" + shown
            + "\n\nReturn the complete corrected JSON object (all keys, not only the fixed ones). JSON only.")


# ----------------------------------------------------------------------------------------------- transport

async def _sdk_backend(req):
    from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, AssistantMessage, query  # lazy import

    kwargs = dict(system_prompt=req["system"],
                  output_format={"type": "json_schema", "schema": req["schema"]},
                  tools=[], max_turns=MAX_TURNS, model=req["model"], effort=req["effort"],
                  setting_sources=[], strict_mcp_config=True)
    try:
        opts = ClaudeAgentOptions(skills=[], **kwargs)
    except TypeError:                                   # older SDK without `skills`
        opts = ClaudeAgentOptions(**kwargs)
    result, texts, usage, cost, model_used = None, [], {}, None, req["model"]
    async for m in query(prompt=req["prompt"], options=opts):
        if isinstance(m, AssistantMessage):
            model_used = getattr(m, "model", model_used) or model_used
            for b in getattr(m, "content", []) or []:
                t = getattr(b, "text", None)
                if t:
                    texts.append(t)
                inp = getattr(b, "input", None)
                if getattr(b, "name", "") == "StructuredOutput" and isinstance(inp, dict):
                    result = inp
        elif isinstance(m, ResultMessage):
            usage = m.usage or {}
            cost = m.total_cost_usd
            if m.is_error:
                raise LLMError("sdk result error: %s %s" % (m.subtype, (m.errors or [])[:2]))
            if m.structured_output is not None:
                result = m.structured_output
            elif result is None and m.result:
                texts.append(m.result)
    return {"data": result, "text": "\n".join(texts), "usage": usage, "cost": cost, "model": model_used}


def _norm_backend_out(out):
    if isinstance(out, dict) and "data" in out and set(out) <= {"data", "text", "usage", "cost", "model"}:
        return out
    if isinstance(out, str):
        return {"data": None, "text": out}
    return {"data": out, "text": ""}


async def _invoke(req):
    fn = _backend or _sdk_backend
    out = fn(req)
    if asyncio.iscoroutine(out) or isinstance(out, asyncio.Future):
        out = await out
    return _norm_backend_out(out)


def _usage_brief(u):
    if not isinstance(u, dict):
        return {}
    keys = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    return {k: u[k] for k in keys if k in u}


# ----------------------------------------------------------------------------------------------- API

async def acall_json(purpose, system, prompt, schema, *, timeout_s, effort=DEFAULT_EFFORT, model=None, budget=None,
                     validate=None):
    """Async structured call -> dict matching `schema`. Raises LLMError after retries.

    timeout_s: per-attempt cap. budget (optional builder.budget.Budget): each attempt gets
    budget.call_timeout(timeout_s) and no retry starts with less than MIN_RETRY_S.
    validate (optional): extra checker obj -> list of error strings (treated like schema errors, repaired)."""
    model = model or DEFAULT_MODEL
    cur_prompt = prompt
    last_err = "no attempt"
    for attempt in range(1 + MAX_REPAIRS):
        t_out = float(timeout_s) if budget is None else budget.call_timeout(timeout_s)
        if t_out <= 0 or (budget is not None and attempt > 0 and t_out < MIN_RETRY_S):
            trace.event("BUDGET", "llm call not started", mod=_MOD, purpose=purpose,
                        attempt=attempt + 1, timeout_s=round(t_out, 1))
            break
        req = {"purpose": purpose, "system": system, "prompt": cur_prompt, "schema": schema, "timeout_s": t_out,
               "effort": effort, "model": model, "attempt": attempt + 1}
        t0 = time.monotonic()
        try:
            out = await asyncio.wait_for(_invoke(req), timeout=t_out)
        except asyncio.TimeoutError:
            last_err = "timeout after %.1fs" % t_out
            trace.event("MODEL", purpose, mod=_MOD, model=model, effort=effort, ok=False, attempt=attempt + 1,
                        seconds=round(time.monotonic() - t0, 1), err=last_err)
            continue                                    # transport problem: retry the same prompt
        except Exception as e:                          # noqa: BLE001
            last_err = "%s: %s" % (type(e).__name__, str(e)[:300])
            trace.event("MODEL", purpose, mod=_MOD, model=model, effort=effort, ok=False, attempt=attempt + 1,
                        seconds=round(time.monotonic() - t0, 1), err=last_err)
            continue
        secs = round(time.monotonic() - t0, 1)
        data = out.get("data")
        if not isinstance(data, dict):
            data = parse_json_text(out.get("text"))
        if data is None:
            errs = ["<root>: no JSON object in the answer"]
        else:
            errs = schema_errors(data, schema)
            if not errs and validate is not None:
                try:
                    errs = list(validate(data) or [])
                except Exception as e:                  # noqa: BLE001
                    errs = ["<validate>: %s" % e]
        trace.event("MODEL", purpose, mod=_MOD, model=out.get("model") or model, effort=effort, ok=not errs,
                    attempt=attempt + 1, seconds=secs, usage=_usage_brief(out.get("usage")),
                    cost_usd=out.get("cost"), errors=len(errs))
        if not errs:
            return data
        last_err = "; ".join(errs[:5])
        cur_prompt = _repair_prompt(prompt, data if data is not None else (out.get("text") or ""), errs)
    raise LLMError("%s failed: %s" % (purpose, last_err))


def call_json(purpose, system, prompt, schema, *, timeout_s, effort=DEFAULT_EFFORT, model=None, budget=None,
              validate=None):
    """Synchronous structured call -> dict matching `schema`. Raises LLMError after retries."""
    return _run(acall_json(purpose, system, prompt, schema, timeout_s=timeout_s, effort=effort, model=model,
                           budget=budget, validate=validate))


def run_parallel(calls, max_concurrency=MAX_CONCURRENCY):
    """calls = [{"purpose", "system", "prompt", "schema", "timeout_s", ...}] -> list of dict | Exception (same order)."""
    async def _all():
        sem = asyncio.Semaphore(max(1, int(max_concurrency)))

        async def one(c):
            async with sem:
                try:
                    kw = {k: c[k] for k in ("effort", "model", "budget", "validate") if k in c}
                    return await acall_json(c["purpose"], c["system"], c["prompt"], c["schema"],
                                            timeout_s=c["timeout_s"], **kw)
                except Exception as e:                  # noqa: BLE001 - returned, not raised
                    return e
        return await asyncio.gather(*(one(c) for c in calls))
    if not calls:
        return []
    return list(_run(_all()))


def _run(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Called from inside a running loop (e.g. a notebook): run in a private thread.
    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result()
