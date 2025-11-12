# Deployment Guide

## Quick Start

### Development Mode
```bash
./start-dev.sh
```

This will:
- Build container with your current user's UID/GID
- Mount source code for live reload
- Start the application

Access:
- **Dashboard**: http://localhost:8000/github-report
- **API Docs**: http://localhost:8000/docs

### Production Mode
```bash
./start-prod.sh
```

This will:
- Build container with fixed UID (1000) for consistency
- Use production-optimized settings
- Exclude source code mount (baked into image)

---

## Architecture Overview

### Key Features Implemented

#### 1. **Auto-Scheduled Reports** ✅
- APScheduler checks hourly if iteration end date has passed
- Automatically generates and publishes reports at iteration end
- Configurable via `GITHUB_ITERATION_END` environment variable

#### 2. **Duplicate Detection** ✅
- Checks if report already exists for current iteration before generating
- Prevents redundant reports within same iteration
- Can be overridden with `force=true` query parameter

#### 3. **Human-Readable Filenames** ✅
- Format: `2025-11-12_04-58-PM_OrgName_iteration-name.html`
- Instead of: `20251112_165831_OrgName_iteration-name.html`
- Timezone-aware (respects `TZ` environment variable)

#### 4. **Git Auto-Commit/Push** ⚠️ **Partial**
- **Status**: Implemented but requires manual git configuration
- **Issue**: Docker mount permissions prevent GitPython from modifying git objects
- **Workaround**: See "Git Operations" section below

---

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Required
GITHUB_TOKEN=ghp_your_token_here
GITHUB_ORG_NAME=your-org-name

# Optional - for automatic iteration tracking
GITHUB_ITERATION_START=2025-11-03
GITHUB_ITERATION_END=2025-11-17T00:00:00
GITHUB_ITERATION_NAME=Iteration 67

# Optional - timezone (default: America/New_York)
TZ=America/New_York
```

### Manual Publish

Trigger a report manually:
```bash
curl -X POST http://localhost:8000/api/reports/publish
```

Force publish (bypass duplicate check):
```bash
curl -X POST "http://localhost:8000/api/reports/publish?force=true"
```

---

## Git Operations

### Current Limitation

Git auto-commit/push from within the Docker container encounters permission issues when trying to create new git objects. This is because:
1. The `.git` directory is mounted from the host
2. Git objects are created with host user permissions
3. Container user (even with matching UID) cannot modify existing git objects due to macOS filesystem ACLs

### Solution Options

**Option A: Host-side Git Operations** (Recommended for Development)

Create a simple script to commit published reports:

```bash
#!/bin/bash
# commit-reports.sh

git add docs/ reports/
if ! git diff --cached --quiet; then
    git commit -m "Auto-publish report $(date +'%Y-%m-%d %H:%M')"
    git push origin $(git branch --show-current)
    echo "✅ Reports committed and pushed"
else
    echo "ℹ️  No changes to commit"
fi
```

Run this script after publishing:
```bash
./commit-reports.sh
```

Or set up a cron job:
```bash
# Run every hour to check for new reports
0 * * * * cd /path/to/project && ./commit-reports.sh
```

**Option B: GitHub Actions** (Recommended for Production)

Create `.github/workflows/publish-reports.yml`:

```yaml
name: Auto-commit Reports

on:
  schedule:
    - cron: '0 * * * *'  # Every hour
  workflow_dispatch:  # Manual trigger

jobs:
  commit-reports:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Check for new reports
        run: |
          if [ -n "$(git status --porcelain docs/ reports/)" ]; then
            git config user.name "GitHub Actions"
            git config user.email "actions@github.com"
            git add docs/ reports/
            git commit -m "Auto-publish report $(date +'%Y-%m-%d %H:%M')"
            git push
          fi
```

**Option C: Fix Container Permissions** (Advanced)

If you need git operations inside Docker:

1. Run container as root temporarily
2. Fix .git permissions before switching to app user
3. This is complex and not recommended for development

---

## Development vs Production

### Development
- Uses your host UID/GID (502:20 on Mac)
- Mounts source code for live reload
- Includes .git for potential git operations
- Easier debugging and iteration

### Production
- Uses fixed UID:GID (1000:1000)
- Source code baked into image
- More secure and consistent
- Use GitHub Actions or external cron for git operations

---

## Troubleshooting

### Container won't start
```bash
docker compose logs
```

### Reports not generating
Check environment variables:
```bash
docker exec copilot-aidevday-2025-github-report-app-1 env | grep GITHUB
```

### Scheduler not running
Check logs for scheduler initialization:
```bash
docker logs copilot-aidevday-2025-github-report-app-1 | grep -i scheduler
```

### Git operations failing
Expected in Docker - use host-side script or GitHub Actions (see "Git Operations" section)

---

## Testing

### Test Manual Publish
```bash
curl -X POST http://localhost:8000/api/reports/publish?force=true
sleep 10
ls -lt docs/*.html | head -3
```

### Test Scheduler
Check logs:
```bash
docker logs copilot-aidevday-2025-github-report-app-1 | grep "Checking for iteration end"
```

### Test Duplicate Detection
```bash
# Publish twice
curl -X POST http://localhost:8000/api/reports/publish
curl -X POST http://localhost:8000/api/reports/publish

# Second should show "skipped" status in logs
docker logs copilot-aidevday-2025-github-report-app-1 | grep "already exists"
```

---

## Production Deployment Checklist

- [ ] Set all required environment variables in `.env`
- [ ] Set up GitHub Actions workflow for auto-commit (or equivalent)
- [ ] Configure iteration dates for automatic scheduling
- [ ] Test manual publish endpoint
- [ ] Verify scheduler is running (check logs)
- [ ] Set up monitoring/alerting for container health
- [ ] Configure backup strategy for reports
- [ ] Document runbook for ops team

---

## Architecture Decisions

### Why APScheduler instead of Cron?
- Python-native solution
- Easier to test and debug
- Better integration with FastAPI
- More flexible scheduling options

### Why GitPython instead of subprocess?
- More Pythonic and testable
- Better error handling
- Type-safe git operations
- Though subprocess would avoid the permission issues

### Why not fix Docker git permissions?
- macOS ACLs make this very complex
- Not worth the effort for development
- Production should use external git automation anyway (GitHub Actions)
- Keeps container simple and focused

---

## Next Steps

To make this production-ready:

1. **Set up GitHub Actions** for auto-commit
2. **Add monitoring** (healthchecks, alerts)
3. **Configure secrets management** (not .env file)
4. **Add rate limiting** on publish endpoint
5. **Implement report retention policy**
6. **Add authentication** if exposing publicly
7. **Set up CI/CD pipeline** for deployments

