# Benchmarks

Stress testing the Absurd-based task system.

## Running the benchmark

Make sure the API server is running first:

```bash
uv run uvicorn absurd_test.main:app
```

Then run the benchmark (workers are spawned automatically):

```bash
uv run python benchmarks/stress_test.py
```

## Options

```bash
uv run python benchmarks/stress_test.py \
  --workers 8 \
  --tasks 500 \
  --concurrent 100
```

- `--workers N` - Number of worker processes (default: 4)
- `--tasks N` - Total tasks to submit (default: 100)
- `--concurrent N` - Max concurrent task submissions (default: 50)

## What it measures

1. **Throughput** - Tasks completed per second
2. **Latency** - Time from submission to completion (min/median/mean/max/p95/p99)
3. **Max concurrent** - How many tasks can be in flight simultaneously

## Test mode

Workers run in `--test` mode, which sleeps for 3 seconds instead of calling the AI. This lets us stress test the queue infrastructure without burning API tokens.
