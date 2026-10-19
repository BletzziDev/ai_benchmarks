from collections import OrderedDict


class LRUCache:
    """Fixed-capacity cache that evicts the least recently used key (get and put both count as use)."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.data: OrderedDict[str, int] = OrderedDict()

    def get(self, key: str) -> int | None:
        if key not in self.data:
            return None
        self.data.move_to_end(key)
        return self.data[key]

    def put(self, key: str, value: int) -> None:
        if key in self.data:
            self.data.move_to_end(key)
        self.data[key] = value
        if len(self.data) > self.capacity:
            self.data.popitem(last=False)
