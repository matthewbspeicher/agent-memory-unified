# Compliance Memo — PM Arb Signal Feed (v1)

**Status:** DRAFT — outline for external legal counsel review
**Date:** 2026-04-15
**Owner:** mspeicher
**Related specs:** [PM Arb Signal Feed v1](../superpowers/specs/2026-04-15-arb-signal-feed-design.md)
**Launch gate:** This memo must be signed off by external counsel before paid tier opens (week 11, ~2026-07-01 per spec §10). External review lead time is the real long pole — started today to preserve that buffer.

---

## Question for counsel

Does offering a **$500/mo subscription data feed** containing real-time prediction-market arbitrage signals (cross-venue price mismatches between Kalshi and Polymarket) to semi-professional quantitative traders constitute **financial advice**, **investment advisory services**, or any other regulated activity under US securities, commodities, or gaming law?

And if so, what disclaimers, terms, structure, or licensing are required to offer the product legally?

---

## Factual context

1. **Product shape.** Customer pays $500/mo for REST API access to a feed of (timestamp, ticker pair, edge in cents, confidence score, expiration). Also a public dashboard showing our own realized PnL on a personal $11k trading sleeve.
2. **What we publish.** Signals are observations of spread opportunities our systems detect. Each signal names the venue pair and direction (e.g., "BUY Kalshi KXELEC-DJT at 73¢ / SELL Polymarket NO at 27¢"). Price, size hint, and confidence are included. No execution on customer behalf. No custody of customer funds or credentials.
3. **What we do not publish.** We do not send buy/sell recommendations for specific securities. We do not represent that following the signals will produce profits. We do not take custody of customer funds, nor place trades on their behalf, nor have visibility into their brokerage accounts.
4. **Our own trading.** We run a separate $11k personal-capital sleeve that trades the same signals via IBKR + direct venue accounts. Realized/unrealized PnL is published on the public dashboard (§3.1 of the spec). Losses as well as gains are shown ("honest tracker" — the dashboard is the credibility play, not a marketing asset).
5. **Target audience.** Semi-pro quants and small prop desks, ~$250k–$1M book size. Not retail, not casual crypto, not pension funds.
6. **Pricing model.** Flat $500/mo. No performance fees. No profit share. No tiered access based on account size. No "managed" products.
7. **Asset class.** Prediction-market contracts only for v1 (event contracts on Kalshi, positions on Polymarket). No securities, no equities, no options, no crypto spot.
8. **Kalshi classification.** Kalshi is a CFTC-regulated designated contract market (DCM) offering event contracts. Contracts are derivatives under CFTC jurisdiction, not securities.
9. **Polymarket classification.** Polymarket operates offshore, uses crypto settlement, blocks US IPs. Open legal question about whether its prediction markets are CFTC-regulated event contracts, unregistered swaps, or something else. We currently trade it from a VPN'd address in accordance with our own risk tolerance — not advising customers on their access.

---

## Preliminary legal hypotheses (need counsel to confirm or reject)

Marking each: **our hypothesis** | **worst-case**

### H1. This is a data feed, not advice.
**Our hypothesis:** Selling structured market data (spreads between venues) is distributed data, not individualized investment advice under Investment Advisers Act §202(a)(11). We do not tailor signals to customers, we do not know what they trade, we do not collect suitability info. Closest analogue: Bloomberg Terminal, TradingView alerts, Santiment/Glassnode feeds — none are registered advisers.

**Worst-case:** SEC/CFTC regulators take a functional view: "specific trade directions + expected profit + pricing that scales with value of the advice" = advisory-like. This is where the "edge_cents" field and per-signal direction get scrutiny.

### H2. Prediction markets are not securities.
**Our hypothesis:** Kalshi contracts are CFTC-regulated event contracts (27 CFR §40) — not securities. Polymarket is unclear but blocks US IPs, so our customers using it from the US are on their own legal footing.

**Worst-case:** SEC revives the "investment contract" theory against certain prediction-market outcomes (e.g., political event contracts). If customers rely on our signals for markets later deemed to be securities, we may be deemed to have provided securities advice.

### H3. Prop-desk-only audience reduces retail risk.
**Our hypothesis:** Targeting "semi-pro quants with $250k–$1M books" and requiring commercial-sounding sign-up (API-first, no Discord, no social media marketing beyond Twitter/X and one GitHub readme) keeps us out of the retail advisory zone. Accredited-investor posture without formally verifying.

**Worst-case:** Actual subscribers include retail individuals; no verification mechanism. Marketing copy on `remembr.dev/feeds/arb` will be read as general solicitation.

### H4. "Honest tracker" public dashboard showing losses is disclaimer-compliant.
**Our hypothesis:** Publishing our own realized PnL (including drawdowns) is a *performance track record* not a *forward-looking claim*. Adding "past performance does not guarantee future results" disclaimers on the dashboard and landing page cover the standard marketing-materials rule.

**Worst-case:** The dashboard's *"customer #1 within 30 days"* success metric in §13 of the spec implies the product *does* produce performance, which counsel may treat as a forward-looking performance claim regardless of disclaimers.

### H5. No performance fees = no adviser-by-conduct test.
**Our hypothesis:** Flat $500/mo pricing and no profit share disposes of the "compensation in exchange for advice" test that triggers adviser registration. Analogue: Bloomberg charges flat rates, not commissions.

**Worst-case:** SEC uses a functional compensation test — if customers buy the product *because of* the expected trading edge, the flat fee is effectively compensation for advice regardless of structure.

---

## Required outputs from counsel

Numbered for tracking:

1. **Go/no-go on current structure.** Is the v1 product as described (flat $500/mo, REST API, semi-pro quants, prediction markets only) legally operable without registering as an investment adviser, commodity trading advisor (CTA), or other regulated entity in the US?
2. **If go with conditions:** what minimum disclaimers, TOS clauses, and customer-verification steps are required? E.g.,
    - Accredited-investor self-cert at signup
    - Terms of service clauses (not-advice, no-warranty, own-risk)
    - Dashboard footer disclaimers
    - Marketing copy restrictions (landing page, X posts, blog)
3. **If no-go:** what structural changes would be required to make it operable? E.g.,
    - CTA registration + exemptions
    - Limit to subscribers who certify $1M+ book
    - Strip "edge" and "confidence" fields; publish raw prices only
    - Move entity offshore
4. **Polymarket-specific risk.** Does publishing signals that reference Polymarket ticker pairs create additional legal risk given Polymarket's US-IP block? Are we facilitating customer violations of Polymarket's TOS / US law?
5. **Testimonials / case studies.** Once we have paying design partners (spec §10 week 2–10), can we publish anonymized usage patterns or "customer X saw Y% improvement"? What are the rules?
6. **State-level variance.** Any states where this product would need additional registration regardless of federal clearance? (NY BitLicense angle if crypto-adjacent is read broadly; CA "financial adviser" state registration thresholds.)

---

## Disclaimers draft (for counsel to sanity-check)

This is the current working draft. Probably needs rework.

**Landing page (`remembr.dev/feeds/arb`):**

> remembr.dev Arb Signal Feed provides data on observed price spreads between prediction-market venues for informational purposes only. Nothing herein is investment advice, an offer to buy or sell any security, or a recommendation of any trade. Past performance on our demonstration account does not guarantee future results. Prediction-market trading carries significant risk of loss. Subscribers are responsible for their own trading decisions, legal compliance in their jurisdiction, and access to the underlying venues. remembr.dev is not a registered investment adviser or commodity trading advisor.

**Dashboard (`remembr.dev/feeds/arb/live`):**

> PnL shown is for a personal trading account operated by the remembr.dev team, funded with $11,000 USD. Realized and unrealized losses are shown in full. This track record is not a forward-looking projection, not representative of what any subscriber would earn, and not a promise of future performance.

**Subscriber API response (HTTP header on every response):**

```
X-Disclaimer: informational-only / not-investment-advice / see-tos
```

**Terms of service (referenced during Stripe checkout):**

> [...] Subscriber acknowledges that (a) Signal Feed data is informational and does not constitute investment advice; (b) remembr.dev is not a registered investment adviser, commodity trading advisor, or broker-dealer; (c) Subscriber is solely responsible for trading decisions, venue account access, and legal compliance in their jurisdiction; (d) any trading, if conducted, is at Subscriber's own risk and with Subscriber's own capital via Subscriber's own accounts; (e) remembr.dev does not have custody of Subscriber funds, access to Subscriber brokerage credentials, or ability to place trades on Subscriber's behalf [...]

---

## Timeline

| Week | Action | Owner |
|---|---|---|
| 1 (2026-04-15, today) | Send this draft + factual context to external counsel; get scoping call | mspeicher |
| 2–3 | First-round counsel feedback; iterate hypotheses H1–H5 | counsel + mspeicher |
| 4–6 | Second round — refine disclaimers, TOS, dashboard copy | counsel + mspeicher |
| 7–8 | Final sign-off memo at `docs/compliance/signals-memo.md` | counsel |
| 9–10 | Integrate approved disclaimers into frontend + API + Stripe checkout | engineering |
| 11 | Paid tier opens on `remembr.dev` | — |

Slippage risk: 3 weeks. If counsel response times exceed 1 week for rounds 1 or 2, escalate to alternate firm or reshape product.

## Escalation if counsel returns red

If H1 is rejected (this IS regulated advice):
- Option 1: Strip "edge_cents" and "confidence" fields from the feed payload; publish raw spread data only. Shifts interpretation burden entirely to subscriber. May survive H1 but is a product-scope change.
- Option 2: Change audience to verified accredited investors only. Friction + smaller TAM.
- Option 3: Incorporate as a CTA, register with NFA. 6+ months of lead time and ongoing compliance cost.
- Option 4: Move entity offshore. Practical only if US customers aren't addressable — probably disqualifies the whole product.
- Option 5: Pivot off the signals thesis entirely; sell Agent Auth API as the primary revenue product. (Per [revenue-roadmap.md §C2](../plans/revenue-roadmap.md) alternate.)

## Notes

- Nothing in this memo is itself legal advice. It's a working draft prepared by an engineer for review by qualified counsel.
- Counsel should be experienced in CFTC derivatives rules AND (separately) SEC adviser rules. If one firm doesn't cover both, use two.
- Keep this memo checked into the repo so the decision trail is auditable if regulators ever ask.
