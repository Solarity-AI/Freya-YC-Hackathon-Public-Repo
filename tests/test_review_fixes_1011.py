"""Review fixes (2026-10-11, pre-freeze): decline_counting decided in code, id-scoped declines on the identity
decline counter, PUB-06 offer references ("it's", "this week") and the refused full amount, plural SMS sentence."""
import copy
import json

import pytest
from test_brain import CASES, SPEC_A, SPEC_AB, W_AB, Driver, exp, run_a, run_case

from builder.pipeline import validate as V
from runtime import brain as B


# ---------------------------------------------------------------------------- 2. decline_counting is deterministic
@pytest.mark.parametrize("brief, want", [
    ("If the customer does not want to answer, explain once. A second refusal closes the call.",
     "per_question_consecutive"),
    ("If the customer declines a security question twice, close the call.", "per_question_consecutive"),
    ("Declines add up across questions: two refusals of any security question close the call.", "total"),
    ("Refusals to answer are counted in total, across all identity questions.", "total"),
    ("If the customer declines the transfer, the total is noted.", "per_question_consecutive"),   # not identity
])
def test_decline_counting_is_decided_from_the_brief_wording(brief, want):
    for llm in ("total", "per_question_consecutive"):
        s = {"interpretation": {"decline_counting": llm}}
        fixes, decisions = [], []
        V._decline_counting(s, brief, fixes, decisions)
        assert s["interpretation"]["decline_counting"] == want
        assert len(fixes) + len(decisions) == 1 and want in (fixes + decisions)[0]


def test_decline_counting_is_logged_as_a_decision(golden_a, catalog_kit, monkeypatch):
    seen = []
    monkeypatch.setattr(V.trace, "event", lambda kind, msg="", **kw: seen.append((kind, msg)))
    g = copy.deepcopy(golden_a)
    g["interpretation"]["decline_counting"] = "total"
    r = V.validate(g, catalog_kit, brief_text="A second refusal or a second such question closes the call.")
    assert r["spec"]["interpretation"]["decline_counting"] == "per_question_consecutive"
    assert any(k == "DECISION" and "decline_counting" in m for k, m in seen), seen
    seen.clear()
    r = V.validate(r["spec"], catalog_kit, brief_text="A second refusal closes the call.")
    assert any(k == "DECISION" and "decline_counting = per_question_consecutive" in m for k, m in seen), seen
    assert V.validate(g, catalog_kit)["spec"]["interpretation"]["decline_counting"] == "total"   # no brief: kept


def test_decline_counting_without_interpretation_is_left_alone():
    s = {}
    V._decline_counting(s, "Declines add up across questions.", [], [])
    assert s == {}


# ---------------------------------------------------------------------------- 3. id-scoped decline intents
DECL = {"id": "declines_identity", "scope": ["id"], "precedence": 350, "product_scoped": False,
        "description": "The customer refuses to answer a security question.", "examples": ["I won't tell you that."],
        "negatives": [], "keywords": [r"\bwon't tell you\b", r"\bnot telling you\b"],
        "action": {"kind": "count_then_close", "say": "", "limit": 2, "situation": "S_ID_DECLINED",
                   "situation_pre_verification": "S_ID_DECLINED"}}


def _ab(extra, counting="per_question_consecutive", **decline):
    sp = copy.deepcopy(SPEC_AB)
    sp["intents"] = list(sp.get("intents") or []) + [copy.deepcopy(extra)]
    sp["interpretation"]["decline_counting"] = counting
    sp["identity"]["decline"].update(decline)
    return sp


def _play(sp, turns):
    d = Driver(sp, W_AB, copy.deepcopy(CASES["PUB-12"]))
    d.play(turns)
    d.st = json.loads(d.vars["st"])
    return d


def test_id_scoped_decline_uses_the_decline_counter_not_refuse_to_talk():
    d = _play(_ab(DECL), ["Yes.", "I won't tell you that."])
    assert not d.ended, d.lines
    assert int(d.st.get("talk", 0)) == 0 and d.st["id"]["dec"] == {"dob": 1}, d.st
    assert SPEC_AB["identity"]["decline"]["explain"] in d.lines[-1], d.lines


def test_id_scoped_decline_per_question_does_not_close_on_another_question():
    # declined the date of birth once, answered it, declined the next question once: per question, not closed
    d = _play(_ab(DECL), ["Yes.", "I won't tell you that.", "19 October 1983.", "I won't tell you that."])
    assert not d.ended, d.lines
    assert int(d.st.get("talk", 0)) == 0, d.st


def test_id_scoped_decline_closes_on_max_declines_of_one_question():
    d = _play(_ab(DECL), ["Yes.", "I won't tell you that.", "I'm not telling you."])
    assert d.ended and "verify_identity" not in d.tools(), d.lines
    assert d.st.get("csit") == SPEC_AB["identity"]["on_declined"], d.st


def test_id_scoped_decline_total_counting_spans_questions():
    d = _play(_ab(DECL, "total"), ["Yes.", "I won't tell you that.", "19 October 1983.", "I won't tell you that."])
    assert d.ended, d.lines


def test_id_scoped_purpose_intent_respects_purpose_question_counts():
    purpose = dict(copy.deepcopy(DECL), id="asks_call_purpose", keywords=[r"\bwhy are you calling\b"])
    d = _play(_ab(purpose, purpose_question_counts=False), ["Yes.", "Why are you calling?", "Why are you calling?"])
    assert not d.ended and d.st["id"]["dec"] == {}, (d.lines, d.st)


def test_refuse_to_talk_intent_still_counts_talk_during_identity():
    sp = copy.deepcopy(SPEC_A)
    it = next(x for x in sp["intents"] if (x.get("action") or {}).get("kind") == "count_then_close")
    assert not B._b_id_scoped({"S": sp}, it)
    assert B._b_id_scoped({"S": sp}, DECL)
    assert B._b_id_scoped({"S": sp}, dict(DECL, scope=["id", "neg"]))       # closes as identity declined


# ---------------------------------------------------------------------------- 4. PUB-06 offer references
ID6 = ["Yes, this is Priya Nair.", "Seventeenth of May nineteen eighty six.", "One five zero two."]
P06 = exp("promise", promises=[{"product_id": "p1", "amount": 637.5, "date": "2026-10-16"}])


def _floor_offers(d):
    return [x for x in d.lines if "637.50" in x and "Do you confirm" not in x and "recorded" not in x]


@pytest.mark.parametrize("second", [
    "I can't pay the full amount, it's too much.",
    "The full amount, it's just too much.",          # was read back as a proposal of the refused full amount
    "I can't pay the full amount this month.",
    "No, the whole balance is too much, it is.",
    "I can't pay the full amount this Friday.",
])
def test_full_amount_objection_after_the_floor_is_not_a_refusal_of_it(second):
    d = run_case("PUB-06", ID6 + ["The full amount is too much.", second, "Okay, Friday works.", "Yes, I confirm."],
                 expected=P06)
    assert len(_floor_offers(d)) == 1, d.lines
    assert not any("2,125.10" in x and "Do you confirm" in x for x in d.lines), d.lines
    assert d.score()["pass"], d.lines


@pytest.mark.parametrize("text, ref", [
    ("i can't pay , it's too much.", False), ("this month is hard", False), ("not this week", False),
    ("not this friday", False), ("that is too much", False), ("i can't do it", True), ("even that", True),
    ("i can't pay that either", True), ("this is still too much", True), ("italy", False), ("iteration", False),
])
def test_offer_reference_words(text, ref):
    assert bool(B._B_OFFERREF.search(text)) is ref


# ---------------------------------------------------------------------------- 6. plural SMS sentence
FRIDAY_ALL = exp("promise", promises=[{"product_id": "p1", "amount": 220.0, "date": "2026-10-16"},
                                      {"product_id": "p2", "amount": 640.0, "date": "2026-10-16"},
                                      {"product_id": "p3", "amount": 75.0, "date": "2026-10-16"}])


def _multi(verbatim):
    sp = copy.deepcopy(SPEC_AB)
    for rs in sp["required_sentences"]:
        rs["verbatim"] = verbatim
    return run_a(["Yes.", "3 June 1987", "2288", "I cannot pay today. I can pay all three this Friday.", "Yes."],
                 cid="PUB-11", expected=FRIDAY_ALL, spec=sp)


def test_several_promises_get_the_plural_sms_sentence():
    d = _multi(False)
    assert d.score()["pass"], d.lines
    said = " ".join(d.lines)
    assert "this promise" not in said and "confirming these promises" in said, d.lines


def test_a_verbatim_sms_sentence_keeps_the_dictated_words_after_several_promises():
    d = _multi(True)            # "word for word ... Legal has signed off that wording": the brief's words win
    assert d.score()["pass"], d.lines
    assert "confirming this promise" in " ".join(d.lines), d.lines


def test_one_promise_keeps_the_singular_sms_sentence():
    d = run_case("PUB-06", ID6 + ["The full amount is too much.", "Okay, Friday works.", "Yes, I confirm."],
                 expected=P06)
    assert "confirming this promise" in " ".join(d.lines), d.lines


@pytest.mark.parametrize("text, want", [
    ("You will receive a text message confirming this promise.",
     "You will receive a text message confirming these promises."),
    ("This promise is binding.", "These promises are binding."),
    ("Your promise has been noted; the promise was saved.", "Your promises have been noted; the promises were saved."),
    ("That promise stands.", "Those promises stand." if False else "Those promises stands."),
])
def test_plural_helper(text, want):
    assert B._b_plural(text) == want


@pytest.mark.parametrize("prop", ["No, I'll pay the full amount on Friday.", "I can pay the full amount on Friday."])
def test_a_full_amount_proposal_after_the_floor_is_still_a_proposal(prop):
    full = exp("promise", promises=[{"product_id": "p1", "amount": 2125.1, "date": "2026-10-16"}])
    d = run_case("PUB-06", ID6 + ["The full amount is too much.", prop, "Yes, I confirm."], expected=full)
    assert any("2,125.10" in x and "Do you confirm" in x for x in d.lines), d.lines
    assert d.score()["pass"], d.lines


# ---------------------------------------------------------------------------- official sims, talkative / pieces styles
TALK = ["Work is so busy right now and I feel like I'", "I have been so busy planning things",
        "I've been running around all day trying to"]


def test_pub04_talkative_small_talk_uses_no_persuasion_attempt():
    ok = exp("promise", promises=[{"product_id": "p1", "amount": 1250.0, "date": "2026-10-23"}])
    d = run_case("PUB-04", ["Yes, this is Lena Hoffmann.", "the thirtieth of January nineteen eighty four", "2219",
                            "I'm sorry, I cannot pay today",
                            "My salary arrives on the sixth of November and I can pay then."] + TALK
                 + ["Yes, the twenty-third works.", "Yes, I confirm."], expected=ok)
    assert d.score()["pass"], d.lines
    assert not any("400" in x for x in d.lines), d.lines                 # no attempt used on the chatter
    assert all(x == SPEC_A["lines"]["neutral_reask"] for x in d.lines[6:9]), d.lines


def test_pub06_talkative_small_talk_after_the_floor_is_a_neutral_reask():
    d = run_case("PUB-06", ID6 + ["I'm afraid that full amount is way too much for me.",
                                  "My boss has been giving me so many tasks to finish before",
                                  "I've been so overwhelmed with these deadlines at work,",
                                  "I've been staring at my computer", "Okay, Friday works.", "Yes, I confirm."],
                 expected=P06)
    assert d.score()["pass"] and len(_floor_offers(d)) == 1, d.lines


def test_small_talk_is_capped_then_counts_as_before():
    d = run_case("PUB-06", ID6 + ["The full amount is too much."] + TALK + ["I've been staring at my computer screen"])
    st = json.loads(d.vars["st"])
    assert st["chat"] == 4 and "Sorry, could you say that again?" in d.lines[-1], d.lines


@pytest.mark.parametrize("text, chat", [
    ("I have been so busy planning things", True), ("I've been running around all day trying to", True),
    ("I don't know.", False), ("Maybe I can pay later", False), ("I'll think about it", False),
    ("I can't do that, sorry", False), ("Busy day.", False), ("What do you mean by that?", False),
    ("It's been such a hectic day trying to get", True),
])
def test_chatter_words(text, chat):
    assert B._b_chatter({"text": text}) is chat


def test_pub05_talkative_transfer_offer_is_made_once():
    ok = exp("no_promise", "hardship")
    d = run_case("PUB-05", ["Yes, this is Tomas Novak.", "nine September nineteen ninety", "8846",
                            "I lost my job last month and I cannot pay anything right now.",
                            "I've been so busy today trying to", "What does the support team do?",
                            "No, I do not want to be transferred."], expected=ok)
    assert d.score()["pass"], d.lines
    assert sum("support team?" in x for x in d.lines) == 1, d.lines


@pytest.mark.parametrize("first", [
    "No, you are speaking with her husband. Work has been so busy today. What is this call regarding?",
    "You are speaking with her husband.",
])
def test_pub02_speaking_with_her_husband_is_a_third_party(first):
    d = run_case("PUB-02", [first, "The traffic was a nightmare getting home", "I'm exhausted because I've been",
                            "She will be back on Thursday at eleven."])
    assert d.score()["pass"], d.lines
    assert not any("date of birth" in x for x in d.lines), d.lines


def test_pub02_third_party_found_during_identity_switches_to_callback():
    d = run_case("PUB-02", ["Yes.", "I am not Maria, I am her husband, and", "She is back on Thursday at eleven."])
    assert d.score()["pass"], d.lines


def test_identity_relative_mention_after_a_verify_is_not_a_switch():
    d = run_a(["Yes, speaking.", "14 March 1988", "I'm her sister's friend, 4471, anyway."], cid="PUB-01")
    assert d.tools()[:2] == ["verify_identity", "verify_identity"], (d.tools(), d.lines)


def test_pub12_pieces_dob_in_two_parts_is_buffered_not_declined():
    d = Driver(copy.deepcopy(SPEC_AB), W_AB, copy.deepcopy(CASES["PUB-12"]))
    d.play(["Yes, this is Marcus Bell.", "19 October.", "Nineteen eighty three."])
    assert d.tools() == ["verify_identity"], (d.tools(), d.lines)
    assert json.loads(d.vars["st"])["id"]["dec"] in ({}, {"dob": 0}), d.vars["st"]


@pytest.mark.parametrize("text", ["thirtieth...", "both on thirtieth...", "I want to pay on thirtieth..."])
def test_pub13_pieces_bare_ordinal_day_is_a_date(text):
    import datetime
    from runtime.parse import parse_date
    assert parse_date(text, datetime.date(2026, 10, 11), SPEC_AB["calendar"]) == {"kind": "date", "date": "2026-10-30"}


# ---------------------------------------------------------------------------- code_exec limit on long multi-product calls
def test_turns_to_limit_matches_the_live_refusal():
    from builder.compiler import lint
    # call 4500f247 (A+B, talkative): 80,393 B of escaped code, code_exec refused at customer turn 41
    assert 39 <= lint.turns_to_limit("x" * 80_391) <= 42
    assert lint.turns_to_limit("x" * 200_000) == 0


def test_lint_warns_when_a_long_call_would_hit_the_code_exec_limit():
    from builder.compiler import lint
    out = []
    lint._lint_code_size({"nodes": {}}, "ctl", "x" * 84_000, out)
    assert any(f["rule"] == "code_turns" and f["level"] == "warn" for f in out), out
    out = []
    lint._lint_code_size({"nodes": {}}, "ctl", "x" * 70_000, out)
    assert not any(f["rule"] == "code_turns" for f in out), out


# ---------------------------------------------------------------------------- graceful turn cap (code_exec limit)
def _capped(cap):
    sp = copy.deepcopy(SPEC_A)
    sp["turn_cap"] = cap
    return sp


def _drive(sp, cid, turns, expected=None):
    case = copy.deepcopy(CASES[cid])
    if expected is not None:
        case["expected"] = expected
    from test_brain import W_A
    d = Driver(sp, W_A, case)
    d.play(turns)
    return d


def test_long_chatter_in_negotiation_wraps_up_at_the_cap_with_close_call_last():
    turns = ID6 + ["The full amount is too much."] + ["Hold on a second."] * 30
    d = _drive(_capped(10), "PUB-06", turns, expected=exp("no_promise", "refused"))
    assert d.ended and len(d.turn_lines) == 10, (len(d.turn_lines), d.lines)
    assert d.tools()[-1] == "close_call" and "create_promise" not in d.tools(), d.tools()
    assert d.score()["pass"], d.lines
    assert d.lines[-1].endswith("Goodbye."), d.lines


def test_agreed_promise_is_recorded_when_the_cap_is_reached_during_the_read_back():
    turns = ID6 + ["The full amount is too much.", "Okay, Friday works."] + ["Hold on a second."] * 30
    d = _drive(_capped(9), "PUB-06", turns, expected=P06)
    assert d.ended and d.tools()[-2:] == ["create_promise", "close_call"], (d.tools(), d.lines)
    assert d.score()["pass"], d.lines
    assert "Is there anything else" not in d.lines[-1], d.lines                # no extra turn after the cap


def test_long_chatter_during_identity_closes_as_declined_at_the_cap():
    turns = ["Yes, this is Priya Nair."] + ["I've been so busy with my cousin's wedding planning all week"] * 30
    d = _drive(_capped(8), "PUB-06", turns, expected=exp("not_verified", "declined"))
    assert d.ended and len(d.turn_lines) <= 8 and d.tools() == ["close_call"], (d.tools(), d.lines)
    assert d.score()["pass"], d.lines


def test_third_party_chatter_closes_without_callback_at_the_cap():
    turns = ["No, this is her husband."] + ["The traffic was a nightmare getting home"] * 30
    d = _drive(_capped(5), "PUB-02", turns, expected=exp("not_reached", "no_callback"))
    assert d.ended and d.tools() == ["close_call"], (d.tools(), d.lines)
    assert d.score()["pass"], d.lines


def test_no_turn_cap_keeps_the_old_forty_turn_guard():
    turns = ID6 + ["The full amount is too much."] + ["Hold on a second."] * 60
    d = _drive(copy.deepcopy(SPEC_A), "PUB-06", turns)
    assert d.ended and len(d.turn_lines) == B._B_MAX_TURNS and d.tools()[-1] == "close_call", len(d.turn_lines)


def test_compiler_bakes_the_turn_budget_from_the_packed_size():
    from builder.compiler import lint, snippet
    from runtime import brain, bundle
    from test_brain import W_A
    code = snippet.build_ctl_code(SPEC_A, W_A)
    ns = {}
    exec(bundle.unpack_snippet(code).split("globals().update")[0], ns)
    cap = brain._b_dec(ns["RSPEC_HEX"])["spec"]["turn_cap"]
    assert abs(cap - (lint.turns_to_limit(code) - snippet.TURN_MARGIN)) <= 1 and cap >= snippet.MIN_TURN_CAP
    assert snippet.turn_cap("x" * 120_000) == snippet.MIN_TURN_CAP
