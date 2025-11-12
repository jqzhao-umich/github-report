"""Git operations for automatic commit and push."""
import os
from pathlib import Path
from typing import Optional, Dict
import git


class GitOperations:
    def __init__(self, repo_path: Optional[str] = None):
        """Initialize git operations.
        
        Args:
            repo_path: Path to the git repository. If None, uses current directory.
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        try:
            self.repo = git.Repo(self.repo_path, search_parent_directories=True)
        except git.InvalidGitRepositoryError:
            print(f"Warning: {self.repo_path} is not a git repository")
            self.repo = None
    
    def commit_and_push(self, 
                       file_paths: list[str],
                       commit_message: str,
                       branch: Optional[str] = None) -> Dict[str, any]:
        """Commit and push files to remote repository.
        
        Args:
            file_paths: List of file paths to commit (relative to repo root)
            commit_message: Commit message
            branch: Branch to push to. If None, uses current branch.
            
        Returns:
            Dict with status and message
        """
        if not self.repo:
            return {
                "status": "error",
                "message": "Not a git repository"
            }
        
        try:
            # Check if there are any changes
            if not self.repo.is_dirty(path=file_paths) and not self.repo.untracked_files:
                return {
                    "status": "skipped",
                    "message": "No changes to commit"
                }
            
            # Stage files
            self.repo.index.add(file_paths)
            
            # Check if there are staged changes
            if not self.repo.index.diff("HEAD"):
                return {
                    "status": "skipped",
                    "message": "No changes staged for commit"
                }
            
            # Commit
            commit = self.repo.index.commit(commit_message)
            
            # Push to remote
            if branch is None:
                branch = self.repo.active_branch.name
            
            origin = self.repo.remote(name='origin')
            push_info = origin.push(branch)
            
            return {
                "status": "success",
                "message": f"Committed and pushed to {branch}",
                "commit_sha": commit.hexsha[:7],
                "files_committed": len(file_paths)
            }
            
        except git.GitCommandError as e:
            return {
                "status": "error",
                "message": f"Git command failed: {str(e)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}"
            }
    
    def get_current_branch(self) -> Optional[str]:
        """Get the name of the current branch."""
        if not self.repo:
            return None
        try:
            return self.repo.active_branch.name
        except:
            return None
    
    def is_clean(self) -> bool:
        """Check if the working directory is clean."""
        if not self.repo:
            return True
        return not self.repo.is_dirty() and not self.repo.untracked_files
