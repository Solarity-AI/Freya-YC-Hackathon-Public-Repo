#!/usr/bin/env python3
"""Go/no-go for one build run, before it is submitted (docs/RUNBOOK.md).

    python3 tools/gonogo.py <run_dir> <tool_api.json|yaml>
    python3 tools/gonogo.py --log traces/hidden-1.log <tool_api>     # the run the tee'd log names

NO-GO (exit 1) when any of these fails: the build exited 0 and deployed; lint has 0 errors; the twin passed every
scenario it ran (and ran at least one); the smoke chat turn is 'ok'; every situation's outcome / reason / queue in
spec.json is in the enum the builder bound for it (catalog.json: outcome, close reason, queue, note reason), and each
bound enum is literally an enum of the hidden tool API file (a wrong binding or a stale catalog fails). Printed for a human look: the opening line, the smoke reply, the
enum values no situation uses, and the build time. Exit 2 on unreadable input.
"""
import argparse
import json
import pathlib
import re
import sys

# situation field -> the catalog enum (catalog.json "enums", bound by the builder from the tool API) it must come from
CHECKED_FIELDS = (("outcome", "outcome"), ("reason", "close_reason"), ("queue", "queue"), ("note_reason", "note_reason"))


def load_api(path):
    text = pathlib.Path(path).read_text()
    try:
        return json.loads(text)
    except ValueError:
        import yaml
        return yaml.safe_load(text)


def enum_sets(node, out=None):
    """Every enum in the document (inline or under components), as a list of sets of strings."""
    out = [] if out is None else out
    if isinstance(node, dict):
        if isinstance(node.get("enum"), list):
            out.append({str(v) for v in node["enum"]})
        for v in node.values():
            enum_sets(v, out)
    elif isinstance(node, list):
        for v in node:
            enum_sets(v, out)
    return out


def _records(rd):
    out = []
    for line in (rd / "trace.jsonl").read_text(errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def checks(rd, api_doc):
    """-> (failures, notes): lists of strings."""
    recs = _records(rd)
    summ = next((r for r in reversed(recs) if r.get("kind") == "SUMMARY"), {})
    fails, notes = [], []
    if summ.get("exit") != 0 or not summ.get("deployed"):
        fails.append("build exit %s, deployed=%s" % (summ.get("exit"), summ.get("deployed")))
    if summ.get("lint_errors") != 0:
        fails.append("lint errors: %s" % summ.get("lint_errors"))
    m = re.match(r"^(\d+)/(\d+)$", str(summ.get("twin", "")))
    if not m or m.group(1) != m.group(2) or m.group(2) == "0":
        fails.append("twin: %s (want n/n with n > 0)" % summ.get("twin"))
    if summ.get("smoke") != "ok":
        fails.append("smoke chat turn: %s" % summ.get("smoke"))
    smoke = next((r for r in recs if r.get("kind") == "FREYA" and r.get("msg") == "smoke chat turn ok"), {})
    notes.append("smoke reply: %s" % (smoke.get("reply") or "-"))
    spec = json.loads((rd / "spec.json").read_text())
    notes.append("opening line: %s" % ((spec.get("opening") or {}).get("line") or "-"))
    fails += _enum_checks(spec, json.loads((rd / "catalog.json").read_text()), api_doc, notes)
    notes.append("build time: %s s, workflow %s, agent %s, nodes %s" % (summ.get("build_s"), summ.get("workflow_id"),
                                                                       summ.get("agent_id"), summ.get("nodes")))
    return fails, notes


def _enum_checks(spec, catalog, api_doc, notes):
    """Situation values against the bound enums, and each bound enum against the hidden tool API itself."""
    fails, raw = [], enum_sets(api_doc)
    sits = [v for v in (spec.get("situations") or {}).values() if isinstance(v, dict)]
    for field, key in CHECKED_FIELDS:
        allowed = {str(v) for v in (catalog.get("enums") or {}).get(key) or []}
        used = {str(s[field]) for s in sits if s.get(field)}
        if not allowed:
            notes.append("%s: no enum in the tool API (used: %s)" % (field, ", ".join(sorted(used)) or "-"))
            continue
        if allowed not in raw:
            fails.append("bound %s enum %s is not an enum of the tool API file" % (key, sorted(allowed)))
        bad = sorted(used - allowed)
        if bad:
            fails.append("situation %s value(s) %s not in the tool API enum %s" % (field, bad, sorted(allowed)))
        if allowed - used:
            notes.append("%s values no situation uses: %s" % (field, ", ".join(sorted(allowed - used))))
    return fails


def run_dir_from_log(path):
    for line in pathlib.Path(path).read_text(errors="replace").splitlines():
        if " START " in line and "| build |" in line:
            m = re.search(r"\brun_dir=(.+?) model_default=", line) or re.search(r"\brun_dir=(\S+)", line)
            if m:
                return pathlib.Path(m.group(1))
    return None


def main(argv=None, out=sys.stdout):
    ap = argparse.ArgumentParser(prog="gonogo.py", description="Go/no-go checks for one build run.")
    ap.add_argument("paths", nargs="+", help="<run_dir> <tool_api>, or only <tool_api> with --log")
    ap.add_argument("--log", default="", help="a tee'd build log: check the run it names")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    try:
        if args.log:
            rd, api = run_dir_from_log(args.log), args.paths[0]
            if rd is None:
                raise ValueError("%s names no run_dir" % args.log)
        elif len(args.paths) == 2:
            rd, api = pathlib.Path(args.paths[0]), args.paths[1]
        else:
            raise ValueError("give <run_dir> <tool_api> (or --log LOG <tool_api>)")
        fails, notes = checks(pathlib.Path(rd), load_api(api))
    except Exception as e:                              # noqa: BLE001 - any unreadable input is a usage error
        print("gonogo: cannot check: %s: %s" % (type(e).__name__, e), file=out)
        return 2
    print("gonogo: run %s" % rd, file=out)
    for n in notes:
        print("  note  %s" % n, file=out)
    for f in fails:
        print("  FAIL  %s" % f, file=out)
    print("gonogo: %s" % ("NO-GO (%d)" % len(fails) if fails else "GO"), file=out)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
