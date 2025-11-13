

import asyncio
import json
import httpx
import requests
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import PlainTextResponse, HTMLResponse, JSONResponse
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio
import os
from github import Github
from dotenv import load_dotenv
from pathlib import Path
import sys
# Removed Azure DevOps imports - now using GitHub Projects

# Load environment variables from .env file at startup
load_dotenv()

# Add the src directory to the path so we can import from agent_mcp_demo
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from agent_mcp_demo.utils.report_publisher import ReportPublisher
from agent_mcp_demo.utils.git_operations import GitOperations
from agent_mcp_demo.utils.report_scheduler import ReportScheduler

# Initialize the report publisher and git operations
publisher = ReportPublisher()
git_ops = GitOperations()

# Add FastAPI app for HTTP endpoints
app = FastAPI()

# Initialize scheduler (will be started in lifespan event)
scheduler = None

@app.on_event("startup")
async def startup_event():
    """Initialize and start the report scheduler on app startup."""
    global scheduler
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Create scheduler with callbacks
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

@app.on_event("shutdown")
async def shutdown_event():
    """Stop the scheduler on app shutdown."""
    global scheduler
    if scheduler:
        scheduler.stop()

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
            async function loadReport() {
                const btn = document.querySelector('.primary-btn');
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
                            'Report published successfully for ' + result.org_name + 
                            (result.iteration_name ? ' - ' + result.iteration_name : '') +
                            '<br>Check the docs folder or GitHub Pages for the published report.' +
                            '</div>'
                        );
                    } else {
                        container.insertAdjacentHTML('beforebegin',
                            '<div class="status-message error">Error: ' + 
                            (result.error || 'Failed to publish report') + 
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

# Agent 1: Fetch data from an API
async def fetch_from_api(url: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

# Agent 2: Read data from a JSON file
def read_from_json_file(filepath: str) -> dict:
    with open(filepath, 'r') as f:
        return json.load(f)

# Agent 3: Get iteration information from GitHub Projects (GraphQL API)
def get_current_iteration_info(github_token: str, org_name: str, project_name: str = "Michigan App Team Task Board") -> dict:
    """
    Get current iteration information from GitHub Projects using GraphQL API
    """
    try:
        import requests
        import json
        
        headers = {
            'Authorization': f'Bearer {github_token}',
            'Content-Type': 'application/json',
        }
        
        # GraphQL query to get organization projects
        query = """
        query($orgName: String!) {
          organization(login: $orgName) {
            projectsV2(first: 20) {
              nodes {
                id
                title
                number
                url
              }
            }
          }
        }
        """
        
        variables = {
            "orgName": org_name
        }
        
        response = requests.post(
            'https://api.github.com/graphql',
            headers=headers,
            json={'query': query, 'variables': variables}
        )
        
        if response.status_code != 200:
            print(f"Error getting projects via GraphQL: {response.status_code} - {response.text}")
            return None
        
        data = response.json()
        
        if 'errors' in data:
            print(f"GraphQL errors: {data['errors']}")
            return None
        
        projects = data['data']['organization']['projectsV2']['nodes']
        print(f"Found {len(projects)} projects in organization")
        
        # Find the specific project
        target_project = None
        for project in projects:
            if project.get('title') == project_name:
                target_project = project
                break
        
        if not target_project:
            print(f"Project '{project_name}' not found in organization '{org_name}'")
            print(f"Available projects: {[p.get('title') for p in projects]}")
            # Fall through to environment variable fallback
        else:
            print(f"Found project: {target_project.get('title')} (ID: {target_project.get('id')})")
            
            # Try to get project fields using GraphQL
            fields_query = """
            query($projectId: ID!) {
              node(id: $projectId) {
                ... on ProjectV2 {
                  fields(first: 50) {
                    nodes {
                      ... on ProjectV2Field {
                        id
                        name
                        dataType
                      }
                      ... on ProjectV2IterationField {
                        id
                        name
                        configuration {
                          iterations {
                            id
                            title
                            startDate
                            duration
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
            """
            
            fields_variables = {
                "projectId": target_project.get('id')
            }
            
            fields_response = requests.post(
                'https://api.github.com/graphql',
                headers=headers,
                json={'query': fields_query, 'variables': fields_variables}
            )
            
            print(f"Fields response status: {fields_response.status_code}")
            if fields_response.status_code == 200:
                fields_data = fields_response.json()
                print(f"Fields response: {json.dumps(fields_data, indent=2)}")
                
                if 'data' in fields_data and fields_data['data']['node']:
                    fields = fields_data['data']['node']['fields']['nodes']
                    print(f"Found {len(fields)} project fields")
                    
                    # Look for iteration fields
                    for field in fields:
                        print(f"Field type: {field.get('__typename')}, name: {field.get('name')}")
                        
                        # Check if this is an iteration field by name or type
                        if (field.get('__typename') == 'ProjectV2IterationField' or 
                            field.get('name', '').lower() == 'iteration'):
                            print(f"Found iteration field: {json.dumps(field, indent=2)}")
                            
                            # Check if this field has configuration with iterations
                            if 'configuration' in field and 'iterations' in field['configuration']:
                                iterations = field['configuration']['iterations']
                                print(f"Found {len(iterations)} iterations")
                                if iterations:
                                    # Find the current iteration based on today's date
                                    from datetime import datetime, timedelta
                                    today = datetime.now().date()
                                    current_iteration = None
                                    
                                    for iteration in iterations:
                                        start_date = iteration.get('startDate')
                                        duration = iteration.get('duration')
                                        
                                        if start_date and duration:
                                            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00')).date()
                                            end_dt = start_dt + timedelta(days=duration)
                                            
                                            # Check if today falls within this iteration
                                            if start_dt <= today <= end_dt:
                                                current_iteration = iteration
                                                print(f"Found current iteration: {iteration.get('title')} ({start_date} to {end_dt})")
                                                break
                                    
                                    # If no current iteration found, use the most recent past iteration
                                    if not current_iteration:
                                        for iteration in reversed(iterations):
                                            start_date = iteration.get('startDate')
                                            duration = iteration.get('duration')
                                            
                                            if start_date and duration:
                                                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00')).date()
                                                end_dt = start_dt + timedelta(days=duration)
                                                
                                                # Use the most recent iteration that has ended
                                                if end_dt < today:
                                                    current_iteration = iteration
                                                    print(f"Using most recent past iteration: {iteration.get('title')} ({start_date} to {end_dt})")
                                                    break
                                    
                                    # If still no iteration found, use the first one (fallback)
                                    if not current_iteration and iterations:
                                        current_iteration = iterations[0]
                                        print(f"Using fallback iteration: {current_iteration.get('title')}")
                                    
                                    if current_iteration:
                                        # Calculate end date from start date and duration
                                        start_date = current_iteration.get('startDate')
                                        duration = current_iteration.get('duration')
                                        
                                        if start_date and duration:
                                            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                                            end_dt = start_dt + timedelta(days=duration)
                                            end_date = end_dt.isoformat()
                                        else:
                                            end_date = None
                                        
                                        return {
                                            'name': current_iteration.get('title', 'Current Sprint'),
                                            'start_date': start_date,
                                            'end_date': end_date,
                                            'path': f"{org_name}/{project_name}"
                                        }
                            
                            # If we found an iteration field but couldn't get configuration, 
                            # try to get the field ID and query it separately
                            field_id = field.get('id')
                            if field_id:
                                print(f"Trying to get iteration data for field ID: {field_id}")
                                
                                # Try to get iteration data from the field response
                                if 'data' in fields_data and 'node' in fields_data['data']:
                                    node_data = fields_data['data']['node']
                                    if 'fields' in node_data and 'nodes' in node_data['fields']:
                                        for field_node in node_data['fields']['nodes']:
                                            if field_node.get('__typename') == 'ProjectV2IterationField':
                                                if 'configuration' in field_node and 'iterations' in field_node['configuration']:
                                                    iterations = field_node['configuration']['iterations']
                                                    if iterations:
                                                        # Find the current iteration based on today's date
                                                        from datetime import datetime, timedelta
                                                        today = datetime.now().date()
                                                        current_iteration = None
                                                        
                                                        for iteration in iterations:
                                                            start_date = iteration.get('startDate')
                                                            duration = iteration.get('duration')
                                                            
                                                            if start_date and duration:
                                                                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00')).date()
                                                                end_dt = start_dt + timedelta(days=duration)
                                                                
                                                                # Check if today falls within this iteration
                                                                if start_dt <= today <= end_dt:
                                                                    current_iteration = iteration
                                                                    print(f"Found current iteration: {iteration.get('title')} ({start_date} to {end_dt})")
                                                                    break
                                                        
                                                        # If no current iteration found, use the most recent past iteration
                                                        if not current_iteration:
                                                            for iteration in reversed(iterations):
                                                                start_date = iteration.get('startDate')
                                                                duration = iteration.get('duration')
                                                                
                                                                if start_date and duration:
                                                                    start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00')).date()
                                                                    end_dt = start_dt + timedelta(days=duration)
                                                                    
                                                                    # Use the most recent iteration that has ended
                                                                    if end_dt < today:
                                                                        current_iteration = iteration
                                                                        print(f"Using most recent past iteration: {iteration.get('title')} ({start_date} to {end_dt})")
                                                                        break
                                                        
                                                        # If still no iteration found, use the first one (fallback)
                                                        if not current_iteration and iterations:
                                                            current_iteration = iterations[0]
                                                            print(f"Using fallback iteration: {current_iteration.get('title')}")
                                                        
                                                        if current_iteration:
                                                            # Calculate end date from start date and duration
                                                            start_date = current_iteration.get('startDate')
                                                            duration = current_iteration.get('duration')
                                                        
                                                        if start_date and duration:
                                                            from datetime import datetime, timedelta
                                                            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                                                            end_dt = start_dt + timedelta(days=duration)
                                                            end_date = end_dt.isoformat()
                                                        else:
                                                            end_date = None
                                                        
                                                        return {
                                                            'name': current_iteration.get('title', 'Current Sprint'),
                                                            'start_date': start_date,
                                                            'end_date': end_date,
                                                            'path': f"{org_name}/{project_name}"
                                                        }
                                
                                print("Iteration field found but configuration not accessible, falling back to environment variables")
                else:
                    print(f"No project data found in response")
            else:
                print(f"Fields request failed: {fields_response.status_code} - {fields_response.text}")
        
        # Fall back to environment variables
        iteration_start = os.environ.get("GITHUB_ITERATION_START")
        iteration_end = os.environ.get("GITHUB_ITERATION_END")
        iteration_name = os.environ.get("GITHUB_ITERATION_NAME", "Current Sprint")
        
        if iteration_start and iteration_end:
            return {
                'name': iteration_name,
                'start_date': iteration_start,
                'end_date': iteration_end,
                'path': f"{org_name}/{project_name}"
            }
        else:
            print("No iteration dates found in environment variables")
            return None
            
    except Exception as e:
        print(f"Error getting iteration info from GitHub Projects: {e}")
        return None


server = Server("agent-mcp-demo")

@server.list_resources()
async def handle_list_resources() -> list[types.Resource]:
    """
    List available note resources.
    Each note is exposed as a resource with a custom note:// URI scheme.
    """
    return [
        types.Resource(
            uri=AnyUrl(f"note://internal/{name}"),
            name=f"Note: {name}",
            description=f"A simple note named {name}",
            mimeType="text/plain",
        )
        for name in notes
    ]

@server.read_resource()
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

@server.list_prompts()
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

@server.get_prompt()
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

@server.list_tools()
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
        types.Tool(
            name="fetch-api-data",
            description="Fetch data from a public API (Agent 1)",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "format": "uri"}
                },
                "required": ["url"],
            },
        ),
        types.Tool(
            name="read-json-file",
            description="Read data from a JSON file (Agent 2)",
            inputSchema={
                "type": "object",
                "properties": {
                    "filepath": {"type": "string"}
                },
                "required": ["filepath"],
            },
        ),
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """
    Handle tool execution requests.
    Tools can modify server state and notify clients of changes.
    """
    # Check for unknown tools first (before checking arguments)
    valid_tools = ["add-note", "fetch-api-data", "read-json-file"]
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
        try:
            await server.request_context.session.send_resource_list_changed()
        except (LookupError, AttributeError):
            # Not in an MCP request context (e.g., during testing)
            pass
        return [
            types.TextContent(
                type="text",
                text=f"Added note '{note_name}' with content: {content}",
            )
        ]
    elif name == "fetch-api-data":
        url = arguments.get("url")
        if not url:
            raise ValueError("Missing url")
        data = await fetch_from_api(url)
        return [
            types.TextContent(
                type="text",
                text=f"Fetched data from API {url}: {json.dumps(data)[:500]}",
            )
        ]
    elif name == "read-json-file":
        filepath = arguments.get("filepath")
        if not filepath:
            raise ValueError("Missing filepath")
        data = read_from_json_file(filepath)
        return [
            types.TextContent(
                type="text",
                text=f"Read data from file {filepath}: {json.dumps(data)[:500]}",
            )
        ]

@app.get("/api/github-report", response_class=PlainTextResponse)
async def github_report_api():
    """
    Fetches all members of a GitHub organization, counts their commits and assigned issues for the current iteration, and returns a report.
    """
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    ORG_NAME = os.environ.get("GITHUB_ORG_NAME")
    
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
        iteration_info = get_current_iteration_info(GITHUB_TOKEN, ORG_NAME, "Michigan App Team Task Board")
        print(f"Retrieved iteration info: {iteration_info}")
    except Exception as e:
        print(f"Error getting iteration info: {e}")
    
    try:
        # Test GitHub connection with timeout
        import asyncio
        from datetime import datetime, timezone, timedelta
        g = Github(GITHUB_TOKEN, timeout=5)  # Short timeout for testing
        
        # Test the connection by getting user info
        try:
            current_user = g.get_user()
            current_user_login = current_user.login
            print(f"Connected as: {current_user_login}")
        except Exception as e:
            return f"GitHub authentication failed: {str(e)}\n\nPlease check your GitHub token."
        
        # Test organization access
        try:
            org = g.get_organization(ORG_NAME)
            print(f"Accessing organization: {org.login}")
        except Exception as e:
            return f"Error accessing organization '{ORG_NAME}': {str(e)}\n\nPlease check your organization name and permissions."
        
        # Get members with timeout
        try:
            members = list(org.get_members())
            print(f"Found {len(members)} members")
        except Exception as e:
            return f"Error getting organization members: {str(e)}"
        
        # Build member stats and email mapping (excluding current user)
        member_stats = {}
        email_to_login = {}
        commit_details = {}
        assigned_issues = {}
        closed_issues = {}
        
        for member in members:
            # Skip the current user
            if member.login == current_user_login:
                print(f"Skipping current user: {member.login}")
                continue
                
            member_stats[member.login] = {"commits": 0, "assigned_issues": 0, "closed_issues": 0}
            commit_details[member.login] = []
            assigned_issues[member.login] = []
            closed_issues[member.login] = []
            try:
                # Get user details including email
                user = g.get_user(member.login)
                if user.email:  # Primary email
                    email_to_login[user.email.lower()] = member.login
                # Get all emails if we have permission
                try:
                    emails = user.get_emails()
                    for email in emails:
                        if email.verified:  # Only use verified emails
                            email_to_login[email.email.lower()] = member.login
                except:
                    pass  # Skip if we don't have permission to see emails
            except Exception as e:
                print(f"Error getting emails for {member.login}: {e}")
        
        print(f"Found {len(email_to_login)} email mappings for {len(member_stats)} members")
        
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
            # Removed artificial limit to process all repositories
                
            # Commits per user from all branches (filtered by iteration if available)
            try:
                # Get all branches for this repository
                branches = repo.get_branches()
                processed_commits = set()  # Track unique commits across branches
                
                for branch in branches:
                    try:
                        print(f"Processing branch {branch.name} in {repo.name}")
                        # Use since parameter to limit to relevant commits if iteration dates are set
                        since = iteration_start if iteration_start else None
                        until = iteration_end if iteration_end else None
                        
                        for commit in repo.get_commits(sha=branch.name, since=since, until=until):
                            # Skip if we've already processed this commit from another branch
                            if commit.sha in processed_commits:
                                continue
                            processed_commits.add(commit.sha)
                            total_commits_processed += 1
                            
                            # Filter by iteration dates if available
                            if iteration_start and iteration_end:
                                try:
                                    commit_date = commit.commit.author.date
                                    # Make sure both dates are timezone-aware for comparison
                                    if commit_date.tzinfo is None:
                                        # If commit_date is naive, assume UTC
                                        from datetime import timezone
                                        commit_date = commit_date.replace(tzinfo=timezone.utc)
                                    
                                    # Ensure iteration dates are also timezone-aware
                                    if iteration_start.tzinfo is None:
                                        iteration_start = iteration_start.replace(tzinfo=timezone.utc)
                                    if iteration_end.tzinfo is None:
                                        iteration_end = iteration_end.replace(tzinfo=timezone.utc)
                                    
                                    if not (iteration_start <= commit_date <= iteration_end):
                                        continue
                                    else:
                                        print(f"Found commit in iteration: {commit.commit.message[:50]}... by {commit.author.login if commit.author else 'Unknown'} on branch {branch.name}")
                                except AttributeError:
                                    # Skip commits with invalid author data
                                    continue
                            
                            # Try to match the commit to a member
                            matched = False
                            commit_info = {
                                'repo': repo.name,
                                'message': commit.commit.message.split('\n')[0],  # First line of commit message
                                'date': commit.commit.author.date,
                                'sha': commit.sha[:7],
                                'branch': branch.name
                            }
                            
                            # First try GitHub API author if available
                            if commit.author and hasattr(commit.author, 'login'):
                                login = commit.author.login
                                # Skip if it's the current user
                                if login == current_user_login:
                                    continue
                                if login in member_stats:
                                    member_stats[login]["commits"] += 1
                                    commit_details[login].append(commit_info)
                                    matched = True
                                    print(f"Matched commit {commit.sha[:7]} on {branch.name} to {login} via GitHub API")
                                    continue  # Move to next commit since we found a match
                            
                            # Try email mapping
                            if hasattr(commit.commit.author, 'email') and commit.commit.author.email:
                                author_email = commit.commit.author.email.lower()
                                if author_email in email_to_login:
                                    member_login = email_to_login[author_email]
                                    # Skip if it's the current user
                                    if member_login == current_user_login:
                                        continue
                                    member_stats[member_login]["commits"] += 1
                                    commit_details[member_login].append(commit_info)
                                    matched = True
                                    print(f"Matched commit {commit.sha[:7]} on {branch.name} to {member_login} via email {author_email}")
                                    continue  # Move to next commit since we found a match
                                
                                # Try to match by username in email
                                email_username = author_email.split('@')[0]
                                for member_login in member_stats.keys():
                                    if member_login.lower() in email_username.lower() or email_username.lower() in member_login.lower():
                                        member_stats[member_login]["commits"] += 1
                                        commit_details[member_login].append(commit_info)
                                        matched = True
                                        print(f"Matched commit {commit.sha[:7]} on {branch.name} to {member_login} via username in email {author_email}")
                                        break
                                
                                if matched:
                                    continue  # Move to next commit since we found a match
                            
                            # If still not matched, log it for debugging
                            author_name = commit.commit.author.name if commit.commit.author else "Unknown"
                            author_email = commit.commit.author.email if commit.commit.author else "Unknown"
                            print(f"Unmatched commit {commit.sha[:7]} on {branch.name} by {author_name} <{author_email}>")
                            
                    except Exception as e:
                        print(f"Error getting commits for branch {branch.name} in {repo.name}: {e}")
                        continue
            except Exception as e:
                print(f"Error getting branches for {repo.name}: {e}")
                continue
                
            # Assigned and closed issues per user (filtered by assignment/closed dates)
            try:
                issue_count = 0
                # Get both open and closed issues
                for issue in repo.get_issues(state="all"):
                    issue_count += 1
                    total_issues_processed += 1
                    if issue_count > 500:  # Increased limit to 500 issues per repo
                        break
                    
                    # Track assignees for both open and closed issues
                    for assignee in issue.assignees:
                        # Skip if it's the current user
                        if assignee.login == current_user_login:
                            continue
                        if assignee.login in member_stats:
                            # Track both open and closed issues for each user
                            from datetime import timezone
                            
                            # Get assignment date
                            assignment_date = getattr(issue, 'assigned_at', None) or issue.created_at
                            if assignment_date.tzinfo is None:
                                assignment_date = assignment_date.replace(tzinfo=timezone.utc)
                            
                            # Get closed date if applicable
                            closed_date = None
                            if issue.state == "closed" and issue.closed_at:
                                closed_date = issue.closed_at
                                if closed_date.tzinfo is None:
                                    closed_date = closed_date.replace(tzinfo=timezone.utc)
                            
                            # Make iteration dates timezone-aware if needed
                            if iteration_start and iteration_end:
                                if iteration_start.tzinfo is None:
                                    iteration_start = iteration_start.replace(tzinfo=timezone.utc)
                                if iteration_end.tzinfo is None:
                                    iteration_end = iteration_end.replace(tzinfo=timezone.utc)
                                
                                # Check if issue was assigned during iteration
                                if iteration_start <= assignment_date <= iteration_end:
                                    member_stats[assignee.login]["assigned_issues"] += 1
                                    assigned_issues[assignee.login].append({
                                        'repo': repo.name,
                                        'number': issue.number,
                                        'title': issue.title,
                                        'state': issue.state,
                                        'assigned_date': assignment_date
                                    })
                                    print(f"Found assigned issue in iteration: {issue.title[:50]}... assigned to {assignee.login}")
                                
                                # Check if issue was closed during iteration
                                if closed_date and iteration_start <= closed_date <= iteration_end:
                                    member_stats[assignee.login]["closed_issues"] += 1
                                    closed_issues[assignee.login].append({
                                        'repo': repo.name,
                                        'number': issue.number,
                                        'title': issue.title,
                                        'closed_date': closed_date
                                    })
                                    print(f"Found closed issue in iteration: {issue.title[:50]}... closed by {assignee.login}")
                            else:
                                # If no iteration filter, count all issues
                                member_stats[assignee.login]["assigned_issues"] += 1
                                assigned_issues[assignee.login].append({
                                    'repo': repo.name,
                                    'number': issue.number,
                                    'title': issue.title,
                                    'state': issue.state,
                                    'assigned_date': assignment_date
                                })
                                
                                if closed_date:
                                    member_stats[assignee.login]["closed_issues"] += 1
                                    closed_issues[assignee.login].append({
                                        'repo': repo.name,
                                        'number': issue.number,
                                        'title': issue.title,
                                        'closed_date': closed_date
                                    })
                                    member_stats[assignee.login]["closed_issues"] += 1
            except Exception as e:
                print(f"Error getting issues for {repo.name}: {e}")
                continue
        
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
        report.append("| User | Commits | Assigned Issues | Closed Issues |")
        report.append("|------|---------|----------------|---------------|")
        for login, stats in member_stats.items():
            report.append(f"| {login} | {stats['commits']} | {stats['assigned_issues']} | {stats['closed_issues']} |")
        
        # Detailed section for each member
        report.append("\n# DETAILED ACTIVITY\n")
        
        for login, stats in member_stats.items():
            if stats['commits'] > 0 or stats['assigned_issues'] > 0 or stats['closed_issues'] > 0:
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
        
        # Add report completion time
        report_end_time = datetime.now().astimezone()
        report.append("=" * 60)
        report.append(f"Report completed on: {report_end_time.strftime('%Y-%m-%d %I:%M:%S %p')} {tz_name}")
        report.append(f"Generation time: {(report_end_time - request_start_time).total_seconds():.2f} seconds")
        
        return "\n".join(report)
        
    except Exception as e:
        return f"Unexpected error: {str(e)}\n\nPlease check your GitHub token and organization access."

@app.get("/github-report", response_class=PlainTextResponse)
async def github_report():
    """
    Legacy endpoint that redirects to the new web interface.
    """
    return "GitHub Report Server is running! Visit / for the web interface or /api/github-report for the raw report."

@app.post("/api/reports/publish", response_class=JSONResponse)
async def publish_report_endpoint(background_tasks: BackgroundTasks, force: bool = False):
    """
    Publish the current report to GitHub Pages.
    The report will be generated and published asynchronously.
    
    Args:
        force: If True, skip duplicate checking and force publish
    """
    try:
        report_text = await github_report_api()
        
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