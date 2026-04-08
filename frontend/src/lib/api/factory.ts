import axios, { AxiosInstance } from 'axios';

export function createApiClient(baseURL: string): AxiosInstance {
  const client = axios.create({ baseURL });

  client.interceptors.request.use((config) => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // Also add X-API-Key if available for engine routes
    const apiKey = import.meta.env.VITE_TRADING_API_KEY || (import.meta.env.DEV ? 'local-validator-dev' : '');
    if (apiKey && baseURL.includes('/engine')) {
        config.headers['X-API-Key'] = apiKey;
    }
    return config;
  });

  client.interceptors.response.use(
    (response) => response,
    (error) => {
      if (error.response?.status === 401) {
        localStorage.removeItem('auth_token');
        window.dispatchEvent(new Event('unauthorized'));
      }
      return Promise.reject(error);
    }
  );

  return client;
}
