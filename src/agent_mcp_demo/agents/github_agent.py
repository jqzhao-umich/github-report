import mcp.types as types
import os
import json
import requests
from datetime import datetime, timezone, timedelta
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
try:
    from github import Github
except ImportError:
    raise ImportError("PyGithub is required. Install it with: pip install PyGithub")

server = Server("github-agent")

def get_current_iteration_info(github_token: str, org_name: str, project_name: str = "Michigan App Team Task Board") -> dict:
    """
    Get current iteration information from GitHub Projects using GraphQL API
    """
    import requests
    import json
    
    try:
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
        target_project = next((p for p in projects if p.get('title') == project_name), None)
        
        if not target_project:
            print(f"Project '{project_name}' not found in organization '{org_name}'")
            print(f"Available projects: {[p.get('title') for p in projects]}")
            # Fall through to environment variable fallback
        else:
            print(f"Found project: {target_project.get('title')} (ID: {target_project.get('id')})")
            
            # Get project fields
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
            
            fields_response = requests.post(
                'https://api.github.com/graphql',
                headers=headers,
                json={'query': fields_query, 'variables': {"projectId": target_project['id']}}
            )
            
            if fields_response.status_code == 200:
                fields_data = fields_response.json()
                if 'data' in fields_data and fields_data['data']['node']:
                    fields = fields_data['data']['node']['fields']['nodes']
                    
                    for field in fields:
                        if (field.get('__typename') == 'ProjectV2IterationField' or 
                            field.get('name', '').lower() == 'iteration'):
                            
                            if 'configuration' in field and 'iterations' in field['configuration']:
                                iterations = field['configuration']['iterations']
                                if iterations:
                                    today = datetime.now().date()
                                    current_iteration = None
                                    
                                    for iteration in iterations:
                                        start_date = datetime.fromisoformat(iteration['startDate']).date()
                                        end_date = start_date + timedelta(days=iteration['duration'])
                                        
                                        if start_date <= today <= end_date:
                                            current_iteration = iteration
                                            break
                                    
                                    if current_iteration:
                                        start_date = datetime.fromisoformat(current_iteration['startDate'])
                                        end_date = start_date + timedelta(days=current_iteration['duration'])
                                        
                                        return {
                                            'name': current_iteration['title'],
                                            'start_date': start_date.isoformat(),
                                            'end_date': end_date.isoformat(),
                                            'path': f"{org_name}/{project_name}"
                                        }
        
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
            
    except Exception as e:
        print(f"Error getting iteration info from GitHub Projects: {e}")
    return None

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get-github-data",
            description="Get GitHub organization data including commits and issues",
            inputSchema={
                "type": "object",
                "properties": {
                    "org_name": {"type": "string"},
                    "iteration_info": {
                        "type": "object",
                        "properties": {
                            "start_date": {"type": "string"},
                            "end_date": {"type": "string"}
                        }
                    }
                },
                "required": ["org_name"]
            }
        ),
        types.Tool(
            name="get-iteration-info",
            description="Get current iteration information from GitHub Projects",
            inputSchema={
                "type": "object",
                "properties": {
                    "org_name": {"type": "string"},
                    "project_name": {"type": "string"}
                },
                "required": ["org_name"]
            }
        )
    ]

class GitHubError(Exception):
    """Base exception for GitHub-related errors"""
    pass

class GitHubAuthError(GitHubError):
    """GitHub authentication error"""
    pass

class GitHubRateLimitError(GitHubError):
    """GitHub API rate limit exceeded"""
    pass

class GitHubAccessError(GitHubError):
    """GitHub resource access error"""
    pass

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    # Check for unknown tools first
    valid_tools = ["get-iteration-info", "get-github-data"]
    if name not in valid_tools:
        raise ValueError(f"Unknown tool: {name}")
    
    if not arguments:
        raise ValueError("Missing arguments")

    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    if not GITHUB_TOKEN:
        raise GitHubAuthError("GitHub token not set in environment. Please set GITHUB_TOKEN environment variable.")

    if name == "get-iteration-info":
        org_name = arguments.get("org_name")
        project_name = arguments.get("project_name", "Michigan App Team Task Board")
        
        iteration_info = get_current_iteration_info(GITHUB_TOKEN, org_name, project_name)
        return [types.TextContent(type="text", text=str(iteration_info))]

    elif name == "get-github-data":
        org_name = arguments.get("org_name")
        iteration_info = arguments.get("iteration_info")
        
        g = Github(GITHUB_TOKEN)
        org = g.get_organization(org_name)
        
        # Initialize data structures
        member_stats = {}
        email_to_login = {}
        commit_details = {}
        assigned_issues = {}
        closed_issues = {}
        
        # Get members and setup tracking
        members = list(org.get_members())
        for member in members:
            member_stats[member.login] = {"commits": 0, "assigned_issues": 0, "closed_issues": 0}
            commit_details[member.login] = []
            assigned_issues[member.login] = []
            closed_issues[member.login] = []
            
            try:
                user = g.get_user(member.login)
                if user.email:
                    email_to_login[user.email.lower()] = member.login
                try:
                    emails = user.get_emails()
                    for email in emails:
                        if email.verified:
                            email_to_login[email.email.lower()] = member.login
                except:
                    pass
            except Exception as e:
                print(f"Error getting emails for {member.login}: {e}")
        
        # Process repositories
        for repo in org.get_repos():
            if repo.archived:
                continue
                
            # Process commits
            for branch in repo.get_branches():
                since = None
                until = None
                if iteration_info:
                    since = datetime.fromisoformat(iteration_info['start_date'])
                    until = datetime.fromisoformat(iteration_info['end_date'])
                
                for commit in repo.get_commits(sha=branch.name, since=since, until=until):
                    commit_info = {
                        'repo': repo.name,
                        'message': commit.commit.message.split('\n')[0],
                        'date': commit.commit.author.date,
                        'sha': commit.sha[:7],
                        'branch': branch.name
                    }
                    
                    if commit.author and commit.author.login in member_stats:
                        member_stats[commit.author.login]["commits"] += 1
                        commit_details[commit.author.login].append(commit_info)
                    elif commit.commit.author.email and commit.commit.author.email.lower() in email_to_login:
                        login = email_to_login[commit.commit.author.email.lower()]
                        member_stats[login]["commits"] += 1
                        commit_details[login].append(commit_info)
            
            # Process issues
            for issue in repo.get_issues(state="all"):
                for assignee in issue.assignees:
                    if assignee.login in member_stats:
                        if iteration_info:
                            assignment_date = getattr(issue, 'assigned_at', None) or issue.created_at
                            iteration_start = datetime.fromisoformat(iteration_info['start_date'])
                            iteration_end = datetime.fromisoformat(iteration_info['end_date'])
                            
                            if iteration_start <= assignment_date <= iteration_end:
                                member_stats[assignee.login]["assigned_issues"] += 1
                                assigned_issues[assignee.login].append({
                                    'repo': repo.name,
                                    'number': issue.number,
                                    'title': issue.title,
                                    'state': issue.state,
                                    'assigned_date': assignment_date
                                })
                            
                            if issue.state == "closed" and issue.closed_at:
                                closed_date = issue.closed_at
                                if iteration_start <= closed_date <= iteration_end:
                                    member_stats[assignee.login]["closed_issues"] += 1
                                    closed_issues[assignee.login].append({
                                        'repo': repo.name,
                                        'number': issue.number,
                                        'title': issue.title,
                                        'closed_date': closed_date
                                    })
                        else:
                            member_stats[assignee.login]["assigned_issues"] += 1
                            assigned_issues[assignee.login].append({
                                'repo': repo.name,
                                'number': issue.number,
                                'title': issue.title,
                                'state': issue.state,
                                'assigned_date': issue.created_at
                            })
                            
                            if issue.state == "closed":
                                member_stats[assignee.login]["closed_issues"] += 1
                                closed_issues[assignee.login].append({
                                    'repo': repo.name,
                                    'number': issue.number,
                                    'title': issue.title,
                                    'closed_date': issue.closed_at
                                })
        
        return [types.TextContent(
            type="text",
            text=str({
                "member_stats": member_stats,
                "commit_details": commit_details,
                "assigned_issues": assigned_issues,
                "closed_issues": closed_issues
            })
        )]

async def main():
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="github-agent",
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
