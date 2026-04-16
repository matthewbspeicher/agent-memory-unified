/**
 * FeedArbLive — public dashboard at remembr.dev/feeds/arb/live
 *
 * Spec §3.1 — the "honest tracker" surface. Shows real-time arb signals
 * published by the trading engine, each tagged with its eventual outcome
 * (filled/missed), plus the realized + scaled PnL from the $11k sleeve.
 *
 * Deliberately renders useful content in every state:
 *  - Pre-first-signal: empty-state banner explaining the feed is warming
 *  - Signals but no fills: shows the signal stream + "no PnL yet, executor
 *    has not traded" disclosure. Honest-tracker brand dies if we fabricate.
 *  - Signals + PnL: full dashboard with realized/scaled/cumulative cards
 *
 * Refresh cadence: 10s (matches the backend Redis cache TTL; polling at
 * the same rate is free from the backend's perspective).
 */

import { useEffect, useState } from 'react';
import { feedsArbApi, type ArbSignal, type PublicFeedSnapshot } from '../lib/api/feeds';
import { GlassCard } from '../components/GlassCard';

const REFRESH_INTERVAL_MS = 10_000;

export default function FeedArbLive() {
  const [snapshot, setSnapshot] = useState<PublicFeedSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fetchSnapshot = async () => {
      try {
        const data = await feedsArbApi.getPublicSnapshot();
        if (cancelled) return;
        setSnapshot(data);
        setError(null);
      } catch (e: any) {
        if (cancelled) return;
        setError(e?.message ?? 'Failed to load feed');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchSnapshot();
    const id = setInterval(fetchSnapshot, REFRESH_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  // Derive aggregate stats from the signals array — these are cheap to
  // compute each render, no memoization needed at this list size (≤50).
  const signals = snapshot?.signals ?? [];
  const outcomes = countOutcomes(signals);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans relative overflow-x-hidden">
      {/* Ambient glows — matches Landing aesthetic */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[600px] bg-cyan-900/10 blur-[150px] rounded-full pointer-events-none" />
      <div className="absolute bottom-0 right-0 w-[600px] h-[600px] bg-violet-900/10 blur-[150px] rounded-full pointer-events-none" />

      <div className="relative z-10 max-w-6xl mx-auto px-4 md:px-8 py-12">
        <Header asOf={snapshot?.as_of} loading={loading} error={error} />

        <div className="mt-8 grid grid-cols-1 lg:grid-cols-3 gap-4">
          <PnLCard snapshot={snapshot} />
          <OutcomesCard outcomes={outcomes} total={signals.length} />
          <HonestyCard scaling={snapshot?.scaling} pnl={snapshot?.pnl ?? null} />
        </div>

        <section className="mt-10">
          <div className="flex items-baseline justify-between mb-3">
            <h2 className="text-xl md:text-2xl font-bold tracking-tight text-slate-100">
              Live signal stream
            </h2>
            <span className="text-xs font-mono text-slate-500 uppercase tracking-widest">
              last {signals.length} / refreshes every 10s
            </span>
          </div>
          {loading && signals.length === 0 ? (
            <LoadingSkeleton />
          ) : signals.length === 0 ? (
            <EmptyState />
          ) : (
            <SignalTable signals={signals} />
          )}
        </section>

        <footer className="mt-16 pt-8 border-t border-white/5 text-xs text-slate-500 font-mono">
          remembr.dev/feeds/arb/live — honest tracker, pre-launch. This is
          a data feed, not investment advice. Past performance on the
          $11,000 demonstration sleeve does not guarantee future results.
          Prediction-market trading carries significant risk of loss.
        </footer>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Header
// ---------------------------------------------------------------------------

function Header({
  asOf,
  loading,
  error,
}: {
  asOf?: string;
  loading: boolean;
  error: string | null;
}) {
  return (
    <header className="flex flex-col md:flex-row md:items-end md:justify-between gap-2">
      <div>
        <div className="inline-flex items-center gap-2 bg-cyan-950/30 border border-cyan-500/30 rounded-full px-3 py-1 mb-4 shadow-[0_0_15px_rgba(34,211,238,0.2)]">
          <span className="relative flex h-2 w-2">
            <span
              className={`animate-ping absolute inline-flex h-full w-full rounded-full ${
                error ? 'bg-rose-400' : 'bg-cyan-400'
              } opacity-75`}
            />
            <span
              className={`relative inline-flex rounded-full h-2 w-2 ${
                error ? 'bg-rose-500' : 'bg-cyan-500'
              }`}
            />
          </span>
          <span className="text-xs font-mono text-cyan-300 tracking-widest uppercase">
            {error ? 'feed offline' : loading ? 'loading' : 'live'}
          </span>
        </div>
        <h1 className="text-4xl md:text-5xl font-black tracking-tighter text-slate-100">
          PM Arb Signal Feed
        </h1>
        <p className="mt-1 text-slate-400 font-mono text-sm">
          Cross-platform prediction-market arbitrage · Kalshi ↔ Polymarket
        </p>
      </div>
      <div className="text-right">
        <div className="text-xs uppercase tracking-widest text-slate-500 font-mono">
          as of
        </div>
        <div className="text-sm font-mono text-slate-300">
          {asOf ? formatAbsolute(asOf) : '—'}
        </div>
      </div>
    </header>
  );
}

// ---------------------------------------------------------------------------
// PnL card — realized/scaled/cumulative with honest-tracker fallback
// ---------------------------------------------------------------------------

function PnLCard({ snapshot }: { snapshot: PublicFeedSnapshot | null }) {
  const pnl = snapshot?.pnl;
  return (
    <GlassCard variant="cyan" hoverEffect={false}>
      <div className="text-xs uppercase tracking-widest text-cyan-300/80 font-mono mb-2">
        realized PnL ($11k sleeve)
      </div>
      {!pnl ? (
        <>
          <div className="text-3xl font-mono font-bold text-slate-500">—</div>
          <p className="mt-3 text-xs font-mono text-slate-500 leading-relaxed">
            No fills on the $11k sleeve yet. The executor is in shadow
            mode pending compliance review (week 11 paid launch). This
            panel stays blank — honest tracker by design — until real
            fills land.
          </p>
        </>
      ) : (
        <>
          <div className="text-3xl font-mono font-bold text-cyan-200">
            {formatUsd(pnl.cumulative_usd)}
          </div>
          <div className="mt-3 space-y-1 text-xs font-mono text-slate-400">
            <Row label="this tick" value={formatUsd(pnl.realized_usd)} />
            <Row label="open mtm" value={formatUsd(pnl.open_usd)} />
            <Row label="closed positions" value={String(pnl.closed_positions)} />
          </div>
          {pnl.scaled_cumulative_usd != null && (
            <div className="mt-4 pt-3 border-t border-cyan-500/10">
              <div className="text-xs uppercase tracking-widest text-violet-300/70 font-mono mb-1">
                scaled to $250k reference
              </div>
              <div className="text-xl font-mono font-bold text-violet-200">
                {formatUsd(pnl.scaled_cumulative_usd)}
              </div>
            </div>
          )}
        </>
      )}
    </GlassCard>
  );
}

// ---------------------------------------------------------------------------
// Outcomes card — filled/missed breakdown
// ---------------------------------------------------------------------------

function OutcomesCard({
  outcomes,
  total,
}: {
  outcomes: Record<string, number>;
  total: number;
}) {
  const cells: Array<{ label: string; value: number; color: string }> = [
    { label: 'filled', value: outcomes.filled ?? 0, color: 'text-emerald-300' },
    { label: 'missed', value: outcomes.missed ?? 0, color: 'text-rose-300' },
    {
      label: 'dead book',
      value: outcomes.dead_book_skipped ?? 0,
      color: 'text-slate-400',
    },
    { label: 'pending', value: outcomes.pending ?? 0, color: 'text-amber-300' },
  ];
  return (
    <GlassCard variant="default" hoverEffect={false}>
      <div className="text-xs uppercase tracking-widest text-slate-400 font-mono mb-3">
        outcomes · last {total}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {cells.map((c) => (
          <div key={c.label}>
            <div className={`text-2xl font-mono font-bold ${c.color}`}>
              {c.value}
            </div>
            <div className="text-xs font-mono text-slate-500 uppercase tracking-wider">
              {c.label}
            </div>
          </div>
        ))}
      </div>
      <p className="mt-4 text-[10px] font-mono text-slate-500 leading-relaxed">
        "missed" means the signal expired without a fill. "pending" means
        the attribution job hasn't run yet or the signal is still live.
      </p>
    </GlassCard>
  );
}

// ---------------------------------------------------------------------------
// Honesty card — explains scaled PnL and what we're NOT doing
// ---------------------------------------------------------------------------

function HonestyCard({
  scaling,
  pnl,
}: {
  scaling?: string | null;
  pnl: PublicFeedSnapshot['pnl'];
}) {
  return (
    <GlassCard variant="violet" hoverEffect={false}>
      <div className="text-xs uppercase tracking-widest text-violet-300/80 font-mono mb-2">
        scaling method
      </div>
      <p className="text-xs font-mono text-slate-400 leading-relaxed">
        {scaling ??
          pnl?.scaling_assumption ??
          'Scaled PnL is a linear projection from the $11k real sleeve to a $250k reference book. Does not adjust for slippage at larger notional; slippage-aware scaling is v1.1. When no fills have happened, nothing is projected.'}
      </p>
      <div className="mt-4 pt-3 border-t border-violet-500/10 text-[10px] font-mono text-slate-500 leading-relaxed">
        If a strategy goes red publicly, we show it. Drawdowns are not
        hidden. Losses are not deleted. This is the brand.
      </div>
    </GlassCard>
  );
}

// ---------------------------------------------------------------------------
// Signal table — the stream
// ---------------------------------------------------------------------------

function SignalTable({ signals }: { signals: ArbSignal[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm font-mono border-collapse">
        <thead>
          <tr className="text-left text-xs uppercase tracking-widest text-slate-500 border-b border-white/5">
            <th className="py-2 pr-4 font-normal">when</th>
            <th className="py-2 pr-4 font-normal">kalshi</th>
            <th className="py-2 pr-4 font-normal">polymarket</th>
            <th className="py-2 pr-4 font-normal text-right">edge</th>
            <th className="py-2 pr-4 font-normal text-right">size</th>
            <th className="py-2 pr-4 font-normal">outcome</th>
          </tr>
        </thead>
        <tbody>
          {signals.map((s) => (
            <tr
              key={s.signal_id}
              className="border-b border-white/5 hover:bg-white/[0.02] transition-colors"
            >
              <td className="py-2 pr-4 text-slate-400" title={s.ts}>
                {formatRelative(s.ts)}
              </td>
              <td className="py-2 pr-4 text-slate-200">
                <span className="text-slate-100">{s.pair.kalshi.ticker}</span>
                <span className="ml-2 text-slate-500">
                  {s.pair.kalshi.side}
                </span>
              </td>
              <td className="py-2 pr-4 text-slate-300">
                <span title={s.pair.polymarket.token_id}>
                  {truncate(s.pair.polymarket.token_id, 16)}
                </span>
                <span className="ml-2 text-slate-500">
                  {s.pair.polymarket.side}
                </span>
              </td>
              <td className="py-2 pr-4 text-right text-cyan-300">
                {s.edge_cents.toFixed(1)}¢
              </td>
              <td className="py-2 pr-4 text-right text-slate-400">
                ${s.max_size_at_edge_usd.toFixed(0)}
              </td>
              <td className="py-2 pr-4">
                <OutcomeChip outcome={s.outcome} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OutcomeChip({ outcome }: { outcome: ArbSignal['outcome'] }) {
  const styles: Record<string, string> = {
    filled: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30',
    missed: 'bg-rose-500/15 text-rose-300 border-rose-500/30',
    dead_book_skipped: 'bg-slate-500/15 text-slate-400 border-slate-500/30',
    pending: 'bg-amber-500/15 text-amber-300 border-amber-500/30',
  };
  const key = outcome ?? 'pending';
  const label = outcome === 'dead_book_skipped' ? 'dead book' : key;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-widest ${styles[key]}`}
    >
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Empty / loading states
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <GlassCard variant="default" hoverEffect={false}>
      <div className="text-sm font-mono text-slate-400">
        No signals in the last window. The cron scan runs every 30 min;
        this panel refreshes every 10s. If this stays empty for longer
        than an hour during trading, the{' '}
        <span className="text-slate-200">D4 publisher-zero-publish</span>{' '}
        alert will fire.
      </div>
    </GlassCard>
  );
}

function LoadingSkeleton() {
  return (
    <GlassCard variant="default" hoverEffect={false}>
      <div className="animate-pulse space-y-2">
        <div className="h-3 bg-slate-700/40 rounded w-1/3" />
        <div className="h-3 bg-slate-700/40 rounded w-1/2" />
        <div className="h-3 bg-slate-700/40 rounded w-2/5" />
      </div>
    </GlassCard>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="uppercase tracking-widest text-slate-500 text-[10px]">
        {label}
      </span>
      <span className="text-slate-300">{value}</span>
    </div>
  );
}

function countOutcomes(signals: ArbSignal[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const s of signals) {
    const key = s.outcome ?? 'pending';
    out[key] = (out[key] ?? 0) + 1;
  }
  return out;
}

function formatUsd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  const sign = n < 0 ? '-' : '';
  const abs = Math.abs(n);
  return `${sign}$${abs.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  if (!Number.isFinite(then)) return '—';
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 48) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

function formatAbsolute(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
  } catch {
    return iso;
  }
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + '…';
}
