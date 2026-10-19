# Scoring

## From evidence to a score

```
checks ──► raw metrics (+ evidence) ──► criteria (metric → [0,1] via transform) ──► weighted 0–100
                                     └► critical-failure rules ──► fail + zero/cap (not compensable)
                                     └► pass gates (pass_requires) ──► verdict
```

1. **Checks** produce flat metrics (`hidden.root_pass_rate`, `scope.lines_changed`, …). Raw metrics are
   stored in `evaluation.json` together with human-readable evidence (failing test names, offending
   files, trace excerpts).
2. **Criteria** (declared per benchmark, before any run) map one metric to `[0, 1]`:
   - `identity` (clamped), e.g. pass rates;
   - `linear` with `zero_at`/`full_at`, e.g. diff size (≤80 lines → 1, ≥300 → 0);
   - `threshold` (`invert` for "≤ threshold is good"), e.g. out-of-scope files = 0.
3. **Weighted score** = `100 × Σ wᵢ·vᵢ / Σ wᵢ` over *available* criteria.
4. **Availability.** A criterion whose metric is unavailable (e.g. a rubric without a judge) is
   excluded and the remaining weights renormalised:
   - optional criterion missing → status `provisional` (verdict still computed);
   - required criterion missing → status `incomplete` (score shown, **no pass/fail verdict**).
   `completeness` (= available weight / total weight) is stored with every score.
5. **Critical failures** are boolean rules over metrics (`report.false_test_claim == 1`). Each
   triggered rule forces `passed = false` and applies its effect: `zero`, `cap: N`, or `fail` (verdict
   only). They are listed separately in reports and counted in the critical-failure rate. Missing
   metrics never trigger a rule (comparisons with unavailable values are false).
6. **Pass** = `score ≥ pass_threshold` ∧ all `pass_requires` gates ∧ no critical failure.

Weights differ per category on purpose (e.g. root causes dominate bug fixing; harmful reversals and
correct updates dominate sycophancy; per-requirement checks dominate frontend). They are documented
in each `EVAL.md` together with the reasoning and the observed selftest scores.

## Aggregation

- **Per benchmark:** mean, sample std, SEM and a 95% t-interval over completed attempts; pass rate;
  unbiased `pass@1`; `pass^k` (all k attempts pass — reliability); critical-failure rate; terminations.
- **Per category:** mean of benchmark means.
- **Overall:** mean of category means (equal weights unless `configs/scoring.yaml` declares
  `category_weights`). The overall number is always shown next to the competency profile, pass and
  critical rates, provisional flags and usage — never alone.
- **Infrastructure errors** (provider outages after retries, harness failures) are excluded from score
  statistics and reported in `completion_rate` and `infra_error_count`.
- **Skipped** attempts (system cannot satisfy the benchmark, e.g. no tool calling) are reported as
  skipped, not as zero.

## Comparing models

`benchmark compare RUN_A RUN_B …` (run ids, or model labels → latest completed run):

- checks comparability (benchmark content hashes, tier, tool set, system kind, harness version) and
  withholds the ranking with explicit warnings when they differ (`--force` overrides);
- computes **paired** differences per benchmark (attempt means), with a seeded percentile bootstrap
  CI over benchmarks, and wins/losses/ties (|Δ| ≤ 0.5 = tie). "No significant difference" is reported
  when the CI contains 0 — practical significance should be judged against the per-benchmark CIs and
  the variability between attempts;
- writes `comparison.md`, `comparison.json` and a self-contained `comparison.html`.

## LLM judges

Used only for rubric criteria (visual quality, design documents). Mitigations:

- the evaluated model cannot judge itself unless `--allow-self-judge` (then flagged in the output);
- artifacts are wrapped as untrusted data; the judge system prompt says to ignore embedded instructions,
  length and confidence;
- every level must cite evidence; levels without evidence are discarded (treated as unavailable);
- multiple `--judge` options can be combined; the maximum spread between judges is reported
  (`judge_agreement_spread`) as an agreement signal;
- judge usage is recorded in `evaluation.json`.

Known risks that remain: position and verbosity biases, sensitivity to answer formatting, shared
blind spots between judge and evaluated model families, and unknown agreement with human graders for
a given rubric. Before relying on a judge for decisions, grade a sample with humans
(`benchmark grade`) and compare.

## Human grading

```bash
benchmark grade --run-id RUN --benchmark frontend_design/agent_platform_site --attempt 1 \
  --criterion visual_quality --level 4 --grader "alice" --evidence "consistent 8px grid; hero hierarchy clear"
```

Grades are stored in the attempt's `human_grades.json` (with grader and evidence) and the attempt is
rescored immediately; `benchmark rescore RUN` recomputes every score from stored evaluations.
