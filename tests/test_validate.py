"""builder.pipeline.validate + spec.defaults.apply_defaults (agent 5).
Golden Specs must validate clean; each error class is provoked on a copy of golden A."""
import copy
import json
import pathlib

import pytest

from builder.pipeline import validate as V
from builder.spec import defaults as D

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRIEFS = (ROOT / "kit" / "briefs" / "brief-a.md").read_text() + "\n" + (ROOT / "kit" / "briefs" / "brief-b.md").read_text()


@pytest.fixture
def ga(golden_a):
    return copy.deepcopy(golden_a)


def run(spec, catalog, brief=BRIEFS):
    return V.validate(spec, catalog, brief_text=brief)


def has(errors, *parts):
    return any(all(p in e for p in parts) for e in errors)


# ----------------------------------------------------------------------------------------------- defaults

def test_apply_defaults_fills_missing_only():
    spec = {"lines": {"clarify": "Pardon?"}, "interpretation": {"hedged_time": "exact"},
            "right_party": {"max_asks": 3, "answers": {"who": "It's me."}}}
    out, applied = D.apply_defaults(spec)
    assert out["lines"]["clarify"] == "Pardon?" and out["lines"]["hold"] == D.DEFAULT_LINES["hold"]
    assert out["right_party"]["max_asks"] == 3 and out["right_party"]["answers"]["who"] == "It's me."
    assert out["right_party"]["answers"]["why"] == D.DEFAULTS["right_party"]["answers"]["why"]
    assert "/lines/hold" in applied and "/lines/clarify" not in applied
    assert "/right_party/answers/why" in applied and "/right_party/max_asks" not in applied
    assert "/interpretation/hedged_time" not in applied and "/interpretation/intent_tie" in applied
    assert applied == sorted(applied)


def test_apply_defaults_does_not_mutate_and_none_is_missing():
    spec = {"calendar": {"holidays": None, "business_weekdays": [6, 0, 1, 2, 3]}}
    snap = copy.deepcopy(spec)
    out, applied = D.apply_defaults(spec)
    assert spec == snap
    assert out["calendar"]["holidays"] == [] and out["calendar"]["business_weekdays"] == [6, 0, 1, 2, 3]
    assert "/calendar/holidays" in applied and "/calendar/business_weekdays" not in applied
    out["lines"]["hold"] = "changed"
    assert D.DEFAULT_LINES["hold"] != "changed"                  # defaults are deep-copied


def test_apply_defaults_keeps_present_lists_and_wrong_types():
    out, applied = D.apply_defaults({"required_sentences": [{"id": "x"}], "banned": "oops"})
    assert out["required_sentences"] == [{"id": "x"}] and out["banned"] == "oops"
    assert not any(a.startswith("/banned") for a in applied)


def test_apply_defaults_on_golden_is_noop(golden_a):
    out, applied = D.apply_defaults(golden_a)
    assert applied == [] and out == golden_a


def test_apply_defaults_non_dict():
    out, applied = D.apply_defaults(None)
    assert out["lines"] == D.DEFAULT_LINES and "/lines" in applied


# ----------------------------------------------------------------------------------------------- golden

@pytest.mark.parametrize("name", ["golden_a", "golden_ab"])
def test_golden_specs_validate_clean(name, request, catalog_kit):
    g = request.getfixturevalue(name)
    r = run(g, catalog_kit)
    assert r["errors"] == [] and r["warnings"] == [] and r["defaults_applied"] == [] and r["fixes"] == []
    body = {k: v for k, v in r["spec"].items() if k != "meta"}
    assert body == {k: v for k, v in g.items() if k != "meta"}
    assert r["spec"]["meta"]["openapi_sha256"] == catalog_kit["openapi_sha256"]


def test_validate_does_not_mutate_input(ga, catalog_kit):
    snap = copy.deepcopy(ga)
    ga["situations"]["S_PAID"]["outcome"] = "Paid"
    snap2 = copy.deepcopy(ga)
    run(ga, catalog_kit)
    assert ga == snap2 and snap != snap2


# ----------------------------------------------------------------------------------------------- fills

def test_missing_keys_filled_by_defaults_and_logged(ga, catalog_kit):
    del ga["lines"]
    del ga["interpretation"]
    del ga["products"]["fields"]
    r = run(ga, catalog_kit)
    assert r["errors"] == []
    assert "/lines" in r["defaults_applied"] and r["spec"]["lines"] == D.DEFAULT_LINES
    assert r["spec"]["products"]["fields"]["past_due"] == "past_due"
    assert r["spec"]["interpretation"]["intent_tie"] == [                       # derived from precedence
        "deceased", "wrong_number", "hardship", "restructure", "dispute", "paid", "human", "refuse_talk", "too_much"]
    assert "/lines" in r["spec"]["meta"]["defaults_applied"]
    assert any("intent_tie" in d for d in r["spec"]["meta"]["decisions"])


def test_nulls_stripped(ga, catalog_kit):
    ga["intents"][0]["action"]["queue"] = None
    ga["calendar"]["holidays"].append(None)
    r = run(ga, catalog_kit)
    assert r["errors"] == []
    assert "queue" not in r["spec"]["intents"][0]["action"] and None not in r["spec"]["calendar"]["holidays"]


def test_unknown_intent_tie_ids_dropped(ga, catalog_kit):
    ga["interpretation"]["intent_tie"].append("ghost")
    r = run(ga, catalog_kit)
    assert r["errors"] == [] and "ghost" not in r["spec"]["interpretation"]["intent_tie"]
    assert has(r["warnings"], "intent_tie", "ghost")


def test_reasonless_outcomes_derived_when_missing(ga, catalog_kit):
    del ga["outcomes"]["reasonless_outcomes"]
    r = run(ga, catalog_kit)
    assert r["spec"]["outcomes"]["reasonless_outcomes"] == ["paid", "promise"]


def test_transient_meta_removed(ga, catalog_kit):
    ga["meta"]["failed_facets"] = ["F2"]
    r = run(ga, catalog_kit)
    assert r["errors"] == [] and "failed_facets" not in r["spec"]["meta"]


# ----------------------------------------------------------------------------------------------- enum binding

def test_enum_spelling_normalised(ga, catalog_kit):
    ga["situations"]["S_DISPUTE"]["outcome"] = "No-Promise"
    ga["situations"]["S_RESTRUCTURE_TRANSFER"]["queue"] = "Restructuring Team"
    ga["intents"][3]["action"]["queue"] = "RESTRUCTURING"
    ga["identity"]["questions"][1]["field_value"] = "phone-last4"
    r = run(ga, catalog_kit)
    assert r["errors"] == []
    s = r["spec"]
    assert s["situations"]["S_DISPUTE"]["outcome"] == "no_promise"
    assert s["situations"]["S_RESTRUCTURE_TRANSFER"]["queue"] == "restructuring"
    assert s["intents"][3]["action"]["queue"] == "restructuring"
    assert s["identity"]["questions"][1]["field_value"] == "phone_last4"
    assert len(r["fixes"]) == 4 and all("match" in f for f in r["fixes"])


def test_enum_value_not_in_catalog_is_error(ga, catalog_kit):
    ga["situations"]["S_HUMAN_TRANSFER"]["queue"] = "legal"
    ga["situations"]["S_PAID"]["note_reason"] = "settled"
    ga["identity"]["hints"][0]["value"] = "swapped"
    r = run(ga, catalog_kit)
    assert has(r["errors"], "/situations/S_HUMAN_TRANSFER/queue", "transfer queue")
    assert has(r["errors"], "/situations/S_PAID/note_reason")
    assert has(r["errors"], "/identity/hints/0/value")
    assert V.facets_with_errors(r["errors"]) == ["F2", "F7"]          # situations live in F7 (facet split)


def test_product_type_keys_bound_and_missing_types_warned(ga, catalog_kit):
    t = ga["products"]["types"]
    t["Personal-Loan"] = t.pop("personal_loan")
    del t["car_loan"]
    r = run(ga, catalog_kit)
    assert r["errors"] == []
    assert "personal_loan" in r["spec"]["products"]["types"]
    assert has(r["warnings"], "/products/types", "car_loan")


def test_unknown_product_type_is_error(ga, catalog_kit):
    ga["products"]["types"]["boat_loan"] = {"spoken": "boat loan", "floor": {"kind": "full"}}
    assert has(run(ga, catalog_kit)["errors"], "/products/types/boat_loan")


def test_close_reason_enum_checked_when_catalog_has_one(ga, catalog_kit):
    cat = copy.deepcopy(catalog_kit)
    cat["enums"]["close_reason"] = ["refused", "dispute"]
    r = run(ga, cat)
    assert has(r["errors"], "/situations/S_CALLBACK/reason", "close reason")


def test_per_field_identity_mode(ga, catalog_kit):
    cat = copy.deepcopy(catalog_kit)
    cat["identity_mode"] = "per_field"
    vt = cat["tools"]["verify_identity"]
    vt["request"] = {"customer_id": vt["request"]["customer_id"], "dob": {"type": "string"}, "pin": {"type": "string"}}
    vt["roles"]["request"] = {"customer": "customer_id"}
    ga["identity"]["questions"][0]["field_value"] = "DOB"
    ga["identity"]["questions"][1]["field_value"] = "phone_last4"
    r = run(ga, cat)
    assert r["spec"]["identity"]["questions"][0]["field_value"] == "dob"
    assert has(r["errors"], "/identity/questions/1/field_value")


def test_reasonless_outcome_with_reason_is_error(ga, catalog_kit):
    ga["situations"]["S_PROMISE"]["reason"] = "full"
    assert has(run(ga, catalog_kit)["errors"], "/situations/S_PROMISE/reason", "reasonless")


# ----------------------------------------------------------------------------------------------- integrity

def test_undefined_situation(ga, catalog_kit):
    ga["right_party"]["on_unresolved"] = "S_NOBODY"
    r = run(ga, catalog_kit)
    assert has(r["errors"], "/right_party/on_unresolved", "S_NOBODY", "not defined")
    assert set(V.facets_with_errors(r["errors"])) == {"F1", "F5", "F7"}


def test_ladder_unknown_band(ga, catalog_kit):
    ga["negotiation"]["ladder"][1]["bands"] = ["middle"]
    r = run(ga, catalog_kit)
    assert has(r["errors"], "/negotiation/ladder/1/bands", "middle")
    assert V.facets_with_errors(r["errors"]) == ["F4"]


def test_duplicate_ids(ga, catalog_kit):
    ga["intents"].append(copy.deepcopy(ga["intents"][0]))
    ga["negotiation"]["ladder"].append(copy.deepcopy(ga["negotiation"]["ladder"][0]))
    r = run(ga, catalog_kit)
    assert has(r["errors"], "/intents", "duplicate") and has(r["errors"], "/negotiation/ladder", "duplicate")


def test_trigger_unknown_intent_and_per_situation(ga, catalog_kit):
    ga["required_sentences"].append({"id": "x", "text": "You will receive a text message confirming this promise.",
                                     "verbatim": True, "trigger": "on_intent:ghost", "once": True})
    ga["closing"]["per_situation"] = {"S_GHOST": "Bye."}
    r = run(ga, catalog_kit)
    assert has(r["errors"], "on_intent:ghost") and has(r["errors"], "/closing/per_situation/S_GHOST")


def test_undeclared_variables(ga, catalog_kit):
    ga["addressing"]["name_vars"] = ["first_name", "nickname"]
    ga["call_variables"]["now"] = "clock"
    r = run(ga, catalog_kit)
    assert has(r["errors"], "/addressing/name_vars", "nickname") and has(r["errors"], "/call_variables/now")


def test_amount_rule_field_must_be_product_leaf(ga, catalog_kit):
    ga["products"]["types"]["car_loan"]["floor"] = {"kind": "field", "field": "monthly_fee"}
    ga["negotiation"]["ladder"][0]["amount"] = {"kind": "max", "args": [{"kind": "field", "field": "bogus"},
                                                                         {"kind": "full"}]}
    r = run(ga, catalog_kit)
    assert has(r["errors"], "/products/types/car_loan/floor/field", "monthly_fee")
    assert has(r["errors"], "/negotiation/ladder/0/amount/args/0/field", "bogus")


# ----------------------------------------------------------------------------------------------- placeholders

def test_brace_vars_fixed_to_v_placeholders(ga, catalog_kit):
    ga["right_party"]["ask"] = "Am I speaking with {title} {{last_name}}?"
    ga["right_party"]["reask"] = "Is this {nobody}?"
    r = run(ga, catalog_kit)
    assert r["spec"]["right_party"]["ask"] == "Am I speaking with <v:title> <v:last_name>?"
    assert any("{var}" in f for f in r["fixes"])
    assert r["spec"]["right_party"]["reask"] == "Is this {nobody}?"


def test_unknown_and_undeclared_placeholders(ga, catalog_kit):
    ga["statement"]["item"] = "Your <thing> is <days_late> days late, with <past_due> past due."
    ga["third_party"]["reach_ask"] = "When can I reach <v:nickname>?"
    ga["products"]["types"]["credit_card"]["spoken"] = "card ending <f:last_digits>"
    ga["lines"]["hold"] = "Hold on {{x}}."
    r = run(ga, catalog_kit)
    assert has(r["errors"], "/statement/item", "unknown placeholder <thing>")
    assert has(r["errors"], "/third_party/reach_ask", "v:nickname")
    assert has(r["errors"], "/products/types/credit_card/spoken", "f:last_digits")
    assert has(r["errors"], "/lines/hold", "braces")


def test_runtime_placeholder_in_compile_time_line(ga, catalog_kit):
    ga["opening"]["line"] = "Hello from <bank> about <product>."
    ga["right_party"]["ask"] = "Is this <customer>, card <f:card_last4>?"
    r = run(ga, catalog_kit)
    assert has(r["errors"], "/opening/line", "<product>")
    assert has(r["errors"], "/right_party/ask", "<f:")


def test_addressing_only_v_placeholders(ga, catalog_kit):
    ga["addressing"]["customer"] = "<v:title> <customer>"
    assert has(run(ga, catalog_kit)["errors"], "/addressing/customer")


def test_examples_are_not_templates(ga, catalog_kit):
    ga["intents"][0]["examples"].append("He's <gone>")
    assert run(ga, catalog_kit)["errors"] == []


# ----------------------------------------------------------------------------------------------- banned words

def test_banned_word_in_pre_verification_lines(ga, catalog_kit):
    ga["identity"]["questions"][0]["ask"] = "To discuss your debt, what is your date of birth?"
    ga["third_party"]["reach_ask"] = "When can I reach <customer> about the Payment?"
    ga["intents"][0]["action"]["say"] = "Sorry, we will close the card."             # deceased: scope rp/tp
    r = run(ga, catalog_kit)
    assert has(r["errors"], "/identity/questions/0/ask", "debt")
    assert has(r["errors"], "/third_party/reach_ask", "payment")
    assert has(r["errors"], "/intents/0/action/say", "card")
    assert set(V.facets_with_errors(r["errors"])) == {"F1", "F2", "F5"}


def test_banned_word_in_lines_the_lint_reads_is_a_validation_error(ga, catalog_kit):
    """An intent spoken before AND after verification, and the generic hold line, are spoken before verification:
    the lint fails the build on their banned words (exit 4), so validation reports them first, where the targeted
    re-extraction can still rewrite the line."""
    assert set(ga["intents"][10]["scope"]) > {"rp", "id"}                 # scam: rp, tp, id, neg, conf
    ga["intents"][10]["action"]["say"] = "We will never ask for your full card number."
    ga["lines"]["hold"] = "One moment while I look at your balance."
    ga["intents"][4]["action"]["say"] = "I understand, the card stays as it is."       # neg/conf only: allowed
    r = run(ga, catalog_kit)
    assert has(r["errors"], "/intents/10/action/say", "card")
    assert has(r["errors"], "/lines/hold", "balance")
    assert not any(e.startswith("/intents/4/") for e in r["errors"])
    assert len([e for e in r["errors"] if e.startswith("/intents/10/action/say")]) == 1
    assert set(V.facets_with_errors(r["errors"])) >= {"F1", "F5"}


def test_banned_word_whole_word_only(ga, catalog_kit):
    ga["third_party"]["reach_ask"] = "When is a good time to call <customer>? Tomorrow is fine, no lateness."
    ga["right_party"]["answers"]["other"] = "I need to know who I am speaking with; my cardigan is irrelevant."
    assert run(ga, catalog_kit)["errors"] == []


def test_post_verification_lines_may_use_banned_words(ga, catalog_kit):
    ga["statement"]["intro"] = "I am calling about a late payment on your card."
    assert run(ga, catalog_kit)["errors"] == []


def test_sentence_for_pre_verification_situation_checked(ga, catalog_kit):
    # S_DECEASED is pre-verification (a line the brief itself dictates would un-ban its word: use another text)
    ga["required_sentences"][1]["text"] = "We are sorry about the loss."
    ga["banned"]["before_verification"].append("loss")
    assert has(run(ga, catalog_kit)["errors"], "/required_sentences/1/text", "loss")


# ----------------------------------------------------------------------------------------------- bands, verbatim

def test_band_overlap_gap_inverted(ga, catalog_kit):
    ga["bands"][1]["days_late_min"] = 7
    r = run(ga, catalog_kit)
    assert has(r["errors"], "/bands", "overlap")
    ga["bands"][1]["days_late_min"] = 10
    r = run(ga, catalog_kit)
    assert r["errors"] == [] and has(r["warnings"], "gap", "8-9")
    ga["bands"][0]["days_late_min"] = 9
    assert has(run(ga, catalog_kit)["errors"], "/bands/0", "days_late_min > days_late_max")


def test_attempts_without_rungs_warned(ga, catalog_kit):
    ga["bands"][1]["attempts"] = 3
    assert has(run(ga, catalog_kit)["warnings"], "/bands/1/attempts", "only 2")


def test_verbatim_sentence_must_be_in_brief(ga, catalog_kit):
    ga["required_sentences"][0]["text"] = "You will get an SMS about this."
    r = run(ga, catalog_kit)
    assert has(r["errors"], "/required_sentences/0/text", "verbatim")
    assert run(ga, catalog_kit, brief=None)["errors"] == []                # no brief -> check skipped


def test_verbatim_question_not_in_brief_warns(ga, catalog_kit):
    ga["confirmation"]["question"] = "Is that all correct?"
    assert has(run(ga, catalog_kit)["warnings"], "/confirmation/question")


def test_invalid_keyword_regex_and_missing_keywords(ga, catalog_kit):
    ga["intents"][0]["keywords"] = ["(unclosed"]
    ga["intents"][1]["keywords"] = []
    r = run(ga, catalog_kit)
    assert has(r["errors"], "invalid regex") and has(r["warnings"], "wrong_number", "no keywords")


# ----------------------------------------------------------------------------------------------- schema / facets

def test_missing_facet_keys_map_to_facets(ga, catalog_kit):
    for k in ("identity", "bands", "negotiation"):
        del ga[k]
    r = run(ga, catalog_kit)
    assert has(r["errors"], "/identity", "required property")
    assert V.facets_with_errors(r["errors"]) == ["F2", "F3", "F4"]


def test_schema_type_errors_have_pointers(ga, catalog_kit):
    ga["right_party"]["max_asks"] = "two"
    ga["bands"][0]["deadline"] = {"kind": "fortnight"}
    r = run(ga, catalog_kit)
    assert has(r["errors"], "/right_party/max_asks", "schema") and has(r["errors"], "/bands/0/deadline/kind")
    assert V.facets_with_errors(r["errors"]) == ["F1", "F3"]


def test_facets_with_errors_edge_inputs():
    assert V.facets_with_errors([]) == [] and V.facets_with_errors(None) == []
    assert V.facets_with_errors(["garbage", "/interpretation/x: bad", "/lines/hold: x"]) == ["F5", "F6"]


def test_bind_enum_helper():
    assert V.bind_enum("x", []) == ("x", "free")
    assert V.bind_enum("Not Reached", ["not_reached"]) == ("not_reached", "normalised")
    assert V.bind_enum("support team", ["support", "general"]) == ("support", "loose")
    assert V.bind_enum("care", ["support"]) == (None, "none")


def test_validate_survives_garbage(catalog_kit):
    r = V.validate({"bands": "x", "intents": [1, None, {"id": 3}], "situations": []}, catalog_kit)
    assert r["errors"] and isinstance(r["spec"], dict)
    r = V.validate(None, catalog_kit)
    assert r["errors"]
    json.dumps(r["spec"])


# ----------------------------------------------------------------------------------------------- code fills (e2e findings)

def test_note_reason_filled_from_reason_or_outcome(ga, catalog_kit):
    for sid in ("S_PAID", "S_DISPUTE", "S_REFUSED_EXHAUSTED", "S_SERVICE_ERROR"):
        ga["situations"][sid]["note_reason"] = ""
    r = run(ga, catalog_kit)
    s = r["spec"]["situations"]
    assert s["S_PAID"]["note_reason"] == "paid"                     # from the outcome (reasonless)
    assert s["S_DISPUTE"]["note_reason"] == "dispute" and s["S_SERVICE_ERROR"]["note_reason"] == "service_error"
    assert s["S_HUMAN_TRANSFER"]["note_reason"] == ""               # 'human' / 'transferred' are no note reasons
    assert s["S_ID_FAILED"]["note_reason"] == ""
    assert sum("note_reason" in f for f in r["fixes"]) == 4


def test_transfer_intents_never_before_verification(ga, catalog_kit):
    human = next(i for i, it in enumerate(ga["intents"]) if it["id"] == "human")
    paid = next(i for i, it in enumerate(ga["intents"]) if it["id"] == "paid")
    ga["intents"][human]["scope"] = ["rp", "tp", "id", "neg", "conf"]
    ga["intents"][paid]["scope"] = ["id", "neg"]
    r = run(ga, catalog_kit)
    assert r["errors"] == []
    assert r["spec"]["intents"][human]["scope"] == ["id", "neg", "conf"]
    assert r["spec"]["intents"][paid]["scope"] == ["neg"]
    assert sum("structural guard" in f for f in r["fixes"]) == 2
    rt = next(i for i, it in enumerate(ga["intents"]) if it["id"] == "refuse_talk")
    ga["intents"][rt]["scope"] = ["rp", "id", "neg"]
    assert run(ga, catalog_kit)["spec"]["intents"][rt]["scope"] == ["id", "neg"]


def test_transfer_intent_only_pre_verification_is_error(ga, catalog_kit):
    i = next(i for i, it in enumerate(ga["intents"]) if it["id"] == "restructure")
    ga["intents"][i]["scope"] = ["rp"]
    assert has(run(ga, catalog_kit)["errors"], "/intents/%d/scope" % i)


def test_example_values_never_baked_in(ga, catalog_kit):
    from builder.pipeline import segment
    ex = segment.segment([str(ROOT / "kit" / "briefs" / "brief-a.md")])["examples"]
    assert run(ga, catalog_kit)["errors"] == [] and V.validate(ga, catalog_kit, BRIEFS, ex)["errors"] == []
    ga["right_party"]["ask"] = "Am I speaking with %s?" % ex[1]
    ga["calendar"]["holidays"].append(ex[-1][:10])
    errs = V.validate(ga, catalog_kit, BRIEFS, ex)["errors"]
    assert has(errs, "/right_party/ask", "example value") and has(errs, "/calendar/holidays", "example 'now'")


def test_validator_never_crashes_on_shapes(catalog_kit):
    for junk in ({"bands": "x", "intents": [1, None, {"id": 3}], "situations": []},
                 {"identity": {"questions": [1, "a"], "hints": "x", "decline": 3}, "situations": {"S_A": 5},
                  "negotiation": {"ladder": [3]}, "required_sentences": [1], "closing": [],
                  "addressing": {"name_vars": [1], "customer": 5}, "right_party": {"answers": [1]}, "outcomes": [],
                  "banned": {"before_verification": "x"}, "third_party": {"situations": [1]}}):
        r = V.validate(junk, catalog_kit, BRIEFS, ["Someone"])
        assert r["errors"] and not any("crashed" in e for e in r["errors"])


def test_r1_example_value_also_written_in_a_rule_is_only_a_warning(ga, catalog_kit, tmp_path):
    # review fix round 1: a product label that the brief writes in a rule is a legitimate constant
    brief = (ROOT / "kit" / "briefs" / "brief-a.md").read_text()
    brief = brief.replace("| `now` |", "| `product_label` | `personal loan` | Spoken product name. |\n| `now` |", 1)
    p = tmp_path / "brief.md"
    p.write_text(brief)
    from builder.pipeline import segment
    ex = segment.segment([str(p)])["examples"]
    assert "personal loan" in ex
    r = V.validate(ga, catalog_kit, brief, ex)
    assert not has(r["errors"], "personal loan") and has(r["warnings"], "personal loan")
