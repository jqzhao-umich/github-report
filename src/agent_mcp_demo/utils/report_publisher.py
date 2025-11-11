"""Report publishing utility for GitHub organization reports."""
import os
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import markdown
import yaml
from zoneinfo import ZoneInfo

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
        """Create the main index.html page for GitHub Pages."""
        template = """
<!DOCTYPE html>
<html>
<head>
    <title>GitHub Organization Reports</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
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
        async function loadReports() {
            const response = await fetch('reports.json');
            const reports = await response.json();
            const reportsDiv = document.getElementById('reports');
            const reportsList = document.createElement('ul');
            reportsList.className = 'report-list';
            
            reports.sort((a, b) => new Date(b.date) - new Date(a.date));
            
            reports.forEach(report => {
                const li = document.createElement('li');
                li.className = 'report-item';
                li.innerHTML = `
                    <div class="report-date">${new Date(report.date).toLocaleDateString()}</div>
                    <div class="report-title">
                        <a href="${report.path}">${report.title}</a>
                    </div>
                    <div class="report-meta">
                        Sprint: ${report.iteration_name || 'N/A'} |
                        Organization: ${report.org_name}
                    </div>
                `;
                reportsList.appendChild(li);
            });
            
            reportsDiv.appendChild(reportsList);
        }
        
        loadReports();
    </script>
</body>
</html>
"""
        with open(self.docs_dir / "index.html", "w") as f:
            f.write(template)

    async def publish_report(self, 
                      report_content: str,
                      org_name: str,
                      iteration_name: Optional[str] = None,
                      start_date: Optional[str] = None,
                      end_date: Optional[str] = None) -> Dict[str, str]:
        """Publish a new report.
        
        Args:
            report_content: The report content in markdown format
            org_name: GitHub organization name
            iteration_name: Name of the iteration/sprint
            start_date: Start date of the iteration
            end_date: End date of the iteration
            
        Returns:
            Dict containing paths to the published files
        """
        # Generate timestamp and slugified names
        local_time = self._get_local_time()
        timestamp = local_time.strftime("%Y%m%d_%H%M%S")
        iteration_slug = (iteration_name or "no-iteration").lower().replace(" ", "-")
        base_name = f"{timestamp}_{org_name}_{iteration_slug}"
        
        # Save markdown version
        md_path = self.reports_dir / f"{base_name}.md"
        with open(md_path, "w") as f:
            f.write(report_content)
        
        # Convert to HTML and save
        html_content = markdown.markdown(report_content)
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
            "markdown": str(md_path),
            "html": str(html_path),
            "web_url": web_url
        }

    def _wrap_html_template(self, content: str, **metadata) -> str:
        """Wrap HTML content in a template with metadata."""
        local_time = self._get_local_time()
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>GitHub Organization Report - {metadata['org_name']}</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; max-width: 1200px; margin: 0 auto; padding: 1rem; }}
        .metadata {{ background-color: #f5f5f5; padding: 1rem; margin-bottom: 2rem; border-radius: 4px; }}
        .content {{ margin-top: 2rem; }}
        table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
        th, td {{ border: 1px solid #ddd; padding: 0.5rem; }}
        th {{ background-color: #f5f5f5; }}
        tr:nth-child(even) {{ background-color: #f9f9f9; }}
    </style>
</head>
<body>
    <div class="metadata">
        <h2>Report Metadata</h2>
        <p><strong>Organization:</strong> {metadata['org_name']}</p>
        <p><strong>Iteration:</strong> {metadata['iteration_name'] or 'N/A'}</p>
        <p><strong>Period:</strong> {metadata['start_date'] or 'N/A'} to {metadata['end_date'] or 'N/A'}</p>
        <p><strong>Generated:</strong> {local_time.strftime('%Y-%m-%d %H:%M:%S %Z')}</p>
    </div>
    <div class="content">
        {content}
    </div>
</body>
</html>
"""

    def _update_reports_index(self, report_info: Dict[str, Any]):
        """Update the reports.json index file."""
        index_file = self.docs_dir / "reports.json"
        
        if index_file.exists():
            with open(index_file) as f:
                reports = json.load(f)
        else:
            reports = []
            
        reports.append(report_info)
        
        with open(index_file, "w") as f:
            json.dump(reports, f, indent=2)