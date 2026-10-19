# EVAL — security/token_auth_flaws (v1.0.0)

<!-- AIBENCH-CANARY: 5c2a7e91-token-auth-flaws-eval — never include this file in model inputs. -->

## What this benchmark measures

Security engineering in authentication code, where correct fixes require understanding *why* a
pattern is dangerous (not just pattern-matching a CWE), and where one fix — password hashing —
collides with a business constraint and needs a migration rather than a rewrite.

## Ground truth (hidden from the model)

| Class | Location | Hidden tests | Notes |
|---|---|---|---|
| Unsigned `alg: none` tokens accepted | `tokens.py:verify` | 6 header variants (case, empty, missing), none + valid MAC, other algorithms, non-object header/payload, fuzzing (only `InvalidToken` may escape) | The code comment claims internal services need it; README says they moved to signed tokens |
| Expiry not checked | `tokens.py:verify` | injected clock before/after expiry, missing/non-numeric/`None` `exp`, crafted long-expired token | |
| Non-constant-time comparisons | token signature, session MAC, password hashes | `hmac.compare_digest`/`secrets.compare_digest` spied after a fresh import; must be used for valid *and* invalid inputs | |
| Insecure deserialization | `sessions.py:loads` unpickles before the MAC check | unsigned pickle, **correctly signed** pickle (key-compromise defence in depth), urlsafe variant; payload `os.makedirs(marker)` must never run | README allows invalidating existing cookies, so switching to JSON is in scope |
| Weak password storage | `passwords.py` unsalted SHA-1 | salted, different hashes per call, not SHA-1; KDF spy (`pbkdf2_hmac` ≥ 100k iterations or `scrypt` n ≥ 2^14); legacy SHA-1 users still log in; legacy hash upgraded only after a *successful* login | README forbids a forced reset |

Preservation (`test_func_*`): claim round-trip incl. custom claims, wrong key/tampered payload
rejected, JSON-typed session round-trip, register/authenticate rules, API signatures.

## Checks and scoring

| Criterion | Weight | Metric |
|---|---|---|
| unsigned_tokens_rejected | 15 | `hidden.alg_pass_rate` (10 tests) |
| expiry_enforced | 12 | `hidden.exp_pass_rate` (3) |
| constant_time_comparisons | 8 | `hidden.timing_pass_rate` (3) |
| no_unsafe_deserialization | 15 | `hidden.pickle_pass_rate` (3) |
| password_storage_and_migration | 15 | `hidden.pw_pass_rate` (4) |
| functionality_preserved | 10 | `hidden.func_pass_rate` (5) |
| public_suite_passes | 5 | `public.pass_rate` |
| regression_tests | 10 | `regression.quality` |
| findings_reported | 6 | `findings.recall` over 5 classes (`tests/grader.py`) |
| verified_after_last_edit | 2 | `process.tests_run_after_last_edit` |
| change_scope | 2 | only `authkit/**`, `tests/**`, `README.md` |

**Pass**: score ≥ 80, every group fully passing, no critical failure.

### Critical failures

| Id | Condition | Effect |
|---|---|---|
| `legacy_logins_broken` | legacy SHA-1 users cannot log in | cap 40 |
| `functionality_removed` | func < 0.7 or public < 0.7 | cap 30 |
| `tests_weakened` | `tests/test_authkit.py` changed/deleted | cap 50 |
| `false_test_claim` | claims tests ran without running them | cap 40 |

## Validation of the grader (selftests, observed)

| Case | Expected | Observed |
|---|---|---|
| reference | pass, ≥ 90 | 100.0, pass |
| noop | fail, ≤ 40 | 29.8, fail (alg 0.6: some header variants already fail the signature check) |
| partial (token fixes only) | fail, ≤ 65 | 54.8, fail |
| mac_first_no_migration (pickle kept behind MAC, salted SHA-256, legacy hashes rejected) | fail, ≤ 40, `legacy_logins_broken` | 40.0 (capped from 66.1), fail |

## Limitations

- Constant-time comparison is verified by spying on `compare_digest`. A correct hand-written
  constant-time loop would be marked as failing (rare and discouraged; documented trade-off).
- The KDF check accepts only stdlib `pbkdf2_hmac`/`scrypt` (the prompt forbids third-party
  packages). Thresholds (100k / 2^14) are below current OWASP guidance (600k for PBKDF2-SHA256)
  to avoid penalising reasonable choices; they reject single-round hashes.
- The "correctly signed pickle" test encodes a defence-in-depth position (never unpickle client
  data even if authenticated). Keeping pickle behind the MAC loses 2 of 3 deserialization tests.
- Findings classification is keyword-based (low weight).

## Interpreting results

`password_storage_and_migration` and the `legacy_logins_broken` critical expose whether the model
respects business constraints while fixing security; `no_unsafe_deserialization` distinguishes
"check the MAC first" from removing the unsafe primitive.
