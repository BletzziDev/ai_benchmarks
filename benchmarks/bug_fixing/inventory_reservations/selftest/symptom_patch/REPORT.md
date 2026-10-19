Availability could go negative and could be stale. I now clamp availability at zero and read through to the repository.

```json
{"root_causes": ["stale cache and negative availability"], "files_changed": ["stockroom/service.py", "tests/test_inc_2291.py"], "tests_run": true, "tests_passed": true}
```
