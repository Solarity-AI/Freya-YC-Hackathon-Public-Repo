"""Fail-fast checks before a build spends any model time (organiser rebuild: a fresh clone with their own keys).

A missing FREYA_API_KEY or a Claude Agent SDK without a login used to surface only after the extraction wave (the
SDK error, retried per facet) or at the deploy stage. check() finds both in well under a second, offline: it reads
the environment and the local Claude login files only, never calls Freya or a model, and never returns or logs a
secret value (only where a credential was found, e.g. "env:ANTHROPIC_API_KEY" or "keychain").
"""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

MIN_PYTHON = (3, 10)
REQUIRED_MODULES = ("jsonschema",)             # every build validates; claude_agent_sdk is checked when a model runs
AUTH_ENV = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN")
PROVIDER_ENV = ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")
SKIP_AUTH_ENV = "BUILDER_SKIP_AUTH_CHECK"      # escape hatch for a login this check cannot see
KEYCHAIN_SERVICE = "Claude Code-credentials"   # where the `claude` CLI keeps its login on macOS
DEFAULT_FREYA_URL = "https://staging-app.freyavoice.ai"


class PreflightError(Exception):
    pass


def _truthy(v):
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


def _has_key_helper(settings_path):
    try:
        return bool(json.loads(pathlib.Path(settings_path).read_text()).get("apiKeyHelper"))
    except (OSError, ValueError, AttributeError):
        return False


def _keychain_has_login(run):
    """macOS: the CLI's keychain item exists (attributes only: without -w/-g no secret is read)."""
    try:
        r = run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE], capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def claude_auth_source(env=None, home=None, platform=None, run=None):
    """Where the Claude Agent SDK will find a login -> a label, or None when nothing was found."""
    env = os.environ if env is None else env
    for k in AUTH_ENV:
        if env.get(k):
            return "env:" + k
    for k in PROVIDER_ENV:
        if _truthy(env.get(k)):
            return "env:" + k
    cfg = pathlib.Path(env.get("CLAUDE_CONFIG_DIR") or pathlib.Path(home or pathlib.Path.home()) / ".claude")
    if (cfg / ".credentials.json").is_file():
        return "file:.credentials.json"
    if _has_key_helper(cfg / "settings.json"):
        return "settings:apiKeyHelper"
    if (platform or sys.platform) == "darwin" and _keychain_has_login(run or subprocess.run):
        return "keychain"
    return None


def _check_claude(env, find_spec, auth_source):
    if find_spec("claude_agent_sdk") is None:
        raise PreflightError("the Claude Agent SDK is not installed for %s: run `%s -m pip install -r "
                             "requirements.txt`" % (sys.executable, sys.executable))
    if _truthy(env.get(SKIP_AUTH_ENV)):
        return "unchecked (%s=1)" % SKIP_AUTH_ENV
    src = auth_source(env)
    if not src:
        raise PreflightError("no Claude login found for the Claude Agent SDK: run `claude` once and log in, or "
                             "export ANTHROPIC_API_KEY=sk-ant-... (set %s=1 if your login is configured in a way "
                             "this check cannot see)" % SKIP_AUTH_ENV)
    return src


def check(need_llm, need_freya, env=None, version=None, find_spec=None, auth_source=None):
    """-> {"python", "freya_url", "claude_auth"} (no secret values). Raises PreflightError with a fix-it message."""
    env = os.environ if env is None else env
    version = tuple(version or sys.version_info[:2])
    if version < MIN_PYTHON:
        raise PreflightError("Python %d.%d+ is required (this is %d.%d)" % (MIN_PYTHON + version[:2]))
    facts = {"python": "%d.%d" % version[:2], "freya_url": env.get("FREYA_API_URL") or DEFAULT_FREYA_URL,
             "claude_auth": "not needed"}
    missing = [m for m in REQUIRED_MODULES if (find_spec or importlib.util.find_spec)(m) is None]
    if missing:
        raise PreflightError("missing Python package(s) %s for %s: run `%s -m pip install -r requirements.txt`"
                             % (", ".join(missing), sys.executable, sys.executable))
    if need_freya and not env.get("FREYA_API_KEY"):
        raise PreflightError("FREYA_API_KEY is not set: export FREYA_API_KEY=fak_... (FREYA_API_URL defaults to "
                             "%s), or pass --no-deploy to build without Freya" % DEFAULT_FREYA_URL)
    if need_llm:
        facts["claude_auth"] = _check_claude(env, find_spec or importlib.util.find_spec,
                                             auth_source or claude_auth_source)
    return facts
