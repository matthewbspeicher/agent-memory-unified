"""Delta-neutral funding rate arbitrage agent.

When perpetual futures funding rate is positive (longs pay shorts):
  Go long spot + short perpetual -> collect funding payments.
When funding rate is negative (shorts pay longs):
  Go short spot + long perpetual -> collect funding payments.

Funding is paid every 8 hours on Binance (3x/day).
Annualized rates often exceed 20% in bullish markets.
Research shows ~19% annual returns with <2% drawdown (delta-neutral).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from agents.base import StructuredAgent
from agents.models import Opportunity
from broker.models import AssetType, Symbol
from data.bus import DataBus

logger = logging.getLogger(__name__)

# Funding payments per day on Binance
_PAYMENTS_PER_DAY = 3
_DAYS_PER_YEAR = 365


class FundingRateArbAgent(StructuredAgent):
    """Delta-neutral funding rate arbitrage.

    When funding is positive (longs pay shorts):
      Go long spot + short perpetual -> collect funding payments
    When funding is negative (shorts pay longs):
      Go short spot + long perpetual -> collect funding payments
    """

    PARAMETER_SCHEMA = {
        "symbols": {"type": "list", "default": ["BTCUSD", "ETHUSD"]},
        "min_annualized_rate": {
            "type": "float",
            "min": 0.01,
            "max": 1.0,
            "default": 0.20,
        },
        "exit_rate": {
            "type": "float",
            "min": 0.0,
            "max": 0.5,
            "default": 0.05,
        },
        "exchange": {"type": "str", "default": "binance"},
    }

    @property
    def description(self) -> str:
        threshold = self.parameters.get("min_annualized_rate", 0.20)
        return (
            f"Funding rate arbitrage: delta-neutral when annualized rate "
            f"> {threshold:.0%}"
        )

    def _map_symbol(self, symbol: str) -> str:
        """Map internal symbol (e.g. BTCUSD) to CCXT perpetual format.

        Binance perps use the format: BTC/USDT:USDT
        """
        # Strip trailing "USD" and build CCXT perpetual symbol
        base = symbol.replace("USD", "")
        return f"{base}/USDT:USDT"

    async def _fetch_funding_rate(self, ccxt_symbol: str) -> float:
        """Fetch current funding rate from exchange via CCXT."""
        from data.exchange_client import ExchangeClient
        exchange_id = self.parameters.get("exchange", "binance")
        client = ExchangeClient(primary=exchange_id)
        try:
            return await client.fetch_funding_rate(ccxt_symbol)
        finally:
            await client.close()

    async def scan(self, data: DataBus) -> list[Opportunity]:
        symbols: list[str] = self.parameters.get("symbols", ["BTCUSD", "ETHUSD"])
        min_annualized: float = self.parameters.get("min_annualized_rate", 0.20)

        opportunities: list[Opportunity] = []

        for sym in symbols:
            try:
                ccxt_symbol = self._map_symbol(sym)
                funding_rate = await self._fetch_funding_rate(ccxt_symbol)
            except Exception as e:
                logger.warning(
                    "FundingRateArb: failed to fetch funding rate for %s: %s",
                    sym,
                    e,
                )
                continue

            annualized_rate = funding_rate * _PAYMENTS_PER_DAY * _DAYS_PER_YEAR

            if abs(annualized_rate) < min_annualized:
                logger.debug(
                    "FundingRateArb: %s annualized=%.4f below threshold %.4f, skipping",
                    sym,
                    annualized_rate,
                    min_annualized,
                )
                continue

            # Signal direction: positive funding → BUY (long spot + short perp)
            #                   negative funding → SELL (short spot + long perp)
            signal = "BUY" if funding_rate > 0 else "SELL"

            # Confidence scales with how far above threshold the rate is
            # At threshold → confidence ~0.5, at 2x threshold → ~0.75, etc.
            excess_ratio = abs(annualized_rate) / min_annualized
            confidence = min(1.0, 0.5 + 0.25 * (excess_ratio - 1.0))

            broker_symbol = Symbol(
                ticker=sym.replace("USD", "/USD"),
                asset_type=AssetType.CRYPTO,
                exchange=self.parameters.get("exchange", "binance"),
                currency="USD",
            )

            opp = Opportunity(
                id=str(uuid.uuid4()),
                agent_name=self.name,
                symbol=broker_symbol,
                signal=signal,
                confidence=confidence,
                reasoning=(
                    f"{sym} funding rate {funding_rate:.6f} "
                    f"(annualized {annualized_rate:.2%}). "
                    f"{'Longs pay shorts' if funding_rate > 0 else 'Shorts pay longs'} "
                    f"→ {signal} spot + {'short' if signal == 'BUY' else 'long'} perp "
                    f"for delta-neutral yield."
                ),
                data={
                    "funding_rate": funding_rate,
                    "annualized_rate": annualized_rate,
                    "ccxt_symbol": ccxt_symbol,
                    "exchange": self.parameters.get("exchange", "binance"),
                    "strategy": "funding_rate_arb",
                    "exit_rate": self.parameters.get("exit_rate", 0.05),
                },
                timestamp=datetime.now(timezone.utc),
            )
            opportunities.append(opp)

        return opportunities
