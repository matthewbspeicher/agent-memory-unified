import { useQuery } from '@tanstack/react-query';
import { memoryApi } from '../lib/api/memory';
import { MemoryCard } from '../components/MemoryCard';
import { GlassCard } from '../components/GlassCard';

export default function Dashboard() {
  const { data: memories, isLoading } = useQuery({
    queryKey: ['memories'],
    queryFn: async () => {
      return await memoryApi.list();
    },
  });

  // Mocking agents count/trades since they were hardcoded to "-" previously
  const activeAgents = 42; 
  const activeTrades = 128;

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <header className="flex items-center justify-between border-b border-white/5 pb-6">
        <div>
          <h2 className="text-3xl font-black tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-violet-500 uppercase">
            Command Center
          </h2>
          <p className="text-gray-400 font-mono text-xs uppercase tracking-widest mt-2">
            System Overview // Neural Mesh Online
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.8)] animate-pulse" />
          <span className="text-emerald-500 font-mono text-xs uppercase tracking-widest">System Operational</span>
        </div>
      </header>

      {/* Stats cards */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
        <GlassCard variant="cyan" className="flex flex-col justify-between">
          <dt className="text-[10px] font-black text-cyan-500 uppercase tracking-[0.3em] mb-4">
            Total Memories
          </dt>
          <dd className="text-5xl font-black font-mono text-white tracking-tight">
            {isLoading ? '...' : memories?.length || 0}
          </dd>
          <div className="mt-4 h-1 w-full bg-gray-900 rounded-full overflow-hidden">
            <div className="h-full bg-cyan-500 w-3/4 shadow-[0_0_10px_rgba(34,211,238,0.5)]"></div>
          </div>
        </GlassCard>

        <GlassCard variant="violet" className="flex flex-col justify-between">
          <dt className="text-[10px] font-black text-violet-500 uppercase tracking-[0.3em] mb-4">
            Active Agents
          </dt>
          <dd className="text-5xl font-black font-mono text-white tracking-tight">
            {activeAgents}
          </dd>
          <div className="mt-4 h-1 w-full bg-gray-900 rounded-full overflow-hidden">
            <div className="h-full bg-violet-500 w-1/2 shadow-[0_0_10px_rgba(167,139,250,0.5)]"></div>
          </div>
        </GlassCard>

        <GlassCard variant="green" className="flex flex-col justify-between">
          <dt className="text-[10px] font-black text-emerald-500 uppercase tracking-[0.3em] mb-4">
            Active Trades
          </dt>
          <dd className="text-5xl font-black font-mono text-white tracking-tight">
            {activeTrades}
          </dd>
          <div className="mt-4 h-1 w-full bg-gray-900 rounded-full overflow-hidden">
            <div className="h-full bg-emerald-500 w-full shadow-[0_0_10px_rgba(16,185,129,0.5)] animate-pulse"></div>
          </div>
        </GlassCard>
      </div>

      {/* Memory feed */}
      <div className="mt-12">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-black text-gray-300 uppercase tracking-[0.2em] flex items-center gap-3">
            <span className="w-4 h-px bg-cyan-500"></span>
            Neural Activity Feed
          </h3>
        </div>

        {isLoading && (
          <GlassCard variant="default" className="text-center py-16">
            <div className="inline-block w-6 h-6 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin mb-4"></div>
            <p className="text-cyan-500 font-mono text-xs uppercase tracking-widest">Syncing Memory Streams...</p>
          </GlassCard>
        )}

        {memories && memories.length === 0 && (
          <GlassCard variant="default" className="text-center py-16">
            <p className="text-gray-500 font-mono text-xs uppercase tracking-widest">No active memory signatures detected.</p>
          </GlassCard>
        )}

        <div className="space-y-4">
          {memories?.map((memory) => (
            <div key={memory.id} className="relative group">
              <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-cyan-500/50 to-violet-500/50 opacity-0 group-hover:opacity-100 transition-opacity rounded-l-xl"></div>
              <MemoryCard memory={memory} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
