"""Regression tests for the network + username-lookup guards in conftest.py.

PROJECT_REVIEW.md recommendation #1: unexpected outbound network calls must
fail immediately. These tests prove the autouse guards do their job:

* Any test that tries to open an outbound TCP socket without opting in
  gets a loud RuntimeError instead of silently reaching the internet.
* web_interface_agent.get_github_username is auto-mocked so the report
  endpoint no longer depends on api.github.com.
"""

import socket

import pytest


def test_network_guard_blocks_outbound_tcp():
    """A test with no opt-in must not be able to open a real TCP socket."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="Blocked unexpected network call"):
            s.connect(("example.com", 80))
    finally:
        s.close()


def test_network_guard_allows_loopback():
    """Loopback stays open so the FastAPI TestClient and other local
    ephemeral servers keep working."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(OSError):
            # 127.0.0.1:1 is closed but the *guard* must not fire — we
            # expect a regular ConnectionRefusedError, not our RuntimeError.
            s.connect(("127.0.0.1", 1))
    finally:
        s.close()


def test_github_username_lookup_is_auto_mocked():
    """The report path in web_interface_agent must not reach GitHub."""
    from agent_mcp_demo.agents import web_interface_agent as web

    # Even though the underlying implementation calls requests.get against
    # api.github.com, the autouse fixture has replaced it with a stub.
    result = web.get_github_username("any-token-value")
    assert result == "test-current-user"


@pytest.mark.network
def test_network_marker_opts_out_of_guard():
    """Sanity check: tests marked @pytest.mark.network are not blocked.

    We don't actually make an outbound call here — just prove the guard
    is inactive by inspecting the socket.socket.connect attribute. Under
    @pytest.mark.network the autouse fixture yields without patching, so
    connect must still be the original C method_descriptor from _socket.
    """
    connect = socket.socket.connect
    # The stub we install is a plain Python function named
    # `_blocked_socket_connect`. Under @pytest.mark.network the guard
    # yields without patching, so we must NOT see that name here.
    assert getattr(connect, "__name__", "") != "_blocked_socket_connect"


def test_allow_github_username_lookup_fixture(allow_github_username_lookup):
    """Opt-in fixture disables the username auto-mock (so a test can assert
    on the real implementation, or provide its own mock)."""
    from agent_mcp_demo.agents import web_interface_agent as web

    # Not the mock's return value — either the real function reference or a
    # user-supplied replacement.
    assert web.get_github_username.__module__ != "unittest.mock"
