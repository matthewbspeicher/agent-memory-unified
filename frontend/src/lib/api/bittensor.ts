import axios from 'axios';
import { api } from './client';

/**
 * Trading API client for Bittensor endpoints.
 * In dev mode, Vite proxies /api/bittensor → trading service (port 8080).
 * X-API-Key is read from VITE_TRADING_API_KEY env or defaults to local dev key.
 */
const tradingApi = axios.create({
  baseURL: '/api',
  headers: {
    'X-API-Key': import.meta.env.VITE_TRADING_API_KEY || (import.meta.env.DEV ? 'local-validator-dev' : ''),
  },
});

export interface BittensorStatus {
  enabled?: boolean;
  healthy?: boolean;
  network?: string;
  syncing?: boolean | number;
  block_height?: number;
  wallet?: {
    coldkey?: string;
    hotkey?: string;
    stake?: number | string;
    balance?: number | string;
  };
  subnet?: {
    id?: string;
    emissions?: number | string;
    dividends?: number | string;
    vtrust?: number | string;
  };
  miners?: {
    top_miners?: any[];
  };
  [key: string]: any;
}

export interface MinerRanking {
  uid: number | string;
  hotkey?: string;
  score?: number;
  [key: string]: any;
}

export interface BittensorRankingsResponse {
  rankings: MinerRanking[];
}

export const bittensorApi = {
  getStatus: () =>
    tradingApi.get<BittensorStatus>('/bittensor/status').then(res => res.data),

  getRankings: (limit = 50) =>
    tradingApi.get<BittensorRankingsResponse>('/bittensor/rankings', { params: { limit } }).then(res => res.data),

  getMetrics: () =>
    tradingApi.get<any>('/bittensor/metrics').then(res => res.data),
};
