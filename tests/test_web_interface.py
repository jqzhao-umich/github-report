import pytest
from fastapi.testclient import TestClient
from agent_mcp_demo.agents.web_interface_agent import app

client = TestClient(app)

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert "GitHub Report" in response.text
    assert "Michigan App Team" in response.text

def test_github_report_endpoint_no_token():
    response = client.get("/api/github-report")
    assert response.status_code == 200
    assert "GitHub token not set" in response.text

def test_github_report_endpoint_no_org():
    # Set token but no org
    import os
    os.environ["GITHUB_TOKEN"] = "test-token"
    try:
        response = client.get("/api/github-report")
        assert response.status_code == 200
        assert "organization name not set" in response.text
    finally:
        del os.environ["GITHUB_TOKEN"]

def test_report_html_structure():
    response = client.get("/")
    html = response.text
    # Check for required HTML elements
    assert '<div class="container">' in html
    assert '<div class="header">' in html
    assert '<button class="refresh-btn"' in html
    assert '<div id="report-container">' in html
    
def test_report_javascript():
    response = client.get("/")
    html = response.text
    # Check for required JavaScript functions
    assert 'async function loadReport()' in html
    assert 'window.onload = loadReport' in html
