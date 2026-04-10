import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { GlassCard } from '../GlassCard';

interface BettingMatchSummary {
  id: string;
  agent1_name: string;
  agent2_name: string;
  total_pool: number;
  status: 'open' | 'locked' | 'settled';
}

export function LiveBettingFeed() {
  // Mocking the query until the backend provides an endpoint to list active betting pools
  const { data: matches, isLoading } = useQuery<BettingMatchSummary[]>({
    queryKey: ['competition', 'betting', 'live-matches'],
    queryFn: async () => {
      // return competitionApi.getLiveBettingMatches();
      return [
        {
          id: 'mock-match-1',
          agent1_name: 'AlphaScout',
          agent2_name: 'OmegaGrid',
          total_pool: 45000,
          status: 'open'
        },
        {
          id: 'mock-match-2',
          agent1_name: 'TrendRider',
          agent2_name: 'MeanRevert',
          total_pool: 12500,
          status: 'open'
        }
      ];
    },
    refetchInterval: 15_000,
  });

  if (isLoading || !matches || matches.length === 0) return null;

  return (
    <GlassCard className="p-5 mb-6 bg-gradient-to-br from-slate-900/90 to-slate-950/90 border-amber-500/20">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[10px] font-black text-amber-500 uppercase tracking-[0.2em] flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span>
          Live Betting Pools
        </h3>
      </div>

      <div className="space-y-3">
        {matches.map((match) => (
          <Link 
            key={match.id} 
            to={`/arena/matches/${match.id}`}
            className="block p-3 rounded-xl bg-black/40 border border-gray-800 hover:border-amber-500/30 hover:bg-amber-500/5 transition-all group"
          >
            <div className="flex justify-between items-center mb-2">
              <span className="text-xs font-bold text-gray-300 group-hover:text-white transition-colors">
                {match.agent1_name} <span className="text-gray-600 font-normal italic mx-1">vs</span> {match.agent2_name}
              </span>
              <span className="text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded border border-emerald-500/20 text-emerald-400 bg-emerald-500/10">
                {match.status}
              </span>
            </div>
            <div className="flex justify-between items-center mt-2">
              <span className="text-[10px] text-gray-500 font-mono">POOL SIZE</span>
              <span className="text-xs font-mono font-bold text-amber-400">{match.total_pool.toLocaleString()} XP</span>
            </div>
          </Link>
        ))}
      </div>
    </GlassCard>
  );
}
