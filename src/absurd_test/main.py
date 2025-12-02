"""FastAPI app that queues agent tasks via Absurd."""

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from absurd_sdk import Absurd
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select

from absurd_test.config import get_settings
from absurd_test.db import get_async_session
from absurd_test.models import AgentJob, Webhook

PKG_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=PKG_DIR / "templates")

absurd_app: Absurd | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global absurd_app
    settings = get_settings()
    absurd_app = Absurd(settings.database_url, queue_name="agent_tasks")
    yield
    absurd_app = None


app = FastAPI(title="Absurd Agent Demo", lifespan=lifespan)


# --- HTML Pages ---


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Show the main page with job submission form and job list."""
    settings = get_settings()
    async with get_async_session() as session:
        result = await session.execute(
            select(AgentJob).order_by(AgentJob.created_at.desc()).limit(3)
        )
        jobs = result.scalars().all()
    return templates.TemplateResponse("index.html", {"request": request, "jobs": jobs, "kiosk": settings.kiosk})


@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    """Show the about page."""
    return templates.TemplateResponse("about.html", {"request": request})


@app.get("/partials/jobs", response_class=HTMLResponse)
async def partials_jobs(request: Request):
    """Return just the job list HTML fragment for HTMX polling."""
    async with get_async_session() as session:
        result = await session.execute(
            select(AgentJob).order_by(AgentJob.created_at.desc()).limit(3)
        )
        jobs = result.scalars().all()
    return templates.TemplateResponse("partials/jobs.html", {"request": request, "jobs": jobs})


@app.post("/submit", response_class=HTMLResponse)
async def submit_job(request: Request, prompt: str = Form(...), tag: str = Form("")):
    """Submit a new agent job to the queue from the web UI."""
    task_id = str(uuid.uuid4())
    tag = tag.strip() or None

    async with get_async_session() as session:
        job = AgentJob(task_id=task_id, prompt=prompt, tag=tag, status="pending")
        session.add(job)
        await session.commit()

    absurd_app.spawn(
        "run-agent",
        {"task_id": task_id, "prompt": prompt, "tag": tag},
        queue="agent_tasks",
    )

    async with get_async_session() as session:
        result = await session.execute(
            select(AgentJob).order_by(AgentJob.created_at.desc()).limit(3)
        )
        jobs = result.scalars().all()
    return templates.TemplateResponse("partials/jobs.html", {"request": request, "jobs": jobs})


@app.get("/job/{task_id}", response_class=HTMLResponse)
async def get_job(request: Request, task_id: str):
    """View a specific job's details."""
    async with get_async_session() as session:
        result = await session.execute(select(AgentJob).where(AgentJob.task_id == task_id))
        job = result.scalar_one_or_none()
    return templates.TemplateResponse("job.html", {"request": request, "job": job})


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Admin page for managing webhooks."""
    async with get_async_session() as session:
        result = await session.execute(select(Webhook).order_by(Webhook.created_at.desc()))
        webhooks = result.scalars().all()
    return templates.TemplateResponse("admin.html", {"request": request, "webhooks": webhooks})


@app.get("/partials/webhooks", response_class=HTMLResponse)
async def partials_webhooks(request: Request):
    """Return just the webhooks list HTML fragment for HTMX."""
    async with get_async_session() as session:
        result = await session.execute(select(Webhook).order_by(Webhook.created_at.desc()))
        webhooks = result.scalars().all()
    return templates.TemplateResponse("partials/webhooks.html", {"request": request, "webhooks": webhooks})


@app.post("/admin/webhooks", response_class=HTMLResponse)
async def create_webhook_form(request: Request, tag: str = Form(...), url: str = Form(...)):
    """Create a webhook from the admin form."""
    async with get_async_session() as session:
        webhook = Webhook(tag=tag.strip(), url=url.strip())
        session.add(webhook)
        await session.commit()

    async with get_async_session() as session:
        result = await session.execute(select(Webhook).order_by(Webhook.created_at.desc()))
        webhooks = result.scalars().all()
    return templates.TemplateResponse("partials/webhooks.html", {"request": request, "webhooks": webhooks})


@app.delete("/admin/webhooks/{webhook_id}", response_class=HTMLResponse)
async def delete_webhook_form(request: Request, webhook_id: int):
    """Delete a webhook from the admin page."""
    async with get_async_session() as session:
        result = await session.execute(select(Webhook).where(Webhook.id == webhook_id))
        webhook = result.scalar_one_or_none()
        if webhook:
            await session.delete(webhook)
            await session.commit()

    async with get_async_session() as session:
        result = await session.execute(select(Webhook).order_by(Webhook.created_at.desc()))
        webhooks = result.scalars().all()
    return templates.TemplateResponse("partials/webhooks.html", {"request": request, "webhooks": webhooks})


# --- JSON API ---


class TaskCreate(BaseModel):
    prompt: str
    tag: Optional[str] = None


class WebhookCreate(BaseModel):
    tag: str
    url: str


@app.post("/api/tasks")
async def create_task(task: TaskCreate):
    """Create a new task via API."""
    task_id = str(uuid.uuid4())
    tag = task.tag.strip() if task.tag else None

    async with get_async_session() as session:
        job = AgentJob(task_id=task_id, prompt=task.prompt, tag=tag, status="pending")
        session.add(job)
        await session.commit()

    absurd_app.spawn(
        "run-agent",
        {"task_id": task_id, "prompt": task.prompt, "tag": tag},
        queue="agent_tasks",
    )

    return {"task_id": task_id}


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    """Get task status and result."""
    async with get_async_session() as session:
        result = await session.execute(select(AgentJob).where(AgentJob.task_id == task_id))
        job = result.scalar_one_or_none()

    if not job:
        return {"error": "task not found"}

    return {
        "task_id": job.task_id,
        "prompt": job.prompt,
        "tag": job.tag,
        "result": job.result,
        "status": job.status,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    """Delete a task."""
    async with get_async_session() as session:
        result = await session.execute(select(AgentJob).where(AgentJob.task_id == task_id))
        job = result.scalar_one_or_none()
        if not job:
            return {"error": "task not found"}

        await session.delete(job)
        await session.commit()

    return {"deleted": task_id}


@app.delete("/jobs/{task_id}", response_class=HTMLResponse)
async def delete_job_ui(request: Request, task_id: str):
    """Delete a job from UI and return updated job list."""
    async with get_async_session() as session:
        result = await session.execute(select(AgentJob).where(AgentJob.task_id == task_id))
        job = result.scalar_one_or_none()
        if job:
            await session.delete(job)
            await session.commit()

    async with get_async_session() as session:
        result = await session.execute(
            select(AgentJob).order_by(AgentJob.created_at.desc()).limit(3)
        )
        jobs = result.scalars().all()
    return templates.TemplateResponse("partials/jobs.html", {"request": request, "jobs": jobs})


@app.post("/api/webhooks")
async def create_webhook(webhook: WebhookCreate):
    """Register a webhook for a tag."""
    async with get_async_session() as session:
        wh = Webhook(tag=webhook.tag.strip(), url=webhook.url.strip())
        session.add(wh)
        await session.commit()
        await session.refresh(wh)
        webhook_id = wh.id

    return {"id": webhook_id, "tag": webhook.tag, "url": webhook.url}


@app.get("/api/webhooks")
async def list_webhooks():
    """List all registered webhooks."""
    async with get_async_session() as session:
        result = await session.execute(select(Webhook))
        webhooks = result.scalars().all()

    return [
        {"id": wh.id, "tag": wh.tag, "url": wh.url, "created_at": wh.created_at.isoformat()}
        for wh in webhooks
    ]


@app.delete("/api/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: int):
    """Delete a webhook."""
    async with get_async_session() as session:
        result = await session.execute(select(Webhook).where(Webhook.id == webhook_id))
        webhook = result.scalar_one_or_none()
        if not webhook:
            return {"error": "webhook not found"}

        await session.delete(webhook)
        await session.commit()

    return {"deleted": webhook_id}
