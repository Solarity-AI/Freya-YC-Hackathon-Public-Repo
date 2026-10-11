"""Tests for runtime/brain.py (agent 2).

The brain is driven turn by turn through main() (vars in, vars out) against the harness MockBank, with a minimal
E1-style graph walk (ctl -> api node -> chain or ctl -> listen / s_bye -> close). The 13 practice cases use the
golden Specs and expected ledgers from kit/public-test-set.json (scored by the kit's own score_ledger); edge cases
come from docs/edge-cases/EDGE-CASES.md (OPN, IDV, NEG, MUL, JDG, TOOL)."""
import copy
import json
import os
import pathlib
import re

import pytest

from builder.paths import import_kit
from harness.mockbank import MockBank
from runtime import brain

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCORE = import_kit("score")


def load(rel):
    return json.loads((ROOT / rel).read_text())


CASES = {c["id"]: c for c in load("kit/public-test-set.json")}
CATALOG = load("tests/fixtures/catalog-kit.json")
SPEC_A = load("tests/golden/spec-a.json")
SPEC_AB = load("tests/golden/spec-ab.json")
W_A = load("tests/fixtures/wiring-a.json")
W_AB = load("tests/fixtures/wiring-ab.json")


def runtime_spec(spec):
    spec = copy.deepcopy(spec)
    spec.pop("meta", None)
    for it in spec.get("intents", []):
        for k in ("label", "description", "examples", "negatives"):
            it.pop(k, None)
    for k in ("confirm_examples", "non_confirm_examples"):
        spec.get("right_party", {}).pop(k, None)
    return spec


def _str(v, bool_style):
    if isinstance(v, bool):
        s = "true" if v else "false"
        return s.title() if bool_style == "title" else s
    if isinstance(v, (list, dict)):
        return json.dumps(v)
    if v is None:
        return ""
    return str(v)


_SNIPPETS = {}


def _default_entry(R):
    """BRAIN_ENTRY=snippet runs every scenario through the bundled, minified ctl snippet instead of main()."""
    if os.environ.get("BRAIN_ENTRY") != "snippet":
        return brain.main
    from runtime import bundle
    key = json.dumps(R, sort_keys=True)
    if key not in _SNIPPETS:
        _SNIPPETS[key] = compile(bundle.make_snippet(R), "<ctl>", "exec")
    code = _SNIPPETS[key]

    def run(vars, _R):
        exec(code, {"vars": vars})
    return run


class Driver:
    """Minimal executor of the D.3 graph semantics around the ctl entry (main or a bundled snippet)."""

    def __init__(self, spec, wiring, case, faults=None, bool_style="lower", entry=None, map_mode="mapped"):
        self.spec = runtime_spec(spec)
        self.W = wiring
        self.R = {"v": 1, "spec": self.spec, "wiring": wiring}
        self.case = copy.deepcopy(case)
        self.bank = MockBank(CATALOG, self.case, faults=faults)
        self.vars = dict(self.case.get("variables") or {})
        self.vars["customer_id"] = self.bank.customer_id
        self.lines = []
        self.turn_lines = []
        self.ended = False
        self.bool_style = bool_style
        self.map_mode = map_mode            # mapped | flat (only <node>_response.data.* keys) | repr
        self.entry = entry or _default_entry(self.R)
        self.path = []
        self.listen = set(wiring["listen"].values())
        self.verified_at = None

    def opening(self):
        line = brain.render(self.spec["opening"]["line"] + " " + self.spec["right_party"]["ask"],
                            {"spec": self.spec, "call": self.vars})
        self.lines.append(line)
        return line

    def turn(self, text, **sensors):
        assert not self.ended, "call already ended"
        self.vars["u_text"] = text
        for k in ("u_act", "u_topic", "u_date", "u_amt", "u_time", "u_ans"):
            self.vars[k] = sensors.get(k, "")
        out = []
        self._run("ctl", out)
        self.turn_lines.append(out)
        self.lines.extend(out)
        return out

    def play(self, turns):
        self.opening()
        for t in turns:
            if self.ended:
                break
            if isinstance(t, str):
                self.turn(t)
            else:
                self.turn(t["t"], **{k: v for k, v in t.items() if k != "t"})
        return self

    def _api(self, node):
        n = self.W["nodes"][node]
        tool = n["tool"]
        roles = self.W["roles"][tool]
        body = {}
        if roles["req"].get("customer"):
            body[roles["req"]["customer"]] = self.vars["customer_id"]
        for field, var in n["body"].items():
            if self.vars.get(var, "") != "":
                body[field] = self.vars[var]
        status, resp = self.bank.call(tool, body)
        self.path.append(node)
        if tool == "get_account" and status == 200 and resp and resp.get("ok") and self.verified_at is None:
            self.verified_at = len(self.lines)
        if status == 200 and isinstance(resp, dict):
            for role, var in n["res"].items():
                leaf = n["res_leaf"][role]
                if leaf in resp:
                    v = resp[leaf]
                    if self.map_mode == "repr" and isinstance(v, list):
                        self.vars[var] = repr(v)
                    elif self.map_mode != "flat":
                        self.vars[var] = _str(v, self.bool_style)
            for k, v in resp.items():
                if self.map_mode == "flat" and isinstance(v, list):
                    for i, item in enumerate(v):
                        for lk, lv in item.items():
                            self.vars["%s_response.data.%s.%d.%s" % (node, k, i, lk)] = lv
                else:
                    self.vars[node + "_response.data." + k] = _str(v, self.bool_style)
        return self.vars.get(n["res"].get("s", ""), "pending") in self.W["success"][tool]["values"] or (
            self.map_mode == "flat" and self.vars.get(node + "_response.data.ok") in ("true", "True"))

    def _run(self, node, out):
        for _hop in range(60):
            if node == "ctl":
                self.path.append("ctl")
                self.entry(self.vars, self.R)
                nx = self.vars["nx"]
                if nx in self.W["nodes"]:
                    assert self.vars.get(self.W["nodes"][nx]["res"].get("s", ""), "pending") == "pending", nx
                node = nx
                continue
            if node == self.W.get("bye"):
                out.append(self.vars.get("say", ""))
                tgt = self.W["api"]["close_r"] if self.vars.get("cmode") == "r" else self.W["api"]["close_n"]
                self._api(tgt)
                self.ended = True
                return
            if node in self.listen:
                out.append(self.vars.get("say", ""))
                self.path.append(node)
                return
            if node in (self.W["api"]["close_r"], self.W["api"]["close_n"]):
                out.append(self.vars.get("say", ""))
                self._api(node)
                self.ended = True
                return
            if node in self.W["nodes"]:
                ok = self._api(node)
                vt = self._vchain(node)
                if vt:
                    node = vt
                    continue
                wn = self.vars.get("wn_" + node, "")
                if ok and wn and self.W.get("chain") and node in self.W.get("chainable", []):
                    if wn not in self.W["nodes"] or self.vars.get(self.W["nodes"][wn]["res"].get("s", ""),
                                                                  "pending") == "pending":
                        node = wn
                        continue
                node = "ctl"
                continue
            raise AssertionError("unknown node %r" % node)
        raise AssertionError("hop limit")

    def _vchain(self, node):
        """The compiled identity-chain transitions out of a verify node (graph.vchain_transitions)."""
        vc = self.W.get("vchain") or {}
        if node not in self.W["api"]["verify"]:
            return None
        res = self.W["nodes"][node]["res"]
        s, v, a = (self.vars.get(res[k], "") for k in ("s", "verified", "all"))
        for t, f in zip(vc.get("t", []), vc.get("f", [])):
            if s == t and v == t:
                wn = self.vars.get("wn_" + node, "")
                if a == t and wn in self.W["nodes"] and \
                        self.vars.get(self.W["nodes"][wn]["res"]["s"], "pending") == "pending":
                    return wn
                if a == f and self.vars.get("wl_" + node, "") == self.W["listen"]["id"]:
                    return self.W["listen"]["id"]
        return None

    def ledger(self):
        return self.bank.ledger()

    def tools(self):
        return [c["tool"] for c in self.ledger()["calls"]]

    def score(self, expected=None):
        case = dict(self.case)
        if expected is not None:
            case = dict(case, expected=expected)
        return SCORE.score_ledger(case, self.ledger())


def pre_verification_lines(d):
    return d.lines[: d.verified_at] if d.verified_at is not None else d.lines


def assert_no_banned_before_verified(d):
    banned = [w.lower() for w in d.spec["banned"]["before_verification"]]
    for line in pre_verification_lines(d):
        for w in banned:
            assert not re.search(r"\b" + re.escape(w) + r"\b", line.lower()), (w, line)


def assert_one_line_per_turn(d):
    for out in d.turn_lines:
        assert len(out) == 1, out
        assert out[0].strip(), "empty say"


def assert_goodbye_last(d):
    good = brain.render(d.spec["closing"]["goodbye"], {"spec": d.spec, "call": d.vars})
    assert d.ended
    assert d.lines[-1].endswith(good), d.lines[-1]
    assert d.tools()[-1] == "close_call"
    assert d.tools().count("close_call") == 1


def spec_for(case):
    return (SPEC_A, W_A) if case["brief"] == "A" else (SPEC_AB, W_AB)


def run_case(cid, turns, faults=None, expected=None, **kw):
    case = copy.deepcopy(CASES[cid])
    if expected is not None:
        case["expected"] = expected
    sp, w = spec_for(case)
    d = Driver(sp, w, case, faults=faults, **kw)
    d.play(turns)
    return d


# ======================================================================= the 13 practice cases
PUB_SCRIPTS = {
    "PUB-01": ["Yes, speaking.", "14 March 1988", "4471", "Yes, I can pay it all today.", "Yes."],
    "PUB-02": ["No, this is her husband. What is this about?", "I can pay it for her if you tell me how much.",
               "She will be back tomorrow morning around eleven."],
    "PUB-03": ["Yes, that is me.", "12 July 1991", "21 August 1992", "21 July 1990", "How much do I owe?"],
    "PUB-04": ["Yes, speaking.", "30 January 1984", "2219",
               {"t": "My salary arrives on the 6th of November, I can pay then.", "u_date": "the 6th of November"},
               "Am I talking to a robot?", "Yes, that works.", "Yes."],
    "PUB-05": ["Yes.", "9 September 1990", "8846", "I lost my job last month and I cannot pay anything.",
               "Can I get a discount?", "No, I do not want to be transferred."],
    "PUB-06": ["Yes, this is Priya Nair.", "17 May 1986", "1502", "The full amount is too much right now.",
               "Yes, I can pay the minimum this Friday.", "Yes."],
    "PUB-07": ["Yes.", "5 December 1975", "7093", "No, I cannot pay today.", "Maybe the week after next.",
               "Monday the 26th.", "Yes, that is fine.", "Yes."],
    "PUB-08": ["Yes, speaking.", "28 April 1993", "3317", {"t": "I paid it in the app this morning.", "u_topic": "paid"}],
    "PUB-09": ["Yes.", "11 August 1981", "5560", "I cannot pay this amount, I want lower instalments."],
    "PUB-10": ["Yes.", "23 February 1989", "9904", "No, not today.", "Yes, I can pay the full amount this Friday.",
               "Yes."],
    "PUB-11": ["Yes.", "3 June 1987", "2288", "No, I cannot pay today.", "I can pay all three this Friday.", "Yes."],
    "PUB-12": ["Yes.", "19 October 1983", "4401", "4410", "I can pay the credit card tomorrow.", "No.", "No.", "No.",
               "Yes."],
    "PUB-13": ["Yes.", "8 January 1991", "6604", "I cannot pay today, but I can pay both on the 30th of October.",
               "Yes."],
}


@pytest.mark.parametrize("cid", sorted(PUB_SCRIPTS))
def test_practice_case_ledger_passes_kit_score(cid):
    d = run_case(cid, PUB_SCRIPTS[cid], faults=CASES[cid].get("faults"))
    r = d.score()
    assert r["pass"], (r, d.lines)
    assert_goodbye_last(d)
    assert_one_line_per_turn(d)
    assert_no_banned_before_verified(d)


@pytest.mark.parametrize("cid", sorted(PUB_SCRIPTS))
@pytest.mark.parametrize("bool_style", ["title"])
def test_practice_cases_with_title_case_booleans(cid, bool_style):
    d = run_case(cid, PUB_SCRIPTS[cid], faults=CASES[cid].get("faults"), bool_style=bool_style)
    assert d.score()["pass"], d.lines


@pytest.mark.parametrize("cid", ["PUB-01", "PUB-11", "PUB-12"])
@pytest.mark.parametrize("mode", ["flat", "repr"])
def test_practice_cases_with_other_product_list_forms(cid, mode):
    d = run_case(cid, PUB_SCRIPTS[cid], map_mode=mode)
    assert d.score()["pass"], d.lines


def test_pub01_lines_and_check_items():
    d = run_case("PUB-01", PUB_SCRIPTS["PUB-01"])
    joined = " ".join(d.lines)
    assert "Do you confirm?" in d.lines[-2]
    assert d.lines[-1].count("You will receive a text message confirming this promise.") == 1
    assert d.tools().count("create_promise") == 1
    assert d.tools()[:2] == ["verify_identity", "verify_identity"] and d.tools()[2] == "get_account"
    assert "collections" not in " ".join(d.lines[:3]).lower()
    assert "collections" in joined.lower()


def test_pub02_third_party_never_discloses_or_verifies():
    d = run_case("PUB-02", PUB_SCRIPTS["PUB-02"])
    assert "verify_identity" not in d.tools() and "get_account" not in d.tools()
    for line in d.lines:
        for w in ("loan", "payment", "debt", "owe", "collections", "310"):
            assert w not in line.lower(), line


def test_pub03_fail_line_and_no_disclosure():
    d = run_case("PUB-03", PUB_SCRIPTS["PUB-03"])
    assert d.tools().count("verify_identity") == 3
    assert "branch" in d.lines[-1]
    assert "95" not in " ".join(d.lines)


def test_pub05_single_sympathy_no_persuasion():
    d = run_case("PUB-05", PUB_SCRIPTS["PUB-05"])
    joined = " ".join(d.lines)
    assert joined.count("I'm sorry to hear that.") == 1
    assert "Could you pay" not in joined
    assert "discount" not in joined.lower().replace("get a discount", "")


def test_pub06_floor_offer_once_with_rest_note():
    d = run_case("PUB-06", PUB_SCRIPTS["PUB-06"])
    joined = " ".join(d.lines)
    assert joined.count("637.50") >= 1
    assert joined.count("The rest stays overdue.") == 1
    assert "how much can you pay" not in joined.lower()


def test_pub10_recorded_only_after_success():
    d = run_case("PUB-10", PUB_SCRIPTS["PUB-10"], faults=CASES["PUB-10"]["faults"])
    assert d.tools().count("create_promise") == 2
    assert len(d.ledger()["promises"]) == 1
    assert "promise is recorded" not in " ".join(d.lines[:-1]).lower()
    assert "Your promise is recorded." in d.lines[-1]


def test_pub11_one_readback_names_all_products():
    d = run_case("PUB-11", PUB_SCRIPTS["PUB-11"])
    rb = [l for l in d.lines if "Do you confirm?" in l]
    assert len(rb) == 1
    assert all(x in rb[0] for x in ("credit card", "personal loan", "car loan"))
    stmt = [l for l in d.lines if "past due" in l][0]
    assert stmt.count("days late") == 3


def test_pub12_attempt_counts_per_product():
    d = run_case("PUB-12", PUB_SCRIPTS["PUB-12"])
    offers = [l for l in d.lines if l.startswith("Could you pay") or "Could you pay" in l]
    loan = [l for l in offers if "1,320" in l or "440" in l]
    car = [l for l in offers if "140" in l]
    assert len(loan) == 2 and len(car) == 1, offers


def test_pub13_readback_names_both_dates_and_clamp():
    d = run_case("PUB-13", PUB_SCRIPTS["PUB-13"])
    rb = [l for l in d.lines if "Do you confirm?" in l][0]
    assert "30 October" in rb and "23 October" in rb
    assert "latest date I can record" in rb


# ======================================================================= OPN: right party / third party
def _a_case(cid="PUB-01", **over):
    case = copy.deepcopy(CASES[cid])
    case.update(over)
    return case


def run_a(turns, cid="PUB-01", expected=None, faults=None, spec=None, wiring=None, **kw):
    case = _a_case(cid)
    if expected is not None:
        case["expected"] = expected
    sp = spec or (SPEC_A if case["brief"] == "A" else SPEC_AB)
    w = wiring or (W_A if case["brief"] == "A" else W_AB)
    d = Driver(sp, w, case, faults=faults, **kw)
    d.play(turns)
    return d


def exp(outcome, reason=None, promises=(), notes=(), callbacks=(), transfers=()):
    return {"outcome": outcome, "reason": reason, "promises": list(promises), "notes": list(notes),
            "callbacks": list(callbacks), "transfers": list(transfers)}


def test_rp_greeting_then_question_after_last_ask_closes_unclear():
    d = run_a(["Hello?", "Who is this?"])
    assert d.ended and d.score(exp("not_reached", "unclear"))["pass"], d.lines
    assert d.lines[1].endswith("Am I speaking with Mr Reyes?")


def test_rp_question_first_then_confirm():
    d = run_a(["Who is this?", "Yes, speaking."])
    assert "digital assistant" in d.lines[1] and d.lines[1].endswith("Mr Reyes?")
    assert "date of birth" in d.lines[2]


def test_rp_robot_question_answered_then_reask():
    d = run_a(["Are you a robot?"])
    assert d.lines[1].startswith("I am Freya") and d.lines[1].endswith("?")


def test_rp_two_unclear_turns_close_unclear():
    d = run_a(["Hmm, what?", "Uh huh, go on."])
    assert d.score(exp("not_reached", "unclear"))["pass"], d.lines


def test_rp_bare_no_goes_to_third_party():
    d = run_a(["No."])
    assert "reach" in d.lines[1].lower()


def test_rp_wrong_number_closes():
    d = run_a(["You have the wrong number."])
    assert d.score(exp("not_reached", "wrong_number"))["pass"], d.lines


def test_rp_deceased_sorry_once_and_no_question():
    d = run_a(["I'm afraid he passed away last month."])
    assert d.score(exp("not_reached", "deceased"))["pass"], d.lines
    assert d.lines[-1].count("I am sorry for your loss.") == 1
    assert "?" not in d.lines[-1]


def test_tp_deceased_after_third_party():
    d = run_a(["No, this is his sister.", "He died last week."])
    assert d.score(exp("not_reached", "deceased"))["pass"], d.lines


def test_tp_two_outside_offers_no_callback():
    d = run_a(["No, he is at work.", "Call him at nine tonight.", "Then try at eight in the evening."])
    assert d.score(exp("not_reached", "no_callback"))["pass"], d.lines
    assert "schedule_callback" not in d.tools()


def test_tp_outside_then_valid_books():
    d = run_a(["No, he is at work.", "Call him at nine tonight.", "Tomorrow at 3 pm then."])
    r = d.score(exp("not_reached", "callback", callbacks=[{"date": "2026-10-15", "time": "15:00"}]))
    assert r["pass"], (r, d.lines)


def test_tp_vague_then_exact():
    d = run_a(["No, he is not home.", "Sometime tomorrow.", "Around 4 pm."])
    r = d.score(exp("not_reached", "callback", callbacks=[{"date": "2026-10-15", "time": "16:00"}]))
    assert r["pass"], (r, d.lines)


def test_tp_time_already_past_today_is_outside():
    d = run_a(["No, she is out.", "Call at ten this morning.", "OK, then at eleven tomorrow."])
    r = d.score(exp("not_reached", "callback", callbacks=[{"date": "2026-10-15", "time": "11:00"}]))
    assert r["pass"], (r, d.lines)


def test_tp_no_time_twice_closes_no_callback():
    d = run_a(["No, he is not here.", "I don't know.", "No idea, really."])
    assert d.score(exp("not_reached", "no_callback"))["pass"], d.lines


def test_tp_offer_to_pay_gets_fixed_line():
    d = run_a(["No, I'm his wife.", "Can I pay it for him?"])
    assert "can only speak with Mr Reyes" in d.lines[2]


def test_rp_hold_restarts_with_opening():
    d = run_a(["Hold on, I'll get him.", "Hello?", "Yes, this is Daniel."])
    assert d.lines[1] == "One moment, please."
    assert d.lines[2].startswith("Hello, I am a digital assistant") and d.lines[2].endswith("Mr Reyes?")
    assert "date of birth" in d.lines[3]


def test_rp_different_name_is_third_party():
    d = run_a(["Yes, this is Maria."])
    assert "reach" in d.lines[1].lower()


def test_callback_service_failure_twice_closes_no_callback():
    d = run_a(["No, she is out.", "Tomorrow at 2 pm."], faults=[{"tool": "schedule_callback", "fail_first_n": 2}])
    assert d.score(exp("not_reached", "no_callback"))["pass"], d.lines
    assert "call back" not in d.lines[-1].lower()


def test_callback_service_failure_once_retries():
    d = run_a(["No, she is out.", "Tomorrow at 2 pm."], faults=[{"tool": "schedule_callback", "fail_first_n": 1}])
    r = d.score(exp("not_reached", "callback", callbacks=[{"date": "2026-10-15", "time": "14:00"}]))
    assert r["pass"], (r, d.lines)


# ======================================================================= IDV: identity
def test_id_digits_in_pieces():
    d = run_a(["Yes.", "14 March 1988", "four four", "seven one", "Yes, today is fine.", "Yes."])
    assert d.lines[3] == "Yes?"
    assert d.score()["pass"], d.lines


def test_id_dob_without_year_asks_full_and_is_not_sent():
    d = run_a(["Yes.", "The fourteenth of March.", "nineteen eighty-eight"])
    assert d.tools().count("verify_identity") == 1
    assert "full date of birth" in d.lines[2]


def test_id_impossible_numeric_date_is_not_sent():
    d = run_a(["Yes.", "03/14/1988"])
    assert "verify_identity" not in d.tools()
    assert "full date of birth" in d.lines[2]


def test_id_hint_day_month_swapped_not_counted():
    case = _a_case("PUB-02")         # DOB 1979-11-02
    d = Driver(SPEC_A, W_A, case)
    d.play(["Yes, speaking.", "11/02/1979", "the second of November nineteen seventy-nine", "0358"])
    assert "month of your date of birth as a word" in d.lines[2]
    assert "phone" in d.lines[3]
    assert d.bank.wrong == 0


def test_id_decline_explain_once_then_close():
    d = run_a(["Yes.", "I'd rather not say.", "No, I won't tell you."])
    assert d.score(exp("not_verified", "declined"))["pass"], d.lines
    assert "protect your account" in d.lines[2]
    assert "verify_identity" not in d.tools()


def test_id_purpose_question_counts_as_decline():
    d = run_a(["Yes.", "What is this about?", "Why do you need that?"])
    assert d.score(exp("not_verified", "declined"))["pass"], d.lines


def test_id_robot_question_is_neutral():
    d = run_a(["Yes.", "Are you a robot?", "14 March 1988", "4471"])
    assert d.lines[2].startswith("I am Freya") and "date of birth" in d.lines[2]
    assert "past due" in d.lines[4]


def test_id_refuse_to_talk_twice_before_verification():
    d = run_a(["Yes.", "I don't want to talk to you.", "Leave me alone."])
    assert d.score(exp("not_verified", "declined"))["pass"], d.lines


def test_id_human_request_then_insist_transfers_general():
    d = run_a(["Yes.", "I want to speak to a real person.", "No, just put me through to a human."])
    r = d.score(exp("transferred", "human", transfers=[{"queue": "general"}]))
    assert r["pass"], (r, d.lines)
    assert "get_account" not in d.tools()


def test_id_human_request_then_answer_resumes():
    d = run_a(["Yes.", "Can I talk to a human?", "No, fine.", "14 March 1988", "4471", "Yes.", "Yes."])
    assert d.score()["pass"], d.lines


def test_id_three_wrong_across_questions_fail():
    d = run_a(["Yes.", "1 January 1980", "14 March 1988", "1111", "2222"])
    assert d.score(exp("not_verified", "failed"))["pass"], d.lines
    assert d.tools().count("verify_identity") == 4


def test_id_verify_transport_failure_resends_once():
    d = run_a(["Yes.", "14 March 1988", "4471", "Yes.", "Yes."], faults=[{"tool": "verify_identity", "fail_first_n": 1}])
    assert d.score()["pass"], d.lines
    assert d.tools().count("verify_identity") == 3


def test_id_answer_with_scam_question_carries_answer():
    d = run_a(["Yes.", "Is this a scam? Anyway it's 14 March 1988."])
    assert "customer service number" in d.lines[2] and "phone number" in d.lines[2]


# ======================================================================= NEG: negotiation and intents
def test_neg_below_floor_offers_floor_then_flat_refusal():
    d = run_a(["Yes.", "14 March 1988", "4471", "I can pay 50 today.", "No."])
    assert "below 126" in d.lines[4] and "126" in d.lines[4]
    # a below-floor proposal implies the full amount is too much: attempt 1 is the floor (NEG-08), never the full
    assert "Could you pay 126 by Friday, 16 October?" in d.lines[5]


def test_neg_above_full_offers_full():
    d = run_a(["Yes.", "14 March 1988", "4471", "I'll pay 500 today.", "Yes.", "Yes."])
    assert "Shall I record 420?" in d.lines[4]
    assert d.score()["pass"], d.lines


def test_neg_weekend_date_offers_next_business_day():
    d = run_a(["Yes.", "14 March 1988", "4471", "I can pay on Saturday.", "Yes.", "Yes."],
              expected=exp("promise", promises=[{"product_id": "p1", "amount": 420.0, "date": "2026-10-19"}]))
    assert "Monday, 19 October" in d.lines[4]
    assert d.score()["pass"], d.lines


def test_neg_past_date_is_not_refusal():
    d = run_a(["Yes.", "14 March 1988", "4471", "I paid on the 1st of October, no wait, I can pay on the 5th of October.",
               "OK, Friday then.", "Yes."],
              expected=exp("promise", promises=[{"product_id": "p1", "amount": 420.0, "date": "2026-10-16"}]))
    assert d.score()["pass"], d.lines


def test_neg_early_band_one_attempt_then_refused():
    d = run_a(["Yes.", "14 March 1988", "4471", "No, I can't.", "No."])
    assert d.score(exp("no_promise", "refused"))["pass"], d.lines
    assert sum("Could you pay" in l for l in d.lines) == 1


def test_neg_late_band_two_attempts_floor_on_deadline():
    d = run_a(["Yes.", "23 February 1989", "9904", "No.", "No.", "No."], cid="PUB-10",
              expected=exp("no_promise", "refused"))
    assert d.score()["pass"], d.lines
    assert "Could you pay at least 109.50 by Friday, 23 October?" in d.lines[5]


def test_neg_too_much_floor_refused_late_band_attempt2_is_floor_on_deadline():
    d = run_a(["Yes.", "17 May 1986", "1502", "That's too much.", "No, I can't.", "Yes.", "Yes."], cid="PUB-06",
              expected=exp("promise", promises=[{"product_id": "p1", "amount": 637.5, "date": "2026-10-23"}]))
    assert d.score()["pass"], d.lines
    assert "The rest stays overdue." in d.lines[4]
    assert "Friday, 23 October" in d.lines[5]


def test_neg_too_much_floor_refused_early_band_exhausted():
    d = run_a(["Yes.", "14 March 1988", "4471", "That's too much.", "No."], expected=exp("no_promise", "refused"))
    assert d.score()["pass"], d.lines


def test_neg_proposal_beats_too_much():
    d = run_a(["Yes.", "14 March 1988", "4471", "That's too much, but I can pay 200 on Friday.", "Yes."],
              expected=exp("promise", promises=[{"product_id": "p1", "amount": 200.0, "date": "2026-10-16"}]))
    assert d.score()["pass"], d.lines


def test_neg_paid_future_tense_is_a_proposal_not_paid():
    d = run_a(["Yes.", "14 March 1988", "4471", "I'll pay it tomorrow.", "Yes."],
              expected=exp("promise", promises=[{"product_id": "p1", "amount": 420.0, "date": "2026-10-15"}]))
    assert d.score()["pass"], d.lines


def test_neg_dispute_closes_no_promise_dispute():
    d = run_a(["Yes.", "14 March 1988", "4471", "This debt is not mine."], expected=exp("no_promise", "dispute"))
    assert d.score()["pass"], d.lines


def test_neg_paid_off_years_ago_is_dispute():
    d = run_a(["Yes.", "14 March 1988", "4471", {"t": "I paid that card off years ago.", "u_topic": "dispute"}],
              expected=exp("no_promise", "dispute"))
    assert d.score()["pass"], d.lines


def test_neg_hardship_accept_transfers_support():
    d = run_a(["Yes.", "14 March 1988", "4471", "I've been in hospital for weeks.", "Yes please."],
              expected=exp("transferred", "support", transfers=[{"queue": "support"}]))
    assert d.score()["pass"], d.lines


def test_neg_human_ask_then_insist():
    d = run_a(["Yes.", "14 March 1988", "4471", "I want to talk to a real person.", "No, I want a human now."],
              expected=exp("transferred", "human", transfers=[{"queue": "general"}]))
    assert d.score()["pass"], d.lines
    assert "anything I can help you with" in d.lines[4]


def test_neg_human_ask_then_other_reply_resumes():
    d = run_a(["Yes.", "14 March 1988", "4471", "Can I speak to someone real?", "I can pay it all today.", "Yes."])
    assert d.score()["pass"], d.lines


def test_neg_human_ask_then_plain_no_is_insisting():
    # review fix round 1 (rule 42): "No." to "is there anything I can help you with?" insists on the human
    d = run_a(["Yes.", "14 March 1988", "4471", "Can I speak to someone real?", "No."],
              expected=exp("transferred", "human", transfers=[{"queue": "general"}]))
    assert d.score()["pass"], d.lines


def test_neg_refuse_talk_twice_after_verification():
    d = run_a(["Yes.", "14 March 1988", "4471", "I don't want to talk to you.", "Stop calling me."],
              expected=exp("no_promise", "refused"))
    assert d.score()["pass"], d.lines


def test_neg_refusal_to_pay_is_not_refusal_to_talk():
    d = run_a(["Yes.", "14 March 1988", "4471", "I don't want to pay today.", "Yes, Friday works.", "Yes."],
              expected=exp("promise", promises=[{"product_id": "p1", "amount": 420.0, "date": "2026-10-16"}]))
    assert d.score()["pass"], d.lines


def test_neg_question_gets_no_info_and_reask():
    d = run_a(["Yes.", "14 March 1988", "4471", "What is the interest rate on this?"])
    assert d.lines[4].startswith("I'm sorry, I don't have that information.")
    assert d.lines[4].endswith("Can you make this payment today?")


def test_neg_forbidden_offer_answered():
    d = run_a(["Yes.", "14 March 1988", "4471", "Can I get a discount?"])
    assert "can't offer that" in d.lines[4]


def test_neg_hedge_is_non_answer_uses_attempt():
    d = run_a(["Yes.", "14 March 1988", "4471", "Maybe, I'm not sure.", "Maybe."], expected=exp("no_promise", "refused"))
    assert d.score()["pass"], d.lines


def test_neg_unclear_twice_counts_as_non_answer():
    d = run_a(["Yes.", "14 March 1988", "4471", "Blue elephants.", "Purple."])
    assert d.lines[4].startswith("Sorry, could you say that again?")
    assert "Could you pay 420 by Friday" in d.lines[5]


def test_neg_vague_twice_proposes_deadline():
    d = run_a(["Yes.", "14 March 1988", "4471", "Sometime next week.", "When my salary comes.", "Yes.", "Yes."],
              expected=exp("promise", promises=[{"product_id": "p1", "amount": 420.0, "date": "2026-11-02"}]))
    assert "Which exact day" in d.lines[4]
    assert "latest date I can record is Monday, 2 November" in d.lines[5]
    assert d.score()["pass"], d.lines


def test_neg_restructure_drops_unrecorded_and_transfers():
    d = run_a(["Yes.", "14 March 1988", "4471", "Yes.", "Actually, can I get a new payment plan instead?"],
              expected=exp("transferred", "restructuring", transfers=[{"queue": "restructuring"}]))
    assert d.score()["pass"], d.lines
    assert "create_promise" not in d.tools()


# ======================================================================= CONF: read-back
def test_conf_change_date_reads_back_again():
    d = run_a(["Yes.", "14 March 1988", "4471", "Yes.", "Actually, make it Friday.", "Yes."],
              expected=exp("promise", promises=[{"product_id": "p1", "amount": 420.0, "date": "2026-10-16"}]))
    assert d.score()["pass"], d.lines
    assert sum("Do you confirm?" in l for l in d.lines) == 2


def test_conf_bare_no_asks_what_to_change_then_refusal_reopens_ladder():
    d = run_a(["Yes.", "14 March 1988", "4471", "Yes.", "No.", "I just can't do it.", "No."],
              expected=exp("no_promise", "refused"))
    assert "What would you like to change?" in d.lines[5]
    assert d.score()["pass"], d.lines


def test_conf_hedge_twice_is_refusal():
    d = run_a(["Yes.", "14 March 1988", "4471", "Yes.", "I hope so, maybe.", "I think so, probably.", "No."],
              expected=exp("no_promise", "refused"))
    assert d.lines[5].endswith("Do you confirm?")
    assert d.score()["pass"], d.lines


def test_conf_change_after_deadline_offers_deadline():
    d = run_a(["Yes.", "14 March 1988", "4471", "Yes.", "Actually, can I pay on the 20th of November?", "OK.", "Yes."],
              expected=exp("promise", promises=[{"product_id": "p1", "amount": 420.0, "date": "2026-11-02"}]))
    assert d.score()["pass"], d.lines


def test_conf_change_promise_question_answered():
    d = run_a(["Yes.", "14 March 1988", "4471", "Yes.", "Can I change the promise later?"])
    assert "cannot be changed" in d.lines[5] or "can't" in d.lines[5]


# ======================================================================= TOOL failures
def test_promise_fails_twice_service_error_honest():
    d = run_a(["Yes.", "14 March 1988", "4471", "Yes.", "Yes."], faults=[{"tool": "create_promise", "fail_first_n": 2}],
              expected=exp("no_promise", "service_error"))
    assert d.score()["pass"], d.lines
    assert "could not record" in d.lines[-1]
    assert "is recorded" not in d.lines[-1]
    assert "text message" not in d.lines[-1]


def test_account_failure_twice_closes_service_error():
    d = run_a(["Yes.", "14 March 1988", "4471"], faults=[{"tool": "get_account", "fail_first_n": 2}],
              expected=exp("no_promise", "service_error"))
    assert d.score()["pass"], d.lines
    assert "can't access the account" in d.lines[-1]


def test_account_failure_once_retries():
    d = run_a(["Yes.", "14 March 1988", "4471", "Yes.", "Yes."], faults=[{"tool": "get_account", "fail_first_n": 1}])
    assert d.score()["pass"], d.lines


def test_transfer_failure_retry_then_success():
    d = run_a(["Yes.", "11 August 1981", "5560", "I want lower instalments."], cid="PUB-09",
              faults=[{"tool": "transfer_to_agent", "fail_first_n": 1}])
    assert d.score()["pass"], d.lines


def test_transfer_failure_twice_closes_service_error():
    d = run_a(["Yes.", "11 August 1981", "5560", "I want lower instalments."], cid="PUB-09",
              faults=[{"tool": "transfer_to_agent", "fail_first_n": 2}], expected=exp("no_promise", "service_error"))
    assert d.score()["pass"], d.lines
    assert "transfer you" not in d.lines[-1]


# ======================================================================= MUL: Brief B
def test_mul_yes_all_today():
    d = run_a(["Yes.", "3 June 1987", "2288", "Yes, I can pay all of them today.", "Yes."], cid="PUB-11",
              expected=exp("promise", promises=[{"product_id": "p1", "amount": 220.0, "date": "2026-10-14"},
                                                {"product_id": "p2", "amount": 640.0, "date": "2026-10-14"},
                                                {"product_id": "p3", "amount": 75.0, "date": "2026-10-14"}]))
    assert d.score()["pass"], d.lines


def test_mul_dispute_one_product_continues_with_note():
    d = run_a(["Yes.", "3 June 1987", "2288", "No.", "The credit card is not mine.", "Yes.", "Yes.", "Yes."],
              cid="PUB-11",
              expected=exp("promise", promises=[{"product_id": "p2", "amount": 640.0, "date": "2026-10-16"},
                                                {"product_id": "p3", "amount": 75.0, "date": "2026-10-16"}],
                           notes=[{"product_id": "p1", "reason": "dispute"}]))
    r = d.score()
    assert r["pass"], (r, d.lines)


def test_mul_all_refused_notes_each_and_no_promise_refused():
    d = run_a(["Yes.", "3 June 1987", "2288", "No.", "No.", "No.", "No.", "No.", "No."], cid="PUB-11",
              expected=exp("no_promise", "refused", notes=[{"product_id": "p1", "reason": "refused"},
                                                            {"product_id": "p2", "reason": "refused"},
                                                            {"product_id": "p3", "reason": "refused"}]))
    r = d.score()
    assert r["pass"], (r, d.lines)


def test_mul_paid_all_closes_paid_with_paid_notes():
    d = run_a(["Yes.", "3 June 1987", "2288", {"t": "I already paid all of them yesterday.", "u_topic": "paid"}],
              cid="PUB-11",
              expected=exp("paid", None, notes=[{"product_id": "p1", "reason": "paid"},
                                                 {"product_id": "p2", "reason": "paid"},
                                                 {"product_id": "p3", "reason": "paid"}]))
    r = d.score()
    assert r["pass"], (r, d.lines)


def test_mul_hardship_decline_notes_all_remaining():
    d = run_a(["Yes.", "3 June 1987", "2288", "I lost my job, I can't pay.", "No thanks."], cid="PUB-11",
              expected=exp("no_promise", "hardship", notes=[{"product_id": "p1", "reason": "hardship"},
                                                             {"product_id": "p2", "reason": "hardship"},
                                                             {"product_id": "p3", "reason": "hardship"}]))
    r = d.score()
    assert r["pass"], (r, d.lines)


def test_mul_restructure_after_agreement_no_notes_no_promises():
    d = run_a(["Yes.", "3 June 1987", "2288", "I can pay the credit card today.", "Can I get lower instalments?"],
              cid="PUB-11", expected=exp("transferred", "restructuring", transfers=[{"queue": "restructuring"}]))
    r = d.score()
    assert r["pass"], (r, d.lines)
    assert "add_note" not in d.tools()


def test_mul_one_promise_fails_twice_service_error_note_others_kept():
    d = run_a(PUB_SCRIPTS["PUB-11"], cid="PUB-11",
              faults=[{"tool": "create_promise", "fail_calls": [1, 2]}],
              expected=exp("promise", promises=[{"product_id": "p2", "amount": 640.0, "date": "2026-10-16"},
                                                {"product_id": "p3", "amount": 75.0, "date": "2026-10-16"}],
                           notes=[{"product_id": "p1", "reason": "service_error"}]))
    r = d.score()
    assert r["pass"], (r, d.lines)
    assert "could not record" in d.lines[-1]


def test_mul_offer_names_product():
    d = run_a(["Yes.", "3 June 1987", "2288", "No."], cid="PUB-11")
    assert "credit card ending 2288" in d.lines[4]


def test_mul_too_much_at_combined_ask_floor_for_first_product():
    d = run_a(["Yes.", "3 June 1987", "2288", "That's too much."], cid="PUB-11")
    assert "66" in d.lines[4] and "credit card" in d.lines[4]


# ======================================================================= spec variants (hidden-brief generality)
def _variant(spec, fn):
    s = copy.deepcopy(spec)
    fn(s)
    return s


def test_variant_currency_symbol_and_custom_lines():
    def f(s):
        s["bank"]["currency"] = {"symbol": "$", "word": "", "position": "before"}
    d = run_a(["Yes.", "14 March 1988", "4471"], spec=_variant(SPEC_A, f))
    assert "$420 past due" in d.lines[3]


def test_variant_notes_enabled_single_product():
    def f(s):
        s["notes"]["enabled"] = True
    d = run_a(["Yes.", "14 March 1988", "4471", "No.", "No."], spec=_variant(SPEC_A, f), wiring=W_AB,
              expected=exp("no_promise", "refused", notes=[{"product_id": "p1", "reason": "refused"}]))
    assert d.score()["pass"], d.lines


def test_variant_no_chain_wiring():
    w = copy.deepcopy(W_AB)
    w["chain"] = False
    d = run_a(PUB_SCRIPTS["PUB-12"], cid="PUB-12", wiring=w)
    assert d.score()["pass"], d.lines


def test_variant_three_attempt_ladder_and_one_band():
    def f(s):
        s["bands"] = [{"key": "all", "days_late_min": 1, "days_late_max": 90,
                       "deadline": {"kind": "nth_business_day_after_today", "n": 10}, "attempts": 3}]
        s["negotiation"]["ladder"] = [
            {"key": "a", "attempt": 1, "bands": ["all"], "amount": {"kind": "full"},
             "date": {"kind": "next_business_day"}, "line": "Could you pay <amount> on <date>?"},
            {"key": "b", "attempt": 2, "bands": ["all"], "amount": {"kind": "percent_of_full", "pct": 50},
             "date": {"kind": "deadline"}, "line": "Could you pay <amount> by <date>?"},
            {"key": "c", "attempt": 3, "bands": ["all"], "amount": {"kind": "floor"},
             "date": {"kind": "deadline"}, "line": "Could you manage <amount> by <date>?"}]
    d = run_a(["Yes.", "14 March 1988", "4471", "No.", "No.", "No.", "Yes.", "Yes."], spec=_variant(SPEC_A, f),
              expected=exp("promise", promises=[{"product_id": "p1", "amount": 126.0, "date": "2026-10-29"}]))
    assert "Could you pay 420 on Thursday, 15 October?" in d.lines[4]
    assert "Could you pay 210 by Thursday, 29 October?" in d.lines[5]
    assert d.score()["pass"], d.lines


def test_variant_three_identity_questions_order():
    def f(s):
        q3 = copy.deepcopy(s["identity"]["questions"][1])
        q3.update({"key": "again", "ask": "One more: the last four digits again?"})
        s["identity"]["questions"].append(q3)
    d = run_a(["Yes.", "14 March 1988", "4471", "4471"], spec=_variant(SPEC_A, f))
    # mock bank reports all verified after two fields; the third question is never needed
    assert "past due" in d.lines[3]


def test_variant_bye_apinode_mode():
    w = copy.deepcopy(W_A)
    w["bye_mode"] = "apinode"
    d = run_a(PUB_SCRIPTS["PUB-01"], wiring=w)
    assert d.score()["pass"], d.lines


# ======================================================================= unit: render / amounts / outcome / io
def _ctx(**kw):
    sp = runtime_spec(SPEC_AB)
    d = {"spec": sp, "call": {"title": "Ms", "last_name": "Doe", "first_name": "Jo"}}
    d.update(kw)
    return d


def test_render_placeholders():
    p = {"type": "credit_card", "due": 212510, "floor": 63750, "dl": 12, "dead": "2026-10-23",
         "f": {"card_last4": "1903"}}
    out = brain.render("<customer>: <product> is <days_late> days late, <past_due> due, floor <floor>, by <deadline>.",
                       _ctx(prod=p, today=__import__("datetime").date(2026, 10, 14)))
    assert out == "Ms Doe: credit card ending 1903 is 12 days late, 2,125.10 due, floor 637.50, by Friday, 23 October."


def test_render_unknown_placeholder_and_bad_input():
    assert brain.render("Hi <nope> there", _ctx()) == "Hi there"
    assert brain.render(None, None) == ""
    assert brain.render("<self>", _ctx()) == "Freya Bank's digital assistant"


def test_render_unknown_type_spoken():
    out = brain.render("your <product>", _ctx(prod={"type": "mystery", "f": {}}))
    assert out == "your account"


def test_eval_amount_kinds():
    p = {"due": 42000, "floor": 12600, "tm": 0, "f": {"x": "99.99"}}
    ea = brain.eval_amount
    assert ea({"kind": "full"}, p, {}) == 42000
    assert ea({"kind": "floor"}, p, {}) == 12600
    assert ea({"kind": "field", "field": "x"}, p, {}) == 9999
    assert ea({"kind": "percent_of_full", "pct": 33}, p, {}) == 13860
    assert ea({"kind": "percent_of_full", "pct": 33.333, "rounding": "floor"}, p, {}) == 13999
    assert ea({"kind": "fixed", "value": 50}, p, {}) == 5000
    assert ea({"kind": "min", "args": [{"kind": "full"}, {"kind": "fixed", "value": 100}]}, p, {}) == 10000
    assert ea({"kind": "max", "args": [{"kind": "floor"}, {"kind": "fixed", "value": 100}]}, p, {}) == 12600
    assert ea({"kind": "floor_if_too_much_else_full"}, p, {}) == 42000
    assert ea({"kind": "floor_if_too_much_else_full"}, dict(p, tm=1), {}) == 12600
    assert ea({"kind": "floor"}, dict(p, floor=None), {}) == 42000
    assert ea(None, None, None) == 0


@pytest.mark.parametrize("v,c", [(420.0, 42000), ("2125.1", 212510), ("2,125.10", 212510), (637.5, 63750),
                                 ("109.5", 10950), (12, 1200), ("0.015", 2), ("", None), (None, None), (True, None)])
def test_cents(v, c):
    assert brain._b_cents(v) == c


def test_resolve_outcome_table():
    sp = runtime_spec(SPEC_AB)
    ro = brain.resolve_outcome
    assert ro(sp, {"ph": "RP"}) == ("not_reached", "unclear", "r")
    assert ro(sp, {"ph": "TP"}) == ("not_reached", "no_callback", "r")
    assert ro(sp, {"ph": "ID"}) == ("not_verified", "declined", "r")
    prods = [{"sit": "S_PAID"}, {"sit": "S_DISPUTE"}, {"sit": ""}]
    assert ro(sp, {"ph": "NEG", "prods": prods}) == ("no_promise", "dispute", "r")
    assert ro(sp, {"ph": "NEG", "prods": [{"sit": "S_PAID"}, {"sit": "S_PAID"}]}) == ("paid", "", "n")
    assert ro(sp, {"ph": "NEG", "prods": [{"sit": "S_PAID"}, {"sit": "", "rec": 1}]}) == ("promise", "", "n")
    assert ro(sp, {"ph": "NEG", "prods": [{"rec": 1}], "xfer": {"sit": "S_RESTRUCTURE_TRANSFER"}}) == (
        "transferred", "restructuring", "r")
    assert ro(sp, {"ph": "NEG", "prods": [{"sit": "S_PAID"}, {"sit": ""}]}) == ("no_promise", "refused", "r")
    assert ro(sp, {"ph": "ID", "csit": "S_ID_FAILED"}) == ("not_verified", "failed", "r")
    assert ro({}, {}) == ("", "", "n")


def test_read_result_fallbacks():
    w = W_A
    assert brain.read_result({"r_a_acct_1_s": "true"}, w, "a_acct_1", "s") == "true"
    assert brain.read_result({"r_a_acct_1_s": "pending", "a_acct_1_response.data.ok": "True"}, w, "a_acct_1",
                             "s") == "True"
    assert brain.read_result({"get_account_response.data.ok": "true"}, w, "a_acct_1", "s") == "true"
    assert brain.read_result({"get_account_response.data.ok": "true"}, w, "a_acct_1", "s",
                             tool_fallback=False) == "pending"
    assert brain.read_result({}, w, "a_acct_1", "s") == "pending"
    assert brain.read_result({"r_a_acct_1_s": "None"}, w, "a_acct_1", "s") == "pending"
    assert brain.read_result(None, None, None, None) == "pending"


@pytest.mark.parametrize("val", [
    [{"product_id": "p1", "past_due": 420}],
    '[{"product_id": "p1", "past_due": 420}]',
    "[{'product_id': 'p1', 'past_due': 420.0, 'flag': True, 'x': None}]",
])
def test_read_products_forms(val):
    out = brain.read_products({"r_a_acct_1_products": val}, W_A, "a_acct_1")
    assert out and out[0]["product_id"] == "p1"


def test_read_products_flattened_keys():
    v = {"a_acct_1_response.data.products.0.product_id": "p1", "a_acct_1_response.data.products.0.past_due": 420,
         "a_acct_1_response.data.products.1.product_id": "p2"}
    out = brain.read_products(v, W_A, "a_acct_1")
    assert [p["product_id"] for p in out] == ["p1", "p2"]


def test_read_products_garbage():
    assert brain.read_products({"r_a_acct_1_products": "{{oops"}, W_A, "a_acct_1") == []
    assert brain.read_products({}, W_A, "a_acct_1") == []


# ======================================================================= main() / step() robustness
def _R():
    return {"v": 1, "spec": runtime_spec(SPEC_A), "wiring": W_A}


def test_main_accepts_hex_rspec_and_writes_nx_last():
    from runtime.bundle import rspec_hex

    class V(dict):
        order = []

        def __setitem__(self, k, v):
            self.order.append(k)
            dict.__setitem__(self, k, v)
    v = V(CASES["PUB-01"]["variables"])
    v["customer_id"] = "c1"
    v["u_text"] = "Yes, speaking."
    V.order = []
    brain.main(v, rspec_hex(_R()))
    assert v.order[0] == "nx" and v.order[-1] == "nx"
    assert v["nx"] == "s_id" and v["ph"] == "ID"
    assert all(isinstance(x, str) for x in dict(v).values())
    assert "}}" not in v["st"] and "{{" not in v["st"]
    assert v["u_text"] == ""


@pytest.mark.parametrize("bad_vars", [{}, {"st": "not json"}, {"st": "[1,2]", "u_text": None},
                                      {"now": "garbage", "u_text": "yes"}])
def test_main_never_raises_on_bad_vars(bad_vars):
    v = dict(bad_vars)
    brain.main(v, _R())
    assert v["nx"] in W_A["listen"].values() or v["nx"] in W_A["nodes"] or v["nx"] == "s_bye"


def test_main_never_raises_on_bad_rspec():
    v = {}
    brain.main(v, "zz-not-hex")
    assert v["nx"] == "s_safe"


def test_step_error_path_then_second_error_closes(monkeypatch):
    R = _R()
    st = {"ph": "NEG", "await": "s_neg", "prods": [], "offer": {"kind": "first_ask", "k": 0}}
    inp = {"call": dict(CASES["PUB-01"]["variables"]), "sensors": {"u_text": "yes"}, "results": {}}

    def boom(c):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(brain, "_b_neg_turn", boom)
    st1, w1 = brain.step(R, st, inp)
    assert w1["nx"] == "s_neg" and w1["say"] == SPEC_A["lines"]["clarify"] and "kaboom" in w1["dbg_err"]
    assert st1["errs"] == 1
    st2, w2 = brain.step(R, st1, inp)
    assert w2["nx"] == "s_bye" and w2["say"].endswith("Goodbye.")


def test_turn_cap_closes():
    R = _R()
    st = {"ph": "RP", "await": "s_rp", "turns": 40, "rp": {"asks": 1}}
    inp = {"call": dict(CASES["PUB-01"]["variables"]), "sensors": {"u_text": "Hello?"}, "results": {}}
    _st, w = brain.step(R, st, inp)
    assert w["nx"] == "s_bye"


def _plan_writes(R, st):
    """Write-chain plan (C.8) for st -> var writes: promises of agreed products + notes, else the close flow."""
    c = brain._b_ctx(R, st, {"call": (st or {}).get("_call") or dict(), "sensors": dict(), "results": dict()})
    if any(p.get("ag") and not p.get("rec") for p in st.get("prods") or []):
        brain._b_write(c, [])
    else:
        brain._b_close(c, [])
    _st, w = brain._b_finish(c)
    return w


def test_plan_writes_for_agreed_product():
    R = _R()
    st = {"ph": "CONF", "_call": dict(CASES["PUB-01"]["variables"]),
          "prods": [{"id": "p1", "type": "credit_card", "due": 42000, "floor": 12600, "dl": 6, "f": {},
                     "ag": [42000, "2026-10-14"], "rec": 0, "sit": ""}]}
    w = _plan_writes(R, st)
    assert w["nx"] == "a_promise_1_1"
    assert w["b_a_promise_1_1_amount"] == "420.00" and w["b_a_promise_1_1_date"] == "2026-10-14"
    assert w["b_a_promise_1_1_product_id"] == "p1"
    assert w["r_a_promise_1_1_s"] == "pending" and w["wn_a_promise_1_1"] == "s_bye"
    assert (w["co"], w["cr"], w["cmode"]) == ("promise", "", "n")


def test_close_reasonless_uses_close_n_and_reason_uses_close_r():
    d = run_case("PUB-08", PUB_SCRIPTS["PUB-08"])
    assert "a_close_n" in d.path
    last = d.ledger()["calls"][-1]
    assert "reason" not in last["args"]
    d2 = run_case("PUB-09", PUB_SCRIPTS["PUB-09"])
    assert "a_close_r" in d2.path


# ======================================================================= later fixes (scenario-driven)
def test_id_hardship_before_verification_is_neutral_and_dispatched_after_statement():
    d = run_a(["Yes.", "I lost my job last month.", "14 March 1988", "4471", "No thanks."],
              expected=exp("no_promise", "hardship"))
    assert d.lines[2].startswith("I understand.") and "date of birth" in d.lines[2]
    assert "past due" in d.lines[4] and "support team" in d.lines[4]
    assert "Can you make this payment today?" not in d.lines[4]
    assert d.score()["pass"], d.lines


def test_id_paid_claim_with_answer_is_stashed_and_verify_still_sent():
    d = run_a(["Yes.", {"t": "I already paid it. My birthday is 14 March 1988.", "u_topic": "paid"}, "4471"],
              expected=exp("paid"))
    assert d.score()["pass"], d.lines
    assert "one business day" in d.lines[-1]


def test_id_discount_request_is_not_a_decline():
    d = run_a(["Yes.", "Can't you just give me a discount?", "Why do you even need that?", "14 March 1988", "4471"])
    assert "past due" in d.lines[-1]


def test_id_dob_year_as_tens_word_with_final_period():
    d = run_a(["Yes.", "The fourteenth of March, nineteen eighty.", "4471"], expected=exp("not_verified", "failed"))
    assert d.tools().count("verify_identity") == 1      # 1980-03-14 was sent (and is wrong for this case)


def test_mul_clause_binding_one_value_clause():
    d = run_a(["Yes.", "19 October 1983", "4410",
               "No. I'll pay the credit card tomorrow, but I'm not paying the personal loan or the car loan.",
               "No.", "No.", "No.", "Yes."], cid="PUB-12")
    assert d.score()["pass"], d.lines


def test_conf_refusal_naming_one_product_reopens_only_that_product():
    d = run_a(["Yes.", "3 June 1987", "2288", "Yes, all of them today.", "No, not the personal loan.", "No.", "No.",
               "Yes."], cid="PUB-11",
              expected=exp("promise", promises=[{"product_id": "p1", "amount": 220.0, "date": "2026-10-14"},
                                                {"product_id": "p3", "amount": 75.0, "date": "2026-10-14"}],
                           notes=[{"product_id": "p2", "reason": "refused"}]))
    r = d.score()
    assert r["pass"], (r, d.lines)


@pytest.mark.parametrize("cid", sorted(PUB_SCRIPTS))
def test_judge_style_invariants_on_practice_cases(cid):
    d = run_case(cid, PUB_SCRIPTS[cid], faults=CASES[cid].get("faults"))
    sp = d.spec
    for rs in sp["required_sentences"]:
        if rs.get("once"):
            assert " ".join(d.lines).count(rs["text"]) <= 1, rs["id"]
    for i, line in enumerate(d.lines[:-1]):
        assert "promise is recorded" not in line.lower() and "promises are recorded" not in line.lower()
        assert "goodbye" not in line.lower(), (i, line)
    never = [w.lower() for w in sp["banned"]["never_ask"]]
    for line in d.lines:
        for w in never:
            assert w not in line.lower()
        for w in sp["negotiation"]["forbidden_offers"]:
            assert not re.search(r"\b(offer|give|propose)\b[^.?]*\b" + re.escape(w), line.lower()), line


# ======================================================================= more spec / wiring variants
def test_variant_rp_greeting_reask_free_allows_extra_ask():
    def f(s):
        s["interpretation"]["rp_greeting_first_turn"] = "reask_free"
    d = run_a(["Hello?", "Hmm, sorry?", "Yes, speaking."], spec=_variant(SPEC_A, f))
    assert "date of birth" in d.lines[3]


def test_variant_rp_question_after_last_ask_allows_one_more():
    def f(s):
        s["interpretation"]["rp_question_after_last_ask"] = "answer_and_allow_one_more"
    d = run_a(["Hello?", "Who is this?", "Ah OK, yes, speaking."], spec=_variant(SPEC_A, f))
    assert "digital assistant" in d.lines[2] and "date of birth" in d.lines[3]


def test_variant_call_scope_note_planned():
    def f(s):
        s["notes"].update({"enabled": True, "scope": "call"})
    w = copy.deepcopy(W_A)
    w["nodes"]["a_note_call_1"] = {"tool": "add_note", "body": {"reason": "b_a_note_call_1_reason"},
                                  "res": {"s": "r_a_note_call_1_s", "err": "r_a_note_call_1_err"},
                                  "res_leaf": {"s": "ok", "err": "error"}}
    w["api"]["note_call"] = ["a_note_call_1"]
    w["chainable"] = sorted(w["chainable"] + ["a_note_call_1"])
    d = run_a(["Yes.", "14 March 1988", "4471", "This debt is not mine."], spec=_variant(SPEC_A, f), wiring=w,
              expected=exp("no_promise", "dispute"))
    assert "a_note_call_1" in d.path
    assert d.vars.get("b_a_note_call_1_reason") == "dispute"
    assert d.score()["pass"], d.lines


def test_variant_no_callback_nodes_closes_no_callback():
    w = copy.deepcopy(W_A)
    w["api"]["cb"] = []
    d = run_a(["No, she is out.", "Tomorrow at 2 pm."], wiring=w)
    assert d.score(exp("not_reached", "no_callback"))["pass"], d.lines


def test_per_field_identity_mode_writes_field_named_body():
    R = {"v": 1, "spec": runtime_spec(SPEC_A), "wiring": copy.deepcopy(W_A)}
    W = R["wiring"]
    W["identity_mode"] = "per_field"
    W["nodes"]["a_verify_1"]["body"] = {"date_of_birth": "b_a_verify_1_date_of_birth",
                                        "phone_last4": "b_a_verify_1_phone_last4"}
    st = {"ph": "ID", "await": "s_id", "rp": {"asks": 1},
          "id": {"qi": 0, "wrong": 0, "wq": {}, "hints": {}, "dec": {}, "expl": 0, "frag": "", "vi": 0, "turns": 0}}
    inp = {"call": dict(CASES["PUB-01"]["variables"]), "sensors": {"u_text": "14 March 1988"}, "results": {}}
    _st, w = brain.step(R, st, inp)
    assert w["nx"] == "a_verify_1"
    assert w["b_a_verify_1_date_of_birth"] == "1988-03-14"
    assert "b_a_verify_1_phone_last4" not in w


def test_scale_100_amount_wire_and_custom_date_format():
    R = {"v": 1, "spec": runtime_spec(SPEC_A), "wiring": copy.deepcopy(W_A)}
    R["wiring"]["wire"]["create_promise.amount"]["scale"] = 100
    R["wiring"]["wire"]["create_promise.date"]["format"] = "%d/%m/%Y"
    st = {"ph": "CONF", "_call": dict(CASES["PUB-01"]["variables"]),
          "prods": [{"id": "p1", "type": "credit_card", "due": 212510, "floor": 63750, "dl": 6, "f": {},
                     "ag": [63750, "2026-10-16"], "rec": 0, "sit": ""}]}
    w = _plan_writes(R, st)
    assert w["b_a_promise_1_1_amount"] == "63750" and w["b_a_promise_1_1_date"] == "16/10/2026"


def test_pub05_live_decline_plus_plan_request_keeps_hardship():
    """LIVE 2026-10-11 (chat, persona): declining the support offer while asking for a plan in the same breath
    must close as the declined offer (the offering intent outranks the restructure transfer), not transfer."""
    d = run_case("PUB-05", ["Yes, this is Mr Novak speaking.", "9 September 1990", "Eight eight four six.",
                            "No, I'm afraid I cannot make a payment today. I lost my job last month and I'm in a "
                            "difficult situation financially.",
                            "No, I don't want to be transferred. I was hoping we could discuss whether there's any "
                            "way to reduce what I owe or work out a payment plan."])
    assert "transfer_to_agent" not in d.tools()
    assert d.tools()[-1] == "close_call"


# ======================================================================= review fix round 1 (regressions)
P07_ID = ["Yes.", "5 December 1975", "7093"]
P10_ID = ["Yes.", "23 February 1989", "9904"]
P05_ID = ["Yes.", "9 September 1990", "8846"]
P11_ID = ["Yes.", "3 June 1987", "2288"]


def test_r1_yes_to_what_to_change_is_not_a_confirmation():
    for reply in ("Yes, the date.", "Yes."):
        d = run_a(P07_ID + ["I can pay on Friday.", "No.", reply], cid="PUB-07")
        assert "create_promise" not in d.tools(), (reply, d.lines)
        assert d.lines[-2] == "What would you like to change?"
    d = run_a(P07_ID + ["I can pay on Friday.", "No.", "Yes."], cid="PUB-07")
    assert d.lines[-1].endswith("Do you confirm?")
    d = run_a(P07_ID + ["I can pay on Friday.", "No.", "Yes, the date.", "Monday.", "Yes."], cid="PUB-07",
              expected=exp("promise", promises=[{"product_id": "p1", "amount": 540.0, "date": "2026-10-19"}]))
    assert d.score()["pass"], d.lines


def test_r1_naming_the_floor_to_reject_it_is_not_a_proposal():
    d = run_a(P10_ID + ["The minimum is too much for me."], cid="PUB-10")
    assert "Do you confirm?" not in d.lines[-1] and "109.50" in d.lines[-1]
    d = run_a(P10_ID + ["Even the minimum is too much."], cid="PUB-10")
    assert "Do you confirm?" not in d.lines[-1]


def test_r1_lower_instalments_during_hardship_offer_repeats_only_the_question():
    d = run_a(P05_ID + ["I lost my job last month.", "I don't know. Can I get lower instalments instead?"], cid="PUB-05")
    # PUB-05 official sims: the support team is offered once; a re-ask with nothing answered is the neutral one
    assert d.lines[-1] == SPEC_A["lines"]["neutral_reask"]
    assert "create_promise" not in d.tools()


@pytest.mark.parametrize("reply", ["I can pay nothing.", "I can pay zero.", "Fine, whatever.",
                                   "How much do I owe exactly?", "Do I have to pay today?",
                                   "Yes, I can pay it, just not today."])
def test_r1_first_ask_replies_that_are_not_an_agreement(reply):
    d = run_a(P10_ID + [reply], cid="PUB-10")
    assert "Do you confirm?" not in d.lines[-1], d.lines
    if not d.ended:
        d.turn("Yes.")
    assert not any(c["tool"] == "create_promise" and c["args"].get("date") == "2026-10-14" and
                   c["args"].get("amount") == "365.00" for c in d.ledger()["calls"]), d.lines


def test_r1_question_about_the_amount_is_answered_from_the_account():
    for q in ("How much is it?", "What do I owe?"):
        d = run_a(P07_ID + [q], cid="PUB-07")
        assert "540 past due" in d.lines[-1] and "don't have that information" not in d.lines[-1]
    d = run_a(P07_ID + ["Why are you calling me?"], cid="PUB-07")
    assert "collections team" in d.lines[-1]
    d = run_a(P07_ID + ["Hello? Are you there?"], cid="PUB-07")
    assert d.lines[-1].startswith("Yes, I am here.")


def test_r1_third_party_callback_keeps_the_day_across_turns():
    d = run_a(["No, this is her husband.", "Call her tomorrow.", "In the afternoon.", "Around three."], cid="PUB-02",
              expected=exp("not_reached", "callback", callbacks=[{"date": "2026-10-15", "time": "15:00"}]))
    r = d.score()
    assert r["pass"], (r, d.lines)
    assert not any("only arrange a call back" in l for l in d.lines)


def test_r1_third_party_hour_in_the_evening_is_exact():
    d = run_a(["No, he is at work.", "Call him tomorrow at 9.", "Then 8 in the evening."],
              expected=exp("not_reached", "no_callback"))
    assert d.score()["pass"], d.lines


def test_r1_confirmed_customer_mentioning_a_death_is_not_deceased():
    d = run_a(["Yes, speaking. Sorry, my father died last week, it is a bad time."], cid="PUB-05")
    assert not d.ended and "date of birth" in d.lines[-1]
    assert "I'm sorry to hear that." in d.lines[-1]
    d = run_a(["Yes, speaking. Sorry, my father died last week, it is a bad time.", "9 September 1990", "8846"],
              cid="PUB-05")
    # the hardship offer comes after the statement, without a second sympathy sentence
    assert d.lines[-1].endswith("Would you like me to connect you with our customer support team?")
    assert d.lines[-1].count("sorry to hear") == 0
    d = run_a(["Speaking. Is this about the wrong number you called yesterday?"], cid="PUB-05")
    assert not d.ended and "date of birth" in d.lines[-1]


def test_r1_yes_with_a_question_or_greeting_confirms():
    d = run_a(["Hi, yes."])
    assert "date of birth" in d.lines[-1]
    d = run_a(["Yes, what is this about?"])
    assert "date of birth" in d.lines[-1] and "collections" not in d.lines[-1]
    d = run_a(["Yes, who is this?", "14 March 1988"])
    assert "last four digits" in d.lines[-1]


@pytest.mark.parametrize("name", ["Daniel.", "Daniel Reyes.", "Mr Reyes.", "Reyes."])
def test_r1_own_name_alone_confirms(name):
    d = run_a([name])
    assert "date of birth" in d.lines[-1]


def test_r1_paid_off_in_the_past_is_a_dispute():
    for t in ({"t": "I paid that off last year.", "u_topic": "paid"}, "I paid that off last year.",
              "I closed that card years ago."):
        d = run_a(P10_ID + [t], cid="PUB-10", expected=exp("no_promise", "dispute"))
        assert d.score()["pass"], (t, d.lines)
    d = run_a(P10_ID + [{"t": "I already paid it this morning.", "u_topic": "paid"}], cid="PUB-10",
              expected=exp("paid"))
    assert d.score()["pass"], d.lines


def test_r1_below_floor_refused_never_escalates_to_full():
    d = run_a(P10_ID + ["I can pay 50 on Friday.", "No.", "No."], cid="PUB-10", expected=exp("no_promise", "refused"))
    assert d.score()["pass"], d.lines
    assert not any("365 by" in l for l in d.lines), d.lines
    assert "109.50 by Friday, 23 October" in d.lines[-2]


def test_r1_human_insist_after_help_question_transfers():
    x = exp("transferred", "human", transfers=[{"queue": "general"}])
    d = run_a(P10_ID + ["I want to speak to a human.", "No, just put me through."], cid="PUB-10", expected=x)
    assert d.score()["pass"], d.lines
    d = run_a(P10_ID + ["I want to speak to a human.", "Transfer me now."], cid="PUB-10", expected=x)
    assert d.score()["pass"], d.lines
    d = run_a(["Yes, speaking.", "I want to speak to a human.", "No, just put me through."], expected=x)
    assert d.score()["pass"], d.lines


def test_r1_hardship_offer_reask_is_the_question_only():
    d = run_a(P05_ID + ["I lost my job last month.", "I was in hospital too."], cid="PUB-05")
    assert d.lines[-1] == SPEC_A["lines"]["neutral_reask"]                 # offered once (PUB-05)
    d = run_a(P05_ID + ["I lost my job last month.", "Can I get a discount?"], cid="PUB-05")
    assert d.lines[-1] == "I'm afraid I can't offer that. Would you like me to connect you with our customer support team?"
    assert sum(l.count("sorry to hear") for l in d.lines) == 1


def test_r1_accepted_support_transfer_is_announced():
    d = run_a(P05_ID + ["I lost my job last month.", "Sure."], cid="PUB-05",
              expected=exp("transferred", "support", transfers=[{"queue": "support"}]))
    assert d.score()["pass"], d.lines
    assert d.lines[-1].startswith("I will connect you with our customer support team now.")
    # without accept_say the offer question is turned into a statement
    sp = copy.deepcopy(SPEC_A)
    for it in sp["intents"]:
        (it.get("action") or {}).pop("accept_say", None)
    d = run_a(P05_ID + ["I lost my job last month.", "Sure."], cid="PUB-05", spec=sp)
    assert d.lines[-1].startswith("I will connect you with our customer support team now.")


def test_r1_mixed_claims_per_product():
    d = run_a(P11_ID + ["I already paid the credit card yesterday. The car loan is not mine.", "No.", "No."],
              cid="PUB-11")
    notes = {c["args"]["product_id"]: c["args"]["reason"] for c in d.ledger()["calls"] if c["tool"] == "add_note"}
    assert notes == {"p1": "paid", "p2": "refused", "p3": "dispute"}, (notes, d.lines)
    close = [c for c in d.ledger()["calls"] if c["tool"] == "close_call"][0]["args"]
    assert close["outcome"] == "no_promise" and close.get("reason") == "refused", close


def test_r1_one_failed_promise_named_in_the_closing():
    d = run_a(P11_ID + ["Yes, I can pay all of them today.", "Yes."], cid="PUB-11",
              faults=[{"tool": "create_promise", "fail_calls": [1, 2]}])
    assert "Your promises are recorded." in d.lines[-1]
    assert "could not record the promise for your credit card ending 2288" in d.lines[-1]
    assert "could not record your promise" not in d.lines[-1]


def test_r1_built_spec_line_hygiene():
    sp = copy.deepcopy(SPEC_A)
    sp["identity"]["fail_line"] = ("I'm sorry, I could not verify your identity. Please use the Freya Bank mobile app "
                                   "or visit a branch.")
    sp["closing"]["per_situation"] = {"S_ID_FAILED": "Please use the mobile app or visit a branch."}
    sp["identity"]["decline"]["explain"] = "These questions protect your account. Could you please answer?"
    sp["intents"].append({"id": "change_recorded_promise", "keywords": ["\\b(change|move) (the|my)? ?(promise|date)"],
                          "scope": ["conf"], "precedence": 5, "product_scoped": False,
                          "action": {"kind": "answer_continue",
                                     "say": "A recorded promise cannot be changed in this call."}})
    d = run_a(PUB_SCRIPTS["PUB-03"], cid="PUB-03", spec=sp)
    assert d.lines[-1].count("visit a branch") == 1, d.lines[-1]
    d = run_a(["Yes, speaking.", "I don't want to answer that."], spec=sp)
    assert "Could you please answer?" not in d.lines[-1]
    d = run_a(P07_ID + ["I can pay on Friday.", "Can I change the date to Monday?", "Yes."], cid="PUB-07", spec=sp)
    assert not any("cannot be changed" in l for l in d.lines), d.lines


def _textq_spec(kind):
    sp = copy.deepcopy(SPEC_A)
    q = sp["identity"]["questions"][0]
    q.update({"kind": kind, "pattern": "", "length": 0, "ask": "What is your city of birth?",
              "reask_wrong": "That does not match. What is your city of birth?",
              "ask_full": "What is your city of birth?"})
    return sp


@pytest.mark.parametrize("kind", ["text", "alnum"])
def test_r1_free_text_identity_never_sends_refusals_or_questions(kind):
    d = run_a(["Yes.", "What is this about?", "I don't want to answer that."], spec=_textq_spec(kind),
              expected=exp("not_verified", "declined"))
    assert d.score()["pass"], d.lines
    assert "verify_identity" not in d.tools()
    d = run_a(["Yes.", "Are you a robot?", "I would rather not say.", "No."], spec=_textq_spec(kind))
    assert "verify_identity" not in d.tools(), d.lines


def test_r1_repeated_swapped_date_is_not_sent_again():
    d = run_a(["Yes.", "06/03/1987", "06/03/1987", "06/03/1987"], cid="PUB-11")
    assert d.tools().count("verify_identity") == 1
    assert not any("does not match" in l for l in d.lines), d.lines


def test_r1_identity_reask_has_no_thank_you():
    d = run_a(["Yes, speaking.", "14 March 1988", "I am not giving you that."])
    assert "Thank you. What are the last four" not in d.lines[-1]
    assert "last four digits" in d.lines[-1]


def test_r1_one_day_late_is_singular():
    assert brain.render("is <x> days late", {"spec": {}, "call": {}}) == "is days late"
    assert re.sub(r"(?<![\d.,])\b1 days\b", "1 day", "is 1 days late") == "is 1 day late"
    sp = copy.deepcopy(SPEC_A)
    sp["statement"]["item"] = "It is 1 days late."
    assert brain.render(sp["statement"]["item"], {"spec": sp, "call": {}}) == "It is 1 day late."


def test_r1_opening_is_one_sentence():
    d = run_a(["Yes."])
    first = re.split(r"(?<=[.!?])\s+", d.lines[0])[0]
    assert "digital assistant" in first and "record" in first and not re.search(r"\brecorded\b", first)


def test_r1_readback_loop_is_bounded():
    # live PUB-12 (fix round 1): a customer who keeps rejecting the read-back with a past date never got a close
    turns = P07_ID + ["I can pay on Friday."] + ["No, the 11th.", "The 11th of October."] * 8
    d = run_a(turns, cid="PUB-07")
    assert d.ended and d.tools()[-1] == "close_call", d.lines[-4:]
    assert "create_promise" not in d.tools()


# ---------------------------------------------------------------- promise-date and callback-time edge cases
# (moved here from the cal/parse unit tests of the unused helpers cal.promise_date_check / cal.callback_resolve:
# the brain's own checks are the code that runs on calls)
_DAT_CAL = {"business_weekdays": [0, 1, 2, 3, 4], "holidays": ["2026-10-26", "2026-11-11", "2026-11-26"],
            "holiday_rules": [], "week_start": 0, "count_from": "after_today", "numeric_order": "DMY",
            "this_next": {"this": "current_week", "next": "following_week"}}


@pytest.mark.parametrize("today,d,deadline,exp", [
    ("2026-10-14", "2026-11-02", "2026-11-02", ("agreed", "2026-11-02")),  # DAT-04 / DAT-06 inclusive
    ("2026-10-14", "2026-11-03", "2026-11-02", ("deadline", "2026-11-02")),
    ("2026-10-21", "2026-10-26", "2026-11-02", ("next_bd", "2026-10-27")),  # DAT-11a holiday
    ("2026-10-14", "2026-10-26", "2026-10-23", ("deadline", "2026-10-23")),  # DAT-13
    ("2026-10-14", "2026-10-24", "2026-10-23", ("deadline", "2026-10-23")),
    ("2026-10-21", "2026-10-31", "2026-11-02", ("next_bd", "2026-11-02")),  # DAT-14
    ("2026-10-14", "2026-10-24", "2026-10-24", ("deadline", "2026-10-23")),  # DAT-50a weekend deadline
    ("2026-10-14", "2026-10-12", "2026-10-23", ("date_ask", "2026-10-14")),  # DAT-18 past date
    ("2026-10-14", "2026-10-14", "2026-10-23", ("agreed", "2026-10-14")),
    ("2026-10-24", "2026-10-24", "2026-11-04", ("next_bd", "2026-10-27")),  # DAT-09
    ("2026-11-11", "2026-11-11", "2026-11-20", ("next_bd", "2026-11-12")),  # DAT-45
])
def test_promise_date_validity_edge_cases(today, d, deadline, exp):
    spec = runtime_spec(SPEC_A)
    spec["calendar"] = dict(_DAT_CAL)
    st = {"ph": "NEG", "prods": [{"id": "p1", "type": "credit_card", "due": 42000, "floor": 12600, "dl": 6, "f": {},
                                  "dead": deadline, "rec": 0, "sit": ""}]}
    c = brain._b_ctx({"v": 1, "spec": spec, "wiring": W_A}, st, {"call": {"now": today + "T11:00:00"}, "sensors": {}})
    r = brain._b_eval_prop(c, 0, None, d, "date", {"kind": "first_ask", "k": -1})
    if exp[0] == "agreed":
        assert r["t"] == "agreed"
        assert st["prods"][0]["ag"] == [42000, exp[1]]
    else:
        got = (st["offer"]["kind"], st["offer"]["date"])
        assert r["t"] in ("offer", "say")
        assert got == exp


@pytest.mark.parametrize("text,exp", [
    ("Call her at seven", "Wednesday, 14 October at 19:00"),  # DAT-37a: 07:00 is outside the window
    ("tomorrow at ten", "Thursday, 15 October at 10:00"),
    ("at two", "Wednesday, 14 October at 14:00"),
    ("at nine", "only arrange a call back"),
    ("She's only home after seven tonight.", "only arrange a call back"),  # OPN-18
    ("Any time after three today.", "Wednesday, 14 October at 15:15"),  # OPN-47: 'after' excludes 15:00
    ("She's in tomorrow between two and four.", "Thursday, 15 October at 14:00"),
    ("Today at eleven.", "only arrange a call back"),  # 11:00 is not after now, 23:00 is after hours
    ("Try her tomorrow morning", "What time would be best"),
    ("She's back Friday.", "only arrange a call back"),
])
def test_third_party_callback_time_examples(text, exp):
    d = run_a(["No, this is her husband.", text], cid="PUB-02")
    assert exp in d.lines[-1], d.lines
