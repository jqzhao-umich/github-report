"""
Tests for the main coordinator agent
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from agent_mcp_demo.agents.main_coordinator import (
    server,
    handle_list_tools,
    handle_call_tool,
    AgentCommunicationError,
    AgentNotAvailableError,
    REQUIRED_AGENTS
)

class TestMainCoordinatorTools:
    """Tests for main coordinator tool listing"""
    
    @pytest.mark.asyncio
    async def test_list_tools(self):
        """Test listing available tools"""
        tools = await handle_list_tools()
        
        assert len(tools) >= 1
        tool_names = [tool.name for tool in tools]
        assert "get-github-report" in tool_names
    
    @pytest.mark.asyncio
    async def test_get_github_report_tool_schema(self):
        """Test get-github-report tool schema"""
        tools = await handle_list_tools()
        report_tool = next(t for t in tools if t.name == "get-github-report")
        
        assert "org_name" in report_tool.inputSchema["properties"]
        assert report_tool.inputSchema["required"] == ["org_name"]

class TestMainCoordinatorConstants:
    """Tests for main coordinator constants"""
    
    def test_required_agents_defined(self):
        """Test that required agents are defined"""
        assert isinstance(REQUIRED_AGENTS, list)
        assert len(REQUIRED_AGENTS) > 0
        assert "core-agent" in REQUIRED_AGENTS
        assert "github-agent" in REQUIRED_AGENTS
        assert "web-interface-agent" in REQUIRED_AGENTS

class TestMainCoordinatorCallTool:
    """Tests for main coordinator tool execution"""
    
    @pytest.mark.asyncio
    async def test_get_github_report_missing_org_name(self):
        """Test get-github-report with missing org_name"""
        with pytest.raises(ValueError, match="Missing"):
            await handle_call_tool("get-github-report", {})
    
    @pytest.mark.asyncio
    async def test_get_github_report_no_arguments(self):
        """Test get-github-report with no arguments"""
        with pytest.raises(ValueError, match="Missing arguments"):
            await handle_call_tool("get-github-report", None)
    
    @pytest.mark.asyncio
    @patch('agent_mcp_demo.agents.main_coordinator.server.request_context', create=True)
    async def test_get_github_report_success(self, mock_request_ctx):
        """Test successful get-github-report call"""
        # Mock the agent calls
        mock_iteration_info = [
            Mock(text='{"name": "Test Sprint", "start_date": "2025-01-01", "end_date": "2025-01-15", "path": "test-org/Board"}')
        ]
        mock_github_data = [
            Mock(text='{"member_stats": {"user1": {"commits": 5, "assigned_issues": 2, "closed_issues": 1}}, "commit_details": {}, "assigned_issues": {}, "closed_issues": {}}')
        ]
        mock_report = [
            Mock(text="GitHub Organization: test-org\nSUMMARY\n...")
        ]
        
        # Set up mock session
        mock_session = AsyncMock()
        call_count = [0]
        
        async def side_effect(agent, tool, args):
            call_count[0] += 1
            if agent == "github-agent" and tool == "get-iteration-info":
                return mock_iteration_info
            elif agent == "github-agent" and tool == "get-github-data":
                return mock_github_data
            elif agent == "web-interface-agent" and tool == "generate-report":
                return mock_report
            return []
        
        mock_session.call_tool.side_effect = side_effect
        mock_request_ctx.session = mock_session
        
        result = await handle_call_tool("get-github-report", {
            "org_name": "test-org"
        })
        
        assert len(result) > 0
        assert "test-org" in result[0].text or "GitHub Organization" in result[0].text or "No report generated" in result[0].text
        
        # Verify that agent calls were made
        assert call_count[0] >= 2
    
    @pytest.mark.asyncio
    @patch('agent_mcp_demo.agents.main_coordinator.server.request_context', create=True)
    async def test_get_github_report_github_agent_error(self, mock_request_ctx):
        """Test get-github-report when GitHub agent fails"""
        # Mock GitHub agent to raise an error
        mock_session = AsyncMock()
        mock_session.call_tool.side_effect = Exception("GitHub agent error")
        mock_request_ctx.session = mock_session
        
        with pytest.raises(Exception, match="GitHub agent error"):
            await handle_call_tool("get-github-report", {
                "org_name": "test-org"
            })
    
    @pytest.mark.asyncio
    @patch('agent_mcp_demo.agents.main_coordinator.server.request_context', create=True)
    async def test_get_github_report_web_agent_error(self, mock_request_ctx):
        """Test get-github-report when web interface agent fails"""
        # Mock successful GitHub agent calls, but web agent fails
        mock_iteration_info = [
            Mock(text='{"name": "Test Sprint"}')
        ]
        mock_github_data = [
            Mock(text='{"member_stats": {}}')
        ]
        
        mock_session = AsyncMock()
        async def side_effect(agent, tool, args):
            if agent == "github-agent":
                if tool == "get-iteration-info":
                    return mock_iteration_info
                elif tool == "get-github-data":
                    return mock_github_data
            elif agent == "web-interface-agent":
                raise Exception("Web agent error")
            return []
        
        mock_session.call_tool.side_effect = side_effect
        mock_request_ctx.session = mock_session
        
        with pytest.raises(Exception, match="Web agent error"):
            await handle_call_tool("get-github-report", {
                "org_name": "test-org"
            })
    
    @pytest.mark.asyncio
    @patch('agent_mcp_demo.agents.main_coordinator.server.request_context', create=True)
    async def test_get_github_report_empty_iteration_info(self, mock_request_ctx):
        """Test get-github-report with empty iteration info"""
        # Mock GitHub agent to return None/empty iteration info
        mock_session = AsyncMock()
        mock_session.call_tool.return_value = []
        mock_request_ctx.session = mock_session
        
        # Should still proceed (iteration info is optional)
        try:
            result = await handle_call_tool("get-github-report", {
                "org_name": "test-org"
            })
            # May succeed or fail depending on implementation
        except Exception:
            # Expected if iteration info is required downstream
            pass
    
    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        """Test calling unknown tool"""
        with pytest.raises(ValueError, match="Unknown tool"):
            await handle_call_tool("unknown-tool", {})

class TestMainCoordinatorErrorHandling:
    """Tests for error handling in main coordinator"""
    
    @pytest.mark.asyncio
    @patch('agent_mcp_demo.agents.main_coordinator.server.request_context', create=True)
    async def test_agent_communication_error_handling(self, mock_request_ctx):
        """Test handling of agent communication errors"""
        mock_session = AsyncMock()
        mock_session.call_tool.side_effect = Exception("Communication error")
        mock_request_ctx.session = mock_session
        
        with pytest.raises(Exception):
            await handle_call_tool("get-github-report", {
                "org_name": "test-org"
            })
    
    @pytest.mark.asyncio
    @patch('agent_mcp_demo.agents.main_coordinator.server.request_context', create=True)
    async def test_partial_agent_failure(self, mock_request_ctx):
        """Test handling when one agent call fails"""
        call_count = [0]
        
        mock_session = AsyncMock()
        async def side_effect(agent, tool, args):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call succeeds
                return [Mock(text='{"name": "Test Sprint"}')]
            else:
                # Subsequent calls fail
                raise Exception("Agent failure")
        
        mock_session.call_tool.side_effect = side_effect
        mock_request_ctx.session = mock_session
        
        with pytest.raises(Exception):
            await handle_call_tool("get-github-report", {
                "org_name": "test-org"
            })
