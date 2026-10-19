"""Isolated execution environments for model-produced code.

Everything a model writes is untrusted. Every command — whether requested by the agent through
``run_command`` or executed by a grader to test the agent's code — goes through a ``Sandbox``.

Backends
--------
``local``  : a private temp directory per sandbox; commands run through ``sandbox_exec`` with
             rlimits (memory, CPU, file size, processes), a scrubbed environment (no host secrets),
             a new network namespace (no network) when the kernel allows it, and — when the harness
             runs as root — an unprivileged uid. Process groups are killed on timeout.
``docker`` : a long-lived container per sandbox with ``--network none``, memory/CPU/pids limits,
             ``--cap-drop ALL``, ``no-new-privileges`` and a non-root user; the workspace is
             bind-mounted at ``/workspace``.

The local backend is not a security boundary against a determined attacker (shared kernel, shared
filesystem view outside the workspace). Use ``docker`` for untrusted models; see docs/security.md.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aibench.core.config import SandboxConfig
from aibench.core.spec import SandboxSpec
from aibench.core.util import dir_size_bytes

BASE_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


@dataclass
class CommandResult:
    command: str
    exit_code: int | None
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False
    truncated: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and self.error is None

    def summary(self) -> dict[str, Any]:
        return {
            "command": self.command, "exit_code": self.exit_code, "duration_s": round(self.duration_s, 3),
            "timed_out": self.timed_out, "truncated": self.truncated, "error": self.error,
        }


@dataclass
class SandboxInfo:
    backend: str
    network_isolated: bool
    privileges_dropped: bool
    limits: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


class Sandbox(ABC):
    """A directory plus a way to run commands against it under restrictions."""

    backend_name = "abstract"

    def __init__(self, spec: SandboxSpec, cfg: SandboxConfig, env: dict[str, str] | None = None):
        self.spec = spec
        self.cfg = cfg
        self.extra_env = dict(env or {})
        self.base = Path(tempfile.mkdtemp(prefix="aibench-"))
        self.root = self.base / "workspace"
        self.home = self.base / "home"
        self.tmp = self.base / "tmp"
        self.bin = self.base / "bin"
        for d in (self.root, self.home, self.tmp, self.bin):
            d.mkdir()
        # Stable interpreter names regardless of how the host names its Python.
        for name in ("python", "python3"):
            (self.bin / name).symlink_to(sys.executable)
        for tool in ("pytest",):
            w = self.bin / tool
            w.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m {tool} "$@"\n')
            w.chmod(0o755)
        self._closed = False

    # -- lifecycle -----------------------------------------------------------------------------
    def start(self) -> None:
        """Called after the workspace has been populated."""

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        shutil.rmtree(self.base, ignore_errors=True)

    def __enter__(self) -> "Sandbox":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- execution -----------------------------------------------------------------------------
    @abstractmethod
    def run(self, command: str, timeout_s: float, cwd: str = ".", stdin: str | None = None,
            env: dict[str, str] | None = None) -> CommandResult: ...

    @property
    @abstractmethod
    def info(self) -> SandboxInfo: ...

    @property
    @abstractmethod
    def workspace_path_for_commands(self) -> str:
        """How the workspace is addressed inside commands (host path or /workspace)."""

    def workspace_mb(self) -> float:
        return dir_size_bytes(self.root) / (1024 * 1024)

    def sandbox_env(self, home: str, tmp: str, workspace: str) -> dict[str, str]:
        env = {
            "PATH": f"{self.bin}:{BASE_PATH}" if self.backend_name == "local" else BASE_PATH,
            "HOME": home,
            "TMPDIR": tmp,
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TERM": "dumb",
            "CI": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "PIP_NO_INPUT": "1",
            "WORKSPACE": workspace,
        }
        env.update(self.extra_env)
        return env


def _read_capped(path: Path, limit: int) -> tuple[str, bool]:
    size = path.stat().st_size if path.exists() else 0
    with open(path, "rb") as f:
        data = f.read(limit + 1)
    text = data[:limit].decode("utf-8", errors="replace")
    return text, size > limit


class LocalSandbox(Sandbox):
    backend_name = "local"

    def __init__(self, spec: SandboxSpec, cfg: SandboxConfig, env: dict[str, str] | None = None,
                 max_output_chars: int = 2_000_000):
        super().__init__(spec, cfg, env)
        self.max_output_chars = max_output_chars
        self._drop = os.geteuid() == 0
        self._netns = (not spec.network) and cfg.isolate_network and _netns_available()
        self._uid = cfg.drop_privileges_uid if self._drop else None
        self._gid = cfg.drop_privileges_gid if self._drop else None
        # The unprivileged user must be able to traverse the base directory.
        os.chmod(self.base, 0o755)

    def start(self) -> None:
        if self._drop:
            _chown_tree(self.base, self._uid, self._gid)

    @property
    def workspace_path_for_commands(self) -> str:
        return str(self.root)

    @property
    def info(self) -> SandboxInfo:
        notes = []
        if not self._netns and not self.spec.network:
            notes.append("network namespace unavailable: commands may reach the network")
        if not self._drop:
            notes.append("harness not running as root: commands run as the harness user")
        return SandboxInfo(
            backend="local", network_isolated=self._netns, privileges_dropped=self._drop,
            limits=self.spec.model_dump(), notes=notes,
        )

    def run(self, command: str, timeout_s: float, cwd: str = ".", stdin: str | None = None,
            env: dict[str, str] | None = None) -> CommandResult:
        from aibench.core.util import safe_join

        try:
            workdir = safe_join(self.root, cwd)
        except ValueError as e:
            return CommandResult(command, None, "", str(e), 0.0, error="invalid_cwd")
        senv = self.sandbox_env(str(self.home), str(self.tmp), str(self.root))
        if env:
            senv.update(env)
        cfg = {
            "argv": ["bash", "-c", command],
            "cwd": str(workdir),
            "env": senv,
            "uid": self._uid,
            "gid": self._gid,
            "isolate_network": self._netns,
            "require_network_isolation": False,
            "limits": {
                "memory_mb": self.spec.memory_mb,
                "cpu_seconds": self.spec.cpu_seconds,
                "max_file_mb": self.spec.max_file_mb,
                "max_processes": self.spec.max_processes,
            },
        }
        out_path = self.base / f".out-{uuid.uuid4().hex}"
        err_path = self.base / f".err-{uuid.uuid4().hex}"
        launcher_env = {"PATH": BASE_PATH, "PYTHONPATH": str(Path(__file__).resolve().parents[2])}
        start = time.monotonic()
        timed_out = False
        with open(out_path, "wb") as out_f, open(err_path, "wb") as err_f:
            try:
                proc = subprocess.Popen(
                    [sys.executable, "-I", "-c",
                     "import sys; sys.path.insert(0, sys.argv[2]); from aibench.core.sandbox_exec import main; "
                     "sys.argv = sys.argv[:2]; main()",
                     json.dumps(cfg), launcher_env["PYTHONPATH"]],
                    stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                    stdout=out_f, stderr=err_f, start_new_session=True, env=launcher_env,
                )
            except OSError as e:
                return CommandResult(command, None, "", str(e), 0.0, error="spawn_failed")
            try:
                proc.communicate(input=stdin.encode() if stdin is not None else None, timeout=timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_group(proc.pid)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
            finally:
                _kill_group(proc.pid)  # reap stragglers that kept running in the background
        duration = time.monotonic() - start
        stdout, t1 = _read_capped(out_path, self.max_output_chars)
        stderr, t2 = _read_capped(err_path, self.max_output_chars)
        for p in (out_path, err_path):
            p.unlink(missing_ok=True)
        err = None
        if self.workspace_mb() > self.spec.max_workspace_mb:
            err = "workspace_quota_exceeded"
        return CommandResult(command, None if timed_out else proc.returncode, stdout, stderr, duration,
                             timed_out=timed_out, truncated=t1 or t2, error=err)


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def _chown_tree(root: Path, uid: int | None, gid: int | None) -> None:
    if uid is None:
        return
    for dirpath, dirnames, filenames in os.walk(root):
        os.chown(dirpath, uid, gid, follow_symlinks=False)
        for n in dirnames + filenames:
            try:
                os.chown(os.path.join(dirpath, n), uid, gid, follow_symlinks=False)
            except OSError:
                pass


_NETNS: bool | None = None


def _netns_available() -> bool:
    global _NETNS
    if _NETNS is None:
        if not hasattr(os, "unshare") or os.geteuid() != 0:
            _NETNS = False
        else:
            r = subprocess.run(
                [sys.executable, "-c", "import os; os.unshare(os.CLONE_NEWNET)"], capture_output=True, timeout=20
            )
            _NETNS = r.returncode == 0
    return _NETNS


class DockerSandbox(Sandbox):
    """One container per sandbox; commands are executed with ``docker exec``."""

    backend_name = "docker"

    def __init__(self, spec: SandboxSpec, cfg: SandboxConfig, env: dict[str, str] | None = None,
                 max_output_chars: int = 2_000_000, image: str | None = None):
        super().__init__(spec, cfg, env)
        self.image = image or cfg.docker_image
        self.max_output_chars = max_output_chars
        self.container: str | None = None
        os.chmod(self.base, 0o755)

    @property
    def workspace_path_for_commands(self) -> str:
        return "/workspace"

    def start(self) -> None:
        if os.geteuid() == 0:
            _chown_tree(self.base, self.cfg.drop_privileges_uid, self.cfg.drop_privileges_gid)
        name = f"aibench-{uuid.uuid4().hex[:12]}"
        senv = self.sandbox_env("/home/sandbox", "/tmp", "/workspace")
        args = [
            "docker", "run", "-d", "--rm", "--name", name,
            "--network", "bridge" if self.spec.network else "none",
            "--memory", f"{self.spec.memory_mb}m", "--memory-swap", f"{self.spec.memory_mb}m",
            "--pids-limit", str(self.spec.max_processes), "--cpus", "2",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--user", f"{self.cfg.drop_privileges_uid}:{self.cfg.drop_privileges_gid}",
            "--ulimit", f"fsize={self.spec.max_file_mb * 1024 * 1024}",
            "--tmpfs", "/tmp:rw,size=256m", "--tmpfs", "/home/sandbox:rw,size=64m",
            "-v", f"{self.root}:/workspace", "-w", "/workspace",
        ]
        for k, v in senv.items():
            args += ["-e", f"{k}={v}"]
        args += [self.image, "sleep", "infinity"]
        r = subprocess.run(args, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"docker run failed: {r.stderr.strip()}")
        self.container = name

    def close(self) -> None:
        if self.container:
            subprocess.run(["docker", "rm", "-f", self.container], capture_output=True, timeout=60)
            self.container = None
        if self.base.exists() and os.geteuid() == 0:
            _chown_tree(self.base, 0, 0)
        super().close()

    @property
    def info(self) -> SandboxInfo:
        return SandboxInfo(backend="docker", network_isolated=not self.spec.network, privileges_dropped=True,
                           limits=self.spec.model_dump(), notes=[f"image={self.image}"])

    def run(self, command: str, timeout_s: float, cwd: str = ".", stdin: str | None = None,
            env: dict[str, str] | None = None) -> CommandResult:
        from aibench.core.util import safe_join

        if not self.container:
            return CommandResult(command, None, "", "sandbox not started", 0.0, error="not_started")
        try:
            rel = safe_join(self.root, cwd).relative_to(self.root.resolve())
        except ValueError as e:
            return CommandResult(command, None, "", str(e), 0.0, error="invalid_cwd")
        args = ["docker", "exec", "-i" if stdin is not None else "-t=false", "-w", f"/workspace/{rel}"]
        args = [a for a in args if a != "-t=false"]
        for k, v in (env or {}).items():
            args += ["-e", f"{k}={v}"]
        t = max(1, int(timeout_s))
        args += [self.container, "timeout", "-s", "KILL", str(t), "bash", "-c", command]
        start = time.monotonic()
        try:
            r = subprocess.run(args, input=stdin.encode() if stdin is not None else None,
                               capture_output=True, timeout=timeout_s + 30)
        except subprocess.TimeoutExpired:
            return CommandResult(command, None, "", "", time.monotonic() - start, timed_out=True)
        duration = time.monotonic() - start
        timed_out = r.returncode in (124, 137) and duration >= t - 0.5
        out = r.stdout.decode("utf-8", "replace")
        errs = r.stderr.decode("utf-8", "replace")
        trunc = len(out) > self.max_output_chars or len(errs) > self.max_output_chars
        err = "workspace_quota_exceeded" if self.workspace_mb() > self.spec.max_workspace_mb else None
        return CommandResult(command, None if timed_out else r.returncode, out[: self.max_output_chars],
                             errs[: self.max_output_chars], duration, timed_out=timed_out, truncated=trunc, error=err)


def docker_available() -> bool:
    if not shutil.which("docker"):
        return False
    r = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, timeout=20)
    return r.returncode == 0


def make_sandbox(backend: str, spec: SandboxSpec, cfg: SandboxConfig, env: dict[str, str] | None = None,
                 max_output_chars: int = 2_000_000) -> Sandbox:
    if backend == "local":
        return LocalSandbox(spec, cfg, env, max_output_chars=max_output_chars)
    if backend == "docker":
        return DockerSandbox(spec, cfg, env, max_output_chars=max_output_chars)
    raise ValueError(f"unknown sandbox backend {backend!r}")
