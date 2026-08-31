import pytest

import depop_client as dc


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("$1,299.00", 1299.00),
        ("$45", 45.0),
        ("  $9.99  ", 9.99),
    ],
)
def test_parse_price(raw, expected):
    assert dc.parse_price(raw) == expected


def test_parse_price_raises_on_no_number():
    with pytest.raises(ValueError):
        dc.parse_price("Sold out")


def test_conditions_at_or_above_good():
    assert dc.conditions_at_or_above("used_good") == [
        "used_good",
        "used_excellent",
        "like_new",
        "brand_new",
    ]


def test_conditions_at_or_above_brand_new():
    assert dc.conditions_at_or_above("brand_new") == ["brand_new"]


def test_conditions_at_or_above_unknown_raises():
    with pytest.raises(ValueError):
        dc.conditions_at_or_above("mint")


def test_build_search_url_no_conditions():
    url = dc.build_search_url("grey polo shirt")
    assert url == "https://www.depop.com/search/?q=grey+polo+shirt&sort=priceAscending"


def test_build_search_url_with_conditions():
    url = dc.build_search_url("grey polo shirt", conditions=["used_good", "used_excellent"])
    assert "conditions=used_good%2Cused_excellent" in url


def test_parse_card_text_with_sale_price():
    text = "Polo Ralph Lauren\n\nXL\n\n$10.00\n\n \n\n$2.00"
    parsed = dc._parse_card_text(text)
    assert parsed == {
        "title": "Polo Ralph Lauren",
        "size": "XL",
        "price": 2.00,
        "original_price": 10.00,
    }


def test_parse_card_text_without_sale_price():
    text = "Polo Ralph Lauren\n\nXL\n\n$4.00"
    parsed = dc._parse_card_text(text)
    assert parsed == {
        "title": "Polo Ralph Lauren",
        "size": "XL",
        "price": 4.00,
        "original_price": None,
    }


def test_parse_card_text_with_no_price_returns_none():
    assert dc._parse_card_text("Polo Ralph Lauren\n\nSold out") is None
