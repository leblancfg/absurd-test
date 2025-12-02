"""Absurd worker that processes agent tasks from the queue."""

import argparse
import logging
import random
import time

import httpx
from absurd_sdk import Absurd

from absurd_test.agent import run_agent
from absurd_test.config import get_settings
from absurd_test.db import get_session
from absurd_test.models import AgentJob, Webhook

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TEST_MODE = False


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

    if TEST_MODE:
        result = ctx.step("test-sleep", lambda: test_task(prompt))
    else:
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


def test_task(prompt: str) -> str:
    """Simulate work by sleeping instead of calling AI."""
    sleep_time = 3 + random.uniform(-0.5, 0.5)
    time.sleep(sleep_time)
    return f"Test result for: {prompt}"


def run_worker(test_mode: bool = False):
    """Start the worker to process tasks."""
    global TEST_MODE
    TEST_MODE = test_mode

    settings = get_settings()
    if settings.kiosk:
        mode_str = "KIOSK MODE (Oblique Strategies)"
    elif test_mode:
        mode_str = "TEST MODE (sleep 3s)"
    else:
        mode_str = "PRODUCTION MODE (AI calls)"

    logger.info(f"Starting Absurd worker for 'agent_tasks' queue - {mode_str}")
    app.start_worker()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Absurd worker")
    parser.add_argument("--test", action="store_true", help="Test mode: sleep instead of calling AI")
    args = parser.parse_args()
    run_worker(test_mode=args.test)
