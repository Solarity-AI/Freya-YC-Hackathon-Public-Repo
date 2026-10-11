"""Brief files -> BriefDoc (docs/CONTRACTS.md F). Owner: agent 5. Pure code, tolerant Markdown table parsing.

BriefDoc = {"docs": [doc...], "numbered": "<path>:<n>| <line>\\n...", "lexicon": {...}, "text": all docs joined}
doc      = {"path", "sha256", "text", "lines", "sections": [{"title","level","line_start","line_end"}],
            "tables": [{"line", "header", "rows"}], "kind", "lexicon"}

Multiple files are layers in the given order (a later file amends an earlier one). A single file may itself hold several
documents (raw material: mail + policy extract + memo + code list); sections are found from Markdown headings, e-mail
header blocks (From:/Subject:/Date:), "MEMO"/"MEMORANDUM" lines and underlined (=== / ---) headings.
Nothing here raises on odd input: unreadable bytes are replaced, malformed tables are padded.
"""
import hashlib
import pathlib
import re

_HEADING_RE = re.compile(r"\s{0,3}(#{1,6})\s+")  # the title after it is cut by _heading (no backtracking)
_MAIL_HDR_RE = re.compile(r"^\s*(from|to|cc|subject|date|sent|re)\s*:\s*\S", re.I)
_MEMO_RE = re.compile(r"^\s*(internal\s+)?(memo|memorandum|circular|notice|policy extract|code list|appendix)\b.*$",
                      re.I)
_UNDERLINE_RE = re.compile(r"^\s*(=){3,}\s*$|^\s*(-){3,}\s*$")
_SEP_CELL_RE = re.compile(r"^\s*:?-+:?\s*$")

# lexicon patterns (raw tokens as written; derivability checks use them)
_ISO_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
# Times, numbers and ranges: each was one alternation Sonar rated too complex. _first_alt scans them with the same
# result as findall over "part1|part2|...": at every start the first part that matches wins.
_TIME_RE = (re.compile(r"\b\d"), (
    re.compile(r"\b(?:[01]?\d|2[0-3])[:.][0-5]\d\b(?:\s*[ap]\.?m\.?)?", re.I),
    re.compile(r"\b(?:1[0-2]|[1-9])\s*[ap]\.?m\.?\b", re.I)))
_NUM_RE = (re.compile(r"(?<![\w.])\d"), (
    re.compile(r"(?<![\w.])\d{1,3}(?:[,.]\d{3})*(?:[.,]\d+)?(?!\w)"),
    re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?!\w)")))
_BACKTICK_RE = re.compile(r"`([^`\n]+)`")
_QUOTE_RE = re.compile(r"\"([^\"\n]{1,200})\"|“([^”\n]{1,200})”")
_RANGE_RE = (re.compile(r"\b\d|[≤≥<>]"), (
    re.compile(r"\b\d+\s*(?:-|–|—|to)\s*\d+\b"),
    re.compile(r"\b\d+\+"),
    re.compile(r"[≤≥<>]=?\s*\d+")))
_ORD_RE = re.compile(r"\b\d+(?:st|nd|rd|th)\b", re.I)
_NUM_WORDS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
              "sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred "
              "thousand first second third fourth fifth sixth seventh eighth ninth tenth twelfth half quarter "
              "once twice").split()
_NUMWORD_RE = re.compile(r"\b(" + "|".join(_NUM_WORDS) + r")\b", re.I)


def _read(path):
    p = pathlib.Path(path)
    data = p.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("﻿", "")
    return data, text


def split_row(line):
    """One table row -> cells. Handles '>' quote prefixes, missing outer pipes and escaped pipes (\\|)."""
    s = line.strip()
    while s.startswith(">"):
        s = s[1:].strip()
    s = s.replace("\\|", "\x00")
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip().replace("\x00", "|") for c in s.split("|")]


def _is_table_line(line):
    s = line.strip()
    while s.startswith(">"):
        s = s[1:].strip()
    if s.count("|") - s.count("\\|") < 1:
        return False
    return s.startswith("|") or s.count("|") - s.count("\\|") >= 2


def _has_pipe(line):
    return line.count("|") - line.count("\\|") >= 1


def _is_sep_row(cells):
    cells = [c for c in cells if c != ""]
    return bool(cells) and all(_SEP_CELL_RE.match(c) for c in cells)


def parse_tables(lines):
    """Markdown pipe tables -> [{"line": first line no (1-based), "header": [...], "rows": [[...]]}].
    Tolerant: rows without outer pipes, '>' prefixes, escaped pipes, short rows padded, long rows kept,
    a table without a separator row is accepted when it has >= 2 rows. Footnote lines directly under a table
    (starting with '*', '†' or '[n]') are attached as "notes"."""
    tables, i, n = [], 0, len(lines)
    while i < n:
        if not _is_table_line(lines[i]):
            i += 1
            continue
        start = i
        block = []
        while i < n and (_is_table_line(lines[i]) or (block and _has_pipe(lines[i]))):
            block.append(split_row(lines[i]))
            i += 1
        if len(block) >= 2 and _is_sep_row(block[1]):
            header, body = block[0], block[2:]
        elif len(block) >= 2:
            header, body = block[0], block[1:]
        else:
            continue                                    # a single pipe line is prose, not a table
        body = [r for r in body if not _is_sep_row(r)]
        w = len(header)
        rows = [r + [""] * (w - len(r)) if len(r) < w else r for r in body]
        t = {"line": start + 1, "header": header, "rows": rows}
        notes = []
        j = i
        while j < n and re.match(r"^\s*(\*+|†|\[\d+\]|note[s]?:)", lines[j], re.I):
            notes.append(lines[j].strip())
            j += 1
        if notes:
            t["notes"] = notes
        tables.append(t)
    return tables


def _heading(line):
    """(level, title) of a Markdown ATX heading line, else None. Same result as the regex
    ^\\s{0,3}(#{1,6})\\s+(.*?)\\s*#*\\s*$ : the title loses its trailing whitespace, closing #s and whitespace
    before them, and a title with a line break inside is not a heading."""
    m = _HEADING_RE.match(line)
    if not m:
        return None
    title = line[m.end():].rstrip().rstrip("#").rstrip()
    if "\n" in title:
        return None
    return (len(m.group(1)), title)


def parse_sections(lines):
    """Headings (Markdown, underlined, mail header blocks, memo lines) -> sections with 1-based inclusive ranges."""
    heads = []
    in_mail_hdr = False
    for idx, line in enumerate(lines):
        hd = _heading(line)
        if hd:
            heads.append((idx, hd[0], hd[1].strip()))
            in_mail_hdr = False
            continue
        if idx + 1 < len(lines) and line.strip() and not _is_table_line(line) and _UNDERLINE_RE.match(lines[idx + 1]) \
                and not _UNDERLINE_RE.match(line):
            lvl = 1 if lines[idx + 1].strip().startswith("=") else 2
            heads.append((idx, lvl, line.strip()))
            continue
        if _MAIL_HDR_RE.match(line):
            if not in_mail_hdr:
                heads.append((idx, 1, "mail: " + line.strip()[:80]))
                in_mail_hdr = True
            continue
        in_mail_hdr = False
        if _MEMO_RE.match(line) and len(line.strip()) <= 100:
            heads.append((idx, 1, line.strip()))
    sections = []
    for k, (idx, lvl, title) in enumerate(heads):
        end = len(lines) - 1
        for idx2, lvl2, _ in heads[k + 1:]:
            if lvl2 <= lvl:
                end = idx2 - 1
                break
        sections.append({"title": title, "level": lvl, "line_start": idx + 1, "line_end": max(idx + 1, end + 1)})
    if not sections and lines:
        sections.append({"title": "(document)", "level": 1, "line_start": 1, "line_end": len(lines)})
    return sections


def _uniq(seq):
    seen, out = set(), []
    for x in seq:
        x = x.strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _first_alt(spec, text):
    """re.findall(part1|part2|..., text) for group-less parts. spec = (start, parts): `start` finds every position
    where some part can begin; there the first matching part wins and the scan resumes after it."""
    start, parts = spec
    out, pos = [], 0
    while True:
        c = start.search(text, pos)
        if not c:
            return out
        p = c.start()
        m = next((m for m in (rx.match(text, p) for rx in parts) if m), None)
        if m:
            out.append(m.group(0))
            pos = m.end()
        else:
            pos = p + 1


def build_lexicon(text):
    """Tokens a value can be derived from: ISO dates, times, numbers, ranges, ordinals, number words,
    backticked tokens and quoted phrases (as written)."""
    quoted = [a or b for a, b in _QUOTE_RE.findall(text)]
    return {
        "iso_dates": _uniq(_ISO_RE.findall(text)),
        "times": _uniq(_first_alt(_TIME_RE, text)),
        "numbers": _uniq(_first_alt(_NUM_RE, _ISO_RE.sub(" ", text))),
        "ranges": _uniq(_first_alt(_RANGE_RE, text)),
        "ordinals": _uniq(_ORD_RE.findall(text)),
        "number_words": _uniq(w.lower() for w in _NUMWORD_RE.findall(text)),
        "backticked": _uniq(_BACKTICK_RE.findall(text)),
        "quoted": _uniq(quoted),
    }


def example_values(tables):
    """Values from 'Example' columns of the brief's tables (BRF-71: they must never become Spec constants).
    Backticked parts of a cell, else the cell split on ',' / ' or '; trailing '...' dropped; >= 3 chars."""
    out = []
    for t in tables or []:
        cols = [i for i, h in enumerate(t.get("header") or []) if re.search(r"\bexamples?\b", h, re.I)]
        for row in t.get("rows") or []:
            for i in cols:
                if i >= len(row):
                    continue
                cell = row[i]
                parts = _BACKTICK_RE.findall(cell) or re.split(r",|\bor\b", cell)
                for p in parts:
                    p = p.strip().strip("`'\"").rstrip(".").rstrip("\u2026").strip()
                    if len(p) >= 3 and p not in out:
                        out.append(p)
    return out


def guess_kind(text, sections):
    """Coarse document kind for logging/prompts: brief | mail | memo | policy | code_list | mixed."""
    low = text.lower()
    kinds = set()
    if any(s["title"].startswith("mail: ") for s in sections):
        kinds.add("mail")
    if re.search(r"^\s*(internal\s+)?(memo|memorandum)\b", low, re.M):
        kinds.add("memo")
    if re.search(r"\bcode list\b|^\s*\|\s*code\s*\|", low, re.M):
        kinds.add("code_list")
    if re.search(r"\bpolicy\b", low) and ("mail" in kinds or "memo" in kinds):
        kinds.add("policy")
    if not kinds:
        return "brief"
    return kinds.pop() if len(kinds) == 1 else "mixed"


def segment_text(path, text, data=None):
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    data = data if data is not None else text.encode("utf-8")
    sections = parse_sections(lines)
    return {
        "path": str(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "text": text,
        "lines": lines,
        "sections": sections,
        "tables": parse_tables(lines),
        "kind": guess_kind(text, sections),
        "lexicon": build_lexicon(text),
    }


_TEXT_SUFFIXES = (".md", ".txt", ".eml", ".csv", ".markdown", "")
_DATA_SUFFIXES = (".json", ".yaml", ".yml", ".tsv")


def _is_api_file(f):
    from builder import openapi_model
    return bool(openapi_model.is_openapi_file(str(f)))  # never raises


def _rich_suffixes():
    """Office/PDF/drawing types read through builder.ingest (case folders of the final: Word, Excel, PDF, ...)."""
    from builder import ingest
    return ingest.READABLE_SUFFIXES - set(_TEXT_SUFFIXES) - set(_DATA_SUFFIXES)


def expand_paths(paths, with_origin=False):
    """Directories expand to their readable files (text, data, Word/Excel/PDF/drawings; sorted; an OpenAPI file inside
    is the tool API, not a brief); other paths pass through. with_origin -> [(path, from_dir)]."""
    out = []
    for p in paths:
        pp = pathlib.Path(p)
        if pp.is_dir():
            out += [(str(f), True) for f in sorted(pp.rglob("*")) if _brief_file(f)]
        else:
            out.append((str(p), False))
    return out if with_origin else [x[0] for x in out]


def _brief_file(f):
    """A file of a raw-material folder that is brief input (readable, and not the tool API)."""
    if not f.is_file() or f.name.startswith((".", "~$")) or "__MACOSX" in f.parts:
        return False
    suf = f.suffix.lower()
    return suf in _TEXT_SUFFIXES or suf in _rich_suffixes() or (suf in _DATA_SUFFIXES and not _is_api_file(f))


def _read_any(p):
    """(bytes, text) of one input file; Word/Excel/PDF/... are converted to Markdown-ish text by builder.ingest."""
    if pathlib.Path(p).suffix.lower() in _rich_suffixes():
        from builder import ingest
        text = ingest.read_document(p)[0]
        return pathlib.Path(p).read_bytes(), text
    return _read(p)


# what a document of each case-folder role is for (shown in its header so extraction weighs it right)
ROLE_NOTES = {
    "brief": "the brief: read first",
    "readme": "says what each document is",
    "test_customers": "TEST DATA: shows field formats and value shapes; its values are not rules or constants",
    "example_conversation": "EXAMPLE CONVERSATION: wording and flow; the documents' rules win over it",
    "service_contract": "the bank services the agent calls",
}


def _name_tag(name):
    return re.sub(r"\s+", "_", name)


def _bdoc(docs, headers):
    numbered = []
    for li, d in enumerate(docs):
        if headers[li]:
            numbered.append(headers[li])
        name = _name_tag(pathlib.Path(d["path"]).name)
        for n, line in enumerate(d["lines"], 1):
            numbered.append("%s:%d| %s" % (name, n, line))
    lex = {}
    for d in docs:
        for k, v in d["lexicon"].items():
            lex.setdefault(k, [])
            lex[k] = _uniq(lex[k] + v)
    examples = []
    for d in docs:
        examples += [x for x in example_values(d["tables"]) if x not in examples]
    return {"docs": docs, "numbered": "\n".join(numbered) + "\n", "lexicon": lex, "examples": examples,
            "text": "\n\n".join(d["text"] for d in docs)}


def segment(paths):
    """-> {"docs": [{"path", "sha256", "text", "lines", "sections": [{"title", "level", "line_start", "line_end"}],
    "tables": [{"line", "header", "rows"}]}], "numbered": "<path>:<n>| <line>\\n..."}. Multiple files = layers in order.
    A folder is read through builder.ingest (every format; BRIEF first, README second); see from_case."""
    if len(paths) == 1 and pathlib.Path(paths[0]).is_dir():
        from builder import ingest
        return from_case(ingest.load_case(paths[0]))
    docs, from_dir = [], []
    for p, in_dir in expand_paths(paths, with_origin=True):
        data, text = _read_any(p)
        docs.append(segment_text(p, text, data))
        from_dir.append(in_dir)
    headers = []
    for li, d in enumerate(docs):
        name = pathlib.Path(d["path"]).name
        if len(docs) > 1 and from_dir[li]:
            # files of a folder are ordered by name only: precedence comes from their content, not their order
            headers.append("=== DOCUMENT %d of %d: %s (kind: %s; from a folder, order means nothing) ===" % (
                li + 1, len(docs), name, d["kind"]))
        elif len(docs) > 1:
            headers.append("=== LAYER %d of %d: %s (kind: %s; later layers amend earlier ones) ===" % (
                li + 1, len(docs), name, d["kind"]))
        else:
            headers.append("")
    return _bdoc(docs, headers)


def from_case(case):
    """builder.ingest CaseDocs -> BriefDoc. Every document except the OpenAPI file (the tool catalog covers it) and
    empty ones, in the case order; each doc also carries "role" (ingest kind) and "rel" (path in the folder).
    bdoc["examples"] additionally holds the test customers' cell values (they must never become Spec constants), and
    bdoc["case"] = {"root", "roles": {rel: role}, "mock_url"}."""
    docs, headers = [], []
    picked = [d for d in case.get("docs") or [] if not d.get("is_openapi") and (d.get("text") or "").strip()]
    for li, cd in enumerate(picked):
        d = segment_text(cd["path"], cd["text"], pathlib.Path(cd["path"]).read_bytes()
                         if pathlib.Path(cd["path"]).is_file() else None)
        d["sha256"] = cd.get("sha256") or d["sha256"]
        d["role"], d["rel"] = cd.get("kind", "other"), cd.get("rel") or pathlib.Path(cd["path"]).name
        docs.append(d)
        note = ROLE_NOTES.get(d["role"], "")
        headers.append("=== DOCUMENT %d of %d: %s (role: %s%s; kind: %s; from a case folder) ===" % (
            li + 1, len(picked), d["rel"], d["role"], ("; " + note) if note else "", d["kind"]))
    out = _bdoc(docs, headers if len(docs) > 1 or any(d["role"] != "brief" for d in docs) else [""] * len(docs))
    for t in case.get("customers_tables") or []:
        for row in t.get("rows") or []:
            for c in row:
                c = str(c).strip()
                if len(c) >= 3 and c not in out["examples"]:
                    out["examples"].append(c)
    out["case"] = {"root": case.get("root"), "mock_url": case.get("mock_url"),
                   "roles": {d["rel"]: d["role"] for d in docs}}
    return out


# --------------------------------------------------------------------------------------------- quotes

_NUMPREFIX_RE = re.compile(r"^\s*[^\s|]+:\d+\|\s?")


def norm_quote_text(s):
    """Normalisation for quote checks: unify quotes/dashes, drop markdown emphasis/backticks/table pipes,
    collapse whitespace, casefold."""
    s = str(s)
    s = "\n".join(_NUMPREFIX_RE.sub("", ln) for ln in s.split("\n"))
    for a, b in (("‘", "'"), ("’", "'"), ("“", '"'), ("”", '"'), ("–", "-"),
                 ("—", "-"), (" ", " "), ("…", "...")):
        s = s.replace(a, b)
    s = re.sub(r"[`*]", "", s)
    s = s.replace("|", " ")
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r" ([?.,;:!)])", r"\1", s)
    return s.strip().casefold()


def quote_in(quote, haystack_norm):
    """True if every '...'-separated part of `quote` (>= 1 non-trivial part) occurs in the normalised haystack."""
    q = norm_quote_text(quote)
    if not q:
        return False
    parts = [p.strip(" .,;:\"'") for p in re.split(r"\.\.\.|\[\.\.\.\]", q)]
    parts = [p for p in parts if len(p) >= 2]
    if not parts:
        return False
    return all(p in haystack_norm for p in parts)
