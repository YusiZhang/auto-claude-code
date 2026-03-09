# auto-claude-code

Task orchestration layer for Claude Code CLI.  
It runs Claude tasks in `tmux`, supports dependency chains, shares task memory, and provides a FastAPI dashboard for live status.

## Features

- Queue tasks from CLI or web dashboard
- Dependency-aware execution (`depends_on`)
- Task execution in detached `tmux` sessions
- Claude hook integration (`Stop`, `Notification`) for status updates
- Shared key/value memory across tasks
- Live dashboard (HTMX refresh every 3s)

## Requirements

- Python `>=3.12`
- [`uv`](https://docs.astral.sh/uv/)
- `tmux`
- `claude` CLI available in `PATH`

## Quick Start

```bash
git clone <your-repo-url>
cd auto-claude-code
./start.sh
```

This script will:

1. install dependencies with `uv sync`
2. initialize the database
3. start the orchestrator
4. start the dashboard at `http://127.0.0.1:8420`

## Manual Start

```bash
uv sync
uv run python3 -m acc run
```

In another terminal:

```bash
uv run python3 -m acc dashboard --host 127.0.0.1 --port 8420
```

## CLI Usage

```bash
# Add a task
uv run python3 -m acc add "Implement auth flow" -d "Use JWT and refresh tokens" -w /path/to/project

# Add task with dependencies
uv run python3 -m acc add "Write integration tests" --depends-on 1,2 -w /path/to/project

# Disable dangerous mode for a task
uv run python3 -m acc add "Refactor config loading" --no-dangerous -w /path/to/project

# Show task statuses
uv run python3 -m acc status
```

## Dashboard

Start with:

```bash
uv run python3 -m acc dashboard
```

Open `http://127.0.0.1:8420` to:

- create and cancel tasks
- inspect task status / last message
- view and edit shared memory
- copy tmux attach commands for active tasks

## Data Location

By default, ACC stores data in:

- `~/.acc/acc.db`
- `~/.acc/tmp/acc_task_<id>.exit`

Override with:

```bash
export ACC_HOME=/custom/path
```

## How It Works

- Orchestrator polls every 3s and dispatches ready tasks
- Each task runs in a dedicated session: `acc_task_<id>`
- `.claude/settings.local.json` is written in each task working directory for hooks
- `CLAUDE.md` is generated/updated with ACC memory instructions and snapshot
- Hook events update task state (`completed`, `needs_input`) in SQLite

## Development

Run tests:

```bash
uv run --extra dev pytest
```

Project layout:

- `acc/`: core orchestrator, DB, hooks, CLI, tmux runner
- `dashboard/`: FastAPI app and templates
- `docs/ARCHITECTURE.md`: detailed design
- `tests/`: unit tests
