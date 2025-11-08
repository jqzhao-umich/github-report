"""Routes for GitHub Organization reports."""
import os
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse
from agent_mcp_demo.utils.report_publisher import ReportPublisher

app = FastAPI()

@app.post("/api/reports/publish", response_class=HTMLResponse)
async def publish_organization_report(
    report_content: str,
    org_name: str,
    iteration_name: str = None,
    start_date: str = None,
    end_date: str = None
) -> dict:
    """
    Publish a GitHub organization report to both the Git repo and GitHub Pages.
    
    Args:
        report_content: The report content in markdown format
        org_name: GitHub organization name
        iteration_name: Optional name of the iteration/sprint
        start_date: Optional start date of the iteration
        end_date: Optional end date of the iteration
        
    Returns:
        Dict containing the paths to the published files and web URL
    """
    publisher = ReportPublisher()
    
    # Publish report to both storage locations
    result = publisher.publish_report(
        report_content=report_content,
        org_name=org_name,
        iteration_name=iteration_name,
        start_date=start_date,
        end_date=end_date
    )
    
    return result