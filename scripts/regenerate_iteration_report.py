#!/usr/bin/env python3
"""Regenerate a specific iteration's report and replace any stale
no-iteration.html for that publish window.

Motivation
----------
When `get_current_iteration_info()` failed to find the ProjectV2 (e.g. by
title before the fix in dfa561c), the scheduled report fell into the
"no iteration information available" branch of `github_report_api()` and
emitted an all-time totals report under a `*_no-iteration.html` filename.
This script rebuilds one such report against the correct iteration
window without disturbing the daily-workflow schedule state.

Usage
-----
    python scripts/regenerate_iteration_report.py "Iteration 87"
    python scripts/regenerate_iteration_report.py "Iteration 87" --dry-run

Reads GITHUB_TOKEN, GITHUB_ORG_NAME, GITHUB_PROJECT_NAME, and
GITHUB_PROJECT_NUMBER from the environment (or a project-root `.env`).
Only touches `docs/`, `reports/`, and `docs/reports.json`. Does NOT
modify `.github/iteration-schedule.yml`, so the next automated run for
Iteration 88+ still follows its normal cadence.
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _fetch_iteration_by_title(token: str, org_name: str, project_number: int,
                              iteration_title: str) -> dict | None:
    """Return the ProjectV2 iteration record whose title matches, or None.

    Searches both active and completed iterations (an iteration that has
    already ended, like a several-week-old one, may live in
    `completedIterations`).
    """
    headers = {"Authorization": f"Bearer {token}"}
    query = """
    query($org: String!, $number: Int!) {
      organization(login: $org) {
        projectV2(number: $number) {
          title
          fields(first: 50) {
            nodes {
              ... on ProjectV2IterationField {
                name
                configuration {
                  iterations           { title startDate duration }
                  completedIterations  { title startDate duration }
                }
              }
            }
          }
        }
      }
    }
    """
    response = requests.post(
        "https://api.github.com/graphql",
        headers=headers,
        json={"query": query, "variables": {"org": org_name, "number": project_number}},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if "errors" in payload:
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")

    project = payload.get("data", {}).get("organization", {}).get("projectV2")
    if not project:
        raise RuntimeError(
            f"Project #{project_number} not found in organization '{org_name}'"
        )
    print(f"Project resolved: {project.get('title')!r}")

    for field in project["fields"]["nodes"] or []:
        cfg = (field or {}).get("configuration")
        if not cfg:
            continue
        for pool_name in ("iterations", "completedIterations"):
            for it in cfg.get(pool_name) or []:
                if it.get("title") == iteration_title:
                    print(f"Found in {pool_name}: {it}")
                    return it
    return None


def _iteration_to_info(iteration: dict, org_name: str, project_name: str) -> dict:
    """Match the shape returned by `iteration_info._format_iteration_response`."""
    start_date = iteration["startDate"]
    duration = iteration["duration"]
    start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
    end_dt = start_dt + timedelta(days=duration)
    return {
        "name": iteration["title"],
        "start_date": start_date,
        "end_date": end_dt.isoformat(),
        "path": f"{org_name}/{project_name}",
    }


def _prune_no_iteration_entries(docs_dir: Path, reports_dir: Path,
                                org_name: str) -> None:
    """Delete any HTML/MD files and reports.json entries whose iteration is
    null/empty for this organization — the fingerprint of a failed run."""
    reports_json = docs_dir / "reports.json"
    if not reports_json.exists():
        return

    with open(reports_json) as f:
        reports = json.load(f)

    survivors = []
    stale_paths = []
    for entry in reports:
        is_stale = (
            entry.get("org_name") == org_name
            and entry.get("iteration_name") in (None, "", "N/A")
        )
        if is_stale:
            stale_paths.append(entry.get("path"))
        else:
            survivors.append(entry)

    for rel_path in stale_paths:
        if not rel_path:
            continue
        html_file = docs_dir / rel_path
        if html_file.exists():
            html_file.unlink()
            print(f"Removed stale HTML: {html_file.name}")
        md_file = reports_dir / rel_path.replace(".html", ".md")
        if md_file.exists():
            md_file.unlink()
            print(f"Removed stale markdown: {md_file.name}")

    if len(survivors) != len(reports):
        with open(reports_json, "w") as f:
            json.dump(survivors, f, indent=2)
        print(
            f"Pruned {len(reports) - len(survivors)} stale entry/entries "
            f"from reports.json"
        )


async def _run(iteration_title: str, dry_run: bool) -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    token = os.environ.get("GITHUB_TOKEN")
    org_name = os.environ.get("GITHUB_ORG_NAME")
    project_name = os.environ.get("GITHUB_PROJECT_NAME",
                                  "Michigan App Team Task Board")
    try:
        project_number = int(os.environ.get("GITHUB_PROJECT_NUMBER", "4"))
    except ValueError:
        print("GITHUB_PROJECT_NUMBER must be an integer", file=sys.stderr)
        return 1

    if not token:
        print("GITHUB_TOKEN not set", file=sys.stderr)
        return 1
    if not org_name:
        print("GITHUB_ORG_NAME not set", file=sys.stderr)
        return 1

    print(f"Looking up {iteration_title!r} in project #{project_number}")
    iteration = _fetch_iteration_by_title(
        token, org_name, project_number, iteration_title
    )
    if not iteration:
        print(f"No iteration titled {iteration_title!r} found", file=sys.stderr)
        return 1

    info = _iteration_to_info(iteration, org_name, project_name)
    print(f"Iteration window: {info['start_date']}  ->  {info['end_date']}")

    # Import server.py only after we have the iteration to inject.
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    import agent_mcp_demo.server as srv  # noqa: E402
    from agent_mcp_demo.utils.report_publisher import ReportPublisher  # noqa: E402

    # `github_report_api()` calls the module-level name
    # `get_current_iteration_info` at request time, so swapping the module
    # attribute here is enough to force this run onto the target iteration
    # without touching any persistent state.
    srv.get_current_iteration_info = lambda *_a, **_kw: info

    print("Generating report...")
    report_content = await srv.github_report_api()

    # `github_report_api()` returns error strings rather than raising for
    # setup problems (see the "GitHub authentication failed:" and
    # "Unexpected error:" branches). Bail out clearly if we got one.
    err_prefixes = (
        "GitHub token not set",
        "GitHub organization name not set",
        "GitHub authentication failed:",
        "Error accessing organization",
        "Unexpected error:",
    )
    if report_content.startswith(err_prefixes):
        print(f"Report generation failed: {report_content}", file=sys.stderr)
        return 1

    if dry_run:
        preview = "\n".join(report_content.splitlines()[:25])
        print("--- Dry run: first 25 lines of report ---")
        print(preview)
        print("--- (report NOT published) ---")
        return 0

    docs_dir = PROJECT_ROOT / "docs"
    reports_dir = PROJECT_ROOT / "reports"

    # Remove any *_no-iteration.* leftovers first so the final index is
    # clean regardless of what path the fresh publish chooses.
    _prune_no_iteration_entries(docs_dir, reports_dir, org_name)

    publisher = ReportPublisher()
    result = await publisher.publish_report(
        report_content=report_content,
        org_name=org_name,
        iteration_name=info["name"],
        start_date=info["start_date"],
        end_date=info["end_date"],
        skip_duplicate_check=False,
    )
    print(f"Publish result: {result}")
    return 0 if result.get("status") == "published" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "iteration_title",
        help="Exact iteration title as it appears in GitHub Projects, "
             "e.g. 'Iteration 87'.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate the report and print a preview; do not write files "
             "or touch reports.json.",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args.iteration_title, args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
