"""Adapter for complete external coding agents (e.g. Claude Code, aider, Codex CLI).

The agent is a black box: it receives the prompt and the workspace path and runs its own loop
with its own tools. The harness only sees the final output and whatever usage the agent reports.
Results are therefore labelled ``system_kind=agent`` and are never ranked against bare models.

Security: the agent process runs on the host with a scrubbed environment (only the variables
listed in ``env_passthrough``), inside the sandbox workspace directory, under a timeout. It is
NOT inside the network/uid sandbox because it must reach its own API. Use a disposable VM or
container for untrusted agents (docs/security.md).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from aibench.adapters.base import AgentAdapter, AgentRunResult, Usage
from aibench.core.sandbox import BASE_PATH


class ExternalAgentAdapter(AgentAdapter):
    def run_task(self, prompt: str, workspace: Path, timeout_s: float, env: dict[str, str]) -> AgentRunResult:
        o = self.cfg.options
        command = list(o.get("command") or [])
        if not command:
            raise ValueError(f"model {self.label}: options.command is required")
        via = o.get("prompt_via", "stdin")
        stdin = None
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as pf:
            pf.write(prompt)
            prompt_file = pf.name
        try:
            command = [c.replace("{prompt_file}", prompt_file).replace("{workspace}", str(workspace)) for c in command]
            if via == "stdin":
                stdin = prompt
            elif via == "arg":
                command = [c.replace("{prompt}", prompt) for c in command]
            run_env = {"PATH": os.environ.get("PATH", BASE_PATH), "HOME": os.environ.get("HOME", "/tmp"),
                       "LANG": "C.UTF-8", "CI": "1"}
            for k in o.get("env_passthrough", []):
                if k in os.environ:
                    run_env[k] = os.environ[k]
            run_env.update(env)
            start = time.monotonic()
            timed_out = False
            proc = subprocess.Popen(command, cwd=workspace, env=run_env, stdin=subprocess.PIPE if stdin else subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, text=True)
            try:
                out, err = proc.communicate(input=stdin, timeout=timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                out, err = proc.communicate()
            duration = time.monotonic() - start
        finally:
            os.unlink(prompt_file)
        result = AgentRunResult(final_text=out, exit_code=None if timed_out else proc.returncode, stdout=out,
                                stderr=err, duration_s=duration, timed_out=timed_out)
        if o.get("output_format") == "claude_json":
            _parse_claude_json(out, result)
        return result


def _parse_claude_json(out: str, result: AgentRunResult) -> None:
    """Parse ``claude -p --output-format json``. Unknown/missing fields stay unavailable."""
    text = out.strip()
    try:
        data = json.loads(text.splitlines()[-1] if text and not text.startswith("{") else text)
    except (json.JSONDecodeError, IndexError):
        result.extra["parse_error"] = "output was not JSON"
        return
    result.final_text = str(data.get("result", ""))
    u = data.get("usage") or {}
    if u:
        result.usage = Usage(input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
                             cache_read_tokens=u.get("cache_read_input_tokens"),
                             cache_write_tokens=u.get("cache_creation_input_tokens"), reported=True)
    if isinstance(data.get("total_cost_usd"), (int, float)):
        result.cost_usd = float(data["total_cost_usd"])
        result.extra["cost_source"] = "reported by agent"
    result.num_turns = data.get("num_turns")
    result.extra["is_error"] = data.get("is_error")
    result.extra["session_id"] = data.get("session_id")
