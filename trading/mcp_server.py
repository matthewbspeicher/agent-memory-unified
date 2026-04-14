"""MCP Tool Server — exposes trading engine operations as MCP tools.

This module creates a FastMCP server that makes key trading engine
operations available to MCP-compatible AI agents.  The server runs
alongside the FastAPI app and shares its lifespan.

Usage with FastAPI::

    from mcp_server import create_mcp_server
    mcp = create_mcp_server()
    mcp_app = mcp.http_app(path='/mcp')
    # In app lifespan: app.mount('/mcp', mcp_app)

Tools exposed:
    - query_signals: Query recent signals from the signal bus
    - agent_status: List running agents and their status
    - publish_signal: Publish a typed signal to the bus
    - get_regime: Current market regime
    - get_positions: Open positions from broker
    - health_check: Engine health status
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
) -> FastMCP:
    """Create and return the MCP server with trading engine tools.

    Args:
        signal_bus: SignalBus instance for querying/publishing signals.
        agent_runner: AgentRunner instance for agent status queries.
        broker: Broker interface for position/order queries.
        regime_manager: RegimeManager for market regime queries.

    Returns:
        Configured FastMCP server instance.
    """
    mcp = FastMCP("trading-engine")

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

    return mcp
