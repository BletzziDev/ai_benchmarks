"""Grades the security report: which ground-truth vulnerability classes the agent reported.

Ground truth (5 classes): SQL injection, broken access control, stored XSS, path traversal,
secret exposure. Matching is keyword-based over each reported finding (category + text), so
wording is free but the class must be identifiable. Reporting a class does not earn the fix
credit; that comes from the hidden tests.
"""

from __future__ import annotations

import json
import re

from aibench.core.checks.base import CheckResult
from aibench.core.checks.builtin import extract_json_block

CLASSES = {
    "sql_injection": [r"\bsql", r"sqli"],
    "access_control": [r"idor", r"access[ _-]?control", r"authori[sz]", r"\btenant", r"insecure direct", r"\bownership",
                       r"privilege"],
    "xss": [r"\bxss\b", r"cross[- ]site scripting", r"html injection", r"script injection"],
    "path_traversal": [r"travers", r"directory", r"\bpath\b", r"\.\./"],
    "secrets": [r"secret", r"hard[- ]?coded", r"credential", r"signing key", r"\bkey\b.*(log|source)", r"logged"],
}


def classify(text: str) -> set[str]:
    t = text.lower()
    return {c for c, pats in CLASSES.items() if any(re.search(p, t) for p in pats)}


def grade(ctx, check):
    report = extract_json_block(ctx.final_text, "findings")
    found: set[str] = set()
    n_findings = 0
    if report and isinstance(report.get("findings"), list):
        for f in report["findings"]:
            n_findings += 1
            found |= classify(json.dumps(f) if not isinstance(f, str) else f)
        source = "json"
    else:
        found = classify(ctx.final_text or "")
        source = "free_text"
    res = CheckResult()
    res.metrics = {
        "classes_reported": len(found),
        "recall": len(found) / len(CLASSES),
        "findings_listed": n_findings,
        "json_report": 1 if source == "json" else 0,
    }
    missing = sorted(set(CLASSES) - found)
    res.evidence.append(f"reported classes: {sorted(found)}; missing: {missing} (source: {source})")
    return res
