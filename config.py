"""App-wide settings. Tracked items live in the database (see db.py) and are
added through the dashboard, not hardcoded here.
"""

import json
import os
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

# How often tracker.py --loop re-checks all tracked listings, in hours.
POLL_INTERVAL_HOURS = float(os.environ.get("POLL_INTERVAL_HOURS", 6))

# Depop session captured by depop_login.py (gitignored -- see data/.gitignore
# via the top-level .gitignore's "data/" rule).
DEPOP_SESSION_PATH = str(DATA_DIR / "depop_session.json")
DEPOP_ACCOUNT_PATH = DATA_DIR / "depop_account.json"


def get_depop_username() -> str | None:
    if not DEPOP_ACCOUNT_PATH.exists():
        return None
    return json.loads(DEPOP_ACCOUNT_PATH.read_text()).get("username")

# Optional email alerts (stretch goal). Leave EMAIL_ENABLED as False to just
# log drops to the console. If enabled, set these via environment variables
# rather than hardcoding credentials here.
EMAIL_ENABLED = os.environ.get("EMAIL_ENABLED", "false").lower() == "true"
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", "")
