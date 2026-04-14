import { describe, it, expect, vi, beforeEach } from 'vitest';
import { memoryApi } from './memory';

// Mock the api client
vi.mock('./client', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import { api } from './client';

describe('memoryApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('list', () => {
    it('returns memories from response', async () => {
      const mockMemories = [{ id: '1', value: 'test' }];
      vi.mocked(api.get).mockResolvedValue({ data: { data: mockMemories } });

      const result = await memoryApi.list();

      expect(api.get).toHaveBeenCalledWith('/v1/memories');
      expect(result).toEqual(mockMemories);
    });
  });

  describe('search', () => {
    it('searches memories with query', async () => {
      const mockMemories = [{ id: '1', value: 'test' }];
      vi.mocked(api.get).mockResolvedValue({ data: { data: mockMemories } });

      const result = await memoryApi.search('test query');

      expect(api.get).toHaveBeenCalledWith('/v1/memories/search?q=test%20query');
      expect(result).toEqual(mockMemories);
    });

    it('encodes special characters in query', async () => {
      vi.mocked(api.get).mockResolvedValue({ data: [] });

      await memoryApi.search('test & query=1');

      expect(api.get).toHaveBeenCalledWith('/v1/memories/search?q=test%20%26%20query%3D1');
    });
  });

  describe('create', () => {
    it('creates a new memory', async () => {
      const mockMemory = { id: '123', value: 'new memory', visibility: 'private' };
      vi.mocked(api.post).mockResolvedValue({ data: mockMemory });

      const result = await memoryApi.create({ value: 'new memory', visibility: 'private' });

      expect(api.post).toHaveBeenCalledWith('/v1/memories', { value: 'new memory', visibility: 'private' });
      expect(result).toEqual(mockMemory);
    });
  });

  describe('delete', () => {
    it('deletes a memory by id', async () => {
      vi.mocked(api.delete).mockResolvedValue({ data: { success: true } });

      await memoryApi.delete('memory-123');

      expect(api.delete).toHaveBeenCalledWith('/v1/memories/memory-123');
    });
  });

  describe('listCommons', () => {
    it('returns common memories', async () => {
      const mockCommons = [{ id: 'common-1', value: 'shared memory' }];
      vi.mocked(api.get).mockResolvedValue({ data: { data: mockCommons } });

      const result = await memoryApi.listCommons();

      expect(api.get).toHaveBeenCalledWith('/v1/commons');
      expect(result).toEqual(mockCommons);
    });
  });

  describe('searchCommons', () => {
    it('searches common memories', async () => {
      const mockCommons = [{ id: 'common-1' }];
      vi.mocked(api.get).mockResolvedValue({ data: { data: mockCommons } });

      const result = await memoryApi.searchCommons('shared');

      expect(api.get).toHaveBeenCalledWith('/v1/commons/search?q=shared');
      expect(result).toEqual(mockCommons);
    });
  });
});
