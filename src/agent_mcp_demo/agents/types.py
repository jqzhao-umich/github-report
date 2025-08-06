"""
Type definitions for MCP agents
"""

from typing import TypedDict, List, Dict, Optional
from datetime import datetime

class CommitInfo(TypedDict):
    repo: str
    message: str
    date: datetime
    sha: str
    branch: str

class IssueInfo(TypedDict):
    repo: str
    number: int
    title: str
    state: str
    assigned_date: datetime

class ClosedIssueInfo(TypedDict):
    repo: str
    number: int
    title: str
    closed_date: datetime

class MemberStats(TypedDict):
    commits: int
    assigned_issues: int
    closed_issues: int

class IterationInfo(TypedDict):
    name: str
    start_date: str
    end_date: str
    path: str

class GitHubData(TypedDict):
    member_stats: Dict[str, MemberStats]
    commit_details: Dict[str, List[CommitInfo]]
    assigned_issues: Dict[str, List[IssueInfo]]
    closed_issues: Dict[str, List[ClosedIssueInfo]]
