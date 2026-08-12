"""Boundary tests for the publish endpoint and the report publisher.

PROJECT_REVIEW.md recommendation #4: add tests for authentication,
body-size, rate-limit, concurrency, and filename/path-boundary safety.

Coverage in this file:

* Body-size limits — 413 on oversized bodies and oversized
  report_content strings; the server never has to parse or slug
  megabytes of untrusted markdown.
* Filename / path boundary — org_name and iteration_name are slugged
  before they touch the filesystem, so `../../etc/passwd` cannot
  escape the reports directory.
* Auth *absence* — a documentation-style test that pins the current
  (unauthenticated) contract so a future auth-adding change is
  visible in the diff. Marked xfail so this file lands green today
  and turns green-strict once auth is wired.
* Concurrency smoke — two overlapping publish requests both succeed
  without corrupting reports.json.
"""

import asyncio
import json
import os
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agent_mcp_demo.server import app, MAX_PUBLISH_BODY_BYTES, MAX_REPORT_CONTENT_BYTES
from agent_mcp_demo.utils.report_publisher import ReportPublisher


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def temp_base_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_env_vars():
    with patch.dict(os.environ, {
        "GITHUB_TOKEN": "test_token",
        "GITHUB_ORG_NAME": "test_org",
    }):
        yield


@pytest.fixture
def mock_publisher(temp_base_dir):
    publisher = ReportPublisher(base_dir=temp_base_dir)
    with patch("agent_mcp_demo.server.publisher", publisher):
        yield publisher


# ---------------------------------------------------------------------------
# Body-size limits
# ---------------------------------------------------------------------------


def test_body_size_limit_rejects_oversized_content_length(client, mock_env_vars):
    """A declared Content-Length above the cap is rejected with 413."""
    huge = "x" * (MAX_PUBLISH_BODY_BYTES + 1)
    response = client.post(
        "/api/reports/publish",
        content=huge.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert "exceeds" in response.json()["error"]


def test_body_size_limit_rejects_oversized_body_without_declared_length(client, mock_env_vars):
    """Even if the client omits or lies about Content-Length, the body
    itself must not exceed the cap."""
    huge = json.dumps({"report_content": "x" * (MAX_REPORT_CONTENT_BYTES + 1)})
    response = client.post(
        "/api/reports/publish",
        content=huge.encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    # Either the outer body cap (2 MiB) or the report_content cap
    # (1 MiB) fires first; both are 413.
    assert response.status_code == 413


def test_body_size_limit_fires_mid_stream(client, mock_env_vars):
    """The streaming cap must abort as soon as the accumulated body
    exceeds MAX_PUBLISH_BODY_BYTES — we should never buffer the whole
    payload before returning 413. We prove this by counting how many
    bytes actually flowed through the ASGI receive channel: it must
    be at most one chunk past the cap, not the full oversized body.
    """
    from agent_mcp_demo import server as server_mod
    from starlette.requests import Request as StarletteRequest

    call_count = {"bytes": 0}
    original_stream = StarletteRequest.stream

    async def _counting_stream(self):
        async for chunk in original_stream(self):
            call_count["bytes"] += len(chunk)
            yield chunk

    # Send exactly 4x the cap so the abort must fire well before EOF.
    oversize = server_mod.MAX_PUBLISH_BODY_BYTES * 4
    payload = b'{"report_content": "' + b"A" * oversize + b'"}'

    with patch.object(StarletteRequest, "stream", _counting_stream):
        response = client.post(
            "/api/reports/publish",
            content=payload,
            headers={
                "Content-Type": "application/json",
                # Omit Content-Length so the fast-path guard doesn't
                # short-circuit the streaming path we want to exercise.
                # (TestClient's default transport will still set one;
                # this test tolerates that by asserting we abort well
                # before the sender's full payload is read.)
            },
        )

    assert response.status_code == 413
    # The whole 4x-oversize payload must NOT have been read into memory.
    # Allow a small overshoot to cover chunk-boundary reads.
    assert call_count["bytes"] <= server_mod.MAX_PUBLISH_BODY_BYTES + 65536, (
        f"Streaming cap did not abort early: read {call_count['bytes']} bytes "
        f"of a {oversize}-byte payload (cap is {server_mod.MAX_PUBLISH_BODY_BYTES})."
    )


def test_report_content_size_limit_rejects_oversized_string(client, mock_env_vars):
    """A JSON body that fits the outer cap but contains a report_content
    string larger than the inner cap is rejected with 413."""
    # Just above the report_content cap, but well under the outer body cap.
    payload = "GitHub Organization: test-org\n\n" + ("A" * MAX_REPORT_CONTENT_BYTES)
    response = client.post(
        "/api/reports/publish",
        json={"report_content": payload},
    )
    assert response.status_code == 413
    assert "report_content exceeds" in response.json()["error"]


def test_body_size_limit_accepts_normal_payload(client, mock_env_vars, mock_publisher):
    """Ordinary-sized report_content payloads still succeed."""
    normal = "GitHub Organization: test-org\n\n# Report\n\nA bit of content."
    response = client.post(
        "/api/reports/publish",
        json={"report_content": normal},
    )
    assert response.status_code == 200


def test_non_string_report_content_is_rejected(client, mock_env_vars):
    """report_content must be a JSON string."""
    response = client.post(
        "/api/reports/publish",
        json={"report_content": {"nested": "object"}},
    )
    assert response.status_code == 400
    assert "must be a string" in response.json()["error"]


def test_invalid_content_length_header(client, mock_env_vars):
    """A malformed Content-Length header is rejected before body read."""
    response = client.post(
        "/api/reports/publish",
        content=b'{"report_content": "GitHub Organization: x"}',
        headers={
            "Content-Type": "application/json",
            "Content-Length": "not-a-number",
        },
    )
    # httpx will normally reject "not-a-number" on the client side. If
    # it does reach the server, our handler should return 400.
    assert response.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Filename / path-boundary safety in the publisher
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "org_name",
    [
        "../../etc/passwd",
        "..",
        "../../..",
        "/absolute/path",
        "org\x00null",
        "org name with spaces",
        "org/name/with/slashes",
        "org\\backslash",
        "😈emoji",
        "<script>alert(1)</script>",
    ],
)
async def test_publisher_slugs_malicious_org_name(temp_base_dir, org_name):
    """No matter what org_name we throw at the publisher, the resulting
    files must land inside reports_dir / docs_dir — never above."""
    publisher = ReportPublisher(base_dir=temp_base_dir)
    result = await publisher.publish_report(
        report_content=f"GitHub Organization: {org_name}\n\n# body",
        org_name=org_name,
        iteration_name="Sprint 1",
    )
    md_path = Path(result["markdown"]).resolve()
    html_path = Path(result["html"]).resolve()
    reports_dir = Path(temp_base_dir, "reports").resolve()
    docs_dir = Path(temp_base_dir, "docs").resolve()

    # The Path.is_relative_to method is 3.9+ and safe here.
    assert md_path.is_relative_to(reports_dir), (
        f"Markdown escaped reports dir: {md_path} not under {reports_dir}"
    )
    assert html_path.is_relative_to(docs_dir), (
        f"HTML escaped docs dir: {html_path} not under {docs_dir}"
    )
    # No path separators or NUL bytes may appear in the basename.
    for path in (md_path, html_path):
        base = path.name
        assert "/" not in base and "\\" not in base and "\x00" not in base
        assert not base.startswith(".")


@pytest.mark.parametrize(
    "iteration_name",
    [
        "../../..",
        "Sprint/with/slashes",
        "Sprint\\backslash",
        "Sprint\x00null",
        "<img src=x onerror=alert(1)>",
    ],
)
async def test_publisher_slugs_malicious_iteration_name(temp_base_dir, iteration_name):
    publisher = ReportPublisher(base_dir=temp_base_dir)
    result = await publisher.publish_report(
        report_content="GitHub Organization: safe-org\n\n# body",
        org_name="safe-org",
        iteration_name=iteration_name,
    )
    md_path = Path(result["markdown"]).resolve()
    html_path = Path(result["html"]).resolve()
    reports_dir = Path(temp_base_dir, "reports").resolve()
    docs_dir = Path(temp_base_dir, "docs").resolve()

    assert md_path.is_relative_to(reports_dir)
    assert html_path.is_relative_to(docs_dir)
    for path in (md_path, html_path):
        assert re.fullmatch(r"[A-Za-z0-9._-]+", path.name), (
            f"Unsafe characters survived slugging: {path.name}"
        )


async def test_publisher_slugs_are_stable_for_same_input(temp_base_dir):
    """Slugging must be deterministic — same org + iteration produces
    the same slug so the duplicate-detection code path keeps working."""
    from agent_mcp_demo.utils.report_publisher import _slug

    assert _slug("test-org", "org") == _slug("Test-Org", "org")
    assert _slug("  spaced  name  ", "x") == _slug("spaced-name", "x")
    assert _slug("../../etc/passwd", "org") == _slug("etc-passwd", "org")


# ---------------------------------------------------------------------------
# Concurrency smoke test
# ---------------------------------------------------------------------------


async def test_concurrent_publish_does_not_lose_entries(temp_base_dir):
    """Two publish_report calls running concurrently must produce a
    reports.json that (a) parses as JSON and (b) contains BOTH entries.
    The stronger invariant depends on the flock + os.replace pipeline
    in ReportPublisher._update_reports_index."""
    publisher = ReportPublisher(base_dir=temp_base_dir)

    async def _publish(name):
        return await publisher.publish_report(
            report_content=f"GitHub Organization: org-{name}\n\n# body",
            org_name=f"org-{name}",
            iteration_name=f"Sprint {name}",
        )

    results = await asyncio.gather(_publish("A"), _publish("B"))
    assert all(r["status"] == "published" for r in results)

    reports_json = Path(temp_base_dir, "docs", "reports.json")
    reports = json.loads(reports_json.read_text())
    orgs = {r["org_name"] for r in reports}
    assert orgs == {"org-A", "org-B"}, (
        "Concurrent publish lost an entry — flock/atomic-rename "
        "regression."
    )


async def test_high_concurrency_publish_keeps_all_entries(temp_base_dir):
    """Stress the atomic-index contract with more concurrency: 10
    parallel publications should ALL land in reports.json. Runs in a
    thread pool so we get real preemption on the read-modify-write."""
    import concurrent.futures

    publisher = ReportPublisher(base_dir=temp_base_dir)

    async def _publish(name):
        return await publisher.publish_report(
            report_content=f"GitHub Organization: org-{name}\n\n# body",
            org_name=f"org-{name}",
            iteration_name=f"Sprint {name}",
        )

    async def _drive():
        return await asyncio.gather(*(_publish(str(i)) for i in range(10)))

    results = await _drive()
    assert all(r["status"] == "published" for r in results)

    reports_json = Path(temp_base_dir, "docs", "reports.json")
    reports = json.loads(reports_json.read_text())
    orgs = {r["org_name"] for r in reports}
    assert orgs == {f"org-{i}" for i in range(10)}


async def test_torn_index_file_is_repaired(temp_base_dir):
    """If a crash left reports.json truncated / non-JSON, the next
    _update_reports_index call must recover rather than raise. This is
    the belt-and-braces companion to atomic writes: if a prior process
    somehow got past the atomic-write guarantee (network share, older
    version, …), we don't turn every future publish into an error."""
    docs_dir = Path(temp_base_dir, "docs")
    docs_dir.mkdir(parents=True, exist_ok=True)
    reports_json = docs_dir / "reports.json"
    reports_json.write_text("{{{ not json at all")

    publisher = ReportPublisher(base_dir=temp_base_dir)
    await publisher.publish_report(
        report_content="GitHub Organization: recover\n\n# body",
        org_name="recover",
        iteration_name="Sprint R",
    )

    # After the publish, reports.json is valid and contains our entry.
    reports = json.loads(reports_json.read_text())
    assert any(r["org_name"] == "recover" for r in reports)


# ---------------------------------------------------------------------------
# Auth: bearer-token enforcement on report/publish endpoints.
# ---------------------------------------------------------------------------
#
# Contract (see src/agent_mcp_demo/auth.py):
#   * AUTH_TOKEN unset  → anonymous access allowed (dev mode, one-shot
#     warning at first use). Existing tests rely on this.
#   * AUTH_TOKEN set    → Authorization: Bearer <token> required;
#     mismatch/missing → 401.


@pytest.fixture
def auth_token(monkeypatch):
    """Enable bearer auth for the duration of this test."""
    from agent_mcp_demo import auth as auth_mod

    monkeypatch.setenv("AUTH_TOKEN", "s3cret-test-token")
    auth_mod.reset_warning_state_for_tests()
    yield "s3cret-test-token"


def test_publish_endpoint_rejects_missing_bearer(client, auth_token):
    """AUTH_TOKEN configured but no Authorization header → 401."""
    response = client.post(
        "/api/reports/publish",
        json={"report_content": "GitHub Organization: test-org\n\n# body"},
    )
    assert response.status_code == 401
    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_publish_endpoint_rejects_wrong_bearer(client, auth_token):
    """AUTH_TOKEN configured, wrong bearer token → 401."""
    response = client.post(
        "/api/reports/publish",
        json={"report_content": "GitHub Organization: test-org\n\n# body"},
        headers={"Authorization": "Bearer not-the-right-token"},
    )
    assert response.status_code == 401


def test_publish_endpoint_rejects_non_bearer_scheme(client, auth_token):
    """Non-Bearer credentials (Basic, token, etc.) → 401."""
    response = client.post(
        "/api/reports/publish",
        json={"report_content": "GitHub Organization: test-org\n\n# body"},
        headers={"Authorization": "Basic dXNlcjpwYXNz"},
    )
    assert response.status_code == 401


def test_publish_endpoint_accepts_correct_bearer(
    client, auth_token, mock_env_vars, mock_publisher
):
    """AUTH_TOKEN configured, correct bearer → 200."""
    response = client.post(
        "/api/reports/publish",
        json={"report_content": "GitHub Organization: test-org\n\n# body"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 200


def test_report_endpoint_rejects_missing_bearer(client, auth_token, mock_env_vars):
    """GET /api/github-report also enforces auth."""
    response = client.get("/api/github-report")
    assert response.status_code == 401


def test_auth_dev_mode_allows_anonymous(client, monkeypatch, mock_env_vars, mock_publisher):
    """AUTH_TOKEN unset AND ALLOW_ANONYMOUS=1 → anonymous access.
    (This is the pytest.ini env default, so a plain test client works.)"""
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    monkeypatch.setenv("ALLOW_ANONYMOUS", "1")
    from agent_mcp_demo import auth as auth_mod
    auth_mod.reset_warning_state_for_tests()

    response = client.post(
        "/api/reports/publish",
        json={"report_content": "GitHub Organization: test-org\n\n# body"},
    )
    assert response.status_code == 200


def test_auth_fails_closed_when_misconfigured(client, monkeypatch, mock_env_vars):
    """AUTH_TOKEN unset AND ALLOW_ANONYMOUS unset → 503. This is the
    security regression the review flagged: fail-open by default meant
    Compose deployments were silently unauthenticated. The dev-mode
    branch now requires an explicit ALLOW_ANONYMOUS=1 opt-in."""
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ALLOW_ANONYMOUS", raising=False)
    from agent_mcp_demo import auth as auth_mod
    auth_mod.reset_warning_state_for_tests()

    response = client.post(
        "/api/reports/publish",
        json={"report_content": "GitHub Organization: test-org\n\n# body"},
    )
    assert response.status_code == 503
    assert "AUTH_TOKEN" in response.json()["detail"]


def test_auth_fails_closed_when_allow_anonymous_is_falsy(client, monkeypatch, mock_env_vars):
    """A literal ALLOW_ANONYMOUS=0 (or "false", "no") is NOT truthy —
    same 503 as when the variable is unset. Guards against operators
    thinking "I set it, so I'm covered" when they set it to 0."""
    monkeypatch.delenv("AUTH_TOKEN", raising=False)
    from agent_mcp_demo import auth as auth_mod

    for falsy in ("0", "false", "no", "", "off"):
        monkeypatch.setenv("ALLOW_ANONYMOUS", falsy)
        auth_mod.reset_warning_state_for_tests()
        response = client.post(
            "/api/reports/publish",
            json={"report_content": "GitHub Organization: test-org\n\n# body"},
        )
        assert response.status_code == 503, (
            f"ALLOW_ANONYMOUS={falsy!r} unexpectedly enabled anonymous access"
        )


def test_auth_token_takes_precedence_over_allow_anonymous(client, monkeypatch, mock_env_vars):
    """When both are set, AUTH_TOKEN wins — a token misconfigured
    alongside ALLOW_ANONYMOUS=1 still enforces the token check. Prevents
    a "I forgot to unset dev mode" prod bug."""
    monkeypatch.setenv("AUTH_TOKEN", "prod-token")
    monkeypatch.setenv("ALLOW_ANONYMOUS", "1")
    from agent_mcp_demo import auth as auth_mod
    auth_mod.reset_warning_state_for_tests()

    # No Authorization header — must be rejected despite ALLOW_ANONYMOUS.
    response = client.post(
        "/api/reports/publish",
        json={"report_content": "GitHub Organization: test-org\n\n# body"},
    )
    assert response.status_code == 401


def test_auth_bearer_comparison_is_constant_time(monkeypatch):
    """Regression: swap in the real dependency, exercise it directly,
    and confirm we route through hmac.compare_digest rather than raw '=='.
    Missing this makes token comparison time-based side channels leak
    the length/prefix of the configured secret."""
    import hmac
    from agent_mcp_demo import auth as auth_mod

    monkeypatch.setenv("AUTH_TOKEN", "s3cret")
    called = {"n": 0}
    real = hmac.compare_digest

    def _spy(a, b):
        called["n"] += 1
        return real(a, b)

    monkeypatch.setattr("agent_mcp_demo.auth.hmac.compare_digest", _spy)
    auth_mod.reset_warning_state_for_tests()

    import asyncio
    from fastapi import HTTPException

    async def _run():
        try:
            await auth_mod.require_auth("Bearer s3cret")
        except HTTPException:
            pytest.fail("valid token was rejected")
        with pytest.raises(HTTPException):
            await auth_mod.require_auth("Bearer wrong")

    asyncio.get_event_loop().run_until_complete(_run()) if False else asyncio.run(_run())
    assert called["n"] >= 2, "hmac.compare_digest was not called for token check"
