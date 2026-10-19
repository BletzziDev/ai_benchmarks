#!/usr/bin/env python3
"""Syntax check for MIGRATION_PLAN.yaml (DSL v1). Checks structure only — NOT whether the plan is safe.

Usage: python tools/check_plan.py [MIGRATION_PLAN.yaml]
"""

import sys

import yaml

REPS = {"name", "split"}
COLUMNS = {"name", "first_name", "last_name"}
REQUIRED = {
    "add_column": {"column"}, "drop_column": {"column"}, "set_not_null": {"column", "method"},
    "drop_not_null": {"column"}, "create_trigger": {"name", "sync"}, "drop_trigger": {"name"},
    "deploy": {"version", "reads", "writes"}, "backfill": {"direction", "batch_size"}, "verify": {"check"},
}
OPTIONAL = {"add_column": {"nullable", "default"}}


def check(data) -> list[str]:
    errs = []
    if not isinstance(data, dict):
        return ["top level must be a mapping"]
    unknown_top = set(data) - {"steps", "point_of_no_return"}
    if unknown_top:
        errs.append(f"unknown top-level keys: {sorted(unknown_top)}")
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        return errs + ["'steps' must be a non-empty list"]
    ids = []
    for i, st in enumerate(steps):
        where = f"step #{i + 1}"
        if not isinstance(st, dict):
            errs.append(f"{where}: must be a mapping")
            continue
        sid, action = st.get("id"), st.get("action")
        if not isinstance(sid, str) or not sid:
            errs.append(f"{where}: 'id' must be a non-empty string")
        elif sid in ids:
            errs.append(f"{where}: duplicate id {sid!r}")
        ids.append(sid)
        if action not in REQUIRED:
            errs.append(f"{where}: unknown action {action!r}; expected one of {sorted(REQUIRED)}")
            continue
        missing = REQUIRED[action] - set(st)
        extra = set(st) - REQUIRED[action] - OPTIONAL.get(action, set()) - {"id", "action"}
        if missing:
            errs.append(f"{where} ({sid}): missing {sorted(missing)}")
        if extra:
            errs.append(f"{where} ({sid}): unexpected keys {sorted(extra)}")
        if "column" in st and st["column"] not in COLUMNS:
            errs.append(f"{where} ({sid}): column must be one of {sorted(COLUMNS)}")
        if action == "deploy":
            if st.get("reads") not in REPS:
                errs.append(f"{where} ({sid}): reads must be 'name' or 'split'")
            w = st.get("writes")
            if not isinstance(w, list) or not w or not set(w) <= REPS or len(set(w)) != len(w):
                errs.append(f"{where} ({sid}): writes must be a non-empty list of 'name'/'split'")
        if action == "backfill" and st.get("direction") not in ("name_to_split", "split_to_name"):
            errs.append(f"{where} ({sid}): direction must be name_to_split or split_to_name")
        if action == "backfill" and not isinstance(st.get("batch_size"), int):
            errs.append(f"{where} ({sid}): batch_size must be an integer")
        if action == "create_trigger" and st.get("sync") not in ("name_to_split", "split_to_name"):
            errs.append(f"{where} ({sid}): sync must be name_to_split or split_to_name")
        if action == "set_not_null" and st.get("method") not in ("direct", "validated_check"):
            errs.append(f"{where} ({sid}): method must be direct or validated_check")
    ponr = data.get("point_of_no_return")
    if ponr is None:
        errs.append("missing point_of_no_return")
    elif ponr not in ids:
        errs.append(f"point_of_no_return {ponr!r} is not a step id")
    return errs


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "MIGRATION_PLAN.yaml"
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        print(f"ERROR: cannot read {path}: {e}")
        return 2
    errs = check(data)
    for e in errs:
        print(f"ERROR: {e}")
    print("syntax OK" if not errs else f"{len(errs)} error(s)")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
