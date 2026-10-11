"""builder.trace: format, files, scrubbing, robustness (agent 5)."""
import json
import re

import pytest

from builder import trace

LINE_RE = re.compile(r"^\[\+\d+\.\ds\] [A-Z]+ \S+ \| ")


@pytest.fixture(autouse=True)
def _close():
    trace.close()
    yield
    trace.close()


def test_event_before_init_prints_only(capsys):
    line = trace.event("START", "hello", a=1)
    out = capsys.readouterr().out
    assert "hello" in out and LINE_RE.match(line)
    assert line.endswith("| a=1")
    assert "test_trace.test_event_before_init_prints_only" in line     # caller detection


def test_init_writes_txt_and_jsonl(tmp_path):
    trace.init(tmp_path / "run")
    trace.event("CATALOG", "tools bound", tools=["x", "y"], n=7)
    trace.event("MODEL", "extract F1", mod="builder.llm.call_json", model="m", ok=True, seconds=1.5)
    trace.close()
    txt = (tmp_path / "run" / "trace.txt").read_text().splitlines()
    assert len(txt) == 2 and all(LINE_RE.match(t) for t in txt)
    assert "builder.llm.call_json" in txt[1] and "model=m" in txt[1]
    recs = [json.loads(x) for x in (tmp_path / "run" / "trace.jsonl").read_text().splitlines()]
    assert [r["kind"] for r in recs] == ["CATALOG", "MODEL"]
    assert recs[0]["tools"] == ["x", "y"] and recs[0]["n"] == 7
    assert recs[1]["mod"] == "builder.llm.call_json" and recs[1]["ok"] is True
    assert all("t" in r and "ts" in r for r in recs)


def test_where_field_for_test_events(tmp_path):
    trace.init(tmp_path)
    trace.event("TWIN", "PASS smoke-1", where="LOCAL")
    trace.event("TEST", "chat case", where="ON-AGENT")
    trace.close()
    recs = [json.loads(x) for x in (tmp_path / "trace.jsonl").read_text().splitlines()]
    assert [(r["kind"], r["where"]) for r in recs] == [("TWIN", "LOCAL"), ("TEST", "ON-AGENT")]


def test_scrub_env_values_and_patterns(monkeypatch):
    monkeypatch.setenv("FREYA_API_KEY", "supersecretvalue123")
    monkeypatch.setenv("FREYA_BANK_TEAM_KEY", "abc")          # too short: ignored
    s = trace.scrub("key=supersecretvalue123 fak_ABCdef123456 sk-ant-api03-xyzXYZ_123 abc ok")
    assert "supersecretvalue123" not in s and "fak_ABC" not in s and "sk-ant-api03" not in s
    assert s.count("***") == 3 and " abc " in s and s.endswith("ok")


def test_secrets_never_reach_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-zzzzzzzzzzzzzzzz")
    monkeypatch.setenv("FREYA_API_KEY", "fak_live_0123456789")
    trace.init(tmp_path)
    trace.event("FREYA", "auth with fak_live_0123456789", header={"x": "sk-ant-zzzzzzzzzzzzzzzz"})
    trace.summary(note="fak_live_0123456789")
    trace.close()
    blob = (tmp_path / "trace.txt").read_text() + (tmp_path / "trace.jsonl").read_text() + capsys.readouterr().out
    assert "fak_live" not in blob and "sk-ant-zzz" not in blob and "***" in blob


def test_unknown_kind_becomes_warn(tmp_path):
    trace.init(tmp_path)
    line = trace.event("bogus", "x")
    trace.close()
    assert " WARN " in line
    rec = json.loads((tmp_path / "trace.jsonl").read_text())
    assert rec["kind"] == "WARN" and rec["orig_kind"] == "BOGUS"


def test_lowercase_known_kind_is_normalised():
    assert " SPEC " in trace.event("spec", "ok")


def test_event_never_raises_on_odd_fields(tmp_path):
    class Weird:
        def __str__(self):
            raise RuntimeError("no str")
    trace.init(tmp_path)
    trace.event("WARN", "odd", obj=object(), s={1, 2}, b=b"\x00\xff")
    trace.event("WARN", "weird", w=Weird())                    # must not raise
    trace.close()
    assert (tmp_path / "trace.jsonl").read_text().count("\n") >= 1


def test_summary_block_and_end(tmp_path):
    trace.init(tmp_path)
    trace.event("END", "exit 0", exit=0)
    assert trace.ended()
    trace.summary(slot="s1", exit=0)
    trace.close()
    txt = (tmp_path / "trace.txt").read_text()
    assert "SUMMARY" in txt and "slot:" in txt and "event_counts" in txt
    recs = [json.loads(x) for x in (tmp_path / "trace.jsonl").read_text().splitlines()]
    assert recs[-1]["kind"] == "SUMMARY" and recs[-1]["slot"] == "s1"


def test_event_after_close_is_stdout_only(tmp_path, capsys):
    trace.init(tmp_path)
    trace.close()
    trace.event("WARN", "late")
    assert "late" in capsys.readouterr().out
    assert (tmp_path / "trace.txt").read_text() == ""


def test_long_values_truncated_and_newlines_flattened():
    line = trace.event("WARN", "multi\nline", big="x" * 1000)
    assert "\n" not in line and "..." in line and len(line) < 600


def test_reinit_resets_clock_and_counts(tmp_path):
    trace.init(tmp_path / "a")
    trace.event("WARN", "1")
    trace.init(tmp_path / "b")
    assert trace.counts() == {}
    assert trace.event("WARN", "2").startswith("[+0.")


def test_fields_named_like_record_keys(tmp_path):
    trace.init(tmp_path)
    line = trace.event("SEGMENT", "doc", kind="brief", msg="m2", t=5)
    trace.close()
    assert "kind=brief" in line
    rec = json.loads((tmp_path / "trace.jsonl").read_text())
    assert rec["kind"] == "SEGMENT" and rec["f_kind"] == "brief" and rec["f_msg"] == "m2" and rec["f_t"] == 5
