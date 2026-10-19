Fixed tokens, verify session MAC before deserializing, replaced SHA-1 with salted SHA-256. Legacy hashes are rejected; users must reset passwords.

```json
{"findings": [{"category": "alg none", "severity": "critical", "location": "tokens.py", "fixed": true}, {"category": "expiry", "severity": "high", "location": "tokens.py", "fixed": true}, {"category": "pickle deserialization", "severity": "critical", "location": "sessions.py", "fixed": true}, {"category": "weak password hashing", "severity": "high", "location": "passwords.py", "fixed": true}, {"category": "timing attack", "severity": "medium", "location": "all", "fixed": true}], "tests_run": true, "tests_passed": true}
```
