"""Claude Code hook handlers for task status reporting.

Called by Claude Code hooks. Reads JSON from stdin, updates task status in ACC DB.

Usage (called by Claude Code, not directly):
    echo '{"hook_event_name":"Stop",...}' | python3 -m acc.hooks --task-id 1
"""

import json
import os
import sys


def _get_task_id() -> int | None:
    """Extract task ID from CLI args or ACC_TASK_ID env var."""
    # Check --task-id arg
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--task-id" and i + 1 < len(args):
            return int(args[i + 1])
    # Check env var
    tid = os.environ.get("ACC_TASK_ID")
    return int(tid) if tid else None


def handle_stop(task_id: int, data: dict) -> None:
    """Handle the Stop hook — Claude finished responding."""
    # Import here to avoid circular imports
    from acc.db import get_task, init_db, update_task_status

    init_db()

    task = get_task(task_id)
    if not task or task["status"] != "running":
        return

    last_message = data.get("last_assistant_message", "")
    update_task_status(task_id, "completed", exit_code=0, last_message=last_message)


def handle_notification(task_id: int, data: dict) -> None:
    """Handle the Notification hook — Claude needs attention."""
    from acc.db import get_task, init_db, update_task_status

    init_db()

    task = get_task(task_id)
    if not task or task["status"] != "running":
        return

    notification_type = data.get("notification_type", "")
    message = data.get("message", "")

    if notification_type in ("permission_prompt", "elicitation_dialog"):
        update_task_status(
            task_id, "needs_input",
            last_message=f"[{notification_type}] {message}",
        )


def main() -> None:
    task_id = _get_task_id()
    if task_id is None:
        sys.exit(0)

    # Read hook payload from stdin
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    event = data.get("hook_event_name", "")

    if event == "Stop":
        handle_stop(task_id, data)
    elif event == "Notification":
        handle_notification(task_id, data)


if __name__ == "__main__":
    main()
