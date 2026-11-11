import React from "react";

interface SkeletonGridProps {
  count?: number;
}

/**
 * Animated skeleton card layout placeholder matching the exact dimensions
 * and grid structure of `ProductGrid`. No circular loading spinners are used.
 */
export const SkeletonGrid: React.FC<SkeletonGridProps> = ({ count = 6 }) => {
  return (
    <div
      className="product-grid"
      aria-busy="true"
      aria-label="Loading matching products"
    >
      {Array.from({ length: count }).map((_, idx) => (
        <article key={idx} className="product-card skeleton-card">
          <div className="product-image-wrap skeleton-shimmer" />
          <div className="product-card-body">
            <div className="product-card-top">
              <span className="skeleton-line skeleton-pill skeleton-shimmer" />
              <span className="skeleton-line skeleton-price skeleton-shimmer" />
            </div>
            <div className="skeleton-line skeleton-title skeleton-shimmer" />
            <div className="skeleton-line skeleton-desc-1 skeleton-shimmer" />
            <div className="skeleton-line skeleton-desc-2 skeleton-shimmer" />
          </div>
        </article>
      ))}
    </div>
  );
};
