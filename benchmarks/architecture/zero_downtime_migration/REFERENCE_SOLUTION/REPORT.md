Wrote `MIGRATION_PLAN.yaml` (11 steps, 2 releases: v2 dual-writes while reading `name`, v3 reads/writes
only the new columns with a temporary `split → name` trigger keeping rollback possible) and
`DESIGN.md` (alternatives, name-splitting rules, failure handling). `python tools/check_plan.py` → syntax OK.
Point of no return: dropping the sync trigger (s10), after which `name` is no longer maintained.

```json
{"plan_file": "MIGRATION_PLAN.yaml", "design_file": "DESIGN.md", "point_of_no_return": "s10_drop_sync_trigger", "plan_checked": true}
```
