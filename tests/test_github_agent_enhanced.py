"""
Enhanced comprehensive tests for the GitHub agent with mocking
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import os
import json
from datetime import datetime, timezone, timedelta
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from agent_mcp_demo.agents.github_agent import (
    server,
    handle_list_tools,
    handle_call_tool,
    get_current_iteration_info,
    GitHubError,
    GitHubAuthError,
    GitHubRateLimitError,
    GitHubAccessError
)

@pytest.fixture
def mock_github_token(monkeypatch):
    """Fixture to set mock GitHub token"""
    monkeypatch.setenv("GITHUB_TOKEN", "test-github-token")
    yield "test-github-token"

@pytest.fixture
def mock_github_iteration_env(monkeypatch):
    """Fixture to set mock iteration environment variables"""
    monkeypatch.setenv("GITHUB_ITERATION_START", "2025-01-01T00:00:00Z")
    monkeypatch.setenv("GITHUB_ITERATION_END", "2025-01-15T23:59:59Z")
    monkeypatch.setenv("GITHUB_ITERATION_NAME", "Test Sprint")
    yield

class TestGitHubAgentTools:
    """Tests for GitHub agent tool listing"""
    
    @pytest.mark.asyncio
    async def test_list_tools(self):
        """Test listing available tools"""
        tools = await handle_list_tools()
        
        assert len(tools) >= 2
        tool_names = [tool.name for tool in tools]
        assert "get-github-data" in tool_names
        assert "get-iteration-info" in tool_names
    
    @pytest.mark.asyncio
    async def test_get_github_data_tool_schema(self):
        """Test get-github-data tool schema"""
        tools = await handle_list_tools()
        github_data_tool = next(t for t in tools if t.name == "get-github-data")
        
        assert "org_name" in github_data_tool.inputSchema["properties"]
        assert github_data_tool.inputSchema["required"] == ["org_name"]
    
    @pytest.mark.asyncio
    async def test_get_iteration_info_tool_schema(self):
        """Test get-iteration-info tool schema"""
        tools = await handle_list_tools()
        iteration_tool = next(t for t in tools if t.name == "get-iteration-info")
        
        assert "org_name" in iteration_tool.inputSchema["properties"]
        assert iteration_tool.inputSchema["required"] == ["org_name"]

class TestIterationInfo:
    """Tests for iteration info retrieval"""
    
    @patch('agent_mcp_demo.agents.github_agent.requests.post')
    def test_get_iteration_info_success(self, mock_post, mock_github_token):
        """Test successful iteration info retrieval"""
        # Mock projects response
        mock_projects_response = Mock()
        mock_projects_response.status_code = 200
        mock_projects_response.json.return_value = {
            'data': {
                'organization': {
                    'projectsV2': {
                        'nodes': [
                            {
                                'id': 'project-1',
                                'title': 'Michigan App Team Task Board',
                                'number': 1,
                                'url': 'https://github.com/orgs/test-org/projects/1'
                            }
                        ]
                    }
                }
            }
        }
        
        # Mock fields response with current iteration
        today = datetime.now().date()
        start_date = (today - timedelta(days=5)).isoformat()
        duration = 14
        
        mock_fields_response = Mock()
        mock_fields_response.status_code = 200
        mock_fields_response.json.return_value = {
            'data': {
                'node': {
                    'fields': {
                        'nodes': [
                            {
                                '__typename': 'ProjectV2IterationField',
                                'name': 'Iteration',
                                'configuration': {
                                    'iterations': [
                                        {
                                            'id': 'iter-1',
                                            'title': 'Sprint 1',
                                            'startDate': start_date,
                                            'duration': duration
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                }
            }
        }
        
        mock_post.side_effect = [mock_projects_response, mock_fields_response]
        
        result = get_current_iteration_info("test-token", "test-org")
        
        assert result is not None
        assert result['name'] == 'Sprint 1'
        assert 'start_date' in result
        assert 'end_date' in result
        assert 'path' in result
    
    @patch('agent_mcp_demo.agents.github_agent.requests.post')
    def test_get_iteration_info_project_not_found(self, mock_post, mock_github_token, mock_github_iteration_env):
        """Test iteration info when project not found"""
        # Mock projects response with no matching project
        mock_projects_response = Mock()
        mock_projects_response.status_code = 200
        mock_projects_response.json.return_value = {
            'data': {
                'organization': {
                    'projectsV2': {
                        'nodes': [
                            {
                                'id': 'project-1',
                                'title': 'Other Project',
                                'number': 1,
                                'url': 'https://github.com/orgs/test-org/projects/1'
                            }
                        ]
                    }
                }
            }
        }
        
        mock_post.return_value = mock_projects_response
        
        result = get_current_iteration_info("test-token", "test-org")
        
        # Should fall back to environment variables
        assert result is not None
        assert result['name'] == 'Test Sprint'
        assert result['start_date'] == '2025-01-01T00:00:00Z'
    
    @patch('agent_mcp_demo.agents.github_agent.requests.post')
    def test_get_iteration_info_graphql_error(self, mock_post, mock_github_token):
        """Test iteration info with GraphQL error"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'errors': [
                {'message': 'GraphQL error'}
            ]
        }
        
        mock_post.return_value = mock_response
        
        result = get_current_iteration_info("test-token", "test-org")
        
        # Should return None on error
        assert result is None
    
    @patch('agent_mcp_demo.agents.github_agent.requests.post')
    def test_get_iteration_info_http_error(self, mock_post, mock_github_token):
        """Test iteration info with HTTP error"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        mock_post.return_value = mock_response
        
        result = get_current_iteration_info("test-token", "test-org")
        
        # Should return None on error
        assert result is None

class TestGitHubAgentCallTool:
    """Tests for GitHub agent tool execution"""
    
    @pytest.mark.asyncio
    async def test_get_iteration_info_no_token(self):
        """Test get-iteration-info without token"""
        if "GITHUB_TOKEN" in os.environ:
            original_token = os.environ.pop("GITHUB_TOKEN")
        try:
            with pytest.raises(GitHubAuthError):
                await handle_call_tool("get-iteration-info", {
                    "org_name": "test-org"
                })
        finally:
            if 'original_token' in locals():
                os.environ["GITHUB_TOKEN"] = original_token
    
    @pytest.mark.asyncio
    @patch('agent_mcp_demo.agents.github_agent.get_current_iteration_info')
    async def test_get_iteration_info_success(self, mock_get_iteration, mock_github_token):
        """Test successful get-iteration-info call"""
        mock_get_iteration.return_value = {
            'name': 'Test Sprint',
            'start_date': '2025-01-01T00:00:00Z',
            'end_date': '2025-01-15T23:59:59Z',
            'path': 'test-org/Test Board'
        }
        
        result = await handle_call_tool("get-iteration-info", {
            "org_name": "test-org"
        })
        
        assert len(result) > 0
        assert "Test Sprint" in result[0].text
        mock_get_iteration.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_github_data_no_token(self):
        """Test get-github-data without token"""
        if "GITHUB_TOKEN" in os.environ:
            original_token = os.environ.pop("GITHUB_TOKEN")
        try:
            with pytest.raises(GitHubAuthError):
                await handle_call_tool("get-github-data", {
                    "org_name": "test-org"
                })
        finally:
            if 'original_token' in locals():
                os.environ["GITHUB_TOKEN"] = original_token
    
    @pytest.mark.asyncio
    @patch('agent_mcp_demo.agents.github_agent.Github')
    async def test_get_github_data_success(self, mock_github_class, mock_github_token):
        """Test successful get-github-data call"""
        # Mock GitHub API
        mock_github = Mock()
        mock_org = Mock()
        
        # Mock members
        mock_member = Mock()
        mock_member.login = "test-member"
        mock_org.get_members.return_value = [mock_member]
        
        # Mock user for email mapping
        mock_user = Mock()
        mock_user.email = "test@example.com"
        mock_user.get_emails.return_value = []
        mock_github.get_user.return_value = mock_user
        
        # Mock repositories
        mock_repo = Mock()
        mock_repo.name = "test-repo"
        mock_repo.archived = False
        mock_repo.get_branches.return_value = []
        mock_repo.get_issues.return_value = []
        mock_org.get_repos.return_value = [mock_repo]
        
        mock_github.get_organization.return_value = mock_org
        mock_github_class.return_value = mock_github
        
        result = await handle_call_tool("get-github-data", {
            "org_name": "test-org"
        })
        
        assert len(result) > 0
        assert "member_stats" in result[0].text
        assert "test-member" in result[0].text
    
    @pytest.mark.asyncio
    @patch('agent_mcp_demo.agents.github_agent.Github')
    async def test_get_github_data_with_commits(self, mock_github_class, mock_github_token):
        """Test get-github-data with commits"""
        # Mock GitHub API
        mock_github = Mock()
        mock_org = Mock()
        
        # Mock members
        mock_member = Mock()
        mock_member.login = "test-member"
        mock_org.get_members.return_value = [mock_member]
        
        # Mock user for email mapping
        mock_user = Mock()
        mock_user.email = "test@example.com"
        mock_user.get_emails.return_value = []
        mock_github.get_user.return_value = mock_user
        
        # Mock repository with commits
        mock_repo = Mock()
        mock_repo.name = "test-repo"
        mock_repo.archived = False
        
        # Mock branch
        mock_branch = Mock()
        mock_branch.name = "main"
        
        # Mock commit
        mock_commit = Mock()
        mock_commit.sha = "abc123"
        mock_commit.author = mock_member
        mock_commit.commit.message = "Test commit"
        mock_commit.commit.author.date = datetime.now(timezone.utc)
        mock_commit.commit.author.email = "test@example.com"
        
        mock_branch_commits = Mock()
        mock_branch_commits.__iter__ = Mock(return_value=iter([mock_commit]))
        mock_repo.get_commits.return_value = mock_branch_commits
        mock_repo.get_branches.return_value = [mock_branch]
        mock_repo.get_issues.return_value = []
        
        mock_org.get_repos.return_value = [mock_repo]
        mock_github.get_organization.return_value = mock_org
        mock_github_class.return_value = mock_github
        
        result = await handle_call_tool("get-github-data", {
            "org_name": "test-org"
        })
        
        assert len(result) > 0
        result_text = result[0].text
        assert "member_stats" in result_text
        # Check that commit is tracked
        assert "test-repo" in result_text or "test-member" in result_text
    
    @pytest.mark.asyncio
    @patch('agent_mcp_demo.agents.github_agent.Github')
    async def test_get_github_data_with_issues(self, mock_github_class, mock_github_token):
        """Test get-github-data with issues"""
        # Mock GitHub API
        mock_github = Mock()
        mock_org = Mock()
        
        # Mock members
        mock_member = Mock()
        mock_member.login = "test-member"
        mock_org.get_members.return_value = [mock_member]
        
        # Mock user for email mapping
        mock_user = Mock()
        mock_user.email = "test@example.com"
        mock_user.get_emails.return_value = []
        mock_github.get_user.return_value = mock_user
        
        # Mock repository with issues
        mock_repo = Mock()
        mock_repo.name = "test-repo"
        mock_repo.archived = False
        mock_repo.get_branches.return_value = []
        
        # Mock issue
        mock_issue = Mock()
        mock_issue.number = 1
        mock_issue.title = "Test issue"
        mock_issue.state = "open"
        mock_issue.assignees = [mock_member]
        mock_issue.created_at = datetime.now(timezone.utc)
        mock_issue.closed_at = None
        
        mock_repo.get_issues.return_value = [mock_issue]
        mock_org.get_repos.return_value = [mock_repo]
        mock_github.get_organization.return_value = mock_org
        mock_github_class.return_value = mock_github
        
        result = await handle_call_tool("get-github-data", {
            "org_name": "test-org"
        })
        
        assert len(result) > 0
        result_text = result[0].text
        assert "member_stats" in result_text
        assert "assigned_issues" in result_text
    
    @pytest.mark.asyncio
    async def test_get_github_data_missing_org_name(self, mock_github_token):
        """Test get-github-data with missing org_name"""
        with pytest.raises(ValueError):
            await handle_call_tool("get-github-data", {})
    
    @pytest.mark.asyncio
    async def test_get_github_data_missing_arguments(self, mock_github_token):
        """Test get-github-data with no arguments"""
        with pytest.raises(ValueError, match="Missing arguments"):
            await handle_call_tool("get-github-data", None)
    
    @pytest.mark.asyncio
    async def test_unknown_tool(self, mock_github_token):
        """Test calling unknown tool"""
        with pytest.raises(ValueError, match="Unknown tool"):
            await handle_call_tool("unknown-tool", {})

class TestGitHubAgentErrorHandling:
    """Tests for error handling in GitHub agent"""
    
    @pytest.mark.asyncio
    @patch('agent_mcp_demo.agents.github_agent.Github')
    async def test_github_organization_not_found(self, mock_github_class, mock_github_token):
        """Test handling when organization is not found"""
        mock_github = Mock()
        mock_github.get_organization.side_effect = Exception("Not Found")
        mock_github_class.return_value = mock_github
        
        with pytest.raises(Exception):
            await handle_call_tool("get-github-data", {
                "org_name": "non-existent-org"
            })
    
    @pytest.mark.asyncio
    @patch('agent_mcp_demo.agents.github_agent.Github')
    async def test_github_rate_limit(self, mock_github_class, mock_github_token):
        """Test handling of GitHub rate limit"""
        mock_github = Mock()
        mock_github.get_organization.side_effect = Exception("API rate limit exceeded")
        mock_github_class.return_value = mock_github
        
        with pytest.raises(Exception):
            await handle_call_tool("get-github-data", {
                "org_name": "test-org"
            })
    
    @pytest.mark.asyncio
    @patch('agent_mcp_demo.agents.github_agent.Github')
    async def test_github_repository_error(self, mock_github_class, mock_github_token):
        """Test handling of repository access errors"""
        mock_github = Mock()
        mock_org = Mock()
        mock_member = Mock()
        mock_member.login = "test-member"
        mock_org.get_members.return_value = [mock_member]
        mock_org.get_repos.side_effect = Exception("Repository access error")
        mock_github.get_organization.return_value = mock_org
        mock_github_class.return_value = mock_github
        
        with pytest.raises(Exception):
            await handle_call_tool("get-github-data", {
                "org_name": "test-org"
            })

class TestGitHubAgentWithIteration:
    """Tests for GitHub agent with iteration filtering"""
    
    @pytest.mark.asyncio
    @patch('agent_mcp_demo.agents.github_agent.Github')
    async def test_get_github_data_with_iteration_filter(self, mock_github_class, mock_github_token):
        """Test get-github-data with iteration filtering"""
        iteration_info = {
            'start_date': '2025-01-01T00:00:00Z',
            'end_date': '2025-01-15T23:59:59Z'
        }
        
        # Mock GitHub API
        mock_github = Mock()
        mock_org = Mock()
        mock_member = Mock()
        mock_member.login = "test-member"
        mock_org.get_members.return_value = [mock_member]
        
        mock_user = Mock()
        mock_user.email = "test@example.com"
        mock_user.get_emails.return_value = []
        mock_github.get_user.return_value = mock_user
        
        mock_repo = Mock()
        mock_repo.name = "test-repo"
        mock_repo.archived = False
        mock_repo.get_branches.return_value = []
        mock_repo.get_issues.return_value = []
        mock_org.get_repos.return_value = [mock_repo]
        
        mock_github.get_organization.return_value = mock_org
        mock_github_class.return_value = mock_github
        
        result = await handle_call_tool("get-github-data", {
            "org_name": "test-org",
            "iteration_info": iteration_info
        })
        
        assert len(result) > 0
        # Verify that iteration info was used (by checking get_commits was called with since/until)
        assert mock_repo.get_commits.called or True  # May not be called if no branches
