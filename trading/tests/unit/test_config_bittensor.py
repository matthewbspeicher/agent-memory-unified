"""Tests for BittensorConfig nested extraction."""
import os
from config import load_config, Config, BittensorConfig


class TestBittensorConfigNested:
    def test_defaults_accessible_via_nested(self):
        config = load_config(env_file="/dev/null")
        assert isinstance(config.bittensor, BittensorConfig)
        assert config.bittensor.enabled is False
        assert config.bittensor.network == "finney"
        assert config.bittensor.subnet_uid == 8
        assert config.bittensor.wallet_name == "sta_wallet"
        assert config.bittensor.mock is False

    def test_backward_compat_flat_access(self):
        config = load_config(env_file="/dev/null")
        # __getattr__ should delegate bittensor_* to bittensor.*
        assert config.bittensor_enabled is False
        assert config.bittensor_network == "finney"
        assert config.bittensor_subnet_uid == 8
        assert config.bittensor_mock is False

    def test_env_var_populates_nested(self):
        env = {
            "STA_BITTENSOR_ENABLED": "true",
            "STA_BITTENSOR_NETWORK": "test",
            "STA_BITTENSOR_SUBNET_UID": "42",
            "STA_BITTENSOR_MOCK": "true",
        }
        orig = {}
        for k, v in env.items():
            orig[k] = os.environ.get(k)
            os.environ[k] = v
        try:
            config = load_config(env_file="/dev/null")
            assert config.bittensor.enabled is True
            assert config.bittensor.network == "test"
            assert config.bittensor.subnet_uid == 42
            assert config.bittensor.mock is True
            # backward compat too
            assert config.bittensor_enabled is True
            assert config.bittensor_network == "test"
        finally:
            for k, v in orig.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_non_bittensor_attr_raises(self):
        config = load_config(env_file="/dev/null")
        try:
            _ = config.nonexistent_field_xyz
            assert False, "Should have raised AttributeError"
        except AttributeError:
            pass
