from aibench.core.config import load_config
from aibench.core.registry import Registry, validate_contract
from conftest import make_agent_benchmark, write


def test_repository_benchmarks_are_valid(repo_cfg):
    reg = Registry.discover(repo_cfg.benchmarks_dir, set(repo_cfg.suite.categories))
    assert not reg.load_errors, reg.load_errors
    assert len(reg.all()) >= 2
    errors = [i for b in reg.all() for i in validate_contract(b) if i.level == "error"]
    assert not errors, [f"{e.benchmark}: {e.message}" for e in errors]


def test_lookup_by_short_name(tmp_suite):
    make_agent_benchmark(tmp_suite)
    cfg = load_config(tmp_suite)
    reg = Registry.discover(cfg.benchmarks_dir, set(cfg.suite.categories))
    assert reg.get("tiny").id == "bug_fixing/tiny"
    assert reg.get("bug_fixing/tiny").content_hash


def test_contract_violations_are_reported(tmp_suite):
    b = make_agent_benchmark(tmp_suite)
    write(b / "fixtures/workspace/hidden/leak.py", "x = 1")
    write(b / "fixtures/workspace/notes.txt", "CANARY-123")
    (b / "EVAL.md").unlink()
    text = (b / "benchmark.yaml").read_text().replace("schema_version: 1", "schema_version: 1\nleak_canaries: [CANARY-123]")
    (b / "benchmark.yaml").write_text(text)
    cfg = load_config(tmp_suite)
    reg = Registry.discover(cfg.benchmarks_dir, set(cfg.suite.categories))
    msgs = [i.message for i in validate_contract(reg.get("tiny"))]
    assert any("EVAL.md" in m for m in msgs)
    assert any("'hidden' path" in m for m in msgs)
    assert any("leak canary" in m for m in msgs)


def test_invalid_spec_is_a_load_error(tmp_suite):
    b = make_agent_benchmark(tmp_suite)
    (b / "benchmark.yaml").write_text((b / "benchmark.yaml").read_text().replace("metric: hidden.pass_rate", "metric: nocheck.x"))
    cfg = load_config(tmp_suite)
    reg = Registry.discover(cfg.benchmarks_dir, set(cfg.suite.categories))
    assert reg.load_errors and "unknown check" in reg.load_errors[0].message
