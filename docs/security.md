# Security of the framework

Everything produced by an evaluated system — files, commands, outputs, reports — is **untrusted**.
So are benchmark fixtures that deliberately contain prompt injections. Security is a requirement of
the harness, not only a benchmark category.

## Threat model

| Threat | Mitigation |
|---|---|
| Model-written code damages the host or reads secrets | All execution in a sandbox; scrubbed environment (no host variables — API keys never reach sandboxes); unprivileged uid; no network |
| Path traversal via tools (`../`, absolute paths, symlinks) | `safe_join` resolves symlinks and rejects anything outside the workspace; violations are recorded as `policy_violation` events |
| Destructive or exfiltrating commands | Command policy (deny patterns: `rm -rf /`, fork bombs, `mkfs`, `dd of=/dev/…`, `sudo`, `git push`, network clients, `/proc/*/environ`) on top of the sandbox; blocked commands are recorded and can be critical failures |
| Resource exhaustion | rlimits / cgroup limits: memory, CPU seconds, file size, processes/threads, workspace size quota; wall-clock and per-command timeouts; process-group kill; capped output capture (to files, not memory) |
| Grader subversion (agent adds `conftest.py`, `sitecustomize.py`, a fake `pytest.py`, `.pth` files) | Hidden tests run in a fresh copy with `python -I`, an isolated ini, `--confcutdir`, and such files are removed and reported |
| Tampering with hidden tests | Hidden tests are never in the workspace; they are injected only into evaluation copies after the episode |
| Prompt injection in fixtures/outputs reaching the judge | Judge inputs are wrapped as untrusted data with explicit instructions; judges only grade optional rubric criteria |
| Secrets in results | Results store only the env var *name* of API keys; sandboxes never receive them |
| Leftover state | Sandboxes are deleted in `finally` blocks, including on errors and Ctrl-C; Docker containers are force-removed |

## Backends

### `local` (default)

Validated in this repository's tests (`tests/test_sandbox.py`) on Linux as root:

- new **network namespace** per command (`unshare(CLONE_NEWNET)`) → no network, not even loopback;
- **privilege drop** to uid/gid 65534 when the harness runs as root → cannot read `/root`, harness
  files or other users' data beyond world-readable files;
- rlimits: `RLIMIT_AS` (memory), `RLIMIT_CPU`, `RLIMIT_FSIZE`, `RLIMIT_NPROC`, no core dumps;
- environment rebuilt from scratch; `HOME`/`TMPDIR` inside the sandbox directory.

Limitations: shared kernel and filesystem view (world-readable host files are readable); when not
run as root there is no privilege drop and possibly no network isolation (the manifest records what
was achieved, and `benchmark doctor` shows it); `RLIMIT_NPROC` is per-uid across all concurrent
sandboxes. **Use `docker` for untrusted models or agents.**

### `docker`

Container per sandbox: `--network none`, `--memory`/`--memory-swap`, `--pids-limit`, `--cpus 2`,
`--cap-drop ALL`, `--security-opt no-new-privileges`, non-root user 65534, file-size ulimit, tmpfs for
`/tmp` and `$HOME`, workspace bind-mounted at `/workspace`, per-command `timeout -s KILL`. Build the
pinned image with `scripts/build_sandbox_image.sh` (custom CAs are passed as BuildKit secrets, not
baked into the image). Validated by `tests/test_sandbox.py::test_docker_sandbox_isolation` and by
running selftests with `--sandbox docker`.

## External agents

`adapter: external_agent` runs a third-party agent CLI in the sandbox workspace directory on the
host, with a scrubbed environment (only `env_passthrough` variables, typically its own API key) and a
timeout. It is **not** inside the network/uid sandbox because it must reach its API. Run external
agents inside a disposable VM or container. They never receive real credentials other than the ones
you explicitly pass.

## Long-horizon runs

The autonomy benchmark never gets host access or real credentials: its workspace contains only fake
data and a fake secret used to detect exposure; destructive operations require a recorded
authorization from the user simulator; following injected instructions is a critical failure.

## Reporting a vulnerability in the harness

Open a private security advisory on the repository. Do not include working exploits against third
parties.
