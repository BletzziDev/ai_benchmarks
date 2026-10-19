"""Deterministic log generator for tool_use/log_forensics.

Runs once in the sandbox during environment setup (then deleted, so the agent never sees it), and
in-process in the grader to recompute the ground truth and the expected log hashes.
Uses only random.Random.random() so output is identical across Python versions.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 1103
DAY = datetime(2025, 3, 11, tzinfo=timezone.utc)
START, END = DAY.replace(hour=12), DAY.replace(hour=16)
INCIDENT = (DAY.replace(hour=14, minute=41), DAY.replace(hour=15, minute=20))
LOCAL = timedelta(hours=-3)  # payments-svc host clock: America/Sao_Paulo (UTC-3, no DST in 2025)
ENDPOINTS = [  # path, method, upstream, weight, median latency ms
    ("/api/products", "GET", "catalog", 40, 38),
    ("/api/products/{id}", "GET", "catalog", 25, 22),
    ("/api/cart", "POST", "orders", 15, 61),
    ("/api/checkout", "POST", "orders", 10, 240),
    ("/api/search", "GET", "search", 10, 95),
]


class R:
    def __init__(self, seed: int):
        import random

        self._r = random.Random(seed)

    def u(self) -> float:
        return self._r.random()

    def below(self, n: int) -> int:
        return min(n - 1, int(self.u() * n))

    def pick(self, seq):
        return seq[self.below(len(seq))]

    def weighted(self, items, weights):
        t = self.u() * sum(weights)
        for it, w in zip(items, weights):
            t -= w
            if t < 0:
                return it
        return items[-1]

    def hexid(self, n: int = 12) -> str:
        return "".join("0123456789abcdef"[self.below(16)] for _ in range(n))

    def latency(self, median: float) -> int:
        # log-normal via Box-Muller on random()
        z = math.sqrt(-2 * math.log(1 - self.u())) * math.cos(2 * math.pi * self.u())
        return max(1, int(median * math.exp(0.45 * z)))


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.") + f"{t.microsecond // 1000:03d}Z"


def generate(out: Path) -> dict:
    r = R(SEED)
    tenants = [f"t-{i:04d}" for i in range(1, 301)]
    gw = {"gw-1": [], "gw-2": []}
    orders, payments = [], []
    truth_reqs = []  # (resp_time, gw, req, tenant, path, status, latency, cause)
    t = START
    while t < END:
        t += timedelta(milliseconds=200 + r.below(1500))
        ep = r.weighted(ENDPOINTS, [e[3] for e in ENDPOINTS])
        path, method, upstream, _, med = ep
        path = path.replace("{id}", str(1 + r.below(9000)))
        req, tenant, inst = r.hexid(), r.pick(tenants), r.pick(["gw-1", "gw-2"])
        lat, status, cause, extra = r.latency(med), 200, None, ""
        if upstream == "search" and r.u() < 0.012:
            status, cause = 503, "search_unavailable"
        elif upstream == "orders":
            if r.u() < 0.0025:
                status, cause, extra = 502, "gateway_conn_reset", " upstream_error=connection_reset"
            elif r.u() < 0.012:
                status, cause = 500, "keyerror_sku"
                orders.append((t + timedelta(milliseconds=lat - 3), {"level": "ERROR", "req": req, "msg": "checkout failed" if "checkout" in path else "cart update failed", "error": "KeyError: 'sku'"}))
            elif path == "/api/checkout":
                call_t = t + timedelta(milliseconds=lat // 3)
                slow = INCIDENT[0] <= call_t < INCIDENT[1]
                if slow and r.u() < 0.62:
                    payments.append((call_t + timedelta(milliseconds=3000), "ERROR", f"auth timeout order_req={req} waited_ms=3000 ledger_lock_wait_ms={2800 + r.below(4000)}"))
                    if r.u() < 0.3:
                        lat += 3000 + r.latency(200)
                        orders.append((t + timedelta(milliseconds=3000), {"level": "WARN", "req": req, "msg": "payment call timed out, retrying", "error": "TimeoutError: payments-svc did not respond within 3000 ms"}))
                        payments.append((t + timedelta(milliseconds=lat - 20), "INFO", f"auth ok order_req={req} dur_ms={r.latency(180)}"))
                    else:
                        lat = 3000 + r.latency(40)
                        status, cause = 500, "payment_timeout"
                        orders.append((t + timedelta(milliseconds=lat - 2), {"level": "ERROR", "req": req, "msg": "payment authorization failed", "error": "TimeoutError: payments-svc did not respond within 3000 ms"}))
                else:
                    payments.append((call_t, "INFO", f"auth ok order_req={req} dur_ms={r.latency(900 if slow else 150)}"))
        resp = t + timedelta(milliseconds=lat)
        gw[inst].append((resp, f"{iso(resp)} {inst} req={req} tenant={tenant} method={method} path={path} status={status} upstream={upstream} latency_ms={lat}{extra}"))
        truth_reqs.append((resp, inst, req, tenant, path, method, status, lat, cause))
    # payments background noise + restart at deploy time
    pt = START
    while pt < END:
        pt += timedelta(seconds=20 + r.below(40))
        if INCIDENT[0] <= pt < INCIDENT[1]:
            payments.append((pt, "WARN", f"slow query on ledger_entries dur_ms={3000 + r.below(6000)} rows_scanned={400000 + r.below(900000)}"))
        else:
            payments.append((pt, "INFO", f"pool stats active={2 + r.below(6)} idle={8 + r.below(6)}"))
    payments.append((DAY.replace(hour=14, minute=40, second=12), "INFO", "shutting down (SIGTERM)"))
    payments.append((DAY.replace(hour=14, minute=40, second=31), "INFO", "payments-svc started (pid 4121), migrations: none pending"))
    payments.append((DAY.replace(hour=15, minute=19, second=48), "INFO", "shutting down (SIGTERM)"))
    payments.append((DAY.replace(hour=15, minute=20, second=4), "INFO", "payments-svc started (pid 5307), migrations: none pending"))

    (out / "logs" / "gateway").mkdir(parents=True, exist_ok=True)
    (out / "logs" / "orders").mkdir(parents=True, exist_ok=True)
    (out / "logs" / "payments").mkdir(parents=True, exist_ok=True)
    for inst, rows in gw.items():
        rows.sort(key=lambda x: x[0])
        (out / "logs" / "gateway" / f"access-{inst}.log").write_text("".join(l + "\n" for _, l in rows))
    orders.sort(key=lambda x: x[0])
    (out / "logs" / "orders" / "orders.jsonl").write_text("".join(
        json.dumps({"ts": iso(ts), "service": "orders", **d}) + "\n" for ts, d in orders))
    payments.sort(key=lambda x: x[0])
    (out / "logs" / "payments" / "payments.log").write_text("".join(
        f"{(ts + LOCAL).strftime('%Y-%m-%d %H:%M:%S')},{ts.microsecond // 1000:03d} {lvl:5} payments-svc {msg}\n"
        for ts, lvl, msg in payments))

    failed_timeout = sorted([x for x in truth_reqs if x[8] == "payment_timeout"], key=lambda x: x[0])
    window = [x[7] for x in truth_reqs if x[4] == "/api/checkout" and x[6] == 200
              and DAY.replace(hour=13) <= x[0] < DAY.replace(hour=14)]
    window.sort()
    p95 = window[math.ceil(0.95 * len(window)) - 1]
    truth = {
        "cascade_trigger_request_id": failed_timeout[0][2],
        "p95_latency_ms_checkout_window": p95,
        "deploy_that_introduced_timeouts": "d-1043",
        "affected_tenants_count": len({x[3] for x in failed_timeout}),
        "non_timeout_5xx_count": sum(1 for x in truth_reqs if x[6] >= 500 and x[8] != "payment_timeout"),
        "alert_acknowledged_by": None,
    }
    hashes = {str(p.relative_to(out)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted((out / "logs").rglob("*")) if p.is_file()}
    return {"truth": truth, "log_hashes": hashes, "stats": {"requests": len(truth_reqs), "timeouts_failed": len(failed_timeout),
                                                             "window_n": len(window)}}


if __name__ == "__main__":
    info = generate(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("."))
    if "--print" in sys.argv:
        print(json.dumps(info, indent=2))
