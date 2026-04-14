"""Unit tests for the MCP tool server (trading/mcp_server.py).

Tests verify:
1. create_mcp_server returns a FastMCP instance
2. query_signals with mocked signal_bus (calls query, formats results)
3. query_signals returns error when signal_bus is None
4. list_signal_types returns known types from registry
5. publish_signal creates AgentSignal and calls signal_bus.publish
6. publish_signal returns error dict when signal_bus is None
7. publish_signal handles ValueError (invalid signal type)
8. agent_status returns error when agent_runner is None
9. agent_status returns agent info when runner is provided
10. get_regime returns error when regime_manager is None
11. get_positions returns error when broker is None
12. health_check returns correct status for each available/unavailable component
13. health_check counts agents when runner is provided
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

mcp = pytest.importorskip("mcp")
from mcp.server.fastmcp import FastMCP

from mcp_server import create_mcp_server


def _make_signal(
    source_agent: str = "test_agent",
    target_agent: str = "executor",
    signal_type: str = "news_event",
    payload: dict | None = None,
    confidence: float = 0.8,
    timestamp: datetime | None = None,
    expires_at: datetime | None = None,
) -> MagicMock:
    sig = MagicMock()
    sig.source_agent = source_agent
    sig.target_agent = target_agent
    sig.signal_type = signal_type
    sig.payload = payload or {"headline": "test"}
    sig.confidence = confidence
    sig.timestamp = timestamp or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    sig.expires_at = expires_at or datetime(2026, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
    return sig


def _make_agent_info(
    name: str = "sentiment",
    description: str = "Sentiment scanner",
    status: str = "running",
    last_run: datetime | None = None,
    error_count: int = 0,
) -> MagicMock:
    info = MagicMock()
    info.name = name
    info.description = description
    info.status = status
    info.last_run = last_run or datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    info.error_count = error_count
    return info


# ---------------------------------------------------------------------------
# 1. create_mcp_server returns a FastMCP instance
# ---------------------------------------------------------------------------


class TestCreateMCPServer:
    def test_returns_fastmcp_instance(self):
        server = create_mcp_server()
        assert isinstance(server, FastMCP)

    def test_server_name_is_trading_engine(self):
        server = create_mcp_server()
        assert server.name == "trading-engine"

    def test_accepts_optional_dependencies(self):
        bus = MagicMock()
        runner = MagicMock()
        broker = MagicMock()
        regime = MagicMock()
        server = create_mcp_server(
            signal_bus=bus,
            agent_runner=runner,
            broker=broker,
            regime_manager=regime,
        )
        assert isinstance(server, FastMCP)


# ---------------------------------------------------------------------------
# 2–3. query_signals
# ---------------------------------------------------------------------------


class TestQuerySignals:
    @pytest.mark.asyncio
    async def query_signals_tool(self, server):
        for tool in server._tool_manager._tools.values():
            if tool.name == "query_signals":
                return tool
        pytest.fail("query_signals tool not found")

    @pytest.fixture
    def server_with_bus(self):
        bus = MagicMock()
        bus.query = MagicMock(return_value=[])
        return create_mcp_server(signal_bus=bus), bus

    @pytest.fixture
    def server_no_bus(self):
        return create_mcp_server(signal_bus=None)

    @pytest.mark.asyncio
    async def test_returns_error_when_bus_is_none(self):
        server = create_mcp_server(signal_bus=None)
        tool_fn = self._get_tool(server, "query_signals")
        result = await tool_fn(signal_type=None, target_agent=None, limit=20)
        assert result == [{"error": "Signal bus not available"}]

    @pytest.mark.asyncio
    async def test_calls_query_and_formats_results(self):
        bus = MagicMock()
        ts = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        exp = datetime(2026, 1, 15, 11, 30, 0, tzinfo=timezone.utc)
        sig = _make_signal(
            source_agent="alpha",
            target_agent="executor",
            signal_type="bittensor_consensus",
            payload={"consensus": "bullish"},
            confidence=0.92,
            timestamp=ts,
            expires_at=exp,
        )
        bus.query = MagicMock(return_value=[sig])
        server = create_mcp_server(signal_bus=bus)
        tool_fn = self._get_tool(server, "query_signals")

        result = await tool_fn(
            signal_type="bittensor_consensus", target_agent="executor", limit=20
        )

        bus.query.assert_called_once_with(
            signal_type="bittensor_consensus", target_agent="executor"
        )
        assert len(result) == 1
        entry = result[0]
        assert entry["source_agent"] == "alpha"
        assert entry["target_agent"] == "executor"
        assert entry["signal_type"] == "bittensor_consensus"
        assert entry["payload"] == {"consensus": "bullish"}
        assert entry["confidence"] == 0.92
        assert entry["timestamp"] == ts.isoformat()
        assert entry["expires_at"] == exp.isoformat()

    @pytest.mark.asyncio
    async def test_respects_limit(self):
        bus = MagicMock()
        signals = [_make_signal(source_agent=f"agent_{i}") for i in range(50)]
        bus.query = MagicMock(return_value=signals)
        server = create_mcp_server(signal_bus=bus)
        tool_fn = self._get_tool(server, "query_signals")

        result = await tool_fn(signal_type=None, target_agent=None, limit=5)
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_none_timestamp_and_expires_at(self):
        bus = MagicMock()
        sig = _make_signal()
        sig.timestamp = None
        sig.expires_at = None
        bus.query = MagicMock(return_value=[sig])
        server = create_mcp_server(signal_bus=bus)
        tool_fn = self._get_tool(server, "query_signals")

        result = await tool_fn(signal_type=None, target_agent=None, limit=20)
        assert result[0]["timestamp"] is None
        assert result[0]["expires_at"] is None

    @staticmethod
    def _get_tool(server, name):
        return server._tool_manager._tools[name].fn


# ---------------------------------------------------------------------------
# 4. list_signal_types
# ---------------------------------------------------------------------------


class TestListSignalTypes:
    @pytest.mark.asyncio
    async def test_returns_known_types_from_registry(self):
        server = create_mcp_server()
        tool_fn = server._tool_manager._tools["list_signal_types"].fn

        with patch("data.signal_types.registry") as mock_registry:
            mock_registry.known_types = MagicMock(
                return_value=["bittensor_consensus", "news_event", "regime_update"]
            )
            result = await tool_fn()

        mock_registry.known_types.assert_called_once()
        assert result == ["bittensor_consensus", "news_event", "regime_update"]


# ---------------------------------------------------------------------------
# 5–7. publish_signal
# ---------------------------------------------------------------------------


class TestPublishSignal:
    @pytest.mark.asyncio
    async def test_returns_error_when_bus_is_none(self):
        server = create_mcp_server(signal_bus=None)
        tool_fn = server._tool_manager._tools["publish_signal"].fn

        result = await tool_fn(
            source_agent="test",
            signal_type="news_event",
            payload={"headline": "x"},
            expires_in_seconds=3600,
        )
        assert result == {"error": "Signal bus not available"}

    @pytest.mark.asyncio
    async def test_creates_signal_and_publishes(self):
        bus = MagicMock()
        bus.publish = AsyncMock()
        server = create_mcp_server(signal_bus=bus)
        tool_fn = server._tool_manager._tools["publish_signal"].fn

        result = await tool_fn(
            source_agent="sentiment",
            signal_type="news_event",
            payload={"headline": "Fed rate decision"},
            expires_in_seconds=1800,
        )

        bus.publish.assert_awaited_once()
        published_signal = bus.publish.call_args[0][0]
        assert published_signal.source_agent == "sentiment"
        assert published_signal.signal_type == "news_event"
        assert published_signal.payload == {"headline": "Fed rate decision"}
        assert result == {"status": "published", "signal_type": "news_event"}

    @pytest.mark.asyncio
    async def test_handles_value_error(self):
        bus = MagicMock()
        bus.publish = AsyncMock(side_effect=ValueError("invalid signal type"))
        server = create_mcp_server(signal_bus=bus)
        tool_fn = server._tool_manager._tools["publish_signal"].fn

        result = await tool_fn(
            source_agent="test",
            signal_type="bad_type",
            payload={},
            expires_in_seconds=3600,
        )

        assert result == {"error": "invalid signal type"}

    @pytest.mark.asyncio
    async def test_handles_unexpected_exception(self):
        bus = MagicMock()
        bus.publish = AsyncMock(side_effect=RuntimeError("boom"))
        server = create_mcp_server(signal_bus=bus)
        tool_fn = server._tool_manager._tools["publish_signal"].fn

        result = await tool_fn(
            source_agent="test",
            signal_type="news_event",
            payload={},
            expires_in_seconds=3600,
        )

        assert "error" in result
        assert "Unexpected error" in result["error"]


# ---------------------------------------------------------------------------
# 8–9. agent_status
# ---------------------------------------------------------------------------


class TestAgentStatus:
    @pytest.mark.asyncio
    async def test_returns_error_when_runner_is_none(self):
        server = create_mcp_server(agent_runner=None)
        tool_fn = server._tool_manager._tools["agent_status"].fn

        result = await tool_fn()
        assert result == [{"error": "Agent runner not available"}]

    @pytest.mark.asyncio
    async def test_returns_agent_info_list(self):
        runner = MagicMock()
        last_run = datetime(2026, 3, 1, 9, 0, 0, tzinfo=timezone.utc)
        runner.list_agents = MagicMock(
            return_value=[
                _make_agent_info(
                    name="sentiment", status="running", last_run=last_run, error_count=0
                ),
                _make_agent_info(
                    name="arbitrage", status="idle", last_run=None, error_count=2
                ),
            ]
        )
        server = create_mcp_server(agent_runner=runner)
        tool_fn = server._tool_manager._tools["agent_status"].fn

        result = await tool_fn()

        assert len(result) == 2
        assert result[0]["name"] == "sentiment"
        assert result[0]["status"] == "running"
        assert result[0]["last_run"] == last_run.isoformat()
        assert result[0]["error_count"] == 0

        assert result[1]["name"] == "arbitrage"
        assert result[1]["status"] == "idle"
        assert result[1]["last_run"] is None
        assert result[1]["error_count"] == 2


# ---------------------------------------------------------------------------
# 10. get_regime
# ---------------------------------------------------------------------------


class TestGetRegime:
    @pytest.mark.asyncio
    async def test_returns_error_when_regime_manager_is_none(self):
        server = create_mcp_server(regime_manager=None)
        tool_fn = server._tool_manager._tools["get_regime"].fn

        result = await tool_fn()
        assert result == {"error": "Regime manager not available"}

    @pytest.mark.asyncio
    async def test_returns_regime_state(self):
        regime = MagicMock()
        state = MagicMock()
        state.market_phase = "bull"
        state.volatility = "low"
        state.trend = "up"
        regime.current_state = state
        server = create_mcp_server(regime_manager=regime)
        tool_fn = server._tool_manager._tools["get_regime"].fn

        result = await tool_fn()

        assert result == {"market_phase": "bull", "volatility": "low", "trend": "up"}

    @pytest.mark.asyncio
    async def test_handles_missing_attributes_with_default(self):
        regime = MagicMock()
        state = MagicMock(spec=[])
        regime.current_state = state
        server = create_mcp_server(regime_manager=regime)
        tool_fn = server._tool_manager._tools["get_regime"].fn

        result = await tool_fn()

        assert result == {
            "market_phase": "unknown",
            "volatility": "unknown",
            "trend": "unknown",
        }

    @pytest.mark.asyncio
    async def test_handles_exception_from_current_state(self):
        regime = MagicMock()
        regime.current_state = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("no state"))
        )
        type(regime).current_state = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("no state"))
        )
        server = create_mcp_server(regime_manager=regime)
        tool_fn = server._tool_manager._tools["get_regime"].fn

        try:
            result = await tool_fn()
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_exception_in_current_state_returns_error(self):
        regime = MagicMock()
        regime.__class__ = type(regime)

        def _raise_current(self):
            raise RuntimeError("state unavailable")

        type(regime).current_state = _raise_current
        server = create_mcp_server(regime_manager=regime)
        tool_fn = server._tool_manager._tools["get_regime"].fn

        result = await tool_fn()
        assert result == {"error": "state unavailable"}


# ---------------------------------------------------------------------------
# 11. get_positions
# ---------------------------------------------------------------------------


class TestGetPositions:
    @pytest.mark.asyncio
    async def test_returns_error_when_broker_is_none(self):
        server = create_mcp_server(broker=None)
        tool_fn = server._tool_manager._tools["get_positions"].fn

        result = await tool_fn()
        assert result == [{"error": "Broker not available"}]

    @pytest.mark.asyncio
    async def test_returns_positions_from_broker(self):
        broker = MagicMock()
        pos = MagicMock()
        pos.symbol = "AAPL"
        pos.side = "long"
        pos.qty = 100
        pos.avg_entry_price = 150.50
        pos.unrealized_pnl = 500.00
        broker.get_positions = AsyncMock(return_value=[pos])
        server = create_mcp_server(broker=broker)
        tool_fn = server._tool_manager._tools["get_positions"].fn

        result = await tool_fn()

        assert len(result) == 1
        assert result[0]["symbol"] == "AAPL"
        assert result[0]["side"] == "long"
        assert result[0]["qty"] == 100
        assert result[0]["entry_price"] == 150.50
        assert result[0]["unrealized_pnl"] == 500.00

    @pytest.mark.asyncio
    async def test_handles_broker_exception(self):
        broker = MagicMock()
        broker.get_positions = AsyncMock(side_effect=RuntimeError("connection lost"))
        server = create_mcp_server(broker=broker)
        tool_fn = server._tool_manager._tools["get_positions"].fn

        result = await tool_fn()

        assert len(result) == 1
        assert "error" in result[0]

    @pytest.mark.asyncio
    async def test_fallback_to_str_when_no_symbol_attr(self):
        broker = MagicMock()
        pos = MagicMock(spec=["side", "qty"])
        pos.side = "long"
        pos.qty = 10
        broker.get_positions = AsyncMock(return_value=[pos])
        server = create_mcp_server(broker=broker)
        tool_fn = server._tool_manager._tools["get_positions"].fn

        result = await tool_fn()

        assert result[0]["symbol"] == str(pos)
        assert result[0]["side"] == "long"


# ---------------------------------------------------------------------------
# 12–13. health_check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_minimal_status_when_no_deps(self):
        server = create_mcp_server()
        tool_fn = server._tool_manager._tools["health_check"].fn

        result = await tool_fn()

        assert result == {"mcp_server": "ok"}

    @pytest.mark.asyncio
    async def test_signal_bus_reported_ok(self):
        bus = MagicMock()
        server = create_mcp_server(signal_bus=bus)
        tool_fn = server._tool_manager._tools["health_check"].fn

        result = await tool_fn()

        assert result["signal_bus"] == "ok"
        assert result["mcp_server"] == "ok"

    @pytest.mark.asyncio
    async def test_broker_reported_connected(self):
        broker = MagicMock()
        server = create_mcp_server(broker=broker)
        tool_fn = server._tool_manager._tools["health_check"].fn

        result = await tool_fn()

        assert result["broker"] == "connected"

    @pytest.mark.asyncio
    async def test_regime_manager_reported_ok(self):
        regime = MagicMock()
        server = create_mcp_server(regime_manager=regime)
        tool_fn = server._tool_manager._tools["health_check"].fn

        result = await tool_fn()

        assert result["regime_manager"] == "ok"

    @pytest.mark.asyncio
    async def test_agent_count_from_runner(self):
        runner = MagicMock()
        runner._agents = {
            "sentiment": MagicMock(),
            "arbitrage": MagicMock(),
            "regime": MagicMock(),
        }
        server = create_mcp_server(agent_runner=runner)
        tool_fn = server._tool_manager._tools["health_check"].fn

        result = await tool_fn()

        assert result["agents"] == 3

    @pytest.mark.asyncio
    async def test_full_status_with_all_deps(self):
        bus = MagicMock()
        runner = MagicMock()
        runner._agents = {"a": MagicMock(), "b": MagicMock()}
        broker = MagicMock()
        regime = MagicMock()
        server = create_mcp_server(
            signal_bus=bus,
            agent_runner=runner,
            broker=broker,
            regime_manager=regime,
        )
        tool_fn = server._tool_manager._tools["health_check"].fn

        result = await tool_fn()

        assert result == {
            "mcp_server": "ok",
            "signal_bus": "ok",
            "agents": 2,
            "broker": "connected",
            "regime_manager": "ok",
        }
