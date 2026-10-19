"""Statistics for repeated attempts and model comparisons (stdlib only).

- Per benchmark: mean, sample std, standard error and a t-based CI over attempts.
- pass@k (unbiased estimator, Chen et al. 2021) and pass^k (all k attempts succeed; tau-bench).
- Comparisons are *paired* by benchmark (and attempts are averaged first), with a percentile
  bootstrap CI over benchmarks, following the recommendation to analyse question-level paired
  differences (Miller 2024, "Adding Error Bars to Evals").
"""

from __future__ import annotations

import math
import random
import statistics
from typing import Sequence

# two-sided Student t critical values for 95% CI, df=1..30 (beyond: normal approx)
_T95 = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228, 2.201, 2.179, 2.160, 2.145, 2.131,
        2.120, 2.110, 2.101, 2.093, 2.086, 2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042]


def t_crit(df: int, confidence: float = 0.95) -> float:
    if abs(confidence - 0.95) > 1e-9:
        # normal approximation for other levels
        return _z(confidence)
    if df <= 0:
        return float("nan")
    return _T95[df - 1] if df <= 30 else 1.96


def _z(confidence: float) -> float:
    # inverse normal CDF via bisection (no scipy)
    target = 1 - (1 - confidence) / 2
    lo, hi = 0.0, 10.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if 0.5 * (1 + math.erf(mid / math.sqrt(2))) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def describe(values: Sequence[float], confidence: float = 0.95) -> dict[str, float | int | None]:
    vals = [float(v) for v in values if v is not None]
    n = len(vals)
    if n == 0:
        return {"n": 0, "mean": None, "std": None, "sem": None, "ci_low": None, "ci_high": None, "min": None, "max": None}
    mean = statistics.fmean(vals)
    if n == 1:
        return {"n": 1, "mean": mean, "std": None, "sem": None, "ci_low": None, "ci_high": None, "min": mean, "max": mean}
    std = statistics.stdev(vals)
    sem = std / math.sqrt(n)
    h = t_crit(n - 1, confidence) * sem
    return {"n": n, "mean": mean, "std": std, "sem": sem, "ci_low": mean - h, "ci_high": mean + h,
            "min": min(vals), "max": max(vals)}


def pass_at_k(n: int, c: int, k: int) -> float | None:
    """Unbiased pass@k: probability that at least one of k samples (drawn from n, c correct) passes."""
    if n <= 0 or k > n:
        return None
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float | None:
    """pass^k: probability that k samples drawn without replacement all pass (reliability)."""
    if n <= 0 or k > n:
        return None
    return math.comb(c, k) / math.comb(n, k)


def bootstrap_mean_ci(values: Sequence[float], iterations: int = 10000, confidence: float = 0.95,
                      seed: int = 1234) -> tuple[float | None, float | None]:
    vals = [float(v) for v in values]
    if len(vals) < 2:
        return None, None
    rng = random.Random(seed)
    n = len(vals)
    means = sorted(statistics.fmean(rng.choices(vals, k=n)) for _ in range(iterations))
    a = (1 - confidence) / 2
    return means[int(a * iterations)], means[min(iterations - 1, int((1 - a) * iterations))]


def paired_comparison(a: dict[str, float], b: dict[str, float], iterations: int = 10000, confidence: float = 0.95,
                      seed: int = 1234) -> dict[str, object]:
    """Paired difference (a - b) over the keys both share."""
    keys = sorted(set(a) & set(b))
    diffs = [a[k] - b[k] for k in keys]
    if not diffs:
        return {"n_pairs": 0, "mean_diff": None, "ci_low": None, "ci_high": None, "wins": 0, "losses": 0, "ties": 0,
                "verdict": "no overlapping benchmarks"}
    lo, hi = bootstrap_mean_ci(diffs, iterations, confidence, seed)
    mean = statistics.fmean(diffs)
    if lo is None:
        verdict = "insufficient pairs for a CI"
    elif lo > 0:
        verdict = "A better (CI excludes 0)"
    elif hi is not None and hi < 0:
        verdict = "B better (CI excludes 0)"
    else:
        verdict = "no significant difference"
    return {"n_pairs": len(diffs), "mean_diff": mean, "ci_low": lo, "ci_high": hi,
            "wins": sum(d > 0.5 for d in diffs), "losses": sum(d < -0.5 for d in diffs),
            "ties": sum(abs(d) <= 0.5 for d in diffs), "verdict": verdict, "keys": keys}
