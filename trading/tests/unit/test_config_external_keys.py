"""Tests for external API key fields added to Config (Task 1)."""
import os
import pytest
from config import Config, load_config

@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in [
        "STA_IB_PORT", "STA_BROKER_MODE", "STA_METACULUS_TOKEN",
        "STA_MANIFOLD_MARKETS_KEY", "STA_NEWSAPI_KEY", "STA_ALPHA_VANTAGE_KEY",
        "STA_COINGECKO_API_KEY", "STA_MASSIVE_KEY", "STA_TRADERCONGRESS_API_KEY",
        "STA_TRADIER_TOKEN", "STA_TRADIER_ACCOUNT_ID", "STA_QUIVERQUANT_API_KEY",
        "STA_API_HOST"
    ]:
        if key in os.environ:
            monkeypatch.delenv(key)

def test_external_keys_default_to_none():
    c = load_config(env_file="nonexistent.env")
    assert c.metaculus_token is None
    assert c.manifold_markets_key is None
    assert c.newsapi_key is None
    assert c.alpha_vantage_key is None
    assert c.coingecko_api_key is None
    assert c.massive_key is None
    assert c.tradercongress_api_key is None
    assert c.tradier_token is None
    assert c.tradier_account_id is None
    assert c.quiverquant_api_key is None


def test_external_keys_can_be_set(monkeypatch):
    monkeypatch.setenv("STA_METACULUS_TOKEN", "meta-tok")
    monkeypatch.setenv("STA_MANIFOLD_MARKETS_KEY", "mani-key")
    monkeypatch.setenv("STA_NEWSAPI_KEY", "news-key")
    monkeypatch.setenv("STA_ALPHA_VANTAGE_KEY", "av-key")
    monkeypatch.setenv("STA_COINGECKO_API_KEY", "cg-key")
    monkeypatch.setenv("STA_MASSIVE_KEY", "massive-key")
    monkeypatch.setenv("STA_TRADERCONGRESS_API_KEY", "tc-key")
    monkeypatch.setenv("STA_TRADIER_TOKEN", "tradier-tok")
    monkeypatch.setenv("STA_TRADIER_ACCOUNT_ID", "ACC123")
    monkeypatch.setenv("STA_QUIVERQUANT_API_KEY", "qq-key")

    c = load_config(env_file="nonexistent.env")
    assert c.metaculus_token == "meta-tok"
    assert c.manifold_markets_key == "mani-key"
    assert c.newsapi_key == "news-key"
    assert c.alpha_vantage_key == "av-key"
    assert c.coingecko_api_key == "cg-key"
    assert c.massive_key == "massive-key"
    assert c.tradercongress_api_key == "tc-key"
    assert c.tradier_token == "tradier-tok"
    assert c.tradier_account_id == "ACC123"
    assert c.quiverquant_api_key == "qq-key"


def test_existing_fields_unaffected(monkeypatch):
    """Regression: ensure existing fields still work after adding new ones."""
    monkeypatch.setenv("STA_BROKER_MODE", "paper")
    c = load_config(env_file="nonexistent.env")
    assert c.ib_port == 4002
    assert c.api_host == "127.0.0.1"