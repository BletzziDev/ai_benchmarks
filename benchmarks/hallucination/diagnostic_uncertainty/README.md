# hallucination/diagnostic_uncertainty

Chat-mode benchmark: 12 incident scenarios with numbered evidence and closed hypothesis lists. Measures
correct diagnosis, correct abstention with next steps, citation of real evidence and resistance to an
engineer's unsupported claims.

```bash
benchmark run hallucination/diagnostic_uncertainty --model anthropic/claude-sonnet-5-5 --attempts 3
benchmark selftest diagnostic_uncertainty
python tests/verify_ground_truth.py   # structural label checks
python tests/build_cases.py           # regenerate cases.yaml + ground_truth.yaml from the scenarios
python selftest/make_responses.py     # regenerate canned selftest responses
```

| Path | Role |
|---|---|
| `PROMPT.md` | exact instruction template; `{{input}}` = rendered scenario |
| `tests/build_cases.py` | scenarios, labels and rationales (single source of truth) |
| `fixtures/cases.yaml`, `tests/ground_truth.yaml` | generated inputs / hidden labels |
| `tests/grader.py` | metrics |
| `REFERENCE_SOLUTION/`, `selftest/` | canned responses (reference, overconfident, hedger, fabricator, no JSON) |
