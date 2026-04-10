import type { Competitor, AgentTrait } from '../../lib/api/competition';
import { TierBadge } from './TierBadge';
import { StreakIndicator } from './StreakIndicator';
import { LevelBadge } from './LevelBadge';

const TRAIT_ICONS: Record<string, string> = {
  genesis: '🧬', risk_manager: '🛡️', tail_hedged: '📉',
  trend_follower: '📈', momentum: '🚀', breakout: '💥',
  mean_reversion: '↩️', range_bound: '📊', statistical: '📐',
  cointegration: '🔗', kalman_filter: '⚙️',
};

interface CompetitorCardProps {
  competitor: Competitor;
  rank: number;
  traits?: AgentTrait[];
}

export function CompetitorCard({ competitor, rank, traits }: CompetitorCardProps) {
  return (
    <div className="flex items-center gap-3 p-3 border-b border-gray-700 hover:bg-gray-800/50">
      <span className="text-gray-500 w-6 text-right text-sm">{rank}</span>
      <LevelBadge level={competitor.level} tier={competitor.tier} />
      <TierBadge tier={competitor.tier} />
      <div className="flex-1 min-w-0">
        <div className="font-medium truncate">{competitor.name}</div>
        <div className="flex items-center gap-1 mt-1">
          <span className="text-xs text-gray-500">{competitor.type}</span>
          {traits && traits.length > 0 && (
            <div className="flex gap-0.5 ml-2">
              {traits.slice(0, 3).map(trait => (
                <span key={trait} className="text-xs" title={trait}>
                  {TRAIT_ICONS[trait] || '?'}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="text-right">
        <div className="font-mono font-bold">{competitor.elo}</div>
        <div className="text-xs"><StreakIndicator streak={competitor.streak} /></div>
      </div>
    </div>
  );
}
