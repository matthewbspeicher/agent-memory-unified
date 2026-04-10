// frontend/src/components/competition/EloChart.tsx
import { useEloHistory, type EloHistoryPoint } from '../../lib/api/competition';
import { Sparkline } from '../charts/Sparkline';

interface EloChartProps {
  competitorId: string;
  asset?: string;
  days?: number;
  compact?: boolean;
}

export function EloChart({ competitorId, asset = 'BTC', days = 30, compact = false }: EloChartProps) {
  const { data, isLoading } = useEloHistory(competitorId, asset, days);

  if (isLoading || !data?.history.length) {
    return <div className="h-8 bg-gray-800 rounded animate-pulse" />;
  }

  const elos = data.history.map((h: EloHistoryPoint) => h.elo);
  const current = elos[elos.length - 1];
  const start = elos[0];
  const delta = current - start;
  const deltaColor = delta >= 0 ? 'var(--color-accent-success)' : 'var(--color-accent-danger)';

  if (compact) {
    return (
      <div className="flex items-center gap-2">
        <Sparkline data={elos} color={deltaColor} />
        <span style={{ color: deltaColor }} className="text-xs font-mono">
          {delta >= 0 ? '+' : ''}{delta}
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold font-mono">{current}</span>
        <span style={{ color: deltaColor }} className="text-sm font-mono">
          {delta >= 0 ? '+' : ''}{delta} ({days}d)
        </span>
      </div>
      <Sparkline data={elos} width={300} height={60} color={deltaColor} />
    </div>
  );
}
