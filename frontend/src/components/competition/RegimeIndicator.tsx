const REGIME_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  trending_bull:  { label: 'Bull',     color: '#10B981', bg: 'rgba(16, 185, 129, 0.15)' },
  trending_bear:  { label: 'Bear',     color: '#EF4444', bg: 'rgba(239, 68, 68, 0.15)' },
  volatile:       { label: 'Volatile', color: '#F59E0B', bg: 'rgba(245, 158, 11, 0.15)' },
  quiet:          { label: 'Quiet',    color: '#6B7280', bg: 'rgba(107, 114, 128, 0.15)' },
};

export function RegimeIndicator({ regime }: { regime: string }) {
  const cfg = REGIME_CONFIG[regime] || REGIME_CONFIG.quiet;
  return (
    <span style={{ color: cfg.color, backgroundColor: cfg.bg }}
      className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium">
      {cfg.label}
    </span>
  );
}
