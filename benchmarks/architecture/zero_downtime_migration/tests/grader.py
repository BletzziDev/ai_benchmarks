"""Grader for architecture/zero_downtime_migration: runs the hidden simulator on MIGRATION_PLAN.yaml.

The plan is untrusted data: it is only parsed with yaml.safe_load (size-capped) and interpreted by the
simulator; nothing from the workspace is imported or executed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

from aibench.core.checks.base import CheckResult

MAX_PLAN_BYTES = 200_000


def _sim():
    path = Path(__file__).parent / "hidden" / "migration_sim.py"
    spec = importlib.util.spec_from_file_location("aibench_migration_sim", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve annotations through sys.modules
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(spec.name, None)
    return mod


def grade(ctx, check) -> CheckResult:
    res = CheckResult()
    m = res.metrics
    plan_path = ctx.final_workspace / "MIGRATION_PLAN.yaml"
    design_path = ctx.final_workspace / "DESIGN.md"
    design = design_path.read_text(encoding="utf-8", errors="replace") if design_path.is_file() else ""
    m["design_present"] = 1 if len(design.strip()) >= 800 else 0
    defaults = {"plan_present": 0, "plan_parsed": 0, "violations": None, "compat_score": 0.0, "downtime_violations": None, "no_downtime": 0,
                "data_loss": 0, "final_state_ok": 0, "rollback_claim_valid": 0, "rollback_through_deploys": 0,
                "rollback_score": 0.0, "deploys": 0, "within_deploy_budget": 0}
    m.update(defaults)
    if not plan_path.is_file():
        res.evidence.append("MIGRATION_PLAN.yaml not found")
        return res
    m["plan_present"] = 1
    raw = plan_path.read_bytes()[:MAX_PLAN_BYTES]
    try:
        data = yaml.safe_load(raw.decode("utf-8", errors="replace"))
    except yaml.YAMLError as e:
        res.evidence.append(f"YAML error: {e}")
        return res
    out = _sim().simulate(data)
    if not out["plan_parsed"]:
        res.evidence.append(f"plan rejected: {out['parse_error']}")
        return res
    n_viol = len(out["violations"])
    m.update({
        "plan_parsed": 1, "violations": n_viol, "compat_score": max(0.0, 1.0 - 0.25 * n_viol),
        "downtime_violations": len(out["downtime"]), "no_downtime": 0 if out["downtime"] else 1,
        "data_loss": len(out["data_loss"]),
        "final_state_ok": out["final_state_ok"], "rollback_claim_valid": out["rollback_claim_valid"],
        "rollback_through_deploys": out["rollback_through_deploys"],
        "rollback_score": 0.5 * out["rollback_claim_valid"] + 0.5 * out["rollback_through_deploys"],
        "deploys": out["deploys"], "within_deploy_budget": 1 if 1 <= out["deploys"] <= 3 else 0,
    })
    for kind in ("violations", "downtime", "data_loss"):
        for x in out[kind][:12]:
            res.evidence.append(f"{kind}: {x}")
    res.evidence.append(f"declared point_of_no_return={out['ponr']}; first step after which rollback is unsafe="
                        f"{out['first_unsafe_step']}")
    if not out["final_state_ok"]:
        res.evidence.append("final state does not meet ACC-731 (name dropped, split fresh, app reads/writes only split, no triggers)")
    res.details = out
    return res
