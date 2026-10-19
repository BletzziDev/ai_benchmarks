import math

from aibench.core.stats import bootstrap_mean_ci, describe, pass_at_k, pass_hat_k, paired_comparison


def test_pass_at_k_matches_closed_form():
    assert pass_at_k(10, 0, 1) == 0.0
    assert pass_at_k(10, 10, 5) == 1.0
    assert math.isclose(pass_at_k(10, 3, 1), 0.3)
    assert math.isclose(pass_at_k(5, 2, 2), 1 - math.comb(3, 2) / math.comb(5, 2))
    assert pass_at_k(3, 1, 4) is None


def test_pass_hat_k():
    assert pass_hat_k(4, 4, 4) == 1.0
    assert pass_hat_k(4, 3, 4) == 0.0
    assert math.isclose(pass_hat_k(4, 3, 2), 3 / 6)


def test_describe_ci_contains_mean():
    d = describe([70, 80, 90])
    assert d["n"] == 3 and d["mean"] == 80 and d["ci_low"] < 80 < d["ci_high"]
    assert describe([50])["std"] is None
    assert describe([])["mean"] is None


def test_bootstrap_is_seeded_and_paired_comparison_verdicts():
    assert bootstrap_mean_ci([1, 2, 3, 4], seed=1) == bootstrap_mean_ci([1, 2, 3, 4], seed=1)
    a = {f"b{i}": 80 + i for i in range(10)}
    b = {f"b{i}": 60 + i for i in range(10)}
    pc = paired_comparison(a, b)
    assert pc["mean_diff"] == 20 and pc["verdict"].startswith("A better")
    pc = paired_comparison(a, {k: v + 0.1 * ((-1) ** i) for i, (k, v) in enumerate(a.items())})
    assert pc["verdict"] == "no significant difference"
    assert paired_comparison({"x": 1}, {"y": 2})["n_pairs"] == 0
