import { api } from './client';

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
    api.get<BittensorStatus>('/bittensor/status').then(res => res.data),
  
  getRankings: (limit = 50) => 
    api.get<BittensorRankingsResponse>('/bittensor/rankings', { params: { limit } }).then(res => res.data),
    
  getMetrics: () => 
    api.get<any>('/bittensor/metrics').then(res => res.data),
};
