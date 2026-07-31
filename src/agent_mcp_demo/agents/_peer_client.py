"""Peer-agent RPC shim.

In mcp 1.x the code called `server.request_context.session.call_tool(...)` to
reach other agents. That path is gone in mcp 2.0 — `ServerSession` never
exposed `call_tool` in either version, so the old usage was implicitly a
mock-only affordance. This module gives the test suite (and any future real
implementation on top of `mcp.stdio_client`) one place to patch.
"""

from __future__ import annotations


async def call_peer_tool(agent_name: str, tool_name: str, arguments: dict | None = None) -> str:
    """Invoke a tool on a peer agent and return its text result.

    Default implementation raises — production code paths never exercise this
    (the standalone `github_report_api()` collects metrics directly). Tests
    patch this function to return canned responses.
    """
    raise NotImplementedError(
        f"Peer-agent RPC not wired: attempted call_peer_tool({agent_name!r}, {tool_name!r}). "
        "Patch agent_mcp_demo.agents._peer_client.call_peer_tool in tests, or implement "
        "over mcp.stdio_client for production use."
    )
