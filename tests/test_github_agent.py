import pytest
from unittest.mock import Mock, AsyncMock
import os
from datetime import datetime, timezone
from agent_mcp_demo.agents.github_agent import GitHubError, GitHubAuthError
from agent_mcp_demo.agents.types import GitHubData, IterationInfo, MemberStats

@pytest.fixture
def mock_github_data() -> GitHubData:
    return {
        "member_stats": {
            "user1": {"commits": 5, "assigned_issues": 3, "closed_issues": 2},
            "user2": {"commits": 2, "assigned_issues": 1, "closed_issues": 1}
        },
        "commit_details": {
            "user1": [
                {
                    "repo": "test-repo",
                    "message": "test commit",
                    "date": datetime.now(timezone.utc),
                    "sha": "abc123",
                    "branch": "main"
                }
            ],
            "user2": []
        },
        "assigned_issues": {
            "user1": [],
            "user2": []
        },
        "closed_issues": {
            "user1": [],
            "user2": []
        }
    }

@pytest.fixture
def mock_iteration_info() -> IterationInfo:
    return {
        "name": "Test Sprint",
        "start_date": "2025-08-01T00:00:00Z",
        "end_date": "2025-08-15T00:00:00Z",
        "path": "test-org/Test Board"
    }

async def test_github_agent_auth_error():
    from agent_mcp_demo.agents.github_agent import handle_call_tool
    
    with pytest.raises(GitHubAuthError):
        await handle_call_tool("get-github-data", {"org_name": "test-org"})

async def test_github_data_validation():
    data = mock_github_data()
    # Test type checking
    assert isinstance(data["member_stats"], dict)
    for stats in data["member_stats"].values():
        assert isinstance(stats, dict)
        assert all(isinstance(v, int) for v in stats.values())
    
    # Test required fields
    for member in data["member_stats"]:
        stats = data["member_stats"][member]
        assert "commits" in stats
        assert "assigned_issues" in stats
        assert "closed_issues" in stats

async def test_iteration_info_validation():
    info = mock_iteration_info()
    # Test required fields
    assert all(key in info for key in ["name", "start_date", "end_date", "path"])
    
    # Test date format
    from datetime import datetime
    start = datetime.fromisoformat(info["start_date"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(info["end_date"].replace("Z", "+00:00"))
    assert end > start
