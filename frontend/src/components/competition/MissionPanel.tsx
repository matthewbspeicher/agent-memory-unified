import { useState } from 'react';
import { useMissions, competitionApi, type MissionType } from '../../lib/api/competition';
import { MissionCard } from './MissionCard';

interface MissionPanelProps {
  competitorId: string;
  asset?: string;
}

export function MissionPanel({ competitorId, asset = 'BTC' }: MissionPanelProps) {
  const [filter, setFilter] = useState<MissionType | 'all'>('all');
  const { data, isLoading, refetch } = useMissions(
    competitorId,
    filter === 'all' ? undefined : filter,
    asset
  );

  const handleClaim = async (missionId: string) => {
    try {
      await competitionApi.claimMission(competitorId, missionId as any, asset);
      refetch();
    } catch (err) {
      console.error('Failed to claim mission:', err);
    }
  };

  const missions = data?.missions ?? [];
  const dailyMissions = missions.filter(m => m.mission_type === 'daily');
  const weeklyMissions = missions.filter(m => m.mission_type === 'weekly');

  const claimableCount = missions.filter(m => m.is_claimable).length;

  if (isLoading) {
    return (
      <div className="p-6 text-center">
        <div className="w-6 h-6 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
        <p className="text-gray-500 text-sm">Loading missions...</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-bold text-gray-300 uppercase tracking-wider">
          Missions
        </h3>
        <div className="flex items-center gap-3">
          {claimableCount > 0 && (
            <span className="text-xs text-emerald-400 font-bold animate-pulse">
              {claimableCount} to claim!
            </span>
          )}
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as MissionType | 'all')}
            className="text-xs bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-300"
          >
            <option value="all">All</option>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
          </select>
        </div>
      </div>

      {filter === 'all' || filter === 'daily' ? (
        <div className="mb-4">
          <div className="text-xs text-cyan-400 uppercase tracking-wider mb-2 font-bold">
            Daily
          </div>
          <div className="space-y-2">
            {dailyMissions.map(mission => (
              <MissionCard
                key={mission.id || mission.mission_id}
                mission={mission}
                onClaim={handleClaim}
              />
            ))}
          </div>
        </div>
      ) : null}

      {filter === 'all' || filter === 'weekly' ? (
        <div>
          <div className="text-xs text-purple-400 uppercase tracking-wider mb-2 font-bold">
            Weekly
          </div>
          <div className="space-y-2">
            {weeklyMissions.map(mission => (
              <MissionCard
                key={mission.id || mission.mission_id}
                mission={mission}
                onClaim={handleClaim}
              />
            ))}
          </div>
        </div>
      ) : null}

      {missions.length === 0 && (
        <div className="text-center py-8 text-gray-500 text-sm">
          No missions available
        </div>
      )}
    </div>
  );
}
