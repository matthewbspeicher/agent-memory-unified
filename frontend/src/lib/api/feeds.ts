/**
 * PM Arb Signal Feed API client.
 *
 * Thin axios wrappers over the trading backend's `/api/v1/feeds/arb/*`
 * routes. Two endpoints:
 *  - `/public`  — no auth, spec §3.1. Used by the FeedArbLive dashboard
 *                  and the sample-signals preview on FeedArbLanding.
 *  - `/signals` — auth required (scope `read:feeds.arb`), spec §3.2.
 *                  Not called from the frontend — paid subscribers hit
 *                  this from their own infra. Typed here for parity.
 *
 * In production the frontend and backend share the `remembr.dev` origin
 * (the Node reverse proxy in frontend/server.mjs routes `/api/*` to the
 * trading service), so all calls are same-origin. In `vite dev` the
 * proxy at `frontend/vite.config.ts` handles the same routing against
 * the local trading container on :8080.
 */

import { createApiClient } from './factory';

// ---------------------------------------------------------------------------
// Response types — match backend shapes exactly (spec §3.1, §3.2)
// ---------------------------------------------------------------------------

/** One signal as returned by either endpoint. */
export interface ArbSignal {
  signal_id: string;
  ts: string; // ISO-8601
  pair: {
    kalshi: { ticker: string; side: string };
    polymarket: { token_id: string; side: string };
  };
  edge_cents: number;
  max_size_at_edge_usd: number;
  expires_at: string; // ISO-8601
  /**
   * Filled by the attribution job. Null = pending (signal still live
   * or attribution hasn't run yet). `dead_book_skipped` reserved for
   * future use when we detect the orderbook was too thin.
   */
  outcome: 'filled' | 'missed' | 'dead_book_skipped' | null;
}

/** Per-rollup PnL row, spec §3.1. */
export interface ArbPnLRollup {
  rollup_ts: string;
  realized_usd: number | null;
  open_usd: number | null;
  cumulative_usd: number | null;
  open_positions: number;
  closed_positions: number;
  scaled_realized_usd: number | null;
  scaled_open_usd: number | null;
  scaled_cumulative_usd: number | null;
  scaling_assumption: string | null;
}

/** `GET /api/v1/feeds/arb/public` response — spec §3.1. */
export interface PublicFeedSnapshot {
  as_of: string;
  signals: ArbSignal[];
  /** Null until the attribution job writes the first rollup — honest
   * tracker: no fake PnL. Frontend must handle this cleanly. */
  pnl: ArbPnLRollup | null;
  scaling: string | null;
}

/** `GET /api/v1/feeds/arb/signals` response — spec §3.2. */
export interface SubscriberFeedPage {
  signals: ArbSignal[];
  next_since: string;
  truncated: boolean;
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

// Same-origin: `/api/v1` resolves via the frontend reverse proxy (prod)
// or the Vite dev-server proxy (dev).
const feedsApi = createApiClient('/api/v1/feeds/arb');

export const feedsArbApi = {
  /** Public dashboard snapshot. 10s TTL cache on the backend; polling
   * from the frontend at the same cadence is safe. */
  getPublicSnapshot: (): Promise<PublicFeedSnapshot> =>
    feedsApi.get<PublicFeedSnapshot>('/public').then((r) => r.data),

  /** Subscriber feed page. Not invoked from the frontend in v1 — paid
   * subscribers call this from their own infra with their API key. Kept
   * for type parity and so an admin tool can preview what subscribers
   * see. */
  getSubscriberPage: (params: {
    since: string;
    limit?: number;
  }): Promise<SubscriberFeedPage> =>
    feedsApi
      .get<SubscriberFeedPage>('/signals', { params })
      .then((r) => r.data),
};
