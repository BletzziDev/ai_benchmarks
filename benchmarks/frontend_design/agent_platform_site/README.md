# frontend_design/agent_platform_site

Hard frontend + design benchmark. The agent builds the static marketing site of "Orbital Agents" (a
fictional enterprise AI-agents platform) from a fixed brief — mandatory palette, system font stacks, exact
copy (`fixtures/workspace/CONTENT.md`), required components and ids — with creative freedom over layout and
visual details. The result is loaded in headless Chromium at 375/768/1280/1920 px, exercised, measured and
screenshotted; screenshots are graded with a rubric by a judge panel or a human.

## Run it

```bash
benchmark run frontend_design/agent_platform_site --model anthropic/claude-sonnet-5-5 --attempts 3 \
  --judge anthropic/claude-opus-5-5          # optional judge; without it the rubric is pending (provisional score)
benchmark selftest agent_platform_site       # validate the grader (no model needed, ~75 s)
benchmark grade --run-id RUN --benchmark agent_platform_site --criterion visual_quality --level 4 \
  --grader "Jane Doe" --evidence "consistent card system, clear CTA hierarchy at 1280"   # human rubric grade
```

Requirements: `pip install -e '.[frontend]'` (Playwright for Python) and a Chromium binary readable by the
unprivileged sandbox user: `AIBENCH_CHROMIUM=/path/to/chrome`, otherwise Playwright's default browser, otherwise
`/opt/pw-browsers/chromium`. If neither Playwright nor Chromium is available the check reports a grader
error (the attempt is not scored as a model failure).

## Layout

| Path | Role |
|---|---|
| `PROMPT.md` | exact task prompt (brief, palette, typography, required ids, permissions) |
| `EVAL.md` | evaluation specification, weights, critical failures, selftest results, limitations |
| `RUBRIC.md` | 1–5 level descriptions for the four visual criteria |
| `benchmark.yaml` | machine-readable configuration |
| `fixtures/workspace/` | `CONTENT.md` (verbatim copy) and `assets/logo-mark.svg` |
| `tests/grader.py` | static checks + launches the probe in an unprivileged, network-isolated sandbox |
| `tests/site_probe.py` | Playwright probe (layout, components, palette, contrast, focus, motion, budgets, screenshots) |
| `REFERENCE_SOLUTION/` | hand-built reference site and report |
| `selftest/` | decoys: naive single page, pretty-but-broken, inaccessible |

## Reproducing the probe by hand

```bash
mkdir -p /tmp/probe && python tests/site_probe.py REFERENCE_SOLUTION/files/site /tmp/probe /opt/pw-browsers/chromium
cat /tmp/probe/result.json   # metrics + evidence; screenshots in /tmp/probe
```
