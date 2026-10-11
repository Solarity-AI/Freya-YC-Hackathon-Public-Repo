"""Path resolution for the builder and harness (lead-owned). Resolves everything from this file, never from cwd."""
import importlib.util
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent          # repo root
_KIT_CANDIDATES = [ROOT / "kit", ROOT.parent / "kit" / "build-the-builder", ROOT / "kit" / "build-the-builder"]
KIT = next((p for p in _KIT_CANDIDATES if (p / "freya.py").exists()), _KIT_CANDIDATES[0])
RUNS = ROOT / "runs"
STATE = ROOT / "state"
SCHEMA = ROOT / "builder" / "spec" / "schema.json"
PROMPTS = ROOT / "builder" / "prompts"

_loaded = {}


def import_kit(name):
    """Import a kit module by name: "freya" (kit/freya.py), "score" or "run_cases" (kit/tools/*.py)."""
    if name in _loaded:
        return _loaded[name]
    path = KIT / (name + ".py")
    if not path.exists():
        path = KIT / "tools" / (name + ".py")
    if not path.exists():
        raise FileNotFoundError(f"kit module {name!r} not found under {KIT}")
    for p in (str(KIT), str(KIT / "tools")):          # run_cases imports freya and score by bare name
        if p not in sys.path:
            sys.path.insert(0, p)
    spec = importlib.util.spec_from_file_location("kit_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _loaded[name] = mod
    return mod


def bank_host():
    return os.environ.get("FREYA_BANK_HOST", "https://freya-bank-mock.freyavoice.workers.dev")
