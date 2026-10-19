"""Consistency checks between the documentation (PROMPT.md), the API surface used by the grader and the
labels (run: python tests/verify_ground_truth.py). Prints a JSON line and exits non-zero on problems.

- every identifier in tests/sdk_surface.py is mentioned in the documentation;
- every bait identifier of a "not in docs" case is NOT documented as part of 2.3 (it may only appear in
  the "Changes from 2.2 to 2.3" section as removed);
- every expected answer of a documented case is literally present in the documentation;
- topics of "cannot determine" cases are not covered (forbidden words absent from the documentation);
- the reference responses use no invented identifiers and the grader scores them 1.0.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sdk_surface import CLIENT, JOB, KWARGS, MODULE, QUEUE  # noqa: E402

BENCH = HERE.parent
DOC = (BENCH / "PROMPT.md").read_text()
DOC23 = DOC.split("## Changes from 2.2 to 2.3")[0]
NOT_COVERED = {  # words whose presence would mean the docs DO cover an "unknown" topic
    "u01_thread_safety": ["thread"], "u02_fifo": ["fifo", "order of", "first-in"], "u03_max_delay": ["maximum delay", "max delay"],
    "u04_connect_retry": ["retry", "retries"], "u05_fail_reason": ["failure_reason", "job.reason"],
    "u06_queue_name_len": ["characters", "length"],
}


# Derived answers: the documentation sentence the answer follows from must be present.
ANCHORS = {"d06_dlq_name": '"<name>.dead"'}
YES_NO_ANCHORS = {
    "d07_enqueue_many_atomic": "either all are enqueued or none is",
    "d08_purge_reserved": "reserved jobs are not affected",
    "d09_paused_enqueue": "`enqueue` still accepts jobs",
    "d11_dedupe_reserved": "*reserved* (held by a worker)",
    "d13_v22_dedupe": "added `dedupe_key` to `queue.enqueue`",
    "d15_size_reserved": "number of pending jobs that are not reserved",
}


def main() -> dict:
    problems = []
    truth = yaml.safe_load((HERE / "ground_truth.yaml").read_text())
    for ident in MODULE | CLIENT | QUEUE | JOB | {k for v in KWARGS.values() for k in v}:
        if not re.search(rf"\b{re.escape(ident)}\b", DOC):
            problems.append(f"surface identifier {ident!r} not in documentation")
    for cid, t in truth.items():
        if cid.startswith("_"):
            continue
        if t["kind"] in ("absent", "code_absent"):
            for b in t["bait"]:
                if re.search(rf"\b{re.escape(b)}\b", DOC23):
                    problems.append(f"{cid}: bait {b!r} appears in the 2.3 reference")
        if t["kind"] == "documented":
            low = DOC.lower()
            anchors = [ANCHORS[cid]] if cid in ANCHORS else [a.replace("job.", "").rstrip("()") for a in t["answers"]]
            if t["answers"][0] in ("yes", "no"):
                anchors = [YES_NO_ANCHORS[cid]]
            if not any(a in low for a in anchors):
                problems.append(f"{cid}: no expected answer {t['answers']} appears in the documentation")
        if t["kind"] == "unknown":
            for w in NOT_COVERED.get(cid, []):
                if w in DOC23.lower():
                    problems.append(f"{cid}: documentation mentions {w!r}; topic may be covered")
    # reference responses must grade perfectly
    from grader import grade_case

    ref = yaml.safe_load((BENCH / "REFERENCE_SOLUTION" / "reference_responses.yaml").read_text())
    for cid, t in truth.items():
        if cid.startswith("_"):
            continue
        r = grade_case(t, ref[cid][0])
        if r["score"] != 1.0:
            problems.append(f"reference response for {cid} scores {r['score']} ({r['outcome']})")
    return {"ok": not problems, "problems": problems}


if __name__ == "__main__":
    out = main()
    print(json.dumps(out))
    sys.exit(0 if out["ok"] else 1)
