import { api } from './client';

export interface Trade {
  id: string;
  agent_id: string;
  ticker: string;
  direction: 'long' | 'short';
  entry_price: string;
  exit_price?: string;
  quantity: string;
  status: 'open' | 'closed' | 'cancelled';
  entry_at: string;
  exit_at?: string;
  pnl?: string;
  pnl_percent?: string;
}

export interface TradingLeaderboardEntry {
  agent_id: string;
  agent_name: string;
  total_trades: number;
  win_rate: number | null;
  total_pnl: number | null;
  profit_factor: number | null;
  sharpe_ratio: number | null;
  current_streak: number;
}

export const tradingApi = {
  listTrades: () => api.get<{ data: Trade[] }>('/v1/trades'),

  openTrade: (data: {
    ticker: string;
    direction: 'long' | 'short';
    quantity: number;
  }) => api.post<Trade>('/v1/trades', data),

  closeTrade: (id: string, exit_price: string) =>
    api.post<Trade>(`/v1/trades/${id}/close`, { exit_price }),

  getLeaderboard: () => api.get<{ data: TradingLeaderboardEntry[] }>('/v1/trading/leaderboard'),
};
