# Absurd Agent Demo

A demonstration of [Absurd](https://github.com/earendil-works/absurd) — Armin Ronacher's PostgreSQL-based durable execution system — integrated with [FastAPI](https://fastapi.tiangolo.com/) and [Pydantic AI](https://ai.pydantic.dev/).

## What is Absurd?

Absurd is a minimalist approach to durable workflows. Instead of requiring separate services like [Temporal](https://temporal.io/) or [Inngest](https://www.inngest.com/), it uses PostgreSQL as both the task queue and state store. Tasks are checkpointed automatically, so if a worker crashes, the next one resumes from where it left off.

Read Armin's [introductory blog post](https://lucumr.pocoo.org/2025/11/3/absurd-workflows/) for the full motivation.

## Features

- **Durable task queue** backed by PostgreSQL via Absurd
- **Automatic checkpointing** — crashed workers resume from last checkpoint
- **Webhook callbacks** — register webhooks to be notified when tasks complete
- **Simple web UI** for submitting prompts and viewing job status
- **REST API** for programmatic access

## Setup

### Prerequisites

- Python 3.13+
- PostgreSQL
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Installation

```bash
uv sync
cp example.env .env
# Edit .env with your OpenAI API key
./scripts/bootstrap.sh
```

## Running

Start the web server:

```bash
uv run uvicorn absurd_test.main:app --reload
```

In a separate terminal, start the worker:

```bash
uv run python -m absurd_test.worker
```

Visit http://localhost:8000

## API

### Submit a task

```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the capital of France?"}'
```

### Check task status

```bash
curl http://localhost:8000/api/tasks/{task_id}
```

### Register a webhook

```bash
curl -X POST http://localhost:8000/api/webhooks \
  -H "Content-Type: application/json" \
  -d '{"tag": "my-tag", "url": "https://example.com/callback"}'
```

Tasks submitted with `"tag": "my-tag"` will POST results to your webhook URL when complete.

## How It Works

1. User submits a prompt via web UI or API
2. App creates a job record and spawns a task in the Absurd queue
3. Worker polls the queue and claims the task
4. Worker executes the AI agent in checkpointed steps
5. Results are saved and webhooks are called

If the worker crashes at any point, the next worker picks up from the last checkpoint — no duplicate API calls, no lost work.

## Benchmarks

See [benchmarks/README.md](benchmarks/README.md) for stress testing instructions.

## License

MIT
