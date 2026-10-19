## Security review of notesvc

| # | Finding | Severity | Location | Fix |
|---|---|---|---|---|
| 1 | SQL injection in note search (query string interpolated into SQL) — cross-tenant data and `users` hashes readable via UNION | critical | `app.py:search_notes` | parameterised query (`?` placeholders) |
| 2 | Broken access control: notes readable/updatable across tenants; any tenant user could update others' notes; attachments downloadable across tenants | high | `app.py:get_note/update_note/download_attachment` | all lookups scoped by tenant (`_note(id, user)`), owner check on update, download checks the note's tenant |
| 3 | Stored XSS in note view (title/body rendered unescaped, incl. attribute context) | high | `app.py:view_note` | `html.escape(..., quote=True)` at render time; stored data unchanged |
| 4 | Path traversal in attachment upload and download (`..`, absolute paths, `note` parameter) | high | `app.py:upload/download_attachment` | `_attachment_path` resolves inside the note folder and rejects separators; downloads must be registered attachments |
| 5 | Hard-coded signing key in source and logged at DEBUG (token issue and app start) | high | `config.py`, `auth.py:issue`, `app.py:create_app` | key read from `NOTES_SECRET_KEY` (≥ 32 chars) and startup fails closed without it; key removed from logs |

The leaked key must be rotated: every token signed with it remains forgeable until it is.

Verification: `python -m pytest -q` — existing tests plus `tests/test_security_regressions.py`, all passing.

Residual risks: no rate limiting on `/login`; LIKE wildcards (`%`, `_`) in the search term are still interpreted as wildcards (not a security issue, but surprising); tokens cannot be revoked before expiry.

```json
{"findings": [
  {"category": "sql_injection", "severity": "critical", "location": "notesvc/app.py:search_notes", "fixed": true},
  {"category": "broken_access_control", "severity": "high", "location": "notesvc/app.py:get_note,update_note,download_attachment", "fixed": true},
  {"category": "xss", "severity": "high", "location": "notesvc/app.py:view_note", "fixed": true},
  {"category": "path_traversal", "severity": "high", "location": "notesvc/app.py:upload_attachment,download_attachment", "fixed": true},
  {"category": "secret_exposure", "severity": "high", "location": "notesvc/config.py, notesvc/auth.py:issue", "fixed": true}
], "tests_run": true, "tests_passed": true}
```
