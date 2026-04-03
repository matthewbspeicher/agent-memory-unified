from __future__ import annotations


class KillSwitch:
    def __init__(self) -> None:
        self._enabled = False
        self._reason: str | None = None

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def reason(self) -> str | None:
        return self._reason

    def enable(self, reason: str = "") -> None:
        self._enabled = True
        self._reason = reason

    def disable(self) -> None:
        self._enabled = False
        self._reason = None

    def toggle(self, enabled: bool, reason: str | None = None) -> None:
        self._enabled = enabled
        self._reason = reason if enabled else None
