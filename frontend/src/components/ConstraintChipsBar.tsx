import React from "react";
import { ActiveFilters, FilterKey, SyncState } from "../types";

interface ConstraintChipsBarProps {
  activeFilters: ActiveFilters;
  onDismissChip: (key: FilterKey) => void;
  onClearAll: () => void;
  syncState: SyncState;
  totalCount: number;
  filteredCount: number;
}

export interface ConstraintChipDescriptor {
  identifier: FilterKey;
  displayLabel: string;
}

function capitalize(word: string): string {
  return word ? word.charAt(0).toUpperCase() + word.slice(1) : "";
}

export function buildConstraintChips(filters: ActiveFilters): ConstraintChipDescriptor[] {
  const chips: ConstraintChipDescriptor[] = [];

  if (filters.category) {
    chips.push({
      identifier: "category",
      displayLabel: `Category: ${capitalize(filters.category)}`,
    });
  }
  if (filters.min_price !== undefined && filters.min_price !== null) {
    chips.push({
      identifier: "min_price",
      displayLabel: `Min Price: $${filters.min_price}`,
    });
  }
  if (filters.max_price !== undefined && filters.max_price !== null) {
    chips.push({
      identifier: "max_price",
      displayLabel: `Max Price: $${filters.max_price}`,
    });
  }
  if (filters.keyword) {
    chips.push({
      identifier: "keyword",
      displayLabel: `Keyword: "${filters.keyword}"`,
    });
  }

  return chips;
}

/**
 * Active Constraint Chips Bar.
 * Rendered directly above the product grid. Dismissing a chip immediately
 * updates the displayed products and synchronizes state back to the ADK session.
 */
export const ConstraintChipsBar: React.FC<ConstraintChipsBarProps> = ({
  activeFilters,
  onDismissChip,
  onClearAll,
  syncState,
  totalCount,
  filteredCount,
}) => {
  const chips = buildConstraintChips(activeFilters);

  return (
    <section className="chips-bar" aria-label="Active search constraints">
      <div className="chips-bar-left">
        <span className="chips-bar-title">Active Constraints</span>
        {chips.length === 0 ? (
          <span className="chips-none-badge">
            None · Showing all {totalCount} catalog items
          </span>
        ) : (
          <div className="chips-list" role="list">
            {chips.map((chip) => (
              <span
                key={chip.identifier}
                role="listitem"
                data-filter-id={chip.identifier}
                className="constraint-chip"
              >
                <span className="constraint-chip-key">{chip.identifier}</span>
                <span className="constraint-chip-label">{chip.displayLabel}</span>
                <button
                  type="button"
                  className="constraint-chip-dismiss"
                  onClick={() => onDismissChip(chip.identifier)}
                  aria-label={`Remove ${chip.displayLabel} constraint`}
                  title={`Remove ${chip.displayLabel}`}
                >
                  ×
                </button>
              </span>
            ))}

            {chips.length > 1 && (
              <button
                type="button"
                className="chips-clear-all-btn"
                onClick={onClearAll}
              >
                Clear All
              </button>
            )}
          </div>
        )}
      </div>

      <div className="chips-bar-right">
        {syncState !== "idle" && (
          <span className={`sync-pill sync-pill-${syncState}`}>
            {syncState === "syncing" && "Syncing context to ADK..."}
            {syncState === "synced" && "✓ Context synchronized"}
            {syncState === "error" && "⚠ Context sync failed"}
          </span>
        )}
        <span className="results-counter">
          Showing <strong>{filteredCount}</strong> of {totalCount} products
        </span>
      </div>
    </section>
  );
};
