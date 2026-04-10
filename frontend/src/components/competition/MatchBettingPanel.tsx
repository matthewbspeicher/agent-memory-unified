import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { GlassCard } from '../GlassCard';
import { useBettingPool, bettingApi } from '../../lib/api/competition';

export function MatchBettingPanel({
  matchId,
  agent1Id,
  agent2Id,
  agent1Name,
  agent2Name,
  matchStatus
}: {
  matchId: string;
  agent1Id: string;
  agent2Id: string;
  agent1Name: string;
  agent2Name: string;
  matchStatus: string;
}) {
  const [betAmount, setBetAmount] = useState(100);
  const { data: pool, refetch } = useBettingPool(matchId);

  const betMutation = useMutation({
    mutationFn: async ({ competitorId, amount }: { competitorId: string; amount: number }) => {
      return bettingApi.placeBet(matchId, {
        predicted_winner: competitorId,
        amount,
      });
    },
    onSuccess: () => {
      refetch();
    }
  });

  if (!pool) {
    return (
      <GlassCard className="p-6 bg-gradient-to-br from-slate-900/90 to-slate-950/90 border-cyan-500/20">
        <div className="text-center text-gray-500">Loading pool...</div>
      </GlassCard>
    );
  }

  const isCompleted = matchStatus === 'completed' || pool.status === 'settled';
  const oddsA = pool.competitor_a_odds * 100;
  const oddsB = pool.competitor_b_odds * 100;

  return (
    <GlassCard className="p-6 bg-gradient-to-br from-slate-900/90 to-slate-950/90 border-cyan-500/20">
      <div className="flex items-center justify-between mb-6">
        <h3 className="text-sm font-black text-cyan-400 uppercase tracking-widest">Arena Betting Pool</h3>
        <div className="text-xs font-mono text-gray-400 border border-gray-700 px-2 py-1 rounded">
          POOL: {pool.total_pool.toLocaleString()} XP
        </div>
      </div>

      <div className="relative h-4 bg-gray-800 rounded-full overflow-hidden mb-6 flex">
        <div
          className="h-full bg-rose-500 transition-all duration-1000"
          style={{ width: `${oddsA.toFixed(1)}%` }}
        />
        <div
          className="h-full bg-cyan-500 transition-all duration-1000"
          style={{ width: `${oddsB.toFixed(1)}%` }}
        />
      </div>

      <div className="flex justify-between text-xs font-mono text-gray-400 mb-8 px-1">
        <div className="flex flex-col">
          <span className="text-rose-400">{agent1Name}</span>
          <span>{oddsA.toFixed(0)}% implied ({pool.competitor_a_bettors} bettors)</span>
        </div>
        <div className="flex flex-col text-right">
          <span className="text-cyan-400">{agent2Name}</span>
          <span>{oddsB.toFixed(0)}% implied ({pool.competitor_b_bettors} bettors)</span>
        </div>
      </div>

      {!isCompleted ? (
        <div className="space-y-4 border-t border-gray-800 pt-6">
          <div className="flex justify-between items-center text-sm">
            <span className="text-gray-400 uppercase tracking-wider text-xs font-bold">Wager Amount</span>
            <div className="flex items-center gap-2">
              <button onClick={() => setBetAmount(Math.max(10, betAmount - 100))} className="w-8 h-8 rounded bg-gray-800 hover:bg-gray-700 text-white">-</button>
              <input 
                type="number" 
                value={betAmount}
                onChange={(e) => setBetAmount(Number(e.target.value))}
                className="w-24 text-center bg-black/50 border border-gray-700 rounded py-1 text-amber-400 font-mono font-bold"
              />
              <button onClick={() => setBetAmount(betAmount + 100)} className="w-8 h-8 rounded bg-gray-800 hover:bg-gray-700 text-white">+</button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <button
              onClick={() => betMutation.mutate({ competitorId: agent1Id, amount: betAmount })}
              disabled={betMutation.isPending}
              className="py-3 px-4 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-400 font-black uppercase tracking-wider text-xs transition-colors disabled:opacity-50"
            >
              {betMutation.isPending ? 'Betting...' : `Bet ${agent1Name}`}
            </button>
            <button
              onClick={() => betMutation.mutate({ competitorId: agent2Id, amount: betAmount })}
              disabled={betMutation.isPending}
              className="py-3 px-4 rounded-xl bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 text-cyan-400 font-black uppercase tracking-wider text-xs transition-colors disabled:opacity-50"
            >
              {betMutation.isPending ? 'Betting...' : `Bet ${agent2Name}`}
            </button>
          </div>
        </div>
      ) : (
        <div className="text-center py-4 border-t border-gray-800 mt-6">
          <span className="text-emerald-400 font-black uppercase tracking-[0.2em] text-xs">Betting Closed - Payouts Settled</span>
        </div>
      )}
    </GlassCard>
  );
}
