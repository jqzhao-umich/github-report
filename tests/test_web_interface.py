import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime
import json

from agent_mcp_demo.agents.web_interface_agent import app, server
from mcp.types import TextContent, ImageContent, EmbeddedResource

client = TestClient(app)

def create_mock_github_data():
    """Create mock GitHub data for testing."""
    return {
        'member_stats': {
            'user1': {
                'commits': 5,
                'assigned_issues': 3,
                'closed_issues': 2
            },
            'user2': {
                'commits': 2,
                'assigned_issues': 1,
                'closed_issues': 1
            }
        },
        'commit_details': {
            'user1': [
                {
                    'repo': 'test-repo',
                    'message': 'Test commit',
                    'date': '2025-11-07T22:37:17.271491'
                }
            ]
        },
        'assigned_issues': {
            'user1': [
                {
                    'repo': 'test-repo',
                    'number': 1,
                    'title': 'Test issue',
                    'state': 'open'
                }
            ]
        },
        'closed_issues': {
            'user1': [
                {
                    'repo': 'test-repo',
                    'number': 2,
                    'title': 'Closed issue',
                    'closed_date': '2025-11-07T22:37:17.271497'
                }
            ]
        }
    }

@pytest.fixture
def mock_env_vars():
    """Setup environment variables for testing."""
    with patch.dict(os.environ, {
        'GITHUB_TOKEN': 'test_token',
        'GITHUB_ORG_NAME': 'test_org',
    }):
        yield

@pytest.fixture
def mock_server_context():
    """Setup mock MCP server context with session."""
    import asyncio
    import contextvars
    from mcp.server.lowlevel.server import request_ctx, RequestContext

    mock_session = AsyncMock()
    mock_context = RequestContext(
        session=mock_session,
        request_id="test-request",
        meta={},
        lifespan_context=None,
    )

    token = request_ctx.set(mock_context)
    yield mock_session
    request_ctx.reset(token)

@pytest.fixture
def mock_publisher():
    """Setup mock report publisher."""
    with patch('agent_mcp_demo.agents.web_interface_agent.publisher') as mock:
        mock.publish_report = AsyncMock()
        mock.publish_report.return_value = {
            'markdown': '/path/to/report.md',
            'html': '/path/to/report.html',
            'web_url': 'https://test.github.io/report.html'
        }
        yield mock

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert "GitHub Report" in response.text
    assert "GitHub Organization Report" in response.text
    # Check for button classes that match our JavaScript selectors
    assert 'class="action-btn primary-btn"' in response.text
    assert 'class="action-btn success-btn"' in response.text

def test_github_report_endpoint_no_token():
    # Remove token if it exists
    import os
    original_token = os.environ.pop("GITHUB_TOKEN", None)
    try:
        response = client.get("/api/github-report")
        assert response.status_code == 500  # We expect a 500 error when no token is provided
        data = response.json()
        assert "error" in data
        assert "GitHub token not set in environment" in data["error"]
    finally:
        if original_token:
            os.environ["GITHUB_TOKEN"] = original_token

def test_github_report_endpoint_no_org():
    # Set token but no org
    import os
    original_token = os.environ.pop("GITHUB_TOKEN", None)
    original_org = os.environ.pop("GITHUB_ORG_NAME", None)
    os.environ["GITHUB_TOKEN"] = "test-token"
    try:
        response = client.get("/api/github-report")
        assert response.status_code == 500  # We expect a 500 error when no org is provided
        data = response.json()
        assert "error" in data
        assert "GitHub organization name not set in environment" in data["error"]
    finally:
        if original_token:
            os.environ["GITHUB_TOKEN"] = original_token
        elif "GITHUB_TOKEN" in os.environ:
            del os.environ["GITHUB_TOKEN"]
        if original_org:
            os.environ["GITHUB_ORG_NAME"] = original_org

def test_report_html_structure():
    response = client.get("/")
    html = response.text
    # Check for required HTML elements
    assert '<div class="container">' in html
    assert '<div class="header">' in html
    assert '<button class="action-btn primary-btn"' in html
    assert '<button class="action-btn success-btn"' in html
    assert '<div id="report-container">' in html
    
def test_report_javascript():
    response = client.get("/")
    html = response.text
    # Check for required JavaScript functions and error handling
    assert 'async function loadReport()' in html
    assert 'async function publishReport()' in html
    assert 'window.onload = loadReport' in html
    # Check for proper error handling in JavaScript
    assert 'status-message error' in html
    assert 'status-message success' in html
    assert 'catch (error)' in html

@pytest.mark.asyncio
async def test_github_report_with_mock_data(mock_env_vars, mock_server_context):
    """Test report generation with mocked GitHub data."""
    # Setup mock responses
    mock_server_context.call_tool.side_effect = [
                    # First call - iteration info
            [TextContent(type="text", text=str({
                'name': 'Sprint 1',
                'start_date': '2025-11-01',
                'end_date': '2025-11-15'
            }))],
            # Second call - GitHub data
            [TextContent(type="text", text=str(create_mock_github_data()))]
    ]

    response = client.get("/api/github-report")
    assert response.status_code == 200
    
    # Verify report content
    content = response.json() if response.headers['content-type'] == 'application/json' else response.text
    assert isinstance(content, (str, dict))
    if isinstance(content, dict):
        assert 'error' not in content
    else:
        assert "GitHub Organization: test_org" in content
        assert "Sprint 1" in content
        assert "user1" in content
        assert "user2" in content

@pytest.mark.asyncio
async def test_publish_report_success(mock_env_vars, mock_server_context, mock_publisher):
    """Test successful report publishing."""
    # Setup mock responses
    mock_server_context.call_tool.side_effect = [
        [TextContent(type="text", text=str({
            'name': 'Sprint 1',
            'start_date': '2025-11-01',
            'end_date': '2025-11-15'
        }))],
        [TextContent(type="text", text=str(create_mock_github_data()))]
    ]

    response = client.post("/api/reports/publish")
    assert response.status_code == 200
    data = response.json()
    
    assert data["message"] == "Report generation started. It will be published shortly."
    assert data["org_name"] == "test_org"
    assert data["iteration_name"] == "Sprint 1"

    # Verify publisher was called correctly
    mock_publisher.publish_report.assert_called_once()
    call_args = mock_publisher.publish_report.call_args[1]
    assert call_args["org_name"] == "test_org"
    assert call_args["iteration_name"] == "Sprint 1"

@pytest.mark.asyncio
async def test_publish_report_failure(mock_env_vars, mock_server_context, mock_publisher):
    """Test report publishing with failure."""
    # Setup mock to raise an exception
    mock_publisher.publish_report.side_effect = Exception("Failed to write report")
    
    # Setup other mocks
    mock_server_context.call_tool.side_effect = [
        [TextContent(type="text", text=str({
            'name': 'Sprint 1',
            'start_date': '2025-11-01',
            'end_date': '2025-11-15'
        }))],
        [TextContent(type="text", text=str(create_mock_github_data()))]
    ]

    response = client.post("/api/reports/publish")
    assert response.status_code == 500
    data = response.json()
    assert "Failed to publish report" in data["error"]

@pytest.mark.asyncio
async def test_publish_report_invalid_data(mock_env_vars, mock_server_context):
    """Test publishing with invalid GitHub data."""
    # Mock invalid GitHub data response
    mock_server_context.call_tool.side_effect = [
                    [TextContent(type="text", text=str({'name': 'Sprint 1'}))],  # iteration info
            [TextContent(type="text", text="invalid data")]  # invalid GitHub data
    ]

    response = client.post("/api/reports/publish")
    assert response.status_code == 500
    data = response.json()
    assert "Failed to parse GitHub data" in data["error"]

@pytest.mark.asyncio
async def test_missing_mcp_context(mock_env_vars):
    """Test behavior when MCP context is missing."""
    from mcp.server.lowlevel.server import request_ctx
    
    # Clear any existing context
    try:
        request_ctx.get()
        request_ctx.reset(request_ctx.set(None))
    except LookupError:
        pass

    try:
        response = client.post("/api/reports/publish")
        assert response.status_code == 500
        data = response.json()
        assert "Failed to publish report: <ContextVar name='request_ctx'" in data["error"]
    finally:
        pass  # No need to restore context, it's managed by other fixtures
