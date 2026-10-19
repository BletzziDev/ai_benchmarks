"""Check plug-in interface.

A check turns evidence (final workspace, transcript, trace) into metrics. Metrics are flat
``name -> value`` maps; values are numbers/bools or ``None`` (unavailable). Each check also returns
human-readable evidence so every score can be audited.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from aibench.core.config import Config
from aibench.core.sandbox import Sandbox, make_sandbox
from aibench.core.spec import CheckSpec, LoadedBenchmark
from aibench.core.util import copy_tree, safe_join


@dataclass
class CheckResult:
    metrics: dict[str, Any] = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"  # ok | error (grader failure, not a model failure) | skipped
    error: str | None = None


@dataclass
class GradingContext:
    """Everything a check may look at. Workspaces are copies; checks may freely modify their sandboxes."""

    benchmark: LoadedBenchmark
    config: Config
    final_workspace: Path  # snapshot of the agent's workspace (read-only by convention)
    original_workspace: Path | None  # pristine copy of the fixture workspace (+ overlays)
    final_text: str
    transcript: list[dict[str, Any]]
    trace_events: list[dict[str, Any]]
    case_results: dict[str, dict[str, Any]]  # chat mode: case_id -> {"replies": [...], "case": {...}}
    artifacts_dir: Path
    sandbox_backend: str
    judge: Any = None  # aibench.core.judge.JudgePanel | None
    evaluated_model: str | None = None
    episode: dict[str, Any] = field(default_factory=dict)
    _sandboxes: list[Sandbox] = field(default_factory=list)

    def new_sandbox(self, source: Path | None = None, overlays: dict[Path, str] | None = None) -> Sandbox:
        """Fresh sandbox populated from ``source`` (default: final workspace) plus overlays
        ``{host_path: workspace_relative_dst}``. Closed automatically after the check."""
        spec = self.benchmark.spec.environment.sandbox
        sb = make_sandbox(self.sandbox_backend, spec, self.config.suite.sandbox,
                          max_output_chars=self.config.suite.harness.max_logged_output_chars)
        try:
            src = self.final_workspace if source is None else source
            if src is not None and Path(src).exists():
                copy_tree(src, sb.root)
            for host, dst in (overlays or {}).items():
                target = safe_join(sb.root, dst)
                if Path(host).is_dir():
                    copy_tree(host, target)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(host, target)
            sb.start()
        except BaseException:
            sb.close()
            raise
        self._sandboxes.append(sb)
        return sb

    def close(self) -> None:
        for sb in self._sandboxes:
            sb.close()
        self._sandboxes.clear()


CheckFn = Callable[[CheckSpec, GradingContext], CheckResult]
