"""Anthropic Messages API adapter (official ``anthropic`` Python SDK).

Notes encoded here (see docs/adapters.md):
- Assistant turns are replayed with their original content blocks (``provider_raw``) so thinking
  blocks survive and history stays append-only.
- All tool results produced for one assistant turn go back in a single user message.
- Current models reject non-default sampling params; list them under ``unsupported_params``.
- ``tool_choice`` is left at ``auto``; forced tool choice is rejected by current models.
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any

from aibench.adapters.base import (
    AdapterError, Capabilities, Message, ModelAdapter, ModelResponse, ToolCall, ToolSpec, Usage,
)


class AnthropicAdapter(ModelAdapter):
    def __init__(self, label, cfg):
        super().__init__(label, cfg)
        self._client = None

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(tool_calling=True, system_prompt=True, vision=True, usage_reporting=True,
                            seed=False, sampling_params=True)

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as e:  # pragma: no cover - environment dependent
                raise AdapterError("the 'anthropic' package is not installed: pip install 'aibench[anthropic]'") from e
            kwargs: dict[str, Any] = {"timeout": self.cfg.timeout_s, "max_retries": 0}  # retries are ours
            if self.cfg.api_key_env:
                key = os.environ.get(self.cfg.api_key_env)
                if not key:
                    raise AdapterError(f"environment variable {self.cfg.api_key_env} is not set")
                kwargs["api_key"] = key
            if self.cfg.base_url:
                kwargs["base_url"] = self.cfg.base_url
            self._client = anthropic.Anthropic(**kwargs)
        return self._client

    # -- translation ---------------------------------------------------------------------------
    @staticmethod
    def to_wire(messages: list[Message]) -> tuple[str | None, list[dict[str, Any]]]:
        system_parts = [m.content for m in messages if m.role == "system"]
        wire: list[dict[str, Any]] = []
        pending_results: list[dict[str, Any]] = []

        def flush() -> None:
            nonlocal pending_results
            if pending_results:
                wire.append({"role": "user", "content": pending_results})
                pending_results = []

        for m in messages:
            if m.role == "system":
                continue
            if m.role == "tool":
                pending_results.append({
                    "type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content or "(no output)",
                    **({"is_error": True} if m.is_error else {}),
                })
                continue
            flush()
            if m.role == "assistant":
                if m.provider == "anthropic" and m.provider_raw is not None:
                    wire.append({"role": "assistant", "content": m.provider_raw})
                    continue
                blocks: list[dict[str, Any]] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
                wire.append({"role": "assistant", "content": blocks or [{"type": "text", "text": "(empty)"}]})
            else:  # user
                if m.images:
                    blocks = []
                    for img in m.images:
                        with open(img.path, "rb") as f:
                            data = base64.standard_b64encode(f.read()).decode()
                        blocks.append({"type": "image", "source": {"type": "base64", "media_type": img.media_type, "data": data}})
                    blocks.append({"type": "text", "text": m.content})
                    wire.append({"role": "user", "content": blocks})
                else:
                    wire.append({"role": "user", "content": m.content})
        flush()
        return ("\n\n".join(system_parts) or None), wire

    @staticmethod
    def from_wire(resp: Any, latency: float) -> ModelResponse:
        text_parts, calls = [], []
        raw_blocks = []
        for block in resp.content:
            raw_blocks.append(block.model_dump(mode="json", exclude_none=True))
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                calls.append(ToolCall(id=block.id, name=block.name, arguments=dict(block.input or {})))
        u = resp.usage
        usage = Usage(
            input_tokens=getattr(u, "input_tokens", None), output_tokens=getattr(u, "output_tokens", None),
            cache_read_tokens=getattr(u, "cache_read_input_tokens", None),
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", None), reported=u is not None,
        )
        return ModelResponse(text="\n".join(text_parts), tool_calls=calls, usage=usage, stop_reason=resp.stop_reason,
                             latency_s=latency, model_reported=getattr(resp, "model", None), provider_raw=raw_blocks,
                             request_id=getattr(resp, "_request_id", None))

    def complete(self, messages: list[Message], tools: list[ToolSpec] | None, max_output_tokens: int) -> ModelResponse:
        import anthropic

        client = self._get_client()
        system, wire = self.to_wire(messages)
        body: dict[str, Any] = {
            "model": self.cfg.model,
            "max_tokens": int(self.applied_params.get("max_output_tokens", max_output_tokens)),
            "messages": wire,
        }
        if system:
            body["system"] = system
        for k in ("temperature", "top_p", "top_k"):
            if k in self.applied_params:
                body[k] = self.applied_params[k]
        if tools:
            body["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools]
        extra = dict(self.cfg.provider_options)
        start = time.monotonic()
        try:
            resp = client.messages.create(**body, extra_body=extra or None)
        except anthropic.RateLimitError as e:
            raise AdapterError(f"rate limited: {e}", retryable=True, status=429) from e
        except anthropic.APIStatusError as e:
            raise AdapterError(f"API error {e.status_code}: {e.message}", retryable=e.status_code >= 500 or e.status_code in (408, 409),
                               status=e.status_code) from e
        except anthropic.APIConnectionError as e:
            raise AdapterError(f"connection error: {e}", retryable=True) from e
        out = self.from_wire(resp, time.monotonic() - start)
        if out.stop_reason == "refusal":
            out.text = out.text or "[model refused]"
        return out
