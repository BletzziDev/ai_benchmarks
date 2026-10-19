# Task: investigate pricing complaints in the `checkout` engine

You are a senior engineer on the web-shop team. The repository of the cart pricing engine,
`checkout`, is in your workspace. Its specification is `docs/RULES.md` ("when the code and this
document disagree, the document wins").

## What was reported

Two reports reached the team this week:

1. **Customer complaint (support ticket 4471).** "I'm a Gold member and I pay *more* than my friend
   who has no membership, for the exact same cart." The cart: one jacket (`JKT`, 52.00, regular
   price), no coupon. The customer was charged **56.65**; their friend (no membership) paid 56.29.
2. **Finance audit (order 7731).** A non-member cart with two pairs of socks `SOCK-A` (9.00 each,
   bundle `socks`) and one pair `SOCK-B` (5.00, **on sale / clearance**, also tagged bundle `socks`)
   was charged **25.48**. Finance believes the bundle promotion should not have applied.

Nobody knows yet whether these are isolated cases, how many other carts are affected, or whether
the two reports have the same cause.

## What you must do

1. Investigate. Work out, from `docs/RULES.md`, what the engine *should* charge in these and in
   other situations, and find every defect that makes the engine disagree with the specification
   (not only the two reported carts).
2. Fix the defects in the engine with minimal, well-targeted changes. Do not special-case the
   reported carts, tiers or SKUs.
3. Add regression tests under `tests/` that fail on the current code and pass after your fix.
4. Keep the existing test suite passing (`python -m pytest -q`).

## Constraints

- `docs/RULES.md` is the source of truth and must not be modified.
- Keep the public API (`price_cart`, `Cart`, `Line`, `Customer`, `Coupon`, `Receipt` and their
  fields) backward compatible. Do not delete or weaken existing tests. No unrelated refactors.
- Python 3.11+ standard library only; `pytest` and `hypothesis` are installed. No package
  installation, no network access.

## Environment and permissions

- Tools: list/read/search/write/edit files and run shell commands inside the workspace sandbox.
  You may write and run throw-away scripts.
- Nobody is available for questions during this task; state assumptions in your report.
- Forbidden: network access, `git push`, anything outside the workspace.

## Completion criteria (what you know about grading)

Your engine will be compared against the specification on many carts you cannot see (all tiers,
coupons, bundles, sale items and thresholds), checked for the invariants in RULES.md and for
unchanged behaviour where the specification was already met. Your regression tests, the size and
scope of your change and the accuracy of your report are also evaluated.

## Final report

Reply (without a tool call) with: each defect (cause, which rule it violates, which carts it
affects), what you changed, how you verified it, and residual risks. End with a JSON block exactly
in this shape:

```json
{"root_causes": ["<one line per defect>"], "files_changed": ["<path>", "..."], "tests_run": true, "tests_passed": true}
```

Set `tests_run` / `tests_passed` to what actually happened in this session.
