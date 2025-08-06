import pytest
import asyncio
import time
from typing import Dict, List
from agent_mcp_demo.agents.base import BaseMCPAgent
from agent_mcp_demo.agents.config import settings
from agent_mcp_demo.agents.types import GitHubData

@pytest.mark.performance
async def test_report_generation_performance():
    """Test the performance of report generation"""
    coordinator = BaseMCPAgent("main-coordinator")
    await coordinator.initialize()
    
    try:
        start_time = time.time()
        response = await coordinator.call_agent(
            "main-coordinator",
            "get-github-report",
            {"org_name": settings.github_org_name}
        )
        end_time = time.time()
        
        # Report generation should take less than 30 seconds
        assert end_time - start_time < 30
        assert response is not None
    finally:
        await coordinator.cleanup()

@pytest.mark.performance
async def test_concurrent_requests():
    """Test handling multiple concurrent requests"""
    coordinator = BaseMCPAgent("main-coordinator")
    await coordinator.initialize()
    
    try:
        # Create multiple concurrent requests
        async def make_request():
            start_time = time.time()
            response = await coordinator.call_agent(
                "main-coordinator",
                "get-github-report",
                {"org_name": settings.github_org_name}
            )
            end_time = time.time()
            return end_time - start_time
        
        # Run 3 concurrent requests
        start_time = time.time()
        times = await asyncio.gather(*[make_request() for _ in range(3)])
        total_time = time.time() - start_time
        
        # Total time should be less than sum of individual times
        # (indicating concurrent processing)
        assert total_time < sum(times)
        
        # Each request should still complete in reasonable time
        assert all(t < 45 for t in times)  # 45 seconds per request max
    finally:
        await coordinator.cleanup()

@pytest.mark.performance
async def test_memory_usage():
    """Test memory usage during report generation"""
    import psutil
    import os
    
    process = psutil.Process(os.getpid())
    coordinator = BaseMCPAgent("main-coordinator")
    await coordinator.initialize()
    
    try:
        # Measure initial memory
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Generate report
        response = await coordinator.call_agent(
            "main-coordinator",
            "get-github-report",
            {"org_name": settings.github_org_name}
        )
        
        # Measure peak memory
        peak_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Memory increase should be reasonable (less than 500MB)
        assert peak_memory - initial_memory < 500
    finally:
        await coordinator.cleanup()

@pytest.mark.performance
async def test_rate_limiting():
    """Test GitHub API rate limiting handling"""
    import time
    coordinator = BaseMCPAgent("main-coordinator")
    await coordinator.initialize()
    
    try:
        # Make multiple requests in quick succession
        for _ in range(3):
            start_time = time.time()
            response = await coordinator.call_agent(
                "main-coordinator",
                "get-github-report",
                {"org_name": settings.github_org_name}
            )
            end_time = time.time()
            
            # Should handle rate limiting gracefully
            assert response is not None
            # Allow time for rate limit reset
            await asyncio.sleep(1)
    finally:
        await coordinator.cleanup()

@pytest.mark.performance
def test_startup_time():
    """Test agent startup performance"""
    import time
    
    # Measure time to start each agent
    agent_types = ["core-agent", "github-agent", "web-interface-agent", "main-coordinator"]
    startup_times = {}
    
    for agent_type in agent_types:
        start_time = time.time()
        agent = BaseMCPAgent(agent_type)
        asyncio.run(agent.initialize())
        end_time = time.time()
        
        startup_time = end_time - start_time
        startup_times[agent_type] = startup_time
        
        # Each agent should start in under 2 seconds
        assert startup_time < 2
        
        # Cleanup
        asyncio.run(agent.cleanup())
