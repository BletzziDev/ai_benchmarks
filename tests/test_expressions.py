import pytest

from aibench.core.expressions import ExpressionError, evaluate


def test_basic_comparisons_and_logic():
    m = {"a.x": 3, "a.y": 0, "b.z": 1.5}
    assert evaluate("a.x > 2 and a.y == 0", m) is True
    assert evaluate("a.x + b.z >= 4.5", m) is True
    assert evaluate("not (a.x > 5) or a.y", m) is True
    assert evaluate("min(a.x, b.z) == 1.5", m) is True


def test_missing_metrics_never_trigger():
    assert evaluate("nope.metric > 0", {}) is False
    assert evaluate("nope.metric == 0", {}) is False
    assert evaluate("missing(nope.metric)", {}) is True
    assert evaluate("a.x / 0 > 1", {"a.x": 1}) is False


@pytest.mark.parametrize("expr", ["__import__('os')", "a.x[0] > 1", "(lambda: 1)()", "open('f')", "'s' == 's'",
                                  "a.__class__ > 0"])
def test_rejects_unsafe_syntax(expr):
    with pytest.raises(ExpressionError):
        evaluate(expr, {"a.x": 1})
