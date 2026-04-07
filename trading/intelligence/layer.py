from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

from agents.models import AgentSignal
from data.signal_bus import SignalBus
from intelligence.circuit_breaker import ProviderCircuitBreaker, CircuitOpenError
from intelligence.config import IntelligenceConfig
from intelligence.enrichment import enrich_confidence
from intelligence.models import IntelReport
from intelligence.providers.anomaly import AnomalyProvider
from intelligence.providers.on_chain import OnChainProvider
from intelligence.providers.sentiment import SentimentProvider
from intelligence.providers.regime import RegimeProvider
from intelligence.providers.order_flow import OrderFlowProvider
from intelligence.providers.derivatives import DerivativesProvider
from intelligence.providers.risk_audit import RiskAuditProvider
from utils.logging import log_event

logger = logging.getLogger(__name__)


class IntelligenceLayer:
    """Orchestrates intel providers, enriches consensus signals, publishes results."""

    def __init__(
        self, signal_bus: SignalBus, config: IntelligenceConfig, memory_manager=None
    ):
        self.signal_bus = signal_bus
        self.config = config
        self._running = False

        # Providers
        self._on_chain = OnChainProvider(coinglass_api_key=config.coinglass_api_key)
        self._sentiment = SentimentProvider()
        self._anomaly = AnomalyProvider()
        self._regime = RegimeProvider(memory_manager=memory_manager)
        self._order_flow = OrderFlowProvider()
        self._risk_audit = RiskAuditProvider(
            var_threshold_pct=config.risk_var_threshold_pct,
            horizon_days=config.risk_horizon_days,
        )
        self._derivatives = DerivativesProvider()

        # Circuit breakers (one per provider)
        def make_breaker() -> ProviderCircuitBreaker:
            return ProviderCircuitBreaker(
                config.circuit_breaker_failures, config.circuit_breaker_reset_seconds
            )

        self._breakers: dict[str, ProviderCircuitBreaker] = {
            "on_chain": make_breaker(),
            "sentiment": make_breaker(),
            "anomaly": make_breaker(),
            "order_flow": make_breaker(),
            "regime": make_breaker(),
            "risk_audit": make_breaker(),
            "derivatives": make_breaker(),
        }

        # Metrics
        self._enrichments_applied = 0
        self._vetos_issued = 0
        self._provider_failures = 0
        self._total_calls = 0

    async def start(self) -> None:
        self._running = True
        self.signal_bus.subscribe(self._handle_consensus)
        logger.info("IntelligenceLayer started (enabled=%s)", self.config.enabled)

    async def stop(self) -> None:
        self._running = False

    async def _handle_consensus(self, signal: AgentSignal) -> None:
        if signal.signal_type != "bittensor_consensus":
            return
        if not self._running:
            return

        payload = signal.payload
        symbol = payload.get("symbol", "BTCUSD")
        base_confidence = payload.get("confidence", 0.0)
        direction = payload.get("direction", "flat")

        # Map direction to numeric score for enrichment
        direction_score = {"bullish": 1.0, "bearish": -1.0, "flat": 0.0}.get(
            direction, 0.0
        )

        if not self.config.enabled:
            await self._publish_enriched(
                signal, base_confidence, vetoed=False, enrichment_data={}
            )
            return

        reports = await self._gather_intel(symbol)

        enriched_confidence, enrichment = enrich_confidence(
            base_confidence=base_confidence,
            direction_score=direction_score,
            reports=reports,
            weights=self.config.weights,
            max_adjustment_pct=self.config.max_adjustment_pct,
        )

        if enrichment.vetoed:
            self._vetos_issued += 1
            log_event(
                logger,
                logging.WARNING,
                "intel.veto",
                f"Intel veto for {symbol}: {enrichment.veto_reason}",
                data={"symbol": symbol, "reason": enrichment.veto_reason},
            )
        else:
            self._enrichments_applied += 1
            log_event(
                logger,
                logging.INFO,
                "intel.enrichment",
                f"Intel enrichment for {symbol}: {base_confidence:.3f} -> {enriched_confidence:.3f}",
                data={
                    "symbol": symbol,
                    "base": base_confidence,
                    "enriched": enriched_confidence,
                    "adjustment": enrichment.adjustment,
                },
            )

        await self._publish_enriched(
            signal,
            enriched_confidence,
            vetoed=enrichment.vetoed,
            enrichment_data={
                "veto_reason": enrichment.veto_reason,
                "base_confidence": enrichment.base_confidence,
                "adjustment": enrichment.adjustment,
                "contributions": enrichment.contributions,
            },
        )

    async def _gather_intel(self, symbol: str) -> list[IntelReport]:
        providers = [
            ("on_chain", self._on_chain),
            ("sentiment", self._sentiment),
            ("anomaly", self._anomaly),
            ("order_flow", self._order_flow),
            ("regime", self._regime),
            ("risk_audit", self._risk_audit),
            ("derivatives", self._derivatives),
        ]

        async def _call_provider(name: str, provider) -> IntelReport | None:
            self._total_calls += 1
            breaker = self._breakers[name]
            try:
                return await breaker.call(lambda: provider.analyze(symbol))
            except CircuitOpenError:
                logger.debug("Circuit open for provider %s, skipping", name)
                return None
            except Exception as e:
                self._provider_failures += 1
                logger.warning("Intel provider %s failed: %s", name, e)
                return None

        timeout = self.config.timeout_ms / 1000.0
        tasks = [_call_provider(name, provider) for name, provider in providers]

        try:
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "Intelligence gathering timed out after %dms", self.config.timeout_ms
            )
            return []

        reports = []
        for result in results:
            if isinstance(result, IntelReport):
                if result.veto:
                    return [result]  # early exit on veto
                reports.append(result)

        return reports

    async def _publish_enriched(
        self,
        original: AgentSignal,
        enriched_confidence: float,
        vetoed: bool,
        enrichment_data: dict,
    ) -> None:
        enriched_payload = dict(original.payload)
        enriched_payload["enriched_confidence"] = enriched_confidence
        enriched_payload["vetoed"] = vetoed
        enriched_payload["intel"] = enrichment_data

        enriched_signal = AgentSignal(
            source_agent="intelligence_layer",
            signal_type="intel_enriched_consensus",
            payload=enriched_payload,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )
        await self.signal_bus.publish(enriched_signal)

    def get_status(self) -> dict:
        return {
            "enabled": self.config.enabled,
            "providers": {
                name: {
                    "circuit": breaker.state,
                    "failures": breaker.failures,
                }
                for name, breaker in self._breakers.items()
            },
            "enrichments_applied": self._enrichments_applied,
            "vetos_issued": self._vetos_issued,
            "provider_failures": self._provider_failures,
            "total_calls": self._total_calls,
        }
