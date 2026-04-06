import pytest
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from whatsapp.assistant import WhatsAppAssistant
from broker.models import Position, Symbol, AssetType, AccountBalance


@pytest.fixture
def deps():
    client = AsyncMock()
    broker = MagicMock()
    broker.account.get_positions = AsyncMock(
        return_value=[
            Position(
                symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
                quantity=Decimal("100"),
                avg_cost=Decimal("150"),
                market_value=Decimal("15200"),
                unrealized_pnl=Decimal("200"),
                realized_pnl=Decimal("0"),
            )
        ]
    )
    broker.account.get_balances = AsyncMock(
        return_value=AccountBalance(
            account_id="U123",
            net_liquidation=Decimal("100000"),
            cash=Decimal("50000"),
            buying_power=Decimal("50000"),
            maintenance_margin=Decimal("0"),
        )
    )
    runner = MagicMock()
    runner.list_agents = MagicMock(return_value=[])
    opp_store = AsyncMock()
    opp_store.list = AsyncMock(return_value=[])
    risk_engine = MagicMock()

    return client, broker, runner, opp_store, risk_engine


@pytest.fixture
def assistant(deps):
    client, broker, runner, opp_store, risk_engine = deps
    return WhatsAppAssistant(
        client=client,
        broker=broker,
        runner=runner,
        opp_store=opp_store,
        risk_engine=risk_engine,
        account_id="U123",
    )


@pytest.fixture
def external_store():
    store = AsyncMock()
    store.get_balances = AsyncMock(
        return_value=[
            {
                "account_id": "X12345",
                "account_name": "INDIVIDUAL",
                "net_liquidation": "50000.00",
                "cash": "5000.00",
                "broker": "fidelity",
            }
        ]
    )
    store.get_positions = AsyncMock(
        return_value=[
            {
                "account_id": "X12345",
                "symbol": "MSFT",
                "description": "Microsoft Corp",
                "quantity": "50",
                "last_price": "400.00",
                "current_value": "20000.00",
                "cost_basis": "18000.00",
            }
        ]
    )
    store.get_import_age = AsyncMock(return_value=2.5)
    return store


@pytest.fixture
def assistant_with_external(deps, external_store):
    client, broker, runner, opp_store, risk_engine = deps
    return WhatsAppAssistant(
        client=client,
        broker=broker,
        runner=runner,
        opp_store=opp_store,
        risk_engine=risk_engine,
        account_id="U123",
        external_store=external_store,
    )


@pytest.mark.asyncio
async def test_portfolio_command(assistant, deps):
    client = deps[0]
    await assistant.handle("15551234567", "/portfolio", "msg-1")
    client.send_text.assert_called_once()
    msg = client.send_text.call_args[0][1]
    assert "Portfolio Total" in msg
    assert "IBKR" in msg


@pytest.mark.asyncio
async def test_portfolio_summary_with_external(
    assistant_with_external, deps, external_store
):
    client = deps[0]
    await assistant_with_external.handle("15551234567", "/portfolio", "msg-1")
    client.send_text.assert_called_once()
    msg = client.send_text.call_args[0][1]
    assert "Portfolio Total" in msg
    assert "IBKR" in msg
    assert "Fidelity" in msg
    assert "INDIVIDUAL" in msg
    # Total should be 100000 + 50000 = 150000
    assert "150,000" in msg


@pytest.mark.asyncio
async def test_portfolio_detailed(assistant_with_external, deps, external_store):
    client = deps[0]
    await assistant_with_external.handle("15551234567", "/portfolio detailed", "msg-1")
    client.send_text.assert_called_once()
    msg = client.send_text.call_args[0][1]
    assert "AAPL" in msg  # IBKR position
    assert "MSFT" in msg  # Fidelity position
    assert "Fidelity (INDIVIDUAL)" in msg


@pytest.mark.asyncio
async def test_portfolio_fidelity_only(assistant_with_external, deps, external_store):
    client = deps[0]
    await assistant_with_external.handle("15551234567", "/portfolio fidelity", "msg-1")
    client.send_text.assert_called_once()
    msg = client.send_text.call_args[0][1]
    assert "MSFT" in msg
    assert "IBKR" not in msg


@pytest.mark.asyncio
async def test_portfolio_fidelity_no_store(assistant, deps):
    client = deps[0]
    await assistant.handle("15551234567", "/portfolio fidelity", "msg-1")
    msg = client.send_text.call_args[0][1]
    assert "No external portfolio data" in msg


@pytest.mark.asyncio
async def test_portfolio_staleness_warning(deps):
    client, broker, runner, opp_store, risk_engine = deps
    store = AsyncMock()
    store.get_balances = AsyncMock(return_value=[])
    store.get_positions = AsyncMock(return_value=[])
    store.get_import_age = AsyncMock(return_value=30.0)  # 30 hours old
    a = WhatsAppAssistant(
        client=client,
        broker=broker,
        runner=runner,
        opp_store=opp_store,
        risk_engine=risk_engine,
        account_id="U123",
        external_store=store,
    )
    await a.handle("15551234567", "/portfolio", "msg-1")
    msg = client.send_text.call_args[0][1]
    assert "Warning" in msg
    assert "30 hours ago" in msg


@pytest.mark.asyncio
async def test_help_command(assistant, deps):
    client = deps[0]
    await assistant.handle("15551234567", "/help", "msg-2")
    client.send_text.assert_called_once()
    msg = client.send_text.call_args[0][1]
    assert "/portfolio" in msg


@pytest.mark.asyncio
async def test_buy_command_creates_confirmation(assistant, deps):
    client = deps[0]
    await assistant.handle("15551234567", "/buy AAPL 100", "msg-3")
    client.send_text.assert_called_once()
    msg = client.send_text.call_args[0][1]
    assert "AAPL" in msg
    assert assistant._confirmation.has_pending("15551234567")


@pytest.mark.asyncio
async def test_approve_command(assistant, deps):
    deps[0]
    opp_store = deps[3]
    opp_store.get = AsyncMock(return_value={"id": "opp-1", "status": "pending"})
    await assistant.handle("15551234567", "/approve opp-1", "msg-4")
    opp_store.update_status.assert_called_once()


@pytest.mark.asyncio
async def test_unknown_text_falls_back_to_no_llm_message(assistant, deps):
    """Without anthropic_api_key, freeform text should get a fallback message."""
    client = deps[0]
    await assistant.handle("15551234567", "how's my portfolio doing?", "msg-5")
    client.send_text.assert_called()
    msg = client.send_text.call_args[0][1]
    assert "/help" in msg.lower() or "command" in msg.lower()
