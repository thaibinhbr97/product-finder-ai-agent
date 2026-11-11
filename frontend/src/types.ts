export type Category = "clothing" | "electronics" | "accessories" | "groceries";

export interface Product {
  id: number;
  name: string;
  category: Category | string;
  description: string;
  price: number;
  image: string;
}

export interface ActiveFilters {
  category?: string;
  min_price?: number;
  max_price?: number;
  keyword?: string;
}

export type FilterKey = keyof ActiveFilters;

export interface ToolCallMeta {
  name: string;
  parameters: Record<string, unknown>;
  status: string;
  latency_ms: number | null;
  error?: string;
}

export type ExecutionStage =
  | "idle"
  | "connecting"
  | "parsing_intent"
  | "executing_tool"
  | "rendering"
  | "complete"
  | "error";

export interface ChatResponsePayload {
  session_id: string;
  reply: string;
  products: Product[];
  product_ids: number[];
  active_filters: ActiveFilters;
  tool_call: ToolCallMeta | null;
  tool_calls?: ToolCallMeta[];
  latency_ms: number;
  http_status?: number;
  client_roundtrip_ms?: number;
}

export interface TurnRecord {
  id: string;
  query: string;
  reply: string;
  toolCall: ToolCallMeta | null;
  httpStatus: number;
  roundtripMs: number;
  serverLatencyMs: number;
  appliedFilters: ActiveFilters;
  matchCount: number;
  timestamp: string;
}

export type SyncState = "idle" | "syncing" | "synced" | "error";
