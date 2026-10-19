import re

_SKU_RE = re.compile(r"^[A-Z0-9]+(-[A-Z0-9]+)*$")


def normalize_sku(raw: str) -> str:
    """Canonical SKU form used as the storage key: trimmed, upper-case, single dashes.

    The storefront sends canonical SKUs; the warehouse admin tool sends whatever operators type
    (often lower-case with stray spaces), so every entry point must normalise.
    """
    sku = re.sub(r"\s+", "", raw).upper()
    sku = re.sub(r"-{2,}", "-", sku)
    if not _SKU_RE.match(sku):
        raise ValueError(f"invalid SKU: {raw!r}")
    return sku
