# Shop platform — services and logs

All logs for 2025-03-11 (12:00–16:00 UTC) were exported to `logs/` for the post-incident review.

## gateway (2 instances: gw-1, gw-2)

Edge proxy. One line per request, written when the response is sent:

    <timestamp UTC, ISO-8601 with Z> <instance> req=<request id> tenant=<tenant id> method=<M> path=<path> status=<HTTP status> upstream=<service> latency_ms=<total latency> [upstream_error=<reason>]

Files: `logs/gateway/access-gw-1.log`, `logs/gateway/access-gw-2.log`. The request id is propagated
to upstream services. `upstream_error=connection_reset` means the gateway itself failed to reach the
upstream (the upstream never saw the request).

## orders

Owns carts and checkout. JSON lines in `logs/orders/orders.jsonl`, timestamps in UTC. Only warnings
and errors are exported. On checkout, orders calls payments-svc to authorize the payment with a
3000 ms timeout and **retries once**; a checkout fails (HTTP 500) only if the retry also fails or
for other errors (`error` field).

## payments-svc

Payment authorization. Plain-text log `logs/payments/payments.log`:

    <YYYY-MM-DD HH:MM:SS,mmm> <LEVEL> payments-svc <message>

payments-svc still runs on the legacy host `pay-legacy-01`, whose clock is configured to local time
(America/Sao_Paulo, UTC−3; Brazil has not observed DST since 2019). Its timestamps carry **no
offset**. `order_req` is the gateway request id.

## search, catalog

Not exported (only their gateway lines are available).

## Deploys

`deploys/deploys.csv` lists deploys with start/finish times in UTC.
