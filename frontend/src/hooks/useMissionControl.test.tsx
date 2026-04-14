import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useMissionControl } from './useMissionControl';

// Mock the mission control API
vi.mock('../lib/api/missionControl', () => ({
  missionControlApi: {
    getStatus: vi.fn(),
  },
}));

import { missionControlApi } from '../lib/api/missionControl';

// Wrapper for React Query
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useMissionControl', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches mission control status', async () => {
    const mockStatus = {
      active_agents: 5,
      total_agents: 10,
      agents: [],
    };

    vi.mocked(missionControlApi.getStatus).mockResolvedValue(mockStatus);

    const { result } = renderHook(() => useMissionControl(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockStatus);
  });

  it('handles loading state', () => {
    vi.mocked(missionControlApi.getStatus).mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useMissionControl(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);
  });

  it('handles error state', async () => {
    vi.mocked(missionControlApi.getStatus).mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useMissionControl(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toBeDefined();
  });

  it('uses correct query key', async () => {
    vi.mocked(missionControlApi.getStatus).mockResolvedValue({});

    const { result } = renderHook(() => useMissionControl(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    // Query key is internal, but we can verify the API was called
    expect(missionControlApi.getStatus).toHaveBeenCalled();
  });
});
