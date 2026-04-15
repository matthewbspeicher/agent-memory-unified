from decimal import Decimal

import pytest

from risk.portfolio_cap import PortfolioCap, PortfolioCapExceeded


class _FakeBroker:
    def __init__(self, positions_usd: Decimal):
        self._positions_usd = positions_usd

    async def total_position_usd(self) -> Decimal:
        return self._positions_usd


@pytest.mark.asyncio
async def test_allows_trade_within_cap():
    cap = PortfolioCap(
        max_usd=Decimal("10000"),
        brokers={
            "kalshi": _FakeBroker(Decimal("2000")),
            "polymarket": _FakeBroker(Decimal("3000")),
        },
    )
    await cap.check(additional_usd=Decimal("1000"))


@pytest.mark.asyncio
async def test_rejects_trade_that_would_exceed_cap():
    cap = PortfolioCap(
        max_usd=Decimal("10000"),
        brokers={
            "kalshi": _FakeBroker(Decimal("6000")),
            "polymarket": _FakeBroker(Decimal("4500")),
        },
    )
    with pytest.raises(PortfolioCapExceeded):
        await cap.check(additional_usd=Decimal("1"))


@pytest.mark.asyncio
async def test_cap_of_zero_disables_check():
    cap = PortfolioCap(
        max_usd=Decimal("0"),
        brokers={"kalshi": _FakeBroker(Decimal("999999"))},
    )
    await cap.check(additional_usd=Decimal("1000000"))
