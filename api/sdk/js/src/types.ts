export type MemoryType = 'fact' | 'preference' | 'procedure' | 'lesson' | 'error_fix' | 'tool_tip' | 'context' | 'note';

export interface Memory {
  id: string;
  agent_id: string;
  key: string | null;
  value: string;
  type: MemoryType;
  visibility: 'private' | 'shared' | 'public' | 'workspace';
  metadata: Record<string, unknown> | null;
  tags: string[] | null;
  importance: number;
  confidence: number;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface MemorySearchResult extends Memory {
  similarity: number;
}

export interface StoreOptions {
  key?: string;
  type?: MemoryType;
  visibility?: 'private' | 'shared' | 'public' | 'workspace';
  metadata?: Record<string, unknown>;
  tags?: string[];
  ttl?: string;
  expires_at?: string;
  importance?: number;
  confidence?: number;
  workspace_id?: string;
  relations?: Array<{ target_id: string; type: string }>;
}

export interface UpdateOptions {
  value?: string;
  type?: MemoryType;
  visibility?: 'private' | 'shared' | 'public' | 'workspace';
  metadata?: Record<string, unknown>;
  tags?: string[];
  importance?: number;
  confidence?: number;
  expires_at?: string | null;
}

export interface SearchOptions {
  limit?: number;
  type?: MemoryType;
  tags?: string[];
}

export interface ListOptions {
  page?: number;
  type?: MemoryType;
  tags?: string[];
}

export interface PaginatedResponse<T> {
  data: T[];
  current_page: number;
  last_page: number;
  per_page: number;
  total: number;
}

export interface RegisterResponse {
  agent_id: string;
  agent_token: string;
  message: string;
}

export interface AgentProfile {
  id: string;
  name: string;
  description: string | null;
  memory_count: number;
  is_active: boolean;
  last_seen_at: string | null;
}

export interface RemembrClientOptions {
  baseUrl?: string;
}
