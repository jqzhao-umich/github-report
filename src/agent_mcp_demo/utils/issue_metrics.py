"""
Shared utility for collecting issue metrics from GitHub repositories.

This module provides functionality to iterate through repository issues,
track assigned and closed issues, and filter by iteration dates.
Used by both standalone functions and MCP agents.
"""

from datetime import datetime, timezone
from typing import Dict, Optional


def collect_issue_metrics(
    repo,
    member_stats: Dict[str, dict],
    assigned_issues: Dict[str, list],
    closed_issues: Dict[str, list],
    iteration_info: Optional[dict] = None
) -> tuple[int, int]:
    """
    Collect issue metrics (assigned and closed) from a repository.
    
    Args:
        repo: PyGithub Repository object
        member_stats: Dict tracking member statistics (updated in-place)
        assigned_issues: Dict storing assigned issue details per member (updated in-place)
        closed_issues: Dict storing closed issue details per member (updated in-place)
        iteration_info: Optional dict with start_date/end_date for filtering
        
    Returns:
        Tuple of (total_assigned, total_closed) issue counts processed
        
    Side Effects:
        - Updates member_stats[login]['assigned_issues'] counters
        - Updates member_stats[login]['closed_issues'] counters
        - Appends issue info dicts to assigned_issues[login]
        - Appends issue info dicts to closed_issues[login]
    """
    # Parse iteration dates if provided
    iteration_start = None
    iteration_end = None
    
    if iteration_info and iteration_info.get('start_date') and iteration_info.get('end_date'):
        try:
            iteration_start = datetime.fromisoformat(
                iteration_info['start_date'].replace('Z', '+00:00')
            )
            iteration_end = datetime.fromisoformat(
                iteration_info['end_date'].replace('Z', '+00:00')
            )
            
            # Ensure timezone-aware
            if iteration_start.tzinfo is None:
                iteration_start = iteration_start.replace(tzinfo=timezone.utc)
            if iteration_end.tzinfo is None:
                iteration_end = iteration_end.replace(tzinfo=timezone.utc)
                
        except Exception as e:
            print(f"Error parsing iteration dates: {e}")
    
    total_assigned = 0
    total_closed = 0
    
    try:
        # Get all issues (open and closed)
        for issue in repo.get_issues(state="all"):
            # Skip pull requests (they show up in issues API)
            if issue.pull_request:
                continue
            
            # Process each assignee
            for assignee in issue.assignees:
                if assignee.login not in member_stats:
                    continue
                
                # Determine assignment date (use created_at as fallback)
                assignment_date = getattr(issue, 'assigned_at', None) or issue.created_at
                
                # Make assignment_date timezone-aware if needed
                if assignment_date.tzinfo is None:
                    assignment_date = assignment_date.replace(tzinfo=timezone.utc)
                
                # Check if assigned within iteration
                if iteration_start and iteration_end:
                    if iteration_start <= assignment_date <= iteration_end:
                        member_stats[assignee.login]["assigned_issues"] += 1
                        assigned_issues[assignee.login].append({
                            'repo': repo.name,
                            'number': issue.number,
                            'title': issue.title,
                            'state': issue.state,
                            'assigned_date': assignment_date
                        })
                        total_assigned += 1
                else:
                    # No iteration filter - count all assigned issues
                    member_stats[assignee.login]["assigned_issues"] += 1
                    assigned_issues[assignee.login].append({
                        'repo': repo.name,
                        'number': issue.number,
                        'title': issue.title,
                        'state': issue.state,
                        'assigned_date': assignment_date
                    })
                    total_assigned += 1
                
                # Check if closed within iteration
                if issue.state == "closed" and issue.closed_at:
                    closed_date = issue.closed_at
                    
                    # Make closed_date timezone-aware if needed
                    if closed_date.tzinfo is None:
                        closed_date = closed_date.replace(tzinfo=timezone.utc)
                    
                    if iteration_start and iteration_end:
                        if iteration_start <= closed_date <= iteration_end:
                            member_stats[assignee.login]["closed_issues"] += 1
                            closed_issues[assignee.login].append({
                                'repo': repo.name,
                                'number': issue.number,
                                'title': issue.title,
                                'closed_date': closed_date
                            })
                            total_closed += 1
                    else:
                        # No iteration filter - count all closed issues
                        member_stats[assignee.login]["closed_issues"] += 1
                        closed_issues[assignee.login].append({
                            'repo': repo.name,
                            'number': issue.number,
                            'title': issue.title,
                            'closed_date': closed_date
                        })
                        total_closed += 1
                        
    except Exception as e:
        print(f"Error processing issues for {repo.name}: {e}")
    
    return total_assigned, total_closed
