# bug_fixing/inventory_reservations

Hard, multi-cause bug-fixing benchmark (Python). The agent receives the `stockroom` repository,
an incident description and production logs, and must find and fix three interacting defects
(cache key normalisation, cache invalidation on expiry, confirmation of lapsed holds masked by a
clamp) with minimal, well-tested changes.

## Run it

```bash
benchmark run bug_fixing/inventory_reservations --model anthropic/claude-sonnet-5-5 --attempts 3
benchmark selftest inventory_reservations          # validate the grader (no model needed)
```

Requirements: Python ≥ 3.11 with `pytest` and `hypothesis` (`pip install -e '.[eval]'`). No network.

## Layout

| Path | Role |
|---|---|
| `PROMPT.md` | exact task prompt sent to the model |
| `EVAL.md` | evaluation specification, rubric, critical failures, limitations |
| `benchmark.yaml` | machine-readable configuration (limits, checks, weights, selftests) |
| `fixtures/workspace/` | the repository the agent works on (incl. `logs/incident-2291.log`) |
| `tests/hidden/` | hidden tests (never copied into the agent workspace) |
| `tests/public/` | benchmark-owned copy of the original public tests |
| `REFERENCE_SOLUTION/` | reference fix, regression tests and report (used by selftests) |
| `selftest/` | decoy solutions: symptom patch, false claim, reckless deletion |

## Reproducing an evaluation by hand

```bash
cp -r fixtures/workspace /tmp/ws && cp -r REFERENCE_SOLUTION/files/* /tmp/ws/
cp tests/hidden/test_hidden_inventory.py /tmp/ws/ && (cd /tmp/ws && python -m pytest -q)
```

Interpretation guidance and the expected selftest scores are in `EVAL.md`.
