"""Core Agent - MCP Server (Pure Provider, Demo/Utility)

This is a pure MCP SERVER that provides basic note management capabilities.
It does NOT call other agents (pure server, not a client).

Provides:
- Tools: add-note (create/update notes)
- Resources: note:// URIs for accessing stored notes
- Prompts: summarize-notes (generate summaries of all notes)

Purpose: Demonstrates core MCP capabilities:
- State management (in-memory note storage)
- Resource exposure with custom URI schemes
- Prompt generation with arguments
- Tool execution with state modification

Note: This is a reference implementation agent, not directly used by the
GitHub reporting workflow. It serves as an example of MCP patterns.
"""

import mcp.types as types
from pydantic import AnyUrl
from mcp.server import Server
import json
from typing import Dict, List, Optional

class NoteNotFoundError(Exception):
    """Raised when a requested note is not found"""
    pass

class InvalidURIError(Exception):
    """Raised when an invalid URI is provided"""
    pass

# Store notes as a simple key-value dict to demonstrate state management
notes: dict[str, str] = {}

async def handle_list_resources() -> list[types.Resource]:
    """
    List available note resources.
    Each note is exposed as a resource with a custom note:// URI scheme.
    """
    return [
        types.Resource(
            uri=f"note://internal/{name}",
            name=f"Note: {name}",
            description=f"A simple note named {name}",
            mimeType="text/plain",
        )
        for name in notes
    ]

async def handle_read_resource(uri: AnyUrl) -> str:
    """
    Read a specific note's content by its URI.
    The note name is extracted from the URI host component.
    """
    if uri.scheme != "note":
        raise ValueError(f"Unsupported URI scheme: {uri.scheme}")

    name = uri.path
    if name is not None:
        name = name.lstrip("/")
        if name not in notes:
            raise ValueError(f"Note not found: {name}")
        return notes[name]
    raise ValueError("Note name is required")

async def handle_list_prompts() -> list[types.Prompt]:
    """
    List available prompts.
    Each prompt can have optional arguments to customize its behavior.
    """
    return [
        types.Prompt(
            name="summarize-notes",
            description="Creates a summary of all notes",
            arguments=[
                types.PromptArgument(
                    name="style",
                    description="Style of the summary (brief/detailed)",
                    required=False,
                )
            ],
        )
    ]

async def handle_get_prompt(
    name: str, arguments: dict[str, str] | None
) -> types.GetPromptResult:
    """
    Generate a prompt by combining arguments with server state.
    The prompt includes all current notes and can be customized via arguments.
    """
    if name != "summarize-notes":
        raise ValueError(f"Unknown prompt: {name}")

    style = (arguments or {}).get("style", "brief")
    detail_prompt = " Give extensive details." if style == "detailed" else ""

    return types.GetPromptResult(
        description="Summarize the current notes",
        messages=[
            types.PromptMessage(
                role="user",
                content=types.TextContent(
                    type="text",
                    text=f"Here are the current notes to summarize:{detail_prompt}\n\n"
                    + "\n".join(
                        f"- {name}: {content}"
                        for name, content in notes.items()
                    ),
                ),
            )
        ],
    )

async def handle_list_tools() -> list[types.Tool]:
    """
    List available tools.
    Each tool specifies its arguments using JSON Schema validation.
    """
    return [
        types.Tool(
            name="add-note",
            description="Add a new note",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["name", "content"],
            },
        )
    ]

async def handle_call_tool(
    name: str,
    arguments: dict | None,
    ctx=None,
) -> list[types.TextContent]:
    """
    Handle tool execution requests.
    Tools can modify server state and notify clients of changes.
    """
    # Check tool name first before validating arguments
    if name not in ["add-note"]:
        raise ValueError(f"Unknown tool: {name}")

    if not arguments:
        raise ValueError("Missing arguments")

    if name == "add-note":
        note_name = arguments.get("name")
        content = arguments.get("content")
        if not note_name or not content:
            raise ValueError("Missing name or content")
        notes[note_name] = content
        if ctx is not None:
            try:
                await ctx.session.send_resource_list_changed()
            except (LookupError, AttributeError):
                pass
        return [
            types.TextContent(
                type="text",
                text=f"Added note '{note_name}' with content: {content}",
            )
        ]
    else:
        raise ValueError(f"Unknown tool: {name}")


# --- mcp 2.0 handler adapters -----------------------------------------------

async def _on_list_resources(ctx, params):
    return types.ListResourcesResult(resources=await handle_list_resources())


async def _on_read_resource(ctx, params):
    text = await handle_read_resource(params.uri)
    return types.ReadResourceResult(
        contents=[types.TextResourceContents(uri=str(params.uri), mimeType="text/plain", text=text)]
    )


async def _on_list_prompts(ctx, params):
    return types.ListPromptsResult(prompts=await handle_list_prompts())


async def _on_get_prompt(ctx, params):
    return await handle_get_prompt(params.name, params.arguments)


async def _on_list_tools(ctx, params):
    return types.ListToolsResult(tools=await handle_list_tools())


async def _on_call_tool(ctx, params):
    content = await handle_call_tool(params.name, params.arguments, ctx=ctx)
    return types.CallToolResult(content=content or [])


server = Server(
    "core-agent",
    version="0.1.0",
    on_list_resources=_on_list_resources,
    on_read_resource=_on_read_resource,
    on_list_prompts=_on_list_prompts,
    on_get_prompt=_on_get_prompt,
    on_list_tools=_on_list_tools,
    on_call_tool=_on_call_tool,
)


async def main():
    from mcp.server.stdio import stdio_server
    from mcp.server import InitializationOptions, NotificationOptions

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="core-agent",
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
