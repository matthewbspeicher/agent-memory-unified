"""Tests for StrategyHealthEngine — transition logic, recovery, and cooldown."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from storage.db import init_db
from storage.strategy_health import StrategyHealthStore
from storage.performance import PerformanceSnapshot, PerformanceStore
from learning.strategy_health import (
    StrategyHealthConfig,
    StrategyHealthEngine,
    StrategyHealthStatus,
    _compute_expectancy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _snapshot(
    agent_name: str = "rsi",
    win_rate: float = 0.55,
    avg_win: float = 150.0,
    avg_loss: float = 80.0,
    max_drawdown: float = 500.0,
    total_trades: int = 30,
    profit_factor: float = 1.5,
) -> PerformanceSnapshot:
    return PerformanceSnapshot(
        agent_name=agent_name,
        timestamp=datetime.now(timezone.utc),
        opportunities_generated=total_trades,
        opportunities_executed=total_trades,
        win_rate=win_rate,
        avg_win=Decimal(str(avg_win)),
        avg_loss=Decimal(str(avg_loss)),
        max_drawdown=max_drawdown,
        profit_factor=profit_factor,
        total_trades=total_trades,
    )


def _cfg(**overrides) -> StrategyHealthConfig:
    defaults = dict(
        enabled=True,
        default_min_trade_count=20,
        default_expectancy_floor=0.0,
        default_drawdown_limit=5000.0,
        cooldown_hours=0,  # disable cooldown for tests
        throttle_multiplier=0.5,
    )
    defaults.update(overrides)
    return StrategyHealthConfig(**defaults)


async def _make_engine(db, cfg: StrategyHealthConfig | None = None, snapshot=None):
    health_store = StrategyHealthStore(db)
    perf_store = MagicMock(spec=PerformanceStore)
    if snapshot is None:
        snapshot = _snapshot()
    perf_store.get_latest = AsyncMock(return_value=snapshot)
    engine = StrategyHealthEngine(
        health_store=health_store,
        perf_store=perf_store,
        config=cfg or _cfg(),
    )
    return engine, health_store


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_db(conn)
    yield conn
    await conn.close()


# ---------------------------------------------------------------------------
# Unit: _compute_expectancy
# ---------------------------------------------------------------------------


class TestComputeExpectancy:
    def test_positive_expectancy(self):
        result = _compute_expectancy(avg_win=150.0, avg_loss=80.0, win_rate=0.6)
        assert result == pytest.approx(0.6 * 150.0 - 0.4 * 80.0)

    def test_zero_expectancy(self):
        # 50% win rate, symmetric wins and losses
        result = _compute_expectancy(avg_win=100.0, avg_loss=100.0, win_rate=0.5)
        assert result == pytest.approx(0.0)

    def test_negative_expectancy(self):
        result = _compute_expectancy(avg_win=50.0, avg_loss=200.0, win_rate=0.3)
        assert result < 0


# ---------------------------------------------------------------------------
# Unit: StrategyHealthStatus enum
# ---------------------------------------------------------------------------


class TestStrategyHealthStatus:
    def test_enum_values(self):
        assert StrategyHealthStatus.NORMAL.value == "normal"
        assert StrategyHealthStatus.WATCHLIST.value == "watchlist"
        assert StrategyHealthStatus.THROTTLED.value == "throttled"
        assert StrategyHealthStatus.SHADOW_ONLY.value == "shadow_only"
        assert StrategyHealthStatus.RETIRED.value == "retired"

    def test_string_construction(self):
        assert StrategyHealthStatus("throttled") == StrategyHealthStatus.THROTTLED


# ---------------------------------------------------------------------------
# Unit: StrategyHealthConfig
# ---------------------------------------------------------------------------


class TestStrategyHealthConfig:
    def test_defaults(self):
        cfg = StrategyHealthConfig()
        assert cfg.enabled is True
        assert cfg.default_min_trade_count == 20
        assert cfg.cooldown_hours == 24
        assert cfg.throttle_multiplier == 0.5

    def test_from_learning_config_with_none(self):
        cfg = StrategyHealthConfig.from_learning_config(None)
        assert cfg.enabled is True

    def test_from_learning_config_with_pydantic(self):
        from learning.config import StrategyHealthConfig as _PydanticCfg

        pydantic_cfg = _PydanticCfg(enabled=False, cooldown_hours=48)
        cfg = StrategyHealthConfig.from_learning_config(pydantic_cfg)
        assert cfg.enabled is False
        assert cfg.cooldown_hours == 48


# ---------------------------------------------------------------------------
# Integration: state transitions
# ---------------------------------------------------------------------------


class TestStateTransitions:
    async def test_insufficient_trades_stays_normal(self, db):
        snap = _snapshot(total_trades=5)  # below default min of 20
        engine, _ = await _make_engine(db, snapshot=snap)
        status = await engine.evaluate("rsi")
        assert status == StrategyHealthStatus.NORMAL

    async def test_normal_to_watchlist_on_bad_expectancy(self, db):
        # avg_win < avg_loss, win rate 40% → negative expectancy
        snap = _snapshot(win_rate=0.4, avg_win=50.0, avg_loss=200.0, total_trades=30)
        engine, _ = await _make_engine(db, snapshot=snap)
        status = await engine.evaluate("rsi")
        assert status == StrategyHealthStatus.WATCHLIST

    async def test_watchlist_to_throttled_on_continued_bad_metrics(self, db):
        snap = _snapshot(win_rate=0.35, avg_win=40.0, avg_loss=200.0, total_trades=30)
        engine, health_store = await _make_engine(db, snapshot=snap)
        # First transition: normal → watchlist
        await engine.evaluate("rsi")
        # Second transition: watchlist → throttled
        status = await engine.evaluate("rsi")
        assert status == StrategyHealthStatus.THROTTLED

    async def test_throttled_to_shadow_on_continued_poor_metrics_with_drawdown(
        self, db
    ):
        snap = _snapshot(
            win_rate=0.3,
            avg_win=30.0,
            avg_loss=300.0,
            max_drawdown=6000.0,
            total_trades=40,
        )
        engine, health_store = await _make_engine(db, snapshot=snap)
        await engine.evaluate("rsi")  # → watchlist
        await engine.evaluate("rsi")  # → throttled
        status = await engine.evaluate("rsi")  # → shadow_only
        assert status == StrategyHealthStatus.SHADOW_ONLY

    async def test_shadow_to_retired_on_sustained_underperformance(self, db):
        snap = _snapshot(
            win_rate=0.25,
            avg_win=20.0,
            avg_loss=400.0,
            max_drawdown=6000.0,
            total_trades=50,
        )
        engine, _ = await _make_engine(db, snapshot=snap)
        await engine.evaluate("rsi")  # → watchlist
        await engine.evaluate("rsi")  # → throttled
        await engine.evaluate("rsi")  # → shadow_only
        status = await engine.evaluate("rsi")  # → retired
        assert status == StrategyHealthStatus.RETIRED

    async def test_watchlist_recovers_to_normal(self, db):
        bad_snap = _snapshot(
            win_rate=0.35, avg_win=40.0, avg_loss=200.0, total_trades=30
        )
        good_snap = _snapshot(
            win_rate=0.6, avg_win=150.0, avg_loss=80.0, total_trades=30
        )

        health_store = StrategyHealthStore(db)
        perf_store = MagicMock(spec=PerformanceStore)
        engine = StrategyHealthEngine(
            health_store=health_store, perf_store=perf_store, config=_cfg()
        )

        perf_store.get_latest = AsyncMock(return_value=bad_snap)
        await engine.evaluate("rsi")  # → watchlist

        perf_store.get_latest = AsyncMock(return_value=good_snap)
        status = await engine.evaluate("rsi")  # → normal
        assert status == StrategyHealthStatus.NORMAL

    async def test_throttled_recovers_to_normal(self, db):
        bad_snap = _snapshot(
            win_rate=0.35, avg_win=40.0, avg_loss=200.0, total_trades=30
        )
        good_snap = _snapshot(
            win_rate=0.65, avg_win=180.0, avg_loss=70.0, total_trades=35
        )

        health_store = StrategyHealthStore(db)
        perf_store = MagicMock(spec=PerformanceStore)
        engine = StrategyHealthEngine(
            health_store=health_store, perf_store=perf_store, config=_cfg()
        )

        perf_store.get_latest = AsyncMock(return_value=bad_snap)
        await engine.evaluate("rsi")  # → watchlist
        await engine.evaluate("rsi")  # → throttled

        perf_store.get_latest = AsyncMock(return_value=good_snap)
        status = await engine.evaluate("rsi")  # → normal
        assert status == StrategyHealthStatus.NORMAL


# ---------------------------------------------------------------------------
# Cooldown enforcement
# ---------------------------------------------------------------------------


class TestCooldown:
    async def test_cooldown_prevents_retransition(self, db):
        snap = _snapshot(win_rate=0.35, avg_win=40.0, avg_loss=200.0, total_trades=30)
        # Use real cooldown hours so transitions are blocked
        cfg = _cfg(cooldown_hours=24)
        engine, health_store = await _make_engine(db, cfg=cfg, snapshot=snap)

        await engine.evaluate("rsi")  # → watchlist
        # Without cooldown passing, second call stays watchlist (not throttled)
        status = await engine.evaluate("rsi")
        assert status == StrategyHealthStatus.WATCHLIST

    async def test_expired_cooldown_allows_transition(self, db):
        snap = _snapshot(win_rate=0.35, avg_win=40.0, avg_loss=200.0, total_trades=30)
        cfg = _cfg(cooldown_hours=24)
        engine, health_store = await _make_engine(db, cfg=cfg, snapshot=snap)

        await engine.evaluate("rsi")  # → watchlist
        # Manually expire cooldown
        past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        await health_store.upsert_status("rsi", "watchlist", cooldown_until=past)

        status = await engine.evaluate("rsi")  # can transition again
        assert status == StrategyHealthStatus.THROTTLED


# ---------------------------------------------------------------------------
# Manual overrides respected
# ---------------------------------------------------------------------------


class TestManualOverride:
    async def test_manual_override_not_overwritten_by_evaluate(self, db):
        snap = _snapshot(win_rate=0.35, avg_win=40.0, avg_loss=200.0, total_trades=30)
        engine, health_store = await _make_engine(db, snapshot=snap)

        # Operator manually sets to retired
        await health_store.set_override("rsi", "retired", actor="operator")

        # evaluate should not change it (manual_override set)
        status = await engine.evaluate("rsi")
        assert status == StrategyHealthStatus.RETIRED


# ---------------------------------------------------------------------------
# Disabled engine
# ---------------------------------------------------------------------------


class TestDisabledEngine:
    async def test_disabled_engine_always_returns_normal(self, db):
        snap = _snapshot(win_rate=0.1, avg_win=10.0, avg_loss=500.0, total_trades=100)
        cfg = _cfg(enabled=False)
        engine, _ = await _make_engine(db, cfg=cfg, snapshot=snap)
        status = await engine.evaluate("rsi")
        assert status == StrategyHealthStatus.NORMAL

    async def test_get_status_with_disabled_engine(self, db):
        cfg = _cfg(enabled=False)
        engine, _ = await _make_engine(db, cfg=cfg)
        status = await engine.get_status("rsi")
        assert status == StrategyHealthStatus.NORMAL


# ---------------------------------------------------------------------------
# get_throttle_multiplier
# ---------------------------------------------------------------------------


class TestThrottleMultiplier:
    async def test_returns_config_default_when_not_set(self, db):
        cfg = _cfg(throttle_multiplier=0.25)
        engine, _ = await _make_engine(db, cfg=cfg)
        multiplier = await engine.get_throttle_multiplier("rsi")
        assert multiplier == pytest.approx(0.25)

    async def test_returns_stored_value_when_set(self, db):
        engine, health_store = await _make_engine(db)
        await health_store.upsert_status("rsi", "throttled", throttle_multiplier=0.33)
        multiplier = await engine.get_throttle_multiplier("rsi")
        assert multiplier == pytest.approx(0.33)


# ---------------------------------------------------------------------------
# on_trade_closed (non-blocking wrapper)
# ---------------------------------------------------------------------------


class TestOnTradeClosed:
    async def test_on_trade_closed_triggers_evaluate(self, db):
        snap = _snapshot()  # healthy snapshot
        engine, _ = await _make_engine(db, snapshot=snap)
        # Should complete without raising
        await engine.on_trade_closed("rsi")


# ---------------------------------------------------------------------------
# Audit events recorded on transition
# ---------------------------------------------------------------------------


class TestAuditEvents:
    async def test_transition_records_event(self, db):
        snap = _snapshot(win_rate=0.35, avg_win=40.0, avg_loss=200.0, total_trades=30)
        engine, health_store = await _make_engine(db, snapshot=snap)
        await engine.evaluate("rsi")

        events = await health_store.get_events("rsi", limit=5)
        assert len(events) == 1
        assert events[0]["old_status"] == "normal"
        assert events[0]["new_status"] == "watchlist"
        assert events[0]["actor"] == "system"

    async def test_no_event_when_no_transition(self, db):
        snap = _snapshot()  # healthy snapshot, stays normal
        engine, health_store = await _make_engine(db, snapshot=snap)
        await engine.evaluate("rsi")

        events = await health_store.get_events("rsi", limit=5)
        assert len(events) == 0
