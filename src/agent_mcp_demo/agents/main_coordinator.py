"""
Main MCP Coordinator

This agent coordinates communication between all other agents in the system.
It handles:
- Request routing
- Error handling and recovery
- State synchronization
"""

from mcp.server.models import types
from mcp.server import Server
import os
import asyncio
from typing import Dict, List, Optional

class AgentCommunicationError(Exception):
    """Raised when communication with an agent fails"""
    pass

class AgentNotAvailableError(Exception):
    """Raised when a required agent is not available"""
    pass

REQUIRED_AGENTS = ["core-agent", "github-agent", "web-interface-agent"]

server = Server("main-coordinator")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get-github-report",
            description="Generate a GitHub organization report",
            inputSchema={
                "type": "object",
                "properties": {
                    "org_name": {"type": "string"}
                },
                "required": ["org_name"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if not arguments:
        raise ValueError("Missing arguments")

    if name == "get-github-report":
        org_name = arguments.get("org_name")
        if not org_name:
            raise ValueError("Missing org_name")
        
        # Get iteration info from GitHub agent
        iteration_info = await server.request_context.session.call_tool(
            "github-agent",
            "get-iteration-info",
            {"org_name": org_name}
        )
        
        # Get GitHub data
        github_data = await server.request_context.session.call_tool(
            "github-agent",
            "get-github-data",
            {
                "org_name": org_name,
                "iteration_info": iteration_info[0].text if iteration_info else None
            }
        )
        
        # Generate report using web interface agent
        report = await server.request_context.session.call_tool(
            "web-interface-agent",
            "generate-report",
            {
                "org_name": org_name,
                "iteration_info": iteration_info[0].text if iteration_info else None,
                "github_data": github_data[0].text if github_data else None
            }
        )
        
        return [types.TextContent(type="text", text=report[0].text if report else "No report generated")]

async def main():
    from mcp.server.stdio import stdio_server
    from mcp.server.models import InitializationOptions
    from mcp.server import NotificationOptions
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="main-coordinator",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
