from typing import Iterator


def chunk(items: list, size: int) -> Iterator[list]:
    """Yield consecutive chunks of `size` items; the last chunk may be shorter. size must be >= 1."""
    if size < 1:
        raise ValueError("size must be >= 1")
    for i in range(0, len(items), size):
        yield items[i:i + size]
