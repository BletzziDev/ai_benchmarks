## Design
A dark Ink hero with a product "agent console" visual (live steps, an approval waiting on a human, guardrail
and audit counters) makes supervised autonomy tangible. Light sections alternate Paper/Mist; Orbit is
reserved for actions and links, Mint for status/accents only. 4px spacing scale, system font stack.

## Responsiveness and accessibility
Mobile-first grid that steps from 1 to 2/3/4 columns; header collapses into a toggle below 768px. Skip
link, landmarks, one h1, labelled fields with linked error messages and focus management, visible focus
rings (Mint on dark backgrounds), reduced-motion guards for the pulse animation, hover lift and smooth scroll.

## Limitations
No browser was available in the sandbox, so behaviour was verified by reading the code.

```json
{"entry_point": "site/index.html", "files": ["site/index.html", "site/styles.css", "site/main.js", "site/logo-mark.svg"], "known_issues": ["Layout not verified in a real browser during the session"]}
```
