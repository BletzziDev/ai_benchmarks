# Methodology

This suite evaluates models **and** complete coding agents on software-engineering work. It is built
around one rule: *a score must be explained by verifiable evidence collected under declared,
reproducible conditions*. This document records the research that informed the design, the
principles derived from it, and how they are implemented.

## 1. Prior work we studied (and what we took from it)

We used existing benchmarks as references for methodology, not as content: every scenario in this
suite is original, written for it, and labelled with leak canaries.

| Reference | What it does | What we adopted | What we deliberately did differently |
|---|---|---|---|
| HumanEval / MBPP; Chen et al. 2021 (Codex) | Function synthesis graded by unit tests; unbiased **pass@k** | `pass@k` estimator (`aibench/core/stats.py`) | Single-function tasks saturate and are contaminated; we grade whole repositories, processes and honesty |
| SWE-bench (Verified, Pro) | Real GitHub issues, hidden fail-to-pass/pass-to-pass tests | Hidden tests never shown to the model; "fail→pass" + "pass→pass" split (our `root`/`pres` groups); scaffold sensitivity | Public-repo tasks leak into training data (OpenAI stopped reporting Verified in 2026 citing memorised gold patches); we use original fixtures + canaries and also grade the agent's *own* regression tests |
| Terminal-Bench, mini-swe-agent style harnesses | Agents act through a shell in a container | Container/namespace sandbox, a small neutral tool set so the score reflects the model, not tool cleverness | We additionally record every tool call and grade process (verification after edits, recovery from faults) |
| METR time horizons (HCAST, RE-Bench; TH 1.1 in 2026) | Success probability vs. human task length; 50%/80% horizons | Budget **tiers** (15m / 1h / 4h / 12h) on the same backlog to observe performance vs. budget | We do not claim a human-time horizon; tiers are resource limits, and wall-clock / model / tool time are reported separately |
| τ-bench | Tool-agent-user simulations; **pass^k** reliability | Scripted user simulator for `ask_user`; `pass^k` | User replies are rule-based and deterministic (no LLM user) for reproducibility |
| UK AISI Inspect, OpenAI Evals, HELM | Task = dataset + solver + scorer; holistic multi-metric reporting | Separation of prompt / data / execution / evaluation; multi-metric reports (never a single number) | Our checks emit raw metrics + evidence; scoring is declarative per benchmark |
| LiveCodeBench | Time-windowed problems against contamination | Canary GUIDs; original content; versioned benchmarks with content hashes | — |
| Miller 2024, "Adding Error Bars to Evals" | CLT standard errors, clustering, **paired** differences, power | t-based CIs over attempts; paired bootstrap of per-benchmark differences in `benchmark compare` | — |
| Zheng et al. 2023 (MT-Bench / LLM-as-judge) | Judge biases: position, verbosity, self-enhancement | Judges see untrusted-data-wrapped artifacts, must cite evidence, self-judging is blocked, multi-judge spread reported, rubric criteria are optional until graded | Judges never decide pass/fail alone |
| Sycophancy research (Sharma et al. 2023; SycEval 2025; SycoBench; "Stubborn or Sycophantic?" 2026) | Measures answer changes under user pressure | Paired designs that change only the pressure | We score **harmful reversals and correct updates separately**, as reversal-only scores reward stubbornness |
| Package hallucination ("We Have a Package for You!", slopsquatting) | LLMs invent package/API names, often repeatably | Closed-world API docs so "does not exist" is decidable; invented-identifier scans | Real-world facts are only used when stable and certain |

Sources: METR time-horizon paper (arXiv 2503.14499) and Epoch AI's METR summary; SWE-bench Pro and the
2026 discussion of SWE-bench Verified contamination; Miller, arXiv 2411.00640; SycEval, arXiv
2502.08177; PARROT, arXiv 2511.17220; Sharma et al. 2023, "Towards Understanding Sycophancy in Language Models";
the "We Have a Package for You!" package-hallucination study (576k samples, 16 models).

## 2. Principles

1. **Evidence over eloquence.** Explanations earn nothing by themselves. Points come from hidden tests,
   property tests, invariant checks, simulators, diffs, traces and structured answers checked against
   ground truth. Qualitative rubrics exist only where no objective check is adequate (visual design,
   design documents) and are marked *optional* so a missing judge yields a *provisional* score, not a
   fabricated one.
2. **Criteria fixed before execution.** Every benchmark declares its checks, metrics, weights,
   transforms, pass gates and critical failures in `benchmark.yaml`, under a semantic version and a
   content hash. Changing them is a new benchmark version.
3. **Discrimination is tested, not assumed.** Each benchmark ships *selftests*: a reference solution
   that must pass, a no-op that must fail, and realistic decoys (symptom patches, special-casing the
   visible examples, global locks, sycophantic answers, reckless deletions, false claims of having
   run tests) that must fail for the documented reason. `benchmark selftest --all` replays them
   through the full pipeline.
4. **Critical failures are not compensable.** Destroying data, following injected instructions,
   exposing secrets, claiming verification that never happened, or violating a critical invariant
   force a fail and zero/cap the score regardless of other dimensions. They are reported separately.
5. **Process is evidence too.** Agents are graded on what they did (tests run after the last edit,
   recovery from injected tool faults, asking before destructive actions) using the recorded trace —
   not on what they say they did.
6. **Honesty is measured against reality.** Reports must end with a JSON block; claims (tests run,
   tickets done, root causes) are compared with the trace and hidden-test outcomes.
7. **No invented numbers.** Tokens and cost are recorded only when the provider reports usage and
   pricing is declared with a source; otherwise they are `unavailable`.
8. **Comparable or not ranked.** Runs are ranked only when benchmark hashes, tiers, tool sets, system
   kind (model vs agent vs scripted) and harness version match; otherwise the comparison shows
   warnings and withholds the ranking.

## 3. Evaluation types used

| Type | Where | Check |
|---|---|---|
| Hidden unit/integration tests grouped by purpose (root cause, preservation, invariants) | bug fixing, reasoning, security, long horizon | `pytest` with `groups` |
| Model-based property tests (Hypothesis, derandomised) against an oracle of the documented spec | inventory, pricing, migration | `pytest` |
| Deterministic interleavings + stress + invariant checks | concurrency | `pytest` with `repeat` |
| Regression-test quality (fails on original, passes on final) | bug fixing, security | `regression_tests` |
| Diff scope and size, protected paths | all agent benchmarks | `diff_scope` |
| Trace/process metrics | all agent benchmarks | `trace` |
| Structured report and claim verification | all agent benchmarks | `final_report` |
| Browser automation (Playwright): DOM/ARIA, behaviour, overflow, contrast, palette, screenshots | frontend | `python` grader |
| Simulators (e.g. migration plans executed against a compatibility matrix) | architecture | `python` grader |
| Structured answers vs. execution-verified ground truth | sycophancy, hallucination, decision making | `python` grader |
| Rubrics (LLM judges and/or humans) | frontend, architecture | `rubric` |

## 4. Distinguishing error types

- **Hallucination** (invented API/fact asserted or used) vs **reasoning error** (wrong conclusion
  about provided material) vs **misinterpretation** vs **legitimate uncertainty** are separate
  metrics in the hallucination benchmarks, enabled by closed-world documentation where existence is
  decidable.
- **Sycophancy** (harmful reversal under pressure) vs **stubbornness** (no update on valid evidence)
  vs **contrarianism** ("correcting" true premises) are separate metrics.
- **Symptom fixes** vs **root-cause fixes** are separated by hidden tests that exercise the cause
  through paths the report did not mention, plus invariant/property tests.

## 5. Model vs. agent evaluations

A *model* run uses this harness's neutral tool protocol and system prompt; an *agent* run (e.g. a CLI
coding agent) brings its own loop, tools, context management and prompts. Both are scored with the
same checks, but `system_kind` is recorded and `benchmark compare` refuses to rank across kinds
without `--force`. Scripted adapters (reference/no-op replays) are a third kind used only for
validation and are never presented as model results.

## 6. Known methodological limitations

- Small per-family case counts in chat benchmarks: use ≥3 attempts and read the per-family counts.
- Property tests are derandomised for reproducibility, so they explore a fixed sample.
- Python concurrency tests cannot prove the absence of races (no TSan; the GIL hides many
  interleavings); deterministic schedules and invariant checks mitigate but do not eliminate this.
- Visual quality remains partly subjective; automated proxies (palette adherence, spacing grid,
  contrast, overflow) do not capture taste, and LLM judges have known biases.
- The local sandbox is defence in depth, not a hard security boundary; use the Docker backend for
  untrusted systems (see `security.md`).
- Budget tiers bound resources; they do not convert into "hours of human work".
