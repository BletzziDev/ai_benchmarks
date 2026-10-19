"""Benchmark discovery and contract validation.

A benchmark is any directory under ``benchmarks/`` that contains a ``benchmark.yaml``. Adding a
benchmark never requires touching the core: discovery is filesystem-based and check types are
resolved through :mod:`aibench.core.checks`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from aibench.core.spec import BenchmarkSpec, LoadedBenchmark
from aibench.core.util import combined_hash, iter_files, load_yaml, sha256_file

REQUIRED_FILES = ["PROMPT.md", "EVAL.md", "README.md", "benchmark.yaml"]
REQUIRED_DIRS = ["tests", "fixtures"]


class BenchmarkError(Exception):
    pass


@dataclass
class ValidationIssue:
    benchmark: str
    level: str  # "error" | "warning"
    message: str


@dataclass
class Registry:
    root: Path
    benchmarks: dict[str, LoadedBenchmark] = field(default_factory=dict)
    load_errors: list[ValidationIssue] = field(default_factory=list)

    @classmethod
    def discover(cls, benchmarks_dir: Path, known_categories: set[str] | None = None) -> "Registry":
        reg = cls(root=Path(benchmarks_dir))
        for yml in sorted(Path(benchmarks_dir).rglob("benchmark.yaml")):
            bdir = yml.parent
            # benchmark.yaml files nested inside fixtures are data, not benchmarks
            if any(part in {"fixtures", "tests", "REFERENCE_SOLUTION"} for part in bdir.relative_to(benchmarks_dir).parts):
                continue
            try:
                lb = load_benchmark(bdir)
            except (BenchmarkError, ValidationError) as e:
                reg.load_errors.append(ValidationIssue(str(bdir.relative_to(benchmarks_dir)), "error", str(e)))
                continue
            if known_categories is not None and lb.spec.category not in known_categories:
                reg.load_errors.append(
                    ValidationIssue(lb.id, "error", f"unknown category {lb.spec.category!r} (declare it in configs/benchmark.yaml)")
                )
                continue
            if lb.id in reg.benchmarks:
                reg.load_errors.append(ValidationIssue(lb.id, "error", f"duplicate benchmark id (also at {reg.benchmarks[lb.id].path})"))
                continue
            reg.benchmarks[lb.id] = lb
        return reg

    def get(self, ref: str) -> LoadedBenchmark:
        """Resolve a full id (``category/name``) or an unambiguous short name."""
        if ref in self.benchmarks:
            return self.benchmarks[ref]
        matches = [b for i, b in self.benchmarks.items() if i.split("/", 1)[1] == ref]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise BenchmarkError(f"ambiguous benchmark name {ref!r}: {[m.id for m in matches]}")
        raise BenchmarkError(f"unknown benchmark {ref!r}. Run `benchmark list`.")

    def by_category(self, category: str) -> list[LoadedBenchmark]:
        return [b for b in self.benchmarks.values() if b.spec.category == category]

    def all(self) -> list[LoadedBenchmark]:
        return [self.benchmarks[k] for k in sorted(self.benchmarks)]


def load_benchmark(bdir: Path) -> LoadedBenchmark:
    bdir = Path(bdir).resolve()
    raw = load_yaml(bdir / "benchmark.yaml")
    if not isinstance(raw, dict):
        raise BenchmarkError(f"{bdir}/benchmark.yaml is not a mapping")
    spec = BenchmarkSpec.model_validate(raw)
    hashes = {str(p.relative_to(bdir)): sha256_file(p) for p in iter_files(bdir)}
    return LoadedBenchmark(spec=spec, path=bdir, content_hash=combined_hash(hashes), file_hashes=hashes)


def validate_contract(lb: LoadedBenchmark) -> list[ValidationIssue]:
    """Checks the per-benchmark file contract and common methodological mistakes."""
    issues: list[ValidationIssue] = []
    s = lb.spec

    def err(msg: str) -> None:
        issues.append(ValidationIssue(lb.id, "error", msg))

    def warn(msg: str) -> None:
        issues.append(ValidationIssue(lb.id, "warning", msg))

    for f in REQUIRED_FILES:
        p = lb.path / f
        if not p.is_file():
            err(f"missing required file {f}")
        elif p.stat().st_size < 200 and f != "benchmark.yaml":
            err(f"{f} is too short to be a real specification ({p.stat().st_size} bytes)")
    for d in REQUIRED_DIRS:
        if not (lb.path / d).is_dir():
            err(f"missing required directory {d}/")

    if s.prompt != "PROMPT.md" and not (lb.path / s.prompt).is_file():
        err(f"prompt file {s.prompt} not found")
    if s.environment.workspace and not (lb.path / s.environment.workspace).is_dir():
        err(f"workspace {s.environment.workspace} not found")
    for src in s.environment.overlays:
        if not (lb.path / src).exists():
            err(f"overlay source {src} not found")
        if "hidden" in Path(src).parts:
            err(f"overlay {src} would copy hidden tests into the model-visible workspace")
    if s.environment.user_simulator and not (lb.path / s.environment.user_simulator).is_file():
        err(f"user simulator {s.environment.user_simulator} not found")
    if s.cases and not (lb.path / s.cases.file).is_file():
        err(f"cases file {s.cases.file} not found")
    if s.interruptions and not (lb.path / s.interruptions.resume_prompt).is_file():
        err(f"resume prompt {s.interruptions.resume_prompt} not found")

    # Hidden tests must never be inside the model-visible workspace.
    if s.environment.workspace:
        ws = lb.path / s.environment.workspace
        for p in ws.rglob("*"):
            if "hidden" in p.relative_to(ws).parts:
                err(f"workspace contains a 'hidden' path: {p.relative_to(lb.path)}")
                break

    # Leak canaries must not appear in anything the model sees.
    visible: list[Path] = [lb.path / s.prompt]
    if s.environment.workspace:
        visible += list(iter_files(lb.path / s.environment.workspace))
    for src in s.environment.overlays:
        sp = lb.path / src
        visible += list(iter_files(sp)) if sp.is_dir() else [sp]
    if s.cases:
        visible.append(lb.path / s.cases.file)
    for canary in s.leak_canaries:
        for p in visible:
            try:
                if canary in p.read_text(encoding="utf-8", errors="ignore"):
                    err(f"leak canary {canary!r} found in model-visible file {p.relative_to(lb.path)}")
            except OSError:
                pass

    # Weights / scoring sanity
    if not s.scoring.criteria:
        err("no scoring criteria")
    if len({c.weight for c in s.scoring.criteria}) == 1 and len(s.scoring.criteria) > 3:
        warn("all criteria share the same weight; confirm this is intentional")
    if not s.selftest:
        warn("no selftest cases: the grader's ability to discriminate is unverified")
    else:
        names = {t.name for t in s.selftest}
        if not any(t.expect.passed is True for t in s.selftest):
            warn("no selftest expects a passing solution")
        if not any(t.expect.passed is False for t in s.selftest):
            warn("no selftest expects a failing solution")
        if "noop" not in names and s.mode == "agent":
            warn("no 'noop' selftest: the untouched workspace is not shown to fail")
        for t in s.selftest:
            if t.solution.path and not (lb.path / t.solution.path).exists():
                err(f"selftest {t.name}: solution path {t.solution.path} not found")
    if s.mode == "agent" and not (lb.path / "tests").exists():
        err("agent benchmarks must ship tests/")
    return issues
