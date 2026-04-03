"""
Tests for config.py - Config dataclass and load_config()
"""
import os
import tempfile
from pathlib import Path

import pytest

from config import Config, load_config


class TestConfigDefaults:
    """Test that Config has sensible defaults"""

    def test_default_ib_connection(self):
        config = Config()
        assert config.ib_host == "127.0.0.1"
        assert config.ib_port is None
        assert config.ib_client_id == 1
        assert config.ib_readonly is False

    def test_default_api_settings(self):
        config = Config()
        assert config.api_host == "127.0.0.1"
        assert config.api_port == 8000
        assert config.api_key == ""

    def test_default_storage_settings(self):
        config = Config()
        assert config.db_path == "data.db"
        assert config.database_url is None
        assert config.broker_mode == "paper"

    def test_default_paper_trading(self):
        config = Config()
        assert config.paper_trading is True
        assert config.paper_trading_initial_balance == 10000.0


class TestLoadConfigFromEnv:
    """Test load_config() reads from environment variables"""

    def test_loads_ib_host_from_env(self, monkeypatch):
        monkeypatch.setenv("STA_IB_HOST", "192.168.1.100")
        config = load_config(env_file="nonexistent.env")
        assert config.ib_host == "192.168.1.100"

    def test_loads_ib_port_from_env(self, monkeypatch):
        monkeypatch.setenv("STA_IB_PORT", "7497")
        config = load_config(env_file="nonexistent.env")
        assert config.ib_port == 7497

    def test_loads_boolean_from_env(self, monkeypatch):
        monkeypatch.setenv("STA_IB_READONLY", "true")
        config = load_config(env_file="nonexistent.env")
        assert config.ib_readonly is True

        monkeypatch.setenv("STA_IB_READONLY", "false")
        config = load_config(env_file="nonexistent.env")
        assert config.ib_readonly is False

    def test_loads_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("STA_API_KEY", "test-secret-key")
        config = load_config(env_file="nonexistent.env")
        assert config.api_key == "test-secret-key"

    def test_loads_list_from_env(self, monkeypatch):
        monkeypatch.setenv("STA_LLM_FALLBACK_CHAIN", "anthropic,groq,ollama")
        config = load_config(env_file="nonexistent.env")
        assert config.llm_fallback_chain == ["anthropic", "groq", "ollama"]


class TestLoadConfigFromDotEnv:
    """Test load_config() reads from .env file"""

    def test_reads_dotenv_file(self, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("STA_IB_HOST=10.0.0.5\nSTA_API_PORT=9000\n")

        config = load_config(env_file=str(env_file))
        assert config.ib_host == "10.0.0.5"
        assert config.api_port == 9000

    def test_env_vars_override_dotenv(self, tmp_path, monkeypatch):
        env_file = tmp_path / ".env"
        env_file.write_text("STA_IB_HOST=10.0.0.5\n")

        monkeypatch.setenv("STA_IB_HOST", "192.168.1.100")
        config = load_config(env_file=str(env_file))
        assert config.ib_host == "192.168.1.100"

    def test_handles_missing_dotenv_file(self):
        config = load_config(env_file="nonexistent.env")
        # Should not raise, just use defaults
        assert config.ib_host == "127.0.0.1"


class TestBrokerValidation:
    """Test broker name validation"""

    def test_valid_primary_broker(self, monkeypatch):
        monkeypatch.setenv("STA_PRIMARY_BROKER", "ibkr")
        config = load_config(env_file="nonexistent.env")
        assert config.primary_broker == "ibkr"

    def test_invalid_primary_broker_raises(self, monkeypatch):
        monkeypatch.setenv("STA_PRIMARY_BROKER", "invalid_broker")
        with pytest.raises(ValueError, match="Unknown primary_broker"):
            load_config(env_file="nonexistent.env")

    def test_valid_broker_routing(self, monkeypatch):
        # JSON-encoded dict in env var
        monkeypatch.setenv("STA_BROKER_ROUTING", '{"STOCK": "alpaca", "OPTION": "ibkr"}')
        config = load_config(env_file="nonexistent.env")
        assert config.broker_routing == {"STOCK": "alpaca", "OPTION": "ibkr"}

    def test_invalid_broker_in_routing_raises(self, monkeypatch):
        monkeypatch.setenv("STA_BROKER_ROUTING", '{"STOCK": "unknown"}')
        with pytest.raises(ValueError, match="Unknown broker"):
            load_config(env_file="nonexistent.env")


class TestIBPortDefault:
    """Test IB port gets defaulted based on broker_mode"""

    def test_paper_mode_defaults_to_4002(self, monkeypatch):
        monkeypatch.setenv("STA_BROKER_MODE", "paper")
        config = load_config(env_file="nonexistent.env")
        assert config.ib_port == 4002

    def test_live_mode_defaults_to_4001(self, monkeypatch):
        monkeypatch.setenv("STA_BROKER_MODE", "live")
        monkeypatch.setenv("STA_API_KEY", "test-key")  # Required for live
        config = load_config(env_file="nonexistent.env")
        assert config.ib_port == 4001

    def test_explicit_port_not_overridden(self, monkeypatch):
        monkeypatch.setenv("STA_BROKER_MODE", "paper")
        monkeypatch.setenv("STA_IB_PORT", "7497")
        config = load_config(env_file="nonexistent.env")
        assert config.ib_port == 7497

    def test_live_mode_requires_api_key(self, monkeypatch):
        monkeypatch.setenv("STA_BROKER_MODE", "live")
        with pytest.raises(ValueError, match="STA_API_KEY must be set"):
            load_config(env_file="nonexistent.env")

    def test_paper_mode_without_api_key_warns(self, monkeypatch):
        monkeypatch.setenv("STA_BROKER_MODE", "paper")
        with pytest.warns(UserWarning, match="paper mode without STA_API_KEY"):
            config = load_config(env_file="nonexistent.env")
        assert config.api_key == ""


class TestComplexTypes:
    """Test handling of complex types (dicts, lists)"""

    def test_dict_from_env(self, monkeypatch):
        monkeypatch.setenv("STA_BROKER_ROUTING", '{"STOCK": "alpaca"}')
        config = load_config(env_file="nonexistent.env")
        assert config.broker_routing == {"STOCK": "alpaca"}

    def test_list_from_env(self, monkeypatch):
        monkeypatch.setenv("STA_NEWS_FEEDS", "https://feed1.com,https://feed2.com")
        config = load_config(env_file="nonexistent.env")
        assert config.news_feeds == ["https://feed1.com", "https://feed2.com"]

    def test_empty_list_from_env(self, monkeypatch):
        monkeypatch.setenv("STA_NEWS_FEEDS", "")
        config = load_config(env_file="nonexistent.env")
        assert config.news_feeds == []
