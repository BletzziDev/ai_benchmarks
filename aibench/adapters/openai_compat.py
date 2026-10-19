"""OpenAI-compatible Chat Completions adapter (OpenAI, OpenRouter, vLLM, Ollama, LM Studio, ...).

Implemented over the standard library so no vendor SDK is required. Providers differ in what they
honour (seed, usage, tool calling); anything not reported is recorded as unavailable.
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

from aibench.adapters.base import (
    AdapterError, Capabilities, Message, ModelAdapter, ModelResponse, ToolCall, ToolSpec, Usage,
)


def _ssl_context() -> ssl.SSLContext:
    bundle = os.environ.get("AIBENCH_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    return ssl.create_default_context(cafile=bundle) if bundle else ssl.create_default_context()


def post_json(url: str, body: dict[str, Any], headers: dict[str, str], timeout: float) -> tuple[dict[str, Any], dict[str, str]]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    ctx = _ssl_context() if url.startswith("https") else None
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode()), dict(resp.headers)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:2000]
        retry = e.code in (408, 409, 429) or e.code >= 500
        raise AdapterError(f"HTTP {e.code}: {detail}", retryable=retry, status=e.code) from e
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise AdapterError(f"connection error: {e}", retryable=True) from e
    except json.JSONDecodeError as e:
        raise AdapterError(f"invalid JSON response: {e}", retryable=True) from e


class OpenAICompatibleAdapter(ModelAdapter):
    @property
    def capabilities(self) -> Capabilities:
        o = self.cfg.options
        return Capabilities(tool_calling=o.get("tool_calling", True), system_prompt=True,
                            vision=o.get("vision", False), usage_reporting=True,
                            seed=o.get("seed", True), sampling_params=True)

    @staticmethod
    def to_wire(messages: list[Message]) -> list[dict[str, Any]]:
        wire: list[dict[str, Any]] = []
        for m in messages:
            if m.role == "tool":
                wire.append({"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content or "(no output)"})
            elif m.role == "assistant":
                d: dict[str, Any] = {"role": "assistant", "content": m.content or None}
                if m.tool_calls:
                    d["tool_calls"] = [{"id": t.id, "type": "function",
                                        "function": {"name": t.name, "arguments": json.dumps(t.arguments)}}
                                       for t in m.tool_calls]
                wire.append(d)
            elif m.role == "user" and m.images:
                parts: list[dict[str, Any]] = []
                for img in m.images:
                    with open(img.path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    parts.append({"type": "image_url", "image_url": {"url": f"data:{img.media_type};base64,{b64}"}})
                parts.append({"type": "text", "text": m.content})
                wire.append({"role": "user", "content": parts})
            else:
                wire.append({"role": m.role, "content": m.content})
        return wire

    def complete(self, messages: list[Message], tools: list[ToolSpec] | None, max_output_tokens: int) -> ModelResponse:
        base = (self.cfg.base_url or "https://api.openai.com/v1").rstrip("/")
        headers = {}
        if self.cfg.api_key_env:
            key = os.environ.get(self.cfg.api_key_env)
            if not key:
                raise AdapterError(f"environment variable {self.cfg.api_key_env} is not set")
            headers["Authorization"] = f"Bearer {key}"
        tokens_param = self.cfg.options.get("max_tokens_param", "max_tokens")
        body: dict[str, Any] = {"model": self.cfg.model, "messages": self.to_wire(messages),
                                tokens_param: int(self.applied_params.get("max_output_tokens", max_output_tokens))}
        for k in ("temperature", "top_p", "seed"):
            if k in self.applied_params:
                body[k] = self.applied_params[k]
        if tools:
            body["tools"] = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                                               "parameters": t.parameters}} for t in tools]
        body.update(self.cfg.provider_options)
        start = time.monotonic()
        data, resp_headers = post_json(f"{base}/chat/completions", body, headers, self.cfg.timeout_s)
        latency = time.monotonic() - start
        if "error" in data:
            raise AdapterError(f"provider error: {data['error']}", retryable=False)
        try:
            choice = data["choices"][0]
            msg = choice["message"]
        except (KeyError, IndexError) as e:
            raise AdapterError(f"unexpected response shape: {str(data)[:500]}", retryable=True) from e
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            raw = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else dict(raw)
                raw_s = None
            except json.JSONDecodeError:
                args, raw_s = {}, raw
            calls.append(ToolCall(id=tc.get("id") or f"call_{uuid.uuid4().hex[:8]}", name=fn.get("name", ""),
                                  arguments=args, raw_arguments=raw_s))
        u = data.get("usage")
        usage = Usage(reported=False)
        if u:
            details = u.get("prompt_tokens_details") or {}
            cached = details.get("cached_tokens")
            prompt = u.get("prompt_tokens")
            usage = Usage(input_tokens=(prompt - cached) if (prompt is not None and cached) else prompt,
                          output_tokens=u.get("completion_tokens"), cache_read_tokens=cached or None, reported=True)
        return ModelResponse(text=msg.get("content") or "", tool_calls=calls, usage=usage,
                             stop_reason=choice.get("finish_reason"), latency_s=latency,
                             model_reported=data.get("model"), request_id=data.get("id"))
