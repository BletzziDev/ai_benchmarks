from decimal import ROUND_HALF_EVEN, Decimal


def round_cents(value: Decimal) -> int:
    """Round a Decimal amount of cents to an integer number of cents (banker's rounding, as
    required by the ledger team so that rounding errors cancel out over many invoices)."""
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))
