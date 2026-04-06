import pytest
import asyncio
import logging
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from execution.arbitrage import ArbCoordinator
from execution.models import ArbTrade, ArbLeg, SequencingStrategy
from broker.models import (
    OrderBase,
    OrderSide,
    OrderStatus,
    OrderResult,
    Symbol,
    AssetType,
)

# Configure logging to capture the skew output
logger = logging.getLogger("execution.arbitrage")
logger.setLevel(logging.INFO)


@pytest.fixture
def mock_brokers():
    kalshi_broker = MagicMock()
    poly_broker = MagicMock()

    # Mock the fast, concurrent network fills (using minimal sleeps to simulate network jitter)
    async def mock_kalshi_fill(*args, **kwargs):
        await asyncio.sleep(0.01)  # 10ms Kalshi latency
        return OrderResult(
            order_id="k-1",
            status=OrderStatus.FILLED,
            avg_fill_price=Decimal("0.5"),
            filled_quantity=Decimal("10"),
        )

    async def mock_poly_fill(*args, **kwargs):
        await asyncio.sleep(0.015)  # 15ms Poly latency
        return OrderResult(
            order_id="p-1",
            status=OrderStatus.FILLED,
            avg_fill_price=Decimal("0.4"),
            filled_quantity=Decimal("10"),
        )

    kalshi_broker.orders.place_order = AsyncMock(side_effect=mock_kalshi_fill)
    poly_broker.orders.place_order = AsyncMock(side_effect=mock_poly_fill)

    # Mock the O(1) cache lookup for pre-flight
    poly_broker.market_data.ds.get_live_quote = AsyncMock(return_value=40)

    return {"kalshi": kalshi_broker, "polymarket": poly_broker}


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.save_trade = AsyncMock()
    store.update_trade_state = AsyncMock()
    store.update_leg = AsyncMock()
    store.update_leg_atomic = AsyncMock()
    return store


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.order_timeout = 5.0
    settings.arb_toxicity_threshold = 0.8
    return settings


@pytest.mark.asyncio
async def test_execution_skew_performance(
    mock_brokers, mock_store, mock_settings, caplog
):
    """
    Validates that the placement skew between Leg A and Leg B is under our 50ms budget.
    """
    coordinator = ArbCoordinator(mock_brokers, mock_store, mock_settings)

    # Run 50 simulated trades to gather a skew distribution
    skews = []

    for i in range(50):
        trade = ArbTrade(
            id=f"arb-perf-{i}",
            symbol_a="KALSHI-YES",
            symbol_b="POLY-NO",
            expected_profit_bps=100,
            sequencing=SequencingStrategy.KALSHI_FIRST,
            leg_a=ArbLeg(
                broker_id="kalshi",
                order=OrderBase(
                    symbol=Symbol(ticker="KALSHI-YES", asset_type=AssetType.PREDICTION),
                    side=OrderSide.BUY,
                    quantity=Decimal("10"),
                    account_id="test-acct",
                ),
            ),
            leg_b=ArbLeg(
                broker_id="polymarket",
                order=OrderBase(
                    symbol=Symbol(ticker="POLY-NO", asset_type=AssetType.PREDICTION),
                    side=OrderSide.BUY,
                    quantity=Decimal("10"),
                    account_id="test-acct",
                ),
            ),
        )

        with caplog.at_level(logging.INFO):
            success = await coordinator.execute_arbitrage(trade)
            assert success is True

            # Extract skew from logs
            for record in caplog.records:
                if "Placement Skew" in record.message and trade.id in record.message:
                    # Example: "ArbCoordinator: Placement Skew for arb-perf-0: 0.12ms"
                    skew_str = record.message.split()[-1].replace("ms", "")
                    skews.append(float(skew_str))
                    break

            caplog.clear()

    # Calculate metrics
    avg_skew = sum(skews) / len(skews)
    max_skew = max(skews)

    print("\n--- Skew Performance Profile ---")
    print(f"Total Trades: {len(skews)}")
    print(f"Average Skew: {avg_skew:.3f} ms")
    print(f"Maximum Skew: {max_skew:.3f} ms")
    print("--------------------------------")

    # The ultimate Go/No-Go Gate: Max skew must be under 50ms
    assert max_skew < 50.0, (
        f"Performance Gate Failed: Max skew {max_skew}ms exceeded 50ms budget"
    )
