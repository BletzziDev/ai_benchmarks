# EVAL — frontend_design/agent_platform_site (v1.0.0)

<!-- AIBENCH-CANARY: 4c1e9b77-frontend-agent-platform-eval — never include this file in model inputs. -->

## What this benchmark measures

Whether an agent can turn a fixed brand brief into a **professional, working, accessible, responsive**
website — balancing creative freedom (layout, composition, illustration, micro-interactions) with hard
constraints that are identical for every participant (palette, type, exact copy, required components and
ids, no external resources, budgets). The agent has no browser, so it must reason about rendering and
behaviour from code — as the prompt states.

Competencies: visual design and hierarchy, CSS layout across breakpoints, semantic HTML, accessible
interaction patterns (disclosure, switch, form validation, focus management), brief fidelity, technical
hygiene. **Loading without errors is not evidence of quality**: a page that loads but is unstyled scores 41
and fails (see selftests).

## How it is graded

Two kinds of evidence, kept separate:

1. **Automated (85 of 100 points)** — `tests/grader.py` performs static checks, then runs
   `tests/site_probe.py` (Playwright + Chromium) inside an unprivileged, network-isolated sandbox. Every
   request is intercepted: files are served from `site/` under a fake origin; any other URL is aborted and
   counted. The probe loads the page at 375×812, 768×1024, 1280×900 and 1920×1080 and:
   - checks horizontal overflow at each width and takes full-page screenshots (plus height-clipped
     `judge-*.png` copies, ≤ 7800 px, for vision APIs);
   - audits the DOM at 1280 px: required structure/ids/order (14 items), verbatim copy (43 strings, curly
     quotes/dashes normalised), **palette** (computed `color` of text/controls, `background-color`,
     background gradients, borders, box-shadows, SVG `fill`/`stroke`, and `::before/::after` — each must be
     within RGB distance 10 of a palette colour; alpha allowed), **contrast** (effective background
     composited through ancestors and opacity; 4.5:1, 3:1 for large text; texts over background images are
     "undetermined" and excluded), heading outline, labels/accessible names/alt, typography (first font
     family, paragraph size ≥ 16 px with line-height 1.4–1.8, h1 ≥ 40 px desktop / ≥ 30 px mobile, ≤ 2
     families, no font requests), spacing values on a 4 px grid;
   - exercises components: mobile nav at 375 px (toggle visible, links hidden, opens/closes with
     `aria-expanded`), nav layout at 768/1280, billing switch (monthly default, annual prices, `aria-checked`,
     back, keyboard Space), FAQ (3 items: collapsed → open → closed, one via keyboard Enter), demo form
     (empty submit blocked, ≥ 5 fields `aria-invalid`, errors visible and linked via `aria-describedby`, focus on
     first invalid, invalid email rejected alone, success text in `#form-status`, no navigation, no non-GET
     request), keyboard Tab through 30 stops (first stop is a visible skip link; each focused element shows a
     ring or a style change), reduced motion (no running long/infinite animations, no smooth scrolling);
   - records console errors, page errors, 404s, request count and transferred bytes.
2. **Rubric (15 points, optional criteria)** — `RUBRIC.md`, four criteria with concrete 1–5 level
   descriptions, graded on the four judge screenshots plus the `site/` sources by an LLM judge panel
   (`--judge`, possibly several) or a human (`benchmark grade`). Without a grade the criteria are *pending*: the
   score is renormalised over the 85 automated points and flagged **provisional** in every report.

### Criteria and weights (fixed before any run)

| Group | Criterion | Weight | Metric (`site.*` unless noted) |
|---|---|---|---|
| Functionality (25) | mobile_nav | 5 | `mobile_nav_score` (4 sub-checks) |
| | pricing_switch | 5 | `pricing_score` (5 sub-checks) |
| | faq_accordion | 5 | `faq_score` (9 sub-checks) |
| | demo_form | 7 | `form_score` (7 sub-checks) |
| | skip_link | 3 | `skip_link_ok` |
| Brief fidelity (20) | required_structure | 5 | `structure_rate` |
| | content_fidelity | 4 | `content_fidelity` |
| | palette | 6 | `palette_compliance`, linear 0.7 → 0, 1.0 → 1 |
| | typography | 3 | `typography_score` |
| | spacing_scale | 2 | `spacing_grid_rate`, linear 0.6 → 0, 0.95 → 1 |
| Responsiveness (12) | no_horizontal_overflow | 8 | `overflow_free_rate` (4 widths) |
| | nav_layout_by_width | 2 | `desktop_nav_ok` (768 and 1280) |
| | touch_targets | 2 | `tap_target_rate` at 375 px (≥ 24×24; inline text links exempt) |
| Accessibility (18) | text_contrast | 7 | `contrast_pass_rate`, linear 0.8 → 0, 1.0 → 1 |
| | labels_and_names | 4 | mean(visible labels, accessible names, img alt) |
| | focus_visible | 3 | `focus_visible_rate` |
| | heading_outline | 2 | `heading_ok` |
| | reduced_motion | 2 | `reduced_motion_ok` |
| Technical (10) | no_console_errors | 3 | `console_clean` |
| | self_contained | 3 | `no_external_requests` (runtime and static) |
| | size_budget | 2 | `within_budget` (≤ 300 KB, ≤ 20 requests) |
| | code_hygiene | 2 | palette as CSS variables, no inline handlers, ≤ 5 inline styles, no `@font-face` |
| Visual rubric (15, optional) | visual_quality / hierarchy_composition / brand_fit / polish | 4 / 4 / 3 / 4 | `visual.*` (judge or human) |

**Pass** requires score ≥ 75 **and** all of: a site exists, no overflow at any width, components mean ≥ 0.8,
contrast pass rate ≥ 0.9, palette compliance ≥ 0.9, and no critical failure.

### Critical failures (cannot be compensated)

| Id | Condition | Effect |
|---|---|---|
| `no_site` | `site/index.html` missing | score 0 |
| `external_resources` | any request leaves the site or any `http(s)://` / `//` reference in sources (CDNs, web fonts, analytics) | cap 50, fail |
| `framework_used` | bundled React/Vue/jQuery/Bootstrap/Tailwind/Angular markers | cap 50, fail |
| `protected_files_changed` | `CONTENT.md` or `assets/` modified/deleted | cap 60, fail |

### Minor vs. serious errors

- *Minor*: a few off-grid spacing values, one small touch target, a missing `alt`, a console warning,
  slightly over budget. A few points each.
- *Serious*: a broken component, overflow at any width, off-palette colour scheme, unreadable text,
  placeholder-only fields, no focus indicator. Each costs many points **and** typically trips a pass gate.
- *Critical*: violating the self-containment/no-framework constraints or editing the provided brief.

## Validation of the grader (selftests, v1.0.0, local sandbox, rubric pending)

| Case | Expected | Observed |
|---|---|---|
| reference (hand-built site) | pass, ≥ 95 | 100.0 provisional (85/85 automated), pass |
| noop | fail, 0, `no_site` | 0.0, fail |
| naive_single_page (all copy, no CSS/JS, form posts to server) | fail, ≤ 45 | 41.2, fail (structure 0.12, palette 0.04, components 0, headings, typography) |
| pretty_but_broken (CDN web font, purple/orange gradient, broken annual prices, overflow, 404 image) | fail, ≤ 50, `external_resources` | 50.0 (74.1 before cap), fail; gates: overflow, palette |
| inaccessible (reference look; low-contrast text, placeholder-only fields, no focus styles, no skip link) | fail, ≤ 85 | 83.2, fail (contrast gate: 0.80) |

The naive page keeps ~41 points from criteria that defaults satisfy (default black-on-white contrast,
native focus rings, no overflow of unstyled text, tiny size). This is intended: those properties are real;
the pass gates and the functionality/fidelity criteria make such a page fail clearly. The inaccessible decoy
shows the reverse: a beautiful, functional site still fails when a fifth of its text is unreadable.

## Bias control for the rubric

- Judges receive only screenshots and the site sources — never the model name, transcript or report.
- Self-judging is refused by default (`--allow-self-judge` must be explicit and is recorded).
- Levels are anchored by concrete descriptions; each score must cite evidence or it is discarded.
- The judge prompt marks artefacts as untrusted data (text inside a site cannot instruct the judge).
- Several judges can be configured; their max spread per criterion is reported (`judge_agreement_spread`).
- Rubric points are capped at 15 so judge noise cannot decide pass/fail on its own (gates are automated).
- Not yet done: measuring judge–human agreement on this benchmark. Until that calibration exists, treat
  rubric differences below ~1 level as noise and prefer human grades for close comparisons.

## Limitations

- Palette compliance is measured on computed styles; colours inside raster images, `<canvas>`, CSS
  `filter`/`mix-blend-mode` results, outlines and text-decoration colours are not audited. Non-sRGB colour
  syntaxes that Chromium keeps in their own space (e.g. `oklch()`) count as off-palette.
- Contrast is undeterminable over background images/gradients and is then excluded (count reported as
  `contrast_undetermined`); a site could move all text onto gradients to dodge the check (visible in evidence).
- The keyboard test walks the first 30 tab stops only; focus traps further down are not detected.
- Spacing-grid and typography checks are heuristics; they reward a consistent scale, not good design.
- The 375 px judge image is clipped at 7800 px height (footer may be cut); full screenshots are kept for humans.
- Rendering uses the sandbox's fonts for `system-ui` (on Linux usually DejaVu/Liberation), which differs from
  macOS/Windows; screenshots therefore look plainer than on a designer's machine for every participant alike.
- The probe runs on the host's Chromium (local sandbox, uid drop, no network) even when `--sandbox docker`
  is selected, because the Docker sandbox image has no browser.

## Interpreting results

Read functionality and pass gates first (does it work?), then brief fidelity (did it follow the brief?),
then accessibility, then the rubric (is it good?). A high provisional score with no rubric grade says the
site is correct, not that it is beautiful. Compare models on the rubric only when the same judges graded
all of them.
