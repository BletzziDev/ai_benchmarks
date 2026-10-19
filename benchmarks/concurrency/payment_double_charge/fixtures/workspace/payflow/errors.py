class PaymentError(Exception):
    """Base class for payment errors."""


class InsufficientFunds(PaymentError):
    def __init__(self, account_id: str, requested: int, balance: int):
        super().__init__(f"insufficient funds in {account_id}: requested {requested}, balance {balance}")
        self.account_id = account_id
        self.requested = requested
        self.balance = balance


class IdempotencyConflict(PaymentError):
    """The idempotency key was already used for a different account or amount."""


class GatewayError(PaymentError):
    """The card gateway declined or failed the charge. Nothing was captured."""
