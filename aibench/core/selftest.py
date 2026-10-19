"""Grader validation: run each benchmark's declared canned solutions through the full pipeline and
check that the resulting scores/verdicts match the declared expectations.

This is how the suite shows that a benchmark *discriminates*: the reference solution must pass,
the untouched workspace must fail, and decoy solutions (symptom patches, sycophantic answers,
reckless agents) must fail for the documented reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aibench.core.config import Config, ModelConfig
from aibench.core.registry import Registry
from aibench.core.runner import Runner
from aibench.core.spec import LoadedBenchmark, SelfTestCase
from aibench.core.util import read_json


@dataclass
class SelfTestOutcome:
    benchmark: str
    case: str
    ok: bool
    score: float | None
    passed: bool | None
    critical: list[str]
    problems: list[str] = field(default_factory=list)
    run_dir: str = ""


def check_expectations(case: SelfTestCase, score: dict[str, Any], metrics: dict[str, Any]) -> list[str]:
    e = case.expect
    probs = []
    s = score.get("score")
    if e.min_score is not None and (s is None or s < e.min_score):
        probs.append(f"score {s} < expected min {e.min_score}")
    if e.max_score is not None and (s is None or s > e.max_score):
        probs.append(f"score {s} > expected max {e.max_score}")
    if e.passed is not None and score.get("passed") is not e.passed:
        probs.append(f"passed={score.get('passed')} (expected {e.passed})")
    crit = sorted(c["id"] for c in score.get("critical_failures", []) if c.get("triggered"))
    if e.critical is not None and crit != sorted(e.critical):
        probs.append(f"critical failures {crit} (expected {sorted(e.critical)})")
    for k, (lo, hi) in e.metrics.items():
        v = metrics.get(k)
        if v is None or not (lo <= float(v) <= hi):
            probs.append(f"metric {k}={v} not in [{lo}, {hi}]")
    return probs


def run_selftests(config: Config, registry: Registry, benches: list[LoadedBenchmark], backend: str | None = None,
                  only_case: str | None = None, echo: bool = False) -> list[SelfTestOutcome]:
    from aibench.core.scoring import flatten_metrics

    label = "__selftest__/scripted"
    config.models.models[label] = ModelConfig(adapter="scripted", kind="scripted",
                                              description="selftest replay adapter", options={"solution": "reference"})
    runner = Runner(config, registry, sandbox_backend=backend, echo=echo,
                    results_dir=config.results_dir / "_selftest")
    outcomes: list[SelfTestOutcome] = []
    for b in benches:
        for case in b.spec.selftest:
            if only_case and case.name != only_case:
                continue
            store = runner.create_run([b], label, attempts=1, extra={"selftest": {"benchmark": b.id, "case": case.name}})
            runner.execute(store, solution_override={b.id: case.solution})
            adir = store.attempt_dir(b.id, 1)
            st = read_json(adir / "status.json")
            if st.get("state") != "completed":
                outcomes.append(SelfTestOutcome(b.id, case.name, False, None, None, [],
                                                [f"attempt state {st.get('state')}: {st.get('error')}"], str(store.dir)))
                continue
            score = read_json(adir / "score.json")
            ev = read_json(adir / "evaluation.json")
            metrics = flatten_metrics(ev["checks"])
            probs = check_expectations(case, score, metrics)
            grader_errors = [f"check {k} errored: {v.get('error')}" for k, v in ev["checks"].items() if v["status"] == "error"]
            probs += grader_errors
            outcomes.append(SelfTestOutcome(b.id, case.name, not probs, score.get("score"), score.get("passed"),
                                            [c["id"] for c in score.get("critical_failures", []) if c.get("triggered")],
                                            probs, str(store.dir)))
    return outcomes
