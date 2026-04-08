"""Exit rules: StopLoss, TakeProfit, TrailingStop, TimeExit."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


class ExitRule(ABC):
    """Base class for all exit rules."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique rule identifier."""

    @abstractmethod
    def should_exit(self, current_price: Decimal, **kwargs: Any) -> bool:
        """Return True when the position should be exited."""

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict for persistence."""

    @property
    def exit_fraction(self) -> float:
        """Fraction of position to close (1.0 = full exit, <1.0 = partial)."""
        return 1.0


@dataclass
class StopLoss(ExitRule):
    """Exit when price crosses the stop threshold.

    For BUY positions: exit if price falls below stop_price.
    For SELL positions: exit if price rises above stop_price.
    """

    stop_price: Decimal
    side: str = "BUY"

    @property
    def name(self) -> str:
        return "stop_loss"

    def should_exit(self, current_price: Decimal, **kwargs: Any) -> bool:
        if self.side == "SELL":
            return current_price >= self.stop_price
        return current_price <= self.stop_price

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "stop_loss",
            "stop_price": str(self.stop_price),
            "side": self.side,
        }


@dataclass
class TakeProfit(ExitRule):
    """Exit when price crosses the profit target.

    For BUY positions: exit if price rises above target_price.
    For SELL positions: exit if price falls below target_price.
    """

    target_price: Decimal
    side: str = "BUY"

    @property
    def name(self) -> str:
        return "take_profit"

    def should_exit(self, current_price: Decimal, **kwargs: Any) -> bool:
        if self.side == "SELL":
            return current_price <= self.target_price
        return current_price >= self.target_price

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "take_profit",
            "target_price": str(self.target_price),
            "side": self.side,
        }


@dataclass
class TrailingStop(ExitRule):
    """Exit when price retraces more than trail_pct from the observed peak.

    Tracks a running peak; call update() each time you have a new price.
    """

    trail_pct: Decimal
    side: str = "BUY"
    _peak: Decimal = field(default=Decimal("0"), init=False, repr=False)

    @property
    def name(self) -> str:
        return "trailing_stop"

    def update(self, current_price: Decimal) -> None:
        """Update the trailing high-water mark (BUY) or low-water mark (SELL)."""
        if self.side == "SELL":
            if self._peak <= 0 or current_price < self._peak:
                self._peak = current_price
        else:
            if current_price > self._peak:
                self._peak = current_price

    def should_exit(self, current_price: Decimal, **kwargs: Any) -> bool:
        if self._peak <= 0:
            return False
        if self.side == "SELL":
            stop = self._peak * (Decimal("1") + self.trail_pct)
            return current_price >= stop
        stop = self._peak * (Decimal("1") - self.trail_pct)
        return current_price <= stop

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "trailing_stop",
            "trail_pct": str(self.trail_pct),
            "side": self.side,
            "peak": str(self._peak),
        }


@dataclass
class TimeExit(ExitRule):
    """Exit after a fixed expiry datetime, regardless of price."""

    expires_at: datetime

    @property
    def name(self) -> str:
        return "time_exit"

    def should_exit(
        self,
        current_price: Decimal,
        current_time: datetime | None = None,
        **kwargs: Any,
    ) -> bool:
        now = current_time or datetime.now(timezone.utc)
        # Normalise to tz-aware
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return now >= expires

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "time_exit",
            "expires_at": self.expires_at.isoformat(),
        }


@dataclass
class PredictionTimeExit(ExitRule):
    """Exit a losing prediction market position within N days of expiry."""

    expires_at: datetime
    max_days_to_expiry: int = 2

    @property
    def name(self) -> str:
        return "prediction_time_exit"

    def should_exit(
        self,
        current_price: Decimal,
        entry_price: Decimal | None = None,
        side: str = "BUY",
        current_time: datetime | None = None,
        **kwargs: Any,
    ) -> bool:
        if entry_price is None:
            return False  # need entry price to know if losing

        is_losing = False
        if side == "BUY":
            is_losing = current_price < entry_price
        else:
            is_losing = current_price > entry_price

        if not is_losing:
            return False

        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)

        days_remaining = (expires - now).total_seconds() / 86400
        # If already expired, TimeExit should catch it, but we can catch it too
        return days_remaining <= self.max_days_to_expiry

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "prediction_time_exit",
            "expires_at": self.expires_at.isoformat(),
            "max_days_to_expiry": self.max_days_to_expiry,
        }


@dataclass
class PreExpiryExit(ExitRule):
    """
    Exit a prediction market position unconditionally when fewer than
    `hours_before_expiry` hours remain before contract expiry.

    Unlike PredictionTimeExit, this fires regardless of P&L.
    Intended to capture remaining liquidity premium before binary resolution.
    """

    expires_at: datetime
    hours_before_expiry: float = 4.0

    @property
    def name(self) -> str:
        return "pre_expiry_exit"

    def should_exit(
        self,
        current_price: Decimal,
        current_time: datetime | None = None,
        **kwargs: Any,
    ) -> bool:
        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        hours_remaining = (expires - now).total_seconds() / 3600
        # Use a small tolerance (1 second) to handle "expiring right now" edge case
        return -1 / 3600 <= hours_remaining <= self.hours_before_expiry

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "pre_expiry_exit",
            "expires_at": self.expires_at.isoformat(),
            "hours_before_expiry": self.hours_before_expiry,
        }


@dataclass
class ProbabilityTrailingStop(ExitRule):
    """
    Trailing stop expressed in probability percentage points (not price pct).

    trail_pp: number of percentage points the market must retrace from peak
              before triggering (e.g. 15 means 15pp, i.e. 0.15 on a 0-1 scale).

    Optionally ignores signals when current_price is within `quiet_zone`
    of 0 or 1 (default 0.05) to avoid noise during terminal convergence.
    """

    trail_pp: float
    side: str = "BUY"
    quiet_zone: float = 0.05
    _peak: float = field(default=0.0, init=False, repr=False)

    @property
    def name(self) -> str:
        return "probability_trailing_stop"

    def update(self, current_price: Decimal) -> None:
        p = float(current_price)
        if p > self._peak:
            self._peak = p

    def should_exit(self, current_price: Decimal, **kwargs: Any) -> bool:
        if self._peak <= 0:
            return False
        p = float(current_price)
        if p < self.quiet_zone or p > (1.0 - self.quiet_zone):
            return False
        stop = self._peak - (self.trail_pp / 100.0)
        return p <= stop

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "probability_trailing_stop",
            "trail_pp": self.trail_pp,
            "side": self.side,
            "quiet_zone": self.quiet_zone,
            "peak": self._peak,
        }


@dataclass
class PartialExitRule(ExitRule):
    """
    Exit a fraction of the position when the market reaches a target probability.

    fraction: portion of remaining position to close (0.0–1.0), e.g. 0.5 = half.
    target_price: probability at which to trigger, e.g. Decimal("0.80").
    side: "BUY" (long YES position) or "SELL" (short/NO position).
    _triggered: internal flag to prevent re-firing after the first trigger.
    """

    target_price: Decimal
    fraction: float
    side: str = "BUY"
    _triggered: bool = field(default=False, init=False, repr=False)

    @property
    def name(self) -> str:
        return "partial_exit"

    @property
    def exit_fraction(self) -> float:
        return self.fraction

    def should_exit(self, current_price: Decimal, **kwargs: Any) -> bool:
        if self._triggered:
            return False
        if self.side == "BUY":
            return current_price >= self.target_price
        return current_price <= self.target_price

    def mark_triggered(self) -> None:
        self._triggered = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "partial_exit",
            "target_price": str(self.target_price),
            "fraction": self.fraction,
            "side": self.side,
            "triggered": self._triggered,
        }


@dataclass
class ConvictionExitRule(ExitRule):
    """Exit when the market disagrees with entry thesis by divergence_threshold.

    When implemented, re-evaluates the agent's original thesis
    against current market price.
    """

    original_confidence: float
    entry_price: Decimal
    divergence_threshold: float
    agent_name: str
    side: str = "BUY"

    @property
    def name(self) -> str:
        return "conviction_exit"

    def should_exit(self, current_price: Decimal, **kwargs: Any) -> bool:
        # Phase 1: simple divergence check (no LLM)
        # market moved against thesis by more than threshold
        if self.side == "BUY":
            implied_shift = float(self.entry_price - current_price) * 100
        else:
            implied_shift = float(current_price - self.entry_price) * 100

        return implied_shift > self.divergence_threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "conviction_exit",
            "original_confidence": self.original_confidence,
            "entry_price": str(self.entry_price),
            "divergence_threshold": self.divergence_threshold,
            "agent_name": self.agent_name,
            "side": self.side,
        }


@dataclass
class StagnationExitRule(ExitRule):
    """Exit if the position does not reach a minimum profit percentage within a certain time frame."""

    entry_time: datetime
    max_stagnation_minutes: int
    min_profit_pct: Decimal
    entry_price: Decimal
    side: str = "BUY"

    @property
    def name(self) -> str:
        return "stagnation_exit"

    def should_exit(
        self,
        current_price: Decimal,
        current_time: datetime | None = None,
        **kwargs: Any,
    ) -> bool:
        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        entry = self.entry_time
        if entry.tzinfo is None:
            entry = entry.replace(tzinfo=timezone.utc)

        minutes_elapsed = (now - entry).total_seconds() / 60.0
        if minutes_elapsed < self.max_stagnation_minutes:
            return False

        if self.side == "BUY":
            profit_pct = (current_price - self.entry_price) / self.entry_price
        else:
            profit_pct = (self.entry_price - current_price) / self.entry_price

        return profit_pct < self.min_profit_pct

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "stagnation_exit",
            "entry_time": self.entry_time.isoformat(),
            "max_stagnation_minutes": self.max_stagnation_minutes,
            "min_profit_pct": str(self.min_profit_pct),
            "entry_price": str(self.entry_price),
            "side": self.side,
        }


def parse_rule(d: dict[str, Any]) -> ExitRule | None:
    """Reconstruct an ExitRule from a dictionary."""
    t = d.get("type")
    if t == "stop_loss":
        return StopLoss(stop_price=Decimal(d["stop_price"]), side=d.get("side", "BUY"))
    elif t == "take_profit":
        return TakeProfit(
            target_price=Decimal(d["target_price"]), side=d.get("side", "BUY")
        )
    elif t == "trailing_stop":
        r = TrailingStop(
            trail_pct=Decimal(d["trail_pct"]), side=d.get("side", "BUY")
        )
        r._peak = Decimal(d.get("peak", "0"))
        return r
    elif t == "time_exit":
        return TimeExit(expires_at=datetime.fromisoformat(d["expires_at"]))
    elif t == "prediction_time_exit":
        return PredictionTimeExit(
            expires_at=datetime.fromisoformat(d["expires_at"]),
            max_days_to_expiry=d.get("max_days_to_expiry", 2),
        )
    elif t == "conviction_exit":
        return ConvictionExitRule(
            original_confidence=d["original_confidence"],
            entry_price=Decimal(d["entry_price"]),
            divergence_threshold=d["divergence_threshold"],
            agent_name=d["agent_name"],
            side=d.get("side", "BUY"),
        )
    elif t == "stagnation_exit":
        return StagnationExitRule(
            entry_time=datetime.fromisoformat(d["entry_time"]),
            max_stagnation_minutes=d["max_stagnation_minutes"],
            min_profit_pct=Decimal(d["min_profit_pct"]),
            entry_price=Decimal(d["entry_price"]),
            side=d.get("side", "BUY"),
        )
    elif t == "pre_expiry_exit":
        return PreExpiryExit(
            expires_at=datetime.fromisoformat(d["expires_at"]),
            hours_before_expiry=d.get("hours_before_expiry", 4.0),
        )
    elif t == "probability_trailing_stop":
        r = ProbabilityTrailingStop(
            trail_pp=d["trail_pp"],
            side=d.get("side", "BUY"),
            quiet_zone=d.get("quiet_zone", 0.05),
        )
        r._peak = d.get("peak", 0.0)
        return r
    elif t == "partial_exit":
        r2 = PartialExitRule(
            target_price=Decimal(d["target_price"]),
            fraction=d["fraction"],
            side=d.get("side", "BUY"),
        )
        if d.get("triggered", False):
            r2.mark_triggered()
        return r2
    return None
