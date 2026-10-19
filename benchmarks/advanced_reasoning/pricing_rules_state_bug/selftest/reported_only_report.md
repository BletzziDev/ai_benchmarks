Two defects: shipping threshold used the post-membership total; sale lines joined bundles. Both fixed.

```json
{"root_causes": ["shipping threshold after membership", "sale lines in bundles"], "files_changed": ["checkout/rules/shipping.py", "checkout/rules/bundles.py", "tests/test_pricing_regressions.py"], "tests_run": true, "tests_passed": true}
```
