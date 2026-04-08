import { createApiClient } from './factory';

/**
 * API client with single baseURL.
 * Vite proxy routes /api → localhost:8000 (Laravel)
 */
export const api = createApiClient('/api');
