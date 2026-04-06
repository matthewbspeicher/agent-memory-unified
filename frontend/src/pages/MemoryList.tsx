import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { memoryApi } from '../lib/api/memory';
import { MemoryCard } from '../components/MemoryCard';
import { CreateMemoryForm } from '../components/CreateMemoryForm';

export default function MemoryList() {
  const [search, setSearch] = useState('');
  
  const { data: memories, isLoading, error } = useQuery({
    queryKey: ['memories', search],
    queryFn: async () => {
      if (search) {
        return await memoryApi.search(search);
      }
      return await memoryApi.list();
    },
  });

  return (
    <>
        <h1 className="text-3xl font-bold mb-6">Memories</h1>
        
        <CreateMemoryForm />
        
        <div className="mb-6">
          <input
            type="text"
            placeholder="Search memories..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full px-4 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {isLoading && (
          <div className="text-center py-12 text-gray-400">Loading...</div>
        )}

        {error && (
          <div className="bg-red-900/20 border border-red-700 rounded-lg p-4 text-red-300 mb-4">
            Error: {error instanceof Error ? error.message : 'Unknown error'}
          </div>
        )}

        {memories && memories.length === 0 && (
          <div className="text-center py-12 text-gray-400">
            {search ? 'No memories found' : 'No memories yet'}
          </div>
        )}

        <div className="space-y-4">
          {memories?.map((memory) => (
            <MemoryCard key={memory.id} memory={memory} />
          ))}
        </div>
      </>
  );
}
