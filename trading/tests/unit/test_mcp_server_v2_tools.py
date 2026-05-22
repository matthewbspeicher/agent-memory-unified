"""Unit tests for the May-2026 MCP tool surface expansion.

Covers the 7 new read-only tools added to ``trading/mcp_server.py``:

    - get_intelligence_status
    - get_opportunities
    - get_journal_entries
    - get_brief
    - get_session_bias
    - get_sentiment
    - get_bittensor_status

Each tool fishes its dependency out of ``app_state``.  Tests verify both
the "not configured" path (returns an error dict) and the happy path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

mcp = pytest.importorskip("mcp")

from agents.models import AgentSignal
from data.signal_bus import SignalBus
from mcp_server import create_mcp_server


def _tool(server, name):
    return server._tool_manager._tools[name].fn


# ---------------------------------------------------------------------------
# get_intelligence_status
# ---------------------------------------------------------------------------


class TestGetIntelligenceStatus:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        server = create_mcp_server(app_state=SimpleNamespace())
        out = await _tool(server, "get_intelligence_status")()
        assert out == {"enabled": False, "status": "not_initialized"}

    @pytest.mark.asyncio
    async def test_returns_layer_status(self):
        layer = MagicMock()
        layer.get_status = MagicMock(return_value={"enabled": True, "enrichments_applied": 5})
        state = SimpleNamespace(intelligence_layer=layer)
        server = create_mcp_server(app_state=state)
        out = await _tool(server, "get_intelligence_status")()
        assert out == {"enabled": True, "enrichments_applied": 5}

    @pytest.mark.asyncio
    async def test_handles_exception(self):
        layer = MagicMock()
        layer.get_status = MagicMock(side_effect=RuntimeError("boom"))
        state = SimpleNamespace(intelligence_layer=layer)
        server = create_mcp_server(app_state=state)
        out = await _tool(server, "get_intelligence_status")()
        assert "error" in out


# ---------------------------------------------------------------------------
# get_opportunities
# ---------------------------------------------------------------------------


@dataclass
class _DummyOpp:
    id: str
    agent_name: str
    symbol: str
    signal: str


class TestGetOpportunities:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        server = create_mcp_server(app_state=SimpleNamespace())
        out = await _tool(server, "get_opportunities")()
        assert out == [{"error": "Opportunity store not available"}]

    @pytest.mark.asyncio
    async def test_returns_opps_as_dicts(self):
        store = MagicMock()
        store.list = AsyncMock(
            return_value=[
                _DummyOpp(id="o1", agent_name="rsi", symbol="AAPL", signal="BUY"),
                _DummyOpp(id="o2", agent_name="rsi", symbol="MSFT", signal="SELL"),
            ]
        )
        state = SimpleNamespace(opportunity_store=store)
        server = create_mcp_server(app_state=state)
        out = await _tool(server, "get_opportunities")(
            agent_name="rsi", limit=10
        )
        assert len(out) == 2
        assert out[0]["id"] == "o1"
        store.list.assert_awaited_once_with(
            agent_name="rsi", symbol=None, signal=None, limit=10
        )

    @pytest.mark.asyncio
    async def test_caps_limit(self):
        store = MagicMock()
        store.list = AsyncMock(return_value=[])
        state = SimpleNamespace(opportunity_store=store)
        server = create_mcp_server(app_state=state)
        await _tool(server, "get_opportunities")(limit=9999)
        # 200 is the cap
        assert store.list.call_args.kwargs["limit"] == 200

    @pytest.mark.asyncio
    async def test_handles_exception(self):
        store = MagicMock()
        store.list = AsyncMock(side_effect=RuntimeError("db down"))
        state = SimpleNamespace(opportunity_store=store)
        server = create_mcp_server(app_state=state)
        out = await _tool(server, "get_opportunities")()
        assert len(out) == 1 and "error" in out[0]


# ---------------------------------------------------------------------------
# get_journal_entries
# ---------------------------------------------------------------------------


@dataclass
class _JournalEntry:
    position_id: str
    agent_name: str
    has_autopsy: bool


class TestGetJournalEntries:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        server = create_mcp_server(app_state=SimpleNamespace())
        out = await _tool(server, "get_journal_entries")()
        assert out == [{"error": "Trade journal not configured"}]

    @pytest.mark.asyncio
    async def test_returns_entries(self):
        svc = MagicMock()
        svc.list_trades = AsyncMock(
            return_value=[
                _JournalEntry(position_id="p1", agent_name="rsi", has_autopsy=True),
            ]
        )
        state = SimpleNamespace(journal_service=svc)
        server = create_mcp_server(app_state=state)
        out = await _tool(server, "get_journal_entries")(agent="rsi", limit=5)
        assert len(out) == 1
        assert out[0]["position_id"] == "p1"
        svc.list_trades.assert_awaited_once_with(agent_name="rsi", limit=5)


# ---------------------------------------------------------------------------
# get_brief
# ---------------------------------------------------------------------------


class TestGetBrief:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        server = create_mcp_server(app_state=SimpleNamespace())
        out = await _tool(server, "get_brief")()
        assert "error" in out

    @pytest.mark.asyncio
    async def test_returns_brief(self):
        gen = MagicMock()
        gen.get_or_generate = AsyncMock(
            return_value={"date": "2026-05-22", "brief": "Markets calm."}
        )
        state = SimpleNamespace(brief_generator=gen)
        server = create_mcp_server(app_state=state)
        out = await _tool(server, "get_brief")()
        assert out["brief"] == "Markets calm."


# ---------------------------------------------------------------------------
# get_session_bias
# ---------------------------------------------------------------------------


class TestGetSessionBias:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        server = create_mcp_server(app_state=SimpleNamespace())
        out = await _tool(server, "get_session_bias")()
        assert "error" in out

    @pytest.mark.asyncio
    async def test_returns_stub_when_no_bias(self):
        gen = MagicMock()
        gen.get_active_bias = AsyncMock(return_value=None)
        state = SimpleNamespace(session_bias_generator=gen)
        server = create_mcp_server(app_state=state)
        out = await _tool(server, "get_session_bias")()
        assert out["bias"] is None

    @pytest.mark.asyncio
    async def test_returns_bias_dict(self):
        bias = MagicMock()
        bias.to_dict = MagicMock(return_value={"date": "2026-05-22", "bias": "bullish"})
        gen = MagicMock()
        gen.get_active_bias = AsyncMock(return_value=bias)
        state = SimpleNamespace(session_bias_generator=gen)
        server = create_mcp_server(app_state=state)
        out = await _tool(server, "get_session_bias")()
        assert out["bias"] == "bullish"


# ---------------------------------------------------------------------------
# get_sentiment (ADR-0011)
# ---------------------------------------------------------------------------


class TestGetSentiment:
    @pytest.mark.asyncio
    async def test_no_signal_bus(self):
        server = create_mcp_server()
        out = await _tool(server, "get_sentiment")(symbol="BTCUSD")
        assert "error" in out

    @pytest.mark.asyncio
    async def test_no_sentiment_for_symbol(self):
        bus = SignalBus()
        server = create_mcp_server(signal_bus=bus)
        out = await _tool(server, "get_sentiment")(symbol="BTCUSD")
        assert "error" in out and "no sentiment" in out["error"]

    @pytest.mark.asyncio
    async def test_returns_fresh_sentiment(self):
        bus = SignalBus()
        await bus.publish(
            AgentSignal(
                source_agent="intelligence_layer",
                signal_type="intel_sentiment",
                payload={
                    "symbol": "BTCUSD",
                    "score": 0.42,
                    "confidence": 0.7,
                    "sources": {"fear_greed_value": 30},
                },
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
        )
        server = create_mcp_server(signal_bus=bus)
        out = await _tool(server, "get_sentiment")(symbol="BTCUSD")
        assert out["score"] == 0.42
        assert out["sources"]["fear_greed_value"] == 30
        assert "age_seconds" in out

    @pytest.mark.asyncio
    async def test_rejects_stale(self):
        bus = SignalBus()
        sig = AgentSignal(
            source_agent="intelligence_layer",
            signal_type="intel_sentiment",
            payload={
                "symbol": "BTCUSD",
                "score": 0.1,
                "confidence": 0.5,
                "sources": {},
            },
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        await bus.publish(sig)
        # Backdate
        stored = bus.query(signal_type="intel_sentiment")[0]
        stored.timestamp = datetime.now(timezone.utc) - timedelta(seconds=1000)
        server = create_mcp_server(signal_bus=bus)
        out = await _tool(server, "get_sentiment")(symbol="BTCUSD", max_age_seconds=300)
        assert "error" in out and "stale" in out["error"]


# ---------------------------------------------------------------------------
# get_bittensor_status
# ---------------------------------------------------------------------------


class TestGetBittensorStatus:
    @pytest.mark.asyncio
    async def test_disabled(self):
        state = SimpleNamespace(bittensor_enabled_runtime=False)
        server = create_mcp_server(app_state=state)
        out = await _tool(server, "get_bittensor_status")()
        assert out == {"enabled": False}

    @pytest.mark.asyncio
    async def test_no_app_state(self):
        server = create_mcp_server()
        out = await _tool(server, "get_bittensor_status")()
        assert out == {"enabled": False}

    @pytest.mark.asyncio
    async def test_returns_summary(self):
        scheduler = SimpleNamespace(
            _running=True,
            _direct_query_enabled=False,
            last_window_miner_count=72,
            last_success_at=datetime(2026, 5, 22, 9, 0, tzinfo=timezone.utc),
        )
        bridge = SimpleNamespace(
            _running=True,
            last_poll_at=datetime(2026, 5, 22, 9, 30, tzinfo=timezone.utc),
            signals_emitted_total=128,
        )
        state = SimpleNamespace(
            bittensor_enabled_runtime=True,
            bittensor_scheduler=scheduler,
            bittensor_store=None,
            taoshi_bridge=bridge,
        )
        server = create_mcp_server(app_state=state)
        out = await _tool(server, "get_bittensor_status")()
        assert out["enabled"] is True
        assert out["scheduler_running"] is True
        assert out["miners_in_metagraph"] == 72
        assert out["taoshi_bridge_running"] is True
        assert out["taoshi_bridge_signal_count"] == 128
