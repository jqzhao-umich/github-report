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

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.responses import PlainTextResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import os
import logging
from datetime import datetime, timezone, timedelta
from mcp.server import Server, NotificationOptions, InitializationOptions

from . import _peer_client, _wire
from ..auth import require_auth

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

# CORS: the UI is served from the same origin as the API, so no
# cross-origin access is needed. If you need to expose the API to an
# external client, set CORS_ALLOWED_ORIGINS to a comma-separated list of
# exact trusted origins (never "*") and re-enable this block.
_cors_env = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
if _cors_env:
    _allowed_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

server = Server("web-interface-agent", version="0.1.0")

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
            // XSS-safe helpers: build DOM nodes with textContent, never
            // interpolate user/GitHub-controlled strings into innerHTML.
            function renderMessage(container, cls, text) {
                const div = document.createElement('div');
                div.className = cls;
                div.textContent = text;
                container.replaceChildren(div);
            }
            function renderReport(container, text) {
                const wrap = document.createElement('div');
                wrap.className = 'report';
                const pre = document.createElement('pre');
                pre.textContent = text;
                wrap.appendChild(pre);
                container.replaceChildren(wrap);
            }
            function showStatus(container, kind, text) {
                document.querySelector('.status-message')?.remove();
                const div = document.createElement('div');
                // Use the literal class strings so they show up in static
                // scans (and to keep them grep-able for tests).
                div.className = kind === 'error' ? 'status-message error' : 'status-message success';
                div.textContent = text;
                container.parentNode.insertBefore(div, container);
                return div;
            }

            async function loadReport() {
                const btn = document.querySelector('.primary-btn');
                const container = document.getElementById('report-container');

                btn.disabled = true;
                btn.textContent = 'Loading...';
                renderMessage(container, 'loading', 'Loading report...');

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

                    const text = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
                    renderReport(container, text);
                } catch (error) {
                    console.error('Error loading report:', error);
                    renderMessage(container, 'error', 'Error loading report: ' + error.message);
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
                        const suffix = result.iteration_name ? ' - ' + result.iteration_name : '';
                        showStatus(container, 'success',
                            'Report started publishing for ' + result.org_name + suffix);
                    } else {
                        // Never render server-provided error details as HTML.
                        showStatus(container, 'error', 'Error: ' + (result.error || 'Failed to publish report'));
                    }
                } catch (error) {
                    showStatus(container, 'error', 'Error: ' + error.message);
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

@app.get("/api/github-report", response_class=JSONResponse, dependencies=[Depends(require_auth)])
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
    
    # Get data from GitHub agent via the peer-agent RPC shim
    iteration_info = None
    github_data = None

    try:
        logger.info("Calling GitHub agent for iteration info...")
        iteration_info_text = await _peer_client.call_peer_tool(
            "github-agent",
            "get-iteration-info",
            {"org_name": ORG_NAME},
        )

        # Peer-agent responses may contain arbitrary GitHub-derived text
        # (issue titles, commit messages, error strings from GitHub's
        # API). Log only a length/type summary — never the full payload —
        # so log files can't be turned into an attacker echo channel.
        logger.info(
            "Iteration info result: len=%s type=%s",
            len(iteration_info_text) if iteration_info_text else 0,
            type(iteration_info_text).__name__,
        )
        if iteration_info_text:
            try:
                iteration_info = _wire.decode(iteration_info_text)
                logger.info("Parsed iteration info OK")
            except (ValueError, TypeError):
                # Reject anything that isn't well-formed wire JSON. Never eval.
                logger.warning("Iteration info was not valid wire JSON; ignoring")
                iteration_info = None

        logger.info("Calling GitHub agent for organization data...")
        github_data_text = await _peer_client.call_peer_tool(
            "github-agent",
            "get-github-data",
            {"org_name": ORG_NAME, "iteration_info": iteration_info},
        )

        logger.info(
            "GitHub data result: len=%s",
            len(github_data_text) if github_data_text else 0,
        )
        if not github_data_text:
            raise ValueError("No response from GitHub agent")

        # Try to parse the GitHub data and validate it. _wire.decode is a
        # strict JSON parser — never executes untrusted content.
        try:
            github_data = _wire.decode(github_data_text)
            if not isinstance(github_data, dict):
                raise ValueError("GitHub data is not a dictionary")
            if 'member_stats' not in github_data:
                raise ValueError("GitHub data missing required 'member_stats' field")
        except (ValueError, TypeError) as e:
            # Log the exception summary only. The raw payload stays out
            # of the log — see the length-only logger.info above.
            logger.error("Failed to parse GitHub data: %r", e)
            raise ValueError("Failed to parse GitHub data")
    except (LookupError, AttributeError, NotImplementedError):
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

@app.post("/api/reports/publish", response_class=JSONResponse, dependencies=[Depends(require_auth)])
async def publish_report(background_tasks: BackgroundTasks):
    """
    Publish the current report to GitHub Pages.
    The report will be generated and published asynchronously.
    """
    try:
        # Availability of the peer-agent RPC path is now determined at call time
        # (see agent_mcp_demo.agents._peer_client). The old low-level request_ctx
        # ambient ContextVar was removed in mcp 2.0.
        report_text = await github_report_api()
        # github_report_api returns a JSONResponse for environment errors
        if isinstance(report_text, JSONResponse):
            return report_text
        logger.info(f"Got report text: {report_text[:200]}...")

        if isinstance(report_text, str) and report_text.startswith("MCP server context not available"):
            return JSONResponse({"error": report_text}, status_code=500)
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
        
    except ValueError as e:
        # Input-shape errors (bad report format, unparseable peer response,
        # missing env vars) are safe to surface — they describe the bad
        # input, not internal state.
        return JSONResponse({"error": str(e)}, status_code=500)
    except Exception:
        # Debug traceback responses were removed here too — the full
        # traceback goes to the logger keyed by correlation_id, never
        # back to the caller.
        import uuid
        correlation_id = uuid.uuid4().hex[:12]
        logger.exception("publish_report failed (correlation_id=%s)", correlation_id)
        return JSONResponse(
            {"error": "Failed to publish report", "correlation_id": correlation_id},
            status_code=500,
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
