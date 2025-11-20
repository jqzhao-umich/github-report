# GitHub Pages Setup Guide

This guide will help you set up GitHub Pages for your repository to deploy the generated reports.

## Prerequisites

- You must have admin access to the repository
- The repository must be public (or you need GitHub Pro/Team for private repo GitHub Pages)

## Setup Steps

### Step 1: Enable GitHub Pages in Repository Settings

1. Go to your repository on GitHub: https://github.com/jqzhao-umich/github-report

2. Click on **Settings** (in the top navigation bar)

3. In the left sidebar, scroll down and click on **Pages** (under "Code and automation")

4. Under "Build and deployment":
   - **Source**: Select "GitHub Actions" from the dropdown
   - This allows the workflow to deploy pages automatically

5. Click **Save**

### Step 2: Configure Branch Protection (Optional but Recommended)

To ensure the GitHub Actions can push commits:

1. Go to **Settings** → **Branches**
2. If you have branch protection rules for `report-publish`, make sure:
   - "Allow force pushes" is disabled (for safety)
   - "Require status checks to pass before merging" is configured as needed
   - Add `github-actions[bot]` to the list of users who can bypass restrictions if needed

### Step 3: Verify Secrets and Variables

1. Go to **Settings** → **Secrets and variables** → **Actions**

2. Add the following **Repository Secrets**:
   - `GITHUB_TOKEN` - This is automatically provided by GitHub Actions (no need to add)
   - `ORG_NAME` - Your organization name (e.g., `WeMoAD-umich`)
     - Click "New repository secret"
     - Name: `ORG_NAME`
     - Value: `WeMoAD-umich`
     - Click "Add secret"

### Step 4: Update the Iteration Schedule

The repository has an iteration schedule file at `.github/iteration-schedule.yml` that needs to be updated:

```yaml
next_iteration_end_date: 2025-11-24  # Format: YYYY-MM-DD
next_iteration_name: Iteration 68    # Name of the iteration
last_updated: 2025-11-19T12:00:00-05:00
```

You can either:
- **Option A**: Update it manually by editing `.github/iteration-schedule.yml`
- **Option B**: Let the GitHub Action update it automatically after the first manual run

### Step 5: Test the Setup

#### Option A: Manual Workflow Trigger

1. Go to **Actions** tab in your repository
2. Click on "Generate Iteration Report" workflow
3. Click **Run workflow** → Select branch `report-publish` → **Run workflow**
4. Wait for the workflow to complete
5. Go to **Actions** → "Deploy Reports to GitHub Pages" (should trigger automatically)
6. Once deployed, visit: https://jqzhao-umich.github.io/github-report/

#### Option B: Wait for Scheduled Run

The workflow runs automatically every night at 11 PM Eastern Time. If today matches the iteration end date in the schedule, it will generate the report.

### Step 6: Verify Deployment

1. After the workflows complete, go to **Settings** → **Pages**
2. You should see: "Your site is live at https://jqzhao-umich.github.io/github-report/"
3. Click the URL to view your reports

## Workflow Overview

### Generate Iteration Report Workflow
- **Trigger**: Daily at 11 PM ET (checks both EDT and EST)
- **Action**: Generates report only on iteration end date
- **Output**: Commits to `docs/` and `reports/` folders

### Deploy Pages Workflow
- **Trigger**: When `docs/` folder changes on `report-publish` branch
- **Action**: Deploys content to GitHub Pages
- **URL**: https://jqzhao-umich.github.io/github-report/

## Troubleshooting

### Pages not deploying
- Check **Actions** tab for workflow errors
- Verify GitHub Pages source is set to "GitHub Actions"
- Ensure workflows have write permissions:
  - Go to **Settings** → **Actions** → **General**
  - Under "Workflow permissions", select "Read and write permissions"
  - Check "Allow GitHub Actions to create and approve pull requests"

### Workflow failing
- Check if `ORG_NAME` secret is set correctly
- Verify the `report-publish` branch exists
- Check workflow logs in the **Actions** tab for specific errors

### Reports not updating
- Verify the iteration end date in `.github/iteration-schedule.yml`
- Check that the date format is `YYYY-MM-DD`
- Review workflow logs to see if the date check passed

## Local Development

To test report generation locally:

```bash
# Set environment variables
export GITHUB_TOKEN="your-token"
export ORG_NAME="WeMoAD-umich"
export GITHUB_ITERATION_START="2025-11-10"
export GITHUB_ITERATION_END="2025-11-17T23:59:59Z"
export GITHUB_ITERATION_NAME="Iteration 67"

# Run with Docker Compose
docker compose up

# Or run directly
python -m uvicorn src.agent_mcp_demo.server:app --host 0.0.0.0 --port 8000
```

Visit http://localhost:8000 to view and generate reports.

## Next Steps

1. ✅ Enable GitHub Pages (Step 1)
2. ✅ Add repository secret for ORG_NAME (Step 3)
3. ✅ Update iteration schedule (Step 4)
4. ✅ Run workflow manually to test (Step 5)
5. ✅ Verify deployment (Step 6)

## Support

If you encounter issues, check:
- [GitHub Pages Documentation](https://docs.github.com/en/pages)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- Workflow logs in the Actions tab
