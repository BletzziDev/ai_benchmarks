"""Episode drivers: native tool-calling agent loop, chat conversations and external agents."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aibench.adapters.base import AdapterError, AgentAdapter, Message, ModelAdapter
from aibench.core.spec import LimitsSpec
from aibench.core.tools import ToolExecutor
from aibench.core.trace import Trace
from aibench.core.util import estimate_tokens

ELIDED = "[output elided by the harness to stay within the context budget; re-run the tool if you need it]"


@dataclass
class EpisodeResult:
    termination: str  # completed | max_turns | max_tool_calls | token_budget | cost_budget | wall_clock | model_error | cancelled
    final_text: str
    messages: list[Message]
    error: str | None = None
    sessions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def infra_failure(self) -> bool:
        return self.termination == "model_error"


class Cancelled(Exception):
    pass


def _budget_exceeded(limits: LimitsSpec, trace: Trace, deadline: float) -> str | None:
    t = trace.totals
    if limits.max_turns is not None and t.model_calls >= limits.max_turns:
        return "max_turns"
    if limits.max_tool_calls is not None and t.tool_calls >= limits.max_tool_calls:
        return "max_tool_calls"
    if limits.max_total_tokens is not None and t.input_tokens is not None:
        used = (t.input_tokens or 0) + (t.output_tokens or 0) + (t.cache_read_tokens or 0) + (t.cache_write_tokens or 0)
        if used >= limits.max_total_tokens:
            return "token_budget"
    if limits.max_cost_usd is not None and t.cost_usd is not None and t.cost_usd >= limits.max_cost_usd:
        return "cost_budget"
    if time.monotonic() >= deadline:
        return "wall_clock"
    return None


def _manage_context(messages: list[Message], strategy: str, budget_tokens: int, trace: Trace) -> None:
    if strategy != "elide_old_tool_outputs":
        return
    est = sum(estimate_tokens(m.content) for m in messages)
    if est <= budget_tokens:
        return
    for m in messages:
        if m.role == "tool" and m.content != ELIDED:
            est -= estimate_tokens(m.content)
            m.content = ELIDED
            trace.totals.context_elisions += 1
            if est <= budget_tokens * 0.8:
                break
    trace.emit("context_elision", estimated_tokens_after=est, budget_tokens=budget_tokens)


def run_agent_episode(
    adapter: ModelAdapter,
    executor: ToolExecutor,
    system_prompt: str,
    task_prompt: str,
    limits: LimitsSpec,
    trace: Trace,
    context_strategy: str = "none",
    context_budget_tokens: int = 400_000,
    interruptions: list[int] | None = None,
    resume_prompt: str | None = None,
    cancel_check: Any = None,
) -> EpisodeResult:
    deadline = time.monotonic() + (limits.wall_clock_s or 10**9)
    tools = executor.specs()
    pending_interrupts = sorted(interruptions or [])
    messages = [Message("system", system_prompt), Message("user", task_prompt)]
    all_sessions: list[dict[str, Any]] = []
    session_start_msgs = 0
    trace.emit("session_start", session=1, tools=[t.name for t in tools], limits=limits.model_dump())

    def on_retry(attempt: int, err: str, delay: float) -> None:
        trace.totals.retries += 1
        trace.emit("model_retry", attempt=attempt, error=err, delay_s=delay)

    while True:
        if cancel_check and cancel_check():
            return EpisodeResult("cancelled", "", messages, sessions=all_sessions)
        reason = _budget_exceeded(limits, trace, deadline)
        if reason:
            trace.emit("budget_exhausted", reason=reason)
            last = next((m.content for m in reversed(messages) if m.role == "assistant" and m.content), "")
            return EpisodeResult(reason, last, messages, sessions=all_sessions)

        if pending_interrupts and trace.totals.tool_calls >= pending_interrupts[0]:
            pending_interrupts.pop(0)
            trace.totals.sessions += 1
            all_sessions.append({"messages": len(messages) - session_start_msgs, "ended_by": "interruption"})
            trace.emit("interruption", session=trace.totals.sessions, after_tool_calls=trace.totals.tool_calls,
                       note="context wiped; workspace preserved")
            messages = [Message("system", system_prompt), Message("user", resume_prompt or task_prompt)]
            session_start_msgs = 0

        _manage_context(messages, context_strategy, context_budget_tokens, trace)
        remaining_turn_budget = limits.max_output_tokens_per_turn
        t0 = time.monotonic()
        try:
            resp = adapter.complete_with_retries(messages, tools, remaining_turn_budget, on_retry=on_retry)
        except AdapterError as e:
            trace.totals.model_time_s += time.monotonic() - t0
            trace.emit("model_error", error=str(e), status=e.status, retryable=e.retryable)
            return EpisodeResult("model_error", "", messages, error=str(e), sessions=all_sessions)
        dt = time.monotonic() - t0
        trace.totals.model_calls += 1
        trace.totals.model_time_s += dt
        cost = adapter.cost_usd(resp.usage)
        trace.record_usage(resp.usage, cost)
        trace.emit("model_call", latency_s=round(dt, 3), stop_reason=resp.stop_reason, text_chars=len(resp.text),
                   tool_calls=[c.name for c in resp.tool_calls], usage=resp.usage.__dict__, cost_usd=cost,
                   model_reported=resp.model_reported, request_id=resp.request_id, text_preview=resp.text[:2000])
        messages.append(Message("assistant", resp.text, tool_calls=resp.tool_calls, provider_raw=resp.provider_raw,
                                provider=adapter.cfg.adapter))
        if not resp.tool_calls:
            trace.emit("session_end", reason="completed")
            all_sessions.append({"messages": len(messages) - session_start_msgs, "ended_by": "final_answer"})
            return EpisodeResult("completed", resp.text, messages, sessions=all_sessions)
        for call in resp.tool_calls:
            content, is_error = executor.execute(call)
            messages.append(Message("tool", content, tool_call_id=call.id, is_error=is_error))


@dataclass
class ChatCaseResult:
    case_id: str
    replies: list[str]
    messages: list[Message]
    termination: str
    error: str | None = None


def run_chat_case(adapter: ModelAdapter, system_prompt: str, user_turns: list[str], limits: LimitsSpec,
                  trace: Trace, case_id: str, images: list[Any] | None = None) -> ChatCaseResult:
    """Scripted multi-turn conversation: each user turn is fixed in advance (no adaptive follow-ups),
    so every model sees the same inputs regardless of its earlier answers."""
    messages: list[Message] = []
    if adapter.capabilities.system_prompt:
        messages.append(Message("system", system_prompt))
    replies: list[str] = []
    trace.emit("case_start", case_id=case_id, turns=len(user_turns))

    def on_retry(attempt: int, err: str, delay: float) -> None:
        trace.totals.retries += 1
        trace.emit("model_retry", case_id=case_id, attempt=attempt, error=err, delay_s=delay)

    for i, turn in enumerate(user_turns):
        content = turn
        if i == 0 and not adapter.capabilities.system_prompt:
            content = f"{system_prompt}\n\n{turn}"
        messages.append(Message("user", content, images=list(images or []) if i == 0 else []))
        t0 = time.monotonic()
        try:
            resp = adapter.complete_with_retries(messages, None, limits.max_output_tokens_per_turn, on_retry=on_retry)
        except AdapterError as e:
            trace.totals.model_time_s += time.monotonic() - t0
            trace.emit("model_error", case_id=case_id, turn=i, error=str(e))
            return ChatCaseResult(case_id, replies, messages, "model_error", str(e))
        dt = time.monotonic() - t0
        trace.totals.model_calls += 1
        trace.totals.model_time_s += dt
        cost = adapter.cost_usd(resp.usage)
        trace.record_usage(resp.usage, cost)
        trace.emit("model_call", case_id=case_id, turn=i, latency_s=round(dt, 3), stop_reason=resp.stop_reason,
                   usage=resp.usage.__dict__, cost_usd=cost, model_reported=resp.model_reported, text_chars=len(resp.text))
        messages.append(Message("assistant", resp.text, provider_raw=resp.provider_raw, provider=adapter.cfg.adapter))
        replies.append(resp.text)
    return ChatCaseResult(case_id, replies, messages, "completed")


def run_external_agent(adapter: AgentAdapter, prompt: str, workspace: Path, limits: LimitsSpec, trace: Trace) -> EpisodeResult:
    trace.emit("session_start", session=1, external_agent=adapter.label, limits=limits.model_dump())
    res = adapter.run_task(prompt, workspace, timeout_s=limits.wall_clock_s or 3600, env={})
    trace.totals.model_time_s += res.duration_s  # indistinguishable from tool time for black-box agents
    trace.record_usage(res.usage, res.cost_usd)
    if res.num_turns is not None:
        trace.totals.model_calls = res.num_turns
    trace.emit("external_agent_result", exit_code=res.exit_code, timed_out=res.timed_out, duration_s=res.duration_s,
               usage=res.usage.__dict__, cost_usd=res.cost_usd, extra=res.extra, stderr_tail=res.stderr[-4000:],
               note="tool calls inside the external agent are not observable by the harness")
    term = "wall_clock" if res.timed_out else ("completed" if res.exit_code == 0 else "agent_error")
    msgs = [Message("user", prompt), Message("assistant", res.final_text)]
    return EpisodeResult(term, res.final_text, msgs, error=None if res.exit_code == 0 else res.stderr[-2000:])
