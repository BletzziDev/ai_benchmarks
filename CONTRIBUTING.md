# Contributing

## Development setup

```bash
pip install -e '.[dev]'             # pytest, hypothesis, playwright, anthropic SDK
python -m playwright install chromium   # or set AIBENCH_CHROMIUM=/path/to/chromium
scripts/build_sandbox_image.sh      # optional: Docker sandbox (AIBENCH_BUILD_CA=... behind TLS proxies)
```

Before opening a PR:

```bash
benchmark validate                  # contract of every benchmark
python -m pytest -q -m "not slow"   # framework tests
python -m pytest -q -m slow         # every benchmark's selftests (reference passes, decoys fail)
```

## Adding a benchmark

1. Read `docs/benchmark-design.md` and copy the structure of a benchmark of the same mode
   (`benchmarks/bug_fixing/inventory_reservations` for agent mode,
   `benchmarks/sycophancy/code_review_pressure` for chat mode).
2. Write the decoys you want to catch **before** the hidden tests.
3. Fix criteria, weights, gates and critical failures in `benchmark.yaml` before running any model.
4. Add selftests for the reference, a no-op and each decoy, run `benchmark selftest <id>`, and record
   the observed scores in `EVAL.md`.
5. Add a unique `AIBENCH-CANARY` string to hidden files and list it in `leak_canaries`.
6. No network, deterministic fixtures, bounded runtimes, no real credentials or personal data.

Changing a released benchmark (prompt, fixtures, tests, weights) requires a version bump; results
from different versions are not comparable.

## Adding an adapter or check type

Adapters: `docs/adapters.md`. Check types: implement `fn(check, ctx) -> CheckResult` and reference it
as `type: package.module:function`, or add it to `aibench/core/checks/builtin.py` with tests.

## Code style

Typed Python ≥ 3.11, standard library first, small modules with one responsibility, structured logs,
no secrets in code or results. Framework changes need tests in `tests/`.
