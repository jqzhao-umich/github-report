"""Integration tests for the multi-agent stack.

These tests exercise the coordinator's plumbing (retry, peer-RPC seam,
response parsing) end-to-end. They come in two flavors:

* Live-stack tests (marked ``@pytest.mark.integration``) — need a real
  multi-agent stack running. They skip when ``_peer_client.call_peer_tool``
  is the default stub. Run with the four agents up in the background and
  ``LIVE_MCP_STACK=1`` in the environment to force execution.
* Plumbing tests (marked ``@pytest.mark.integration``) — mock
  ``call_peer_tool`` at the module boundary and verify that
  ``BaseMCPAgent.call_agent`` retries, unwraps TextContent, and
  propagates errors correctly. Fast and hermetic.

The ``performance`` marker is reserved for tests in test_performance.py.
"""

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest

from agent_mcp_demo.agents import _peer_client
from agent_mcp_demo.agents.base import BaseMCPAgent
from agent_mcp_demo.agents.config import settings
from agent_mcp_demo.agents.types import GitHubData, IterationInfo


def _live_stack_available() -> bool:
    """A live stack is available if LIVE_MCP_STACK=1 is set in env.
    The default ``call_peer_tool`` raises NotImplementedError, so
    without explicit opt-in these tests would just retry forever."""
    return os.environ.get("LIVE_MCP_STACK") == "1"


needs_live_stack = pytest.mark.skipif(
    not _live_stack_available(),
    reason=(
        "Live multi-agent stack not detected. Start the four agents via "
        "`./start.sh start` and set LIVE_MCP_STACK=1 to run this test."
    ),
)


# ---------------------------------------------------------------------------
# Live-stack tests — the ones from the original file, now guarded so they
# skip cleanly when there's no real stack (previously they errored with
# `AttributeError: 'Server' object has no attribute 'request_context'`).
# ---------------------------------------------------------------------------


@pytest.fixture
async def running_agents():
    agents = {
        "core": BaseMCPAgent("core-agent"),
        "github": BaseMCPAgent("github-agent"),
        "web": BaseMCPAgent("web-interface-agent"),
        "coordinator": BaseMCPAgent("main-coordinator"),
    }
    await asyncio.gather(*(a.initialize() for a in agents.values()))
    try:
        yield agents
    finally:
        await asyncio.gather(*(a.cleanup() for a in agents.values()))


@needs_live_stack
@pytest.mark.integration
async def test_end_to_end_report_generation(running_agents):
    coordinator = running_agents["coordinator"]
    response = await coordinator.call_agent(
        "main-coordinator",
        "get-github-report",
        {"org_name": settings.github_org_name},
    )
    assert response and isinstance(response, list)
    report_text = response[0].text
    assert "GitHub Organization:" in report_text
    assert "SUMMARY" in report_text
    assert "DETAILED ACTIVITY" in report_text


@needs_live_stack
@pytest.mark.integration
async def test_agent_communication_chain(running_agents):
    coordinator = running_agents["coordinator"]
    iteration_info = await coordinator.call_agent(
        "github-agent",
        "get-iteration-info",
        {"org_name": settings.github_org_name},
    )
    assert iteration_info is not None

    github_data = await coordinator.call_agent(
        "github-agent",
        "get-github-data",
        {
            "org_name": settings.github_org_name,
            "iteration_info": iteration_info[0].text if iteration_info else None,
        },
    )
    assert github_data is not None

    report = await coordinator.call_agent(
        "web-interface-agent",
        "generate-report",
        {
            "org_name": settings.github_org_name,
            "iteration_info": iteration_info[0].text if iteration_info else None,
            "github_data": github_data[0].text if github_data else None,
        },
    )
    assert report is not None


@needs_live_stack
@pytest.mark.integration
async def test_error_propagation(running_agents):
    coordinator = running_agents["coordinator"]

    with pytest.raises(Exception) as exc_info:
        await coordinator.call_agent(
            "github-agent",
            "get-github-data",
            {"org_name": "invalid-org-name"},
        )
    assert "error" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Plumbing tests — mock the RPC seam and verify BaseMCPAgent.call_agent's
# retry / wrapping / error-propagation contract. These run in the default
# integration filter without needing a live stack.
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_call_agent_wraps_text_in_textcontent(monkeypatch):
    """The MCP 2.0 seam returns raw text; call_agent must wrap it in
    a [TextContent] list so existing callers keep working."""
    async def _fake(agent, tool, args=None):
        return "hello from peer"

    monkeypatch.setattr(_peer_client, "call_peer_tool", _fake)
    coordinator = BaseMCPAgent("main-coordinator")

    result = await coordinator.call_agent("github-agent", "get-iteration-info")
    assert isinstance(result, list) and len(result) == 1
    assert result[0].text == "hello from peer"
    assert result[0].type == "text"


@pytest.mark.integration
async def test_call_agent_retries_on_transient_error(monkeypatch):
    """Retry contract: settings.max_retries attempts, exponential
    backoff (patched to zero for speed)."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    calls = {"n": 0}

    async def _flaky(agent, tool, args=None):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise RuntimeError("transient")
        return "ok"

    monkeypatch.setattr(_peer_client, "call_peer_tool", _flaky)
    coordinator = BaseMCPAgent("main-coordinator")

    result = await coordinator.call_agent("github-agent", "get-something")
    assert result[0].text == "ok"
    assert calls["n"] == 3


@pytest.mark.integration
async def test_call_agent_propagates_after_max_retries(monkeypatch):
    """Once max_retries is exhausted, the exception propagates."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    async def _always_fails(agent, tool, args=None):
        raise RuntimeError("persistent")

    monkeypatch.setattr(_peer_client, "call_peer_tool", _always_fails)
    coordinator = BaseMCPAgent("main-coordinator")

    with pytest.raises(RuntimeError, match="persistent"):
        await coordinator.call_agent("github-agent", "get-something")


@pytest.mark.integration
async def test_call_agent_does_not_retry_notimplementederror(monkeypatch):
    """When the RPC is unwired, retrying is pointless — propagate
    immediately so callers see a clear signal rather than
    max_retries * sleep of delay."""
    sleep_spy = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", sleep_spy)

    call_count = {"n": 0}

    async def _unwired(agent, tool, args=None):
        call_count["n"] += 1
        raise NotImplementedError("no stack wired")

    monkeypatch.setattr(_peer_client, "call_peer_tool", _unwired)
    coordinator = BaseMCPAgent("main-coordinator")

    with pytest.raises(NotImplementedError):
        await coordinator.call_agent("github-agent", "get-something")
    assert call_count["n"] == 1, "NotImplementedError should not trigger retries"
    sleep_spy.assert_not_awaited()
