from __future__ import annotations
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tournament.store import TournamentStore
    from storage.performance import PerformanceStore, PerformanceSnapshot
    from notifications.base import Notifier
    from agents.runner import AgentRunner
    from learning.config import TournamentConfig

logger = logging.getLogger(__name__)


class TournamentEngine:
    def __init__(
        self,
        *,
        store: TournamentStore,
        perf_store: PerformanceStore,
        notifier: Notifier,
        runner: AgentRunner,
        config: TournamentConfig,
        llm: Any = None,  # LLMClient | None
    ) -> None:
        self._store = store
        self._perf_store = perf_store
        self._notifier = notifier
        self._runner = runner
        self._config = config

        if llm is not None:
            self._llm = llm
        else:
            from llm.client import LLMClient as _LLMClient

            self._llm = _LLMClient()

    def _check_thresholds(
        self, snap: PerformanceSnapshot, *, target_stage: int
    ) -> tuple[bool, str]:
        """Return (passed, reason). reason is empty string on pass."""
        thresholds = self._config.stages.get(target_stage)
        if thresholds is None:
            return False, f"no threshold config for stage {target_stage}"

        if snap.sharpe_ratio < thresholds.min_sharpe:
            return False, (
                f"sharpe {snap.sharpe_ratio:.2f} < required {thresholds.min_sharpe}"
            )
        if snap.total_trades < thresholds.min_trades:
            return False, (
                f"trades {snap.total_trades} < required {thresholds.min_trades}"
            )
        if snap.max_drawdown > thresholds.max_drawdown:
            return False, (
                f"drawdown {snap.max_drawdown:.2%} > limit {thresholds.max_drawdown:.2%}"
            )
        if snap.win_rate < thresholds.min_win_rate:
            return False, (
                f"win_rate {snap.win_rate:.2%} < required {thresholds.min_win_rate:.2%}"
            )
        return True, ""

    async def evaluate_all(self) -> None:
        """Check every registered agent against promotion thresholds. Called on cron."""
        agents = self._runner.list_agents()
        for agent_info in agents:
            await self._evaluate_one(agent_info.name)

    async def _evaluate_one(self, agent_name: str) -> None:
        current_stage = await self._store.get_stage(agent_name)
        target_stage = current_stage + 1
        if target_stage > 3:
            return  # already at max stage

        snap = await self._perf_store.get_latest(agent_name)
        if snap is None:
            logger.debug("No performance snapshot for %s, skipping", agent_name)
            return

        passed, reason = self._check_thresholds(snap, target_stage=target_stage)
        if passed:
            await self.promote(agent_name, to_stage=target_stage, snap=snap)

    async def promote(
        self,
        agent_name: str,
        to_stage: int,
        snap: PerformanceSnapshot | None = None,
        overridden_by: str | None = None,
    ) -> None:
        """Promote agent. Runs AI gate unless this is a manual override."""
        from_stage = await self._store.get_stage(agent_name)

        if snap is None:
            snap = await self._perf_store.get_latest(agent_name)

        threshold_summary = ""
        if snap is not None:
            threshold_summary = (
                f"sharpe={snap.sharpe_ratio:.2f} trades={snap.total_trades} "
                f"drawdown={snap.max_drawdown:.2%} win_rate={snap.win_rate:.2%}"
            )

        ai_analysis = ""
        ai_recommendation = "go"
        if overridden_by is None and snap is not None:
            ai_analysis, ai_recommendation = await self._run_ai_gate(
                agent_name, snap, to_stage
            )
            if ai_recommendation == "no-go":
                logger.info(
                    "AI gate blocked promotion of %s to stage %d: %s",
                    agent_name,
                    to_stage,
                    ai_analysis,
                )
                return

        await self._store.set_stage(agent_name, to_stage)
        await self._store.write_audit(
            agent_name=agent_name,
            from_stage=from_stage,
            to_stage=to_stage,
            reason=threshold_summary or "manual override",
            ai_analysis=ai_analysis,
            ai_recommendation=ai_recommendation,
            overridden_by=overridden_by,
        )
        stage_names = {0: "Backtest", 1: "Paper", 2: "Live Limited", 3: "Live Full"}
        msg = (
            f"PROMOTED: {agent_name}\n"
            f"{stage_names.get(from_stage, str(from_stage))} → {stage_names.get(to_stage, str(to_stage))}\n"
            f"Metrics: {threshold_summary}\n"
            f"AI: {ai_analysis[:200] if ai_analysis else 'N/A'}\n"
            f"To reverse: OVERRIDE DEMOTE {agent_name}"
        )
        await self._send_text_notification(msg)

    async def demote(
        self,
        agent_name: str,
        reason: str,
        snap_summary: str = "",
        overridden_by: str | None = None,
    ) -> None:
        """Hard demote to stage 0, immediately."""
        from_stage = await self._store.get_stage(agent_name)
        to_stage = 0

        ai_summary = await self._run_ai_demotion_summary(agent_name, reason)

        await self._store.set_stage(agent_name, to_stage)
        await self._store.write_audit(
            agent_name=agent_name,
            from_stage=from_stage,
            to_stage=to_stage,
            reason=reason,
            ai_analysis=ai_summary,
            ai_recommendation="demote",
            overridden_by=overridden_by,
        )
        msg = (
            f"DEMOTED: {agent_name}\n"
            f"Reason: {reason}\n"
            f"{snap_summary}\n"
            f"AI: {ai_summary}\n"
            f"To reverse: OVERRIDE PROMOTE {agent_name}"
        )
        await self._send_text_notification(msg)

    async def override(self, agent_name: str, action: str, by: str) -> str:
        """Handle WhatsApp override command. action is 'promote' or 'demote'."""
        action = action.lower().strip()
        if action == "promote":
            current = await self._store.get_stage(agent_name)
            to_stage = min(current + 1, 3)
            await self.promote(agent_name, to_stage=to_stage, overridden_by=by)
            return f"Override applied: {agent_name} promoted to stage {to_stage}."
        elif action == "demote":
            await self.demote(
                agent_name, reason=f"manual override by {by}", overridden_by=by
            )
            return f"Override applied: {agent_name} demoted to stage 0."
        else:
            return f"Unknown override action '{action}'. Use 'promote' or 'demote'."

    async def _run_ai_gate(
        self,
        agent_name: str,
        snap: PerformanceSnapshot,
        to_stage: int,
    ) -> tuple[str, str]:
        """Call LLM chain. Returns (analysis_text, 'go'|'no-go')."""
        try:
            prompt = (
                f"You are reviewing a trading strategy called '{agent_name}' for promotion "
                f"to stage {to_stage} (0=Backtest, 1=Paper, 2=LiveLimited, 3=LiveFull).\n\n"
                f"Performance metrics:\n"
                f"- Sharpe Ratio: {snap.sharpe_ratio:.2f}\n"
                f"- Total Trades: {snap.total_trades}\n"
                f"- Max Drawdown: {snap.max_drawdown:.2%}\n"
                f"- Win Rate: {snap.win_rate:.2%}\n"
                f"- Total PnL: {snap.total_pnl}\n\n"
                f"Evaluate:\n"
                f"1. Is performance concentrated in one regime (regime dependency)?\n"
                f"2. Is there risk of overfitting given the trade count?\n"
                f"3. Any market condition concerns?\n\n"
                f"End your response with exactly one line: RECOMMENDATION: go  OR  RECOMMENDATION: no-go"
            )
            result = await self._llm.complete(prompt, max_tokens=400)
            text = result.text or ""
            recommendation = "no-go"
            for line in reversed(text.splitlines()):
                if "RECOMMENDATION:" in line:
                    recommendation = (
                        "go" if "go" in line.lower().replace("no-go", "") else "no-go"
                    )
                    if "no-go" in line.lower():
                        recommendation = "no-go"
                    break
            return text, recommendation
        except Exception as exc:
            logger.warning(
                "AI gate failed for %s: %s — defaulting to go", agent_name, exc
            )
            return f"AI gate error: {exc}", "go"

    async def _run_ai_demotion_summary(self, agent_name: str, reason: str) -> str:
        """One-sentence summary for demotion notification via LLM."""
        try:
            prompt = (
                f"In one sentence, summarize why '{agent_name}' was demoted. "
                f"Reason: {reason}"
            )
            result = await self._llm.complete(prompt, max_tokens=80)
            return (result.text or "").strip()
        except Exception as exc:
            logger.warning("AI demotion summary failed: %s", exc)
            return ""

    async def _send_text_notification(self, message: str) -> None:
        """Send a plain-text notification via CompositeNotifier.

        CompositeNotifier.send() accepts an Opportunity. We create a minimal
        stand-in object that notifiers treating the message as a plain string can use.
        We rely on LogNotifier always working; WhatsApp/Slack notifiers that
        inspect specific Opportunity fields will receive the text in `reasoning`.
        """
        from agents.models import Opportunity, OpportunityStatus
        from broker.models import Symbol, AssetType
        from datetime import datetime, timezone
        import uuid

        pseudo_opp = Opportunity(
            id=str(uuid.uuid4()),
            agent_name="tournament",
            symbol=Symbol(ticker="TOURNAMENT", asset_type=AssetType.STOCK),
            signal="stage_transition",
            confidence=1.0,
            reasoning=message,
            data={"tournament_notification": True},
            timestamp=datetime.now(timezone.utc),
            status=OpportunityStatus.PENDING,
        )
        await self._notifier.send(pseudo_opp)

    async def update_elo_ratings(self, rankings: list[dict]) -> None:
        """Update ELO ratings based on tournament rankings.

        Args:
            rankings: List of dicts with agent_name, sharpe_ratio, rank.
                      Must be sorted by rank (1 = best).
        """
        K_FACTOR = 32
        ELO_FLOOR = 100
        MAX_DELTA = 50

        for i, entry in enumerate(rankings):
            agent_name = entry["agent_name"]
            agent_rank = entry.get("rank", i + 1)
            agent_sharpe = entry.get("sharpe_ratio", 0.0)

            old_elo = await self._store.get_elo(agent_name)

            total_agents = len(rankings)
            beat_median_rank = (total_agents / 2) - agent_rank

            positive_sharpe_bonus = (
                int((agent_sharpe - 1.5) * 10) if agent_sharpe > 1.5 else 0
            )
            negative_sharpe_penalty = int(agent_sharpe * 15) if agent_sharpe < 0 else 0

            base_elo_change = int(beat_median_rank * (K_FACTOR / total_agents))
            new_elo = (
                old_elo
                + base_elo_change
                + positive_sharpe_bonus
                + negative_sharpe_penalty
            )
            new_elo = max(
                ELO_FLOOR, min(old_elo + MAX_DELTA, max(old_elo - MAX_DELTA, new_elo))
            )

            await self._store.set_elo(agent_name, new_elo)
            await self._store.record_elo_change(
                agent_name=agent_name,
                old_rating=old_elo,
                new_rating=new_elo,
                reason=f"rank_{agent_rank}_sharpe_{agent_sharpe:.2f}",
            )

            logger.info(
                "ELO update: %s %d → %d (Δ%d, rank=%d, sharpe=%.2f)",
                agent_name,
                old_elo,
                new_elo,
                new_elo - old_elo,
                agent_rank,
                agent_sharpe,
            )

    async def get_elo_ratings(self) -> dict[str, int]:
        """Get all ELO ratings for consensus.py AgentWeightProvider."""
        return await self._store.get_all_elo()

    async def compute_rankings(self) -> list[dict]:
        """Compute tournament rankings from performance snapshots.

        Returns list of dicts sorted by Sharpe ratio (descending).
        Each dict: {agent_name, sharpe_ratio, rank, stage, ...}
        """
        agents = self._runner.list_agents()
        rankings = []

        for agent_info in agents:
            snap = await self._perf_store.get_latest(agent_info.name)
            if snap is None:
                continue

            stage = await self._store.get_stage(agent_info.name)
            rankings.append(
                {
                    "agent_name": agent_info.name,
                    "sharpe_ratio": snap.sharpe_ratio,
                    "max_drawdown": snap.max_drawdown,
                    "win_rate": snap.win_rate,
                    "total_trades": snap.total_trades,
                    "total_pnl": float(snap.total_pnl),
                    "stage": stage,
                }
            )

        rankings.sort(key=lambda x: x["sharpe_ratio"], reverse=True)

        for i, r in enumerate(rankings):
            r["rank"] = i + 1

        return rankings

    async def run_tournament(self) -> dict:
        """Run complete tournament cycle: evaluate, rank, update ELO.

        Returns tournament results summary.
        """
        await self.evaluate_all()
        rankings = await self.compute_rankings()
        await self.update_elo_ratings(rankings)
        elo_ratings = await self.get_elo_ratings()

        return {
            "rankings": rankings,
            "elo_ratings": elo_ratings,
            "timestamp": __import__("datetime")
            .datetime.now(__import__("datetime").timezone.utc)
            .isoformat(),
        }

    async def run_arena_gym_cycle(self, tuner: Any = None) -> dict:
        """Run complete Arena-Gym cycle: tournament + auto-tune underperformers.

        1. Run tournament (evaluate, rank, update ELO)
        2. Identify agents with Sharpe < 1.0 (underperformers)
        3. Run AdaptiveTuner.generate_parameter_variants() for each
        4. Return tuning recommendations

        Args:
            tuner: AdaptiveTuner instance (optional, will create if not provided)

        Returns:
            Dict with tournament results + tuning recommendations
        """
        tournament_results = await self.run_tournament()
        rankings = tournament_results["rankings"]

        if tuner is None:
            from agents.runner import AgentRunner
            from agents.tuning import AdaptiveTuner
            from storage.opportunities import OpportunityStore
            from storage.trades import TradeStore

            db = getattr(self._runner, "_db", None)
            if db is None:
                return {**tournament_results, "tuning": "skipped - no db"}

            opp_store = OpportunityStore(db)
            trade_store = TradeStore(db)
            tuner = AdaptiveTuner(self._runner, opp_store, trade_store)

        tuning_recommendations = []
        for entry in rankings:
            if entry["sharpe_ratio"] >= 1.0:
                continue

            agent_name = entry["agent_name"]
            snapshot = {
                "sharpe_ratio": entry["sharpe_ratio"],
                "win_rate": entry["win_rate"],
                "total_trades": entry["total_trades"],
                "max_drawdown": entry["max_drawdown"],
            }

            try:
                recommendations = await tuner.generate_recommendations(
                    agent_name, snapshot
                )
                tuning_recommendations.append(
                    {
                        "agent_name": agent_name,
                        "current_sharpe": entry["sharpe_ratio"],
                        "rank": entry["rank"],
                        "recommendations": recommendations,
                    }
                )
            except Exception as e:
                logger.warning("Tuning recommendation failed for %s: %s", agent_name, e)

        return {
            **tournament_results,
            "tuning": {
                "underperformers": len(tuning_recommendations),
                "recommendations": tuning_recommendations,
            },
        }
