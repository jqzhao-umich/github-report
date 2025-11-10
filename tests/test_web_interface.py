import pytest
from fastapi.testclient import TestClient
from agent_mcp_demo.agents.web_interface_agent import app
from unittest.mock import patch, MagicMock

client = TestClient(app)

@pytest.fixture(autouse=True)
def mock_mcp_context():
    # Patch server in the correct module
    with patch("agent_mcp_demo.agents.web_interface_agent.server") as mock_server:
        class DummySession:
            async def call_tool(self, *args, **kwargs):
                return [MagicMock(text="{}")]
        class DummyContext:
            session = DummySession()
        mock_server.request_context = DummyContext()
        yield


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert "GitHub Report" in response.text
    assert "GitHub Organization Report" in response.text


def test_github_report_endpoint_no_token():
    import os
    token = os.environ.pop("GITHUB_TOKEN", None)
    org = os.environ.pop("GITHUB_ORG_NAME", None)
    response = client.get("/api/github-report")
    assert response.status_code == 200
    assert "GitHub token not set" in response.text
    if token:
        os.environ["GITHUB_TOKEN"] = token
    if org:
        os.environ["GITHUB_ORG_NAME"] = org


def test_github_report_endpoint_no_org():
    import os
    token = os.environ.get("GITHUB_TOKEN")
    os.environ["GITHUB_TOKEN"] = "test-token"
    org = os.environ.pop("GITHUB_ORG_NAME", None)
    try:
        response = client.get("/api/github-report")
        assert response.status_code == 200
        assert "organization name not set" in response.text
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
    assert '<button class="refresh-btn"' in html
    assert '<div id="report-container">' in html
    
def test_report_javascript():
    response = client.get("/")
    html = response.text
    assert 'async function loadReport()' in html
    assert 'window.onload = loadReport' in html
