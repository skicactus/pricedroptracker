"""Threshold check + notification logic."""

import logging
import smtplib
from email.message import EmailMessage

import config

logger = logging.getLogger("tracker.alerts")


def check_and_alert(product, price: float, previous_price: float | None):
    """Compare the latest scraped price to the product's threshold and to the
    previous price, logging (and optionally emailing) a clear alert on a drop
    below threshold.
    """
    if price > product["threshold"]:
        return

    if previous_price is not None and previous_price <= product["threshold"]:
        # Already below threshold last time we checked; don't re-alert on
        # every single poll, only on the drop itself or a further drop.
        if price >= previous_price:
            return

    message = (
        f"PRICE DROP: {product['name']} is now ${price:.2f} "
        f"(threshold ${product['threshold']:.2f}) -> {product['url']}"
    )
    logger.warning(message)
    print(f"\n*** {message} ***\n")

    if config.EMAIL_ENABLED:
        _send_email_alert(product, price, message)


def _send_email_alert(product, price: float, message: str):
    if not (config.SMTP_USERNAME and config.SMTP_PASSWORD and config.ALERT_EMAIL_TO):
        logger.warning("EMAIL_ENABLED is true but SMTP settings are incomplete; skipping email")
        return

    email = EmailMessage()
    email["Subject"] = f"Price drop: {product['name']}"
    email["From"] = config.SMTP_USERNAME
    email["To"] = config.ALERT_EMAIL_TO
    email.set_content(message)

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as smtp:
            smtp.starttls()
            smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
            smtp.send_message(email)
    except smtplib.SMTPException as exc:
        logger.error(f"failed to send alert email: {exc}")
