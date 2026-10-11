"""Run the Turkish rehearsal twin scenarios (testbed/tr-final/twin/TRF-*.json) against a compiled build.

usage: .venv/bin/python testbed/tr-final/run_twin.py [build_dir] [scenario ids...]
build_dir defaults to testbed/tr-final/twin/build (a copy of runs/rh-trfinal/r20261011T153020Z).
Prints PASS/FAIL per scenario; for a FAIL the reasons, the ledger and the agent transcript.
"""
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from harness import scenarios as hs  # noqa: E402

TWIN_DIR = HERE / "twin"
DEFAULT_BUILD = TWIN_DIR / "build"


def load_build(build_dir=DEFAULT_BUILD):
    b = pathlib.Path(build_dir)
    rd = lambda n: json.loads((b / n).read_text())  # noqa: E731
    return rd("workflow.json"), rd("catalog.json"), rd("spec.json")


def load_scenarios(ids=None):
    out = hs.load(TWIN_DIR)
    return [s for s in out if not ids or s["id"] in ids]


def run_all(build_dir=DEFAULT_BUILD, ids=None):
    workflow, catalog, spec = load_build(build_dir)
    return [hs.run(s, workflow, catalog, spec) for s in load_scenarios(ids)]


def main(argv):
    build = DEFAULT_BUILD
    if argv and pathlib.Path(argv[0]).is_dir():
        build, argv = argv[0], argv[1:]
    results = run_all(build, set(argv) or None)
    for r in results:
        print("%s %s" % ("PASS" if r["pass"] else "FAIL", r["id"]))
        if r["pass"]:
            continue
        for f in r["failed"]:
            print("   - " + f)
        led = r["ledger"]
        print("   ledger: outcome=%r reason=%r promises=%s notes=%s callbacks=%s transfers=%s" % (
            led["outcome"], led["reason"], [(p["product_id"], p["amount"], p["date"]) for p in led["promises"]],
            led["notes"], led["callbacks"], led["transfers"]))
        print("   calls: " + ", ".join("%s%s" % (c["tool"], "" if c["status"] == 200 else "[%s]" % c["status"])
                                       for c in led["calls"]))
        for role, text in r["transcript"]:
            print("   %s: %s" % ("A" if role != "customer" else "C", text))
    n = sum(1 for r in results if r["pass"])
    print("%d/%d passed" % (n, len(results)))
    return 0 if n == len(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
