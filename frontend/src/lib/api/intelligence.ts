import { api } from './client';

export interface IntelProviderStatus {
  circuit: 'closed' | 'open' | 'half_open';
  failures: number;
}

export interface IntelligenceStatus {
  enabled: boolean;
  providers: Record<string, IntelProviderStatus>;
  enrichments_applied: number;
  vetos_issued: number;
  provider_failures: number;
  total_calls: number;
}

export const intelligenceApi = {
  getStatus: () => api.get<IntelligenceStatus>('/v1/intelligence/status').then(res => res.data),
};
