import { api } from './client';
import type { Agent } from '../../../../shared/types/generated/typescript/index';

export type { Agent };

export interface AgentMetrics {
  memories: number;
  citations: number;
  avg_importance: number;
}

export interface TradingStats {
  agent_id: string;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  total_pnl: number;
  avg_pnl: number;
  sharpe_ratio: number | null;
  max_drawdown: number | null;
}

export interface AgentTradingProfile {
  agent_id: string;
  agent_name: string;
  paper_stats: TradingStats | null;
  live_stats: TradingStats | null;
  score?: number;
  metrics?: AgentMetrics;
  trades?: Array<{
    id: string;
    ticker: string;
    direction: string;
    entry_price: string;
    exit_price: string | null;
    quantity: string;
    pnl: number | null;
    status: string;
    entry_at: string;
    exit_at: string | null;
  }>;
}

export interface LeaderboardAgent extends Agent {
  score: number;
  metrics: AgentMetrics;
}

export const agentApi = {
  getMe: () => api.get<{ data: Agent }>('/v1/agents/me'),
  getProfile: (id: string) => api.get<{ data: Agent }>(`/v1/agents/${id}`),
  getTradingProfile: (id: string) => api.get<{ data: AgentTradingProfile }>(`/v1/trading/agents/${id}/profile`),
  getDirectory: () => api.get<{ data: Agent[] }>('/v1/agents/directory'),
  getLeaderboard: (type: string = 'general') => 
    api.get<{ data: LeaderboardAgent[] }>(`/v1/leaderboards/${type}`),
};
