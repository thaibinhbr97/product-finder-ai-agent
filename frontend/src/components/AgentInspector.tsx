import React, { useState } from "react";
import { ToolCallMeta } from "../types";

interface AgentInspectorProps {
  toolCall: ToolCallMeta | null;
  httpStatus: number;
  roundtripMs: number;
  serverLatencyMs: number;
}

const PARAM_LABELS: Record<string, string> = {
  category: "Category Name",
  max_price: "Maximum Price Threshold",
  min_price: "Minimum Price Threshold",
  keyword: "Search Keyword",
};

function formatParamValue(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "Unrestricted";
  }
  if (key === "max_price" || key === "min_price") {
    return `$${Number(value).toFixed(2)}`;
  }
  return String(value);
}

/**
 * Collapsible Tool Call Log (Agent Inspector).
 * Defaults to collapsed state to avoid cluttering the primary user flow.
 * Positioned directly above the agent's text response.
 */
export const AgentInspector: React.FC<AgentInspectorProps> = ({
  toolCall,
  httpStatus,
  roundtripMs,
  serverLatencyMs,
}) => {
  // Candidate Implementation Rule: must default to collapsed state.
  const [expanded, setExpanded] = useState<boolean>(false);

  const toolName = toolCall?.name ?? "No tool invoked";
  const statusText = toolCall
    ? `HTTP ${httpStatus} · ${toolCall.status.toUpperCase()}`
    : `HTTP ${httpStatus} · DIRECT_RESPONSE`;
  const isSuccess = httpStatus >= 200 && httpStatus < 300 && toolCall?.status !== "error";

  const entries = toolCall ? Object.entries(toolCall.parameters) : [];

  return (
    <div className="inspector-box">
      <button
        type="button"
        className="inspector-toggle"
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
      >
        <div className="inspector-toggle-left">
          <span className="inspector-chevron">{expanded ? "▾" : "▸"}</span>
          <span className="inspector-title">Agent Inspector · Tool Call Log</span>
          <code className="inspector-fn-pill">{toolName}</code>
        </div>
        <div className="inspector-toggle-right">
          <span
            className={`inspector-status-badge ${
              isSuccess ? "inspector-status-ok" : "inspector-status-err"
            }`}
          >
            {statusText}
          </span>
          <span className="inspector-latency-pill">{Math.round(roundtripMs)} ms</span>
        </div>
      </button>

      {expanded && (
        <div className="inspector-body">
          <div className="inspector-meta-grid">
            <div className="inspector-meta-card">
              <span className="inspector-meta-label">Tool Name</span>
              <code className="inspector-meta-value">{toolName}</code>
            </div>
            <div className="inspector-meta-card">
              <span className="inspector-meta-label">Execution Status</span>
              <span
                className={`inspector-meta-value ${
                  isSuccess ? "text-success" : "text-danger"
                }`}
              >
                {statusText}
              </span>
            </div>
            <div className="inspector-meta-card">
              <span className="inspector-meta-label">Round-Trip Latency</span>
              <code className="inspector-meta-value">
                {roundtripMs.toFixed(1)} ms (Server: {serverLatencyMs.toFixed(1)} ms
                {toolCall?.latency_ms != null
                  ? ` · Tool: ${toolCall.latency_ms.toFixed(2)} ms`
                  : ""}
                )
              </code>
            </div>
          </div>

          <div className="inspector-params-section">
            <div className="inspector-params-header">
              Extracted Parameters ({entries.length})
            </div>
            {entries.length === 0 ? (
              <div className="inspector-empty-params">
                No filter constraints extracted (unrestricted catalog query).
              </div>
            ) : (
              <dl className="inspector-kv-list">
                {entries.map(([key, val]) => (
                  <div key={key} className="inspector-kv-row">
                    <dt className="inspector-kv-key">
                      <span className="inspector-key-human">
                        {PARAM_LABELS[key] || key}
                      </span>
                      <code className="inspector-key-code">{key}</code>
                    </dt>
                    <dd className="inspector-kv-val">
                      <span className="inspector-val-formatted">
                        {formatParamValue(key, val)}
                      </span>
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
