"""Configuration constants for auto-claude-code."""

import os
from pathlib import Path

POLL_INTERVAL_S = 3
MAX_CONCURRENCY = 1


def acc_home() -> Path:
    """Central data directory: ~/.acc/ (override with ACC_HOME env var)."""
    return Path(os.environ.get("ACC_HOME", Path.home() / ".acc"))


def _data_dir() -> Path:
    d = acc_home()
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    _data_dir()
    return acc_home() / "acc.db"


def tmp_dir() -> Path:
    d = acc_home() / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def exit_file_path(task_id: int) -> Path:
    return tmp_dir() / f"acc_task_{task_id}.exit"


def tmux_session_name(task_id: int) -> str:
    return f"acc_task_{task_id}"
