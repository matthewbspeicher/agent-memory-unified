"""
Kalshi REST API v2 async HTTP client.

Auth: RSA key-pair (PKCS#8 private key) used to sign a JWT per request.
Docs: https://trading-api.readme.io/reference
"""
from __future__ import annotations

import base64
import hashlib
import logging
import time
from pathlib import Path
from collections.abc import Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)

PROD_BASE = "https://api.elections.kalshi.com/trade-api/v2"
DEMO_BASE = "https://demo-api.kalshi.co/trade-api/v2"


def _build_signature(method: str, path: str, key_id: str, private_key_pem: str) -> dict[str, str]:
    """Return Authorization headers signed with the Kalshi RSASSA-PSS scheme."""
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError as e:
        raise RuntimeError(
            "cryptography package required for Kalshi auth. "
            "Add 'cryptography' to requirements.txt."
        ) from e

    ts_ms = str(int(time.time() * 1000))
    clean_path = path.split("?")[0]
    if not clean_path.startswith("/trade-api/v2"):
        clean_path = "/trade-api/v2" + clean_path
        
    msg = (ts_ms + method.upper() + clean_path).encode()

    private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    signature = private_key.sign(
        msg,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.DIGEST_LENGTH
        ),
        hashes.SHA256()
    )
    sig_b64 = base64.b64encode(signature).decode()

    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-TIMESTAMP": ts_ms,
        "KALSHI-ACCESS-SIGNATURE": sig_b64,
    }


class KalshiClient:
    """Thin async wrapper around Kalshi REST API v2."""

    def __init__(
        self,
        key_id: str | None = None,
        private_key_path: str | None = None,
        demo: bool = True,
        timeout: float = 10.0,
    ) -> None:
        self._key_id = key_id
        self._private_key: str | None = None
        if private_key_path:
            self._private_key = Path(private_key_path).read_text()
        self._base = DEMO_BASE if demo else PROD_BASE
        self._client = httpx.AsyncClient(
            base_url=self._base,
            headers={"Content-Type": "application/json"},
            timeout=timeout,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def ws_connect(self, channels: list[str], callback: Callable[[dict], None]) -> None:
        import websockets
        import json
        import asyncio

        ws_host = self._base.replace("https://", "wss://").replace("v2", "ws/v2")
        
        while True:
            try:
                headers = self._auth_headers("GET", "/trade-api/ws/v2")
                async with websockets.connect(ws_host, additional_headers=headers) as ws:
                    logger.info(f"Kalshi WS connected to {ws_host}")
                    
                    sub_msg = {
                        "id": 1,
                        "cmd": "subscribe",
                        "params": {"channels": channels}
                    }
                    await ws.send(json.dumps(sub_msg))
                    
                    async for message in ws:
                        try:
                            data = json.loads(message)
                            callback(data)
                        except json.JSONDecodeError:
                            pass
                        
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Kalshi WS connection closed. Reconnecting...")
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Kalshi WS error: {e}. Reconnecting...")
                await asyncio.sleep(5)

    def _auth_headers(self, method: str, path: str) -> dict[str, str]:
        if self._key_id and self._private_key:
            return _build_signature(method, path, self._key_id, self._private_key)
        return {}

    async def _get(self, path: str, params: dict | None = None) -> Any:
        headers = self._auth_headers("GET", path)
        resp = await self._client.get(path, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, body: dict) -> Any:
        headers = self._auth_headers("POST", path)
        resp = await self._client.post(path, json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def _delete(self, path: str) -> Any:
        headers = self._auth_headers("DELETE", path)
        resp = await self._client.delete(path, headers=headers)
        resp.raise_for_status()
        return resp.json()

    # -------------------------------------------------------------------------
    # Market data (no auth required for public endpoints)
    # -------------------------------------------------------------------------

    async def get_markets(
        self,
        category: str | None = None,
        status: str = "open",
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict:
        """GET /markets — returns {markets: [...], cursor: ...}"""
        params: dict[str, Any] = {"limit": limit, "status": status}
        if category:
            params["category"] = category
        if cursor:
            params["cursor"] = cursor
        return await self._get("/markets", params=params)

    async def get_all_markets(
        self,
        category: str | None = None,
        status: str = "open",
        max_pages: int = 10,
    ) -> list[dict]:
        """Paginate through /markets, returning a flat list."""
        results: list[dict] = []
        cursor: str | None = None
        for _ in range(max_pages):
            page = await self.get_markets(category=category, status=status, cursor=cursor)
            results.extend(page.get("markets", []))
            cursor = page.get("cursor")
            if not cursor:
                break
        return results

    async def get_market(self, ticker: str) -> dict:
        """GET /markets/{ticker}"""
        data = await self._get(f"/markets/{ticker}")
        return data.get("market", data)

    async def get_orderbook(self, ticker: str, depth: int = 10) -> dict:
        """GET /markets/{ticker}/orderbook"""
        data = await self._get(f"/markets/{ticker}/orderbook", params={"depth": depth})
        return data.get("orderbook", data)

    async def get_trades(self, ticker: str, limit: int = 50) -> list[dict]:
        """GET /markets/{ticker}/trades — recent executed trades."""
        data = await self._get(f"/markets/{ticker}/trades", params={"limit": limit})
        return data.get("trades", [])

    # -------------------------------------------------------------------------
    # Portfolio (auth required)
    # -------------------------------------------------------------------------

    async def get_balance(self) -> dict:
        """GET /portfolio/balance"""
        data = await self._get("/portfolio/balance")
        return data

    async def get_positions(self) -> list[dict]:
        """GET /portfolio/positions"""
        data = await self._get("/portfolio/positions")
        return data.get("market_positions", [])

    async def get_order_history(self, limit: int = 100) -> list[dict]:
        """GET /portfolio/orders"""
        data = await self._get("/portfolio/orders", params={"limit": limit, "status": "all"})
        return data.get("orders", [])

    # -------------------------------------------------------------------------
    # Order management (auth required)
    # -------------------------------------------------------------------------

    async def create_order(
        self,
        ticker: str,
        side: str,          # "yes" | "no"
        count: int,         # number of contracts
        price: int,         # cents 1–99
        order_type: str = "limit",
        expiration_ts: int | None = None,
    ) -> dict:
        """POST /portfolio/orders"""
        body: dict[str, Any] = {
            "ticker": ticker,
            "action": "buy",
            "side": side,
            "count": count,
            "type": order_type,
        }
        if order_type == "limit":
            body["yes_price"] = price if side == "yes" else (100 - price)
        if expiration_ts:
            body["expiration_ts"] = expiration_ts
        data = await self._post("/portfolio/orders", body)
        return data.get("order", data)

    async def cancel_order(self, order_id: str) -> dict:
        """DELETE /portfolio/orders/{order_id}"""
        data = await self._delete(f"/portfolio/orders/{order_id}")
        return data.get("order", data)

    async def check_health(self) -> bool:
        """Verify connectivity by fetching balance."""
        try:
            await self.get_balance()
            return True
        except Exception as e:
            logger.error(f"Kalshi check_health failed: {e}")
            return False
