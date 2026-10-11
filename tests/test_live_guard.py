"""The autouse live guard in tests/conftest.py: no test reaches a non-localhost host, a real Claude Agent SDK
transport or the claude CLI unless it opts in with @pytest.mark.allow_network / allow_claude (or `live`).
Every blocked call below fails before any packet or process leaves this test process."""
import asyncio
import os
import pathlib
import socket
import subprocess
import sys
import textwrap
import urllib.request

import pytest

import conftest as guard

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEST_NET = "192.0.2.1"            # RFC 5737 documentation address: never routed, and never reached here anyway


# ------------------------------------------------------------------------------------------------ helpers

@pytest.mark.parametrize("host,local", [
    ("127.0.0.1", True), ("127.8.9.10", True), ("::1", True), ("[::1]", True), ("localhost", True),
    ("api.localhost", True), ("LOCALHOST", True), ("0.0.0.0", True), ("::", True), ("", True),
    ("::ffff:127.0.0.1", True), (b"127.0.0.1", True), ("fe80::1%lo0", False),
    (TEST_NET, False), ("8.8.8.8", False), ("2001:db8::1", False), ("example.com", False),
    ("localhost.example.com", False), ("::ffff:8.8.8.8", False),
])
def test_is_local_host(host, local):
    assert guard._is_local_host(host) is local


def test_is_local_address_families():
    assert guard._is_local_address(socket.AF_UNIX, "/tmp/x.sock")
    assert guard._is_local_address(socket.AF_INET, b"/tmp/x.sock")
    assert guard._is_local_address(socket.AF_INET, ("127.0.0.1", 80))
    assert guard._is_local_address(socket.AF_INET6, ("::1", 80, 0, 0))
    assert not guard._is_local_address(socket.AF_INET, (TEST_NET, 80))
    assert not guard._is_local_address(socket.AF_INET, None)
    assert not guard._is_local_address(socket.AF_INET, ())


@pytest.mark.parametrize("args,executable,hit", [
    (["claude", "-p", "hi"], None, True),
    (["/usr/local/bin/claude", "--version"], None, True),
    ("claude -p 'hello there'", None, True),
    (b"/opt/claude", None, True),
    (pathlib.Path("/x/claude.exe"), None, True),
    (["/venv/site-packages/claude_agent_sdk/_bundled/claude"], None, True),
    (["node", "/usr/lib/node_modules/@anthropic-ai/claude-code/cli.js"], None, True),
    (["C:\\tools\\claude.exe"], None, True),
    (["sh"], "/usr/local/bin/claude", True),
    ("echo 'unbalanced", None, False),
    (["python", "-c", "print(1)"], None, False),
    (["claude-config-tool"], None, False),
    (["git", "log", "--grep=claude code"], None, False),
    (None, None, False),
])
def test_is_claude_cli(args, executable, hit):
    assert guard._is_claude_cli(args, executable) is hit


# ------------------------------------------------------------------------------------------------ sockets

def test_socket_to_non_localhost_is_blocked():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        with pytest.raises(AssertionError, match="non-localhost"):
            s.connect((TEST_NET, 9))
        with pytest.raises(AssertionError, match="non-localhost"):
            s.connect_ex((TEST_NET, 9))
    with pytest.raises(AssertionError, match="non-localhost"):
        socket.create_connection(("example.com", 443), timeout=1)


def test_udp_sendto_non_localhost_is_blocked():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        with pytest.raises(AssertionError, match="non-localhost"):
            s.sendto(b"x", (TEST_NET, 9))
        with pytest.raises(AssertionError, match="non-localhost"):
            s.sendto(b"x", 0, (TEST_NET, 9))


def test_http_clients_to_non_localhost_are_blocked():
    import http.client
    with pytest.raises(AssertionError, match="live HTTP connection"):      # urlopen itself is guarded too
        urllib.request.urlopen("http://%s/" % TEST_NET, timeout=1)
    conn = http.client.HTTPConnection(TEST_NET, 80, timeout=1)
    with pytest.raises(AssertionError, match="non-localhost"):
        conn.request("GET", "/")
    conn.close()


def test_localhost_sockets_still_work():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        with socket.create_connection(srv.getsockname(), timeout=2) as c:
            peer, _ = srv.accept()
            with peer:
                c.sendall(b"ok")
                assert peer.recv(2) == b"ok"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as rx, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tx:
        rx.bind(("127.0.0.1", 0))
        tx.sendto(b"u", rx.getsockname())
        assert rx.recv(1) == b"u"


def test_unix_sockets_and_asyncio_loop_still_work(tmp_path):
    a, b = socket.socketpair()
    with a, b:
        a.sendall(b"p")
        assert b.recv(1) == b"p"
    assert asyncio.run(asyncio.sleep(0, result=7)) == 7


# ------------------------------------------------------------------------------------------------ claude

def test_claude_cli_launch_is_blocked():
    with pytest.raises(AssertionError, match="claude CLI"):
        subprocess.run(["claude", "--version"], capture_output=True)
    with pytest.raises(AssertionError, match="claude CLI"):
        subprocess.run("claude -p hi", shell=True, capture_output=True)


def test_claude_cli_launch_through_asyncio_is_blocked():
    async def go():
        return await asyncio.create_subprocess_exec("claude", "--version")
    coro = go()
    with pytest.raises(AssertionError, match="claude CLI"):
        asyncio.run(coro)


def test_other_subprocesses_still_work():
    r = subprocess.run([sys.executable, "-c", "print(6 * 7)"], capture_output=True, text=True, check=True)
    assert r.stdout.strip() == "42"


def test_real_sdk_query_is_blocked():
    import claude_agent_sdk as sdk

    async def go():
        async for _m in sdk.query(prompt="hi"):
            pass
    coro = go()
    with pytest.raises(AssertionError, match="real Claude Agent SDK call"):
        asyncio.run(coro)


def test_builder_sdk_backend_is_blocked():
    from builder import llm
    req = {"system": "s", "schema": {"type": "object"}, "model": "m", "effort": "low", "prompt": "p"}
    coro = llm._sdk_backend(req)
    with pytest.raises(AssertionError, match="real Claude Agent SDK call"):
        asyncio.run(coro)


def test_faked_sdk_query_still_works(monkeypatch):
    import claude_agent_sdk as sdk

    async def fake_query(prompt, options=None):
        yield "fake:" + prompt
    monkeypatch.setattr(sdk, "query", fake_query)

    async def go():
        return [m async for m in sdk.query(prompt="hi")]
    assert asyncio.run(go()) == ["fake:hi"]


# ------------------------------------------------------------------------------------------------ opt-in

def _guarded_now():
    from claude_agent_sdk._internal.transport import subprocess_cli
    return {"network": "connect" in socket.socket.__dict__,
            "cli": subprocess.Popen._execute_child.__qualname__ != "Popen._execute_child",
            "sdk": subprocess_cli.SubprocessCLITransport.connect.__qualname__ != "SubprocessCLITransport.connect"}


def test_default_test_is_fully_guarded():
    assert _guarded_now() == {"network": True, "cli": True, "sdk": True}


@pytest.mark.allow_network
def test_allow_network_opts_in_to_sockets_only():
    assert _guarded_now() == {"network": False, "cli": True, "sdk": True}


@pytest.mark.allow_claude
def test_allow_claude_opts_in_to_claude_only():
    assert _guarded_now() == {"network": True, "cli": False, "sdk": False}


@pytest.mark.allow_network
@pytest.mark.allow_claude
def test_both_markers_lift_every_guard():
    assert _guarded_now() == {"network": False, "cli": False, "sdk": False}


def test_live_marker_lifts_every_guard_and_is_skipped_without_run_live(tmp_path):
    """A `live` test runs only with RUN_LIVE=1, and then without the guards (it talks to Freya by design)."""
    (tmp_path / "test_x.py").write_text(textwrap.dedent('''
        import pytest
        from test_live_guard import _guarded_now

        @pytest.mark.live
        def test_live():
            assert _guarded_now() == {"network": False, "cli": False, "sdk": False}
    '''))
    cmd = [sys.executable, "-m", "pytest", "-rA", "-p", "no:cacheprovider", "--rootdir", str(ROOT),
           "-c", str(ROOT / "pytest.ini"), "--confcutdir", str(ROOT / "tests"), "-p", "conftest", str(tmp_path)]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT), str(ROOT / "tests")]))
    env.pop("COV_CORE_SOURCE", None)
    for run_live, want in (("1", "PASSED"), ("0", "SKIPPED")):
        env["RUN_LIVE"] = run_live
        r = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=120)
        assert want in r.stdout, r.stdout + r.stderr
