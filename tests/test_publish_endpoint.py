"""Tests for the POST body publish endpoint in server.py."""
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

# Import the app from server.py (the main application)
from agent_mcp_demo.server import app
from agent_mcp_demo.utils.report_publisher import ReportPublisher


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def temp_base_dir():
    """Create a temporary directory for report publishing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_env_vars():
    """Setup environment variables for testing."""
    with patch.dict(os.environ, {
        'GITHUB_TOKEN': 'test_token',
        'GITHUB_ORG_NAME': 'test_org',
    }):
        yield


@pytest.fixture
def mock_publisher(temp_base_dir):
    """Setup mock report publisher."""
    publisher = ReportPublisher(base_dir=temp_base_dir)
    with patch('agent_mcp_demo.server.publisher', publisher):
        yield publisher


# ============================================================================
# POST Body Publish Endpoint Tests
# ============================================================================

def test_publish_with_report_content_in_body(client, mock_env_vars, mock_publisher):
    """Test publishing with report_content provided in POST body."""
    report_content = """GitHub Organization: test-org

## CURRENT ITERATION INFORMATION
- Iteration Name: Sprint 1
- Start Date: 2025-11-01
- End Date: 2025-11-15

## SUMMARY
Test report content."""
    
    response = client.post(
        "/api/reports/publish",
        json={"report_content": report_content}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "Report publishing started" in data["message"]
    assert data["org_name"] == "test-org"
    assert data["iteration_name"] == "Sprint 1"


def test_publish_missing_report_content(client, mock_env_vars):
    """Test publishing without report_content in POST body."""
    response = client.post(
        "/api/reports/publish",
        json={}
    )
    
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "No report content provided" in data["error"]


def test_publish_empty_report_content(client, mock_env_vars):
    """Test publishing with empty report_content."""
    response = client.post(
        "/api/reports/publish",
        json={"report_content": ""}
    )
    
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert "No report content provided" in data["error"]


def test_publish_with_error_message_content(client, mock_env_vars):
    """Test publishing with error message as report content."""
    error_messages = [
        "GitHub token not set",
        "GitHub organization name not set",
        "Unexpected error: something went wrong"
    ]
    
    for error_msg in error_messages:
        response = client.post(
            "/api/reports/publish",
            json={"report_content": error_msg}
        )
        
        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert error_msg in data["error"]


def test_publish_invalid_report_format(client, mock_env_vars):
    """Test publishing with invalid report format (missing organization line)."""
    invalid_content = """This is a report without proper format

Some random content."""
    
    response = client.post(
        "/api/reports/publish",
        json={"report_content": invalid_content}
    )
    
    assert response.status_code == 500
    data = response.json()
    assert "error" in data
    assert "Invalid report format" in data["error"]


def test_publish_malformed_organization_line(client, mock_env_vars):
    """Test publishing with malformed organization line."""
    malformed_content = """GitHub Organization test-org

Some content."""
    
    response = client.post(
        "/api/reports/publish",
        json={"report_content": malformed_content}
    )
    
    assert response.status_code == 500
    data = response.json()
    assert "error" in data
    # The actual error is about format, not specifically organization line
    assert "Invalid report format" in data["error"]


def test_publish_with_force_parameter(client, mock_env_vars, mock_publisher):
    """Test publishing with force=True to skip duplicate check."""
    report_content = """GitHub Organization: test-org

## CURRENT ITERATION INFORMATION
- Iteration Name: Sprint 1
- Start Date: 2025-11-01
- End Date: 2025-11-15

## SUMMARY
Test report content."""
    
    response = client.post(
        "/api/reports/publish?force=true",
        json={"report_content": report_content}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "Report publishing started" in data["message"]
    
    # Give background task time to complete
    import time
    time.sleep(0.5)
    
    # Check that report was published
    reports_json = Path(mock_publisher.docs_dir, "reports.json")
    assert reports_json.exists()


def test_publish_without_iteration_info(client, mock_env_vars, mock_publisher):
    """Test publishing report without iteration information section."""
    report_content = """GitHub Organization: test-org

## SUMMARY
Test report without iteration info."""
    
    response = client.post(
        "/api/reports/publish",
        json={"report_content": report_content}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["org_name"] == "test-org"
    # iteration_name might be "N/A" or None when not found
    assert data.get("iteration_name") in [None, "N/A"]
    assert data.get("iteration_name") in [None, "N/A"]


def test_publish_with_partial_iteration_info(client, mock_env_vars, mock_publisher):
    """Test publishing with partial iteration information."""
    report_content = """GitHub Organization: test-org

## CURRENT ITERATION INFORMATION
- Iteration Name: Sprint 1

## SUMMARY
Test report with partial iteration info."""
    
    response = client.post(
        "/api/reports/publish",
        json={"report_content": report_content}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["org_name"] == "test-org"
    assert data["iteration_name"] == "Sprint 1"


def test_publish_invalid_json_body(client, mock_env_vars):
    """Test publishing with invalid JSON in request body."""
    response = client.post(
        "/api/reports/publish",
        content=b"invalid json",
        headers={"Content-Type": "application/json"}
    )
    
    # FastAPI should handle this and return 422 Unprocessable Entity or 500
    assert response.status_code in [422, 500]


def test_publish_missing_github_token_env(client, mock_publisher):
    """Test publishing when GITHUB_TOKEN environment variable is missing."""
    report_content = """GitHub Organization: test-org

## SUMMARY
Test report."""
    
    # Remove GITHUB_TOKEN from environment
    original_token = os.environ.pop("GITHUB_TOKEN", None)
    try:
        response = client.post(
            "/api/reports/publish",
            json={"report_content": report_content}
        )
        
        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert "GitHub token not set" in data["error"]
    finally:
        if original_token:
            os.environ["GITHUB_TOKEN"] = original_token


def test_publish_missing_github_org_env(client, mock_publisher):
    """Test publishing when GITHUB_ORG_NAME environment variable is missing."""
    report_content = """GitHub Organization: test-org

## SUMMARY
Test report."""
    
    # Set GITHUB_TOKEN but remove GITHUB_ORG_NAME
    os.environ["GITHUB_TOKEN"] = "test-token"
    original_org = os.environ.pop("GITHUB_ORG_NAME", None)
    try:
        response = client.post(
            "/api/reports/publish",
            json={"report_content": report_content}
        )
        
        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert "GitHub organization name not set" in data["error"]
    finally:
        if original_org:
            os.environ["GITHUB_ORG_NAME"] = original_org
        os.environ.pop("GITHUB_TOKEN", None)


def test_publish_actually_publishes_report(client, mock_env_vars, mock_publisher):
    """Test that publishing actually creates report files."""
    report_content = """GitHub Organization: test-org

## CURRENT ITERATION INFORMATION
- Iteration Name: Sprint 1
- Start Date: 2025-11-01
- End Date: 2025-11-15

## SUMMARY
This is a test report to verify actual file creation."""
    
    response = client.post(
        "/api/reports/publish",
        json={"report_content": report_content}
    )
    
    assert response.status_code == 200
    
    # Give background task time to complete
    import time
    time.sleep(0.5)
    
    # Check that files were created
    reports_json = Path(mock_publisher.docs_dir, "reports.json")
    assert reports_json.exists()
    
    # Verify at least one HTML report was created
    html_files = list(Path(mock_publisher.docs_dir).glob("*.html"))
    # Filter out index.html
    report_files = [f for f in html_files if f.name != "index.html"]
    assert len(report_files) > 0, "No report HTML files were created"
    
    # Verify report content
    with open(report_files[0]) as f:
        html_content = f.read()
        assert "test-org" in html_content
        assert "Sprint 1" in html_content


def test_publish_parses_iteration_dates_correctly(client, mock_env_vars, mock_publisher):
    """Test that iteration dates are correctly parsed from report content."""
    report_content = """GitHub Organization: test-org

## CURRENT ITERATION INFORMATION
- Iteration Name: Sprint 2
- Start Date: 2025-12-01
- End Date: 2025-12-15

## SUMMARY
Report with dates."""
    
    response = client.post(
        "/api/reports/publish",
        json={"report_content": report_content}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["iteration_name"] == "Sprint 2"
    
    # Give background task time to complete
    import time
    time.sleep(0.5)
    
    # Check reports.json for the dates
    reports_json = Path(mock_publisher.docs_dir, "reports.json")
    import json
    with open(reports_json) as f:
        reports = json.load(f)
    
    assert len(reports) > 0
    latest_report = reports[-1]
    assert latest_report["start_date"] == "2025-12-01"
    assert latest_report["end_date"] == "2025-12-15"
