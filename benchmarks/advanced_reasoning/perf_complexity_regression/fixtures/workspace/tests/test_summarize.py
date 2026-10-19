import pytest

from eventstats import summarize


def ev(user, eid, ts, points=1):
    return {"user": user, "event_id": eid, "ts": ts, "points": points}


def test_basic_ranking():
    s = summarize([ev("a", "1", 10, 5), ev("b", "2", 11, 7), ev("a", "3", 12, 4)])
    assert [(u.user, u.points) for u in s.top] == [("a", 9), ("b", 7)]
    assert s.unique_events == 3 and s.users == 2


def test_duplicates_keep_earliest_copy():
    s = summarize([ev("a", "1", 20, 5), ev("a", "1", 10, 5), ev("a", "1", 30, 5)])
    assert s.unique_events == 1 and s.duplicates == 2
    assert s.top[0].first_ts == 10


def test_user_normalisation():
    s = summarize([ev(" Alice ", "1", 1), ev("ALICE", "1", 2), ev("alice", "2", 3)])
    assert s.users == 1 and s.unique_events == 2


def test_ties_by_first_appearance():
    s = summarize([ev("z", "1", 1, 3), ev("y", "2", 2, 3), ev("x", "3", 3, 3)])
    assert [u.user for u in s.top] == ["z", "y", "x"]


def test_skipped_records():
    s = summarize([{"user": "a"}, ev("a", "1", 1), {"user": "b", "event_id": "2", "ts": "soon", "points": 1}])
    assert s.skipped == 2 and s.unique_events == 1


def test_top_k():
    s = summarize([ev(str(i), str(i), i, i) for i in range(30)], top_k=3)
    assert [u.user for u in s.top] == ["29", "28", "27"]
    with pytest.raises(ValueError):
        summarize([], top_k=-1)
