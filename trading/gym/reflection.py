"""LLM self-reflection pipeline for agent learning and trade analysis.

SelfReflectionAgent queries trade history, sends to LLM for pattern analysis,
and stores actionable insights. TradeAnalyzer categorizes trades by quality
and aggregates statistics per agent.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class InsightCategory(str, Enum):
    """Categories for self-reflection insights."""

    ENTRY_TIMING = "entry_timing"
    EXIT_TIMING = "exit_timing"
    POSITION_SIZING = "position_sizing"
    REGIME_FIT = "regime_fit"
    RISK_MANAGEMENT = "risk_management"
    PATTERN_RECOGNITION = "pattern_recognition"


class TradeCategory(str, Enum):
    """Categories for trade outcome analysis."""

    GOOD_ENTRY = "good_entry"
    BAD_ENTRY = "bad_entry"
    GOOD_EXIT = "good_exit"
    BAD_EXIT = "bad_exit"
    SIZE_ISSUE = "size_issue"
    REGIME_MISMATCH = "regime_mismatch"
    LUCKY_WIN = "lucky_win"
    UNLUCKY_LOSS = "unlucky_loss"


@dataclass
class Insight:
    """A single insight from self-reflection analysis."""

    agent_name: str
    category: InsightCategory
    content: str
    confidence: float
    related_trades: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TradeAnalysis:
    """Analysis of a single trade."""

    trade_id: str
    agent_name: str
    symbol: str
    entry_time: datetime
    exit_time: datetime
    pnl: float
    pnl_pct: float
    category: TradeCategory
    reasoning: str
    regime: str | None = None


@dataclass
class AgentTradeStats:
    """Aggregated trade statistics for an agent."""

    agent_name: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win_pct: float
    avg_loss_pct: float
    best_category: TradeCategory
    worst_category: TradeCategory
    category_distribution: dict[TradeCategory, int]
    insights: list[Insight]


class LLMClient(Protocol):
    """Protocol for LLM client interface."""

    async def complete(self, prompt: str, max_tokens: int = 500) -> Any: ...


class TradeReflector:
    """Queries trade history for reflection analysis."""

    def __init__(self, trade_store: Any, opp_store: Any):
        self._trade_store = trade_store
        self._opp_store = opp_store

    async def get_recent_trades(
        self,
        agent_name: str,
        days: int = 7,
        limit: int = 100,
    ) -> list[dict]:
        """Get recent trades for an agent."""
        cutoff = datetime.utcnow() - timedelta(days=days)
        trades = await self._trade_store.list(
            agent_name=agent_name,
            limit=limit,
        )
        return [t for t in trades if self._parse_time(t.get("created_at")) > cutoff]

    async def get_trade_context(
        self,
        trade: dict,
    ) -> dict:
        """Get market context for a trade (regime, volatility, etc.)."""
        opp = await self._opp_store.get(trade.get("opportunity_id"))
        return {
            "regime": opp.get("regime") if opp else None,
            "volatility": opp.get("volatility") if opp else None,
            "confidence": trade.get("confidence", 0),
        }

    @staticmethod
    def _parse_time(ts: str | datetime | None) -> datetime:
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.min


class SelfReflectionAgent:
    """LLM-powered self-reflection for agent learning.

    Queries trade history, analyzes patterns via LLM, and stores insights
    for continuous improvement.
    """

    def __init__(
        self,
        llm: LLMClient,
        trade_reflector: TradeReflector,
        insight_store: Any | None = None,
    ):
        self._llm = llm
        self._reflector = trade_reflector
        self._insight_store = insight_store
        self._insights: dict[str, list[Insight]] = {}

    async def reflect(
        self,
        agent_name: str,
        days: int = 7,
    ) -> list[Insight]:
        """Run self-reflection on agent's recent trades.

        Args:
            agent_name: Agent to reflect on.
            days: Number of days of history to analyze.

        Returns:
            List of insights generated from the analysis.
        """
        trades = await self._reflector.get_recent_trades(agent_name, days=days)
        if len(trades) < 5:
            logger.debug(
                "Insufficient trades for reflection: %s has %d trades",
                agent_name,
                len(trades),
            )
            return []

        # Build trade summary for LLM
        trade_summary = self._build_trade_summary(trades)

        prompt = (
            f"Analyze the following trading history for agent '{agent_name}':\n\n"
            f"{trade_summary}\n\n"
            "Provide 2-3 actionable insights. For each insight:\n"
            "1. Category (entry_timing, exit_timing, position_sizing, regime_fit, risk_management, pattern_recognition)\n"
            "2. Specific observation with concrete examples\n"
            "3. Recommended action\n"
            "4. Confidence level (0.0-1.0)\n\n"
            'Return as JSON array: [{"category": "...", "content": "...", "confidence": 0.8, "tags": [...]}]'
        )

        insights = []
        try:
            result = await self._llm.complete(prompt, max_tokens=800)
            text = result.text.strip()

            # Parse JSON response
            if text.startswith("```"):
                lines = text.split("\n")
                lines = [l for l in lines if not l.startswith("```")]
                text = "\n".join(lines)

            parsed = json.loads(text)
            if isinstance(parsed, list):
                for item in parsed:
                    try:
                        insight = Insight(
                            agent_name=agent_name,
                            category=InsightCategory(
                                item.get("category", "pattern_recognition")
                            ),
                            content=item.get("content", ""),
                            confidence=float(item.get("confidence", 0.5)),
                            tags=item.get("tags", []),
                            related_trades=[t.get("id", "") for t in trades[:5]],
                        )
                        insights.append(insight)
                    except (ValueError, KeyError) as e:
                        logger.warning("Failed to parse insight: %s", e)

        except Exception as e:
            logger.warning("LLM reflection failed for %s: %s", agent_name, e)

        # Store insights
        if agent_name not in self._insights:
            self._insights[agent_name] = []
        self._insights[agent_name].extend(insights)

        if self._insight_store:
            for insight in insights:
                await self._store_insight(insight)

        return insights

    def get_insights(
        self,
        agent_name: str,
        category: InsightCategory | None = None,
        limit: int = 10,
    ) -> list[Insight]:
        """Retrieve stored insights for an agent."""
        agent_insights = self._insights.get(agent_name, [])
        if category:
            agent_insights = [i for i in agent_insights if i.category == category]
        return sorted(agent_insights, key=lambda x: x.timestamp, reverse=True)[:limit]

    def _build_trade_summary(self, trades: list[dict]) -> str:
        """Build a concise summary of trades for LLM analysis."""
        lines = []
        for i, trade in enumerate(trades[:20]):  # Limit to 20 trades
            pnl = trade.get("pnl", 0)
            pnl_pct = trade.get("pnl_pct", 0)
            symbol = trade.get("symbol", "unknown")
            direction = "LONG" if trade.get("side") == "buy" else "SHORT"
            lines.append(
                f"{i + 1}. {symbol} {direction}: PnL={pnl:.2f} ({pnl_pct:.2%}), "
                f"confidence={trade.get('confidence', 0):.2f}"
            )
        return "\n".join(lines)

    async def _store_insight(self, insight: Insight) -> None:
        """Store insight to persistent store."""
        try:
            await self._insight_store.save(
                agent_name=insight.agent_name,
                category=insight.category.value,
                content=insight.content,
                confidence=insight.confidence,
                tags=insight.tags,
                related_trades=insight.related_trades,
            )
        except Exception as e:
            logger.warning("Failed to store insight: %s", e)


class TradeAnalyzer:
    """Categorizes trades and aggregates statistics per agent."""

    def __init__(self, trade_store: Any, opp_store: Any):
        self._trade_store = trade_store
        self._opp_store = opp_store

    async def analyze_trade(
        self,
        trade: dict,
        market_data: dict | None = None,
    ) -> TradeAnalysis:
        """Analyze a single trade and categorize it.

        Categories:
        - good_entry/bad_entry: Entry timing quality
        - good_exit/bad_exit: Exit timing quality
        - size_issue: Position sizing problems
        - regime_mismatch: Strategy not suited for market regime
        - lucky_win/unlucky_loss: Outcome driven by luck vs skill
        """
        pnl = trade.get("pnl", 0)
        pnl_pct = trade.get("pnl_pct", 0)
        confidence = trade.get("confidence", 0.5)
        hold_duration = self._calc_hold_duration(trade)

        category = self._categorize_trade(
            pnl=pnl,
            pnl_pct=pnl_pct,
            confidence=confidence,
            hold_duration=hold_duration,
            market_data=market_data,
        )

        reasoning = self._build_reasoning(
            category, pnl, confidence, hold_duration, market_data
        )

        return TradeAnalysis(
            trade_id=trade.get("id", ""),
            agent_name=trade.get("agent_name", "unknown"),
            symbol=trade.get("symbol", ""),
            entry_time=self._parse_time(trade.get("entry_time")),
            exit_time=self._parse_time(trade.get("exit_time")),
            pnl=pnl,
            pnl_pct=pnl_pct,
            category=category,
            reasoning=reasoning,
            regime=market_data.get("regime") if market_data else None,
        )

    async def analyze_agent_trades(
        self,
        agent_name: str,
        days: int = 30,
        limit: int = 200,
    ) -> AgentTradeStats:
        """Analyze all trades for an agent and return aggregated stats."""
        trades = await self._trade_store.list(agent_name=agent_name, limit=limit)
        if not trades:
            return AgentTradeStats(
                agent_name=agent_name,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                avg_win_pct=0,
                avg_loss_pct=0,
                best_category=TradeCategory.GOOD_ENTRY,
                worst_category=TradeCategory.BAD_ENTRY,
                category_distribution={},
                insights=[],
            )

        analyses = []
        for trade in trades:
            analysis = await self.analyze_trade(trade)
            analyses.append(analysis)

        # Aggregate stats
        wins = [a for a in analyses if a.pnl > 0]
        losses = [a for a in analyses if a.pnl <= 0]

        category_counts: dict[TradeCategory, int] = {}
        for a in analyses:
            category_counts[a.category] = category_counts.get(a.category, 0) + 1

        best_cat = (
            max(category_counts, key=category_counts.get)
            if category_counts
            else TradeCategory.GOOD_ENTRY
        )
        worst_cat = (
            min(category_counts, key=category_counts.get)
            if category_counts
            else TradeCategory.BAD_ENTRY
        )

        return AgentTradeStats(
            agent_name=agent_name,
            total_trades=len(analyses),
            winning_trades=len(wins),
            losing_trades=len(losses),
            avg_win_pct=sum(a.pnl_pct for a in wins) / len(wins) if wins else 0,
            avg_loss_pct=sum(a.pnl_pct for a in losses) / len(losses) if losses else 0,
            best_category=best_cat,
            worst_category=worst_cat,
            category_distribution=category_counts,
            insights=[],
        )

    def _categorize_trade(
        self,
        pnl: float,
        pnl_pct: float,
        confidence: float,
        hold_duration: timedelta,
        market_data: dict | None,
    ) -> TradeCategory:
        """Categorize a trade based on multiple factors."""
        is_win = pnl > 0
        is_high_confidence = confidence > 0.7
        is_quick_trade = hold_duration < timedelta(minutes=5)

        if is_win and is_high_confidence:
            return TradeCategory.GOOD_ENTRY
        elif is_win and not is_high_confidence:
            return TradeCategory.LUCKY_WIN
        elif not is_win and is_high_confidence:
            # High confidence loss - possible exit timing issue
            if is_quick_trade:
                return TradeCategory.BAD_EXIT
            return TradeCategory.REGIME_MISMATCH
        elif not is_win and abs(pnl_pct) < 0.01:
            # Small loss - likely size issue or noise
            return TradeCategory.SIZE_ISSUE
        else:
            return TradeCategory.BAD_ENTRY

    def _build_reasoning(
        self,
        category: TradeCategory,
        pnl: float,
        confidence: float,
        hold_duration: timedelta,
        market_data: dict | None,
    ) -> str:
        """Build human-readable reasoning for the categorization."""
        regime = market_data.get("regime", "unknown") if market_data else "unknown"

        reasons = {
            TradeCategory.GOOD_ENTRY: f"High confidence ({confidence:.0%}) entry led to profitable trade. Regime: {regime}.",
            TradeCategory.BAD_ENTRY: f"Low confidence ({confidence:.0%}) entry resulted in loss. Consider tightening entry criteria.",
            TradeCategory.GOOD_EXIT: f"Exit timing captured profits. Hold duration: {hold_duration}.",
            TradeCategory.BAD_EXIT: f"Quick exit ({hold_duration}) on high-confidence trade suggests premature closure.",
            TradeCategory.SIZE_ISSUE: f"Small PnL ({pnl:.2f}) suggests position sizing may be suboptimal.",
            TradeCategory.REGIME_MISMATCH: f"High-confidence loss in {regime} regime suggests strategy不适合 current conditions.",
            TradeCategory.LUCKY_WIN: f"Profitable trade with low confidence ({confidence:.0%}) - may be noise.",
            TradeCategory.UNLUCKY_LOSS: "Loss despite good setup - market moved against position.",
        }
        return reasons.get(category, "Unable to determine cause.")

    @staticmethod
    def _calc_hold_duration(trade: dict) -> timedelta:
        entry = TradeAnalyzer._parse_time(trade.get("entry_time"))
        exit_ = TradeAnalyzer._parse_time(trade.get("exit_time"))
        if exit_ > entry:
            return exit_ - entry
        return timedelta(0)

    @staticmethod
    def _parse_time(ts: str | datetime | None) -> datetime:
        if isinstance(ts, datetime):
            return ts
        if isinstance(ts, str):
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.utcnow()
