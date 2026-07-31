# mcp2 canary — testing the mcp 2.0 port before merging

This document explains how to verify the `mcp2` branch (the port from `mcp` 1.x to 2.0) is behaving correctly in production-like conditions, without publishing anything to the live GitHub Pages site.

## What's set up

1. **`.github/workflows/mcp2-canary.yml`** — runs on every push to `mcp2` and on manual dispatch. Installs, imports, runs pytest, and produces a dry-run report as an artifact. **Never commits or publishes.**
2. **`mcp2-canary` job inside `.github/workflows/generate-iteration-report.yml`** — runs on the same daily 5:00 UTC cron as the production job, but checks out `mcp2` instead of `main` and produces a dry-run report. `continue-on-error: true` so a canary failure never blocks the production job. This job only exists once `main` has the workflow change; see the "Bootstrapping" section below.
3. **`dry_run` input on `generate-iteration-report.yml`** — a manual dispatch can now run the entire iteration-boundary path (report → publish → schedule update) against any ref (defaulting to `main`) with commits and pushes disabled. The generated artifacts are uploaded to the run so you can diff them against the live site.

## The three checks, in order of cost

### 1. Import smoke — 90% of what could go wrong

The failure that originally motivated the port was an `AttributeError` at module load. Every canary run exercises this exact import path. **If the "Import smoke test" step is green, the port's basic compatibility with mcp 2.0 holds.**

- **Where:** Actions → `mcp2 canary (dry run)` → the latest run.
- **What "healthy" looks like:** All checkmarks; the "Install dependencies" step prints `mcp dist version: 2.x.y`.
- **Escalate if:** The step goes red with an `ImportError` or `AttributeError` — that's the port breaking against a newer patch release of `mcp`.

### 2. Behavioral parity — "runs but produces wrong output"

Each canary run uploads `mcp2-report.md` as an artifact. Compare that against a `main` run from the same day.

```bash
# 1. Grab the latest canary artifact from the mcp2 branch
gh run list --workflow="mcp2 canary (dry run)" --branch=mcp2 --limit=1 --json databaseId --jq '.[0].databaseId' \
  | xargs -I {} gh run download {} --name "mcp2-canary-report-*" -D /tmp/mcp2

# 2. Trigger a same-day dry-run against main and grab its artifact
gh workflow run generate-iteration-report.yml --ref main -f dry_run=true
# Wait ~2 minutes, then:
gh run list --workflow="Generate Iteration Report" --branch=main --limit=1 --json databaseId --jq '.[0].databaseId' \
  | xargs -I {} gh run download {} -D /tmp/main-dryrun

# 3. Diff the two reports
diff /tmp/mcp2/mcp2-report.md /tmp/main-dryrun/reports/*.md
```

- **What "healthy" looks like:** The diff is empty, or differs only in timestamps and generation-time lines. The commit / issue / PR counts are identical.
- **Escalate if:** The mcp2 report has zero commits or is missing a member. That means the mcp 2.0 types are round-tripping data differently than expected — port bug.
- **Cheaper alternative (no download):** open the mcp2 canary run's summary panel — the "Dry-run report generation" step prints the first 20 lines of the report inline, so you can eyeball the header/`Total commits processed` value without downloading.

You can also diff against the currently-live Pages site rather than a same-day main dry-run:

```bash
# Fetch the most recent published report from Pages
curl -sS https://<your-org>.github.io/<your-repo>/reports/iteration-XX.html > /tmp/live.html
# The dry-run report is plain text, so extract text from the HTML for a rough comparison:
python -c "from html.parser import HTMLParser; ..." # or use pandoc / your tool of choice
```

Comparing against Pages is noisier (HTML vs. markdown) but useful once a week when the last published report is fresh.

### 3. Real end-to-end iteration boundary — highest confidence, but rare

The port only *really* matters on the ~2-week cadence when a real iteration boundary hits and the workflow commits, updates the schedule YAML, and pushes. To exercise that path on `mcp2` without waiting or polluting anything:

**Option A: Full dry-run against mcp2 (safest, recommended)**

```bash
gh workflow run generate-iteration-report.yml \
  --ref main \
  -f ref=mcp2 \
  -f dry_run=true
```

This runs the workflow *definition* from `main` (so it has the `dry_run` gate you added), but checks out and executes the code on `mcp2`. Because `dry_run=true`, it:

- Runs the "Check if today is scheduled report date" step — since this is a `workflow_dispatch`, `should_generate=true` regardless of the calendar.
- Generates the report using `mcp2` code.
- Skips "Update schedule for next iteration" (writes `.github/iteration-schedule.yml`).
- Skips "Commit and push reports".
- Uploads `docs/`, `reports/`, and `.github/iteration-schedule.yml` as the `iteration-report-dryrun-*` artifact.

After the run:

```bash
# Download the dry-run artifact
gh run download $(gh run list --workflow="Generate Iteration Report" --limit=1 --json databaseId --jq '.[0].databaseId') \
  -n "iteration-report-dryrun-*" -D /tmp/mcp2-e2e

# Compare docs/ against what the live Pages site currently shows
ls /tmp/mcp2-e2e/docs/
diff -r /tmp/mcp2-e2e/docs/ ./docs/    # against your local main checkout

# Compare the new iteration-schedule.yml against the current one
diff /tmp/mcp2-e2e/.github/iteration-schedule.yml ./.github/iteration-schedule.yml
```

**What "healthy" looks like:**
- `docs/` in the artifact contains a fresh iteration report HTML file with the same shape as the last real one on Pages.
- `iteration-schedule.yml` has advanced `next_iteration_start_date` and `next_iteration_name` by one iteration (14 days later, name incremented).
- No stack traces in the workflow log.

**Escalate if:**
- The artifact is missing `docs/` or `reports/` entirely.
- `iteration-schedule.yml` in the artifact is identical to the current one (schedule-update script didn't run correctly against mcp2 code).
- The workflow log shows an exception during publishing.

**Option B: Real publish from mcp2 (only when you're ready to trust it)**

Same command without `dry_run`:

```bash
gh workflow run generate-iteration-report.yml --ref main -f ref=mcp2
```

This commits and pushes to `mcp2` (not `main` — `actions/checkout` was on `mcp2`, so the push target is `mcp2`). The Pages deployment workflow only fires on pushes to `main`, so this still does not deploy — but it does write into `mcp2/docs/`, which is a good staging-ground before merge.

**Never** run this against `main` with `mcp2` code until you're comfortable merging.

## Bootstrapping — before the canary starts working

The daily `mcp2-canary` job is defined in `.github/workflows/generate-iteration-report.yml` and only runs from `main` (that's where `schedule:` triggers fire). So you have two options:

1. **Recommended:** cherry-pick just the workflow changes from `mcp2` onto `main` and merge that as a small, safe PR. Since the workflow change only *adds* a job that runs against `mcp2` and is guarded by `continue-on-error: true`, it's zero risk to production. Once merged, the daily canary starts running automatically.
2. **Alternative:** rely on the `mcp2-canary.yml` workflow (which lives on `mcp2` and fires on push to `mcp2` + manual dispatch). This gives you per-commit signal but no *daily* automatic exercise unless you manually dispatch it.

The daily cron matters because the production issue that motivated the port was a scheduled run breaking overnight. If you want the same coverage on mcp2, do option 1.

## What to actually watch each day (5-second check)

1. Open Actions → filter for `mcp2-canary` job on the latest scheduled run.
2. Verify: green status; the summary panel shows a report with plausible byte/line counts (compare mentally against the last few days).
3. If red for two consecutive days, open the failing step's log — most likely an mcp SDK patch release changed a type or method again, or the org's GitHub state changed in a way that surfaces a port bug.

## Merge checklist

Ready to merge `mcp2` into `main` when:

- Import smoke has been green for at least one full iteration cycle (~14 days).
- At least one behavioral-parity diff has come out clean (empty / timestamp-only).
- At least one full-path dry run (Option A above) has produced an artifact whose `docs/` and `iteration-schedule.yml` match expectations.
- Optionally: one Option B run has committed to `mcp2` and the resulting HTML renders the same as the currently-live Pages site.

Once merged:

- Remove `.github/workflows/mcp2-canary.yml` (dead code).
- Remove the `mcp2-canary` job block from `generate-iteration-report.yml` (dead code — `mcp2` branch will be gone or stale).
- Keep the `dry_run` `workflow_dispatch` input — it's useful for future dependency-upgrade rehearsals.
