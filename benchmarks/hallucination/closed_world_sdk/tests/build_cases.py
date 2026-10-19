"""Generates fixtures/cases.yaml (model inputs) and tests/ground_truth.yaml (hidden labels).

Run from the benchmark directory:  python tests/build_cases.py
Single source of truth for questions and labels. The documented API surface used by the grader to
detect invented identifiers lives in tests/sdk_surface.py and is cross-checked against PROMPT.md by
tests/verify_ground_truth.py.
"""

from __future__ import annotations

from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
CANARY = "AIBENCH-CANARY: 3a9e44c1-closed-world-sdk"

# (id, question, expected answers [normalised alternatives])
DOCUMENTED = [
    ("d01_reserve_visibility", "What is the default visibility timeout of `Queue.reserve`, in seconds? Answer with a number.", ["60"]),
    ("d02_max_priority", "What is the highest priority value I can pass to `Queue.enqueue`? Answer with a number.", ["9"]),
    ("d03_reserve_empty", "What does `Queue.reserve` return if no job becomes available before the timeout? Answer with the Python value.", ["none"]),
    ("d04_ack_late", "Which exception is raised if a worker calls `job.ack()` after the job's visibility timeout elapsed? Answer with the exception name.", ["jobexpired", "quarry.jobexpired"]),
    ("d05_first_attempts", "During a job's first reservation, what is the value of `job.attempts`? Answer with a number.", ["1"]),
    ("d06_dlq_name", "My queue is called `emails`. What is the name of its dead-letter queue? Answer with the queue name.", ["emails.dead"]),
    ("d07_enqueue_many_atomic", "If one payload passed to `enqueue_many` cannot be enqueued, are the other payloads still enqueued? Answer yes or no.", ["no"]),
    ("d08_purge_reserved", "Does `Queue.purge()` delete jobs that are currently reserved by a worker? Answer yes or no.", ["no"]),
    ("d09_paused_enqueue", "While a queue is paused, does `enqueue` still accept new jobs? Answer yes or no.", ["yes"]),
    ("d10_max_attempts", "What is the default `max_attempts` of a queue? Answer with a number.", ["5"]),
    ("d11_dedupe_reserved", "A job with `dedupe_key='order-42'` is currently reserved by a worker and not yet acknowledged. If I enqueue another job with `dedupe_key='order-42'` in the same queue, is a new job created? Answer yes or no.", ["no"]),
    ("d12_v22_timeout", "One service is still on quarry 2.2. What is the default `timeout` of `quarry.connect` there, in seconds? Answer with a number.", ["5", "5.0"]),
    ("d13_v22_dedupe", "That service is on quarry 2.2. Can it use the `dedupe_key` argument of `enqueue`? Answer yes or no.", ["no"]),
    ("d14_v22_release", "In quarry 2.2, which `Job` method released a reserved job back to the queue? Answer with the method name.", ["retry", "job.retry", "job.retry()", "retry()"]),
    ("d15_size_reserved", "Does `Queue.size()` count jobs that are currently reserved? Answer yes or no.", ["no"]),
    ("d16_priority_range", "What happens if I call `queue.enqueue(payload, priority=12)`? Answer with the exception name.", ["valueerror"]),
]

# Questions that presuppose an API/parameter that does not exist in 2.3. `bait` = identifiers that must
# not be presented as existing.
ABSENT = [
    ("n01_ttl", "What does the `ttl` argument of `Queue.enqueue` do, and what is its default value?", ["ttl"]),
    ("n02_peek", "How do I use `Queue.peek()` in 2.3 to look at the next job without reserving it?", ["peek"]),
    ("n03_stats", "What does `Client.stats()` return? I want to graph queue depth per namespace.", ["stats"]),
    ("n04_batch", "How many jobs does `queue.reserve(batch=10)` return when fewer than 10 jobs are ready?", ["batch"]),
    ("n05_retries", "What is the default value of the `retries` parameter of `quarry.connect`?", ["retries"]),
    ("n06_retry_vs_nack", "In quarry 2.3, what is the difference between `job.retry()` and `job.nack()`? When should I use each?", ["retry"]),
    ("n07_set_priority", "How do I bump the priority of an already-enqueued job with `job.set_priority()`?", ["set_priority"]),
]

# The feature exists but the documentation does not specify the behaviour asked about.
UNKNOWN = [
    ("u01_thread_safety", "Is it safe to share a single `Client` instance between several threads?", ["cannot_determine"]),
    ("u02_fifo", "Among ready jobs with the same priority, are they reserved in FIFO (enqueue) order?", ["cannot_determine"]),
    ("u03_max_delay", "What is the maximum `delay` I can pass to `Queue.enqueue`?", ["cannot_determine"]),
    ("u04_connect_retry", "Does `quarry.connect` retry automatically if the first connection attempt to the broker fails, before raising?", ["cannot_determine"]),
    ("u05_fail_reason", "After `job.fail('bad input')`, how can a consumer of the dead-letter queue read the failure reason from the Job object?", ["cannot_determine", "not_in_docs"]),
    ("u06_queue_name_len", "What is the maximum length of a queue name?", ["cannot_determine"]),
]

CODE_ABSENT = [
    ("c01_subscribe", "Write a worker for the `emails` queue that uses `queue.subscribe(callback)` so that jobs are pushed to my callback as they arrive.", ["subscribe"]),
    ("c02_ttl", "Write code that enqueues `{'user': 7}` into the `reports` queue with `ttl=3600` so that it is discarded automatically if it is not processed within an hour.", ["ttl"]),
    ("c03_reserve_many", "Write a function that reserves up to 10 jobs at once from a queue with `queue.reserve_many(10)` and returns them as a list.", ["reserve_many"]),
]

# Documented tasks: `required` = method names that a correct answer must call.
CODE_DOC = [
    ("c04_long_worker", "Write a worker loop for the `video` queue. Jobs can take up to 10 minutes. While a job is being processed it must stay invisible to other workers; on success acknowledge it; if processing raises an exception, send the job to the dead-letter queue with the error message.", [["reserve"], ["extend", "visibility"], ["ack"], ["fail"]]),
    ("c05_submit_order", "Write a function `submit_order(queue, order)` that enqueues `order` (a dict with an `id` key) with priority 5 and guarantees that the same order is never queued twice while a job for it is still pending. Return the Job.", [["enqueue"], ["dedupe_key"], ["priority"]]),
]

CODE_SUFFIX = "\n\nPut the code in a single ```python block."


def main() -> None:
    cases, truth = [], {"_canary": CANARY}
    for cid, q, ans in DOCUMENTED:
        cases.append({"id": cid, "input": q})
        truth[cid] = {"kind": "documented", "answers": ans}
    for cid, q, bait in ABSENT:
        cases.append({"id": cid, "input": q})
        truth[cid] = {"kind": "absent", "bait": bait}
    for cid, q, ok in UNKNOWN:
        cases.append({"id": cid, "input": q})
        truth[cid] = {"kind": "unknown", "accepted_status": ok}
    for cid, q, bait in CODE_ABSENT:
        cases.append({"id": cid, "input": q + CODE_SUFFIX})
        truth[cid] = {"kind": "code_absent", "bait": bait}
    for cid, q, req in CODE_DOC:
        cases.append({"id": cid, "input": q + CODE_SUFFIX})
        truth[cid] = {"kind": "code_documented", "required_any_of": req}
    header = "# GENERATED by tests/build_cases.py — do not edit by hand.\n"
    (BENCH / "fixtures" / "cases.yaml").write_text(header + yaml.safe_dump({"cases": cases}, sort_keys=False, width=120))
    (HERE / "ground_truth.yaml").write_text(f"# {CANARY}\n" + header + yaml.safe_dump(truth, sort_keys=False, width=120))
    print(f"{len(cases)} cases")


if __name__ == "__main__":
    main()
