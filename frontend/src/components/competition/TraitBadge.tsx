import { AgentTrait } from '@/lib/api/competition';

const TRAIT_CONFIG: Record<AgentTrait, { icon: string; name: string }> = {
  genesis:         { icon: '🧬', name: 'Genesis' },
  risk_manager:    { icon: '🛡️', name: 'Risk Manager' },
  tail_hedged:     { icon: '📉', name: 'Tail Hedged' },
  trend_follower:  { icon: '📈', name: 'Trend Follower' },
  momentum:        { icon: '🚀', name: 'Momentum' },
  breakout:        { icon: '💥', name: 'Breakout' },
  mean_reversion:  { icon: '↩️', name: 'Mean Reversion' },
  range_bound:     { icon: '📊', name: 'Range Bound' },
  statistical:     { icon: '📐', name: 'Statistical' },
  cointegration:   { icon: '🔗', name: 'Cointegration' },
  kalman_filter:   { icon: '⚙️', name: 'Kalman Filter' },
};

interface TraitBadgeProps {
  trait: AgentTrait;
  unlocked?: boolean;
  size?: 'sm' | 'md' | 'lg';
  onClick?: () => void;
  selected?: boolean;
}

export function TraitBadge({ trait, unlocked = true, size = 'md', onClick, selected }: TraitBadgeProps) {
  const cfg = TRAIT_CONFIG[trait] || { icon: '?', name: trait };
  const locked = !unlocked;

  const sizeClasses = {
    sm: 'px-1.5 py-0.5 text-xs gap-1',
    md: 'px-2 py-1 text-sm gap-1.5',
    lg: 'px-3 py-1.5 text-base gap-2',
  };

  const iconSizes = {
    sm: 'text-xs',
    md: 'text-sm',
    lg: 'text-base',
  };

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={locked || !onClick}
      className={`
        inline-flex items-center rounded border transition-all
        ${sizeClasses[size]}
        ${locked
          ? 'border-gray-800 bg-gray-900/30 opacity-40 cursor-not-allowed'
          : selected
            ? 'border-cyan-500 bg-cyan-500/10 shadow-[0_0_8px_rgba(6,182,212,0.3)]'
            : 'border-gray-700 bg-gray-800/50 hover:border-gray-500 hover:bg-gray-800'
        }
        ${onClick && !locked ? 'cursor-pointer' : ''}
      `}
      title={locked ? `Locked (requires level)` : cfg.name}
    >
      <span className={iconSizes[size]}>{locked ? '🔒' : cfg.icon}</span>
      <span className={`font-medium ${locked ? 'text-gray-600' : 'text-gray-200'}`}>
        {cfg.name}
      </span>
    </button>
  );
}
