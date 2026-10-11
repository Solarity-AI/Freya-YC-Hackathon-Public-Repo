"""Tests for runtime/bundle.py (agent 2): one brace-safe, stdlib-only ctl snippet that behaves exactly like the
runtime modules (the 13 practice cases are replayed through the exec'd snippet)."""
import copy
import json
import re

import pytest

from runtime import brain, bundle
from tests.test_brain import (CASES, PUB_SCRIPTS, SPEC_A, SPEC_AB, W_A, W_AB, Driver, runtime_spec, spec_for)


def _rspec(spec, wiring):
    return {"v": 1, "spec": runtime_spec(spec), "wiring": wiring}


def _plain_snippet(rs):
    """Unminified, uncompacted bundle (over MAX_BYTES for B, so assembled here without the size gate)."""
    code = bundle.bundle_source(minify=False)
    return (code + "RSPEC_HEX = '" + bundle.rspec_hex(rs) + "'\nglobals().update(locals())\n"
            "try:\n    main(vars, RSPEC_HEX)\nexcept Exception:\n    vars['nx'] = 's_safe'\n")


@pytest.fixture(scope="module")
def snippets():
    out = {}
    for key, (sp, w) in {"A": (SPEC_A, W_A), "B": (SPEC_AB, W_AB)}.items():
        out[key] = {"min": bundle.make_snippet(_rspec(sp, w)),
                    "plain": _plain_snippet(_rspec(sp, w)),
                    "json": bundle.make_snippet(_rspec(sp, w), encoding="json")}
    return out


def _entry(code, separate_locals=False):
    compiled = compile(code, "<ctl>", "exec")

    def run(vars, _R):
        if separate_locals:
            exec(compiled, {"vars": vars}, {})
        else:
            exec(compiled, {"vars": vars})
    return run


# ------------------------------------------------------------------ static properties
def test_check_brace_safe():
    assert bundle.check_brace_safe("a = 1\nb = {'x': 1}\n") == []
    probs = bundle.check_brace_safe("x = 1\ny = {'a': {'b': 1}}\n")
    assert probs and probs[0].startswith("line 2")
    assert bundle.check_brace_safe("{{x") and bundle.check_brace_safe("y}}")


@pytest.mark.parametrize("minify", [True, False])
def test_bundle_source_compiles_and_is_stdlib_only(minify):
    code = bundle.bundle_source(minify=minify)
    compile(code, "<b>", "exec")
    assert "{{" not in code and "}}" not in code
    for line in code.splitlines():
        m = re.match(r"^\s*(?:import|from)\s+([\w.]+)", line)
        if m:
            assert m.group(1).split(".")[0] in ("json", "re", "datetime"), line
    assert "from ." not in code
    assert "def main(" in code


def test_minified_is_smaller_and_keeps_public_names():
    a = bundle.bundle_source(minify=True)
    b = bundle.bundle_source(minify=False)
    assert len(a) < len(b)
    assert "def main(" in a
    stripped = re.sub(r"'[^']*'|\"[^\"]*\"", "", a)
    assert "_b_" not in stripped and "def step(" not in stripped


@pytest.mark.parametrize("key", ["A", "B"])
def test_snippet_shape_and_size(snippets, key):
    s = snippets[key]["min"]
    assert len(s.encode()) <= bundle.MAX_BYTES
    assert not bundle.check_brace_safe(s)
    tail = s.splitlines()[-6:]
    assert tail[0].startswith("RSPEC_HEX = '") and re.match(r"^RSPEC_HEX = '[0-9a-f]+'$", tail[0])
    assert tail[2:] == ["try:", "    main(vars, RSPEC_HEX)", "except Exception:", "    vars['nx'] = 's_safe'"]
    hx = tail[0].split("'")[1]
    rs = json.loads(bytes.fromhex(hx).decode())
    assert rs["v"] == 1 and "meta" not in rs["spec"]


def test_json_encoding_is_brace_safe_and_decodes(snippets):
    s = snippets["B"]["json"]
    assert not bundle.check_brace_safe(s)
    line = [l for l in s.splitlines() if l.startswith("RSPEC_HEX = ")][0]
    ns = {}
    exec(line, ns)
    assert brain._b_dec(ns["RSPEC_HEX"])["spec"]["bank"]["name"] == SPEC_AB["bank"]["name"]
    assert len(s) < len(snippets["B"]["min"])


def test_auto_encoding_switches_to_json_when_hex_too_big(monkeypatch):
    rs = _rspec(SPEC_AB, W_AB)
    rs["pad"] = "x" * 10000
    monkeypatch.setattr(bundle, "MAX_BYTES", len(bundle.make_snippet(rs, encoding="json").encode()) + 10)
    s = bundle.make_snippet(rs)
    assert not re.search(r"^RSPEC_HEX = '[0-9a-f]+'$", s, re.M)
    with pytest.raises(ValueError):
        bundle.make_snippet(rs, encoding="hex")


def test_too_big_raises(monkeypatch):
    monkeypatch.setattr(bundle, "MAX_BYTES", 1000)
    with pytest.raises(ValueError):
        bundle.make_snippet(_rspec(SPEC_A, W_A))


def test_compact_wiring_round_trip():
    for w in (W_A, W_AB):
        cw = bundle.compact_wiring(w)
        assert len(json.dumps(cw)) < len(json.dumps(w))
        for node in w["nodes"]:
            assert brain._b_node(cw, node) == w["nodes"][node], node
        assert cw["nodes"]["a_close_n"] == w["nodes"]["a_close_n"]   # co/cr bodies stay explicit


# ------------------------------------------------------------------ bundling rules on synthetic modules
def _fake_runtime(tmp_path, files):
    for name in bundle.MODULE_ORDER:
        (tmp_path / (name + ".py")).write_text(files.get(name, "X_%s = 1\n" % name))
    return tmp_path


def test_duplicate_top_level_names_rejected(tmp_path, monkeypatch):
    d = _fake_runtime(tmp_path, {"cal": "def f():\n    return 1\n", "parse": "def f():\n    return 2\n"})
    monkeypatch.setattr(bundle, "RUNTIME_DIR", d)
    with pytest.raises(ValueError, match="top-level name"):
        bundle.bundle_source()


def test_disallowed_import_rejected(tmp_path, monkeypatch):
    d = _fake_runtime(tmp_path, {"ident": "import os\n"})
    monkeypatch.setattr(bundle, "RUNTIME_DIR", d)
    with pytest.raises(ValueError, match="not allowed"):
        bundle.bundle_source()


def test_nested_disallowed_import_rejected(tmp_path, monkeypatch):
    d = _fake_runtime(tmp_path, {"ident": "def g():\n    import subprocess\n    return 1\n"})
    monkeypatch.setattr(bundle, "RUNTIME_DIR", d)
    with pytest.raises(ValueError, match="not allowed"):
        bundle.bundle_source()


def test_name_main_block_rejected(tmp_path, monkeypatch):
    d = _fake_runtime(tmp_path, {"brain": "if __name__ == '__main__':\n    pass\n"})
    monkeypatch.setattr(bundle, "RUNTIME_DIR", d)
    with pytest.raises(ValueError, match="__name__"):
        bundle.bundle_source()


def test_double_brace_in_module_rejected(tmp_path, monkeypatch):
    d = _fake_runtime(tmp_path, {"brain": "X = {'a': {'b': 1}}\n"})
    monkeypatch.setattr(bundle, "RUNTIME_DIR", d)
    with pytest.raises(ValueError, match="brace"):
        bundle.bundle_source(minify=False)


def test_sibling_imports_stripped_and_hoisted(tmp_path, monkeypatch):
    d = _fake_runtime(tmp_path, {
        "cal": "import datetime\nfrom datetime import date\n\n\ndef _c_one():\n    \"\"\"doc\"\"\"\n    return 1\n",
        "parse": "from .cal import (\n    _c_one,\n)\nimport re\n\n\ndef _p_two():\n    # comment\n    return _c_one() + 1\n",
        "ident": "from .parse import _p_two\n\n\ndef only_doc():\n    \"\"\"just a docstring\"\"\"\n",
        "brain": "import json\nfrom .ident import only_doc\n\n\ndef main(vars, rspec):\n    vars['nx'] = str(_p_two())\n",
    })
    monkeypatch.setattr(bundle, "RUNTIME_DIR", d)
    code = bundle.bundle_source()
    assert "from ." not in code and "just a docstring" not in code and '"""' not in code and "comment" not in code
    v = {}
    exec(code + "main(vars, None)\n", {"vars": v})
    assert v["nx"] == "2"


def test_minify_preserves_strings_and_operators():
    src = ("def f(a, b=-1, *c, **d):\n"
           "    x = 'a  b # not a comment'  # real comment\n"
           "    y = [1,\n         2]\n"
           "    if a is not None and b <= -1 or a == 2:\n"
           "        return x, y, a ** 2, 1 if a else 2, .5, 1.0, \"q\" \"r\"\n"
           "    return None\n")
    m = bundle._minify(src)
    ns1, ns2 = {}, {}
    exec(src, ns1)
    exec(m, ns2)
    for args in [(2,), (None,), (0, -1), (3, 5)]:
        assert ns1["f"](*args) == ns2["f"](*args)
    assert "real comment" not in m and "a  b # not a comment" in m


# ------------------------------------------------------------------ behaviour: snippet == modules
@pytest.mark.parametrize("variant", ["min", "plain", "json"])
@pytest.mark.parametrize("cid", sorted(PUB_SCRIPTS))
def test_practice_cases_through_snippet(snippets, cid, variant):
    case = CASES[cid]
    sp, w = spec_for(case)
    code = snippets[case["brief"] if case["brief"] == "A" else "B"][variant]
    d = Driver(sp, w, case, faults=case.get("faults"), entry=_entry(code))
    d.play(PUB_SCRIPTS[cid])
    ref = Driver(sp, w, case, faults=case.get("faults"))
    ref.play(PUB_SCRIPTS[cid])
    assert d.score()["pass"], d.lines
    assert d.lines == ref.lines
    assert d.tools() == ref.tools()


def test_snippet_works_with_separate_globals_and_locals(snippets):
    case = CASES["PUB-12"]
    d = Driver(SPEC_AB, W_AB, case, entry=_entry(snippets["B"]["min"], separate_locals=True))
    d.play(PUB_SCRIPTS["PUB-12"])
    assert d.score()["pass"], d.lines


def test_snippet_writes_strings_only_and_nx_last(snippets):
    class V(dict):
        order = []

        def __setitem__(self, k, v):
            V.order.append(k)
            assert isinstance(v, str), (k, v)
            dict.__setitem__(self, k, v)
    v = V(CASES["PUB-01"]["variables"])
    dict.__setitem__(v, "customer_id", "c1")
    dict.__setitem__(v, "u_text", "Yes, speaking.")
    exec(snippets["A"]["min"], {"vars": v})
    assert V.order[0] == "nx" and V.order[-1] == "nx" and v["nx"] == "s_id"


def test_snippet_crash_safe_on_garbage_state(snippets):
    v = {"st": "{not json", "u_text": None, "now": None}
    exec(snippets["A"]["min"], {"vars": v})
    assert isinstance(v["nx"], str) and v["nx"]


def test_snippet_entry_guard_sets_safe_when_main_missing():
    code = bundle.bundle_source()
    code = code.replace("def main(", "def _unused_main(")
    tail = "RSPEC_HEX = 'zz'\ntry:\n    main(vars, RSPEC_HEX)\nexcept Exception:\n    vars['nx'] = 's_safe'\n"
    v = {}
    exec(code + tail, {"vars": v})
    assert v["nx"] == "s_safe"


def test_whole_brain_scenario_suite_through_minified_snippet():
    """Replays every Driver scenario of tests/test_brain.py through the exec'd, minified bundle."""
    import os
    import subprocess
    import sys
    env = dict(os.environ, BRAIN_ENTRY="snippet")
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_brain.py"],
                       cwd=str(bundle.RUNTIME_DIR.parent), env=env, capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]


# ---------------------------------------------------------------- packed loader (live 128 KiB code_exec limit)
@pytest.mark.parametrize("fallback", [False, True], ids=["zlib", "pure_inflate"])
def test_packed_snippet_runs_like_inner(snippets, fallback):
    inner = snippets["B"]["json"]
    packed = bundle.pack_snippet(inner, force_fallback=fallback)
    assert len(packed.encode()) <= bundle.PACK_MAX_BYTES
    assert bundle.check_brace_safe(packed) == []
    assert bundle.unpack_snippet(packed) == inner
    tops = [l for l in packed.splitlines() if l.startswith("import ")]
    assert tops == ["import json", "import re", "import datetime"]
    for sep in (False, True):
        v1, v2 = {"u_text": "Hello?"}, {"u_text": "Hello?"}
        if sep:                                           # platform may exec with separate globals/locals
            exec(compile(packed, "<ctl>", "exec"), {}, {"vars": v1})
        else:
            exec(compile(packed, "<ctl>", "exec"), {"vars": v1})
        exec(compile(inner, "<ctl>", "exec"), {"vars": v2})
        assert v1 == v2 and v1.get("nx") not in (None, "s_safe")


def test_packed_snippet_corrupt_payload_goes_safe():
    packed = bundle.pack_snippet("vars['nx'] = 'x'\n")
    bad = re.sub(r"_qb\('[^']*'\)", "_qb('AAAA')", packed)
    v = {}
    exec(bad, {"vars": v})
    assert v["nx"] == "s_safe"
