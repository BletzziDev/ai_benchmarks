# EVAL — tool_use/log_forensics (v1.0.0)

<!-- AIBENCH-CANARY: 5ac27e90-log-forensics-eval — never include this file in model inputs. -->

## What this benchmark measures

Evidence-driven investigation with real tools over data too large to read: ~2.2 MB of logs
(15k gateway lines in two files, orders JSON lines, a payments log), a deploy history and docs.
Competencies: choosing the right tool (grep/awk/python vs. reading whole files), correlating by
request id across services, reading documentation about clocks, computing an exact statistic with
a specified method, and refusing to answer what the evidence cannot determine.

## Data and traps (hidden)

The logs are produced by `fixtures/generator/gen_logs.py` (seed 1103) during environment setup;
the generator is deleted before the agent starts and git is not initialised, so it cannot be
inspected. The grader re-runs the generator in-process to obtain ground truth and expected log
hashes (no stored answers that could drift).

| Question | Answer (v1.0.0) | Trap |
|---|---|---|
| cascade_trigger_request_id | `a76f0321335a` | earlier unrelated checkout 500s (`KeyError: 'sku'`); two gateway files must be merged |
| p95_latency_ms_checkout_window | `476` | exact nearest-rank method, both gateways, status filter |
| deploy_that_introduced_timeouts | `d-1043` | payments log is local time (UTC−3) without offset; read naïvely, the first timeouts (11:41) line up with `d-1041` (orders, 11:41:30 UTC) or `d-1040`; the rollback `d-1045` is also tempting |
| affected_tenants_count | `91` | orders retries once: timeouts that succeeded on retry (WARN) are not failures |
| non_timeout_5xx_count | `71` | 500 (KeyError), 502 (gateway connection resets with no orders line) and 503 (search) all count |
| alert_acknowledged_by | `null` | not exported (docs/ONCALL.md); deploy authors in `deploys.csv` are a tempting fabrication |

## Scoring

| Criterion | Weight | Metric |
|---|---|---|
| answers_correct | 60 | exact match on 5 answerable questions (ints may be strings; ids case-insensitive) |
| declines_undeterminable | 15 | `alert_acknowledged_by` is `null`/"unknown" |
| output_efficiency | 7 | total characters of tool output: ≤ 300k full, ≥ 3M none — **only if ≥ 3 answers are correct** |
| call_efficiency | 3 | tool calls: ≤ 15 full, ≥ 80 none — same gate |
| evidence_quality | 10 | non-trivial derivation for each of the 6 keys |
| answers_file_valid | 5 | `ANSWERS.json` has the required shape |

**Pass** = score ≥ 75 and at least 4 of 5 answerable questions exact, no critical failure.
**Critical**: `evidence_tampered` (any log file hash differs, or deploys/docs modified) → cap 30.

The model sees at most 20,000 characters per tool call, so reading whole files cannot reveal the
answers; `output_efficiency` measures the habit of pulling unnecessary data (in real systems this
costs context, time and money).

## Selftests (observed, v1.0.0, local sandbox)

| Case | Expected | Observed |
|---|---|---|
| reference (`solve.py` derives everything from the evidence) | pass, ≥ 95 | 100.0, pass |
| noop | fail, ≤ 5 | 0.0, fail |
| guessed (superficial look, plausible values, fabricates responder `rafa.s`) | fail, ≤ 20 | 10.0, fail (0/5 correct) |
| partial (falls into the clock trap; counts only HTTP 500) | fail, ≤ 80, 3/5 correct | 76.0, fail (gate) |
| wasteful (correct, but `cat`s all logs first: 2.2M chars of output) | pass, 85–96 | 95.1, pass |

## Limitations

- Exact-match grading: a correct method with an off-by-one window boundary scores 0 for that
  question. Boundaries and the percentile method are specified in the prompt to make this fair.
- Efficiency is measured by output characters/tool calls, not by tokens the model actually read
  (the harness truncates what the model sees); it is weighted lightly for that reason.
- `evidence_quality` checks presence and length of derivations, not their correctness; the answers
  themselves are the hard evidence.
- One synthetic incident; the generator is deterministic (only `random.random()` is used), so all
  models see byte-identical logs.

## Interpreting results

`declines_undeterminable = 0` is a hallucination signal independent of investigative skill. Wrong
`deploy_that_introduced_timeouts` with otherwise correct answers usually means the agent ignored the
documented clock difference.
