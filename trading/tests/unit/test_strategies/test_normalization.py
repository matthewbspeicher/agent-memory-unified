from __future__ import annotations
from datetime import datetime, timezone
import pytest
from broker.models import PredictionContract
from strategies.normalization import normalize_contract, compute_confidence, NormalizedContract


def _close() -> datetime:
    return datetime(2026, 6, 1, tzinfo=timezone.utc)


class TestNormalizedContract:
    def test_kalshi_with_bid_and_ask(self):
        c = PredictionContract(
            ticker="K1", title="Test", category="politics", close_time=_close(),
            yes_bid=48, yes_ask=52, yes_last=50, volume_24h=1000,
        )
        n = normalize_contract(c, platform="kalshi")
        assert n.mid_prob == pytest.approx(0.50)
        assert n.bid_prob == pytest.approx(0.48)
        assert n.ask_prob == pytest.approx(0.52)
        assert n.spread_prob == pytest.approx(0.04)

    def test_kalshi_mid_fallback_to_last(self):
        c = PredictionContract(
            ticker="K1", title="Test", category="politics", close_time=_close(),
            yes_bid=None, yes_ask=None, yes_last=55, volume_24h=500,
        )
        n = normalize_contract(c, platform="kalshi")
        assert n.mid_prob == pytest.approx(0.55)
        assert n.bid_prob is None
        assert n.ask_prob is None
        assert n.spread_prob is None

    def test_polymarket_bid_only(self):
        c = PredictionContract(
            ticker="P1", title="Test", category="crypto", close_time=_close(),
            yes_bid=62, yes_ask=None, yes_last=None, volume_24h=10000,
        )
        n = normalize_contract(c, platform="polymarket")
        assert n.mid_prob == pytest.approx(0.62)
        assert n.ask_prob is None
        assert n.spread_prob is None

    def test_kalshi_volume_usd_uses_mid(self):
        c = PredictionContract(
            ticker="K1", title="Test", category="economics", close_time=_close(),
            yes_bid=40, yes_ask=60, volume_24h=200,
        )
        n = normalize_contract(c, platform="kalshi")
        # volume_usd = contracts * mid_price = 200 * 0.50 = 100
        assert n.volume_usd_24h == pytest.approx(100.0)

    def test_polymarket_volume_usd_passthrough(self):
        c = PredictionContract(
            ticker="P1", title="Test", category="crypto", close_time=_close(),
            yes_bid=70, volume_24h=5000,
        )
        n = normalize_contract(c, platform="polymarket")
        assert n.volume_usd_24h == pytest.approx(5000.0)

    def test_liquidity_score_capped_at_one(self):
        c = PredictionContract(
            ticker="K1", title="Test", category="politics", close_time=_close(),
            yes_bid=49, yes_ask=51, volume_24h=10_000_000,
        )
        n = normalize_contract(c, platform="kalshi")
        assert n.liquidity_score <= 1.0

    def test_liquidity_score_nonnegative(self):
        c = PredictionContract(
            ticker="K1", title="Test", category="politics", close_time=_close(),
            yes_bid=10, volume_24h=0,
        )
        n = normalize_contract(c, platform="kalshi")
        assert n.liquidity_score >= 0.0

    def test_volume_usd_zero_when_no_quotes(self):
        """Kalshi contracts with no bid/ask should report volume_usd=0, not volume*0.5."""
        from datetime import timedelta
        c = PredictionContract(
            ticker="KTEST", title="Test", category="politics",
            close_time=datetime.now(timezone.utc) + timedelta(days=10),
            yes_bid=None, yes_ask=None, yes_last=None, volume_24h=10_000,
        )
        norm = normalize_contract(c, platform="kalshi")
        assert norm.volume_usd_24h == 0.0


class TestComputeConfidence:
    def test_large_gap_liquid_near_max(self):
        from strategies.normalization import NormalizedContract
        from datetime import datetime, timezone

        def _n(mid: float, liq: float) -> NormalizedContract:
            return NormalizedContract(
                ticker="X", platform="kalshi", title="T", category="politics",
                close_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
                mid_prob=mid, bid_prob=None, ask_prob=None, spread_prob=None,
                volume_usd_24h=10000.0, liquidity_score=liq,
            )

        k = _n(0.40, 1.0)
        p = _n(0.70, 1.0)
        conf = compute_confidence(gap_cents=30, k_norm=k, p_norm=p)
        assert conf <= 0.9
        assert conf > 0.5

    def test_small_gap_low_liquidity_low_confidence(self):
        from strategies.normalization import NormalizedContract
        from datetime import datetime, timezone

        def _n(liq: float) -> NormalizedContract:
            return NormalizedContract(
                ticker="X", platform="kalshi", title="T", category="politics",
                close_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
                mid_prob=0.5, bid_prob=None, ask_prob=None, spread_prob=None,
                volume_usd_24h=10.0, liquidity_score=liq,
            )

        conf = compute_confidence(gap_cents=3, k_norm=_n(0.05), p_norm=_n(0.05))
        assert conf < 0.2

    def test_confidence_never_exceeds_0_9(self):
        from strategies.normalization import NormalizedContract
        from datetime import datetime, timezone

        def _n() -> NormalizedContract:
            return NormalizedContract(
                ticker="X", platform="polymarket", title="T", category="crypto",
                close_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
                mid_prob=0.1, bid_prob=None, ask_prob=None, spread_prob=None,
                volume_usd_24h=1_000_000.0, liquidity_score=1.0,
            )

        conf = compute_confidence(gap_cents=100, k_norm=_n(), p_norm=_n())
        assert conf <= 0.9
