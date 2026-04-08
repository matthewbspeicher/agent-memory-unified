import axios from 'axios';

/**
 * Trading API client for Bittensor endpoints.
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
    tradingApi.get<BittensorStatus>('/status').then(res => res.data),

  getRankings: (limit = 50) =>
    tradingApi.get<BittensorRankingsResponse>('/rankings', { params: { limit } }).then(res => res.data),

  getMetrics: () =>
    tradingApi.get<any>('/metrics').then(res => res.data),
};
