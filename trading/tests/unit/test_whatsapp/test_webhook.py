import pytest
import hashlib
import hmac
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from whatsapp.webhook import create_webhook_router


APP_SECRET = "test-secret"
VERIFY_TOKEN = "test-verify-token"
ALLOWED = "15551234567"


@pytest.fixture
def app():
    from unittest.mock import AsyncMock
    assistant = AsyncMock()
    wa_router = create_webhook_router(
        assistant=assistant,
        verify_token=VERIFY_TOKEN,
        app_secret=APP_SECRET,
        allowed_numbers=ALLOWED,
    )
    app = FastAPI()
    app.include_router(wa_router)
    return app, assistant


def test_verify_challenge(app):
    fast_app, _ = app
    client = TestClient(fast_app)
    resp = client.get("/webhook/whatsapp", params={
        "hub.mode": "subscribe",
        "hub.verify_token": VERIFY_TOKEN,
        "hub.challenge": "challenge-123",
    })
    assert resp.status_code == 200
    assert resp.text == "challenge-123"


def test_verify_wrong_token(app):
    fast_app, _ = app
    client = TestClient(fast_app)
    resp = client.get("/webhook/whatsapp", params={
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong",
        "hub.challenge": "challenge-123",
    })
    assert resp.status_code == 403


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _make_payload(phone: str, text: str, msg_id: str = "msg-1"):
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": phone,
                        "type": "text",
                        "text": {"body": text},
                        "id": msg_id,
                    }]
                }
            }]
        }]
    }


def test_post_valid_message(app):
    fast_app, assistant = app
    client = TestClient(fast_app)
    body = json.dumps(_make_payload("15551234567", "hello")).encode()
    sig = _sign(body, APP_SECRET)
    resp = client.post(
        "/webhook/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200


def test_post_invalid_signature(app):
    fast_app, _ = app
    client = TestClient(fast_app)
    body = json.dumps(_make_payload("15551234567", "hello")).encode()
    resp = client.post(
        "/webhook/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": "sha256=wrong", "Content-Type": "application/json"},
    )
    assert resp.status_code == 401


def test_post_disallowed_number(app):
    fast_app, assistant = app
    client = TestClient(fast_app)
    body = json.dumps(_make_payload("19999999999", "hello")).encode()
    sig = _sign(body, APP_SECRET)
    resp = client.post(
        "/webhook/whatsapp",
        content=body,
        headers={"X-Hub-Signature-256": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200  # returns 200 but doesn't dispatch
    assistant.handle.assert_not_called()
