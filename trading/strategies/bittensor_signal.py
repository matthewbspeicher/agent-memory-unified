from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone

from agents.base import StructuredAgent
from agents.models import Opportunity, OpportunityStatus
from broker.models import AssetType, Symbol
from data.bus import DataBus

logger = logging.getLogger(__name__)


def _as_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


class BittensorSignalAgent(StructuredAgent):
    """Converts stored Bittensor consensus views into conservative directional opportunities."""

    @property
    def description(self) -> str:
        symbol = self.parameters.get("symbol", "BTCUSD")
        tf = self.parameters.get("timeframe", "5m")
        return f"Bittensor Subnet 8 consensus signal for {symbol} {tf}"

    async def scan(self, data: DataBus) -> list[Opportunity]:
        ds = getattr(data, "_bittensor_source", None)
        if ds is None:
            return []

        symbol = self.parameters.get("symbol", "BTCUSD")
        timeframe = self.parameters.get("timeframe", "5m")

        view = await ds.get_latest_signal(symbol, timeframe)
        if view is None:
            return []

        # Gate: staleness
        max_age = self.parameters.get("max_signal_age_seconds", 600)
        age = (datetime.now(timezone.utc) - _as_utc(view.timestamp)).total_seconds()
        if age > max_age:
            return []

        # Gate: low confidence
        if view.is_low_confidence:
            return []

        # Gate: minimum responders
        min_responders = self.parameters.get("min_responses_for_opportunity", 3)
        if view.responder_count < min_responders:
            return []

        # Select view type (equal-weight vs incentive-weighted)
        use_weighted = self.parameters.get("use_weighted_view", False)
        direction_score = (
            view.weighted_direction if use_weighted else view.equal_weight_direction
        )
        expected_return = (
            view.weighted_expected_return
            if use_weighted
            else view.equal_weight_expected_return
        )

        # Gate: agreement
        min_agreement = self.parameters.get("min_agreement_ratio", 0.65)
        if view.agreement_ratio < min_agreement:
            return []

        # Gate: directional strength
        min_direction = self.parameters.get("min_abs_direction", 0.20)
        if abs(direction_score) < min_direction:
            return []

        # Gate: minimum expected return
        min_return = self.parameters.get("min_expected_return", 0.002)
        if abs(expected_return) < min_return:
            return []

        # Gate: weighting divergence
        max_divergence = self.parameters.get("max_weighting_divergence", 0.25)
        if abs(view.weighted_direction - view.equal_weight_direction) > max_divergence:
            return []

        # Gate: short signals
        allow_short = self.parameters.get("allow_short_signals", True)
        if direction_score < 0 and not allow_short:
            return []

        # Gate: intel veto
        intel_enabled = self.parameters.get("intel_enabled", False)
        intel_enrichment = None
        if intel_enabled:
            signal_bus = getattr(data, "_signal_bus", None)
            if signal_bus:
                enriched_signals = signal_bus.query(signal_type="intel_enriched_consensus")
                for s in reversed(enriched_signals):
                    if s.payload.get("symbol") == symbol:
                        intel_enrichment = s.payload
                        break

            if intel_enrichment:
                if intel_enrichment.get("vetoed", False):
                    return []

        # Derive signal
        signal = "BUY" if direction_score > 0 else "SELL"
        if intel_enrichment and "enriched_confidence" in intel_enrichment:
            confidence = intel_enrichment["enriched_confidence"]
        else:
            confidence = min(abs(direction_score) * view.agreement_ratio, 1.0)

        return [
            Opportunity(
                id=str(uuid.uuid4()),
                agent_name=self.name,
                symbol=Symbol(ticker=symbol, asset_type=AssetType.PREDICTION),
                signal=signal,
                confidence=confidence,
                reasoning=(
                    f"Bittensor {symbol} {timeframe} signal: "
                    f"direction={direction_score:.2f}, "
                    f"expected_return={expected_return:.3%}, "
                    f"agreement={view.agreement_ratio:.2f}, "
                    f"responders={view.responder_count}"
                ),
                data={
                    "source": "bittensor",
                    "window_id": view.window_id,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction_score": direction_score,
                    "expected_return": expected_return,
                    "equal_weight_direction": view.equal_weight_direction,
                    "weighted_direction": view.weighted_direction,
                    "agreement_ratio": view.agreement_ratio,
                    "responder_count": view.responder_count,
                    "derivation_version": view.derivation_version,
                    "is_low_confidence": view.is_low_confidence,
                    "intel": intel_enrichment.get("intel") if intel_enrichment else None,
                },
                timestamp=view.timestamp,
                status=OpportunityStatus.PENDING,
            )
        ]
