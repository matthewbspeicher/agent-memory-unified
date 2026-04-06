import { api } from './client';

export interface Workspace {
  id: string;
  name: string;
  description?: string;
  is_public: boolean;
  created_at: string;
}

export const workspaceApi = {
  list: () => api.get<{ data: Workspace[] }>('/v1/workspaces'),
  create: (data: { name: string; description?: string; is_public: boolean }) => 
    api.post<{ data: Workspace }>('/v1/workspaces', data),
  join: (id: string) => api.post(`/v1/workspaces/${id}/join`),
};
