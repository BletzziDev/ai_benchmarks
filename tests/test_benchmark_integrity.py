"""Suite-level integrity: ground truth is verifiable, and every benchmark's grader discriminates."""

import subprocess
import sys

import pytest

from aibench.core.config import load_config
from aibench.core.registry import Registry
from conftest import REPO

CFG = load_config(REPO)
REG = Registry.discover(CFG.benchmarks_dir, set(CFG.suite.categories))
VERIFIERS = sorted(REG.root.rglob("tests/verify_ground_truth.py"))


@pytest.mark.parametrize("script", VERIFIERS, ids=[str(p.parent.parent.relative_to(REG.root)) for p in VERIFIERS])
def test_ground_truth_verifies_by_execution(script):
    r = subprocess.run([sys.executable, str(script)], cwd=script.parent.parent, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]


@pytest.mark.slow
@pytest.mark.parametrize("bench_id", sorted(REG.benchmarks))
def test_selftests_behave_as_declared(bench_id, repo_cfg):
    from aibench.core.selftest import run_selftests

    outs = run_selftests(repo_cfg, REG, [REG.get(bench_id)])
    bad = [f"{o.case}: {'; '.join(o.problems)}" for o in outs if not o.ok]
    assert outs and not bad, bad
