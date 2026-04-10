import { useState, useEffect } from 'react';
import { useSeasons, useSeasonLeaderboard, type Season } from '../../lib/api/competition';

interface SeasonPanelProps {
  competitorId?: string;
}

function StatusBadge({ status }: { status: Season['status'] }) {
  const config = {
    active: { bg: 'bg-cyan-500/15', text: 'text-cyan-400', label: 'Active' },
    ended: { bg: 'bg-gray-600/15', text: 'text-gray-400', label: 'Ended' },
    upcoming: { bg: 'bg-purple-500/15', text: 'text-purple-400', label: 'Upcoming' },
  }[status];

  return (
    <span className={`px-2 py-0.5 rounded text-xs font-bold ${config.bg} ${config.text}`}>
      {config.label}
    </span>
  );
}

function CountdownTimer({ endsAt }: { endsAt: string }) {
  const [timeLeft, setTimeLeft] = useState('');

  useEffect(() => {
    const update = () => {
      const now = Date.now();
      const end = new Date(endsAt).getTime();
      const diff = end - now;

      if (diff <= 0) {
        setTimeLeft('Ended');
        return;
      }

      const days = Math.floor(diff / (1000 * 60 * 60 * 24));
      const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
      const seconds = Math.floor((diff % (1000 * 60)) / 1000);

      if (days > 0) {
        setTimeLeft(`${days}d ${hours}h ${minutes}m`);
      } else if (hours > 0) {
        setTimeLeft(`${hours}h ${minutes}m ${seconds}s`);
      } else {
        setTimeLeft(`${minutes}m ${seconds}s`);
      }
    };

    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, [endsAt]);

  return (
    <span className="font-mono text-lg font-bold text-cyan-400">
      {timeLeft}
    </span>
  );
}

function LoadingSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="h-20 bg-gray-800 rounded-lg" />
      <div className="h-40 bg-gray-800 rounded-lg" />
      <div className="h-32 bg-gray-800 rounded-lg" />
    </div>
  );
}

function LeaderboardRow({
  entry,
  isUser,
}: {
  entry: { rank: number; competitor_id: string; name: string; elo: number; tier: string; matches: number };
  isUser: boolean;
}) {
  const tierColors: Record<string, string> = {
    diamond: 'text-cyan-400',
    gold: 'text-yellow-400',
    silver: 'text-gray-300',
    bronze: 'text-orange-400',
  };

  return (
    <tr className={`border-b border-gray-800 ${isUser ? 'bg-cyan-500/10' : 'hover:bg-gray-800/50'}`}>
      <td className="py-2 px-3 text-gray-400 font-mono text-sm w-10">{entry.rank}</td>
      <td className={`py-2 px-3 font-medium ${isUser ? 'text-cyan-300' : 'text-gray-200'}`}>
        {entry.name}
        {isUser && <span className="ml-2 text-xs text-cyan-500">(You)</span>}
      </td>
      <td className="py-2 px-3 text-right font-mono font-bold text-gray-200">{entry.elo}</td>
      <td className={`py-2 px-3 text-right text-xs font-bold uppercase ${tierColors[entry.tier] || 'text-gray-400'}`}>
        {entry.tier}
      </td>
      <td className="py-2 px-3 text-right text-gray-500 text-sm">{entry.matches}</td>
    </tr>
  );
}

export function SeasonPanel({ competitorId }: SeasonPanelProps) {
  const [selectedSeasonId, setSelectedSeasonId] = useState<string | null>(null);
  const { data: seasonsData, isLoading: seasonsLoading } = useSeasons();
  const { data: leaderboardData, isLoading: leaderboardLoading } = useSeasonLeaderboard(
    selectedSeasonId || '',
    10,
  );

  useEffect(() => {
    if (seasonsData?.current && !selectedSeasonId) {
      setSelectedSeasonId(seasonsData.current.id);
    }
  }, [seasonsData, selectedSeasonId]);

  if (seasonsLoading) {
    return (
      <div className="p-6 border border-gray-700 rounded-lg bg-gray-900">
        <LoadingSkeleton />
      </div>
    );
  }

  const currentSeason = seasonsData?.current;
  const pastSeasons = (seasonsData?.seasons ?? []).filter(s => s.status === 'ended').slice(0, 5);

  return (
    <div className="space-y-6">
      {currentSeason && (
        <div className="p-5 border border-gray-700 rounded-lg bg-gray-900">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-lg font-bold text-white">
                Season {currentSeason.number}
              </h3>
              <p className="text-sm text-gray-400">{currentSeason.name}</p>
            </div>
            <StatusBadge status={currentSeason.status} />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-5">
            <div className="p-3 rounded-lg bg-gray-800 border border-gray-700">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">
                Time Remaining
              </div>
              <CountdownTimer endsAt={currentSeason.ends_at} />
            </div>

            <div className="p-3 rounded-lg bg-gray-800 border border-gray-700">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">
                Participants
              </div>
              <div className="text-lg font-bold text-gray-200">
                {currentSeason.total_participants.toLocaleString()}
              </div>
            </div>

            <div className="p-3 rounded-lg bg-gray-800 border border-gray-700">
              <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">
                Your Rating
              </div>
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold text-gray-200">
                  {currentSeason.your_rating}
                </span>
                {currentSeason.your_rank && (
                  <span className="text-xs text-gray-500">
                    (Rank #{currentSeason.your_rank})
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-gray-800/50 border border-gray-700 flex items-start gap-2">
            <span className="text-purple-400 text-lg leading-none">&#9432;</span>
            <div className="text-xs text-gray-400">
              <span className="font-semibold text-purple-300">Soft Reset:</span>{' '}
              Each season resets ratings but preserves your level, traits, and achievements.
              ELO is recalibrated based on season performance. Participate to climb the ranks!
            </div>
          </div>
        </div>
      )}

      <div className="p-5 border border-gray-700 rounded-lg bg-gray-900">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold text-gray-300 uppercase tracking-wider">
            Season Leaderboard
          </h3>
          {seasonsData?.seasons && seasonsData.seasons.length > 1 && (
            <select
              value={selectedSeasonId || ''}
              onChange={e => setSelectedSeasonId(e.target.value)}
              className="text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-300"
            >
              {seasonsData.seasons.map(s => (
                <option key={s.id} value={s.id}>
                  Season {s.number} - {s.name}
                </option>
              ))}
            </select>
          )}
        </div>

        {leaderboardLoading ? (
          <div className="animate-pulse space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-8 bg-gray-800 rounded" />
            ))}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-500 border-b border-gray-700">
                <th className="py-2 px-3 text-left w-10">#</th>
                <th className="py-2 px-3 text-left">Name</th>
                <th className="py-2 px-3 text-right w-16">ELO</th>
                <th className="py-2 px-3 text-right w-16">Tier</th>
                <th className="py-2 px-3 text-right w-16">Matches</th>
              </tr>
            </thead>
            <tbody>
              {(leaderboardData?.leaderboard ?? []).map(entry => (
                <LeaderboardRow
                  key={entry.competitor_id}
                  entry={entry}
                  isUser={entry.competitor_id === competitorId}
                />
              ))}
              {(!leaderboardData?.leaderboard || leaderboardData.leaderboard.length === 0) && (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-gray-500">
                    No leaderboard data yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>

      {pastSeasons.length > 0 && (
        <div className="p-5 border border-gray-700 rounded-lg bg-gray-900">
          <h3 className="text-sm font-bold text-gray-300 uppercase tracking-wider mb-3">
            Season History
          </h3>
          <div className="space-y-2">
            {pastSeasons.map(s => (
              <div
                key={s.id}
                className="flex items-center justify-between p-3 rounded-lg bg-gray-800 border border-gray-700 cursor-pointer hover:bg-gray-800/80"
                onClick={() => setSelectedSeasonId(s.id)}
              >
                <div className="flex items-center gap-3">
                  <span className="text-sm font-bold text-gray-400">
                    S{s.number}
                  </span>
                  <span className="text-sm text-gray-300">{s.name}</span>
                </div>
                <div className="flex items-center gap-4 text-xs text-gray-500">
                  <span>{s.total_participants} participants</span>
                  {s.your_rank && (
                    <span className="text-gray-400">
                      Your rank: <span className="font-bold">#{s.your_rank}</span>
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
