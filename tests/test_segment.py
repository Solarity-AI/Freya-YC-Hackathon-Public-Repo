"""builder.pipeline.segment: tables, sections, lexicon, numbering, quotes (agent 5). Generic fixtures + the kit briefs."""
import pathlib

from builder.pipeline import segment as seg

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRIEF_A = ROOT / "kit" / "briefs" / "brief-a.md"
BRIEF_B = ROOT / "kit" / "briefs" / "brief-b.md"


def test_standard_table():
    lines = ["intro", "| a | b | c |", "|---|:--:|--:|", "| 1 | 2 | 3 |", "| x | y | z |", "after"]
    t = seg.parse_tables(lines)
    assert t == [{"line": 2, "header": ["a", "b", "c"], "rows": [["1", "2", "3"], ["x", "y", "z"]]}]


def test_table_without_outer_pipes_and_short_rows_padded():
    lines = ["a | b | c", "---|---|---", "1 | 2", "4 | 5 | 6 | 7"]
    t = seg.parse_tables(lines)[0]
    assert t["header"] == ["a", "b", "c"]
    assert t["rows"] == [["1", "2", ""], ["4", "5", "6", "7"]]


def test_table_escaped_pipe_and_quote_prefix():
    lines = ["> | code | meaning |", "> |---|---|", "> | A\\|B | either |"]
    t = seg.parse_tables(lines)[0]
    assert t["rows"] == [["A|B", "either"]]


def test_table_without_separator_row():
    t = seg.parse_tables(["| k | v |", "| 1 | 2 |"])[0]
    assert t["header"] == ["k", "v"] and t["rows"] == [["1", "2"]]


def test_single_pipe_line_is_not_a_table():
    assert seg.parse_tables(["use a | b as you like"]) == []
    assert seg.parse_tables(["| only one row |"]) == []


def test_table_footnotes_attached():
    t = seg.parse_tables(["| a | b |", "|---|---|", "| 1 | 2* |", "* except weekends", "text"])[0]
    assert t["notes"] == ["* except weekends"]


def test_two_tables_and_empty_cells():
    lines = ["| a | b |", "|---|---|", "| | 2 |", "", "| c |  d |", "|-|-|", "| 3 | |"]
    ts = seg.parse_tables(lines)
    assert len(ts) == 2 and ts[0]["rows"] == [["", "2"]] and ts[1]["rows"] == [["3", ""]]


def test_sections_markdown_levels():
    lines = ["# Title", "x", "## One", "a", "### One.1", "b", "## Two", "c"]
    s = seg.parse_sections(lines)
    assert [(x["title"], x["level"], x["line_start"], x["line_end"]) for x in s] == [
        ("Title", 1, 1, 8), ("One", 2, 3, 6), ("One.1", 3, 5, 6), ("Two", 2, 7, 8)]


def test_sections_raw_material_mail_memo_underline():
    lines = ["From: Head of Ops", "To: Vendor", "Subject: rules", "", "Please follow the attached.",
             "MEMO 2026-03-02", "The limit changes.", "Policy extract", "==============", "Rule 1."]
    s = seg.parse_sections(lines)
    titles = [x["title"] for x in s]
    assert titles[0].startswith("mail: From:") and "MEMO 2026-03-02" in titles and "Policy extract" in titles
    assert sum(1 for t in titles if t.startswith("mail:")) == 1          # one header block = one section


def test_sections_fallback_whole_document():
    assert seg.parse_sections(["plain", "text"]) == [{"title": "(document)", "level": 1, "line_start": 1,
                                                      "line_end": 2}]


def test_lexicon_tokens():
    lex = seg.build_lexicon('Holidays: 2031-02-03. Call `ref_id` 10:00 to 19:30, 6 pm. Ask "Is that you?" '
                            'the 4th business day, 1,250.50 due, 1-7 days, 46+, twelve, “curly”')
    assert lex["iso_dates"] == ["2031-02-03"]
    assert "10:00" in lex["times"] and "19:30" in lex["times"] and any("6 pm" in t for t in lex["times"])
    assert lex["backticked"] == ["ref_id"]
    assert "Is that you?" in lex["quoted"] and "curly" in lex["quoted"]
    assert "4th" in lex["ordinals"] and "1,250.50" in lex["numbers"]
    assert any("1-7" in r for r in lex["ranges"]) and "46+" in lex["ranges"]
    assert "twelve" in lex["number_words"]
    assert "2031" not in lex["numbers"]                                   # ISO dates are not split into numbers


def test_segment_single_file(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("# Brief\r\n\r\n| a | b |\r\n|---|---|\r\n| 1 | 2 |\r\n")
    b = seg.segment([str(p)])
    d = b["docs"][0]
    assert d["lines"][0] == "# Brief" and len(d["lines"]) == 5 and d["tables"][0]["line"] == 3
    assert len(d["sha256"]) == 64 and d["kind"] == "brief"
    assert b["numbered"].splitlines()[0] == "x.md:1| # Brief"
    assert "LAYER" not in b["numbered"]


def test_segment_layers_in_order(tmp_path):
    a, c = tmp_path / "a.md", tmp_path / "c.md"
    a.write_text("base rule\n")
    c.write_text("amendment\n")
    b = seg.segment([str(a), str(c)])
    lines = b["numbered"].splitlines()
    assert lines[0].startswith("=== LAYER 1 of 2: a.md") and lines[1] == "a.md:1| base rule"
    assert lines[2].startswith("=== LAYER 2 of 2: c.md") and lines[3] == "c.md:1| amendment"
    assert b["text"] == "base rule\n\n\namendment\n"


def test_segment_bad_bytes_and_bom(tmp_path):
    p = tmp_path / "x.txt"
    p.write_bytes(b"\xef\xbb\xbfhello \xff world\n")
    d = seg.segment([str(p)])["docs"][0]
    assert d["lines"][0].startswith("hello") and "�" in d["lines"][0]


def test_expand_dirs(tmp_path):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "2.md").write_text("b")
    (tmp_path / "d" / "1.txt").write_text("a")
    (tmp_path / "d" / "img.png").write_bytes(b"\x89PNG")
    out = seg.expand_paths([str(tmp_path / "d")])
    assert [pathlib.Path(x).name for x in out] == ["1.txt", "2.md"]


def test_kind_guess_mixed():
    text = "From: a\nSubject: b\n\nMEMO\nCode list\n| code | meaning |\n|---|---|\n| X1 | y |\n"
    d = seg.segment_text("raw.md", text)
    assert d["kind"] == "mixed"


def test_kit_brief_a_structure():
    b = seg.segment([str(BRIEF_A)])
    d = b["docs"][0]
    assert len(d["tables"]) == 3                                  # call variables, bands, outcomes
    headers = [t["header"][0].lower() for t in d["tables"]]
    assert headers[0] == "variable" and "days_late" in headers[1] and headers[2] == "outcome"
    assert len(d["tables"][1]["rows"]) == 2 and len(d["tables"][2]["rows"]) == 6
    assert any(s["title"].startswith("7. Dates") for s in d["sections"])
    assert len(b["lexicon"]["iso_dates"]) >= 5


def test_kit_briefs_as_layers():
    b = seg.segment([str(BRIEF_A), str(BRIEF_B)])
    assert len(b["docs"]) == 2 and b["numbered"].count("=== LAYER") == 2


# ----------------------------------------------------------------------------------------------- quotes

def test_quote_normalisation():
    hay = seg.norm_quote_text('Ask "Am I `here`?" — it’s **fine**.\n| 1 to 7 | early |')
    assert seg.quote_in("ask “Am I here?” - it's fine.", hay)
    assert seg.quote_in("| 1 to 7 | early |", hay)
    assert seg.quote_in("x.md:12| it's fine", hay)                 # numbered prefix tolerated
    assert seg.quote_in("Ask ... it's fine", hay)                  # ellipsis joins parts
    assert not seg.quote_in("Ask ... missing part", hay)
    assert not seg.quote_in("", hay) and not seg.quote_in("...", hay)


def test_quote_across_lines():
    hay = seg.norm_quote_text("first half of\nthe sentence")
    assert seg.quote_in("first half of the sentence", hay)


def test_example_values_from_example_columns():
    tables = [{"header": ["Variable", "Example", "Meaning"],
               "rows": [["`id`", "`x_9f...`", "pass it"], ["`a`, `b`", "`Ann`, `Lee`", "names"],
                        ["`t`", "`Dr` or `Prof`", "title"], ["`n`", "2031-04-05T09:30", "now"], ["short"]]},
              {"header": ["Code", "Meaning"], "rows": [["X1", "ignored"]]}]
    assert seg.example_values(tables) == ["x_9f", "Ann", "Lee", "Prof", "2031-04-05T09:30"]


def test_kit_brief_examples_collected():
    ex = seg.segment([str(BRIEF_A)])["examples"]
    assert len(ex) >= 3 and all(len(x) >= 3 for x in ex)


def test_r1_folder_keeps_data_files_and_uses_neutral_headers(tmp_path):
    d = tmp_path / "raw"
    d.mkdir()
    (d / "a-memo.md").write_text("memo rule")
    (d / "b-codes.json").write_text('{"codes": ["X1"]}')
    (d / "c-api.json").write_text((ROOT / "kit" / "tools" / "openapi.json").read_text())
    b = seg.segment([str(d)])
    names = [pathlib.Path(x["path"]).name for x in b["docs"]]
    assert names == ["a-memo.md", "b-codes.json"]
    assert "=== DOCUMENT 1 of 2" in b["numbered"] and "LAYER" not in b["numbered"]
    from builder import build
    ns = build.parse_args([str(d)])
    assert ns.api.endswith("c-api.json") and ns.briefs == [str(d)]
