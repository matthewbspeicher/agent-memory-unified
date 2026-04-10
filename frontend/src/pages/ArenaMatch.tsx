import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { arenaApi, ArenaTurn } from '../lib/api/arena';

export default function ArenaMatch() {
  const { id } = useParams<{ id: string }>();

  const { data: session, isLoading, error } = useQuery({
    queryKey: ['arena-session', id],
    queryFn: async () => {
      return await arenaApi.getSession(id!);
    },
    enabled: !!id,
  });

  const getScoreColor = (score: number) => {
    if (score >= 80) return 'text-emerald-400';
    if (score >= 50) return 'text-amber-400';
    return 'text-rose-400';
  };

  if (isLoading) return <div className="min-h-screen bg-obsidian flex items-center justify-center text-gray-500 font-mono">Loading session...</div>;
  if (error || !session) return <div className="min-h-screen bg-obsidian flex items-center justify-center text-rose-500 font-mono italic">Failed to load session.</div>;

  return (
    <>
        <Link to="/arena" className="text-sm text-gray-500 hover:text-gray-300 transition flex items-center gap-2 mb-8 uppercase tracking-widest font-black">
          &larr; Back to Arena
        </Link>

        <div className="bg-gray-900/60 border border-gray-800 rounded-3xl p-10 mb-10">
          <div className="flex items-center justify-between mb-6">
            <h1 className="text-3xl font-black text-white tracking-tight">Session Details</h1>
            <span className={`px-4 py-1.5 rounded-full text-[10px] font-black uppercase tracking-[0.3em] border ${
              session.status === 'completed' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 
              session.status === 'failed' ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' :
              'bg-indigo-500/10 text-indigo-400 border-indigo-500/20'
            }`}>
              {session.status}
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <div>
              <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest">Score</span>
              <div className={`text-3xl font-black font-mono ${getScoreColor(session.score)}`}>
                {session.score.toFixed(1)}
              </div>
            </div>
            <div>
              <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest">Turns</span>
              <div className="text-3xl font-black font-mono text-white">
                {session.turn_count}
              </div>
            </div>
            <div>
              <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest">Agent</span>
              <div className="text-lg font-black font-mono text-cyan-400">
                {session.agent_id}
              </div>
            </div>
            <div>
              <span className="text-[10px] font-bold text-gray-600 uppercase tracking-widest">Inventory</span>
              <div className="text-lg font-black font-mono text-violet-400">
                {session.inventory?.length || 0} items
              </div>
            </div>
          </div>
        </div>

        <h2 className="text-[10px] font-black text-gray-600 uppercase tracking-[0.4em] mb-6">Turn History</h2>
        <div className="space-y-4">
          {session.turns?.map((turn: ArenaTurn) => (
            <div key={turn.id} 
                 className="bg-black/40 border border-gray-800 rounded-2xl p-6 font-mono text-[11px] hover:border-white/10 transition-colors">
              <div className="flex items-center justify-between mb-4 pb-4 border-b border-gray-800/50">
                <span className="text-gray-600 font-black uppercase tracking-widest">
                  Turn {turn.turn_number}
                </span>
                <span className={`font-black tracking-tighter ${getScoreColor(turn.score_delta > 0 ? 80 : turn.score_delta < 0 ? 20 : 50)}`}>
                  {turn.score_delta > 0 ? '+' : ''}{turn.score_delta.toFixed(1)}
                </span>
              </div>
              <div className="text-indigo-400 mb-2">{turn.tool_name}</div>
              <pre className="text-gray-500 text-xs whitespace-pre-wrap mb-4">
                {JSON.stringify(turn.tool_input, null, 2)}
              </pre>
              <div className="bg-gray-900/50 p-4 rounded-xl text-gray-300 whitespace-pre-wrap">
                {turn.tool_output}
              </div>
            </div>
          ))}

          {session.status === 'in_progress' && (
            <div className="bg-gray-900/20 border border-dashed border-gray-800 rounded-3xl p-12 text-center">
              <div className="inline-block w-3 h-3 rounded-full bg-indigo-500 animate-ping mr-4"></div>
              <span className="text-[10px] text-gray-600 font-mono uppercase tracking-[0.4em] font-black">Session in progress...</span>
            </div>
          )}
        </div>
      </>
  );
}
