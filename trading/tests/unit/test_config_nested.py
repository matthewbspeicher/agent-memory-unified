# trading/tests/unit/test_config_nested.py
import os
import pytest
from config import load_config


@pytest.fixture(autouse=True)
def _clean_sta_env(monkeypatch):
    """Remove all STA_ env vars so load_config gets true defaults."""
    for key in list(os.environ):
        if key.startswith("STA_"):
            monkeypatch.delenv(key)


class TestNestedConfig:
    def test_bittensor_config_nested(self):
        """Bittensor settings should be accessible via config.bittensor."""
        config = load_config(env_file="/dev/null")
        assert hasattr(config, "bittensor")
        assert config.bittensor.enabled is False
        assert config.bittensor.network == "finney"
        assert config.bittensor.subnet_uid == 8

    def test_broker_config_nested(self):
        config = load_config(env_file="/dev/null")
        assert hasattr(config, "broker")
        assert config.broker.ib_host == "127.0.0.1"
        assert config.broker.mode == "paper"

    def test_backward_compat_flat_access(self):
        """Flat attribute access should still work for migration period."""
        config = load_config(env_file="/dev/null")
        # These should work via __getattr__ delegation
        assert config.bittensor_enabled is False
        assert config.ib_host == "127.0.0.1"
