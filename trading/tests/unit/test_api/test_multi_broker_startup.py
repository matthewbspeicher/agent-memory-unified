from __future__ import annotations

import pytest


def test_config_rejects_unknown_primary_broker(monkeypatch):
    monkeypatch.setenv("STA_PRIMARY_BROKER", "alpaka")
    monkeypatch.setenv("STA_API_KEY", "test")
    from config import load_config

    with pytest.raises(ValueError, match="Unknown"):
        load_config(env_file="nonexistent.env")


def test_config_rejects_unknown_routing_broker(monkeypatch):
    monkeypatch.setenv("STA_BROKER_ROUTING", '{"STOCK": "alpaka"}')
    monkeypatch.setenv("STA_API_KEY", "test")
    from config import load_config

    with pytest.raises(ValueError, match="Unknown"):
        load_config(env_file="nonexistent.env")


def test_config_accepts_valid_brokers(monkeypatch):
    monkeypatch.setenv("STA_PRIMARY_BROKER", "alpaca")
    monkeypatch.setenv("STA_BROKER_ROUTING", '{"STOCK": "alpaca", "OPTION": "tradier"}')
    monkeypatch.setenv("STA_API_KEY", "test")
    from config import load_config

    c = load_config(env_file="nonexistent.env")
    assert c.primary_broker == "alpaca"
    assert c.broker_routing == {"STOCK": "alpaca", "OPTION": "tradier"}
