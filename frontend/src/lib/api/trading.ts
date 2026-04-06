import { api } from './client';
import type { Trade } from '../../../../shared/types/generated/typescript/index';

export type { Trade };

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
  listTrades: () => api.get<{ data: Trade[] }>('/v1/trades').then(res => res.data?.data ?? res.data),

  openTrade: (data: {
    ticker: string;
    direction: 'long' | 'short';
    quantity: number;
  }) => api.post<Trade>('/v1/trades', data).then(res => (res.data as any)?.data ?? res.data),

  closeTrade: (id: string, exit_price: string) =>
    api.post<Trade>(`/v1/trades/${id}/close`, { exit_price }).then(res => (res.data as any)?.data ?? res.data),

  getLeaderboard: () => api.get<{ data: TradingLeaderboardEntry[] }>('/v1/trading/leaderboard').then(res => res.data?.data ?? res.data),
};
