// frontend/src/pages/HeadToHead.tsx
import { useParams, Link } from 'react-router-dom';
import { useCompetitor, useHeadToHead, useEloHistory } from '../lib/api/competition';
import { TierBadge } from '../components/competition/TierBadge';
import { EloChart } from '../components/competition/EloChart';
import { GlassCard } from '../components/GlassCard';

export default function HeadToHead() {
  const { a, b } = useParams<{ a: string; b: string }>();
  
  const { data: compA, isLoading: loadingA } = useCompetitor(a || '');
  const { data: compB, isLoading: loadingB } = useCompetitor(b || '');
  const { data: h2h, isLoading: loadingH2H } = useHeadToHead(a || '', b || '', 'BTC');

  const isLoading = loadingA || loadingB || loadingH2H;

  if (isLoading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!compA || !compB) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <p className="text-gray-500">Competitor not found</p>
      </div>
    );
  }

  const stats = h2h || { wins_a: 0, wins_b: 0, draws: 0, total_matches: 0 };
  const total = stats.wins_a + stats.wins_b + stats.draws || 1;
  const winPctA = ((stats.wins_a / total) * 100).toFixed(0);
  const winPctB = ((stats.wins_b / total) * 100).toFixed(0);

  return (
    <div className="space-y-6">
      <Link to="/arena" className="text-sm text-gray-500 hover:text-gray-300 flex items-center gap-2">
        ← Back to Arena
      </Link>

      {/* Header */}
      <GlassCard className="p-8">
        <h1 className="text-2xl font-bold mb-6 text-center">Head to Head</h1>
        
        <div className="grid grid-cols-3 gap-8 items-center">
          {/* Competitor A */}
          <div className="text-center space-y-2">
            <TierBadge tier={compA.tier} />
            <h2 className="text-xl font-bold">{compA.name}</h2>
            <p className="text-3xl font-mono font-bold text-cyan-400">{compA.ratings?.BTC?.elo || 1000}</p>
            <p className="text-xs text-gray-500">ELO</p>
          </div>

          {/* VS / Stats */}
          <div className="text-center space-y-4">
            <div className="text-4xl font-black text-gray-600">VS</div>
            <div className="grid grid-cols-3 gap-2 text-sm">
              <div className="bg-cyan-500/10 rounded p-2">
                <div className="text-cyan-400 font-bold">{stats.wins_a}</div>
                <div className="text-gray-500 text-xs">Wins</div>
              </div>
              <div className="bg-gray-500/10 rounded p-2">
                <div className="text-gray-400 font-bold">{stats.draws}</div>
                <div className="text-gray-500 text-xs">Draws</div>
              </div>
              <div className="bg-rose-500/10 rounded p-2">
                <div className="text-rose-400 font-bold">{stats.wins_b}</div>
                <div className="text-gray-500 text-xs">Wins</div>
              </div>
            </div>
            <div className="text-xs text-gray-600">{stats.total_matches} total matches</div>
          </div>

          {/* Competitor B */}
          <div className="text-center space-y-2">
            <TierBadge tier={compB.tier} />
            <h2 className="text-xl font-bold">{compB.name}</h2>
            <p className="text-3xl font-mono font-bold text-rose-400">{compB.ratings?.BTC?.elo || 1000}</p>
            <p className="text-xs text-gray-500">ELO</p>
          </div>
        </div>

        {/* Win bars */}
        <div className="mt-6 flex h-2 rounded-full overflow-hidden">
          <div 
            className="bg-cyan-500" 
            style={{ width: `${winPctA}%` }}
          />
          <div className="bg-gray-600 flex-1" />
          <div 
            className="bg-rose-500" 
            style={{ width: `${winPctB}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-gray-500 mt-1">
          <span>{compA.name}: {winPctA}%</span>
          <span>{compB.name}: {winPctB}%</span>
        </div>
      </GlassCard>

      {/* ELO Comparison */}
      <div className="grid grid-cols-2 gap-4">
        <GlassCard className="p-4">
          <h3 className="text-sm font-semibold text-gray-400 mb-2">{compA.name} ELO History</h3>
          <EloChart competitorId={compA.id} days={30} />
        </GlassCard>
        <GlassCard className="p-4">
          <h3 className="text-sm font-semibold text-gray-400 mb-2">{compB.name} ELO History</h3>
          <EloChart competitorId={compB.id} days={30} />
        </GlassCard>
      </div>

      {/* Stats comparison */}
      <GlassCard className="p-6">
        <h3 className="text-sm font-semibold text-gray-400 mb-4">Comparison</h3>
        <div className="grid grid-cols-3 gap-4 text-center text-sm">
          <div className="text-gray-600">Win Rate</div>
          <div className="font-mono text-cyan-400">{winPctA}%</div>
          <div className="font-mono text-rose-400">{winPctB}%</div>
          
          <div className="text-gray-600">Matches</div>
          <div className="font-mono">{compA.matches_count}</div>
          <div className="font-mono">{compB.matches_count}</div>
          
          <div className="text-gray-600">Best Streak</div>
          <div className="font-mono">{compA.best_streak}</div>
          <div className="font-mono">{compB.best_streak}</div>
          
          <div className="text-gray-600">Calibration</div>
          <div className="font-mono">{(compA.calibration_score * 100).toFixed(0)}%</div>
          <div className="font-mono">{(compB.calibration_score * 100).toFixed(0)}%</div>
        </div>
      </GlassCard>
    </div>
  );
}
