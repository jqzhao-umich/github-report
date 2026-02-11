"""
Utility for collecting pull request metrics from GitHub repositories.
Shared by both the MCP agent system and standalone report generator.
"""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any


def collect_pr_metrics(
    repo,
    member_stats: Dict[str, Dict[str, int]],
    iteration_info: Optional[Dict[str, str]] = None,
    current_user_login: Optional[str] = None
) -> tuple[Dict[str, List[Dict]], Dict[str, List[Dict]], Dict[str, List[Dict]], Dict[str, List[Dict]]]:
    """
    Collect pull request metrics for repository members.
    
    Args:
        repo: GitHub repository object
        member_stats: Dictionary of member statistics to update
        iteration_info: Optional iteration information with start_date and end_date
        current_user_login: Optional current user login to exclude from metrics
        
    Returns:
        Tuple of (pr_created, pr_reviewed, pr_merged, pr_commented) dictionaries
    """
    pr_created = defaultdict(list)
    pr_reviewed = defaultdict(list)
    pr_merged = defaultdict(list)
    pr_commented = defaultdict(list)
    
    # Initialize PR counters in member_stats if not present
    for login in member_stats.keys():
        if "pr_created" not in member_stats[login]:
            member_stats[login]["pr_created"] = 0
        if "pr_reviewed" not in member_stats[login]:
            member_stats[login]["pr_reviewed"] = 0
        if "pr_merged" not in member_stats[login]:
            member_stats[login]["pr_merged"] = 0
        if "pr_commented" not in member_stats[login]:
            member_stats[login]["pr_commented"] = 0
    
    # Parse iteration dates if provided
    iteration_start = None
    iteration_end = None
    if iteration_info and iteration_info.get('start_date') and iteration_info.get('end_date'):
        try:
            iteration_start = datetime.fromisoformat(iteration_info['start_date'].replace('Z', '+00:00'))
            iteration_end = datetime.fromisoformat(iteration_info['end_date'].replace('Z', '+00:00'))
            
            # Make iteration dates timezone-aware if they aren't
            if iteration_start.tzinfo is None:
                iteration_start = iteration_start.replace(tzinfo=timezone.utc)
            if iteration_end.tzinfo is None:
                iteration_end = iteration_end.replace(tzinfo=timezone.utc)
        except Exception as e:
            print(f"Error parsing iteration dates: {e}")
    
    try:
        # Process pull requests
        for pr in repo.get_pulls(state="all"):
            # Determine if PR is in the iteration period
            in_iteration = True
            pr_created_in_iteration = False
            pr_merged_in_iteration = False
            pr_updated_in_iteration = False
            
            if iteration_start and iteration_end:
                # Check if PR was created in this iteration
                pr_created_in_iteration = iteration_start <= pr.created_at <= iteration_end
                
                # Check if PR was merged in this iteration
                pr_merged_in_iteration = pr.merged_at and iteration_start <= pr.merged_at <= iteration_end
                
                # Check if PR was updated in this iteration (for reviews/comments)
                pr_updated_in_iteration = iteration_start <= pr.updated_at <= iteration_end
                
                in_iteration = pr_created_in_iteration or pr_merged_in_iteration or pr_updated_in_iteration
            
            if not in_iteration and iteration_info:
                continue
            
            pr_info = {
                'repo': repo.name,
                'number': pr.number,
                'title': pr.title,
                'state': pr.state,
                'created_at': pr.created_at,
                'merged_at': pr.merged_at,
                'closed_at': pr.closed_at
            }
            
            # Track PR creator
            if pr.user and pr.user.login in member_stats:
                if pr.user.login != current_user_login:
                    if not iteration_info or (iteration_info and pr_created_in_iteration):
                        member_stats[pr.user.login]["pr_created"] += 1
                        pr_created[pr.user.login].append(pr_info)
            
            # Track PR merger (person who merged the PR)
            if pr.merged and pr.merged_by and pr.merged_by.login in member_stats:
                if pr.merged_by.login != current_user_login:
                    if not iteration_info or (iteration_info and pr_merged_in_iteration):
                        member_stats[pr.merged_by.login]["pr_merged"] += 1
                        pr_merged[pr.merged_by.login].append(pr_info)
            
            # Track reviewers
            try:
                reviews = pr.get_reviews()
                reviewer_set = set()
                for review in reviews:
                    if review.user and review.user.login in member_stats:
                        if review.user.login != current_user_login:
                            if not iteration_info or (iteration_info and 
                                iteration_start <= review.submitted_at <= iteration_end):
                                reviewer_set.add(review.user.login)
                
                for reviewer_login in reviewer_set:
                    member_stats[reviewer_login]["pr_reviewed"] += 1
                    if pr_info not in pr_reviewed[reviewer_login]:
                        pr_reviewed[reviewer_login].append(pr_info)
            except Exception as e:
                print(f"Error getting reviews for PR #{pr.number} in {repo.name}: {e}")
            
            # Track commenters
            try:
                comments = pr.get_comments()
                commenter_set = set()
                for comment in comments:
                    if comment.user and comment.user.login in member_stats:
                        if comment.user.login != current_user_login:
                            if not iteration_info or (iteration_info and 
                                iteration_start <= comment.created_at <= iteration_end):
                                commenter_set.add(comment.user.login)
                
                # Also check issue comments on PR
                issue_comments = pr.get_issue_comments()
                for comment in issue_comments:
                    if comment.user and comment.user.login in member_stats:
                        if comment.user.login != current_user_login:
                            if not iteration_info or (iteration_info and 
                                iteration_start <= comment.created_at <= iteration_end):
                                commenter_set.add(comment.user.login)
                
                for commenter_login in commenter_set:
                    member_stats[commenter_login]["pr_commented"] += 1
                    if pr_info not in pr_commented[commenter_login]:
                        pr_commented[commenter_login].append(pr_info)
            except Exception as e:
                print(f"Error getting comments for PR #{pr.number} in {repo.name}: {e}")
    
    except Exception as e:
        print(f"Error processing pull requests for {repo.name}: {e}")
    
    return dict(pr_created), dict(pr_reviewed), dict(pr_merged), dict(pr_commented)
