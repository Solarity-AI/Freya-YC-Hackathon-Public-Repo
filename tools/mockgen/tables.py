"""Table readers for the test-customers document (standard library only).

read_tables(path) -> [Table]: every table found in a .csv/.tsv/.json/.md/.txt/.xlsx/.docx file, or in every such file
under a directory. A Table is {"source": str, "name": str, "header": [str], "rows": [{header: str}]} with every cell a
string (an Excel date cell becomes YYYY-MM-DD, an integral Excel number loses its ".0"). PDFs are read through the
`pdftotext` CLI when it is installed (tables as whitespace columns are not parsed: a PDF yields no table).
JSON: a list of flat objects is one table; a list of objects with nested `identity`/`products` is returned as
{"shaped": [...]} instead (see make_config.load_customers).
"""
from __future__ import annotations

import csv
import datetime
import io
import json
import pathlib
import re
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
TABLE_EXT = {".csv", ".tsv", ".json", ".md", ".markdown", ".txt", ".xlsx", ".xlsm", ".docx"}
# built-in Excel number formats that are dates
_DATE_FMT_IDS = set(range(14, 23)) | {27, 30, 36, 45, 46, 47, 50, 57}


def _table(source, name, header, rows):
    rows = [list(r) for r in rows]
    width = max([len(header)] + [len(r) for r in rows if any(str(c or "").strip() for c in r)])
    header = [str(h or "").strip() for h in header] + [""] * (width - len(header))
    # blank or duplicate header cells get a positional name
    seen = {}
    for i, h in enumerate(header):
        if not h:
            h = "col%d" % (i + 1)
        if h in seen:
            seen[h] += 1
            h = "%s_%d" % (h, seen[h])
        else:
            seen[h] = 1
        header[i] = h
    out = []
    for r in rows:
        cells = [("" if c is None else str(c)).strip() for c in r]
        if not any(cells):
            continue
        cells += [""] * (len(header) - len(cells))
        out.append({h: cells[i] for i, h in enumerate(header)})
    return {"source": str(source), "name": name, "header": header, "rows": out}


# ---------------------------------------------------------------------------------------------------- csv / md

def _csv_tables(path, text, delim=None):
    if delim is None:
        sample = text[:4096]
        delim = max([",", ";", "\t", "|"], key=lambda d: sample.count(d))
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2:
        return []
    return [_table(path, pathlib.Path(path).stem, rows[0], rows[1:])]


_MD_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def md_tables(text, source="<text>"):
    """Pipe tables in Markdown text -> [Table]. The heading above a table names it."""
    lines = text.splitlines()
    out, i, heading = [], 0, ""
    while i < len(lines):
        ln = lines[i]
        if re.match(r"^\s*#+\s", ln):
            heading = re.sub(r"^\s*#+\s*", "", ln).strip()
        if "|" in ln and i + 1 < len(lines) and _MD_SEP.match(lines[i + 1]):
            header = _md_cells(ln)
            rows = []
            j = i + 2
            while j < len(lines) and "|" in lines[j] and lines[j].strip():
                rows.append(_md_cells(lines[j]))
                j += 1
            out.append(_table(source, heading or "table%d" % (len(out) + 1), header, rows))
            i = j
            continue
        i += 1
    return out


def _md_cells(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    cells = re.split(r"(?<!\\)\|", s)
    return [re.sub(r"^`(.*)`$", r"\1", c.strip().replace("\\|", "|")).replace("**", "").strip() for c in cells]


# ---------------------------------------------------------------------------------------------------- xlsx

def _col_index(ref):
    letters = re.match(r"^([A-Z]+)", ref or "")
    if not letters:
        return None
    n = 0
    for ch in letters.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _excel_date(serial, epoch1904=False):
    base = datetime.date(1904, 1, 1) if epoch1904 else datetime.date(1899, 12, 30)
    return (base + datetime.timedelta(days=int(float(serial)))).isoformat()


def _num_text(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    if f.is_integer() and abs(f) < 1e15:
        return str(int(f))
    return repr(round(f, 10)).rstrip("0").rstrip(".") if "e" not in repr(f) else v


def xlsx_tables(path):
    out = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(S + "si"):
                shared.append("".join(t.text or "" for t in si.iter(S + "t")))
        date_styles = set()
        if "xl/styles.xml" in names:
            st = ET.fromstring(z.read("xl/styles.xml"))
            custom = {}
            nf = st.find(S + "numFmts")
            if nf is not None:
                for f in nf.findall(S + "numFmt"):
                    code = (f.get("formatCode") or "").lower()
                    code = re.sub(r"\[[^\]]*\]|\"[^\"]*\"", "", code)
                    custom[int(f.get("numFmtId"))] = bool(re.search(r"[dy]", code)) and "h" not in code[:1]
            xfs = st.find(S + "cellXfs")
            if xfs is not None:
                for i, xf in enumerate(xfs.findall(S + "xf")):
                    fid = int(xf.get("numFmtId") or 0)
                    if fid in _DATE_FMT_IDS or custom.get(fid):
                        date_styles.add(i)
        epoch1904 = False
        sheets = []
        if "xl/workbook.xml" in names:
            wb = ET.fromstring(z.read("xl/workbook.xml"))
            pr = wb.find(S + "workbookPr")
            epoch1904 = pr is not None and pr.get("date1904") in ("1", "true")
            rels = {}
            if "xl/_rels/workbook.xml.rels" in names:
                for rel in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")):
                    tgt = rel.get("Target") or ""
                    tgt = tgt.lstrip("/")
                    rels[rel.get("Id")] = tgt if tgt.startswith("xl/") else "xl/" + tgt
            for i, sh in enumerate(wb.iter(S + "sheet")):
                target = rels.get(sh.get(R_NS + "id")) or "xl/worksheets/sheet%d.xml" % (i + 1)
                sheets.append((sh.get("name") or target, target))
        if not sheets:
            sheets = [(n, n) for n in sorted(x for x in names if re.match(r"xl/worksheets/sheet\d+\.xml$", x))]
        for sname, target in sheets:
            if target not in names:
                continue
            grid = []
            prev_r = 0
            for row in ET.fromstring(z.read(target)).iter(S + "row"):
                rnum = int(row.get("r") or prev_r + 1)
                if rnum > prev_r + 1 and grid:
                    grid.append([])                         # skipped rows are blank rows (they split tables)
                prev_r = rnum
                vals = {}
                pos = 0
                for c in row.findall(S + "c"):
                    idx = _col_index(c.get("r"))
                    idx = pos if idx is None else idx
                    pos = idx + 1
                    t = c.get("t")
                    v = c.find(S + "v")
                    if t == "s" and v is not None:
                        val = shared[int(v.text)]
                    elif t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter(S + "t"))
                    elif t == "b" and v is not None:
                        val = "true" if v.text == "1" else "false"
                    elif v is not None and v.text is not None:
                        style = int(c.get("s") or 0)
                        if t in (None, "n") and style in date_styles:
                            try:
                                val = _excel_date(v.text, epoch1904)
                            except (ValueError, OverflowError):
                                val = v.text
                        elif t in (None, "n"):
                            val = _num_text(v.text)
                        else:
                            val = v.text
                    else:
                        val = ""
                    vals[idx] = val
                if vals:
                    width = max(vals) + 1
                    grid.append([vals.get(i, "") for i in range(width)])
                else:
                    grid.append([])
            out += _grid_tables(path, sname, grid)
    return out


def _grid_tables(path, name, grid):
    """A sheet may hold a title row or several tables separated by blank rows: split on blank rows and use the first
    row with at least two non-empty cells as each block's header."""
    blocks, cur = [], []
    for r in grid:
        if any(str(c).strip() for c in r):
            cur.append(r)
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    out = []
    for b in blocks:
        start = next((i for i, r in enumerate(b) if sum(1 for c in r if str(c).strip()) >= 2), None)
        if start is None or start + 1 >= len(b):
            continue
        out.append(_table(path, name, b[start], b[start + 1:]))
    return out


# ---------------------------------------------------------------------------------------------------- docx

def docx_tables(path):
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    out = []
    heading = ""

    def para(p):
        return "".join(t.text or "" for t in p.iter(W + "t")).strip()

    def walk(el):
        nonlocal heading
        for ch in list(el):
            if ch.tag == W + "p":
                t = para(ch)
                if t:
                    heading = t
            elif ch.tag == W + "tbl":
                rows = []
                for tr in ch.findall(W + "tr"):
                    rows.append([" ".join(para(p) for p in tc.iter(W + "p")).strip() for tc in tr.findall(W + "tc")])
                rows = [r for r in rows if any(c for c in r)]
                if len(rows) >= 2:
                    out.append(_table(path, heading or "table%d" % (len(out) + 1), rows[0], rows[1:]))
            else:
                walk(ch)

    body = root.find(W + "body")
    if body is not None:
        walk(body)
    return out


# ---------------------------------------------------------------------------------------------------- json

def json_tables(path, text):
    try:
        data = json.loads(text)
    except ValueError:
        return []
    if isinstance(data, dict):
        for k in ("customers", "test_customers", "musteriler", "data", "items", "rows"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
    if not isinstance(data, list) or not data or not all(isinstance(x, dict) for x in data):
        return []
    if any(isinstance(x.get("identity"), dict) or isinstance(x.get("products"), list) for x in data):
        return [{"source": str(path), "name": pathlib.Path(path).stem, "shaped": data}]
    header = []
    for x in data:
        for k in x:
            if k not in header and not isinstance(x[k], (dict, list)):
                header.append(k)
    rows = [[_cell(x.get(h)) for h in header] for x in data]
    return [_table(path, pathlib.Path(path).stem, header, rows)]


def _cell(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


# ---------------------------------------------------------------------------------------------------- entry

def read_tables(path):
    p = pathlib.Path(path)
    if p.is_dir():
        out = []
        for f in sorted(p.rglob("*")):
            if f.is_file() and f.suffix.lower() in TABLE_EXT and not f.name.startswith((".", "~$")):
                try:
                    out += read_tables(f)
                except Exception as e:                      # noqa: BLE001 - one bad file never stops the scan
                    out.append({"source": str(f), "name": f.name, "error": str(e), "header": [], "rows": []})
        return out
    ext = p.suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        return xlsx_tables(p)
    if ext == ".docx":
        return docx_tables(p)
    text = p.read_bytes().decode("utf-8-sig", errors="replace")
    if ext == ".json":
        return json_tables(p, text)
    if ext == ".csv":
        return _csv_tables(p, text)
    if ext == ".tsv":
        return _csv_tables(p, text, "\t")
    return md_tables(text, str(p))
