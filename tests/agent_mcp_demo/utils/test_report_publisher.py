"""Tests for the report publisher module."""
import os
import json
from pathlib import Path
import tempfile
import pytest
import asyncio
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

@pytest.mark.asyncio
async def test_publish_report(publisher, temp_base_dir):
    """Test publishing a report."""
    report_content = """# Test Report
This is a test report."""
    
    result = await publisher.publish_report(
        report_content=report_content,
        org_name="test-org",
        iteration_name="Sprint 1",
        start_date="2025-01-01",
        end_date="2025-01-15"
    )
    
    # Check that files were created
    assert Path(result["markdown"]).exists()
    assert Path(result["html"]).exists()
    assert result["status"] == "published"
    
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
        # Check for timezone abbreviation (EST or EDT)
        assert "EST" in html_content or "EDT" in html_content

@pytest.mark.asyncio
async def test_multiple_reports(publisher):
    """Test publishing multiple reports."""
    # Publish first report
    report1 = await publisher.publish_report(
        "# Report 1",
        org_name="org1",
        iteration_name="Sprint 1"
    )
    
    # Publish second report
    report2 = await publisher.publish_report(
        "# Report 2",
        org_name="org2",
        iteration_name="Sprint 2"
    )
    
    assert Path(report1["markdown"]).exists()
    assert Path(report2["markdown"]).exists()
    assert Path(report1["html"]).exists()
    assert Path(report2["html"]).exists()

@pytest.mark.asyncio
async def test_overwrite_same_iteration(publisher, temp_base_dir):
    """Test that publishing the same iteration overwrites the old report."""
    # Publish first report
    result1 = await publisher.publish_report(
        report_content="# First Report\nThis is the first version.",
        org_name="test-org",
        iteration_name="Sprint 1",
        start_date="2025-01-01",
        end_date="2025-01-15"
    )
    
    first_html = result1["html"]
    first_md = result1["markdown"]
    
    # Verify first report exists
    assert Path(first_html).exists()
    assert Path(first_md).exists()
    
    # Read first report content
    with open(first_html) as f:
        first_content = f.read()
        assert "First Report" in first_content
    
    # Wait 2 seconds to ensure different timestamp
    import time
    time.sleep(2)
    
    # Publish second report with same org and iteration
    result2 = await publisher.publish_report(
        report_content="# Second Report\nThis is the updated version.",
        org_name="test-org",
        iteration_name="Sprint 1",
        start_date="2025-01-01",
        end_date="2025-01-15"
    )
    
    second_html = result2["html"]
    second_md = result2["markdown"]
    
    # Verify new files exist
    assert Path(second_html).exists()
    assert Path(second_md).exists()
    
    # Verify new content (should contain updated version)
    with open(second_html) as f:
        content = f.read()
        assert "Second Report" in content
        assert "updated version" in content
        # Check for timezone abbreviation (EST or EDT)
        assert "EST" in content or "EDT" in content
    
    # If filenames are different (different timestamps), verify old files were removed
    if first_html != second_html:
        assert not Path(first_html).exists(), "Old HTML file should be deleted when filename differs"
        assert not Path(first_md).exists(), "Old markdown file should be deleted when filename differs"
    
    # Verify reports.json has only one entry for this iteration
    reports_json = Path(temp_base_dir, "docs", "reports.json")
    with open(reports_json) as f:
        reports = json.load(f)
    
    sprint1_reports = [r for r in reports if r["org_name"] == "test-org" and r["iteration_name"] == "Sprint 1"]
    assert len(sprint1_reports) == 1, "Should only have one report for Sprint 1"
    assert sprint1_reports[0]["path"] == Path(second_html).name

@pytest.mark.asyncio
async def test_overwrite_different_iterations_same_org(publisher, temp_base_dir):
    """Test that different iterations for the same org don't overwrite each other."""
    # Publish Sprint 1
    result1 = await publisher.publish_report(
        report_content="# Sprint 1 Report",
        org_name="test-org",
        iteration_name="Sprint 1"
    )
    
    # Publish Sprint 2
    result2 = await publisher.publish_report(
        report_content="# Sprint 2 Report",
        org_name="test-org",
        iteration_name="Sprint 2"
    )
    
    # Both reports should exist
    assert Path(result1["html"]).exists()
    assert Path(result1["markdown"]).exists()
    assert Path(result2["html"]).exists()
    assert Path(result2["markdown"]).exists()
    
    # Verify reports.json has both entries
    reports_json = Path(temp_base_dir, "docs", "reports.json")
    with open(reports_json) as f:
        reports = json.load(f)
    
    org_reports = [r for r in reports if r["org_name"] == "test-org"]
    assert len(org_reports) == 2
    
    iterations = {r["iteration_name"] for r in org_reports}
    assert "Sprint 1" in iterations
    assert "Sprint 2" in iterations

@pytest.mark.asyncio
async def test_overwrite_same_iteration_different_orgs(publisher, temp_base_dir):
    """Test that same iteration name for different orgs don't overwrite each other."""
    # Publish for org1
    result1 = await publisher.publish_report(
        report_content="# Org1 Sprint 1",
        org_name="org1",
        iteration_name="Sprint 1"
    )
    
    # Publish for org2 with same iteration name
    result2 = await publisher.publish_report(
        report_content="# Org2 Sprint 1",
        org_name="org2",
        iteration_name="Sprint 1"
    )
    
    # Both reports should exist
    assert Path(result1["html"]).exists()
    assert Path(result2["html"]).exists()
    
    # Verify reports.json has both entries
    reports_json = Path(temp_base_dir, "docs", "reports.json")
    with open(reports_json) as f:
        reports = json.load(f)
    
    assert len(reports) == 2
    
    orgs = {r["org_name"] for r in reports}
    assert "org1" in orgs
    assert "org2" in orgs

@pytest.mark.asyncio
async def test_find_and_remove_old_report(publisher, temp_base_dir):
    """Test the _find_and_remove_old_report method directly."""
    # Publish initial report
    await publisher.publish_report(
        report_content="# Initial Report",
        org_name="test-org",
        iteration_name="Sprint 1"
    )
    
    # Verify reports.json has one entry
    reports_json = Path(temp_base_dir, "docs", "reports.json")
    with open(reports_json) as f:
        reports = json.load(f)
    assert len(reports) == 1
    
    old_path = reports[0]["path"]
    
    # Call _find_and_remove_old_report
    removed_path = publisher._find_and_remove_old_report("test-org", "Sprint 1")
    
    # Should return the old report path
    assert removed_path == old_path
    
    # Old files should be removed
    assert not Path(temp_base_dir, "docs", old_path).exists()

@pytest.mark.asyncio
async def test_find_and_remove_no_old_report(publisher, temp_base_dir):
    """Test _find_and_remove_old_report when no old report exists."""
    # No reports exist yet
    removed_path = publisher._find_and_remove_old_report("test-org", "Sprint 1")
    
    # Should return None
    assert removed_path is None

@pytest.mark.asyncio
async def test_skip_duplicate_check(publisher, temp_base_dir):
    """Test that skip_duplicate_check parameter prevents overwrite."""
    # Publish first report with unique org name
    result1 = await publisher.publish_report(
        report_content="# First Report",
        org_name="test-org-unique1",
        iteration_name="Sprint 1",
        skip_duplicate_check=False
    )
    
    first_html = result1["html"]
    
    # Verify reports.json has one entry
    reports_json = Path(temp_base_dir, "docs", "reports.json")
    with open(reports_json) as f:
        reports = json.load(f)
    assert len(reports) == 1
    
    # Publish second report with different org (to avoid same filename) but skip_duplicate_check=True
    result2 = await publisher.publish_report(
        report_content="# Second Report",
        org_name="test-org-unique2",
        iteration_name="Sprint 1",
        skip_duplicate_check=True
    )
    
    second_html = result2["html"]
    
    # Verify both reports still exist
    assert Path(first_html).exists()
    assert Path(second_html).exists()
    
    # Verify reports.json now has TWO entries (no removal happened due to skip_duplicate_check)
    with open(reports_json) as f:
        reports = json.load(f)
    assert len(reports) == 2, "Should have two reports when skip_duplicate_check=True"

@pytest.mark.asyncio
async def test_update_reports_index_removes_duplicates(publisher, temp_base_dir):
    """Test that _update_reports_index removes old entries."""
    reports_json = Path(temp_base_dir, "docs", "reports.json")
    
    # Create initial reports.json with a duplicate entry
    initial_reports = [
        {
            "date": "2025-01-01T12:00:00",
            "title": "Old Report",
            "path": "old-report.html",
            "org_name": "test-org",
            "iteration_name": "Sprint 1"
        }
    ]
    
    with open(reports_json, 'w') as f:
        json.dump(initial_reports, f)
    
    # Call _update_reports_index with new entry
    publisher._update_reports_index({
        "date": "2025-01-02T12:00:00",
        "title": "New Report",
        "path": "new-report.html",
        "org_name": "test-org",
        "iteration_name": "Sprint 1"
    })
    
    # Read reports.json
    with open(reports_json) as f:
        reports = json.load(f)
    
    # Should only have one entry (old one removed)
    assert len(reports) == 1
    assert reports[0]["path"] == "new-report.html"
    assert reports[0]["title"] == "New Report"

@pytest.mark.asyncio
async def test_reports_with_none_iteration(publisher, temp_base_dir):
    """Test publishing reports with None iteration name."""
    # Publish with None iteration
    result1 = await publisher.publish_report(
        report_content="# Report 1",
        org_name="test-org",
        iteration_name=None
    )
    
    first_html = result1["html"]
    
    # Wait 2 seconds to ensure different timestamp
    import time
    time.sleep(2)
    
    # Publish another with None iteration (should overwrite)
    result2 = await publisher.publish_report(
        report_content="# Report 2",
        org_name="test-org",
        iteration_name=None
    )
    
    second_html = result2["html"]
    
    # Second report should exist
    assert Path(second_html).exists()
    
    # If filenames differ, first should be removed
    if first_html != second_html:
        assert not Path(first_html).exists()
    
    # Verify reports.json has only one entry for None iteration
    reports_json = Path(temp_base_dir, "docs", "reports.json")
    with open(reports_json) as f:
        reports = json.load(f)
    
    none_reports = [r for r in reports if r["org_name"] == "test-org" and r["iteration_name"] is None]
    assert len(none_reports) == 1, "Should only have one report for None iteration"

@pytest.mark.asyncio
async def test_html_contains_proper_formatting(publisher, temp_base_dir):
    """Test that published HTML contains proper CSS and formatting."""
    result = await publisher.publish_report(
        report_content="# Test\n\nSome text.",
        org_name="test-org",
        iteration_name="Sprint 1"
    )
    
    with open(result["html"]) as f:
        html = f.read()
    
    # Check for CSS styling
    assert "<style>" in html
    assert "font-family:" in html
    assert "border-collapse:" in html  # For tables
    
    # Check for metadata section
    assert "Report Metadata" in html
    assert "Organization:" in html
    assert "Iteration:" in html

@pytest.mark.asyncio
async def test_markdown_table_rendering(publisher, temp_base_dir):
    """Test that markdown tables are rendered properly in HTML."""
    report_content = """# Test Report

| Column 1 | Column 2 |
|----------|----------|
| Value 1  | Value 2  |
"""
    
    result = await publisher.publish_report(
        report_content=report_content,
        org_name="test-org",
        iteration_name="Sprint 1"
    )
    
    with open(result["html"]) as f:
        html = f.read()
    
    # Check for HTML table elements
    assert "<table>" in html
    assert "<thead>" in html
    assert "<tbody>" in html
    assert "<th>" in html
    assert "<td>" in html
    assert "Value 1" in html
    assert "Value 2" in html