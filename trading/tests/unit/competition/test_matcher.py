# tests/unit/competition/test_matcher.py
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from competition.matcher import MatchProcessor, MatchResult
from competition.tracker import TrackedSignal


class MockCompetitionStore:
    def __init__(self):
        self._elos: dict[tuple[str, str], int] = {}
        self._updates: list[dict] = []
        self._competitors: dict[str, dict] = {}
        self._matches_recorded: list[dict] = []

    async def get_elo(self, competitor_id: str, asset: str) -> int:
        return self._elos.get((competitor_id, asset), 1000)

    async def update_elo(
        self, competitor_id: str, asset: str, new_elo: int, elo_delta: int
    ) -> None:
        self._elos[(competitor_id, asset)] = new_elo
        self._updates.append(
            {"id": competitor_id, "asset": asset, "elo": new_elo, "delta": elo_delta}
        )

    async def get_competitor_by_ref(self, comp_type: str, ref_id: str) -> dict | None:
        return self._competitors.get(ref_id)

    async def record_match(self, match_data: dict) -> None:
        self._matches_recorded.append(match_data)

    def seed_competitor(self, ref_id: str, comp_id: str, elo: int = 1000) -> None:
        self._competitors[ref_id] = {"id": comp_id, "type": "agent", "ref_id": ref_id}
        self._elos[(comp_id, "BTC")] = elo


class MockPriceFetcher:
    def __init__(self, prices: dict[tuple[str, datetime], float] | None = None):
        self._prices = prices or {}
        self.default_price = 50000.0

    async def get_price(self, asset: str, at: datetime) -> float | None:
        return self._prices.get((asset, at), self.default_price)


class TestMatchProcessor:
    @pytest.mark.asyncio
    async def test_baseline_match_win(self):
        store = MockCompetitionStore()
        store.seed_competitor("rsi_scanner", "comp-1", elo=1000)
        fetcher = MockPriceFetcher()
        now = datetime.now(timezone.utc)

        processor = MatchProcessor(store=store, price_fetcher=fetcher)
        signal = TrackedSignal(
            source_agent="rsi_scanner",
            asset="BTC",
            direction="long",
            confidence=0.8,
            timestamp=now,
        )
        result = processor.evaluate_signal(
            signal, price_at_signal=50000.0, price_at_eval=50500.0
        )
        assert result.correct is True
        assert result.return_pct > 0

    @pytest.mark.asyncio
    async def test_baseline_match_loss(self):
        processor = MatchProcessor(
            store=MockCompetitionStore(), price_fetcher=MockPriceFetcher()
        )
        signal = TrackedSignal(
            source_agent="rsi_scanner",
            asset="BTC",
            direction="long",
            confidence=0.7,
            timestamp=datetime.now(timezone.utc),
        )
        result = processor.evaluate_signal(
            signal, price_at_signal=50000.0, price_at_eval=49500.0
        )
        assert result.correct is False
        assert result.return_pct < 0

    @pytest.mark.asyncio
    async def test_short_signal_correct_on_drop(self):
        processor = MatchProcessor(
            store=MockCompetitionStore(), price_fetcher=MockPriceFetcher()
        )
        signal = TrackedSignal(
            source_agent="rsi_scanner",
            asset="BTC",
            direction="short",
            confidence=0.6,
            timestamp=datetime.now(timezone.utc),
        )
        result = processor.evaluate_signal(
            signal, price_at_signal=50000.0, price_at_eval=49000.0
        )
        assert result.correct is True

    def test_pairwise_window_detection(self):
        processor = MatchProcessor(
            store=MockCompetitionStore(), price_fetcher=MockPriceFetcher()
        )
        now = datetime.now(timezone.utc)
        signals = [
            TrackedSignal("agent_a", "BTC", "long", 0.8, now),
            TrackedSignal("agent_b", "BTC", "short", 0.7, now + timedelta(minutes=3)),
            TrackedSignal("agent_c", "ETH", "long", 0.9, now),  # different asset
            TrackedSignal(
                "agent_d", "BTC", "long", 0.6, now + timedelta(minutes=10)
            ),  # outside window
        ]
        pairs = processor.find_pairwise_matches(signals, window_minutes=5)
        # Only agent_a and agent_b are within 5min on same asset
        assert len(pairs) == 1
        assert {pairs[0][0].source_agent, pairs[0][1].source_agent} == {
            "agent_a",
            "agent_b",
        }
