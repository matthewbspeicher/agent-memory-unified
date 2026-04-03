"""Integration tests against Kalshi demo environment.

Skipped automatically unless KALSHI_DEMO=true AND KALSHI_API_KEY_ID/KALSHI_PRIVATE_KEY_PATH are set.
Run with: cd python && KALSHI_DEMO=true pytest tests/integration/test_kalshi_demo.py -v
"""
from __future__ import annotations

import os
import pytest

DEMO_ENABLED = (
    os.getenv("KALSHI_DEMO", "").lower() == "true"
    and os.getenv("KALSHI_API_KEY_ID")
    and os.getenv("KALSHI_PRIVATE_KEY_PATH")
)

skip_unless_demo = pytest.mark.skipif(
    not DEMO_ENABLED,
    reason="KALSHI_DEMO=true and credentials required",
)


@skip_unless_demo
@pytest.mark.asyncio
async def test_rsa_signing_get_balance():
    """RSA auth headers accepted by Kalshi demo — balance endpoint returns dict."""
    from adapters.kalshi.client import KalshiClient
    client = KalshiClient(
        key_id=os.environ["KALSHI_API_KEY_ID"],
        private_key_path=os.environ["KALSHI_PRIVATE_KEY_PATH"],
        demo=True,
    )
    try:
        balance = await client.get_balance()
        assert isinstance(balance, dict)
        assert "available_balance" in balance or "portfolio_value" in balance
    finally:
        await client.close()


@skip_unless_demo
@pytest.mark.asyncio
async def test_get_markets_returns_contracts():
    """Public /markets endpoint returns at least one contract."""
    from adapters.kalshi.client import KalshiClient
    client = KalshiClient(demo=True)
    try:
        page = await client.get_markets(status="open", limit=5)
        assert "markets" in page
        assert len(page["markets"]) > 0
        m = page["markets"][0]
        assert "ticker" in m
        assert "title" in m
    finally:
        await client.close()


@skip_unless_demo
@pytest.mark.asyncio
async def test_get_positions_returns_list():
    """Authenticated /portfolio/positions returns a list."""
    from adapters.kalshi.client import KalshiClient
    client = KalshiClient(
        key_id=os.environ["KALSHI_API_KEY_ID"],
        private_key_path=os.environ["KALSHI_PRIVATE_KEY_PATH"],
        demo=True,
    )
    try:
        positions = await client.get_positions()
        assert isinstance(positions, list)
    finally:
        await client.close()


@skip_unless_demo
@pytest.mark.asyncio
async def test_get_order_history_returns_list():
    """Authenticated /portfolio/orders returns a list."""
    from adapters.kalshi.client import KalshiClient
    client = KalshiClient(
        key_id=os.environ["KALSHI_API_KEY_ID"],
        private_key_path=os.environ["KALSHI_PRIVATE_KEY_PATH"],
        demo=True,
    )
    try:
        orders = await client.get_order_history(limit=10)
        assert isinstance(orders, list)
    finally:
        await client.close()
