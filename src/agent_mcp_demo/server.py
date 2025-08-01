

import asyncio
import json
import httpx
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, HTMLResponse
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio
import os
from github import Github
from dotenv import load_dotenv
# Removed Azure DevOps imports - now using GitHub Projects

# Load environment variables from .env file at startup
load_dotenv()

# Add FastAPI app for HTTP endpoints
app = FastAPI()

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
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>GitHub Organization Report</h1>
                <button class="refresh-btn" onclick="loadReport()">Refresh Report</button>
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
            return None
        
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
        return notes[name]
    raise ValueError(f"Note not found: {name}")

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
    if not arguments:
        raise ValueError("Missing arguments")

    if name == "add-note":
        note_name = arguments.get("name")
        content = arguments.get("content")
        if not note_name or not content:
            raise ValueError("Missing name or content")
        notes[note_name] = content
        await server.request_context.session.send_resource_list_changed()
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
    else:
        raise ValueError(f"Unknown tool: {name}")

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
        from datetime import datetime, timezone
        g = Github(GITHUB_TOKEN, timeout=5)  # Short timeout for testing
        
        # Test the connection by getting user info
        try:
            user = g.get_user()
            print(f"Connected as: {user.login}")
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
        
        member_stats = {m.login: {"commits": 0, "assigned_issues": 0, "closed_issues": 0} for m in members}
        
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
            repo_count += 1
            # Removed artificial limit to process all repositories
                
            # Commits per user from all branches (filtered by iteration if available)
            try:
                commit_count = 0
                # Get all branches for this repository
                branches = repo.get_branches()
                for branch in branches:
                    try:
                        for commit in repo.get_commits(sha=branch.name):
                            commit_count += 1
                            total_commits_processed += 1
                            if commit_count > 1000:  # Increased limit to 1000 commits per repo
                                break
                            
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
                            
                            if commit.author and hasattr(commit.author, 'login') and commit.author.login in member_stats:
                                member_stats[commit.author.login]["commits"] += 1
                    except Exception as e:
                        print(f"Error getting commits for branch {branch.name} in {repo.name}: {e}")
                        continue
                        
                    if commit_count > 1000:  # Stop if we hit the limit
                        break
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
                        if assignee.login in member_stats:
                            # For open issues: check if assigned during iteration
                            if issue.state == "open":
                                # Use assignment date if available, otherwise creation date
                                assignment_date = getattr(issue, 'assigned_at', None) or issue.created_at
                                if assignment_date.tzinfo is None:
                                    from datetime import timezone
                                    assignment_date = assignment_date.replace(tzinfo=timezone.utc)
                                
                                if iteration_start and iteration_end:
                                    # Ensure iteration dates are timezone-aware
                                    if iteration_start.tzinfo is None:
                                        from datetime import timezone
                                        iteration_start = iteration_start.replace(tzinfo=timezone.utc)
                                    if iteration_end.tzinfo is None:
                                        iteration_end = iteration_end.replace(tzinfo=timezone.utc)
                                    
                                    if iteration_start <= assignment_date <= iteration_end:
                                        member_stats[assignee.login]["assigned_issues"] += 1
                                        print(f"Found assigned issue in iteration: {issue.title[:50]}... assigned to {assignee.login}")
                                else:
                                    # If no iteration filtering, count all assigned issues
                                    member_stats[assignee.login]["assigned_issues"] += 1
                            
                            # For closed issues: check if closed during iteration
                            elif issue.state == "closed":
                                # Use closed date if available, otherwise creation date
                                closed_date = getattr(issue, 'closed_at', None) or issue.created_at
                                if closed_date.tzinfo is None:
                                    from datetime import timezone
                                    closed_date = closed_date.replace(tzinfo=timezone.utc)
                                
                                if iteration_start and iteration_end:
                                    # Ensure iteration dates are timezone-aware
                                    if iteration_start.tzinfo is None:
                                        from datetime import timezone
                                        iteration_start = iteration_start.replace(tzinfo=timezone.utc)
                                    if iteration_end.tzinfo is None:
                                        iteration_end = iteration_end.replace(tzinfo=timezone.utc)
                                    
                                    if iteration_start <= closed_date <= iteration_end:
                                        member_stats[assignee.login]["closed_issues"] += 1
                                        print(f"Found closed issue in iteration: {issue.title[:50]}... closed by {assignee.login}")
                                else:
                                    # If no iteration filtering, count all closed issues
                                    member_stats[assignee.login]["closed_issues"] += 1
            except Exception as e:
                print(f"Error getting issues for {repo.name}: {e}")
                continue
        
        # Build report with iteration information
        report = ["hello world\n", f"GitHub Organization: {ORG_NAME}\n"]
        
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
        report.append("")
        report.append(f"{'User':20} | {'Commits':7} | {'Assigned Issues':14} | {'Closed Issues':13}")
        report.append("-"*65)
        for login, stats in member_stats.items():
            report.append(f"{login:20} | {stats['commits']:7} | {stats['assigned_issues']:14} | {stats['closed_issues']:13}")
        return "\n".join(report)
        
    except Exception as e:
        return f"Unexpected error: {str(e)}\n\nPlease check your GitHub token and organization access."

@app.get("/github-report", response_class=PlainTextResponse)
async def github_report():
    """
    Legacy endpoint that redirects to the new web interface.
    """
    return "GitHub Report Server is running! Visit / for the web interface or /api/github-report for the raw report."

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