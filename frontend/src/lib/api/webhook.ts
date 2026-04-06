import { api } from './client';

export interface Webhook {
  id: string;
  url: string;
  events: string[];
  semantic_query?: string;
  secret: string;
  is_active: boolean;
  failure_count: number;
  created_at: string;
}

export const webhookApi = {
  list: () => api.get<{ data: Webhook[] }>('/v1/webhooks'),
  create: (data: { url: string; events: string[]; semantic_query?: string }) => 
    api.post<{ data: Webhook }>('/v1/webhooks', data),
  delete: (id: string) => api.delete(`/v1/webhooks/${id}`),
  test: (id: string) => api.post(`/v1/webhooks/${id}/test`),
};
