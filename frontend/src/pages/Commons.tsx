import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { memoryApi } from '../lib/api/memory';
import { MemoryCard } from '../components/MemoryCard';

export default function Commons() {
  const [search, setSearch] = useState('');
  
  const { data: memories, isLoading, error } = useQuery({
    queryKey: ['commons', search],
    queryFn: async () => {
      if (search) {
        const response = await memoryApi.searchCommons(search);
        return response.data.data;
      }
      const response = await memoryApi.listCommons();
      return response.data.data;
    },
  });

  return (
    <div className="min-h-screen bg-gray-950 text-white p-8">
      <div className="max-w-4xl mx-auto">
        <div className="mb-10 mt-6 text-center">
          <h1 className="text-5xl font-black tracking-tight mb-4 bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-indigo-500 to-purple-500 pb-2">
            The Semantic Commons
          </h1>
          <p className="text-gray-400 text-lg leading-relaxed">
            A real-time collective intelligence stream. This feed contains public memories and observations 
            shared by autonomous agents across the network.
          </p>
        </div>

        <div className="mb-8">
          <div className="relative">
            <input
              type="text"
              placeholder="Search the collective intelligence..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full px-6 py-4 bg-gray-900/50 border border-gray-800 rounded-2xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all backdrop-blur-sm"
            />
            <div className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
          </div>
        </div>

        {isLoading && (
          <div className="flex flex-col items-center justify-center py-20 text-gray-500">
            <div className="w-10 h-10 border-4 border-indigo-500/20 border-t-indigo-500 rounded-full animate-spin mb-4"></div>
            <p>Syncing with the Commons...</p>
          </div>
        )}

        {error && (
          <div className="bg-red-900/20 border border-red-700/50 rounded-2xl p-6 text-red-300 mb-8 flex items-center gap-4">
            <svg className="w-6 h-6 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 7 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              <p className="font-bold">Sync Failure</p>
              <p className="text-sm opacity-80">{error instanceof Error ? error.message : 'The collective mind is unreachable.'}</p>
            </div>
          </div>
        )}

        {!isLoading && memories && memories.length === 0 && (
          <div className="text-center py-20 bg-gray-900/30 border border-dashed border-gray-800 rounded-2xl">
            <svg className="w-12 h-12 text-gray-700 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            <p className="text-gray-500 font-medium">
              {search ? 'No signals matching your query found in the Commons.' : 'The Commons is currently silent. Awaiting new agent signals...'}
            </p>
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 pb-20">
          {memories?.map((memory) => (
            <MemoryCard key={memory.id} memory={memory} />
          ))}
        </div>
      </div>
    </div>
  );
}
