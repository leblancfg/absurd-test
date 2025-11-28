"""Stress test the Absurd agent system."""

import argparse
import asyncio
import multiprocessing
import statistics
import subprocess
import sys
import time
from datetime import datetime

import httpx


class BenchmarkRunner:
    def __init__(self, api_url: str, num_workers: int, num_tasks: int, concurrent: int):
        self.api_url = api_url
        self.num_workers = num_workers
        self.num_tasks = num_tasks
        self.concurrent = concurrent
        self.worker_processes = []
        self.task_times = {}

    def start_workers(self):
        """Start N worker processes in test mode."""
        print(f"\n==> Starting {self.num_workers} workers...")
        for i in range(self.num_workers):
            proc = subprocess.Popen(
                [sys.executable, "-m", "absurd_test.worker", "--test"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.worker_processes.append(proc)
            print(f"    Worker {i+1} started (PID {proc.pid})")
        time.sleep(2)

    def stop_workers(self):
        """Stop all worker processes."""
        print(f"\n==> Stopping {len(self.worker_processes)} workers...")
        for proc in self.worker_processes:
            proc.terminate()
            proc.wait(timeout=5)
        self.worker_processes = []

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

    async def wait_for_task(self, client: httpx.AsyncClient, task_id: str):
        """Poll until task is complete."""
        while True:
            response = await client.get(f"{self.api_url}/api/tasks/{task_id}")
            data = response.json()
            if data.get("status") == "completed":
                self.task_times[task_id]["complete"] = time.time()
                return
            await asyncio.sleep(0.1)

    async def run_batch(self):
        """Submit and wait for all tasks."""
        print(f"\n==> Submitting {self.num_tasks} tasks ({self.concurrent} concurrent)...")
        start_time = time.time()

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Submit tasks in batches
            task_ids = []
            for i in range(0, self.num_tasks, self.concurrent):
                batch = range(i, min(i + self.concurrent, self.num_tasks))
                batch_tasks = [self.submit_task(client, n) for n in batch]
                batch_ids = await asyncio.gather(*batch_tasks)
                task_ids.extend(batch_ids)

            submit_time = time.time() - start_time
            print(f"    Submitted {self.num_tasks} tasks in {submit_time:.2f}s")

            # Wait for all to complete
            print(f"\n==> Waiting for completion...")
            wait_tasks = [self.wait_for_task(client, tid) for tid in task_ids]
            await asyncio.gather(*wait_tasks)

        total_time = time.time() - start_time
        return total_time

    def calculate_metrics(self, total_time: float):
        """Calculate and display metrics."""
        latencies = []
        for task_id, times in self.task_times.items():
            if times["complete"]:
                latency = times["complete"] - times["submit"]
                latencies.append(latency)

        completed = len(latencies)
        throughput = completed / total_time

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
        print("ABSURD STRESS TEST")
        print("=" * 60)
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        self.start_workers()

        try:
            total_time = await self.run_batch()
            self.calculate_metrics(total_time)
        finally:
            self.stop_workers()


async def main():
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
