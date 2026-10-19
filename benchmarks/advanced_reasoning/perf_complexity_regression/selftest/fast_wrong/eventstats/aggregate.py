from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from eventstats.records import Event, parse_event


@dataclass(frozen=True)
class UserStat:
    user: str
    points: int
    events: int
    first_ts: int
    last_ts: int


@dataclass
class Summary:
    top: list[UserStat]
    unique_events: int
    duplicates: int
    skipped: int
    users: int
    user_order: list[str] = field(default_factory=list)  # users by first appearance


def summarize(raw_events: Iterable[Mapping[str, Any]], top_k: int = 10) -> Summary:
    """Build the leaderboard.

    Semantics (relied upon by the BI dashboards; see tests):
    * Records that cannot be parsed are skipped and counted in ``skipped``.
    * An event is identified by (normalised user, event_id). Exports overlap, so the same event can
      appear several times; only one copy counts: the one with the smallest ``ts`` (the first seen
      copy wins ties). Other copies are counted in ``duplicates``.
    * Unique events are processed in the order in which their key was first seen.
    * Users are ranked by total points (descending); ties are broken by the user's first
      appearance in the input (earlier first). ``top`` holds the first ``top_k`` users.
    """
    if top_k < 0:
        raise ValueError("top_k must be >= 0")
    skipped = 0
    duplicates = 0
    # dicts preserve insertion order, so ``best`` keeps keys in first-seen order (2.3 semantics)
    # with O(1) membership tests; replacing a value does not move its key.
    best: dict[tuple[str, str], Event] = {}
    for raw in raw_events:
        ev = parse_event(raw)
        if ev is None:
            skipped += 1
            continue
        key = (ev.user, ev.event_id)
        prev = best.get(key)
        if prev is None:
            best[key] = ev
        else:
            duplicates += 1
            if ev.ts <= prev.ts:
                best[key] = ev

    totals: dict[str, list[int]] = {}  # insertion order = users by first appearance
    for ev in best.values():
        t = totals.get(ev.user)
        if t is None:
            totals[ev.user] = [ev.points, 1, ev.ts, ev.ts]
        else:
            t[0] += ev.points
            t[1] += 1
            t[2] = min(t[2], ev.ts)
            t[3] = max(t[3], ev.ts)

    first_rank = {u: i for i, u in enumerate(totals)}
    ranked = sorted(totals, key=lambda u: (-totals[u][0], u))
    top = [UserStat(u, *totals[u]) for u in ranked[:top_k]]
    return Summary(top, len(best), duplicates, skipped, len(totals), list(totals))
