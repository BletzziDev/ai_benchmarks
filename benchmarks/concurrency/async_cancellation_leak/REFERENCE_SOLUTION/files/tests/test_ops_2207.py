"""Regression tests for OPS-2207 (leaked connections, duplicate exports, unsafe shutdown)."""

import asyncio

import pytest

from jobq import Connection, ConnectionPool, Job, JobRunner


def run(coro):
    return asyncio.run(asyncio.wait_for(coro, 10))


def test_cancelled_job_returns_its_connection():
    async def main():
        pool = ConnectionPool(1)
        started = asyncio.Event()

        async def handler(job, conn):
            started.set()
            await asyncio.Event().wait()

        runner = JobRunner(pool, handler)
        task = runner.submit(Job("export"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert pool.available == 1

    run(main())


def test_cancel_during_connect_returns_permit():
    async def main():
        entered = asyncio.Event()

        async def connect(i):
            entered.set()
            await asyncio.Event().wait()
            return Connection(i)

        pool = ConnectionPool(1, connect=connect)

        async def handler(job, conn):
            return 1

        task = JobRunner(pool, handler).submit(Job("j"))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert pool.available == 1

    run(main())


def test_redelivered_job_runs_once():
    async def main():
        pool = ConnectionPool(2)
        gate = asyncio.Event()
        calls = []

        async def handler(job, conn):
            calls.append(job.id)
            await gate.wait()
            return "ok"

        runner = JobRunner(pool, handler)
        first = runner.submit(Job("exp"))
        await asyncio.sleep(0)
        second = runner.submit(Job("exp"))
        gate.set()
        assert await asyncio.gather(first, second) == ["ok", "ok"]
        assert calls == ["exp"]

    run(main())


def test_shutdown_cancels_and_waits_for_stragglers():
    async def main():
        pool = ConnectionPool(1)
        cleaned = []

        async def handler(job, conn):
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0.01)
                cleaned.append(job.id)

        runner = JobRunner(pool, handler, attempt_timeout=30)
        task = runner.submit(Job("stuck"))
        await asyncio.sleep(0)
        summary = await runner.shutdown(grace=0.05)
        assert summary.cancelled == ["stuck"]
        assert task.done() and cleaned == ["stuck"]
        assert pool.available == 1

    run(main())
