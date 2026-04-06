import { api } from './client';
import type { Memory } from '../../../../shared/types/generated/typescript/index';

export type { Memory };

export const memoryApi = {
  list: () => api.get<{ data: Memory[] }>('/v1/memories'),

  search: (q: string) =>
    api.get<{ data: Memory[] }>(`/v1/memories/search?q=${encodeURIComponent(q)}`),

  create: (data: { value: string; visibility: 'private' | 'public' }) =>
    api.post<Memory>('/v1/memories', data),

  delete: (id: string) => api.delete(`/v1/memories/${id}`),

  listCommons: () => api.get<{ data: Memory[] }>('/v1/commons'),

  searchCommons: (q: string) =>
    api.get<{ data: Memory[] }>(`/v1/commons/search?q=${encodeURIComponent(q)}`),
};
