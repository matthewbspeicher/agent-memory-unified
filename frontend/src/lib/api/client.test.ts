import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
    })),
  },
}));

describe('createApiClient', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('creates axios instance with baseURL', async () => {
    const { createApiClient } = await import('./factory');
    createApiClient('/api');

    expect(axios.create).toHaveBeenCalledWith({ baseURL: '/api' });
  });

  it('adds Authorization header when token exists', async () => {
    localStorage.setItem('auth_token', 'test-token');

    const { createApiClient } = await import('./factory');
    const client = createApiClient('/api');

    // Verify request interceptor was registered
    expect(client.interceptors.request.use).toHaveBeenCalled();
  });

  it('creates client with engine baseURL', async () => {
    const { createApiClient } = await import('./factory');
    createApiClient('/engine');

    expect(axios.create).toHaveBeenCalledWith({ baseURL: '/engine' });
  });
});
