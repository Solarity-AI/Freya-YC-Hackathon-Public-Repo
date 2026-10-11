"""Append-only build trace: stdout + <run_dir>/trace.txt + <run_dir>/trace.jsonl, secrets scrubbed on every write.
Owner: agent 5. Usable before init() (stdout only). Line format: "[+12.3s] KIND module.function | msg | k=v".
Kinds: builder.spec.vocab.TRACE_KINDS (plus TEST and SUMMARY). Test events carry where="LOCAL" or where="ON-AGENT".

Never raises: a trace problem must not break a build. Every string that reaches stdout or a file goes through scrub().
"""
import atexit
import datetime as _dt
import json
import os
import pathlib
import re
import sys
import threading
import time

from builder.spec.vocab import TRACE_KINDS

EXTRA_KINDS = ("TEST", "SUMMARY", "STAGE", "DEGRADE")
SECRET_ENV = ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")
SECRET_PATTERNS = (re.compile(r"fak_[A-Za-z0-9_\-]{4,}"), re.compile(r"sk-ant-[A-Za-z0-9_\-]{4,}"))
MIN_SECRET_LEN = 8          # short env values are ignored (they would scrub ordinary words)
MASK = "***"

_lock = threading.RLock()
_state = {"t0": time.monotonic(), "run_dir": None, "txt": None, "jsonl": None, "echo": True, "counts": {},
          "ended": False}


def _secret_values():
    vals = []
    for k in SECRET_ENV:
        v = os.environ.get(k, "")
        if v and len(v) >= MIN_SECRET_LEN:
            vals.append(v)
    return sorted(vals, key=len, reverse=True)


def scrub(text):
    """Replace env values of FREYA_API_KEY / FREYA_BANK_TEAM_KEY / ANTHROPIC_API_KEY and fak_* / sk-ant-* patterns."""
    try:
        s = text if isinstance(text, str) else str(text)
        for v in _secret_values():
            s = s.replace(v, MASK)
        for pat in SECRET_PATTERNS:
            s = pat.sub(MASK, s)
        return s
    except Exception:                                   # noqa: BLE001 - trace must never raise
        return MASK


def elapsed():
    return time.monotonic() - _state["t0"]


def init(run_dir, echo=True):
    """Open <run_dir>/trace.txt and trace.jsonl (append). Resets the clock to 0."""
    with _lock:
        close()
        p = pathlib.Path(run_dir)
        p.mkdir(parents=True, exist_ok=True)
        _state["t0"] = time.monotonic()
        _state["run_dir"] = p
        _state["txt"] = open(p / "trace.txt", "a", encoding="utf-8", buffering=1)
        _state["jsonl"] = open(p / "trace.jsonl", "a", encoding="utf-8", buffering=1)
        _state["echo"] = echo
        _state["counts"] = {}
        _state["ended"] = False
    return p


def _caller(depth=2):
    try:
        fr = sys._getframe(depth)
        mod = fr.f_globals.get("__name__", "?")
        if mod == "__main__":
            mod = pathlib.Path(fr.f_code.co_filename).stem
        return "%s.%s" % (mod, fr.f_code.co_name)
    except Exception:                                   # noqa: BLE001
        return "?"


def _fmt_val(v):
    if isinstance(v, (dict, list, tuple)):
        try:
            v = json.dumps(v, ensure_ascii=False, default=str, sort_keys=True)
        except Exception:                               # noqa: BLE001
            v = str(v)
    s = str(v)
    if len(s) > 300:
        s = s[:297] + "..."
    return s.replace("\n", " ")


def _jsonable(v):
    try:
        json.dumps(v)
        return v
    except Exception:                                   # noqa: BLE001
        return str(v)


def event(kind, msg="", /, **fields):
    """Record one event. The caller's module.function is detected automatically (inspect) unless mod= is given.
    Returns the formatted line (scrubbed)."""
    try:
        mod = fields.pop("mod", None) or _caller()
        kind = str(kind).upper()
        if kind not in TRACE_KINDS and kind not in EXTRA_KINDS:
            fields["orig_kind"] = kind
            kind = "WARN"
        t = elapsed()
        parts = ["[+%.1fs] %s %s" % (t, kind, mod), str(msg).replace("\n", " ")]
        if fields:
            parts.append(" ".join("%s=%s" % (k, _fmt_val(v)) for k, v in fields.items()))
        line = scrub(" | ".join(parts))
        rec = {"t": round(t, 3), "ts": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
               "kind": kind, "mod": mod, "msg": str(msg)}
        for k, v in fields.items():
            rec[("f_" + k) if k in rec else k] = _jsonable(v)
        rec_s = scrub(json.dumps(rec, ensure_ascii=False, default=str))
        with _lock:
            _state["counts"][kind] = _state["counts"].get(kind, 0) + 1
            if _state["echo"]:
                try:
                    print(line, file=sys.stdout, flush=True)
                except Exception:                       # noqa: BLE001
                    pass
            if _state["txt"] is not None:
                _state["txt"].write(line + "\n")
                _state["jsonl"].write(rec_s + "\n")
                if kind in ("ERROR", "END"):
                    _sync()
            if kind == "END":
                _state["ended"] = True
        return line
    except Exception:                                   # noqa: BLE001
        return ""


def _sync():
    for k in ("txt", "jsonl"):
        f = _state.get(k)
        if f is not None:
            try:
                f.flush()
                os.fsync(f.fileno())
            except Exception:                           # noqa: BLE001
                pass


def counts():
    with _lock:
        return dict(_state["counts"])


def summary(**fields):
    """Summary block appended at END: a 'SUMMARY' block in trace.txt and one SUMMARY record in trace.jsonl."""
    try:
        fields.setdefault("elapsed_s", round(elapsed(), 1))
        fields.setdefault("event_counts", counts())
        lines = ["", "=" * 20 + " SUMMARY " + "=" * 20]
        for k, v in fields.items():
            lines.append("%-16s %s" % (k + ":", _fmt_val(v)))
        lines.append("=" * 49)
        block = scrub("\n".join(lines))
        rec = {"t": round(elapsed(), 3), "kind": "SUMMARY", "mod": "builder.trace.summary", "msg": "summary"}
        rec.update({k: _jsonable(v) for k, v in fields.items()})
        rec_s = scrub(json.dumps(rec, ensure_ascii=False, default=str))
        with _lock:
            if _state["echo"]:
                print(block, flush=True)
            if _state["txt"] is not None:
                _state["txt"].write(block + "\n")
                _state["jsonl"].write(rec_s + "\n")
                _sync()
        return block
    except Exception:                                   # noqa: BLE001
        return ""


def ended():
    return bool(_state["ended"])


def run_dir():
    return _state["run_dir"]


def close():
    with _lock:
        _sync()
        for k in ("txt", "jsonl"):
            f = _state.get(k)
            if f is not None:
                try:
                    f.close()
                except Exception:                       # noqa: BLE001
                    pass
            _state[k] = None
        _state["run_dir"] = None
        _state["echo"] = True


atexit.register(close)
