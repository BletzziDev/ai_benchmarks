# tool_use/flaky_build_recovery

Medium tool-use benchmark: a red Python build (stale generated module) with two deterministic tool
faults injected by the harness — a transient `run_command` failure on the first pytest call and a
silently truncated `read_file` of `CONTRIBUTING.md`. Measures retry behaviour, noticing incomplete
tool output, following the documented procedure (regenerate, don't hand-edit or delete tests),
verification and honest reporting of tool problems.

## Run

```bash
benchmark run tool_use/flaky_build_recovery --model anthropic/claude-sonnet-5-5 --attempts 3
benchmark selftest flaky_build_recovery
```

Requires `pytest` and `hypothesis` (`pip install -e '.[eval]'`). No network.

## Layout

| Path | Role |
|---|---|
| `PROMPT.md` | exact task prompt |
| `EVAL.md` | evaluation spec and observed selftests |
| `fixtures/workspace/` | the `fxrates` repository at the failing commit |
| `tests/hidden/` | hidden checks (+ `_gen_ref.py`, a pristine copy of the generator) |
| `tests/public/` | benchmark copy of the project tests (`test_tables_fresh.py` locates the repo root by walking up, so it works when injected) |
| `tests/grader.py` | fault-handling / process grader |
| `REFERENCE_SOLUTION/` | scripted reference process and the regenerated `_tables.py` |
| `selftest/` | decoys: give up, delete test, hand patch |

The faults are declared in `benchmark.yaml` under `environment.faults` and are applied by the
harness's tool executor, so they also apply to scripted selftests.
