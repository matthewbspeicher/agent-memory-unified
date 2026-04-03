/** A single memory object returned by the API. */
export interface Memory {
  id: string;
  key: string | null;
  value: string;
  summary: string | null;
  type: MemoryType;
  category: string | null;
  visibility: Visibility;
  workspace_id: string | null;
  importance: number;
  confidence: number;
  access_count: number;
  useful_count: number;
  has_full_content: boolean;
  metadata: Record<string, unknown>;
  tags: string[];
  relations: MemoryRelation[];
  created_at: string;
  updated_at: string;
  expires_at: string | null;
}

/** A memory with an additional similarity score from search results. */
export interface SearchMemory extends Memory {
  similarity: number;
}

/** A memory with agent info, returned from commons endpoints. */
export interface CommonsMemory extends Memory {
  agent: {
    id: string;
    name: string;
    description: string | null;
  };
}

/** A commons search result with both agent info and similarity. */
export interface CommonsSearchMemory extends CommonsMemory {
  similarity: number;
}

export interface MemoryRelation {
  id: string;
  type: string;
}

export type MemoryType =
  | "fact"
  | "preference"
  | "procedure"
  | "lesson"
  | "error_fix"
  | "tool_tip"
  | "context"
  | "note";

export type Visibility = "private" | "shared" | "public" | "workspace";

/** Extracted memory returned from session extraction. */
export interface ExtractedMemory {
  key: string;
  value: string;
  type: MemoryType;
  importance: number;
}

/** Options for storing a new memory. */
export interface StoreOptions {
  key?: string;
  value: string;
  type?: MemoryType;
  category?: string;
  visibility?: Visibility;
  workspace_id?: string;
  metadata?: Record<string, unknown>;
  importance?: number;
  confidence?: number;
  expires_at?: string;
  ttl?: string;
  tags?: string[];
  relations?: MemoryRelation[];
}

/** Options for searching memories. */
export interface SearchOptions {
  q: string;
  limit?: number;
  tags?: string[];
  type?: MemoryType;
  category?: string;
  detail?: "full" | "summary";
}

/** Options for updating an existing memory. */
export interface UpdateOptions {
  value?: string;
  type?: MemoryType;
  category?: string | null;
  visibility?: Visibility;
  workspace_id?: string | null;
  metadata?: Record<string, unknown>;
  importance?: number;
  confidence?: number;
  expires_at?: string | null;
  ttl?: string | null;
  tags?: string[];
  relations?: MemoryRelation[];
}

/** Options for listing memories. */
export interface ListOptions {
  page?: number;
  tags?: string[];
  type?: MemoryType;
  category?: string;
  detail?: "full" | "summary";
}

/** Options for session extraction. */
export interface ExtractSessionOptions {
  transcript: string;
  category?: string;
  visibility?: Visibility;
}

/** Paginated response wrapper. */
export interface PaginatedResponse<T> {
  data: T[];
  meta: {
    total: number;
    per_page: number;
    current_page: number;
    last_page: number;
  };
}

/** Search response wrapper. */
export interface SearchResponse<T> {
  data: T[];
}

/** Session extraction response. */
export interface ExtractSessionResponse {
  data: Memory[];
  meta: {
    extracted_count: number;
    stored_count: number;
  };
}

/** A single entry on a leaderboard. */
export interface LeaderboardEntry {
  agent_id: string;
  agent_name: string;
  score: number;
  top_categories?: Record<string, number>;
  streak_days?: number;
}

/** Leaderboard response from the API. */
export interface LeaderboardResponse {
  type: string;
  entries: LeaderboardEntry[];
}

/** Knowledge graph data returned by the graph endpoints. */
export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/** A node in the knowledge graph (one memory). */
export interface GraphNode {
  id: string;
  key: string | null;
  summary: string;
  type: MemoryType;
  category: string | null;
  importance: number;
  created_at: string;
}

/** An edge in the knowledge graph (a relation between memories). */
export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
}
