import json
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_FILE = Path(__file__).resolve().parent.parent/"data"/"products.json"

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
        """
        Deterministically filters the product dataset based on extracted parameters.
        """
        results = self.products
        
        # Category Filter (normalized case-insensitive)
        if category:
            cat_lower = category.strip().lower()
            results = [p for p in results if p.get("category", "").lower() == cat_lower]
        
        # Minimum Price Floor
        if min_price is not None:
            resutls = [p for p in results if p.get("price", 0) >= min_price]

        # Maximum Price Ceiling 
        if max_price is not None:
            resutls = [p for p in results if p.get("price", 0) <= max_price]       

        # Keyword Filter in Name or Description
        if keyword:
            kw = keyword.strip().lower()
            results = [
                p for p in results if kw in p.get("name", "").lower() or kw in p.get("description", "").lower()
            ]
        
        return results

# Singleton instance
filter_engine = FilterEngine()
