"""Command-line interface: ``benchmark <command>``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from aibench.core.config import Config, load_config


def _registry(cfg: Config):
    from aibench.core.registry import Registry

    reg = Registry.discover(cfg.benchmarks_dir, set(cfg.suite.categories))
    for issue in reg.load_errors:
        print(f"[{issue.level}] {issue.benchmark}: {issue.message}", file=sys.stderr)
    return reg


def _load_env_file(root: Path) -> None:
    """Load KEY=VALUE pairs from .env (does not override existing env)."""
    import os

    p = root / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        if v and k.strip() not in os.environ:
            os.environ[k.strip()] = v.strip().strip('"').strip("'")


def cmd_list(args, cfg: Config) -> int:
    reg = _registry(cfg)
    rows = [b for b in reg.all() if not args.category or b.spec.category == args.category]
    if args.json:
        print(json.dumps([{"id": b.id, "version": b.spec.version, "category": b.spec.category, "mode": b.spec.mode,
                           "difficulty": b.spec.difficulty, "name": b.spec.name} for b in rows], indent=2))
        return 0
    print(f"{'ID':52} {'VER':7} {'MODE':6} {'DIFF':7} NAME")
    for b in rows:
        print(f"{b.id:52} {b.spec.version:7} {b.spec.mode:6} {b.spec.difficulty:7} {b.spec.name}")
    print(f"\n{len(rows)} benchmark(s)")
    return 0


def cmd_show(args, cfg: Config) -> int:
    reg = _registry(cfg)
    b = reg.get(args.benchmark)
    print(json.dumps({"path": str(b.path), "content_hash": b.content_hash, **b.spec.model_dump(mode="json")}, indent=2))
    return 0


def cmd_validate(args, cfg: Config) -> int:
    from aibench.core.registry import validate_contract

    reg = _registry(cfg)
    n_err = len(reg.load_errors)
    targets = [reg.get(x) for x in args.benchmarks] if args.benchmarks else reg.all()
    for b in targets:
        for issue in validate_contract(b):
            print(f"[{issue.level}] {issue.benchmark}: {issue.message}")
            n_err += issue.level == "error"
    print(f"validated {len(targets)} benchmark(s): {n_err} error(s)")
    return 1 if n_err else 0


def _select(reg, cfg: Config, args) -> list:
    if getattr(args, "all", False):
        return reg.all()
    if getattr(args, "category", None):
        if args.category not in cfg.suite.categories:
            raise SystemExit(f"unknown category {args.category!r}")
        found = reg.by_category(args.category)
        if not found:
            raise SystemExit(f"no benchmarks in category {args.category!r}")
        return found
    return [reg.get(x) for x in args.benchmarks]


def _run(args, cfg: Config, benches: list) -> int:
    from aibench.core.runner import Runner

    runner = Runner(cfg, _registry(cfg), sandbox_backend=args.sandbox, judge_labels=args.judge,
                    allow_self_judge=args.allow_self_judge)
    store = runner.create_run(benches, args.model, attempts=args.attempts, tier=args.tier, run_id=args.run_id)
    print(f"run id: {store.run_id}\nresults: {store.dir}", file=sys.stderr)
    outcomes = runner.execute(store)
    _print_outcomes(outcomes)
    print(f"\nreport: {store.dir / 'report.md'}")
    return 0


def _print_outcomes(outcomes) -> None:
    print(f"\n{'BENCHMARK':52} {'ATT':4} {'STATE':12} {'SCORE':>7} {'PASS':6} CRITICAL")
    for o in outcomes:
        sc = "n/a" if o.score is None else f"{o.score:.1f}"
        print(f"{o.bench_id:52} {o.attempt:<4} {o.state:12} {sc:>7} {str(o.passed):6} {','.join(o.critical) or '-'}")


def cmd_run(args, cfg: Config) -> int:
    reg = _registry(cfg)
    return _run(args, cfg, [reg.get(x) for x in args.benchmarks])


def cmd_run_category(args, cfg: Config) -> int:
    reg = _registry(cfg)
    args.all = False
    return _run(args, cfg, _select(reg, cfg, args))


def cmd_run_all(args, cfg: Config) -> int:
    return _run(args, cfg, _registry(cfg).all())


def cmd_resume(args, cfg: Config) -> int:
    from aibench.core.artifacts import RunStore
    from aibench.core.runner import Runner

    store = RunStore.open(cfg.results_dir, args.run_id)
    m = store.manifest()
    runner = Runner(cfg, _registry(cfg), sandbox_backend=(m.get("sandbox") or {}).get("backend"),
                    judge_labels=m.get("judges") or None, allow_self_judge=bool(m.get("allow_self_judge")))
    _print_outcomes(runner.execute(store))
    return 0


def cmd_report(args, cfg: Config) -> int:
    from aibench.core.artifacts import RunStore
    from aibench.core.reporting import write_summary

    store = RunStore.open(cfg.results_dir, args.run_id)
    s = write_summary(store, cfg, _registry(cfg))
    if args.format == "json":
        print(json.dumps(s, indent=2))
    else:
        print((store.dir / "report.md").read_text())
    print(f"\nwritten: {store.dir / 'summary.json'}, {store.dir / 'report.md'}, {store.dir / 'report.html'}", file=sys.stderr)
    return 0


def _resolve_run(cfg: Config, ref: str):
    from aibench.core.artifacts import RunStore, list_runs

    try:
        return RunStore.open(cfg.results_dir, ref)
    except FileNotFoundError:
        runs = [r for r in list_runs(cfg.results_dir) if r["model"] == ref and r["state"] == "completed"]
        if not runs:
            raise SystemExit(f"{ref!r} is neither a run id nor a model label with a completed run")
        return RunStore.open(cfg.results_dir, sorted(runs, key=lambda r: r["created_at"])[-1]["run_id"])


def cmd_compare(args, cfg: Config) -> int:
    from aibench.core.reporting import compare_runs, comparison_markdown, html_report
    from aibench.core.util import write_json

    stores = [_resolve_run(cfg, r) for r in args.runs]
    if len(stores) < 2:
        raise SystemExit("compare needs at least two runs")
    c = compare_runs(stores, cfg, force=args.force)
    md = comparison_markdown(c)
    print(md)
    out = Path(args.output) if args.output else cfg.results_dir / "comparisons" / "_".join(s.run_id for s in stores)
    out.mkdir(parents=True, exist_ok=True)
    (out / "comparison.md").write_text(md)
    (out / "comparison.html").write_text(html_report(c["summaries"], c))
    write_json(out / "comparison.json", {k: v for k, v in c.items() if k != "summaries"})
    print(f"written: {out}", file=sys.stderr)
    return 0


def cmd_runs(args, cfg: Config) -> int:
    from aibench.core.artifacts import list_runs

    for r in list_runs(cfg.results_dir):
        print(f"{r['run_id']:48} {str(r['model']):36} {str(r['state']):12} {r['benchmarks']} benchmark(s)")
    return 0


def cmd_models(args, cfg: Config) -> int:
    import os

    for label, m in sorted(cfg.models.models.items()):
        key = "n/a" if not m.api_key_env else ("set" if os.environ.get(m.api_key_env) else f"missing ${m.api_key_env}")
        print(f"{label:36} {m.kind:9} {m.adapter:18} {str(m.model):34} key:{key}")
    return 0


def cmd_selftest(args, cfg: Config) -> int:
    from aibench.core.selftest import run_selftests

    reg = _registry(cfg)
    benches = reg.all() if args.all or not args.benchmarks else [reg.get(x) for x in args.benchmarks]
    if args.category:
        benches = [b for b in benches if b.spec.category == args.category]
    outs = run_selftests(cfg, reg, benches, backend=args.sandbox, only_case=args.case, echo=args.verbose)
    bad = 0
    print(f"{'BENCHMARK':50} {'CASE':28} {'SCORE':>7} {'PASSED':7} {'OK':4} PROBLEMS")
    for o in outs:
        sc = "n/a" if o.score is None else f"{o.score:.1f}"
        print(f"{o.benchmark:50} {o.case:28} {sc:>7} {str(o.passed):7} {'yes' if o.ok else 'NO':4} {'; '.join(o.problems)}")
        bad += not o.ok
    print(f"\n{len(outs) - bad}/{len(outs)} selftest case(s) behaved as declared")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps([o.__dict__ for o in outs], indent=2))
    return 1 if bad else 0


def cmd_grade(args, cfg: Config) -> int:
    """Record a human rubric grade and rescore the attempt."""
    from aibench.core.artifacts import RunStore
    from aibench.core.runner import score_from_disk
    from aibench.core.util import read_json, write_json

    store = RunStore.open(cfg.results_dir, args.run_id)
    reg = _registry(cfg)
    b = reg.get(args.benchmark)
    adir = store.attempt_dir(b.id, args.attempt)
    ev = read_json(adir / "evaluation.json")
    check_id, crit = args.criterion.split(".", 1) if "." in args.criterion else (None, args.criterion)
    rubric_checks = [c for c in b.spec.evaluation.checks if c.type == "rubric"]
    chk = next((c for c in rubric_checks if check_id in (None, c.id)), None)
    if chk is None:
        raise SystemExit("benchmark has no rubric check")
    crit_def = next((c for c in chk.params.get("criteria", []) if c["id"] == crit), None)
    if crit_def is None:
        raise SystemExit(f"unknown rubric criterion {crit!r}; choose from {[c['id'] for c in chk.params.get('criteria', [])]}")
    lo, hi = crit_def.get("min", 1), crit_def.get("max", 5)
    if not (lo <= args.level <= hi):
        raise SystemExit(f"level must be in [{lo}, {hi}]")
    hp = adir / "human_grades.json"
    grades = read_json(hp) if hp.exists() else {}
    grades[f"{chk.id}.{crit}"] = {"value": (args.level - lo) / (hi - lo), "level": args.level, "grader": args.grader,
                                  "evidence": args.evidence}
    write_json(hp, grades)
    sc = score_from_disk(b, adir)
    del ev
    print(f"recorded; new score {sc['score']} (status {sc['status']}, passed {sc['passed']})")
    return 0


def cmd_rescore(args, cfg: Config) -> int:
    from aibench.core.artifacts import RunStore
    from aibench.core.reporting import write_summary
    from aibench.core.runner import score_from_disk

    store = RunStore.open(cfg.results_dir, args.run_id)
    reg = _registry(cfg)
    for bm in store.manifest()["benchmarks"]:
        b = reg.get(bm["id"])
        for k in range(1, bm["attempts"] + 1):
            adir = store.attempt_dir(b.id, k)
            if (adir / "evaluation.json").exists():
                score_from_disk(b, adir)
    write_summary(store, cfg, reg)
    print(f"rescored {store.run_id}")
    return 0


def cmd_doctor(args, cfg: Config) -> int:
    from aibench.core.artifacts import tool_versions
    from aibench.core.sandbox import _netns_available, docker_available

    import os

    info: dict[str, Any] = tool_versions()
    info["running_as_root"] = os.geteuid() == 0
    info["network_namespace"] = _netns_available()
    info["docker_daemon"] = docker_available()
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401

        info["playwright"] = info.get("playwright") or "installed"
    except ImportError:
        info["playwright"] = None
    print(json.dumps(info, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="benchmark", description="AI coding benchmark suite")
    p.add_argument("--root", help="suite root (default: auto-detect)")
    p.add_argument("--models-file", help="alternative models.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("list", help="list benchmarks")
    s.add_argument("--category")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("show", help="show a benchmark definition")
    s.add_argument("benchmark")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("validate", help="validate benchmark contracts")
    s.add_argument("benchmarks", nargs="*")
    s.set_defaults(fn=cmd_validate)

    def run_opts(sp):
        sp.add_argument("--model", required=True, help="model label from configs/models.yaml")
        sp.add_argument("--attempts", type=int, help="attempts per benchmark (default: benchmark's repetition.attempts)")
        sp.add_argument("--tier", help="budget tier (e.g. 15m, 1h, 4h, 12h) for benchmarks that define tiers")
        sp.add_argument("--sandbox", choices=["local", "docker"])
        sp.add_argument("--judge", action="append", help="model label used as rubric judge (repeatable)")
        sp.add_argument("--allow-self-judge", action="store_true")
        sp.add_argument("--run-id")

    s = sub.add_parser("run", help="run specific benchmark(s)")
    s.add_argument("benchmarks", nargs="+")
    run_opts(s)
    s.set_defaults(fn=cmd_run)

    s = sub.add_parser("run-category", help="run all benchmarks in a category")
    s.add_argument("category")
    run_opts(s)
    s.set_defaults(fn=cmd_run_category)

    s = sub.add_parser("run-all", help="run the full suite")
    run_opts(s)
    s.set_defaults(fn=cmd_run_all)

    s = sub.add_parser("resume", help="resume an interrupted run")
    s.add_argument("run_id")
    s.set_defaults(fn=cmd_resume)

    s = sub.add_parser("report", help="(re)generate a run report")
    s.add_argument("--run-id", required=True)
    s.add_argument("--format", choices=["md", "json"], default="md")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("compare", help="compare runs (run ids or model labels -> latest completed run)")
    s.add_argument("runs", nargs="+")
    s.add_argument("--force", action="store_true", help="rank even if conditions differ")
    s.add_argument("--output")
    s.set_defaults(fn=cmd_compare)

    s = sub.add_parser("runs", help="list stored runs")
    s.set_defaults(fn=cmd_runs)

    s = sub.add_parser("models", help="list configured models/agents")
    s.set_defaults(fn=cmd_models)

    s = sub.add_parser("selftest", help="validate graders with canned solutions")
    s.add_argument("benchmarks", nargs="*")
    s.add_argument("--all", action="store_true")
    s.add_argument("--category")
    s.add_argument("--case")
    s.add_argument("--sandbox", choices=["local", "docker"])
    s.add_argument("--verbose", action="store_true")
    s.add_argument("--json-out")
    s.set_defaults(fn=cmd_selftest)

    s = sub.add_parser("grade", help="record a human rubric grade for an attempt")
    s.add_argument("--run-id", required=True)
    s.add_argument("--benchmark", required=True)
    s.add_argument("--attempt", type=int, default=1)
    s.add_argument("--criterion", required=True, help="rubric criterion id (optionally check_id.criterion)")
    s.add_argument("--level", type=int, required=True)
    s.add_argument("--grader", required=True)
    s.add_argument("--evidence", required=True)
    s.set_defaults(fn=cmd_grade)

    s = sub.add_parser("rescore", help="recompute scores from stored evaluations")
    s.add_argument("run_id")
    s.set_defaults(fn=cmd_rescore)

    s = sub.add_parser("doctor", help="check the execution environment")
    s.set_defaults(fn=cmd_doctor)
    return p


def _sigterm_as_interrupt(signum, frame):  # noqa: ARG001
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    import signal
    import threading

    if threading.current_thread() is threading.main_thread():
        # SIGTERM (e.g. a CI timeout) takes the same clean path as Ctrl-C: sandboxes are closed,
        # the attempt is marked "interrupted" and the run can be resumed.
        signal.signal(signal.SIGTERM, _sigterm_as_interrupt)
    args = build_parser().parse_args(argv)
    cfg = load_config(Path(args.root) if args.root else None, Path(args.models_file) if args.models_file else None)
    _load_env_file(cfg.root)
    try:
        return int(args.fn(args, cfg) or 0)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
