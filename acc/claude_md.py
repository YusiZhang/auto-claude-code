"""Generate CLAUDE.md and .claude/settings.json for task working directories."""

import json
import os
from pathlib import Path

from acc.memory import render_memory_to_markdown


ACC_SECTION_START = "<!-- ACC:START -->"
ACC_SECTION_END = "<!-- ACC:END -->"


def generate_acc_section(task_id: int, task_name: str, working_dir: str) -> str:
    """Generate the ACC section to embed in CLAUDE.md."""
    memory_section = render_memory_to_markdown()

    acc_module_path = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(acc_module_path)

    return f"""{ACC_SECTION_START}

# Auto Claude Code — Task #{task_id}: {task_name}

This task is being managed by auto-claude-code (ACC).

{memory_section}

## Memory Commands

To read/write shared memory that persists across tasks:

```bash
# Set a memory value
uv run --project {project_root} python3 -m acc.memory set KEY VALUE

# Get a memory value
uv run --project {project_root} python3 -m acc.memory get KEY

# List all memory
uv run --project {project_root} python3 -m acc.memory list
```

## Important

- When you complete this task, update shared memory with any important findings.
- Use the memory commands above to share state with future tasks.

{ACC_SECTION_END}"""


def write_claude_md(task_id: int, task_name: str, working_dir: str) -> Path:
    """Append ACC section to CLAUDE.md, preserving existing content.

    If an ACC section already exists, it is replaced in-place.
    If no CLAUDE.md exists, one is created with just the ACC section.
    """
    acc_section = generate_acc_section(task_id, task_name, working_dir)
    wd = Path(working_dir) if working_dir else Path.cwd()
    wd.mkdir(parents=True, exist_ok=True)
    claude_md_path = wd / "CLAUDE.md"

    if claude_md_path.exists():
        existing = claude_md_path.read_text()

        if ACC_SECTION_START in existing and ACC_SECTION_END in existing:
            # Replace existing ACC section
            before = existing[: existing.index(ACC_SECTION_START)]
            after = existing[existing.index(ACC_SECTION_END) + len(ACC_SECTION_END) :]
            claude_md_path.write_text(before + acc_section + after)
        else:
            # Append ACC section
            separator = "\n\n" if existing and not existing.endswith("\n\n") else ""
            claude_md_path.write_text(existing + separator + acc_section + "\n")
    else:
        claude_md_path.write_text(acc_section + "\n")

    return claude_md_path


def generate_hooks_settings(task_id: int) -> dict:
    """Generate .claude/settings.json with ACC hooks for a task."""
    acc_module_path = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(acc_module_path)

    # The hook command: set ACC env vars and run acc.hooks
    hook_cmd = (
        f"ACC_TASK_ID={task_id} "
        f"uv run --project {project_root} python3 -m acc.hooks"
    )

    return {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": hook_cmd,
                            "timeout": 30,
                        }
                    ]
                }
            ],
            "Notification": [
                {
                    "matcher": "permission_prompt",
                    "hooks": [
                        {
                            "type": "command",
                            "command": hook_cmd,
                            "timeout": 30,
                        }
                    ]
                },
                {
                    "matcher": "elicitation_dialog",
                    "hooks": [
                        {
                            "type": "command",
                            "command": hook_cmd,
                            "timeout": 30,
                        }
                    ]
                },
            ],
        }
    }


def write_hooks_settings(task_id: int, working_dir: str) -> Path:
    """Write .claude/settings.local.json with ACC hooks into the working directory.

    Uses settings.local.json so it doesn't conflict with any committed
    .claude/settings.json in the project.
    """
    settings = generate_hooks_settings(task_id)
    wd = Path(working_dir) if working_dir else Path.cwd()
    claude_dir = wd / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings_path = claude_dir / "settings.local.json"

    # Merge with existing settings.local.json if present
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
            existing["hooks"] = settings["hooks"]
            settings = existing
        except (json.JSONDecodeError, KeyError):
            pass

    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    return settings_path
