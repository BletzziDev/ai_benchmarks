"""Transaction handler chain-of-responsibility."""

from __future__ import annotations

from typing import Any

from ledgerly.interfaces import IAccumulator, ITransactionHandler


class SaleHandler(ITransactionHandler):
    """Handles sale transactions."""

    KIND = "sale"
    RATE = 0.029
    FIXED = 0.30
    PENALTY = 15.0

    def handles(self, kind: str) -> bool:
        return kind == self.KIND

    def apply(self, accumulator: IAccumulator, amount: float, tx: dict[str, Any]) -> None:
        accumulator.add("gross", amount)
        accumulator.add("fees", amount * self.RATE + self.FIXED)

    def __repr__(self) -> str:
        return "SaleHandler()"

class RefundHandler(ITransactionHandler):
    """Handles refund transactions."""

    KIND = "refund"
    RATE = 0.029
    FIXED = 0.30
    PENALTY = 15.0

    def handles(self, kind: str) -> bool:
        return kind == self.KIND

    def apply(self, accumulator: IAccumulator, amount: float, tx: dict[str, Any]) -> None:
        accumulator.add("refunds", amount)

    def __repr__(self) -> str:
        return "RefundHandler()"

class FeeHandler(ITransactionHandler):
    """Handles fee transactions."""

    KIND = "fee"
    RATE = 0.029
    FIXED = 0.30
    PENALTY = 15.0

    def handles(self, kind: str) -> bool:
        return kind == self.KIND

    def apply(self, accumulator: IAccumulator, amount: float, tx: dict[str, Any]) -> None:
        accumulator.add("fees", amount)

    def __repr__(self) -> str:
        return "FeeHandler()"

class ChargebackHandler(ITransactionHandler):
    """Handles chargeback transactions."""

    KIND = "chargeback"
    RATE = 0.029
    FIXED = 0.30
    PENALTY = 15.0

    def handles(self, kind: str) -> bool:
        return kind == self.KIND

    def apply(self, accumulator: IAccumulator, amount: float, tx: dict[str, Any]) -> None:
        accumulator.add("chargebacks", amount)
        accumulator.add("chargeback_fees", self.PENALTY)

    def __repr__(self) -> str:
        return "ChargebackHandler()"


class HandlerChain:
    def __init__(self, handlers: list[ITransactionHandler] | None = None) -> None:
        self._handlers = handlers or [SaleHandler(), RefundHandler(), FeeHandler(), ChargebackHandler()]

    def dispatch(self, accumulator: IAccumulator, amount: float, tx: dict[str, Any]) -> None:
        for handler in self._handlers:
            if handler.handles(tx["type"]):
                handler.apply(accumulator, amount, tx)
                return


class DictAccumulator(IAccumulator):
    def __init__(self) -> None:
        self._values: dict[str, float] = {}

    def add(self, key: str, value: float) -> None:
        self._values[key] = self._values.get(key, 0.0) + value

    def get(self, key: str) -> float:
        return self._values.get(key, 0.0)
