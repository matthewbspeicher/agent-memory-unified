// frontend/src/components/competition/TierBadge.tsx
import type { Tier } from '../../lib/api/competition';

const TIER_CONFIG: Record<Tier, { color: string; bg: string; label: string }> = {
  diamond: { color: '#00D4FF', bg: 'rgba(0, 212, 255, 0.15)', label: 'DIA' },
  gold:    { color: '#FFD700', bg: 'rgba(255, 215, 0, 0.15)', label: 'GLD' },
  silver:  { color: '#C0C0C0', bg: 'rgba(192, 192, 192, 0.15)', label: 'SLV' },
  bronze:  { color: '#CD7F32', bg: 'rgba(205, 127, 50, 0.15)', label: 'BRZ' },
};

export function TierBadge({ tier }: { tier: Tier }) {
  const cfg = TIER_CONFIG[tier];
  return (
    <span
      style={{ color: cfg.color, backgroundColor: cfg.bg }}
      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-bold"
      title={tier}
    >
      <span style={{ fontSize: '0.6rem' }}>&#9670;</span> {cfg.label}
    </span>
  );
}
