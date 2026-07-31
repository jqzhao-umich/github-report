"""Main Coordinator - MCP Server + Client (Orchestrator)

This is an MCP SERVER that also acts as a CLIENT to orchestrate other agents.

Server role (provides tools):
- get-github-report: Orchestrates report generation across multiple agents

Client role (calls other agents):
- Calls github-agent for iteration info and organization data
- Calls web-interface-agent for report formatting

Responsibilities:
- Request routing between agents
- Error handling and recovery
- State synchronization
- Agent communication coordination

Architecture: Sits at the top of the agent hierarchy, coordinating workflows.
"""

import mcp.types as types
from mcp.server import Server, NotificationOptions, InitializationOptions
import os
import asyncio
from typing import Dict, List, Optional

from . import _peer_client


class AgentCommunicationError(Exception):
    """Raised when communication with an agent fails"""
    pass

class AgentNotAvailableError(Exception):
    """Raised when a required agent is not available"""
    pass

REQUIRED_AGENTS = ["core-agent", "github-agent", "web-interface-agent"]


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

async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    # Check for unknown tools first
    if name != "get-github-report":
        raise ValueError(f"Unknown tool: {name}")

    if not arguments:
        raise ValueError("Missing arguments")

    if name == "get-github-report":
        org_name = arguments.get("org_name")
        if not org_name:
            raise ValueError("Missing org_name")

        # Get iteration info from GitHub agent
        try:
            iteration_info_text = await _peer_client.call_peer_tool(
                "github-agent",
                "get-iteration-info",
                {"org_name": org_name},
            )
        except (LookupError, AttributeError, NotImplementedError) as e:
            raise AgentCommunicationError(f"Failed to communicate with github-agent: {e}")

        # Get GitHub data
        try:
            github_data_text = await _peer_client.call_peer_tool(
                "github-agent",
                "get-github-data",
                {"org_name": org_name, "iteration_info": iteration_info_text},
            )
        except (LookupError, AttributeError, NotImplementedError) as e:
            raise AgentCommunicationError(f"Failed to communicate with github-agent: {e}")

        # Generate report using web interface agent
        try:
            report_text = await _peer_client.call_peer_tool(
                "web-interface-agent",
                "generate-report",
                {
                    "org_name": org_name,
                    "iteration_info": iteration_info_text,
                    "github_data": github_data_text,
                },
            )
        except (LookupError, AttributeError, NotImplementedError) as e:
            raise AgentCommunicationError(f"Failed to communicate with web-interface-agent: {e}")

        if not isinstance(report_text, str):
            report_text = str(report_text) if report_text is not None else "No report generated"
        return [types.TextContent(type="text", text=report_text)]


# --- mcp 2.0 handler adapters -----------------------------------------------

async def _on_list_tools(ctx, params):
    return types.ListToolsResult(tools=await handle_list_tools())


async def _on_call_tool(ctx, params):
    content = await handle_call_tool(params.name, params.arguments)
    return types.CallToolResult(content=content or [])


server = Server(
    "main-coordinator",
    version="0.1.0",
    on_list_tools=_on_list_tools,
    on_call_tool=_on_call_tool,
)


async def main():
    from mcp.server.stdio import stdio_server

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
