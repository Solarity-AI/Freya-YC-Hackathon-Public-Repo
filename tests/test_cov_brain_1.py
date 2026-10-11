"""Coverage tests for runtime/brain.py lines 1-1350, part 1: small helpers, rendering (B.2/B.6), amounts (B.5),
outcome resolution (B.3), tool-result readers (C.5 read_result / read_products) and the literal parser.

Every test asserts behaviour that the contracts (docs/CONTRACTS.md B.2, B.3, B.5, B.6, C.5, C.7) define: spoken
money and dates, the AmountRule kinds, the outcome precedence atoms, the "total on bad input" rule of the public
runtime functions, and where a tool result may be read from."""
import copy
import datetime
import json
import pathlib

import pytest

from runtime import brain

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC_A = json.loads((ROOT / "tests/golden/spec-a.json").read_text())
W_A = json.loads((ROOT / "tests/fixtures/wiring-a.json").read_text())


def spec_with_currency(**cur):
    s = {"bank": {"name": "Acme", "currency": {"symbol": "", "word": "", "position": "none"}}}
    s["bank"]["currency"].update(cur)
    return s


# ----------------------------------------------------------------------------------------------- small helpers
class TestSmallHelpers:
    def test_bool_strings_are_lowercase_words(self):
        # C.7: every written value is a string; booleans are "true"/"false"
        assert brain._b_s(True) == "true"
        assert brain._b_s(False) == "false"
        assert brain._b_s(None) == ""
        assert brain._b_s(12) == "12"

    @pytest.mark.parametrize("raw,cents", [
        (4, 400), (1.234, 123), ("420.00", 42000), ("2,125.10", 212510), ("1.005", 101), ("1.004", 100),
        ("-3.5", -350), (".5", 50), ("$ 7", 700),
    ])
    def test_cents_from_numbers_and_strings(self, raw, cents):
        assert brain._b_cents(raw) == cents

    @pytest.mark.parametrize("raw", [None, True, "", "abc", "-", float("inf"), float("nan")])
    def test_cents_none_on_non_money(self, raw):
        # an infinite/NaN float (json.loads accepts Infinity/NaN) must not raise: "no amount"
        assert brain._b_cents(raw) is None

    def test_load_st_keeps_a_dict_and_rejects_non_objects(self):
        st = {"ph": "RP", "turns": 2}
        assert brain._b_load_st(st) is st
        assert brain._b_load_st('{"ph": "ID"}') == {"ph": "ID"}
        assert brain._b_load_st("[1, 2]") == {}
        assert brain._b_load_st("{not json") == {}
        assert brain._b_load_st("pending") == {}
        assert brain._b_load_st(None) == {}

    def test_dump_round_trips_without_adjacent_closing_braces(self):
        st = {"a": {"b": {"c": 1}}, "l": [{"x": 1}]}
        out = brain._b_dump(st)
        assert json.loads(out) == st
        assert "}}" not in out  # C.1: no double braces in anything the platform template engine sees

    def test_join_collapses_whitespace_and_consecutive_repeats(self):
        assert brain._b_join(["  Hello  there ", "Hello there", "", None, "Bye."]) == "Hello there Bye."
        # only a consecutive repeat is dropped
        assert brain._b_join(["A.", "B.", "A."]) == "A. B. A."

    def test_and_joins_spoken_lists(self):
        assert brain._b_and([]) == ""
        assert brain._b_and(["a", ""]) == "a"
        assert brain._b_and(["a", "b"]) == "a and b"
        assert brain._b_and(["a", "b", "c"]) == "a, b and c"

    def test_int_parses_or_defaults(self):
        assert brain._b_int("3") == 3
        assert brain._b_int("3.9") == 3
        assert brain._b_int("x", 7) == 7
        assert brain._b_int(None) is None


class TestGrounded:
    """C.5 step 3: a slot value is used only when its tokens also occur in u_text."""

    def test_empty_slot_or_text_is_never_grounded(self):
        assert brain._b_grounded("", "on the 14th of March") is False
        assert brain._b_grounded("pending", "on the 14th") is False
        assert brain._b_grounded("14 March", "") is False
        assert brain._b_grounded("...", "anything") is False  # no tokens in the slot

    def test_slot_tokens_present_in_text(self):
        assert brain._b_grounded("14 March", "I can pay on 14 March") is True

    def test_slot_digit_missing_from_text_is_not_grounded(self):
        # the extractor normalised 'fifteenth' to 15; the digits are not in the text -> not grounded
        assert brain._b_grounded("15 March", "on the fourteenth of March") is False

    def test_digits_spoken_one_by_one_are_found_in_the_digit_run(self):
        assert brain._b_grounded("card 4471 now ok", "card 4 4 7 1 now ok") is True

    def test_too_few_matching_tokens_is_not_grounded(self):
        assert brain._b_grounded("next friday afternoon", "friday") is False


# ----------------------------------------------------------------------------------------------- money / render
class TestMoney:
    def test_none_is_empty(self):
        assert brain._b_money(None, {}) == ""

    def test_whole_and_fractional_amounts(self):
        assert brain._b_money(42000, {}) == "420"
        assert brain._b_money(212510, {}) == "2,125.10"

    def test_symbol_before(self):
        assert brain._b_money(123450, spec_with_currency(symbol="$", position="before")) == "$1,234.50"

    def test_word_after(self):
        assert brain._b_money(42000, spec_with_currency(word="euros", position="after")) == "420 euros"

    def test_symbol_after_without_word(self):
        assert brain._b_money(42000, spec_with_currency(symbol="€", position="after")) == "420€"

    def test_position_none_still_speaks_the_word(self):
        assert brain._b_money(500, spec_with_currency(word="dollars", position="none")) == "5 dollars"

    def test_position_none_without_word_is_bare(self):
        assert brain._b_money(500, spec_with_currency(symbol="$", position="none")) == "5"

    def test_position_after_without_word_or_symbol_is_bare(self):
        assert brain._b_money(500, spec_with_currency(position="after")) == "5"

    def test_negative_amount(self):
        assert brain._b_money(-500, spec_with_currency(symbol="$", position="before")) == "-$5"


class TestRender:
    SPEC = {"bank": {"name": "Acme Bank", "assistant_self": "<bank>'s assistant",
                     "currency": {"symbol": "", "word": "", "position": "none"}},
            "addressing": {"customer": "<v:title> <v:last_name>"},
            "products": {"types": {"card": {"spoken": "card ending <f:last4>"}}, "unknown_type_spoken": "account"}}

    def ctx(self, **kw):
        d = {"spec": self.SPEC, "call": {"title": "Ms", "last_name": "Lee"}}
        d.update(kw)
        return d

    def test_bank_self_customer(self):
        out = brain.render("I am <self>, calling <customer> from <bank>.", self.ctx())
        assert out == "I am Acme Bank's assistant, calling Ms Lee from Acme Bank."

    def test_unknown_placeholder_is_removed_and_spacing_fixed(self):
        assert brain.render("Hello <nope> there .", self.ctx()) == "Hello there."

    def test_product_spoken_form_and_unknown_type(self):
        p = {"type": "card", "f": {"last4": "4821"}, "due": 42000}
        assert brain.render("Your <product>.", self.ctx(prod=p)) == "Your card ending 4821."
        assert brain.render("Your <product>.", self.ctx(prod={"type": "zzz"})) == "Your account."

    def test_product_without_a_product_renders_nothing(self):
        assert brain.render("Your <product> is late.", self.ctx()) == "Your is late."

    def test_customer_template_recursion_is_bounded(self):
        spec = copy.deepcopy(self.SPEC)
        spec["addressing"]["customer"] = "<customer> X"
        out = brain.render("Hi <customer>", {"spec": spec, "call": {}})
        assert out == "Hi X X X"  # depth 1..3, then empty: never infinite

    def test_rest_from_ctx_from_product_or_empty(self):
        p = {"due": 42000}
        assert brain.render("<rest>", self.ctx(rest=12000)) == "120"
        assert brain.render("<rest>", self.ctx(prod=p, amount=30000)) == "120"
        assert brain.render("<rest>", self.ctx(prod=p, amount=50000)) == "0"  # never negative
        assert brain.render("<rest>", self.ctx(prod=p)) == ""
        assert brain.render("<rest>", self.ctx()) == ""

    def test_money_placeholders_fall_back_to_the_product(self):
        p = {"due": 42000, "floor": 12600}
        assert brain.render("<amount> <past_due> <floor>", self.ctx(prod=p)) == "420 420 126"
        assert brain.render("<amount>", self.ctx(prod=p, amount=1000)) == "10"
        assert brain.render("<amount>", self.ctx()) == ""

    def test_dates(self):
        today = datetime.date(2026, 1, 5)
        assert brain.render("on <date>", self.ctx(date="2026-01-07", today=today)) == "on Wednesday, 7 January"
        assert brain.render("on <date>", self.ctx(date=datetime.date(2027, 1, 7), today=today)) \
            == "on Thursday, 7 January 2027"
        assert brain.render("by <deadline>", self.ctx(prod={"dead": "2026-01-09"}, today=today)) \
            == "by Friday, 9 January"
        # no date at all, or an unparsable one -> nothing
        assert brain.render("on <date>.", self.ctx()) == "on."
        assert brain.render("on <date>.", self.ctx(date="soon")) == "on."

    def test_days_late_and_one_day_singular(self):
        assert brain.render("<days_late> days late", self.ctx(prod={"dl": 1})) == "1 day late"
        assert brain.render("<days_late> days late", self.ctx(days_late=11)) == "11 days late"
        assert brain.render("<days_late> days late", self.ctx()) == "days late"
        assert brain.render("2.1 days", self.ctx()) == "2.1 days"

    def test_time_from_minutes_or_string(self):
        assert brain.render("at <time>", self.ctx(time=615)) == "at 10:15"
        assert brain.render("at <time>", self.ctx(time="10:30")) == "at 10:30"

    def test_items_and_call_and_field_placeholders(self):
        p = {"f": {"last4": "9"}}
        assert brain.render("<items>; <v:title>; <f:last4>", self.ctx(items="a and b", prod=p)) == "a and b; Ms; 9"

    def test_render_never_raises_on_a_bad_context(self):
        # C.5: render never raises; a bad ctx falls back to the template with placeholders removed (whitespace
        # collapsed, punctuation spacing left as is)
        assert brain.render("Hello <customer>, from <bank>.", "not a dict") == "Hello , from ."

    def test_render_never_raises_on_an_unprintable_template(self):
        class Bad:
            def __str__(self):
                raise ValueError("no")
        assert brain.render(Bad(), {}) == ""


# ----------------------------------------------------------------------------------------------- amounts
class TestEvalAmount:
    P = {"due": 1001, "floor": 300, "f": {"minimum_payment": "126.00"}}

    def test_full_floor_field_fixed(self):
        assert brain.eval_amount({"kind": "full"}, self.P, {}) == 1001
        assert brain.eval_amount({"kind": "floor"}, self.P, {}) == 300
        assert brain.eval_amount({"kind": "floor"}, {"due": 200, "floor": 300}, {}) == 200  # min(floor, full)
        assert brain.eval_amount({"kind": "floor"}, {"due": 200}, {}) == 200  # missing floor -> full
        assert brain.eval_amount({"kind": "field", "field": "minimum_payment"}, self.P, {}) == 12600
        assert brain.eval_amount({"kind": "field", "field": "missing"}, self.P, {}) == 1001
        assert brain.eval_amount({"kind": "fixed", "value": "50"}, self.P, {}) == 5000
        assert brain.eval_amount({"kind": "fixed", "value": "n/a"}, self.P, {}) == 1001

    @pytest.mark.parametrize("rounding,cents", [("half_up", 501), ("ceil", 501), ("floor", 500)])
    def test_percent_of_full_rounding(self, rounding, cents):
        # 50% of 10.01 = 5.005 -> half_up 5.01, ceil 5.01, floor 5.00
        assert brain.eval_amount({"kind": "percent_of_full", "pct": 50, "rounding": rounding}, self.P, {}) == cents

    def test_percent_ceil_on_an_exact_value_does_not_round_up(self):
        assert brain.eval_amount({"kind": "percent_of_full", "pct": 50, "rounding": "ceil"}, {"due": 1000}, {}) == 500

    def test_min_max(self):
        rule = {"kind": "min", "args": [{"kind": "full"}, {"kind": "fixed", "value": "5"}]}
        assert brain.eval_amount(rule, self.P, {}) == 500
        rule["kind"] = "max"
        assert brain.eval_amount(rule, self.P, {}) == 1001
        assert brain.eval_amount({"kind": "min", "args": []}, self.P, {}) == 1001

    def test_min_nesting_is_depth_limited_to_full(self):
        rule = {"kind": "fixed", "value": "1"}
        for _ in range(8):
            rule = {"kind": "min", "args": [rule]}
        assert brain.eval_amount(rule, self.P, {}) == 1001

    def test_floor_if_too_much(self):
        rule = {"kind": "floor_if_too_much_else_full"}
        assert brain.eval_amount(rule, self.P, {}) == 1001
        assert brain.eval_amount(rule, dict(self.P, tm=1), {}) == 300
        assert brain.eval_amount(rule, {"due": 1001, "tm": 1}, {}) == 1001

    def test_unknown_kind_and_bad_rule(self):
        assert brain.eval_amount({"kind": "mystery"}, self.P, {}) == 1001
        assert brain.eval_amount("not a rule", self.P, {}) == 1001  # never raises: the full amount
        assert brain.eval_amount(None, None, None) == 0


# ----------------------------------------------------------------------------------------------- outcome
class TestResolveOutcome:
    S = SPEC_A

    def test_phase_defaults_before_any_situation(self):
        assert brain.resolve_outcome(self.S, {"ph": "OPEN"}) == ("not_reached", "unclear", "r")
        assert brain.resolve_outcome(self.S, {"ph": "RP"}) == ("not_reached", "unclear", "r")
        tp = brain.resolve_outcome(self.S, {"ph": "TP"})
        assert tp == ("not_reached", "no_callback", "r")
        idd = brain.resolve_outcome(self.S, {"ph": "ID"})
        assert idd == ("not_verified", "declined", "r")

    def test_bad_spec_never_raises(self):
        assert brain.resolve_outcome(None, {"ph": "RP"}) == ("", "", "n")

    def test_reasonless_outcome_drops_the_reason(self):
        st = {"ph": "BYE", "prods": [{"rec": 1}]}
        assert brain.resolve_outcome(self.S, st) == ("promise", "", "n")

    def test_any_product_atom(self):
        spec = copy.deepcopy(self.S)
        spec["outcomes"]["precedence"] = [{"when": "any_product:S_DISPUTE", "use": "situation:S_DISPUTE"},
                                          {"when": "else", "use": "situation:S_PAID"}]
        st = {"ph": "BYE", "prods": [{"sit": "S_PAID"}, {"sit": "S_DISPUTE"}]}
        assert brain.resolve_outcome(spec, st) == ("no_promise", "dispute", "r")
        st["prods"][1]["sit"] = "S_PAID"
        assert brain.resolve_outcome(spec, st) == ("paid", "", "n")

    def test_unknown_atom_and_unknown_use_are_skipped(self):
        spec = copy.deepcopy(self.S)
        spec["outcomes"]["precedence"] = [{"when": "moon_is_full", "use": "situation:S_PAID"},
                                          {"when": "else", "use": "mystery"},
                                          {"when": "else", "use": "situation:S_DISPUTE"}]
        assert brain.resolve_outcome(spec, {"ph": "BYE", "prods": [{}]}) == ("no_promise", "dispute", "r")

    def test_first_product_excluding_falls_back_to_the_first_product(self):
        spec = copy.deepcopy(self.S)
        spec["outcomes"]["precedence"] = [{"when": "else", "use": "first_product_excluding:S_PAID"}]
        st = {"ph": "BYE", "prods": [{"sit": "S_PAID"}, {"sit": "S_PAID"}]}
        assert brain.resolve_outcome(spec, st) == ("paid", "", "n")

    def test_first_product_excluding_skips_recorded_products(self):
        spec = copy.deepcopy(self.S)
        spec["outcomes"]["precedence"] = [{"when": "else", "use": "first_product_excluding:S_PAID"}]
        st = {"ph": "BYE", "prods": [{"rec": 1}, {"sit": "S_DISPUTE"}]}
        assert brain.resolve_outcome(spec, st)[1] == "dispute"
        # only a recorded product: no situation of its own -> the unresolved-product situation
        assert brain.resolve_outcome(spec, {"ph": "BYE", "prods": [{"rec": 1}]})[1] == "refused"

    def test_first_product_excluding_without_products(self):
        spec = copy.deepcopy(self.S)
        spec["outcomes"]["precedence"] = [{"when": "else", "use": "first_product_excluding:S_PAID"}]
        assert brain.resolve_outcome(spec, {"ph": "ACCT"}) == ("no_promise", "refused", "r")

    def test_empty_precedence_falls_back_to_the_phase_default_then_unresolved(self):
        spec = copy.deepcopy(self.S)
        spec["outcomes"]["precedence"] = []
        assert brain.resolve_outcome(spec, {"ph": "TP", "csit": "S_CALLBACK"})[1] == "no_callback"
        assert brain.resolve_outcome(spec, {"ph": "NEG", "csit": "S_CALLBACK"})[1] == "refused"

    def test_transfer_done_beats_a_promise_unless_failed(self):
        st = {"ph": "BYE", "prods": [{"rec": 1}], "xfer": {"sit": "S_HUMAN_TRANSFER"}}
        assert brain.resolve_outcome(self.S, st) == ("transferred", "human", "r")
        st["xfer"]["failed"] = 1
        assert brain.resolve_outcome(self.S, st) == ("promise", "", "n")


# ----------------------------------------------------------------------------------------------- tool results
class TestNodeAndReadResult:
    def test_compact_node_is_expanded_by_naming_convention(self):
        W = {"nodes": {"a_note_1": {"tool": "add_note", "bf": ["product_id", "reason"]}},
             "roles": {"add_note": {"res": {"s": "ok", "err": "error"}}}}
        n = brain._b_node(W, "a_note_1")
        assert n == {"tool": "add_note",
                     "body": {"product_id": "b_a_note_1_product_id", "reason": "b_a_note_1_reason"},
                     "res": {"s": "r_a_note_1_s", "err": "r_a_note_1_err"},
                     "res_leaf": {"s": "ok", "err": "error"}}

    def test_missing_node_and_bad_wiring(self):
        assert brain._b_node(W_A, "nope") == {}
        assert brain._b_node(["not", "a", "dict"], "a_verify_1") == {}

    def test_mapped_variable_first(self):
        v = {"r_a_verify_1_s": "true", "a_verify_1_response.data.ok": "false"}
        assert brain.read_result(v, W_A, "a_verify_1", "s") == "true"

    def test_node_flattened_then_node_response_key(self):
        assert brain.read_result({"a_verify_1_response.data.ok": "True"}, W_A, "a_verify_1", "s") == "True"
        assert brain.read_result({"a_verify_1_response.ok": "false"}, W_A, "a_verify_1", "s") == "false"

    def test_tool_level_key_only_with_the_fallback(self):
        v = {"verify_identity_response.data.ok": "true"}
        assert brain.read_result(v, W_A, "a_verify_1", "s") == "true"
        assert brain.read_result(v, W_A, "a_verify_1", "s", tool_fallback=False) == "pending"

    def test_pending_values_are_no_result(self):
        v = {"r_a_verify_1_s": "pending", "a_verify_1_response.data.ok": "None"}
        assert brain.read_result(v, W_A, "a_verify_1", "s") == "pending"

    def test_unwired_node_reads_the_role_name_as_leaf(self):
        assert brain.read_result({"x_node_response.data.s": "ok"}, W_A, "x_node", "s") == "ok"

    def test_leaf_from_tool_roles_when_the_node_has_none(self):
        W = copy.deepcopy(W_A)
        W["nodes"]["a_verify_1"]["res_leaf"] = {}
        assert brain.read_result({"a_verify_1_response.data.ok": "true"}, W, "a_verify_1", "s") == "true"

    def test_bad_wiring_reads_pending(self):
        assert brain.read_result({}, None, "a_verify_1", "s") == "pending"


class TestLiteral:
    @pytest.mark.parametrize("raw,val", [
        ('[{"a": 1}]', [{"a": 1}]),
        ("[{'id': 'p1', 'ok': True, 'x': None}]", [{"id": "p1", "ok": True, "x": None}]),
        ("[1, 2, ]", [1, 2]),
        ("(1, 2)", [1, 2]),
        ("[]", []),
        ("{}", {}),
        ("{'a': 1, }", {"a": 1}),
        ("{'a': 'x\\ny', 'b': 'q\\'s'}", {"a": "x\ny", "b": "q's"}),
        ("{'t': 'a\\tb'}", {"t": "a\tb"}),
        ("{'n': -1.5e2, 'f': false, 'z': null}", {"n": -150.0, "f": False, "z": None}),
        ("  True ", True),
    ])
    def test_python_repr_and_json_literals(self, raw, val):
        assert brain._b_lit(raw) == val

    @pytest.mark.parametrize("raw", ["{'a' 1}", "{'a': 1 'b': 2}", "[1 2]", "garbage", "[1, 2", "'open"])
    def test_malformed_literals_are_none(self, raw):
        assert brain._b_lit(raw) is None


class TestReadProducts:
    def test_list_value(self):
        v = {"r_a_acct_1_products": [{"id": "p1"}, "junk"]}
        assert brain.read_products(v, W_A, "a_acct_1") == [{"id": "p1"}]

    def test_single_dict_value(self):
        v = {"r_a_acct_1_products": {"id": "p1"}}
        assert brain.read_products(v, W_A, "a_acct_1") == [{"id": "p1"}]

    def test_json_and_repr_strings(self):
        assert brain.read_products({"r_a_acct_1_products": '[{"id": "p1"}, 3]'}, W_A, "a_acct_1") == [{"id": "p1"}]
        assert brain.read_products({"r_a_acct_1_products": "[{'id': 'p2'}]"}, W_A, "a_acct_1") == [{"id": "p2"}]

    def test_whole_response_object_with_the_products_leaf(self):
        v = {"a_acct_1_response.data.products": "{'products': [{'id': 'p1'}, {'id': 'p2'}], 'ok': True}"}
        assert brain.read_products(v, W_A, "a_acct_1") == [{"id": "p1"}, {"id": "p2"}]

    def test_single_product_object_string(self):
        v = {"get_account_response.data.products": "{'id': 'p1', 'past_due': 420.0}"}
        assert brain.read_products(v, W_A, "a_acct_1") == [{"id": "p1", "past_due": 420.0}]

    def test_flattened_keys_in_index_order(self):
        v = {"a_acct_1_response.data.products.1.product_id": "p2",
             "a_acct_1_response.data.products[0].product_id": "p1",
             "a_acct_1_response.data.products.0.past_due": "420.0",
             "unrelated": "x"}
        assert brain.read_products(v, W_A, "a_acct_1") == [{"product_id": "p1", "past_due": "420.0"},
                                                            {"product_id": "p2"}]

    def test_nothing_or_unparsable(self):
        assert brain.read_products({}, W_A, "a_acct_1") == []
        assert brain.read_products({"r_a_acct_1_products": "nonsense"}, W_A, "a_acct_1") == []

    def test_bad_wiring_never_raises(self):
        assert brain.read_products({"r_x_products": "[]"}, None, "x") == []
