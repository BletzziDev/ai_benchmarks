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

20 benchmarks across all 12 categories (14 agent-mode, 6 chat-mode), 114 selftest cases.

| Category | Benchmark | Mode | Difficulty | What it discriminates |
|---|---|---|---|---|
| Frontend & design | `frontend_design/agent_platform_site` | agent | hard | Fixed brand brief (palette, fonts, sections, components); Playwright grader at 375/768/1280/1920 px: components work, no overflow, palette, WCAG contrast, labels, focus, reduced motion, budgets, no external requests; screenshots + optional visual rubric |
| Advanced reasoning | `advanced_reasoning/pricing_rules_state_bug` | agent | hard | Defects visible only in specific state combinations; one implied only by a documented invariant; oracle-based property tests |
| | `advanced_reasoning/perf_complexity_regression` | agent | medium | Hidden O(n²) behind innocent code + red herring; exact equivalence with the original + machine-independent complexity ratio |
| Bug fixing | `bug_fixing/inventory_reservations` | agent | hard | Three interacting root causes (cache key, invalidation on expiry, lapsed holds masked by a clamp); symptom vs cause; discriminating regression tests |
| | `bug_fixing/date_range_billing` | agent | medium | Single-cause DST proration bug; plausible "ceil" patch breaks fall-back months |
| Concurrency | `concurrency/payment_double_charge` | agent | hard | Idempotency under concurrent retries, overdrafts, lost updates; global lock held across I/O fails a parallelism test |
| | `concurrency/transfer_deadlock` | agent | medium | Lock-order deadlocks (incl. a second one surviving the obvious fix), leaked lock on timeout, self-transfer hang |
| | `concurrency/async_cancellation_leak` | agent | hard | asyncio permit leaks on cancellation, duplicate processing on redelivery, unsafe shutdown |
| Architecture | `architecture/zero_downtime_migration` | agent | hard | Migration plan in a DSL executed by a simulator over mixed-version deploy windows; data loss, stale reads, rollback points; multiple valid plans accepted; optional design rubric |
| Code quality | `code_quality/legacy_report_refactor` | agent | medium | Behaviour-preserving refactor; complexity/duplication/nesting metrics vs the original; over-engineering penalised |
| Security | `security/notes_service_vulns` | agent | hard | SQLi, broken tenant isolation, stored XSS, path traversal, hard-coded/logged secret — exploit variants defeat blacklists |
| | `security/token_auth_flaws` | agent | hard | `alg: none`, missing expiry, non-constant-time compare, pickle before MAC, unsalted SHA-1 with backward-compatible rehash |
| Hallucination | `hallucination/closed_world_sdk` | chat | hard | Fictional SDK docs in the prompt; non-existent/removed APIs, version questions, unspecified behaviour; invented identifiers in code (AST); confident-hallucination rate |
| | `hallucination/diagnostic_uncertainty` | chat | medium | Diagnose or abstain from logs with line ids; fabricated evidence citations are critical |
| Sycophancy | `sycophancy/code_review_pressure` | chat | medium | Paired design: pressure vs bogus evidence vs valid evidence; false vs true premises; insecure insistence; harmful reversals and correct updates scored separately |
| Decision making | `decision_making/disk_pressure_incident` | agent | medium | Disk at 97% with WAL data, sessions, retention rules and an irreversible migration; authorization via simulated owner; timid and reckless both fail |
| | `decision_making/judgment_scenarios` | chat | medium | 14 decisions with per-option scores and rationales; reversibility / authorization judgments; harmful-choice gate |
| Tool use | `tool_use/flaky_build_recovery` | agent | medium | Injected transient failure + silently truncated file read; stale generated code must be regenerated, not hand-patched |
| | `tool_use/log_forensics` | agent | hard | 2.2 MB of logs, clock-offset trap, cross-file correlation, one unanswerable question; efficiency from the trace |
| Long-horizon autonomy | `long_horizon_autonomy/saas_accounts` | agent | expert | 12-ticket backlog with 15m/1h/4h/12h budgets, mid-run context wipe and resume from `PROGRESS.md`, destructive-migration authorization, blocked ticket, prompt injection, fake secret, honesty of completion claims |

Each benchmark's `EVAL.md` lists its criteria and weights, critical failures, the observed selftest
scores and its limitations; `benchmark show <id>` prints the full configuration.

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
