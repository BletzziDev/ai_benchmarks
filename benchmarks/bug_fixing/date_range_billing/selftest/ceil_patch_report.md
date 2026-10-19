Days with a DST transition are 23h, so floor division lost a day. I now round up.

```json
{"root_causes": ["floor division of UTC seconds drops 23-hour days"], "files_changed": ["billing/periods.py", "tests/test_dst_proration.py"], "tests_run": true, "tests_passed": true}
```
