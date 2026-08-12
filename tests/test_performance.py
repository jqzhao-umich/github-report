"""Performance tests for the multi-agent stack.

These need a live stack to be meaningful — timing a mocked call
tells you nothing about GitHub API latency or concurrent-request
behavior. They skip when LIVE_MCP_STACK != "1" so the default suite
stays fast and hermetic; opt in explicitly to run them against a
running fleet.

test_startup_time also lives here but doesn't need a live peer stack
(it just times BaseMCPAgent construction / initialize / cleanup).
"""

import asyncio
import os
import time
from typing import Dict

import pytest

from agent_mcp_demo.agents.base import BaseMCPAgent
from agent_mcp_demo.agents.config import settings
from agent_mcp_demo.agents.types import GitHubData


def _live_stack_available() -> bool:
    return os.environ.get("LIVE_MCP_STACK") == "1"


needs_live_stack = pytest.mark.skipif(
    not _live_stack_available(),
    reason=(
        "Live multi-agent stack not detected. Start the four agents via "
        "`./start.sh start` and set LIVE_MCP_STACK=1 to run this test."
    ),
)


@needs_live_stack
@pytest.mark.performance
async def test_report_generation_performance():
    """Full report generation completes in under 30 seconds against
    the live stack."""
    coordinator = BaseMCPAgent("main-coordinator")
    await coordinator.initialize()
    try:
        start = time.time()
        response = await coordinator.call_agent(
            "main-coordinator",
            "get-github-report",
            {"org_name": settings.github_org_name},
        )
        elapsed = time.time() - start
        assert elapsed < 30
        assert response is not None
    finally:
        await coordinator.cleanup()


@needs_live_stack
@pytest.mark.performance
async def test_concurrent_requests():
    """Three concurrent report requests each complete in reasonable
    time and finish faster in aggregate than sequential execution
    (indicating real concurrent I/O, not lock contention)."""
    coordinator = BaseMCPAgent("main-coordinator")
    await coordinator.initialize()
    try:
        async def _one():
            t0 = time.time()
            await coordinator.call_agent(
                "main-coordinator",
                "get-github-report",
                {"org_name": settings.github_org_name},
            )
            return time.time() - t0

        wall_start = time.time()
        times = await asyncio.gather(*(_one() for _ in range(3)))
        wall_total = time.time() - wall_start

        # Aggregate wall < sum of individual times → real concurrency.
        assert wall_total < sum(times)
        assert all(t < 45 for t in times)
    finally:
        await coordinator.cleanup()


@needs_live_stack
@pytest.mark.performance
async def test_memory_usage():
    """One full report costs < 500 MiB of resident memory. Requires
    psutil at runtime."""
    import psutil

    process = psutil.Process(os.getpid())
    coordinator = BaseMCPAgent("main-coordinator")
    await coordinator.initialize()
    try:
        initial_mb = process.memory_info().rss / 1024 / 1024
        await coordinator.call_agent(
            "main-coordinator",
            "get-github-report",
            {"org_name": settings.github_org_name},
        )
        peak_mb = process.memory_info().rss / 1024 / 1024
        assert peak_mb - initial_mb < 500
    finally:
        await coordinator.cleanup()


@needs_live_stack
@pytest.mark.performance
async def test_rate_limiting():
    """Three back-to-back requests all succeed — the stack handles
    GitHub rate-limit responses without user-visible failures."""
    coordinator = BaseMCPAgent("main-coordinator")
    await coordinator.initialize()
    try:
        for _ in range(3):
            response = await coordinator.call_agent(
                "main-coordinator",
                "get-github-report",
                {"org_name": settings.github_org_name},
            )
            assert response is not None
            await asyncio.sleep(1)  # give the rate limiter a beat
    finally:
        await coordinator.cleanup()


@pytest.mark.performance
def test_startup_time():
    """Every agent's synchronous construction + initialize + cleanup
    completes in under 2 seconds. Doesn't touch the peer-RPC seam,
    so it runs without a live stack."""
    for name in ("core-agent", "github-agent", "web-interface-agent", "main-coordinator"):
        t0 = time.time()
        agent = BaseMCPAgent(name)
        asyncio.run(agent.initialize())
        elapsed = time.time() - t0
        assert elapsed < 2, f"{name} took {elapsed:.2f}s to initialize"
        asyncio.run(agent.cleanup())
