"""Coverage + behaviour for harness/mockbank.py: catalog-driven corner cases (docs/CONTRACTS.md E.2)."""
import copy

import pytest

from harness import mockbank as mb
from harness.mockbank import MockBank

CID = "c_cov"


def _case(public_cases, cid="PUB-01", **over):
    c = copy.deepcopy(public_cases[cid])
    c["variables"]["customer_id"] = CID
    c.update(over)
    return c


def _verify_all(bank, case):
    for field, answer in case["identity"].items():
        st, r = bank.call("verify_identity", {"customer_id": CID, "field": field, "answer": answer})
        assert st == 200 and r["ok"] is True
    assert bank._all_ok()


@pytest.mark.parametrize("v,want", [(True, None), (False, None), (3, 3.0), (2.5, 2.5), (" -4.50 ", -4.5),
                                    ("4,50", None), ("abc", None), (None, None), ([1], None)])
def test_num_rules(v, want):
    assert mb._num(v) == want


def test_valid_iso_and_js_numbers():
    assert mb._valid_iso("2026-02-28") and not mb._valid_iso("2026-02-30") and not mb._valid_iso("2026-2-3")
    assert not mb._valid_iso(None)
    assert mb._js({"a": [1.0, 2.5, {"b": 3.0}], "c": True}) == {"a": [1, 2.5, {"b": 3}], "c": True}


def test_boolean_amount_is_not_a_number(catalog_kit, public_cases):
    case = _case(public_cases)
    bank = MockBank(catalog_kit, case)
    _verify_all(bank, case)
    st, r = bank.call("create_promise", {"customer_id": CID, "product_id": "p1", "amount": True,
                                         "date": "2026-10-14"})
    assert (st, r) == (200, {"ok": False, "error": "amount must be a number"}) and bank.promises == []


def _swap_dob(case):
    case["identity"]["date_of_birth"] = "1988-03-05"              # day <= 12, so the swap is a valid date
    return "1988-05-03"


def test_swapped_date_without_hint_role_counts_as_wrong(catalog_kit, public_cases):
    cat = copy.deepcopy(catalog_kit)
    del cat["tools"]["verify_identity"]["roles"]["response"]["hint"]
    case = _case(public_cases)
    swapped = _swap_dob(case)
    bank = MockBank(cat, case)
    st, r = bank.call("verify_identity", {"customer_id": CID, "field": "date_of_birth", "answer": swapped})
    assert r == {"ok": True, "verified": False, "wrong_answers_left": 2, "all_verified": False}
    assert bank.wrong == 1 and bank.hinted == 0


def test_swapped_date_with_hint_leaf_but_no_enum_counts_as_wrong(catalog_kit, public_cases):
    cat = copy.deepcopy(catalog_kit)
    leaf = cat["tools"]["verify_identity"]["roles"]["response"]["hint"]
    cat["tools"]["verify_identity"]["response"][leaf]["enum"] = []
    case = _case(public_cases)
    swapped = _swap_dob(case)
    bank = MockBank(cat, case)
    bank.call("verify_identity", {"customer_id": CID, "field": "date_of_birth", "answer": swapped})
    assert bank.wrong == 1 and bank.hinted == 0


def test_response_without_success_leaf_or_unbound_roles(catalog_kit, public_cases):
    cat = copy.deepcopy(catalog_kit)
    resp = cat["tools"]["verify_identity"]["roles"]["response"]
    del resp["s"], resp["left"]
    bank = MockBank(cat, _case(public_cases))
    st, r = bank.call("verify_identity", {"customer_id": CID, "field": "phone_last4", "answer": "0000"})
    assert st == 200 and r == {"verified": False, "all_verified": False}     # no ok / wrong_answers_left leaves


def test_selector_value_outside_identity_without_catalog_enum(catalog_kit, public_cases):
    cat = copy.deepcopy(catalog_kit)
    cat["tools"]["verify_identity"]["request"]["field"]["enum"] = []
    bank = MockBank(cat, _case(public_cases))
    st, r = bank.call("verify_identity", {"customer_id": CID, "field": "mothers_maiden_name", "answer": "X"})
    assert (st, r) == (200, {"ok": False, "error": "unknown field"}) and bank.wrong == 0
    assert bank.calls[-1]["tool"] == "verify_identity"                          # rejected calls are logged


def test_swapped_date_with_hint_enum_is_a_hint_not_counted(catalog_kit, public_cases):
    case = _case(public_cases)
    swapped = _swap_dob(case)
    bank = MockBank(catalog_kit, case)
    st, r = bank.call("verify_identity", {"customer_id": CID, "field": "date_of_birth", "answer": swapped})
    assert r["ok"] is True and r["verified"] is False and r["hint"] and bank.wrong == 0 and bank.hinted == 1


def test_case_max_wrong_override_locks_after_one(catalog_kit, public_cases):
    bank = MockBank(catalog_kit, _case(public_cases, max_wrong=1))
    st, r = bank.call("verify_identity", {"customer_id": CID, "field": "phone_last4", "answer": "0000"})
    assert r == {"ok": False, "error": "too many wrong answers", "verified": False, "wrong_answers_left": 0,
                 "all_verified": False}
    st, r = bank.call("verify_identity", {"customer_id": CID, "field": "phone_last4", "answer": "4471"})
    assert r["ok"] is False and "locked" in r["error"] and bank.wrong == 1


def test_transfer_without_required_queue_role_value(catalog_kit, public_cases):
    cat = copy.deepcopy(catalog_kit)
    cat["tools"]["transfer_to_agent"]["required"] = ["customer_id"]
    bank = MockBank(cat, _case(public_cases))
    assert bank.call("transfer_to_agent", {"customer_id": CID}) == (200, {"ok": False, "error": "missing queue"})
    assert bank.call("transfer_to_agent", {"customer_id": CID, "queue": "general"}) == (200, {"ok": True})
    assert bank.transfers == [{"queue": "general"}]


def test_close_without_required_outcome_value(catalog_kit, public_cases):
    cat = copy.deepcopy(catalog_kit)
    cat["tools"]["close_call"]["required"] = ["customer_id"]
    bank = MockBank(cat, _case(public_cases))
    assert bank.call("close_call", {"customer_id": CID, "reason": "refused"}) == \
        (200, {"ok": False, "error": "missing outcome"})
    assert not bank.closed and bank.outcome is None


def test_close_reasonless_outcome_with_empty_reason_leaf_records_empty_reason(catalog_kit, public_cases):
    bank = MockBank(catalog_kit, _case(public_cases))
    assert bank.call("close_call", {"customer_id": CID, "outcome": "paid", "reason": ""}) == (200, {"ok": True})
    led = bank.ledger()
    assert led["outcome"] == "paid" and led["reason"] == "" and bank.closed
    bank2 = MockBank(catalog_kit, _case(public_cases))
    bank2.call("close_call", {"customer_id": CID, "outcome": "paid"})
    assert bank2.ledger()["reason"] is None


def test_close_call_reason_role_unbound(catalog_kit, public_cases):
    cat = copy.deepcopy(catalog_kit)
    del cat["tools"]["close_call"]["roles"]["request"]["reason"]
    bank = MockBank(cat, _case(public_cases))
    st, r = bank.call("close_call", {"customer_id": CID, "outcome": "no_promise", "reason": "refused"})
    assert r == {"ok": False, "error": "a reason is required for outcome no_promise"}   # reason leaf not readable
    assert bank.call("close_call", {"customer_id": CID, "outcome": "promise"}) == (200, {"ok": True})
    assert bank.ledger()["reason"] is None


def test_add_note_without_reason_role_and_with_text(catalog_kit, public_cases):
    cat = copy.deepcopy(catalog_kit)
    del cat["tools"]["add_note"]["roles"]["request"]["reason"]
    cat["tools"]["add_note"]["required"] = ["customer_id", "product_id"]
    bank = MockBank(cat, _case(public_cases))
    assert bank.call("add_note", {"customer_id": CID, "product_id": "p1", "text": "said they paid"}) == \
        (200, {"ok": True})
    assert bank.notes == [{"product_id": "p1", "reason": None, "text": "said they paid"}]


def test_schedule_callback_datetime_role_unparseable(catalog_kit, public_cases):
    cat = copy.deepcopy(catalog_kit)
    cat["tools"]["schedule_callback"]["roles"]["request"] = {"customer": "customer_id", "datetime": "when"}
    cat["tools"]["schedule_callback"]["required"] = ["customer_id"]
    bank = MockBank(cat, _case(public_cases))
    assert bank.call("schedule_callback", {"customer_id": CID, "when": "tomorrow 3pm"})[1]["ok"] is False
    assert bank.call("schedule_callback", {"customer_id": CID, "when": "2026-10-15 14:30:00"}) == \
        (200, {"ok": True})
    assert bank.callbacks == [{"date": "2026-10-15", "time": "14:30"}]


def test_get_account_without_id_leaf_role_uses_id(catalog_kit, public_cases):
    cat = copy.deepcopy(catalog_kit)
    del cat["tools"]["get_account"]["roles"]["item"]["id"]
    case = _case(public_cases)
    case["products"] = [{"id": "X9", "type": "car_loan", "past_due": 100.0}, {"type": "car_loan", "past_due": 1}]
    bank = MockBank(cat, case)
    assert [p["id"] for p in bank.products] == ["X9", "p2"] and bank.id_leaf == "id"
