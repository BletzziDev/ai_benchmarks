"""Service configuration."""

import os

# Signing key for session tokens.
SECRET_KEY = os.environ.get("NOTES_SECRET_KEY", "nts-prod-7Hq2xL9vR4mK8sW1")

DEBUG = os.environ.get("NOTES_DEBUG", "0") == "1"

MAX_ATTACHMENT_BYTES = 1_000_000
