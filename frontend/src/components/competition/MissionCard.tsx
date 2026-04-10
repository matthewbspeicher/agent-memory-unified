import type { Mission } from '../../lib/api/competition';

interface MissionCardProps {
  mission: Mission;
  onClaim?: (missionId: string) => void;
}

export function MissionCard({ mission, onClaim }: MissionCardProps) {
  const isDaily = mission.mission_type === 'daily';

  return (
    <div className={`
      relative p-4 rounded-lg border transition-all
      ${mission.completed
        ? mission.claimed
          ? 'border-gray-700 bg-gray-900/30 opacity-60'
          : 'border-emerald-500/50 bg-emerald-950/30 shadow-[0_0_15px_rgba(16,185,129,0.2)]'
        : 'border-gray-700 bg-gray-800/50 hover:border-gray-600'
      }
    `}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-2xl">{mission.icon}</span>
          <div>
            <div className="font-bold text-white">{mission.name}</div>
            <div className="text-xs text-gray-400">{mission.description}</div>
          </div>
        </div>
        <div className={`
          text-xs px-2 py-0.5 rounded uppercase font-bold tracking-wider
          ${isDaily ? 'bg-cyan-500/20 text-cyan-400' : 'bg-purple-500/20 text-purple-400'}
        `}>
          {isDaily ? 'Daily' : 'Weekly'}
        </div>
      </div>

      <div className="mb-3">
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>Progress</span>
          <span>{mission.progress} / {mission.target}</span>
        </div>
        <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              mission.completed
                ? 'bg-emerald-500'
                : 'bg-gradient-to-r from-cyan-500 to-blue-500'
            }`}
            style={{ width: `${mission.progress_pct}%` }}
          />
        </div>
      </div>

      <div className="flex items-center justify-between">
        <div className="text-xs">
          <span className="text-amber-400 font-bold">+{mission.xp_reward} XP</span>
        </div>

        {mission.is_claimable && onClaim && (
          <button
            onClick={() => onClaim(mission.mission_id)}
            className="px-3 py-1 text-xs font-bold bg-emerald-600 hover:bg-emerald-500 text-white rounded transition-colors"
          >
            Claim
          </button>
        )}

        {mission.claimed && (
          <span className="text-xs text-emerald-400 font-bold">Claimed</span>
        )}

        {!mission.completed && !mission.is_claimable && (
          <span className="text-xs text-gray-500">
            {mission.completed ? 'Complete!' : `${Math.round(mission.progress_pct)}%`}
          </span>
        )}
      </div>
    </div>
  );
}
