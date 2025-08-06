"""
Shared utilities for MCP agents
"""

import os
from datetime import datetime, timezone, timedelta
from typing import Optional

def get_detroit_timezone() -> timezone:
    """Get Detroit timezone (UTC-4)"""
    return timezone(timedelta(hours=-4))

def get_env_var(name: str, required: bool = True) -> Optional[str]:
    """Get environment variable with optional requirement check"""
    value = os.environ.get(name)
    if required and not value:
        raise ValueError(f"Environment variable {name} is required but not set")
    return value

def format_datetime(dt: datetime) -> str:
    """Format datetime in Detroit timezone"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    detroit_tz = get_detroit_timezone()
    local_dt = dt.astimezone(detroit_tz)
    return local_dt.strftime('%Y-%m-%d %I:%M:%S %p EDT')
