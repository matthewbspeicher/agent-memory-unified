"""
Session Bias Generator — pre-session workflow that scans a watchlist,
applies user-defined criteria from trading_rules.yaml, and produces a
structured daily bias that all agents can reference.

Inspired by tradingview-mcp-jackson's "Morning Brief" pattern.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any

from brief.rules_loader import RulesLoader, TradingRules
from broker.models import Symbol

if TYPE_CHECKING:
    import aiosqlite
    from data.bus import DataBus
    from llm.client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class SymbolBias:
    symbol: str
    bias: str  # "bullish" | "bearish" | "neutral"
    confidence: float  # 0.0 - 1.0
    key_levels: dict[str, float] = field(default_factory=dict)
    indicators: dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""


@dataclass
class SessionBiasReport:
    date: str
    generated_at: str
    overall_bias: str  # "bullish" | "bearish" | "neutral" | "mixed"
    symbols: list[SymbolBias] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)

    def for_symbol(self, ticker: str) -> SymbolBias | None:
        """Look up bias for a specific symbol."""
        for sb in self.symbols:
            if sb.symbol == ticker:
                return sb
        return None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_agent_context(self) -> str:
        """Compact text representation for injection into agent prompts."""
        lines = [f"Session Bias ({self.date}): {self.overall_bias}"]
        for sb in self.symbols:
            lines.append(
                f"  {sb.symbol}: {sb.bias} (conf={sb.confidence:.0%}) — {sb.reasoning}"
            )
        if self.risk_notes:
            lines.append("Risk notes: " + "; ".join(self.risk_notes))
        return "\n".join(lines)


BIAS_PROMPT = """You are a trading analyst generating a pre-session bias report.

Analyze the following market data for each symbol and classify the bias as "bullish", "bearish", or "neutral".

## User-Defined Criteria
Bullish if: {bullish_criteria}
Bearish if: {bearish_criteria}
Neutral if: {neutral_criteria}

## Market Snapshot
{snapshot}

Respond with valid JSON only (no markdown). Format:
{{
  "symbols": [
    {{
      "symbol": "BTCUSD",
      "bias": "bullish",
      "confidence": 0.75,
      "key_levels": {{"support": 62000, "resistance": 68000}},
      "reasoning": "Price above EMA 200, RSI at 58 and rising, MACD histogram positive"
    }}
  ],
  "overall_bias": "bullish",
  "risk_notes": ["High correlation between crypto assets — concentration risk"]
}}"""


class SessionBiasGenerator:
    """Generates and caches daily session bias reports."""

    def __init__(
        self,
        db: aiosqlite.Connection,
        data_bus: DataBus,
        llm: LLMClient | None = None,
        rules_loader: RulesLoader | None = None,
    ) -> None:
        self._db = db
        self._data_bus = data_bus
        self._rules_loader = rules_loader or RulesLoader()
        if llm is not None:
            self._llm = llm
        else:
            from llm.client import LLMClient as _LLMClient

            self._llm = _LLMClient()
        self._cached_bias: SessionBiasReport | None = None
        self._cached_date: str = ""

    async def get_active_bias(self) -> SessionBiasReport | None:
        """Return today's bias from memory cache, DB cache, or None."""
        today = date.today()
        today_iso = today.isoformat()

        # In-memory cache (fast path)
        if self._cached_date == today_iso and self._cached_bias:
            return self._cached_bias

        # DB cache
        try:
            # We use the date object for the parameter as asyncpg expects a date, not a string
            cursor = await self._db.execute(
                "SELECT brief_text FROM daily_briefs WHERE date = $1 AND brief_text LIKE '{%'",
                today,
            )
        except Exception:
            # Fallback for sqlite which uses ? and might prefer string
            try:
                cursor = await self._db.execute(
                    "SELECT brief_text FROM daily_briefs WHERE date = ? AND brief_text LIKE '{%'",
                    (today_iso,),
                )
            except Exception:
                # If both fail, try with object and ?
                cursor = await self._db.execute(
                    "SELECT brief_text FROM daily_briefs WHERE date = ? AND brief_text LIKE '{%'",
                    (today,),
                )

        row = await cursor.fetchone() if hasattr(cursor, 'fetchone') else (cursor[0] if isinstance(cursor, list) and cursor else None)

        # Asyncpg fetchrow returns a Record directly, aiopg/aiosqlite returns a cursor
        if hasattr(self._db, 'fetchrow'):
            row = await self._db.fetchrow(
                "SELECT brief_text FROM daily_briefs WHERE date = $1 AND brief_text LIKE '{%'",
                today,
            )

        if row:
            try:
                report = self._parse_report(today_iso, row[0])
                self._cached_bias = report
                self._cached_date = today_iso
                return report
            except Exception:
                return None
        return None
        return None

    async def generate(self) -> SessionBiasReport:
        """Generate fresh session bias for today."""
        rules = self._rules_loader.get()
        snapshot = await self._gather_market_snapshot(rules)
        today = date.today().isoformat()

        prompt = BIAS_PROMPT.format(
            bullish_criteria="; ".join(rules.session_bias.bullish_criteria),
            bearish_criteria="; ".join(rules.session_bias.bearish_criteria),
            neutral_criteria="; ".join(rules.session_bias.neutral_criteria),
            snapshot=snapshot,
        )

        report: SessionBiasReport | None = None
        try:
            result = await self._llm.complete(prompt, max_tokens=1000)
            if result.text:
                report = self._parse_report(today, result.text)
        except Exception as e:
            logger.warning("Session bias LLM call failed: %s", e)

        if report is None:
            report = await self._fallback_bias(today, rules)

        # Persist to daily_briefs table (as JSON)
        now = datetime.now(timezone.utc).isoformat()
        report_json = json.dumps(report.to_dict())
        await self._db.execute(
            "INSERT OR REPLACE INTO daily_briefs (date, brief_text, created_at) VALUES (?, ?, ?)",
            (today, report_json, now),
        )
        await self._db.commit()

        self._cached_bias = report
        self._cached_date = today
        logger.info(
            "Session bias generated: overall=%s, %d symbols analyzed",
            report.overall_bias,
            len(report.symbols),
        )
        return report

    async def get_or_generate(self) -> SessionBiasReport:
        """Return cached bias or generate fresh."""
        existing = await self.get_active_bias()
        if existing:
            return existing
        return await self.generate()

    async def _gather_market_snapshot(self, rules: TradingRules) -> str:
        """Fetch indicator data for all watchlist symbols using existing DataBus methods."""
        sections = []

        for ticker in rules.all_symbols:
            symbol = Symbol(ticker=ticker)
            data_points: dict[str, Any] = {"symbol": ticker}

            try:
                quote = await self._data_bus.get_quote(symbol)
                data_points["price"] = float(quote.last) if quote.last else 0
            except Exception as e:
                data_points["price"] = "unavailable"
                logger.debug("Quote fetch failed for %s: %s", ticker, e)

            # Fetch indicators in parallel-safe manner (DataBus caches internally)
            for indicator in rules.session_bias.indicators:
                try:
                    if indicator == "rsi_14":
                        data_points["rsi_14"] = round(
                            await self._data_bus.get_rsi(symbol, 14), 2
                        )
                    elif indicator == "ema_20":
                        data_points["ema_20"] = round(
                            await self._data_bus.get_ema(symbol, 20), 2
                        )
                    elif indicator == "ema_200":
                        data_points["ema_200"] = round(
                            await self._data_bus.get_ema(symbol, 200), 2
                        )
                    elif indicator == "macd":
                        macd = await self._data_bus.get_macd(symbol)
                        data_points["macd_line"] = round(macd.macd_line, 4)
                        data_points["macd_signal"] = round(macd.signal_line, 4)
                        data_points["macd_histogram"] = round(macd.histogram, 4)
                    elif indicator == "bollinger_20_2":
                        bb = await self._data_bus.get_bollinger(symbol, 20, 2.0)
                        data_points["bb_upper"] = round(bb.upper, 2)
                        data_points["bb_middle"] = round(bb.middle, 2)
                        data_points["bb_lower"] = round(bb.lower, 2)
                except Exception as e:
                    data_points[indicator] = "unavailable"
                    logger.debug("Indicator %s failed for %s: %s", indicator, ticker, e)

            sections.append(json.dumps(data_points, indent=2))

        return "\n\n".join(sections)

    def _parse_report(self, today: str, text: str) -> SessionBiasReport:
        """Parse LLM JSON response into a SessionBiasReport."""
        # Strip markdown code fences if present
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        data = json.loads(cleaned)
        symbols = []
        for s in data.get("symbols", []):
            symbols.append(
                SymbolBias(
                    symbol=s["symbol"],
                    bias=s.get("bias", "neutral"),
                    confidence=float(s.get("confidence", 0.5)),
                    key_levels=s.get("key_levels", {}),
                    reasoning=s.get("reasoning", ""),
                )
            )

        return SessionBiasReport(
            date=today,
            generated_at=datetime.now(timezone.utc).isoformat(),
            overall_bias=data.get("overall_bias", "neutral"),
            symbols=symbols,
            risk_notes=data.get("risk_notes", []),
        )

    async def _fallback_bias(
        self, today: str, rules: TradingRules
    ) -> SessionBiasReport:
        """Rule-based fallback when LLM is unavailable."""
        symbols = []
        for ticker in rules.all_symbols:
            symbol = Symbol(ticker=ticker)
            bias = "neutral"
            confidence = 0.5
            indicators: dict[str, Any] = {}

            try:
                rsi = await self._data_bus.get_rsi(symbol, 14)
                indicators["rsi_14"] = round(rsi, 2)

                ema_20 = await self._data_bus.get_ema(symbol, 20)
                ema_200 = await self._data_bus.get_ema(symbol, 200)
                indicators["ema_20"] = round(ema_20, 2)
                indicators["ema_200"] = round(ema_200, 2)

                quote = await self._data_bus.get_quote(symbol)
                price = float(quote.last)

                # Simple rule-based bias
                bullish_signals = 0
                bearish_signals = 0

                if price > ema_200:
                    bullish_signals += 1
                else:
                    bearish_signals += 1

                if 40 <= rsi <= 70:
                    bullish_signals += 1
                elif rsi < 40:
                    bearish_signals += 1

                macd = await self._data_bus.get_macd(symbol)
                indicators["macd_histogram"] = round(macd.histogram, 4)
                if macd.histogram > 0:
                    bullish_signals += 1
                else:
                    bearish_signals += 1

                if bullish_signals > bearish_signals:
                    bias = "bullish"
                    confidence = min(
                        0.9, 0.5 + (bullish_signals - bearish_signals) * 0.15
                    )
                elif bearish_signals > bullish_signals:
                    bias = "bearish"
                    confidence = min(
                        0.9, 0.5 + (bearish_signals - bullish_signals) * 0.15
                    )

            except Exception as e:
                logger.debug("Fallback bias calculation failed for %s: %s", ticker, e)

            symbols.append(
                SymbolBias(
                    symbol=ticker,
                    bias=bias,
                    confidence=confidence,
                    indicators=indicators,
                    reasoning="Rule-based fallback (LLM unavailable)",
                )
            )

        # Determine overall bias from symbol biases
        bias_counts = {"bullish": 0, "bearish": 0, "neutral": 0}
        for sb in symbols:
            bias_counts[sb.bias] = bias_counts.get(sb.bias, 0) + 1
        max_bias = max(bias_counts, key=bias_counts.get)  # type: ignore[arg-type]
        overall = max_bias if bias_counts[max_bias] > len(symbols) / 2 else "mixed"

        return SessionBiasReport(
            date=today,
            generated_at=datetime.now(timezone.utc).isoformat(),
            overall_bias=overall,
            symbols=symbols,
            risk_notes=["Generated via rule-based fallback — LLM unavailable"],
        )
