"""Global memory interface for cross-task state sharing."""

import sys

from acc.db import init_db, list_memory, read_memory, write_memory


def read_all_memory() -> dict[str, str]:
    """Read all memory entries as a dict."""
    entries = list_memory()
    return {e["key"]: e["value"] for e in entries}


def render_memory_to_markdown() -> str:
    """Render all memory entries as a markdown section."""
    entries = list_memory()
    if not entries:
        return "## Global Memory\n\nNo entries yet.\n"

    lines = ["## Global Memory\n"]
    for e in entries:
        lines.append(f"- **{e['key']}**: {e['value']}")
    lines.append("")
    return "\n".join(lines)


def _cli_main() -> None:
    """CLI for memory operations: python3 -m acc.memory set KEY VALUE / get KEY"""
    init_db()
    if len(sys.argv) < 3:
        print("Usage: python3 -m acc.memory set KEY VALUE")
        print("       python3 -m acc.memory get KEY")
        print("       python3 -m acc.memory list")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "get":
        key = sys.argv[2]
        val = read_memory(key)
        if val is None:
            print(f"Key '{key}' not found")
            sys.exit(1)
        print(val)

    elif cmd == "set":
        if len(sys.argv) < 4:
            print("Usage: python3 -m acc.memory set KEY VALUE")
            sys.exit(1)
        key = sys.argv[2]
        value = " ".join(sys.argv[3:])
        task_id = None
        write_memory(key, value, task_id=task_id)
        print(f"Set {key} = {value}")

    elif cmd == "list":
        entries = list_memory()
        for e in entries:
            print(f"{e['key']} = {e['value']}")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    _cli_main()
