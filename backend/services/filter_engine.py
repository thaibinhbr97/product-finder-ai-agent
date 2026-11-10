"""Deterministic product filtering.

This is the only place products are selected. The LLM never picks products
itself: it only extracts structured parameters, which are applied here with
plain Python comparisons (no embeddings, no RAG).
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "products.json"

VALID_CATEGORIES = ("clothing", "electronics", "accessories", "groceries")
FILTER_KEYS = ("category", "min_price", "max_price", "keyword")


def normalize_filters(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Cleans a filter dict: drops empty values, lower-cases strings, coerces
    prices to float, and rejects unknown keys / categories.

    Raises:
        ValueError: if a value is invalid (unknown category, negative or
            non-numeric price).
    """
    clean: Dict[str, Any] = {}
    if not raw:
        return clean

    for key, value in raw.items():
        if key not in FILTER_KEYS:
            raise ValueError(f"Unknown filter '{key}'. Allowed: {', '.join(FILTER_KEYS)}")
        if value is None or (isinstance(value, str) and not value.strip()):
            continue

        if key == "category":
            category = str(value).strip().lower()
            if category not in VALID_CATEGORIES:
                raise ValueError(
                    f"Unknown category '{value}'. Allowed: {', '.join(VALID_CATEGORIES)}"
                )
            clean["category"] = category
        elif key in ("min_price", "max_price"):
            try:
                price = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"'{key}' must be a number, got {value!r}") from None
            if price < 0:
                raise ValueError(f"'{key}' cannot be negative")
            clean[key] = price
        elif key == "keyword":
            clean["keyword"] = str(value).strip().lower()

    return clean


class FilterEngine:
    def __init__(self, data_path: Path = DATA_FILE):
        with open(data_path, "r", encoding="utf-8") as f:
            self.products: List[Dict[str, Any]] = json.load(f)

    def filter_products(
        self,
        category: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        keyword: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Returns products matching ALL given constraints (inclusive bounds)."""
        results = self.products

        if category:
            cat = category.strip().lower()
            results = [p for p in results if p["category"].lower() == cat]

        if min_price is not None:
            results = [p for p in results if p["price"] >= min_price]

        if max_price is not None:
            results = [p for p in results if p["price"] <= max_price]

        if keyword:
            kw = keyword.strip().lower()
            results = [
                p
                for p in results
                if kw in p["name"].lower() or kw in p["description"].lower()
            ]

        return results

    def apply(self, filters: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Validates a filter dict and applies it."""
        return self.filter_products(**normalize_filters(filters))


# Singleton instance
filter_engine = FilterEngine()
