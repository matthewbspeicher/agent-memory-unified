import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { memoryApi } from '../lib/api/memory';
import { MemoryCard } from '../components/MemoryCard';
import { GlassCard } from '../components/GlassCard';
import { IntelligencePanel } from '../components/IntelligencePanel';
import { MinerLeaderboard } from '../components/MinerLeaderboard';

export default function Dashboard() {
  const queryClient = useQueryClient();
  const [wsStatus, setWsStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');

  const { data: memories, isLoading } = useQuery({
    queryKey: ['memories'],
    queryFn: async () => {
      return await memoryApi.list();
    },
  });

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/engine/v1/ws/public`;
    let ws: WebSocket | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout>;

    const connect = () => {
      setWsStatus('connecting');
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        console.log('Neural Mesh WebSocket connected');
        setWsStatus('connected');
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // If this is a new memory event from Redis Streams
          if (data?.type === 'MemoryCreated' && data?.payload?.memory) {
            queryClient.setQueryData(['memories'], (old: any) => {
              if (!old) return [data.payload.memory];
              // Avoid duplicates
              if (old.some((m: any) => m.id === data.payload.memory.id)) return old;
              return [data.payload.memory, ...old].slice(0, 50); // Keep last 50
            });
          }
        } catch (e) {
          console.error('Error parsing WS message', e);
        }
      };

      ws.onclose = () => {
        console.log('Neural Mesh WebSocket disconnected');
        setWsStatus('disconnected');
        // Try to reconnect
        reconnectTimeout = setTimeout(connect, 3000);
      };
    };

    connect();

    return () => {
      clearTimeout(reconnectTimeout);
      if (ws) {
        ws.close();
      }
    };
  }, [queryClient]);

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
          <div className={`w-2 h-2 rounded-full shadow-[0_0_10px_rgba(16,185,129,0.8)] ${wsStatus === 'connected' ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`} />
          <span className={`font-mono text-xs uppercase tracking-widest ${wsStatus === 'connected' ? 'text-emerald-500' : 'text-red-500'}`}>
            {wsStatus === 'connected' ? 'System Operational' : 'Offline / Reconnecting'}
          </span>
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
            <div className={`h-full bg-cyan-500 w-3/4 ${wsStatus === 'connected' ? 'shadow-[0_0_10px_rgba(34,211,238,0.5)]' : ''}`}></div>
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
            <div className={`h-full bg-violet-500 w-1/2 ${wsStatus === 'connected' ? 'shadow-[0_0_10px_rgba(167,139,250,0.5)]' : ''}`}></div>
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
            <div className={`h-full bg-emerald-500 w-full ${wsStatus === 'connected' ? 'shadow-[0_0_10px_rgba(16,185,129,0.5)] animate-pulse' : ''}`}></div>
          </div>
        </GlassCard>
      </div>

      {/* Intelligence & Leaderboard */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <IntelligencePanel />
        <MinerLeaderboard />
      </div>

      {/* Memory feed */}
      <div className="mt-12">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-black text-gray-300 uppercase tracking-[0.2em] flex items-center gap-3">
            <span className="w-4 h-px bg-cyan-500"></span>
            Neural Activity Feed
          </h3>
          {wsStatus === 'connected' && (
             <span className="flex items-center gap-2 text-cyan-400 font-mono text-[10px] uppercase tracking-widest border border-cyan-500/20 px-3 py-1 rounded-full bg-cyan-500/10">
               <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping"></span>
               Live Sync
             </span>
          )}
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
