# GitHub Report MCP Server

This project is a Model Context Protocol (MCP) server implementation that generates GitHub organization reports. The server is split into multiple agents that communicate using MCP to provide a scalable and maintainable architecture.

## Features

### Core Features
- **Modular Architecture**: Split into specialized agents communicating via MCP
- **Real-time Data Processing**: Fetches and processes GitHub data in real-time
- **Comprehensive Reports**: Detailed activity reports including commits, issues, and PRs
- **Sprint/Iteration Support**: Filter data by specific time periods
- **Web Interface**: User-friendly web interface for accessing reports

### Agent Components
- **Core Agent**: Handles basic note operations and state management
- **GitHub Agent**: Manages all GitHub API interactions
- **Web Interface Agent**: Provides HTTP endpoints and report generation
- **Main Coordinator**: Orchestrates communication between agents
- **User Identification**: Smart matching of commits to users via GitHub API, email addresses, and username patterns

### Iteration-Based Reporting
- **Sprint Integration**: Integrates with GitHub Projects for iteration/sprint-based filtering
- **Date Range Filtering**: Filters commits and issues based on iteration start and end dates
- **Timezone Support**: All timestamps are displayed in Detroit timezone (EDT/EST)

### Report Components
1. **Summary Statistics**:
   - Total repositories processed
   - Total commits and issues analyzed
   - Activity filtered by iteration dates

2. **Per-User Activity**:
   - Commit counts and details
   - Assigned issues tracking
   - Closed issues monitoring

3. **Detailed Breakdown**:
   - Commit messages with timestamps
   - Issue assignments with status
   - Issue closure tracking

## Prerequisites

- Python 3.9 or higher
- GitHub Personal Access Token with required permissions
- GitHub organization membership

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/jqzhao-umich/github-report.git
   cd github-report
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Create a `.env` file in the project root with:

```env
GITHUB_TOKEN=your_github_token
GITHUB_ORG_NAME=your_organization_name
```

Optional environment variables for iteration settings:
```env
GITHUB_ITERATION_START=2023-08-01
GITHUB_ITERATION_END=2023-08-15
GITHUB_ITERATION_NAME=Sprint 1
```

## Running the Server

### Quick Start (Recommended)

Use the provided `start.sh` script to manage all agents:

```bash
# Start all agents
./start.sh start

# Check status of all agents
./start.sh status

# Restart all agents
./start.sh restart

# Stop all agents
./start.sh stop
```

The script provides:
- 🔄 Automatic virtual environment setup
- 📝 Individual agent logging (in `logs` directory)
- 📊 Status monitoring
- 🔍 Process management with PID files
- 🧹 Clean process handling and shutdown

All agent logs are stored in the `logs` directory:
- `logs/core.log` - Core agent logs
- `logs/github.log` - GitHub agent logs
- `logs/web.log` - Web interface agent logs
- `logs/coordinator.log` - Main coordinator logs

Once started, access the web interface at: http://localhost:8000

### Manual Start (Alternative)

If you prefer to run agents manually, open four terminal windows and run the following commands (make sure your virtual environment is activated in each):

1. Start the core agent:
   ```bash
   python src/agent_mcp_demo/agents/core_agent.py
   ```

2. Start the GitHub agent:
   ```bash
   python src/agent_mcp_demo/agents/github_agent.py
   ```

3. Start the web interface agent:
   ```bash
   python src/agent_mcp_demo/agents/web_interface_agent.py
   ```

4. Start the main coordinator:
   ```bash
   python src/agent_mcp_demo/agents/main_coordinator.py
   ```

Note: The manual method doesn't provide the logging and process management features available in the start script.

## Development

### Project Structure

```
src/agent_mcp_demo/
├── agents/               # MCP agent implementations
│   ├── base.py          # Base agent class
│   ├── config.py        # Configuration management
│   ├── core_agent.py    # Core agent
│   ├── github_agent.py  # GitHub integration
│   ├── main_coordinator.py  # Agent coordinator
│   └── web_interface_agent.py  # Web interface
├── routes/              # FastAPI route handlers
│   └── reports.py       # Report generation endpoints
├── utils/               # Utility modules
│   ├── git_operations.py    # Git commit/push operations
│   ├── report_publisher.py  # Report publishing logic
│   └── report_scheduler.py  # Automated scheduling
├── server.py            # FastAPI server
└── logging_config.json  # Logging configuration

tests/                   # Test suite (92 tests)
├── agent_mcp_demo/
│   ├── agents/          # Agent tests
│   └── utils/           # Utility tests
└── test_iteration_schedule_system.py
```

### Adding a New Agent

1. Create a new agent class inheriting from BaseMCPAgent:
```python
from .base import BaseMCPAgent

class MyNewAgent(BaseMCPAgent):
    def __init__(self):
        super().__init__("my-new-agent")
```

2. Define the agent's tools:
```python
@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="my-tool",
            description="Tool description",
            inputSchema={
                "type": "object",
                "properties": {
                    "param": {"type": "string"}
                }
            }
        )
    ]
```

3. Implement tool handlers:
```python
@server.call_tool()
async def handle_call_tool(
    name: str, 
    arguments: dict | None
) -> list[types.TextContent]:
    if name == "my-tool":
        # Tool implementation
        return [types.TextContent(type="text", text="result")]
```

### Error Handling

- Use specific exception types from `types.py`
- Implement retry logic using `BaseMCPAgent.call_agent`
- Log errors with appropriate severity

### Configuration

- Add new settings to `config.py`
- Use environment variables with fallback values
- Document new settings in README.md

## Testing

### Test Coverage Overview

The project has **comprehensive test coverage with 92 tests** across all critical infrastructure components:

- **ReportPublisher Tests** (13 tests) - Report generation, overwrite logic, duplicate handling
- **POST Body Endpoint Tests** (14 tests) - Request validation, error handling, background tasks  
- **ReportScheduler Tests** (18 tests) - Iteration detection, timezone handling, automated scheduling
- **Iteration Schedule System Tests** (22 tests) - YAML operations, date logic, DST transitions
- **GitOperations Tests** (25 tests) - Commit/push operations, error handling, branch management

### Running Tests

#### Using Docker (Recommended)

Run tests in the containerized environment:

```bash
# Run all tests
docker compose exec github-report-app python -m pytest

# Run tests with verbose output
docker compose exec github-report-app python -m pytest -v

# Run specific test file
docker compose exec github-report-app python -m pytest tests/agent_mcp_demo/utils/test_report_publisher.py -v

# Run tests with coverage
docker compose exec github-report-app python -m pytest --cov=agent_mcp_demo --cov-report=term-missing
```

#### Local Development

1. Set up the test environment:
   ```bash
   # Create and activate virtual environment
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate

   # Install all dependencies including test requirements
   pip install -r requirements.txt
   ```

2. Basic Test Commands:
   ```bash
   # Run all tests
   pytest

   # Run tests with verbose output
   pytest -v

   # Run tests and show print statements
   pytest -s

   # Run tests with coverage report
   pytest --cov=agent_mcp_demo --cov-report=term-missing
   ```

3. Run Tests by Component:
   ```bash
   # Report publishing infrastructure
   pytest tests/agent_mcp_demo/utils/test_report_publisher.py -v
   
   # Automated scheduling
   pytest tests/agent_mcp_demo/utils/test_report_scheduler.py -v
   
   # Git operations
   pytest tests/agent_mcp_demo/utils/test_git_operations.py -v
   
   # Iteration schedule system
   pytest tests/test_iteration_schedule_system.py -v
   
   # POST endpoint tests
   pytest tests/agent_mcp_demo/agents/test_web_interface_publishing.py -v

   # Run specific test function
   pytest tests/agent_mcp_demo/utils/test_report_publisher.py::test_publish_report_success -v
   ```

4. Coverage and Reporting:
   ```bash
   pytest --cov=agent_mcp_demo --cov-report=html
   ```

### Test Structure

```
tests/
├── agent_mcp_demo/
│   ├── agents/
│   │   └── test_web_interface_publishing.py  # POST endpoint tests (14 tests)
│   └── utils/
│       ├── test_report_publisher.py          # Report generation tests (13 tests)
│       ├── test_report_scheduler.py          # Scheduler tests (18 tests)
│       └── test_git_operations.py            # Git operations tests (25 tests)
└── test_iteration_schedule_system.py         # Schedule system tests (22 tests)
```

**Key Test Features:**
- Comprehensive mocking for isolated unit tests
- Timezone-aware datetime testing (EST/EDT, UTC)
- Async test support with pytest-asyncio
- Temporary file fixtures for safe test isolation
- Error handling and edge case coverage

### Writing Tests

1. Add tests in the appropriate test file
2. Use pytest fixtures for common setup
3. Mark integration tests with @pytest.mark.integration
4. Use mocking for external services

## Technical Implementation

The application is built using:
- **FastAPI**: Modern, fast web framework for building APIs
- **MCP**: Model Context Protocol for agent communication
- **PyGithub**: Python library for GitHub API integration
- **Uvicorn**: Lightweight ASGI server implementation
- **Pydantic**: Data validation using Python type annotations
- **Python-dotenv**: Environment variable management
- **Pytest**: Testing framework with async support
- **PyGithub**: GitHub API v3 integration
- **Docker**: Containerized deployment for easy setup
- **Environment Configuration**: Flexible configuration via environment variables or .env file

## Configuration

### GitHub Integration Setup

The agent includes a GitHub report feature that requires environment variables to be set:

1. **Generate a GitHub Personal Access Token:**
   - Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
   - Click "Generate new token (classic)"
   - Select scopes: `repo`, `read:org`, `read:user`
   - Copy the generated token

2. **Set Environment Variables:**

   **Option A: Using the setup script (recommended):**
   ```bash
   ./setup_env.sh
   ```
   This will prompt you for your GitHub token and organization name.

   **Option B: Manual setup:**
   ```bash
   export GITHUB_TOKEN="your_github_token_here"
   export GITHUB_ORG_NAME="your_organization_name"
   ```

   **Option C: Using .env file:**
   Create a `.env` file in the project root:
   ```
   GITHUB_TOKEN=your_github_token_here
   GITHUB_ORG_NAME=your_organization_name
   ```
   Then load it with:
   ```bash
   python load_env.py
   ```

### GitHub Projects Integration Setup (Optional)

For iteration-based reporting, you can configure GitHub Projects integration:

1. **Ensure your GitHub token has the required scopes:**
   - `repo` (for repository access)
   - `read:org` (for organization access)
   - `read:user` (for user information)

2. **Add GitHub Projects Environment Variables (Optional):**
   
   **Option A: Add to .env file:**
   ```
   GITHUB_ITERATION_START=2024-01-15T00:00:00Z
   GITHUB_ITERATION_END=2024-01-29T23:59:59Z
   GITHUB_ITERATION_NAME=Current Sprint
   ```
   
   **Option B: Manual setup:**
   ```bash
   export GITHUB_ITERATION_START="2024-01-15T00:00:00Z"
   export GITHUB_ITERATION_END="2024-01-29T23:59:59Z"
   export GITHUB_ITERATION_NAME="Current Sprint"
   ```

   **Note:** The application will look for the "Michigan App Team Task Board" project in your organization. If iteration dates are not configured, the report will show all-time data instead of iteration-filtered data.

### Iteration-Based Reporting

The application now supports iteration-based reporting that:

1. **Fetches current iteration information** from GitHub Projects ("Michigan App Team Task Board")
2. **Filters commits and issues** to only show those within the current iteration timeframe
3. **Displays iteration details** at the top of the report including:
   - Iteration name
   - Start and end dates
   - Project path

**Example Report Output:**
```
hello world
GitHub Organization: WeMoAD-umich

============================================================
CURRENT ITERATION INFORMATION
============================================================
Iteration Name: Sprint 2024.1
Start Date: 2024-01-15T00:00:00Z
End Date: 2024-01-29T23:59:59Z
Project Path: WeMoAD-umich/Michigan App Team Task Board
============================================================

Processed 5 repositories
Filtered by iteration: 2024-01-15 to 2024-01-29

User                 | Commits | Assigned Issues
--------------------------------------------------
jqzhao-umich        |      15 |              3
teammate1           |       8 |              2
teammate2           |      12 |              1
```

3. **Access the GitHub Report:**

   **Option A: Using Docker (Recommended):**
   ```bash
   # Build the Docker image
   docker build -t github-report .

   # Run the container in foreground (recommended for development)
   docker run --name github-report-container --env-file .env -p 8000:8000 github-report uvicorn src.agent_mcp_demo.server:app --host 0.0.0.0 --port 8000

   # To stop the container
   docker stop github-report-container

   # To remove the container (after stopping)
   docker rm github-report-container

   # To rebuild and restart (after making changes)
   docker build -t github-report .
   docker run --name github-report-container --env-file .env -p 8000:8000 github-report uvicorn src.agent_mcp_demo.server:app --host 0.0.0.0 --port 8000
   ```

   **Option B: Local Development:**
   ```bash
   # Activate virtual environment
   source venv/bin/activate
   
   # Start the server
   python -m uvicorn src.agent_mcp_demo.server:app --host 127.0.0.1 --port 8000
   ```

   Then visit: `http://localhost:8000/github-report`

## Quickstart

### Install

#### Claude Desktop

On MacOS: `~/Library/Application\ Support/Claude/claude_desktop_config.json`
On Windows: `%APPDATA%/Claude/claude_desktop_config.json`

<details>
  <summary>Development/Unpublished Servers Configuration</summary>
  ```
  "mcpServers": {
    "agent-mcp-demo": {
      "command": "uv",
      "args": [
        "--directory",
        "/Users/jqzhao/projects/github-report",
        "run",
        "agent-mcp-demo"
      ]
    }
  }
  ```
</details>

<details>
  <summary>Published Servers Configuration</summary>
  ```
  "mcpServers": {
    "agent-mcp-demo": {
      "command": "uvx",
      "args": [
        "agent-mcp-demo"
      ]
    }
  }
  ```
</details>

## Development

### Docker Development

The project is containerized for easy development and deployment:

```bash
# Build and start the application
docker-compose up --build

# Run in detached mode
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the application
docker-compose down
```

### Local Development

For local development, you have two options:

#### 1. Using the start script (Recommended)

The `start.sh` script provides a developer-friendly environment:

```bash
# Start all agents with logging
./start.sh start

# Monitor agent status
./start.sh status

# View logs in real-time
tail -f logs/*.log

# Restart after code changes
./start.sh restart
```

#### 2. Manual setup without Docker

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e .

# Start the server (in separate terminals)
python -m uvicorn src.agent_mcp_demo.server:app --reload --host 127.0.0.1 --port 8000
```

### Building and Publishing

To prepare the package for distribution:

1. Sync dependencies and update lockfile:
```bash
uv sync
```

2. Build package distributions:
```bash
uv build
```

This will create source and wheel distributions in the `dist/` directory.

3. Publish to PyPI:
```bash
uv publish
```

Note: You'll need to set PyPI credentials via environment variables or command flags:
- Token: `--token` or `UV_PUBLISH_TOKEN`
- Or username/password: `--username`/`UV_PUBLISH_USERNAME` and `--password`/`UV_PUBLISH_PASSWORD`

### Debugging

Since MCP servers run over stdio, debugging can be challenging. For the best debugging
experience, we strongly recommend using the [MCP Inspector](https://github.com/modelcontextprotocol/inspector).


You can launch the MCP Inspector via [`npm`](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm) with this command:

```bash
npx @modelcontextprotocol/inspector uv --directory /Users/jqzhao/projects/github-report run agent-mcp-demo
```


Upon launching, the Inspector will display a URL that you can access in your browser to begin debugging.