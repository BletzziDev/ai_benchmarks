def add_tag(tag: str, tags: list[str] = []) -> list[str]:
    """Return a list containing the given tags plus `tag`. Calls must not affect each other."""
    tags.append(tag)
    return tags
