"""Dependency injection via FastAPI app.state.

All state is stored on request.app.state. The getter functions below
extract typed references from app.state for use in route dependencies.

NOTE: The setter functions below are DEPRECATED. State should be set
directly on app.state in the lifespan or startup functions.
"""

from broker.interfaces import Broker
from agents.runner import AgentRunner
from data.events import EventBus
from storage.trades import TradeStore


def get_broker() -> Broker:

    # Actual implementation uses Depends - see api/dependencies.py
    raise NotImplementedError("Use get_broker from api.dependencies instead")


def get_agent_runner() -> AgentRunner:

    raise NotImplementedError("Use get_agent_runner from api.dependencies instead")


def get_opportunity_store():
    raise NotImplementedError("Use get_opportunity_store from api.dependencies instead")


def get_risk_engine():
    raise NotImplementedError("Use get_risk_engine from api.dependencies instead")


def get_risk_analytics():
    raise NotImplementedError("Use get_risk_analytics from api.dependencies instead")


def get_event_bus() -> EventBus:
    raise NotImplementedError("Use get_event_bus from api.dependencies instead")


def get_trade_store() -> TradeStore:
    raise NotImplementedError("Use get_trade_store from api.dependencies instead")


def check_kill_switch():
    raise NotImplementedError("Use check_kill_switch from api.dependencies instead")


# Backward compatibility setters - DEPRECATED
def set_broker(broker: Broker) -> None:
    import warnings

    warnings.warn(
        "set_broker is deprecated. Set broker directly on app.state in startup.",
        DeprecationWarning,
        stacklevel=2,
    )


def set_agent_runner(runner: AgentRunner) -> None:
    import warnings

    warnings.warn(
        "set_agent_runner is deprecated. Set runner directly on app.state in startup.",
        DeprecationWarning,
        stacklevel=2,
    )


def set_opportunity_store(store) -> None:
    import warnings

    warnings.warn(
        "set_opportunity_store is deprecated. Set store directly on app.state in startup.",
        DeprecationWarning,
        stacklevel=2,
    )


def set_risk_engine(engine) -> None:
    import warnings

    warnings.warn(
        "set_risk_engine is deprecated. Set engine directly on app.state in startup.",
        DeprecationWarning,
        stacklevel=2,
    )


def set_event_bus(bus: EventBus) -> None:
    import warnings

    warnings.warn(
        "set_event_bus is deprecated. Set bus directly on app.state in startup.",
        DeprecationWarning,
        stacklevel=2,
    )


def set_trade_store(store: TradeStore) -> None:
    import warnings

    warnings.warn(
        "set_trade_store is deprecated. Set store directly on app.state in startup.",
        DeprecationWarning,
        stacklevel=2,
    )
