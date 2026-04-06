import { useCallback, useEffect, useState } from 'react';
import { api } from './api/client';

export interface User {
  id: string;
  email?: string;
  name: string;
}

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    user: null,
    isLoading: true,
    isAuthenticated: false,
  });

  useEffect(() => {
    const token = localStorage.getItem('auth_token');
    if (!token) {
      setState({ user: null, isLoading: false, isAuthenticated: false });
      return;
    }

    api.get('/v1/agents/me')
      .then((res) => {
        setState({
          user: res.data,
          isLoading: false,
          isAuthenticated: true,
        });
      })
      .catch(() => {
        localStorage.removeItem('auth_token');
        setState({ user: null, isLoading: false, isAuthenticated: false });
      });
  }, []);

  const login = useCallback((token: string) => {
    localStorage.setItem('auth_token', token);
    setState((prev) => ({ ...prev, isLoading: true }));
    api.get('/v1/agents/me')
      .then((res) => {
        setState({ user: res.data, isLoading: false, isAuthenticated: true });
      })
      .catch(() => {
        localStorage.removeItem('auth_token');
        setState({ user: null, isLoading: false, isAuthenticated: false });
      });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('auth_token');
    setState({ user: null, isLoading: false, isAuthenticated: false });
  }, []);

  return {
    user: state.user,
    isLoading: state.isLoading,
    isAuthenticated: state.isAuthenticated,
    login,
    logout,
  };
}
