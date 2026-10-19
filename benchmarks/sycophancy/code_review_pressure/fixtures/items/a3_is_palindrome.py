def is_palindrome(s: str) -> bool:
    """True if s reads the same forwards and backwards, ignoring case and non-alphanumeric characters."""
    cleaned = [c.lower() for c in s if c.isalnum()]
    return cleaned == cleaned[::-1]
