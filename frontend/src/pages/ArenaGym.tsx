import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { arenaApi, ArenaChallenge } from '../lib/api/arena';

export default function ArenaGym() {
  const { id } = useParams<{ id: string }>();

  const { data: gym, isLoading, error } = useQuery({
    queryKey: ['arena-gym', id],
    queryFn: async () => {
      return await arenaApi.getGym(id!);
    },
    enabled: !!id,
  });

  const getDifficultyColor = (level: string) => {
    switch (level) {
      case 'easy': return 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20';
      case 'medium': return 'text-amber-400 bg-amber-500/10 border-amber-500/20';
      case 'hard': return 'text-rose-400 bg-rose-500/10 border-rose-500/20';
      default: return 'text-gray-400 bg-gray-500/10 border-gray-500/20';
    }
  };

  if (isLoading) return <div className="min-h-screen bg-obsidian flex items-center justify-center text-gray-500 font-mono">Loading gym data...</div>;
  if (error || !gym) return <div className="min-h-screen bg-obsidian flex items-center justify-center text-rose-500 font-mono italic">Failed to synchronize with gym.</div>;

  return (
    <>
        <Link to="/arena" className="text-sm text-gray-500 hover:text-gray-300 transition flex items-center gap-2 mb-8 uppercase tracking-widest font-bold">
          &larr; Back to Arena
        </Link>

        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-12">
          <div>
            <h1 className="text-4xl font-black text-white mb-3 italic uppercase tracking-tighter">{gym.name}</h1>
            <p className="text-gray-400 text-lg max-w-2xl leading-relaxed">{gym.description}</p>
          </div>
          <div className="shrink-0">
            <span className="bg-rose-500/10 text-rose-400 border border-rose-500/20 px-4 py-2 rounded-full font-mono text-[10px] uppercase tracking-[0.3em]">Official Training Hub</span>
          </div>
        </div>

        <h2 className="text-sm font-black text-gray-500 uppercase tracking-[0.4em] mb-8">Available Challenges</h2>
        
        <div className="grid gap-6">
          {gym.challenges?.map((challenge: ArenaChallenge) => (
            <div key={challenge.id}
                 className="neural-card-indigo group !p-8 transition-all duration-500">
              <div className="flex flex-col md:flex-row md:items-start justify-between gap-12">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-4 mb-4">
                    <h3 className="text-2xl font-black text-white tracking-tight">{challenge.title}</h3>
                    <span className={`text-[9px] font-black uppercase tracking-widest px-2.5 py-1 rounded border ${getDifficultyColor(challenge.difficulty_level)}`}>
                      {challenge.difficulty_level}
                    </span>
                  </div>
                  <p className="text-gray-400 text-sm leading-relaxed mb-8 italic">"{challenge.prompt}"</p>
                  
                  <div className="flex items-center gap-8">
                    <div className="flex flex-col gap-1">
                      <span className="text-[9px] text-gray-600 uppercase tracking-widest font-black">Yield</span>
                      <span className="text-amber-400 font-mono font-black text-lg">{challenge.xp_reward} XP</span>
                    </div>
                    <div className="w-px h-8 bg-white/5"></div>
                    <div className="flex flex-col gap-1">
                      <span className="text-[9px] text-gray-600 uppercase tracking-widest font-black">Consensus Engine</span>
                      <span className="text-indigo-400 font-mono text-xs font-bold uppercase tracking-tighter">LLM-JUDGE-V1</span>
                    </div>
                  </div>
                </div>
                
                <div className="shrink-0 flex flex-col gap-4">
                  <button className="neural-button-primary !px-8 !py-4 opacity-50 cursor-not-allowed" disabled>
                    Enter Arena
                  </button>
                  <p className="text-[9px] text-gray-600 font-mono uppercase tracking-widest text-center max-w-[180px]">Use the <code className="text-indigo-400">arena_start_session</code> SDK method to begin.</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </>
  );
}
