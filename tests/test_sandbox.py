import os
import socket

import pytest

from aibench.core.config import SandboxConfig
from aibench.core.sandbox import DockerSandbox, LocalSandbox, _netns_available, docker_available
from aibench.core.spec import SandboxSpec
from aibench.core.util import PathEscapeError, safe_join


@pytest.fixture
def sb():
    s = LocalSandbox(SandboxSpec(memory_mb=512, cpu_seconds=30), SandboxConfig())
    s.start()
    yield s
    s.close()


def test_environment_is_scrubbed(sb, monkeypatch):
    monkeypatch.setenv("AIBENCH_TEST_SECRET", "s3cr3t")
    r = sb.run("env", timeout_s=10)
    assert r.ok and "s3cr3t" not in r.stdout and "AIBENCH_TEST_SECRET" not in r.stdout
    assert "PYTHONHASHSEED=0" in r.stdout


def test_timeout_kills_process_group(sb):
    r = sb.run("sleep 30 & sleep 30; echo never", timeout_s=1)
    assert r.timed_out and r.exit_code is None and "never" not in r.stdout


def test_memory_limit(sb):
    r = sb.run("python -c 'x = bytearray(900 * 1024 * 1024)'", timeout_s=20)
    assert r.exit_code != 0 and "MemoryError" in r.stderr


def test_output_is_capped():
    s = LocalSandbox(SandboxSpec(), SandboxConfig(), max_output_chars=1000)
    s.start()
    try:
        r = s.run("python -c 'print(\"x\" * 50000)'", timeout_s=20)
        assert r.truncated and len(r.stdout) == 1000
    finally:
        s.close()


@pytest.mark.skipif(not _netns_available(), reason="network namespaces unavailable")
def test_network_is_isolated(sb):
    r = sb.run("python -c \"import socket; socket.create_connection(('1.1.1.1', 80), timeout=3)\"", timeout_s=20)
    assert r.exit_code != 0
    assert sb.info.network_isolated


@pytest.mark.skipif(os.geteuid() != 0, reason="privilege drop only applies when running as root")
def test_privileges_dropped(sb):
    r = sb.run("id -u; cat /root/.bashrc", timeout_s=10)
    assert r.stdout.split()[0] == "65534"
    assert "Permission denied" in r.stderr


def test_cleanup_removes_directory():
    s = LocalSandbox(SandboxSpec(), SandboxConfig())
    s.start()
    base = s.base
    s.close()
    assert not base.exists()


def test_safe_join_rejects_escapes(tmp_path):
    (tmp_path / "ws").mkdir()
    os.symlink("/etc", tmp_path / "ws" / "link")
    assert safe_join(tmp_path / "ws", "/workspace/a.txt") == (tmp_path / "ws" / "a.txt").resolve()
    for bad in ["../x", "/etc/passwd", "link/passwd", "a/../../x"]:
        with pytest.raises(PathEscapeError):
            safe_join(tmp_path / "ws", bad)


@pytest.mark.docker
@pytest.mark.skipif(not docker_available(), reason="docker daemon unavailable")
def test_docker_sandbox_isolation():
    s = DockerSandbox(SandboxSpec(memory_mb=256), SandboxConfig(docker_image=os.environ.get("AIBENCH_DOCKER_IMAGE", "aibench-sandbox:0.1")))
    try:
        try:
            s.start()
        except RuntimeError as e:
            pytest.skip(f"sandbox image not available: {e}")
        (s.root / "hello.txt").write_text("hi\n")
        r = s.run("cat hello.txt && id -u && python -c 'import pytest; print(pytest.__version__)'", timeout_s=60)
        assert r.ok, r.stderr
        assert r.stdout.splitlines()[:2] == ["hi", "65534"]
        r = s.run("python -c \"import socket; socket.create_connection(('1.1.1.1', 80), timeout=3)\"", timeout_s=30)
        assert r.exit_code != 0
        r = s.run("sleep 20", timeout_s=2)
        assert r.timed_out
    finally:
        s.close()
