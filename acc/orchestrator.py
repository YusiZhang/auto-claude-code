"""Orchestrator daemon — polls for tasks and dispatches them via tmux."""

import asyncio
import logging
import os

from acc.claude_md import write_claude_md, write_hooks_settings
from acc.config import MAX_CONCURRENCY, POLL_INTERVAL_S, exit_file_path
from acc.db import (
    get_dispatchable_tasks,
    get_running_tasks,
    init_db,
    update_task_status,
)
from acc.tmux_runner import create_session, is_session_alive, read_exit_code

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ACC] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("acc")


def _build_command(task: dict) -> str:
    """Build the claude CLI command for a task."""
    parts = ["claude"]
    if task.get("skip_permissions"):
        parts.append("--dangerously-skip-permissions")

    prompt = task["name"]
    if task.get("description"):
        prompt += f"\n\n{task['description']}"

    # Escape single quotes in prompt
    escaped = prompt.replace("'", "'\\''")
    parts.append(f"'{escaped}'")

    return " ".join(parts)


def _poll_running_tasks() -> None:
    """Check running tasks for completion or crash.

    Status can be updated by two mechanisms:
    1. Claude Code hooks (Stop/Notification) — update DB directly via acc.hooks
    2. Exit file + tmux session death — fallback detection here
    """
    for task in get_running_tasks():
        tid = task["id"]

        if not is_session_alive(tid):
            # Tmux session ended — check exit file for the code
            exit_code = read_exit_code(tid)
            exit_file_path(tid).unlink(missing_ok=True)
            if exit_code is not None:
                # Only override if hook hasn't already marked it completed
                status = "completed" if exit_code == 0 else "failed"
                update_task_status(tid, status, exit_code=exit_code)
                log.info("Task %d %s (exit code %d, from exit file)", tid, status, exit_code)
            else:
                update_task_status(tid, "failed", exit_code=-1)
                log.warning("Task %d tmux session died unexpectedly", tid)


def _dispatch_tasks() -> None:
    """Launch dispatchable tasks up to the concurrency limit."""
    running_count = len(get_running_tasks())
    available_slots = MAX_CONCURRENCY - running_count

    if available_slots <= 0:
        return

    dispatchable = get_dispatchable_tasks()
    for task in dispatchable[:available_slots]:
        tid = task["id"]
        working_dir = task.get("working_dir") or os.getcwd()

        # Generate CLAUDE.md and hooks settings in working directory
        write_claude_md(tid, task["name"], working_dir)
        write_hooks_settings(tid, working_dir)

        # Build and launch command
        command = f"cd '{working_dir}' && {_build_command(task)}"
        update_task_status(tid, "running")
        create_session(tid, command)
        log.info("Dispatched task %d: %s", tid, task["name"][:60])


async def run_loop() -> None:
    """Main orchestrator loop."""
    init_db()
    log.info("Orchestrator started (poll=%ds, concurrency=%d)", POLL_INTERVAL_S, MAX_CONCURRENCY)

    while True:
        try:
            _poll_running_tasks()
            _dispatch_tasks()
        except Exception:
            log.exception("Error in orchestrator loop")

        await asyncio.sleep(POLL_INTERVAL_S)


def main() -> None:
    asyncio.run(run_loop())


if __name__ == "__main__":
    main()
