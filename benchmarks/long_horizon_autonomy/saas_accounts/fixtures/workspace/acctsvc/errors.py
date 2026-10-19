class AccountError(Exception):
    """Base class for all account-service errors."""


class NotFound(AccountError):
    pass


class Conflict(AccountError):
    """A uniqueness rule would be violated (e.g. duplicate email)."""


class Forbidden(AccountError):
    """The actor is not allowed to perform the action."""


class LastOwnerError(AccountError):
    """The operation would leave an organisation without any owner."""


class InvalidPlan(AccountError):
    pass


class SeatLimitExceeded(AccountError):
    def __init__(self, plan: str, limit: int):
        super().__init__(f"plan {plan!r} allows at most {limit} members")
        self.plan = plan
        self.limit = limit
