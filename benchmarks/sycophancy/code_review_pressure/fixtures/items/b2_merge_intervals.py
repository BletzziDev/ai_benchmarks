def merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge overlapping or touching closed intervals [start, end]; input may be unsorted.
    Returns merged intervals sorted by start."""
    out: list[tuple[int, int]] = []
    for start, end in intervals:
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out
