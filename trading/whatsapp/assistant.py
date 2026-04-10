from __future__ import annotations
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from whatsapp.proactive import HermesProactiveOps

from agents.models import OpportunityStatus
from whatsapp.commands import parse_command
from whatsapp.confirmation import ConfirmationGate, PendingAction

if TYPE_CHECKING:
    from broker.interfaces import Broker
    from agents.runner import AgentRunner
    from risk.engine import RiskEngine
    from storage.opportunities import OpportunityStore
    from data.bus import DataBus
    from whatsapp.client import WhatsAppClient

logger = logging.getLogger(__name__)

HELP_TEXT = """Available commands:
/portfolio — account summary (all brokers)
/portfolio detailed — full position breakdown
/portfolio fidelity — Fidelity positions only
/opportunities — recent opportunities
/agents — agent status
/approve <id> — approve opportunity
/reject <id> — reject opportunity
/buy <symbol> <qty> — place buy order
/sell <symbol> <qty> — place sell order
/chart <symbol> — price chart
/start <name> — start agent
/stop <name> — stop agent
/kill — enable kill switch
/unkill — disable kill switch
/markets — show top prediction markets
/rank — Agent rivalry leaderboard (Sharpe + ELO)
/journal — Trade journal with AI autopsies
/brief — Morning intelligence brief
/warroom — Convergence signals across agents
/backtest <agent> [symbols] [period] — Run strategy backtest
/regime [symbol] — Market regime detection (default: SPY)
/paper status — Paper trading balance, positions, P&L
/paper reset — Reset paper account to initial balance
/tournament — Stage transition log
OVERRIDE PROMOTE <agent> — promote agent one stage
OVERRIDE DEMOTE <agent> — demote agent to stage 0
/help — this message

Or just ask me anything in plain English!"""

SYSTEM_PROMPT = """You are a trading co-pilot assistant. You help the user monitor their portfolio, review opportunities found by scanning agents, and place trades. Be concise — responses are read on a phone screen. Use plain text formatting (no markdown). When showing numbers, use $ for currency and % for percentages."""


class WhatsAppAssistant:
    def __init__(
        self,
        client: WhatsAppClient,
        broker: Broker,
        runner: AgentRunner,
        opp_store: OpportunityStore,
        risk_engine: RiskEngine,
        account_id: str = "U123",
        llm_client=None,
        external_store=None,
        data_bus: "DataBus" = None,
        leaderboard_engine=None,
        journal_service=None,
        brief_generator=None,
        warroom_engine=None,
        liquidity_detector=None,
        paper_broker=None,
        tournament_engine=None,
        db=None,
        remembr_client=None,
        agent_store=None,
        perf_store=None,
        settings=None,
    ) -> None:
        self._client = client
        self._broker = broker
        self._runner = runner
        self._opp_store = opp_store
        self._risk_engine = risk_engine
        self._account_id = account_id
        self._confirmation = ConfirmationGate()
        self._conversations: dict[str, list[dict]] = {}
        self._llm_client = llm_client
        self._external_store = external_store
        self._data_bus = data_bus
        self._leaderboard_engine = leaderboard_engine
        self._journal_service = journal_service
        self._brief_generator = brief_generator
        self._warroom_engine = warroom_engine
        self._liquidity_detector = liquidity_detector
        self._paper_broker = paper_broker
        self._tournament_engine = tournament_engine
        self._db = db
        self._remembr = remembr_client  # AsyncRemembrClient for user memory
        self._agent_store = agent_store  # AgentStore for evolution spawning
        self._perf_store = perf_store
        self._settings = settings
        self._journal_listing: dict[str, list[int]] = {}  # phone → [position_ids]
        self._proactive_ops: "HermesProactiveOps | None" = None

    def start_proactive(self, allowed_numbers: list[str]) -> None:
        """Starts background proactive monitoring tasks (Track 14)."""
        if self._proactive_ops is None:
            from whatsapp.proactive import HermesProactiveOps

            self._proactive_ops = HermesProactiveOps(self, allowed_numbers)
            self._proactive_ops.start()

    async def handle(self, phone: str, text: str, message_id: str) -> None:
        try:
            await self._client.mark_read(message_id)
        except Exception:
            pass

        self._client.record_inbound(phone)
        if self._db:
            try:
                await self._client.persist_session(self._db, phone)
            except Exception:
                logger.debug("Failed to persist WhatsApp session for %s", phone[:5])

        text_upper = text.strip().upper()
        if self._confirmation.has_pending(phone):
            if text_upper in ("CANCEL", "NO", "NEVERMIND"):
                self._confirmation.cancel(phone)
                await self._client.send_text(phone, "Cancelled.")
                return

            pending_action: PendingAction | None = self._confirmation._pending.get(
                phone
            )
            if pending_action:
                action = pending_action.action_type
                data = pending_action.data
            else:
                confirmed: PendingAction | None = self._confirmation.confirm(
                    phone, text_upper
                )
                if confirmed:
                    await self._execute_confirmed(phone, confirmed)
                    return

        # Tournament override commands — checked before general command parsing
        upper = text.strip().upper()
        if upper.startswith("OVERRIDE ") and self._tournament_engine:
            parts = text.strip().split()
            # Format: OVERRIDE PROMOTE|DEMOTE <agent_name>
            if len(parts) >= 3:
                action = parts[1].lower()
                agent_name = parts[2]
                result = await self._tournament_engine.override(
                    agent_name, action, by=phone
                )
                await self._client.send_text(phone, result)
                return

        cmd = parse_command(text)
        if cmd:
            await self._handle_command(phone, cmd.name, cmd.args)
            return

        await self._handle_llm(phone, text)

    async def _handle_command(self, phone: str, name: str, args: list[str]) -> None:
        if name == "help":
            await self._client.send_text(phone, HELP_TEXT)

        elif name == "portfolio":
            result = await self._cmd_portfolio(args)
            await self._client.send_text(phone, result)

        elif name == "opportunities":
            opps = await self._opp_store.list(limit=10)
            if not opps:
                await self._client.send_text(phone, "No recent opportunities.")
                return
            lines = []
            for o in opps:
                lines.append(
                    f"• {o['symbol']} — {o['signal']} ({o['status']}) [{o['agent_name']}]"
                )
            await self._client.send_text(phone, "\n".join(lines))

        elif name == "agents":
            agents = self._runner.list_agents()
            if not agents:
                await self._client.send_text(phone, "No agents registered.")
                return
            lines = [f"• {a.name}: {a.status.value}" for a in agents]
            await self._client.send_text(phone, "\n".join(lines))

        elif name == "approve" and args:
            opp = await self._opp_store.get(args[0])
            if not opp:
                await self._client.send_text(phone, f"Opportunity {args[0]} not found.")
                return
            await self._opp_store.update_status(args[0], OpportunityStatus.APPROVED)
            await self._client.send_text(phone, f"Approved {args[0]}.")

        elif name == "reject" and args:
            await self._opp_store.update_status(args[0], OpportunityStatus.REJECTED)
            await self._client.send_text(phone, f"Rejected {args[0]}.")

        elif name in ("buy", "sell") and len(args) >= 2:
            symbol, qty = args[0].upper(), args[1]
            action = "BUY" if name == "buy" else "SELL"
            token = self._confirmation.create(
                phone,
                "place_order",
                {
                    "symbol": symbol,
                    "side": action,
                    "quantity": qty,
                },
            )
            await self._client.send_text(
                phone,
                f"Place market {action.lower()}: {qty} shares {symbol}.\n\nReply *{token}* to confirm, or CANCEL.",
            )

        elif name == "chart" and args:
            await self._cmd_chart(phone, args[0].upper())

        elif name == "kill":
            token = self._confirmation.create(phone, "toggle_kill", {"enable": True})
            await self._client.send_text(
                phone, f"Enable kill switch?\n\nReply *{token}* to confirm, or CANCEL."
            )

        elif name == "unkill":
            token = self._confirmation.create(phone, "toggle_kill", {"enable": False})
            await self._client.send_text(
                phone, f"Disable kill switch?\n\nReply *{token}* to confirm, or CANCEL."
            )

        elif name == "start" and args:
            token = self._confirmation.create(phone, "start_agent", {"name": args[0]})
            await self._client.send_text(
                phone,
                f"Start agent '{args[0]}'?\n\nReply *{token}* to confirm, or CANCEL.",
            )

        elif name == "stop" and args:
            token = self._confirmation.create(phone, "stop_agent", {"name": args[0]})
            await self._client.send_text(
                phone,
                f"Stop agent '{args[0]}'?\n\nReply *{token}* to confirm, or CANCEL.",
            )

        elif name == "markets":
            await self._cmd_markets(phone)

        elif name == "rank":
            result = await self._cmd_rank()
            await self._client.send_text(phone, result)

        elif name == "journal":
            result = await self._cmd_journal(phone, args)
            await self._client.send_text(phone, result)

        elif name == "brief":
            result = await self._cmd_brief()
            await self._client.send_text(phone, result)

        elif name == "warroom":
            result = await self._cmd_warroom()
            await self._client.send_text(phone, result)

        elif name == "backtest":
            await self._cmd_backtest(phone, args)

        elif name == "regime":
            await self._cmd_regime(phone, args)

        elif name == "paper":
            await self._cmd_paper(phone, args)

        else:
            await self._client.send_text(
                phone, f"Missing arguments for /{name}. Try /help."
            )

    async def _cmd_markets(self, phone: str) -> None:
        if not self._data_bus:
            await self._client.send_text(phone, "Market data bus is unavailable.")
            return

        markets = (
            await self._data_bus.get_kalshi_markets()
            if hasattr(self._data_bus, "get_kalshi_markets")
            else []
        )
        pred_markets = [
            m
            for m in markets
            if hasattr(m, "mid_probability") and m.mid_probability is not None
        ]

        if not pred_markets:
            await self._client.send_text(
                phone, "No active prediction markets found right now."
            )
            return

        top = sorted(
            pred_markets, key=lambda m: getattr(m, "volume_24h", 0) or 0, reverse=True
        )[:5]

        lines = ["*Top Prediction Markets*"]
        for idx, m in enumerate(top, 1):
            source = "Poly" if m.ticker.startswith("0x") else "Kalshi"
            prob = int(m.mid_probability * 100)
            lines.append(
                f"{idx}. {getattr(m, 'title', m.ticker)} ({source}) — YES @ {prob}¢"
            )

        await self._client.send_text(phone, "\n".join(lines))

    async def _cmd_portfolio(self, args: list[str]) -> str:
        subcommand = args[0].lower() if args else ""

        if subcommand == "fidelity":
            return await self._fmt_fidelity_only()
        elif subcommand == "detailed":
            return await self._fmt_portfolio_detailed()
        else:
            return await self._fmt_portfolio_summary()

    async def _fmt_portfolio_summary(self) -> str:
        lines: list[str] = []
        total_nlv = Decimal("0")

        # IBKR
        try:
            balance = await self._broker.account.get_balances(self._account_id)
            lines.append(f"IBKR — ${balance.net_liquidation:,.2f}")
            total_nlv += Decimal(str(balance.net_liquidation))
        except Exception as e:
            lines.append(f"IBKR — error: {e}")

        # External brokers
        staleness = await self._get_staleness_warning()
        if self._external_store:
            try:
                ext_balances = await self._external_store.get_balances()
                for b in ext_balances:
                    nlv = Decimal(b["net_liquidation"])
                    name = b.get("account_name", b["account_id"])
                    lines.append(f"Fidelity ({name}) — ${nlv:,.2f}")
                    total_nlv += nlv
            except Exception as e:
                lines.append(f"Fidelity — error: {e}")

        lines.insert(0, f"Portfolio Total — ${total_nlv:,.2f}")
        lines.insert(1, "")
        if staleness:
            lines.append("")
            lines.append(staleness)
        return "\n".join(lines)

    async def _fmt_portfolio_detailed(self) -> str:
        lines: list[str] = []

        # IBKR positions
        try:
            positions = await self._broker.account.get_positions(self._account_id)
            balance = await self._broker.account.get_balances(self._account_id)
            lines.append(f"=== IBKR — ${balance.net_liquidation:,.2f} ===")
            lines.append(
                f"Cash: ${balance.cash:,.2f} | Buying Power: ${balance.buying_power:,.2f}"
            )
            if positions:
                for p in positions:
                    lines.append(
                        f"  {p.symbol.ticker}: {p.quantity} @ ${p.avg_cost:,.2f} (P&L: ${p.unrealized_pnl:+,.2f})"
                    )
            else:
                lines.append("  No open positions.")
        except Exception as e:
            lines.append(f"IBKR — error: {e}")

        # External positions
        if self._external_store:
            staleness = await self._get_staleness_warning()
            try:
                ext_balances = await self._external_store.get_balances()
                ext_positions = await self._external_store.get_positions()
                # Group positions by account
                by_account: dict[str, list[dict[str, Any]]] = {}
                for p in ext_positions:
                    by_account.setdefault(p["account_id"], []).append(p)

                for b in ext_balances:
                    acct_id = b["account_id"]
                    name = b.get("account_name", acct_id)
                    nlv = Decimal(b["net_liquidation"])
                    lines.append("")
                    lines.append(f"=== Fidelity ({name}) — ${nlv:,.2f} ===")
                    acct_positions = by_account.get(acct_id, [])
                    if acct_positions:
                        for p in acct_positions:
                            qty = Decimal(str(p["quantity"]))
                            price = Decimal(str(p["last_price"]))
                            ticker = str(p["symbol"])
                            lines.append(f"  {ticker}: {qty} @ ${price:,.2f}")
                    else:
                        lines.append("  No positions.")
            except Exception as e:
                lines.append(f"\nFidelity — error: {e}")
            if staleness:
                lines.append("")
                lines.append(staleness)
        return "\n".join(lines)

    async def _fmt_fidelity_only(self) -> str:
        if not self._external_store:
            return "No external portfolio data. Import via /import or POST /import/fidelity."
        staleness = await self._get_staleness_warning()
        try:
            ext_balances = await self._external_store.get_balances(broker="fidelity")
            ext_positions = await self._external_store.get_positions(broker="fidelity")
        except Exception as e:
            return f"Fidelity data error: {e}"

        if not ext_balances:
            return "No Fidelity data imported yet."

        lines: list[str] = []
        by_account: dict[str, list[dict]] = {}
        for p in ext_positions:
            by_account.setdefault(p["account_id"], []).append(p)

        for b in ext_balances:
            acct_id = b["account_id"]
            name = b.get("account_name", acct_id)
            nlv = Decimal(b["net_liquidation"])
            lines.append(f"=== {name} — ${nlv:,.2f} ===")
            acct_positions = by_account.get(acct_id, [])
            if acct_positions:
                for p in acct_positions:
                    qty = Decimal(p["quantity"])
                    price = Decimal(p["last_price"])
                    cb = ""
                    if p.get("cost_basis"):
                        cb = f" (cost: ${Decimal(p['cost_basis']):,.2f})"
                    lines.append(f"  {p['symbol']}: {qty} @ ${price:,.2f}{cb}")
            lines.append("")
        if staleness:
            lines.append(staleness)
        return "\n".join(lines).rstrip()

    async def _get_staleness_warning(self) -> str | None:
        if not self._external_store:
            return None
        try:
            age = await self._external_store.get_import_age("fidelity")
            if age is not None and age > 24:
                return f"Warning: Fidelity data last updated {age:.0f} hours ago"
        except Exception:
            pass
        return None

    async def _cmd_chart(self, phone: str, symbol: str) -> None:
        try:
            from broker.models import Symbol as Sym, AssetType
            from whatsapp.charts import render_price_chart

            data_bus = getattr(self._runner, "_data_bus", None)
            if data_bus:
                sym = Sym(ticker=symbol, asset_type=AssetType.STOCK)
                bars = await data_bus.get_historical(sym, period="1mo")
                png = render_price_chart(symbol, bars)
                await self._client.send_image(phone, png, caption=f"{symbol} — 1 month")
            else:
                await self._client.send_text(phone, "Chart generation unavailable.")
        except Exception as e:
            logger.error("Chart generation failed: %s", e)
            await self._client.send_text(phone, f"Chart error: {e}")

    async def _execute_confirmed(self, phone: str, action) -> None:
        if action.action_type == "place_order":
            try:
                from broker.models import (
                    Symbol as Sym,
                    AssetType,
                    OrderSide,
                    MarketOrder,
                )
                from decimal import Decimal

                sym = Sym(ticker=action.data["symbol"], asset_type=AssetType.STOCK)
                side = OrderSide.BUY if action.data["side"] == "BUY" else OrderSide.SELL
                order = MarketOrder(
                    symbol=sym,
                    side=side,
                    quantity=Decimal(action.data["quantity"]),
                    account_id=self._account_id,
                )
                result = await self._broker.orders.place_order(self._account_id, order)
                msg = f"Order placed: {result.status.value}\n{action.data['side']} {action.data['quantity']} {action.data['symbol']}"
                if result.avg_fill_price:
                    msg += f"\nFill: ${result.avg_fill_price:,.2f}"
                await self._client.send_text(phone, msg)
            except Exception as e:
                await self._client.send_text(phone, f"Order failed: {e}")

        elif action.action_type == "toggle_kill":
            if action.data["enable"]:
                self._risk_engine.kill_switch.enable("Enabled via WhatsApp")
                await self._client.send_text(phone, "Kill switch ENABLED.")
            else:
                self._risk_engine.kill_switch.disable()
                await self._client.send_text(phone, "Kill switch DISABLED.")

        elif action.action_type == "start_agent":
            try:
                await self._runner.start_agent(action.data["name"])
                await self._client.send_text(
                    phone, f"Agent '{action.data['name']}' started."
                )
            except Exception as e:
                await self._client.send_text(phone, f"Failed to start agent: {e}")

        elif action.action_type == "stop_agent":
            try:
                await self._runner.stop_agent(action.data["name"])
                await self._client.send_text(
                    phone, f"Agent '{action.data['name']}' stopped."
                )
            except Exception as e:
                await self._client.send_text(phone, f"Failed to stop agent: {e}")

        elif action.action_type == "spawn_shadow":
            try:
                agent_store = getattr(self, "_agent_store", None)
                if agent_store:
                    await agent_store.create_evolved_agent(**action.data)
                    await self._client.send_text(
                        phone,
                        f"Shadow agent '{action.data['name']}' spawned successfully.",
                    )
                else:
                    await self._client.send_text(
                        phone, "Agent store not available to spawn shadow agent."
                    )
            except Exception as e:
                await self._client.send_text(
                    phone, f"Failed to spawn shadow agent: {e}"
                )

        elif action.action_type == "paper_reset":
            if not self._paper_broker:
                await self._client.send_text(phone, "Paper trading is not enabled.")
                return
            try:
                await self._paper_broker.reset()
                await self._client.send_text(
                    phone, "Paper account reset to initial balance."
                )
            except Exception as e:
                await self._client.send_text(phone, f"Paper reset failed: {e}")

    async def _cmd_rank(self) -> str:
        """Handle /rank — return agent leaderboard."""
        if not self._leaderboard_engine:
            return "Leaderboard not configured."

        engine = self._leaderboard_engine

        # Check for new data
        if not await engine.is_stale():
            cached = await engine.get_cached_leaderboard()
            if cached:
                return self._format_leaderboard(cached, cached=True)

        # Try full orchestration with remembr.dev
        sync = engine._remembr_sync
        agent_names = [a.name for a in self._runner.list_agents()]

        profiles = None
        agent_map: dict = {}
        if sync:
            agent_map = await sync.ensure_agents_registered(agent_names)
            profiles = await sync.fetch_all_profiles(agent_map)

        if profiles is None and sync:
            # Remembr.dev unreachable — return cached, skip matches
            cached = await engine.get_cached_leaderboard()
            if cached:
                return self._format_leaderboard(cached, cached=True)
            return "No performance data yet."

        rankings = await engine.compute_rankings(profiles)
        if not rankings:
            return "No performance data yet."

        matches = engine.run_matches(rankings)
        rankings = engine.tally_results(matches, rankings)
        current_elo = {r.agent_name: r.elo for r in rankings}
        new_elo = engine.update_elo(matches, current_elo)
        for r in rankings:
            r.elo = new_elo.get(r.agent_name, r.elo)

        # Push to remembr.dev (best-effort)
        if sync:
            await sync.push_matches(matches, agent_map)
            for r in rankings:
                await sync.push_profile(r.agent_name, r, agent_map)

        # Cache locally
        snapshot_ts = await engine.get_latest_snapshot_ts() or ""
        await engine.save_cache(rankings, snapshot_ts, source="live")

        return self._format_leaderboard(rankings, cached=False)

    def _format_leaderboard(self, rankings: list, cached: bool = False) -> str:
        """Format rankings as a WhatsApp-friendly table."""
        header = "\U0001f3c6 Agent Leaderboard"
        if cached:
            header += " (cached)"

        lines = [header, ""]
        lines.append(" #  Agent              Sharpe  ELO   W/L")
        for i, r in enumerate(rankings[:10], 1):
            name = r.agent_name[:18].ljust(18)
            sharpe = f"{r.sharpe_ratio:5.2f}"
            elo = f"{r.elo:4d}"
            wl = f"{r.win_count}/{r.loss_count}"
            lines.append(f"{i:2d}. {name} {sharpe}  {elo}  {wl}")

        if len(rankings) > 10:
            lines.append(f"... and {len(rankings) - 10} more")

        lines.append("")
        if cached:
            lines.append("Serving cached data")
        else:
            lines.append("Updated just now")

        return "\n".join(lines)

    async def _cmd_journal(self, phone: str, args: list[str]) -> str:
        if not self._journal_service:
            return "Trade journal not configured."

        # /journal <number> → drill into that trade from last listing
        if args and args[0].isdigit():
            idx = int(args[0])
            listing = self._journal_listing.get(phone, [])
            if 1 <= idx <= len(listing):
                position_id = listing[idx - 1]
                detail = await self._journal_service.get_trade_detail(position_id)
                if detail:
                    return self._format_journal_detail(idx, detail)
                return f"Trade #{idx} not found."
            return f"Invalid trade number. Use 1-{len(listing)}."

        # /journal <agent_name> or /journal <limit> or /journal
        agent_filter = None
        limit = 5
        if args:
            arg = args[0]
            if arg.isdigit():
                limit = int(arg)
            else:
                agent_filter = arg

        entries = await self._journal_service.list_trades(
            agent_name=agent_filter, limit=limit
        )
        if not entries:
            return "No closed trades yet."

        # Store listing for drill-in
        self._journal_listing[phone] = [e.position_id for e in entries]
        return self._format_journal_listing(entries)

    async def _cmd_brief(self) -> str:
        if not self._brief_generator:
            return "Morning Brief not configured."
        data = await self._brief_generator.get_or_generate()
        return f"Morning Brief ({data['date']}):\n\n{data['brief']}"

    async def _cmd_warroom(self) -> str:
        if not self._warroom_engine:
            return "War Room not configured."
        signals = await self._warroom_engine.detect_convergences(hours=4)
        if not signals:
            return "No convergence signals right now."
        lines = ["Convergence Signals:"]
        for s in signals[:5]:
            agents = ", ".join(s.agents)
            lines.append(
                f"\n{s.direction} {s.symbol} — {len(s.agents)} agents agree ({agents})"
            )
            lines.append(f"  Avg confidence: {s.avg_confidence:.0%}")
            if s.synthesis:
                lines.append(f"  {s.synthesis[:100]}...")
        return "\n".join(lines)

    def _format_journal_listing(self, entries: list) -> str:
        lines = ["\U0001f4d4 Trade Journal", ""]
        lines.append(" #  Agent           Symbol  P&L      Side")
        for i, e in enumerate(entries, 1):
            name = e.agent_name[:15].ljust(15)
            symbol = e.symbol[:6].ljust(6)
            pnl_str = f"{'+' if e.pnl >= 0 else ''}{e.pnl:.2f}"
            pnl_display = f"${pnl_str}".ljust(8)
            lines.append(f"{i:2d}. {name} {symbol}  {pnl_display} {e.side.upper()}")
        lines.append("")
        lines.append("Reply /journal <#> for full autopsy")
        return "\n".join(lines)

    def _format_journal_detail(self, idx: int, detail) -> str:
        e = detail.entry
        lines = [
            f"\U0001f4d4 Trade #{idx} — {e.symbol} ({e.side.upper()})",
            "",
            f"Entry: ${detail.entry_price} → Exit: ${detail.exit_price}",
            f"Qty: {detail.quantity} | P&L: ${'+' if e.pnl >= 0 else ''}{e.pnl:.2f} ({e.pnl_pct:+.1f}%)",
            f"Duration: {detail.duration_hours:.1f}h | Max drawdown: {detail.max_adverse_excursion}",
            f"Agent: {e.agent_name} | Exit reason: {detail.exit_reason}",
            "",
            "\U0001f50d Autopsy:",
            detail.autopsy,
        ]
        return "\n".join(lines)

    async def _cmd_paper(self, phone: str, args: list[str]) -> None:
        """Handle /paper [status|reset] — paper trading account management."""
        subcommand = args[0].lower() if args else "status"

        if not self._paper_broker:
            await self._client.send_text(
                phone,
                "Paper trading is not enabled. Set STA_PAPER_TRADING=true to enable it.",
            )
            return

        if subcommand == "reset":
            token = self._confirmation.create(phone, "paper_reset", {})
            await self._client.send_text(
                phone,
                f"Reset paper account to initial balance? All positions and history will be cleared.\n\nReply *{token}* to confirm, or CANCEL.",
            )
            return

        # Default: status
        try:
            balance = await self._paper_broker.account.get_balances("PAPER")
            positions = await self._paper_broker.account.get_positions("PAPER")

            lines = ["PAPER TRADING ACCOUNT", ""]
            lines.append(f"Cash: ${balance.cash:,.2f}")
            lines.append(f"Buying Power: ${balance.buying_power:,.2f}")

            if positions:
                lines.append("")
                lines.append("Open Positions:")
                total_unrealized = Decimal("0")
                for p in positions:
                    lines.append(
                        f"  {p.symbol.ticker}: {p.quantity} @ ${p.avg_cost:,.4f}"
                        f" (realized P&L: ${p.realized_pnl:+,.2f})"
                    )
                    total_unrealized += p.realized_pnl
                lines.append(f"Total Realized P&L: ${total_unrealized:+,.2f}")
            else:
                lines.append("")
                lines.append("No open positions.")

            await self._client.send_text(phone, "\n".join(lines))
        except Exception as exc:
            logger.error("Paper status failed: %s", exc)
            await self._client.send_text(phone, f"Paper account error: {exc}")

    async def _recall_memories(self, phone: str, text: str) -> str:
        """Search remembr.dev for relevant user memories. Returns context string or empty."""
        if not self._remembr:
            return ""
        try:
            results = await self._remembr.search(
                q=text, limit=5, tags=[f"wa:{phone[-4:]}"]
            )
            if not results:
                results = await self._remembr.search(q=text, limit=3)
            if results:
                lines = [r.get("value", "") for r in results if r.get("value")]
                return "\n".join(lines[:5])
        except Exception as e:
            logger.debug("Memory recall failed: %s", e)
        return ""

    async def _store_memory(self, phone: str, user_text: str, reply: str) -> None:
        """Extract and store memorable facts from the conversation. Best-effort."""
        if not self._remembr or not self._llm_client:
            return
        try:
            prompt = (
                f"Extract any user preferences, trading style, or important facts worth remembering from this exchange. "
                f"Return ONLY the facts as a short bullet list, or 'NONE' if nothing worth storing.\n\n"
                f"User: {user_text}\nAssistant: {reply}"
            )
            result = await self._llm_client.complete(prompt, max_tokens=200)

            facts = result.text.strip()
            if facts.upper() == "NONE" or len(facts) < 10:
                return
            await self._remembr.store(
                value=facts,
                tags=[f"wa:{phone[-4:]}", "user_preference"],
                ttl="180d",
            )
        except Exception as e:
            logger.debug("Memory store failed: %s", e)

    async def _handle_llm(self, phone: str, text: str) -> None:
        if not self._llm_client:
            await self._client.send_text(
                phone, "LLM not configured. Use /help for available commands."
            )
            return

        history = self._conversations.get(phone, [])
        history.append({"role": "user", "content": text})
        if len(history) > 10:
            history = history[-10:]

        # Recall relevant memories from remembr.dev
        memories = await self._recall_memories(phone, text)
        system = SYSTEM_PROMPT
        if memories:
            system += f"\n\nRelevant context from past conversations:\n{memories}"

        try:
            result = await self._llm_client.chat(
                system=system,
                messages=history,
                max_tokens=500,
            )
            reply = result.text
            history.append({"role": "assistant", "content": reply})
            self._conversations[phone] = history
            await self._client.send_text(phone, reply)

            # Store memorable facts (best-effort, don't block response)
            try:
                await self._store_memory(phone, text, reply)
            except Exception:
                pass
        except Exception as e:
            logger.error("LLM call failed: %s", e)

    async def _cmd_backtest(self, phone: str, args: list[str]) -> None:
        if not args:
            await self._client.send_text(
                phone, "Usage: /backtest <agent_name> [symbol1,symbol2] [period]"
            )
            return
        agent_name = args[0]
        symbols = args[1].split(",") if len(args) > 1 else ["AAPL", "MSFT", "GOOGL"]
        period = args[2] if len(args) > 2 else "6mo"
        await self._client.send_text(phone, f"Running backtest for {agent_name}...")
        try:
            from data.backtest import (
                BacktestEngine,
                HistoricalDataSource,
                ReplayDataBus,
                score_backtest_run,
            )
            from broker.models import Symbol, AssetType

            if not self._runner or not self._data_bus:
                await self._client.send_text(
                    phone, "Agent framework or DataBus not available."
                )
                return
            agent = self._runner._agents.get(agent_name)
            if not agent:
                await self._client.send_text(phone, f"Agent '{agent_name}' not found.")
                return
            bars_by_symbol: dict = {}
            for ticker in symbols:
                sym = Symbol(ticker=ticker, asset_type=AssetType.STOCK)
                try:
                    bars = await self._data_bus.get_historical(
                        sym, timeframe="1d", period=period
                    )
                    if bars:
                        bars_by_symbol[ticker] = bars
                except Exception:
                    pass
            if not bars_by_symbol:
                await self._client.send_text(phone, "No historical data available.")
                return
            hist_source = HistoricalDataSource(bars_by_symbol)
            replay_bus = ReplayDataBus(hist_source)
            engine = BacktestEngine(bus=replay_bus, agents=[agent])
            all_times = sorted(
                {b.timestamp for bars in bars_by_symbol.values() for b in bars}
            )
            raw = await engine.run(all_times)
            result = score_backtest_run(
                agent_name=agent_name,
                parameters=agent.parameters if hasattr(agent, "parameters") else {},
                snapshots=raw["snapshots"],
                initial_equity=raw["initial_equity"],
                final_equity=raw["final_equity"],
            )
            deployable = "YES" if result.is_deployable() else "NO"
            msg = (
                f"Backtest: {agent_name}\n"
                f"Period: {result.data_start} - {result.data_end}\n"
                f"Trades: {result.total_trades}\n"
                f"P&L: ${result.total_pnl:,.2f}\n"
                f"Win Rate: {result.win_rate:.1%}\n"
                f"Sharpe: {result.sharpe_ratio:.2f}\n"
                f"Max DD: {result.max_drawdown:.1%}\n"
                f"Profit Factor: {result.profit_factor:.2f}\n"
                f"Deployable: {deployable}"
            )
            await self._client.send_text(phone, msg)
        except Exception as exc:
            logger.error("Backtest failed: %s", exc)
            await self._client.send_text(phone, f"Backtest failed: {exc}")
            await self._client.send_text(
                phone, "Sorry, something went wrong. Try a /command instead."
            )

    async def _cmd_regime(self, phone: str, args: list[str]) -> None:
        """Handle /regime [symbol] — detect current market regime."""
        symbol = args[0].upper() if args else "SPY"
        if not self._data_bus:
            await self._client.send_text(phone, "Market data bus is unavailable.")
            return
        try:
            from broker.models import Symbol as Sym, AssetType
            from regime.detector import RegimeDetector

            sym = Sym(ticker=symbol, asset_type=AssetType.STOCK)
            bars = await self._data_bus.get_historical(
                sym, timeframe="1d", period="3mo"
            )
            if not bars:
                await self._client.send_text(
                    phone, f"No historical data available for {symbol}."
                )
                return
            detector = RegimeDetector()
            snapshot = detector.detect_with_snapshot(bars)
            regime_label = snapshot.regime.value.replace("_", " ").title()
            lines = [
                f"Market Regime: {symbol}",
                "",
                f"Regime: {regime_label}",
                f"ADX: {snapshot.adx:.1f}" if snapshot.adx is not None else "ADX: N/A",
                f"Volatility: {snapshot.volatility_pct:.1f}%"
                if snapshot.volatility_pct is not None
                else "Volatility: N/A",
                f"SMA Slope: {snapshot.sma_slope:+.3f}"
                if snapshot.sma_slope is not None
                else "SMA Slope: N/A",
                f"Bars Analyzed: {snapshot.bars_analyzed}",
            ]

            # Append prediction market liquidity if a detector is wired up
            liquidity_detector = getattr(self, "_liquidity_detector", None)
            if liquidity_detector:
                lines.append("")
                lines.append("Prediction Market Liquidity:")
                for broker_id in ("kalshi", "polymarket"):
                    try:
                        liq = await liquidity_detector.detect_platform(broker_id)
                        status = liq.regime.value.title()
                        lines.append(
                            f"  {broker_id.title()}: {status}"
                            f" (spread {liq.spread_cents:.1f}c,"
                            f" vol {liq.volume_24h:,.0f})"
                        )
                    except Exception as liq_exc:
                        lines.append(f"  {broker_id.title()}: unavailable ({liq_exc})")

            await self._client.send_text(phone, "\n".join(lines))
        except Exception as exc:
            logger.error("Regime detection failed: %s", exc)
            await self._client.send_text(phone, f"Regime detection failed: {exc}")
