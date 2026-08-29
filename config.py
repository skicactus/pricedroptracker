"""App-wide settings. Products themselves live in the database (see db.py) and
are added through the dashboard, not hardcoded here.
"""

import os

# How often tracker.py --loop re-scrapes all products, in hours.
POLL_INTERVAL_HOURS = float(os.environ.get("POLL_INTERVAL_HOURS", 6))

# Optional email alerts (stretch goal). Leave EMAIL_ENABLED as False to just
# log drops to the console. If enabled, set these via environment variables
# rather than hardcoding credentials here.
EMAIL_ENABLED = os.environ.get("EMAIL_ENABLED", "false").lower() == "true"
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", "")
