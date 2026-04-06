import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from api.auth import _get_settings
from api.deps import get_event_bus

router = APIRouter(prefix="/ws", tags=["websockets"])


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)


@router.websocket("/public")
async def public_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # We can just start sending events
    event_bus = get_event_bus()
    try:
        async for event in event_bus.subscribe():
            # Only broadcast public events if needed, or all for now
            payload = json.dumps(event, cls=CustomJSONEncoder)
            await websocket.send_text(payload)
    except WebSocketDisconnect:
        pass

@router.websocket("")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
        msg = json.loads(raw)
        settings = _get_settings()
        if msg.get("type") != "auth" or msg.get("api_key") != settings.api_key:
            await websocket.close(code=4001, reason="Invalid API key")
            return
    except (asyncio.TimeoutError, json.JSONDecodeError):
        await websocket.close(code=4001, reason="Auth timeout")
        return

    event_bus = get_event_bus()
    try:
        async for event in event_bus.subscribe():
            payload = json.dumps(event, cls=CustomJSONEncoder)
            await websocket.send_text(payload)
    except WebSocketDisconnect:
        pass
