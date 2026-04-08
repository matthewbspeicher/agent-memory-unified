// frontend/src/pages/Arena.tsx
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLeaderboard, type CompetitorType } from '../lib/api/competition';
import { LeaderboardTable } from '../components/competition/LeaderboardTable';
import { CompetitionErrorBoundary } from '../components/competition/CompetitionErrorBoundary';

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

  const { data, isLoading } = useLeaderboard(asset, typeFilter);

  return (
    <CompetitionErrorBoundary>
      <div className="space-y-4">
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
    </CompetitionErrorBoundary>
  );
}
