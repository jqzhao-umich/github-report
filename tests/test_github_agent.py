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
            "user1": {
                "commits": 5, 
                "assigned_issues": 3, 
                "closed_issues": 2,
                "pr_created": 2,
                "pr_reviewed": 3,
                "pr_merged": 1,
                "pr_commented": 4
            },
            "user2": {
                "commits": 2, 
                "assigned_issues": 1, 
                "closed_issues": 1,
                "pr_created": 1,
                "pr_reviewed": 1,
                "pr_merged": 0,
                "pr_commented": 2
            }
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
        },
        "pr_created": {
            "user1": [],
            "user2": []
        },
        "pr_reviewed": {
            "user1": [],
            "user2": []
        },
        "pr_merged": {
            "user1": [],
            "user2": []
        },
        "pr_commented": {
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
        assert "pr_created" in stats
        assert "pr_reviewed" in stats
        assert "pr_merged" in stats
        assert "pr_commented" in stats

async def test_iteration_info_validation():
    info = mock_iteration_info()
    # Test required fields
    assert all(key in info for key in ["name", "start_date", "end_date", "path"])
    
    # Test date format
    from datetime import datetime
    start = datetime.fromisoformat(info["start_date"].replace("Z", "+00:00"))
    end = datetime.fromisoformat(info["end_date"].replace("Z", "+00:00"))
    assert end > start

def test_pr_metrics_in_member_stats(mock_github_data):
    """Test that PR metrics are properly included in member stats"""
    data = mock_github_data
    
    for member, stats in data["member_stats"].items():
        # Verify all PR metrics exist
        assert "pr_created" in stats, f"Missing pr_created for {member}"
        assert "pr_reviewed" in stats, f"Missing pr_reviewed for {member}"
        assert "pr_merged" in stats, f"Missing pr_merged for {member}"
        assert "pr_commented" in stats, f"Missing pr_commented for {member}"
        
        # Verify all PR metrics are integers
        assert isinstance(stats["pr_created"], int), "pr_created should be an integer"
        assert isinstance(stats["pr_reviewed"], int), "pr_reviewed should be an integer"
        assert isinstance(stats["pr_merged"], int), "pr_merged should be an integer"
        assert isinstance(stats["pr_commented"], int), "pr_commented should be an integer"
        
        # Verify non-negative values
        assert stats["pr_created"] >= 0, "pr_created should be non-negative"
        assert stats["pr_reviewed"] >= 0, "pr_reviewed should be non-negative"
        assert stats["pr_merged"] >= 0, "pr_merged should be non-negative"
        assert stats["pr_commented"] >= 0, "pr_commented should be non-negative"

def test_pr_detail_structures(mock_github_data):
    """Test that PR detail dictionaries are properly structured"""
    data = mock_github_data
    
    # Verify all PR detail dictionaries exist
    assert "pr_created" in data, "Missing pr_created details"
    assert "pr_reviewed" in data, "Missing pr_reviewed details"
    assert "pr_merged" in data, "Missing pr_merged details"
    assert "pr_commented" in data, "Missing pr_commented details"
    
    # Verify they are dictionaries
    assert isinstance(data["pr_created"], dict)
    assert isinstance(data["pr_reviewed"], dict)
    assert isinstance(data["pr_merged"], dict)
    assert isinstance(data["pr_commented"], dict)
    
    # Verify each member has an entry
    for member in data["member_stats"].keys():
        assert member in data["pr_created"], f"Missing pr_created details for {member}"
        assert member in data["pr_reviewed"], f"Missing pr_reviewed details for {member}"
        assert member in data["pr_merged"], f"Missing pr_merged details for {member}"
        assert member in data["pr_commented"], f"Missing pr_commented details for {member}"
        
        # Verify entries are lists
        assert isinstance(data["pr_created"][member], list)
        assert isinstance(data["pr_reviewed"][member], list)
        assert isinstance(data["pr_merged"][member], list)
        assert isinstance(data["pr_commented"][member], list)

def test_github_data_completeness(mock_github_data):
    """Test that GitHub data structure contains all required fields"""
    data = mock_github_data
    
    # Original fields
    required_fields = ["member_stats", "commit_details", "assigned_issues", "closed_issues"]
    # New PR fields
    pr_fields = ["pr_created", "pr_reviewed", "pr_merged", "pr_commented"]
    
    all_required = required_fields + pr_fields
    
    for field in all_required:
        assert field in data, f"Missing required field: {field}"
        assert isinstance(data[field], dict), f"{field} should be a dictionary"
