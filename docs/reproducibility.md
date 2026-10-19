# Reproducibility and experimental rigour

## What every run records (`results/<run_id>/manifest.json`)

| Field | Content |
|---|---|
| `harness_version`, `repo.commit`, `repo.dirty` | Exact framework code used |
| `tools` | Python, pytest, hypothesis, playwright, pydantic, anthropic, docker versions; platform; CPU count |
| `model` | adapter, model id, base URL, **applied** generation params, **dropped** params with the reason, provider options, capabilities, declared pricing and its source |
| `system_kind` | `model`, `agent` or `scripted` |
| `tier` | budget tier (if any) |
| `sandbox` | backend, network isolation and privilege drop *as actually achieved*, limits, notes |
| `harness` | system prompts' SHA-256, context strategy, output caps |
| `command_policy` | deny patterns in force |
| `benchmarks[]` | id, version, **content hash** (all files of the benchmark), mode, tools, attempts, effective limits |
| `judges` | judge labels and the self-judging setting |

Per attempt: the exact rendered prompt (`prompt.md`), full transcript, `trace.jsonl` (every model
call with latency, stop reason, reported usage, model id echoed by the provider and request id; every
tool call with arguments, duration, output size, errors and injected faults), the final workspace
snapshot and diff, all check outputs with evidence, and the score.

## Controls

- **Benchmark versioning:** semantic `version` + content hash; `execute` warns if a benchmark changed
  between planning and execution.
- **Identical inputs:** prompts and chat follow-ups are fixed files; follow-ups never depend on the
  model's previous answer; the user simulator is rule-based.
- **Fresh, isolated environments:** each attempt and each check gets a new sandbox from pristine
  fixtures; hidden tests are injected only into evaluation copies.
- **Deterministic graders:** property tests use `derandomize=True, database=None`; generators are
  seeded; bootstrap CIs use a fixed seed (`configs/scoring.yaml`); `PYTHONHASHSEED=0` in sandboxes.
- **Repetitions:** `repetition.attempts` (default 3 for most benchmarks; override with `--attempts`);
  reports show mean, std, n and a 95% CI. `pass^k` exposes unreliable systems.
- **Dependency pinning:** the Docker sandbox image pins Python 3.12, pytest and hypothesis; the local
  backend records the host versions in the manifest.
- **Failures are data:** infrastructure errors, timeouts, budget exhaustion and incomplete evaluations
  are recorded with their reason, never silently dropped or counted as model failures.
- **Resumability:** `benchmark resume RUN_ID` skips completed attempts and redoes interrupted ones from
  scratch.

## Equivalence between providers is not assumed

The same temperature, prompt or token limit does not make two providers equivalent. Known sources of
non-equivalence, and how they are surfaced:

| Difference | Handling |
|---|---|
| Unsupported sampling params (e.g. current Claude models reject non-default `temperature`/`top_p`) | Declared in `models.yaml` (`unsupported_params`); dropped and listed under `dropped_params` |
| Seeds | Applied only when the provider supports them; otherwise recorded as dropped |
| Hidden reasoning / effort settings | `provider_options` are recorded verbatim (e.g. `output_config.effort`) |
| Tokenizers differ | Token counts are provider-reported and are not comparable across providers; cost is the comparable unit when pricing is declared |
| Context window, tool-calling protocol, parallel tool calls | Capabilities recorded; benchmarks declare `requires`; incompatible systems are skipped, not scored 0 |
| Provider-side retries, caching | Request ids and cache token counts are logged when reported |
| Agents bring their own tools/prompts | `system_kind: agent`; never ranked against bare models without `--force` |

## Statistical guidance

- Treat differences smaller than the per-benchmark CI half-width as noise.
- Use paired comparisons (`benchmark compare`) rather than comparing two overall numbers.
- With 3 attempts per benchmark, CIs are wide; for decisions, increase attempts on the benchmarks that
  matter or add benchmarks (more pairs narrow the bootstrap CI).
- Report the number of samples with every claim (`n` is in every table).

## What is *not* controlled

- Provider-side model updates behind a stable model id (the echoed `model_reported` helps detect them).
- Wall-clock-dependent behaviour (latency, rate limits) across days.
- Hardware differences on the local backend (performance benchmarks use ratio-based, generous
  thresholds for this reason).
