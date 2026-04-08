// frontend/src/components/competition/CompetitorCard.tsx
import type { Competitor } from '../../lib/api/competition';
import { TierBadge } from './TierBadge';
import { StreakIndicator } from './StreakIndicator';

export function CompetitorCard({ competitor, rank }: { competitor: Competitor; rank: number }) {
  return (
    <div className="flex items-center gap-3 p-3 border-b border-gray-700 hover:bg-gray-800/50">
      <span className="text-gray-500 w-6 text-right text-sm">{rank}</span>
      <TierBadge tier={competitor.tier} />
      <div className="flex-1 min-w-0">
        <div className="font-medium truncate">{competitor.name}</div>
        <div className="text-xs text-gray-500">{competitor.type}</div>
      </div>
      <div className="text-right">
        <div className="font-mono font-bold">{competitor.elo}</div>
        <div className="text-xs"><StreakIndicator streak={competitor.streak} /></div>
      </div>
    </div>
  );
}
