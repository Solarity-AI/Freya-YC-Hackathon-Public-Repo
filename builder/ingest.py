"""Case folder (or .zip) -> CaseDocs: every document of the bank read as text, classified, ordered. Owner: ingest.

Standard library first (zipfile + xml for Word/Excel/PowerPoint/draw.io, csv, json); optional helpers when present:
`pdftotext` (poppler) or pypdf for PDF, openpyxl for Excel when the stdlib reader fails, macOS `textutil` for legacy
.doc/.rtf/.odt. A file that cannot be read is skipped with a warning; nothing here raises on odd input except
`load_case` on a path that does not exist (CaseError).

CONTRACT NOTE (how other workstreams call this module):
- load_case(path, mock_url=None) -> CaseDocs (a plain dict, JSON-serialisable except nothing; see below).
    path: a case folder, a .zip of one, or a single file. A .zip is extracted to a temp folder (zip-slip safe,
    __MACOSX/._*/.DS_Store/~$ lock files ignored, cp437 file names re-decoded as UTF-8 when they are).
- CaseDocs = {
    "root": str,                      # the folder that was walked (the extracted folder for a .zip)
    "source": str,                    # what the caller passed
    "mock_url": str | None,           # http(s) base of our bank mock, trailing '/' removed
    "docs": [Doc, ...],               # ordered: brief first, readme second, then by path; test_customers and
                                      #   example_conversation docs last (they are data, not rules)
    "openapi": dict | None,           # the first OpenAPI document found in the folder (json/yaml, by content)
    "openapi_path": str | None,
    "contract_docs": [Doc, ...],      # kind == "service_contract" (an OpenAPI file is one too)
    "customers_tables": [Table, ...], # every table of the test_customers docs, each with "doc" = Doc["rel"]
    "examples": [Doc, ...],           # kind == "example_conversation"
    "files": [{"rel", "kind", "reader", "bytes", "chars", "status": "read"|"skipped"|"empty", "note"}],
    "warnings": [str, ...],
  }
  Doc   = {"path", "rel", "name", "kind", "reader", "text", "tables": [Table], "bytes", "sha256", "is_openapi",
           "kind_why": str}
  Table = {"name": sheet / table title or "", "header": [str], "rows": [[str]]}
- KINDS: brief readme analysis flow announcements service_contract test_customers qa example_conversation other.
  Classified from README.md mentions + file/folder names + content, with generic multilingual keywords only.
- read_document(path) -> (text, tables, reader, warnings)  one file, any supported type (never raises).
- tool_api_for(case, out_dir, fetch=None) -> path | None: the tool API (OpenAPI) as a JSON file in out_dir with
    servers = [mock_url]. Order: OpenAPI inside the case folder, else GET <mock_url>/openapi.json. None when neither
    exists (the contract stage then derives one from case["contract_docs"]).
- with_server(doc, url) -> a copy of an OpenAPI dict whose servers[0].url is `url`.
"""
import csv
import hashlib
import html
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
import zlib

KINDS = ("brief", "readme", "analysis", "flow", "announcements", "service_contract", "test_customers", "qa",
         "example_conversation", "other")
MAX_FILE_BYTES = 25 * 1024 * 1024
TEXT_SUFFIXES = {".md", ".markdown", ".txt", ".text", ".eml", ".mmd", ".mermaid", ".puml", ".log", ".rst"}
TABLE_SUFFIXES = {".csv", ".tsv"}
DATA_SUFFIXES = {".json", ".yaml", ".yml"}
WORD_SUFFIXES = {".docx", ".docm", ".dotx"}
EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xltx"}
PPT_SUFFIXES = {".pptx"}
PDF_SUFFIXES = {".pdf"}
_VSDX = ".vsdx"
DRAW_SUFFIXES = {".drawio", ".xml", ".bpmn", ".svg", _VSDX}
HTML_SUFFIXES = {".html", ".htm"}
TEXTUTIL_SUFFIXES = {".doc", ".rtf", ".odt", ".wordml", ".webarchive"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".heic"}
READABLE_SUFFIXES = (TEXT_SUFFIXES | TABLE_SUFFIXES | DATA_SUFFIXES | WORD_SUFFIXES | EXCEL_SUFFIXES | PPT_SUFFIXES
                     | PDF_SUFFIXES | DRAW_SUFFIXES | HTML_SUFFIXES | TEXTUTIL_SUFFIXES)
_JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}


class CaseError(Exception):
    pass


# ============================================================================================ text helpers

def decode_bytes(data):
    """Bytes -> str: UTF-8 (BOM dropped), UTF-16 with a BOM, else Windows Turkish (cp1254), else latin-1."""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp1254")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def _norm_newlines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("﻿", "")


def fold(text):
    """Casefold + strip accents, Turkish-aware (I/ı/İ -> i), separators to spaces: for keyword matching only."""
    s = str(text).replace("İ", "i").replace("I", "i").replace("ı", "i")
    s = unicodedata.normalize("NFKD", s.casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[_\-.\s/\\]+", " ", s).strip()


def _cell(text):
    """One markdown table cell: newlines -> <br>, pipes escaped, whitespace collapsed."""
    s = str(text if text is not None else "")
    s = re.sub(r"[ \t ]+", " ", s).strip()
    s = _br_lines(s)
    return s.replace("|", "\\|")


def _br_lines(s):
    """Every run of whitespace holding a newline -> ' <br> ' (a linear form of re.sub(r'\\s*\\n\\s*', ...),
    which backtracks on long whitespace runs)."""
    if "\n" not in s:
        return s
    parts = s.split("\n")
    mid = [x.strip() for x in parts[1:-1]]
    return " <br> ".join([parts[0].rstrip()] + [x for x in mid if x] + [parts[-1].lstrip()])


def md_table(header, rows):
    """header + rows -> markdown pipe table text (rows padded to the widest row)."""
    width = max([len(header)] + [len(r) for r in rows] + [1])
    hdr = list(header) + [""] * (width - len(header))
    out = ["| " + " | ".join(_cell(c) for c in hdr) + " |", "|" + "---|" * width]
    for r in rows:
        r = list(r) + [""] * (width - len(r))
        out.append("| " + " | ".join(_cell(c) for c in r) + " |")
    return "\n".join(out)


def _trim_grid(grid):
    """Drop empty rows and trailing empty columns."""
    grid = [[("" if c is None else str(c)) for c in r] for r in grid]
    grid = [r for r in grid if any(c.strip() for c in r)]
    if not grid:
        return []
    width = max(len(r) for r in grid)
    while width > 0 and all(len(r) < width or not r[width - 1].strip() for r in grid):
        width -= 1
    return [(r + [""] * width)[:width] for r in grid]


def _table_from_grid(grid, name=""):
    grid = _trim_grid(grid)
    if not grid:
        return None
    return {"name": name, "header": grid[0], "rows": grid[1:]}


# ============================================================================================ Word (.docx)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
_ROMAN = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
          (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]


def _roman(n):
    out = ""
    for v, s in _ROMAN:
        while n >= v:
            out += s
            n -= v
    return out


def _letters(n):
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(97 + r) + s
    return s


def _fmt_num(fmt, n):
    if fmt in ("lowerLetter",):
        return _letters(n)
    if fmt in ("upperLetter",):
        return _letters(n).upper()
    if fmt in ("lowerRoman",):
        return _roman(n)
    if fmt in ("upperRoman",):
        return _roman(n).upper()
    return str(n)


def _xml(z, name):
    try:
        return ET.fromstring(z.read(name))
    except (KeyError, ET.ParseError):
        return None


class _Numbering:
    """word/numbering.xml: list paragraphs get their number ('3.', 'b)') or a bullet ('-')."""

    def __init__(self, root):
        self.abstract, self.num2abs, self.counters = {}, {}, {}
        if root is None:
            return
        for a in root.findall(W + "abstractNum"):
            lv = {}
            for lvl in a.findall(W + "lvl"):
                ilvl = int(lvl.get(W + "ilvl") or 0)
                fmt = lvl.find(W + "numFmt")
                txt = lvl.find(W + "lvlText")
                start = lvl.find(W + "start")
                lv[ilvl] = {"fmt": fmt.get(W + "val") if fmt is not None else "decimal",
                            "text": txt.get(W + "val") if txt is not None else "%1.",
                            "start": int(start.get(W + "val")) if start is not None else 1}
            self.abstract[a.get(W + "abstractNumId")] = lv
        for n in root.findall(W + "num"):
            a = n.find(W + "abstractNumId")
            if a is not None:
                self.num2abs[n.get(W + "numId")] = a.get(W + "val")

    def label(self, num_id, ilvl):
        aid = self.num2abs.get(num_id)
        levels = self.abstract.get(aid)
        if not levels:
            return "-"
        lvl = levels.get(ilvl) or {"fmt": "decimal", "text": "%1.", "start": 1}
        if lvl["fmt"] in ("bullet", "none"):
            return "-"
        cnt = self.counters.setdefault(aid, {})
        cnt[ilvl] = cnt.get(ilvl, lvl["start"] - 1) + 1
        for deeper in [k for k in cnt if k > ilvl]:
            del cnt[deeper]

        def repl(m):
            k = int(m.group(1)) - 1
            lk = levels.get(k) or {"fmt": "decimal", "start": 1}
            return _fmt_num(lk["fmt"], cnt.get(k, lk["start"]))
        out = re.sub(r"%(\d)", repl, lvl["text"]).strip()
        return out or "-"


class _Docx:
    def __init__(self, z):
        self.z = z
        self.numbering = _Numbering(_xml(z, "word/numbering.xml"))
        self.heading = {}
        styles = _xml(z, "word/styles.xml")
        for st in (styles.findall(W + "style") if styles is not None else []):
            sid = st.get(W + "styleId")
            name_el = st.find(W + "name")
            name = (name_el.get(W + "val") if name_el is not None else "") or ""
            m = re.match(r"(?i)^\s*heading\s*(\d)\s*$", name)
            lvl = None
            if m:
                lvl = int(m.group(1))
            elif re.match(r"(?i)^\s*title\s*$", name):
                lvl = 1
            else:
                ol = st.find(W + "pPr/" + W + "outlineLvl")
                if ol is not None and (ol.get(W + "val") or "").isdigit() and int(ol.get(W + "val")) < 9:
                    lvl = int(ol.get(W + "val")) + 1
            if lvl:
                self.heading[sid] = min(lvl, 6)
        self.tables = []

    # --- inline text
    def _inline(self, el, out, boxes, br="\n"):
        for ch in el:
            tag = ch.tag
            if tag == W + "t":
                out.append(ch.text or "")
            elif tag in (W + "tab", W + "ptab"):
                out.append(" ")
            elif tag in (W + "br", W + "cr"):
                out.append(br)
            elif tag == W + "noBreakHyphen":
                out.append("-")
            elif tag == W + "txbxContent":
                boxes.append(ch)
            elif tag == MC + "Fallback":
                continue                                  # the same content as mc:Choice
            elif tag in (W + "delText", W + "instrText", W + "pPr", W + "rPr", W + "del"):
                continue
            else:
                self._inline(ch, out, boxes, br)

    def para_text(self, p, boxes, br="\n"):
        out = []
        self._inline(p, out, boxes, br)
        return re.sub(r"[ \t ]+", " ", "".join(out)).strip()

    def para_line(self, p, boxes):
        text = self.para_text(p, boxes)
        if not text:
            return ""
        ppr = p.find(W + "pPr")
        if ppr is not None:
            st = ppr.find(W + "pStyle")
            sid = st.get(W + "val") if st is not None else None
            ol = ppr.find(W + "outlineLvl")
            lvl = self.heading.get(sid)
            if lvl is None and ol is not None and (ol.get(W + "val") or "").isdigit() and int(ol.get(W + "val")) < 9:
                lvl = int(ol.get(W + "val")) + 1
            num = ppr.find(W + "numPr")
            if num is not None and lvl is None:
                nid = num.find(W + "numId")
                il = num.find(W + "ilvl")
                nid = nid.get(W + "val") if nid is not None else None
                ilvl = int(il.get(W + "val") or 0) if il is not None else 0
                if nid and nid != "0":
                    return "  " * ilvl + self.numbering.label(nid, ilvl) + " " + text
            if lvl:
                return "#" * lvl + " " + text
        return text

    # --- blocks
    def blocks(self, el, out):
        for ch in el:
            if ch.tag == W + "p":
                boxes = []
                line = self.para_line(ch, boxes)
                if line:
                    out.append(line)
                for b in boxes:
                    self.blocks(b, out)
            elif ch.tag == W + "tbl":
                grid, title = self.table_grid(ch)
                t = _table_from_grid(grid, title)
                if t:
                    self.tables.append(t)
                    out.append("")
                    out.append(md_table(t["header"], t["rows"]))
                    out.append("")
            elif ch.tag in (W + "sectPr", W + "pPr", W + "tblPr", W + "tblGrid"):
                continue
            else:                                         # sdt, customXml, ins, smartTag...: look inside
                self.blocks(ch, out)

    def _cells(self, tr):
        for ch in tr:
            if ch.tag == W + "tc":
                yield ch
            elif ch.tag in (W + "sdt", W + "sdtContent", W + "customXml"):
                yield from self._cells(ch)

    def cell_text(self, tc):
        parts = []
        for ch in tc:
            if ch.tag == W + "p":
                boxes = []
                t = self.para_line(ch, boxes)
                if t:
                    parts.append(t)
                for b in boxes:
                    sub = []
                    self.blocks(b, sub)
                    parts += [s for s in sub if s.strip()]
            elif ch.tag == W + "tbl":                     # nested table: rows as 'a / b' joined with '; '
                grid, _ = self.table_grid(ch)
                rows = [" / ".join(c for c in r if c.strip()) for r in _trim_grid(grid)]
                parts.append("; ".join(r for r in rows if r))
            elif ch.tag != W + "tcPr":
                sub = []
                self.blocks(ch, sub)
                parts += [s for s in sub if s.strip()]
        return "\n".join(parts)

    def table_grid(self, tbl):
        grid, above = [], {}
        rows = list(tbl.iter(W + "tr"))
        own = {id(x) for x in tbl.findall(W + "tr")}
        for sdt in tbl.findall(W + "sdt"):            # rows wrapped in content controls
            own |= {id(x) for x in sdt.iter(W + "tr")}
        rows = [tr for tr in rows if id(tr) in own]
        for tr in rows:
            row, col = [], 0
            for tc in self._cells(tr):
                pr = tc.find(W + "tcPr")
                span = 1
                vcont = False
                if pr is not None:
                    gs = pr.find(W + "gridSpan")
                    if gs is not None and (gs.get(W + "val") or "").isdigit():
                        span = max(1, int(gs.get(W + "val")))
                    vm = pr.find(W + "vMerge")
                    vcont = vm is not None and (vm.get(W + "val") or "continue") != "restart"
                text = above.get(col, "") if vcont else self.cell_text(tc)
                for k in range(span):
                    row.append(text if k == 0 else "")
                    above[col + k] = text if k == 0 else ""
                col += span
            grid.append(row)
        return grid, ""


def docx_read(path):
    """-> (markdown text, tables). Body in order (headings '#', list numbers, tables as markdown tables, text boxes,
    content controls), then headers/footers, footnotes, endnotes and comments when they hold text."""
    with zipfile.ZipFile(path) as z:
        d = _Docx(z)
        root = _xml(z, "word/document.xml")
        if root is None:
            raise ValueError("no word/document.xml")
        out = []
        body = root.find(W + "body")
        d.blocks(body if body is not None else root, out)
        extra_seen = set()
        names = z.namelist()
        for label, pat in (("header", r"word/header\d*\.xml$"), ("footer", r"word/footer\d*\.xml$"),
                           ("footnote", r"word/footnotes\.xml$"), ("endnote", r"word/endnotes\.xml$"),
                           ("comment", r"word/comments\.xml$")):
            for n in sorted(x for x in names if re.match(pat, x)):
                r = _xml(z, n)
                if r is None:
                    continue
                sub = []
                d.blocks(r, sub)
                for s in sub:
                    s = s.strip()
                    if s and s not in extra_seen and s not in out:
                        extra_seen.add(s)
                        out.append("[%s] %s" % (label, s))
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n", d.tables


# ============================================================================================ Excel (.xlsx)

S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_DATE_BUILTIN = set(range(14, 23)) | {27, 30, 36, 45, 46, 47, 50, 57}


def _col_index(ref):
    m = re.match(r"([A-Za-z]+)", ref or "")
    if not m:
        return None
    n = 0
    for ch in m.group(1).upper():
        n = n * 26 + ord(ch) - 64
    return n - 1


def _serial_to_iso(v, date1904=False):
    import datetime as _dt
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    base = _dt.datetime(1904, 1, 1) if date1904 else _dt.datetime(1899, 12, 30)
    d = base + _dt.timedelta(days=f)
    if abs(f - int(f)) < 1e-9:
        return d.strftime("%Y-%m-%d")
    if f < 1:
        return d.strftime("%H:%M")
    return d.strftime("%Y-%m-%d %H:%M")


def _num_text(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if f == int(f) and abs(f) < 1e15:
        return str(int(f))
    return repr(round(f, 10)).rstrip("0").rstrip(".") if "e" not in repr(f) else str(f)


def _date_styles(z):
    st = _xml(z, "xl/styles.xml")
    if st is None:
        return set()
    custom = {}
    nf = st.find(S + "numFmts")
    for f in (nf.findall(S + "numFmt") if nf is not None else []):
        code = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', "", f.get("formatCode") or "").lower()
        custom[int(f.get("numFmtId"))] = bool(re.search(r"[dy]|m{1,4}(?!s)", code)) and "0" not in code[:1]
    out = set()
    xfs = st.find(S + "cellXfs")
    for i, xf in enumerate(xfs.findall(S + "xf") if xfs is not None else []):
        nid = int(xf.get("numFmtId") or 0)
        if nid in _DATE_BUILTIN or custom.get(nid):
            out.add(i)
    return out


def _sheet_paths(z):
    """[(sheet name, part path)] in workbook order (via workbook.xml.rels, not file names)."""
    wb = _xml(z, "xl/workbook.xml")
    rels = _xml(z, "xl/_rels/workbook.xml.rels")
    targets = {}
    for r in (rels.findall(PKG_REL + "Relationship") if rels is not None else []):
        t = r.get("Target") or ""
        t = t.lstrip("/") if t.startswith("/") else "xl/" + t
        targets[r.get("Id")] = re.sub(r"/[^/]+/\.\./", "/", t)
    out = []
    if wb is not None:
        for i, sh in enumerate(wb.iter(S + "sheet")):
            if (sh.get("state") or "") == "veryHidden":
                continue
            part = targets.get(sh.get(R_NS + "id")) or "xl/worksheets/sheet%d.xml" % (i + 1)
            out.append((sh.get("name") or "Sheet%d" % (i + 1), part))
    if not out:
        out = [(pathlib.PurePosixPath(n).stem, n) for n in sorted(z.namelist())
               if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
    return out


def _xlsx_stdlib(path):
    sheets = []
    with zipfile.ZipFile(path) as z:
        shared = []
        sst = _xml(z, "xl/sharedStrings.xml")
        for si in (sst.findall(S + "si") if sst is not None else []):
            phonetic = {id(t) for rph in si.findall(S + "rPh") for t in rph.iter(S + "t")}
            shared.append("".join(t.text or "" for t in si.iter(S + "t") if id(t) not in phonetic))
        wb = _xml(z, "xl/workbook.xml")
        pr = wb.find(S + "workbookPr") if wb is not None else None
        date1904 = pr is not None and (pr.get("date1904") or "").lower() in ("1", "true")
        dates = _date_styles(z)
        for name, part in _sheet_paths(z):
            root = _xml(z, part)
            if root is None:
                continue
            grid = []
            for row in root.iter(S + "row"):
                vals = {}
                nxt = 0
                for c in row.findall(S + "c"):
                    ci = _col_index(c.get("r"))
                    ci = nxt if ci is None else ci
                    nxt = ci + 1
                    t = c.get("t") or "n"
                    v = c.find(S + "v")
                    raw = v.text if v is not None and v.text is not None else ""
                    if t == "s":
                        val = shared[int(raw)] if raw.isdigit() and int(raw) < len(shared) else raw
                    elif t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(S + "t"))
                    elif t == "b":
                        val = "TRUE" if raw == "1" else "FALSE"
                    elif t in ("str", "e"):
                        val = raw
                    elif raw != "" and (c.get("s") or "").isdigit() and int(c.get("s")) in dates:
                        val = _serial_to_iso(raw, date1904)
                    else:
                        val = _num_text(raw) if raw != "" else ""
                    vals[ci] = val
                if vals:
                    r = [""] * (max(vals) + 1)
                    for k, val in vals.items():
                        r[k] = val
                    grid.append(r)
                else:
                    grid.append([])
            sheets.append((name, grid))
    return sheets


def _xlsx_openpyxl(path):
    import datetime as _dt
    import openpyxl                                       # optional
    wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
    sheets = []
    for ws in wb.worksheets:
        grid = []
        for row in ws.iter_rows(values_only=True):
            r = []
            for v in row:
                if isinstance(v, _dt.datetime):
                    v = v.strftime("%Y-%m-%d") if (v.hour, v.minute, v.second) == (0, 0, 0) \
                        else v.strftime("%Y-%m-%d %H:%M")
                elif isinstance(v, _dt.date):
                    v = v.strftime("%Y-%m-%d")
                elif isinstance(v, float):
                    v = _num_text(v)
                r.append("" if v is None else str(v))
            grid.append(r)
        sheets.append((ws.title, grid))
    return sheets


def xlsx_read(path):
    """-> (markdown text, tables): every sheet as '## Sheet: <name>' + a markdown table (first non-empty row = header).
    Shared/inline strings, booleans and date-formatted cells (ISO dates) are resolved. The stdlib reader is used first
    (deterministic everywhere); openpyxl only when it fails."""
    try:
        sheets = _xlsx_stdlib(path)
    except Exception:                                     # noqa: BLE001 - broken or exotic workbook
        sheets = _xlsx_openpyxl(path)
    out, tables = [], []
    for name, grid in sheets:
        t = _table_from_grid(grid, name)
        out.append("## Sheet: %s" % name)
        if t is None:
            out.append("(empty sheet)")
        else:
            tables.append(t)
            out.append(md_table(t["header"], t["rows"]))
        out.append("")
    return "\n".join(out).strip() + "\n", tables


# ============================================================================================ PowerPoint (.pptx)

A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _xml_number(name):
    """12 for '.../slide12.xml' (the trailing number of the file stem, 0 when there is none); no regex."""
    stem = name[:-4] if name.endswith(".xml") else name
    digits = len(stem) - len(stem.rstrip("0123456789"))
    return int(stem[len(stem) - digits:]) if digits else 0


def pptx_read(path):
    with zipfile.ZipFile(path) as z:
        slides = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                        key=_xml_number)
        out = []
        for i, n in enumerate(slides, 1):
            root = _xml(z, n)
            if root is None:
                continue
            out.append("## Slide %d" % i)
            for p in root.iter(A_NS + "p"):
                t = "".join(x.text or "" for x in p.iter(A_NS + "t")).strip()
                if t:
                    out.append(t)
            out.append("")
    return "\n".join(out).strip() + "\n", []


# ============================================================================================ PDF

def pdf_read(path, run=subprocess.run, which=shutil.which):
    """pdftotext -layout (poppler) when installed, else pypdf. -> (text, [], warnings)."""
    warns = []
    if which("pdftotext"):
        try:
            r = run(["pdftotext", "-layout", "-enc", "UTF-8", str(path), "-"], capture_output=True, timeout=120)
            if r.returncode == 0:
                text = decode_bytes(r.stdout)
                if text.strip():
                    return _pdf_clean(text), [], warns
            else:
                warns.append("pdftotext failed (exit %s)" % r.returncode)
        except (OSError, subprocess.SubprocessError) as e:
            warns.append("pdftotext failed: %s" % type(e).__name__)
    try:
        import pypdf                                      # optional
        text = "\n\f".join((p.extract_text() or "") for p in pypdf.PdfReader(str(path)).pages)
        if text.strip():
            return _pdf_clean(text), [], warns
    except ImportError:
        if not which("pdftotext"):
            warns.append("no PDF reader: install poppler (pdftotext) or pypdf")
    except Exception as e:                                # noqa: BLE001
        warns.append("pypdf failed: %s" % type(e).__name__)
    warns.append("PDF has no extractable text (scanned image?)")
    return "", [], warns


def _pdf_clean(text):
    pages = _norm_newlines(text).split("\f")
    out = []
    for i, p in enumerate(pages, 1):
        lines = [ln.rstrip() for ln in p.split("\n")]
        body = "\n".join(lines).strip("\n")
        if body.strip():
            if len(pages) > 1:
                out.append("[page %d]" % i)
            out.append(body)
    return "\n".join(out) + "\n"


# ============================================================================================ drawings

_MX_TAG = re.compile(r"<[^>]+>")


def _label(v):
    v = html.unescape(_MX_TAG.sub(" ", re.sub(r"(?i)<br\s*/?>|</div>|</p>", " ", v or "")))
    return re.sub(r"\s+", " ", v).strip()


def _drawio_models(root):
    """mxGraphModel elements of a draw.io file (plain or compressed <diagram> pages) -> [(page name, model)]."""
    out = []
    if root.tag == "mxGraphModel":
        return [("", root)]
    for dg in root.iter("diagram"):
        model = dg.find("mxGraphModel")
        if model is None and (dg.text or "").strip():
            try:
                raw = zlib.decompress(__import__("base64").b64decode(dg.text.strip()), -15)
                model = ET.fromstring(urllib.parse.unquote(raw.decode("utf-8")))
            except Exception:                             # noqa: BLE001
                model = None
        if model is not None:
            out.append((dg.get("name") or "", model))
    if not out:
        out += [("", m) for m in root.iter("mxGraphModel")]
    return out


def drawio_text(root):
    """Nodes and edges of a draw.io / mxGraph drawing as a text flow ('A -> B [label]')."""
    out = []
    for name, model in _drawio_models(root):
        for obj in model.iter():                          # <object label=...><mxCell/></object> / <UserObject>
            if obj.tag in ("object", "UserObject"):
                c = obj.find("mxCell")
                if c is not None and obj.get("id"):
                    c.set("value", obj.get("label") or c.get("value") or "")
                    c.set("id", obj.get("id"))
        cells = {c.get("id"): c for c in model.iter("mxCell") if c.get("id")}
        labels = {cid: _label(c.get("value")) for cid, c in cells.items()}
        edge_labels = {}
        for cid, c in cells.items():                      # labels drawn as children of an edge
            par = cells.get(c.get("parent"))
            if par is not None and par.get("edge") == "1" and labels.get(cid):
                edge_labels.setdefault(c.get("parent"), []).append(labels[cid])
        nodes = [labels[cid] for cid, c in cells.items() if c.get("vertex") == "1" and labels.get(cid)
                 and (cells.get(c.get("parent")) is None or cells[c.get("parent")].get("edge") != "1")]
        edges = []
        for cid, c in cells.items():
            if c.get("edge") != "1":
                continue
            lab = " / ".join(x for x in [labels.get(cid)] + edge_labels.get(cid, []) if x)
            a = labels.get(c.get("source")) or "(%s)" % (c.get("source") or "?")
            b = labels.get(c.get("target")) or "(%s)" % (c.get("target") or "?")
            edges.append("- %s -> %s%s" % (a, b, " [%s]" % lab if lab else ""))
        out.append("## Diagram%s" % (": " + name if name else ""))
        out.append("Steps:")
        out += ["- %s" % n for n in nodes] or ["- (none)"]
        out.append("Flow:")
        out += edges or ["- (no connections)"]
        out.append("")
    return "\n".join(out)


def _svg_text(root):
    lines = []
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] == "text":
            t = re.sub(r"\s+", " ", "".join(el.itertext())).strip()
            if t:
                lines.append(t)
        elif el.tag.rsplit("}", 1)[-1] == "div" and (el.text or "").strip():   # foreignObject labels
            lines.append(el.text.strip())
    return "\n".join(lines)


def _bpmn_text(root):
    names, flows = {}, []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if el.get("id") and el.get("name") and tag != "sequenceFlow":
            names[el.get("id")] = el.get("name")
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] in ("sequenceFlow", "messageFlow"):
            a = names.get(el.get("sourceRef"), el.get("sourceRef"))
            b = names.get(el.get("targetRef"), el.get("targetRef"))
            flows.append("- %s -> %s%s" % (a, b, " [%s]" % el.get("name") if el.get("name") else ""))
    return "Steps:\n" + "\n".join("- %s" % v for v in names.values()) + "\nFlow:\n" + "\n".join(flows) + "\n"


def drawing_read(path):
    """.drawio/.xml/.bpmn/.svg/.vsdx -> text."""
    suf = pathlib.Path(path).suffix.lower()
    if suf == _VSDX:
        with zipfile.ZipFile(path) as z:
            out = []
            for n in sorted(x for x in z.namelist() if re.match(r"visio/pages/page\d+\.xml$", x)):
                root = _xml(z, n)
                for el in (root.iter() if root is not None else []):
                    if el.tag.rsplit("}", 1)[-1] == "Text":
                        t = re.sub(r"\s+", " ", "".join(el.itertext())).strip()
                        if t:
                            out.append("- " + t)
            return "\n".join(out) + "\n", []
    data = pathlib.Path(path).read_bytes()
    root = ET.fromstring(data)
    tag = root.tag.rsplit("}", 1)[-1]
    if tag in ("mxfile", "mxGraphModel") or root.find(".//mxGraphModel") is not None:
        return drawio_text(root), []
    if tag == "svg":
        if "mxGraphModel" in decode_bytes(data) and root.get("content"):
            try:
                return drawio_text(ET.fromstring(root.get("content"))), []
            except ET.ParseError:
                pass
        return _svg_text(root) + "\n", []
    if tag == "definitions" or "bpmn" in root.tag.lower():
        return _bpmn_text(root), []
    text = re.sub(r"[ \t]+", " ", "\n".join(t.strip() for t in root.itertext() if t.strip()))
    return text + "\n", []


# ============================================================================================ others

_HTML_DROP = re.compile(r"(?is)<(script|style)\b.*?</\1\s*>|<!--.*?-->")
_HTML_BREAK = re.compile(r"(?i)<(br|p|div|li|tr|h[1-6])\b[^>]*>")
_HTML_CELL = re.compile(r"(?i)<t[dh]\b[^>]*>")
_HTML_TAG = re.compile(r"<[^>]*>")


def html_read(path):
    """HTML -> text: scripts/styles/comments dropped, block tags become line breaks, cells ' | '."""
    text = _HTML_DROP.sub(" ", decode_bytes(pathlib.Path(path).read_bytes()))
    text = _HTML_CELL.sub(" | ", _HTML_BREAK.sub("\n", text))
    text = html.unescape(_HTML_TAG.sub("", text))
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip() + "\n", []


def csv_read(path):
    text = _norm_newlines(decode_bytes(pathlib.Path(path).read_bytes()))
    delim = "\t" if pathlib.Path(path).suffix.lower() == ".tsv" else None
    if delim is None:
        try:
            delim = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|").delimiter
        except csv.Error:
            delim = ","
    grid = list(csv.reader(io.StringIO(text), delimiter=delim))
    t = _table_from_grid(grid, pathlib.Path(path).stem)
    if t is None:
        return "", []
    return md_table(t["header"], t["rows"]) + "\n", [t]


def textutil_read(path, run=subprocess.run, which=shutil.which):
    if not which("textutil"):
        raise ValueError("no reader for %s on this machine (macOS textutil missing)" % pathlib.Path(path).suffix)
    r = run(["textutil", "-convert", "txt", "-stdout", str(path)], capture_output=True, timeout=60)
    if r.returncode != 0:
        raise ValueError("textutil failed (exit %s)" % r.returncode)
    return _norm_newlines(decode_bytes(r.stdout)), []


def _parse_data(text, suffix):
    if suffix == ".json":
        try:
            return json.loads(text)
        except ValueError:
            return None
    try:
        import yaml                                       # optional (requirements.txt lists it)
        return yaml.safe_load(text)
    except Exception:                                     # noqa: BLE001
        return None


def is_openapi_doc(doc):
    """Same test as openapi_model.is_openapi_file: a mapping with an 'openapi' (or 'swagger') key."""
    return isinstance(doc, dict) and ("openapi" in doc or "swagger" in doc)


def _records_table(obj, name=""):
    """A list of flat-ish objects (or {"customers": [...]}) -> a table; else None."""
    if isinstance(obj, dict):
        lists = [(k, v) for k, v in obj.items() if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)]
        if len(lists) == 1:
            return _records_table(lists[0][1], lists[0][0])
        return None
    if not (isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj)):
        return None
    cols = []
    for rec in obj:
        for k in rec:
            if k not in cols:
                cols.append(k)

    def cell(v):
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return {"name": name, "header": cols, "rows": [[cell(r.get(c, "")) for c in cols] for r in obj]}


def read_document(path):
    """One file -> (text, tables, reader, warnings). Never raises; unreadable -> ('', [], 'skipped', [why])."""
    p = pathlib.Path(path)
    suf = p.suffix.lower()
    try:
        size = p.stat().st_size
    except OSError as e:
        return "", [], "skipped", ["cannot stat: %s" % e]
    if size > MAX_FILE_BYTES:
        return "", [], "skipped", ["file too large (%d bytes > %d)" % (size, MAX_FILE_BYTES)]
    if suf in IMAGE_SUFFIXES:
        return "", [], "skipped", ["image file: not read (no OCR); a flow drawn as a picture must be described "
                                   "elsewhere"]
    try:
        if suf in TEXT_SUFFIXES or suf == "":
            text = _norm_newlines(decode_bytes(p.read_bytes()))
            if suf == "" and "\x00" in text[:2048]:
                return "", [], "skipped", ["binary file without an extension"]
            return text, [], "text", []
        if suf in TABLE_SUFFIXES:
            text, tables = csv_read(p)
            return text, tables, "csv", []
        if suf in DATA_SUFFIXES:
            text = _norm_newlines(decode_bytes(p.read_bytes()))
            obj = _parse_data(text, suf)
            t = _records_table(obj, p.stem) if obj is not None and not is_openapi_doc(obj) else None
            return text, [t] if t else [], "data", []
        if suf in WORD_SUFFIXES:
            text, tables = docx_read(p)
            return text, tables, "docx", []
        if suf in EXCEL_SUFFIXES:
            text, tables = xlsx_read(p)
            return text, tables, "xlsx", []
        if suf in PPT_SUFFIXES:
            text, tables = pptx_read(p)
            return text, tables, "pptx", []
        if suf in PDF_SUFFIXES:
            text, tables, warns = pdf_read(p)
            return text, tables, "pdf", warns
        if suf in DRAW_SUFFIXES:
            text, tables = drawing_read(p)
            return text, tables, "drawing", []
        if suf in HTML_SUFFIXES:
            text, tables = html_read(p)
            return text, tables, "html", []
        if suf in TEXTUTIL_SUFFIXES:
            text, tables = textutil_read(p)
            return text, tables, "textutil", []
    except Exception as e:                                # noqa: BLE001 - one bad file never stops the build
        return "", [], "skipped", ["unreadable %s: %s: %s" % (suf or "file", type(e).__name__, str(e)[:160])]
    return "", [], "skipped", ["unsupported file type %r: skipped" % (suf or "(none)")]


# ============================================================================================ zip

def _zip_name(info):
    name = info.filename
    if not info.flag_bits & 0x800:                        # not flagged UTF-8: Python decoded cp437; try UTF-8
        try:
            name = name.encode("cp437").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return name


def extract_zip(zpath, dest=None):
    """Safe extraction (no absolute paths, no '..', junk skipped) -> the case root: the single top folder when the
    zip holds exactly one, else the extraction folder."""
    dest = pathlib.Path(dest or tempfile.mkdtemp(prefix="freya-case-"))
    dest.mkdir(parents=True, exist_ok=True)
    root_res = dest.resolve()
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            name = _zip_name(info).replace("\\", "/")
            parts = [x for x in name.split("/") if x not in ("", ".")]
            if not parts or ".." in parts or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
                continue
            if parts[0] == "__MACOSX" or _junk(parts[-1]):
                continue
            target = dest.joinpath(*parts)
            if not str(target.resolve()).startswith(str(root_res)):
                continue
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
    tops = [x for x in dest.iterdir() if not _junk(x.name)]
    if len(tops) == 1 and tops[0].is_dir():
        return tops[0]
    return dest


def _junk(name):
    n = name.lower()
    return n.startswith((".", "~$", "._")) or n in _JUNK_NAMES


def list_files(root):
    """Every candidate file under root (sorted, junk and hidden folders skipped)."""
    root = pathlib.Path(root)
    if root.is_file():
        return [root]
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "__MACOSX" and d != "__pycache__")
        for f in sorted(filenames):
            if not _junk(f):
                out.append(pathlib.Path(dirpath) / f)
    return sorted(out, key=lambda p: str(p.relative_to(root)).casefold())


# ============================================================================================ classification

_KW = {
    "brief": [r"\bbrief", r"\bbrif\b", r"\bgorev tanim", r"\bonce bunu oku", r"\bread (this )?first\b",
              r"\bilk once\b"],
    "readme": [r"\breadme\b", r"\bbeni ?oku\b", r"\boku ?beni\b", r"\bread ?me\b"],
    "analysis": [r"\banaliz", r"\banaly[sz]", r"\bgereksinim", r"\brequirement", r"\bis kural", r"\bbusiness rule",
                 r"\bpolitika", r"\bpolicy", r"\bprosedur", r"\bprocedure", r"\bspesifikasyon", r"\bspecification"],
    "flow": [r"\bakis", r"\bflow", r"\bdiyagram", r"\bdiagram", r"\bsemasi\b", r"\bsema\b", r"\bcizim",
             r"\bdrawing", r"\bsurec", r"\bprocess", r"\bdrawio\b", r"\bbpmn\b", r"\bmermaid\b"],
    "announcements": [r"\bduyuru", r"\bannouncement", r"\bgenelge", r"\bcircular", r"\bbildiri", r"\bmemo\b",
                      r"\bnotice", r"\bbulten", r"\bbulletin", r"\bdegisiklik", r"\bchange ?log"],
    "service_contract": [r"\bsozlesme", r"\bcontract", r"\bservis", r"\bservices?\b", r"\bapi\b", r"\bendpoint",
                         r"\bentegrasyon", r"\bintegration", r"\bhizmet", r"\bopenapi", r"\bswagger",
                         r"\barayuz", r"\binterface", r"\bweb ?servis"],
    "test_customers": [r"\btest musteri", r"\bmusteri(ler|leri)?\b.{0,20}\btest", r"\btest\b.{0,20}\bmusteri",
                       r"\btest customers?", r"\bcustomers?\b", r"\bmusteriler", r"\bpersona", r"\btest veri",
                       r"\btest data", r"\bornek musteri", r"\bsample customers?"],
    "qa": [r"\bsss\b", r"\bfaq\b", r"\bq ?(&|and) ?a\b", r"\bsoru", r"\bcevap", r"\bquestions?\b", r"\bs ?& ?c\b",
           r"\bsik sorulan", r"\bsoru cevap", r"\bqa\b"],
    "example_conversation": [r"\bornek konusma", r"\bkonusma", r"\bdiyalog", r"\bdialog", r"\btranscript",
                             r"\bconversation", r"\bgorusme", r"\bcagri kayd", r"\b(example|sample) calls?\b",
                             r"\bornek cagri", r"\bornek diyalog", r"\bsenaryo", r"\bscenario"],
}
_KW_RE = {k: [re.compile(p) for p in v] for k, v in _KW.items()}
_PRIORITY = ["brief", "readme", "example_conversation", "test_customers", "service_contract", "qa", "flow",
             "announcements", "analysis", "other"]
_SPEAKER_RE = re.compile(r"^\W{0,4}([^\W\d_][^\n:：]{0,24}?)\W{0,4}\s*[:：]\s*\S", re.U)
_HTTP_RE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\b\s+`?/[\w{}/.-]+")
_QA_LINE_RE = re.compile(r"^\W{0,6}(s|c|q|a|soru|cevap|yanit|question|answer)\s*(?:\d{1,3}\s*)?[:.)\-]\s*\S", re.I)
_Q_MARK_RE = re.compile(r"#+|\*\*|\d+[.)]")


def _question_line(ln):
    """A line that is one question (optional '#', '**' or '1.' marker, 3-200 characters, ending in '?', optionally
    closed by '**'): a linear form of ^\\s*(#+|\\*\\*|\\d+[.)])?.{3,200}\\?\\s*(\\*\\*)?\\s*$."""
    t = ln.rstrip()
    if t.endswith("**"):
        t = t[:-2].rstrip()
    if not t.endswith("?") or "\n" in t:
        return False
    body = t[:-1]
    m = _Q_MARK_RE.match(body.lstrip())
    return len(body) >= 3 and len(body.lstrip()) - (m.end() if m else 0) <= 200
_CUST_HDR = re.compile(r"\b(musteri|customer|ad|adi|soyad|name|dogum|birth|dob|telefon|phone|tckn|kimlik|tc|id|no|"
                       r"numara|kart|card|bakiye|borc|balance|limit|iban|hesap|account)\b")


def _kw_scores(text):
    f = fold(text)
    return {k: sum(1 for rx in rxs if rx.search(f)) for k, rxs in _KW_RE.items()}


_QA_LABELS = {"s", "c", "q", "a", "soru", "cevap", "yanit", "question", "answer", "not", "note", "ornek", "example"}


def _speaker_score(text):
    """Dialogue shape: >= 2 speaker labels used >= 2 times each, covering a good share of the lines."""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if len(lines) < 4:
        return 0
    counts = {}
    hits = 0
    for ln in lines:
        m = _SPEAKER_RE.match(ln.strip())
        if m and len(m.group(1).split()) <= 3:
            lab = fold(m.group(1))
            counts[lab] = counts.get(lab, 0) + 1
            hits += 1
    talkers = [k for k, v in counts.items() if v >= 2 and k not in _QA_LABELS]
    if len(talkers) >= 2 and hits >= 4 and hits >= 0.4 * len(lines):
        top2 = sorted(counts.values(), reverse=True)[:2]
        return 3 if sum(top2) >= 0.5 * hits else 1
    return 0


def _content_scores(text, tables, is_openapi):
    sc = dict.fromkeys(KINDS, 0)
    if is_openapi:
        sc["service_contract"] += 6
    sc["example_conversation"] += _speaker_score(text)
    if len(_HTTP_RE.findall(text)) >= 1:
        sc["service_contract"] += 2 + min(2, len(_HTTP_RE.findall(text)) // 3)
    qa = sum(1 for ln in text.split("\n") if _QA_LINE_RE.match(ln.strip()))
    qs = sum(1 for ln in text.split("\n") if _question_line(ln))
    if qa >= 4 or (qs >= 4 and sc["example_conversation"] == 0):
        sc["qa"] += 2
    for t in tables:
        hdr = fold(" ".join(t.get("header") or []))
        if len(t.get("rows") or []) >= 2 and len(set(_CUST_HDR.findall(hdr))) >= 3:
            sc["test_customers"] += 2
            break
    if re.search(r"(?m)^\s*(```\s*mermaid|graph (td|lr|tb)|flowchart\b|sequenceDiagram)", text, re.I) or \
            text.startswith("## Diagram") or len(re.findall(r"(->|→|-->)", text)) >= 6:
        sc["flow"] += 2
    return sc


def _name_keys(rel):
    p = pathlib.PurePosixPath(rel)
    keys = {fold(p.name), fold(p.stem)} | {fold(x) for x in p.parts[:-1]}
    return {k for k in keys if len(k) >= 3}


def _mentions(fl, keys):
    return any(re.search(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", fl) for k in keys)


def _readme_hints(readme_text, rel, all_rels=None):
    """Lines of the README that mention this file (by name, stem or folder) and no other file of the case ->
    keyword scores (a line listing several files says nothing about any one of them)."""
    if not readme_text:
        return {}
    keys = _name_keys(rel)
    others = [_name_keys(r) - keys for r in (all_rels or []) if r != rel]
    total = {}
    for ln in readme_text.split("\n"):
        fl = fold(ln)
        if not fl or not _mentions(fl, keys) or any(o and _mentions(fl, o) for o in others):
            continue
        rest = fl
        for k in sorted(keys, key=len, reverse=True):   # the file's own name must not vote twice (whole words only)
            rest = re.sub(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])", " ", rest)
        for k, v in _kw_scores(rest).items():
            total[k] = total.get(k, 0) + v
    return total


def classify(rel, text, tables, is_openapi=False, readme_text="", all_rels=None):
    """-> (kind, why). README mentions weigh 3, the file name 3, folder names 2, content as scored."""
    p = pathlib.PurePosixPath(rel)
    stem = fold(p.stem)
    if re.match(r"^(brief|brif)\b", stem):
        return "brief", "file name"
    if re.match(r"^(read ?me|beni ?oku|oku ?beni)\b", stem):
        return "readme", "file name"
    score = dict.fromkeys(KINDS, 0)
    why = {k: [] for k in KINDS}
    for k, v in _kw_scores(stem).items():
        if v and k not in ("brief", "readme"):
            score[k] += 3 * v
            why[k].append("name")
    for part in p.parts[:-1]:
        for k, v in _kw_scores(part).items():
            if v and k not in ("brief", "readme"):
                score[k] += 2 * v
                why[k].append("folder")
    for k, v in _readme_hints(readme_text, rel, all_rels).items():
        if v and k not in ("brief", "readme"):
            score[k] += 3 * v
            why[k].append("readme")
    for k, v in _content_scores(text, tables, is_openapi).items():
        if v:
            score[k] += v
            why[k].append("content")
    if p.suffix.lower() in (".drawio", ".bpmn", _VSDX, ".mmd", ".mermaid", ".puml"):
        score["flow"] += 3
        why["flow"].append("type")
    best = max(score.values())
    if best <= 0:
        return "other", "no signal"
    kind = next(k for k in _PRIORITY if score.get(k) == best)
    return kind, "+".join(sorted(set(why[kind]))) + " (score %d)" % best


# ============================================================================================ load_case

_FIRST_RANK = {"brief": 0, "readme": 1}                 # load order: the brief, the README, the rest
_ORDER_LAST = ("test_customers", "example_conversation")


def load_case(path, mock_url=None):
    """Case folder / .zip / single file -> CaseDocs (see the module CONTRACT NOTE)."""
    src = pathlib.Path(path)
    if not src.exists():
        raise CaseError("case path not found: %s" % path)
    root = src
    if src.is_file() and src.suffix.lower() == ".zip":
        root = extract_zip(src)
    warnings, files, raw = [], [], []
    seen_zip = set()
    queue = list(list_files(root))
    base = root if root.is_dir() else root.parent
    while queue:
        f = queue.pop(0)
        rel = f.relative_to(base).as_posix() if f.is_relative_to(base) else f.name
        suf = f.suffix.lower()
        if suf == ".zip" and f != src and f not in seen_zip:      # a zip inside the folder: read its files too
            seen_zip.add(f)
            try:
                sub = extract_zip(f, tempfile.mkdtemp(prefix="freya-sub-"))
                inner = list_files(sub)
                for g in inner:
                    raw.append(("%s/%s" % (rel, g.relative_to(sub).as_posix()), g))
                files.append({"rel": rel, "kind": "archive", "reader": "zip", "bytes": f.stat().st_size,
                              "chars": 0, "status": "read", "note": "%d file(s) inside" % len(inner)})
            except (zipfile.BadZipFile, OSError) as e:
                warnings.append("%s: bad zip: %s" % (rel, e))
                files.append({"rel": rel, "kind": "archive", "reader": "skipped", "bytes": f.stat().st_size,
                              "chars": 0, "status": "skipped", "note": str(e)[:120]})
            continue
        raw.append((rel, f))
    readme_text = ""
    loaded = []
    for rel, f in raw:
        text, tables, reader, warns = read_document(f)
        nbytes = f.stat().st_size if f.exists() else 0
        for w in warns:
            warnings.append("%s: %s" % (rel, w))
        if reader == "skipped":
            files.append({"rel": rel, "kind": "skipped", "reader": reader, "bytes": nbytes, "chars": 0,
                          "status": "skipped", "note": "; ".join(warns)[:200]})
            continue
        if not tables and reader in ("text", "pdf", "textutil", "html"):
            tables = _md_tables(text)
        obj = _parse_data(text, f.suffix.lower()) if f.suffix.lower() in DATA_SUFFIXES else None
        doc = {"path": str(f), "rel": rel, "name": f.name, "kind": "other", "reader": reader, "text": text,
               "tables": tables, "bytes": nbytes, "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
               "is_openapi": is_openapi_doc(obj), "kind_why": "", "_obj": obj}
        loaded.append(doc)
        if re.match(r"^(readme|beni ?oku|oku ?beni)\b", fold(f.stem)) and not readme_text:
            readme_text = text
        if not text.strip():
            warnings.append("%s: no text could be read" % rel)
    for d in loaded:
        d["kind"], d["kind_why"] = classify(d["rel"], d["text"], d["tables"], d["is_openapi"], readme_text,
                                            [x["rel"] for x in loaded])
        files.append({"rel": d["rel"], "kind": d["kind"], "reader": d["reader"], "bytes": d["bytes"],
                      "chars": len(d["text"]), "status": "read" if d["text"].strip() else "empty",
                      "note": d["kind_why"]})

    def rank(d):
        top = d["rel"].count("/")
        k = d["kind"]
        first = _FIRST_RANK.get(k, 3 if k in _ORDER_LAST else 2)
        last = _ORDER_LAST.index(k) if k in _ORDER_LAST else 0
        return (first, top if first < 2 else 0, last, d["rel"].casefold())
    docs = sorted(loaded, key=rank)
    openapi, openapi_path = None, None
    for d in docs:
        obj = d.pop("_obj")
        if d["is_openapi"] and openapi is None:
            openapi, openapi_path = obj, d["path"]
    if not any(d["kind"] == "brief" for d in docs) and docs:
        warnings.append("no BRIEF document found (by name): reading every document as equal")
    customers_tables = [dict(t, doc=d["rel"]) for d in docs if d["kind"] == "test_customers" for t in d["tables"]]
    return {
        "root": str(root), "source": str(path),
        "mock_url": normalise_url(mock_url) if mock_url else None,
        "docs": docs, "openapi": openapi, "openapi_path": openapi_path,
        "contract_docs": [d for d in docs if d["kind"] == "service_contract"],
        "customers_tables": customers_tables,
        "examples": [d for d in docs if d["kind"] == "example_conversation"],
        "files": files, "warnings": warnings,
    }


def _md_tables(text):
    from builder.pipeline.segment import parse_tables
    out = []
    for t in parse_tables(text.split("\n")):
        out.append({"name": "", "header": t["header"], "rows": t["rows"]})
    return out


# ============================================================================================ tool API

def is_url(s):
    return bool(re.match(r"^https?://[^\s/]+", str(s or ""), re.I))


def normalise_url(url):
    return str(url).strip().rstrip("/")


def with_server(doc, url):
    out = json.loads(json.dumps(doc))
    out["servers"] = [{"url": normalise_url(url)}]
    out.pop("host", None)
    out.pop("basePath", None)
    out.pop("schemes", None)
    return out


USER_AGENT = "Mozilla/5.0 (compatible; freya-builder/1.0)"   # Cloudflare answers 403 / error 1010 to Python-urllib


def fetch_json(url, timeout=15):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 - our own mock URL from the CLI
        return json.loads(r.read().decode("utf-8", errors="replace"))


def tool_api_for(case, out_dir, fetch=None):
    """-> (path | None, source description). The OpenAPI of the case folder, else <mock>/openapi.json, written to
    out_dir/tool_api.json with servers = [mock_url] (when a mock URL is known)."""
    fetch = fetch or fetch_json
    mock = case.get("mock_url")
    doc, source = case.get("openapi"), case.get("openapi_path")
    if doc is None and mock:
        try:
            got = fetch(mock + "/openapi.json")
            if is_openapi_doc(got):
                doc, source = got, mock + "/openapi.json"
        except Exception as e:                            # noqa: BLE001 - unreachable mock: caller decides
            source = "fetch %s/openapi.json failed: %s" % (mock, str(e)[:160])
    if doc is None:
        return None, source or "no OpenAPI in the case folder"
    if mock:
        doc = with_server(doc, mock)
    out = pathlib.Path(out_dir) / "tool_api.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
    return str(out), source


def manifest_lines(case):
    """Human summary for the trace: one line per file."""
    return ["%-22s %-9s %8d B %7d ch  %s  %s" % (f["kind"], f["reader"], f["bytes"], f["chars"], f["rel"],
                                                  f.get("note") or "") for f in case.get("files") or []]
