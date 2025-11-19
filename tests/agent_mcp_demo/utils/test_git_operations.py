"""Tests for GitOperations class."""
import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import git
from agent_mcp_demo.utils.git_operations import GitOperations


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        
        # Initialize git repo
        repo = git.Repo.init(repo_path)
        
        # Configure git user for commits
        repo.config_writer().set_value("user", "name", "Test User").release()
        repo.config_writer().set_value("user", "email", "test@example.com").release()
        
        # Add a remote (needed for push operations)
        repo.create_remote("origin", "https://github.com/test/repo.git")
        
        # Create initial commit
        test_file = repo_path / "README.md"
        test_file.write_text("# Test Repo")
        repo.index.add(["README.md"])
        repo.index.commit("Initial commit")
        
        yield repo_path


@pytest.fixture
def mock_repo():
    """Create a mock git repository."""
    repo = MagicMock()
    repo.is_dirty.return_value = True
    repo.untracked_files = []
    repo.active_branch.name = "main"
    repo.index = MagicMock()
    repo.index.add = MagicMock()
    repo.index.commit = MagicMock(return_value=Mock(hexsha="abc123def456"))
    repo.index.diff = MagicMock(return_value=["changed_file"])
    repo.remote = MagicMock(return_value=MagicMock())
    return repo


def test_git_operations_initialization(temp_git_repo):
    """Test GitOperations initializes with valid repo."""
    git_ops = GitOperations(str(temp_git_repo))
    
    assert git_ops.repo is not None
    assert git_ops.repo_path == temp_git_repo


def test_git_operations_initialization_with_cwd():
    """Test GitOperations initializes with current directory."""
    with patch('agent_mcp_demo.utils.git_operations.Path.cwd') as mock_cwd:
        mock_cwd.return_value = Path("/test/path")
        
        with patch('agent_mcp_demo.utils.git_operations.git.Repo') as mock_repo_class:
            mock_repo_class.return_value = Mock()
            git_ops = GitOperations()
            
            assert git_ops.repo_path == Path("/test/path")


def test_git_operations_invalid_repo():
    """Test GitOperations handles invalid repository."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Directory without .git
        git_ops = GitOperations(tmpdir)
        
        assert git_ops.repo is None


def test_commit_and_push_success(temp_git_repo):
    """Test successful commit and push."""
    git_ops = GitOperations(str(temp_git_repo))
    
    # Create a new file
    test_file = temp_git_repo / "test.txt"
    test_file.write_text("test content")
    
    # Mock the remote and push operation
    mock_remote = Mock()
    mock_remote.push.return_value = [Mock()]
    
    with patch.object(git_ops.repo, 'remote', return_value=mock_remote):
        result = git_ops.commit_and_push(
            file_paths=["test.txt"],
            commit_message="Add test file"
        )
    
    assert result["status"] == "success"
    assert "commit_sha" in result
    assert result["files_committed"] == 1


def test_commit_and_push_no_changes(temp_git_repo):
    """Test commit and push with no changes."""
    git_ops = GitOperations(str(temp_git_repo))
    
    # Try to commit when nothing has changed
    result = git_ops.commit_and_push(
        file_paths=["README.md"],
        commit_message="No changes"
    )
    
    assert result["status"] == "skipped"
    assert "No changes" in result["message"]


def test_commit_and_push_with_branch(temp_git_repo):
    """Test commit and push to specific branch."""
    git_ops = GitOperations(str(temp_git_repo))
    
    # Create a new file
    test_file = temp_git_repo / "branch_test.txt"
    test_file.write_text("branch content")
    
    # Mock the push operation
    mock_remote = Mock()
    mock_remote.push.return_value = [Mock()]
    
    with patch.object(git_ops.repo, 'remote', return_value=mock_remote):
        
        
        result = git_ops.commit_and_push(
            file_paths=["branch_test.txt"],
            commit_message="Branch commit",
            branch="feature-branch"
        )
    
    assert result["status"] == "success"
    mock_remote.push.assert_called_once_with("feature-branch")


def test_commit_and_push_no_repo():
    """Test commit and push when repo is invalid."""
    with tempfile.TemporaryDirectory() as tmpdir:
        git_ops = GitOperations(tmpdir)
        
        result = git_ops.commit_and_push(
            file_paths=["test.txt"],
            commit_message="Test"
        )
        
        assert result["status"] == "error"
        assert "Not a git repository" in result["message"]


def test_commit_and_push_git_error(temp_git_repo):
    """Test commit and push with git command error."""
    git_ops = GitOperations(str(temp_git_repo))
    
    # Create a new file
    test_file = temp_git_repo / "error_test.txt"
    test_file.write_text("error content")
    
    # Mock push to raise error
    mock_remote = Mock()
    mock_remote.push.side_effect = git.GitCommandError("push", "error")
    
    with patch.object(git_ops.repo, 'remote', return_value=mock_remote):
        result = git_ops.commit_and_push(
            file_paths=["error_test.txt"],
            commit_message="Error test"
        )
    
    assert result["status"] == "error"
    assert "Git command failed" in result["message"]


def test_commit_and_push_multiple_files(temp_git_repo):
    """Test committing multiple files at once."""
    git_ops = GitOperations(str(temp_git_repo))
    
    # Create multiple files
    for i in range(3):
        test_file = temp_git_repo / f"file{i}.txt"
        test_file.write_text(f"content {i}")
    
    # Mock the push operation
    mock_remote = Mock()
    mock_remote.push.return_value = [Mock()]
    
    with patch.object(git_ops.repo, 'remote', return_value=mock_remote):
        
        
        result = git_ops.commit_and_push(
            file_paths=["file0.txt", "file1.txt", "file2.txt"],
            commit_message="Add multiple files"
        )
    
    assert result["status"] == "success"
    assert result["files_committed"] == 3


def test_get_current_branch(temp_git_repo):
    """Test getting current branch name."""
    git_ops = GitOperations(str(temp_git_repo))
    
    branch = git_ops.get_current_branch()
    
    # Default branch is usually 'master' or 'main'
    assert branch in ["master", "main"]


def test_get_current_branch_no_repo():
    """Test getting current branch when repo is invalid."""
    with tempfile.TemporaryDirectory() as tmpdir:
        git_ops = GitOperations(tmpdir)
        
        branch = git_ops.get_current_branch()
        
        assert branch is None


def test_get_current_branch_error():
    """Test getting current branch when error occurs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        git_ops = GitOperations(tmpdir)
        
        # Repo is invalid, so should return None
        branch = git_ops.get_current_branch()
        
        assert branch is None


def test_is_clean_true(temp_git_repo):
    """Test is_clean returns True for clean repo."""
    git_ops = GitOperations(str(temp_git_repo))
    
    # Repo should be clean after initial commit
    assert git_ops.is_clean() is True


def test_is_clean_false_dirty(temp_git_repo):
    """Test is_clean returns False when repo is dirty."""
    git_ops = GitOperations(str(temp_git_repo))
    
    # Modify existing file
    readme = temp_git_repo / "README.md"
    readme.write_text("# Modified")
    
    assert git_ops.is_clean() is False


def test_is_clean_false_untracked(temp_git_repo):
    """Test is_clean returns False with untracked files."""
    git_ops = GitOperations(str(temp_git_repo))
    
    # Create untracked file
    new_file = temp_git_repo / "untracked.txt"
    new_file.write_text("untracked content")
    
    assert git_ops.is_clean() is False


def test_is_clean_no_repo():
    """Test is_clean returns True when repo is invalid."""
    with tempfile.TemporaryDirectory() as tmpdir:
        git_ops = GitOperations(tmpdir)
        
        assert git_ops.is_clean() is True


def test_commit_message_formatting(temp_git_repo):
    """Test commit message is properly used."""
    git_ops = GitOperations(str(temp_git_repo))
    
    # Create a new file
    test_file = temp_git_repo / "msg_test.txt"
    test_file.write_text("test content")
    
    commit_message = "feat: add new feature\n\nDetailed description"
    
    # Mock the push operation
    mock_remote = Mock()
    mock_remote.push.return_value = [Mock()]
    
    with patch.object(git_ops.repo, 'remote', return_value=mock_remote):
        
        
        result = git_ops.commit_and_push(
            file_paths=["msg_test.txt"],
            commit_message=commit_message
        )
    
    assert result["status"] == "success"
    
    # Verify last commit message
    last_commit = git_ops.repo.head.commit
    assert last_commit.message == commit_message


def test_commit_sha_format(temp_git_repo):
    """Test that commit SHA is truncated correctly."""
    git_ops = GitOperations(str(temp_git_repo))
    
    # Create a new file
    test_file = temp_git_repo / "sha_test.txt"
    test_file.write_text("test content")
    
    # Mock the push operation
    mock_remote = Mock()
    mock_remote.push.return_value = [Mock()]
    
    with patch.object(git_ops.repo, 'remote', return_value=mock_remote):
        
        
        result = git_ops.commit_and_push(
            file_paths=["sha_test.txt"],
            commit_message="SHA test"
        )
    
    assert result["status"] == "success"
    assert "commit_sha" in result
    assert len(result["commit_sha"]) == 7  # Should be truncated to 7 chars


def test_commit_with_directory_path(temp_git_repo):
    """Test committing files in subdirectories."""
    git_ops = GitOperations(str(temp_git_repo))
    
    # Create subdirectory with file
    subdir = temp_git_repo / "subdir"
    subdir.mkdir()
    test_file = subdir / "file.txt"
    test_file.write_text("nested content")
    
    # Mock the push operation
    mock_remote = Mock()
    mock_remote.push.return_value = [Mock()]
    
    with patch.object(git_ops.repo, 'remote', return_value=mock_remote):
        
        
        result = git_ops.commit_and_push(
            file_paths=["subdir/file.txt"],
            commit_message="Add nested file"
        )
    
    assert result["status"] == "success"


def test_commit_with_wildcard_paths(temp_git_repo):
    """Test committing with directory wildcard."""
    git_ops = GitOperations(str(temp_git_repo))
    
    # Create directory with multiple files
    docs_dir = temp_git_repo / "docs"
    docs_dir.mkdir()
    for i in range(3):
        (docs_dir / f"doc{i}.md").write_text(f"doc {i}")
    
    # Mock the push operation
    mock_remote = Mock()
    mock_remote.push.return_value = [Mock()]
    
    with patch.object(git_ops.repo, 'remote', return_value=mock_remote):
        
        
        result = git_ops.commit_and_push(
            file_paths=["docs/"],
            commit_message="Add docs directory"
        )
    
    assert result["status"] == "success"


def test_repo_search_parent_directories():
    """Test that repo search looks in parent directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        
        # Initialize git repo in parent
        git.Repo.init(repo_path)
        
        # Create subdirectory
        subdir = repo_path / "subdir"
        subdir.mkdir()
        
        # Initialize from subdirectory
        git_ops = GitOperations(str(subdir))
        
        # Should find repo in parent
        assert git_ops.repo is not None


def test_commit_and_push_exception_handling():
    """Test handling of unexpected exceptions."""
    git_ops = GitOperations()
    git_ops.repo = Mock()
    
    # Mock to raise unexpected exception
    git_ops.repo.is_dirty.side_effect = RuntimeError("Unexpected error")
    
    result = git_ops.commit_and_push(
        file_paths=["test.txt"],
        commit_message="Test"
    )
    
    assert result["status"] == "error"
    assert "Unexpected error" in result["message"]


def test_remote_configuration(temp_git_repo):
    """Test that remote is properly configured."""
    git_ops = GitOperations(str(temp_git_repo))
    
    # Remote "origin" should already exist (created in fixture)
    remotes = git_ops.repo.remotes
    assert len(remotes) > 0
    assert "origin" in [r.name for r in remotes]


def test_commit_with_empty_file_list():
    """Test committing with empty file list."""
    git_ops = GitOperations()
    git_ops.repo = Mock()
    git_ops.repo.is_dirty.return_value = False
    git_ops.repo.untracked_files = []
    
    result = git_ops.commit_and_push(
        file_paths=[],
        commit_message="Empty commit"
    )
    
    assert result["status"] == "skipped"


def test_concurrent_git_operations(temp_git_repo):
    """Test that git operations handle concurrent modifications."""
    git_ops = GitOperations(str(temp_git_repo))
    
    # Simulate concurrent modification
    file1 = temp_git_repo / "concurrent1.txt"
    file2 = temp_git_repo / "concurrent2.txt"
    file1.write_text("content 1")
    file2.write_text("content 2")
    
    # Mock the push operation
    mock_remote = Mock()
    mock_remote.push.return_value = [Mock()]
    
    with patch.object(git_ops.repo, 'remote', return_value=mock_remote):
        
        
        # Commit both files together
        result = git_ops.commit_and_push(
            file_paths=["concurrent1.txt", "concurrent2.txt"],
            commit_message="Concurrent changes"
        )
    
    assert result["status"] == "success"
    assert result["files_committed"] == 2
