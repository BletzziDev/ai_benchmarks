from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from jobq.pool import Connection, ConnectionPool

log = logging.getLogger("jobq")

Handler = Callable[["Job", Connection], Awaitable[Any]]


@dataclass(frozen=True)
class Job:
    id: str
    payload: Any = None


class JobFailed(Exception):
    def __init__(self, job_id: str, attempts: int):
        super().__init__(f"job {job_id} failed after {attempts} attempt(s)")
        self.job_id = job_id
        self.attempts = attempts


class RunnerClosed(RuntimeError):
    pass


@dataclass
class ShutdownSummary:
    finished: list[str] = field(default_factory=list)  # jobs that completed (or failed) on their own
    cancelled: list[str] = field(default_factory=list)  # jobs cancelled because the grace period ran out


class JobRunner:
    """Runs jobs concurrently, each attempt holding one pooled connection.

    Contract (the queue consumer and the deploy tooling rely on it):

    * Every connection checked out for an attempt is returned to the pool exactly once, whether the
      attempt succeeds, raises, times out, or is cancelled at any await point (including while the
      connection is still being established).
    * Each attempt is limited to ``attempt_timeout`` seconds; timed-out attempts are retried up to
      ``max_attempts`` in total, then the job fails with ``JobFailed``. Other exceptions from the
      handler propagate immediately (no retry).
    * Jobs are de-duplicated by id: submitting a job whose id is pending or running returns the task
      already processing it (the handler runs once); submitting a completed job id returns a task
      resolving to the stored result without running the handler. Failed or cancelled jobs are not
      remembered and can be submitted again. The queue redelivers messages, so duplicates are normal.
    * ``shutdown(grace)`` stops accepting jobs (``submit`` raises ``RunnerClosed``), lets running jobs
      finish for up to ``grace`` seconds, then cancels the rest and waits until they have actually
      stopped. When it returns, no job task is still running and every connection is back in the pool.
    """

    def __init__(self, pool: ConnectionPool, handler: Handler, *, max_attempts: int = 3,
                 attempt_timeout: float = 5.0):
        self._pool = pool
        self._handler = handler
        self._max_attempts = max_attempts
        self._attempt_timeout = attempt_timeout
        self._results: dict[str, Any] = {}
        self._tasks: dict[asyncio.Task, str] = {}
        self._closed = False

    # -- public API ------------------------------------------------------------------------------
    def submit(self, job: Job) -> asyncio.Task:
        if self._closed:
            raise RunnerClosed("runner is shutting down")
        if job.id in self._results:
            return asyncio.ensure_future(self._stored(job.id))
        task = asyncio.create_task(self._process(job), name=f"job:{job.id}")
        self._tasks[task] = job.id
        task.add_done_callback(self._tasks.pop)
        return task

    def result(self, job_id: str) -> Any:
        return self._results[job_id]

    async def shutdown(self, grace: float) -> ShutdownSummary:
        self._closed = True
        summary = ShutdownSummary()
        if not self._tasks:
            return summary
        tasks = dict(self._tasks)
        done, pending = await asyncio.wait(tasks, timeout=grace)
        summary.finished = sorted(tasks[t] for t in done)
        summary.cancelled = sorted(tasks[t] for t in pending)
        return summary

    # -- internals -------------------------------------------------------------------------------
    async def _stored(self, job_id: str) -> Any:
        return self._results[job_id]

    async def _process(self, job: Job) -> Any:
        for attempt in range(1, self._max_attempts + 1):
            try:
                result = await self._attempt(job)
            except TimeoutError:
                log.warning("job %s attempt %d timed out", job.id, attempt)
                continue
            self._results[job.id] = result
            return result
        raise JobFailed(job.id, self._max_attempts)

    async def _attempt(self, job: Job) -> Any:
        conn = await self._pool.acquire()
        try:
            async with asyncio.timeout(self._attempt_timeout):
                return await self._handler(job, conn)
        finally:  # OPS-2207: also release on cancellation
            self._pool.release(conn)
