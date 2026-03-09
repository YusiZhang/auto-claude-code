"""CLI entry points for auto-claude-code."""

import argparse
import sys

from acc.db import create_task, init_db, list_tasks


def cmd_run(args: argparse.Namespace) -> None:
    """Start the orchestrator daemon."""
    from acc.orchestrator import main
    main()


def cmd_dashboard(args: argparse.Namespace) -> None:
    """Start the web dashboard."""
    import uvicorn
    init_db()
    uvicorn.run("dashboard.app:app", host=args.host, port=args.port, reload=False)


def cmd_add(args: argparse.Namespace) -> None:
    """Add a new task."""
    init_db()
    depends_on = None
    if args.depends_on:
        depends_on = [int(x.strip()) for x in args.depends_on.split(",")]

    task_id = create_task(
        name=args.prompt,
        description=args.description or "",
        depends_on=depends_on,
        skip_permissions=not args.no_dangerous,
        working_dir=args.working_dir or "",
    )
    print(f"Created task #{task_id}")


def cmd_status(args: argparse.Namespace) -> None:
    """Show task statuses."""
    init_db()
    tasks = list_tasks()
    if not tasks:
        print("No tasks")
        return

    for t in tasks:
        deps = f" (deps: {t['depends_on']})" if t["depends_on"] else ""
        exit_info = f" exit={t['exit_code']}" if t["exit_code"] is not None else ""
        print(f"  #{t['id']} [{t['status']}] {t['name'][:60]}{deps}{exit_info}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="acc", description="Auto Claude Code orchestrator")
    sub = parser.add_subparsers(dest="command")

    # run
    sub.add_parser("run", help="Start orchestrator daemon")

    # dashboard
    p_dash = sub.add_parser("dashboard", help="Start web dashboard")
    p_dash.add_argument("--host", default="127.0.0.1")
    p_dash.add_argument("--port", type=int, default=8420)

    # add
    p_add = sub.add_parser("add", help="Add a new task")
    p_add.add_argument("prompt", help="Task prompt for Claude")
    p_add.add_argument("--description", "-d", default="")
    p_add.add_argument("--depends-on", default="")
    p_add.add_argument("--no-dangerous", action="store_true", help="Disable --dangerously-skip-permissions")
    p_add.add_argument("--working-dir", "-w", default="")

    # status
    sub.add_parser("status", help="Show task statuses")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    handlers = {
        "run": cmd_run,
        "dashboard": cmd_dashboard,
        "add": cmd_add,
        "status": cmd_status,
    }
    handlers[args.command](args)
