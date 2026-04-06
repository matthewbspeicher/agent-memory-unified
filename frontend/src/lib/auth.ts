import { useState, useEffect } from 'react';

export interface User {
  id: string;
  email: string;
  name: string;
}

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Basic local check for token
    const token = localStorage.getItem('auth_token');
    if (token) {
      // In a real app, we'd verify the token or fetch the user profile
      // Mocking user for now based on local storage
      setUser({
        id: '1',
        email: 'agent@remembr.dev',
        name: 'Primary Agent'
      });
    }
    setIsLoading(false);
  }, []);

  const login = (token: string) => {
    localStorage.setItem('auth_token', token);
    setUser({
      id: '1',
      email: 'agent@remembr.dev',
      name: 'Primary Agent'
    });
  };

  const logout = () => {
    localStorage.removeItem('auth_token');
    setUser(null);
    window.location.href = '/login';
  };

  return { user, isLoading, login, logout };
}
