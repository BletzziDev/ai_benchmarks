class StockroomError(Exception):
    """Base class for inventory errors."""


class InsufficientStock(StockroomError):
    def __init__(self, sku: str, requested: int, available: int):
        super().__init__(f"insufficient stock for {sku}: requested {requested}, available {available}")
        self.sku = sku
        self.requested = requested
        self.available = available


class ReservationNotFound(StockroomError):
    pass


class ReservationExpired(StockroomError):
    """Raised when an operation needs an active hold but the hold has lapsed."""
