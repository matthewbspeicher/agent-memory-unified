import { useQuery } from '@tanstack/react-query';
import { bittensorApi } from '../lib/api/bittensor';
import { GlassCard } from './GlassCard';

export function MinerLeaderboard() {
  const { data, isLoading } = useQuery({
    queryKey: ['bittensor-rankings'],
    queryFn: () => bittensorApi.getRankings(5),
    refetchInterval: 30000, // slower refresh for rankings
  });

  if (isLoading) return <div className="animate-pulse h-64 bg-white/5 rounded-xl" />;

  const rankings = data?.rankings || [];

  return (
    <GlassCard variant="cyan" className="h-full">
      <h3 className="text-sm font-bold text-cyan-400 uppercase tracking-widest flex items-center gap-2 mb-6">
        <span className="w-2 h-2 rounded-full bg-cyan-500 animate-pulse" />
        Miner Alpha Leaderboard
      </h3>

      <div className="space-y-4">
        {rankings.length === 0 && (
          <p className="text-gray-500 font-mono text-[10px] uppercase text-center py-8">No ranking data available</p>
        )}
        {rankings.map((miner, idx) => (
          <div key={miner.uid} className="flex items-center justify-between group border-b border-white/5 pb-3 last:border-0 last:pb-0">
            <div className="flex items-center gap-3">
              <span className="text-lg font-black text-white/20 font-mono w-4">{idx + 1}</span>
              <div className="flex flex-col">
                <span className="text-xs font-bold text-white group-hover:text-cyan-400 transition-colors cursor-default">
                  {miner.hotkey?.slice(0, 8)}...{miner.hotkey?.slice(-4)}
                </span>
                <span className="text-[10px] text-gray-500 font-mono uppercase">UID: {miner.uid}</span>
              </div>
            </div>
            <div className="text-right">
              <div className="text-sm font-bold text-white font-mono">{(miner.score || 0).toFixed(4)}</div>
              <div className="text-[9px] text-cyan-500 uppercase font-mono tracking-tighter">HYBRID ALPHA</div>
            </div>
          </div>
        ))}
      </div>
    </GlassCard>
  );
}
