Fixed the race conditions in the payment processor. Verified with the test suite.

```json
{"root_causes": ["check-then-act race on idempotency key", "non-atomic balance check and debit"], "files_changed": ["payflow/processor.py"], "tests_run": true, "tests_passed": true}
```
