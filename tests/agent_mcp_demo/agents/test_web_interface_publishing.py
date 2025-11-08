"""Tests for report publishing functionality in the web interface agent."""
import os
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from agent_mcp_demo.agents.web_interface_agent import app

# Create test client
client = TestClient(app)

@pytest.fixture
def mock_environment():
    """Fixture to set up test environment variables."""
    original_token = os.environ.get("GITHUB_TOKEN")
    original_org = os.environ.get("GITHUB_ORG_NAME")
    
    os.environ["GITHUB_TOKEN"] = "test-token"
    os.environ["GITHUB_ORG_NAME"] = "test-org"
    
    yield
    
    # Restore original environment
    if original_token:
        os.environ["GITHUB_TOKEN"] = original_token
    else:
        del os.environ["GITHUB_TOKEN"]
        
    if original_org:
        os.environ["GITHUB_ORG_NAME"] = original_org
    else:
        del os.environ["GITHUB_ORG_NAME"]

@pytest.fixture
def temp_workspace(tmpdir):
    """Create a temporary workspace for testing."""
    reports_dir = tmpdir.mkdir("reports")
    docs_dir = tmpdir.mkdir("docs")
    return str(tmpdir)

def test_publish_report_endpoint_success(mock_environment, temp_workspace, monkeypatch):
    """Test successful report publishing."""
    # Mock publisher to use temp workspace
    from agent_mcp_demo.utils.report_publisher import ReportPublisher
    monkeypatch.setattr(
        ReportPublisher, 
        "__init__", 
        lambda self: setattr(self, "base_dir", Path(temp_workspace))
    )
    
    # Make the publish request
    response = client.post("/api/reports/publish")
    assert response.status_code == 200
    
    data = response.json()
    assert data["org_name"] == "test-org"
    assert "message" in data
    
    # Verify files were created
    reports_dir = Path(temp_workspace) / "reports"
    docs_dir = Path(temp_workspace) / "docs"
    
    assert reports_dir.exists()
    assert docs_dir.exists()
    assert len(list(reports_dir.glob("*.md"))) == 1
    assert len(list(docs_dir.glob("*.html"))) == 1
    assert (docs_dir / "reports.json").exists()

def test_publish_report_endpoint_failure(client):
    """Test report publishing with missing environment variables."""
    # Remove required environment variables
    os.environ.pop("GITHUB_TOKEN", None)
    os.environ.pop("GITHUB_ORG_NAME", None)
    
    response = client.post("/api/reports/publish")
    assert response.status_code == 500
    assert "error" in response.json()