"""Utility functions for the agent_mcp_demo package."""

import os
import pytz
from datetime import datetime
import httpx

def get_detroit_timezone():
    """Get the Detroit timezone."""
    return pytz.timezone('America/Detroit')

def get_env_var(name: str, default=None):
    """Get an environment variable."""
    return os.environ.get(name, default)

def format_datetime(dt: datetime) -> str:
    """Format a datetime object to a string."""
    if not dt.tzinfo:
        dt = get_detroit_timezone().localize(dt)
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z")