"""Shared test fixtures (lead-owned). Repo root is on sys.path via pytest.ini `pythonpath = .`."""
import json
import os
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
KIT = ROOT / "kit"


def _load(rel):
    return json.loads((ROOT / rel).read_text())


@pytest.fixture
def schema():
    return _load("builder/spec/schema.json")


@pytest.fixture
def golden_a():
    return _load("tests/golden/spec-a.json")


@pytest.fixture
def golden_ab():
    return _load("tests/golden/spec-ab.json")


@pytest.fixture
def catalog_kit():
    return _load("tests/fixtures/catalog-kit.json")


@pytest.fixture
def wiring_a():
    return _load("tests/fixtures/wiring-a.json")


@pytest.fixture
def wiring_ab():
    return _load("tests/fixtures/wiring-ab.json")


@pytest.fixture
def kit_openapi_path():
    return KIT / "tools" / "openapi.json"


@pytest.fixture
def public_cases():
    return {c["id"]: c for c in json.loads((KIT / "public-test-set.json").read_text())}


def pytest_collection_modifyitems(config, items):
    if os.environ.get("RUN_LIVE") == "1":
        return
    skip = pytest.mark.skip(reason="live test: set RUN_LIVE=1")
    for it in items:
        if "live" in it.keywords:
            it.add_marker(skip)


# ------------------------------------------------------------------------------------------------ live guard
# Every test runs offline unless it opts in with a marker (the `live` marker opts in to both and is skipped unless
# RUN_LIVE=1):
#   @pytest.mark.allow_network  sockets to non-loopback hosts (default: only localhost / 127.0.0.0/8 / ::1 / unix)
#   @pytest.mark.allow_claude   real model calls through the Claude Agent SDK transport and launching the claude CLI
# Tests that fake the SDK (monkeypatch claude_agent_sdk.query, llm.set_backend, a custom Transport) never reach these
# guards. The guards cover this process only: a child process started by a test is not guarded.

CLAUDE_CLI_MARKERS = ("@anthropic-ai/claude-code", "claude_agent_sdk/_bundled/")
CLAUDE_CLI_NAMES = ("claude", "claude.exe")


def pytest_configure(config):
    config.addinivalue_line("markers", "allow_network: the test may open sockets to non-localhost hosts")
    config.addinivalue_line("markers", "allow_claude: the test may make real Claude Agent SDK / claude CLI calls")


def _is_local_host(host):
    """True for loopback / any-address hosts; a hostname other than localhost is not resolved and counts as remote."""
    import ipaddress
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    host = str(host).strip("[]").split("%", 1)[0].lower()
    if host in ("", "localhost") or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return ip.is_loopback or ip.is_unspecified


def _is_local_address(family, address):
    import socket as _s
    if family == getattr(_s, "AF_UNIX", object()) or isinstance(address, (str, bytes, os.PathLike)):
        return True                                       # unix-domain socket path: never leaves the machine
    if isinstance(address, tuple) and address:
        return _is_local_host(address[0])
    return False


def _is_claude_cli(args, executable=None):
    import shlex
    if isinstance(args, (str, bytes, os.PathLike)):
        args = [args]
    tokens = []
    for a in list(args or []) + ([executable] if executable else []):
        a = os.fsdecode(a) if isinstance(a, (bytes, os.PathLike)) else str(a)
        tokens.append(a)
        try:
            tokens.extend(shlex.split(a))
        except ValueError:
            tokens.extend(a.split())
    for t in tokens:
        t = t.replace("\\", "/")
        if os.path.basename(t).lower() in CLAUDE_CLI_NAMES or any(m in t for m in CLAUDE_CLI_MARKERS):
            return True
    return False


@pytest.fixture(autouse=True)
def _no_live_platform(request, monkeypatch, tmp_path):
    """Tests never reach the live platform, the network or a real model (hackathon rule): the live-chat transport
    fails unless a test fakes it, sockets to non-localhost hosts fail, real Claude Agent SDK transports and claude CLI
    launches fail, and the workspace chat lock lives in the test's tmp dir."""
    import socket
    import subprocess
    from harness import chat_e2e
    live = request.node.get_closest_marker("live") is not None
    allow_network = live or request.node.get_closest_marker("allow_network") is not None
    allow_claude = live or request.node.get_closest_marker("allow_claude") is not None

    real = chat_e2e.urllib.request.urlopen

    def blocked(req, *a, **k):
        url = getattr(req, "full_url", req)
        if allow_network or str(url).startswith(("http://127.0.0.1", "http://localhost")):
            return real(req, *a, **k)
        raise AssertionError("a test tried to open a live HTTP connection: %s" % url)
    monkeypatch.setattr(chat_e2e.urllib.request, "urlopen", blocked)
    monkeypatch.setattr(chat_e2e, "LOCK_PATH", tmp_path / "chat.lock")

    if not allow_network:
        def guard(name):
            orig = getattr(socket.socket, name)

            def guarded(self, first, *a, **k):
                target = first if name != "sendto" else (a[-1] if a else None)   # sendto(data[, flags], address)
                if not _is_local_address(self.family, target):
                    raise AssertionError("a test tried to open a network socket to a non-localhost address %r "
                                         "(mark it @pytest.mark.allow_network to opt in)" % (target,))
                return orig(self, first, *a, **k)
            monkeypatch.setattr(socket.socket, name, guarded)
        for name in ("connect", "connect_ex", "sendto"):
            guard(name)

    if not allow_claude:
        orig_exec = subprocess.Popen._execute_child

        def exec_child(self, args, executable, *a, **k):
            if _is_claude_cli(args, executable):
                raise AssertionError("a test tried to launch the claude CLI: %r "
                                     "(mark it @pytest.mark.allow_claude to opt in)" % (args,))
            return orig_exec(self, args, executable, *a, **k)
        monkeypatch.setattr(subprocess.Popen, "_execute_child", exec_child)

        try:
            from claude_agent_sdk._internal.transport import subprocess_cli
        except ImportError:                                  # SDK missing or moved: the CLI-launch guard still holds
            return

        async def no_sdk(self, *a, **k):
            raise AssertionError("a test tried to make a real Claude Agent SDK call (fake claude_agent_sdk.query or "
                                 "llm.set_backend, or mark it @pytest.mark.allow_claude to opt in)")
        monkeypatch.setattr(subprocess_cli.SubprocessCLITransport, "connect", no_sdk)
