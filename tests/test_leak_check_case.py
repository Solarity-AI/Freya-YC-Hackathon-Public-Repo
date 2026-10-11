"""tools/leak_check.py on the final's input: a case folder or .zip is expanded, Word/Excel go through builder.ingest."""
import zipfile

from tests.test_leak_check import leak as lc


def _docx(path, text):
    body = "<w:p><w:r><w:t>%s</w:t></w:r></w:p>" % text
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        z.writestr("word/document.xml", '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
                   'wordprocessingml/2006/main"><w:body>%s</w:body></w:document>' % body)


def test_folder_and_docx_are_read(tmp_path):
    case = tmp_path / "Case"
    case.mkdir()
    (case / "BRIEF.md").write_text("The Zorblat queue takes QX-9917 transfers.")
    _docx(case / "contract.docx", "operation frobnicate_widget uses field glorp_amount")
    toks = lc.hidden_tokens([case])
    assert any("zorblat" in t.lower() for t in toks)
    assert any("glorp_amount" in t.lower() or "frobnicate_widget" in t.lower() for t in toks)


def test_zip_is_expanded(tmp_path):
    z = tmp_path / "case.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Case/BRIEF.md", "The Zorblat queue takes QX-9917 transfers.")
    toks = lc.hidden_tokens([z])
    assert any("zorblat" in t.lower() for t in toks)


def test_plain_files_unchanged(tmp_path):
    f = tmp_path / "b.txt"
    f.write_text("The Zorblat queue.")
    assert lc._text_of(f) == "The Zorblat queue."
    unknown = tmp_path / "x.bin"
    unknown.write_text("Zorblat raw")
    assert "Zorblat" in lc._text_of(unknown)
