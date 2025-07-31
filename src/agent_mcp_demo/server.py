

import asyncio
import json
import httpx
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from mcp.server.models import InitializationOptions
import mcp.types as types
from mcp.server import NotificationOptions, Server
from pydantic import AnyUrl
import mcp.server.stdio
import os
from github import Github
from dotenv import load_dotenv
from azure.devops.connection import Connection
from msrest.authentication import BasicAuthentication

# Load environment variables from .env file at startup
load_dotenv()

# Add FastAPI app for HTTP endpoints
app = FastAPI()

@app.get("/", response_class=PlainTextResponse)
async def root():
    return "GitHub Report Server is running! Visit /github-report for the report."

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

# Agent 3: Get iteration information from Azure DevOps
def get_current_iteration_info(org_url: str, project_name: str, personal_access_token: str) -> dict:
    """
    Get current iteration information from Azure DevOps
    """
    try:
        # Create a connection to Azure DevOps
        credentials = BasicAuthentication('', personal_access_token)
        connection = Connection(base_url=org_url, creds=credentials)
        
        # Get the work client
        work_client = connection.clients.get_work_client()
        
        # Get iterations for the project
        iterations = work_client.get_iterations(project=project_name)
        
        # Find the current iteration (active iteration)
        current_iteration = None
        for iteration in iterations:
            if iteration.attributes and iteration.attributes.time_frame == 'current':
                current_iteration = iteration
                break
        
        if current_iteration:
            return {
                'name': current_iteration.name,
                'start_date': current_iteration.attributes.start_date.isoformat() if current_iteration.attributes.start_date else None,
                'end_date': current_iteration.attributes.finish_date.isoformat() if current_iteration.attributes.finish_date else None,
                'path': current_iteration.path
            }
        else:
            return None
            
    except Exception as e:
        print(f"Error getting iteration info: {e}")
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

@app.get("/github-report", response_class=PlainTextResponse)
async def github_report():
    """
    Fetches all members of a GitHub organization, counts their commits and assigned issues for the current iteration, and returns a report.
    """
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    ORG_NAME = os.environ.get("GITHUB_ORG_NAME")
    AZURE_DEVOPS_TOKEN = os.environ.get("AZURE_DEVOPS_TOKEN")
    AZURE_DEVOPS_ORG_URL = os.environ.get("AZURE_DEVOPS_ORG_URL")
    AZURE_DEVOPS_PROJECT = os.environ.get("AZURE_DEVOPS_PROJECT")
    
    if not GITHUB_TOKEN:
        return "GitHub token not set in environment. Please set GITHUB_TOKEN environment variable."
    if not ORG_NAME:
        return "GitHub organization name not set in environment. Please set GITHUB_ORG_NAME environment variable."
    
    # Get current iteration information
    iteration_info = None
    if AZURE_DEVOPS_TOKEN and AZURE_DEVOPS_ORG_URL and AZURE_DEVOPS_PROJECT:
        try:
            iteration_info = get_current_iteration_info(AZURE_DEVOPS_ORG_URL, AZURE_DEVOPS_PROJECT, AZURE_DEVOPS_TOKEN)
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
        
        member_stats = {m.login: {"commits": 0, "assigned_issues": 0} for m in members}
        
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
        for repo in org.get_repos():
            repo_count += 1
            # Removed artificial limit to process all repositories
                
            # Commits per user (filtered by iteration if available)
            try:
                commit_count = 0
                for commit in repo.get_commits():
                    commit_count += 1
                    if commit_count > 1000:  # Increased limit to 1000 commits per repo
                        break
                    
                    # Filter by iteration dates if available
                    if iteration_start and iteration_end:
                        try:
                            commit_date = commit.commit.author.date
                            if not (iteration_start <= commit_date <= iteration_end):
                                continue
                        except AttributeError:
                            # Skip commits with invalid author data
                            continue
                    
                    if commit.author and hasattr(commit.author, 'login') and commit.author.login in member_stats:
                        member_stats[commit.author.login]["commits"] += 1
            except Exception as e:
                print(f"Error getting commits for {repo.name}: {e}")
                continue
                
            # Assigned issues per user (filtered by iteration if available)
            try:
                issue_count = 0
                for issue in repo.get_issues(state="open"):
                    issue_count += 1
                    if issue_count > 500:  # Increased limit to 500 issues per repo
                        break
                    
                    # Filter by iteration dates if available
                    if iteration_start and iteration_end:
                        issue_date = issue.created_at
                        if not (iteration_start <= issue_date <= iteration_end):
                            continue
                    
                    for assignee in issue.assignees:
                        if assignee.login in member_stats:
                            member_stats[assignee.login]["assigned_issues"] += 1
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
        if iteration_start and iteration_end:
            report.append(f"Filtered by iteration: {iteration_start.strftime('%Y-%m-%d')} to {iteration_end.strftime('%Y-%m-%d')}")
        report.append("")
        report.append(f"{'User':20} | {'Commits':7} | {'Assigned Issues':14}")
        report.append("-"*50)
        for login, stats in member_stats.items():
            report.append(f"{login:20} | {stats['commits']:7} | {stats['assigned_issues']:14}")
        return "\n".join(report)
        
    except Exception as e:
        return f"Unexpected error: {str(e)}\n\nPlease check your GitHub token and organization access."

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