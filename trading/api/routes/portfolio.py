"""GET /portfolio/summary — multi-broker portfolio view."""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, Request

from api.auth import verify_api_key

logger = logging.getLogger(__name__)
router = APIRouter()


def _decimal_to_float(d) -> float:
    return float(d) if isinstance(d, Decimal) else d


async def _fetch_broker(name: str, broker, settings) -> tuple[str, dict]:
    """Fetch balance + positions for a single broker. Returns (name, entry)."""
    # Derive account_id from the broker's own account list
    try:
        accounts = await broker.account.get_accounts()
        account_id = accounts[0].account_id if accounts else name.upper()
    except Exception:
        account_id = name.upper()

    entry: dict = {
        "balance": {"net_liquidation": 0, "buying_power": 0, "cash": 0},
        "positions": [],
        "connected": broker.connection.is_connected(),
    }

    if (
        name == "polymarket"
        and settings
        and getattr(settings, "polymarket_dry_run", False)
    ):
        entry["dry_run"] = True
    if name == "kalshi" and settings and getattr(settings, "kalshi_demo", False):
        entry["demo"] = True

    try:
        balance = await broker.account.get_balances(account_id)
        entry["balance"] = {
            "net_liquidation": _decimal_to_float(balance.net_liquidation),
            "buying_power": _decimal_to_float(balance.buying_power),
            "cash": _decimal_to_float(balance.cash),
        }
    except Exception as exc:
        logger.debug("Failed to fetch balance for %s: %s", name, exc)

    try:
        positions = await broker.account.get_positions(account_id)
        entry["positions"] = [
            {
                "symbol": p.symbol.ticker,
                "quantity": _decimal_to_float(p.quantity),
                "avg_cost": _decimal_to_float(p.avg_cost),
                "market_value": _decimal_to_float(p.market_value),
                "unrealized_pnl": _decimal_to_float(p.unrealized_pnl),
            }
            for p in positions
        ]
    except Exception as exc:
        logger.debug("Failed to fetch positions for %s: %s", name, exc)

    return name, entry


@router.get("/portfolio/summary")
async def portfolio_summary(
    request: Request,
    _: str = Depends(verify_api_key),
):
    brokers = getattr(request.app.state, "brokers", {})
    settings = getattr(request.app.state, "settings", None)

    if not brokers:
        return {
            "brokers": {},
            "totals": {"equity": 0, "buying_power": 0, "open_positions": 0},
        }

    # Fetch all brokers in parallel
    results = await asyncio.gather(
        *[_fetch_broker(name, broker, settings) for name, broker in brokers.items()],
        return_exceptions=True,
    )

    broker_data = {}
    total_equity = Decimal("0")
    total_buying_power = Decimal("0")
    total_positions = 0

    for result in results:
        if isinstance(result, Exception):
            logger.warning("Broker fetch failed: %s", result)
            continue
        name, entry = result  # type: ignore[misc]
        broker_data[name] = entry
        total_equity += Decimal(str(entry["balance"]["net_liquidation"]))
        total_buying_power += Decimal(str(entry["balance"]["buying_power"]))
        total_positions += len(entry["positions"])

    return {
        "brokers": broker_data,
        "totals": {
            "equity": _decimal_to_float(total_equity),
            "buying_power": _decimal_to_float(total_buying_power),
            "open_positions": total_positions,
        },
    }
