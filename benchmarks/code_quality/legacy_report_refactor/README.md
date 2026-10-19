# code_quality/legacy_report_refactor

Medium refactoring benchmark (Python stdlib). The agent must make a 418-line legacy reporting
module maintainable while keeping every output byte-identical and the public API unchanged, and
without over-engineering.

```bash
benchmark run code_quality/legacy_report_refactor --model <label> --attempts 3
benchmark selftest code_quality/legacy_report_refactor
```

| Path | Role |
|---|---|
| `PROMPT.md` | exact prompt |
| `EVAL.md` | traps, metric formulas, weights, critical failures, observed selftests, limitations |
| `fixtures/workspace/` | `ledgerly` package, sample data, public tests |
| `tests/hidden/legacy_original.py` | frozen copy of the original module (behavioural oracle) |
| `tests/hidden/test_hidden_equivalence.py` | property-based equivalence + API tests |
| `tests/public/` | benchmark copy of the public tests |
| `tests/grader.py` | static maintainability metrics (`ast`, `tokenize`) |
| `REFERENCE_SOLUTION/` | reference refactor and report |
| `selftest/` | decoys: cosmetic, behaviour_change, over_engineered (+ reports) |

Compute metrics by hand: `python -c "import sys; sys.path.insert(0,'tests'); import grader; print(grader.analyze('fixtures/workspace'))"`.
