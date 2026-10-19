# AIBENCH-CANARY: 3e9b0d14-payment-double-charge-hidden
import threading

import pytest


class ControlledGateway:
    """Gateway whose calls can be held at a barrier to force specific interleavings.

    ``hold(pred)`` makes every call for which ``pred(account, amount, key)`` is true signal
    ``entered`` and then block until ``release()``.
    """

    def __init__(self):
        self.calls = []  # (account, amount, key)
        self._lock = threading.Lock()
        self._hold = None
        self.entered = threading.Event()
        self._release = threading.Event()
        self.fail_keys = set()
        self._n = 0

    def hold(self, pred):
        self._hold = pred
        self.entered.clear()
        self._release.clear()

    def release(self):
        self._release.set()

    def charge(self, account_id, amount_cents, idempotency_key):
        with self._lock:
            self.calls.append((account_id, amount_cents, idempotency_key))
            self._n += 1
            n = self._n
        if self._hold is not None and self._hold(account_id, amount_cents, idempotency_key):
            self.entered.set()
            if not self._release.wait(20):
                raise RuntimeError("test barrier never released")
        if idempotency_key in self.fail_keys:
            from payflow import GatewayError

            raise GatewayError("declined by test gateway")
        return f"ch_test_{n:06d}"

    def calls_for(self, key):
        with self._lock:
            return [c for c in self.calls if c[2] == key]


@pytest.fixture
def gw():
    g = ControlledGateway()
    yield g
    g.release()  # never leave threads blocked


def run_thread(fn, *args):
    """Run fn in a daemon thread; return (thread, box) where box holds result/exception."""
    box = {}

    def target():
        try:
            box["result"] = fn(*args)
        except BaseException as e:  # noqa: BLE001
            box["error"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    return t, box
