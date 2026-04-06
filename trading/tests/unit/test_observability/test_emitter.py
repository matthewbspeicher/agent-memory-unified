from unittest.mock import AsyncMock, MagicMock
import pytest
from config import load_config


def test_supabase_config_default_none():
    c = load_config(env_file="nonexistent.env")
    assert hasattr(c, "supabase_url")
    assert hasattr(c, "supabase_anon_key")
    assert hasattr(c, "supabase_service_key")


from observability.emitter import ObservabilityEmitter, TradeEvent


@pytest.fixture
def mock_supabase():
    """Returns a mock supabase async client."""
    client = MagicMock()
    # table(...).insert(...).execute() pattern
    table = MagicMock()
    table.insert = MagicMock(return_value=table)
    table.upsert = MagicMock(return_value=table)
    table.execute = AsyncMock(return_value=MagicMock(data=[{}]))
    client.table = MagicMock(return_value=table)
    return client


@pytest.fixture
def mock_alert_router():
    router = MagicMock()
    router.fire = AsyncMock()
    router.flush_warnings = AsyncMock()
    return router


@pytest.mark.asyncio
async def test_emit_critical_calls_alert_router(mock_supabase, mock_alert_router):
    emitter = ObservabilityEmitter(
        supabase_client=mock_supabase,
        alert_router=mock_alert_router,
    )
    await emitter.emit(
        event_type="kill_switch_triggered",
        level="critical",
        agent_name=None,
        message="Kill switch engaged",
        metadata={"rule": "max_drawdown"},
    )
    mock_alert_router.fire.assert_awaited_once_with(
        "critical",
        "kill_switch_triggered",
        "Kill switch engaged",
        {"rule": "max_drawdown"},
    )


@pytest.mark.asyncio
async def test_emit_info_does_not_call_alert_router(mock_supabase, mock_alert_router):
    emitter = ObservabilityEmitter(
        supabase_client=mock_supabase,
        alert_router=mock_alert_router,
    )
    await emitter.emit(
        event_type="trade_executed",
        level="info",
        agent_name="rsi_agent",
        message="Trade done",
        metadata={},
    )
    mock_alert_router.fire.assert_not_awaited()


@pytest.mark.asyncio
async def test_heartbeat_upserts_agent(mock_supabase, mock_alert_router):
    emitter = ObservabilityEmitter(
        supabase_client=mock_supabase,
        alert_router=mock_alert_router,
    )
    await emitter.heartbeat(agent_name="rsi_agent", status="running")
    mock_supabase.table.assert_any_call("agent_heartbeats")


@pytest.mark.asyncio
async def test_emit_trade_inserts_row(mock_supabase, mock_alert_router):
    emitter = ObservabilityEmitter(
        supabase_client=mock_supabase,
        alert_router=mock_alert_router,
    )
    event = TradeEvent(
        agent_name="rsi_agent",
        symbol="AAPL",
        action="buy",
        fill_price=150.05,
        expected_price=150.00,
        slippage_bps=3,
        commission=1.00,
    )
    await emitter.emit_trade(event)
    mock_supabase.table.assert_any_call("trade_events")
