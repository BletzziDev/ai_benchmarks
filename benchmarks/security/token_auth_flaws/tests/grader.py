"""Grades the security report: which ground-truth flaw classes the agent reported (keyword-based)."""

from __future__ import annotations

import json
import re

from aibench.core.checks.base import CheckResult
from aibench.core.checks.builtin import extract_json_block

CLASSES = {
    "alg_none": [r"\balg", r"\bnone\b", r"unsigned", r"algorithm"],
    "expiry": [r"expir", r"\bexp\b", r"lifetime"],
    "timing": [r"timing", r"constant[- ]time", r"compare_digest", r"side[- ]channel"],
    "deserialization": [r"pickle", r"deserializ", r"deserialis", r"\brce\b", r"remote code"],
    "password_hashing": [r"sha-?1", r"salt", r"password hash", r"weak hash", r"pbkdf2", r"scrypt", r"bcrypt", r"argon"],
}


def classify(text: str) -> set[str]:
    t = text.lower()
    return {c for c, pats in CLASSES.items() if any(re.search(p, t) for p in pats)}


def grade(ctx, check):
    report = extract_json_block(ctx.final_text, "findings")
    found: set[str] = set()
    if report and isinstance(report.get("findings"), list):
        for f in report["findings"]:
            found |= classify(f if isinstance(f, str) else json.dumps(f))
        source = "json"
    else:
        found = classify(ctx.final_text or "")
        source = "free_text"
    res = CheckResult(metrics={"classes_reported": len(found), "recall": len(found) / len(CLASSES),
                               "json_report": 1 if source == "json" else 0})
    res.evidence.append(f"reported: {sorted(found)}; missing: {sorted(set(CLASSES) - found)} (source: {source})")
    return res
