"""ExitManager — attaches, checks, and persists exit rules for open positions."""

from __future__ import annotations

import logging
import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from exits.rules import (
    ExitRule,
    StopLoss,
    TakeProfit,
    TrailingStop,
    TimeExit,
    PredictionTimeExit,
    PreExpiryExit,
    ProbabilityTrailingStop,
    ThetaDecayExit,
    parse_rule,
)
from broker.models import AssetType

logger = logging.getLogger(__name__)


class ExitManager:
    """Manages exit rules per open position.

    attach() and detach() are async because they call the persistent store.
    check() is synchronous — it reads from the in-memory cache.
    """

    def __init__(self, store=None) -> None:
        # position_id -> list of exit rules (in-memory cache)
        self._rules: dict[str | int, list[ExitRule]] = {}
        self._durable_rules: dict[str | int, list[dict]] = {}
        self._store = store
        self._mutation_lock = asyncio.Lock()

    async def attach(self, position_id: str | int, rules: list[ExitRule]) -> None:
        """Explicitly replace rules, committing persistence before publishing cache."""
        async with self._mutation_lock:
            if self._store:
                await self._store.save(position_id, [r.to_dict() for r in rules])
            self._rules[position_id] = rules
            self._durable_rules[position_id] = [rule.to_dict() for rule in rules]

    async def ensure_rules(self, position_id: str | int, rules: list[ExitRule]) -> None:
        """Install initial rules once without resetting trailing state on retries.

        The store atomically retains whichever initial rules were persisted first.
        An existing cache may hold newer trailing marks and must not be replaced
        by the initial durable snapshot during repeated fill reconciliation.
        """
        async with self._mutation_lock:
            if position_id in self._rules:
                return
            if self._store:
                serialized = await self._store.ensure(
                    position_id, [rule.to_dict() for rule in rules]
                )
                restored = [parse_rule(value) for value in serialized]
                if any(rule is None for rule in restored):
                    raise ValueError(
                        "Persisted exit rules contain an unknown rule type"
                    )
                self._rules[position_id] = restored
                self._durable_rules[position_id] = serialized
            else:
                self._rules[position_id] = rules

    async def hydrate_rules(self, position_id: str | int) -> bool:
        """Read missing durable protection without initializing or resetting rules.

        Another worker may have completed the entry since this manager started.
        Missing rules are retried on later scans; never persist an empty default.
        """
        async with self._mutation_lock:
            if position_id in self._rules:
                return True
            if self._store is None:
                return False
            raw = await self._store.load_all()
            if position_id not in raw:
                return False
            serialized = raw[position_id]
            restored = [parse_rule(value) for value in serialized]
            if any(rule is None for rule in restored):
                raise ValueError("Persisted exit rules contain an unknown rule type")
            self._rules[position_id] = restored
            self._durable_rules[position_id] = serialized
            return True

    async def reconcile_position(self, position_id: str | int, rules: list[ExitRule]) -> None:
        """Reconcile rules with durable position state, including stale-worker retries."""
        if self._store is None:
            raise RuntimeError("Position reconciliation requires durable storage")
        async with self._mutation_lock:
            serialized = await self._store.sync_position(
                position_id, [rule.to_dict() for rule in rules]
            )
            if serialized is None:
                self._rules.pop(position_id, None)
                self._durable_rules.pop(position_id, None)
                return
            if position_id in self._rules and self._durable_rules.get(position_id) == serialized:
                return  # Keep locally advanced trailing marks for unchanged rules.
            restored = [parse_rule(value) for value in serialized]
            if any(rule is None for rule in restored):
                raise ValueError("Persisted exit rules contain an unknown rule type")
            self._rules[position_id] = restored
            self._durable_rules[position_id] = serialized

    async def detach(self, position_id: str | int) -> None:
        """Remove durable rules before removing the active local protection."""
        async with self._mutation_lock:
            if self._store:
                await self._store.delete(position_id)
            self._rules.pop(position_id, None)
            self._durable_rules.pop(position_id, None)

    async def load_rules(self) -> None:
        """Restore persisted exit rules into the in-memory cache on startup."""
        if not self._store or not hasattr(self._store, "load_all"):
            return
        async with self._mutation_lock:
            raw_rules = await self._store.load_all()
            restored: dict[str | int, list[ExitRule]] = {}
            for position_id, serialized_rules in raw_rules.items():
                parsed = [
                    rule
                    for rule in (parse_rule(d) for d in serialized_rules)
                    if rule is not None
                ]
                restored[position_id] = parsed
            self._rules = restored
            self._durable_rules = raw_rules

    def check(
        self,
        position_id: str | int,
        current_price: Decimal,
        current_time: datetime | None = None,
        entry_price: Decimal | None = None,
        side: str = "BUY",
    ) -> ExitRule | None:
        """Return the first triggered rule, or None if position should stay open.

        entry_price and side are forwarded to rules that need position context
        (e.g. PredictionTimeExit).
        """
        rules = self._rules.get(position_id)
        if not rules:
            return None
        now = current_time or datetime.now(timezone.utc)
        for rule in rules:
            kwargs: dict = {"current_price": current_price}
            if isinstance(rule, (TimeExit, PredictionTimeExit, PreExpiryExit)):
                kwargs["current_time"] = now
            if isinstance(rule, PredictionTimeExit):
                if entry_price is not None:
                    kwargs["entry_price"] = entry_price
                kwargs["side"] = side
            if rule.should_exit(**kwargs):
                return rule
        return None

    def update_trailing(self, position_id: str | int, current_price: Decimal) -> None:
        """Update trailing-stop high-water marks for a position."""
        for rule in self._rules.get(position_id, []):
            if isinstance(rule, (TrailingStop, ProbabilityTrailingStop)):
                rule.update(current_price)

    def compute_default_exits(
        self,
        side: str,
        entry_price: Decimal,
        atr: Decimal | None = None,
        asset_type: AssetType | None = None,
        contract_expires_at: datetime | None = None,
    ) -> list[ExitRule]:
        """Build a default set of exit rules from entry parameters.

        For prediction markets: uses PreExpiryExit + ProbabilityTrailingStop.
        For equities/others: uses ATR-based or percentage-based stop/target/trail.
        """
        if asset_type == AssetType.PREDICTION:
            rules: list[ExitRule] = []
            if contract_expires_at:
                rules.append(
                    ThetaDecayExit(
                        entry_price=entry_price,
                        profit_target_pct=0.50,
                        stop_loss_pct=2.0,
                        min_dte=2,
                        expires_at=contract_expires_at,
                        side=side,
                    )
                )
                rules.append(
                    PreExpiryExit(
                        expires_at=contract_expires_at,
                        hours_before_expiry=4.0,
                    )
                )
            rules.append(ProbabilityTrailingStop(trail_pp=20.0, side=side))
            return rules

        if atr and atr > 0:
            stop_d = atr * Decimal("2")
            target_d = atr * Decimal("3")
        else:
            stop_d = entry_price * Decimal("0.02")
            target_d = entry_price * Decimal("0.03")

        rules = []
        if side == "BUY":
            rules.append(StopLoss(stop_price=entry_price - stop_d, side="BUY"))
            rules.append(TakeProfit(target_price=entry_price + target_d, side="BUY"))
        else:
            rules.append(StopLoss(stop_price=entry_price + stop_d, side="SELL"))
            rules.append(TakeProfit(target_price=entry_price - target_d, side="SELL"))
        rules.append(TrailingStop(trail_pct=Decimal("0.05"), side=side))
        return rules
