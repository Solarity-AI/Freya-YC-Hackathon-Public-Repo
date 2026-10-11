"""Last-resort Spec repair before giving up with exit 3 (review fix round 1).

When validation errors survive extraction, re-extraction and the critic, a degraded but valid workflow still scores
while no workflow scores nothing. For each remaining error pointer this tries, from the deepest pointer prefix up:
the generic default at that path (builder/spec/defaults.DEFAULTS), then removing the offending list element or dict
key. A candidate is kept only if the validation error count goes down. Nothing here knows any brief.
"""
import copy
import re

from builder import trace

_MISSING = object()
_REMOVABLE_LISTS = ("intents", "required_sentences", "hints", "holiday_rules", "forbidden_offers")
MAX_CHECKS = 80


def _unesc(p):
    return p.replace("~1", "/").replace("~0", "~")


def _ptr(err):
    m = re.match(r"^(/[^:\s]*)", str(err))
    if not m:
        return None
    return [_unesc(x) for x in m.group(1).split("/")[1:] if x != ""]


def _get(obj, parts):
    cur = obj
    for p in parts:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        elif isinstance(cur, list) and str(p).isdigit() and int(p) < len(cur):
            cur = cur[int(p)]
        else:
            return _MISSING
    return cur


def _resolve_ids(spec, parts):
    """'/intents/<id>/...' (validate names intents by id) -> numeric index."""
    out = list(parts)
    if len(out) >= 2 and out[0] in ("intents",) and not out[1].isdigit():
        for i, it in enumerate(spec.get("intents") or []):
            if isinstance(it, dict) and it.get("id") == out[1]:
                out[1] = str(i)
                break
    return out


def _candidates(spec, err):
    parts = _ptr(err)
    if parts is None:
        return
    parts = _resolve_ids(spec, parts)
    yield from _required_defaults(spec, parts, err)
    for n in range(len(parts), 0, -1):
        yield from _prefix_candidates(spec, parts[:n])


def _required_defaults(spec, parts, err):
    """'<name>' is a required property -> fill the default of that key."""
    from builder.spec.defaults import DEFAULTS
    for name in re.findall(r"'([A-Za-z_]+)' is a required property", str(err)):
        dv = _get(DEFAULTS, parts + [name])
        cont = _get(spec, parts) if parts else spec
        if dv is not _MISSING and isinstance(cont, dict):
            cand = copy.deepcopy(spec)
            (_get(cand, parts) if parts else cand)[name] = copy.deepcopy(dv)
            yield "default %s" % "/".join([""] + parts + [name]), cand


def _prefix_candidates(spec, pre):
    """For one pointer prefix: its default, then removing it from a removable list, then dropping the key."""
    from builder.spec.defaults import DEFAULTS
    n = len(pre)
    dv = _get(DEFAULTS, pre)
    parent = _get(spec, pre[:-1]) if n > 1 else spec
    key = pre[-1]
    if dv is not _MISSING and isinstance(parent, dict):
        cand = copy.deepcopy(spec)
        (_get(cand, pre[:-1]) if n > 1 else cand)[key] = copy.deepcopy(dv)
        yield "default /%s" % "/".join(pre), cand
    if isinstance(parent, list) and key.isdigit() and int(key) < len(parent) and \
            any(x in _REMOVABLE_LISTS for x in pre[:-1][-1:]):
        cand = copy.deepcopy(spec)
        del _get(cand, pre[:-1])[int(key)]
        yield "remove /%s" % "/".join(pre), cand
    if isinstance(parent, dict) and key in parent and n > 1:
        cand = copy.deepcopy(spec)
        del _get(cand, pre[:-1])[key]
        yield "drop /%s" % "/".join(pre), cand


def degrade(spec, errors, check):
    """check(spec) -> list of error strings. -> (spec, errors, applied[str])."""
    st = {"cur": copy.deepcopy(spec), "errs": list(errors or []), "applied": [], "checks": 0}
    for _pass in range(3):
        progressed = False
        for e in st["errs"]:                            # st["errs"] is rebound, never mutated, inside the loop
            if st["checks"] >= MAX_CHECKS:
                break
            progressed = _degrade_one(st, e, check) or progressed
            if not st["errs"]:
                break
        if not st["errs"] or not progressed or st["checks"] >= MAX_CHECKS:
            break
    return st["cur"], st["errs"], st["applied"]


def _degrade_one(st, e, check):
    """Try the candidates for one error; keep the first that lowers the error count. -> True when one was kept."""
    for label, cand in _candidates(st["cur"], e):
        st["checks"] += 1
        errs2 = check(cand)
        if len(errs2) < len(st["errs"]):
            st["cur"], st["errs"] = cand, errs2
            st["applied"].append(label)
            trace.event("DEGRADE", "%s (errors now %d)" % (label, len(st["errs"])), err=str(e)[:160])
            return True
        if st["checks"] >= MAX_CHECKS:
            return False
    return False
