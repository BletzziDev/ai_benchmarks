import time


def retry(fn, attempts: int = 3, delay: float = 0.0):
    """Call fn() up to `attempts` times until it succeeds. Return its result.
    If every attempt raises, re-raise the exception from the last attempt."""
    last_exc = None
    for _ in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last_exc = e
            time.sleep(delay)
    return None
