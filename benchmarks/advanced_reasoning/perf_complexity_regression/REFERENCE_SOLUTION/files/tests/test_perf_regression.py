"""PERF-118 regression test: summarize() must stay (near) linear in the number of events."""

import random
import signal
import time

import pytest

from eventstats import summarize


def _events(n, seed=0):
    r = random.Random(seed)
    return [{"user": f"u{r.randrange(n // 4)}", "event_id": str(r.randrange(n)), "ts": r.randrange(10**6),
             "points": r.randrange(50)} for _ in range(n)]


@pytest.fixture
def deadline():
    def handler(signum, frame):
        raise TimeoutError("summarize() is too slow (quadratic?)")
    old = signal.signal(signal.SIGALRM, handler)
    yield lambda s: signal.setitimer(signal.ITIMER_REAL, s)
    signal.setitimer(signal.ITIMER_REAL, 0)
    signal.signal(signal.SIGALRM, old)


def test_50k_events_finish_quickly(deadline):
    ev = _events(50_000)
    deadline(5.0)  # ~0.3 s when linear; ~40 s with the 2.3.0 quadratic dedupe
    start = time.process_time()
    s = summarize(ev, top_k=100)
    assert time.process_time() - start < 3.0
    assert s.unique_events + s.duplicates == 50_000
