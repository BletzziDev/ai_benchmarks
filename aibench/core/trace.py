"""Structured, append-only event trace for one attempt (``trace.jsonl``).

Three clocks are kept apart on purpose:
- wall-clock time of the attempt,
- time spent waiting for the model (``model_time_s``),
- time spent executing tools (``tool_time_s``).
Anything else is harness overhead. Budget tiers are limits, not claims about elapsed time.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aibench.core.util import to_jsonable


@dataclass
class Totals:
    model_calls: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    model_time_s: float = 0.0
    tool_time_s: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    usage_reported_calls: int = 0
    cost_usd: float | None = None
    cost_available: bool = True
    retries: int = 0
    policy_violations: int = 0
    asks: int = 0
    faults_injected: int = 0
    context_elisions: int = 0
    sessions: int = 1
    tools_by_name: dict[str, int] = field(default_factory=dict)


class Trace:
    def __init__(self, path: Path | None):
        self.path = Path(path) if path else None
        self.events: list[dict[str, Any]] = []
        self.t0 = time.monotonic()
        self.totals = Totals()
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self.path, "a", encoding="utf-8")
        else:
            self._fh = None

    def elapsed(self) -> float:
        return time.monotonic() - self.t0

    def emit(self, type_: str, **data: Any) -> dict[str, Any]:
        ev = {"seq": len(self.events), "t": round(self.elapsed(), 4),
              "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), "type": type_, **to_jsonable(data)}
        self.events.append(ev)
        if self._fh:
            self._fh.write(json.dumps(ev, ensure_ascii=False) + "\n")
            self._fh.flush()
        return ev

    def record_usage(self, usage: Any, cost: float | None) -> None:
        t = self.totals
        if usage.reported:
            t.usage_reported_calls += 1
            for attr in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
                v = getattr(usage, attr)
                if v is not None:
                    setattr(t, attr, (getattr(t, attr) or 0) + v)
        if cost is None:
            t.cost_available = False
        else:
            t.cost_usd = (t.cost_usd or 0.0) + cost

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def summary(self) -> dict[str, Any]:
        t = self.totals
        d = to_jsonable(t.__dict__)
        d["wall_time_s"] = round(self.elapsed(), 3)
        d["model_time_s"] = round(t.model_time_s, 3)
        d["tool_time_s"] = round(t.tool_time_s, 3)
        d["harness_overhead_s"] = round(max(0.0, self.elapsed() - t.model_time_s - t.tool_time_s), 3)
        if t.usage_reported_calls == 0:
            for k in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
                d[k] = None
            d["usage_status"] = "unavailable"
        elif t.usage_reported_calls < t.model_calls:
            d["usage_status"] = "partial"
        else:
            d["usage_status"] = "reported"
        if not t.cost_available or t.cost_usd is None:
            d["cost_usd"] = None
            d["cost_status"] = "unavailable"
        else:
            d["cost_status"] = "computed_from_declared_pricing"
        return d


def load_trace(path: Path) -> list[dict[str, Any]]:
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
