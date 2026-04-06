"""
Cross-platform arbitrage integration test.

Exercises: CrossPlatformArbAgent.scan() with both real KalshiDataSource and
PolymarketDataSource simultaneously.

Marked @pytest.mark.live_paper — not run in normal CI.
Requires:
  - STA_KALSHI_DEMO=true (Kalshi safety guard)
  - STA_POLYMARKET_DRY_RUN=true (Polymarket safety guard)
"""

from __future__ import annotations


import pytest

from tests.live_paper.conftest import skip_no_kalshi, skip_no_polymarket

pytestmark = [
    pytest.mark.live_paper,
]


def _make_agent(kalshi_ds, polymarket_ds):
    """Build a CrossPlatformArbAgent with injected data sources."""
    from agents.models import ActionLevel, AgentConfig
    from strategies.cross_platform_arb import CrossPlatformArbAgent

    config = AgentConfig(
        name="cross_platform_arb_test",
        strategy="cross_platform_arb",
        schedule="on_demand",
        action_level=ActionLevel.NOTIFY,
        parameters={
            "threshold_cents": 3,
            "min_match_similarity": 0.50,
            "kalshi_categories": ["economics", "politics"],
            "polymarket_tags": ["politics", "crypto"],
            "max_markets_per_platform": 20,
        },
    )
    return CrossPlatformArbAgent(
        config, kalshi_ds=kalshi_ds, polymarket_ds=polymarket_ds
    )


# ---------------------------------------------------------------------------
# Test — CrossPlatformArbAgent.scan() with both real data sources
# ---------------------------------------------------------------------------


@skip_no_kalshi
@skip_no_polymarket
@pytest.mark.timeout(90)
async def test_cross_platform_arb_scan(kalshi_client, polymarket_client):
    """
    CrossPlatformArbAgent.scan() queries both Kalshi demo and Polymarket CLOB,
    fuzzy-matches market titles across platforms, and returns a list of
    arbitrage Opportunities.

    The list may be empty — that is valid when no cross-platform title matches
    exceed both the similarity threshold and price gap threshold.  The test
    asserts structural correctness of whatever is returned.
    """
    from adapters.kalshi.data_source import KalshiDataSource
    from adapters.polymarket.data_source import PolymarketDataSource

    k_ds = KalshiDataSource(kalshi_client)
    p_ds = PolymarketDataSource(polymarket_client)

    agent = _make_agent(k_ds, p_ds)
    # CrossPlatformArbAgent.scan() takes any data argument (it ignores it,
    # relying on self.kalshi_ds / self.polymarket_ds instead).
    opportunities = await agent.scan(None)

    assert isinstance(opportunities, list)
    for opp in opportunities:
        assert opp.agent_name == "cross_platform_arb_test"
        assert opp.symbol is not None
        assert opp.broker_id in ("kalshi", "polymarket"), (
            f"Expected broker_id in (kalshi, polymarket), got {opp.broker_id!r}"
        )
        assert 0.0 <= opp.confidence <= 1.0
        data = opp.data
        assert "kalshi_ticker" in data
        assert "poly_ticker" in data
        assert "gap_cents" in data
        assert data["gap_cents"] > 0
