"""Application service layer orchestrating repositories, converters, handlers and renderers."""

from __future__ import annotations

from typing import Any

from ledgerly.converters import ConverterFactory
from ledgerly.handlers import DictAccumulator, HandlerChain
from ledgerly.renderers import RendererFactory
from ledgerly.repository import RepositoryFactory


class ReportingContext:
    def __init__(self, currency: str = "USD", fmt: str = "text") -> None:
        self.currency = currency
        self.fmt = fmt


class ReportingService:
    def __init__(self, context: ReportingContext | None = None) -> None:
        self.context = context or ReportingContext()
        self.chain = HandlerChain()

    def totals(self, transactions: list[dict[str, Any]], month: str) -> dict[str, float]:
        repo = RepositoryFactory.from_list(transactions)
        acc = DictAccumulator()
        for tx in repo.for_month(month):  # type: ignore[attr-defined]
            amount = ConverterFactory.create(tx["currency"]).to_usd(tx["amount"])
            self.chain.dispatch(acc, amount, tx)
        return {k: acc.get(k) for k in ("gross", "refunds", "fees", "chargebacks", "chargeback_fees")}

    def render(self, model: dict[str, Any]) -> str:
        return RendererFactory.create(self.context.fmt).render(model)


class ReportingServiceBuilder:
    def __init__(self) -> None:
        self._context = ReportingContext()

    def with_currency(self, currency: str) -> "ReportingServiceBuilder":
        self._context.currency = currency
        return self

    def with_format(self, fmt: str) -> "ReportingServiceBuilder":
        self._context.fmt = fmt
        return self

    def build(self) -> ReportingService:
        return ReportingService(self._context)
