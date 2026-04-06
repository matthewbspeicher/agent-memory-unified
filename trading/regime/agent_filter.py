"""RegimeFilter — pause agents in unfavorable market regimes."""

from __future__ import annotations
import logging

from regime.models import MarketRegime, LiquidityRegime

logger = logging.getLogger(__name__)

# Default allowed regimes for agents with no custom configuration:
# Allow trending and sideways markets; block high volatility
DEFAULT_ALLOWED_REGIMES: frozenset[MarketRegime] = frozenset(
    {
        MarketRegime.TRENDING_UP,
        MarketRegime.TRENDING_DOWN,
        MarketRegime.SIDEWAYS,
        MarketRegime.LOW_VOLATILITY,
    }
)


class RegimeFilter:
    """
    Determines whether an agent is allowed to trade in the current market regime.

    For equity symbols, uses the equity MarketRegime (ADX/vol/slope-based).
    For prediction market symbols (AssetType.PREDICTION), delegates to a
    per-symbol LiquidityRegimeDetector when one is configured.

    Agents can be configured with custom allowed regime sets.
    If not configured, the DEFAULT_ALLOWED_REGIMES set is used.
    UNKNOWN regime always allows trading (not enough data to block).
    """

    def __init__(
        self,
        agent_regimes: dict[str, set[MarketRegime]] | None = None,
        liquidity_detector=None,
    ) -> None:
        """
        Args:
            agent_regimes: Optional map of agent_name → set of allowed regimes.
                           Agents not in this map use DEFAULT_ALLOWED_REGIMES.
            liquidity_detector: Optional LiquidityRegimeDetector for prediction
                                 market per-symbol liquidity checks.
        """
        self._agent_regimes: dict[str, frozenset[MarketRegime]] = {}
        if agent_regimes:
            for name, regimes in agent_regimes.items():
                self._agent_regimes[name] = frozenset(regimes)
        self._liquidity_detector = liquidity_detector

    def is_allowed(self, agent_name: str, regime: MarketRegime) -> bool:
        """
        Return True if the agent is allowed to trade in the given equity regime.

        UNKNOWN regime always returns True (insufficient data → don't block).
        This method handles equity symbols only. For prediction market symbols,
        use is_allowed_for_symbol() instead.
        """
        return self._check_equity_regime(agent_name, regime)

    async def is_allowed_for_symbol(self, agent_name: str, symbol) -> bool:
        """
        Return True if the agent is allowed to trade the given symbol.

        For PREDICTION asset types: checks per-symbol liquidity regime.
        For all other asset types: falls back to equity regime check using
        the symbol's last known MarketRegime (callers must supply regime separately
        via is_allowed() for equity symbols — this path returns True by default
        when no equity regime is available, matching the fail-open policy).

        UNKNOWN liquidity → allow (fail-open).
        No liquidity_detector configured → allow prediction agents.
        """
        try:
            from broker.models import AssetType

            if symbol.asset_type == AssetType.PREDICTION:
                if not self._liquidity_detector:
                    return True  # no detector configured, allow
                snapshot = await self._liquidity_detector.detect_symbol(symbol)
                allowed = snapshot.regime != LiquidityRegime.UNFAVORABLE
                if not allowed:
                    logger.info(
                        "RegimeFilter: blocking %s for prediction symbol %s "
                        "(spread=%.2f¢, vol=%.0f)",
                        agent_name,
                        symbol.ticker,
                        snapshot.spread_cents,
                        snapshot.volume_24h,
                    )
                return allowed
        except Exception as exc:
            logger.warning(
                "RegimeFilter: liquidity check failed for %s/%s, allowing: %s",
                agent_name,
                getattr(symbol, "ticker", symbol),
                exc,
            )
            return True  # fail-open on unexpected errors

        # Non-prediction symbols: callers should use is_allowed(agent, regime)
        return True

    def _check_equity_regime(self, agent_name: str, regime: MarketRegime) -> bool:
        """Internal equity-regime check (synchronous)."""
        if regime == MarketRegime.UNKNOWN:
            return True

        allowed = self._agent_regimes.get(agent_name, DEFAULT_ALLOWED_REGIMES)
        permitted = regime in allowed

        if not permitted:
            logger.info(
                "RegimeFilter: blocking %s in %s regime (allowed: %s)",
                agent_name,
                regime.value,
                [r.value for r in allowed],
            )

        return permitted

    def get_allowed_regimes(self, agent_name: str) -> frozenset[MarketRegime]:
        """Return the set of allowed regimes for an agent."""
        return self._agent_regimes.get(agent_name, DEFAULT_ALLOWED_REGIMES)
