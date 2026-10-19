# security/token_auth_flaws

Hard defensive-security benchmark on an authentication library (`authkit`, Python stdlib):
alg-none tokens, missing expiry checks, timing-unsafe comparisons, pickle deserialization of
client cookies, and unsalted SHA-1 passwords that must be migrated without forcing resets.

```bash
benchmark run security/token_auth_flaws --model <label> --attempts 3
benchmark selftest security/token_auth_flaws
```

| Path | Role |
|---|---|
| `PROMPT.md` | exact prompt |
| `EVAL.md` | ground truth, scoring, critical failures, observed selftests, limitations |
| `fixtures/workspace/` | `authkit` + public tests + operational README |
| `tests/hidden/` | attack-variant, migration and preservation tests |
| `tests/public/` | benchmark copy of the public tests |
| `tests/grader.py` | findings-report classifier |
| `REFERENCE_SOLUTION/` | reference fix, regression tests, report |
| `selftest/` | decoys `partial`, `mac_first_no_migration` and their reports |
