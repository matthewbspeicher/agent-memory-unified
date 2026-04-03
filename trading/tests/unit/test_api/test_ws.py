import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from api.routes.ws import router
from data.events import EventBus

@pytest.fixture
def ws_app():
    app = FastAPI()
    bus = EventBus()

    from api.deps import _init_state
    app.state.event_bus = bus
    _init_state(app.state)

    app.include_router(router)
    yield app, bus


def test_websocket_rejects_without_api_key(ws_app):
    app, bus = ws_app
    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws"):
            pass


def test_websocket_rejects_invalid_api_key(ws_app):
    app, bus = ws_app
    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws?api_key=wrong"):
            pass
