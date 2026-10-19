"""Central executor: plan -> prepare isolated environment -> run model/agent -> evaluate -> score -> store.

Guarantees:
- every sandbox is closed in ``finally`` blocks, including on errors and Ctrl-C;
- infrastructure failures (provider outages, harness errors) are retried per the benchmark's
  ``repetition.infra_retries`` and, if they persist, recorded as ``infra_error`` and excluded from
  scores (but reported in completion/error rates) — they are never silently counted as model failures;
- runs are resumable: completed attempts are skipped, interrupted ones are redone from scratch.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aibench import HARNESS_VERSION
from aibench.adapters import create_adapter
from aibench.adapters.base import AgentAdapter, ModelAdapter
from aibench.core.agent_loop import run_agent_episode, run_chat_case, run_external_agent
from aibench.core.artifacts import RunStore, StructuredLog, git_commit, new_run_id, now_iso, tool_versions
from aibench.core.checks.base import GradingContext
from aibench.core.checks.builtin import tree_diff, DEFAULT_IGNORE
from aibench.core.config import Config
from aibench.core.evaluator import run_checks
from aibench.core.judge import JudgePanel
from aibench.core.registry import Registry
from aibench.core.sandbox import Sandbox, make_sandbox
from aibench.core.scoring import flatten_metrics, score_attempt
from aibench.core.spec import LoadedBenchmark, SolutionSpec
from aibench.core.tools import ToolExecutor, UserSimulator
from aibench.core.trace import Trace, load_trace
from aibench.core.util import copy_tree, dir_size_bytes, load_yaml, read_json, safe_join, sha256_file, write_json


@dataclass
class AttemptOutcome:
    bench_id: str
    attempt: int
    state: str
    score: float | None
    passed: bool | None
    critical: list[str]
    error: str | None = None


def system_kind(adapter: ModelAdapter | AgentAdapter) -> str:
    return getattr(adapter, "kind", "model")


def render_prompt(template: str, case: dict[str, Any]) -> str:
    out = template.replace("{{input}}", str(case.get("input", "")))
    for k, v in case.items():
        if isinstance(v, (str, int, float)):
            out = out.replace("{{" + k + "}}", str(v))
    return out


def load_cases(bench: LoadedBenchmark) -> list[dict[str, Any]]:
    data = load_yaml(bench.resolve(bench.spec.cases.file))  # type: ignore[union-attr]
    cases = data.get("cases", data) if isinstance(data, dict) else data
    if not isinstance(cases, list) or not all(isinstance(c, dict) and "id" in c for c in cases):
        raise ValueError(f"{bench.id}: cases file must be a list of mappings with 'id'")
    ids = [str(c["id"]) for c in cases]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{bench.id}: duplicate case ids")
    return cases


def prepare_workspace(bench: LoadedBenchmark, dest: Path) -> None:
    env = bench.spec.environment
    if env.workspace:
        copy_tree(bench.resolve(env.workspace), dest)
    for src, dst in env.overlays.items():
        s = bench.resolve(src)
        target = safe_join(dest, dst)
        if s.is_dir():
            copy_tree(s, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, target)
    if env.git_init:
        cmds = [["git", "init", "-q", "-b", "main"], ["git", "add", "-A"],
                ["git", "-c", "user.name=aibench", "-c", "user.email=aibench@localhost", "-c", "commit.gpgsign=false",
                 "commit", "-q", "--allow-empty", "-m", "Initial state of the benchmark workspace"]]
        for c in cmds:
            subprocess.run(c, cwd=dest, check=True, capture_output=True, timeout=60,
                           env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(dest.parent), "GIT_CONFIG_NOSYSTEM": "1"})


class Runner:
    def __init__(self, config: Config, registry: Registry, sandbox_backend: str | None = None,
                 judge_labels: list[str] | None = None, allow_self_judge: bool = False, echo: bool = True,
                 results_dir: Path | None = None):
        self.config = config
        self.results_dir = Path(results_dir) if results_dir else config.results_dir
        self.registry = registry
        self.backend = sandbox_backend or config.suite.sandbox.backend
        self.judge_labels = judge_labels or []
        self.allow_self_judge = allow_self_judge
        self.echo = echo
        self._judge: JudgePanel | None = None
        if self.judge_labels:
            judges = []
            for lbl in self.judge_labels:
                a = create_adapter(lbl, config.model(lbl))
                if not isinstance(a, ModelAdapter):
                    raise ValueError(f"judge {lbl} must be a model, not an agent")
                judges.append(a)
            self._judge = JudgePanel(judges, allow_self_judge=allow_self_judge)

    # ------------------------------------------------------------------ planning
    def create_run(self, benchmarks: list[LoadedBenchmark], model_label: str, attempts: int | None = None,
                   tier: str | None = None, run_id: str | None = None, extra: dict[str, Any] | None = None) -> RunStore:
        adapter = create_adapter(model_label, self.config.model(model_label))
        run_id = run_id or new_run_id(model_label)
        store = RunStore(self.results_dir, run_id)
        harness_files = {
            "agent_system_prompt": self.config.suite.harness.agent_system_prompt,
            "chat_system_prompt": self.config.suite.harness.chat_system_prompt,
        }
        probe = make_sandbox(self.backend, benchmarks[0].spec.environment.sandbox if benchmarks else
                             __import__("aibench.core.spec", fromlist=["SandboxSpec"]).SandboxSpec(), self.config.suite.sandbox)
        try:
            sandbox_info = probe.info.__dict__
        finally:
            probe.close()
        manifest = {
            "run_id": run_id, "created_at": now_iso(), "state": "planned", "harness_version": HARNESS_VERSION,
            "repo": git_commit(self.config.root), "tools": tool_versions(),
            "model": adapter.describe(), "system_kind": system_kind(adapter), "tier": tier,
            "sandbox": {"backend": self.backend, **sandbox_info},
            "judges": self.judge_labels, "allow_self_judge": self.allow_self_judge,
            "harness": {**self.config.suite.harness.model_dump(),
                        "file_hashes": {k: sha256_file(self.config.root / v) for k, v in harness_files.items()}},
            "command_policy": self.config.suite.command_policy.model_dump(),
            "benchmarks": [
                {"id": b.id, "version": b.spec.version, "category": b.spec.category, "mode": b.spec.mode,
                 "content_hash": b.content_hash, "tools": b.spec.environment.tools if b.spec.mode == "agent" else [],
                 "attempts": attempts or b.spec.repetition.attempts,
                 "limits": b.spec.limits_for(tier if tier in b.spec.budget_tiers else None).model_dump()}
                for b in benchmarks
            ],
            **(extra or {}),
        }
        store.write_manifest(manifest)
        return store

    # ------------------------------------------------------------------ execution
    def execute(self, store: RunStore, solution_override: dict[str, SolutionSpec] | None = None) -> list[AttemptOutcome]:
        manifest = store.manifest()
        log = store.log(echo=self.echo)
        label = manifest["model"]["label"]
        adapter = create_adapter(label, self.config.model(label))
        manifest["state"] = "running"
        manifest.setdefault("started_at", now_iso())
        store.write_manifest(manifest)
        outcomes: list[AttemptOutcome] = []
        tier = manifest.get("tier")
        try:
            for bmeta in manifest["benchmarks"]:
                bench = self.registry.get(bmeta["id"])
                if bench.content_hash != bmeta["content_hash"]:
                    log.warn("benchmark_changed_since_plan", benchmark=bench.id,
                             note="results will be recorded with the current content hash")
                for k in range(1, int(bmeta["attempts"]) + 1):
                    st = store.status(bench.id, k)
                    if st and st.get("state") in ("completed", "skipped", "infra_error"):
                        log.info("attempt_skip_existing", benchmark=bench.id, attempt=k, state=st["state"])
                        outcomes.append(self._outcome_from_disk(store, bench.id, k))
                        continue
                    adir = store.attempt_dir(bench.id, k)
                    if adir.exists():
                        shutil.rmtree(adir)  # interrupted/partial attempt: redo from scratch
                    sol = (solution_override or {}).get(bench.id)
                    outcomes.append(self._attempt_with_retries(store, bench, adapter, k, tier, sol, log))
            manifest = store.manifest()
            manifest["state"] = "completed"
        except KeyboardInterrupt:
            manifest = store.manifest()
            manifest["state"] = "interrupted"
            log.warn("run_interrupted", note="resume with `benchmark resume " + store.run_id + "`")
            raise
        finally:
            manifest["finished_at"] = now_iso()
            store.write_manifest(manifest)
        from aibench.core.reporting import write_summary

        write_summary(store, self.config, self.registry)
        return outcomes

    def _outcome_from_disk(self, store: RunStore, bench_id: str, k: int) -> AttemptOutcome:
        adir = store.attempt_dir(bench_id, k)
        st = read_json(adir / "status.json")
        sc = read_json(adir / "score.json") if (adir / "score.json").exists() else {}
        return AttemptOutcome(bench_id, k, st.get("state"), sc.get("score"), sc.get("passed"),
                              [c["id"] for c in sc.get("critical_failures", []) if c.get("triggered")], st.get("error"))

    def _attempt_with_retries(self, store: RunStore, bench: LoadedBenchmark, adapter: Any, k: int, tier: str | None,
                              solution: SolutionSpec | None, log: StructuredLog) -> AttemptOutcome:
        retries = bench.spec.repetition.infra_retries
        last: AttemptOutcome | None = None
        for r in range(retries + 1):
            adir = store.attempt_dir(bench.id, k)
            if adir.exists():
                shutil.rmtree(adir)
            last = self.run_attempt(store, bench, adapter, k, tier, solution, log, infra_try=r)
            if last.state != "infra_error":
                return last
            log.warn("infra_error_retry", benchmark=bench.id, attempt=k, try_=r + 1, error=last.error)
        assert last is not None
        return last

    def run_attempt(self, store: RunStore, bench: LoadedBenchmark, adapter: Any, k: int, tier: str | None,
                    solution: SolutionSpec | None, log: StructuredLog, infra_try: int = 0) -> AttemptOutcome:
        adir = store.attempt_dir(bench.id, k)
        adir.mkdir(parents=True, exist_ok=True)
        (adir / "artifacts").mkdir(exist_ok=True)
        store.set_status(bench.id, k, state="running", started_at=now_iso(), infra_try=infra_try)
        spec = bench.spec
        log.info("attempt_start", benchmark=bench.id, attempt=k, model=adapter.label)
        # Compatibility: refuse to run conditions the system cannot satisfy rather than scoring 0.
        incompatible = None
        if spec.mode == "chat" and isinstance(adapter, AgentAdapter):
            incompatible = "chat benchmarks require a model adapter (external agents need a workspace task)"
        if spec.mode == "agent" and isinstance(adapter, ModelAdapter) and not adapter.capabilities.tool_calling:
            incompatible = "agent benchmark requires tool calling"
        if "vision" in spec.requires and isinstance(adapter, ModelAdapter) and not adapter.capabilities.vision:
            incompatible = "benchmark requires vision input"
        if incompatible:
            store.set_status(bench.id, k, state="skipped", reason=incompatible, finished_at=now_iso())
            log.warn("attempt_skipped", benchmark=bench.id, reason=incompatible)
            return AttemptOutcome(bench.id, k, "skipped", None, None, [], incompatible)
        limits = spec.limits_for(tier if tier in spec.budget_tiers else None)
        trace = Trace(adir / "trace.jsonl")
        tmp_orig = Path(tempfile.mkdtemp(prefix="aibench-orig-"))
        sb: Sandbox | None = None
        episode: dict[str, Any] = {}
        try:
            if spec.mode == "chat":
                episode, case_results, final_text, transcript = self._run_chat(bench, adapter, limits, trace, adir, solution)
                final_ws = None
                original_ws = None
            else:
                sb = make_sandbox(self.backend, spec.environment.sandbox, self.config.suite.sandbox,
                                  max_output_chars=self.config.suite.harness.max_logged_output_chars)
                prepare_workspace(bench, sb.root)
                copy_tree(sb.root, tmp_orig)
                original_ws = tmp_orig
                sb.start()
                for cmd in spec.environment.setup:
                    r = sb.run(cmd, timeout_s=limits.command_timeout_s)
                    trace.emit("setup_command", **r.summary())
                    if not r.ok:
                        raise RuntimeError(f"setup command failed: {cmd}: {r.stderr[-500:]}")
                prompt = bench.resolve(spec.prompt).read_text(encoding="utf-8")
                (adir / "prompt.md").write_text(prompt, encoding="utf-8")
                if isinstance(adapter, AgentAdapter):
                    res = run_external_agent(adapter, prompt, sb.root, limits, trace)
                else:
                    adapter.begin_episode(bench, None, solution)
                    user_sim = UserSimulator(bench.resolve(spec.environment.user_simulator)
                                             if spec.environment.user_simulator else None)
                    executor = ToolExecutor(sb, trace, spec.environment.tools, limits.command_timeout_s,
                                            self.config.suite.command_policy.deny_patterns,
                                            self.config.suite.harness.max_tool_output_chars,
                                            faults=spec.environment.faults, user_simulator=user_sim)
                    system = (self.config.root / self.config.suite.harness.agent_system_prompt).read_text(encoding="utf-8")
                    resume = None
                    if spec.interruptions:
                        resume = bench.resolve(spec.interruptions.resume_prompt).read_text(encoding="utf-8")
                    res = run_agent_episode(adapter, executor, system, prompt, limits, trace,
                                            context_strategy=self.config.suite.harness.context_strategy,
                                            context_budget_tokens=self.config.suite.harness.context_budget_tokens,
                                            interruptions=spec.interruptions.after_tool_calls if spec.interruptions else None,
                                            resume_prompt=resume)
                episode = {"termination": res.termination, "error": res.error, "sessions": res.sessions}
                if res.infra_failure:
                    raise _InfraError(res.error or "model error")
                final_text = res.final_text
                transcript = [m.to_json() for m in res.messages]
                case_results = {}
                final_ws = adir / "final_workspace"
                self._snapshot(sb, final_ws, spec.environment.sandbox.max_workspace_mb, trace)
                d = tree_diff(original_ws, final_ws, DEFAULT_IGNORE)
                (adir / "workspace.diff").write_text(d["patch"], encoding="utf-8")
                sb.close()
                sb = None
            write_json(adir / "transcript.json", transcript)
            (adir / "final_message.md").write_text(final_text or "", encoding="utf-8")
            summary = trace.summary()
            trace.close()
            # ---------------- evaluation
            ctx = GradingContext(
                benchmark=bench, config=self.config, final_workspace=final_ws or adir, original_workspace=original_ws,
                final_text=final_text or "", transcript=transcript, trace_events=load_trace(adir / "trace.jsonl"),
                case_results=case_results, artifacts_dir=adir / "artifacts", sandbox_backend=self.backend,
                judge=self._judge, evaluated_model=adapter.label, episode=episode,
            )
            checks = run_checks(spec.evaluation.checks, ctx, log)
            write_json(adir / "evaluation.json", {"benchmark": bench.id, "version": spec.version,
                                                  "content_hash": bench.content_hash, "checks": checks,
                                                  "episode": episode, "usage": summary})
            sc = self.score(bench, adir)
            store.set_status(bench.id, k, state="completed", finished_at=now_iso(), termination=episode.get("termination"))
            log.info("attempt_done", benchmark=bench.id, attempt=k, score=sc["score"], passed=sc["passed"],
                     status=sc["status"], critical=[c["id"] for c in sc["critical_failures"] if c.get("triggered")])
            return AttemptOutcome(bench.id, k, "completed", sc["score"], sc["passed"],
                                  [c["id"] for c in sc["critical_failures"] if c.get("triggered")])
        except _InfraError as e:
            trace.close()
            store.set_status(bench.id, k, state="infra_error", error=str(e), finished_at=now_iso())
            log.error("attempt_infra_error", benchmark=bench.id, attempt=k, error=str(e))
            return AttemptOutcome(bench.id, k, "infra_error", None, None, [], str(e))
        except KeyboardInterrupt:
            trace.close()
            store.set_status(bench.id, k, state="interrupted", finished_at=now_iso())
            raise
        except Exception as e:
            trace.close()
            tb = traceback.format_exc()
            store.set_status(bench.id, k, state="infra_error", error=f"harness error: {e}", traceback=tb[-8000:],
                             finished_at=now_iso())
            log.error("attempt_harness_error", benchmark=bench.id, attempt=k, error=str(e))
            return AttemptOutcome(bench.id, k, "infra_error", None, None, [], f"harness error: {e}")
        finally:
            if sb is not None:
                sb.close()
            shutil.rmtree(tmp_orig, ignore_errors=True)

    def _snapshot(self, sb: Sandbox, dest: Path, max_mb: int, trace: Trace) -> None:
        """Preserve the final workspace for auditing; oversized workspaces keep only files <= 5 MB."""
        size_mb = dir_size_bytes(sb.root) / (1024 * 1024)
        copy_tree(sb.root, dest)
        shutil.rmtree(dest / ".git", ignore_errors=True)
        if size_mb > max_mb:
            dropped = []
            for p in sorted(dest.rglob("*")):
                if p.is_file() and p.stat().st_size > 5 * 1024 * 1024:
                    dropped.append(str(p.relative_to(dest)))
                    p.unlink()
            trace.emit("snapshot_truncated", size_mb=round(size_mb, 1), limit_mb=max_mb, dropped_files=dropped[:100])

    def _run_chat(self, bench: LoadedBenchmark, adapter: ModelAdapter, limits: Any, trace: Trace, adir: Path,
                  solution: SolutionSpec | None) -> tuple[dict[str, Any], dict[str, Any], str, list[Any]]:
        spec = bench.spec
        cases = load_cases(bench)
        template = bench.resolve(spec.prompt).read_text(encoding="utf-8")
        system = (self.config.root / self.config.suite.harness.chat_system_prompt).read_text(encoding="utf-8")
        results: dict[str, Any] = {}
        transcripts: dict[str, Any] = {}
        deadline = time.monotonic() + (limits.wall_clock_s or 10**9)
        errors = 0
        for case in cases:
            cid = str(case["id"])
            if time.monotonic() > deadline:
                results[cid] = {"case_id": cid, "replies": [], "termination": "wall_clock"}
                continue
            adapter.begin_episode(bench, cid, solution)
            turns = [render_prompt(template, case)] + [str(t) for t in case.get("followups", [])]
            images = []
            if case.get("images"):
                from aibench.adapters.base import ImagePart

                images = [ImagePart(str(bench.resolve(p))) for p in case["images"]]
            r = run_chat_case(adapter, system, turns, limits, trace, cid, images)
            results[cid] = {"case_id": cid, "replies": r.replies, "termination": r.termination, "error": r.error,
                            "user_turns": turns}
            transcripts[cid] = [m.to_json() for m in r.messages]
            if r.termination == "model_error":
                errors += 1
        if errors and errors == len(cases):
            raise _InfraError("model errors on every case")
        write_json(adir / "cases.json", results)
        episode = {"termination": "completed", "cases": len(cases), "case_errors": errors}
        return episode, results, "", [{"case_transcripts": transcripts}]

    # ------------------------------------------------------------------ scoring (re-runnable)
    def score(self, bench: LoadedBenchmark, adir: Path) -> dict[str, Any]:
        return score_from_disk(bench, adir)


def score_from_disk(bench: LoadedBenchmark, adir: Path) -> dict[str, Any]:
    """(Re)compute score.json from evaluation.json + optional human_grades.json. Idempotent."""
    ev = read_json(adir / "evaluation.json")
    metrics = flatten_metrics(ev["checks"])
    human = {}
    hp = adir / "human_grades.json"
    if hp.exists():
        human = read_json(hp)
        for key, g in human.items():
            metrics[key] = g["value"]
    # episode-level metrics usable in rules (e.g. episode.budget_exhausted)
    term = (ev.get("episode") or {}).get("termination")
    metrics["episode.completed"] = 1 if term == "completed" else 0
    sr = score_attempt(bench.spec.scoring, metrics).to_dict()
    sr["human_grades"] = human
    sr["benchmark"] = bench.id
    sr["version"] = bench.spec.version
    write_json(adir / "score.json", sr)
    return sr


class _InfraError(Exception):
    pass
