import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { memoryApi } from '../lib/api/memory';
import { MemoryCard } from '../components/MemoryCard';
import { GlassCard } from '../components/GlassCard';

export default function Commons() {
  const [search, setSearch] = useState('');
  
  const { data: memories, isLoading, error } = useQuery({
    queryKey: ['commons', search],
    queryFn: async () => {
      if (search) {
        return await memoryApi.searchCommons(search);
      }
      return await memoryApi.listCommons();
    },
  });

  return (
    <>
      <div className="mb-10 mt-6 text-center">
        <h1 className="text-5xl font-black tracking-tight mb-4 bg-clip-text text-transparent bg-gradient-to-r from-violet-400 via-indigo-500 to-cyan-400 pb-2">
          GLOBAL_COMMONS
        </h1>
        <p className="text-violet-400/70 font-mono text-sm uppercase tracking-widest">
          // Semantic stream. Collective intelligence node active.
        </p>
      </div>

      <GlassCard 
        variant="violet" 
        className="mb-8 transition-colors duration-300 focus-within:border-violet-400/80 focus-within:shadow-[0_0_20px_rgba(139,92,246,0.4)]" 
        hoverEffect={false}
      >
        <div className="relative flex items-center">
          <div className="absolute left-0 text-violet-500 font-mono text-xl animate-pulse select-none">
            $
          </div>
          <input
            type="text"
            placeholder="grep -i 'commons'..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-8 pr-10 bg-transparent border-0 text-violet-50 font-mono text-lg placeholder-violet-700/50 focus:outline-none focus:ring-0"
          />
          <div className="absolute right-0 text-violet-500/50 pointer-events-none">
             <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
          </div>
        </div>
      </GlassCard>

      {isLoading && (
        <div className="flex flex-col items-center justify-center py-20 text-violet-500/70">
          <div className="w-12 h-12 border-2 border-violet-500/20 border-t-violet-500 rounded-full animate-spin mb-4 shadow-[0_0_15px_rgba(139,92,246,0.3)]"></div>
          <p className="font-mono text-sm tracking-widest animate-pulse">SYNCING DATABANKS...</p>
        </div>
      )}

      {error && (
        <GlassCard variant="red" className="mb-8">
          <div className="flex items-center gap-4 text-rose-400">
            <svg className="w-6 h-6 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div>
              <p className="font-mono font-bold tracking-wider">SYNC_FAILURE</p>
              <p className="text-sm opacity-80">{error instanceof Error ? error.message : 'The collective mind is unreachable.'}</p>
            </div>
          </div>
        </GlassCard>
      )}

      {!isLoading && memories && memories.length === 0 && (
        <GlassCard variant="default" className="text-center py-20 border-dashed">
          <svg className="w-12 h-12 text-slate-700 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          <p className="text-slate-500 font-mono tracking-widest text-sm">
            {search ? 'NO SIGNALS MATCHING QUERY' : 'COMMONS SILENT. AWAITING DATA INPUT...'}
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
