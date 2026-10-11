"""Coverage tests for runtime/brain.py lines 1-1350, part 2: intent selection (C.5 step 3, B.3 intent rules and
interpretation switches), required sentences, say composition, the close flow, notes, the C.8 write chain
(plan / reconcile / retries / failures) and wire formatting of planned api calls.

Plans are driven through brain.step with a crafted state and api results, exactly as the ctl node re-enters after a
chained api node fails (C.8)."""
import copy
import datetime
import json
import pathlib

import pytest

from runtime import brain

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load(rel):
    return json.loads((ROOT / rel).read_text())


def runtime_spec(spec):
    spec = copy.deepcopy(spec)
    spec.pop("meta", None)
    for it in spec.get("intents", []):
        for k in ("label", "description", "examples", "negatives"):
            it.pop(k, None)
    return spec


SPEC_A = runtime_spec(_load("tests/golden/spec-a.json"))
SPEC_AB = runtime_spec(_load("tests/golden/spec-ab.json"))
W_A = _load("tests/fixtures/wiring-a.json")
W_AB = _load("tests/fixtures/wiring-ab.json")
CALL = {"customer_id": "c-1", "first_name": "Ann", "last_name": "Lee", "title": "Ms", "now": "2026-01-07T11:00"}
GOODBYE = SPEC_A["closing"]["goodbye"]
TEXT_MSG = SPEC_A["required_sentences"][0]["text"]


def ctx(spec=SPEC_A, W=W_A, st=None, text="", topic="", act="", results=None):
    R = {"v": 1, "spec": spec, "wiring": W}
    sens = {"u_text": text, "u_topic": topic, "u_act": act}
    return brain._b_ctx(R, copy.deepcopy(st or {}), {"call": dict(CALL), "sensors": sens, "results": results or {}})


def step(spec, W, st, results=None, text=""):
    R = {"v": 1, "spec": spec, "wiring": W}
    return brain.step(R, st, {"call": dict(CALL), "sensors": {"u_text": text}, "results": results or {},
                              "entered_from": ""})


def prod(pid, due, **kw):
    p = {"id": pid, "type": "credit_card", "due": due, "dl": 6, "f": {}, "sit": "", "ag": None, "rec": 0}
    p.update(kw)
    return p


def ids(hits):
    return [h.get("id") for h in hits]


# ----------------------------------------------------------------------------------------------- intents
class TestIntentSelection:
    def test_paid_with_a_future_marker_is_not_a_payment(self):
        # paid_requires_completed_tense: "I have paid ... and will pay the rest tomorrow" is not 'paid'
        c = ctx(text="I have paid some and I will pay the rest tomorrow")
        assert "paid" not in ids(brain._b_intents(c, "neg"))

    def test_paid_by_keyword_in_completed_tense(self):
        c = ctx(text="I already paid it")
        assert ids(brain._b_intents(c, "neg"))[0] == "paid"

    def test_paid_topic_without_a_completed_payment_is_dropped(self):
        c = ctx(text="hmm okay", topic="paid")
        assert "paid" not in ids(brain._b_intents(c, "neg"))

    def test_paid_topic_with_a_completed_payment_in_the_text_is_kept(self):
        c = ctx(text="I sent the payment last week, I paid it", topic="paid")
        assert "paid" in ids(brain._b_intents(c, "neg"))

    def test_hardship_needs_a_cause_keyword_not_just_the_topic(self):
        assert "hardship" not in ids(brain._b_intents(ctx(text="things are hard", topic="hardship"), "neg"))
        assert ids(brain._b_intents(ctx(text="I lost my job", topic="hardship"), "neg"))[0] == "hardship"

    def test_hardship_by_topic_alone_when_the_interpretation_allows_it(self):
        spec = copy.deepcopy(SPEC_A)
        spec["interpretation"]["hardship_requires_cause"] = False
        assert "hardship" in ids(brain._b_intents(ctx(spec, text="things are hard", topic="hardship"), "neg"))

    def test_refuse_to_talk_topic_needs_talk_words(self):
        assert "refuse_talk" not in ids(brain._b_intents(ctx(text="no", topic="refuse_talk"), "neg"))
        assert "refuse_talk" in ids(brain._b_intents(ctx(text="I won't talk about it", topic="refuse_talk"), "neg"))

    def test_are_you_a_real_person_is_a_question_not_a_human_request(self):
        c = ctx(text="Are you a real person?")
        assert "human" not in ids(brain._b_intents(c, "neg"))
        # the extracted topic still wins: the customer asked for a human in the same breath
        c = ctx(text="Are you a real person?", topic="human")
        assert "human" in ids(brain._b_intents(c, "neg"))

    def test_precedence_then_tie_order(self):
        c = ctx(text="I lost my job and I want a payment plan, is this a scam")
        got = ids(brain._b_intents(c, "neg"))
        assert got[:2] == ["hardship", "restructure"]
        assert "scam" in got

    def test_out_of_scope_intents_are_ignored(self):
        assert brain._b_intents(ctx(text="I already paid"), "rp") == []

    def test_intents_on_a_clause_ignore_the_extracted_topic(self):
        c = ctx(text="whatever", topic="dispute")
        assert brain._b_intents_on(c, "neg", "it is not mine") and \
            ids(brain._b_intents_on(c, "neg", "it is not mine"))[0] == "dispute"
        assert brain._b_intents_on(c, "neg", "fine") == []
        assert (c["text"], c["topic"]) == ("whatever", "dispute")  # restored


class TestClosureDispute:
    """interpretation.past_closure_is_dispute (M3)."""

    def test_paid_off_long_ago_becomes_the_dispute_intent(self):
        got = ids(brain._b_intents(ctx(text="I have paid that off"), "neg"))
        assert "paid" not in got and got[0] == "dispute"

    def test_recent_closure_stays_paid(self):
        got = ids(brain._b_intents(ctx(text="I have paid that off this morning"), "neg"))
        assert got[0] == "paid"

    def test_switch_off_keeps_paid(self):
        spec = copy.deepcopy(SPEC_A)
        spec["interpretation"]["past_closure_is_dispute"] = False
        got = ids(brain._b_intents(ctx(spec, text="I have paid that off"), "neg"))
        assert got[0] == "paid"

    def test_without_any_no_promise_resolve_intent_nothing_changes(self):
        spec = copy.deepcopy(SPEC_A)
        spec["intents"] = [it for it in spec["intents"] if it["id"] != "dispute"]
        got = ids(brain._b_intents(ctx(spec, text="I have paid that off"), "neg"))
        assert got[0] == "paid"

    def test_fallback_is_the_first_no_promise_resolve_intent(self):
        spec = copy.deepcopy(SPEC_A)
        spec["intents"] = [it for it in spec["intents"] if it["id"] != "dispute"]
        spec["situations"]["S_NOT_OURS"] = {"outcome": "no_promise", "reason": "other", "queue": "",
                                            "note_reason": "other"}
        spec["intents"] += [
            {"id": "settled", "scope": ["neg"], "precedence": 30, "keywords": ["\\bsettled\\b"],
             "action": {"kind": "resolve_product", "say": "Noted.", "situation": "S_PROMISE"}},
            {"id": "not_ours", "scope": ["neg"], "precedence": 30, "keywords": ["\\bnot ours\\b"],
             "action": {"kind": "resolve_product", "say": "Noted.", "situation": "S_NOT_OURS"}},
            {"id": "not_ours_2", "scope": ["neg"], "precedence": 30, "keywords": ["\\bnot ours either\\b"],
             "action": {"kind": "resolve_product", "say": "Noted.", "situation": "S_NOT_OURS"}},
        ]
        got = ids(brain._b_intents(ctx(spec, text="I closed that card"), "neg"))
        assert got == ["not_ours"]


class TestSplitAndRequired:
    def test_recorded_answer_is_skipped_until_something_is_recorded(self):
        spec = copy.deepcopy(SPEC_A)
        it = {"id": "x", "action": {"kind": "answer_continue", "say": "Your promise was recorded already."}}
        c = ctx(spec, st={"prods": [prod("p1", 100)]})
        assert brain._b_split_intents(c, [it]) == ([], [], False)
        c = ctx(spec, st={"prods": [prod("p1", 100, rec=1)]})
        assert brain._b_split_intents(c, [it])[0] == ["Your promise was recorded already."]

    def test_split_kinds(self):
        hits = [it for it in SPEC_A["intents"] if it["id"] in ("too_much", "robot", "dispute")]
        ans, acts, tm = brain._b_split_intents(ctx(), hits)
        assert ans == ["I am Freya Bank's digital assistant."]
        assert ids(acts) == ["dispute"]
        assert tm is True

    def test_once_sentences_are_said_once_and_others_every_time(self):
        spec = copy.deepcopy(SPEC_A)
        spec["required_sentences"] = [
            {"id": "a", "text": "Once only.", "trigger": "before_close", "once": True},
            {"id": "b", "text": "Every time.", "trigger": "before_close", "once": False},
            {"id": "c", "text": "Elsewhere.", "trigger": "after_verified"},
        ]
        c = ctx(spec)
        assert brain._b_req(c, ["before_close"]) == ["Once only.", "Every time."]
        assert brain._b_req(c, ["before_close"]) == ["Every time."]
        assert c["st"]["said"] == ["a"]

    def test_not_persisted_when_asked(self):
        c = ctx()
        assert brain._b_req(c, ["after_promise_recorded"], persist=False) == [TEXT_MSG]
        assert brain._b_req(c, ["after_promise_recorded"]) == [TEXT_MSG]


class TestCompose:
    def test_near_duplicate_sentences_are_dropped_but_questions_kept(self):
        c = {"say": ["I understand your situation completely.", "I understand your situation completely now.",
                     "Could you pay today?", "Could you pay today, please?"]}
        assert brain._b_compose(c) == ("I understand your situation completely. Could you pay today? "
                                       "Could you pay today, please?")

    def test_contained_parts_and_stop_word_sentences(self):
        c = {"say": ["Thank you. Goodbye.", "Goodbye.", "", "Is it?", "It is."]}
        # "Goodbye." is already inside the first part; stop-word-only sentences have no key and are kept
        assert brain._b_compose(c) == "Thank you. Goodbye. Is it? It is."

    def test_dupe_needs_a_key(self):
        assert brain._b_dupe("the and you.", [["x"]]) is False
        assert brain._b_dupe("Payment recorded today", [["payment", "recorded", "today"]]) is True


# ----------------------------------------------------------------------------------------------- close / notes
class TestClose:
    def test_unrecorded_agreement_is_dropped_at_a_terminal_close(self):
        st = {"ph": "NEG", "prods": [prod("p1", 42000, ag=[42000, "2026-01-07"])], "csit": "S_REFUSED_TO_TALK"}
        c = ctx(st=st)
        brain._b_close(c, ["Fine."])
        assert c["st"]["prods"][0]["ag"] is None
        assert c["st"]["ph"] == "BYE" and c["nx"] == "s_bye"
        assert c["say"] == ["Fine.", GOODBYE]
        assert c["co"] == ("no_promise", "refused", "r")

    def test_agreement_kept_when_the_interpretation_says_so(self):
        spec = copy.deepcopy(SPEC_A)
        spec["interpretation"]["agreed_before_terminal"] = "keep"
        st = {"ph": "NEG", "prods": [prod("p1", 42000, ag=[42000, "2026-01-07"])]}
        c = ctx(spec, st=st)
        brain._b_close(c)
        assert c["st"]["prods"][0]["ag"] == [42000, "2026-01-07"]

    def test_pending_transfer_without_transfer_nodes_closes_as_service_error(self):
        W = copy.deepcopy(W_A)
        W["api"]["xfer"] = []
        st = {"ph": "NEG", "prods": [prod("p1", 42000)], "xfer": {"sit": "S_HUMAN_TRANSFER", "q": "general"},
              "bye_pre": ["I will transfer you to a colleague."]}
        c = ctx(W=W, st=st)
        brain._b_close(c)
        assert c["st"]["xfer"]["failed"] == 1
        assert c["st"]["csit"] == "S_SERVICE_ERROR"
        assert c["nx"] == "s_bye"
        # the transfer announcement is withdrawn; the honest close is the service error
        assert c["say"] == [GOODBYE]
        assert c["co"] == ("no_promise", "service_error", "r")

    def test_pending_transfer_is_planned_before_bye(self):
        st = {"ph": "NEG", "prods": [prod("p1", 42000)], "xfer": {"sit": "S_HUMAN_TRANSFER", "q": "general"}}
        c = ctx(st=st)
        brain._b_close(c, ["I will transfer you to a colleague."])
        assert c["nx"] == "a_xfer_1"
        assert c["w"]["b_a_xfer_1_queue"] == "general"
        assert c["w"]["r_a_xfer_1_s"] == "pending"
        assert c["w"]["wn_a_xfer_1"] == "s_bye"
        assert c["st"]["plan"] == ["a_xfer_1", "s_bye"]
        assert c["co"] == ("transferred", "human", "r")

    def test_unknown_close_situation_has_no_outcome_sentence(self):
        spec = copy.deepcopy(SPEC_A)
        spec["required_sentences"].append({"id": "o", "text": "Outcome line.", "trigger": "on_outcome:",
                                           "once": True})
        c = ctx(spec, st={"ph": "NEG", "csit": "S_GHOST"})
        brain._b_close(c)
        assert c["say"] == [GOODBYE]
        assert c["co"] == ("", "", "n")

    def test_per_situation_closing_line_before_goodbye(self):
        spec = copy.deepcopy(SPEC_A)
        spec["closing"]["per_situation"] = {"S_REFUSED_TO_TALK": "We will write to you."}
        c = ctx(spec, st={"ph": "NEG", "csit": "S_REFUSED_TO_TALK"})
        brain._b_close(c)
        assert c["say"] == ["We will write to you.", GOODBYE]


class TestNotes:
    def test_product_notes_only_for_situations_with_a_note_reason(self):
        spec = copy.deepcopy(SPEC_AB)
        spec["situations"]["S_DISPUTE"]["note_reason"] = ""
        st = {"ph": "NEG", "prods": [prod("p1", 100, sit="S_DISPUTE"), prod("p2", 200, sit="S_PAID"),
                                     prod("p3", 300, rec=1)]}
        c = ctx(spec, W_AB, st=st)
        items = brain._b_note_items(c, [])
        assert items == [{"t": "note", "j": 1, "n": "a_note_2", "reason": "paid"}]

    def test_notes_skipped_after_a_transfer_unless_configured(self):
        st = {"ph": "NEG", "prods": [prod("p1", 100, sit="S_DISPUTE")], "xfer": {"sit": "S_HUMAN_TRANSFER"}}
        assert brain._b_note_items(ctx(SPEC_AB, W_AB, st=st), []) == []
        spec = copy.deepcopy(SPEC_AB)
        spec["notes"]["skip_if_transfer"] = False
        assert len(brain._b_note_items(ctx(spec, W_AB, st=st), [])) == 1
        st["xfer"]["failed"] = 1  # the transfer failed: notes apply again
        assert len(brain._b_note_items(ctx(SPEC_AB, W_AB, st=st), [])) == 1

    def test_note_text_is_rendered_per_product(self):
        spec = copy.deepcopy(SPEC_AB)
        spec["notes"]["text"] = "Customer said <days_late> days."
        W = copy.deepcopy(W_AB)
        W["nodes"]["a_note_1"]["body"]["text"] = "b_a_note_1_text"
        W["roles"]["add_note"]["req"]["text"] = "text"
        st = {"ph": "NEG", "prods": [prod("p1", 100, sit="S_DISPUTE", dl=9)]}
        c = ctx(spec, W, st=st)
        brain._b_close(c)
        assert c["nx"] == "a_note_1"
        assert c["w"]["b_a_note_1_text"] == "Customer said 9 days."
        assert c["w"]["b_a_note_1_reason"] == "dispute"
        assert c["w"]["b_a_note_1_product_id"] == "p1"


def call_notes():
    spec = copy.deepcopy(SPEC_AB)
    spec["notes"]["scope"] = "call"
    W = copy.deepcopy(W_AB)
    W["api"]["note"] = []
    W["api"]["note_call"] = ["a_note_call_1"]
    W["nodes"]["a_note_call_1"] = {"tool": "add_note", "body": {"reason": "b_a_note_call_1_reason"},
                                   "res": {"s": "r_a_note_call_1_s", "err": "r_a_note_call_1_err"},
                                   "res_leaf": {"s": "ok", "err": "error"}}
    return spec, W


class TestCallNotes:
    def test_one_call_note_with_the_outcome_reason(self):
        spec, W = call_notes()
        st = {"ph": "NEG", "prods": [prod("p1", 100, sit="S_DISPUTE"), prod("p2", 100, sit="S_PAID")]}
        c = ctx(spec, W, st=st)
        brain._b_close(c)
        assert c["nx"] == "a_note_call_1"
        assert c["w"]["b_a_note_call_1_reason"] == "dispute"
        assert not any(k.startswith("b_a_note_call_1_product") for k in c["w"])
        assert c["st"]["pm"] == [{"t": "cnote", "n": "a_note_call_1", "reason": "dispute"}]

    def test_call_note_text_without_a_product(self):
        spec, W = call_notes()
        spec["notes"]["text"] = "Call with <customer>."
        W["nodes"]["a_note_call_1"]["body"]["text"] = "b_a_note_call_1_text"
        W["roles"]["add_note"]["req"]["text"] = "text"
        c = ctx(spec, W, st={"ph": "NEG", "prods": [prod("p1", 100, sit="S_DISPUTE")]})
        brain._b_close(c)
        assert c["w"]["b_a_note_call_1_text"] == "Call with Ms Lee."

    def test_no_call_note_when_noted_recorded_or_reasonless(self):
        spec, W = call_notes()
        st = {"ph": "NEG", "prods": [prod("p1", 100, sit="S_DISPUTE")], "cnoted": 1}
        assert brain._b_note_items(ctx(spec, W, st=st), []) == []
        st = {"ph": "NEG", "prods": [prod("p1", 100, rec=1), prod("p2", 100, sit="S_DISPUTE")]}
        assert brain._b_note_items(ctx(spec, W, st=st), []) == []
        st = {"ph": "NEG", "prods": [prod("p1", 100)], "csit": "S_WRONG_NUMBER"}  # note_reason ""
        assert brain._b_note_items(ctx(spec, W, st=st), []) == []

    def test_call_note_success_on_reentry_without_chain(self):
        spec, W = call_notes()
        W["chain"] = False
        st = {"ph": "NOTES", "prods": [prod("p1", 100, sit="S_DISPUTE")], "plan": ["a_note_call_1", "s_bye"],
              "pm": [{"t": "cnote", "n": "a_note_call_1", "reason": "dispute"}], "await": "a_note_call_1"}
        st2, w = step(spec, W, st, {"a_note_call_1": {"s": "true"}})
        assert st2["cnoted"] == 1
        assert w["nx"] == "s_bye" and st2["ph"] == "BYE"
        assert w["co"] == "no_promise" and w["cr"] == "dispute"

    def test_failed_call_note_is_skipped(self):
        spec, W = call_notes()
        st = {"ph": "NOTES", "prods": [prod("p1", 100, sit="S_DISPUTE")], "plan": ["a_note_call_1", "s_bye"],
              "pm": [{"t": "cnote", "n": "a_note_call_1", "reason": "dispute"}], "await": "a_note_call_1"}
        st2, w = step(spec, W, st, {"a_note_call_1": {"s": "false"}})
        assert st2["cnote_failed"] == 1
        assert w["nx"] == "s_bye"
        assert w["say"] == SPEC_AB["closing"]["goodbye"]


# ----------------------------------------------------------------------------------------------- write chain
def two_promises(**extra):
    st = {"ph": "WRITE", "prods": [prod("p1", 42000, ag=[42000, "2026-01-07"]),
                                   prod("p2", 10050, ag=[10050, "2026-01-08"])],
          "plan": ["a_promise_1_1", "a_promise_2_1", "s_bye"],
          "pm": [{"t": "promise", "j": 0, "n": "a_promise_1_1", "try": 0},
                 {"t": "promise", "j": 1, "n": "a_promise_2_1", "try": 0}],
          "await": "a_promise_1_1"}
    st.update(extra)
    return st


class TestReconcile:
    def test_second_promise_fails_first_is_kept_and_retry_planned(self):
        st2, w = step(SPEC_AB, W_AB, two_promises(),
                      {"a_promise_1_1": {"s": "true", "pid": "PR-1"}, "a_promise_2_1": {"s": "false", "err": "x"}})
        assert st2["prods"][0]["rec"] == 1 and st2["prods"][0]["pid"] == "PR-1"
        assert w["nx"] == "a_promise_2_2"
        assert w["b_a_promise_2_2_amount"] == "100.50"
        assert w["b_a_promise_2_2_date"] == "2026-01-08"
        assert w["b_a_promise_2_2_product_id"] == "p2"
        assert w["r_a_promise_2_2_s"] == "pending"
        assert w["wn_a_promise_2_2"] == "s_bye"
        assert st2["plan"] == ["a_promise_2_2", "s_bye"]
        assert "Your promises are recorded." in w["say"] and w["say"].endswith(SPEC_AB["closing"]["goodbye"])
        assert (w["co"], w["cr"], w["cmode"]) == ("promise", "", "n")

    def test_retry_fails_too_product_becomes_service_error_and_is_noted(self):
        st = two_promises(plan=["a_promise_2_2", "s_bye"],
                          pm=[{"t": "promise", "j": 1, "n": "a_promise_2_2", "try": 1}])
        st["await"] = "a_promise_2_2"
        st["prods"][0]["rec"] = 1
        st2, w = step(SPEC_AB, W_AB, st, {"a_promise_2_2": {"s": "false"}})
        p2 = st2["prods"][1]
        assert p2["failed"] == 1 and p2["sit"] == "S_SERVICE_ERROR" and p2["ag"] is None
        assert w["nx"] == "a_note_2"
        assert w["b_a_note_2_reason"] == "service_error"
        # a recorded promise and a failed one: the per-product failure line, not a contradictory "could not record"
        assert "Your promise is recorded." in w["say"]
        assert "I'm sorry, I could not record the promise for your" in w["say"]
        assert w["co"] == "promise"

    def test_failed_note_is_skipped_and_the_chain_continues(self):
        st = {"ph": "NOTES", "prods": [prod("p1", 100, sit="S_DISPUTE"), prod("p2", 100, sit="S_PAID")],
              "plan": ["a_note_1", "a_note_2", "s_bye"],
              "pm": [{"t": "note", "j": 0, "n": "a_note_1", "reason": "dispute"},
                     {"t": "note", "j": 1, "n": "a_note_2", "reason": "paid"}], "await": "a_note_1"}
        st2, w = step(SPEC_AB, W_AB, st, {"a_note_1": {"s": "false"}, "a_note_2": {"s": "pending"}})
        assert st2["prods"][0]["note_failed"] == 1
        assert w["nx"] == "a_note_2" and st2["plan"] == ["a_note_2", "s_bye"]
        assert w["b_a_note_2_reason"] == "paid"

    def test_duplicate_planned_items_are_planned_once(self):
        st = {"ph": "NOTES", "prods": [prod("p1", 100, sit="S_DISPUTE"), prod("p2", 100, sit="S_PAID")],
              "plan": ["a_note_1", "a_note_2", "a_note_2", "s_bye"],
              "pm": [{"t": "note", "j": 0, "n": "a_note_1", "reason": "dispute"},
                     {"t": "note", "j": 1, "n": "a_note_2", "reason": "paid"},
                     {"t": "note", "j": 1, "n": "a_note_2", "reason": "paid"}], "await": "a_note_1"}
        st2, w = step(SPEC_AB, W_AB, st, {"a_note_1": {"s": "false"}})
        assert st2["plan"] == ["a_note_2", "s_bye"]
        assert len(st2["pm"]) == 1

    def test_transfer_success_without_chain_is_marked_done(self):
        W = copy.deepcopy(W_A)
        W["chain"] = False
        st = {"ph": "XFER", "prods": [prod("p1", 42000)], "xfer": {"sit": "S_HUMAN_TRANSFER", "q": "general"},
              "plan": ["a_xfer_1", "s_bye"], "pm": [{"t": "xfer", "n": "a_xfer_1", "try": 0}], "await": "a_xfer_1"}
        st2, w = step(SPEC_A, W, st, {"a_xfer_1": {"s": "true"}})
        assert st2["xfer"]["done"] == 1
        assert w["nx"] == "s_bye"
        assert (w["co"], w["cr"]) == ("transferred", "human")

    def test_callback_success_without_chain_is_marked_done_and_booked_line_said(self):
        W = copy.deepcopy(W_A)
        W["chain"] = False
        st = {"ph": "WRITE", "csit": "S_CALLBACK", "cb": {"d": "2026-01-07", "t": 900, "try": 0},
              "plan": ["a_cb_1", "s_bye"], "pm": [{"t": "cb", "n": "a_cb_1", "try": 0}], "await": "a_cb_1"}
        st2, w = step(SPEC_A, W, st, {"a_cb_1": {"s": "true"}})
        assert st2["cb"]["done"] == 1
        assert w["nx"] == "s_bye"
        assert "We will call back on Wednesday, 7 January at 15:00." in w["say"]
        assert (w["co"], w["cr"]) == ("not_reached", "callback")

    def test_without_chain_only_the_first_success_is_counted(self):
        W = copy.deepcopy(W_AB)
        W["chain"] = False
        st2, w = step(SPEC_AB, W, two_promises(),
                      {"a_promise_1_1": {"s": "true"}, "a_promise_2_1": {"s": "true"}})
        assert st2["prods"][0]["rec"] == 1 and not st2["prods"][1].get("rec")
        assert w["nx"] == "a_promise_2_1"

    def test_http_ok_no_error_success(self):
        W = copy.deepcopy(W_AB)
        W["success"]["create_promise"] = {"role": "s", "kind": "http_ok_no_error", "values": []}
        st = two_promises()
        st2, w = step(SPEC_AB, W, st, {"a_promise_1_1": {"s": "pending", "err": "pending", "pid": "PR-9"},
                                       "a_promise_2_1": {"s": "pending", "err": "invalid date", "pid": "pending"}})
        assert st2["prods"][0]["rec"] == 1 and st2["prods"][0]["pid"] == "PR-9"
        assert w["nx"] == "a_promise_2_2"  # an error leaf (or nothing at all) is a failure

    def test_empty_plan_items_re_emit_the_bye(self):
        st = {"ph": "WRITE", "prods": [prod("p1", 42000, rec=1)], "plan": ["s_bye"], "pm": []}
        st2, w = step(SPEC_A, W_A, st)
        assert w["nx"] == "s_bye" and st2["ph"] == "BYE" and st2["plan"] == []
        assert w["co"] == "promise"

    def test_listen_bye_closes_on_the_next_turn(self):
        W = copy.deepcopy(W_A)
        W["bye_mode"] = "listen"
        st = {"ph": "CONF", "turns": 5, "prods": [prod("p1", 42000, ag=[42000, "2026-01-07"])]}
        c = ctx(W=W, st=st)
        brain._b_write(c, [])
        st1, w1 = brain._b_finish(c)
        assert w1["nx"] == "a_promise_1_1" and st1["plan"] == ["a_promise_1_1", "s_bye"]
        # chain: a_promise_1_1 succeeds -> s_bye speaks the goodbye -> the customer says bye -> ctl
        st2, w2 = step(SPEC_A, W, st1, {"a_promise_1_1": {"s": "true", "pid": "PR-1"}}, text="bye")
        # CONTRACTS D.3: "bye=listen (s_bye is a normal listen node; ctl closes on the next turn)"
        assert w2["nx"] == "a_close_n"
        assert st2["ph"] == "CLOSE"


class TestItemValues:
    def test_unknown_item_kind_has_no_values(self):
        assert brain._b_item_vals(ctx(), {"t": "mystery"}) == {}

    def test_wire_amount_scale_100(self):
        W = copy.deepcopy(W_A)
        W["wire"]["create_promise.amount"]["scale"] = 100
        assert brain._b_wire_amount(ctx(W=W), "create_promise", "amount", 42050) == "42050"
        assert brain._b_wire_amount(ctx(), "create_promise", "amount", 42050) == "420.50"

    def test_wire_date_formats(self):
        W = copy.deepcopy(W_A)
        W["wire"]["create_promise.date"]["format"] = "%d/%m/%Y"
        assert brain._b_wire_date(ctx(W=W), "create_promise", "date", "2026-01-07") == "07/01/2026"
        assert brain._b_wire_date(ctx(), "create_promise", "date", datetime.date(2026, 1, 7)) == "2026-01-07"
        # not a date: passed through as text, never raises
        assert brain._b_wire_date(ctx(), "create_promise", "date", "someday") == "someday"

    def test_wire_time(self):
        assert brain._b_wire_time(ctx(), "schedule_callback", "time", 905) == "15:05"
        W = copy.deepcopy(W_A)
        W["wire"]["schedule_callback.time"]["format"] = "%H%M"
        assert brain._b_wire_time(ctx(W=W), "schedule_callback", "time", 905) == "1505"

    def test_callback_values(self):
        st = {"cb": {"d": "2026-01-07", "t": 930, "try": 0}}
        vals = brain._b_item_vals(ctx(st=st), {"t": "cb", "n": "a_cb_1", "try": 0})
        assert vals["date"] == "2026-01-07" and vals["time"] == "15:30"

    def test_callback_datetime_carries_the_booked_time(self):
        W = copy.deepcopy(W_A)
        W["wire"]["schedule_callback.callback_at"] = {"type": "string", "format": "%Y-%m-%dT%H:%M:%S", "scale": 1}
        W["roles"]["schedule_callback"]["req"] = {"customer": "customer_id", "datetime": "callback_at"}
        st = {"cb": {"d": "2026-01-07", "t": 930, "try": 0}}
        vals = brain._b_item_vals(ctx(W=W, st=st), {"t": "cb", "n": "a_cb_1", "try": 0})
        assert vals["datetime"] == "2026-01-07T15:30:00"

    def test_promise_datetime_field_is_filled(self):
        W = copy.deepcopy(W_A)
        W["roles"]["create_promise"]["req"] = {"customer": "customer_id", "product": "product_id",
                                               "amount": "amount", "datetime": "promised_at"}
        W["nodes"]["a_promise_1_1"]["body"] = {"product_id": "b_a_promise_1_1_product_id",
                                               "amount": "b_a_promise_1_1_amount",
                                               "promised_at": "b_a_promise_1_1_promised_at"}
        W["wire"]["create_promise.promised_at"] = {"type": "string", "format": "%Y-%m-%dT%H:%M:%S", "scale": 1}
        st = {"ph": "CONF", "prods": [prod("p1", 42000, ag=[42000, "2026-01-07"])]}
        c = ctx(W=W, st=st)
        brain._b_write(c, [])
        assert c["w"].get("b_a_promise_1_1_promised_at", "").startswith("2026-01-07")
