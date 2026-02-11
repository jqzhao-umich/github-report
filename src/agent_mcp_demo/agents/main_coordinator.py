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
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
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
            iteration_info = await server.request_context.session.call_tool(
                "github-agent",
                "get-iteration-info",
                {"org_name": org_name}
            )
        except (LookupError, AttributeError) as e:
            raise AgentCommunicationError(f"Failed to communicate with github-agent: {e}")
        
        # Get GitHub data
        try:
            github_data = await server.request_context.session.call_tool(
                "github-agent",
                "get-github-data",
                {
                    "org_name": org_name,
                    "iteration_info": iteration_info[0].text if iteration_info else None
                }
            )
        except (LookupError, AttributeError) as e:
            raise AgentCommunicationError(f"Failed to communicate with github-agent: {e}")
        
        # Generate report using web interface agent
        try:
            report = await server.request_context.session.call_tool(
                "web-interface-agent",
                "generate-report",
                {
                    "org_name": org_name,
                    "iteration_info": iteration_info[0].text if iteration_info else None,
                    "github_data": github_data[0].text if github_data else None
                }
            )
        except (LookupError, AttributeError) as e:
            raise AgentCommunicationError(f"Failed to communicate with web-interface-agent: {e}")
        
        # Safely extract report text, ensuring it's a string
        try:
            report_text = "No report generated"
            if report and len(report) > 0:
                report_content = report[0].text if hasattr(report[0], 'text') else str(report[0])
                # Ensure it's actually a string (not a Mock or other object)
                if isinstance(report_content, str):
                    report_text = report_content
                else:
                    report_text = str(report_content)
            return [types.TextContent(type="text", text=report_text)]
        except (AttributeError, TypeError, ValueError) as e:
            raise AgentCommunicationError(f"Failed to extract report content: {e}")

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
