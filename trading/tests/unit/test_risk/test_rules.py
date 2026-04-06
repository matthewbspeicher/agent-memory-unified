from decimal import Decimal

from broker.models import (
    AccountBalance,
    AssetType,
    LimitOrder,
    MarketOrder,
    OrderSide,
    Position,
    Quote,
    Symbol,
)
from risk.rules import (
    MaxDailyLoss,
    MaxDailyTrades,
    MaxOpenPositions,
    MaxPortfolioExposure,
    MaxPositionSize,
    PortfolioContext,
    SectorConcentration,
    MaxCorrelation,
    MaxDrawdownPct,
)


def _ctx(**overrides) -> PortfolioContext:
    defaults = dict(
        positions=[],
        balance=AccountBalance(
            account_id="U123",
            net_liquidation=Decimal("100000"),
            buying_power=Decimal("50000"),
            cash=Decimal("30000"),
            maintenance_margin=Decimal("20000"),
        ),
        daily_pnl=Decimal("0"),
        daily_trade_count=0,
        sectors={},
    )
    defaults.update(overrides)
    return PortfolioContext(**defaults)


def _trade(ticker="AAPL", qty=100, price=150):
    return MarketOrder(
        symbol=Symbol(ticker=ticker),
        side=OrderSide.BUY,
        quantity=Decimal(str(qty)),
        account_id="U123",
    ), Quote(symbol=Symbol(ticker=ticker), last=Decimal(str(price)))


class TestMaxPositionSize:
    def test_pass(self):
        trade, quote = _trade(qty=10, price=150)
        rule = MaxPositionSize(max_dollars=5000, max_shares=500)
        result = rule.evaluate(trade, quote, _ctx())
        assert result.passed

    def test_fail_dollars(self):
        trade, quote = _trade(qty=100, price=150)  # $15000
        rule = MaxPositionSize(max_dollars=5000, max_shares=500)
        result = rule.evaluate(trade, quote, _ctx())
        assert not result.passed
        assert "dollars" in result.reason.lower()

    def test_fail_shares(self):
        trade, quote = _trade(qty=600, price=1)
        rule = MaxPositionSize(max_dollars=50000, max_shares=500)
        result = rule.evaluate(trade, quote, _ctx())
        assert not result.passed


class TestMaxPortfolioExposure:
    def test_pass(self):
        trade, quote = _trade(qty=10, price=150)  # $1500 / $100k = 1.5%
        rule = MaxPortfolioExposure(max_percent=10)
        result = rule.evaluate(trade, quote, _ctx())
        assert result.passed

    def test_fail(self):
        trade, quote = _trade(qty=100, price=150)  # $15000 / $100k = 15%
        rule = MaxPortfolioExposure(max_percent=10)
        result = rule.evaluate(trade, quote, _ctx())
        assert not result.passed


class TestMaxDailyLoss:
    def test_pass(self):
        rule = MaxDailyLoss(max_dollars=1000)
        trade, quote = _trade()
        result = rule.evaluate(trade, quote, _ctx(daily_pnl=Decimal("-500")))
        assert result.passed

    def test_fail(self):
        rule = MaxDailyLoss(max_dollars=1000)
        trade, quote = _trade()
        result = rule.evaluate(trade, quote, _ctx(daily_pnl=Decimal("-1200")))
        assert not result.passed


class TestMaxOpenPositions:
    def test_pass(self):
        rule = MaxOpenPositions(max_count=20)
        trade, quote = _trade()
        positions = [
            Position(
                symbol=Symbol(ticker=f"SYM{i}"),
                quantity=Decimal("10"),
                avg_cost=Decimal("100"),
                market_value=Decimal("1000"),
                unrealized_pnl=Decimal("0"),
                realized_pnl=Decimal("0"),
            )
            for i in range(5)
        ]
        result = rule.evaluate(trade, quote, _ctx(positions=positions))
        assert result.passed

    def test_fail(self):
        rule = MaxOpenPositions(max_count=5)
        trade, quote = _trade()
        positions = [
            Position(
                symbol=Symbol(ticker=f"SYM{i}"),
                quantity=Decimal("10"),
                avg_cost=Decimal("100"),
                market_value=Decimal("1000"),
                unrealized_pnl=Decimal("0"),
                realized_pnl=Decimal("0"),
            )
            for i in range(5)
        ]
        result = rule.evaluate(trade, quote, _ctx(positions=positions))
        assert not result.passed


class TestMaxDailyTrades:
    def test_pass(self):
        rule = MaxDailyTrades(max_count=10)
        trade, quote = _trade()
        result = rule.evaluate(trade, quote, _ctx(daily_trade_count=5))
        assert result.passed

    def test_fail(self):
        rule = MaxDailyTrades(max_count=10)
        trade, quote = _trade()
        result = rule.evaluate(trade, quote, _ctx(daily_trade_count=10))
        assert not result.passed


class TestSectorConcentration:
    def test_pass(self):
        rule = SectorConcentration(max_percent=25)
        trade, quote = _trade()
        result = rule.evaluate(
            trade,
            quote,
            _ctx(
                sectors={"Technology": Decimal("15000")},  # 15%
            ),
        )
        assert result.passed

    def test_fail(self):
        rule = SectorConcentration(max_percent=25)
        trade, quote = _trade()
        result = rule.evaluate(
            trade,
            quote,
            _ctx(
                sectors={"Technology": Decimal("30000")},  # 30%
            ),
        )
        assert not result.passed


class TestMaxDrawdownPct:
    def test_pass_no_drawdown(self):
        rule = MaxDrawdownPct(max_pct=5.0)
        trade, quote = _trade()
        # Initialize HWM by evaluating once
        rule.evaluate(
            trade,
            quote,
            _ctx(
                balance=AccountBalance(
                    "U123",
                    Decimal("100000"),
                    Decimal("50000"),
                    Decimal("30"),
                    Decimal("20"),
                )
            ),
        )

        # Balance stays at 100k
        result = rule.evaluate(
            trade,
            quote,
            _ctx(
                balance=AccountBalance(
                    "U123",
                    Decimal("100000"),
                    Decimal("50000"),
                    Decimal("30"),
                    Decimal("20"),
                )
            ),
        )
        assert result.passed
        assert rule.high_water_mark == Decimal("100000")

    def test_pass_within_drawdown(self):
        rule = MaxDrawdownPct(max_pct=5.0)
        trade, quote = _trade()
        rule.evaluate(
            trade,
            quote,
            _ctx(
                balance=AccountBalance(
                    "U123", Decimal("100000"), Decimal("0"), Decimal("0"), Decimal("0")
                )
            ),
        )

        # Balance drops to 96k (4% drawdown)
        result = rule.evaluate(
            trade,
            quote,
            _ctx(
                balance=AccountBalance(
                    "U123", Decimal("96000"), Decimal("0"), Decimal("0"), Decimal("0")
                )
            ),
        )
        assert result.passed

    def test_fail_exceeds_drawdown(self):
        rule = MaxDrawdownPct(max_pct=5.0)
        trade, quote = _trade()
        rule.evaluate(
            trade,
            quote,
            _ctx(
                balance=AccountBalance(
                    "U123", Decimal("100000"), Decimal("0"), Decimal("0"), Decimal("0")
                )
            ),
        )

        # Balance drops to 94k (6% drawdown)
        result = rule.evaluate(
            trade,
            quote,
            _ctx(
                balance=AccountBalance(
                    "U123", Decimal("94000"), Decimal("0"), Decimal("0"), Decimal("0")
                )
            ),
        )
        assert not result.passed
        assert "exceeds max" in result.reason

    def test_hwm_updates_automatically(self):
        rule = MaxDrawdownPct(max_pct=5.0)
        trade, quote = _trade()
        rule.evaluate(
            trade,
            quote,
            _ctx(
                balance=AccountBalance(
                    "U123", Decimal("100000"), Decimal("0"), Decimal("0"), Decimal("0")
                )
            ),
        )

        # Balance rises to 110k
        rule.evaluate(
            trade,
            quote,
            _ctx(
                balance=AccountBalance(
                    "U123", Decimal("110000"), Decimal("0"), Decimal("0"), Decimal("0")
                )
            ),
        )
        assert rule.high_water_mark == Decimal("110000")

        # Balance drops to 104k (5.4% drawdown relative to 110k)
        result = rule.evaluate(
            trade,
            quote,
            _ctx(
                balance=AccountBalance(
                    "U123", Decimal("104000"), Decimal("0"), Decimal("0"), Decimal("0")
                )
            ),
        )
        assert not result.passed


class TestMaxCorrelation:
    def test_pass_no_history(self):
        rule = MaxCorrelation(max_avg=0.5)
        trade, quote = _trade()
        # No history
        result = rule.evaluate(trade, quote, _ctx())
        assert result.passed

    def test_pass_within_correlation(self):
        rule = MaxCorrelation(max_avg=0.5)
        trade, quote = _trade()
        ctx = _ctx()
        # Mock low correlation histories (AAPL vs XYZ correlation is 0)
        ctx.price_histories = {
            "AAPL": [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")],
            "XYZ": [Decimal("4"), Decimal("1"), Decimal("4"), Decimal("1")],
        }
        result = rule.evaluate(trade, quote, ctx)
        assert result.passed

    def test_fail_exceeds_correlation(self):
        rule = MaxCorrelation(max_avg=0.8)
        trade, quote = _trade()
        ctx = _ctx()
        # Highly correlated +1 histories
        ctx.price_histories = {
            "AAPL": [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")],
            "MSFT": [Decimal("2"), Decimal("4"), Decimal("6"), Decimal("8")],
        }
        result = rule.evaluate(trade, quote, ctx)
        assert not result.passed
        assert "exceeds max" in result.reason


class TestMaxPredictionExposure:
    def test_evaluate_ignores_non_prediction(self):
        from risk.rules import MaxPredictionExposure

        rule = MaxPredictionExposure(max_dollars=50.0)
        trade = LimitOrder(
            symbol=Symbol("AAPL"),
            quantity=Decimal("100"),
            side=OrderSide.BUY,
            limit_price=Decimal("150"),
            account_id="U1",
        )
        quote = Quote(
            symbol=Symbol("AAPL"),
            bid=Decimal("150"),
            ask=Decimal("151"),
            last=Decimal("150"),
            volume=0,
        )
        ctx = _ctx()

        result = rule.evaluate(trade, quote, ctx)
        assert result.passed is True

    def test_evaluate_prediction_exposure_within_limit(self):
        from risk.rules import MaxPredictionExposure

        rule = MaxPredictionExposure(max_dollars=50.0)
        trade = LimitOrder(
            symbol=Symbol("WIN", AssetType.PREDICTION),
            quantity=Decimal("100"),
            side=OrderSide.BUY,
            limit_price=Decimal("0.45"),
            account_id="U1",
        )
        quote = Quote(
            symbol=Symbol("WIN", AssetType.PREDICTION),
            bid=Decimal("0.44"),
            ask=Decimal("0.46"),
            last=Decimal("0.45"),
            volume=0,
        )
        ctx = _ctx()

        result = rule.evaluate(trade, quote, ctx)
        assert result.passed is True

    def test_evaluate_prediction_exposure_exceeds_limit(self):
        from risk.rules import MaxPredictionExposure

        rule = MaxPredictionExposure(max_dollars=50.0)
        trade = LimitOrder(
            symbol=Symbol("WIN", AssetType.PREDICTION),
            quantity=Decimal("2000"),
            side=OrderSide.BUY,
            limit_price=Decimal("0.45"),
            account_id="U1",
        )
        quote = Quote(
            symbol=Symbol("WIN", AssetType.PREDICTION),
            bid=Decimal("0.44"),
            ask=Decimal("0.46"),
            last=Decimal("0.45"),
            volume=0,
        )
        ctx = _ctx()

        result = rule.evaluate(trade, quote, ctx)
        assert result.passed is False
        assert "exceeds max $50.0" in result.reason
