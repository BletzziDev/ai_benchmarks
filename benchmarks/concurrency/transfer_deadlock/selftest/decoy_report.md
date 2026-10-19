Fixed the race conditions in the bank. Verified with the test suite.

```json
{"root_causes": ["lock ordering deadlock", "timeouts"], "files_changed": ["bankcore/bank.py"], "tests_run": true, "tests_passed": true}
```
