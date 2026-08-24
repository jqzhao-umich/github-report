"""GitHub Report Server - Dual Purpose: Standalone Function + MCP Server

This module contains:

1. STANDALONE FUNCTION: github_report_api()
   - Collects GitHub metrics WITHOUT using MCP
   - Used by: GitHub Actions workflows for scheduled reports
   - Directly accesses GitHub API (no agent coordination)
   
2. MCP SERVER: Main coordinator server
   - Provides: MCP tools for orchestration
   - Also includes: FastAPI web server on port 8000
   - Scheduled report generation based on iteration cycles

3. SHARED UTILITIES:
   - Report publishing to GitHub Pages
   - Git operations for automated deployment

Note: Both the standalone function and github_agent.py collect the same metrics,
but via different mechanisms (direct API vs MCP protocol).
"""

import asyncio
import json
import httpx
import requests
from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks, Depends, Request
from fastapi.responses import PlainTextResponse, HTMLResponse, JSONResponse
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio
import os
from github import Github, Auth
from dotenv import load_dotenv
from pathlib import Path
import sys
# Removed Azure DevOps imports - now using GitHub Projects

# Load environment variables from .env file at startup
load_dotenv()

# Add the src directory to the path so we can import from agent_mcp_demo
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agent_mcp_demo.auth import require_auth
from agent_mcp_demo.utils.report_publisher import ReportPublisher
from agent_mcp_demo.utils.git_operations import GitOperations
from agent_mcp_demo.utils.report_scheduler import ReportScheduler
from agent_mcp_demo.utils.pr_metrics import collect_pr_metrics
from agent_mcp_demo.utils.iteration_info import get_current_iteration_info
from agent_mcp_demo.utils.github_members import collect_members_and_emails, initialize_detail_structures
from agent_mcp_demo.utils.commit_metrics import collect_commit_metrics
from agent_mcp_demo.utils.issue_metrics import collect_issue_metrics

# Initialize the report publisher and git operations
publisher = ReportPublisher()
git_ops = GitOperations()

# Initialize scheduler (will be started in lifespan event)
scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan - startup and shutdown."""
    global scheduler
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Startup
    scheduler = ReportScheduler(
        report_generator_callback=github_report_api,
        publish_callback=lambda report_text, org_name, iteration_name, skip_duplicate_check: 
            publisher.publish_report(
                report_content=report_text,
                org_name=org_name,
                iteration_name=iteration_name,
                start_date=os.getenv("GITHUB_ITERATION_START"),
                end_date=os.getenv("GITHUB_ITERATION_END"),
                skip_duplicate_check=skip_duplicate_check
            ),
        git_operations=git_ops
    )
    scheduler.start()
    logging.info("Application started with automatic report scheduling")
    
    yield
    
    # Shutdown
    if scheduler:
        scheduler.stop()

# Add FastAPI app for HTTP endpoints
app = FastAPI(lifespan=lifespan)

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
            .actions { 
                margin: 20px 0;
                display: flex;
                gap: 10px;
                justify-content: center;
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
            .primary-btn:disabled {
                background-color: #6c757d;
                cursor: not-allowed;
            }
            .success-btn {
                background-color: #28a745;
                color: white;
            }
            .success-btn:hover {
                background-color: #218838;
            }
            .success-btn:disabled {
                background-color: #6c757d;
                cursor: not-allowed;
            }
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
                    <button class="action-btn success-btn" onclick="publishReport()">Save to GitHub Pages</button>
                </div>
            </div>
            <div id="report-container">
                <div class="loading">Loading report...</div>
            </div>
        </div>
        
        <script>
            // Store the current report content
            let currentReportContent = null;

            // XSS-safe helpers: build DOM nodes with textContent, never
            // interpolate user/GitHub-controlled strings into innerHTML.
            function renderMessage(container, cls, text) {
                const div = document.createElement('div');
                div.className = cls;
                div.textContent = text;
                container.replaceChildren(div);
            }
            function renderReport(container, text) {
                // Report is plain text; render in a <pre> block via textContent.
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
                    const data = await response.text();

                    if (response.ok) {
                        // Store the report content for publishing
                        currentReportContent = data;
                        renderReport(container, data);
                    } else {
                        currentReportContent = null;
                        renderMessage(container, 'error', 'Error: ' + data);
                    }
                } catch (error) {
                    currentReportContent = null;
                    renderMessage(container, 'error', 'Error loading report: ' + error.message);
                } finally {
                    btn.disabled = false;
                    btn.textContent = 'Refresh Report';
                }
            }

            async function publishReport() {
                const btn = document.querySelector('.success-btn');
                const container = document.getElementById('report-container');

                // Check if report is loaded
                if (!currentReportContent) {
                    const msg = showStatus(container, 'error', 'Please load or refresh the report first before publishing.');
                    setTimeout(() => msg.remove(), 5000);
                    return;
                }

                btn.disabled = true;
                btn.textContent = 'Publishing...';

                try {
                    const response = await fetch('/api/reports/publish', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            report_content: currentReportContent
                        })
                    });
                    const result = await response.json();

                    if (response.ok) {
                        const suffix = result.iteration_name ? ' - ' + result.iteration_name : '';
                        showStatus(container, 'success',
                            'Report published successfully for ' + result.org_name + suffix +
                            '. Check the docs folder or GitHub Pages for the published report.');
                    } else {
                        showStatus(container, 'error', 'Error: ' + (result.error || 'Failed to publish report'));
                    }
                } catch (error) {
                    showStatus(container, 'error', 'Error: ' + error.message);
                } finally {
                    btn.disabled = false;
                    btn.textContent = 'Save to GitHub Pages';
                    
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

# Store notes as a simple key-value dict to demonstrate state management
notes: dict[str, str] = {}

# Agent 3: Get iteration information from GitHub Projects (GraphQL API)
# NOTE: This function has been moved to utils/iteration_info.py
# This is kept as a wrapper for backwards compatibility
def get_current_iteration_info_deprecated(github_token: str, org_name: str, project_name: str = "Michigan App Team Task Board") -> dict:
    """
    DEPRECATED: Moved to utils/iteration_info.py
    This wrapper kept for backwards compatibility
    """
    return get_current_iteration_info(github_token, org_name, project_name)


async def handle_list_resources() -> list[types.Resource]:
    """
    List available note resources.
    Each note is exposed as a resource with a custom note:// URI scheme.
    """
    return [
        types.Resource(
            uri=f"note://internal/{name}",
            name=f"Note: {name}",
            description=f"A simple note named {name}",
            mimeType="text/plain",
        )
        for name in notes
    ]

async def handle_read_resource(uri: AnyUrl) -> str:
    """
    Read a specific note's content by its URI.
    The note name is extracted from the URI host component.
    """
    if uri.scheme != "note":
        raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

    name = uri.path
    if name is not None:
        name = name.lstrip("/")
        if name not in notes:
            raise ValueError(f"Note not found: {name}")
        return notes[name]
    raise ValueError(f"Invalid URI: missing note name")

async def handle_list_prompts() -> list[types.Prompt]:
    """
    List available prompts.
    Each prompt can have optional arguments to customize its behavior.
    """
    return [
        types.Prompt(
            name="summarize-notes",
            description="Creates a summary of all notes",
            arguments=[
                types.PromptArgument(
                    name="style",
                    description="Style of the summary (brief/detailed)",
                    required=False,
                )
            ],
        )
    ]

async def handle_get_prompt(
    name: str, arguments: dict[str, str] | None
) -> types.GetPromptResult:
    """
    Generate a prompt by combining arguments with server state.
    The prompt includes all current notes and can be customized via arguments.
    """
    if name != "summarize-notes":
        raise ValueError(f"Unknown prompt: {name}")

    style = (arguments or {}).get("style", "brief")
    detail_prompt = " Give extensive details." if style == "detailed" else ""

    return types.GetPromptResult(
        description="Summarize the current notes",
        messages=[
            types.PromptMessage(
                role="user",
                content=types.TextContent(
                    type="text",
                    text=f"Here are the current notes to summarize:{detail_prompt}\n\n"
                    + "\n".join(
                        f"- {name}: {content}"
                        for name, content in notes.items()
                    ),
                ),
            )
        ],
    )

async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        types.Tool(
            name="add-note",
            description="Add a new note",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["name", "content"],
            },
        ),
    ]

async def handle_call_tool(
    name: str,
    arguments: dict | None,
    ctx: "ServerRequestContext | None" = None,
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool execution requests.
    Tools can modify server state and notify clients of changes.
    """
    # Check for unknown tools first (before checking arguments)
    valid_tools = ["add-note"]
    if name not in valid_tools:
        raise ValueError(f"Unknown tool: {name}")

    if not arguments:
        raise ValueError("Missing arguments")

    if name == "add-note":
        note_name = arguments.get("name")
        content = arguments.get("content")
        if not note_name or not content:
            raise ValueError("Missing name or content")
        notes[note_name] = content
        # Only send notification if we're in an MCP request context
        if ctx is not None:
            try:
                await ctx.session.send_resource_list_changed()
            except (LookupError, AttributeError):
                pass
        return [
            types.TextContent(
                type="text",
                text=f"Added note '{note_name}' with content: {content}",
            )
        ]


# ---------------------------------------------------------------------------
# mcp 2.0 handler adapters — the SDK now takes handlers as constructor kwargs
# with signatures `(ctx, params) -> ResultType`. We keep the original
# `handle_*(name, arguments)` functions above so tests and callers can invoke
# them directly with plain Python values.
# ---------------------------------------------------------------------------

async def _on_list_resources(ctx, params):
    return types.ListResourcesResult(resources=await handle_list_resources())


async def _on_read_resource(ctx, params):
    text = await handle_read_resource(params.uri)
    uri_str = str(params.uri)
    return types.ReadResourceResult(
        contents=[types.TextResourceContents(uri=uri_str, mimeType="text/plain", text=text)]
    )


async def _on_list_prompts(ctx, params):
    return types.ListPromptsResult(prompts=await handle_list_prompts())


async def _on_get_prompt(ctx, params):
    return await handle_get_prompt(params.name, params.arguments)


async def _on_list_tools(ctx, params):
    return types.ListToolsResult(tools=await handle_list_tools())


async def _on_call_tool(ctx, params):
    content = await handle_call_tool(params.name, params.arguments, ctx=ctx)
    return types.CallToolResult(content=content or [])


from mcp.server import ServerRequestContext  # re-exported for the annotation above  # noqa: E402

server = Server(
    "agent-mcp-demo",
    version="0.1.0",
    on_list_resources=_on_list_resources,
    on_read_resource=_on_read_resource,
    on_list_prompts=_on_list_prompts,
    on_get_prompt=_on_get_prompt,
    on_list_tools=_on_list_tools,
    on_call_tool=_on_call_tool,
)

@app.get("/api/github-report", response_class=PlainTextResponse, dependencies=[Depends(require_auth)])
async def github_report_api():
    """
    Fetches all members of a GitHub organization, counts their commits and assigned issues for the current iteration, and returns a report.
    """
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    ORG_NAME = os.environ.get("GITHUB_ORG_NAME")
    PROJECT_NAME = os.environ.get("GITHUB_PROJECT_NAME", "Michigan App Team Task Board")
    PROJECT_NUMBER = int(os.environ.get("GITHUB_PROJECT_NUMBER", "4"))

    if not GITHUB_TOKEN:
        return "GitHub token not set in environment. Please set GITHUB_TOKEN environment variable."
    if not ORG_NAME:
        return "GitHub organization name not set in environment. Please set GITHUB_ORG_NAME environment variable."
    
    # Record start time in local timezone with proper EST/EDT detection
    from datetime import datetime
    import time
    request_start_time = datetime.now().astimezone()
    # Detect if we're in daylight saving time
    tz_name = "EDT" if time.localtime().tm_isdst else "EST"
    print(f"Request received at: {request_start_time.strftime('%Y-%m-%d %I:%M:%S %p')} {tz_name}")

    # Get current iteration information from GitHub Projects
    iteration_info = None
    try:
        iteration_info = get_current_iteration_info(GITHUB_TOKEN, ORG_NAME, PROJECT_NAME, PROJECT_NUMBER)
        print(f"Retrieved iteration info: {iteration_info}")
    except Exception as e:
        print(f"Error getting iteration info: {e}")
    
    try:
        # Test GitHub connection with timeout
        import asyncio
        from datetime import datetime, timezone, timedelta
        auth = Auth.Token(GITHUB_TOKEN)
        g = Github(auth=auth, timeout=5)  # Short timeout for testing
        
        # Test the connection by getting user info. Log the raw
        # exception server-side (with a correlation id) but never
        # return the exception text — GitHub's error messages can
        # include repo/org names, request IDs, and rate-limit hints
        # that we don't want to surface to unauthenticated callers.
        import uuid, logging as _logging
        _log = _logging.getLogger(__name__)
        try:
            current_user = g.get_user()
            current_user_login = current_user.login
            print(f"Connected as: {current_user_login}")
        except Exception as e:
            corr = uuid.uuid4().hex[:12]
            _log.error("GitHub authentication failed (correlation_id=%s): %r", corr, e)
            # Keep the "GitHub authentication failed:" prefix (with the
            # colon) so downstream error-detection heuristics — notably
            # the daily workflow at .github/workflows/generate-iteration-
            # report.yml — keep matching. Same for the other returns
            # below.
            return (
                "GitHub authentication failed: check your GitHub token. "
                f"correlation_id={corr}"
            )

        # Test organization access
        try:
            org = g.get_organization(ORG_NAME)
            print(f"Accessing organization: {org.login}")
        except Exception as e:
            corr = uuid.uuid4().hex[:12]
            _log.error("Error accessing organization (correlation_id=%s): %r", corr, e)
            return (
                f"Error accessing organization '{ORG_NAME}': check the organization "
                f"name and your permissions. correlation_id={corr}"
            )
        
        # Collect members and build email mapping using shared utility
        member_stats, email_to_login, member_logins = collect_members_and_emails(
            g, ORG_NAME, exclude_user_login=current_user_login
        )
        
        # Initialize detail tracking structures using shared utility  
        details = initialize_detail_structures(member_logins)
        commit_details = details['commit_details']
        assigned_issues = details['assigned_issues']
        closed_issues = details['closed_issues']
        pr_created = details['pr_created']
        pr_reviewed = details['pr_reviewed']
        pr_merged = details['pr_merged']
        pr_commented = details['pr_commented']
        
        # Filter by iteration dates if available
        iteration_start = None
        iteration_end = None
        if iteration_info and iteration_info.get('start_date') and iteration_info.get('end_date'):
            try:
                iteration_start = datetime.fromisoformat(iteration_info['start_date'].replace('Z', '+00:00'))
                iteration_end = datetime.fromisoformat(iteration_info['end_date'].replace('Z', '+00:00'))
                print(f"Filtering by iteration: {iteration_start} to {iteration_end}")
            except Exception as e:
                print(f"Error parsing iteration dates: {e}")
        
        # For each repo, count commits and assigned issues for current iteration
        repo_count = 0
        total_commits_processed = 0
        total_issues_processed = 0
        for repo in org.get_repos():
            # Skip archived repositories
            if repo.archived:
                print(f"Skipping archived repository: {repo.name}")
                continue
                
            repo_count += 1
                
            # Collect commit metrics using shared utility
            commits_processed = collect_commit_metrics(
                repo, member_stats, email_to_login, commit_details,
                iteration_info, exclude_user_login=current_user_login
            )
            total_commits_processed += commits_processed
            
            # Collect issue metrics using shared utility
            assigned_count, closed_count = collect_issue_metrics(
                repo, member_stats, assigned_issues, closed_issues,
                iteration_info
            )
            total_issues_processed += (assigned_count + closed_count)
            
            # Process pull requests using shared utility
            try:
                repo_pr_created, repo_pr_reviewed, repo_pr_merged, repo_pr_commented = collect_pr_metrics(
                    repo, member_stats, iteration_info, current_user_login=current_user_login
                )
                
                # Merge PR metrics for this repo into overall metrics
                for login, prs in repo_pr_created.items():
                    if login not in pr_created:
                        pr_created[login] = []
                    pr_created[login].extend(prs)
                for login, prs in repo_pr_reviewed.items():
                    if login not in pr_reviewed:
                        pr_reviewed[login] = []
                    pr_reviewed[login].extend(prs)
                for login, prs in repo_pr_merged.items():
                    if login not in pr_merged:
                        pr_merged[login] = []
                    pr_merged[login].extend(prs)
                for login, prs in repo_pr_commented.items():
                    if login not in pr_commented:
                        pr_commented[login] = []
                    pr_commented[login].extend(prs)
            except Exception as e:
                print(f"Error collecting PR metrics for {repo.name}: {e}")
        
        # Build report with iteration information
        report = [
            f"GitHub Organization: {ORG_NAME}",
            f"Report started on: {request_start_time.strftime('%Y-%m-%d %I:%M:%S %p')} {tz_name}\n"
        ]
        
        # Add iteration information at the beginning
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
            report.append("")  # Empty line for spacing
        else:
            report.append("Note: No iteration information available. Showing all-time data.")
            report.append("")  # Empty line for spacing
        
        report.append(f"Processed {repo_count} repositories")
        report.append(f"Total commits processed: {total_commits_processed}")
        report.append(f"Total issues processed: {total_issues_processed}")
        if iteration_start and iteration_end:
            report.append(f"Filtered by iteration: {iteration_start.strftime('%Y-%m-%d')} to {iteration_end.strftime('%Y-%m-%d')}")
        
        # Summary section with proper markdown table
        report.append("\n# SUMMARY\n")
        report.append("| User | Commits | Assigned Issues | Closed Issues | PRs Created | PRs Reviewed | PRs Merged | PRs Commented |")
        report.append("|------|---------|----------------|---------------|-------------|--------------|------------|---------------|")
        for login, stats in member_stats.items():
            report.append(f"| {login} | {stats['commits']} | {stats['assigned_issues']} | {stats['closed_issues']} | {stats.get('pr_created', 0)} | {stats.get('pr_reviewed', 0)} | {stats.get('pr_merged', 0)} | {stats.get('pr_commented', 0)} |")
        
        # Detailed section for each member
        report.append("\n# DETAILED ACTIVITY\n")
        
        for login, stats in member_stats.items():
            if stats['commits'] > 0 or stats['assigned_issues'] > 0 or stats['closed_issues'] > 0 or stats.get('pr_created', 0) > 0 or stats.get('pr_reviewed', 0) > 0 or stats.get('pr_merged', 0) > 0 or stats.get('pr_commented', 0) > 0:
                report.append(f"\n## User: {login}\n")
                
                # List commits
                if stats['commits'] > 0:
                    report.append("**Commits:**\n")
                    for commit_info in commit_details.get(login, []):
                        report.append(f"- [{commit_info['repo']}] {commit_info['message']} ({commit_info['date'].strftime('%Y-%m-%d')})")
                    report.append("")  # Empty line
                
                # List assigned issues
                if stats['assigned_issues'] > 0:
                    report.append("**Assigned Issues:**\n")
                    for issue_info in assigned_issues.get(login, []):
                        status = "Open" if issue_info['state'] == "open" else "Closed"
                        report.append(f"- [{issue_info['repo']}] #{issue_info['number']} {issue_info['title']} ({status})")
                    report.append("")  # Empty line
                
                # List closed issues
                if stats['closed_issues'] > 0:
                    report.append("**Closed Issues:**\n")
                    for issue_info in closed_issues.get(login, []):
                        report.append(f"- [{issue_info['repo']}] #{issue_info['number']} {issue_info['title']} (Closed on {issue_info['closed_date'].strftime('%Y-%m-%d')})")
                    report.append("")  # Empty line
                
                # List PRs created
                if stats.get('pr_created', 0) > 0:
                    report.append("**Pull Requests Created:**\n")
                    for pr_info in pr_created.get(login, []):
                        status = "Merged" if pr_info.get('merged_at') else ("Closed" if pr_info['state'] == "closed" else "Open")
                        report.append(f"- [{pr_info['repo']}] #{pr_info['number']} {pr_info['title']} ({status})")
                    report.append("")  # Empty line
                
                # List PRs reviewed
                if stats.get('pr_reviewed', 0) > 0:
                    report.append("**Pull Requests Reviewed:**\n")
                    for pr_info in pr_reviewed.get(login, []):
                        status = "Merged" if pr_info.get('merged_at') else ("Closed" if pr_info['state'] == "closed" else "Open")
                        report.append(f"- [{pr_info['repo']}] #{pr_info['number']} {pr_info['title']} ({status})")
                    report.append("")  # Empty line
                
                # List PRs merged
                if stats.get('pr_merged', 0) > 0:
                    report.append("**Pull Requests Merged:**\n")
                    for pr_info in pr_merged.get(login, []):
                        merged_date = pr_info.get('merged_at').strftime('%Y-%m-%d') if pr_info.get('merged_at') else 'N/A'
                        report.append(f"- [{pr_info['repo']}] #{pr_info['number']} {pr_info['title']} (Merged on {merged_date})")
                    report.append("")  # Empty line
                
                # List PRs commented
                if stats.get('pr_commented', 0) > 0:
                    report.append("**Pull Requests Commented:**\n")
                    for pr_info in pr_commented.get(login, []):
                        status = "Merged" if pr_info.get('merged_at') else ("Closed" if pr_info['state'] == "closed" else "Open")
                        report.append(f"- [{pr_info['repo']}] #{pr_info['number']} {pr_info['title']} ({status})")
                    report.append("")  # Empty line
        
        # Add report completion time
        report_end_time = datetime.now().astimezone()
        report.append("=" * 60)
        report.append(f"Report completed on: {report_end_time.strftime('%Y-%m-%d %I:%M:%S %p')} {tz_name}")
        report.append(f"Generation time: {(report_end_time - request_start_time).total_seconds():.2f} seconds")
        
        return "\n".join(report)

    except Exception as e:
        import uuid, logging as _logging
        corr = uuid.uuid4().hex[:12]
        _logging.getLogger(__name__).exception(
            "Unexpected error building report (correlation_id=%s)", corr,
        )
        # Keep the "Unexpected error:" prefix (with the colon) so the
        # daily workflow's `startswith("Unexpected error:")` heuristic
        # keeps catching this — see
        # .github/workflows/generate-iteration-report.yml.
        return (
            "Unexpected error: failed to build report. Please check your GitHub "
            f"token and organization access. correlation_id={corr}"
        )

@app.get("/github-report", response_class=PlainTextResponse)
async def github_report():
    """
    Legacy endpoint that redirects to the new web interface.
    """
    return "GitHub Report Server is running! Visit / for the web interface or /api/github-report for the raw report."

MAX_PUBLISH_BODY_BYTES = int(os.environ.get("MAX_PUBLISH_BODY_BYTES", 2 * 1024 * 1024))  # 2 MiB default
MAX_REPORT_CONTENT_BYTES = int(os.environ.get("MAX_REPORT_CONTENT_BYTES", 1 * 1024 * 1024))  # 1 MiB default


@app.post(
    "/api/reports/publish",
    response_class=JSONResponse,
    dependencies=[Depends(require_auth)],
)
async def publish_report_endpoint(
    background_tasks: BackgroundTasks,
    request: Request,
    force: bool = False
):
    """
    Publish the current report to GitHub Pages.
    The report content should be provided in the request body.

    Args:
        force: If True, skip duplicate checking and force publish
    """
    try:
        # Guard against oversized bodies BEFORE parsing JSON.
        # Fast path — reject on an honestly declared oversized Content-Length.
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except (TypeError, ValueError):
                return JSONResponse({"error": "Invalid Content-Length"}, status_code=400)
            if declared > MAX_PUBLISH_BODY_BYTES:
                return JSONResponse(
                    {"error": f"Request body exceeds {MAX_PUBLISH_BODY_BYTES}-byte limit"},
                    status_code=413,
                )

        # Stream the body and abort as soon as the cumulative size
        # exceeds the cap. This bounds memory use to
        # MAX_PUBLISH_BODY_BYTES + one chunk, regardless of what the
        # sender declares (or omits) in Content-Length. Chunked / no-
        # length requests that would previously buffer without limit
        # are now cut off mid-stream.
        chunks = []
        total = 0
        async for chunk in request.stream():
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_PUBLISH_BODY_BYTES:
                return JSONResponse(
                    {"error": f"Request body exceeds {MAX_PUBLISH_BODY_BYTES}-byte limit"},
                    status_code=413,
                )
            chunks.append(chunk)
        raw = b"".join(chunks)
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

        report_text = body.get('report_content') if isinstance(body, dict) else None

        if not report_text:
            return JSONResponse({"error": "No report content provided"}, status_code=400)
        if not isinstance(report_text, str):
            return JSONResponse({"error": "report_content must be a string"}, status_code=400)
        if len(report_text.encode("utf-8")) > MAX_REPORT_CONTENT_BYTES:
            return JSONResponse(
                {"error": f"report_content exceeds {MAX_REPORT_CONTENT_BYTES}-byte limit"},
                status_code=413,
            )
        
        # Check if the report is an error message (starts with error indicators)
        if isinstance(report_text, str) and (
            report_text.startswith("GitHub token not set") or 
            report_text.startswith("GitHub organization name not set") or
            report_text.startswith("Unexpected error:")
        ):
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
        except Exception as e:
            print(f"Error parsing iteration info: {e}")
            # Don't fail if iteration info parsing fails
        
        async def publish_in_background():
            try:
                print("Starting background publish task...")
                print(f"Publishing report for org: {org_name}")
                print(f"Iteration info: {iteration_info}")
                
                result = await publisher.publish_report(
                    report_content=report_text,
                    org_name=org_name,
                    iteration_name=iteration_info.get("name"),
                    start_date=iteration_info.get("start_date"),
                    end_date=iteration_info.get("end_date"),
                    skip_duplicate_check=force
                )
                print(f"Publish result: {result}")
                
                # Auto-commit and push if successfully published
                if result.get("status") == "published":
                    commit_msg = f"Publish report for {iteration_info.get('name', 'iteration')}\n\n- Organization: {org_name}\n- Manually triggered publish"
                    git_result = git_ops.commit_and_push(
                        file_paths=["docs/", "reports/"],
                        commit_message=commit_msg
                    )
                    print(f"Git operation: {git_result}")
                    result["git_result"] = git_result
                
                return result
            except Exception as e:
                print(f"Error in background publish task: {e}")
                import traceback
                traceback.print_exc()
                raise
            
        # Run the task in background
        background_tasks.add_task(publish_in_background)
        
        return JSONResponse({
            "message": "Report publishing started. Will auto-commit and push when complete.",
            "org_name": org_name,
            "iteration_name": iteration_info.get("name", "N/A")
        })
        
    except ValueError as e:
        # Input-shape errors are safe to surface (they describe the bad
        # input, not internal state).
        return JSONResponse({"error": str(e)}, status_code=500)
    except Exception as e:
        # Debug traceback responses were removed: even a misconfigured
        # DEBUG=1 flag in production must not leak internal state to
        # unauthenticated callers. The full traceback still lands in
        # server logs, keyed by correlation_id.
        import logging, uuid
        correlation_id = uuid.uuid4().hex[:12]
        logging.getLogger(__name__).exception(
            "publish_report failed (correlation_id=%s)", correlation_id,
        )
        return JSONResponse(
            {"error": "Failed to publish report", "correlation_id": correlation_id},
            status_code=500,
        )

async def main():
    # Run the server using stdin/stdout streams
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="agent-mcp-demo",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )