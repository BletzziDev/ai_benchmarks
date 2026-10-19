from checkout.config import TAX_PERCENT
from checkout.money import percent_of


def apply(ctx) -> None:
    ctx.tax = percent_of(ctx.merchandise_total, TAX_PERCENT)
