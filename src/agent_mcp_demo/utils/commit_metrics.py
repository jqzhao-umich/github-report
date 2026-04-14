"""
Shared utility for collecting commit metrics from GitHub repositories.

This module provides functionality to iterate through repository branches,
collect commits, match them to organization members, and track commit details.
Used by both standalone functions and MCP agents.
"""

from datetime import datetime, timezone
from typing import Dict, Optional, Set

from github.GithubException import IncompletableObject


def collect_commit_metrics(
    repo,
    member_stats: Dict[str, dict],
    email_to_login: Dict[str, str],
    commit_details: Dict[str, list],
    iteration_info: Optional[dict] = None,
    exclude_user_login: Optional[str] = None
) -> int:
    """
    Collect commit metrics from all branches in a repository.

    Args:
        repo: PyGithub Repository object
        member_stats: Dict tracking member statistics (updated in-place)
        email_to_login: Dict mapping emails to GitHub logins
        commit_details: Dict storing commit details per member (updated in-place)
        iteration_info: Optional dict with start_date/end_date for filtering
        exclude_user_login: Optional username to exclude from counting

    Returns:
        Total number of commits processed in this repo

    Side Effects:
        - Updates member_stats[login]['commits'] counters
        - Appends commit info dicts to commit_details[login]
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

            if iteration_start.tzinfo is None:
                iteration_start = iteration_start.replace(tzinfo=timezone.utc)
            if iteration_end.tzinfo is None:
                iteration_end = iteration_end.replace(tzinfo=timezone.utc)

        except Exception as e:
            print(f"Error parsing iteration dates: {e}")

    total_commits_processed = 0
    processed_commits: Set[str] = set()
    # Pre-compute lowered login lookup to avoid per-commit .lower() calls
    login_lower_to_login = {login.lower(): login for login in member_stats}

    try:
        branches = repo.get_branches()

        for branch in branches:
            try:
                print(f"Processing branch {branch.name} in {repo.name}")

                # PyGithub asserts since/until are datetime, not None — only pass when set
                commit_kwargs = {"sha": branch.name}
                if iteration_start:
                    commit_kwargs["since"] = iteration_start
                if iteration_end:
                    commit_kwargs["until"] = iteration_end

                for commit in repo.get_commits(**commit_kwargs):
                    if commit.sha in processed_commits:
                        continue
                    processed_commits.add(commit.sha)
                    total_commits_processed += 1

                    # Additional date filtering (GitHub API may return commits outside range)
                    if iteration_start and iteration_end:
                        try:
                            commit_date = commit.commit.author.date

                            if commit_date.tzinfo is None:
                                commit_date = commit_date.replace(tzinfo=timezone.utc)

                            if not (iteration_start <= commit_date <= iteration_end):
                                continue
                            else:
                                print(f"Found commit in iteration: {commit.commit.message[:50]}... "
                                      f"by {commit.author.login if commit.author else 'Unknown'} "
                                      f"on branch {branch.name}")

                        except AttributeError:
                            continue

                    commit_info = {
                        'repo': repo.name,
                        'message': commit.commit.message.split('\n')[0],
                        'date': commit.commit.author.date,
                        'sha': commit.sha[:7],
                        'branch': branch.name
                    }

                    matched_login = None

                    # First try: GitHub API author (most reliable)
                    try:
                        if commit.author and commit.author.login:
                            login = commit.author.login
                            if login in member_stats:
                                matched_login = login
                                print(f"Matched commit {commit.sha[:7]} on {branch.name} to {login} via GitHub API")
                    except (IncompletableObject, AttributeError):
                        pass

                    # Second try: Email matching (for commits without GitHub author)
                    if not matched_login and commit.commit.author and commit.commit.author.email:
                        email = commit.commit.author.email.lower()
                        if email in email_to_login:
                            matched_login = email_to_login[email]
                            print(f"Matched commit {commit.sha[:7]} on {branch.name} to {matched_login} via email")

                    # Third try: match email local part or git author name against member logins
                    # (handles unlinked accounts like eylinaf@hostname.local or "Weiguo Xia")
                    if not matched_login and commit.commit.author:
                        candidates = set()
                        if commit.commit.author.email:
                            local_part = commit.commit.author.email.lower().split('@')[0]
                            candidates.add(local_part)
                            if '+' in local_part:
                                candidates.add(local_part.split('+')[-1])
                        if commit.commit.author.name:
                            candidates.add(commit.commit.author.name.replace(' ', '').lower())

                        for candidate in candidates:
                            if candidate in login_lower_to_login:
                                matched_login = login_lower_to_login[candidate]
                                print(f"Matched commit {commit.sha[:7]} on {branch.name} to {matched_login} via local part/name")
                                break

                    # Skip excluded user, update statistics
                    if matched_login:
                        if exclude_user_login and matched_login == exclude_user_login:
                            continue
                        member_stats[matched_login]["commits"] += 1
                        commit_details[matched_login].append(commit_info)
                        
            except Exception as e:
                print(f"Error processing branch {branch.name} in {repo.name}: {e}")
                continue
                
    except Exception as e:
        print(f"Error getting branches for {repo.name}: {e}")
    
    return total_commits_processed
