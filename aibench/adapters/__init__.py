"""Adapter registry. New providers register a factory here (or via ``module:Class`` in models.yaml)."""

from __future__ import annotations

import importlib
from typing import Callable

from aibench.adapters.base import AgentAdapter, ModelAdapter
from aibench.core.config import ModelConfig


def _anthropic(label: str, cfg: ModelConfig) -> ModelAdapter:
    from aibench.adapters.anthropic_adapter import AnthropicAdapter

    return AnthropicAdapter(label, cfg)


def _openai(label: str, cfg: ModelConfig) -> ModelAdapter:
    from aibench.adapters.openai_compat import OpenAICompatibleAdapter

    return OpenAICompatibleAdapter(label, cfg)


def _scripted(label: str, cfg: ModelConfig) -> ModelAdapter:
    from aibench.adapters.scripted import ScriptedAdapter

    return ScriptedAdapter(label, cfg)


def _external(label: str, cfg: ModelConfig) -> AgentAdapter:
    from aibench.adapters.external_agent import ExternalAgentAdapter

    return ExternalAgentAdapter(label, cfg)


ADAPTERS: dict[str, Callable[[str, ModelConfig], ModelAdapter | AgentAdapter]] = {
    "anthropic": _anthropic,
    "openai_compatible": _openai,
    "scripted": _scripted,
    "external_agent": _external,
}


def create_adapter(label: str, cfg: ModelConfig) -> ModelAdapter | AgentAdapter:
    if cfg.adapter in ADAPTERS:
        return ADAPTERS[cfg.adapter](label, cfg)
    if ":" in cfg.adapter:  # third-party adapter: "package.module:ClassName"
        mod, cls = cfg.adapter.split(":", 1)
        return getattr(importlib.import_module(mod), cls)(label, cfg)
    raise KeyError(f"unknown adapter {cfg.adapter!r}; known: {sorted(ADAPTERS)}")
