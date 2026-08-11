import os
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime
import json

from agent_mcp_demo.agents.web_interface_agent import app, server
from agent_mcp_demo.agents import _peer_client, _wire
from mcp.types import TextContent


# Simple stand-ins for the removed mcp.server.lowlevel.server.request_ctx /
# RequestContext. Tests below patch _peer_client.call_peer_tool, which is the
# 2.0 replacement for the ambient MCP context seam.
class _ProxySession:
    """Mock session that records call_tool invocations and yields text results."""

    def __init__(self):
        self.call_tool = AsyncMock()


def create_mock_server_context():
    mock_session = _ProxySession()
    mock_context = MagicMock(session=mock_session, request_id="test-request", meta={}, lifespan_context=None)
    return mock_context, mock_session


client = TestClient(app)


def _extract_text_from_side_effect_item(item):
    """The old tests pushed side_effect entries shaped [TextContent(text=...)].
    The new peer_client returns raw text strings, so unwrap the TextContent
    lists here to keep tests readable."""
    if isinstance(item, list) and item and hasattr(item[0], "text"):
        return item[0].text
    if hasattr(item, "text"):
        return item.text
    return item


def _install_peer_side_effect(mock_session):
    """Bridge the old-shape side_effect list on mock_session.call_tool to the
    new _peer_client.call_peer_tool contract (returns a text string)."""

    async def _call_peer_tool(agent_name, tool_name, arguments=None):
        entries = mock_session.call_tool.side_effect
        if entries is None:
            raise NotImplementedError("no side_effect configured")
        if not isinstance(entries, list):
            entries = list(entries)
        try:
            entry = entries.pop(0)
        except IndexError as e:
            raise StopAsyncIteration from e
        mock_session.call_tool.side_effect = entries
        # keep the historical call-count assertions working
        mock_session.call_tool.call_count = getattr(mock_session.call_tool, "call_count", 0) + 1
        return _extract_text_from_side_effect_item(entry)

    return _call_peer_tool

def create_mock_github_data():
    """Create mock GitHub data for testing."""
    from datetime import datetime
    return {
        'member_stats': {
            'user1': {
                'commits': 5,
                'assigned_issues': 3,
                'closed_issues': 2,
                'pr_created': 2,
                'pr_reviewed': 3,
                'pr_merged': 1,
                'pr_commented': 4
            },
            'user2': {
                'commits': 2,
                'assigned_issues': 1,
                'closed_issues': 1,
                'pr_created': 1,
                'pr_reviewed': 1,
                'pr_merged': 0,
                'pr_commented': 2
            }
        },
        'commit_details': {
            'user1': [
                {
                    'repo': 'test-repo',
                    'message': 'Test commit',
                    'date': datetime.fromisoformat('2025-11-07T22:37:17')
                }
            ],
            'user2': []
        },
        'assigned_issues': {
            'user1': [
                {
                    'repo': 'test-repo',
                    'number': 1,
                    'title': 'Test issue',
                    'state': 'open'
                }
            ],
            'user2': []
        },
        'closed_issues': {
            'user1': [
                {
                    'repo': 'test-repo',
                    'number': 2,
                    'title': 'Closed issue',
                    'closed_date': datetime.fromisoformat('2025-11-07T22:37:17')
                }
            ],
            'user2': []
        },
        'pr_created': {
            'user1': [
                {
                    'repo': 'test-repo',
                    'number': 10,
                    'title': 'Test PR',
                    'state': 'open',
                    'created_at': datetime.fromisoformat('2025-11-07T22:37:17'),
                    'merged_at': None,
                    'closed_at': None
                }
            ],
            'user2': []
        },
        'pr_reviewed': {
            'user1': [],
            'user2': []
        },
        'pr_merged': {
            'user1': [],
            'user2': []
        },
        'pr_commented': {
            'user1': [],
            'user2': []
        }
    }

def serialize_github_data(data):
    """Wire-encode GitHub data for tests. Wraps _wire.encode so existing test
    call sites keep working after the eval()→JSON port."""
    return _wire.encode(data)

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
    """Setup mock peer-agent RPC surface used by web_interface_agent."""
    mock_context, mock_session = create_mock_server_context()

    mock_session.call_tool.side_effect = [
        [TextContent(type="text", text=_wire.encode({
            'name': 'Sprint 1',
            'start_date': '2025-11-01',
            'end_date': '2025-11-15'
        }))],
        [TextContent(type="text", text=str(create_mock_github_data()))]
    ]

    patcher = patch.object(_peer_client, "call_peer_tool", _install_peer_side_effect(mock_session))
    patcher.start()
    try:
        yield mock_session
    finally:
        patcher.stop()

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

def test_github_report_endpoint_no_token(mock_server_context):
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

def test_github_report_endpoint_no_org(mock_server_context):
    # Set token but no org
    import os
    token = os.environ.get("GITHUB_TOKEN")
    os.environ["GITHUB_TOKEN"] = "test-token"
    org = os.environ.pop("GITHUB_ORG_NAME", None)
    try:
        response = client.get("/api/github-report")
        assert response.status_code == 500  # We expect a 500 error when no org is provided
        data = response.json()
        assert "error" in data
        assert "GitHub organization name not set in environment" in data["error"]
    finally:
        if token:
            os.environ["GITHUB_TOKEN"] = token
        else:
            del os.environ["GITHUB_TOKEN"]
        if org:
            os.environ["GITHUB_ORG_NAME"] = org


def test_report_html_structure():
    response = client.get("/")
    html = response.text
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
            [TextContent(type="text", text=_wire.encode({
                'name': 'Sprint 1',
                'start_date': '2025-11-01',
                'end_date': '2025-11-15'
            }))],
            # Second call - GitHub data
            [TextContent(type="text", text=serialize_github_data(create_mock_github_data()))]
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
        [TextContent(type="text", text=_wire.encode({
            'name': 'Sprint 1',
            'start_date': '2025-11-01',
            'end_date': '2025-11-15'
        }))],
        [TextContent(type="text", text=serialize_github_data(create_mock_github_data()))]
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
    import logging
    
    # Setup mock responses for report generation
    mock_server_context.call_tool.side_effect = [
        [TextContent(type="text", text=_wire.encode({
            'name': 'Sprint 1',
            'start_date': '2025-11-01',
            'end_date': '2025-11-15'
        }))],
        [TextContent(type="text", text=serialize_github_data(create_mock_github_data()))]
    ]
    
    # Setup the publisher to fail
    mock_publisher.publish_report.side_effect = Exception("Failed to write report")
    
    # Log handler to capture log messages
    log_messages = []
    class TestLogHandler(logging.Handler):
        def emit(self, record):
            log_messages.append(record.getMessage())
    
    # Add test handler to logger
    logger = logging.getLogger('web-interface-agent')
    test_handler = TestLogHandler()
    logger.addHandler(test_handler)
    
    try:
        # Enable test mode to run background tasks synchronously
        with patch.dict(os.environ, {"TEST_MODE": "true"}):
            response = client.post("/api/reports/publish")
            
            # Initial response should be successful
            assert response.status_code == 200
            data = response.json()
            assert "Report generation started" in data["message"]
            
            # Check that error was logged
            error_logs = [msg for msg in log_messages if "Error in test mode background publish" in msg]
            assert any("Failed to write report" in msg for msg in error_logs)
    finally:
        # Clean up test handler
        logger.removeHandler(test_handler)

@pytest.mark.asyncio
async def test_report_contains_pr_metrics(mock_env_vars, mock_server_context):
    """Test that generated report includes PR metrics in summary table."""
    # Setup mock responses
    mock_server_context.call_tool.side_effect = [
        [TextContent(type="text", text=_wire.encode({
            'name': 'Sprint 1',
            'start_date': '2025-11-01',
            'end_date': '2025-11-15'
        }))],
        [TextContent(type="text", text=serialize_github_data(create_mock_github_data()))]
    ]

    response = client.get("/api/github-report")
    assert response.status_code == 200
    
    report_text = response.json() if response.headers['content-type'] == 'application/json' else response.text
    if isinstance(report_text, dict):
        report_text = str(report_text)
    
    # Verify PR metrics columns exist in summary table
    assert "PRs Created" in report_text, "Missing 'PRs Created' column in summary"
    assert "PRs Reviewed" in report_text, "Missing 'PRs Reviewed' column in summary"
    assert "PRs Merged" in report_text, "Missing 'PRs Merged' column in summary"
    assert "PRs Commented" in report_text, "Missing 'PRs Commented' column in summary"
    
    # Verify summary section exists
    assert "SUMMARY" in report_text

@pytest.mark.asyncio
async def test_report_contains_pr_detail_sections(mock_env_vars, mock_server_context):
    """Test that generated report includes PR detail sections."""
    # Setup mock responses with PR data
    mock_server_context.call_tool.side_effect = [
        [TextContent(type="text", text=_wire.encode({
            'name': 'Sprint 1',
            'start_date': '2025-11-01',
            'end_date': '2025-11-15'
        }))],
        [TextContent(type="text", text=serialize_github_data(create_mock_github_data()))]
    ]

    response = client.get("/api/github-report")
    assert response.status_code == 200
    
    report_text = response.json() if response.headers['content-type'] == 'application/json' else response.text
    if isinstance(report_text, dict):
        report_text = str(report_text)
    
    # Verify PR detail sections exist
    assert "Pull Requests Created:" in report_text, "Missing 'Pull Requests Created' section"
    assert "Pull Requests Reviewed:" in report_text, "Missing 'Pull Requests Reviewed' section"
    assert "Pull Requests Merged:" in report_text, "Missing 'Pull Requests Merged' section"
    assert "Pull Requests Commented:" in report_text, "Missing 'Pull Requests Commented' section"

def test_pr_metrics_data_structure():
    """Test that PR metrics data structure is correct."""
    data = create_mock_github_data()
    
    # Verify PR metrics exist in member_stats
    for user, stats in data['member_stats'].items():
        assert 'pr_created' in stats, f"Missing pr_created for {user}"
        assert 'pr_reviewed' in stats, f"Missing pr_reviewed for {user}"
        assert 'pr_merged' in stats, f"Missing pr_merged for {user}"
        assert 'pr_commented' in stats, f"Missing pr_commented for {user}"
        
        # Verify types
        assert isinstance(stats['pr_created'], int)
        assert isinstance(stats['pr_reviewed'], int)
        assert isinstance(stats['pr_merged'], int)
        assert isinstance(stats['pr_commented'], int)
    
    # Verify PR detail dictionaries exist
    assert 'pr_created' in data
    assert 'pr_reviewed' in data
    assert 'pr_merged' in data
    assert 'pr_commented' in data
    
    # Verify structure of PR details
    for user in data['member_stats'].keys():
        assert user in data['pr_created']
        assert user in data['pr_reviewed']
        assert user in data['pr_merged']
        assert user in data['pr_commented']
        
        assert isinstance(data['pr_created'][user], list)
        assert isinstance(data['pr_reviewed'][user], list)
        assert isinstance(data['pr_merged'][user], list)
        assert isinstance(data['pr_commented'][user], list)


@pytest.mark.asyncio
async def test_publish_report_invalid_data(mock_env_vars, mock_server_context):
    """Test publishing with invalid GitHub data."""
    # Mock invalid GitHub data response
    mock_server_context.call_tool.side_effect = [
                    [TextContent(type="text", text=_wire.encode({'name': 'Sprint 1'}))],  # iteration info
            [TextContent(type="text", text="invalid data")]  # invalid GitHub data
    ]

    response = client.post("/api/reports/publish")
    assert response.status_code == 500
    data = response.json()
    assert "Failed to parse GitHub data" in data["error"]

@pytest.mark.asyncio
async def test_missing_mcp_context(mock_env_vars):
    """Test behavior when the peer-agent RPC path is unavailable.

    In mcp 2.0 the ambient request_ctx ContextVar is gone; the runtime seam is
    now agent_mcp_demo.agents._peer_client.call_peer_tool. When that raises
    NotImplementedError (its default), the endpoints surface the same
    "MCP server context not available" error the old low-level ContextVar did.
    """
    from fastapi.testclient import TestClient
    from agent_mcp_demo.agents.web_interface_agent import app

    test_client = TestClient(app)

    async def _unavailable(*args, **kwargs):
        raise NotImplementedError("peer agent not wired")

    with patch.object(_peer_client, "call_peer_tool", _unavailable):
        response = test_client.post("/api/reports/publish")
        assert response.status_code == 500
        assert "MCP server context not available" in response.json()["error"]
