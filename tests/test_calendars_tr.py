from builder import calendars as C


def test_tr_full_days_include_fixed_and_eids():
    d = C.national_holidays("TR")
    for x in ("2026-10-29", "2027-01-01", "2026-03-20", "2026-03-22", "2026-05-27", "2026-05-30",
              "2027-03-09", "2027-03-11", "2027-05-16", "2027-05-19", "2026-04-23", "2026-07-15", "2026-08-30"):
        assert x in d
    assert "2026-10-28" not in d and "2026-05-26" not in d  # half days are business days by default


def test_tr_half_days_on_request():
    d = C.national_holidays("TR", include_half_days=True)
    assert {"2026-10-28", "2026-03-19", "2026-05-26", "2027-03-08", "2027-05-15"} <= set(d)
    assert C.half_days("TR")[0] == "2026-03-19"


def test_unknown_country_is_empty():
    assert C.national_holidays("XX") == [] and C.national_holidays(None) == []


def test_country_guess():
    assert C.country_for("tr") == "TR"
    assert C.country_for("en", "Tutar 1.250,00 TL") == "TR"
    assert C.country_for("en", "Freya Bank, USD") is None


def test_merge_uses_national_list_when_brief_only_mentions_public_holidays():
    dec, warn = [], []
    out = C.merge([], "TR", "Ödeme tarihi resmi tatil günlerine denk gelemez.", dec, warn)
    assert "2026-10-29" in out and dec and not warn


def test_merge_keeps_brief_list_and_warns_on_missing_national_days():
    dec, warn = [], []
    out = C.merge(["2026-11-02"], "TR", "Tatiller: 2 Kasım", dec, warn, window=("2026-10-14", "2026-11-30"))
    assert out == ["2026-11-02"] and not dec and warn and "2026-10-29" in warn[0]


def test_merge_without_mention_or_country_keeps_list():
    dec, warn = [], []
    assert C.merge([], "TR", "No holiday words here.", dec, warn) == []
    assert C.merge(["2026-12-25"], None, "public holidays", dec, warn) == ["2026-12-25"]
    assert not dec and not warn
