from __future__ import annotations

import threading
from typing import Protocol


class Journal(Protocol):
    def record(self, src: str, dst: str, amount: int) -> None:
        """Persist a transfer. Called while the transfer is being applied, so that the journal and
        the balances never disagree. May block on I/O (fsync, network storage)."""
        ...


class MemoryJournal:
    def __init__(self) -> None:
        self.entries: list[tuple[str, str, int]] = []
        self._lock = threading.Lock()

    def record(self, src: str, dst: str, amount: int) -> None:
        with self._lock:
            self.entries.append((src, dst, amount))
