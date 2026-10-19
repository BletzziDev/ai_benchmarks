# hallucination/closed_world_sdk

Chat-mode benchmark: the full documentation of a fictional SDK (`quarry` 2.3) is in the prompt; 34
questions and code tasks test whether the model answers only from it, abstains correctly, notices
non-existent and removed APIs, and writes code without invented identifiers.

```bash
benchmark run hallucination/closed_world_sdk --model anthropic/claude-sonnet-5-5 --attempts 3
benchmark selftest closed_world_sdk
python tests/verify_ground_truth.py   # docs/surface/labels consistency + reference responses grade 1.0
python tests/build_cases.py           # regenerate cases.yaml + ground_truth.yaml
python selftest/make_responses.py     # regenerate canned selftest responses
```

| Path | Role |
|---|---|
| `PROMPT.md` | exact prompt: the complete quarry 2.3 documentation + JSON reply format; `{{input}}` = question |
| `fixtures/cases.yaml` | generated questions |
| `tests/ground_truth.yaml` | hidden labels (kind, expected answers, bait identifiers) |
| `tests/sdk_surface.py` | documented API surface + AST detection of invented identifiers |
| `tests/grader.py` | per-case classification and metrics |
| `tests/verify_ground_truth.py` | consistency checks |
| `REFERENCE_SOLUTION/`, `selftest/` | canned responses (reference, hallucinator, hedger, careless reader, no JSON) |
