"""Dependency injection via FastAPI app.state.

All state is stored on request.app.state. The getter functions below
extract typed references from app.state for use in route dependencies
via Depends().
"""

from fastapi import HTTPException, Request

from broker.interfaces import Broker
from agents.runner import AgentRunner
from data.events import EventBus
from storage.trades import TradeStore


def get_broker(request: Request) -> Broker:
    broker = getattr(request.app.state, "broker", None)
    if broker is None:
        raise HTTPException(500, "Broker not initialized")
    return broker


def get_agent_runner(request: Request) -> AgentRunner:
    runner = getattr(request.app.state, "agent_runner", None)
    if runner is None:
        raise HTTPException(500, "AgentRunner not initialized")
    return runner


def get_opportunity_store(request: Request):
    store = getattr(request.app.state, "opportunity_store", None)
    if store is None:
        raise HTTPException(500, "Opportunity store not initialized")
    return store


def get_risk_engine(request: Request):
    engine = getattr(request.app.state, "risk_engine", None)
    if engine is None:
        raise HTTPException(500, "Risk engine not initialized")
    return engine


def get_risk_analytics(request: Request):
    return getattr(request.app.state, "risk_analytics", None)


def get_event_bus(request: Request) -> EventBus:
    bus = getattr(request.app.state, "event_bus", None)
    if bus is None:
        raise HTTPException(500, "EventBus not initialized")
    return bus


def get_trade_store(request: Request) -> TradeStore:
    store = getattr(request.app.state, "trade_store", None)
    if store is None:
        raise HTTPException(500, "TradeStore not initialized")
    return store


async def check_kill_switch(request: Request):
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return  # No Redis = no kill switch enforcement
    is_active = await redis.get("kill_switch:active")
    if is_active == "true" and request.method != "GET":
        raise HTTPException(503, "Trading is currently halted via global kill-switch")


# Legacy no-op setters — kept for ServiceContainer compatibility (api/container.py).
# Live app uses app.state directly (see api/app.py lifespan).
def set_broker(broker: Broker) -> None:
    pass


def set_agent_runner(runner: AgentRunner) -> None:
    pass


def set_opportunity_store(store) -> None:
    pass


def set_risk_engine(engine) -> None:
    pass


def set_event_bus(bus: EventBus) -> None:
    pass


def set_trade_store(store: TradeStore) -> None:
    pass
