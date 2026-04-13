"""
Shared utility for GitHub organization member management.

This module provides functionality to retrieve organization members,
build email-to-GitHub login mappings, and initialize member statistics
tracking structures. Used by both standalone functions and MCP agents.
"""

from github import Github
from typing import Dict, List, Optional


def collect_members_and_emails(
    github: Github,
    org_name: str,
    exclude_user_login: Optional[str] = None
) -> tuple[Dict[str, dict], Dict[str, str], List[str]]:
    """
    Collect organization members and build email mapping.
    
    Args:
        github: Authenticated Github instance (PyGithub)
        org_name: GitHub organization name
        exclude_user_login: Optional username to exclude (e.g., current user)
        
    Returns:
        Tuple of (member_stats, email_to_login, member_logins):
        - member_stats: Dict[login, stats_dict] with initialized counters
        - email_to_login: Dict[email, login] for email-based commit matching
        - member_logins: List of member login names (for sorting/display)
        
    Example:
        member_stats = {
            'alice': {
                'commits': 0,
                'assigned_issues': 0,
                'closed_issues': 0,
                'pr_created': 0,
                'pr_reviewed': 0,
                'pr_merged': 0,
                'pr_commented': 0
            }
        }
        email_to_login = {
            'alice@example.com': 'alice',
            'alice@users.noreply.github.com': 'alice'
        }
        member_logins = ['alice', 'bob', 'carol']
    """
    org = github.get_organization(org_name)
    members = list(org.get_members())
    print(f"Found {len(members)} members")
    
    member_stats = {}
    email_to_login = {}
    member_logins = []
    
    for member in members:
        # Skip excluded user (e.g., current user running the report)
        if exclude_user_login and member.login == exclude_user_login:
            print(f"Skipping current user: {member.login}")
            continue
        
        # Initialize member statistics
        member_stats[member.login] = {
            "commits": 0,
            "assigned_issues": 0,
            "closed_issues": 0,
            "pr_created": 0,
            "pr_reviewed": 0,
            "pr_merged": 0,
            "pr_commented": 0
        }
        
        member_logins.append(member.login)
        
        # Build email mapping for commit attribution
        try:
            user = github.get_user(member.login)
            
            # Get primary email if available
            if user.email:
                email_to_login[user.email.lower()] = member.login
            
            # Get all verified emails if we have permission
            try:
                emails = user.get_emails()
                for email in emails:
                    if email.verified:  # Only use verified emails
                        email_to_login[email.email.lower()] = member.login
            except:
                # Skip if we don't have permission to see emails
                pass
                
        except Exception as e:
            print(f"Error getting emails for {member.login}: {e}")
    
    print(f"Found {len(email_to_login)} email mappings for {len(member_stats)} members")
    
    return member_stats, email_to_login, member_logins


def initialize_detail_structures(member_logins: List[str]) -> Dict[str, Dict[str, list]]:
    """
    Initialize detailed activity tracking structures for all members.
    
    Args:
        member_logins: List of member GitHub login names
        
    Returns:
        Dictionary with empty lists for each activity type per member:
        {
            'commit_details': {login: []},
            'assigned_issues': {login: []},
            'closed_issues': {login: []},
            'pr_created': {login: []},
            'pr_reviewed': {login: []},
            'pr_merged': {login: []},
            'pr_commented': {login: []}
        }
    """
    details = {
        'commit_details': {},
        'assigned_issues': {},
        'closed_issues': {},
        'pr_created': {},
        'pr_reviewed': {},
        'pr_merged': {},
        'pr_commented': {}
    }
    
    for login in member_logins:
        details['commit_details'][login] = []
        details['assigned_issues'][login] = []
        details['closed_issues'][login] = []
        details['pr_created'][login] = []
        details['pr_reviewed'][login] = []
        details['pr_merged'][login] = []
        details['pr_commented'][login] = []
    
    return details
