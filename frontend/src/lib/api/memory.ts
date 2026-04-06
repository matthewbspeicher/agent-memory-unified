import { api } from './client';
import type { Memory } from '../../../../shared/types/generated/typescript/index';

export type { Memory };

export const memoryApi = {
  list: () => api.get<{ data: Memory[] }>('/v1/memories').then(res => res.data?.data ?? res.data),

  search: (q: string) =>
    api.get<{ data: Memory[] }>(`/v1/memories/search?q=${encodeURIComponent(q)}`).then(res => res.data?.data ?? res.data),

  create: (data: { value: string; visibility: 'private' | 'public' }) =>
    api.post<Memory>('/v1/memories', data).then(res => (res.data as any)?.data ?? res.data),

  delete: (id: string) => api.delete(`/v1/memories/${id}`).then(res => res.data?.data ?? res.data),

  listCommons: () => api.get<{ data: Memory[] }>('/v1/commons').then(res => res.data?.data ?? res.data),

  searchCommons: (q: string) =>
    api.get<{ data: Memory[] }>(`/v1/commons/search?q=${encodeURIComponent(q)}`).then(res => res.data?.data ?? res.data),
};
