"""Minimal .docx / .xlsx writers (standard library only: zipfile + XML strings) for the rehearsal case files.

docx: paragraphs with styles (Title, Heading1, Heading2, normal, list), bold runs (**x** in the text), tables, and an
optional content-control wrapper (w:sdt) around a block, which is how Word templates often nest content.
xlsx: several sheets, shared strings, numbers, real date cells (serial number + date number format) and text cells
that keep leading zeros.
"""
from __future__ import annotations

import datetime as dt
import re
import zipfile
from xml.sax.saxutils import escape

_FIXED_TIME = (2026, 10, 11, 9, 0, 0)  # deterministic zip timestamps


def _zip(path, files: dict):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            zi = zipfile.ZipInfo(name, _FIXED_TIME)
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, data.encode("utf-8") if isinstance(data, str) else data)


# ------------------------------------------------------------------ docx
W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _runs(text: str) -> str:
    out = []
    for i, part in enumerate(re.split(r"\*\*", text)):
        if not part:
            continue
        rpr = "<w:rPr><w:b/></w:rPr>" if i % 2 else ""
        out.append(f'<w:r>{rpr}<w:t xml:space="preserve">{escape(part)}</w:t></w:r>')
    return "".join(out)


def _p(text: str, style: str | None = None) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}{_runs(text)}</w:p>"


def _tbl(rows: list[list[str]]) -> str:
    grid = "".join("<w:gridCol/>" for _ in rows[0])
    trs = []
    for ri, row in enumerate(rows):
        tcs = []
        for cell in row:
            txt = f"**{cell}**" if ri == 0 and cell else cell
            paras = "".join(_p(line) for line in str(cell and txt).split("\n")) or "<w:p/>"
            tcs.append(f'<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/></w:tcPr>{paras}</w:tc>')
        trs.append("<w:tr>" + "".join(tcs) + "</w:tr>")
    return ('<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/></w:tblPr>'
            f"<w:tblGrid>{grid}</w:tblGrid>" + "".join(trs) + "</w:tbl><w:p/>")


def docx(path, blocks: list):
    """blocks: ("title"|"h1"|"h2"|"p"|"li", text) | ("table", rows) | ("sdt", [blocks...])."""
    def render(bl):
        out = []
        for b in bl:
            kind = b[0]
            if kind == "table":
                out.append(_tbl(b[1]))
            elif kind == "sdt":
                out.append('<w:sdt><w:sdtPr><w:alias w:val="Bolum"/></w:sdtPr><w:sdtContent>'
                           + render(b[1]) + "</w:sdtContent></w:sdt>")
            else:
                style = {"title": "Title", "h1": "Heading1", "h2": "Heading2", "li": "ListParagraph"}.get(kind)
                text = ("• " + b[1]) if kind == "li" else b[1]
                out.append(_p(text, style))
        return "".join(out)

    body = render(blocks)
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W_NS}><w:body>{body}'
                '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" '
                'w:left="1134" w:header="709" w:footer="709" w:gutter="0"/></w:sectPr></w:body></w:document>')

    def st(sid, name, size, bold=True, based="Normal"):
        b = "<w:b/>" if bold else ""
        return (f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/><w:basedOn w:val="{based}"/>'
                f'<w:next w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="240" w:after="120"/></w:pPr>'
                f'<w:rPr>{b}<w:sz w:val="{size}"/></w:rPr></w:style>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              f'<w:styles {W_NS}><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" '
              'w:cs="Calibri"/><w:sz w:val="22"/><w:lang w:val="tr-TR"/></w:rPr></w:rPrDefault></w:docDefaults>'
              '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/>'
              '<w:pPr><w:spacing w:after="80"/></w:pPr></w:style>'
              + st("Title", "Title", 36) + st("Heading1", "heading 1", 30) + st("Heading2", "heading 2", 26)
              + st("ListParagraph", "List Paragraph", 22, bold=False) +
              '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders>'
              '<w:top w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:left w:val="single" w:sz="4" '
              'w:space="0" w:color="auto"/><w:bottom w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
              '<w:right w:val="single" w:sz="4" w:space="0" w:color="auto"/><w:insideH w:val="single" w:sz="4" '
              'w:space="0" w:color="auto"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="auto"/>'
              '</w:tblBorders></w:tblPr></w:style></w:styles>')
    _zip(path, {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.'
        'openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxml'
        'formats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override '
        'PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.'
        'document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-'
        'officedocument.wordprocessingml.styles+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.'
        'openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.'
        'org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>',
        "word/_rels/document.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships '
        'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://'
        'schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        "word/document.xml": document,
        "word/styles.xml": styles,
    })


# ------------------------------------------------------------------ xlsx
def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


class Date(str):
    """Marks an ISO date string to be written as a real Excel date cell."""


class Text(str):
    """Marks a value to be written as text even if it looks like a number (leading zeros)."""


def xlsx(path, sheets: list[tuple[str, list[list]]]):
    """sheets: [(name, rows)]; cell values: str (text), Text, Date('YYYY-MM-DD'), int/float (number), None."""
    shared, index = [], {}

    def sidx(s):
        if s not in index:
            index[s] = len(shared)
            shared.append(s)
        return index[s]

    sheet_xml = []
    for name, rows in sheets:
        out = []
        for r, row in enumerate(rows, start=1):
            cells = []
            for c, v in enumerate(row):
                ref = f"{_col(c)}{r}"
                if v is None or v == "":
                    continue
                if isinstance(v, Date):
                    serial = (dt.date.fromisoformat(v) - dt.date(1899, 12, 30)).days
                    cells.append(f'<c r="{ref}" s="1"><v>{serial}</v></c>')
                elif isinstance(v, bool):
                    cells.append(f'<c r="{ref}" t="b"><v>{int(v)}</v></c>')
                elif isinstance(v, (int, float)) and not isinstance(v, Text):
                    style = ' s="2"' if isinstance(v, float) else ""
                    cells.append(f'<c r="{ref}"{style}><v>{v}</v></c>')
                else:
                    style = ' s="3"' if r == 1 else ""
                    cells.append(f'<c r="{ref}" t="s"{style}><v>{sidx(str(v))}</v></c>')
            out.append(f'<row r="{r}">' + "".join(cells) + "</row>")
        widths = '<cols><col min="1" max="12" width="22" customWidth="1"/></cols>'
        sheet_xml.append('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.'
                         'openxmlformats.org/spreadsheetml/2006/main">' + widths + "<sheetData>" + "".join(out)
                         + "</sheetData></worksheet>")
    sst = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><sst xmlns="http://schemas.openxmlformats.org/'
           f'spreadsheetml/2006/main" count="{len(shared)}" uniqueCount="{len(shared)}">'
           + "".join(f'<si><t xml:space="preserve">{escape(s)}</t></si>' for s in shared) + "</sst>")
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats'
              '.org/spreadsheetml/2006/main"><numFmts count="2"><numFmt numFmtId="164" formatCode="dd\\.mm\\.yyyy"/>'
              '<numFmt numFmtId="165" formatCode="#,##0.00"/></numFmts><fonts count="2"><font><sz val="11"/><name '
              'val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2">'
              '<fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs '
              'count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="4">'
              '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="164" fontId="0" fillId="0" '
              'borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="165" fontId="0" fillId="0" borderId="0" '
              'xfId="0" applyNumberFormat="1"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" '
              'applyFont="1"/></cellXfs></styleSheet>')
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.'
        'openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.'
        'openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.'
        'spreadsheetml.sheet.main+xml"/>' + "".join(
            f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" ContentType="application/vnd.openxmlformats-'
            'officedocument.spreadsheetml.worksheet+xml"/>' for i in range(len(sheets)))
        + '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.'
        'spreadsheetml.sharedStrings+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.'
        'openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.'
        'org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.'
        'openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/'
        'relationships"><sheets>' + "".join(
            f'<sheet name="{escape(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, (n, _) in enumerate(sheets))
        + "</sheets></workbook>",
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns='
        '"http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(
            f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            f'worksheet" Target="worksheets/sheet{i + 1}.xml"/>' for i in range(len(sheets)))
        + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
        f'relationships/sharedStrings" Target="sharedStrings.xml"/><Relationship Id="rId{len(sheets) + 2}" Type="'
        'http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>",
        "xl/sharedStrings.xml": sst,
        "xl/styles.xml": styles,
    }
    for i, x in enumerate(sheet_xml):
        files[f"xl/worksheets/sheet{i + 1}.xml"] = x
    _zip(path, files)
