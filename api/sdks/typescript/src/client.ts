import {
  RemembrError,
  AuthError,
  NotFoundError,
  RateLimitError,
  ValidationError,
} from "./errors";
import type {
  Memory,
  SearchMemory,
  CommonsSearchMemory,
  StoreOptions,
  SearchOptions,
  UpdateOptions,
  ListOptions,
  ExtractSessionOptions,
  PaginatedResponse,
  SearchResponse,
  ExtractSessionResponse,
  GraphData,
} from "./types";

export interface RemembrOptions {
  /** Base URL of the Remembr API (default: "https://remembr.dev/api/v1"). */
  baseUrl?: string;
}

/**
 * TypeScript client for the Remembr API.
 *
 * Uses native `fetch` — zero runtime dependencies.
 *
 * @example
 * ```ts
 * const remembr = new Remembr("amc_your_token");
 * const memory = await remembr.store({ value: "I prefer dark mode." });
 * const results = await remembr.search({ q: "preferences" });
 * ```
 */
export class Remembr {
  private readonly token: string;
  private readonly baseUrl: string;

  constructor(token: string, options: RemembrOptions = {}) {
    this.token = token;
    this.baseUrl = (options.baseUrl ?? "https://remembr.dev/api/v1").replace(
      /\/$/,
      "",
    );
  }

  // ---------------------------------------------------------------------------
  // Internal HTTP helper
  // ---------------------------------------------------------------------------

  private async request<T>(
    method: string,
    path: string,
    body?: Record<string, unknown>,
    query?: Record<string, string | number | undefined>,
  ): Promise<T> {
    let url = `${this.baseUrl}/${path.replace(/^\//, "")}`;

    if (query) {
      const params = new URLSearchParams();
      for (const [key, value] of Object.entries(query)) {
        if (value !== undefined && value !== null) {
          params.set(key, String(value));
        }
      }
      const qs = params.toString();
      if (qs) url += `?${qs}`;
    }

    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.token}`,
      Accept: "application/json",
    };

    const init: RequestInit = { method, headers };

    if (body) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(body);
    }

    const response = await fetch(url, init);

    if (!response.ok) {
      const text = await response.text();
      let message: string;
      try {
        const json = JSON.parse(text);
        message = json.error ?? json.message ?? text;
      } catch {
        message = text;
      }

      switch (response.status) {
        case 401:
          throw new AuthError(message);
        case 404:
          throw new NotFoundError(message);
        case 422:
          throw new ValidationError(message);
        case 429:
          throw new RateLimitError(message);
        default:
          throw new RemembrError(message, response.status);
      }
    }

    // Handle 204 No Content
    if (response.status === 204) {
      return undefined as T;
    }

    return response.json() as Promise<T>;
  }

  // ---------------------------------------------------------------------------
  // Memory CRUD
  // ---------------------------------------------------------------------------

  /**
   * Store a new memory.
   *
   * Returns the created memory object directly (not wrapped in `{ data }`).
   */
  async store(options: StoreOptions): Promise<Memory> {
    return this.request<Memory>("POST", "memories", options as unknown as unknown as Record<string, unknown>);
  }

  /**
   * Get a single memory by its key.
   *
   * Returns the memory object directly (not wrapped in `{ data }`).
   */
  async get(key: string, detail?: "full" | "summary"): Promise<Memory> {
    return this.request<Memory>("GET", `memories/${encodeURIComponent(key)}`, undefined, {
      detail,
    });
  }

  /**
   * Update an existing memory by key.
   *
   * Returns the updated memory object directly (not wrapped in `{ data }`).
   */
  async update(key: string, options: UpdateOptions): Promise<Memory> {
    return this.request<Memory>(
      "PATCH",
      `memories/${encodeURIComponent(key)}`,
      options as unknown as Record<string, unknown>,
    );
  }

  /** Delete a memory by key. */
  async delete(key: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(
      "DELETE",
      `memories/${encodeURIComponent(key)}`,
    );
  }

  // ---------------------------------------------------------------------------
  // Listing & Search
  // ---------------------------------------------------------------------------

  /** List the authenticated agent's memories (paginated). */
  async list(options: ListOptions = {}): Promise<PaginatedResponse<Memory>> {
    const query: Record<string, string | number | undefined> = {
      page: options.page,
      type: options.type,
      category: options.category,
      detail: options.detail,
      tags: options.tags?.join(","),
    };

    return this.request<PaginatedResponse<Memory>>("GET", "memories", undefined, query);
  }

  /**
   * Semantically search the authenticated agent's memories.
   *
   * Returns `{ data: SearchMemory[] }`.
   */
  async search(options: SearchOptions): Promise<SearchResponse<SearchMemory>> {
    const query: Record<string, string | number | undefined> = {
      q: options.q,
      limit: options.limit,
      type: options.type,
      category: options.category,
      detail: options.detail,
      tags: options.tags?.join(","),
    };

    return this.request<SearchResponse<SearchMemory>>(
      "GET",
      "memories/search",
      undefined,
      query,
    );
  }

  /**
   * Semantically search the public commons (all agents).
   *
   * Returns `{ data: CommonsSearchMemory[] }`.
   */
  async searchCommons(
    options: SearchOptions,
  ): Promise<SearchResponse<CommonsSearchMemory>> {
    const query: Record<string, string | number | undefined> = {
      q: options.q,
      limit: options.limit,
      type: options.type,
      category: options.category,
      detail: options.detail,
      tags: options.tags?.join(","),
    };

    return this.request<SearchResponse<CommonsSearchMemory>>(
      "GET",
      "commons/search",
      undefined,
      query,
    );
  }

  // ---------------------------------------------------------------------------
  // Feedback & Sharing
  // ---------------------------------------------------------------------------

  /** Submit relevance feedback for a memory (useful or not). */
  async feedback(key: string, useful: boolean): Promise<{ message: string }> {
    return this.request<{ message: string }>(
      "POST",
      `memories/${encodeURIComponent(key)}/feedback`,
      { useful },
    );
  }

  /** Share a memory with another agent by their ID. */
  async share(key: string, agentId: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(
      "POST",
      `memories/${encodeURIComponent(key)}/share`,
      { agent_id: agentId },
    );
  }

  // ---------------------------------------------------------------------------
  // Session Extraction
  // ---------------------------------------------------------------------------

  /**
   * Extract durable memories from a conversation transcript.
   *
   * The API uses an LLM to identify key facts, preferences, and lessons
   * from the transcript, then stores each as a separate memory.
   */
  async extractSession(
    options: ExtractSessionOptions,
  ): Promise<ExtractSessionResponse> {
    return this.request<ExtractSessionResponse>(
      "POST",
      "sessions/extract",
      options as unknown as Record<string, unknown>,
    );
  }

  // ---------------------------------------------------------------------------
  // Knowledge Graph
  // ---------------------------------------------------------------------------

  /**
   * Get the knowledge graph for the authenticated agent.
   *
   * Returns nodes (memories) and edges (relations between them).
   */
  async graph(): Promise<GraphData> {
    return this.request<GraphData>("GET", "agents/me/graph");
  }
}
