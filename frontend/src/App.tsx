import React, { useEffect, useRef, useState } from "react";
import {
  checkHealth,
  fetchCatalog,
  getDefaultApiUrl,
  streamAgentChat,
  syncFilterState,
} from "./api";
import { AgentInspector } from "./components/AgentInspector";
import { ConstraintChipsBar } from "./components/ConstraintChipsBar";
import { ProductGrid } from "./components/ProductGrid";
import { SkeletonGrid } from "./components/SkeletonGrid";
import { StageStatusBar } from "./components/StageStatusBar";
import { FALLBACK_CATALOG, filterCatalog } from "./data/catalog";
import {
  ActiveFilters,
  ExecutionStage,
  FilterKey,
  Product,
  SyncState,
  TurnRecord,
} from "./types";

const EXAMPLE_PROMPTS = [
  "Show me all clothing items.",
  "What clothing items are under $50?",
  "Which ones are red?",
  "Which ones are cotton?",
  "Find electronics between $50 and $300",
  "Show me groceries over $100",
];

function makeSessionId(): string {
  return `sess-${Math.random().toString(36).slice(2, 9)}`;
}

export const App: React.FC = () => {
  const [apiBaseUrl, setApiBaseUrl] = useState<string>(getDefaultApiUrl);
  const [sessionId, setSessionId] = useState<string>(makeSessionId);
  const [backendOnline, setBackendOnline] = useState<boolean | null>(null);

  const [catalog, setCatalog] = useState<Product[]>(FALLBACK_CATALOG);
  const [activeFilters, setActiveFilters] = useState<ActiveFilters>({});
  const [displayedProducts, setDisplayedProducts] =
    useState<Product[]>(FALLBACK_CATALOG);

  const [promptInput, setPromptInput] = useState<string>("");
  const [stage, setStage] = useState<ExecutionStage>("idle");
  const [elapsedMs, setElapsedMs] = useState<number>(0);
  const [slowNotice, setSlowNotice] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [syncState, setSyncState] = useState<SyncState>("idle");
  const [turns, setTurns] = useState<TurnRecord[]>([]);

  const timerRef = useRef<number | null>(null);

  const isLoading =
    stage === "connecting" ||
    stage === "parsing_intent" ||
    stage === "executing_tool" ||
    stage === "rendering";

  // Probe backend health & load live catalog on mount / endpoint change
  useEffect(() => {
    let cancelled = false;
    (async () => {
      const health = await checkHealth(apiBaseUrl);
      if (cancelled) return;
      setBackendOnline(health.ok);
      if (health.ok) {
        try {
          const items = await fetchCatalog(apiBaseUrl);
          if (!cancelled && items.length > 0) {
            setCatalog(items);
            setDisplayedProducts(() =>
              Object.keys(activeFilters).length === 0
                ? items
                : filterCatalog(items, activeFilters)
            );
          }
        } catch {
          // keep fallback catalog
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [apiBaseUrl]);

  const stopTimer = () => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const handleSubmitQuery = async (rawQuery?: string) => {
    const query = (rawQuery ?? promptInput).trim();
    if (!query || isLoading) return;

    setPromptInput("");
    setErrorMessage(null);
    setSlowNotice(false);
    setElapsedMs(0);
    setStage("connecting");

    const startPerf = performance.now();
    stopTimer();
    timerRef.current = window.setInterval(() => {
      const currentElapsed = performance.now() - startPerf;
      setElapsedMs(currentElapsed);
      if (currentElapsed >= 1500) {
        setSlowNotice(true);
      }
    }, 80);

    try {
      const response = await streamAgentChat(apiBaseUrl, sessionId, query, {
        onStage: (nextStage) => setStage(nextStage),
        onToolCall: () => {
          // tool_call received; stage transitions handled via SSE
        },
      });

      stopTimer();
      const totalElapsed = performance.now() - startPerf;
      setElapsedMs(totalElapsed);
      setSlowNotice(totalElapsed >= 1500);

      setActiveFilters(response.active_filters || {});
      setDisplayedProducts(response.products || []);
      setStage("complete");
      setBackendOnline(true);

      const newTurn: TurnRecord = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        query,
        reply: response.reply,
        toolCall: response.tool_call,
        httpStatus: response.http_status ?? 200,
        roundtripMs: response.client_roundtrip_ms ?? totalElapsed,
        serverLatencyMs: response.latency_ms,
        appliedFilters: response.active_filters || {},
        matchCount: (response.products || []).length,
        timestamp: new Date().toLocaleTimeString(),
      };
      setTurns((prev) => [newTurn, ...prev]);
    } catch (err) {
      stopTimer();
      setStage("error");
      setErrorMessage(err instanceof Error ? err.message : String(err));
    }
  };

  /**
   * Part 2 #4: Interactive State Mutation & Context Synchronization.
   * 1. Instantly re-filters the product grid on the client (0ms wait).
   * 2. Synchronizes the mutated filter state back to the backend ADK session.
   */
  const applyManualFilterMutation = async (nextFilters: ActiveFilters) => {
    // 1. Immediate client-side update
    setActiveFilters(nextFilters);
    const localFiltered = filterCatalog(catalog, nextFilters);
    setDisplayedProducts(localFiltered);

    // 2. Synchronize state to backend ADK session memory
    setSyncState("syncing");
    try {
      const synced = await syncFilterState(apiBaseUrl, sessionId, nextFilters);
      setActiveFilters(synced.active_filters);
      setDisplayedProducts(synced.products);
      setSyncState("synced");
    } catch (err) {
      setSyncState("error");
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to sync state with backend"
      );
    }
  };

  const handleDismissChip = (key: FilterKey) => {
    const nextFilters: ActiveFilters = { ...activeFilters };
    delete nextFilters[key];
    void applyManualFilterMutation(nextFilters);
  };

  const handleClearAll = () => {
    void applyManualFilterMutation({});
  };

  const handleNewSession = () => {
    const nextId = makeSessionId();
    setSessionId(nextId);
    setActiveFilters({});
    setDisplayedProducts(catalog);
    setTurns([]);
    setStage("idle");
    setElapsedMs(0);
    setSlowNotice(false);
    setErrorMessage(null);
    setSyncState("idle");
  };

  const latestTurn = turns[0] ?? null;

  return (
    <div className="app-shell">
      <header className="top-header">
        <div className="brand-block">
          <div className="brand-badge">GOOGLE ADK · CLOUD RUN</div>
          <h1 className="brand-title">Product Finder · Agent Control Interface</h1>
          <p className="brand-subtitle">
            Deterministic parameter extraction, live execution telemetry, and
            bidirectional context synchronization
          </p>
        </div>

        <div className="endpoint-controls">
          <div className="endpoint-field">
            <label htmlFor="api-url-input" className="endpoint-label">
              Backend Endpoint
              <span
                className={`conn-dot ${
                  backendOnline === null
                    ? "conn-pending"
                    : backendOnline
                    ? "conn-ok"
                    : "conn-err"
                }`}
              />
            </label>
            <input
              id="api-url-input"
              type="url"
              className="endpoint-input"
              value={apiBaseUrl}
              onChange={(e) => setApiBaseUrl(e.target.value.replace(/\/+$/, ""))}
              placeholder="http://localhost:8080"
            />
          </div>

          <div className="session-pill-group">
            <span className="session-badge" title="Active ADK session ID">
              Session: <code>{sessionId}</code>
            </span>
            <button
              type="button"
              className="btn-reset-session"
              onClick={handleNewSession}
            >
              Reset Session
            </button>
          </div>
        </div>
      </header>

      <main className="main-workspace">
        {/* Prompt & Quick-Test Bar */}
        <section className="query-panel">
          <form
            className="query-form"
            onSubmit={(e) => {
              e.preventDefault();
              void handleSubmitQuery();
            }}
          >
            <input
              type="text"
              className="query-input"
              value={promptInput}
              onChange={(e) => setPromptInput(e.target.value)}
              placeholder='Ask in natural language (e.g., "What clothing items are under $50?")'
              disabled={isLoading}
            />
            <button
              type="submit"
              className="query-submit-btn"
              disabled={isLoading || !promptInput.trim()}
            >
              {isLoading ? "Executing..." : "Run Agent"}
            </button>
          </form>

          <div className="preset-prompts-row">
            <span className="preset-label">Walkthrough Scenarios:</span>
            {EXAMPLE_PROMPTS.map((sample) => (
              <button
                key={sample}
                type="button"
                className="preset-chip"
                disabled={isLoading}
                onClick={() => void handleSubmitQuery(sample)}
              >
                {sample}
              </button>
            ))}
          </div>
        </section>

        {/* Component 1a: Multi-Stage Live Status */}
        <StageStatusBar
          stage={stage}
          elapsedMs={elapsedMs}
          slowNotice={slowNotice}
        />

        {errorMessage && (
          <div className="error-alert" role="alert">
            <strong>Backend Error:</strong> {errorMessage}
          </div>
        )}

        {/* Component 2: Collapsible Tool Call Log (Agent Inspector) + Agent Response */}
        {latestTurn && (
          <section className="agent-response-card" aria-label="Latest agent response">
            <div className="turn-query-header">
              <span className="turn-query-badge">Prompt</span>
              <span className="turn-query-text">“{latestTurn.query}”</span>
              <span className="turn-timestamp">{latestTurn.timestamp}</span>
            </div>

            {/* Positioned directly above the agent's text response */}
            <AgentInspector
              key={latestTurn.id}
              toolCall={latestTurn.toolCall}
              httpStatus={latestTurn.httpStatus}
              roundtripMs={latestTurn.roundtripMs}
              serverLatencyMs={latestTurn.serverLatencyMs}
            />

            <div className="agent-reply-box">
              <span className="agent-reply-label">Agent Response</span>
              <p className="agent-reply-text">
                {latestTurn.reply || "Filters applied to catalog."}
              </p>
            </div>
          </section>
        )}

        {/* Component 3 & 4: Active Constraint Chips Bar + Bidirectional State Mutation */}
        <ConstraintChipsBar
          activeFilters={activeFilters}
          onDismissChip={handleDismissChip}
          onClearAll={handleClearAll}
          syncState={syncState}
          totalCount={catalog.length}
          filteredCount={displayedProducts.length}
        />

        {/* Component 1b: Skeleton Card Grid Loader vs Final Product Grid */}
        {isLoading ? (
          <SkeletonGrid count={6} />
        ) : (
          <ProductGrid
            products={displayedProducts}
            onResetFilters={
              Object.keys(activeFilters).length > 0 ? handleClearAll : undefined
            }
          />
        )}

        {/* Previous Turns History */}
        {turns.length > 1 && (
          <section className="history-section">
            <h2 className="history-heading">Previous Turns in Session</h2>
            <div className="history-list">
              {turns.slice(1).map((turn) => (
                <div key={turn.id} className="history-item">
                  <div className="turn-query-header">
                    <span className="turn-query-badge">Prompt</span>
                    <span className="turn-query-text">“{turn.query}”</span>
                    <span className="turn-timestamp">{turn.timestamp}</span>
                  </div>
                  <AgentInspector
                    toolCall={turn.toolCall}
                    httpStatus={turn.httpStatus}
                    roundtripMs={turn.roundtripMs}
                    serverLatencyMs={turn.serverLatencyMs}
                  />
                  <p className="history-reply">{turn.reply}</p>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
};
