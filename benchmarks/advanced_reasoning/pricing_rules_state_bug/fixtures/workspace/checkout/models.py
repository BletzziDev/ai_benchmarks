from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from checkout.config import MEMBER_PERCENT


@dataclass(frozen=True)
class Line:
    sku: str
    unit_price: int
    quantity: int = 1
    on_sale: bool = False
    bundle: str | None = None

    def __post_init__(self) -> None:
        if self.unit_price < 0 or self.quantity < 1:
            raise ValueError(f"invalid line {self.sku}: price must be >= 0 and quantity >= 1")

    @property
    def subtotal(self) -> int:
        return self.unit_price * self.quantity


@dataclass(frozen=True)
class Cart:
    lines: tuple[Line, ...]

    def __init__(self, lines):
        object.__setattr__(self, "lines", tuple(lines))


@dataclass(frozen=True)
class Customer:
    tier: str = "none"

    def __post_init__(self) -> None:
        if self.tier not in MEMBER_PERCENT:
            raise ValueError(f"unknown tier {self.tier!r}")


@dataclass(frozen=True)
class Coupon:
    code: str
    kind: str  # "percent" | "fixed"
    value: Decimal | int
    min_spend: int = 0
    applies_to_sale: bool = False

    def __post_init__(self) -> None:
        if self.kind not in ("percent", "fixed"):
            raise ValueError(f"unknown coupon kind {self.kind!r}")
        if self.value < 0 or self.min_spend < 0:
            raise ValueError("coupon value and min_spend must be >= 0")


@dataclass
class Receipt:
    subtotal: int
    bundle_discount: int
    member_discount: int
    coupon_discount: int
    merchandise_total: int
    shipping: int
    tax: int
    total: int
    notes: list[str] = field(default_factory=list)
