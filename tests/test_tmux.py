"""Tests for the tmux runner."""

import time

from acc.config import exit_file_path
from acc.tmux_runner import (
    create_session,
    get_attach_command,
    is_session_alive,
    kill_session,
    read_exit_code,
)

import pytest


@pytest.fixture(autouse=True)
def cleanup_sessions():
    yield
    for tid in [900, 901]:
        kill_session(tid)
        exit_file_path(tid).unlink(missing_ok=True)


def test_create_and_complete_session():
    name = create_session(900, "echo hello-from-test")
    assert name == "acc_task_900"
    time.sleep(2)
    code = read_exit_code(900)
    assert code == 0


def test_session_alive():
    create_session(901, "sleep 10")
    time.sleep(1)
    assert is_session_alive(901)
    kill_session(901)
    time.sleep(0.5)
    assert not is_session_alive(901)


def test_attach_command():
    cmd = get_attach_command(42)
    assert cmd == "tmux attach -t acc_task_42"


def test_failed_command_exit_code():
    create_session(900, "bash -c 'exit 1'")
    time.sleep(2)
    code = read_exit_code(900)
    assert code == 1
