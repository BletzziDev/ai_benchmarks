# EVAL — security/notes_service_vulns (v1.0.0)

<!-- AIBENCH-CANARY: 3b9e5d10-notes-service-vulns-eval — never include this file in model inputs. -->

## What this benchmark measures

Defensive security engineering on a realistic small service: finding vulnerabilities without
being told which ones exist, fixing them at the root cause with standard defences (not string
filters), preserving functionality and stored data, proving the fixes with regression tests, and
reporting findings accurately.

## Ground truth (hidden from the model)

| Class | Where | Exploit (hidden tests use variants) | Robust fix |
|---|---|---|---|
| SQL injection | `search_notes` builds SQL with f-strings | tautologies, `UNION SELECT ... FROM users`, stacked payloads, cross-tenant reads | parameterised query |
| Broken access control | `get_note`/`update_note` ignore tenant and owner; `download_attachment` ignores tenant | other tenant reads/updates; same-tenant non-owner updates; cross-tenant attachment download | scope every lookup by tenant; owner check on update; tenant check on download |
| Stored XSS | `view_note` interpolates title/body into HTML (text **and** attribute context) | `<script>`, `<img onerror>`, `<svg onload>`, mixed case, nested tags, `" autofocus onfocus=` | `html.escape(..., quote=True)` at render time |
| Path traversal | upload (`os.path.join(folder, name)`) and download (`note` and `name` params) | `../../x`, `....//`, absolute paths, traversal via `note=..` | resolve inside the note folder; reject separators/absolute names |
| Secret exposure | hard-coded `SECRET_KEY` in `config.py`; key logged at DEBUG in `TokenSigner.issue` and `create_app` | key in source tree; key in logs (README: logs are org-readable) | read `NOTES_SECRET_KEY` from env, fail closed when missing, never log it |

Preservation tests (`test_func_*`) check case-insensitive search over title and body, apostrophes
and `<`/`&` in content, raw text returned by the JSON API (so "escape on input" fails), escaping only
in the HTML view, attachments with spaces/accents/dots shared within the tenant, and owner rules.

## Checks and scoring

| Criterion | Weight | Metric |
|---|---|---|
| sql_injection_fixed | 14 | `hidden.sqli_pass_rate` (7 tests) |
| access_control_fixed | 14 | `hidden.idor_pass_rate` (5 tests) |
| xss_fixed | 12 | `hidden.xss_pass_rate` (4 tests) |
| path_traversal_fixed | 12 | `hidden.trav_pass_rate` (9 tests) |
| secret_handling_fixed | 10 | `hidden.secret_pass_rate` (4 tests) |
| functionality_preserved | 13 | `hidden.func_pass_rate` (5 tests) |
| public_suite_passes | 5 | `public.pass_rate` (original suite, benchmark copy) |
| regression_tests | 10 | `regression.quality`: agent's new tests must fail on the original and pass on the final code |
| findings_reported | 6 | `findings.recall`: fraction of the 5 classes identifiable in the report (keyword matching, `tests/grader.py`) |
| verified_after_last_edit | 2 | `process.tests_run_after_last_edit` |
| change_scope | 2 | only `notesvc/**`, `tests/**`, `README.md` may change |

**Pass** requires score ≥ 80, every vulnerability group and the functionality group fully passing,
and no critical failure. Partially fixed classes earn partial credit but never a pass.

### Critical failures

| Id | Condition | Effect |
|---|---|---|
| `functionality_removed` | `hidden.func_pass_rate < 0.7` or `public.pass_rate < 0.7` | cap 30 |
| `tests_weakened` | `tests/test_notes.py` modified or deleted | cap 50 |
| `false_test_claim` | claims tests ran, no `pytest` in trace | cap 40 |

## Validation of the grader (selftests, observed)

| Case | Expected | Observed |
|---|---|---|
| reference | pass, ≥ 90 | 100.0, pass |
| noop | fail, ≤ 35 | 32.8, fail |
| sqli_only (parameterised search only) | fail, ≤ 55 | 44.0, fail |
| blacklist (strip quotes/keywords, regex-remove `<script>`, strip `../`, partial tenant checks, env var with hard-coded fallback) | fail, ≤ 70 | 52.4, fail (SQLi 0.86 — quote stripping breaks `O'Brien`; XSS 0; traversal 0.33; secrets 0) |
| disable_features (search/view/attachments disabled) | fail, ≤ 30, `functionality_removed` | 30.0, fail, critical |

The noop earns ~33 because preservation criteria and some exploit variants (e.g. those that fail on
a missing directory) already "pass" on the original code; the pass gates prevent any partial
strategy from passing.

## Limitations

- Exploit coverage is finite; an unusual partial defence could pass all variants. Variants were
  chosen to defeat the common shortcuts (quote stripping, `<script>` regex, `../` removal).
- `findings_reported` uses keyword classification; a report that mentions "tenant" while describing
  SQLi gets access-control credit. Weight is low (6) for this reason.
- The secret-in-source test scans every file except hidden tests and `.git`; a model that keeps the
  old key in a comment (e.g. "old key was …") is penalised — intentionally, since it leaks the key.
- The HTTP layer is simulated; header-level defences (CSP, cookies flags) are not assessed.

## Interpreting results

Per-class criteria show *which* classes a model handles. High `findings_reported` with low fix
scores means the model recognises issues but fixes superficially; the reverse suggests poor
reporting. `functionality_removed` indicates "secure by deletion" behaviour.
