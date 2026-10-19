"""Repository abstraction over transaction sources."""

from __future__ import annotations

from typing import Any

from ledgerly.interfaces import IRepository


class InMemoryTransactionRepository(IRepository):
    def __init__(self, transactions: list[dict[str, Any]]) -> None:
        self._transactions = list(transactions)

    def all(self) -> list[dict[str, Any]]:
        return list(self._transactions)

    def for_month(self, month: str) -> list[dict[str, Any]]:
        return [t for t in self._transactions if t["date"][:7] == month]

    def for_customer(self, customer: str) -> list[dict[str, Any]]:
        return [t for t in self._transactions if t.get("customer", "") == customer]


class RepositoryFactory:
    @staticmethod
    def from_list(transactions: list[dict[str, Any]]) -> IRepository:
        return InMemoryTransactionRepository(transactions)
