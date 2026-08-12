"""Compatibility tests for the daily GitHub Actions workflow.

.github/workflows/generate-iteration-report.yml runs at 05:00 UTC
every day and calls `agent_mcp_demo.server.github_report_api` and
`ReportPublisher.publish_report` as plain Python functions — it never
goes through FastAPI, so the auth/streaming/CORS work is transparent
to it.

What the workflow DOES care about is the exact prefix on the error
strings that `github_report_api` returns. Line 193-194 of the workflow
early-exits on:

    if report_content.startswith("GitHub token not set") or \\
       report_content.startswith("Unexpected error:"):

These tests pin those prefixes so a future refactor can't silently
regress the workflow's early-exit path (which happened during the
error-disclosure hardening pass and had to be reverted).

We also pin the `ReportPublisher` import contract for the same reason.
"""

import inspect

import pytest

from agent_mcp_demo import server as server_mod


# ---------------------------------------------------------------------------
# Error-prefix contract.
#
# We can't easily execute github_report_api() with real GitHub creds in
# a unit test, so we scan the source text for the return sites and pin
# the prefixes there. Any refactor that removes a colon or drops a
# leading keyword will fail the test.
# ---------------------------------------------------------------------------


def _source() -> str:
    return inspect.getsource(server_mod.github_report_api)


def test_workflow_error_prefixes_present_in_source():
    """The daily workflow relies on exact prefixes to short-circuit.
    Each string below must appear as a substring of a return in
    github_report_api's source."""
    src = _source()
    # These are the prefixes that .github/workflows/generate-iteration-report.yml
    # matches with startswith(). Keep them stable.
    required_prefixes = [
        "GitHub token not set",
        "Unexpected error:",
    ]
    for prefix in required_prefixes:
        assert prefix in src, (
            f"Workflow-compat regression: prefix {prefix!r} is no longer "
            f"present in github_report_api. The daily workflow's "
            "startswith() check will silently fail — restore the prefix."
        )


def test_workflow_error_prefixes_are_return_values():
    """Belt + braces: the required prefixes must appear on a `return`
    line, not just in a comment or docstring. This catches the case
    where someone leaves the prefix in a comment but removes it from
    the actual returned string."""
    src = _source()
    for prefix in ("GitHub token not set", "Unexpected error:"):
        return_lines = [
            line.strip()
            for line in src.splitlines()
            if prefix in line and ("return" in line or line.strip().startswith('"'))
        ]
        assert return_lines, (
            f"Prefix {prefix!r} is present in the source but not on any "
            "return statement — workflow compat is theoretical, not real."
        )


# ---------------------------------------------------------------------------
# Direct-import contract.
#
# The workflow uses:
#   from agent_mcp_demo.server import github_report_api
#   from agent_mcp_demo.utils.report_publisher import ReportPublisher
# If either symbol goes away or is moved, the workflow's inline python
# heredoc dies with ImportError. Pin the import paths.
# ---------------------------------------------------------------------------


def test_github_report_api_is_importable_from_server():
    from agent_mcp_demo.server import github_report_api
    assert callable(github_report_api)


def test_report_publisher_is_importable_from_utils():
    from agent_mcp_demo.utils.report_publisher import ReportPublisher
    # The workflow instantiates it with no args and awaits publish_report.
    assert callable(ReportPublisher)
    assert hasattr(ReportPublisher, "publish_report")


def test_publish_report_accepts_workflow_call_signature():
    """The workflow calls:

        publisher.publish_report(
            report_content=..., org_name=..., iteration_name=...,
            start_date=..., end_date=..., skip_duplicate_check=False,
        )

    Keep all six kwargs supported."""
    from agent_mcp_demo.utils.report_publisher import ReportPublisher
    sig = inspect.signature(ReportPublisher.publish_report)
    for name in (
        "report_content",
        "org_name",
        "iteration_name",
        "start_date",
        "end_date",
        "skip_duplicate_check",
    ):
        assert name in sig.parameters, (
            f"ReportPublisher.publish_report dropped the {name!r} kwarg the "
            "daily workflow passes. Restore or update the workflow in lockstep."
        )
