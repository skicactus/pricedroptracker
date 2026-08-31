"""All interaction with Depop: search, single-listing lookups, and wishlist
("likes") retrieval. Depop sits behind a Cloudflare JS challenge that blocks
plain HTTP requests, so every call here drives real (headless) Chromium via
Playwright rather than using `requests`.
"""

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = "https://www.depop.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
NAV_TIMEOUT_MS = 30_000
RENDER_WAIT_MS = 4_000

# Depop's own condition tiers, worst to best, and the query-param value each
# maps to. "min_condition" filtering below includes everything at or above
# the chosen tier.
CONDITIONS = [
    ("used_fair", "Used - Fair"),
    ("used_good", "Used - Good"),
    ("used_excellent", "Used - Excellent"),
    ("like_new", "Like new"),
    ("brand_new", "Brand new"),
]
CONDITION_VALUES = [value for value, _label in CONDITIONS]

_PRICE_PATTERN = re.compile(r"\d[\d,]*\.?\d*")


class DepopError(Exception):
    """Raised when a Depop page can't be loaded or parsed as expected."""


class NotLoggedInError(DepopError):
    """Raised when a wishlist request needs a session that isn't set up."""


def parse_price(raw) -> float:
    if raw is None:
        raise ValueError("price value is empty")
    text = str(raw).replace(",", "")
    match = _PRICE_PATTERN.search(text)
    if not match:
        raise ValueError(f"couldn't find a numeric price in {raw!r}")
    return float(match.group())


def conditions_at_or_above(min_condition: str) -> list[str]:
    """e.g. 'used_good' -> ['used_good', 'used_excellent', 'like_new', 'brand_new']"""
    if min_condition not in CONDITION_VALUES:
        raise ValueError(f"unknown condition {min_condition!r}")
    idx = CONDITION_VALUES.index(min_condition)
    return CONDITION_VALUES[idx:]


def build_search_url(query: str, conditions: list[str] | None = None) -> str:
    from urllib.parse import urlencode

    params = {"q": query, "sort": "priceAscending"}
    if conditions:
        params["conditions"] = ",".join(conditions)
    return f"{BASE_URL}/search/?{urlencode(params)}"


def _parse_card_text(text: str) -> dict | None:
    """Parse a search/likes result card's innerText, e.g.
    'Polo Ralph Lauren\\n\\nXL\\n\\n$10.00\\n\\n \\n\\n$2.00' (on sale) or
    'Polo Ralph Lauren\\n\\nXL\\n\\n$4.00' (not on sale).
    """
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    prices = []
    other = []
    for line in lines:
        try:
            prices.append(parse_price(line))
        except ValueError:
            other.append(line)
    if not prices:
        return None
    brand = other[0] if other else "Untitled listing"
    size = other[1] if len(other) > 1 else None
    price = prices[-1]  # sale price is listed last when there's a strikethrough original
    original_price = prices[0] if len(prices) > 1 else None
    return {"brand": brand, "size": size, "price": price, "original_price": original_price}


def _extract_cards(page) -> list[dict]:
    raw_cards = page.eval_on_selector_all(
        'a[href*="/products/"]',
        """els => els.map(e => {
            const card = e.closest('li') || e.parentElement.parentElement;
            return { href: e.href, text: card.innerText, label: e.getAttribute('aria-label') };
        })""",
    )
    results = []
    seen_urls = set()
    for raw in raw_cards:
        if raw["href"] in seen_urls:
            continue
        parsed = _parse_card_text(raw["text"])
        if not parsed:
            continue
        seen_urls.add(raw["href"])
        parsed["url"] = raw["href"]
        # aria-label carries Depop's own descriptive title (e.g. "Polo ralph
        # lauren men's grey shirt"), much better for re-searching than the
        # bare brand name pulled from the card's visible text.
        parsed["title"] = raw["label"] or parsed["brand"]
        results.append(parsed)
    return results


def search(query: str, min_condition: str | None = None, limit: int = 20) -> list[dict]:
    """Search Depop for `query`, cheapest first. If `min_condition` is given
    (one of CONDITION_VALUES), only listings at or above that condition tier
    are included.
    """
    conditions = conditions_at_or_above(min_condition) if min_condition else None
    url = build_search_url(query, conditions)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT, viewport={"width": 1280, "height": 1600})
            page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            page.wait_for_timeout(RENDER_WAIT_MS)
            cards = _extract_cards(page)
        finally:
            browser.close()

    return cards[:limit]


def find_cheaper_alternatives(
    title: str, current_price: float, exclude_url: str | None = None, limit: int = 5
) -> list[dict]:
    """Search Depop using `title` (typically a tracked item's own title) and
    return other listings priced below `current_price`, cheapest first.
    Depop has no SKU matching -- this is a title-text search, so results are
    "similar items from other sellers," not verified identical items.
    """
    results = search(title, limit=limit + 1)
    cheaper = [
        r for r in results if r["price"] < current_price and r["url"] != exclude_url
    ]
    return cheaper[:limit]


def get_listing(url: str) -> dict:
    """Fetch a single Depop product page's current price/condition/availability."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT, viewport={"width": 1280, "height": 1600})
            page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
            page.wait_for_timeout(RENDER_WAIT_MS)

            h1 = page.query_selector("h1")
            title = h1.inner_text().strip() if h1 else None

            price_el = page.query_selector('[aria-description="Price with fee"]')
            if not price_el:
                raise DepopError(f"couldn't find a price on {url} (listing may be removed)")
            price = parse_price(price_el.inner_text())

            attrs_el = page.query_selector('[data-testid="productPrimaryAttributes"]')
            attrs_text = attrs_el.inner_text() if attrs_el else ""
            attrs = [a.strip() for a in attrs_text.split("•") if a.strip()]

            button_labels = page.eval_on_selector_all(
                "button", "els => els.map(e => e.innerText.trim())"
            )
            available = any(
                label in ("Buy now", "Make offer", "Add to bag") for label in button_labels
            )
        finally:
            browser.close()

    return {
        "url": url,
        "title": title,
        "price": price,
        "attributes": attrs,
        "available": available,
    }


def capture_login_session(session_path: Path, timeout_ms: int = 300_000) -> str:
    """Open a real, visible browser for the user to log into Depop, then save
    the resulting session. Returns the logged-in username. Meant to be run
    interactively (see depop_login.py) -- not from a headless/sandboxed
    context, since it needs a real display.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        try:
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()
            page.goto(f"{BASE_URL}/login/", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)

            print("A browser window has opened. Log into your Depop account there.")
            print("Once you're logged in and can see your account, come back here and press Enter.")
            input()

            profile_links = page.eval_on_selector_all(
                'a[href$="/likes/"]', "els => els.map(e => e.getAttribute('href'))"
            )
            username = None
            for href in profile_links:
                match = re.match(r"^/([^/]+)/likes/$", href or "")
                if match:
                    username = match.group(1)
                    break
            if not username:
                raise NotLoggedInError(
                    "couldn't detect a logged-in account -- make sure you completed login "
                    "before pressing Enter"
                )

            session_path.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(session_path))
            return username
        finally:
            browser.close()


def get_wishlist(session_path: Path, username: str, limit: int = 100) -> list[dict]:
    """Fetch the signed-in user's liked items using a session captured by
    capture_login_session(). Raises NotLoggedInError if the session file is
    missing or has expired.
    """
    if not session_path.exists():
        raise NotLoggedInError(
            f"no saved Depop session at {session_path} -- run depop_login.py first"
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent=USER_AGENT, storage_state=str(session_path)
            )
            page = context.new_page()
            page.goto(
                f"{BASE_URL}/{username}/likes/", wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS
            )
            page.wait_for_timeout(RENDER_WAIT_MS)

            if page.url.startswith(f"{BASE_URL}/login"):
                raise NotLoggedInError("Depop session has expired -- run depop_login.py again")

            cards = _extract_cards(page)
        finally:
            browser.close()

    return cards[:limit]
