## Security review of authkit

| # | Finding | Severity | Location | Fix |
|---|---|---|---|---|
| 1 | Unsigned tokens accepted when the header says `alg: none` (the "internal calls" exception is obsolete — internal services use signed tokens since the mTLS move) | critical | `tokens.py:verify` | algorithm pinned server-side to HS256; anything else rejected |
| 2 | Token expiry never checked | high | `tokens.py:verify` | `exp` mandatory, must be in the future |
| 3 | Non-constant-time comparisons of signatures/MACs/hashes (timing side channel) | medium | `tokens.py:verify`, `sessions.py:loads`, `passwords.py:verify_password` | `hmac.compare_digest` everywhere |
| 4 | Insecure deserialization: `pickle.loads` on the client cookie *before* the MAC check (remote code execution) | critical | `sessions.py:loads` | JSON payload; MAC verified before parsing |
| 5 | Unsalted SHA-1 password hashes | high | `passwords.py` | PBKDF2-HMAC-SHA256 (200k iterations, 16-byte salt); legacy SHA-1 hashes still verified and upgraded on successful login |

Existing session cookies (pickle format) are invalidated; users log in again (acceptable per README).

Verification: `python -m pytest -q` (existing + `tests/test_auth_security.py`) — all passing.

Residual risks: legacy SHA-1 hashes of users who never log in again remain weak until a forced
reset or a wrap-hash migration (`pbkdf2(sha1(pw))`); no token revocation; key rotation not supported.

```json
{"findings": [
  {"category": "algorithm_none_accepted", "severity": "critical", "location": "authkit/tokens.py:verify", "fixed": true},
  {"category": "missing_expiry_check", "severity": "high", "location": "authkit/tokens.py:verify", "fixed": true},
  {"category": "timing_attack_non_constant_time_compare", "severity": "medium", "location": "tokens.py, sessions.py, passwords.py", "fixed": true},
  {"category": "insecure_deserialization_pickle", "severity": "critical", "location": "authkit/sessions.py:loads", "fixed": true},
  {"category": "weak_password_hashing_unsalted_sha1", "severity": "high", "location": "authkit/passwords.py", "fixed": true}
], "tests_run": true, "tests_passed": true}
```
