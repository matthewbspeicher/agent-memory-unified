from unittest.mock import AsyncMock, MagicMock
from tournament.engine import TournamentEngine
from tournament.store import TournamentStore
from learning.config import TournamentConfig, TournamentStageConfig, LiveLimitedConfig
from storage.performance import PerformanceSnapshot
from decimal import Decimal
from datetime import datetime, timezone


def _make_config(stages: dict | None = None) -> TournamentConfig:
    default_stages = {
        1: TournamentStageConfig(
            min_sharpe=1.5, min_trades=50, max_drawdown=0.15, min_win_rate=0.45
        ),
        2: TournamentStageConfig(
            min_sharpe=1.8, min_trades=100, max_drawdown=0.12, min_win_rate=0.48
        ),
        3: TournamentStageConfig(
            min_sharpe=2.0, min_trades=200, max_drawdown=0.10, min_win_rate=0.50
        ),
    }
    return TournamentConfig(
        enabled=True,
        evaluate_cron="0 * * * *",
        stages=stages or default_stages,
        live_limited=LiveLimitedConfig(max_capital_pct=0.10, max_capital_usd=500),
    )


def _make_snapshot(
    agent_name: str = "agent1",
    sharpe: float = 2.0,
    trades: int = 100,
    drawdown: float = 0.10,
    win_rate: float = 0.50,
) -> PerformanceSnapshot:
    return PerformanceSnapshot(
        agent_name=agent_name,
        timestamp=datetime.now(timezone.utc),
        opportunities_generated=200,
        opportunities_executed=100,
        win_rate=win_rate,
        total_pnl=Decimal("500"),
        sharpe_ratio=sharpe,
        max_drawdown=drawdown,
        total_trades=trades,
    )


def _make_engine(config: TournamentConfig | None = None) -> TournamentEngine:
    store = MagicMock(spec=TournamentStore)
    store.get_stage = AsyncMock(return_value=0)
    store.set_stage = AsyncMock()
    store.write_audit = AsyncMock()
    store.get_all_stages = AsyncMock(return_value={})
    perf_store = MagicMock()
    perf_store.get_latest = AsyncMock(return_value=None)
    notifier = MagicMock()
    notifier.send = AsyncMock()
    runner = MagicMock()
    runner.list_agents = MagicMock(return_value=[])
    return TournamentEngine(
        store=store,
        perf_store=perf_store,
        notifier=notifier,
        runner=runner,
        config=config or _make_config(),
        llm=MagicMock(),
    )


class TestThresholdCheck:
    async def test_passes_when_all_metrics_meet_stage1(self):
        engine = _make_engine()
        snap = _make_snapshot(sharpe=1.6, trades=60, drawdown=0.10, win_rate=0.50)
        passed, reason = engine._check_thresholds(snap, target_stage=1)
        assert passed is True
        assert reason == ""

    async def test_fails_when_sharpe_too_low(self):
        engine = _make_engine()
        snap = _make_snapshot(sharpe=1.0, trades=60, drawdown=0.10, win_rate=0.50)
        passed, reason = engine._check_thresholds(snap, target_stage=1)
        assert passed is False
        assert "sharpe" in reason.lower()

    async def test_fails_when_trades_too_few(self):
        engine = _make_engine()
        snap = _make_snapshot(sharpe=2.0, trades=10, drawdown=0.10, win_rate=0.50)
        passed, reason = engine._check_thresholds(snap, target_stage=1)
        assert passed is False
        assert "trades" in reason.lower()

    async def test_fails_when_drawdown_too_high(self):
        engine = _make_engine()
        snap = _make_snapshot(sharpe=2.0, trades=60, drawdown=0.20, win_rate=0.50)
        passed, reason = engine._check_thresholds(snap, target_stage=1)
        assert passed is False
        assert "drawdown" in reason.lower()

    async def test_fails_when_win_rate_too_low(self):
        engine = _make_engine()
        snap = _make_snapshot(sharpe=2.0, trades=60, drawdown=0.10, win_rate=0.30)
        passed, reason = engine._check_thresholds(snap, target_stage=1)
        assert passed is False
        assert "win_rate" in reason.lower()

    async def test_no_threshold_config_for_stage_blocks_promotion(self):
        engine = _make_engine()
        snap = _make_snapshot(sharpe=2.0, trades=60, drawdown=0.10, win_rate=0.50)
        passed, reason = engine._check_thresholds(snap, target_stage=99)
        assert passed is False
        assert "no threshold" in reason.lower()


class TestPromoteDemote:
    async def test_promote_sets_stage_and_writes_audit(self):
        engine = _make_engine()
        engine._store.get_stage = AsyncMock(return_value=0)
        snap = _make_snapshot(agent_name="a1")
        engine._perf_store.get_latest = AsyncMock(return_value=snap)

        await engine.promote("a1", to_stage=1, snap=snap, overridden_by="test")

        engine._store.set_stage.assert_awaited_once_with("a1", 1)
        engine._store.write_audit.assert_awaited_once()
        call_kwargs = engine._store.write_audit.call_args.kwargs
        assert call_kwargs["from_stage"] == 0
        assert call_kwargs["to_stage"] == 1
        assert call_kwargs["overridden_by"] == "test"

    async def test_demote_always_goes_to_stage_zero(self):
        engine = _make_engine()
        engine._store.get_stage = AsyncMock(return_value=3)

        await engine.demote("a1", reason="drawdown breach")

        engine._store.set_stage.assert_awaited_once_with("a1", 0)
        call_kwargs = engine._store.write_audit.call_args.kwargs
        assert call_kwargs["from_stage"] == 3
        assert call_kwargs["to_stage"] == 0
        assert call_kwargs["ai_recommendation"] == "demote"

    async def test_override_promote_calls_promote(self):
        engine = _make_engine()
        engine._store.get_stage = AsyncMock(return_value=1)
        snap = _make_snapshot()
        engine._perf_store.get_latest = AsyncMock(return_value=snap)

        result = await engine.override("a1", "promote", by="+15551234")

        assert "promoted" in result.lower()
        engine._store.set_stage.assert_awaited_once_with("a1", 2)

    async def test_override_demote_calls_demote(self):
        engine = _make_engine()
        engine._store.get_stage = AsyncMock(return_value=2)

        result = await engine.override("a1", "demote", by="+15551234")

        assert "demoted" in result.lower()
        engine._store.set_stage.assert_awaited_once_with("a1", 0)

    async def test_override_promote_caps_at_stage_3(self):
        engine = _make_engine()
        engine._store.get_stage = AsyncMock(return_value=3)
        snap = _make_snapshot()
        engine._perf_store.get_latest = AsyncMock(return_value=snap)

        await engine.override("a1", "promote", by="+15551234")
        engine._store.set_stage.assert_awaited_once_with("a1", 3)

    async def test_evaluate_all_promotes_eligible_agent(self):
        engine = _make_engine()
        agent_info = MagicMock()
        agent_info.name = "a1"
        engine._runner.list_agents = MagicMock(return_value=[agent_info])
        engine._store.get_stage = AsyncMock(return_value=0)
        snap = _make_snapshot(sharpe=2.0, trades=60, drawdown=0.10, win_rate=0.50)
        engine._perf_store.get_latest = AsyncMock(return_value=snap)

        await engine.evaluate_all()

        engine._store.set_stage.assert_awaited_once_with("a1", 1)

    async def test_evaluate_all_skips_ineligible_agent(self):
        engine = _make_engine()
        agent_info = MagicMock()
        agent_info.name = "a1"
        engine._runner.list_agents = MagicMock(return_value=[agent_info])
        engine._store.get_stage = AsyncMock(return_value=0)
        snap = _make_snapshot(sharpe=0.5, trades=10, drawdown=0.50, win_rate=0.20)
        engine._perf_store.get_latest = AsyncMock(return_value=snap)

        await engine.evaluate_all()

        engine._store.set_stage.assert_not_awaited()


class TestWhatsAppOverrideRouting:
    async def test_override_promote_command_parsed(self):
        """Verify the WhatsApp assistant routes OVERRIDE PROMOTE to TournamentEngine."""
        from unittest.mock import AsyncMock, MagicMock
        from whatsapp.assistant import WhatsAppAssistant

        wa_client = MagicMock()
        wa_client.mark_read = AsyncMock()
        wa_client.send_text = AsyncMock()
        wa_client.record_inbound = MagicMock()
        wa_client.persist_session = AsyncMock()

        tournament_engine = MagicMock()
        tournament_engine.override = AsyncMock(
            return_value="Override applied: agent1 promoted."
        )

        assistant = WhatsAppAssistant(
            client=wa_client,
            broker=MagicMock(),
            runner=MagicMock(),
            opp_store=MagicMock(),
            risk_engine=MagicMock(),
            tournament_engine=tournament_engine,
            db=None,
        )
        assistant._runner.list_agents = MagicMock(return_value=[])
        assistant._opp_store.list = AsyncMock(return_value=[])

        await assistant.handle("+15551234", "OVERRIDE PROMOTE agent1", "msg1")

        tournament_engine.override.assert_awaited_once_with(
            "agent1", "promote", by="+15551234"
        )
        wa_client.send_text.assert_awaited()
