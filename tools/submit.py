#!/usr/bin/env python3
"""Package one build for the hackathon form, then print the form JSON.

THE FINAL (one case, one agent, our own mock):
    python3 tools/submit.py final --members "Name One, Name Two" [--mock-url URL] [--run-dir ...] [--offline]
  The official trace is traces/final.log, the tee'd stdout of
    python3 builder/build.py <CaseFolder> <mock_url> 2>&1 | tee traces/final.log
  Writes submission/final.workflow.json, traces/final.trace.jsonl and submission.json (repo root):
    {team, members, repo, commit, run_command, workflow, trace, mock_url}
  mock_url comes from the log's START line (the URL the agent's tools call) unless --mock-url is given; members are
  kept in submission.json once given. A mock that is not https, a temporary trycloudflare.com tunnel, or one whose
  /health does not answer ok (online only) is refused.

Legacy (the two hidden briefs):
    python3 tools/submit.py hidden-1 [--run-dir runs/<slot>/<run_id>] [--offline]
    python3 tools/submit.py --form                  # only print the form for what submission/ + traces/ hold now

For hidden slot N the official trace is traces/N.log, the tee'd stdout of
    python3 builder/build.py briefs/N.md briefs/N.openapi.json 2>&1 | tee traces/N.log
The run is the one that log names (its START line's run_dir); without a log, the latest run of brief N under runs/.
Checks, all before anything is copied:
  - the run ended with exit 0, deployed, and every FREYA event names ONE workflow id; the export's workflow_id,
    ids.json and the SUMMARY agree with it (and the export's agent_id with the SUMMARY's);
  - traces/N.log belongs to that run (it names the run id) and reached END exit 0;
  - no secret in the export, the log or trace.jsonl: fak_*, sk-ant-*, or the value of any key in the environment;
  - online (read-only GETs, skipped with --offline): the newest version of the workflow is published and is the run's
    version, and the workflow's updatedAt still equals the export's (the agent was not edited after the run).
Then: run_dir/workflow.export.json -> submission/N.workflow.json, run_dir/trace.jsonl -> traces/N.trace.jsonl
(traces/N.log is left as tee wrote it; when it is missing, run_dir/trace.txt is copied there with a warning).
stdout carries only the form JSON; every message goes to stderr. Exit 0 ok, 1 a check failed, 2 bad usage.
"""
import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEAM = "Solarity-AI"
REPO = os.environ.get("SUBMISSION_REPO", "")
BRANCH = os.environ.get("SUBMISSION_BRANCH", "main")
RUN_COMMAND = "python3 builder/build.py {brief_path} {tool_api_path}"
FINAL_RUN_COMMAND = "python3 builder/build.py {case_folder} {mock_url}"
FINAL = "final"
NAME_RE = re.compile(r"^(hidden-\d+|final)$")
BUILDER_PATHS = ("builder", "runtime", "harness", "kit", "requirements.txt")
SECRET_PATTERNS = (("a fak_ key", re.compile(r"fak_[A-Za-z0-9]")), ("an sk-ant- key", re.compile(r"sk-ant-[A-Za-z0-9]")))
SECRET_ENV = ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN",
              "ANTHROPIC_AUTH_TOKEN")
MIN_SECRET_LEN = 8
_WID_IN_MSG = re.compile(r"\b(?:created|updated) workflow ([0-9A-Za-z-]{8,})")


class SubmitError(Exception):
    pass


def say(msg):
    print(msg, file=sys.stderr, flush=True)


# ----------------------------------------------------------------------------------------------- locating the run

def run_dir_from_log(text):
    """The run folder the tee'd log's START line names, or None."""
    for line in text.splitlines():
        if " START " not in line or "| build |" not in line:
            continue
        m = re.search(r"\brun_dir=(.+?) model_default=", line) or re.search(r"\brun_dir=(\S+)", line)
        if m:
            return pathlib.Path(m.group(1))
    return None


def latest_run(root, name):
    """Newest runs/[$BUILDER_SLOT_PREFIX]<name>-<sha8>-<stamp>/r<UTC>/ that holds a trace (run ids sort by time)."""
    prefix = re.sub(r"[^A-Za-z0-9_-]", "-", os.environ.get("BUILDER_SLOT_PREFIX") or "")[:20]
    slot_re = re.compile(r"^%s-[0-9a-f]{8}-" % re.escape(prefix + name))
    cands = [d for s in (root / "runs").glob(prefix + name + "-*") if s.is_dir() and slot_re.match(s.name)
             for d in s.glob("r*") if (d / "trace.jsonl").is_file()]
    return max(cands, key=lambda d: d.name) if cands else None


def find_run_dir(root, name, log_path, run_dir=None):
    if run_dir:
        rd = pathlib.Path(run_dir)
    elif log_path.is_file():
        rd = run_dir_from_log(log_path.read_text(errors="replace"))
        if rd is None:
            raise SubmitError("%s has no START line naming its run_dir: is it the tee'd build output?" % log_path)
    else:
        rd = latest_run(root, name)
        if rd is None:
            raise SubmitError("no run of brief %s under %s/runs (and no %s)" % (name, root, log_path))
    if not (rd / "trace.jsonl").is_file():
        raise SubmitError("run folder %s has no trace.jsonl" % rd)
    return rd


# ----------------------------------------------------------------------------------------------- verifying the run

def _records(path):
    out = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _freya_ids(recs):
    ids = set()
    for r in recs:
        if r.get("kind") != "FREYA":
            continue
        if r.get("workflow_id"):
            ids.add(str(r["workflow_id"]))
        m = _WID_IN_MSG.search(str(r.get("msg", "")))
        if m:
            ids.add(m.group(1))
    return ids


def verify_run(rd):
    """-> {"workflow_id", "agent_id", "version", "updated_at", "commit"} of a finished, deployed run."""
    recs = _records(rd / "trace.jsonl")
    summ = next((r for r in reversed(recs) if r.get("kind") == "SUMMARY"), None)
    if summ is None:
        raise SubmitError("%s: trace.jsonl has no SUMMARY (the build did not finish)" % rd)
    if summ.get("exit") != 0 or not summ.get("deployed"):
        raise SubmitError("%s: the build exited %s, deployed=%s" % (rd, summ.get("exit"), summ.get("deployed")))
    ids = _freya_ids(recs)
    if len(ids) != 1:
        raise SubmitError("%s: expected one workflow id in the FREYA events, found %s" % (rd, sorted(ids) or "none"))
    wid = ids.pop()
    export_p = rd / "workflow.export.json"
    if not export_p.is_file():
        raise SubmitError("%s: no workflow.export.json" % rd)
    export = json.loads(export_p.read_text())
    others = {"export": export.get("workflow_id"), "SUMMARY": summ.get("workflow_id")}
    if (rd / "ids.json").is_file():
        others["ids.json"] = json.loads((rd / "ids.json").read_text()).get("workflow_id")
    bad = {k: v for k, v in others.items() if v != wid}
    if bad:
        raise SubmitError("%s: workflow id mismatch: FREYA event %s vs %s" % (rd, wid, bad))
    if summ.get("agent_id") and export.get("agent_id") != summ.get("agent_id"):
        raise SubmitError("%s: export agent_id %s != SUMMARY agent_id %s" % (rd, export.get("agent_id"),
                                                                           summ.get("agent_id")))
    start = next((r for r in recs if r.get("kind") == "START"), {})
    return {"workflow_id": wid, "agent_id": export.get("agent_id"), "version": summ.get("version"),
            "updated_at": export.get("updated_at"), "commit": start.get("commit")}


def verify_log(text, rd, wid):
    if rd.name not in text:
        raise SubmitError("the log names another run, not %s" % rd.name)
    if not re.search(r"\bEND \S+ \| exit 0\b", text):
        raise SubmitError("the log has no 'END ... | exit 0' line (the build failed or was cut off)")
    if wid not in text:
        raise SubmitError("the log never mentions workflow %s" % wid)


def scan_secrets(files, env=None):
    """-> ['file:line: <what>'] for every fak_* / sk-ant-* / environment key value (never the value itself)."""
    env = os.environ if env is None else env
    values = [(k, env[k]) for k in SECRET_ENV if len(env.get(k) or "") >= MIN_SECRET_LEN]
    hits = []
    for f in files:
        for i, line in enumerate(pathlib.Path(f).read_text(errors="replace").splitlines(), 1):
            hits += ["%s:%d: %s" % (f, i, what) for what, pat in SECRET_PATTERNS if pat.search(line)]
            hits += ["%s:%d: the value of %s" % (f, i, k) for k, v in values if v in line]
    return hits


def check_published(fr, wid, version, updated_at):
    """Read-only: the newest version is published and is the run's; the workflow is unchanged since the export."""
    r = fr.api("GET", "/api/v2/versions/workflow/%s" % wid, workspaceId=fr.workspace_id(), limit=100)
    vs = [v for v in ((r.get("versions") if isinstance(r, dict) else r) or []) if isinstance(v, dict)]
    if not vs:
        raise SubmitError("workflow %s: no versions listed" % wid)
    newest = max(vs, key=lambda v: int(v.get("versionNumber") or 0))
    if not newest.get("isPublished"):
        raise SubmitError("workflow %s: newest version %s is not published" % (wid, newest.get("versionNumber")))
    if version is not None and int(newest.get("versionNumber") or 0) != int(version):
        raise SubmitError("workflow %s: newest published version is %s, the run published %s (edited after the run?)"
                          % (wid, newest.get("versionNumber"), version))
    w = fr.api("GET", "/api/v2/workflow/%s" % wid, workspaceId=fr.workspace_id()).get("workflow") or {}
    if updated_at and w.get("updatedAt") != updated_at:
        raise SubmitError("workflow %s: updatedAt is %s, the export has %s (edited after the run?)"
                          % (wid, w.get("updatedAt"), updated_at))
    return int(newest.get("versionNumber") or 0)


PUBLISHED_CHECK_TIMEOUT_S = 20      # the kit's urlopen waits 120 s per request; a hung platform must not hang submit
OFFLINE_HINT = "the platform may be down; rerun with --offline to skip the published-version check"


def check_published_bounded(fr, wid, version, updated_at, timeout=None):
    """check_published under a short deadline (run in a daemon thread: the kit's own timeout cannot be changed)."""
    timeout = PUBLISHED_CHECK_TIMEOUT_S if timeout is None else timeout
    box = {}

    def work():
        try:
            box["v"] = check_published(fr, wid, version, updated_at)
        except BaseException as e:                       # noqa: BLE001 (re-raised in the caller's thread)
            box["e"] = e

    t = threading.Thread(target=work, name="submit-check-published", daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise SubmitError("the Freya API did not answer within %ss: %s" % (timeout, OFFLINE_HINT))
    if "e" in box:
        raise box["e"]
    return box["v"]


def _kit_freya(root):
    if not os.environ.get("FREYA_API_KEY"):
        raise SubmitError("FREYA_API_KEY is not set: source the kit env.sh, or pass --offline to skip the "
                          "published-version check")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from builder import paths
    return paths.import_kit("freya")


# ----------------------------------------------------------------------------------------------- git + form

def _git(root, *args):
    try:
        r = subprocess.run(["git", "-C", str(root)] + list(args), capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return r.returncode, r.stdout.strip()


def git_head(root):
    rc, out = _git(root, "rev-parse", "HEAD")
    return out if rc == 0 and out else "unknown"


def git_warnings(root, run_commit=None):
    """Reproducibility warnings (strings): dirty builder code, a run built from other code, an unpushed HEAD."""
    out = []
    head = git_head(root)
    if _git(root, "status", "--porcelain", "--", *BUILDER_PATHS)[1]:
        out.append("uncommitted changes under the builder's code: commit them before you send the form")
    if run_commit and run_commit.endswith("+dirty"):
        out.append("the run was built from UNCOMMITTED builder code (%s): the organisers cannot reproduce it; "
                   "commit and rebuild" % run_commit)
    base = (run_commit or "").replace("+dirty", "")
    if base and base != "unknown" and _git(root, "diff", "--quiet", base, "HEAD", "--", *BUILDER_PATHS)[0] != 0:
        out.append("the builder's code changed between the run's commit %s and HEAD %s: rebuild from HEAD"
                   % (base[:12], head[:12]))
    rc, remote = _git(root, "branch", "-r", "--contains", "HEAD")
    if rc != 0 or "origin/%s" % BRANCH not in remote.split():
        out.append("HEAD %s is not on origin/%s yet: push before you send the form" % (head[:12], BRANCH))
    return out


def form(root):
    names = sorted((p.name[:-len(".workflow.json")] for p in (root / "submission").glob("hidden-*.workflow.json")
                    if (root / "traces" / (p.name[:-len(".workflow.json")] + ".log")).is_file()),
                   key=lambda n: int(n.split("-")[1]) if n.split("-")[1].isdigit() else 0)
    return {"team": TEAM, "repo": REPO, "branch": BRANCH, "commit": git_head(root), "run_command": RUN_COMMAND,
            "workflows": {n: "submission/%s.workflow.json" % n for n in names},
            "traces": {n: "traces/%s.log" % n for n in names}}


def mock_url_from_log(text):
    """The mock URL the build's START line records (build.py input_fields), or None."""
    for line in text.splitlines():
        if " START " in line and "| build |" in line:
            m = re.search(r"\bmock_url=(\S+)", line)
            if m and m.group(1) not in ("None", ""):
                return m.group(1).rstrip("/")
    return None


def check_mock_url(url, fetch=None):
    """-> list of problems with the submitted mock URL (empty = fine). fetch(url) -> parsed /health (online)."""
    if not url:
        return ["no mock URL (the build log's START line has none; pass --mock-url)"]
    probs = []
    if not url.startswith("https://"):
        probs.append("mock URL %s is not https" % url)
    if "trycloudflare.com" in url or url.endswith(".invalid") or "localhost" in url or "example" in url:
        probs.append("mock URL %s is a temporary/local/placeholder address: deploy the Worker for real" % url)
    if fetch is not None and not probs:
        try:
            got = fetch(url.rstrip("/") + "/health")
        except Exception as e:                           # noqa: BLE001
            return ["mock %s/health did not answer: %s" % (url, str(e)[:200])]
        if not (isinstance(got, dict) and got.get("ok") is True):
            probs.append("mock %s/health is not ok: %s" % (url, str(got)[:200]))
    return probs


def _fetch_json(url, timeout=15):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; freya-builder/1.0)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def final_form(root, members, mock_url, name=FINAL):
    """The single-agent submission.json of the final."""
    return {"team": TEAM, "members": members, "repo": REPO, "branch": BRANCH, "commit": git_head(root),
            "run_command": FINAL_RUN_COMMAND, "workflow": "submission/%s.workflow.json" % name,
            "trace": "traces/%s.log" % name, "mock_url": mock_url}


def _members(arg, root):
    if arg:
        return [m.strip() for m in re.split(r"[,;]", arg) if m.strip()]
    try:
        old = json.loads((pathlib.Path(root) / "submission.json").read_text())
        return list(old.get("members") or [])
    except (OSError, ValueError):
        return []


# ----------------------------------------------------------------------------------------------- package

def package(root, name, run_dir=None, offline=False, fr=None, env=None):
    """Verify, scan and copy one hidden slot. -> the run facts. Raises SubmitError; copies nothing on failure."""
    root = pathlib.Path(root)
    log_path = root / "traces" / (name + ".log")
    rd = find_run_dir(root, name, log_path, run_dir)
    say("%s: run %s" % (name, rd))
    facts = verify_run(rd)
    if log_path.is_file():
        verify_log(log_path.read_text(errors="replace"), rd, facts["workflow_id"])
        log_src = log_path
    else:
        say("WARN %s is missing (the official trace is the tee'd stdout): using %s instead" % (log_path, rd / "trace.txt"))
        log_src = rd / "trace.txt"
    hits = scan_secrets([rd / "workflow.export.json", log_src, rd / "trace.jsonl"], env)
    if hits:
        raise SubmitError("secrets found, nothing copied:\n  " + "\n  ".join(hits[:20]))
    if not offline:
        v = check_published_bounded(fr or _kit_freya(root), facts["workflow_id"], facts["version"],
                                    facts["updated_at"])
        say("%s: workflow %s version %s is the published newest one, unchanged since the run"
            % (name, facts["workflow_id"], v))
    (root / "submission").mkdir(exist_ok=True)
    (root / "traces").mkdir(exist_ok=True)
    shutil.copyfile(rd / "workflow.export.json", root / "submission" / (name + ".workflow.json"))
    shutil.copyfile(rd / "trace.jsonl", root / "traces" / (name + ".trace.jsonl"))
    if log_src != log_path:
        shutil.copyfile(log_src, log_path)
    say("%s: wrote submission/%s.workflow.json, traces/%s.log, traces/%s.trace.jsonl (workflow %s, agent %s)"
        % (name, name, name, name, facts["workflow_id"], facts["agent_id"]))
    return facts


def main(argv=None, root=ROOT, fr=None):
    ap = argparse.ArgumentParser(prog="submit.py", description="Package a hidden-brief build and print the form JSON.")
    ap.add_argument("name", nargs="?", help="hidden slot name, e.g. hidden-1")
    ap.add_argument("--run-dir", default="", help="the run folder (default: the one traces/<name>.log names)")
    ap.add_argument("--offline", action="store_true", help="skip the read-only published-version check")
    ap.add_argument("--form", action="store_true", help="only print the form JSON for the files already in place")
    ap.add_argument("--members", default="", help="final: team members, comma-separated (kept in submission.json)")
    ap.add_argument("--mock-url", default="", help="final: the deployed mock (default: the build log's START line)")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    root = pathlib.Path(root)
    run_commit = None
    if args.name == FINAL:
        return _main_final(args, root, fr)
    if not args.form:
        if not args.name or not NAME_RE.match(args.name):
            say("give a hidden slot name like hidden-1 (or --form)")
            return 2
        try:
            run_commit = package(root, args.name, args.run_dir or None, args.offline, fr)["commit"]
        except (SubmitError, OSError, ValueError) as e:
            say("FAIL %s: %s" % (args.name, e))
            return 1
        except RuntimeError as e:                        # kit freya.api: HTTP error from the platform
            say("FAIL %s: Freya API error (%s): %s" % (args.name, str(e)[:300], OFFLINE_HINT))
            return 1
    for w in git_warnings(root, run_commit):
        say("WARN " + w)
    print(json.dumps(form(root), indent=1))
    return 0


def _main_final(args, root, fr):
    members = _members(args.members, root)
    if not members:
        say("FAIL final: give --members \"Name One, Name Two\" (kept in submission.json afterwards)")
        return 2
    log_path = root / "traces" / (FINAL + ".log")
    mock = (args.mock_url or "").rstrip("/") or (mock_url_from_log(log_path.read_text(errors="replace"))
                                                  if log_path.is_file() else None)
    probs = check_mock_url(mock, None if args.offline else _fetch_json)
    if probs:
        say("FAIL final: " + "; ".join(probs))
        return 1
    try:
        run_commit = package(root, FINAL, args.run_dir or None, args.offline, fr)["commit"]
    except (SubmitError, OSError, ValueError) as e:
        say("FAIL final: %s" % e)
        return 1
    except RuntimeError as e:                            # kit freya.api: HTTP error from the platform
        say("FAIL final: Freya API error (%s): %s" % (str(e)[:300], OFFLINE_HINT))
        return 1
    for w in git_warnings(root, run_commit):
        say("WARN " + w)
    sub = final_form(root, members, mock)
    (root / "submission.json").write_text(json.dumps(sub, indent=1, ensure_ascii=False) + "\n")
    say("wrote submission.json")
    print(json.dumps(sub, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
