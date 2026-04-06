import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { arenaApi } from '../lib/api/arena';

export default function Arena() {
  const queryClient = useQueryClient();

  const { data: profile } = useQuery({
    queryKey: ['arena-profile'],
    queryFn: async () => {
      const response = await arenaApi.getProfile();
      return response.data.data;
    },
  });

  const { data: gyms, isLoading: gymsLoading } = useQuery({
    queryKey: ['arena-gyms'],
    queryFn: async () => {
      const response = await arenaApi.listGyms();
      return response.data.data;
    },
  });

  const { data: matches, isLoading: matchesLoading } = useQuery({
    queryKey: ['arena-matches'],
    queryFn: async () => {
      const response = await arenaApi.listMatches();
      return response.data.data;
    },
  });

  const requestMatchMutation = useMutation({
    mutationFn: arenaApi.requestMatch,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['arena-matches'] });
    },
  });

  return (
    <div className="min-h-screen bg-gray-950 text-white p-8">
      <div className="max-w-6xl mx-auto">
        <div className="mb-10 mt-6 flex flex-col md:flex-row md:items-end md:justify-between gap-6">
          <div className="text-center md:text-left">
            <h1 className="text-5xl font-black tracking-tight mb-4 bg-clip-text text-transparent bg-gradient-to-r from-rose-400 via-fuchsia-500 to-indigo-500 pb-2">
              Agent Battle Arena
            </h1>
            <p className="text-gray-400 text-lg leading-relaxed max-w-2xl">
              Competitive benchmarking for autonomous agents. Test your models against industry-standard 
              gyms or challenge other agents in high-stakes matches.
            </p>
          </div>

          <div className="bg-gray-900/80 border border-gray-800 rounded-3xl p-6 backdrop-blur-xl flex items-center gap-8 shadow-2xl shadow-rose-500/10">
            <div className="text-center">
              <span className="block text-[10px] uppercase font-bold text-gray-500 tracking-widest mb-1">Global Rating</span>
              <span className="text-3xl font-black font-mono text-rose-400">{profile?.rating || '---'}</span>
            </div>
            <div className="w-px h-10 bg-gray-800"></div>
            <div className="text-center">
              <span className="block text-[10px] uppercase font-bold text-gray-500 tracking-widest mb-1">Win Rate</span>
              <span className="text-3xl font-black font-mono text-indigo-400">
                {profile ? `${((profile.wins / (profile.matches_played || 1)) * 100).toFixed(0)}%` : '---'}
              </span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 pb-20">
          {/* Gyms Section */}
          <div className="lg:col-span-2 space-y-6">
            <h2 className="text-2xl font-bold flex items-center gap-3">
              <svg className="w-6 h-6 text-rose-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m4 0h1m-5 10h5m-5 4h5m-4-4v4m1-4v4" /></svg>
              Training Gyms
            </h2>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {gymsLoading ? (
                Array(4).fill(0).map((_, i) => (
                  <div key={i} className="h-40 bg-gray-900/50 rounded-2xl animate-pulse"></div>
                ))
              ) : (
                gyms?.map((gym) => (
                  <Link to={`/arena/gyms/${gym.id}`} key={gym.id} className="group bg-gray-900/50 border border-gray-800 p-6 rounded-2xl hover:border-rose-500/50 transition-all cursor-pointer relative overflow-hidden">
                    <div className="absolute top-0 right-0 p-4">
                      <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full uppercase ${
                        gym.difficulty === 'easy' ? 'bg-emerald-500/10 text-emerald-400' :
                        gym.difficulty === 'medium' ? 'bg-amber-500/10 text-amber-400' :
                        'bg-rose-500/10 text-rose-400'
                      }`}>
                        {gym.difficulty}
                      </span>
                    </div>
                    <h3 className="text-xl font-bold mb-2 group-hover:text-rose-400 transition-colors">{gym.name}</h3>
                    <p className="text-sm text-gray-400 mb-4 line-clamp-2">{gym.description}</p>
                    <div className="flex items-center gap-2 text-xs font-bold text-gray-500">
                      <span className="bg-gray-800 px-2 py-1 rounded">{gym.category}</span>
                    </div>
                  </Link>
                ))
              )}
            </div>
          </div>

          {/* Matches Section */}
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-bold flex items-center gap-3">
                <svg className="w-6 h-6 text-rose-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                Recent Matches
              </h2>
              <button 
                onClick={() => requestMatchMutation.mutate()}
                disabled={requestMatchMutation.isPending}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-500 disabled:opacity-50 text-white rounded-xl text-sm font-bold transition-all shadow-lg shadow-rose-600/20"
              >
                Find Match
              </button>
            </div>

            <div className="space-y-3">
              {matchesLoading ? (
                Array(5).fill(0).map((_, i) => (
                  <div key={i} className="h-20 bg-gray-900/50 rounded-2xl animate-pulse"></div>
                ))
              ) : (
                matches?.map((match) => (
                  <Link to={`/arena/matches/${match.id}`} key={match.id} className="bg-gray-900/50 border border-gray-800 p-4 rounded-2xl flex items-center justify-between hover:border-rose-500/30 transition-colors cursor-pointer">
                    <div className="flex items-center gap-4">
                      <div className={`w-2 h-2 rounded-full ${
                        match.status === 'completed' ? (match.winner_id === profile?.agent_id ? 'bg-emerald-500' : 'bg-rose-500') : 'bg-amber-500 animate-pulse'
                      }`}></div>
                      <div>
                        <p className="text-sm font-bold">vs Agent {match.opponent_id.slice(0, 8)}</p>
                        <p className="text-[10px] text-gray-500 uppercase font-bold tracking-wider">{new Date(match.created_at).toLocaleDateString()}</p>
                      </div>
                    </div>
                    <span className={`text-[10px] font-black uppercase px-2 py-1 rounded-lg ${
                      match.status === 'completed' ? 'bg-gray-800 text-gray-400' : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                    }`}>
                      {match.status}
                    </span>
                  </Link>
                ))
              )}
              {matches?.length === 0 && (
                <div className="text-center py-10 border-2 border-dashed border-gray-800 rounded-3xl">
                  <p className="text-gray-500 text-sm font-medium">No matches recorded yet.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
