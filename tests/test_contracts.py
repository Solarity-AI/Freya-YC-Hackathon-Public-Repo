"""Contract tests (lead-owned): golden Specs, shared fixtures, skeleton imports, brief leakage."""
import importlib
import json
import pathlib
import re

import jsonschema
import pytest

from builder.spec import vocab

ROOT = pathlib.Path(__file__).resolve().parent.parent
GOLDEN = ["spec-a.json", "spec-ab.json"]


def _spec(name):
    return json.loads((ROOT / "tests" / "golden" / name).read_text())


def _openapi():
    return json.loads((ROOT / "kit" / "tools" / "openapi.json").read_text())


def _enum(oa, path, field, where="request"):
    op = oa["paths"][path]["post"]
    if where == "request":
        return op["requestBody"]["content"]["application/json"]["schema"]["properties"][field].get("enum", [])
    return op["responses"]["200"]["content"]["application/json"]["schema"]["properties"][field].get("enum", [])


def test_schema_is_valid_draft(schema):
    jsonschema.Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize("name", GOLDEN)
def test_golden_validates_against_schema(schema, name):
    errs = sorted(jsonschema.Draft202012Validator(schema).iter_errors(_spec(name)), key=lambda e: list(e.path))
    assert not errs, "\n".join(f"{list(e.path)}: {e.message}" for e in errs[:20])


def _situation_refs(spec):
    refs = set()

    def walk(x):
        if isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            refs.update(re.findall(r"S_[A-Z][A-Z0-9_]*", x))
    walk({k: v for k, v in spec.items() if k not in ("meta", "situations")})
    return refs


@pytest.mark.parametrize("name", GOLDEN)
def test_golden_enum_bindings_match_kit_openapi(name):
    spec, oa = _spec(name), _openapi()
    outcomes = _enum(oa, "/close_call", "outcome")
    queues = _enum(oa, "/transfer_to_agent", "queue")
    note_reasons = _enum(oa, "/add_note", "reason")
    fields = _enum(oa, "/verify_identity", "field")
    hints = _enum(oa, "/verify_identity", "hint", where="response")
    types = oa["paths"]["/get_account"]["post"]["responses"]["200"]["content"]["application/json"]["schema"][
        "properties"]["products"]["items"]["properties"]["type"]["enum"]
    for sid, s in spec["situations"].items():
        assert s["outcome"] in outcomes, sid
        assert s["queue"] in queues + [""], sid
        assert s["note_reason"] in note_reasons + [""], sid
        if s["outcome"] in spec["outcomes"]["reasonless_outcomes"]:
            assert s["reason"] == "", sid
    for it in spec["intents"]:
        q = it["action"].get("queue")
        if q is not None:
            assert q in queues, it["id"]
    for q in spec["identity"]["questions"]:
        assert q["field_value"] in fields
    for h in spec["identity"]["hints"]:
        assert h["value"] in hints
    assert set(spec["products"]["types"]) <= set(types)


@pytest.mark.parametrize("name", GOLDEN)
def test_golden_referential_integrity(name):
    spec = _spec(name)
    missing = _situation_refs(spec) - set(spec["situations"])
    assert not missing, missing
    band_keys = {b["key"] for b in spec["bands"]}
    for r in spec["negotiation"]["ladder"]:
        assert r["bands"] == ["all"] or set(r["bands"]) <= band_keys, r["key"]
    ids = {i["id"] for i in spec["intents"]}
    assert set(spec["interpretation"]["intent_tie"]) <= ids
    for rs in spec["required_sentences"]:
        if rs["trigger"].startswith("on_intent:"):
            assert rs["trigger"].split(":", 1)[1] in ids


def _lines(spec):
    """Yield (pointer, text) for every Line-typed string we can find by key name."""
    def walk(x, ptr):
        if isinstance(x, dict):
            for k, v in x.items():
                yield from walk(v, ptr + "/" + str(k))
        elif isinstance(x, list):
            for i, v in enumerate(x):
                yield from walk(v, ptr + "/" + str(i))
        elif isinstance(x, str) and "<" in x and ">" in x:
            yield ptr, x
    yield from walk({k: v for k, v in spec.items() if k not in ("meta", "intents")}, "")
    for i, it in enumerate(spec["intents"]):
        for key in ("say", "question"):
            if key in it["action"]:
                yield f"/intents/{i}/action/{key}", it["action"][key]


@pytest.mark.parametrize("name", GOLDEN)
def test_golden_placeholders_closed(name):
    spec = _spec(name)
    declared = {d["name"] for d in spec["call_variables"]["declared"]}
    for ptr, text in _lines(spec):
        if ptr.endswith("/confirm_examples/3"):
            continue                                    # "<own name>" is an example, not a template
        for ph in re.findall(r"<([^<>]+)>", text):
            if ph.startswith("v:"):
                assert ph[2:] in declared, (ptr, ph)
            elif ph.startswith("f:"):
                continue
            else:
                assert ph in vocab.PLACEHOLDERS, (ptr, ph)


@pytest.mark.parametrize("name", GOLDEN)
def test_golden_pre_verification_lines_have_no_banned_words(name):
    spec = _spec(name)
    banned = [w.lower() for w in spec["banned"]["before_verification"]]
    pre = [spec["opening"]["line"], spec["right_party"]["ask"], spec["right_party"]["reask"]]
    pre += list(spec["right_party"]["answers"].values())
    tp = spec["third_party"]
    pre += [tp[k] for k in ("reach_ask", "reach_reask", "outside_line", "vague_line", "booked_line", "offer_to_pay_line")]
    idn = spec["identity"]
    for q in idn["questions"]:
        pre += [q["ask"], q["reask_wrong"], q["ask_full"]]
    pre += [h["say"] for h in idn["hints"]] + [idn["decline"]["explain"], idn["fail_line"]]
    for it in spec["intents"]:
        if set(it["scope"]) <= {"rp", "tp", "id"}:
            pre += [it["action"][k] for k in ("say", "question") if k in it["action"]]
    for line in pre:
        for w in banned:
            assert not re.search(r"\b" + re.escape(w) + r"\b", line.lower()), (w, line)


def test_catalog_fixture_matches_kit_openapi(catalog_kit):
    oa = _openapi()
    assert catalog_kit["server"] == oa["servers"][0]["url"].rstrip("/")
    assert set(catalog_kit["tools"]) == set(vocab.TOOLS)
    for name, t in catalog_kit["tools"].items():
        assert t["url"] == catalog_kit["server"] + "/" + name
        assert set(t["roles"]["response"]) <= set(vocab.RESPONSE_ROLES)
        assert set(t["roles"]["request"]) <= set(vocab.REQUEST_ROLES)
        for role, field in t["roles"]["request"].items():
            assert field in t["request"], (name, role)


@pytest.mark.parametrize("name,spec_name", [("wiring-a.json", "spec-a.json"), ("wiring-ab.json", "spec-ab.json")])
def test_wiring_fixture_consistent_with_spec(name, spec_name, catalog_kit):
    w = json.loads((ROOT / "tests" / "fixtures" / name).read_text())
    spec = _spec(spec_name)
    assert len(w["api"]["promise"]) == spec["products"]["max"]
    assert all(len(row) == spec["recording"]["tries"] for row in w["api"]["promise"])
    assert bool(w["api"]["note"]) == (spec["notes"]["enabled"] and spec["notes"]["scope"] == "product")
    for node, n in w["nodes"].items():
        assert n["tool"] in vocab.TOOLS
        assert all(v.startswith("b_" + node + "_") or v in ("co", "cr") for v in n["body"].values()), node
        assert all(v == "r_" + node + "_" + role for role, v in n["res"].items()), node
    assert "reason" not in w["nodes"]["a_close_n"]["body"]
    assert w["nodes"]["a_close_r"]["body"]["reason"] == "cr"


MODULES = [
    "builder.paths", "builder.spec.vocab", "builder.spec.defaults", "builder.build", "builder.llm", "builder.trace",
    "builder.budget", "builder.openapi_model", "builder.deploy", "builder.pipeline.segment", "builder.pipeline.extract",
    "builder.pipeline.validate", "builder.pipeline.critic", "builder.compiler.graph", "builder.compiler.render",
    "builder.compiler.snippet", "builder.compiler.lint", "runtime.cal", "runtime.parse", "runtime.ident",
    "runtime.brain", "runtime.bundle", "harness.twin", "harness.mockbank", "harness.scenarios", "harness.persona",
    "harness.chat_e2e",
]


@pytest.mark.parametrize("mod", MODULES)
def test_module_imports(mod):
    importlib.import_module(mod)


def test_runtime_sources_are_brace_safe_and_stdlib_only():
    for name in ("cal", "parse", "ident", "brain"):
        src = (ROOT / "runtime" / (name + ".py")).read_text()
        assert "{{" not in src and "}}" not in src, name
        for line in src.splitlines():
            m = re.match(r"^\s*(?:import|from)\s+([\w.]+)", line)
            if m and not m.group(1).startswith("."):
                assert m.group(1).split(".")[0] in ("json", "re", "datetime"), (name, line)


def test_defaults_lines_cover_all_slots():
    from builder.spec.defaults import DEFAULT_LINES, DEFAULT_INTERPRETATION
    assert set(DEFAULT_LINES) == set(vocab.LINE_SLOTS)
    schema = json.loads((ROOT / "builder" / "spec" / "schema.json").read_text())
    assert set(DEFAULT_INTERPRETATION) == set(schema["$defs"]["Interpretation"]["properties"])


# Tokens that exist only because of Brief A/B or the kit OpenAPI. None may appear in generic code.
LEAK_TOKENS = [
    "Freya Bank", "collections team", "credit_card", "personal_loan", "car_loan", "credit card", "personal loan",
    "car loan", "minimum_payment", "instalment_amount", "card_last4", "date_of_birth", "phone_last4",
    "day_month_swapped", "wrong_answers_left", "all_verified", "restructuring", "2026-10-26", "2026-11-11",
    "2026-11-26", "2026-12-25", "2027-01-01", "Do you confirm", "text message confirming", "sorry for your loss",
    "mobile app", "Daniel", "Reyes", "12th business day", "7th business day",
]


def test_no_brief_leakage():
    hits = []
    for top in ("builder", "runtime", "harness"):
        for p in (ROOT / top).rglob("*"):
            if p.suffix not in (".py", ".md", ".json", ".txt") or "__pycache__" in p.parts:
                continue
            text = p.read_text(errors="ignore")
            for tok in LEAK_TOKENS:
                if tok.lower() in text.lower():
                    hits.append(f"{p.relative_to(ROOT)}: {tok!r}")
    assert not hits, "\n".join(hits)
