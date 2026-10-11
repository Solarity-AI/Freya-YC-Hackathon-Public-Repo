"""Bundle runtime modules into ONE brace-safe Python snippet for the Freya ctl code node (docs/CONTRACTS.md C.1).
Owner: agent 2. This module itself runs in the builder (not bundled), so it may use any stdlib.

CONTRACT NOTE (bundle):
- Layout is the C.1 template plus one defensive line, `globals().update(locals())`, before the entry call: if the
  platform exec()s the code with separate globals/locals dicts, top-level defs land in locals and functions could
  not see each other; copying them into globals makes both layouts work.
- To stay far below the size limits the bundle is minified with the tokenizer only (no semantic rewrite):
  docstrings, comments and blank lines dropped, one space per indent level, logical lines joined, minimal spaces
  between tokens, and every top-level name except the entry `main` renamed to a short id (nothing in the runtime
  looks names up dynamically). minify=False gives the plain concatenation.
- RSPEC_HEX holds the hex of the exact rspec JSON (C.1). Only when that would push the snippet over MAX_BYTES does
  make_snippet (compact="auto", encoding="auto") first compact the wiring (below), then embed the JSON text itself
  as a brace-escaped string literal (\\x7b / \\x7d); runtime.brain main() accepts hex, JSON text or a dict.
- The compaction turns wiring nodes that follow the naming convention (b_<node>_<field>, r_<node>_<role>,
  res_leaf = catalog roles) to {tool, bf: [fields]}; runtime.brain._b_node expands them again.
"""
import ast
import io
import json
import keyword
import pathlib
import re
import tokenize

MODULE_ORDER = ["cal", "locale", "parse", "ident", "brain"]
FLOW_MODULES = ["flow"]                                 # the generic call-flow runtime (Spec mode "flow")
ALLOWED_IMPORTS = ("json", "re", "datetime")
RUNTIME_DIR = pathlib.Path(__file__).resolve().parent
# sanity cap for an UNPACKED snippet (tests, BRAIN_ENTRY=snippet). The platform limit applies to the packed code
# (PACK_MAX_BYTES + the lint code-plus-data projection), so the builder calls make_snippet(max_bytes=0).
MAX_BYTES = 260_000
KEEP_NAMES = ("main",)


class BundleError(ValueError):
    pass


def check_brace_safe(code):
    """-> list of problems (line numbers containing '{{' or '}}'); empty list = safe."""
    out = []
    for i, line in enumerate(code.splitlines(), 1):
        if "{{" in line or "}}" in line:
            out.append("line %d: %s" % (i, line.strip()[:120]))
    return out


def _docstring_ranges(tree):
    res = []

    def visit(node):
        body = getattr(node, "body", None)
        if isinstance(body, list) and body:
            first = body[0]
            if (isinstance(first, ast.Expr) and isinstance(getattr(first, "value", None), ast.Constant)
                    and isinstance(first.value.value, str)):
                res.append((first.lineno, first.end_lineno, len(body) == 1, first.col_offset))
        for child in ast.walk(node):
            if child is not node and isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                b = child.body
                if b and isinstance(b[0], ast.Expr) and isinstance(getattr(b[0], "value", None), ast.Constant) \
                        and isinstance(b[0].value.value, str):
                    res.append((b[0].lineno, b[0].end_lineno, len(b) == 1, b[0].col_offset))
    visit(tree)
    return sorted(set(res))


def _module_body(name):
    """-> (hoisted_import_lines, body_text, top_level_names) for one runtime module (comments/docstrings kept out)."""
    path = RUNTIME_DIR / (name + ".py")
    src = path.read_text()
    tree = ast.parse(src)
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.append(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
        elif isinstance(node, ast.If) and "__name__" in ast.unparse(node.test):
            raise BundleError("%s: 'if __name__' blocks are not allowed" % name)
    lines = src.splitlines()
    drop = set()
    replace = {}
    for start, end, as_pass, col in _docstring_ranges(tree):
        for ln in range(start, end + 1):
            drop.add(ln)
        if as_pass:
            replace[start] = " " * col + "pass"
    hoisted = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            seg = range(node.lineno, node.end_lineno + 1)
            if isinstance(node, ast.ImportFrom) and node.level and node.level > 0:
                drop.update(seg)
                continue
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.name.split(".")[0] not in ALLOWED_IMPORTS or a.asname:
                        raise BundleError("%s: import %s not allowed" % (name, a.name))
                    hoisted.append("import " + a.name)
            else:
                mod = node.module or ""
                if mod.split(".")[0] not in ALLOWED_IMPORTS:
                    raise BundleError("%s: from %s import not allowed" % (name, mod))
                hoisted.append("from %s import %s" % (mod, ", ".join(
                    a.name + (" as " + a.asname if a.asname else "") for a in node.names)))
            drop.update(seg)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in ALLOWED_IMPORTS:
                    raise BundleError("%s: import %s not allowed" % (name, a.name))
        elif isinstance(node, ast.ImportFrom) and not node.level:
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                raise BundleError("%s: from %s import not allowed" % (name, node.module))
    body_lines = []
    for i, line in enumerate(lines, 1):
        if i in replace:
            body_lines.append(replace[i])
        elif i in drop:
            body_lines.append("")
        else:
            body_lines.append(line)
    return hoisted, "\n".join(body_lines) + "\n", names


def _def_col(toks, tok):
    """Column of the 'def' keyword (FunctionDef.col_offset) for the name token after it."""
    for t in toks:
        if t[2][0] == tok[2][0] and t[1] == "def" and t[2][1] < tok[2][1]:
            return t[2][1]
    return -1


def _except_key(toks, tok):
    """('except', line, col of the 'except' keyword) for the name after 'as' in an except clause."""
    for t in toks:
        if t[2][0] == tok[2][0] and t[1] == "except" and t[2][1] < tok[2][1]:
            return ("except", t[2][0], t[2][1])
    return None


# operator pairs that must keep a space between them so they are not re-tokenized as one operator
_JOINED_OPS = ("**", "//", "==", "<=", ">=", "!=", "->", "<<", ">>", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=",
               ":=", "<>", "**=", "//=")
_EQ_PREFIX_OPS = ("=", "<", ">", "!", "*", "/", "-", "+", "%", "&", "|", "^")
_WORDY = tuple(t for t in (tokenize.NAME, tokenize.NUMBER, tokenize.STRING, getattr(tokenize, "FSTRING_START", None))
               if t is not None)


_FSTRING_MIDDLE = getattr(tokenize, "FSTRING_MIDDLE", -1)


def _minify(src, rename=None, posmap=None):
    """Token-level minifier (see module note). String tokens are emitted unchanged. posmap renames single
    occurrences by (line, col); `except X as name` / nested `def name` are found by the preceding keyword."""
    rename = rename or {}
    posmap = posmap or {}
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    out_lines = []
    cur = []
    level = 0
    prev = None
    prev_op = None
    for tok in toks:
        tt, ts = tok[0], tok[1]
        if tt == tokenize.INDENT:
            level += 1
            continue
        if tt == tokenize.DEDENT:
            level -= 1
            continue
        if tt in (tokenize.COMMENT, tokenize.NL, tokenize.ENCODING, tokenize.ENDMARKER):
            continue
        if tt == tokenize.NEWLINE:
            out_lines.append(" " * level + "".join(cur))   # tokenize emits a token before every NEWLINE
            cur = []
            prev = None
            prev_op = None
            continue
        if tt == tokenize.NAME and prev_op != ".":
            key = (tok[2][0], tok[2][1])
            if key in posmap:
                ts = posmap[key]
            elif ts in rename:
                ts = rename[ts]
            elif prev is not None and prev[1] == "def" and ("def", tok[2][0], _def_col(toks, tok)) in posmap:
                ts = posmap[("def", tok[2][0], _def_col(toks, tok))]
            elif prev is not None and prev[1] == "as" and _except_key(toks, tok) in posmap:
                ts = posmap[_except_key(toks, tok)]
        if tt == _FSTRING_MIDDLE:
            # Python 3.12+ yields f-string literal text unescaped ("{{" -> "{"); escape it back so the meaning (and the
            # brace check on the output) is the same as for the plain source
            ts = ts.replace("{", "{{").replace("}", "}}")
        if prev is not None:
            p_tt, p_ts = prev
            need = (
                (p_tt in _WORDY and tt in _WORDY)
                or (p_tt == tokenize.NUMBER and tt == tokenize.OP and ts == ".")
                or (p_tt == tokenize.OP and tt == tokenize.OP and (p_ts + ts) in _JOINED_OPS)
                or (p_tt == tokenize.OP and p_ts in _EQ_PREFIX_OPS and tt == tokenize.OP and ts == "="))
            if need:
                cur.append(" ")
        cur.append(ts)
        prev = (tt, ts)
        prev_op = ts if tt == tokenize.OP else None
    return "\n".join(out_lines)                          # tokenize always ends a statement with NEWLINE


def _local_renames(src, taken):
    """-> {(line, col): new_name} for every occurrence of a function-local name (params included) in `src`.
    Each function scope (incl. lambdas) maps its locals to short names unused anywhere in the bundle; nested scopes
    inherit the parent's mapping for free variables. Parameters that are ever passed by keyword are kept, as are
    names declared global/nonlocal."""
    tree = ast.parse(src)
    kw_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg:
            kw_names.add(node.arg)
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            kw_names.update(node.names)
    pos = {}
    counter = [0]

    def fresh():
        while True:
            k = counter[0]
            counter[0] += 1
            s2 = ""
            while True:
                s2 = "abcdefghijklmnopqrstuvwxyz"[k % 26] + s2
                k = k // 26 - 1
                if k < 0:
                    break
            if s2 not in taken and not keyword.iskeyword(s2):
                return s2

    def scope_nodes(fn):
        """Nodes of fn's own scope (comprehensions included), nested defs/lambdas yielded but not entered."""
        stack = list(ast.iter_child_nodes(fn))
        while stack:
            n = stack.pop()
            yield n
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                continue
            stack.extend(ast.iter_child_nodes(n))

    def handle(fn, parent_map):
        a = fn.args
        params = [x for x in (a.posonlyargs + a.args + a.kwonlyargs) if x.arg not in kw_names]
        for x in (a.vararg, a.kwarg):
            if x is not None and x.arg not in kw_names:
                params.append(x)
        local = set(x.arg for x in params)
        for n in scope_nodes(fn):
            if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)) and n.id not in kw_names:
                local.add(n.id)
            elif isinstance(n, ast.ExceptHandler) and n.name and n.name not in kw_names:
                local.add(n.name)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name not in kw_names:
                local.add(n.name)
        mp = dict(parent_map)
        for name in sorted(local):
            mp[name] = fresh()
        for x in params:
            pos[(x.lineno, x.col_offset)] = mp[x.arg]
        for n in scope_nodes(fn):
            if isinstance(n, ast.Name) and n.id in mp:
                pos[(n.lineno, n.col_offset)] = mp[n.id]
            elif isinstance(n, ast.ExceptHandler) and n.name and n.name in mp:
                pos[("except", n.lineno, n.col_offset)] = mp[n.name]
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in mp:
                pos[("def", n.lineno, n.col_offset)] = mp[n.name]
        for n in scope_nodes(fn):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                handle(n, mp)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            counter[0] = 0
            handle(node, dict())
        else:
            for n in ast.walk(node):
                if isinstance(n, ast.Lambda):
                    counter[0] = 0
                    handle(n, dict())
    return pos


def _short_names(names, taken):
    out = {}
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    i = 0
    for n in names:
        while True:
            k = i
            s = ""
            while True:
                s = alphabet[k % len(alphabet)] + s
                k = k // len(alphabet)
                if k == 0:
                    break
            cand = "Q" + s
            i += 1
            if cand not in taken and not keyword.iskeyword(cand):
                break
        out[n] = cand
    return out


def bundle_source(minify=True, rename_locals=True, modules=None):
    """Concatenate MODULE_ORDER bodies: hoist allowed stdlib imports, strip sibling imports ('from .x import ...'),
    assert unique top-level names (ast) and brace safety. -> code string (no RSPEC, no entry call)."""
    hoisted, bodies, seen = [], [], {}
    for name in (modules or MODULE_ORDER):
        h, body, names = _module_body(name)
        for imp in h:
            if imp not in hoisted:
                hoisted.append(imp)
        for n in names:
            if n in seen:
                raise BundleError("top-level name %r defined in both %s and %s" % (n, seen[n], name))
            seen[n] = name
        bodies.append(body)
    joined = "\n".join(bodies)
    rename = {}
    if minify:
        all_names = set()
        for tok in tokenize.generate_tokens(io.StringIO(joined).readline):
            if tok[0] == tokenize.NAME:
                all_names.add(tok[1])
        private = sorted(n for n in seen if n not in KEEP_NAMES)
        rename = _short_names(private, all_names)
        taken = set(all_names) | set(rename.values()) | set(dir(__builtins__) if isinstance(__builtins__, dict)
                                                             else dir(__import__("builtins")))
        taken |= set(["vars", "json", "re", "datetime", "date", "timedelta"])
        posmap = _local_renames(joined, taken) if rename_locals else {}
        code = "\n".join(hoisted) + "\n" + _minify(joined, rename, posmap) + "\n"
    else:
        code = "\n".join(hoisted) + "\n" + "\n".join(
            line.rstrip() for line in joined.splitlines() if line.strip() and not line.strip().startswith("#")) + "\n"
    probs = check_brace_safe(code)
    if probs:
        raise BundleError("bundle not brace-safe: " + "; ".join(probs[:5]))
    return code


def compact_wiring(wiring):
    """Shrink wiring nodes that follow the naming convention (see module note). Never changes semantics."""
    w = json.loads(json.dumps(wiring))
    roles = w.get("roles") or {}
    for node, n in list((w.get("nodes") or {}).items()):
        tool = n.get("tool", "")
        rres = (roles.get(tool) or {}).get("res") or {}
        body = n.get("body") or {}
        if any(v != "b_" + node + "_" + f for f, v in body.items()):
            continue
        if n.get("res") != dict((r, "r_" + node + "_" + r) for r in rres):
            continue
        if n.get("res_leaf") != rres:
            continue
        extra = set(n) - {"tool", "body", "res", "res_leaf"}
        if extra:
            continue
        w["nodes"][node] = {"tool": tool, "bf": sorted(body)}
    return w


def rspec_hex(rspec):
    return json.dumps(rspec, separators=(",", ":"), ensure_ascii=True, sort_keys=True).encode("ascii").hex()


def rspec_literal(rspec):
    """Brace-safe Python string literal holding the rspec JSON text itself (about half the size of hex)."""
    # ensure_ascii=False: a call language's letters stay one or two UTF-8 bytes instead of a six-letter \uXXXX
    # escape (the literal is valid Python source either way; JSON escapes every control character)
    txt = json.dumps(rspec, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
    txt = txt.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    txt = txt.replace("\\", "\\\\").replace("'", "\\'").replace("\x7b", "\\x7b").replace("\x7d", "\\x7d")
    return "'" + txt + "'"


def make_snippet(rspec, minify=True, compact="auto", encoding="auto", max_bytes=None, modules=None):
    """Full ctl code: bundle_source() + RSPEC_HEX line + guarded main(vars, RSPEC_HEX) call (CONTRACTS C.1).
    encoding: "hex" (C.1), "json" (brace-escaped JSON literal; main() accepts both) or "auto" = hex unless that
    would exceed the size cap. max_bytes: the cap (default MAX_BYTES; 0 = no cap, for a snippet that is packed).
    Raises BundleError if the result is not brace-safe, does not compile, or is too big."""
    limit = MAX_BYTES if max_bytes is None else int(max_bytes)
    code = bundle_source(minify=minify, modules=modules) if modules else bundle_source(minify=minify)
    rs = dict(rspec)
    if compact is True and isinstance(rs.get("wiring"), dict):
        rs["wiring"] = compact_wiring(rs["wiring"])

    def build(enc):
        lit = rspec_literal(rs) if enc == "json" else "'" + rspec_hex(rs) + "'"
        tail = (
            "RSPEC_HEX = " + lit + "\n"
            "globals().update(locals())\n"
            "try:\n"
            "    main(vars, RSPEC_HEX)\n"
            "except Exception:\n"
            "    vars['nx'] = 's_safe'\n"
        )
        return code + tail

    snippet = build("json" if encoding == "json" else "hex")
    if compact == "auto" and 0 < limit < len(snippet.encode("utf-8")) and isinstance(rs.get("wiring"), dict):
        rs["wiring"] = compact_wiring(rs["wiring"])
        snippet = build("json" if encoding == "json" else "hex")
    if encoding == "auto" and 0 < limit < len(snippet.encode("utf-8")):
        snippet = build("json")
    probs = check_brace_safe(snippet)
    if probs:
        raise BundleError("snippet not brace-safe: " + "; ".join(probs[:5]))
    try:
        compile(snippet, "<ctl>", "exec")
    except SyntaxError as e:
        raise BundleError("snippet does not compile: %s" % e)
    if 0 < limit < len(snippet.encode("utf-8")):
        raise BundleError("snippet is %d bytes (> %d)" % (len(snippet.encode("utf-8")), limit))
    return snippet


# ---------------------------------------------------------------- packing (live limit, 2026-10-11)
# LIVE FACT: code_exec rejects "code and data" over 131072 bytes in total ("data" = the variable table, about
# 16-31 KB). The minified bundle with the rspec is about 190 KB, so the ctl code ships PACKED: the full snippet
# is raw-DEFLATE compressed, encoded as text in an 85-letter alphabet (_QALPHA) and run by a small loader with
# exec(). The loader uses only builtins: the text is decoded by hand, and zlib is tried first with a pure-Python
# inflate as the fallback, so the snippet still runs if the sandbox allows only json/re/datetime. The loader itself
# is brace-safe and imports nothing outside ALLOWED_IMPORTS at the top level.
# Hard cap, above the 85 KB target (lint warns from CODE_WARN_BYTES): a hidden Spec a little bigger than the target
# still builds, and the compiler bakes a smaller turn budget for it (compiler/snippet.turn_cap), so a long call
# wraps up instead of meeting the platform limit.
PACK_MAX_BYTES = 98_000  # hard stop; the turn cap (snippet.turn_cap) adapts to the size
# 85 printable ASCII letters without braces (brace safety), quotes and backslash (a plain '...' literal), the
# characters a JSON encoder may escape (< > &), and backtick: the packed text is never escaped or lengthened.
_QALPHA = "".join(ch for ch in map(chr, range(33, 127)) if ch not in "{}\\'\"<>&`")

_LOADER = r'''import json
import re
import datetime
def _qb(s):
    a = QALPHA
    t = dict(zip(a, range(85)))
    o = bytearray()
    for i in range(0, len(s), 5):
        g = s[i:i + 5]
        v = 0
        for ch in g + a[84] * (5 - len(g)):
            v = v * 85 + t[ch]
        o += v.to_bytes(4, 'big')[:len(g) - 1]
    return bytes(o)
def _qi(d):
    o = bytearray()
    p = [0]
    def rb(n):
        v = 0
        b = p[0]
        for i in range(n):
            v |= ((d[b >> 3] >> (b & 7)) & 1) << i
            b += 1
        p[0] = b
        return v
    def mk(ls):
        mx = max(ls)
        bc = [0] * (mx + 2)
        for l in ls:
            if l:
                bc[l] += 1
        nc = [0] * (mx + 2)
        c = 0
        for k in range(1, mx + 1):
            c = (c + bc[k - 1]) << 1
            nc[k] = c
        t = dict()
        for s, l in enumerate(ls):
            if l:
                t[(l, nc[l])] = s
                nc[l] += 1
        return t
    def sym(t):
        c = 0
        l = 0
        while l < 20:
            c = (c << 1) | rb(1)
            l += 1
            r = t.get((l, c))
            if r is not None:
                return r
        raise ValueError('bad code')
    LB = [3,4,5,6,7,8,9,10,11,13,15,17,19,23,27,31,35,43,51,59,67,83,99,115,131,163,195,227,258]
    LE = [0,0,0,0,0,0,0,0,1,1,1,1,2,2,2,2,3,3,3,3,4,4,4,4,5,5,5,5,0]
    DB = [1,2,3,4,5,7,9,13,17,25,33,49,65,97,129,193,257,385,513,769,1025,1537,2049,3073,4097,6145,8193,12289,16385,24577]
    DE = [0,0,0,0,1,1,2,2,3,3,4,4,5,5,6,6,7,7,8,8,9,9,10,10,11,11,12,12,13,13]
    OR = [16,17,18,0,8,7,9,6,10,5,11,4,12,3,13,2,14,1,15]
    last = 0
    while not last:
        last = rb(1)
        ty = rb(2)
        if ty == 0:
            p[0] = (p[0] + 7) & ~7
            i = p[0] >> 3
            ln = d[i] | (d[i + 1] << 8)
            o += d[i + 4:i + 4 + ln]
            p[0] = (i + 4 + ln) * 8
            continue
        if ty == 1:
            lt = mk([8] * 144 + [9] * 112 + [7] * 24 + [8] * 8)
            dt = mk([5] * 30)
        else:
            hl = rb(5) + 257
            hd = rb(5) + 1
            hc = rb(4) + 4
            cl = [0] * 19
            for i in range(hc):
                cl[OR[i]] = rb(3)
            ct = mk(cl)
            ls = []
            while len(ls) < hl + hd:
                s = sym(ct)
                if s < 16:
                    ls.append(s)
                elif s == 16:
                    ls += [ls[-1]] * (3 + rb(2))
                elif s == 17:
                    ls += [0] * (3 + rb(3))
                else:
                    ls += [0] * (11 + rb(7))
            lt = mk(ls[:hl])
            dt = mk(ls[hl:])
        while True:
            s = sym(lt)
            if s < 256:
                o.append(s)
            elif s == 256:
                break
            else:
                s -= 257
                ln = LB[s] + rb(LE[s])
                s = sym(dt)
                ds = DB[s] + rb(DE[s])
                st = len(o) - ds
                if ds >= ln:
                    o += o[st:st + ln]
                else:
                    for k in range(ln):
                        o.append(o[st + k])
    return bytes(o)
def _qz(b):
    try:
        import zlib
        return zlib.decompress(b, -15)
    except Exception:
        return _qi(b)
globals().update(locals())
try:
    _qs = _qz(_qb(QPACK)).decode('utf-8')
    _qg = dict(globals())
    _qg.update(locals())
    exec(_qs, _qg)
except Exception:
    vars['nx'] = 's_safe'
'''


def _b85(raw):
    """raw bytes -> text in the 85-letter alphabet _QALPHA (4 bytes -> 5 letters; a last group of n bytes -> n + 1
    letters). About 6% shorter than base64."""
    out = []
    for i in range(0, len(raw), 4):
        g = raw[i:i + 4]
        v = int.from_bytes(g + b"\0" * (4 - len(g)), "big")
        d = []
        for _ in range(5):
            v, r = divmod(v, 85)
            d.append(_QALPHA[r])
        out.append("".join(reversed(d))[:len(g) + 1])
    return "".join(out)


def _unb85(text):
    t = dict(zip(_QALPHA, range(85)))
    o = bytearray()
    for i in range(0, len(text), 5):
        g = text[i:i + 5]
        v = 0
        for ch in g + _QALPHA[84] * (5 - len(g)):
            v = v * 85 + t[ch]
        o += v.to_bytes(4, "big")[:len(g) - 1]
    return bytes(o)


def pack_snippet(snippet, force_fallback=False):
    """-> brace-safe loader code that exec()s `snippet` (raw DEFLATE + the 85-letter text encoding, see the note
    above). The loader passes the variable table through as the same dict object, so the inner snippet's writes to
    vars land on the platform's variable table."""
    import zlib
    co = zlib.compressobj(9, zlib.DEFLATED, -15, 9)
    raw = co.compress(snippet.encode("utf-8")) + co.flush()
    loader = re.sub(r"(?m)^((?: {4})+)", lambda m: " " * (len(m.group(1)) // 4), _LOADER)    # one space per level
    loader = loader.replace("QALPHA", "'" + _QALPHA + "'", 1).replace("QPACK)", "'" + _b85(raw) + "')", 1)
    if force_fallback:
        loader = loader.replace("import zlib\n", "import zlib_missing_for_test\n", 1)
    probs = check_brace_safe(loader)
    if probs:
        raise BundleError("packed snippet not brace-safe: " + "; ".join(probs[:5]))
    compile(loader, "<ctl>", "exec")
    if len(loader.encode("utf-8")) > PACK_MAX_BYTES:
        raise BundleError("packed snippet is %d bytes (> %d)" % (len(loader.encode("utf-8")), PACK_MAX_BYTES))
    return loader


def unpack_snippet(code):
    """Inverse of pack_snippet for tests/tools: -> the inner snippet, or `code` itself when it is not packed."""
    import zlib
    m = re.search(r"_qz\(_qb\('([^'\\]*)'\)\)", code)
    if not m:
        return code
    return zlib.decompress(_unb85(m.group(1)), -15).decode("utf-8")
