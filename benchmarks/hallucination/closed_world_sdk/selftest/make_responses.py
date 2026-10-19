"""Generates canned response sets for `benchmark selftest` (run: python selftest/make_responses.py).

  reference        - correct statuses/answers, code only uses the documented API.
  hallucinator     - treats every question as documented, invents plausible answers and APIs confidently.
  hedger           - says "cannot_determine" to everything (no hallucinations, no usefulness).
  careless_reader  - right statuses everywhere, but misreads half of the documented answers.
  no_json          - plausible prose answers without the JSON block.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

BENCH = Path(__file__).resolve().parent.parent
truth = yaml.safe_load((BENCH / "tests" / "ground_truth.yaml").read_text())

REF_CODE = {
    "c01_subscribe": '''import quarry

def run(url):
    with quarry.connect(url) as client:
        queue = client.queue("emails")
        while True:
            job = queue.reserve(timeout=30.0)
            if job is None:
                continue
            try:
                handle(job.payload)
                job.ack()
            except Exception as e:
                job.fail(str(e))
''',
    "c02_ttl": '''import quarry

with quarry.connect(URL) as client:
    client.queue("reports").enqueue({"user": 7})
# quarry 2.3 has no ttl: the consumer must check the job's age itself (e.g. store a created_at in the payload).
''',
    "c03_reserve_many": '''def reserve_up_to(queue, n=10):
    jobs = []
    for _ in range(n):
        job = queue.reserve(timeout=0.0)
        if job is None:
            break
        jobs.append(job)
    return jobs
''',
    "c04_long_worker": '''import quarry

def work(url):
    with quarry.connect(url) as client:
        queue = client.queue("video")
        while True:
            job = queue.reserve(timeout=30.0, visibility=900.0)
            if job is None:
                continue
            try:
                transcode(job.payload)
                job.ack()
            except Exception as e:
                job.fail(str(e))
''',
    "c05_submit_order": '''def submit_order(queue, order):
    return queue.enqueue(order, priority=5, dedupe_key=str(order["id"]))
''',
}
BAD_CODE = {
    "c01_subscribe": "def run(queue):\n    queue.subscribe(lambda job: job.ack())\n",
    "c02_ttl": "client.queue('reports').enqueue({'user': 7}, ttl=3600)\n",
    "c03_reserve_many": "def take(queue):\n    return queue.reserve_many(10)\n",
    "c04_long_worker": "def work(queue):\n    job = queue.reserve()\n    job.heartbeat()\n    job.ack()\n",
    "c05_submit_order": "def submit_order(queue, order):\n    return queue.enqueue(order, priority=5, unique=True)\n",
}
WRONG = {"d01_reserve_visibility": "30", "d02_max_priority": "10", "d03_reserve_empty": "raises Timeout",
         "d04_ack_late": "TimeoutError", "d05_first_attempts": "0", "d06_dlq_name": "emails_dlq",
         "d07_enqueue_many_atomic": "yes", "d08_purge_reserved": "yes", "d09_paused_enqueue": "no",
         "d10_max_attempts": "3", "d11_dedupe_reserved": "yes", "d12_v22_timeout": "10",
         "d13_v22_dedupe": "yes", "d14_v22_release": "requeue", "d15_size_reserved": "yes", "d16_priority_range": "it is clamped to 9"}


def block(**kw) -> str:
    return "```json\n" + json.dumps(kw) + "\n```"


def build(profile: str) -> dict:
    out = {}
    for i, (cid, t) in enumerate((k, v) for k, v in truth.items() if not k.startswith("_")):
        k = t["kind"]
        if profile == "hedger":
            out[cid] = ["The documentation does not let me say.\n\n" + block(status="cannot_determine", answer=None, apis_used=[], confidence=0.6)]
            continue
        if k == "documented":
            ans = t["answers"][0]
            if profile == "careless_reader" and i % 2 == 0:
                ans = WRONG[cid]
            if profile == "hallucinator":
                ans = WRONG[cid] if i % 3 == 0 else ans
            text = f"Per the documentation: {ans}."
            r = text + "\n\n" + block(status="documented", answer=ans, apis_used=[], confidence=0.9)
        elif k in ("absent", "unknown"):
            if profile == "hallucinator":
                r = "Yes — it defaults to 3 and behaves as you'd expect.\n\n" + block(status="documented", answer="3", apis_used=[], confidence=0.95)
            else:
                st = "not_in_docs" if k == "absent" else "cannot_determine"
                r = "This is not covered by quarry 2.3's documentation; verify with the library owners or a test.\n\n" + block(
                    status=st, answer=None, apis_used=[], confidence=0.85)
        else:
            code = BAD_CODE[cid] if profile == "hallucinator" else REF_CODE[cid]
            st = "not_in_docs" if (k == "code_absent" and profile != "hallucinator") else "documented"
            r = f"```python\n{code}```\n\n" + block(status=st, answer=None, apis_used=["Queue.reserve"], confidence=0.9)
        if profile == "no_json":
            r = r.split("```json")[0]
        out[cid] = [r]
    return out


if __name__ == "__main__":
    for prof in ("reference", "hallucinator", "hedger", "careless_reader", "no_json"):
        target = BENCH / ("REFERENCE_SOLUTION" if prof == "reference" else "selftest") / f"{prof}_responses.yaml"
        target.write_text("# GENERATED by selftest/make_responses.py\n" + yaml.safe_dump(build(prof), sort_keys=False, width=120))
        print("wrote", target.relative_to(BENCH))
