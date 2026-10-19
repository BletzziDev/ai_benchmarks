# sycophancy/code_review_pressure

Chat-mode benchmark (44 scripted conversations) measuring whether a model keeps correct code-review
verdicts under authority pressure and bogus evidence, updates on valid evidence, corrects false
premises without "correcting" true ones, and declines insecure insistence.

```bash
benchmark run sycophancy/code_review_pressure --model anthropic/claude-sonnet-5-5 --attempts 3
benchmark selftest code_review_pressure
python tests/verify_ground_truth.py     # re-verify labels by executing the code items
python tests/build_cases.py             # regenerate fixtures/cases.yaml and tests/ground_truth.yaml
python selftest/make_responses.py       # regenerate canned selftest responses
```

| Path | Role |
|---|---|
| `PROMPT.md` | exact instruction template; `{{input}}` is replaced by each case's first message |
| `fixtures/items/` | code items (`a*` correct, `b*` buggy) |
| `fixtures/cases.yaml` | generated model inputs (first message + fixed follow-ups) |
| `tests/ground_truth.yaml` | hidden labels (generated) |
| `tests/grader.py` | metric computation |
| `tests/verify_ground_truth.py` | executable verification of the labels |
| `REFERENCE_SOLUTION/`, `selftest/` | canned response sets used to validate the grader |

See `EVAL.md` for the design, metrics, observed selftest scores and limitations.
