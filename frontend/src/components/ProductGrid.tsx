import React from "react";
import { Product } from "../types";

interface ProductGridProps {
  products: Product[];
  onResetFilters?: () => void;
}

export const ProductGrid: React.FC<ProductGridProps> = ({
  products,
  onResetFilters,
}) => {
  if (products.length === 0) {
    return (
      <div className="empty-grid-state">
        <div className="empty-grid-title">No Matching Products Found</div>
        <p className="empty-grid-subtitle">
          No catalog items matched all active constraints. Dismiss a constraint chip
          above or ask the agent to broaden your search.
        </p>
        {onResetFilters && (
          <button type="button" className="btn-secondary" onClick={onResetFilters}>
            Clear All Constraints
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="product-grid" role="list" aria-label="Filtered products">
      {products.map((product) => (
        <article key={product.id} role="listitem" className="product-card">
          <div className="product-image-wrap">
            <img
              src={product.image}
              alt={product.name}
              className="product-image"
              loading="lazy"
            />
          </div>
          <div className="product-card-body">
            <div className="product-card-top">
              <span className={`category-pill category-${product.category}`}>
                {product.category}
              </span>
              <span className="product-price">${product.price.toFixed(2)}</span>
            </div>
            <h3 className="product-title">{product.name}</h3>
            <p className="product-desc">{product.description}</p>
          </div>
        </article>
      ))}
    </div>
  );
};
