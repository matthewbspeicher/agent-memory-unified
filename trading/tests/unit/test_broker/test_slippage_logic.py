import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from broker.models import Symbol, AssetType, MarketOrder, OrderSide
from broker.paper import PaperOrderManager

@pytest.mark.asyncio
async def test_realistic_slippage_calculation():
    # Setup mock market data with order book
    market_data = AsyncMock()
    # BTC/USDT order book
    # Asks (for BUY): [price, volume]
    market_data.get_order_book = AsyncMock(return_value={
        "asks": [
            [50000.0, 1.0],
            [50010.0, 2.0],
            [50050.0, 5.0]
        ],
        "bids": []
    })
    market_data.get_quote = AsyncMock(return_value=MagicMock(ask=Decimal("50000")))
    
    store = AsyncMock()
    store.record_fill = AsyncMock()
    store.save_order = AsyncMock()
    
    mgr = PaperOrderManager(market_data, store, max_slippage=Decimal("0.001"))
    
    # Buy 2.0 BTC
    # 1.0 @ 50000 = 50000
    # 1.0 @ 50010 = 50010
    # Avg = (50000 + 50010) / 2 = 50005
    
    symbol = Symbol(ticker="BTCUSD", asset_type=AssetType.CRYPTO)
    order = MarketOrder(symbol=symbol, side=OrderSide.BUY, quantity=Decimal("2.0"), account_id="PAPER")
    
    fill_price = await mgr._estimate_slippage(symbol, Decimal("2.0"), OrderSide.BUY, Decimal("50000"))
    assert fill_price == Decimal("50005.0")
