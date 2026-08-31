"""Scheduler: sync your Depop wishlist, re-check every tracked listing's
price, store it, and check thresholds.

Usage:
    python tracker.py --once   run a single pass, then exit
    python tracker.py --loop   run continuously, polling every POLL_INTERVAL_HOURS
"""

import argparse
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import alerts
import config
import db
import depop_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tracker")


def sync_wishlist():
    """Pull the signed-in Depop account's liked items and start tracking any
    that aren't already tracked. No-ops with a clear message if no session
    has been captured yet.
    """
    username = config.get_depop_username()
    if not username:
        logger.info("no Depop session set up yet -- run `python depop_login.py` to sync a wishlist")
        return

    try:
        liked = depop_client.get_wishlist(Path(config.DEPOP_SESSION_PATH), username)
    except depop_client.NotLoggedInError as exc:
        logger.warning(f"wishlist sync skipped: {exc}")
        return

    added = 0
    for item in liked:
        if db.product_exists(item["url"]):
            continue
        db.add_product(item["title"], item["url"], threshold=item["price"])
        added += 1
    logger.info(f"wishlist sync: {len(liked)} liked items, {added} newly tracked")


def run_once():
    db.init_db()
    sync_wishlist()

    products = db.list_products()
    if not products:
        logger.info("nothing tracked yet -- add items from the dashboard or sync your wishlist")
        return

    for product in products:
        logger.info(f"checking {product['name']} ({product['url']})")
        try:
            listing = depop_client.get_listing(product["url"])
        except depop_client.DepopError as exc:
            logger.error(f"  failed: {exc}")
            continue

        if not listing["available"]:
            logger.info("  sold / no longer available")
            continue

        price = listing["price"]
        previous = db.get_latest_price(product["id"])
        previous_price = previous["price"] if previous else None

        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db.insert_price(product["id"], price, timestamp)
        logger.info(f"  ${price:.2f} (previous: {previous_price})")

        alerts.check_and_alert(product, price, previous_price)

        alternatives = depop_client.find_cheaper_alternatives(
            listing["title"] or product["name"], current_price=price, exclude_url=product["url"]
        )
        alerts.alert_cheaper_alternatives(product, alternatives)


def run_loop():
    interval_seconds = config.POLL_INTERVAL_HOURS * 3600
    while True:
        run_once()
        logger.info(f"sleeping {config.POLL_INTERVAL_HOURS}h until next poll")
        time.sleep(interval_seconds)


def main():
    parser = argparse.ArgumentParser(description="Depop wishlist price tracker")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true", help="check everything once and exit")
    group.add_argument("--loop", action="store_true", help="check continuously on a timer")
    args = parser.parse_args()

    if args.once:
        run_once()
    else:
        run_loop()


if __name__ == "__main__":
    main()
