#!/bin/bash

# Default configuration
VENV_DIR="venv"
LOG_DIR="logs"
PID_DIR="run"

# Create necessary directories
mkdir -p "$LOG_DIR" "$PID_DIR"

# Function to check if a process is running
is_running() {
    local pid=$1
    [ -f "$pid" ] && ps -p $(cat "$pid") > /dev/null 2>&1
}

# Function to start an agent
start_agent() {
    local name=$1
    local script=$2
    local pid_file="$PID_DIR/${name}.pid"
    local log_file="$LOG_DIR/${name}.log"

    if is_running "$pid_file"; then
        echo "⚠️  $name is already running."
        return
    fi

    echo "🚀 Starting $name..."
    source "$VENV_DIR/bin/activate"
    if [ "$name" = "web" ]; then
        uvicorn agent_mcp_demo.agents.web_interface_agent:app --host 0.0.0.0 --port 8000 > "$log_file" 2>&1 &
    else
        PYTHONPATH=$PYTHONPATH:$(pwd)/src python -m agent_mcp_demo.agents.$(basename "${script%.*}") > "$log_file" 2>&1 &
    fi
    echo $! > "$pid_file"
    echo "✅ $name started (PID: $(cat $pid_file))"
}

# Function to stop an agent
stop_agent() {
    local name=$1
    local pid_file="$PID_DIR/${name}.pid"

    if [ -f "$pid_file" ]; then
        if is_running "$pid_file"; then
            echo "🛑 Stopping $name (PID: $(cat $pid_file))..."
            kill $(cat "$pid_file")
            rm "$pid_file"
            echo "✅ $name stopped"
        else
            echo "⚠️  $name is not running, cleaning up stale PID file"
            rm "$pid_file"
        fi
    else
        echo "ℹ️  $name is not running"
    fi
}

# Function to show status of all agents
show_status() {
    echo "📊 Agent Status:"
    for name in "core" "github" "web" "coordinator"; do
        local pid_file="$PID_DIR/${name}.pid"
        if [ -f "$pid_file" ]; then
            if is_running "$pid_file"; then
                echo "✅ $name is running (PID: $(cat $pid_file))"
            else
                echo "❌ $name is not running (stale PID file)"
            fi
        else
            echo "❌ $name is not running"
        fi
    done
}

# Function to setup the environment
setup_env() {
    echo "🔧 Setting up virtual environment..."
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
    source "$VENV_DIR/bin/activate"
    pip install -e .
    echo "✅ Virtual environment setup complete"
}

# Function to clean everything
clean() {
    echo "🧹 Cleaning up..."
    rm -f "$LOG_DIR"/* "$PID_DIR"/* 2>/dev/null || true
    rm -rf "$VENV_DIR"
    echo "✨ Clean up complete"
}

# Main command handling
case "$1" in
    start)
        setup_env
        start_agent "core" "src/agent_mcp_demo/agents/core_agent.py"
        start_agent "github" "src/agent_mcp_demo/agents/github_agent.py"
        start_agent "web" "src/agent_mcp_demo/agents/web_interface_agent.py"
        start_agent "coordinator" "src/agent_mcp_demo/agents/main_coordinator.py"
        echo "🌟 All agents started. Access the web interface at: http://localhost:8000"
        ;;
    stop)
        stop_agent "coordinator"
        stop_agent "web"
        stop_agent "github"
        stop_agent "core"
        echo "🛑 All agents stopped"
        ;;
    restart)
        $0 stop
        sleep 2
        $0 start
        ;;
    clean)
        $0 stop
        clean
        ;;
    fresh)
        $0 clean
        $0 start
        ;;
    status)
        show_status
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|clean|fresh|status}"
        echo "  start   - Start all agents"
        echo "  stop    - Stop all agents"
        echo "  restart - Restart all agents"
        echo "  status  - Show status of all agents"
        exit 1
        ;;
esac

exit 0