import time
from whatsapp.confirmation import ConfirmationGate


def test_create_pending():
    gate = ConfirmationGate()
    token = gate.create("15551234567", "place_order", {"symbol": "AAPL", "qty": 100})
    assert len(token) >= 6
    assert gate.has_pending("15551234567")


def test_confirm_with_correct_token():
    gate = ConfirmationGate()
    token = gate.create("15551234567", "place_order", {"symbol": "AAPL"})
    action = gate.confirm("15551234567", token)
    assert action is not None
    assert action.action_type == "place_order"
    assert action.data["symbol"] == "AAPL"
    assert not gate.has_pending("15551234567")


def test_confirm_with_wrong_token():
    gate = ConfirmationGate()
    gate.create("15551234567", "place_order", {"symbol": "AAPL"})
    action = gate.confirm("15551234567", "WRONG")
    assert action is None
    assert gate.has_pending("15551234567")


def test_cancel():
    gate = ConfirmationGate()
    gate.create("15551234567", "place_order", {"symbol": "AAPL"})
    result = gate.cancel("15551234567")
    assert result is True
    assert not gate.has_pending("15551234567")


def test_expiry():
    gate = ConfirmationGate(ttl_seconds=0)  # immediate expiry
    gate.create("15551234567", "place_order", {"symbol": "AAPL"})
    time.sleep(0.01)
    assert not gate.has_pending("15551234567")


def test_new_confirmation_replaces_old():
    gate = ConfirmationGate()
    token1 = gate.create("15551234567", "place_order", {"symbol": "AAPL"})
    token2 = gate.create("15551234567", "toggle_kill", {"enable": True})
    assert token1 != token2
    action = gate.confirm("15551234567", token1)
    assert action is None  # old token invalidated
    action = gate.confirm("15551234567", token2)
    assert action is not None
    assert action.action_type == "toggle_kill"
