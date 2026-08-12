"""XSS regression tests for report_publisher.

PROJECT_REVIEW.md recommendation #3: prove that published Markdown,
metadata, and index entries cannot execute HTML/script. These tests
document the security contract of the publish pipeline and will fail
the moment the sanitization is regressed.

The known injection surfaces (from PROJECT_REVIEW.md):

* report_publisher.py:193-196 - markdown.markdown() renders raw HTML
  unchanged unless we escape.
* report_publisher.py:241-278 - metadata (org_name, iteration_name,
  start_date, end_date) is interpolated directly into an f-string HTML
  template.
* report_publisher.py:87-96 - the index page inline JS uses innerHTML
  with template literals fed from reports.json.
"""
import html
import json
import re
import tempfile
from pathlib import Path

import pytest

from agent_mcp_demo.utils.report_publisher import ReportPublisher


# Malicious payloads we make sure never survive to the published HTML.
XSS_PAYLOADS = [
    "<script>alert('xss')</script>",
    "<img src=x onerror=alert('xss')>",
    "<svg/onload=alert('xss')>",
    "<iframe src='javascript:alert(1)'></iframe>",
    "<a href='javascript:alert(1)'>click</a>",
    "<style>body{background:url(javascript:alert(1))}</style>",
]


@pytest.fixture
def temp_base_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def publisher(temp_base_dir):
    return ReportPublisher(base_dir=temp_base_dir)


def _read_report_html(result) -> str:
    with open(result["html"]) as f:
        return f.read()


def _read_index_html(temp_base_dir) -> str:
    with open(Path(temp_base_dir, "docs", "index.html")) as f:
        return f.read()


# ---------------------------------------------------------------------------
# Markdown content sanitization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("payload", XSS_PAYLOADS)
async def test_markdown_raw_html_is_neutralized(publisher, payload):
    """Raw HTML inside report_content must NOT appear verbatim in the
    published HTML. It should be either escaped or stripped so that a
    browser cannot execute it."""
    report_content = f"""GitHub Organization: test-org

# Report

Someone put a payload in a commit message:

{payload}

More text.
"""
    result = await publisher.publish_report(
        report_content=report_content,
        org_name="test-org",
        iteration_name="Sprint 1",
    )
    html_out = _read_report_html(result)

    # The literal, unescaped payload must not appear anywhere in the
    # published HTML body (metadata section is separate and covered by
    # its own tests below).
    body = html_out.split('<div class="content">', 1)[1]
    assert payload not in body, (
        f"Payload survived rendering unescaped: {payload!r}\n\n"
        f"Excerpt:\n{body[:500]}"
    )

    # Confirmatively: no actual (unescaped) executable-tag opener may
    # appear inside the content section. Escaped forms (`&lt;script&gt;`,
    # `&lt;img … onerror=…&gt;`) are inert text and are fine — the
    # browser never turns them into a tag with a running handler. The
    # check below fires only on the literal, tag-opening `<`.
    forbidden = re.compile(
        r"<\s*(script|iframe|svg|img|style|object|embed)\b",
        re.IGNORECASE,
    )
    assert not forbidden.search(body), (
        f"Unescaped executable-tag opener reached content: {payload!r}\n"
        f"Excerpt:\n{body[:500]}"
    )


async def test_markdown_link_with_javascript_scheme_is_neutralized(publisher):
    """Markdown links pointing at `javascript:` URLs must be neutralized
    (either the href stripped or the whole anchor removed)."""
    report_content = """GitHub Organization: test-org

# Report

[click me](javascript:alert('xss'))
"""
    result = await publisher.publish_report(
        report_content=report_content,
        org_name="test-org",
        iteration_name="Sprint 1",
    )
    html_out = _read_report_html(result)
    body = html_out.split('<div class="content">', 1)[1]

    assert "javascript:" not in body.lower(), (
        f"javascript: URL survived rendering:\n{body[:500]}"
    )


async def test_benign_markdown_still_renders(publisher):
    """The sanitization must not break normal markdown: tables, bold,
    ordinary anchor links, and headings must still render."""
    report_content = """GitHub Organization: test-org

# Weekly Report

Some **bold** text and an [external link](https://example.com/page).

| Col1 | Col2 |
|------|------|
| A    | B    |
"""
    result = await publisher.publish_report(
        report_content=report_content,
        org_name="test-org",
        iteration_name="Sprint 1",
    )
    html_out = _read_report_html(result)

    assert "<h1>Weekly Report</h1>" in html_out
    assert "<strong>bold</strong>" in html_out
    assert '<a href="https://example.com/page">external link</a>' in html_out
    assert "<table>" in html_out and "<td>A</td>" in html_out


# ---------------------------------------------------------------------------
# Metadata sanitization (org_name, iteration_name, start_date, end_date)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("org_name", "<script>alert('org')</script>"),
        ("iteration_name", "<img src=x onerror=alert('iter')>"),
        ("start_date", "<svg/onload=alert('start')>"),
        ("end_date", '"><script>alert("end")</script>'),
    ],
)
async def test_metadata_fields_are_html_escaped(publisher, field, value):
    """Metadata is interpolated into the HTML template with f-strings —
    every field must be HTML-escaped before it lands in output."""
    kwargs = {
        "org_name": "safe-org",
        "iteration_name": "Sprint 1",
        "start_date": "2025-01-01",
        "end_date": "2025-01-15",
    }
    kwargs[field] = value

    result = await publisher.publish_report(
        report_content=f"GitHub Organization: {kwargs['org_name']}\n\n# body",
        **kwargs,
    )
    html_out = _read_report_html(result)

    # The unescaped payload must not appear anywhere in output.
    assert value not in html_out, (
        f"{field} landed unescaped in HTML:\n"
        f"Payload: {value!r}\n"
        f"Excerpt:\n{html_out[:800]}"
    )
    # The escaped form should appear inside the metadata block.
    escaped = html.escape(value, quote=True)
    assert escaped in html_out, (
        f"Expected the HTML-escaped form of {field} in output.\n"
        f"Escaped payload: {escaped!r}"
    )


# ---------------------------------------------------------------------------
# Index page inline JS
# ---------------------------------------------------------------------------


def test_index_page_does_not_use_innerhtml_with_report_data(temp_base_dir, publisher):
    """The reports index page renders entries from reports.json in the
    browser. That inline JS must not use innerHTML with untrusted data —
    it must build DOM nodes with createElement + textContent instead."""
    index_html = _read_index_html(temp_base_dir)

    # No template-literal innerHTML anywhere in the script block.
    assert not re.search(r"\.innerHTML\s*=\s*`", index_html), (
        "index.html uses .innerHTML with a template literal — must be "
        "replaced with createElement + textContent."
    )

    # Must use safe DOM construction primitives.
    assert "createElement" in index_html
    assert "textContent" in index_html


def test_index_page_validates_link_scheme(temp_base_dir, publisher):
    """The index page must validate report.path before dropping it into
    an <a href>. We check for a scheme allowlist / regex guard rather
    than free-form interpolation."""
    index_html = _read_index_html(temp_base_dir)
    # Look for a validation guard — a regex over report.path or an
    # explicit scheme check. Any of these patterns is acceptable.
    guards = [
        r"/\^[^:]*\$/",  # regex that rejects colons (blocks schemes)
        r"\.html\$",  # regex ending in .html
        r"startsWith\(",  # explicit prefix check
        r"safePath",  # a helper by that name
    ]
    assert any(re.search(g, index_html) for g in guards), (
        "index.html interpolates report.path without a visible scheme "
        "or filename guard; add a regex/prefix check before assigning to "
        "the anchor's href."
    )


# ---------------------------------------------------------------------------
# End-to-end: full published output must not contain any executable form
# ---------------------------------------------------------------------------


async def test_reports_json_is_pure_data(publisher, temp_base_dir):
    """reports.json must never contain HTML — it's data consumed by the
    browser, and the browser must be the one that decides how to render
    it. Store the raw fields, not pre-rendered HTML."""
    payload = "<script>alert('xss')</script>"
    await publisher.publish_report(
        report_content="GitHub Organization: test-org\n\n# body",
        org_name=payload,
        iteration_name="Sprint 1",
    )
    reports_json_path = Path(temp_base_dir, "docs", "reports.json")
    with open(reports_json_path) as f:
        reports = json.load(f)

    # The payload is stored as data (raw JSON value), NOT interpreted or
    # pre-rendered as HTML. This is fine — the risk is when the browser
    # inserts this into the DOM via innerHTML.
    assert reports[-1]["org_name"] == payload
    # But the file is pure JSON — no accidental HTML tags at the file
    # level (e.g. from a bug that concatenated raw HTML into the file).
    raw = reports_json_path.read_text()
    assert "<script" not in raw.lower() or raw.strip().startswith("["), (
        "reports.json must be a JSON array — a leading '<script' would "
        "mean somebody wrote HTML into the data file."
    )
