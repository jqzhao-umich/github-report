"""
Comprehensive tests for the main server.py FastAPI application
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
import os
import json
from datetime import datetime, timezone, timedelta
from github import Github

# Import the server app
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from agent_mcp_demo.server import app, get_current_iteration_info

client = TestClient(app)

@pytest.fixture
def mock_github_token(monkeypatch):
    """Fixture to set mock GitHub token"""
    monkeypatch.setenv("GITHUB_TOKEN", "test-github-token")
    yield "test-github-token"
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

@pytest.fixture
def mock_org_name(monkeypatch):
    """Fixture to set mock organization name"""
    monkeypatch.setenv("GITHUB_ORG_NAME", "test-org")
    yield "test-org"
    monkeypatch.delenv("GITHUB_ORG_NAME", raising=False)

@pytest.fixture
def mock_iteration_env(monkeypatch):
    """Fixture to set mock iteration environment variables"""
    monkeypatch.setenv("GITHUB_ITERATION_START", "2025-01-01T00:00:00Z")
    monkeypatch.setenv("GITHUB_ITERATION_END", "2025-01-15T23:59:59Z")
    monkeypatch.setenv("GITHUB_ITERATION_NAME", "Test Sprint")
    yield
    monkeypatch.delenv("GITHUB_ITERATION_START", raising=False)
    monkeypatch.delenv("GITHUB_ITERATION_END", raising=False)
    monkeypatch.delenv("GITHUB_ITERATION_NAME", raising=False)

class TestRootEndpoint:
    """Tests for the root endpoint"""
    
    def test_root_endpoint_returns_html(self):
        """Test that root endpoint returns HTML"""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "GitHub Report" in response.text
    
    def test_root_endpoint_contains_refresh_button(self):
        """Test that root endpoint contains refresh button"""
        response = client.get("/")
        assert '<button class="refresh-btn"' in response.text
        assert 'loadReport()' in response.text
    
    def test_root_endpoint_contains_report_container(self):
        """Test that root endpoint contains report container"""
        response = client.get("/")
        assert '<div id="report-container">' in response.text
    
    def test_root_endpoint_contains_javascript(self):
        """Test that root endpoint contains JavaScript"""
        response = client.get("/")
        assert 'async function loadReport()' in response.text
        assert 'window.onload = loadReport' in response.text

class TestGitHubReportAPI:
    """Tests for the GitHub report API endpoint"""
    
    def test_github_report_no_token(self):
        """Test that report endpoint returns error when token is missing"""
        # Remove token if it exists
        if "GITHUB_TOKEN" in os.environ:
            original_token = os.environ.pop("GITHUB_TOKEN")
        
        try:
            response = client.get("/api/github-report")
            assert response.status_code == 200
            assert "GitHub token not set" in response.text
        finally:
            # Restore token if it existed
            if 'original_token' in locals():
                os.environ["GITHUB_TOKEN"] = original_token
    
    def test_github_report_no_org(self, mock_github_token):
        """Test that report endpoint returns error when org name is missing"""
        if "GITHUB_ORG_NAME" in os.environ:
            original_org = os.environ.pop("GITHUB_ORG_NAME")
        
        try:
            response = client.get("/api/github-report")
            assert response.status_code == 200
            assert "organization name not set" in response.text
        finally:
            if 'original_org' in locals():
                os.environ["GITHUB_ORG_NAME"] = original_org
    
    @patch('agent_mcp_demo.server.Github')
    def test_github_report_authentication_failure(self, mock_github_class, mock_github_token, mock_org_name):
        """Test that report endpoint handles authentication failure"""
        # Mock GitHub authentication failure
        mock_github = Mock()
        mock_github_class.return_value = mock_github
        mock_github.get_user.side_effect = Exception("Bad credentials")
        
        response = client.get("/api/github-report")
        assert response.status_code == 200
        assert "authentication failed" in response.text.lower()
    
    @patch('agent_mcp_demo.server.Github')
    def test_github_report_org_access_failure(self, mock_github_class, mock_github_token, mock_org_name):
        """Test that report endpoint handles organization access failure"""
        # Mock GitHub organization access failure
        mock_github = Mock()
        mock_user = Mock()
        mock_user.login = "test-user"
        mock_github.get_user.return_value = mock_user
        mock_github.get_organization.side_effect = Exception("Organization not found")
        mock_github_class.return_value = mock_github
        
        response = client.get("/api/github-report")
        assert response.status_code == 200
        assert "error accessing organization" in response.text.lower()
    
    @patch('agent_mcp_demo.server.Github')
    @patch('agent_mcp_demo.server.get_current_iteration_info')
    def test_github_report_success(
        self, 
        mock_iteration_info, 
        mock_github_class, 
        mock_github_token, 
        mock_org_name
    ):
        """Test successful report generation"""
        # Mock iteration info
        mock_iteration_info.return_value = {
            'name': 'Test Sprint',
            'start_date': '2025-01-01T00:00:00Z',
            'end_date': '2025-01-15T23:59:59Z',
            'path': 'test-org/Test Board'
        }
        
        # Mock GitHub API
        mock_github = Mock()
        mock_user = Mock()
        mock_user.login = "test-user"
        mock_github.get_user.return_value = mock_user
        
        mock_org = Mock()
        mock_member = Mock()
        mock_member.login = "test-member"
        mock_org.get_members.return_value = [mock_member]
        mock_org.get_repos.return_value = []
        mock_github.get_organization.return_value = mock_org
        mock_github_class.return_value = mock_github
        
        response = client.get("/api/github-report")
        assert response.status_code == 200
        assert "GitHub Organization: test-org" in response.text
        assert "SUMMARY" in response.text
        assert "Processed 0 repositories" in response.text
    
    @patch('agent_mcp_demo.server.Github')
    @patch('agent_mcp_demo.server.get_current_iteration_info')
    def test_github_report_with_commits(
        self,
        mock_iteration_info,
        mock_github_class,
        mock_github_token,
        mock_org_name
    ):
        """Test report generation with commits"""
        # Mock iteration info
        mock_iteration_info.return_value = {
            'name': 'Test Sprint',
            'start_date': '2025-01-01T00:00:00Z',
            'end_date': '2025-01-15T23:59:59Z',
            'path': 'test-org/Test Board'
        }
        
        # Mock GitHub API
        mock_github = Mock()
        mock_user = Mock()
        mock_user.login = "test-user"
        mock_user.email = "test@example.com"
        mock_user.get_emails.return_value = []
        mock_github.get_user.return_value = mock_user
        
        mock_org = Mock()
        mock_member = Mock()
        mock_member.login = "test-member"
        mock_org.get_members.return_value = [mock_member]
        
        # Mock repository with commits
        mock_repo = Mock()
        mock_repo.name = "test-repo"
        mock_repo.archived = False
        
        mock_branch = Mock()
        mock_branch.name = "main"
        mock_repo.get_branches.return_value = [mock_branch]
        
        mock_commit = Mock()
        mock_commit.sha = "abc123"
        mock_commit.author = mock_member
        mock_commit.commit.message = "Test commit"
        mock_commit.commit.author.date = datetime.now(timezone.utc)
        mock_commit.commit.author.email = "test@example.com"
        mock_repo.get_commits.return_value = [mock_commit]
        mock_repo.get_issues.return_value = []
        
        mock_org.get_repos.return_value = [mock_repo]
        mock_github.get_organization.return_value = mock_org
        mock_github_class.return_value = mock_github
        
        # Mock user lookup for email mapping
        mock_user_lookup = Mock()
        mock_user_lookup.email = "test@example.com"
        mock_user_lookup.get_emails.return_value = []
        mock_github.get_user.return_value = mock_user_lookup
        
        response = client.get("/api/github-report")
        assert response.status_code == 200
        assert "GitHub Organization: test-org" in response.text

class TestIterationInfo:
    """Tests for iteration info retrieval"""
    
    @patch('agent_mcp_demo.server.requests.post')
    def test_get_iteration_info_from_graphql(self, mock_post):
        """Test getting iteration info from GraphQL API"""
        # Mock GraphQL response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
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
        
        # Mock fields response
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
                                            'startDate': '2025-01-01',
                                            'duration': 14
                                        }
                                    ]
                                }
                            }
                        ]
                    }
                }
            }
        }
        
        mock_post.side_effect = [mock_response, mock_fields_response]
        
        result = get_current_iteration_info("test-token", "test-org")
        
        assert result is not None
        assert result['name'] == 'Sprint 1'
        assert 'start_date' in result
        assert 'end_date' in result
    
    @patch('agent_mcp_demo.server.requests.post')
    def test_get_iteration_info_fallback_to_env(self, mock_post, mock_iteration_env):
        """Test that iteration info falls back to environment variables"""
        # Mock GraphQL response with no project found
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': {
                'organization': {
                    'projectsV2': {
                        'nodes': []
                    }
                }
            }
        }
        
        mock_post.return_value = mock_response
        
        result = get_current_iteration_info("test-token", "test-org")
        
        assert result is not None
        assert result['name'] == 'Test Sprint'
        assert result['start_date'] == '2025-01-01T00:00:00Z'
        assert result['end_date'] == '2025-01-15T23:59:59Z'
    
    @patch('agent_mcp_demo.server.requests.post')
    def test_get_iteration_info_error_handling(self, mock_post):
        """Test error handling in iteration info retrieval"""
        # Mock GraphQL error response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        result = get_current_iteration_info("test-token", "test-org")
        
        # Should return None on error
        assert result is None

class TestGitHubReportEndpoint:
    """Tests for the legacy GitHub report endpoint"""
    
    def test_github_report_legacy_endpoint(self):
        """Test the legacy GitHub report endpoint"""
        response = client.get("/github-report")
        assert response.status_code == 200
        assert "GitHub Report Server is running" in response.text

class TestServerTools:
    """Tests for MCP server tools"""
    
    @pytest.mark.asyncio
    async def test_add_note_tool(self):
        """Test the add-note tool"""
        from agent_mcp_demo.server import handle_call_tool, notes
        
        # Clear notes
        notes.clear()
        
        result = await handle_call_tool("add-note", {
            "name": "test-note",
            "content": "Test content"
        })
        
        assert len(result) > 0
        assert "test-note" in notes
        assert notes["test-note"] == "Test content"
    
    @pytest.mark.asyncio
    async def test_add_note_tool_missing_args(self):
        """Test add-note tool with missing arguments"""
        from agent_mcp_demo.server import handle_call_tool
        
        with pytest.raises(ValueError, match="Missing"):
            await handle_call_tool("add-note", {"name": "test"})
    
    @pytest.mark.asyncio
    async def test_fetch_api_data_tool(self):
        """Test the fetch-api-data tool"""
        from agent_mcp_demo.server import handle_call_tool
        
        with patch('agent_mcp_demo.server.fetch_from_api') as mock_fetch:
            mock_fetch.return_value = {"test": "data"}
            
            result = await handle_call_tool("fetch-api-data", {
                "url": "https://api.example.com/data"
            })
            
            assert len(result) > 0
            mock_fetch.assert_called_once_with("https://api.example.com/data")
    
    @pytest.mark.asyncio
    async def test_read_json_file_tool(self):
        """Test the read-json-file tool"""
        from agent_mcp_demo.server import handle_call_tool
        import tempfile
        import json
        
        # Create a temporary JSON file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"test": "data"}, f)
            temp_path = f.name
        
        try:
            result = await handle_call_tool("read-json-file", {
                "filepath": temp_path
            })
            
            assert len(result) > 0
            assert "test" in result[0].text.lower()
        finally:
            os.unlink(temp_path)
    
    @pytest.mark.asyncio
    async def test_unknown_tool(self):
        """Test handling of unknown tool"""
        from agent_mcp_demo.server import handle_call_tool
        
        with pytest.raises(ValueError, match="Unknown tool"):
            await handle_call_tool("unknown-tool", {})

class TestServerResources:
    """Tests for MCP server resources"""
    
    @pytest.mark.asyncio
    async def test_list_resources(self):
        """Test listing resources"""
        from agent_mcp_demo.server import handle_list_resources, notes
        
        # Add a note
        notes.clear()
        notes["test-note"] = "Test content"
        
        resources = await handle_list_resources()
        
        assert len(resources) == 1
        assert resources[0].name == "Note: test-note"
    
    @pytest.mark.asyncio
    async def test_read_resource(self):
        """Test reading a resource"""
        from agent_mcp_demo.server import handle_read_resource, notes
        from pydantic import AnyUrl
        
        # Add a note
        notes.clear()
        notes["test-note"] = "Test content"
        
        uri = AnyUrl("note://internal/test-note")
        content = await handle_read_resource(uri)
        
        assert content == "Test content"
    
    @pytest.mark.asyncio
    async def test_read_resource_invalid_uri(self):
        """Test reading resource with invalid URI"""
        from agent_mcp_demo.server import handle_read_resource
        from pydantic import AnyUrl
        
        uri = AnyUrl("http://example.com/resource")
        
        with pytest.raises(ValueError, match="Unsupported URI scheme"):
            await handle_read_resource(uri)
    
    @pytest.mark.asyncio
    async def test_read_resource_not_found(self):
        """Test reading non-existent resource"""
        from agent_mcp_demo.server import handle_read_resource, notes
        from pydantic import AnyUrl
        
        notes.clear()
        
        uri = AnyUrl("note://internal/non-existent")
        
        with pytest.raises(ValueError, match="Note not found"):
            await handle_read_resource(uri)

class TestServerPrompts:
    """Tests for MCP server prompts"""
    
    @pytest.mark.asyncio
    async def test_list_prompts(self):
        """Test listing prompts"""
        from agent_mcp_demo.server import handle_list_prompts
        
        prompts = await handle_list_prompts()
        
        assert len(prompts) == 1
        assert prompts[0].name == "summarize-notes"
    
    @pytest.mark.asyncio
    async def test_get_prompt_brief(self):
        """Test getting prompt with brief style"""
        from agent_mcp_demo.server import handle_get_prompt, notes
        
        notes.clear()
        notes["note1"] = "Content 1"
        notes["note2"] = "Content 2"
        
        result = await handle_get_prompt("summarize-notes", {"style": "brief"})
        
        assert result.description == "Summarize the current notes"
        assert len(result.messages) == 1
        assert "note1" in result.messages[0].content.text
        assert "note2" in result.messages[0].content.text
    
    @pytest.mark.asyncio
    async def test_get_prompt_detailed(self):
        """Test getting prompt with detailed style"""
        from agent_mcp_demo.server import handle_get_prompt, notes
        
        notes.clear()
        notes["note1"] = "Content 1"
        
        result = await handle_get_prompt("summarize-notes", {"style": "detailed"})
        
        assert "extensive details" in result.messages[0].content.text.lower()
    
    @pytest.mark.asyncio
    async def test_get_prompt_unknown(self):
        """Test getting unknown prompt"""
        from agent_mcp_demo.server import handle_get_prompt
        
        with pytest.raises(ValueError, match="Unknown prompt"):
            await handle_get_prompt("unknown-prompt", {})

class TestServerHelpers:
    """Tests for helper functions in server.py"""
    
    @pytest.mark.asyncio
    async def test_fetch_from_api_success(self):
        """Test successful API fetch"""
        from agent_mcp_demo.server import fetch_from_api
        
        with patch('agent_mcp_demo.server.httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.json.return_value = {"test": "data"}
            mock_response.raise_for_status = Mock()
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            result = await fetch_from_api("https://api.example.com/data")
            assert result == {"test": "data"}
    
    @pytest.mark.asyncio
    async def test_fetch_from_api_error(self):
        """Test API fetch with HTTP error"""
        from agent_mcp_demo.server import fetch_from_api
        import httpx
        
        with patch('agent_mcp_demo.server.httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Not Found", request=Mock(), response=Mock(status_code=404)
            )
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            with pytest.raises(httpx.HTTPStatusError):
                await fetch_from_api("https://api.example.com/notfound")
    
    def test_read_from_json_file_success(self):
        """Test successful JSON file read"""
        from agent_mcp_demo.server import read_from_json_file
        import tempfile
        import json
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"test": "data"}, f)
            temp_path = f.name
        
        try:
            result = read_from_json_file(temp_path)
            assert result == {"test": "data"}
        finally:
            os.unlink(temp_path)
    
    def test_read_from_json_file_not_found(self):
        """Test reading non-existent JSON file"""
        from agent_mcp_demo.server import read_from_json_file
        
        with pytest.raises(FileNotFoundError):
            read_from_json_file("/nonexistent/file.json")
    
    def test_read_from_json_file_invalid_json(self):
        """Test reading invalid JSON file"""
        from agent_mcp_demo.server import read_from_json_file
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json {")
            temp_path = f.name
        
        try:
            with pytest.raises(json.JSONDecodeError):
                read_from_json_file(temp_path)
        finally:
            os.unlink(temp_path)

class TestServerToolsErrorHandling:
    """Tests for error handling in server tools"""
    
    @pytest.mark.asyncio
    async def test_fetch_api_data_tool_error(self):
        """Test fetch-api-data tool with API error"""
        from agent_mcp_demo.server import handle_call_tool
        import httpx
        
        with patch('agent_mcp_demo.server.fetch_from_api') as mock_fetch:
            mock_fetch.side_effect = httpx.HTTPStatusError(
                "Not Found", request=Mock(), response=Mock(status_code=404)
            )
            
            with pytest.raises(httpx.HTTPStatusError):
                await handle_call_tool("fetch-api-data", {
                    "url": "https://api.example.com/notfound"
                })
    
    @pytest.mark.asyncio
    async def test_read_json_file_tool_error(self):
        """Test read-json-file tool with file error"""
        from agent_mcp_demo.server import handle_call_tool
        
        with pytest.raises(FileNotFoundError):
            await handle_call_tool("read-json-file", {
                "filepath": "/nonexistent/file.json"
            })
    
    @pytest.mark.asyncio
    async def test_add_note_tool_empty_name(self):
        """Test add-note tool with empty name"""
        from agent_mcp_demo.server import handle_call_tool
        
        with pytest.raises(ValueError, match="Missing name or content"):
            await handle_call_tool("add-note", {
                "name": "",
                "content": "test"
            })
    
    @pytest.mark.asyncio
    async def test_add_note_tool_empty_content(self):
        """Test add-note tool with empty content"""
        from agent_mcp_demo.server import handle_call_tool
        
        with pytest.raises(ValueError, match="Missing name or content"):
            await handle_call_tool("add-note", {
                "name": "test",
                "content": ""
            })

class TestGitHubReportAPIErrorHandling:
    """Tests for error handling in GitHub report API"""
    
    @pytest.mark.asyncio
    async def test_github_report_api_context_error(self):
        """Test GitHub report API when MCP context is not available"""
        from agent_mcp_demo.server import github_report_api
        import os
        
        # Set required environment variables
        os.environ["GITHUB_TOKEN"] = "test-token"
        os.environ["GITHUB_ORG_NAME"] = "test-org"
        
        try:
            # This should handle the context error gracefully
            response = await github_report_api()
            # Should return an error message
            assert "error" in response.lower() or "failed" in response.lower()
        finally:
            # Cleanup
            if "GITHUB_TOKEN" in os.environ:
                del os.environ["GITHUB_TOKEN"]
            if "GITHUB_ORG_NAME" in os.environ:
                del os.environ["GITHUB_ORG_NAME"]
