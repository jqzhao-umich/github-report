"""GitHub Agent - MCP Server (Pure Provider)

This is an MCP SERVER that provides GitHub organization data tools.
It does NOT call other agents (pure server, not a client).

Provides tools:
- get-iteration-info: Current iteration from GitHub Projects
- get-github-data: Comprehensive org metrics including:
  • Member commits with branch tracking and email matching
  • Assigned and closed issues filtered by iteration dates
  • Pull request metrics (created, reviewed, merged, commented)

Called by: web_interface_agent, main_coordinator
For standalone report generation (no MCP), see server.py instead.
"""

import mcp.types as types
import os
import json
import logging
import requests
from datetime import datetime, timezone, timedelta
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/github.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('github-agent')
try:
    from github import Github, Auth
except ImportError:
    raise ImportError("PyGithub is required. Install it with: pip install PyGithub")

from ..utils.pr_metrics import collect_pr_metrics
from ..utils.iteration_info import get_current_iteration_info
from ..utils.github_members import collect_members_and_emails, initialize_detail_structures
from ..utils.commit_metrics import collect_commit_metrics
from ..utils.issue_metrics import collect_issue_metrics

import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/github.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('github-agent')

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
    """Handle tool calls with comprehensive error handling"""
    print(f"Starting tool execution: {name} with arguments: {arguments}")
    
    # Check for unknown tools first
    valid_tools = ["get-iteration-info", "get-github-data"]
    if name not in valid_tools:
        raise ValueError(f"Unknown tool: {name}")
    
    if not arguments:
        raise ValueError("Missing arguments")
    
    print(f"Arguments validated for tool: {name}")
    
    GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
    if not GITHUB_TOKEN:
        raise GitHubAuthError("GitHub token not set in environment. Please set GITHUB_TOKEN environment variable.")
        
    print(f"Environment validated for tool: {name}")

    if name == "get-iteration-info":
        try:
            org_name = arguments.get("org_name")
            if not org_name:
                raise ValueError("org_name is required")
                
            project_name = arguments.get("project_name", "Michigan App Team Task Board")
            print(f"Getting iteration info for org: {org_name}, project: {project_name}")
            
            iteration_info = get_current_iteration_info(GITHUB_TOKEN, org_name, project_name)
            if iteration_info is None:
                raise GitHubAccessError("Could not fetch iteration information")
                
            print(f"Successfully retrieved iteration info: {iteration_info}")
            return [types.TextContent(type="text", text=str(iteration_info))]
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error in get-iteration-info: {error_details}")
            raise GitHubError(f"Error getting iteration info: {str(e)}")

    elif name == "get-github-data":
        try:
            org_name = arguments.get("org_name")
            if not org_name:
                raise ValueError("org_name is required")
                
            iteration_info = arguments.get("iteration_info")
            print(f"Getting GitHub data for org: {org_name} with iteration info: {iteration_info}")
            
            try:
                auth = Auth.Token(GITHUB_TOKEN)
                g = Github(auth=auth)
                
                # Test GitHub connection first
                current_user = g.get_user()
                if not current_user or not current_user.login:
                    raise GitHubAuthError("Could not authenticate with GitHub API")
                current_user_login = current_user.login
                print(f"Successfully authenticated as: {current_user_login}")
                
                # Test organization access
                org = g.get_organization(org_name)
                if not org or not org.login:
                    raise GitHubAccessError(f"Could not access organization: {org_name}")
                print(f"Successfully connected to GitHub organization: {org_name}")
                
                # Test org membership
                try:
                    current_user.get_organization_membership(org_name)
                except:
                    print(f"Warning: User {current_user_login} might not be a member of {org_name}, some data may be limited")
                    
            except GitHubAuthError as e:
                raise e
            except GitHubAccessError as e:
                raise e
            except Exception as e:
                raise GitHubAccessError(f"Failed to access GitHub organization {org_name}: {str(e)}")
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"Error in get-github-data setup: {error_details}")
            raise GitHubError(f"Failed to setup GitHub data retrieval: {str(e)}")
        
        # Collect members and build email mapping using shared utility
        # Exclude current user to match GitHub Actions behavior
        member_stats, email_to_login, member_logins = collect_members_and_emails(
            g, org_name, exclude_user_login=current_user_login
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
        
        # Process repositories
        for repo in org.get_repos():
            if repo.archived:
                continue
            
            # Collect commit metrics using shared utility
            collect_commit_metrics(
                repo, member_stats, email_to_login, commit_details,
                iteration_info, exclude_user_login=current_user_login
            )
            
            # Collect issue metrics using shared utility
            collect_issue_metrics(
                repo, member_stats, assigned_issues, closed_issues,
                iteration_info
            )
            
            # Collect PR metrics using shared utility
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
        
        return [types.TextContent(
            type="text",
            text=str({
                "member_stats": member_stats,
                "commit_details": commit_details,
                "assigned_issues": assigned_issues,
                "closed_issues": closed_issues,
                "pr_created": pr_created,
                "pr_reviewed": pr_reviewed,
                "pr_merged": pr_merged,
                "pr_commented": pr_commented
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
    import logging
    import os
    
    # Set up logging
    os.makedirs('logs', exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/github.log'),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger('github-agent')
    logger.info("Starting GitHub Agent")
    
    asyncio.run(main())
