# aibench — benchmarks and evals for AI software-engineering models and agents

A modular, reproducible and extensible framework that **executes** tasks, **collects evidence**,
**scores** against criteria fixed in advance and **compares** models and coding agents — from
building a polished, accessible frontend to root-causing concurrency bugs, resisting sycophancy,
avoiding hallucinations and working autonomously on a backlog with interruptions.

> Status: v0.1. Every benchmark listed below is implemented and validated by selftests (reference
> solution passes, no-op and realistic decoys fail). No real model results are shipped: the demo
> reports in `results/demo/` come from deterministic scripted adapters and are labelled as such.

## Quick start

```bash
pip install -e '.[dev]'                       # Python ≥ 3.11
benchmark doctor                              # sandbox capabilities, Docker, Playwright
benchmark list
benchmark validate                            # contract of every benchmark
benchmark selftest --all                      # prove each grader discriminates (no API key needed)

export ANTHROPIC_API_KEY=...                  # or OPENROUTER_API_KEY / OPENAI_API_KEY (see configs/models.yaml)
benchmark run bug_fixing/inventory_reservations --model anthropic/claude-sonnet-5-5 --attempts 3
benchmark run-category concurrency --model anthropic/claude-sonnet-5-5
benchmark run-all --model anthropic/claude-opus-5-5 --sandbox docker
benchmark run long_horizon_autonomy/saas_accounts --model anthropic/claude-opus-5-5 --tier 4h
benchmark run frontend_design/agent_platform_site --model M --judge anthropic/claude-opus-5-5   # rubric judge ≠ evaluated model
benchmark report --run-id RUN_ID
benchmark compare RUN_A RUN_B                 # or model labels → their latest completed runs
benchmark resume RUN_ID                       # continue an interrupted run
benchmark grade --run-id RUN_ID --benchmark B --criterion visual_quality --level 4 --grader you --evidence "…"
```

## Architecture

```
configs/            suite config (categories, sandbox, command policy), models.yaml, scoring.yaml, harness prompts
aibench/
  cli.py            `benchmark` command
  core/
    spec.py         pydantic schemas for benchmark.yaml (validated contract)
    registry.py     discovery (any dir with benchmark.yaml) + contract validation
    runner.py       plan → isolate → run → snapshot → evaluate → score → store; retries, resume, cleanup
    sandbox.py      local (netns + unprivileged uid + rlimits) and docker backends
    tools.py        neutral tool protocol, path confinement, command policy, fault injection, user simulator
    agent_loop.py   native tool loop, scripted chat conversations, external agents; budgets; context strategy
    trace.py        event trace; wall-clock vs model vs tool time; usage/cost only when reported
    checks/         pytest, command, diff_scope, regression_tests, trace, final_report, python, rubric
    scoring.py      criteria → 0–100, gates, critical failures (non-compensable), provisional/incomplete
    stats.py        mean/std/t-CI, pass@k, pass^k, paired bootstrap comparisons
    judge.py        LLM judge panel with self-judging guard and evidence requirement
    reporting.py    summary.json, report.md, self-contained report.html, comparisons
    artifacts.py    results layout, manifests (hashes, versions, params), structured logs
    selftest.py     replays canned solutions to validate graders
  adapters/         anthropic (official SDK), openai_compatible (stdlib), external_agent (CLI), scripted
benchmarks/<category>/<name>/   PROMPT.md · EVAL.md · benchmark.yaml · README.md · fixtures/ · tests/ · REFERENCE_SOLUTION/
docs/               methodology, benchmark-design, scoring, reproducibility, security, adapters
docker/             pinned sandbox image
tests/              framework tests (+ slow: all selftests)
```

Design decisions (details in `docs/`):

- **Prompt, data, execution and evaluation are separate**: `PROMPT.md` is the exact text sent; fixtures
  are the only model-visible data; hidden tests are injected only into evaluation copies; checks are
  declarative in `benchmark.yaml`.
- **Criteria are fixed before execution** and versioned with a content hash recorded in every run.
- **Selftests prove discrimination**: each benchmark declares a reference, a no-op and decoys with
  expected score ranges/verdicts/critical failures.
- **Critical failures cannot be compensated** (destroying evidence or data, following prompt
  injections, false claims of having run tests, protected-file edits, unauthorised destructive actions).
- **No invented metrics**: tokens/cost are `n/a` unless the provider reports usage and pricing is
  declared with a source.
- **Models vs agents vs scripted** are different `system_kind`s; comparisons across kinds or
  different conditions are flagged and not ranked.

## Benchmarks

BENCHMARK_TABLE_PLACEHOLDER

## What a report contains

Per run: overall score (mean of category means) **next to** the competency profile, pass rate,
critical-failure rate, completion rate and infra errors; per benchmark: mean ± std, n, 95% CI,
pass count, critical failures, wall/model/tool time, tokens, cost (when available), per-criterion
scores and links to every attempt's artifacts (prompt, transcript, trace, final workspace, diff,
check evidence, screenshots). `report.html` is self-contained and readable in light and dark mode.

## Requirements

- Linux (the local sandbox uses network namespaces and privilege drop when run as root; elsewhere it
  degrades and the manifest records it). Docker for the hardened backend (`scripts/build_sandbox_image.sh`).
- Python ≥ 3.11 with `pydantic`, `PyYAML`; `pytest` + `hypothesis` for graders; Playwright + Chromium
  for the frontend benchmark (`AIBENCH_CHROMIUM` to point at a browser binary); the `anthropic` SDK
  for Anthropic models.

## Limitations

See `docs/methodology.md#6-known-methodological-limitations` and each benchmark's `EVAL.md`. In short:
small per-family samples in chat benchmarks; derandomised property tests explore fixed samples;
Python race detection is probabilistic beyond the deterministic interleavings; visual quality is
partly subjective; the local sandbox is defence in depth (use Docker for untrusted systems); budget
tiers are limits, not measurements of human-equivalent time.

## License

MIT — see `LICENSE`.
