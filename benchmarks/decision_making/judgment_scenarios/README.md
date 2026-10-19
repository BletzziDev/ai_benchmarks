# decision_making/judgment_scenarios

Chat-mode benchmark: 14 technical decision scenarios with binding policies, risk budgets and four
options with pre-registered partial credit. Measures decision quality, harmful choices and whether the
model correctly judges reversibility and authorization requirements.

```bash
benchmark run decision_making/judgment_scenarios --model anthropic/claude-sonnet-5-5 --attempts 3
benchmark selftest judgment_scenarios
python tests/verify_ground_truth.py   # structural checks of scores, rationales and fields
python tests/build_cases.py           # regenerate cases.yaml + ground_truth.yaml
python selftest/make_responses.py     # regenerate canned selftest responses
```

| Path | Role |
|---|---|
| `PROMPT.md` | exact instruction template; `{{input}}` = rendered scenario |
| `tests/build_cases.py` | scenarios, option scores, harmful flags, rationales (single source of truth) |
| `fixtures/cases.yaml`, `tests/ground_truth.yaml` | generated inputs / hidden labels |
| `tests/grader.py` | metrics |
| `REFERENCE_SOLUTION/`, `selftest/` | canned responses (reference, reckless, timid, acceptable, no JSON) |
