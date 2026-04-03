"""Unit tests for ResolutionTracker."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from broker.models import Symbol, AssetType, Position


def _make_position(ticker: str, qty: float = 10.0, avg_cost: float = 0.60) -> Position:
    return Position(
        symbol=Symbol(ticker=ticker, asset_type=AssetType.PREDICTION),
        quantity=Decimal(str(qty)),
        avg_cost=Decimal(str(avg_cost)),
        market_value=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
    )


class TestResolutionTrackerKalshi:
    @pytest.fixture
    def tracker(self):
        from exits.resolution_tracker import ResolutionTracker
        kalshi_client = MagicMock()
        kalshi_paper = MagicMock()
        kalshi_paper.resolve_contract = AsyncMock()
        paper_store = MagicMock()
        paper_store.get_positions = AsyncMock(return_value=[
            _make_position("KXBTCD-25MAR28")
        ])
        return ResolutionTracker(
            kalshi_client=kalshi_client,
            polymarket_client=None,
            kalshi_paper_broker=kalshi_paper,
            polymarket_paper_broker=None,
            paper_store=paper_store,
        )

    @pytest.mark.asyncio
    async def test_finalized_yes_calls_resolve(self, tracker):
        tracker._kalshi_client.get_market = AsyncMock(return_value={
            "status": "finalized",
            "result": "yes",
        })
        await tracker._settle_kalshi()
        tracker._kalshi_paper.resolve_contract.assert_called_once()
        call_kwargs = tracker._kalshi_paper.resolve_contract.call_args.kwargs
        assert call_kwargs["resolution"] == "YES"

    @pytest.mark.asyncio
    async def test_finalized_no_calls_resolve(self, tracker):
        tracker._kalshi_client.get_market = AsyncMock(return_value={
            "status": "finalized",
            "result": "no",
        })
        await tracker._settle_kalshi()
        tracker._kalshi_paper.resolve_contract.assert_called_once()
        call_kwargs = tracker._kalshi_paper.resolve_contract.call_args.kwargs
        assert call_kwargs["resolution"] == "NO"

    @pytest.mark.asyncio
    async def test_finalized_void_maps_to_cancelled(self, tracker):
        tracker._kalshi_client.get_market = AsyncMock(return_value={
            "status": "finalized",
            "result": "void",
        })
        await tracker._settle_kalshi()
        call_kwargs = tracker._kalshi_paper.resolve_contract.call_args.kwargs
        assert call_kwargs["resolution"] == "CANCELLED"

    @pytest.mark.asyncio
    async def test_open_market_no_resolve(self, tracker):
        tracker._kalshi_client.get_market = AsyncMock(return_value={
            "status": "open",
            "result": "",
        })
        await tracker._settle_kalshi()
        tracker._kalshi_paper.resolve_contract.assert_not_called()

    @pytest.mark.asyncio
    async def test_event_bus_publish_on_resolution(self, tracker):
        event_bus = MagicMock()
        event_bus.publish = AsyncMock()
        tracker._event_bus = event_bus
        tracker._kalshi_client.get_market = AsyncMock(return_value={
            "status": "finalized",
            "result": "yes",
        })
        await tracker._settle_kalshi()
        event_bus.publish.assert_called_once_with("market_resolved", {
            "broker": "kalshi",
            "ticker": "KXBTCD-25MAR28",
            "resolution": "YES",
        })

    @pytest.mark.asyncio
    async def test_no_positions_no_calls(self, tracker):
        tracker._paper_store.get_positions = AsyncMock(return_value=[])
        await tracker._settle_kalshi()
        tracker._kalshi_paper.resolve_contract.assert_not_called()


class TestResolutionTrackerPolymarket:
    @pytest.fixture
    def tracker(self):
        from exits.resolution_tracker import ResolutionTracker
        poly_client = MagicMock()
        poly_paper = MagicMock()
        poly_paper.resolve_contract = AsyncMock()
        paper_store = MagicMock()
        paper_store.get_positions = AsyncMock(return_value=[
            _make_position("token-abc123")
        ])
        return ResolutionTracker(
            kalshi_client=None,
            polymarket_client=poly_client,
            kalshi_paper_broker=None,
            polymarket_paper_broker=poly_paper,
            paper_store=paper_store,
        )

    @pytest.mark.asyncio
    async def test_resolved_yes_token_calls_yes(self, tracker):
        tracker._poly_client.get_market = MagicMock(return_value={
            "closed": True,
            "resolved": True,
            "winning_outcomes": ["token-abc123"],
        })
        await tracker._settle_polymarket()
        tracker._poly_paper.resolve_contract.assert_called_once()
        call_kwargs = tracker._poly_paper.resolve_contract.call_args.kwargs
        assert call_kwargs["resolution"] == "YES"

    @pytest.mark.asyncio
    async def test_resolved_token_not_in_winning_calls_no(self, tracker):
        tracker._poly_client.get_market = MagicMock(return_value={
            "closed": True,
            "resolved": True,
            "winning_outcomes": ["other-token"],
        })
        await tracker._settle_polymarket()
        call_kwargs = tracker._poly_paper.resolve_contract.call_args.kwargs
        assert call_kwargs["resolution"] == "NO"

    @pytest.mark.asyncio
    async def test_not_closed_no_resolve(self, tracker):
        tracker._poly_client.get_market = MagicMock(return_value={
            "closed": False,
            "resolved": False,
        })
        await tracker._settle_polymarket()
        tracker._poly_paper.resolve_contract.assert_not_called()
