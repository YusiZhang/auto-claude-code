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


<!-- ACC:START -->

# Auto Claude Code — Task #1: Slow task 1

This task is being managed by auto-claude-code (ACC).

## Global Memory

No entries yet.


## Memory Commands

To read/write shared memory that persists across tasks:

```bash
# Set a memory value
uv run --project /Users/yusizhang/workspace/auto-claude-code python3 -m acc.memory set KEY VALUE

# Get a memory value
uv run --project /Users/yusizhang/workspace/auto-claude-code python3 -m acc.memory get KEY

# List all memory
uv run --project /Users/yusizhang/workspace/auto-claude-code python3 -m acc.memory list
```

## Important

- When you complete this task, update shared memory with any important findings.
- Use the memory commands above to share state with future tasks.

<!-- ACC:END -->
