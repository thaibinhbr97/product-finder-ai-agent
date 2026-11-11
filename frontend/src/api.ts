import {
  ActiveFilters,
  ChatResponsePayload,
  ExecutionStage,
  Product,
  ToolCallMeta,
} from "./types";

const ENV_API_URL = (import.meta.env.VITE_API_URL as string | undefined) || "http://localhost:8080";

export function getDefaultApiUrl(): string {
  return ENV_API_URL.replace(/\/+$/, "");
}

export async function fetchCatalog(baseUrl: string): Promise<Product[]> {
  const res = await fetch(`${baseUrl}/api/products`);
  if (!res.ok) {
    throw new Error(`Failed to fetch catalog: HTTP ${res.status}`);
  }
  const data = (await res.json()) as { products: Product[] };
  return data.products;
}

export async function checkHealth(baseUrl: string): Promise<{ ok: boolean; latencyMs: number }> {
  const t0 = performance.now();
  try {
    const res = await fetch(`${baseUrl}/api/health`);
    return { ok: res.ok, latencyMs: Math.round(performance.now() - t0) };
  } catch {
    return { ok: false, latencyMs: Math.round(performance.now() - t0) };
  }
}

export interface StreamCallbacks {
  onStage: (stage: ExecutionStage) => void;
  onToolCall: (toolCall: ToolCallMeta) => void;
}

export async function streamAgentChat(
  baseUrl: string,
  sessionId: string,
  message: string,
  callbacks: StreamCallbacks
): Promise<ChatResponsePayload> {
  const start = performance.now();
  callbacks.onStage("connecting");

  const res = await fetch(`${baseUrl}/api/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({ session_id: sessionId, message }),
  });

  const httpStatus = res.status;
  if (!res.ok || !res.body) {
    let detail = `HTTP ${res.status}`;
    try {
      const errJson = (await res.json()) as { detail?: string };
      if (errJson.detail) detail = errJson.detail;
    } catch {
      // ignore json parse error
    }
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalResult: ChatResponsePayload | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";

    for (const block of blocks) {
      if (!block.trim()) continue;
      let eventType = "message";
      const dataLines: string[] = [];

      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) {
          eventType = line.slice("event:".length).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice("data:".length).trim());
        }
      }

      if (dataLines.length === 0) continue;
      const payload = JSON.parse(dataLines.join("\n"));

      if (eventType === "stage") {
        const stage = payload.stage as ExecutionStage;
        callbacks.onStage(stage);
      } else if (eventType === "tool_call") {
        callbacks.onToolCall(payload as ToolCallMeta);
      } else if (eventType === "result") {
        callbacks.onStage("rendering");
        finalResult = payload as ChatResponsePayload;
      } else if (eventType === "error") {
        throw new Error(payload.detail || "Agent execution failed");
      }
    }
  }

  if (!finalResult) {
    throw new Error("Stream ended without a result payload.");
  }

  finalResult.http_status = httpStatus;
  finalResult.client_roundtrip_ms = Math.round((performance.now() - start) * 10) / 10;
  return finalResult;
}

export interface StateSyncResponse {
  status?: string;
  session_id: string;
  active_filters: ActiveFilters;
  products: Product[];
  product_ids: number[];
}

export async function syncFilterState(
  baseUrl: string,
  sessionId: string,
  activeFilters: ActiveFilters
): Promise<StateSyncResponse> {
  const res = await fetch(`${baseUrl}/api/state`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      active_filters: activeFilters,
    }),
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const errJson = (await res.json()) as { detail?: string };
      if (errJson.detail) detail = errJson.detail;
    } catch {
      // ignore
    }
    throw new Error(`State sync failed: ${detail}`);
  }

  return (await res.json()) as StateSyncResponse;
}
