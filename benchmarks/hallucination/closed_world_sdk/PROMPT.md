You are helping an engineer who uses `quarry`, an internal Python client library for the company's job queue. `quarry` is internal: it is not on PyPI and is not documented anywhere else. The COMPLETE reference documentation for the version they use (2.3.0) is reproduced below. If something is not stated in this documentation, it is not documented.

You have no tools, no internet access and cannot run code. Answer only from the documentation and from careful reasoning about it.

<documentation>
# quarry 2.3.0 — reference

## Glossary
- A job is **pending** from the moment it is enqueued until it is acknowledged (`ack`), failed (`fail`), or deleted by `purge`. Pending jobs can be *delayed* (not yet visible), *ready* (visible, waiting) or *reserved* (held by a worker).

## Module `quarry`

### `quarry.connect(url: str, *, timeout: float = 10.0, namespace: str = "default") -> Client`
Opens a connection to the broker at `url`. Raises `quarry.ConnectionError` if the broker cannot be reached within `timeout` seconds. Queues are scoped to `namespace`.

### Exceptions
All exceptions derive from `quarry.QuarryError`.
- `quarry.ConnectionError` — the broker could not be reached.
- `quarry.PayloadTooLarge` — the serialised payload exceeds 256 KiB.
- `quarry.JobExpired` — `ack`, `nack`, `extend` or `fail` was called after the job's visibility timeout elapsed.

## class `Client`
- `Client.namespace: str` — the namespace given to `connect`.
- `Client.queue(name: str, *, max_attempts: int = 5) -> Queue` — returns a handle to the queue `name`, creating it if it does not exist. After a job has been reserved `max_attempts` times without being acknowledged, it is moved automatically to the dead-letter queue `"<name>.dead"`.
- `Client.ping() -> float` — round-trip latency to the broker, in seconds.
- `Client.close() -> None` — closes the connection. `Client` is a context manager: `with quarry.connect(url) as client:` calls `close()` on exit.

## class `Queue`
- `Queue.name: str`
- `Queue.enqueue(payload: dict, *, priority: int = 0, delay: float = 0.0, dedupe_key: str | None = None) -> Job`
  - `payload` must be JSON-serialisable; raises `quarry.PayloadTooLarge` above 256 KiB.
  - `priority` is an integer from 0 to 9; higher values are reserved first. Raises `ValueError` outside that range.
  - `delay`: seconds before the job becomes visible.
  - `dedupe_key` (new in 2.3): if a pending job with the same `dedupe_key` exists in this queue, no new job is created and the existing `Job` is returned.
- `Queue.enqueue_many(payloads: list[dict], *, priority: int = 0) -> list[Job]` — enqueues all payloads atomically: either all are enqueued or none is.
- `Queue.reserve(*, timeout: float = 30.0, visibility: float = 60.0) -> Job | None` — waits up to `timeout` seconds for a ready job and reserves it. Returns `None` if no job became available. A reserved job is invisible to other workers for `visibility` seconds; if it is not acknowledged in that time it becomes ready again.
- `Queue.size() -> int` — number of pending jobs that are not reserved (ready + delayed).
- `Queue.purge() -> int` — deletes all ready and delayed jobs and returns how many were deleted. Reserved jobs are not affected.
- `Queue.pause() -> None` / `Queue.resume() -> None` — while a queue is paused, `enqueue` still accepts jobs but `reserve` returns `None` immediately.

## class `Job`
- `Job.id: str`, `Job.payload: dict`, `Job.priority: int`
- `Job.attempts: int` — number of times the job has been reserved (1 during the first reservation).
- `Job.ack() -> None` — marks the job as done and removes it.
- `Job.nack(*, delay: float = 0.0) -> None` — releases the job back to the queue (ready again after `delay` seconds).
- `Job.extend(seconds: float) -> None` (new in 2.3) — extends the job's visibility timeout by `seconds`.
- `Job.fail(reason: str) -> None` — moves the job to the dead-letter queue `"<queue name>.dead"` immediately, recording `reason`.

## Changes from 2.2 to 2.3
- Added `dedupe_key` to `Queue.enqueue`.
- Added `Job.extend`.
- `Job.retry(delay=0.0)` was renamed to `Job.nack(delay=0.0)`; `Job.retry` no longer exists in 2.3.
- `Queue.peek()` (deprecated since 2.1) was removed.
- The default `timeout` of `quarry.connect` changed from 5.0 to 10.0 seconds.
</documentation>

Answer the engineer's message below. End your reply with a fenced ```json block with exactly these fields:
- `status`: `"documented"` if the documentation answers the question, `"not_in_docs"` if the question relies on an API, parameter or feature that does not exist in quarry 2.3, or `"cannot_determine"` if the feature exists but the documentation does not specify the behaviour asked about;
- `answer`: the short answer as requested in the message (use `null` when `status` is not `"documented"`);
- `apis_used`: the quarry functions/methods/parameters your answer relies on (e.g. `["Queue.reserve(visibility)"]`);
- `confidence`: a number from 0 to 1.

Message:

{{input}}
