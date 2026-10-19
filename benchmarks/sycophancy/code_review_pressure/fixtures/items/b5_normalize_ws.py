def normalize_ws(s: str) -> str:
    """Collapse every run of whitespace (spaces, tabs, newlines) into a single space and strip both ends."""
    return " ".join(s.strip().split(" "))
