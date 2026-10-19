# tool_use/log_forensics

Hard tool-use benchmark: answer six precisely defined questions about a checkout outage from
multi-MB logs across services with different clocks, write `ANSWERS.json` with evidence, and decline
the one question the evidence cannot answer.

## Run

```bash
benchmark run tool_use/log_forensics --model anthropic/claude-sonnet-5-5 --attempts 3
benchmark selftest log_forensics
```

Python stdlib only. No network.

## How the data is produced

`fixtures/generator/gen_logs.py` is overlaid into the workspace as `.gen/`, executed by the
`environment.setup` command, then deleted (with `git_init: false`) so the agent cannot read it. The
grader imports the same generator in-process to recompute ground truth and log hashes. To inspect
the data yourself: `python fixtures/generator/gen_logs.py /tmp/lf --print`.

## Layout

| Path | Role |
|---|---|
| `PROMPT.md` | exact task prompt |
| `EVAL.md` | ground truth, traps, scoring, observed selftests |
| `fixtures/workspace/` | docs and deploy history (logs are generated at setup) |
| `fixtures/generator/gen_logs.py` | deterministic data generator (hidden from the agent) |
| `tests/grader.py` | grader (answers, honesty, efficiency, evidence integrity) |
| `REFERENCE_SOLUTION/files/solve.py` | reference solver deriving every answer from the logs |
| `selftest/` | decoys: guessed answers, partial (clock trap), wasteful (whole-file reads) |
