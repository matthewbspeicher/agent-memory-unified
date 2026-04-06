import { api } from './client';

export interface Agent {
  id: string;
  name: string;
  description: string;
  creator?: string;
  is_active: boolean;
  last_seen_at?: string;
}

export interface AgentMetrics {
  memories: number;
  citations: number;
  avg_importance: number;
}

export interface LeaderboardAgent extends Agent {
  score: number;
  metrics: AgentMetrics;
}

export const agentApi = {
  getMe: () => api.get<{ data: Agent }>('/v1/agents/me'),
  getProfile: (id: string) => api.get<{ data: Agent }>(`/v1/agents/${id}`),
  getTradingProfile: (id: string) => api.get<{ data: any }>(`/v1/trading/agents/${id}/profile`),
  getDirectory: () => api.get<{ data: Agent[] }>('/v1/agents/directory'),
  getLeaderboard: (type: string = 'general') => 
    api.get<{ data: LeaderboardAgent[] }>(`/v1/leaderboards/${type}`),
};
