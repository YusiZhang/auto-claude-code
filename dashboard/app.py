"""FastAPI dashboard for auto-claude-code."""

import os

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from acc.config import tmux_session_name
from acc.db import (
    create_task,
    get_recent_working_dirs,
    get_task,
    init_db,
    list_memory,
    list_tasks,
    update_task_status,
    write_memory,
)
from acc.tmux_runner import kill_session

app = FastAPI(title="Auto Claude Code Dashboard")

templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(__file__), "templates")
)


@app.on_event("startup")
def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    tasks = list_tasks()
    memory = list_memory()
    recent_dirs = get_recent_working_dirs()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "tasks": tasks,
            "memory": memory,
            "tmux_session_name": tmux_session_name,
            "recent_dirs": recent_dirs,
        },
    )


@app.get("/api/tasks")
async def api_list_tasks():
    return list_tasks()


@app.post("/api/tasks")
async def api_create_task(
    name: str = Form(...),
    description: str = Form(""),
    depends_on: str = Form(""),
    skip_permissions: str = Form(""),
    working_dir: str = Form(""),
):
    dep_list = None
    if depends_on.strip():
        dep_list = [int(x.strip()) for x in depends_on.split(",") if x.strip()]

    task_id = create_task(
        name=name,
        description=description,
        depends_on=dep_list,
        skip_permissions=skip_permissions == "on",
        working_dir=working_dir,
    )
    return {"id": task_id, "status": "created"}


@app.post("/api/tasks/{task_id}/cancel")
async def api_cancel_task(task_id: int):
    task = get_task(task_id)
    if not task:
        return {"error": "Task not found"}, 404
    if task["status"] == "running":
        kill_session(task_id)
    update_task_status(task_id, "cancelled")
    return {"id": task_id, "status": "cancelled"}


@app.get("/api/memory")
async def api_list_memory():
    return list_memory()


@app.post("/api/memory")
async def api_write_memory(
    key: str = Form(...),
    value: str = Form(...),
):
    write_memory(key, value)
    return {"key": key, "status": "written"}


# JSON endpoint for working dir autocomplete refresh
@app.get("/api/working-dirs")
async def api_working_dirs():
    return get_recent_working_dirs()


# HTMX partial for live data refresh (tasks + memory, no forms)
@app.get("/partials/live", response_class=HTMLResponse)
async def partials_live(request: Request):
    return templates.TemplateResponse(
        "live.html",
        {
            "request": request,
            "tasks": list_tasks(),
            "memory": list_memory(),
            "tmux_session_name": tmux_session_name,
        },
    )
