"""
Shared utility for retrieving iteration information from GitHub Projects.

This module provides functionality to query GitHub Projects (GraphQL API) 
and retrieve current or previous iteration details based on today's date.
Used by both standalone functions and MCP agents.
"""

import os
import json
import requests
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def get_current_iteration_info(
    github_token: str, 
    org_name: str, 
    project_name: str = "Michigan App Team Task Board"
) -> dict:
    """
    Get current iteration information from GitHub Projects using GraphQL API.
    
    Logic:
    - If today is the first day of a new iteration, returns the PREVIOUS iteration
    - Otherwise, returns the current iteration
    - Falls back to environment variables if GraphQL fails
    
    Args:
        github_token: GitHub personal access token with project read permissions
        org_name: GitHub organization name
        project_name: GitHub Projects board name
        
    Returns:
        Dictionary with iteration info: {
            'name': 'Iteration 74',
            'start_date': '2026-02-09',
            'end_date': '2026-02-23T00:00:00',
            'path': 'org/project'
        }
        Returns None if no iteration found and no fallback available
    """
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
        
        variables = {"orgName": org_name}
        
        response = requests.post(
            'https://api.github.com/graphql',
            headers=headers,
            json={'query': query, 'variables': variables},
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"Error getting projects via GraphQL: {response.status_code} - {response.text}")
            return _fallback_to_env_vars(org_name, project_name)
        
        data = response.json()
        
        if 'errors' in data:
            print(f"GraphQL errors: {data['errors']}")
            return _fallback_to_env_vars(org_name, project_name)
        
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
            return _fallback_to_env_vars(org_name, project_name)
        
        print(f"Found project: {target_project.get('title')} (ID: {target_project.get('id')})")
        
        # Get project fields to find iteration configuration
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
        
        fields_variables = {"projectId": target_project.get('id')}
        
        fields_response = requests.post(
            'https://api.github.com/graphql',
            headers=headers,
            json={'query': fields_query, 'variables': fields_variables},
            timeout=10
        )
        
        if fields_response.status_code != 200:
            print(f"Error getting project fields: {fields_response.status_code}")
            return _fallback_to_env_vars(org_name, project_name)
        
        fields_data = fields_response.json()
        
        if 'data' not in fields_data or not fields_data['data']['node']:
            print("No field data returned from GraphQL")
            return _fallback_to_env_vars(org_name, project_name)
        
        fields = fields_data['data']['node']['fields']['nodes']
        print(f"Found {len(fields)} project fields")
        
        # Look for iteration field and extract current/previous iteration
        for field in fields:
            if (field.get('__typename') == 'ProjectV2IterationField' or 
                field.get('name', '').lower() == 'iteration'):
                
                if 'configuration' not in field or 'iterations' not in field['configuration']:
                    continue
                
                iterations = field['configuration']['iterations']
                print(f"Found {len(iterations)} iterations")
                
                if not iterations:
                    continue
                
                target_iteration = _find_target_iteration(iterations)
                
                if target_iteration:
                    return _format_iteration_response(
                        target_iteration, 
                        org_name, 
                        project_name
                    )
        
        print("No iteration field found in project")
        return _fallback_to_env_vars(org_name, project_name)
        
    except Exception as e:
        print(f"Error getting iteration info: {e}")
        import traceback
        traceback.print_exc()
        return _fallback_to_env_vars(org_name, project_name)


def _find_target_iteration(iterations: list) -> dict:
    """
    Find the target iteration based on today's date (Eastern Time).
    
    Logic:
    - If today is the first day of a new iteration, return PREVIOUS iteration
    - Otherwise, return the current iteration
    - If no current iteration, return most recent past iteration
    
    Args:
        iterations: List of iteration dicts from GitHub Projects
        
    Returns:
        Target iteration dict or None
    """
    today = datetime.now(ZoneInfo("America/New_York")).date()
    target_iteration = None
    
    # First, find which iteration we're in
    for idx, iteration in enumerate(iterations):
        start_date = iteration.get('startDate')
        duration = iteration.get('duration')
        
        if not start_date or not duration:
            continue
        
        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00')).date()
        end_dt = start_dt + timedelta(days=duration)
        
        # Check if today falls within this iteration
        if start_dt <= today <= end_dt:
            print(f"Today is in: {iteration.get('title')} ({start_date} to {end_dt})")
            
            # If today is the first day of iteration, use previous iteration
            if today == start_dt:
                if idx > 0:
                    # Previous iteration exists in the list
                    target_iteration = iterations[idx - 1]
                    prev_start_dt = datetime.fromisoformat(
                        target_iteration.get('startDate').replace('Z', '+00:00')
                    ).date()
                    prev_end_dt = prev_start_dt + timedelta(days=target_iteration.get('duration'))
                    print(f"First day of iteration - using previous: {target_iteration.get('title')} "
                          f"({target_iteration.get('startDate')} to {prev_end_dt})")
                else:
                    # Calculate previous iteration (not in list)
                    prev_end_dt = start_dt - timedelta(days=1)
                    prev_start_dt = prev_end_dt - timedelta(days=duration - 1)
                    
                    # Extract iteration number and create previous iteration info
                    match = re.search(r'(\d+)', iteration.get('title', ''))
                    if match:
                        current_num = int(match.group(1))
                        prev_title = iteration.get('title', 'Iteration').replace(
                            str(current_num), 
                            str(current_num - 1)
                        )
                    else:
                        prev_title = 'Previous Iteration'
                    
                    target_iteration = {
                        'title': prev_title,
                        'startDate': prev_start_dt.isoformat(),
                        'duration': duration
                    }
                    print(f"First day of iteration - calculated previous: {prev_title} "
                          f"({prev_start_dt} to {prev_end_dt})")
            else:
                # Use current iteration
                target_iteration = iteration
                print(f"Using current iteration: {iteration.get('title')} ({start_date} to {end_dt})")
            break
    
    # If no current iteration found, use the most recent past iteration
    if not target_iteration:
        for iteration in reversed(iterations):
            start_date = iteration.get('startDate')
            duration = iteration.get('duration')
            
            if not start_date or not duration:
                continue
            
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00')).date()
            end_dt = start_dt + timedelta(days=duration)
            
            # Use the most recent iteration that has ended
            if end_dt < today:
                target_iteration = iteration
                print(f"Using most recent past iteration: {iteration.get('title')} "
                      f"({start_date} to {end_dt})")
                break
    
    # If still no iteration found, use the first one (fallback)
    if not target_iteration and iterations:
        target_iteration = iterations[0]
        print(f"Using fallback iteration: {target_iteration.get('title')}")
    
    return target_iteration


def _format_iteration_response(iteration: dict, org_name: str, project_name: str) -> dict:
    """
    Format iteration data into standardized response.
    
    Args:
        iteration: Iteration dict from GitHub Projects
        org_name: Organization name
        project_name: Project name
        
    Returns:
        Formatted iteration info dict
    """
    start_date = iteration.get('startDate')
    duration = iteration.get('duration')
    
    if start_date and duration:
        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        end_dt = start_dt + timedelta(days=duration)
        end_date = end_dt.isoformat()
    else:
        end_date = None
    
    return {
        'name': iteration.get('title', 'Current Sprint'),
        'start_date': start_date,
        'end_date': end_date,
        'path': f"{org_name}/{project_name}"
    }


def _fallback_to_env_vars(org_name: str, project_name: str) -> dict:
    """
    Fallback to environment variables when GraphQL query fails.
    
    Args:
        org_name: Organization name
        project_name: Project name
        
    Returns:
        Iteration info from env vars, or None if not set
    """
    iteration_start = os.environ.get("GITHUB_ITERATION_START")
    iteration_end = os.environ.get("GITHUB_ITERATION_END")
    iteration_name = os.environ.get("GITHUB_ITERATION_NAME", "Current Sprint")
    
    if iteration_start and iteration_end:
        print("Using iteration info from environment variables")
        return {
            'name': iteration_name,
            'start_date': iteration_start,
            'end_date': iteration_end,
            'path': f"{org_name}/{project_name}"
        }
    
    print("No iteration info available from GraphQL or environment variables")
    return None
