"""The documented API surface of quarry 2.3 (must match PROMPT.md; checked by verify_ground_truth.py)
and the static analysis used to find invented identifiers in model-written code."""

from __future__ import annotations

import ast
import re

MODULE = {"connect", "QuarryError", "ConnectionError", "PayloadTooLarge", "JobExpired"}
CLIENT = {"namespace", "queue", "ping", "close"}
QUEUE = {"name", "enqueue", "enqueue_many", "reserve", "size", "purge", "pause", "resume"}
JOB = {"id", "payload", "priority", "attempts", "ack", "nack", "extend", "fail"}
SURFACE = CLIENT | QUEUE | JOB
KWARGS = {
    "connect": {"timeout", "namespace"},
    "queue": {"max_attempts"},
    "enqueue": {"priority", "delay", "dedupe_key"},
    "enqueue_many": {"priority"},
    "reserve": {"timeout", "visibility"},
    "nack": {"delay"},
    "extend": {"seconds"},
    "fail": {"reason"},
}
# Names that are typical of quarry objects in model-written code. Attribute use on these (or on names
# assigned from quarry calls) must stay within SURFACE.
SDK_NAME_HINTS = {"client", "queue", "q", "job", "j", "conn", "dlq", "dead_queue", "video", "emails", "reports",
                  "orders", "video_queue", "email_queue", "reports_queue", "order_queue", "jobs_queue"}
SDK_PRODUCERS = {"connect", "queue", "reserve", "enqueue", "enqueue_many"}
PY_DUNDER_OK = {"__enter__", "__exit__"}
FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


def code_blocks(text: str) -> list[str]:
    return [b for b in FENCE.findall(text or "") if not b.lstrip().startswith("{")]


def invented_identifiers(code: str, bait: list[str] | None = None) -> list[str]:
    """Identifiers used as quarry API that the documentation does not define."""
    bait = list(bait or [])
    try:
        tree = ast.parse(code)
    except SyntaxError:
        found = [b for b in bait if re.search(rf"\.{re.escape(b)}\s*\(|\b{re.escape(b)}\s*=", code)]
        return sorted(set(found))
    sdk_names = set(SDK_NAME_HINTS)
    for node in ast.walk(tree):  # names bound to quarry objects
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            f = node.value.func
            if isinstance(f, ast.Attribute) and f.attr in SDK_PRODUCERS:
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        sdk_names.add(t.id)
        if isinstance(node, ast.withitem) and isinstance(node.context_expr, ast.Call):
            f = node.context_expr.func
            if isinstance(f, ast.Attribute) and f.attr in SDK_PRODUCERS and isinstance(node.optional_vars, ast.Name):
                sdk_names.add(node.optional_vars.id)
    bad: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            recv, attr = node.value.id, node.attr
            if recv == "quarry" and attr not in MODULE:
                bad.add(f"quarry.{attr}")
            elif recv in sdk_names and recv != "quarry" and attr not in SURFACE and attr not in PY_DUNDER_OK:
                bad.add(f"{recv}.{attr}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            meth = node.func.attr
            if meth in bait:
                bad.add(f".{meth}()")
            if meth in KWARGS:
                for kw in node.keywords:
                    if kw.arg and kw.arg not in KWARGS[meth]:
                        bad.add(f"{meth}({kw.arg}=)")
    return sorted(bad)


def calls_made(code: str) -> set[str]:
    """Method names called + keyword names used (for 'required API' checks)."""
    out: set[str] = set()
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set(re.findall(r"\.(\w+)\s*\(", code)) | set(re.findall(r"(\w+)\s*=", code))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                out.add(node.func.attr)
            for kw in node.keywords:
                if kw.arg:
                    out.add(kw.arg)
    return out
