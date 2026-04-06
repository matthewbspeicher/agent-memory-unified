from __future__ import annotations
import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from agents.base import Agent
from agents.models import AgentConfig, Opportunity, OpportunityStatus, AgentSignal
from broker.models import Symbol, AssetType, MarketOrder, OrderSide
from storage.symbol_map import SignalMapper

if TYPE_CHECKING:
    from data.bus import DataBus

logger = logging.getLogger(__name__)

class BittensorAlphaAgent(Agent):
    """
    Agent that trades based on Bittensor Subnet 8 consensus signals.
    """
    
    def __init__(self, config: AgentConfig):
        super().__init__(config)
        # Thresholds from config
        self._min_agreement = float(config.parameters.get("min_agreement", 0.7))
        self._min_return = float(config.parameters.get("min_return", 0.015))
        self._pending_opportunities: list[Opportunity] = []

    @property
    def description(self) -> str:
        return f"Bittensor Subnet 8 Consensus Agent (min_agreement={self._min_agreement})"

    async def setup(self) -> None:
        if self.signal_bus:
            self.signal_bus.subscribe(self.handle_signal)

    async def handle_signal(self, signal: AgentSignal):
        if signal.signal_type != "bittensor_consensus":
            return

        payload = signal.payload
        symbol_ticker = payload.get("symbol")
        if not symbol_ticker:
            return
            
        direction = payload.get("direction")
        confidence = payload.get("confidence", 0)
        expected_return = payload.get("expected_return", 0)

        if direction == "flat":
            return

        # Consensus logic
        if confidence < self._min_agreement or abs(expected_return) < self._min_return:
            logger.debug(f"BittensorAgent: Signal for {symbol_ticker} below thresholds (Conf: {confidence:.2f}, Ret: {expected_return:.4f})")
            return

        logger.info(f"BittensorAgent: High-conviction signal for {symbol_ticker} ({direction}, Conf: {confidence:.2f})")

        # Map to internal symbol
        asset_type = AssetType.STOCK
        if "USD" in symbol_ticker and "-" not in symbol_ticker:
            asset_type = AssetType.CRYPTO
        
        mapper = SignalMapper()
        symbol = mapper.map_to_symbol(symbol_ticker) or Symbol(ticker=symbol_ticker, asset_type=asset_type)
        
        # Create Opportunity
        opp = Opportunity(
            id=f"bt-{payload.get('window_id', 'unknown')}-{symbol_ticker}",
            agent_name=self.name,
            symbol=symbol,
            signal=direction.upper(),
            confidence=confidence,
            reasoning=f"Bittensor Subnet 8 Consensus: {confidence*100:.1f}% agreement among {payload.get('miner_count', 0)} miners. Expected return: {expected_return*100:.2f}%",
            data=payload,
            timestamp=datetime.now(timezone.utc),
            status=OpportunityStatus.PENDING,
            suggested_trade=MarketOrder(
                symbol=symbol,
                side=OrderSide.BUY if direction == "bullish" else OrderSide.SELL,
                quantity=Decimal("0"), # SizingEngine will fill this
                account_id="",
            )
        )

        self._pending_opportunities.append(opp)

    async def scan(self, data: DataBus) -> list[Opportunity]:
        # This agent is primarily signal-driven
        opps = list(self._pending_opportunities)
        self._pending_opportunities.clear()
        return opps
