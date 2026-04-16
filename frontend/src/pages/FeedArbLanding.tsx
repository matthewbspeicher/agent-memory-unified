/**
 * FeedArbLanding — sales page at remembr.dev/feeds/arb
 *
 * Spec §3.3. Sections:
 *  1. Hero: product pitch + live signal count
 *  2. Sample signals (5 most recent from public dashboard — proof
 *     that the feed is live)
 *  3. Mini PnL summary (or honest "no fills yet" state)
 *  4. Design-partner CTA: "free 60-day access" before paid launch;
 *     Stripe checkout button is stubbed (lands when STA_STRIPE_ENABLED
 *     goes live per plan G5).
 *  5. FAQ: pricing, audience, not-financial-advice, privacy
 */

import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { feedsArbApi, type ArbSignal, type PublicFeedSnapshot } from '../lib/api/feeds';
import { GlassCard } from '../components/GlassCard';

const SAMPLE_SIGNAL_LIMIT = 5;
const REFRESH_INTERVAL_MS = 30_000; // landing page needs less freshness than /live

export default function FeedArbLanding() {
  const [snapshot, setSnapshot] = useState<PublicFeedSnapshot | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fetchSnapshot = async () => {
      try {
        const data = await feedsArbApi.getPublicSnapshot();
        if (!cancelled) setSnapshot(data);
      } catch {
        // Non-fatal on landing page — don't disrupt the pitch.
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

  const sampleSignals = (snapshot?.signals ?? []).slice(0, SAMPLE_SIGNAL_LIMIT);
  const totalSignals = snapshot?.signals.length ?? 0;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans relative overflow-x-hidden">
      {/* Ambient glows */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[600px] bg-cyan-900/10 blur-[150px] rounded-full pointer-events-none" />
      <div className="absolute bottom-0 left-0 w-[600px] h-[600px] bg-violet-900/10 blur-[150px] rounded-full pointer-events-none" />

      <div className="relative z-10 max-w-4xl mx-auto px-4 md:px-8">
        <Hero loading={loading} totalSignals={totalSignals} />
        <SampleSignals signals={sampleSignals} />
        <PnLSummary snapshot={snapshot} />
        <CTA />
        <FAQ />
        <Footer />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hero
// ---------------------------------------------------------------------------

function Hero({ loading, totalSignals }: { loading: boolean; totalSignals: number }) {
  return (
    <section className="pt-20 md:pt-28 text-center">
      <div className="inline-flex items-center gap-2 bg-cyan-950/30 border border-cyan-500/30 rounded-full px-4 py-1.5 mb-8 shadow-[0_0_15px_rgba(34,211,238,0.2)]">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
        </span>
        <span className="text-xs font-mono text-cyan-300 tracking-widest uppercase">
          {loading
            ? 'loading'
            : `${totalSignals} live signals · honest tracker`}
        </span>
      </div>

      <h1 className="text-5xl md:text-7xl font-black tracking-tighter leading-tight mb-6 text-slate-100">
        PREDICTION-MARKET<br />
        <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-violet-400 to-emerald-400">
          ARB SIGNAL FEED
        </span>
      </h1>

      <p className="text-slate-400 text-lg md:text-xl max-w-2xl mx-auto leading-relaxed mb-2 font-mono">
        Real-time cross-platform price mismatches between Kalshi and
        Polymarket. Integrate via REST, track realized fills on a
        public dashboard, own your edge.
      </p>
      <p className="text-slate-500 text-sm md:text-base max-w-2xl mx-auto font-mono">
        $500/mo flat · single tier · no performance fees · signals only,
        no execution on your behalf
      </p>

      <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
        <Link
          to="/feeds/arb/live"
          className="inline-flex items-center gap-2 bg-cyan-500/20 border border-cyan-400/40 text-cyan-200 hover:bg-cyan-500/30 hover:border-cyan-400/70 transition-colors rounded-full px-5 py-2.5 font-mono text-sm uppercase tracking-widest shadow-[0_0_15px_rgba(34,211,238,0.15)]"
        >
          See the live dashboard →
        </Link>
        <a
          href="#apply"
          className="inline-flex items-center gap-2 bg-violet-500/10 border border-violet-400/30 text-violet-200 hover:bg-violet-500/20 hover:border-violet-400/60 transition-colors rounded-full px-5 py-2.5 font-mono text-sm uppercase tracking-widest"
        >
          Apply for design-partner access
        </a>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Sample signals — proof the feed is live
// ---------------------------------------------------------------------------

function SampleSignals({ signals }: { signals: ArbSignal[] }) {
  return (
    <section className="mt-20">
      <div className="text-center mb-6">
        <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-slate-100">
          Most recent signals
        </h2>
        <p className="mt-1 text-sm font-mono text-slate-500">
          Pulled live from the same endpoint paid subscribers hit.
        </p>
      </div>

      {signals.length === 0 ? (
        <GlassCard variant="default" hoverEffect={false}>
          <div className="text-sm font-mono text-slate-400 text-center">
            No signals in the current window — cron scan runs every 30
            min. Check back shortly or watch the{' '}
            <Link to="/feeds/arb/live" className="text-cyan-300 underline">
              live dashboard
            </Link>
            .
          </div>
        </GlassCard>
      ) : (
        <div className="space-y-2">
          {signals.map((s) => (
            <GlassCard key={s.signal_id} variant="default" hoverEffect={false}>
              <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 font-mono text-sm">
                <div className="text-slate-300">
                  <span className="text-slate-100">{s.pair.kalshi.ticker}</span>{' '}
                  <span className="text-slate-500">{s.pair.kalshi.side}</span>
                  <span className="mx-2 text-slate-600">↔</span>
                  <span className="text-slate-300">
                    {truncate(s.pair.polymarket.token_id, 10)}
                  </span>{' '}
                  <span className="text-slate-500">
                    {s.pair.polymarket.side}
                  </span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-cyan-300">
                    {s.edge_cents.toFixed(1)}¢ edge
                  </span>
                  <span className="text-slate-400">
                    ${s.max_size_at_edge_usd.toFixed(0)}
                  </span>
                  <OutcomePill outcome={s.outcome} />
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      )}
    </section>
  );
}

function OutcomePill({ outcome }: { outcome: ArbSignal['outcome'] }) {
  const styles: Record<string, string> = {
    filled: 'bg-emerald-500/15 text-emerald-300',
    missed: 'bg-rose-500/15 text-rose-300',
    dead_book_skipped: 'bg-slate-500/15 text-slate-400',
    pending: 'bg-amber-500/15 text-amber-300',
  };
  const key = outcome ?? 'pending';
  const label = outcome === 'dead_book_skipped' ? 'dead book' : key;
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-[10px] uppercase tracking-widest ${styles[key]}`}
    >
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// PnL summary — small, defers to /live for detail
// ---------------------------------------------------------------------------

function PnLSummary({ snapshot }: { snapshot: PublicFeedSnapshot | null }) {
  const pnl = snapshot?.pnl;
  return (
    <section className="mt-20 grid grid-cols-1 md:grid-cols-2 gap-4">
      <GlassCard variant="cyan" hoverEffect={false}>
        <div className="text-xs uppercase tracking-widest text-cyan-300/80 font-mono mb-2">
          realized PnL · $11k sleeve
        </div>
        {pnl ? (
          <div className="text-3xl font-mono font-bold text-cyan-200">
            {formatUsd(pnl.cumulative_usd)}
          </div>
        ) : (
          <div className="text-2xl font-mono font-bold text-slate-500">
            Not trading live yet
          </div>
        )}
        <p className="mt-3 text-xs font-mono text-slate-400 leading-relaxed">
          {pnl
            ? 'Realized from actual fills. Every win and every loss shown on the live dashboard.'
            : 'Executor is in shadow mode pending compliance review. This number stays blank — honest tracker — until real fills happen. Spec §11 week-11 paid open is the target.'}
        </p>
      </GlassCard>
      <GlassCard variant="violet" hoverEffect={false}>
        <div className="text-xs uppercase tracking-widest text-violet-300/80 font-mono mb-2">
          scaled to $250k reference
        </div>
        {pnl && pnl.scaled_cumulative_usd != null ? (
          <div className="text-3xl font-mono font-bold text-violet-200">
            {formatUsd(pnl.scaled_cumulative_usd)}
          </div>
        ) : (
          <div className="text-2xl font-mono font-bold text-slate-500">—</div>
        )}
        <p className="mt-3 text-xs font-mono text-slate-400 leading-relaxed">
          Linear projection only. Does not adjust for slippage at larger
          notional — that's v1.1. What this shows is the strategy
          economics, not a promise.
        </p>
      </GlassCard>
    </section>
  );
}

// ---------------------------------------------------------------------------
// CTA — design partner application
// ---------------------------------------------------------------------------

function CTA() {
  return (
    <section id="apply" className="mt-24">
      <GlassCard variant="cyan" hoverEffect={false}>
        <div className="text-center py-6">
          <h2 className="text-2xl md:text-3xl font-bold text-slate-100 mb-3">
            Apply for free 60-day design-partner access
          </h2>
          <p className="text-slate-400 font-mono text-sm max-w-xl mx-auto mb-6">
            Five slots. Semi-pro quants and small prop desks. You get
            the full feed with zero fees for 60 days in exchange for
            weekly feedback calls. Paid tier opens after the window
            closes — at which point design partners get a founding-
            member discount ($300/mo vs $500/mo).
          </p>
          <a
            href="mailto:hello@remembr.dev?subject=Feed%20design%20partner%20application"
            className="inline-flex items-center gap-2 bg-cyan-500/20 border border-cyan-400/40 text-cyan-200 hover:bg-cyan-500/30 hover:border-cyan-400/70 transition-colors rounded-full px-6 py-3 font-mono text-sm uppercase tracking-widest"
          >
            hello@remembr.dev
          </a>
          <p className="mt-4 text-[10px] font-mono text-slate-500 uppercase tracking-widest">
            Stripe checkout unlocks week 11 after compliance sign-off
          </p>
        </div>
      </GlassCard>
    </section>
  );
}

// ---------------------------------------------------------------------------
// FAQ
// ---------------------------------------------------------------------------

function FAQ() {
  const items = [
    {
      q: 'Who is this for?',
      a: 'Semi-professional quantitative traders and small prop desks with $250k–$1M book sizes who want a low-latency REST feed of cross-venue prediction-market arb opportunities. Retail is not the target audience.',
    },
    {
      q: 'How does the signal look?',
      a: 'Each signal is a pair: a Kalshi leg (ticker + side) and a Polymarket leg (token ID + side), plus edge in cents, max size at that edge, and an expires_at horizon. Full schema documented in the spec; recent examples are visible on the live dashboard.',
    },
    {
      q: 'Is this investment advice?',
      a: 'No. This is an informational data feed. We are not a registered investment adviser or commodity trading advisor. You are responsible for your own trading decisions, broker accounts, and legal compliance in your jurisdiction. Prediction-market trading carries significant risk of loss.',
    },
    {
      q: 'Do you trade the signals yourselves?',
      a: 'Yes — an $11,000 personal trading account runs the same signals. Realized and unrealized PnL (including drawdowns) is published on the live dashboard. If the strategy goes red, you see it.',
    },
    {
      q: 'What if I hit the rate limit?',
      a: 'Default tier: 600 req/hr per subscription (10 req/min; 6× headroom over the recommended 30s polling cadence). One client per subscription. Higher limits and webhook delivery are planned for a v2 premium tier after v1 stabilizes.',
    },
    {
      q: 'Why not offer copy trading?',
      a: 'Order routing against customer credentials with a profit share is likely advisory / asset-management activity under SEC or CFTC / NFA. We intentionally stay on the signals-only side of that line. You execute your own trades, in your own accounts, at your own risk.',
    },
  ];
  return (
    <section className="mt-24 space-y-3">
      <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-slate-100 text-center mb-6">
        FAQ
      </h2>
      {items.map(({ q, a }) => (
        <GlassCard key={q} variant="default" hoverEffect={false}>
          <div className="font-mono text-sm">
            <div className="text-slate-100 font-bold mb-2">{q}</div>
            <div className="text-slate-400 leading-relaxed">{a}</div>
          </div>
        </GlassCard>
      ))}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Footer
// ---------------------------------------------------------------------------

function Footer() {
  return (
    <footer className="mt-24 mb-12 pt-8 border-t border-white/5 text-[10px] text-slate-500 font-mono text-center leading-relaxed">
      remembr.dev Arb Signal Feed provides data on observed price
      spreads between prediction-market venues for informational purposes
      only. Nothing herein is investment advice, an offer to buy or sell
      any security, or a recommendation of any trade. Past performance
      on our demonstration account does not guarantee future results.
      Subscribers are responsible for their own trading decisions, legal
      compliance in their jurisdiction, and access to the underlying
      venues. remembr.dev is not a registered investment adviser or
      commodity trading advisor.
    </footer>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatUsd(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return '—';
  const sign = n < 0 ? '-' : '';
  const abs = Math.abs(n);
  return `${sign}$${abs.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + '…';
}
