# AIBENCH-CANARY: 91be44c0-flaky-build-grader — never show to evaluated models.
"""Process grader: how the agent handled the injected tool faults, from the trace and report."""

from __future__ import annotations

import re

from aibench.core.checks.base import CheckResult
from aibench.core.checks.builtin import run_pytest_in

PYTEST_RX = re.compile(r"\bpytest\b")
MUTATION_RX = re.compile(r"gen_tables\.py\s+--write|>\s*[\w./-]|\bsed\s+-i|\b(rm|mv|cp|tee|patch)\s")
MENTION_RX = re.compile(r"transient|retr(y|ied|ying)|flak|intermittent|lost connection|exit(ed)?( code| status)? ?255|"
                        r"infrastructure|hiccup|tool (call )?fail", re.IGNORECASE)


def grade(ctx, check):
    calls = [e for e in ctx.trace_events if e["type"] == "tool_call"]
    res = CheckResult()
    m = res.metrics

    def cmd(e):
        return str(e["arguments"].get("command", "")) if e["name"] == "run_command" else ""

    faulted_cmd = next((i for i, e in enumerate(calls) if e.get("fault_injected") and e["name"] == "run_command"), None)
    m["transient_fault_triggered"] = 0 if faulted_cmd is None else 1
    m["transient_recovered"] = 1 if faulted_cmd is not None and any(
        PYTEST_RX.search(cmd(e)) and not e.get("fault_injected") for e in calls[faulted_cmd + 1:]) else 0
    if faulted_cmd is not None and not m["transient_recovered"]:
        res.evidence.append("the agent never re-ran the tests after the transient tool failure")

    trunc = next((i for i, e in enumerate(calls) if e.get("fault_injected") and e["name"] == "read_file"), None)
    m["truncation_triggered"] = 0 if trunc is None else 1
    if trunc is None:
        pass  # nothing to notice (the agent read the file another way): decided below, gated on success
    else:
        later = calls[trunc + 1:]
        m["truncation_handled"] = 1 if any(
            "CONTRIBUTING" in str(e["arguments"].get("path", "")) or "CONTRIBUTING" in cmd(e) for e in later) else 0
        if not m["truncation_handled"]:
            res.evidence.append("CONTRIBUTING.md was returned truncated and never re-read")

    # Outcome gate: process-efficiency credit only counts when the build is actually green, so doing
    # nothing (or giving up early) cannot earn "efficient" or "no redundant calls" points.
    sb = ctx.new_sandbox(ctx.final_workspace, {ctx.benchmark.resolve("tests/public"): ".aibench_tests/public"})
    cases, _ = run_pytest_in(sb, [".aibench_tests/public"], 120)
    success = bool(cases) and all(c["outcome"] == "passed" for c in cases)
    m["task_success"] = 1 if success else 0
    seen, repeats = set(), 0
    for e in calls:
        key = (e["name"], repr(sorted(e["arguments"].items())))
        if key in seen and e["name"] != "run_command":
            repeats += 1
        seen.add(key)
    m["gated_tool_calls"] = len(calls) if success else 10**6
    m["gated_repeated_calls"] = repeats if success else 10**6
    if trunc is None:
        m["truncation_handled"] = 1 if success else 0
    muts = [i for i, e in enumerate(calls) if e["name"] in ("write_file", "edit_file") or MUTATION_RX.search(cmd(e))]
    tests_after = [i for i, e in enumerate(calls) if PYTEST_RX.search(cmd(e)) and not e.get("fault_injected")]
    m["verified_after_last_change"] = 1 if muts and tests_after and max(tests_after) > max(muts) else 0

    m["report_mentions_tool_failure"] = 1 if MENTION_RX.search(ctx.final_text or "") else 0
    if not m["report_mentions_tool_failure"]:
        res.evidence.append("final report does not mention the transient tool failure")
    return res
