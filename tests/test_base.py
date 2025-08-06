import pytest
from unittest.mock import Mock, AsyncMock
import os
import json
from datetime import datetime, timezone
from agent_mcp_demo.agents.config import Settings
from agent_mcp_demo.agents.utils import get_detroit_timezone, format_datetime
from agent_mcp_demo.agents.base import BaseMCPAgent

@pytest.fixture
def mock_settings():
    return Settings(
        github_token="test-token",
        github_org_name="test-org",
        github_iteration_name="Test Sprint"
    )

@pytest.fixture
def mock_agent():
    agent = BaseMCPAgent("test-agent")
    agent.server.request_context = Mock()
    agent.server.request_context.session = AsyncMock()
    return agent

async def test_base_agent_initialization():
    agent = BaseMCPAgent("test-agent", "1.0.0")
    assert agent.name == "test-agent"
    assert agent.version == "1.0.0"
    
    # Test initialization
    await agent.initialize()
    # Test cleanup
    await agent.cleanup()

async def test_agent_call_with_retry():
    agent = BaseMCPAgent("test-agent")
    agent.server.request_context = Mock()
    session_mock = AsyncMock()
    agent.server.request_context.session = session_mock
    
    # Test successful call
    session_mock.call_tool.return_value = ["success"]
    result = await agent.call_agent("other-agent", "test-tool", {"param": "value"})
    assert result == ["success"]
    
    # Test retry on failure
    session_mock.call_tool.side_effect = [
        Exception("First failure"),
        Exception("Second failure"),
        ["success after retry"]
    ]
    result = await agent.call_agent("other-agent", "test-tool", {"param": "value"})
    assert result == ["success after retry"]
    assert session_mock.call_tool.call_count == 3

def test_timezone_utils():
    # Test Detroit timezone
    tz = get_detroit_timezone()
    assert tz.utcoffset(None).total_seconds() == -4 * 3600
    
    # Test datetime formatting
    dt = datetime(2025, 8, 6, 12, 0, tzinfo=timezone.utc)
    formatted = format_datetime(dt)
    assert "EDT" in formatted
    assert "2025-08-06" in formatted
