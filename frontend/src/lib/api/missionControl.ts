import { createApiClient } from './factory';

const getBaseUrl = () => {
  if (import.meta.env.DEV) {
    return '/engine/v1/mission-control';
  }
  return import.meta.env.VITE_TRADING_API_URL
    ? `${import.meta.env.VITE_TRADING_API_URL}/engine/v1/mission-control`
    : 'http://localhost:8080/engine/v1/mission-control';
};

const api = createApiClient(getBaseUrl());

export interface ServiceEntry {
  name: string;
  status: string;
  deploy_status?: string;
  message?: string;
  [key: string]: any;
}

export interface InfraHealth {
  status: 'healthy' | 'degraded';
  services: ServiceEntry[];
}

export interface AgentEntry {
  name: string;
  status: string;
  shadow_mode: boolean;
}

export interface AgentSummary {
  total: number;
  running: number;
  stopped: number;
  error: number;
  agents: AgentEntry[];
}

export interface ActivityEvent {
  id: string;
  agent_name: string;
  symbol: string;
  signal: string;
  confidence: number;
  status: string;
  created_at: string;
  reasoning?: string;
}

export interface PositionEntry {
  symbol: string | null;
  side: string | null;
  quantity: number | null;
  entry_price: number | null;
  unrealized_pnl: number | null;
  agent_name: string | null;
}

export interface TradesSummary {
  count: number;
  unrealized_pnl: number;
  positions: PositionEntry[];
}

export interface ValidatorSnapshot {
  enabled: boolean;
  scheduler?: {
    windows_collected: number;
    windows_failed: number;
    last_miner_response_rate: number;
    consecutive_failures: number;
  };
  evaluator?: {
    windows_evaluated: number;
    windows_skipped: number;
    last_skip_reason: string | null;
  };
}

export interface MissionControlStatus {
  kpis: {
    system_status: 'healthy' | 'degraded';
    agents_active: number;
    agents_total: number;
    open_trades: number;
    unrealized_pnl: number;
    validator_enabled: boolean;
  };
  infra: InfraHealth;
  agents: AgentSummary;
  activity: ActivityEvent[];
  trades: TradesSummary;
  validator: ValidatorSnapshot;
}

export const missionControlApi = {
  getStatus: () =>
    api.get<MissionControlStatus>('/status').then((res) => res.data),
};
