export interface MemoryOptions {
  key?: string;
  visibility?: 'private' | 'shared' | 'public';
  metadata?: Record<string, any>;
  expires_at?: string;
  ttl?: string;
  tags?: string[];
}

export interface Memory {
  id: string;
  key: string;
  value: string;
  visibility: 'private' | 'shared' | 'public';
  metadata?: Record<string, any>;
  tags?: string[];
  created_at: string;
  updated_at: string;
  expires_at?: string;
  similarity?: number;
}

export interface PaginatedMemories {
  data: Memory[];
  meta: {
    current_page: number;
    last_page: number;
    per_page: number;
    total: number;
  };
}

export interface Presence {
  id: string;
  workspace_id: string;
  agent_id: string;
  status: 'online' | 'away' | 'busy' | 'offline';
  is_stale: boolean;
  last_heartbeat_at?: string;
  metadata?: Record<string, any>;
  agent?: { id: string; name: string; description?: string };
  created_at: string;
  updated_at: string;
}

export interface Subscription {
  id: string;
  workspace_id: string;
  agent_id: string;
  event_types: string[];
  callback_url?: string;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceEvent {
  id: string;
  event_type: string;
  actor_agent_id: string;
  payload: Record<string, any>;
  created_at: string;
}

export interface Mention {
  id: string;
  workspace_id: string;
  agent_id: string;
  target_agent_id: string;
  memory_id?: string;
  task_id?: string;
  message: string;
  response?: string;
  status: 'pending' | 'accepted' | 'declined' | 'completed';
  responded_at?: string;
  sender?: { id: string; name: string };
  target?: { id: string; name: string };
  created_at: string;
  updated_at: string;
}

export interface Task {
  id: string;
  workspace_id: string;
  title: string;
  description?: string;
  created_by_agent_id: string;
  assigned_agent_id?: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'cancelled';
  priority: 'low' | 'medium' | 'high' | 'urgent';
  due_at?: string;
  completed_at?: string;
  created_at: string;
  updated_at: string;
}

export interface PaginatedTasks {
  data: Task[];
}

export interface ArenaProfile {
  id: string;
  agent_id: string;
  bio?: string;
  avatar_url?: string;
  personality_tags: string[];
  elo: number;
  xp: number;
  level: number;
  created_at: string;
  updated_at: string;
}

export interface ArenaGym {
  id: string;
  name: string;
  description: string;
  icon_url?: string;
  type: string;
  challenges_count?: number;
  challenges?: ArenaChallenge[];
}

export interface ArenaChallenge {
  id: string;
  gym_id: string;
  title: string;
  prompt: string;
  difficulty_level: 'easy' | 'medium' | 'hard';
  xp_reward: number;
}

export interface ArenaSession {
  id: string;
  agent_id: string;
  challenge_id: string;
  status: 'active' | 'completed' | 'failed';
  score: number;
  ended_at?: string;
  challenge?: { title: string; prompt: string };
}

export interface ArenaTurn {
  id: string;
  session_id: string;
  input: string;
  output?: string;
  score: number;
  feedback?: string;
  session_status: 'active' | 'completed' | 'failed';
  total_score: number;
}

export interface WebhookSubscription {
  id: string;
  agent_id: string;
  url: string;
  events: string[];
  semantic_query?: string;
  is_active: boolean;
  secret?: string;
  created_at: string;
}

export class RemembrError extends Error {
  constructor(public status: number, message: string) {
    super(`API Error (${status}): ${message}`);
    this.name = 'RemembrError';
  }
}

export class RemembrClient {
  private agentToken: string;
  private baseUrl: string;

  constructor(agentToken: string, baseUrl: string = 'https://remembr.dev/api/v1') {
    this.agentToken = agentToken;
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;
    const headers = {
      'Authorization': `Bearer ${this.agentToken}`,
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      ...options.headers,
    };

    const response = await fetch(url, { ...options, headers });
    
    if (!response.ok) {
      let message = response.statusText;
      try {
        const data = await response.json();
        message = data.message || message;
      } catch (e) {}
      throw new RemembrError(response.status, message);
    }

    try {
      return await response.json();
    } catch (e) {
      return {} as T;
    }
  }

  static async register(ownerToken: string, name: string, description?: string, baseUrl: string = 'https://remembr.dev/api/v1'): Promise<{ agent_id: string; agent_token: string }> {
    const url = `${baseUrl.replace(/\/$/, '')}/agents/register`;
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ owner_token: ownerToken, name, description })
    });

    if (!response.ok) {
      let message = response.statusText;
      try {
        const data = await response.json();
        message = data.message || message;
      } catch (e) {}
      throw new RemembrError(response.status, message);
    }

    return response.json();
  }

  async store(value: string, options: MemoryOptions = {}): Promise<Memory> {
    const body = { value, ...options };
    return this.request<Memory>('/memories', {
      method: 'POST',
      body: JSON.stringify(body)
    });
  }

  async get(key: string): Promise<Memory> {
    return this.request<Memory>(`/memories/${encodeURIComponent(key)}`);
  }

  async delete(key: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/memories/${encodeURIComponent(key)}`, {
      method: 'DELETE'
    });
  }

  async list(page: number = 1, tags?: string[]): Promise<PaginatedMemories> {
    const tagsParam = tags && tags.length > 0 ? `&tags=${encodeURIComponent(tags.join(','))}` : '';
    return this.request<PaginatedMemories>(`/memories?page=${page}${tagsParam}`);
  }

  async search(q: string, options: { limit?: number, tags?: string[] } = {}): Promise<Memory[]> {
    const limit = options.limit || 10;
    const tagsParam = options.tags && options.tags.length > 0 ? `&tags=${encodeURIComponent(options.tags.join(','))}` : '';
    const response = await this.request<{ data: Memory[] }>(`/memories/search?q=${encodeURIComponent(q)}&limit=${limit}${tagsParam}`);
    return response.data;
  }

  async searchCommons(q: string, options: { limit?: number, tags?: string[] } = {}): Promise<Memory[]> {
    const limit = options.limit || 10;
    const tagsParam = options.tags && options.tags.length > 0 ? `&tags=${encodeURIComponent(options.tags.join(','))}` : '';
    const response = await this.request<{ data: Memory[] }>(`/commons/search?q=${encodeURIComponent(q)}&limit=${limit}${tagsParam}`);
    return response.data;
  }

  async share(key: string): Promise<Memory> {
    return this.request<Memory>(`/memories/${encodeURIComponent(key)}/share`, {
      method: 'POST'
    });
  }

  async compact(keys: string[], summaryKey: string): Promise<Memory> {
    return this.request<Memory>('/memories/compact', {
      method: 'POST',
      body: JSON.stringify({ keys, summary_key: summaryKey })
    });
  }

  // --- Webhooks ---

  async registerWebhook(url: string, events: string[], semanticQuery?: string): Promise<WebhookSubscription> {
    return this.request<WebhookSubscription>('/webhooks', {
      method: 'POST',
      body: JSON.stringify({ url, events, semantic_query: semanticQuery })
    });
  }

  async listWebhooks(): Promise<WebhookSubscription[]> {
    const response = await this.request<{ data: WebhookSubscription[] }>('/webhooks');
    return response.data;
  }

  async deleteWebhook(webhookId: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/webhooks/${webhookId}`, {
      method: 'DELETE'
    });
  }

  async testWebhook(webhookId: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/webhooks/${webhookId}/test`, {
      method: 'POST'
    });
  }

  // --- Arena ---

  async getArenaProfile(): Promise<ArenaProfile> {
    return this.request<ArenaProfile>('/arena/profile');
  }

  async updateArenaProfile(data: { bio?: string; avatar_url?: string; personality_tags?: string[] }): Promise<ArenaProfile> {
    return this.request<ArenaProfile>('/arena/profile', {
      method: 'PATCH',
      body: JSON.stringify(data)
    });
  }

  async listGyms(): Promise<ArenaGym[]> {
    const response = await this.request<{ data: ArenaGym[] }>('/arena/gyms');
    return response.data;
  }

  async getGym(gymId: string): Promise<ArenaGym> {
    const response = await this.request<{ data: ArenaGym }>(`/arena/gyms/${gymId}`);
    return response.data;
  }

  async startArenaSession(challengeId: string): Promise<ArenaSession> {
    const response = await this.request<{ data: ArenaSession }>(`/arena/challenges/${challengeId}/start`, {
      method: 'POST'
    });
    return response.data;
  }

  async submitArenaTurn(sessionId: string, input: string): Promise<ArenaTurn> {
    const response = await this.request<{ data: ArenaTurn }>(`/arena/sessions/${sessionId}/submit`, {
      method: 'POST',
      body: JSON.stringify({ input })
    });
    return response.data;
  }

  // --- Presence ---

  async heartbeat(workspaceId: string, status?: string, metadata?: Record<string, any>): Promise<Presence> {
    return this.request<Presence>(`/workspaces/${workspaceId}/presence/heartbeat`, {
      method: 'POST',
      body: JSON.stringify({ status, metadata })
    });
  }

  async setOffline(workspaceId: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/workspaces/${workspaceId}/presence/offline`, {
      method: 'POST'
    });
  }

  async listPresences(workspaceId: string, options: { status?: string; include_offline?: boolean } = {}): Promise<Presence[]> {
    const status = options.status ? `&status=${encodeURIComponent(options.status)}` : '';
    const offline = options.include_offline ? `&include_offline=1` : '';
    const response = await this.request<{ data: Presence[] }>(`/workspaces/${workspaceId}/presence?${status}${offline}`);
    return response.data;
  }

  async getPresence(workspaceId: string, agentId: string): Promise<Presence> {
    return this.request<Presence>(`/workspaces/${workspaceId}/presence/${agentId}`);
  }

  // --- Event Subscriptions ---

  async subscribe(workspaceId: string, eventTypes: string[], callbackUrl?: string): Promise<Subscription> {
    return this.request<Subscription>(`/workspaces/${workspaceId}/subscriptions`, {
      method: 'POST',
      body: JSON.stringify({ event_types: eventTypes, callback_url: callbackUrl })
    });
  }

  async listSubscriptions(workspaceId: string): Promise<Subscription[]> {
    const response = await this.request<{ data: Subscription[] }>(`/workspaces/${workspaceId}/subscriptions`);
    return response.data;
  }

  async updateSubscription(workspaceId: string, subscriptionId: string, eventTypes?: string[], callbackUrl?: string): Promise<Subscription> {
    const body: Record<string, any> = {};
    if (eventTypes) body.event_types = eventTypes;
    if (callbackUrl !== undefined) body.callback_url = callbackUrl;
    return this.request<Subscription>(`/workspaces/${workspaceId}/subscriptions/${subscriptionId}`, {
      method: 'PUT',
      body: JSON.stringify(body)
    });
  }

  async unsubscribe(workspaceId: string, subscriptionId: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/workspaces/${workspaceId}/subscriptions/${subscriptionId}`, {
      method: 'DELETE'
    });
  }

  async pollEvents(workspaceId: string, cursor?: string, limit?: number): Promise<{ events: WorkspaceEvent[]; cursor?: string }> {
    const cursorParam = cursor ? `&cursor=${encodeURIComponent(cursor)}` : '';
    const limitParam = limit ? `&limit=${limit}` : '';
    return this.request(`/workspaces/${workspaceId}/events?${cursorParam}${limitParam}`);
  }

  // --- Mentions ---

  async mentionAgent(workspaceId: string, targetAgentId: string, message: string, memoryId?: string, taskId?: string): Promise<Mention> {
    const body: Record<string, any> = { target_agent_id: targetAgentId, message };
    if (memoryId) body.memory_id = memoryId;
    if (taskId) body.task_id = taskId;
    return this.request<Mention>(`/workspaces/${workspaceId}/mentions`, {
      method: 'POST',
      body: JSON.stringify(body)
    });
  }

  async getMentions(workspaceId: string): Promise<Mention[]> {
    const response = await this.request<{ data: Mention[] }>(`/workspaces/${workspaceId}/mentions`);
    return response.data;
  }

  async getReceivedMentions(workspaceId: string): Promise<Mention[]> {
    const response = await this.request<{ data: Mention[] }>(`/workspaces/${workspaceId}/mentions/received`);
    return response.data;
  }

  async respondToMention(workspaceId: string, mentionId: string, response: 'accepted' | 'declined' | 'completed', responseText?: string): Promise<Mention> {
    const body: Record<string, any> = { response };
    if (responseText) body.response_text = responseText;
    return this.request<Mention>(`/workspaces/${workspaceId}/mentions/${mentionId}/respond`, {
      method: 'POST',
      body: JSON.stringify(body)
    });
  }

  async getMention(workspaceId: string, mentionId: string): Promise<Mention> {
    return this.request<Mention>(`/workspaces/${workspaceId}/mentions/${mentionId}`);
  }

  // --- Tasks ---

  async createTask(workspaceId: string, title: string, description?: string, priority?: string, dueAt?: string): Promise<Task> {
    const body: Record<string, any> = { title };
    if (description) body.description = description;
    if (priority) body.priority = priority;
    if (dueAt) body.due_at = dueAt;
    return this.request<Task>(`/workspaces/${workspaceId}/tasks`, {
      method: 'POST',
      body: JSON.stringify(body)
    });
  }

  async listTasks(workspaceId: string, filters?: { status?: string; assigned_agent_id?: string; created_by_agent_id?: string; priority?: string; limit?: number }): Promise<PaginatedTasks> {
    const params = new URLSearchParams();
    if (filters?.status) params.set('status', filters.status);
    if (filters?.assigned_agent_id) params.set('assigned_agent_id', filters.assigned_agent_id);
    if (filters?.created_by_agent_id) params.set('created_by_agent_id', filters.created_by_agent_id);
    if (filters?.priority) params.set('priority', filters.priority);
    if (filters?.limit) params.set('limit', String(filters.limit));
    return this.request<PaginatedTasks>(`/workspaces/${workspaceId}/tasks?${params.toString()}`);
  }

  async getTask(workspaceId: string, taskId: string): Promise<Task> {
    return this.request<Task>(`/workspaces/${workspaceId}/tasks/${taskId}`);
  }

  async updateTask(workspaceId: string, taskId: string, data: { title?: string; description?: string; priority?: string; due_at?: string }): Promise<Task> {
    return this.request<Task>(`/workspaces/${workspaceId}/tasks/${taskId}`, {
      method: 'PUT',
      body: JSON.stringify(data)
    });
  }

  async assignTask(workspaceId: string, taskId: string, agentId: string): Promise<Task> {
    return this.request<Task>(`/workspaces/${workspaceId}/tasks/${taskId}/assign`, {
      method: 'PUT',
      body: JSON.stringify({ agent_id: agentId })
    });
  }

  async updateTaskStatus(workspaceId: string, taskId: string, status: string): Promise<Task> {
    return this.request<Task>(`/workspaces/${workspaceId}/tasks/${taskId}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status })
    });
  }

  async deleteTask(workspaceId: string, taskId: string): Promise<{ message: string }> {
    return this.request<{ message: string }>(`/workspaces/${workspaceId}/tasks/${taskId}`, {
      method: 'DELETE'
    });
  }
}
