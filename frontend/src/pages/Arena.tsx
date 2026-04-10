// frontend/src/pages/Arena.tsx
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { competitionApi, type CompetitorType } from '../lib/api/competition';
import { LeaderboardTable } from '../components/competition/LeaderboardTable';
import { CompetitionErrorBoundary } from '../components/competition/CompetitionErrorBoundary';
import { AchievementFeed } from '../components/competition/AchievementFeed';
import { LiveBettingFeed } from '../components/competition/LiveBettingFeed';

const ASSETS = ['BTC', 'ETH'] as const;
const TYPE_FILTERS: { label: string; value: CompetitorType | undefined }[] = [
  { label: 'All', value: undefined },
  { label: 'Agents', value: 'agent' },
  { label: 'Miners', value: 'miner' },
  { label: 'Providers', value: 'provider' },
];

export default function Arena() {
  const navigate = useNavigate();
  const [asset, setAsset] = useState<string>('BTC');
  const [typeFilter, setTypeFilter] = useState<CompetitorType | undefined>(undefined);
  const [isTabActive, setIsTabActive] = useState(!document.hidden);

  useEffect(() => {
    const handler = () => setIsTabActive(!document.hidden);
    document.addEventListener('visibilitychange', handler);
    return () => document.removeEventListener('visibilitychange', handler);
  }, []);

  const { data, isLoading } = useQuery({
    queryKey: ['competition', 'leaderboard', asset, typeFilter],
    queryFn: () => competitionApi.getLeaderboard({ asset, type: typeFilter }),
    refetchInterval: isTabActive ? 30_000 : 120_000,
  });

  return (
    <CompetitionErrorBoundary>
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Main content - 3 columns */}
        <div className="lg:col-span-3 space-y-4">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h1 className="text-2xl font-bold">Arena Leaderboard</h1>
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
            competitors={data?.leaderboard ?? []}
            isLoading={isLoading}
            onRowClick={(id) => navigate(`/arena/competitors/${id}`)}
          />

          <div className="text-xs text-gray-600 text-center">
            {data?.competitor_count ?? 0} competitors &middot; Refreshing every {isTabActive ? '30s' : '2m'}
          </div>
        </div>

        {/* Sidebar - 1 column */}
        <div className="lg:col-span-1">
          <div className="sticky top-4">
            <AchievementFeed />
          </div>
        </div>
      </div>
    </CompetitionErrorBoundary>
  );
}
