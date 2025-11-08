"""
Publisher module for generating and publishing reports.
"""
import os
import asyncio
from typing import Dict, Any, Optional

async def publish_report(
    org_name: str,
    iteration_name: str,
    report_data: str,
    output_dir: Optional[str] = None
) -> Dict[str, str]:
    """
    Publish a report to markdown and HTML files.
    
    Args:
        org_name: Name of the GitHub organization
        iteration_name: Name of the iteration/sprint
        report_data: The report content as a string
        output_dir: Optional directory for output files
        
    Returns:
        Dictionary with paths to generated files and web URL
    """
    if output_dir is None:
        output_dir = os.path.join(os.getcwd(), 'reports')
        
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Create filenames
    base_name = f"{org_name}_{iteration_name}".lower().replace(' ', '_')
    md_file = os.path.join(output_dir, f"{base_name}.md")
    html_file = os.path.join(output_dir, f"{base_name}.html")
    
    # Write markdown file
    with open(md_file, 'w') as f:
        f.write(report_data)
        
    # Convert to HTML (basic conversion for demo)
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>GitHub Report - {org_name} - {iteration_name}</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            pre {{ white-space: pre-wrap; }}
        </style>
    </head>
    <body>
        <h1>GitHub Organization Report</h1>
        <h2>{org_name} - {iteration_name}</h2>
        <pre>{report_data}</pre>
    </body>
    </html>
    """
    
    # Write HTML file
    with open(html_file, 'w') as f:
        f.write(html_content)
        
    # For demo purposes, web URL is local file path
    # In real implementation, this would be a GitHub Pages or other web URL
    web_url = f"file://{html_file}"
    
    return {
        'markdown': md_file,
        'html': html_file,
        'web_url': web_url
    }