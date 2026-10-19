"""Turns check metrics into a 0-100 score, a pass/fail verdict and critical-failure records.

Rules (also in docs/scoring.md):
1. Each criterion maps one metric to [0, 1] (optionally through a declared transform) and has a
   weight fixed in benchmark.yaml before any run.
2. Unavailable *optional* criteria are excluded and the remaining weights renormalised; the result
   is flagged ``provisional``. Unavailable *required* criteria make the attempt ``incomplete``:
   it has a provisional score but no pass/fail verdict.
3. Critical failures are evaluated independently, recorded separately and cannot be compensated:
   any critical failure forces ``passed = False``; ``zero`` sets the score to 0, ``cap`` limits it.
4. Raw metrics are preserved next to the normalised score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aibench.core.expressions import evaluate
from aibench.core.spec import Criterion, ScoringSpec, Transform


@dataclass
class CriterionScore:
    id: str
    weight: float
    metric: str
    raw: Any
    value: float | None  # normalised [0,1], None if unavailable
    required: bool


@dataclass
class ScoreResult:
    score: float | None  # 0-100 after critical-failure effects
    score_before_critical: float | None
    passed: bool | None
    status: str  # scored | provisional | incomplete | not_evaluated
    criteria: list[CriterionScore] = field(default_factory=list)
    critical_failures: list[dict[str, Any]] = field(default_factory=list)
    gates: list[dict[str, Any]] = field(default_factory=list)
    completeness: float = 1.0  # fraction of total weight that was available

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score, "score_before_critical": self.score_before_critical, "passed": self.passed,
            "status": self.status, "completeness": round(self.completeness, 4),
            "criteria": [c.__dict__ for c in self.criteria], "critical_failures": self.critical_failures,
            "gates": self.gates,
        }


def apply_transform(raw: Any, t: Transform) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        raw = 1.0 if raw else 0.0
    try:
        x = float(raw)
    except (TypeError, ValueError):
        return None
    if t.type == "identity":
        return max(0.0, min(1.0, x))
    if t.type == "threshold":
        assert t.threshold is not None
        ok = x <= t.threshold if t.invert else x >= t.threshold
        return 1.0 if ok else 0.0
    if t.type == "linear":
        assert t.zero_at is not None and t.full_at is not None
        if t.full_at == t.zero_at:
            return 1.0 if x >= t.full_at else 0.0
        return max(0.0, min(1.0, (x - t.zero_at) / (t.full_at - t.zero_at)))
    return None


def score_attempt(spec: ScoringSpec, metrics: dict[str, Any]) -> ScoreResult:
    crit_scores: list[CriterionScore] = []
    for c in spec.criteria:
        raw = metrics.get(c.metric)
        crit_scores.append(CriterionScore(c.id, c.weight, c.metric, raw, apply_transform(raw, c.transform), c.required))
    total_w = sum(c.weight for c in crit_scores)
    avail = [c for c in crit_scores if c.value is not None]
    avail_w = sum(c.weight for c in avail)
    missing_required = [c.id for c in crit_scores if c.value is None and c.required]
    if not avail:
        return ScoreResult(None, None, None, "not_evaluated", crit_scores, completeness=0.0)
    base = 100.0 * sum(c.weight * c.value for c in avail) / avail_w  # type: ignore[operator]
    status = "scored" if avail_w == total_w else ("incomplete" if missing_required else "provisional")

    criticals = []
    for cf in spec.critical_failures:
        try:
            hit = bool(evaluate(cf.when, metrics))
        except Exception as e:  # malformed rule = benchmark bug; surface it loudly
            criticals.append({"id": cf.id, "error": str(e), "triggered": False})
            continue
        if hit:
            criticals.append({"id": cf.id, "description": cf.description, "effect": cf.effect, "cap": cf.cap,
                              "when": cf.when, "triggered": True})
    triggered = [c for c in criticals if c.get("triggered")]
    score = base
    for c in triggered:
        if c["effect"] == "zero":
            score = 0.0
        elif c["effect"] == "cap":
            score = min(score, float(c["cap"]))

    gates = []
    for g in spec.pass_requires:
        try:
            ok = bool(evaluate(g, metrics))
        except Exception as e:
            ok = False
            gates.append({"gate": g, "ok": False, "error": str(e)})
            continue
        gates.append({"gate": g, "ok": ok})

    if status == "incomplete":
        passed = None if not triggered else False
    else:
        passed = (score >= spec.pass_threshold) and not triggered and all(g["ok"] for g in gates)
    return ScoreResult(round(score, 3), round(base, 3), passed, status, crit_scores,
                       [c for c in criticals if c.get("triggered") or c.get("error")], gates,
                       completeness=avail_w / total_w if total_w else 0.0)


def flatten_metrics(check_results: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for cid, res in check_results.items():
        for k, v in (res.get("metrics") or {}).items():
            flat[f"{cid}.{k}"] = v
        flat[f"{cid}.__status"] = 1 if res.get("status") == "ok" else 0
    return flat


def criterion_for(spec: ScoringSpec, cid: str) -> Criterion | None:
    return next((c for c in spec.criteria if c.id == cid), None)
