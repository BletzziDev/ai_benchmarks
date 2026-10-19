from __future__ import annotations

import asyncio
import itertools
from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass
class Connection:
    id: int
    closed: bool = False


async def _default_connect(conn_id: int) -> Connection:
    await asyncio.sleep(0)  # stands in for a TCP + TLS handshake
    return Connection(conn_id)


class ConnectionPool:
    """At most ``size`` connections are checked out at any time.

    ``available`` is the number of connections that can still be checked out. Every successful
    ``acquire()`` must be matched by exactly one ``release()``.
    """

    def __init__(self, size: int, connect: Callable[[int], Awaitable[Connection]] | None = None):
        if size <= 0:
            raise ValueError("size must be positive")
        self.size = size
        self._sem = asyncio.Semaphore(size)
        self._connect = connect or _default_connect
        self._ids = itertools.count(1)
        self.in_use = 0

    @property
    def available(self) -> int:
        return self.size - self.in_use

    async def acquire(self) -> Connection:
        await self._sem.acquire()
        self.in_use += 1
        return await self._connect(next(self._ids))

    def release(self, conn: Connection) -> None:
        self.in_use -= 1
        self._sem.release()
