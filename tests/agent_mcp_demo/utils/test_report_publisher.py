"""Tests for the report publisher module."""
import os
from pathlib import Path
import tempfile
import pytest
from agent_mcp_demo.utils.report_publisher import ReportPublisher

@pytest.fixture
def temp_base_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir

@pytest.fixture
def publisher(temp_base_dir):
    """Create a ReportPublisher instance with a temp directory."""
    return ReportPublisher(base_dir=temp_base_dir)

def test_publisher_initialization(publisher, temp_base_dir):
    """Test that the publisher creates necessary directories."""
    assert Path(temp_base_dir, "reports").exists()
    assert Path(temp_base_dir, "docs").exists()
    assert Path(temp_base_dir, "docs", "index.html").exists()

def test_publish_report(publisher, temp_base_dir):
    """Test publishing a report."""
    report_content = """# Test Report
This is a test report."""
    
    result = publisher.publish_report(
        report_content=report_content,
        org_name="test-org",
        iteration_name="Sprint 1",
        start_date="2025-01-01",
        end_date="2025-01-15"
    )
    
    # Check that files were created
    assert Path(result["markdown"]).exists()
    assert Path(result["html"]).exists()
    
    # Check that index was updated
    index_path = Path(temp_base_dir, "docs", "reports.json")
    assert index_path.exists()
    
    # Check HTML content
    with open(result["html"]) as f:
        html_content = f.read()
        assert "test-org" in html_content
        assert "Sprint 1" in html_content
        assert "2025-01-01" in html_content
        assert "2025-01-15" in html_content
        assert "Test Report" in html_content

def test_multiple_reports(publisher):
    """Test publishing multiple reports."""
    # Publish first report
    report1 = publisher.publish_report(
        "# Report 1",
        org_name="org1",
        iteration_name="Sprint 1"
    )
    
    # Publish second report
    report2 = publisher.publish_report(
        "# Report 2",
        org_name="org2",
        iteration_name="Sprint 2"
    )
    
    assert Path(report1["markdown"]).exists()
    assert Path(report2["markdown"]).exists()
    assert Path(report1["html"]).exists()
    assert Path(report2["html"]).exists()