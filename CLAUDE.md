# Auto Claude Code (ACC)

Task orchestration layer that wraps Claude Code CLI. Queues sequential/dependent tasks, runs them in isolated tmux sessions, provides global memory between tasks, and offers a web dashboard.

## Quick Start

```bash
# Start orchestrator (polls and dispatches tasks)
uv run python3 -m acc run

# Start dashboard (web UI on port 8420)
uv run python3 -m acc dashboard

# Add tasks via CLI
uv run python3 -m acc add "Build a hello world app"
uv run python3 -m acc add "Add tests" --depends-on 1

# Check status
uv run python3 -m acc status
```

## Architecture

- `acc/config.py` — paths, polling interval, concurrency limit
- `acc/db.py` — SQLite CRUD for tasks and global memory
- `acc/tmux_runner.py` — libtmux wrapper for session management
- `acc/orchestrator.py` — async polling loop that dispatches tasks
- `acc/memory.py` — cross-task memory interface + CLI
- `acc/claude_md.py` — generates CLAUDE.md per task with memory snapshot
- `acc/cli.py` — CLI entry points
- `dashboard/app.py` — FastAPI + HTMX web dashboard

## Running Tests

```bash
uv run python3 -m pytest tests/ -v
```