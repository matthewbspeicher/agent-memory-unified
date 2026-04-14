import { describe, it, expect, vi, beforeEach } from 'vitest';
import { tradingApi } from './trading';

// Mock the api client
vi.mock('./client', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { api } from './client';

describe('tradingApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('listTrades', () => {
    it('returns trades from response data', async () => {
      const mockTrades = [{ id: '1', ticker: 'BTC' }];
      vi.mocked(api.get).mockResolvedValue({ data: { data: mockTrades } });

      const result = await tradingApi.listTrades();

      expect(api.get).toHaveBeenCalledWith('/v1/trades');
      expect(result).toEqual(mockTrades);
    });

    it('handles flat response format', async () => {
      const mockTrades = [{ id: '1' }];
      vi.mocked(api.get).mockResolvedValue({ data: mockTrades });

      const result = await tradingApi.listTrades();

      expect(result).toEqual(mockTrades);
    });
  });

  describe('openTrade', () => {
    it('posts trade data and returns result', async () => {
      const tradeData = { ticker: 'BTC', direction: 'long' as const, quantity: 1 };
      const mockTrade = { id: 'trade-123', ...tradeData };
      vi.mocked(api.post).mockResolvedValue({ data: mockTrade });

      const result = await tradingApi.openTrade(tradeData);

      expect(api.post).toHaveBeenCalledWith('/v1/trades', tradeData);
      expect(result).toEqual(mockTrade);
    });
  });

  describe('closeTrade', () => {
    it('posts close request with exit price', async () => {
      const mockTrade = { id: 'trade-123', status: 'closed' };
      vi.mocked(api.post).mockResolvedValue({ data: { data: mockTrade } });

      const result = await tradingApi.closeTrade('trade-123', '50000');

      expect(api.post).toHaveBeenCalledWith('/v1/trades/trade-123/close', { exit_price: '50000' });
      expect(result).toEqual(mockTrade);
    });
  });

  describe('getLeaderboard', () => {
    it('returns leaderboard entries', async () => {
      const mockEntries = [{ agent_id: 'agent1', agent_name: 'Test', total_trades: 10 }];
      vi.mocked(api.get).mockResolvedValue({ data: { data: mockEntries } });

      const result = await tradingApi.getLeaderboard();

      expect(api.get).toHaveBeenCalledWith('/v1/trading/leaderboard');
      expect(result).toEqual(mockEntries);
    });
  });
});
