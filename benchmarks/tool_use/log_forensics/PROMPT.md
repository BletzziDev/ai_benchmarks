# Task: post-incident log forensics for the 2025-03-11 checkout outage

On 2025-03-11 checkouts failed for a while. You are preparing the evidence for the post-incident
review. Your workspace contains the exported logs (`logs/`, several MB), the deploy history
(`deploys/deploys.csv`) and service documentation (`docs/`). Read the docs: log formats and clocks
differ between services.

Answer the questions below **from the evidence in the workspace only**. Some logs are large: use
the shell (`grep`, `awk`, `sort`, `python3`, ...) rather than reading whole files.

## Questions

1. `cascade_trigger_request_id` — the gateway request id of the **first** request (by gateway
   timestamp, across all gateway instances) that failed with an HTTP 5xx **because payments-svc
   timed out**.
2. `p95_latency_ms_checkout_window` — the 95th percentile of `latency_ms` for gateway requests
   `POST /api/checkout` with `status=200` whose gateway timestamp is in [13:00:00.000, 14:00:00.000)
   UTC, both gateways combined. Use the nearest-rank method: sort ascending, take the value at
   1-based rank `ceil(0.95 × n)`. Integer.
3. `deploy_that_introduced_timeouts` — the `deploy_id` (from `deploys/deploys.csv`) of the deploy
   that introduced the payment timeouts.
4. `affected_tenants_count` — the number of distinct tenants that had at least one gateway request
   fail with 5xx because payments-svc timed out.
5. `non_timeout_5xx_count` — the number of gateway responses with status ≥ 500 in the exported
   logs that were **not** caused by a payments-svc timeout.
6. `alert_acknowledged_by` — the name of the on-call engineer who acknowledged the outage alert.

If the evidence available here does not determine an answer, use `null` for it and say why in the
evidence field. A wrong answer is worse than `null`.

## Deliverable

Write `ANSWERS.json` in the workspace root, exactly in this shape:

```json
{
  "answers": {
    "cascade_trigger_request_id": "<id or null>",
    "p95_latency_ms_checkout_window": 0,
    "deploy_that_introduced_timeouts": "<deploy id or null>",
    "affected_tenants_count": 0,
    "non_timeout_5xx_count": 0,
    "alert_acknowledged_by": "<name or null>"
  },
  "evidence": {"<question key>": "<files and the exact method/command used to derive the answer>"}
}
```

Then reply (without a tool call) with a short summary of your findings.

## Constraints and permissions

- Do not modify anything under `logs/`, `deploys/` or `docs/` (it is evidence). You may create
  helper scripts and scratch files elsewhere in the workspace.
- Tools: list/read/search/write/edit files and run shell commands in the sandbox. No network.
- Nobody is available to answer questions.

## Completion criteria (what you know about grading)

Each answer is checked exactly against ground truth. Answering an undeterminable question with a
guess is penalised; `null` with a reason is correct for such questions. Efficiency (how much tool
output you pulled and how many calls you made) and the quality of the evidence also count.
