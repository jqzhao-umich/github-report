#!/usr/bin/env python3
"""
Helper script to manually update the iteration schedule.
This sets the next iteration end date so the GitHub Action knows when to run.

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
from agent_mcp_demo.utils.github_projects_api import get_current_iteration_info
from dotenv import load_dotenv

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
        iteration_info = get_current_iteration_info(token, org_name, "Michigan App Team Task Board")
        
        if not iteration_info:
            print("❌ No active iteration found")
            sys.exit(1)
        
        end_date_str = iteration_info.get('end_date', '')
        if not end_date_str:
            print("❌ No end date found for current iteration")
            sys.exit(1)
        
        # Parse and convert to Eastern time
        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
        eastern = ZoneInfo("America/New_York")
        end_date_eastern = end_date.astimezone(eastern)
        
        iteration_name = iteration_info.get('name', 'Unknown')
        
        print(f"\n📊 Current Iteration Information:")
        print(f"   Name: {iteration_name}")
        print(f"   End Date: {end_date_eastern.date()} (Eastern Time)")
        print(f"   Start Date: {iteration_info.get('start_date', 'Unknown')}")
        
        # Create schedule data
        schedule_data = {
            'next_iteration_end_date': end_date_eastern.date().isoformat(),
            'next_iteration_name': iteration_name,
            'last_updated': datetime.now(eastern).isoformat()
        }
        
        # Write to schedule file
        schedule_file = Path(".github/iteration-schedule.yml")
        schedule_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(schedule_file, 'w') as f:
            yaml.dump(schedule_data, f, default_flow_style=False, sort_keys=False)
        
        print(f"\n✅ Schedule file updated: {schedule_file}")
        print(f"   Next report will be generated on: {end_date_eastern.date()}")
        print(f"\n💡 Commit this file to activate the schedule:")
        print(f"   git add {schedule_file}")
        print(f"   git commit -m 'Update iteration schedule for {iteration_name}'")
        print(f"   git push")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
