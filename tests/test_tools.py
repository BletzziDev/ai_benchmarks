import os

import pytest

from aibench.adapters.base import ToolCall
from aibench.core.config import SandboxConfig, load_config
from aibench.core.sandbox import LocalSandbox
from aibench.core.spec import FaultSpec, SandboxSpec
from aibench.core.tools import TOOL_SPECS, ToolExecutor, UserSimulator
from aibench.core.trace import Trace


@pytest.fixture
def ex(tmp_path, repo_cfg):
    sb = LocalSandbox(SandboxSpec(), SandboxConfig())
    (sb.root / "src").mkdir()
    (sb.root / "src" / "a.py").write_text("x = 1\ny = 2\n")
    sb.start()
    rules = tmp_path / "user.yaml"
    rules.write_text("default_reply: no idea\nrules:\n  - id: ok_delete\n    match: ['delete', 'cache']\n"
                     "    reply: yes, delete the cache\n    grants: [delete_cache]\n")
    trace = Trace(tmp_path / "trace.jsonl")
    e = ToolExecutor(sb, trace, list(TOOL_SPECS), 10, repo_cfg.suite.command_policy.deny_patterns, 500,
                     faults=[FaultSpec(tool="run_command", match="pytest", times=1, message="flaky")],
                     user_simulator=UserSimulator(rules))
    yield e
    sb.close()


def call(e, name, **args):
    return e.execute(ToolCall(id="c", name=name, arguments=args))


def test_read_write_edit_search(ex):
    out, err = call(ex, "read_file", path="src/a.py")
    assert not err and "x = 1" in out
    assert call(ex, "edit_file", path="src/a.py", old_text="y = 2", new_text="y = 3")[1] is False
    assert call(ex, "write_file", path="/workspace/new/b.txt", content="hello")[1] is False
    out, _ = call(ex, "search", pattern=r"y = \d")
    assert "src/a.py:2:y = 3" in out
    out, _ = call(ex, "run_command", command="cat new/b.txt")
    assert "hello" in out


def test_path_escape_is_blocked_and_recorded(ex):
    out, err = call(ex, "read_file", path="../../etc/passwd")
    assert err and "escapes" in out
    os.symlink("/etc", ex.sb.root / "evil")
    out, err = call(ex, "write_file", path="evil/x", content="pwn")
    assert err
    assert ex.trace.totals.policy_violations == 2


def test_command_policy_denies(ex):
    out, err = call(ex, "run_command", command="git push origin main")
    assert err and "blocked" in out
    out, err = call(ex, "run_command", command="rm -rf /")
    assert err and "blocked" in out


def test_fault_injection_then_recovery(ex):
    out, err = call(ex, "run_command", command="python -m pytest -q")
    assert err and "flaky" in out
    out, err = call(ex, "run_command", command="python -m pytest -q")
    assert "flaky" not in out  # injected only once
    assert ex.trace.totals.faults_injected == 1


def test_user_simulator_rules_and_grants(ex):
    out, _ = call(ex, "ask_user", question="May I delete the cache directory?")
    assert out == "yes, delete the cache"
    out, _ = call(ex, "ask_user", question="What is the meaning of life?")
    assert out == "no idea"
    asks = [e for e in ex.trace.events if e["type"] == "ask_user"]
    assert asks[0]["grants"] == ["delete_cache"] and asks[1]["rule"] is None


def test_output_truncated_for_model(ex):
    out, _ = call(ex, "run_command", command="python -c 'print(\"z\" * 5000)'")
    assert "characters omitted by harness" in out and len(out) < 1000


def test_unknown_tool_and_bad_args(ex):
    assert call(ex, "launch_missiles")[1] is True
    assert call(ex, "read_file", wrong="x")[1] is True
