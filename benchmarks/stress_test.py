"""Stress test the Absurd agent system using webhooks."""

import argparse
import asyncio
import statistics
import subprocess
import sys
import time
from datetime import datetime

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class BenchmarkRunner:
    def __init__(self, api_url: str, num_workers: int, num_tasks: int, concurrent: int):
        self.api_url = api_url
        self.num_workers = num_workers
        self.num_tasks = num_tasks
        self.concurrent = concurrent
        self.worker_processes = []
        self.task_times = {}
        self.completed_tasks = set()
        self.webhook_id = None
        self.completion_event = asyncio.Event()

    def start_workers(self):
        """Start N worker processes in test mode."""
        print(f"\n==> Starting {self.num_workers} workers...")
        for i in range(self.num_workers):
            proc = subprocess.Popen(
                [sys.executable, "-m", "absurd_test.worker", "--test"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.worker_processes.append(proc)
            print(f"    Worker {i+1} started (PID {proc.pid})")

        time.sleep(2)

        # Check if workers are actually running
        alive_count = sum(1 for p in self.worker_processes if p.poll() is None)
        print(f"    {alive_count}/{self.num_workers} workers alive after 2s")

        # Show any startup errors
        for i, proc in enumerate(self.worker_processes):
            if proc.poll() is not None:
                stderr = proc.stderr.read().decode()
                print(f"    Worker {i+1} died: {stderr[:200]}")

    def stop_workers(self):
        """Stop all worker processes."""
        print(f"\n==> Stopping {len(self.worker_processes)} workers...")
        for proc in self.worker_processes:
            proc.terminate()
            proc.wait(timeout=5)
        self.worker_processes = []

    async def handle_webhook(self, request: Request):
        """Handle webhook callback from completed task."""
        data = await request.json()
        task_id = data["task_id"]

        if task_id in self.task_times:
            self.task_times[task_id]["complete"] = time.time()
            self.completed_tasks.add(task_id)

            # Show progress
            completed = len(self.completed_tasks)
            if completed % 10 == 0 or completed == self.num_tasks:
                print(f"    Progress: {completed}/{self.num_tasks} tasks completed")

            if completed >= self.num_tasks:
                self.completion_event.set()

        return JSONResponse({"ok": True})

    async def run_callback_server(self):
        """Run a local HTTP server to receive webhook callbacks."""
        app = FastAPI()
        app.post("/callback")(self.handle_webhook)

        config = uvicorn.Config(app, host="127.0.0.1", port=9000, log_level="error")
        server = uvicorn.Server(config)
        await server.serve()

    async def register_webhook(self, client: httpx.AsyncClient):
        """Register webhook for benchmark tag."""
        print("\n==> Registering webhook...")
        response = await client.post(
            f"{self.api_url}/api/webhooks",
            json={"tag": "benchmark", "url": "http://localhost:9000/callback"},
        )
        data = response.json()
        self.webhook_id = data["id"]
        print(f"    Webhook registered (ID: {self.webhook_id})")

    async def cleanup_webhook(self, client: httpx.AsyncClient):
        """Delete the benchmark webhook."""
        if self.webhook_id:
            print(f"\n==> Cleaning up webhook {self.webhook_id}...")
            await client.delete(f"{self.api_url}/api/webhooks/{self.webhook_id}")

    async def submit_task(self, client: httpx.AsyncClient, task_num: int) -> str:
        """Submit a single task and return task_id."""
        response = await client.post(
            f"{self.api_url}/api/tasks",
            json={"prompt": f"Benchmark task {task_num}", "tag": "benchmark"},
        )
        data = response.json()
        task_id = data["task_id"]
        self.task_times[task_id] = {"submit": time.time(), "complete": None}
        return task_id

    async def run_benchmark_tasks(self):
        """Submit tasks and wait for webhook callbacks."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            await self.register_webhook(client)

            print(f"\n==> Submitting {self.num_tasks} tasks ({self.concurrent} concurrent)...")
            start_time = time.time()

            # Submit tasks in batches
            task_ids = []
            for i in range(0, self.num_tasks, self.concurrent):
                batch = range(i, min(i + self.concurrent, self.num_tasks))
                batch_tasks = [self.submit_task(client, n) for n in batch]
                batch_ids = await asyncio.gather(*batch_tasks)
                task_ids.extend(batch_ids)

            submit_time = time.time() - start_time
            print(f"    Submitted {self.num_tasks} tasks in {submit_time:.2f}s")

            # Wait for all callbacks
            print(f"\n==> Waiting for webhook callbacks...")
            await self.completion_event.wait()

            total_time = time.time() - start_time

            await self.cleanup_webhook(client)

            return total_time

    def calculate_metrics(self, total_time: float):
        """Calculate and display metrics."""
        latencies = []
        for task_id, times in self.task_times.items():
            if times["complete"]:
                latency = times["complete"] - times["submit"]
                latencies.append(latency)

        completed = len(latencies)
        throughput = completed / total_time if total_time > 0 else 0

        print("\n" + "=" * 60)
        print("BENCHMARK RESULTS")
        print("=" * 60)
        print(f"Configuration:")
        print(f"  Workers:           {self.num_workers}")
        print(f"  Tasks submitted:   {self.num_tasks}")
        print(f"  Concurrent batch:  {self.concurrent}")
        print(f"\nThroughput:")
        print(f"  Total time:        {total_time:.2f}s")
        print(f"  Tasks completed:   {completed}")
        print(f"  Tasks/second:      {throughput:.2f}")
        print(f"\nLatency (submit → complete):")
        print(f"  Min:               {min(latencies):.2f}s")
        print(f"  Median:            {statistics.median(latencies):.2f}s")
        print(f"  Mean:              {statistics.mean(latencies):.2f}s")
        print(f"  Max:               {max(latencies):.2f}s")
        print(f"  P95:               {statistics.quantiles(latencies, n=20)[18]:.2f}s")
        print(f"  P99:               {statistics.quantiles(latencies, n=100)[98]:.2f}s")
        print(f"\nConcurrency:")
        print(f"  Peak concurrent:   {self.concurrent}")
        print("=" * 60)

    async def run(self):
        """Run the full benchmark."""
        print("=" * 60)
        print("ABSURD STRESS TEST (WEBHOOK MODE)")
        print("=" * 60)
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        self.start_workers()

        try:
            # Run callback server in background
            server_task = asyncio.create_task(self.run_callback_server())

            # Give server time to start
            await asyncio.sleep(1)

            # Run the benchmark
            total_time = await self.run_benchmark_tasks()

            # Calculate and display results
            self.calculate_metrics(total_time)

            # Stop server
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass

        finally:
            self.stop_workers()


async def main():
    # Import uvicorn here to avoid issues
    global uvicorn
    import uvicorn

    parser = argparse.ArgumentParser(description="Benchmark Absurd system")
    parser.add_argument("--workers", type=int, default=4, help="Number of workers")
    parser.add_argument("--tasks", type=int, default=100, help="Number of tasks to submit")
    parser.add_argument("--concurrent", type=int, default=50, help="Max concurrent submissions")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API URL")
    args = parser.parse_args()

    runner = BenchmarkRunner(
        api_url=args.api_url,
        num_workers=args.workers,
        num_tasks=args.tasks,
        concurrent=args.concurrent,
    )
    await runner.run()


if __name__ == "__main__":
    asyncio.run(main())
