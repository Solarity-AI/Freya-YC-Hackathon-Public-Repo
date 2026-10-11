"""Coverage round (builder core): paths, compiler.snippet, pipeline.degrade, trace, compiler.render.

Every test asserts the contract behaviour (return values, raised errors, trace records), success and error paths.
"""
import io
import json
import sys

import pytest

from builder import paths, trace
from builder.compiler import render, snippet
from builder.pipeline import degrade


@pytest.fixture(autouse=True)
def _close_trace():
    trace.close()
    yield
    trace.close()


# ================================================================================================ paths

def test_import_kit_loads_root_module_and_caches(monkeypatch):
    monkeypatch.setattr(paths, "_loaded", {})
    monkeypatch.setattr(sys, "path", list(sys.path))
    mod = paths.import_kit("freya")                       # kit/freya.py (root, not kit/tools/)
    assert mod.__file__.endswith("freya.py") and hasattr(mod, "save_workflow")
    assert paths.import_kit("freya") is mod               # cached
    assert str(paths.KIT) in sys.path and str(paths.KIT / "tools") in sys.path


def test_import_kit_tools_module(monkeypatch):
    monkeypatch.setattr(paths, "_loaded", {})
    monkeypatch.setattr(sys, "path", list(sys.path))
    mod = paths.import_kit("score")                       # kit/tools/score.py
    assert mod.__file__.endswith("score.py") and "tools" in mod.__file__


def test_import_kit_missing_module_raises(monkeypatch):
    monkeypatch.setattr(paths, "_loaded", {})
    with pytest.raises(FileNotFoundError, match="no_such_kit_module"):
        paths.import_kit("no_such_kit_module")


def test_bank_host_env_override(monkeypatch):
    monkeypatch.delenv("FREYA_BANK_HOST", raising=False)
    assert paths.bank_host().startswith("https://")
    monkeypatch.setenv("FREYA_BANK_HOST", "http://localhost:9")
    assert paths.bank_host() == "http://localhost:9"


# ================================================================================================ snippet

def test_runtime_spec_strips_meta_and_extraction_only_fields():
    spec = {"meta": {"x": 1}, "intents": [{"id": "i", "label": "L", "description": "d", "examples": ["e"],
                                           "negatives": ["n"], "action": {"kind": "k"}}],
            "right_party": {"ask": "a", "confirm_examples": ["c"], "non_confirm_examples": ["n"]}}
    w = {"listen": {"rp": "s_rp"}}
    r = snippet.runtime_spec(spec, w)
    assert r["v"] == 1 and "meta" not in r["spec"]
    assert r["spec"]["intents"] == [{"id": "i", "action": {"kind": "k"}}]
    assert r["spec"]["right_party"] == {"ask": "a"}
    assert r["wiring"] == w and r["wiring"] is not w
    assert spec["meta"] == {"x": 1} and "label" in spec["intents"][0]       # input untouched


def test_runtime_spec_non_dict_right_party_kept():
    r = snippet.runtime_spec({"right_party": None, "intents": None}, {})
    assert r["spec"] == {"right_party": None, "intents": None}


def test_check_code_problems():
    assert snippet.check_code("") == ["empty code"]
    assert snippet.check_code(None) == ["empty code"]
    assert snippet.check_code("x = 1\n") == []
    probs = snippet.check_code("x = '{{a}}'\n")
    assert probs == ["line 1: Freya braces in code"]
    probs = snippet.check_code("def f(:\n")
    assert len(probs) == 1 and probs[0].startswith("compile error")


def test_build_ctl_code_pack_failure_is_snippet_error(monkeypatch, golden_a, wiring_a):
    from runtime import bundle

    def boom(code):
        raise ValueError("deflate broke")
    monkeypatch.setattr(bundle, "pack_snippet", boom)
    with pytest.raises(snippet.SnippetError, match="pack failed: deflate broke"):
        snippet.build_ctl_code(golden_a, wiring_a)


def test_build_ctl_code_rejects_bad_packed_code(monkeypatch, golden_a, wiring_a):
    from runtime import bundle
    monkeypatch.setattr(bundle, "pack_snippet", lambda code: "x = '{{oops}}'\n")
    with pytest.raises(snippet.SnippetError, match="Freya braces"):
        snippet.build_ctl_code(golden_a, wiring_a)


def test_build_ctl_code_rejects_bad_inner_snippet(monkeypatch, golden_a, wiring_a):
    from runtime import bundle
    monkeypatch.setattr(bundle, "make_snippet", lambda rs, encoding="json", max_bytes=None, compact="auto": "def broken(:\n")
    with pytest.raises(snippet.SnippetError, match="compile error"):
        snippet.build_ctl_code(golden_a, wiring_a)


# ================================================================================================ degrade

def _int_lines(spec):
    return sorted(k for k, v in (spec.get("lines") or {}).items() if not isinstance(v, str))


def test_degrade_replaces_bad_leaf_with_default():
    spec = {"lines": {"clarify": 5, "ack": "ok"}}

    def check(s):
        return ["/lines/%s: 5 is not of type 'string'" % k for k in _int_lines(s)]
    out, errs, applied = degrade.degrade(spec, check(spec), check)
    assert errs == [] and applied == ["default /lines/clarify"]
    from builder.spec.defaults import DEFAULTS
    assert out["lines"]["clarify"] == DEFAULTS["lines"]["clarify"] and out["lines"]["ack"] == "ok"
    assert spec["lines"]["clarify"] == 5                                       # input never mutated


def test_degrade_fills_required_property_from_defaults_nested_and_root():
    spec = {"right_party": {"ask": "a"}}

    def check(s):
        e = []
        if "max_asks" not in s.get("right_party", {}):
            e.append("/right_party: 'max_asks' is a required property")
        if "lines" not in s:
            e.append("/: 'lines' is a required property")
        return e
    out, errs, applied = degrade.degrade(spec, check(spec), check)
    assert errs == []
    assert applied == ["default /right_party/max_asks", "default /lines"]
    assert out["right_party"]["max_asks"] == 2 and out["lines"]["clarify"]


def test_degrade_removes_list_element_named_by_intent_id(tmp_path):
    trace.init(tmp_path / "t", echo=False)
    spec = {"intents": [{"id": "I_OK", "keywords": ["a"]}, {"id": "I_BAD", "keywords": ["("]}]}

    def check(s):
        return ["/intents/I_BAD/keywords/0: bad regex"] if any(i["id"] == "I_BAD" for i in s["intents"]) else []
    out, errs, applied = degrade.degrade(spec, check(spec), check)
    assert errs == [] and applied == ["remove /intents/1"]
    assert [i["id"] for i in out["intents"]] == ["I_OK"]
    trace.close()
    recs = [json.loads(x) for x in (tmp_path / "t" / "trace.jsonl").read_text().splitlines()]
    # DEGRADE is a registered trace kind (trace.EXTRA_KINDS), so the trace can be filtered by it
    assert any(r["kind"] == "DEGRADE" and "orig_kind" not in r and "remove /intents/1" in r["msg"] for r in recs)


def test_degrade_drops_unknown_dict_key():
    spec = {"notes": {"enabled": False, "bogus_key": 1}}

    def check(s):
        return ["/notes/bogus_key: unexpected"] if "bogus_key" in s["notes"] else []
    out, errs, applied = degrade.degrade(spec, check(spec), check)
    assert errs == [] and applied == ["drop /notes/bogus_key"] and out["notes"] == {"enabled": False}


def test_degrade_error_without_pointer_is_left_alone():
    calls = []

    def check(s):
        calls.append(1)
        return ["something is wrong"]
    out, errs, applied = degrade.degrade({"a": 1}, ["something is wrong"], check)
    assert out == {"a": 1} and errs == ["something is wrong"] and applied == [] and calls == []


def test_degrade_candidate_kept_only_when_errors_drop():
    spec = {"lines": {"clarify": 5}}

    def check(s):
        return ["/lines/clarify: still bad"]                                 # never improves
    out, errs, applied = degrade.degrade(spec, check(spec), check)
    assert out == spec and errs == ["/lines/clarify: still bad"] and applied == []


def test_degrade_stops_after_three_passes():
    # one fix per pass (each fix reveals the next bad key); five bad keys -> three fixed, two left
    keys = ["ack", "clarify", "continue_prompt", "hold", "no_info"]
    spec = {"lines": {k: 1 for k in keys}}

    def check(s):
        bad = _int_lines(s)
        if not bad:
            return []
        return ["/lines/%s: not a string" % bad[0]] + ["/zzz: pad"] * (len(bad) - 1)
    out, errs, applied = degrade.degrade(spec, check(spec), check)
    assert applied == ["default /lines/ack", "default /lines/clarify", "default /lines/continue_prompt"]
    assert len(errs) == 2 and _int_lines(out) == ["hold", "no_info"]


def test_degrade_check_budget(monkeypatch):
    monkeypatch.setattr(degrade, "MAX_CHECKS", 1)
    calls = []

    def check(s):
        calls.append(1)
        return ["/lines/clarify: bad", "/lines/ack: bad"]
    spec = {"lines": {"clarify": 1, "ack": 1}}
    out, errs, applied = degrade.degrade(spec, ["/lines/clarify: bad", "/lines/ack: bad"], check)
    assert len(calls) == 1 and applied == [] and len(errs) == 2


# ================================================================================================ trace

class _Boom:
    def __str__(self):
        raise RuntimeError("no str")


def test_scrub_never_raises():
    assert trace.scrub(_Boom()) == trace.MASK


def test_caller_of_main_module_uses_file_stem():
    g = {"__name__": "__main__", "trace": trace}
    exec(compile("line = trace.event('START', 'from a script')", "/x/my_script.py", "exec"), g)
    assert " my_script.<module> " in g["line"]


def test_caller_too_deep_is_question_mark():
    assert trace._caller(10_000) == "?"


def test_fmt_val_unsortable_dict_falls_back_to_str():
    assert trace._fmt_val({1: "a", "b": 2}) == "{1: 'a', 'b': 2}"
    assert trace._fmt_val(["x"]) == '["x"]'


def test_event_survives_broken_stdout(tmp_path, monkeypatch):
    trace.init(tmp_path / "t", echo=True)

    class BadOut:
        def write(self, s):
            raise OSError("closed pipe")

        def flush(self):
            raise OSError("closed pipe")
    monkeypatch.setattr(sys, "stdout", BadOut())
    line = trace.event("START", "still written")
    monkeypatch.undo()
    trace.close()
    assert "still written" in line
    assert "still written" in (tmp_path / "t" / "trace.txt").read_text()


def test_error_event_sync_tolerates_files_without_fileno(monkeypatch):
    txt, jl = io.StringIO(), io.StringIO()
    monkeypatch.setitem(trace._state, "txt", txt)
    monkeypatch.setitem(trace._state, "jsonl", jl)
    monkeypatch.setitem(trace._state, "echo", False)
    trace.event("ERROR", "disk event")                  # ERROR -> _sync -> fileno() unsupported, swallowed
    assert "disk event" in txt.getvalue() and json.loads(jl.getvalue())["kind"] == "ERROR"
    monkeypatch.setitem(trace._state, "txt", None)
    monkeypatch.setitem(trace._state, "jsonl", None)


def test_summary_echo_off_writes_files_only(tmp_path, capsys):
    trace.init(tmp_path / "t", echo=False)
    block = trace.summary(exit=0)
    trace.close()
    assert capsys.readouterr().out == ""
    assert "exit:" in block and "SUMMARY" in (tmp_path / "t" / "trace.txt").read_text()
    rec = json.loads((tmp_path / "t" / "trace.jsonl").read_text().splitlines()[-1])
    assert rec["kind"] == "SUMMARY" and rec["exit"] == 0


def test_summary_before_init_prints_only(capsys):
    block = trace.summary(exit=2)
    assert "exit:" in capsys.readouterr().out and "SUMMARY" in block
    assert trace.run_dir() is None


def test_summary_never_raises():
    assert trace.summary(bad=_Boom()) == ""


def test_run_dir_and_close_with_failing_files(tmp_path):
    p = trace.init(tmp_path / "t", echo=False)
    assert trace.run_dir() == p

    class BadFile:
        def flush(self):
            raise OSError("x")

        def fileno(self):
            raise OSError("x")

        def close(self):
            raise OSError("x")
    real_txt, real_jl = trace._state["txt"], trace._state["jsonl"]
    trace._state["txt"], trace._state["jsonl"] = BadFile(), BadFile()
    trace.close()                                       # never raises
    real_txt.close()
    real_jl.close()
    assert trace.run_dir() is None and trace._state["txt"] is None and trace._state["jsonl"] is None


# ================================================================================================ render

SPEC = {"bank": {"name": "Acme Credit", "assistant_self": "the <bank> assistant", "language": "de"},
        "addressing": {"customer": "<v:title> <v:surname>"},
        "call_variables": {"declared": [{"name": "title"}, {"name": "surname"}]},
        "opening": {"line": "Hello from <bank>."}, "right_party": {"ask": "Am I speaking with <customer>?"}}


def test_compile_line_none_and_customer_expansion():
    assert render.compile_line(None, SPEC) == ""
    assert render.compile_line("Hi <customer>, this is <self>.", SPEC) == \
        "Hi {{title}} {{surname}}, this is the Acme Credit assistant."


def test_compile_line_errors():
    bad = dict(SPEC, addressing={"customer": "<customer>"})
    with pytest.raises(render.RenderError, match="refers to itself"):
        render.compile_line("Hi <customer>", bad)
    with pytest.raises(render.RenderError, match="braces"):
        render.compile_line("Hi {{x}}", SPEC)
    with pytest.raises(render.RenderError, match="runtime-only"):
        render.compile_line("Pay <amount>", SPEC)
    with pytest.raises(render.RenderError, match="runtime-only"):
        render.compile_line("Pay <f:due>", SPEC)
    with pytest.raises(render.RenderError, match="unknown placeholder"):
        render.compile_line("Pay <zork>", SPEC)
    with pytest.raises(render.RenderError, match="not a declared"):
        render.compile_line("Hi <v:nickname>", SPEC)
    with pytest.raises(render.RenderError, match="bad call variable"):
        render.compile_line("Hi <v:9x>", SPEC)


def test_strip_runtime_drops_runtime_placeholders():
    assert render.strip_runtime("Pay <amount> to <bank> by <date>.", SPEC) == "Pay to Acme Credit by ."
    assert render.strip_runtime(None, SPEC) == ""


def test_check_placeholders_all_problem_kinds():
    assert render.check_placeholders("Hi <v:title> <f:due_amount> <amount>", SPEC) == []
    probs = render.check_placeholders("{{x}} <v:nope> <v:9a> <f:9bad> <zork>", SPEC)
    assert probs == ["Freya braces in a Spec line", "<v:nope> is not a declared call variable",
                     "<v:9a> is not a declared call variable", "bad field placeholder <f:9bad>",
                     "unknown placeholder <zork>"]


def test_open_line_task_clarify_and_system_prompt():
    assert render.open_line(SPEC) == "Hello from Acme Credit. Am I speaking with {{title}} {{surname}}?"
    assert render.open_task(SPEC).endswith("«" + render.open_line(SPEC) + "»")
    assert render.clarify_line(SPEC) == "Sorry, could you say that again?"
    assert render.clarify_line(dict(SPEC, lines={"clarify": "Pardon, <bank>?"})) == "Pardon, Acme Credit?"
    sp = render.system_prompt(SPEC)
    assert "Speak German." in sp and "the Acme Credit assistant" in sp and "Never call a tool." in sp
    sp2 = render.system_prompt({"bank": {"language": "xx-YY"}})
    assert "Speak xx-YY." in sp2 and "a digital assistant" in sp2


def test_topic_values_ordering_dedup_and_builtins():
    spec = {"interpretation": {"intent_tie": ["B"]},
            "intents": [{"id": "A", "scope": ["neg"], "precedence": 1},
                        {"id": "B", "scope": ["neg"], "precedence": 1},
                        {"id": "C", "scope": ["neg"], "precedence": 5},
                        {"id": "C", "scope": ["neg"]},                  # duplicate id: dropped
                        {"id": "", "scope": ["neg"]},                   # empty id: dropped
                        {"id": "other_person", "scope": ["rp"]}]}       # shadows a builtin rp topic
    assert render.topic_values("neg", spec) == ["C", "B", "A", "none"]
    rp = render.topic_values("rp", spec)
    assert rp == ["other_person", "unavailable", "hold", "none"]          # builtin other_person not repeated
    assert render.topic_values("safe", spec) == []


def test_topic_values_capped_with_trace(tmp_path):
    trace.init(tmp_path / "t", echo=False)
    spec = {"intents": [{"id": "I%02d" % i, "scope": ["conf"]} for i in range(15)]}
    vals = render.topic_values("conf", spec)
    trace.close()
    assert len(vals) == 12 and vals[-1] == "none" and vals[:2] == ["I00", "I01"]
    txt = (tmp_path / "t" / "trace.txt").read_text()
    assert "capped at 12" in txt and "I11" in txt and "I14" in txt


def test_extraction_schema_topic_descriptions_and_slots():
    spec = {"intents": [{"id": "X_BOTH", "scope": ["conf"], "description": 'says "{{hi}}"',
                         "examples": ["e1", "e2", "e3"], "negatives": ["n1"]},
                        {"id": "X_EX", "scope": ["conf"], "label": "only examples", "examples": ["e"]},
                        {"id": "X_NEG", "scope": ["conf"], "negatives": ["n"]},
                        {"id": "X_NONE", "scope": ["conf"]}]}
    f = render.extraction_schema("conf", spec)
    assert [x["name"] for x in f] == ["u_text", "u_act", "u_topic", "u_date", "u_amt"]
    d = f[2]["description"]
    assert "X_BOTH: says '(hi)' (e.g. \"e1\"; \"e2\"; not \"n1\")." in d and "e3" not in d
    assert "X_EX: only examples (e.g. \"e\")." in d
    assert "X_NEG: X_NEG (not \"n\")." in d
    assert "X_NONE: X_NONE." in d
    assert f[2]["enum_values"][-1] == "none"
    safe = render.extraction_schema("safe", spec)
    assert [x["name"] for x in safe] == ["u_text", "u_act"]
    with pytest.raises(render.RenderError, match="unknown stage"):
        render.extraction_schema("zz", spec)
