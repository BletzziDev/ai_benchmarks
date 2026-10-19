from collections import defaultdict

from checkout.config import BUNDLE_SIZE


def apply(ctx) -> None:
    """"3 for 2": in each bundle group, every third unit (by descending price) is free."""
    units: dict[str, list[int]] = defaultdict(list)
    for line in ctx.cart.lines:
        if line.bundle:
            units[line.bundle].extend([line.unit_price] * line.quantity)
    free = 0
    for group, prices in sorted(units.items()):
        prices.sort(reverse=True)
        group_free = sum(prices[BUNDLE_SIZE - 1::BUNDLE_SIZE])
        if group_free:
            ctx.notes.append(f"bundle {group}: {group_free} off")
        free += group_free
    ctx.bundle_discount = free
