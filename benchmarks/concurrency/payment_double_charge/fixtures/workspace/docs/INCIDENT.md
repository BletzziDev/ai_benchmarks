# PAY-417 — duplicate card charges and a negative prepaid balance

Timeline (production, 2025-04-02):

- 14:02:11 order 88412: `pay(acct-7731, 4900, key=co-88412)` from the checkout handler. The
  gateway was slow (p99 at 12 s that afternoon).
- 14:02:21 the checkout client timed out after 10 s and retried with the same key `co-88412`.
- 14:02:23 both requests returned success with different charge ids (`ch_771201`, `ch_771202`).
  The customer was charged twice; the prepaid balance was debited twice.
- 14:05:40 account `acct-1290` (balance 6000) paid two different orders of 4000 within ~1 s
  (web + mobile app). Both succeeded; the balance ended at -2000.
- Reconciliation also found an account whose final balance did not match the sum of its
  successful payments (one debit seems to have been lost).

Support asks for "no more double charges". Finance asks for "balances that add up".
