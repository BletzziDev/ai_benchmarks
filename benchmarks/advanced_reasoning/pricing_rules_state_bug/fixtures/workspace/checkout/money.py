from decimal import ROUND_HALF_UP, Decimal


def round_cents(value: Decimal) -> int:
    """Round half up to a whole cent."""
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def percent_of(cents: int, percent: Decimal) -> int:
    return round_cents(Decimal(cents) * Decimal(percent) / Decimal(100))
