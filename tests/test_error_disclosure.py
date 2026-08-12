"""Regression tests for error/log disclosure.

PROJECT_REVIEW.md Medium finding: publish failures previously returned
tracebacks when DEBUG=1, raw GitHub exception strings, and full peer-
agent responses in logs. These tests pin the current safer contract:

* No stack trace, module path, exception class name, or raw exception
  text may leak into the HTTP response body — not even under DEBUG=1.
* Every error response carries a correlation_id for support/debugging.
* Peer-agent response payloads are never logged in full.
"""

import io
import logging
import os
import re
import tempfile
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from agent_mcp_demo.server import app as server_app
from agent_mcp_demo.utils.report_publisher import ReportPublisher


@pytest.fixture
def client():
    return TestClient(server_app)


@pytest.fixture
def mock_env_vars():
    with patch.dict(os.environ, {
        "GITHUB_TOKEN": "test_token",
        "GITHUB_ORG_NAME": "test_org",
    }):
        yield


@pytest.fixture
def temp_publisher():
    with tempfile.TemporaryDirectory() as tmpdir:
        pub = ReportPublisher(base_dir=tmpdir)
        with patch("agent_mcp_demo.server.publisher", pub):
            yield pub


# ---------------------------------------------------------------------------
# server.py publish endpoint
# ---------------------------------------------------------------------------


def _forbidden_disclosure_patterns():
    """Substrings that must NEVER appear in an error response body."""
    return [
        "Traceback",
        "traceback",
        "File \"",
        "line ",
        "at 0x",  # object memory addresses
        "boom-secret-marker",  # our synthetic exception message
    ]


def test_publish_endpoint_sync_error_returns_correlation_id(
    client, mock_env_vars, temp_publisher, monkeypatch
):
    """Force the *synchronous* error path in publish_report_endpoint by
    passing a body that survives validation but blows up during
    processing. The response must be a stable generic error with a
    correlation_id — not the raw exception."""
    # Make json.loads raise on the parsed dict path so the outer
    # `except Exception` handler kicks in.
    import agent_mcp_demo.server as server_mod

    real = server_mod.json.loads

    def _explode(raw, *args, **kwargs):
        # Only trip on our targeted payload, so we don't break other
        # tests that share this handler.
        if b"trip-generic-500" in (raw or b""):
            raise RuntimeError("boom-secret-marker deep internal state")
        return real(raw, *args, **kwargs)

    monkeypatch.setattr(server_mod.json, "loads", _explode)

    response = client.post(
        "/api/reports/publish",
        content=b'{"report_content": "trip-generic-500"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "Failed to publish report"
    assert re.fullmatch(r"[0-9a-f]{12}", body["correlation_id"])
    for pattern in _forbidden_disclosure_patterns():
        assert pattern not in response.text, (
            f"Leak: {pattern!r} in response body"
        )


def test_debug_env_var_does_not_re_enable_disclosure(
    client, mock_env_vars, temp_publisher, monkeypatch
):
    """DEBUG=1 must NOT bring back traceback responses. The historical
    behavior — where operators could re-enable full stack traces via
    an env var — was a foot-gun: a single misconfiguration in prod
    turned every 500 into an information disclosure. The env var no
    longer changes the response body at all."""
    monkeypatch.setenv("DEBUG", "1")

    import agent_mcp_demo.server as server_mod
    real = server_mod.json.loads

    def _explode(raw, *args, **kwargs):
        if b"trip-generic-500" in (raw or b""):
            raise RuntimeError("boom-secret-marker private")
        return real(raw, *args, **kwargs)

    monkeypatch.setattr(server_mod.json, "loads", _explode)

    response = client.post(
        "/api/reports/publish",
        content=b'{"report_content": "trip-generic-500"}',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "Failed to publish report"
    # No details/traceback fields; no smuggled marker.
    assert "details" not in body
    for pattern in _forbidden_disclosure_patterns():
        assert pattern not in response.text


# ---------------------------------------------------------------------------
# web_interface_agent peer-response logging
# ---------------------------------------------------------------------------


def test_peer_response_is_not_logged_in_full(caplog, monkeypatch):
    """Full peer-agent response payloads must never hit the logs. This
    used to be `logger.info(f"Iteration info result: {full_payload}")`
    which turned the log into an echo channel for attacker-controlled
    GitHub text."""
    from agent_mcp_demo.agents import web_interface_agent as web
    from agent_mcp_demo.agents import _peer_client, _wire

    iteration_secret = "PEER-SECRET-ITER-" + ("X" * 4096)
    github_secret = "PEER-SECRET-DATA-" + ("Y" * 4096)

    responses = iter([
        _wire.encode({"name": iteration_secret, "start_date": "2025-01-01"}),
        _wire.encode({
            "member_stats": {},
            "commit_details": {},
            "assigned_issues": {},
            "closed_issues": {},
            "extra_marker": github_secret,
        }),
    ])

    async def _fake_call(agent, tool, args=None):
        return next(responses)

    monkeypatch.setattr(_peer_client, "call_peer_tool", _fake_call)
    monkeypatch.setenv("GITHUB_TOKEN", "test_token")
    monkeypatch.setenv("GITHUB_ORG_NAME", "test_org")

    caplog.set_level(logging.INFO, logger="web-interface-agent")

    client = TestClient(web.app, raise_server_exceptions=False)
    client.get("/api/github-report")

    joined = "\n".join(record.getMessage() for record in caplog.records)
    for secret in (iteration_secret, github_secret):
        assert secret not in joined, (
            "Peer-agent payload leaked into logs — length/type summary "
            "logging was regressed."
        )
    # It's fine (in fact, expected) that we log a length summary.
    assert any("len=" in msg for msg in (r.getMessage() for r in caplog.records))
