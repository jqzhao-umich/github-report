import asyncio
import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timezone

from agent_mcp_demo.agents.config import Settings
from agent_mcp_demo.agents.utils import get_detroit_timezone, format_datetime
from agent_mcp_demo.agents.base import BaseMCPAgent
from agent_mcp_demo.agents import _peer_client


@pytest.fixture
def mock_settings():
    return Settings(
        github_token="test-token",
        github_org_name="test-org",
        github_iteration_name="Test Sprint",
    )


async def test_base_agent_initialization():
    agent = BaseMCPAgent("test-agent", "1.0.0")
    assert agent.name == "test-agent"
    assert agent.version == "1.0.0"
    await agent.initialize()
    await agent.cleanup()


async def test_agent_call_with_retry(monkeypatch):
    """BaseMCPAgent.call_agent now goes through _peer_client.call_peer_tool
    (MCP 2.0 seam). Verify the retry contract still holds: successful
    call returns immediately; transient failures are retried up to
    max_retries times, then the last attempt's response is returned."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    agent = BaseMCPAgent("test-agent")

    # Successful call: raw text becomes [TextContent(text=...)] under the hood.
    async def _ok(a, t, args=None):
        return "success"

    monkeypatch.setattr(_peer_client, "call_peer_tool", _ok)
    result = await agent.call_agent("other-agent", "test-tool", {"param": "value"})
    assert isinstance(result, list) and result[0].text == "success"

    # Retry-then-succeed contract.
    call_count = {"n": 0}

    async def _flaky(a, t, args=None):
        call_count["n"] += 1
        if call_count["n"] <= 2:
            raise Exception(f"failure {call_count['n']}")
        return "success after retry"

    monkeypatch.setattr(_peer_client, "call_peer_tool", _flaky)
    result = await agent.call_agent("other-agent", "test-tool", {"param": "value"})
    assert result[0].text == "success after retry"
    assert call_count["n"] == 3

def test_timezone_utils():
    # Test Detroit timezone
    tz = get_detroit_timezone()
    assert tz.utcoffset(None).total_seconds() == -4 * 3600
    
    # Test datetime formatting
    dt = datetime(2025, 8, 6, 12, 0, tzinfo=timezone.utc)
    formatted = format_datetime(dt)
    assert "EDT" in formatted
    assert "2025-08-06" in formatted
