"""Tmux session management for running Claude Code tasks."""

import libtmux

from acc.config import exit_file_path, tmux_session_name


def _get_server() -> libtmux.Server:
    return libtmux.Server()


def create_session(task_id: int, command: str) -> str:
    """Create a tmux session that runs a command and writes exit code to a file.

    Returns the session name.
    """
    server = _get_server()
    name = tmux_session_name(task_id)
    exit_file = exit_file_path(task_id)

    # Remove stale exit file if it exists
    exit_file.unlink(missing_ok=True)

    # Wrap command to capture exit code
    wrapped = f'{command} ; echo $? > {exit_file}'

    server.new_session(
        session_name=name,
        window_command=wrapped,
        detach=True,
    )
    return name


def is_session_alive(task_id: int) -> bool:
    """Check if a tmux session for a task is still running."""
    server = _get_server()
    name = tmux_session_name(task_id)
    return server.has_session(name)


def kill_session(task_id: int) -> None:
    """Kill a tmux session for a task."""
    server = _get_server()
    name = tmux_session_name(task_id)
    try:
        session = server.sessions.get(session_name=name)
        if session:
            session.kill()
    except Exception:
        pass


def get_attach_command(task_id: int) -> str:
    """Return the shell command to attach to a task's tmux session."""
    return f"tmux attach -t {tmux_session_name(task_id)}"


def read_exit_code(task_id: int) -> int | None:
    """Read the exit code from a task's exit file. Returns None if not yet written."""
    exit_file = exit_file_path(task_id)
    if not exit_file.exists():
        return None
    try:
        return int(exit_file.read_text().strip())
    except (ValueError, OSError):
        return None
