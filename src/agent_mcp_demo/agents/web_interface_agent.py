"""Web Interface Agent - MCP Server + Client + FastAPI Server

This is an MCP SERVER that also acts as a CLIENT and runs a FastAPI web server.

Server roles:
1. MCP Server: Provides tools for report generation (when used via MCP protocol)
2. FastAPI Server: HTTP endpoints on port 8000 for web-based report access

Client role (calls other agents):
- Calls github-agent to fetch iteration info and organization data
- Coordinates data from multiple sources for report generation

HTTP Endpoints:
- GET /: Web interface for viewing reports
- GET /api/github-report: Generate and return report text
- POST /api/reports/publish: Publish report to GitHub Pages

Note: This agent bridges MCP protocol and HTTP, enabling both programmatic
and web-based access to GitHub organization reports.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import os
import logging
from datetime import datetime, timezone, timedelta
from mcp.server import Server, NotificationOptions

# Set up logging
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/web.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('web-interface-agent')
from mcp.server.models import InitializationOptions
from ..utils import get_detroit_timezone, get_env_var, format_datetime
from ..utils.report_publisher import ReportPublisher
import requests

publisher = ReportPublisher()

try:
    import uvicorn
except ImportError:
    raise ImportError("uvicorn is required. Install it with: pip install uvicorn")

# Configure FastAPI app with CORS
app = FastAPI(title="GitHub Report Server",
             description="MCP-based GitHub organization report generator",
             version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

server = Server("web-interface-agent")

def get_github_username(token: str) -> str:
    """Fetch the GitHub username associated with the token."""
    headers = {"Authorization": f"token {token}"}
    response = requests.get("https://api.github.com/user", headers=headers)
    if response.status_code == 200:
        return response.json().get("login", "")
    return ""

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>GitHub Report</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { text-align: center; margin-bottom: 30px; }
            .refresh-btn { 
                background-color: #007bff; 
                color: white; 
                padding: 10px 20px; 
                border: none; 
                border-radius: 5px; 
                cursor: pointer; 
                font-size: 16px;
                margin-bottom: 20px;
            }
            .refresh-btn:hover { background-color: #0056b3; }
            .refresh-btn:disabled { background-color: #6c757d; cursor: not-allowed; }
            .loading { color: #666; font-style: italic; }
            .error { color: #dc3545; }
            .report { 
                background-color: #f8f9fa; 
                padding: 20px; 
                border-radius: 5px; 
                white-space: pre-wrap; 
                font-family: monospace; 
                font-size: 14px;
                max-height: 600px;
                overflow-y: auto;
            }
            .actions {
                margin: 20px 0;
                display: flex;
                gap: 10px;
            }
            .action-btn {
                padding: 10px 20px;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-size: 16px;
            }
            .primary-btn {
                background-color: #007bff;
                color: white;
            }
            .primary-btn:hover {
                background-color: #0056b3;
            }
            .success-btn {
                background-color: #28a745;
                color: white;
            }
            .success-btn:hover {
                background-color: #218838;
            }
            .status-message {
                margin-top: 10px;
                padding: 10px;
                border-radius: 5px;
            }
            .status-message.success {
                background-color: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }
            .status-message.error {
                background-color: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }
            .error-details {
                margin-top: 10px;
                padding: 10px;
                background: #fff;
                border: 1px solid #dc3545;
                border-radius: 4px;
                font-size: 12px;
                white-space: pre-wrap;
                overflow-x: auto;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>GitHub Organization Report</h1>
                <div class="actions">
                    <button class="action-btn primary-btn" onclick="loadReport()">Refresh Report</button>
                    <button class="action-btn success-btn" onclick="publishReport()">Save Report</button>
                </div>
            </div>
            <div id="report-container">
                <div class="loading">Loading report...</div>
            </div>
        </div>
        
        <script>
            async function loadReport() {
                const btn = document.querySelector('.primary-btn');
                const container = document.getElementById('report-container');
                
                btn.disabled = true;
                btn.textContent = 'Loading...';
                container.innerHTML = '<div class="loading">Loading report...</div>';
                
                try {
                    const response = await fetch('/api/github-report');
                    const contentType = response.headers.get('content-type');
                    let data;
                    
                    if (contentType && contentType.includes('application/json')) {
                        // Parse JSON response
                        data = await response.json();
                        if (data.error) {
                            throw new Error(data.error);
                        }
                    } else {
                        // Handle text response
                        data = await response.text();
                    }
                    
                    if (!response.ok) {
                        throw new Error(typeof data === 'string' ? data : (data.error || 'Unknown error'));
                    }
                    
                    if (typeof data === 'string') {
                        container.innerHTML = '<div class="report">' + data + '</div>';
                    } else {
                        container.innerHTML = '<div class="report">' + JSON.stringify(data, null, 2) + '</div>';
                    }
                } catch (error) {
                    console.error('Error loading report:', error);
                    container.innerHTML = '<div class="error">Error loading report: ' + error.message + '</div>';
                } finally {
                    btn.disabled = false;
                    btn.textContent = 'Refresh Report';
                }
            }
            
            async function publishReport() {
                const btn = document.querySelector('.success-btn');
                const container = document.getElementById('report-container');
                
                btn.disabled = true;
                btn.textContent = 'Publishing...';
                
                try {
                    const response = await fetch('/api/reports/publish', {
                        method: 'POST'
                    });
                    const result = await response.json();
                    
                    if (response.ok) {
                        container.insertAdjacentHTML('beforebegin', 
                            '<div class="status-message success">' + 
                            'Report started publishing for ' + result.org_name + 
                            (result.iteration_name ? ' - ' + result.iteration_name : '') +
                            '</div>'
                        );
                    } else {
                        container.insertAdjacentHTML('beforebegin',
                            '<div class="status-message error">Error: ' + 
                            (result.error || 'Failed to publish report') + 
                            (result.details ? '<pre class="error-details">' + result.details + '</pre>' : '') +
                            '</div>'
                        );
                    }
                } catch (error) {
                    container.insertAdjacentHTML('beforebegin',
                        '<div class="status-message error">Error: ' + 
                        error.message + '</div>'
                    );
                } finally {
                    btn.disabled = false;
                    btn.textContent = 'Save Report';
                    
                    // Remove status message after 5 seconds
                    setTimeout(() => {
                        const messages = document.querySelectorAll('.status-message');
                        messages.forEach(msg => msg.remove());
                    }, 5000);
                }
            }
            
            // Load report on page load
            window.onload = loadReport;
        </script>
    </body>
    </html>
    """

@app.get("/api/github-report", response_class=JSONResponse)
async def github_report_api():
    """
    Fetches all members of a GitHub organization, counts their commits and assigned issues for the current iteration, 
    and returns a report.
    """
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    ORG_NAME = os.environ.get("GITHUB_ORG_NAME")
    
    if not GITHUB_TOKEN:
        return JSONResponse(
            {"error": "GitHub token not set in environment. Please set GITHUB_TOKEN environment variable."}, 
            status_code=500
        )
    if not ORG_NAME:
        return JSONResponse(
            {"error": "GitHub organization name not set in environment. Please set GITHUB_ORG_NAME environment variable."}, 
            status_code=500
        )
    
    import time
    request_start_time = datetime.now().astimezone()
    # Detect if we're in daylight saving time
    tz_name = "EDT" if time.localtime().tm_isdst else "EST"
    
    # Get data from GitHub agent (only if MCP context is available)
    iteration_info = None
    github_data = None
    
    try:
        # First check if we can access the GitHub agent
        if not hasattr(server, "request_context") or not server.request_context or not server.request_context.session:
            return "MCP server context not available. This endpoint requires the MCP server to be running with agent connections."
            
        logger.info("Calling GitHub agent for iteration info...")
        iteration_info_result = await server.request_context.session.call_tool(
            "github-agent", 
            "get-iteration-info",
            {"org_name": ORG_NAME}
        )
        
        logger.info(f"Iteration info result: {iteration_info_result}")
        if not iteration_info_result:
            logger.warning("No iteration info returned from GitHub agent")
        elif not isinstance(iteration_info_result, list):
            logger.warning(f"Unexpected iteration info type: {type(iteration_info_result)}")
        elif len(iteration_info_result) > 0:
            try:
                iteration_info = eval(iteration_info_result[0].text)
                print(f"Found iteration info: {iteration_info}")
            except Exception as e:
                print(f"Error parsing iteration info: {e}")
                iteration_info = None
        
        logger.info("Calling GitHub agent for organization data...")
        github_data_result = await server.request_context.session.call_tool(
            "github-agent",
            "get-github-data",
            {
                "org_name": ORG_NAME,
                "iteration_info": iteration_info
            }
        )
        
        logger.info(f"GitHub data result: {github_data_result}")
        if not github_data_result:
            raise ValueError("No response from GitHub agent")
        if not isinstance(github_data_result, list):
            raise ValueError(f"Unexpected response type from GitHub agent: {type(github_data_result)}")
        if len(github_data_result) == 0:
            raise ValueError("Empty response from GitHub agent")
        if not hasattr(github_data_result[0], 'text'):
            raise ValueError(f"Invalid response format from GitHub agent: {github_data_result[0]}")
            
        # Try to parse the GitHub data and validate it
        try:
            github_data = eval(github_data_result[0].text)
            if not isinstance(github_data, dict):
                raise ValueError(f"GitHub data is not a dictionary: {type(github_data)}")
            if 'member_stats' not in github_data:
                raise ValueError("GitHub data missing required 'member_stats' field")
        except Exception as e:
            logger.error(f"Failed to parse GitHub data: {e}")
            logger.error(f"Raw data: {github_data_result[0].text}")
            raise ValueError(f"Failed to parse GitHub data: {e}")
            
        try:
            github_data = eval(github_data_result[0].text)
            print(f"Parsed GitHub data successfully: {len(github_data.get('member_stats', {})) if github_data else 0} members found")
        except Exception as e:
            print(f"Error parsing GitHub data: {e}")
            raise ValueError(f"Invalid data returned from GitHub agent: {e}")
    except (LookupError, AttributeError):
        # MCP context not available - return error message
        return "MCP server context not available. This endpoint requires the MCP server to be running with agent connections."
    
    # Generate report
    report = []
    report.append(f"GitHub Organization: {ORG_NAME}")
    report.append(f"Report started on: {request_start_time.strftime('%Y-%m-%d %I:%M:%S %p')} {tz_name}\n")
    
    if iteration_info:
        report.append("=" * 60)
        report.append("CURRENT ITERATION INFORMATION")
        report.append("=" * 60)
        report.append(f"Iteration Name: {iteration_info.get('name', 'Unknown')}")
        if iteration_info.get('start_date'):
            report.append(f"Start Date: {iteration_info['start_date']} ({tz_name})")
        if iteration_info.get('end_date'):
            report.append(f"End Date: {iteration_info['end_date']} ({tz_name})")
        if iteration_info.get('path'):
            report.append(f"Iteration Path: {iteration_info['path']}")
        report.append("=" * 60)
        report.append("")
    
    # Summary section
    report.append("\nSUMMARY")
    report.append("=" * 60)
    report.append(f"{'User':20} | {'Commits':7} | {'Assigned Issues':14} | {'Closed Issues':13} | {'PRs Created':11} | {'PRs Reviewed':12} | {'PRs Merged':10} | {'PRs Commented':13}")
    report.append("-" * 140)
    
    member_stats = github_data['member_stats']
    commit_details = github_data['commit_details']
    assigned_issues = github_data['assigned_issues']
    closed_issues = github_data['closed_issues']
    pr_created = github_data.get('pr_created', {})
    pr_reviewed = github_data.get('pr_reviewed', {})
    pr_merged = github_data.get('pr_merged', {})
    pr_commented = github_data.get('pr_commented', {})
    
    # Exclude the current user from the report
    current_user = get_github_username(GITHUB_TOKEN) if GITHUB_TOKEN else None
    
    for login, stats in member_stats.items():
        if current_user and login == current_user:
            continue  # Skip myself
        report.append(f"{login:20} | {stats['commits']:7} | {stats['assigned_issues']:14} | {stats['closed_issues']:13} | {stats.get('pr_created', 0):11} | {stats.get('pr_reviewed', 0):12} | {stats.get('pr_merged', 0):10} | {stats.get('pr_commented', 0):13}")
    
    # Detailed section
    report.append("\nDETAILED ACTIVITY")
    report.append("=" * 60)
    
    for login, stats in member_stats.items():
        if current_user and login == current_user:
            continue  # Skip myself
        if (stats['commits'] > 0 or stats['assigned_issues'] > 0 or stats['closed_issues'] > 0 or 
            stats.get('pr_created', 0) > 0 or stats.get('pr_reviewed', 0) > 0 or 
            stats.get('pr_merged', 0) > 0 or stats.get('pr_commented', 0) > 0):
            report.append(f"\nUser: {login}")
            report.append("-" * 40)
            
            if stats['commits'] > 0:
                report.append("\nCommits:")
                for commit_info in commit_details.get(login, []):
                    report.append(f"- [{commit_info['repo']}] {commit_info['message']} ({commit_info['date'].strftime('%Y-%m-%d')})")
            
            if stats['assigned_issues'] > 0:
                report.append("\nAssigned Issues:")
                for issue_info in assigned_issues.get(login, []):
                    status = "Open" if issue_info['state'] == "open" else "Closed"
                    report.append(f"- [{issue_info['repo']}] #{issue_info['number']} {issue_info['title']} ({status})")
            
            if stats['closed_issues'] > 0:
                report.append("\nClosed Issues:")
                for issue_info in closed_issues.get(login, []):
                    report.append(f"- [{issue_info['repo']}] #{issue_info['number']} {issue_info['title']} (Closed on {issue_info['closed_date'].strftime('%Y-%m-%d')})")
            
            if stats.get('pr_created', 0) > 0:
                report.append("\nPull Requests Created:")
                for pr_info in pr_created.get(login, []):
                    status = "Merged" if pr_info.get('merged_at') else ("Closed" if pr_info['state'] == "closed" else "Open")
                    report.append(f"- [{pr_info['repo']}] #{pr_info['number']} {pr_info['title']} ({status})")
            
            if stats.get('pr_reviewed', 0) > 0:
                report.append("\nPull Requests Reviewed:")
                for pr_info in pr_reviewed.get(login, []):
                    status = "Merged" if pr_info.get('merged_at') else ("Closed" if pr_info['state'] == "closed" else "Open")
                    report.append(f"- [{pr_info['repo']}] #{pr_info['number']} {pr_info['title']} ({status})")
            
            if stats.get('pr_merged', 0) > 0:
                report.append("\nPull Requests Merged:")
                for pr_info in pr_merged.get(login, []):
                    merged_date = pr_info.get('merged_at').strftime('%Y-%m-%d') if pr_info.get('merged_at') else 'N/A'
                    report.append(f"- [{pr_info['repo']}] #{pr_info['number']} {pr_info['title']} (Merged on {merged_date})")
            
            if stats.get('pr_commented', 0) > 0:
                report.append("\nPull Requests Commented:")
                for pr_info in pr_commented.get(login, []):
                    status = "Merged" if pr_info.get('merged_at') else ("Closed" if pr_info['state'] == "closed" else "Open")
                    report.append(f"- [{pr_info['repo']}] #{pr_info['number']} {pr_info['title']} ({status})")
            
            report.append("")
    
    # Add report completion time
    report_end_time = datetime.now().astimezone()
    report.append("=" * 60)
    report.append(f"Report completed on: {report_end_time.strftime('%Y-%m-%d %I:%M:%S %p')} {tz_name}")
    report.append(f"Generation time: {(report_end_time - request_start_time).total_seconds():.2f} seconds")
    
    return "\n".join(report)

@app.get("/github-report", response_class=PlainTextResponse)
async def github_report():
    """
    Legacy endpoint that redirects to the new web interface.
    """
    return "GitHub Report Server is running! Visit / for the web interface or /api/github-report for the raw report."

@app.post("/api/reports/publish", response_class=JSONResponse)
async def publish_report(background_tasks: BackgroundTasks):
    """
    Publish the current report to GitHub Pages.
    The report will be generated and published asynchronously.
    """
    try:
        from mcp.server.lowlevel.server import request_ctx
        
        # Check if MCP context is available
        try:
            ctx = request_ctx.get()
            if not ctx or not ctx.session:
                return JSONResponse({
                    "error": "MCP server context not available. This endpoint requires the MCP server to be running with agent connections."
                }, status_code=500)
        except LookupError:
            return JSONResponse({
                "error": "MCP server context not available. This endpoint requires the MCP server to be running with agent connections."
            }, status_code=500)

        report_text = await github_report_api()
        logger.info(f"Got report text: {report_text[:200]}...")
        
        if isinstance(report_text, str) and "error" in report_text.lower():
            return JSONResponse({"error": report_text}, status_code=500)
            
        # Parse organization name from the report
        lines = report_text.split("\n")
        if not lines or not lines[0].startswith("GitHub Organization:"):
            raise ValueError(f"Invalid report format - does not start with organization info")
            
        org_line_parts = lines[0].split(": ")
        if len(org_line_parts) != 2:
            raise ValueError(f"Invalid organization line format: {lines[0]}")
            
        org_name = org_line_parts[1].strip()

        # Check if required environment variables are set
        if not os.environ.get("GITHUB_TOKEN"):
            raise ValueError("GitHub token not set. Please set GITHUB_TOKEN environment variable.")
        if not os.environ.get("GITHUB_ORG_NAME"):
            raise ValueError("GitHub organization name not set. Please set GITHUB_ORG_NAME environment variable.")
        
        # Parse iteration info if available
        iteration_info = {}
        try:
            if "CURRENT ITERATION INFORMATION" in report_text:
                info_section = report_text.split("CURRENT ITERATION INFORMATION")[1].split("SUMMARY")[0]
                for line in info_section.split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip()
                        value = value.strip()
                        if "Iteration Name" in key:
                            iteration_info["name"] = value
                        elif "Start Date" in key:
                            iteration_info["start_date"] = value
                        elif "End Date" in key:
                            iteration_info["end_date"] = value
                logger.info(f"Parsed iteration info: {iteration_info}")
        except Exception as e:
            logger.warning(f"Error parsing iteration info: {e}")
            # Don't fail if iteration info parsing fails
        
        async def publish_in_background():
            try:
                logger.info("Starting background publish task...")
                logger.info(f"Publishing report for org: {org_name}")
                logger.info(f"Iteration info: {iteration_info}")
                
                result = await publisher.publish_report(
                    report_content=report_text,
                    org_name=org_name,
                    iteration_name=iteration_info.get("name"),
                    start_date=iteration_info.get("start_date"),
                    end_date=iteration_info.get("end_date")
                )
                logger.info(f"Publish result: {result}")
                return result
            except Exception as e:
                logger.error(f"Error in background publish task: {e}", exc_info=True)
                raise
            
        # In test mode, run the task directly
        test_mode = os.environ.get("TEST_MODE") == "true"
        if test_mode:
            try:
                await publish_in_background()
            except Exception as e:
                # In test mode, log the error but don't let it affect the response
                logger.error(f"Error in test mode background publish: {e}", exc_info=True)
        else:
            background_tasks.add_task(publish_in_background)
        
        return JSONResponse({
            "message": "Report generation started. It will be published shortly.",
            "org_name": org_name,
            "iteration_name": iteration_info.get("name", "N/A")
        })
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error in publish_report: {error_details}")
        return JSONResponse(
            {
                "error": f"Failed to publish report: {str(e)}",
                "details": error_details
            }, 
            status_code=500
        )

async def main():
    from mcp.server.stdio import stdio_server
    import os
    import uvicorn
    
    # Start FastAPI app in the background
    config = uvicorn.Config(app, host="0.0.0.0", port=8000)
    uvicorn_server = uvicorn.Server(config)
    import asyncio
    asyncio.create_task(uvicorn_server.serve())
    
    # Run MCP server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="web-interface-agent",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
