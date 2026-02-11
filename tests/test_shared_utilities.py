"""
Tests for shared GitHub data collection utilities.

These utilities are used by both server.py (GitHub Actions) and github_agent.py (MCP).
"""

import pytest
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent_mcp_demo.utils.iteration_info import (
    get_current_iteration_info,
    _find_target_iteration,
    _format_iteration_response,
    _fallback_to_env_vars
)
from agent_mcp_demo.utils.github_members import (
    collect_members_and_emails,
    initialize_detail_structures
)
from agent_mcp_demo.utils.commit_metrics import collect_commit_metrics
from agent_mcp_demo.utils.issue_metrics import collect_issue_metrics
from agent_mcp_demo.utils.pr_metrics import collect_pr_metrics


class TestIterationInfo:
    """Tests for iteration_info.py utilities"""
    
    def test_find_target_iteration_current(self):
        """Test finding current iteration when not first day"""
        iterations = [
            {
                'title': 'Iteration 73',
                'startDate': '2026-01-26',
                'duration': 14
            },
            {
                'title': 'Iteration 74',
                'startDate': '2026-02-09',
                'duration': 14
            },
            {
                'title': 'Iteration 75',
                'startDate': '2026-02-23',
                'duration': 14
            }
        ]
        
        # Mock today as Feb 11, 2026 (within Iteration 74)
        with patch('agent_mcp_demo.utils.iteration_info.datetime') as mock_datetime:
            mock_now = Mock()
            mock_now.date.return_value = datetime(2026, 2, 11).date()
            mock_datetime.now.return_value = mock_now
            mock_datetime.fromisoformat = datetime.fromisoformat
            
            target = _find_target_iteration(iterations)
            
            assert target is not None
            assert target['title'] == 'Iteration 74'
    
    def test_find_target_iteration_first_day(self):
        """Test finding previous iteration on first day of new iteration"""
        iterations = [
            {
                'title': 'Iteration 73',
                'startDate': '2026-01-26',
                'duration': 14
            },
            {
                'title': 'Iteration 74',
                'startDate': '2026-02-09',
                'duration': 14
            }
        ]
        
        # Mock today as Feb 9, 2026 (first day of Iteration 74)
        with patch('agent_mcp_demo.utils.iteration_info.datetime') as mock_datetime:
            mock_now = Mock()
            mock_now.date.return_value = datetime(2026, 2, 9).date()
            mock_datetime.now.return_value = mock_now
            mock_datetime.fromisoformat = datetime.fromisoformat
            
            target = _find_target_iteration(iterations)
            
            assert target is not None
            assert target['title'] == 'Iteration 73'  # Previous iteration
    
    def test_format_iteration_response(self):
        """Test formatting iteration response"""
        iteration = {
            'title': 'Iteration 74',
            'startDate': '2026-02-09',
            'duration': 14
        }
        
        result = _format_iteration_response(iteration, 'test-org', 'test-project')
        
        assert result['name'] == 'Iteration 74'
        assert result['start_date'] == '2026-02-09'
        assert 'end_date' in result
        assert result['path'] == 'test-org/test-project'
    
    def test_fallback_to_env_vars(self, monkeypatch):
        """Test fallback to environment variables"""
        monkeypatch.setenv('GITHUB_ITERATION_START', '2026-02-09')
        monkeypatch.setenv('GITHUB_ITERATION_END', '2026-02-23')
        monkeypatch.setenv('GITHUB_ITERATION_NAME', 'Test Iteration')
        
        result = _fallback_to_env_vars('test-org', 'test-project')
        
        assert result is not None
        assert result['name'] == 'Test Iteration'
        assert result['start_date'] == '2026-02-09'
        assert result['end_date'] == '2026-02-23'
    
    def test_fallback_to_env_vars_missing(self, monkeypatch):
        """Test fallback when env vars are missing"""
        monkeypatch.delenv('GITHUB_ITERATION_START', raising=False)
        monkeypatch.delenv('GITHUB_ITERATION_END', raising=False)
        
        result = _fallback_to_env_vars('test-org', 'test-project')
        
        assert result is None


class TestGithubMembers:
    """Tests for github_members.py utilities"""
    
    def test_collect_members_and_emails(self):
        """Test collecting members and building email mapping"""
        # Mock Github and organization
        mock_github = Mock()
        mock_org = Mock()
        mock_github.get_organization.return_value = mock_org
        
        # Mock members
        mock_member1 = Mock()
        mock_member1.login = 'alice'
        
        mock_member2 = Mock()
        mock_member2.login = 'bob'
        
        mock_member3 = Mock()
        mock_member3.login = 'charlie'  # Will be excluded
        
        mock_org.get_members.return_value = [mock_member1, mock_member2, mock_member3]
        
        # Mock user details with emails
        mock_user1 = Mock()
        mock_user1.email = 'alice@example.com'
        mock_email1 = Mock()
        mock_email1.email = 'alice@users.noreply.github.com'
        mock_email1.verified = True
        mock_user1.get_emails.return_value = [mock_email1]
        
        mock_user2 = Mock()
        mock_user2.email = None
        mock_user2.get_emails.side_effect = Exception("No access")
        
        mock_github.get_user.side_effect = lambda login: mock_user1 if login == 'alice' else mock_user2
        
        # Call function
        member_stats, email_to_login, member_logins = collect_members_and_emails(
            mock_github, 'test-org', exclude_user_login='charlie'
        )
        
        # Verify results
        assert len(member_stats) == 2
        assert 'alice' in member_stats
        assert 'bob' in member_stats
        assert 'charlie' not in member_stats  # Excluded
        
        assert member_stats['alice']['commits'] == 0
        assert member_stats['alice']['assigned_issues'] == 0
        
        assert 'alice@example.com' in email_to_login
        assert email_to_login['alice@example.com'] == 'alice'
        assert 'alice@users.noreply.github.com' in email_to_login
        
        assert 'alice' in member_logins
        assert 'bob' in member_logins
        assert len(member_logins) == 2
    
    def test_initialize_detail_structures(self):
        """Test initializing detail tracking structures"""
        member_logins = ['alice', 'bob', 'charlie']
        
        details = initialize_detail_structures(member_logins)
        
        assert 'commit_details' in details
        assert 'assigned_issues' in details
        assert 'closed_issues' in details
        assert 'pr_created' in details
        assert 'pr_reviewed' in details
        assert 'pr_merged' in details
        assert 'pr_commented' in details
        
        # Each member should have empty list
        for login in member_logins:
            assert login in details['commit_details']
            assert details['commit_details'][login] == []
            assert login in details['pr_created']
            assert details['pr_created'][login] == []


class TestCommitMetrics:
    """Tests for commit_metrics.py utilities"""
    
    def test_collect_commit_metrics_basic(self):
        """Test basic commit metrics collection"""
        # Mock repository
        mock_repo = Mock()
        mock_repo.name = 'test-repo'
        
        # Mock branch
        mock_branch = Mock()
        mock_branch.name = 'main'
        mock_repo.get_branches.return_value = [mock_branch]
        
        # Mock commit
        mock_commit = Mock()
        mock_commit.sha = 'abc123def456'
        mock_commit_author = Mock()
        mock_commit_author.date = datetime(2026, 2, 10, 12, 0, 0, tzinfo=timezone.utc)
        mock_commit_author.email = 'alice@example.com'
        mock_commit.commit.author = mock_commit_author
        mock_commit.commit.message = 'Fix bug\n\nDetailed description'
        
        # Mock GitHub author
        mock_author = Mock()
        mock_author.login = 'alice'
        mock_commit.author = mock_author
        
        mock_repo.get_commits.return_value = [mock_commit]
        
        # Setup member stats
        member_stats = {'alice': {'commits': 0}}
        email_to_login = {'alice@example.com': 'alice'}
        commit_details = {'alice': []}
        
        # Call function
        total = collect_commit_metrics(
            mock_repo, member_stats, email_to_login, commit_details,
            iteration_info=None, exclude_user_login=None
        )
        
        # Verify results
        assert total == 1
        assert member_stats['alice']['commits'] == 1
        assert len(commit_details['alice']) == 1
        assert commit_details['alice'][0]['repo'] == 'test-repo'
        assert commit_details['alice'][0]['message'] == 'Fix bug'
        assert commit_details['alice'][0]['sha'] == 'abc123d'
    
    def test_collect_commit_metrics_with_iteration_filter(self):
        """Test commit collection with iteration date filtering"""
        mock_repo = Mock()
        mock_repo.name = 'test-repo'
        
        mock_branch = Mock()
        mock_branch.name = 'main'
        mock_repo.get_branches.return_value = [mock_branch]
        
        # Commit within iteration
        mock_commit_in = Mock()
        mock_commit_in.sha = 'commit_in'
        mock_commit_in.commit.author.date = datetime(2026, 2, 10, 12, 0, 0, tzinfo=timezone.utc)
        mock_commit_in.commit.message = 'In iteration'
        mock_commit_in.author.login = 'alice'
        
        # Commit outside iteration
        mock_commit_out = Mock()
        mock_commit_out.sha = 'commit_out'
        mock_commit_out.commit.author.date = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_commit_out.commit.message = 'Outside iteration'
        mock_commit_out.author.login = 'alice'
        
        mock_repo.get_commits.return_value = [mock_commit_in, mock_commit_out]
        
        member_stats = {'alice': {'commits': 0}}
        email_to_login = {}
        commit_details = {'alice': []}
        
        iteration_info = {
            'start_date': '2026-02-09T00:00:00',
            'end_date': '2026-02-23T00:00:00'
        }
        
        total = collect_commit_metrics(
            mock_repo, member_stats, email_to_login, commit_details,
            iteration_info=iteration_info
        )
        
        # Should only count the commit within iteration
        assert member_stats['alice']['commits'] == 1
        assert commit_details['alice'][0]['message'] == 'In iteration'
    
    def test_collect_commit_metrics_exclude_user(self):
        """Test excluding specific user from commit counting"""
        mock_repo = Mock()
        mock_repo.name = 'test-repo'
        
        mock_branch = Mock()
        mock_branch.name = 'main'
        mock_repo.get_branches.return_value = [mock_branch]
        
        mock_commit = Mock()
        mock_commit.sha = 'abc123'
        mock_commit.commit.author.date = datetime(2026, 2, 10, tzinfo=timezone.utc)
        mock_commit.commit.message = 'Commit by bot'
        mock_commit.author.login = 'bot-user'
        
        mock_repo.get_commits.return_value = [mock_commit]
        
        member_stats = {'bot-user': {'commits': 0}}
        commit_details = {'bot-user': []}
        
        total = collect_commit_metrics(
            mock_repo, member_stats, {}, commit_details,
            exclude_user_login='bot-user'
        )
        
        # Commit should be skipped
        assert member_stats['bot-user']['commits'] == 0
        assert len(commit_details['bot-user']) == 0


class TestIssueMetrics:
    """Tests for issue_metrics.py utilities"""
    
    def test_collect_issue_metrics_basic(self):
        """Test basic issue metrics collection"""
        mock_repo = Mock()
        mock_repo.name = 'test-repo'
        
        # Mock issue
        mock_issue = Mock()
        mock_issue.number = 123
        mock_issue.title = 'Test issue'
        mock_issue.state = 'open'
        mock_issue.created_at = datetime(2026, 2, 10, tzinfo=timezone.utc)
        mock_issue.closed_at = None
        mock_issue.pull_request = None
        
        # Mock assignee
        mock_assignee = Mock()
        mock_assignee.login = 'alice'
        mock_issue.assignees = [mock_assignee]
        
        mock_repo.get_issues.return_value = [mock_issue]
        
        member_stats = {'alice': {'assigned_issues': 0, 'closed_issues': 0}}
        assigned_issues = {'alice': []}
        closed_issues = {'alice': []}
        
        assigned, closed = collect_issue_metrics(
            mock_repo, member_stats, assigned_issues, closed_issues
        )
        
        assert assigned == 1
        assert closed == 0
        assert member_stats['alice']['assigned_issues'] == 1
        assert member_stats['alice']['closed_issues'] == 0
        assert len(assigned_issues['alice']) == 1
    
    def test_collect_issue_metrics_closed(self):
        """Test collecting closed issue metrics"""
        mock_repo = Mock()
        mock_repo.name = 'test-repo'
        
        mock_issue = Mock()
        mock_issue.number = 124
        mock_issue.title = 'Closed issue'
        mock_issue.state = 'closed'
        mock_issue.created_at = datetime(2026, 2, 10, tzinfo=timezone.utc)
        mock_issue.closed_at = datetime(2026, 2, 15, tzinfo=timezone.utc)
        mock_issue.pull_request = None
        
        mock_assignee = Mock()
        mock_assignee.login = 'bob'
        mock_issue.assignees = [mock_assignee]
        
        mock_repo.get_issues.return_value = [mock_issue]
        
        member_stats = {'bob': {'assigned_issues': 0, 'closed_issues': 0}}
        assigned_issues = {'bob': []}
        closed_issues = {'bob': []}
        
        assigned, closed = collect_issue_metrics(
            mock_repo, member_stats, assigned_issues, closed_issues
        )
        
        assert assigned == 1
        assert closed == 1
        assert member_stats['bob']['assigned_issues'] == 1
        assert member_stats['bob']['closed_issues'] == 1
    
    def test_collect_issue_metrics_skip_prs(self):
        """Test that pull requests are skipped"""
        mock_repo = Mock()
        mock_repo.name = 'test-repo'
        
        # Mock a PR (shows up in issues API)
        mock_pr = Mock()
        mock_pr.pull_request = Mock()  # Has pull_request attribute
        
        mock_repo.get_issues.return_value = [mock_pr]
        
        member_stats = {'alice': {'assigned_issues': 0}}
        assigned_issues = {'alice': []}
        closed_issues = {'alice': []}
        
        assigned, closed = collect_issue_metrics(
            mock_repo, member_stats, assigned_issues, closed_issues
        )
        
        # PR should be skipped
        assert assigned == 0
        assert closed == 0


class TestPRMetrics:
    """Tests for pr_metrics.py utilities"""
    
    def test_collect_pr_metrics_created(self):
        """Test collecting created PR metrics"""
        mock_repo = Mock()
        mock_repo.name = 'test-repo'
        
        # Mock PR
        mock_pr = Mock()
        mock_pr.number = 42
        mock_pr.title = 'Add feature'
        mock_pr.state = 'open'
        mock_pr.created_at = datetime(2026, 2, 10, tzinfo=timezone.utc)
        mock_pr.updated_at = datetime(2026, 2, 10, tzinfo=timezone.utc)
        mock_pr.merged_at = None
        mock_pr.user.login = 'alice'
        mock_pr.get_reviews.return_value = []
        mock_pr.get_comments.return_value = []
        mock_pr.get_review_comments.return_value = []
        
        mock_repo.get_pulls.return_value = [mock_pr]
        
        member_stats = {'alice': {'pr_created': 0, 'pr_reviewed': 0, 'pr_merged': 0, 'pr_commented': 0}}
        
        pr_created, pr_reviewed, pr_merged, pr_commented = collect_pr_metrics(
            mock_repo, member_stats, iteration_info=None
        )
        
        assert len(pr_created.get('alice', [])) == 1
        assert member_stats['alice']['pr_created'] == 1
    
    def test_collect_pr_metrics_with_iteration_filter(self):
        """Test PR collection with iteration date filtering"""
        mock_repo = Mock()
        mock_repo.name = 'test-repo'
        
        # PR within iteration
        mock_pr_in = Mock()
        mock_pr_in.number = 42
        mock_pr_in.title = 'In iteration'
        mock_pr_in.created_at = datetime(2026, 2, 10, tzinfo=timezone.utc)
        mock_pr_in.updated_at = datetime(2026, 2, 10, tzinfo=timezone.utc)
        mock_pr_in.user.login = 'alice'
        mock_pr_in.merged_at = None
        mock_pr_in.get_reviews.return_value = []
        mock_pr_in.get_comments.return_value = []
        mock_pr_in.get_review_comments.return_value = []
        
        # PR outside iteration
        mock_pr_out = Mock()
        mock_pr_out.number = 43
        mock_pr_out.title = 'Outside iteration'
        mock_pr_out.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        mock_pr_out.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        mock_pr_out.user.login = 'alice'
        mock_pr_out.merged_at = None
        mock_pr_out.get_reviews.return_value = []
        mock_pr_out.get_comments.return_value = []
        mock_pr_out.get_review_comments.return_value = []
        
        mock_repo.get_pulls.return_value = [mock_pr_in, mock_pr_out]
        
        member_stats = {'alice': {'pr_created': 0, 'pr_reviewed': 0, 'pr_merged': 0, 'pr_commented': 0}}
        
        iteration_info = {
            'start_date': '2026-02-09T00:00:00',
            'end_date': '2026-02-23T00:00:00'
        }
        
        pr_created, _, _, _ = collect_pr_metrics(
            mock_repo, member_stats, iteration_info=iteration_info
        )
        
        # Should only count PR within iteration
        alice_prs = pr_created.get('alice', [])
        assert len(alice_prs) == 1
        assert alice_prs[0]['title'] == 'In iteration'


class TestIntegration:
    """Integration tests for shared utilities"""
    
    def test_full_data_collection_workflow(self):
        """Test complete workflow using all utilities together"""
        # This tests that all utilities work together correctly
        
        # Mock Github instance
        mock_github = Mock()
        
        # Mock organization
        mock_org = Mock()
        mock_github.get_organization.return_value = mock_org
        
        # Mock members
        mock_member1 = Mock()
        mock_member1.login = 'alice'
        mock_org.get_members.return_value = [mock_member1]
        
        # Mock user with emails
        mock_user = Mock()
        mock_user.email = 'alice@example.com'
        mock_user.get_emails.return_value = []
        mock_github.get_user.return_value = mock_user
        
        # Step 1: Collect members
        member_stats, email_to_login, member_logins = collect_members_and_emails(
            mock_github, 'test-org'
        )
        
        assert 'alice' in member_stats
        assert 'alice@example.com' in email_to_login
        
        # Step 2: Initialize detail structures
        details = initialize_detail_structures(member_logins)
        
        assert 'alice' in details['commit_details']
        assert 'alice' in details['pr_created']
        
        # Step 3-5: Would collect commits, issues, PRs from repos
        # (Already tested individually above)
        
        # Verify all data structures are properly initialized
        assert member_stats['alice']['commits'] == 0
        assert member_stats['alice']['assigned_issues'] == 0
        assert member_stats['alice']['pr_created'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
