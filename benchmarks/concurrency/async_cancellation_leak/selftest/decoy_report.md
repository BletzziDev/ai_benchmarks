Fixed the connection leaks and shutdown in the job runner. Verified with the test suite.

```json
{"root_causes": ["connections leaked on cancellation", "shutdown"], "files_changed": ["jobq/runner.py"], "tests_run": true, "tests_passed": true}
```
