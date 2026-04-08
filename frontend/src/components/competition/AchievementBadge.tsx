// frontend/src/components/competition/AchievementBadge.tsx
const BADGE_CONFIG: Record<string, { icon: string; label: string; rarity: string }> = {
  streak_5:         { icon: '🔥', label: 'Hot Streak',      rarity: 'common' },
  streak_10:        { icon: '🔥', label: 'Blazing Streak',  rarity: 'rare' },
  sharp_shooter:    { icon: '🎯', label: 'Sharp Shooter',   rarity: 'rare' },
  iron_throne:      { icon: '💎', label: 'Iron Throne',     rarity: 'legendary' },
  comeback_kid:     { icon: '⬆️', label: 'Comeback Kid',    rarity: 'legendary' },
  regime_survivor:  { icon: '🐂', label: 'Regime Survivor', rarity: 'rare' },
  whale_whisperer:  { icon: '🐋', label: 'Whale Whisperer', rarity: 'rare' },
  first_blood:      { icon: '⚡', label: 'First Blood',     rarity: 'rare' },
};

const RARITY_COLORS: Record<string, string> = {
  common: 'border-gray-600',
  rare: 'border-blue-500',
  legendary: 'border-yellow-500',
};

interface AchievementBadgeProps {
  type: string;
  earnedAt?: string;
  progress?: number;
}

export function AchievementBadge({ type, earnedAt, progress }: AchievementBadgeProps) {
  const cfg = BADGE_CONFIG[type] || { icon: '🏆', label: type, rarity: 'common' };
  const earned = !!earnedAt;
  const borderColor = earned ? RARITY_COLORS[cfg.rarity] : 'border-gray-800';

  return (
    <div 
      className={`inline-flex items-center gap-2 px-2 py-1 rounded border ${borderColor} ${earned ? '' : 'opacity-50'}`}
      title={earned ? `Earned ${earnedAt}` : `${((progress ?? 0) * 100).toFixed(0)}% progress`}
    >
      <span>{cfg.icon}</span>
      <span className="text-xs">{cfg.label}</span>
      {!earned && progress != null && (
        <div className="w-8 h-1 bg-gray-800 rounded-full overflow-hidden">
          <div className="h-full bg-blue-500 rounded-full" style={{ width: `${progress * 100}%` }} />
        </div>
      )}
    </div>
  );
}
