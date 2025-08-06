import pytest
import asyncio
import time
from typing import Dict, List
from agent_mcp_demo.agents.base import BaseMCPAgent
from agent_mcp_demo.agents.types import GitHubData, IterationInfo
from agent_mcp_demo.agents.config import settings

@pytest.mark.integration
@pytest.fixture
async def running_agents():
    """Fixture to start all agents for integration testing"""
    agents = {
        "core": BaseMCPAgent("core-agent"),
        "github": BaseMCPAgent("github-agent"),
        "web": BaseMCPAgent("web-interface-agent"),
        "coordinator": BaseMCPAgent("main-coordinator")
    }
    
    # Start all agents
    tasks = []
    for name, agent in agents.items():
        task = asyncio.create_task(agent.initialize())
        tasks.append(task)
    
    await asyncio.gather(*tasks)
    yield agents
    
    # Cleanup
    tasks = []
    for agent in agents.values():
        task = asyncio.create_task(agent.cleanup())
        tasks.append(task)
    await asyncio.gather(*tasks)

@pytest.mark.integration
async def test_end_to_end_report_generation(running_agents):
    """Test the complete flow of report generation"""
    coordinator = running_agents["coordinator"]
    
    # Request report generation
    response = await coordinator.call_agent(
        "main-coordinator",
        "get-github-report",
        {"org_name": settings.github_org_name}
    )
    
    assert response is not None
    assert isinstance(response, list)
    assert len(response) > 0
    
    # Verify report content
    report_text = response[0].text
    assert "GitHub Organization:" in report_text
    assert "SUMMARY" in report_text
    assert "DETAILED ACTIVITY" in report_text

@pytest.mark.integration
async def test_agent_communication_chain(running_agents):
    """Test the communication chain between agents"""
    coordinator = running_agents["coordinator"]
    
    # Step 1: Get iteration info from GitHub agent
    iteration_info = await coordinator.call_agent(
        "github-agent",
        "get-iteration-info",
        {"org_name": settings.github_org_name}
    )
    assert iteration_info is not None
    
    # Step 2: Get GitHub data using iteration info
    github_data = await coordinator.call_agent(
        "github-agent",
        "get-github-data",
        {
            "org_name": settings.github_org_name,
            "iteration_info": iteration_info[0].text if iteration_info else None
        }
    )
    assert github_data is not None
    
    # Step 3: Generate report using web interface agent
    report = await coordinator.call_agent(
        "web-interface-agent",
        "generate-report",
        {
            "org_name": settings.github_org_name,
            "iteration_info": iteration_info[0].text if iteration_info else None,
            "github_data": github_data[0].text if github_data else None
        }
    )
    assert report is not None

@pytest.mark.integration
async def test_error_propagation(running_agents):
    """Test error handling and propagation between agents"""
    coordinator = running_agents["coordinator"]
    
    # Test with invalid organization
    with pytest.raises(Exception) as exc_info:
        await coordinator.call_agent(
            "github-agent",
            "get-github-data",
            {"org_name": "invalid-org-name"}
        )
    assert "error" in str(exc_info.value).lower()
    
    # Test with missing token
    original_token = settings.github_token
    settings.github_token = ""
    try:
        with pytest.raises(Exception) as exc_info:
            await coordinator.call_agent(
                "github-agent",
                "get-github-data",
                {"org_name": settings.github_org_name}
            )
        assert "token" in str(exc_info.value).lower()
    finally:
        settings.github_token = original_token
