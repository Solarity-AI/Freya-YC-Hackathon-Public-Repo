"""Call language (Turkish fully supported, generic for any language): locale rendering, the typed model-read
extraction fields, runtime arbitration (model values primary, code validates), forbidden words with endings, slot
suffix lint, language defaults, packing of non-ASCII Specs and the language-aware turn budget.

The Spec values here are Brief A's (golden) with bank.language switched to "tr": the lines stay English, which is
enough to drive the logic; the customer speaks Turkish (u_text) and the extraction fields carry the model's reading.
"""
import copy
import datetime
import json

import pytest
from test_brain import CASES, SPEC_A, SPEC_AB, W_A, W_AB, Driver, exp
from test_review_fixes_1011 import P06

from builder.compiler import lint, render, snippet
from builder.pipeline import validate as V
from builder.spec import defaults as D
from builder.spec import vocab
from runtime import brain as B
from runtime import bundle, ident
from runtime import locale as L

X_SENSORS = vocab.SENSOR_VARS_X


def tr_spec(base=SPEC_A):
    sp = copy.deepcopy(base)
    sp["bank"]["language"] = "tr"
    return sp


class TrDriver(Driver):
    """Driver whose turns also set the typed extraction sensors of a non-English listen node."""

    def turn(self, text, **sensors):
        for k in X_SENSORS:
            self.vars[k] = sensors.get(k, "")
        return Driver.turn(self, text, **sensors)


def tr_run(turns, cid="PUB-06", expected=None, spec=None, wiring=W_A, entry=None):
    case = copy.deepcopy(CASES[cid])
    if expected is not None:
        case["expected"] = expected
    d = TrDriver(spec or tr_spec(), wiring, case, entry=entry)
    d.play(turns)
    return d


def T(text, en="", **kw):
    """One Turkish customer turn: the words, the English rendering (u_en) and the typed fields (u_kind=...)."""
    out = {"t": text, "u_en": en}
    out.update(kw)
    return out


RP_TR = T("Evet, benim.", "Yes, it's me.", u_act="yes")
DOB_TR = T("On yedi Mayıs bin dokuz yüz seksen altı.", "", u_val="1986-05-17", u_done="complete", u_act="answer")
PHONE_TR = T("Bir beş sıfır iki.", "", u_val="1502", u_done="complete", u_act="answer")
ID_TR = [RP_TR, DOB_TR, PHONE_TR]
TOO_MUCH_TR = T("Tamamını ödeyemem, çok fazla.", "I can't pay the whole amount, it's too much.", u_kind="no",
                u_act="no")
YES_TR = T("Evet, doğru.", "Yes, that's right.", u_kind="yes", u_act="yes")


# ------------------------------------------------------------------------------------------------- locale.py
@pytest.mark.parametrize("lang, d, today, want", [
    ("tr", datetime.date(2026, 10, 23), datetime.date(2026, 10, 14), "23 Ekim Cuma"),
    ("tr", datetime.date(2027, 1, 5), datetime.date(2026, 10, 14), "5 Ocak 2027 Salı"),
    ("tr", datetime.date(2026, 2, 28), None, "28 Şubat Cumartesi"),
    ("en", datetime.date(2026, 10, 23), datetime.date(2026, 10, 14), "Friday, 23 October"),
    ("en", datetime.date(2027, 1, 5), datetime.date(2026, 10, 14), "Tuesday, 5 January 2027"),
    ("de", datetime.date(2026, 10, 23), datetime.date(2026, 10, 14), "Friday, 23 October"),   # no table: English
])
def test_date_phrase(lang, d, today, want):
    assert L.date_phrase(d, today, lang) == want


def test_date_phrase_bad_input_is_empty():
    assert L.date_phrase(None, None, "tr") == "" and L.date_phrase("x", None, "en") == ""


@pytest.mark.parametrize("cents, lang, want", [
    (125000, "tr", "1.250"), (125050, "tr", "1.250,50"), (212510, "tr", "2.125,10"), (99, "tr", "0,99"),
    (125000000, "tr", "1.250.000"), (-125000, "tr", "-1.250"), (125050, "en", "1,250.50"), (125000, "en", "1,250"),
    (125050, "fr", "1 250,50"), (125050, "xx", "1,250.50"),
])
def test_money_digits(cents, lang, want):
    assert L.money_digits(cents, lang) == want


def test_money_digits_bad_input():
    assert L.money_digits("abc", "tr") == "" and L.money_digits(None, "en") == ""


@pytest.mark.parametrize("name, want", [
    ("Friday", 4), ("friday", 4), ("FRI", 4), ("Cuma", 4), ("cuma", 4), ("Çarşamba", 2), ("carsamba", 2),
    ("ÇARŞAMBA", 2), ("Salı", 1), ("SALI", 1), ("Cumartesi", 5), ("Pazar", 6), ("Pazartesi", 0), ("Mon.", 0),
    ("", None), ("xyz", None), ("fr", None), (None, None),
])
def test_weekday_index(name, want):
    assert L.weekday_index(name) == want


@pytest.mark.parametrize("spec, want", [
    ({"bank": {"language": "tr"}}, "tr"), ({"bank": {"language": "TR"}}, "tr"), ({"bank": {"language": "tr-TR"}}, "tr"),
    ({"bank": {}}, "en"), ({}, "en"), (None, "en"), ({"bank": {"language": "1x"}}, "en"), ({"language": "de"}, "de"),
])
def test_lang_of(spec, want):
    assert L.lang_of(spec) == want


def test_turkish_lower_case_rules():
    assert L.lang_lower("KREDİ KARTI", "tr") == "kredi kartı"
    assert L.lang_lower("IĞDIR", "tr") == "ığdır"
    assert L.lang_lower("İstanbul", "en") == "istanbul"          # no combining dot left behind
    assert L.lang_fold("Ödeme Çağrısı") == "odeme cagrisi"


def test_brain_renders_money_and_dates_in_the_call_language():
    sp = tr_spec()
    sp["bank"]["currency"] = {"symbol": "", "word": "TL", "position": "after"}
    ctx = {"spec": sp, "today": datetime.date(2026, 10, 14), "amount": 125050, "date": "2026-10-23"}
    assert B.render("Tutar: <amount>. Tarih: <date>.", ctx) == "Tutar: 1.250,50 TL. Tarih: 23 Ekim Cuma."
    sp["bank"]["currency"] = {"symbol": "₺", "word": "", "position": "after"}
    assert B._b_money(125000, sp) == "1.250₺"
    en = copy.deepcopy(SPEC_A)
    assert B.render("<amount> on <date>.", dict(ctx, spec=en)) == "1,250.50 on Friday, 23 October."


# ------------------------------------------------------------------------------------------------ ident.id_model
DOB_Q = {"key": "dob", "kind": "date", "wire_format": "%Y-%m-%d", "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}$"}
PH_Q = {"key": "phone", "kind": "digits", "length": 4, "pattern": "^[0-9]{4}$"}
TODAY = datetime.date(2026, 10, 14)


@pytest.mark.parametrize("q, val, done, frag, want", [
    (DOB_Q, "1986-05-17", "complete", "", {"status": "complete", "wire": "1986-05-17"}),
    (DOB_Q, "1986-5-7", "complete", "", {"status": "complete", "wire": "1986-05-07"}),
    (DOB_Q, "1986-02-30", "complete", "", {"status": "none"}),            # no such day
    (DOB_Q, "2031-01-01", "complete", "", {"status": "none"}),            # in the future
    (DOB_Q, "1880-01-01", "complete", "", {"status": "none"}),            # out of range
    (DOB_Q, "05-17", "partial", "", {"status": "none"}),                  # the words are parsed instead
    (DOB_Q, "1986-05-17", "partial", "", {"status": "none"}),
    (DOB_Q, "17 Mayıs 1986", "complete", "", {"status": "none"}),
    (DOB_Q, "", "none", "", {"status": "none"}),
    (DOB_Q, "1986-05-17", "none", "", {"status": "none"}),
    (PH_Q, "1502", "complete", "", {"status": "complete", "wire": "1502"}),
    (PH_Q, "15", "partial", "", {"status": "incomplete", "frag": "15"}),
    (PH_Q, "02", "complete", "15", {"status": "complete", "wire": "1502"}),
    (PH_Q, "15 02", "complete", "", {"status": "complete", "wire": "1502"}),
    (PH_Q, "123456", "complete", "", {"status": "invalid"}),
    (PH_Q, "bir beş", "complete", "", {"status": "none"}),               # words, not digits: parsed instead
    ({"key": "y", "kind": "year"}, "1986", "complete", "", {"status": "complete", "wire": "1986"}),
    ({"key": "y", "kind": "year"}, "86", "complete", "", {"status": "none"}),
    ({"key": "y", "kind": "year"}, "2099", "complete", "", {"status": "none"}),
    ({"key": "c", "kind": "alnum", "length": 6}, "ab 12 cd", "complete", "", {"status": "complete", "wire": "AB12CD"}),
    ({"key": "c", "kind": "alnum"}, "--", "complete", "", {"status": "none"}),
    ({"key": "m", "kind": "text"}, "Yılmaz.", "complete", "", {"status": "complete", "wire": "Yılmaz"}),
    ({"key": "m", "kind": "text"}, "Yıl", "partial", "", {"status": "none"}),
])
def test_id_model(q, val, done, frag, want):
    assert ident.id_model(q, val, done, frag, TODAY) == want


def test_id_model_never_raises():
    assert ident.id_model(None, object(), "complete", None, None) == {"status": "none"}


# ------------------------------------------------------------------------------------------- extraction schema
def _fields(stage, spec):
    return {f["name"]: f for f in render.extraction_schema(stage, spec)}


def test_english_extraction_schema_is_unchanged():
    for stage in render.STAGES:
        names = [f["name"] for f in render.extraction_schema(stage, SPEC_A)]
        assert not set(names) & set(X_SENSORS), (stage, names)
        assert names[:2] == ["u_text", "u_act"]


@pytest.mark.parametrize("stage, extra", [
    ("id", {"u_val", "u_done"}), ("neg", {"u_amt", "u_dkind", "u_dval", "u_dwhich", "u_kind"}),
    ("conf", {"u_amt", "u_dkind", "u_dval", "u_dwhich", "u_kind"}), ("rp", set()), ("tp", {"u_date", "u_time"}),
    ("safe", set()),
])
def test_turkish_extraction_schema_has_the_typed_fields(stage, extra):
    f = _fields(stage, tr_spec())
    assert "u_en" in f and "u_text" in f and "u_act" in f
    assert extra <= set(f), (stage, sorted(f))
    assert not ({"u_ans", "u_date"} & set(f)) or stage == "tp"
    assert "Turkish" in f["u_text"]["description"]
    for name, fld in f.items():                                  # every enum holds the brain's neutral reset value
        if fld.get("enum_values") and name in B._B_RESET:
            assert B._B_RESET[name] in fld["enum_values"], name
    assert len(render.extraction_schema(stage, tr_spec())) == len(f)


def test_extraction_never_asks_the_model_to_compute_a_date():
    f = _fields("neg", tr_spec())
    assert "Never compute a date" in f["u_dval"]["description"]
    assert "never turn" in f["u_en"]["description"]


def test_sensor_names_match_between_builder_and_runtime():
    assert tuple(B._B_SENS_X) == tuple(vocab.SENSOR_VARS_X)
    assert B._b_sensor_names(tr_spec()) == B._B_SENSORS + B._B_SENS_X
    assert B._b_sensor_names(SPEC_A) == B._B_SENSORS


# ---------------------------------------------------------------------------- Turkish turn-by-turn (twin driver)
def test_turkish_call_floor_offer_on_friday_recorded():
    d = tr_run(ID_TR + [TOO_MUCH_TR,
                        T("Cuma günü ödeyebilirim.", "I can pay on Friday.", u_dkind="weekday", u_dval="Friday",
                          u_kind="yes", u_act="yes"),
                        YES_TR], expected=P06)
    assert d.tools() == ["verify_identity", "verify_identity", "get_account", "create_promise", "close_call"], d.lines
    assert d.score()["pass"], d.lines
    joined = " ".join(d.lines)
    assert "637,50" in joined and "16 Ekim Cuma" in joined and "637.50" not in joined


def test_turkish_identity_in_words_is_read_from_the_model_value_alone():
    # u_en is empty: only the typed u_val can carry the answers
    d = tr_run(ID_TR + [TOO_MUCH_TR], expected=P06)
    assert d.tools()[:3] == ["verify_identity", "verify_identity", "get_account"], (d.tools(), d.lines)


def test_turkish_identity_partial_digits_then_rest():
    turns = [RP_TR, DOB_TR, T("Bir beş...", "One five...", u_val="15", u_done="partial", u_act="answer"),
             T("Sıfır iki.", "Zero two.", u_val="02", u_done="partial", u_act="answer"), TOO_MUCH_TR]
    d = tr_run(turns, expected=P06)
    assert d.tools()[:3] == ["verify_identity", "verify_identity", "get_account"], (d.tools(), d.lines)


def test_turkish_bad_model_date_falls_back_to_the_english_rendering():
    dob = T("On yedi Mayıs seksen altı... bin dokuz yüz seksen altı.", "Seventeenth of May 1986.",
            u_val="17-05-1986", u_done="complete", u_act="answer")        # not YYYY-MM-DD: code rejects it
    d = tr_run([RP_TR, dob, PHONE_TR, TOO_MUCH_TR], expected=P06)
    assert d.tools()[:3] == ["verify_identity", "verify_identity", "get_account"], (d.tools(), d.lines)


def test_turkish_amount_with_dot_thousands_and_friday():
    want = exp("promise", promises=[{"product_id": "p1", "amount": 1250.0, "date": "2026-10-16"}])
    d = tr_run(ID_TR + [TOO_MUCH_TR,
                        T("Cuma günü 1.250 lira ödeyebilirim.", "I can pay 1.250 lira on Friday.", u_amt="1.250",
                          u_dkind="weekday", u_dval="Cuma", u_kind="answer", u_act="proposal"),
                        YES_TR], expected=want)
    assert d.score()["pass"], d.lines
    assert any("1.250" in x and "16 Ekim Cuma" in x for x in d.lines), d.lines


def test_turkish_relative_day_is_resolved_by_code_from_now():
    case_now = CASES["PUB-06"]["variables"]
    today = B.parse_now(case_now.get("now") or case_now.get("current_datetime") or "")[0]
    tomorrow = (today + datetime.timedelta(days=1)).isoformat()
    want = exp("promise", promises=[{"product_id": "p1", "amount": 637.5, "date": tomorrow}])
    d = tr_run(ID_TR + [TOO_MUCH_TR,
                        T("Yarın ödeyebilirim.", "", u_dkind="relative_days", u_dval="1", u_kind="yes",
                          u_act="yes"),
                        YES_TR], expected=want)
    assert d.score()["pass"], d.lines


def test_turkish_small_talk_never_consumes_the_pending_offer():
    chat = T("Kuzenimin düğünü cumartesi, çok yoğunum bu aralar.",
             "My cousin's wedding is on Saturday, I'm very busy these days.", u_kind="smalltalk",
             u_act="chatter_only")
    d = tr_run(ID_TR + [TOO_MUCH_TR, chat], expected=P06)
    offer = d.turn_lines[-2][-1]
    after = d.turn_lines[-1]
    assert not d.ended and "Do you confirm" not in " ".join(after), d.lines
    assert after[-1] in (offer, SPEC_A["lines"]["neutral_reask"]), (offer, after)    # the offer stays pending
    for x in (T("Cuma günü ödeyebilirim.", "I can pay on Friday.", u_dkind="weekday", u_dval="Friday",
                 u_kind="yes", u_act="yes"), YES_TR):
        d.turn(x["t"], **{k: v for k, v in x.items() if k != "t"})
    assert d.score()["pass"], d.lines


def test_turkish_small_talk_with_a_value_is_not_small_talk():
    # the model says smalltalk but read a day: the value wins (no silent drop of an offer)
    d = tr_run(ID_TR + [TOO_MUCH_TR,
                        T("Ah hava güzel, cuma öderim.", "Oh the weather is nice, I'll pay Friday.",
                          u_dkind="weekday", u_dval="Friday", u_kind="smalltalk", u_act="proposal"),
                        YES_TR], expected=P06)
    assert d.score()["pass"], d.lines


def test_turkish_spec_keywords_match_the_customers_own_words():
    sp = tr_spec()
    paid = [it for it in sp["intents"] if (it.get("action") or {}).get("kind") == "resolve_product"]
    assert paid
    sp["intents"] = [dict(it, keywords=[r"\bzaten [öo]ded\w*"]) if it is paid[0] else it for it in sp["intents"]]
    B._B_RAW["g"], B._B_RAW["r"] = "I already did it.", "Zaten ödedim."
    try:
        assert B._b_kw(paid[0] | {"keywords": [r"\bzaten [öo]ded\w*"]}, "I already did it.")
        assert not B._b_kw(paid[0] | {"keywords": [r"\bzaten [öo]ded\w*"]}, "another clause")
    finally:
        B._B_RAW["g"], B._B_RAW["r"] = "", ""


def test_turkish_resets_write_neutral_enum_values():
    d = tr_run(ID_TR[:1])
    for k in X_SENSORS:
        assert d.vars[k] == B._B_RESET.get(k, ""), (k, d.vars[k])


@pytest.mark.parametrize("v, want", [
    ("1250", 125000), ("1250.50", 125050), ("1.250", 125000), ("1.250,50", 125050), ("1,250", 125000),
    ("12,5", 1250), ("637.5", 63750), ("lira", None), ("", None), ("1.2.3,4,5", None), (" 900 TL", 90000),
])
def test_model_amount_reading(v, want):
    assert B._b_mv_cents(v) == want


@pytest.mark.parametrize("mv, want", [
    ({"dkind": "absolute", "dval": "10-23"}, "2026-10-23"),
    ({"dkind": "absolute", "dval": "2027-01-05"}, "2027-01-05"),
    ({"dkind": "absolute", "dval": "02-30"}, None),
    ({"dkind": "weekday", "dval": "Cuma", "dwhich": "next"}, "2026-10-23"),
    ({"dkind": "weekday", "dval": "Friday", "dwhich": ""}, "2026-10-16"),
    ({"dkind": "weekday", "dval": "someday"}, None),
    ({"dkind": "relative_days", "dval": "0"}, "2026-10-14"),
    ({"dkind": "relative_days", "dval": "2"}, "2026-10-16"),
    ({"dkind": "relative_days", "dval": "7"}, "2026-10-21"),
    ({"dkind": "relative_days", "dval": "-3"}, None),
    ({"dkind": "relative_days", "dval": "x"}, None),
    ({"dkind": "day_of_month", "dval": "23"}, "2026-10-23"),
    ({"dkind": "day_of_month", "dval": "2"}, "2026-11-02"),
    ({"dkind": "day_of_month", "dval": "40"}, None),
    ({"dkind": "", "dval": ""}, None),
])
def test_model_date_resolution(mv, want):
    from runtime.cal import prepare
    c = {"mv": dict({"dwhich": ""}, **mv), "today": TODAY, "cal": prepare({"business_weekdays": [0, 1, 2, 3, 4]}, TODAY)}
    r = B._b_mv_date(c)
    assert (r or {}).get("date") == want, r


def test_model_date_vague_and_past():
    from runtime.cal import prepare
    cal = prepare({}, TODAY)
    assert B._b_mv_date({"mv": {"dkind": "vague", "dval": ""}, "today": TODAY, "cal": cal})["kind"] == "vague"
    r = B._b_mv_date({"mv": {"dkind": "absolute", "dval": "10-01", "dwhich": ""}, "today": TODAY, "cal": cal})
    assert r == {"kind": "past", "date": "2026-10-01"}


def test_english_call_ignores_the_typed_sensors():
    c = {"S": copy.deepcopy(SPEC_A)}
    B._b_sens(c, {"u_text": "Yes.", "u_act": "yes", "u_en": "No.", "u_kind": "no"})
    assert c["mv"] is None and c["text"] == "Yes." and c["act"] == "yes"


def test_turkish_sensor_intake():
    c = {"S": tr_spec()}
    B._b_sens(c, {"u_text": "Evet.", "u_act": "unclear", "u_en": "Yes.", "u_kind": "yes", "u_dkind": "none",
                  "u_dwhich": "bare", "u_val": "Yılmaz", "u_amt": ""})
    assert c["text"] == "Yes." and c["raw"] == "Evet." and c["act"] == "yes"
    assert c["mv"]["val"] == "Yılmaz" and c["mv"]["dkind"] == "" and c["mv"]["dwhich"] == "" and c["mv"]["amt"] == ""
    c = {"S": tr_spec()}
    B._b_sens(c, {"u_text": "Evet.", "u_en": "none"})
    assert c["text"] == "Evet."                                      # no usable rendering: the words themselves


# ------------------------------------------------------------------------------------- packed ctl (bundled run)
def test_packed_turkish_ctl_runs_a_call():
    sp = tr_spec()
    code = snippet.build_ctl_code(sp, W_A)
    compiled = compile(code, "<ctl>", "exec")

    def entry(vars, _R):
        exec(compiled, {"vars": vars})
    d = tr_run(ID_TR + [TOO_MUCH_TR,
                        T("Cuma günü ödeyebilirim.", "I can pay on Friday.", u_dkind="weekday", u_dval="Friday",
                          u_kind="yes", u_act="yes"),
                        YES_TR], expected=P06, spec=sp, entry=entry)
    assert d.score()["pass"], d.lines
    assert "16 Ekim Cuma" in " ".join(d.lines)


def test_rspec_literal_keeps_non_ascii_letters_and_round_trips():
    rs = {"spec": {"lines": {"a": "Ödemeniz için teşekkürler   {x} 'q' \\ ş"}}}
    lit = bundle.rspec_literal(rs)
    assert "Ödemeniz" in lit and "\\u00d6" not in lit and "{" not in lit and "}" not in lit
    assert json.loads(eval(lit)) == rs                                    # noqa: S307 - a literal built above


def test_turn_cap_is_smaller_for_a_non_english_call():
    code = "x" * 84_000
    assert snippet.turn_cap(code, "tr") < snippet.turn_cap(code, "en")
    assert lint.turns_to_limit(code, "tr") < lint.turns_to_limit(code)
    sp = tr_spec()
    ns = {}
    exec(bundle.unpack_snippet(snippet.build_ctl_code(sp, W_A)).split("globals().update")[0], ns)
    cap = B._b_dec(ns["RSPEC_HEX"])["spec"]["turn_cap"]
    assert cap >= snippet.MIN_TURN_CAP


def test_packed_size_of_a_turkish_spec_stays_under_the_hard_cap():
    for sp, w in ((tr_spec(SPEC_A), W_A), (tr_spec(SPEC_AB), W_AB)):
        code = snippet.build_ctl_code(sp, w)
        assert len(code.encode()) <= bundle.PACK_MAX_BYTES
        assert lint.turns_to_limit(code, "tr") - snippet.TURN_MARGIN >= snippet.MIN_TURN_CAP


def test_lint_projection_is_a_warning_while_the_turn_budget_is_safe():
    out = []
    lint._lint_code_size({"nodes": {}}, "ctl", "x" * 88_000, out)
    assert any(f["rule"] == "code_size" and f["level"] == "warn" for f in out), out
    assert not any(f["level"] == "error" for f in out), out


# ------------------------------------------------------------------------- forbidden words with Turkish endings
@pytest.mark.parametrize("word, text, hit", [
    ("borç", "Borcunuz hakkında arıyorum.", True),
    ("borç", "BORÇLARINIZ", True),
    ("ödeme", "Ödemeniz gecikti.", True),
    ("kart", "Kartınızın son dört hanesi", True),
    ("gecikme", "gecikmeniz", True),
    ("kitap", "kitabınız", True),
    ("renk", "rengi", True),
    ("kredi", "KREDİ KARTI", True),
    ("İade", "iadeniz", True),
    ("borç", "Merhaba, nasılsınız?", False),
    ("kart", "bu bir şaka", False),
    ("ödeme", "ödül", False),
])
def test_turkish_forbidden_word_morphology(word, text, hit):
    assert bool(lint.words_hit([word], text, "tr")) is hit


def test_english_forbidden_words_stay_whole_words():
    assert lint.words_hit(["debt"], "your debts", "en") == []
    assert lint.words_hit(["debt"], "Your DEBT.", "en") == ["debt"]
    assert lint._words_hit(["card"], "a card", "en") == ["card"]
    assert lint.word_rx("", "tr") is None and lint.words_hit([""], "x", "tr") == []


def test_validate_banned_hits_uses_the_call_language():
    assert V.banned_hits("Borcunuz hakkında", ["borç"], "tr") == ["borç"]
    assert V.banned_hits("Borcunuz hakkında", ["borç"]) == []


def test_lint_flags_a_turkish_banned_word_with_an_ending_before_verification(golden_a, catalog_kit):
    from builder.compiler import graph
    sp = copy.deepcopy(golden_a)
    sp["bank"]["language"] = "tr"
    sp["banned"]["before_verification"] = list(sp["banned"]["before_verification"]) + ["borç"]
    sp["right_party"]["answers"]["why"] = "Borcunuz hakkında yalnızca <customer> ile konuşabilirim."
    wf, w = graph.compile_workflow(sp, catalog_kit, code="x = 1\n")
    out = lint.lint(wf, catalog_kit, sp, w, stable=False)
    assert any(f["rule"] == "banned_word" and "borç" in f["msg"] for f in out), out


# ------------------------------------------------------------------------------------- slot endings (Turkish)
def test_slot_suffix_lint_and_validate_warning():
    sp = {"bank": {"language": "tr"}, "lines": {"a": "Tutar <amount>'ı ödeyin.", "b": "Tutar: <amount>.",
                                                 "c": "<date>de arayacağım", "d": "<v:surname> Bey",
                                                 "e": "<product>ınız", "f": "<bank>'ın asistanıyım",
                                                 "g": "<self>yım"}}
    hits = dict(lint.slot_suffixes(sp))
    assert set(hits) == {"/lines/a", "/lines/c", "/lines/e"}
    assert lint.slot_suffixes(dict(sp, bank={"language": "en"})) == []


def test_turkish_default_lines_have_no_slot_endings_and_no_english():
    sp = {"bank": {"language": "tr"}}
    out, applied = D.apply_defaults(sp)
    assert out["lines"]["clarify"] == "Affedersiniz, tekrar söyler misiniz?"
    assert out["lines"]["amount_change_ask"] and out["identity"]["verified_prefix"] == "Teşekkür ederim."
    assert set(D.DEFAULT_LINES) <= set(out["lines"])
    assert lint.slot_suffixes(out) == []
    assert not any(v == D.DEFAULT_LINES.get(k) for k, v in out["lines"].items())
    en, _ = D.apply_defaults({"bank": {"language": "en"}})
    assert "amount_change_ask" not in en["lines"] and en["lines"] == D.DEFAULT_LINES


@pytest.mark.parametrize("v, want", [("Turkish", "tr"), ("tr-TR", "tr"), ("TR", "tr"), ("Türkçe", "tr"),
                                     (None, "en"), ("", "en"), ("en", "en"), ("Klingon!", "en")])
def test_validate_normalises_the_call_language(v, want):
    s = {"bank": {"language": v}}
    fixes = []
    V._fix_language(s, fixes)
    assert s["bank"]["language"] == want
    assert bool(fixes) == (v != want)


def test_schema_accepts_any_two_letter_language():
    sch = json.load(open(__import__("pathlib").Path(V.__file__).resolve().parents[1] / "spec" / "schema.json"))
    lang = sch["properties"]["bank"]["properties"]["language"]
    assert lang["pattern"] == "^[a-z]{2}$"


def test_system_prompt_names_the_call_language():
    assert "Speak Turkish." in render.system_prompt(tr_spec())


class _Boom:
    def __str__(self):
        raise ValueError("boom")

    def get(self, *_a):
        raise ValueError("boom")


def test_locale_helpers_never_raise():
    assert L.lang_of(_Boom()) == "en" and L.lang_of(["tr"]) == "en"
    assert L.lang_lower(_Boom(), "tr") == "" and L.lang_fold(_Boom()) == ""
    assert L.weekday_index(_Boom()) is None


def _mv_c(**mv):
    base = {"val": "", "done": "", "amt": "", "dkind": "", "dval": "", "dwhich": "", "kind": ""}
    base.update(mv)
    from runtime.cal import prepare
    return {"mv": base, "today": TODAY, "cal": prepare({}, TODAY)}


@pytest.mark.parametrize("kind, yn_in, want", [
    ("yes", {"yn": ""}, {"yn": "yes"}),
    ("no", {"yn": ""}, {"yn": "no"}),
    ("yes", {"yn": "no"}, {"yn": "yes"}),                      # the model's reading wins over the rendering
    ("yes", {"yn": "no", "cant": True}, {"yn": "no"}),          # "yes, but I can't": stays a no
    ("no", {"yn": "yes"}, {"yn": "no"}),
    ("hedge", {"yn": "yes"}, {"yn": "yes", "hedge": True}),
    ("correction", {"yn": ""}, {"yn": "", "corr": True}),
    ("refusal", {"yn": ""}, {"yn": "no"}),
    ("question", {"yn": ""}, {"yn": "", "question": True}),
    ("answer", {"yn": ""}, {"yn": ""}),
])
def test_model_kind_merges_into_the_yes_no_reading(kind, yn_in, want):
    _a, _d, yn = B._b_mv_values(_mv_c(kind=kind), {}, {}, {}, dict(yn_in))
    for k, v in want.items():
        assert yn.get(k) == v, (kind, yn)


@pytest.mark.parametrize("amt, hi, want", [
    ("0", 212510, {"kind": "zero"}), ("1250", 212510, {"kind": "amount", "cents": 125000}),
    ("99999999", 212510, {}), ("", 212510, {}), ("1250", 0, {"kind": "amount", "cents": 125000}),
])
def test_model_amount_is_validated(amt, hi, want):
    a, _d, _yn = B._b_mv_values(_mv_c(amt=amt), {"hi": hi}, {}, {}, {})
    assert a == want


def test_model_small_talk_clears_values_parsed_from_the_rendering():
    a, d, yn = B._b_mv_values(_mv_c(kind="smalltalk"), {}, {"kind": "amount", "cents": 5}, {"kind": "date"},
                              {"yn": "yes"})
    assert a == {} and d == {} and yn["yn"] == ""


def test_model_date_bad_value_is_ignored():
    assert B._b_mv_date(_mv_c(dkind="absolute", dval="13-45")) is None
    assert B._b_mv_date(_mv_c(dkind="day_of_month", dval="abc")) is None


def test_accept_say_is_not_built_from_english_words_in_another_language():
    c = {"lang": "tr", "S": tr_spec(), "call": {}, "today": TODAY, "st": {}}
    assert B._b_accept_say(c, {"say": "Would you like me to connect you with a specialist?"}) == ""
    assert B._b_accept_say(c, {"accept_say": "Sizi bağlıyorum."}) == "Sizi bağlıyorum."


@pytest.mark.parametrize("raw, want", [
    ("1.250 lira öderim", "1250 lira öderim"), ("1.250,50 TL", "1250.50 TL"), ("1.250.000", "1250000"),
    ("23.10.2026 tarihinde", "23.10.2026 tarihinde"), ("12,5 lira", "12.5 lira"), ("cuma günü", "cuma günü"),
])
def test_turkish_words_without_a_rendering_get_plain_numbers(raw, want):
    c = {"S": tr_spec()}
    B._b_sens(c, {"u_text": raw, "u_en": ""})
    assert c["text"] == want and c["raw"] == raw
