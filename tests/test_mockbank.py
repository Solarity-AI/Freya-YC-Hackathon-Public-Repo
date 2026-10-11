"""Mock bank (harness/mockbank.py): kit bank behaviour from the ToolCatalog + one case. Owner: agent 4."""
import copy

import pytest

from harness import score as hscore
from harness.mockbank import MockBank

CID = "c_test"


def _case(public_cases, cid="PUB-01", **over):
    c = copy.deepcopy(public_cases[cid])
    c["variables"]["customer_id"] = CID
    c.update(over)
    return c


@pytest.fixture
def bank(catalog_kit, public_cases):
    return MockBank(catalog_kit, _case(public_cases))


def V(bank, field, answer, cid=CID):
    return bank.call("verify_identity", {"customer_id": cid, "field": field, "answer": answer})


def verify_all(bank):
    assert V(bank, "date_of_birth", "1988-03-14")[1]["ok"] is True
    st, r = V(bank, "phone_last4", "4471")
    assert r["all_verified"] is True
    return r


# ---------------------------------------------------------------- verify_identity
def test_verify_happy_path_sets_all_verified(bank):
    st, r = V(bank, "date_of_birth", "1988-03-14")
    assert st == 200 and r == {"ok": True, "verified": True, "wrong_answers_left": 3, "all_verified": False}
    r = verify_all(bank)
    assert r["verified"] is True and r["wrong_answers_left"] == 3
    assert bank.ledger()["verified"] == {"date_of_birth": True, "phone_last4": True}


def test_verify_unreadable_date_not_counted(bank):
    for bad in ("14 March 1988", "1988-02-30", "", "garbage"):
        st, r = V(bank, "date_of_birth", bad)
        assert st == 200 and r["ok"] is False and "error" in r
    assert bank.ledger()["wrong"] == 0


def test_verify_day_month_swapped_gives_hint_not_counted(catalog_kit, public_cases):
    b = MockBank(catalog_kit, _case(public_cases, "PUB-07"))          # dob 1975-12-05
    st, r = V(b, "date_of_birth", "1975-05-12")
    assert r["ok"] is True and r["verified"] is False and r["hint"] == "day_month_swapped"
    assert r["wrong_answers_left"] == 3
    led = b.ledger()
    assert led["wrong"] == 0 and led["hinted"] == 1


def test_three_wrong_answers_lock(catalog_kit, public_cases):
    b = MockBank(catalog_kit, _case(public_cases, "PUB-03"))          # dob 1992-07-21
    r1 = V(b, "date_of_birth", "1991-07-12")[1]
    r2 = V(b, "date_of_birth", "1992-08-21")[1]
    r3 = V(b, "date_of_birth", "1990-07-21")[1]
    assert (r1["ok"], r1["wrong_answers_left"]) == (True, 2)
    assert (r2["ok"], r2["wrong_answers_left"]) == (True, 1)
    assert (r3["ok"], r3["wrong_answers_left"], r3["verified"]) == (False, 0, False)
    r4 = V(b, "date_of_birth", "1992-07-21")[1]                         # even a right answer is refused now
    assert r4["ok"] is False and r4["wrong_answers_left"] == 0 and "locked" in r4["error"]
    assert b.ledger()["wrong"] == 3


def test_wrong_digits_counted_and_spoken_words_not_normalised(catalog_kit, public_cases):
    b = MockBank(catalog_kit, _case(public_cases, "PUB-12"))          # phone 4410
    assert V(b, "phone_last4", "4401")[1]["wrong_answers_left"] == 2
    assert V(b, "phone_last4", "four four one zero")[1]["wrong_answers_left"] == 1
    assert V(b, "phone_last4", " 4410 ")[1]["verified"] is True


def test_verify_unknown_field_rejected_not_counted(bank):
    st, r = V(bank, "mother_maiden_name", "x")
    assert r["ok"] is False and bank.ledger()["wrong"] == 0
    st, r = bank.call("verify_identity", {"customer_id": CID, "answer": "1988-03-14"})
    assert r["ok"] is False and "missing" in r["error"]


def test_reverify_of_verified_field_omits_all_leaf(bank):
    verify_all(bank)
    st, r = V(bank, "date_of_birth", "1988-03-14")
    assert r["ok"] is True and r["verified"] is True and "all_verified" not in r


def test_unknown_customer_is_404_and_not_logged(bank):
    st, r = V(bank, "date_of_birth", "1988-03-14", cid="c_other")
    assert st == 404 and r["error"] == "unknown customer_id"
    st, r = bank.call("get_account", {})
    assert st == 404
    assert bank.ledger()["calls"] == []


def test_unknown_tool_is_404(bank):
    assert bank.call("delete_everything", {"customer_id": CID})[0] == 404


# ---------------------------------------------------------------- get_account
def test_get_account_before_verification_fails_score(bank, public_cases):
    st, r = bank.call("get_account", {"customer_id": CID})
    assert st == 200 and r == {"ok": False, "error": "identity not verified"}
    led = bank.ledger()
    assert led["calls"][0]["result"]["error"] == "identity not verified"
    res = hscore.score_ledger(public_cases["PUB-01"], led)
    assert any("before identity was verified" in f for f in res["failed"])


def test_get_account_products_ids_and_js_numbers(catalog_kit, public_cases):
    b = MockBank(catalog_kit, _case(public_cases, "PUB-11"))
    V(b, "date_of_birth", "1987-06-03")
    V(b, "phone_last4", "2288")
    st, r = b.call("get_account", {"customer_id": CID})
    assert r["ok"] is True
    assert [p["product_id"] for p in r["products"]] == ["p1", "p2", "p3"]
    assert r["products"][0]["past_due"] == 220 and isinstance(r["products"][0]["past_due"], int)
    assert r["products"][1]["instalment_amount"] == 213


def test_get_account_partial_verification_refused(bank):
    V(bank, "date_of_birth", "1988-03-14")
    assert bank.call("get_account", {"customer_id": CID})[1]["error"] == "identity not verified"


# ---------------------------------------------------------------- create_promise
def P(bank, **kw):
    body = {"customer_id": CID, "product_id": "p1", "amount": 420.0, "date": "2026-10-14"}
    body.update(kw)
    body = {k: v for k, v in body.items() if v is not None}
    return bank.call("create_promise", body)


def test_promise_gate_and_validation(bank):
    assert P(bank)[1]["error"] == "identity not verified"
    verify_all(bank)
    assert P(bank, product_id="p9")[1]["error"] == "unknown product_id"
    assert P(bank, date="14/10/2026")[1]["error"] == "date must be YYYY-MM-DD"
    assert P(bank, amount="lots")[1]["error"] == "amount must be a number"
    assert P(bank, date=None)[1]["error"] == "missing date"
    st, r = P(bank, amount="420.00")                                    # numeric string accepted (G8)
    assert r == {"ok": True, "promise_id": "pr1"}
    assert P(bank)[1]["error"] == "this product already has a promise"
    led = bank.ledger()
    assert led["promises"] == [{"promise_id": "pr1", "product_id": "p1", "type": "credit_card", "amount": 420.0,
                                "date": "2026-10-14"}]


def test_fault_injection_first_promise_500_nothing_recorded(catalog_kit, public_cases):
    b = MockBank(catalog_kit, _case(public_cases, "PUB-10"))
    V(b, "date_of_birth", "1989-02-23")
    V(b, "phone_last4", "9904")
    st, r = P(b, amount=365, date="2026-10-16")
    assert st == 500 and r is None
    assert b.ledger()["promises"] == [] and b.ledger()["failures"] == {"create_promise": 1}
    assert b.ledger()["calls"][-1]["status"] == 500 and b.ledger()["calls"][-1]["result"] == {}
    st, r = P(b, amount=365, date="2026-10-16")
    assert st == 200 and r["ok"] is True
    assert len(b.ledger()["promises"]) == 1


@pytest.mark.parametrize("mode,status,body", [("ok_false", 200, {"ok": False, "error": "the service failed"}),
                                              ("empty", 200, {}), ("timeout", 599, None)])
def test_fault_modes(catalog_kit, public_cases, mode, status, body):
    b = MockBank(catalog_kit, _case(public_cases), faults=[{"tool": "get_account", "fail_first_n": 1}],
                 fault_mode=mode)
    verify_all(b)
    assert b.call("get_account", {"customer_id": CID}) == (status, body)
    assert b.call("get_account", {"customer_id": CID})[1]["ok"] is True


def test_fault_on_specific_call_numbers_and_dict_form(catalog_kit, public_cases):
    b = MockBank(catalog_kit, _case(public_cases), faults=[{"tool": "verify_identity", "fail_calls": [2],
                                                             "mode": "ok_false"}])
    assert V(b, "date_of_birth", "1988-03-14")[1]["ok"] is True
    assert V(b, "phone_last4", "4471")[1] == {"ok": False, "error": "the service failed"}
    assert V(b, "phone_last4", "4471")[1]["all_verified"] is True
    b2 = MockBank(catalog_kit, _case(public_cases), faults={"verify_identity": 1})
    assert V(b2, "date_of_birth", "1988-03-14")[0] == 500


# ---------------------------------------------------------------- notes, callbacks, transfers
def test_add_note_enum_and_product(bank):
    verify_all(bank)
    assert bank.call("add_note", {"customer_id": CID, "product_id": "p1", "reason": "bored"})[1]["error"] \
        == "unknown reason"
    assert bank.call("add_note", {"customer_id": CID, "product_id": "p7", "reason": "refused"})[1]["error"] \
        == "unknown product_id"
    assert bank.call("add_note", {"customer_id": CID, "product_id": "p1", "reason": "refused", "text": "t"})[1] \
        == {"ok": True}
    assert bank.ledger()["notes"] == [{"product_id": "p1", "reason": "refused", "text": "t"}]


def test_call_level_note_when_catalog_has_no_product_role(catalog_kit, public_cases):
    cat = copy.deepcopy(catalog_kit)
    t = cat["tools"]["add_note"]
    del t["roles"]["request"]["product"]
    del t["request"]["product_id"]
    t["required"] = ["customer_id", "reason"]
    b = MockBank(cat, _case(public_cases))
    assert b.call("add_note", {"customer_id": CID, "reason": "refused"})[1]["ok"] is True
    assert b.ledger()["notes"] == [{"reason": "refused"}]


def test_schedule_callback_validation(catalog_kit, public_cases):
    b = MockBank(catalog_kit, _case(public_cases, "PUB-02"))
    bad = b.call("schedule_callback", {"customer_id": CID, "date": "2026-10-15", "time": "11am"})[1]
    assert bad["error"] == "date must be YYYY-MM-DD and time HH:MM"
    assert b.call("schedule_callback", {"customer_id": CID, "date": "2026-10-15", "time": "24:00"})[1]["ok"] is False
    assert b.call("schedule_callback", {"customer_id": CID, "date": "2026-10-15", "time": "11:00"})[1]["ok"] is True
    assert b.ledger()["callbacks"] == [{"date": "2026-10-15", "time": "11:00"}]


def test_schedule_callback_datetime_role(catalog_kit, public_cases):
    cat = copy.deepcopy(catalog_kit)
    t = cat["tools"]["schedule_callback"]
    t["roles"]["request"] = {"customer": "customer_id", "datetime": "when"}
    t["request"] = {"customer_id": t["request"]["customer_id"], "when": dict(t["request"]["date"])}
    t["required"] = ["customer_id", "when"]
    b = MockBank(cat, _case(public_cases, "PUB-02"))
    assert b.call("schedule_callback", {"customer_id": CID, "when": "2026-10-15T11:00:00"})[1]["ok"] is True
    assert b.ledger()["callbacks"] == [{"date": "2026-10-15", "time": "11:00"}]


def test_transfer_queue_enum(bank):
    assert bank.call("transfer_to_agent", {"customer_id": CID, "queue": "nowhere"})[1]["error"] == "unknown queue"
    assert bank.call("transfer_to_agent", {"customer_id": CID, "queue": "general"})[1]["ok"] is True
    assert bank.ledger()["transfers"] == [{"queue": "general"}]


# ---------------------------------------------------------------- close_call
def C(bank, **body):
    return bank.call("close_call", dict({"customer_id": CID}, **body))


def test_close_requires_reason_unless_reasonless(bank):
    assert C(bank, outcome="no_promise")[1]["error"].startswith("a reason is required")
    assert C(bank, outcome="no_promise", reason="")[1]["ok"] is False
    assert C(bank, outcome="weird")[1]["error"] == "unknown outcome"
    assert C(bank)[1]["error"] == "missing outcome"
    assert C(bank, outcome="no_promise", reason="refused")[1]["ok"] is True
    led = bank.ledger()
    assert (led["outcome"], led["reason"]) == ("no_promise", "refused")


def test_reason_sent_with_reasonless_outcome_is_recorded_and_fails_score(bank, public_cases):
    verify_all(bank)
    bank.call("get_account", {"customer_id": CID})
    P(bank)
    assert C(bank, outcome="promise", reason="promise")[1]["ok"] is True
    res = hscore.score_ledger(public_cases["PUB-01"], bank.ledger())
    assert not res["pass"] and any(f.startswith("outcome") for f in res["failed"])


def test_custom_reasonless_list(catalog_kit, public_cases):
    b = MockBank(catalog_kit, _case(public_cases), reasonless=["promise", "paid", "not_reached"])
    assert C(b, outcome="not_reached")[1]["ok"] is True


def test_nothing_accepted_after_close_and_score_needs_close_last(bank, public_cases):
    verify_all(bank)
    bank.call("get_account", {"customer_id": CID})
    P(bank)
    assert C(bank, outcome="promise")[1]["ok"] is True
    assert bank.ledger()["reason"] is None
    assert hscore.score_ledger(public_cases["PUB-01"], bank.ledger()) == {"pass": True, "failed": []}
    st, r = bank.call("add_note", {"customer_id": CID, "product_id": "p1", "reason": "paid"})
    assert r == {"ok": False, "error": "the call is already closed"}
    assert C(bank, outcome="paid")[1]["error"] == "the call is already closed"
    led = bank.ledger()
    assert led["notes"] == [] and led["outcome"] == "promise"
    res = hscore.score_ledger(public_cases["PUB-01"], led)
    assert "the call was not closed with close_call" not in res["failed"]       # last logged call is close_call
    bank.call("get_account", {"customer_id": CID})
    res = hscore.score_ledger(public_cases["PUB-01"], bank.ledger())
    assert "the call was not closed with close_call" in res["failed"]


def test_not_reached_case_fails_score_if_verify_was_called(catalog_kit, public_cases):
    b = MockBank(catalog_kit, _case(public_cases, "PUB-02"))
    V(b, "date_of_birth", "1979-11-02")
    b.call("schedule_callback", {"customer_id": CID, "date": "2026-10-15", "time": "11:00"})
    C(b, outcome="not_reached", reason="callback")
    res = hscore.score_ledger(public_cases["PUB-02"], b.ledger())
    assert any("not on the line" in f for f in res["failed"])


def test_per_field_identity_mode(catalog_kit, public_cases):
    cat = copy.deepcopy(catalog_kit)
    t = cat["tools"]["verify_identity"]
    del t["roles"]["request"]["selector"]
    del t["roles"]["request"]["answer"]
    t["request"] = {"customer_id": t["request"]["customer_id"], "date_of_birth": {"type": "string"},
                    "phone_last4": {"type": "string"}}
    t["required"] = ["customer_id"]
    cat["identity_mode"] = "per_field"
    b = MockBank(cat, _case(public_cases))
    assert b.call("verify_identity", {"customer_id": CID})[1]["ok"] is False
    r = b.call("verify_identity", {"customer_id": CID, "date_of_birth": "1988-03-14", "phone_last4": "4471"})[1]
    assert r["all_verified"] is True


def test_missing_customer_id_defaults_and_product_ids_kept(catalog_kit, public_cases):
    c = copy.deepcopy(public_cases["PUB-01"])
    c["products"][0]["product_id"] = "X-1"
    b = MockBank(catalog_kit, c)
    assert b.customer_id.startswith("c_twin_")
    assert b.products[0]["product_id"] == "X-1"


def test_renamed_success_leaf_from_catalog(catalog_kit, public_cases):
    cat = copy.deepcopy(catalog_kit)
    cat["tools"]["transfer_to_agent"]["roles"]["response"] = {"s": "accepted", "err": "message"}
    b = MockBank(cat, _case(public_cases))
    assert b.call("transfer_to_agent", {"customer_id": CID, "queue": "general"})[1] == {"accepted": True}
    assert b.call("transfer_to_agent", {"customer_id": CID, "queue": "x"})[1] == {"accepted": False,
                                                                                  "message": "unknown queue"}
