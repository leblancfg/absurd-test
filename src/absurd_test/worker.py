"""Absurd worker that processes agent tasks from the queue."""

import logging

import httpx
from absurd_sdk import Absurd

from absurd_test.agent import run_agent
from absurd_test.config import get_settings
from absurd_test.db import get_session
from absurd_test.models import AgentJob, Webhook

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_absurd_app() -> Absurd:
    settings = get_settings()
    return Absurd(settings.database_url, queue_name="agent_tasks")


app = create_absurd_app()


def call_webhooks(task_id: str, tag: str | None, result: str):
    """Call all webhooks registered for this tag."""
    if not tag:
        return

    session = get_session()
    webhooks = session.query(Webhook).filter_by(tag=tag).all()
    session.close()

    if not webhooks:
        return

    payload = {"task_id": task_id, "result": result, "status": "completed"}

    for wh in webhooks:
        try:
            logger.info(f"Calling webhook {wh.url} for tag '{tag}'")
            resp = httpx.post(wh.url, json=payload, timeout=10)
            logger.info(f"Webhook response: {resp.status_code}")
        except Exception as e:
            logger.error(f"Webhook call failed: {e}")


@app.register_task(name="run-agent")
def handle_agent_task(params: dict, ctx):
    """Process an agent task."""
    task_id = params["task_id"]
    prompt = params["prompt"]
    tag = params.get("tag")

    logger.info(f"Processing task {task_id}: {prompt[:50]}...")

    @ctx.run_step("mark-running")
    def mark_running():
        session = get_session()
        job = session.query(AgentJob).filter_by(task_id=task_id).first()
        if job:
            job.status = "running"
            session.commit()
        session.close()

    result = ctx.step("run-agent", lambda: run_agent(prompt))

    @ctx.run_step("save-result")
    def save_result():
        session = get_session()
        job = session.query(AgentJob).filter_by(task_id=task_id).first()
        if job:
            job.result = result
            job.status = "completed"
            session.commit()
        session.close()

    @ctx.run_step("call-webhooks")
    def notify_webhooks():
        call_webhooks(task_id, tag, result)

    logger.info(f"Completed task {task_id}")
    return {"task_id": task_id, "result": result}


def run_worker():
    """Start the worker to process tasks."""
    logger.info("Starting Absurd worker for 'agent_tasks' queue...")
    app.start_worker()


if __name__ == "__main__":
    run_worker()
