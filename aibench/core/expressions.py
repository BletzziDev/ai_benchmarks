"""A deliberately tiny, safe expression language for gates and critical-failure rules.

Supported: numbers, booleans, metric references (``check.metric`` or ``check.metric.sub``),
comparisons, ``and``/``or``/``not``, arithmetic (+ - * /), ``min``/``max``/``abs``.
Anything else (attribute access on objects, calls to other names, subscripts, lambdas) is
rejected at parse time. Unavailable metrics evaluate to ``None``; any comparison involving
``None`` is ``False`` so a missing metric can never *trigger* a critical failure by accident —
use ``missing(x)`` to test explicitly.
"""

from __future__ import annotations

import ast
import operator
from typing import Any, Mapping

_CMP = {
    ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Lt: operator.lt, ast.LtE: operator.le,
    ast.Eq: operator.eq, ast.NotEq: operator.ne,
}
_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_FUNCS = {"min": min, "max": max, "abs": abs}


class ExpressionError(ValueError):
    pass


def _dotted(node: ast.AST) -> str | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def references(expr: str) -> set[str]:
    tree = _parse(expr)
    refs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and not isinstance(getattr(node, "_parent", None), ast.Attribute):
            d = _dotted(node)
            if d:
                refs.add(d)
    # keep only maximal dotted names
    return {r for r in refs if not any(o != r and o.startswith(r + ".") for o in refs)}


def _parse(expr: str) -> ast.Expression:
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ExpressionError(f"invalid expression {expr!r}: {e}") from e
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child._parent = node  # type: ignore[attr-defined]
        allowed = (
            ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not, ast.USub, ast.Compare,
            ast.BinOp, ast.Constant, ast.Name, ast.Attribute, ast.Load, ast.Call, *_CMP, *_BIN,
        )
        if not isinstance(node, allowed):
            raise ExpressionError(f"disallowed syntax in {expr!r}: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in (*_FUNCS, "missing"):
                raise ExpressionError(f"only min/max/abs/missing calls are allowed in {expr!r}")
            if node.keywords:
                raise ExpressionError("keyword arguments are not allowed")
    return tree


def evaluate(expr: str, metrics: Mapping[str, Any]) -> Any:
    tree = _parse(expr)

    def ev(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float, bool)) and node.value is not None:
                raise ExpressionError("only numeric/boolean constants are allowed")
            return node.value
        if isinstance(node, (ast.Name, ast.Attribute)):
            name = _dotted(node)
            if name in ("true", "True"):
                return True
            if name in ("false", "False"):
                return False
            if name is None:
                raise ExpressionError("bad reference")
            return metrics.get(name)
        if isinstance(node, ast.BoolOp):
            vals = [ev(v) for v in node.values]
            if isinstance(node.op, ast.And):
                return all(bool(v) for v in vals)
            return any(bool(v) for v in vals)
        if isinstance(node, ast.UnaryOp):
            v = ev(node.operand)
            if isinstance(node.op, ast.Not):
                return not bool(v)
            return None if v is None else -v
        if isinstance(node, ast.Compare):
            left = ev(node.left)
            for op, comp in zip(node.ops, node.comparators):
                right = ev(comp)
                if left is None or right is None:
                    return False
                if not _CMP[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.BinOp):
            a, b = ev(node.left), ev(node.right)
            if a is None or b is None:
                return None
            if isinstance(node.op, ast.Div) and b == 0:
                return None
            return _BIN[type(node.op)](a, b)
        if isinstance(node, ast.Call):
            fname = node.func.id  # type: ignore[union-attr]
            if fname == "missing":
                return all(ev(a) is None for a in node.args)
            args = [ev(a) for a in node.args]
            if any(a is None for a in args):
                return None
            return _FUNCS[fname](*args)
        raise ExpressionError(f"unsupported node {type(node).__name__}")

    return ev(tree)
