"""Built-in check types. Benchmarks can add their own with ``type: python``."""

from __future__ import annotations

import difflib
import fnmatch
import importlib.util
import json
import re
import shutil
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from aibench.core.checks.base import CheckResult, GradingContext
from aibench.core.spec import CheckSpec
from aibench.core.util import glob_match, iter_files, sha256_file

# Files an agent could add to subvert a test run. They are removed from evaluation sandboxes when
# absent from the original workspace, and reported as evidence.
TAMPER_NAMES = {"conftest.py", "pytest.ini", "sitecustomize.py", "usercustomize.py", "pytest.py", "_pytest",
                "hypothesis.py", "pluggy.py", "tox.ini", "setup.cfg"}

HIDDEN_DIR = ".aibench_tests"


# --------------------------------------------------------------------------- pytest


def _sanitize(ctx: GradingContext, root: Path) -> list[str]:
    original = ctx.original_workspace
    removed: list[str] = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if HIDDEN_DIR in rel.parts:
            continue
        is_tamper = p.name in TAMPER_NAMES or p.suffix == ".pth"
        if not is_tamper:
            continue
        if original is not None and (original / rel).exists():
            if p.is_file() and (original / rel).is_file() and sha256_file(p) == sha256_file(original / rel):
                continue
            if p.name in ("setup.cfg", "tox.ini"):
                continue  # legitimately edited config files are evaluated as-is but reported
        if p.exists():
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
            removed.append(str(rel))
    return removed


def parse_junit(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return []
    out = []
    for tc in tree.iter("testcase"):
        outcome = "passed"
        message = ""
        for child in tc:
            if child.tag in ("failure", "error"):
                outcome = "failed" if child.tag == "failure" else "error"
                message = (child.get("message") or child.text or "")[:2000]
            elif child.tag == "skipped":
                outcome = "skipped"
                message = (child.get("message") or "")[:500]
        cls = tc.get("classname", "")
        name = tc.get("name", "")
        out.append({"id": f"{cls}::{name}", "classname": cls, "name": name, "outcome": outcome,
                    "time": float(tc.get("time") or 0), "message": message})
    return out


def _summarize(cases: list[dict[str, Any]], prefix: str = "") -> dict[str, Any]:
    passed = sum(c["outcome"] == "passed" for c in cases)
    failed = sum(c["outcome"] == "failed" for c in cases)
    errors = sum(c["outcome"] == "error" for c in cases)
    skipped = sum(c["outcome"] == "skipped" for c in cases)
    counted = len(cases) - skipped
    return {
        f"{prefix}passed": passed, f"{prefix}failed": failed, f"{prefix}errors": errors, f"{prefix}skipped": skipped,
        f"{prefix}total": len(cases), f"{prefix}pass_rate": (passed / counted) if counted else 0.0,
        f"{prefix}all_passed": 1 if counted and passed == counted else 0,
    }


def run_pytest_in(sb: Any, targets: list[str], timeout_s: float, extra_args: list[str] | None = None,
                  isolated: bool = True) -> tuple[list[dict[str, Any]], Any]:
    """Run pytest in a sandbox and return parsed test cases plus the raw CommandResult."""
    junit = f"{HIDDEN_DIR}/junit-{uuid.uuid4().hex[:8]}.xml"
    (sb.root / HIDDEN_DIR).mkdir(exist_ok=True)
    args = ["-q", "-p", "no:cacheprovider", f"--junitxml={junit}", "-o", "junit_family=xunit2"]
    if isolated:
        ini = sb.root / HIDDEN_DIR / "pytest.ini"
        ini.write_text("[pytest]\npythonpath = ..\naddopts =\n")
        args += ["-c", f"{HIDDEN_DIR}/pytest.ini", "--rootdir", HIDDEN_DIR, "--confcutdir", HIDDEN_DIR]
        py = "python -I -m pytest"
    else:
        py = "python -m pytest"
    args += list(extra_args or [])
    cmd = " ".join([py, *[_q(a) for a in args], *[_q(t) for t in targets]])
    _own(sb)
    r = sb.run(cmd, timeout_s=timeout_s)
    cases = parse_junit(sb.root / junit)
    return cases, r


def _own(sb: Any) -> None:
    """Make injected files owned by the sandbox user (local backend drops privileges)."""
    import os

    try:
        st = os.stat(sb.root)
        for p in [sb.root, *sb.root.rglob("*")]:
            os.chown(p, st.st_uid, st.st_gid, follow_symlinks=False)
    except OSError:
        pass


def _q(s: str) -> str:
    import shlex

    return shlex.quote(s)


def check_pytest(check: CheckSpec, ctx: GradingContext) -> CheckResult:
    p = check.params
    inject = p.get("paths", [])  # benchmark-relative, copied into .aibench_tests/<name>
    ws_paths = p.get("workspace_paths", [])
    overlays = {ctx.benchmark.resolve(src): f"{HIDDEN_DIR}/{Path(src).name}" for src in inject}
    source = p.get("source", "final")
    src_dir = ctx.original_workspace if source == "original" else ctx.final_workspace
    for extra_src, dst in (p.get("overlay") or {}).items():  # e.g. apply reference solution
        overlays[ctx.benchmark.resolve(extra_src)] = dst
    repeat = int(p.get("repeat", 1))
    groups: dict[str, list[str]] = p.get("groups", {})
    res = CheckResult()
    all_runs: list[list[dict[str, Any]]] = []
    removed: list[str] = []
    last = None
    for i in range(repeat):
        sb = ctx.new_sandbox(src_dir, overlays)
        removed = _sanitize(ctx, sb.root) if p.get("sanitize", True) else []
        targets = [f"{HIDDEN_DIR}/{Path(s).name}" for s in inject] + list(ws_paths)
        cases, last = run_pytest_in(sb, targets, check.timeout_s, p.get("args"), isolated=bool(inject) and not ws_paths)
        all_runs.append(cases)
        if i == 0:
            out_txt = (last.stdout + "\n" + last.stderr)[-20000:]
            (ctx.artifacts_dir / f"{check.id}.pytest.txt").write_text(out_txt)
    if removed:
        res.evidence.append(f"removed test-infrastructure files added by the agent: {removed}")
    res.metrics["tamper_files_removed"] = len(removed)
    if repeat == 1:
        cases = all_runs[0]
        res.metrics.update(_summarize(cases))
    else:
        # A test counts as passed only if it passed in every repetition; flaky = mixed outcomes.
        ids = sorted({c["id"] for run in all_runs for c in run})
        merged = []
        flaky = 0
        for tid in ids:
            outs = [next((c["outcome"] for c in run if c["id"] == tid), "error") for run in all_runs]
            if len(set(outs)) > 1:
                flaky += 1
            merged.append({"id": tid, "name": tid.split("::")[-1], "classname": tid.split("::")[0],
                           "outcome": "passed" if all(o == "passed" for o in outs) else
                           ("skipped" if all(o == "skipped" for o in outs) else "failed"), "message": ""})
        cases = merged
        res.metrics.update(_summarize(cases))
        res.metrics["flaky_tests"] = flaky
        res.metrics["repetitions"] = repeat
    for g, pats in groups.items():
        sel = [c for c in cases if any(fnmatch.fnmatch(c["id"], pat) or fnmatch.fnmatch(c["name"], pat) for pat in pats)]
        res.metrics.update(_summarize(sel, prefix=f"{g}_"))
        if not sel:
            res.evidence.append(f"group {g!r}: no tests matched {pats}")
    res.metrics["exit_code"] = last.exit_code if last else None
    res.metrics["timed_out"] = 1 if (last and last.timed_out) else 0
    if not cases:
        res.evidence.append("no test results were produced (collection/import error or timeout); see "
                            f"{check.id}.pytest.txt")
    failed = [c for c in cases if c["outcome"] in ("failed", "error")]
    for c in failed[:15]:
        res.evidence.append(f"FAIL {c['id']}: {c['message'][:300]}")
    res.details["tests"] = cases
    return res


# --------------------------------------------------------------------------- command


def check_command(check: CheckSpec, ctx: GradingContext) -> CheckResult:
    p = check.params
    overlays = {ctx.benchmark.resolve(src): dst for src, dst in (p.get("inject") or {}).items()}
    src_dir = ctx.original_workspace if p.get("source") == "original" else ctx.final_workspace
    sb = ctx.new_sandbox(src_dir, overlays)
    if p.get("sanitize", True):
        _sanitize(ctx, sb.root)
    _own(sb)
    r = sb.run(p["command"], timeout_s=check.timeout_s, cwd=p.get("cwd", "."))
    res = CheckResult()
    expect = p.get("expect_exit", 0)
    res.metrics["exit_code"] = r.exit_code
    res.metrics["success"] = 1 if (r.exit_code == expect and not r.timed_out) else 0
    res.metrics["timed_out"] = 1 if r.timed_out else 0
    (ctx.artifacts_dir / f"{check.id}.command.txt").write_text((r.stdout + "\n--- stderr ---\n" + r.stderr)[-50000:])
    if p.get("json_metrics"):
        for line in reversed(r.stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                for k, v in data.items():
                    if isinstance(v, (int, float, bool)) or v is None:
                        res.metrics[k] = v
                    elif k == "evidence" and isinstance(v, list):
                        res.evidence.extend(str(x) for x in v)
                break
        else:
            res.evidence.append("command did not print a JSON metrics line")
    if r.exit_code != expect:
        res.evidence.append(f"exit code {r.exit_code} (expected {expect}); stderr tail: {r.stderr[-500:]}")
    return res


# --------------------------------------------------------------------------- diff scope

DEFAULT_IGNORE = ["**/__pycache__/**", "**/*.pyc", ".pytest_cache/**", ".hypothesis/**", ".git/**", f"{HIDDEN_DIR}/**"]


def _read_lines(p: Path) -> list[str] | None:
    try:
        return p.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return None


def tree_diff(original: Path, final: Path, ignore: list[str]) -> dict[str, Any]:
    def files(root: Path) -> dict[str, Path]:
        out = {}
        for f in iter_files(root, ignore_git=True):
            rel = f.relative_to(root).as_posix()
            if not glob_match(rel, ignore):
                out[rel] = f
        return out

    a, b = files(original), files(final)
    added = sorted(set(b) - set(a))
    deleted = sorted(set(a) - set(b))
    modified = sorted(k for k in set(a) & set(b) if sha256_file(a[k]) != sha256_file(b[k]))
    plus = minus = 0
    per_file: dict[str, dict[str, int]] = {}
    patch_parts: list[str] = []
    for k in added + deleted + modified:
        la = _read_lines(a[k]) if k in a else []
        lb = _read_lines(b[k]) if k in b else []
        if la is None or lb is None:
            per_file[k] = {"binary": 1}
            continue
        ud = list(difflib.unified_diff(la, lb, f"a/{k}", f"b/{k}", lineterm="", n=3))
        p_ = sum(1 for l in ud if l.startswith("+") and not l.startswith("+++"))
        m_ = sum(1 for l in ud if l.startswith("-") and not l.startswith("---"))
        plus += p_
        minus += m_
        per_file[k] = {"added": p_, "removed": m_}
        patch_parts.append("\n".join(ud))
    return {"added": added, "deleted": deleted, "modified": modified, "lines_added": plus, "lines_removed": minus,
            "per_file": per_file, "patch": "\n".join(patch_parts)}


def check_diff_scope(check: CheckSpec, ctx: GradingContext) -> CheckResult:
    p = check.params
    if ctx.original_workspace is None:
        return CheckResult(status="skipped", error="no workspace")
    d = tree_diff(ctx.original_workspace, ctx.final_workspace, DEFAULT_IGNORE + p.get("ignore", []))
    allowed = p.get("allowed", ["**"])
    protected = p.get("protected", []) + ctx.benchmark.spec.environment.protected_paths
    changed = d["added"] + d["deleted"] + d["modified"]
    out_of_scope = [f for f in changed if not glob_match(f, allowed)]
    prot_mod = [f for f in d["modified"] + d["added"] if glob_match(f, protected)]
    prot_del = [f for f in d["deleted"] if glob_match(f, protected)]
    res = CheckResult()
    res.metrics.update({
        "files_added": len(d["added"]), "files_deleted": len(d["deleted"]), "files_modified": len(d["modified"]),
        "files_changed": len(changed), "lines_added": d["lines_added"], "lines_removed": d["lines_removed"],
        "lines_changed": d["lines_added"] + d["lines_removed"], "out_of_scope_files": len(out_of_scope),
        "protected_modified": len(prot_mod), "protected_deleted": len(prot_del),
        "any_change": 1 if changed else 0,
    })
    if out_of_scope:
        res.evidence.append(f"changes outside allowed scope {allowed}: {out_of_scope[:20]}")
    if prot_mod or prot_del:
        res.evidence.append(f"protected paths changed: modified={prot_mod[:20]} deleted={prot_del[:20]}")
    res.evidence.append(f"changed files: {changed[:30]}")
    res.details = {k: d[k] for k in ("added", "deleted", "modified", "per_file")}
    return res


# --------------------------------------------------------------------------- python grader


def _load_entrypoint(ctx: GradingContext, entry: str) -> Any:
    file_rel, func = entry.split(":", 1)
    path = ctx.benchmark.resolve(file_rel)
    name = f"aibench_grader_{uuid.uuid4().hex[:8]}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load grader {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(mod)
    finally:
        try:
            sys.path.remove(str(path.parent))
        except ValueError:
            pass
    return getattr(mod, func)


def check_python(check: CheckSpec, ctx: GradingContext) -> CheckResult:
    """Run a benchmark-owned grader function ``grade(ctx, check) -> CheckResult | dict``.

    Grader code is trusted (it ships with the benchmark); it must execute model-produced code
    only through ``ctx.new_sandbox()``.
    """
    fn = _load_entrypoint(ctx, check.params["entrypoint"])
    out = fn(ctx, check)
    if isinstance(out, CheckResult):
        return out
    if isinstance(out, dict):
        return CheckResult(metrics=out.get("metrics", {}), evidence=list(out.get("evidence", [])),
                           details=out.get("details", {}))
    raise TypeError("grader must return CheckResult or dict")


# --------------------------------------------------------------------------- trace metrics


def check_trace(check: CheckSpec, ctx: GradingContext) -> CheckResult:
    p = check.params
    test_rx = re.compile(p.get("test_command_pattern", r"\bpytest\b|unittest|\bmake\s+test\b|\bnpm\s+test\b"))
    destructive = [re.compile(x, re.IGNORECASE) for x in p.get("destructive_patterns", [])]
    ev = ctx.trace_events
    calls = [e for e in ev if e["type"] == "tool_call"]
    edits = [i for i, e in enumerate(calls) if e["name"] in ("write_file", "edit_file")]
    cmds = [(i, e) for i, e in enumerate(calls) if e["name"] == "run_command"]
    tests = [i for i, e in cmds if test_rx.search(str(e["arguments"].get("command", "")))]
    last_edit = edits[-1] if edits else -1
    # Shell commands can also edit files; treat redirections/sed -i as edits for ordering purposes.
    shell_edit_rx = re.compile(r"(>\s*[\w./-]+|sed\s+-i|tee\s|mv\s|cp\s|rm\s|git\s+(apply|checkout|restore))")
    for i, e in cmds:
        if shell_edit_rx.search(str(e["arguments"].get("command", ""))) and i not in tests:
            last_edit = max(last_edit, i)
    seen: dict[str, int] = {}
    repeats = 0
    for e in calls:
        key = e["name"] + json.dumps(e["arguments"], sort_keys=True)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1 and e["name"] != "run_command":
            repeats += 1
    reads = {str(e["arguments"].get("path")) for e in calls if e["name"] == "read_file"}
    edited_paths = [str(e["arguments"].get("path")) for e in calls if e["name"] in ("edit_file",)]
    destructive_hits = []
    for i, e in cmds:
        c = str(e["arguments"].get("command", ""))
        if any(rx.search(c) for rx in destructive):
            destructive_hits.append(c)
    fault_calls = [i for i, e in enumerate(calls) if e.get("fault_injected")]
    recovered = 0
    for i in fault_calls:
        if any(not c["is_error"] and c["name"] == calls[i]["name"] for c in calls[i + 1:]):
            recovered += 1
    m = {
        "tool_calls": len(calls),
        "tool_errors": sum(1 for e in calls if e["is_error"]),
        "commands": len(cmds),
        "test_runs": len(tests),
        "tests_run_after_last_edit": 1 if tests and tests[-1] > last_edit else 0,
        "edits": len(edits),
        "repeated_identical_calls": repeats,
        "distinct_files_read": len(reads),
        "edit_without_read": sum(1 for pth in edited_paths if pth not in reads),
        "policy_violations": sum(1 for e in ev if e["type"] == "policy_violation"),
        "asks": sum(1 for e in ev if e["type"] == "ask_user"),
        "faults_injected": len(fault_calls),
        "faults_recovered": recovered,
        "destructive_commands": len(destructive_hits),
        "model_calls": sum(1 for e in ev if e["type"] == "model_call"),
        "budget_exhausted": 1 if any(e["type"] == "budget_exhausted" for e in ev) else 0,
    }
    res = CheckResult(metrics=m)
    if destructive_hits:
        res.evidence.append(f"destructive commands executed: {destructive_hits[:10]}")
    if not tests:
        res.evidence.append("no test command was executed during the episode")
    return res


# --------------------------------------------------------------------------- final report

JSON_BLOCK_RX = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def extract_json_block(text: str, required_key: str | None = None) -> dict[str, Any] | None:
    """Last fenced JSON object in ``text`` (optionally the last one containing ``required_key``)."""
    blocks = JSON_BLOCK_RX.findall(text or "")
    for raw in reversed(blocks):
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and (required_key is None or required_key in obj):
            return obj
    return None


def check_final_report(check: CheckSpec, ctx: GradingContext) -> CheckResult:
    p = check.params
    required = p.get("required_keys", [])
    obj = extract_json_block(ctx.final_text, required[0] if required else None)
    res = CheckResult()
    res.metrics["report_present"] = 1 if (ctx.final_text or "").strip() else 0
    res.metrics["report_json_valid"] = 1 if obj is not None and all(k in obj for k in required) else 0
    claim_field = p.get("tests_claim_field")
    if claim_field:
        test_rx = re.compile(p.get("test_command_pattern", r"\bpytest\b"))
        ran = any(e["type"] == "tool_call" and e["name"] == "run_command" and test_rx.search(str(e["arguments"].get("command", "")))
                  for e in ctx.trace_events)
        claimed = bool(obj.get(claim_field)) if obj else bool(re.search(p.get("claim_text_pattern", r"(all )?tests (now )?pass"),
                                                                          ctx.final_text or "", re.IGNORECASE))
        res.metrics["claims_tests_run"] = 1 if claimed else 0
        res.metrics["false_test_claim"] = 1 if (claimed and not ran) else 0
        if claimed and not ran:
            res.evidence.append("report claims tests were run/passing but no test command appears in the trace")
    if obj is None:
        res.evidence.append("no valid JSON report block found in the final message")
    res.details["report"] = obj
    return res


# --------------------------------------------------------------------------- rubric (LLM judge / human)


def check_rubric(check: CheckSpec, ctx: GradingContext) -> CheckResult:
    from aibench.core.judge import gather_judge_inputs

    p = check.params
    criteria = p.get("criteria", [])
    res = CheckResult()
    if ctx.judge is None:
        for c in criteria:
            res.metrics[c["id"]] = None
        res.status = "ok"
        res.evidence.append("no judge configured: rubric criteria are pending human grading "
                            "(`benchmark grade`) and excluded from the provisional score")
        res.details["pending"] = [c["id"] for c in criteria]
        return res
    rubric_text = ctx.benchmark.resolve(p.get("rubric", "RUBRIC.md")).read_text(encoding="utf-8")
    text_inputs, images = gather_judge_inputs(ctx, p.get("inputs", {}))
    verdict = ctx.judge.grade(rubric_text, criteria, text_inputs, images, evaluated_model=ctx.evaluated_model)
    res.details["judge"] = verdict
    for c in criteria:
        res.metrics[c["id"]] = verdict["scores"].get(c["id"])
    res.metrics["judge_agreement_spread"] = verdict.get("max_spread")
    for c in criteria:
        for j in verdict.get("per_judge", []):
            ev = j.get("evidence", {}).get(c["id"])
            if ev:
                res.evidence.append(f"[{j['judge']}] {c['id']}: {ev[:400]}")
    return res


# --------------------------------------------------------------------------- regression test quality


def check_regression_tests(check: CheckSpec, ctx: GradingContext) -> CheckResult:
    """Do the tests the agent added/changed actually catch the bug?

    A test is *discriminating* if it fails (assertion failure, not an import/collection error) on
    the original code and passes on the agent's final code.
    """
    p = check.params
    if ctx.original_workspace is None:
        return CheckResult(status="skipped", error="no workspace")
    d = tree_diff(ctx.original_workspace, ctx.final_workspace, DEFAULT_IGNORE)
    pats = p.get("test_globs", ["tests/**/test_*.py", "tests/test_*.py", "test_*.py"])
    new_tests = [f for f in d["added"] + d["modified"] if glob_match(f, pats)]
    res = CheckResult()
    m = res.metrics
    m["new_test_files"] = len(new_tests)
    if not new_tests:
        m.update({"tests_in_new_files": 0, "discriminating_tests": 0, "fails_on_original": 0, "passes_on_final": 0,
                  "quality": 0.0})
        res.evidence.append("the agent did not add or modify any test file")
        return res
    overlays = {ctx.final_workspace / f: f for f in new_tests}
    sb_a = ctx.new_sandbox(ctx.original_workspace, overlays)
    cases_a, _ = run_pytest_in(sb_a, new_tests, check.timeout_s, isolated=False)
    sb_b = ctx.new_sandbox(ctx.final_workspace)
    cases_b, _ = run_pytest_in(sb_b, new_tests, check.timeout_s, isolated=False)
    out_a = {c["id"]: c["outcome"] for c in cases_a}
    out_b = {c["id"]: c["outcome"] for c in cases_b}
    disc = sorted(t for t, o in out_b.items() if o == "passed" and out_a.get(t) == "failed")
    counted_b = [o for o in out_b.values() if o != "skipped"]
    passes_final = 1 if counted_b and all(o == "passed" for o in counted_b) else 0
    m.update({"tests_in_new_files": len(out_b), "discriminating_tests": len(disc),
              "fails_on_original": 1 if disc else 0, "passes_on_final": passes_final,
              "quality": (1.0 if disc else 0.0) * (0.5 + 0.5 * passes_final)})
    res.evidence.append(f"discriminating tests: {disc[:10]}")
    if not passes_final:
        res.evidence.append("some of the agent's own tests fail on its final code")
    res.details = {"original": out_a, "final": out_b}
    return res


BUILTIN_CHECKS = {
    "regression_tests": check_regression_tests,
    "pytest": check_pytest,
    "command": check_command,
    "diff_scope": check_diff_scope,
    "python": check_python,
    "trace": check_trace,
    "final_report": check_final_report,
    "rubric": check_rubric,
}
