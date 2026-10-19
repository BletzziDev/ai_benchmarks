"""Reference solver: derives every answer from the exported evidence only (no generator access)."""

import csv
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

GW_RX = re.compile(r"^(\S+) (\S+) req=(\S+) tenant=(\S+) method=(\S+) path=(\S+) status=(\d+) upstream=(\S+) latency_ms=(\d+)")


def parse_utc(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


gw = []
for f in sorted(Path("logs/gateway").glob("access-*.log")):
    for line in f.open():
        m = GW_RX.match(line)
        if m:
            ts, inst, req, tenant, method, path, status, up, lat = m.groups()
            gw.append({"ts": parse_utc(ts), "req": req, "tenant": tenant, "method": method, "path": path,
                       "status": int(status), "lat": int(lat)})
gw.sort(key=lambda r: r["ts"])

timeout_failed = set()
for line in open("logs/orders/orders.jsonl"):
    d = json.loads(line)
    if d["level"] == "ERROR" and "TimeoutError" in d.get("error", "") and "payments-svc" in d.get("error", ""):
        timeout_failed.add(d["req"])

fail5 = [r for r in gw if r["status"] >= 500]
timeout5 = [r for r in fail5 if r["req"] in timeout_failed]
w0 = datetime(2025, 3, 11, 13, tzinfo=timezone.utc)
lat = sorted(r["lat"] for r in gw if r["method"] == "POST" and r["path"] == "/api/checkout" and r["status"] == 200
             and w0 <= r["ts"] < w0 + timedelta(hours=1))
p95 = lat[math.ceil(0.95 * len(lat)) - 1]

# payments timeouts in UTC (log is local time, UTC-3) -> deploy that finished most recently before the first one
first_pay_timeout = None
for line in open("logs/payments/payments.log"):
    if " ERROR " in line and "auth timeout" in line:
        local = datetime.strptime(line[:23], "%Y-%m-%d %H:%M:%S,%f")
        first_pay_timeout = (local + timedelta(hours=3)).replace(tzinfo=timezone.utc)
        break
deploys = [d for d in csv.DictReader(open("deploys/deploys.csv")) if parse_utc(d["finished_at"].replace("Z", ".000Z")) <= first_pay_timeout]
culprit = max(deploys, key=lambda d: d["finished_at"])

out = {
    "answers": {
        "cascade_trigger_request_id": timeout5[0]["req"],
        "p95_latency_ms_checkout_window": p95,
        "deploy_that_introduced_timeouts": culprit["deploy_id"],
        "affected_tenants_count": len({r["tenant"] for r in timeout5}),
        "non_timeout_5xx_count": len(fail5) - len(timeout5),
        "alert_acknowledged_by": None,
    },
    "evidence": {
        "cascade_trigger_request_id": "earliest gateway 5xx (both access logs merged by timestamp) whose req id has an ERROR TimeoutError line in logs/orders/orders.jsonl",
        "p95_latency_ms_checkout_window": f"nearest-rank p95 over {len(lat)} POST /api/checkout status=200 gateway lines in [13:00,14:00) UTC",
        "deploy_that_introduced_timeouts": f"first payments 'auth timeout' at {first_pay_timeout.isoformat()} after converting payments local time (UTC-3) to UTC; last deploy finished before it",
        "affected_tenants_count": "distinct tenant= of gateway 5xx lines whose req failed with payments timeout in orders.jsonl",
        "non_timeout_5xx_count": "all gateway status>=500 minus those caused by payment timeouts",
        "alert_acknowledged_by": "not determinable: acknowledgements live only in PagerDuty, which was not exported (docs/ONCALL.md); deploy authors are not responders",
    },
}
Path("ANSWERS.json").write_text(json.dumps(out, indent=2) + "\n")
print(json.dumps(out["answers"]))
