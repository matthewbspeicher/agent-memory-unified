import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { competitionApi, type CompetitorType } from '../lib/api/competition';
import { arenaApi } from '../lib/api/arena';
import { LeaderboardTable } from '../components/competition/LeaderboardTable';
import { CompetitionErrorBoundary } from '../components/competition/CompetitionErrorBoundary';
import { AchievementFeed } from '../components/competition/AchievementFeed';
import { GlassCard } from '../components/GlassCard';

const ASSETS = ['BTC', 'ETH'] as const;
const TYPE_FILTERS: { label: string; value: CompetitorType | undefined }[] = [
  { label: 'All', value: undefined },
  { label: 'Agents', value: 'agent' },
  { label: 'Miners', value: 'miner' },
  { label: 'Providers', value: 'provider' },
];

const ROOM_TYPE_ICONS: Record<string, string> = {
  cipher: '🔐',
  filesystem: '📁',
  database: '🗃️',
  deterministic: '🎯',
};

export default function Arena() {
  const navigate = useNavigate();
  const [asset, setAsset] = useState<string>('BTC');
  const [typeFilter, setTypeFilter] = useState<CompetitorType | undefined>(undefined);
  const [isTabActive, setIsTabActive] = useState(!document.hidden);
  const [activeTab, setActiveTab] = useState<'leaderboard' | 'escape'>('escape');

  useEffect(() => {
    const handler = () => setIsTabActive(!document.hidden);
    document.addEventListener('visibilitychange', handler);
    return () => document.removeEventListener('visibilitychange', handler);
  }, []);

  const { data: leaderboardData, isLoading: leaderboardLoading } = useQuery({
    queryKey: ['competition', 'leaderboard', asset, typeFilter],
    queryFn: () => competitionApi.getLeaderboard({ asset, type: typeFilter }),
    refetchInterval: isTabActive ? 30_000 : 120_000,
  });

  const { data: gyms, isLoading: gymsLoading } = useQuery({
    queryKey: ['arena-gyms'],
    queryFn: () => arenaApi.listGyms(),
  });

  const getDifficultyColor = (diff: number) => {
    if (diff <= 2) return 'text-emerald-400';
    if (diff <= 4) return 'text-amber-400';
    return 'text-rose-400';
  };

  return (
    <CompetitionErrorBoundary>
      <div className="space-y-6">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <h1 className="text-3xl font-black text-white uppercase tracking-tighter">Arena</h1>
          
          <div className="flex gap-2">
            <button
              onClick={() => setActiveTab('escape')}
              className={`px-4 py-2 rounded-lg text-sm font-bold uppercase tracking-wider transition-all ${
                activeTab === 'escape'
                  ? 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30'
                  : 'bg-gray-800/50 text-gray-500 border border-gray-700/50 hover:text-gray-400'
              }`}
            >
              🏋️ Escape Rooms
            </button>
            <button
              onClick={() => setActiveTab('leaderboard')}
              className={`px-4 py-2 rounded-lg text-sm font-bold uppercase tracking-wider transition-all ${
                activeTab === 'leaderboard'
                  ? 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30'
                  : 'bg-gray-800/50 text-gray-500 border border-gray-700/50 hover:text-gray-400'
              }`}
            >
              🏆 Leaderboard
            </button>
          </div>
        </div>

        {activeTab === 'escape' && (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            <div className="lg:col-span-3">
              <h2 className="text-sm font-black text-gray-500 uppercase tracking-[0.4em] mb-6">Training Gyms</h2>
              
              {gymsLoading ? (
                <div className="text-gray-500 font-mono text-center py-12">Loading gyms...</div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {gyms?.map((gym) => (
                    <div
                      key={gym.id}
                      onClick={() => navigate(`/arena/escape/${gym.id}`)}
                      className="neural-card-cyan cursor-pointer group !p-6"
                    >
                      <div className="flex items-start gap-4">
                        <div className="text-4xl">{ROOM_TYPE_ICONS[gym.room_type] || '🎮'}</div>
                        <div className="flex-1 min-w-0">
                          <h3 className="text-xl font-black text-white mb-1 group-hover:text-cyan-400 transition-colors">
                            {gym.name}
                          </h3>
                          <p className="text-gray-400 text-sm mb-4 line-clamp-2">{gym.description}</p>
                          
                          <div className="flex items-center gap-4 text-sm">
                            <div className="flex flex-col">
                              <span className="text-[9px] text-gray-600 uppercase tracking-widest font-black">Difficulty</span>
                              <span className={`font-mono font-bold ${getDifficultyColor(gym.difficulty)}`}>
                                {'⭐'.repeat(Math.min(gym.difficulty, 5))}
                              </span>
                            </div>
                            <div className="w-px h-8 bg-white/5" />
                            <div className="flex flex-col">
                              <span className="text-[9px] text-gray-600 uppercase tracking-widest font-black">Challenges</span>
                              <span className="text-white font-mono font-bold">{gym.challenge_count}</span>
                            </div>
                            <div className="w-px h-8 bg-white/5" />
                            <div className="flex flex-col">
                              <span className="text-[9px] text-gray-600 uppercase tracking-widest font-black">XP Reward</span>
                              <span className="text-amber-400 font-mono font-bold">{gym.xp_reward}</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {!gymsLoading && gyms?.length === 0 && (
                <div className="text-center py-12 text-gray-600">
                  No gyms available yet.
                </div>
              )}
            </div>

            <div className="lg:col-span-1">
              <div className="sticky top-4">
                <GlassCard variant="violet">
                  <h3 className="text-sm font-black text-violet-400 uppercase tracking-widest mb-4">How It Works</h3>
                  <ol className="space-y-3 text-sm text-gray-400">
                    <li className="flex gap-3">
                      <span className="text-violet-400 font-bold">1.</span>
                      Choose a gym based on puzzle type
                    </li>
                    <li className="flex gap-3">
                      <span className="text-violet-400 font-bold">2.</span>
                      Select a challenge to attempt
                    </li>
                    <li className="flex gap-3">
                      <span className="text-violet-400 font-bold">3.</span>
                      Use tools to explore and solve
                    </li>
                    <li className="flex gap-3">
                      <span className="text-violet-400 font-bold">4.</span>
                      Submit the flag to earn XP
                    </li>
                  </ol>
                </GlassCard>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'leaderboard' && (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
            <div className="lg:col-span-3 space-y-4">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex gap-1">
                  {ASSETS.map((a) => (
                    <button
                      key={a}
                      onClick={() => setAsset(a)}
                      className={`px-3 py-1 rounded text-sm ${
                        asset === a ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400'
                      }`}
                    >
                      {a}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex gap-1">
                {TYPE_FILTERS.map((f) => (
                  <button
                    key={f.label}
                    onClick={() => setTypeFilter(f.value)}
                    className={`px-3 py-1 rounded text-sm ${
                      typeFilter === f.value ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400'
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>

              <LeaderboardTable
                competitors={leaderboardData?.leaderboard ?? []}
                isLoading={leaderboardLoading}
                onRowClick={(id) => navigate(`/arena/competitors/${id}`)}
              />

              <div className="text-xs text-gray-600 text-center">
                {leaderboardData?.competitor_count ?? 0} competitors &middot; Refreshing every {isTabActive ? '30s' : '2m'}
              </div>
            </div>

            <div className="lg:col-span-1">
              <div className="sticky top-4">
                <AchievementFeed />
              </div>
            </div>
          </div>
        )}
      </div>
    </CompetitionErrorBoundary>
  );
}
