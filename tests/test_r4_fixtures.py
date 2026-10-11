"""The four hidden-brief rehearsal fixtures end to end in the twin: the LLM-built Spec of each (tests/fixtures/
rehearsal/<fixture>.spec.json, built by builder/build.py --no-deploy in the rehearsal fix round) is compiled with the
current builder and runtime against the fixture's own (mutated) OpenAPI, and every scenario in testbed/<fixture>/
scenarios must pass (kit score_ledger + transcript checks). Fixture values live in tests/ and testbed/ only."""
import contextlib
import io
import json
import pathlib

import pytest

from builder import openapi_model
from builder.compiler import graph
from builder.pipeline import validate
from harness import scenarios

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = ["raw-a", "raw-ab", "mut-c", "mut-d"]


def _load(fx):
    with contextlib.redirect_stdout(io.StringIO()):
        cat = openapi_model.load(str(ROOT / "testbed" / fx / "openapi.json"))
        spec = json.loads((ROOT / "tests" / "fixtures" / "rehearsal" / (fx + ".spec.json")).read_text())
        r = validate.validate(spec, cat, brief_text=(ROOT / "testbed" / fx / "brief.md").read_text())
        wf, _w = graph.compile_workflow(r["spec"], cat)
    return r, cat, wf


@pytest.mark.parametrize("fx", FIXTURES)
def test_rehearsal_fixture_scenarios_pass(fx):
    r, cat, wf = _load(fx)
    assert r["errors"] == [], r["errors"]
    res = []
    with contextlib.redirect_stdout(io.StringIO()):
        for sc in scenarios.load(ROOT / "testbed" / fx / "scenarios"):
            out = scenarios.run(sc, wf, cat, r["spec"])
            res.append((sc["id"], out["pass"], out["failed"][:3]))
    bad = [x for x in res if not x[1]]
    assert len(res) >= 12 and not bad, bad
