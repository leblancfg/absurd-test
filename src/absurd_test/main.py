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

from absurd_test.config import get_settings
from absurd_test.db import get_session
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
    session = get_session()
    jobs = session.query(AgentJob).order_by(AgentJob.created_at.desc()).limit(3).all()
    session.close()
    return templates.TemplateResponse("index.html", {"request": request, "jobs": jobs})


@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    """Show the about page."""
    return templates.TemplateResponse("about.html", {"request": request})


@app.get("/partials/jobs", response_class=HTMLResponse)
async def partials_jobs(request: Request):
    """Return just the job list HTML fragment for HTMX polling."""
    session = get_session()
    jobs = session.query(AgentJob).order_by(AgentJob.created_at.desc()).limit(3).all()
    session.close()
    return templates.TemplateResponse("partials/jobs.html", {"request": request, "jobs": jobs})


@app.post("/submit", response_class=HTMLResponse)
async def submit_job(request: Request, prompt: str = Form(...), tag: str = Form("")):
    """Submit a new agent job to the queue from the web UI."""
    task_id = str(uuid.uuid4())
    tag = tag.strip() or None

    session = get_session()
    job = AgentJob(task_id=task_id, prompt=prompt, tag=tag, status="pending")
    session.add(job)
    session.commit()
    session.close()

    absurd_app.spawn(
        "run-agent",
        {"task_id": task_id, "prompt": prompt, "tag": tag},
        queue="agent_tasks",
    )

    session = get_session()
    jobs = session.query(AgentJob).order_by(AgentJob.created_at.desc()).limit(3).all()
    session.close()
    return templates.TemplateResponse("partials/jobs.html", {"request": request, "jobs": jobs})


@app.get("/job/{task_id}", response_class=HTMLResponse)
async def get_job(request: Request, task_id: str):
    """View a specific job's details."""
    session = get_session()
    job = session.query(AgentJob).filter_by(task_id=task_id).first()
    session.close()
    return templates.TemplateResponse("job.html", {"request": request, "job": job})


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    """Admin page for managing webhooks."""
    session = get_session()
    webhooks = session.query(Webhook).order_by(Webhook.created_at.desc()).all()
    session.close()
    return templates.TemplateResponse("admin.html", {"request": request, "webhooks": webhooks})


@app.get("/partials/webhooks", response_class=HTMLResponse)
async def partials_webhooks(request: Request):
    """Return just the webhooks list HTML fragment for HTMX."""
    session = get_session()
    webhooks = session.query(Webhook).order_by(Webhook.created_at.desc()).all()
    session.close()
    return templates.TemplateResponse("partials/webhooks.html", {"request": request, "webhooks": webhooks})


@app.post("/admin/webhooks", response_class=HTMLResponse)
async def create_webhook_form(request: Request, tag: str = Form(...), url: str = Form(...)):
    """Create a webhook from the admin form."""
    session = get_session()
    webhook = Webhook(tag=tag.strip(), url=url.strip())
    session.add(webhook)
    session.commit()
    session.close()

    session = get_session()
    webhooks = session.query(Webhook).order_by(Webhook.created_at.desc()).all()
    session.close()
    return templates.TemplateResponse("partials/webhooks.html", {"request": request, "webhooks": webhooks})


@app.delete("/admin/webhooks/{webhook_id}", response_class=HTMLResponse)
async def delete_webhook_form(request: Request, webhook_id: int):
    """Delete a webhook from the admin page."""
    session = get_session()
    webhook = session.query(Webhook).filter_by(id=webhook_id).first()
    if webhook:
        session.delete(webhook)
        session.commit()
    session.close()

    session = get_session()
    webhooks = session.query(Webhook).order_by(Webhook.created_at.desc()).all()
    session.close()
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

    session = get_session()
    job = AgentJob(task_id=task_id, prompt=task.prompt, tag=tag, status="pending")
    session.add(job)
    session.commit()
    session.close()

    absurd_app.spawn(
        "run-agent",
        {"task_id": task_id, "prompt": task.prompt, "tag": tag},
        queue="agent_tasks",
    )

    return {"task_id": task_id}


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    """Get task status and result."""
    session = get_session()
    job = session.query(AgentJob).filter_by(task_id=task_id).first()
    session.close()

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
    session = get_session()
    job = session.query(AgentJob).filter_by(task_id=task_id).first()
    if not job:
        session.close()
        return {"error": "task not found"}

    session.delete(job)
    session.commit()
    session.close()

    return {"deleted": task_id}


@app.delete("/jobs/{task_id}", response_class=HTMLResponse)
async def delete_job_ui(request: Request, task_id: str):
    """Delete a job from UI and return updated job list."""
    session = get_session()
    job = session.query(AgentJob).filter_by(task_id=task_id).first()
    if job:
        session.delete(job)
        session.commit()
    session.close()

    session = get_session()
    jobs = session.query(AgentJob).order_by(AgentJob.created_at.desc()).limit(3).all()
    session.close()
    return templates.TemplateResponse("partials/jobs.html", {"request": request, "jobs": jobs})


@app.post("/api/webhooks")
async def create_webhook(webhook: WebhookCreate):
    """Register a webhook for a tag."""
    session = get_session()
    wh = Webhook(tag=webhook.tag.strip(), url=webhook.url.strip())
    session.add(wh)
    session.commit()
    webhook_id = wh.id
    session.close()

    return {"id": webhook_id, "tag": webhook.tag, "url": webhook.url}


@app.get("/api/webhooks")
async def list_webhooks():
    """List all registered webhooks."""
    session = get_session()
    webhooks = session.query(Webhook).all()
    session.close()

    return [
        {"id": wh.id, "tag": wh.tag, "url": wh.url, "created_at": wh.created_at.isoformat()}
        for wh in webhooks
    ]


@app.delete("/api/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: int):
    """Delete a webhook."""
    session = get_session()
    webhook = session.query(Webhook).filter_by(id=webhook_id).first()
    if not webhook:
        session.close()
        return {"error": "webhook not found"}

    session.delete(webhook)
    session.commit()
    session.close()

    return {"deleted": webhook_id}
