"""Promise kind: a create_promise enum field whose values name the full amount / the minimum / part of it (generic
language words). The compiler finds it (graph.promise_kind), adds it to every promise node's body and puts the
value map in wiring["pkind"]; the runtime picks the value from the promised amount against the product's due amount
and floor. Without it the field was baked as enum[0] (every promise "full")."""
import copy
import json
import pathlib

from builder.compiler import graph
from runtime import brain

ROOT = pathlib.Path(__file__).resolve().parent.parent
W_A = json.loads((ROOT / "tests/fixtures/wiring-a.json").read_text())
SPEC_A = json.loads((ROOT / "tests/golden/spec-a.json").read_text())
CALL = {"customer_id": "c-1", "first_name": "Ann", "last_name": "Lee", "title": "Ms", "now": "2026-01-07T11:00"}


def _catalog(enum, role="reason", field="kind"):
    req = {"customer_id": {"type": "string", "required": True}, "product_id": {"type": "string", "required": True},
           "amount": {"type": "number", "required": True}, "date": {"type": "string", "required": True},
           field: {"type": "string", "required": True, "enum": list(enum)}}
    roles = {"customer": "customer_id", "product": "product_id", "amount": "amount", "date": "date"}
    if role:
        roles[role] = field
    return {"tools": {"create_promise": {"request": req, "roles": {"request": roles}}}}


class TestClassify:
    def test_turkish_and_english_words(self):
        assert graph._pk_class("TAMAMI") == "full"
        assert graph._pk_class("ASGARI") == "min"
        assert graph._pk_class("KISMI") == "part"
        assert graph._pk_class("FULL_BALANCE") == "full"
        assert graph._pk_class("minimum_due") == "min"
        assert graph._pk_class("Partial") == "part"
        assert graph._pk_class("EN_AZ_ODEME") == "min"
        assert graph._pk_class("tam ödeme") == "full"

    def test_unknown_or_ambiguous_is_none(self):
        assert graph._pk_class("STANDARD") is None
        assert graph._pk_class("FULL_PARTIAL") is None
        assert graph._pk_class("") is None


class TestCompiler:
    def test_found_on_a_reason_field(self):
        pk = graph.promise_kind(_catalog(["TAMAMI", "ASGARI", "KISMI"]))
        assert pk == {"field": "kind", "full": "TAMAMI", "min": "ASGARI", "part": "KISMI"}

    def test_found_on_an_unbound_field(self):
        pk = graph.promise_kind(_catalog(["FULL", "PARTIAL"], role=None, field="ptype"))
        assert pk == {"field": "ptype", "full": "FULL", "part": "PARTIAL"}

    def test_not_found(self):
        assert graph.promise_kind(_catalog(["A", "B"])) is None
        assert graph.promise_kind(_catalog(["FULL"])) is None              # one kind is not a kind field
        assert graph.promise_kind({"tools": {}}) is None
        cat = _catalog(["FULL", "PARTIAL"], role="product")                  # a bound non-reason role is never it
        assert graph.promise_kind(cat) is None

    def test_kit_wiring_has_no_pkind(self):
        assert "pkind" not in W_A


def _W():
    W = copy.deepcopy(W_A)
    W["pkind"] = {"field": "kind", "full": "TAMAMI", "min": "ASGARI", "part": "KISMI"}
    for n, ent in W["nodes"].items():
        if ent["tool"] == "create_promise":
            ent["body"]["kind"] = "b_%s_kind" % n
    return W


def _vals(W, amount, due=100000, floor=40000):
    p = {"id": "p1", "type": "credit_card", "due": due, "dl": 6, "f": {}, "sit": "", "rec": 0,
         "ag": [amount, "2026-01-08"]}
    if floor is not None:
        p["floor"] = floor
    R = {"v": 1, "spec": SPEC_A, "wiring": W}
    c = brain._b_ctx(R, {"prods": [p]}, {"call": dict(CALL), "sensors": {}, "results": {}})
    return brain._b_item_vals(c, {"t": "promise", "j": 0, "n": "a_promise_1_1"})


class TestRuntime:
    def test_full_min_part(self):
        W = _W()
        assert _vals(W, 100000)["@kind"] == "TAMAMI"
        assert _vals(W, 120000)["@kind"] == "TAMAMI"
        assert _vals(W, 40000)["@kind"] == "ASGARI"
        assert _vals(W, 60000)["@kind"] == "KISMI"
        assert _vals(W, 30000)["@kind"] == "KISMI"
        assert _vals(W, 60000, floor=None)["@kind"] == "KISMI"

    def test_missing_kind_falls_back(self):
        W = _W()
        del W["pkind"]["part"]
        assert _vals(W, 60000)["@kind"] == "ASGARI"

    def test_no_pkind_no_value(self):
        assert not any(k.startswith("@") for k in _vals(copy.deepcopy(W_A), 60000))

    def test_value_reaches_the_body_variable(self):
        W = _W()
        p = {"id": "p1", "type": "credit_card", "due": 100000, "floor": 40000, "dl": 6, "f": {}, "sit": "",
             "rec": 0, "ag": [40000, "2026-01-08"]}
        R = {"v": 1, "spec": SPEC_A, "wiring": W}
        c = brain._b_ctx(R, {"prods": [p]}, {"call": dict(CALL), "sensors": {}, "results": {}})
        brain._b_route_api(c, "a_promise_1_1", brain._b_item_vals(c, {"t": "promise", "j": 0, "n": "a_promise_1_1"}))
        assert c["w"]["b_a_promise_1_1_kind"] == "ASGARI"
