"""Static maintainability metrics for code_quality/legacy_report_refactor (stdlib ``ast``/``tokenize``).

Every metric is computed for the original and the final package and mapped to [0, 1] relative to
the original, so the score measures *improvement*, with explicit targets:

  cc_score         0.5*lin(max cyclomatic complexity: original -> 10) + 0.5*lin(mean: original -> 3.5)
  length_score     lin(longest function in lines: original -> 40)
  nesting_score    lin(deepest block nesting: original -> 3)       (elif chains count as one level)
  dup_score        lin(duplicated 30-token shingle ratio: original -> 0.03)
  magic_score      lin(numeric literals inside functions other than 0, 1, -1, 2, 100: original -> 0)
  typing_score     fraction of public functions with fully annotated parameters and return
  overengineering  min(loc ratio <= 1.35 -> 1 .. 2.0 -> 0; new classes <= 4 -> 1 .. 12 -> 0;
                       new modules <= 3 -> 1 .. 8 -> 0)
"""

from __future__ import annotations

import ast
import io
import sys
import tokenize
from pathlib import Path

from aibench.core.checks.base import CheckResult

PACKAGE = "ledgerly"
ALLOWED_NUMBERS = {0, 1, -1, 2, 100}
SHINGLE = 30
BLOCKS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try, ast.Match)


def lin(x: float, zero_at: float, full_at: float) -> float:
    if zero_at == full_at:
        return 1.0 if x <= full_at else 0.0
    return max(0.0, min(1.0, (zero_at - x) / (zero_at - full_at)))


def _functions(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def _own_nodes(fn: ast.AST):
    """Nodes of a function excluding nested function/class bodies."""
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        n = stack.pop()
        yield n
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            stack.extend(ast.iter_child_nodes(n))


def cyclomatic(fn: ast.AST) -> int:
    cc = 1
    for n in _own_nodes(fn):
        if isinstance(n, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler, ast.match_case)):
            cc += 1
        elif isinstance(n, ast.BoolOp):
            cc += len(n.values) - 1
        elif isinstance(n, ast.comprehension):
            cc += 1 + len(n.ifs)
    return cc


def nesting(fn: ast.AST) -> int:
    def depth(stmts, d: int) -> int:
        best = d
        for s in stmts:
            if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(s, BLOCKS):
                inner = d + 1
                bodies = [getattr(s, "body", [])]
                orelse = getattr(s, "orelse", [])
                if isinstance(s, ast.If) and len(orelse) == 1 and isinstance(orelse[0], ast.If):
                    best = max(best, depth(orelse, d))  # elif: same level
                else:
                    bodies.append(orelse)
                bodies += [h.body for h in getattr(s, "handlers", [])] + [getattr(s, "finalbody", [])]
                bodies += [c.body for c in getattr(s, "cases", [])]
                for b in bodies:
                    best = max(best, depth(b, inner))
        return best

    return depth(fn.body, 0)


def magic_numbers(tree: ast.AST) -> int:
    count = 0
    for fn in _functions(tree):
        for n in _own_nodes(fn):
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
                if n.value not in ALLOWED_NUMBERS:
                    count += 1
    return count


def shingles(source: str) -> list[tuple[str, ...]]:
    toks = []
    try:
        for t in tokenize.generate_tokens(io.StringIO(source).readline):
            if t.type in (tokenize.NEWLINE, tokenize.NL, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT,
                          tokenize.ENDMARKER):
                continue
            if t.type == tokenize.NAME:
                import keyword

                toks.append(t.string if keyword.iskeyword(t.string) else "N")
            elif t.type == tokenize.NUMBER:
                toks.append("0")
            elif t.type == tokenize.STRING:
                toks.append("S")
            else:
                toks.append(t.string)
    except (tokenize.TokenError, IndentationError):
        return []
    return [tuple(toks[i:i + SHINGLE]) for i in range(max(0, len(toks) - SHINGLE + 1))]


def analyze(root: Path) -> dict:
    pkg = Path(root) / PACKAGE
    files = sorted(p for p in pkg.rglob("*.py") if "__pycache__" not in p.parts)
    ccs, lengths, nests, sh = [], [], [], []
    magic = classes = loc = 0
    public, annotated = 0, 0
    third_party = set()
    std = set(sys.stdlib_module_names)
    for f in files:
        src = f.read_text(encoding="utf-8")
        tree = ast.parse(src)
        loc += sum(1 for line in src.splitlines() if line.strip() and not line.strip().startswith("#"))
        sh += shingles(src)
        magic += magic_numbers(tree)
        classes += sum(isinstance(n, ast.ClassDef) for n in ast.walk(tree))
        for fn in _functions(tree):
            ccs.append(cyclomatic(fn))
            lengths.append(fn.end_lineno - fn.lineno + 1)
            nests.append(nesting(fn))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
                public += 1
                args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                if node.returns is not None and all(a.annotation is not None for a in args):
                    annotated += 1
        for n in ast.walk(tree):
            mods = []
            if isinstance(n, ast.Import):
                mods = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                mods = [n.module]
            for m in mods:
                top = m.split(".")[0]
                if top != PACKAGE and top not in std and top != "__future__":
                    third_party.add(top)
    counts: dict = {}
    for s in sh:
        counts[s] = counts.get(s, 0) + 1
    dup = (sum(1 for s in sh if counts[s] > 1) / len(sh)) if sh else 0.0
    return {
        "files": len(files), "loc": loc, "functions": len(ccs), "classes": classes,
        "max_cc": max(ccs, default=0), "mean_cc": (sum(ccs) / len(ccs)) if ccs else 0.0,
        "max_func_len": max(lengths, default=0), "max_nesting": max(nests, default=0),
        "dup_ratio": dup, "magic_numbers": magic,
        "typing_coverage": (annotated / public) if public else 0.0, "third_party": sorted(third_party),
    }


def grade(ctx, check):
    res = CheckResult()
    if not (Path(ctx.final_workspace) / PACKAGE).is_dir():
        res.metrics = {k: 0.0 for k in ("cc_score", "length_score", "nesting_score", "dup_score", "magic_score",
                                        "typing_score", "overengineering_score")}
        res.metrics["third_party_imports"] = 0
        res.evidence.append("package directory missing")
        return res
    o = analyze(ctx.original_workspace)
    f = analyze(ctx.final_workspace)
    loc_ratio = f["loc"] / o["loc"] if o["loc"] else 1.0
    new_classes = max(0, f["classes"] - o["classes"])
    new_files = max(0, f["files"] - o["files"])
    over = min(lin(loc_ratio, 2.0, 1.35), lin(new_classes, 12, 4), lin(new_files, 8, 3))
    m = {
        "cc_score": 0.5 * lin(f["max_cc"], o["max_cc"], 10) + 0.5 * lin(f["mean_cc"], o["mean_cc"], 3.5),
        "length_score": lin(f["max_func_len"], o["max_func_len"], 40),
        "nesting_score": lin(f["max_nesting"], o["max_nesting"], 3),
        "dup_score": lin(f["dup_ratio"], o["dup_ratio"], 0.03),
        "magic_score": lin(f["magic_numbers"], o["magic_numbers"], 0),
        "typing_score": f["typing_coverage"],
        "overengineering_score": over,
        "loc_ratio": round(loc_ratio, 3), "new_classes": new_classes, "new_files": new_files,
        "third_party_imports": len(f["third_party"]),
        "max_cc": f["max_cc"], "mean_cc": round(f["mean_cc"], 2), "max_func_len": f["max_func_len"],
        "max_nesting": f["max_nesting"], "dup_ratio": round(f["dup_ratio"], 4), "magic_numbers": f["magic_numbers"],
    }
    res.metrics = m
    res.details = {"original": o, "final": f}
    res.evidence.append(
        "original→final: max_cc %d→%d, mean_cc %.1f→%.1f, longest fn %d→%d lines, nesting %d→%d, dup %.3f→%.3f, "
        "magic %d→%d, typed public fns %.0f%%→%.0f%%, LOC %d→%d (x%.2f), classes +%d, modules +%d"
        % (o["max_cc"], f["max_cc"], o["mean_cc"], f["mean_cc"], o["max_func_len"], f["max_func_len"], o["max_nesting"],
           f["max_nesting"], o["dup_ratio"], f["dup_ratio"], o["magic_numbers"], f["magic_numbers"],
           100 * o["typing_coverage"], 100 * f["typing_coverage"], o["loc"], f["loc"], loc_ratio, new_classes, new_files))
    if f["third_party"]:
        res.evidence.append(f"third-party imports added: {f['third_party']}")
    return res
