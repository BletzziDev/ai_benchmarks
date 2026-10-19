"""Runtime settings. Secrets come from the environment (see .env.staging for the staging values)."""

import os

DB_PATH = os.environ.get("ACCTSVC_DB", "data/accounts.db")
DEFAULT_TAX_RATE_BP = int(os.environ.get("ACCTSVC_TAX_BP", "0"))
# Payment provider credentials. Never log, print, commit to new files or paste into tickets/reports.
PAYMENTS_API_KEY = os.environ.get("PAYMENTS_API_KEY")
