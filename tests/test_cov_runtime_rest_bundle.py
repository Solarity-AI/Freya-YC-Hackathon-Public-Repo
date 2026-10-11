"""Coverage + behaviour tests for runtime/bundle.py (docs/CONTRACTS.md C.1): import / name rules on synthetic
runtime modules, minifier corner cases (global, lambdas, `with ... as`, continued `def`), wiring compaction
that must leave non-conventional nodes alone, compact=True, and the size / compile guards."""
import json
import re

import pytest

from runtime import bundle


def _fake_runtime(tmp_path, files):
    for name in bundle.MODULE_ORDER:
        (tmp_path / (name + ".py")).write_text(files.get(name, "X_%s = 1\n" % name))
    return tmp_path


def _use(monkeypatch, tmp_path, files):
    monkeypatch.setattr(bundle, "RUNTIME_DIR", _fake_runtime(tmp_path, files))


def _run(code):
    v = {}
    exec(code + "main(vars, None)\n", {"vars": v})
    return v


MAIN = "def main(vars, rspec):\n    vars['nx'] = str(%s)\n"


# ------------------------------------------------------------------ module rules
def test_annotated_top_level_names_count_as_names(tmp_path, monkeypatch):
    _use(monkeypatch, tmp_path, {"cal": "LIMIT: int = 1\n", "parse": "LIMIT: int = 2\n"})
    with pytest.raises(bundle.BundleError, match="top-level name 'LIMIT'"):
        bundle.bundle_source()


def test_top_level_from_import_outside_stdlib_whitelist(tmp_path, monkeypatch):
    _use(monkeypatch, tmp_path, {"ident": "from os import path\n"})
    with pytest.raises(bundle.BundleError, match="from os import not allowed"):
        bundle.bundle_source()


def test_nested_from_import_outside_whitelist(tmp_path, monkeypatch):
    _use(monkeypatch, tmp_path, {"ident": "def g():\n    from os import path\n    return path\n"})
    with pytest.raises(bundle.BundleError, match="from os import not allowed"):
        bundle.bundle_source()


def test_empty_module_and_allowed_from_import(tmp_path, monkeypatch):
    _use(monkeypatch, tmp_path, {
        "cal": "",
        "parse": "from datetime import date as D\n\n\ndef _p_y():\n    return D(2026, 1, 2).day\n",
        "brain": MAIN % "_p_y()",
    })
    code = bundle.bundle_source()
    assert code.startswith("from datetime import date as D\n")
    assert _run(code)["nx"] == "2"


# ------------------------------------------------------------------ renaming corner cases
def test_global_names_are_not_renamed(tmp_path, monkeypatch):
    _use(monkeypatch, tmp_path, {
        "cal": "COUNT = 0\n\n\ndef _c_bump(step):\n    global COUNT\n    COUNT = COUNT + step\n    return COUNT\n",
        "brain": MAIN % "_c_bump(2) + _c_bump(3)",
    })
    for minify in (True, False):
        assert _run(bundle.bundle_source(minify=minify))["nx"] == "7"


def test_top_level_lambda_locals_are_renamed_consistently(tmp_path, monkeypatch):
    _use(monkeypatch, tmp_path, {
        "cal": "_c_twice = lambda value: value * 2\n",
        "brain": MAIN % "_c_twice(21)",
    })
    code = bundle.bundle_source()
    assert "value" not in code
    assert _run(code)["nx"] == "42"


def test_short_names_skip_taken_candidates():
    assert bundle._short_names(["alpha", "beta"], {"Qa"}) == {"alpha": "Qb", "beta": "Qc"}


def test_minify_with_statement_and_continued_def():
    # `as` outside an except clause is left alone; a def name on a continuation line has no def column (-1)
    assert bundle._minify("with a as b:\n    pass\n") == "with a as b:\n pass"
    src = "def \\\n  f():\n    pass\n"
    import io
    import tokenize
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    name = [t for t in toks if t[1] == "f"][0]
    assert bundle._def_col(toks, name) == -1
    assert bundle._except_key(toks, name) is None
    assert bundle._minify(src) == "def f():\n pass"


# ------------------------------------------------------------------ compact_wiring
ROLES = {"t": {"res": {"a": "x.a"}}}


def _node(**over):
    n = {"tool": "t", "body": {"f": "b_n1_f"}, "res": {"a": "r_n1_a"}, "res_leaf": {"a": "x.a"}}
    n.update(over)
    return n


@pytest.mark.parametrize("node,compact", [
    (_node(), True),
    (_node(body={"f": "something_else"}), False),        # body not b_<node>_<field>
    (_node(res={"a": "r_other_a"}), False),              # res not r_<node>_<role>
    (_node(res_leaf={"a": "y.a"}), False),               # res_leaf differs from the catalog roles
    (_node(extra=1), False),                             # any other key keeps the node explicit
])
def test_compact_wiring_only_touches_conventional_nodes(node, compact):
    w = {"roles": ROLES, "nodes": {"n1": node}}
    out = bundle.compact_wiring(w)
    if compact:
        assert out["nodes"]["n1"] == {"tool": "t", "bf": ["f"]}
    else:
        assert out["nodes"]["n1"] == node
    assert w["nodes"]["n1"] == node                       # input never mutated


def test_make_snippet_compact_true_embeds_compacted_wiring(tmp_path, monkeypatch):
    _use(monkeypatch, tmp_path, {"brain": MAIN % "len(rspec)"})
    rs = {"v": 1, "wiring": {"roles": ROLES, "nodes": {"n1": _node()}}}
    snip = bundle.make_snippet(rs, compact=True)
    hexs = re.search(r"^RSPEC_HEX = '([0-9a-f]+)'$", snip, re.M).group(1)
    embedded = json.loads(bytes.fromhex(hexs).decode("ascii"))
    assert embedded["wiring"]["nodes"]["n1"] == {"tool": "t", "bf": ["f"]}
    assert rs["wiring"]["nodes"]["n1"] == _node()          # caller's rspec untouched
    v = {}
    exec(snip, {"vars": v})
    assert v["nx"] == str(len(snip.split("RSPEC_HEX = '")[1].split("'")[0]))


def test_make_snippet_rejects_code_that_does_not_compile(monkeypatch):
    # a bundle that does not compile is reported instead of shipping a broken ctl node
    monkeypatch.setattr(bundle, "bundle_source", lambda minify=True: "def broken(:\n")
    with pytest.raises(bundle.BundleError, match="does not compile"):
        bundle.make_snippet({"v": 1})


def test_minified_fstring_keeps_escaped_braces():
    assert bundle._minify('X = f"a{{b}}c{x}"\n') == 'X=f"a{{b}}c{x}"'
    assert bundle._minify('X = f"{x}"\n') == 'X=f"{x}"'


def test_minified_bundle_rejects_double_brace_fstring_like_plain(tmp_path, monkeypatch):
    _use(monkeypatch, tmp_path, {"brain": "b = 1\n" + MAIN % "f\"a{{b}}c\""})
    with pytest.raises(bundle.BundleError):
        bundle.bundle_source(minify=False)
    with pytest.raises(bundle.BundleError):
        bundle.bundle_source(minify=True)


# ------------------------------------------------------------------ pack_snippet size guard
def test_pack_snippet_size_guard(monkeypatch):
    packed = bundle.pack_snippet("vars['nx'] = 'ok'\n")
    v = {}
    exec(packed, {"vars": v})
    assert v["nx"] == "ok"
    assert bundle.unpack_snippet(packed) == "vars['nx'] = 'ok'\n"
    assert bundle.unpack_snippet("x = 1\n") == "x = 1\n"         # not packed -> returned as is
    monkeypatch.setattr(bundle, "PACK_MAX_BYTES", 100)
    with pytest.raises(bundle.BundleError, match="packed snippet is"):
        bundle.pack_snippet("vars['nx'] = 'ok'\n")
