# AIBENCH-CANARY: 5d07ab93-perf-complexity-hidden — this file must never be shown to evaluated models.
"""Hidden tests for advanced_reasoning/perf_complexity_regression.

test_equiv_*  exact behavioural equivalence with the frozen 2.3.0 implementation (the intended output)
test_perf_*   machine-independent scaling check (CPU time ratio n -> 8n) and an absolute budget
test_pres_*   API / contract preservation
"""

import dataclasses
import inspect
import random
import signal
import statistics
import time
from contextlib import contextmanager

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import _original_230 as original
from eventstats import Summary, UserStat, summarize


def canon(s):
    return ([dataclasses.astuple(u) for u in s.top], s.unique_events, s.duplicates, s.skipped, s.users, list(s.user_order))


def gen(n, seed=7, users=None, dup_rate=0.25):
    r = random.Random(seed)
    users = users or max(1, n // 4)
    out = []
    for _ in range(n):
        u = f"{' ' if r.random() < 0.1 else ''}User{r.randrange(users)}"
        if r.random() < 0.3:
            u = u.upper()
        eid = str(r.randrange(int(n * (1 - dup_rate)) + 1))
        out.append({"user": u, "event_id": eid, "ts": r.randrange(10**6), "points": r.randrange(-5, 50)})
    return out


# ------------------------------------------------------------------ equivalence

user_st = st.sampled_from(["a", "A", " a", "b", "B ", "c", "d", "  ", "e"])
raw_st = st.one_of(
    st.fixed_dictionaries({"user": user_st, "event_id": st.sampled_from(list("123456")),
                           "ts": st.integers(0, 6), "points": st.integers(-3, 9)}),
    st.fixed_dictionaries({"user": user_st, "event_id": st.sampled_from(list("12"))}),
    st.fixed_dictionaries({"user": user_st, "event_id": st.just("1"), "ts": st.sampled_from(["x", True, 1.5]),
                           "points": st.integers(0, 3)}),
)


@settings(max_examples=500, deadline=None, derandomize=True, database=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.lists(raw_st, max_size=30), st.integers(0, 6))
def test_equiv_property_matches_230(events, k):
    assert canon(summarize(events, k)) == canon(original.summarize(events, k))


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_equiv_realistic_batches(seed):
    ev = gen(1500, seed=seed)
    assert canon(summarize(ev, 100)) == canon(original.summarize(ev, 100))


def test_equiv_tie_breaks_and_earliest_copy():
    ev = [{"user": "z", "event_id": "1", "ts": 5, "points": 3},
          {"user": "y", "event_id": "1", "ts": 4, "points": 3},
          {"user": "Z", "event_id": "1", "ts": 1, "points": 3},   # same key as first: earlier ts wins, position stays
          {"user": "x", "event_id": "9", "ts": 1, "points": 6},
          {"user": "y", "event_id": "1", "ts": 4, "points": 100}]  # equal ts: first copy wins
    s = summarize(ev, 10)
    assert canon(s) == canon(original.summarize(ev, 10))
    assert [u.user for u in s.top] == ["x", "z", "y"]
    assert s.top[1].first_ts == 1 and s.top[2].points == 3


def test_equiv_generator_input_and_reuse_after_mutation():
    ev = gen(300, seed=11)
    assert canon(summarize(iter(ev), 5)) == canon(original.summarize(list(ev), 5))
    first = canon(summarize(ev, 5))
    ev.append({"user": "newcomer", "event_id": "x", "ts": 0, "points": 10**6})
    second = summarize(ev, 5)
    assert canon(second) == canon(original.summarize(ev, 5))
    assert second.top[0].user == "newcomer" and canon(second) != first


def test_equiv_input_records_not_mutated_or_retained():
    ev = gen(200, seed=5)
    snapshot = [dict(r) for r in ev]
    summarize(ev, 10)
    assert ev == snapshot


# ------------------------------------------------------------------ performance

class Timeout(Exception):
    pass


@contextmanager
def wall_limit(seconds):
    def handler(signum, frame):
        raise Timeout(f"exceeded {seconds}s")
    old = signal.signal(signal.SIGALRM, handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def cpu_time(fn, repeats):
    out = []
    for _ in range(repeats):
        t = time.process_time()
        fn()
        out.append(time.process_time() - t)
    return statistics.median(out)


def test_perf_scaling_is_near_linear():
    """CPU-time ratio for 8x more events. Linear/n log n code measures ~7-11; the 2.3.0 code ~50+.
    CPU time (not wall time) is used so that other processes on the machine do not matter."""
    small, large = gen(4000, seed=3), gen(32000, seed=4)
    with wall_limit(60):
        summarize(small, 100)  # warm-up
        t_small = cpu_time(lambda: summarize(small, 100), 5)
        t_large = cpu_time(lambda: summarize(large, 100), 3)
    ratio = t_large / max(t_small, 1e-4)
    assert ratio <= 20, f"8x input took {ratio:.1f}x CPU time (small={t_small:.3f}s large={t_large:.3f}s)"


def test_perf_absolute_budget_200k_events():
    ev = gen(200_000, seed=9)
    with wall_limit(45):
        t = cpu_time(lambda: summarize(ev, 100), 1)
    assert t < 8.0, f"200k events took {t:.1f}s CPU"


def test_perf_many_distinct_users():
    ev = gen(60_000, seed=10, users=50_000, dup_rate=0.05)
    with wall_limit(30):
        t = cpu_time(lambda: summarize(ev, 100), 1)
    assert t < 4.0, f"60k events / 50k users took {t:.1f}s CPU"


# ------------------------------------------------------------------ preservation

def test_pres_api():
    assert list(inspect.signature(summarize).parameters) == ["raw_events", "top_k"]
    assert inspect.signature(summarize).parameters["top_k"].default == 10
    assert [f.name for f in dataclasses.fields(Summary)] == ["top", "unique_events", "duplicates", "skipped", "users", "user_order"]
    assert [f.name for f in dataclasses.fields(UserStat)] == ["user", "points", "events", "first_ts", "last_ts"]


def test_pres_errors_and_empty():
    with pytest.raises(ValueError):
        summarize([], top_k=-1)
    s = summarize([])
    assert canon(s) == ([], 0, 0, 0, 0, [])
