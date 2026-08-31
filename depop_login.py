"""Run this yourself, in your own terminal, to log into Depop.

This opens a real, visible browser window on your machine. You type your
Depop username/password (and any 2FA) directly into that window -- nothing
you type is seen by this script. Once you're logged in, it saves the
resulting session cookies to data/depop_session.json (gitignored) so the
rest of the app can check your wishlist and track listings without asking
you to log in again.

Re-run this whenever the saved session expires (tracker.py / dashboard.py
will tell you if that happens).
"""

from pathlib import Path

import config
import depop_client

SESSION_PATH = Path(config.DEPOP_SESSION_PATH)
ACCOUNT_PATH = SESSION_PATH.with_name("depop_account.json")


def main():
    print("Opening a browser window for Depop login...")
    username = depop_client.capture_login_session(SESSION_PATH)

    import json

    ACCOUNT_PATH.write_text(json.dumps({"username": username}))

    print(f"Logged in as '{username}'. Session saved to {SESSION_PATH}.")
    print("You can now sync your wishlist from the dashboard or tracker.py.")


if __name__ == "__main__":
    main()
