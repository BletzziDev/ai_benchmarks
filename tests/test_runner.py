import json
import os
import stat
import textwrap

import pytest

from aibench.cli import main
from aibench.core.artifacts import RunStore
from aibench.core.config import ModelConfig, load_config
from aibench.core.registry import Registry
from aibench.core.reporting import compare_runs, summarize
from aibench.core.runner import Runner
from aibench.core.selftest import run_selftests
from aibench.core.util import read_json, write_json
from conftest import make_agent_benchmark, write


def setup(tmp_suite, **kw):
    make_agent_benchmark(tmp_suite, **kw)
    cfg = load_config(tmp_suite)
    reg = Registry.discover(cfg.benchmarks_dir, set(cfg.suite.categories))
    return cfg, reg


def test_selftests_discriminate(tmp_suite):
    cfg, reg = setup(tmp_suite)
    outs = run_selftests(cfg, reg, reg.all())
    assert [(o.case, o.ok) for o in outs] == [("reference", True), ("noop", True)], [o.problems for o in outs]
    ref = next(o for o in outs if o.case == "reference")
    adir = next((p for p in (cfg.results_dir / "_selftest").rglob("a1") if (p / "score.json").exists()))
    assert (adir / "workspace.diff").read_text().count("+    return a + b") >= 1 or ref.score == 100


def test_run_resume_report_and_compare(tmp_suite):
    cfg, reg = setup(tmp_suite)
    runner = Runner(cfg, reg, echo=False)
    b = reg.get("tiny")
    store_ref = runner.create_run([b], "scripted/reference", attempts=2)
    runner.execute(store_ref)
    s = summarize(store_ref, cfg)
    assert s["benchmarks"][0]["score"]["mean"] == 100 and s["pass_rate"] == 1.0
    assert s["benchmarks"][0]["input_tokens"] is None  # scripted adapter reports no usage
    # simulate a crash during attempt 2, then resume: only attempt 2 is redone
    a1 = store_ref.attempt_dir(b.id, 1) / "evaluation.json"
    mtime = a1.stat().st_mtime_ns
    store_ref.set_status(b.id, 2, state="running")
    runner.execute(store_ref)
    assert a1.stat().st_mtime_ns == mtime
    assert store_ref.status(b.id, 2)["state"] == "completed"
    store_noop = runner.create_run([b], "scripted/noop", attempts=2)
    runner.execute(store_noop)
    c = compare_runs([store_ref, store_noop], cfg)
    assert not c["warnings"] and c["ranking"][0][0] == "scripted/reference"
    assert c["pairs"][0]["mean_diff"] == 80  # noop keeps the 20-point scope criterion
    for f in ("summary.json", "report.md", "report.html"):
        assert (store_ref.dir / f).exists()
    html = (store_ref.dir / "report.html").read_text()
    assert "prefers-color-scheme" in html and "http" not in html.split("<body>")[1].split("xmlns")[0]


def test_incomparable_runs_are_not_ranked(tmp_suite):
    cfg, reg = setup(tmp_suite, extra_yaml="budget_tiers:\n  short: {limits: {wall_clock_s: 60}}\n  long: {limits: {wall_clock_s: 120}}")
    runner = Runner(cfg, reg, echo=False)
    b = reg.get("tiny")
    s1 = runner.create_run([b], "scripted/reference", attempts=1, tier="short")
    runner.execute(s1)
    s2 = runner.create_run([b], "scripted/noop", attempts=1, tier="long")
    runner.execute(s2)
    c = compare_runs([s1, s2], cfg)
    assert any("tier differs" in w for w in c["warnings"]) and c["ranking"] is None
    assert compare_runs([s1, s2], cfg, force=True)["ranking"] is not None


def test_infra_errors_are_retried_and_excluded(tmp_suite, monkeypatch):
    cfg, reg = setup(tmp_suite)
    monkeypatch.setattr("aibench.adapters.base.time.sleep", lambda s: None)
    cfg.models.models["fake/fails"] = ModelConfig(adapter="fake_adapters:AlwaysFails", model="x", max_retries=1)
    runner = Runner(cfg, reg, echo=False)
    store = runner.create_run([reg.get("tiny")], "fake/fails", attempts=1)
    outs = runner.execute(store)
    assert outs[0].state == "infra_error"
    s = summarize(store, cfg)
    assert s["infra_error_count"] == 1 and s["completion_rate"] == 0 and s["benchmarks"][0]["score"]["mean"] is None


def test_policy_violation_is_critical(tmp_suite):
    cfg, reg = setup(tmp_suite, selftest=(
        "  - name: pusher\n"
        "    solution: {kind: script, path: push.yaml}\n"
        "    expect: {passed: false, max_score: 0, critical: [policy]}\n"))
    write(reg.get("tiny").path / "push.yaml", "steps:\n  - {tool: write_file, args: {path: calc.py, content: \"def add(a, b):\\n    return a + b\\n\"}}\n"
                                               "  - {tool: run_command, args: {command: git push origin main}}\n  - {final: done}\n")
    reg = Registry.discover(cfg.benchmarks_dir, set(cfg.suite.categories))
    outs = run_selftests(cfg, reg, reg.all(), only_case="pusher")
    assert outs[0].ok, outs[0].problems


def test_external_agent_adapter(tmp_suite, tmp_path):
    cfg, reg = setup(tmp_suite)
    agent = write(tmp_path / "fake_agent.py", textwrap.dedent("""\
        import json, sys
        prompt = sys.stdin.read()
        open("calc.py", "w").write("def add(a, b):\\n    return a + b\\n")
        print(json.dumps({"result": "fixed add()", "num_turns": 3, "total_cost_usd": 0.0123,
                          "usage": {"input_tokens": 1000, "output_tokens": 200}}))
    """))
    cfg.models.models["agent/fake"] = ModelConfig(adapter="external_agent", kind="agent", options={
        "command": ["python3", str(agent)], "prompt_via": "stdin", "output_format": "claude_json"})
    runner = Runner(cfg, reg, echo=False)
    store = runner.create_run([reg.get("tiny")], "agent/fake", attempts=1)
    outs = runner.execute(store)
    assert outs[0].state == "completed" and outs[0].passed is True
    ev = read_json(store.attempt_dir("bug_fixing/tiny", 1) / "evaluation.json")
    assert ev["usage"]["input_tokens"] == 1000 and ev["usage"]["cost_usd"] == pytest.approx(0.0123)
    assert read_json(store.dir / "manifest.json")["system_kind"] == "agent"


def test_rubric_pending_then_human_grade_and_judge(tmp_suite, capsys):
    extra = textwrap.dedent("""\
    """)
    b = make_agent_benchmark(tmp_suite)
    y = (b / "benchmark.yaml").read_text()
    y = y.replace("    - {id: process, type: trace}", "    - {id: process, type: trace}\n"
                  "    - {id: style, type: rubric, rubric: RUBRIC.md, criteria: [{id: clarity, description: clear code}], inputs: {files: ['*.py']}}")
    y = y.replace("    - {id: correct, weight: 80, metric: hidden.pass_rate}",
                  "    - {id: correct, weight: 80, metric: hidden.pass_rate}\n    - {id: clarity, weight: 20, metric: style.clarity, required: false}")
    (b / "benchmark.yaml").write_text(y)
    write(b / "RUBRIC.md", "clarity: 1 unreadable ... 5 exemplary")
    cfg = load_config(tmp_suite)
    reg = Registry.discover(cfg.benchmarks_dir, set(cfg.suite.categories))
    runner = Runner(cfg, reg, echo=False)
    store = runner.create_run([reg.get("tiny")], "scripted/reference", attempts=1)
    runner.execute(store)
    sc = read_json(store.attempt_dir("bug_fixing/tiny", 1) / "score.json")
    assert sc["status"] == "provisional" and sc["score"] == 100
    rc = main(["--root", str(tmp_suite), "grade", "--run-id", store.run_id, "--benchmark", "tiny", "--criterion", "clarity",
               "--level", "3", "--grader", "alice", "--evidence", "naming ok, no docstring"])
    assert rc == 0
    sc = read_json(store.attempt_dir("bug_fixing/tiny", 1) / "score.json")
    assert sc["status"] == "scored" and sc["score"] == pytest.approx(100 * (80 + 20 + 20 * 0.5) / 120, abs=0.01)
    # LLM judge path (fake judge), self-judging guard
    cfg.models.models["fake/judge"] = ModelConfig(adapter="fake_adapters:FakeJudge", model="judge-1")
    runner = Runner(cfg, reg, judge_labels=["fake/judge"], echo=False)
    store = runner.create_run([reg.get("tiny")], "scripted/reference", attempts=1)
    runner.execute(store)
    ev = read_json(store.attempt_dir("bug_fixing/tiny", 1) / "evaluation.json")
    assert ev["checks"]["style"]["metrics"]["clarity"] == pytest.approx(0.75)
    assert read_json(store.attempt_dir("bug_fixing/tiny", 1) / "score.json")["status"] == "scored"


def test_cli_list_validate_and_doctor(tmp_suite, capsys):
    make_agent_benchmark(tmp_suite)
    assert main(["--root", str(tmp_suite), "list"]) == 0
    assert "bug_fixing/tiny" in capsys.readouterr().out
    assert main(["--root", str(tmp_suite), "validate"]) == 0
    assert main(["--root", str(tmp_suite), "doctor"]) == 0


def test_render_task_prompt_variables():
    from aibench.core.runner import render_task_prompt
    from aibench.core.spec import LimitsSpec

    lim = LimitsSpec(wall_clock_s=900, max_tool_calls=90)
    assert render_task_prompt("no vars", "15m", lim) == "no vars"
    out = render_task_prompt("{{tier}}|{{wall_clock_human}}|{{limits.max_tool_calls}}|{{limits.max_total_tokens}}|{{task_prompt}}",
                             "15m", lim, task_prompt="T")
    assert out == "15m|15 minutes|90|unlimited|T"
