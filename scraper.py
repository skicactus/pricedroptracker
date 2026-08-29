"""Fetch a product page and extract its price.

Tries several detection strategies in order, since arbitrary sites vary in
how they expose price data:
  1. an explicit manual CSS selector, if one was supplied
  2. JSON-LD Product/Offer structured data (most e-commerce sites embed this
     for SEO even when the visible price is rendered by JavaScript)
  3. Open Graph / itemprop price meta tags
  4. a heuristic scan for elements whose class name contains "price"

Only static HTML is fetched (no JS execution), so sites that render price
purely client-side with no structured data will raise PriceNotFoundError.
"""

import json
import re

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
REQUEST_TIMEOUT = 10

_PRICE_PATTERN = re.compile(r"\d[\d,]*\.?\d*")
_PRICE_CLASS_PATTERN = re.compile(r"price", re.IGNORECASE)


class FetchError(Exception):
    """The page could not be retrieved (network error, timeout, bad status)."""


class PriceNotFoundError(Exception):
    """The page was retrieved but no price could be extracted from it."""


def parse_price(raw) -> float:
    """Parse a currency string like '$1,299.00' or 'USD 45' into a float.

    Raises ValueError if no numeric price can be found in the string.
    """
    if raw is None:
        raise ValueError("price value is empty")
    text = str(raw).replace(",", "")
    match = _PRICE_PATTERN.search(text)
    if not match:
        raise ValueError(f"couldn't find a numeric price in {raw!r}")
    return float(match.group())


def fetch_page(url: str) -> BeautifulSoup:
    try:
        response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise FetchError(f"failed to fetch {url}: {exc}") from exc
    return BeautifulSoup(response.text, "html.parser")


def _iter_json_nodes(data):
    if isinstance(data, list):
        for item in data:
            yield from _iter_json_nodes(item)
    elif isinstance(data, dict):
        yield data
        if "@graph" in data:
            yield from _iter_json_nodes(data["@graph"])


def _price_from_offers(offers):
    if isinstance(offers, list):
        for offer in offers:
            price = _price_from_offers(offer)
            if price is not None:
                return price
        return None
    if isinstance(offers, dict):
        return offers.get("price") or offers.get("lowPrice")
    return None


def _price_from_json_ld(soup: BeautifulSoup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for node in _iter_json_nodes(data):
            if not isinstance(node, dict):
                continue
            raw_price = _price_from_offers(node.get("offers"))
            if raw_price is None:
                continue
            try:
                return parse_price(raw_price)
            except ValueError:
                continue
    return None


def _price_from_meta(soup: BeautifulSoup):
    for prop in ("product:price:amount", "og:price:amount"):
        tag = soup.find("meta", attrs={"property": prop})
        if tag and tag.get("content"):
            try:
                return parse_price(tag["content"])
            except ValueError:
                continue

    tag = soup.find(attrs={"itemprop": "price"})
    if tag:
        raw = tag.get("content") or tag.get_text()
        try:
            return parse_price(raw)
        except ValueError:
            pass
    return None


def _price_from_selector(soup: BeautifulSoup, selector: str):
    tag = soup.select_one(selector)
    if not tag:
        return None
    try:
        return parse_price(tag.get_text())
    except ValueError:
        return None


def _price_from_heuristic(soup: BeautifulSoup):
    candidates = soup.find_all(
        lambda t: t.name in ("span", "div", "p", "strong", "b")
        and t.get("class")
        and any(_PRICE_CLASS_PATTERN.search(c) for c in t.get("class"))
    )
    for tag in candidates:
        text = tag.get_text(strip=True)
        if not text:
            continue
        try:
            return parse_price(text)
        except ValueError:
            continue
    return None


def extract_price(soup: BeautifulSoup, selector: str | None = None) -> float:
    if selector:
        price = _price_from_selector(soup, selector)
        if price is not None:
            return price

    for strategy in (_price_from_json_ld, _price_from_meta, _price_from_heuristic):
        price = strategy(soup)
        if price is not None:
            return price

    raise PriceNotFoundError(
        "couldn't detect a price on this page (no structured data, meta tags, "
        "or price-labeled elements found)"
    )


def extract_title(soup: BeautifulSoup) -> str | None:
    tag = soup.find("meta", attrs={"property": "og:title"})
    if tag and tag.get("content"):
        return tag["content"].strip()
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return None


def scrape_price(url: str, selector: str | None = None) -> float:
    """Fetch `url` and return its price as a float, or raise FetchError /
    PriceNotFoundError."""
    soup = fetch_page(url)
    return extract_price(soup, selector)
