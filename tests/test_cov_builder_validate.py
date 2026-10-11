"""Coverage round (builder/pipeline/validate.py + a few lint partial branches): catalog helpers without an account
tool, line pointer walks, brace fixes in lists, validator crash guard, examples without brief text."""
import copy
import json
import pathlib

import pytest

from builder import openapi_model as om
from builder.compiler import graph, lint
from builder.pipeline import validate as V

ROOT = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def ga():
    return json.loads((ROOT / "tests" / "golden" / "spec-a.json").read_text())


def test_catalog_helpers_without_an_account_tool():
    cat = {"tools": {"t": {"roles": {"response": {"s": "ok"}}}}}
    assert V.tool_by_response_role(cat, "products") == (None, None)
    assert V.product_fields(cat) is None and V.product_leaves(cat) == set()
    assert V.identity_values({"identity_mode": "per_field", "enums": {"identity_field": ["x"]}}) == ["x"]


def test_identity_values_per_field_uses_request_fields(catalog_kit):
    c = copy.deepcopy(catalog_kit)
    c["identity_mode"] = "per_field"
    assert V.identity_values(c) == ["field", "answer"]                # every request field except the customer


def test_line_pointers_clamp_line_and_notes_text():
    ptrs = dict(V._line_pointers({"multi_product": {"clamp_line": "Clamp <deadline>."},
                                  "notes": {"text": "Call note."}}))
    assert ptrs["/multi_product/clamp_line"] == "Clamp <deadline>." and ptrs["/notes/text"] == "Call note."
    ptrs2 = dict(V._line_pointers({"multi_product": {"clamp_line": 5}, "notes": {"text": ""}}))
    assert "/multi_product/clamp_line" not in ptrs2 and "/notes/text" not in ptrs2


def test_pre_verification_lines_include_only_pre_verification_situation_sentences():
    spec = {"identity": {"on_failed": "S_FAIL"},
            "required_sentences": [{"trigger": "on_situation:S_FAIL", "text": "Early."},
                                   {"trigger": "on_situation:S_LATE", "text": "Late."},
                                   {"trigger": "after_promise_recorded", "text": "Promise."}]}
    lines = V.pre_verification_lines(spec)
    assert ("/required_sentences/0/text", "Early.") in lines
    assert all(t not in ("Late.", "Promise.") for _, t in lines)


def test_brace_vars_fixed_inside_lists():
    spec = {"x": ["Hello {title}", "Keep {unknown}", 3, {"y": "Dear {{title}}"}]}
    fixes = []
    V._fix_brace_vars(spec, {"title"}, fixes)
    assert spec["x"][0] == "Hello <v:title>" and spec["x"][1] == "Keep {unknown}"
    assert spec["x"][3]["y"] == "Dear <v:title>"
    assert fixes == ["/x/0: {var} -> <v:var>", "/x/3/y: {var} -> <v:var>"]


def test_bind_empty_value_is_untouched():
    errors, fixes = [], []
    assert V._bind("", ["a"], "/p", errors, fixes, "queue") == ""
    assert V._bind(None, ["a"], "/p", errors, fixes, "queue") is None
    assert errors == [] and fixes == []


def test_validator_crash_is_an_error_not_an_exception(monkeypatch, catalog_kit):
    def boom(*a, **k):
        raise ZeroDivisionError("bad day")
    monkeypatch.setattr(V, "_validate", boom)
    r = V.validate({"a": 1}, catalog_kit)
    assert r["errors"] == ["/: validator crashed: bad day"] and r["spec"] == {"a": 1}
    assert V.validate("junk", catalog_kit)["spec"] == {}


def test_non_dict_meta_and_catalog_without_sha_or_note_enum(ga, catalog_kit):
    ga["meta"] = "not a dict"
    c = copy.deepcopy(catalog_kit)
    c.pop("openapi_sha256", None)
    c["enums"]["note_reason"] = []
    for sv in ga["situations"].values():
        if "note_reason" in sv:
            sv["note_reason"] = ""
    r = V.validate(ga, c)
    assert isinstance(r["spec"]["meta"], dict) and "openapi_sha256" not in r["spec"]["meta"]
    assert all(sv.get("note_reason", "") == "" for sv in r["spec"]["situations"].values())


def test_duplicate_identity_question_keys(ga, catalog_kit):
    ga["identity"]["questions"].append(copy.deepcopy(ga["identity"]["questions"][0]))
    errs = V.validate(ga, catalog_kit)["errors"]
    assert "/identity/questions: duplicate question keys" in errs


def test_example_values_without_brief_text_are_errors(ga, catalog_kit):
    ga["right_party"]["ask"] = "Is this Zebulon Quark?"
    errs = V.validate(ga, catalog_kit, brief_text=None, examples=["Zebulon Quark", "ab"])["errors"]
    assert any(e.startswith("/right_party/ask: contains the brief's example value 'Zebulon Quark'") for e in errs)


def test_facets_with_errors_ignores_unknown_top_keys():
    assert V.facets_with_errors(["/meta/x: odd", "/zzz: odd"]) == []
    assert V.facets_with_errors(["/interpretation/x: bad"]) == ["F5"]


# ------------------------------------------------------------------------------------------------ lint partials

STUB = "import json\nvars['nx'] = 's_safe'\n"


def test_lint_system_prompt_with_written_variable_and_valid_per_field_question():
    cat = om.load(ROOT / "kit" / "tools" / "openapi.json")
    spec = json.loads((ROOT / "tests" / "golden" / "spec-a.json").read_text())
    wf, w = graph.compile_workflow(spec, cat, code=STUB)
    wf["system_prompt"] += " The customer is {{customer_id}}."
    out = lint.lint(wf, cat, spec, w, stable=False)
    assert not [f for f in out if f["rule"] == "var_writer"]
    c = copy.deepcopy(cat)
    c["identity_mode"] = "per_field"
    spec["identity"]["questions"][0]["field_value"] = "answer"
    found = []
    lint._lint_spec_enums(spec, c, found)
    wheres = [f["where"] for f in found if f["rule"] == "spec_enum"]
    assert "/identity/questions/0/field_value" not in wheres and "/identity/questions/1/field_value" in wheres


# ------------------------------------------------------------------------------------------------ segment

def test_guess_kind_policy_memo_is_mixed_and_memo_alone():
    from builder.pipeline import segment
    assert segment.guess_kind("Internal memo\nThe collections policy changed.", []) == "mixed"
    assert segment.guess_kind("Memo\nNothing else.", []) == "memo"
    assert segment.guess_kind("A policy without a memo or a mail.", []) == "brief"


def test_expand_paths_skips_dotfiles_and_folders(tmp_path):
    from builder.pipeline import segment
    d = tmp_path / "mat"
    (d / "sub").mkdir(parents=True)
    (d / ".hidden.md").write_text("secret")
    (d / "sub" / "a.md").write_text("A")
    (d / "b.txt").write_text("B")
    (d / "pic.png").write_bytes(b"\x89PNG")
    got = segment.expand_paths([str(d)])
    assert got == [str(d / "b.txt"), str(d / "sub" / "a.md")]
