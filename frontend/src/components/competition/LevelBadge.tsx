// frontend/src/components/competition/LevelBadge.tsx
import type { Tier } from '../../lib/api/competition';

const TIER_CONFIG: Record<Tier, { color: string; glow: string }> = {
  diamond: { color: '#00D4FF', glow: '0 0 8px rgba(0, 212, 255, 0.5)' },
  gold:    { color: '#FFD700', glow: '0 0 8px rgba(255, 215, 0, 0.5)' },
  silver:  { color: '#C0C0C0', glow: 'none' },
  bronze:  { color: '#CD7F32', glow: 'none' },
};

export function LevelBadge({ level, tier = 'silver' }: { level: number; tier?: Tier }) {
  const cfg = TIER_CONFIG[tier];
  return (
    <span
      className="inline-flex items-center justify-center w-7 h-7 rounded-full font-bold text-sm"
      style={{
        color: cfg.color,
        border: `2px solid ${cfg.color}`,
        backgroundColor: `${cfg.color}15`,
        boxShadow: cfg.glow,
      }}
      title={`Level ${level}`}
    >
      {level}
    </span>
  );
}
