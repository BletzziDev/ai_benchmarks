"""Deterministic offline adapter that replays canned solutions.

It is *not* a model. It exists to validate the pipeline and the graders: the reference solution
must pass, the no-op must fail, and decoy solutions must fail for the documented reason. All
usage metrics are reported as unavailable because nothing was generated.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from aibench.adapters.base import Capabilities, Message, ModelAdapter, ModelResponse, ToolCall, ToolSpec, Usage
from aibench.core.util import iter_files, load_yaml

DELETE_LIST = ".aibench_delete"


class ScriptedAdapter(ModelAdapter):
    kind = "scripted"

    def __init__(self, label, cfg):
        super().__init__(label, cfg)
        self._queue: list[ModelResponse] = []
        self._chat: dict[str, list[str]] = {}
        self._case: str | None = None
        self._turn = 0
        self.solution_name: str | None = None

    @property
    def capabilities(self) -> Capabilities:
        return Capabilities(tool_calling=True, system_prompt=True, vision=True, usage_reporting=False,
                            seed=False, sampling_params=False)

    # -- episode binding -----------------------------------------------------------------------
    def begin_episode(self, benchmark: Any, case_id: str | None = None, solution: Any = None) -> None:
        """Select the solution for this benchmark. ``solution`` (a SolutionSpec) overrides the
        model's configured choice; otherwise options.solution is 'reference', 'noop' or a selftest name."""
        spec = benchmark.spec
        if solution is None:
            choice = self.cfg.options.get("solution", "reference")
            if choice == "noop":
                from aibench.core.spec import SolutionSpec

                solution = SolutionSpec(kind="noop")
            else:
                cands = [t for t in spec.selftest if t.name == choice] or (
                    [t for t in spec.selftest if t.expect.passed] if choice == "reference" else [])
                if not cands:
                    raise ValueError(f"benchmark {spec.id} has no selftest solution {choice!r}")
                solution = cands[0].solution
                self.solution_name = cands[0].name
        self._case = case_id
        self._turn = 0
        self._queue = []
        if spec.mode == "chat":
            if solution.kind == "responses":
                data = load_yaml(benchmark.resolve(solution.path))
                self._chat = {str(k): (v if isinstance(v, list) else [v]) for k, v in data.items()}
            else:
                self._chat = {}
            return
        self._queue = self._agent_script(benchmark, solution)

    def _agent_script(self, benchmark: Any, sol: Any) -> list[ModelResponse]:
        steps: list[tuple[str, dict[str, Any]] | str] = []
        if sol.kind == "overlay":
            root = benchmark.resolve(sol.path)
            for p in iter_files(root):
                rel = str(p.relative_to(root))
                if rel == DELETE_LIST:
                    for line in p.read_text().splitlines():
                        if line.strip():
                            steps.append(("run_command", {"command": f"rm -rf -- {json.dumps(line.strip())}"}))
                    continue
                steps.append(("write_file", {"path": rel, "content": p.read_text(encoding="utf-8")}))
            for cmd in sol.run_commands:
                steps.append(("run_command", {"command": cmd}))
            steps.append(self._report(benchmark, sol))
        elif sol.kind == "script":
            data = load_yaml(benchmark.resolve(sol.path))
            for st in data.get("steps", []):
                if "tool" in st:
                    steps.append((st["tool"], st.get("args", {})))
                elif "final" in st:
                    steps.append(str(st["final"]))
            if not steps or not isinstance(steps[-1], str):
                steps.append(self._report(benchmark, sol))
        elif sol.kind == "noop":
            steps.append(self._report(benchmark, sol) if sol.report else "")
        out = []
        for st in steps:
            if isinstance(st, str):
                out.append(ModelResponse(text=st, tool_calls=[], usage=Usage(), stop_reason="end_turn", latency_s=0.0))
            else:
                name, args = st
                out.append(ModelResponse(text="", tool_calls=[ToolCall(id=f"call_{uuid.uuid4().hex[:10]}", name=name,
                                                                        arguments=args)],
                                         usage=Usage(), stop_reason="tool_use", latency_s=0.0))
        return out

    @staticmethod
    def _report(benchmark: Any, sol: Any) -> str:
        if not sol.report:
            return "Done."
        try:
            p = benchmark.resolve(sol.report)
            if p.is_file():
                return p.read_text(encoding="utf-8")
        except ValueError:
            pass
        return sol.report

    # -- model interface -----------------------------------------------------------------------
    def complete(self, messages: list[Message], tools: list[ToolSpec] | None, max_output_tokens: int) -> ModelResponse:
        if self._chat or (self._case is not None and not self._queue):
            replies = self._chat.get(str(self._case), [])
            text = replies[self._turn] if self._turn < len(replies) else ""
            self._turn += 1
            return ModelResponse(text=text, tool_calls=[], usage=Usage(), stop_reason="end_turn", latency_s=0.0)
        if not self._queue:
            return ModelResponse(text="", tool_calls=[], usage=Usage(), stop_reason="end_turn", latency_s=0.0)
        return self._queue.pop(0)


def solution_files(root: Path) -> list[str]:
    return [str(p.relative_to(root)) for p in iter_files(root)]
