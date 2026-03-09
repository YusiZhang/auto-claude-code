"""SQLite database layer for task management and global memory."""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from acc.config import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    depends_on TEXT NOT NULL DEFAULT '[]',
    skip_permissions INTEGER NOT NULL DEFAULT 0,
    working_dir TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    exit_code INTEGER,
    last_message TEXT
);

CREATE TABLE IF NOT EXISTS global_memory (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_by_task_id INTEGER,
    updated_at TEXT NOT NULL
);
"""

MIGRATIONS = [
    "ALTER TABLE tasks ADD COLUMN last_message TEXT",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = get_conn()
    conn.executescript(SCHEMA)
    # Run migrations for existing databases
    for migration in MIGRATIONS:
        try:
            conn.execute(migration)
        except sqlite3.OperationalError:
            pass  # Column already exists
    conn.commit()
    conn.close()


def create_task(
    name: str,
    description: str = "",
    depends_on: list[int] | None = None,
    skip_permissions: bool = True,
    working_dir: str = "",
) -> int:
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO tasks (name, description, depends_on, skip_permissions, working_dir, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            name,
            description,
            json.dumps(depends_on or []),
            int(skip_permissions),
            working_dir,
            _now(),
        ),
    )
    conn.commit()
    task_id = cur.lastrowid
    conn.close()
    return task_id


def get_task(task_id: int) -> dict[str, Any] | None:
    conn = get_conn()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    return _row_to_dict(row)


def list_tasks() -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def update_task_status(
    task_id: int,
    status: str,
    exit_code: int | None = None,
    last_message: str | None = None,
) -> None:
    conn = get_conn()
    now = _now()
    if status == "running":
        conn.execute(
            "UPDATE tasks SET status = ?, started_at = ? WHERE id = ?",
            (status, now, task_id),
        )
    elif status in ("completed", "failed", "cancelled"):
        conn.execute(
            "UPDATE tasks SET status = ?, completed_at = ?, exit_code = ?, last_message = ? WHERE id = ?",
            (status, now, exit_code, last_message, task_id),
        )
    elif status == "needs_input":
        conn.execute(
            "UPDATE tasks SET status = ?, last_message = ? WHERE id = ?",
            (status, last_message, task_id),
        )
    else:
        conn.execute(
            "UPDATE tasks SET status = ? WHERE id = ?",
            (status, task_id),
        )
    conn.commit()
    conn.close()


def get_dispatchable_tasks() -> list[dict[str, Any]]:
    """Return pending tasks whose dependencies are all completed."""
    conn = get_conn()
    pending = conn.execute(
        "SELECT * FROM tasks WHERE status = 'pending' ORDER BY id"
    ).fetchall()

    completed_ids = {
        row["id"]
        for row in conn.execute(
            "SELECT id FROM tasks WHERE status = 'completed'"
        ).fetchall()
    }
    conn.close()

    result = []
    for row in pending:
        deps = json.loads(row["depends_on"])
        if all(dep_id in completed_ids for dep_id in deps):
            result.append(_row_to_dict(row))
    return result


def get_running_tasks() -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE status = 'running' ORDER BY id"
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


# --- Global Memory ---


def write_memory(key: str, value: str, task_id: int | None = None) -> None:
    conn = get_conn()
    conn.execute(
        """INSERT INTO global_memory (key, value, updated_by_task_id, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value=?, updated_by_task_id=?, updated_at=?""",
        (key, value, task_id, _now(), value, task_id, _now()),
    )
    conn.commit()
    conn.close()


def read_memory(key: str) -> str | None:
    conn = get_conn()
    row = conn.execute(
        "SELECT value FROM global_memory WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else None


def list_memory() -> list[dict[str, Any]]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM global_memory ORDER BY key").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_working_dirs() -> list[str]:
    """Return distinct working dirs ordered by most recently used."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT DISTINCT working_dir FROM tasks
           WHERE working_dir != ''
           ORDER BY id DESC"""
    ).fetchall()
    conn.close()
    return [row["working_dir"] for row in rows]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    if "depends_on" in d:
        d["depends_on"] = json.loads(d["depends_on"])
    return d
