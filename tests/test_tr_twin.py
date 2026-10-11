"""Turkish rehearsal (testbed/tr-final) twin scenarios on the compiled build.

The build is read from testbed/tr-final/twin/build (a copy of runs/rh-trfinal2/r20261011T160923Z: the existing Spec
rebuilt offline with --spec-in), or from runs/ when the copy is missing; the test skips when neither exists. Every
scenario is asserted, including TRF-03 (half-day callback window) and TRF-06/06a (cards handled one at a time),
plus the spoken-output rules of a Turkish call (no English words, no raw ISO dates, the SMS sentence once).
"""
import re
import json
import pathlib

import pytest

from harness import scenarios as hs

ROOT = pathlib.Path(__file__).resolve().parent.parent
TWIN = ROOT / "testbed" / "tr-final" / "twin"
BUILDS = [TWIN / "build", ROOT / "runs" / "rh-trfinal2" / "r20261011T160923Z"]
PASSING = ["TRF-01", "TRF-02", "TRF-03", "TRF-04", "TRF-05", "TRF-06", "TRF-06a", "TRF-07", "TRF-08", "TRF-09",
           "TRF-10", "TRF-11", "TRF-12", "TRF-13"]
_ENGLISH = re.compile(r"\b(?:For your|and|the|your)\b")
_ISO = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
NEEDED = ("workflow.json", "catalog.json", "spec.json")


def _build():
    for b in BUILDS:
        if all((b / n).exists() for n in NEEDED):
            return [json.loads((b / n).read_text()) for n in NEEDED]
    return None


@pytest.fixture(scope="module")
def build():
    got = _build()
    if got is None:
        pytest.skip("the tr-final build r20261011T153020Z is not available")
    return got


@pytest.mark.parametrize("sid", PASSING)
def test_tr_twin_scenario_passes(build, sid):
    workflow, catalog, spec = build
    path = TWIN / (sid + ".json")
    if not path.exists():
        pytest.skip("scenario %s missing" % sid)
    r = hs.run(hs.load(path)[0], workflow, catalog, spec)
    assert r["pass"], "%s failed: %s\n%s" % (sid, r["failed"], "\n".join("%s: %s" % t for t in r["transcript"]))
    agent = [t for role, t in r["transcript"] if role != "customer"]
    sms = [x.get("text", "") for x in spec.get("required_sentences") or [] if x.get("trigger") == "after_promise_recorded"]
    for line in agent:
        assert not _ENGLISH.search(line) and not _ISO.search(line), (sid, line)
    for s_ in sms:
        assert sum(line.count(s_) for line in agent) <= 1, (sid, s_)
