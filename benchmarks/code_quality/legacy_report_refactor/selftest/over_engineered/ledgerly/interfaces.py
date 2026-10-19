"""Abstract interfaces for the reporting domain."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ICurrencyConverter(ABC):
    @abstractmethod
    def to_usd(self, amount: float) -> float: ...

    @abstractmethod
    def from_usd(self, amount: float) -> float: ...


class ITransactionHandler(ABC):
    @abstractmethod
    def handles(self, kind: str) -> bool: ...

    @abstractmethod
    def apply(self, accumulator: "IAccumulator", amount: float, tx: dict[str, Any]) -> None: ...


class IAccumulator(ABC):
    @abstractmethod
    def add(self, key: str, value: float) -> None: ...

    @abstractmethod
    def get(self, key: str) -> float: ...


class IRenderer(ABC):
    @abstractmethod
    def render(self, model: dict[str, Any]) -> str: ...


class IRepository(ABC):
    @abstractmethod
    def all(self) -> list[dict[str, Any]]: ...
