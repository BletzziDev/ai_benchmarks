# Task: build the marketing website for Orbital Agents

You are a senior front-end engineer and product designer. Build the public website of
**Orbital Agents**, a (fictional) startup that sells a platform for running supervised autonomous
AI agents inside large enterprises. The workspace contains the exact copy (`CONTENT.md`) and the
logo mark (`assets/logo-mark.svg`).

You have creative freedom over layout, composition, illustration (CSS/inline SVG), micro-interactions
and visual details. The constraints below are fixed and identical for every participant.

## Brand

- Personality: calm, precise, trustworthy; technical but warm. Confident, never hype-y.
  The site should feel like a serious enterprise product, not a toy or a crypto landing page.
- Audience: COOs, heads of operations, CIOs and risk/compliance leaders at large companies.

## Colour palette (mandatory)

Use **only** these colours. Transparency (alpha) of a palette colour is allowed. Gradients may only
use palette colours. Do not use any other colour value anywhere (including borders, shadows on
text-bearing elements, SVG fills/strokes and pseudo-elements). Default browser colours (pure black
text, default blue links) are not in the palette.

| Token | HEX | Intended use |
|---|---|---|
| Ink | `#0B1020` | primary text; dark sections |
| Slate | `#4A5568` | secondary text on light backgrounds |
| Paper | `#FFFFFF` | page background; text on dark/Orbit backgrounds |
| Mist | `#F3F5FA` | alternate section and card backgrounds |
| Line | `#DCE1EC` | borders and dividers; secondary text on Ink |
| Orbit | `#3346E8` | primary actions, links, focus rings on light backgrounds |
| Mint | `#19C3A0` | accents and highlights; never as text on light backgrounds |

## Typography (mandatory)

- No web fonts: do not load any font files (no `@font-face`, no font services).
- Sans stack for all text: `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`.
  Optional mono stack for small technical labels: `ui-monospace, "SF Mono", Menlo, Consolas, monospace`.
- The h1 is at least 40px on desktop (≥ 1280px wide) and at least 30px at 375px.
- Body/paragraph text is at least 16px with a line-height between 1.4 and 1.8.
- Clear hierarchy: exactly one `h1` (the hero headline); no skipped heading levels.

## Required structure and components

Use these exact ids/attributes; they are part of the specification.

1. `<html lang="en">`. The first focusable element is a skip link `<a href="#main">Skip to content</a>`
   that may be visually hidden until focused, and must be visible when focused.
2. `<header>` with the wordmark, a `<nav aria-label="Primary">` containing the five links from
   `CONTENT.md` (hrefs `#features`, `#how-it-works`, `#pricing`, `#faq`, `#contact`) and the header CTA.
3. **Mobile navigation:** below 768px wide the nav links are hidden behind a `<button id="nav-toggle">`
   with `aria-controls` and `aria-expanded`. Activating it shows the links and sets
   `aria-expanded="true"`; activating it again hides them. At 768px and wider the links are always
   visible and the toggle is hidden.
4. `<main id="main">` containing, in order: `section#hero`, a proof-points band, `section#features`,
   `section#how-it-works`, `section#customers`, `section#pricing`, `section#faq`, `section#contact`.
5. `section#hero`: the h1, eyebrow, subheadline, primary CTA `<a id="hero-cta" href="#contact">` and
   the secondary CTA.
6. `section#features`: the six features, each title as an `h3`.
7. `section#how-it-works`: the four steps as an ordered list (`<ol>`).
8. `section#customers`: the six text logos and the three testimonials, each in a `<blockquote>`.
9. `section#pricing`: a billing switch `<button id="billing-toggle" role="switch" aria-checked="false">`
   (Monthly is the default). Toggling it sets `aria-checked="true"` and shows the annual prices; toggling
   again returns to monthly. Each plan card has `data-plan="starter" | "growth" | "enterprise"` and
   contains one element with a `data-price` attribute whose text is the displayed price (e.g. `$49`).
10. `section#faq`: an accordion. Each question is a `<button>` (inside a heading) with `aria-expanded`
    and `aria-controls` pointing to its answer panel. Panels start collapsed (not visible); activating a
    question shows its panel and sets `aria-expanded="true"`; activating it again collapses it.
11. `section#contact`: `<form id="demo-form" novalidate>` with the fields from `CONTENT.md` using the
    given `name` attributes, each with a visible `<label>`. On submit, validate on the client:
    - invalid fields get `aria-invalid="true"` and an error message (the copy from `CONTENT.md`) that is
      visible and referenced by the field's `aria-describedby`;
    - focus moves to the first invalid field;
    - when everything is valid, show the success message in an element `#form-status` that has
      `role="status"`, and do not navigate or send any network request.
12. `<footer>` with the copyright line and links.

## Responsiveness

The layout must work at 375, 768, 1280 and 1920px wide with **no horizontal scrolling**, readable line
lengths and touch targets of at least 24×24px for buttons, form controls and navigation links.

## Accessibility (WCAG 2.2 AA)

Text contrast ≥ 4.5:1 (≥ 3:1 for large text), visible labels for every form control, accessible names for
all links and buttons, `alt` on every `<img>`, full keyboard operability with a clearly visible focus
indicator, and respect for `prefers-reduced-motion: reduce` (no animations; no smooth scrolling).

## Technical constraints

- Deliverable: a static site in `site/` with entry point `site/index.html`. Plain HTML, CSS and vanilla
  JavaScript only. No frameworks or libraries (no React/Vue/jQuery/Bootstrap/Tailwind, etc.), no build
  step, no CDNs.
- `site/` must be self-contained: no request may leave the site (no external URLs of any kind). Copy any
  asset you use from `assets/` into `site/`.
- Budget: total transferred size of the page ≤ 300 KB and ≤ 20 requests. No console errors.
- Avoid inline event handler attributes (`onclick=` …); define colours as CSS custom properties.

## Environment and permissions

- Tools: list/read/search/write/edit files and run shell commands inside the workspace sandbox.
  Only Python 3 is available for scripting. No browser is provided, there is no network access and you
  cannot install packages. Nobody is available to answer questions; state assumptions in your report.
- Forbidden: network access, files outside the workspace, modifying `CONTENT.md` or `assets/`.

## Completion criteria (what you know about grading)

The site is loaded in a headless browser at the four widths. Automated checks verify the structure and
components above, interaction behaviour, layout overflow, palette and typography adherence, contrast,
labels, keyboard focus, reduced motion, request/size budgets and console errors. Full-page screenshots are
graded with a rubric for visual quality, hierarchy and composition, brand fit and polish. Loading without
errors is necessary but not sufficient.

## Final report

When finished, reply (without a tool call) with a short report: design decisions, how you addressed
responsiveness and accessibility, known limitations. End with a JSON block exactly in this shape:

```json
{"entry_point": "site/index.html", "files": ["<path>", "..."], "known_issues": ["<issue>", "..."]}
```
