"""Service configuration."""

import os

# Signing key for session tokens: never hard-code it; it is read from the environment at startup.
SECRET_KEY_ENV = "NOTES_SECRET_KEY"
MIN_SECRET_KEY_LENGTH = 32


def load_secret_key() -> str:
    key = os.environ.get(SECRET_KEY_ENV, "")
    if len(key) < MIN_SECRET_KEY_LENGTH:
        raise RuntimeError(f"{SECRET_KEY_ENV} must be set to a random value of at least {MIN_SECRET_KEY_LENGTH} characters")
    return key

DEBUG = os.environ.get("NOTES_DEBUG", "0") == "1"

MAX_ATTACHMENT_BYTES = 1_000_000
