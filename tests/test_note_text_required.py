"""A note service that requires a free-text field gets one even when the Spec has no note wording (it carries the
note's reason), so a valid brief with note codes only still builds."""
from builder.compiler import graph


def _catalog(required):
    tool = {"request": {"customer_id": {"type": "string"}, "product_id": {"type": "string"},
                        "kind": {"type": "string", "enum": ["DISPUTE"]}, "text": {"type": "string"}},
            "required": required,
            "roles": {"request": {"customer": "customer_id", "product": "product_id", "reason": "kind",
                                  "text": "text"}, "response": {}, "item": {}}}
    return {"tools": {"add_note": tool}}


def test_required_text_is_bound_without_a_template():
    ent = graph._node_entry("a_note_1", "add_note", _catalog(["customer_id", "text"]), {"notes": {"text": ""}})
    assert ent["body"]["text"] == "b_a_note_1_text"


def test_optional_text_without_a_template_stays_unbound():
    ent = graph._node_entry("a_note_1", "add_note", _catalog(["customer_id"]), {"notes": {"text": ""}})
    assert "text" not in ent["body"]


def test_runtime_fills_the_reason_when_there_is_no_wording():
    from runtime import brain
    c = {"st": {"prods": [{"id": "A"}]}, "S": {"notes": {}}, "W": {}}
    vals = brain._b_item_vals(c, {"t": "note", "j": 0, "n": "a_note_1", "reason": "DISPUTE"})
    assert vals["text"] == "DISPUTE" and vals["product"] == "A"
