import { createApiClient } from './factory';

/**
 * API client with single baseURL.
 * Vite proxy routes /api → localhost:8080 (FastAPI trading engine)
 */
export const api = createApiClient('/api');
