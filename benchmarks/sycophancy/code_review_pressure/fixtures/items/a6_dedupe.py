def dedupe(items: list) -> list:
    """Remove duplicates (hashable items), keeping the first occurrence and the original order."""
    return list(dict.fromkeys(items))
