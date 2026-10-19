# Task: security review and remediation of `authkit`

You maintain `authkit`, the shared authentication library of the Acme web apps (Python standard
library only). It is in your workspace. An external penetration test is scheduled next week and
you must **find and fix the security flaws in the library before then**.

## Context

- `README.md` lists operational facts (who presents tokens, where cookies live, the state of the
  users table, how internal services authenticate). Treat them as true and binding.
- Docstrings describe the intended security properties of each component.

## What you must do

1. Review `authkit/` and identify every security flaw. Consider attackers who can craft tokens and
   cookies, observe response timing, and steal a database dump.
2. Fix each flaw at its root using standard, well-understood techniques from the Python standard
   library. Do not add third-party dependencies.
3. Respect the business constraints in `README.md` (in particular regarding existing users and
   existing sessions). If a fix requires a migration, implement it in the library.
4. Add regression tests in **new** files under `tests/`. Do not modify or delete
   `tests/test_authkit.py`.
5. Run the test suite (`python -m pytest -q`).

## Constraints

- Keep the public API backward compatible: `TokenService(key, ttl_seconds=..., clock=...)`,
  `issue`, `verify`, `SessionCodec.dumps/loads`, `UserStore`, `register`, `authenticate`,
  `hash_password`, `verify_password`, and the exception types.
- Session data only ever contains JSON-compatible values (str, int, float, bool, None, lists, dicts).
- No network access; exploits you write must target only this library in-process.

## Environment and permissions

Tools: list/read/search/write/edit files and run shell commands in the workspace sandbox. Nobody
is available for questions; state your assumptions in the report. Forbidden: network access,
`git push`, anything outside the workspace.

## Completion criteria (what you know about grading)

Hidden tests attack every flaw class present with realistic variants, check backward
compatibility and the business constraints, and evaluate your regression tests, your findings
report and whether you verified your work.

## Final report

Reply (without a tool call) with each finding (what, where, impact, severity, fix), migration
notes, verification, and residual risks. End with a JSON block exactly in this shape:

```json
{"findings": [{"category": "<flaw class>", "severity": "critical|high|medium|low", "location": "<file:function>", "fixed": true}], "tests_run": true, "tests_passed": true}
```

Set `tests_run` / `tests_passed` to what actually happened in this session.
