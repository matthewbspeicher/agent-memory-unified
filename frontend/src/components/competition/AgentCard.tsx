import type { AgentCard as AgentCardType, CardRarity } from '../../lib/api/competition';
import { LevelBadge } from './LevelBadge';
import { TierBadge } from './TierBadge';

const RARITY_CONFIG: Record<CardRarity, { border: string; bg: string; glow: string; label: string }> = {
  common: {
    border: 'border-gray-600',
    bg: 'bg-gray-900/80',
    glow: '',
    label: 'Common',
  },
  uncommon: {
    border: 'border-green-600',
    bg: 'bg-green-950/40',
    glow: 'shadow-[0_0_15px_rgba(34,197,94,0.3)]',
    label: 'Uncommon',
  },
  rare: {
    border: 'border-blue-500',
    bg: 'bg-blue-950/40',
    glow: 'shadow-[0_0_20px_rgba(59,130,246,0.4)]',
    label: 'Rare',
  },
  epic: {
    border: 'border-purple-500',
    bg: 'bg-purple-950/40',
    glow: 'shadow-[0_0_25px_rgba(168,85,247,0.5)]',
    label: 'Epic',
  },
  legendary: {
    border: 'border-amber-400',
    bg: 'bg-amber-950/40',
    glow: 'shadow-[0_0_30px_rgba(251,191,36,0.6)] animate-legendary-glow',
    label: 'Legendary',
  },
};

const TRAIT_ICONS: Record<string, string> = {
  genesis: '🧬', risk_manager: '🛡️', tail_hedged: '📉',
  trend_follower: '📈', momentum: '🚀', breakout: '💥',
  mean_reversion: '↩️', range_bound: '📊', statistical: '📐',
  cointegration: '🔗', kalman_filter: '⚙️',
};

interface AgentCardProps {
  card: AgentCardType;
  onClick?: () => void;
  compact?: boolean;
}

export function AgentCard({ card, onClick, compact = false }: AgentCardProps) {
  const rarity = RARITY_CONFIG[card.rarity];

  if (compact) {
    return (
      <button
        onClick={onClick}
        className={`
          relative w-48 p-3 rounded-lg border-2 ${rarity.border} ${rarity.bg} ${rarity.glow}
          hover:scale-105 transition-transform cursor-pointer text-left
        `}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <LevelBadge level={card.level} tier={card.tier} />
          <TierBadge tier={card.tier} />
        </div>

        {/* Name */}
        <div className="font-bold text-white truncate mb-1">{card.name}</div>

        {/* Stats row */}
        <div className="flex justify-between text-xs text-gray-400 mb-2">
          <span>ELO {card.elo}</span>
          <span className="text-amber-400">{rarity.label}</span>
        </div>

        {/* Trait icons */}
        {card.trait_icons.length > 0 && (
          <div className="flex gap-1">
            {card.trait_icons.slice(0, 3).map((icon, i) => (
              <span key={i} className="text-sm">{icon}</span>
            ))}
          </div>
        )}
      </button>
    );
  }

  return (
    <div
      onClick={onClick}
      className={`
        relative w-72 rounded-xl border-2 ${rarity.border} ${rarity.bg} ${rarity.glow}
        overflow-hidden ${onClick ? 'cursor-pointer hover:scale-[1.02] transition-transform' : ''}
      `}
    >
      {/* Rarity banner */}
      <div className={`px-3 py-1 text-center text-xs font-bold uppercase tracking-wider
        ${card.rarity === 'legendary' ? 'bg-amber-500/20 text-amber-400' :
          card.rarity === 'epic' ? 'bg-purple-500/20 text-purple-400' :
          card.rarity === 'rare' ? 'bg-blue-500/20 text-blue-400' :
          card.rarity === 'uncommon' ? 'bg-green-500/20 text-green-400' :
          'bg-gray-700/50 text-gray-400'}
      `}>
        {rarity.label} Card
      </div>

      {/* Main content */}
      <div className="p-4">
        {/* Header with level and tier */}
        <div className="flex items-center justify-between mb-3">
          <LevelBadge level={card.level} tier={card.tier} />
          <TierBadge tier={card.tier} />
        </div>

        {/* Name and ELO */}
        <div className="mb-4">
          <div className="text-xl font-black text-white truncate">{card.name}</div>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-2xl font-mono font-bold text-cyan-400">{card.elo}</span>
            <span className="text-xs text-gray-500 uppercase">ELO</span>
          </div>
        </div>

        {/* XP bar */}
        <div className="mb-4">
          <div className="flex justify-between text-xs text-gray-400 mb-1">
            <span>Level {card.level}</span>
            <span>{card.stats.total_xp} XP</span>
          </div>
          <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-cyan-500 to-blue-500 rounded-full"
              style={{ width: `${Math.min(100, (card.stats.total_xp % 10000) / 100)}%` }}
            />
          </div>
        </div>

        {/* Stats grid */}
        <div className="grid grid-cols-3 gap-2 mb-4">
          <div className="text-center p-2 bg-gray-800/50 rounded">
            <div className="text-lg font-bold text-white">{card.stats.matches}</div>
            <div className="text-[10px] text-gray-500 uppercase">Matches</div>
          </div>
          <div className="text-center p-2 bg-gray-800/50 rounded">
            <div className="text-lg font-bold text-emerald-400">{card.stats.win_rate}%</div>
            <div className="text-[10px] text-gray-500 uppercase">Win Rate</div>
          </div>
          <div className="text-center p-2 bg-gray-800/50 rounded">
            <div className="text-lg font-bold text-amber-400">{card.stats.best_streak}</div>
            <div className="text-[10px] text-gray-500 uppercase">Best Streak</div>
          </div>
        </div>

        {/* Trait icons */}
        {card.trait_icons.length > 0 && (
          <div className="mb-3">
            <div className="text-[10px] text-gray-500 uppercase mb-1">Traits</div>
            <div className="flex gap-1">
              {card.trait_icons.slice(0, 3).map((icon, i) => (
                <span key={i} className="text-lg" title={icon}>{TRAIT_ICONS[icon] || icon}</span>
              ))}
            </div>
          </div>
        )}

        {/* Achievement badges */}
        {card.achievement_badges.length > 0 && (
          <div>
            <div className="text-[10px] text-gray-500 uppercase mb-1">Recent Achievements</div>
            <div className="flex gap-1 flex-wrap">
              {card.achievement_badges.slice(0, 4).map((badge, i) => (
                <span
                  key={i}
                  className={`text-[10px] px-2 py-0.5 rounded
                    ${badge.tier === 'legendary' ? 'bg-amber-500/20 text-amber-400' :
                      badge.tier === 'rare' ? 'bg-purple-500/20 text-purple-400' :
                      'bg-gray-700/50 text-gray-400'}
                  `}
                  title={badge.name}
                >
                  {badge.type.slice(0, 4)}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 bg-black/30 flex justify-between items-center text-[10px] text-gray-500">
        <span>v{card.card_version}</span>
        <span>{card.stats.achievement_count} achievements</span>
      </div>
    </div>
  );
}
