Fixed token verification: algorithm pinned to HS256, expiry enforced, constant-time signature compare.

```json
{"findings": [{"category": "alg none accepted", "severity": "critical", "location": "tokens.py", "fixed": true}, {"category": "missing expiry", "severity": "high", "location": "tokens.py", "fixed": true}], "tests_run": true, "tests_passed": true}
```
