"""Deploy a compiled workflow with the kit client (docs/CONTRACTS.md D.6 'Deploy (L3)'). Owner: agent 3.

Uses builder.paths.import_kit("freya"). Credentials only from the environment. Never starts simulations.

Sequence: dry run (optional) -> save_workflow (twice when the slot is new: the 2nd save patches agent_config and
publishes, returning the published version) -> export (one GET) -> projected read-back diff taken from the export.
No redundant GETs (BUILD SPEED item 5): the versions list is read only when the kit returned no version number.
Every Freya call is sequential; the kit client has a 120 s timeout per request; nothing is retried here except one
publish of an unpublished newest version.
"""
import json
import os
import pathlib
import re

from builder import paths


class DeployError(Exception):
    def __init__(self, msg, result=None):
        super().__init__(msg)
        self.result = result or {}


def _scrub(text):
    from builder import trace
    return trace.scrub(text)                            # never raises


def _log(kind, msg, **fields):
    import sys
    from builder import trace
    fields.setdefault("mod", "builder.deploy." + sys._getframe(1).f_code.co_name)
    fields.setdefault("where", "ON-AGENT")
    trace.event(kind, msg, **fields)                    # never raises


def _kit(freya):
    if freya is not None:
        return freya
    if not os.environ.get("FREYA_API_KEY"):
        raise DeployError("FREYA_API_KEY is not set (source the kit env.sh)")
    return paths.import_kit("freya")


def _safe_slot(slot):
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(slot)).strip("._")
    if not s:
        raise DeployError("empty slot name")
    return s


def _false_success(x, path=""):
    """Pointers of every `success: false` (or ok:false / valid:false) inside a dry-run result."""
    out = []
    if isinstance(x, dict):
        for k, v in x.items():
            if k in ("success", "valid", "ok") and v is False:
                out.append(path + "/" + k)
            else:
                out += _false_success(v, path + "/" + str(k))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            out += _false_success(v, path + "/" + str(i))
    return out


# ------------------------------------------------------------------------------------------------ read-back diff

def _cond(c):
    if not isinstance(c, dict):
        return c
    if "conditions" in c:
        return {"logic": c.get("logic", "or"), "conditions": [_cond(x) for x in c.get("conditions") or []]}
    out = {"operator": c.get("operator")}
    if "variable" in c:
        out["variable"] = c.get("variable")
    if "operand" in c:
        out["operand"] = str(c.get("operand"))
    return out


def _project(node):
    n = node or {}
    oe = n.get("on_enter") or {}
    p = {
        "node_type": n.get("node_type"),
        "passthrough": bool(n.get("passthrough")),
        "on_enter": {"type": oe.get("type", "llm"), "text": oe.get("text", "")},
        "transitions": [(t.get("target_node"), json.dumps(_cond(t.get("condition") or {}), sort_keys=True))
                        for t in n.get("transitions") or []],
        "response_mapping": [(m.get("path"), m.get("variable")) for m in n.get("response_mapping") or []],
        "extraction": [(x.get("name"), tuple(x.get("enum_values") or ())) for x in n.get("extraction_schema") or []],
        "pre_actions": [],
    }
    for pa in n.get("pre_actions") or []:
        fn = pa.get("function") or {}
        props = (fn.get("parameters") or {}).get("properties") or {}
        body = ((props.get("body") or {}).get("properties") or {})
        p["pre_actions"].append({
            "name": fn.get("name"),
            "url": (props.get("url") or {}).get("default", ""),
            "code": (props.get("code") or {}).get("default", ""),
            "body": {k: str((v or {}).get("default", "")) for k, v in sorted(body.items())},
        })
    return p


def projected_diff(sent, stored):
    """Compare the fields we rely on (node keys, node_type, passthrough, on_enter, transitions, pre_action names,
    url, body defaults, response_mapping, extraction names/enums). -> list of human-readable differences."""
    diffs = []
    sent = sent or {}
    stored = stored or {}
    if sent.get("initial_node") != stored.get("initial_node"):
        diffs.append(f"initial_node: sent {sent.get('initial_node')!r}, stored {stored.get('initial_node')!r}")
    sn, tn = sent.get("nodes") or {}, stored.get("nodes") or {}
    for k in sorted(set(sn) - set(tn)):
        diffs.append(f"node {k}: missing after save")
    for k in sorted(set(tn) - set(sn)):
        diffs.append(f"node {k}: unexpected node after save")
    for k in sorted(set(sn) & set(tn)):
        a, b = _project(sn[k]), _project(tn[k])
        for field in ("node_type", "passthrough", "on_enter", "transitions", "response_mapping", "extraction"):
            if a[field] != b[field]:
                if field == "transitions":
                    diffs.append(f"node {k}: transitions differ ({len(a[field])} sent, {len(b[field])} stored)")
                else:
                    diffs.append(f"node {k}: {field} differs")
        if len(a["pre_actions"]) != len(b["pre_actions"]):
            diffs.append(f"node {k}: {len(a['pre_actions'])} pre_actions sent, {len(b['pre_actions'])} stored")
        else:
            for i, (pa, pb) in enumerate(zip(a["pre_actions"], b["pre_actions"])):
                for f in ("name", "url", "code", "body"):
                    if pa[f] != pb[f]:
                        diffs.append(f"node {k}: pre_action {i} {f} differs")
    return diffs


# ------------------------------------------------------------------------------------------------ calls

def _versions(fr, wid):
    r = fr.api("GET", f"/api/v2/versions/workflow/{wid}", workspaceId=fr.workspace_id(), limit=100)
    vs = r.get("versions") if isinstance(r, dict) else r
    return [v for v in vs or [] if isinstance(v, dict)]


def _published_check(fr, wid):
    vs = _versions(fr, wid)
    if not vs:
        raise DeployError(f"workflow {wid}: no versions listed")
    newest = max(vs, key=lambda v: int(v.get("versionNumber") or 0))
    if not newest.get("isPublished"):
        _log("FREYA", f"newest version {newest.get('versionNumber')} not published: publishing once")
        fr.api("POST", f"/api/v2/versions/workflow/{wid}/publish", {"versionId": newest["id"]})
        vs = _versions(fr, wid)
        newest = max(vs, key=lambda v: int(v.get("versionNumber") or 0))
        if not newest.get("isPublished"):
            raise DeployError(f"workflow {wid}: newest version {newest.get('versionNumber')} is not published")
    return int(newest.get("versionNumber") or 0)


def _stored_from_export(path):
    """The stored workflow as written by the export (kit format {"workflow_id", ..., "workflow": {...}})."""
    doc = json.loads(pathlib.Path(path).read_text())
    w = doc.get("workflow") if isinstance(doc, dict) else None
    return w if isinstance(w, dict) else {}


def export(workflow_id, path, freya=None):
    """kit freya.export_workflow wrapper -> path."""
    fr = _kit(freya)
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        fr.export_workflow(workflow_id, str(p))
    except Exception as e:
        raise DeployError("export failed: " + _scrub(e)) from None
    _log("EXPORT", f"exported workflow {workflow_id}", path=str(p))
    return str(p)


def deploy(workflow, slot, run_dir, dry_run=True, freya=None, state_dir=None, strict=False, name=None):
    """Dry run (if dry_run) -> save_workflow twice on create -> published check -> projected read-back diff -> export.
    -> {"workflow_id", "agent_id", "version", "export_path", "diff": [str], "created", "state_file", "llm_ok"}.
    Raises DeployError on failure (with strict=True also on a non-empty read-back diff, after the export)."""
    fr = _kit(freya)
    slot_s = _safe_slot(slot)
    run_dir = pathlib.Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    state_dir = pathlib.Path(state_dir or paths.STATE)
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / (slot_s + ".json")
    if dry_run:
        try:
            r = fr.validate_workflow(name or slot_s, workflow)
        except Exception as e:
            raise DeployError("dry run rejected the workflow: " + _scrub(e)) from None
        bad = _false_success(r)
        if bad:
            raise DeployError("dry run reported failure at " + ", ".join(bad[:5]) + ": "
                              + _scrub(json.dumps(r)[:800]))
        _log("DEPLOY", "dry run ok")
    try:
        state = json.loads(state_file.read_text()) if state_file.exists() else {}
    except (ValueError, OSError) as e:
        raise DeployError(f"state file {state_file} is unreadable ({e}); fix or remove it by hand "
                          "(it holds the workflow id of this slot)") from None
    created = slot_s not in state
    try:
        ids = fr.save_workflow(slot_s, workflow, state_file=str(state_file))
        _log("FREYA", ("created" if created else "updated") + f" workflow {ids.get('workflow_id')}",
             agent_id=ids.get("agent_id"), version=ids.get("version", ""))
        if created:
            ids = fr.save_workflow(slot_s, workflow, state_file=str(state_file))
            _log("FREYA", f"second save (agent_config patch + publish) version {ids.get('version')}")
    except DeployError:
        raise
    except Exception as e:
        raise DeployError("save_workflow failed: " + _scrub(e)) from None
    wid, agent = ids.get("workflow_id"), ids.get("agent_id")
    if not wid:
        raise DeployError("save_workflow returned no workflow_id")
    try:
        # the kit's update already published the newest version and returned its number
        version = int(ids["version"]) if str(ids.get("version", "")).isdigit() else _published_check(fr, wid)
    except DeployError:
        raise
    except Exception as e:
        raise DeployError("read-back failed: " + _scrub(e)) from None
    export_path = export(wid, run_dir / "workflow.export.json", freya=fr)
    try:
        stored = _stored_from_export(export_path)
    except (OSError, ValueError) as e:
        raise DeployError("read-back failed: " + _scrub(e)) from None
    diff = projected_diff(workflow, stored)
    llm = ((stored.get("agent_config") or {}).get("llmConfig") or {})
    want = getattr(fr, "AGENT_LLM", None) or {}
    llm_ok = not want or (llm.get("provider"), llm.get("model")) == (want.get("provider"), want.get("model"))
    if not llm_ok:
        diff.append(f"agent_config.llmConfig is {llm.get('provider')}/{llm.get('model')}, "
                    f"expected {want.get('provider')}/{want.get('model')}")
    for d in diff:
        _log("WARN", "read-back: " + d)
    result = {"workflow_id": wid, "agent_id": agent, "version": version, "export_path": export_path,
              "diff": diff, "created": created, "state_file": str(state_file), "llm_ok": llm_ok}
    (run_dir / "ids.json").write_text(json.dumps({k: result[k] for k in ("workflow_id", "agent_id", "version",
                                                                        "created")}, indent=1))
    _log("DEPLOY", f"published version {version} of {wid}", diff=len(diff))
    if strict and diff:
        raise DeployError(f"read-back differs in {len(diff)} places: " + "; ".join(diff[:5]), result)
    return result
