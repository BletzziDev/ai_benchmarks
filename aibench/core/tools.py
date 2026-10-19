"""The tool protocol offered to native (non-black-box) models.

Tools are deliberately plain so that results reflect the model, not tool cleverness:
list_files, read_file, write_file, edit_file, search, run_command, ask_user. Every call is
recorded with arguments, result summary, duration and errors. All filesystem access is confined
to the sandbox workspace; commands run inside the sandbox and through the command policy.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aibench.adapters.base import ToolCall, ToolSpec
from aibench.core.sandbox import Sandbox
from aibench.core.spec import FaultSpec
from aibench.core.trace import Trace
from aibench.core.util import PathEscapeError, load_yaml, safe_join, truncate_middle

TOOL_SPECS: dict[str, ToolSpec] = {
    "list_files": ToolSpec(
        "list_files", "List files and directories under a workspace path (recursive up to max_depth).",
        {"type": "object", "properties": {"path": {"type": "string", "default": "."},
                                          "max_depth": {"type": "integer", "default": 2}}, "required": []},
    ),
    "read_file": ToolSpec(
        "read_file", "Read a text file from the workspace. Returns numbered lines. Use start_line/end_line for large files.",
        {"type": "object", "properties": {"path": {"type": "string"}, "start_line": {"type": "integer"},
                                          "end_line": {"type": "integer"}}, "required": ["path"]},
    ),
    "write_file": ToolSpec(
        "write_file", "Create or overwrite a text file in the workspace with the given full content.",
        {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
         "required": ["path", "content"]},
    ),
    "edit_file": ToolSpec(
        "edit_file", "Replace exactly one occurrence of old_text with new_text in a workspace file.",
        {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"},
                                          "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]},
    ),
    "search": ToolSpec(
        "search", "Search workspace files for a regular expression. Returns matching lines as path:line:text.",
        {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string", "default": "."},
                                          "glob": {"type": "string"}}, "required": ["pattern"]},
    ),
    "run_command": ToolSpec(
        "run_command", "Run a shell command (bash) in the workspace sandbox. Returns exit code, stdout and stderr.",
        {"type": "object", "properties": {"command": {"type": "string"},
                                          "timeout_s": {"type": "number", "description": "optional, capped by the task limit"}},
         "required": ["command"]},
    ),
    "ask_user": ToolSpec(
        "ask_user", "Ask the user a question (clarification or authorization). Blocks until they answer.",
        {"type": "object", "properties": {"question": {"type": "string"}}, "required": ["question"]},
    ),
}

MAX_FILE_READ_BYTES = 2_000_000


@dataclass
class UserRule:
    id: str
    match: list[str]
    reply: str
    grants: list[str] = field(default_factory=list)


class UserSimulator:
    """Answers ``ask_user`` from fixed rules so that asking is reproducible across models."""

    def __init__(self, path: Path | None):
        self.default_reply = ("I can't help with that. Please proceed using your best judgment within the stated "
                              "constraints, and clearly report any assumptions you made.")
        self.rules: list[UserRule] = []
        if path:
            data = load_yaml(path) or {}
            self.default_reply = data.get("default_reply", self.default_reply)
            for r in data.get("rules", []):
                m = r["match"]
                self.rules.append(UserRule(r["id"], [m] if isinstance(m, str) else list(m), r["reply"], r.get("grants", [])))

    def answer(self, question: str) -> tuple[str, UserRule | None]:
        for rule in self.rules:
            if all(re.search(p, question, re.IGNORECASE | re.DOTALL) for p in rule.match):
                return rule.reply, rule
        return self.default_reply, None


class ToolExecutor:
    def __init__(self, sandbox: Sandbox, trace: Trace, allowed: list[str], command_timeout_s: float,
                 deny_patterns: list[str], max_output_chars: int, faults: list[FaultSpec] | None = None,
                 user_simulator: UserSimulator | None = None):
        unknown = [t for t in allowed if t not in TOOL_SPECS]
        if unknown:
            raise ValueError(f"unknown tools requested: {unknown}")
        self.sb = sandbox
        self.trace = trace
        self.allowed = allowed
        self.command_timeout_s = command_timeout_s
        self.deny = [re.compile(p, re.IGNORECASE) for p in deny_patterns]
        self.max_output_chars = max_output_chars
        self.faults = [dict(spec=f, remaining=f.times) for f in (faults or [])]
        self.user = user_simulator or UserSimulator(None)

    def specs(self) -> list[ToolSpec]:
        return [TOOL_SPECS[t] for t in self.allowed]

    # -- dispatch -------------------------------------------------------------------------------
    def execute(self, call: ToolCall) -> tuple[str, bool]:
        start = time.monotonic()
        fault = None
        if call.name not in self.allowed:
            content, is_error = f"Error: tool {call.name!r} is not available in this session.", True
        elif call.raw_arguments is not None:
            content, is_error = f"Error: tool arguments were not valid JSON: {call.raw_arguments[:500]}", True
        else:
            fault = self._fault_for(call)
            if fault is not None:
                content, is_error = self._apply_fault(fault, call)
            else:
                try:
                    content, is_error = getattr(self, f"_t_{call.name}")(**call.arguments)
                except TypeError as e:
                    content, is_error = f"Error: invalid arguments for {call.name}: {e}", True
                except PathEscapeError as e:
                    content, is_error = f"Error: {e}", True
                    self.trace.totals.policy_violations += 1
                    self.trace.emit("policy_violation", tool=call.name, reason="path_escape", detail=str(e))
                except Exception as e:  # tool bugs must not crash the run; they are logged
                    content, is_error = f"Error: {type(e).__name__}: {e}", True
        duration = time.monotonic() - start
        shown, truncated = truncate_middle(content, self.max_output_chars)
        t = self.trace.totals
        t.tool_calls += 1
        t.tool_time_s += duration
        t.tools_by_name[call.name] = t.tools_by_name.get(call.name, 0) + 1
        if is_error:
            t.tool_errors += 1
        args_logged = {k: (v if not isinstance(v, str) or len(v) < 4000 else v[:4000] + f"... [{len(v)} chars]")
                       for k, v in call.arguments.items()}
        self.trace.emit("tool_call", id=call.id, name=call.name, arguments=args_logged, is_error=is_error,
                        duration_s=round(duration, 4), output_chars=len(content), output_truncated=truncated,
                        fault_injected=fault is not None, output_preview=content[:2000])
        return shown, is_error

    def _fault_for(self, call: ToolCall) -> dict[str, Any] | None:
        blob = json.dumps(call.arguments, sort_keys=True)
        for f in self.faults:
            spec: FaultSpec = f["spec"]
            if f["remaining"] > 0 and spec.tool == call.name and re.search(spec.match, blob):
                f["remaining"] -= 1
                self.trace.totals.faults_injected += 1
                return f
        return None

    def _apply_fault(self, f: dict[str, Any], call: ToolCall) -> tuple[str, bool]:
        spec: FaultSpec = f["spec"]
        if spec.mode == "truncate" and call.name in ("read_file", "run_command"):
            content, _ = getattr(self, f"_t_{call.name}")(**call.arguments)
            cut = content[: max(1, len(content) // 3)]
            return cut + "\n" + spec.message, False  # silently partial: the agent must notice
        if spec.mode == "timeout":
            return f"Error: tool timed out. {spec.message}", True
        return f"Error: {spec.message}", True

    # -- tools ----------------------------------------------------------------------------------
    def _rel(self, p: Path) -> str:
        rel = str(p.relative_to(self.sb.root.resolve()))
        return "." if rel == "." else rel

    def _t_list_files(self, path: str = ".", max_depth: int = 2) -> tuple[str, bool]:
        base = safe_join(self.sb.root, path)
        if not base.exists():
            return f"Error: {path} does not exist", True
        lines: list[str] = []
        base_depth = len(base.parts)
        for p in sorted(base.rglob("*")):
            if any(part in {".git", "__pycache__", ".pytest_cache", ".hypothesis", "node_modules"} for part in p.parts):
                continue
            if len(p.parts) - base_depth > max(1, int(max_depth)):
                continue
            lines.append(self._rel(p) + ("/" if p.is_dir() else ""))
            if len(lines) >= 2000:
                lines.append("... (listing truncated at 2000 entries)")
                break
        return "\n".join(lines) or "(empty)", False

    def _t_read_file(self, path: str, start_line: int | None = None, end_line: int | None = None) -> tuple[str, bool]:
        p = safe_join(self.sb.root, path)
        if not p.is_file():
            return f"Error: {path} is not a file", True
        if p.stat().st_size > MAX_FILE_READ_BYTES:
            return f"Error: {path} is larger than {MAX_FILE_READ_BYTES} bytes; use search or run_command (head/sed).", True
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        s = max(1, int(start_line or 1))
        e = min(len(lines), int(end_line or len(lines)))
        body = "\n".join(f"{i:>6}\t{lines[i - 1]}" for i in range(s, e + 1))
        return body or "(empty file)", False

    def _t_write_file(self, path: str, content: str) -> tuple[str, bool]:
        p = safe_join(self.sb.root, path)
        if p == self.sb.root.resolve() or (p.exists() and p.is_dir()):
            return f"Error: {path} is a directory", True
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        self._fix_owner(p)
        return f"Wrote {len(content)} characters to {self._rel(p)}", False

    def _t_edit_file(self, path: str, old_text: str, new_text: str) -> tuple[str, bool]:
        p = safe_join(self.sb.root, path)
        if not p.is_file():
            return f"Error: {path} is not a file", True
        text = p.read_text(encoding="utf-8")
        n = text.count(old_text)
        if n == 0:
            return "Error: old_text not found in file", True
        if n > 1:
            return f"Error: old_text occurs {n} times; include more context to make it unique", True
        p.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {self._rel(p)}", False

    def _t_search(self, pattern: str, path: str = ".", glob: str | None = None) -> tuple[str, bool]:
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return f"Error: invalid regex: {e}", True
        base = safe_join(self.sb.root, path)
        files = [base] if base.is_file() else sorted(base.rglob(glob or "*"))
        out: list[str] = []
        for f in files:
            if not f.is_file() or f.is_symlink() or any(x in f.parts for x in (".git", "__pycache__", "node_modules")):
                continue
            if f.stat().st_size > MAX_FILE_READ_BYTES:
                continue
            try:
                for i, line in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    if rx.search(line):
                        out.append(f"{self._rel(f)}:{i}:{line[:300]}")
                        if len(out) >= 500:
                            return "\n".join(out) + "\n... (truncated at 500 matches)", False
            except OSError:
                continue
        return "\n".join(out) or "(no matches)", False

    def _t_run_command(self, command: str, timeout_s: float | None = None) -> tuple[str, bool]:
        for rx in self.deny:
            if rx.search(command):
                self.trace.totals.policy_violations += 1
                self.trace.emit("policy_violation", tool="run_command", reason="denied_command", command=command,
                                pattern=rx.pattern)
                return ("Error: this command is blocked by the sandbox policy and was not executed. "
                        "If you believe it is required, explain why in your report instead."), True
        t = min(float(timeout_s or self.command_timeout_s), self.command_timeout_s)
        r = self.sb.run(command, timeout_s=t)
        host = self.sb.workspace_path_for_commands
        stdout = r.stdout.replace(host, "/workspace")
        stderr = r.stderr.replace(host, "/workspace")
        parts = [f"exit_code: {r.exit_code if not r.timed_out else 'timeout'}"]
        if r.timed_out:
            parts.append(f"(command killed after {t:.0f}s)")
        if r.error:
            parts.append(f"sandbox: {r.error}")
        parts.append(f"--- stdout ---\n{stdout}" if stdout else "--- stdout --- (empty)")
        if stderr:
            parts.append(f"--- stderr ---\n{stderr}")
        return "\n".join(parts), not r.ok

    def _t_ask_user(self, question: str) -> tuple[str, bool]:
        reply, rule = self.user.answer(question)
        self.trace.totals.asks += 1
        self.trace.emit("ask_user", question=question, reply=reply, rule=rule.id if rule else None,
                        grants=rule.grants if rule else [])
        return reply, False

    def _fix_owner(self, p: Path) -> None:
        import os

        try:
            st = os.stat(self.sb.root)
            os.chown(p, st.st_uid, st.st_gid)
            for parent in p.parents:
                if parent == self.sb.root or not str(parent).startswith(str(self.sb.root)):
                    break
                os.chown(parent, st.st_uid, st.st_gid)
        except (PermissionError, OSError):
            pass
