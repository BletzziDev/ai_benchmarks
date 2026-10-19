from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from aibench.core.config import load_config

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _isolated_results(tmp_path, monkeypatch):
    """Never write test runs into the repository's results/ directory."""
    monkeypatch.setenv("AIBENCH_RESULTS_DIR", str(tmp_path / "results"))


@pytest.fixture
def repo_cfg():
    return load_config(REPO)


@pytest.fixture
def tmp_suite(tmp_path):
    """A throwaway suite root with the real configs and an empty benchmarks/ directory."""
    root = tmp_path / "suite"
    shutil.copytree(REPO / "configs", root / "configs")
    (root / "benchmarks").mkdir()
    return root


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


MIN_DOC = "x" * 250  # contract requires non-trivial docs


def make_agent_benchmark(root: Path, bid: str = "bug_fixing/tiny", extra_yaml: str = "", selftest: str = "") -> Path:
    cat, name = bid.split("/")
    b = root / "benchmarks" / cat / name
    write(b / "PROMPT.md", "Fix add() so that add(2, 2) == 4.\n" + MIN_DOC)
    write(b / "EVAL.md", "Eval\n" + MIN_DOC)
    write(b / "README.md", "Readme\n" + MIN_DOC)
    write(b / "fixtures/workspace/calc.py", "def add(a, b):\n    return a - b\n")
    write(b / "tests/hidden/test_calc.py", "from calc import add\n\ndef test_add():\n    assert add(2, 2) == 4\n")
    write(b / "solution/calc.py", "def add(a, b):\n    return a + b\n")
    write(b / "benchmark.yaml", f"""
schema_version: 1
id: {bid}
name: tiny
version: 1.0.0
category: {cat}
difficulty: easy
description: tiny synthetic benchmark used by framework tests
mode: agent
environment:
  workspace: fixtures/workspace
  tools: [list_files, read_file, write_file, edit_file, search, run_command, ask_user]
limits: {{wall_clock_s: 120, max_turns: 20, max_tool_calls: 40, command_timeout_s: 30}}
evaluation:
  checks:
    - {{id: hidden, type: pytest, paths: [tests/hidden], timeout_s: 60}}
    - {{id: scope, type: diff_scope, allowed: ["calc.py"]}}
    - {{id: process, type: trace}}
scoring:
  pass_threshold: 70
  criteria:
    - {{id: correct, weight: 80, metric: hidden.pass_rate}}
    - {{id: scope, weight: 20, metric: scope.out_of_scope_files, transform: {{type: threshold, threshold: 0, invert: true}}}}
  critical_failures:
    - {{id: policy, when: "process.policy_violations > 0", effect: zero}}
{extra_yaml}
selftest:
  - name: reference
    solution: {{kind: overlay, path: solution, run_commands: ["python -m pytest -q"]}}
    expect: {{passed: true, min_score: 99}}
  - name: noop
    solution: {{kind: noop}}
    expect: {{passed: false, max_score: 25}}
{selftest}
""")
    return b
