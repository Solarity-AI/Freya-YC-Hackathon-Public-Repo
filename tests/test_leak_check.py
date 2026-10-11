"""tools/leak_check.py: distinctive hidden-brief tokens found in builder lines added since a git ref are reported
(exit 1); generic words and anything the repo already held at the ref are not."""
import importlib.util
import io
import json
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("tools_leak_check", ROOT / "tools" / "leak_check.py")
leak = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(leak)

BRIEF = """# Quillbrook Credit Union: arrears desk
Quillbrook calls members who owe $1,847.50 on account HB-204 by March 14, 2027 or 2027-03-14.
Open with "Thanks for holding, this is Quillbrook" and never mention the zephyrine overdraft programme today.
Use the code PROMISE_KEPT_ZQ when the member agrees. Due 4/30/2027.
"""
OPENAPI = {"openapi": "3.0.0", "servers": [{"url": "https://bank.example/zq"}],
           "paths": {"/members/{id}/arrears_zq": {"post": {"operationId": "logArrearsZq", "requestBody": {
               "content": {"application/json": {"schema": {"type": "object", "properties": {
                   "outcome_zq": {"type": "string", "enum": ["kept_zq", "declined"], "example": "kept_zq"},
                   "amount": {"type": "number", "default": 2500},
                   "flag": {"type": "boolean", "default": True}}}}}}}}},
           "components": {"schemas": {"ArrearsZq": {"type": "object", "description": "See 'Harrowgate rules'."}}}}


def _git(root, *args):
    subprocess.run(["git", "-C", str(root)] + list(args), check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    (r / "builder").mkdir(parents=True)
    (r / "kit").mkdir()
    (r / "builder" / "a.py").write_text("# the customer account is late; ask for a payment promise\nX = 30\n")
    (r / "kit" / "brief.md").write_text("Public brief: declined, amount, members, Thanks for holding.\n")
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "t")
    _git(r, "add", ".")
    _git(r, "commit", "-qm", "base")
    _git(r, "tag", "pre-hidden")
    hidden = tmp_path / "hidden"
    hidden.mkdir()
    (hidden / "hidden-1.md").write_text(BRIEF)
    (hidden / "hidden-1.openapi.json").write_text(json.dumps(OPENAPI))
    return r, [str(hidden / "hidden-1.md"), str(hidden / "hidden-1.openapi.json")]


def run(root, argv):
    out = io.StringIO()
    code = leak.main(argv, root=root, out=out)
    return code, out.getvalue()


def commit(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "change")


def test_tokens_listed_and_generic_ones_dropped(repo):
    root, hidden = repo
    code, out = run(root, ["--hidden", *hidden, "--since", "pre-hidden"])
    assert code == 0 and "leak_check: clean" in out and "0 added line(s)" in out
    for tok in ("Quillbrook Credit Union", "1,847.50", "1847.50", "HB-204", "March 14, 2027", "2027-03-14", "4/30/2027",
                "PROMISE_KEPT_ZQ", "kept_zq", "logArrearsZq", "/members/{id}/arrears_zq", "outcome_zq", "ArrearsZq",
                "Harrowgate rules", "https://bank.example/zq", "zephyrine"):
        assert tok in out, tok
    tokens_line = "\n".join(x for x in out.splitlines() if x.startswith("  "))
    for generic in ("declined", "| amount", "Thanks for holding |", "| 30 |"):      # known at the ref / common
        assert generic not in tokens_line, generic


def test_leaked_tokens_in_a_commit_are_hits(repo):
    root, hidden = repo
    commit(root, "builder/b.py", "NAME = 'Quillbrook'\nCAP = 1847.50\nOUT = ['kept_zq']\n"
                                 "# never mention the zephyrine overdraft programme today\nok = True\n")
    code, out = run(root, ["--hidden", *hidden, "--since", "pre-hidden", "--quiet"])
    assert code == 1 and "FAIL" in out
    hits = [x for x in out.splitlines() if x.startswith("HIT ")]
    assert any("builder/b.py:1 [name] 'Quillbrook'" in h for h in hits)
    assert any("builder/b.py:2 [number] '1847.50'" in h for h in hits)
    assert any("builder/b.py:3 [enum] 'kept_zq'" in h and "openapi" in h for h in hits)
    assert any("builder/b.py:4 [phrase]" in h for h in hits) and not any(":5 " in h for h in hits)
    assert "  name " not in out                                                      # --quiet: no token list


def test_generic_fix_is_clean_and_other_paths_are_ignored(repo):
    root, hidden = repo
    commit(root, "builder/a.py", "# the customer account is late; ask for a payment promise\nX = 31\n")
    commit(root, "docs/notes.md", "Quillbrook HB-204\n")                              # not builder code
    code, out = run(root, ["--hidden", *hidden, "--since", "pre-hidden"])
    assert code == 0 and "1 added line(s)" in out


def test_worktree_mode_includes_uncommitted_and_untracked(repo):
    root, hidden = repo
    (root / "builder" / "a.py").write_text((root / "builder" / "a.py").read_text() + "D = '2027-03-14'\n")
    (root / "runtime").mkdir()
    (root / "runtime" / "new.py").write_text("x = 1\ncode = 'HB-204'\n")
    code, out = run(root, ["--hidden", *hidden, "--since", "pre-hidden"])
    assert code == 0                                                                 # HEAD unchanged
    code, out = run(root, ["--hidden", *hidden, "--since", "pre-hidden", "--worktree"])
    assert code == 1 and "builder/a.py:3 [date] '2027-03-14'" in out and "runtime/new.py:2 [code] 'HB-204'" in out


@pytest.mark.parametrize("argv, code", [
    (["--since", "pre-hidden"], 2),
    (["--help"], 0),
])
def test_usage(repo, argv, code):
    root, _ = repo
    assert run(root, argv)[0] == code


def test_bad_inputs(repo, tmp_path):
    root, hidden = repo
    code, out = run(root, ["--hidden", str(tmp_path / "missing.md"), "--since", "pre-hidden"])
    assert code == 2 and "not found" in out
    code, out = run(root, ["--hidden", *hidden, "--since", "no-such-ref"])
    assert code == 2 and "git" in out
    code, out = run(tmp_path / "nowhere", ["--hidden", *hidden, "--since", "pre-hidden"])
    assert code == 2


def test_yaml_and_non_openapi_json(tmp_path):
    y = tmp_path / "api.yaml"
    y.write_text("openapi: 3.0.0\npaths:\n  /zq_calls:\n    get:\n      operationId: listZq\n")
    j = tmp_path / "notes.json"
    j.write_text(json.dumps({"text": "Talk to Bramblewick"}))
    bad = tmp_path / "broken.yml"
    bad.write_text("a: [unclosed\n  Zorvane Holdings")
    toks = leak.hidden_tokens([y, j, bad])
    assert toks["listZq"][0] == "code" and toks["/zq_calls"][0] == "path"
    assert "Bramblewick" in toks and "Zorvane Holdings" in toks


def test_parse_diff():
    diff = ("diff --git a/x b/x\n+++ b/builder/x.py\n@@ -1,0 +5,2 @@\n+one\n+two\n-gone\n"
            "+++ /dev/null\n@@ -1 +0,0 @@\n+ignored\n@@ junk @@\n")
    assert leak.parse_diff(diff) == [("builder/x.py", 5, "one"), ("builder/x.py", 6, "two")]


def test_git_missing(monkeypatch):
    def boom(*a, **kw):
        raise OSError("no git")
    monkeypatch.setattr(leak.subprocess, "run", boom)
    with pytest.raises(leak.LeakCheckError, match="no git"):
        leak._git(ROOT, "status")


def test_corpus_skips_unreadable_blobs(repo, monkeypatch):
    root, _ = repo
    real = leak._git

    def flaky(r, *args, **kw):
        if args[0] == "show":
            raise leak.LeakCheckError("bad blob")
        return real(r, *args, **kw)
    monkeypatch.setattr(leak, "_git", flaky)
    assert leak.corpus_at(root, "pre-hidden", ["builder"]).words == set()
