"""Plan catalogue. Prices are monthly, in integer cents (USD)."""

from __future__ import annotations

from dataclasses import dataclass

from acctsvc.errors import InvalidPlan


@dataclass(frozen=True)
class Plan:
    name: str
    monthly_price_cents: int
    seats: int | None  # maximum number of members; None = unlimited


PLANS: dict[str, Plan] = {
    "free": Plan("free", 0, seats=3),
    "team": Plan("team", 4900, seats=10),
    "business": Plan("business", 19900, seats=None),
}


def get_plan(name: str) -> Plan:
    try:
        return PLANS[name]
    except KeyError:
        raise InvalidPlan(f"unknown plan {name!r}; choose from {sorted(PLANS)}") from None
