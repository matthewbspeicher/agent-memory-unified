const REGIME_CONFIG: Record<MarketRegime, {label: string, color: string, bg: string}> = {
  trending_bull:  { label: 'Bull',     color: 'var(--color-accent-success)', bg: 'rgba(var(--color-accent-success-rgb), 0.15)' },
  trending_bear:  { label: 'Bear',     color: 'var(--color-accent-danger)', bg: 'rgba(var(--color-accent-danger-rgb), 0.15)' },
  volatile:       { label: 'Volatile', color: 'var(--color-accent-warning)', bg: 'rgba(var(--color-accent-warning-rgb), 0.15)' },
  quiet:          { label: 'Quiet',    color: 'var(--color-text-muted)', bg: 'rgba(var(--color-text-muted-rgb), 0.15)' },
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
