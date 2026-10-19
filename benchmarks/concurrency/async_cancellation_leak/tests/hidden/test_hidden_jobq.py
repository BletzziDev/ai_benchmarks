# AIBENCH-CANARY: 91c4e6b3-async-cancellation-leak-hidden — never show this file to evaluated models.
"""Hidden tests for concurrency/async_cancellation_leak.

Prefixes: test_cancel_ (permits survive cancellation at every await point), test_dup_ (redelivered
jobs run once), test_shut_ (graceful shutdown semantics), test_pres_ (unchanged contract),
test_stress_ (seeded randomised mixes with invariant checks).
All tests run their event loop under a hard timeout, so a hang is a failure, not a stuck run.
"""

import asyncio
import inspect
import random

import pytest

from jobq import Connection, ConnectionPool, Job, JobFailed, JobRunner, RunnerClosed, ShutdownSummary


def run(coro, timeout=15):
    return asyncio.run(asyncio.wait_for(coro, timeout))


async def settle(n=5):
    for _ in range(n):
        await asyncio.sleep(0)


# ----------------------------------------------------------------------------- cancellation

def test_cancel_during_handler_returns_connection():
    async def main():
        pool = ConnectionPool(2)
        started = asyncio.Event()

        async def handler(job, conn):
            started.set()
            await asyncio.Event().wait()

        runner = JobRunner(pool, handler)
        t = runner.submit(Job("export-1"))
        await asyncio.wait_for(started.wait(), 5)
        assert pool.available == 1
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
        assert pool.available == 2, "a cancelled job kept its connection"
        assert pool.in_use == 0

    run(main())


def test_cancel_while_connecting_returns_permit():
    async def main():
        entered = asyncio.Event()

        async def slow_connect(i):
            entered.set()
            await asyncio.Event().wait()  # handshake never completes
            return Connection(i)

        pool = ConnectionPool(1, connect=slow_connect)

        async def handler(job, conn):
            return "x"

        runner = JobRunner(pool, handler)
        t = runner.submit(Job("j"))
        await asyncio.wait_for(entered.wait(), 5)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
        assert pool.available == 1, "permit leaked when cancelled during connection establishment"
        # the pool must still be usable
        async def fast_connect(i):
            return Connection(i)

        pool._connect = fast_connect  # noqa: SLF001 - test seam
        conn = await asyncio.wait_for(pool.acquire(), 2)
        pool.release(conn)

    run(main())


def test_cancel_while_waiting_for_pool_is_clean():
    async def main():
        pool = ConnectionPool(1)
        gate = asyncio.Event()

        async def handler(job, conn):
            await gate.wait()
            return job.id

        runner = JobRunner(pool, handler)
        first = runner.submit(Job("a"))
        await settle()
        waiting = runner.submit(Job("b"))
        await settle()
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        gate.set()
        assert await first == "a"
        assert pool.available == 1

    run(main())


def test_cancel_many_at_different_points():
    async def main():
        pool = ConnectionPool(3)

        async def connect(i):
            for _ in range(i % 3):
                await asyncio.sleep(0)
            return Connection(i)

        pool._connect = connect  # noqa: SLF001
        never = asyncio.Event()

        async def handler(job, conn):
            for _ in range(int(job.payload)):
                await asyncio.sleep(0)
            await never.wait()

        runner = JobRunner(pool, handler, attempt_timeout=30)
        tasks = [runner.submit(Job(f"j{i}", i % 4)) for i in range(30)]
        for step in range(40):
            await asyncio.sleep(0)
            for i, t in enumerate(tasks):
                if (i * 7 + step) % 11 == 0 and not t.done():
                    t.cancel()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        assert pool.in_use == 0 and pool.available == 3, f"leaked: in_use={pool.in_use}"

    run(main())


def test_cancel_after_timeout_retry_still_balanced():
    async def main():
        pool = ConnectionPool(1)
        attempts = []

        async def handler(job, conn):
            attempts.append(1)
            await asyncio.sleep(10)

        runner = JobRunner(pool, handler, max_attempts=5, attempt_timeout=0.03)
        t = runner.submit(Job("slow"))
        while len(attempts) < 2:
            await asyncio.sleep(0.01)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
        assert pool.available == 1
        assert pool.in_use == 0

    run(main())


# ----------------------------------------------------------------------------- duplicates

def test_dup_redelivery_while_running_runs_handler_once():
    async def main():
        pool = ConnectionPool(4)
        gate = asyncio.Event()
        calls = []

        async def handler(job, conn):
            calls.append(job.id)
            await gate.wait()
            return f"exported:{job.id}"

        runner = JobRunner(pool, handler)
        t1 = runner.submit(Job("exp-9"))
        await settle()
        dups = [runner.submit(Job("exp-9")) for _ in range(5)]
        await settle()
        gate.set()
        results = await asyncio.gather(t1, *dups)
        assert calls == ["exp-9"], f"handler ran {len(calls)} times for one job"
        assert set(results) == {"exported:exp-9"}
        assert pool.available == 4

    run(main())


def test_dup_redelivery_while_pending_in_pool_queue():
    async def main():
        pool = ConnectionPool(1)
        gate = asyncio.Event()
        calls = []

        async def handler(job, conn):
            calls.append(job.id)
            await gate.wait()
            return job.id

        runner = JobRunner(pool, handler)
        blocker = runner.submit(Job("blocker"))
        await settle()
        a1 = runner.submit(Job("queued"))
        await settle()
        a2 = runner.submit(Job("queued"))
        gate.set()
        assert await asyncio.gather(blocker, a1, a2) == ["blocker", "queued", "queued"]
        assert calls.count("queued") == 1

    run(main())


def test_dup_redelivery_during_retry_does_not_start_second_runner():
    async def main():
        pool = ConnectionPool(2)
        active = {"n": 0, "max": 0}
        attempts = []
        gate = asyncio.Event()

        async def handler(job, conn):
            attempts.append(job.id)
            active["n"] += 1
            active["max"] = max(active["max"], active["n"])
            try:
                if len(attempts) == 1:
                    await asyncio.sleep(10)  # first attempt times out
                await gate.wait()
                return "ok"
            finally:
                active["n"] -= 1

        runner = JobRunner(pool, handler, max_attempts=3, attempt_timeout=0.05)
        t1 = runner.submit(Job("r"))
        while len(attempts) < 2:  # wait until the retry is running
            await asyncio.sleep(0.005)
        t2 = runner.submit(Job("r"))  # redelivery during the retry
        await settle()
        gate.set()
        assert await asyncio.gather(t1, t2) == ["ok", "ok"]
        assert active["max"] == 1, "two attempts of the same job ran concurrently"
        assert len(attempts) == 2

    run(main())


def test_dup_failed_and_cancelled_jobs_can_be_resubmitted():
    async def main():
        pool = ConnectionPool(1)
        mode = {"fail": True}
        started = asyncio.Event()

        async def handler(job, conn):
            started.set()
            if job.id == "c":
                await asyncio.Event().wait()
            if mode["fail"]:
                raise ValueError("boom")
            return "ok"

        runner = JobRunner(pool, handler)
        with pytest.raises(ValueError):
            await runner.submit(Job("f"))
        mode["fail"] = False
        assert await runner.submit(Job("f")) == "ok"
        t = runner.submit(Job("c"))
        await asyncio.wait_for(started.wait(), 5)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
        t2 = runner.submit(Job("c"))
        assert t2 is not t and not t2.done()
        t2.cancel()
        await asyncio.gather(t2, return_exceptions=True)
        assert pool.available == 1

    run(main())


# ----------------------------------------------------------------------------- shutdown

def test_shut_cancels_stragglers_and_waits_for_cleanup():
    async def main():
        pool = ConnectionPool(3)
        cleaned = []

        async def handler(job, conn):
            try:
                if job.id == "quick":
                    await asyncio.sleep(0.01)
                    return "q"
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0.02)  # cleanup that itself awaits
                cleaned.append(job.id)

        runner = JobRunner(pool, handler, attempt_timeout=30)
        tasks = [runner.submit(Job(i)) for i in ("quick", "stuck-1", "stuck-2")]
        await settle()
        summary = await runner.shutdown(grace=0.2)
        assert isinstance(summary, ShutdownSummary)
        assert summary.finished == ["quick"]
        assert summary.cancelled == ["stuck-1", "stuck-2"]
        assert all(t.done() for t in tasks), "job tasks still running after shutdown() returned"
        assert sorted(cleaned) == ["quick", "stuck-1", "stuck-2"], "shutdown returned before cleanup finished"
        assert pool.available == 3 and pool.in_use == 0

    run(main())


def test_shut_rejects_new_jobs_and_is_bounded():
    async def main():
        pool = ConnectionPool(1)

        async def handler(job, conn):
            await asyncio.Event().wait()

        runner = JobRunner(pool, handler, attempt_timeout=30)
        t = runner.submit(Job("x"))
        await settle()
        loop = asyncio.get_running_loop()
        t0 = loop.time()
        summary = await runner.shutdown(grace=0.1)
        assert loop.time() - t0 < 2.0
        assert summary.cancelled == ["x"] and t.cancelled()
        with pytest.raises(RunnerClosed):
            runner.submit(Job("y"))
        assert pool.available == 1

    run(main())


def test_shut_with_idle_runner_and_completed_jobs():
    async def main():
        pool = ConnectionPool(1)

        async def handler(job, conn):
            return job.id

        runner = JobRunner(pool, handler)
        assert await runner.submit(Job("a")) == "a"
        summary = await runner.shutdown(grace=0.1)
        assert summary.finished == [] and summary.cancelled == []

    run(main())


# ----------------------------------------------------------------------------- contract

def test_pres_api():
    params = list(inspect.signature(JobRunner.__init__).parameters)
    assert params[:3] == ["self", "pool", "handler"]
    sig = inspect.signature(JobRunner.__init__).parameters
    assert sig["max_attempts"].default == 3 and sig["attempt_timeout"].default == 5.0
    assert list(inspect.signature(JobRunner.shutdown).parameters) == ["self", "grace"]
    assert inspect.iscoroutinefunction(JobRunner.shutdown)
    assert not inspect.iscoroutinefunction(JobRunner.submit)


def test_pres_retry_and_failure_semantics():
    async def main():
        pool = ConnectionPool(2)
        calls = {"t": 0, "e": 0}

        async def handler(job, conn):
            if job.id == "timeout":
                calls["t"] += 1
                await asyncio.sleep(5)
            calls["e"] += 1
            raise KeyError("x")

        runner = JobRunner(pool, handler, max_attempts=2, attempt_timeout=0.02)
        with pytest.raises(JobFailed) as ei:
            await runner.submit(Job("timeout"))
        assert ei.value.attempts == 2 and calls["t"] == 2
        with pytest.raises(KeyError):
            await runner.submit(Job("err"))
        assert calls["e"] == 1
        assert pool.available == 2

    run(main())


def test_pres_results_and_pool_basics():
    async def main():
        pool = ConnectionPool(2)
        with pytest.raises(ValueError):
            ConnectionPool(0)

        async def handler(job, conn):
            assert isinstance(conn, Connection)
            return job.payload

        runner = JobRunner(pool, handler)
        assert await asyncio.gather(*(runner.submit(Job(str(i), i)) for i in range(5))) == list(range(5))
        assert runner.result("3") == 3
        c = await pool.acquire()
        assert pool.available == 1
        pool.release(c)
        assert pool.available == 2

    run(main())


# ----------------------------------------------------------------------------- stress

@pytest.mark.parametrize("seed", range(5))
def test_stress_random_mix(seed):
    async def main():
        rng = random.Random(seed)
        size = 4
        pool = ConnectionPool(size)

        async def connect(i):
            for _ in range(rng.randint(0, 2)):
                await asyncio.sleep(0)
            return Connection(i)

        pool._connect = connect  # noqa: SLF001
        active = {}
        overlap = []
        completions = {}

        async def handler(job, conn):
            active[job.id] = active.get(job.id, 0) + 1
            if active[job.id] > 1:
                overlap.append(job.id)
            try:
                await asyncio.sleep(rng.choice([0, 0.001, 0.004, 0.03]))
                if rng.random() < 0.1:
                    raise ValueError("flaky")
                completions[job.id] = completions.get(job.id, 0) + 1
                return job.id
            finally:
                active[job.id] -= 1

        runner = JobRunner(pool, handler, max_attempts=2, attempt_timeout=0.02)
        tasks = []
        for step in range(150):
            jid = f"j{rng.randint(0, 40)}"
            tasks.append(runner.submit(Job(jid)))
            if rng.random() < 0.15:
                victim = rng.choice(tasks)
                victim.cancel()
            await asyncio.sleep(rng.choice([0, 0, 0.001]))
            assert 0 <= pool.in_use <= size
        # every job settles on its own (short handlers, timeouts): then the pool must be whole again
        await asyncio.wait(tasks, timeout=10)
        assert all(t.done() for t in tasks)
        assert pool.in_use == 0 and pool.available == size, f"leaked connections: in_use={pool.in_use}"
        # second wave, interrupted by shutdown
        late = [runner.submit(Job(f"late{i}")) for i in range(8)]
        summary = await runner.shutdown(grace=0.002)
        assert all(t.done() for t in late)
        assert pool.in_use == 0 and pool.available == size, f"leaked after shutdown: in_use={pool.in_use}"
        assert not overlap, f"same job ran concurrently: {sorted(set(overlap))[:5]}"
        assert all(n == 1 for n in completions.values()), "a job completed more than once"
        assert isinstance(summary, ShutdownSummary)

    run(main(), timeout=30)
