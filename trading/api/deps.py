"""Dependency injection using app.state with module-level cache."""

from broker.interfaces import Broker
from agents.runner import AgentRunner
from data.events import EventBus
from storage.trades import TradeStore

# Module-level reference to app.state (set once during startup)
_app_state = None


def _init_state(state):
    """Initialize module with app.state reference. Called from lifespan."""
    global _app_state
    _app_state = state


def get_broker() -> Broker:
    if _app_state is None:
        raise RuntimeError("deps not initialized")
    broker = getattr(_app_state, "broker", None)
    if broker is None:
        raise RuntimeError("Broker not initialized")
    return broker


def get_agent_runner() -> AgentRunner:
    if _app_state is None:
        raise RuntimeError("deps not initialized")
    runner = getattr(_app_state, "agent_runner", None)
    if runner is None:
        raise RuntimeError("AgentRunner not initialized")
    return runner


def get_opportunity_store():
    if _app_state is None:
        raise RuntimeError("deps not initialized")
    store = getattr(_app_state, "opportunity_store", None)
    if store is None:
        raise RuntimeError("Opportunity store not initialized")
    return store


def get_risk_engine():
    if _app_state is None:
        raise RuntimeError("deps not initialized")
    engine = getattr(_app_state, "risk_engine", None)
    if engine is None:
        raise RuntimeError("Risk engine not initialized")
    return engine


def get_event_bus() -> EventBus:
    if _app_state is None:
        raise RuntimeError("deps not initialized")
    bus = getattr(_app_state, "event_bus", None)
    if bus is None:
        raise RuntimeError("EventBus not initialized")
    return bus


def get_trade_store() -> TradeStore:
    if _app_state is None:
        raise RuntimeError("deps not initialized")
    store = getattr(_app_state, "trade_store", None)
    if store is None:
        raise RuntimeError("TradeStore not initialized")
    return store


# Backward compatibility setters (no-ops now - everything uses app.state)
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
