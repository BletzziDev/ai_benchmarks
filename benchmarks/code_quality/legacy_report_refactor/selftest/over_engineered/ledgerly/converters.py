"""Currency converter strategy hierarchy."""

from __future__ import annotations

from ledgerly.interfaces import ICurrencyConverter


class UsdConverter(ICurrencyConverter):
    """Converter for USD."""

    RATE = 1.0

    def __init__(self) -> None:
        self._rate = self.RATE

    @property
    def code(self) -> str:
        return "USD"

    def to_usd(self, amount: float) -> float:
        if self._rate == 1.0:
            return amount
        return amount * self._rate

    def from_usd(self, amount: float) -> float:
        if self._rate == 1.0:
            return amount
        return amount / self._rate

    def __repr__(self) -> str:
        return f"UsdConverter(rate={self._rate})"

class EurConverter(ICurrencyConverter):
    """Converter for EUR."""

    RATE = 1.08

    def __init__(self) -> None:
        self._rate = self.RATE

    @property
    def code(self) -> str:
        return "EUR"

    def to_usd(self, amount: float) -> float:
        if self._rate == 1.0:
            return amount
        return amount * self._rate

    def from_usd(self, amount: float) -> float:
        if self._rate == 1.0:
            return amount
        return amount / self._rate

    def __repr__(self) -> str:
        return f"EurConverter(rate={self._rate})"

class GbpConverter(ICurrencyConverter):
    """Converter for GBP."""

    RATE = 1.27

    def __init__(self) -> None:
        self._rate = self.RATE

    @property
    def code(self) -> str:
        return "GBP"

    def to_usd(self, amount: float) -> float:
        if self._rate == 1.0:
            return amount
        return amount * self._rate

    def from_usd(self, amount: float) -> float:
        if self._rate == 1.0:
            return amount
        return amount / self._rate

    def __repr__(self) -> str:
        return f"GbpConverter(rate={self._rate})"

class BrlConverter(ICurrencyConverter):
    """Converter for BRL."""

    RATE = 0.2

    def __init__(self) -> None:
        self._rate = self.RATE

    @property
    def code(self) -> str:
        return "BRL"

    def to_usd(self, amount: float) -> float:
        if self._rate == 1.0:
            return amount
        return amount * self._rate

    def from_usd(self, amount: float) -> float:
        if self._rate == 1.0:
            return amount
        return amount / self._rate

    def __repr__(self) -> str:
        return f"BrlConverter(rate={self._rate})"


class ConverterFactory:
    """Creates converters by currency code."""

    _registry: dict[str, type[ICurrencyConverter]] = {}

    @classmethod
    def register(cls, code: str, klass: type[ICurrencyConverter]) -> None:
        cls._registry[code] = klass

    @classmethod
    def create(cls, code: str) -> ICurrencyConverter:
        try:
            return cls._registry[code]()
        except KeyError:
            raise ValueError("unknown currency " + code) from None


ConverterFactory.register("USD", UsdConverter)
ConverterFactory.register("EUR", EurConverter)
ConverterFactory.register("GBP", GbpConverter)
ConverterFactory.register("BRL", BrlConverter)
