"""Tests for the database layer."""

from acc.db import (
    create_task,
    get_dispatchable_tasks,
    get_running_tasks,
    get_task,
    list_memory,
    list_tasks,
    read_memory,
    update_task_status,
    write_memory,
)


def test_create_and_get_task():
    tid = create_task("Test task", "A description")
    task = get_task(tid)
    assert task is not None
    assert task["name"] == "Test task"
    assert task["description"] == "A description"
    assert task["status"] == "pending"
    assert task["depends_on"] == []


def test_list_tasks():
    create_task("Task A")
    create_task("Task B")
    tasks = list_tasks()
    assert len(tasks) >= 2


def test_task_dependencies():
    t1 = create_task("First")
    t2 = create_task("Second", depends_on=[t1])

    dispatchable = get_dispatchable_tasks()
    ids = [t["id"] for t in dispatchable]
    assert t1 in ids
    assert t2 not in ids

    update_task_status(t1, "completed", exit_code=0)
    dispatchable = get_dispatchable_tasks()
    ids = [t["id"] for t in dispatchable]
    assert t2 in ids


def test_update_task_status():
    tid = create_task("Status test")
    update_task_status(tid, "running")
    task = get_task(tid)
    assert task["status"] == "running"
    assert task["started_at"] is not None

    update_task_status(tid, "completed", exit_code=0)
    task = get_task(tid)
    assert task["status"] == "completed"
    assert task["completed_at"] is not None
    assert task["exit_code"] == 0


def test_get_running_tasks():
    tid = create_task("Running test")
    update_task_status(tid, "running")
    running = get_running_tasks()
    assert any(t["id"] == tid for t in running)


def test_memory_crud():
    write_memory("test_key", "test_value", task_id=1)
    assert read_memory("test_key") == "test_value"

    write_memory("test_key", "updated", task_id=2)
    assert read_memory("test_key") == "updated"

    entries = list_memory()
    assert any(e["key"] == "test_key" for e in entries)

    assert read_memory("nonexistent") is None
