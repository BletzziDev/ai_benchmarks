class AuthError(Exception):
    """Base class for authentication errors."""


class InvalidToken(AuthError):
    """The token or cookie is malformed, forged, expired or otherwise unacceptable."""
