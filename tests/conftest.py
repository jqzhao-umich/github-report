"""
Shared pytest fixtures and configuration
"""

import pytest
import os
import sys
from unittest.mock import Mock, AsyncMock
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

@pytest.fixture(scope="session")
def test_data_dir():
    """Fixture for test data directory"""
    return os.path.join(os.path.dirname(__file__), 'data')

@pytest.fixture
def mock_github_token(monkeypatch):
    """Fixture to set mock GitHub token"""
    token = "test-github-token-12345"
    monkeypatch.setenv("GITHUB_TOKEN", token)
    yield token
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

@pytest.fixture
def mock_org_name(monkeypatch):
    """Fixture to set mock organization name"""
    org = "test-org"
    monkeypatch.setenv("GITHUB_ORG_NAME", org)
    yield org
    monkeypatch.delenv("GITHUB_ORG_NAME", raising=False)

@pytest.fixture
def mock_iteration_env(monkeypatch):
    """Fixture to set mock iteration environment variables"""
    monkeypatch.setenv("GITHUB_ITERATION_START", "2025-01-01T00:00:00Z")
    monkeypatch.setenv("GITHUB_ITERATION_END", "2025-01-15T23:59:59Z")
    monkeypatch.setenv("GITHUB_ITERATION_NAME", "Test Sprint")
    yield
    monkeypatch.delenv("GITHUB_ITERATION_START", raising=False)
    monkeypatch.delenv("GITHUB_ITERATION_END", raising=False)
    monkeypatch.delenv("GITHUB_ITERATION_NAME", raising=False)

@pytest.fixture
def mock_github_user():
    """Fixture for mock GitHub user"""
    user = Mock()
    user.login = "test-user"
    user.email = "test@example.com"
    user.get_emails.return_value = []
    return user

@pytest.fixture
def mock_github_member():
    """Fixture for mock GitHub organization member"""
    member = Mock()
    member.login = "test-member"
    return member

@pytest.fixture
def mock_github_org(mock_github_member):
    """Fixture for mock GitHub organization"""
    org = Mock()
    org.login = "test-org"
    org.get_members.return_value = [mock_github_member]
    org.get_repos.return_value = []
    return org

@pytest.fixture
def mock_github_repo():
    """Fixture for mock GitHub repository"""
    repo = Mock()
    repo.name = "test-repo"
    repo.archived = False
    repo.get_branches.return_value = []
    repo.get_issues.return_value = []
    repo.get_commits.return_value = []
    return repo

@pytest.fixture
def mock_iteration_info():
    """Fixture for mock iteration info"""
    return {
        'name': 'Test Sprint',
        'start_date': '2025-01-01T00:00:00Z',
        'end_date': '2025-01-15T23:59:59Z',
        'path': 'test-org/Test Board'
    }

@pytest.fixture
def mock_github_data():
    """Fixture for mock GitHub data"""
    return {
        "member_stats": {
            "user1": {
                "commits": 5,
                "assigned_issues": 3,
                "closed_issues": 2
            },
            "user2": {
                "commits": 2,
                "assigned_issues": 1,
                "closed_issues": 1
            }
        },
        "commit_details": {
            "user1": [
                {
                    "repo": "test-repo",
                    "message": "Test commit",
                    "date": datetime.now(timezone.utc),
                    "sha": "abc123",
                    "branch": "main"
                }
            ],
            "user2": []
        },
        "assigned_issues": {
            "user1": [
                {
                    "repo": "test-repo",
                    "number": 1,
                    "title": "Test issue",
                    "state": "open",
                    "assigned_date": datetime.now(timezone.utc)
                }
            ],
            "user2": []
        },
        "closed_issues": {
            "user1": [
                {
                    "repo": "test-repo",
                    "number": 2,
                    "title": "Closed issue",
                    "closed_date": datetime.now(timezone.utc)
                }
            ],
            "user2": []
        }
    }

@pytest.fixture
def mock_mcp_session():
    """Fixture for mock MCP session"""
    session = AsyncMock()
    session.call_tool = AsyncMock()
    return session

@pytest.fixture
def mock_server_context(mock_mcp_session):
    """Fixture for mock server request context"""
    context = Mock()
    context.session = mock_mcp_session
    return context

# Pytest configuration
def pytest_configure(config):
    """Configure pytest markers"""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running"
    )
    config.addinivalue_line(
        "markers", "performance: marks tests as performance tests"
    )
    config.addinivalue_line(
        "markers", "network: marks tests that require network access"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
