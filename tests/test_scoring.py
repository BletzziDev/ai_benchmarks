from aibench.core.scoring import apply_transform, score_attempt
from aibench.core.spec import ScoringSpec, Transform


def spec(**kw):
    base = {
        "pass_threshold": 70,
        "criteria": [
            {"id": "a", "weight": 60, "metric": "c.a"},
            {"id": "b", "weight": 40, "metric": "c.b", "required": False},
        ],
    }
    base.update(kw)
    return ScoringSpec.model_validate(base)


def test_transforms():
    assert apply_transform(150, Transform(type="linear", zero_at=300, full_at=80)) == (300 - 150) / 220
    assert apply_transform(10, Transform(type="linear", zero_at=300, full_at=80)) == 1.0
    assert apply_transform(0, Transform(type="threshold", threshold=0, invert=True)) == 1.0
    assert apply_transform(2, Transform(type="threshold", threshold=0, invert=True)) == 0.0
    assert apply_transform(True, Transform()) == 1.0
    assert apply_transform(None, Transform()) is None


def test_weighted_score_and_pass():
    r = score_attempt(spec(), {"c.a": 1.0, "c.b": 0.5})
    assert r.score == 80.0 and r.passed is True and r.status == "scored"


def test_optional_criterion_missing_is_provisional_and_renormalised():
    r = score_attempt(spec(), {"c.a": 0.8})
    assert r.status == "provisional" and r.score == 80.0 and abs(r.completeness - 0.6) < 1e-9


def test_required_criterion_missing_gives_no_verdict():
    r = score_attempt(spec(), {"c.b": 1.0})
    assert r.status == "incomplete" and r.passed is None


def test_critical_failures_cannot_be_compensated():
    s = spec(critical_failures=[{"id": "lie", "when": "c.lie == 1", "effect": "cap", "cap": 40},
                                {"id": "boom", "when": "c.boom > 0", "effect": "zero"}])
    r = score_attempt(s, {"c.a": 1, "c.b": 1, "c.lie": 1})
    assert r.score == 40 and r.score_before_critical == 100 and r.passed is False
    r = score_attempt(s, {"c.a": 1, "c.b": 1, "c.boom": 3})
    assert r.score == 0 and [c["id"] for c in r.critical_failures] == ["boom"]


def test_pass_gates():
    r = score_attempt(spec(pass_requires=["c.gate == 1"]), {"c.a": 1, "c.b": 1, "c.gate": 0})
    assert r.score == 100 and r.passed is False
