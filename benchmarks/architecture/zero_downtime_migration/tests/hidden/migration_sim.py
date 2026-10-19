# AIBENCH-CANARY: e2a6c4d9-zero-downtime-hidden — never shown to evaluated models.
"""Deterministic simulator for MIGRATION_PLAN.yaml (DSL v1, see PROMPT.md).

World model (identical to what the prompt states):
- Representations ("reps"): ``name`` (column name) and ``split`` (columns first_name + last_name).
- A rep is *fresh* when every row holds the correct value. Writes never stop (3k/s), so a rep that
  exists but is not *maintained* by every running app version (directly or via a trigger) becomes stale.
- A deploy is rolling: old and new version run together (mixed window), then only the new one.
- Rollback = re-deploying the previously deployed versions in reverse order (rolling, with mixed
  windows) on the current schema; it is possible from a state if every rollback deploy is violation-free.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

REPS = ("name", "split")
SPLIT_COLS = ("first_name", "last_name")
ACTIONS = {"add_column", "drop_column", "create_trigger", "drop_trigger", "deploy", "backfill", "set_not_null",
           "drop_not_null", "verify"}
MAX_BATCH = 50_000


class PlanError(ValueError):
    pass


@dataclass
class Version:
    label: str
    reads: str
    writes: tuple[str, ...]


@dataclass
class State:
    columns: dict = field(default_factory=lambda: {"name": {"not_null": True}})
    triggers: dict = field(default_factory=dict)  # name -> direction "name_to_split" | "split_to_name"
    fresh: dict = field(default_factory=lambda: {"name": True, "split": False})
    running: list = field(default_factory=lambda: [Version("v1", "name", ("name",))])
    history: list = field(default_factory=lambda: [Version("v1", "name", ("name",))])

    def rep_exists(self, rep: str) -> bool:
        return all(c in self.columns for c in (SPLIT_COLS if rep == "split" else ("name",)))


def _cols(rep):
    return SPLIT_COLS if rep == "split" else ("name",)


def parse_plan(data) -> tuple[list[dict], str | None]:
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list) or not data["steps"]:
        raise PlanError("plan must be a mapping with a non-empty 'steps' list")
    steps, ids = [], set()
    for i, st in enumerate(data["steps"]):
        if not isinstance(st, dict):
            raise PlanError(f"step {i} is not a mapping")
        sid, action = st.get("id"), st.get("action")
        if not isinstance(sid, str) or not sid or sid in ids:
            raise PlanError(f"step {i}: missing or duplicate id")
        ids.add(sid)
        if action not in ACTIONS:
            raise PlanError(f"step {sid}: unknown action {action!r}")
        if action in ("add_column", "drop_column", "set_not_null", "drop_not_null") and st.get("column") not in ("name", *SPLIT_COLS):
            raise PlanError(f"step {sid}: column must be one of name, first_name, last_name")
        if action == "deploy":
            if not isinstance(st.get("version"), str) or st.get("reads") not in REPS:
                raise PlanError(f"step {sid}: deploy needs version and reads in {REPS}")
            w = st.get("writes")
            if not isinstance(w, list) or not w or any(x not in REPS for x in w) or len(set(w)) != len(w):
                raise PlanError(f"step {sid}: writes must be a non-empty list from {REPS}")
        if action in ("create_trigger", "backfill") and st.get("direction" if action == "backfill" else "sync") not in ("name_to_split", "split_to_name"):
            raise PlanError(f"step {sid}: direction/sync must be name_to_split or split_to_name")
        if action in ("create_trigger", "drop_trigger") and not isinstance(st.get("name"), str):
            raise PlanError(f"step {sid}: trigger needs a name")
        if action == "set_not_null" and st.get("method") not in ("direct", "validated_check"):
            raise PlanError(f"step {sid}: method must be direct or validated_check")
        steps.append(st)
    ponr = data.get("point_of_no_return")
    if ponr is not None and ponr not in ids:
        raise PlanError(f"point_of_no_return {ponr!r} is not a step id")
    return steps, ponr


class Sim:
    def __init__(self):
        self.violations: list[str] = []
        self.downtime: list[str] = []
        self.data_loss: list[str] = []

    # ---------------------------------------------------------------- invariants
    def maintained(self, s: State, rep: str, running=None) -> bool:
        running = s.running if running is None else running
        for v in running:
            if rep in v.writes:
                continue
            other = "split" if rep == "name" else "name"
            if any(d == f"{other}_to_{rep}" for d in s.triggers.values()) and other in v.writes:
                continue
            return False
        return True

    def settle(self, s: State, where: str, running=None, record=True) -> list[str]:
        """Apply staleness for the given running set and check every running version."""
        running = s.running if running is None else running
        problems = []
        for rep in REPS:
            if s.rep_exists(rep) and not self.maintained(s, rep, running):
                s.fresh[rep] = False
        if not s.rep_exists("split"):
            s.fresh["split"] = False
        for v in running:
            if not s.rep_exists(v.reads):
                problems.append(f"{where}: {v.label} reads {v.reads} but its column(s) do not exist")
            elif not s.fresh[v.reads]:
                problems.append(f"{where}: {v.label} reads {v.reads}, which is stale/incomplete")
            for w in v.writes:
                if not s.rep_exists(w):
                    problems.append(f"{where}: {v.label} writes {w} but its column(s) do not exist")
            for col, meta in s.columns.items():
                if meta.get("not_null") and not meta.get("default_set") and not _writes_col(v, col, s):
                    problems.append(f"{where}: {v.label} inserts would fail: {col} is NOT NULL and not written")
        if record:
            self.violations.extend(problems)
        return problems

    # ---------------------------------------------------------------- steps
    def apply(self, s: State, st: dict) -> None:
        a, sid = st["action"], st["id"]
        if a == "verify":
            return
        if a == "add_column":
            col = st["column"]
            if col in s.columns:
                self.violations.append(f"{sid}: column {col} already exists")
                return
            nullable = st.get("nullable", True)
            has_default = st.get("default") is not None
            if not nullable and not has_default:
                self.violations.append(f"{sid}: ADD COLUMN {col} NOT NULL without default fails on a non-empty table")
                return
            s.columns[col] = {"not_null": not nullable, "default_set": has_default}
            s.fresh["split" if col in SPLIT_COLS else "name"] = False  # a new column holds no real data yet
            self.settle(s, sid)
        elif a == "drop_column":
            col = st["column"]
            if col not in s.columns:
                self.violations.append(f"{sid}: column {col} does not exist")
                return
            rep = "split" if col in SPLIT_COLS else "name"
            other = "name" if rep == "split" else "split"
            for v in s.running:
                if v.reads == rep or rep in v.writes:
                    self.violations.append(f"{sid}: running {v.label} still uses {rep}; dropping {col} breaks it")
            for tname, d in s.triggers.items():
                if rep in d.split("_to_"):
                    self.violations.append(f"{sid}: trigger {tname} depends on {col}")
            if s.rep_exists(rep) and s.fresh.get(rep) is not None and not s.fresh[other]:
                # rows whose only correct copy lives in the dropped column are lost
                self.data_loss.append(f"{sid}: dropping {col} while {other} is not fully backfilled/fresh loses data")
            del s.columns[col]
            s.fresh[rep] = False
            s.triggers = {k: d for k, d in s.triggers.items() if rep not in d.split("_to_")}
            self.settle(s, sid)
        elif a == "create_trigger":
            d = st["sync"]
            if not (s.rep_exists("name") and s.rep_exists("split")):
                self.violations.append(f"{sid}: trigger needs both name and split columns")
                return
            if st["name"] in s.triggers:
                self.violations.append(f"{sid}: trigger {st['name']} exists")
                return
            opposite = "split_to_name" if d == "name_to_split" else "name_to_split"
            if opposite in s.triggers.values():
                self.violations.append(f"{sid}: triggers in both directions recurse (lock/loop risk)")
            s.triggers[st["name"]] = d
            self.settle(s, sid)
        elif a == "drop_trigger":
            if st["name"] not in s.triggers:
                self.violations.append(f"{sid}: trigger {st['name']} does not exist")
                return
            del s.triggers[st["name"]]
            self.settle(s, sid)
        elif a == "backfill":
            d = st["direction"]
            src, dst = d.split("_to_")
            bs = st.get("batch_size")
            if not isinstance(bs, int) or bs < 1 or bs > MAX_BATCH:
                self.downtime.append(f"{sid}: backfill without batch_size <= {MAX_BATCH} locks rows for minutes")
            if not (s.rep_exists(src) and s.rep_exists(dst)):
                self.violations.append(f"{sid}: backfill needs both representations to exist")
                return
            if not s.fresh[src]:
                self.violations.append(f"{sid}: backfill source {src} is stale; it would copy wrong data")
                return
            if not self.maintained(s, dst):
                self.violations.append(f"{sid}: writes during the backfill are not propagated to {dst}; backfill is ineffective")
                return
            s.fresh[dst] = True
            self.settle(s, sid)
        elif a == "set_not_null":
            col = st["column"]
            if col not in s.columns:
                self.violations.append(f"{sid}: column {col} does not exist")
                return
            rep = "split" if col in SPLIT_COLS else "name"
            if not s.fresh[rep]:
                self.violations.append(f"{sid}: SET NOT NULL on {col} fails, rows still NULL/stale")
                return
            if st["method"] == "direct":
                self.downtime.append(f"{sid}: SET NOT NULL directly scans 40M rows under ACCESS EXCLUSIVE lock")
            s.columns[col]["not_null"] = True
            self.settle(s, sid)
        elif a == "drop_not_null":
            col = st["column"]
            if col not in s.columns:
                self.violations.append(f"{sid}: column {col} does not exist")
                return
            s.columns[col]["not_null"] = False  # metadata-only, instant
            self.settle(s, sid)
        elif a == "deploy":
            v = Version(st["version"], st["reads"], tuple(st["writes"]))
            if any(h.label == v.label for h in s.history):
                self.violations.append(f"{sid}: version label {v.label} reused")
            mixed = list(s.running) + [v]
            self.settle(s, f"{sid} (mixed window)", mixed)
            s.running = [v]
            s.history.append(v)
            self.settle(s, sid)

    # ---------------------------------------------------------------- rollback
    def rollback_safe(self, s: State) -> bool:
        probe = Sim()
        t = copy.deepcopy(s)
        for v in reversed(t.history[:-1]):
            mixed = list(t.running) + [v]
            if probe.settle(t, "rollback", mixed):
                return False
            t.running = [v]
            if probe.settle(t, "rollback"):
                return False
        return True


def _writes_col(v: Version, col: str, s: State) -> bool:
    rep = "split" if col in SPLIT_COLS else "name"
    if rep in v.writes:
        return True
    other = "name" if rep == "split" else "split"
    return f"{other}_to_{rep}" in s.triggers.values() and other in v.writes


def simulate(data) -> dict:
    out = {"plan_parsed": 0, "violations": [], "downtime": [], "data_loss": [], "final_state_ok": 0,
           "rollback_claim_valid": 0, "rollback_through_deploys": 0, "deploys": 0, "first_unsafe_step": None,
           "parse_error": None, "ponr": None}
    try:
        steps, ponr = parse_plan(data)
    except PlanError as e:
        out["parse_error"] = str(e)
        return out
    out["plan_parsed"] = 1
    out["ponr"] = ponr
    sim, s = Sim(), State()
    safe_after = []
    for st in steps:
        sim.apply(s, st)
        safe_after.append(sim.rollback_safe(s))
    ids = [st["id"] for st in steps]
    first_unsafe = next((i for i, ok in enumerate(safe_after) if not ok), None)
    out["first_unsafe_step"] = ids[first_unsafe] if first_unsafe is not None else None
    deploy_idx = [i for i, st in enumerate(steps) if st["action"] == "deploy"]
    out["deploys"] = len(deploy_idx)
    if ponr is not None:
        p = ids.index(ponr)
        # rollback must be possible after every step strictly before the point of no return
        out["rollback_claim_valid"] = 1 if all(safe_after[:p]) else 0
    last_deploy = deploy_idx[-1] if deploy_idx else -1
    out["rollback_through_deploys"] = 1 if (first_unsafe is None or first_unsafe > last_deploy) and deploy_idx else 0
    final_ok = ("name" not in s.columns and s.rep_exists("split") and s.fresh["split"] and len(s.running) == 1
                and s.running[0].reads == "split" and s.running[0].writes == ("split",) and not s.triggers)
    out["final_state_ok"] = 1 if final_ok else 0
    out["violations"], out["downtime"], out["data_loss"] = sim.violations, sim.downtime, sim.data_loss
    return out
