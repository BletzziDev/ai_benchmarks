# Adapters: models, agents and providers

The harness separates six concerns, each in its own module:

| Concern | Module |
|---|---|
| Model interface (neutral messages, tool calls, usage) | `aibench/adapters/base.py` |
| Tool-call protocol offered to models | `aibench/core/tools.py` |
| Execution environment | `aibench/core/sandbox.py` |
| Context management | `aibench/core/agent_loop.py` (`context_strategy`) |
| Metric capture | `aibench/core/trace.py` |
| Evaluation / storage | `aibench/core/evaluator.py`, `checks/`, `artifacts.py` |

## Kinds of systems

| Kind | Adapter base | Who runs the loop | Observable |
|---|---|---|---|
| `model` | `ModelAdapter.complete(messages, tools, max_output_tokens)` | this harness (neutral tools, system prompt in `configs/prompts/`) | every call and tool call |
| `agent` | `AgentAdapter.run_task(prompt, workspace, timeout_s, env)` | the agent (its own tools, memory, prompts) | final output, final workspace, whatever usage the agent reports |
| `scripted` | `ScriptedAdapter` | canned solutions | used only for validation/demos |

Results record `system_kind`; comparisons across kinds are flagged.

## Built-in adapters

| `adapter:` | Provider | Notes |
|---|---|---|
| `anthropic` | Anthropic Messages API via the official SDK (`pip install 'aibench[anthropic]'`) | Assistant turns are replayed with their original content blocks so thinking blocks survive; tool results for one turn are sent in one user message; `tool_choice` stays `auto`; declare sampling params as `unsupported_params` for models that reject them; `provider_options` (e.g. `output_config: {effort: high}`) are passed through. Images supported (frontend judging). |
| `openai_compatible` | OpenAI Chat Completions shape (OpenAI, OpenRouter, vLLM, Ollama, LM Studio, …) | Stdlib HTTP; `options.max_tokens_param` for providers that renamed it; unparsable tool-call JSON is returned to the model as a tool error; cached prompt tokens are reported separately when present. |
| `external_agent` | Any CLI agent | `options.command`, `prompt_via: stdin|file|arg`, `output_format: text|claude_json`, `env_passthrough`. |
| `scripted` | — | `options.solution: reference|noop|<selftest name>`. |
| `package.module:Class` | your own | Subclass `ModelAdapter` or `AgentAdapter`. |

## Writing an adapter

```python
from aibench.adapters.base import Capabilities, ModelAdapter, ModelResponse, ToolCall, Usage

class MyAdapter(ModelAdapter):
    @property
    def capabilities(self):
        return Capabilities(tool_calling=True, vision=False, usage_reporting=True, seed=False)

    def complete(self, messages, tools, max_output_tokens):
        ...  # translate neutral Message/ToolSpec -> provider; raise AdapterError(retryable=...) on failures
        return ModelResponse(text=..., tool_calls=[ToolCall(id, name, args)], usage=Usage(..., reported=True),
                             stop_reason=..., latency_s=..., model_reported=..., request_id=...)
```

Rules:

- **Never invent metrics.** If the provider returns no usage, return `Usage()` (`reported=False`).
- **Report what you could not apply.** Unsupported params are dropped by `ModelAdapter._resolve_params`
  and appear in the manifest.
- **Classify errors.** `AdapterError(retryable=True)` for 408/409/429/5xx/connection errors (the base
  class retries with exponential backoff and logs each retry); `retryable=False` otherwise. Persistent
  failures become `infra_error` attempts, excluded from scores.
- **Do not leak secrets.** Read keys from the env var named in `api_key_env`; never log them.

## Context management

`configs/benchmark.yaml → harness.context_strategy`:

- `none` (default): append-only history. Required by providers that bind reasoning blocks to the exact
  history (editing earlier turns can invalidate them or be rejected).
- `elide_old_tool_outputs`: when the estimated context (chars/4, labelled as an estimate) exceeds
  `context_budget_tokens`, the oldest tool outputs are replaced with a placeholder; each elision is a
  trace event. Use only with providers that accept edited history.

Long-horizon benchmarks additionally test *agent-side* context management through simulated
interruptions: the context is wiped and the agent must resume from the repository and its own
checkpoint file.
