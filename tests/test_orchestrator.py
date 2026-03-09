"""Tests for the orchestrator."""

import time

import pytest

import acc.orchestrator as orch
from acc.config import exit_file_path
from acc.db import create_task, get_task, list_tasks
from acc.tmux_runner import kill_session


@pytest.fixture(autouse=True)
def patch_build_command():
    original = orch._build_command
    orch._build_command = lambda task: f"echo test-output-{task['id']}"
    yield
    orch._build_command = original
    for t in list_tasks():
        kill_session(t["id"])
        exit_file_path(t["id"]).unlink(missing_ok=True)


def test_dispatch_single_task():
    tid = create_task("Test dispatch")
    orch._dispatch_tasks()

    task = get_task(tid)
    assert task["status"] == "running"

    time.sleep(2)
    orch._poll_running_tasks()

    task = get_task(tid)
    assert task["status"] == "completed"
    assert task["exit_code"] == 0


def test_chained_tasks():
    t1 = create_task("First task")
    t2 = create_task("Second task", depends_on=[t1])

    orch._dispatch_tasks()
    assert get_task(t1)["status"] == "running"
    assert get_task(t2)["status"] == "pending"

    time.sleep(2)
    orch._poll_running_tasks()
    assert get_task(t1)["status"] == "completed"

    orch._dispatch_tasks()
    assert get_task(t2)["status"] == "running"

    time.sleep(2)
    orch._poll_running_tasks()
    assert get_task(t2)["status"] == "completed"


def test_concurrency_limit():
    """With MAX_CONCURRENCY=1, only one task should run at a time."""
    t1 = create_task("Slow task 1")
    t2 = create_task("Slow task 2")

    orch._build_command = lambda task: "sleep 5"

    orch._dispatch_tasks()
    assert get_task(t1)["status"] == "running"
    assert get_task(t2)["status"] == "pending"

    # Second dispatch should not start t2
    orch._dispatch_tasks()
    assert get_task(t2)["status"] == "pending"
