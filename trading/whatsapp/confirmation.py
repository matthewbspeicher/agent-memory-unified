from __future__ import annotations
import secrets
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PendingAction:
    action_type: str
    data: dict[str, Any]
    token: str
    created_at: float = field(default_factory=time.time)


class ConfirmationGate:
    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self._pending: dict[str, PendingAction] = {}
        self._ttl = ttl_seconds

    def _generate_token(self, action_type: str) -> str:
        prefix = action_type[:3].upper()
        suffix = secrets.token_hex(2).upper()
        return f"{prefix}-{suffix}"

    def _is_expired(self, action: PendingAction) -> bool:
        return time.time() - action.created_at > self._ttl

    def create(self, phone: str, action_type: str, data: dict[str, Any]) -> str:
        token = self._generate_token(action_type)
        self._pending[phone] = PendingAction(
            action_type=action_type,
            data=data,
            token=token,
        )
        return token

    def has_pending(self, phone: str) -> bool:
        action = self._pending.get(phone)
        if not action:
            return False
        if self._is_expired(action):
            del self._pending[phone]
            return False
        return True

    def confirm(self, phone: str, token: str) -> PendingAction | None:
        action = self._pending.get(phone)
        if not action or self._is_expired(action):
            self._pending.pop(phone, None)
            return None

        token_upper = token.upper()
        # Allow exact token match OR generic approval keywords if there is an active pending action
        if action.token != token_upper and token_upper not in ("APPROVE", "YES"):
            return None

        del self._pending[phone]
        return action

    def cancel(self, phone: str) -> bool:
        return self._pending.pop(phone, None) is not None
