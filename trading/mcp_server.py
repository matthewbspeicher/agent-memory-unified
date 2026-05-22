"""MCP Tool Server — exposes trading engine operations as MCP tools.

This module creates a FastMCP server that makes key trading engine
operations available to MCP-compatible AI agents.  The server runs
alongside the FastAPI app and shares its lifespan.

Usage with FastAPI::

    from mcp_server import create_mcp_server
    mcp = create_mcp_server(app_state=app.state, signal_bus=…)
    mcp_app = mcp.http_app(path='/mcp')
    # In app lifespan: app.mount('/mcp', mcp_app)

Tools exposed:
    Read-only operational:
      - query_signals: Query recent signals from the signal bus
      - list_signal_types: Names of every registered signal type
      - agent_status: List running agents and their status
      - get_regime: Current market regime
      - get_positions: Open positions from broker
      - get_intelligence_status: IntelligenceLayer metrics + provider health
      - get_opportunities: Recent Opportunity objects from the store
      - get_journal_entries: Trade journal entries (with autopsies)
      - get_brief: Today's morning brief (generates on first call)
      - get_session_bias: Today's session bias (cached or None)
      - get_sentiment: Latest normalized sentiment for a symbol (ADR-0011)
      - get_bittensor_status: Summary of validator + scheduler + miner state
      - health_check: Engine health status
    Write:
      - publish_signal: Publish a typed signal to the bus

The new (May 2026) tools mirror the read-only FastAPI routes under
`api/routes/`.  Each fishes its dependency from `app_state` exactly like
the corresponding route handler does, so wiring stays uniform.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)


def create_mcp_server(
    signal_bus: Any | None = None,
    agent_runner: Any | None = None,
    broker: Any | None = None,
    regime_manager: Any | None = None,
    app_state: Any | None = None,
) -> FastMCP:
    """Create and return the MCP server with trading engine tools.

    Args:
        signal_bus: SignalBus instance for querying/publishing signals.
        agent_runner: AgentRunner instance for agent status queries.
        broker: Broker interface for position/order queries.
        regime_manager: RegimeManager for market regime queries.
        app_state: FastAPI ``app.state``.  Tools that need state objects
            (intelligence_layer, opportunity_store, journal_service,
            brief_generator, bittensor_* attrs) read them from here,
            matching the route-handler convention in ``api/routes/``.

    Returns:
        Configured FastMCP server instance.
    """
    mcp = FastMCP("trading-engine")

    def _state(attr: str, default: Any = None) -> Any:
        """Fetch *attr* from ``app_state`` if set, else *default*."""
        if app_state is None:
            return default
        return getattr(app_state, attr, default)

    @mcp.tool()
    async def query_signals(
        signal_type: str | None = None,
        target_agent: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Query recent signals from the signal bus.

        Args:
            signal_type: Filter by type (e.g. 'bittensor_consensus', 'news_event').
            target_agent: Filter by target agent name.
            limit: Maximum signals to return (default 20).
        """
        if signal_bus is None:
            return [{"error": "Signal bus not available"}]
        signals = signal_bus.query(signal_type=signal_type, target_agent=target_agent)
        results = []
        for sig in signals[:limit]:
            results.append(
                {
                    "source_agent": sig.source_agent,
                    "target_agent": sig.target_agent,
                    "signal_type": sig.signal_type,
                    "payload": sig.payload,
                    "confidence": sig.confidence,
                    "timestamp": sig.timestamp.isoformat() if sig.timestamp else None,
                    "expires_at": sig.expires_at.isoformat()
                    if sig.expires_at
                    else None,
                }
            )
        return results

    @mcp.tool()
    async def list_signal_types() -> list[str]:
        """List all registered signal types with their descriptions."""
        from data.signal_types import registry

        return registry.known_types()

    @mcp.tool()
    async def publish_signal(
        source_agent: str,
        signal_type: str,
        payload: dict,
        expires_in_seconds: int = 3600,
    ) -> dict:
        """Publish a typed signal to the bus.

        Args:
            source_agent: Name of the agent publishing.
            signal_type: Must be a registered type (e.g. 'news_event').
            payload: Payload matching the signal type's Pydantic model.
            expires_in_seconds: TTL in seconds (default 3600 = 1 hour).
        """
        if signal_bus is None:
            return {"error": "Signal bus not available"}
        from datetime import datetime, timezone, timedelta
        from agents.models import AgentSignal

        try:
            signal = AgentSignal(
                source_agent=source_agent,
                signal_type=signal_type,
                payload=payload,
                expires_at=datetime.now(timezone.utc)
                + timedelta(seconds=expires_in_seconds),
            )
            await signal_bus.publish(signal)
            return {"status": "published", "signal_type": signal_type}
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"Unexpected error: {e}"}

    @mcp.tool()
    async def agent_status() -> list[dict]:
        """List all agents with their current status."""
        if agent_runner is None:
            return [{"error": "Agent runner not available"}]
        return [
            {
                "name": info.name,
                "description": info.description,
                "status": info.status,
                "last_run": info.last_run.isoformat() if info.last_run else None,
                "error_count": info.error_count,
            }
            for info in agent_runner.list_agents()
        ]

    @mcp.tool()
    async def get_regime() -> dict:
        """Get the current market regime state."""
        if regime_manager is None:
            return {"error": "Regime manager not available"}
        try:
            state = regime_manager.current_state
            return {
                "market_phase": getattr(state, "market_phase", "unknown"),
                "volatility": getattr(state, "volatility", "unknown"),
                "trend": getattr(state, "trend", "unknown"),
            }
        except Exception as e:
            return {"error": str(e)}

    @mcp.tool()
    async def get_positions() -> list[dict]:
        """Get current open positions from the broker."""
        if broker is None:
            return [{"error": "Broker not available"}]
        try:
            positions = await broker.get_positions()
            result = []
            for p in positions:
                result.append(
                    {
                        "symbol": getattr(p, "symbol", str(p)),
                        "side": getattr(p, "side", "unknown"),
                        "qty": getattr(p, "qty", 0),
                        "entry_price": getattr(p, "avg_entry_price", 0),
                        "unrealized_pnl": getattr(p, "unrealized_pnl", 0),
                    }
                )
            return result
        except Exception as e:
            logger.warning("Broker positions query failed: %s", e)
            return [{"error": str(e)}]

    @mcp.tool()
    async def health_check() -> dict:
        """Check trading engine health status."""
        status = {"mcp_server": "ok"}
        if signal_bus is not None:
            status["signal_bus"] = "ok"
        if agent_runner is not None:
            status["agents"] = len(agent_runner._agents)
        if broker is not None:
            status["broker"] = "connected"
        if regime_manager is not None:
            status["regime_manager"] = "ok"
        return status

    # -----------------------------------------------------------------
    # New read-only tools (2026-05) — mirror routes under api/routes/.
    # Each fishes its dependency out of app_state, same as the route.
    # -----------------------------------------------------------------

    @mcp.tool()
    async def get_intelligence_status() -> dict:
        """Get IntelligenceLayer metrics and per-provider circuit-breaker status.

        Mirrors ``GET /engine/v1/intelligence/status``.
        """
        layer = _state("intelligence_layer")
        if layer is None:
            return {"enabled": False, "status": "not_initialized"}
        try:
            return layer.get_status()
        except Exception as e:
            logger.warning("get_intelligence_status failed: %s", e)
            return {"error": str(e)}

    @mcp.tool()
    async def get_opportunities(
        agent_name: str | None = None,
        symbol: str | None = None,
        signal: str | None = None,
        limit: int = 25,
    ) -> list[dict]:
        """List recent Opportunity objects from the store.

        Mirrors ``GET /api/v1/opportunities``.  Filter by agent, symbol,
        or signal direction.  Limit defaults to 25 (max 200).
        """
        store = _state("opportunity_store")
        if store is None:
            return [{"error": "Opportunity store not available"}]
        try:
            limit = max(1, min(200, int(limit)))
            opps = await store.list(
                agent_name=agent_name,
                symbol=symbol,
                signal=signal,
                limit=limit,
            )
            # Coerce dataclass-shaped or model-shaped records to dicts.
            result = []
            for o in opps:
                if isinstance(o, dict):
                    result.append(o)
                else:
                    # dataclass / pydantic / arbitrary — best effort
                    try:
                        from dataclasses import asdict

                        result.append(asdict(o))
                    except Exception:
                        result.append({"repr": repr(o)})
            return result
        except Exception as e:
            logger.warning("get_opportunities failed: %s", e)
            return [{"error": str(e)}]

    @mcp.tool()
    async def get_journal_entries(
        agent: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """List recent trade journal entries.

        Mirrors ``GET /journal``.  Each entry carries an autopsy if the
        background autopsy job has produced one.
        """
        service = _state("journal_service")
        if service is None:
            return [{"error": "Trade journal not configured"}]
        try:
            from dataclasses import asdict

            limit = max(1, min(50, int(limit)))
            entries = await service.list_trades(agent_name=agent, limit=limit)
            return [asdict(e) for e in entries]
        except Exception as e:
            logger.warning("get_journal_entries failed: %s", e)
            return [{"error": str(e)}]

    @mcp.tool()
    async def get_brief() -> dict:
        """Return today's morning brief (generates on first call).

        Mirrors ``GET /brief``.  Returns ``{date, brief, …}`` or an error
        if no brief generator is configured.
        """
        brief_gen = _state("brief_generator")
        if brief_gen is None:
            return {"error": "Morning Brief not configured"}
        try:
            return await brief_gen.get_or_generate()
        except Exception as e:
            logger.warning("get_brief failed: %s", e)
            return {"error": str(e)}

    @mcp.tool()
    async def get_session_bias() -> dict:
        """Return today's session bias if generated, else a stub.

        Mirrors ``GET /brief/bias``.
        """
        bias_gen = _state("session_bias_generator")
        if bias_gen is None:
            return {"error": "Session Bias not configured"}
        try:
            bias = await bias_gen.get_active_bias()
            if not bias:
                return {"date": None, "bias": None, "message": "No bias generated yet today"}
            return bias.to_dict()
        except Exception as e:
            logger.warning("get_session_bias failed: %s", e)
            return {"error": str(e)}

    @mcp.tool()
    async def get_sentiment(symbol: str, max_age_seconds: int = 300) -> dict:
        """Return the freshest normalized sentiment for *symbol* (ADR-0011).

        Reads the ``intel_sentiment`` SignalBus topic.  Returns
        ``{symbol, score (-1..1), confidence (0..1), sources, age_seconds}``
        or ``{error}`` when no fresh signal exists.

        See also: ``query_signals(signal_type='intel_sentiment')`` for the
        raw signal listing.
        """
        if signal_bus is None:
            return {"error": "Signal bus not available"}
        try:
            from datetime import datetime, timezone

            signals = signal_bus.query(signal_type="intel_sentiment")
            matching = [s for s in signals if s.payload.get("symbol") == symbol]
            if not matching:
                return {"error": f"no sentiment available for {symbol}"}
            newest = max(matching, key=lambda s: s.timestamp)
            age = (datetime.now(timezone.utc) - newest.timestamp).total_seconds()
            if age > max_age_seconds:
                return {
                    "error": f"sentiment for {symbol} is stale (age={int(age)}s > max={max_age_seconds}s)"
                }
            return {**newest.payload, "age_seconds": int(age)}
        except Exception as e:
            logger.warning("get_sentiment failed: %s", e)
            return {"error": str(e)}

    @mcp.tool()
    async def get_bittensor_status() -> dict:
        """Summary of the Bittensor validator + scheduler + miner state.

        Mirrors a focused subset of ``GET /engine/v1/bittensor/status`` —
        only the fields most useful to an LLM client.  For the full
        validator dashboard payload, query the HTTP route directly.
        """
        enabled = _state("bittensor_enabled_runtime", False)
        if not enabled:
            return {"enabled": False}

        scheduler = _state("bittensor_scheduler")
        store = _state("bittensor_store")

        result: dict = {"enabled": True}
        if scheduler:
            result["scheduler_running"] = getattr(scheduler, "_running", False)
            result["direct_query_enabled"] = getattr(
                scheduler, "_direct_query_enabled", False
            )
            result["miners_in_metagraph"] = getattr(
                scheduler, "last_window_miner_count", 0
            )
            last_ok = getattr(scheduler, "last_success_at", None)
            if last_ok is not None:
                result["last_window_collected"] = last_ok.isoformat()
        if store:
            result["recent_predictions"] = len(getattr(store, "_predictions", []))
        # TaoshiBridge — the more important runtime path for v1
        bridge = _state("taoshi_bridge")
        if bridge:
            result["taoshi_bridge_running"] = getattr(bridge, "_running", False)
            result["taoshi_bridge_last_poll"] = (
                bridge.last_poll_at.isoformat()
                if getattr(bridge, "last_poll_at", None)
                else None
            )
            result["taoshi_bridge_signal_count"] = getattr(
                bridge, "signals_emitted_total", 0
            )
        return result

    return mcp
