from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse, HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import os
from datetime import datetime, timezone, timedelta
import mcp.types as types
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from ..utils import get_detroit_timezone, get_env_var, format_datetime
from ..utils.report_publisher import ReportPublisher

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

app = FastAPI()

server = Server("web-interface-agent")

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
                const btn = document.querySelector('.refresh-btn');
                const container = document.getElementById('report-container');
                
                btn.disabled = true;
                btn.textContent = 'Loading...';
                container.innerHTML = '<div class="loading">Loading report...</div>';
                
                try {
                    const response = await fetch('/api/github-report');
                    const data = await response.text();
                    
                    if (response.ok) {
                        container.innerHTML = '<div class="report">' + data + '</div>';
                    } else {
                        container.innerHTML = '<div class="error">Error: ' + data + '</div>';
                    }
                } catch (error) {
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
                            (result.error || 'Failed to publish report') + '</div>'
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

@app.get("/api/github-report", response_class=PlainTextResponse)
async def github_report_api():
    """
    Fetches all members of a GitHub organization, counts their commits and assigned issues for the current iteration, 
    and returns a report.
    """
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    ORG_NAME = os.environ.get("GITHUB_ORG_NAME")
    
    if not GITHUB_TOKEN:
        return "GitHub token not set in environment. Please set GITHUB_TOKEN environment variable."
    if not ORG_NAME:
        return "GitHub organization name not set in environment. Please set GITHUB_ORG_NAME environment variable."
    
    detroit_tz = get_detroit_timezone()
    request_start_time = datetime.now(detroit_tz)
    
    # Get data from GitHub agent (only if MCP context is available)
    iteration_info = None
    github_data = None
    
    try:
        iteration_info_result = await server.request_context.session.call_tool(
            "github-agent", 
            "get-iteration-info",
            {"org_name": ORG_NAME}
        )
        
        if isinstance(iteration_info_result, list) and len(iteration_info_result) > 0:
            iteration_info = eval(iteration_info_result[0].text)
        
        github_data_result = await server.request_context.session.call_tool(
            "github-agent",
            "get-github-data",
            {
                "org_name": ORG_NAME,
                "iteration_info": iteration_info
            }
        )
        
        if isinstance(github_data_result, list) and len(github_data_result) > 0:
            github_data = eval(github_data_result[0].text)
    except (LookupError, AttributeError):
        # MCP context not available - return error message
        return "MCP server context not available. This endpoint requires the MCP server to be running with agent connections."
    
    # Generate report
    report = []
    report.append(f"GitHub Organization: {ORG_NAME}")
    report.append(f"Report started on: {request_start_time.strftime('%Y-%m-%d %I:%M:%S %p EDT')}\n")
    
    if iteration_info:
        report.append("=" * 60)
        report.append("CURRENT ITERATION INFORMATION")
        report.append("=" * 60)
        report.append(f"Iteration Name: {iteration_info.get('name', 'Unknown')}")
        if iteration_info.get('start_date'):
            report.append(f"Start Date: {iteration_info['start_date']}")
        if iteration_info.get('end_date'):
            report.append(f"End Date: {iteration_info['end_date']}")
        if iteration_info.get('path'):
            report.append(f"Iteration Path: {iteration_info['path']}")
        report.append("=" * 60)
        report.append("")
    
    # Summary section
    report.append("\nSUMMARY")
    report.append("=" * 60)
    report.append(f"{'User':20} | {'Commits':7} | {'Assigned Issues':14} | {'Closed Issues':13}")
    report.append("-" * 65)
    
    member_stats = github_data['member_stats']
    commit_details = github_data['commit_details']
    assigned_issues = github_data['assigned_issues']
    closed_issues = github_data['closed_issues']
    
    for login, stats in member_stats.items():
        report.append(f"{login:20} | {stats['commits']:7} | {stats['assigned_issues']:14} | {stats['closed_issues']:13}")
    
    # Detailed section
    report.append("\nDETAILED ACTIVITY")
    report.append("=" * 60)
    
    for login, stats in member_stats.items():
        if stats['commits'] > 0 or stats['assigned_issues'] > 0 or stats['closed_issues'] > 0:
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
            
            report.append("")
    
    # Add report completion time
    report_end_time = datetime.now(detroit_tz)
    report.append("=" * 60)
    report.append(f"Report completed on: {report_end_time.strftime('%Y-%m-%d %I:%M:%S %p EDT')}")
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
    Publish the current report to both Git storage and GitHub Pages.
    The report will be generated and published asynchronously.
    """
    try:
        report_text = await github_report_api()
        if isinstance(report_text, str) and "error" in report_text.lower():
            return JSONResponse({"error": report_text}, status_code=500)
            
        # Parse iteration info from the report text
        lines = report_text.split("\n")
        org_name = lines[0].split(": ")[1]
        
        iteration_info = {}
        if "CURRENT ITERATION INFORMATION" in report_text:
            info_section = report_text.split("CURRENT ITERATION INFORMATION")[1].split("SUMMARY")[0]
            for line in info_section.split("\n"):
                if "Iteration Name:" in line:
                    iteration_info["name"] = line.split(": ")[1]
                elif "Start Date:" in line:
                    iteration_info["start_date"] = line.split(": ")[1]
                elif "End Date:" in line:
                    iteration_info["end_date"] = line.split(": ")[1]
        
        def publish_in_background():
            result = publisher.publish_report(
                report_content=report_text,
                org_name=org_name,
                iteration_name=iteration_info.get("name"),
                start_date=iteration_info.get("start_date"),
                end_date=iteration_info.get("end_date")
            )
            return result
            
        background_tasks.add_task(publish_in_background)
        
        return JSONResponse({
            "message": "Report generation started. It will be published shortly.",
            "org_name": org_name,
            "iteration_name": iteration_info.get("name")
        })
        
    except Exception as e:
        return JSONResponse(
            {"error": f"Failed to publish report: {str(e)}"}, 
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
