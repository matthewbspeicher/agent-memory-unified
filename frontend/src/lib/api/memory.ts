import { api } from './client';

export interface Memory {
  id: string;
  agent_id: string;
  value: string;
  visibility: 'private' | 'public';
  created_at: string;
}

export const memoryApi = {
  list: () => api.get<{ data: Memory[] }>('/v1/memories'),

  search: (q: string) =>
    api.get<{ data: Memory[] }>(`/v1/memories/search?q=${encodeURIComponent(q)}`),

  create: (data: { value: string; visibility: 'private' | 'public' }) =>
    api.post<Memory>('/v1/memories', data),

  delete: (id: string) => api.delete(`/v1/memories/${id}`),
};
