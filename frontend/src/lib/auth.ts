import { useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { agentApi } from './api/agent';

export interface User {
  id: string;
  email?: string;
  name: string;
}

export function useAuth() {
  const queryClient = useQueryClient();

  const { data: user, isLoading, isError } = useQuery<User | null>({
    queryKey: ['auth', 'me'],
    queryFn: async () => {
      const token = localStorage.getItem('auth_token');
      if (!token) return null;
      
      try {
        const agent = await agentApi.getMe();
        return agent as unknown as User;
      } catch (err) {
        localStorage.removeItem('auth_token');
        return null;
      }
    },
    retry: false,
  });

  const login = useCallback(
    async (token: string) => {
      localStorage.setItem('auth_token', token);
      await queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
    },
    [queryClient]
  );

  const logout = useCallback(() => {
    localStorage.removeItem('auth_token');
    queryClient.setQueryData(['auth', 'me'], null);
  }, [queryClient]);

  const isAuthenticated = !!user && !isError;

  return {
    user: user ?? null,
    isLoading,
    isAuthenticated,
    login,
    logout,
  };
}
