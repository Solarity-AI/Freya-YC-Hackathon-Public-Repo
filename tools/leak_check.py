#!/usr/bin/env python3
"""Did anything from a hidden brief get written into the builder?  (Rule: after the hidden briefs open, only generic
fixes may go into the builder; a reviewer agent reads the commit.)

    python3 tools/leak_check.py --hidden briefs/hidden-1.md briefs/hidden-1.openapi.json ... --since pre-hidden
                                [--worktree] [--paths builder runtime harness prompts] [--quiet]

1. Lists the distinctive tokens of the hidden files: numbers (2+ digits, amounts with or without thousands commas),
   dates (ISO, 'March 14', '14 March', '3/14/2026'), quoted strings ("...", '...', `...`, curly quotes), proper
   nouns (capitalised words and runs of them), uncommon lower-case words (5+ letters), codes (ABC-123, ALL_CAPS, snake_case, camelCase), the OpenAPI's enum
   values, operationIds, paths and path segments, schema and property names, examples/defaults and server URLs, and
   every 6-word phrase (copied sentences).
2. Drops generic ones: common English words, and anything already present at <ref> in the builder's code, the public
   kit or the tests (--allow-from): such a token was known before the hidden briefs and is no evidence of a leak.
3. Scans the lines ADDED by `git diff <ref>..HEAD -- <paths>` (with --worktree: <ref> against the working tree, plus
   untracked files) and prints every hit as file:line [kind] token.
Exit 0 clean, 1 hits (review each one: a generic word can still collide), 2 usage or git error.
Known blind spot: a token the builder already contained at <ref> (e.g. a common number like 30) is never reported.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_PATHS = ("builder", "runtime", "harness", "prompts")
DEFAULT_ALLOW_FROM = ("builder", "runtime", "harness", "kit", "tests")
SHINGLE = 6
MAX_BLOB = 3_000_000

COMMON = set("""
a about above account accounts after again against all also always am an and any are as ask asked asks at available
back bank be because been before being below between both but by call called caller calls can cannot case cases
check close code customer customers date day days did do does done down during each else end every example
fee few first for from full further get give given goes had has have he her here him his how i if in into is it its
just last later less like line lines long make may me more most must my need never new next no not note now number
of off on once one only or other our out over own pay paid payment payments per phone please promise read record
reply request same say says see she should since so some still such than that the their them then there these they
this those through time to today too true false null none under until up us use used very was we were what when
where which while who why will with within without would yes you your monday tuesday wednesday thursday friday
saturday sunday january february march april may june july august september october november december string
integer boolean object array required type properties description summary example default enum format items schema
post get put patch delete status error success result results data message id name value values true false
""".split())
MONTHS = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|" \
         r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_EXTRACTORS = (
    ("date", re.compile(r"\b\d{4}-\d{2}-\d{2}\b")),
    ("date", re.compile(r"\b%s\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\b" % MONTHS)),
    ("date", re.compile(r"\b\d{1,2}(?:st|nd|rd|th)?\s+%s\b(?:,?\s+\d{4})?" % MONTHS)),
    ("date", re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b")),
    ("quote", re.compile(r'"([^"\n]{3,80})"')),
    ("quote", re.compile("“([^”\n]{3,80})”")),
    ("quote", re.compile(r"(?<![A-Za-z])'([^'\n]{3,60})'(?![A-Za-z])")),
    ("quote", re.compile(r"`([^`\n]{2,80})`")),
    ("code", re.compile(r"\b[A-Z]{2,}[-_]?\d+[A-Z0-9-]*\b")),
    ("code", re.compile(r"\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b|\b[A-Z]{3,}\b")),
    ("code", re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")),
    ("code", re.compile(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b")),
    ("name", re.compile(r"\b[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)+\b")),
    ("name", re.compile(r"\b[A-Z][a-z]{2,}\b")),
    ("word", re.compile(r"\b[a-z]{5,}\b")),
)
_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?(?![\w])")
_WORD = re.compile(r"[a-z0-9]+")


class LeakCheckError(Exception):
    pass


# ----------------------------------------------------------------------------------------------- tokens

def _norm_words(text):
    return _WORD.findall(text.lower())


def shingles(text):
    w = _norm_words(text)
    return {" ".join(w[i:i + SHINGLE]) for i in range(len(w) - SHINGLE + 1)}


def _add(out, kind, tok):
    tok = str(tok).strip()
    if tok and tok not in out:
        out[tok] = kind


def prose_tokens(text, out=None):
    """{token: kind} from free text (a brief, or an OpenAPI description)."""
    out = {} if out is None else out
    for kind, rx in _EXTRACTORS:
        for m in rx.finditer(text):
            _add(out, kind, m.group(1) if rx.groups else m.group(0))
    for m in _NUMBER.finditer(text):
        raw = m.group(0).rstrip(",")
        plain = raw.replace(",", "")
        if len(re.sub(r"\D", "", plain.split(".")[0])) >= 2 or "." in plain:
            _add(out, "number", raw)
            _add(out, "number", plain)
    for line in text.splitlines():
        for s in shingles(line):
            _add(out, "phrase", s)
    return out


def _walk(node, out, parent=""):
    if isinstance(node, dict):
        for k, v in node.items():
            if parent in ("properties", "schemas", "parameters", "responses") and isinstance(k, str):
                _add(out, "field", k)
            if k == "enum" and isinstance(v, list):
                for e in v:
                    _add(out, "enum", e)
            elif k in ("operationId", "url") and isinstance(v, str):
                _add(out, "code" if k == "operationId" else "url", v)
            elif k in ("example", "default", "const") and isinstance(v, (str, int, float)) and not isinstance(v, bool):
                _add(out, "example", v)
            elif k == "name" and isinstance(v, str) and parent == "":
                _add(out, "field", v)
            _walk(v, out, k)
    elif isinstance(node, list):
        for v in node:
            _walk(v, out, parent)
    elif isinstance(node, str):
        prose_tokens(node, out)


def openapi_tokens(doc, out=None):
    """{token: kind} from a parsed OpenAPI document (structure + every string in it)."""
    out = {} if out is None else out
    for path in (doc.get("paths") or {}) if isinstance(doc, dict) else ():
        _add(out, "path", path)
        for seg in str(path).strip("/").split("/"):
            if seg and not seg.startswith("{"):
                _add(out, "path", seg)
    _walk(doc, out)
    return out


def _parse_structured(text):
    try:
        return json.loads(text)
    except ValueError:
        pass
    try:
        import yaml
        return yaml.safe_load(text)
    except Exception:                                   # noqa: BLE001 - not YAML either: treat as prose
        return None


def _expand(files):
    """Files as given; a folder (the final's case folder) or a .zip -> every file in it."""
    out = []
    for f in files:
        p = pathlib.Path(f)
        if p.is_dir() or p.suffix.lower() == ".zip":
            if str(ROOT) not in sys.path:
                sys.path.insert(0, str(ROOT))
            from builder import ingest
            out += ingest.list_files(ingest.extract_zip(p) if p.is_file() else p)
        else:
            out.append(p)
    return out


def _text_of(path):
    """Plain text of a hidden file: Word / Excel / PDF / drawings through builder.ingest, the rest as text."""
    p = pathlib.Path(path)
    if p.suffix.lower() in (".json", ".yaml", ".yml", ".md", ".txt", ".csv", ""):
        return p.read_text(errors="replace")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from builder import ingest
    text = ingest.read_document(p)[0]
    return text or p.read_text(errors="replace")


def hidden_tokens(files):
    """{token: (kind, source file)} for every hidden file (an OpenAPI is recognised by its 'paths' or 'openapi').
    A folder or .zip is expanded; Word, Excel, PDF and drawings are read through builder.ingest."""
    out = {}
    for f in _expand(files):
        text = _text_of(f)
        doc = _parse_structured(text) if pathlib.Path(f).suffix.lower() in (".json", ".yaml", ".yml") else None
        toks = openapi_tokens(doc) if isinstance(doc, dict) and ("paths" in doc or "openapi" in doc) \
            else prose_tokens(text)
        for t, kind in toks.items():
            out.setdefault(t, (kind, str(f)))
    return out


# ----------------------------------------------------------------------------------------------- generic filter

class Corpus:
    """What was known before: lower-case words, the joined lower-case text and the 6-word phrases at <ref>."""

    def __init__(self, texts):
        self.text = "\n".join(t.lower() for t in texts)
        self.words = set(_norm_words(self.text))
        self.phrases = set()
        for t in texts:
            self.phrases |= shingles(t)

    def known(self, tok, kind):
        low = tok.lower()
        if kind == "phrase":
            return low in self.phrases
        if low in COMMON or low in self.words:
            return True
        return not re.fullmatch(r"[a-z0-9]+", low) and low in self.text


def distinctive(tokens, corpus):
    """Drop generic tokens (too short, common, or already known at <ref>)."""
    out = {}
    for tok, (kind, src) in tokens.items():
        if kind == "number":
            if len(re.sub(r"\D", "", tok)) < 2:
                continue
        elif len(tok) < 3:
            continue
        if not corpus.known(tok, kind):
            out[tok] = (kind, src)
    return out


# ----------------------------------------------------------------------------------------------- git

def _git(root, *args, input_text=None):
    try:
        r = subprocess.run(["git", "-C", str(root)] + list(args), capture_output=True, text=True, timeout=120,
                           input=input_text)
    except (OSError, subprocess.SubprocessError) as e:
        raise LeakCheckError("git %s failed: %s" % (args[0], e)) from None
    if r.returncode != 0:
        raise LeakCheckError("git %s failed: %s" % (" ".join(args[:2]), r.stderr.strip()[:300]))
    return r.stdout


def corpus_at(root, ref, allow_from):
    names = [n for n in _git(root, "ls-tree", "-r", "--name-only", ref, "--", *allow_from).splitlines() if n]
    texts = []
    for n in names:
        try:
            blob = _git(root, "show", "%s:%s" % (ref, n))
        except LeakCheckError:
            continue
        if len(blob) <= MAX_BLOB:
            texts.append(blob)
    return Corpus(texts)


def parse_diff(diff_text):
    """-> [(file, new line number, text)] of the added lines of a `git diff -U0` output."""
    out, cur, n = [], None, 0
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            cur = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            n = int(m.group(1)) if m else 0
        elif line.startswith("+") and cur is not None:
            out.append((cur, n, line[1:]))
            n += 1
    return out


def added_lines(root, ref, paths, worktree=False):
    rng = [ref] if worktree else ["%s..HEAD" % ref]
    lines = parse_diff(_git(root, "diff", "-U0", "--no-color", "--no-ext-diff", *rng, "--", *paths))
    if worktree:
        for f in _git(root, "ls-files", "--others", "--exclude-standard", "--", *paths).splitlines():
            p = pathlib.Path(root) / f
            if f and p.is_file():
                lines += [(f, i, t) for i, t in enumerate(p.read_text(errors="replace").splitlines(), 1)]
    return lines


# ----------------------------------------------------------------------------------------------- matching

def _pattern(tok):
    return re.compile(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % re.escape(tok), re.I)


def find_hits(tokens, lines):
    """-> [(file, line, kind, token, source)] for each distinctive token in an added line."""
    pats = [(tok, kind, src, _pattern(tok)) for tok, (kind, src) in tokens.items() if kind != "phrase"]
    phrases = {tok: src for tok, (kind, src) in tokens.items() if kind == "phrase"}
    hits = []
    for f, n, text in lines:
        for tok, kind, src, rx in pats:
            if rx.search(text):
                hits.append((f, n, kind, tok, src))
        if phrases:
            for s in shingles(text) & set(phrases):
                hits.append((f, n, "phrase", s, phrases[s]))
    return hits


def main(argv=None, root=ROOT, out=sys.stdout):
    ap = argparse.ArgumentParser(prog="leak_check.py", description="Hidden-brief tokens in builder changes since a ref.")
    ap.add_argument("--hidden", nargs="+", required=True, help="the hidden brief / OpenAPI files")
    ap.add_argument("--since", required=True, help="git ref taken before the hidden briefs opened (e.g. a tag)")
    ap.add_argument("--paths", nargs="+", default=list(DEFAULT_PATHS), help="where a leak matters")
    ap.add_argument("--allow-from", nargs="+", default=list(DEFAULT_ALLOW_FROM),
                    help="tokens present here at <ref> are generic")
    ap.add_argument("--worktree", action="store_true", help="diff <ref> against the working tree (+ untracked files)")
    ap.add_argument("--quiet", action="store_true", help="do not list the tokens, only the hits")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    missing = [f for f in args.hidden if not pathlib.Path(f).exists()]
    if missing:
        print("leak_check: hidden file(s) not found: %s" % ", ".join(missing), file=out)
        return 2
    try:
        corpus = corpus_at(root, args.since, args.allow_from)
        toks = distinctive(hidden_tokens(args.hidden), corpus)
        lines = added_lines(root, args.since, args.paths, args.worktree)
    except LeakCheckError as e:
        print("leak_check: %s" % e, file=out)
        return 2
    by_kind = {}
    for tok, (kind, _src) in sorted(toks.items()):
        by_kind.setdefault(kind, []).append(tok)
    print("leak_check: %d distinctive tokens in %d hidden file(s): %s" % (
        len(toks), len(args.hidden), ", ".join("%s %d" % (k, len(v)) for k, v in sorted(by_kind.items()))), file=out)
    if not args.quiet:
        for kind, vals in sorted(by_kind.items()):
            if kind != "phrase":
                print("  %-7s %s" % (kind, " | ".join(vals)), file=out)
    rng = args.since if args.worktree else "%s..HEAD" % args.since
    print("leak_check: git diff %s -- %s: %d added line(s)" % (rng, " ".join(args.paths), len(lines)), file=out)
    hits = find_hits(toks, lines)
    for f, n, kind, tok, src in hits:
        print("HIT %s:%d [%s] %r (from %s)" % (f, n, kind, tok, src), file=out)
    print("leak_check: %s" % ("%d hit(s): FAIL" % len(hits) if hits else "clean"), file=out)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
