# tests/unit/agents/test_funding_arb.py
from __future__ import annotations

from agents.adapters.funding_arb import FundingRateArbAdapter, FundingArbConfig
from data.sources.derivatives import FundingOISnapshot


class TestFundingCalculations:
    def test_net_funding_positive_rate(self):
        adapter = FundingRateArbAdapter(config=FundingArbConfig())
        # 100% annualized, fees ~43.8% annualized (0.0004 * 3 * 365)
        net = adapter.calculate_net_funding(1.0, "BTCUSD")
        assert net > 0.0  # Profitable after fees

    def test_net_funding_low_rate_unprofitable(self):
        adapter = FundingRateArbAdapter(
            config=FundingArbConfig(min_annualized_rate=0.20)
        )
        net = adapter.calculate_net_funding(0.05, "BTCUSD")
        # Below minimum threshold
        assert net < 0.20

    def test_net_funding_negative_disabled(self):
        adapter = FundingRateArbAdapter(
            config=FundingArbConfig(allow_negative_funding=False)
        )
        net = adapter.calculate_net_funding(-0.30, "BTCUSD")
        assert net == 0.0

    def test_net_funding_negative_enabled(self):
        adapter = FundingRateArbAdapter(
            config=FundingArbConfig(allow_negative_funding=True)
        )
        # With -50% rate: abs(0.50) - borrow(~7.3%) - fees(~43.8%) = ~39% net
        net = adapter.calculate_net_funding(-0.50, "BTCUSD")
        assert net > 0.0


class TestExchangeDivergence:
    def test_agreement_when_all_close(self):
        adapter = FundingRateArbAdapter(config=FundingArbConfig())
        snapshots = [
            FundingOISnapshot("BTC", "binance", 0.001, 1.095, 1e9, 0),
            FundingOISnapshot("BTC", "bybit", 0.0011, 1.2045, 1e9, 0),
            FundingOISnapshot("BTC", "okx", 0.00105, 1.14975, 1e9, 0),
        ]
        assert adapter.check_exchange_agreement(snapshots) is True

    def test_disagreement_when_outlier(self):
        adapter = FundingRateArbAdapter(config=FundingArbConfig())
        snapshots = [
            FundingOISnapshot("BTC", "binance", 0.001, 1.095, 1e9, 0),
            FundingOISnapshot("BTC", "bybit", 0.0001, 0.1095, 1e9, 0),  # 10x lower
        ]
        assert adapter.check_exchange_agreement(snapshots) is False

    def test_needs_minimum_exchanges(self):
        adapter = FundingRateArbAdapter(config=FundingArbConfig())
        snapshots = [FundingOISnapshot("BTC", "binance", 0.001, 1.095, 1e9, 0)]
        assert adapter.check_exchange_agreement(snapshots) is False


class TestSpikeDetection:
    def test_normal_rate_no_spike(self):
        adapter = FundingRateArbAdapter(config=FundingArbConfig(spike_threshold=1.0))
        assert adapter.is_spike(0.50) is False

    def test_extreme_rate_is_spike(self):
        adapter = FundingRateArbAdapter(config=FundingArbConfig(spike_threshold=1.0))
        assert adapter.is_spike(1.50) is True

    def test_spike_reduces_size(self):
        adapter = FundingRateArbAdapter(
            config=FundingArbConfig(spike_size_multiplier=0.5)
        )
        assert adapter.size_multiplier(annualized=1.5) == 0.5
        assert adapter.size_multiplier(annualized=0.3) == 1.0
