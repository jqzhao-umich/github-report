#!/usr/bin/env python3
"""
Helper script to manually update the iteration schedule.
This sets the next iteration start date so the GitHub Action knows when to run.
The report will be generated on the first day of each iteration for the previous iteration.

Usage:
    python scripts/update_iteration_schedule.py
    
Or set environment variables:
    GITHUB_TOKEN=your_token GITHUB_ORG_NAME=your_org python scripts/update_iteration_schedule.py
"""

import os
import sys
import yaml
from datetime import datetime
from pathlib import Path

# Add parent directory to path to import our modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import requests

def get_actual_current_iteration(token, org_name, project_name):
    """Get the actual current iteration (not adjusted for report generation)."""
    print(f"Fetching projects for organization: {org_name}")
    
    # Get projects
    headers = {"Authorization": f"Bearer {token}"}
    projects_query = f"""
    query {{
      organization(login: "{org_name}") {{
        projectsV2(first: 20) {{
          nodes {{
            id
            title
          }}
        }}
      }}
    }}
    """
    
    response = requests.post(
        "https://api.github.com/graphql",
        json={"query": projects_query},
        headers=headers
    )
    response.raise_for_status()
    data = response.json()
    
    projects = data.get("data", {}).get("organization", {}).get("projectsV2", {}).get("nodes", [])
    project = next((p for p in projects if p.get("title") == project_name), None)
    
    if not project:
        return None
    
    project_id = project["id"]
    
    # Get iteration field
    fields_query = f"""
    query {{
      node(id: "{project_id}") {{
        ... on ProjectV2 {{
          fields(first: 20) {{
            nodes {{
              ... on ProjectV2IterationField {{
                id
                name
                configuration {{
                  iterations {{
                    id
                    title
                    startDate
                    duration
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """
    
    response = requests.post(
        "https://api.github.com/graphql",
        json={"query": fields_query},
        headers=headers
    )
    response.raise_for_status()
    data = response.json()
    
    fields = data.get("data", {}).get("node", {}).get("fields", {}).get("nodes", [])
    iteration_field = next((f for f in fields if f and f.get("name") == "Iteration"), None)
    
    if not iteration_field:
        return None
    
    iterations = iteration_field.get("configuration", {}).get("iterations", [])
    
    # Find current iteration based on today's date
    eastern = ZoneInfo("America/New_York")
    today = datetime.now(eastern).date()
    
    for iteration in iterations:
        start_date_str = iteration.get("startDate")
        duration = iteration.get("duration", 14)
        
        if start_date_str:
            start_dt = datetime.fromisoformat(start_date_str).replace(tzinfo=eastern).date()
            from datetime import timedelta
            end_dt = start_dt + timedelta(days=duration - 1)
            
            if start_dt <= today <= end_dt:
                return {
                    'name': iteration.get('title'),
                    'start_date': start_dt.isoformat(),
                    'end_date': end_dt.isoformat(),
                    'path': f"{org_name}/{project_name}"
                }
    
    return None

def main():
    # Load environment variables
    load_dotenv()
    
    token = os.environ.get("GITHUB_TOKEN")
    org_name = os.environ.get("GITHUB_ORG_NAME")
    
    if not token:
        print("❌ GITHUB_TOKEN not set. Please set it in .env file or environment.")
        sys.exit(1)
    
    if not org_name:
        print("❌ GITHUB_ORG_NAME not set. Please set it in .env file or environment.")
        sys.exit(1)
    
    print(f"Fetching current iteration info for {org_name}...")
    
    try:
        iteration_info = get_actual_current_iteration(token, org_name, "Michigan App Team Task Board")
        
        if not iteration_info:
            print("❌ No active iteration found")
            sys.exit(1)
        
        start_date_str = iteration_info.get('start_date', '')
        end_date_str = iteration_info.get('end_date', '')
        
        if not start_date_str or not end_date_str:
            print("❌ No start/end date found for current iteration")
            sys.exit(1)
        
        # Parse dates
        start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
        eastern = ZoneInfo("America/New_York")
        start_date_eastern = start_date.astimezone(eastern)
        end_date_eastern = end_date.astimezone(eastern)
        
        # Get current timezone abbreviation (EST or EDT)
        tz_name = "EDT" if datetime.now(eastern).dst() else "EST"
        
        iteration_name = iteration_info.get('name', 'Unknown')
        
        # Calculate next iteration start date (day after current iteration ends)
        from datetime import timedelta
        next_iteration_start = end_date_eastern.date() + timedelta(days=1)
        
        print(f"\n📊 Current Iteration Information:")
        print(f"   Name: {iteration_name}")
        print(f"   Start Date: {start_date_eastern.date()} {tz_name}")
        print(f"   End Date: {end_date_eastern.date()} {tz_name}")
        print(f"\n📅 Next Iteration:")
        print(f"   Start Date: {next_iteration_start} {tz_name}")
        print(f"   (Report will be generated for {iteration_name} on {next_iteration_start} {tz_name})")
        
        # Create schedule data
        # Note: All dates in this file are in Eastern Time (EST/EDT depending on season)
        schedule_data = {
            'next_iteration_start_date': next_iteration_start.isoformat(),
            'previous_iteration_name': iteration_name,
            'last_updated': datetime.now(eastern).isoformat(),
            '_timezone_note': f'All dates are in {tz_name} (Eastern Time)'
        }
        
        # Write to schedule file with timezone comment header
        schedule_file = Path(".github/iteration-schedule.yml")
        schedule_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(schedule_file, 'w') as f:
            f.write(f"# Iteration Schedule - All dates in {tz_name} (Eastern Time)\n")
            yaml.dump(schedule_data, f, default_flow_style=False, sort_keys=False)
        
        print(f"\n✅ Schedule file updated: {schedule_file}")
        print(f"   Next report will be generated on: {next_iteration_start} {tz_name}")
        print(f"   Report will cover: {iteration_name}")
        print(f"\n💡 Commit this file to activate the schedule:")
        print(f"   git add {schedule_file}")
        print(f"   git commit -m 'Update iteration schedule: report on {next_iteration_start} {tz_name}'")
        print(f"   git push")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
