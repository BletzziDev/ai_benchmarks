# Benchmark design and the per-benchmark contract

## Directory contract

Every benchmark lives in `benchmarks/<category>/<name>/` and is discovered automatically (any
directory with a `benchmark.yaml`). Adding one never requires changing the core.

| File / dir | Required | Purpose |
|---|---|---|
| `PROMPT.md` | yes | The **exact** text sent to the model (agent mode; harness variables `{{tier}}`, `{{wall_clock_human}}`, `{{limits.<field>}}` and, in resume prompts, `{{task_prompt}}` are filled in and the rendered text is stored as `prompt.md` in each attempt) or the exact template (chat mode, `{{input}}` and `{{field}}` placeholders filled from each case). States context, objectives, constraints, permissions, forbidden actions, expected artifacts, known completion criteria and the final report format. Never contains answers, reference solutions or hidden-test details. Identical across models. |
| `EVAL.md` | yes | Human evaluation specification: what is measured, ground truth, criteria with weights, critical failures, minor vs serious errors, observed selftest results, limitations, interpretation. |
| `benchmark.yaml` | yes | Machine-readable definition validated by `aibench.core.spec.BenchmarkSpec`. |
| `README.md` | yes | How to run it alone, requirements, how to reproduce the evaluation by hand. |
| `fixtures/` | yes | Workspace, logs, data, cases — everything the model may see. |
| `tests/` | yes | Hidden tests (`tests/hidden/`, never copied into the workspace), graders, ground truth, verification scripts. |
| `REFERENCE_SOLUTION/` | recommended | Reference fix/answers used by selftests. |
| `RUBRIC.md`, `GROUND_TRUTH.*`, `INVARIANTS.md`, `selftest/` | as needed | Only when they serve the evaluation. No empty or decorative files. |

`benchmark validate` enforces the contract: required files with real content, no `hidden` paths in
the workspace, leak canaries absent from every model-visible file, criteria referencing existing
checks, selftests present and pointing to existing solutions, and categories declared in
`configs/benchmark.yaml`.

## `benchmark.yaml` reference

```yaml
schema_version: 1
id: <category>/<name>          # stable identifier
name: ...
version: 1.0.0                 # bump on any change to prompt, fixtures, checks or scoring
category: bug_fixing           # must be declared in configs/benchmark.yaml
difficulty: easy|medium|hard|expert
description: ...
languages: [python]
mode: agent | chat
requires: [tools, vision, multi_turn, long_context]   # capabilities a system must have

prompt: PROMPT.md
cases: {file: fixtures/cases.yaml}       # chat mode: list of {id, input, followups?, images?}

environment:
  workspace: fixtures/workspace          # copied into a fresh sandbox per attempt (git-initialised)
  overlays: {fixtures/extra: docs/}      # extra model-visible files
  setup: ["python scripts/generate.py"]  # run inside the sandbox before the episode
  tools: [list_files, read_file, write_file, edit_file, search, run_command, ask_user]
  faults: [{tool: run_command, match: pytest, mode: error|timeout|truncate, times: 1, message: ...}]
  user_simulator: fixtures/user.yaml     # rules answering ask_user deterministically
  protected_paths: ["data/**"]
  sandbox: {memory_mb: 2048, cpu_seconds: 600, max_file_mb: 64, max_processes: 1024, max_workspace_mb: 512, network: false}

limits: {wall_clock_s, max_turns, max_tool_calls, max_total_tokens, max_output_tokens_per_turn, command_timeout_s, max_cost_usd}
budget_tiers: {15m: {limits: {...}}, 1h: {...}, 4h: {...}, 12h: {...}}
default_tier: 1h
interruptions: {after_tool_calls: [60], resume_prompt: fixtures/RESUME_PROMPT.md}

evaluation:
  checks:
    - {id: hidden, type: pytest, paths: [tests/hidden], groups: {root: ["*test_root_*"]}, repeat: 1}
    - {id: scope, type: diff_scope, allowed: ["src/**", "tests/**"]}
    - {id: regression, type: regression_tests}
    - {id: process, type: trace, test_command_pattern: '\bpytest\b', destructive_patterns: ['rm\s+-rf']}
    - {id: report, type: final_report, required_keys: [summary], tests_claim_field: tests_run}
    - {id: custom, type: python, entrypoint: tests/grader.py:grade}
    - {id: design, type: rubric, rubric: RUBRIC.md, criteria: [{id: clarity, min: 1, max: 5}], inputs: {files: ["*.md"]}}

scoring:
  pass_threshold: 75
  pass_requires: ["hidden.root_all_passed == 1"]
  criteria:
    - {id: root_cause, weight: 35, metric: hidden.root_pass_rate}
    - {id: size, weight: 5, metric: scope.lines_changed, transform: {type: linear, zero_at: 300, full_at: 80}}
    - {id: clarity, weight: 10, metric: design.clarity, required: false}
  critical_failures:
    - {id: false_test_claim, when: "report.false_test_claim == 1", effect: cap, cap: 40}

repetition: {attempts: 3, infra_retries: 1}
leak_canaries: ["AIBENCH-CANARY: <unique id>"]
selftest:
  - name: reference
    solution: {kind: overlay, path: REFERENCE_SOLUTION/files, report: REFERENCE_SOLUTION/REPORT.md, run_commands: ["python -m pytest -q"]}
    expect: {passed: true, min_score: 90, critical: []}
  - {name: noop, solution: {kind: noop}, expect: {passed: false, max_score: 35}}
```

## Built-in check types

| Type | Metrics (prefix `<check_id>.`) | Notes |
|---|---|---|
| `pytest` | `passed failed errors skipped total pass_rate all_passed`, per group `<g>_pass_rate …`, `flaky_tests` (with `repeat`), `tamper_files_removed` | Hidden tests are injected into a **fresh copy** of the final workspace under `.aibench_tests/`, run with `python -I`, an isolated ini, `--confcutdir` and `-p no:cacheprovider`; agent-added `conftest.py`, `sitecustomize.py`, `pytest.py`, `*.pth` etc. are removed first and reported. |
| `command` | `exit_code success timed_out` + JSON metrics printed on the last stdout line | For custom scripts/simulators. |
| `diff_scope` | `files_added/deleted/modified/changed lines_added/removed/changed out_of_scope_files protected_modified protected_deleted` | Compares the original workspace with the final snapshot. |
| `regression_tests` | `new_test_files discriminating_tests fails_on_original passes_on_final quality` | Runs the agent's new/changed tests against the original and the final code. |
| `trace` | `tool_calls tool_errors commands test_runs tests_run_after_last_edit edits repeated_identical_calls policy_violations asks faults_injected faults_recovered destructive_commands budget_exhausted` | Process evidence from `trace.jsonl`. |
| `final_report` | `report_present report_json_valid claims_tests_run false_test_claim` | Last fenced JSON block of the final message. |
| `python` | anything the grader returns | `grade(ctx, check) -> CheckResult|dict`. Trusted benchmark code; must execute model code only via `ctx.new_sandbox()`. |
| `rubric` | one metric per rubric criterion (0–1) | LLM judges (`--judge`) or human grades (`benchmark grade`); `None` (pending) otherwise. |

Third-party check types can be referenced as `type: package.module:function` without core changes.

## Writing a good benchmark

1. **Start from the capability**, then design a scenario where weak and strong systems behave
   differently. Write down the decoys (plausible wrong solutions) before the hidden tests.
2. **Hide the right things.** The prompt states the goal, constraints and the *kinds* of evaluation;
   hidden tests target root causes through paths not mentioned in the prompt, invariants and
   preservation.
3. **Prefer behaviour over implementation.** Accept every correct design; check observable behaviour
   and invariants. Never grep for a specific fix unless the property is inherently syntactic (e.g.
   no new third-party imports).
4. **Make ground truth verifiable.** For chat benchmarks generate cases and labels from one script and
   verify labels by execution where possible (`tests/verify_ground_truth.py`, run by the framework
   test suite).
5. **Declare critical failures** for actions that must never be traded off.
6. **Write selftests** for reference, no-op and each decoy; record the observed scores in `EVAL.md`.
7. **Keep fixtures deterministic**: no network, seeded generators, derandomised property tests,
   bounded runtimes (timeouts in concurrency tests).
8. **Version** every change (`version:`); the content hash in each run manifest makes silent changes
   visible.

## Selftest solution kinds

| Kind | Meaning |
|---|---|
| `overlay` | Copy a directory over the workspace (`.aibench_delete` lists paths to delete), optionally run commands, then send a report. Executed as real tool calls through the harness. Every file in the overlay is written into the workspace, so keep the report **outside** it (e.g. `REFERENCE_SOLUTION/REPORT.md` next to `REFERENCE_SOLUTION/files/`). |
| `script` | YAML `steps: [{tool: name, args: {...}}, {final: "..."}]` — for behaviours like `ask_user` flows or reckless commands. |
| `responses` | Chat mode: `{case_id: [reply_turn1, reply_turn2, ...]}`. |
| `noop` | Do nothing; empty final message. |
