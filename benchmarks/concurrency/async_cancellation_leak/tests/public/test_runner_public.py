import asyncio

import pytest

from jobq import ConnectionPool, Job, JobFailed, JobRunner


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, 10))


def test_processes_jobs_and_returns_connections():
    async def main():
        pool = ConnectionPool(2)

        async def handler(job, conn):
            await asyncio.sleep(0.01)
            return job.payload * 2

        runner = JobRunner(pool, handler)
        results = await asyncio.gather(*(runner.submit(Job(f"j{i}", i)) for i in range(6)))
        assert results == [0, 2, 4, 6, 8, 10]
        assert pool.available == 2
        assert runner.result("j3") == 6

    run(main())


def test_timeouts_are_retried_then_fail():
    async def main():
        pool = ConnectionPool(1)
        calls = []

        async def handler(job, conn):
            calls.append(job.id)
            await asyncio.sleep(1)

        runner = JobRunner(pool, handler, max_attempts=3, attempt_timeout=0.02)
        with pytest.raises(JobFailed):
            await runner.submit(Job("slow"))
        assert calls == ["slow"] * 3
        assert pool.available == 1

    run(main())


def test_handler_errors_propagate_without_retry():
    async def main():
        pool = ConnectionPool(1)
        calls = []

        async def handler(job, conn):
            calls.append(1)
            raise ValueError("bad payload")

        runner = JobRunner(pool, handler)
        with pytest.raises(ValueError):
            await runner.submit(Job("x"))
        assert calls == [1]
        assert pool.available == 1

    run(main())


def test_completed_job_is_not_reprocessed():
    async def main():
        pool = ConnectionPool(1)
        calls = []

        async def handler(job, conn):
            calls.append(job.id)
            return "done"

        runner = JobRunner(pool, handler)
        assert await runner.submit(Job("a")) == "done"
        assert await runner.submit(Job("a")) == "done"
        assert calls == ["a"]

    run(main())
