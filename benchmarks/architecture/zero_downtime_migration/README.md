# architecture/zero_downtime_migration

Hard architecture benchmark. The agent writes `MIGRATION_PLAN.yaml` (a small DSL) and `DESIGN.md` for
splitting `users.name` into `first_name`/`last_name` under rolling deploys, continuous writes, a
no-downtime SLO, a 3-release budget and a rollback policy. A hidden simulator executes the plan; a
rubric grades the design document.

```bash
benchmark run architecture/zero_downtime_migration --model <label> --judge <judge-label>
benchmark selftest zero_downtime_migration
```

Requires Python ≥ 3.11 and PyYAML. No network.

| Path | Role |
|---|---|
| `PROMPT.md` | exact prompt incl. the DSL and the world rules |
| `EVAL.md` | scoring, critical failures, observed selftests, limitations |
| `RUBRIC.md` | rubric for DESIGN.md |
| `benchmark.yaml` | configuration |
| `fixtures/workspace/` | context docs, schema, v1 code, syntax checker |
| `tests/grader.py` | python check: runs the simulator |
| `tests/hidden/migration_sim.py` | the simulator (hidden) |
| `REFERENCE_SOLUTION/` | reference plan, design doc, report |
| `selftest/` | alternative valid plan and dangerous/invalid plans |

Try a plan by hand:
`python -c "import sys,yaml; sys.path.insert(0,'tests/hidden'); from migration_sim import simulate; print(simulate(yaml.safe_load(open(sys.argv[1]))))" REFERENCE_SOLUTION/files/MIGRATION_PLAN.yaml`
