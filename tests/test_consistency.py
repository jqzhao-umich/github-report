"""
Tests to verify consistency between GitHub Actions (server.py) and MCP Agent (github_agent.py)
This ensures both paths use shared utilities identically.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestSharedUtilityUsage:
    """Test that both server.py and github_agent.py use shared utilities correctly"""
    
    @patch('agent_mcp_demo.server.Github')
    @patch('agent_mcp_demo.server.collect_members_and_emails')
    @patch('agent_mcp_demo.server.initialize_detail_structures')
    @patch('agent_mcp_demo.server.collect_commit_metrics')
    @patch('agent_mcp_demo.server.collect_issue_metrics')
    @patch('agent_mcp_demo.server.collect_pr_metrics')
    @pytest.mark.asyncio
    async def test_server_uses_shared_utilities(
        self,
        mock_pr_metrics,
        mock_issue_metrics,
        mock_commit_metrics,
        mock_init_details,
        mock_collect_members,
        mock_github
    ):
        """Test that server.py calls all shared utilities"""
        from agent_mcp_demo.server import github_report_api
        
        # Setup mocks
        mock_user = Mock()
        mock_user.login = "test-bot"
        mock_github_instance = Mock()
        mock_github_instance.get_user.return_value = mock_user
        
        mock_org = Mock()
        mock_org.login = "test-org"
        mock_org.get_repos.return_value = []
        mock_github_instance.get_organization.return_value = mock_org
        mock_github.return_value = mock_github_instance
        
        # Mock utility returns
        mock_collect_members.return_value = (
            {"user1": {"commits": 0, "assigned_issues": 0, "closed_issues": 0}},
            {"user1@example.com": "user1"},
            ["user1"]
        )
        mock_init_details.return_value = {
            'commit_details': {},
            'assigned_issues': {},
            'closed_issues': {},
            'pr_created': {},
            'pr_reviewed': {},
            'pr_merged': {},
            'pr_commented': {}
        }
        mock_commit_metrics.return_value = 0
        mock_issue_metrics.return_value = (0, 0)
        mock_pr_metrics.return_value = ({}, {}, {}, {})
        
        # Set environment variables
        os.environ["GITHUB_TOKEN"] = "test-token"
        os.environ["GITHUB_ORG_NAME"] = "test-org"
        
        try:
            # Call the function
            result = await github_report_api()
            
            # Verify shared utilities were called
            mock_collect_members.assert_called_once()
            mock_init_details.assert_called_once()
            
            # Verify collect_members_and_emails was called with exclude_user_login
            args, kwargs = mock_collect_members.call_args
            assert 'exclude_user_login' in kwargs
            assert kwargs['exclude_user_login'] == 'test-bot'
            
        finally:
            if "GITHUB_TOKEN" in os.environ:
                del os.environ["GITHUB_TOKEN"]
            if "GITHUB_ORG_NAME" in os.environ:
                del os.environ["GITHUB_ORG_NAME"]
    
    @patch('agent_mcp_demo.agents.github_agent.Github')
    @patch('agent_mcp_demo.agents.github_agent.collect_members_and_emails')
    @patch('agent_mcp_demo.agents.github_agent.initialize_detail_structures')
    @patch('agent_mcp_demo.agents.github_agent.collect_commit_metrics')
    @patch('agent_mcp_demo.agents.github_agent.collect_issue_metrics')
    @patch('agent_mcp_demo.agents.github_agent.collect_pr_metrics')
    @pytest.mark.asyncio
    async def test_github_agent_uses_shared_utilities(
        self,
        mock_pr_metrics,
        mock_issue_metrics,
        mock_commit_metrics,
        mock_init_details,
        mock_collect_members,
        mock_github
    ):
        """Test that github_agent.py calls all shared utilities"""
        from agent_mcp_demo.agents.github_agent import handle_call_tool
        
        # Setup mocks
        mock_user = Mock()
        mock_user.login = "test-bot"
        mock_user.get_organization_membership.return_value = True
        
        mock_github_instance = Mock()
        mock_github_instance.get_user.return_value = mock_user
        
        mock_org = Mock()
        mock_org.login = "test-org"
        mock_org.get_repos.return_value = []
        mock_github_instance.get_organization.return_value = mock_org
        mock_github.return_value = mock_github_instance
        
        # Mock utility returns
        mock_collect_members.return_value = (
            {"user1": {"commits": 0, "assigned_issues": 0, "closed_issues": 0}},
            {"user1@example.com": "user1"},
            ["user1"]
        )
        mock_init_details.return_value = {
            'commit_details': {"user1": []},
            'assigned_issues': {"user1": []},
            'closed_issues': {"user1": []},
            'pr_created': {"user1": []},
            'pr_reviewed': {"user1": []},
            'pr_merged': {"user1": []},
            'pr_commented': {"user1": []}
        }
        mock_commit_metrics.return_value = 0
        mock_issue_metrics.return_value = (0, 0)
        mock_pr_metrics.return_value = (
            {"user1": []},
            {"user1": []},
            {"user1": []},
            {"user1": []}
        )
        
        # Set environment variable
        os.environ["GITHUB_TOKEN"] = "test-token"
        
        try:
            # Call the tool
            result = await handle_call_tool("get-github-data", {
                "org_name": "test-org",
                "iteration_info": None
            })
            
            # Verify shared utilities were called
            mock_collect_members.assert_called_once()
            mock_init_details.assert_called_once()
            
            # Verify collect_members_and_emails was called with exclude_user_login
            args, kwargs = mock_collect_members.call_args
            assert 'exclude_user_login' in kwargs
            assert kwargs['exclude_user_login'] == 'test-bot'
            
        finally:
            if "GITHUB_TOKEN" in os.environ:
                del os.environ["GITHUB_TOKEN"]


class TestConsistentUserExclusion:
    """Test that both paths exclude the current user consistently"""
    
    @patch('agent_mcp_demo.server.Github')
    @patch('agent_mcp_demo.server.collect_members_and_emails')
    @pytest.mark.asyncio
    async def test_server_excludes_current_user(self, mock_collect_members, mock_github):
        """Test that server.py excludes current_user_login"""
        from agent_mcp_demo.server import github_report_api
        
        mock_user = Mock()
        mock_user.login = "github-bot"
        mock_github_instance = Mock()
        mock_github_instance.get_user.return_value = mock_user
        
        mock_org = Mock()
        mock_org.login = "test-org"
        mock_org.get_repos.return_value = []
        mock_github_instance.get_organization.return_value = mock_org
        mock_github.return_value = mock_github_instance
        
        mock_collect_members.return_value = ({}, {}, [])
        
        os.environ["GITHUB_TOKEN"] = "test-token"
        os.environ["GITHUB_ORG_NAME"] = "test-org"
        
        try:
            await github_report_api()
            
            # Verify exclude_user_login was passed
            call_args = mock_collect_members.call_args
            assert call_args[1]['exclude_user_login'] == 'github-bot'
        finally:
            if "GITHUB_TOKEN" in os.environ:
                del os.environ["GITHUB_TOKEN"]
            if "GITHUB_ORG_NAME" in os.environ:
                del os.environ["GITHUB_ORG_NAME"]
    
    @patch('agent_mcp_demo.agents.github_agent.Github')
    @patch('agent_mcp_demo.agents.github_agent.collect_members_and_emails')
    @pytest.mark.asyncio
    async def test_github_agent_excludes_current_user(self, mock_collect_members, mock_github):
        """Test that github_agent.py excludes current_user_login"""
        from agent_mcp_demo.agents.github_agent import handle_call_tool
        
        mock_user = Mock()
        mock_user.login = "github-bot"
        mock_user.get_organization_membership.return_value = True
        
        mock_github_instance = Mock()
        mock_github_instance.get_user.return_value = mock_user
        
        mock_org = Mock()
        mock_org.login = "test-org"
        mock_org.get_repos.return_value = []
        mock_github_instance.get_organization.return_value = mock_org
        mock_github.return_value = mock_github_instance
        
        mock_collect_members.return_value = ({}, {}, [])
        
        os.environ["GITHUB_TOKEN"] = "test-token"
        
        try:
            await handle_call_tool("get-github-data", {
                "org_name": "test-org",
                "iteration_info": None
            })
            
            # Verify exclude_user_login was passed
            call_args = mock_collect_members.call_args
            assert call_args[1]['exclude_user_login'] == 'github-bot'
        finally:
            if "GITHUB_TOKEN" in os.environ:
                del os.environ["GITHUB_TOKEN"]


class TestConsistentVariableNaming:
    """Test that both paths use consistent variable naming"""
    
    def test_server_uses_current_user_naming(self):
        """Verify server.py uses 'current_user' and 'current_user_login'"""
        with open('src/agent_mcp_demo/server.py', 'r') as f:
            content = f.read()
            
        # Should use current_user not just user
        assert 'current_user = g.get_user()' in content
        assert 'current_user_login = current_user.login' in content
    
    def test_github_agent_uses_current_user_naming(self):
        """Verify github_agent.py uses 'current_user' and 'current_user_login'"""
        with open('src/agent_mcp_demo/agents/github_agent.py', 'r') as f:
            content = f.read()
            
        # Should use current_user not just user
        assert 'current_user = g.get_user()' in content
        assert 'current_user_login = current_user.login' in content


class TestPRMetricsMerging:
    """Test that both paths merge PR metrics with safety checks"""
    
    @patch('agent_mcp_demo.server.Github')
    @patch('agent_mcp_demo.server.collect_pr_metrics')
    @pytest.mark.asyncio
    async def test_server_pr_merging_has_safety_checks(self, mock_pr_metrics, mock_github):
        """Test that server.py safely merges PR metrics"""
        from agent_mcp_demo.server import github_report_api
        
        mock_user = Mock()
        mock_user.login = "test-bot"
        mock_github_instance = Mock()
        mock_github_instance.get_user.return_value = mock_user
        
        mock_org = Mock()
        mock_org.login = "test-org"
        
        # Create a repo that will return PR metrics
        mock_repo = Mock()
        mock_repo.name = "test-repo"
        mock_repo.archived = False
        mock_org.get_repos.return_value = [mock_repo]
        
        mock_github_instance.get_organization.return_value = mock_org
        mock_github.return_value = mock_github_instance
        
        # Return PR metrics for new user not in initial dict
        mock_pr_metrics.return_value = (
            {"new_user": [{"number": 1}]},  # pr_created
            {},  # pr_reviewed
            {},  # pr_merged
            {}   # pr_commented
        )
        
        os.environ["GITHUB_TOKEN"] = "test-token"
        os.environ["GITHUB_ORG_NAME"] = "test-org"
        
        try:
            # This should not raise KeyError
            result = await github_report_api()
            assert result is not None
        finally:
            if "GITHUB_TOKEN" in os.environ:
                del os.environ["GITHUB_TOKEN"]
            if "GITHUB_ORG_NAME" in os.environ:
                del os.environ["GITHUB_ORG_NAME"]
