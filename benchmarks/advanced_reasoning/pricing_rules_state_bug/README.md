# advanced_reasoning/pricing_rules_state_bug

Hard reasoning benchmark (Python). A cart pricing engine (`checkout`) disagrees with its written
specification (`docs/RULES.md`) only for specific combinations of membership tier, coupon thresholds,
bundles and sale items. Two complaints are given; a third defect is implied by a documented invariant.

```bash
benchmark run advanced_reasoning/pricing_rules_state_bug --model <label> --attempts 3
benchmark selftest pricing_rules_state_bug
```

Requires Python ≥ 3.11, `pytest`, `hypothesis`. No network.

| Path | Role |
|---|---|
| `PROMPT.md` | exact task prompt |
| `EVAL.md` | defects, scoring, critical failures, observed selftests, limitations |
| `benchmark.yaml` | configuration |
| `fixtures/workspace/` | engine, `docs/RULES.md`, public tests |
| `tests/hidden/` | oracle (`_pricing_oracle.py`) and hidden tests |
| `tests/public/` | benchmark copy of the public tests |
| `REFERENCE_SOLUTION/` | reference fix + regression tests + report |
| `selftest/` | decoys: special-casing, reorder hack, reported-only partial fix, false claim |

Manual check: copy `fixtures/workspace`, overlay `REFERENCE_SOLUTION/files`, copy both files from
`tests/hidden/` next to it, run `python -m pytest -q`.
