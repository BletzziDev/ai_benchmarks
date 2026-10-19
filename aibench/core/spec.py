"""Typed, validated schemas for benchmark definitions (benchmark.yaml) and suite configs.

Every benchmark declares *before execution* how it runs, how it is evaluated and how it is
scored. The runner never infers these from the model's behaviour.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ID_RE = re.compile(r"^[a-z0-9_]+/[a-z0-9_]+$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- execution


class LimitsSpec(StrictModel):
    """Hard limits for one attempt. ``None`` means "no limit from this layer"."""

    wall_clock_s: float | None = 1800
    max_turns: int | None = 60
    max_tool_calls: int | None = 200
    max_total_tokens: int | None = None
    max_output_tokens_per_turn: int = 16000
    command_timeout_s: float = 120
    max_cost_usd: float | None = None


class SandboxSpec(StrictModel):
    memory_mb: int = 2048
    cpu_seconds: int = 600
    max_file_mb: int = 64
    max_processes: int = 1024  # RLIMIT_NPROC counts threads and is per-uid across concurrent sandboxes
    max_workspace_mb: int = 512
    network: bool = False


class FaultSpec(StrictModel):
    """Deterministic fault injection for tool-use benchmarks."""

    tool: str
    match: str = ".*"  # regex applied to the JSON-encoded tool arguments
    mode: Literal["error", "timeout", "truncate"] = "error"
    times: int = 1
    message: str = "Transient failure: the tool could not complete. Retrying may help."


class EnvironmentSpec(StrictModel):
    workspace: str | None = "fixtures/workspace"
    # Extra directories copied into the workspace: {benchmark_relative_src: workspace_relative_dst}
    overlays: dict[str, str] = Field(default_factory=dict)
    setup: list[str] = Field(default_factory=list)
    python_packages: list[str] = Field(default_factory=list)
    tools: list[str] = Field(
        default_factory=lambda: [
            "list_files", "read_file", "write_file", "edit_file", "search", "run_command", "ask_user",
        ]
    )
    faults: list[FaultSpec] = Field(default_factory=list)
    user_simulator: str | None = None  # path to YAML rules for the ask_user tool
    protected_paths: list[str] = Field(default_factory=list)
    sandbox: SandboxSpec = Field(default_factory=SandboxSpec)
    git_init: bool = True


class InterruptionSpec(StrictModel):
    """Simulated session interruption: context is wiped and a resume prompt starts a new session."""

    after_tool_calls: list[int] = Field(default_factory=list)
    resume_prompt: str = "fixtures/RESUME_PROMPT.md"


class CaseSource(StrictModel):
    file: str = "fixtures/cases.yaml"


# --------------------------------------------------------------------------- evaluation


class CheckSpec(BaseModel):
    """A single evaluation check. Type-specific parameters live alongside ``id``/``type``."""

    model_config = ConfigDict(extra="allow")

    id: str
    type: str
    description: str = ""
    timeout_s: float = 300

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not re.match(r"^[a-z0-9_]+$", v):
            raise ValueError(f"check id must be snake_case: {v!r}")
        return v

    @property
    def params(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


class EvaluationSpec(StrictModel):
    checks: list[CheckSpec]

    @model_validator(mode="after")
    def _unique(self) -> "EvaluationSpec":
        ids = [c.id for c in self.checks]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            raise ValueError(f"duplicate check ids: {sorted(dup)}")
        return self


class Transform(StrictModel):
    """Maps a raw metric to [0, 1]. ``linear``: zero_at -> 0, full_at -> 1 (clamped)."""

    type: Literal["linear", "threshold", "identity"] = "identity"
    zero_at: float | None = None
    full_at: float | None = None
    threshold: float | None = None  # for type=threshold: value >= threshold -> 1 else 0
    invert: bool = False  # for type=threshold: value <= threshold -> 1


class Criterion(StrictModel):
    id: str
    description: str = ""
    weight: float = Field(gt=0)
    metric: str  # "<check_id>.<metric_name>"
    transform: Transform = Field(default_factory=Transform)
    required: bool = True  # if unavailable the attempt is "incomplete" (no pass/fail verdict)


class CriticalFailure(StrictModel):
    id: str
    description: str = ""
    when: str  # safe boolean expression over metrics, e.g. "scope.protected_modified > 0"
    effect: Literal["fail", "zero", "cap"] = "zero"
    cap: float | None = None

    @model_validator(mode="after")
    def _cap(self) -> "CriticalFailure":
        if self.effect == "cap" and self.cap is None:
            raise ValueError("effect=cap requires 'cap'")
        return self


class ScoringSpec(StrictModel):
    criteria: list[Criterion]
    pass_threshold: float = 70.0
    # Additional gates that must hold for "passed" (expressions), independent of score.
    pass_requires: list[str] = Field(default_factory=list)
    critical_failures: list[CriticalFailure] = Field(default_factory=list)

    @model_validator(mode="after")
    def _weights(self) -> "ScoringSpec":
        ids = [c.id for c in self.criteria]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate criterion ids")
        return self


class RepetitionSpec(StrictModel):
    attempts: int = Field(default=1, ge=1)
    infra_retries: int = Field(default=1, ge=0)


# --------------------------------------------------------------------------- self-test


class SolutionSpec(StrictModel):
    """A canned solution used to validate that the grader discriminates."""

    kind: Literal["overlay", "responses", "script", "noop"]
    path: str | None = None  # relative to benchmark dir
    report: str | None = None  # final message for overlay solutions (file path or literal)
    run_commands: list[str] = Field(default_factory=list)


class ExpectSpec(StrictModel):
    min_score: float | None = None
    max_score: float | None = None
    passed: bool | None = None
    critical: list[str] | None = None  # exact set of critical failure ids expected (None = don't care)
    metrics: dict[str, list[float]] = Field(default_factory=dict)  # metric -> [min, max]


class SelfTestCase(StrictModel):
    name: str
    description: str = ""
    solution: SolutionSpec
    expect: ExpectSpec


class BudgetTier(StrictModel):
    description: str = ""
    limits: LimitsSpec


# --------------------------------------------------------------------------- benchmark


class BenchmarkSpec(StrictModel):
    schema_version: Literal[1] = 1
    id: str
    name: str
    version: str
    category: str
    difficulty: Literal["easy", "medium", "hard", "expert"]
    description: str
    languages: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    mode: Literal["agent", "chat"]
    # What kind of system can legitimately be compared on this benchmark.
    requires: list[Literal["tools", "vision", "multi_turn", "long_context"]] = Field(default_factory=list)

    prompt: str = "PROMPT.md"
    cases: CaseSource | None = None
    environment: EnvironmentSpec = Field(default_factory=EnvironmentSpec)
    limits: LimitsSpec = Field(default_factory=LimitsSpec)
    budget_tiers: dict[str, BudgetTier] = Field(default_factory=dict)
    default_tier: str | None = None
    interruptions: InterruptionSpec | None = None

    evaluation: EvaluationSpec
    scoring: ScoringSpec
    metrics_collected: list[str] = Field(default_factory=list)
    repetition: RepetitionSpec = Field(default_factory=RepetitionSpec)
    selftest: list[SelfTestCase] = Field(default_factory=list)
    # Strings that must never appear in what the model sees (PROMPT.md, workspace, cases inputs).
    leak_canaries: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError(f"benchmark id must look like 'category/name' (snake_case): {v!r}")
        return v

    @field_validator("version")
    @classmethod
    def _valid_version(cls, v: str) -> str:
        if not SEMVER_RE.match(v):
            raise ValueError(f"version must be semver MAJOR.MINOR.PATCH: {v!r}")
        return v

    @model_validator(mode="after")
    def _consistency(self) -> "BenchmarkSpec":
        if not self.id.startswith(self.category + "/"):
            raise ValueError(f"id {self.id!r} must start with its category {self.category!r}/")
        check_ids = {c.id for c in self.evaluation.checks}
        for crit in self.scoring.criteria:
            check = crit.metric.split(".", 1)[0]
            if check not in check_ids:
                raise ValueError(f"criterion {crit.id!r} references unknown check {check!r}")
        if self.mode == "chat" and self.cases is None:
            raise ValueError("chat benchmarks must declare 'cases'")
        if self.default_tier and self.default_tier not in self.budget_tiers:
            raise ValueError(f"default_tier {self.default_tier!r} not in budget_tiers")
        return self

    def limits_for(self, tier: str | None) -> LimitsSpec:
        tier = tier or self.default_tier
        if tier is None:
            return self.limits
        if tier not in self.budget_tiers:
            raise KeyError(f"benchmark {self.id} has no budget tier {tier!r}; available: {sorted(self.budget_tiers)}")
        return self.budget_tiers[tier].limits


class LoadedBenchmark(BaseModel):
    """A validated benchmark plus its location and content hash."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    spec: BenchmarkSpec
    path: Path
    content_hash: str
    file_hashes: dict[str, str]

    @property
    def id(self) -> str:
        return self.spec.id

    def resolve(self, rel: str) -> Path:
        from aibench.core.util import safe_join

        return safe_join(self.path, rel)
