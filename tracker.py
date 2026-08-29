"""Scheduler: scrape every tracked product, store the price, check thresholds.

Usage:
    python tracker.py --once   run a single pass over all products, then exit
    python tracker.py --loop   run continuously, polling every POLL_INTERVAL_HOURS
"""

import argparse
import logging
import time
from datetime import datetime, timezone

import alerts
import config
import db
import scraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("tracker")


def run_once():
    db.init_db()
    products = db.list_products()
    if not products:
        logger.info("no products tracked yet -- add some from the dashboard")
        return

    for product in products:
        logger.info(f"scraping {product['name']} ({product['url']})")
        try:
            price = scraper.scrape_price(product["url"], product["selector"])
        except (scraper.FetchError, scraper.PriceNotFoundError) as exc:
            logger.error(f"  failed: {exc}")
            continue

        previous = db.get_latest_price(product["id"])
        previous_price = previous["price"] if previous else None

        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db.insert_price(product["id"], price, timestamp)
        logger.info(f"  ${price:.2f} (previous: {previous_price})")

        alerts.check_and_alert(product, price, previous_price)


def run_loop():
    interval_seconds = config.POLL_INTERVAL_HOURS * 3600
    while True:
        run_once()
        logger.info(f"sleeping {config.POLL_INTERVAL_HOURS}h until next poll")
        time.sleep(interval_seconds)


def main():
    parser = argparse.ArgumentParser(description="Price drop tracker scheduler")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true", help="scrape all products once and exit")
    group.add_argument("--loop", action="store_true", help="scrape continuously on a timer")
    args = parser.parse_args()

    if args.once:
        run_once()
    else:
        run_loop()


if __name__ == "__main__":
    main()
