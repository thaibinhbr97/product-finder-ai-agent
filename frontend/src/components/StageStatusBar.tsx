import React from "react";
import { ExecutionStage } from "../types";

interface StageStatusBarProps {
  stage: ExecutionStage;
  elapsedMs: number;
  slowNotice: boolean;
}

const STAGES: Array<{
  key: ExecutionStage;
  label: string;
  description: string;
}> = [
  {
    key: "connecting",
    label: "Connecting / Warming",
    description: "Initiating connection or waking up serverless container instance",
  },
  {
    key: "parsing_intent",
    label: "Parsing Intent",
    description: "Google ADK agent analyzing prompt and extracting parameters",
  },
  {
    key: "executing_tool",
    label: "Executing Tool",
    description: "Running deterministic filter_products logic against catalog",
  },
  {
    key: "rendering",
    label: "Rendering",
    description: "Hydrating components and painting product grid layout",
  },
];

const STAGE_ORDER: Record<ExecutionStage, number> = {
  idle: -1,
  connecting: 0,
  parsing_intent: 1,
  executing_tool: 2,
  rendering: 3,
  complete: 4,
  error: -1,
};

export const StageStatusBar: React.FC<StageStatusBarProps> = ({
  stage,
  elapsedMs,
  slowNotice,
}) => {
  const currentIdx = STAGE_ORDER[stage] ?? -1;
  const isRunning =
    stage === "connecting" ||
    stage === "parsing_intent" ||
    stage === "executing_tool" ||
    stage === "rendering";

  const currentStageMeta = STAGES.find((s) => s.key === stage);

  return (
    <section className="stage-panel" aria-live="polite">
      <div className="stage-header">
        <div className="stage-badge-row">
          <span className={`stage-status-pill stage-pill-${stage}`}>
            <span className="stage-dot" />
            {stage === "idle" && "Ready"}
            {stage === "complete" && "Execution Complete"}
            {stage === "error" && "Execution Error"}
            {currentStageMeta && currentStageMeta.label}
          </span>
          {currentStageMeta && (
            <span className="stage-description">{currentStageMeta.description}</span>
          )}
        </div>
        {(isRunning || elapsedMs > 0) && (
          <span className="stage-timer" title="Measured execution time">
            {(elapsedMs / 1000).toFixed(2)}s ({Math.round(elapsedMs)} ms)
          </span>
        )}
      </div>

      <div className="stage-steps" role="list" aria-label="Agent execution lifecycle">
        {STAGES.map((step, index) => {
          const state =
            stage === "complete" || index < currentIdx
              ? "done"
              : index === currentIdx
              ? "active"
              : "upcoming";
          return (
            <div
              key={step.key}
              role="listitem"
              className={`stage-step stage-step-${state}`}
            >
              <div className="stage-step-bar" />
              <div className="stage-step-meta">
                <span className="stage-step-num">0{index + 1}</span>
                <span className="stage-step-label">{step.label}</span>
              </div>
            </div>
          );
        })}
      </div>

      {slowNotice && (
        <div className="cold-start-banner" role="status">
          <span className="cold-start-badge">LATENCY &gt; 1.5s</span>
          <div className="cold-start-text">
            <strong>Waking up serverless container...</strong>
            <span>
              Backend execution exceeded 1.5 seconds ({(elapsedMs / 1000).toFixed(1)}s
              elapsed). Waiting for Cloud Run instance warmup and Google ADK response.
            </span>
          </div>
        </div>
      )}
    </section>
  );
};
