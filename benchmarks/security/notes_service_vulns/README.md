# security/notes_service_vulns

Hard defensive-security benchmark (Python stdlib). The agent reviews and fixes `notesvc`, a
multi-tenant notes service with five vulnerability classes it is not told about, without removing
features, and adds regression tests.

```bash
benchmark run security/notes_service_vulns --model <label> --attempts 3
benchmark selftest security/notes_service_vulns
```

| Path | Role |
|---|---|
| `PROMPT.md` | exact prompt |
| `EVAL.md` | ground truth, scoring, critical failures, observed selftests, limitations |
| `fixtures/workspace/` | the vulnerable service + public tests + ops README |
| `tests/hidden/` | exploit-variant and preservation tests (never shown to the model) |
| `tests/public/` | benchmark copy of the original public tests |
| `tests/grader.py` | findings-report classifier |
| `REFERENCE_SOLUTION/` | reference fix, regression tests, report |
| `selftest/` | decoys: sqli_only, blacklist, disable_features (+ their reports) |

Manual reproduction: copy `fixtures/workspace`, overlay `REFERENCE_SOLUTION/files`, copy
`tests/hidden/` into `.aibench_tests/hidden/` and run `python -m pytest .aibench_tests/hidden`.
