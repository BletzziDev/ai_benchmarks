# AIBENCH-CANARY: 5a7d2c90-transfer-deadlock-hidden
import threading
import time

import pytest


class BlockingJournal:
    """Journal that parks selected transfers inside ``record`` (i.e. while the transfer holds its
    locks) until ``release()``. Lets tests create contention deterministically."""

    def __init__(self):
        self.entries = []
        self._lock = threading.Lock()
        self._pred = None
        self.entered = threading.Event()
        self._go = threading.Event()

    def hold(self, pred):
        self._pred = pred
        self.entered.clear()
        self._go.clear()

    def release(self):
        self._go.set()

    def record(self, src, dst, amount):
        if self._pred is not None and self._pred(src, dst, amount):
            self.entered.set()
            if not self._go.wait(20):
                raise RuntimeError("test barrier never released")
        with self._lock:
            self.entries.append((src, dst, amount))


@pytest.fixture
def journal():
    j = BlockingJournal()
    yield j
    j.release()


def run_thread(fn, *args, **kw):
    box = {}

    def target():
        t0 = time.monotonic()
        try:
            box["result"] = fn(*args, **kw)
        except BaseException as e:  # noqa: BLE001
            box["error"] = e
        box["elapsed"] = time.monotonic() - t0

    t = threading.Thread(target=target, daemon=True)
    t.start()
    return t, box


def join_all(threads, budget):
    deadline = time.monotonic() + budget
    for t in threads:
        t.join(max(0.0, deadline - time.monotonic()))
    return sum(t.is_alive() for t in threads)
