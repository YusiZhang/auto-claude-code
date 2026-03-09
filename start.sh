#!/usr/bin/env bash
set -euo pipefail

# Auto Claude Code — single startup script
# Starts both the orchestrator daemon and the web dashboard.
# Usage: ./start.sh

# Ensure we're in the project root
cd "$(dirname "$0")"

# Check for uv
if ! command -v uv &>/dev/null; then
    echo "Error: uv is not installed. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Check for tmux
if ! command -v tmux &>/dev/null; then
    echo "Error: tmux is not installed. Install it with: brew install tmux"
    exit 1
fi

# Install dependencies
echo "Installing dependencies..."
uv sync --quiet

# Ensure DB is initialized
uv run python3 -c "from acc.db import init_db; init_db()"

# Start orchestrator in background
echo "Starting orchestrator..."
uv run python3 -m acc run &
ORCH_PID=$!

# Start dashboard in foreground
echo "Starting dashboard at http://127.0.0.1:8420"
echo ""
echo "Press Ctrl+C to stop both services."
echo ""

cleanup() {
    echo ""
    echo "Shutting down..."
    kill "$ORCH_PID" 2>/dev/null || true
    wait "$ORCH_PID" 2>/dev/null || true
    echo "Done."
}
trap cleanup EXIT INT TERM

uv run python3 -m acc dashboard
