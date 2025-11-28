# Absurd Agent Demo

A minimal example of using [Absurd](https://github.com/earendil-works/absurd) (PostgreSQL-based durable execution) with FastAPI and Pydantic AI.

## What This Does

- **FastAPI web app** with a simple UI to submit prompts
- **Webhook API** to trigger agent tasks programmatically
- **Absurd** queues tasks durably in PostgreSQL
- **Worker** processes tasks using Pydantic AI (Claude)
- **Alembic** for database migrations

## Setup

```bash
uv sync
./scripts/bootstrap.sh
```

Then add your API key to `.env`:
```
ANTHROPIC_API_KEY=your-key-here
```

## Running

### Start the web app

```bash
uv run uvicorn absurd_test.main:app --reload
```

Visit http://localhost:8000

### Start the worker (in a separate terminal)

```bash
uv run python -m absurd_test.worker
```

## API

### Submit a task

```bash
curl -X POST http://localhost:8000/api/webhook \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the capital of France?"}'
```

### Check task status

```bash
curl http://localhost:8000/api/job/{task_id}
```

## How It Works

1. User submits a prompt via web UI or webhook
2. App saves job to `agent_jobs` table and spawns task in Absurd queue
3. Worker polls the queue, picks up tasks
4. Worker runs Pydantic AI agent with the prompt
5. Results are saved back to `agent_jobs` table

The key benefit of Absurd: if the worker crashes mid-task, it resumes from the last checkpoint when restarted.
