"""Launcher that applies sandbox restrictions and then ``exec``s the real command.

Invoked by :class:`aibench.core.sandbox.LocalSandbox` as
``python -m aibench.core.sandbox_exec '<json>'``. Doing this in a separate process (instead of a
``preexec_fn``) keeps the harness free of fork-safety problems and makes the restrictions easy to
test in isolation.

Order matters: resource limits -> namespaces (needs root) -> drop privileges -> chdir -> exec.
"""

from __future__ import annotations

import json
import os
import resource
import sys


def main() -> None:
    cfg = json.loads(sys.argv[1])
    limits = cfg.get("limits", {})
    mb = 1024 * 1024
    if limits.get("memory_mb"):
        v = limits["memory_mb"] * mb
        resource.setrlimit(resource.RLIMIT_AS, (v, v))
    if limits.get("cpu_seconds"):
        v = int(limits["cpu_seconds"])
        resource.setrlimit(resource.RLIMIT_CPU, (v, v + 5))
    if limits.get("max_file_mb"):
        v = limits["max_file_mb"] * mb
        resource.setrlimit(resource.RLIMIT_FSIZE, (v, v))
    if limits.get("max_processes"):
        v = int(limits["max_processes"])
        resource.setrlimit(resource.RLIMIT_NPROC, (v, v))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    if cfg.get("isolate_network") and hasattr(os, "unshare"):
        try:
            os.unshare(os.CLONE_NEWNET)
        except OSError as e:  # not permitted: report and continue only if allowed
            if cfg.get("require_network_isolation"):
                sys.stderr.write(f"aibench sandbox: network isolation unavailable: {e}\n")
                os._exit(97)

    uid, gid = cfg.get("uid"), cfg.get("gid")
    if uid is not None and os.geteuid() == 0:
        os.setgroups([])
        os.setgid(gid)
        os.setuid(uid)
        if os.geteuid() == 0:
            os._exit(98)

    os.chdir(cfg["cwd"])
    os.umask(0o022)
    env = cfg["env"]
    argv = cfg["argv"]
    try:
        os.execvpe(argv[0], argv, env)
    except OSError as e:
        sys.stderr.write(f"aibench sandbox: cannot exec {argv[0]!r}: {e}\n")
        os._exit(127)


if __name__ == "__main__":
    main()
