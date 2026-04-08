"""Broker startup and connection logic."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from config import Config
    from broker.interfaces import Broker

logger = logging.getLogger(__name__)


async def setup_brokers(
    config: Config,
    db: Any,
    broker: Broker | None,
) -> tuple[Broker | None, dict[str, Broker], Any]:
    """
    Initialize trading brokers (IBKR, Alpaca, Tradier) with retry logic.

    Returns:
        (primary_broker, all_brokers_dict, paper_store)
    """
    from broker.paper import PaperBroker

    if isinstance(broker, PaperBroker):
        await broker._store.init_tables()

    # --- Paper trading mode: replace broker with PaperBroker ---
    _paper_store = None
    if config.paper_trading:
        from broker.paper import PaperBroker
        from storage.paper import PaperStore

        _paper_store = PaperStore(db)
        await _paper_store.init_tables()

        _initial = config.paper_trading_initial_balance
        await db.execute(
            """
            INSERT OR REPLACE INTO paper_accounts
                (account_id, net_liquidation, buying_power, cash, maintenance_margin)
            VALUES ('PAPER', ?, ?, ?, 0.0)
            """,
            (_initial, _initial, _initial),
        )
        await db.commit()

        # market_data is required for PaperBroker; we'll use a placeholder or 
        # ensure it's wired correctly. Since real_broker might be None,
        # we need a source for market data.
        # DataBus will be wired into it after DataBus is created in app.py.
        # For now, we create it with a placeholder MarketDataProvider if needed,
        # but SimulatedBroker was also created with None data_bus initially.
        
        broker = PaperBroker(
            store=_paper_store,
            market_data=None,  # injected after DataBus is built in app.py
            initial_balance=_initial,
        )
        await broker.connection.connect()
        logger.warning(
            "PAPER TRADING MODE — no real money at risk. Starting balance: $%.2f",
            _initial,
        )

    # --- Worker Mode: skip broker initialization ---
    if config.worker_mode:
        logger.info("WORKER MODE ENABLED — skipping broker and execution setup")
        return None, {}, _paper_store

    # --- Multi-broker startup ---
    _all_brokers: dict = {}

    async def _connect_with_retry(b: Broker, name: str) -> bool:
        _delay = config.reconnect_initial_delay
        for _attempt in range(1, 6):
            try:
                await b.connection.connect()
                return True
            except Exception as _e:
                if _attempt == 5:
                    logger.warning(
                        "%s unreachable after 5 attempts, skipping: %s", name, _e
                    )
                    return False
                logger.info(
                    "%s connect attempt %d failed, retrying in %ds: %s",
                    name,
                    _attempt,
                    _delay,
                    _e,
                )
                await asyncio.sleep(_delay)
                _delay = min(_delay * 2, config.reconnect_max_delay)
        return False

    # IBKR (optional — skip if ib_host is empty or readonly)
    # Lazy connect: register immediately, attempt connection in background.
    # TWS/Gateway may not be running; IBKR auto-reconnects when it comes online.
    if config.ib_host and not config.ib_readonly:
        try:
            from adapters.ibkr.adapter import IBKRBroker

            _ibkr = IBKRBroker(
                host=config.ib_host,
                port=config.ib_port,
                client_id=config.ib_client_id,
                readonly=config.ib_readonly,
                order_timeout=config.order_timeout,
            )
            _all_brokers["ibkr"] = _ibkr
            try:
                await _ibkr.connection.connect()
                logger.info("IBKR broker connected")
            except Exception:
                logger.info(
                    "IBKR not reachable at startup — will auto-reconnect when TWS/Gateway is available"
                )
        except Exception as _ibkr_exc:
            logger.warning("IBKR setup failed (continuing without it): %s", _ibkr_exc)

    # Alpaca (optional — only if configured)
    if config.alpaca_api_key and config.alpaca_secret_key:
        try:
            from adapters.alpaca.adapter import AlpacaBroker

            _alpaca = AlpacaBroker(
                api_key=config.alpaca_api_key,
                secret_key=config.alpaca_secret_key,
                paper=config.alpaca_paper,
                data_feed=config.alpaca_data_feed,
                order_timeout=config.order_timeout,
            )
            if await _connect_with_retry(_alpaca, "Alpaca"):
                _all_brokers["alpaca"] = _alpaca
                logger.info(
                    "Alpaca broker connected (%s)",
                    "paper" if config.alpaca_paper else "LIVE",
                )
        except Exception as _alpaca_exc:
            logger.warning(
                "Alpaca setup failed (continuing without it): %s", _alpaca_exc
            )

    # Tradier (optional — only if configured)
    if config.tradier_token:
        try:
            from adapters.tradier.adapter import TradierBroker

            _tradier = TradierBroker(
                token=config.tradier_token,
                account_id=config.tradier_account_id or "",
                sandbox=config.tradier_sandbox,
                order_timeout=config.order_timeout,
            )
            if await _connect_with_retry(_tradier, "Tradier"):
                _all_brokers["tradier"] = _tradier
                logger.info(
                    "Tradier broker connected (%s)",
                    "sandbox" if config.tradier_sandbox else "LIVE",
                )
        except Exception as _tradier_exc:
            logger.warning(
                "Tradier setup failed (continuing without it): %s", _tradier_exc
            )

    # Fail-fast: at least one broker must be connected
    if not _all_brokers:
        logger.warning(
            "No brokers connected — agent auto-execution will be unavailable"
        )

    # Primary broker selection (skip override when paper trading)
    if not config.paper_trading:
        if config.primary_broker and config.primary_broker in _all_brokers:
            broker = _all_brokers[config.primary_broker]
            logger.info("Primary broker: %s (explicit config)", config.primary_broker)
        elif _all_brokers:
            # Priority fallback: ibkr > alpaca > tradier
            for _preferred in ("ibkr", "alpaca", "tradier"):
                if _preferred in _all_brokers:
                    broker = _all_brokers[_preferred]
                    logger.info("Primary broker: %s (priority fallback)", _preferred)
                    break
            else:
                broker = next(iter(_all_brokers.values()))
                logger.info(
                    "Primary broker: %s (first connected)", next(iter(_all_brokers))
                )
        else:
            broker = None

    return broker, _all_brokers, _paper_store
