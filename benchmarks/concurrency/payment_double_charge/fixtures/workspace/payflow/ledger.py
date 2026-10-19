from __future__ import annotations

import logging

log = logging.getLogger("payflow.ledger")


class Ledger:
    """Account balances in integer cents, with an audit trail of every movement."""

    def __init__(self) -> None:
        self._balances: dict[str, int] = {}
        self.audit: list[tuple[str, str, int]] = []  # (kind, account, amount)

    def open_account(self, account_id: str, initial_cents: int = 0) -> None:
        if account_id in self._balances:
            raise ValueError(f"account {account_id} already exists")
        self._balances[account_id] = initial_cents

    def balance(self, account_id: str) -> int:
        return self._balances[account_id]

    def debit(self, account_id: str, amount_cents: int) -> int:
        current = self._balances[account_id]
        self.audit.append(("debit", account_id, amount_cents))
        log.debug("debit %s %d: %d -> %d", account_id, amount_cents, current, current - amount_cents)
        self._balances[account_id] = current - amount_cents
        return self._balances[account_id]

    def credit(self, account_id: str, amount_cents: int) -> int:
        current = self._balances[account_id]
        self.audit.append(("credit", account_id, amount_cents))
        log.debug("credit %s %d: %d -> %d", account_id, amount_cents, current, current + amount_cents)
        self._balances[account_id] = current + amount_cents
        return self._balances[account_id]
