// frontend/src/lib/api/competition.ts
import axios from 'axios';
import { useQuery } from '@tanstack/react-query';

/**
 * Trading API client for Competition endpoints.
 * In dev mode, Vite proxies /api/competition → trading service (port 8080).
 */
const tradingApi = axios.create({
  baseURL: '/api',
  headers: {
    'X-API-Key': import.meta.env.VITE_TRADING_API_KEY || (import.meta.env.DEV ? 'local-validator-dev' : ''),
  },
});

// ── Types ──

export type CompetitorType = 'agent' | 'miner' | 'provider';
export type Tier = 'diamond' | 'gold' | 'silver' | 'bronze';

export interface Competitor {
  id: string;
  type: CompetitorType;
  name: string;
  ref_id: string;
  status: string;
  elo: number;
  tier: Tier;
  matches_count: number;
  streak: number;
  best_streak: number;
}

export interface LeaderboardResponse {
  leaderboard: Competitor[];
  competitor_count: number;
}

export interface DashboardSummary {
  leaderboard: Competitor[];
  competitor_count: number;
}

export interface EloHistoryPoint {
  elo: number;
  tier: string;
  elo_delta: number;
  recorded_at: string;
}

export interface CompetitorDetail {
  id: string;
  type: CompetitorType;
  name: string;
  ref_id: string;
  status: string;
  metadata: Record<string, unknown>;
  ratings: Record<string, { elo: number }>;
}

// ── API Functions ──

export const competitionApi = {
  getDashboardSummary: (asset = 'BTC') =>
    tradingApi.get<DashboardSummary>('/competition/dashboard/summary', { params: { asset } })
      .then(res => res.data),

  getLeaderboard: (params: { asset?: string; type?: string; limit?: number; offset?: number } = {}) =>
    tradingApi.get<LeaderboardResponse>('/competition/leaderboard', { params })
      .then(res => res.data),

  getCompetitor: (id: string) =>
    tradingApi.get<CompetitorDetail>(`/competition/competitors/${id}`)
      .then(res => res.data),

  getEloHistory: (id: string, asset = 'BTC', days = 30) =>
    tradingApi.get<{ competitor_id: string; asset: string; history: EloHistoryPoint[] }>(
      `/competition/competitors/${id}/elo-history`,
      { params: { asset, days } },
    ).then(res => res.data),
};

// ── TanStack Query Hooks ──

export function useLeaderboard(asset = 'BTC', type?: string) {
  return useQuery({
    queryKey: ['competition', 'leaderboard', asset, type],
    queryFn: () => competitionApi.getLeaderboard({ asset, type }),
    refetchInterval: 30_000,
  });
}

export function useDashboardSummary(asset = 'BTC') {
  return useQuery({
    queryKey: ['competition', 'dashboard', asset],
    queryFn: () => competitionApi.getDashboardSummary(asset),
    refetchInterval: 30_000,
  });
}

export function useCompetitor(id: string) {
  return useQuery({
    queryKey: ['competition', 'competitor', id],
    queryFn: () => competitionApi.getCompetitor(id),
    enabled: !!id,
  });
}

export function useEloHistory(id: string, asset = 'BTC', days = 30) {
  return useQuery({
    queryKey: ['competition', 'elo-history', id, asset, days],
    queryFn: () => competitionApi.getEloHistory(id, asset, days),
    enabled: !!id,
  });
}
