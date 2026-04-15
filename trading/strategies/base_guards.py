"""Base-class guards that every StructuredAgent runs before scan()."""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class _KillSwitchLike(Protocol):
    is_enabled: bool
    reason: str | None


class KillSwitchGuard:
    """Blocks scan() when the risk kill-switch is active."""

    def __init__(self, kill_switch: _KillSwitchLike | None) -> None:
        self._ks = kill_switch

    async def allow_scan(self, agent_name: str) -> bool:
        if self._ks is None:
            return True
        if getattr(self._ks, "is_enabled", False):
            logger.info(
                "agent.scan_blocked agent=%s reason=%s",
                agent_name,
                getattr(self._ks, "reason", None),
            )
            return False
        return True
