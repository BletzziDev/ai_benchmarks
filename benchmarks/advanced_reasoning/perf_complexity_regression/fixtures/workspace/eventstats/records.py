from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Mapping

_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class Event:
    user: str      # normalised user id
    event_id: str
    ts: int        # epoch milliseconds
    points: int


def normalize_user(raw: str) -> str:
    """User ids arrive from three upstream systems with inconsistent case and stray whitespace."""
    return _WS.sub("", raw).casefold()


def parse_event(raw: Mapping[str, Any]) -> Event | None:
    """Return an Event, or None if the record is unusable (missing/invalid fields)."""
    rec = copy.deepcopy(dict(raw))  # never mutate caller-owned records
    try:
        user = rec["user"]
        event_id = rec["event_id"]
        ts = rec["ts"]
        points = rec["points"]
    except KeyError:
        return None
    if not isinstance(user, str) or not isinstance(event_id, str) or not normalize_user(user):
        return None
    if isinstance(ts, bool) or not isinstance(ts, int) or isinstance(points, bool) or not isinstance(points, int):
        return None
    return Event(normalize_user(user), event_id, ts, points)
