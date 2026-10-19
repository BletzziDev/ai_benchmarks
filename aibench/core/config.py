"""Suite-level configuration: configs/benchmark.yaml, configs/models.yaml, configs/scoring.yaml."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aibench.core.util import load_yaml


class _M(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CategoryInfo(_M):
    title: str
    description: str = ""


class CommandPolicy(_M):
    """Commands the harness refuses to execute for an agent, regardless of benchmark.

    This is defence in depth: the sandbox is the real boundary. A blocked command is recorded as a
    ``policy_violation`` event that graders can use as evidence.
    """

    deny_patterns: list[str] = Field(default_factory=list)


class HarnessConfig(_M):
    agent_system_prompt: str = "configs/prompts/agent_system.md"
    chat_system_prompt: str = "configs/prompts/chat_system.md"
    max_tool_output_chars: int = 20000
    max_logged_output_chars: int = 2_000_000
    context_strategy: Literal["none", "elide_old_tool_outputs"] = "none"
    context_budget_tokens: int = 400_000


class SandboxConfig(_M):
    backend: Literal["local", "docker"] = "local"
    docker_image: str = "aibench-sandbox:0.1"
    # When the harness runs as root, run sandboxed commands as this uid/gid (65534 = nobody).
    drop_privileges_uid: int = 65534
    drop_privileges_gid: int = 65534
    isolate_network: bool = True  # local backend: new network namespace when available


class SuiteConfig(_M):
    benchmarks_dir: str = "benchmarks"
    results_dir: str = "results"
    categories: dict[str, CategoryInfo] = Field(default_factory=dict)
    harness: HarnessConfig = Field(default_factory=HarnessConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    command_policy: CommandPolicy = Field(default_factory=CommandPolicy)


class Pricing(_M):
    input_per_mtok: float
    output_per_mtok: float
    cache_read_per_mtok: float | None = None
    cache_write_per_mtok: float | None = None
    currency: str = "USD"
    source: str  # where the numbers came from; required so costs are auditable
    as_of: str


class ModelConfig(_M):
    adapter: str
    model: str | None = None
    kind: Literal["model", "agent", "scripted"] = "model"
    description: str = ""
    api_key_env: str | None = None
    base_url: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    # Parameters this model/provider rejects or ignores; they are dropped and logged as "not applied".
    unsupported_params: list[str] = Field(default_factory=list)
    provider_options: dict[str, Any] = Field(default_factory=dict)
    pricing: Pricing | None = None
    options: dict[str, Any] = Field(default_factory=dict)  # adapter-specific
    timeout_s: float = 600
    max_retries: int = 4


class ModelsConfig(_M):
    models: dict[str, ModelConfig]


class StatsConfig(_M):
    confidence: float = 0.95
    bootstrap_iterations: int = 10000
    seed: int = 1234
    min_attempts_for_ci: int = 2


class ScoringConfig(_M):
    category_weights: dict[str, float] = Field(default_factory=dict)  # default: equal
    overall_aggregation: Literal["mean_of_categories", "mean_of_benchmarks"] = "mean_of_categories"
    stats: StatsConfig = Field(default_factory=StatsConfig)
    # Comparisons between runs with different conditions are refused unless forced.
    comparability_fields: list[str] = Field(
        default_factory=lambda: ["benchmark_hash", "tier", "tools", "system_kind", "harness_version"]
    )


class Config(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    root: Path
    suite: SuiteConfig
    models: ModelsConfig
    scoring: ScoringConfig

    @property
    def benchmarks_dir(self) -> Path:
        return (self.root / self.suite.benchmarks_dir).resolve()

    @property
    def results_dir(self) -> Path:
        env = os.environ.get("AIBENCH_RESULTS_DIR")
        return Path(env).resolve() if env else (self.root / self.suite.results_dir).resolve()

    def model(self, label: str) -> ModelConfig:
        if label not in self.models.models:
            raise KeyError(f"unknown model {label!r}; configured: {', '.join(sorted(self.models.models))}")
        return self.models.models[label]


def find_root(start: Path | None = None) -> Path:
    env = os.environ.get("AIBENCH_ROOT")
    if env:
        return Path(env).resolve()
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if (p / "configs" / "benchmark.yaml").is_file():
            return p
    # fall back to the source checkout this package lives in
    pkg_root = Path(__file__).resolve().parents[2]
    if (pkg_root / "configs" / "benchmark.yaml").is_file():
        return pkg_root
    raise FileNotFoundError("could not locate configs/benchmark.yaml (set AIBENCH_ROOT)")


def load_config(root: Path | None = None, models_file: Path | None = None) -> Config:
    root = Path(root).resolve() if root else find_root()
    suite = SuiteConfig.model_validate(load_yaml(root / "configs" / "benchmark.yaml") or {})
    mpath = models_file or Path(os.environ.get("AIBENCH_MODELS_FILE", root / "configs" / "models.yaml"))
    models = ModelsConfig.model_validate(load_yaml(mpath) or {"models": {}})
    scoring = ScoringConfig.model_validate(load_yaml(root / "configs" / "scoring.yaml") or {})
    return Config(root=root, suite=suite, models=models, scoring=scoring)
