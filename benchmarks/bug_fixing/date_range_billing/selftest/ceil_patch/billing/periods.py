from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo


def local_midnight(d: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, time(0, 0), tzinfo=tz)


def days_between(start: date, end: date, tz: ZoneInfo) -> int:
    """Number of calendar days in the half-open interval [start, end) as seen by an account in ``tz``.

    Instants are compared in UTC so that accounts in different timezones are handled uniformly.
    """
    if end < start:
        raise ValueError("end must not be before start")
    a = local_midnight(start, tz).astimezone(timezone.utc)
    b = local_midnight(end, tz).astimezone(timezone.utc)
    # round up so that short (23h) DST days are still counted
    return math.ceil((b - a).total_seconds() / 86400)


@dataclass(frozen=True)
class BillingPeriod:
    """A billing period ``[start, end)`` in the account's local calendar. ``end`` is exclusive:
    a monthly period for March 2025 is ``BillingPeriod(date(2025, 3, 1), date(2025, 4, 1), tz)``."""

    start: date
    end: date
    tz: ZoneInfo

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError("billing period must have a positive length")

    @property
    def days(self) -> int:
        return days_between(self.start, self.end, self.tz)

    def local_date(self, instant: datetime) -> date:
        """Calendar date of an aware instant in the account's timezone."""
        if instant.tzinfo is None:
            raise ValueError("instant must be timezone-aware")
        return instant.astimezone(self.tz).date()

    def contains(self, d: date) -> bool:
        return self.start <= d < self.end

    @classmethod
    def monthly(cls, year: int, month: int, tz: ZoneInfo) -> "BillingPeriod":
        start = date(year, month, 1)
        end = date(year + (month == 12), month % 12 + 1, 1)
        return cls(start, end, tz)
