# Auto Claude Code (ACC) — Architecture Document

## 1. Overview

Auto Claude Code (ACC) is a task orchestration layer that wraps the Claude Code CLI. It solves the problem of running multiple Claude Code sessions in sequence or in dependency chains, with shared state between them, while providing visibility into what's happening.

```
┌─────────────────────────────────────────────────────────────┐
│                        User Interface                       │
│                                                             │
│   CLI (python -m acc)          Dashboard (localhost:8420)    │
│   ├── add "prompt"             ├── Task table + status      │
│   ├── status                   ├── Create task form         │
│   ├── run                      ├── Cancel tasks             │
│   └── dashboard                ├── Memory viewer/editor     │
│                                └── HTMX auto-refresh (3s)   │
└────────────┬──────────────────────────────┬──────────────────┘
             │                              │
             ▼                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     SQLite Database                          │
│                                                             │
│   tasks table              global_memory table              │
│   ├── id, name, status     ├── key (PK)                    │
│   ├── depends_on (JSON)    ├── value                       │
│   ├── skip_permissions     ├── updated_by_task_id          │
│   ├── working_dir          └── updated_at                  │
│   ├── exit_code                                            │
│   ├── last_message         ◄──────── written by hooks ───┐ │
│   └── timestamps                                         │ │
└────────────┬──────────────────────────────┬──────────────┬──┘
             │                              │              │
             ▼                              │              │
┌──────────────────────────┐                │              │
│   Orchestrator Daemon    │                │              │
│                          │                │              │
│   Async loop (3s poll):  │                │              │
│   1. Poll running tasks  │                │              │
│      └─ check tmux alive │                │              │
│      └─ (fallback only)  │                │              │
│   2. Dispatch ready tasks│                │              │
│      └─ generate CLAUDE.md◄───────────────┘              │
│      └─ write hooks cfg  │         (memory snapshot)     │
│      └─ build CLI command│                               │
│      └─ create tmux sess.│                               │
└──────────┬───────────────┘                               │
           │                                               │
           ▼                                               │
┌──────────────────────────────────────────────────────────────┐
│                       tmux Sessions                          │
│                                                              │
│   acc_task_1                 acc_task_2                       │
│   ┌────────────────────┐     ┌────────────────────┐          │
│   │ cd /project &&     │     │ cd /project &&     │          │
│   │ claude --dangerous │     │ claude --dangerous │          │
│   │   "prompt..."      │     │   "prompt..."      │          │
│   │ ; echo $? > exit   │     │ ; echo $? > exit   │          │
│   └────────┬───────────┘     └────────┬───────────┘          │
│            │                          │                      │
│            ▼                          ▼                      │
│   Claude Code Hooks (.claude/settings.local.json)            │
│   ├── Stop hook ──────► acc.hooks ──► DB: completed ─────────┘
│   └── Notification hook ► acc.hooks ► DB: needs_input        │
│                                                              │
│   Users can attach:  tmux attach -t acc_task_1               │
└──────────────────────────────────────────────────────────────┘
```

## 2. Design Principles

1. **Hooks as primary signal, polling as fallback**: Task completion is detected via Claude Code hooks — the `Stop` hook fires when Claude finishes responding and writes the status directly to the DB. The orchestrator's polling loop only handles the fallback case where the tmux session dies unexpectedly (crash, user kill) without hooks firing.

2. **Exit files as fallback IPC**: When a tmux session finishes (Claude exits entirely), it writes its exit code to `~/.acc/tmp/acc_task_{id}.exit`. The orchestrator reads these files only as a fallback — the primary completion signal comes from hooks.

3. **Lazy configuration**: All config paths are computed via functions (not module-level constants) so that `ACC_HOME` can be changed at runtime — critical for test isolation.

4. **Synchronous SQLite**: Despite the orchestrator being async, all DB access is synchronous via `sqlite3` (not `aiosqlite`). This is intentional — the DB operations are fast local I/O, and synchronous access avoids the complexity of async connection management. `aiosqlite` is available as a dependency for future use.

5. **Preserve user files**: The CLAUDE.md generator uses HTML comment sentinels (`<!-- ACC:START -->` / `<!-- ACC:END -->`) to append/replace only its section, never destroying existing project documentation.

## 3. Component Deep Dive

### 3.1 Configuration (`acc/config.py`)

All paths are derived lazily from a single root:

```
~/.acc/ (override with ACC_HOME env var)
├── acc.db                    # SQLite database
└── tmp/
    ├── acc_task_1.exit       # Exit code files (ephemeral)
    ├── acc_task_2.exit
    └── ...
```

| Constant | Value | Purpose |
|----------|-------|---------|
| `POLL_INTERVAL_S` | `3` | How often the orchestrator checks for task updates |
| `MAX_CONCURRENCY` | `1` | Maximum tasks running simultaneously |

Key functions:
- `db_path() -> Path` — SQLite database location
- `exit_file_path(task_id) -> Path` — Where tmux writes `$?` after command finishes
- `tmux_session_name(task_id) -> str` — Deterministic session name: `acc_task_{id}`

### 3.2 Database Layer (`acc/db.py`)

SQLite with WAL mode for concurrent read/write safety. Two tables:

#### `tasks` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | Auto-increment |
| `name` | TEXT | The prompt sent to Claude |
| `description` | TEXT | Additional context appended to prompt |
| `status` | TEXT | `pending` → `running` → `completed` / `failed` / `cancelled` / `needs_input` |
| `depends_on` | TEXT | JSON array of task IDs, e.g. `[1, 3]` |
| `skip_permissions` | INTEGER | `1` = use `--dangerously-skip-permissions` |
| `working_dir` | TEXT | Directory to `cd` into before running Claude |
| `created_at` | TEXT | ISO8601 UTC timestamp |
| `started_at` | TEXT | Set when status → `running` |
| `completed_at` | TEXT | Set when status → `completed`/`failed`/`cancelled` |
| `exit_code` | INTEGER | Process exit code (`0` = success, `-1` = tmux crash) |
| `last_message` | TEXT | Claude's last response (from Stop hook) or notification message |

#### `global_memory` table

| Column | Type | Notes |
|--------|------|-------|
| `key` | TEXT PK | Memory entry identifier |
| `value` | TEXT | Arbitrary string value |
| `updated_by_task_id` | INTEGER | Which task last wrote this entry |
| `updated_at` | TEXT | ISO8601 UTC timestamp |

#### Key operations

```
create_task()            → INSERT, returns task_id
get_dispatchable_tasks() → SELECT pending tasks WHERE all deps are completed
get_running_tasks()      → SELECT tasks WHERE status = 'running'
update_task_status()     → UPDATE with appropriate timestamp fields
write_memory()           → INSERT ... ON CONFLICT DO UPDATE (upsert)
```

#### Task status state machine

```
                    ┌──────────┐
                    │ pending  │
                    └────┬─────┘
                         │  _dispatch_tasks()
                         ▼
                    ┌──────────┐
           ┌────────│ running  │────────┐
           │        └──┬────┬──┘        │
           │           │    │           │
     Stop hook    Notification   tmux died / cancel
     fires        hook fires           │
           │           │               │
           ▼           ▼               ▼
     ┌──────────┐ ┌─────────────┐ ┌───────────┐
     │completed │ │ needs_input │ │  failed   │
     └──────────┘ └──────┬──────┘ └───────────┘
                         │                ▲
                    user provides         │
                    input in tmux    ┌────┴─────┐
                         │          │ cancelled │
                         ▼          └──────────┘
                    ┌──────────┐
                    │ running  │  (Stop hook fires again)
                    └──────────┘
```

**Hook-driven transitions:**
- `running` → `completed`: Stop hook fires, meaning Claude finished responding
- `running` → `needs_input`: Notification hook fires (`permission_prompt` or `elicitation_dialog`)
- `needs_input` → `running`: User attaches to tmux and provides input; Claude resumes; on next Stop hook, it transitions to `completed`

**Fallback transitions (no hooks):**
- `running` → `failed`: tmux session dies without hooks firing (crash, OOM, etc.)
- `running` → `completed`/`failed`: exit file written after Claude process exits entirely

### 3.3 Tmux Runner (`acc/tmux_runner.py`)

Thin wrapper around `libtmux`. Each task gets its own detached tmux session.

**Session lifecycle:**

1. `create_session(task_id, command)`:
   - Deletes any stale exit file from a previous run
   - Wraps the command: `{command} ; echo $? > /path/to/acc_task_{id}.exit`
   - Creates a detached tmux session named `acc_task_{id}`

2. While running:
   - `is_session_alive(task_id)` — checks if the tmux session still exists
   - User can attach: `tmux attach -t acc_task_{id}`

3. On completion:
   - `read_exit_code(task_id)` — reads the integer from the exit file
   - Orchestrator cleans up the exit file after reading

**Why tmux?** It provides a real PTY, so Claude Code runs exactly as it would in a terminal. Users can attach to watch or interact with a running task in real time.

### 3.4 Claude Code Hooks (`acc/hooks.py`)

ACC uses Claude Code's hook system to detect task completion and human-input requests **without polling**. Hooks are shell commands that Claude Code invokes at lifecycle events, receiving JSON on stdin.

#### How hooks are installed

Before dispatching a task, the orchestrator writes `.claude/settings.local.json` into the working directory. This file is project-scoped and local-only (not committed to git), so it doesn't conflict with any existing `.claude/settings.json`.

```json
{
  "hooks": {
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "ACC_TASK_ID=42 uv run --project /path/to/acc python3 -m acc.hooks",
        "timeout": 30
      }]
    }],
    "Notification": [
      {
        "matcher": "permission_prompt",
        "hooks": [{ "type": "command", "command": "..." }]
      },
      {
        "matcher": "elicitation_dialog",
        "hooks": [{ "type": "command", "command": "..." }]
      }
    ]
  }
}
```

The hook command bakes in `ACC_TASK_ID` as an environment variable so the hook script knows which task to update. The database location is fixed at `~/.acc/acc.db` (or `ACC_HOME` env var).

#### Hook events

| Hook | When it fires | What `acc.hooks` does |
|------|---------------|----------------------|
| **Stop** | Claude finishes a response and is about to wait for input | Reads `last_assistant_message` from stdin JSON. Marks task `completed` in DB. |
| **Notification** (`permission_prompt`) | Claude needs permission to run a tool | Marks task `needs_input` with the permission message. |
| **Notification** (`elicitation_dialog`) | Claude is asking the user a question | Marks task `needs_input` with the question. |

#### Stdin JSON schema (Stop hook)

```json
{
  "session_id": "abc123",
  "hook_event_name": "Stop",
  "stop_hook_active": false,
  "last_assistant_message": "I've completed the git init. Repository created.",
  "transcript_path": "~/.claude/projects/.../session.jsonl",
  "cwd": "/path/to/project"
}
```

#### Stdin JSON schema (Notification hook)

```json
{
  "session_id": "abc123",
  "hook_event_name": "Notification",
  "notification_type": "permission_prompt",
  "message": "Claude needs your permission to use Bash",
  "title": "Permission needed"
}
```

### 3.5 Orchestrator (`acc/orchestrator.py`)

The orchestrator is an async loop that runs forever, polling every 3 seconds:

```python
while True:
    _poll_running_tasks()    # Fallback: check for tmux deaths
    _dispatch_tasks()        # Launch new tasks
    await asyncio.sleep(3)
```

#### `_poll_running_tasks()` — fallback only

Most status transitions are handled by hooks (see 3.4). The polling loop only handles the edge case where the tmux session dies without hooks firing:

For each task with `status = 'running'`:

1. Check if tmux session is still alive
2. If dead → read exit file (if any) → mark `completed` or `failed` accordingly
3. If dead with no exit file → mark `failed` with exit code `-1`

Tasks already marked `completed` or `needs_input` by hooks are not in the `running` state, so they're skipped.

#### `_dispatch_tasks()`

1. Count currently running tasks
2. Calculate available slots: `MAX_CONCURRENCY - running_count`
3. Get dispatchable tasks (pending with all deps completed)
4. For each task (up to available slots):
   - Generate `CLAUDE.md` in the task's working directory (with memory snapshot)
   - Write `.claude/settings.local.json` with hook configuration
   - Build command: `cd '{working_dir}' && claude [--dangerously-skip-permissions] '{prompt}'`
   - Update DB status to `running`
   - Create tmux session

#### Command construction

```
cd '/path/to/project' && claude --dangerously-skip-permissions 'Build a REST API

Additional context from description field'
```

The prompt is constructed by concatenating `task.name` and `task.description` with a double newline.

### 3.6 Memory System (`acc/memory.py` + `acc/claude_md.py`)

Memory enables tasks to share state. A task can write a key-value pair that subsequent tasks will see.

#### Two access paths

**1. From inside a Claude task** (via CLI):
```bash
# Claude Code can run these commands during a task
uv run --project /path/to/acc python3 -m acc.memory set API_KEY sk-xxx
uv run --project /path/to/acc python3 -m acc.memory get API_KEY
uv run --project /path/to/acc python3 -m acc.memory list
```

**2. From the dashboard/API**:
```
POST /api/memory  {"key": "API_KEY", "value": "sk-xxx"}
GET  /api/memory
```

#### CLAUDE.md injection

Before each task starts, the orchestrator generates a `CLAUDE.md` that includes:
- A snapshot of all current memory entries
- Instructions on how to use the memory CLI
- Task identification

**Preservation logic** in `write_claude_md()`:

```
Existing CLAUDE.md?
├── No  → Create new file with ACC section only
├── Yes, has ACC section → Replace ACC section in-place
└── Yes, no ACC section  → Append ACC section at the end
```

ACC sections are delimited by:
```html
<!-- ACC:START -->
...ACC content...
<!-- ACC:END -->
```

### 3.7 Dashboard (`dashboard/app.py` + `dashboard/templates/index.html`)

FastAPI app serving a single-page dashboard with HTMX for live updates.

#### API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/` | HTML dashboard page |
| `GET` | `/api/tasks` | JSON list of all tasks |
| `POST` | `/api/tasks` | Create new task (form-encoded) |
| `POST` | `/api/tasks/{id}/cancel` | Cancel task (kills tmux if running) |
| `GET` | `/api/memory` | JSON list of all memory entries |
| `POST` | `/api/memory` | Write a memory entry (form-encoded) |
| `GET` | `/partials/live` | HTMX partial for auto-refresh (tasks + memory only) |

#### Live updates

The dynamic content (tasks table + memory table) lives in a dedicated `#live-data` div that polls `/partials/live` every 3 seconds:
```html
<div id="live-data" hx-get="/partials/live" hx-trigger="every 3s" hx-swap="innerHTML">
```

Forms are **outside** this div and are never replaced by polling, so user input is preserved while typing. The templates are split:
- `index.html` — full page with static forms + `{% include "live.html" %}`
- `live.html` — tasks table + memory table only (returned by `/partials/live`)

#### UI components

- **Task creation form**: Name, description, dependencies, working directory, dangerous mode toggle
- **Task table**: ID, name (truncated), status badge (including `needs_input`), `last_message` preview, dependency list, tmux attach command (for running and needs_input tasks), cancel button
- **Memory table**: Key-value pairs with "updated by" task reference
- **Memory form**: Set key-value pairs manually

#### Status badges

| Status | Color | Meaning |
|--------|-------|---------|
| `pending` | Gray | Waiting for dependencies |
| `running` | Green | Claude is actively working |
| `completed` | Blue | Claude finished (Stop hook fired) |
| `failed` | Red | Task errored or tmux died |
| `cancelled` | Orange | Manually cancelled |
| `needs_input` | Yellow | Claude is waiting for human input (permission or question) |

### 3.8 CLI (`acc/cli.py` + `acc/__main__.py`)

Entry point: `python -m acc <command>`

| Command | Description | Key flags |
|---------|-------------|-----------|
| `run` | Start orchestrator daemon | — |
| `dashboard` | Start web UI | `--host` (default `127.0.0.1`), `--port` (default `8420`) |
| `add "prompt"` | Queue a new task | `--depends-on 1,2`, `--no-dangerous`, `-d "description"`, `-w /path` |
| `status` | Print task list | — |

By default, tasks are created with `--dangerously-skip-permissions` enabled. Use `--no-dangerous` to disable it.

## 4. Data Flow: Complete Task Lifecycle

```
1. User creates task
   CLI:       python -m acc add "Build auth module" --depends-on 1
   Dashboard: POST /api/tasks {name: "Build auth module", depends_on: [1]}
                │
                ▼
2. Task stored in SQLite
   tasks: {id: 2, name: "Build auth module", status: "pending", depends_on: [1]}
                │
                ▼
3. Orchestrator poll cycle (every 3s)
   _dispatch_tasks():
     - Task 2 is pending, but depends_on=[1]
     - Is task 1 completed? No → skip
     - ...later, task 1 completes...
     - Is task 1 completed? Yes → task 2 is dispatchable
                │
                ▼
4. Dispatch
   a) Generate CLAUDE.md in working directory
      - Snapshot current global memory
      - Include memory CLI commands
      - Preserve any existing CLAUDE.md content
   b) Write .claude/settings.local.json with hooks config
      - Stop hook → runs acc.hooks with ACC_TASK_ID=2
      - Notification hooks → permission_prompt, elicitation_dialog
   c) Build command:
      cd '/project' && claude --dangerously-skip-permissions 'Build auth module'
   d) Update DB: status → "running", set started_at
   e) Create tmux session: acc_task_2
                │
                ▼
5. Claude runs in tmux
   - Real PTY, user can attach: tmux attach -t acc_task_2
   - Claude reads CLAUDE.md, sees memory and instructions
   - Claude can write memory: python3 -m acc.memory set AUTH_TYPE jwt
   - Claude loads hooks from .claude/settings.local.json
                │
                ├─── Claude finishes responding ───┐
                │                                  ▼
                │                        Stop hook fires
                │                        acc.hooks reads stdin JSON
                │                        Extracts last_assistant_message
                │                        DB: status → "completed"
                │                                  │
                ├─── Claude needs permission ──────┤
                │                                  ▼
                │                        Notification hook fires
                │                        acc.hooks reads stdin JSON
                │                        DB: status → "needs_input"
                │                        Dashboard shows yellow badge
                │                        User attaches to tmux, responds
                │                        Claude resumes → Stop hook fires
                │                                  │
                ▼                                  │
6. Downstream tasks unblocked  ◄───────────────────┘
   - Task 2 is now "completed"
   - Any task with depends_on=[2] becomes dispatchable

Fallback path (if hooks don't fire):
   - Orchestrator detects tmux session died
   - Reads exit file if present
   - Marks task completed or failed accordingly
```

## 5. File Map

```
auto-claude-code/
├── acc/
│   ├── __init__.py          # Package marker
│   ├── __main__.py          # python -m acc entry point
│   ├── config.py            # Lazy path config + constants
│   ├── db.py                # SQLite schema + CRUD + migrations
│   ├── tmux_runner.py       # libtmux session wrapper
│   ├── orchestrator.py      # Main daemon loop (dispatch + fallback polling)
│   ├── hooks.py             # Claude Code hook handler (Stop + Notification)
│   ├── memory.py            # Memory read/write + CLI
│   ├── claude_md.py         # CLAUDE.md + .claude/settings.local.json generation
│   └── cli.py               # Argument parsing + command handlers
├── dashboard/
│   ├── __init__.py          # Package marker
│   ├── app.py               # FastAPI routes (form-encoded endpoints)
│   └── templates/
│       ├── index.html       # Full page: forms + includes live.html
│       └── live.html        # HTMX partial: tasks table + memory table
├── tests/
│   ├── __init__.py          # Package marker
│   ├── conftest.py          # Shared fixture: isolated ACC_HOME per test
│   ├── test_db.py           # 6 tests: CRUD, deps, memory
│   ├── test_tmux.py         # 4 tests: session lifecycle, exit codes
│   └── test_orchestrator.py # 3 tests: dispatch, chaining, concurrency
├── pyproject.toml           # Project metadata + dependencies
├── CLAUDE.md                # Project documentation
└── .gitignore               # Excludes .venv/, __pycache__/
```

## 6. Dependency Graph (module level)

```
cli.py ──────► orchestrator.py ──────► tmux_runner.py ──► config.py
  │                 │                                        ▲
  │                 ├──► claude_md.py ──► memory.py           │
  │                 │       │               │                 │
  │                 │       └──► json (hooks settings)        │
  │                 │                                         │
  │                 └──► db.py ─────────────┘─────────────────┘
  │                       ▲                        ▲
  └──► db.py              │                        │
                          │                        │
dashboard/app.py ─────────┘──► tmux_runner.py      │
                              ► config.py          │
                                                   │
hooks.py (called by Claude Code) ──► db.py ────────┘
  └─ reads stdin JSON, updates task status
```

## 7. Limitations & Future Work

| Limitation | Notes |
|------------|-------|
| **Concurrency = 1** | `MAX_CONCURRENCY` is hardcoded to 1. Can be increased but tasks share the same `CLAUDE.md` generation which may conflict. |
| **No task retry** | Failed tasks stay failed. No automatic retry mechanism. |
| **No log capture** | Task output lives only in the tmux scrollback buffer. No persistent log storage. `last_message` captures Claude's final response only. |
| **Hooks require Claude Code 2.1+** | The Stop and Notification hooks require a recent Claude Code version. Older versions will fall back to exit file detection. |
| **No auth on dashboard** | The web dashboard has no authentication. Bind to localhost only. |
| **Synchronous DB in async loop** | DB calls block the event loop briefly. Not a problem at current scale. |
| **Single machine** | tmux sessions are local. No distributed task execution. |
| **Hook config is per-project** | `.claude/settings.local.json` is written to the working directory. If two tasks share the same working directory, they'll overwrite each other's hook config. |
