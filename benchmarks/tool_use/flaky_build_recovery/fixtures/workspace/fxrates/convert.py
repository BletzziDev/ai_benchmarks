from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from fxrates._tables import MINOR_DIGITS, NAMES, USD_PER_UNIT


class UnknownCurrency(KeyError):
    pass


def _rate(code: str) -> Decimal:
    try:
        return USD_PER_UNIT[code]
    except KeyError:
        raise UnknownCurrency(code) from None


def convert(amount: Decimal, src: str, dst: str) -> Decimal:
    """Convert ``amount`` from ``src`` to ``dst``, rounded half-even to the destination's minor unit."""
    usd = Decimal(amount) * _rate(src)
    out = usd / _rate(dst)
    quantum = Decimal(1).scaleb(-MINOR_DIGITS[dst])
    return out.quantize(quantum, rounding=ROUND_HALF_EVEN)


def format_amount(amount: Decimal, code: str) -> str:
    _rate(code)
    digits = MINOR_DIGITS[code]
    q = Decimal(amount).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_EVEN)
    return f"{q:,.{digits}f} {code} ({NAMES[code]})"
