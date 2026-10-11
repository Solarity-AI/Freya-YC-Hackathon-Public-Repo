#!/usr/bin/env python3
"""python3 builder/build.py <case_folder | case.zip> <mock_url> [options]          (the final's form)
   python3 builder/build.py <brief.md> [<brief.md> ...] <tool_api file> [<mock_url>] [options]  (docs/CONTRACTS.md F)

Brief(s) + tool API -> Spec -> workflow -> lint -> twin -> deploy -> export, with a full trace. Owner: agent 5.
Exit codes: 0 ok | 2 input | 3 spec invalid | 4 lint | 5 deploy | 6 budget.

CONTRACT NOTE (agent 5, simplest readings of ambiguous points):
- Trace files are runs/<slot>/<run_id>/trace.txt + trace.jsonl (the contract's names; never *.log).
- An unexpected internal exception exits 1 (the contract lists no code for it); it is traced as ERROR first.
- The twin (L2) is advisory: failing generated smoke scenarios are WARN events, they do not fail the build.
- --spec-in skips extraction and the critic; the Spec still goes through validate (defaults are filled).
- Re-extraction after validation errors and the critic's targeted re-extraction share ONE budget: at most one
  re-extraction round per build. The critic's patches are applied one by one and each is kept only if the
  validation error count does not grow.
- Interpretation overrides from the brief ride on facet F5 as an optional key (extract.FACET_OPTIONAL_KEYS).
- Budget: hard cap 26:00 -> exit 6 (and the slot's last published workflow is exported when a state file exists);
  soft cap 20:00 -> critic / re-extraction / twin are skipped.
- --dev: tracebacks are written into ERROR events (scrubbed), otherwise only the exception text.
- BUILD SPEED addendum: the critic (and its re-extraction) is opt-in (--critic), never on the default path; every
  stage is timed (STAGE events, `stages` in the summary); after deploy ONE live chat turn proves the agent starts
  (advisory, <= SMOKE_TIMEOUT_S = 60 s, --no-smoke turns it off).
- Default slot (no --slot): '<brief stem>-<sha8 of the inputs>-<UTC YYYYmmddTHHMMSS>', so EVERY run creates a fresh
  workflow named after its brief (docs/SYSTEM-DESIGN.md D13): hidden-1 and hidden-2 never collide, and a re-run can
  never overwrite the agent another run's trace describes (the rules forbid editing an agent after its run). One run
  costs one of the workspace's 200 workflows. --slot NAME updates the slot NAME in place instead.
- Preflight (builder.preflight): before any model call, a missing FREYA_API_KEY (unless --no-deploy), a missing
  Claude Agent SDK or a missing Claude login (unless --spec-in) exits 2 with a fix-it message.
- CASE FOLDER (ingest workstream): a folder or .zip of the bank's documents (md/docx/xlsx/pdf/json/csv/drawio...) plus
  the http(s) URL of our bank mock. builder.ingest reads + classifies every file (INPUT event per file: kind, reader,
  bytes); the tool catalog comes from builder.contract.build_catalog(case, mock_url, run_dir, budget) (folder OpenAPI,
  else <mock>/openapi.json, else derived from the contract documents); without that module the folder's OpenAPI or
  <mock>/openapi.json is loaded directly. Its servers are set to the mock so every tool call reaches it. A URL in
  the old form only re-points the tool API's server. The mock's /health is probed once (advisory INPUT role=mock event).
- The trace records the UTC start/end time, the builder's git commit, every model call (MODEL: model + purpose),
  what was created on Freya (FREYA 'built on Freya': workflow id, agent id, version, nodes, tools) and the smoke turn.
"""
import argparse
import datetime as _dt
import re
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))   # repo root, so `import builder.*` works

from builder import budget as budget_mod      # noqa: E402
from builder import paths, trace              # noqa: E402

EXIT_OK, EXIT_INPUT, EXIT_SPEC, EXIT_LINT, EXIT_DEPLOY, EXIT_BUDGET = 0, 2, 3, 4, 5, 6
EXIT_INTERNAL = 1
FLOW_MODE = "flow"            # internal: the case's services are not a collections call -> the call-flow pipeline


_OPENAPI_SUFFIXES = (".json", ".yaml", ".yml")
_INPUT_MSG = "input: %s"

class InputError(Exception):
    pass


# ----------------------------------------------------------------------------------------------- CLI

def _is_openapi(path):
    from builder import openapi_model
    return bool(openapi_model.is_openapi_file(path))   # never raises (False on any problem)


def parse_flags(text):
    """'k=v,k2=v2' -> dict. Raises InputError on a malformed item."""
    out = {}
    for item in (text or "").split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise InputError("bad --flags item %r (want k=v)" % item)
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def parse_args(argv):
    """-> namespace(briefs: [paths], api: path | None, mock_url, case, case_name, slot, out_dir, no_deploy, no_twin,
    no_critic, flags: dict, spec_in, dev). Two forms: <case folder | .zip> <mock_url> (api may stay None: resolved
    from the mock in the input stage), or brief file(s) + a tool API file (recognised by content,
    openapi_model.is_openapi_file, whatever its position/extension) and an optional mock URL.
    Raises InputError on bad input."""
    ap = argparse.ArgumentParser(prog="build.py", description="Case folder + mock URL (or brief(s) + tool API) -> "
                                                              "Freya workflow.")
    ap.add_argument("inputs", nargs="+", help="a case folder or .zip and the mock URL; or brief file(s) and the tool "
                                              "API file (any order)")
    ap.add_argument("--slot", default="")
    ap.add_argument("--out-dir", default=str(paths.RUNS))
    ap.add_argument("--no-deploy", action="store_true")
    ap.add_argument("--no-twin", action="store_true")
    ap.add_argument("--no-critic", action="store_true", help="kept for compatibility: the critic is off by default")
    ap.add_argument("--critic", action="store_true", help="opt in to the critic LLM review of a valid Spec")
    ap.add_argument("--no-smoke", action="store_true", help="skip the one live chat turn after deploy")
    ap.add_argument("--flags", default="")
    ap.add_argument("--spec-in", default="")
    ap.add_argument("--dev", action="store_true")
    ap.add_argument("--mode", default="auto", choices=("auto", "flow", "collections"),
                    help="auto: a call flow when the bank's services have no promise operation, else collections")
    try:
        ns = ap.parse_args(argv)
    except SystemExit as e:
        if not e.code:                          # --help printed the usage: a clean exit 0, not an input error
            raise
        raise InputError("bad arguments") from e
    _split_inputs(ns)
    ns.flags = parse_flags(ns.flags)
    od = pathlib.Path(ns.out_dir)
    if od.exists() and not od.is_dir():
        raise InputError("--out-dir is not a directory: %s" % ns.out_dir)
    if ns.spec_in and not pathlib.Path(ns.spec_in).is_file():
        raise InputError("--spec-in file not found: %s" % ns.spec_in)
    return ns


def _split_inputs(ns):
    """Fill ns.mock_url / zip_src / case / case_name / api / briefs from ns.inputs (see parse_args)."""
    from builder import ingest
    urls = [x for x in ns.inputs if ingest.is_url(x)]
    if len(urls) > 1:
        raise InputError("more than one URL given (expected one mock URL): %s" % ", ".join(urls))
    ns.mock_url = ingest.normalise_url(urls[0]) if urls else None
    rest = [x for x in ns.inputs if x not in urls]
    if not rest:
        raise InputError("no case folder or brief file given")
    missing = [p for p in rest if not pathlib.Path(p).exists()]
    if missing:
        raise InputError("input file(s) not found: %s" % ", ".join(missing))
    ns.zip_src, ns.case_name = None, None
    if len(rest) == 1 and pathlib.Path(rest[0]).is_file() and pathlib.Path(rest[0]).suffix.lower() == ".zip":
        try:
            root = ingest.extract_zip(rest[0])
        except (OSError, ingest.zipfile.BadZipFile) as e:
            raise InputError("cannot open the case zip %s: %s" % (rest[0], e)) from e
        ns.zip_src, ns.case_name = rest[0], pathlib.Path(rest[0]).stem
        rest = [str(root)]
    ns.case = rest[0] if len(rest) == 1 and pathlib.Path(rest[0]).is_dir() else None
    if ns.case:
        ns.case_name = ns.case_name or pathlib.Path(ns.case.rstrip("/\\")).name
        try:
            ns.api = _find_api(rest)
        except InputError as e:
            if "found 0" not in str(e):
                ns.api = _first_api(ns.case)              # several OpenAPI files in a case folder: the first wins
            elif ns.mock_url:
                ns.api = None                             # resolved from the mock / contract in the input stage
            else:
                raise InputError("the case folder has no OpenAPI file: give the mock URL too "
                                 "(build.py <case_folder> <mock_url>)") from e
        ns.briefs = [ns.case]
        return
    ns.api = _find_api(rest)
    ns.briefs = [p for p in rest if p != ns.api]
    if not ns.briefs:
        raise InputError("no brief file given")
    empty = [b for b in ns.briefs if pathlib.Path(b).is_file() and pathlib.Path(b).stat().st_size == 0]
    if empty:
        raise InputError("brief file is empty: %s" % empty[0])


def _first_api(folder):
    from builder import ingest
    for f in ingest.list_files(folder):
        if f.suffix.lower() in _OPENAPI_SUFFIXES and _is_openapi(str(f)):
            return str(f)
    return None


def _find_api(inputs):
    """The one tool API (OpenAPI) among the inputs, recognised by content; a folder of raw material may hold it."""
    apis = [p for p in inputs if pathlib.Path(p).is_file() and _is_openapi(p)]
    if not apis:
        for d in [p for p in inputs if pathlib.Path(p).is_dir()]:
            apis += [str(f) for f in sorted(pathlib.Path(d).rglob("*"))
                     if f.is_file() and f.suffix.lower() in _OPENAPI_SUFFIXES and _is_openapi(str(f))]
    if len(apis) != 1:
        raise InputError("expected exactly one tool API file (OpenAPI), found %d: %s" % (len(apis), apis))
    return apis[0]


def _input_bytes(briefs, api_path, mock_url=None):
    h = hashlib.sha256()
    from builder.pipeline.segment import expand_paths
    for p in expand_paths(list(briefs)) + ([api_path] if api_path else []):
        h.update(pathlib.Path(p).read_bytes())
    if mock_url:
        h.update(str(mock_url).encode())
    return h.hexdigest()


SLOT_PREFIX_ENV = "BUILDER_SLOT_PREFIX"     # rehearsals: e.g. 'fresh-' so a dry run never creates a 'hidden-1-*' slot


def _slot_safe(text, limit):
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in text)[:limit]


def default_slot(briefs, api_path, now=None, env=None, mock_url=None, name=None):
    """'[$BUILDER_SLOT_PREFIX]<first brief stem>-<sha8 of all input bytes>-<UTC YYYYmmddTHHMMSS>': a fresh workflow per
    run (see the module notes); the date keeps a run on another day at the same clock time from reusing an old slot's
    state file. The optional prefix (unset for the official runs) marks rehearsal workflows."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    env = os.environ if env is None else env
    first = pathlib.Path(str(briefs[0]).rstrip("/\\"))
    stem = _slot_safe(name or (first.name if first.is_dir() else first.stem) or "brief", 40)
    prefix = _slot_safe(env.get(SLOT_PREFIX_ENV) or "", 20)
    return "%s%s-%s-%s" % (prefix, stem, _input_bytes(briefs, api_path, mock_url)[:8], now.strftime("%Y%m%dT%H%M%S"))


def _utc_now():
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def git_commit(root=None, run=subprocess.run):
    """The builder's commit: '<sha>' or '<sha>+dirty' (uncommitted changes under the builder's code), else 'unknown'."""
    root = str(root or paths.ROOT)
    try:
        head = run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        if head.returncode != 0:
            return "unknown"
        st = run(["git", "-C", root, "status", "--porcelain", "--", "builder", "runtime", "harness", "kit",
                  "requirements.txt"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return head.stdout.strip() + ("+dirty" if st.stdout.strip() else "")


def workflow_counts(workflow):
    """-> {"nodes": steps incl. global nodes, "tool_calls": tool/API actions wired in, "tools": distinct API tools}."""
    wf = workflow or {}
    nodes = [n for key in ("nodes", "global_nodes") if isinstance(wf.get(key), dict) for n in wf[key].values()]
    actions = [a for n in nodes if isinstance(n, dict) for a in (n.get("pre_actions") or []) + (n.get("tools") or [])]
    actions += list(wf.get("tools") or [])
    names = [((a.get("function") or {}).get("name") or a.get("name")) for a in actions if isinstance(a, dict)]
    tools = sorted({n for n in names if n and n != "code_exec"})
    return {"nodes": len(nodes), "tool_calls": sum(1 for n in names if n and n != "code_exec"), "tools": tools}


# ----------------------------------------------------------------------------------------------- helpers

def _write_json(path, obj):
    pathlib.Path(path).write_text(json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=False) + "\n")


def _err(e, dev):
    if dev:
        return "%s: %s | %s" % (type(e).__name__, e, traceback.format_exc()[-1500:])
    return "%s: %s" % (type(e).__name__, str(e)[:500])


_NONE_ITEM = "- none"


def _decisions_md(spec, extra):
    meta = (spec or {}).get("meta") or {}
    out = ["# Build decisions", ""]
    for title, key in (("Decisions", "decisions"), ("Defaults applied", "defaults_applied"),
                       ("Warnings", "warnings")):
        items = meta.get(key) or []
        out.append("## %s (%d)" % (title, len(items)))
        out += ["- %s" % x for x in items] or [_NONE_ITEM]
        out.append("")
    rr = meta.get("residual_rules") or []
    out.append("## Residual rules (%d)" % len(rr))
    out += ["- [%s] %s" % (r.get("class"), r.get("text")) for r in rr] or [_NONE_ITEM]
    out.append("")
    for title, items in extra:
        out.append("## %s (%d)" % (title, len(items)))
        out += ["- %s" % x for x in items] or [_NONE_ITEM]
        out.append("")
    return "\n".join(out)


def _export_last_published(slot, run_dir):
    """Budget exit: export the slot's last published workflow if a state file knows it. Never raises."""
    try:
        from builder import deploy
        key = getattr(deploy, "_safe_slot", lambda s: s)(slot)
        sf = paths.STATE / (key + ".json")
        if not sf.exists():
            trace.event("BUDGET", "no published workflow for this slot to export")
            return None
        state = json.loads(sf.read_text())
        ent = state.get(key) if isinstance(state, dict) else None
        wid = ent.get("workflow_id") if isinstance(ent, dict) else None
        if not wid:
            return None
        p = deploy.export(wid, pathlib.Path(run_dir) / "workflow.export.json")
        trace.event("EXPORT", "last published workflow exported", workflow_id=wid, path=str(p))
        return p
    except Exception as e:                              # noqa: BLE001
        trace.event("WARN", "export of last published failed: %s" % str(e)[:200])
        return None


def _at(spec, pointer):
    """Value at a JSON pointer (None when missing)."""
    cur = spec
    for p in [x.replace("~1", "/").replace("~0", "~") for x in str(pointer or "").split("/")[1:] if x != ""]:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        elif isinstance(cur, list) and p.isdigit() and int(p) < len(cur):
            cur = cur[int(p)]
        else:
            return None
    return json.dumps(cur, sort_keys=True)


def _copy_pointers(src, dst, pointers):
    """dst with the values at `pointers` taken from src (each pointer's parent must exist in dst)."""
    out = json.loads(json.dumps(dst))
    for ptr in pointers:
        parts = [x.replace("~1", "/").replace("~0", "~") for x in str(ptr).split("/")[1:] if x != ""]
        if parts:
            _copy_one(src, out, parts)
    return out


def _copy_one(src, dst, parts):
    s, d = src, dst
    last = len(parts) - 1
    for i, p in enumerate(parts):
        key = int(p) if isinstance(d, list) and p.isdigit() else p
        try:
            if i == last:
                d[key] = json.loads(json.dumps(s[key]))
                return
            s, d = s[key], d[key]
        except (KeyError, IndexError, TypeError):
            return


def _count_errors_list(catalog, brief_text, examples=None):
    from builder.pipeline import validate as V

    def check(spec):
        return V.validate(spec, catalog, brief_text=brief_text, examples=examples)["errors"]
    return check


def _count_errors(catalog, brief_text, examples=None):
    from builder.pipeline import validate as V

    def check(spec):
        r = V.validate(spec, catalog, brief_text=brief_text, examples=examples)
        return len(r["errors"])
    return check


# ----------------------------------------------------------------------------------------------- stages

class Stages:
    """Wall-clock per build stage (BUILD SPEED item 1): one STAGE trace event per stage and summary['stages']."""

    def __init__(self, summary=None):
        self.secs = {}
        if summary is not None:
            summary["stages"] = self.secs
        self.cur, self.t0 = None, 0.0

    def start(self, name):
        self.stop()
        self.cur, self.t0 = name, time.monotonic()

    def stop(self):
        if self.cur is None:
            return
        s = time.monotonic() - self.t0
        self.secs[self.cur] = round(self.secs.get(self.cur, 0.0) + s, 1)
        trace.event("STAGE", self.cur, seconds=round(s, 1))
        self.cur = None


def stage_spec(args, bdoc, catalog, bud, run_dir, stg=None):
    """extract -> validate -> (re-extract once) -> critic (opt-in). -> (spec, errors)."""
    from builder.pipeline import extract
    stg = stg or Stages()
    ex = {"bdoc": bdoc, "catalog": catalog, "bud": bud, "text": bdoc["text"], "examples": bdoc.get("examples") or []}
    stg.start("extract")
    if args.spec_in:
        draft = json.loads(pathlib.Path(args.spec_in).read_text())
        trace.event("EXTRACT", "spec loaded from --spec-in (extraction skipped)", path=args.spec_in)
    else:
        bud.check("extract")
        draft = extract.extract(bdoc, catalog, bud)
    _write_json(run_dir / "spec.draft.json", draft)
    failed = extract.failed_facets(draft)
    stg.start("validate")
    res = _validate_traced(ex, extract.clean_meta(draft), warnings=True)
    reextracted = False
    if (res["errors"] or failed) and not args.spec_in and bud.go("reextract"):
        res, reextracted = _reextract(ex, draft, res, failed, stg)
    # BUILD SPEED item 2: the critic is opt-in; validation errors are repaired by the targeted re-extraction above
    if getattr(args, "critic", False) and not args.no_critic and not args.spec_in and not res["errors"] \
            and bud.go("critic"):
        stg.start("critic")
        res = _critic_round(args, ex, res, reextracted)
    stg.stop()
    return res["spec"], res["errors"]


def _validate_traced(ex, spec, warnings=False):
    from builder.pipeline import validate as V
    res = V.validate(spec, ex["catalog"], brief_text=ex["text"], examples=ex["examples"])
    for e in res["errors"][:40]:
        trace.event("VALIDATE", "error: " + e)
    for w in (res.get("warnings") or [])[:40] if warnings else []:
        trace.event("VALIDATE", "warning: " + str(w))
    return res


def _reextract(ex, draft, res, failed, stg):
    """One targeted re-extraction of the facets with errors. -> (res, reextracted)."""
    from builder.pipeline import extract, validate as V
    facets = sorted(set(V.facets_with_errors(res["errors"])) | set(failed))
    if not facets:
        return res, False
    stg.start("reextract")
    trace.event("EXTRACT", "targeted re-extraction", facets=facets, errors=len(res["errors"]))
    draft2 = extract.extract(ex["bdoc"], ex["catalog"], ex["bud"], only=facets, feedback=list(res["errors"]),
                             base=draft)
    res2 = V.validate(extract.clean_meta(draft2), ex["catalog"], brief_text=ex["text"], examples=ex["examples"])
    if len(res2["errors"]) <= len(res["errors"]):
        res = res2
        trace.event("VALIDATE", "re-extraction kept", errors=len(res2["errors"]))
    else:
        trace.event("VALIDATE", "re-extraction reverted (more errors)", errors=len(res2["errors"]))
    for e in res["errors"][:40]:
        trace.event("VALIDATE", "error: " + e)
    return res, True


def _critic_round(args, ex, res, reextracted):
    """Opt-in critic: patches kept only when the Spec stays valid. -> the validation result to use."""
    from builder.pipeline import critic, validate as V
    try:
        cr = critic.critique(ex["bdoc"], res["spec"], ex["catalog"], ex["bud"])
        check = _count_errors(ex["catalog"], ex["text"], ex["examples"])
        spec2, applied, rejected = critic.apply_and_check(res["spec"], cr["issues"], check)
        trace.event("CRITIC", "patches applied=%d rejected=%d" % (len(applied), len(rejected)))
        for it in rejected:
            trace.event("CRITIC", "rejected: %s" % it.get("problem", "")[:160], why=it.get("why"),
                        pointer=it.get("pointer"))
        need = [it for it in rejected if it.get("why") == "no usable op"]
        if need and not reextracted and ex["bud"].go("reextract"):
            spec2 = _critic_reextract(ex, need, spec2)
        final = V.validate(spec2, ex["catalog"], brief_text=ex["text"], examples=ex["examples"])
        if final["errors"]:
            trace.event("CRITIC", "critic result reverted (validation errors)", errors=len(final["errors"]))
            return res
        meta = final["spec"].setdefault("meta", {})
        meta.setdefault("residual_rules", []).extend(
            {"text": r["text"], "class": r.get("class", "flow"), "bound_to": "critic"}
            for r in cr.get("residual") or [] if isinstance(r, dict) and r.get("text"))
        meta.setdefault("decisions", []).extend("critic: %s (%s)" % (it.get("problem"), it.get("pointer"))
                                                for it in applied)
        return final
    except Exception as e:                              # noqa: BLE001 - the critic is optional
        trace.event("WARN", "critic failed, Spec kept: %s" % _err(e, args.dev))
        return res


def _critic_reextract(ex, need, spec2):
    """Critic-driven re-extraction of the flagged facets; only the flagged values are taken over."""
    from builder.pipeline import extract, validate as V
    facets = V.facets_with_errors([it.get("pointer", "") for it in need])
    if not facets:
        return spec2
    trace.event("EXTRACT", "critic-driven re-extraction", facets=facets)
    draft3 = extract.extract(ex["bdoc"], ex["catalog"], ex["bud"], only=facets, feedback=need, base=spec2)
    res3 = V.validate(extract.clean_meta(draft3), ex["catalog"], brief_text=ex["text"], examples=ex["examples"])
    changed = [p for p in (it.get("pointer", "") for it in need) if _at(res3["spec"], p) != _at(spec2, p)]
    if res3["errors"]:
        trace.event("CRITIC", "critic re-extraction reverted", errors=len(res3["errors"]))
        return spec2
    if not changed:
        trace.event("CRITIC", "critic re-extraction ignored (the flagged values did not change)")
        return spec2
    # take only the flagged values: the rest of the re-extracted facet was not reviewed
    return _copy_pointers(res3["spec"], spec2, changed)


def run(args):
    """The whole pipeline under budget.Budget; returns an exit code. Writes runs/<slot>/<run_id>/... ."""
    bud = budget_mod.Budget()
    slot = args.slot or default_slot(args.briefs, args.api, mock_url=getattr(args, "mock_url", None),
                                     name=getattr(args, "case_name", None))
    run_id = _dt.datetime.now(_dt.timezone.utc).strftime("r%Y%m%dT%H%M%SZ")
    run_dir = pathlib.Path(args.out_dir) / slot / run_id
    try:
        trace.init(run_dir)
    except OSError as e:
        _input_error_trace("cannot create the run folder %s: %s" % (run_dir, e))
        return EXIT_INPUT
    summary = {"slot": slot, "run_id": run_id, "run_dir": str(run_dir), "started_at": _utc_now(), "exit": None}
    code = EXIT_INTERNAL
    try:
        code = _run(args, bud, slot, run_dir, summary)
    except budget_mod.BudgetExceeded as e:
        trace.event("BUDGET", "hard cap reached: %s" % e)
        _export_last_published(slot, run_dir)
        code = EXIT_BUDGET
    except Exception as e:                              # noqa: BLE001
        trace.event("ERROR", "internal error: " + _err(e, args.dev))
        code = EXIT_INTERNAL
    finally:
        stg = summary.pop("_stg", None)
        if stg is not None:
            stg.stop()
        summary["exit"] = code
        summary["ended_at"] = _utc_now()
        summary["build_s"] = round(trace.elapsed(), 1)
        summary["budget"] = bud.snapshot()
        trace.event("END", "exit %d" % code, **{k: v for k, v in summary.items()
                                                 if k in ("slot", "exit", "ended_at", "build_s")})
        trace.summary(**summary)
        trace.close()
    return code


def _run(args, bud, slot, run_dir, summary):
    from builder import llm
    stg = Stages(summary)
    summary["_stg"] = stg
    trace.event("START", "build", argv=sys.argv[1:], slot=slot, run_dir=str(run_dir), model_default=llm.DEFAULT_MODEL,
                effort_default=llm.DEFAULT_EFFORT, facet_overrides=llm.facet_overrides(), critic=bool(args.critic),
                started_at=summary.get("started_at"), commit=git_commit(), **input_fields(args))
    from builder import preflight
    try:
        facts = preflight.check(need_llm=not args.spec_in and llm.uses_sdk(), need_freya=not args.no_deploy)
    except preflight.PreflightError as e:
        trace.event("ERROR", "preflight: %s" % e)
        return EXIT_INPUT
    trace.event("START", "preflight ok", **facts)
    if getattr(args, "case", None) and getattr(args, "mode", "auto") == "flow":
        trace.event("DECISION", "mode flow (--mode flow)")
        return _flow_from_case(args, bud, slot, run_dir, summary, stg, None)
    stg.start("input")
    code, catalog, bdoc = _stage_inputs(args, run_dir, bud)
    if code == FLOW_MODE:
        return _flow_from_case(args, bud, slot, run_dir, summary, stg, args._flow_case)
    if code is not None:
        return code
    spec, errors = stage_spec(args, bdoc, catalog, bud, run_dir, stg)
    stg.start("spec_out")
    spec = _stage_spec_out(spec, errors, catalog, bdoc, run_dir, summary)
    if spec is None:
        return EXIT_SPEC
    bud.check("compile")
    stg.start("compile")
    from builder.compiler import graph
    try:
        workflow, wiring = graph.compile_workflow(spec, catalog, args.flags or None)
    except Exception as e:                              # noqa: BLE001 - e.g. a ctl code size / snippet failure
        trace.event("ERROR", "compile failed: " + _err(e, args.dev))
        return EXIT_LINT
    _write_json(run_dir / "wiring.json", wiring)
    _write_json(run_dir / "workflow.json", workflow)
    summary.update(workflow_counts(workflow))
    trace.event("COMPILE", "workflow compiled", nodes=len(workflow.get("nodes") or {}),
                bytes=len(json.dumps(workflow)))
    stg.start("lint")
    if _stage_lint(workflow, catalog, spec, wiring, summary):
        return EXIT_LINT
    stg.start("twin")
    if not args.no_twin and bud.go("twin"):
        _stage_twin(args, spec, catalog, workflow, run_dir, summary)
    if bud.past_hard():
        # the workflow is compiled and lint-clean: deploying takes seconds, so the hard cap only stops new LLM work
        trace.event("BUDGET", "hard cap passed after compile+lint; deploying the finished workflow anyway")
    stg.start("deploy")
    return _stage_deploy(args, slot, run_dir, workflow, spec, summary, stg)


def _flow_from_case(args, bud, slot, run_dir, summary, stg, case):
    """Flow mode: read the service contract (the folder's OpenAPI, else derived from the contract documents; the
    derivation is cached, so a collections attempt before costs nothing twice) and build the call flow."""
    from builder import contract, openapi_model
    if case is None:
        stg.start("input")
        case = _load_case_traced(args, run_dir)
        if case is None:
            return EXIT_INPUT
    if not (hasattr(contract, "_coerce_case") and hasattr(contract, "_source_doc")):
        trace.event("ERROR", "service contract unusable: no contract stage for a call flow")
        return EXIT_INPUT
    cc = contract._coerce_case(case, args.mock_url)
    try:
        doc, source, _ = contract._source_doc(cc, args.mock_url, False, True, bud)
    except openapi_model.CatalogError:
        try:                                            # no contract in the folder: the mock's own openapi.json
            doc, source, _ = contract._source_doc(cc, args.mock_url, None, True, bud)
        except openapi_model.CatalogError as e:
            trace.event("ERROR", "service contract unusable: %s" % e)
            return EXIT_INPUT
    trace.event("INPUT", "service contract read", role="tool_api", source=source,
                operations=sum(len([m for m in (v or {}) if m in openapi_model.HTTP_METHODS])
                               for v in (doc.get("paths") or {}).values() if isinstance(v, dict)))
    return _run_flow(args, bud, slot, run_dir, summary, stg, case, doc)


def _run_flow(args, bud, slot, run_dir, summary, stg, case, doc):
    from builder.compiler import flowgraph
    from builder.pipeline import flowspec
    ops = flowgraph.flow_ops(doc, args.mock_url or "")
    _write_json(run_dir / "openapi.json", doc)
    _write_json(run_dir / "ops.json", ops)
    for k, op in sorted(ops.items()):
        trace.event("CATALOG", "%s %s %s" % (k, op["method"], op["path"]), params=sorted(op["params"]),
                    body=sorted(op["body"]), response=op["res"])
    stg.start("spec")
    if args.spec_in:
        spec = json.loads(pathlib.Path(args.spec_in).read_text())
        errs = flowspec.check(spec, ops)
        trace.event("EXTRACT", "flow spec loaded from --spec-in", path=args.spec_in)
    else:
        try:
            spec, errs = flowspec.extract(case["docs"], ops, budget=bud)
        except Exception as e:                          # noqa: BLE001
            trace.event("ERROR", "flow extraction failed: %s" % _err(e, args.dev))
            return EXIT_SPEC
    _write_json(run_dir / "spec.json", spec)
    F = spec.get("flow") or {}
    trace.event("SPEC", "flow spec", language=(spec.get("bank") or {}).get("language"), nodes=len(F.get("nodes") or {}),
                global_intents=len(F.get("global") or []),
                variables=[d.get("name") for d in (spec.get("call_variables") or {}).get("declared") or []])
    for d in (spec.get("meta") or {}).get("decisions") or []:
        trace.event("DECISION", str(d)[:400])
    for e in errs:
        trace.event("VALIDATE", "error: " + str(e)[:400])
    if errs:
        return EXIT_SPEC
    stg.start("compile")
    try:
        workflow, wiring = flowgraph.compile_flow(spec, ops)
    except Exception as e:                              # noqa: BLE001
        trace.event("ERROR", "compile failed: " + _err(e, args.dev))
        return EXIT_LINT
    _write_json(run_dir / "wiring.json", wiring)
    _write_json(run_dir / "workflow.json", workflow)
    summary.update(workflow_counts(workflow))
    trace.event("COMPILE", "flow workflow compiled", nodes=len(workflow.get("nodes") or {}),
                bytes=len(json.dumps(workflow)), ctl_code=len(workflow["nodes"]["ctl"]["pre_actions"][0]["function"][
                    "parameters"]["properties"]["code"]["default"]))
    stg.start("lint")
    probs = flowgraph.check(workflow, wiring, spec)
    for p in probs:
        trace.event("LINT", "error: " + p)
    summary["lint_errors"] = len(probs)
    if probs:
        return EXIT_LINT
    trace.event("LINT", "flow workflow: 0 errors")
    stg.start("deploy")
    return _stage_deploy(args, slot, run_dir, workflow, spec, summary, stg)


def input_fields(args):
    """START trace fields describing the input form."""
    case = getattr(args, "case", None)
    out = {"input_form": "case_folder" if case else "files", "mock_url": getattr(args, "mock_url", None)}
    if case:
        out["case"] = case
    if getattr(args, "zip_src", None):
        out["zip"] = args.zip_src
    return out


def _stage_inputs(args, run_dir, bud=None):
    """Trace the inputs, load the tool API catalog and segment the brief(s). -> (exit code or None, catalog, bdoc).
    Case folder: builder.contract.build_catalog(case, mock_url, run_dir, budget=bud) binds the service contract when
    that module provides it; otherwise the folder's OpenAPI / <mock>/openapi.json is loaded by openapi_model."""
    case = None
    if getattr(args, "case", None):
        case = _load_case_traced(args, run_dir)
        if case is None:
            return EXIT_INPUT, None, None
        code, catalog = _case_catalog(args, case, run_dir, bud)
        if code is not None:
            return code, None, None
    else:
        for p in list(args.briefs) + [args.api]:
            pp = pathlib.Path(p)
            if pp.is_file():
                trace.event("INPUT", str(p), sha256=hashlib.sha256(pp.read_bytes()).hexdigest(),
                            bytes=pp.stat().st_size, role="tool_api" if p == args.api else "brief")
            else:
                trace.event("INPUT", str(p), role="brief_dir")
        if getattr(args, "mock_url", None):
            args.api = _api_on_mock(args.api, args.mock_url, run_dir)
            trace.event("INPUT", str(args.api), role="tool_api", source="server set to the mock",
                        mock_url=args.mock_url)
        from builder import openapi_model
        try:
            catalog = openapi_model.load(args.api)
        except openapi_model.CatalogError as e:
            trace.event("ERROR", "tool API unusable: %s" % e)
            return EXIT_INPUT, None, None
    _write_json(run_dir / "catalog.json", catalog)
    trace.event("CATALOG", "tools bound", tools=sorted(catalog.get("tools") or {}),
                identity_mode=catalog.get("identity_mode"), warnings=len(catalog.get("warnings") or []),
                server=catalog.get("server"))
    from builder.pipeline import segment
    try:
        bdoc = segment.from_case(case) if case is not None else segment.segment(args.briefs)
    except OSError as e:
        trace.event("ERROR", "cannot read brief: %s" % e)
        return EXIT_INPUT, None, None
    if not bdoc["docs"] or not bdoc["text"].strip():
        trace.event("ERROR", "brief input is empty")
        return EXIT_INPUT, None, None
    for d in bdoc["docs"]:
        trace.event("SEGMENT", d.get("rel") or d["path"], doc_kind=d["kind"], role=d.get("role"), lines=len(d["lines"]),
                    sections=len(d["sections"]), tables=len(d["tables"]))
    return None, catalog, bdoc


def _load_case_traced(args, run_dir):
    """builder.ingest.load_case + one INPUT event per file (kind, reader, size) + WARN per problem. -> case | None."""
    from builder import ingest
    try:
        case = ingest.load_case(args.case, args.mock_url)
    except (ingest.CaseError, OSError) as e:
        trace.event("ERROR", "cannot read the case folder: %s" % e)
        return None
    for f in case["files"]:
        trace.event("INPUT", f["rel"], doc_kind=f["kind"], reader=f["reader"], bytes=f["bytes"], chars=f["chars"],
                    status=f["status"], why=f.get("note") or "")
    for w in case["warnings"]:
        trace.event("WARN", _INPUT_MSG % w)
    _write_json(run_dir / "case_manifest.json", {k: case[k] for k in ("root", "source", "mock_url", "openapi_path",
                                                                       "files", "warnings")})
    (run_dir / "case_manifest.txt").write_text("\n".join(ingest.manifest_lines(case)) + "\n")
    if not any(d["text"].strip() for d in case["docs"]):
        trace.event("ERROR", "the case folder has no readable document")
        return None
    _probe_mock(args.mock_url)
    return case


def _probe_mock(mock_url):
    """Advisory: GET <mock>/health once (a wrong or unreachable mock fails every conversation)."""
    if not mock_url:
        return
    from builder import ingest
    try:
        got = ingest.fetch_json(mock_url + "/health", timeout=8)
        trace.event("INPUT", "mock reachable", role="mock", url=mock_url, health=str(got)[:200])
    except Exception as e:                              # noqa: BLE001 - advisory
        trace.event("WARN", "mock %s/health not reachable: %s" % (mock_url, str(e)[:200]))


def _case_catalog(args, case, run_dir, bud):
    """Case form: -> (exit code or None, ToolCatalog). contract.build_catalog when present, else the fallback."""
    from builder import openapi_model
    try:
        from builder import contract                    # the contract workstream (optional module)
    except ImportError:
        contract = None
    build_catalog = getattr(contract, "build_catalog", None)
    if build_catalog is not None:
        try:
            catalog = build_catalog(case, args.mock_url, run_dir, budget=bud)
        except openapi_model.CatalogError as e:
            if getattr(args, "mode", "auto") == "auto" and "no service contract" not in str(e):
                trace.event("DECISION", "mode flow: the services are not a collections call (%s)" % str(e)[:300])
                args._flow_case = case
                return FLOW_MODE, None
            trace.event("ERROR", "service contract unusable: %s" % e)
            return EXIT_INPUT, None
        info = catalog.get("contract") or {}
        if getattr(args, "mode", "auto") == "auto" and "create_promise" in (info.get("absent") or []):
            trace.event("DECISION", "mode flow: the contract has no promise service, so this is not a collections "
                                    "call; the bank's call flow is built instead")
            args._flow_case = case
            return FLOW_MODE, None
        args.api = info.get("openapi_path") or args.api
        trace.event("INPUT", str(args.api), role="tool_api", source=info.get("source"), mock_url=args.mock_url)
        return None, catalog
    api, source = _case_tool_api(args, case, run_dir)
    if not api:
        trace.event("ERROR", "no tool API: %s" % source)
        return EXIT_INPUT, None
    args.api = api
    trace.event("INPUT", str(api), role="tool_api", source=source, mock_url=args.mock_url)
    try:
        return None, openapi_model.load(api)
    except openapi_model.CatalogError as e:
        trace.event("ERROR", "tool API unusable: %s" % e)
        return EXIT_INPUT, None


def _case_tool_api(args, case, run_dir):
    """Fallback without builder.contract: -> (OpenAPI path with servers = mock, source). Folder file, else
    <mock>/openapi.json; (None, why) when neither exists."""
    from builder import ingest
    if args.api:
        return (_api_on_mock(args.api, args.mock_url, run_dir) if args.mock_url else args.api), args.api
    path, source = ingest.tool_api_for(case, run_dir)
    return path, (source if path else "%s; no OpenAPI in the case folder and no contract stage" % source)


def _api_on_mock(api_path, mock_url, run_dir):
    """Copy of the tool API with servers = [mock_url] in run_dir/tool_api.json (unparseable: the original path)."""
    from builder import ingest, openapi_model
    try:
        doc = openapi_model._parse_text(pathlib.Path(api_path).read_text(errors="replace"))
    except OSError:
        return api_path
    if not isinstance(doc, dict):
        return api_path
    out = pathlib.Path(run_dir) / "tool_api.json"
    out.write_text(json.dumps(ingest.with_server(doc, mock_url), indent=1, ensure_ascii=False) + "\n")
    return str(out)


def _stage_spec_out(spec, errors, catalog, bdoc, run_dir, summary):
    """Write the Spec and its decisions; degrade an invalid Spec to validity. -> the Spec, or None (exit 3)."""
    _write_json(run_dir / "spec.json", spec)
    (run_dir / "decisions.md").write_text(_decisions_md(spec, [("Validation errors", errors)]))
    summary["spec_errors"] = len(errors)
    summary["defaults_applied"] = len(((spec.get("meta") or {}).get("defaults_applied")) or [])
    summary["residual_rules"] = len(((spec.get("meta") or {}).get("residual_rules")) or [])
    if errors:
        trace.event("WARN", "invalid Spec: %d errors; trying a degraded Spec" % len(errors), first=errors[:5])
        from builder.pipeline import degrade, validate as V
        check = _count_errors_list(catalog, bdoc["text"], bdoc.get("examples") or [])
        spec2, errors2, applied = degrade.degrade(spec, errors, check)
        if errors2:
            summary["spec_errors"] = len(errors2)
            trace.event("SPEC", "invalid Spec: %d errors" % len(errors2), first=errors2[:5], degrade_steps=len(applied))
            return None
        spec = V.validate(spec2, catalog, brief_text=bdoc["text"], examples=bdoc.get("examples") or [])["spec"]
        spec.setdefault("meta", {}).setdefault("decisions", []).extend("degraded: " + a for a in applied)
        _write_json(run_dir / "spec.json", spec)
        summary["degraded"] = True
        summary["degrade_steps"] = applied
        summary["spec_errors"] = 0
        trace.event("WARN", "Spec degraded to validity", steps=applied)
    trace.event("SPEC", "valid", sha256=hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:16],
                intents=len(spec.get("intents") or []), situations=len(spec.get("situations") or {}),
                bands=len(spec.get("bands") or []))
    return spec


def _stage_lint(workflow, catalog, spec, wiring, summary):
    """-> True when lint found errors."""
    from builder.compiler import lint
    findings = lint.lint(workflow, catalog, spec, wiring)
    errs = [f for f in findings if f.get("level") == "error"]
    for f in findings[:60]:
        trace.event("LINT", "%s %s @%s: %s" % (f.get("level"), f.get("rule"), f.get("where"), f.get("msg")))
    summary["lint_errors"] = len(errs)
    summary["lint_warnings"] = len(findings) - len(errs)
    return bool(errs)


def _stage_twin(args, spec, catalog, workflow, run_dir, summary):
    """L2 twin on generated smoke scenarios (advisory: failures are WARN events)."""
    try:
        from harness import scenarios
        scen = scenarios.generate(spec, catalog)
        rep = scenarios.run_suite(scen, workflow, catalog, spec)
        _write_json(run_dir / "twin_report.json", rep)
        for r in rep.get("results") or []:
            trace.event("TWIN", "%s %s" % ("PASS" if r.get("pass") else "FAIL", r.get("id", "")), where="LOCAL",
                        failed=(r.get("failed") or [])[:3])
        summary["twin"] = "%s/%s" % (rep.get("passed"), rep.get("total"))
        if not rep.get("total"):
            trace.event("WARN", "no smoke scenarios: the Spec's calendar/identity shape gave the generator nothing to "
                        "run, so the twin checked nothing", where="LOCAL")
        elif rep.get("passed") != rep.get("total"):
            trace.event("WARN", "twin smoke scenarios failing", where="LOCAL", passed=rep.get("passed"),
                        total=rep.get("total"))
    except Exception as e:                              # noqa: BLE001 - advisory stage
        trace.event("WARN", "twin stage failed: %s" % _err(e, args.dev), where="LOCAL")
        summary["twin"] = "error"


def _stage_deploy(args, slot, run_dir, workflow, spec, summary, stg):
    """Deploy + export + read-back check, then the one-turn smoke check. -> exit code."""
    if args.no_deploy:
        trace.event("DEPLOY", "skipped (--no-deploy)")
        summary["deployed"] = False
        return EXIT_OK
    from builder import deploy
    try:
        res = deploy.deploy(workflow, slot, run_dir, dry_run=True)
    except deploy.DeployError as e:
        trace.event("ERROR", "deploy failed: %s" % str(e)[:500])
        return EXIT_DEPLOY
    summary.update({"deployed": True, "workflow_id": res.get("workflow_id"), "agent_id": res.get("agent_id"),
                    "version": res.get("version"), "export": res.get("export_path"),
                    "readback_diff": len(res.get("diff") or [])})
    trace.event("FREYA", "built on Freya", workflow_id=res.get("workflow_id"), agent_id=res.get("agent_id"),
                version=res.get("version"), created=res.get("created"), nodes=summary.get("nodes"),
                tools=len(summary.get("tools") or []), where="ON-AGENT")
    trace.event("EXPORT", "export written", path=res.get("export_path"))
    structural = [d for d in (res.get("diff") or []) if not _cosmetic_diff(d)]
    if structural or res.get("llm_ok") is False:
        trace.event("ERROR", "read-back differs from what was sent: %d structural difference(s)" % len(structural),
                    first=structural[:5], llm_ok=res.get("llm_ok"))
        return EXIT_DEPLOY
    if not args.no_smoke:
        stg.start("smoke")
        summary["smoke"] = smoke_turn(res.get("workflow_id"), spec)
    return EXIT_OK


SMOKE_TIMEOUT_S = 60          # 10 s timed out on 7 of 12 live builds of 2026-10-11; one fresh-copy turn then took 27 s


def smoke_turn(workflow_id, spec, chat=None):
    """BUILD SPEED item 3: one live chat turn ('Hello?') proves the published agent starts. Advisory: -> 'ok' or
    'warn: ...' (a WARN event; the exit code does not change). The call is ended right after."""
    if chat is None:
        from harness import chat_e2e as chat
    clarify = str(((spec or {}).get("lines") or {}).get("clarify") or "").strip()
    call_id = None
    try:
        with chat.chat_lock(wait_s=30):
            try:
                reply, call_id = chat.chat_turn(workflow_id, "Hello?", {}, None, SMOKE_TIMEOUT_S)
            finally:
                if call_id:
                    chat.end_chat(call_id)
    except Exception as e:                              # noqa: BLE001 - advisory
        trace.event("WARN", "smoke chat turn failed: %s" % str(e)[:300], where="ON-AGENT")
        return "warn: %s" % str(e)[:120]
    first = re.split(r"(?<=[.?!])\s", (reply or "").strip())[0]
    if not (reply or "").strip() or (clarify and reply.strip().startswith(clarify)):
        trace.event("WARN", "smoke chat turn: the agent did not start properly", reply=first, where="ON-AGENT")
        return "warn: reply %r" % first[:80]
    trace.event("FREYA", "smoke chat turn ok", reply=first, call_id=call_id, where="ON-AGENT")
    return "ok"


def _cosmetic_diff(d):
    """Read-back differences that do not change behaviour (none are known yet: every projected field matters)."""
    return bool(re.match(r"^(name|description|updated|created)\b", str(d)))


def _input_error_trace(e):
    """Input errors happen before the run dir exists: still write a trace (runs/_input_errors/<stamp>/)."""
    try:
        stamp = _dt.datetime.now(_dt.timezone.utc).strftime("r%Y%m%dT%H%M%SZ")
        run_dir = paths.RUNS / "_input_errors" / stamp
        trace.init(run_dir)
        trace.event("ERROR", _INPUT_MSG % e, mod="builder.build.main")
        trace.event("END", "exit %d" % EXIT_INPUT, exit=EXIT_INPUT)
        trace.summary(exit=EXIT_INPUT, error=str(e), run_dir=str(run_dir))
        trace.close()
    except Exception:                                   # noqa: BLE001
        trace.event("ERROR", _INPUT_MSG % e, mod="builder.build.main")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        args = parse_args(argv)
    except InputError as e:
        _input_error_trace(e)
        return EXIT_INPUT
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
