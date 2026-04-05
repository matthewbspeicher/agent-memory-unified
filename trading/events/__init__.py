# trading/events/__init__.py
from .consumer import EventConsumer, handle_agent_deactivated

__all__ = ["EventConsumer", "handle_agent_deactivated"]
