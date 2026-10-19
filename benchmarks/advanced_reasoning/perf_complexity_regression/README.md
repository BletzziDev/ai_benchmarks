# advanced_reasoning/perf_complexity_regression

Medium/hard performance benchmark (Python). `eventstats.summarize()` became quadratic in release 2.3.0;
the agent must measure, find the hot spots (list membership in the dedupe loop and `list.index` in sort
keys; `deepcopy` is a red herring) and restore near-linear scaling with **identical** results.

```bash
benchmark run advanced_reasoning/perf_complexity_regression --model <label> --attempts 3
benchmark selftest perf_complexity_regression     # ~4 min: the no-op/decoys are genuinely slow
```

Requires Python ≥ 3.11, `pytest`, `hypothesis`. No network.

| Path | Role |
|---|---|
| `PROMPT.md` | exact task prompt |
| `EVAL.md` | scoring, timing method, observed selftests, limitations |
| `benchmark.yaml` | configuration |
| `fixtures/workspace/` | `eventstats` 2.3.0 + `ops/PERF-118.md` |
| `tests/hidden/` | frozen 2.3.0 implementation (`_original_230.py`) + hidden tests |
| `tests/public/` | benchmark copy of the public tests |
| `REFERENCE_SOLUTION/` | reference fix, perf regression test, report |
| `selftest/` | decoys: unsafe memoisation, fast-but-wrong, micro-optimisation |
