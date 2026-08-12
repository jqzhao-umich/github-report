"""Report publishing utility for GitHub organization reports."""
import contextlib
import errno
import fcntl
import html
import os
import json
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import markdown
import yaml
from zoneinfo import ZoneInfo


# ---------------------------------------------------------------------------
# XSS defenses.
#
# Report content and metadata can originate from GitHub issues, PR titles,
# commit messages, and other attacker-influenceable inputs. The publisher
# writes those into static HTML that we ship to GitHub Pages, so any raw
# HTML that survives to output becomes persistent XSS for readers.
#
# Strategy:
#   * Escape all HTML metacharacters in the markdown source BEFORE handing
#     it to `markdown.markdown()`. Markdown syntax (#, *, tables, [](url))
#     does not use <, >, & so escaping is safe. Any raw HTML in the input
#     becomes literal text in the output.
#   * After markdown renders, strip href/src attributes whose scheme is
#     not http(s), mailto, or a bare relative path. This blocks
#     `[click](javascript:alert(1))` even if the input was already
#     escaped when it reached us.
#   * Escape every metadata value before f-string interpolation into the
#     wrapper HTML template.
# ---------------------------------------------------------------------------

_SAFE_URL_SCHEMES = ("http:", "https:", "mailto:", "#")

_DANGEROUS_ATTR_RE = re.compile(
    r"""\s(href|src)\s*=\s*(?P<q>["'])(?P<val>[^"']*)(?P=q)""",
    re.IGNORECASE,
)


def _sanitize_url(url: str) -> str:
    """Return a safe href/src value, or '#' for anything suspicious.

    Relative paths are allowed; only absolute URLs go through the
    scheme allowlist.
    """
    stripped = url.strip()
    if not stripped:
        return "#"
    lower = stripped.lower()
    # javascript:, data:, vbscript:, etc. are all rejected. A relative
    # URL (no ':' before the first '/', '?' or '#') is allowed.
    scheme_end = lower.find(":")
    slash = lower.find("/")
    query = lower.find("?")
    hashmark = lower.find("#")
    for pos in (slash, query, hashmark):
        if 0 <= pos < scheme_end or scheme_end < 0:
            return stripped  # relative URL, keep as-is
    for allowed in _SAFE_URL_SCHEMES:
        if lower.startswith(allowed):
            return stripped
    return "#"


def _strip_dangerous_urls(rendered_html: str) -> str:
    """Rewrite href/src attributes whose scheme isn't in the allowlist."""

    def _replace(match: re.Match) -> str:
        attr = match.group(1)
        quote = match.group("q")
        val = match.group("val")
        safe = _sanitize_url(val)
        return f' {attr}={quote}{safe}{quote}'

    return _DANGEROUS_ATTR_RE.sub(_replace, rendered_html)


def _render_markdown_safely(source: str) -> str:
    """Render Markdown to HTML with raw HTML escaped and dangerous URLs
    stripped. Safe to call on attacker-influenced input."""
    escaped_source = html.escape(source, quote=False)
    rendered = markdown.markdown(
        escaped_source,
        extensions=["extra", "nl2br", "sane_lists"],
    )
    return _strip_dangerous_urls(rendered)


def _slug(value: Optional[str], default: str) -> str:
    """Produce a filesystem-safe slug from an untrusted string."""
    if not value:
        return default
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower())
    slug = slug.strip("-._") or default
    return slug[:80]

class ReportPublisher:
    def __init__(self, base_dir: str = None):
        """Initialize the report publisher.
        
        Args:
            base_dir: Base directory for the project. If None, uses git root directory.
        """
        self.base_dir = Path(base_dir) if base_dir else Path(os.environ.get("WORKSPACE_DIR", os.getcwd()))
        self.reports_dir = self.base_dir / "reports"
        self.docs_dir = self.base_dir / "docs"
        # Use EST timezone (you can make this configurable via env var)
        self.timezone = ZoneInfo(os.environ.get("TZ", "America/New_York"))
        try:
            self._ensure_directories()
        except Exception as e:
            print(f"Error creating directories: {e}")
            # Create in temp dir as fallback
            import tempfile
            temp_root = Path(tempfile.gettempdir()) / "github_reports"
            temp_root.mkdir(exist_ok=True)
            self.reports_dir = temp_root / "reports"
            self.docs_dir = temp_root / "docs"
            self._ensure_directories()

    def _get_local_time(self):
        """Get current time in the configured timezone."""
        return datetime.now(self.timezone)

    def _ensure_directories(self):
        """Ensure necessary directories exist."""
        self.reports_dir.mkdir(exist_ok=True)
        self.docs_dir.mkdir(exist_ok=True)
        
        # Create index.html if it doesn't exist
        index_path = self.docs_dir / "index.html"
        if not index_path.exists():
            self._create_index_page()

    def _create_index_page(self):
        """Create the main index.html page for GitHub Pages.

        The report entries come from reports.json, which contains
        org/iteration/title strings that may originally have flowed
        through GitHub PR titles or commit messages. The inline JS below
        builds each list item with document.createElement + textContent
        so those values are never interpreted as HTML, and validates the
        report path against a strict filename regex before dropping it
        into an <a href>.
        """
        template = """
<!DOCTYPE html>
<html>
<head>
    <title>GitHub Organization Reports</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="Content-Security-Policy"
          content="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; base-uri 'none'; object-src 'none'; frame-ancestors 'self'">
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; max-width: 1200px; margin: 0 auto; padding: 1rem; }
        .report-list { list-style: none; padding: 0; }
        .report-item { margin: 1rem 0; padding: 1rem; border: 1px solid #ddd; border-radius: 4px; }
        .report-item:hover { background-color: #f5f5f5; }
        .report-date { color: #666; }
        .report-title { font-size: 1.2rem; margin: 0.5rem 0; }
        .report-meta { font-size: 0.9rem; }
    </style>
</head>
<body>
    <h1>GitHub Organization Reports</h1>
    <div id="reports">
        <!-- Reports will be dynamically inserted here -->
    </div>
    <script>
        // XSS-safe helpers. Report metadata comes from reports.json and
        // ultimately from GitHub PR/commit/issue text — never interpolate
        // it into innerHTML. Use createElement + textContent.
        const SAFE_PATH = /^[A-Za-z0-9._-]+\\.html$/;

        function safePath(path) {
            return typeof path === 'string' && SAFE_PATH.test(path) ? path : '#';
        }

        function buildReportItem(report) {
            const li = document.createElement('li');
            li.className = 'report-item';

            const dateDiv = document.createElement('div');
            dateDiv.className = 'report-date';
            dateDiv.textContent = new Date(report.date).toLocaleDateString();

            const titleDiv = document.createElement('div');
            titleDiv.className = 'report-title';
            const link = document.createElement('a');
            link.href = safePath(report.path);
            link.textContent = report.title || '';
            titleDiv.appendChild(link);

            const metaDiv = document.createElement('div');
            metaDiv.className = 'report-meta';
            metaDiv.textContent =
                'Sprint: ' + (report.iteration_name || 'N/A') +
                ' | Organization: ' + (report.org_name || '');

            li.appendChild(dateDiv);
            li.appendChild(titleDiv);
            li.appendChild(metaDiv);
            return li;
        }

        async function loadReports() {
            const response = await fetch('reports.json');
            const reports = await response.json();
            const reportsDiv = document.getElementById('reports');
            const reportsList = document.createElement('ul');
            reportsList.className = 'report-list';

            reports.sort((a, b) => new Date(b.date) - new Date(a.date));
            reports.forEach(report => reportsList.appendChild(buildReportItem(report)));

            reportsDiv.appendChild(reportsList);
        }

        loadReports();
    </script>
</body>
</html>
"""
        with open(self.docs_dir / "index.html", "w") as f:
            f.write(template)

    def _find_and_remove_old_report(self, org_name: str, iteration_name: Optional[str]) -> Optional[str]:
        """Find and remove old report files for the same iteration.
        
        Returns:
            Path of the old report that was removed, or None if no old report found
        """
        reports_json = self.docs_dir / "reports.json"
        if not reports_json.exists():
            return None
            
        try:
            with open(reports_json) as f:
                reports = json.load(f)
            
            old_report_path = None
            for report in reports:
                if (report.get("org_name") == org_name and 
                    report.get("iteration_name") == iteration_name):
                    old_report_path = report.get("path")
                    break
            
            if old_report_path:
                # Remove old HTML file
                old_html = self.docs_dir / old_report_path
                if old_html.exists():
                    old_html.unlink()
                    print(f"Removed old HTML report: {old_html.name}")
                
                # Remove old markdown file (replace .html with .md and check in reports dir)
                old_md_name = old_report_path.replace('.html', '.md')
                old_md = self.reports_dir / old_md_name
                if old_md.exists():
                    old_md.unlink()
                    print(f"Removed old markdown report: {old_md.name}")
                
                return old_report_path
            
            return None
        except Exception as e:
            print(f"Error removing old report: {e}")
            return None

    async def publish_report(self, 
                      report_content: str,
                      org_name: str,
                      iteration_name: Optional[str] = None,
                      start_date: Optional[str] = None,
                      end_date: Optional[str] = None,
                      skip_duplicate_check: bool = False) -> Dict[str, str]:
        """Publish a new report, overwriting any existing report for the same iteration.
        
        Args:
            report_content: The report content in markdown format
            org_name: GitHub organization name
            iteration_name: Name of the iteration/sprint
            start_date: Start date of the iteration
            end_date: End date of the iteration
            skip_duplicate_check: If True, skip checking and removing old reports
            
        Returns:
            Dict containing paths to the published files or status info
        """
        # Remove old report for the same iteration (if exists)
        old_report_removed = None
        if not skip_duplicate_check:
            old_report_removed = self._find_and_remove_old_report(org_name, iteration_name)
            if old_report_removed:
                print(f"Overwriting existing report for {org_name} - {iteration_name}")
        
        # Generate human-readable timestamp and slugified names. Both
        # org_name and iteration_name may contain arbitrary characters
        # (attacker-influenced via GitHub payload / config), so slug
        # them before using them in filenames.
        local_time = self._get_local_time()
        # Format: 2025-11-12_3-03-PM
        readable_time = local_time.strftime("%Y-%m-%d_%I-%M-%p")
        org_slug = _slug(org_name, default="org")
        iteration_slug = _slug(iteration_name, default="no-iteration")
        base_name = f"{readable_time}_{org_slug}_{iteration_slug}"

        # Save markdown version
        md_path = self.reports_dir / f"{base_name}.md"
        with open(md_path, "w") as f:
            f.write(report_content)

        # Convert to HTML and save. See _render_markdown_safely for the
        # sanitization contract; raw HTML in the source is escaped, and
        # rendered anchors with a non-allowlisted URL scheme have their
        # href stripped to '#'.
        html_content = _render_markdown_safely(report_content)
        html_template = self._wrap_html_template(
            html_content,
            org_name=org_name,
            iteration_name=iteration_name,
            start_date=start_date,
            end_date=end_date
        )
        
        html_path = self.docs_dir / f"{base_name}.html"
        with open(html_path, "w") as f:
            f.write(html_template)
            
        # Update reports index
        self._update_reports_index({
            "date": local_time.isoformat(),
            "title": f"Report for {org_name}" + (f" - {iteration_name}" if iteration_name else ""),
            "path": f"{base_name}.html",
            "org_name": org_name,
            "iteration_name": iteration_name,
            "start_date": start_date,
            "end_date": end_date
        })
        
        # Build web URL if GITHUB_REPOSITORY is set
        repo_env = os.getenv('GITHUB_REPOSITORY', '')
        if repo_env and '/' in repo_env:
            owner, repo = repo_env.split('/', 1)
            web_url = f"https://{owner}.github.io/{repo}/{base_name}.html"
        else:
            web_url = f"../{base_name}.html"
        
        return {
            "status": "published",
            "markdown": str(md_path),
            "html": str(html_path),
            "web_url": web_url,
            "org_name": org_name,
            "iteration_name": iteration_name
        }

    def _wrap_html_template(self, content: str, **metadata) -> str:
        """Wrap HTML content in a template with metadata.

        Every metadata field lands inside PCDATA in the emitted HTML, so
        each one is HTML-escaped before interpolation. The `content`
        argument is already sanitized markdown (see
        `_render_markdown_safely`); we do NOT escape it a second time
        here or the tags would render as literal text.
        """
        local_time = self._get_local_time()
        tz_name = "EDT" if local_time.dst() else "EST"
        # Coerce to str + escape. quote=True is important because the
        # payload might contain quote characters that would otherwise
        # break out of surrounding attributes if we ever moved to
        # attribute interpolation.
        org_name = html.escape(str(metadata['org_name']), quote=True)
        iteration_name = html.escape(str(metadata['iteration_name'] or 'N/A'), quote=True)
        start_date = html.escape(str(metadata['start_date'] or 'N/A'), quote=True)
        end_date = html.escape(str(metadata['end_date'] or 'N/A'), quote=True)
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>GitHub Organization Report - {org_name}</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="Content-Security-Policy"
          content="default-src 'self'; script-src 'none'; style-src 'self' 'unsafe-inline'; base-uri 'none'; object-src 'none'; frame-ancestors 'self'">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 1200px; margin: 0 auto; padding: 1rem; background-color: #fff; }}
        .metadata {{ background-color: #f5f5f5; padding: 1rem; margin-bottom: 2rem; border-radius: 4px; }}
        .content {{ margin-top: 2rem; }}
        .content h1 {{ color: #333; border-bottom: 2px solid #0066cc; padding-bottom: 0.5rem; margin-top: 2rem; }}
        .content h2 {{ color: #555; margin-top: 1.5rem; margin-bottom: 0.5rem; }}
        .content p {{ margin: 0.5rem 0; }}
        .content pre {{ background-color: #f5f5f5; padding: 1rem; border-radius: 4px; overflow-x: auto; white-space: pre-wrap; word-wrap: break-word; }}
        .content ul, .content ol {{ margin: 0.5rem 0; padding-left: 2rem; }}
        .content li {{ margin: 0.25rem 0; }}
        table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
        th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; }}
        th {{ background-color: #f5f5f5; font-weight: bold; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
        code {{ background-color: #f0f0f0; padding: 0.2rem 0.4rem; border-radius: 3px; font-family: monospace; }}
    </style>
</head>
<body>
    <div class="metadata">
        <h2>Report Metadata</h2>
        <p><strong>Organization:</strong> {org_name}</p>
        <p><strong>Iteration:</strong> {iteration_name}</p>
        <p><strong>Period:</strong> {start_date} to {end_date} ({tz_name})</p>
        <p><strong>Generated:</strong> {local_time.strftime('%Y-%m-%d %H:%M:%S')} {tz_name}</p>
    </div>
    <div class="content">
        {content}
    </div>
</body>
</html>
"""

    @contextlib.contextmanager
    def _index_lock(self, timeout: float = 30.0):
        """Advisory file lock over reports.json.

        Two publications can otherwise race the classic
        read → filter → append → write cycle: A reads the current
        3 entries, B reads the same 3, both append their new entry,
        both write back — B's write clobbers A's addition. The lock
        below serializes the entire critical section using an OS-level
        ``flock`` on a separate ``.lock`` sibling file. The lock file
        is created lazily, retried under contention, and released
        automatically on scope exit or crash (kernel drops flock on
        fd close).
        """
        lock_path = self.docs_dir / "reports.json.lock"
        # Open (or create) the lock file. We keep the file descriptor
        # for the whole critical section — closing it releases flock.
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as e:
                    if e.errno not in (errno.EAGAIN, errno.EACCES):
                        raise
                    if time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"Timed out waiting for reports.json lock at {lock_path}"
                        )
                    # Small backoff avoids a tight busy-loop.
                    time.sleep(0.05)
            yield
        finally:
            with contextlib.suppress(OSError):
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _update_reports_index(self, report_info: Dict[str, Any]):
        """Update the reports.json index file, removing any old entry for
        the same (org, iteration) pair.

        Concurrency contract:

        * The whole read → filter → append → write cycle runs inside a
          ``flock`` on ``reports.json.lock``, so concurrent publications
          cannot lose each other's entries.
        * Writes go through ``tempfile + os.replace`` so a crash mid-
          write never leaves a torn ``reports.json``. Readers always see
          either the previous complete state or the new complete state.
        """
        index_file = self.docs_dir / "reports.json"
        tmp_path = index_file.with_suffix(".json.tmp")

        with self._index_lock():
            if index_file.exists():
                with open(index_file) as f:
                    try:
                        reports = json.load(f)
                    except json.JSONDecodeError:
                        # A previous crash may have left a torn file
                        # from before atomic writes landed; recover by
                        # rebuilding from scratch rather than crashing.
                        reports = []
            else:
                reports = []

            org_name = report_info.get("org_name")
            iteration_name = report_info.get("iteration_name")
            reports = [
                r for r in reports
                if not (r.get("org_name") == org_name and r.get("iteration_name") == iteration_name)
            ]
            reports.append(report_info)

            # Atomic write: dump to a sibling tempfile, fsync, rename.
            # os.replace is atomic on the same filesystem (POSIX + NTFS).
            with open(tmp_path, "w") as f:
                json.dump(reports, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, index_file)