# Repository Migration Guide

## Migrating from copilot-aidevday-2025 to github-report

This guide walks you through creating a new `github-report` repository and migrating the codebase.

### Option 1: Create New Repository on GitHub (Recommended)

1. **Create the new repository on GitHub:**
   - Go to https://github.com/new
   - Repository name: `github-report`
   - Description: "GitHub organization report generator with automated scheduling and publishing"
   - Choose: Public or Private
   - **Do NOT initialize** with README, .gitignore, or license
   - Click "Create repository"

2. **Update the remote in your local repository:**
   ```bash
   cd /Users/jqzhao/projects/copilot-aidevday-2025
   
   # Add the new remote
   git remote add new-origin https://github.com/jqzhao-umich/github-report.git
   
   # Push all branches to the new repository
   git push new-origin --all
   
   # Push all tags
   git push new-origin --tags
   
   # Remove old remote and rename new one
   git remote remove origin
   git remote rename new-origin origin
   ```

3. **Rename the local directory:**
   ```bash
   cd /Users/jqzhao/projects
   mv copilot-aidevday-2025 github-report
   cd github-report
   ```

4. **Verify everything works:**
   ```bash
   # Check remote
   git remote -v
   
   # Should show:
   # origin  https://github.com/jqzhao-umich/github-report.git (fetch)
   # origin  https://github.com/jqzhao-umich/github-report.git (push)
   
   # Test Docker build
   docker compose build
   
   # Start the application
   docker compose up -d
   
   # Check it works
   curl http://localhost:8000/github-report
   
   # Stop the application
   docker compose down
   ```

### Option 2: Rename Existing Repository on GitHub

If you want to rename the existing repository instead:

1. **On GitHub:**
   - Go to https://github.com/jqzhao-umich/copilot-aidevday-2025
   - Click "Settings"
   - Scroll to "Repository name"
   - Change to: `github-report`
   - Click "Rename"

2. **Update your local repository:**
   ```bash
   cd /Users/jqzhao/projects/copilot-aidevday-2025
   
   # Update remote URL
   git remote set-url origin https://github.com/jqzhao-umich/github-report.git
   
   # Rename local directory
   cd /Users/jqzhao/projects
   mv copilot-aidevday-2025 github-report
   cd github-report
   ```

3. **Verify:**
   ```bash
   git remote -v
   git fetch
   git status
   ```

### Post-Migration Checklist

After migration, update any references in:

- [ ] Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json`)
  - Update path from `/Users/jqzhao/projects/copilot-aidevday-2025` to `/Users/jqzhao/projects/github-report`

- [ ] GitHub Actions workflows (if any in `.github/workflows/`)
  - Check for hardcoded repository names

- [ ] Any external documentation or bookmarks

- [ ] Team members' local clones (they should run):
  ```bash
  git remote set-url origin https://github.com/jqzhao-umich/github-report.git
  ```

### Verification Commands

Run these to ensure everything works:

```bash
# 1. Check git configuration
git remote -v
git branch -a

# 2. Test Docker
docker compose build
docker compose up -d
docker compose ps
curl http://localhost:8000/github-report
docker compose down

# 3. Run tests
docker compose up -d
docker compose exec github-report-app python -m pytest -v
docker compose down

# 4. Verify file paths in scripts
./start-dev.sh  # Should work without changes
```

### Cleanup Old Repository (Optional)

If you chose Option 1 (created new repo), you can archive or delete the old repository:

1. **Archive** (recommended - preserves history):
   - Go to https://github.com/jqzhao-umich/copilot-aidevday-2025
   - Settings → Archive this repository

2. **Delete** (permanent):
   - Go to https://github.com/jqzhao-umich/copilot-aidevday-2025
   - Settings → Delete this repository

### Notes

- All commits, branches, and tags are preserved
- GitHub will automatically redirect traffic from the old URL to the new one (if you renamed)
- Docker container names will now use `github-report` prefix
- The application functionality remains unchanged
- All 92 tests should continue to pass

### Need Help?

If you encounter issues:

1. Check git remote configuration: `git remote -v`
2. Verify Docker configuration: `docker compose config`
3. Check application logs: `docker compose logs -f`
4. Ensure `.env` file exists with correct variables
