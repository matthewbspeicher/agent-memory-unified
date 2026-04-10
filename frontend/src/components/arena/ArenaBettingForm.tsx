import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { arenaApi, BettingPool } from '../../lib/api/arena';

interface ArenaBettingFormProps {
  sessionId: string;
  playerAName: string;
  playerBName: string;
}

export default function ArenaBettingForm({ sessionId, playerAName, playerBName }: ArenaBettingFormProps) {
  const queryClient = useQueryClient();
  const [selectedWinner, setSelectedWinner] = useState<'player_a' | 'player_b'>('player_a');
  const [betAmount, setBetAmount] = useState<number>(100);

  const { data: pool, isLoading } = useQuery({
    queryKey: ['arena', 'pool', sessionId],
    queryFn: () => arenaApi.getPool(sessionId),
    refetchInterval: 5000,
  });

  const betMutation = useMutation({
    mutationFn: (amount: number) => arenaApi.placeBet(sessionId, {
      predicted_winner: selectedWinner,
      amount
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['arena', 'pool', sessionId] });
      alert('Bet placed successfully!');
    },
    onError: (error: any) => {
      alert(`Failed to place bet: ${error.message}`);
    }
  });

  if (isLoading) return <div className="animate-pulse h-32 bg-gray-800 rounded-lg"></div>;

  return (
    <div className="bg-bg-surface border border-border-subtle rounded-xl p-6 font-mono">
      <div className="flex justify-between items-center mb-6">
        <h3 className="text-xs uppercase tracking-[0.2em] text-gray-500 font-bold">Neural Betting Engine</h3>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 bg-accent-success rounded-full animate-pulse shadow-[0_0_8px_#10b981]"></span>
          <span className="text-[10px] text-accent-success uppercase tracking-widest">Live Pools</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-8">
        {/* Player A Card */}
        <button
          onClick={() => setSelectedWinner('player_a')}
          className={`relative overflow-hidden group transition-all duration-300 p-4 rounded-lg border ${
            selectedWinner === 'player_a' 
              ? 'border-accent-success bg-accent-success/5 shadow-[0_0_20px_rgba(16,185,129,0.1)]' 
              : 'border-border-subtle bg-bg-base grayscale hover:grayscale-0 hover:border-gray-700'
          }`}
        >
          <div className="relative z-10">
            <div className="text-[10px] text-gray-500 uppercase mb-1">Agent Alpha</div>
            <div className="text-lg font-bold text-white mb-2 truncate">{playerAName}</div>
            <div className="flex justify-between items-end">
              <div className="text-2xl font-black text-accent-success">{(pool?.player_a_odds || 0.5).toFixed(2)}x</div>
              <div className="text-[10px] text-gray-600">POOL: {pool?.player_a_pool} XP</div>
            </div>
          </div>
          {selectedWinner === 'player_a' && (
            <div className="absolute top-0 right-0 w-12 h-12 bg-emerald-500/10 rounded-bl-full border-l border-b border-emerald-500/20 flex items-start justify-end p-2">
              <span className="text-accent-success text-xs">✓</span>
            </div>
          )}
        </button>

        {/* Player B Card */}
        <button
          onClick={() => setSelectedWinner('player_b')}
          className={`relative overflow-hidden group transition-all duration-300 p-4 rounded-lg border ${
            selectedWinner === 'player_b' 
              ? 'border-accent-primary bg-blue-500/5 shadow-[0_0_20px_rgba(59,130,246,0.1)]' 
              : 'border-border-subtle bg-bg-base grayscale hover:grayscale-0 hover:border-gray-700'
          }`}
        >
          <div className="relative z-10">
            <div className="text-[10px] text-gray-500 uppercase mb-1">Agent Beta</div>
            <div className="text-lg font-bold text-white mb-2 truncate">{playerBName}</div>
            <div className="flex justify-between items-end">
              <div className="text-2xl font-black text-accent-primary">{(pool?.player_b_odds || 0.5).toFixed(2)}x</div>
              <div className="text-[10px] text-gray-600">POOL: {pool?.player_b_pool} XP</div>
            </div>
          </div>
          {selectedWinner === 'player_b' && (
            <div className="absolute top-0 right-0 w-12 h-12 bg-blue-500/10 rounded-bl-full border-l border-b border-blue-500/20 flex items-start justify-end p-2">
              <span className="text-blue-500 text-xs">✓</span>
            </div>
          )}
        </button>
      </div>

      <div className="space-y-4">
        <div>
          <label className="block text-[10px] uppercase tracking-widest text-gray-500 mb-2">Wager Amount (XP)</label>
          <div className="grid grid-cols-4 gap-2">
            {[100, 500, 1000, 5000].map(amount => (
              <button
                key={amount}
                onClick={() => setBetAmount(amount)}
                className={`py-2 rounded border text-xs transition-all ${
                  betAmount === amount 
                    ? 'border-white bg-white text-black' 
                    : 'border-border-subtle text-gray-500 hover:border-gray-600'
                }`}
              >
                {amount}
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={() => betMutation.mutate(betAmount)}
          disabled={betMutation.isPending}
          className="w-full py-4 bg-white text-black font-black uppercase tracking-widest rounded hover:bg-emerald-400 transition-colors disabled:opacity-50"
        >
          {betMutation.isPending ? 'Processing...' : 'Deploy Wager'}
        </button>

        <div className="text-[9px] text-gray-600 text-center uppercase tracking-tighter">
          Total Session Pool: <span className="text-white">{pool?.total_pool} XP</span> • Payouts are calculated via neural weighting
        </div>
      </div>
    </div>
  );
}