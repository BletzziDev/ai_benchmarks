from decimal import Decimal

SHIPPING_FEE = 599
FREE_SHIPPING_THRESHOLD = 5000
TAX_PERCENT = Decimal("8.25")
MEMBER_PERCENT = {"none": Decimal(0), "silver": Decimal(5), "gold": Decimal(10)}
BUNDLE_SIZE = 3
