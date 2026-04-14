import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the factory to return a mock api
const mockGet = vi.fn();
vi.mock('./factory', () => ({
  createApiClient: vi.fn(() => ({
    get: mockGet,
  })),
}));

// Import after mock
const { missionControlApi } = await import('./missionControl');

describe('missionControlApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getStatus', () => {
    it('returns mission control status', async () => {
      const mockStatus = {
        kpis: {
          system_status: 'healthy',
          agents_active: 5,
          agents_total: 10,
          open_trades: 3,
          unrealized_pnl: 1000,
          validator_enabled: true,
        },
        infra: { status: 'healthy', services: [] },
        agents: { total: 10, running: 5, stopped: 3, error: 2, agents: [] },
        activity: [],
        trades: { count: 5, unrealized_pnl: 1000, positions: [] },
        validator: { enabled: true },
      };
      mockGet.mockResolvedValue({ data: mockStatus });

      const result = await missionControlApi.getStatus();

      expect(mockGet).toHaveBeenCalledWith('/status');
      expect(result).toEqual(mockStatus);
    });
  });
});
