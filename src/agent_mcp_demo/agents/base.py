"""
Base MCP agent implementation with common functionality
"""

import logging
import asyncio
from typing import Optional, Any, List, Union
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import TextContent
import mcp.types as types
from .config import settings

class BaseMCPAgent:
    def __init__(self, name: str, version: str = "0.1.0"):
        self.name = name
        self.version = version
        self.server = Server(name)
        self.logger = logging.getLogger(name)
        
    async def initialize(self) -> None:
        """Initialize the agent"""
        self.logger.info(f"Initializing {self.name}")
        
    async def cleanup(self) -> None:
        """Cleanup resources"""
        self.logger.info(f"Cleaning up {self.name}")
        
    def get_capabilities(self) -> dict:
        """Get agent capabilities"""
        return self.server.get_capabilities(
            notification_options=NotificationOptions(),
            experimental_capabilities={},
        )
        
    async def run(self) -> None:
        """Run the agent"""
        from mcp.server.stdio import stdio_server
        
        try:
            await self.initialize()
            
            async with stdio_server() as (read_stream, write_stream):
                await self.server.run(
                    read_stream,
                    write_stream,
                    InitializationOptions(
                        server_name=self.name,
                        server_version=self.version,
                        capabilities=self.get_capabilities(),
                    ),
                )
        except Exception as e:
            self.logger.error(f"Error running {self.name}: {e}")
            raise
        finally:
            await self.cleanup()
            
    async def call_agent(
        self, 
        agent: str, 
        tool: str, 
        arguments: Optional[dict] = None,
        retry_count: int = 0
    ) -> list[TextContent]:
        """Call another agent's tool with retry logic"""
        try:
            return await self.server.request_context.session.call_tool(
                agent, tool, arguments
            )
        except Exception as e:
            if retry_count < settings.max_retries:
                self.logger.warning(f"Error calling {agent}.{tool}, retrying... ({retry_count + 1}/{settings.max_retries})")
                await asyncio.sleep(1 * (retry_count + 1))  # Exponential backoff
                return await self.call_agent(agent, tool, arguments, retry_count + 1)
            raise
