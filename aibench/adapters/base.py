"""Provider-neutral model interface.

Adapters translate between these neutral types and a provider's wire format. They must report
what they could *not* do (unsupported parameters, missing usage data) instead of inventing values.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from aibench.core.config import ModelConfig

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ImagePart:
    path: str
    media_type: str = "image/png"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str | None = None  # original string when the provider sent unparsable JSON


@dataclass
class Message:
    role: Role
    content: str = ""
    images: list[ImagePart] = field(default_factory=list)
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    is_error: bool = False
    # Provider-native representation of an assistant turn (e.g. Anthropic content blocks including
    # thinking blocks). Replayed verbatim to the same provider so history stays append-only.
    provider_raw: Any = None
    provider: str | None = None

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.images:
            d["images"] = [i.path for i in self.images]
        if self.tool_calls:
            d["tool_calls"] = [{"id": t.id, "name": t.name, "arguments": t.arguments} for t in self.tool_calls]
        if self.tool_call_id:
            d["tool_call_id"] = self.tool_call_id
        if self.is_error:
            d["is_error"] = True
        return d


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class Usage:
    """Token usage as reported by the provider. ``reported=False`` means the provider gave nothing."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    reported: bool = False

    def add(self, other: "Usage") -> "Usage":
        def s(a: int | None, b: int | None) -> int | None:
            if a is None and b is None:
                return None
            return (a or 0) + (b or 0)

        return Usage(
            s(self.input_tokens, other.input_tokens), s(self.output_tokens, other.output_tokens),
            s(self.cache_read_tokens, other.cache_read_tokens), s(self.cache_write_tokens, other.cache_write_tokens),
            self.reported or other.reported,
        )

    @property
    def total(self) -> int | None:
        if self.input_tokens is None and self.output_tokens is None:
            return None
        return (self.input_tokens or 0) + (self.output_tokens or 0) + (self.cache_read_tokens or 0) + (
            self.cache_write_tokens or 0)


@dataclass
class ModelResponse:
    text: str
    tool_calls: list[ToolCall]
    usage: Usage
    stop_reason: str | None
    latency_s: float
    model_reported: str | None = None  # model id echoed by the provider, if any
    provider_raw: Any = None
    request_id: str | None = None


@dataclass
class Capabilities:
    tool_calling: bool = True
    system_prompt: bool = True
    vision: bool = False
    usage_reporting: bool = True
    seed: bool = False
    sampling_params: bool = True


class AdapterError(Exception):
    def __init__(self, message: str, retryable: bool = False, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


class ModelAdapter(ABC):
    """A model that maps a message list (+ optional tools) to one response."""

    kind = "model"

    def __init__(self, label: str, cfg: ModelConfig):
        self.label = label
        self.cfg = cfg
        self.applied_params: dict[str, Any] = {}
        self.dropped_params: dict[str, str] = {}
        self._resolve_params()

    @property
    @abstractmethod
    def capabilities(self) -> Capabilities: ...

    def _resolve_params(self) -> None:
        caps = self.capabilities
        for k, v in self.cfg.params.items():
            if k in self.cfg.unsupported_params:
                self.dropped_params[k] = "declared unsupported for this model in models.yaml"
            elif k == "seed" and not caps.seed:
                self.dropped_params[k] = "provider does not support seeds"
            elif k in ("temperature", "top_p", "top_k") and not caps.sampling_params:
                self.dropped_params[k] = "provider does not support sampling params"
            else:
                self.applied_params[k] = v

    def begin_episode(self, benchmark: Any, case_id: str | None = None, solution: Any = None) -> None:
        """Hook called before each episode (agent attempt or chat case). Real models ignore it."""

    @abstractmethod
    def complete(self, messages: list[Message], tools: list[ToolSpec] | None, max_output_tokens: int) -> ModelResponse:
        """One model call. Raise AdapterError(retryable=...) on provider failures."""

    def complete_with_retries(self, messages: list[Message], tools: list[ToolSpec] | None,
                              max_output_tokens: int, on_retry: Any = None) -> ModelResponse:
        attempt = 0
        while True:
            try:
                return self.complete(messages, tools, max_output_tokens)
            except AdapterError as e:
                attempt += 1
                if not e.retryable or attempt > self.cfg.max_retries:
                    raise
                delay = min(60.0, 2.0 ** attempt)
                if on_retry:
                    on_retry(attempt, str(e), delay)
                time.sleep(delay)

    def describe(self) -> dict[str, Any]:
        caps = self.capabilities
        return {
            "label": self.label,
            "adapter": self.cfg.adapter,
            "kind": self.kind,
            "model": self.cfg.model,
            "base_url": self.cfg.base_url,
            "applied_params": self.applied_params,
            "dropped_params": self.dropped_params,
            "provider_options": self.cfg.provider_options,
            "capabilities": caps.__dict__,
            "pricing": self.cfg.pricing.model_dump() if self.cfg.pricing else None,
        }

    def cost_usd(self, usage: Usage) -> float | None:
        p = self.cfg.pricing
        if p is None or not usage.reported or usage.input_tokens is None:
            return None
        cost = (usage.input_tokens or 0) * p.input_per_mtok + (usage.output_tokens or 0) * p.output_per_mtok
        if usage.cache_read_tokens:
            if p.cache_read_per_mtok is None:
                return None
            cost += usage.cache_read_tokens * p.cache_read_per_mtok
        if usage.cache_write_tokens:
            if p.cache_write_per_mtok is None:
                return None
            cost += usage.cache_write_tokens * p.cache_write_per_mtok
        return cost / 1_000_000


@dataclass
class AgentRunResult:
    final_text: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool
    usage: Usage = field(default_factory=Usage)
    cost_usd: float | None = None
    num_turns: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class AgentAdapter(ABC):
    """A complete agent (its own loop, tools and context management) driven as a black box."""

    kind = "agent"

    def __init__(self, label: str, cfg: ModelConfig):
        self.label = label
        self.cfg = cfg

    @abstractmethod
    def run_task(self, prompt: str, workspace: Path, timeout_s: float, env: dict[str, str]) -> AgentRunResult: ...

    def describe(self) -> dict[str, Any]:
        return {"label": self.label, "adapter": self.cfg.adapter, "kind": self.kind, "options": self.cfg.options,
                "model": self.cfg.model}
