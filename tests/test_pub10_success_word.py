"""PUB-10 official sims (2026-10-11, 2 of 3 reps): the judge read "agent does not say 'recorded' before a successful
call" literally and flagged the opening, "... and this call is recorded." validate now derives the success word from
the Spec's own recording lines and puts every pre-success use of it in the active voice ("we record this call"),
logged as a DECISION; lines spoken only after success, and lines the brief dictates verbatim, are left alone."""
import copy
import json
import pathlib
import re

import pytest
from test_brain import CASES, PUB_SCRIPTS, SPEC_A, SPEC_AB, W_A, W_AB, Driver, run_case

from builder.compiler import lint
from builder.pipeline import validate as V

ROOT = pathlib.Path(__file__).resolve().parent.parent
REC = re.compile(r"\brecorded\b", re.I)
OPEN_LIVE = "Hello, this is <self> calling, and this call is recorded."          # the opening the judge quoted


@pytest.fixture
def ga():
    return json.loads((ROOT / "tests" / "golden" / "spec-a.json").read_text())


def _validate(spec, cat, monkeypatch=None):
    seen = []
    if monkeypatch is not None:
        monkeypatch.setattr(V.trace, "event", lambda kind, msg="", **kw: seen.append((kind, msg)))
    r = V.validate(spec, cat)
    return r, seen


def test_opening_avoids_success_participle(ga, catalog_kit, monkeypatch):
    ga["opening"]["line"] = OPEN_LIVE
    ga["amounts"]["below_floor"]["say"] = "I'm afraid that amount cannot be recorded. Could you pay <floor> instead?"
    r, seen = _validate(ga, catalog_kit, monkeypatch)
    s = r["spec"]
    assert s["opening"]["line"] == "Hello, this is <self> calling, and we record this call."
    assert "record" in s["opening"]["line"] and "<self>" in s["opening"]["line"]
    # a negated clause claims no success: left as the Spec says it (review fix, 2026-10-11)
    assert s["amounts"]["below_floor"]["say"] == "I'm afraid that amount cannot be recorded. Could you pay <floor> instead?"
    assert s["recording"]["recorded"] == SPEC_A["recording"]["recorded"]                     # said after success
    assert s["confirmation"]["recorded_cannot_change"] == SPEC_A["confirmation"]["recorded_cannot_change"]
    assert any(k == "DECISION" and m.startswith("/opening/line: success word") for k, m in seen), seen
    assert any(m.startswith("/opening/line") for m in s["meta"]["decisions"])
    out = []
    lint._lint_opening(s, out)
    assert not out, out


@pytest.mark.parametrize("line, want", [
    ("Hello, this is <self>. This call is being recorded.", "Hello, this is <self>. We record this call."),  # fresh
    ("Hello, this is <self>, and the call may be recorded.", "Hello, this is <self>, and we may record this call."),
    ("Hello, this is <self>. Calls are recorded for quality.", "Hello, this is <self>. We record calls for quality."),
])
def test_other_passive_recording_disclosures(ga, catalog_kit, line, want):
    ga["opening"]["line"] = line
    assert V.validate(ga, catalog_kit)["spec"]["opening"]["line"] == want


def test_the_success_word_comes_from_the_spec(ga, catalog_kit):
    ga["recording"]["recorded"] = "Your promise is saved."
    ga["recording"]["recorded_multi"] = "Your promises are saved."
    ga["recording"]["failed"] = "I'm sorry, I could not save your promise."
    ga["opening"]["line"] = "Hello, this is <self>, and this call is saved."
    ga["amounts"]["below_floor"]["say"] = "Sorry, <amount> cannot be saved."
    s = V.validate(ga, catalog_kit)["spec"]
    assert V.success_words(s) == ["saved"]
    assert s["opening"]["line"] == "Hello, this is <self>, and we save this call."
    assert s["amounts"]["below_floor"]["say"] == "Sorry, <amount> cannot be saved."
    assert s["recording"]["recorded"] == "Your promise is saved."


def test_verbatim_lines_and_post_success_sentences_are_kept(ga, catalog_kit):
    ga["opening"]["line"] = "Hello, this is <self>, and this call is recorded."
    ga["opening"]["verbatim"] = True
    ga["required_sentences"].append({"id": "after_rec", "text": "Your promise is recorded in our system.",
                                     "verbatim": True, "trigger": "after_promise_recorded", "once": True})
    r = V.validate(ga, catalog_kit)
    s = r["spec"]
    assert s["opening"]["line"] == "Hello, this is <self>, and this call is recorded."
    assert s["required_sentences"][-1]["text"] == "Your promise is recorded in our system."
    assert any(w.startswith("/opening/line: says recorded") and "verbatim" in w for w in r["warnings"]), r["warnings"]


def test_a_line_the_rule_cannot_rewrite_is_warned(ga, catalog_kit):
    ga["lines"]["deadline_offer"] = "Payments are recorded by <deadline>. Could you pay <amount> by then?"
    r = V.validate(ga, catalog_kit)
    assert any(w.startswith("/lines/deadline_offer: says recorded") for w in r["warnings"]), r["warnings"]


def test_success_word_helpers_edge_cases():
    assert V.success_words({}) == []
    assert V._base_verb("logged", {}) == "log" and V._base_verb("copied", {}) == "copy"
    assert V._base_verb("registered", {}) == "register" and V._base_verb("stored", {}) == "store"
    s = {"closing": {"per_situation": {"S_PROMISE": "Thanks, all recorded.", "S_UNCLEAR": "Bye."}},
         "recording": {"recorded": "Your promise is recorded."}}
    assert "/closing/per_situation/S_PROMISE" in V._post_success_ptrs(s)
    fixes, warns = [], []
    V._success_word_fixes(s, warns, fixes)
    assert not fixes and not warns


# ---------------------------------------------------------------------------- the call: nothing says it too early
def _validated(spec):
    s = copy.deepcopy(spec)
    V._success_word_fixes(s, [], [])
    return s


@pytest.mark.parametrize("which", ["A", "AB"])
def test_pub10_no_success_word_before_create_ok(which):
    if which == "A":
        sp, w, case, turns = SPEC_A, W_A, copy.deepcopy(CASES["PUB-10"]), PUB_SCRIPTS["PUB-10"]
    else:
        sp, w, case = SPEC_AB, W_AB, copy.deepcopy(CASES["PUB-13"])
        turns = PUB_SCRIPTS["PUB-13"]
    sp = copy.deepcopy(sp)
    sp["opening"]["line"] = "Hello, I am a digital assistant calling from <bank>, and this call is recorded."
    sp["amounts"]["below_floor"]["say"] = "I'm afraid that amount cannot be recorded."
    d = Driver(_validated(sp), w, case, faults=[{"tool": "create_promise", "fail_first_n": 1}])
    d.play(turns)
    assert d.tools().count("create_promise") >= 2, d.tools()
    before = [x for x in d.lines if "Your promise" not in x and "Your promises" not in x]
    assert not any(V._claims_success(x, "recorded") for x in before), d.lines
    assert REC.search(d.lines[-1]), d.lines


def test_pub10_below_floor_line_before_success_is_active():
    sp = copy.deepcopy(SPEC_A)
    sp["amounts"]["below_floor"]["say"] = "I'm afraid that amount cannot be recorded."
    d = Driver(_validated(sp), W_A, copy.deepcopy(CASES["PUB-10"]),
               faults=[{"tool": "create_promise", "fail_first_n": 1}])
    d.play(["Yes.", "23 February 1989", "9904", "I can pay 5 on Friday.", "Yes, the minimum then.", "Yes."])
    assert any("cannot be recorded" in x for x in d.lines), d.lines            # negated: no success claim, kept
    assert not any(V._claims_success(x, "recorded") for x in d.lines[:-1]), d.lines


def test_pub10_recorded_only_after_success_on_the_golden_spec():
    d = run_case("PUB-10", PUB_SCRIPTS["PUB-10"], faults=CASES["PUB-10"]["faults"])
    assert not any(REC.search(x) for x in d.lines[:-1]), d.lines
    assert "we record this call" in d.lines[0]


# ---------------------------------------------------------------------------- review fix: narrow, safe rewrite only
@pytest.mark.parametrize("line, want", [
    # the deployed A+B Spec: a negated clause is no success claim and must never be scrambled
    ("I am sorry, an amount of <amount> cannot be recorded.", "I am sorry, an amount of <amount> cannot be recorded."),
    ("That amount could not be recorded.", "That amount could not be recorded."),
    ("Sorry, <amount> can't be recorded.", "Sorry, <amount> can't be recorded."),
    ("Your promise has not been recorded yet.", "Your promise has not been recorded yet."),
    # 'and <participle>' is never rewritten (warned instead)
    ("Hello, this call is recorded and monitored.", "Hello, this call is recorded and monitored."),
    ("Calls may be recorded and/or monitored.", "Calls may be recorded and/or monitored."),
    ("This call is recorded, and monitored for training.", "This call is recorded, and monitored for training."),
    # the whole subject is the call: rewritten, the modal kept
    ("Hello, this call may be recorded.", "Hello, we may record this call."),
    ("Calls may be recorded for quality.", "We may record calls for quality."),
    ("This call might be recorded.", "We might record this call."),
    ("This conversation is recorded.", "We record this conversation."),
    ("Please note that the call will be recorded.", "Please note that we record this call."),
    ("The call is recorded for quality and training purposes.", "We record this call for quality and training purposes."),
    # not the whole subject: left alone
    ("All calls are recorded.", "All calls are recorded."),
    ("Your call is recorded.", "Your call is recorded."),
])
def test_active_voice_is_narrow_and_safe(line, want):
    assert V._active_voice(line, "recorded", "record") == want


@pytest.mark.parametrize("line, warned", [
    ("I am sorry, an amount of <amount> cannot be recorded.", False),
    ("Hello, this is <self>, and this call is recorded and monitored.", True),
    ("Hello, this is <self>, and this call may be recorded.", False),
])
def test_negated_lines_are_kept_and_not_warned_and_participle_pairs_are_warned(ga, catalog_kit, line, warned):
    ga["opening"]["line"] = line
    r = V.validate(ga, catalog_kit)
    assert "<amount> of I" not in r["spec"]["opening"]["line"] and "an amount of I" not in r["spec"]["opening"]["line"]
    assert any(w.startswith("/opening/line: says recorded") for w in r["warnings"]) is warned, r["warnings"]
    if "may be" in line:
        assert r["spec"]["opening"]["line"].endswith("and we may record this call.")
    else:
        assert r["spec"]["opening"]["line"] == line


def test_claims_success_ignores_negated_uses():
    assert not V._claims_success("That amount cannot be recorded.", "recorded")
    assert not V._claims_success("It was not yet recorded.", "recorded")
    assert V._claims_success("Payments are recorded by Friday.", "recorded")
