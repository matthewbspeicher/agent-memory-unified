from decimal import Decimal
from datetime import datetime, timezone, timedelta
from broker.models import Bar, Symbol, AssetType, Position
from whatsapp.charts import render_price_chart, render_portfolio_chart


def _make_bars(count=30):
    base = datetime.now(timezone.utc) - timedelta(days=count)
    sym = Symbol(ticker="AAPL", asset_type=AssetType.STOCK)
    return [
        Bar(
            symbol=sym,
            open=Decimal("150") + Decimal(str(i % 5)),
            high=Decimal("155") + Decimal(str(i % 3)),
            low=Decimal("148") + Decimal(str(i % 4)),
            close=Decimal("152") + Decimal(str(i % 5)),
            volume=1000000 + i * 10000,
            timestamp=base + timedelta(days=i),
        )
        for i in range(count)
    ]


def test_price_chart_returns_png():
    bars = _make_bars()
    png_bytes = render_price_chart("AAPL", bars)
    assert isinstance(png_bytes, bytes)
    assert len(png_bytes) > 100
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_portfolio_chart_returns_png():
    positions = [
        Position(
            symbol=Symbol(ticker="AAPL", asset_type=AssetType.STOCK),
            quantity=Decimal("100"),
            avg_cost=Decimal("150"),
            market_value=Decimal("15200"),
            unrealized_pnl=Decimal("200"),
            realized_pnl=Decimal("0"),
        ),
        Position(
            symbol=Symbol(ticker="MSFT", asset_type=AssetType.STOCK),
            quantity=Decimal("50"),
            avg_cost=Decimal("300"),
            market_value=Decimal("15500"),
            unrealized_pnl=Decimal("500"),
            realized_pnl=Decimal("0"),
        ),
    ]
    png_bytes = render_portfolio_chart(positions)
    assert isinstance(png_bytes, bytes)
    assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"


def test_price_chart_empty_bars():
    png_bytes = render_price_chart("AAPL", [])
    assert isinstance(png_bytes, bytes)
    assert len(png_bytes) > 100
