from collections import defaultdict

from checkout.config import BUNDLE_SIZE


def apply(ctx) -> None:
    """"3 for 2": in each bundle group, every third unit (by descending price) is free.

    Sale lines never take part in bundles (RULES.md step 1), even when they carry a bundle name.
    """
    units: dict[str, list[int]] = defaultdict(list)
    for line in ctx.cart.lines:
        if line.bundle and not line.on_sale:
            units[line.bundle].extend([line.unit_price] * line.quantity)
    free = 0
    for group, prices in sorted(units.items()):
        prices.sort(reverse=True)
        group_free = sum(prices[BUNDLE_SIZE - 1::BUNDLE_SIZE])
        if group_free:
            ctx.notes.append(f"bundle {group}: {group_free} off")
        free += group_free
    ctx.bundle_discount = free
