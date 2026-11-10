import pytest

from backend.services.filter_engine import filter_engine, normalize_filters


def ids(products):
    return sorted(p["id"] for p in products)


def test_category_search():
    assert ids(filter_engine.filter_products(category="clothing")) == [0, 5, 7, 8]


def test_combined_search_matches_pdf_example():
    # PDF: $45 Hoodie and $15 T-Shirt included, pricier clothing excluded.
    result = filter_engine.filter_products(category="clothing", max_price=50)
    assert ids(result) == [0, 7]


def test_price_bounds_are_inclusive():
    assert ids(filter_engine.filter_products(min_price=45, max_price=45)) == [0]


def test_range_and_keyword():
    assert ids(filter_engine.filter_products(category="electronics", min_price=50, max_price=300)) == [2, 3, 4]
    assert ids(filter_engine.filter_products(keyword="cotton")) == [0, 7]


def test_empty_result():
    assert filter_engine.filter_products(category="groceries", min_price=100) == []


def test_case_insensitive_category():
    assert ids(filter_engine.filter_products(category="  Clothing ")) == [0, 5, 7, 8]


def test_normalize_filters():
    assert normalize_filters({"category": "Clothing", "max_price": "50", "keyword": None}) == {
        "category": "clothing",
        "max_price": 50.0,
    }
    for bad in ({"category": "furniture"}, {"max_price": -1}, {"max_price": "abc"}, {"color": "red"}):
        with pytest.raises(ValueError):
            normalize_filters(bad)
