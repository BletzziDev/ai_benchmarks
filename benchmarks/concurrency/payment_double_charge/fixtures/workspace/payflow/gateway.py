"""Card gateway client.

This module simulates the EXTERNAL card provider used in production. Its behaviour is fixed by the
provider and must not be changed: in particular the legacy gateway does NOT de-duplicate requests;
every call to ``charge`` captures money, so the processor must guarantee at most one call per
idempotency key.
"""

from __future__ import annotations

import itertools
import threading
import time
from typing import Protocol


class Gateway(Protocol):
    def charge(self, account_id: str, amount_cents: int, idempotency_key: str) -> str:
        """Capture ``amount_cents``; return a charge id. Raises GatewayError on decline/failure.
        Calls may take several seconds in production."""
        ...


class FakeGateway:
    """In-memory gateway used in tests and local development."""

    def __init__(self, latency_s: float = 0.0):
        self.latency_s = latency_s
        self.charges: list[tuple[str, str, int, str]] = []  # (charge_id, account, amount, key)
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def charge(self, account_id: str, amount_cents: int, idempotency_key: str) -> str:
        if self.latency_s:
            time.sleep(self.latency_s)
        with self._lock:
            charge_id = f"ch_{next(self._ids):06d}"
            self.charges.append((charge_id, account_id, amount_cents, idempotency_key))
        return charge_id
