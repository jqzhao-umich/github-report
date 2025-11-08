import os
import json
import logging
from typing import Dict, Any, Optional, List
import ast

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from mcp.server.base import MCP
from mcp.types import TextContent
from mcp.server.lowlevel.server import request_ctx

from agent_mcp_demo.reporting import publisher

# Setup logging
logger = logging.getLogger('web-interface-agent')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

app = FastAPI()
server = MCP("GitHub Report MCP Server")

# HTML template for the web interface
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>GitHub Organization Report</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }
        .header {
            text-align: center;
            margin-bottom: 20px;
        }
        .action-btn {
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            margin: 5px;
            font-weight: bold;
        }
        .primary-btn {
            background-color: #007bff;
            color: white;
        }
        .success-btn {
            background-color: #28a745;
            color: white;
        }
        .status-message {
            margin-top: 10px;
            padding: 10px;
            border-radius: 4px;
        }
        .error {
            background-color: #ffebee;
            color: #c62828;
            border: 1px solid #ffcdd2;
        }
        .success {
            background-color: #e8f5e9;
            color: #2e7d32;
            border: 1px solid #c8e6c9;
        }
        #report-container {
            margin-top: 20px;
            white-space: pre-wrap;
            font-family: monospace;
            padding: 10px;
            background-color: #f8f9fa;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>GitHub Report</h1>
            <h2>GitHub Organization Report</h2>
            <button class="action-btn primary-btn" onclick="loadReport()">Load Report</button>
            <button class="action-btn success-btn" onclick="publishReport()">Publish Report</button>
        </div>
        <div id="status-message"></div>
        <div id="report-container"></div>
    </div>
    <script>
        async function loadReport() {
            try {
                document.getElementById('status-message').innerHTML = '';
                const response = await fetch('/api/github-report');
                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.error || 'Failed to load report');
                }
                const report = await response.text();
                document.getElementById('report-container').textContent = report;
                showStatus('Report loaded successfully!', 'success');
            } catch (error) {
                showStatus(error.message, 'error');
            }
        }

        async function publishReport() {
            try {
                document.getElementById('status-message').innerHTML = '';
                const response = await fetch('/api/reports/publish', {
                    method: 'POST'
                });
                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.error || 'Failed to publish report');
                }
                const result = await response.json();
                showStatus(result.message, 'success');
            } catch (error) {
                showStatus(error.message, 'error');
            }
        }

        function showStatus(message, type) {
            const statusDiv = document.getElementById('status-message');
            statusDiv.className = `status-message ${type}`;
            statusDiv.textContent = message;
        }

        window.onload = loadReport;
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(content=HTML_TEMPLATE, status_code=200)

def ensure_github_token():
    """Ensure GitHub token is set in environment."""
    if not os.environ.get("GITHUB_TOKEN"):
        raise HTTPException(
            status_code=500,
            detail="GitHub token not set in environment"
        )

def ensure_org_name():
    """Ensure GitHub organization name is set in environment."""
    if not os.environ.get("GITHUB_ORG_NAME"):
        raise HTTPException(
            status_code=500,
            detail="GitHub organization name not set in environment"
        )

def ensure_mcp_context():
    """Ensure MCP server context is available."""
    context = request_ctx.get()
    if not context or not context.session:
        raise HTTPException(
            status_code=500,
            detail="MCP server context not available"
        )
    return context

async def get_iteration_info() -> Dict[str, str]:
    """Get iteration info from GitHub project."""
    context = ensure_mcp_context()
    org_name = os.environ.get("GITHUB_ORG_NAME", "")
    
    result = await context.session.call_tool(
        "mcp_github-agent_get-iteration-info",
        {"org_name": org_name}
    )
    
    if not result or not isinstance(result[0], TextContent):
        raise HTTPException(
            status_code=500,
            detail="Failed to get iteration info"
        )
    
    try:
        return ast.literal_eval(result[0].text)
    except (ValueError, SyntaxError) as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse iteration info: {str(e)}"
        )

async def get_github_data(iteration_info: Dict[str, str]) -> Dict[str, Any]:
    """Get GitHub data for the organization."""
    context = ensure_mcp_context()
    org_name = os.environ.get("GITHUB_ORG_NAME", "")
    
    result = await context.session.call_tool(
        "mcp_github-agent_get-github-data",
        {
            "org_name": org_name,
            "iteration_info": iteration_info
        }
    )
    
    if not result or not isinstance(result[0], TextContent):
        raise HTTPException(
            status_code=500,
            detail="Failed to get GitHub data"
        )
    
    try:
        return ast.literal_eval(result[0].text)
    except (ValueError, SyntaxError) as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to parse GitHub data: {str(e)}"
        )

def format_report(org_name: str, iteration_name: str, data: Dict[str, Any]) -> str:
    """Format the report data into a readable string."""
    report = [
        f"GitHub Organization: {org_name}",
        f"Iteration: {iteration_name}\n",
        "Member Statistics:",
    ]
    
    for user, stats in data['member_stats'].items():
        report.extend([
            f"\nUser: {user}",
            f"Commits: {stats['commits']}",
            f"Assigned Issues: {stats['assigned_issues']}",
            f"Closed Issues: {stats['closed_issues']}"
        ])
        
        # Add commit details if available
        if user in data['commit_details']:
            report.append("\nRecent Commits:")
            for commit in data['commit_details'][user]:
                report.append(f"- {commit['repo']}: {commit['message']} ({commit['date']})")
                
        # Add assigned issues if available
        if user in data['assigned_issues']:
            report.append("\nAssigned Issues:")
            for issue in data['assigned_issues'][user]:
                report.append(f"- {issue['repo']} #{issue['number']}: {issue['title']}")
                
        # Add closed issues if available
        if user in data['closed_issues']:
            report.append("\nClosed Issues:")
            for issue in data['closed_issues'][user]:
                report.append(f"- {issue['repo']} #{issue['number']}: {issue['title']} (Closed: {issue['closed_date']})")
    
    return "\n".join(report)

@app.get("/api/github-report")
async def github_report():
    """Generate a GitHub organization report."""
    ensure_github_token()
    ensure_org_name()
    
    org_name = os.environ["GITHUB_ORG_NAME"]
    
    # Get iteration info and GitHub data
    try:
        iteration_info = await get_iteration_info()
        github_data = await get_github_data(iteration_info)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
    
    report = format_report(org_name, iteration_info['name'], github_data)
    return report

def is_test_mode() -> bool:
    """Check if we're running in test mode."""
    return os.environ.get("TEST_MODE", "").lower() == "true"

async def background_publish(
    org_name: str,
    iteration_name: str,
    github_data: Dict[str, Any]
) -> None:
    """Background task for publishing reports."""
    try:
        report = format_report(org_name, iteration_name, github_data)
        await publisher.publish_report(
            org_name=org_name,
            iteration_name=iteration_name,
            report_data=report
        )
        logger.info(f"Published report for {org_name} - {iteration_name}")
    except Exception as e:
        if is_test_mode():
            logger.error(f"Error in test mode background publish task: {str(e)}")
            raise  # Re-raise in test mode
        else:
            logger.error(f"Error in background publish task: {str(e)}")

@app.post("/api/reports/publish")
async def publish_report(
    background_tasks: BackgroundTasks,
    request: Request
):
    """Start report generation and publishing process."""
    ensure_github_token()
    ensure_org_name()
    ensure_mcp_context()
    
    org_name = os.environ["GITHUB_ORG_NAME"]
    
    try:
        # Get data needed for the report
        iteration_info = await get_iteration_info()
        github_data = await get_github_data(iteration_info)
        
        # Add the background task
        if is_test_mode():
            # In test mode, we run the task synchronously
            await background_publish(org_name, iteration_info['name'], github_data)
        else:
            # Normal mode - run as background task
            background_tasks.add_task(
                background_publish,
                org_name,
                iteration_info['name'],
                github_data
            )
        
        return {
            "message": "Report generation started. It will be published shortly.",
            "org_name": org_name,
            "iteration_name": iteration_info['name']
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )