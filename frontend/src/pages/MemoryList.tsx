import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { memoryApi } from '../lib/api/memory';
import { MemoryCard } from '../components/MemoryCard';
import { CreateMemoryForm } from '../components/CreateMemoryForm';
import { GlassCard } from '../components/GlassCard';

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
      <div className="mb-8">
        <h1 className="text-4xl font-black tracking-tighter mb-2 bg-clip-text text-transparent bg-gradient-to-r from-cyan-400 via-blue-500 to-violet-500">
          WORKSPACE_MEMORIES
        </h1>
        <p className="text-cyan-500/70 font-mono text-sm uppercase tracking-widest">
          // Private Datastore _
        </p>
      </div>

      <div className="mb-8">
        <CreateMemoryForm />
      </div>

      <GlassCard 
        variant="cyan" 
        className="mb-8 transition-colors duration-300 focus-within:border-cyan-400/80 focus-within:shadow-[0_0_20px_rgba(34,211,238,0.4)]" 
        hoverEffect={false}
      >
        <div className="relative flex items-center">
          <div className="absolute left-0 text-cyan-500 font-mono text-xl animate-pulse select-none">
            &gt;
          </div>
          <input
            type="text"
            placeholder="Query memory fragments..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-8 bg-transparent border-0 text-cyan-50 font-mono text-lg placeholder-cyan-700/50 focus:outline-none focus:ring-0"
          />
        </div>
      </GlassCard>

      {isLoading && (
        <div className="flex flex-col items-center justify-center py-20 text-cyan-500/70">
          <div className="w-12 h-12 border-2 border-cyan-500/20 border-t-cyan-500 rounded-full animate-spin mb-4 shadow-[0_0_15px_rgba(34,211,238,0.3)]"></div>
          <p className="font-mono text-sm tracking-widest animate-pulse">SCANNING NETWORK...</p>
        </div>
      )}

      {error && (
        <GlassCard variant="red" className="mb-8">
          <div className="flex items-center gap-4 text-rose-400">
            <svg className="w-6 h-6 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div>
              <p className="font-mono font-bold tracking-wider">SYSTEM_FAULT</p>
              <p className="text-sm opacity-80">{error instanceof Error ? error.message : 'Unknown error during datastore access.'}</p>
            </div>
          </div>
        </GlassCard>
      )}

      {!isLoading && memories && memories.length === 0 && (
        <GlassCard variant="default" className="text-center py-20 border-dashed">
          <svg className="w-12 h-12 text-slate-700 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 002-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
          </svg>
          <p className="text-slate-500 font-mono tracking-widest text-sm">
            {search ? 'NO DATA FRAGMENTS FOUND' : 'WORKSPACE EMPTY. READY FOR INGESTION.'}
          </p>
        </GlassCard>
      )}

      <div className="grid grid-cols-1 gap-4 pb-20">
        {memories?.map((memory) => (
          <MemoryCard key={memory.id} memory={memory} />
        ))}
      </div>
    </>
  );
}
