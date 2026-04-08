// frontend/src/lib/api/competition.ts
import axios from 'axios';
import { useQuery } from '@tanstack/react-query';

/**
 * Trading API client for Competition endpoints.
 * Uses /engine/v1 prefix for FastAPI trading engine.
 */
const getBaseUrl = () => {
  if (import.meta.env.DEV) {
    return '/engine/v1';
  }
  return import.meta.env.VITE_TRADING_API_URL 
    ? `${import.meta.env.VITE_TRADING_API_URL}/engine/v1`
    : 'http://localhost:8080/engine/v1';
};

const tradingApi = axios.create({
  baseURL: getBaseUrl(),
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
  calibration_score: number;
}

export interface HeadToHeadResponse {
  competitor_a: Record<string, unknown>;
  competitor_b: Record<string, unknown>;
  wins_a: number;
  wins_b: number;
  draws: number;
  total_matches: number;
}

// ── API Functions ──

export const competitionApi = {
  getDashboardSummary: (asset = 'BTC') =>
    tradingApi.get<DashboardSummary>('/dashboard/summary', { params: { asset } })
      .then(res => res.data),

  getLeaderboard: (params: { asset?: string; type?: string; limit?: number; offset?: number } = {}) =>
    tradingApi.get<LeaderboardResponse>('/leaderboard', { params })
      .then(res => res.data),

  getCompetitor: (id: string) =>
    tradingApi.get<CompetitorDetail>(`/competitors/${id}`)
      .then(res => res.data),

  getEloHistory: (id: string, asset = 'BTC', days = 30) =>
    tradingApi.get<{ competitor_id: string; asset: string; history: EloHistoryPoint[] }>(
      `/competitors/${id}/elo-history`,
      { params: { asset, days } },
    ).then(res => res.data),

  getHeadToHead: (a: string, b: string, asset = 'BTC') =>
    tradingApi.get<HeadToHeadResponse>(`/head-to-head/${a}/${b}`, { params: { asset } })
      .then(res => res.data),
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

export function useHeadToHead(a: string, b: string, asset = 'BTC') {
  return useQuery({
    queryKey: ['competition', 'h2h', a, b, asset],
    queryFn: () => competitionApi.getHeadToHead(a, b, asset),
    enabled: !!a && !!b,
  });
}

export function useMetaLearnerStatus() {
  return useQuery({
    queryKey: ['competition', 'meta-learner'],
    queryFn: () => tradingApi.get('/meta-learner/status').then(res => res.data),
    refetchInterval: 60_000,
  });
}
