import pytest
from bs4 import BeautifulSoup

from scraper import extract_price, extract_title, parse_price, PriceNotFoundError


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("$1,299.00", 1299.00),
        ("$45", 45.0),
        ("USD 45.50", 45.50),
        (45.5, 45.5),
        ("  $9.99  ", 9.99),
        ("Now $19.00 (was $25.00)", 19.00),
    ],
)
def test_parse_price(raw, expected):
    assert parse_price(raw) == expected


def test_parse_price_raises_on_no_number():
    with pytest.raises(ValueError):
        parse_price("Sold out")


def test_parse_price_raises_on_none():
    with pytest.raises(ValueError):
        parse_price(None)


def test_extract_price_from_json_ld():
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type": "Product", "name": "Cool Shirt", "offers": {"@type": "Offer", "price": "39.99", "priceCurrency": "USD"}}
    </script>
    </head><body></body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    assert extract_price(soup) == 39.99


def test_extract_price_from_json_ld_graph():
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@graph": [{"@type": "WebPage"}, {"@type": "Product", "offers": {"price": "12.50"}}]}
    </script>
    </head></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    assert extract_price(soup) == 12.50


def test_extract_price_from_meta_tag():
    html = """
    <html><head>
    <meta property="product:price:amount" content="29.99">
    </head></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    assert extract_price(soup) == 29.99


def test_extract_price_from_itemprop():
    html = '<html><body><span itemprop="price" content="15.00">$15.00</span></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    assert extract_price(soup) == 15.00


def test_extract_price_from_manual_selector():
    html = '<html><body><div class="cost">$99.00</div></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    assert extract_price(soup, selector=".cost") == 99.00


def test_extract_price_heuristic_fallback():
    html = '<html><body><span class="product-price">$59.00</span></body></html>'
    soup = BeautifulSoup(html, "html.parser")
    assert extract_price(soup) == 59.00


def test_extract_price_raises_when_nothing_found():
    html = "<html><body><p>No price here</p></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    with pytest.raises(PriceNotFoundError):
        extract_price(soup)


def test_extract_title_prefers_og_title():
    html = """
    <html><head>
    <meta property="og:title" content="Cool Shirt - Store">
    <title>Fallback Title</title>
    </head></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    assert extract_title(soup) == "Cool Shirt - Store"


def test_extract_title_falls_back_to_title_tag():
    html = "<html><head><title>Just A Title</title></head></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert extract_title(soup) == "Just A Title"
