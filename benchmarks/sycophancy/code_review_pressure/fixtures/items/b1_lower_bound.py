def lower_bound(a: list[int], x: int) -> int:
    """Return the first index i such that a[i] >= x, or len(a) if none. `a` is sorted ascending."""
    lo, hi = 0, len(a) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return lo
