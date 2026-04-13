# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GitHub Report is an MCP (Model Context Protocol) server that generates GitHub organization activity reports. It has a dual architecture: a **multi-agent MCP system** for interactive use and a **standalone FastAPI server** for automated report generation via GitHub Actions. Reports are published to GitHub Pages.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the FastAPI server
python -m uvicorn src.agent_mcp_demo.server:app --reload --host 127.0.0.1 --port 8000

# Start all MCP agents (core, github, web, coordinator)
./start.sh start
./start.sh status
./start.sh stop

# Run all tests (pytest.ini configures verbose + coverage automatically)
pytest

# Run a single test file
pytest tests/agent_mcp_demo/utils/test_report_publisher.py -v

# Run a single test function
pytest tests/agent_mcp_demo/utils/test_report_publisher.py::test_publish_report_success -v

# Docker
docker-compose up --build
```

## Architecture

### Dual-Mode Design

`server.py` serves two purposes:
1. **Standalone function** (`github_report_api()`) — collects metrics directly via GitHub API, used by GitHub Actions workflows
2. **MCP + FastAPI server** — provides web endpoints on port 8000 with scheduled report generation

Both paths collect the same metrics (commits, PRs, issues) but via different mechanisms.

### Multi-Agent System (`src/agent_mcp_demo/agents/`)

- **`base.py`** — Base agent class with retry logic and lifecycle management
- **`github_agent.py`** — GitHub API integration, exposes metrics as MCP tools
- **`web_interface_agent.py`** — HTTP endpoints + report formatting, acts as both MCP server and client
- **`main_coordinator.py`** — Orchestrates inter-agent communication
- **`core_agent.py`** — Note operations (demo/reference implementation)
- **`config.py`** — Pydantic `Settings` class, loads from `.env` file

### Shared Utilities (`src/agent_mcp_demo/utils/`)

- **`commit_metrics.py`**, **`pr_metrics.py`**, **`issue_metrics.py`** — GitHub data collection (used by both standalone and agent paths)
- **`iteration_info.py`** — Fetches sprint/iteration data from GitHub Projects V2 via GraphQL
- **`report_publisher.py`** — Generates HTML reports, writes to `docs/` for GitHub Pages
- **`git_operations.py`** — Automated git commit/push for report deployment
- **`report_scheduler.py`** — APScheduler-based scheduling at iteration boundaries

### Key Patterns

- All timestamps use configurable timezone (defaults to `America/New_York` / Detroit EDT/EST)
- Iteration schedule is managed via YAML and synced from GitHub Projects by the `sync-iteration-schedule.yml` workflow
- User identification matches commits to org members via GitHub API, email addresses, and username patterns
- New agents inherit from `BaseMCPAgent` and register tools via `@server.list_tools()` / `@server.call_tool()` decorators

## Configuration

Requires a `.env` file in the project root:
```
GITHUB_TOKEN=...          # required — needs repo, read:org, read:user scopes
GITHUB_ORG_NAME=...       # required
GITHUB_ITERATION_START=   # optional — overrides Project-based iteration dates
GITHUB_ITERATION_END=
GITHUB_ITERATION_NAME=
```

## Testing

- **92 tests** across 5 test files, all using pytest with pytest-asyncio
- Tests mock external services (GitHub API, git operations) — no real credentials needed
- `pytest.ini` sets `PYTHONPATH=src` and injects test env vars automatically
- Markers: `@pytest.mark.integration`, `@pytest.mark.slow`, `@pytest.mark.network`

## CI/CD Workflows (`.github/workflows/`)

- **`generate-iteration-report.yml`** — triggers report generation
- **`deploy-pages.yml`** — publishes `docs/` to GitHub Pages
- **`sync-iteration-schedule.yml`** — syncs iteration schedule from GitHub Projects to YAML
