"""Runs a benchmark's declared checks against the evidence of one attempt."""

from __future__ import annotations

import importlib
import time
import traceback
from typing import Any

from aibench.core.checks.base import CheckFn, CheckResult, GradingContext
from aibench.core.checks.builtin import BUILTIN_CHECKS
from aibench.core.spec import CheckSpec


def resolve_check(type_: str) -> CheckFn:
    if type_ in BUILTIN_CHECKS:
        return BUILTIN_CHECKS[type_]
    if ":" in type_:  # external plug-in: "package.module:function"
        mod, fn = type_.split(":", 1)
        return getattr(importlib.import_module(mod), fn)
    raise KeyError(f"unknown check type {type_!r}; built-ins: {sorted(BUILTIN_CHECKS)}")


def run_checks(checks: list[CheckSpec], ctx: GradingContext, log: Any = None) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for check in checks:
        t0 = time.monotonic()
        try:
            fn = resolve_check(check.type)
            res = fn(check, ctx)
        except Exception as e:
            res = CheckResult(status="error", error=f"{type(e).__name__}: {e}",
                              evidence=[f"grader error (not attributed to the model): {e}"],
                              details={"traceback": traceback.format_exc()[-6000:]})
        finally:
            ctx.close()
        results[check.id] = {
            "type": check.type, "status": res.status, "error": res.error, "metrics": res.metrics,
            "evidence": res.evidence, "details": res.details, "duration_s": round(time.monotonic() - t0, 3),
        }
        if log:
            log.info("check_done", check=check.id, status=res.status, duration_s=results[check.id]["duration_s"])
    return results
