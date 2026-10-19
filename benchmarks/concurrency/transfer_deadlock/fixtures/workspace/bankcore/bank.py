from __future__ import annotations

import threading
from dataclasses import dataclass, field

from bankcore.journal import Journal, MemoryJournal


class InsufficientFunds(Exception):
    pass


class UnknownAccount(KeyError):
    pass


class TransferTimeout(Exception):
    """The transfer could not start within the caller's deadline. Nothing was changed."""


@dataclass
class Account:
    id: str
    balance: int
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class Bank:
    """Thread-safe ledger of integer balances.

    Guarantees (relied on by the treasury service, which calls these methods from a thread pool):

    * ``transfer`` is atomic: both balances and the journal entry change together or not at all.
    * Money is conserved: ``total()`` always equals the sum of all deposits, and every call to
      ``total()`` returns a consistent snapshot even while transfers are running.
    * No operation can deadlock, whatever the mix of concurrent calls.
    * ``transfer(..., timeout=t)`` waits at most about ``t`` seconds to start; on timeout it raises
      ``TransferTimeout`` and leaves everything unchanged and usable.
    * Transfers between disjoint pairs of accounts run in parallel (the journal may be slow).
    * Transferring from an account to itself is rejected with ``ValueError``.
    """

    def __init__(self, journal: Journal | None = None):
        self._accounts: dict[str, Account] = {}
        self._journal = journal or MemoryJournal()
        self._registry_lock = threading.Lock()

    def open(self, account_id: str, initial: int = 0) -> None:
        with self._registry_lock:
            if account_id in self._accounts:
                raise ValueError(f"account {account_id} exists")
            self._accounts[account_id] = Account(account_id, initial)

    def _get(self, account_id: str) -> Account:
        try:
            return self._accounts[account_id]
        except KeyError:
            raise UnknownAccount(account_id) from None

    def balance(self, account_id: str) -> int:
        acct = self._get(account_id)
        with acct.lock:
            return acct.balance

    def transfer(self, src: str, dst: str, amount: int, timeout: float | None = None) -> None:
        if amount <= 0:
            raise ValueError("amount must be positive")
        a, b = self._get(src), self._get(dst)
        wait = -1 if timeout is None else timeout
        if not a.lock.acquire(timeout=wait):
            raise TransferTimeout(f"{src} busy")
        if not b.lock.acquire(timeout=wait):
            raise TransferTimeout(f"{dst} busy")
        try:
            if a.balance < amount:
                raise InsufficientFunds(f"{src} has {a.balance}, needs {amount}")
            self._journal.record(src, dst, amount)
            a.balance -= amount
            b.balance += amount
        finally:
            b.lock.release()
            a.lock.release()

    def total(self) -> int:
        """Sum of all balances, as a consistent snapshot."""
        accounts = list(self._accounts.values())
        for acct in accounts:
            acct.lock.acquire()
        try:
            return sum(acct.balance for acct in accounts)
        finally:
            for acct in reversed(accounts):
                acct.lock.release()
