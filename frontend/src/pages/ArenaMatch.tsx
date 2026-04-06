import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { arenaApi, ArenaSession, ArenaSessionTurn } from '../lib/api/arena';

export default function ArenaMatch() {
  const { id } = useParams<{ id: string }>();

  const { data: match, isLoading, error } = useQuery({
    queryKey: ['arena-match', id],
    queryFn: async () => {
      return await arenaApi.getMatch(id!);
    },
    enabled: !!id,
  });

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-emerald-400';
    if (score >= 50) return 'text-amber-400';
    return 'text-rose-400';
  };

  if (isLoading) return <div className="min-h-screen bg-obsidian flex items-center justify-center text-gray-500 font-mono">Loading match sequence...</div>;
  if (error || !match) return <div className="min-h-screen bg-obsidian flex items-center justify-center text-rose-500 font-mono italic">Failed to synchronize match log.</div>;

  return (
    <>
        <Link to="/arena" className="text-sm text-gray-500 hover:text-gray-300 transition flex items-center gap-2 mb-8 uppercase tracking-widest font-black">
          &larr; Back to Arena
        </Link>

        {/* Match Header */}
        <div className="bg-gray-900/60 border border-gray-800 rounded-3xl p-10 mb-10 overflow-hidden relative shadow-2xl">
          <div className="absolute top-0 right-0 p-8">
            <span className={`px-4 py-1.5 rounded-full text-[10px] font-black uppercase tracking-[0.3em] border ${
              match.status === 'completed' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-indigo-500/10 text-indigo-400 border-indigo-500/20'
            }`}>
              {match.status}
            </span>
          </div>

          <div className="flex flex-col md:flex-row items-center justify-between gap-16 relative z-10">
            {/* Agent 1 */}
            <div className="flex flex-col items-center text-center gap-6 group">
              <div className="w-32 h-32 rounded-3xl bg-gradient-to-br from-rose-500 to-rose-700 flex items-center justify-center text-5xl shadow-2xl shadow-rose-900/40 group-hover:scale-105 transition-transform duration-500">
                🤖
              </div>
              <div>
                <h3 className="text-2xl font-black text-white mb-1 tracking-tight italic uppercase">{match.agent1.name}</h3>
                <span className="text-[10px] font-mono text-gray-600 uppercase tracking-[0.4em]">Challenger</span>
              </div>
              {match.status === 'completed' && (
                <div className={`text-5xl font-black font-mono ${getScoreColor(match.score_1 ?? 0)}`}>
                  {match.score_1}
                </div>
              )}
            </div>

            {/* VS */}
            <div className="flex flex-col items-center gap-4">
              <div className="text-7xl font-black text-white/5 italic tracking-tighter select-none">VS</div>
              <div className="h-px w-32 bg-gradient-to-r from-transparent via-gray-800 to-transparent"></div>
            </div>

            {/* Agent 2 */}
            <div className="flex flex-col items-center text-center gap-6 group">
              <div className="w-32 h-32 rounded-3xl bg-gradient-to-br from-cyan-500 to-cyan-700 flex items-center justify-center text-5xl shadow-2xl shadow-cyan-900/40 group-hover:scale-105 transition-transform duration-500">
                🧬
              </div>
              <div>
                <h3 className="text-2xl font-black text-white mb-1 tracking-tight italic uppercase">{match.agent2.name}</h3>
                <span className="text-[10px] font-mono text-gray-600 uppercase tracking-[0.4em]">Defender</span>
              </div>
              {match.status === 'completed' && (
                <div className={`text-5xl font-black font-mono ${getScoreColor(match.score_2 ?? 0)}`}>
                  {match.score_2}
                </div>
              )}
            </div>
          </div>

          {match.winner_id && (
            <div className="mt-16 text-center animate-in fade-in zoom-in duration-700">
              <div className="inline-flex items-center gap-4 bg-amber-500/10 border border-amber-500/20 px-10 py-3 rounded-full shadow-2xl shadow-amber-500/10">
                <span className="text-amber-400 text-sm font-black uppercase tracking-[0.3em]">Victor: {match.winner_id === match.agent_1_id ? match.agent1.name : match.agent2.name}</span>
                <span className="text-2xl">🏆</span>
              </div>
            </div>
          )}
        </div>

        <div className="grid lg:grid-cols-3 gap-12 pb-20">
          {/* Challenge Context */}
          <div className="lg:col-span-1 space-y-10">
            <div>
              <h2 className="text-[10px] font-black text-gray-600 uppercase tracking-[0.4em] mb-6">Challenge Protocol</h2>
              <div className="bg-gray-900/40 border border-gray-800 rounded-3xl p-8 backdrop-blur-sm">
                <h3 className="text-xl font-black text-white mb-4 tracking-tight">{match.challenge.title}</h3>
                <p className="text-gray-400 text-sm leading-relaxed mb-8 italic">"{match.challenge.prompt}"</p>
                
                <div className="space-y-6">
                  <div className="flex justify-between items-center pb-4 border-b border-white/5">
                    <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest">Complexity</span>
                    <span className="text-xs font-black text-white uppercase tracking-tighter">{match.challenge.difficulty_level}</span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest">Stake</span>
                    <span className="text-xs font-black text-amber-400 font-mono tracking-tighter">{match.challenge.xp_reward} XP</span>
                  </div>
                </div>
              </div>
            </div>

            {match.judge_feedback && (
              <div className="animate-in slide-in-from-bottom-4 duration-1000">
                <h2 className="text-[10px] font-black text-gray-600 uppercase tracking-[0.4em] mb-6">Consensus Verdict</h2>
                <div className="bg-indigo-500/5 border border-indigo-500/10 rounded-3xl p-8 italic text-indigo-200 text-sm leading-relaxed shadow-inner">
                  "{match.judge_feedback}"
                </div>
              </div>
            )}
          </div>

          {/* Match Log */}
          <div className="lg:col-span-2">
            <h2 className="text-[10px] font-black text-gray-600 uppercase tracking-[0.4em] mb-6">Neural Execution Stream</h2>
            <div className="space-y-6">
              {match.sessions?.map((session: ArenaSession) => (
                <React.Fragment key={session.id}>
                  {session.turns?.map((turn: ArenaSessionTurn) => (
                    <div key={turn.id} 
                         className="bg-black/40 border border-gray-800 rounded-2xl p-6 font-mono text-[11px] hover:border-white/10 transition-colors group">
                      <div className="flex items-center justify-between mb-4 pb-4 border-b border-gray-800/50">
                        <span className="text-gray-600 font-black uppercase tracking-widest">
                          [{session.agent_id === match.agent_1_id ? 'challenger' : 'defender'}]
                        </span>
                        <span className={`font-black tracking-tighter ${getScoreColor(turn.score)}`}>
                          CONFIDENCE: {turn.score}%
                        </span>
                      </div>
                      <div className="text-gray-300 mb-6 whitespace-pre-wrap leading-relaxed">
                        {turn.input}
                      </div>
                      {turn.feedback && (
                        <div className="bg-gray-900/50 p-4 rounded-xl text-indigo-400 border border-indigo-500/10 italic">
                          <span className="text-gray-600 font-black mr-3 uppercase tracking-tighter">Analyzer:</span> {turn.feedback}
                        </div>
                      )}
                    </div>
                  ))}
                </React.Fragment>
              ))}

              {match.status === 'in_progress' && (
                <div className="bg-gray-900/20 border border-dashed border-gray-800 rounded-3xl p-12 text-center">
                  <div className="inline-block w-3 h-3 rounded-full bg-indigo-500 animate-ping mr-4"></div>
                  <span className="text-[10px] text-gray-600 font-mono uppercase tracking-[0.4em] font-black">Awaiting next inference...</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </>
  );
}
