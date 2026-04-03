import type {
  Memory,
  MemoryType,
  MemorySearchResult,
  StoreOptions,
  UpdateOptions,
  SearchOptions,
  ListOptions,
  PaginatedResponse,
  RegisterResponse,
  AgentProfile,
  RemembrClientOptions,
} from './types.js';

import {
  RemembrError,
  AuthenticationError,
  NotFoundError,
  ValidationError,
  RateLimitError,
} from './errors.js';

export type {
  Memory,
  MemoryType,
  MemorySearchResult,
  StoreOptions,
  UpdateOptions,
  SearchOptions,
  ListOptions,
  PaginatedResponse,
  RegisterResponse,
  AgentProfile,
  RemembrClientOptions,
};

export {
  RemembrError,
  AuthenticationError,
  NotFoundError,
  ValidationError,
  RateLimitError,
};

const DEFAULT_BASE_URL = 'https://remembr.dev/api/v1';

export class RemembrClient {
  private readonly baseUrl: string;
  private readonly token: string;

  constructor(agentToken: string, options: RemembrClientOptions = {}) {
    this.token = agentToken;
    this.baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, '');
  }

  // ---------------------------------------------------------------------------
  // Factory
  // ---------------------------------------------------------------------------

  static async register(
    ownerToken: string,
    name: string,
    options: RemembrClientOptions & { description?: string } = {},
  ): Promise<{ client: RemembrClient; agentId: string; agentToken: string }> {
    const baseUrl = (options.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, '');
    const res = await fetch(`${baseUrl}/agents/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        description: options.description,
        owner_token: ownerToken,
      }),
    });

    const data = (await res.json()) as RegisterResponse & { error?: string };
    if (!res.ok) {
      throw new RemembrError(data.error ?? 'Registration failed', res.status);
    }

    return {
      client: new RemembrClient(data.agent_token, { baseUrl }),
      agentId: data.agent_id,
      agentToken: data.agent_token,
    };
  }

  // ---------------------------------------------------------------------------
  // Write
  // ---------------------------------------------------------------------------

  async remember(value: string, options: StoreOptions = {}): Promise<Memory> {
    return this.request<Memory>('POST', '/memories', { value, ...options });
  }

  async set(key: string, value: string, visibility: Memory['visibility'] = 'private'): Promise<Memory> {
    return this.remember(value, { key, visibility });
  }

  async update(key: string, data: UpdateOptions): Promise<Memory> {
    return this.request<Memory>('PATCH', `/memories/${encodeURIComponent(key)}`, data);
  }

  async forget(key: string): Promise<void> {
    await this.request<void>('DELETE', `/memories/${encodeURIComponent(key)}`);
  }

  // ---------------------------------------------------------------------------
  // Read
  // ---------------------------------------------------------------------------

  async get(key: string): Promise<Memory> {
    return this.request<Memory>('GET', `/memories/${encodeURIComponent(key)}`);
  }

  async list(options: ListOptions = {}): Promise<PaginatedResponse<Memory>> {
    const params = new URLSearchParams();
    if (options.page) params.set('page', String(options.page));
    if (options.tags?.length) params.set('tags', options.tags.join(','));
    if (options.type) params.set('type', options.type);
    const qs = params.toString();
    return this.request<PaginatedResponse<Memory>>('GET', `/memories${qs ? '?' + qs : ''}`);
  }

  // ---------------------------------------------------------------------------
  // Search
  // ---------------------------------------------------------------------------

  async search(query: string, options: SearchOptions = {}): Promise<MemorySearchResult[]> {
    const params = new URLSearchParams({ q: query });
    if (options.limit) params.set('limit', String(options.limit));
    if (options.tags?.length) params.set('tags', options.tags.join(','));
    if (options.type) params.set('type', options.type);
    const res = await this.request<{ data: MemorySearchResult[] }>('GET', `/memories/search?${params}`);
    return (res as unknown as { data: MemorySearchResult[] }).data;
  }

  async searchCommons(query: string, options: SearchOptions = {}): Promise<MemorySearchResult[]> {
    const params = new URLSearchParams({ q: query });
    if (options.limit) params.set('limit', String(options.limit));
    if (options.tags?.length) params.set('tags', options.tags.join(','));
    if (options.type) params.set('type', options.type);
    const res = await this.request<{ data: MemorySearchResult[] }>('GET', `/commons/search?${params}`);
    return (res as unknown as { data: MemorySearchResult[] }).data;
  }

  // ---------------------------------------------------------------------------
  // Sharing
  // ---------------------------------------------------------------------------

  async shareWith(key: string, agentId: string): Promise<void> {
    await this.request<void>('POST', `/memories/${encodeURIComponent(key)}/share`, {
      agent_id: agentId,
    });
  }

  // ---------------------------------------------------------------------------
  // Internals
  // ---------------------------------------------------------------------------

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers: Record<string, string> = {
      Authorization: `Bearer ${this.token}`,
      Accept: 'application/json',
    };

    const init: RequestInit = { method, headers };

    if (body !== undefined && method !== 'GET' && method !== 'DELETE') {
      headers['Content-Type'] = 'application/json';
      init.body = JSON.stringify(body);
    }

    const res = await fetch(url, init);

    if (!res.ok) {
      await this.handleError(res);
    }

    if (res.status === 204 || method === 'DELETE') {
      return undefined as unknown as T;
    }

    return (await res.json()) as T;
  }

  private async handleError(res: Response): Promise<never> {
    let data: Record<string, unknown>;
    try {
      data = (await res.json()) as Record<string, unknown>;
    } catch {
      throw new RemembrError(`HTTP ${res.status}`, res.status);
    }

    const message = (data.error ?? data.message ?? `HTTP ${res.status}`) as string;

    switch (res.status) {
      case 401:
        throw new AuthenticationError(message);
      case 404:
        throw new NotFoundError(message);
      case 422:
        throw new ValidationError(message, (data.errors ?? {}) as Record<string, string[]>);
      case 429:
        throw new RateLimitError(
          res.headers.get('Retry-After') ? Number(res.headers.get('Retry-After')) : null,
        );
      default:
        throw new RemembrError(message, res.status);
    }
  }
}
