# agent-mcp-demo MCP server

MCP server with two agents: one for API, one for JSON file

## Components

### Resources

The server implements a simple note storage system with:
- Custom note:// URI scheme for accessing individual notes
- Each note resource has a name, description and text/plain mimetype

### Prompts

The server provides a single prompt:
- summarize-notes: Creates summaries of all stored notes
  - Optional "style" argument to control detail level (brief/detailed)
  - Generates prompt combining all current notes with style preference

### Tools

The server implements one tool:
- add-note: Adds a new note to the server
  - Takes "name" and "content" as required string arguments
  - Updates server state and notifies clients of resource changes

## Agent-based system example

Agent 1: Fetch data from an API
Usage example:
result = await fetch_from_api('https://api.example.com/data')

Agent 2: Read data from a JSON file
Usage example:
result = read_from_json_file('sample_data.json')

The server exposes both agents as tools:
- fetch-api-data: Takes a URL and returns the API response
- read-json-file: Takes a file path and returns the JSON content

See src/agent_mcp_demo/server.py for implementation details.

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
   # Build and run with Docker Compose
   docker-compose up --build
   
   # Or build and run with Docker directly
   docker build -t github-report-app .
   docker run -p 8000:8000 -e GITHUB_TOKEN=your_token -e GITHUB_ORG_NAME=your_org github-report-app
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
        "/Users/jqzhao/projects/copilot-aidevday-2025",
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

For local development without Docker:

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -e .

# Start the server
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
npx @modelcontextprotocol/inspector uv --directory /Users/jqzhao/projects/copilot-aidevday-2025 run agent-mcp-demo
```


Upon launching, the Inspector will display a URL that you can access in your browser to begin debugging.