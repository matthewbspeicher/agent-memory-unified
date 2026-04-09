import asyncio
import hmac
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from api.auth import _get_settings
from api.deps import get_event_bus

router = APIRouter(prefix="/engine/v1/ws", tags=["websockets"])


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)


async def _authenticate_ws(websocket: WebSocket) -> bool:
    """Shared WebSocket authentication: expects {"type": "auth", "api_key": "..."}."""
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
        msg = json.loads(raw)
        settings = _get_settings()
        if msg.get("type") != "auth" or not hmac.compare_digest(
            msg.get("api_key", ""), settings.api_key
        ):
            await websocket.close(code=4001, reason="Invalid API key")
            return False
        return True
    except (asyncio.TimeoutError, json.JSONDecodeError):
        await websocket.close(code=4001, reason="Auth timeout")
        return False


@router.websocket("/public")
async def public_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    if not await _authenticate_ws(websocket):
        return

    event_bus = get_event_bus()
    try:
        async for event in event_bus.subscribe():
            payload = json.dumps(event, cls=CustomJSONEncoder)
            await websocket.send_text(payload)
    except WebSocketDisconnect:
        pass


@router.websocket("")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    if not await _authenticate_ws(websocket):
        return

    event_bus = get_event_bus()
    try:
        async for event in event_bus.subscribe():
            payload = json.dumps(event, cls=CustomJSONEncoder)
            await websocket.send_text(payload)
    except WebSocketDisconnect:
        pass


@router.websocket("/spreads")
async def spreads_websocket_endpoint(websocket: WebSocket):
    """Real-time spread monitoring WebSocket endpoint.

    Streams spread observations filtered to only include:
    - New spread opportunities (gap_cents >= threshold)
    - Claim/release events
    - Price updates on monitored pairs

    Client can send {"type": "subscribe", "tickers": ["KALSHI_X", "POLY_X"]} to filter.
    Default: streams all spreads with gap >= 3 cents.
    """
    await websocket.accept()
    if not await _authenticate_ws(websocket):
        return

    event_bus = get_event_bus()
    subscribed_tickers: set[str] | None = None
    min_gap = 3  # default minimum gap in cents

    try:
        while True:
            try:
                # Non-blocking check for client messages (subscription updates)
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                msg = json.loads(raw)
                if msg.get("type") == "subscribe":
                    tickers = msg.get("tickers", [])
                    subscribed_tickers = set(tickers) if tickers else None
                elif msg.get("type") == "min_gap":
                    min_gap = int(msg.get("value", 3))
            except asyncio.TimeoutError:
                pass  # No client message, continue streaming

            async for event in event_bus.subscribe():
                event_type = event.get("event_type", "")
                # Filter for spread-related events
                if event_type not in (
                    "spread.new",
                    "spread.claimed",
                    "spread.released",
                    "spread.update",
                ):
                    continue

                data = event.get("data", {})
                spread_gap = data.get("gap_cents", 0)
                if spread_gap < min_gap:
                    continue

                # Filter by subscribed tickers if specified
                if subscribed_tickers is not None:
                    pair_tickers = {data.get("kalshi_ticker"), data.get("poly_ticker")}
                    if not pair_tickers & subscribed_tickers:
                        continue

                payload = json.dumps(event, cls=CustomJSONEncoder)
                await websocket.send_text(payload)
    except WebSocketDisconnect:
        pass
