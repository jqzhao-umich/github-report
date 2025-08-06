"""
Configuration management for MCP agents
"""

from typing import Optional
from pydantic import BaseSettings, AnyHttpUrl
from pathlib import Path
import json

class Settings(BaseSettings):
    # GitHub settings
    github_token: str
    github_org_name: str
    github_iteration_start: Optional[str] = None
    github_iteration_end: Optional[str] = None
    github_iteration_name: Optional[str] = "Current Sprint"
    
    # Web interface settings
    web_host: str = "0.0.0.0"
    web_port: int = 8000
    enable_cors: bool = True
    allowed_origins: list[str] = ["*"]
    
    # Agent settings
    agent_timeout: int = 30  # seconds
    max_retries: int = 3
    
    # Logging settings
    log_level: str = "INFO"
    log_file: str = "mcp_server.log"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

def load_logging_config() -> dict:
    """Load logging configuration from JSON file"""
    config_path = Path(__file__).parent.parent / "logging_config.json"
    try:
        with open(config_path) as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading logging config: {e}")
        return {}

settings = Settings()
logging_config = load_logging_config()
